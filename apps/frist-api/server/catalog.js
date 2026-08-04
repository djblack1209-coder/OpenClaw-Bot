import {
  normalizeModelGroup, inferProviderGroup,
  normalizeOfficialModelName, normalizeOfficialModelList, modelMatchesGroup,
} from '../src/core.js';
import {
  DEFAULT_MODEL, DEFAULT_PUBLIC_MODEL, DEFAULT_RECHARGE_PLANS, DEFAULT_MODEL_PRICES, DEFAULT_MODEL_CATALOG,
  round2, formatCny, formatUsdFromCnyCents, compactTokenText,
  poolPriority, findModelPrice, priceLabel, uniqueStrings,
  sortModelsByStrength, strongestModel, sanitizeRiskNote, PRIMARY_SOURCE_TYPE,
  providerFromModel, taglineForModel, contextForModel,
  isSourceRouteApproved, isCredentialRouteApproved,
  effectiveCredentialGroup, estimateCredentialWaste, normalizePool,
  normalizeRechargePlan, reconcileUserBalance,
} from './shared.js';

export { normalizeRechargePlan, reconcileUserBalance };

const DEFAULT_MODEL_PRICE_BY_MODEL = new Map(
  DEFAULT_MODEL_PRICES.map((price) => [normalizeOfficialModelName(price.model), price]),
);

export function pricingPayload(data) {
  const pricing = normalizePricingConfig(data.pricing || {});
  return { rechargePlans: pricing.rechargePlans, modelPrices: pricing.modelPrices };
}

export function normalizePricingConfig(input = {}) {
  const rechargePlans = normalizeRechargePlans(input.rechargePlans);
  const modelPrices = normalizeModelPrices(input.modelPrices);
  return { rechargePlans, modelPrices };
}

export function normalizeRechargePlans(plans) {
  const rows = Array.isArray(plans) && plans.length ? plans : DEFAULT_RECHARGE_PLANS;
  return rows
    .map((plan, index) => {
      const quotaUsd = Math.max(0, Number(plan.quotaUsd || 0));
      const priceCny = Math.max(0, Number(plan.priceCny ?? plan.amountCny ?? 0));
      const durationDays = Math.max(0, Number(plan.durationDays || 0));
      const inferredPlan = durationDays === 1 ? 'day' : 'balance';
      return {
        id: String(plan.id || `plan-${index + 1}`).trim(),
        label: String(plan.label || `Codex API ${quotaUsd}刀额度/${durationDays === 1 ? '日卡' : '不限时'}`).trim(),
        quotaUsd,
        priceCny: round2(priceCny),
        durationDays,
        plan: normalizeRechargePlan(plan.plan || inferredPlan),
        active: index === 0,
      };
    })
    .filter((plan) => plan.id && plan.quotaUsd > 0 && plan.priceCny > 0);
}

export function normalizeModelPrices(prices) {
  const rows = Array.isArray(prices) && prices.length ? prices : DEFAULT_MODEL_PRICES;
  const merged = new Map();
  for (const price of rows) {
    const model = normalizeOfficialModelName(price.model);
    if (!model) continue;
    const source = String(price.source || 'official').trim() || 'official';
    const officialDefault = source.toLowerCase() === 'official' && !String(price.displayPrice || '').trim()
      ? DEFAULT_MODEL_PRICE_BY_MODEL.get(model)
      : null;
    const normalizedPrice = officialDefault || price;
    merged.set(model, {
      model,
      currency: String(normalizedPrice.currency || 'CNY').toUpperCase(),
      inputCostCnyPerMillion: round2(Number(normalizedPrice.inputCostCnyPerMillion || 0)),
      outputCostCnyPerMillion: round2(Number(normalizedPrice.outputCostCnyPerMillion || 0)),
      inputSaleCnyPerMillion: round2(Number(normalizedPrice.inputSaleCnyPerMillion ?? normalizedPrice.inputCostCnyPerMillion ?? 0)),
      outputSaleCnyPerMillion: round2(Number(normalizedPrice.outputSaleCnyPerMillion ?? normalizedPrice.outputCostCnyPerMillion ?? 0)),
      source: String(normalizedPrice.source || source),
      status: String(price.status || normalizedPrice.status || 'confirmed'),
      displayPrice: String(normalizedPrice.displayPrice || '').trim(),
    });
  }
  return [...merged.values()];
}

export function mergeModelPrices(existing, configured) {
  const merged = new Map();
  for (const price of normalizeModelPrices(configured)) {
    merged.set(price.model, price);
  }
  for (const price of Array.isArray(existing) ? existing : []) {
    const model = normalizeOfficialModelName(price.model);
    if (!model || merged.has(model)) continue;
    merged.set(model, { ...price, model });
  }
  return [...merged.values()];
}

export function normalizeCredentialRecord(credential) {
  const sourceType = normalizeSourceTypeLocal(credential.sourceType || PRIMARY_SOURCE_TYPE);
  return {
    ...credential,
    models: normalizeOfficialModelList(credential.models || []),
    modelGroup: normalizeModelGroup(credential.modelGroup || inferProviderGroup((credential.models || []).join('\n'))),
    sourceType,
    riskStatus: normalizeRiskStatusLocal(credential.riskStatus || 'approved'),
    backupRiskAccepted: Boolean(credential.backupRiskAccepted),
    riskNote: sanitizeRiskNote(credential.riskNote || ''),
  };
}

export function normalizeSupplierProfileRecord(profile) {
  const sourceType = normalizeSourceTypeLocal(profile.sourceType || PRIMARY_SOURCE_TYPE);
  return {
    ...profile,
    models: normalizeOfficialModelList(profile.models || []),
    modelGroup: normalizeModelGroup(profile.modelGroup || inferProviderGroup((profile.models || []).join('\n'))),
    sourceType,
    riskStatus: normalizeRiskStatusLocal(profile.riskStatus || 'approved'),
    backupRiskAccepted: Boolean(profile.backupRiskAccepted),
    riskNote: sanitizeRiskNote(profile.riskNote || ''),
  };
}

function normalizeSourceTypeLocal(value) {
  const sourceType = String(value || '').trim().toLowerCase();
  if (sourceType === PRIMARY_SOURCE_TYPE || sourceType === 'official' || sourceType === 'primary') return PRIMARY_SOURCE_TYPE;
  if (sourceType === 'cpa' || sourceType === 'cpa_json' || sourceType === 'cpa_json_backup') return 'cpa_json_backup';
  if (sourceType === 'chong' || sourceType === 'chong_backup') return 'chong_backup';
  if (sourceType === 'manual_backup' || sourceType === 'other_backup' || sourceType === 'backup') return 'manual_backup';
  return PRIMARY_SOURCE_TYPE;
}

function normalizeRiskStatusLocal(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'approved' || status === 'pass' || status === 'allowed') return 'approved';
  if (status === 'blocked' || status === 'rejected' || status === 'disabled') return 'blocked';
  return 'quarantined';
}

export function availableModelsForCustomer(data, user, key, requestedModel = '') {
  expireUserPlanIfNeeded(data, user, {});
  const allowedPools = allowedPoolsForUser(user);
  const liveModels = data.credentials
    .filter((credential) => allowedPools.includes(credential.pool))
    .filter((credential) => credential.enabled)
    .filter((credential) => credential.status === 'healthy')
    .filter(isCredentialRouteApproved)
    .filter((credential) => Number(credential.quotaRemaining || 0) > 0)
    .filter((credential) => credentialMatchesModelGroup(credential, '', key.modelGroup))
    .flatMap((credential) => credential.models || [])
    .filter((model) => modelMatchesGroup(model, key.modelGroup || 'All'));
  const requested = normalizeOfficialModelName(requestedModel);
  const liveSet = new Set(liveModels);
  return sortModelsByStrength(uniqueStrings([...(requested && liveSet.has(requested) ? [requested] : []), ...liveModels]));
}

function credentialMatchesModelGroup(credential, model, keyGroup) {
  const normalizedKeyGroup = normalizeModelGroup(keyGroup || 'All');
  if (normalizedKeyGroup === 'All') return true;
  const credentialGroup = normalizeModelGroup(credential.modelGroup || 'All');
  if (credentialGroup !== 'All' && credentialGroup !== normalizedKeyGroup) return false;
  if (model) return modelMatchesGroup(model, normalizedKeyGroup);
  return (credential.models || []).some((item) => modelMatchesGroup(item, normalizedKeyGroup));
}

export function buildGatewayModels(data, request) {
  const userKey = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === userKey.userId);
  if (!user) throw publicError(401, '用户不存在');
  expireUserPlanIfNeeded(data, user, {});
  const allowedPools = allowedPoolsForUser(user);
  const models = uniqueStrings(
    data.credentials
      .filter((credential) => allowedPools.includes(credential.pool))
      .filter((credential) => credential.enabled)
      .filter((credential) => credential.status === 'healthy')
      .filter(isCredentialRouteApproved)
      .filter((credential) => Number(credential.quotaRemaining || 0) > 0)
      .filter((credential) => credentialMatchesModelGroup(credential, '', userKey.modelGroup))
      .flatMap((credential) => credential.models || []),
  ).filter((model) => modelMatchesGroup(model, userKey.modelGroup || 'All'));
  const sortedModels = sortModelsByStrength(models);
  return {
    object: 'list',
    data: sortedModels.map((model) => ({ id: model, object: 'model', owned_by: 'frist-api' })),
  };
}

export function buildModelCatalog(data) {
  const liveByModel = buildLiveModelMap(data);
  const rowsByModel = new Map();
  const auditCatalogByModel = new Map(
    DEFAULT_MODEL_CATALOG.map((item) => [normalizeOfficialModelName(item.model), item]),
  );
  for (const model of uniqueStrings(data.credentials.flatMap((credential) => credential.models || []))) {
    const live = liveByModel.get(model);
    const price = findModelPrice(data, model);
    rowsByModel.set(model, {
      model, family: live?.provider || auditCatalogByModel.get(model)?.family || providerFromModel(model),
      tagline: auditCatalogByModel.get(model)?.tagline || taglineForModel(model),
      context: auditCatalogByModel.get(model)?.context || contextForModel(model),
      price: price ? priceLabel(price) : auditCatalogByModel.get(model)?.price || '参考标价待同步',
      available: Boolean(live?.ok),
    });
  }
  return [...rowsByModel.values()].sort((left, right) => {
    const liveDelta = Number(right.available) - Number(left.available);
    if (liveDelta !== 0) return liveDelta;
    return `${left.family}:${left.model}`.localeCompare(`${right.family}:${right.model}`);
  });
}

function buildLiveModelMap(data) {
  const rows = new Map();
  for (const credential of data.credentials || []) {
    const provider = effectiveCredentialGroup(credential);
    const isLive =
      credential.enabled &&
      credential.status === 'healthy' &&
      isCredentialRouteApproved(credential) &&
      Number(credential.quotaRemaining || 0) > 0;
    for (const model of normalizeOfficialModelList(credential.models || [])) {
      const current = rows.get(model);
      rows.set(model, {
        provider: current?.provider || provider || providerFromModel(model),
        ok: Boolean(current?.ok || isLive),
      });
    }
  }
  return rows;
}

export function buildModelUsage(data, user) {
  const events = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  const totals = new Map();
  for (const event of events) {
    const current = totals.get(event.model) || { cost: 0, calls: 0, tokens: 0 };
    current.cost += Number(event.quotaCost || 0);
    current.calls += 1;
    current.tokens += Number(event.totalTokens || 0);
    totals.set(event.model, current);
  }
  const totalCost = [...totals.values()].reduce((sum, item) => sum + item.cost, 0) || 1;
  return [...totals.entries()].map(([model, usage]) => ({
    model,
    amount: formatUsdFromCnyCents(usage.cost),
    amountCny: formatCny(usage.cost),
    calls: `${usage.calls} 次`,
    tokens: compactTokenText(usage.tokens),
    percent: Math.max(4, Math.round((usage.cost / totalCost) * 100)),
  }));
}

export function buildInventorySummary(data) {
  const buckets = new Map();
  for (const credential of data.credentials) {
    const group = effectiveCredentialGroup(credential);
    const key = `${credential.pool || 'default'}:${group}`;
    const current = buckets.get(key) || {
      pool: credential.pool || 'default', providerGroup: group, totalKeys: 0, healthyKeys: 0,
      quotaRemaining: 0, quotaTotal: 0, wasteEstimate: 0, nearestExpiresAt: '',
    };
    current.totalKeys += 1;
    if (credential.enabled && credential.status === 'healthy' && isCredentialRouteApproved(credential)) {
      current.healthyKeys += 1;
      current.quotaRemaining += Number(credential.quotaRemaining || 0);
    }
    current.quotaTotal += Number(credential.quotaTotal || credential.quotaRemaining || 0);
    current.wasteEstimate += estimateCredentialWaste(credential).quotaRemaining;
    if (credential.expiresAt && (!current.nearestExpiresAt || Date.parse(credential.expiresAt) < Date.parse(current.nearestExpiresAt))) {
      current.nearestExpiresAt = credential.expiresAt;
    }
    buckets.set(key, current);
  }
  return [...buckets.values()]
    .sort((left, right) => poolPriority(left.pool) - poolPriority(right.pool) || left.providerGroup.localeCompare(right.providerGroup))
    .map((item) => ({
      ...item, totalCount: item.totalKeys, healthyCount: item.healthyKeys,
      remainingRatio: item.quotaTotal > 0 ? Number((item.quotaRemaining / item.quotaTotal).toFixed(4)) : 0,
      quotaRemainingText: formatCny(item.quotaRemaining), quotaTotalText: formatCny(item.quotaTotal),
      wasteText: formatCny(item.wasteEstimate),
    }));
}

export function availableQuotaCents(user) {
  reconcileUserBalance(user);
  return Number(user.packageQuotaCents || 0) + Number(user.boosterQuotaCents || 0);
}

export function deductUserQuota(user, quotaCost) {
  let remaining = Number(quotaCost || 0);
  const packageDeduction = Math.min(Number(user.packageQuotaCents || 0), remaining);
  user.packageQuotaCents = Math.max(0, Number(user.packageQuotaCents || 0) - packageDeduction);
  remaining -= packageDeduction;
  const boosterDeduction = Math.min(Number(user.boosterQuotaCents || 0), Math.max(0, remaining));
  if (remaining > 0) {
    user.boosterQuotaCents = Math.max(0, Number(user.boosterQuotaCents || 0) - boosterDeduction);
  }
  reconcileUserBalance(user);
  return { packageCents: packageDeduction, boosterCents: boosterDeduction };
}

export function expireUserPlanIfNeeded(data, user, serverOptions, options = {}) {
  const plan = String(user.plan || '');
  const planCanExpire = plan.includes('日卡') || plan.includes('月卡');
  if (!planCanExpire) { reconcileUserBalance(user); return false; }

  const expiresAtMs = planExpiryMs(user);
  if (!Number.isFinite(expiresAtMs) || currentDate(serverOptions).getTime() < expiresAtMs) {
    reconcileUserBalance(user); return false;
  }

  const now = currentDate(serverOptions).toISOString();
  const expiredPlan = user.plan;
  user.packageQuotaCents = 0;
  user.plan = '默认套餐';
  user.renewalDate = '-';
  user.planExpiresAt = '';
  user.updatedAt = now;
  reconcileUserBalance(user);

  if (options.recordEvent !== false && data?.events) {
    data.events.push({ type: 'plan_expired', userId: user.id, plan: expiredPlan, at: now });
  }
  return true;
}

function planExpiryMs(user) {
  if (user.planExpiresAt) return Date.parse(user.planExpiresAt);
  if (user.renewalDate && user.renewalDate !== '-') return Date.parse(`${user.renewalDate}T00:00:00.000Z`);
  return Number.NaN;
}

export function currentDate(serverOptions = {}) {
  const value = typeof serverOptions.nowFactory === 'function' ? serverOptions.nowFactory() : new Date();
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return new Date();
  return date;
}

export function poolForUser(user) {
  if (String(user.plan || '').includes('日卡')) return 'day';
  if (String(user.plan || '').includes('月卡')) return 'month';
  return 'default';
}

export function allowedPoolsForUser(user) {
  const pool = poolForUser(user);
  if (pool === 'day') return ['hour', 'day', 'unlimited', 'default'];
  if (pool === 'month') return ['hour', 'day', 'month', 'unlimited', 'default'];
  return ['unlimited', 'default'];
}

export function accountFromUser(data, user) {
  reconcileUserBalance(user);
  const now = currentDate();
  const today = now.toISOString().slice(0, 10);
  const month = now.toISOString().slice(0, 7);
  const routedEvents = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  const todayEvents = routedEvents.filter((item) => String(item.at || '').startsWith(today));
  const monthEvents = routedEvents.filter((item) => String(item.at || '').startsWith(month));
  const todayCost = todayEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  const monthCost = monthEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  const todayTokens = todayEvents.reduce((sum, item) => sum + Number(item.totalTokens || 0), 0);
  const totalTokens = routedEvents.reduce((sum, item) => sum + Number(item.totalTokens || 0), 0);
  const responseEvents = routedEvents.filter((item) => Number(item.latencyMs || 0) > 0);
  const averageLatency = responseEvents.length
    ? Math.round(responseEvents.reduce((sum, item) => sum + Number(item.latencyMs || 0), 0) / responseEvents.length)
    : 0;
  const successRate = routedEvents.length
    ? `${Math.round((routedEvents.filter((item) => item.status !== 'failed').length / routedEvents.length) * 1000) / 10}%`
    : '0%';
  return {
    plan: user.plan,
    renewalDate: user.renewalDate,
    balance: formatUsdFromCnyCents(user.balanceCents),
    balanceCny: formatCny(user.balanceCents),
    packageQuota: formatUsdFromCnyCents(user.packageQuotaCents),
    packageQuotaCny: formatCny(user.packageQuotaCents),
    boosterQuota: formatUsdFromCnyCents(user.boosterQuotaCents),
    boosterQuotaCny: formatCny(user.boosterQuotaCents),
    quotaLeft: formatUsdFromCnyCents(user.balanceCents),
    todayCost: formatUsdFromCnyCents(todayCost),
    monthCost: formatUsdFromCnyCents(monthCost),
    usageTotal: formatUsdFromCnyCents(monthCost),
    todayCalls: `${todayEvents.length} 次`,
    todayTokens: compactTokenText(todayTokens),
    totalTokens: compactTokenText(totalTokens),
    averageLatency: averageLatency ? `${averageLatency}ms` : '-',
    successRate,
  };
}

export function resolveQuotaCostCents(data, model, body, upstream, serverOptions) {
  const usage = parseUpstreamUsage(upstream.bodyText);
  const price = findModelPrice(data, model);
  if (price && usage.totalTokens > 0) {
    return priceUsageCents(price, usage.promptTokens, usage.completionTokens);
  }
  return estimateQuotaCostCents(data, model, body, serverOptions);
}

export function estimateQuotaCostCents(data, model, body, serverOptions) {
  const price = findModelPrice(data, model);
  if (!price) return Number(serverOptions.quotaCost || DEFAULT_QUOTA_COST_IMPORT);
  const promptTokens = estimatePromptTokens(body.messages ?? body.input ?? body.prompt);
  const completionTokens = Number(body.max_tokens || body.max_completion_tokens || body.max_output_tokens || 256);
  return Math.max(Number(serverOptions.quotaCost || DEFAULT_QUOTA_COST_IMPORT), priceUsageCents(price, promptTokens, completionTokens));
}

import { requireUserKey } from './auth.js';
import { publicError, parseUpstreamUsage, estimatePromptTokens, priceUsageCents, DEFAULT_QUOTA_COST as DEFAULT_QUOTA_COST_IMPORT } from './shared.js';

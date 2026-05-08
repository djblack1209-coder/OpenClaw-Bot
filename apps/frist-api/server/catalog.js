import {
  normalizeModelGroup, inferProviderGroup,
  normalizeOfficialModelName, normalizeOfficialModelList, modelMatchesGroup,
} from '../src/core.js';
import {
  DEFAULT_MODEL, DEFAULT_PUBLIC_MODEL, DEFAULT_RECHARGE_PLANS, DEFAULT_MODEL_PRICES, DEFAULT_MODEL_CATALOG,
  round2, formatCny, poolPriority, findModelPrice, priceLabel, uniqueStrings,
  sortModelsByStrength, strongestModel, sanitizeRiskNote, PRIMARY_SOURCE_TYPE,
  providerFromModel, taglineForModel, contextForModel,
  isSourceRouteApproved, isCredentialRouteApproved,
  effectiveCredentialGroup, estimateCredentialWaste,
} from './shared.js';

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
    .filter((plan) => plan.id && Number(plan.quotaUsd || 0) > 0 && Number(plan.priceCny || 0) > 0)
    .map((plan, index) => {
      const quotaUsd = Math.max(0, Number(plan.quotaUsd || 0));
      const priceCny = Math.max(0, Number(plan.priceCny ?? plan.amountCny ?? 0));
      const durationDays = Math.max(0, Number(plan.durationDays || 0));
      const inferredPlan = durationDays === 1 ? 'day' : 'balance';
      return {
        id: String(plan.id || `plan-${index + 1}`).trim(),
        label: String(plan.label || `Codex API ${quotaUsd}刀额度/${durationDays === 1 ? '日卡' : '不限时'}`).trim(),
        quotaUsd, priceCny: round2(priceCny), durationDays,
        plan: normalizeRechargePlan(plan.plan || inferredPlan),
        active: index === 0,
      };
    });
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

export function normalizeUserRecord(user) {
  const email = normalizeAlertEmailLocal(user?.email || '');
  return { ...user, balanceAlert: normalizeBalanceAlertRecordLocal(user?.balanceAlert, email) };
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

function normalizeRechargePlan(value) {
  const plan = String(value || 'balance').trim().toLowerCase();
  return ['balance', 'day', 'month'].includes(plan) ? plan : 'balance';
}

function normalizeAlertEmailLocal(value) {
  const email = String(value || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return '';
  return email.slice(0, 254);
}

function normalizeBalanceAlertRecordLocal(record, fallbackEmail = '') {
  const current = record && typeof record === 'object' ? record : {};
  const thresholdCents = normalizeMoneyCentsLocal(current.thresholdCents ?? Number(current.thresholdCny ?? 5) * 100);
  return {
    enabled: Object.prototype.hasOwnProperty.call(current, 'enabled') ? Boolean(current.enabled) : true,
    thresholdCents: Number.isFinite(thresholdCents) && thresholdCents > 0 && thresholdCents <= 1_000_000_00 ? thresholdCents : 500,
    email: normalizeAlertEmailLocal(current.email) || fallbackEmail || '',
    lastAlertAt: String(current.lastAlertAt || ''),
    lastAlertBalanceCents: Math.max(0, normalizeMoneyCentsLocal(current.lastAlertBalanceCents || 0)),
    lastTriggeredThresholdCents: Math.max(0, normalizeMoneyCentsLocal(current.lastTriggeredThresholdCents || 0)),
    updatedAt: String(current.updatedAt || ''),
  };
}

function normalizeMoneyCentsLocal(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return Number.NaN;
    const numeric = Number(trimmed.replace(/[^\d.-]/g, ''));
    return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
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
  const catalogModels = buildModelCatalog(data)
    .filter((item) => item.available !== false)
    .map((item) => item.model)
    .filter((model) => modelMatchesGroup(model, key.modelGroup || 'All'));
  const models = uniqueStrings([requestedModel, ...liveModels, ...catalogModels]);
  return sortModelsByStrength(models.length ? models : [DEFAULT_PUBLIC_MODEL]);
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
  const liveByModel = new Map(buildChannelChecks(data).map((item) => [normalizeOfficialModelName(item.model), item]));
  const rowsByModel = new Map(
    DEFAULT_MODEL_CATALOG.map((item) => {
      const model = normalizeOfficialModelName(item.model);
      const price = findModelPrice(data, model);
      return [model, { ...item, model, price: price ? priceLabel(price) : item.price || '官方价格待同步' }];
    }),
  );
  for (const model of uniqueStrings(data.credentials.flatMap((credential) => credential.models || []))) {
    const live = liveByModel.get(model);
    const price = findModelPrice(data, model);
    rowsByModel.set(model, {
      model, family: live?.provider || providerFromModel(model),
      tagline: taglineForModel(model), context: contextForModel(model),
      price: price ? priceLabel(price) : rowsByModel.get(model)?.price || '官方价格待同步',
      available: live ? Boolean(live.ok) : true,
    });
  }
  return [...rowsByModel.values()].sort((left, right) => {
    const liveDelta = Number(right.available) - Number(left.available);
    if (liveDelta !== 0) return liveDelta;
    return `${left.family}:${left.model}`.localeCompare(`${right.family}:${right.model}`);
  });
}

export function buildChannelChecks(data) {
  const grouped = new Map();
  for (const credential of data.credentials) {
    const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
    for (const model of models) {
      const key = model;
      const current = grouped.get(key) || {
        model, provider: providerFromModel(model), total: 0, healthy: 0, down: 0, slow: 0,
        latencyMs: 0, latencyTotal: 0, latencySamples: 0, checkedAt: '', status: credential.status, history: [],
      };
      const isHealthy = credential.enabled && credential.status === 'healthy' && isCredentialRouteApproved(credential);
      const latency = Number(credential.latencyMs || 0);
      const bucket = isHealthy ? (latency > 1600 ? 'slow' : 'ok') : 'down';
      current.total += 1;
      current.healthy += isHealthy ? 1 : 0;
      current.down += isHealthy ? 0 : 1;
      current.slow += bucket === 'slow' ? 1 : 0;
      if (isHealthy) {
        const safeLatency = latency || 999999;
        current.latencyMs = current.latencyMs ? Math.min(current.latencyMs, safeLatency) : safeLatency;
        current.latencyTotal += safeLatency;
        current.latencySamples += 1;
        current.status = 'healthy';
      } else if (!current.healthy) {
        current.status = credential.status || current.status || 'failed';
      }
      current.checkedAt = [current.checkedAt, credential.updatedAt].filter(Boolean).sort().at(-1) || '';
      current.history.push(bucket);
      grouped.set(key, current);
    }
  }
  return [...grouped.values()]
    .sort((left, right) => `${left.provider}:${left.model}`.localeCompare(`${right.provider}:${right.model}`))
    .map((item) => {
      const availabilityPercent = item.total ? Math.round((item.healthy / item.total) * 1000) / 10 : 0;
      const averageLatencyMs = item.latencySamples ? Math.round(item.latencyTotal / item.latencySamples) : 0;
      const monitorStatus = item.healthy === 0 ? '异常' : item.down > 0 || item.slow > 0 ? '降级' : '正常';
      return {
        model: normalizeOfficialModelName(item.model), provider: item.provider,
        channel: `${item.provider} 可用线路 ${item.healthy}/${item.total}`,
        endpoint: '/v1',
        ok: item.healthy > 0,
        status: item.healthy > 0 ? (item.slow > 0 ? 'slow' : 'healthy') : item.status,
        latencyMs: item.healthy > 0 ? item.latencyMs : 0,
        averageLatencyMs,
        checkedAt: item.checkedAt,
        availability: `${availabilityPercent}%`,
        availability7d: availabilityPercent,
        availability_7d: availabilityPercent,
        availabilityWindow: '当前库存快照',
        healthyCount: item.healthy,
        totalCount: item.total,
        downCount: item.down,
        slowCount: item.slow,
        successLabel: `${item.healthy}/${item.total} 可用`,
        latencyLabel: item.healthy > 0 ? `最低 ${item.latencyMs}ms / 平均 ${averageLatencyMs}ms` : '未检测到可用线路',
        monitorIntervalSeconds: 60,
        monitorStatus,
        officialStatus: monitorStatus,
        history: item.history.slice(-60),
      };
    });
}

export function buildModelUsage(data, user) {
  const events = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  const totals = new Map();
  for (const event of events) {
    totals.set(event.model, (totals.get(event.model) || 0) + Number(event.quotaCost || 0));
  }
  return [...totals.entries()].map(([model, cost]) => ({
    model, amount: formatCny(cost),
    calls: `${events.filter((event) => event.model === model).length} 次`,
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

export function reconcileUserBalance(user) {
  user.packageQuotaCents = Math.max(0, Number(user.packageQuotaCents || 0));
  user.boosterQuotaCents = Math.max(0, Number(user.boosterQuotaCents || 0));
  user.balanceCents = user.packageQuotaCents + user.boosterQuotaCents;
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
  if (remaining > 0) {
    user.boosterQuotaCents = Math.max(0, Number(user.boosterQuotaCents || 0) - remaining);
  }
  reconcileUserBalance(user);
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
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const month = now.toISOString().slice(0, 7);
  const routedEvents = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  const todayEvents = routedEvents.filter((item) => String(item.at || '').startsWith(today));
  const monthEvents = routedEvents.filter((item) => String(item.at || '').startsWith(month));
  const todayCost = todayEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  const monthCost = monthEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  return {
    plan: user.plan, renewalDate: user.renewalDate, balance: formatCny(user.balanceCents),
    packageQuota: formatCny(user.packageQuotaCents), boosterQuota: formatCny(user.boosterQuotaCents),
    quotaLeft: formatCny(user.balanceCents), todayCost: formatCny(todayCost),
    monthCost: formatCny(monthCost), usageTotal: formatCny(monthCost), todayCalls: `${todayEvents.length} 次`,
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

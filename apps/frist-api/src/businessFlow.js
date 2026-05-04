import {
  buildCcSwitchImportUrl,
  buildClientConfig,
  chooseNextCredential,
  normalizeBaseUrl,
  normalizeModelGroup,
  parseSupplierOrderText,
  parsePriceText,
  recommendConnectionPath,
} from './core.js';

const DAY_CARD_CODES = new Map([
  ['FRIST-DAY-001', { plan: '日卡', days: 1, packageCents: 800 }],
  ['FRIST-MONTH-001', { plan: '月卡 Pro', days: 30, packageCents: 8000 }],
  ['FRIST-BOOST-100', { plan: null, days: 0, boosterCents: 10000 }],
]);

const DEFAULT_PUBLIC_MODEL = 'gpt-5.5';
const DISPLAY_USD_TO_CNY = 7.2;
const PRIMARY_SOURCE_TYPE = 'authorized';
const BACKUP_SOURCE_TYPES = new Set(['cpa_json_backup', 'chong_backup', 'manual_backup']);

export function createBusinessStateFromDashboard(dashboard, options = {}) {
  const idFactory = options.idFactory || defaultIdFactory();
  const now = normalizeDate(options.now);
  const account = dashboard.accountSummary || {};
  const firstKey = dashboard.apiKeys?.[0];

  return {
    idFactory,
    now: now.toISOString(),
    customer: {
      email: options.email || account.email || '',
      emailVerified: true,
      verificationCode: '',
      isAdmin: Boolean(account.isAdmin),
      userInitials: account.userInitials || 'FA',
      plan: account.plan || '默认套餐',
      renewalDate: account.renewalDate || formatDate(addDays(now, 30)),
      balanceCents: centsFromMoney(account.balance),
      packageQuotaCents: centsFromMoney(account.packageQuota),
      boosterQuotaCents: centsFromMoney(account.boosterQuota),
    },
    counters: {
      todayCostCents: centsFromMoney(account.todayCost),
      monthCostCents: centsFromMoney(account.monthCost),
      todayCalls: integerFromText(account.todayCalls),
    },
    apiKeys: (dashboard.apiKeys || []).map((key, index) => {
      const secret = key.secret || '';
      return {
        id: String(key.id || `key-${index + 1}`),
        name: key.name || `API Key ${index + 1}`,
        secret,
        preview: key.preview || (secret ? maskKey(secret) : '未返回'),
        enabled: Boolean(key.enabled),
        costCents: centsFromMoney(key.cost),
        tokens: key.tokens || '0.00M',
        lastUsed: key.lastUsed || '-',
        expiresAt: key.expiresAt || '-',
        modelGroup: key.modelGroup || 'All',
      };
    }),
    modelUsage: clone(dashboard.modelUsage || []),
    channelChecks: clone(dashboard.channelChecks || []),
    rechargeOptions: clone(dashboard.rechargeOptions || []),
    supplierProfiles: [],
    credentials: [],
    priceDrafts: [],
    events: [],
  };
}

export function registerCustomer(state, { email, password }) {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(email || ''))) {
    throw new Error('邮箱格式不正确');
  }
  if (String(password || '').length < 6) {
    throw new Error('密码至少 6 位');
  }

  const verificationCode = String(Math.abs(hash(`${email}:${password}`))).slice(0, 6).padStart(6, '0');
  const next = cloneState(state);
  next.customer.email = String(email).trim();
  next.customer.emailVerified = false;
  next.customer.verificationCode = verificationCode;
  next.customer.userInitials = initialsFromEmail(email);
  next.apiKeys = [];
  next.events.push({ type: 'registered', email: next.customer.email });
  return { state: next, verificationCode };
}

export function verifyCustomerEmail(state, { code }) {
  const next = cloneState(state);
  if (String(code) !== next.customer.verificationCode) {
    throw new Error('验证码不正确');
  }
  next.customer.emailVerified = true;
  next.customer.verificationCode = '';
  next.events.push({ type: 'email_verified' });
  return next;
}

export function applyRecharge(state, { amountCny, method = 'manual' }) {
  const amountCents = Math.round(Number(amountCny) * 100);
  if (!Number.isFinite(amountCents) || amountCents <= 0) {
    throw new Error('充值金额必须大于 0');
  }

  const next = cloneState(state);
  next.customer.balanceCents += amountCents;
  next.customer.boosterQuotaCents += amountCents;
  next.events.push({ type: 'recharged', amountCents, method });
  return next;
}

export function redeemCode(state, { code }) {
  const normalized = String(code || '').trim().toUpperCase();
  const rule = DAY_CARD_CODES.get(normalized);
  if (!rule) {
    throw new Error('兑换码无效');
  }

  const next = cloneState(state);
  const now = new Date(next.now);
  if (rule.plan) {
    next.customer.plan = rule.plan;
    next.customer.renewalDate = formatDate(addDays(now, rule.days));
  }
  next.customer.packageQuotaCents += Number(rule.packageCents || 0);
  next.customer.balanceCents += Number(rule.packageCents || 0) + Number(rule.boosterCents || 0);
  next.customer.boosterQuotaCents += Number(rule.boosterCents || 0);
  next.events.push({ type: 'redeemed', code: normalized });
  return next;
}

export function createCustomerKey(state, { name, modelGroup }) {
  if (!state.customer.emailVerified) {
    throw new Error('请先完成邮箱验证');
  }

  const next = cloneState(state);
  const customerId = next.idFactory();
  const keyId = next.idFactory();
  const secret = `fk-live-${customerId}-${keyId}`;
  const key = {
    id: keyId,
    name: String(name || `API Key ${next.apiKeys.length + 1}`),
    secret,
    preview: maskKey(secret),
    enabled: true,
    costCents: 0,
    tokens: '0.00M',
    lastUsed: formatTime(new Date(next.now)),
    expiresAt: '-',
    modelGroup: normalizeModelGroup(modelGroup),
  };

  next.apiKeys.unshift(key);
  next.events.push({ type: 'key_created', id: key.id });
  return { state: next, key };
}

export function setCustomerKeyEnabled(state, { id, enabled }) {
  const next = cloneState(state);
  const key = next.apiKeys.find((item) => item.id === String(id));
  if (!key) {
    throw new Error('API Key 不存在');
  }
  key.enabled = Boolean(enabled);
  next.events.push({ type: key.enabled ? 'key_enabled' : 'key_disabled', id: key.id });
  return next;
}

export function renameCustomerKey(state, { id, name }) {
  const next = cloneState(state);
  const key = next.apiKeys.find((item) => item.id === String(id));
  if (!key) {
    throw new Error('API Key 不存在');
  }
  const cleanName = String(name || '').trim();
  if (!cleanName) {
    throw new Error('API Key 名称不能为空');
  }
  key.name = cleanName;
  next.events.push({ type: 'key_renamed', id: key.id });
  return next;
}

export function deleteCustomerKey(state, { id }) {
  const next = cloneState(state);
  const index = next.apiKeys.findIndex((item) => item.id === String(id));
  if (index === -1) {
    throw new Error('API Key 不存在');
  }
  const [deleted] = next.apiKeys.splice(index, 1);
  next.events.push({ type: 'key_deleted', id: deleted.id });
  return next;
}

export function buildBusinessImportUrl(state, { target, baseUrl, model = DEFAULT_PUBLIC_MODEL, defaultModel, availableModels = [] }) {
  const key = state.apiKeys.find((item) => item.enabled);
  if (!key) {
    throw new Error('没有可用的 API Key');
  }

  return buildCcSwitchImportUrl({
    target,
    apiKey: key.secret,
    baseUrl,
    model,
    defaultModel,
    availableModels,
    modelGroup: key.modelGroup,
  });
}

export function buildBusinessClientConfig(state, { target, baseUrl, model = DEFAULT_PUBLIC_MODEL, defaultModel, availableModels = [] }) {
  const key = state.apiKeys.find((item) => item.enabled);
  if (!key) {
    throw new Error('没有可用的 API Key');
  }

  return buildClientConfig({
    target,
    apiKey: key.secret,
    baseUrl,
    model,
    defaultModel,
    availableModels,
    modelGroup: key.modelGroup,
  });
}

export function deriveDashboardData(state, fallback) {
  return {
    ...clone(fallback),
    accountSummary: {
      userInitials: state.customer.userInitials,
      plan: state.customer.plan,
      balance: formatUsdFromCnyCents(state.customer.balanceCents),
      todayCost: formatUsdFromCnyCents(state.counters.todayCostCents),
      monthCost: formatUsdFromCnyCents(state.counters.monthCostCents),
      quotaLeft: formatUsdFromCnyCents(state.customer.balanceCents),
      packageQuota: formatUsdFromCnyCents(state.customer.packageQuotaCents),
      boosterQuota: formatUsdFromCnyCents(state.customer.boosterQuotaCents),
      usageTotal: formatUsdFromCnyCents(state.counters.monthCostCents),
      todayCalls: `${state.counters.todayCalls} 次`,
      renewalDate: state.customer.renewalDate,
    },
    apiKeys: state.apiKeys.map((key) => ({
      id: key.id,
      name: key.name,
      secret: key.secret,
      preview: key.preview,
      enabled: key.enabled,
      cost: formatUsdFromCnyCents(key.costCents),
      tokens: key.tokens,
      lastUsed: key.lastUsed,
      expiresAt: key.expiresAt,
      modelGroup: key.modelGroup || 'All',
    })),
    modelUsage: clone(state.modelUsage),
    channelChecks: clone(state.channelChecks),
    rechargeOptions: clone(state.rechargeOptions),
  };
}

export function createReplenishmentReport({
  baseUrl,
  keys,
  pool,
  priceText = '',
  modelProbe = {},
  keyProbes = {},
  connectionProbe = {},
  pricing = {},
  sourceType = PRIMARY_SOURCE_TYPE,
  riskStatus,
  backupRiskAccepted = false,
  riskNote = '',
}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  const models = modelProbe.supported === false ? fallbackModels(modelProbe.models) : clone(modelProbe.models || []);
  const connectionPath = recommendConnectionPath(connectionProbe);
  const normalizedSourceType = normalizeSourceType(sourceType);
  const normalizedRiskStatus = normalizeRiskStatus(
    riskStatus || (normalizedSourceType === PRIMARY_SOURCE_TYPE ? 'approved' : 'quarantined'),
  );
  const routeApproved = isSourceRouteApproved({
    sourceType: normalizedSourceType,
    riskStatus: normalizedRiskStatus,
    backupRiskAccepted,
  });
  const credentialStatus = routeApproved ? 'healthy' : normalizedRiskStatus === 'blocked' ? 'blocked' : 'quarantined';
  const cleanRiskNote = String(riskNote || '').replace(/\s+/g, ' ').trim().slice(0, 500);
  const keyResults = keys.map((key) => {
    const probe = keyProbes[key] || { ok: false, reason: '未检测' };
    return {
      keyPreview: maskKey(key),
      status: probe.ok ? 'healthy' : 'failed',
      reason: probe.ok ? '' : String(probe.reason || '检测失败'),
      quotaRemaining: Number(probe.quotaRemaining || 0),
      quotaTotal: Number(probe.quotaTotal || probe.quotaRemaining || 0),
      latencyMs: Number(probe.latencyMs || 0),
    };
  });

  return {
    baseUrl: normalizedBaseUrl,
    pool,
    connectionPath,
    sourceType: normalizedSourceType,
    riskStatus: normalizedRiskStatus,
    backupRiskAccepted: Boolean(backupRiskAccepted),
    riskNote: cleanRiskNote,
    models,
    keyResults,
    credentials: keyResults
      .filter((result) => result.status === 'healthy')
      .map((result) => ({
        keyPreview: result.keyPreview,
        pool,
        baseUrl: normalizedBaseUrl,
        models,
        sourceType: normalizedSourceType,
        riskStatus: normalizedRiskStatus,
        backupRiskAccepted: Boolean(backupRiskAccepted),
        riskNote: cleanRiskNote,
        enabled: routeApproved,
        status: credentialStatus,
        quotaRemaining: result.quotaRemaining,
        quotaTotal: result.quotaTotal || result.quotaRemaining,
        latencyMs: result.latencyMs,
      })),
    priceDrafts: parsePriceText(priceText, pricing),
  };
}

export function createReplenishmentReportFromOrderText({
  orderText,
  modelProbe = {},
  keyProbes = {},
  connectionProbe = {},
  pricing = {},
  sourceType = PRIMARY_SOURCE_TYPE,
  riskStatus,
  backupRiskAccepted = false,
  riskNote = '',
}) {
  const parsed = parseSupplierOrderText(orderText, pricing);
  const keyValues = parsed.keys.map((key) => key.value);
  const probes = {};
  for (const key of parsed.keys) {
    const provided = keyProbes[key.value] || { ok: true, latencyMs: key.latencyMs || 999 };
    probes[key.value] = {
      ...provided,
      quotaRemaining: Number(provided.quotaRemaining || key.quotaRemaining),
      quotaTotal: Number(provided.quotaTotal || key.quotaTotal),
    };
  }

  const report = createReplenishmentReport({
    baseUrl: parsed.baseUrl,
    keys: keyValues,
    pool: parsed.pool,
    priceText: '',
    modelProbe: {
      supported: modelProbe.supported ?? true,
      models: modelProbe.models?.length ? modelProbe.models : parsed.models,
    },
    keyProbes: probes,
    connectionProbe: Object.keys(connectionProbe).length
      ? connectionProbe
      : { direct: { ok: true, p95Ms: 999, failureRate: 0 } },
    pricing,
    sourceType,
    riskStatus,
    backupRiskAccepted,
    riskNote,
  });

  return {
    ...report,
    providerGroup: parsed.providerGroup,
    cardType: parsed.cardType,
    durationDays: parsed.durationDays,
    supplierFingerprint: parsed.supplierFingerprint,
    credentials: report.credentials.map((credential) => ({
      ...credential,
      modelGroup: parsed.providerGroup,
      cardType: parsed.cardType,
      expiresAt: parsed.expiresAt,
      quotaRemaining: parsed.keys.find((key) => maskKey(key.value) === credential.keyPreview)?.quotaRemaining ?? credential.quotaRemaining,
      quotaTotal: parsed.keys.find((key) => maskKey(key.value) === credential.keyPreview)?.quotaTotal ?? credential.quotaTotal,
    })),
  };
}

export function applyReplenishmentReport(state, report) {
  const next = cloneState(state);
  const sourceId = `source-${Math.abs(hash(report.baseUrl))}`;
  const existingSource = next.supplierProfiles.find((item) => item.id === sourceId);

  if (!existingSource) {
    next.supplierProfiles.push({
      id: sourceId,
      baseUrl: report.baseUrl,
      models: report.models,
      connectionPath: report.connectionPath,
      pool: report.pool,
      sourceType: report.sourceType || PRIMARY_SOURCE_TYPE,
      riskStatus: report.riskStatus || 'approved',
      backupRiskAccepted: Boolean(report.backupRiskAccepted),
      riskNote: report.riskNote || '',
    });
  }

  for (const credential of report.credentials) {
    next.credentials.push({
      id: next.idFactory(),
      sourceId,
      ...credential,
    });
  }

  next.priceDrafts.push(...report.priceDrafts);
  next.events.push({ type: 'replenishment_applied', sourceId, healthyKeys: report.credentials.length });
  return next;
}

export function routeModelRequest(state, { model, pool, quotaCost }) {
  const next = cloneState(state);
  const allowedPools = arguments[1].allowedPools?.length ? arguments[1].allowedPools : [pool];
  const candidates = next.credentials.filter(isSourceRouteApproved);
  for (const credential of candidates) {
    const compatible =
      allowedPools.includes(credential.pool) &&
      credential.enabled &&
      credential.status === 'healthy' &&
      isSourceRouteApproved(credential) &&
      credential.models.includes(model);
    if (compatible && Number(credential.quotaRemaining || 0) < quotaCost) {
      credential.status = 'exhausted';
      credential.enabled = false;
    }
  }

  let credential = chooseNextCredential(candidates, {
    allowedPools,
    model,
    quotaCost,
  });

  while (credential) {
    if (credential.quotaRemaining < quotaCost) {
      credential.status = 'exhausted';
      credential.enabled = false;
      credential = chooseNextCredential(candidates, { allowedPools, model, quotaCost });
      continue;
    }

    credential.quotaRemaining -= quotaCost;
    if (credential.quotaRemaining <= 0) {
      credential.status = 'exhausted';
      credential.enabled = false;
    }
    next.events.push({ type: 'model_routed', credentialId: credential.id, model, pool: credential.pool, quotaCost });
    return { state: next, credentialId: credential.id };
  }

  throw new Error('当前模型暂不可用');
}

function fallbackModels(models) {
  return models?.length ? clone(models) : ['claude-opus-4-6-thinking-c', 'gpt-5.5', 'gemini-2.5-pro'];
}

function normalizeSourceType(value) {
  const sourceType = String(value || '').trim().toLowerCase();
  if (sourceType === PRIMARY_SOURCE_TYPE || sourceType === 'official' || sourceType === 'primary') return PRIMARY_SOURCE_TYPE;
  if (sourceType === 'cpa' || sourceType === 'cpa_json' || sourceType === 'cpa_json_backup') return 'cpa_json_backup';
  if (sourceType === 'chong' || sourceType === 'chong_backup') return 'chong_backup';
  if (sourceType === 'manual_backup' || sourceType === 'other_backup' || sourceType === 'backup') return 'manual_backup';
  return PRIMARY_SOURCE_TYPE;
}

function normalizeRiskStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'approved' || status === 'pass' || status === 'allowed') return 'approved';
  if (status === 'blocked' || status === 'rejected' || status === 'disabled') return 'blocked';
  return 'quarantined';
}

function isSourceRouteApproved({ sourceType, riskStatus, backupRiskAccepted }) {
  const normalizedSourceType = normalizeSourceType(sourceType);
  const normalizedRiskStatus = normalizeRiskStatus(riskStatus || 'approved');
  if (normalizedRiskStatus !== 'approved') return false;
  if (normalizedSourceType === PRIMARY_SOURCE_TYPE) return true;
  return BACKUP_SOURCE_TYPES.has(normalizedSourceType) && Boolean(backupRiskAccepted);
}

function normalizeDate(value) {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function formatTime(date) {
  return date.toISOString().slice(11, 16);
}

function centsFromMoney(value) {
  const number = Number(String(value || '').replace(/[^\d.-]/g, ''));
  return Number.isFinite(number) ? Math.round(number * 100) : 0;
}

function integerFromText(value) {
  const number = Number(String(value || '').replace(/[^\d]/g, ''));
  return Number.isFinite(number) ? number : 0;
}

function formatCny(cents) {
  return `¥${(Number(cents || 0) / 100).toFixed(2)}`;
}

function formatUsdFromCnyCents(cents) {
  return `$${(Number(cents || 0) / 100 / DISPLAY_USD_TO_CNY).toFixed(2)}`;
}

function maskKey(value) {
  const key = String(value || '');
  if (!key) return 'fk-live-••••••';
  const prefix = /^fk-live-/i.test(key) ? 'fk-live' : key.slice(0, Math.min(6, key.length)).replace(/-$/, '');
  return `${prefix}-••••••${key.slice(-4)}`;
}

function initialsFromEmail(email) {
  const name = String(email).split('@')[0] || 'user';
  return name.slice(0, 2).toUpperCase();
}

function hash(value) {
  let result = 0;
  for (const char of String(value)) {
    result = (result << 5) - result + char.charCodeAt(0);
    result |= 0;
  }
  return result;
}

function defaultIdFactory() {
  let index = 0;
  return () => {
    index += 1;
    return `id-${index}`;
  };
}

function cloneState(state) {
  const next = clone(state);
  next.idFactory = state.idFactory;
  return next;
}

function clone(value) {
  return JSON.parse(
    JSON.stringify(value, (key, item) => {
      if (key === 'idFactory') return undefined;
      return item;
    }),
  );
}

import { createHash, randomBytes } from 'node:crypto';
import { dirname } from 'node:path';

export const DEFAULT_MODEL = 'claude-opus-4-6-thinking-c';
export const DEFAULT_PUBLIC_MODEL = 'gpt-5.5';
export const DEFAULT_USD_TO_CNY = 7.2;
export const DISPLAY_USD_TO_CNY = DEFAULT_USD_TO_CNY;
export const DEFAULT_PROBE_MODELS = [
  'claude-opus-4-6-thinking-c',
  'claude-opus-4-6-c',
  'claude-sonnet-4-5-c',
  'gpt-5.5',
  'gpt-5.4',
  'gpt-5.4-mini',
  'gpt-image-2',
  'gpt-5.3-codex',
  'deepseek-v4-flash',
  'deepseek-v4-pro',
  'gemini-2.5-flash',
];
export const DEFAULT_QUOTA_COST = 10;
export const PRIMARY_SOURCE_TYPE = 'authorized';
export const BACKUP_SOURCE_TYPES = new Set(['cpa_json_backup', 'chong_backup', 'manual_backup']);
export const DEFAULT_RECHARGE_PLANS = Object.freeze([
  Object.freeze({ id: 'codex-30-day', label: 'Codex API 30刀额度/日卡', quotaUsd: 30, priceCny: 5.88, durationDays: 1, plan: 'day' }),
  Object.freeze({ id: 'codex-30-unlimited', label: 'Codex API 30刀额度/不限时', quotaUsd: 30, priceCny: 8.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-100-unlimited', label: 'Codex API 100刀额度/不限时', quotaUsd: 100, priceCny: 28.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-500-unlimited', label: 'Codex API 500刀额度/不限时', quotaUsd: 500, priceCny: 68.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-1000-unlimited', label: 'Codex API 1000刀额度/不限时', quotaUsd: 1000, priceCny: 118.88, durationDays: 0, plan: 'balance' }),
]);
export const DEFAULT_MODEL_PRICES = Object.freeze([
  Object.freeze({ model: 'gpt-5.5', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '官方 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.5-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '官方 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.4', currency: 'CNY', inputCostCnyPerMillion: 18, outputCostCnyPerMillion: 108, inputSaleCnyPerMillion: 18, outputSaleCnyPerMillion: 108, source: 'official', displayPrice: '官方 输入 $2.50 / 缓存 $0.25 / 输出 $15.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.4-mini', currency: 'CNY', inputCostCnyPerMillion: 5.4, outputCostCnyPerMillion: 32.4, inputSaleCnyPerMillion: 5.4, outputSaleCnyPerMillion: 32.4, source: 'official', displayPrice: '官方 输入 $0.75 / 缓存 $0.075 / 输出 $4.50 每 1M' }),
  Object.freeze({ model: 'gpt-5.3-codex', currency: 'CNY', inputCostCnyPerMillion: 12.6, outputCostCnyPerMillion: 100.8, inputSaleCnyPerMillion: 12.6, outputSaleCnyPerMillion: 100.8, source: 'official', displayPrice: '官方 输入 $1.75 / 缓存 $0.175 / 输出 $14.00 每 1M' }),
  Object.freeze({ model: 'gpt-5-codex', currency: 'CNY', inputCostCnyPerMillion: 9, outputCostCnyPerMillion: 72, inputSaleCnyPerMillion: 9, outputSaleCnyPerMillion: 72, source: 'official', displayPrice: '官方 输入 $1.25 / 缓存 $0.125 / 输出 $10.00 每 1M' }),
  Object.freeze({ model: 'gpt-4o', currency: 'CNY', inputCostCnyPerMillion: 18, outputCostCnyPerMillion: 72, inputSaleCnyPerMillion: 18, outputSaleCnyPerMillion: 72, source: 'official', displayPrice: '官方 输入 $2.50 / 缓存 $1.25 / 输出 $10.00 每 1M' }),
  Object.freeze({ model: 'gpt-image-2', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '官方 文字入 $5 / 文字缓存 $1.25 / 图入 $8 / 图缓存 $2 / 图出 $30 每 1M' }),
  Object.freeze({ model: 'gpt-image-1.5', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 230.4, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 230.4, source: 'official', displayPrice: '官方 文字入 $5 / 文字缓存 $1.25 / 文字出 $10 / 图入 $8 / 图缓存 $2 / 图出 $32 每 1M' }),
  Object.freeze({ model: 'claude-opus-4-6-thinking-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 180, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 180, source: 'official', displayPrice: '官方 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M' }),
  Object.freeze({ model: 'claude-opus-4-6-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 180, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 180, source: 'official', displayPrice: '官方 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M' }),
  Object.freeze({ model: 'claude-sonnet-4-5-c', currency: 'CNY', inputCostCnyPerMillion: 21.6, outputCostCnyPerMillion: 108, inputSaleCnyPerMillion: 21.6, outputSaleCnyPerMillion: 108, source: 'official', displayPrice: '官方 输入 $3.00 / 缓存写 $3.75 / 缓存读 $0.30 / 输出 $15.00 每 1M' }),
  Object.freeze({ model: 'gemini-2.5-flash', currency: 'CNY', inputCostCnyPerMillion: 2.16, outputCostCnyPerMillion: 18, inputSaleCnyPerMillion: 2.16, outputSaleCnyPerMillion: 18, source: 'official', displayPrice: '官方 ≤200K 输入 $0.30 / 缓存 $0.03 / 输出 $2.50 每 1M' }),
  Object.freeze({ model: 'deepseek-v4-flash', currency: 'CNY', inputCostCnyPerMillion: 1.01, outputCostCnyPerMillion: 2.02, inputSaleCnyPerMillion: 1.01, outputSaleCnyPerMillion: 2.02, source: 'official', displayPrice: '官方 缓存命中 $0.014 / 输入 $0.14 / 输出 $0.28 每 1M' }),
  Object.freeze({ model: 'deepseek-v4-pro', currency: 'CNY', inputCostCnyPerMillion: 3.13, outputCostCnyPerMillion: 6.26, inputSaleCnyPerMillion: 3.13, outputSaleCnyPerMillion: 6.26, source: 'official', displayPrice: '官方 缓存命中 $0.035 / 输入 $0.435 / 输出 $0.87 每 1M' }),
]);
export const DEFAULT_MODEL_CATALOG = [
  { model: 'gpt-5.5', family: 'OpenAI', tagline: '推理和代码主力', context: '1M 上下文', price: '官方 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M', available: true },
  { model: 'gpt-5.4', family: 'OpenAI', tagline: '日常问答和代码补全', context: '1M 上下文', price: '官方 输入 $2.50 / 缓存 $0.25 / 输出 $15.00 每 1M', available: true },
  { model: 'gpt-5.4-mini', family: 'OpenAI', tagline: '轻量代码和快速问答', context: '400K 上下文', price: '官方 输入 $0.75 / 缓存 $0.075 / 输出 $4.50 每 1M', available: true },
  { model: 'gpt-image-2', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '官方 文字入 $5 / 文字缓存 $1.25 / 图入 $8 / 图缓存 $2 / 图出 $30 每 1M', available: true },
  { model: 'gpt-image-1.5', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '官方 文字入 $5 / 文字缓存 $1.25 / 文字出 $10 / 图入 $8 / 图缓存 $2 / 图出 $32 每 1M', available: true },
  { model: 'gpt-5.3-codex', family: 'OpenAI', tagline: 'Codex 专用代码模型', context: '400K 上下文', price: '官方 输入 $1.75 / 缓存 $0.175 / 输出 $14.00 每 1M', available: true },
  { model: 'gpt-5-codex', family: 'OpenAI', tagline: 'Codex 代码模型', context: '400K 上下文', price: '官方 输入 $1.25 / 缓存 $0.125 / 输出 $10.00 每 1M', available: true },
  { model: 'gpt-4o', family: 'OpenAI', tagline: '通用多模态', context: '128K 上下文', price: '官方 输入 $2.50 / 缓存 $1.25 / 输出 $10.00 每 1M', available: true },
  { model: 'deepseek-v4-flash', family: 'DeepSeek', tagline: 'Codex 桌面版官方兼容网关', context: 'OpenAI v1 兼容', price: '官方 缓存命中 $0.014 / 输入 $0.14 / 输出 $0.28 每 1M', available: true },
  { model: 'deepseek-v4-pro', family: 'DeepSeek', tagline: '推理模型别名', context: 'OpenAI v1 兼容', price: '官方 缓存命中 $0.035 / 输入 $0.435 / 输出 $0.87 每 1M', available: true },
  { model: 'gemini-2.5-flash', family: 'Gemini', tagline: '多模态和轻量任务', context: '1M 上下文', price: '官方 ≤200K 输入 $0.30 / 缓存 $0.03 / 输出 $2.50 每 1M', available: true },
  { model: DEFAULT_MODEL, family: 'Claude', tagline: '复杂开发和长链路推理', context: '长上下文', price: '官方 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M', available: true },
];
export const SESSION_COOKIE = 'frist_session';
export const DAY_CARD_CODES = new Map([
  ['FRIST-DAY-001', { plan: '日卡', days: 1, packageCents: 800 }],
  ['FRIST-MONTH-001', { plan: '月卡 Pro', days: 30, packageCents: 8000 }],
  ['FRIST-BOOST-100', { plan: null, days: 0, boosterCents: 10000 }],
]);
export const CONTENT_TYPES = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml; charset=utf-8'],
]);
export const ROOT_GATEWAY_PATHS = new Set([
  '/chat/completions',
  '/openai/chat/completions',
  '/responses',
  '/openai/responses',
  '/images/generations',
  '/openai/images/generations',
  '/messages',
]);

export function createId(prefix) {
  return `${prefix}-${randomBytes(12).toString('base64url')}`;
}

export function hashId(value) {
  return createHash('sha1').update(String(value)).digest('hex').slice(0, 12);
}

export function hashAdminClaimCode(value) {
  return createHash('sha256').update(String(value || '').trim()).digest('hex');
}

export function parseAdminClaimCodes(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value || '')
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function generateVerificationCode() {
  return String(randomBytes(4).readUInt32BE(0) % 1000000).padStart(6, '0');
}

export function maskKey(value) {
  const key = String(value || '');
  if (!key) return 'sk-******';
  const prefix = /^sk-/i.test(key)
    ? 'sk'
    : /^fk-live-/i.test(key)
      ? 'fk-live'
      : key.slice(0, Math.min(6, key.length)).replace(/-$/, '');
  return `${prefix}-••••••${key.slice(-4)}`;
}

export function initialsFromEmail(email) {
  const name = String(email || 'fa').split('@')[0];
  return name.slice(0, 2).toUpperCase();
}

export function addDays(date, days) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + Number(days || 0));
  return next;
}

export function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

export function formatCny(cents) {
  return `¥${(Number(cents || 0) / 100).toFixed(2)}`;
}

export function formatUsdFromCnyCents(cents, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return `$${(Number(cents || 0) / 100 / safeRate).toFixed(2)}`;
}

export function formatUsdPriceFromCny(value, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return `$${(Number(value || 0) / safeRate).toFixed(3)}`;
}

export function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

export function formatEmailTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || '-');
  }
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Shanghai',
  }).format(date);
}

export function parseCookies(header) {
  return String(header || '')
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce((cookies, part) => {
      const index = part.indexOf('=');
      if (index === -1) return cookies;
      cookies[part.slice(0, index)] = decodeURIComponent(part.slice(index + 1));
      return cookies;
    }, {});
}

export function requestOrigin(request) {
  const protocol = request.headers['x-forwarded-proto'] || 'http';
  const host = request.headers['x-forwarded-host'] || request.headers.host || '127.0.0.1';
  return `${protocol}://${host}`;
}

export function headerValue(request, name) {
  const value = request.headers[name.toLowerCase()];
  if (Array.isArray(value)) {
    return value[0] || '';
  }
  return value || '';
}

export function clientIp(request) {
  const forwarded = headerValue(request, 'x-forwarded-for').split(',')[0]?.trim();
  return forwarded || request.socket?.remoteAddress || 'unknown';
}

export function publicError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.expose = true;
  return error;
}

export function compareGatewayCredentials(left, right) {
  const poolDelta = poolPriority(left.pool) - poolPriority(right.pool);
  if (poolDelta !== 0) return poolDelta;
  const expiryDelta = expiryMs(left.expiresAt) - expiryMs(right.expiresAt);
  if (expiryDelta !== 0) return expiryDelta;
  return Number(left.latencyMs || 999999) - Number(right.latencyMs || 999999);
}

export function credentialMatchesModelGroup(credential, model, keyGroup) {
  const normalizedKeyGroup = normalizeModelGroup(keyGroup || 'All');
  if (normalizedKeyGroup === 'All') return true;
  const credentialGroup = normalizeModelGroup(credential.modelGroup || 'All');
  if (credentialGroup !== 'All' && credentialGroup !== normalizedKeyGroup) {
    return false;
  }
  if (model) {
    return modelMatchesGroup(model, normalizedKeyGroup);
  }
  return (credential.models || []).some((item) => modelMatchesGroup(item, normalizedKeyGroup));
}

export function expiryMs(value) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.MAX_SAFE_INTEGER;
}

export function poolPriority(pool) {
  const order = new Map([
    ['hour', 0],
    ['day', 1],
    ['month', 2],
    ['unlimited', 3],
    ['default', 4],
  ]);
  return order.get(String(pool || 'default')) ?? 9;
}

export function compactObject(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ''),
  );
}

export function parseJsonPayload(bodyText) {
  try {
    return JSON.parse(bodyText || '{}');
  } catch {
    return {};
  }
}

export function chatMessageContentToText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === 'string' ? part : part?.text || JSON.stringify(part || {})))
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

export function inputText(item) {
  if (typeof item === 'string') return item;
  if (typeof item?.content === 'string') return item.content;
  return JSON.stringify(item?.content || item || '');
}

export function normalizePool(value) {
  const pool = String(value || '').trim().toLowerCase();
  if (['hour', 'day', 'month', 'unlimited', 'default'].includes(pool)) return pool;
  if (/小时|hour/.test(pool)) return 'hour';
  if (/日|天|day/.test(pool)) return 'day';
  if (/月|month/.test(pool)) return 'month';
  if (/不限|永久|unlimited/.test(pool)) return 'unlimited';
  return '';
}

export function normalizeSourceType(value) {
  const sourceType = String(value || '').trim().toLowerCase();
  if (sourceType === PRIMARY_SOURCE_TYPE || sourceType === 'official' || sourceType === 'primary') return PRIMARY_SOURCE_TYPE;
  if (sourceType === 'cpa' || sourceType === 'cpa_json' || sourceType === 'cpa_json_backup') return 'cpa_json_backup';
  if (sourceType === 'chong' || sourceType === 'chong_backup') return 'chong_backup';
  if (sourceType === 'manual_backup' || sourceType === 'other_backup' || sourceType === 'backup') return 'manual_backup';
  return PRIMARY_SOURCE_TYPE;
}

export function normalizeRiskStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'approved' || status === 'pass' || status === 'allowed') return 'approved';
  if (status === 'blocked' || status === 'rejected' || status === 'disabled') return 'blocked';
  return 'quarantined';
}

export function sanitizeRiskNote(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500);
}

export function isSourceRouteApproved({ sourceType, riskStatus, backupRiskAccepted }) {
  const normalizedSourceType = normalizeSourceType(sourceType);
  const normalizedRiskStatus = normalizeRiskStatus(riskStatus);
  if (normalizedRiskStatus !== 'approved') {
    return false;
  }
  if (normalizedSourceType === PRIMARY_SOURCE_TYPE) {
    return true;
  }
  return BACKUP_SOURCE_TYPES.has(normalizedSourceType) && Boolean(backupRiskAccepted);
}

export function isCredentialRouteApproved(credential) {
  return isSourceRouteApproved({
    sourceType: credential.sourceType || PRIMARY_SOURCE_TYPE,
    riskStatus: credential.riskStatus || 'approved',
    backupRiskAccepted: credential.backupRiskAccepted,
  });
}

export function sortModelsByStrength(models = []) {
  const order = [
    'gpt-5.5-pro', 'gpt-5.5-c', 'gpt-5.5',
    'gpt-5.4-pro', 'gpt-5.4-c', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano',
    'gpt-image-2', 'gpt-image-1.5', 'gpt-image-1',
    'gpt-5.3-codex',
    'deepseek-v4-flash', 'deepseek-v4-pro',
    'deepseek-chat', 'deepseek-reasoner',
    'claude-opus-4-6-thinking-c', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c',
    'gemini-2.5-flash',
  ];
  return normalizeOfficialModelList(models).sort((left, right) => {
    const leftRank = order.indexOf(left);
    const rightRank = order.indexOf(right);
    const normalizedLeft = leftRank === -1 ? Number.MAX_SAFE_INTEGER : leftRank;
    const normalizedRight = rightRank === -1 ? Number.MAX_SAFE_INTEGER : rightRank;
    if (normalizedLeft !== normalizedRight) return normalizedLeft - normalizedRight;
    return left.localeCompare(right);
  });
}

export function uniqueStrings(values) {
  return [...new Set(values.map((value) => normalizeOfficialModelName(value)).filter(Boolean))];
}

export function findModelPrice(data, model) {
  const normalizedModel = normalizeOfficialModelName(model);
  return [...(data.priceDrafts || [])]
    .reverse()
    .find((draft) => normalizeOfficialModelName(draft.model) === normalizedModel || draft.model === '*');
}

export function parseUpstreamUsage(bodyText) {
  try {
    const payload = JSON.parse(bodyText || '{}');
    const usage = payload.usage || {};
    const promptTokens = Number(usage.prompt_tokens || usage.input_tokens || 0);
    const completionTokens = Number(usage.completion_tokens || usage.output_tokens || 0);
    return {
      promptTokens: Number.isFinite(promptTokens) ? promptTokens : 0,
      completionTokens: Number.isFinite(completionTokens) ? completionTokens : 0,
      totalTokens: Number(usage.total_tokens || 0) || promptTokens + completionTokens,
    };
  } catch {
    return { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
  }
}

export function estimatePromptTokens(input) {
  if (!Array.isArray(input)) {
    return Math.max(1, Math.ceil(String(input || '').length / 4));
  }
  const text = input.map(inputText).join('\n');
  return Math.max(1, Math.ceil(text.length / 4));
}

export function priceUsageCents(price, promptTokens, completionTokens) {
  const inputCny = (Number(promptTokens || 0) / 1_000_000) * Number(price.inputSaleCnyPerMillion || 0);
  const outputCny = (Number(completionTokens || 0) / 1_000_000) * Number(price.outputSaleCnyPerMillion || 0);
  return Math.max(1, Math.ceil((inputCny + outputCny) * 100));
}

export function sanitizeUserKey(key, options = {}) {
  return {
    id: key.id,
    name: key.name,
    preview: key.preview || maskKey(key.secret),
    ...(options.revealSecret ? { secret: key.secret } : {}),
    enabled: Boolean(key.enabled),
    modelGroup: key.modelGroup || 'All',
    cost: formatUsdFromCnyCents(key.costCents),
    costCny: formatCny(key.costCents),
    tokens: key.tokens || '0.00M',
    lastUsed: key.lastUsed || '-',
    expiresAt: key.expiresAt || '-',
  };
}

export function sanitizeUser(user) {
  return {
    id: user.id,
    email: user.email,
    emailVerified: Boolean(user.emailVerified),
    isAdmin: Boolean(user.isAdmin),
    plan: user.plan,
    renewalDate: user.renewalDate,
    userInitials: initialsFromEmail(user.email),
  };
}

export function sanitizeCredential(credential) {
  return {
    id: credential.id,
    sourceId: credential.sourceId,
    keyPreview: credential.keyPreview || maskKey(credential.rawKey),
    pool: credential.pool,
    modelGroup: credential.modelGroup || 'All',
    cardType: credential.cardType || credential.pool,
    sourceType: credential.sourceType || PRIMARY_SOURCE_TYPE,
    riskStatus: credential.riskStatus || 'approved',
    backupRiskAccepted: Boolean(credential.backupRiskAccepted),
    riskNote: credential.riskNote || '',
    baseUrl: credential.baseUrl,
    connectionPath: credential.connectionPath || 'direct',
    models: credential.models,
    status: credential.status,
    enabled: Boolean(credential.enabled),
    quotaRemaining: credential.quotaRemaining,
    quotaTotal: credential.quotaTotal || credential.quotaRemaining,
    expiresAt: credential.expiresAt || '',
    wasteEstimate: estimateCredentialWaste(credential),
    latencyMs: credential.latencyMs,
    lastProbeStatus: credential.lastProbeStatus || '',
    lastProbeReason: credential.lastProbeReason || '',
    updatedAt: credential.updatedAt,
  };
}

export function sanitizePaymentOrder(order) {
  return {
    id: order.id,
    email: order.email || '',
    amount: formatCny(order.amountCents),
    amountCents: Number(order.amountCents || 0),
    credit: formatUsdFromCnyCents(order.creditCents),
    creditCny: formatCny(order.creditCents),
    creditCents: Number(order.creditCents || order.amountCents || 0),
    quotaUsd: Number(order.quotaUsd || 0),
    planId: order.planId || '',
    plan: order.plan || 'balance',
    method: order.method,
    status: order.status,
    createdAt: order.createdAt,
    updatedAt: order.updatedAt,
  };
}

export function sanitizeParsedOrder(parsed) {
  return {
    baseUrl: parsed.baseUrl,
    supplierDomain: parsed.supplierDomain,
    supplierFingerprint: parsed.supplierFingerprint,
    pool: parsed.pool,
    cardType: parsed.cardType,
    durationDays: parsed.durationDays,
    quantity: parsed.quantity,
    quotaUsd: parsed.quotaUsd,
    amountCny: parsed.amountCny,
    providerGroup: parsed.providerGroup,
    models: parsed.models,
    interfaceFormat: parsed.interfaceFormat,
    authHeaderName: parsed.authHeaderName,
    keyPreviews: parsed.keys.map((key) => maskKey(key.value)),
    quotaTotal: parsed.keys.reduce((sum, key) => sum + Number(key.quotaTotal || 0), 0),
    expiresAt: parsed.expiresAt,
    inventorySummary: [{
      pool: parsed.pool,
      providerGroup: parsed.providerGroup,
      totalCount: parsed.keys.length,
      healthyCount: parsed.keys.length,
      quotaRemaining: parsed.keys.reduce((sum, key) => sum + Number(key.quotaRemaining || 0), 0),
      quotaTotal: parsed.keys.reduce((sum, key) => sum + Number(key.quotaTotal || 0), 0),
      wasteText: parsed.expiresAt ? '待写入后计算' : '无到期浪费',
    }],
  };
}

export function sanitizeAdminEvents(events) {
  return [...events]
    .slice(-50)
    .reverse()
    .map((event) => ({
      type: event.type,
      at: event.at || '',
      detail: adminEventDetail(event),
    }));
}

export function adminEventDetail(event) {
  if (event.type === 'replenished') {
    return `${event.pool || 'default'} 池写入 ${event.credentialCount || 0} 枚，失败 ${event.failedCount || 0} 枚`;
  }
  if (event.type === 'credential_exhausted') {
    return `上游 Key 已摘除: ${event.reason || '额度或连通性异常'}`;
  }
  if (event.type === 'credential_failed') {
    return `上游 Key 已切出: ${event.reason || '连通性异常'}`;
  }
  if (event.type === 'gateway_routed') {
    return `${event.model || 'unknown'} 已路由，计费 ${formatUsdFromCnyCents(event.quotaCost)}`;
  }
  if (event.type === 'registered') return '新用户注册';
  if (event.type === 'logged_in') return '用户登录';
  if (event.type === 'redeemed') return `兑换码 ${event.code || ''} 已生效`;
  if (event.type === 'plan_expired') return `${event.plan || '套餐'} 已到期，套餐额度已清零`;
  if (event.type === 'payment_order_created') return `用户发起充值 ${formatCny(event.amountCents)}`;
  if (event.type === 'manual_recharged') return `人工入账 ${formatCny(event.amountCents)}`;
  return '系统事件';
}

export function sanitizeExtraHeaders(headers) {
  if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
    return {};
  }
  const result = {};
  for (const [rawName, rawValue] of Object.entries(headers)) {
    const name = String(rawName || '').trim().toLowerCase();
    const value = String(rawValue || '').trim();
    if (!name || !value || name === 'authorization' || name === 'x-api-key' || /[\r\n]/.test(`${name}${value}`)) {
      continue;
    }
    if (/(?:sk-|sk_|cr_)[A-Za-z0-9_-]{12,}/.test(value)) {
      continue;
    }
    result[name] = value;
  }
  return result;
}

export function authHeadersForKey(rawKey, authConfig = {}) {
  const headerName = String(authConfig.authHeaderName || 'authorization').trim().toLowerCase() || 'authorization';
  const valuePrefix =
    authConfig.authHeaderValuePrefix === ''
      ? ''
      : String(authConfig.authHeaderValuePrefix || 'Bearer').trim();
  return {
    ...sanitizeExtraHeaders(authConfig.extraHeaders),
    [headerName]: valuePrefix ? `${valuePrefix} ${rawKey}` : String(rawKey || ''),
  };
}

export function normalizeModels(models, options = {}) {
  if (typeof models === 'string') {
    const parsed = models
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    return parsed.length > 0 || options.allowEmpty ? normalizeOfficialModelList(parsed) : [DEFAULT_MODEL];
  }
  if (Array.isArray(models) && models.length > 0) {
    return normalizeOfficialModelList(models.map((item) => String(item).trim()).filter(Boolean));
  }
  if (options.allowEmpty) {
    return [];
  }
  return [DEFAULT_MODEL];
}

export function pipeReadableStreamToResponse(bodyStream, response) {
  if (typeof bodyStream.getReader === 'function') {
    const reader = bodyStream.getReader();
    try {
      const pump = async () => {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          response.write(normalizeStreamChunk(chunk.value));
        }
      };
      return pump().then(() => {
        reader.releaseLock?.();
        response.end();
      });
    } catch {
      reader.releaseLock?.();
      response.end();
    }
    return Promise.resolve();
  }

  if (typeof bodyStream[Symbol.asyncIterator] === 'function') {
    const pump = async () => {
      for await (const chunk of bodyStream) {
        response.write(normalizeStreamChunk(chunk));
      }
      response.end();
    };
    return pump();
  }

  response.end();
  return Promise.resolve();
}

export function normalizeStreamChunk(chunk) {
  if (Buffer.isBuffer(chunk)) return chunk;
  if (chunk instanceof Uint8Array) return Buffer.from(chunk);
  return Buffer.from(String(chunk || ''), 'utf8');
}

export async function readJsonBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 1024 * 1024) {
      throw publicError(413, '请求体过大');
    }
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw publicError(400, 'JSON 格式不正确');
  }
}

export function writeJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-csrf-token, x-frist-session-id, x-conversation-id',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

export function writeNoContent(response) {
  response.writeHead(204, {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-csrf-token, x-frist-session-id, x-conversation-id',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  });
  response.end();
}

export function isImageGenerationModel(model) {
  return /image|dall/i.test(String(model || ''));
}

export function parseModelIds(bodyText) {
  try {
    const payload = JSON.parse(bodyText || '{}');
    if (!Array.isArray(payload.data)) return [];
    return normalizeOfficialModelList(
      payload.data.map((item) => String(item.id || item.name || '').trim()).filter(Boolean),
    );
  } catch {
    return [];
  }
}

export function providerFromModel(model = '') {
  const value = String(model || '').toLowerCase();
  if (value.includes('gpt') || value.includes('openai')) return 'OpenAI';
  if (value.includes('deepseek')) return 'DeepSeek';
  if (value.includes('gemini')) return 'Gemini';
  return 'Claude';
}

export function taglineForModel(model = '') {
  if (/image|dall/i.test(model)) return '图片生成';
  if (/gpt/i.test(model)) return '推理和代码';
  if (/claude/i.test(model)) return '长文和工具调用';
  if (/gemini/i.test(model)) return '多模态和轻量任务';
  return '通用模型';
}

export function contextForModel(model = '') {
  if (/image|dall/i.test(model)) return '按图计费';
  if (/gpt-5|claude/i.test(model)) return '长上下文';
  return '按模型能力';
}

export function priceLabel(price) {
  if (price.displayPrice) {
    return price.displayPrice;
  }
  const input = Number(price.inputSaleCnyPerMillion || 0);
  const output = Number(price.outputSaleCnyPerMillion || 0);
  if (input <= 0 && output <= 0) {
    return '官方价格待同步';
  }
  return `${formatUsdPriceFromCny(input)}/${formatUsdPriceFromCny(output)} 每 1M`;
}

export function effectiveCredentialGroup(credential) {
  const explicit = normalizeModelGroup(credential.modelGroup || '');
  if (explicit !== 'All') {
    return explicit;
  }
  return inferProviderGroup((credential.models || []).join('\n'));
}

export function estimateCredentialWaste(credential) {
  const quotaRemaining = Number(credential.quotaRemaining || 0);
  if (!credential.expiresAt || quotaRemaining <= 0) {
    return { quotaRemaining: 0, reason: '' };
  }
  const expiresAt = Date.parse(credential.expiresAt);
  if (!Number.isFinite(expiresAt)) {
    return { quotaRemaining: 0, reason: '' };
  }
  const hoursLeft = (expiresAt - Date.now()) / 3_600_000;
  if (hoursLeft <= 0) {
    return { quotaRemaining, reason: '已过期未用完' };
  }
  if (hoursLeft <= 24) {
    return { quotaRemaining, reason: '24小时内到期' };
  }
  return { quotaRemaining: 0, reason: '' };
}

export function strongestModel(models = []) {
  return sortModelsByStrength(models)[0] || DEFAULT_PUBLIC_MODEL;
}

export function isModelUnsupportedResponse(status, bodyText) {
  return (status === 400 || status === 404) && /model|not found|unsupported|not supported|不存在|不支持/i.test(bodyText || '');
}

export function isOpenAiChatCompletionPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return Array.isArray(payload.choices);
}

export function isOpenAiResponsesPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return payload.object === 'response' || Array.isArray(payload.output) || typeof payload.output_text === 'string';
}

export function isOpenAiImageGenerationPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return Array.isArray(payload.data);
}

export function shouldTryResponsesProbe(status, bodyText) {
  return status === 404 || status === 405 || isModelUnsupportedResponse(status, bodyText);
}

export function isQuotaExhaustedResponse(upstream) {
  if (upstream.status >= 200 && upstream.status < 300) {
    return false;
  }
  if (upstream.status === 402 || upstream.status === 429) {
    return true;
  }
  return /insufficient|quota|balance|余额|额度/i.test(upstream.bodyText || '');
}

export function exhaustCredential(data, credential, reason) {
  credential.status = 'exhausted';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  data.events.push({
    type: 'credential_exhausted',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

export function failCredential(data, credential, reason) {
  credential.status = 'failed';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  data.events.push({
    type: 'credential_failed',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

export function gatewayUnavailableResponse() {
  return {
    status: 503,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({ error: '当前模型暂不可用' }),
  };
}

export function shouldFailoverUpstream(upstream) {
  return upstream.status === 408 || upstream.status >= 500 || isCredentialRejectedResponse(upstream) || isGatewayAdapterUnsupported(upstream);
}

export function isGatewayAdapterUnsupported(upstream) {
  if (!upstream || ![400, 404, 405, 415].includes(upstream.status)) {
    return false;
  }
  return /not found|unsupported|not supported|unknown endpoint|cannot\s+post|不存在|不支持/i.test(upstream.bodyText || '');
}

export function isCredentialRejectedResponse(upstream) {
  if (!upstream || ![401, 403].includes(upstream.status)) {
    return false;
  }
  return /invalid api key|missing api key|unauthorized|forbidden|token|api key|认证|鉴权|密钥/i.test(upstream.bodyText || '');
}

import {
  normalizeModelGroup,
  inferProviderGroup,
  normalizeOfficialModelName,
  normalizeOfficialModelList,
  modelMatchesGroup,
} from '../src/core.js';

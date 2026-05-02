import { normalizeBaseUrl } from './core.js';

const DEFAULT_QUOTA_PER_CNY = 100;
const DEFAULT_HISTORY_SIZE = 12;
const USER_ENDPOINTS = {
  status: '/api/status',
  self: '/api/user/self',
  tokens: '/api/token/',
  usage: '/api/log/self',
  channelHealth: '/api/frist/channel-health',
};

export function createNewApiClient({ baseUrl = window.location.origin, fetchImpl = window.fetch } = {}) {
  const root = normalizeBaseUrl(baseUrl);

  async function getJson(path) {
    const response = await fetchImpl(`${root}${path}`, {
      credentials: 'include',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`New-API 请求失败: ${response.status}`);
    }

    return response.json();
  }

  return {
    getStatus: () => getJson(USER_ENDPOINTS.status),
    getUserSelf: () => getJson(USER_ENDPOINTS.self),
    getTokens: () => getJson(USER_ENDPOINTS.tokens),
    getUsage: () => getJson(USER_ENDPOINTS.usage),
    getChannelHealth: () => getJson(USER_ENDPOINTS.channelHealth),
  };
}

export function normalizeNewApiUserSummary(raw, options = {}) {
  const user = unwrapObject(raw);
  const plan = readPlanName(user, options.planNames);
  const quota = numberFromAny(user.quota ?? user.remain_quota ?? user.remaining_quota);
  const usedQuota = numberFromAny(user.used_quota ?? user.usedQuota ?? user.month_quota ?? user.monthly_quota);
  const todayQuota = numberFromAny(user.today_quota ?? user.today_used_quota ?? user.daily_quota);
  const calls = numberFromAny(user.request_count ?? user.today_calls ?? user.calls);
  const quotaPerCny = quotaUnit(options);

  return {
    userInitials: initialsFrom(user.display_name || user.name || user.username || user.email),
    plan,
    balance: formatMoney(quota, quotaPerCny),
    todayCost: formatMoney(todayQuota, quotaPerCny),
    monthCost: formatMoney(usedQuota, quotaPerCny),
    quotaLeft: formatMoney(quota, quotaPerCny),
    packageQuota: formatMoney(quota, quotaPerCny),
    boosterQuota: formatMoney(0, quotaPerCny),
    usageTotal: formatMoney(usedQuota, quotaPerCny),
    todayCalls: `${calls} 次`,
    renewalDate: formatDate(user.subscription_expires_at ?? user.expired_time ?? user.renewal_time),
  };
}

export function normalizeNewApiTokens(raw, options = {}) {
  const quotaPerCny = quotaUnit(options);
  return unwrapArray(raw).map((token, index) => {
    const usedQuota = numberFromAny(token.used_quota ?? token.usedQuota);
    const remainQuota = numberFromAny(token.remain_quota ?? token.remaining_quota ?? token.quota);

    return {
      id: String(token.id ?? token.name ?? index),
      name: String(token.name || token.title || `API Key ${index + 1}`),
      preview: maskKey(token.key || token.token || token.preview || ''),
      enabled: tokenEnabled(token.status ?? token.enabled),
      cost: formatMoney(usedQuota, quotaPerCny),
      tokens: `${formatQuota(remainQuota, quotaPerCny)} 额度`,
      lastUsed: formatDate(token.accessed_time ?? token.last_used_time ?? token.updated_at),
      expiresAt: formatDate(token.expired_time ?? token.expires_at),
    };
  });
}

export function normalizeNewApiUsage(raw, options = {}) {
  const quotaPerCny = quotaUnit(options);
  const grouped = new Map();

  for (const row of unwrapArray(raw)) {
    const model = String(row.model_name || row.model || row.modelName || 'unknown');
    const bucket = modelBucket(model);
    const current = grouped.get(bucket.model) || {
      model: bucket.model,
      family: bucket.family,
      quota: 0,
      calls: 0,
      tokens: 0,
    };

    current.quota += numberFromAny(row.quota ?? row.used_quota ?? row.cost);
    current.calls += numberFromAny(row.count ?? row.request_count ?? row.calls);
    current.tokens += numberFromAny(row.prompt_tokens ?? row.input_tokens) + numberFromAny(row.completion_tokens ?? row.output_tokens);
    grouped.set(bucket.model, current);
  }

  const rows = [...grouped.values()].sort((left, right) => right.quota - left.quota);
  const totalQuota = rows.reduce((sum, row) => sum + row.quota, 0) || 1;

  return rows.map((row) => ({
    model: row.model,
    family: row.family,
    percent: Math.round((row.quota / totalQuota) * 100),
    amount: formatMoney(row.quota, quotaPerCny),
    calls: `${row.calls} 次`,
    tokens: formatTokenCount(row.tokens),
  }));
}

export function normalizeNewApiChannels(raw) {
  return unwrapArray(raw).map((channel) => {
    const status = channel.status || (channel.ok ? 'healthy' : 'down');
    const ok = ['healthy', 'ok', 'enabled', 'normal', true, 1].includes(status);
    const latencyMs = numberFromAny(channel.response_time_ms ?? channel.latency_ms ?? channel.latencyMs);
    const pingMs = numberFromAny(channel.ping_ms ?? channel.pingMs);
    const successRate = readSuccessRate(channel);
    const successCount = numberFromAny(channel.success_count ?? channel.successCount);
    const totalCount = numberFromAny(channel.total_count ?? channel.totalCount);
    const state = ok ? (latencyMs > 1200 ? 'slow' : 'ok') : 'down';

    return {
      provider: providerLabel(channel.provider || channel.type || channel.model),
      channel: String(channel.name || channel.channel || channel.provider || '模型通道'),
      model: String(channel.model || channel.default_model || channel.model_name || '-'),
      endpoint: String(channel.endpoint || channel.public_endpoint || '/v1'),
      ok,
      latencyMs,
      pingMs,
      checkedAt: formatTime(channel.checked_at || channel.updated_at),
      officialStatus: ok ? (state === 'slow' ? '降级' : '正常') : '异常',
      availability: `${(successRate * 100).toFixed(2)}%`,
      successLabel: `${successCount}/${totalCount} 成功`,
      history: Array.isArray(channel.history) ? channel.history.slice(0, DEFAULT_HISTORY_SIZE) : Array(DEFAULT_HISTORY_SIZE).fill(state),
      replacement: String(channel.replacement || ''),
    };
  });
}

function unwrapArray(raw) {
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw?.data)) return raw.data;
  if (Array.isArray(raw?.data?.items)) return raw.data.items;
  if (Array.isArray(raw?.items)) return raw.items;
  if (Array.isArray(raw?.rows)) return raw.rows;
  return [];
}

function unwrapObject(raw) {
  if (raw?.data && !Array.isArray(raw.data)) return raw.data;
  return raw || {};
}

function readPlanName(user, planNames = {}) {
  const group = String(user.plan || user.group || user.plan_name || 'default');
  return planNames[group] || user.plan_label || group;
}

function initialsFrom(value) {
  const parts = String(value || 'U')
    .replace(/[_-]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }

  return String(parts[0] || 'U')
    .slice(0, 2)
    .toUpperCase();
}

function tokenEnabled(status) {
  return [1, true, '1', 'enabled', 'active', 'normal'].includes(status);
}

function maskKey(value) {
  const key = String(value || '');
  if (!key) return 'fk-live-••••••';

  const last = key.slice(-4);
  const prefix = /^fk-live-/i.test(key) ? 'fk-live' : key.slice(0, Math.min(6, key.length)).replace(/-$/, '');
  return `${prefix}-••••••${last}`;
}

function modelBucket(model) {
  const normalized = String(model).toLowerCase();
  if (normalized.includes('claude') || normalized.includes('anthropic')) {
    return { model: 'Claude', family: 'Anthropic' };
  }
  if (normalized.includes('codex')) {
    return { model: 'Codex', family: 'OpenAI' };
  }
  if (normalized.includes('opencode')) {
    return { model: 'OpenCode', family: 'Other' };
  }
  return { model: 'OpenAI', family: 'OpenAI' };
}

function providerLabel(value) {
  const normalized = String(value || '').toLowerCase();
  if (normalized.includes('claude') || normalized.includes('anthropic')) return 'Claude';
  if (normalized.includes('openai') || normalized.includes('gpt') || normalized.includes('codex')) return 'OpenAI';
  return String(value || '模型');
}

function readSuccessRate(channel) {
  const direct = channel.success_rate ?? channel.successRate ?? channel.availability;
  if (direct !== undefined) {
    const value = Number(String(direct).replace('%', ''));
    return value > 1 ? value / 100 : value;
  }

  const success = numberFromAny(channel.success_count ?? channel.successCount);
  const total = numberFromAny(channel.total_count ?? channel.totalCount);
  return total > 0 ? success / total : channel.ok === false ? 0 : 1;
}

function numberFromAny(value) {
  if (value === null || value === undefined || value === '') return 0;
  const parsed = Number(String(value).replace(/[^\d.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function quotaUnit(options) {
  return Number(options.quotaPerCny || DEFAULT_QUOTA_PER_CNY);
}

function formatMoney(quota, quotaPerCny) {
  return `¥${formatQuota(quota, quotaPerCny)}`;
}

function formatQuota(quota, quotaPerCny) {
  return (numberFromAny(quota) / quotaPerCny).toFixed(2);
}

function formatTokenCount(tokens) {
  return `${(numberFromAny(tokens) / 1_000_000).toFixed(2)}M`;
}

function formatDate(value) {
  const numeric = numberFromAny(value);
  if (!numeric || numeric < 0) return '-';
  const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toISOString().slice(0, 10);
}

function formatTime(value) {
  if (!value) return '--:--';
  if (typeof value === 'string' && /^\d{1,2}:\d{2}$/.test(value)) return value;
  const numeric = numberFromAny(value);
  if (!numeric) return '--:--';
  const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
  if (Number.isNaN(date.getTime())) return '--:--';
  return date.toISOString().slice(11, 16);
}

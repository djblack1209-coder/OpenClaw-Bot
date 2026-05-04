import { normalizeBaseUrl, normalizeModelGroup } from '../src/core.js';

const DEFAULT_QUOTA_PER_CNY = 100;
const DEFAULT_USD_TO_CNY = 7.2;
const TOKEN_STATUS_ENABLED = 1;
const TOKEN_STATUS_DISABLED = 2;
const TOKEN_STATUS_EXHAUSTED = 4;
const PAGE_SIZE = 100;

export function createNewApiBridge(options = {}) {
  const config = normalizeBridgeConfig(options);
  if (!config.enabled) {
    return null;
  }

  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') {
    throw new Error('New-API 适配器需要 fetch 支持');
  }

  async function request(path, requestOptions = {}) {
    const response = await fetchImpl(`${config.baseUrl}${path}`, {
      method: requestOptions.method || 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: config.accessToken,
        'New-Api-User': String(config.userId),
        ...(requestOptions.body ? { 'content-type': 'application/json' } : {}),
        ...(requestOptions.headers || {}),
      },
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
    });
    const text = await response.text();
    const payload = parseJson(text);
    if (!response.ok || payload.success === false || payload.code === false) {
      const message = payload.message || payload.error || `New-API 请求失败: ${response.status}`;
      const error = new Error(message);
      error.statusCode = response.ok ? 502 : response.status;
      error.expose = true;
      throw error;
    }
    return payload;
  }

  return {
    config,
    async buildDashboard(localData, user, serverOptions) {
      const [self, tokens, usage, stats, quotaData, subscriptions, topupInfo, affiliate] = await Promise.allSettled([
        request('/api/user/self'),
        request(`/api/token/?p=1&size=${PAGE_SIZE}`),
        request(`/api/log/self?p=1&size=${PAGE_SIZE}`),
        request('/api/log/self/stat'),
        request('/api/data/self'),
        request('/api/subscription/self'),
        request('/api/user/topup/info'),
        request('/api/user/aff'),
      ]);
      const tokenRows = unwrapArray(settledValue(tokens));
      const usageRows = unwrapArray(settledValue(usage));
      const statPayload = settledValue(stats);
      const quotaRows = unwrapArray(settledValue(quotaData));
      const safeUser = {
        ...user,
        newApiUserId: config.userId,
        newApiMode: true,
      };
      return {
        authenticated: true,
        account: accountFromNewApi(settledValue(self), usageRows, statPayload, quotaRows),
        user: sanitizeBridgeUser(safeUser, settledValue(self)),
        balanceAlert: sanitizeLocalBalanceAlert(user),
        apiKeys: tokenRows.map((token) => sanitizeBridgeToken(token, { revealSecret: true })),
        modelUsage: buildBridgeModelUsage(usageRows),
        channelChecks: [],
        modelCatalog: [],
        rechargeOptions: buildBridgeRechargeOptions(localData, settledValue(topupInfo)),
        usageRecords: buildBridgeUsageRecords(usageRows),
        recentLogs: buildBridgeRecentLogs(usageRows, {
          subscriptions: settledValue(subscriptions),
          affiliate: settledValue(affiliate),
        }),
      };
    },
    async createToken(body) {
      const tokenPayload = tokenCreatePayload(body, config);
      await request('/api/token/', { method: 'POST', body: tokenPayload });
      const tokens = unwrapArray(await request(`/api/token/search?keyword=${encodeURIComponent(tokenPayload.name)}&p=1&size=10`));
      const created = tokens.find((token) => String(token.name || '') === tokenPayload.name) || tokens[0] || tokenPayload;
      const keyPayload = created.id ? await request(`/api/token/${encodeURIComponent(created.id)}/key`, { method: 'POST' }) : {};
      const key = unwrapObject(keyPayload).key || created.key || '';
      return { key: sanitizeBridgeToken({ ...created, key }, { revealSecret: true }) };
    },
    async updateToken(keyId, body) {
      const current = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      const patch = {
        ...current,
        id: Number(current.id || keyId),
        name: Object.prototype.hasOwnProperty.call(body, 'name') ? String(body.name || '').trim().slice(0, 50) : current.name,
        status: Object.prototype.hasOwnProperty.call(body, 'enabled')
          ? (body.enabled ? TOKEN_STATUS_ENABLED : TOKEN_STATUS_DISABLED)
          : Number(current.status || TOKEN_STATUS_ENABLED),
        expired_time: normalizeExpiredTime(current.expired_time),
        remain_quota: Number(current.remain_quota ?? config.defaultTokenQuota),
        unlimited_quota: Boolean(current.unlimited_quota),
        model_limits_enabled: Boolean(current.model_limits_enabled),
        model_limits: current.model_limits || '',
        allow_ips: current.allow_ips || '',
        group: current.group || config.defaultGroup,
        cross_group_retry: Boolean(current.cross_group_retry),
      };
      if (!patch.name) {
        throw publicBridgeError(400, 'API Key 名称不能为空');
      }
      const updated = await request('/api/token/', { method: 'PUT', body: patch });
      return { key: sanitizeBridgeToken(unwrapObject(updated) || patch, { revealSecret: true }) };
    },
    async deleteToken(keyId) {
      await request(`/api/token/${encodeURIComponent(keyId)}`, { method: 'DELETE' });
      return { deletedKeyId: String(keyId) };
    },
    async redeemCode(body) {
      const code = String(body.code || '').trim();
      if (!code) {
        throw publicBridgeError(400, '兑换码不能为空');
      }
      const redeemed = await request('/api/user/topup', { method: 'POST', body: { key: code } });
      const [self, usage] = await Promise.allSettled([
        request('/api/user/self'),
        request(`/api/log/self?p=1&size=${PAGE_SIZE}`),
      ]);
      return {
        account: accountFromNewApi(settledValue(self), unwrapArray(settledValue(usage)), {}, []),
        user: null,
        newApiQuota: unwrapObject(redeemed),
      };
    },
    async buildImportUrl(requestUrl, buildUrl) {
      const tokens = unwrapArray(await request(`/api/token/?p=1&size=${PAGE_SIZE}`));
      const key = tokens.find((token) => tokenEnabled(token.status ?? token.enabled));
      if (!key) {
        throw publicBridgeError(409, '没有可用的 API Key');
      }
      const keyPayload = await request(`/api/token/${encodeURIComponent(key.id)}/key`, { method: 'POST' });
      const secret = unwrapObject(keyPayload).key || key.key || '';
      if (!secret) {
        throw publicBridgeError(409, 'New-API 未返回完整 API Key');
      }
      const modelGroup = normalizeBridgeModelGroup(key);
      const availableModels = normalizeModelLimits(key);
      const defaultModel = strongestBridgeModel(availableModels, requestUrl.searchParams.get('model') || '', modelGroup);
      return buildUrl({
        target: requestUrl.searchParams.get('target') || 'Claude',
        apiKey: secret,
        modelGroup,
        availableModels,
        defaultModel,
      });
    },
    async proxyGateway({ request, response, url, bodyText }) {
      const upstream = await fetchImpl(`${config.gatewayBaseUrl}${gatewayPath(url.pathname)}`, {
        method: request.method,
        headers: filterGatewayHeaders(request.headers),
        body: bodyText,
      });
      response.writeHead(upstream.status, {
        'content-type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
        'access-control-allow-origin': '*',
        'cache-control': 'no-store',
        ...(upstream.body ? { 'x-accel-buffering': 'no' } : {}),
      });
      if (upstream.body) {
        await pipeReadableStreamToResponse(upstream.body, response);
        return true;
      }
      response.end(await upstream.text());
      return true;
    },
  };
}

function normalizeBridgeConfig(options) {
  const enabled = booleanOption(options.newApiEnabled, process.env.FRIST_API_NEWAPI_ENABLED);
  const baseUrlInput = options.newApiBaseUrl || process.env.FRIST_API_NEWAPI_BASE_URL || '';
  const accessToken = String(options.newApiAccessToken || process.env.FRIST_API_NEWAPI_ACCESS_TOKEN || '').trim();
  const userId = String(options.newApiUserId || process.env.FRIST_API_NEWAPI_USER_ID || '').trim();
  if (!enabled) {
    return { enabled: false };
  }
  if (!baseUrlInput || !accessToken || !userId) {
    throw new Error('启用 New-API 适配器时必须配置 FRIST_API_NEWAPI_BASE_URL / ACCESS_TOKEN / USER_ID');
  }
  const baseUrl = normalizeBaseUrl(baseUrlInput);
  return {
    enabled,
    baseUrl,
    gatewayBaseUrl: normalizeBaseUrl(options.newApiGatewayBaseUrl || process.env.FRIST_API_NEWAPI_GATEWAY_BASE_URL || `${baseUrl}/v1`),
    accessToken: /^Bearer\s+/i.test(accessToken) ? accessToken : `Bearer ${accessToken}`,
    userId,
    defaultTokenQuota: Number(options.newApiDefaultTokenQuota ?? process.env.FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA ?? 0),
    defaultGroup: String(options.newApiDefaultGroup || process.env.FRIST_API_NEWAPI_DEFAULT_GROUP || 'default'),
  };
}

function booleanOption(value, envValue) {
  if (typeof value === 'boolean') return value;
  return String(envValue || '') === '1';
}

function tokenCreatePayload(body, config) {
  const modelGroup = normalizeModelGroup(body.modelGroup);
  const modelLimits = modelLimitsForGroup(modelGroup);
  return {
    name: String(body.name || `Frist-API Key ${Date.now()}`).trim().slice(0, 50),
    expired_time: normalizeExpiredTime(body.expiredTime ?? body.expired_time),
    remain_quota: Number(body.remainQuota ?? body.remain_quota ?? config.defaultTokenQuota),
    unlimited_quota: body.unlimitedQuota ?? body.unlimited_quota ?? true,
    model_limits_enabled: modelLimits.length > 0,
    model_limits: modelLimits.join(','),
    allow_ips: '',
    group: config.defaultGroup,
    cross_group_retry: true,
  };
}

function modelLimitsForGroup(group) {
  const normalized = normalizeModelGroup(group);
  if (normalized === 'Claude') return ['claude-*'];
  if (normalized === 'OpenAI') return ['gpt-*', 'o*', 'dall-*'];
  if (normalized === 'Gemini') return ['gemini-*'];
  if (normalized === 'DeepSeek') return ['deepseek-*'];
  return [];
}

function normalizeExpiredTime(value) {
  if (value === undefined || value === null || value === '' || value === '-') return -1;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return numeric;
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.floor(date / 1000) : -1;
}

function accountFromNewApi(rawSelf, usageRows, rawStats, quotaRows) {
  const self = unwrapObject(rawSelf);
  const stat = unwrapObject(rawStats);
  const quota = numberFromAny(self.quota ?? self.remain_quota ?? self.remaining_quota);
  const usedQuota = numberFromAny(self.used_quota ?? self.usedQuota);
  const todayRows = rowsForToday(usageRows);
  const todayQuota = sum(todayRows, (row) => numberFromAny(row.quota ?? row.used_quota ?? row.cost));
  const todayTokens = sum(todayRows, tokenTotalFromRow);
  const totalTokens = quotaRows.length ? sum(quotaRows, tokenTotalFromRow) : sum(usageRows, tokenTotalFromRow);
  const requestCount = numberFromAny(stat.today_count ?? stat.request_count ?? self.request_count ?? todayRows.length);
  const averageLatency = average(usageRows.map((row) => numberFromAny(row.use_time ?? row.latency_ms ?? row.response_time_ms)).filter(Boolean));
  return {
    plan: String(self.group || self.plan || self.plan_name || 'New-API'),
    renewalDate: formatDate(self.expired_time ?? self.subscription_expires_at ?? self.renewal_time),
    balance: formatMoney(quota),
    packageQuota: formatMoney(quota),
    boosterQuota: '$0.00',
    quotaLeft: formatMoney(quota),
    todayCost: formatMoney(todayQuota),
    monthCost: formatMoney(usedQuota),
    usageTotal: formatMoney(usedQuota),
    todayCalls: `${requestCount} 次`,
    todayTokens: compactTokenText(todayTokens),
    totalTokens: compactTokenText(totalTokens),
    averageLatency: averageLatency ? `${Math.round(averageLatency)}ms` : '-',
    successRate: successRateLabel(usageRows),
  };
}

function sanitizeBridgeUser(localUser, rawSelf) {
  const self = unwrapObject(rawSelf);
  const email = String(self.email || localUser.email || '');
  return {
    id: localUser.id,
    email,
    emailVerified: Boolean(localUser.emailVerified),
    isAdmin: Boolean(localUser.isAdmin),
    plan: String(self.group || localUser.plan || 'New-API'),
    renewalDate: formatDate(self.expired_time ?? self.subscription_expires_at) || localUser.renewalDate,
    userInitials: initialsFrom(email || self.username || self.display_name),
    newApiMode: true,
  };
}

function sanitizeBridgeToken(token, options = {}) {
  const secret = String(token.key || token.token || '');
  const modelGroup = normalizeBridgeModelGroup(token);
  return {
    id: String(token.id ?? token.name ?? ''),
    name: String(token.name || 'New-API Key'),
    preview: maskBridgeKey(secret || token.preview || token.key_preview || ''),
    ...(options.revealSecret && secret ? { secret } : {}),
    enabled: tokenEnabled(token.status ?? token.enabled),
    modelGroup,
    cost: formatMoney(token.used_quota ?? token.usedQuota),
    tokens: `${formatQuota(token.remain_quota ?? token.remaining_quota ?? token.quota)} 额度`,
    lastUsed: formatDate(token.accessed_time ?? token.last_used_time ?? token.updated_at),
    expiresAt: formatDate(token.expired_time ?? token.expires_at),
  };
}

function buildBridgeModelUsage(rows) {
  const grouped = new Map();
  for (const row of rows) {
    const model = String(row.model_name || row.model || row.modelName || 'unknown');
    const key = modelBucket(model).model;
    const current = grouped.get(key) || { model: key, family: modelBucket(model).family, quota: 0, calls: 0, tokens: 0 };
    current.quota += numberFromAny(row.quota ?? row.used_quota ?? row.cost);
    current.calls += numberFromAny(row.count ?? row.request_count ?? 1);
    current.tokens += tokenTotalFromRow(row);
    grouped.set(key, current);
  }
  const total = sum([...grouped.values()], (row) => row.quota) || 1;
  return [...grouped.values()].sort((left, right) => right.quota - left.quota).map((row) => ({
    model: row.model,
    family: row.family,
    amount: formatMoney(row.quota),
    calls: `${row.calls} 次`,
    tokens: compactTokenText(row.tokens),
    percent: Math.max(4, Math.round((row.quota / total) * 100)),
  }));
}

function buildBridgeUsageRecords(rows) {
  return rows.slice(0, 80).map((row, index) => ({
    id: String(row.id || row.created_at || `newapi-usage-${index + 1}`),
    apiKey: maskBridgeKey(row.token_name || row.token || row.key || ''),
    model: String(row.model_name || row.model || 'unknown'),
    inferenceEffort: String(row.reasoning_effort || row.inference_effort || '默认'),
    endpoint: String(row.endpoint || row.path || '/v1/chat/completions'),
    type: requestTypeLabel(row),
    billingMode: row.is_stream ? '流式' : '按量',
    tokens: compactTokenText(tokenTotalFromRow(row)),
    amount: formatMoney(row.quota ?? row.used_quota ?? row.cost),
    status: row.is_error || row.status === 'failed' ? 'failed' : 'success',
    at: formatDateTime(row.created_at ?? row.created_time ?? row.time),
  }));
}

function buildBridgeRecentLogs(rows, meta = {}) {
  const logs = buildBridgeUsageRecords(rows).slice(0, 10).map((row) => ({
    type: 'newapi_usage',
    at: row.at,
    detail: `${row.model} 调用 ${row.tokens}，计费 ${row.amount}`,
  }));
  if (meta.subscriptions) {
    logs.push({ type: 'newapi_subscription', at: '', detail: '订阅状态已从 New-API 同步' });
  }
  if (meta.affiliate) {
    logs.push({ type: 'newapi_affiliate', at: '', detail: '邀请返利数据已从 New-API 同步' });
  }
  return logs.slice(0, 10);
}

function buildBridgeRechargeOptions(localData, rawTopupInfo) {
  const info = unwrapObject(rawTopupInfo);
  const plans = localData?.pricing?.rechargePlans || [];
  return plans.map((plan, index) => ({
    id: plan.id,
    label: plan.label,
    quotaUsd: plan.quotaUsd,
    priceCny: plan.priceCny,
    durationDays: plan.durationDays,
    plan: plan.plan,
    cny: `¥${Number(plan.priceCny || 0).toFixed(2)}`,
    quota: `$${Number(plan.quotaUsd || 0).toFixed(0)}`,
    active: index === 0,
    newApiTopupEnabled: Boolean(info.enable_online_topup || info.enable_stripe_topup || info.enable_creem_topup),
  }));
}

function sanitizeLocalBalanceAlert(user) {
  const alert = user.balanceAlert || {};
  const thresholdCents = Number(alert.thresholdCents || 3600);
  return {
    enabled: alert.enabled !== false,
    threshold: `$${(thresholdCents / 100 / DEFAULT_USD_TO_CNY).toFixed(2)}`,
    thresholdUsd: thresholdCents / 100 / DEFAULT_USD_TO_CNY,
    thresholdCny: thresholdCents / 100,
    thresholdCents,
    email: alert.email || user.email || '',
    lastAlertAt: alert.lastAlertAt || '',
  };
}

function normalizeBridgeModelGroup(token) {
  const limits = normalizeModelLimits(token).join('\n').toLowerCase();
  if (limits.includes('deepseek')) return 'DeepSeek';
  if (limits.includes('gemini')) return 'Gemini';
  if (limits.includes('claude') || limits.includes('anthropic')) return 'Claude';
  if (limits.includes('gpt') || limits.includes('dall') || limits.includes('image')) return 'OpenAI';
  return normalizeModelGroup(token.modelGroup || token.model_group || 'All');
}

function normalizeModelLimits(token) {
  const raw = token.model_limits ?? token.modelLimits ?? token.models ?? token.availableModels ?? '';
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean);
  return String(raw || '').split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
}

function strongestBridgeModel(models, requested, modelGroup) {
  const cleaned = models.filter((model) => !model.includes('*'));
  if (requested) return requested;
  if (cleaned.length) return cleaned[0];
  const group = normalizeModelGroup(modelGroup);
  if (group === 'DeepSeek') return 'deepseek-v4-flash';
  if (group === 'Claude') return 'claude-opus-4-6-thinking-c';
  if (group === 'Gemini') return 'gemini-2.5-flash';
  return 'gpt-5.5';
}

function tokenEnabled(status) {
  return [TOKEN_STATUS_ENABLED, true, '1', 'enabled', 'active', 'normal'].includes(status);
}

function settledValue(result) {
  return result && result.status === 'fulfilled' ? result.value : {};
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

function parseJson(text) {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return {};
  }
}

function rowsForToday(rows) {
  const today = new Date().toISOString().slice(0, 10);
  return rows.filter((row) => formatDateTime(row.created_at ?? row.created_time ?? row.time).startsWith(today));
}

function tokenTotalFromRow(row) {
  return (
    numberFromAny(row.prompt_tokens ?? row.input_tokens) +
    numberFromAny(row.completion_tokens ?? row.output_tokens) +
    numberFromAny(row.tokens ?? row.token_count)
  );
}

function successRateLabel(rows) {
  if (!rows.length) return '0%';
  const success = rows.filter((row) => !row.is_error && row.status !== 'failed').length;
  return `${Math.round((success / rows.length) * 1000) / 10}%`;
}

function requestTypeLabel(row) {
  const endpoint = String(row.endpoint || row.path || '').toLowerCase();
  const model = String(row.model_name || row.model || '').toLowerCase();
  if (endpoint.includes('image') || model.includes('image')) return '图片';
  if (endpoint.includes('responses')) return 'Responses';
  return '文本';
}

function modelBucket(model) {
  const value = String(model || '').toLowerCase();
  if (value.includes('deepseek')) return { model: 'DeepSeek', family: 'DeepSeek' };
  if (value.includes('claude') || value.includes('anthropic')) return { model: 'Claude', family: 'Anthropic' };
  if (value.includes('gemini')) return { model: 'Gemini', family: 'Google' };
  if (value.includes('codex')) return { model: 'Codex', family: 'OpenAI' };
  return { model: 'OpenAI', family: 'OpenAI' };
}

function numberFromAny(value) {
  if (value === null || value === undefined || value === '') return 0;
  const parsed = Number(String(value).replace(/[^\d.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function sum(rows, mapper) {
  return rows.reduce((total, row) => total + Number(mapper(row) || 0), 0);
}

function average(values) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
}

function formatMoney(quota) {
  return `$${(numberFromAny(quota) / DEFAULT_QUOTA_PER_CNY / DEFAULT_USD_TO_CNY).toFixed(2)}`;
}

function formatQuota(quota) {
  return (numberFromAny(quota) / DEFAULT_QUOTA_PER_CNY).toFixed(2);
}

function compactTokenText(tokens) {
  const value = numberFromAny(tokens);
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(Math.round(value));
}

function formatDate(value) {
  const numeric = numberFromAny(value);
  if (!numeric || numeric < 0) return '-';
  const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toISOString().slice(0, 10);
}

function formatDateTime(value) {
  if (!value) return '';
  if (typeof value === 'string' && Number.isNaN(Number(value))) return value;
  const numeric = numberFromAny(value);
  if (!numeric) return '';
  const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

function initialsFrom(value) {
  const cleaned = String(value || 'FA').replace(/@.*$/, '').replace(/[_-]+/g, ' ').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return String(parts[0] || 'FA').slice(0, 2).toUpperCase();
}

function maskBridgeKey(value) {
  const key = String(value || '');
  if (!key) return 'sk-******';
  const normalized = key.startsWith('sk-') ? key : `sk-${key}`;
  return `${normalized.slice(0, 6)}••••••${normalized.slice(-4)}`;
}

function gatewayPath(pathname) {
  if (pathname.startsWith('/v1/')) return pathname.replace(/^\/v1/, '');
  if (pathname.startsWith('/openai/')) return pathname.replace(/^\/openai/, '');
  return pathname;
}

function filterGatewayHeaders(headers) {
  const clean = {};
  for (const [key, value] of Object.entries(headers)) {
    const normalized = key.toLowerCase();
    if (['host', 'connection', 'content-length'].includes(normalized)) continue;
    clean[key] = Array.isArray(value) ? value.join(', ') : value;
  }
  return clean;
}

async function pipeReadableStreamToResponse(stream, response) {
  const reader = stream.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      response.write(Buffer.from(value));
    }
  } finally {
    response.end();
    reader.releaseLock();
  }
}

function publicBridgeError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.expose = true;
  return error;
}

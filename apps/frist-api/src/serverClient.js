export function createFristApiBrowserClient(options = {}) {
  const baseUrl = String(options.baseUrl || window.location.origin).replace(/\/+$/, '');
  const fetchImpl = options.fetchImpl || window.fetch.bind(window);
  let csrfToken = '';

  async function request(path, requestOptions = {}) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method: requestOptions.method || 'GET',
      credentials: 'include',
      headers: {
        ...(requestOptions.body ? { 'content-type': 'application/json' } : {}),
        ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(String(requestOptions.method || 'GET').toUpperCase()) ? { 'x-csrf-token': csrfToken } : {}),
        ...(requestOptions.headers || {}),
      },
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (payload.csrfToken) {
      csrfToken = payload.csrfToken;
    }
    if (!response.ok) {
      const error = new Error(payload.error || `请求失败: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  async function gatewayRequest(path, requestOptions = {}) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method: requestOptions.method || 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${requestOptions.apiKey || ''}`,
        ...(requestOptions.headers || {}),
      },
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      const errorMessage =
        (payload.error && typeof payload.error === 'object' ? payload.error.message : payload.error) ||
        `请求失败: ${response.status}`;
      const error = new Error(errorMessage);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  return {
    register: (body) => request('/api/frist/register', { method: 'POST', body }),
    login: (body) => request('/api/frist/login', { method: 'POST', body }),
    challenge: () => request('/api/frist/challenge'),
    claimAdmin: (body) => request('/api/frist/admin/claim', { method: 'POST', body }),
    changePassword: (body) => request('/api/frist/password', { method: 'POST', body }),
    requestPasswordReset: (body) => request('/api/frist/password-reset/request', { method: 'POST', body }),
    confirmPasswordReset: (body) => request('/api/frist/password-reset/confirm', { method: 'POST', body }),
    verify: (body) => request('/api/frist/verify', { method: 'POST', body }),
    updateProfile: (body) => request('/api/frist/profile', { method: 'PATCH', body }),
    recharge: (body) => request('/api/frist/recharge', { method: 'POST', body }),
    redeem: (body) => request('/api/frist/redeem', { method: 'POST', body }),
    saveBalanceAlert: (body) => request('/api/frist/balance-alert', { method: 'PUT', body }),
    sendBalanceAlertTest: (body) => request('/api/frist/balance-alert/test', { method: 'POST', body }),
    createKey: (body) => request('/api/frist/token', { method: 'POST', body }),
    setKeyEnabled: (id, body) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
    renameKey: (id, body) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
    deleteKey: (id) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    getImportUrl: ({ target, model, modelGroup, keyId }) => {
      const params = new URLSearchParams({ target, model });
      if (modelGroup) params.set('modelGroup', modelGroup);
      if (keyId) params.set('keyId', keyId);
      return request(`/api/frist/import-url?${params.toString()}`);
    },
    loadDashboard: () => request('/api/frist/dashboard'),
    chatCompletion: ({ apiKey, body }) => gatewayRequest('/v1/chat/completions', { apiKey, body }),
    generateImage: ({ apiKey, body }) => gatewayRequest('/v1/images/generations', { apiKey, body }),
  };
}

export function normalizeFristDashboard(payload, fallback = createEmptyDashboard()) {
  const authenticated = Boolean(payload.authenticated);
  const account = payload.account || {};
  const user = payload.user || {};
  const apiKeys = Array.isArray(payload.apiKeys) ? payload.apiKeys : [];
  const channelChecks = Array.isArray(payload.channelChecks) ? payload.channelChecks : [];
  const modelUsage = Array.isArray(payload.modelUsage) ? payload.modelUsage : [];
  const modelCatalog = Array.isArray(payload.modelCatalog) ? payload.modelCatalog : [];
  const rechargeOptions = Array.isArray(payload.rechargeOptions) ? payload.rechargeOptions : [];
  const balanceAlert = normalizeBalanceAlert(payload.balanceAlert, fallback.balanceAlert);
  const accountFallback = authenticated ? fallback.accountSummary : guestAccountFallback(fallback.accountSummary);

  return {
    ...fallback,
    accountSummary: {
      ...accountFallback,
      userInitials: user.userInitials || accountFallback.userInitials,
      displayName: user.displayName || accountFallback.displayName || '',
      avatarUrl: user.avatarUrl || accountFallback.avatarUrl || '',
      plan: account.plan || accountFallback.plan,
      renewalDate: account.renewalDate || accountFallback.renewalDate,
      balance: account.balance || accountFallback.balance,
      todayCost: account.todayCost || accountFallback.todayCost,
      monthCost: account.monthCost || accountFallback.monthCost,
      quotaLeft: account.quotaLeft || account.balance || accountFallback.quotaLeft,
      packageQuota: account.packageQuota || accountFallback.packageQuota,
      boosterQuota: account.boosterQuota || accountFallback.boosterQuota,
      usageTotal: account.usageTotal || account.monthCost || accountFallback.usageTotal,
      todayCalls: account.todayCalls || accountFallback.todayCalls,
      todayTokens: account.todayTokens || accountFallback.todayTokens || '0',
      totalTokens: account.totalTokens || accountFallback.totalTokens || '0',
      averageLatency: account.averageLatency || accountFallback.averageLatency || '-',
      successRate: account.successRate || accountFallback.successRate || '0%',
      email: user.email || accountFallback.email || '',
      emailMasked: user.emailMasked || maskEmail(user.email || accountFallback.email || ''),
      isAdmin: Boolean(user.isAdmin || accountFallback.isAdmin),
    },
    apiKeys: apiKeys.map((key) => ({
      id: key.id,
      name: key.name,
      secret: key.secret,
      preview: key.preview,
      enabled: Boolean(key.enabled),
      cost: key.cost || '$0.00',
      tokens: key.tokens || '0.00M',
      lastUsed: key.lastUsed || '-',
      expiresAt: key.expiresAt || '-',
      modelGroup: key.modelGroup || 'All',
    })),
    modelUsage: modelUsage.length > 0 ? normalizeModelUsage(modelUsage) : zeroModelUsage(fallback.modelUsage),
    channelChecks: normalizeChannelChecks(channelChecks),
    modelCatalog: normalizeModelCatalog(modelCatalog, fallback.modelCatalog || []),
    rechargeOptions: normalizeRechargeOptions(rechargeOptions, fallback.rechargeOptions || []),
    usageRecords: normalizeUsageRecords(payload.usageRecords || fallback.usageRecords || []),
    usageAnomalies: normalizeUsageAnomalies(payload.usageAnomalies || fallback.usageAnomalies || []),
    recentLogs: normalizeRecentLogs(payload.recentLogs || fallback.recentLogs || []),
    balanceAlert,
  };
}

function createEmptyDashboard() {
  return {
    accountSummary: {
      userInitials: 'FA',
      plan: '未登录',
      renewalDate: '-',
      balance: '$0.00',
      todayCost: '$0.00',
      monthCost: '$0.00',
      quotaLeft: '$0.00',
      packageQuota: '$0.00',
      boosterQuota: '$0.00',
      usageTotal: '$0.00',
      todayCalls: '0 次',
      todayTokens: '0',
      totalTokens: '0',
      averageLatency: '-',
      successRate: '0%',
      email: '',
      emailMasked: '',
      displayName: '',
      avatarUrl: '',
      isAdmin: false,
    },
    apiKeys: [],
    channelChecks: [],
    helpLinks: [],
    importTargets: ['Claude', 'Codex', 'OpenCode', 'OpenClaw', 'Hermes'],
    modelUsage: [],
    modelCatalog: [],
    usageRecords: [],
    usageAnomalies: [],
    recentLogs: [],
    rechargeOptions: [],
    balanceAlert: {
      enabled: true,
      threshold: '$5.00',
      thresholdUsd: 5,
      thresholdCny: 36,
      thresholdCents: 3600,
      email: '',
      lastAlertAt: '',
    },
  };
}

function guestAccountFallback(fallback = {}) {
  return {
    ...fallback,
    userInitials: 'FA',
    plan: '未登录',
    renewalDate: '-',
    balance: '$0.00',
    todayCost: '$0.00',
    monthCost: '$0.00',
    quotaLeft: '$0.00',
    packageQuota: '$0.00',
    boosterQuota: '$0.00',
    usageTotal: '$0.00',
    todayCalls: '0 次',
    todayTokens: '0',
    totalTokens: '0',
    averageLatency: '-',
    successRate: '0%',
  };
}

function normalizeModelUsage(rows) {
  const total = rows.reduce((sum, row) => sum + moneyToNumber(row.amount), 0) || 1;
  return rows.map((row) => {
    const amount = moneyToNumber(row.amount);
    return {
      model: row.model,
      amount: row.amount || '$0.00',
      calls: row.calls || '1 次',
      tokens: row.tokens || '0.00M',
      percent: Math.max(4, Math.round((amount / total) * 100)),
    };
  });
}

function zeroModelUsage(rows) {
  return (rows || []).map((row) => ({
    ...row,
    amount: '$0.00',
    calls: '0 次',
    tokens: '0.00M',
    percent: 0,
  }));
}

function normalizeChannelChecks(rows, fallbackRows = []) {
  return rows.map((row, index) => {
    const fallback = fallbackRows[index % Math.max(fallbackRows.length, 1)] || {};
    const ok = Boolean(row.ok);
    const model = normalizeOfficialModelName(row.model || fallback.model || '');
    const healthyCount = Number(row.healthyCount ?? fallback.healthyCount ?? (ok ? 1 : 0));
    const totalCount = Number(row.totalCount ?? fallback.totalCount ?? (healthyCount || 1));
    const slowCount = Number(row.slowCount ?? fallback.slowCount ?? 0);
    const downCount = Number(row.downCount ?? fallback.downCount ?? Math.max(0, totalCount - healthyCount));
    const monitorStatus = row.monitorStatus || row.officialStatus || fallback.monitorStatus || fallback.officialStatus || (ok ? '正常' : '不可用');
    return {
      provider: row.provider || fallback.provider || 'Claude',
      channel: row.channel || row.poolLabel || fallback.channel || fallback.poolLabel || '号池渠道',
      pool: row.pool || fallback.pool || '',
      poolLabel: row.poolLabel || fallback.poolLabel || '',
      model: model || 'unknown',
      endpoint: row.endpoint || fallback.endpoint || '/v1',
      ok,
      maintenance: false,
      latencyMs: Number(row.latencyMs || fallback.latencyMs || 0),
      pingMs: Number(row.pingMs || fallback.pingMs || 0),
      averageLatencyMs: Number(row.averageLatencyMs || fallback.averageLatencyMs || row.latencyMs || fallback.latencyMs || 0),
      checkedAt: row.checkedAt || fallback.checkedAt || '',
      officialStatus: monitorStatus,
      monitorStatus,
      availability: row.availability || fallback.availability || (totalCount ? `${Math.round((healthyCount / totalCount) * 1000) / 10}%` : '0%'),
      availability7d: Number(row.availability7d ?? row.availability_7d ?? fallback.availability7d ?? fallback.availability_7d ?? (totalCount ? Math.round((healthyCount / totalCount) * 1000) / 10 : 0)),
      availability_7d: Number(row.availability_7d ?? row.availability7d ?? fallback.availability_7d ?? fallback.availability7d ?? (totalCount ? Math.round((healthyCount / totalCount) * 1000) / 10 : 0)),
      availabilityWindow: row.availabilityWindow || fallback.availabilityWindow || '当前库存快照',
      healthyCount,
      totalCount,
      downCount,
      slowCount,
      successLabel: row.successLabel || fallback.successLabel || `${healthyCount}/${totalCount} 可用`,
      latencyLabel: row.latencyLabel || fallback.latencyLabel || (ok ? '等待真实请求更新' : '未检测到可用线路'),
      monitorIntervalSeconds: Number(row.monitorIntervalSeconds || fallback.monitorIntervalSeconds || 60),
      history: Array.isArray(row.history) && row.history.length ? row.history : [],
    };
  });
}

function normalizeUsageRecords(rows) {
  return (Array.isArray(rows) ? rows : []).map((row, index) => ({
    id: row.id || `usage-${index + 1}`,
    apiKey: row.apiKey || row.key || 'sk-******',
    model: row.model || 'unknown',
    inferenceEffort: row.inferenceEffort || row.reasoningEffort || '默认',
    endpoint: row.endpoint || '-',
    type: row.type || '文本',
    billingMode: row.billingMode || '余额',
    client: row.client || 'API',
    tokens: row.tokens || '0',
    amount: row.amount || '$0.00',
    amountCny: row.amountCny || '',
    latency: row.latency || '-',
    status: row.status || 'success',
    at: row.at || '',
  }));
}

function normalizeUsageAnomalies(rows) {
  return (Array.isArray(rows) ? rows : []).map((row, index) => ({
    id: row.id || `usage-anomaly-${index + 1}`,
    severity: ['critical', 'warning', 'info'].includes(row.severity) ? row.severity : 'info',
    title: row.title || '异常检测',
    detail: row.detail || '',
    action: row.action || '查看记录',
    at: row.at || '',
  }));
}

function normalizeRecentLogs(rows) {
  return (Array.isArray(rows) ? rows : []).map((row, index) => ({
    id: row.id || `log-${index + 1}`,
    type: row.type || 'event',
    detail: row.detail || '系统事件',
    at: row.at || '',
  }));
}

function normalizeModelCatalog(rows, fallbackRows = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return fallbackRows;
  }
  return rows.map((row) => ({
    model: normalizeOfficialModelName(row.model || row.id || 'unknown'),
    family: row.family || row.provider || 'Other',
    tagline: row.tagline || row.description || '当前可用',
    context: row.context || '按模型能力',
    price: row.price || row.billing || '官方价格待同步',
    available: row.available !== false,
  }));
}

function normalizeRechargeOptions(rows, fallbackRows = []) {
  const source = Array.isArray(rows) && rows.length > 0 ? rows : fallbackRows;
  return source.map((row, index) => ({
    id: row.id || `plan-${index + 1}`,
    label: row.label || '充值套餐',
    cny: row.cny || `¥${Number(row.priceCny || row.amountCny || 0).toFixed(2)}`,
    quota: row.quota || (row.quotaUsd ? `$${Number(row.quotaUsd).toFixed(0)}` : ''),
    quotaUsd: Number(row.quotaUsd || 0),
    priceCny: Number(row.priceCny ?? row.amountCny ?? moneyToNumber(row.cny)),
    durationDays: Number(row.durationDays || 0),
    plan: row.plan || (Number(row.durationDays || 0) === 1 ? 'day' : 'balance'),
    active: row.active === true || index === 0,
  }));
}

function normalizeBalanceAlert(row = {}, fallback = {}) {
  const thresholdUsd = Number(row.thresholdUsd ?? fallback.thresholdUsd ?? 5);
  const thresholdCny = Number(row.thresholdCny ?? fallback.thresholdCny ?? thresholdUsd * 7.2);
  const thresholdCents = Number(row.thresholdCents ?? fallback.thresholdCents ?? Math.round(thresholdCny * 100));
  const normalizedThreshold = Number.isFinite(thresholdCents) && thresholdCents > 0 ? thresholdCents : 3600;
  return {
    enabled: row.enabled !== undefined ? Boolean(row.enabled) : fallback.enabled !== false,
    threshold: row.threshold || fallback.threshold || `$${(normalizedThreshold / 100 / 7.2).toFixed(2)}`,
    thresholdCny: Number((normalizedThreshold / 100).toFixed(2)),
    thresholdUsd: Number((normalizedThreshold / 100 / 7.2).toFixed(2)),
    thresholdCents: normalizedThreshold,
    email: row.email || fallback.email || '',
    lastAlertAt: row.lastAlertAt || fallback.lastAlertAt || '',
  };
}

function moneyToNumber(value) {
  const number = Number(String(value || '').replace(/[^\d.-]/g, ''));
  return Number.isFinite(number) ? number : 0;
}

function maskEmail(value) {
  const email = String(value || '');
  const [name = '', domain = ''] = email.split('@');
  if (!name || !domain) return email;
  return `${name.slice(0, 2)}***@${domain}`;
}
import { normalizeOfficialModelName } from './core.js';

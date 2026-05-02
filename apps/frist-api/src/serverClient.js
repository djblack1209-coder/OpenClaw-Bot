export function createFristApiBrowserClient(options = {}) {
  const baseUrl = String(options.baseUrl || window.location.origin).replace(/\/+$/, '');
  const fetchImpl = options.fetchImpl || window.fetch.bind(window);

  async function request(path, requestOptions = {}) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method: requestOptions.method || 'GET',
      credentials: 'include',
      headers: {
        ...(requestOptions.body ? { 'content-type': 'application/json' } : {}),
        ...(requestOptions.headers || {}),
      },
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
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
    verify: (body) => request('/api/frist/verify', { method: 'POST', body }),
    recharge: (body) => request('/api/frist/recharge', { method: 'POST', body }),
    redeem: (body) => request('/api/frist/redeem', { method: 'POST', body }),
    createKey: (body) => request('/api/frist/token', { method: 'POST', body }),
    setKeyEnabled: (id, body) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
    renameKey: (id, body) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
    deleteKey: (id) => request(`/api/frist/token/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    getImportUrl: ({ target, model }) => {
      const params = new URLSearchParams({ target, model });
      return request(`/api/frist/import-url?${params.toString()}`);
    },
    loadDashboard: () => request('/api/frist/dashboard'),
    chatCompletion: ({ apiKey, body }) => gatewayRequest('/v1/chat/completions', { apiKey, body }),
    generateImage: ({ apiKey, body }) => gatewayRequest('/v1/images/generations', { apiKey, body }),
  };
}

export function normalizeFristDashboard(payload, fallback) {
  const authenticated = Boolean(payload.authenticated);
  const account = payload.account || {};
  const user = payload.user || {};
  const apiKeys = Array.isArray(payload.apiKeys) ? payload.apiKeys : [];
  const channelChecks = Array.isArray(payload.channelChecks) ? payload.channelChecks : [];
  const modelUsage = Array.isArray(payload.modelUsage) ? payload.modelUsage : [];
  const accountFallback = authenticated ? fallback.accountSummary : guestAccountFallback(fallback.accountSummary);

  return {
    ...fallback,
    accountSummary: {
      ...accountFallback,
      userInitials: user.userInitials || accountFallback.userInitials,
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
      email: user.email || accountFallback.email || '',
      isAdmin: Boolean(user.isAdmin || accountFallback.isAdmin),
    },
    apiKeys: apiKeys.map((key) => ({
      id: key.id,
      name: key.name,
      secret: key.secret,
      preview: key.preview,
      enabled: Boolean(key.enabled),
      cost: key.cost || '¥0.00',
      tokens: key.tokens || '0.00M',
      lastUsed: key.lastUsed || '-',
      expiresAt: key.expiresAt || '-',
      modelGroup: key.modelGroup || 'All',
    })),
    modelUsage: modelUsage.length > 0 ? normalizeModelUsage(modelUsage) : zeroModelUsage(fallback.modelUsage),
    channelChecks: channelChecks.length > 0 ? normalizeChannelChecks(channelChecks, fallback.channelChecks) : fallback.channelChecks,
    modelCatalog: normalizeModelCatalog(payload.modelCatalog, fallback.modelCatalog),
  };
}

function guestAccountFallback(fallback = {}) {
  return {
    ...fallback,
    userInitials: 'FA',
    plan: '未登录',
    renewalDate: '-',
    balance: '¥0.00',
    todayCost: '¥0.00',
    monthCost: '¥0.00',
    quotaLeft: '¥0.00',
    packageQuota: '¥0.00',
    boosterQuota: '¥0.00',
    usageTotal: '¥0.00',
    todayCalls: '0 次',
  };
}

function normalizeModelUsage(rows) {
  const total = rows.reduce((sum, row) => sum + moneyToNumber(row.amount), 0) || 1;
  return rows.map((row) => {
    const amount = moneyToNumber(row.amount);
    return {
      model: row.model,
      amount: row.amount || '¥0.00',
      calls: row.calls || '1 次',
      tokens: row.tokens || '0.00M',
      percent: Math.max(4, Math.round((amount / total) * 100)),
    };
  });
}

function zeroModelUsage(rows) {
  return (rows || []).map((row) => ({
    ...row,
    amount: '¥0.00',
    calls: '0 次',
    tokens: '0.00M',
    percent: 0,
  }));
}

function normalizeChannelChecks(rows, fallbackRows) {
  return rows.map((row, index) => {
    const fallback = fallbackRows[index % Math.max(fallbackRows.length, 1)] || {};
    const ok = Boolean(row.ok);
    return {
      provider: row.provider || fallback.provider || 'Claude',
      channel: row.channel || `${row.provider || 'Claude'} 线路`,
      model: row.model || fallback.model || 'claude-haiku',
      endpoint: fallback.endpoint || '/v1/chat/completions',
      ok,
      maintenance: false,
      latencyMs: Number(row.latencyMs || fallback.latencyMs || 0),
      pingMs: Number(row.pingMs || fallback.pingMs || 0),
      checkedAt: row.checkedAt || new Date().toISOString(),
      officialStatus: ok ? '正常' : '不可用',
      availability: ok ? '99.9%' : '0%',
      successLabel: ok ? '最近可用' : '等待补充',
      history: ok ? ['ok', 'ok', 'ok', 'ok', 'ok', 'ok'] : ['down', 'down', 'down', 'down'],
    };
  });
}

function normalizeModelCatalog(rows, fallbackRows = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return fallbackRows;
  }
  return rows.map((row) => ({
    model: row.model || row.id || 'unknown',
    family: row.family || row.provider || 'Other',
    tagline: row.tagline || row.description || '当前可用',
    context: row.context || '按模型能力',
    price: row.price || row.billing || '按后台价格',
    available: row.available !== false,
  }));
}

function moneyToNumber(value) {
  const number = Number(String(value || '').replace(/[^\d.-]/g, ''));
  return Number.isFinite(number) ? number : 0;
}

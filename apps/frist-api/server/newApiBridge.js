import { modelMatchesGroup, normalizeBaseUrl, normalizeClientAvailableModels, normalizeModelGroup } from '../src/core.js';

const DEFAULT_QUOTA_PER_CNY = 500_000;
const DEFAULT_USD_TO_CNY = 7.2;
const TOKEN_STATUS_ENABLED = 1;
const TOKEN_STATUS_DISABLED = 2;
const TOKEN_STATUS_EXHAUSTED = 4;
const PAGE_SIZE = 100;
const MAX_TOKEN_PAGES = 100;
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;

export function createNewApiBridge(options = {}) {
  const config = normalizeBridgeConfig(options);
  if (!config.enabled) {
    return null;
  }

  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') {
    throw new Error('New-API 适配器需要 fetch 支持');
  }

  async function fetchWithTimeout(url, fetchOptions = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);
    try {
      return await fetchImpl(url, {
        ...fetchOptions,
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) {
        throw publicBridgeError(504, 'New-API 请求超时，请稍后重试');
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function request(path, requestOptions = {}) {
    const response = await fetchWithTimeout(`${config.baseUrl}${path}`, {
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

  async function listAllTokens() {
    const tokensById = new Map();
    for (let page = 1; page <= MAX_TOKEN_PAGES; page += 1) {
      const rows = unwrapArray(await request(`/api/token/?p=${page}&size=${PAGE_SIZE}`));
      for (const token of rows) {
        const tokenId = String(token.id || '').trim();
        if (!tokenId) {
          throw publicBridgeError(502, 'New-API 返回了缺少 ID 的 Token，已拒绝继续');
        }
        tokensById.set(tokenId, token);
      }
      if (rows.length < PAGE_SIZE) {
        return [...tokensById.values()];
      }
    }
    // 无法证明已经读到完整清单时，不能把未知历史 Token 误认成新客户资产。
    throw publicBridgeError(503, 'New-API Token 数量超过安全扫描上限，已拒绝创建新 Key');
  }

  return {
    config,
    async buildDashboard(localData, user, serverOptions) {
      // Token 清单决定客户资产视图，读取失败时必须显式报错，不能伪装成空账户。
      const tokenRows = (await listAllTokens()).filter((token) =>
        bridgeTokenOwnedBy(localData, user.id, token.id),
      );
      const [usage, topupInfo] = await Promise.allSettled([
        request(`/api/log/self?p=1&size=${PAGE_SIZE}`),
        request('/api/user/topup/info'),
      ]);
      const usageRows = filterBridgeUsageRows(unwrapArray(settledValue(usage)), tokenRows);
      const safeUser = {
        ...user,
        newApiMode: true,
      };
      return {
        authenticated: true,
        account: accountFromBridgeTokens(safeUser, tokenRows, usageRows),
        user: sanitizeBridgeUser(safeUser, {}),
        balanceAlert: sanitizeLocalBalanceAlert(user),
        apiKeys: tokenRows.map((token) => sanitizeBridgeToken(token)),
        modelUsage: buildBridgeModelUsage(usageRows),
        channelChecks: [],
        modelCatalog: [],
        rechargeOptions: buildBridgeRechargeOptions(localData, settledValue(topupInfo)),
        usageRecords: buildBridgeUsageRecords(usageRows),
        usageAnomalies: buildBridgeUsageAnomalies(usageRows, {
          quota: sum(tokenRows, (token) => numberFromAny(token.remain_quota ?? token.remaining_quota)),
        }),
        recentLogs: buildBridgeRecentLogs(usageRows),
      };
    },
    async syncUpstreamBalance() {
      const self = unwrapObject(await request('/api/user/self'));
      const remainingQuota = numberFromAny(self.quota ?? self.remain_quota ?? self.remaining_quota);
      const usedQuota = numberFromAny(self.used_quota ?? self.usedQuota);
      return {
        provider: 'New-API',
        userId: config.userId,
        username: String(self.username || self.display_name || '').slice(0, 80),
        emailMasked: maskEmail(self.email || ''),
        group: String(self.group || self.plan || self.plan_name || 'default').slice(0, 80),
        remainingQuota,
        usedQuota,
        remainingCny: quotaToCnyNumber(remainingQuota),
        usedCny: quotaToCnyNumber(usedQuota),
        remainingUsd: moneyNumber(remainingQuota),
      };
    },
    async createToken(body, createOptions = {}) {
      const beforeTokens = await listAllTokens();
      const beforeIds = new Set(beforeTokens.map((token) => String(token.id || '')).filter(Boolean));
      const modelInventory = await fetchNewApiModelInventory(request);
      const tokenPayload = tokenCreatePayload(body, config, modelInventory, createOptions);
      const createResult = unwrapObject(await request('/api/token/', { method: 'POST', body: tokenPayload }));
      const returnedId = String(createResult.id || '');
      if (returnedId && beforeIds.has(returnedId)) {
        throw publicBridgeError(502, 'New-API 返回了已存在的 Token ID，已拒绝覆盖客户归属');
      }
      let created = null;
      if (returnedId) {
        const persisted = unwrapObject(await request(`/api/token/${encodeURIComponent(returnedId)}`));
        if (String(persisted.id || '') !== returnedId || String(persisted.name || '') !== tokenPayload.name) {
          throw publicBridgeError(502, 'New-API 新 Key 校验失败，已拒绝建立客户归属');
        }
        assertTokenQuota(persisted, tokenPayload.remain_quota);
        created = persisted;
      } else {
        const afterTokens = await listAllTokens();
        const candidates = afterTokens.filter(
          (token) => String(token.name || '') === tokenPayload.name && !beforeIds.has(String(token.id || '')),
        );
        if (candidates.length !== 1) {
          throw publicBridgeError(502, 'New-API 未返回可唯一识别的新 Key，已拒绝建立错误归属');
        }
        [created] = candidates;
        assertTokenQuota(created, tokenPayload.remain_quota);
      }
      const keyPayload = created.id ? await request(`/api/token/${encodeURIComponent(created.id)}/key`, { method: 'POST' }) : {};
      const key = unwrapObject(keyPayload).key || created.key || '';
      if (!created.id || !key) {
        throw publicBridgeError(502, 'New-API 未返回完整的新 Key');
      }
      return { key: sanitizeBridgeToken({ ...created, key }, { revealSecret: true }) };
    },
    async activateTokenQuota(keyId, quotaUnits) {
      const safeQuota = Number(quotaUnits);
      if (!Number.isSafeInteger(safeQuota) || safeQuota <= 0) {
        throw publicBridgeError(503, 'New-API Key 激活额度无效');
      }
      const current = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      if (String(current.id || '') !== String(keyId)) {
        throw publicBridgeError(502, 'New-API Key 激活前 ID 校验失败');
      }
      const patch = {
        ...current,
        id: Number(current.id),
        name: String(current.name || '').trim().slice(0, 50),
        expired_time: normalizeExpiredTime(current.expired_time),
        remain_quota: safeQuota,
        unlimited_quota: false,
        model_limits_enabled: Boolean(current.model_limits_enabled),
        model_limits: current.model_limits || '',
        allow_ips: current.allow_ips || '',
        group: current.group || config.defaultGroup,
        cross_group_retry: Boolean(current.cross_group_retry),
      };
      if (!patch.name) {
        throw publicBridgeError(502, 'New-API Key 激活前名称为空');
      }
      await request('/api/token/', { method: 'PUT', body: patch });
      const latest = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      if (String(latest.id || '') !== String(keyId)) {
        throw publicBridgeError(502, 'New-API Key 激活后 ID 校验失败');
      }
      assertTokenQuota(latest, safeQuota);
      return { key: sanitizeBridgeToken(latest) };
    },
    async updateToken(keyId, body) {
      const current = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      const wantsStatusChange = Object.prototype.hasOwnProperty.call(body, 'enabled');
      const wantsMetadataChange = ['name', 'expiredTime', 'expired_time', 'remainQuota', 'remain_quota', 'unlimitedQuota', 'unlimited_quota'].some((key) =>
        Object.prototype.hasOwnProperty.call(body, key),
      );
      const patch = {
        ...current,
        id: Number(current.id || keyId),
        name: Object.prototype.hasOwnProperty.call(body, 'name') ? String(body.name || '').trim().slice(0, 50) : current.name,
        status: Object.prototype.hasOwnProperty.call(body, 'enabled')
          ? (body.enabled ? TOKEN_STATUS_ENABLED : TOKEN_STATUS_DISABLED)
          : Number(current.status || TOKEN_STATUS_ENABLED),
        expired_time: normalizeExpiredTime(current.expired_time),
        remain_quota: Number(current.remain_quota ?? cnyCentsToNewApiQuota(config.defaultTokenQuotaCents)),
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
      if (wantsMetadataChange) {
        await request('/api/token/', { method: 'PUT', body: patch });
      }
      if (wantsStatusChange) {
        // New-API 的普通 PUT 不会更新 status，必须使用官方前端同款 status_only 入口。
        await request('/api/token/?status_only=true', {
          method: 'PUT',
          body: { id: patch.id, status: patch.status },
        });
      }
      const latest = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      return { key: sanitizeBridgeToken({ ...patch, ...latest, status: wantsStatusChange ? patch.status : latest.status }, { revealSecret: true }) };
    },
    async deleteToken(keyId) {
      // New-API 前端删除 Token 使用带尾斜杠的资源路径；无尾斜杠在部分版本不会真正删除。
      await request(`/api/token/${encodeURIComponent(keyId)}/`, { method: 'DELETE' });
      let remaining;
      try {
        remaining = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      } catch (error) {
        if ([404, 410].includes(Number(error?.statusCode))) {
          return { deletedKeyId: String(keyId) };
        }
        throw publicBridgeError(502, '无法确认 New-API Key 已删除，已保留本地归属');
      }

      if (!bridgeTokenIdMatches(remaining, keyId)) {
        throw publicBridgeError(502, 'New-API 删除复验返回了错误 Key ID，已保留本地归属');
      }
      if (!bridgeTokenExplicitlyRevoked(remaining)) {
        const numericId = Number(remaining.id || keyId);
        if (!Number.isSafeInteger(numericId) || numericId <= 0) {
          throw publicBridgeError(502, 'New-API 删除复验返回了无效 Key ID，已保留本地归属');
        }
        await request('/api/token/?status_only=true', {
          method: 'PUT',
          body: { id: numericId, status: TOKEN_STATUS_DISABLED },
        });
        const disabled = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
        if (!bridgeTokenIdMatches(disabled, keyId) || !bridgeTokenExplicitlyRevoked(disabled)) {
          throw publicBridgeError(502, 'New-API Key 删除后没有明确撤销，已保留本地归属');
        }
      }
      return { deletedKeyId: String(keyId) };
    },
    async redeemCode(body) {
      const code = String(body.code || '').trim();
      if (!code) {
        throw publicBridgeError(400, '兑换码不能为空');
      }
      const redeemed = await request('/api/user/topup', { method: 'POST', body: { key: code } });
      return {
        newApiQuota: unwrapObject(redeemed),
      };
    },
    async buildImportUrl(requestUrl, keyId, buildUrl) {
      if (!keyId) {
        throw publicBridgeError(400, '请选择要导入的 API Key');
      }
      const key = unwrapObject(await request(`/api/token/${encodeURIComponent(keyId)}`));
      if (!key.id || !tokenEnabled(key.status ?? key.enabled)) {
        throw publicBridgeError(409, '所选 API Key 不可用');
      }
      const keyPayload = await request(`/api/token/${encodeURIComponent(key.id)}/key`, { method: 'POST' });
      const secret = unwrapObject(keyPayload).key || key.key || '';
      if (!secret) {
        throw publicBridgeError(409, 'New-API 未返回完整 API Key');
      }
      const modelGroup = normalizeBridgeModelGroup(key);
      // 参考 OpenAI Models API list（2026-07-02 复核）：New-API token 通配符只代表权限范围，不等同于真实健康 /v1/models 库存。
      const availableModels = normalizeClientAvailableModels(normalizeModelLimits(key), {
        modelGroup,
        expandPatterns: false,
      });
      if (!availableModels.length) {
        throw publicBridgeError(409, '暂无健康上游模型，请先在 New-API 渠道中补齐真实模型后再导入客户端');
      }
      const defaultModel = strongestBridgeModel(availableModels, requestUrl.searchParams.get('model') || '', modelGroup);
      return buildUrl({
        target: requestUrl.searchParams.get('target') || 'Claude',
        apiKey: secret,
        modelGroup,
        availableModels,
        defaultModel,
      });
    },
    async buildKeyUsage(clientRequest) {
      const secret = readBearerToken(clientRequest);
      if (!secret) {
        throw publicBridgeError(401, 'API Key 不可用');
      }
      const tokens = unwrapArray(await request(`/api/token/search?keyword=&token=${encodeURIComponent(secret)}&p=1&size=${PAGE_SIZE}`));
      const token = tokens.find((item) => {
        const key = String(item.key || item.token || '');
        return key === secret && tokenEnabled(item.status ?? item.enabled);
      });
      if (!token) {
        throw publicBridgeError(401, 'API Key 不可用');
      }
      const [usage] = await Promise.allSettled([
        request(`/api/log/self?p=1&size=${PAGE_SIZE}`),
      ]);
      const usageRows = filterBridgeUsageRows(unwrapArray(settledValue(usage)), [token]);
      const account = accountFromBridgeTokens({}, [token], usageRows);
      const remainingQuota = numberFromAny(token.remain_quota ?? token.remaining_quota);
      const usedQuota = numberFromAny(token.used_quota ?? token.usedQuota);
      return {
        ok: true,
        valid: true,
        keyPreview: maskBridgeKey(secret),
        plan: account.plan,
        renewalDate: account.renewalDate,
        remainingUsd: moneyNumber(remainingQuota),
        usedUsd: moneyNumber(usedQuota),
        totalUsd: moneyNumber(remainingQuota + usedQuota),
        balance: account.balance,
        todayCost: account.todayCost,
        monthCost: account.monthCost,
        todayCalls: account.todayCalls,
        todayTokens: account.todayTokens,
        totalTokens: account.totalTokens,
        averageLatency: account.averageLatency,
        successRate: account.successRate,
      };
    },
    async proxyGateway({ request, response, url, bodyText, localData }) {
      await requireAuthorizedGatewayToken(request, localData);
      const upstreamRequest = {
        method: request.method,
        headers: filterGatewayHeaders(request.headers),
      };
      if (!['GET', 'HEAD'].includes(String(request.method || '').toUpperCase())) {
        upstreamRequest.body = bodyText;
      }
      const upstream = await fetchWithTimeout(
        `${config.gatewayBaseUrl}${gatewayPath(url.pathname)}`,
        upstreamRequest,
      );
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

  async function requireAuthorizedGatewayToken(clientRequest, localData) {
    const secret = readBearerToken(clientRequest);
    if (!secret) {
      throw publicBridgeError(401, 'API Key 不可用');
    }
    const matches = unwrapArray(
      await request(`/api/token/search?keyword=&token=${encodeURIComponent(secret)}&p=1&size=${PAGE_SIZE}`),
    ).filter((item) => String(item.key || item.token || '') === secret);
    if (matches.length !== 1) {
      throw publicBridgeError(401, 'API Key 不可用');
    }
    const tokenId = String(matches[0].id || '').trim();
    const owner = localData?.newApiTokenOwners?.[tokenId];
    if (!tokenId || !validGatewayOwner(localData, owner)) {
      throw publicBridgeError(401, 'API Key 不可用');
    }
    const token = unwrapObject(await request(`/api/token/${encodeURIComponent(tokenId)}`));
    const remainingQuota = numberFromAny(token.remain_quota ?? token.remaining_quota ?? token.quota);
    if (
      String(token.id || '') !== tokenId ||
      !tokenEnabled(token.status ?? token.enabled) ||
      !tokenExplicitlyFinite(token) ||
      remainingQuota <= 0
    ) {
      throw publicBridgeError(401, 'API Key 不可用');
    }
    return token;
  }
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
  const requestTimeoutMs = Number(
    options.newApiRequestTimeoutMs ?? process.env.FRIST_API_NEWAPI_REQUEST_TIMEOUT_MS ?? DEFAULT_REQUEST_TIMEOUT_MS,
  );
  return {
    enabled,
    baseUrl,
    gatewayBaseUrl: normalizeBaseUrl(options.newApiGatewayBaseUrl || process.env.FRIST_API_NEWAPI_GATEWAY_BASE_URL || `${baseUrl}/v1`),
    accessToken: /^Bearer\s+/i.test(accessToken) ? accessToken : `Bearer ${accessToken}`,
    userId,
    sqliteDb: String(options.newApiSqliteDb || process.env.FRIST_API_NEWAPI_SQLITE_DB || '').trim(),
    defaultTokenQuotaCents: Number(
      options.newApiDefaultTokenQuota ?? process.env.FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA ?? 0,
    ),
    defaultGroup: String(options.newApiDefaultGroup || process.env.FRIST_API_NEWAPI_DEFAULT_GROUP || 'default'),
    requestTimeoutMs: Number.isFinite(requestTimeoutMs)
      ? Math.max(1000, requestTimeoutMs)
      : DEFAULT_REQUEST_TIMEOUT_MS,
  };
}

function booleanOption(value, envValue) {
  if (typeof value === 'boolean') return value;
  return String(envValue || '') === '1';
}

async function fetchNewApiModelInventory(request) {
  try {
    return extractNewApiModelNames(await request('/api/models/?page_size=1000'));
  } catch {
    return [];
  }
}

function extractNewApiModelNames(payload) {
  return uniqueStrings(
    unwrapArray(payload)
      .map((item) => String(item.model_name || item.id || item.name || item.model || '').trim())
      .filter(Boolean),
  );
}

function tokenCreatePayload(body, config, modelInventory = [], options = {}) {
  const modelGroup = normalizeModelGroup(body.modelGroup);
  const modelLimits = modelLimitsForGroup(modelGroup, modelInventory);
  const requestedQuota = body.remainQuota ?? body.remain_quota;
  const remainQuota = Number(
    requestedQuota === undefined
      ? cnyCentsToNewApiQuota(config.defaultTokenQuotaCents)
      : requestedQuota,
  );
  if (!Number.isFinite(remainQuota) || remainQuota < 0 || (!options.allowZeroQuota && remainQuota === 0)) {
    throw publicBridgeError(503, 'New-API 默认 Key 额度未配置，已拒绝创建无限额度 Key');
  }
  return {
    name: String(body.name || `CC Key ${Date.now()}`).trim().slice(0, 50),
    expired_time: normalizeExpiredTime(body.expiredTime ?? body.expired_time),
    remain_quota: remainQuota,
    unlimited_quota: false,
    model_limits_enabled: modelLimits.length > 0,
    model_limits: modelLimits.join(','),
    allow_ips: '',
    group: config.defaultGroup,
    cross_group_retry: true,
  };
}

function bridgeTokenOwnedBy(localData, userId, tokenId) {
  const owner = localData?.newApiTokenOwners?.[String(tokenId)];
  const ownerId = typeof owner === 'string' ? owner : owner?.userId;
  return Boolean(ownerId && ownerId === userId);
}

function filterBridgeUsageRows(rows, tokens) {
  const tokenIds = new Set(tokens.map((token) => String(token.id || '')).filter(Boolean));
  return rows.filter((row) => {
    const rowTokenId = String(row.token_id ?? row.tokenId ?? row.token?.id ?? '').trim();
    // Token 名称可被不同客户重复使用；没有明确 Token ID 的日志宁可不展示，也不能猜归属。
    return Boolean(rowTokenId && tokenIds.has(rowTokenId));
  });
}

function accountFromBridgeTokens(localUser, tokens, usageRows) {
  const unallocatedQuota = cnyCentsToNewApiQuota(
    numberFromAny(
      localUser.balanceCents ??
        (numberFromAny(localUser.packageQuotaCents) + numberFromAny(localUser.boosterQuotaCents)),
    ),
  );
  const remainingQuota = unallocatedQuota + sum(
    tokens,
    (token) => numberFromAny(token.remain_quota ?? token.remaining_quota ?? token.quota),
  );
  const usedQuota = sum(tokens, (token) => numberFromAny(token.used_quota ?? token.usedQuota));
  return accountFromNewApi(
    {
      group: localUser.plan || 'New-API',
      expired_time: localUser.planExpiresAt || localUser.renewalDate || '',
      quota: remainingQuota,
      used_quota: usedQuota,
      request_count: usageRows.length,
    },
    usageRows,
    {},
    [],
  );
}

function modelLimitsForGroup(group, modelInventory = []) {
  const normalized = normalizeModelGroup(group);
  const inventoryLimits = normalizeClientAvailableModels(modelInventory, {
    modelGroup: normalized,
    expandPatterns: false,
  }).filter((model) => model && !model.includes('*') && modelMatchesGroup(model, normalized));
  if (inventoryLimits.length > 0) {
    return inventoryLimits;
  }
  // New-API 网关不按 OpenAI 风格通配符授权，生产 Key 必须写入精确模型名。
  if (normalized === 'Claude') {
    return [
      'claude-haiku-4-5-20251001',
      'claude-sonnet-4-5-20250929',
      'claude-sonnet-4-6',
      'claude-sonnet-5',
      'claude-opus-4-6',
      'claude-opus-4-7',
      'claude-opus-4-8',
      'claude-fable-5',
      'claude-opus-4-6-thinking-c',
      'claude-opus-4-6-c',
      'claude-sonnet-4-5-c',
    ];
  }
  if (normalized === 'OpenAI') {
    return [
      'gpt-5.3-codex-spark',
      'gpt-5.4-mini',
      'gpt-5.4',
      'gpt-5.5',
      'gpt-image-1',
      'gpt-image-1.5',
      'gpt-image-2',
      'gpt-5.3-codex',
      'gpt-5-codex',
      'gpt-4o',
    ];
  }
  if (normalized === 'Gemini') return ['gemini-2.5-flash', 'gemini-2.0-flash'];
  if (normalized === 'DeepSeek') return ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'];
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
  const displayName = String(localUser.displayName || localUser.nickname || self.username || self.display_name || '').trim();
  return {
    id: localUser.id,
    email,
    emailMasked: maskEmail(email),
    displayName: displayName || email.split('@')[0] || 'Frist',
    emailVerified: Boolean(localUser.emailVerified),
    isAdmin: Boolean(localUser.isAdmin),
    plan: String(self.group || localUser.plan || 'New-API'),
    renewalDate: formatDate(self.expired_time ?? self.subscription_expires_at) || localUser.renewalDate,
    userInitials: initialsFrom(displayName || email),
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
    client: clientLabelFromNewApiRow(row),
    tokens: compactTokenText(tokenTotalFromRow(row)),
    amount: formatMoney(row.quota ?? row.used_quota ?? row.cost),
    amountCny: `¥${formatQuota(row.quota ?? row.used_quota ?? row.cost)}`,
    latency: numberFromAny(row.use_time ?? row.latency_ms ?? row.response_time_ms)
      ? `${Math.round(numberFromAny(row.use_time ?? row.latency_ms ?? row.response_time_ms))}ms`
      : '-',
    status: row.is_error || row.status === 'failed' ? 'failed' : 'success',
    at: formatDateTime(row.created_at ?? row.created_time ?? row.time),
  }));
}

function buildBridgeUsageAnomalies(rows, rawSelf = {}) {
  const self = unwrapObject(rawSelf);
  const todayRows = rowsForToday(rows);
  const todayQuota = sum(todayRows, (row) => numberFromAny(row.quota ?? row.used_quota ?? row.cost));
  const remainingQuota = numberFromAny(self.quota ?? self.remain_quota ?? self.remaining_quota);
  const largestRow = [...todayRows].sort(
    (left, right) =>
      numberFromAny(right.quota ?? right.used_quota ?? right.cost) -
      numberFromAny(left.quota ?? left.used_quota ?? left.cost),
  )[0];
  const largestQuota = largestRow ? numberFromAny(largestRow.quota ?? largestRow.used_quota ?? largestRow.cost) : 0;
  const rowsOut = [];

  if (todayQuota > 0 && remainingQuota > 0 && todayQuota >= remainingQuota * 0.5) {
    rowsOut.push({
      id: 'newapi-today-spend-balance-ratio',
      severity: todayQuota >= remainingQuota ? 'critical' : 'warning',
      title: '今日消耗偏高',
      detail: `今日已用 ${formatMoney(todayQuota)}，接近当前剩余额度 ${formatMoney(remainingQuota)}。`,
      action: '建议检查 New-API 日志和 Key 使用方',
      at: formatDateTime(largestRow?.created_at ?? largestRow?.created_time ?? largestRow?.time),
    });
  }

  if (largestQuota > 0 && largestQuota >= Math.max(5, todayQuota * 0.6)) {
    rowsOut.push({
      id: 'newapi-single-call-cost-spike',
      severity: largestQuota >= Math.max(20, todayQuota * 0.8) ? 'critical' : 'warning',
      title: '单次调用费用突增',
      detail: `${largestRow?.model_name || largestRow?.model || '模型'} 单次消耗 ${formatMoney(largestQuota)}。`,
      action: '建议核对上下文长度、图片请求和调用客户端',
      at: formatDateTime(largestRow?.created_at ?? largestRow?.created_time ?? largestRow?.time),
    });
  }

  return rowsOut.slice(0, 4);
}

function buildBridgeRecentLogs(rows, meta = {}) {
  const logs = buildBridgeUsageRecords(rows).slice(0, 5).map((row) => ({
    type: 'newapi_usage',
    at: row.at,
    detail: `${row.model} · ${row.amount} · ${row.client}`,
  }));
  if (meta.subscriptions) {
    logs.push({ type: 'newapi_subscription', at: '', detail: '订阅已同步' });
  }
  if (meta.affiliate) {
    logs.push({ type: 'newapi_affiliate', at: '', detail: '邀请已同步' });
  }
  return logs.slice(0, 5);
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

function strongestBridgeModel(models, requested) {
  const cleaned = models.filter((model) => !model.includes('*'));
  const normalizedRequested = normalizeClientAvailableModels([requested], { expandPatterns: false })[0] || '';
  if (normalizedRequested && cleaned.includes(normalizedRequested)) return normalizedRequested;
  return cleaned[0] || '';
}

function tokenEnabled(status) {
  return [TOKEN_STATUS_ENABLED, true, '1', 'enabled', 'active', 'normal'].includes(status);
}

function tokenExplicitlyFinite(token) {
  const unlimited = token?.unlimited_quota ?? token?.unlimitedQuota;
  return [false, 0, '0', 'false'].includes(
    typeof unlimited === 'string' ? unlimited.toLowerCase() : unlimited,
  );
}

function validGatewayOwner(localData, owner) {
  if (!owner || typeof owner !== 'object' || Array.isArray(owner) || owner.state !== 'active') {
    return false;
  }
  const userId = String(owner.userId || '').trim();
  const matchingUsers = Array.isArray(localData?.users)
    ? localData.users.filter((user) => String(user?.id || '') === userId)
    : [];
  if (!userId || matchingUsers.length !== 1) {
    return false;
  }
  const upstreamQuotaUnits = Number(owner.upstreamQuotaUnits);
  if (!Number.isSafeInteger(upstreamQuotaUnits) || upstreamQuotaUnits <= 0) {
    return false;
  }
  if (owner.source === 'explicit_manual_mapping') {
    return Boolean(String(owner.mappingReason || '').trim() && Date.parse(owner.finiteVerifiedAt || ''));
  }
  const allocatedCents = Number(owner.allocatedCents);
  return Number.isSafeInteger(allocatedCents) && allocatedCents > 0;
}

function bridgeTokenIdMatches(token, expectedId) {
  return Boolean(token?.id) && String(token.id) === String(expectedId);
}

function bridgeTokenExplicitlyRevoked(token) {
  if (token?.enabled === false) return true;
  const status = token?.status;
  return [
    TOKEN_STATUS_DISABLED,
    TOKEN_STATUS_EXHAUSTED,
    3,
    '2',
    '3',
    '4',
    'disabled',
    'exhausted',
    'expired',
    'deleted',
    'revoked',
    'inactive',
  ].includes(typeof status === 'string' ? status.toLowerCase() : status);
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

function readBearerToken(request) {
  const authorization = request.headers.authorization || '';
  const xApiKey = request.headers['x-api-key'] || request.headers['anthropic-auth-token'] || '';
  return authorization.match(/^Bearer\s+(.+)$/i)?.[1] || String(xApiKey || '').trim();
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

function cnyCentsToNewApiQuota(cents) {
  return Math.max(0, Math.round((numberFromAny(cents) / 100) * DEFAULT_QUOTA_PER_CNY));
}

function assertTokenQuota(token, expectedQuota) {
  const actualQuota = numberFromAny(token.remain_quota ?? token.remaining_quota ?? token.quota);
  if (actualQuota !== Number(expectedQuota) || Boolean(token.unlimited_quota)) {
    throw publicBridgeError(502, 'New-API Key 额度校验失败');
  }
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

function moneyNumber(quota) {
  return Math.round((numberFromAny(quota) / DEFAULT_QUOTA_PER_CNY / DEFAULT_USD_TO_CNY) * 100) / 100;
}

function quotaToCnyNumber(quota) {
  return Math.round((numberFromAny(quota) / DEFAULT_QUOTA_PER_CNY) * 100) / 100;
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
  const prefix = /^sk-/i.test(key)
    ? 'sk'
    : /^fk-live-/i.test(key)
      ? 'fk-live'
      : key.slice(0, Math.min(6, key.length)).replace(/-$/, '') || 'key';
  return `${prefix}-••••••${key.slice(-4)}`;
}

function maskEmail(value) {
  const email = String(value || '');
  const [name = '', domain = ''] = email.split('@');
  if (!name || !domain) return email;
  return `${name.slice(0, 2)}***@${domain}`;
}

function clientLabelFromNewApiRow(row) {
  const text = String(row.metadata?.frist_session_id || row.metadata || row.user_agent || row.channel || row.request_id || '').toLowerCase();
  if (text.includes('playground') || text.includes('connectivity') || text.includes('square')) return '广场';
  if (text.includes('mac') || text.includes('darwin')) return 'MacBook';
  if (text.includes('windows') || text.includes('pc')) return 'PC';
  if (text.includes('codex')) return 'Codex';
  if (text.includes('claude')) return 'Claude';
  return 'API';
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

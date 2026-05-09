import { createCipheriv, createDecipheriv, createHash, createHmac, pbkdf2Sync, randomBytes, timingSafeEqual } from 'node:crypto';
import { lookup as lookupDns } from 'node:dns/promises';
import { createServer } from 'node:http';
import { mkdir, open, readFile, rename, rm, stat } from 'node:fs/promises';
import { connect as connectNet, isIP } from 'node:net';
import { basename, dirname, extname, join, normalize, relative, resolve } from 'node:path';
import { connect as connectTls } from 'node:tls';
import { fileURLToPath } from 'node:url';

import { createNewApiBridge } from './newApiBridge.js';
import {
  createProviderPayment,
  parseAlipayNotification,
  paymentConfigFromOptions,
  providerReady,
  verifyWechatNotification,
} from './payments.js';
import {
  buildClientConfig,
  buildClientSetupCommands,
  inferProviderGroup,
  modelMatchesGroup,
  normalizeBaseUrl,
  normalizeClientAvailableModels,
  normalizeModelGroup,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  parsePriceText,
  parseSupplierOrderText,
  poolPriority,
  recommendConnectionPath,
} from '../src/core.js';

const DEFAULT_MODEL = 'claude-opus-4-6-thinking-c';
const DEFAULT_PUBLIC_MODEL = 'gpt-5.5';
const DEFAULT_USD_TO_CNY = 7.2;
const DISPLAY_USD_TO_CNY = DEFAULT_USD_TO_CNY;
const DEFAULT_PROBE_MODELS = Object.freeze([
  'claude-opus-4-6-thinking-c', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c',
  'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2', 'gpt-5.3-codex', 'gemini-2.5-flash',
  'deepseek-v4-flash', 'deepseek-v4-pro',
]);
const DEFAULT_QUOTA_COST = 10;
const PRIMARY_SOURCE_TYPE = 'authorized';
const BACKUP_SOURCE_TYPES = new Set(['cpa_json_backup', 'chong_backup', 'manual_backup']);
const PLUS_ACCOUNT_STATUSES = new Set(['warming', 'active', 'renewal_due', 'paused', 'risk_hold', 'retired']);
const PLUS_ACCOUNT_COMPLIANCE_STATUSES = new Set(['self_use_only', 'needs_review', 'blocked']);
const PLUS_ACCOUNT_REGIONS = new Set(['Türkiye', 'United States', 'China', 'Other']);
const RT_ACCOUNT_STATUSES = new Set(['ready_for_refresh', 'active', 'needs_refresh', 'blocked', 'retired']);
const RT_ACCOUNT_PLATFORMS = new Set(['codex', 'openai', 'claude', 'gemini', 'other']);
const DEFAULT_RECHARGE_PLANS = Object.freeze([
  Object.freeze({ id: 'codex-30-day', label: 'Codex API 30刀额度/日卡', quotaUsd: 30, priceCny: 5.88, durationDays: 1, plan: 'day' }),
  Object.freeze({ id: 'codex-30-unlimited', label: 'Codex API 30刀额度/不限时', quotaUsd: 30, priceCny: 8.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-100-unlimited', label: 'Codex API 100刀额度/不限时', quotaUsd: 100, priceCny: 28.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-500-unlimited', label: 'Codex API 500刀额度/不限时', quotaUsd: 500, priceCny: 68.88, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'codex-1000-unlimited', label: 'Codex API 1000刀额度/不限时', quotaUsd: 1000, priceCny: 118.88, durationDays: 0, plan: 'balance' }),
]);
const DEFAULT_CARD_BATCH_PREFIX = 'FRIST';
const DEFAULT_MODEL_PRICES = Object.freeze([
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
const DEFAULT_MODEL_PRICE_BY_MODEL = new Map(
  DEFAULT_MODEL_PRICES.map((price) => [normalizeOfficialModelName(price.model), price]),
);
const DEFAULT_MODEL_CATALOG = [
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
const SESSION_COOKIE = 'frist_session';
const CSRF_COOKIE = 'frist_csrf';
const ADMIN_2FA_COOKIE = 'frist_admin_2fa';
const TOTP_STEP_SECONDS = 30;
const TOTP_DIGITS = 6;
const DEFAULT_SLA_RETENTION_DAYS = 30;
const LEGACY_CARD_CODES = new Map([
  ['FRIST-DAY-001', { label: 'Codex API 30刀额度/日卡', plan: 'day', days: 1, packageCents: 800, quotaUsd: 30, priceCny: 5.88 }],
  ['FRIST-MONTH-001', { label: 'Codex API 月卡 Pro', plan: 'month', days: 30, packageCents: 8000, quotaUsd: 300, priceCny: 58.88 }],
  ['FRIST-BOOST-100', { label: 'Codex API 100刀加油包', plan: 'balance', days: 0, boosterCents: 10000, quotaUsd: 100, priceCny: 28.88 }],
]);
const CONTENT_TYPES = new Map([
  ['.css', 'text/css; charset=utf-8'], ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'], ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml; charset=utf-8'],
]);
const ROOT_GATEWAY_PATHS = new Set([
  '/chat/completions', '/openai/chat/completions', '/responses', '/openai/responses',
  '/images/generations', '/openai/images/generations', '/messages',
]);
const DEFAULT_CANONICAL_HOST = 'frist-api.101-43-41-96.nip.io';
const DEFAULT_REDIRECT_HOSTS = Object.freeze(['101-43-41-96.nip.io']);
const DEFAULT_CHANNEL_MONITOR_INTERVAL_MS = 60_000;
const DEFAULT_CHANNEL_MONITOR_BATCH_SIZE = 4;
const DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS = 55_000;

export function createFristApiServer(options = {}) {
  const serverOptions = normalizeServerOptions(options);
  const newApiBridge = createNewApiBridge(serverOptions);
  const store = createRuntimeStore(serverOptions.dataFile, serverOptions.dataEncryptionKey);
  const securityState = createSecurityState();
  let stopChannelMonitor = null;

  const server = createServer(async (request, response) => {
    try {
      if (request.method === 'OPTIONS') {
        writeNoContent(response);
        return;
      }

      const url = new URL(request.url || '/', requestOrigin(request));
      if (redirectToCanonicalHost({ request, response, url, serverOptions })) {
        return;
      }
      if (url.pathname.startsWith('/api/frist/')) {
        await handleCustomerApi({ request, response, url, store, serverOptions, securityState, newApiBridge });
        return;
      }
      if (url.pathname.startsWith('/api/admin/')) {
        await handleAdminApi({ request, response, url, store, serverOptions });
        return;
      }
      if (url.pathname.startsWith('/v1/') || ROOT_GATEWAY_PATHS.has(url.pathname)) {
        await handleGatewayApi({ request, response, url, store, serverOptions, newApiBridge });
        return;
      }

      await serveStaticFile({ request, response, url, publicDir: serverOptions.publicDir, serverOptions, store });
    } catch (error) {
      const url = new URL(request.url || '/', requestOrigin(request));
      if (url.pathname.startsWith('/api/admin/') && error?.statusCode === 401) {
        await recordAdminAuthFailure(store, request, url);
      }
      const message = error.expose ? error.message : '服务暂时不可用';
      writeJson(response, error.statusCode || 500, { error: message });
    }
  });
  if (Number.isFinite(serverOptions.keepAliveTimeoutMs)) {
    server.keepAliveTimeout = Number(serverOptions.keepAliveTimeoutMs);
  }
  if (serverOptions.channelMonitorEnabled) {
    server.on('listening', () => {
      if (stopChannelMonitor) {
        stopChannelMonitor();
      }
      stopChannelMonitor = startChannelMonitor({ store, serverOptions });
    });
    server.on('close', () => {
      if (stopChannelMonitor) {
        stopChannelMonitor();
        stopChannelMonitor = null;
      }
    });
  }
  return server;
}

async function handleCustomerApi({ request, response, url, store, serverOptions, securityState, newApiBridge }) {
  if (request.method === 'GET' && url.pathname === '/api/frist/challenge') {
    assertAuthRateLimit(securityState, request, serverOptions);
    writeJson(response, 200, createCaptchaChallenge(securityState, serverOptions));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/register') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    requireCaptchaIfEnabled(securityState, body, serverOptions);
    const result = await store.mutate((data) => registerCustomer(data, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': sessionCookies(result.sessionToken, result.csrfToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/login') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    const result = await store.mutate((data) => loginCustomer(data, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': sessionCookies(result.sessionToken, result.csrfToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return changeCustomerPassword(data, request, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password-reset/request') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    const result = await store.mutate((data) => requestCustomerPasswordReset(data, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password-reset/confirm') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    const result = await store.mutate((data) => confirmCustomerPasswordReset(data, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/verify') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return verifyCustomer(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'PATCH' && url.pathname === '/api/frist/profile') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerProfile(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'PUT' && url.pathname === '/api/frist/balance-alert') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerBalanceAlert(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/balance-alert/test') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return sendCustomerBalanceAlertTest(data, request, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/recharge') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return rechargeCustomer(data, request, body, serverOptions);
    });
    writeJson(response, result.status || 200, result.body || result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/payments/wechat/notify') {
    const rawBody = await readRequestText(request);
    const result = await store.mutate((data) =>
      handleWechatPaymentNotification(data, request, rawBody, serverOptions),
    );
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/payments/alipay/notify') {
    const rawBody = await readRequestText(request);
    const result = await store.mutate((data) =>
      handleAlipayPaymentNotification(data, rawBody, serverOptions),
    );
    response.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    response.end(result.ok ? 'success' : 'fail');
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/redeem') {
    const body = await readJsonBody(request);
    if (newApiBridge) {
      const data = await store.load();
      requireCsrfIfEnabled(data, request, serverOptions);
      const { user } = requireSession(data, request);
      const result = await newApiBridge.redeemCode(body);
      result.user = sanitizeUser(user);
      writeJson(response, 200, result);
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return redeemCustomerCode(data, request, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/token') {
    const body = await readJsonBody(request);
    if (newApiBridge) {
      const data = await store.load();
      requireCsrfIfEnabled(data, request, serverOptions);
      const { user } = requireSession(data, request);
      if (serverOptions.requireEmailVerification && !user.emailVerified) {
        throw publicError(403, '请先完成邮箱验证');
      }
      writeJson(response, 200, await newApiBridge.createToken(body));
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return createCustomerToken(data, request, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  const tokenMatch = url.pathname.match(/^\/api\/frist\/token\/([^/]+)$/);
  if (request.method === 'PATCH' && tokenMatch) {
    const body = await readJsonBody(request);
    if (newApiBridge) {
      const data = await store.load();
      requireCsrfIfEnabled(data, request, serverOptions);
      requireSession(data, request);
      writeJson(response, 200, await newApiBridge.updateToken(tokenMatch[1], body));
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerToken(data, request, tokenMatch[1], body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'DELETE' && tokenMatch) {
    if (newApiBridge) {
      const data = await store.load();
      requireCsrfIfEnabled(data, request, serverOptions);
      requireSession(data, request);
      writeJson(response, 200, await newApiBridge.deleteToken(tokenMatch[1]));
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return deleteCustomerToken(data, request, tokenMatch[1]);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/import-url') {
    const data = await store.load();
    if (newApiBridge) {
      const { user } = requireSession(data, request);
      const result = await newApiBridge.buildImportUrl(url, ({ target, apiKey, modelGroup, availableModels, defaultModel }) => {
        const baseUrl = serverOptions.publicGatewayBaseUrl || `${requestOrigin(request)}/v1`;
        const requestedModel = url.searchParams.get('model') || '';
        const config = buildClientConfig({
          target,
          apiKey,
          baseUrl,
          model: requestedModel || defaultModel,
          defaultModel,
          availableModels,
          modelGroup,
          planExpiresAt: user.planExpiresAt,
          preferExplicitDefaultModel: Boolean(requestedModel || defaultModel),
        });
        const setup = buildClientSetupCommands(config);
        return {
          url: config.ccSwitchUrl,
          config,
          setup,
          defaultModel,
          availableModels,
        };
      });
      writeJson(response, 200, result);
      return;
    }
    const result = buildCustomerImportUrl(data, request, url, serverOptions);
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/key-usage') {
    const data = await store.load();
    if (newApiBridge) {
      writeJson(response, 200, await newApiBridge.buildKeyUsage(request), {
        'cache-control': 'no-store',
      });
      return;
    }
    writeJson(response, 200, buildKeyUsagePayload(data, request, serverOptions), {
      'cache-control': 'no-store',
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/dashboard') {
    const data = await store.load();
    const { user } = findSession(data, request);
    if (user && newApiBridge) {
      writeJson(response, 200, await newApiBridge.buildDashboard(data, user, serverOptions));
      return;
    }
    writeJson(response, 200, user ? buildDashboard(data, user, serverOptions) : buildGuestDashboard(data));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/admin/claim') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return claimAdminIdentity(data, request, body, serverOptions);
    });
    writeJson(response, 200, result, adminGateCookie(serverOptions));
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function handleAdminApi({ request, response, url, store, serverOptions }) {
  if (request.method === 'POST' && url.pathname === '/api/admin/2fa/verify') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => verifyAdminSecondFactor(data, request, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': adminSecondFactorCookie(result.sessionToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/production-readiness') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, await buildProductionReadiness(data, serverOptions));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/backups/status') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return recordBackupStatus(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/pricing') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, pricingPayload(data));
    return;
  }

  if (request.method === 'PUT' && url.pathname === '/api/admin/pricing') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      data.pricing = normalizePricingConfig(body);
      data.priceDrafts = mergeModelPrices(data.priceDrafts, data.pricing.modelPrices);
      data.events.unshift({
        type: 'pricing_updated',
        detail: `套餐 ${data.pricing.rechargePlans.length} 个，模型价格 ${data.pricing.modelPrices.length} 个`,
        at: new Date().toISOString(),
      });
      return pricingPayload(data);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/replenishments') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      credentials: data.credentials.map(sanitizeCredential),
      supplierProfiles: data.supplierProfiles,
      priceDrafts: data.priceDrafts,
      paymentOrders: data.paymentOrders.map(sanitizePaymentOrder),
      redemptionCards: data.redemptionCards.map(sanitizeRedemptionCard),
      plusAccounts: data.plusAccounts.map((account) => sanitizePlusAccount(account, serverOptions)),
      plusAccountSummary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
      rtAccounts: data.rtAccounts.map(sanitizeRtAccount),
      rtAccountSummary: buildRtAccountSummary(data.rtAccounts),
      inventorySummary: buildInventorySummary(data),
      productionReadiness: await buildProductionReadiness(data, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/plus-accounts') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      accounts: data.plusAccounts.map((account) => sanitizePlusAccount(account, serverOptions)),
      summary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/plus-accounts') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return upsertPlusAccount(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/rt-accounts') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      accounts: data.rtAccounts.map(sanitizeRtAccount),
      summary: buildRtAccountSummary(data.rtAccounts),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/rt-accounts/import') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return importRtAccounts(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/redemption-cards') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      cards: data.redemptionCards.map(sanitizeRedemptionCard),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/redemption-cards') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return createRedemptionCards(data, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments/parse-order') {
    const body = await readJsonBody(request);
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
    const parsed = parseSupplierOrderText(body.orderText || '', body.pricing || {});
    writeJson(response, 200, sanitizeParsedOrder(parsed));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/customers/recharge') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return manualRechargeCustomer(data, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/customers/password') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return adminResetCustomerPassword(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return replenishCredentials(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function recordAdminAuthFailure(store, request, url) {
  try {
    await store.mutate((data) => {
      data.events.push({
        type: 'admin_auth_failed',
        path: url.pathname,
        ipHash: hashId(clientIp(request)),
        at: new Date().toISOString(),
      });
    });
  } catch (error) {
    process.emitWarning(`Frist-API 管理认证失败审计写入失败: ${error.message}`, {
      code: 'FRIST_API_ADMIN_AUDIT_WRITE_FAILED',
    });
  }
}

async function handleGatewayApi({ request, response, url, store, serverOptions, newApiBridge }) {
  if (newApiBridge && serverOptions.newApiGatewayEnabled && request.method === 'POST') {
    if (![
      '/v1/chat/completions',
      '/v1/openai/chat/completions',
      '/chat/completions',
      '/openai/chat/completions',
      '/v1/responses',
      '/v1/openai/responses',
      '/responses',
      '/openai/responses',
      '/v1/images/generations',
      '/v1/openai/images/generations',
      '/images/generations',
      '/openai/images/generations',
      '/v1/messages',
      '/messages',
    ].includes(url.pathname)) {
      writeJson(response, 404, { error: '接口不存在' });
      return;
    }
    const bodyText = await readRequestText(request);
    if (await newApiBridge.proxyGateway({ request, response, url, bodyText })) {
      return;
    }
  }

  if (request.method === 'GET' && url.pathname === '/v1/models') {
    const data = await store.load();
    const result = buildGatewayModels(data, request);
    writeJson(response, 200, result);
    return;
  }

  const chatCompletionRouteOptions = {
    upstreamAttempts: [
      { upstreamPath: '/chat/completions' },
      {
        upstreamPath: '/responses',
        transformRequest: chatCompletionRequestToResponses,
        transformResponse: responsesToChatCompletionResponse,
      },
    ],
  };
  const responsesRouteOptions = {
    upstreamAttempts: [
      { upstreamPath: '/responses' },
      {
        upstreamPath: '/chat/completions',
        transformRequest: responsesRequestToChatCompletion,
        transformResponse: chatCompletionToResponsesResponse,
      },
    ],
  };
  const anthropicMessagesRouteOptions = {
    upstreamAttempts: [
      {
        upstreamPath: '/messages',
        validateResponse: isAnthropicMessagePayload,
      },
      {
        upstreamPath: '/chat/completions',
        transformRequest: anthropicMessagesToChatCompletion,
        transformResponse: chatCompletionToAnthropicMessageResponse,
      },
    ],
  };

  const upstreamPathByRoute = new Map([
    ['/v1/chat/completions', chatCompletionRouteOptions],
    ['/v1/openai/chat/completions', chatCompletionRouteOptions],
    ['/chat/completions', chatCompletionRouteOptions],
    ['/openai/chat/completions', chatCompletionRouteOptions],
    ['/v1/responses', responsesRouteOptions],
    ['/v1/openai/responses', responsesRouteOptions],
    ['/responses', responsesRouteOptions],
    ['/openai/responses', responsesRouteOptions],
    ['/v1/images/generations', { upstreamPath: '/images/generations' }],
    ['/v1/openai/images/generations', { upstreamPath: '/images/generations' }],
    ['/images/generations', { upstreamPath: '/images/generations' }],
    ['/openai/images/generations', { upstreamPath: '/images/generations' }],
    ['/v1/messages', anthropicMessagesRouteOptions],
    ['/messages', anthropicMessagesRouteOptions],
  ]);
  const routeOptions = upstreamPathByRoute.get(url.pathname);
  if (request.method !== 'POST' || !routeOptions) {
    writeJson(response, 404, { error: '接口不存在' });
    return;
  }

  const body = await readJsonBody(request);
  const result = await store.mutate((data) =>
    routeChatCompletion(data, request, body, serverOptions, { ...routeOptions, request }),
  );
  response.writeHead(result.status, {
    'content-type': result.contentType,
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
    ...(result.bodyStream ? { 'x-accel-buffering': 'no' } : {}),
  });
  if (result.bodyStream) {
    await pipeReadableStreamToResponse(result.bodyStream, response, { abort: result.abort });
    return;
  }
  response.end(result.bodyText);
}

async function registerCustomer(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  if (password.length < 6) {
    throw publicError(400, '密码至少 6 位');
  }

  const now = new Date().toISOString();
  const verificationCode = serverOptions.requireEmailVerification ? generateVerificationCode() : '';
  let user = data.users.find((item) => item.email === email);
  if (user) {
    throw publicError(409, '邮箱已注册，请直接登录');
  }

  user = {
    id: createId('user'),
    email,
    emailVerified: !serverOptions.requireEmailVerification,
    passwordHash: hashPassword(password, serverOptions.passwordHashSecret),
    displayName: email.split('@')[0],
    verificationCode,
    plan: '默认套餐',
    renewalDate: formatDate(addDays(new Date(), 30)),
    planExpiresAt: '',
    balanceCents: 0,
    packageQuotaCents: 0,
    boosterQuotaCents: 0,
    balanceAlert: defaultBalanceAlert(email),
    createdAt: now,
    updatedAt: now,
  };
  data.users.push(user);

  const sessionToken = createId('sess');
  const csrfToken = createId('csrf');
  data.sessions[sessionToken] = user.id;
  data.sessionCsrfTokens[sessionToken] = csrfToken;
  data.events.push({ type: 'registered', userId: user.id, at: now });

  const responseUser = sanitizeUser(user);
  const result = {
    sessionToken,
    csrfToken,
    body: {
      user: responseUser,
      csrfToken,
      ...(serverOptions.exposeVerificationCode && verificationCode ? { verificationCode } : {}),
    },
  };
  if (verificationCode) {
    await scheduleEmailDelivery({
      serverOptions,
      to: email,
      message: buildVerificationEmail({
        user,
        code: verificationCode,
        publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
        at: now,
      }),
      data,
      successType: 'email_verification_sent',
      failureType: 'email_verification_failed',
      eventBase: { userId: user.id, email: maskEmail(email) },
    });
  }
  return result;
}

function loginCustomer(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  const user = data.users.find((item) => item.email === email);
  const passwordResult = verifyPassword(password, user?.passwordHash, serverOptions.passwordHashSecrets);
  if (!user || !passwordResult.ok) {
    throw publicError(401, '邮箱或密码不正确');
  }

  const now = new Date().toISOString();
  if (!isModernPasswordHash(user.passwordHash) || passwordResult.secret !== serverOptions.passwordHashSecret) {
    user.passwordHash = hashPassword(password, serverOptions.passwordHashSecret);
    data.events.push({ type: 'password_hash_upgraded', userId: user.id, at: now });
  }
  const sessionToken = createId('sess');
  const csrfToken = createId('csrf');
  data.sessions[sessionToken] = user.id;
  data.sessionCsrfTokens[sessionToken] = csrfToken;
  user.updatedAt = now;
  data.events.push({ type: 'logged_in', userId: user.id, at: now });
  return {
    sessionToken,
    csrfToken,
    body: {
      user: sanitizeUser(user),
      account: accountFromUser(data, user),
      csrfToken,
    },
  };
}

function changeCustomerPassword(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const oldPassword = String(body.oldPassword || '');
  const newPassword = String(body.newPassword || '');
  if (!verifyPassword(oldPassword, user.passwordHash, serverOptions.passwordHashSecrets).ok) {
    throw publicError(401, '旧密码不正确');
  }
  if (newPassword.length < 6) {
    throw publicError(400, '新密码至少 6 位');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(newPassword, serverOptions.passwordHashSecret);
  user.updatedAt = now;
  data.events.push({ type: 'password_changed', userId: user.id, at: now });
  return { user: sanitizeUser(user), account: accountFromUser(data, user) };
}

async function requestCustomerPasswordReset(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  const now = new Date().toISOString();
  const user = data.users.find((item) => item.email === email);
  if (user) {
    const code = generateVerificationCode();
    user.passwordReset = {
      codeHash: hashPasswordResetCode(code, serverOptions.passwordHashSecret),
      expiresAt: new Date(Date.now() + Number(serverOptions.passwordResetTtlMs || 900_000)).toISOString(),
      usedAt: '',
      requestedAt: now,
    };
    user.updatedAt = now;
    data.events.push({ type: 'password_reset_requested', userId: user.id, email: maskEmail(email), at: now });
    await scheduleEmailDelivery({
      serverOptions,
      to: email,
      message: buildPasswordResetEmail({
        user,
        code,
        publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
        expiresMinutes: Math.max(1, Math.round(Number(serverOptions.passwordResetTtlMs || 900_000) / 60_000)),
        at: now,
      }),
      data,
      successType: 'password_reset_email_sent',
      failureType: 'password_reset_email_failed',
      eventBase: { userId: user.id, email: maskEmail(email) },
    });
    return {
      ok: true,
      message: '如果邮箱存在，我们会发送重置验证码。',
      ...(serverOptions.exposeVerificationCode ? { resetCode: code } : {}),
    };
  }
  data.events.push({ type: 'password_reset_requested_unknown', email: maskEmail(email), at: now });
  return { ok: true, message: '如果邮箱存在，我们会发送重置验证码。' };
}

function confirmCustomerPasswordReset(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const code = String(body.code || '').trim();
  const newPassword = String(body.newPassword || body.password || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  if (!code) {
    throw publicError(400, '重置验证码不能为空');
  }
  if (newPassword.length < 6) {
    throw publicError(400, '新密码至少 6 位');
  }
  const user = data.users.find((item) => item.email === email);
  const reset = user?.passwordReset;
  if (!user || !reset?.codeHash || reset.usedAt) {
    throw publicError(400, '重置验证码无效或已过期');
  }
  if (Date.parse(reset.expiresAt || '') <= Date.now()) {
    throw publicError(400, '重置验证码无效或已过期');
  }
  if (!safeEqual(reset.codeHash, hashPasswordResetCode(code, serverOptions.passwordHashSecret))) {
    throw publicError(400, '重置验证码无效或已过期');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(newPassword, serverOptions.passwordHashSecret);
  user.passwordReset = { ...reset, usedAt: now };
  user.updatedAt = now;
  data.events.push({ type: 'password_reset_confirmed', userId: user.id, at: now });
  return { ok: true, message: '密码已重置，请用新密码登录。' };
}

function verifyCustomer(data, request, body) {
  const { user } = requireSession(data, request);
  if (!user.verificationCode && user.emailVerified) {
    return { user: sanitizeUser(user) };
  }
  if (String(body.code || '') !== user.verificationCode) {
    throw publicError(400, '验证码不正确');
  }
  user.emailVerified = true;
  user.verificationCode = '';
  user.updatedAt = new Date().toISOString();
  data.events.push({ type: 'email_verified', userId: user.id, at: user.updatedAt });
  return { user: sanitizeUser(user) };
}

function updateCustomerProfile(data, request, body) {
  const { user } = requireSession(data, request);
  const displayName = String(body.displayName ?? body.nickname ?? '').trim();
  const nextEmail = String(body.email ?? user.email ?? '').trim().toLowerCase();
  const avatarUrl = sanitizeAvatarUrl(body.avatarUrl ?? user.avatarUrl ?? '');
  if (!displayName || displayName.length > 40) {
    throw publicError(400, '昵称需要 1-40 个字符');
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(nextEmail)) {
    throw publicError(400, '邮箱格式不正确');
  }
  const oldEmail = String(user.email || '').toLowerCase();
  if (nextEmail !== oldEmail && data.users.some((item) => item.id !== user.id && item.email === nextEmail)) {
    throw publicError(409, '邮箱已被占用');
  }

  const now = new Date().toISOString();
  user.displayName = displayName.slice(0, 40);
  user.avatarUrl = avatarUrl;
  if (nextEmail !== oldEmail) {
    const previousAlertEmail = normalizeAlertEmail(user.balanceAlert?.email || '');
    user.email = nextEmail;
    user.emailVerified = false;
    user.verificationCode = '';
    if (!previousAlertEmail || previousAlertEmail === oldEmail) {
      user.balanceAlert = {
        ...normalizeBalanceAlertRecord(user.balanceAlert, nextEmail),
        email: nextEmail,
        updatedAt: now,
      };
    }
  }
  user.updatedAt = now;
  data.events.push({
    type: 'profile_updated',
    userId: user.id,
    emailChanged: nextEmail !== oldEmail,
    at: now,
  });
  return {
    user: sanitizeUser(user),
    account: accountFromUser(data, user),
    balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email),
  };
}

function updateCustomerBalanceAlert(data, request, body) {
  const { user } = requireSession(data, request);
  const thresholdCents = normalizeAlertThresholdCents(body);
  const email = normalizeAlertEmail(body.email || user.balanceAlert?.email || user.email);
  const enabled = Object.prototype.hasOwnProperty.call(body, 'enabled') ? Boolean(body.enabled) : true;
  if (!Number.isFinite(thresholdCents) || thresholdCents <= 0 || thresholdCents > 1_000_000_00) {
    throw publicError(400, '余额预警阈值必须在 $0.01 ~ $1,000,000.00 之间');
  }
  if (!email) {
    throw publicError(400, '预警邮箱格式不正确');
  }

  const now = new Date().toISOString();
  user.balanceAlert = {
    enabled,
    thresholdCents,
    email,
    lastAlertAt: '',
    lastAlertBalanceCents: 0,
    lastTriggeredThresholdCents: 0,
    updatedAt: now,
  };
  user.updatedAt = now;
  data.events.push({
    type: 'balance_alert_updated',
    userId: user.id,
    thresholdCents,
    enabled,
    alertEmail: maskEmail(email),
    at: now,
  });
  return { balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email) };
}

async function sendCustomerBalanceAlertTest(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const current = normalizeBalanceAlertRecord(user.balanceAlert, user.email);
  const email = normalizeAlertEmail(body.email || current.email || user.email);
  const thresholdCents = normalizeAlertThresholdCents(body, current.thresholdCents);
  if (!email) {
    throw publicError(400, '预警邮箱格式不正确');
  }
  if (!Number.isFinite(thresholdCents) || thresholdCents <= 0 || thresholdCents > 1_000_000_00) {
    throw publicError(400, '余额预警阈值必须在 $0.01 ~ $1,000,000.00 之间');
  }
  const sender = serverOptions.balanceAlertEmailSender;
  if (typeof sender !== 'function') {
    throw publicError(503, 'SMTP 邮件服务未配置');
  }

  const now = new Date().toISOString();
  const message = buildBalanceAlertEmail({
    user,
    to: email,
    thresholdCents,
    balanceCents: availableQuotaCents(user),
    previousBalanceCents: availableQuotaCents(user),
    model: String(body.model || '测试邮件'),
    quotaCost: 0,
    publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
    at: now,
    isTest: true,
  });
  await sender(message);
  data.events.push({
    type: 'balance_alert_test_sent',
    userId: user.id,
    alertEmail: maskEmail(email),
    thresholdCents,
    at: now,
  });
  return { ok: true, balanceAlert: sanitizeBalanceAlert({ ...current, email, thresholdCents }, user.email) };
}

function claimAdminIdentity(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = String(body.code || '').trim();
  const codeHash = hashAdminClaimCode(code);
  const allowedHashes = serverOptions.adminClaimCodeHashes || [];
  if (!code || allowedHashes.length === 0 || !allowedHashes.includes(codeHash)) {
    throw publicError(403, '身份码无效');
  }
  if (data.usedAdminClaimCodeHashes.includes(codeHash)) {
    throw publicError(409, '身份码已失效');
  }

  const now = new Date().toISOString();
  user.isAdmin = true;
  user.updatedAt = now;
  data.usedAdminClaimCodeHashes.push(codeHash);
  data.events.push({ type: 'admin_claimed', userId: user.id, at: now });
  return {
    user: sanitizeUser(user),
    adminUrl: '/admin.html',
    message: '管理员身份已激活',
  };
}

function verifyAdminSecondFactor(data, request, body, serverOptions) {
  requireAdmin(data, request, serverOptions, { allowPendingSecondFactor: true });
  if (!serverOptions.requireAdmin2fa) {
    return {
      sessionToken: '',
      body: {
        ok: true,
        secondFactorRequired: false,
        message: '管理员 2FA 未启用',
      },
    };
  }
  const code = String(body.code || body.totp || '').replace(/\s+/g, '');
  if (!verifyTotpCode(serverOptions.adminTotpSecrets, code, serverOptions.nowFactory())) {
    data.events.push({
      type: 'admin_2fa_failed',
      ipHash: hashId(clientIp(request)),
      at: currentDate(serverOptions).toISOString(),
    });
    throw publicError(401, '管理员 2FA 验证码无效');
  }
  const now = currentDate(serverOptions).toISOString();
  const sessionToken = createId('mfa');
  data.adminSecondFactorSessions[sessionToken] = {
    createdAt: now,
    expiresAt: new Date(currentDate(serverOptions).getTime() + Number(serverOptions.admin2faSessionTtlMs || 3_600_000)).toISOString(),
    ipHash: hashId(clientIp(request)),
  };
  pruneAdminSecondFactorSessions(data, serverOptions);
  data.events.push({
    type: 'admin_2fa_verified',
    ipHash: hashId(clientIp(request)),
    at: now,
  });
  return {
    sessionToken,
    body: {
      ok: true,
      secondFactorRequired: false,
      message: '管理员 2FA 已通过',
    },
  };
}

async function rechargeCustomer(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const selectedPlan = findRechargePlan(data, body);
  const amountCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.amountCny || 0) * 100);
  const creditCents = selectedPlan ? planCreditCents(selectedPlan) : amountCents;
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : normalizeRechargePlan(body.plan);
  if (!Number.isFinite(amountCents) || amountCents <= 0 || !Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '充值金额必须大于 0');
  }

  if (!serverOptions.allowDemoRecharge) {
    const now = new Date().toISOString();
    const method = normalizePaymentMethod(body.method);
    const paymentOrder = {
      id: createId('pay'),
      userId: user.id,
      email: user.email,
      amountCents,
      creditCents,
      quotaUsd: selectedPlan?.quotaUsd || 0,
      planId: selectedPlan?.id || '',
      plan: planType,
      method,
      provider: paymentProviderForMethod(method),
      status: paymentProviderForMethod(method) ? 'pending_provider_payment' : 'pending_manual_payment',
      createdAt: now,
      updatedAt: now,
    };
    if (paymentProviderForMethod(method)) {
      const provider = paymentProviderForMethod(method);
      if (!providerReady(serverOptions.paymentConfig, provider)) {
        throw publicError(503, provider === 'wechat' ? '微信支付接口未配置完成' : '支付宝接口未配置完成');
      }
      const providerPayment = await createProviderPayment({
        provider,
        order: paymentOrder,
        plan: selectedPlan,
        fetchImpl: serverOptions.fetchImpl || globalThis.fetch,
        paymentConfig: serverOptions.paymentConfig,
      });
      paymentOrder.providerOrder = sanitizeProviderPayment(providerPayment);
      paymentOrder.notifyUrl = providerPayment.notifyUrl;
      paymentOrder.qrCode = providerPayment.qrCode;
      paymentOrder.status = 'pending_provider_payment';
    }
    data.paymentOrders.unshift(paymentOrder);
    data.events.push({
      type: 'payment_order_created',
      userId: user.id,
      amountCents,
      creditCents,
      plan: paymentOrder.plan,
      method: paymentOrder.method,
      provider: paymentOrder.provider || '',
      at: now,
    });
    return {
      status: 202,
      body: {
        paymentOrder: sanitizePaymentOrder(paymentOrder),
        provider: paymentOrder.provider || '',
        qrCode: paymentOrder.qrCode || '',
        account: accountFromUser(data, user),
        user: sanitizeUser(user),
      },
    };
  }

  if (planType === 'day') {
    user.plan = '日卡';
    const expiresAt = addDays(currentDate(serverOptions), 1);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += creditCents;
  } else {
    user.boosterQuotaCents += creditCents;
  }
  reconcileUserBalance(user);
  user.updatedAt = new Date().toISOString();
  data.events.push({
    type: 'recharged',
    userId: user.id,
    amountCents,
    creditCents,
    method: String(body.method || 'manual'),
    at: user.updatedAt,
  });
  return {
    status: 200,
    body: { account: accountFromUser(data, user), user: sanitizeUser(user) },
  };
}

function adminResetCustomerPassword(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || body.newPassword || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '用户邮箱格式不正确');
  }
  if (password.length < 10) {
    throw publicError(400, '新密码至少 10 位');
  }
  const user = data.users.find((item) => item.email === email);
  if (!user) {
    throw publicError(404, '用户不存在');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(password, serverOptions.passwordHashSecret);
  user.passwordReset = {
    codeHash: '',
    expiresAt: '',
    usedAt: now,
    requestedAt: now,
  };
  user.updatedAt = now;
  data.events.push({ type: 'admin_password_reset', userId: user.id, email: maskEmail(email), at: now });
  return {
    ok: true,
    user: sanitizeUser(user),
    message: '用户密码已重置',
    events: sanitizeAdminEvents(data.events),
  };
}

function manualRechargeCustomer(data, body) {
  const email = String(body.email || '').trim().toLowerCase();
  const selectedPlan = findRechargePlan(data, body);
  const amountCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.amountCny || 0) * 100);
  const creditCents = selectedPlan ? planCreditCents(selectedPlan) : amountCents;
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : String(body.plan || 'balance').trim().toLowerCase();
  if (!email) {
    throw publicError(400, '用户邮箱不能为空');
  }
  if (!Number.isFinite(amountCents) || amountCents <= 0 || !Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '充值金额必须大于 0');
  }

  const user = data.users.find((item) => item.email === email);
  if (!user) {
    throw publicError(404, '用户不存在');
  }

  const now = new Date().toISOString();
  if (planType === 'day' || planType === 'month') {
    const days = planType === 'day' ? 1 : 30;
    user.plan = planType === 'day' ? '日卡' : '月卡';
    const expiresAt = addDays(new Date(now), days);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += creditCents;
  } else {
    user.boosterQuotaCents += creditCents;
  }
  reconcileUserBalance(user);
  user.updatedAt = now;

  const pendingOrder = data.paymentOrders.find(
    (order) =>
      order.userId === user.id &&
      order.status === 'pending_manual_payment' &&
      (String(body.paymentOrderId || '') ? order.id === body.paymentOrderId : Number(order.amountCents) === amountCents),
  );
  if (pendingOrder) {
    pendingOrder.status = 'confirmed';
    pendingOrder.confirmedAt = now;
    pendingOrder.updatedAt = now;
  }

  data.events.push({
    type: 'manual_recharged',
    userId: user.id,
    amountCents,
    creditCents,
    plan: planType,
    method: String(body.method || 'manual_confirmed'),
    at: now,
  });

  return {
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    paymentOrder: pendingOrder ? sanitizePaymentOrder(pendingOrder) : null,
    events: sanitizeAdminEvents(data.events),
  };
}

function handleWechatPaymentNotification(data, request, rawBody, serverOptions) {
  const transaction = verifyWechatNotification({
    headers: request.headers,
    rawBody,
    paymentConfig: serverOptions.paymentConfig,
  });
  const orderId = String(transaction.out_trade_no || '').trim();
  if (!orderId) {
    throw publicError(400, '微信支付回调缺少订单号');
  }
  if (String(transaction.trade_state || '').toUpperCase() !== 'SUCCESS') {
    recordPaymentCallback(data, orderId, {
      provider: 'wechat',
      status: 'ignored',
      reason: transaction.trade_state || 'not_success',
      payload: sanitizePaymentCallbackPayload(transaction),
    });
    return { code: 'SUCCESS', message: '成功' };
  }
  confirmProviderPayment(data, orderId, {
    provider: 'wechat',
    transactionId: transaction.transaction_id || '',
    payload: sanitizePaymentCallbackPayload(transaction),
    rawPayload: transaction,
  });
  return { code: 'SUCCESS', message: '成功' };
}

function handleAlipayPaymentNotification(data, rawBody, serverOptions) {
  const notification = parseAlipayNotification(rawBody, serverOptions.paymentConfig.alipay.publicKey);
  const orderId = String(notification.out_trade_no || '').trim();
  if (!orderId) {
    throw publicError(400, '支付宝回调缺少订单号');
  }
  const tradeStatus = String(notification.trade_status || '').toUpperCase();
  if (!['TRADE_SUCCESS', 'TRADE_FINISHED'].includes(tradeStatus)) {
    recordPaymentCallback(data, orderId, {
      provider: 'alipay',
      status: 'ignored',
      reason: tradeStatus || 'not_success',
      payload: sanitizePaymentCallbackPayload(notification),
    });
    return { ok: true };
  }
  confirmProviderPayment(data, orderId, {
    provider: 'alipay',
    transactionId: notification.trade_no || '',
    payload: sanitizePaymentCallbackPayload(notification),
    rawPayload: notification,
  });
  return { ok: true };
}

function confirmProviderPayment(data, orderId, details = {}) {
  const order = data.paymentOrders.find((item) => item.id === orderId);
  if (!order) {
    throw publicError(404, '支付订单不存在');
  }
  const user = data.users.find((item) => item.id === order.userId);
  if (!user) {
    throw publicError(404, '支付订单用户不存在');
  }
  const now = new Date().toISOString();
  if (order.status === 'paid' || order.status === 'confirmed') {
    recordPaymentCallback(data, orderId, {
      provider: details.provider || order.provider || '',
      status: 'duplicate',
      transactionId: details.transactionId || order.transactionId || '',
      payload: details.payload || {},
    });
    return { order, user, duplicate: true };
  }
  assertPaymentAmountMatchesOrder(order, details.provider || order.provider || '', details.rawPayload || details.payload || {});

  creditUserForOrder(user, order, now);
  order.status = 'paid';
  order.provider = details.provider || order.provider || '';
  order.transactionId = details.transactionId || '';
  order.paidAt = now;
  order.updatedAt = now;
  order.callbackPayload = details.payload || {};
  data.events.push({
    type: 'provider_payment_confirmed',
    userId: user.id,
    orderId: order.id,
    provider: order.provider,
    amountCents: order.amountCents,
    creditCents: order.creditCents,
    transactionId: order.transactionId,
    at: now,
  });
  recordPaymentCallback(data, orderId, {
    provider: order.provider,
    status: 'confirmed',
    transactionId: order.transactionId,
    payload: details.payload || {},
  });
  return { order, user, duplicate: false };
}

function assertPaymentAmountMatchesOrder(order, provider, payload) {
  const expected = Number(order.amountCents || 0);
  const actual = providerPaymentAmountCents(provider, payload);
  if (!Number.isFinite(actual) || actual !== expected) {
    throw publicError(400, '支付金额与订单金额不一致');
  }
}

function providerPaymentAmountCents(provider, payload = {}) {
  if (provider === 'wechat') {
    return Number(payload?.amount?.payer_total ?? payload?.amount?.total);
  }
  if (provider === 'alipay') {
    return yuanToCents(payload.receipt_amount || payload.buyer_pay_amount || payload.total_amount);
  }
  return Number.NaN;
}

function yuanToCents(value) {
  const text = String(value ?? '').trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) {
    return Number.NaN;
  }
  const [yuan, cents = ''] = text.split('.');
  return Number(yuan) * 100 + Number(cents.padEnd(2, '0'));
}

function creditUserForOrder(user, order, now) {
  if (normalizeRechargePlan(order.plan) === 'day') {
    user.plan = '日卡';
    const expiresAt = addDays(new Date(now), 1);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += Number(order.creditCents || 0);
  } else if (normalizeRechargePlan(order.plan) === 'month') {
    user.plan = '月卡';
    const expiresAt = addDays(new Date(now), 30);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += Number(order.creditCents || 0);
  } else {
    user.boosterQuotaCents += Number(order.creditCents || 0);
  }
  reconcileUserBalance(user);
  user.updatedAt = now;
}

function recordPaymentCallback(data, orderId, details = {}) {
  data.events.push({
    type: 'payment_callback',
    orderId,
    provider: details.provider || '',
    status: details.status || '',
    reason: details.reason || '',
    transactionId: details.transactionId || '',
    at: new Date().toISOString(),
  });
}

function buildPaymentClosureStatus(serverOptions) {
  const paymentConfig = serverOptions.paymentConfig || {};
  const wechatReady = providerReady(paymentConfig, 'wechat');
  const alipayReady = providerReady(paymentConfig, 'alipay');
  const wechatNotifyUrl = paymentConfig.wechat?.notifyUrl || (
    paymentConfig.publicBaseUrl ? `${paymentConfig.publicBaseUrl}/api/frist/payments/wechat/notify` : ''
  );
  const alipayNotifyUrl = paymentConfig.alipay?.notifyUrl || (
    paymentConfig.publicBaseUrl ? `${paymentConfig.publicBaseUrl}/api/frist/payments/alipay/notify` : ''
  );
  const providers = [
    {
      id: 'wechat',
      name: '微信支付',
      ready: wechatReady,
      notifyUrl: wechatNotifyUrl,
      missing: paymentMissingFields(paymentConfig.wechat || {}, [
        ['enabled', 'FRIST_API_WECHAT_PAY_ENABLED'],
        ['appid', 'FRIST_API_WECHAT_PAY_APPID'],
        ['mchid', 'FRIST_API_WECHAT_PAY_MCH_ID'],
        ['serialNo', 'FRIST_API_WECHAT_PAY_SERIAL_NO'],
        ['privateKey', 'FRIST_API_WECHAT_PAY_PRIVATE_KEY'],
        ['publicKey', 'FRIST_API_WECHAT_PAY_PUBLIC_KEY'],
        ['apiV3Key', 'FRIST_API_WECHAT_PAY_API_V3_KEY'],
      ]),
    },
    {
      id: 'alipay',
      name: '支付宝',
      ready: alipayReady,
      notifyUrl: alipayNotifyUrl,
      missing: paymentMissingFields(paymentConfig.alipay || {}, [
        ['enabled', 'FRIST_API_ALIPAY_ENABLED'],
        ['appId', 'FRIST_API_ALIPAY_APP_ID'],
        ['privateKey', 'FRIST_API_ALIPAY_PRIVATE_KEY'],
        ['publicKey', 'FRIST_API_ALIPAY_PUBLIC_KEY'],
      ]),
    },
  ];
  return {
    enabled: Boolean(paymentConfig.enabled),
    ready: Boolean(paymentConfig.enabled && providers.some((provider) => provider.ready)),
    providers,
  };
}

function paymentMissingFields(config, fields) {
  return fields
    .filter(([key]) => {
      if (key === 'enabled') return !config.enabled;
      return !String(config[key] || '').trim();
    })
    .map(([, envName]) => envName);
}

function normalizePaymentMethod(value) {
  const method = String(value || 'manual_pending').trim().toLowerCase();
  if (['wechat_native', 'wechat', 'wechat_pay', 'wxpay'].includes(method)) return 'wechat_native';
  if (['alipay_precreate', 'alipay', 'alipay_qr'].includes(method)) return 'alipay_precreate';
  return method || 'manual_pending';
}

function paymentProviderForMethod(method) {
  if (method === 'wechat_native') return 'wechat';
  if (method === 'alipay_precreate') return 'alipay';
  return '';
}

function sanitizeProviderPayment(payment) {
  return {
    provider: payment.provider,
    notifyUrl: payment.notifyUrl,
    qrCode: payment.qrCode,
  };
}

function sanitizePaymentCallbackPayload(payload = {}) {
  const blocked = new Set(['openid', 'payer', 'buyer_logon_id', 'buyer_user_id', 'fund_bill_list']);
  return Object.fromEntries(
    Object.entries(payload)
      .filter(([key]) => !blocked.has(key))
      .map(([key, value]) => [key, typeof value === 'object' ? JSON.stringify(value).slice(0, 300) : String(value).slice(0, 300)]),
  );
}

function normalizeRechargePlan(value) {
  const plan = String(value || 'balance').trim().toLowerCase();
  return ['balance', 'day', 'month'].includes(plan) ? plan : 'balance';
}

function findRechargePlan(data, body = {}) {
  const plans = normalizePricingConfig(data.pricing || {}).rechargePlans;
  const requestedId = String(body.planId || '').trim();
  if (requestedId) {
    return plans.find((plan) => plan.id === requestedId) || null;
  }
  const requestedPlan = String(body.plan || '').trim().toLowerCase();
  const amountCny = Number(body.amountCny || 0);
  return (
    plans.find(
      (plan) =>
        normalizeRechargePlan(plan.plan) === normalizeRechargePlan(requestedPlan) &&
        Math.abs(Number(plan.priceCny || 0) - amountCny) < 0.001,
    ) ||
    plans.find((plan) => Math.abs(Number(plan.priceCny || 0) - amountCny) < 0.001) ||
    null
  );
}

function planCreditCents(plan) {
  return Math.round(Number(plan.quotaUsd || 0) * DEFAULT_USD_TO_CNY * 100);
}

function planPriceCents(plan) {
  return Math.round(Number(plan.priceCny || 0) * 100);
}

function buildRechargeOptions(data) {
  return normalizePricingConfig(data.pricing || {}).rechargePlans.map((plan, index) => ({
    id: plan.id,
    label: plan.label,
    quotaUsd: plan.quotaUsd,
    priceCny: plan.priceCny,
    durationDays: plan.durationDays,
    plan: plan.plan,
    cny: `¥${Number(plan.priceCny || 0).toFixed(2)}`,
    quota: `$${Number(plan.quotaUsd || 0).toFixed(0)}`,
    active: index === 0,
  }));
}

function createRedemptionCards(data, body) {
  const selectedPlan = findRechargePlan(data, body);
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : normalizeRechargePlan(body.plan);
  const quantity = clampInteger(body.quantity, 1, 200);
  const now = new Date().toISOString();
  const prefix = normalizeCardPrefix(body.prefix || DEFAULT_CARD_BATCH_PREFIX);
  const label = String(body.label || selectedPlan?.label || cardLabelForPlan(planType, body)).trim();
  const priceCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.priceCny || 0) * 100);
  const creditCents = selectedPlan
    ? planCreditCents(selectedPlan)
    : Math.round(Number(body.quotaUsd || body.creditUsd || 0) * DEFAULT_USD_TO_CNY * 100);
  const quotaUsd = selectedPlan ? Number(selectedPlan.quotaUsd || 0) : round2(Number(body.quotaUsd || body.creditUsd || 0));
  const durationDays = selectedPlan
    ? Number(selectedPlan.durationDays || 0)
    : planType === 'day'
      ? 1
      : planType === 'month'
        ? 30
        : Math.max(0, Number(body.durationDays || 0));

  if (!Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '卡密额度必须大于 0');
  }
  if (!label) {
    throw publicError(400, '卡密名称不能为空');
  }

  const batchId = createId('batch');
  const cards = [];
  const existingCodes = new Set([
    ...data.redemptionCards.map((card) => card.code),
    ...data.redemptions.map((item) => item.code),
    ...LEGACY_CARD_CODES.keys(),
  ]);
  for (let index = 0; index < quantity; index += 1) {
    let code = '';
    for (let attempt = 0; attempt < 20; attempt += 1) {
      code = `${prefix}-${randomCardCodeSegment()}-${randomCardCodeSegment()}`;
      if (!existingCodes.has(code)) break;
    }
    if (!code || existingCodes.has(code)) {
      throw publicError(500, '卡密生成失败，请重试');
    }
    existingCodes.add(code);
    const card = {
      id: createId('card'),
      batchId,
      code,
      label,
      plan: planType,
      durationDays,
      quotaUsd,
      priceCny: round2(priceCents / 100),
      creditCents,
      status: 'unused',
      source: 'xianyu',
      note: String(body.note || '').trim(),
      createdAt: now,
      updatedAt: now,
      redeemedAt: '',
      redeemedBy: '',
      redeemedEmail: '',
    };
    data.redemptionCards.unshift(card);
    cards.push(card);
  }

  data.events.push({
    type: 'redemption_cards_created',
    batchId,
    count: cards.length,
    plan: planType,
    creditCents,
    at: now,
  });
  return {
    batchId,
    cards: cards.map(sanitizeRedemptionCard),
    exportText: buildRedemptionCardExport(cards),
    events: sanitizeAdminEvents(data.events),
  };
}

function redeemCustomerCode(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = String(body.code || '').trim().toUpperCase();
  const card = data.redemptionCards.find((item) => item.code === code);
  const rule = card ? redemptionRuleFromCard(card) : LEGACY_CARD_CODES.get(code);
  if (!rule) {
    throw publicError(400, '兑换码无效');
  }
  if (data.redemptions.some((item) => item.code === code)) {
    throw publicError(409, '兑换码已使用');
  }
  if (card && card.status !== 'unused') {
    throw publicError(409, '兑换码已使用');
  }

  const now = currentDate(serverOptions);
  const planType = normalizeRechargePlan(rule.plan);
  if (planType === 'day' || planType === 'month' || rule.displayPlan) {
    user.plan = rule.displayPlan || (planType === 'month' ? '月卡' : '日卡');
    const expiresAt = addDays(now, rule.days);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
  }
  user.packageQuotaCents += Number(rule.packageCents || 0);
  user.boosterQuotaCents += Number(rule.boosterCents || 0);
  user.balanceCents += Number(rule.packageCents || 0) + Number(rule.boosterCents || 0);
  reconcileUserBalance(user);
  user.updatedAt = now.toISOString();
  data.redemptions.push({
    code,
    userId: user.id,
    plan: rule.displayPlan || rule.label || (planType === 'balance' ? '加油包' : planType),
    cardId: card?.id || '',
    batchId: card?.batchId || '',
    creditCents: Number(rule.packageCents || 0) + Number(rule.boosterCents || 0),
    at: user.updatedAt,
  });
  if (card) {
    card.status = 'redeemed';
    card.redeemedAt = user.updatedAt;
    card.redeemedBy = user.id;
    card.redeemedEmail = user.email;
    card.updatedAt = user.updatedAt;
  }
  data.events.push({ type: 'redeemed', userId: user.id, code, at: user.updatedAt });
  return {
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    redemption: {
      code,
      label: rule.label || '兑换码',
      plan: rule.displayPlan || rule.plan || 'balance',
      credit: formatUsdFromCnyCents(Number(rule.packageCents || 0) + Number(rule.boosterCents || 0)),
    },
  };
}

function redemptionRuleFromCard(card) {
  const planType = normalizeRechargePlan(card.plan);
  const creditCents = Number(card.creditCents || 0);
  return {
    label: card.label || 'Frist-API 兑换码',
    plan: planType,
    displayPlan: planType === 'day' ? '日卡' : planType === 'month' ? '月卡' : '',
    days: Number(card.durationDays || (planType === 'month' ? 30 : planType === 'day' ? 1 : 0)),
    packageCents: planType === 'day' || planType === 'month' ? creditCents : 0,
    boosterCents: planType === 'balance' ? creditCents : 0,
  };
}

function upsertPlusAccount(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const existing = body.id ? data.plusAccounts.find((account) => account.id === String(body.id)) : null;
  const mergedBody = existing
    ? {
        ...existing,
        ...body,
        openaiEmail: body.openaiEmail || existing.openaiEmail,
        appleEmail: body.appleEmail || existing.appleEmail,
        secrets: body.secrets || existing.secrets,
      }
    : body;
  const input = normalizePlusAccountRecord({
    ...mergedBody,
    id: existing?.id || '',
    createdAt: existing?.createdAt || body.createdAt || now,
    updatedAt: now,
  });
  if (!input.openaiEmail && !input.appleEmail) {
    throw publicError(400, '至少填写一个 OpenAI 或 Apple ID 邮箱');
  }
  if (input.complianceStatus === 'blocked' && input.status !== 'risk_hold' && input.status !== 'retired') {
    input.status = 'risk_hold';
  }
  if (input.status === 'active' && input.complianceStatus !== 'self_use_only') {
    throw publicError(400, 'Plus 账号必须标记为仅自用后才能设为活跃');
  }

  const account = existing
    ? Object.assign(existing, {
        ...input,
        id: existing.id,
        createdAt: existing.createdAt || input.createdAt || now,
        updatedAt: now,
      })
    : input;
  if (!existing) {
    data.plusAccounts.unshift(account);
  }

  data.events.push({
    type: 'plus_account_upserted',
    accountId: account.id,
    status: account.status,
    renewalAt: account.plusRenewalAt || '',
    at: now,
  });
  return {
    account: sanitizePlusAccount(account, serverOptions),
    summary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
    events: sanitizeAdminEvents(data.events),
  };
}

function importRtAccounts(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const parsedRows = parseRtImportText(body.rtText ?? body.text ?? body.json ?? body.items);
  const platform = normalizeRtPlatform(body.platform || '');
  const sourceLabel = String(body.sourceLabel || '').trim().slice(0, 80);
  const accountType = String(body.accountType || '').trim().slice(0, 60);
  const note = sanitizeRiskNote(body.note || '');
  const imported = [];
  const skipped = [];
  for (const row of parsedRows) {
    const normalized = normalizeRtAccountRecord({
      ...row,
      platform: row.platform || platform,
      sourceLabel: row.sourceLabel || sourceLabel,
      accountType: row.accountType || accountType,
      note: row.note || note,
      createdAt: row.createdAt || now,
      updatedAt: now,
      importedAt: now,
    });
    if (!normalized.refreshToken) {
      skipped.push({ email: normalized.email || row.email || '', reason: '缺少 refresh_token' });
      continue;
    }
    const fingerprint = normalized.refreshTokenFingerprint;
    const existing = data.rtAccounts.find(
      (account) =>
        account.refreshTokenFingerprint === fingerprint ||
        (normalized.email && account.email === normalized.email && account.platform === normalized.platform),
    );
    if (existing) {
      Object.assign(existing, {
        ...normalized,
        id: existing.id,
        createdAt: existing.createdAt || normalized.createdAt,
        updatedAt: now,
      });
      imported.push(existing);
    } else {
      data.rtAccounts.unshift(normalized);
      imported.push(normalized);
    }
  }

  if (!parsedRows.length) {
    throw publicError(400, '没有识别到 RT 账号，请粘贴 JSON 数组、单个 JSON 对象或每行一个 RT');
  }
  if (!imported.length) {
    throw publicError(400, '没有可导入的 refresh_token');
  }

  data.events.push({
    type: 'rt_accounts_imported',
    count: imported.length,
    skipped: skipped.length,
    platform,
    at: now,
  });
  return {
    imported: imported.map(sanitizeRtAccount),
    skipped,
    accounts: data.rtAccounts.map(sanitizeRtAccount),
    summary: buildRtAccountSummary(data.rtAccounts),
    events: sanitizeAdminEvents(data.events),
  };
}

function createCustomerToken(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  if (serverOptions.requireEmailVerification && !user.emailVerified) {
    throw publicError(403, '请先完成邮箱验证');
  }

  const now = new Date().toISOString();
  const secret = generateCustomerApiKey();
  const key = {
    id: createId('key'),
    userId: user.id,
    name: String(body.name || `API Key ${data.userKeys.length + 1}`).trim(),
    secret,
    preview: maskKey(secret),
    enabled: true,
    modelGroup: normalizeModelGroup(body.modelGroup),
    costCents: 0,
    tokens: '0.00M',
    lastUsed: '-',
    expiresAt: '-',
    createdAt: now,
    updatedAt: now,
  };
  data.userKeys.unshift(key);
  data.events.push({ type: 'key_created', userId: user.id, keyId: key.id, at: now });
  return { key: sanitizeUserKey(key, { revealSecret: true }) };
}

function updateCustomerToken(data, request, keyId, body) {
  const { user } = requireSession(data, request);
  const key = data.userKeys.find((item) => item.userId === user.id && item.id === keyId);
  if (!key) {
    throw publicError(404, 'API Key 不存在');
  }
  const hasEnabled = Object.prototype.hasOwnProperty.call(body, 'enabled');
  const hasName = Object.prototype.hasOwnProperty.call(body, 'name');
  if (hasEnabled) {
    key.enabled = Boolean(body.enabled);
  }
  if (hasName) {
    const cleanName = String(body.name || '').trim();
    if (!cleanName) {
      throw publicError(400, 'API Key 名称不能为空');
    }
    key.name = cleanName.slice(0, 80);
  }
  key.updatedAt = new Date().toISOString();
  if (hasEnabled) {
    data.events.push({
      type: key.enabled ? 'key_enabled' : 'key_disabled',
      userId: user.id,
      keyId: key.id,
      at: key.updatedAt,
    });
  }
  if (hasName) {
    data.events.push({
      type: 'key_renamed',
      userId: user.id,
      keyId: key.id,
      at: key.updatedAt,
    });
  }
  return { key: sanitizeUserKey(key, { revealSecret: true }) };
}

function deleteCustomerToken(data, request, keyId) {
  const { user } = requireSession(data, request);
  const index = data.userKeys.findIndex((item) => item.userId === user.id && item.id === keyId);
  if (index === -1) {
    throw publicError(404, 'API Key 不存在');
  }
  const [deleted] = data.userKeys.splice(index, 1);
  const now = new Date().toISOString();
  data.events.push({
    type: 'key_deleted',
    userId: user.id,
    keyId: deleted.id,
    at: now,
  });
  return { deletedKeyId: deleted.id };
}

function buildCustomerImportUrl(data, request, url, serverOptions) {
  const { user } = requireSession(data, request);
  const targetModelGroup = normalizeModelGroup(
    url.searchParams.get('modelGroup') || inferProviderGroup(url.searchParams.get('model') || ''),
  );
  const requestedKeyId = String(url.searchParams.get('keyId') || '').trim();
  const enabledKeys = data.userKeys.filter((item) => item.userId === user.id && item.enabled);
  const key =
    enabledKeys.find((item) => requestedKeyId && item.id === requestedKeyId) ||
    enabledKeys.find((item) => targetModelGroup !== 'All' && normalizeModelGroup(item.modelGroup) === targetModelGroup) ||
    enabledKeys.find((item) => targetModelGroup !== 'All' && normalizeModelGroup(item.modelGroup) === 'All') ||
    enabledKeys[0];
  if (!key) {
    throw publicError(409, '没有可用的 API Key');
  }

  const target = url.searchParams.get('target') || 'Claude';
  const requestedModel = url.searchParams.get('model') || '';
  const baseUrl = serverOptions.publicGatewayBaseUrl || `${requestOrigin(request)}/v1`;
  const { availableModels, defaultModel } = customerImportModelSelection(data, user, key, requestedModel);
  const config = buildClientConfig({
    target,
    apiKey: key.secret,
    baseUrl,
    model: requestedModel || defaultModel,
    defaultModel,
    availableModels,
    modelGroup: key.modelGroup,
    planExpiresAt: user.planExpiresAt,
    preferExplicitDefaultModel: Boolean(requestedModel || defaultModel),
  });
  const setup = buildClientSetupCommands(config);
  return {
    url: config.ccSwitchUrl,
    config,
    setup,
    defaultModel,
    availableModels,
  };
}

function buildKeyUsagePayload(data, request, serverOptions) {
  const key = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === key.userId);
  if (!user) {
    throw publicError(401, '用户不存在');
  }
  expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
  const account = accountFromUser(data, user);
  const remainingCents = Number(user.balanceCents || 0);
  const usedMonthCents = sumUserGatewayCost(data, user.id, currentDate(serverOptions).toISOString().slice(0, 7));
  const totalCents = remainingCents + usedMonthCents;
  return {
    ok: true,
    valid: true,
    keyPreview: sanitizeUserKey(key).preview,
    plan: user.plan || '默认套餐',
    renewalDate: user.renewalDate || '-',
    remainingUsd: usdNumberFromCnyCents(remainingCents),
    usedUsd: usdNumberFromCnyCents(usedMonthCents),
    totalUsd: usdNumberFromCnyCents(totalCents),
    remainingCny: cnyNumberFromCents(remainingCents),
    usedCny: cnyNumberFromCents(usedMonthCents),
    totalCny: cnyNumberFromCents(totalCents),
    balance: account.balance,
    packageQuota: account.packageQuota,
    boosterQuota: account.boosterQuota,
    todayCost: account.todayCost,
    monthCost: account.monthCost,
    todayCalls: account.todayCalls,
    todayTokens: account.todayTokens,
    totalTokens: account.totalTokens,
    averageLatency: account.averageLatency,
    successRate: account.successRate,
  };
}

function buildDashboard(data, user, serverOptions) {
  expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
  const apiKeys = data.userKeys
    .filter((item) => item.userId === user.id)
    .map((item) => sanitizeUserKey(item));
  return {
    authenticated: true,
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email),
    apiKeys,
    modelUsage: buildModelUsage(data, user),
    channelChecks: buildChannelChecks(data),
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
    usageRecords: buildUsageRecords(data, user),
    usageAnomalies: buildUsageAnomalies(data, user),
    recentLogs: buildRecentLogs(data, user),
  };
}

function buildGuestDashboard(data) {
  return {
    authenticated: false,
    account: {
      plan: '未登录',
      renewalDate: '-',
      balance: '$0.00',
      todayCost: '$0.00',
      monthCost: '$0.00',
      packageQuota: '$0.00',
      boosterQuota: '$0.00',
      quotaLeft: '$0.00',
      usageTotal: '$0.00',
      todayCalls: '0 次',
    },
    user: {
      id: '',
      email: '',
      emailVerified: false,
      plan: '未登录',
      renewalDate: '-',
      userInitials: 'FA',
    },
    balanceAlert: sanitizeBalanceAlert(defaultBalanceAlert(''), ''),
    apiKeys: [],
    modelUsage: [],
    channelChecks: [],
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
    usageRecords: [],
    usageAnomalies: [],
    recentLogs: [],
  };
}

async function replenishCredentials(data, body, serverOptions) {
  const parsedOrder = body.orderText ? parseSupplierOrderText(body.orderText, body.pricing || {}) : null;
  const normalizedBaseUrl = normalizeBaseUrl(body.baseUrl || parsedOrder?.baseUrl);
  const normalizedProxyBaseUrl = String(body.proxyBaseUrl || '').trim() ? normalizeBaseUrl(body.proxyBaseUrl) : '';
  await assertSafeUpstreamBaseUrl(normalizedBaseUrl, serverOptions);
  if (normalizedProxyBaseUrl) {
    await assertSafeUpstreamBaseUrl(normalizedProxyBaseUrl, serverOptions);
  }
  const pool = normalizePool(body.pool || parsedOrder?.pool || 'default');
  const modelGroup = normalizeModelGroup(body.modelGroup || parsedOrder?.providerGroup || '');
  const cardType = normalizePool(body.cardType || parsedOrder?.cardType || pool);
  const expiresAt = String(body.expiresAt || parsedOrder?.expiresAt || '');
  const sourceType = normalizeSourceType(body.sourceType || PRIMARY_SOURCE_TYPE);
  const riskStatus = normalizeRiskStatus(
    body.riskStatus || (sourceType === PRIMARY_SOURCE_TYPE ? 'approved' : 'quarantined'),
  );
  const backupRiskAccepted = Boolean(body.backupRiskAccepted || body.manualRiskAccepted);
  const riskNote = sanitizeRiskNote(body.riskNote || '');
  const routeApproved = isSourceRouteApproved({ sourceType, riskStatus, backupRiskAccepted });
  const gatedStatus = routeApproved ? 'healthy' : riskStatus === 'blocked' ? 'blocked' : 'quarantined';
  const now = new Date().toISOString();
  const keyInputs = normalizeReplenishmentKeys(body.keys ?? parsedOrder?.keys ?? []);
  if (keyInputs.length === 0) {
    throw publicError(400, 'Key 列表不能为空');
  }

  const providedModels = normalizeModels(body.models ?? parsedOrder?.models ?? [], { allowEmpty: true });
  const probeMode = String(body.probeMode || (providedModels.length > 0 ? 'trusted' : 'auto'));
  const probeReport = await probeReplenishment({
    baseUrl: normalizedBaseUrl,
    proxyBaseUrl: normalizedProxyBaseUrl,
    keyInputs,
    models: providedModels,
    modelGroup,
    probeMode,
    serverOptions,
  });
  const models = providedModels.length > 0 ? providedModels : probeReport.models;
  const sourceGroup = modelGroup || inferProviderGroup(models.join('\n'));
  const sourceFingerprint =
    sourceType === PRIMARY_SOURCE_TYPE
      ? `${normalizedBaseUrl}:${sourceGroup}`
      : `${sourceType}:${normalizedBaseUrl}:${sourceGroup}`;
  const sourceId = `source-${hashId(sourceFingerprint)}`;
  const source = upsertSupplierProfile(data, {
    id: sourceId,
    baseUrl: normalizedBaseUrl,
    proxyBaseUrl: normalizedProxyBaseUrl,
    routeBaseUrl: probeReport.routeBaseUrl,
    pool,
    models,
    modelGroup: sourceGroup,
    cardType,
    expiresAt,
    sourceType,
    riskStatus: gatedStatus === 'healthy' ? 'approved' : riskStatus,
    backupRiskAccepted,
    riskNote,
    connectionPath: probeReport.connectionPath,
    updatedAt: now,
  });

  const failedKeys = [];
  const credentials = [];
  for (const key of keyInputs) {
    const probe = probeReport.keyResults.get(key.value) || { ok: true, reason: '信任写入' };
    if (!probe.ok) {
      failedKeys.push({
        keyPreview: maskKey(key.value),
        reason: probe.reason || '检测失败',
        status: probe.status || 'probe_failed',
      });
      continue;
    }

    const credentialModels = providedModels.length > 0 ? models : probe.models?.length ? probe.models : models;
    const credential = upsertCredential(data, {
      sourceId: source.id,
      baseUrl: normalizedBaseUrl,
      proxyBaseUrl: normalizedProxyBaseUrl,
      routeBaseUrl: probe.routeBaseUrl || probeReport.routeBaseUrl || normalizedBaseUrl,
      connectionPath: probe.connectionPath || probeReport.connectionPath || 'direct',
      rawKey: key.value,
      keyPreview: maskKey(key.value),
      pool,
      modelGroup: key.modelGroup || modelGroup || inferProviderGroup(credentialModels.join('\n')),
      cardType: key.cardType || cardType,
      expiresAt: key.expiresAt || expiresAt,
      quotaTotal: Number.isFinite(key.quotaTotal) ? key.quotaTotal : Number(probe.quotaTotal || key.quotaRemaining || probe.quotaRemaining || 1000),
      authHeaderName: key.authHeaderName || 'authorization',
      authHeaderValuePrefix: key.authHeaderValuePrefix ?? 'Bearer',
      extraHeaders: sanitizeExtraHeaders(key.extraHeaders),
      models: credentialModels,
      sourceType,
      riskStatus: gatedStatus === 'healthy' ? 'approved' : riskStatus,
      backupRiskAccepted,
      riskNote,
      enabled: routeApproved,
      status: gatedStatus,
      quotaRemaining: Number.isFinite(key.quotaRemaining) ? key.quotaRemaining : Number(probe.quotaRemaining || 1000),
      latencyMs: resolveProbeLatencyMs(key, probe),
      lastProbeStatus: probe.status || probeMode,
      lastProbeReason: routeApproved ? probe.reason || '' : riskNote || '备用渠道待人工风险放行',
      createdAt: now,
      updatedAt: now,
    });
    credentials.push(credential);
  }

  const priceDrafts = parsePriceText(body.priceText || '', body.pricing || {}).map((draft) => ({
    id: createId('price'),
    sourceId: source.id,
    ...draft,
    createdAt: now,
  }));
  data.priceDrafts.push(...priceDrafts);
  data.events.push({
    type: 'replenished',
    sourceId: source.id,
    pool,
    modelGroup,
    credentialCount: credentials.length,
    failedCount: failedKeys.length,
    probeMode,
    sourceType,
    riskStatus,
    routeApproved,
    at: now,
  });

  return {
    supplierProfile: source,
    credentials: credentials.map(sanitizeCredential),
    failedKeys,
    priceDrafts,
    inventorySummary: buildInventorySummary(data),
    events: sanitizeAdminEvents(data.events),
  };
}

async function probeReplenishment({ baseUrl, proxyBaseUrl, keyInputs, models, modelGroup = '', probeMode, serverOptions }) {
  if (probeMode === 'trusted') {
    const routeBaseUrl = proxyBaseUrl || baseUrl;
    return {
      connectionPath: proxyBaseUrl ? 'proxy' : 'direct',
      routeBaseUrl,
      models: models.length > 0 ? models : DEFAULT_PROBE_MODELS,
      keyResults: new Map(
        keyInputs.map((key) => [
          key.value,
          {
            ok: true,
            status: 'trusted',
            reason: '信任写入',
            connectionPath: proxyBaseUrl ? 'proxy' : 'direct',
            routeBaseUrl,
          },
        ]),
      ),
    };
  }

  const keyResults = new Map();
  let detectedModels = models;
  if (detectedModels.length === 0) {
    detectedModels = await detectSupplierModels(baseUrl, proxyBaseUrl, keyInputs, serverOptions);
  }
  const candidateModels = detectedModels.length > 0 ? detectedModels : DEFAULT_PROBE_MODELS;
  const shouldCollectSupportedModels = models.length === 0 && detectedModels.length === 0;
  for (const key of keyInputs) {
    const probe = await probeCredentialRoutes({
      baseUrl,
      proxyBaseUrl,
      rawKey: key.value,
      authConfig: key,
      models: candidateModels,
      serverOptions,
      collectAllModels: shouldCollectSupportedModels,
      preferAnthropicMessages: normalizeModelGroup(key.modelGroup || modelGroup || '') === 'Claude',
    });
    keyResults.set(key.value, probe);
  }

  const healthyProbes = [...keyResults.values()].filter((probe) => probe.ok);
  const routeVotes = healthyProbes.reduce(
    (counts, probe) => {
      counts[probe.connectionPath || 'direct'] += 1;
      return counts;
    },
    { direct: 0, proxy: 0 },
  );
  const connectionPath = routeVotes.proxy > routeVotes.direct ? 'proxy' : 'direct';
  const routeBaseUrl = connectionPath === 'proxy' && proxyBaseUrl ? proxyBaseUrl : baseUrl;
  const successfulModels = shouldCollectSupportedModels
    ? uniqueStrings(healthyProbes.flatMap((probe) => probe.models || []))
    : candidateModels;

  return {
    connectionPath,
    routeBaseUrl,
    models: successfulModels.length > 0 ? successfulModels : candidateModels,
    keyResults,
  };
}

async function detectSupplierModels(baseUrl, proxyBaseUrl, keyInputs, serverOptions) {
  for (const key of keyInputs) {
    const probe = await probeCredentialModels(baseUrl, key.value, serverOptions, key);
    if (probe.ok && probe.models.length > 0) {
      return probe.models;
    }
    if (probe.ok && probe.status === 'models_not_supported') {
      if (proxyBaseUrl) {
        const proxyProbe = await probeCredentialModels(proxyBaseUrl, key.value, serverOptions, key);
        if (proxyProbe.ok && proxyProbe.models.length > 0) {
          return proxyProbe.models;
        }
      }
      return [];
    }
  }
  return [];
}

async function probeCredentialModels(baseUrl, rawKey, serverOptions, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }
  try {
    await assertSafeUpstreamBaseUrl(baseUrl, serverOptions);
  } catch (error) {
    return { ok: false, status: 'network_failed', reason: error.message || '请求地址不可达', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/models`, {
      method: 'GET',
      headers: authHeadersForKey(rawKey, authConfig),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    const models = parseModelIds(bodyText);
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models };
    }
    if (response.status >= 200 && response.status < 300) {
      return { ok: true, status: models.length > 0 ? 'models_detected' : 'reachable', reason: '', models };
    }
    if (response.status === 404 || response.status === 405) {
      return { ok: true, status: 'models_not_supported', reason: '上游不支持模型列表接口', models: [] };
    }
    return { ok: false, status: 'http_failed', reason: `上游返回 HTTP ${response.status}`, models };
  } catch (error) {
    return { ok: false, status: 'network_failed', reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达', models: [] };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialRoutes({
  baseUrl,
  proxyBaseUrl,
  rawKey,
  authConfig = {},
  models,
  serverOptions,
  collectAllModels,
  preferAnthropicMessages = false,
}) {
  const direct = await probeCredentialRouteCandidates(baseUrl, rawKey, models, serverOptions, {
    collectAllModels,
    authConfig,
    preferAnthropicMessages,
  });
  if (!proxyBaseUrl) {
    return {
      ...direct,
      connectionPath: 'direct',
      routeBaseUrl: direct.routeBaseUrl || baseUrl,
    };
  }

  const proxy = await probeCredentialRouteCandidates(proxyBaseUrl, rawKey, models, serverOptions, {
    collectAllModels,
    authConfig,
    preferAnthropicMessages,
  });
  const connectionPath = recommendConnectionPath({
    direct: { ok: direct.ok, p95Ms: direct.latencyMs || 999999, failureRate: direct.ok ? 0 : 1 },
    proxy: { ok: proxy.ok, p95Ms: proxy.latencyMs || 999999, failureRate: proxy.ok ? 0 : 1 },
  });
  if (connectionPath === 'proxy') {
    return {
      ...proxy,
      connectionPath,
      routeBaseUrl: proxy.routeBaseUrl || proxyBaseUrl,
    };
  }
  if (connectionPath === 'direct') {
    return {
      ...direct,
      connectionPath,
      routeBaseUrl: direct.routeBaseUrl || baseUrl,
    };
  }

  return {
    ...direct,
    ok: false,
    status: direct.status || proxy.status || 'network_failed',
    reason: direct.reason || proxy.reason || '直连和代理均不可用',
    connectionPath: 'direct',
    routeBaseUrl: baseUrl,
  };
}

async function probeCredentialRouteCandidates(baseUrl, rawKey, models, serverOptions, options = {}) {
  let lastProbe = null;
  for (const routeBaseUrl of routeBaseUrlCandidates(baseUrl)) {
    const probe = await probeCredentialChat(routeBaseUrl, rawKey, models, serverOptions, options);
    if (probe.ok) {
      return { ...probe, routeBaseUrl };
    }
    lastProbe = probe;
    if (['auth_failed', 'quota_failed'].includes(probe.status)) {
      break;
    }
  }
  return {
    ...(lastProbe || { ok: false, status: 'network_failed', reason: '请求地址不可达', models: [] }),
    routeBaseUrl: normalizeBaseUrl(baseUrl),
  };
}

function routeBaseUrlCandidates(baseUrl) {
  const normalized = normalizeBaseUrl(baseUrl);
  const candidates = [normalized];
  try {
    const parsed = new URL(normalized);
    const pathname = parsed.pathname.replace(/\/+$/, '');
    if (!/(^|\/)v1$/i.test(pathname)) {
      parsed.pathname = `${pathname}/v1`.replace(/\/+/g, '/');
      candidates.push(normalizeBaseUrl(parsed.toString()));
    }
  } catch {
    // normalizeBaseUrl 已经处理常见输入；极端解析失败时保留原始候选地址。
  }
  return [...new Set(candidates)];
}

function isRootUpstreamBaseUrl(baseUrl) {
  try {
    const pathname = new URL(normalizeBaseUrl(baseUrl)).pathname.replace(/\/+$/, '');
    return pathname === '';
  } catch {
    return false;
  }
}

async function probeCredentialChat(baseUrl, rawKey, models, serverOptions, options = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const supportedModels = [];
  let bestLatencyMs = 0;
  let lastFailure = null;

  for (const model of models) {
    if (options.preferAnthropicMessages && inferProviderGroup(model) === 'Claude') {
      const anthropicProbe = await probeCredentialAnthropicMessages(
        baseUrl,
        rawKey,
        model,
        serverOptions,
        Date.now(),
        options.authConfig || {},
      );
      if (anthropicProbe.status === 'auth_failed' || anthropicProbe.status === 'quota_failed' || anthropicProbe.status === 'network_failed') {
        return anthropicProbe;
      }
      if (anthropicProbe.ok) {
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, anthropicProbe.latencyMs) : anthropicProbe.latencyMs;
        if (!options.collectAllModels) {
          return anthropicProbe;
        }
        continue;
      }
      if (!isGatewayAdapterUnsupported({ status: anthropicProbe.httpStatus, bodyText: anthropicProbe.bodyText })) {
        lastFailure = anthropicProbe;
        if (!options.collectAllModels) {
          return lastFailure;
        }
      } else if (isRootUpstreamBaseUrl(baseUrl)) {
        return anthropicProbe;
      }
    }

    if (isImageGenerationModel(model)) {
      const imageProbe = await probeCredentialImageGeneration(
        baseUrl,
        rawKey,
        model,
        serverOptions,
        Date.now(),
        options.authConfig || {},
      );
      if (imageProbe.status === 'auth_failed' || imageProbe.status === 'quota_failed' || imageProbe.status === 'network_failed') {
        return imageProbe;
      }
      if (imageProbe.ok) {
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, imageProbe.latencyMs) : imageProbe.latencyMs;
        if (!options.collectAllModels) {
          return imageProbe;
        }
        continue;
      }
      if (isModelUnsupportedResponse(imageProbe.httpStatus, imageProbe.bodyText)) {
        continue;
      }
      lastFailure = imageProbe;
      if (!options.collectAllModels) {
        return lastFailure;
      }
      continue;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
    const startedAt = Date.now();
    try {
      const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/chat/completions`, {
        method: 'POST',
        headers: {
          ...authHeadersForKey(rawKey, options.authConfig || {}),
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
          stream: false,
        }),
        signal: controller.signal,
      });
      const bodyText = await response.text();
      if (response.status === 401 || response.status === 403) {
        return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [] };
      }
      if (response.status === 402 || response.status === 429) {
        return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [] };
      }
      if (response.status >= 200 && response.status < 300) {
        if (!isOpenAiChatCompletionPayload(bodyText)) {
          lastFailure = {
            ok: false,
            status: 'adapter_unsupported',
            reason: '上游返回非 OpenAI 兼容响应',
            models: [],
            httpStatus: response.status,
            bodyText,
          };
          if (!options.collectAllModels) {
            return lastFailure;
          }
          continue;
        }
        const latencyMs = Math.max(1, Date.now() - startedAt);
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, latencyMs) : latencyMs;
        if (!options.collectAllModels) {
          return {
            ok: true,
            status: 'chat_probe_ok',
            reason: '',
            models: [model],
            latencyMs,
          };
        }
        continue;
      }
      if (shouldTryResponsesProbe(response.status, bodyText)) {
        const responsesProbe = await probeCredentialResponses(
          baseUrl,
          rawKey,
          model,
          serverOptions,
          startedAt,
          options.authConfig || {},
        );
        if (responsesProbe.status === 'auth_failed' || responsesProbe.status === 'quota_failed' || responsesProbe.status === 'network_failed') {
          return responsesProbe;
        }
        if (responsesProbe.ok) {
          supportedModels.push(model);
          bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, responsesProbe.latencyMs) : responsesProbe.latencyMs;
          if (!options.collectAllModels) {
            return responsesProbe;
          }
          continue;
        }
        if (isModelUnsupportedResponse(responsesProbe.httpStatus, responsesProbe.bodyText)) {
          continue;
        }
        lastFailure = responsesProbe;
        if (!options.collectAllModels) {
          return lastFailure;
        }
        continue;
      }
      if (isModelUnsupportedResponse(response.status, bodyText)) {
        continue;
      }
      lastFailure = { ok: false, status: 'http_failed', reason: `上游返回 HTTP ${response.status}`, models: [] };
      if (!options.collectAllModels) {
        return lastFailure;
      }
    } catch (error) {
      return {
        ok: false,
        status: 'network_failed',
        reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
        models: [],
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  if (supportedModels.length > 0) {
    return {
      ok: true,
      status: 'chat_probe_ok',
      reason: '',
      models: supportedModels,
      latencyMs: bestLatencyMs || 999,
    };
  }

  if (lastFailure) {
    return lastFailure;
  }

  return { ok: false, status: 'model_failed', reason: '预设模型均不可用', models: [] };
}

async function probeCredentialAnthropicMessages(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/messages`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'ping' }],
        max_tokens: 1,
        stream: false,
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isAnthropicMessagePayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 Anthropic Messages 响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'anthropic_messages_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialImageGeneration(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/images/generations`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        prompt: 'ping',
        size: '1024x1024',
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isOpenAiImageGenerationPayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 OpenAI 图片响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'image_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialResponses(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/responses`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        input: [{ role: 'user', content: [{ type: 'input_text', text: 'ping' }] }],
        max_output_tokens: 1,
        stream: false,
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isOpenAiResponsesPayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 OpenAI Responses 响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'responses_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}

function shouldTryResponsesProbe(status, bodyText) {
  return status === 404 || status === 405 || isModelUnsupportedResponse(status, bodyText);
}

function isOpenAiChatCompletionPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return Array.isArray(payload.choices);
}

function isOpenAiResponsesPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return payload.object === 'response' || Array.isArray(payload.output) || typeof payload.output_text === 'string';
}

function isOpenAiImageGenerationPayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return Array.isArray(payload.data);
}

function isAnthropicMessagePayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return payload.type === 'message' && Array.isArray(payload.content);
}

function isModelUnsupportedResponse(status, bodyText) {
  return (status === 400 || status === 404) && /model|not found|unsupported|not supported|不存在|不支持/i.test(bodyText || '');
}

function isImageGenerationModel(model) {
  return /image|dall/i.test(String(model || ''));
}

function parseModelIds(bodyText) {
  try {
    const payload = JSON.parse(bodyText || '{}');
    if (!Array.isArray(payload.data)) return [];
    return normalizeOfficialModelList(
      payload.data
        .map((item) => String(item.id || item.name || '').trim())
        .filter(Boolean),
    );
  } catch {
    return [];
  }
}

function uniqueStrings(values) {
  return [...new Set(values.map((value) => normalizeOfficialModelName(value)).filter(Boolean))];
}

async function routeChatCompletion(data, request, body, serverOptions, options = {}) {
  const userKey = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === userKey.userId);
  if (!user) {
    throw publicError(401, '用户不存在');
  }

  const model = normalizeOfficialModelName(body.model);
  if (!model) {
    throw publicError(400, '缺少模型名称');
  }
  if (!modelMatchesGroup(model, userKey.modelGroup || 'All')) {
    throw publicError(403, '当前 API Key 的模型分组不匹配，请创建对应分组的 Key');
  }

  const routedBody = { ...body, model };
  const estimatedQuotaCost = estimateQuotaCostCents(data, model, routedBody, serverOptions);
  expireUserPlanIfNeeded(data, user, serverOptions);
  if (availableQuotaCents(user) < estimatedQuotaCost) {
    throw publicError(402, '余额不足，请先充值或兑换套餐');
  }

  const allowedPools = allowedPoolsForUser(user);
  const sessionKey = buildGatewayAffinityKey(request, body, userKey, model);
  const candidates = orderGatewayCandidates(
    data,
    data.credentials
      .filter((credential) => allowedPools.includes(credential.pool))
      .filter((credential) => credential.enabled)
      .filter((credential) => credential.status === 'healthy')
      .filter(isCredentialRouteApproved)
      .filter((credential) => normalizeOfficialModelList(credential.models).includes(model) || credential.models.includes('*'))
      .filter((credential) => credentialMatchesModelGroup(credential, model, userKey.modelGroup))
      .sort(compareGatewayCredentials),
    sessionKey,
  );

  for (const credential of candidates) {
    if (Number(credential.quotaRemaining || 0) < estimatedQuotaCost) {
      exhaustCredential(data, credential, 'quota_too_low_before_request');
      await maybeNotifyCredentialIssue(data, credential, 'quota_too_low_before_request', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    let upstream;
    try {
      upstream = await callGatewayAttempts(credential, routedBody, serverOptions, options);
    } catch {
      failCredential(data, credential, 'upstream_network_failed');
      await maybeNotifyCredentialIssue(data, credential, 'upstream_network_failed', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (isQuotaExhaustedResponse(upstream)) {
      exhaustCredential(data, credential, 'quota_exhausted_by_upstream');
      await maybeNotifyCredentialIssue(data, credential, 'quota_exhausted_by_upstream', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (shouldFailoverUpstream(upstream)) {
      failCredential(data, credential, `upstream_http_${upstream.status}`);
      await maybeNotifyCredentialIssue(data, credential, `upstream_http_${upstream.status}`, serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    if (upstream.status >= 200 && upstream.status < 300) {
      const quotaCost = resolveQuotaCostCents(data, model, routedBody, upstream, serverOptions);
      const usage = parseUpstreamUsage(upstream.bodyText);
      const beforeUserQuota = availableQuotaCents(user);
      const client = clientLabelFromRequest(request, routedBody);
      credential.quotaRemaining = Math.max(0, Number(credential.quotaRemaining || 0) - quotaCost);
      credential.status = credential.quotaRemaining > 0 ? 'healthy' : 'exhausted';
      credential.enabled = credential.quotaRemaining > 0;
      credential.updatedAt = new Date().toISOString();
      deductUserQuota(user, quotaCost);
      userKey.costCents += quotaCost;
      userKey.totalTokens = Number(userKey.totalTokens || 0) + Number(usage.totalTokens || 0);
      userKey.tokens = compactTokenText(userKey.totalTokens);
      userKey.lastUsed = credential.updatedAt.slice(11, 16);
      userKey.updatedAt = credential.updatedAt;
      data.events.push({
        type: 'gateway_routed',
        userId: user.id,
        keyId: userKey.id,
        credentialId: credential.id,
        model,
        pool: credential.pool,
        quotaCost,
        endpoint: credential.baseUrl,
        client,
        apiKeyPreview: userKey.preview || maskKey(userKey.secret),
        inferenceEffort: String(routedBody.reasoning_effort || routedBody.reasoning?.effort || routedBody.thinking?.budget_tokens || '默认'),
        requestType: options.requestType || (isImageGenerationModel(model) ? '图片' : '文本'),
        billingMode: credential.pool === 'day' || credential.pool === 'hour' || credential.pool === 'month' ? '套餐' : '余额',
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        totalTokens: usage.totalTokens,
        latencyMs: Number(upstream.latencyMs || credential.latencyMs || 0),
        status: 'success',
        at: credential.updatedAt,
      });
      recordChannelProbeEvent(data, credential, Number(upstream.latencyMs || credential.latencyMs || 0) > 1600 ? 'slow' : 'ok', 'gateway_success', serverOptions, {
        latencyMs: Number(upstream.latencyMs || credential.latencyMs || 0),
      });
      rememberRouteAffinity(data, sessionKey, {
        userId: user.id,
        keyId: userKey.id,
        credentialId: credential.id,
        model,
        pool: credential.pool,
        updatedAt: credential.updatedAt,
      });
      await maybeNotifyLowInventory(data, credential, serverOptions);
      await maybeNotifyCustomerLowBalance(data, user, serverOptions, {
        beforeUserQuota,
        afterUserQuota: availableQuotaCents(user),
        quotaCost,
        model,
      });
      return upstream;
    }

    return upstream;
  }

  return gatewayUnavailableResponse();
}

async function callGatewayAttempts(credential, body, serverOptions, options = {}) {
  const attempts = options.upstreamAttempts?.length
    ? options.upstreamAttempts
    : [{ upstreamPath: options.upstreamPath || '/chat/completions' }];
  let lastUpstream = null;

  for (const [index, attempt] of attempts.entries()) {
    const upstreamBody = attempt.transformRequest ? attempt.transformRequest(body) : body;
    const upstream = await callUpstreamChatCompletion(credential, upstreamBody, serverOptions, {
      streamResponse: body.stream === true && !attempt.transformResponse,
      upstreamPath: attempt.upstreamPath,
      request: options.request,
    });
    if (
      attempt.validateResponse &&
      upstream.status >= 200 &&
      upstream.status < 300 &&
      !upstream.bodyStream &&
      !attempt.validateResponse(upstream.bodyText)
    ) {
      lastUpstream = {
        ...upstream,
        status: 415,
        bodyText: JSON.stringify({ error: '上游返回格式不兼容' }),
      };
      continue;
    }
    if (isGatewayAdapterUnsupported(upstream) && index < attempts.length - 1) {
      lastUpstream = upstream;
      continue;
    }
    return attempt.transformResponse ? attempt.transformResponse(upstream, body, upstreamBody) : upstream;
  }

  return lastUpstream;
}

function gatewayUnavailableResponse() {
  return {
    status: 503,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({ error: '当前模型暂不可用' }),
  };
}

function shouldFailoverUpstream(upstream) {
  return upstream.status === 408 || upstream.status >= 500 || isCredentialRejectedResponse(upstream) || isGatewayAdapterUnsupported(upstream);
}

function isGatewayAdapterUnsupported(upstream) {
  if (!upstream || ![400, 404, 405, 415].includes(upstream.status)) {
    return false;
  }
  return /not found|unsupported|not supported|unknown endpoint|cannot\s+post|不存在|不支持/i.test(upstream.bodyText || '');
}

function isCredentialRejectedResponse(upstream) {
  if (!upstream || ![401, 403].includes(upstream.status)) {
    return false;
  }
  return /invalid api key|missing api key|unauthorized|forbidden|token|api key|认证|鉴权|密钥/i.test(upstream.bodyText || '');
}

function anthropicMessagesToChatCompletion(body) {
  const messages = [];
  const system = anthropicContentToText(body.system);
  if (system) {
    messages.push({ role: 'system', content: system });
  }
  for (const message of body.messages || []) {
    messages.push({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: anthropicContentToText(message.content),
    });
  }
  return compactObject({
    model: body.model,
    messages,
    max_tokens: body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stop: body.stop_sequences,
    stream: body.stream,
    metadata: body.metadata,
  });
}

function anthropicContentToText(content) {
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part?.type === 'text') return part.text || '';
        if (part?.type === 'tool_result') return typeof part.content === 'string' ? part.content : JSON.stringify(part.content || {});
        if (part?.type === 'image') return '[图片]';
        return JSON.stringify(part || {});
      })
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

function responsesRequestToChatCompletion(body) {
  return compactObject({
    model: body.model,
    messages: responsesInputToMessages(body.input ?? body.messages ?? body.prompt),
    max_tokens: body.max_output_tokens || body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stream: body.stream,
    metadata: body.metadata,
  });
}

function chatCompletionRequestToResponses(body) {
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const instructions = messages
    .filter((message) => message.role === 'system' || message.role === 'developer')
    .map((message) => chatMessageContentToText(message.content))
    .filter(Boolean)
    .join('\n\n');
  const inputMessages = messages
    .filter((message) => message.role !== 'system' && message.role !== 'developer')
    .map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: chatContentToResponsesContent(message.content),
    }));

  return compactObject({
    model: body.model,
    instructions,
    input: inputMessages.length ? inputMessages : responsesInputToMessages(body.prompt || '').map((message) => ({
      role: message.role,
      content: chatContentToResponsesContent(message.content),
    })),
    max_output_tokens: body.max_completion_tokens || body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stream: false,
    metadata: body.metadata,
  });
}

function chatContentToResponsesContent(content) {
  if (typeof content === 'string') {
    return [{ type: 'input_text', text: content }];
  }
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === 'string') return { type: 'input_text', text: part };
      if (part?.type === 'text') return { type: 'input_text', text: part.text || '' };
      if (part?.type === 'image_url') {
        return { type: 'input_image', image_url: part.image_url?.url || part.image_url || '' };
      }
      return { type: 'input_text', text: JSON.stringify(part || {}) };
    });
  }
  return [{ type: 'input_text', text: content ? JSON.stringify(content) : '' }];
}

function responsesInputToMessages(input) {
  if (Array.isArray(input)) {
    return input.map((item) => ({
      role: item.role === 'assistant' || item.role === 'system' ? item.role : 'user',
      content: responsesContentToText(item.content ?? item),
    }));
  }
  return [{ role: 'user', content: responsesContentToText(input) }];
}

function responsesContentToText(content) {
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part?.type === 'input_text' || part?.type === 'output_text' || part?.type === 'text') return part.text || '';
        if (part?.type === 'input_image') return '[图片]';
        return JSON.stringify(part || {});
      })
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

function chatCompletionToAnthropicMessageResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const choice = payload.choices?.[0] || {};
  const text = chatMessageContentToText(choice.message?.content);
  const usage = payload.usage || {};
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: payload.id || createId('msg'),
      type: 'message',
      role: 'assistant',
      model: payload.model || originalBody.model,
      content: [{ type: 'text', text }],
      stop_reason: choice.finish_reason === 'length' ? 'max_tokens' : 'end_turn',
      stop_sequence: null,
      usage: {
        input_tokens: Number(usage.prompt_tokens || usage.input_tokens || 0),
        output_tokens: Number(usage.completion_tokens || usage.output_tokens || 0),
      },
    }),
  };
}

function responsesToChatCompletionResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const usage = payload.usage || {};
  const inputTokens = Number(usage.prompt_tokens || usage.input_tokens || 0);
  const outputTokens = Number(usage.completion_tokens || usage.output_tokens || 0);
  const id = String(payload.id || createId('resp'));
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: id.startsWith('chatcmpl') ? id : `chatcmpl_${id}`,
      object: 'chat.completion',
      created: Number(payload.created || payload.created_at || Math.floor(Date.now() / 1000)),
      model: payload.model || originalBody.model,
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: responsesOutputToText(payload),
          },
          finish_reason: responseFinishReason(payload),
        },
      ],
      usage: {
        prompt_tokens: inputTokens,
        completion_tokens: outputTokens,
        total_tokens: Number(usage.total_tokens || inputTokens + outputTokens),
      },
    }),
  };
}

function responsesOutputToText(payload) {
  if (typeof payload.output_text === 'string') {
    return payload.output_text;
  }
  return (payload.output || [])
    .flatMap((item) => item.content || [])
    .map((part) => {
      if (typeof part === 'string') return part;
      if (part?.type === 'output_text' || part?.type === 'text') return part.text || '';
      return part ? JSON.stringify(part) : '';
    })
    .filter(Boolean)
    .join('\n');
}

function responseFinishReason(payload) {
  if (payload.status === 'incomplete') return 'length';
  if (payload.status === 'failed') return 'error';
  return 'stop';
}

function chatCompletionToResponsesResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const choice = payload.choices?.[0] || {};
  const text = chatMessageContentToText(choice.message?.content);
  const usage = payload.usage || {};
  const inputTokens = Number(usage.prompt_tokens || usage.input_tokens || 0);
  const outputTokens = Number(usage.completion_tokens || usage.output_tokens || 0);
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: `resp_${payload.id || createId('chat')}`,
      object: 'response',
      status: 'completed',
      model: payload.model || originalBody.model,
      output: [
        {
          id: `msg_${payload.id || createId('chat')}`,
          type: 'message',
          role: 'assistant',
          content: [{ type: 'output_text', text, annotations: [] }],
        },
      ],
      usage: {
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: Number(usage.total_tokens || inputTokens + outputTokens),
      },
    }),
  };
}

function chatMessageContentToText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === 'string' ? part : part?.text || JSON.stringify(part || {})))
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

function parseJsonPayload(bodyText) {
  try {
    return JSON.parse(bodyText || '{}');
  } catch {
    return {};
  }
}

function compactObject(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ''),
  );
}

async function callUpstreamChatCompletion(credential, body, serverOptions, options = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw publicError(500, '当前 Node 环境缺少 fetch');
  }

  const upstreamPath = String(options.upstreamPath || '/chat/completions').startsWith('/')
    ? options.upstreamPath
    : `/${options.upstreamPath}`;
  const upstreamBaseUrl = normalizeBaseUrl(credential.routeBaseUrl || credential.baseUrl);
  await assertSafeUpstreamBaseUrl(upstreamBaseUrl, serverOptions);
  const upstreamUrl = `${upstreamBaseUrl}${upstreamPath}`;
  const controller = new AbortController();
  const abortUpstream = () => controller.abort();
  options.request?.once?.('close', abortUpstream);
  const response = await fetchImpl(upstreamUrl, {
    method: 'POST',
    headers: {
      ...authHeadersForKey(credential.rawKey, credential),
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
    signal: controller.signal,
    redirect: 'manual',
  });
  const contentType = response.headers?.get?.('content-type') || 'application/json; charset=utf-8';
  if (options.streamResponse && response.status >= 200 && response.status < 300 && response.body) {
    return {
      status: response.status,
      contentType,
      bodyText: '',
      bodyStream: response.body,
      abort: abortUpstream,
    };
  }

  const bodyText = await response.text();
  options.request?.off?.('close', abortUpstream);
  return {
    status: response.status,
    contentType,
    bodyText,
    latencyMs: Number(response.headers?.get?.('x-frist-upstream-latency-ms') || 0) || Number(credential.latencyMs || 0),
  };
}

function authHeadersForKey(rawKey, authConfig = {}) {
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

function sanitizeExtraHeaders(headers) {
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

function isQuotaExhaustedResponse(upstream) {
  if (upstream.status >= 200 && upstream.status < 300) {
    return false;
  }
  if (upstream.status === 402 || upstream.status === 429) {
    return true;
  }
  return /insufficient|quota|balance|余额|额度/i.test(upstream.bodyText || '');
}

function exhaustCredential(data, credential, reason) {
  credential.status = 'exhausted';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  recordChannelProbeEvent(data, credential, 'exhausted', reason, {});
  data.events.push({
    type: 'credential_exhausted',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

function failCredential(data, credential, reason) {
  credential.status = 'failed';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  recordChannelProbeEvent(data, credential, 'down', reason, {});
  data.events.push({
    type: 'credential_failed',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

async function maybeNotifyLowInventory(data, credential, serverOptions) {
  const threshold = Number(serverOptions.lowInventoryThresholdRatio || 0.05);
  if (!Number.isFinite(threshold) || threshold <= 0) {
    return;
  }

  const summary = buildInventorySummary(data).find(
    (item) => item.pool === credential.pool && item.providerGroup === effectiveCredentialGroup(credential),
  );
  if (!summary || summary.quotaTotal <= 0) {
    return;
  }

  const ratio = Number((summary.quotaRemaining / summary.quotaTotal).toFixed(4));
  const alertKey = `${summary.pool}:${summary.providerGroup}`;
  const previous = data.lowInventoryAlerts?.[alertKey]?.ratio ?? 1;
  if (ratio > threshold || ratio >= previous) {
    data.lowInventoryAlerts[alertKey] = {
      ratio,
      at: new Date().toISOString(),
    };
    return;
  }

  data.lowInventoryAlerts[alertKey] = {
    ratio,
    at: new Date().toISOString(),
  };

  const notifier = serverOptions.notifyLowInventory;
  if (typeof notifier === 'function') {
    await notifier({
      pool: summary.pool,
      providerGroup: summary.providerGroup,
      remainingRatio: ratio,
      quotaRemaining: summary.quotaRemaining,
      quotaTotal: summary.quotaTotal,
      nearestExpiresAt: summary.nearestExpiresAt,
      wasteText: summary.wasteText,
    });
  }
}

function credentialIssueTypeFromReason(reason = '') {
  const text = String(reason || '').toLowerCase();
  if (text.includes('quota') || text.includes('402') || text.includes('429')) {
    return 'quota';
  }
  if (text.includes('auth') || text.includes('401') || text.includes('403') || text.includes('forbidden')) {
    return 'auth';
  }
  return '';
}

function upstreamHostFromCredential(credential) {
  const target = credential?.routeBaseUrl || credential?.baseUrl || '';
  try {
    return new URL(normalizeBaseUrl(target)).host;
  } catch {
    return '';
  }
}

async function maybeNotifyCredentialIssue(data, credential, reason, serverOptions) {
  const issueType = credentialIssueTypeFromReason(reason);
  if (!credential || !issueType) {
    return;
  }
  if (!data.upstreamKeyAlerts || typeof data.upstreamKeyAlerts !== 'object') {
    data.upstreamKeyAlerts = {};
  }
  const alertKey = `${credential.id}:${issueType}`;
  if (data.upstreamKeyAlerts?.[alertKey]) {
    return;
  }
  const at = currentDate(serverOptions).toISOString();
  data.upstreamKeyAlerts[alertKey] = {
    at,
    issueType,
    reason: String(reason || '').slice(0, 120),
    status: String(credential.status || ''),
  };

  const notifier = serverOptions.notifyCredentialIssue;
  if (typeof notifier !== 'function') {
    return;
  }

  await notifier({
    type: 'upstream_key_issue',
    issueType,
    reason: String(reason || '').slice(0, 120),
    keyPreview: credential.keyPreview || maskKey(credential.rawKey),
    pool: credential.pool || 'default',
    providerGroup: effectiveCredentialGroup(credential),
    modelGroup: credential.modelGroup || 'All',
    status: credential.status || '',
    quotaRemaining: Number(credential.quotaRemaining || 0),
    quotaTotal: Number(credential.quotaTotal || credential.quotaRemaining || 0),
    sourceHost: upstreamHostFromCredential(credential),
    connectionPath: credential.connectionPath || 'direct',
    at,
  });
}

function monitorCandidateCredentials(data, serverOptions) {
  const batchSize = Math.max(1, Number(serverOptions.channelMonitorBatchSize || DEFAULT_CHANNEL_MONITOR_BATCH_SIZE));
  const cooldownMs = Math.max(0, Number(serverOptions.channelMonitorCooldownMs ?? DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS));
  const nowMs = currentDate(serverOptions).getTime();
  const candidates = data.credentials
    .filter((credential) => credential.enabled && credential.status === 'healthy')
    .filter(isCredentialRouteApproved)
    .filter((credential) => String(credential.rawKey || '').trim())
    .filter((credential) => String(credential.baseUrl || '').trim())
    .filter((credential) => {
      const lastProbeAt = Date.parse(credential.lastAutoProbeAt || '');
      if (!Number.isFinite(lastProbeAt)) return true;
      return nowMs - lastProbeAt >= cooldownMs;
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.lastAutoProbeAt || '') || 0;
      const rightTime = Date.parse(right.lastAutoProbeAt || '') || 0;
      return leftTime - rightTime;
    });
  return candidates.slice(0, batchSize);
}

export async function runChannelMonitorSweep(data, serverOptions) {
  const credentials = monitorCandidateCredentials(data, serverOptions);
  for (const credential of credentials) {
    const probe = await probeCredentialRoutes({
      baseUrl: credential.baseUrl,
      proxyBaseUrl: credential.proxyBaseUrl || '',
      rawKey: credential.rawKey,
      authConfig: {
        authHeaderName: credential.authHeaderName || 'authorization',
        authHeaderValuePrefix:
          credential.authHeaderValuePrefix === ''
            ? ''
            : credential.authHeaderValuePrefix ?? 'Bearer',
        extraHeaders: credential.extraHeaders || {},
      },
      models: normalizeOfficialModelList(
        Array.isArray(credential.models) && credential.models.length > 0
          ? credential.models
          : [DEFAULT_MODEL],
      ),
      serverOptions,
      collectAllModels: false,
      preferAnthropicMessages: effectiveCredentialGroup(credential) === 'Claude',
    });
    const now = currentDate(serverOptions).toISOString();
    credential.lastAutoProbeAt = now;
    credential.lastProbeStatus = probe.status || '';
    credential.lastProbeReason = probe.reason || '';
    if (probe.ok) {
      credential.status = 'healthy';
      credential.enabled = isCredentialRouteApproved(credential);
      credential.routeBaseUrl = probe.routeBaseUrl || credential.routeBaseUrl || credential.baseUrl;
      credential.connectionPath = probe.connectionPath || credential.connectionPath || 'direct';
      if (Array.isArray(probe.models) && probe.models.length > 0) {
        credential.models = normalizeOfficialModelList(probe.models);
      }
      const latencyMs = Math.max(0, Number(probe.latencyMs || credential.latencyMs || 0) || 0);
      credential.latencyMs = latencyMs;
      credential.updatedAt = now;
      recordChannelProbeEvent(
        data,
        credential,
        latencyMs > 1600 ? 'slow' : 'ok',
        probe.status || 'auto_probe_ok',
        serverOptions,
        { latencyMs },
      );
      continue;
    }

    if (probe.status === 'quota_failed') {
      exhaustCredential(data, credential, 'auto_probe_quota_failed');
      credential.lastProbeReason = probe.reason || '上游额度不足或限速';
      await maybeNotifyCredentialIssue(data, credential, 'auto_probe_quota_failed', serverOptions);
      continue;
    }

    if (probe.status === 'auth_failed') {
      failCredential(data, credential, 'auto_probe_auth_failed');
      credential.lastProbeReason = probe.reason || '认证失败或 Key 无效';
      await maybeNotifyCredentialIssue(data, credential, 'auto_probe_auth_failed', serverOptions);
      continue;
    }

    failCredential(data, credential, `auto_probe_${probe.status || 'failed'}`);
    credential.lastProbeReason = probe.reason || '通道探测失败';
  }
}

function startChannelMonitor({ store, serverOptions }) {
  const intervalMs = Math.max(100, Number(serverOptions.channelMonitorIntervalMs || DEFAULT_CHANNEL_MONITOR_INTERVAL_MS));
  let stopped = false;
  let running = false;
  const runOnce = async () => {
    if (stopped || running) {
      return;
    }
    running = true;
    try {
      await store.mutate(async (data) => {
        await runChannelMonitorSweep(data, serverOptions);
      });
    } catch {
      // 巡检失败不会阻断用户请求，下一轮继续执行。
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runOnce();
  }, intervalMs);
  if (typeof timer.unref === 'function') {
    timer.unref();
  }
  void runOnce();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

async function maybeNotifyCustomerLowBalance(data, user, serverOptions, context = {}) {
  const alert = normalizeBalanceAlertRecord(user.balanceAlert, user.email);
  user.balanceAlert = alert;
  if (!alert.enabled || alert.thresholdCents <= 0 || !alert.email) {
    return;
  }
  const balanceCents = Number(context.afterUserQuota ?? availableQuotaCents(user));
  if (balanceCents > alert.thresholdCents) {
    alert.lastTriggeredThresholdCents = 0;
    return;
  }

  const beforeBalanceCents = Number(context.beforeUserQuota ?? balanceCents);
  const crossedThreshold = beforeBalanceCents > alert.thresholdCents && balanceCents <= alert.thresholdCents;
  const thresholdChanged = Number(alert.lastTriggeredThresholdCents || 0) !== alert.thresholdCents;
  if (!crossedThreshold && !thresholdChanged) {
    return;
  }

  const sender = serverOptions.balanceAlertEmailSender;
  if (typeof sender !== 'function') {
    return;
  }

  const now = new Date().toISOString();
  const message = buildBalanceAlertEmail({
    user,
    to: alert.email,
    thresholdCents: alert.thresholdCents,
    balanceCents,
    previousBalanceCents: beforeBalanceCents,
    model: context.model,
    quotaCost: context.quotaCost,
    publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
    at: now,
  });

  try {
    await sender(message);
    alert.lastAlertAt = now;
    alert.lastAlertBalanceCents = balanceCents;
    alert.lastTriggeredThresholdCents = alert.thresholdCents;
    data.events.push({
      type: 'balance_alert_sent',
      userId: user.id,
      thresholdCents: alert.thresholdCents,
      balanceCents,
      alertEmail: maskEmail(alert.email),
      model: context.model || '',
      at: now,
    });
  } catch {
    data.events.push({
      type: 'balance_alert_failed',
      userId: user.id,
      thresholdCents: alert.thresholdCents,
      balanceCents,
      alertEmail: maskEmail(alert.email),
      at: now,
    });
  }
}

function buildBalanceAlertEmail({
  user,
  to,
  thresholdCents,
  balanceCents,
  previousBalanceCents,
  model,
  quotaCost,
  publicGatewayBaseUrl,
  at,
  isTest = false,
}) {
  const subject = isTest
    ? 'Frist-API 余额预警测试'
    : `Frist-API 余额预警：当前 ${formatUsdFromCnyCents(balanceCents)}`;
  const accountEmail = user.email || 'Frist-API 用户';
  const dashboardUrl = publicGatewayBaseUrl
    ? String(publicGatewayBaseUrl).replace(/\/v1\/?$/i, '').replace(/\/+$/, '')
    : '';
  const modelText = model ? String(model) : 'API 调用';
  const currentBalanceText = formatUsdFromCnyCents(balanceCents);
  const thresholdText = formatUsdFromCnyCents(thresholdCents);
  const previousBalanceText = formatUsdFromCnyCents(previousBalanceCents);
  const quotaCostText = formatUsdFromCnyCents(quotaCost);
  const alertTimeText = formatEmailTime(at);
  const preheader = `${accountEmail} 当前余额 ${currentBalanceText}，已低于 ${thresholdText} 安全线。`;
  const html = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light dark" />
    <meta name="supported-color-schemes" content="light dark" />
    <title>${escapeHtml(subject)}</title>
    <style>
      @media (prefers-color-scheme: dark) {
        .email-bg { background: #111827 !important; }
        .email-card { background: #172033 !important; border-color: #374151 !important; }
        .email-text { color: #f8fafc !important; }
        .email-muted { color: #cbd5e1 !important; }
        .email-panel { background: #111827 !important; border-color: #334155 !important; }
        .email-row { border-color: #334155 !important; }
        .email-soft { background: #1f2937 !important; color: #f8fafc !important; border-color: #475569 !important; }
      }
      @media screen and (max-width: 600px) {
        .email-shell { padding: 18px 10px !important; }
        .email-card { border-radius: 14px !important; }
        .email-pad { padding-left: 18px !important; padding-right: 18px !important; }
        .metric-cell { display: block !important; width: auto !important; }
        .metric-gap { display: block !important; width: auto !important; height: 10px !important; }
      }
    </style>
  </head>
  <body class="email-bg" style="margin:0;background:#eef2f5;color:#111827;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">${escapeHtml(preheader)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-bg email-shell" style="background:#eef2f5;padding:30px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-card" style="max-width:680px;background:#ffffff;border:1px solid #d7dee8;border-radius:18px;overflow:hidden;box-shadow:0 18px 45px rgba(15,23,42,.12);">
            <tr>
              <td style="padding:0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0f172a;">
                  <tr>
                    <td class="email-pad" style="padding:22px 28px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td valign="middle">
                            <div style="font-size:12px;line-height:1.2;letter-spacing:1.6px;text-transform:uppercase;color:#93c5fd;font-weight:800;">Frist-API Balance Guard</div>
                            <div style="margin-top:8px;color:#ffffff;font-size:25px;font-weight:800;line-height:1.22;">余额进入预警区间</div>
                          </td>
                          <td align="right" valign="middle">
                            <span style="display:inline-block;background:#fee2e2;color:#991b1b;border-radius:999px;padding:7px 11px;font-size:12px;font-weight:800;white-space:nowrap;">${isTest ? '测试预览' : '低余额预警'}</span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad email-text" style="padding:28px 28px 10px;color:#111827;">
                <div style="font-size:13px;color:#64748b;font-weight:700;">账户</div>
                <div class="email-text" style="margin-top:6px;font-size:18px;font-weight:800;color:#111827;line-height:1.35;">${escapeHtml(accountEmail)}</div>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:8px 28px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td class="metric-cell" width="50%" valign="top" style="width:50%;padding:18px;background:#ef4444;color:#ffffff;border:1px solid #dc2626;border-radius:16px;">
                      <div style="font-size:12px;line-height:1.2;opacity:.9;font-weight:800;">当前余额</div>
                      <div style="margin-top:10px;font-size:38px;font-weight:900;line-height:1;">${currentBalanceText}</div>
                      <div style="margin-top:10px;font-size:13px;line-height:1.45;color:#fee2e2;">低于安全线，需要关注</div>
                    </td>
                    <td class="metric-gap" width="12" style="width:12px;font-size:0;line-height:0;">&nbsp;</td>
                    <td class="metric-cell email-soft" width="50%" valign="top" style="width:50%;padding:18px;background:#f8fafc;color:#0f172a;border:1px solid #dbe3ed;border-radius:16px;">
                      <div style="font-size:12px;line-height:1.2;color:#64748b;font-weight:800;">预警阈值</div>
                      <div class="email-text" style="margin-top:10px;font-size:34px;font-weight:900;line-height:1;color:#0f172a;">${thresholdText}</div>
                      <div class="email-muted" style="margin-top:10px;font-size:13px;line-height:1.45;color:#64748b;">你设置的余额安全线</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:0 28px 22px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-panel" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;">
                  <tr>
                    <td colspan="2" class="email-row" style="padding:15px 16px;border-bottom:1px solid #e2e8f0;">
                      <div style="font-size:12px;line-height:1.2;color:#64748b;font-weight:800;">事件摘要</div>
                      <div class="email-text" style="margin-top:6px;font-size:16px;line-height:1.45;color:#111827;font-weight:800;">一次 API 消耗让余额跌破预警阈值</div>
                    </td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">触发模型</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${escapeHtml(modelText)}</td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">上次余额</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${previousBalanceText}</td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">本次扣费</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${quotaCostText}</td>
                  </tr>
                  <tr>
                    <td class="email-muted" style="padding:13px 16px;color:#64748b;">触发时间</td>
                    <td align="right" class="email-text" style="padding:13px 16px;color:#111827;font-weight:800;">${escapeHtml(alertTimeText)}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:0 28px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-soft" style="background:#f8fafc;border:1px solid #dbe3ed;border-radius:14px;">
                  <tr>
                    <td style="padding:16px 18px;">
                      <p class="email-text" style="margin:0;color:#1f2937;font-size:15px;line-height:1.7;">相当于油表已经进入红线区。为了避免 Codex、Claude Code 或 OpenCode 调用中断，建议尽快充值，或者把预警阈值调到更符合你使用节奏的位置。</p>
                    </td>
                  </tr>
                </table>
                ${
                  dashboardUrl
                    ? `<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:18px;">
                        <tr>
                          <td bgcolor="#111827" style="border-radius:999px;">
                            <a href="${escapeAttribute(dashboardUrl)}" style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;border-radius:999px;padding:13px 20px;font-size:14px;font-weight:900;">打开 Frist-API</a>
                          </td>
                          <td class="email-muted" style="padding-left:14px;color:#64748b;font-size:13px;line-height:1.45;">查看余额、充值或调整预警设置</td>
                        </tr>
                      </table>`
                    : ''
                }
              </td>
            </tr>
          </table>
          <div style="max-width:680px;margin-top:18px;color:#64748b;font-size:12px;line-height:1.65;text-align:left;">这是一封 Frist-API 余额预警通知。你可以在仪表盘关闭提醒、调整阈值或更换通知邮箱。</div>
        </td>
      </tr>
    </table>
  </body>
</html>`;
  const text = [
    subject,
    '',
    `账户: ${accountEmail}`,
    `当前余额: ${currentBalanceText}`,
    `预警阈值: ${thresholdText}`,
    `触发模型: ${modelText}`,
    `上次余额: ${previousBalanceText}`,
    `本次扣费: ${quotaCostText}`,
    `触发时间: ${alertTimeText}`,
    dashboardUrl ? `打开 Frist-API: ${dashboardUrl}` : '',
  ]
    .filter(Boolean)
    .join('\n');
  return { to, subject, html, text };
}

function defaultBalanceAlert(email = '') {
  const normalizedEmail = normalizeAlertEmail(email);
  return {
    enabled: true,
    thresholdCents: Math.round(5 * DISPLAY_USD_TO_CNY * 100),
    email: normalizedEmail,
    lastAlertAt: '',
    lastAlertBalanceCents: 0,
    lastTriggeredThresholdCents: 0,
    updatedAt: '',
  };
}

async function scheduleEmailDelivery({
  serverOptions,
  to,
  message,
  data,
  successType,
  failureType,
  eventBase = {},
}) {
  const sender = serverOptions.accountEmailSender || serverOptions.balanceAlertEmailSender;
  if (typeof sender !== 'function') {
    data.events.push({
      type: failureType,
      ...eventBase,
      reason: 'SMTP 邮件服务未配置',
      at: new Date().toISOString(),
    });
    return;
  }
  try {
    await sender({ ...message, to });
    data.events.push({ type: successType, ...eventBase, at: new Date().toISOString() });
  } catch (error) {
    data.events.push({
      type: failureType,
      ...eventBase,
      reason: String(error?.message || error).slice(0, 300),
      at: new Date().toISOString(),
    });
  }
}

function buildVerificationEmail({ user, code, publicGatewayBaseUrl, at }) {
  const dashboardUrl = publicGatewayBaseUrl
    ? String(publicGatewayBaseUrl).replace(/\/v1\/?$/i, '').replace(/\/+$/, '')
    : '';
  const subject = 'Frist-API 注册验证码';
  const timeText = formatEmailTime(at);
  const html = `<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;background:#f3f4f6;color:#111827;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:28px 12px;background:#f3f4f6;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
          <tr><td style="background:#111827;color:#ffffff;padding:22px 26px;">
            <div style="font-size:12px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;color:#fbbf24;">Frist-API</div>
            <div style="margin-top:8px;font-size:24px;font-weight:900;">完成邮箱验证</div>
          </td></tr>
          <tr><td style="padding:26px;color:#111827;">
            <p style="margin:0 0 14px;font-size:15px;line-height:1.7;">${escapeHtml(user.email)}，你的注册验证码是：</p>
            <div style="font-size:36px;letter-spacing:8px;font-weight:900;background:#fef3c7;border:1px solid #f59e0b;border-radius:12px;padding:16px;text-align:center;color:#111827;">${escapeHtml(code)}</div>
            <p style="margin:18px 0 0;color:#6b7280;font-size:13px;line-height:1.7;">验证码用于激活账户，请不要转发给别人。发送时间：${escapeHtml(timeText)}</p>
            ${dashboardUrl ? `<p style="margin:18px 0 0;"><a href="${escapeAttribute(dashboardUrl)}" style="color:#111827;font-weight:800;">打开 Frist-API</a></p>` : ''}
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>`;
  const text = [
    subject,
    '',
    `账户: ${user.email}`,
    `验证码: ${code}`,
    `发送时间: ${timeText}`,
    dashboardUrl ? `打开 Frist-API: ${dashboardUrl}` : '',
  ]
    .filter(Boolean)
    .join('\n');
  return { subject, html, text };
}

function buildPasswordResetEmail({ user, code, publicGatewayBaseUrl, expiresMinutes, at }) {
  const dashboardUrl = publicGatewayBaseUrl
    ? String(publicGatewayBaseUrl).replace(/\/v1\/?$/i, '').replace(/\/+$/, '')
    : '';
  const subject = 'Frist-API 密码重置验证码';
  const timeText = formatEmailTime(at);
  const html = `<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;background:#f3f4f6;color:#111827;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:28px 12px;background:#f3f4f6;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
          <tr><td style="background:#7f1d1d;color:#ffffff;padding:22px 26px;">
            <div style="font-size:12px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;color:#fecaca;">Frist-API Security</div>
            <div style="margin-top:8px;font-size:24px;font-weight:900;">重置登录密码</div>
          </td></tr>
          <tr><td style="padding:26px;color:#111827;">
            <p style="margin:0 0 14px;font-size:15px;line-height:1.7;">${escapeHtml(user.email)}，你的密码重置验证码是：</p>
            <div style="font-size:36px;letter-spacing:8px;font-weight:900;background:#fee2e2;border:1px solid #ef4444;border-radius:12px;padding:16px;text-align:center;color:#111827;">${escapeHtml(code)}</div>
            <p style="margin:18px 0 0;color:#6b7280;font-size:13px;line-height:1.7;">${Number(expiresMinutes)} 分钟内有效。如果不是你本人操作，可以忽略这封邮件。发送时间：${escapeHtml(timeText)}</p>
            ${dashboardUrl ? `<p style="margin:18px 0 0;"><a href="${escapeAttribute(dashboardUrl)}" style="color:#111827;font-weight:800;">打开 Frist-API</a></p>` : ''}
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>`;
  const text = [
    subject,
    '',
    `账户: ${user.email}`,
    `重置验证码: ${code}`,
    `有效期: ${Number(expiresMinutes)} 分钟`,
    `发送时间: ${timeText}`,
    dashboardUrl ? `打开 Frist-API: ${dashboardUrl}` : '',
  ]
    .filter(Boolean)
    .join('\n');
  return { subject, html, text };
}

function normalizeBalanceAlertRecord(record, fallbackEmail = '') {
  const current = record && typeof record === 'object' ? record : {};
  const fallback = defaultBalanceAlert(fallbackEmail);
  const thresholdCents = normalizeAlertThresholdCents(current, fallback.thresholdCents);
  return {
    enabled: Object.prototype.hasOwnProperty.call(current, 'enabled') ? Boolean(current.enabled) : fallback.enabled,
    thresholdCents:
      Number.isFinite(thresholdCents) && thresholdCents > 0 && thresholdCents <= 1_000_000_00
        ? thresholdCents
        : fallback.thresholdCents,
    email: normalizeAlertEmail(current.email) || fallback.email,
    lastAlertAt: String(current.lastAlertAt || ''),
    lastAlertBalanceCents: Math.max(0, normalizeMoneyCents(current.lastAlertBalanceCents || 0)),
    lastTriggeredThresholdCents: Math.max(0, normalizeMoneyCents(current.lastTriggeredThresholdCents || 0)),
    updatedAt: String(current.updatedAt || ''),
  };
}

function sanitizeBalanceAlert(record, fallbackEmail = '') {
  const alert = normalizeBalanceAlertRecord(record, fallbackEmail);
  return {
    enabled: alert.enabled,
    threshold: formatUsdFromCnyCents(alert.thresholdCents),
    thresholdCents: alert.thresholdCents,
    thresholdCny: Number((alert.thresholdCents / 100).toFixed(2)),
    thresholdUsd: Number((alert.thresholdCents / 100 / DISPLAY_USD_TO_CNY).toFixed(2)),
    email: alert.email,
    lastAlertAt: alert.lastAlertAt,
  };
}

function normalizeAlertThresholdCents(record = {}, fallbackCents = Number.NaN) {
  if (record.thresholdCents !== undefined) return normalizeMoneyCents(record.thresholdCents);
  if (record.thresholdUsd !== undefined) {
    return normalizeMoneyCents(Number(record.thresholdUsd || 0) * DISPLAY_USD_TO_CNY * 100);
  }
  if (record.thresholdCny !== undefined) return normalizeMoneyCents(Number(record.thresholdCny || 0) * 100);
  if (record.threshold !== undefined) {
    const text = String(record.threshold || '').trim();
    if (/^\$/.test(text)) return normalizeMoneyCents(Number(text.replace(/[^\d.-]/g, '')) * DISPLAY_USD_TO_CNY * 100);
    return normalizeMoneyCents(Number(text.replace(/[^\d.-]/g, '')) * DISPLAY_USD_TO_CNY * 100);
  }
  return normalizeMoneyCents(fallbackCents);
}

function normalizeMoneyCents(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return Number.NaN;
    const numeric = Number(trimmed.replace(/[^\d.-]/g, ''));
    return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
}

function normalizeAlertEmail(value) {
  const email = String(value || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return '';
  }
  return email.slice(0, 254);
}

function maskEmail(email) {
  const [name, domain] = String(email || '').split('@');
  if (!name || !domain) return '';
  const head = name.slice(0, Math.min(2, name.length));
  return `${head}${name.length > 2 ? '***' : '*'}@${domain}`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

function formatEmailTime(value) {
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

function createBalanceAlertEmailSender(options = {}) {
  const host = String(options.host ?? process.env.FRIST_API_SMTP_HOST ?? '').trim();
  const user = String(options.user ?? process.env.FRIST_API_SMTP_USER ?? '').trim();
  const password = String(options.password ?? process.env.FRIST_API_SMTP_PASSWORD ?? '');
  const from = String(options.from ?? process.env.FRIST_API_SMTP_FROM ?? user).trim();
  if (!host || !user || !password || !from) {
    return null;
  }

  const port = Number(options.port ?? process.env.FRIST_API_SMTP_PORT ?? 465);
  const secure =
    typeof options.secure === 'boolean'
      ? options.secure
      : String(process.env.FRIST_API_SMTP_SECURE ?? '1') !== '0';
  const fromName = String(
    options.fromName ?? process.env.FRIST_API_BALANCE_ALERT_FROM_NAME ?? 'Frist-API Billing',
  ).trim();
  const family = normalizeSmtpAddressFamily(options.family ?? process.env.FRIST_API_SMTP_FAMILY ?? 'auto');

  return async (message) =>
    sendSmtpMail({
      host,
      port,
      secure,
      family,
      user,
      password,
      from,
      fromName,
      to: message.to,
      subject: message.subject,
      text: message.text,
      html: message.html,
    });
}

async function sendSmtpMail(options) {
  const socket = await openSmtpSocket(options);
  const reader = createSmtpReader(socket);
  const writer = (line) => socket.write(`${line}\r\n`);
  try {
    await readSmtpReply(reader, [220]);
    writer(`EHLO ${smtpDomain(options.from)}`);
    await readSmtpReply(reader, [250]);
    writer('AUTH PLAIN ' + Buffer.from(`\u0000${options.user}\u0000${options.password}`).toString('base64'));
    await readSmtpReply(reader, [235]);
    writer(`MAIL FROM:<${options.from}>`);
    await readSmtpReply(reader, [250]);
    writer(`RCPT TO:<${options.to}>`);
    await readSmtpReply(reader, [250, 251]);
    writer('DATA');
    await readSmtpReply(reader, [354]);
    socket.write(`${buildMimeMessage(options)}\r\n.\r\n`);
    await readSmtpReply(reader, [250]);
    writer('QUIT');
    await readSmtpReply(reader, [221]);
  } finally {
    socket.end();
  }
}

async function openSmtpSocket(options) {
  const targets = await resolveSmtpSocketTargets(options);
  const errors = [];
  for (const target of targets) {
    try {
      return await connectSmtpSocketTarget(options, target);
    } catch (error) {
      errors.push(`${target.host}: ${error.message}`);
    }
  }
  throw new Error(`SMTP 连接失败: ${errors.join('; ')}`);
}

export async function resolveSmtpSocketTargets(options) {
  const family = normalizeSmtpAddressFamily(options.family ?? 'auto');
  const port = Number(options.port || 465);
  const ipFamily = isIP(options.host);
  if (ipFamily) {
    return [{ host: options.host, port, servername: options.host, family: ipFamily }];
  }

  const addresses = Array.isArray(options.addresses)
    ? options.addresses
    : await lookupDns(options.host, { all: true, verbatim: true });
  const normalized = addresses
    .map((address) => ({
      host: address.address,
      port,
      servername: options.host,
      family: Number(address.family),
    }))
    .filter((address) => address.host && (family === 'auto' || String(address.family) === family));
  if (!normalized.length) {
    return [{ host: options.host, port, servername: options.host, family: 0 }];
  }
  return normalized;
}

function connectSmtpSocketTarget(options, target) {
  const socketOptions = {
    host: target.host,
    port: target.port,
    family: target.family || undefined,
    servername: target.servername,
  };
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      callback(value);
    };
    const socket = options.secure
      ? connectTls(socketOptions, () => finish(resolve, socket))
      : connectNet(socketOptions, () => finish(resolve, socket));
    socket.setTimeout(Number(options.timeoutMs || 8_000));
    socket.once('error', (error) => finish(reject, error));
    socket.once('timeout', () => {
      socket.destroy();
      finish(reject, new Error('SMTP 连接超时'));
    });
  });
}

function normalizeSmtpAddressFamily(value) {
  const family = String(value || 'auto').trim().toLowerCase();
  if (family === '4' || family === 'ipv4') return '4';
  if (family === '6' || family === 'ipv6') return '6';
  return 'auto';
}

function createSmtpReader(socket) {
  const state = {
    buffer: '',
    waiters: [],
  };
  socket.setEncoding('utf8');
  socket.on('data', (chunk) => {
    state.buffer += chunk;
    flushSmtpWaiters(state);
  });
  socket.on('error', (error) => {
    const waiters = state.waiters.splice(0);
    for (const waiter of waiters) waiter.reject(error);
  });
  return state;
}

function flushSmtpWaiters(state) {
  while (state.waiters.length > 0) {
    const reply = takeCompleteSmtpReply(state);
    if (!reply) return;
    const waiter = state.waiters.shift();
    waiter.resolve(reply);
  }
}

function takeCompleteSmtpReply(state) {
  const lines = state.buffer.split(/\r?\n/);
  if (!state.buffer.match(/\r?\n$/)) {
    lines.pop();
  }
  let consumed = 0;
  for (const line of lines) {
    if (!line) {
      consumed += 1;
      continue;
    }
    consumed += 1;
    if (/^\d{3}\s/.test(line)) {
      const replyLines = lines.slice(0, consumed);
      state.buffer = lines.slice(consumed).join('\n');
      return replyLines.join('\n');
    }
  }
  return null;
}

function readSmtpReply(reader, expectedCodes) {
  return new Promise((resolve, reject) => {
    const complete = takeCompleteSmtpReply(reader);
    const handleReply = (reply) => {
      const code = Number(reply.slice(0, 3));
      if (!expectedCodes.includes(code)) {
        reject(new Error(`SMTP 返回异常: ${reply}`));
        return;
      }
      resolve(reply);
    };
    if (complete) {
      handleReply(complete);
      return;
    }
    reader.waiters.push({
      resolve: handleReply,
      reject,
    });
  });
}

function buildMimeMessage({ from, fromName, to, subject, text, html }) {
  const boundary = `frist-api-${randomBytes(12).toString('hex')}`;
  return [
    `From: ${encodeMimeHeader(fromName)} <${from}>`,
    `To: <${to}>`,
    `Subject: ${encodeMimeHeader(subject)}`,
    'MIME-Version: 1.0',
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${randomBytes(12).toString('hex')}@${smtpDomain(from)}>`,
    `Content-Type: multipart/alternative; boundary="${boundary}"`,
    '',
    `--${boundary}`,
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    wrapBase64(text || ''),
    `--${boundary}`,
    'Content-Type: text/html; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    wrapBase64(html || ''),
    `--${boundary}--`,
  ].join('\r\n');
}

function encodeMimeHeader(value) {
  const text = String(value || '');
  if (/^[\x20-\x7E]*$/.test(text)) {
    return text;
  }
  return `=?UTF-8?B?${Buffer.from(text, 'utf8').toString('base64')}?=`;
}

function wrapBase64(value) {
  return Buffer.from(String(value || ''), 'utf8')
    .toString('base64')
    .replace(/.{1,76}/g, '$&\r\n')
    .trim();
}

function smtpDomain(email) {
  return String(email || '').split('@')[1] || 'frist-api.local';
}

function buildGatewayAffinityKey(request, body, userKey, model) {
  const explicitSessionId = [
    headerValue(request, 'x-frist-session-id'),
    headerValue(request, 'x-conversation-id'),
    body?.metadata?.frist_session_id,
    body?.metadata?.conversation_id,
    body?.metadata?.session_id,
    body?.conversation_id,
    body?.session_id,
    body?.user,
  ]
    .map((value) => String(value || '').trim())
    .find(Boolean);
  const sessionId = explicitSessionId || 'default';
  return `${userKey.id}:${model}:${hashId(sessionId)}`;
}

function orderGatewayCandidates(data, candidates, sessionKey) {
  const affinity = data.routeAffinities?.[sessionKey];
  if (!affinity?.credentialId) {
    return candidates;
  }
  const stickyCredential = candidates.find((credential) => credential.id === affinity.credentialId);
  if (!stickyCredential) {
    delete data.routeAffinities[sessionKey];
    return candidates;
  }
  return [stickyCredential, ...candidates.filter((credential) => credential.id !== stickyCredential.id)];
}

function rememberRouteAffinity(data, sessionKey, affinity) {
  if (!sessionKey) return;
  data.routeAffinities[sessionKey] = affinity;
}

function clearRouteAffinity(data, sessionKey, credentialId) {
  const affinity = data.routeAffinities?.[sessionKey];
  if (affinity?.credentialId === credentialId) {
    delete data.routeAffinities[sessionKey];
  }
}

function createSecurityState() {
  return {
    captchas: new Map(),
    rateLimits: new Map(),
  };
}

function createCaptchaChallenge(securityState, serverOptions) {
  if (!serverOptions.requireCaptcha) {
    return {
      required: false,
      id: '',
      question: '',
    };
  }
  cleanupCaptchas(securityState);
  const challenge = buildRegistrationCaptcha();
  const id = createId('cap');
  securityState.captchas.set(id, {
    answer: challenge.answer,
    attemptsLeft: Number(serverOptions.captchaMaxAttempts || 3),
    expiresAt: Date.now() + Number(serverOptions.captchaTtlMs || 600_000),
  });
  return {
    required: true,
    id,
    question: challenge.question,
  };
}

function requireCaptchaIfEnabled(securityState, body, serverOptions) {
  if (!serverOptions.requireCaptcha) {
    return;
  }
  cleanupCaptchas(securityState);
  const id = String(body.captchaId || '').trim();
  const answer = String(body.captchaAnswer || '').trim();
  const challenge = securityState.captchas.get(id);
  if (!challenge || challenge.expiresAt < Date.now()) {
    throw publicError(400, '验证码已过期，请刷新后重试');
  }
  const normalizedAnswer = normalizeCaptchaAnswer(answer);
  const expected = normalizeCaptchaAnswer(challenge.answer);
  if (normalizedAnswer !== expected) {
    challenge.attemptsLeft = Math.max(0, Number(challenge.attemptsLeft || 1) - 1);
    if (challenge.attemptsLeft <= 0) {
      securityState.captchas.delete(id);
      throw publicError(400, '验证码不正确，请刷新后重试');
    }
    throw publicError(400, '验证码不正确');
  }
  securityState.captchas.delete(id);
}

function cleanupCaptchas(securityState) {
  const now = Date.now();
  for (const [id, challenge] of securityState.captchas) {
    if (challenge.expiresAt < now) {
      securityState.captchas.delete(id);
    }
  }
}

function buildRegistrationCaptcha() {
  const type = randomInt(4);
  if (type === 0) {
    const left = 18 + randomInt(73);
    const right = 11 + randomInt(58);
    const subtract = 3 + randomInt(17);
    return {
      question: `${left} + ${right} - ${subtract} = ?`,
      answer: String(left + right - subtract),
    };
  }
  if (type === 1) {
    const code = randomCaptchaCode(5);
    const firstIndex = randomInt(code.length);
    let secondIndex = randomInt(code.length);
    while (secondIndex === firstIndex) {
      secondIndex = randomInt(code.length);
    }
    const indexes = [firstIndex, secondIndex].sort((a, b) => a - b);
    return {
      question: `验证码 ${code}，输入第 ${indexes[0] + 1} 和第 ${indexes[1] + 1} 位字符`,
      answer: `${code[indexes[0]]}${code[indexes[1]]}`,
    };
  }
  if (type === 2) {
    const code = randomCaptchaCode(4);
    return {
      question: `把 ${code} 倒序输入`,
      answer: code.split('').reverse().join(''),
    };
  }
  const code = randomCaptchaCode(6);
  const digits = code.replace(/\D/g, '');
  if (digits.length >= 2) {
    return {
      question: `验证码 ${code}，只输入其中的数字`,
      answer: digits,
    };
  }
  return {
    question: `验证码 ${code}，输入最后 3 位`,
    answer: code.slice(-3),
  };
}

function normalizeCaptchaAnswer(value) {
  return String(value || '').trim().replace(/\s+/g, '').toUpperCase();
}

function randomCaptchaCode(length) {
  const alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let index = 0; index < length; index += 1) {
    code += alphabet[randomInt(alphabet.length)];
  }
  return code;
}

function randomInt(max) {
  return randomBytes(1)[0] % Math.max(1, Number(max) || 1);
}

function assertAuthRateLimit(securityState, request, serverOptions) {
  const max = Number(serverOptions.authRateLimitMax || 20);
  const windowMs = Number(serverOptions.authRateLimitWindowMs || 60_000);
  if (!Number.isFinite(max) || max <= 0 || !Number.isFinite(windowMs) || windowMs <= 0) {
    return;
  }
  const key = `auth:${clientIp(request)}`;
  const now = Date.now();
  const bucket = securityState.rateLimits.get(key) || { count: 0, resetAt: now + windowMs };
  if (bucket.resetAt <= now) {
    bucket.count = 0;
    bucket.resetAt = now + windowMs;
  }
  bucket.count += 1;
  securityState.rateLimits.set(key, bucket);
  if (bucket.count > max) {
    throw publicError(429, '请求过于频繁，请稍后再试');
  }
}

function clientIp(request) {
  const forwarded = headerValue(request, 'x-forwarded-for').split(',')[0]?.trim();
  return forwarded || request.socket?.remoteAddress || 'unknown';
}

function headerValue(request, name) {
  const value = request.headers[name.toLowerCase()];
  if (Array.isArray(value)) {
    return value[0] || '';
  }
  return value || '';
}

async function pipeReadableStreamToResponse(bodyStream, response, options = {}) {
  const abort = typeof options.abort === 'function' ? options.abort : null;
  let closed = false;
  response.once?.('close', () => {
    closed = true;
    abort?.();
  });
  if (typeof bodyStream.getReader === 'function') {
    const reader = bodyStream.getReader();
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        if (closed || response.destroyed) {
          await reader.cancel?.();
          break;
        }
        response.write(normalizeStreamChunk(chunk.value));
      }
    } finally {
      abort?.();
      reader.releaseLock?.();
      if (!response.destroyed) response.end();
    }
    return;
  }

  if (typeof bodyStream[Symbol.asyncIterator] === 'function') {
    try {
      for await (const chunk of bodyStream) {
        if (closed || response.destroyed) break;
        response.write(normalizeStreamChunk(chunk));
      }
    } finally {
      abort?.();
      if (!response.destroyed) response.end();
    }
    return;
  }

  abort?.();
  if (!response.destroyed) response.end();
}

function normalizeStreamChunk(chunk) {
  if (Buffer.isBuffer(chunk)) return chunk;
  if (chunk instanceof Uint8Array) return Buffer.from(chunk);
  return Buffer.from(String(chunk || ''), 'utf8');
}

async function writeFileAtomic(filePath, text) {
  await mkdir(dirname(filePath), { recursive: true });
  const tempPath = join(dirname(filePath), `.${basename(filePath)}.${process.pid}.${Date.now()}.${randomBytes(4).toString('hex')}.tmp`);
  const handle = await open(tempPath, 'w', 0o600);
  try {
    await handle.writeFile(text, 'utf8');
    await handle.sync();
  } catch (error) {
    await rm(tempPath, { force: true }).catch(() => {});
    throw error;
  } finally {
    await handle.close();
  }
  await rename(tempPath, filePath);
}

function createRuntimeStore(dataFile, encryptionKey = '') {
  let writeQueue = Promise.resolve();
  const encryption = createRuntimeEncryption(encryptionKey);

  async function load() {
    try {
      const raw = await readFile(dataFile, 'utf8');
      return normalizeRuntimeData(decryptRuntimeData(JSON.parse(raw), encryption));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
      return normalizeRuntimeData({});
    }
  }

  async function save(data) {
    await mkdir(dirname(dataFile), { recursive: true });
    const normalized = normalizeRuntimeData(data);
    await writeFileAtomic(dataFile, `${JSON.stringify(encryptRuntimeData(normalized, encryption), null, 2)}\n`);
  }

  async function mutate(mutator) {
    const run = writeQueue.then(async () => {
      const data = await load();
      const result = await mutator(data);
      try {
        await save(data);
      } catch (error) {
        process.emitWarning(`Frist-API runtime 写入失败: ${error.message}`, {
          code: 'FRIST_API_RUNTIME_WRITE_FAILED',
        });
        throw error;
      }
      return result;
    });
    writeQueue = run.catch(() => {});
    return run;
  }

  return { load, mutate };
}

function normalizeRuntimeData(data) {
  const pricing = normalizePricingConfig(data.pricing || {});
  return {
    users: Array.isArray(data.users) ? data.users.map(normalizeUserRecord) : [],
    sessions: data.sessions && typeof data.sessions === 'object' ? data.sessions : {},
    sessionCsrfTokens: data.sessionCsrfTokens && typeof data.sessionCsrfTokens === 'object' ? data.sessionCsrfTokens : {},
    adminSecondFactorSessions: data.adminSecondFactorSessions && typeof data.adminSecondFactorSessions === 'object' ? data.adminSecondFactorSessions : {},
    userKeys: Array.isArray(data.userKeys) ? data.userKeys : [],
    credentials: Array.isArray(data.credentials) ? data.credentials.map(normalizeCredentialRecord) : [],
    supplierProfiles: Array.isArray(data.supplierProfiles) ? data.supplierProfiles.map(normalizeSupplierProfileRecord) : [],
    priceDrafts: mergeModelPrices(Array.isArray(data.priceDrafts) ? data.priceDrafts : [], pricing.modelPrices),
    pricing,
    paymentOrders: Array.isArray(data.paymentOrders) ? data.paymentOrders : [],
    redemptions: Array.isArray(data.redemptions) ? data.redemptions : [],
    redemptionCards: Array.isArray(data.redemptionCards) ? data.redemptionCards.map(normalizeRedemptionCardRecord) : [],
    plusAccounts: Array.isArray(data.plusAccounts) ? data.plusAccounts.map(normalizePlusAccountRecord) : [],
    rtAccounts: Array.isArray(data.rtAccounts) ? data.rtAccounts.map(normalizeRtAccountRecord) : [],
    routeAffinities: data.routeAffinities && typeof data.routeAffinities === 'object' ? data.routeAffinities : {},
    lowInventoryAlerts: data.lowInventoryAlerts && typeof data.lowInventoryAlerts === 'object' ? data.lowInventoryAlerts : {},
    upstreamKeyAlerts: data.upstreamKeyAlerts && typeof data.upstreamKeyAlerts === 'object' ? data.upstreamKeyAlerts : {},
    backupStatus: normalizeBackupStatusRecord(data.backupStatus),
    channelProbeEvents: Array.isArray(data.channelProbeEvents) ? data.channelProbeEvents.map(normalizeChannelProbeEvent).filter(Boolean) : [],
    usedAdminClaimCodeHashes: Array.isArray(data.usedAdminClaimCodeHashes) ? data.usedAdminClaimCodeHashes : [],
    events: Array.isArray(data.events) ? data.events : [],
  };
}

function createRuntimeEncryption(secret) {
  const value = String(secret || '').trim();
  if (!value) {
    return null;
  }
  return createHash('sha256').update(value).digest();
}

function encryptRuntimeData(data, encryption) {
  if (!encryption) {
    return data;
  }
  const copy = structuredCloneJson(data);
  copy.__encryption = { version: 1, algorithm: 'aes-256-gcm', fields: ['userKeys.secret', 'credentials.rawKey', 'plusAccounts.secrets', 'rtAccounts.refreshToken'] };
  copy.userKeys = copy.userKeys.map((key) => ({
    ...key,
    secret: encryptSecretField(key.secret, encryption),
  }));
  copy.credentials = copy.credentials.map((credential) => ({
    ...credential,
    rawKey: encryptSecretField(credential.rawKey, encryption),
  }));
  copy.plusAccounts = copy.plusAccounts.map((account) => ({
    ...account,
    secrets: encryptSecretField(account.secrets, encryption),
  }));
  copy.rtAccounts = copy.rtAccounts.map((account) => ({
    ...account,
    refreshToken: encryptSecretField(account.refreshToken, encryption),
  }));
  return copy;
}

function decryptRuntimeData(data, encryption) {
  const copy = structuredCloneJson(data || {});
  if (!encryption) {
    return copy;
  }
  try {
    copy.userKeys = Array.isArray(copy.userKeys)
      ? copy.userKeys.map((key) => ({ ...key, secret: decryptSecretField(key.secret, encryption) }))
      : [];
    copy.credentials = Array.isArray(copy.credentials)
      ? copy.credentials.map((credential) => ({ ...credential, rawKey: decryptSecretField(credential.rawKey, encryption) }))
      : [];
    copy.plusAccounts = Array.isArray(copy.plusAccounts)
      ? copy.plusAccounts.map((account) => ({ ...account, secrets: decryptSecretField(account.secrets, encryption) }))
      : [];
    copy.rtAccounts = Array.isArray(copy.rtAccounts)
      ? copy.rtAccounts.map((account) => ({ ...account, refreshToken: decryptSecretField(account.refreshToken, encryption) }))
      : [];
    delete copy.__encryption;
    return copy;
  } catch (error) {
    throw normalizePublicError(error);
  }
}

function encryptSecretField(value, encryption) {
  const text = String(value || '');
  if (!text || text.startsWith('enc:v1:')) {
    return text;
  }
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', encryption, iv);
  const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
  return `enc:v1:${iv.toString('base64url')}:${cipher.getAuthTag().toString('base64url')}:${encrypted.toString('base64url')}`;
}

function decryptSecretField(value, encryption) {
  const text = String(value || '');
  if (!text.startsWith('enc:v1:')) {
    return text;
  }
  const [, version, ivText, authTagText, encryptedText] = text.split(':');
  if (version !== 'v1' || !ivText || !authTagText || !encryptedText) {
    throw publicError(500, '运行数据加密字段格式不正确');
  }
  try {
    const decipher = createDecipheriv('aes-256-gcm', encryption, Buffer.from(ivText, 'base64url'));
    decipher.setAuthTag(Buffer.from(authTagText, 'base64url'));
    return `${decipher.update(Buffer.from(encryptedText, 'base64url'), undefined, 'utf8')}${decipher.final('utf8')}`;
  } catch {
    throw publicError(500, '运行数据加密密钥不匹配');
  }
}

function structuredCloneJson(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

function normalizeUserRecord(user) {
  const email = normalizeAlertEmail(user?.email || '');
  return {
    ...user,
    passwordReset: normalizePasswordResetRecord(user?.passwordReset),
    balanceAlert: normalizeBalanceAlertRecord(user?.balanceAlert, email),
  };
}

function normalizePasswordResetRecord(record) {
  if (!record || typeof record !== 'object') {
    return null;
  }
  return {
    codeHash: String(record.codeHash || ''),
    expiresAt: String(record.expiresAt || ''),
    usedAt: String(record.usedAt || ''),
    requestedAt: String(record.requestedAt || ''),
  };
}

function normalizeCredentialRecord(credential) {
  const sourceType = normalizeSourceType(credential.sourceType || PRIMARY_SOURCE_TYPE);
  return {
    ...credential,
    models: normalizeOfficialModelList(credential.models || []),
    modelGroup: normalizeModelGroup(credential.modelGroup || inferProviderGroup((credential.models || []).join('\n'))),
    sourceType,
    riskStatus: normalizeRiskStatus(credential.riskStatus || 'approved'),
    backupRiskAccepted: Boolean(credential.backupRiskAccepted),
    riskNote: sanitizeRiskNote(credential.riskNote || ''),
  };
}

function normalizeSupplierProfileRecord(profile) {
  const sourceType = normalizeSourceType(profile.sourceType || PRIMARY_SOURCE_TYPE);
  return {
    ...profile,
    models: normalizeOfficialModelList(profile.models || []),
    modelGroup: normalizeModelGroup(profile.modelGroup || inferProviderGroup((profile.models || []).join('\n'))),
    sourceType,
    riskStatus: normalizeRiskStatus(profile.riskStatus || 'approved'),
    backupRiskAccepted: Boolean(profile.backupRiskAccepted),
    riskNote: sanitizeRiskNote(profile.riskNote || ''),
  };
}

function normalizeRedemptionCardRecord(card) {
  const plan = normalizeRechargePlan(card?.plan || 'balance');
  return {
    id: String(card?.id || createId('card')),
    batchId: String(card?.batchId || ''),
    code: String(card?.code || '').trim().toUpperCase(),
    label: String(card?.label || 'Frist-API 兑换码').trim(),
    plan,
    durationDays: Math.max(0, Number(card?.durationDays || (plan === 'month' ? 30 : plan === 'day' ? 1 : 0))),
    quotaUsd: Math.max(0, Number(card?.quotaUsd || 0)),
    priceCny: round2(Number(card?.priceCny || 0)),
    creditCents: Math.max(0, Number(card?.creditCents || 0)),
    status: ['unused', 'redeemed', 'disabled'].includes(String(card?.status || 'unused')) ? String(card.status) : 'unused',
    source: String(card?.source || 'xianyu'),
    note: String(card?.note || ''),
    createdAt: String(card?.createdAt || ''),
    updatedAt: String(card?.updatedAt || card?.createdAt || ''),
    redeemedAt: String(card?.redeemedAt || ''),
    redeemedBy: String(card?.redeemedBy || ''),
    redeemedEmail: String(card?.redeemedEmail || ''),
  };
}

function normalizePlusAccountRecord(account) {
  const openaiEmail = normalizeAlertEmail(account?.openaiEmail || '');
  const appleEmail = normalizeAlertEmail(account?.appleEmail || '');
  const status = normalizePlusAccountStatus(account?.status || '');
  const complianceStatus = normalizePlusAccountComplianceStatus(account?.complianceStatus || '');
  return {
    id: String(account?.id || createId('plus')),
    label: String(account?.label || openaiEmail || appleEmail || 'ChatGPT Plus 账号').trim().slice(0, 80),
    openaiEmail,
    appleEmail,
    region: normalizePlusAccountRegion(account?.region || 'Türkiye'),
    status,
    complianceStatus,
    billingMethod: String(account?.billingMethod || 'apple_iap').trim().slice(0, 60),
    appleBalanceTry: round2Finite(account?.appleBalanceTry),
    monthlyCostTry: round2Finite(account?.monthlyCostTry),
    plusRenewalAt: String(account?.plusRenewalAt || ''),
    lastCheckedAt: String(account?.lastCheckedAt || ''),
    deviceProfile: String(account?.deviceProfile || '').trim().slice(0, 120),
    browserProfile: String(account?.browserProfile || '').trim().slice(0, 120),
    riskNote: sanitizeRiskNote(account?.riskNote || ''),
    operatorNote: String(account?.operatorNote || '').trim().slice(0, 500),
    secrets: String(account?.secrets || '').trim().slice(0, 1000),
    routingEnabled: false,
    createdAt: String(account?.createdAt || ''),
    updatedAt: String(account?.updatedAt || ''),
  };
}

function normalizeRtAccountRecord(account) {
  const refreshToken = String(
    account?.refreshToken ?? account?.refresh_token ?? account?.rt ?? account?.token ?? '',
  ).trim().slice(0, 4000);
  const email = normalizeAlertEmail(account?.email || '');
  const platform = normalizeRtPlatform(account?.platform || account?.provider || '');
  const status = normalizeRtAccountStatus(account?.status || '');
  const accountId = String(account?.accountId ?? account?.account_id ?? '').trim().slice(0, 160);
  const fingerprint = String(account?.refreshTokenFingerprint || tokenFingerprint(refreshToken)).trim();
  return {
    id: String(account?.id || createId('rt')),
    label: String(account?.label || email || accountId || 'RT 账号').trim().slice(0, 80),
    platform,
    status,
    email,
    accountId,
    refreshToken,
    refreshTokenFingerprint: fingerprint,
    sourceLabel: String(account?.sourceLabel || '').trim().slice(0, 80),
    accountType: String(account?.accountType || '').trim().slice(0, 60),
    note: sanitizeRiskNote(account?.note || account?.riskNote || ''),
    lastRefreshAt: String(account?.lastRefreshAt || ''),
    expiresAt: String(account?.expiresAt || account?.expired || ''),
    importedAt: String(account?.importedAt || account?.createdAt || ''),
    createdAt: String(account?.createdAt || ''),
    updatedAt: String(account?.updatedAt || ''),
    routingEnabled: false,
  };
}

function normalizeBackupStatusRecord(record) {
  const current = record && typeof record === 'object' ? record : {};
  return {
    provider: String(current.provider || '').trim().slice(0, 80),
    target: String(current.target || '').trim().slice(0, 160),
    lastBackupAt: String(current.lastBackupAt || ''),
    lastRestoreTestAt: String(current.lastRestoreTestAt || ''),
    status: ['ok', 'warning', 'failed'].includes(String(current.status || '')) ? String(current.status) : 'warning',
    artifact: String(current.artifact || '').trim().slice(0, 180),
    sizeBytes: Math.max(0, Number(current.sizeBytes || 0) || 0),
    checksum: String(current.checksum || '').trim().slice(0, 128),
    message: String(current.message || '').trim().slice(0, 240),
    updatedAt: String(current.updatedAt || current.lastBackupAt || ''),
  };
}

function normalizeChannelProbeEvent(event) {
  if (!event || typeof event !== 'object') {
    return null;
  }
  const model = normalizeOfficialModelName(event.model);
  const status = normalizeSlaStatus(event.status);
  const at = String(event.at || '');
  if (!model || !status || !at) {
    return null;
  }
  return {
    id: String(event.id || createId('sla')),
    model,
    provider: event.provider || providerFromModel(model),
    credentialId: String(event.credentialId || ''),
    status,
    reason: String(event.reason || '').slice(0, 120),
    latencyMs: Math.max(0, Number(event.latencyMs || 0) || 0),
    pool: String(event.pool || ''),
    at,
  };
}

function normalizeSlaStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'ok' || status === 'healthy' || status === 'success') return 'ok';
  if (status === 'slow' || status === 'degraded') return 'slow';
  if (status === 'down' || status === 'failed' || status === 'exhausted') return 'down';
  return '';
}

function pricingPayload(data) {
  const pricing = normalizePricingConfig(data.pricing || {});
  return {
    rechargePlans: pricing.rechargePlans,
    modelPrices: pricing.modelPrices,
  };
}

function normalizePricingConfig(input = {}) {
  const rechargePlans = normalizeRechargePlans(input.rechargePlans);
  const modelPrices = normalizeModelPrices(input.modelPrices);
  return { rechargePlans, modelPrices };
}

function normalizeRechargePlans(plans) {
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

function normalizeModelPrices(prices) {
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
      displayPrice: String(normalizedPrice.displayPrice || '').trim(),
      status: String(price.status || normalizedPrice.status || 'confirmed'),
    });
  }
  return [...merged.values()];
}

function mergeModelPrices(existing, configured) {
  const merged = new Map();
  for (const price of normalizeModelPrices(configured)) {
    merged.set(price.model, price);
  }
  for (const price of Array.isArray(existing) ? existing : []) {
    const model = normalizeOfficialModelName(price.model);
    if (!model || merged.has(model)) continue;
    merged.set(model, {
      ...price,
      model,
    });
  }
  return [...merged.values()];
}

function normalizeServerOptions(options) {
  const root = dirname(fileURLToPath(import.meta.url));
  const exposeVerificationCode =
    typeof options.exposeVerificationCode === 'boolean'
      ? options.exposeVerificationCode
      : process.env.FRIST_API_EXPOSE_VERIFICATION_CODE === '1';
  const allowDemoRecharge =
    typeof options.allowDemoRecharge === 'boolean'
      ? options.allowDemoRecharge
      : process.env.FRIST_API_ALLOW_DEMO_RECHARGE === '1';
  const requireEmailVerification =
    typeof options.requireEmailVerification === 'boolean'
      ? options.requireEmailVerification
      : process.env.FRIST_API_REQUIRE_EMAIL_VERIFICATION === '1';
  const requireCaptcha =
    typeof options.requireCaptcha === 'boolean'
      ? options.requireCaptcha
      : process.env.FRIST_API_REQUIRE_CAPTCHA === '1';
  const normalized = {
    adminToken: options.adminToken || process.env.FRIST_API_ADMIN_TOKEN || 'frist-api-dev-admin-token',
    adminPageCode: options.adminPageCode || process.env.FRIST_API_ADMIN_PAGE_CODE || '',
    adminClaimCodeHashes: parseAdminClaimCodes(
      options.adminClaimCodes ?? process.env.FRIST_API_ADMIN_CLAIM_CODES ?? process.env.FRIST_API_ADMIN_CLAIM_CODE ?? '',
    ).map(hashAdminClaimCode),
    dataFile: options.dataFile || process.env.FRIST_API_DATA_FILE || join(root, '../data/runtime.json'),
    exposeVerificationCode,
    fetchImpl: options.fetchImpl,
    authRateLimitMax: Number(options.authRateLimitMax ?? process.env.FRIST_API_AUTH_RATE_LIMIT_MAX ?? 20),
    authRateLimitWindowMs: Number(
      options.authRateLimitWindowMs ?? process.env.FRIST_API_AUTH_RATE_LIMIT_WINDOW_MS ?? 60_000,
    ),
    captchaTtlMs: Number(options.captchaTtlMs ?? process.env.FRIST_API_CAPTCHA_TTL_MS ?? 600_000),
    captchaMaxAttempts: Number(options.captchaMaxAttempts ?? process.env.FRIST_API_CAPTCHA_MAX_ATTEMPTS ?? 3),
    passwordResetTtlMs: Number(options.passwordResetTtlMs ?? process.env.FRIST_API_PASSWORD_RESET_TTL_MS ?? 900_000),
    keepAliveTimeoutMs:
      options.keepAliveTimeoutMs === undefined && process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS === undefined
        ? Number.NaN
        : Number(options.keepAliveTimeoutMs ?? process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS),
    probeTimeoutMs: Number(options.probeTimeoutMs || process.env.FRIST_API_PROBE_TIMEOUT_MS || 8000),
    publicDir: options.publicDir ? resolve(options.publicDir) : resolve(root, '..'),
    publicGatewayBaseUrl: options.publicGatewayBaseUrl || process.env.FRIST_API_PUBLIC_GATEWAY_BASE_URL || '',
    canonicalHost: normalizeCanonicalHost(
      options.canonicalHost ?? process.env.FRIST_API_CANONICAL_HOST ?? DEFAULT_CANONICAL_HOST,
    ),
    redirectHosts: parseRedirectHosts(
      options.redirectHosts ?? process.env.FRIST_API_REDIRECT_HOSTS ?? DEFAULT_REDIRECT_HOSTS.join(','),
    ),
    dataEncryptionKey: options.dataEncryptionKey || process.env.FRIST_API_DATA_ENCRYPTION_KEY || '',
    quotaCost: Number(options.quotaCost || DEFAULT_QUOTA_COST),
    requireEmailVerification,
    requireCaptcha,
    sessionSecret: options.sessionSecret || process.env.FRIST_API_SESSION_SECRET || 'frist-api-dev-session-secret',
    passwordHashSecret:
      options.passwordHashSecret ||
      process.env.FRIST_API_PASSWORD_HASH_SECRET ||
      options.sessionSecret ||
      process.env.FRIST_API_SESSION_SECRET ||
      'frist-api-dev-session-secret',
    legacyPasswordHashSecrets: parseSecretList(
      options.legacyPasswordHashSecrets ?? process.env.FRIST_API_LEGACY_PASSWORD_HASH_SECRETS ?? '',
    ),
    allowDemoRecharge,
    newApiEnabled:
      typeof options.newApiEnabled === 'boolean'
        ? options.newApiEnabled
        : process.env.FRIST_API_NEWAPI_ENABLED === '1',
    newApiBaseUrl: options.newApiBaseUrl || process.env.FRIST_API_NEWAPI_BASE_URL || '',
    newApiAccessToken: options.newApiAccessToken || process.env.FRIST_API_NEWAPI_ACCESS_TOKEN || '',
    newApiUserId: options.newApiUserId || process.env.FRIST_API_NEWAPI_USER_ID || '',
    newApiDefaultGroup: options.newApiDefaultGroup || process.env.FRIST_API_NEWAPI_DEFAULT_GROUP || 'default',
    newApiDefaultTokenQuota: Number(
      options.newApiDefaultTokenQuota ?? process.env.FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA ?? 0,
    ),
    newApiGatewayBaseUrl:
      options.newApiGatewayBaseUrl || process.env.FRIST_API_NEWAPI_GATEWAY_BASE_URL || '',
    newApiGatewayEnabled:
      typeof options.newApiGatewayEnabled === 'boolean'
        ? options.newApiGatewayEnabled
        : process.env.FRIST_API_NEWAPI_GATEWAY_ENABLED === '1',
    requireNewApiDatabase:
      typeof options.requireNewApiDatabase === 'boolean'
        ? options.requireNewApiDatabase
        : process.env.FRIST_API_REQUIRE_NEWAPI_DATABASE === '1',
    enforceProductionReadiness:
      typeof options.enforceProductionReadiness === 'boolean'
        ? options.enforceProductionReadiness
        : process.env.FRIST_API_ENFORCE_PRODUCTION_READINESS === '1',
    requireAdmin2fa:
      typeof options.requireAdmin2fa === 'boolean'
        ? options.requireAdmin2fa
        : process.env.FRIST_API_REQUIRE_ADMIN_2FA === '1',
    adminTotpSecrets: normalizeTotpSecrets(options.adminTotpSecrets ?? process.env.FRIST_API_ADMIN_TOTP_SECRETS ?? process.env.FRIST_API_ADMIN_TOTP_SECRET ?? ''),
    admin2faSessionTtlMs: Number(options.admin2faSessionTtlMs ?? process.env.FRIST_API_ADMIN_2FA_SESSION_TTL_MS ?? 3_600_000),
    backupStatusMaxAgeHours: Number(options.backupStatusMaxAgeHours ?? process.env.FRIST_API_BACKUP_STATUS_MAX_AGE_HOURS ?? 26),
    slaRetentionDays: Number(options.slaRetentionDays ?? process.env.FRIST_API_SLA_RETENTION_DAYS ?? DEFAULT_SLA_RETENTION_DAYS),
    allowInsecurePublicHttp:
      typeof options.allowInsecurePublicHttp === 'boolean'
        ? options.allowInsecurePublicHttp
        : process.env.FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP === '1',
    requireCsrf:
      typeof options.requireCsrf === 'boolean'
        ? options.requireCsrf
        : process.env.FRIST_API_REQUIRE_CSRF === '1' || process.env.FRIST_API_PUBLIC_MODE === '1' || process.env.NODE_ENV === 'production',
    allowPrivateUpstreamUrls:
      typeof options.allowPrivateUpstreamUrls === 'boolean'
        ? options.allowPrivateUpstreamUrls
        : process.env.FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS === '1',
    resolveUpstreamAddresses: options.resolveUpstreamAddresses,
    publicMode:
      typeof options.publicMode === 'boolean'
        ? options.publicMode
        : process.env.FRIST_API_PUBLIC_MODE === '1' || process.env.NODE_ENV === 'production',
    nowFactory: typeof options.nowFactory === 'function' ? options.nowFactory : () => new Date(),
    lowInventoryThresholdRatio: Number(
      options.lowInventoryThresholdRatio ?? process.env.FRIST_API_LOW_INVENTORY_THRESHOLD_RATIO ?? 0.05,
    ),
    notifyLowInventory:
      typeof options.notifyLowInventory === 'function'
        ? options.notifyLowInventory
        : createLowInventoryWebhookNotifier(options.fetchImpl || globalThis.fetch),
    channelMonitorEnabled:
      typeof options.channelMonitorEnabled === 'boolean'
        ? options.channelMonitorEnabled
        : process.env.FRIST_API_CHANNEL_MONITOR_ENABLED === '1',
    channelMonitorIntervalMs: Number(
      options.channelMonitorIntervalMs ?? process.env.FRIST_API_CHANNEL_MONITOR_INTERVAL_MS ?? DEFAULT_CHANNEL_MONITOR_INTERVAL_MS,
    ),
    channelMonitorBatchSize: Number(
      options.channelMonitorBatchSize ?? process.env.FRIST_API_CHANNEL_MONITOR_BATCH_SIZE ?? DEFAULT_CHANNEL_MONITOR_BATCH_SIZE,
    ),
    channelMonitorCooldownMs: Number(
      options.channelMonitorCooldownMs ?? process.env.FRIST_API_CHANNEL_MONITOR_COOLDOWN_MS ?? DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS,
    ),
    notifyCredentialIssue:
      typeof options.notifyCredentialIssue === 'function'
        ? options.notifyCredentialIssue
        : createCredentialIssueNotifier(options.fetchImpl || globalThis.fetch),
    balanceAlertEmailSender:
      typeof options.balanceAlertEmailSender === 'function'
        ? options.balanceAlertEmailSender
        : createBalanceAlertEmailSender({
            host: options.smtpHost,
            port: options.smtpPort,
            secure: options.smtpSecure,
            user: options.smtpUser,
            password: options.smtpPassword,
            from: options.smtpFrom,
            fromName: options.balanceAlertFromName,
            family: options.smtpFamily,
          }),
  };
  normalized.passwordHashSecrets = [
    normalized.passwordHashSecret,
    normalized.sessionSecret,
    ...normalized.legacyPasswordHashSecrets,
  ].filter((secret, index, list) => secret && list.indexOf(secret) === index);
  normalized.accountEmailSender =
    typeof options.accountEmailSender === 'function' ? options.accountEmailSender : normalized.balanceAlertEmailSender;
  normalized.paymentConfig = paymentConfigFromOptions({
    ...options,
    publicGatewayBaseUrl: normalized.publicGatewayBaseUrl,
  });
  validatePublicModeOptions(normalized);
  return normalized;
}

function validatePublicModeOptions(serverOptions) {
  if (!serverOptions.publicMode) {
    return;
  }

  const problems = [];
  if (isUnsafeSecret(serverOptions.adminToken, 24)) {
    problems.push('管理员令牌必须替换成长随机值');
  }
  if (isUnsafeSecret(serverOptions.sessionSecret, 32)) {
    problems.push('会话密钥必须替换成长随机值');
  }
  if (serverOptions.exposeVerificationCode) {
    problems.push('公开模式禁止回显验证码');
  }
  if (serverOptions.allowDemoRecharge) {
    problems.push('公开模式禁止演示充值');
  }
  if (!serverOptions.dataEncryptionKey) {
    problems.push('运行数据加密密钥必须配置');
  }
  if (!serverOptions.adminPageCode) {
    problems.push('管理页隐藏入口码必须配置');
  }
  if (!serverOptions.requireCsrf) {
    problems.push('公开模式必须开启 CSRF 防护');
  }
  if (
    !isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) &&
    !(serverOptions.allowInsecurePublicHttp && isPublicHttpGateway(serverOptions.publicGatewayBaseUrl))
  ) {
    problems.push('公开网关地址必须是 HTTPS 域名，或显式允许临时公网 HTTP IP');
  }
  if (serverOptions.enforceProductionReadiness) {
    if (!isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl)) {
      problems.push('生产强制模式必须使用固定 HTTPS 品牌域名');
    }
    if (!serverOptions.canonicalHost || isTemporaryHost(serverOptions.canonicalHost)) {
      problems.push('生产强制模式必须配置固定品牌域名 FRIST_API_CANONICAL_HOST');
    }
    if (!serverOptions.newApiEnabled || !serverOptions.requireNewApiDatabase) {
      problems.push('生产强制模式必须启用 New-API 数据库替代 JSON runtime');
    }
    if (!serverOptions.requireAdmin2fa || serverOptions.adminTotpSecrets.length === 0) {
      problems.push('生产强制模式必须启用管理员 2FA');
    }
    const paymentStatus = buildPaymentClosureStatus(serverOptions);
    if (!paymentStatus.ready) {
      problems.push('生产强制模式必须接通至少一个真实支付商户回调');
    }
  }

  if (problems.length > 0) {
    throw new Error(`公开模式配置不安全: ${problems.join('；')}`);
  }
}

function createLowInventoryWebhookNotifier(fetchImpl) {
  const webhookUrl = process.env.FRIST_API_LOW_INVENTORY_WEBHOOK || '';
  if (!webhookUrl || typeof fetchImpl !== 'function') {
    return null;
  }

  return async (payload) => {
    try {
      await fetchImpl(webhookUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          source: 'Frist-API',
          type: 'low_inventory',
          ...payload,
        }),
      });
    } catch {
      // 低库存通知不能阻断用户请求，失败会留给下一轮健康检查处理。
    }
  };
}

function createCredentialIssueNotifier(fetchImpl) {
  if (typeof fetchImpl !== 'function') {
    return null;
  }
  const telegramToken = String(process.env.FRIST_API_TELEGRAM_BOT_TOKEN || '').trim();
  const telegramChatId = String(process.env.FRIST_API_TELEGRAM_CHAT_ID || '').trim();
  const webhookUrl = String(process.env.FRIST_API_KEY_ALERT_WEBHOOK || process.env.FRIST_API_LOW_INVENTORY_WEBHOOK || '').trim();
  if (!telegramToken && !webhookUrl) {
    return null;
  }

  return async (payload) => {
    const message = [
      `[Frist-API] ${payload.issueType === 'quota' ? 'Key 额度异常' : 'Key 认证异常'}`,
      `渠道: ${payload.pool || 'default'} / ${payload.providerGroup || 'Unknown'}`,
      `Key: ${payload.keyPreview || 'unknown'}`,
      `状态: ${payload.status || 'unknown'}`,
      `原因: ${payload.reason || 'unknown'}`,
      `剩余额度: ${Number(payload.quotaRemaining || 0)} / ${Number(payload.quotaTotal || 0)}`,
      `入口: ${payload.sourceHost || '-'}`,
      `时间: ${payload.at || ''}`,
      '动作: 请补号或轮换上游 Key',
    ].join('\n');
    try {
      if (telegramToken && telegramChatId) {
        await fetchImpl(`https://api.telegram.org/bot${telegramToken}/sendMessage`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            chat_id: telegramChatId,
            text: message,
            disable_web_page_preview: true,
          }),
        });
      }
      if (webhookUrl) {
        await fetchImpl(webhookUrl, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            source: 'Frist-API',
            type: 'upstream_key_issue',
            message,
            payload,
          }),
        });
      }
    } catch {
      // 告警失败不阻断主流程，等待下一次巡检或请求重试。
    }
  };
}

function normalizeCanonicalHost(value) {
  const host = String(value || '')
    .split(',')[0]
    .trim()
    .replace(/^https?:\/\//i, '')
    .replace(/\/.*$/, '')
    .toLowerCase();
  if (/^\[[^\]]+\]/.test(host)) {
    return host.replace(/:(80|443)$/, '');
  }
  return host.replace(/:\d+$/, '');
}

function parseRedirectHosts(value) {
  const items = Array.isArray(value) ? value : String(value || '').split(',');
  return new Set(items.map(normalizeCanonicalHost).filter(Boolean));
}

async function assertSafeUpstreamBaseUrl(value, serverOptions) {
  if (serverOptions.allowPrivateUpstreamUrls) {
    return;
  }
  const parsed = parseUpstreamUrl(value);
  if (isPrivateHostname(parsed.hostname) || isPrivateIpLiteral(parsed.hostname)) {
    throw publicError(400, '请求地址不能指向内网或本机地址');
  }
  const records = await resolveUpstreamAddresses(parsed.hostname, serverOptions);
  if (!records.length || records.some((record) => isPrivateIpLiteral(record.address))) {
    throw publicError(400, '请求地址不能解析到内网或本机地址');
  }
}

function parseUpstreamUrl(value) {
  let parsed;
  try {
    parsed = new URL(normalizeBaseUrl(value));
  } catch {
    throw publicError(400, '请求地址格式不正确');
  }
  if (!['https:', 'http:'].includes(parsed.protocol)) {
    throw publicError(400, '请求地址只支持 HTTP 或 HTTPS');
  }
  if (!parsed.hostname) {
    throw publicError(400, '请求地址缺少域名');
  }
  return parsed;
}

async function resolveUpstreamAddresses(hostname, serverOptions) {
  if (typeof serverOptions.resolveUpstreamAddresses === 'function') {
    return serverOptions.resolveUpstreamAddresses(hostname);
  }
  const literalFamily = isIP(hostname);
  if (literalFamily) {
    return [{ address: hostname, family: literalFamily }];
  }
  return lookupDns(hostname, { all: true, verbatim: true });
}

function isPrivateHostname(hostname) {
  const host = String(hostname || '').toLowerCase();
  return host === 'localhost' || host.endsWith('.localhost');
}

function isPrivateIpLiteral(value) {
  const ip = String(value || '').replace(/^\[|\]$/g, '').toLowerCase();
  if (!isIP(ip)) return false;
  if (ip === '::1' || ip === '0:0:0:0:0:0:0:1') return true;
  if (/^(fc|fd|fe80):/i.test(ip)) return true;
  if (ip.startsWith('::ffff:')) {
    return isPrivateIpLiteral(ip.slice('::ffff:'.length));
  }
  const parts = ip.split('.').map((item) => Number(item));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  const [first, second] = parts;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

function redirectToCanonicalHost({ request, response, url, serverOptions }) {
  if (!serverOptions.canonicalHost || !serverOptions.redirectHosts?.size) {
    return false;
  }
  const requestHost = normalizeCanonicalHost(request.headers['x-forwarded-host'] || request.headers.host || '');
  if (!requestHost || !serverOptions.redirectHosts.has(requestHost)) {
    return false;
  }
  url.host = serverOptions.canonicalHost;
  response.writeHead(301, {
    location: url.toString(),
    'cache-control': 'no-store',
  });
  response.end();
  return true;
}

function isUnsafeSecret(value, minLength) {
  const secret = String(value || '');
  if (secret.length < minLength) {
    return true;
  }
  return /frist-api-dev|replace|change-before|default|example|password/i.test(secret);
}

function isPublicHttpsGateway(value) {
  const gateway = String(value || '').trim();
  if (!/^https:\/\//i.test(gateway)) {
    return false;
  }
  return !/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|example\.(com|org|net))/i.test(gateway);
}

function isPublicHttpGateway(value) {
  const gateway = String(value || '').trim();
  if (!/^http:\/\//i.test(gateway)) {
    return false;
  }
  return !/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|example\.(com|org|net))/i.test(gateway);
}

function isTemporaryHost(value) {
  const host = normalizeCanonicalHost(value);
  return !host || /\.nip\.io$/i.test(host) || /\.sslip\.io$/i.test(host) || /^\d{1,3}(\.\d{1,3}){3}$/.test(host);
}

function requireSession(data, request) {
  const session = findSession(data, request);
  if (!session.user) {
    throw publicError(401, '请先登录');
  }
  return session;
}

function findSession(data, request) {
  const token = parseCookies(request.headers.cookie || '')[SESSION_COOKIE];
  const userId = token ? data.sessions[token] : '';
  const user = data.users.find((item) => item.id === userId);
  return { token, user };
}

function requireCsrfIfEnabled(data, request, serverOptions, options = {}) {
  if (!serverOptions.requireCsrf || request.method === 'GET' || request.method === 'HEAD' || request.method === 'OPTIONS') {
    return;
  }
  if (options.allowAdminToken && request.headers['x-admin-token']) {
    return;
  }
  const { token, user } = findSession(data, request);
  if (!user || !token) {
    throw publicError(401, '请先登录');
  }
  const expected = String(data.sessionCsrfTokens?.[token] || parseCookies(request.headers.cookie || '')[CSRF_COOKIE] || '');
  const actual = String(request.headers['x-csrf-token'] || '').trim();
  if (!expected || !actual || !safeEqual(expected, actual)) {
    throw publicError(403, '页面安全校验失败，请刷新后重试');
  }
}

function requireUserKey(data, request) {
  const authorization = request.headers.authorization || '';
  const xApiKey = request.headers['x-api-key'] || request.headers['anthropic-auth-token'] || '';
  const secret = authorization.match(/^Bearer\s+(.+)$/i)?.[1] || String(xApiKey || '').trim();
  const key = data.userKeys.find((item) => safeEqual(item.secret, secret));
  if (!key || !key.enabled) {
    throw publicError(401, 'API Key 不可用');
  }
  return key;
}

function requireAdmin(data, request, serverOptions, options = {}) {
  const token = request.headers['x-admin-token'];
  if (token && token === serverOptions.adminToken) {
    requireAdminSecondFactorIfEnabled(data, request, serverOptions, options);
    return;
  }
  const { user } = findSession(data, request);
  if (user?.isAdmin) {
    requireAdminSecondFactorIfEnabled(data, request, serverOptions, options);
    return;
  }
  throw publicError(401, '管理员身份无效');
}

function requireAdminSecondFactorIfEnabled(data, request, serverOptions, options = {}) {
  if (!serverOptions.requireAdmin2fa || options.allowPendingSecondFactor) {
    return;
  }
  pruneAdminSecondFactorSessions(data, serverOptions);
  const token = parseCookies(request.headers.cookie || '')[ADMIN_2FA_COOKIE] || headerValue(request, 'x-admin-2fa-session');
  const session = token ? data.adminSecondFactorSessions?.[token] : null;
  const expiresAt = Date.parse(session?.expiresAt || '');
  if (!session || !Number.isFinite(expiresAt) || expiresAt <= currentDate(serverOptions).getTime()) {
    throw publicError(401, '需要管理员 2FA 验证');
  }
}

function pruneAdminSecondFactorSessions(data, serverOptions) {
  const now = currentDate(serverOptions).getTime();
  data.adminSecondFactorSessions = Object.fromEntries(
    Object.entries(data.adminSecondFactorSessions || {}).filter(([, session]) => {
      const expiresAt = Date.parse(session?.expiresAt || '');
      return Number.isFinite(expiresAt) && expiresAt > now;
    }),
  );
}

function normalizeReplenishmentKeys(keys) {
  if (typeof keys === 'string') {
    return keys
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((value) => ({
        value,
        quotaRemaining: 1000,
        quotaTotal: 1000,
        latencyMs: 0,
        latencyProvided: false,
        authHeaderName: 'authorization',
        authHeaderValuePrefix: 'Bearer',
        extraHeaders: {},
        modelGroup: 'All',
        cardType: '',
        expiresAt: '',
      }));
  }
  if (!Array.isArray(keys)) {
    throw publicError(400, 'Key 列表不能为空');
  }
  return keys
    .map((item) => (typeof item === 'string' ? { value: item } : item))
    .map((item) => ({
      value: String(item.value || item.key || item.apiKey || item.api_key || item.token || '').trim(),
      quotaRemaining: Number(item.quotaRemaining ?? 1000),
      quotaTotal: Number(item.quotaTotal ?? item.quotaRemaining ?? 1000),
      latencyMs: Number(item.latencyMs ?? 0),
      latencyProvided: item.latencyMs !== undefined,
      authHeaderName: String(item.authHeaderName || 'authorization').trim().toLowerCase(),
      authHeaderValuePrefix:
        item.authHeaderValuePrefix === ''
          ? ''
          : String(item.authHeaderValuePrefix || 'Bearer').trim(),
      extraHeaders: sanitizeExtraHeaders(item.extraHeaders),
      modelGroup: item.modelGroup ? normalizeModelGroup(item.modelGroup) : '',
      cardType: normalizePool(item.cardType || ''),
      expiresAt: String(item.expiresAt || ''),
    }))
    .filter((item) => item.value);
}

function resolveProbeLatencyMs(key, probe = {}) {
  if (key.latencyProvided && Number.isFinite(key.latencyMs) && key.latencyMs > 0) {
    return key.latencyMs;
  }
  const latency = Number(probe.latencyMs || 0);
  return Number.isFinite(latency) && latency > 0 ? latency : 0;
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

function sanitizeRiskNote(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500);
}

function normalizePlusAccountStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (PLUS_ACCOUNT_STATUSES.has(status)) return status;
  return 'warming';
}

function normalizePlusAccountComplianceStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (PLUS_ACCOUNT_COMPLIANCE_STATUSES.has(status)) return status;
  return 'needs_review';
}

function normalizePlusAccountRegion(value) {
  const text = String(value || '').trim();
  if (text.toLowerCase() === 'turkey' || text.toLowerCase() === 'turkiye' || text === '土耳其') {
    return 'Türkiye';
  }
  if (PLUS_ACCOUNT_REGIONS.has(text)) return text;
  return 'Other';
}

function normalizeRtAccountStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (RT_ACCOUNT_STATUSES.has(status)) return status;
  return 'ready_for_refresh';
}

function normalizeRtPlatform(value) {
  const platform = String(value || '').trim().toLowerCase();
  if (platform === 'chatgpt') return 'openai';
  if (RT_ACCOUNT_PLATFORMS.has(platform)) return platform;
  return 'codex';
}

function isSourceRouteApproved({ sourceType, riskStatus, backupRiskAccepted }) {
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

function isCredentialRouteApproved(credential) {
  return isSourceRouteApproved({
    sourceType: credential.sourceType || PRIMARY_SOURCE_TYPE,
    riskStatus: credential.riskStatus || 'approved',
    backupRiskAccepted: credential.backupRiskAccepted,
  });
}

function normalizeModels(models, options = {}) {
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

function upsertSupplierProfile(data, profile) {
  let source = data.supplierProfiles.find((item) => item.id === profile.id);
  if (!source) {
    source = {
      id: profile.id,
      baseUrl: profile.baseUrl,
      proxyBaseUrl: profile.proxyBaseUrl || '',
      routeBaseUrl: profile.routeBaseUrl || profile.baseUrl,
      pool: profile.pool,
      modelGroup: profile.modelGroup || 'All',
      cardType: profile.cardType || profile.pool,
      expiresAt: profile.expiresAt || '',
      sourceType: profile.sourceType || PRIMARY_SOURCE_TYPE,
      riskStatus: profile.riskStatus || 'approved',
      backupRiskAccepted: Boolean(profile.backupRiskAccepted),
      riskNote: sanitizeRiskNote(profile.riskNote || ''),
      models: profile.models,
      connectionPath: profile.connectionPath || 'direct',
      createdAt: profile.updatedAt,
      updatedAt: profile.updatedAt,
    };
    data.supplierProfiles.push(source);
    return source;
  }
  source.pool = profile.pool;
  source.modelGroup = profile.modelGroup || source.modelGroup || 'All';
  source.cardType = profile.cardType || source.cardType || profile.pool;
  source.expiresAt = profile.expiresAt || source.expiresAt || '';
  source.sourceType = profile.sourceType || source.sourceType || PRIMARY_SOURCE_TYPE;
  source.riskStatus = profile.riskStatus || source.riskStatus || 'approved';
  source.backupRiskAccepted = Boolean(profile.backupRiskAccepted);
  source.riskNote = sanitizeRiskNote(profile.riskNote || source.riskNote || '');
  source.proxyBaseUrl = profile.proxyBaseUrl || '';
  source.routeBaseUrl = profile.routeBaseUrl || profile.baseUrl;
  source.models = profile.models;
  source.connectionPath = profile.connectionPath || source.connectionPath || 'direct';
  source.updatedAt = profile.updatedAt;
  return source;
}

function upsertCredential(data, nextCredential) {
  let credential = data.credentials.find(
    (item) =>
      item.sourceId === nextCredential.sourceId &&
      normalizeModelGroup(item.modelGroup) === normalizeModelGroup(nextCredential.modelGroup) &&
      item.rawKey === nextCredential.rawKey,
  );
  if (!credential) {
    credential = {
      id: createId('cred'),
      createdAt: nextCredential.createdAt,
    };
    data.credentials.push(credential);
  }

  Object.assign(credential, {
    ...nextCredential,
    id: credential.id,
    createdAt: credential.createdAt || nextCredential.createdAt,
  });
  return credential;
}

async function serveStaticFile({ request, response, url, publicDir, serverOptions, store }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    writeJson(response, 405, { error: '请求方法不支持' });
    return;
  }

  const pathname = decodeURIComponent(url.pathname);
  const adminGateHeaders = await validateAdminPageGate({ request, url, pathname, serverOptions, store });
  if (adminGateHeaders === false) {
    writeJson(response, 404, { error: '文件不存在' });
    return;
  }
  const candidate = pathname === '/' ? '/index.html' : pathname;
  const safeCandidate = normalize(candidate).replace(/^[/\\]+/, '').replace(/^(\.\.(\/|\\|$))+/, '');
  const filePath = resolve(publicDir, safeCandidate);
  if (relative(publicDir, filePath).startsWith('..')) {
    writeJson(response, 403, { error: '路径不可访问' });
    return;
  }

  let finalPath = filePath;
  try {
    const info = await stat(finalPath);
    if (info.isDirectory()) {
      finalPath = join(finalPath, 'index.html');
    }
    const content = await readFile(finalPath);
    response.writeHead(200, {
      'content-type': CONTENT_TYPES.get(extname(finalPath)) || 'application/octet-stream',
      'cache-control': 'no-store',
      ...(adminGateHeaders || {}),
    });
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    response.end(content);
  } catch (error) {
    if (error.code === 'ENOENT') {
      writeJson(response, 404, { error: '文件不存在' });
      return;
    }
    throw error;
  }
}

async function validateAdminPageGate({ request, url, pathname, serverOptions, store }) {
  if (pathname !== '/admin.html' || !serverOptions.adminPageCode) {
    return {};
  }
  const cookies = parseCookies(request.headers.cookie || '');
  const code = url.searchParams.get('code') || '';
  if (cookies.frist_admin_gate === hashId(serverOptions.adminPageCode)) {
    return {};
  }
  if (code !== serverOptions.adminPageCode) {
    if (store) {
      const data = await store.load();
      const { user } = findSession(data, request);
      if (user?.isAdmin) {
        return {};
      }
    }
    return false;
  }
  return adminGateCookie(serverOptions);
}

function adminGateCookie(serverOptions) {
  if (!serverOptions.adminPageCode) {
    return {};
  }
  return {
    'set-cookie': [
      `frist_admin_gate=${hashId(serverOptions.adminPageCode)}`,
      'Path=/',
      'HttpOnly',
      'SameSite=Lax',
      serverOptions.publicMode && isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) ? 'Secure' : '',
    ].filter(Boolean).join('; '),
  };
}

function sessionCookies(sessionToken, csrfToken, request, serverOptions) {
  return [
    sessionCookie(sessionToken, request, serverOptions),
    csrfCookie(csrfToken, request, serverOptions),
  ];
}

function adminSecondFactorCookie(sessionToken, request, serverOptions) {
  if (!sessionToken) {
    return '';
  }
  return [
    `${ADMIN_2FA_COOKIE}=${sessionToken}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function sessionCookie(sessionToken, request, serverOptions) {
  return [
    `${SESSION_COOKIE}=${sessionToken}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function csrfCookie(csrfToken, request, serverOptions) {
  return [
    `${CSRF_COOKIE}=${csrfToken}`,
    'Path=/',
    'SameSite=Lax',
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function shouldUseSecureCookie(request, serverOptions) {
  const forwardedProto = String(request.headers['x-forwarded-proto'] || '').split(',')[0].trim().toLowerCase();
  return forwardedProto === 'https' || isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl);
}

async function readJsonBody(request) {
  const bodyText = await readRequestText(request);
  if (!bodyText) {
    return {};
  }
  try {
    return JSON.parse(bodyText);
  } catch {
    throw publicError(400, 'JSON 格式不正确');
  }
}

async function readRequestText(request) {
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
    return '';
  }
  return Buffer.concat(chunks).toString('utf8');
}

function writeJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-csrf-token, x-frist-session-id, x-conversation-id',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

function writeNoContent(response) {
  response.writeHead(204, {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-csrf-token, x-frist-session-id, x-conversation-id',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  });
  response.end();
}

function publicError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.expose = true;
  return error;
}

function normalizePublicError(error) {
  if (error?.expose) {
    return error;
  }
  return publicError(500, String(error?.message || '服务暂时不可用'));
}

function requestOrigin(request) {
  const protocol = request.headers['x-forwarded-proto'] || 'http';
  const host = request.headers['x-forwarded-host'] || request.headers.host || '127.0.0.1';
  return `${protocol}://${host}`;
}

function parseCookies(header) {
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

function poolForUser(user) {
  if (String(user.plan || '').includes('日卡')) return 'day';
  if (String(user.plan || '').includes('月卡')) return 'month';
  return 'default';
}

function allowedPoolsForUser(user) {
  const pool = poolForUser(user);
  if (pool === 'day') return ['hour', 'day', 'unlimited', 'default'];
  if (pool === 'month') return ['hour', 'day', 'month', 'unlimited', 'default'];
  return ['unlimited', 'default'];
}

function normalizePool(value) {
  const pool = String(value || '').trim().toLowerCase();
  if (['hour', 'day', 'month', 'unlimited', 'default'].includes(pool)) return pool;
  if (/小时|hour/.test(pool)) return 'hour';
  if (/日|天|day/.test(pool)) return 'day';
  if (/月|month/.test(pool)) return 'month';
  if (/不限|永久|unlimited/.test(pool)) return 'unlimited';
  return '';
}

function compareGatewayCredentials(left, right) {
  const poolDelta = poolPriority(left.pool) - poolPriority(right.pool);
  if (poolDelta !== 0) return poolDelta;
  const expiryDelta = expiryMs(left.expiresAt) - expiryMs(right.expiresAt);
  if (expiryDelta !== 0) return expiryDelta;
  return Number(left.latencyMs || 999999) - Number(right.latencyMs || 999999);
}

function credentialMatchesModelGroup(credential, model, keyGroup) {
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

function expiryMs(value) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.MAX_SAFE_INTEGER;
}

function accountFromUser(data, user) {
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

function sumUserGatewayCost(data, userId, periodPrefix = '') {
  return data.events
    .filter((item) => item.type === 'gateway_routed' && item.userId === userId)
    .filter((item) => !periodPrefix || String(item.at || '').startsWith(periodPrefix))
    .reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
}

function availableQuotaCents(user) {
  reconcileUserBalance(user);
  return Number(user.packageQuotaCents || 0) + Number(user.boosterQuotaCents || 0);
}

function deductUserQuota(user, quotaCost) {
  let remaining = Number(quotaCost || 0);
  const packageDeduction = Math.min(Number(user.packageQuotaCents || 0), remaining);
  user.packageQuotaCents = Math.max(0, Number(user.packageQuotaCents || 0) - packageDeduction);
  remaining -= packageDeduction;
  if (remaining > 0) {
    user.boosterQuotaCents = Math.max(0, Number(user.boosterQuotaCents || 0) - remaining);
  }
  reconcileUserBalance(user);
}

function resolveQuotaCostCents(data, model, body, upstream, serverOptions) {
  const usage = parseUpstreamUsage(upstream.bodyText);
  const price = findModelPrice(data, model);
  if (price && usage.totalTokens > 0) {
    return priceUsageCents(price, usage.promptTokens, usage.completionTokens);
  }
  return estimateQuotaCostCents(data, model, body, serverOptions);
}

function estimateQuotaCostCents(data, model, body, serverOptions) {
  const price = findModelPrice(data, model);
  if (!price) {
    return Number(serverOptions.quotaCost || DEFAULT_QUOTA_COST);
  }

  const promptTokens = estimatePromptTokens(body.messages ?? body.input ?? body.prompt);
  const completionTokens = Number(body.max_tokens || body.max_completion_tokens || body.max_output_tokens || 256);
  return Math.max(Number(serverOptions.quotaCost || DEFAULT_QUOTA_COST), priceUsageCents(price, promptTokens, completionTokens));
}

function buildGatewayModels(data, request) {
  const userKey = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === userKey.userId);
  if (!user) {
    throw publicError(401, '用户不存在');
  }
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
  )
    .filter((model) => modelMatchesGroup(model, userKey.modelGroup || 'All'));
  const sortedModels = sortModelsByStrength(models);

  return {
    object: 'list',
    data: sortedModels.map((model) => ({
      id: model,
      object: 'model',
      owned_by: 'frist-api',
    })),
  };
}

function availableModelsForCustomer(data, user, key, requestedModel = '') {
  return customerImportModelSelection(data, user, key, requestedModel).availableModels;
}

function customerImportModelSelection(data, user, key, requestedModel = '') {
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
  const liveSet = new Set(normalizeClientAvailableModels(liveModels, { modelGroup: key.modelGroup }));
  const safeRequested = requested && liveSet.has(requested) ? requested : '';
  const primaryModels = normalizeClientAvailableModels(uniqueStrings([...liveSet, safeRequested]), {
    model: safeRequested,
    modelGroup: key.modelGroup,
  });

  if (primaryModels.length) {
    return {
      availableModels: primaryModels,
      defaultModel: safeRequested || strongestModel(primaryModels),
    };
  }

  const catalogModels = buildModelCatalog(data)
    .filter((item) => item.available !== false)
    .map((item) => item.model)
    .filter((model) => modelMatchesGroup(model, key.modelGroup || 'All'));
  const fallbackModels = normalizeClientAvailableModels(catalogModels.length ? catalogModels : [DEFAULT_PUBLIC_MODEL], {
    modelGroup: key.modelGroup,
  });
  return {
    availableModels: fallbackModels,
    defaultModel: strongestModel(fallbackModels),
  };
}

function strongestModel(models = []) {
  return sortModelsByStrength(models)[0] || DEFAULT_PUBLIC_MODEL;
}

function sortModelsByStrength(models = []) {
  const order = [
    'gpt-5.5-pro',
    'gpt-5.5-c',
    'gpt-5.5',
    'gpt-5.4-pro',
    'gpt-5.4-c',
    'gpt-5.4',
    'gpt-5.4-mini',
    'gpt-5.4-nano',
    'gpt-image-2',
    'gpt-image-1.5',
    'gpt-image-1',
    'gpt-5.3-codex',
    'deepseek-v4-flash',
    'deepseek-v4-pro',
    'deepseek-chat',
    'deepseek-reasoner',
    'claude-opus-4-6-thinking-c',
    'claude-opus-4-6-c',
    'claude-sonnet-4-5-c',
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

function findModelPrice(data, model) {
  const normalizedModel = normalizeOfficialModelName(model);
  return [...(data.priceDrafts || [])]
    .reverse()
    .find((draft) => normalizeOfficialModelName(draft.model) === normalizedModel || draft.model === '*');
}

function parseUpstreamUsage(bodyText) {
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

function estimatePromptTokens(input) {
  if (!Array.isArray(input)) {
    return Math.max(1, Math.ceil(String(input || '').length / 4));
  }
  const text = input.map(inputText).join('\n');
  return Math.max(1, Math.ceil(text.length / 4));
}

function inputText(item) {
  if (typeof item === 'string') return item;
  if (typeof item?.content === 'string') return item.content;
  return JSON.stringify(item?.content || item || '');
}

function priceUsageCents(price, promptTokens, completionTokens) {
  const inputCny = (Number(promptTokens || 0) / 1_000_000) * Number(price.inputSaleCnyPerMillion || 0);
  const outputCny = (Number(completionTokens || 0) / 1_000_000) * Number(price.outputSaleCnyPerMillion || 0);
  return Math.max(1, Math.ceil((inputCny + outputCny) * 100));
}

function reconcileUserBalance(user) {
  user.packageQuotaCents = Math.max(0, Number(user.packageQuotaCents || 0));
  user.boosterQuotaCents = Math.max(0, Number(user.boosterQuotaCents || 0));
  user.balanceCents = user.packageQuotaCents + user.boosterQuotaCents;
}

function expireUserPlanIfNeeded(data, user, serverOptions, options = {}) {
  const plan = String(user.plan || '');
  const planCanExpire = plan.includes('日卡') || plan.includes('月卡');
  if (!planCanExpire) {
    reconcileUserBalance(user);
    return false;
  }

  const expiresAtMs = planExpiryMs(user);
  if (!Number.isFinite(expiresAtMs) || currentDate(serverOptions).getTime() < expiresAtMs) {
    reconcileUserBalance(user);
    return false;
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
    data.events.push({
      type: 'plan_expired',
      userId: user.id,
      plan: expiredPlan,
      at: now,
    });
  }
  return true;
}

function planExpiryMs(user) {
  if (user.planExpiresAt) {
    return Date.parse(user.planExpiresAt);
  }
  if (user.renewalDate && user.renewalDate !== '-') {
    return Date.parse(`${user.renewalDate}T00:00:00.000Z`);
  }
  return Number.NaN;
}

function currentDate(serverOptions = {}) {
  const value = typeof serverOptions.nowFactory === 'function' ? serverOptions.nowFactory() : new Date();
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return new Date();
  }
  return date;
}

function buildModelUsage(data, user) {
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

function buildUsageRecords(data, user) {
  const keyById = new Map(
    data.userKeys
      .filter((key) => key.userId === user.id)
      .map((key) => [key.id, key]),
  );
  return data.events
    .filter((event) => event.type === 'gateway_routed' && event.userId === user.id)
    .slice(-80)
    .reverse()
    .map((event) => {
      const key = keyById.get(event.keyId);
      return {
        id: `${event.at || ''}-${event.keyId || ''}-${event.model || ''}`,
        apiKey: event.apiKeyPreview || key?.preview || 'sk-******',
        model: normalizeOfficialModelName(event.model || 'unknown'),
        inferenceEffort: event.inferenceEffort || '默认',
        endpoint: event.endpoint || '-',
        type: event.requestType || '文本',
        billingMode: event.billingMode || '余额',
        client: event.client || clientLabelFromEvent(event),
        tokens: compactTokenText(event.totalTokens || 0),
        amount: formatUsdFromCnyCents(event.quotaCost || 0),
        amountCny: formatCny(event.quotaCost || 0),
        latency: event.latencyMs ? `${Math.round(Number(event.latencyMs || 0))}ms` : '-',
        status: event.status || 'success',
        at: event.at || '',
      };
    });
}

function buildUsageAnomalies(data, user) {
  const routedEvents = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  if (routedEvents.length === 0) {
    return [];
  }
  const now = currentDate();
  const today = now.toISOString().slice(0, 10);
  const currentMonth = now.toISOString().slice(0, 7);
  const todayEvents = routedEvents.filter((item) => String(item.at || '').startsWith(today));
  const monthEvents = routedEvents.filter((item) => String(item.at || '').startsWith(currentMonth));
  const todayCost = sumEventField(todayEvents, 'quotaCost');
  const monthCost = sumEventField(monthEvents, 'quotaCost');
  const largestEvent = [...todayEvents].sort((left, right) => Number(right.quotaCost || 0) - Number(left.quotaCost || 0))[0];
  const rows = [];
  const remaining = availableQuotaCents(user);

  if (todayCost > 0 && remaining > 0 && todayCost >= remaining * 0.5) {
    rows.push({
      id: 'today-spend-balance-ratio',
      severity: todayCost >= remaining ? 'critical' : 'warning',
      title: '今日消耗偏高',
      detail: `今日已用 ${formatUsdFromCnyCents(todayCost)}，接近当前剩余额度 ${formatUsdFromCnyCents(remaining)}。`,
      action: '建议检查记录页和 Key 使用方',
      at: largestEvent?.at || now.toISOString(),
    });
  }

  if (largestEvent && Number(largestEvent.quotaCost || 0) >= Math.max(50, monthCost * 0.6)) {
    rows.push({
      id: 'single-call-cost-spike',
      severity: Number(largestEvent.quotaCost || 0) >= Math.max(200, monthCost * 0.8) ? 'critical' : 'warning',
      title: '单次调用费用突增',
      detail: `${largestEvent.model || '模型'} 单次消耗 ${formatUsdFromCnyCents(largestEvent.quotaCost)}。`,
      action: '建议核对上下文长度、图片请求和调用客户端',
      at: largestEvent.at || now.toISOString(),
    });
  }

  const slowEvents = todayEvents.filter((item) => Number(item.latencyMs || 0) >= 5000);
  if (slowEvents.length >= 2) {
    rows.push({
      id: 'latency-spike',
      severity: 'warning',
      title: '延迟异常',
      detail: `今日 ${slowEvents.length} 次请求超过 5 秒。`,
      action: '建议查看通道页是否有降级渠道',
      at: slowEvents.at(-1)?.at || now.toISOString(),
    });
  }

  return rows.slice(0, 4);
}

function sumEventField(events, field) {
  return events.reduce((sum, item) => sum + Number(item[field] || 0), 0);
}

function buildRecentLogs(data, user) {
  const allowedTypes = new Set([
    'gateway_routed',
    'redeemed',
    'payment_order_created',
    'manual_recharged',
    'recharged',
    'balance_alert_sent',
    'key_created',
    'key_enabled',
    'key_disabled',
    'profile_updated',
  ]);
  return data.events
    .filter((event) => event.userId === user.id && allowedTypes.has(event.type))
    .slice(-5)
    .reverse()
    .map((event) => ({
      type: event.type || 'event',
      at: event.at || '',
      detail: userEventDetail(event),
    }));
}

function userEventDetail(event) {
  if (event.type === 'gateway_routed') {
    return `${event.model || '模型'} · ${formatUsdFromCnyCents(event.quotaCost)} · ${clientLabelFromEvent(event)}`;
  }
  if (event.type === 'redeemed') return `兑换到账 ${event.credit ? event.credit : ''}`.trim();
  if (event.type === 'payment_order_created') return `充值单 ${formatUsdFromCnyCents(event.creditCents || event.amountCents)}`;
  if (event.type === 'manual_recharged' || event.type === 'recharged') return `余额到账 ${formatUsdFromCnyCents(event.creditCents || event.amountCents)}`;
  if (event.type === 'balance_alert_sent') return '余额预警已发送';
  if (event.type === 'key_created') return '新 Key 已创建';
  if (event.type === 'key_enabled') return 'Key 已开启';
  if (event.type === 'key_disabled') return 'Key 已暂停';
  if (event.type === 'profile_updated') return event.emailChanged ? '资料已更新，邮箱待验证' : '资料已更新';
  return '系统事件';
}

function clientLabelFromEvent(event) {
  return event.client || clientLabelFromSessionId(event.sessionId || event.fristSessionId || event.metadata?.frist_session_id) || 'API';
}

function clientLabelFromRequest(request, body = {}) {
  const explicit = headerValue(request, 'x-frist-client') || body.metadata?.frist_client || body.metadata?.client;
  const normalizedExplicit = normalizeClientLabel(explicit);
  if (normalizedExplicit) return normalizedExplicit;
  const sessionLabel = clientLabelFromSessionId(body.metadata?.frist_session_id);
  if (sessionLabel) return sessionLabel;
  const userAgent = headerValue(request, 'user-agent').toLowerCase();
  if (/macintosh|mac os|darwin/.test(userAgent)) return 'MacBook';
  if (/windows|win64|win32/.test(userAgent)) return 'PC';
  if (/iphone|android|mobile/.test(userAgent)) return '移动端';
  return 'API';
}

function clientLabelFromSessionId(value) {
  const text = String(value || '').toLowerCase();
  if (!text) return '';
  if (text.includes('playground') || text.includes('connectivity') || text.includes('square')) return '广场';
  if (text.includes('mac') || text.includes('darwin')) return 'MacBook';
  if (text.includes('pc') || text.includes('windows')) return 'PC';
  if (text.includes('codex')) return 'Codex';
  if (text.includes('claude')) return 'Claude';
  return '';
}

function normalizeClientLabel(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return '';
  if (['square', 'playground', 'web'].includes(text)) return '广场';
  if (['mac', 'macbook', 'darwin'].includes(text)) return 'MacBook';
  if (['pc', 'windows'].includes(text)) return 'PC';
  if (text.includes('codex')) return 'Codex';
  if (text.includes('claude')) return 'Claude';
  return String(value || '').trim().slice(0, 24);
}

function buildChannelChecks(data) {
  const grouped = new Map();
  for (const credential of data.credentials) {
    const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
    const source = data.supplierProfiles.find((item) => item.id === credential.sourceId) || {};
    const pool = normalizePool(credential.pool || source.pool || 'default') || 'default';
    const provider = effectiveCredentialGroup(credential);
    const key = `${pool}:${credential.sourceId || provider}`;
    const current = grouped.get(key) || {
      model: models[0] || DEFAULT_MODEL,
      provider,
      channel: '',
      pool,
      poolLabel: poolTypeLabel(pool),
      total: 0,
      healthy: 0,
      down: 0,
      slow: 0,
      latencyMs: 0,
      latencyTotal: 0,
      latencySamples: 0,
      checkedAt: '',
      status: credential.status,
      endpoint: '/v1',
      history: [],
      models: new Set(),
    };
    for (const model of models) {
      current.models.add(normalizeOfficialModelName(model));
    }
    const isHealthy = credential.enabled && credential.status === 'healthy' && isCredentialRouteApproved(credential);
    const latency = Number(credential.latencyMs || 0);
    const hasRealLatency = isHealthy && Number.isFinite(latency) && latency > 0 && latency < 999999;
    const bucket = isHealthy ? (hasRealLatency && latency > 1600 ? 'slow' : 'ok') : 'down';
    current.total += 1;
    current.healthy += isHealthy ? 1 : 0;
    current.down += isHealthy ? 0 : 1;
    current.slow += bucket === 'slow' ? 1 : 0;
    if (isHealthy) {
      if (hasRealLatency) {
        current.latencyMs = current.latencyMs ? Math.min(current.latencyMs, latency) : latency;
        current.latencyTotal += latency;
        current.latencySamples += 1;
      }
      current.status = 'healthy';
    } else if (!current.healthy) {
      current.status = credential.status || current.status || 'failed';
    }
    current.checkedAt = [current.checkedAt, credential.updatedAt].filter(Boolean).sort().at(-1) || '';
    current.endpoint = '/v1';
    current.history.push(bucket);
    grouped.set(key, current);
  }

  return [...grouped.values()]
    .sort((left, right) => poolPriority(left.pool) - poolPriority(right.pool) || left.channel.localeCompare(right.channel))
    .map((item, index) => {
      const channel = publicPoolChannelLabel(index + 1);
      const availabilityPercent = item.total ? Math.round((item.healthy / item.total) * 1000) / 10 : 0;
      const averageLatencyMs = item.latencySamples ? Math.round(item.latencyTotal / item.latencySamples) : 0;
      const monitorStatus =
        item.healthy === 0
          ? '异常'
          : item.down > 0 || item.slow > 0
            ? '降级'
            : '正常';
      const status = item.healthy > 0 ? (item.slow > 0 ? 'slow' : 'healthy') : item.status;
      const primaryModel = normalizeOfficialModelName([...item.models][0] || item.model);
      return {
        model: primaryModel,
        provider: item.provider,
        channel,
        pool: item.pool,
        poolLabel: item.poolLabel,
        endpoint: item.endpoint || '/v1',
        ok: item.healthy > 0,
        status,
        latencyMs: item.latencySamples ? item.latencyMs : 0,
        averageLatencyMs,
        checkedAt: item.checkedAt,
        availability: `${availabilityPercent}%`,
        availability7d: availabilityPercent,
        availability_7d: availabilityPercent,
        availability15d: availabilityPercent,
        availability30d: availabilityPercent,
        availability_15d: availabilityPercent,
        availability_30d: availabilityPercent,
        availabilityWindow: '当前库存快照',
        healthyCount: item.healthy,
        totalCount: item.total,
        downCount: item.down,
        slowCount: item.slow,
        successLabel: `${item.healthy}/${item.total} 可用`,
        latencyLabel: item.latencySamples ? `最低 ${item.latencyMs}ms / 平均 ${averageLatencyMs}ms` : '等待真实请求更新',
        monitorIntervalSeconds: 60,
        monitorStatus,
        officialStatus: monitorStatus,
        history: item.history.slice(-60),
        sla: buildChannelSlaSummary(data, primaryModel, {
          availabilityPercent,
          history: item.history,
          checkedAt: item.checkedAt,
        }),
      };
    });
}

function publicPoolChannelLabel(index) {
  const safeIndex = Math.max(1, Number(index || 1));
  return `卡商${safeIndex}`;
}

function poolTypeLabel(pool) {
  const normalized = normalizePool(pool || 'default') || 'default';
  const labels = {
    hour: '小时卡号池',
    day: '日卡号池',
    month: '月卡号池',
    unlimited: '不限时号池',
    default: '默认号池',
  };
  return labels[normalized] || '号池渠道';
}

function recordChannelProbeEvent(data, credential, status, reason, serverOptions, extra = {}) {
  if (!credential) {
    return;
  }
  const now = currentDate(serverOptions).toISOString();
  const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
  const bucket = status === 'ok' || status === 'slow'
    ? status
    : status === 'exhausted'
      ? 'down'
      : 'down';
  for (const model of models) {
    data.channelProbeEvents.push({
      id: createId('sla'),
      model,
      provider: providerFromModel(model),
      credentialId: credential.id,
      status: bucket,
      reason: String(reason || '').slice(0, 120),
      latencyMs: Math.max(0, Number(extra.latencyMs ?? credential.latencyMs ?? 0) || 0),
      pool: credential.pool || '',
      at: now,
    });
  }
  pruneChannelProbeEvents(data, serverOptions);
}

function pruneChannelProbeEvents(data, serverOptions) {
  const retentionDays = Number(serverOptions.slaRetentionDays || DEFAULT_SLA_RETENTION_DAYS);
  const cutoff = currentDate(serverOptions).getTime() - Math.max(1, retentionDays) * 86_400_000;
  data.channelProbeEvents = (data.channelProbeEvents || [])
    .filter((event) => {
      const time = Date.parse(event.at || '');
      return Number.isFinite(time) && time >= cutoff;
    })
    .slice(-20_000);
}

function buildChannelSlaSummary(data, model, fallback = {}) {
  const normalizedModel = normalizeOfficialModelName(model);
  const events = (data.channelProbeEvents || [])
    .filter((event) => normalizeOfficialModelName(event.model) === normalizedModel)
    .sort((left, right) => String(left.at || '').localeCompare(String(right.at || '')));
  if (!events.length) {
    return {
      window: '当前库存快照',
      availability7d: fallback.availabilityPercent || 0,
      availability15d: fallback.availabilityPercent || 0,
      availability30d: fallback.availabilityPercent || 0,
      samples7d: 0,
      samples15d: 0,
      samples30d: 0,
      lastIncidentAt: '',
      lastIncidentReason: '',
      history: (fallback.history || []).slice(-60),
      checkedAt: fallback.checkedAt || '',
    };
  }
  const now = Date.now();
  const summary7d = summarizeSlaWindow(events, now - 7 * 86_400_000);
  const summary15d = summarizeSlaWindow(events, now - 15 * 86_400_000);
  const summary30d = summarizeSlaWindow(events, now - 30 * 86_400_000);
  const incidents = events.filter((event) => event.status === 'down');
  const lastIncident = incidents.at(-1);
  return {
    window: '真实探测事件',
    availability7d: summary7d.availability,
    availability15d: summary15d.availability,
    availability30d: summary30d.availability,
    samples7d: summary7d.samples,
    samples15d: summary15d.samples,
    samples30d: summary30d.samples,
    lastIncidentAt: lastIncident?.at || '',
    lastIncidentReason: lastIncident?.reason || '',
    history: events.slice(-60).map((event) => event.status),
    checkedAt: events.at(-1)?.at || '',
  };
}

function summarizeSlaWindow(events, cutoffMs) {
  const windowEvents = events.filter((event) => Date.parse(event.at || '') >= cutoffMs);
  const samples = windowEvents.length;
  if (!samples) {
    return { availability: 0, samples: 0 };
  }
  const healthy = windowEvents.filter((event) => event.status === 'ok' || event.status === 'slow').length;
  return {
    availability: Math.round((healthy / samples) * 1000) / 10,
    samples,
  };
}

function buildModelCatalog(data) {
  const liveByModel = buildLiveModelMap(data);
  const rowsByModel = new Map(
    DEFAULT_MODEL_CATALOG.map((item) => {
      const model = normalizeOfficialModelName(item.model);
      const price = findModelPrice(data, model);
      return [
        model,
        {
          ...item,
          model,
          price: price ? priceLabel(price) : item.price || '官方价格待同步',
        },
      ];
    }),
  );

  for (const model of uniqueStrings(data.credentials.flatMap((credential) => credential.models || []))) {
    const live = liveByModel.get(model);
    const price = findModelPrice(data, model);
    rowsByModel.set(model, {
      model,
      family: live?.provider || providerFromModel(model),
      tagline: taglineForModel(model),
      context: contextForModel(model),
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

function providerFromModel(model = '') {
  const value = String(model || '').toLowerCase();
  if (value.includes('gpt') || value.includes('openai')) return 'OpenAI';
  if (value.includes('deepseek')) return 'DeepSeek';
  if (value.includes('gemini')) return 'Gemini';
  return 'Claude';
}

function taglineForModel(model = '') {
  if (/image|dall/i.test(model)) return '图片生成';
  if (/gpt/i.test(model)) return '推理和代码';
  if (/claude/i.test(model)) return '长文和工具调用';
  if (/gemini/i.test(model)) return '多模态和轻量任务';
  return '通用模型';
}

function contextForModel(model = '') {
  if (/image|dall/i.test(model)) return '按图计费';
  if (/gpt-5|claude/i.test(model)) return '长上下文';
  return '按模型能力';
}

function priceLabel(price) {
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

function buildInventorySummary(data) {
  const buckets = new Map();
  for (const credential of data.credentials) {
    const group = effectiveCredentialGroup(credential);
    const key = `${credential.pool || 'default'}:${group}`;
    const current = buckets.get(key) || {
      pool: credential.pool || 'default',
      providerGroup: group,
      totalKeys: 0,
      healthyKeys: 0,
      quotaRemaining: 0,
      quotaTotal: 0,
      wasteEstimate: 0,
      nearestExpiresAt: '',
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
      ...item,
      totalCount: item.totalKeys,
      healthyCount: item.healthyKeys,
      remainingRatio: item.quotaTotal > 0 ? Number((item.quotaRemaining / item.quotaTotal).toFixed(4)) : 0,
      quotaRemainingText: formatCny(item.quotaRemaining),
      quotaTotalText: formatCny(item.quotaTotal),
      wasteText: formatCny(item.wasteEstimate),
    }));
}

async function buildProductionReadiness(data, serverOptions) {
  const backup = buildBackupReadiness(data, serverOptions);
  const payment = buildPaymentClosureStatus(serverOptions);
  const checks = [
    {
      id: 'brand_domain',
      label: '固定品牌域名',
      ok: isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) && !isTemporaryHost(serverOptions.canonicalHost),
      detail: serverOptions.canonicalHost || '未配置',
    },
    {
      id: 'database',
      label: '数据库替代 JSON runtime',
      ok: Boolean(serverOptions.newApiEnabled && serverOptions.requireNewApiDatabase),
      detail: serverOptions.newApiEnabled ? 'New-API 桥接已启用' : '仍在 JSON runtime 模式',
    },
    {
      id: 'backup_monitoring',
      label: '备份监控',
      ok: backup.ready,
      detail: backup.message,
    },
    {
      id: 'admin_2fa',
      label: '管理员 2FA',
      ok: Boolean(serverOptions.requireAdmin2fa && serverOptions.adminTotpSecrets.length > 0),
      detail: serverOptions.requireAdmin2fa ? '已要求 TOTP 二次验证' : '未启用',
    },
    {
      id: 'merchant_payment',
      label: '真实支付商户闭环',
      ok: payment.ready,
      detail: payment.ready ? '至少一个商户回调可用' : '未接通真实商户',
    },
    {
      id: 'channel_sla',
      label: '长期渠道 SLA 记录',
      ok: (data.channelProbeEvents || []).length > 0,
      detail: `${(data.channelProbeEvents || []).length} 条探测事件`,
    },
  ];
  return {
    enforceProductionReadiness: Boolean(serverOptions.enforceProductionReadiness),
    ready: checks.every((check) => check.ok),
    checks,
    payment,
    backup,
    sla: {
      retentionDays: Number(serverOptions.slaRetentionDays || DEFAULT_SLA_RETENTION_DAYS),
      eventCount: (data.channelProbeEvents || []).length,
      models: uniqueStrings((data.channelProbeEvents || []).map((event) => event.model)).length,
    },
  };
}

function buildBackupReadiness(data, serverOptions) {
  const backup = normalizeBackupStatusRecord(data.backupStatus);
  const maxAgeHours = Number(serverOptions.backupStatusMaxAgeHours || 26);
  const lastBackupMs = Date.parse(backup.lastBackupAt || '');
  const lastRestoreMs = Date.parse(backup.lastRestoreTestAt || '');
  const nowMs = currentDate(serverOptions).getTime();
  const fresh = Number.isFinite(lastBackupMs) && nowMs - lastBackupMs <= maxAgeHours * 3_600_000;
  const restoreTested = Number.isFinite(lastRestoreMs) && nowMs - lastRestoreMs <= 30 * 86_400_000;
  const ready = backup.status === 'ok' && fresh && restoreTested;
  return {
    ...backup,
    ready,
    maxAgeHours,
    fresh,
    restoreTested,
    message: ready
      ? `最近备份 ${backup.lastBackupAt}，恢复演练 ${backup.lastRestoreTestAt}`
      : backup.message || '未看到新鲜备份和恢复演练记录',
  };
}

function recordBackupStatus(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const next = normalizeBackupStatusRecord({
    provider: body.provider,
    target: body.target,
    lastBackupAt: body.lastBackupAt || now,
    lastRestoreTestAt: body.lastRestoreTestAt,
    status: body.status || 'ok',
    artifact: body.artifact,
    sizeBytes: body.sizeBytes,
    checksum: body.checksum,
    message: body.message,
    updatedAt: now,
  });
  data.backupStatus = next;
  data.events.push({
    type: 'backup_status_recorded',
    status: next.status,
    target: next.target,
    at: now,
  });
  return {
    backup: buildBackupReadiness(data, serverOptions),
    productionReadiness: null,
    events: sanitizeAdminEvents(data.events),
  };
}

function buildPlusAccountSummary(accounts, serverOptions = {}) {
  const now = currentDate(serverOptions);
  const active = accounts.filter((account) => account.status === 'active').length;
  const dueSoon = accounts.filter((account) => {
    const daysLeft = plusAccountRenewalDaysLeft(account.plusRenewalAt, now);
    return daysLeft !== null && daysLeft >= 0 && daysLeft <= 5;
  }).length;
  const blocked = accounts.filter((account) =>
    account.status === 'risk_hold' ||
    account.status === 'retired' ||
    account.complianceStatus === 'blocked',
  ).length;
  const totalTry = accounts.reduce((sum, account) => sum + Number(account.appleBalanceTry || 0), 0);
  return {
    total: accounts.length,
    active,
    dueSoon,
    blocked,
    totalAppleBalanceTry: round2(totalTry),
    reminderText: accounts.length
      ? `${dueSoon} 个账号 5 天内需处理，${blocked} 个处于风险/停用状态`
      : '暂无 Plus 账号资产',
  };
}

function buildRtAccountSummary(accounts) {
  const active = accounts.filter((account) => account.status === 'active').length;
  const ready = accounts.filter((account) => account.status === 'ready_for_refresh').length;
  const needsRefresh = accounts.filter((account) => account.status === 'needs_refresh').length;
  const blocked = accounts.filter((account) => account.status === 'blocked' || account.status === 'retired').length;
  const byPlatform = accounts.reduce((summary, account) => {
    const platform = account.platform || 'codex';
    summary[platform] = (summary[platform] || 0) + 1;
    return summary;
  }, {});
  return {
    total: accounts.length,
    active,
    ready,
    needsRefresh,
    blocked,
    byPlatform,
    reminderText: accounts.length
      ? `${ready} 个待刷新，${needsRefresh} 个需要重新授权，${blocked} 个已停用`
      : '暂无 RT 账号',
  };
}

function effectiveCredentialGroup(credential) {
  const explicit = normalizeModelGroup(credential.modelGroup || '');
  if (explicit !== 'All') {
    return explicit;
  }
  return inferProviderGroup((credential.models || []).join('\n'));
}

function estimateCredentialWaste(credential) {
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

function sanitizeUser(user) {
  const displayName = String(user.displayName || user.nickname || '').trim();
  return {
    id: user.id,
    email: user.email,
    emailMasked: maskEmail(user.email),
    displayName: displayName || String(user.email || '').split('@')[0] || 'Frist',
    avatarUrl: sanitizeAvatarUrl(user.avatarUrl || ''),
    emailVerified: Boolean(user.emailVerified),
    isAdmin: Boolean(user.isAdmin),
    plan: user.plan,
    renewalDate: user.renewalDate,
    userInitials: initialsFromDisplayName(displayName || user.email),
  };
}

function sanitizeAvatarUrl(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const url = new URL(raw);
    if (!/^https?:$/i.test(url.protocol)) return '';
    return url.href.slice(0, 500);
  } catch {
    return '';
  }
}

function sanitizeUserKey(key, options = {}) {
  return {
    id: key.id,
    name: key.name,
    preview: publicUserKeyPreview(key.preview || key.secret),
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

function publicUserKeyPreview(value) {
  return maskKey(String(value || ''));
}

function sanitizeCredential(credential) {
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

function sanitizePaymentOrder(order) {
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
    provider: order.provider || '',
    qrCode: order.qrCode || '',
    notifyUrl: order.notifyUrl || '',
    transactionId: order.transactionId || '',
    status: order.status,
    paidAt: order.paidAt || '',
    createdAt: order.createdAt,
    updatedAt: order.updatedAt,
  };
}

function sanitizeRedemptionCard(card) {
  return {
    id: card.id,
    batchId: card.batchId || '',
    code: card.code,
    label: card.label || 'Frist-API 兑换码',
    plan: card.plan || 'balance',
    durationDays: Number(card.durationDays || 0),
    quotaUsd: Number(card.quotaUsd || 0),
    priceCny: Number(card.priceCny || 0),
    credit: formatUsdFromCnyCents(card.creditCents),
    creditCny: formatCny(card.creditCents),
    creditCents: Number(card.creditCents || 0),
    status: card.status || 'unused',
    source: card.source || 'xianyu',
    note: card.note || '',
    createdAt: card.createdAt || '',
    updatedAt: card.updatedAt || '',
    redeemedAt: card.redeemedAt || '',
    redeemedEmail: maskEmail(card.redeemedEmail || ''),
  };
}

function sanitizePlusAccount(account, serverOptions = {}) {
  const renewalDaysLeft = plusAccountRenewalDaysLeft(account.plusRenewalAt, currentDate(serverOptions));
  return {
    id: account.id,
    label: sanitizeLedgerLabel(account.label, {
      fallback: 'ChatGPT Plus 账号',
      email: account.openaiEmail || account.appleEmail || '',
      accountId: '',
      refreshToken: '',
    }),
    openaiEmail: maskEmail(account.openaiEmail || ''),
    appleEmail: maskEmail(account.appleEmail || ''),
    openaiEmailHint: emailDomain(account.openaiEmail || ''),
    appleEmailHint: emailDomain(account.appleEmail || ''),
    region: account.region || 'Other',
    status: account.status || 'warming',
    complianceStatus: account.complianceStatus || 'needs_review',
    billingMethod: account.billingMethod || 'apple_iap',
    appleBalanceTry: Number(account.appleBalanceTry || 0),
    monthlyCostTry: Number(account.monthlyCostTry || 0),
    plusRenewalAt: account.plusRenewalAt || '',
    renewalDaysLeft,
    renewalText: formatRenewalText(renewalDaysLeft, account.plusRenewalAt),
    lastCheckedAt: account.lastCheckedAt || '',
    deviceProfile: account.deviceProfile || '',
    browserProfile: account.browserProfile || '',
    riskNote: account.riskNote || '',
    operatorNote: account.operatorNote || '',
    secretPreview: account.secrets ? '已保存，管理端脱敏' : '未保存',
    routingEnabled: false,
    createdAt: account.createdAt || '',
    updatedAt: account.updatedAt || '',
  };
}

function sanitizeRtAccount(account) {
  return {
    id: account.id,
    label: sanitizeLedgerLabel(account.label, {
      fallback: 'RT 账号',
      email: account.email || '',
      accountId: account.accountId || '',
      refreshToken: account.refreshToken || '',
    }),
    platform: account.platform || 'codex',
    status: account.status || 'ready_for_refresh',
    email: maskEmail(account.email || ''),
    emailHint: emailDomain(account.email || ''),
    accountId: maskAccountId(account.accountId || ''),
    accountIdHint: tailHint(account.accountId || ''),
    refreshTokenPreview: maskRefreshToken(account.refreshToken || ''),
    refreshTokenFingerprint: account.refreshTokenFingerprint || tokenFingerprint(account.refreshToken || ''),
    sourceLabel: account.sourceLabel || '',
    accountType: account.accountType || '',
    note: account.note || '',
    lastRefreshAt: account.lastRefreshAt || '',
    expiresAt: account.expiresAt || '',
    importedAt: account.importedAt || account.createdAt || '',
    routingEnabled: false,
    createdAt: account.createdAt || '',
    updatedAt: account.updatedAt || '',
  };
}

function emailDomain(email) {
  const [, domain = ''] = String(email || '').split('@');
  return domain ? `@${domain}` : '';
}

function sanitizeLedgerLabel(value, { fallback, email, accountId, refreshToken }) {
  let label = String(value || '').trim();
  if (!label) return fallback;
  if (email) {
    label = label.replaceAll(email, maskEmail(email));
  }
  if (accountId) {
    label = label.replaceAll(accountId, maskAccountId(accountId));
  }
  if (refreshToken) {
    label = label.replaceAll(refreshToken, maskRefreshToken(refreshToken));
  }
  return label.slice(0, 80) || fallback;
}

function plusAccountRenewalDaysLeft(value, nowValue = new Date()) {
  if (!value) return null;
  const renewal = Date.parse(value);
  if (!Number.isFinite(renewal)) return null;
  const now = nowValue instanceof Date ? nowValue.getTime() : Date.parse(nowValue);
  if (!Number.isFinite(now)) return null;
  return Math.ceil((renewal - now) / 86_400_000);
}

function formatRenewalText(daysLeft, value) {
  if (!value) return '未登记续费日';
  if (daysLeft === null) return '续费日期无效';
  if (daysLeft < 0) return `已过期 ${Math.abs(daysLeft)} 天`;
  if (daysLeft === 0) return '今天到期';
  return `${daysLeft} 天后到期`;
}

function parseRtImportText(input) {
  if (Array.isArray(input)) {
    return input.flatMap((item) => parseRtImportItem(item));
  }
  if (input && typeof input === 'object') {
    return parseRtImportItem(input);
  }
  const raw = String(input || '').trim();
  if (!raw) return [];
  if (raw.startsWith('[') || raw.startsWith('{')) {
    const parsed = JSON.parse(raw);
    return parseRtImportText(parsed);
  }
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [refreshToken, email = '', accountId = ''] = line.split(/[,\t|]/).map((part) => part.trim());
      return {
        refreshToken,
        email,
        accountId,
      };
    });
}

function parseRtImportItem(item) {
  if (typeof item === 'string') {
    return parseRtImportText(item);
  }
  if (!item || typeof item !== 'object') {
    return [];
  }
  return [
    {
      label: item.label,
      platform: item.platform || item.provider,
      status: item.status,
      email: item.email,
      accountId: item.accountId ?? item.account_id,
      refreshToken: item.refreshToken ?? item.refresh_token ?? item.rt ?? item.token,
      sourceLabel: item.sourceLabel || item.source || item.file,
      accountType: item.accountType || item.type,
      note: item.note || item.riskNote,
      lastRefreshAt: item.lastRefreshAt || item.last_refresh,
      expiresAt: item.expiresAt || item.expired,
    },
  ];
}

function sanitizeParsedOrder(parsed) {
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
    inventorySummary: [
      {
        pool: parsed.pool,
        providerGroup: parsed.providerGroup,
        totalCount: parsed.keys.length,
        healthyCount: parsed.keys.length,
        quotaRemaining: parsed.keys.reduce((sum, key) => sum + Number(key.quotaRemaining || 0), 0),
        quotaTotal: parsed.keys.reduce((sum, key) => sum + Number(key.quotaTotal || 0), 0),
        wasteText: parsed.expiresAt ? '待写入后计算' : '无到期浪费',
      },
    ],
  };
}

function sanitizeAdminEvents(events) {
  return [...events]
    .slice(-50)
    .reverse()
    .map((event) => ({
      type: event.type,
      at: event.at || '',
      detail: adminEventDetail(event),
    }));
}

function adminEventDetail(event) {
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
  if (event.type === 'redemption_cards_created') return `生成兑换卡 ${event.count || 0} 张`;
  if (event.type === 'plus_account_upserted') return `Plus 账号台账已更新: ${event.status || 'warming'}`;
  if (event.type === 'rt_accounts_imported') return `RT 账号导入 ${event.count || 0} 个，跳过 ${event.skipped || 0} 个`;
  if (event.type === 'admin_auth_failed') return `管理认证失败: ${event.path || '/api/admin/*'} · ${event.ipHash || 'unknown'}`;
  if (event.type === 'plan_expired') return `${event.plan || '套餐'} 已到期，套餐额度已清零`;
  if (event.type === 'payment_order_created') return `用户发起充值 ${formatCny(event.amountCents)}`;
  if (event.type === 'manual_recharged') return `人工入账 ${formatCny(event.amountCents)}`;
  return '系统事件';
}

function createId(prefix) {
  return `${prefix}-${randomBytes(12).toString('base64url')}`;
}

function randomCardCodeSegment() {
  const alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  let text = '';
  for (let index = 0; index < 5; index += 1) {
    text += alphabet[randomInt(alphabet.length)];
  }
  return text;
}

function normalizeCardPrefix(value) {
  const text = String(value || DEFAULT_CARD_BATCH_PREFIX).trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  return (text || DEFAULT_CARD_BATCH_PREFIX).slice(0, 10);
}

function clampInteger(value, min, max) {
  const number = Math.round(Number(value || min));
  if (!Number.isFinite(number)) return min;
  return Math.min(max, Math.max(min, number));
}

function cardLabelForPlan(plan, body = {}) {
  const quotaUsd = Number(body.quotaUsd || body.creditUsd || 0);
  if (plan === 'day') return `Codex API ${quotaUsd || 30}刀额度/日卡`;
  if (plan === 'month') return `Codex API ${quotaUsd || 300}刀额度/月卡`;
  return `Codex API ${quotaUsd || 30}刀额度/不限时`;
}

function buildRedemptionCardExport(cards) {
  return cards
    .map((card) => [
      card.code,
      card.label,
      formatUsdFromCnyCents(card.creditCents),
      card.plan,
      card.durationDays ? `${card.durationDays}天` : '不限时',
    ].join('\t'))
    .join('\n');
}

function hashPassword(password, salt) {
  const iterations = 210_000;
  const passwordSalt = randomBytes(16).toString('base64url');
  const digest = pbkdf2Sync(String(password), `${salt}:${passwordSalt}`, iterations, 32, 'sha256').toString('base64url');
  return `pbkdf2-sha256$${iterations}$${passwordSalt}$${digest}`;
}

function verifyPassword(password, storedHash, salts) {
  const stored = String(storedHash || '');
  const candidates = Array.isArray(salts) ? salts : [salts];
  if (stored.startsWith('pbkdf2-sha256$')) {
    const [, iterationsText, passwordSalt, expectedDigest] = stored.split('$');
    const iterations = Number(iterationsText);
    if (!Number.isSafeInteger(iterations) || iterations < 100_000 || !passwordSalt || !expectedDigest) {
      return { ok: false, secret: '' };
    }
    const matchedSecret = candidates.find((salt) => {
      const actualDigest = pbkdf2Sync(String(password), `${salt}:${passwordSalt}`, iterations, 32, 'sha256').toString('base64url');
      return safeEqual(actualDigest, expectedDigest);
    });
    return { ok: Boolean(matchedSecret), secret: matchedSecret || '' };
  }
  const matchedSecret = candidates.find((salt) => safeEqual(legacyHashPassword(password, salt), stored));
  return { ok: Boolean(matchedSecret), secret: matchedSecret || '' };
}

function isModernPasswordHash(storedHash) {
  return String(storedHash || '').startsWith('pbkdf2-sha256$');
}

function legacyHashPassword(password, salt) {
  return createHash('sha256').update(`${salt}:${password}`).digest('hex');
}

function hashPasswordResetCode(code, salt) {
  return createHash('sha256').update(`${salt}:password-reset:${String(code || '').trim()}`).digest('hex');
}

function parseSecretList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim()).filter(Boolean);
  }
  return String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function normalizeTotpSecrets(value) {
  const items = Array.isArray(value) ? value : String(value || '').split(/[,\s]+/);
  return items
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .map((item) => {
      const decoded = decodeBase32Secret(item);
      return decoded.length >= 10 ? decoded : null;
    })
    .filter(Boolean);
}

function verifyTotpCode(secretBuffers, code, nowValue = new Date()) {
  const normalizedCode = String(code || '').replace(/\D/g, '');
  if (!/^\d{6}$/.test(normalizedCode) || !Array.isArray(secretBuffers) || secretBuffers.length === 0) {
    return false;
  }
  const nowMs = nowValue instanceof Date ? nowValue.getTime() : Date.parse(nowValue);
  const counter = Math.floor((Number.isFinite(nowMs) ? nowMs : Date.now()) / 1000 / TOTP_STEP_SECONDS);
  for (const secret of secretBuffers) {
    for (const offset of [-1, 0, 1]) {
      if (safeEqual(generateTotpCode(secret, counter + offset), normalizedCode)) {
        return true;
      }
    }
  }
  return false;
}

function generateTotpCode(secret, counter) {
  const buffer = Buffer.alloc(8);
  const safeCounter = Math.max(0, Number(counter || 0));
  buffer.writeUInt32BE(Math.floor(safeCounter / 0x100000000), 0);
  buffer.writeUInt32BE(safeCounter >>> 0, 4);
  const digest = createHmac('sha1', secret).update(buffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % 10 ** TOTP_DIGITS).padStart(TOTP_DIGITS, '0');
}

function decodeBase32Secret(value) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = String(value || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  let bits = '';
  for (const char of clean) {
    const index = alphabet.indexOf(char);
    if (index === -1) continue;
    bits += index.toString(2).padStart(5, '0');
  }
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}

function hashId(value) {
  return createHash('sha1').update(String(value)).digest('hex').slice(0, 12);
}

function hashAdminClaimCode(value) {
  return createHash('sha256').update(String(value || '').trim()).digest('hex');
}

function parseAdminClaimCodes(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value || '')
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function generateVerificationCode() {
  return String(randomBytes(4).readUInt32BE(0) % 1000000).padStart(6, '0');
}

function generateCustomerApiKey() {
  return `fk-live-${randomBytes(32).toString('base64url')}`;
}

function maskKey(value) {
  const key = String(value || '');
  if (!key) return 'sk-******';
  const prefix = /^sk-/i.test(key)
    ? 'sk'
    : /^fk-live-/i.test(key)
      ? 'fk-live'
      : key.slice(0, Math.min(6, key.length)).replace(/-$/, '');
  return `${prefix}-••••••${key.slice(-4)}`;
}

function maskRefreshToken(value) {
  const token = String(value || '');
  if (!token) return 'rt-******';
  const prefix = token.includes('_') ? token.split('_')[0] : token.slice(0, Math.min(6, token.length));
  return `${prefix}-••••••${token.slice(-6)}`;
}

function maskAccountId(value) {
  const text = String(value || '');
  if (!text) return '';
  return `${text.slice(0, Math.min(6, text.length))}••••${text.slice(-4)}`;
}

function tailHint(value) {
  const text = String(value || '');
  return text ? `尾号 ${text.slice(-4)}` : '';
}

function tokenFingerprint(value) {
  const text = String(value || '').trim();
  return text ? createHash('sha256').update(text).digest('hex').slice(0, 16) : '';
}

function initialsFromEmail(email) {
  const name = String(email || 'fa').split('@')[0];
  return name.slice(0, 2).toUpperCase();
}

function initialsFromDisplayName(value) {
  const cleaned = String(value || 'fa').replace(/@.*$/, '').replace(/[_-]+/g, ' ').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return String(parts[0] || 'fa').slice(0, 2).toUpperCase();
}

function addDays(date, days) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + Number(days || 0));
  return next;
}

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function formatCny(cents) {
  return `¥${(Number(cents || 0) / 100).toFixed(2)}`;
}

function formatUsdFromCnyCents(cents, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return `$${(Number(cents || 0) / 100 / safeRate).toFixed(2)}`;
}

function usdNumberFromCnyCents(cents, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return round2Finite(Number(cents || 0) / 100 / safeRate);
}

function cnyNumberFromCents(cents) {
  return round2Finite(Number(cents || 0) / 100);
}

function formatUsdPriceFromCny(value, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return `$${(Number(value || 0) / safeRate).toFixed(3)}`;
}

function compactTokenText(tokens) {
  const value = Number(tokens || 0);
  if (!Number.isFinite(value) || value <= 0) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(Math.round(value));
}

function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function round2Finite(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return round2(number);
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isCli) {
  const port = Number(process.env.FRIST_API_PORT || process.env.PORT || 3180);
  const host = process.env.FRIST_API_HOST || '127.0.0.1';
  const server = createFristApiServer({
    exposeVerificationCode: process.env.FRIST_API_EXPOSE_VERIFICATION_CODE === '1',
  });
  server.listen(port, host, () => {
    console.log(`Frist-API server listening on http://${host}:${port}`);
  });
  let closing = false;
  const closeGracefully = (signal) => {
    if (closing) return;
    closing = true;
    console.log(`Frist-API server received ${signal}, closing...`);
    const forceTimer = setTimeout(() => {
      console.error('Frist-API server close timeout, exiting.');
      process.exit(1);
    }, 8_000);
    forceTimer.unref();
    server.close((error) => {
      if (error) {
        console.error(`Frist-API server close failed: ${error.message}`);
        process.exit(1);
      }
      process.exit(0);
    });
  };
  process.once('SIGTERM', () => closeGracefully('SIGTERM'));
  process.once('SIGINT', () => closeGracefully('SIGINT'));
}

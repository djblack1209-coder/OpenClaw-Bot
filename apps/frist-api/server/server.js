import { createHash, randomBytes } from 'node:crypto';
import { createServer } from 'node:http';
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { dirname, extname, join, normalize, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildCcSwitchImportUrl,
  inferProviderGroup,
  modelMatchesGroup,
  normalizeBaseUrl,
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
const DEFAULT_PROBE_MODELS = [
  'claude-opus-4-6-thinking-c',
  'claude-opus-4-6-c',
  'claude-sonnet-4-5-c',
  'gpt-5.5',
  'gpt-5.4',
  'gpt-5.4-mini',
  'gpt-image-2',
  'gpt-5.3-codex',
  'gemini-2.5-flash',
];
const DEFAULT_QUOTA_COST = 10;
const PRIMARY_SOURCE_TYPE = 'authorized';
const BACKUP_SOURCE_TYPES = new Set(['cpa_json_backup', 'chong_backup', 'manual_backup']);
const DEFAULT_RECHARGE_PLANS = Object.freeze([
  Object.freeze({
    id: 'codex-30-day',
    label: 'Codex API 30刀额度/日卡',
    quotaUsd: 30,
    priceCny: 5.88,
    durationDays: 1,
    plan: 'day',
  }),
  Object.freeze({
    id: 'codex-30-unlimited',
    label: 'Codex API 30刀额度/不限时',
    quotaUsd: 30,
    priceCny: 8.88,
    durationDays: 0,
    plan: 'balance',
  }),
  Object.freeze({
    id: 'codex-100-unlimited',
    label: 'Codex API 100刀额度/不限时',
    quotaUsd: 100,
    priceCny: 28.88,
    durationDays: 0,
    plan: 'balance',
  }),
  Object.freeze({
    id: 'codex-500-unlimited',
    label: 'Codex API 500刀额度/不限时',
    quotaUsd: 500,
    priceCny: 68.88,
    durationDays: 0,
    plan: 'balance',
  }),
  Object.freeze({
    id: 'codex-1000-unlimited',
    label: 'Codex API 1000刀额度/不限时',
    quotaUsd: 1000,
    priceCny: 118.88,
    durationDays: 0,
    plan: 'balance',
  }),
]);
const DEFAULT_MODEL_PRICES = Object.freeze([
  Object.freeze({
    model: 'gpt-5.5',
    currency: 'CNY',
    inputCostCnyPerMillion: 8,
    outputCostCnyPerMillion: 48,
    inputSaleCnyPerMillion: 8,
    outputSaleCnyPerMillion: 48,
    source: 'official',
  }),
  Object.freeze({
    model: 'gpt-5.5-c',
    currency: 'CNY',
    inputCostCnyPerMillion: 8,
    outputCostCnyPerMillion: 48,
    inputSaleCnyPerMillion: 8,
    outputSaleCnyPerMillion: 48,
    source: 'official',
  }),
  Object.freeze({
    model: 'claude-opus-4-6-thinking-c',
    currency: 'CNY',
    inputCostCnyPerMillion: 108,
    outputCostCnyPerMillion: 540,
    inputSaleCnyPerMillion: 108,
    outputSaleCnyPerMillion: 540,
    source: 'official',
  }),
  Object.freeze({
    model: 'claude-opus-4-6-c',
    currency: 'CNY',
    inputCostCnyPerMillion: 108,
    outputCostCnyPerMillion: 540,
    inputSaleCnyPerMillion: 108,
    outputSaleCnyPerMillion: 540,
    source: 'official',
  }),
  Object.freeze({
    model: 'claude-sonnet-4-5-c',
    currency: 'CNY',
    inputCostCnyPerMillion: 21.6,
    outputCostCnyPerMillion: 108,
    inputSaleCnyPerMillion: 21.6,
    outputSaleCnyPerMillion: 108,
    source: 'official',
  }),
]);
const DEFAULT_MODEL_CATALOG = [
  {
    model: 'gpt-5.5',
    family: 'OpenAI',
    tagline: '推理和代码主力',
    context: '1M 上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-5.4',
    family: 'OpenAI',
    tagline: '日常问答和代码补全',
    context: '1M 上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-5.4-mini',
    family: 'OpenAI',
    tagline: '轻量代码和快速问答',
    context: '长上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-image-2',
    family: 'OpenAI',
    tagline: '图片生成',
    context: '按图计费',
    price: '按张结算',
    available: true,
  },
  {
    model: 'gpt-5.3-codex',
    family: 'OpenAI',
    tagline: 'Codex 专用代码模型',
    context: '长上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: DEFAULT_MODEL,
    family: 'Claude',
    tagline: '复杂开发和长链路推理',
    context: '1M 上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
];
const SESSION_COOKIE = 'frist_session';
const DAY_CARD_CODES = new Map([
  ['FRIST-DAY-001', { plan: '日卡', days: 1, packageCents: 800 }],
  ['FRIST-MONTH-001', { plan: '月卡 Pro', days: 30, packageCents: 8000 }],
  ['FRIST-BOOST-100', { plan: null, days: 0, boosterCents: 10000 }],
]);

const CONTENT_TYPES = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml; charset=utf-8'],
]);
const ROOT_GATEWAY_PATHS = new Set([
  '/chat/completions',
  '/openai/chat/completions',
  '/responses',
  '/openai/responses',
  '/images/generations',
  '/openai/images/generations',
  '/messages',
]);

export function createFristApiServer(options = {}) {
  const serverOptions = normalizeServerOptions(options);
  const store = createRuntimeStore(serverOptions.dataFile);
  const securityState = createSecurityState();

  const server = createServer(async (request, response) => {
    try {
      if (request.method === 'OPTIONS') {
        writeNoContent(response);
        return;
      }

      const url = new URL(request.url || '/', requestOrigin(request));
      if (url.pathname.startsWith('/api/frist/')) {
        await handleCustomerApi({ request, response, url, store, serverOptions, securityState });
        return;
      }
      if (url.pathname.startsWith('/api/admin/')) {
        await handleAdminApi({ request, response, url, store, serverOptions });
        return;
      }
      if (url.pathname.startsWith('/v1/') || ROOT_GATEWAY_PATHS.has(url.pathname)) {
        await handleGatewayApi({ request, response, url, store, serverOptions });
        return;
      }

      await serveStaticFile({ request, response, url, publicDir: serverOptions.publicDir, serverOptions, store });
    } catch (error) {
      const message = error.expose ? error.message : '服务暂时不可用';
      writeJson(response, error.statusCode || 500, { error: message });
    }
  });
  if (Number.isFinite(serverOptions.keepAliveTimeoutMs)) {
    server.keepAliveTimeout = Number(serverOptions.keepAliveTimeoutMs);
  }
  return server;
}

async function handleCustomerApi({ request, response, url, store, serverOptions, securityState }) {
  if (request.method === 'GET' && url.pathname === '/api/frist/challenge') {
    writeJson(response, 200, createCaptchaChallenge(securityState, serverOptions));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/register') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    requireCaptchaIfEnabled(securityState, body, serverOptions);
    const result = await store.mutate((data) => registerCustomer(data, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': `${SESSION_COOKIE}=${result.sessionToken}; Path=/; HttpOnly; SameSite=Lax`,
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/login') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    requireCaptchaIfEnabled(securityState, body, serverOptions);
    const result = await store.mutate((data) => loginCustomer(data, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': `${SESSION_COOKIE}=${result.sessionToken}; Path=/; HttpOnly; SameSite=Lax`,
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => changeCustomerPassword(data, request, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/verify') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => verifyCustomer(data, request, body));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/recharge') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => rechargeCustomer(data, request, body, serverOptions));
    writeJson(response, result.status || 200, result.body || result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/redeem') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => redeemCustomerCode(data, request, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/token') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => createCustomerToken(data, request, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  const tokenMatch = url.pathname.match(/^\/api\/frist\/token\/([^/]+)$/);
  if (request.method === 'PATCH' && tokenMatch) {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => updateCustomerToken(data, request, tokenMatch[1], body));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'DELETE' && tokenMatch) {
    const result = await store.mutate((data) => deleteCustomerToken(data, request, tokenMatch[1]));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/import-url') {
    const data = await store.load();
    const result = buildCustomerImportUrl(data, request, url, serverOptions);
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/dashboard') {
    const data = await store.load();
    const { user } = findSession(data, request);
    writeJson(response, 200, user ? buildDashboard(data, user, serverOptions) : buildGuestDashboard(data));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/admin/claim') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => claimAdminIdentity(data, request, body, serverOptions));
    writeJson(response, 200, result, adminGateCookie(serverOptions));
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function handleAdminApi({ request, response, url, store, serverOptions }) {
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
      inventorySummary: buildInventorySummary(data),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments/parse-order') {
    const body = await readJsonBody(request);
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    const parsed = parseSupplierOrderText(body.orderText || '', body.pricing || {});
    writeJson(response, 200, sanitizeParsedOrder(parsed));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/customers/recharge') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      return manualRechargeCustomer(data, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      return replenishCredentials(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function handleGatewayApi({ request, response, url, store, serverOptions }) {
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
    [
      '/v1/messages',
      {
        upstreamAttempts: [
          {
            upstreamPath: '/chat/completions',
            transformRequest: anthropicMessagesToChatCompletion,
            transformResponse: chatCompletionToAnthropicMessageResponse,
          },
        ],
      },
    ],
    [
      '/messages',
      {
        upstreamAttempts: [
          {
            upstreamPath: '/chat/completions',
            transformRequest: anthropicMessagesToChatCompletion,
            transformResponse: chatCompletionToAnthropicMessageResponse,
          },
        ],
      },
    ],
  ]);
  const routeOptions = upstreamPathByRoute.get(url.pathname);
  if (request.method !== 'POST' || !routeOptions) {
    writeJson(response, 404, { error: '接口不存在' });
    return;
  }

  const body = await readJsonBody(request);
  const result = await store.mutate((data) =>
    routeChatCompletion(data, request, body, serverOptions, routeOptions),
  );
  response.writeHead(result.status, {
    'content-type': result.contentType,
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
    ...(result.bodyStream ? { 'x-accel-buffering': 'no' } : {}),
  });
  if (result.bodyStream) {
    await pipeReadableStreamToResponse(result.bodyStream, response);
    return;
  }
  response.end(result.bodyText);
}

function registerCustomer(data, body, serverOptions) {
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
    passwordHash: hashPassword(password, serverOptions.sessionSecret),
    verificationCode,
    plan: '默认套餐',
    renewalDate: formatDate(addDays(new Date(), 30)),
    planExpiresAt: '',
    balanceCents: 0,
    packageQuotaCents: 0,
    boosterQuotaCents: 0,
    createdAt: now,
    updatedAt: now,
  };
  data.users.push(user);

  const sessionToken = createId('sess');
  data.sessions[sessionToken] = user.id;
  data.events.push({ type: 'registered', userId: user.id, at: now });

  const responseUser = sanitizeUser(user);
  return {
    sessionToken,
    body: {
      user: responseUser,
      ...(serverOptions.exposeVerificationCode && verificationCode ? { verificationCode } : {}),
    },
  };
}

function loginCustomer(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  const user = data.users.find((item) => item.email === email);
  if (!user || user.passwordHash !== hashPassword(password, serverOptions.sessionSecret)) {
    throw publicError(401, '邮箱或密码不正确');
  }

  const now = new Date().toISOString();
  const sessionToken = createId('sess');
  data.sessions[sessionToken] = user.id;
  user.updatedAt = now;
  data.events.push({ type: 'logged_in', userId: user.id, at: now });
  return {
    sessionToken,
    body: {
      user: sanitizeUser(user),
      account: accountFromUser(data, user),
    },
  };
}

function changeCustomerPassword(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const oldPassword = String(body.oldPassword || '');
  const newPassword = String(body.newPassword || '');
  if (user.passwordHash !== hashPassword(oldPassword, serverOptions.sessionSecret)) {
    throw publicError(401, '旧密码不正确');
  }
  if (newPassword.length < 6) {
    throw publicError(400, '新密码至少 6 位');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(newPassword, serverOptions.sessionSecret);
  user.updatedAt = now;
  data.events.push({ type: 'password_changed', userId: user.id, at: now });
  return { user: sanitizeUser(user), account: accountFromUser(data, user) };
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

function rechargeCustomer(data, request, body, serverOptions) {
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
    const paymentOrder = {
      id: createId('pay'),
      userId: user.id,
      email: user.email,
      amountCents,
      creditCents,
      quotaUsd: selectedPlan?.quotaUsd || 0,
      planId: selectedPlan?.id || '',
      plan: planType,
      method: String(body.method || 'manual_pending'),
      status: 'pending_manual_payment',
      createdAt: now,
      updatedAt: now,
    };
    data.paymentOrders.unshift(paymentOrder);
    data.events.push({
      type: 'payment_order_created',
      userId: user.id,
      amountCents,
      creditCents,
      plan: paymentOrder.plan,
      method: paymentOrder.method,
      at: now,
    });
    return {
      status: 202,
      body: {
        paymentOrder: sanitizePaymentOrder(paymentOrder),
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

function redeemCustomerCode(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = String(body.code || '').trim().toUpperCase();
  const rule = DAY_CARD_CODES.get(code);
  if (!rule) {
    throw publicError(400, '兑换码无效');
  }
  if (data.redemptions.some((item) => item.code === code)) {
    throw publicError(409, '兑换码已使用');
  }

  const now = currentDate(serverOptions);
  if (rule.plan) {
    user.plan = rule.plan;
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
    plan: rule.plan || '加油包',
    at: user.updatedAt,
  });
  data.events.push({ type: 'redeemed', userId: user.id, code, at: user.updatedAt });
  return { account: accountFromUser(data, user), user: sanitizeUser(user) };
}

function createCustomerToken(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  if (serverOptions.requireEmailVerification && !user.emailVerified) {
    throw publicError(403, '请先完成邮箱验证');
  }

  const now = new Date().toISOString();
  const secret = `fk-live-${randomBytes(18).toString('base64url')}`;
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
  const key = data.userKeys.find((item) => item.userId === user.id && item.enabled);
  if (!key) {
    throw publicError(409, '没有可用的 API Key');
  }

  const target = url.searchParams.get('target') || 'Claude';
  const requestedModel = url.searchParams.get('model') || '';
  const baseUrl = serverOptions.publicGatewayBaseUrl || `${requestOrigin(request)}/v1`;
  const availableModels = availableModelsForCustomer(data, user, key, requestedModel);
  const defaultModel = strongestModel(availableModels);
  return {
    url: buildCcSwitchImportUrl({
      target,
      apiKey: key.secret,
      baseUrl,
      model: requestedModel || defaultModel,
      defaultModel,
      availableModels,
      modelGroup: key.modelGroup,
      planExpiresAt: user.planExpiresAt,
    }),
    defaultModel,
    availableModels,
  };
}

function buildDashboard(data, user, serverOptions) {
  expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
  const apiKeys = data.userKeys
    .filter((item) => item.userId === user.id)
    .map((item) => sanitizeUserKey(item, { revealSecret: true }));
  return {
    authenticated: true,
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    apiKeys,
    modelUsage: buildModelUsage(data, user),
    channelChecks: buildChannelChecks(data),
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
  };
}

function buildGuestDashboard(data) {
  return {
    authenticated: false,
    account: {
      plan: '未登录',
      renewalDate: '-',
      balance: '¥0.00',
      todayCost: '¥0.00',
      monthCost: '¥0.00',
      packageQuota: '¥0.00',
      boosterQuota: '¥0.00',
      quotaLeft: '¥0.00',
      usageTotal: '¥0.00',
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
    apiKeys: [],
    modelUsage: [],
    channelChecks: buildChannelChecks(data),
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
  };
}

async function replenishCredentials(data, body, serverOptions) {
  const parsedOrder = body.orderText ? parseSupplierOrderText(body.orderText, body.pricing || {}) : null;
  const normalizedBaseUrl = normalizeBaseUrl(body.baseUrl || parsedOrder?.baseUrl);
  const normalizedProxyBaseUrl = String(body.proxyBaseUrl || '').trim() ? normalizeBaseUrl(body.proxyBaseUrl) : '';
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
    probeMode,
    serverOptions,
  });
  const models = providedModels.length > 0 ? providedModels : probeReport.models;
  const sourceFingerprint = sourceType === PRIMARY_SOURCE_TYPE ? normalizedBaseUrl : `${sourceType}:${normalizedBaseUrl}`;
  const sourceId = `source-${hashId(sourceFingerprint)}`;
  const source = upsertSupplierProfile(data, {
    id: sourceId,
    baseUrl: normalizedBaseUrl,
    proxyBaseUrl: normalizedProxyBaseUrl,
    routeBaseUrl: probeReport.routeBaseUrl,
    pool,
    models,
    modelGroup,
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
      latencyMs: key.latencyProvided && Number.isFinite(key.latencyMs) ? key.latencyMs : Number(probe.latencyMs || 999),
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

async function probeReplenishment({ baseUrl, proxyBaseUrl, keyInputs, models, probeMode, serverOptions }) {
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

async function probeCredentialRoutes({ baseUrl, proxyBaseUrl, rawKey, authConfig = {}, models, serverOptions, collectAllModels }) {
  const direct = await probeCredentialRouteCandidates(baseUrl, rawKey, models, serverOptions, { collectAllModels, authConfig });
  if (!proxyBaseUrl) {
    return {
      ...direct,
      connectionPath: 'direct',
      routeBaseUrl: direct.routeBaseUrl || baseUrl,
    };
  }

  const proxy = await probeCredentialRouteCandidates(proxyBaseUrl, rawKey, models, serverOptions, { collectAllModels, authConfig });
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

async function probeCredentialChat(baseUrl, rawKey, models, serverOptions, options = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const supportedModels = [];
  let bestLatencyMs = 0;
  let lastFailure = null;

  for (const model of models) {
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
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    let upstream;
    try {
      upstream = await callGatewayAttempts(credential, routedBody, serverOptions, options);
    } catch {
      failCredential(data, credential, 'upstream_network_failed');
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (isQuotaExhaustedResponse(upstream)) {
      exhaustCredential(data, credential, 'quota_exhausted_by_upstream');
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (shouldFailoverUpstream(upstream)) {
      failCredential(data, credential, `upstream_http_${upstream.status}`);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    if (upstream.status >= 200 && upstream.status < 300) {
      const quotaCost = resolveQuotaCostCents(data, model, routedBody, upstream, serverOptions);
      credential.quotaRemaining = Math.max(0, Number(credential.quotaRemaining || 0) - quotaCost);
      credential.status = credential.quotaRemaining > 0 ? 'healthy' : 'exhausted';
      credential.enabled = credential.quotaRemaining > 0;
      credential.updatedAt = new Date().toISOString();
      deductUserQuota(user, quotaCost);
      userKey.costCents += quotaCost;
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
        at: credential.updatedAt,
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
    });
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
  const upstreamUrl = `${normalizeBaseUrl(credential.routeBaseUrl || credential.baseUrl)}${upstreamPath}`;
  const response = await fetchImpl(upstreamUrl, {
    method: 'POST',
    headers: {
      ...authHeadersForKey(credential.rawKey, credential),
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const contentType = response.headers?.get?.('content-type') || 'application/json; charset=utf-8';
  if (options.streamResponse && response.status >= 200 && response.status < 300 && response.body) {
    return {
      status: response.status,
      contentType,
      bodyText: '',
      bodyStream: response.body,
    };
  }

  const bodyText = await response.text();
  return {
    status: response.status,
    contentType,
    bodyText,
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
  const left = 10 + randomBytes(1)[0] % 40;
  const right = 1 + randomBytes(1)[0] % 30;
  const id = createId('cap');
  securityState.captchas.set(id, {
    answer: String(left + right),
    expiresAt: Date.now() + Number(serverOptions.captchaTtlMs || 600_000),
  });
  return {
    required: true,
    id,
    question: `${left} + ${right} = ?`,
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
  securityState.captchas.delete(id);
  if (answer !== challenge.answer) {
    throw publicError(400, '验证码不正确');
  }
}

function cleanupCaptchas(securityState) {
  const now = Date.now();
  for (const [id, challenge] of securityState.captchas) {
    if (challenge.expiresAt < now) {
      securityState.captchas.delete(id);
    }
  }
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

async function pipeReadableStreamToResponse(bodyStream, response) {
  if (typeof bodyStream.getReader === 'function') {
    const reader = bodyStream.getReader();
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        response.write(normalizeStreamChunk(chunk.value));
      }
    } finally {
      reader.releaseLock?.();
      response.end();
    }
    return;
  }

  if (typeof bodyStream[Symbol.asyncIterator] === 'function') {
    try {
      for await (const chunk of bodyStream) {
        response.write(normalizeStreamChunk(chunk));
      }
    } finally {
      response.end();
    }
    return;
  }

  response.end();
}

function normalizeStreamChunk(chunk) {
  if (Buffer.isBuffer(chunk)) return chunk;
  if (chunk instanceof Uint8Array) return Buffer.from(chunk);
  return Buffer.from(String(chunk || ''), 'utf8');
}

function createRuntimeStore(dataFile) {
  let writeQueue = Promise.resolve();

  async function load() {
    try {
      const raw = await readFile(dataFile, 'utf8');
      return normalizeRuntimeData(JSON.parse(raw));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
      return normalizeRuntimeData({});
    }
  }

  async function save(data) {
    await mkdir(dirname(dataFile), { recursive: true });
    await writeFile(dataFile, `${JSON.stringify(normalizeRuntimeData(data), null, 2)}\n`, 'utf8');
  }

  async function mutate(mutator) {
    const run = writeQueue.then(async () => {
      const data = await load();
      const result = await mutator(data);
      await save(data);
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
    users: Array.isArray(data.users) ? data.users : [],
    sessions: data.sessions && typeof data.sessions === 'object' ? data.sessions : {},
    userKeys: Array.isArray(data.userKeys) ? data.userKeys : [],
    credentials: Array.isArray(data.credentials) ? data.credentials.map(normalizeCredentialRecord) : [],
    supplierProfiles: Array.isArray(data.supplierProfiles) ? data.supplierProfiles.map(normalizeSupplierProfileRecord) : [],
    priceDrafts: mergeModelPrices(Array.isArray(data.priceDrafts) ? data.priceDrafts : [], pricing.modelPrices),
    pricing,
    paymentOrders: Array.isArray(data.paymentOrders) ? data.paymentOrders : [],
    redemptions: Array.isArray(data.redemptions) ? data.redemptions : [],
    routeAffinities: data.routeAffinities && typeof data.routeAffinities === 'object' ? data.routeAffinities : {},
    lowInventoryAlerts: data.lowInventoryAlerts && typeof data.lowInventoryAlerts === 'object' ? data.lowInventoryAlerts : {},
    usedAdminClaimCodeHashes: Array.isArray(data.usedAdminClaimCodeHashes) ? data.usedAdminClaimCodeHashes : [],
    events: Array.isArray(data.events) ? data.events : [],
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
    merged.set(model, {
      model,
      currency: String(price.currency || 'CNY').toUpperCase(),
      inputCostCnyPerMillion: round2(Number(price.inputCostCnyPerMillion || 0)),
      outputCostCnyPerMillion: round2(Number(price.outputCostCnyPerMillion || 0)),
      inputSaleCnyPerMillion: round2(Number(price.inputSaleCnyPerMillion ?? price.inputCostCnyPerMillion ?? 0)),
      outputSaleCnyPerMillion: round2(Number(price.outputSaleCnyPerMillion ?? price.outputCostCnyPerMillion ?? 0)),
      source: String(price.source || 'official'),
      status: String(price.status || 'confirmed'),
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
    keepAliveTimeoutMs:
      options.keepAliveTimeoutMs === undefined && process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS === undefined
        ? Number.NaN
        : Number(options.keepAliveTimeoutMs ?? process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS),
    probeTimeoutMs: Number(options.probeTimeoutMs || process.env.FRIST_API_PROBE_TIMEOUT_MS || 2500),
    publicDir: options.publicDir ? resolve(options.publicDir) : resolve(root, '..'),
    publicGatewayBaseUrl: options.publicGatewayBaseUrl || process.env.FRIST_API_PUBLIC_GATEWAY_BASE_URL || '',
    quotaCost: Number(options.quotaCost || DEFAULT_QUOTA_COST),
    requireEmailVerification,
    requireCaptcha,
    sessionSecret: options.sessionSecret || process.env.FRIST_API_SESSION_SECRET || 'frist-api-dev-session-secret',
    allowDemoRecharge,
    allowInsecurePublicHttp:
      typeof options.allowInsecurePublicHttp === 'boolean'
        ? options.allowInsecurePublicHttp
        : process.env.FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP === '1',
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
  };
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
  if (
    !isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) &&
    !(serverOptions.allowInsecurePublicHttp && isPublicHttpGateway(serverOptions.publicGatewayBaseUrl))
  ) {
    problems.push('公开网关地址必须是 HTTPS 域名，或显式允许临时公网 HTTP IP');
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

function requireUserKey(data, request) {
  const authorization = request.headers.authorization || '';
  const xApiKey = request.headers['x-api-key'] || request.headers['anthropic-auth-token'] || '';
  const secret = authorization.match(/^Bearer\s+(.+)$/i)?.[1] || String(xApiKey || '').trim();
  const key = data.userKeys.find((item) => item.secret === secret);
  if (!key || !key.enabled) {
    throw publicError(401, 'API Key 不可用');
  }
  return key;
}

function requireAdmin(data, request, serverOptions) {
  const token = request.headers['x-admin-token'];
  if (token && token === serverOptions.adminToken) {
    return;
  }
  const { user } = findSession(data, request);
  if (user?.isAdmin) {
    return;
  }
  throw publicError(401, '管理员身份无效');
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
        latencyMs: 999,
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
      latencyMs: Number(item.latencyMs ?? 999),
      latencyProvided: item.latencyMs !== undefined,
      authHeaderName: String(item.authHeaderName || 'authorization').trim().toLowerCase(),
      authHeaderValuePrefix:
        item.authHeaderValuePrefix === ''
          ? ''
          : String(item.authHeaderValuePrefix || 'Bearer').trim(),
      extraHeaders: sanitizeExtraHeaders(item.extraHeaders),
      modelGroup: normalizeModelGroup(item.modelGroup || ''),
      cardType: normalizePool(item.cardType || ''),
      expiresAt: String(item.expiresAt || ''),
    }))
    .filter((item) => item.value);
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
    (item) => item.sourceId === nextCredential.sourceId && item.rawKey === nextCredential.rawKey,
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
    'set-cookie': `frist_admin_gate=${hashId(serverOptions.adminPageCode)}; Path=/; HttpOnly; SameSite=Lax`,
  };
}

async function readJsonBody(request) {
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

function writeJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-frist-session-id, x-conversation-id',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

function writeNoContent(response) {
  response.writeHead(204, {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type, authorization, x-api-key, anthropic-auth-token, x-admin-token, x-frist-session-id, x-conversation-id',
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
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const month = now.toISOString().slice(0, 7);
  const routedEvents = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  const todayEvents = routedEvents.filter((item) => String(item.at || '').startsWith(today));
  const monthEvents = routedEvents.filter((item) => String(item.at || '').startsWith(month));
  const todayCost = todayEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  const monthCost = monthEvents.reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
  return {
    plan: user.plan,
    renewalDate: user.renewalDate,
    balance: formatCny(user.balanceCents),
    packageQuota: formatCny(user.packageQuotaCents),
    boosterQuota: formatCny(user.boosterQuotaCents),
    quotaLeft: formatCny(user.balanceCents),
    todayCost: formatCny(todayCost),
    monthCost: formatCny(monthCost),
    usageTotal: formatCny(monthCost),
    todayCalls: `${todayEvents.length} 次`,
  };
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
    totals.set(event.model, (totals.get(event.model) || 0) + Number(event.quotaCost || 0));
  }
  return [...totals.entries()].map(([model, cost]) => ({
    model,
    amount: formatCny(cost),
    calls: `${events.filter((event) => event.model === model).length} 次`,
  }));
}

function buildChannelChecks(data) {
  const grouped = new Map();
  for (const credential of data.credentials) {
    const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
    for (const model of models) {
      const key = model;
      const current = grouped.get(key) || {
        model,
        provider: providerFromModel(model),
        total: 0,
        healthy: 0,
        latencyMs: 0,
        checkedAt: '',
        status: credential.status,
      };
      const isHealthy = credential.enabled && credential.status === 'healthy' && isCredentialRouteApproved(credential);
      current.total += 1;
      current.healthy += isHealthy ? 1 : 0;
      if (isHealthy) {
        const latency = Number(credential.latencyMs || 999999);
        current.latencyMs = current.latencyMs ? Math.min(current.latencyMs, latency) : latency;
        current.status = 'healthy';
      } else if (!current.healthy) {
        current.status = credential.status || current.status || 'failed';
      }
      current.checkedAt = [current.checkedAt, credential.updatedAt].filter(Boolean).sort().at(-1) || '';
      grouped.set(key, current);
    }
  }

  return [...grouped.values()]
    .sort((left, right) => `${left.provider}:${left.model}`.localeCompare(`${right.provider}:${right.model}`))
    .map((item) => ({
      model: normalizeOfficialModelName(item.model),
      provider: item.provider,
      channel: `${item.provider} 可用线路 ${item.healthy}/${item.total}`,
      ok: item.healthy > 0,
      status: item.healthy > 0 ? 'healthy' : item.status,
      latencyMs: item.healthy > 0 ? item.latencyMs : 0,
      checkedAt: item.checkedAt,
    }));
}

function buildModelCatalog(data) {
  const liveByModel = new Map(buildChannelChecks(data).map((item) => [normalizeOfficialModelName(item.model), item]));
  const rowsByModel = new Map(
    DEFAULT_MODEL_CATALOG.map((item) => {
      const model = normalizeOfficialModelName(item.model);
      const price = findModelPrice(data, model);
      return [
        model,
        {
          ...item,
          model,
          price: price ? priceLabel(price) : item.price || '按后台价格',
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
      price: price ? priceLabel(price) : rowsByModel.get(model)?.price || '按后台价格',
      available: live ? Boolean(live.ok) : true,
    });
  }

  return [...rowsByModel.values()].sort((left, right) => {
    const liveDelta = Number(right.available) - Number(left.available);
    if (liveDelta !== 0) return liveDelta;
    return `${left.family}:${left.model}`.localeCompare(`${right.family}:${right.model}`);
  });
}

function providerFromModel(model = '') {
  const value = String(model || '').toLowerCase();
  if (value.includes('gpt') || value.includes('openai')) return 'OpenAI';
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
  const input = Number(price.inputSaleCnyPerMillion || 0);
  const output = Number(price.outputSaleCnyPerMillion || 0);
  if (input <= 0 && output <= 0) {
    return '按后台价格';
  }
  return `¥${input}/¥${output} 每 1M`;
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

function sanitizeUserKey(key, options = {}) {
  return {
    id: key.id,
    name: key.name,
    preview: key.preview || maskKey(key.secret),
    ...(options.revealSecret ? { secret: key.secret } : {}),
    enabled: Boolean(key.enabled),
    modelGroup: key.modelGroup || 'All',
    cost: formatCny(key.costCents),
    tokens: key.tokens || '0.00M',
    lastUsed: key.lastUsed || '-',
    expiresAt: key.expiresAt || '-',
  };
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
    credit: formatCny(order.creditCents),
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
    return `${event.model || 'unknown'} 已路由，计费 ${formatCny(event.quotaCost)}`;
  }
  if (event.type === 'registered') return '新用户注册';
  if (event.type === 'logged_in') return '用户登录';
  if (event.type === 'redeemed') return `兑换码 ${event.code || ''} 已生效`;
  if (event.type === 'plan_expired') return `${event.plan || '套餐'} 已到期，套餐额度已清零`;
  if (event.type === 'payment_order_created') return `用户发起充值 ${formatCny(event.amountCents)}`;
  if (event.type === 'manual_recharged') return `人工入账 ${formatCny(event.amountCents)}`;
  return '系统事件';
}

function createId(prefix) {
  return `${prefix}-${randomBytes(12).toString('base64url')}`;
}

function hashPassword(password, salt) {
  return createHash('sha256').update(`${salt}:${password}`).digest('hex');
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

function maskKey(value) {
  const key = String(value || '');
  if (!key) return 'sk-******';
  const prefix = /^fk-live-/i.test(key) ? 'fk-live' : key.slice(0, Math.min(6, key.length)).replace(/-$/, '');
  return `${prefix}-••••••${key.slice(-4)}`;
}

function initialsFromEmail(email) {
  const name = String(email || 'fa').split('@')[0];
  return name.slice(0, 2).toUpperCase();
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

function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100;
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
}

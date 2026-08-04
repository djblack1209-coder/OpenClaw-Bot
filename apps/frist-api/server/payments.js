import { createDecipheriv, createSign, createVerify, randomBytes } from 'node:crypto';

import {
  addDays,
  formatDate,
  normalizeRechargePlan,
  reconcileUserBalance,
} from './shared.js';

export function normalizePem(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.replace(/\\n/g, '\n');
}

export function paymentConfigFromOptions(options = {}) {
  const publicBaseUrl = String(options.publicGatewayBaseUrl || '').replace(/\/v1\/?$/i, '').replace(/\/+$/, '');
  const configuredTimeout = Number(
    options.paymentRequestTimeoutMs ?? process.env.FRIST_API_PAYMENT_REQUEST_TIMEOUT_MS ?? 15_000,
  );
  const requestTimeoutMs = Number.isFinite(configuredTimeout)
    ? Math.min(120_000, Math.max(100, Math.round(configuredTimeout)))
    : 15_000;
  return {
    enabled: boolOption(options.paymentEnabled, process.env.FRIST_API_PAYMENT_ENABLED),
    publicBaseUrl,
    requestTimeoutMs,
    wechat: {
      enabled: boolOption(options.wechatPayEnabled, process.env.FRIST_API_WECHAT_PAY_ENABLED),
      appid: String(options.wechatPayAppId || process.env.FRIST_API_WECHAT_PAY_APPID || '').trim(),
      mchid: String(options.wechatPayMchId || process.env.FRIST_API_WECHAT_PAY_MCH_ID || '').trim(),
      serialNo: String(options.wechatPaySerialNo || process.env.FRIST_API_WECHAT_PAY_SERIAL_NO || '').trim(),
      privateKey: normalizePem(options.wechatPayPrivateKey || process.env.FRIST_API_WECHAT_PAY_PRIVATE_KEY || ''),
      publicKey: normalizePem(options.wechatPayPublicKey || process.env.FRIST_API_WECHAT_PAY_PUBLIC_KEY || ''),
      platformSerialNo: String(
        options.wechatPayPlatformSerialNo || process.env.FRIST_API_WECHAT_PAY_PLATFORM_SERIAL_NO || '',
      ).trim(),
      apiV3Key: String(options.wechatPayApiV3Key || process.env.FRIST_API_WECHAT_PAY_API_V3_KEY || ''),
      notifyUrl: String(options.wechatPayNotifyUrl || process.env.FRIST_API_WECHAT_PAY_NOTIFY_URL || '').trim(),
      gateway: String(options.wechatPayGateway || process.env.FRIST_API_WECHAT_PAY_GATEWAY || 'https://api.mch.weixin.qq.com').replace(/\/+$/, ''),
    },
    alipay: {
      enabled: boolOption(options.alipayEnabled, process.env.FRIST_API_ALIPAY_ENABLED),
      appId: String(options.alipayAppId || process.env.FRIST_API_ALIPAY_APP_ID || '').trim(),
      privateKey: normalizePem(options.alipayPrivateKey || process.env.FRIST_API_ALIPAY_PRIVATE_KEY || ''),
      publicKey: normalizePem(options.alipayPublicKey || process.env.FRIST_API_ALIPAY_PUBLIC_KEY || ''),
      notifyUrl: String(options.alipayNotifyUrl || process.env.FRIST_API_ALIPAY_NOTIFY_URL || '').trim(),
      gateway: String(options.alipayGateway || process.env.FRIST_API_ALIPAY_GATEWAY || 'https://openapi.alipay.com/gateway.do').trim(),
    },
  };
}

export function providerReady(config, provider) {
  if (!config?.enabled) return false;
  if (provider === 'wechat') {
    const item = config.wechat || {};
    return Boolean(
      item.enabled &&
      item.appid &&
      item.mchid &&
      item.serialNo &&
      item.privateKey &&
      item.publicKey &&
      item.platformSerialNo &&
      item.apiV3Key
    );
  }
  if (provider === 'alipay') {
    const item = config.alipay || {};
    return Boolean(item.enabled && item.appId && item.privateKey && item.publicKey);
  }
  return false;
}

export async function createProviderPayment({ provider, order, plan, fetchImpl, paymentConfig }) {
  if (provider === 'wechat') {
    return createWechatNativePayment({ order, plan, fetchImpl, paymentConfig });
  }
  if (provider === 'alipay') {
    return createAlipayPrecreatePayment({ order, plan, fetchImpl, paymentConfig });
  }
  throw publicPaymentError(400, '不支持的支付渠道');
}

async function createWechatNativePayment({ order, plan, fetchImpl, paymentConfig }) {
  const config = paymentConfig.wechat;
  assertFetch(fetchImpl);
  const notifyUrl = config.notifyUrl || `${paymentConfig.publicBaseUrl}/api/frist/payments/wechat/notify`;
  const body = {
    appid: config.appid,
    mchid: config.mchid,
    description: paymentDescription(plan),
    out_trade_no: order.id,
    notify_url: notifyUrl,
    amount: {
      total: Number(order.amountCents || 0),
      currency: 'CNY',
    },
  };
  const bodyText = JSON.stringify(body);
  const path = '/v3/pay/transactions/native';
  const response = await fetchPaymentGateway(fetchImpl, `${config.gateway}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: buildWechatAuthorization({
        method: 'POST',
        path,
        bodyText,
        mchid: config.mchid,
        serialNo: config.serialNo,
        privateKey: config.privateKey,
      }),
    },
    body: bodyText,
  }, paymentConfig.requestTimeoutMs);
  const text = await response.text();
  verifyWechatResponseSignature({ headers: response.headers, rawBody: text, config });
  const payload = parseJson(text);
  if (!response.ok || !payload.code_url) {
    throw publicPaymentError(502, payload.message || payload.code || `微信支付下单失败: ${response.status}`);
  }
  return {
    provider: 'wechat',
    notifyUrl,
    qrCode: payload.code_url,
    raw: payload,
  };
}

async function createAlipayPrecreatePayment({ order, plan, fetchImpl, paymentConfig }) {
  const config = paymentConfig.alipay;
  assertFetch(fetchImpl);
  const notifyUrl = config.notifyUrl || `${paymentConfig.publicBaseUrl}/api/frist/payments/alipay/notify`;
  const params = {
    app_id: config.appId,
    method: 'alipay.trade.precreate',
    charset: 'utf-8',
    sign_type: 'RSA2',
    timestamp: formatAlipayTimestamp(new Date()),
    version: '1.0',
    notify_url: notifyUrl,
    biz_content: JSON.stringify({
      out_trade_no: order.id,
      total_amount: (Number(order.amountCents || 0) / 100).toFixed(2),
      subject: paymentDescription(plan),
      product_code: 'FACE_TO_FACE_PAYMENT',
    }),
  };
  params.sign = signAlipayParams(params, config.privateKey);
  const response = await fetchPaymentGateway(fetchImpl, config.gateway, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
    },
    body: new URLSearchParams(params).toString(),
  }, paymentConfig.requestTimeoutMs);
  const text = await response.text();
  const payload = parseJson(text);
  const result = payload.alipay_trade_precreate_response || {};
  if (!payload.sign) {
    throw publicPaymentError(502, '支付宝下单响应签名缺失');
  }
  if (!verifyAlipayResponse(
    text,
    'alipay_trade_precreate_response',
    payload.sign,
    config.publicKey,
  )) {
    throw publicPaymentError(502, '支付宝下单响应签名验签失败');
  }
  if (!response.ok || result.code !== '10000' || !result.qr_code) {
    throw publicPaymentError(502, result.sub_msg || result.msg || `支付宝下单失败: ${response.status}`);
  }
  return {
    provider: 'alipay',
    notifyUrl,
    qrCode: result.qr_code,
    raw: result,
  };
}

export function buildWechatAuthorization({ method, path, bodyText, mchid, serialNo, privateKey }) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomBytes(16).toString('hex');
  const message = `${method}\n${path}\n${timestamp}\n${nonce}\n${bodyText || ''}\n`;
  const signature = createSign('RSA-SHA256').update(message).sign(privateKey, 'base64');
  return [
    'WECHATPAY2-SHA256-RSA2048',
    `mchid="${mchid}"`,
    `nonce_str="${nonce}"`,
    `signature="${signature}"`,
    `timestamp="${timestamp}"`,
    `serial_no="${serialNo}"`,
  ].join(' ');
}

// 按微信支付 API v3 原始报文合同验证平台应答，并阻断过期或序列号漂移的响应。
export function verifyWechatResponseSignature({ headers, rawBody, config }) {
  const { timestamp, nonce, signature } = validatedWechatSignatureHeaders({
    headers,
    config,
    statusCode: 502,
    context: '微信支付下单响应',
  });
  const message = `${timestamp}\n${nonce}\n${rawBody}\n`;
  let verified = false;
  try {
    verified = createVerify('RSA-SHA256')
      .update(message)
      .verify(config.publicKey, signature, 'base64');
  } catch {
    verified = false;
  }
  if (!verified) {
    throw publicPaymentError(502, '微信支付下单响应签名验签失败');
  }
}

export function verifyWechatNotification({ headers, rawBody, paymentConfig }) {
  const config = paymentConfig.wechat || {};
  if (!config.publicKey || !config.apiV3Key) {
    throw publicPaymentError(503, '微信支付回调验签配置未完成');
  }
  const { timestamp, nonce, signature } = validatedWechatSignatureHeaders({
    headers,
    config,
    statusCode: 400,
    context: '微信支付回调',
  });
  const message = `${timestamp}\n${nonce}\n${rawBody}\n`;
  let verified = false;
  try {
    verified = createVerify('RSA-SHA256').update(message).verify(config.publicKey, signature, 'base64');
  } catch {
    verified = false;
  }
  if (!verified) {
    throw publicPaymentError(400, '微信支付回调验签失败');
  }
  const payload = parseJson(rawBody);
  const resource = payload.resource || {};
  const plaintext = decryptWechatResource(resource, config.apiV3Key);
  return parseJson(plaintext);
}

// 下单响应与异步通知共用同一套签名时效和平台证书身份约束。
function validatedWechatSignatureHeaders({ headers, config, statusCode, context }) {
  const timestamp = String(header(headers, 'wechatpay-timestamp') || '');
  const nonce = String(header(headers, 'wechatpay-nonce') || '');
  const signature = String(header(headers, 'wechatpay-signature') || '');
  const serialNo = String(header(headers, 'wechatpay-serial') || '');
  if (!timestamp || !nonce || !signature || !serialNo) {
    throw publicPaymentError(statusCode, `${context}签名头缺失`);
  }
  if (!config?.platformSerialNo || serialNo !== config.platformSerialNo) {
    throw publicPaymentError(statusCode, `${context}平台序列号不匹配`);
  }
  const timestampSeconds = Number(timestamp);
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(timestampSeconds) || Math.abs(nowSeconds - timestampSeconds) > 300) {
    throw publicPaymentError(statusCode, `${context}签名时间戳无效`);
  }
  return { timestamp, nonce, signature, serialNo };
}

export function decryptWechatResource(resource, apiV3Key) {
  const ciphertext = Buffer.from(String(resource.ciphertext || ''), 'base64');
  if (ciphertext.length < 17) {
    throw publicPaymentError(400, '微信支付回调密文无效');
  }
  const decipher = createDecipheriv(
    'aes-256-gcm',
    Buffer.from(String(apiV3Key), 'utf8'),
    Buffer.from(String(resource.nonce || ''), 'utf8'),
  );
  decipher.setAuthTag(ciphertext.subarray(ciphertext.length - 16));
  decipher.setAAD(Buffer.from(String(resource.associated_data || ''), 'utf8'));
  return `${decipher.update(ciphertext.subarray(0, ciphertext.length - 16), undefined, 'utf8')}${decipher.final('utf8')}`;
}

export function parseAlipayNotification(rawBody, publicKey) {
  const params = Object.fromEntries(new URLSearchParams(rawBody));
  if (!verifyAlipayParams(params, publicKey)) {
    throw publicPaymentError(400, '支付宝回调验签失败');
  }
  return params;
}

// 验证微信回调后驱动支付订单状态机，任何身份、金额或交易号异常都失败关闭。
export function handleWechatPaymentNotification(data, request, rawBody, serverOptions) {
  const transaction = verifyWechatNotification({
    headers: request.headers,
    rawBody,
    paymentConfig: serverOptions.paymentConfig,
  });
  const orderId = String(transaction.out_trade_no || '').trim();
  if (!orderId) {
    throw publicPaymentError(400, '微信支付回调缺少订单号');
  }
  assertPaymentMerchantMatchesConfig('wechat', transaction, serverOptions.paymentConfig);
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

// 验证支付宝回调后驱动支付订单状态机，未成功状态只留审计记录而不入账。
export function handleAlipayPaymentNotification(data, rawBody, serverOptions) {
  const notification = parseAlipayNotification(rawBody, serverOptions.paymentConfig.alipay.publicKey);
  const orderId = String(notification.out_trade_no || '').trim();
  if (!orderId) {
    throw publicPaymentError(400, '支付宝回调缺少订单号');
  }
  assertPaymentMerchantMatchesConfig('alipay', notification, serverOptions.paymentConfig);
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

// 将平台交易原子绑定到唯一订单，并在全部不变量成立后才写入用户额度。
function confirmProviderPayment(data, orderId, details = {}) {
  const order = data.paymentOrders.find((item) => item.id === orderId);
  if (!order) {
    throw publicPaymentError(404, '支付订单不存在');
  }
  const provider = String(details.provider || '').trim();
  const transactionId = String(details.transactionId || '').trim();
  if (!provider || order.provider !== provider) {
    throw publicPaymentError(409, '支付订单渠道不匹配');
  }
  if (!transactionId) {
    throw publicPaymentError(400, '支付回调缺少平台交易号');
  }
  const user = data.users.find((item) => item.id === order.userId);
  if (!user) {
    throw publicPaymentError(404, '支付订单用户不存在');
  }
  const now = new Date().toISOString();
  if (order.status === 'paid' || order.status === 'confirmed') {
    if (order.transactionId !== transactionId) {
      throw publicPaymentError(409, '已入账订单的平台交易号不匹配');
    }
    // 已确认订单的重复通知不再追加审计事件，避免截获报文反复放大运行时文件。
    return { order, user, duplicate: true };
  }
  if (order.status !== 'pending_provider_payment') {
    throw publicPaymentError(409, '支付订单状态不允许渠道回调入账');
  }
  const transactionConflict = data.paymentOrders.find(
    (item) =>
      item.id !== orderId &&
      item.provider === provider &&
      item.transactionId === transactionId &&
      ['paid', 'confirmed'].includes(item.status),
  );
  if (transactionConflict) {
    throw publicPaymentError(409, '平台交易号已绑定其他订单');
  }
  assertPaymentAmountMatchesOrder(order, provider, details.rawPayload || details.payload || {});

  creditUserForOrder(user, order, now);
  order.status = 'paid';
  order.provider = provider;
  order.transactionId = transactionId;
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

// 将回调声明的商户身份与本地渠道配置做精确绑定。
function assertPaymentMerchantMatchesConfig(provider, payload, paymentConfig) {
  if (provider === 'wechat') {
    const expected = paymentConfig?.wechat || {};
    if (
      !expected.appid ||
      !expected.mchid ||
      String(payload?.appid || '') !== expected.appid ||
      String(payload?.mchid || '') !== expected.mchid
    ) {
      throw publicPaymentError(400, '微信支付回调商户身份不匹配');
    }
    return;
  }
  if (provider === 'alipay') {
    const expected = paymentConfig?.alipay || {};
    if (!expected.appId || String(payload?.app_id || '') !== expected.appId) {
      throw publicPaymentError(400, '支付宝回调商户身份不匹配');
    }
    return;
  }
  throw publicPaymentError(400, '支付回调渠道无效');
}

// 以最小货币单位比较平台实付金额，避免浮点误差和少付入账。
function assertPaymentAmountMatchesOrder(order, provider, payload) {
  const expected = Number(order.amountCents || 0);
  const actual = providerPaymentAmountCents(provider, payload);
  if (!Number.isFinite(actual) || actual !== expected) {
    throw publicPaymentError(400, '支付金额与订单金额不一致');
  }
}

// 统一提取微信分值和支付宝元值为整数分。
function providerPaymentAmountCents(provider, payload = {}) {
  if (provider === 'wechat') {
    return Number(payload?.amount?.total);
  }
  if (provider === 'alipay') {
    return yuanToCents(payload.total_amount);
  }
  return Number.NaN;
}

// 严格解析最多两位小数的人民币元值。
function yuanToCents(value) {
  const text = String(value ?? '').trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) {
    return Number.NaN;
  }
  const [yuan, cents = ''] = text.split('.');
  return Number(yuan) * 100 + Number(cents.padEnd(2, '0'));
}

// 根据订单套餐只执行一次额度入账，并立即重算总余额。
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

// 保存有限字段的回调审计事件，不写入用户标识或完整平台载荷。
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

// 汇总支付渠道配置闭环状态，供管理端展示缺失项。
export function buildPaymentClosureStatus(serverOptions) {
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
        ['platformSerialNo', 'FRIST_API_WECHAT_PAY_PLATFORM_SERIAL_NO'],
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

// 列出渠道就绪所需但尚未配置的环境变量。
function paymentMissingFields(config, fields) {
  return fields
    .filter(([key]) => {
      if (key === 'enabled') return !config.enabled;
      return !String(config[key] || '').trim();
    })
    .map(([, envName]) => envName);
}

// 将兼容别名收敛为稳定的支付方式标识。
export function normalizePaymentMethod(value) {
  const method = String(value || 'manual_pending').trim().toLowerCase();
  if (['wechat_native', 'wechat', 'wechat_pay', 'wxpay'].includes(method)) return 'wechat_native';
  if (['alipay_precreate', 'alipay', 'alipay_qr'].includes(method)) return 'alipay_precreate';
  return method || 'manual_pending';
}

// 从标准支付方式映射唯一提供商。
export function paymentProviderForMethod(method) {
  if (method === 'wechat_native') return 'wechat';
  if (method === 'alipay_precreate') return 'alipay';
  return '';
}

// 只把前端展示二维码所需字段带出提供商响应。
export function sanitizeProviderPayment(payment) {
  return {
    provider: payment.provider,
    notifyUrl: payment.notifyUrl,
    qrCode: payment.qrCode,
  };
}

// 剔除付款人标识并限制审计载荷长度。
function sanitizePaymentCallbackPayload(payload = {}) {
  const blocked = new Set(['openid', 'payer', 'buyer_logon_id', 'buyer_user_id', 'fund_bill_list']);
  return Object.fromEntries(
    Object.entries(payload)
      .filter(([key]) => !blocked.has(key))
      .map(([key, value]) => [key, typeof value === 'object' ? JSON.stringify(value).slice(0, 300) : String(value).slice(0, 300)]),
  );
}

export function signAlipayParams(params, privateKey) {
  return createSign('RSA-SHA256').update(alipaySignContent(params)).sign(privateKey, 'base64');
}

export function verifyAlipayParams(params, publicKey) {
  if (!publicKey) {
    throw publicPaymentError(503, '支付宝回调验签配置未完成');
  }
  const signature = params.sign || '';
  if (!signature) return false;
  return createVerify('RSA-SHA256')
    .update(alipaySignContent(params))
    .verify(publicKey, signature, 'base64');
}

function verifyAlipayResponse(rawBody, responseKey, signature, publicKey) {
  if (!rawBody || !responseKey || !signature || !publicKey) return false;
  try {
    const signedContent = extractTopLevelJsonValueRaw(rawBody, responseKey);
    return Boolean(
      signedContent &&
      createVerify('RSA-SHA256').update(signedContent).verify(publicKey, signature, 'base64')
    );
  } catch {
    return false;
  }
}

// 保留支付宝响应对象的原始 JSON 字节，避免解析后重排空格或转义导致合法签名失效。
function extractTopLevelJsonValueRaw(rawBody, expectedKey) {
  const text = String(rawBody || '');
  let cursor = skipJsonWhitespace(text, 0);
  let matchedValue = '';
  if (text[cursor] !== '{') throw new Error('支付宝响应不是 JSON 对象');
  cursor += 1;

  while (cursor < text.length) {
    cursor = skipJsonWhitespace(text, cursor);
    if (text[cursor] === '}') return matchedValue;
    const keyStart = cursor;
    const keyEnd = scanJsonStringEnd(text, keyStart);
    const key = JSON.parse(text.slice(keyStart, keyEnd));
    cursor = skipJsonWhitespace(text, keyEnd);
    if (text[cursor] !== ':') throw new Error('支付宝响应 JSON 缺少冒号');
    const valueStart = skipJsonWhitespace(text, cursor + 1);
    const valueEnd = scanJsonValueEnd(text, valueStart);
    if (key === expectedKey) {
      if (matchedValue) throw new Error('支付宝响应包含重复验签对象');
      matchedValue = text.slice(valueStart, valueEnd);
    }

    cursor = skipJsonWhitespace(text, valueEnd);
    if (text[cursor] === ',') {
      cursor += 1;
      continue;
    }
    if (text[cursor] === '}') return matchedValue;
    throw new Error('支付宝响应 JSON 顶层分隔符无效');
  }
  throw new Error('支付宝响应 JSON 未闭合');
}

function skipJsonWhitespace(text, start) {
  let cursor = start;
  while (cursor < text.length && /\s/.test(text[cursor])) cursor += 1;
  return cursor;
}

function scanJsonStringEnd(text, start) {
  if (text[start] !== '"') throw new Error('JSON 字符串起点无效');
  let escaped = false;
  for (let cursor = start + 1; cursor < text.length; cursor += 1) {
    const character = text[cursor];
    if (escaped) {
      escaped = false;
    } else if (character === '\\') {
      escaped = true;
    } else if (character === '"') {
      return cursor + 1;
    }
  }
  throw new Error('JSON 字符串未闭合');
}

function scanJsonValueEnd(text, start) {
  const first = text[start];
  if (first === '"') return scanJsonStringEnd(text, start);
  if (first === '{' || first === '[') {
    const stack = [first];
    for (let cursor = start + 1; cursor < text.length; cursor += 1) {
      const character = text[cursor];
      if (character === '"') {
        cursor = scanJsonStringEnd(text, cursor) - 1;
        continue;
      }
      if (character === '{' || character === '[') {
        stack.push(character);
        continue;
      }
      if (character === '}' || character === ']') {
        const opening = stack.pop();
        if ((opening === '{' && character !== '}') || (opening === '[' && character !== ']')) {
          throw new Error('JSON 容器闭合顺序无效');
        }
        if (stack.length === 0) return cursor + 1;
      }
    }
    throw new Error('JSON 容器未闭合');
  }

  let cursor = start;
  while (cursor < text.length && text[cursor] !== ',' && text[cursor] !== '}') cursor += 1;
  let end = cursor;
  while (end > start && /\s/.test(text[end - 1])) end -= 1;
  JSON.parse(text.slice(start, end));
  return end;
}

function alipaySignContent(params) {
  return Object.entries(params)
    .filter(([key, value]) => key !== 'sign' && key !== 'sign_type' && value !== undefined && value !== null && value !== '')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
}

function formatAlipayTimestamp(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
    ' ',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes()),
    ':',
    pad(date.getSeconds()),
  ].join('');
}

function paymentDescription(plan) {
  return String(plan?.label || 'CC中转 充值').slice(0, 120);
}

// 支付网关请求必须有硬超时；超时只中止本次外部请求，不占用本地写队列。
async function fetchPaymentGateway(fetchImpl, url, options, timeoutMs) {
  const controller = new AbortController();
  const timeoutDuration = Number.isFinite(Number(timeoutMs))
    ? Math.max(100, Number(timeoutMs))
    : 15_000;
  let timedOut = false;
  let timer;
  const request = Promise.resolve().then(() => fetchImpl(url, {
    ...options,
    signal: controller.signal,
  }));
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
      reject(publicPaymentError(504, '支付渠道请求超时'));
      }, timeoutDuration);
  });
  try {
    return await Promise.race([request, timeout]);
  } catch (error) {
    if (timedOut) {
      throw publicPaymentError(504, '支付渠道请求超时');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function boolOption(value, envValue) {
  if (typeof value === 'boolean') return value;
  return String(envValue || '') === '1';
}

function assertFetch(fetchImpl) {
  if (typeof fetchImpl !== 'function') {
    throw publicPaymentError(503, '当前 Node 环境不支持支付接口请求');
  }
}

function header(headers, name) {
  if (typeof headers?.get === 'function') {
    return headers.get(name) || '';
  }
  const direct = headers?.[name] ?? headers?.[name.toLowerCase()] ?? headers?.[name.toUpperCase()];
  if (Array.isArray(direct)) return direct[0] || '';
  return direct || '';
}

function parseJson(text) {
  try {
    return JSON.parse(text || '{}');
  } catch {
    return {};
  }
}

function publicPaymentError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.expose = true;
  return error;
}

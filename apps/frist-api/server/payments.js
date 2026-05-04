import { createDecipheriv, createSign, createVerify, randomBytes } from 'node:crypto';

export function normalizePem(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.replace(/\\n/g, '\n');
}

export function paymentConfigFromOptions(options = {}) {
  const publicBaseUrl = String(options.publicGatewayBaseUrl || '').replace(/\/v1\/?$/i, '').replace(/\/+$/, '');
  return {
    enabled: boolOption(options.paymentEnabled, process.env.FRIST_API_PAYMENT_ENABLED),
    publicBaseUrl,
    wechat: {
      enabled: boolOption(options.wechatPayEnabled, process.env.FRIST_API_WECHAT_PAY_ENABLED),
      appid: String(options.wechatPayAppId || process.env.FRIST_API_WECHAT_PAY_APPID || '').trim(),
      mchid: String(options.wechatPayMchId || process.env.FRIST_API_WECHAT_PAY_MCH_ID || '').trim(),
      serialNo: String(options.wechatPaySerialNo || process.env.FRIST_API_WECHAT_PAY_SERIAL_NO || '').trim(),
      privateKey: normalizePem(options.wechatPayPrivateKey || process.env.FRIST_API_WECHAT_PAY_PRIVATE_KEY || ''),
      publicKey: normalizePem(options.wechatPayPublicKey || process.env.FRIST_API_WECHAT_PAY_PUBLIC_KEY || ''),
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
    return Boolean(item.enabled && item.appid && item.mchid && item.serialNo && item.privateKey && item.apiV3Key);
  }
  if (provider === 'alipay') {
    const item = config.alipay || {};
    return Boolean(item.enabled && item.appId && item.privateKey);
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
  const response = await fetchImpl(`${config.gateway}${path}`, {
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
  });
  const text = await response.text();
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
  const response = await fetchImpl(config.gateway, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
    },
    body: new URLSearchParams(params).toString(),
  });
  const text = await response.text();
  const payload = parseJson(text);
  const result = payload.alipay_trade_precreate_response || {};
  if (!response.ok || result.code !== '10000' || !result.qr_code) {
    throw publicPaymentError(502, result.sub_msg || result.msg || `支付宝下单失败: ${response.status}`);
  }
  if (config.publicKey && payload.sign && !verifyAlipayResponse(payload, config.publicKey)) {
    throw publicPaymentError(502, '支付宝下单响应验签失败');
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

export function verifyWechatNotification({ headers, rawBody, paymentConfig }) {
  const config = paymentConfig.wechat || {};
  if (!config.publicKey || !config.apiV3Key) {
    throw publicPaymentError(503, '微信支付回调验签配置未完成');
  }
  const timestamp = String(header(headers, 'wechatpay-timestamp') || '');
  const nonce = String(header(headers, 'wechatpay-nonce') || '');
  const signature = String(header(headers, 'wechatpay-signature') || '');
  if (!timestamp || !nonce || !signature) {
    throw publicPaymentError(400, '微信支付回调缺少签名头');
  }
  const message = `${timestamp}\n${nonce}\n${rawBody}\n`;
  const verified = createVerify('RSA-SHA256').update(message).verify(config.publicKey, signature, 'base64');
  if (!verified) {
    throw publicPaymentError(400, '微信支付回调验签失败');
  }
  const payload = parseJson(rawBody);
  const resource = payload.resource || {};
  const plaintext = decryptWechatResource(resource, config.apiV3Key);
  return parseJson(plaintext);
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
  if (publicKey && !verifyAlipayParams(params, publicKey)) {
    throw publicPaymentError(400, '支付宝回调验签失败');
  }
  return params;
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

function verifyAlipayResponse(payload, publicKey) {
  const methodKey = Object.keys(payload).find((key) => key.endsWith('_response'));
  if (!methodKey) return false;
  const content = JSON.stringify(payload[methodKey]);
  return createVerify('RSA-SHA256').update(content).verify(publicKey, payload.sign, 'base64');
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
  return String(plan?.label || 'Frist-API 充值').slice(0, 120);
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

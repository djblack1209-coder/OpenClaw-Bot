import assert from 'node:assert/strict';
import { createSign, generateKeyPairSync } from 'node:crypto';
import test from 'node:test';

import {
  createProviderPayment,
  parseAlipayNotification,
  paymentConfigFromOptions,
  providerReady,
} from '../server/payments.js';

function rsaPemPair() {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  return {
    privateKey: privateKey.export({ type: 'pkcs8', format: 'pem' }),
    publicKey: publicKey.export({ type: 'spki', format: 'pem' }),
  };
}

test('支付宝缺少平台公钥时渠道必须保持未就绪', () => {
  const incomplete = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: 'private-key',
    alipayPublicKey: '',
  });
  const complete = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: 'private-key',
    alipayPublicKey: 'public-key',
  });

  assert.equal(providerReady(incomplete, 'alipay'), false);
  assert.equal(providerReady(complete, 'alipay'), true);
});

test('微信缺少平台公钥时渠道必须保持未就绪', () => {
  const base = {
    paymentEnabled: true,
    wechatPayEnabled: true,
    wechatPayAppId: 'wx-test-app',
    wechatPayMchId: '1900000001',
    wechatPaySerialNo: 'SERIALNO',
    wechatPayPrivateKey: 'private-key',
    wechatPayPlatformSerialNo: 'PLATFORM-SERIAL',
    wechatPayApiV3Key: '12345678901234567890123456789012',
  };

  assert.equal(providerReady(paymentConfigFromOptions(base), 'wechat'), false);
  assert.equal(
    providerReady(paymentConfigFromOptions({ ...base, wechatPayPublicKey: 'public-key' }), 'wechat'),
    true,
  );
});

test('支付宝回调缺少平台公钥时必须失败关闭', () => {
  const rawBody = new URLSearchParams({
    out_trade_no: 'pay_1',
    trade_no: 'alipay_1',
    trade_status: 'TRADE_SUCCESS',
    total_amount: '5.88',
  }).toString();

  assert.throws(
    () => parseAlipayNotification(rawBody, ''),
    (error) => {
      assert.equal(error.statusCode, 503);
      assert.match(error.message, /支付宝回调验签配置未完成/);
      return true;
    },
  );
});

test('微信下单响应缺少平台签名时必须失败关闭', async () => {
  const keys = rsaPemPair();
  const paymentConfig = paymentConfigFromOptions({
    paymentEnabled: true,
    wechatPayEnabled: true,
    wechatPayAppId: 'wx-test-app',
    wechatPayMchId: '1900000001',
    wechatPaySerialNo: 'MERCHANT-SERIAL',
    wechatPayPrivateKey: keys.privateKey,
    wechatPayPublicKey: keys.publicKey,
    wechatPayPlatformSerialNo: 'PLATFORM-SERIAL',
    wechatPayApiV3Key: '12345678901234567890123456789012',
  });

  await assert.rejects(
    () => createProviderPayment({
      provider: 'wechat',
      order: { id: 'pay_wechat_unsigned', amountCents: 588 },
      plan: { label: '测试日卡' },
      fetchImpl: async () => new Response(JSON.stringify({ code_url: 'weixin://wxpay/test' }), { status: 200 }),
      paymentConfig,
    }),
    (error) => {
      assert.equal(error.statusCode, 502);
      assert.match(error.message, /微信支付下单响应签名/);
      return true;
    },
  );
});

test('支付宝下单响应缺少平台签名时必须失败关闭', async () => {
  const keys = rsaPemPair();
  const paymentConfig = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: keys.privateKey,
    alipayPublicKey: keys.publicKey,
  });

  await assert.rejects(
    () => createProviderPayment({
      provider: 'alipay',
      order: { id: 'pay_alipay_unsigned', amountCents: 588 },
      plan: { label: '测试日卡' },
      fetchImpl: async () => new Response(JSON.stringify({
        alipay_trade_precreate_response: {
          code: '10000',
          qr_code: 'https://qr.alipay.com/test',
        },
      }), { status: 200 }),
      paymentConfig,
    }),
    (error) => {
      assert.equal(error.statusCode, 502);
      assert.match(error.message, /支付宝下单响应签名/);
      return true;
    },
  );
});

test('支付宝下单按平台原始 JSON 子串验签而不重序列化', async () => {
  const keys = rsaPemPair();
  const paymentConfig = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: keys.privateKey,
    alipayPublicKey: keys.publicKey,
  });
  const signedContent = '{"code":"10000", "qr_code":"https:\\/\\/qr.alipay.com\\/signed"}';
  const sign = createSign('RSA-SHA256').update(signedContent).sign(keys.privateKey, 'base64');
  const rawResponse = `{"alipay_trade_precreate_response":${signedContent},"sign":"${sign}"}`;

  const result = await createProviderPayment({
    provider: 'alipay',
    order: { id: 'pay_alipay_signed_raw', amountCents: 588 },
    plan: { label: '测试日卡' },
    fetchImpl: async () => new Response(rawResponse, { status: 200 }),
    paymentConfig,
  });

  assert.equal(result.qrCode, 'https://qr.alipay.com/signed');
});

test('支付宝下单拒绝验签对象与业务对象分离的重复响应键', async () => {
  const keys = rsaPemPair();
  const paymentConfig = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: keys.privateKey,
    alipayPublicKey: keys.publicKey,
  });
  const signedContent = '{"code":"10000","qr_code":"https://qr.alipay.com/signed"}';
  const unsignedContent = '{"code":"10000","qr_code":"https://attacker.invalid/unsigned"}';
  const sign = createSign('RSA-SHA256').update(signedContent).sign(keys.privateKey, 'base64');
  const rawResponse = [
    '{"alipay_trade_precreate_response":',
    signedContent,
    ',"alipay_trade_precreate_response":',
    unsignedContent,
    `,"sign":"${sign}"}`,
  ].join('');

  await assert.rejects(
    () => createProviderPayment({
      provider: 'alipay',
      order: { id: 'pay_alipay_duplicate_key', amountCents: 588 },
      plan: { label: '测试日卡' },
      fetchImpl: async () => new Response(rawResponse, { status: 200 }),
      paymentConfig,
    }),
    /支付宝下单响应签名验签失败/,
  );
});

test('支付渠道请求超过配置时限后必须失败关闭', async () => {
  const keys = rsaPemPair();
  const paymentConfig = paymentConfigFromOptions({
    paymentEnabled: true,
    alipayEnabled: true,
    alipayAppId: '2021000000000000',
    alipayPrivateKey: keys.privateKey,
    alipayPublicKey: keys.publicKey,
    paymentRequestTimeoutMs: 30,
  });
  const result = await Promise.race([
    createProviderPayment({
      provider: 'alipay',
      order: { id: 'pay_alipay_timeout', amountCents: 588 },
      plan: { label: '测试日卡' },
      fetchImpl: async () => new Promise(() => {}),
      paymentConfig,
    }).then(
      () => ({ resolved: true }),
      (error) => ({ error }),
    ),
    new Promise((resolve) => setTimeout(() => resolve({ guardTimedOut: true }), 250)),
  ]);

  assert.equal(result.guardTimedOut, undefined);
  assert.equal(result.error?.statusCode, 504);
  assert.match(result.error?.message || '', /支付渠道请求超时/);
});

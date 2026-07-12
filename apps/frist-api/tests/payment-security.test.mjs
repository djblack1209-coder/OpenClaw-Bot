import assert from 'node:assert/strict';
import { createSign, generateKeyPairSync } from 'node:crypto';
import { describe, it } from 'node:test';

import {
  parseAlipayNotification,
  providerReady,
  signAlipayParams,
  verifyWechatNotification,
} from '../server/payments.js';


describe('CC中转 payment verification boundaries', () => {
  it('does not mark WeChat Pay ready without a platform verification public key', () => {
    const config = {
      enabled: true,
      wechat: {
        enabled: true,
        appid: 'wx-app',
        mchid: 'merchant',
        serialNo: 'serial',
        privateKey: 'merchant-private-key',
        apiV3Key: '12345678901234567890123456789012',
        publicKey: '',
      },
    };

    assert.equal(providerReady(config, 'wechat'), false);
  });

  it('does not mark Alipay ready without its verification public key', () => {
    const config = {
      enabled: true,
      alipay: {
        enabled: true,
        appId: 'alipay-app',
        privateKey: 'merchant-private-key',
        publicKey: '',
      },
    };

    assert.equal(providerReady(config, 'alipay'), false);
  });

  it('rejects unsigned Alipay callbacks when the verification key is missing', () => {
    assert.throws(
      () => parseAlipayNotification('out_trade_no=order-1&trade_status=TRADE_SUCCESS', ''),
      /验签配置未完成/,
    );
  });

  it('rejects signed WeChat callbacks outside the official five-minute window', () => {
    const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    const rawBody = '{}';
    const now = new Date('2026-07-12T12:00:00.000Z');
    const staleTimestamp = String(Math.floor(now.getTime() / 1000) - 301);
    const nonce = 'stale-notify';
    const signature = createSign('RSA-SHA256')
      .update(`${staleTimestamp}\n${nonce}\n${rawBody}\n`)
      .sign(privateKey, 'base64');

    assert.throws(
      () => verifyWechatNotification({
        headers: {
          'wechatpay-timestamp': staleTimestamp,
          'wechatpay-nonce': nonce,
          'wechatpay-signature': signature,
        },
        rawBody,
        now,
        paymentConfig: {
          wechat: {
            publicKey: publicKey.export({ type: 'spki', format: 'pem' }),
            apiV3Key: '12345678901234567890123456789012',
          },
        },
      }),
      /时间戳已过期/,
    );
  });

  it('rejects a valid Alipay signature issued for a different app id', () => {
    const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    const params = {
      app_id: 'attacker-app',
      out_trade_no: 'order-1',
      trade_status: 'TRADE_SUCCESS',
      total_amount: '1.00',
      sign_type: 'RSA2',
    };
    const sign = signAlipayParams(params, privateKey.export({ type: 'pkcs8', format: 'pem' }));
    const rawBody = new URLSearchParams({ ...params, sign }).toString();

    assert.throws(
      () => parseAlipayNotification(
        rawBody,
        publicKey.export({ type: 'spki', format: 'pem' }),
        'expected-app',
      ),
      /应用 ID 不匹配/,
    );
  });
});

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';

import { buildInventorySummary, buildModelCatalog } from '../server/catalog.js';
import { requireUserKey } from '../server/auth.js';
import {
  assertPasswordResetConfirmRateLimit,
  assertRateLimit,
  clientIp,
  createSecurityState,
  parseTrustedProxyIps,
  passwordResetAccountKey,
} from '../server/security.js';
import { isCredentialRouteApproved } from '../server/shared.js';

describe('Frist 安全状态机', () => {
  it('只在 socket 对端可信时从代理链右侧解析客户 IP', () => {
    const trustedProxyIps = parseTrustedProxyIps('127.0.0.1, 10.0.0.2');
    const trustedRequest = {
      socket: { remoteAddress: '::ffff:127.0.0.1' },
      headers: { 'x-forwarded-for': '198.51.100.8, 10.0.0.2' },
    };
    const directRequest = {
      socket: { remoteAddress: '203.0.113.5' },
      headers: { 'x-forwarded-for': '198.51.100.9' },
    };

    assert.equal(clientIp(trustedRequest, { trustedProxyIps }), '198.51.100.8');
    assert.equal(clientIp(directRequest, { trustedProxyIps }), '203.0.113.5');
  });

  it('账号级重置限流使用稳定摘要且不保留邮箱明文', () => {
    const first = passwordResetAccountKey(' Owner@Example.com ', 'unit-secret');
    const second = passwordResetAccountKey('owner@example.com', 'unit-secret');

    assert.equal(first, second);
    assert.equal(first.includes('owner@example.com'), false);

    const state = createSecurityState();
    const options = {
      passwordHashSecret: 'unit-secret',
      passwordResetConfirmRateLimitMax: 1,
      passwordResetConfirmRateLimitWindowMs: 60_000,
      rateLimitMaxEntries: 10,
    };
    assertPasswordResetConfirmRateLimit(state, 'owner@example.com', options);
    assert.throws(
      () => assertPasswordResetConfirmRateLimit(state, 'OWNER@example.com', options),
      (error) => error.statusCode === 429 && error.expose === true,
    );
  });

  it('容量耗尽时拒绝新桶且不淘汰已有封禁', () => {
    const state = createSecurityState();
    assertRateLimit(state, 'existing', 1, 60_000, 2);
    assert.throws(() => assertRateLimit(state, 'existing', 1, 60_000, 2), { statusCode: 429 });
    assertRateLimit(state, 'second', 1, 60_000, 2);
    assert.throws(() => assertRateLimit(state, 'new-client', 1, 60_000, 2), { statusCode: 429 });
    assert.equal(state.rateLimits.has('existing'), true);
  });

  it('加密占位凭据永不进入可路由模型或健康库存', () => {
    const credential = {
      id: 'cred-encrypted',
      sourceId: 'source-encrypted',
      rawKey: 'enc:v1:unreadable-runtime-secret',
      models: ['gpt-5.5'],
      modelGroup: 'OpenAI',
      pool: 'day',
      sourceType: 'authorized',
      riskStatus: 'approved',
      backupRiskAccepted: false,
      enabled: true,
      status: 'healthy',
      quotaRemaining: 1000,
      quotaTotal: 1000,
    };
    const data = {
      credentials: [credential],
      supplierProfiles: [],
      pricing: { modelPrices: [] },
      events: [],
    };

    assert.equal(isCredentialRouteApproved(credential), false);
    assert.equal(buildModelCatalog(data).find((item) => item.model === 'gpt-5.5')?.available, false);
    const inventory = buildInventorySummary(data)[0];
    assert.equal(inventory.healthyKeys, 0);
    assert.equal(inventory.quotaRemaining, 0);
  });

  it('加密占位 API Key 永不通过认证边界', () => {
    const data = {
      userKeys: [{ id: 'key-encrypted', secret: 'enc:v1:runtime-placeholder', enabled: true }],
    };
    const request = {
      headers: { authorization: 'Bearer enc:v1:runtime-placeholder' },
    };

    assert.throws(
      () => requireUserKey(data, request),
      (error) => error.statusCode === 401 && error.expose === true,
    );
  });

  it('入口文件复用统一凭据路由规则，不保留第二份实现', async () => {
    const source = await readFile(new URL('../server/server.js', import.meta.url), 'utf8');

    assert.doesNotMatch(source, /function isCredentialRouteApproved\b/);
  });

  it('认证模块不暴露绕过管理员 2FA 的旧实现', async () => {
    const source = await readFile(new URL('../server/auth.js', import.meta.url), 'utf8');

    assert.doesNotMatch(source, /export function requireAdmin\b/);
    assert.doesNotMatch(source, /export function claimAdminIdentity\b/);
  });

  it('辅助模块不再公开弱化的代理、流式、SLA 与运行时事实源', async () => {
    const sharedSource = await readFile(new URL('../server/shared.js', import.meta.url), 'utf8');
    const catalogSource = await readFile(new URL('../server/catalog.js', import.meta.url), 'utf8');
    const sharedExports = [...sharedSource.matchAll(/export function (\w+)/g)].map((match) => match[1]);
    const catalogExports = [...catalogSource.matchAll(/export function (\w+)/g)].map((match) => match[1]);

    assert.deepEqual(
      sharedExports.filter((name) => [
        'clientIp',
        'requestOrigin',
        'sanitizeUser',
        'pipeReadableStreamToResponse',
        'exhaustCredential',
        'failCredential',
      ].includes(name)),
      [],
    );
    assert.deepEqual(
      catalogExports.filter((name) => ['normalizeUserRecord', 'buildChannelChecks'].includes(name)),
      [],
    );
  });
});

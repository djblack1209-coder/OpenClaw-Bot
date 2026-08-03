import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createCipheriv, createHash, createHmac, createSign, generateKeyPairSync, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { connect } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import { createFristApiServer, resolveSmtpSocketTargets } from '../server/server.js';
import { normalizeClientAvailableModels } from '../src/core.js';

function decodeUrlSafeBase64(value) {
  const raw = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const padded = raw.padEnd(Math.ceil(raw.length / 4) * 4, '=');
  return Buffer.from(padded, 'base64').toString('utf8');
}

function totpCode(secret, date = new Date()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = String(secret || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  let bits = '';
  for (const char of clean) bits += alphabet.indexOf(char).toString(2).padStart(5, '0');
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  const counter = Math.floor(date.getTime() / 1000 / 30);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeUInt32BE(Math.floor(counter / 0x100000000), 0);
  counterBuffer.writeUInt32BE(counter >>> 0, 4);
  const digest = createHmac('sha1', Buffer.from(bytes)).update(counterBuffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % 1_000_000).padStart(6, '0');
}

describe('CC中转 public server chain', () => {
  it('resolves SMTP targets in DNS order so IPv6 can bypass blocked IPv4 exits', async () => {
    const targets = await resolveSmtpSocketTargets({
      host: 'smtp.example.com',
      port: 465,
      family: 'auto',
      addresses: [
        { address: '2001:db8::465', family: 6 },
        { address: '203.0.113.46', family: 4 },
      ],
    });

    assert.deepEqual(
      targets.map((target) => ({ host: target.host, family: target.family, servername: target.servername })),
      [
        { host: '2001:db8::465', family: 6, servername: 'smtp.example.com' },
        { host: '203.0.113.46', family: 4, servername: 'smtp.example.com' },
      ],
    );

    const ipv6Only = await resolveSmtpSocketTargets({
      host: 'smtp.example.com',
      port: 465,
      family: '6',
      addresses: [
        { address: '2001:db8::465', family: 6 },
        { address: '203.0.113.46', family: 4 },
      ],
    });
    assert.deepEqual(ipv6Only.map((target) => target.family), [6]);
  });

  it('serves the customer website from the same lightweight server', async () => {
    const fixture = await createServerFixture();

    try {
      const home = await fixture.request('/');
      assert.equal(home.status, 200);
      assert.match(home.text, /CC中转/);
    } finally {
      await fixture.close();
    }
  });

  it('keeps serving after an origin-form proxy request hits the static error path', async () => {
    const fixture = await createServerFixture();

    try {
      const invalidPath = await sendRawHttpRequest({
        port: fixture.port,
        requestText:
          'GET /%E0%A4%A HTTP/1.1\r\n' +
          'Host: frist-api-oracle.245334.xyz\r\n' +
          'Connection: close\r\n' +
          '\r\n',
      });
      assert.match(invalidPath, /^HTTP\/1\.1 500/m);
      assert.match(invalidPath, /服务暂时不可用/);

      const admin = await sendRawHttpRequest({
        port: fixture.port,
        requestText:
          'GET /admin.html HTTP/1.1\r\n' +
          'Host: frist-api-oracle.245334.xyz\r\n' +
          'Connection: close\r\n' +
          '\r\n',
      });
      assert.match(admin, /^HTTP\/1\.1 200/m);
      assert.match(admin, /CC中转/);
    } finally {
      await fixture.close();
    }
  });

  it('normalizes chained proxy forwarded headers before parsing request URLs', async () => {
    const fixture = await createServerFixture();

    try {
      const dashboard = await sendRawHttpRequest({
        port: fixture.port,
        requestText:
          'GET /api/frist/dashboard HTTP/1.1\r\n' +
          'Host: jiyu.245334.xyz\r\n' +
          'X-Forwarded-Proto: https, http\r\n' +
          'X-Forwarded-Host: jiyu.245334.xyz, internal.local\r\n' +
          'Connection: close\r\n' +
          '\r\n',
      });
      assert.match(dashboard, /^HTTP\/1\.1 200/m);
      assert.match(dashboard, /"authenticated":false/);

      const stillAlive = await fixture.request('/');
      assert.equal(stillAlive.status, 200);
    } finally {
      await fixture.close();
    }
  });

  it('redirects the bare nip host to the single CC中转 branded host', async () => {
    const fixture = await createServerFixture();

    try {
      const redirected = await fixture.request('/api/frist/dashboard?from=bare-host', {
        headers: {
          'x-forwarded-host': '101-43-41-96.nip.io',
        },
        redirect: 'manual',
      });
      assert.equal(redirected.status, 301);
      assert.equal(
        redirected.location,
        'http://jiyu.245334.xyz/api/frist/dashboard?from=bare-host',
      );
      assert.equal(redirected.text, '');

      const canonical = await fixture.request('/', {
        headers: {
          'x-forwarded-host': 'jiyu.245334.xyz',
        },
      });
      assert.equal(canonical.status, 200);
      assert.match(canonical.text, /CC中转/);
    } finally {
      await fixture.close();
    }
  });

  it('returns a quiet guest dashboard before login', async () => {
    const fixture = await createServerFixture();

    try {
      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(dashboard.status, 200);
      assert.equal(dashboard.json.authenticated, false);
      assert.deepEqual(dashboard.json.apiKeys, []);
      assert.equal(dashboard.json.account.monthCost, '$0.00');
      assert.equal(dashboard.json.account.usageTotal, '$0.00');
      assert.deepEqual(dashboard.json.modelUsage, []);
      assert.deepEqual(dashboard.json.channelChecks, []);
      assert.deepEqual(
        dashboard.json.rechargeOptions.map((item) => ({
          id: item.id,
          quotaUsd: item.quotaUsd,
          priceCny: item.priceCny,
          durationDays: item.durationDays,
        })),
        [
          { id: 'xianyu-test-1', quotaUsd: 1, priceCny: 1, durationDays: 0 },
          { id: 'xianyu-5', quotaUsd: 5, priceCny: 5, durationDays: 0 },
          { id: 'xianyu-15', quotaUsd: 15, priceCny: 15, durationDays: 0 },
          { id: 'xianyu-50', quotaUsd: 50, priceCny: 50, durationDays: 0 },
          { id: 'xianyu-100', quotaUsd: 100, priceCny: 100, durationDays: 0 },
          { id: 'xianyu-500', quotaUsd: 500, priceCny: 500, durationDays: 0 },
        ],
      );
    } finally {
      await fixture.close();
    }
  });

  it('marks captcha challenges as required only when the server enables captcha', async () => {
    const relaxed = await createServerFixture({ requireCaptcha: false });
    const strict = await createServerFixture({ requireCaptcha: true });

    try {
      const relaxedChallenge = await relaxed.request('/api/frist/challenge');
      const strictChallenge = await strict.request('/api/frist/challenge');

      assert.equal(relaxedChallenge.status, 200);
      assert.equal(relaxedChallenge.json.required, false);
      assert.equal(strictChallenge.status, 200);
      assert.equal(strictChallenge.json.required, true);
    } finally {
      await relaxed.close();
      await strict.close();
    }
  });

  it('requires verified Turnstile tokens for register, login and redeem when enabled', async () => {
    const turnstileCalls = [];
    const fixture = await createServerFixture({
      requireTurnstile: true,
      turnstileSecret: 'turnstile-secret-for-tests',
      turnstileAllowedHostnames: ['jiyu.245334.xyz'],
      fetchImpl: async (url, options = {}) => {
        if (String(url) === 'https://challenges.cloudflare.com/turnstile/v0/siteverify') {
          const params = new URLSearchParams(String(options.body || ''));
          turnstileCalls.push({
            url: String(url),
            method: options.method,
            secret: params.get('secret'),
            response: params.get('response'),
          });
          const action = String(params.get('response') || '').split(':')[0];
          return jsonResponse(200, {
            success: true,
            hostname: 'jiyu.245334.xyz',
            action,
          });
        }
        return jsonResponse(200, { ok: true });
      },
    });

    try {
      const blockedRegister = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'turnstile@example.com', password: 'TestPass123!' },
      });
      assert.equal(blockedRegister.status, 400);
      assert.match(blockedRegister.json.error, /人机验证/);

      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'turnstile@example.com', password: 'TestPass123!', turnstileToken: 'register:ok' },
      });
      assert.equal(registered.status, 200);

      const blockedLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'turnstile@example.com', password: 'TestPass123!' },
      });
      assert.equal(blockedLogin.status, 400);
      assert.match(blockedLogin.json.error, /人机验证/);

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'turnstile@example.com', password: 'TestPass123!', turnstileToken: 'login:ok' },
      });
      assert.equal(loggedIn.status, 200);

      const blockedRedeem = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      assert.equal(blockedRedeem.status, 400);
      assert.match(blockedRedeem.json.error, /人机验证/);

      const redeemed = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: 'JIYU-DAY-001', turnstileToken: 'redeem:ok' },
      });
      assert.equal(redeemed.status, 200);
      assert.equal(redeemed.json.account.balance, '$1.11');

      assert.deepEqual(
        turnstileCalls.map((call) => ({
          url: call.url,
          method: call.method,
          secret: call.secret,
          response: call.response,
        })),
        [
          {
            url: 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            method: 'POST',
            secret: 'turnstile-secret-for-tests',
            response: 'register:ok',
          },
          {
            url: 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            method: 'POST',
            secret: 'turnstile-secret-for-tests',
            response: 'login:ok',
          },
          {
            url: 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            method: 'POST',
            secret: 'turnstile-secret-for-tests',
            response: 'redeem:ok',
          },
        ],
      );
    } finally {
      await fixture.close();
    }
  });

  it('rejects Turnstile failures, action mismatches and unexpected hostnames', async () => {
    const responses = [
      { success: false, 'error-codes': ['timeout-or-duplicate'] },
      { success: true, hostname: 'jiyu.245334.xyz', action: 'login' },
      { success: true, hostname: 'evil.example.com', action: 'register' },
    ];
    const fixture = await createServerFixture({
      requireTurnstile: true,
      turnstileSecret: 'turnstile-secret-for-tests',
      turnstileAllowedHostnames: ['jiyu.245334.xyz'],
      fetchImpl: async (url) => {
        assert.equal(String(url), 'https://challenges.cloudflare.com/turnstile/v0/siteverify');
        return jsonResponse(200, responses.shift());
      },
    });

    try {
      const failed = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'bad-turnstile@example.com', password: 'TestPass123!', turnstileToken: 'register:bad' },
      });
      assert.equal(failed.status, 403);
      assert.match(failed.json.error, /验证失败|刷新/);

      const actionMismatch = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'bad-action@example.com', password: 'TestPass123!', turnstileToken: 'register:wrong-action' },
      });
      assert.equal(actionMismatch.status, 403);
      assert.match(actionMismatch.json.error, /刷新/);

      const hostnameMismatch = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'bad-host@example.com', password: 'TestPass123!', turnstileToken: 'register:wrong-host' },
      });
      assert.equal(hostnameMismatch.status, 403);
      assert.match(hostnameMismatch.json.error, /刷新/);
    } finally {
      await fixture.close();
    }
  });

  it('lets admins update recharge packages and custom model prices without changing code', async () => {
    const fixture = await createServerFixture();

    try {
      const pricing = await fixture.request('/api/admin/pricing', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(pricing.status, 200);
      assert.equal(pricing.json.rechargePlans.length, 6);
      assert.equal(pricing.json.modelPrices.find((item) => item.model === 'gpt-5.5').source, 'official');

      const updated = await fixture.request('/api/admin/pricing', {
        method: 'PUT',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          rechargePlans: [
            { id: 'xianyu-test-1', label: 'CC中转 1元测试档', quotaUsd: 1, priceCny: 1.11, durationDays: 0 },
            { id: 'xianyu-5', label: 'CC中转 5元档', quotaUsd: 5, priceCny: 5, durationDays: 0 },
            { id: 'xianyu-15', label: 'CC中转 15元档', quotaUsd: 15, priceCny: 15, durationDays: 0 },
            { id: 'xianyu-50', label: 'CC中转 50元档', quotaUsd: 50, priceCny: 50, durationDays: 0 },
            { id: 'xianyu-100', label: 'CC中转 100元档', quotaUsd: 100, priceCny: 100, durationDays: 0 },
            { id: 'xianyu-500', label: 'CC中转 500元档', quotaUsd: 500, priceCny: 500, durationDays: 0 },
          ],
          modelPrices: [
            {
              model: 'gpt-5.5',
              currency: 'CNY',
              inputCostCnyPerMillion: 9,
              outputCostCnyPerMillion: 49,
              inputSaleCnyPerMillion: 9,
              outputSaleCnyPerMillion: 49,
              source: 'custom',
            },
          ],
        },
      });
      assert.equal(updated.status, 200);
      assert.equal(updated.json.rechargePlans[0].priceCny, 1.11);

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-pricing-visible', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(dashboard.json.rechargeOptions[0].priceCny, 1.11);
      assert.equal(dashboard.json.rechargeOptions[0].cny, '¥1.11');
      assert.equal(dashboard.json.modelCatalog.find((item) => item.model === 'gpt-5.5').price, '$1.250/$6.806 每 1M');
    } finally {
      await fixture.close();
    }
  });

  it('migrates stale official model prices to full official pricing labels', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.writeData({
        pricing: {
          modelPrices: [
            {
              model: 'gpt-5.5',
              currency: 'CNY',
              inputCostCnyPerMillion: 8,
              outputCostCnyPerMillion: 48,
              inputSaleCnyPerMillion: 8,
              outputSaleCnyPerMillion: 48,
              source: 'official',
              displayPrice: '',
              status: 'confirmed',
            },
          ],
        },
        priceDrafts: [],
      });

      const pricing = await fixture.request('/api/admin/pricing', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      const officialGpt = pricing.json.modelPrices.find((item) => item.model === 'gpt-5.5');
      assert.equal(officialGpt.inputSaleCnyPerMillion, 36);
      assert.equal(officialGpt.outputSaleCnyPerMillion, 216);
      assert.equal(officialGpt.displayPrice, '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M');

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-official-price-visible', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(
        dashboard.json.modelCatalog.find((item) => item.model === 'gpt-5.5').price,
        '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M',
      );
    } finally {
      await fixture.close();
    }
  });

  it('runs register, verify, recharge, create key and import URL through HTTP APIs', async () => {
    const fixture = await createServerFixture({ allowDemoRecharge: true, requireEmailVerification: true });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'customer@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);
      assert.equal(registered.json.verificationCode.length, 6);

      const cookie = registered.cookie;
      const verified = await fixture.request('/api/frist/verify', {
        method: 'POST',
        cookie,
        body: { code: registered.json.verificationCode },
      });
      assert.equal(verified.status, 200);
      assert.equal(verified.json.user.emailVerified, true);

      const recharged = await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { amountCny: 8, method: 'manual_demo' },
      });
      assert.equal(recharged.status, 200);
      assert.equal(recharged.json.account.balance, '$1.11');

      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Claude 日常 Key', modelGroup: 'Claude' },
      });
      assert.equal(token.status, 200);
      assert.match(token.json.key.secret, /^fk-live-/);
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/claude',
          pool: 'default',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-customer-flow-claude', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const imported = await fixture.request('/api/frist/import-url?target=Claude&model=claude-sonnet-4-5-c', {
        cookie,
      });
      assert.equal(imported.status, 200);
      assert.match(decodeURIComponent(imported.json.url), new RegExp(token.json.key.secret));
      const importUrl = new URL(imported.json.url);
      assert.equal(importUrl.searchParams.get('app'), 'claude');
      assert.equal(importUrl.searchParams.get('usageEnabled'), 'true');
      assert.equal(importUrl.searchParams.get('usageApiKey'), token.json.key.secret);
      assert.equal(importUrl.searchParams.get('usageBaseUrl'), fixture.baseUrl);
      assert.match(decodeUrlSafeBase64(importUrl.searchParams.get('usageScript')), /\/api\/frist\/key-usage/);
      assert.equal(imported.json.config.targetSlug, 'claude');
      assert.equal(imported.json.config.authField, 'ANTHROPIC_AUTH_TOKEN');
      assert.equal(JSON.parse(imported.json.config.authJson).env.ANTHROPIC_AUTH_TOKEN, token.json.key.secret);
      assert.equal(imported.json.config.usageBaseUrl, fixture.baseUrl);
      assert.match(imported.json.config.usageScript, /\/api\/frist\/key-usage/);
      assert.match(imported.json.setup.test, /claude --bare --no-session-persistence/);
      assert.match(imported.json.setup.test, /--settings "\$tmp_settings"/);
      assert.doesNotMatch(JSON.stringify(imported.json), /supplier-codex\.example\.com|cr_fake_supplier_secret/);

      const disabled = await fixture.request(`/api/frist/token/${token.json.key.id}`, {
        method: 'PATCH',
        cookie,
        body: { enabled: false },
      });
      assert.equal(disabled.status, 200);

      const blockedImport = await fixture.request('/api/frist/import-url?target=Claude&model=claude-haiku', {
        cookie,
      });
      assert.equal(blockedImport.status, 409);
    } finally {
      await fixture.close();
    }
  });

  it('lets public beta customers create a key after login without blocking on unreachable email delivery', async () => {
    const fixture = await createServerFixture({ allowDemoRecharge: true, requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'public-beta@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);
      assert.equal(registered.json.user.emailVerified, true);
      assert.equal(registered.json.verificationCode, undefined);

      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: '公开测试 Key' },
      });
      assert.equal(token.status, 200);
      assert.match(token.json.key.secret, /^fk-live-/);
    } finally {
      await fixture.close();
    }
  });

  it('sends registration email codes and supports password reset without requiring login', async () => {
    const sentEmails = [];
    const fixture = await createServerFixture({
      requireEmailVerification: true,
      accountEmailSender: (message) => sentEmails.push(message),
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'mail-verify@example.com', password: 'OldPass123!' },
      });
      assert.equal(registered.status, 200);
      assert.equal(sentEmails.length, 1);
      assert.equal(sentEmails[0].to, 'mail-verify@example.com');
      assert.match(sentEmails[0].subject, /注册验证码/);
      assert.match(sentEmails[0].text, new RegExp(registered.json.verificationCode));
      assert.match(sentEmails[0].html, /mail-shell|brand-card|security-badge/);
      assert.match(sentEmails[0].html, /font-size:\s*4[0-9]px/);
      assert.match(sentEmails[0].html, /如果不是你本人操作/);

      const resetRequested = await fixture.request('/api/frist/password-reset/request', {
        method: 'POST',
        body: { email: 'mail-verify@example.com' },
      });
      assert.equal(resetRequested.status, 200);
      assert.equal(sentEmails.length, 2);
      assert.match(sentEmails[1].subject, /密码重置验证码/);
      assert.match(sentEmails[1].text, new RegExp(resetRequested.json.resetCode));
      assert.match(sentEmails[1].html, /mail-shell|brand-card|security-badge/);
      assert.match(sentEmails[1].html, /如果不是你本人操作/);

      const resetConfirmed = await fixture.request('/api/frist/password-reset/confirm', {
        method: 'POST',
        body: { email: 'mail-verify@example.com', code: resetRequested.json.resetCode, newPassword: 'NewPass123!' },
      });
      assert.equal(resetConfirmed.status, 200);

      const oldLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'mail-verify@example.com', password: 'OldPass123!' },
      });
      assert.equal(oldLogin.status, 401);

      const newLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'mail-verify@example.com', password: 'NewPass123!' },
      });
      assert.equal(newLogin.status, 200);
    } finally {
      await fixture.close();
    }
  });

  it('lets customers rename and delete their own API keys through HTTP APIs', async () => {
    const fixture = await createServerFixture({ requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'keys-owner@example.com', password: 'TestPass123!' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: '临时 Key' },
      });
      assert.match(token.json.key.secret, /^fk-live-/);

      const renamed = await fixture.request(`/api/frist/token/${token.json.key.id}`, {
        method: 'PATCH',
        cookie: registered.cookie,
        body: { name: 'OpenCode 主力 Key' },
      });
      assert.equal(renamed.status, 200);
      assert.equal(renamed.json.key.name, 'OpenCode 主力 Key');
      assert.equal(renamed.json.key.enabled, true);

      const dashboardAfterRename = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });
      assert.equal(dashboardAfterRename.json.apiKeys[0].name, 'OpenCode 主力 Key');
      assert.equal(Object.prototype.hasOwnProperty.call(dashboardAfterRename.json.apiKeys[0], 'secret'), false);

      const deleted = await fixture.request(`/api/frist/token/${token.json.key.id}`, {
        method: 'DELETE',
        cookie: registered.cookie,
      });
      assert.equal(deleted.status, 200);
      assert.equal(deleted.json.deletedKeyId, token.json.key.id);

      const dashboardAfterDelete = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });
      assert.deepEqual(dashboardAfterDelete.json.apiKeys, []);
    } finally {
      await fixture.close();
    }
  });

  it('creates a pending recharge order by default instead of crediting public balance for free', async () => {
    const fixture = await createServerFixture();

    try {
      const cookie = await fixture.createVerifiedCustomer('pending-pay@example.com');
      const pending = await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { amountCny: 8, method: 'web_checkout' },
      });
      assert.equal(pending.status, 202);
      assert.equal(pending.json.paymentOrder.status, 'pending_manual_payment');
      assert.equal(pending.json.account.balance, '$0.00');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.balance, '$0.00');
    } finally {
      await fixture.close();
    }
  });

  it('lets admins confirm a manual recharge after the user creates an offline payment order', async () => {
    const fixture = await createServerFixture();

    try {
      const cookie = await fixture.createVerifiedCustomer('manual-credit@example.com');
      await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { amountCny: 8, method: 'web_checkout' },
      });

      const credited = await fixture.request('/api/admin/customers/recharge', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { email: 'manual-credit@example.com', amountCny: 8, method: 'manual_confirmed' },
      });
      assert.equal(credited.status, 200);
      assert.equal(credited.json.account.balance, '$1.11');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.boosterQuota, '$1.11');
    } finally {
      await fixture.close();
    }
  });

  it('creates WeChat native payment orders and credits exactly once after signed notify', async () => {
    const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    const wechatPrivateKey = privateKey.export({ type: 'pkcs8', format: 'pem' });
    const wechatPublicKey = publicKey.export({ type: 'spki', format: 'pem' });
    const apiV3Key = '12345678901234567890123456789012';
    const fixture = await createServerFixture({
      paymentEnabled: true,
      wechatPayEnabled: true,
      wechatPayAppId: 'wx-test-app',
      wechatPayMchId: '1900000001',
      wechatPaySerialNo: 'SERIALNO',
      wechatPayPrivateKey: wechatPrivateKey,
      wechatPayPublicKey: wechatPublicKey,
      wechatPayApiV3Key: apiV3Key,
      fetchImpl: async (url) => {
        assert.equal(String(url), 'https://api.mch.weixin.qq.com/v3/pay/transactions/native');
        return jsonResponse(200, { code_url: 'weixin://wxpay/bizpayurl?pr=test' });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('wechat-paid@example.com');
      const created = await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { planId: 'codex-30-unlimited', method: 'wechat_native' },
      });
      assert.equal(created.status, 202);
      assert.equal(created.json.provider, 'wechat');
      assert.equal(created.json.qrCode, 'weixin://wxpay/bizpayurl?pr=test');
      assert.equal(created.json.paymentOrder.status, 'pending_provider_payment');

      const notifyBody = buildWechatNotifyBody({
        apiV3Key,
        transaction: {
          out_trade_no: created.json.paymentOrder.id,
          transaction_id: 'wx-transaction-1',
          trade_state: 'SUCCESS',
          amount: { total: 888, payer_total: 888 },
        },
      });
      const notify = await fixture.rawRequest('/api/frist/payments/wechat/notify', {
        method: 'POST',
        headers: signWechatNotifyHeaders({
          privateKey: wechatPrivateKey,
          bodyText: notifyBody,
        }),
        bodyText: notifyBody,
      });
      assert.equal(notify.status, 200);
      assert.equal(notify.json.code, 'SUCCESS');

      const duplicate = await fixture.rawRequest('/api/frist/payments/wechat/notify', {
        method: 'POST',
        headers: signWechatNotifyHeaders({
          privateKey: wechatPrivateKey,
          bodyText: notifyBody,
        }),
        bodyText: notifyBody,
      });
      assert.equal(duplicate.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.boosterQuota, '$30.00');
      assert.equal(dashboard.json.account.balance, '$30.00');
      const data = await fixture.readData();
      assert.equal(data.paymentOrders[0].status, 'paid');
      assert.equal(data.events.filter((event) => event.type === 'provider_payment_confirmed').length, 1);
    } finally {
      await fixture.close();
    }
  });

  it('rejects provider payment callbacks when the paid amount is lower than the order amount', async () => {
    const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    const alipayPrivateKey = privateKey.export({ type: 'pkcs8', format: 'pem' });
    const alipayPublicKey = publicKey.export({ type: 'spki', format: 'pem' });
    const fixture = await createServerFixture({
      paymentEnabled: true,
      alipayEnabled: true,
      alipayAppId: '2021000000000000',
      alipayPrivateKey,
      alipayPublicKey,
      fetchImpl: async () =>
        jsonResponse(200, {
          alipay_trade_precreate_response: {
            code: '10000',
            msg: 'Success',
            out_trade_no: 'server-generated',
            qr_code: 'https://qr.alipay.com/test',
          },
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('alipay-underpaid@example.com');
      const created = await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { planId: 'codex-30-unlimited', method: 'alipay_precreate' },
      });
      assert.equal(created.status, 202);
      assert.equal(created.json.paymentOrder.amount, '¥8.88');

      const notifyBody = signAlipayNotifyBody(
        {
          app_id: '2021000000000000',
          out_trade_no: created.json.paymentOrder.id,
          trade_no: 'ali-underpaid-1',
          trade_status: 'TRADE_SUCCESS',
          total_amount: '5.88',
        },
        alipayPrivateKey,
      );
      const notify = await fixture.rawRequest('/api/frist/payments/alipay/notify', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        bodyText: notifyBody,
      });
      assert.equal(notify.status, 400);
      assert.match(notify.text, /支付金额与订单金额不一致/);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.balance, '$0.00');
      const data = await fixture.readData();
      assert.equal(data.paymentOrders[0].status, 'pending_provider_payment');
      assert.equal(data.events.filter((event) => event.type === 'provider_payment_confirmed').length, 0);
    } finally {
      await fixture.close();
    }
  });

  it('creates Alipay precreate orders and credits customer after verified notify', async () => {
    const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    const alipayPrivateKey = privateKey.export({ type: 'pkcs8', format: 'pem' });
    const alipayPublicKey = publicKey.export({ type: 'spki', format: 'pem' });
    const fixture = await createServerFixture({
      paymentEnabled: true,
      alipayEnabled: true,
      alipayAppId: '2021000000000000',
      alipayPrivateKey,
      alipayPublicKey,
      fetchImpl: async (url, options = {}) => {
        assert.equal(String(url), 'https://openapi.alipay.com/gateway.do');
        assert.match(String(options.body || ''), /alipay.trade.precreate/);
        return jsonResponse(200, {
          alipay_trade_precreate_response: {
            code: '10000',
            msg: 'Success',
            out_trade_no: 'server-generated',
            qr_code: 'https://qr.alipay.com/test',
          },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('alipay-paid@example.com');
      const created = await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { planId: 'codex-30-day', method: 'alipay_precreate' },
      });
      assert.equal(created.status, 202);
      assert.equal(created.json.provider, 'alipay');
      assert.equal(created.json.paymentOrder.status, 'pending_provider_payment');
      assert.equal(created.json.qrCode, 'https://qr.alipay.com/test');

      const notifyBody = signAlipayNotifyBody(
        {
          app_id: '2021000000000000',
          out_trade_no: created.json.paymentOrder.id,
          trade_no: 'ali-trade-1',
          trade_status: 'TRADE_SUCCESS',
          total_amount: '5.88',
        },
        alipayPrivateKey,
      );
      const notify = await fixture.rawRequest('/api/frist/payments/alipay/notify', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        bodyText: notifyBody,
      });
      assert.equal(notify.status, 200);
      assert.equal(notify.text, 'success');

      const duplicate = await fixture.rawRequest('/api/frist/payments/alipay/notify', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        bodyText: notifyBody,
      });
      assert.equal(duplicate.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.plan, '日卡');
      assert.equal(dashboard.json.account.packageQuota, '$30.00');
      const data = await fixture.readData();
      assert.equal(data.paymentOrders[0].status, 'paid');
      assert.equal(data.events.filter((event) => event.type === 'provider_payment_confirmed').length, 1);
    } finally {
      await fixture.close();
    }
  });

  it('lets admins mark a paid customer as day-card so balance routes to day inventory', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
        });
        return jsonResponse(200, {
          id: 'chatcmpl-day-paid',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('paid-day@example.com');
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '日卡客户 Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-paid-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const credited = await fixture.request('/api/admin/customers/recharge', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { email: 'paid-day@example.com', amountCny: 8, plan: 'day', method: 'manual_confirmed' },
      });
      assert.equal(credited.status, 200);
      assert.equal(credited.json.account.plan, '日卡');
      assert.equal(credited.json.account.packageQuota, '$1.11');

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'ping' }] },
      });
      assert.equal(gateway.status, 200);
      assert.equal(upstreamCalls.at(-1).authorization, 'Bearer sk-paid-day');
    } finally {
      await fixture.close();
    }
  });

  it('lets returning customers log in without re-registering the account', async () => {
    const fixture = await createServerFixture();

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'returning@example.com', password: 'TestPass123!' },
      });
      await fixture.request('/api/frist/verify', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: registered.json.verificationCode },
      });

      const duplicate = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'returning@example.com', password: 'TestPass123!' },
      });
      assert.equal(duplicate.status, 409);

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'returning@example.com', password: 'TestPass123!' },
      });
      assert.equal(loggedIn.status, 200);
      assert.equal(loggedIn.json.user.email, 'returning@example.com');

      const dashboard = await fixture.request('/api/frist/dashboard', {
        cookie: loggedIn.cookie,
      });
      assert.equal(dashboard.json.authenticated, true);
    } finally {
      await fixture.close();
    }
  });

  it('stores new passwords with a slow hash and upgrades legacy hashes on login', async () => {
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      passwordHashSecret: 'password-hash-secret-with-enough-randomness-2026',
      legacyPasswordHashSecrets: ['session-secret-with-enough-randomness-2026'],
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'hash-upgrade@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);

      let data = await fixture.readData();
      const user = data.users.find((item) => item.email === 'hash-upgrade@example.com');
      assert.match(user.passwordHash, /^pbkdf2-sha256\$210000\$/);
      assert.equal(user.passwordHash.includes('TestPass123!'), false);

      user.passwordHash = legacyPasswordHash('LegacyPass123!', 'session-secret-with-enough-randomness-2026');
      await fixture.writeData(data);

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'hash-upgrade@example.com', password: 'LegacyPass123!' },
      });
      assert.equal(loggedIn.status, 200);

      data = await fixture.readData();
      const upgraded = data.users.find((item) => item.email === 'hash-upgrade@example.com');
      assert.match(upgraded.passwordHash, /^pbkdf2-sha256\$210000\$/);
      assert.equal(upgraded.passwordHash.includes('LegacyPass123!'), false);
      assert.equal(data.events.some((event) => event.type === 'password_hash_upgraded'), true);
    } finally {
      await fixture.close();
    }
  });

  it('keeps old customer passwords valid after rotating the session secret', async () => {
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      sessionSecret: 'new-session-secret-with-enough-randomness-2026',
      passwordHashSecret: 'new-password-hash-secret-with-enough-randomness-2026',
      legacyPasswordHashSecrets: ['old-session-secret-with-enough-randomness-2026'],
    });

    try {
      const legacyHash = legacyPasswordHash('StillWorks123!', 'old-session-secret-with-enough-randomness-2026');
      await fixture.writeData({
        users: [
          {
            id: 'user-legacy-session',
            email: 'legacy-session@example.com',
            displayName: 'legacy-session',
            emailVerified: true,
            isAdmin: false,
            plan: '默认套餐',
            renewalDate: '2026-06-07',
            balanceCents: 0,
            packageQuotaCents: 0,
            boosterQuotaCents: 0,
            passwordHash: legacyHash,
            createdAt: '2026-05-08T00:00:00.000Z',
            updatedAt: '2026-05-08T00:00:00.000Z',
          },
        ],
      });

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'legacy-session@example.com', password: 'StillWorks123!' },
      });
      assert.equal(loggedIn.status, 200);

      const data = await fixture.readData();
      const upgraded = data.users.find((item) => item.email === 'legacy-session@example.com');
      assert.match(upgraded.passwordHash, /^pbkdf2-sha256\$210000\$/);
      assert.notEqual(upgraded.passwordHash, legacyHash);
      assert.equal(data.events.some((event) => event.type === 'password_hash_upgraded'), true);
    } finally {
      await fixture.close();
    }
  });

  it('encrypts runtime API secrets on disk while keeping gateway reads compatible', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      dataEncryptionKey: 'local-runtime-encryption-key-for-tests',
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
        });
        return jsonResponse(200, {
          id: 'chatcmpl-encrypted-runtime',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'encrypted ok' } }],
        });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'encrypted-runtime@example.com', password: 'TestPass123!' },
      });
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Encrypted Runtime Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-encrypted-upstream', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const raw = await fixture.readRawData();
      assert.equal(raw.includes(token.json.key.secret), false);
      assert.equal(raw.includes('sk-encrypted-upstream'), false);
      assert.match(raw, /enc:v1:/);

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'ping' }] },
      });
      assert.equal(gateway.status, 200);
      assert.equal(upstreamCalls.at(-1).authorization, 'Bearer sk-encrypted-upstream');
    } finally {
      await fixture.close();
    }
  });

  it('quarantines legacy orphan encrypted runtime fields when a new data encryption key is configured', async () => {
    const fixture = await createServerFixture({
      dataEncryptionKey: 'new-runtime-encryption-key-after-orphan-fields',
    });

    try {
      await fixture.writeData({
        credentials: [
          {
            id: 'cred-orphan-encrypted',
            rawKey: 'enc:v1:old:missing:key',
            keyPreview: '',
            enabled: true,
            status: 'healthy',
            riskStatus: 'approved',
            sourceType: 'authorized',
            baseUrl: 'https://supplier.example.com/v1',
            models: ['gpt-5.5'],
          },
        ],
        userKeys: [
          {
            id: 'key-orphan-encrypted',
            userId: 'user-orphan',
            name: '历史 Key',
            secret: 'enc:v1:old:missing:userkey',
            enabled: true,
          },
        ],
      });

      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(dashboard.status, 200);

      const admin = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(admin.status, 200);
      assert.equal(admin.json.credentials[0].enabled, false);
      assert.equal(admin.json.credentials[0].requiresRotation, true);
      assert.equal(admin.json.credentials[0].keyPreview, '需重新生成');
    } finally {
      await fixture.close();
    }
  });

  it('quarantines marked encrypted runtime fields when the old data key is unavailable', async () => {
    const oldFixture = await createServerFixture({
      requireEmailVerification: false,
      dataEncryptionKey: 'old-runtime-encryption-key-that-is-not-available',
    });
    let markedEncryptedRuntime = '';

    try {
      const registered = await oldFixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'marked-orphan@example.com', password: 'TestPass123!' },
      });
      const token = await oldFixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Marked Orphan Key', modelGroup: 'OpenAI' },
      });
      await oldFixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-marked-orphan-upstream', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      markedEncryptedRuntime = await oldFixture.readRawData();
      assert.match(markedEncryptedRuntime, /"__encryption"/);
      assert.equal(markedEncryptedRuntime.includes(token.json.key.secret), false);
      assert.equal(markedEncryptedRuntime.includes('sk-marked-orphan-upstream'), false);
    } finally {
      await oldFixture.close();
    }

    const newFixture = await createServerFixture({
      dataEncryptionKey: 'new-runtime-encryption-key-after-marked-orphan-fields',
    });

    try {
      await writeFile(newFixture.dataFile, markedEncryptedRuntime, 'utf8');

      const dashboard = await newFixture.request('/api/frist/dashboard');
      assert.equal(dashboard.status, 200);

      const admin = await newFixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(admin.status, 200);
      assert.equal(admin.json.credentials[0].enabled, false);
      assert.equal(admin.json.credentials[0].requiresRotation, true);
      assert.equal(admin.json.credentials[0].keyPreview, '需重新生成');
      assert.equal(admin.json.productionReadiness.ready, false);
    } finally {
      await newFixture.close();
    }
  });

  it('adds Secure to session cookies when the public gateway is HTTPS', async () => {
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      publicGatewayBaseUrl: 'https://gateway.frist-api.example/v1',
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'secure-cookie@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);
      assert.match(registered.setCookie, /HttpOnly/);
      assert.match(registered.setCookie, /SameSite=Lax/);
      assert.match(registered.setCookie, /Secure/);

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'secure-cookie@example.com', password: 'TestPass123!' },
      });
      assert.equal(loggedIn.status, 200);
      assert.match(loggedIn.setCookie, /Secure/);
    } finally {
      await fixture.close();
    }
  });

  it('requires CSRF tokens for cookie-authenticated mutations when enabled', async () => {
    const fixture = await createServerFixture({ requireCsrf: true, requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'csrf@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);
      assert.match(registered.setCookie, /frist_csrf=/);
      const csrfToken = registered.json.csrfToken;

      const reloaded = await fixture.request('/api/frist/dashboard', {
        cookie: registered.cookie,
      });
      assert.equal(reloaded.status, 200);
      assert.equal(reloaded.json.csrfToken, csrfToken);

      const blocked = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Blocked Key' },
      });
      assert.equal(blocked.status, 403);

      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        headers: { 'x-csrf-token': csrfToken },
        body: { name: 'Allowed Key' },
      });
      assert.equal(created.status, 200);
      assert.match(created.json.key.secret, /^fk-live-/);
    } finally {
      await fixture.close();
    }
  });

  it('logs customers out by revoking the server session and expiring both cookies', async () => {
    const fixture = await createServerFixture({ requireCsrf: true, requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'logout@example.com', password: 'TestPass123!' },
      });
      const csrfToken = registered.json.csrfToken;

      const blocked = await fixture.request('/api/frist/logout', {
        method: 'POST',
        cookie: registered.cookie,
      });
      assert.equal(blocked.status, 403);

      const loggedOut = await fixture.request('/api/frist/logout', {
        method: 'POST',
        cookie: registered.cookie,
        headers: { 'x-csrf-token': csrfToken },
      });
      assert.equal(loggedOut.status, 200);
      assert.match(loggedOut.setCookie, /frist_session=.*Max-Age=0/);
      assert.match(loggedOut.setCookie, /frist_csrf=.*Max-Age=0/);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });
      assert.equal(dashboard.json.authenticated, false);
    } finally {
      await fixture.close();
    }
  });

  it('lets logged-in customers change password before using the same account again', async () => {
    const fixture = await createServerFixture();

    try {
      const cookie = await fixture.createVerifiedCustomer('change-password@example.com');
      const changed = await fixture.request('/api/frist/password', {
        method: 'POST',
        cookie,
        body: { oldPassword: 'TestPass123!', newPassword: 'NewPass123!' },
      });
      assert.equal(changed.status, 200);
      assert.equal(changed.json.user.email, 'change-password@example.com');

      const revokedSession = await fixture.request('/api/frist/dashboard', { cookie });
      const rotatedSession = await fixture.request('/api/frist/dashboard', { cookie: changed.cookie });
      assert.equal(revokedSession.json.authenticated, false);
      assert.equal(rotatedSession.json.authenticated, true);

      const oldLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'change-password@example.com', password: 'TestPass123!' },
      });
      assert.equal(oldLogin.status, 401);

      const newLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'change-password@example.com', password: 'NewPass123!' },
      });
      assert.equal(newLogin.status, 200);
    } finally {
      await fixture.close();
    }
  });

  it('lets admins recover a customer account when email reset delivery is unavailable', async () => {
    const fixture = await createServerFixture();

    try {
      const oldCookie = await fixture.createVerifiedCustomer('admin-reset@example.com');
      const reset = await fixture.request('/api/admin/customers/password', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { email: 'admin-reset@example.com', password: 'RecoveredPass123!' },
      });
      assert.equal(reset.status, 200);
      assert.equal(reset.json.user.email, 'admin-reset@example.com');
      assert.equal(reset.text.includes('RecoveredPass123!'), false);

      const revokedSession = await fixture.request('/api/frist/dashboard', { cookie: oldCookie });
      assert.equal(revokedSession.json.authenticated, false);

      const oldLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'admin-reset@example.com', password: 'TestPass123!' },
      });
      assert.equal(oldLogin.status, 401);

      const newLogin = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'admin-reset@example.com', password: 'RecoveredPass123!' },
      });
      assert.equal(newLogin.status, 200);

      const data = await fixture.readData();
      const user = data.users.find((item) => item.email === 'admin-reset@example.com');
      assert.match(user.passwordHash, /^pbkdf2-sha256\$210000\$/);
      assert.equal(user.passwordHash.includes('RecoveredPass123!'), false);
      assert.equal(data.events.some((event) => event.type === 'admin_password_reset'), true);
    } finally {
      await fixture.close();
    }
  });

  it('expires customer sessions on the server instead of trusting persistent cookies forever', async () => {
    const fixture = await createServerFixture({ sessionTtlMs: 60_000 });

    try {
      const cookie = await fixture.createVerifiedCustomer('expired-session@example.com');
      const data = await fixture.readData();
      const token = cookie.split('=')[1];
      data.sessions[token].expiresAt = '2020-01-01T00:00:00.000Z';
      await fixture.writeData(data);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      const mutation = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Expired Session Key' },
      });
      assert.equal(dashboard.json.authenticated, false);
      assert.equal(mutation.status, 401);
    } finally {
      await fixture.close();
    }
  });

  it('stores model group on customer keys and blocks models outside that group', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        return jsonResponse(200, {
          id: 'chatcmpl-openai-group',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('model-group@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'OpenAI Key', modelGroup: 'OpenAI' },
      });
      assert.equal(token.json.key.modelGroup, 'OpenAI');

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5', 'claude-haiku'],
          keys: [{ value: 'sk-openai-group', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const models = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });
      assert.deepEqual(models.json.data.map((item) => item.id), ['gpt-5.5']);

      const blocked = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'blocked' }] },
      });
      assert.equal(blocked.status, 403);
      assert.match(blocked.text, /模型分组/);

      const allowed = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'allowed' }] },
      });
      assert.equal(allowed.status, 200);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-openai-group');
    } finally {
      await fixture.close();
    }
  });

  it('deducts user quota on gateway calls and blocks requests before upstream when quota is gone', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      allowDemoRecharge: true,
      quotaCost: 500,
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
        });
        return jsonResponse(200, {
          id: 'chatcmpl-charged',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'charged' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { amountCny: 1.01, method: 'manual_test' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '计费 Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-billable', quotaRemaining: 1000, latencyMs: 80 }],
        },
      });

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'first' }] },
      });
      assert.equal(first.status, 200);

      const afterFirst = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(afterFirst.json.account.packageQuota, '$0.42');
      assert.equal(afterFirst.json.account.boosterQuota, '$0.14');
      assert.equal(afterFirst.json.account.quotaLeft, '$0.56');
      assert.equal(afterFirst.json.account.todayCost, '$0.69');
      assert.equal(afterFirst.json.account.todayCalls, '1 次');

      const ccSwitchUsage = await fixture.request('/api/frist/key-usage', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });
      assert.equal(ccSwitchUsage.status, 200);
      assert.equal(ccSwitchUsage.json.ok, true);
      assert.equal(ccSwitchUsage.json.valid, true);
      assert.equal(ccSwitchUsage.json.plan, '日卡');
      assert.equal(ccSwitchUsage.json.remainingUsd, 0.56);
      assert.equal(ccSwitchUsage.json.usedUsd, 0.69);
      assert.equal(ccSwitchUsage.json.totalUsd, 1.25);
      assert.equal(ccSwitchUsage.json.todayCalls, '1 次');
      assert.equal(JSON.stringify(ccSwitchUsage.json).includes(token.json.key.secret), false);
      assert.equal(JSON.stringify(ccSwitchUsage.json).includes('sk-billable'), false);

      const blockedUsage = await fixture.request('/api/frist/key-usage', {
        headers: { Authorization: 'Bearer fk-live-wrong-key' },
      });
      assert.equal(blockedUsage.status, 401);

      const blocked = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'second' }] },
      });
      assert.equal(blocked.status, 402);
      assert.match(blocked.text, /余额不足/);
      assert.equal(upstreamCalls.length, 1);
    } finally {
      await fixture.close();
    }
  });

  it('lets customers configure a custom balance alert email from the dashboard API', async () => {
    const fixture = await createServerFixture({ requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'balance-alert@example.com', password: 'TestPass123!' },
      });

      const saved = await fixture.request('/api/frist/balance-alert', {
        method: 'PUT',
        cookie: registered.cookie,
        body: {
          enabled: true,
          thresholdUsd: 5.5,
          email: 'ops-billing@example.com',
        },
      });
      assert.equal(saved.status, 200);
      assert.equal(saved.json.balanceAlert.enabled, true);
      assert.equal(saved.json.balanceAlert.thresholdUsd, 5.5);
      assert.equal(saved.json.balanceAlert.email, 'ops-billing@example.com');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });
      assert.equal(dashboard.json.balanceAlert.enabled, true);
      assert.equal(dashboard.json.balanceAlert.thresholdUsd, 5.5);
      assert.equal(dashboard.json.balanceAlert.threshold, '$5.50');
      assert.equal(dashboard.json.balanceAlert.email, 'ops-billing@example.com');
    } finally {
      await fixture.close();
    }
  });

  it('sends one branded email when customer balance crosses the custom alert threshold', async () => {
    const sentEmails = [];
    const fixture = await createServerFixture({
      quotaCost: 300,
      balanceAlertEmailSender: (message) => sentEmails.push(message),
      publicGatewayBaseUrl: 'https://gateway.frist-api.dev/v1',
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-balance-alert',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('threshold-crossing@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      await fixture.request('/api/frist/balance-alert', {
        method: 'PUT',
        cookie,
        body: { enabled: true, thresholdUsd: 5.5, email: 'billing-watch@example.com' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '余额预警 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-balance-alert', quotaRemaining: 900, latencyMs: 80 }],
        },
      });
      sentEmails.length = 0;

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'first billable call' }] },
      });
      assert.equal(first.status, 200);
      assert.equal(sentEmails.length, 1);
      assert.equal(sentEmails[0].to, 'billing-watch@example.com');
      assert.match(sentEmails[0].subject, /余额预警/);
      assert.match(sentEmails[0].html, /CC中转 Balance Guard/);
      assert.match(sentEmails[0].html, /当前余额/);
      assert.match(sentEmails[0].html, /预警阈值/);
      assert.match(sentEmails[0].html, /打开 CC中转/);
      assert.match(sentEmails[0].html, /\$5\.50/);
      assert.match(sentEmails[0].text, /threshold-crossing@example\.com/);
      assert.match(sentEmails[0].text, /预警阈值: \$5\.50/);

      const second = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'second billable call' }] },
      });
      assert.equal(second.status, 200);
      assert.equal(sentEmails.length, 1);
    } finally {
      await fixture.close();
    }
  });

  it('supports Codex/OpenCode response-format gateway calls without losing request context', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        return jsonResponse(200, {
          id: 'resp-codex',
          model: 'gpt-5.5',
          output: [{ type: 'message', content: [{ type: 'output_text', text: 'ok' }] }],
          usage: { input_tokens: 20, output_tokens: 4, total_tokens: 24 },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('codex-response@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Codex Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-codex-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const body = {
        model: 'gpt-5.5',
        input: [
          { role: 'user', content: [{ type: 'input_text', text: 'keep this response context' }] },
        ],
        metadata: { frist_session_id: 'codex-session-1' },
      };
      const response = await fixture.request('/v1/responses', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body,
      });

      assert.equal(response.status, 200);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].url, 'https://supplier.example.com/openai/responses');
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-codex-day');
      assert.deepEqual(upstreamCalls[0].body, body);
    } finally {
      await fixture.close();
    }
  });

  it('accepts Claude Code Anthropic Messages calls and routes ChatGPT models through OpenAI-compatible stock', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        return jsonResponse(200, {
          id: 'chatcmpl-claude-code-openai',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'openai through claude code' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 18, completion_tokens: 6, total_tokens: 24 },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('claude-code-openai@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Claude Code OpenAI Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-claude-code-openai', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const response = await fixture.request('/v1/messages', {
        method: 'POST',
        headers: {
          'x-api-key': token.json.key.secret,
          'x-frist-session-id': 'claude-code-openai-session',
        },
        body: {
          model: 'gpt-5.5',
          system: 'keep claude code system prompt',
          messages: [{ role: 'user', content: [{ type: 'text', text: 'route this as chatgpt' }] }],
          max_tokens: 64,
        },
      });

      assert.equal(response.status, 200);
      assert.equal(response.json.type, 'message');
      assert.equal(response.json.role, 'assistant');
      assert.equal(response.json.model, 'gpt-5.5');
      assert.equal(response.json.content[0].text, 'openai through claude code');
      assert.deepEqual(
        upstreamCalls.map((call) => call.url),
        [
          'https://supplier.example.com/openai/messages',
          'https://supplier.example.com/openai/chat/completions',
        ],
      );
      assert.equal(upstreamCalls[1].authorization, 'Bearer sk-claude-code-openai');
      assert.deepEqual(upstreamCalls[1].body.messages, [
        { role: 'system', content: 'keep claude code system prompt' },
        { role: 'user', content: 'route this as chatgpt' },
      ]);
    } finally {
      await fixture.close();
    }
  });

  it('routes Claude Code Anthropic Messages calls to native Claude-compatible upstreams first', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        if (String(url).endsWith('/messages')) {
          return jsonResponse(200, {
            id: 'msg-native-claude',
            type: 'message',
            role: 'assistant',
            model: 'claude-sonnet-4-5-c',
            content: [{ type: 'text', text: 'native claude upstream' }],
            usage: { input_tokens: 12, output_tokens: 4 },
          });
        }
        return jsonResponse(500, { error: { message: 'chat fallback should not run' } });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('claude-native-upstream@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Claude Native Key', modelGroup: 'Claude' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-native-claude', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'trusted',
        },
      });

      const response = await fixture.request('/v1/messages', {
        method: 'POST',
        headers: {
          'x-api-key': token.json.key.secret,
          'x-frist-session-id': 'claude-native-session',
        },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: [{ type: 'text', text: 'route natively' }] }],
          max_tokens: 64,
        },
      });

      assert.equal(response.status, 200);
      assert.equal(response.json.type, 'message');
      assert.equal(response.json.content[0].text, 'native claude upstream');
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].url, 'https://supplier.example.com/v1/messages');
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-native-claude');
      assert.equal(upstreamCalls[0].body.model, 'claude-sonnet-4-5-c');
      assert.deepEqual(upstreamCalls[0].body.messages, [
        { role: 'user', content: [{ type: 'text', text: 'route natively' }] },
      ]);
    } finally {
      await fixture.close();
    }
  });

  it('falls back from Responses to Chat Completions so Codex can use Claude model stock', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        if (String(url).endsWith('/responses')) {
          return jsonResponse(404, { error: { message: 'responses not supported' } });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-codex-claude',
          model: 'claude-opus-4-6-c',
          choices: [{ message: { role: 'assistant', content: 'claude through codex' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 16, completion_tokens: 5, total_tokens: 21 },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('codex-claude@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Codex Claude Key', modelGroup: 'Claude' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/anthropic-compatible',
          pool: 'day',
          models: ['claude-opus-4-6-c'],
          keys: [{ value: 'sk-codex-claude-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const body = {
        model: 'claude-opus-4-6-c',
        input: [
          { role: 'user', content: [{ type: 'input_text', text: 'keep codex response context' }] },
        ],
        metadata: { frist_session_id: 'codex-claude-session' },
      };
      const response = await fixture.request('/v1/responses', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body,
      });

      assert.equal(response.status, 200);
      assert.equal(response.json.id, 'resp_chatcmpl-codex-claude');
      assert.equal(response.json.model, 'claude-opus-4-6-c');
      assert.equal(response.json.output[0].content[0].text, 'claude through codex');
      assert.deepEqual(
        upstreamCalls.map((call) => call.url),
        [
          'https://supplier.example.com/anthropic-compatible/responses',
          'https://supplier.example.com/anthropic-compatible/chat/completions',
        ],
      );
      assert.deepEqual(upstreamCalls[1].body.messages, [
        { role: 'user', content: 'keep codex response context' },
      ]);
    } finally {
      await fixture.close();
    }
  });

  it('returns only customer-safe models from healthy inventory', async () => {
    const fixture = await createServerFixture();

    try {
      const cookie = await fixture.createVerifiedCustomer('models@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Models Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.4', 'gpt-5.5', 'gpt-image-2'],
          keys: [{ value: 'sk-models-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const models = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });

      assert.equal(models.status, 200);
      assert.deepEqual(
        models.json.data.map((item) => item.id),
        ['gpt-5.5', 'gpt-5.4', 'gpt-image-2'],
      );
      assert.equal(JSON.stringify(models.json).includes('sk-models-day'), false);
    } finally {
      await fixture.close();
    }
  });

  it('falls back Chat Completions requests to upstream Responses when chat routes are missing', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        upstreamCalls.push({
          url: String(url),
          body: JSON.parse(options.body),
        });
        if (String(url).endsWith('/chat/completions')) {
          return jsonResponse(404, {
            error: 'Not Found',
            message: 'Route /openai/chat/completions not found',
          });
        }
        if (String(url).endsWith('/responses')) {
          return jsonResponse(200, {
            id: 'resp-chat-fallback',
            object: 'response',
            model: 'gpt-5.5',
            output: [
              {
                type: 'message',
                role: 'assistant',
                content: [{ type: 'output_text', text: 'OK from responses fallback' }],
              },
            ],
            usage: { input_tokens: 4, output_tokens: 3, total_tokens: 7 },
          });
        }
        return jsonResponse(500, { error: 'unexpected upstream path' });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('chat-fallback@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Chat Fallback Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-chat-fallback-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 12,
        },
      });

      assert.equal(gateway.status, 200);
      assert.equal(gateway.json.object, 'chat.completion');
      assert.equal(gateway.json.choices[0].message.content, 'OK from responses fallback');
      assert.deepEqual(
        upstreamCalls.map((call) => call.url),
        ['https://supplier.example.com/openai/chat/completions', 'https://supplier.example.com/openai/responses'],
      );
      assert.deepEqual(upstreamCalls[1].body.input, [{ role: 'user', content: [{ type: 'input_text', text: 'ping' }] }]);
    } finally {
      await fixture.close();
    }
  });

  it('accepts OpenCode openai-prefixed Chat Completions gateway routes', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        upstreamCalls.push({
          url: String(url),
          body: JSON.parse(options.body),
        });
        return jsonResponse(200, {
          id: `chatcmpl-${upstreamCalls.length}`,
          object: 'chat.completion',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: `alias-${upstreamCalls.length}` }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 2, completion_tokens: 2, total_tokens: 4 },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('opencode-alias@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'OpenCode Alias Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-opencode-alias-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      for (const path of ['/v1/openai/chat/completions', '/openai/chat/completions']) {
        const gateway = await fixture.request(path, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token.json.key.secret}` },
          body: {
            model: 'gpt-5.5',
            messages: [{ role: 'user', content: 'ping' }],
            max_tokens: 8,
          },
        });

        assert.equal(gateway.status, 200);
        assert.match(gateway.json.choices[0].message.content, /^alias-/);
      }
      assert.deepEqual(
        upstreamCalls.map((call) => call.url),
        [
          'https://supplier.example.com/openai/chat/completions',
          'https://supplier.example.com/openai/chat/completions',
        ],
      );
    } finally {
      await fixture.close();
    }
  });

  it('skips invalid upstream credentials before returning a gateway response', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        const body = JSON.parse(options.body);
        const auth = options.headers.authorization || '';
        upstreamCalls.push({
          url: String(url),
          model: body.model,
          keyPreview: auth.includes('bad-day') ? 'bad-day' : 'good-day',
        });
        if (auth.includes('bad-day')) {
          return jsonResponse(401, { error: 'Invalid API key' });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-good-day',
          object: 'chat.completion',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'healthy fallback key' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 2, completion_tokens: 2, total_tokens: 4 },
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('invalid-upstream-failover@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Invalid Upstream Failover Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [
            { value: 'sk-bad-day', quotaRemaining: 900, latencyMs: 10 },
            { value: 'sk-good-day', quotaRemaining: 900, latencyMs: 20 },
          ],
        },
      });

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });

      assert.equal(gateway.status, 200);
      assert.equal(gateway.json.choices[0].message.content, 'healthy fallback key');
      assert.deepEqual(upstreamCalls.map((call) => call.keyPreview), ['bad-day', 'good-day']);
      assert.equal(inventory.json.credentials.find((item) => item.status === 'failed')?.status, 'failed');
      assert.equal(inventory.json.credentials.find((item) => item.status === 'healthy')?.status, 'healthy');
    } finally {
      await fixture.close();
    }
  });

  it('persists disabled upstream credentials when every candidate is rejected', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        const auth = options.headers.authorization || '';
        upstreamCalls.push({
          url: String(url),
          keyPreview: auth.includes('disabled-a') ? 'disabled-a' : 'disabled-b',
        });
        return jsonResponse(401, { error: { message: 'API key is disabled' } });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('all-upstreams-disabled@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'All Disabled Upstream Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [
            { value: 'sk-disabled-a', quotaRemaining: 900, latencyMs: 10 },
            { value: 'sk-disabled-b', quotaRemaining: 900, latencyMs: 20 },
          ],
        },
      });

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      const models = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });

      assert.equal(gateway.status, 503);
      assert.match(gateway.text, /当前模型暂不可用/);
      assert.deepEqual(upstreamCalls.map((call) => call.keyPreview), ['disabled-a', 'disabled-b']);
      assert.equal(inventory.json.credentials.every((item) => item.status === 'failed'), true);
      assert.equal(models.json.data.some((item) => item.id === 'gpt-5.5'), false);
    } finally {
      await fixture.close();
    }
  });

  it('circuit-breaks overspent slow supplier inventory before routing to a healthy fallback', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        const auth = options.headers.authorization || '';
        upstreamCalls.push(auth.includes('overspent-slow') ? 'overspent-slow' : 'fallback-healthy');
        return jsonResponse(200, {
          id: 'chatcmpl-fallback',
          object: 'chat.completion',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'fallback after breaker' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 2, completion_tokens: 2, total_tokens: 4 },
        });
      },
      nowFactory: () => new Date('2026-07-02T15:00:00.000Z'),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('overspent-slow-breaker@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Overspent Slow Breaker Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://metered-supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [
            {
              value: 'sk-overspent-slow',
              quotaRemaining: 100,
              quotaTotal: 5000,
              latencyMs: 16_110,
              dailySpendLimitCents: 120,
            },
          ],
        },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'default',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-fallback-healthy', quotaRemaining: 900, quotaTotal: 900, latencyMs: 80 }],
        },
      });
      const data = await fixture.readData();
      const slowCredential = data.credentials.find((item) => item.rawKey === 'sk-overspent-slow');
      assert.equal(slowCredential.dailySpendLimitCents, 120);
      data.events.push({
        type: 'gateway_routed',
        credentialId: slowCredential.id,
        quotaCost: 150,
        latencyMs: 16_110,
        status: 'success',
        at: '2026-07-02T10:00:00.000Z',
      });
      await fixture.writeData(data);

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });

      assert.equal(gateway.status, 200);
      assert.equal(gateway.json.choices[0].message.content, 'fallback after breaker');
      assert.deepEqual(upstreamCalls, ['fallback-healthy']);
      const slowInventory = inventory.json.credentials.find((item) => item.keyPreview === slowCredential.keyPreview);
      assert.equal(slowInventory.status, 'exhausted');
      assert.equal(slowInventory.enabled, false);
      assert.match(slowInventory.lastProbeReason, /daily_spend_limit/);
    } finally {
      await fixture.close();
    }
  });

  it('marks probe-healthy credentials failed and sends one alert when real calls return 503', async () => {
    const upstreamCalls = [];
    const alerts = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options) => {
        const auth = options.headers.authorization || '';
        if (auth.includes('real-503')) {
          upstreamCalls.push('real-503');
          return jsonResponse(503, { error: 'upstream overloaded' });
        }
        upstreamCalls.push('fallback-ok');
        return jsonResponse(200, {
          id: 'chatcmpl-fallback-ok',
          object: 'chat.completion',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'fallback ok' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 2, completion_tokens: 2, total_tokens: 4 },
        });
      },
      notifyCredentialIssue: async (payload) => {
        alerts.push(payload);
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('probe-real-503@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Probe Healthy Real 503 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [
            { value: 'sk-real-503', quotaRemaining: 900, latencyMs: 10 },
            { value: 'sk-fallback-ok', quotaRemaining: 900, latencyMs: 20 },
          ],
        },
      });

      const firstGateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      const secondGateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping again' }],
          max_tokens: 8,
        },
      });
      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });

      assert.equal(firstGateway.status, 200);
      assert.equal(secondGateway.status, 200);
      assert.deepEqual(upstreamCalls, ['real-503', 'fallback-ok', 'fallback-ok']);
      assert.equal(alerts.length, 1);
      assert.equal(alerts[0].issueType, 'upstream');
      assert.match(alerts[0].reason, /upstream_http_503/);
      assert.equal(inventory.json.credentials.find((item) => item.status === 'failed')?.status, 'failed');
      assert.equal(inventory.json.credentials.find((item) => item.status === 'healthy')?.status, 'healthy');
    } finally {
      await fixture.close();
    }
  });

  it('exports the same complete model list for Codex and OpenCode import URLs', async () => {
    const fixture = await createServerFixture({ requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'import-models@example.com', password: 'TestPass123!' },
      });
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Codex OpenAI Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.4-mini', 'gpt-5.4', 'gpt-5.5', 'gpt-image-2'],
          keys: [{ value: 'sk-import-models-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      for (const target of ['Codex', 'OpenCode']) {
        const imported = await fixture.request(`/api/frist/import-url?target=${target}&model=gpt-5.4`, {
          cookie: registered.cookie,
        });
        const importUrl = new URL(imported.json.url);
        const expectedModels = [
          'gpt-5.5',
          'gpt-5.4',
          'gpt-5.4-mini',
          'gpt-image-2',
        ];

        assert.equal(imported.status, 200);
        assert.ok(imported.json.url.length < 3500);
        assert.equal(importUrl.searchParams.get('model'), 'gpt-5.4');
        assert.equal(imported.json.defaultModel, 'gpt-5.4');
        assert.deepEqual(imported.json.availableModels, expectedModels);
        assert.deepEqual(imported.json.config.availableModels, expectedModels);
        assert.match(imported.json.config.configToml, /available_models = \["gpt-5\.5", "gpt-5\.4", "gpt-5\.4-mini", "gpt-image-2"\]/);
        assert.equal(importUrl.searchParams.get('config'), null);
        assert.equal(importUrl.searchParams.get('availableModels'), null);
      }
    } finally {
      await fixture.close();
    }
  });

  it('rejects New-API wildcard-only imports until real upstream models are known', async () => {
    let tokenCreated = false;
    let tokenQuota = 0;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      newApiGatewayEnabled: false,
      fetchImpl: async (url, init = {}) => {
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, {
            success: true,
            data: {
              items: tokenCreated ? [
                {
                  id: 9,
                  name: 'OpenAI Partial Key',
                  key: 'sk-openai-partial-secret',
                  status: 1,
                  remain_quota: tokenQuota,
                  unlimited_quota: false,
                  model_limits_enabled: true,
                  model_limits: 'gpt-*',
                },
              ] : [],
            },
          });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          const body = JSON.parse(init.body);
          assert.equal(body.remain_quota, 0);
          tokenCreated = true;
          tokenQuota = body.remain_quota;
          return jsonResponse(200, {
            success: true,
            data: {
              id: 9,
              ...body,
              key: 'sk-openai-partial-secret',
              status: 1,
              remain_quota: tokenQuota,
              unlimited_quota: false,
              model_limits_enabled: true,
              model_limits: 'gpt-*',
            },
          });
        }
        if (path === '/api/token/search') {
          return jsonResponse(200, { success: true, data: { items: [] } });
        }
        if (path === '/api/token/9') {
          return jsonResponse(200, {
            success: true,
            data: {
              id: 9,
              name: 'OpenAI Partial Key',
              status: 1,
              remain_quota: tokenQuota,
              unlimited_quota: false,
              model_limits_enabled: true,
              model_limits: 'gpt-*',
            },
          });
        }
        if (path === '/api/token/' && init.method === 'PUT') {
          const body = JSON.parse(init.body);
          assert.equal(requestUrl.searchParams.has('status_only'), false);
          assert.equal(body.id, 9);
          assert.equal(body.remain_quota, 36_000_000);
          assert.equal(body.unlimited_quota, false);
          tokenQuota = body.remain_quota;
          return jsonResponse(200, { success: true, data: body });
        }
        if (path === '/api/token/9/key') {
          return jsonResponse(200, { success: true, data: { key: 'sk-openai-partial-secret' } });
        }
        if (path === '/api/user/self' || path === '/api/log/self' || path === '/api/log/self/stat' || path === '/api/data/self' || path === '/api/subscription/self' || path === '/api/user/topup/info' || path === '/api/user/aff') {
          return jsonResponse(200, { success: true, data: {} });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'partial-openai@example.com', password: 'TestPass123!' },
      });
      const funded = await fixture.readData();
      const fundedUser = funded.users.find((user) => user.email === 'partial-openai@example.com');
      fundedUser.packageQuotaCents = 7200;
      fundedUser.balanceCents = 7200;
      await fixture.writeData(funded);
      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'OpenAI Partial Key', modelGroup: 'OpenAI' },
      });
      assert.equal(created.status, 200);

      const imported = await fixture.request(`/api/frist/import-url?target=Codex&model=gpt-5.4&keyId=${created.json.key.id}`, {
        cookie: registered.cookie,
      });
      assert.equal(imported.status, 409);
      assert.match(imported.json.error, /暂无健康上游模型/);
      assert.deepEqual(
        normalizeClientAvailableModels(['gpt-*'], { modelGroup: 'OpenAI', expandPatterns: false }),
        [],
      );
    } finally {
      await fixture.close();
    }
  });


  it('does not show hard-coded catalog models when a customer has no healthy upstream inventory', async () => {
    const fixture = await createServerFixture({ requireEmailVerification: false });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'no-live-models@example.com', password: 'TestPass123!' },
      });
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'No Live Key', modelGroup: 'OpenAI' },
      });

      const imported = await fixture.request('/api/frist/import-url?target=Codex&model=gpt-5.5', {
        cookie: registered.cookie,
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Empty Inventory Key', modelGroup: 'OpenAI' },
      });
      const models = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });

      assert.equal(imported.status, 409);
      assert.match(imported.json.error, /暂无健康上游模型/);
      assert.equal(models.status, 200);
      assert.deepEqual(models.json.data, []);
      assert.equal(dashboard.json.modelCatalog.some((item) => item.model === 'gpt-5.5'), false);
    } finally {
      await fixture.close();
    }
  });

  it('returns a customer-safe model catalog with pricing and no raw upstream key material', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5', 'gpt-image-2'],
          keys: [{ value: 'sk-catalog-secret', quotaRemaining: 900, latencyMs: 80 }],
          priceText: 'gpt-5.5 input ¥8/1M output ¥48/1M',
          pricing: { profitMultiplier: 1, safetyCnyPerMillion: 0 },
        },
      });

      const cookie = await fixture.createVerifiedCustomer();
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.status, 200);
      assert.equal(Array.isArray(dashboard.json.modelCatalog), true);
      const gpt = dashboard.json.modelCatalog.find((item) => item.model === 'gpt-5.5');
      const image = dashboard.json.modelCatalog.find((item) => item.model === 'gpt-image-2');
      assert.equal(gpt.family, 'OpenAI');
      assert.equal(gpt.available, true);
      assert.equal(gpt.price, '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M');
      assert.equal(image.tagline, '图片生成');
      assert.equal(JSON.stringify(dashboard.json.modelCatalog).includes('sk-catalog-secret'), false);
      assert.equal(JSON.stringify(dashboard.json.modelCatalog).includes('supplier.example.com'), false);
    } finally {
      await fixture.close();
    }
  });

  it('routes image generation models through the same user key, day-card and upstream failover chain', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
          body: JSON.parse(options.body),
        });
        return jsonResponse(200, {
          created: 1777777777,
          data: [{ b64_json: 'ZmFrZS1pbWFnZQ==' }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('image-playground@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '图片 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['image2'],
          keys: [{ value: 'sk-image-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const image = await fixture.request('/v1/images/generations', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'image2',
          prompt: '生成一张 CC中转 测试图',
          size: '1024x1024',
        },
      });

      assert.equal(image.status, 200);
      assert.deepEqual(image.json.data, [{ b64_json: 'ZmFrZS1pbWFnZQ==' }]);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].url, 'https://supplier.example.com/openai/images/generations');
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-image-day');
      assert.equal(upstreamCalls[0].body.model, 'gpt-image-2');
      assert.equal(upstreamCalls[0].body.prompt, '生成一张 CC中转 测试图');
    } finally {
      await fixture.close();
    }
  });

  it('probes image-only supplier stock through the image generation endpoint', async () => {
    const probeUrls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url) => {
        probeUrls.push(String(url));
        if (String(url).endsWith('/images/generations')) {
          return jsonResponse(200, {
            created: 1777777777,
            data: [{ b64_json: 'ZmFrZS1pbWFnZQ==' }],
          });
        }
        return jsonResponse(400, { error: { message: 'this endpoint does not support image model' } });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          probeMode: 'strict',
          models: ['image2'],
          keys: [{ value: 'sk-image-only', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      assert.equal(replenished.status, 200);
      assert.deepEqual(replenished.json.supplierProfile.models, ['gpt-image-2']);
      assert.equal(replenished.json.credentials.length, 1);
      assert.equal(replenished.json.credentials[0].status, 'healthy');
      assert.equal(replenished.json.credentials[0].lastProbeStatus, 'image_probe_ok');
      assert.deepEqual(probeUrls, ['https://supplier.example.com/openai/images/generations']);
    } finally {
      await fixture.close();
    }
  });

  it('accepts response-format-only day-card suppliers during replenishment probing', async () => {
    const probeUrls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url) => {
        probeUrls.push(String(url));
        if (String(url).endsWith('/chat/completions')) {
          return jsonResponse(404, { error: { message: 'chat not supported' } });
        }
        if (String(url).endsWith('/responses')) {
          return jsonResponse(200, {
            id: 'resp-probe',
            model: 'gpt-5.5',
            output: [{ type: 'message', content: [{ type: 'output_text', text: 'ok' }] }],
          });
        }
        return jsonResponse(404, { error: { message: 'not found' } });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          probeMode: 'auto',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-response-only', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.length, 1);
      assert.equal(replenished.json.credentials[0].status, 'healthy');
      assert.deepEqual(probeUrls, [
        'https://supplier.example.com/openai/chat/completions',
        'https://supplier.example.com/openai/responses',
      ]);
    } finally {
      await fixture.close();
    }
  });

  it('uses supplier auth field config during replenishment probing and gateway routing', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const headers = options.headers || {};
        const customKey = headers['x-api-key'] || headers['X-API-Key'];
        const referer = headers['http-referer'] || headers['HTTP-Referer'];
        upstreamCalls.push({
          url: String(url),
          customKey,
          referer,
          authorization: headers.authorization || headers.Authorization,
        });
        if (customKey !== 'supplier-custom-auth-key' || referer !== 'https://frist-api.example') {
          return jsonResponse(401, { error: { message: 'missing cleaned supplier headers' } });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-custom-auth',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'custom auth ok' } }],
        });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [
            {
              value: 'supplier-custom-auth-key',
              quotaRemaining: 1000,
              authHeaderName: 'x-api-key',
              authHeaderValuePrefix: '',
              extraHeaders: {
                'http-referer': 'https://frist-api.example',
                'x-title': 'CC中转',
              },
            },
          ],
          probeMode: 'strict',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.length, 1);

      const cookie = await fixture.createVerifiedCustomer('custom-auth@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '自定义认证 Key', modelGroup: 'OpenAI' },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'custom auth' }] },
      });
      assert.equal(response.status, 200);
      assert.equal(upstreamCalls.every((call) => call.customKey === 'supplier-custom-auth-key'), true);
      assert.equal(upstreamCalls.every((call) => call.referer === 'https://frist-api.example'), true);
      assert.equal(upstreamCalls.some((call) => call.authorization), false);
    } finally {
      await fixture.close();
    }
  });

  it('requires a lightweight challenge before public registration when captcha is enabled', async () => {
    const fixture = await createServerFixture({ requireCaptcha: true });

    try {
      const blocked = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'captcha@example.com', password: 'TestPass123!' },
      });
      assert.equal(blocked.status, 400);
      assert.match(blocked.text, /验证码/);

      const challenge = await fixture.request('/api/frist/challenge');
      assert.equal(challenge.status, 200);
      assert.match(challenge.json.id, /^cap-/);
      assert.equal(typeof challenge.json.question, 'string');
      assert.ok(challenge.json.question.length > 8);
      assert.equal(solveRegistrationChallenge(challenge.json.question).length > 0, true);

      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: {
          email: 'captcha@example.com',
          password: 'TestPass123!',
          captchaId: challenge.json.id,
          captchaAnswer: solveRegistrationChallenge(challenge.json.question),
        },
      });
      assert.equal(registered.status, 200);
    } finally {
      await fixture.close();
    }
  });

  it('lets returning customers log in without captcha while keeping registration protected', async () => {
    const fixture = await createServerFixture({ requireCaptcha: true, requireEmailVerification: false });

    try {
      const challenge = await fixture.request('/api/frist/challenge');
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: {
          email: 'login-without-captcha@example.com',
          password: 'TestPass123!',
          captchaId: challenge.json.id,
          captchaAnswer: solveRegistrationChallenge(challenge.json.question),
        },
      });
      assert.equal(registered.status, 200);

      const loggedIn = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: {
          email: 'login-without-captcha@example.com',
          password: 'TestPass123!',
          captchaId: 'wrong-challenge',
          captchaAnswer: 'wrong-answer',
        },
      });
      assert.equal(loggedIn.status, 200);
      assert.equal(loggedIn.json.user.email, 'login-without-captcha@example.com');
    } finally {
      await fixture.close();
    }
  });

  it('rate limits repeated auth attempts from the same client', async () => {
    const fixture = await createServerFixture({ authRateLimitMax: 1, authRateLimitWindowMs: 60_000 });

    try {
      const first = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'rate-limit@example.com', password: 'wrong-password' },
      });
      assert.equal(first.status, 401);

      const second = await fixture.request('/api/frist/login', {
        method: 'POST',
        body: { email: 'rate-limit@example.com', password: 'wrong-password' },
      });
      assert.equal(second.status, 429);
      assert.match(second.text, /请求过于频繁/);
    } finally {
      await fixture.close();
    }
  });

  it('prevents one manual card code from being redeemed by multiple customers', async () => {
    const fixture = await createServerFixture();

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-100-unlimited', quantity: 2, note: '内测测试批次' },
      });
      assert.equal(batch.status, 200);
      assert.equal(batch.json.cards.length, 2);
      assert.match(batch.json.cards[0].code, /^CC-/);
      assert.match(batch.json.exportText, /Codex API 100刀额度\/不限时/);
      const code = batch.json.cards[0].code;
      const rawAfterCreate = await fixture.readRawData();
      assert.equal(rawAfterCreate.includes(code), false, '新卡密不能明文落库');
      assert.match(rawAfterCreate, /codeHash/);
      assert.match(rawAfterCreate, /codeCipher/);

      const inventory = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.status, 200);
      assert.equal(inventory.json.cards.filter((card) => card.status === 'unused').length, 2);
      assert.equal(inventory.json.cards.some((card) => card.code === code), false, '列表只能展示脱敏卡密');

      const firstCookie = await fixture.createVerifiedCustomer('first-card@example.com');
      const firstRedeem = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: firstCookie,
        body: { code },
      });
      assert.equal(firstRedeem.status, 200);
      assert.equal(firstRedeem.json.account.boosterQuota, '$100.00');

      const secondCookie = await fixture.createVerifiedCustomer('second-card@example.com');
      const secondRedeem = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: secondCookie,
        body: { code },
      });
      assert.equal(secondRedeem.status, 409);
      assert.match(secondRedeem.text, /兑换码已使用/);

      const afterRedeem = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      const redeemedCard = afterRedeem.json.cards.find((card) => card.codeHash === batch.json.cards[0].codeHash);
      assert.equal(redeemedCard.status, 'redeemed');
      assert.equal(redeemedCard.redeemedEmail, 'fi***@example.com');
    } finally {
      await fixture.close();
    }
  });

  it('rate limits redemption attempts by IP and logged-in account', async () => {
    const fixture = await createServerFixture({ redemptionRateLimitMax: 1, redemptionRateLimitWindowMs: 60_000 });

    try {
      const cookie = await fixture.createVerifiedCustomer('redeem-limit@example.com');
      const first = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        headers: { 'x-forwarded-for': '198.51.100.10' },
        body: { code: 'BAD-CODE-ONE' },
      });
      assert.equal(first.status, 400);

      const sameIp = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        headers: { 'x-forwarded-for': '198.51.100.10' },
        body: { code: 'BAD-CODE-TWO' },
      });
      assert.equal(sameIp.status, 429);

      const sameUser = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        headers: { 'x-forwarded-for': '198.51.100.11' },
        body: { code: 'BAD-CODE-THREE' },
      });
      assert.equal(sameUser.status, 429);
    } finally {
      await fixture.close();
    }
  });


  it('auto replenishes Xianyu card stock to approved safety levels without exceeding daily caps', async () => {
    const fixture = await createServerFixture();

    try {
      const first = await fixture.request('/api/admin/redemption-cards/autoreplenish', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { dryRun: false },
      });
      assert.equal(first.status, 200);
      assert.equal(first.json.enabled, true);
      assert.equal(first.json.created, 32);
      assert.equal(first.json.dailyCap, 50);
      assert.deepEqual(
        first.json.plans.map((plan) => ({ planId: plan.planId, safetyStock: plan.safetyStock, currentUnused: plan.currentUnused, toCreate: plan.toCreate, created: plan.created })),
        [
          { planId: 'xianyu-test-1', safetyStock: 3, currentUnused: 0, toCreate: 3, created: 3 },
          { planId: 'xianyu-5', safetyStock: 10, currentUnused: 0, toCreate: 10, created: 10 },
          { planId: 'xianyu-15', safetyStock: 10, currentUnused: 0, toCreate: 10, created: 10 },
          { planId: 'xianyu-50', safetyStock: 5, currentUnused: 0, toCreate: 5, created: 5 },
          { planId: 'xianyu-100', safetyStock: 3, currentUnused: 0, toCreate: 3, created: 3 },
          { planId: 'xianyu-500', safetyStock: 1, currentUnused: 0, toCreate: 1, created: 1 },
        ],
      );

      const inventory = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.cards.filter((card) => card.status === 'unused').length, 32);
      assert.equal(inventory.json.cards.some((card) => card.code && /-[A-Z0-9]{8}-[A-Z0-9]{8}/.test(card.code)), false);

      const second = await fixture.request('/api/admin/redemption-cards/autoreplenish', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { dryRun: false },
      });
      assert.equal(second.status, 200);
      assert.equal(second.json.created, 0);
      assert.equal(second.json.dailyCreated, 32);
    } finally {
      await fixture.close();
    }
  });

  it('starts Xianyu card auto replenishment in the background when enabled', async () => {
    const fixture = await createServerFixture({ cardAutoreplenishEnabled: true });

    try {
      await waitFor(async () => {
        const inventory = await fixture.request('/api/admin/redemption-cards', {
          headers: { 'x-admin-token': 'admin-test-token' },
        });
        assert.ok(inventory.json.cards.filter((card) => card.status === 'unused').length >= 32);
      });
      const data = await fixture.readData();
      const event = data.events.find((item) => item.type === 'redemption_cards_autoreplenished');
      assert.equal(event.created, 32);
      assert.equal(event.dryRun, false);
    } finally {
      await fixture.close();
    }
  });

  it('syncs newly generated CC cards into New-API redemptions when the production bridge is enabled', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-newapi-redemptions-'));
    const sqliteDb = join(dir, 'one-api.db');
    createNewApiRedemptionSchema(sqliteDb);
    const fixture = await createServerFixture({
      newApiEnabled: true,
      newApiBaseUrl: 'http://new-api.example.test',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '1',
      newApiDefaultTokenQuota: 7200,
      newApiSqliteDb: sqliteDb,
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, note: 'INTERNAL-TEST New-API sync' },
      });
      assert.equal(batch.status, 200);
      assert.match(batch.json.cards[0].code, /^CC-/);
      assert.equal(batch.json.newApiSync.synced, 1);
      assert.equal(
        sqliteScalar(sqliteDb, `select count(*) from redemptions where \`key\`=${sqlQuote(batch.json.cards[0].code)} and status=1;`),
        '1',
      );
      assert.equal(
        sqliteScalar(sqliteDb, `select quota > 0 from redemptions where \`key\`=${sqlQuote(batch.json.cards[0].code)};`),
        '1',
      );
    } finally {
      await fixture.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('keeps Xianyu 1 yuan test cards at exactly 1 yuan credit in local and New-API redemption quota', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-newapi-one-yuan-'));
    const sqliteDb = join(dir, 'one-api.db');
    createNewApiRedemptionSchema(sqliteDb);
    const fixture = await createServerFixture({
      newApiEnabled: true,
      newApiBaseUrl: 'http://new-api.example.test',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '1',
      newApiSqliteDb: sqliteDb,
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'xianyu-test-1', quantity: 1, note: 'INTERNAL-TEST one yuan quota' },
      });

      assert.equal(batch.status, 200);
      assert.equal(batch.json.cards[0].priceCny, 1);
      assert.equal(batch.json.cards[0].creditCents, 100);
      assert.equal(batch.json.cards[0].quotaUsd, 1);
      assert.equal(
        sqliteScalar(sqliteDb, `select quota from redemptions where \`key\`=${sqlQuote(batch.json.cards[0].code)};`),
        '500000',
      );
    } finally {
      await fixture.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('syncs New-API native redemption status back to local Xianyu fulfillment', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-newapi-status-sync-'));
    const sqliteDb = join(dir, 'one-api.db');
    createNewApiRedemptionSchema(sqliteDb);
    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      newApiEnabled: true,
      newApiBaseUrl: 'http://new-api.example.test',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '1',
      newApiSqliteDb: sqliteDb,
      newApiRedemptionStatusSyncEnabled: false,
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, note: 'INTERNAL-TEST New-API native status sync' },
      });
      assert.equal(batch.status, 200);
      const cardCode = batch.json.cards[0].code;

      const fulfillment = await fixture.request('/api/admin/xianyu/fulfillments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          orderId: 'xy_native_status_sync_001',
          buyerHint: '内测买家',
          productTitle: 'CC中转 内测日卡',
          cardCode,
        },
      });
      assert.equal(fulfillment.status, 200);
      assert.equal(fulfillment.json.fulfillment.status, 'delivered');

      const redeemedTime = Math.floor(Date.parse('2026-07-05T12:00:00Z') / 1000);
      sqliteScalar(
        sqliteDb,
        `update redemptions set status=2, redeemed_time=${redeemedTime}, used_user_id=88 where \`key\`=${sqlQuote(cardCode)};`,
      );

      const synced = await fixture.request('/api/admin/redemption-cards/sync-newapi-status', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(synced.status, 200);
      assert.equal(synced.json.syncedCards, 1);
      assert.equal(synced.json.syncedFulfillments, 1);
      assert.equal(synced.json.backfilledRedemptions, 1);

      const after = await fixture.request('/api/admin/xianyu/fulfillments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(after.json.summary.redeemed, 1);
      assert.equal(after.json.fulfillments[0].status, 'redeemed');
      assert.equal(after.json.fulfillments[0].orderId, 'xy_native_status_sync_001');

      const cards = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(cards.json.cards.find((card) => card.id === fulfillment.json.card.id).status, 'redeemed');
      const rawRuntime = await fixture.readRawData();
      assert.equal(rawRuntime.includes(cardCode), false, 'New-API 状态回写不能把完整卡密明文落库');
    } finally {
      await fixture.close();
      await rm(dir, { recursive: true, force: true });
    }
  });


  it('marks local CC card and Xianyu fulfillment redeemed after a New-API topup succeeds', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-newapi-local-redeem-'));
    const sqliteDb = join(dir, 'one-api.db');
    createNewApiRedemptionSchema(sqliteDb);
    const newApiCalls = [];
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiSqliteDb: sqliteDb,
      fetchImpl: async (url, init = {}) => {
        const path = new URL(String(url)).pathname;
        newApiCalls.push({ path, init });
        if (path === '/api/user/topup') {
          const body = JSON.parse(init.body || '{}');
          assert.match(body.key, /^CC-/);
          return jsonResponse(200, { success: true, data: { key: body.key, quota: 360000 } });
        }
        if (path === '/api/user/self') {
          return jsonResponse(200, {
            success: true,
            data: { email: 'newapi@example.com', username: 'newapi-user', group: 'default', quota: 360000, used_quota: 0 },
          });
        }
        if (path === '/api/log/self') {
          return jsonResponse(200, { success: true, data: { items: [] } });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { plan: 'balance', quotaUsd: 0.01, quantity: 1, note: 'INTERNAL-TEST New-API local redeem' },
      });
      assert.equal(batch.status, 200);

      const fulfillment = await fixture.request('/api/admin/xianyu/fulfillments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          orderId: 'XY-NEWAPI-LOCAL-REDEEM',
          buyerHint: '内测买家',
          productTitle: 'CC中转 内测加油包',
          cardCode: batch.json.cards[0].code,
        },
      });
      assert.equal(fulfillment.status, 200);
      const deliveredCode = fulfillment.json.deliveryMessage.match(/兑换码：([A-Z0-9-]+)/)?.[1] || '';
      assert.match(deliveredCode, /^CC-/);
      assert.match(fulfillment.json.deliveryMessage, /注册或登录账号/);
      assert.match(fulfillment.json.deliveryMessage, /进入“兑换码”/);
      assert.match(fulfillment.json.deliveryMessage, /进入“API Key”/);
      assert.match(fulfillment.json.deliveryMessage, /进入“CC Switch”/);
      assert.match(fulfillment.json.deliveryMessage, /选择模型测试/);
      assert.doesNotMatch(fulfillment.json.deliveryMessage, /jiyu\.245334\.xyz\/v1/);

      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'newapi-local-redeem@example.com', password: 'TestPass123!' },
      });
      const redeemed = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: deliveredCode },
      });
      assert.equal(redeemed.status, 200);
      assert.ok(newApiCalls.some((call) => call.path === '/api/user/topup'));

      const after = await fixture.request('/api/admin/xianyu/fulfillments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(after.json.summary.redeemed, 1);
      assert.equal(after.json.fulfillments[0].status, 'redeemed');
      assert.equal(after.json.fulfillments[0].redeemedEmail, 'ne***@example.com');

      const cards = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(cards.json.cards.find((card) => card.id === fulfillment.json.card.id).status, 'redeemed');
    } finally {
      await fixture.close();
      await rm(dir, { recursive: true, force: true });
    }
  });


  it('syncs New-API upstream balance and warns below operator thresholds without exposing admin tokens', async () => {
    const calls = [];
    const fixture = await createServerFixture({
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-secret-token',
      newApiUserId: '42',
      fetchImpl: async (url, init = {}) => {
        calls.push({ url: String(url), authorization: init.headers?.Authorization || '' });
        if (String(url).endsWith('/api/user/self')) {
          return jsonResponse(200, { success: true, data: { username: 'operator', quota: 35 * 500_000, used_quota: 10 * 500_000, group: 'default' } });
        }
        return jsonResponse(404, { success: false, message: 'unexpected endpoint' });
      },
    });

    try {
      const synced = await fixture.request('/api/admin/upstream-balance/sync', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(synced.status, 200);
      assert.equal(synced.json.ok, true);
      assert.equal(synced.json.balance.remainingCny, 35);
      assert.equal(synced.json.balance.level, 'warning');
      assert.equal(synced.json.balance.pauseRecommended, false);
      assert.equal(JSON.stringify(synced.json).includes('newapi-secret-token'), false);
      assert.equal(calls[0].authorization, 'Bearer newapi-secret-token');

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.upstreamBalance.remainingCny, 35);
      assert.equal(inventory.json.upstreamBalance.level, 'warning');
      assert.equal(JSON.stringify(inventory.json).includes('newapi-secret-token'), false);
    } finally {
      await fixture.close();
    }
  });

  it('syncs upstream channel multipliers with downstream markup for operator review', async () => {
    const fixture = await createServerFixture({ rateMarkup: 0.1 });

    try {
      const synced = await fixture.request('/api/admin/upstream-sync', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          source: 'reference-channel',
          channels: [
            { provider: '参考渠道', platform: 'Plus', model: 'gpt-5.5', status: 'healthy', multiplier: 0.18, latencyMs: 890 },
            { provider: '参考渠道', platform: 'Claude', model: 'claude-opus-4-6', status: 'degraded', multiplier: 0.33, latencyMs: 2100 },
          ],
        },
      });

      assert.equal(synced.status, 200);
      assert.equal(synced.json.rateMarkup, 0.1);
      assert.deepEqual(
        synced.json.channels.map((channel) => ({ model: channel.model, status: channel.status, upstreamMultiplier: channel.upstreamMultiplier, saleMultiplier: channel.saleMultiplier })),
        [
          { model: 'gpt-5.5', status: 'healthy', upstreamMultiplier: 0.18, saleMultiplier: 0.28 },
          { model: 'claude-opus-4-6-c', status: 'slow', upstreamMultiplier: 0.33, saleMultiplier: 0.43 },
        ],
      );
      assert.equal(synced.json.summary.healthy, 1);
      assert.equal(JSON.stringify(synced.json).includes('sk-'), false);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.channelSyncSummary.rateMarkup, 0.1);
      assert.equal(inventory.json.upstreamChannels[0].saleMultiplier, 0.28);
    } finally {
      await fixture.close();
    }
  });

  it('allocates a redemption card for a Xianyu order and marks fulfillment after redeem', async () => {
    const fixture = await createServerFixture({ publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1' });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, prefix: 'XY', note: '闲鱼自动发货批次' },
      });
      assert.equal(batch.status, 200);

      const fulfillment = await fixture.request('/api/admin/xianyu/fulfillments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          orderId: 'XY202607040001',
          buyerHint: '买家A',
          productTitle: 'Codex API 30刀额度/日卡',
          planId: 'codex-30-day',
        },
      });
      assert.equal(fulfillment.status, 200);
      assert.equal(fulfillment.json.fulfillment.status, 'delivered');
      assert.match(fulfillment.json.deliveryMessage, /兑换码：XY-/);
      assert.match(fulfillment.json.deliveryMessage, /https:\/\/jiyu\.245334\.xyz/);
      assert.match(fulfillment.json.deliveryMessage, /注册或登录账号/);
      assert.match(fulfillment.json.deliveryMessage, /进入“API Key”/);
      assert.match(fulfillment.json.deliveryMessage, /进入“CC Switch”/);
      assert.doesNotMatch(fulfillment.json.deliveryMessage, /jiyu\.245334\.xyz\/v1/);
      assert.equal(fulfillment.json.summary.availableCards, 0);
      assert.equal(fulfillment.json.summary.soldCards, 1);
      const deliveredCode = fulfillment.json.deliveryMessage.match(/兑换码：([A-Z0-9-]+)/)?.[1] || '';
      assert.match(deliveredCode, /^XY-/);
      const rawAfterFulfillment = await fixture.readRawData();
      assert.equal(rawAfterFulfillment.includes(deliveredCode), false, '闲鱼履约不能把完整卡密明文落库');

      const soldInventory = await fixture.request('/api/admin/redemption-cards', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      const soldCard = soldInventory.json.cards.find((card) => card.id === fulfillment.json.card.id);
      assert.equal(soldCard.status, 'sold');
      assert.equal(soldCard.soldOrderId, 'XY202607040001');

      const cookie = await fixture.createVerifiedCustomer('xianyu-buyer@example.com');
      const redeemed = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: deliveredCode },
      });
      assert.equal(redeemed.status, 200);
      assert.equal(redeemed.json.account.plan, '日卡');

      const after = await fixture.request('/api/admin/xianyu/fulfillments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(after.json.summary.redeemed, 1);
      assert.equal(after.json.fulfillments[0].status, 'redeemed');
      assert.equal(after.json.fulfillments[0].redeemedEmail, 'xi***@example.com');
    } finally {
      await fixture.close();
    }
  });

  it('accepts paid Xianyu orders through a low-scope auto-ship webhook only after payment is confirmed', async () => {
    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      xianyuWebhookToken: 'low-scope-xianyu-token',
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, prefix: 'XY', note: '闲鱼全自动发货批次' },
      });
      assert.equal(batch.status, 200);

      const noToken = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        body: { orderId: 'XY-AUTO-001', status: '等待卖家发货', paid: true },
      });
      assert.equal(noToken.status, 401);

      const unpaid = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: { orderId: 'XY-AUTO-001', status: '等待买家付款', paid: false },
      });
      assert.equal(unpaid.status, 409);
      assert.match(unpaid.json.error, /未确认已付款/);

      const paid = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: {
          orderId: 'XY-AUTO-001',
          status: '等待卖家发货',
          paid: true,
          productTitle: 'CC中转 日卡',
          buyerHint: '买家尾号001',
          planId: 'codex-30-day',
        },
      });
      assert.equal(paid.status, 200);
      assert.equal(paid.json.ok, true);
      assert.equal(paid.json.autoShip, true);
      assert.equal(paid.json.fulfillment.status, 'delivered');
      assert.match(paid.json.deliveryMessage, /兑换码：XY-/);

      const duplicate = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: { orderId: 'XY-AUTO-001', status: '买家已付款', paid: true },
      });
      assert.equal(duplicate.status, 200);
      assert.equal(duplicate.json.idempotent, true);
      assert.equal(duplicate.json.summary.soldCards, 1);
      assert.equal(duplicate.json.summary.availableCards, 0);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.xianyuAutomation.enabled, true);
      assert.equal(inventory.json.xianyuAutomation.authHeader, 'x-cc-xianyu-token');
      assert.equal(JSON.stringify(inventory.json.xianyuAutomation).includes('low-scope-xianyu-token'), false);
    } finally {
      await fixture.close();
    }
  });

  it('remaps a browser Xianyu fulfillment to a real order id without issuing another card', async () => {
    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      xianyuWebhookToken: 'low-scope-xianyu-token',
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, prefix: 'XY', note: '闲鱼真实订单接管批次' },
      });
      assert.equal(batch.status, 200);

      const paid = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: {
          orderId: 'xy_browser_old_order',
          status: '等待卖家发货',
          paid: true,
          productTitle: 'CC中转 日卡',
          buyerHint: '真实买家',
          planId: 'codex-30-day',
        },
      });
      assert.equal(paid.status, 200);
      assert.equal(paid.json.summary.soldCards, 1);
      assert.equal(paid.json.summary.availableCards, 0);

      const noToken = await fixture.request('/api/ops/xianyu/remap-order', {
        method: 'POST',
        body: { oldOrderId: 'xy_browser_old_order', newOrderId: 'xy_oid_real_order' },
      });
      assert.equal(noToken.status, 401);

      const remap = await fixture.request('/api/ops/xianyu/remap-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: { oldOrderId: 'xy_browser_old_order', newOrderId: 'xy_oid_real_order' },
      });
      assert.equal(remap.status, 200);
      assert.equal(remap.json.ok, true);
      assert.equal(remap.json.fulfillment.orderId, 'xy_oid_real_order');
      assert.equal(remap.json.card.soldOrderId, 'xy_oid_real_order');
      assert.equal(remap.json.summary.soldCards, 1);
      assert.equal(remap.json.summary.availableCards, 0);

      const duplicate = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: { orderId: 'xy_oid_real_order', status: '买家已付款', paid: true },
      });
      assert.equal(duplicate.status, 200);
      assert.equal(duplicate.json.idempotent, true);
      assert.equal(duplicate.json.summary.soldCards, 1);
      assert.equal(duplicate.json.summary.availableCards, 0);
    } finally {
      await fixture.close();
    }
  });

  it('allocates an unused Xianyu card even when the paid-order webhook has no plan id', async () => {
    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      xianyuWebhookToken: 'low-scope-xianyu-token',
    });

    try {
      const batch = await fixture.request('/api/admin/redemption-cards', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { planId: 'codex-30-day', quantity: 1, prefix: 'XY', note: '闲鱼无套餐订单发货批次' },
      });
      assert.equal(batch.status, 200);

      const paid = await fixture.request('/api/ops/xianyu/paid-order', {
        method: 'POST',
        headers: { 'x-cc-xianyu-token': 'low-scope-xianyu-token' },
        body: {
          orderId: 'XY-AUTO-NO-PLAN-001',
          status: '等待卖家发货',
          paid: true,
          productTitle: 'CC中转 日卡',
          buyerHint: '直接付款买家001',
        },
      });
      assert.equal(paid.status, 200);
      assert.equal(paid.json.fulfillment.status, 'delivered');
      assert.equal(paid.json.card.plan, 'day');
      assert.match(paid.json.deliveryMessage, /兑换码：XY-/);
      assert.equal(paid.json.summary.availableCards, 0);
      assert.equal(paid.json.summary.soldCards, 1);
    } finally {
      await fixture.close();
    }
  });

  it('expires day-card package quota before routing so old cards cannot keep using the day pool', async () => {
    let now = new Date('2026-05-01T12:00:00.000Z');
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      quotaCost: 500,
      nowFactory: () => now,
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push(options.headers?.Authorization || options.headers?.authorization);
        return jsonResponse(200, {
          id: 'chatcmpl-expired',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'expired' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('expired-day@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '过期日卡 Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      now = new Date('2026-05-03T12:00:00.000Z');
      const blocked = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'after expiry' }] },
      });
      assert.equal(blocked.status, 402);
      assert.equal(upstreamCalls.length, 0);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.plan, '默认套餐');
      assert.equal(dashboard.json.account.packageQuota, '$0.00');
    } finally {
      await fixture.close();
    }
  });

  it('probes supplier models once and filters invalid keys before writing replenishment inventory', async () => {
    const modelProbeCalls = [];
    const healthProbeCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        if (String(url).endsWith('/models')) {
          const authorization = options.headers?.Authorization || options.headers?.authorization;
          modelProbeCalls.push(authorization);
          if (authorization === 'Bearer sk-bad') {
            return jsonResponse(401, { error: { message: 'invalid api key' } });
          }
          return jsonResponse(200, {
            data: [{ id: 'claude-sonnet-4-5-c' }, { id: 'gpt-5.5' }],
          });
        }
        if (String(url).endsWith('/chat/completions')) {
          const authorization = options.headers?.Authorization || options.headers?.authorization;
          healthProbeCalls.push(authorization);
          if (authorization === 'Bearer sk-bad') {
            return jsonResponse(401, { error: { message: 'invalid api key' } });
          }
        }
        return jsonResponse(200, {
          id: 'chatcmpl-ok',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          keys: [
            { value: 'sk-good', quotaRemaining: 700, latencyMs: 90 },
            { value: 'sk-bad', quotaRemaining: 700, latencyMs: 90 },
          ],
          probeMode: 'strict',
        },
      });

      assert.equal(replenished.status, 200);
      assert.deepEqual(replenished.json.supplierProfile.models, ['claude-sonnet-4-5-c', 'gpt-5.5']);
      assert.equal(replenished.json.credentials.length, 1);
      assert.equal(replenished.json.credentials[0].keyPreview.endsWith('good'), true);
      assert.equal(replenished.json.failedKeys.length, 1);
      assert.match(replenished.json.failedKeys[0].reason, /认证失败/);
      assert.deepEqual(modelProbeCalls, ['Bearer sk-good']);
      assert.deepEqual(healthProbeCalls, ['Bearer sk-good', 'Bearer sk-bad']);
    } finally {
      await fixture.close();
    }
  });

  it('parses pasted supplier order details and replenishes inventory without returning raw upstream keys', async () => {
    const fixture = await createServerFixture();
    const orderText = `
      商品名称: CodexAPI 30刀额度 日卡
      订单金额: ￥3.87
      数量: 2
      密码：cr_fakeorder111111111111111111111111111111111111111111111111111111
      密码：cr_fakeorder222222222222222222222222222222222222222222222222222222
      模型：gpt-5.4、gpt-5.5、gpt-image-2模型
      地址: https://supplier-codex.example.com/openai
    `;

    try {
      const parsed = await fixture.request('/api/admin/replenishments/parse-order', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { orderText },
      });
      assert.equal(parsed.status, 200);
      assert.equal(parsed.json.baseUrl, 'https://supplier-codex.example.com/openai');
      assert.equal(parsed.json.pool, 'day');
      assert.deepEqual(parsed.json.models, ['gpt-5.4', 'gpt-5.5', 'gpt-image-2']);
      assert.equal(parsed.json.keyPreviews.length, 2);
      assert.equal(JSON.stringify(parsed.json).includes('cr_fakeorder111111'), false);

      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { orderText, probeMode: 'trusted' },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.length, 2);
      assert.equal(replenished.json.supplierProfile.baseUrl, 'https://supplier-codex.example.com/openai');
      assert.equal(replenished.json.credentials[0].pool, 'day');
      assert.equal(replenished.json.credentials[0].quotaRemaining, 21600);
      assert.equal(JSON.stringify(replenished.json).includes('cr_fakeorder111111'), false);
    } finally {
      await fixture.close();
    }
  });

  it('routes root supplier URLs through /v1 when the root path returns a website shell', async () => {
    const probeUrls = [];
    const gatewayUrls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const targetUrl = String(url);
        const body = options.body ? JSON.parse(options.body) : {};
        probeUrls.push(targetUrl);
        if (targetUrl === 'https://supplier.example.com/chat/completions') {
          return textResponse(200, '<!doctype html><main>balance dashboard</main>');
        }
        if (targetUrl === 'https://supplier.example.com/v1/chat/completions') {
          if (body.messages?.[0]?.content === 'customer request') {
            gatewayUrls.push(targetUrl);
          }
          return jsonResponse(200, {
            id: 'chatcmpl-v1',
            object: 'chat.completion',
            model: body.model || 'gpt-5.5',
            choices: [{ message: { role: 'assistant', content: 'ok' } }],
            usage: { prompt_tokens: 2, completion_tokens: 1, total_tokens: 3 },
          });
        }
        return jsonResponse(404, { error: { message: 'not found' } });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com',
          pool: 'unlimited',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-root-html', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials[0].status, 'healthy');
      assert.equal(replenished.json.credentials[0].lastProbeStatus, 'chat_probe_ok');
      assert.deepEqual(probeUrls.slice(0, 2), [
        'https://supplier.example.com/chat/completions',
        'https://supplier.example.com/v1/chat/completions',
      ]);

      const cookie = await fixture.createVerifiedCustomer('root-v1-route@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '根路径自愈 Key', modelGroup: 'OpenAI' },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'customer request' }],
        },
      });

      assert.equal(response.status, 200);
      assert.equal(response.json.choices[0].message.content, 'ok');
      assert.deepEqual(gatewayUrls, ['https://supplier.example.com/v1/chat/completions']);
    } finally {
      await fixture.close();
    }
  });

  it('probes native Claude Messages supplier stock and routes Claude Code through the same path', async () => {
    const probeUrls = [];
    const gatewayUrls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const targetUrl = String(url);
        const body = options.body ? JSON.parse(options.body) : {};
        probeUrls.push(targetUrl);
        if (targetUrl === 'https://supplier.example.com/v1/messages') {
          if (body.messages?.[0]?.content === 'customer request') {
            gatewayUrls.push(targetUrl);
          }
          return jsonResponse(200, {
            id: 'msg-claude-native',
            type: 'message',
            role: 'assistant',
            model: body.model || 'claude-sonnet-4-5-c',
            content: [{ type: 'text', text: 'ok' }],
            usage: { input_tokens: 2, output_tokens: 1 },
          });
        }
        return jsonResponse(404, { error: { message: 'not found' } });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com',
          pool: 'day',
          modelGroup: 'Claude',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-claude-native-probe', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials[0].status, 'healthy');
      assert.equal(replenished.json.credentials[0].lastProbeStatus, 'anthropic_messages_probe_ok');
      assert.deepEqual(probeUrls.slice(0, 2), [
        'https://supplier.example.com/messages',
        'https://supplier.example.com/v1/messages',
      ]);

      const cookie = await fixture.createVerifiedCustomer('native-claude-probe@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '原生 Claude Key', modelGroup: 'Claude' },
      });

      const response = await fixture.request('/v1/messages', {
        method: 'POST',
        headers: { 'x-api-key': token.json.key.secret },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'customer request' }],
          max_tokens: 32,
        },
      });

      assert.equal(response.status, 200);
      assert.equal(response.json.content[0].text, 'ok');
      assert.deepEqual(gatewayUrls, ['https://supplier.example.com/v1/messages']);
    } finally {
      await fixture.close();
    }
  });

  it('keeps the replenishment model group when object-form keys omit per-key groups', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-group',
          model: 'gpt-5.4-mini',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
          usage: { prompt_tokens: 2, completion_tokens: 1, total_tokens: 3 },
        }),
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          modelGroup: 'OpenAI',
          models: ['gpt-5.4-mini'],
          keys: [{ value: 'sk-openai-no-key-group', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      });

      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials[0].modelGroup, 'OpenAI');
      assert.equal(replenished.json.supplierProfile.modelGroup, 'OpenAI');
    } finally {
      await fixture.close();
    }
  });

  it('keeps separate inventory records when one upstream key serves Claude and OpenAI groups', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const targetUrl = String(url);
        const body = options.body ? JSON.parse(options.body) : {};
        if (body.messages?.[0]?.content === 'claude customer') {
          upstreamCalls.push({ url: targetUrl, model: body.model });
        }
        if (body.messages?.[0]?.content === 'openai customer') {
          upstreamCalls.push({ url: targetUrl, model: body.model });
        }
        if (targetUrl.endsWith('/messages')) {
          return jsonResponse(200, {
            id: 'msg-shared-key',
            type: 'message',
            role: 'assistant',
            model: body.model || 'claude-sonnet-4-5-c',
            content: [{ type: 'text', text: 'claude ok' }],
            usage: { input_tokens: 2, output_tokens: 1 },
          });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-shared-key',
          model: body.model || 'gpt-5.4-mini',
          choices: [{ message: { role: 'assistant', content: 'openai ok' } }],
          usage: { prompt_tokens: 2, completion_tokens: 1, total_tokens: 3 },
        });
      },
    });

    try {
      for (const body of [
        {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          modelGroup: 'Claude',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-shared-upstream', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
        {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          modelGroup: 'OpenAI',
          models: ['gpt-5.4-mini'],
          keys: [{ value: 'sk-shared-upstream', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      ]) {
        const replenished = await fixture.request('/api/admin/replenishments', {
          method: 'POST',
          headers: { 'x-admin-token': 'admin-test-token' },
          body,
        });
        assert.equal(replenished.status, 200);
        assert.equal(replenished.json.credentials.length, 1);
      }

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.deepEqual(
        inventory.json.credentials.map((credential) => credential.modelGroup).sort(),
        ['Claude', 'OpenAI'],
      );

      const cookie = await fixture.createVerifiedCustomer('shared-key-groups@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const claudeToken = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Claude shared upstream', modelGroup: 'Claude' },
      });
      const openAiToken = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'OpenAI shared upstream', modelGroup: 'OpenAI' },
      });

      const claude = await fixture.request('/v1/messages', {
        method: 'POST',
        headers: { 'x-api-key': claudeToken.json.key.secret },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'claude customer' }],
          max_tokens: 32,
        },
      });
      const openai = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${openAiToken.json.key.secret}` },
        body: {
          model: 'gpt-5.4-mini',
          messages: [{ role: 'user', content: 'openai customer' }],
        },
      });

      assert.equal(claude.status, 200);
      assert.equal(openai.status, 200);
      assert.deepEqual(upstreamCalls, [
        { url: 'https://supplier.example.com/v1/messages', model: 'claude-sonnet-4-5-c' },
        { url: 'https://supplier.example.com/v1/chat/completions', model: 'gpt-5.4-mini' },
      ]);
    } finally {
      await fixture.close();
    }
  });

  it('selects the matching customer key when exporting CC Switch links for a model group', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const targetUrl = String(url);
        const body = options.body ? JSON.parse(options.body) : {};
        if (targetUrl.endsWith('/messages')) {
          return jsonResponse(200, {
            id: 'msg-export-group',
            type: 'message',
            role: 'assistant',
            model: body.model || 'claude-sonnet-4-5-c',
            content: [{ type: 'text', text: 'ok' }],
          });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-export-group',
          model: body.model || 'gpt-5.4-mini',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('export-groups@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          modelGroup: 'Claude',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-export-claude', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          modelGroup: 'OpenAI',
          models: ['gpt-5.4-mini'],
          keys: [{ value: 'sk-export-openai', quotaRemaining: 900, latencyMs: 80 }],
          probeMode: 'strict',
        },
      });
      const claudeToken = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '导出 Claude Key', modelGroup: 'Claude' },
      });
      const openAiToken = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '导出 OpenAI Key', modelGroup: 'OpenAI' },
      });

      const claudeImport = await fixture.request(
        '/api/frist/import-url?target=Claude&modelGroup=Claude&model=claude-sonnet-4-5-c',
        { cookie },
      );
      const codexImport = await fixture.request(
        '/api/frist/import-url?target=Codex&modelGroup=OpenAI&model=gpt-5.4-mini',
        { cookie },
      );
      const claudeUrl = new URL(claudeImport.json.url);
      const codexUrl = new URL(codexImport.json.url);

      assert.equal(claudeUrl.searchParams.get('apiKey'), claudeToken.json.key.secret);
      assert.equal(claudeUrl.searchParams.get('model'), 'claude-sonnet-4-5-c');
      assert.deepEqual(claudeImport.json.availableModels, ['claude-sonnet-4-5-c']);
      assert.equal(codexUrl.searchParams.get('apiKey'), openAiToken.json.key.secret);
      assert.equal(codexUrl.searchParams.get('model'), 'gpt-5.4-mini');
      assert.deepEqual(codexImport.json.availableModels, ['gpt-5.4-mini']);
    } finally {
      await fixture.close();
    }
  });

  it('aggregates customer channel checks by card merchant channel instead of exposing one card per upstream key', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [
            { value: 'sk-model-a', quotaRemaining: 900, latencyMs: 120 },
            { value: 'sk-model-b', quotaRemaining: 900, latencyMs: 80 },
          ],
        },
      });

      const cookie = await fixture.createVerifiedCustomer();
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.status, 200);
      assert.equal(dashboard.json.channelChecks.length, 1);
      assert.equal(dashboard.json.channelChecks[0].model, 'claude-sonnet-4-5-c');
      assert.equal(dashboard.json.channelChecks[0].ok, true);
      assert.equal(dashboard.json.channelChecks[0].channel, '卡商1');
      assert.equal(dashboard.json.channelChecks[0].poolLabel, '日卡号池');
      assert.equal(dashboard.json.channelChecks[0].pool, 'day');
      assert.equal(dashboard.json.channelChecks[0].healthyCount, 2);
      assert.equal(dashboard.json.channelChecks[0].totalCount, 2);
      assert.equal(dashboard.json.channelChecks[0].downCount, 0);
      assert.equal(dashboard.json.channelChecks[0].monitorStatus, '正常');
      assert.equal(dashboard.json.channelChecks[0].successLabel, '2/2 可用');
      assert.equal(dashboard.json.channelChecks[0].availability7d, 100);
      assert.equal(dashboard.json.channelChecks[0].availabilityWindow, '当前库存快照');
      assert.equal(dashboard.json.channelChecks[0].monitorIntervalSeconds, 60);
      assert.match(dashboard.json.channelChecks[0].latencyLabel, /最低 80ms \/ 平均 100ms/);
      assert.deepEqual(dashboard.json.channelChecks[0].history, ['ok', 'ok']);
      assert.equal(JSON.stringify(dashboard.json.channelChecks).includes('supplier.example.com'), false);
      assert.equal(JSON.stringify(dashboard.json.channelChecks).includes('sk-model-a'), false);
    } finally {
      await fixture.close();
    }
  });

  it('marks channel checks as degraded when some approved inventory is slow or down', async () => {
    const fixture = await createServerFixture();

    try {
      const sourceId = 'source-degraded';
      await fixture.writeData({
        supplierProfiles: [
          {
            id: sourceId,
            pool: 'day',
            models: ['gpt-5.5'],
            modelGroup: 'OpenAI',
            sourceType: 'authorized',
            riskStatus: 'approved',
          },
        ],
        credentials: [
          {
            id: 'fast',
            sourceId,
            pool: 'day',
            models: ['gpt-5.5'],
            sourceType: 'authorized',
            riskStatus: 'approved',
            backupRiskAccepted: false,
            enabled: true,
            status: 'healthy',
            latencyMs: 90,
            updatedAt: '2026-05-06T10:00:00.000Z',
          },
          {
            id: 'slow',
            sourceId,
            pool: 'day',
            models: ['gpt-5.5'],
            sourceType: 'authorized',
            riskStatus: 'approved',
            backupRiskAccepted: false,
            enabled: true,
            status: 'healthy',
            latencyMs: 1900,
            updatedAt: '2026-05-06T10:01:00.000Z',
          },
          {
            id: 'down',
            sourceId,
            pool: 'day',
            models: ['gpt-5.5'],
            sourceType: 'authorized',
            riskStatus: 'approved',
            backupRiskAccepted: false,
            enabled: false,
            status: 'failed',
            latencyMs: 0,
            updatedAt: '2026-05-06T10:02:00.000Z',
          },
        ],
      });

      const cookie = await fixture.createVerifiedCustomer();
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      const [check] = dashboard.json.channelChecks;
      assert.equal(check.model, 'gpt-5.5');
      assert.equal(check.channel, '卡商1');
      assert.equal(check.poolLabel, '日卡号池');
      assert.equal(check.healthyCount, 2);
      assert.equal(check.totalCount, 3);
      assert.equal(check.downCount, 1);
      assert.equal(check.slowCount, 1);
      assert.equal(check.monitorStatus, '降级');
      assert.equal(check.officialStatus, '降级');
      assert.equal(check.availability, '66.7%');
      assert.equal(check.availability7d, 66.7);
      assert.equal(check.latencyMs, 90);
      assert.equal(check.averageLatencyMs, 995);
      assert.equal(check.successLabel, '2/3 可用');
      assert.equal(check.monitorIntervalSeconds, 60);
      assert.deepEqual(check.history, ['ok', 'slow', 'down']);
    } finally {
      await fixture.close();
    }
  });

  it('keeps channel cards grouped by pool while model catalog availability stays per model', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['gpt-5.5', 'gpt-image-2'],
          keys: [{ value: 'sk-pool-models', quotaRemaining: 900, latencyMs: 120 }],
        },
      });

      const cookie = await fixture.createVerifiedCustomer('pool-catalog@example.com');
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      const channelNames = dashboard.json.channelChecks.map((item) => item.channel);
      const catalogByModel = new Map(dashboard.json.modelCatalog.map((item) => [item.model, item]));

      assert.deepEqual(channelNames, ['卡商1']);
      assert.equal(catalogByModel.get('gpt-5.5')?.available, true);
      assert.equal(catalogByModel.get('gpt-image-2')?.available, true);
      assert.equal(JSON.stringify(dashboard.json.channelChecks).includes('可用线路'), false);
    } finally {
      await fixture.close();
    }
  });

  it('does not invent latency for trusted inventory before a real probe or gateway call', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://trusted.example.com/v1',
          pool: 'day',
          probeMode: 'trusted',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-trusted-no-latency', quotaRemaining: 900 }],
        },
      });

      const cookie = await fixture.createVerifiedCustomer('trusted-latency@example.com');
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      const [check] = dashboard.json.channelChecks;

      assert.equal(check.channel, '卡商1');
      assert.equal(check.poolLabel, '日卡号池');
      assert.equal(check.latencyMs, 0);
      assert.equal(check.averageLatencyMs, 0);
      assert.equal(check.latencyLabel, '等待真实请求更新');
      assert.equal(check.monitorIntervalSeconds, 60);
    } finally {
      await fixture.close();
    }
  });

  it('lets admins replenish day-card credentials and routes user gateway calls to the healthy key', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
        });
        return jsonResponse(200, {
          id: 'chatcmpl-ok',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '日卡 Key' },
      });
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });

      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [
            { value: 'sk-empty', quotaRemaining: 1, latencyMs: 90 },
            { value: 'sk-healthy', quotaRemaining: 900, latencyMs: 120 },
          ],
          priceText: 'claude-sonnet-4-5-c input $3/1M output $15/1M',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.length, 2);
      assert.equal(JSON.stringify(replenished.json).includes('sk-healthy'), false);

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      assert.equal(gateway.status, 200);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-healthy');

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.status, 200);
      assert.equal(inventory.json.credentials.find((item) => item.keyPreview.endsWith('mpty')).status, 'exhausted');
      assert.equal(inventory.json.credentials.find((item) => item.keyPreview.endsWith('lthy')).quotaRemaining, 890);
    } finally {
      await fixture.close();
    }
  });

  it('keeps CPA JSON and chong backup sources behind manual risk approval', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push({
          url: String(url),
          authorization: options.headers?.Authorization || options.headers?.authorization,
        });
        return jsonResponse(200, {
          id: 'chatcmpl-backup-ok',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'backup ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('backup-risk@example.com');
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '备用渠道 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });

      const quarantined = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://backup.example.com/v1',
          pool: 'day',
          probeMode: 'trusted',
          sourceType: 'cpa_json_backup',
          riskStatus: 'quarantined',
          backupRiskAccepted: false,
          riskNote: '人工未放行，只登记备用库存',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-cpa-risk', quotaRemaining: 900, quotaTotal: 900 }],
        },
      });
      assert.equal(quarantined.status, 200);
      assert.equal(quarantined.json.credentials[0].sourceType, 'cpa_json_backup');
      assert.equal(quarantined.json.credentials[0].riskStatus, 'quarantined');
      assert.equal(quarantined.json.credentials[0].status, 'quarantined');
      assert.equal(quarantined.json.credentials[0].enabled, false);

      const hiddenModels = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });
      assert.equal(hiddenModels.status, 200);
      assert.deepEqual(hiddenModels.json.data, []);

      const blockedGateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      assert.equal(blockedGateway.status, 503);
      assert.equal(upstreamCalls.length, 0);

      const approved = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://backup.example.com/v1',
          pool: 'day',
          probeMode: 'trusted',
          sourceType: 'chong_backup',
          riskStatus: 'approved',
          backupRiskAccepted: true,
          riskNote: '人工确认只作为备用渠道',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-chong-approved', quotaRemaining: 900, quotaTotal: 900 }],
        },
      });
      assert.equal(approved.status, 200);
      assert.equal(approved.json.credentials[0].sourceType, 'chong_backup');
      assert.equal(approved.json.credentials[0].riskStatus, 'approved');
      assert.equal(approved.json.credentials[0].status, 'healthy');
      assert.equal(approved.json.credentials[0].enabled, true);

      const visibleModels = await fixture.request('/v1/models', {
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
      });
      assert.deepEqual(visibleModels.json.data.map((item) => item.id), ['gpt-5.5']);

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 8,
        },
      });
      assert.equal(gateway.status, 200);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-chong-approved');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(JSON.stringify(dashboard.json).includes('cpa_json_backup'), false);
      assert.equal(JSON.stringify(dashboard.json).includes('chong_backup'), false);
    } finally {
      await fixture.close();
    }
  });

  it('uses expiring stock first and falls back to unlimited inventory when day cards run out', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      quotaCost: 10,
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push(options.headers?.Authorization || options.headers?.authorization);
        return jsonResponse(200, {
          id: 'chatcmpl-pool-priority',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('priority@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '优先级 Key', modelGroup: 'OpenAI' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'unlimited',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-unlimited-fast', quotaRemaining: 900, quotaTotal: 900, latencyMs: 20 }],
        },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/day',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-day-expiring', quotaRemaining: 10, quotaTotal: 100, latencyMs: 200 }],
        },
      });

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}`, 'x-frist-session-id': 'pool-a' },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'first' }] },
      });
      assert.equal(first.status, 200);

      const second = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}`, 'x-frist-session-id': 'pool-b' },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'second' }] },
      });
      assert.equal(second.status, 200);
      assert.deepEqual(upstreamCalls, ['Bearer sk-day-expiring', 'Bearer sk-unlimited-fast']);
    } finally {
      await fixture.close();
    }
  });

  it('notifies operators when compatible inventory drops under the low-stock threshold', async () => {
    const notifications = [];
    const fixture = await createServerFixture({
      quotaCost: 10,
      lowInventoryThresholdRatio: 0.05,
      notifyLowInventory: (payload) => notifications.push(payload),
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-low-stock',
          model: 'gpt-5.5',
          choices: [{ message: { role: 'assistant', content: 'ok' } }],
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('low-stock@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '低库存 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/openai',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-low-stock', quotaRemaining: 20, quotaTotal: 200, latencyMs: 80 }],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'use stock' }] },
      });
      assert.equal(response.status, 200);
      assert.equal(notifications.length, 1);
      assert.equal(notifications[0].pool, 'day');
      assert.equal(notifications[0].providerGroup, 'OpenAI');
      assert.equal(notifications[0].remainingRatio <= 0.05, true);
    } finally {
      await fixture.close();
    }
  });

  it('runs background channel monitoring every interval, downgrades invalid keys and only notifies once', async () => {
    const keyAlerts = [];
    const upstreamCalls = [];
    const fetchImpl = async (url, options = {}) => {
      const authorization = options.headers?.Authorization || options.headers?.authorization || '';
      upstreamCalls.push(authorization);
      if (authorization === 'Bearer sk-bad') {
        return jsonResponse(401, { error: { message: 'invalid api key' } });
      }
      return jsonResponse(200, {
        id: 'chatcmpl-monitor-ok',
        model: 'gpt-5.5',
        choices: [{ message: { role: 'assistant', content: 'ok' } }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      });
    };
    const fixture = await createServerFixture({
      fetchImpl,
      channelMonitorEnabled: true,
      channelMonitorIntervalMs: 25,
      channelMonitorBatchSize: 2,
      channelMonitorCooldownMs: 0,
      notifyCredentialIssue: (payload) => keyAlerts.push(payload),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('monitor@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '巡检降级 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          probeMode: 'trusted',
          models: ['gpt-5.5'],
          keys: [
            { value: 'sk-bad', quotaRemaining: 800, quotaTotal: 800 },
            { value: 'sk-good', quotaRemaining: 900, quotaTotal: 900 },
          ],
        },
      });

      let degradedCredential = null;
      for (let index = 0; index < 40; index += 1) {
        const runtime = await fixture.readData();
        degradedCredential = runtime.credentials.find((item) => item.rawKey === 'sk-bad') || null;
        if (degradedCredential && degradedCredential.status === 'failed' && degradedCredential.enabled === false) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      assert.equal(Boolean(degradedCredential), true);
      assert.equal(degradedCredential.status, 'failed');
      assert.equal(degradedCredential.enabled, false);
      assert.equal(keyAlerts.length, 1);
      assert.equal(keyAlerts[0].issueType, 'auth');
      assert.equal(keyAlerts[0].keyPreview.endsWith('bad'), true);

      await new Promise((resolve) => setTimeout(resolve, 120));
      assert.equal(keyAlerts.length, 1, '同一个失效 Key 应该只提醒一次补号');

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}`, 'x-frist-session-id': 'monitor-fallback' },
        body: { model: 'gpt-5.5', messages: [{ role: 'user', content: 'still works' }] },
      });
      assert.equal(response.status, 200);
      assert.equal(upstreamCalls.some((value) => value === 'Bearer sk-good'), true);
    } finally {
      await fixture.close();
    }
  });

  it('retries the next day-card key when an upstream reports quota exhaustion, then accepts replenishment', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const authorization = options.headers?.Authorization || options.headers?.authorization;
        upstreamCalls.push(authorization);
        if (authorization === 'Bearer sk-first') {
          return jsonResponse(402, { error: { message: 'insufficient quota' } });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-after-switch',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'switched' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '自动切换 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [
            { value: 'sk-first', quotaRemaining: 900, latencyMs: 80 },
            { value: 'sk-second', quotaRemaining: 900, latencyMs: 120 },
          ],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'ping' }],
        },
      });
      assert.equal(response.status, 200);
      assert.deepEqual(upstreamCalls, ['Bearer sk-first', 'Bearer sk-second']);

      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-third', quotaRemaining: 500, latencyMs: 70 }],
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.some((item) => item.keyPreview.endsWith('hird')), true);
    } finally {
      await fixture.close();
    }
  });

  it('fails over to the next day-card key when the fastest upstream is temporarily unavailable', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const authorization = options.headers?.Authorization || options.headers?.authorization;
        upstreamCalls.push(authorization);
        if (authorization === 'Bearer sk-unstable') {
          return jsonResponse(503, { error: { message: 'upstream unavailable' } });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-failover',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'failover' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '故障切换 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [
            { value: 'sk-unstable', quotaRemaining: 900, latencyMs: 50 },
            { value: 'sk-backup', quotaRemaining: 900, latencyMs: 120 },
          ],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'ping' }],
        },
      });
      assert.equal(response.status, 200);
      assert.deepEqual(upstreamCalls, ['Bearer sk-unstable', 'Bearer sk-backup']);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.credentials.find((item) => item.keyPreview.endsWith('able')).status, 'failed');
      assert.equal(inventory.json.credentials.find((item) => item.keyPreview.endsWith('ckup')).status, 'healthy');
    } finally {
      await fixture.close();
    }
  });

  it('keeps the same healthy upstream for one explicit conversation session', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : {};
        upstreamCalls.push({
          authorization: options.headers?.Authorization || options.headers?.authorization,
          content: body.messages?.at(-1)?.content || '',
        });
        return jsonResponse(200, {
          id: 'chatcmpl-sticky',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'sticky' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('sticky-session@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '会话粘滞 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-stable', quotaRemaining: 900, latencyMs: 120 }],
        },
      });

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-alpha',
        },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'first turn' }] },
      });
      assert.equal(first.status, 200);

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-faster', quotaRemaining: 900, latencyMs: 20 }],
        },
      });

      const secondSameConversation = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-alpha',
        },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'second turn' }] },
      });
      assert.equal(secondSameConversation.status, 200);

      const otherConversation = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-beta',
        },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'new conversation' }] },
      });
      assert.equal(otherConversation.status, 200);

      assert.deepEqual(
        upstreamCalls.map((call) => call.authorization),
        ['Bearer sk-stable', 'Bearer sk-stable', 'Bearer sk-faster'],
      );
      assert.deepEqual(
        upstreamCalls.map((call) => call.content),
        ['first turn', 'second turn', 'new conversation'],
      );
    } finally {
      await fixture.close();
    }
  });

  it('forwards the original full chat body when failover moves a session to backup inventory', async () => {
    const upstreamBodies = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const authorization = options.headers?.Authorization || options.headers?.authorization;
        upstreamBodies.push(JSON.parse(options.body));
        if (authorization === 'Bearer sk-context-bad') {
          return jsonResponse(503, { error: { message: 'temporary unavailable' } });
        }
        return jsonResponse(200, {
          id: 'chatcmpl-context-failover',
          model: 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'context kept' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('context-failover@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '上下文切换 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [
            { value: 'sk-context-bad', quotaRemaining: 900, latencyMs: 30 },
            { value: 'sk-context-good', quotaRemaining: 900, latencyMs: 90 },
          ],
        },
      });

      const fullBody = {
        model: 'claude-sonnet-4-5-c',
        messages: [
          { role: 'system', content: 'keep system prompt' },
          { role: 'user', content: 'first user turn' },
          { role: 'assistant', content: 'assistant memory' },
          { role: 'user', content: [{ type: 'text', text: 'second user turn' }] },
        ],
        temperature: 0.2,
        tools: [{ type: 'function', function: { name: 'lookup_order', parameters: { type: 'object' } } }],
        metadata: { frist_session_id: 'metadata-session' },
      };

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: fullBody,
      });
      assert.equal(response.status, 200);
      assert.equal(upstreamBodies.length, 2);
      assert.deepEqual(upstreamBodies[0], fullBody);
      assert.deepEqual(upstreamBodies[1], fullBody);
    } finally {
      await fixture.close();
    }
  });

  it('passes streaming gateway responses through before the upstream stream finishes', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode('data: {"delta":"first"}\n\n'));
              setTimeout(() => {
                controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
                controller.close();
              }, 180);
            },
          }),
          {
            status: 200,
            headers: { 'content-type': 'text/event-stream; charset=utf-8' },
          },
        ),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('streaming@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '流式 Key' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-stream', quotaRemaining: 900, latencyMs: 50 }],
        },
      });

      const startedAt = Date.now();
      const response = await fetch(`${fixture.baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${token.json.key.secret}`,
          'content-type': 'application/json',
          'x-frist-session-id': 'stream-alpha',
        },
        body: JSON.stringify({
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'stream this' }],
          stream: true,
        }),
      });
      assert.equal(response.status, 200);
      assert.match(response.headers.get('content-type') || '', /text\/event-stream/);
      const reader = response.body.getReader();
      const firstChunk = await reader.read();
      assert.equal(firstChunk.done, false);
      assert.match(new TextDecoder().decode(firstChunk.value), /first/);
      assert.equal(Date.now() - startedAt < 120, true);
      await reader.cancel();
    } finally {
      await fixture.close();
    }
  });

  it('restores an exhausted day-card credential when the same upstream key is replenished again', async () => {
    const upstreamCalls = [];
    const fixture = await createServerFixture({
      quotaCost: 10,
      fetchImpl: async (url, options = {}) => {
        upstreamCalls.push(options.headers?.Authorization || options.headers?.authorization);
        return jsonResponse(200, {
          id: 'chatcmpl-restored',
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'restored' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '可恢复 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-restore', quotaRemaining: 10, latencyMs: 90 }],
        },
      });
      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-sonnet-4-5-c', messages: [{ role: 'user', content: 'first' }] },
      });
      assert.equal(first.status, 200);

      const exhausted = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(exhausted.json.credentials.length, 1);
      assert.equal(exhausted.json.credentials[0].status, 'exhausted');

      const restored = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-restore', quotaRemaining: 500, latencyMs: 70 }],
        },
      });
      assert.equal(restored.status, 200);
      assert.equal(restored.json.credentials.length, 1);
      assert.equal(restored.json.credentials[0].status, 'healthy');
      assert.equal(restored.json.credentials[0].quotaRemaining, 500);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.credentials.length, 1);
      assert.equal(inventory.json.credentials[0].quotaRemaining, 500);
    } finally {
      await fixture.close();
    }
  });

  it('uses confirmed official model pricing and upstream usage to bill gateway calls', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-priced',
          model: 'claude-sonnet-4-5-c',
          usage: {
            prompt_tokens: 1_000_000,
            completion_tokens: 500_000,
          },
          choices: [{ message: { role: 'assistant', content: 'priced' } }],
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('priced@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '按量计费 Key' },
      });

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-priced', quotaRemaining: 1000, latencyMs: 80 }],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'priced request' }],
        },
      });
      assert.equal(response.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.packageQuota, '$0.00');
      assert.equal(dashboard.json.account.todayCost, '$10.50');

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.credentials[0].quotaRemaining, 0);
    } finally {
      await fixture.close();
    }
  });

  it('returns customer usage records, recent logs and performance counters for the workbench shell', async () => {
    const fixture = await createServerFixture({
      quotaCost: 125,
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-records',
          model: 'gpt-5.5',
          usage: {
            prompt_tokens: 1200,
            completion_tokens: 345,
            total_tokens: 1545,
          },
          choices: [{ message: { role: 'assistant', content: 'records ok' } }],
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('records@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '记录 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-records', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          reasoning_effort: 'high',
          messages: [{ role: 'user', content: 'records' }],
        },
      });
      assert.equal(response.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.todayCalls, '1 次');
      assert.equal(dashboard.json.account.todayTokens, '1.5K');
      assert.equal(dashboard.json.account.totalTokens, '1.5K');
      assert.match(dashboard.json.account.averageLatency, /^\d+ms$/);
      assert.equal(dashboard.json.account.successRate, '100%');
      assert.equal(dashboard.json.usageRecords.length, 1);
      assert.equal(dashboard.json.usageRecords[0].apiKey, token.json.key.preview);
      assert.equal(dashboard.json.usageRecords[0].model, 'gpt-5.5');
      assert.equal(dashboard.json.usageRecords[0].inferenceEffort, 'high');
      assert.equal(dashboard.json.usageRecords[0].endpoint, 'https://supplier.example.com/v1');
      assert.equal(dashboard.json.usageRecords[0].type, '文本');
      assert.equal(dashboard.json.usageRecords[0].billingMode, '套餐');
      assert.equal(dashboard.json.usageRecords[0].tokens, '1.5K');
      assert.match(dashboard.json.usageRecords[0].amount, /^\$\d+\.\d{2}$/);
      assert.ok(dashboard.json.recentLogs.some((item) => item.type === 'gateway_routed'));
    } finally {
      await fixture.close();
    }
  });

  it('returns lightweight usage anomaly alerts for customer dashboards', async () => {
    const fixture = await createServerFixture({
      quotaCost: 500,
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-anomaly',
          model: 'gpt-5.5',
          usage: {
            prompt_tokens: 90000,
            completion_tokens: 250000,
            total_tokens: 340000,
          },
          choices: [{ message: { role: 'assistant', content: 'anomaly ok' } }],
        }),
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('usage-anomaly@example.com');
      await fixture.request('/api/admin/customers/recharge', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { email: 'usage-anomaly@example.com', amountCny: 80, method: 'manual_confirmed' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '异常 Key', modelGroup: 'OpenAI' },
      });
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'default',
          models: ['gpt-5.5'],
          keys: [{ value: 'sk-anomaly', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'anomaly' }],
        },
      });
      assert.equal(response.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.usageAnomalies.length >= 1, true);
      assert.ok(dashboard.json.usageAnomalies.some((item) => item.title === '今日消耗偏高'));
      assert.ok(dashboard.json.usageAnomalies.some((item) => /今日已用|单次消耗/.test(item.detail)));
      assert.equal(JSON.stringify(dashboard.json.usageAnomalies).includes('sk-anomaly'), false);
    } finally {
      await fixture.close();
    }
  });

  it('uses New-API business endpoints for dashboard, token management, import and gateway when enabled', async () => {
    const newApiCalls = [];
    let newApiTokenStatus = 1;
    let newApiTokenCreated = false;
    let newApiTokenQuota = 0;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      newApiGatewayEnabled: true,
      newApiGatewayBaseUrl: 'https://new-api.internal/v1',
      fetchImpl: async (url, init = {}) => {
        newApiCalls.push({ url: String(url), init });
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (String(url).startsWith('https://new-api.internal/api/')) {
          assert.equal(init.headers.Authorization, 'Bearer newapi-access-token');
          assert.equal(init.headers['New-Api-User'], '42');
        }
        if (path === '/api/user/self') {
          return jsonResponse(200, {
            success: true,
            data: {
              email: 'newapi@example.com',
              username: 'newapi-user',
              group: 'pro',
              quota: 7200,
              used_quota: 14400,
              request_count: 8,
            },
          });
        }
        if (path === '/api/models/') {
          return jsonResponse(200, {
            success: true,
            data: {
              items: [
                { model_name: 'deepseek-v4-flash' },
                { model_name: 'deepseek-v4-pro' },
                { model_name: 'deepseek-chat' },
                { model_name: 'deepseek-reasoner' },
                { model_name: 'gpt-5.5' },
              ],
            },
          });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          const body = JSON.parse(init.body);
          assert.equal(body.name, 'Codex NewAPI Key');
          assert.equal(body.unlimited_quota, false);
          assert.equal(body.remain_quota, 0);
          assert.equal(body.model_limits_enabled, true);
          assert.equal(body.model_limits, 'deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner');
          newApiTokenCreated = true;
          newApiTokenQuota = body.remain_quota;
          return jsonResponse(200, {
            success: true,
            data: {
              id: 9,
              ...body,
              key: 'sk-newapi-full-secret',
              status: newApiTokenStatus,
            },
          });
        }
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, {
            success: true,
            data: {
              items: newApiTokenCreated ? [
                {
                  id: 9,
                  name: 'Codex NewAPI Key',
                  key: 'sk-newapi-full-secret',
                  status: newApiTokenStatus,
                  used_quota: 500_000,
                  remain_quota: newApiTokenQuota,
                  unlimited_quota: false,
                  model_limits_enabled: true,
                  model_limits: 'deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner',
                  accessed_time: 1770000000,
                  expired_time: -1,
                },
              ] : [],
            },
          });
        }
        if (path === '/api/token/search') {
          return jsonResponse(200, {
            success: true,
            data: {
              items: [
                {
                  id: 9,
                  name: 'Codex NewAPI Key',
                  key: 'sk-newapi-full-secret',
                  status: newApiTokenStatus,
                  remain_quota: newApiTokenQuota,
                  used_quota: 500_000,
                  unlimited_quota: false,
                  model_limits: 'deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner',
                },
              ],
            },
          });
        }
        if (path === '/api/token/9/key') {
          return jsonResponse(200, { success: true, data: { key: 'sk-newapi-full-secret' } });
        }
        if (path === '/api/token/9' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, {
            success: true,
            data: {
              id: 9,
              name: 'Codex NewAPI Key',
              status: newApiTokenStatus,
              remain_quota: newApiTokenQuota,
              unlimited_quota: false,
              model_limits_enabled: true,
              model_limits: 'deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner',
              expired_time: -1,
            },
          });
        }
        if (path === '/api/token/' && init.method === 'PUT') {
          const body = JSON.parse(init.body);
          assert.equal(body.id, 9);
          if (requestUrl.searchParams.get('status_only') === 'true') {
            assert.equal(body.status, 2);
            newApiTokenStatus = body.status;
          } else {
            assert.equal(body.remain_quota, 36_000_000);
            assert.equal(body.unlimited_quota, false);
            newApiTokenQuota = body.remain_quota;
          }
          return jsonResponse(200, { success: true, data: { ...body, key: 'sk-newapi-full-secret' } });
        }
        if (path === '/api/token/9/' && init.method === 'DELETE') {
          newApiTokenStatus = 2;
          return jsonResponse(200, { success: true, data: 1 });
        }
        if (path === '/api/log/self') {
          return jsonResponse(200, {
            success: true,
            data: {
              items: [
                {
                  id: 88,
                  token_id: 9,
                  model_name: 'deepseek-v4-flash',
                  quota: 360,
                  prompt_tokens: 1000,
                  completion_tokens: 400,
                  created_at: 1770000000,
                  endpoint: '/v1/responses',
                },
              ],
            },
          });
        }
        if (path === '/api/log/self/stat' || path === '/api/data/self') {
          return jsonResponse(200, { success: true, data: {} });
        }
        if (path === '/api/subscription/self' || path === '/api/user/topup/info' || path === '/api/user/aff') {
          return jsonResponse(200, { success: true, data: {} });
        }
        if (path === '/v1/models') {
          assert.equal(init.headers.authorization, 'Bearer sk-newapi-full-secret');
          assert.equal(init.method || 'GET', 'GET');
          assert.equal(Object.prototype.hasOwnProperty.call(init, 'body'), false);
          return jsonResponse(200, { object: 'list', data: [{ id: 'deepseek-v4-flash', object: 'model' }] });
        }
        if (path === '/v1/responses') {
          const body = JSON.parse(init.body);
          assert.equal(body.model, 'deepseek-v4-flash');
          assert.equal(init.headers.authorization, 'Bearer sk-newapi-full-secret');
          return jsonResponse(200, { id: 'resp-newapi', output_text: 'ok' });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'newapi@example.com', password: 'TestPass123!' },
      });
      const funded = await fixture.readData();
      const fundedUser = funded.users.find((user) => user.email === 'newapi@example.com');
      fundedUser.packageQuotaCents = 7200;
      fundedUser.balanceCents = 7200;
      await fixture.writeData(funded);
      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Codex NewAPI Key', modelGroup: 'DeepSeek' },
      });
      assert.equal(created.status, 200);
      assert.equal(created.json.key.secret, 'sk-newapi-full-secret');
      assert.equal(created.json.key.modelGroup, 'DeepSeek');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie: registered.cookie });
      assert.equal(dashboard.status, 200);
      assert.equal(dashboard.json.account.balance, '$10.00');
      assert.equal(dashboard.json.account.monthCost, '$0.14');
      assert.equal(dashboard.json.apiKeys[0].preview, 'sk-••••••cret');
      assert.equal(Object.hasOwn(dashboard.json.apiKeys[0], 'secret'), false);
      assert.equal(dashboard.json.modelUsage[0].model, 'DeepSeek');

      const imported = await fixture.request('/api/frist/import-url?target=Codex&keyId=9', {
        cookie: registered.cookie,
      });
      assert.equal(imported.status, 200);
      const importUrl = new URL(imported.json.url);
      assert.equal(importUrl.searchParams.get('endpoint'), 'https://api.deepseek.com/v1');
      assert.equal(importUrl.searchParams.get('usageEnabled'), 'true');
      assert.equal(importUrl.searchParams.get('usageApiKey'), 'sk-newapi-full-secret');
      assert.equal(importUrl.searchParams.get('usageBaseUrl'), fixture.baseUrl);
      assert.match(decodeUrlSafeBase64(importUrl.searchParams.get('usageScript')), /\/api\/frist\/key-usage/);
      assert.equal(importUrl.searchParams.get('config'), null);
      assert.equal(imported.json.config.targetSlug, 'codex');
      assert.equal(JSON.parse(imported.json.config.authJson).OPENAI_API_KEY, 'sk-newapi-full-secret');
      assert.equal(imported.json.config.apiRequestUrl, 'https://api.deepseek.com/v1');
      assert.equal(imported.json.config.usageBaseUrl, fixture.baseUrl);
      assert.match(imported.json.config.ccSwitchMcpUrl, /resource=mcp/);
      assert.match(imported.json.setup.test, /CODEX_HOME="\$tmp_home" codex exec/);
      assert.match(imported.json.setup.test, /\[mcp_servers\.playwright\]/);

      const usage = await fixture.request('/api/frist/key-usage', {
        headers: { Authorization: 'Bearer sk-newapi-full-secret' },
      });
      assert.equal(usage.status, 200);
      assert.equal(usage.json.ok, true);
      assert.equal(usage.json.keyPreview, 'sk-••••••cret');
      assert.equal(usage.json.plan, 'New-API');
      assert.equal(usage.json.remainingUsd, 10);
      assert.equal(usage.json.usedUsd, 0.14);
      assert.equal(JSON.stringify(usage.json).includes('sk-newapi-full-secret'), false);

      const models = await fixture.request('/v1/models', {
        headers: { Authorization: 'Bearer sk-newapi-full-secret' },
      });
      assert.equal(models.status, 200);
      assert.equal(models.json.data[0].id, 'deepseek-v4-flash');
      assert.ok(newApiCalls.some((call) => call.url === 'https://new-api.internal/v1/models'));

      const gateway = await fixture.request('/v1/responses', {
        method: 'POST',
        headers: { Authorization: 'Bearer sk-newapi-full-secret' },
        body: { model: 'deepseek-v4-flash', input: 'hello' },
      });
      assert.equal(gateway.status, 200);
      assert.equal(gateway.json.id, 'resp-newapi');
      assert.ok(newApiCalls.some((call) => call.url === 'https://new-api.internal/v1/responses'));

      const disabled = await fixture.request('/api/frist/token/9', {
        method: 'PATCH',
        cookie: registered.cookie,
        body: { enabled: false },
      });
      assert.equal(disabled.status, 200);
      assert.equal(disabled.json.key.enabled, false);

      const deleted = await fixture.request('/api/frist/token/9', {
        method: 'DELETE',
        cookie: registered.cookie,
      });
      assert.equal(deleted.status, 200);
      assert.equal(deleted.json.deletedKeyId, '9');
      assert.ok(newApiCalls.some((call) => call.url === 'https://new-api.internal/api/token/9/'));
    } finally {
      await fixture.close();
    }
  });

  it('blocks unowned, legacy, pending, malformed, orphan, unlimited, exhausted and disabled New-API tokens before gateway proxying', async () => {
    const tokenSecret = 'sk-gateway-owner-boundary-secret';
    const upstreamToken = {
      id: 88,
      name: 'Gateway Ownership Boundary',
      key: tokenSecret,
      status: 1,
      remain_quota: 500_000,
      unlimited_quota: false,
    };
    let gatewayCalls = 0;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      newApiGatewayEnabled: true,
      newApiGatewayBaseUrl: 'https://new-api.internal/v1',
      fetchImpl: async (url) => {
        const path = new URL(String(url)).pathname;
        if (path === '/api/token/search') {
          return jsonResponse(200, { success: true, data: { items: [{ ...upstreamToken }] } });
        }
        if (path === '/api/token/88') {
          return jsonResponse(200, { success: true, data: { ...upstreamToken } });
        }
        if (path === '/v1/responses') {
          gatewayCalls += 1;
          return jsonResponse(200, { id: 'resp-owner-verified', output_text: 'ok' });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    async function setOwner(owner) {
      const data = await fixture.readData();
      data.newApiTokenOwners = owner === undefined ? {} : { '88': owner };
      await fixture.writeData(data);
    }

    async function requestGateway() {
      return fixture.request('/v1/responses', {
        method: 'POST',
        headers: { Authorization: `Bearer ${tokenSecret}` },
        body: { model: 'gpt-5.5', input: 'owner boundary' },
      });
    }

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'gateway-owner@example.com', password: 'TestPass123!' },
      });
      assert.equal(registered.status, 200);
      const data = await fixture.readData();
      const user = data.users.find((item) => item.email === 'gateway-owner@example.com');

      await setOwner(undefined);
      assert.equal((await requestGateway()).status, 401);
      await setOwner(user.id);
      assert.equal((await requestGateway()).status, 401);
      await setOwner({ userId: user.id, state: 'pending_activation' });
      assert.equal((await requestGateway()).status, 401);
      await setOwner({ state: 'active', allocatedCents: 100, upstreamQuotaUnits: 500_000 });
      assert.equal((await requestGateway()).status, 401);
      await setOwner({ userId: 'missing-user', state: 'active', allocatedCents: 100, upstreamQuotaUnits: 500_000 });
      assert.equal((await requestGateway()).status, 401);
      const duplicatedUsers = await fixture.readData();
      duplicatedUsers.users.push({ ...user, email: 'duplicate-id@example.com' });
      duplicatedUsers.newApiTokenOwners = {
        '88': { userId: user.id, state: 'active', allocatedCents: 100, upstreamQuotaUnits: 500_000 },
      };
      await fixture.writeData(duplicatedUsers);
      assert.equal((await requestGateway()).status, 401);
      duplicatedUsers.users = duplicatedUsers.users.filter(
        (item) => item.id !== user.id || item.email === 'gateway-owner@example.com',
      );
      await fixture.writeData(duplicatedUsers);
      await setOwner({ userId: user.id, state: 'active' });
      assert.equal((await requestGateway()).status, 401);
      await setOwner({ userId: user.id, state: 'active', allocatedCents: 100, upstreamQuotaUnits: 500_000 });
      upstreamToken.unlimited_quota = true;
      assert.equal((await requestGateway()).status, 401);
      upstreamToken.unlimited_quota = false;
      upstreamToken.remain_quota = 0;
      assert.equal((await requestGateway()).status, 401);
      upstreamToken.remain_quota = 500_000;
      upstreamToken.status = 2;
      assert.equal((await requestGateway()).status, 401);
      assert.equal(gatewayCalls, 0);

      upstreamToken.status = 1;
      const allowed = await requestGateway();
      assert.equal(allowed.status, 200);
      assert.equal(allowed.json.id, 'resp-owner-verified');
      assert.equal(gatewayCalls, 1);
    } finally {
      await fixture.close();
    }
  });

  it('isolates shared New-API tokens by local customer ownership', async () => {
    const upstreamTokens = [];
    const deletedTokenIds = [];
    let returnExistingToken = false;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      fetchImpl: async (url, init = {}) => {
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (path === '/api/models/') {
          return jsonResponse(200, { success: true, data: { items: [{ model_name: 'gpt-5.5' }] } });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          const body = JSON.parse(init.body);
          assert.equal(body.unlimited_quota, false);
          assert.equal(body.remain_quota, 0);
          if (returnExistingToken) {
            return jsonResponse(200, { success: true, data: upstreamTokens[0] });
          }
          const id = upstreamTokens.length + 1;
          const token = {
            id,
            ...body,
            key: `sk-tenant-${id}-secret`,
            status: 1,
            used_quota: id * 100,
            remain_quota: body.remain_quota,
          };
          upstreamTokens.push(token);
          return jsonResponse(200, { success: true, data: token });
        }
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, { success: true, data: { items: upstreamTokens } });
        }
        if (path === '/api/token/search') {
          const keyword = requestUrl.searchParams.get('keyword') || '';
          return jsonResponse(200, {
            success: true,
            data: { items: upstreamTokens.filter((token) => token.name.includes(keyword)) },
          });
        }
        const keyMatch = path.match(/^\/api\/token\/(\d+)\/key$/);
        if (keyMatch) {
          const token = upstreamTokens.find((item) => item.id === Number(keyMatch[1]));
          return jsonResponse(200, { success: true, data: { key: token?.key || '' } });
        }
        const tokenMatch = path.match(/^\/api\/token\/(\d+)\/?$/);
        if (tokenMatch && init.method === 'DELETE') {
          deletedTokenIds.push(Number(tokenMatch[1]));
          return jsonResponse(200, { success: true, data: 1 });
        }
        if (tokenMatch && (!init.method || init.method === 'GET')) {
          const token = upstreamTokens.find((item) => item.id === Number(tokenMatch[1]));
          return token
            ? jsonResponse(200, { success: true, data: token })
            : jsonResponse(404, { success: false, message: 'not found' });
        }
        if (path === '/api/token/' && init.method === 'PUT') {
          const body = JSON.parse(init.body);
          const token = upstreamTokens.find((item) => item.id === Number(body.id));
          Object.assign(token, body);
          return jsonResponse(200, { success: true, data: token });
        }
        if (path === '/api/log/self') {
          return jsonResponse(200, {
            success: true,
            data: {
              items: upstreamTokens.map((token) => ({
                id: `log-${token.id}`,
                token_id: token.id,
                model_name: 'gpt-5.5',
                quota: token.id * 10,
              })).concat({
                id: 'log-ambiguous-name-only',
                token_name: 'Shared Key',
                model_name: 'leaked-model',
                quota: 999_999,
              }),
            },
          });
        }
        if (path === '/api/user/topup/info') {
          return jsonResponse(200, { success: true, data: {} });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const first = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'first-newapi@example.com', password: 'TestPass123!' },
      });
      const second = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'second-newapi@example.com', password: 'TestPass123!' },
      });

      const unfunded = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: first.cookie,
        body: { name: 'Shared Key', modelGroup: 'OpenAI' },
      });
      assert.equal(unfunded.status, 402);
      assert.equal(upstreamTokens.length, 0);

      const funded = await fixture.readData();
      for (const user of funded.users) {
        if (['first-newapi@example.com', 'second-newapi@example.com'].includes(user.email)) {
          user.packageQuotaCents = 7200;
          user.balanceCents = 7200;
        }
      }
      await fixture.writeData(funded);

      const firstKey = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: first.cookie,
        body: { name: 'Shared Key', modelGroup: 'OpenAI', remainQuota: 999_999 },
      });
      const secondKey = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: second.cookie,
        body: { name: 'Shared Key', modelGroup: 'OpenAI' },
      });
      assert.equal(firstKey.status, 200);
      assert.equal(secondKey.status, 200);
      assert.equal(firstKey.json.key.id, '1');
      assert.equal(secondKey.json.key.id, '2');

      const allocated = await fixture.readData();
      assert.equal(allocated.users.find((user) => user.email === 'first-newapi@example.com').balanceCents, 0);
      assert.equal(allocated.users.find((user) => user.email === 'second-newapi@example.com').balanceCents, 0);
      assert.equal(allocated.newApiTokenOwners['1'].allocatedCents, 7200);
      assert.equal(allocated.newApiTokenOwners['2'].allocatedCents, 7200);
      assert.equal(allocated.newApiTokenOwners['1'].upstreamQuotaUnits, 36_000_000);
      assert.equal(allocated.newApiTokenOwners['2'].upstreamQuotaUnits, 36_000_000);
      assert.equal(allocated.newApiTokenOwners['1'].state, 'active');
      assert.equal(allocated.newApiTokenOwners['2'].state, 'active');
      assert.deepEqual(allocated.newApiTokenCreateIntents, {});

      const duplicatedQuota = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: first.cookie,
        body: { name: 'Another Key', modelGroup: 'OpenAI', remainQuota: 999_999 },
      });
      assert.equal(duplicatedQuota.status, 402);
      assert.equal(upstreamTokens.length, 2);

      const collisionData = await fixture.readData();
      const firstUser = collisionData.users.find((user) => user.email === 'first-newapi@example.com');
      firstUser.packageQuotaCents = 7200;
      firstUser.balanceCents = 7200;
      await fixture.writeData(collisionData);
      returnExistingToken = true;
      const collided = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: first.cookie,
        body: { name: 'Collision Key', modelGroup: 'OpenAI' },
      });
      returnExistingToken = false;
      assert.equal(collided.status, 502);
      const afterCollision = await fixture.readData();
      assert.equal(afterCollision.newApiTokenOwners['1'].userId, firstUser.id);
      assert.equal(afterCollision.users.find((user) => user.id === firstUser.id).balanceCents, 7200);

      const firstDashboard = await fixture.request('/api/frist/dashboard', { cookie: first.cookie });
      const secondDashboard = await fixture.request('/api/frist/dashboard', { cookie: second.cookie });
      assert.deepEqual(firstDashboard.json.apiKeys.map((key) => key.id), ['1']);
      assert.deepEqual(secondDashboard.json.apiKeys.map((key) => key.id), ['2']);
      assert.equal(JSON.stringify(firstDashboard.json).includes('sk-tenant-2-secret'), false);
      assert.equal(JSON.stringify(secondDashboard.json).includes('sk-tenant-1-secret'), false);
      assert.equal(JSON.stringify(firstDashboard.json).includes('leaked-model'), false);
      assert.equal(JSON.stringify(secondDashboard.json).includes('leaked-model'), false);

      const stolenPatch = await fixture.request('/api/frist/token/1', {
        method: 'PATCH',
        cookie: second.cookie,
        body: { enabled: false },
      });
      const stolenDelete = await fixture.request('/api/frist/token/1', {
        method: 'DELETE',
        cookie: second.cookie,
      });
      const stolenImport = await fixture.request('/api/frist/import-url?target=Codex&keyId=1', {
        cookie: second.cookie,
      });
      assert.equal(stolenPatch.status, 404);
      assert.equal(stolenDelete.status, 404);
      assert.equal(stolenImport.status, 404);
      assert.deepEqual(deletedTokenIds, []);

      const missingKeyImport = await fixture.request('/api/frist/import-url?target=Codex', {
        cookie: second.cookie,
      });
      assert.equal(missingKeyImport.status, 400);

      const ownImport = await fixture.request('/api/frist/import-url?target=Codex&keyId=2', {
        cookie: second.cookie,
      });
      assert.equal(ownImport.status, 200);
      assert.equal(JSON.parse(ownImport.json.config.authJson).OPENAI_API_KEY, 'sk-tenant-2-secret');
    } finally {
      await fixture.close();
    }
  });

  it('revokes a staged New-API token and restores quota when owner persistence fails', async () => {
    let upstreamToken = null;
    let failOwnerSave = false;
    let deleteRequests = 0;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      runtimeBeforeSave: async (data) => {
        if (failOwnerSave && Object.keys(data.newApiTokenOwners || {}).length > 0) {
          failOwnerSave = false;
          throw new Error('simulated owner persistence failure');
        }
      },
      fetchImpl: async (url, init = {}) => {
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (path === '/api/models/') {
          return jsonResponse(200, { success: true, data: { items: [{ model_name: 'gpt-5.5' }] } });
        }
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, { success: true, data: { items: upstreamToken ? [upstreamToken] : [] } });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          const body = JSON.parse(init.body);
          assert.equal(body.remain_quota, 0);
          assert.equal(body.unlimited_quota, false);
          upstreamToken = {
            id: 91,
            ...body,
            key: 'sk-staged-persistence-secret',
            status: 1,
          };
          failOwnerSave = true;
          return jsonResponse(200, { success: true, data: upstreamToken });
        }
        if (path === '/api/token/91/key') {
          return jsonResponse(200, { success: true, data: { key: upstreamToken?.key || '' } });
        }
        if (path === '/api/token/91' && (!init.method || init.method === 'GET')) {
          return upstreamToken
            ? jsonResponse(200, { success: true, data: upstreamToken })
            : jsonResponse(404, { success: false, message: 'not found' });
        }
        if (path === '/api/token/91/' && init.method === 'DELETE') {
          deleteRequests += 1;
          upstreamToken = null;
          return jsonResponse(200, { success: true, data: 1 });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'owner-save-failure@example.com', password: 'TestPass123!' },
      });
      const funded = await fixture.readData();
      const user = funded.users.find((item) => item.email === 'owner-save-failure@example.com');
      user.packageQuotaCents = 7200;
      user.balanceCents = 7200;
      await fixture.writeData(funded);

      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Persistence Safety Key', modelGroup: 'OpenAI' },
      });

      assert.equal(created.status, 500);
      assert.equal(deleteRequests, 1);
      assert.equal(upstreamToken, null);
      const after = await fixture.readData();
      assert.equal(after.users.find((item) => item.id === user.id).balanceCents, 7200);
      assert.deepEqual(after.newApiTokenOwners, {});
      assert.deepEqual(after.newApiTokenCreateIntents, {});
      assert.equal(
        after.events.some((event) => event.type === 'newapi_token_create_rolled_back' && event.userId === user.id),
        true,
      );
    } finally {
      await fixture.close();
    }
  });

  it('keeps New-API ownership when delete cannot revoke an enabled token', async () => {
    const upstreamToken = {
      id: 77,
      name: 'Delete Safety Key',
      key: 'sk-delete-safety-secret',
      status: 1,
      remain_quota: 0,
      unlimited_quota: false,
    };
    let disableAttempts = 0;
    let deleteVerificationMode = 'enabled';
    let deleteRequested = false;
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      fetchImpl: async (url, init = {}) => {
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (path === '/api/models/') {
          return jsonResponse(200, { success: true, data: { items: ['gpt-5.5'] } });
        }
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          return jsonResponse(200, { success: true, data: { items: [] } });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          Object.assign(upstreamToken, JSON.parse(init.body));
          return jsonResponse(200, { success: true, data: upstreamToken });
        }
        if (path === '/api/token/77/key') {
          return jsonResponse(200, { success: true, data: { key: upstreamToken.key } });
        }
        if (path === '/api/token/77' && (!init.method || init.method === 'GET')) {
          if (deleteRequested && deleteVerificationMode === 'missing-status') {
            return jsonResponse(200, { success: true, data: { id: 77 } });
          }
          if (deleteRequested && deleteVerificationMode === 'wrong-id') {
            return jsonResponse(200, { success: true, data: { id: 78, status: 2 } });
          }
          return jsonResponse(200, { success: true, data: upstreamToken });
        }
        if (path === '/api/token/77/' && init.method === 'DELETE') {
          // 模拟旧上游返回成功但实际上没有删除或禁用。
          deleteRequested = true;
          return jsonResponse(200, { success: true, data: 1 });
        }
        if (path === '/api/token/' && init.method === 'PUT') {
          const body = JSON.parse(init.body);
          if (requestUrl.searchParams.get('status_only') === 'true') {
            disableAttempts += 1;
            // 模拟状态接口也谎报成功，后续 GET 仍为 enabled。
            return jsonResponse(200, { success: true, data: { id: 77, status: 2 } });
          }
          Object.assign(upstreamToken, body);
          return jsonResponse(200, { success: true, data: upstreamToken });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'delete-safety@example.com', password: 'TestPass123!' },
      });
      const funded = await fixture.readData();
      const user = funded.users.find((item) => item.email === 'delete-safety@example.com');
      user.packageQuotaCents = 7200;
      user.balanceCents = 7200;
      await fixture.writeData(funded);

      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: upstreamToken.name, modelGroup: 'OpenAI' },
      });
      assert.equal(created.status, 200);

      const deleted = await fixture.request('/api/frist/token/77', {
        method: 'DELETE',
        cookie: registered.cookie,
      });
      assert.equal(deleted.status, 502);
      assert.equal(disableAttempts, 1);

      let after = await fixture.readData();
      assert.equal(after.newApiTokenOwners['77'].userId, user.id);
      assert.equal(
        after.events.some((event) => event.type === 'newapi_token_deleted' && event.keyId === '77'),
        false,
      );

      deleteVerificationMode = 'missing-status';
      const missingStatus = await fixture.request('/api/frist/token/77', {
        method: 'DELETE',
        cookie: registered.cookie,
      });
      assert.equal(missingStatus.status, 502);
      assert.equal(disableAttempts, 2);
      after = await fixture.readData();
      assert.equal(after.newApiTokenOwners['77'].userId, user.id);

      deleteVerificationMode = 'wrong-id';
      const wrongId = await fixture.request('/api/frist/token/77', {
        method: 'DELETE',
        cookie: registered.cookie,
      });
      assert.equal(wrongId.status, 502);
      assert.equal(disableAttempts, 2);
      after = await fixture.readData();
      assert.equal(after.newApiTokenOwners['77'].userId, user.id);
    } finally {
      await fixture.close();
    }
  });

  it('reports New-API token inventory failures instead of showing an empty dashboard', async () => {
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      fetchImpl: async (url) => {
        const path = new URL(String(url)).pathname;
        if (path === '/api/token/') {
          return jsonResponse(503, { success: false, message: 'inventory unavailable' });
        }
        return jsonResponse(200, { success: true, data: { items: [] } });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'inventory-failure@example.com', password: 'TestPass123!' },
      });

      const dashboard = await fixture.request('/api/frist/dashboard', {
        cookie: registered.cookie,
      });

      assert.equal(dashboard.status, 503);
      assert.equal(dashboard.json.error, 'inventory unavailable');
    } finally {
      await fixture.close();
    }
  });

  it('never claims an unowned historical New-API token beyond the first page', async () => {
    const upstreamTokens = Array.from({ length: 101 }, (_, index) => ({
      id: index + 1,
      name: index === 100 ? 'Historical Shared Key' : `Historical Key ${index + 1}`,
      key: index === 100 ? 'sk-legacy-secret' : `sk-history-${index + 1}`,
      status: 1,
      remain_quota: 100,
    }));
    let historicalSecretRead = false;
    const requestedTokenPages = [];
    const fixture = await createServerFixture({
      requireEmailVerification: false,
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'newapi-access-token',
      newApiUserId: '42',
      newApiDefaultTokenQuota: 7200,
      fetchImpl: async (url, init = {}) => {
        const requestUrl = new URL(String(url));
        const path = requestUrl.pathname;
        if (path === '/api/models/') {
          return jsonResponse(200, { success: true, data: { items: [] } });
        }
        if (path === '/api/token/' && (!init.method || init.method === 'GET')) {
          const page = Number(requestUrl.searchParams.get('p') || 1);
          requestedTokenPages.push(page);
          const start = (page - 1) * 100;
          return jsonResponse(200, {
            success: true,
            data: { items: upstreamTokens.slice(start, start + 100) },
          });
        }
        if (path === '/api/token/' && init.method === 'POST') {
          // 旧逻辑会在无 ID 响应后按名称搜索，并误认第 101 条历史 Token。
          return jsonResponse(200, { success: true, data: {} });
        }
        if (path === '/api/token/search') {
          return jsonResponse(200, { success: true, data: { items: [upstreamTokens[100]] } });
        }
        if (path === '/api/token/101/key') {
          historicalSecretRead = true;
          return jsonResponse(200, { success: true, data: { key: 'sk-legacy-secret' } });
        }
        return jsonResponse(404, { success: false, message: `unexpected ${path}` });
      },
    });

    try {
      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: { email: 'pagination-owner@example.com', password: 'TestPass123!' },
      });
      const funded = await fixture.readData();
      const user = funded.users.find((item) => item.email === 'pagination-owner@example.com');
      user.packageQuotaCents = 7200;
      user.balanceCents = 7200;
      await fixture.writeData(funded);

      const created = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie: registered.cookie,
        body: { name: 'Historical Shared Key', modelGroup: 'OpenAI' },
      });

      assert.equal(created.status, 502);
      assert.equal(historicalSecretRead, false);
      assert.ok(requestedTokenPages.includes(2));
      const after = await fixture.readData();
      assert.equal(after.newApiTokenOwners['101'], undefined);
      assert.equal(after.users.find((item) => item.id === user.id).balanceCents, 7200);
    } finally {
      await fixture.close();
    }
  });

  it('selects the faster proxy path during replenishment and routes gateway calls through it', async () => {
    const gatewayUrls = [];
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        const targetUrl = String(url);
        const body = options.body ? JSON.parse(options.body) : {};
        if (targetUrl.includes('supplier.example.com') && targetUrl.endsWith('/chat/completions')) {
          await delay(30);
        }
        if (body.messages?.[0]?.content === 'customer request') {
          gatewayUrls.push(targetUrl);
        }
        return jsonResponse(200, {
          id: 'chatcmpl-proxy',
          model: body.model || 'claude-sonnet-4-5-c',
          choices: [{ message: { role: 'assistant', content: 'proxy' } }],
        });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          proxyBaseUrl: 'https://proxy.example.com/v1',
          pool: 'day',
          models: ['claude-sonnet-4-5-c'],
          keys: [{ value: 'sk-proxy', quotaRemaining: 1000, latencyMs: 999 }],
          probeMode: 'strict',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.supplierProfile.connectionPath, 'proxy');

      const cookie = await fixture.createVerifiedCustomer('proxy-route@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'JIYU-DAY-001' },
      });
      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: '代理路径 Key' },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-sonnet-4-5-c',
          messages: [{ role: 'user', content: 'customer request' }],
        },
      });
      assert.equal(response.status, 200);
      assert.deepEqual(gatewayUrls, ['https://proxy.example.com/v1/chat/completions']);
    } finally {
      await fixture.close();
    }
  });

  it('keeps only fallback models that pass chat probing when supplier model listing is unavailable', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async (url, options = {}) => {
        if (String(url).endsWith('/models')) {
          return jsonResponse(404, { error: { message: 'models endpoint not found' } });
        }
        const body = options.body ? JSON.parse(options.body) : {};
        if (body.model === 'gpt-5.5') {
          return jsonResponse(200, {
            id: 'chatcmpl-gpt',
            model: 'gpt-5.5',
            choices: [{ message: { role: 'assistant', content: 'ok' } }],
          });
        }
        return jsonResponse(404, { error: { message: `model ${body.model} not found` } });
      },
    });

    try {
      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          keys: [{ value: 'sk-fallback', quotaRemaining: 1000, latencyMs: 90 }],
          probeMode: 'strict',
        },
      });
      assert.equal(replenished.status, 200);
      assert.deepEqual(replenished.json.supplierProfile.models, ['gpt-5.5']);
      assert.deepEqual(replenished.json.credentials[0].models, ['gpt-5.5']);
    } finally {
      await fixture.close();
    }
  });

  it('blocks upstream replenishment URLs that resolve to loopback or private addresses', async () => {
    const fixture = await createServerFixture({
      resolveUpstreamAddresses: async (hostname) => {
        if (hostname === 'metadata.example.com') return [{ address: '169.254.169.254', family: 4 }];
        return [{ address: '203.0.113.10', family: 4 }];
      },
    });

    try {
      const loopback = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'http://127.0.0.1:8080/v1',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: ['sk-loopback'],
        },
      });
      assert.equal(loopback.status, 400);
      assert.match(loopback.json.error, /内网|本机/);

      const rebinding = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://metadata.example.com/v1',
          pool: 'day',
          models: ['gpt-5.5'],
          keys: ['sk-rebinding'],
        },
      });
      assert.equal(rebinding.status, 400);
      assert.match(rebinding.json.error, /解析到内网|本机/);
    } finally {
      await fixture.close();
    }
  });

  it('refuses to start in public mode with unsafe defaults enabled', () => {
    assert.throws(
      () =>
        createFristApiServer({
          publicMode: true,
          adminToken: 'frist-api-dev-admin-token',
          sessionSecret: 'frist-api-dev-session-secret',
          exposeVerificationCode: true,
          allowDemoRecharge: true,
          publicGatewayBaseUrl: 'http://127.0.0.1:3180/v1',
        }),
      /公开模式配置不安全/,
    );

    const server = createFristApiServer({
      publicMode: true,
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
      adminPageCode: 'hidden-admin-entry-2026',
      requireCsrf: true,
      publicGatewayBaseUrl: 'https://gateway.frist-api.dev/v1',
    });
    server.close();

    const temporaryIpServer = createFristApiServer({
      publicMode: true,
      allowInsecurePublicHttp: true,
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
      adminPageCode: 'hidden-admin-entry-2026',
      requireCsrf: true,
      publicGatewayBaseUrl: 'http://101.43.41.96:5566/v1',
    });
    temporaryIpServer.close();
  });

  it('enforces production boundaries for brand domain, New-API database, 2FA and redemption billing', () => {
    assert.throws(
      () =>
        createFristApiServer({
          publicMode: true,
          enforceProductionReadiness: true,
          adminToken: 'admin-token-with-enough-randomness-2026',
          sessionSecret: 'session-secret-with-enough-randomness-2026',
          dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
          adminPageCode: 'hidden-admin-entry-2026',
          publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
          canonicalHost: 'jiyu.245334.xyz',
        }),
      /固定 HTTPS 品牌域名|New-API 数据库|管理员 2FA|兑换码|人机验证/,
    );

    const productionServer = createFristApiServer({
      publicMode: true,
      enforceProductionReadiness: true,
      requireNewApiDatabase: true,
      newApiEnabled: true,
      newApiBaseUrl: 'http://openclaw-newapi:3000',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '1',
      newApiDefaultTokenQuota: 7200,
      requireAdmin2fa: true,
      adminTotpSecrets: ['JBSWY3DPEHPK3PXP'],
      requireTurnstile: true,
      turnstileSiteKey: '1x00000000000000000000AA',
      turnstileSecret: '1x0000000000000000000000000000000AA',
      requireCsrf: true,
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
      adminPageCode: 'hidden-admin-entry-2026',
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      canonicalHost: 'jiyu.245334.xyz',
    });
    productionServer.close();
  });

  it('requires administrator TOTP before admin APIs when 2FA is enabled', async () => {
    const fixedNow = new Date('2026-05-07T12:00:00.000Z');
    const secret = 'JBSWY3DPEHPK3PXP';
    const fixture = await createServerFixture({
      requireAdmin2fa: true,
      adminTotpSecrets: [secret],
      nowFactory: () => fixedNow,
    });

    try {
      const blocked = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(blocked.status, 401);
      assert.match(blocked.json.error, /2FA/);

      const invalid = await fixture.request('/api/admin/2fa/verify', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { code: '000000' },
      });
      assert.equal(invalid.status, 401);

      const verified = await fixture.request('/api/admin/2fa/verify', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { code: totpCode(secret, fixedNow) },
      });
      assert.equal(verified.status, 200);
      assert.match(verified.setCookie, /frist_admin_2fa=/);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
        cookie: verified.cookie,
      });
      assert.equal(inventory.status, 200);
      assert.equal(Array.isArray(inventory.json.credentials), true);
    } finally {
      await fixture.close();
    }
  });

  it('records backup status and real channel SLA events for production readiness checks', async () => {
    const fixture = await createServerFixture({
      nowFactory: () => new Date('2026-05-07T12:00:00.000Z'),
      backupStatusMaxAgeHours: 26,
    });

    try {
      const initial = await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(initial.status, 200);
      assert.equal(initial.json.ready, false);
      assert.equal(initial.json.backup.ready, false);
      assert.equal(initial.json.sla.eventCount, 0);

      const backup = await fixture.request('/api/admin/backups/status', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          provider: 'rclone',
          target: 's3://frist-api-prod/runtime',
          lastBackupAt: '2026-05-07T11:30:00.000Z',
          lastRestoreTestAt: '2026-05-07T11:40:00.000Z',
          status: 'ok',
          artifact: 'runtime-20260507.tgz',
          checksum: 'sha256:test-checksum',
        },
      });
      assert.equal(backup.status, 200);
      assert.equal(backup.json.backup.ready, true);
      assert.equal(JSON.stringify(backup.json).includes('runtime-20260507.tgz'), true);

      await fixture.writeData({
        ...(await fixture.readData()),
        users: [
          {
            id: 'user-sla',
            email: 'sla@example.com',
            emailVerified: true,
            passwordHash: 'pbkdf2-sha256$210000$salt$digest',
            plan: '默认套餐',
            renewalDate: '-',
            balanceCents: 10_000,
            packageQuotaCents: 0,
            boosterQuotaCents: 10_000,
          },
        ],
        userKeys: [
          {
            id: 'key-sla',
            userId: 'user-sla',
            name: 'SLA Key',
            secret: 'fk-live-sla-test-key',
            preview: 'fk-live-••••••-test',
            enabled: true,
            modelGroup: 'OpenAI',
            costCents: 0,
          },
        ],
        credentials: [
          {
            id: 'cred-sla',
            sourceId: 'source-sla',
            baseUrl: 'https://supplier.example.com/v1',
            routeBaseUrl: 'https://supplier.example.com/v1',
            rawKey: 'sk-sla-upstream',
            keyPreview: 'sk-••••••ream',
            pool: 'default',
            modelGroup: 'OpenAI',
            models: ['gpt-5.5'],
            enabled: true,
            status: 'healthy',
            quotaRemaining: 1000,
            quotaTotal: 1000,
            latencyMs: 80,
            sourceType: 'authorized',
            riskStatus: 'approved',
            updatedAt: '2026-05-07T11:50:00.000Z',
          },
        ],
      });

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          authorization: 'Bearer fk-live-sla-test-key',
        },
        body: {
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: 'pong' }],
        },
      });
      assert.equal(gateway.status, 200);

      const viewerCookie = await fixture.createVerifiedCustomer('sla-viewer@example.com');
      const current = await fixture.readData();
      current.userKeys.find((item) => item.id === 'key-sla').userId = current.sessions[viewerCookie.split('=')[1]].userId;
      await fixture.writeData(current);
      const dashboard = await fixture.request('/api/frist/dashboard', { cookie: viewerCookie });
      const check = dashboard.json.channelChecks.find((item) => item.model === 'gpt-5.5');
      assert.equal(check.sla.window, '真实探测事件');
      assert.equal(check.sla.samples7d, 1);
      assert.equal(check.sla.availability7d, 100);

      const readiness = await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(readiness.json.backup.ready, true);
      assert.equal(readiness.json.sla.eventCount, 1);
    } finally {
      await fixture.close();
    }
  });

  it('keeps production readiness blocked when no healthy upstream inventory is available', async () => {
    const fixedNow = new Date('2026-05-07T12:00:00.000Z');
    const secret = 'JBSWY3DPEHPK3PXP';
    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      canonicalHost: 'jiyu.245334.xyz',
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '42',
      requireNewApiDatabase: true,
      requireAdmin2fa: true,
      adminTotpSecrets: [secret],
      requireTurnstile: true,
      turnstileSiteKey: '1x00000000000000000000AA',
      turnstileSecret: '1x0000000000000000000000000000000AA',
      nowFactory: () => fixedNow,
    });

    try {
      const verified = await fixture.request('/api/admin/2fa/verify', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { code: totpCode(secret, fixedNow) },
      });
      assert.equal(verified.status, 200);

      await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
        cookie: verified.cookie,
      });
      await fixture.writeData({
        ...(await fixture.readData()),
        backupStatus: {
          provider: 'rclone',
          target: 's3://frist-api-prod/runtime',
          lastBackupAt: '2026-05-07T11:30:00.000Z',
          lastRestoreTestAt: '2026-05-07T11:40:00.000Z',
          status: 'ok',
          artifact: 'runtime-20260507.tgz',
          checksum: 'sha256:test-checksum',
          updatedAt: '2026-05-07T11:40:00.000Z',
        },
        channelProbeEvents: [
          {
            model: 'gpt-5.5',
            status: 'ok',
            at: '2026-05-07T11:55:00.000Z',
            latencyMs: 88,
          },
        ],
        credentials: [
          {
            id: 'cred-failed-only',
            sourceId: 'source-failed-only',
            baseUrl: 'https://supplier.example.com/v1',
            routeBaseUrl: 'https://supplier.example.com/v1',
            rawKey: 'sk-failed-only',
            pool: 'default',
            modelGroup: 'OpenAI',
            models: ['gpt-5.5'],
            enabled: true,
            status: 'failed',
            quotaRemaining: 1000,
            quotaTotal: 1000,
            sourceType: 'authorized',
            riskStatus: 'approved',
          },
        ],
      });

      const readiness = await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
        cookie: verified.cookie,
      });
      assert.equal(readiness.status, 200);
      assert.equal(readiness.json.ready, false);
      const upstream = readiness.json.checks.find((check) => check.id === 'healthy_upstream_inventory');
      assert.equal(upstream.ok, false);
      assert.match(upstream.detail, /暂无健康上游/);
    } finally {
      await fixture.close();
    }
  });

  it('counts New-API inventory for production readiness with the current SQLite schema', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-api-newapi-readiness-'));
    const sqliteDb = join(dir, 'one-api.db');
    const fixedNow = new Date('2026-05-07T12:00:00.000Z');
    const secret = 'JBSWY3DPEHPK3PXP';
    const sqlite = spawnSync(
      'sqlite3',
      [sqliteDb],
      {
        input: [
          'create table channels (id integer primary key, status integer, models text);',
          'create table models (id integer primary key, model_name text, status integer);',
          "insert into channels (status, models) values (1, 'gpt-5.5,claude-sonnet-4-5-c');",
          "insert into models (model_name, status) values ('gpt-5.5', 1);",
        ].join('\n'),
        encoding: 'utf8',
      },
    );
    assert.equal(sqlite.status, 0, sqlite.stderr);

    const fixture = await createServerFixture({
      publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
      canonicalHost: 'jiyu.245334.xyz',
      newApiEnabled: true,
      newApiBaseUrl: 'https://new-api.internal',
      newApiAccessToken: 'new-api-access-token-with-enough-randomness',
      newApiUserId: '42',
      newApiSqliteDb: sqliteDb,
      requireNewApiDatabase: true,
      requireAdmin2fa: true,
      adminTotpSecrets: [secret],
      requireTurnstile: true,
      turnstileSiteKey: '1x00000000000000000000AA',
      turnstileSecret: '1x0000000000000000000000000000000AA',
      nowFactory: () => fixedNow,
    });

    try {
      const verified = await fixture.request('/api/admin/2fa/verify', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: { code: totpCode(secret, fixedNow) },
      });
      assert.equal(verified.status, 200);

      await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
        cookie: verified.cookie,
      });
      await fixture.writeData({
        ...(await fixture.readData()),
        backupStatus: {
          provider: 'rclone',
          target: 's3://frist-api-prod/runtime',
          lastBackupAt: '2026-05-07T11:30:00.000Z',
          lastRestoreTestAt: '2026-05-07T11:40:00.000Z',
          status: 'ok',
          artifact: 'runtime-20260507.tgz',
          checksum: 'sha256:test-checksum',
          updatedAt: '2026-05-07T11:40:00.000Z',
        },
        channelProbeEvents: [
          {
            model: 'gpt-5.5',
            status: 'ok',
            at: '2026-05-07T11:55:00.000Z',
            latencyMs: 88,
          },
        ],
        credentials: [],
      });

      const readiness = await fixture.request('/api/admin/production-readiness', {
        headers: { 'x-admin-token': 'admin-test-token' },
        cookie: verified.cookie,
      });
      assert.equal(readiness.status, 200);
      assert.equal(readiness.json.upstreamInventory.sqliteDbReadable, true);
      assert.equal(readiness.json.upstreamInventory.newApiEnabledChannels, 1);
      assert.equal(readiness.json.upstreamInventory.newApiModels, 1);
      assert.equal(readiness.json.checks.find((check) => check.id === 'healthy_upstream_inventory').ok, true);
    } finally {
      await fixture.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('records failed admin authentication without storing submitted tokens', async () => {
    const fixture = await createServerFixture();

    try {
      const blocked = await fixture.request('/api/admin/replenishments', {
        headers: {
          'x-admin-token': 'wrong-admin-token-should-not-be-stored',
          'x-forwarded-for': '203.0.113.9',
        },
      });
      assert.equal(blocked.status, 401);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.status, 200);
      const authEvent = inventory.json.events.find((event) => event.type === 'admin_auth_failed');
      assert.ok(authEvent);
      assert.match(authEvent.detail, /管理认证失败: \/api\/admin\/replenishments/);
      assert.equal(JSON.stringify(inventory.json).includes('wrong-admin-token-should-not-be-stored'), false);
      assert.equal((await fixture.readRawData()).includes('wrong-admin-token-should-not-be-stored'), false);
    } finally {
      await fixture.close();
    }
  });

  it('ships runtime write failure warnings and CLI graceful shutdown hooks', () => {
    const serverSource = readFileSync(new URL('../server/server.js', import.meta.url), 'utf8');

    assert.match(serverSource, /FRIST_API_RUNTIME_WRITE_FAILED/);
    assert.match(serverSource, /FRIST_API_ADMIN_AUDIT_WRITE_FAILED/);
    assert.match(serverSource, /process\.once\('SIGTERM'/);
    assert.match(serverSource, /process\.once\('SIGINT'/);
    assert.match(serverSource, /server\.close\(\(error\) =>/);
  });

  it('hides the static admin page behind a separate public gate code', async () => {
    const fixture = await createServerFixture({
      publicMode: true,
      allowInsecurePublicHttp: true,
      publicGatewayBaseUrl: 'http://101.43.41.96:5566/v1',
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
      exposeVerificationCode: false,
      adminPageCode: 'hidden-admin-entry-2026',
      requireCsrf: true,
    });

    try {
      const blocked = await fixture.request('/admin.html');
      assert.equal(blocked.status, 404);

      const allowed = await fixture.request('/admin.html?code=hidden-admin-entry-2026');
      assert.equal(allowed.status, 200);
      assert.match(allowed.text, /CC中转 管理端|>Admin</);
    } finally {
      await fixture.close();
    }
  });

  it('lets a logged-in customer claim one one-time owner code and manage with the session cookie', async () => {
    const fixture = await createServerFixture({
      adminClaimCodes: ['owner-claim-once-2026'],
      adminPageCode: 'hidden-admin-entry-2026',
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('owner@example.com');
      const before = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(before.json.user.isAdmin, false);

      const claimed = await fixture.request('/api/frist/admin/claim', {
        method: 'POST',
        cookie,
        body: { code: 'owner-claim-once-2026' },
      });
      assert.equal(claimed.status, 200);
      assert.equal(claimed.json.user.isAdmin, true);
      assert.equal(claimed.json.adminUrl, '/admin.html');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.user.isAdmin, true);

      const inventory = await fixture.request('/api/admin/replenishments', { cookie });
      assert.equal(inventory.status, 200);
      assert.equal(Array.isArray(inventory.json.credentials), true);

      const repeated = await fixture.request('/api/frist/admin/claim', {
        method: 'POST',
        cookie,
        body: { code: 'owner-claim-once-2026' },
      });
      assert.equal(repeated.status, 409);

      const otherCookie = await fixture.createVerifiedCustomer('other-owner@example.com');
      const stolen = await fixture.request('/api/frist/admin/claim', {
        method: 'POST',
        cookie: otherCookie,
        body: { code: 'owner-claim-once-2026' },
      });
      assert.equal(stolen.status, 409);
    } finally {
      await fixture.close();
    }
  });

  it('manages ChatGPT Plus account ledger without exposing credentials or routing it as API stock', async () => {
    const fixture = await createServerFixture({
      nowFactory: () => new Date('2026-05-04T12:00:00.000Z'),
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
    });

    try {
      const saved = await fixture.request('/api/admin/plus-accounts', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          label: 'Plus 工作号 A',
          openaiEmail: 'plus-work@example.com',
          appleEmail: 'apple-tr@example.com',
          region: 'Turkey',
          status: 'active',
          complianceStatus: 'self_use_only',
          plusRenewalAt: '2026-05-07',
          appleBalanceTry: 620,
          monthlyCostTry: 499.99,
          deviceProfile: 'Chrome Profile Plus-A',
          riskNote: '仅本人使用，不转售不共享',
          secrets: 'apple-password-and-recovery-note',
        },
      });
      assert.equal(saved.status, 200);
      assert.equal(saved.json.account.region, 'Türkiye');
      assert.equal(saved.json.account.label, 'Plus 工作号 A');
      assert.equal(saved.json.account.openaiEmail, 'pl***@example.com');
      assert.equal(saved.json.account.secretPreview, '已保存，管理端脱敏');
      assert.equal(saved.json.account.routingEnabled, false);
      assert.equal(JSON.stringify(saved.json).includes('apple-password-and-recovery-note'), false);
      assert.equal(saved.json.summary.dueSoon, 1);

      const ledger = await fixture.request('/api/admin/plus-accounts', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(ledger.status, 200);
      assert.equal(ledger.json.accounts.length, 1);
      assert.equal(ledger.json.accounts[0].renewalText, '3 天后到期');
      assert.equal(JSON.stringify(ledger.json).includes('plus-work@example.com'), false);
      assert.equal(JSON.stringify(ledger.json).includes('apple-password-and-recovery-note'), false);

      const updated = await fixture.request('/api/admin/plus-accounts', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          id: ledger.json.accounts[0].id,
          status: 'renewal_due',
          plusRenewalAt: '2026-05-05',
          appleBalanceTry: '余额异常',
          monthlyCostTry: '月费异常',
        },
      });
      assert.equal(updated.status, 200);
      assert.equal(updated.json.account.openaiEmail, 'pl***@example.com');
      assert.equal(updated.json.account.status, 'renewal_due');
      assert.equal(updated.json.account.appleBalanceTry, 0);
      assert.equal(updated.json.account.monthlyCostTry, 0);
      assert.equal(JSON.stringify(updated.json).includes('apple-password-and-recovery-note'), false);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.plusAccounts.length, 1);
      assert.equal(inventory.json.credentials.length, 0);
      assert.deepEqual(inventory.json.inventorySummary, []);

      const rawRuntime = await readFile(fixture.dataFile, 'utf8');
      assert.equal(rawRuntime.includes('apple-password-and-recovery-note'), false);
    } finally {
      await fixture.close();
    }
  });

  it('imports RT JSON and TXT credentials as a separate masked management ledger', async () => {
    const fixture = await createServerFixture({
      nowFactory: () => new Date('2026-05-04T12:00:00.000Z'),
      dataEncryptionKey: 'runtime-encryption-key-with-enough-randomness-2026',
    });

    try {
      const imported = await fixture.request('/api/admin/rt-accounts/import', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          platform: 'codex',
          sourceLabel: 'New-API Codex OAuth',
          accountType: 'Plus',
          rtText: JSON.stringify([
            {
              refresh_token: 'rt_codex_alpha_abcdefghijklmnopqrstuvwxyz',
              email: 'codex-alpha@example.com',
              account_id: 'acct_codex_alpha_001',
            },
            {
              refresh_token: 'rt_codex_beta_abcdefghijklmnopqrstuvwxyz',
              email: 'codex-beta@example.com',
            },
          ]),
          note: '只做刷新台账，不进入用户路由',
        },
      });
      assert.equal(imported.status, 200);
      assert.equal(imported.json.imported.length, 2);
      assert.equal(imported.json.summary.total, 2);
      assert.equal(imported.json.summary.ready, 2);
      assert.equal(imported.json.accounts[0].label, 'co***@example.com');
      assert.equal(imported.json.accounts[0].email, 'co***@example.com');
      assert.match(imported.json.accounts[0].refreshTokenPreview, /^rt-••••••/);
      assert.equal(JSON.stringify(imported.json).includes('codex-beta@example.com'), false);
      assert.equal(JSON.stringify(imported.json).includes('rt_codex_alpha'), false);
      assert.equal(JSON.stringify(imported.json).includes('acct_codex_alpha_001'), false);

      const updated = await fixture.request('/api/admin/rt-accounts/import', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          platform: 'openai',
          rtText: [
            'rt_chatgpt_txt_abcdefghijklmnopqrstuvwxyz,chatgpt@example.com,acct_chatgpt_001',
            'rt_codex_alpha_abcdefghijklmnopqrstuvwxyz,codex-alpha@example.com,acct_codex_alpha_001',
          ].join('\n'),
        },
      });
      assert.equal(updated.status, 200);
      assert.equal(updated.json.summary.total, 3);
      assert.equal(updated.json.imported.length, 2);

      const ledger = await fixture.request('/api/admin/rt-accounts', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(ledger.status, 200);
      assert.equal(ledger.json.accounts.length, 3);
      assert.equal(ledger.json.accounts.some((account) => account.label === 'chatgpt@example.com'), false);
      assert.equal(JSON.stringify(ledger.json).includes('rt_chatgpt_txt'), false);
      assert.equal(JSON.stringify(ledger.json).includes('acct_chatgpt_001'), false);

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.rtAccounts.length, 3);
      assert.equal(inventory.json.credentials.length, 0);
      assert.deepEqual(inventory.json.inventorySummary, []);

      const rawRuntime = await readFile(fixture.dataFile, 'utf8');
      assert.equal(rawRuntime.includes('rt_codex_alpha_abcdefghijklmnopqrstuvwxyz'), false);
      assert.equal(rawRuntime.includes('rt_chatgpt_txt_abcdefghijklmnopqrstuvwxyz'), false);
      assert.match(rawRuntime, /enc:v1:/);
    } finally {
      await fixture.close();
    }
  });
});

async function createServerFixture(options = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'frist-api-'));
  const dataFile = join(dir, 'runtime.json');
  const server = createFristApiServer({
    dataFile,
    publicDir: new URL('../', import.meta.url).pathname,
    sessionSecret: options.sessionSecret || 'session-test-secret',
    adminToken: options.adminToken || 'admin-test-token',
    exposeVerificationCode: options.exposeVerificationCode ?? true,
    allowDemoRecharge: options.allowDemoRecharge,
    requireEmailVerification: options.requireEmailVerification ?? true,
    nowFactory: options.nowFactory,
    quotaCost: options.quotaCost,
    fetchImpl: options.fetchImpl || (async () =>
      jsonResponse(200, {
        id: 'chatcmpl-fixture',
        choices: [{ message: { role: 'assistant', content: 'pong' } }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      })),
    lowInventoryThresholdRatio: options.lowInventoryThresholdRatio,
    notifyLowInventory: options.notifyLowInventory,
    channelMonitorEnabled: options.channelMonitorEnabled,
    channelMonitorIntervalMs: options.channelMonitorIntervalMs,
    channelMonitorBatchSize: options.channelMonitorBatchSize,
    channelMonitorCooldownMs: options.channelMonitorCooldownMs,
    rateMarkup: options.rateMarkup,
    xianyuWebhookToken: options.xianyuWebhookToken,
    notifyCredentialIssue: options.notifyCredentialIssue,
    balanceAlertEmailSender: options.balanceAlertEmailSender,
    requireCaptcha: options.requireCaptcha,
    requireTurnstile: options.requireTurnstile,
    turnstileSiteKey: options.turnstileSiteKey,
    turnstileSecret: options.turnstileSecret,
    turnstileVerifyUrl: options.turnstileVerifyUrl,
    turnstileAllowedHostnames: options.turnstileAllowedHostnames,
    authRateLimitMax: options.authRateLimitMax,
    authRateLimitWindowMs: options.authRateLimitWindowMs,
    redemptionRateLimitMax: options.redemptionRateLimitMax,
    redemptionRateLimitWindowMs: options.redemptionRateLimitWindowMs,
    publicMode: options.publicMode,
    allowInsecurePublicHttp: options.allowInsecurePublicHttp,
    publicGatewayBaseUrl: options.publicGatewayBaseUrl,
    adminPageCode: options.adminPageCode,
    adminClaimCodes: options.adminClaimCodes,
    newApiEnabled: options.newApiEnabled,
    newApiBaseUrl: options.newApiBaseUrl,
    newApiAccessToken: options.newApiAccessToken,
    newApiUserId: options.newApiUserId,
    newApiDefaultTokenQuota: options.newApiDefaultTokenQuota,
    newApiRequestTimeoutMs: options.newApiRequestTimeoutMs,
    newApiSqliteDb: Object.hasOwn(options, 'newApiSqliteDb') ? options.newApiSqliteDb : '',
    newApiGatewayEnabled: options.newApiGatewayEnabled,
    newApiGatewayBaseUrl: options.newApiGatewayBaseUrl,
    newApiRedemptionStatusSyncEnabled: options.newApiRedemptionStatusSyncEnabled,
    newApiRedemptionStatusSyncIntervalMs: options.newApiRedemptionStatusSyncIntervalMs,
    runtimeBeforeSave: options.runtimeBeforeSave,
    cardAutoreplenishEnabled: options.cardAutoreplenishEnabled,
    cardAutoreplenishIntervalMs: options.cardAutoreplenishIntervalMs,
    cardAutoreplenishDailyCap: options.cardAutoreplenishDailyCap,
    cardAutoreplenishSafetyStock: options.cardAutoreplenishSafetyStock,
    dataEncryptionKey: options.dataEncryptionKey,
    passwordHashSecret: options.passwordHashSecret,
    legacyPasswordHashSecrets: options.legacyPasswordHashSecrets,
    accountEmailSender: options.accountEmailSender,
    passwordResetTtlMs: options.passwordResetTtlMs,
    sessionTtlMs: options.sessionTtlMs,
    paymentEnabled: options.paymentEnabled,
    enforceProductionReadiness: options.enforceProductionReadiness,
    requireNewApiDatabase: options.requireNewApiDatabase,
    requireAdmin2fa: options.requireAdmin2fa,
    adminTotpSecrets: options.adminTotpSecrets,
    admin2faSessionTtlMs: options.admin2faSessionTtlMs,
    backupStatusMaxAgeHours: options.backupStatusMaxAgeHours,
    slaRetentionDays: options.slaRetentionDays,
    requireCsrf: options.requireCsrf,
    allowPrivateUpstreamUrls: options.allowPrivateUpstreamUrls,
    resolveUpstreamAddresses:
      options.resolveUpstreamAddresses ||
      (async (hostname) => {
        if (hostname === 'metadata.example.com') return [{ address: '169.254.169.254', family: 4 }];
        if (hostname === 'localhost') return [{ address: '127.0.0.1', family: 4 }];
        return [{ address: '203.0.113.10', family: 4 }];
      }),
    wechatPayEnabled: options.wechatPayEnabled,
    wechatPayAppId: options.wechatPayAppId,
    wechatPayMchId: options.wechatPayMchId,
    wechatPaySerialNo: options.wechatPaySerialNo,
    wechatPayPrivateKey: options.wechatPayPrivateKey,
    wechatPayPublicKey: options.wechatPayPublicKey,
    wechatPayApiV3Key: options.wechatPayApiV3Key,
    wechatPayGateway: options.wechatPayGateway,
    wechatPayNotifyUrl: options.wechatPayNotifyUrl,
    alipayEnabled: options.alipayEnabled,
    alipayAppId: options.alipayAppId,
    alipayPrivateKey: options.alipayPrivateKey,
    alipayPublicKey: options.alipayPublicKey,
    alipayGateway: options.alipayGateway,
    alipayNotifyUrl: options.alipayNotifyUrl,
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;

  return {
    baseUrl,
    port,
    dataFile,
    async request(path, options = {}) {
      const response = await fetch(`${baseUrl}${path}`, {
        method: options.method || 'GET',
        redirect: options.redirect || 'follow',
        headers: {
          ...(options.body ? { 'content-type': 'application/json' } : {}),
          ...(options.cookie ? { cookie: options.cookie } : {}),
          ...(options.headers || {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
      const text = await response.text();
      return {
        status: response.status,
        setCookie: response.headers.get('set-cookie') || '',
        cookie: response.headers.get('set-cookie')?.split(';')[0] || options.cookie || '',
        location: response.headers.get('location') || '',
        json: parseJsonOrEmpty(text),
        text,
      };
    },
    async rawRequest(path, options = {}) {
      const response = await fetch(`${baseUrl}${path}`, {
        method: options.method || 'GET',
        headers: options.headers || {},
        body: options.bodyText,
      });
      const text = await response.text();
      return {
        status: response.status,
        setCookie: response.headers.get('set-cookie') || '',
        json: parseJsonOrEmpty(text),
        text,
      };
    },
    async readData() {
      return JSON.parse(await readFile(dataFile, 'utf8'));
    },
    async readRawData() {
      return readFile(dataFile, 'utf8');
    },
    async writeData(data) {
      await writeFile(dataFile, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
    },
    async createVerifiedCustomer(email = `user-${Date.now()}@example.com`) {
      const registered = await this.request('/api/frist/register', {
        method: 'POST',
        body: { email, password: 'TestPass123!' },
      });
      await this.request('/api/frist/verify', {
        method: 'POST',
        cookie: registered.cookie,
        body: { code: registered.json.verificationCode },
      });
      return registered.cookie;
    },
    async close() {
      await new Promise((resolve) => server.close(resolve));
      await rm(dir, { force: true, recursive: true });
    },
  };
}

function sendRawHttpRequest({ port, requestText }) {
  return new Promise((resolve, reject) => {
    const socket = connect({ host: '127.0.0.1', port });
    let response = '';
    socket.setEncoding('utf8');
    socket.setTimeout(3000);
    socket.on('connect', () => socket.write(requestText));
    socket.on('data', (chunk) => {
      response += chunk;
    });
    socket.on('end', () => resolve(response));
    socket.on('timeout', () => {
      socket.destroy(new Error('raw HTTP request timed out'));
    });
    socket.on('error', reject);
  });
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function textResponse(status, body, contentType = 'text/html') {
  return new Response(body, {
    status,
    headers: { 'content-type': contentType },
  });
}

function buildWechatNotifyBody({ apiV3Key, transaction }) {
  const nonce = Buffer.from(randomBytes(12).toString('base64url').slice(0, 12), 'utf8');
  const cipher = createCipheriv('aes-256-gcm', Buffer.from(apiV3Key, 'utf8'), nonce);
  const associatedData = 'transaction';
  cipher.setAAD(Buffer.from(associatedData, 'utf8'));
  const encrypted = Buffer.concat([
    cipher.update(JSON.stringify(transaction), 'utf8'),
    cipher.final(),
    cipher.getAuthTag(),
  ]).toString('base64');
  return JSON.stringify({
    id: 'notify-id',
    create_time: '2026-05-04T12:00:00+08:00',
      resource_type: 'encrypt-resource',
    event_type: 'TRANSACTION.SUCCESS',
    resource: {
      algorithm: 'AEAD_AES_256_GCM',
      ciphertext: encrypted,
      associated_data: associatedData,
      nonce: nonce.toString('utf8'),
    },
  });
}

function signWechatNotifyHeaders({ privateKey, bodyText }) {
  const timestamp = '1777777777';
  const nonce = 'notify-nonce';
  const message = `${timestamp}\n${nonce}\n${bodyText}\n`;
  return {
    'wechatpay-timestamp': timestamp,
    'wechatpay-nonce': nonce,
    'wechatpay-signature': createSign('RSA-SHA256').update(message).sign(privateKey, 'base64'),
    'wechatpay-serial': 'TEST-SERIAL',
    'content-type': 'application/json',
  };
}

function signAlipayNotifyBody(params, privateKey) {
  const payload = {
    ...params,
    charset: 'utf-8',
    sign_type: 'RSA2',
    version: '1.0',
    notify_time: '2026-05-04 12:00:00',
  };
  const content = Object.entries(payload)
    .filter(([key, value]) => key !== 'sign' && key !== 'sign_type' && value !== undefined && value !== null && value !== '')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
  payload.sign = createSign('RSA-SHA256').update(content).sign(privateKey, 'base64');
  return new URLSearchParams(payload).toString();
}

function createNewApiRedemptionSchema(sqliteDb) {
  const sql = `
    create table redemptions (
      id integer primary key,
      user_id integer,
      \`key\` char(32) unique,
      status integer default 1,
      name text,
      quota integer default 100,
      created_time integer,
      redeemed_time integer,
      used_user_id integer,
      expired_time integer
    );
  `;
  const result = spawnSync('sqlite3', [sqliteDb], { input: sql, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

function sqliteScalar(sqliteDb, sql) {
  const result = spawnSync('sqlite3', [sqliteDb, sql], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

function sqlQuote(value) {
  return `'${String(value ?? '').replace(/'/g, "''")}'`;
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function waitFor(assertion, { timeoutMs = 800, intervalMs = 25 } = {}) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt <= timeoutMs) {
    try {
      await assertion();
      return;
    } catch (error) {
      lastError = error;
      await delay(intervalMs);
    }
  }
  throw lastError || new Error('waitFor timed out');
}

function legacyPasswordHash(password, salt) {
  return createHash('sha256').update(`${salt}:${password}`).digest('hex');
}

function parseJsonOrEmpty(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function solveRegistrationChallenge(question) {
  const text = String(question || '');
  const arithmetic = text.match(/(\d+)\s*\+\s*(\d+)\s*-\s*(\d+)/);
  if (arithmetic) {
    return String(Number(arithmetic[1]) + Number(arithmetic[2]) - Number(arithmetic[3]));
  }
  const positions = text.match(/验证码\s+([A-Z0-9]+).*第\s*(\d+)\s*和第\s*(\d+)\s*位字符/);
  if (positions) {
    return `${positions[1][Number(positions[2]) - 1]}${positions[1][Number(positions[3]) - 1]}`;
  }
  const reverse = text.match(/把\s+([A-Z0-9]+)\s+倒序输入/);
  if (reverse) {
    return reverse[1].split('').reverse().join('');
  }
  const digits = text.match(/验证码\s+([A-Z0-9]+).*只输入其中的数字/);
  if (digits) {
    return digits[1].replace(/\D/g, '');
  }
  const suffix = text.match(/验证码\s+([A-Z0-9]+).*最后\s*3\s*位/);
  if (suffix) {
    return suffix[1].slice(-3);
  }
  return '';
}

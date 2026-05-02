import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import { createFristApiServer } from '../server/server.js';

describe('Frist-API public server chain', () => {
  it('serves the customer website from the same lightweight server', async () => {
    const fixture = await createServerFixture();

    try {
      const home = await fixture.request('/');
      assert.equal(home.status, 200);
      assert.match(home.text, /Frist-API/);
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
      assert.equal(dashboard.json.account.monthCost, '¥0.00');
      assert.equal(dashboard.json.account.usageTotal, '¥0.00');
      assert.deepEqual(dashboard.json.modelUsage, []);
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
      assert.equal(recharged.json.account.balance, '¥8.00');

      const token = await fixture.request('/api/frist/token', {
        method: 'POST',
        cookie,
        body: { name: 'Claude 日常 Key' },
      });
      assert.equal(token.status, 200);
      assert.match(token.json.key.secret, /^fk-live-/);

      const imported = await fixture.request('/api/frist/import-url?target=Claude&model=claude-haiku', {
        cookie,
      });
      assert.equal(imported.status, 200);
      assert.match(decodeURIComponent(imported.json.url), /target=claude/);
      assert.match(decodeURIComponent(imported.json.url), new RegExp(token.json.key.secret));

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
      assert.equal(pending.json.account.balance, '¥0.00');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.balance, '¥0.00');
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
      assert.equal(credited.json.account.balance, '¥8.00');

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.boosterQuota, '¥8.00');
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
      assert.equal(credited.json.account.packageQuota, '¥8.00');

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
        body: { code: 'FRIST-DAY-001' },
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'charged' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
      });
      await fixture.request('/api/frist/recharge', {
        method: 'POST',
        cookie,
        body: { amountCny: 1, method: 'manual_test' },
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
          models: ['claude-haiku'],
          keys: [{ value: 'sk-billable', quotaRemaining: 1000, latencyMs: 80 }],
        },
      });

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'first' }] },
      });
      assert.equal(first.status, 200);

      const afterFirst = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(afterFirst.json.account.packageQuota, '¥3.00');
      assert.equal(afterFirst.json.account.boosterQuota, '¥1.00');
      assert.equal(afterFirst.json.account.quotaLeft, '¥4.00');
      assert.equal(afterFirst.json.account.todayCost, '¥5.00');
      assert.equal(afterFirst.json.account.todayCalls, '1 次');

      const blocked = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'second' }] },
      });
      assert.equal(blocked.status, 402);
      assert.match(blocked.text, /余额不足/);
      assert.equal(upstreamCalls.length, 1);
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
        body: { code: 'FRIST-DAY-001' },
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
        body: { code: 'FRIST-DAY-001' },
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
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].url, 'https://supplier.example.com/openai/chat/completions');
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-claude-code-openai');
      assert.deepEqual(upstreamCalls[0].body.messages, [
        { role: 'system', content: 'keep claude code system prompt' },
        { role: 'user', content: 'route this as chatgpt' },
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
        body: { code: 'FRIST-DAY-001' },
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
        body: { code: 'FRIST-DAY-001' },
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
        ['gpt-5.4', 'gpt-5.5', 'gpt-image-2'],
      );
      assert.equal(JSON.stringify(models.json).includes('sk-models-day'), false);
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
        body: { code: 'FRIST-DAY-001' },
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
        const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));
        const expectedModels = ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2'];

        assert.equal(imported.status, 200);
        assert.equal(importUrl.searchParams.get('defaultModel'), 'gpt-5.5');
        assert.deepEqual(JSON.parse(importUrl.searchParams.get('availableModels')), expectedModels);
        assert.deepEqual(JSON.parse(importUrl.searchParams.get('available_models')), expectedModels);
        assert.deepEqual(providerConfig.provider.models, expectedModels);
        assert.deepEqual(providerConfig.provider.availableModels, expectedModels);
        assert.equal(providerConfig.provider.defaultModel, 'gpt-5.5');
        assert.deepEqual(providerConfig.codex.availableModels, expectedModels);
      }
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

      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(dashboard.status, 200);
      assert.equal(Array.isArray(dashboard.json.modelCatalog), true);
      const gpt = dashboard.json.modelCatalog.find((item) => item.model === 'gpt-5.5');
      const image = dashboard.json.modelCatalog.find((item) => item.model === 'gpt-image-2');
      assert.equal(gpt.family, 'OpenAI');
      assert.equal(gpt.available, true);
      assert.equal(gpt.price, '¥8/¥48 每 1M');
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
        body: { code: 'FRIST-DAY-001' },
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
          models: ['gpt-image-2'],
          keys: [{ value: 'sk-image-day', quotaRemaining: 900, latencyMs: 80 }],
        },
      });

      const image = await fixture.request('/v1/images/generations', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'gpt-image-2',
          prompt: '生成一张 Frist-API 测试图',
          size: '1024x1024',
        },
      });

      assert.equal(image.status, 200);
      assert.deepEqual(image.json.data, [{ b64_json: 'ZmFrZS1pbWFnZQ==' }]);
      assert.equal(upstreamCalls.length, 1);
      assert.equal(upstreamCalls[0].url, 'https://supplier.example.com/openai/images/generations');
      assert.equal(upstreamCalls[0].authorization, 'Bearer sk-image-day');
      assert.equal(upstreamCalls[0].body.prompt, '生成一张 Frist-API 测试图');
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
                'x-title': 'Frist-API',
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
        body: { code: 'FRIST-DAY-001' },
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
      assert.match(challenge.json.question, /\d+\s*\+\s*\d+/);

      const registered = await fixture.request('/api/frist/register', {
        method: 'POST',
        body: {
          email: 'captcha@example.com',
          password: 'TestPass123!',
          captchaId: challenge.json.id,
          captchaAnswer: solveMathChallenge(challenge.json.question),
        },
      });
      assert.equal(registered.status, 200);
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
      const firstCookie = await fixture.createVerifiedCustomer('first-card@example.com');
      const firstRedeem = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: firstCookie,
        body: { code: 'FRIST-DAY-001' },
      });
      assert.equal(firstRedeem.status, 200);

      const secondCookie = await fixture.createVerifiedCustomer('second-card@example.com');
      const secondRedeem = await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie: secondCookie,
        body: { code: 'FRIST-DAY-001' },
      });
      assert.equal(secondRedeem.status, 409);
      assert.match(secondRedeem.text, /兑换码已使用/);
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'expired' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('expired-day@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
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
      assert.equal(dashboard.json.account.packageQuota, '¥0.00');
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
            data: [{ id: 'claude-haiku' }, { id: 'gpt-5.5' }],
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
      assert.deepEqual(replenished.json.supplierProfile.models, ['claude-haiku', 'gpt-5.5']);
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

  it('aggregates customer channel checks by model instead of exposing one card per upstream key', async () => {
    const fixture = await createServerFixture();

    try {
      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-haiku'],
          keys: [
            { value: 'sk-model-a', quotaRemaining: 900, latencyMs: 120 },
            { value: 'sk-model-b', quotaRemaining: 900, latencyMs: 80 },
          ],
        },
      });

      const dashboard = await fixture.request('/api/frist/dashboard');
      assert.equal(dashboard.status, 200);
      assert.equal(dashboard.json.channelChecks.length, 1);
      assert.equal(dashboard.json.channelChecks[0].model, 'claude-haiku');
      assert.equal(dashboard.json.channelChecks[0].ok, true);
      assert.match(dashboard.json.channelChecks[0].channel, /可用线路 2\/2/);
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
          model: 'claude-haiku',
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
        body: { code: 'FRIST-DAY-001' },
      });

      const replenished = await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-haiku'],
          keys: [
            { value: 'sk-empty', quotaRemaining: 1, latencyMs: 90 },
            { value: 'sk-healthy', quotaRemaining: 900, latencyMs: 120 },
          ],
          priceText: 'claude-haiku input $0.8/1M output $4/1M',
        },
      });
      assert.equal(replenished.status, 200);
      assert.equal(replenished.json.credentials.length, 2);
      assert.equal(JSON.stringify(replenished.json).includes('sk-healthy'), false);

      const gateway = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-haiku',
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
        body: { code: 'FRIST-DAY-001' },
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
        body: { code: 'FRIST-DAY-001' },
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'switched' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
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
          model: 'claude-haiku',
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
          models: ['claude-haiku'],
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'failover' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer();
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
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
          model: 'claude-haiku',
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'sticky' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('sticky-session@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
          keys: [{ value: 'sk-stable', quotaRemaining: 900, latencyMs: 120 }],
        },
      });

      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-alpha',
        },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'first turn' }] },
      });
      assert.equal(first.status, 200);

      await fixture.request('/api/admin/replenishments', {
        method: 'POST',
        headers: { 'x-admin-token': 'admin-test-token' },
        body: {
          baseUrl: 'https://supplier.example.com/v1',
          pool: 'day',
          models: ['claude-haiku'],
          keys: [{ value: 'sk-faster', quotaRemaining: 900, latencyMs: 20 }],
        },
      });

      const secondSameConversation = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-alpha',
        },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'second turn' }] },
      });
      assert.equal(secondSameConversation.status, 200);

      const otherConversation = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.json.key.secret}`,
          'x-frist-session-id': 'conversation-beta',
        },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'new conversation' }] },
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
          model: 'claude-haiku',
          choices: [{ message: { role: 'assistant', content: 'context kept' } }],
        });
      },
    });

    try {
      const cookie = await fixture.createVerifiedCustomer('context-failover@example.com');
      await fixture.request('/api/frist/redeem', {
        method: 'POST',
        cookie,
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
          keys: [
            { value: 'sk-context-bad', quotaRemaining: 900, latencyMs: 30 },
            { value: 'sk-context-good', quotaRemaining: 900, latencyMs: 90 },
          ],
        },
      });

      const fullBody = {
        model: 'claude-haiku',
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
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
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
          model: 'claude-haiku',
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
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
          keys: [{ value: 'sk-restore', quotaRemaining: 10, latencyMs: 90 }],
        },
      });
      const first = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: { model: 'claude-haiku', messages: [{ role: 'user', content: 'first' }] },
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
          models: ['claude-haiku'],
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

  it('uses pasted model pricing and upstream usage to bill gateway calls', async () => {
    const fixture = await createServerFixture({
      fetchImpl: async () =>
        jsonResponse(200, {
          id: 'chatcmpl-priced',
          model: 'claude-haiku',
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
        body: { code: 'FRIST-DAY-001' },
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
          models: ['claude-haiku'],
          keys: [{ value: 'sk-priced', quotaRemaining: 1000, latencyMs: 80 }],
          priceText: 'claude-haiku input ¥1/1M output ¥2/1M',
          pricing: { profitMultiplier: 1, safetyCnyPerMillion: 0 },
        },
      });

      const response = await fixture.request('/v1/chat/completions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.json.key.secret}` },
        body: {
          model: 'claude-haiku',
          messages: [{ role: 'user', content: 'priced request' }],
        },
      });
      assert.equal(response.status, 200);

      const dashboard = await fixture.request('/api/frist/dashboard', { cookie });
      assert.equal(dashboard.json.account.packageQuota, '¥6.00');
      assert.equal(dashboard.json.account.todayCost, '¥2.00');

      const inventory = await fixture.request('/api/admin/replenishments', {
        headers: { 'x-admin-token': 'admin-test-token' },
      });
      assert.equal(inventory.json.credentials[0].quotaRemaining, 800);
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
          model: body.model || 'claude-haiku',
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
          models: ['claude-haiku'],
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
        body: { code: 'FRIST-DAY-001' },
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
          model: 'claude-haiku',
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
      publicGatewayBaseUrl: 'https://gateway.frist-api.dev/v1',
    });
    server.close();

    const temporaryIpServer = createFristApiServer({
      publicMode: true,
      allowInsecurePublicHttp: true,
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      publicGatewayBaseUrl: 'http://101.43.41.96:5566/v1',
    });
    temporaryIpServer.close();
  });

  it('hides the static admin page behind a separate public gate code', async () => {
    const fixture = await createServerFixture({
      publicMode: true,
      allowInsecurePublicHttp: true,
      publicGatewayBaseUrl: 'http://101.43.41.96:5566/v1',
      adminToken: 'admin-token-with-enough-randomness-2026',
      sessionSecret: 'session-secret-with-enough-randomness-2026',
      exposeVerificationCode: false,
      adminPageCode: 'hidden-admin-entry-2026',
    });

    try {
      const blocked = await fixture.request('/admin.html');
      assert.equal(blocked.status, 404);

      const allowed = await fixture.request('/admin.html?code=hidden-admin-entry-2026');
      assert.equal(allowed.status, 200);
      assert.match(allowed.text, /Frist-API Admin/);
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
    fetchImpl: options.fetchImpl,
    nowFactory: options.nowFactory,
    quotaCost: options.quotaCost,
    lowInventoryThresholdRatio: options.lowInventoryThresholdRatio,
    notifyLowInventory: options.notifyLowInventory,
    requireCaptcha: options.requireCaptcha,
    authRateLimitMax: options.authRateLimitMax,
    authRateLimitWindowMs: options.authRateLimitWindowMs,
    publicMode: options.publicMode,
    allowInsecurePublicHttp: options.allowInsecurePublicHttp,
    publicGatewayBaseUrl: options.publicGatewayBaseUrl,
    adminPageCode: options.adminPageCode,
    adminClaimCodes: options.adminClaimCodes,
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;

  return {
    baseUrl,
    async request(path, options = {}) {
      const response = await fetch(`${baseUrl}${path}`, {
        method: options.method || 'GET',
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
        cookie: response.headers.get('set-cookie')?.split(';')[0] || options.cookie || '',
        json: parseJsonOrEmpty(text),
        text,
      };
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

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function parseJsonOrEmpty(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function solveMathChallenge(question) {
  const match = String(question || '').match(/(\d+)\s*\+\s*(\d+)/);
  if (!match) return '';
  return String(Number(match[1]) + Number(match[2]));
}

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  createFristApiDataStore,
  createNewApiClient,
  normalizeNewApiChannels,
  normalizeNewApiTokens,
  normalizeNewApiUsage,
  normalizeNewApiUserSummary,
} from '../src/newApiClient.js';
import { normalizeFristDashboard } from '../src/serverClient.js';

const fallback = {
  accountSummary: {
    userInitials: 'DJ',
    plan: '月卡 Pro',
    balance: '¥81.58',
    todayCost: '¥18.42',
    monthCost: '¥428.90',
    quotaLeft: '¥81.58',
    packageQuota: '¥64.00',
    boosterQuota: '¥17.58',
    usageTotal: '¥428.90',
    todayCalls: '186 次',
    renewalDate: '2026-05-28',
  },
  apiKeys: [{ id: 'fallback-key', name: '演示 Key', preview: 'fk-live-••••••demo', enabled: true }],
  channelChecks: [{ provider: 'Claude', channel: '演示线', ok: true, latencyMs: 300 }],
  modelUsage: [{ model: 'Claude', amount: '¥18.42', percent: 100, calls: '18 次', tokens: '1.00M' }],
};

describe('Frist-API New-API adapter', () => {
  it('normalizes lightweight Frist-API dashboard billing counters instead of keeping demo totals', () => {
    const dashboard = normalizeFristDashboard(
      {
        authenticated: false,
        account: {},
        user: {},
        apiKeys: [],
        channelChecks: [],
        modelUsage: [],
      },
      fallback,
    );

    assert.equal(dashboard.accountSummary.plan, '未登录');
    assert.equal(dashboard.accountSummary.balance, '¥0.00');
    assert.equal(dashboard.accountSummary.monthCost, '¥0.00');
    assert.equal(dashboard.accountSummary.usageTotal, '¥0.00');
    assert.equal(dashboard.accountSummary.todayCalls, '0 次');
    assert.deepEqual(dashboard.modelUsage, [
      { model: 'Claude', amount: '¥0.00', percent: 0, calls: '0 次', tokens: '0.00M' },
    ]);
  });

  it('preserves authenticated dashboard billing counters when the server provides them', () => {
    const dashboard = normalizeFristDashboard(
      {
        authenticated: true,
        account: {
          plan: '日卡',
          balance: '¥4.00',
          quotaLeft: '¥4.00',
          packageQuota: '¥3.00',
          boosterQuota: '¥1.00',
          todayCost: '¥5.00',
          monthCost: '¥5.00',
          usageTotal: '¥5.00',
          todayCalls: '1 次',
          renewalDate: '2026-05-02',
        },
        user: { userInitials: 'CU' },
        apiKeys: [],
        channelChecks: [],
        modelUsage: [],
      },
      fallback,
    );

    assert.equal(dashboard.accountSummary.todayCost, '¥5.00');
    assert.equal(dashboard.accountSummary.monthCost, '¥5.00');
    assert.equal(dashboard.accountSummary.usageTotal, '¥5.00');
    assert.equal(dashboard.accountSummary.todayCalls, '1 次');
  });

  it('normalizes New-API user quota into the customer account summary', () => {
    const summary = normalizeNewApiUserSummary(
      {
        success: true,
        data: {
          username: 'blackdj',
          display_name: 'DJ Black',
          quota: '8158',
          used_quota: 42890,
          request_count: 186,
          group: 'monthly_pro',
          today_quota: 1842,
          subscription_expires_at: 1779926400,
        },
      },
      { quotaPerCny: 100, planNames: { monthly_pro: '月卡 Pro' } },
    );

    assert.deepEqual(summary, {
      userInitials: 'DB',
      plan: '月卡 Pro',
      balance: '¥81.58',
      todayCost: '¥18.42',
      monthCost: '¥428.90',
      quotaLeft: '¥81.58',
      packageQuota: '¥81.58',
      boosterQuota: '¥0.00',
      usageTotal: '¥428.90',
      todayCalls: '186 次',
      renewalDate: '2026-05-28',
    });
  });

  it('normalizes New-API tokens while masking the real key', () => {
    const tokens = normalizeNewApiTokens({
      data: [
        {
          id: 71,
          name: 'Claude 主力',
          key: 'fk-live-real-secret-9x2a',
          status: 1,
          used_quota: 42890,
          remain_quota: 8158,
          accessed_time: 1770000000,
          expired_time: -1,
        },
      ],
    });

    assert.deepEqual(tokens, [
      {
        id: '71',
        name: 'Claude 主力',
        preview: 'fk-live-••••••9x2a',
        enabled: true,
        cost: '¥428.90',
        tokens: '81.58 额度',
        lastUsed: '2026-02-02',
        expiresAt: '-',
      },
    ]);
    assert.equal(JSON.stringify(tokens).includes('real-secret'), false);
  });

  it('groups New-API usage rows by model family for the customer chart', () => {
    const usage = normalizeNewApiUsage(
      {
        data: [
          { model_name: 'claude-sonnet-4-5', quota: 2000, prompt_tokens: 1000000, completion_tokens: 500000, count: 10 },
          { model_name: 'gpt-5.5', quota: 1000, prompt_tokens: 400000, completion_tokens: 100000, count: 4 },
          { model_name: 'claude-haiku-4-5', quota: 1000, prompt_tokens: 600000, completion_tokens: 300000, count: 6 },
        ],
      },
      { quotaPerCny: 100 },
    );

    assert.deepEqual(usage, [
      { model: 'Claude', family: 'Anthropic', percent: 75, amount: '¥30.00', calls: '16 次', tokens: '2.40M' },
      { model: 'OpenAI', family: 'OpenAI', percent: 25, amount: '¥10.00', calls: '4 次', tokens: '0.50M' },
    ]);
  });

  it('normalizes channel health without leaking upstream channel ids or keys', () => {
    const channels = normalizeNewApiChannels({
      data: [
        {
          id: 88,
          provider: 'OpenAI',
          name: 'Codex Pro',
          model: 'gpt-5.5',
          base_url: 'https://supplier.example.com/v1',
          endpoint: 'https://api.frist.example.com/openai/pro',
          response_time_ms: 1771,
          ping_ms: 91,
          success_rate: 0.9924,
          success_count: 9994,
          total_count: 10071,
          status: 'healthy',
          key: 'sk-upstream-secret',
        },
      ],
    });

    assert.equal(channels[0].provider, 'OpenAI');
    assert.equal(channels[0].channel, 'Codex Pro');
    assert.equal(channels[0].endpoint, 'https://api.frist.example.com/openai/pro');
    assert.equal(channels[0].availability, '99.24%');
    assert.equal(channels[0].successLabel, '9994/10071 成功');
    assert.equal(JSON.stringify(channels).includes('88'), false);
    assert.equal(JSON.stringify(channels).includes('upstream-secret'), false);
    assert.equal(JSON.stringify(channels).includes('supplier.example.com'), false);
  });

  it('falls back to demo data when New-API is unavailable', async () => {
    const store = createFristApiDataStore({
      fallback,
      client: {
        getStatus: async () => {
          throw new Error('New-API offline');
        },
      },
    });

    assert.deepEqual(await store.load(), fallback);
  });

  it('merges successful New-API slices while keeping fallback for missing optional endpoints', async () => {
    const store = createFristApiDataStore({
      fallback,
      config: { quotaPerCny: 100, planNames: { default: '默认套餐' } },
      client: {
        getStatus: async () => ({ data: { quota_per_unit: 100 } }),
        getUserSelf: async () => ({ data: { username: 'first_user', quota: 1200, used_quota: 300, group: 'default' } }),
        getTokens: async () => ({ data: [{ id: 1, name: '生产 Key', key: 'fk-live-abc123456789', status: 1 }] }),
        getUsage: async () => {
          throw new Error('usage endpoint missing');
        },
        getChannelHealth: async () => {
          throw new Error('channel endpoint missing');
        },
      },
    });

    const data = await store.load();
    assert.equal(data.accountSummary.balance, '¥12.00');
    assert.equal(data.accountSummary.plan, '默认套餐');
    assert.equal(data.apiKeys[0].name, '生产 Key');
    assert.deepEqual(data.modelUsage, fallback.modelUsage);
    assert.deepEqual(data.channelChecks, fallback.channelChecks);
  });

  it('creates a session-based New-API client without sending user API keys from the browser', async () => {
    const calls = [];
    const client = createNewApiClient({
      baseUrl: 'https://new-api.example.com/',
      fetchImpl: async (url, init) => {
        calls.push({ url, init });
        return {
          ok: true,
          json: async () => ({ success: true, data: {} }),
        };
      },
    });

    await client.getUserSelf();
    await client.getTokens();

    assert.deepEqual(
      calls.map((call) => call.url),
      ['https://new-api.example.com/api/user/self', 'https://new-api.example.com/api/token/'],
    );
    assert.equal(calls[0].init.credentials, 'include');
    assert.equal(Object.hasOwn(calls[0].init.headers, 'Authorization'), false);
  });

  it('wires the page through the New-API data store instead of hard-coded demo arrays', () => {
    const appSource = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');

    assert.equal(appSource.includes('createFristApiDataStore'), true);
    assert.equal(appSource.includes('loadDashboardData'), true);
    assert.equal(/import\s*{[^}]*accountSummary/s.test(appSource), false);
    assert.equal(/import\s*{[^}]*channelChecks/s.test(appSource), false);
  });
});

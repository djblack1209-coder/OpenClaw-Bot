import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  createNewApiClient,
  normalizeNewApiChannels,
  normalizeNewApiTokens,
  normalizeNewApiUsage,
  normalizeNewApiUserSummary,
} from '../src/newApiClient.js';
import { normalizeFristDashboard } from '../src/serverClient.js';

const previousDashboard = {
  accountSummary: {
    userInitials: 'DJ',
    plan: '历史套餐',
    balance: '$11.33',
    todayCost: '$2.56',
    monthCost: '$59.57',
    quotaLeft: '$11.33',
    packageQuota: '$8.89',
    boosterQuota: '$2.44',
    usageTotal: '$59.57',
    todayCalls: '186 次',
    renewalDate: '2026-05-28',
  },
  apiKeys: [{ id: 'previous-key', name: '历史 Key', preview: 'sk-••••••prev', enabled: true }],
  channelChecks: [{ provider: 'Claude', channel: '历史线路', ok: true, latencyMs: 300 }],
  modelUsage: [{ model: 'Claude', amount: '$2.56', percent: 100, calls: '18 次', tokens: '1.00M' }],
};

describe('Frist-API New-API adapter', () => {
  it('normalizes lightweight Frist-API dashboard billing counters instead of keeping stale totals', () => {
    const dashboard = normalizeFristDashboard(
      {
        authenticated: false,
        account: {},
        user: {},
        apiKeys: [],
        channelChecks: [],
        modelUsage: [],
      },
      previousDashboard,
    );

    assert.equal(dashboard.accountSummary.plan, '未登录');
    assert.equal(dashboard.accountSummary.balance, '$0.00');
    assert.equal(dashboard.accountSummary.monthCost, '$0.00');
    assert.equal(dashboard.accountSummary.usageTotal, '$0.00');
    assert.equal(dashboard.accountSummary.todayCalls, '0 次');
    assert.deepEqual(dashboard.channelChecks, []);
    assert.deepEqual(dashboard.usageAnomalies, []);
    assert.deepEqual(dashboard.modelUsage, [
      { model: 'Claude', amount: '$0.00', percent: 0, calls: '0 次', tokens: '0.00M' },
    ]);
  });

  it('returns empty public dashboard state when no fallback is provided', () => {
    const dashboard = normalizeFristDashboard({
      authenticated: false,
      account: {},
      user: {},
      apiKeys: [],
      channelChecks: [],
      modelUsage: [],
    });

    assert.equal(dashboard.accountSummary.plan, '未登录');
    assert.equal(dashboard.apiKeys.length, 0);
    assert.equal(dashboard.channelChecks.length, 0);
    assert.equal(dashboard.modelUsage.length, 0);
  });

  it('preserves authenticated dashboard billing counters when the server provides them', () => {
    const dashboard = normalizeFristDashboard(
      {
        authenticated: true,
        account: {
          plan: '日卡',
          balance: '$0.56',
          quotaLeft: '$0.56',
          packageQuota: '$0.42',
          boosterQuota: '$0.14',
          todayCost: '$0.69',
          monthCost: '$0.69',
          usageTotal: '$0.69',
          todayCalls: '1 次',
          renewalDate: '2026-05-02',
        },
        user: { userInitials: 'CU' },
        apiKeys: [],
        channelChecks: [],
        modelUsage: [],
      },
      previousDashboard,
    );

    assert.equal(dashboard.accountSummary.todayCost, '$0.69');
    assert.equal(dashboard.accountSummary.monthCost, '$0.69');
    assert.equal(dashboard.accountSummary.usageTotal, '$0.69');
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
      balance: '$11.33',
      todayCost: '$2.56',
      monthCost: '$59.57',
      quotaLeft: '$11.33',
      packageQuota: '$11.33',
      boosterQuota: '$0.00',
      usageTotal: '$59.57',
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
        cost: '$59.57',
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
      { model: 'Claude', family: 'Anthropic', percent: 75, amount: '$4.17', calls: '16 次', tokens: '2.40M' },
      { model: 'OpenAI', family: 'OpenAI', percent: 25, amount: '$1.39', calls: '4 次', tokens: '0.50M' },
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

  it('normalizes Frist channel monitor fields for the customer dashboard', () => {
    const dashboard = normalizeFristDashboard({
      authenticated: false,
      account: {},
      user: {},
      apiKeys: [],
      modelUsage: [],
      channelChecks: [
        {
          provider: 'OpenAI',
          model: 'gpt-5.5',
          endpoint: '/v1',
          ok: true,
          latencyMs: 90,
          averageLatencyMs: 995,
          healthyCount: 2,
          totalCount: 3,
          downCount: 1,
          slowCount: 1,
          monitorStatus: '降级',
          availability: '66.7%',
          availability7d: 66.7,
          availabilityWindow: '当前库存快照',
          successLabel: '2/3 可用',
          latencyLabel: '最低 90ms / 平均 995ms',
          monitorIntervalSeconds: 60,
          history: ['ok', 'slow', 'down'],
        },
      ],
    });

    assert.equal(dashboard.channelChecks[0].endpoint, '/v1');
    assert.equal(dashboard.channelChecks[0].monitorStatus, '降级');
    assert.equal(dashboard.channelChecks[0].officialStatus, '降级');
    assert.equal(dashboard.channelChecks[0].successLabel, '2/3 可用');
    assert.equal(dashboard.channelChecks[0].latencyLabel, '最低 90ms / 平均 995ms');
    assert.equal(dashboard.channelChecks[0].monitorIntervalSeconds, 60);
    assert.equal(dashboard.channelChecks[0].availabilityWindow, '当前库存快照');
    assert.deepEqual(dashboard.channelChecks[0].history, ['ok', 'slow', 'down']);
  });

  it('normalizes Frist usage anomaly alerts without leaking raw usage internals', () => {
    const dashboard = normalizeFristDashboard({
      authenticated: true,
      account: { plan: '日卡' },
      user: { userInitials: 'UA' },
      apiKeys: [],
      modelUsage: [],
      channelChecks: [],
      usageAnomalies: [
        {
          id: 'spike',
          severity: 'critical',
          title: '今日消耗偏高',
          detail: '今日已用 $0.69',
          action: '建议检查记录页和 Key 使用方',
          rawKey: 'sk-upstream-secret',
        },
      ],
    });

    assert.deepEqual(dashboard.usageAnomalies, [
      {
        id: 'spike',
        severity: 'critical',
        title: '今日消耗偏高',
        detail: '今日已用 $0.69',
        action: '建议检查记录页和 Key 使用方',
        at: '',
      },
    ]);
    assert.equal(JSON.stringify(dashboard.usageAnomalies).includes('upstream-secret'), false);
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

  it('wires the page through the real Frist server dashboard without local fallbacks', () => {
    const appSource = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');

    assert.equal(appSource.includes('createFristApiBrowserClient'), true);
    assert.equal(appSource.includes('loadDashboardData'), true);
    assert.equal(appSource.includes('createFristApiDataStore'), false);
    assert.equal(appSource.includes("from './data.js'"), false);
    assert.equal(appSource.includes('store.load()'), false);
    assert.equal(/import\s*{[^}]*accountSummary/s.test(appSource), false);
    assert.equal(/import\s*{[^}]*channelChecks/s.test(appSource), false);
  });
});

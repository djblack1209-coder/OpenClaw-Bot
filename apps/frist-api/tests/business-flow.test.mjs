import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  applyRecharge,
  applyReplenishmentReport,
  buildBusinessClientConfig,
  buildBusinessImportUrl,
  createBusinessStateFromDashboard,
  createCustomerKey,
  createReplenishmentReport,
  createReplenishmentReportFromOrderText,
  deriveDashboardData,
  redeemCode,
  registerCustomer,
  routeModelRequest,
  setCustomerKeyEnabled,
  verifyCustomerEmail,
} from '../src/businessFlow.js';

const dashboardSeed = {
  accountSummary: {
    userInitials: 'DJ',
    plan: '月卡 Pro',
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
  apiKeys: [
    {
      id: 'key-main',
      name: '主力 Key',
      preview: 'fk-live-••••••9x2a',
      enabled: true,
      cost: '$59.57',
      tokens: '25.58M',
      lastUsed: '20:16',
      expiresAt: '-',
    },
  ],
  channelChecks: [
    {
      provider: 'Claude',
      channel: '官渠主线',
      model: 'claude-opus-4-6-thinking-c',
      endpoint: 'https://api.frist.example.com/claude/office',
      ok: true,
      latencyMs: 1912,
      pingMs: 87,
      checkedAt: '20:16',
      officialStatus: '正常',
      availability: '89.65%',
      successLabel: '8101/9036 成功',
      history: ['ok', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'down', 'ok', 'ok', 'ok'],
      replacement: 'Claude 备用线',
    },
    {
      provider: 'OpenAI',
      channel: 'Codex Pro',
      model: 'gpt-5.5',
      endpoint: 'https://api.frist.example.com/openai/pro',
      ok: true,
      latencyMs: 1771,
      pingMs: 196,
      checkedAt: '20:16',
      officialStatus: '降级',
      availability: '99.24%',
      successLabel: '9994/10071 成功',
      history: ['ok', 'ok', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'slow', 'ok', 'ok'],
      replacement: 'Codex Plus',
    },
  ],
  modelUsage: [
    { model: 'Claude', family: 'Anthropic', percent: 42, amount: '$24.89', calls: '326 次', tokens: '9.83M' },
    { model: 'OpenAI', family: 'OpenAI', percent: 31, amount: '$18.47', calls: '284 次', tokens: '8.12M' },
  ],
  rechargeOptions: [
    { label: 'Codex API 30刀额度/日卡', caption: '1 天', plan: 'day', cny: '¥5.88', active: true },
    { label: 'Codex API 30刀额度/不限时', caption: '不限时', plan: 'balance', cny: '¥8.88', active: false },
  ],
};

describe('Frist-API customer business chain', () => {
  it('runs register, verify, recharge, create key, toggle key and CC Switch import as one customer flow', () => {
    let state = createBusinessStateFromDashboard(dashboardSeed, {
      idFactory: createIds(['user-1', 'key-1']),
      now: '2026-05-01T20:00:00.000Z',
    });

    const registered = registerCustomer(state, {
      email: 'customer@example.com',
      password: 'TestPass123!',
    });
    state = registered.state;
    assert.equal(state.customer.emailVerified, false);
    assert.equal(registered.verificationCode.length, 6);

    state = verifyCustomerEmail(state, { code: registered.verificationCode });
    state = applyRecharge(state, { amountCny: 8, method: 'manual_demo' });
    const created = createCustomerKey(state, { name: 'Claude 主力 Key', modelGroup: 'Claude' });
    state = created.state;

    assert.equal(created.key.secret, 'fk-live-user-1-key-1');
    assert.equal(state.apiKeys[0].enabled, true);
    assert.equal(state.apiKeys[0].modelGroup, 'Claude');
    assert.equal(deriveDashboardData(state, dashboardSeed).accountSummary.balance, '$2.68');

    state = setCustomerKeyEnabled(state, { id: 'key-1', enabled: false });
    assert.throws(() => buildBusinessImportUrl(state, { target: 'Claude', baseUrl: 'https://api.frist.example.com/v1' }), /没有可用的 API Key/);

    state = setCustomerKeyEnabled(state, { id: 'key-1', enabled: true });
    const importUrl = buildBusinessImportUrl(state, {
      target: 'Claude',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'claude-haiku-4-5-20251001',
    });

    assert.match(importUrl, /^ccswitch:\/\/v1\/import\?/);
    assert.match(decodeURIComponent(importUrl), /target=claude/);
    assert.match(decodeURIComponent(importUrl), /fk-live-user-1-key-1/);

    const codexConfig = buildBusinessClientConfig(state, {
      target: 'Codex',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.5',
    });
    assert.match(codexConfig.configToml, /wire_api = "responses"/);
    assert.match(codexConfig.authJson, /OPENAI_API_KEY/);
  });

  it('redeems day-card codes without exposing internal pool names to the customer dashboard', () => {
    let state = createBusinessStateFromDashboard(dashboardSeed, {
      now: '2026-05-01T20:00:00.000Z',
    });

    state = redeemCode(state, { code: 'FRIST-DAY-001' });
    const customerData = deriveDashboardData(state, dashboardSeed);

    assert.equal(customerData.accountSummary.plan, '日卡');
    assert.equal(customerData.accountSummary.renewalDate, '2026-05-02');
    assert.equal(JSON.stringify(customerData).includes('day-pool'), false);
  });
});

describe('Frist-API management replenishment chain', () => {
  it('cleans pasted order details into replenishment report inputs without exposing raw supplier data to users', () => {
    const report = createReplenishmentReportFromOrderText({
      orderText: `
      商品名称: CodexAPI 30刀额度 日卡
      订单金额: ￥3.87
      数量: 2
      密码：cr_fakecodex111111111111111111111111111111111111111111111111111111
      密码：cr_fakecodex222222222222222222222222222222222222222222222222222222
      模型：gpt-5.4、gpt-5.5、gpt-image-2模型
      地址: https://supplier-codex.example.com/openai
      `,
      modelProbe: { supported: true },
      keyProbes: {
        cr_fakecodex111111111111111111111111111111111111111111111111111111: { ok: true, latencyMs: 120 },
        cr_fakecodex222222222222222222222222222222222222222222222222222222: { ok: true, latencyMs: 140 },
      },
      pricing: { usdToCny: 7.2 },
    });

    assert.equal(report.baseUrl, 'https://supplier-codex.example.com/openai');
    assert.equal(report.pool, 'day');
    assert.equal(report.providerGroup, 'OpenAI');
    assert.equal(report.cardType, 'day');
    assert.equal(report.credentials.length, 2);
    assert.equal(report.credentials[0].modelGroup, 'OpenAI');
    assert.equal(report.credentials[0].quotaRemaining, 21600);
    assert.equal(JSON.stringify(report).includes('cr_fakecodex111111'), false, '报告展示层不能包含完整上游 Key');
  });

  it('turns one supplier URL, many keys and pasted prices into a safe replenishment report', () => {
    const report = createReplenishmentReport({
      baseUrl: ' supplier.example.com/v1/ ',
      keys: ['sk-good-1', 'sk-bad-2'],
      pool: 'day',
      priceText: 'claude-haiku input $0.8/1M output $4/1M',
      modelProbe: {
        supported: true,
        models: ['claude-haiku', 'gpt-5.5'],
      },
      keyProbes: {
        'sk-good-1': { ok: true, quotaRemaining: 1200, latencyMs: 210 },
        'sk-bad-2': { ok: false, reason: '余额不足' },
      },
      connectionProbe: {
        direct: { ok: true, p95Ms: 360, failureRate: 0.01 },
        proxy: { ok: true, p95Ms: 820, failureRate: 0.02 },
      },
      pricing: { usdToCny: 7.2, profitMultiplier: 1.35, safetyCnyPerMillion: 0.2 },
    });

    assert.equal(report.baseUrl, 'https://supplier.example.com/v1');
    assert.equal(report.connectionPath, 'direct');
    assert.deepEqual(report.models, ['claude-haiku', 'gpt-5.5']);
    assert.equal(report.keyResults[0].status, 'healthy');
    assert.equal(report.keyResults[1].status, 'failed');
    assert.equal(report.credentials.length, 1);
    assert.equal(report.priceDrafts[0].status, 'needs_admin_confirmation');
  });

  it('keeps backup replenishment reports quarantined until manual approval is explicit', () => {
    const quarantined = createReplenishmentReport({
      baseUrl: 'https://cpa-backup.example.com/v1',
      keys: ['sk-cpa-json'],
      pool: 'day',
      sourceType: 'cpa_json_backup',
      riskStatus: 'quarantined',
      backupRiskAccepted: false,
      riskNote: '只登记，不路由',
      modelProbe: { supported: true, models: ['gpt-5.5'] },
      keyProbes: {
        'sk-cpa-json': { ok: true, quotaRemaining: 900, latencyMs: 220 },
      },
      connectionProbe: {
        direct: { ok: true, p95Ms: 300, failureRate: 0.01 },
      },
    });
    assert.equal(quarantined.credentials[0].sourceType, 'cpa_json_backup');
    assert.equal(quarantined.credentials[0].status, 'quarantined');
    assert.equal(quarantined.credentials[0].enabled, false);

    const approved = createReplenishmentReport({
      baseUrl: 'https://chong-backup.example.com/v1',
      keys: ['sk-chong-backup'],
      pool: 'day',
      sourceType: 'chong_backup',
      riskStatus: 'approved',
      backupRiskAccepted: true,
      modelProbe: { supported: true, models: ['gpt-5.5'] },
      keyProbes: {
        'sk-chong-backup': { ok: true, quotaRemaining: 900, latencyMs: 180 },
      },
      connectionProbe: {
        direct: { ok: true, p95Ms: 260, failureRate: 0.01 },
      },
    });
    assert.equal(approved.credentials[0].status, 'healthy');
    assert.equal(approved.credentials[0].enabled, true);
  });

  it('applies replenishment and automatically skips exhausted day-card credentials on routing', () => {
    let state = createBusinessStateFromDashboard(dashboardSeed, {
      idFactory: createIds(['cred-1', 'cred-2']),
      now: '2026-05-01T20:00:00.000Z',
    });

    const report = createReplenishmentReport({
      baseUrl: 'https://supplier.example.com/v1',
      keys: ['sk-nearly-empty', 'sk-healthy'],
      pool: 'day',
      modelProbe: { supported: true, models: ['claude-haiku'] },
      keyProbes: {
        'sk-nearly-empty': { ok: true, quotaRemaining: 5, latencyMs: 100 },
        'sk-healthy': { ok: true, quotaRemaining: 900, latencyMs: 180 },
      },
      connectionProbe: {
        direct: { ok: true, p95Ms: 300, failureRate: 0.01 },
        proxy: { ok: false, p95Ms: 0, failureRate: 1 },
      },
    });

    state = applyReplenishmentReport(state, report);
    const routed = routeModelRequest(state, {
      model: 'claude-haiku',
      pool: 'day',
      quotaCost: 10,
    });

    assert.equal(routed.credentialId, 'cred-2');
    assert.equal(routed.state.credentials.find((item) => item.id === 'cred-1').status, 'exhausted');
    assert.equal(routed.state.credentials.find((item) => item.id === 'cred-2').quotaRemaining, 890);
  });

  it('routes through the shortest-lived compatible pool before monthly or unlimited stock', () => {
    let state = createBusinessStateFromDashboard(dashboardSeed, {
      idFactory: createIds(['cred-hour', 'cred-day', 'cred-month', 'cred-unlimited']),
      now: '2026-05-01T20:00:00.000Z',
    });
    state.credentials = [
      {
        id: 'cred-unlimited',
        pool: 'unlimited',
        enabled: true,
        status: 'healthy',
        models: ['gpt-5.5'],
        quotaRemaining: 999999,
        latencyMs: 20,
      },
      {
        id: 'cred-month',
        pool: 'month',
        enabled: true,
        status: 'healthy',
        models: ['gpt-5.5'],
        quotaRemaining: 50000,
        latencyMs: 50,
      },
      {
        id: 'cred-day',
        pool: 'day',
        enabled: true,
        status: 'healthy',
        models: ['gpt-5.5'],
        quotaRemaining: 30000,
        latencyMs: 200,
      },
      {
        id: 'cred-hour',
        pool: 'hour',
        enabled: true,
        status: 'healthy',
        models: ['gpt-5.5'],
        quotaRemaining: 5,
        latencyMs: 10,
      },
    ];

    const routed = routeModelRequest(state, {
      model: 'gpt-5.5',
      allowedPools: ['hour', 'day', 'month', 'unlimited'],
      quotaCost: 10,
    });

    assert.equal(routed.credentialId, 'cred-day');
    assert.equal(routed.state.credentials.find((item) => item.id === 'cred-hour').status, 'exhausted');
    assert.equal(routed.state.credentials.find((item) => item.id === 'cred-day').quotaRemaining, 29990);
  });
});

describe('Frist-API page business wiring', () => {
  const page = [
    readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/serverClient.js', import.meta.url), 'utf8'),
  ].join('\n');

  it('exposes customer business actions without adding management screens to the user page', () => {
    for (const required of [
      'data-register-account',
      'data-login-account',
      'data-change-password',
      'data-new-password',
      'data-captcha-question',
      'data-captcha-answer',
      'data-owner-claim-code',
      'data-owner-claim',
      'data-owner-entry',
      'data-auth-dialog',
      'data-auth-mode',
      'data-auth-close',
      'data-model-group',
      'data-create-key',
      'data-pay-submit',
      'data-redeem-code',
      'data-refresh-health',
      'data-server-recovery',
      'data-retry-dashboard',
      'data-action-message',
      'data-auth-feedback',
      'data-key-feedback',
    ]) {
      assert.equal(page.includes(required), true, `${required} 应该接入客户侧业务动作`);
    }

    for (const forbidden of ['补号助手', '号源写入', '渠道写入']) {
      assert.equal(page.includes(forbidden), false, `${forbidden} 不应该出现在用户端`);
    }

    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    assert.equal(userHtml.includes('value="TestPass123!"'), false, '公开用户页不应该预填演示密码');
    assert.equal(userHtml.includes('account-flow'), false, '注册登录不能作为 API 管理正文模块出现');
    assert.equal(userHtml.includes('data-verify-code'), false, '公开用户页不应该把验证码输入堆到客户菜单里');
    assert.equal(userHtml.includes('role="dialog"'), true, '注册登录应该使用可聚焦弹窗承载');
    assert.equal(userHtml.includes('aria-modal="true"'), true, '账户弹窗应该向辅助技术声明模态语义');
    assert.equal(userHtml.includes('role="tab"'), true, '登录/注册切换应该使用明确的 tab 语义');
    assert.equal(userHtml.includes('data-auth-submit="login"'), true, '登录模式只应该显示登录提交按钮');
    assert.equal(userHtml.includes('data-auth-submit="register"'), true, '注册模式只应该显示注册提交按钮');
    assert.equal(userHtml.includes('data-password-row'), true, '改密码入口应该与登录态分离，避免游客注册时困惑');
    assert.equal(page.includes('authSubmit'), true, '账户弹窗渲染时应该按当前模式隐藏无关提交动作');
    assert.equal(page.includes('aria-selected'), true, '账户模式切换应该同步辅助技术选中状态');
    assert.equal(page.includes('.auth-panel__actions [hidden]'), true, '账户弹窗按钮隐藏态不能被通用按钮样式覆盖');
    assert.equal(page.includes('/api/frist/challenge'), true, '公开注册应该接入安全挑战，避免机器人批量撞库');
    assert.equal(page.includes('/api/frist/admin/claim'), true, '管理员身份码应该从用户账号侧一次性激活');
    assert.equal(page.includes('challenge.required !== false'), true, '前端只应在服务端要求时强制填写安全验证');
    assert.equal(page.includes('requireCaptcha: true'), true, '登录不应再强制验证码，注册才需要服务端挑战');
    assert.equal(page.includes('captchaId'), true, '注册请求应该带服务端挑战 ID');
    assert.equal(page.includes('captchaAnswer'), true, '注册请求应该带用户填写的挑战答案');
    assert.equal(page.includes('data-admin-token'), false, '用户端不能暴露管理 API 令牌输入框');
  });

  it('shows explicit success and failure feedback for login, key creation and health refresh', () => {
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

    for (const required of [
      "setActionMessage('登录中",
      "setActionMessage('登录成功",
      "setActionMessage(serverError.message",
      "setScopedFeedback('[data-auth-feedback]'",
      "setScopedFeedback('[data-key-feedback]'",
      'setButtonBusy(createKey',
      'setButtonBusy(login',
      'handleRefreshHealth(event)',
      'handleRetryDashboard',
      'event?.preventDefault()',
      "setActionMessage('连通性刷新中",
      "setActionMessage('正在重新连接",
      "setActionMessage('连通性已刷新",
    ]) {
      assert.equal(appScript.includes(required), true, `${required} 应该让关键动作有明确反馈`);
    }

    for (const required of [
      '.action-message.is-visible',
      '.action-message--success',
      '.action-message--error',
      '.field-feedback',
      '.field-feedback--error',
      '.field-feedback--success',
      '.provider-models',
      '.provider-meta',
      '.server-recovery',
    ]) {
      assert.equal(styles.includes(required), true, `${required} 应该支撑明显反馈和升级后的连通性展示`);
    }
  });

  it('renders client target selection and generated config snippets on the import page', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const switchPanel =
      userHtml.match(/<section class="view-panel" data-view="switch"[\s\S]*?<\/main>/)?.[0] ||
      '';
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');

    for (const required of [
      'data-import-targets',
      'data-import-link',
      'data-open-import',
      'data-export-default-model',
      'data-export-model-count',
      'data-export-models',
      'data-auth-json',
      'data-config-toml',
      'data-copy-auth-json',
      'data-copy-config-toml',
      'data-opencode-config-card',
      'data-opencode-provider-json',
      'data-copy-opencode-config',
      'Codex',
      'Gemini',
      'OpenCode',
      'OpenCode 完整配置',
      'OpenClaw',
      'Hermes',
      'Harmes',
      'data-import-family-option="DeepSeek"',
      'data-import-family-option="Gemini"',
    ]) {
      assert.equal(switchPanel.includes(required), true, `${required} 应该出现在导入页面`);
    }

    for (const required of [
      'renderExportModelSummary',
      'renderOpenCodeConfig',
      'availableModelsForGroup',
      'defaultModelForGroup',
      'data-export-model-chip',
      'openCodeProviderJson',
    ]) {
      assert.equal(appScript.includes(required), true, `${required} 应该让导入页展示完整模型清单`);
    }
    assert.match(
      appScript,
      /state\.target = button\.dataset\.target;[\s\S]*renderImportLink\(\);[\s\S]*renderClientConfig\(\);/,
      '切换 Codex/OpenCode 目标后应该同步刷新手动配置和模型清单',
    );
    assert.match(
      appScript,
      /state\.modelGroup = modelGroup\.dataset\.modelGroupOption[\s\S]*renderImportLink\(\);[\s\S]*renderClientConfig\(\);/,
      '切换模型分组后应该同步刷新导入配置',
    );
  });

  it('wires the expanded customer shell pages, API search, endpoint display and usage records', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
    const combined = `${userHtml}\n${appScript}\n${styles}`;

    for (const view of ['records', 'subscription', 'redeem', 'invite', 'profile']) {
      assert.equal(userHtml.includes(`data-view="${view}"`), true, `${view} 页面应该存在`);
      assert.equal(userHtml.includes(`data-route="${view}"`), true, `${view} 应该能从工作台进入`);
    }

    for (const required of [
      'data-api-search',
      '搜索名称或 key',
      'key-endpoint',
      'icon-button',
      'data-token-trend',
      'data-recent-logs',
      'data-usage-records',
      'data-usage-records-empty',
      'API 密钥',
      '推理强度',
      '计费模式',
      'renderTrendChart',
      'renderRecentLogs',
      'renderUsageRecords',
      'usageRecords',
      'recentLogs',
      'manual-collection-panel',
      'profile-surface',
      'subscription-surface',
      'records-table',
    ]) {
      assert.equal(combined.includes(required), true, `${required} 应该接入新版用户壳`);
    }
  });

  it('guides customers through cross-family CC Switch imports and Claude developer mode', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
    const switchPanel =
      userHtml.match(/<section class="view-panel" data-view="switch"[\s\S]*?<\/main>/)?.[0] ||
      '';

    for (const required of [
      'data-import-family',
      'data-import-family-option="OpenAI"',
      'data-import-family-option="Claude"',
      'data-import-primary-row',
      'danger-text',
      'data-cross-import-title',
      'data-cross-import-copy',
      'data-claude-developer-guide',
      'data-claude-guide-step',
      'data-walkthrough="openai-to-claude"',
      'data-walkthrough="claude-to-codex"',
      'data-copy-flow-codex-toml',
      'data-flow-codex-toml',
      'Configure Third-Party Inference...',
      'Gateway base URL',
      'Gateway API key',
      'Gateway auth scheme',
      'Skip login-mode chooser',
      'API 请求地址',
      'wire_api = "responses"',
      '[mcp_servers.playwright]',
      '开发者模式',
      '第三方 API',
      '一键导入',
    ]) {
      assert.equal(switchPanel.includes(required), true, `${required} 应该解释跨模型家族导入`);
    }
    assert.ok(
      switchPanel.indexOf('data-import-primary-row') < switchPanel.indexOf('data-walkthrough="openai-to-claude"'),
      '一键导入主操作应该在长教程流程图之前，避免用户先被教程淹没',
    );

    for (const required of [
      'renderCrossImportGuide',
      'data-import-family-option',
      'state.modelGroup = family.dataset.importFamilyOption',
      'cross-import-guide',
      'Codex 最强开发配置',
      '@playwright/mcp@latest',
      'superpowers-mcp@latest',
      'open-computer-use@latest',
      'data-copy-flow-codex-toml',
      'syncWalkthroughFields',
      'setActiveWalkthrough',
      'data-flow-claude-base',
      'data-flow-codex-base',
    ]) {
      assert.equal(`${switchPanel}\n${appScript}\n${styles}`.includes(required), true, `${required} 应该接入导入页状态和样式`);
    }
  });

  it('documents the payment last-mile work that still needs the operator', () => {
    const runbook = readFileSync(new URL('../../../docs/007-operations.md', import.meta.url), 'utf8');

    for (const required of [
      '支付宝当面付',
      '微信支付 Native',
      '商户号',
      '签名密钥',
      '异步通知',
      '收款二维码',
      '人工确认入账',
      '不要把密钥发到聊天里',
    ]) {
      assert.equal(runbook.includes(required), true, `${required} 应该写入支付最后一公里手册`);
    }
  });

  it('wires the new customer playground, analytics, model catalog and guide pages', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const serverClient = readFileSync(new URL('../src/serverClient.js', import.meta.url), 'utf8');
    const combined = `${userHtml}\n${appScript}\n${serverClient}`;

    for (const view of ['playground', 'analytics', 'models', 'docs']) {
      assert.equal(userHtml.includes(`data-view="${view}"`), true, `${view} 应该作为用户侧独立页面存在`);
      assert.equal(userHtml.includes(`data-route="${view}"`), true, `${view} 应该能从首页动作入口进入`);
    }

    for (const required of [
      'data-playground-model',
      'data-playground-model-search',
      'data-playground-model-grid',
      'data-playground-family-filter',
      'data-playground-selected-model',
      'data-playground-diagnostics',
      'data-playground-suggestion',
      'data-playground-send',
      'data-playground-test',
      'data-playground-status',
      'data-image-output',
      'data-delete-message',
      'data-clear-playground',
      'filteredPlaygroundModels',
      'renderSelectedPlaygroundModel',
      'renderPlaygroundDiagnostics',
      'data-model-catalog-search',
      'data-select-playground-model',
      'buildImageRequestBody',
      "quality: 'low'",
      "output_format: 'png'",
      'data-usage-donut',
      'data-service-health',
      'data-model-catalog',
      'data-mac-command',
      'data-win-command',
      'data-copy-mac-command',
      'data-copy-win-command',
      "event.key === 'Enter'",
      '!event.shiftKey',
      'handlePlaygroundSend()',
      'renderPlayground',
      'renderAnalytics',
      'renderModelCatalog',
      'renderSetupGuides',
      'chatCompletion',
      'generateImage',
      'buildClientSetupCommands',
      'deletePlaygroundMessage',
      'handlePlaygroundConnectivityTest',
      'performance.now',
    ]) {
      assert.equal(combined.includes(required), true, `${required} 应该接入用户侧完整链路`);
    }

    for (const view of ['playground', 'analytics', 'models', 'docs', 'api', 'billing', 'switch']) {
      const panel = userHtml.match(new RegExp(`<section class="view-panel" data-view="${view}"[\\s\\S]*?<\\/section>`))?.[0] || '';
      assert.equal(panel.includes('data-back-home'), true, `${view} 页面应该提供返回首页按钮`);
    }

    for (const forbidden of ['补号助手', '上游号商', '新增渠道', '价格解析']) {
      assert.equal(userHtml.includes(forbidden), false, `${forbidden} 不能出现在用户侧新增页面`);
    }
  });

  it('wires customer balance alert controls through the billing page and browser client', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const serverClient = readFileSync(new URL('../src/serverClient.js', import.meta.url), 'utf8');
    const combined = `${userHtml}\n${appScript}\n${serverClient}`;

    for (const required of [
      'data-balance-alert-card',
      'data-balance-alert-enabled',
      'data-balance-alert-threshold',
      'data-balance-alert-email',
      'data-balance-alert-save',
      'data-balance-alert-test',
      'data-balance-alert-feedback',
      'renderBalanceAlert',
      'handleBalanceAlertSave',
      'handleBalanceAlertTest',
      'saveBalanceAlert',
      'sendBalanceAlertTest',
      '/api/frist/balance-alert',
      '/api/frist/balance-alert/test',
    ]) {
      assert.equal(combined.includes(required), true, `${required} 应该接入用户余额预警设置`);
    }
  });

  it('renders every API Key status from its own enabled flag instead of a global switch', () => {
    assert.match(page, /class="key-state \$\{key\.enabled \? 'is-on' : ''\}"/);
    assert.match(page, /\$\{key\.enabled \? '已开启' : '已关闭'\}/);
    assert.match(page, /data-key-name="\$\{escapeHtml\(key\.id\)\}"/);
    assert.match(page, /data-rename-key="\$\{escapeHtml\(key\.id\)\}"/);
    assert.match(page, /data-delete-key="\$\{escapeHtml\(key\.id\)\}"/);
    assert.match(page, /renameKey\(/);
    assert.match(page, /deleteKey\(/);
  });

  it('lists every supported client in the setup guide, including OpenCode and Hermes aliases', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const docsPanel =
      userHtml.match(/<section class="view-panel" data-view="docs"[\s\S]*?<section class="view-panel" data-view="api"/)?.[0] ||
      '';

    for (const required of ['Codex', 'Claude', 'Gemini', 'OpenCode', 'OpenClaw', 'Hermes', 'Harmes']) {
      assert.equal(docsPanel.includes(required), true, `${required} 应该出现在使用教程里`);
    }
  });

  it('keeps the replenishment workspace on a separate admin page wired to server APIs', () => {
    const adminPage = [
      readFileSync(new URL('../admin.html', import.meta.url), 'utf8'),
      readFileSync(new URL('../src/admin.js', import.meta.url), 'utf8'),
    ].join('\n');

    for (const required of [
      'data-admin-token',
      'data-admin-credit-email',
      'data-admin-credit-amount',
      'data-admin-credit-plan',
      'data-admin-credit',
      'data-admin-base-url',
      'data-admin-proxy-url',
      'data-admin-source-type',
      'data-admin-risk-status',
      'data-admin-backup-risk-accepted',
      'data-admin-risk-note',
      'data-admin-order-text',
      'data-admin-parse-order',
      'data-admin-inventory-summary',
      'data-admin-keys',
      'data-admin-probe-mode',
      'data-admin-audit',
      'data-admin-replenish',
      'data-admin-pricing',
      'data-admin-pricing-save',
      'data-admin-plans',
      'data-admin-model-prices',
      '/api/admin/replenishments/parse-order',
      '/api/admin/replenishments',
      '/api/admin/customers/recharge',
      '/api/admin/pricing',
    ]) {
      assert.equal(adminPage.includes(required), true, `${required} 应该只存在于管理端`);
      assert.equal(page.includes(required), false, `${required} 不应该出现在用户端`);
    }
  });

  it('escapes dynamic admin and customer HTML fields before writing innerHTML', () => {
    const adminScript = readFileSync(new URL('../src/admin.js', import.meta.url), 'utf8');
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');

    for (const required of [
      'escapeHtml(item.providerGroup)',
      'escapeHtml(item.wasteText',
      'escapeHtml(event.detail)',
      'escapeHtml(event.at',
    ]) {
      assert.equal(adminScript.includes(required), true, `${required} 应该保护管理端动态 HTML`);
    }

    for (const required of [
      'safePercent(item.percent)',
      'escapeHtml(key.id)',
      'escapeHtml(key.preview)',
      'escapeHtml(option.label',
      'escapeHtml(target)',
    ]) {
      assert.equal(appScript.includes(required), true, `${required} 应该保护用户端动态 HTML`);
    }
  });
});

function createIds(values) {
  const queue = [...values];
  return () => queue.shift() || `id-${queue.length}`;
}

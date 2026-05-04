import {
  buildClientSetupCommands,
  normalizeBaseUrl,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  summarizeModelHealth,
} from './core.js';
import {
  buildBusinessClientConfig,
  buildBusinessImportUrl,
  createBusinessStateFromDashboard,
} from './businessFlow.js';
import { createFristApiBrowserClient, normalizeFristDashboard } from './serverClient.js';

const emptyDashboard = {
  accountSummary: {
    userInitials: 'FA',
    plan: '未登录',
    renewalDate: '-',
    balance: '$0.00',
    todayCost: '$0.00',
    monthCost: '$0.00',
    quotaLeft: '$0.00',
    packageQuota: '$0.00',
    boosterQuota: '$0.00',
    usageTotal: '$0.00',
    todayCalls: '0 次',
    todayTokens: '0',
    totalTokens: '0',
    averageLatency: '-',
    successRate: '0%',
    email: '',
    isAdmin: false,
  },
  apiKeys: [],
  channelChecks: [],
  helpLinks: [],
  importTargets: ['Claude', 'Codex', 'Gemini', 'OpenCode', 'OpenClaw', 'Hermes', 'Harmes'],
  modelUsage: [],
  modelCatalog: [],
  usageRecords: [],
  recentLogs: [],
  rechargeOptions: [],
  balanceAlert: {
    enabled: true,
    threshold: '$5.00',
    thresholdUsd: 5,
    thresholdCny: 36,
    thresholdCents: 3600,
    email: '',
    lastAlertAt: '',
  },
};

const dashboardData = structuredClone(emptyDashboard);
let businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });

const serverClient = createFristApiBrowserClient({
  baseUrl: window.FRIST_API_SERVER_BASE_URL || window.location.origin,
});

const catalogTemplate = [
  { model: 'gpt-5.5', family: 'OpenAI', tagline: '推理和代码主力', context: '1M 上下文', price: '按后台价格', available: false },
  { model: 'gpt-5.4', family: 'OpenAI', tagline: '日常问答和代码补全', context: '1M 上下文', price: '按后台价格', available: false },
  { model: 'gpt-5.4-mini', family: 'OpenAI', tagline: '轻量代码和快速问答', context: '长上下文', price: '按后台价格', available: false },
  { model: 'gpt-image-2', family: 'OpenAI', tagline: '图片生成', context: '按图计费', price: '按张结算', available: false },
  { model: 'gpt-5.3-codex', family: 'OpenAI', tagline: 'Codex 专用代码模型', context: '长上下文', price: '按后台价格', available: false },
  { model: 'claude-opus-4-6-thinking-c', family: 'Claude', tagline: '复杂开发和长链路推理', context: '1M 上下文', price: '按后台价格', available: false },
  { model: 'gemini-2.5-flash', family: 'Gemini', tagline: '多模态和轻量任务', context: '长上下文', price: '按后台价格', available: false },
  { model: 'deepseek-v4-flash', family: 'DeepSeek', tagline: 'Codex 桌面版官方兼容网关', context: 'OpenAI v1 兼容', price: '按官方 API 结算', available: false },
];

const viewMeta = {
  dashboard: {
    kicker: 'Frist',
    title: '首页',
    desc: '余额、消耗、连通和导入。',
  },
  playground: {
    kicker: 'Square',
    title: '广场',
    desc: '直接试模型，顺手出图。',
  },
  api: {
    kicker: 'Key',
    title: 'API',
    desc: '创建、开关、复制。',
  },
  billing: {
    kicker: 'Billing',
    title: '充值',
    desc: '购买和兑换卡密。',
  },
  switch: {
    kicker: 'Import',
    title: '导入',
    desc: '选择客户端。',
  },
  analytics: {
    kicker: 'Data',
    title: '数据看板',
    desc: '看模型消耗和可用性。',
  },
  records: {
    kicker: 'Records',
    title: '使用记录',
    desc: '按 Key、模型和端点追踪。',
  },
  subscription: {
    kicker: 'Plan',
    title: '我的订阅',
    desc: '为时限套餐预留。',
  },
  redeem: {
    kicker: 'Code',
    title: '兑换码',
    desc: '闲鱼发货后核销。',
  },
  invite: {
    kicker: 'Referral',
    title: '邀请返利',
    desc: '客户增长入口。',
  },
  profile: {
    kicker: 'Profile',
    title: '个人资料',
    desc: '账户和偏好。',
  },
  models: {
    kicker: 'Market',
    title: '模型广场',
    desc: '看模型和价格。',
  },
  docs: {
    kicker: 'Guide',
    title: '使用教程',
    desc: '一键配置客户端。',
  },
};

const state = {
  view: 'dashboard',
  dashboardLoading: true,
  target: 'Codex',
  authMode: 'login',
  keyEnabled: true,
  baseUrl: 'https://api.frist.example.com/v1',
  model: 'gpt-5.5',
  playgroundModel: 'gpt-5.5',
  modelGroup: 'OpenAI',
  selectedRechargeCny: 5.88,
  selectedRechargePlanId: '',
  selectedRechargePlan: 'day',
  passwordResetRequested: false,
  apiSearch: '',
  modelSearch: '',
  playgroundModelSearch: '',
  playgroundFamily: 'All',
  serverAvailable: false,
  hasServerSession: false,
  importRequestId: 0,
  playgroundBusy: false,
  playgroundConnectivity: {
    status: 'idle',
    text: '等待实测',
  },
  playgroundMessageSeq: 0,
  playgroundMessages: [
    {
      id: 'msg-welcome',
      role: 'assistant',
      content: '先从左侧选择模型，再直接测试文字、代码或图片能力。',
    },
  ],
  generatedImage: null,
  guideTarget: 'Codex',
  captcha: {
    id: '',
    question: '',
  },
};

function render() {
  renderLoadingState();
  renderAccountSummary();
  renderAuthPanel();
  renderDashboard();
  renderUsage();
  renderChannelHealth();
  renderTrendChart();
  renderRecentLogs();
  renderUsageRecords();
  renderProfile();
  renderPlayground();
  renderAnalytics();
  renderModelCatalog();
  renderApiKeys();
  renderModelGroupPicker();
  renderRechargeOptions();
  renderXianyuPurchaseLinks();
  renderBalanceAlert();
  renderImportTargets();
  renderImportFamilyPicker();
  renderImportLink();
  renderClientConfig();
  renderSetupGuides();
  renderHelpLinks();
  routeFromHash();
}

async function loadDashboardData() {
  state.dashboardLoading = true;
  renderLoadingState();
  let nextData = normalizeFristDashboard(emptyServerPayload(), emptyDashboard);
  try {
    const serverDashboard = await serverClient.loadDashboard();
    nextData = normalizeFristDashboard(serverDashboard, emptyDashboard);
    state.serverAvailable = true;
    state.hasServerSession = Boolean(serverDashboard.authenticated);
  } catch (error) {
    state.serverAvailable = false;
    state.hasServerSession = false;
    setActionMessage(userFacingLoadError(error), 'error');
  }

  state.dashboardLoading = false;
  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
  syncPrimaryAccountState();
  render();
}

function emptyServerPayload() {
  return {
    authenticated: false,
    account: {},
    user: {},
    apiKeys: [],
    channelChecks: [],
    modelUsage: [],
    modelCatalog: [],
    usageRecords: [],
    recentLogs: [],
    rechargeOptions: [],
    balanceAlert: {},
  };
}

function renderAccountSummary() {
  const { accountSummary } = dashboardData;
  setText('[data-plan]', accountSummary.plan);
  setText('[data-balance]', accountSummary.balance);
  setText('[data-user-initials]', accountSummary.userInitials);
  setText('[data-today-cost]', accountSummary.todayCost);
  setText('[data-month-cost]', accountSummary.monthCost);
  setText('[data-quota-left]', accountSummary.quotaLeft);
  setText('[data-quota-breakdown]', `套餐 ${accountSummary.packageQuota} · 加油包 ${accountSummary.boosterQuota}`);
  setText('[data-package-status]', `${accountSummary.plan} · ${accountSummary.renewalDate} 续费`);
  setText('[data-today-calls]', accountSummary.todayCalls);
  setText('[data-usage-total]', accountSummary.usageTotal);
  setText('[data-today-tokens]', accountSummary.todayTokens || '0');
  setText('[data-total-tokens]', accountSummary.totalTokens || '0');
  setText('[data-average-latency]', accountSummary.averageLatency || '-');
  setText('[data-success-rate]', accountSummary.successRate || '0%');
  setText('[data-profile-email]', accountSummary.email || '未登录');
  setText('[data-profile-plan]', accountSummary.plan || '未登录');
}

function renderAuthPanel() {
  const emailInput = document.querySelector('[data-register-email]');
  const isAdmin = Boolean(businessState.customer.isAdmin);
  const status = businessState.customer.email
    ? businessState.customer.emailVerified
      ? '已登录'
      : '已登录'
    : '登录后创建 Key。';

  if (emailInput && document.activeElement !== emailInput) {
    emailInput.value = businessState.customer.email;
  }
  const captchaRow = document.querySelector('[data-captcha-row]');
  if (captchaRow) {
    captchaRow.hidden = state.authMode !== 'register' || !state.captcha.question;
  }
  const showAccountTools = state.authMode === 'login' && state.hasServerSession;
  const ownerClaimRow = document.querySelector('[data-owner-claim-row]');
  if (ownerClaimRow) {
    ownerClaimRow.hidden = !showAccountTools || isAdmin;
  }
  const ownerEntry = document.querySelector('[data-owner-entry]');
  if (ownerEntry) {
    ownerEntry.hidden = !isAdmin;
  }
  const passwordRow = document.querySelector('[data-password-row]');
  if (passwordRow) {
    passwordRow.hidden = !showAccountTools;
  }
  const resetRequestRow = document.querySelector('[data-reset-request-row]');
  if (resetRequestRow) {
    resetRequestRow.hidden = state.authMode !== 'login' || state.hasServerSession;
  }
  const resetConfirmRow = document.querySelector('[data-reset-confirm-row]');
  if (resetConfirmRow) {
    resetConfirmRow.hidden = state.authMode !== 'login' || !state.passwordResetRequested || state.hasServerSession;
  }
  setText('[data-auth-title]', state.authMode === 'register' ? '注册账号' : '登录账号');
  setText('[data-captcha-question]', state.captcha.question ? `验证 ${state.captcha.question}` : '安全验证');
  setText('[data-email-status]', status);
  setText('[data-verification-hint]', isAdmin ? '管理员身份已激活。' : state.hasServerSession ? '可以创建 Key。' : status);

  for (const button of document.querySelectorAll('[data-auth-mode]')) {
    const selected = button.dataset.authMode === state.authMode;
    button.classList.toggle('is-active', selected);
    button.setAttribute('aria-selected', String(selected));
  }
  for (const button of document.querySelectorAll('[data-auth-submit]')) {
    button.hidden = button.dataset.authSubmit !== state.authMode;
  }
}

function renderDashboard() {
  const { channelChecks } = dashboardData;
  const healthyCount = channelChecks.filter((item) => item.ok && !item.maintenance).length;
  const total = channelChecks.length;
  setText('[data-channel-ratio]', `${healthyCount}/${total}`);
  setText('[data-api-summary]', `${enabledKeyCount()} / ${dashboardData.apiKeys.length}`);
}

function renderUsage() {
  const { modelUsage } = dashboardData;
  const compact = document.querySelector('[data-usage-compact]');
  const renderRows = (rows, options = {}) => rows
    .map(
      (item) => `
        <article class="usage-row ${options.compact ? 'usage-row--compact' : ''}">
          <div>
            <strong>${item.model}</strong>
            ${options.compact ? '' : `<span>${item.calls} · ${item.tokens}</span>`}
          </div>
          <div class="usage-track" aria-label="${escapeHtml(item.model)} 消耗占比 ${safePercent(item.percent)}%">
            <i style="width: ${safePercent(item.percent)}%"></i>
          </div>
          <b>${item.amount}</b>
        </article>
      `,
    )
    .join('');

  if (compact) {
    compact.innerHTML = state.dashboardLoading
      ? renderSkeletonRows(2, '模型消耗加载中')
      : renderRows(modelUsage.slice(0, 2), { compact: true }) || renderEmptyState('暂无模型消耗', '创建 Key 并发起请求后展示占比。');
  }
}

function renderTrendChart() {
  const chart = document.querySelector('[data-token-trend]');
  if (!chart) return;
  const rows = tokenTrendRows();
  const max = Math.max(1, ...rows.map((item) => item.tokens));
  const hasTokens = rows.some((item) => item.tokens > 0);
  chart.classList.toggle('is-empty', !hasTokens && !state.dashboardLoading);
  chart.innerHTML = rows
    .map(
      (item) => `
        <span class="trend-bar" role="img" aria-label="${escapeHtml(item.label)} ${item.tokens} Token" style="--height:${Math.max(8, Math.round((item.tokens / max) * 100))}%">
          <i></i>
          <b>${escapeHtml(item.label)}</b>
        </span>
      `,
    )
    .join('');
}

function tokenTrendRows() {
  const source = dashboardData.usageRecords || [];
  const labels = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    return date.toISOString().slice(0, 10);
  });
  const totals = new Map(labels.map((label) => [label, 0]));
  for (const record of source) {
    const day = String(record.at || '').slice(0, 10);
    if (totals.has(day)) {
      totals.set(day, totals.get(day) + tokenNumber(record.tokens));
    }
  }
  return labels.map((label) => ({
    label: label.slice(5),
    tokens: totals.get(label) || 0,
  }));
}

function tokenNumber(value) {
  const text = String(value || '0').trim().toUpperCase();
  const number = Number(text.replace(/[^\d.]/g, ''));
  if (!Number.isFinite(number)) return 0;
  if (text.endsWith('M')) return number * 1_000_000;
  if (text.endsWith('K')) return number * 1_000;
  return number;
}

function renderRecentLogs() {
  const container = document.querySelector('[data-recent-logs]');
  if (!container) return;
  const rows = dashboardData.recentLogs || [];
  container.innerHTML = rows.length
    ? rows
        .map(
          (item) => `
            <article class="log-row">
              <span>${escapeHtml(formatCheckedAt(item.at))}</span>
              <strong>${escapeHtml(item.detail)}</strong>
              <small>${escapeHtml(item.type)}</small>
            </article>
          `,
        )
        .join('')
    : renderEmptyState('暂无使用日志', '发起请求后会在这里显示最近路由、计费和错误。');
}

function renderUsageRecords() {
  const container = document.querySelector('[data-usage-records]');
  const empty = document.querySelector('[data-usage-records-empty]');
  if (!container) return;
  const rows = dashboardData.usageRecords || [];
  if (empty) {
    empty.hidden = rows.length > 0;
    empty.innerHTML = rows.length ? '' : renderEmptyState('暂无使用记录', '发起请求后会展示 Key、模型、端点、计费模式和 Token。');
  }
  container.innerHTML = rows.length
    ? rows
        .map(
          (item) => `
            <tr>
              <td>${escapeHtml(item.apiKey)}</td>
              <td>${escapeHtml(item.model)}</td>
              <td>${escapeHtml(item.inferenceEffort)}</td>
              <td>${escapeHtml(item.endpoint)}</td>
              <td>${escapeHtml(item.type)}</td>
              <td>${escapeHtml(item.billingMode)}</td>
              <td>${escapeHtml(item.tokens)}</td>
            </tr>
          `,
        )
        .join('')
    : '<tr class="table-empty"><td colspan="7">暂无使用记录</td></tr>';
}

function renderProfile() {
  setText('[data-profile-key-count]', `${dashboardData.apiKeys.length} 个`);
  setText('[data-profile-balance]', dashboardData.accountSummary.quotaLeft || '$0.00');
}

function renderChannelHealth() {
  const { channelChecks } = dashboardData;
  const compact = document.querySelector('[data-channel-compact]');
  const providerItems = providerSummaries(channelChecks);
  const compactItems = providerItems.map(renderProviderSummary).join('');

  if (compact) {
    compact.innerHTML = state.dashboardLoading
      ? renderSkeletonRows(2, '渠道连通性加载中')
      : compactItems || renderEmptyState('暂无渠道检测', '刷新连通后展示 OpenAI、Claude 等可用线路。');
  }
}

function renderProviderSummary(item) {
  return `
    <article class="provider-row">
      <span class="health-dot health-dot--${item.status}" aria-hidden="true"></span>
      <div class="provider-main">
        <strong>${escapeHtml(item.provider)}</strong>
        <small class="provider-meta">${escapeHtml(item.okText)} · 最低 ${escapeHtml(item.latencyText)} · ${escapeHtml(item.checkedText)}</small>
        <div class="provider-models">
          ${item.models.map((model) => `<span>${escapeHtml(model)}</span>`).join('')}
        </div>
      </div>
    </article>
  `;
}

function providerSummaries(channelChecks) {
  const grouped = new Map();
  for (const snapshot of channelChecks) {
    const summary = summarizeModelHealth(snapshot);
    const current = grouped.get(snapshot.provider) || {
      provider: snapshot.provider,
      total: 0,
      healthy: 0,
      bestLatency: 0,
      models: [],
      checkedAt: '',
      lastReason: '',
    };
    current.total += 1;
    current.healthy += snapshot.ok && !snapshot.maintenance ? 1 : 0;
    if (snapshot.ok) {
      current.bestLatency = current.bestLatency
        ? Math.min(current.bestLatency, Number(snapshot.latencyMs || 0))
        : Number(snapshot.latencyMs || 0);
    }
    current.models.push(snapshot.model);
    current.checkedAt = [current.checkedAt, snapshot.checkedAt].filter(Boolean).sort().at(-1) || '';
    current.lastReason = snapshot.officialStatus || snapshot.status || current.lastReason;
    current.status = current.healthy > 0 ? summary.status : 'down';
    grouped.set(snapshot.provider, current);
  }

  return [...grouped.values()].map((item) => ({
    provider: item.provider,
    status: item.healthy > 0 ? (item.bestLatency > 1600 ? 'slow' : 'healthy') : 'down',
    okText: item.healthy > 0 ? `${item.healthy}/${item.total}` : '不可用',
    latencyText: item.bestLatency ? `${item.bestLatency}ms` : '-',
    checkedText: item.checkedAt ? `最近 ${formatCheckedAt(item.checkedAt)}` : item.lastReason || '等待检测',
    models: normalizeOfficialModelList([...new Set(item.models)]).slice(0, 4),
  }));
}

function formatCheckedAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || '-');
  }
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function renderPlayground() {
  normalizePlaygroundMessages();
  const select = document.querySelector('[data-playground-model]');
  const rows = filteredPlaygroundModels();
  const models = availableModels();
  if (!models.includes(state.playgroundModel)) {
    state.playgroundModel = models[0] || 'gpt-5.5';
  }

  if (select && document.activeElement !== select) {
    select.innerHTML = models
      .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
      .join('');
    select.value = state.playgroundModel;
  }

  const search = document.querySelector('[data-playground-model-search]');
  if (search && document.activeElement !== search) {
    search.value = state.playgroundModelSearch;
  }

  renderPlaygroundFamilyFilter();
  renderPlaygroundModelGrid(rows);
  renderSelectedPlaygroundModel();
  renderPlaygroundDiagnostics();

  const log = document.querySelector('[data-playground-log]');
  if (log) {
    log.innerHTML = state.playgroundMessages
      .map(
        (message) => `
          <article class="chat-bubble chat-bubble--${message.role}">
            <div class="chat-bubble__head">
              <span>${message.role === 'user' ? '你' : 'Frist'}</span>
              <button class="chat-delete" data-delete-message="${escapeHtml(message.id)}" type="button" aria-label="删除这条消息">×</button>
            </div>
            <p>${escapeHtml(message.content)}</p>
          </article>
        `,
      )
      .join('');
    log.scrollTop = log.scrollHeight;
  }

  const imageOutput = document.querySelector('[data-image-output]');
  if (imageOutput) {
    imageOutput.hidden = !state.generatedImage;
    imageOutput.innerHTML = state.generatedImage
      ? `<img src="${escapeHtml(state.generatedImage)}" alt="生成结果" />`
      : '';
  }

  const sendButton = document.querySelector('[data-playground-send]');
  if (sendButton) {
    sendButton.disabled = state.playgroundBusy;
    sendButton.textContent = state.playgroundBusy
      ? '处理中'
      : isImageModel(state.playgroundModel)
        ? '生成'
        : '发送';
  }

  const testButton = document.querySelector('[data-playground-test]');
  if (testButton) {
    testButton.disabled = state.playgroundBusy;
    testButton.textContent = state.playgroundBusy ? '实测中' : '实测连通';
  }

  const status = document.querySelector('[data-playground-status]');
  if (status) {
    status.textContent = state.playgroundConnectivity.text;
    status.className = `playground-status playground-status--${state.playgroundConnectivity.status}`;
  }

  const clearButton = document.querySelector('[data-clear-playground]');
  if (clearButton) {
    clearButton.disabled = state.playgroundMessages.length <= 1;
  }
}

function renderPlaygroundFamilyFilter() {
  for (const button of document.querySelectorAll('[data-playground-family]')) {
    const active = button.dataset.playgroundFamily === state.playgroundFamily;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  }
}

function renderPlaygroundModelGrid(rows) {
  const container = document.querySelector('[data-playground-model-grid]');
  setText('[data-playground-model-count]', `${rows.length} 个模型`);
  if (!container) return;

  container.innerHTML = rows
    .map((item) => {
      const active = item.model === state.playgroundModel;
      const summary = modelHealthSummaryFor(item.model);
      return `
        <button
          class="playground-model-row ${active ? 'is-active' : ''} ${item.available ? 'is-available' : 'is-unavailable'}"
          data-playground-model-card="${escapeHtml(item.model)}"
          type="button"
          role="listitem"
          aria-pressed="${active ? 'true' : 'false'}"
        >
          <span class="health-dot health-dot--${summary.status}" aria-hidden="true"></span>
          <span class="playground-model-row__main">
            <strong>${escapeHtml(item.model)}</strong>
            <small>${escapeHtml(item.family)} · ${escapeHtml(item.endpointType)}</small>
          </span>
          <span class="playground-model-row__meta">${escapeHtml(item.price)}</span>
        </button>
      `;
    })
    .join('') || renderEmptyState('没有匹配的模型', '换一个关键词或切到全部分组。');
}

function renderSelectedPlaygroundModel() {
  const container = document.querySelector('[data-playground-selected-model]');
  if (!container) return;

  const selected = modelCatalogRows().find((item) => item.model === state.playgroundModel) || fallbackModelRow(state.playgroundModel);
  const summary = modelHealthSummaryFor(selected.model);
  const endpoint = endpointForModel(selected);
  const isImage = isImageModel(selected.model);
  container.innerHTML = `
    <div class="selected-model-panel__main">
      <span class="provider-badge">${escapeHtml(selected.family)}</span>
      <h3>${escapeHtml(selected.model)}</h3>
      <p>${escapeHtml(selected.tagline || (isImage ? '图片生成模型' : '文本和代码模型'))}</p>
    </div>
    <div class="selected-model-panel__facts">
      <span><b>${escapeHtml(summary.label)}</b><small>状态</small></span>
      <span><b>${escapeHtml(selected.price || '按后台价格')}</b><small>计费</small></span>
      <span><b>${escapeHtml(selected.context || '按模型能力')}</b><small>上下文</small></span>
      <code>${escapeHtml(endpoint)}</code>
    </div>
  `;
}

function renderPlaygroundDiagnostics() {
  const container = document.querySelector('[data-playground-diagnostics]');
  if (!container) return;
  const selected = modelCatalogRows().find((item) => item.model === state.playgroundModel) || fallbackModelRow(state.playgroundModel);
  const summary = modelHealthSummaryFor(selected.model);
  const key = activeApiKey();
  const rows = [
    ['Key', key ? `${key.name} · ${key.enabled ? '已开启' : '已禁用'}` : '未创建'],
    ['端点', endpointForModel(selected)],
    ['类型', isImageModel(selected.model) ? '图片生成' : 'Chat Completions'],
    ['连通', `${summary.label} · ${summary.latencyText}`],
  ];
  container.innerHTML = rows
    .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`)
    .join('');
}

function renderAnalytics() {
  const usageRows = dashboardData.modelUsage || [];
  for (const donut of document.querySelectorAll('[data-usage-donut]')) {
    donut.style.background = usageDonutGradient(usageRows);
  }

  const usage = document.querySelector('[data-analytics-usage]');
  if (usage) {
    usage.innerHTML = usageRows
      .map(
        (item, index) => `
          <article class="analytics-row">
            <i style="background:${chartColor(index)}"></i>
            <strong>${escapeHtml(item.model)}</strong>
            <span>${escapeHtml(item.amount)} · ${escapeHtml(item.calls || '0 次')}</span>
          </article>
        `,
      )
      .join('') || renderEmptyState('暂无消耗分布', '有请求后会按模型展示美元消耗。');
  }

  const health = document.querySelector('[data-service-health]');
  if (health) {
    health.innerHTML = (dashboardData.channelChecks || [])
      .map((item) => {
        const summary = summarizeModelHealth(item);
        return `
          <article class="service-card service-card--${escapeHtml(summary.status)}">
            <div class="service-card__top">
              <span class="health-dot health-dot--${summary.status}" aria-hidden="true"></span>
              <strong>${escapeHtml(item.provider || summary.model)}</strong>
              <small>${escapeHtml(item.availability || (item.ok ? '99.9%' : '0%'))}</small>
            </div>
            <b>${escapeHtml(summary.model)}</b>
            <code>${escapeHtml(item.endpoint || '/v1')}</code>
            <div class="availability-strip">
              ${(item.history || []).slice(-12).map((status) => `<i class="${status === 'ok' ? 'is-ok' : 'is-down'}"></i>`).join('')}
            </div>
            <small>${escapeHtml(summary.label)} · ${escapeHtml(summary.latencyText)} · ${escapeHtml(formatCheckedAt(item.checkedAt))}</small>
          </article>
        `;
      })
      .join('') || renderEmptyState('暂无服务可用性', '登录或刷新连通后展示最近 12 次检测图。');
  }
}

function renderModelCatalog() {
  const catalog = filteredModelCatalogRows();
  setText('[data-model-count]', `${catalog.filter((item) => item.available).length} 个可用`);
  const container = document.querySelector('[data-model-catalog]');
  if (!container) return;

  const search = document.querySelector('[data-model-catalog-search]');
  if (search && document.activeElement !== search) {
    search.value = state.modelSearch;
  }

  container.innerHTML = catalog
    .map(
      (item) => `
        <article class="model-card ${item.available ? 'is-available' : ''}" data-model-card="${escapeHtml(item.model)}">
          <div>
            <span class="provider-badge">${escapeHtml(item.family)}</span>
            <strong>${escapeHtml(item.model)}</strong>
          </div>
          <p>${escapeHtml(item.tagline)}</p>
          <div class="model-meta">
            <span>${escapeHtml(item.context)}</span>
            <span>${escapeHtml(item.price)}</span>
            <span>${escapeHtml(endpointForModel(item))}</span>
          </div>
          <div class="model-card-actions">
            <button class="text-action" data-select-playground-model="${escapeHtml(item.model)}" type="button">测试</button>
            <button class="icon-action" data-copy-text="${escapeHtml(item.model)}" type="button" aria-label="复制模型名">⧉</button>
          </div>
        </article>
      `,
    )
    .join('') || renderEmptyState('没有匹配的模型', '清空搜索后查看全部模型。');
}

function renderSetupGuides() {
  renderGuideTargets();
  const key = activeApiKey();
  setText('[data-guide-key-status]', key ? 'Key 已开启' : '请先创建 Key');

  let config = null;
  try {
    config = buildBusinessClientConfig(businessState, {
      target: state.guideTarget,
      baseUrl: state.baseUrl,
      model: state.model,
      defaultModel: defaultModelForGroup(state.modelGroup),
      availableModels: availableModelsForGroup(state.modelGroup),
    });
  } catch {
    config = null;
  }

  if (!config) {
    const empty = '# 请先登录并创建 API Key';
    setText('[data-guide-json]', '{}\n');
    setText('[data-guide-toml]', '');
    setText('[data-mac-command]', empty);
    setText('[data-win-command]', empty);
    return;
  }

  const setup = buildClientSetupCommands(config);
  setText('[data-guide-json]', setup.jsonConfig);
  setText('[data-guide-toml]', setup.tomlConfig);
  setText('[data-mac-command]', setup.macos);
  setText('[data-win-command]', setup.windows);
}

function renderGuideTargets() {
  const container = document.querySelector('[data-guide-targets]');
  if (!container) return;
  for (const button of container.querySelectorAll('[data-guide-target]')) {
    button.classList.toggle('is-active', button.dataset.guideTarget === state.guideTarget);
  }
}

function availableModels() {
  const liveModels = (dashboardData.channelChecks || []).map((item) => item.model).filter(Boolean);
  const catalogModels = (dashboardData.modelCatalog || []).map((item) => item.model).filter(Boolean);
  const templateModels = catalogTemplate.map((item) => item.model);
  const unique = [...new Set([...liveModels, ...catalogModels, ...templateModels])];
  return sortModelsByStrength(unique.length ? unique : ['gpt-5.5']);
}

function availableModelsForGroup(group) {
  const models = availableModels().filter((model) => modelMatchesUiGroup(model, group));
  return models.length ? models : [defaultModelForGroup(group)];
}

function filteredPlaygroundModels() {
  const query = state.playgroundModelSearch.toLowerCase();
  const rows = modelCatalogRows()
    .filter((item) => state.playgroundFamily === 'All' || modelMatchesUiGroup(item.model, state.playgroundFamily))
    .filter((item) => modelRowMatchesQuery(item, query));
  return rows;
}

function filteredModelCatalogRows() {
  const query = state.modelSearch.toLowerCase();
  return modelCatalogRows().filter((item) => modelRowMatchesQuery(item, query));
}

function modelRowMatchesQuery(item, query) {
  if (!query) return true;
  const endpoint = endpointForModel(item);
  return [
    item.model,
    item.family,
    item.tagline,
    item.context,
    item.price,
    item.endpointType,
    endpoint,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .includes(query);
}

function modelMatchesUiGroup(model, group) {
  const normalized = String(group || 'All').toLowerCase();
  const value = String(model || '').toLowerCase();
  if (normalized === 'all') return true;
  if (normalized === 'openai') return /gpt|dall|image/.test(value);
  if (normalized === 'claude') return /claude|anthropic/.test(value);
  if (normalized === 'gemini') return /gemini/.test(value);
  if (normalized === 'deepseek') return /deepseek/.test(value);
  if (normalized === 'other') return !/gpt|dall|image|claude|anthropic|gemini|deepseek/.test(value);
  return true;
}

function sortModelsByStrength(models) {
  const order = [
    'gpt-5.5-pro',
    'gpt-5.5-c',
    'gpt-5.5',
    'gpt-5.4-pro',
    'gpt-5.4-c',
    'gpt-5.4',
    'gpt-5.4-mini',
    'gpt-5.4-nano',
    'gpt-image-2',
    'gpt-image-1.5',
    'gpt-image-1',
    'gpt-5.3-codex',
    'deepseek-v4-flash',
    'deepseek-v4-pro',
    'deepseek-reasoner',
    'deepseek-chat',
    'claude-opus-4-6-thinking-c',
    'claude-opus-4-6-c',
    'claude-sonnet-4-5-c',
    'gemini-2.5-flash',
  ];
  return [...new Set((models || []).map((model) => normalizeOfficialModelName(model)).filter(Boolean))].sort((left, right) => {
    const leftRank = order.indexOf(left);
    const rightRank = order.indexOf(right);
    const normalizedLeft = leftRank === -1 ? Number.MAX_SAFE_INTEGER : leftRank;
    const normalizedRight = rightRank === -1 ? Number.MAX_SAFE_INTEGER : rightRank;
    if (normalizedLeft !== normalizedRight) return normalizedLeft - normalizedRight;
    return left.localeCompare(right);
  });
}

function modelCatalogRows() {
  const statusByModel = new Map((dashboardData.channelChecks || []).map((item) => [normalizeOfficialModelName(item.model), item]));
  const catalog = (dashboardData.modelCatalog || []).map((item) => ({
    ...item,
    model: normalizeOfficialModelName(item.model),
    family: item.family || inferUiFamily(item.model),
    endpointType: item.endpointType || endpointTypeForModel(item.model),
    available: statusByModel.has(normalizeOfficialModelName(item.model)) ? Boolean(statusByModel.get(normalizeOfficialModelName(item.model)).ok) : Boolean(item.available),
  }));
  const catalogModels = new Set(catalog.map((item) => item.model));
  const liveAdditions = (dashboardData.channelChecks || [])
    .filter((item) => item.model && !catalogModels.has(item.model))
    .map((item) => ({
      model: item.model,
      family: item.provider || inferUiFamily(item.model),
      tagline: '当前可用',
      context: '按模型能力',
      price: '按后台价格',
      endpointType: endpointTypeForModel(item.model),
      available: Boolean(item.ok),
    }));
  const rowsByModel = new Map();
  for (const item of catalogTemplate) {
    rowsByModel.set(item.model, {
      ...item,
      model: normalizeOfficialModelName(item.model),
      endpointType: endpointTypeForModel(item.model),
    });
  }
  for (const item of [...catalog, ...liveAdditions]) {
    rowsByModel.set(item.model, item);
  }
  return sortModelRows([...rowsByModel.values()]);
}

function sortModelRows(rows) {
  const sortedModels = sortModelsByStrength(rows.map((item) => item.model));
  const rank = new Map(sortedModels.map((model, index) => [model, index]));
  return [...rows].sort((left, right) => {
    const availableDelta = Number(right.available) - Number(left.available);
    if (availableDelta !== 0) return availableDelta;
    const rankDelta = (rank.get(left.model) ?? 9999) - (rank.get(right.model) ?? 9999);
    if (rankDelta !== 0) return rankDelta;
    return `${left.family}:${left.model}`.localeCompare(`${right.family}:${right.model}`);
  });
}

function fallbackModelRow(model) {
  return {
    model: normalizeOfficialModelName(model),
    family: inferUiFamily(model),
    tagline: isImageModel(model) ? '图片生成模型' : '文本和代码模型',
    context: '按模型能力',
    price: '按后台价格',
    endpointType: endpointTypeForModel(model),
    available: false,
  };
}

function endpointTypeForModel(model) {
  return isImageModel(model) ? 'Images' : 'Chat';
}

function endpointForModel(item) {
  return isImageModel(item?.model) ? '/v1/images/generations' : '/v1/chat/completions';
}

function inferUiFamily(model) {
  const value = String(model || '').toLowerCase();
  if (/gpt|dall|image/.test(value)) return 'OpenAI';
  if (/claude|anthropic/.test(value)) return 'Claude';
  if (/gemini/.test(value)) return 'Gemini';
  if (/deepseek/.test(value)) return 'DeepSeek';
  return 'Other';
}

function modelHealthSummaryFor(model) {
  const status = (dashboardData.channelChecks || []).find((item) => normalizeOfficialModelName(item.model) === normalizeOfficialModelName(model));
  if (!status) {
    return {
      status: 'idle',
      label: '未检测',
      latencyText: '-',
    };
  }
  return summarizeModelHealth(status);
}

function usageDonutGradient(rows) {
  const colors = rows.map((_, index) => chartColor(index));
  let cursor = 0;
  const segments = rows
    .map((row, index) => {
      const percent = Math.max(0, Number(row.percent || 0));
      const start = cursor;
      cursor += percent;
      return `${colors[index]} ${start}% ${Math.min(cursor, 100)}%`;
    })
    .filter((segment) => !segment.endsWith(' 0%'));
  return segments.length
    ? `conic-gradient(${segments.join(', ')}, rgba(245,240,232,0.08) ${Math.min(cursor, 100)}% 100%)`
    : 'conic-gradient(rgba(245,240,232,0.08) 0 100%)';
}

function chartColor(index) {
  return ['#e7c59a', '#00ac5c', '#f3f3f3', '#949494', '#333333'][index % 5];
}

function safePercent(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

function renderApiKeys() {
  const { accountSummary, apiKeys } = dashboardData;
  const summary = document.querySelector('[data-key-summary]');
  const list = document.querySelector('[data-api-keys]');
  const activeCount = enabledKeyCount();
  const searchInput = document.querySelector('[data-api-search]');
  if (searchInput && document.activeElement !== searchInput) {
    searchInput.value = state.apiSearch;
  }
  if (!list) return;
  const filteredKeys = apiKeys.filter((key) => {
    const haystack = `${key.name || ''} ${key.preview || ''} ${key.secret || ''}`.toLowerCase();
    return !state.apiSearch || haystack.includes(state.apiSearch.toLowerCase());
  });

  if (summary) {
    summary.innerHTML = `
    <article><span>秘钥总数</span><strong>${apiKeys.length}</strong></article>
    <article><span>活跃秘钥</span><strong>${activeCount}</strong></article>
    <article><span>今日调用</span><strong>${accountSummary.todayCalls}</strong></article>
    <article><span>本月费用</span><strong>${accountSummary.monthCost}</strong></article>
  `;
  }

  list.innerHTML = filteredKeys
    .map(
      (key) => `
        <article class="key-row">
          <div class="key-name-field">
            <input
              type="text"
              data-key-name="${escapeHtml(key.id)}"
              value="${escapeHtml(key.name)}"
              aria-label="API Key 名称"
            />
            <span>${escapeHtml(key.preview)}</span>
          </div>
          <code class="key-endpoint">${escapeHtml(state.baseUrl)}</code>
          <span class="key-state ${key.enabled ? 'is-on' : ''}" data-key-status>
            ${key.enabled ? '已开启' : '已关闭'}
          </span>
          <div class="key-stats">
            <span>${escapeHtml(key.cost)}</span>
            <small>${escapeHtml(key.tokens)}</small>
          </div>
          <div class="key-actions">
            <button class="icon-button" data-copy-key-id="${escapeHtml(key.id)}" type="button" aria-label="复制 API Key" title="复制">⧉</button>
            <button class="icon-button" data-toggle-key="${escapeHtml(key.id)}" type="button" aria-label="${key.enabled ? '禁用 API Key' : '启用 API Key'}" title="${key.enabled ? '禁用' : '启用'}">${key.enabled ? '⏸' : '▶'}</button>
            <button class="icon-button" data-rename-key="${escapeHtml(key.id)}" type="button" aria-label="编辑 API Key 名称" title="编辑">✎</button>
            <button class="icon-button icon-button--danger" data-delete-key="${escapeHtml(key.id)}" type="button" aria-label="删除 API Key" title="删除">⌫</button>
          </div>
        </article>
      `,
    )
    .join('') || renderEmptyState(
      state.apiSearch ? '没有匹配的 API Key' : '暂无 API Key',
      state.apiSearch ? '换一个名称或 key 片段再试。' : '创建 Key 后会显示端点、状态和操作按钮。',
    );

  bindCopyButtons(list);
}

function renderLoadingState() {
  document.body.classList.toggle('is-loading-dashboard', state.dashboardLoading);
  document.body.dataset.serverState = state.serverAvailable ? 'connected' : state.dashboardLoading ? 'loading' : 'offline';
  const main = document.querySelector('#main-content');
  if (main) {
    main.setAttribute('aria-busy', String(state.dashboardLoading));
  }
  const board = document.querySelector('[data-console-board]');
  if (board) {
    board.setAttribute('aria-busy', String(state.dashboardLoading));
  }
  const recovery = document.querySelector('[data-server-recovery]');
  if (recovery) {
    recovery.hidden = state.dashboardLoading || state.serverAvailable;
  }
}

function renderSkeletonRows(count, label) {
  return Array.from({ length: count }, (_, index) => `
    <article class="skeleton-row" role="status" aria-label="${escapeHtml(label)} ${index + 1}">
      <span></span><b></b><i></i>
    </article>
  `).join('');
}

function renderEmptyState(title, detail = '') {
  return `
    <article class="empty-row empty-row--stack" role="status">
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ''}
    </article>
  `;
}

function userFacingLoadError(error) {
  const message = String(error?.message || '');
  if (/unexpected token|not valid json|json|failed to fetch|404|network/i.test(message)) {
    return '后端暂不可用，当前显示空数据。启动 Frist-API 服务后刷新。';
  }
  return message || '服务暂时不可用，请先启动后端';
}

function renderModelGroupPicker() {
  for (const button of document.querySelectorAll('[data-model-group-option]')) {
    button.classList.toggle('is-active', button.dataset.modelGroupOption === state.modelGroup);
  }
}

function renderRechargeOptions() {
  const { rechargeOptions } = dashboardData;
  const container = document.querySelector('[data-recharge-options]');
  if (!container) return;
  if (!state.selectedRechargePlanId && rechargeOptions[0]) {
    state.selectedRechargePlanId = rechargeOptions[0].id || '';
    state.selectedRechargeCny = Number(rechargeOptions[0].priceCny || String(rechargeOptions[0].cny).replace(/[^\d.]/g, ''));
    state.selectedRechargePlan = rechargeOptions[0].plan || 'balance';
  }
  container.innerHTML = rechargeOptions
    .map(
      (option) => `
        <button class="amount-button ${option.id === state.selectedRechargePlanId || option.active ? 'is-active' : ''}" data-recharge-plan-id="${escapeHtml(option.id || '')}" data-recharge-plan="${option.plan || 'balance'}" data-recharge-option="${Number(
          option.priceCny || String(option.cny).replace(/[^\d.]/g, ''),
        )}" type="button">
          <em>${escapeHtml(option.label || '余额')}</em>
          <strong>${escapeHtml(option.cny)}</strong>
          ${option.quotaUsd ? `<span>${escapeHtml(option.quota || `$${option.quotaUsd}`)} 额度</span>` : ''}
        </button>
      `,
    )
    .join('');
}

function renderXianyuPurchaseLinks() {
  const configuredLink = String(window.FRIST_API_XIANYU_PURCHASE_URL || '').trim();
  for (const link of document.querySelectorAll('[data-xianyu-purchase-link]')) {
    if (configuredLink) {
      link.href = configuredLink;
      link.textContent = '去闲鱼购买兑换码';
      link.removeAttribute('aria-disabled');
    } else {
      link.href = '#';
      link.textContent = '闲鱼链接待配置';
      link.setAttribute('aria-disabled', 'true');
    }
  }
}

function renderBalanceAlert() {
  const alert = dashboardData.balanceAlert || {};
  const enabledInput = document.querySelector('[data-balance-alert-enabled]');
  const thresholdInput = document.querySelector('[data-balance-alert-threshold]');
  const emailInput = document.querySelector('[data-balance-alert-email]');
  const status = document.querySelector('[data-balance-alert-status]');
  const last = document.querySelector('[data-balance-alert-last]');

  if (enabledInput && document.activeElement !== enabledInput) {
    enabledInput.checked = alert.enabled !== false;
  }
  if (thresholdInput && document.activeElement !== thresholdInput) {
    thresholdInput.value = Number(alert.thresholdUsd || 5).toFixed(2);
  }
  if (emailInput && document.activeElement !== emailInput) {
    emailInput.value = alert.email || dashboardData.accountSummary.email || '';
  }
  if (status) {
    status.textContent = alert.enabled === false ? '已关闭' : `低于 ${alert.threshold || '$5.00'} 发送`;
    status.classList.toggle('is-off', alert.enabled === false);
  }
  if (last) {
    last.textContent = alert.lastAlertAt ? `上次通知 ${formatCheckedAt(alert.lastAlertAt)}` : '暂未触发';
  }
}

function renderImportTargets() {
  const { importTargets } = dashboardData;
  const container = document.querySelector('[data-import-targets]');
  container.innerHTML = importTargets
    .map(
      (target) => `
        <button class="target-button ${state.target === target ? 'is-active' : ''}" data-target="${escapeHtml(target)}" type="button">
          ${escapeHtml(target)}
        </button>
      `,
    )
    .join('');

  for (const button of container.querySelectorAll('button')) {
    button.addEventListener('click', () => {
      state.target = button.dataset.target;
      renderImportTargets();
      renderImportFamilyPicker();
      renderImportLink();
      renderClientConfig();
    });
  }
}

function renderImportFamilyPicker() {
  const container = document.querySelector('[data-import-family]');
  if (!container) return;
  for (const button of container.querySelectorAll('button')) {
    button.classList.toggle('is-active', button.dataset.importFamilyOption === state.modelGroup);
  }
}

function renderImportLink() {
  let link = '';
  let config = null;
  try {
    const options = {
      target: state.target,
      baseUrl: state.baseUrl,
      model: state.model,
      defaultModel: defaultModelForGroup(state.modelGroup),
      availableModels: availableModelsForGroup(state.modelGroup),
    };
    link = buildBusinessImportUrl(businessState, options);
    config = buildBusinessClientConfig(businessState, options);
  } catch {
    link = '';
  }

  renderExportModelSummary(config);
  renderOpenCodeConfig(config);
  setText('[data-key-inline-status]', state.keyEnabled ? 'Key 已开启' : 'Key 已关闭');
  document.querySelector('[data-import-link]').value = link;
  const openImport = document.querySelector('[data-open-import]');
  if (openImport) {
    openImport.setAttribute('href', link || '#');
    openImport.toggleAttribute('aria-disabled', !link);
  }
  setText('[data-base-url]', normalizeBaseUrl(state.baseUrl));
  renderCrossImportGuide();
  refreshImportLinkFromServer();
}

function renderCrossImportGuide() {
  const title = document.querySelector('[data-cross-import-title]');
  const copy = document.querySelector('[data-cross-import-copy]');
  const guide = document.querySelector('[data-claude-developer-guide]');
  syncWalkthroughFields();
  const isClaudeTarget = state.target === 'Claude';
  const isOpenAiFamily = state.modelGroup === 'OpenAI';
  if (!title || !copy || !guide) return;

  if (isClaudeTarget && isOpenAiFamily) {
    title.textContent = 'ChatGPT 模型导入 Claude Code';
    copy.textContent = '选 Claude + ChatGPT，按红色重点填 Base URL、bearer 和默认模型。';
    guide.innerHTML = [
      '<li data-claude-guide-step><strong>Developer</strong> 进入第三方推理配置。</li>',
      '<li data-claude-guide-step><strong class="danger-text">Base URL 不带 /v1</strong>，认证方式选 bearer。</li>',
      '<li data-claude-guide-step>导入后新会话选择 Frist-API Gateway。</li>',
    ].join('');
    setActiveWalkthrough('openai-to-claude');
    return;
  }

  if (state.target === 'Codex' && state.modelGroup === 'Claude') {
    title.textContent = 'Claude 模型导入 Codex';
    copy.textContent = '选 Codex + Claude，一键写入 Responses、/v1 地址、默认模型和 MCP。';
    guide.innerHTML = [
      '<li data-claude-guide-step>目标客户端选 <strong>Codex</strong>。</li>',
      '<li data-claude-guide-step><strong class="danger-text">API 请求地址必须带 /v1</strong>。</li>',
      '<li data-claude-guide-step>重启 Codex 后测试同一上下文。</li>',
    ].join('');
    setActiveWalkthrough('claude-to-codex');
    return;
  }

  if (state.target === 'Codex') {
    title.textContent = state.modelGroup === 'DeepSeek' ? 'Codex DeepSeek 官方网关' : 'Codex 最强开发配置';
    copy.textContent = state.modelGroup === 'DeepSeek'
      ? '写入 DeepSeek 官方 OpenAI 兼容入口，供 Codex 桌面版直接测试。'
      : '默认启用 Responses、xhigh 推理和常用开发 MCP。';
    guide.innerHTML = [
      '<li data-claude-guide-step>目标客户端选 <strong>Codex</strong>。</li>',
      state.modelGroup === 'DeepSeek'
        ? '<li data-claude-guide-step>模型家族选 <strong>DeepSeek</strong>，默认模型 deepseek-v4-flash。</li>'
        : '<li data-claude-guide-step>确认 auth.json 和 config.toml 已写入。</li>',
      '<li data-claude-guide-step>Computer Use 首次调用按系统提示授权。</li>',
    ].join('');
    setActiveWalkthrough('claude-to-codex');
    return;
  }

  title.textContent = '一键导入';
  copy.textContent = '选目标客户端后直接导入，模型清单会随当前库存更新。';
  guide.innerHTML = [
    '<li data-claude-guide-step>确认至少有一个开启的 API Key。</li>',
    '<li data-claude-guide-step>选择目标客户端和模型家族。</li>',
    '<li data-claude-guide-step>导入后检查默认模型和模型列表。</li>',
  ].join('');
  setActiveWalkthrough('');
}

function syncWalkthroughFields() {
  const codexBase = normalizeBaseUrl(state.baseUrl);
  const claudeBase = codexBase.replace(/\/v1\/?$/i, '');
  const openAiModel = availableModelsForGroup('OpenAI')[0] || 'gpt-5.5';
  const claudeModel = availableModelsForGroup('Claude')[0] || 'claude-opus-4-6-thinking-c';
  const deepseekModel = availableModelsForGroup('DeepSeek')[0] || 'deepseek-v4-flash';
  const keyLabel = enabledKeyCount() ? 'fk-live-你的用户Key' : '先在 API 页面创建 fk-live 用户 Key';
  setText('[data-flow-codex-base]', codexBase);
  setText('[data-flow-claude-base]', claudeBase);
  setText('[data-flow-openai-model]', openAiModel);
  setText('[data-flow-claude-model]', claudeModel);
  setText('[data-flow-deepseek-model]', deepseekModel);
  setText('[data-flow-user-key]', keyLabel);
}

function setActiveWalkthrough(name) {
  for (const item of document.querySelectorAll('[data-walkthrough]')) {
    const isActive = item.dataset.walkthrough === name;
    item.classList.toggle('is-active', isActive);
    item.classList.toggle('is-muted', Boolean(name) && !isActive);
  }
}

function renderClientConfig() {
  let config = { authJson: '{}\n', configToml: '', ccSwitchUrl: '' };
  try {
    config = buildBusinessClientConfig(businessState, {
      target: state.target,
      baseUrl: state.baseUrl,
      model: state.model,
      defaultModel: defaultModelForGroup(state.modelGroup),
      availableModels: availableModelsForGroup(state.modelGroup),
    });
  } catch {
    // 没有 Key 时保持空配置，避免把示例 Key 误当成可用配置。
  }

  setText('[data-auth-json]', config.authJson);
  setText('[data-config-toml]', config.configToml);
  renderExportModelSummary(config);
  renderOpenCodeConfig(config);
}

function renderExportModelSummary(config) {
  const modelList = sortModelsByStrength(config?.availableModels || availableModelsForGroup(state.modelGroup));
  const defaultModel = config?.defaultModel || modelList[0] || defaultModelForGroup(state.modelGroup);
  setText('[data-export-default-model]', defaultModel);
  setText('[data-export-model-count]', `${modelList.length} 个`);
  const container = document.querySelector('[data-export-models]');
  if (!container) return;
  container.innerHTML = modelList
    .map(
      (model) => `
        <span
          class="export-model-chip ${model === defaultModel ? 'is-default' : ''}"
          data-export-model-chip="${escapeHtml(model)}"
          role="listitem"
        >
          ${escapeHtml(model)}${model === defaultModel ? ' · 默认' : ''}
        </span>
      `,
    )
    .join('');
}

function renderOpenCodeConfig(config) {
  const card = document.querySelector('[data-opencode-config-card]');
  const output = document.querySelector('[data-opencode-provider-json]');
  if (!card || !output) return;
  const isOpenCode = (config?.targetSlug || '').toLowerCase() === 'opencode';
  card.hidden = !isOpenCode;
  output.textContent = config?.openCodeProviderJson || '{}\n';
}

async function refreshImportLinkFromServer() {
  if (!state.serverAvailable || !state.hasServerSession || !enabledKeyCount()) return;
  const requestId = (state.importRequestId += 1);
  try {
    const result = await serverClient.getImportUrl({ target: state.target, model: state.model });
    if (requestId === state.importRequestId) {
      document.querySelector('[data-import-link]').value = result.url;
      renderExportModelSummary({
        defaultModel: result.defaultModel,
        availableModels: result.availableModels,
      });
      const openImport = document.querySelector('[data-open-import]');
      if (openImport) {
        openImport.setAttribute('href', result.url);
        openImport.removeAttribute('aria-disabled');
      }
    }
  } catch {
    if (requestId === state.importRequestId && !enabledKeyCount()) {
      document.querySelector('[data-import-link]').value = '';
    }
  }
}

function renderHelpLinks() {
  const container = document.querySelector('[data-help-links]');
  if (container) container.innerHTML = '';
}

function bindStaticActions() {
  document.querySelector('[data-copy-link]').addEventListener('click', async (event) => {
    const input = document.querySelector('[data-import-link]');
    await copyText(input.value, event.currentTarget);
  });

  window.addEventListener('hashchange', routeFromHash);
  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-route]');
    if (link) {
      setActiveView(link.dataset.route);
      return;
    }

    const authClose = event.target.closest('[data-auth-close]');
    if (authClose) {
      toggleAuthPanel(false);
      return;
    }

    const authMode = event.target.closest('[data-auth-mode]');
    if (authMode) {
      state.authMode = authMode.dataset.authMode || 'login';
      if (state.authMode === 'register') {
        prepareCaptchaChallenge();
      } else {
        state.captcha = { id: '', question: '' };
        state.passwordResetRequested = false;
        const answerInput = document.querySelector('[data-captcha-answer]');
        if (answerInput) answerInput.value = '';
      }
      renderAuthPanel();
      return;
    }

    const authToggle = event.target.closest('[data-auth-toggle]');
    if (authToggle) {
      toggleAuthPanel();
      return;
    }

    const amount = event.target.closest('[data-recharge-option]');
    if (amount) {
      state.selectedRechargePlanId = amount.dataset.rechargePlanId || '';
      state.selectedRechargeCny = Number(amount.dataset.rechargeOption);
      state.selectedRechargePlan = amount.dataset.rechargePlan || 'balance';
      renderRechargeOptions();
      renderImportLink();
      return;
    }

    const createKey = event.target.closest('[data-create-key]');
    if (createKey) {
      handleCreateKey(createKey);
      return;
    }

    const modelGroup = event.target.closest('[data-model-group-option]');
    if (modelGroup) {
      state.modelGroup = modelGroup.dataset.modelGroupOption || 'OpenAI';
      state.model = defaultModelForGroup(state.modelGroup);
      state.playgroundModel = state.model;
      renderModelGroupPicker();
      renderImportFamilyPicker();
      renderImportLink();
      renderClientConfig();
      renderSetupGuides();
      renderPlayground();
      return;
    }

    const family = event.target.closest('[data-import-family-option]');
    if (family) {
      state.modelGroup = family.dataset.importFamilyOption || 'OpenAI';
      state.model = defaultModelForGroup(state.modelGroup);
      state.playgroundModel = state.model;
      renderModelGroupPicker();
      renderImportFamilyPicker();
      renderImportLink();
      renderClientConfig();
      renderSetupGuides();
      renderPlayground();
      return;
    }

    const playgroundSend = event.target.closest('[data-playground-send]');
    if (playgroundSend) {
      handlePlaygroundSend();
      return;
    }

    const playgroundTest = event.target.closest('[data-playground-test]');
    if (playgroundTest) {
      handlePlaygroundConnectivityTest();
      return;
    }

    const deleteMessage = event.target.closest('[data-delete-message]');
    if (deleteMessage) {
      deletePlaygroundMessage(deleteMessage.dataset.deleteMessage);
      return;
    }

    const clearPlayground = event.target.closest('[data-clear-playground]');
    if (clearPlayground) {
      clearPlaygroundMessages();
      return;
    }

    const playgroundFamily = event.target.closest('[data-playground-family]');
    if (playgroundFamily) {
      state.playgroundFamily = playgroundFamily.dataset.playgroundFamily || 'All';
      const nextModel = filteredPlaygroundModels()[0]?.model;
      if (nextModel) {
        state.playgroundModel = nextModel;
        state.model = nextModel;
      }
      renderPlayground();
      return;
    }

    const playgroundModelCard = event.target.closest('[data-playground-model-card]');
    if (playgroundModelCard) {
      state.playgroundModel = playgroundModelCard.dataset.playgroundModelCard || state.playgroundModel;
      state.model = state.playgroundModel;
      renderPlayground();
      renderImportLink();
      renderClientConfig();
      return;
    }

    const selectPlaygroundModel = event.target.closest('[data-select-playground-model]');
    if (selectPlaygroundModel) {
      state.playgroundModel = selectPlaygroundModel.dataset.selectPlaygroundModel || state.playgroundModel;
      state.model = state.playgroundModel;
      setActiveView('playground');
      renderPlayground();
      return;
    }

    const useModelInPlayground = event.target.closest('[data-use-model-in-playground]');
    if (useModelInPlayground) {
      setActiveView('playground');
      renderPlayground();
      return;
    }

    const suggestion = event.target.closest('[data-playground-suggestion]');
    if (suggestion) {
      const promptInput = document.querySelector('[data-playground-prompt]');
      if (promptInput) {
        promptInput.value = suggestion.dataset.playgroundSuggestion || '';
        promptInput.focus();
      }
      return;
    }

    const guideTarget = event.target.closest('[data-guide-target]');
    if (guideTarget) {
      state.guideTarget = guideTarget.dataset.guideTarget || 'Codex';
      renderSetupGuides();
      return;
    }

    const register = event.target.closest('[data-register-account]');
    if (register) {
      handleRegisterAccount(register);
      return;
    }

    const login = event.target.closest('[data-login-account]');
    if (login) {
      handleLoginAccount(login);
      return;
    }

    const changePassword = event.target.closest('[data-change-password]');
    if (changePassword) {
      handleChangePassword(changePassword);
      return;
    }

    const resetRequest = event.target.closest('[data-password-reset-request]');
    if (resetRequest) {
      handlePasswordResetRequest(resetRequest);
      return;
    }

    const resetConfirm = event.target.closest('[data-password-reset-confirm]');
    if (resetConfirm) {
      handlePasswordResetConfirm(resetConfirm);
      return;
    }

    const ownerClaim = event.target.closest('[data-owner-claim]');
    if (ownerClaim) {
      handleOwnerClaim(ownerClaim);
      return;
    }

    const verify = event.target.closest('[data-verify-account]');
    if (verify) {
      handleVerifyAccount(verify);
      return;
    }

    const toggleKeyButton = event.target.closest('[data-toggle-key]');
    if (toggleKeyButton) {
      toggleKey(toggleKeyButton.dataset.toggleKey);
      return;
    }

    const renameKeyButton = event.target.closest('[data-rename-key]');
    if (renameKeyButton) {
      renameKey(renameKeyButton.dataset.renameKey);
      return;
    }

    const deleteKeyButton = event.target.closest('[data-delete-key]');
    if (deleteKeyButton) {
      deleteKey(deleteKeyButton.dataset.deleteKey);
      return;
    }

    const copyKey = event.target.closest('[data-copy-key-id]');
    if (copyKey) {
      handleCopyKey(copyKey.dataset.copyKeyId, copyKey);
      return;
    }

    const openImport = event.target.closest('[data-open-import]');
    if (openImport) {
      const importUrl = document.querySelector('[data-import-link]').value;
      if (!importUrl) {
        event.preventDefault();
        setActionMessage('请先创建并开启 Key');
        return;
      }
      openImport.setAttribute('href', importUrl);
      return;
    }

    const alertSave = event.target.closest('[data-balance-alert-save]');
    if (alertSave) {
      handleBalanceAlertSave(alertSave);
      return;
    }

    const alertTest = event.target.closest('[data-balance-alert-test]');
    if (alertTest) {
      handleBalanceAlertTest(alertTest);
      return;
    }

    const redeem = event.target.closest('[data-redeem-code], [data-billing-redeem-code]');
    if (redeem) {
      handleRedeemCode(redeem);
      return;
    }

    const refresh = event.target.closest('[data-refresh-health]');
    if (refresh) {
      handleRefreshHealth(event);
      return;
    }

    const retryDashboard = event.target.closest('[data-retry-dashboard]');
    if (retryDashboard) {
      handleRetryDashboard(retryDashboard);
      return;
    }

    const copyAuthJson = event.target.closest('[data-copy-auth-json]');
    if (copyAuthJson) {
      copyText(document.querySelector('[data-auth-json]').textContent, copyAuthJson);
      return;
    }

    const copyConfigToml = event.target.closest('[data-copy-config-toml]');
    if (copyConfigToml) {
      copyText(document.querySelector('[data-config-toml]').textContent, copyConfigToml);
      return;
    }

    const copyOpenCodeConfig = event.target.closest('[data-copy-opencode-config]');
    if (copyOpenCodeConfig) {
      copyText(document.querySelector('[data-opencode-provider-json]').textContent, copyOpenCodeConfig);
      return;
    }

    const copyGuideJson = event.target.closest('[data-copy-guide-json]');
    if (copyGuideJson) {
      copyText(document.querySelector('[data-guide-json]').textContent, copyGuideJson);
      return;
    }

    const copyGuideToml = event.target.closest('[data-copy-guide-toml]');
    if (copyGuideToml) {
      copyText(document.querySelector('[data-guide-toml]').textContent, copyGuideToml);
      return;
    }

    const copyMacCommand = event.target.closest('[data-copy-mac-command]');
    if (copyMacCommand) {
      copyText(document.querySelector('[data-mac-command]').textContent, copyMacCommand);
      return;
    }

    const copyWinCommand = event.target.closest('[data-copy-win-command]');
    if (copyWinCommand) {
      copyText(document.querySelector('[data-win-command]').textContent, copyWinCommand);
      return;
    }

    const copyFlowCodexToml = event.target.closest('[data-copy-flow-codex-toml]');
    if (copyFlowCodexToml) {
      const manualToml = document.querySelector('[data-config-toml]')?.textContent || '';
      const flowToml = document.querySelector('[data-flow-codex-toml]')?.innerText.replace(/^7\s*/, '') || '';
      copyText(manualToml || flowToml, copyFlowCodexToml);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      toggleAuthPanel(false);
      return;
    }
    const promptInput = event.target.closest?.('[data-playground-prompt]');
    if (promptInput && event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      handlePlaygroundSend();
    }
  });

  document.addEventListener('change', (event) => {
    const playgroundModel = event.target.closest('[data-playground-model]');
    if (playgroundModel) {
      state.playgroundModel = playgroundModel.value || state.playgroundModel;
      state.model = state.playgroundModel;
      renderPlayground();
    }
  });

  document.addEventListener('input', (event) => {
    const apiSearch = event.target.closest('[data-api-search]');
    if (apiSearch) {
      state.apiSearch = apiSearch.value.trim();
      renderApiKeys();
    }

    const modelSearch = event.target.closest('[data-model-catalog-search]');
    if (modelSearch) {
      state.modelSearch = modelSearch.value.trim();
      renderModelCatalog();
    }

    const playgroundSearch = event.target.closest('[data-playground-model-search]');
    if (playgroundSearch) {
      state.playgroundModelSearch = playgroundSearch.value.trim();
      renderPlayground();
    }
  });
}

function startCarouselTimer() {
  return undefined;
}

function toggleAuthPanel(force) {
  const panel = document.querySelector('[data-auth-panel]');
  const button = document.querySelector('[data-auth-toggle]');
  if (!panel || !button) return;
  const shouldOpen = typeof force === 'boolean' ? force : panel.hidden;
  panel.hidden = !shouldOpen;
  button.setAttribute('aria-expanded', String(shouldOpen));
  if (shouldOpen) {
    if (state.authMode === 'register') {
      prepareCaptchaChallenge();
    }
    window.setTimeout(() => {
      panel.querySelector('[data-register-email]')?.focus();
    }, 0);
  }
}

async function prepareCaptchaChallenge(options = {}) {
  if (!options.force && state.captcha.id) {
    return state.captcha;
  }
  try {
    const challenge = await serverClient.challenge();
    state.captcha = {
      id: challenge.required !== false ? challenge.id || '' : '',
      question: challenge.required !== false ? challenge.question || '' : '',
    };
    renderAuthPanel();
  } catch {
    state.captcha = { id: '', question: '' };
  }
  return state.captcha;
}

async function buildAuthPayload({ email, password, requireCaptcha = false }) {
  const payload = { email, password };
  if (!requireCaptcha) {
    return payload;
  }

  await prepareCaptchaChallenge();
  if (!state.captcha.id) {
    return payload;
  }

  const answerInput = document.querySelector('[data-captcha-answer]');
  const captchaAnswer = answerInput?.value.trim() || '';
  if (!captchaAnswer) {
    const error = new Error('请先完成安全验证');
    error.localValidation = true;
    throw error;
  }
  return {
    ...payload,
    captchaId: state.captcha.id,
    captchaAnswer,
  };
}

async function refreshCaptchaAfterAuthError(error) {
  if (state.authMode !== 'register' || !/验证码|验证|captcha|challenge/i.test(error.message || '')) {
    return false;
  }
  const answerInput = document.querySelector('[data-captcha-answer]');
  if (answerInput) {
    answerInput.value = '';
  }
  await prepareCaptchaChallenge({ force: true });
  return true;
}

function bindCopyButtons(scope) {
  for (const button of scope.querySelectorAll('[data-copy-value]')) {
    button.addEventListener('click', async () => {
      await copyText(button.dataset.copyValue, button);
    });
  }
}

function routeFromHash() {
  const requested = window.location.hash.replace('#', '') || 'dashboard';
  setActiveView(viewMeta[requested] ? requested : 'dashboard');
}

function setActiveView(view) {
  state.view = view;
  document.body.dataset.currentView = view;
  const meta = viewMeta[view];

  setText('[data-view-kicker]', meta.kicker);
  setText('[data-view-title]', meta.title);
  setText('[data-view-desc]', meta.desc);

  for (const panel of document.querySelectorAll('[data-view]')) {
    panel.hidden = panel.dataset.view !== view;
  }

  for (const item of document.querySelectorAll('[data-route]')) {
    const active = item.dataset.route === view;
    item.classList.toggle('is-active', active);
    if (active && item.closest('.workspace-nav')) {
      item.setAttribute('aria-current', 'page');
    } else {
      item.removeAttribute('aria-current');
    }
  }
}

function normalizePlaygroundMessages() {
  for (const message of state.playgroundMessages) {
    if (!message.id) {
      message.id = nextPlaygroundMessageId();
    }
  }
}

function nextPlaygroundMessageId() {
  state.playgroundMessageSeq += 1;
  return `msg-${state.playgroundMessageSeq}`;
}

function createPlaygroundMessage(role, content) {
  return {
    id: nextPlaygroundMessageId(),
    role,
    content,
  };
}

function resetPlaygroundMessages() {
  state.generatedImage = null;
  state.playgroundMessages = [
    {
      id: 'msg-welcome',
      role: 'assistant',
      content: '先从左侧选择模型，再直接测试文字、代码或图片能力。',
    },
  ];
}

function deletePlaygroundMessage(id) {
  const before = state.playgroundMessages.length;
  state.playgroundMessages = state.playgroundMessages.filter((message) => message.id !== id);
  if (state.playgroundMessages.length === 0) {
    resetPlaygroundMessages();
  }
  if (state.playgroundMessages.length !== before) {
    renderPlayground();
    setActionMessage('消息已删除');
  }
}

function clearPlaygroundMessages() {
  resetPlaygroundMessages();
  renderPlayground();
  setActionMessage('广场已清空');
}

async function handlePlaygroundSend() {
  const promptInput = document.querySelector('[data-playground-prompt]');
  const prompt = promptInput?.value.trim() || '';
  const key = activeApiKey();
  if (!key) {
    setActionMessage('请先登录并创建 Key');
    setActiveView('api');
    return;
  }
  if (!prompt || state.playgroundBusy) {
    return;
  }

  state.playgroundBusy = true;
  state.generatedImage = null;
  state.playgroundMessages.push(createPlaygroundMessage('user', prompt));
  if (promptInput) promptInput.value = '';
  renderPlayground();

  try {
    if (isImageModel(state.playgroundModel)) {
      const result = await serverClient.generateImage({
        apiKey: key.secret,
        body: buildImageRequestBody(state.playgroundModel, prompt),
      });
      state.generatedImage = firstImageSource(result);
      state.playgroundMessages.push(
        createPlaygroundMessage('assistant', state.generatedImage ? '图片已生成。' : '上游返回成功，但没有图片地址。'),
      );
    } else {
      const result = await serverClient.chatCompletion({
        apiKey: key.secret,
        body: {
          model: state.playgroundModel,
          messages: [
            ...state.playgroundMessages
              .filter((message) => message.role === 'user' || message.role === 'assistant')
              .slice(-8)
              .map((message) => ({ role: message.role, content: message.content })),
          ],
          max_tokens: 512,
          metadata: { frist_session_id: `web-playground-${key.id}` },
        },
      });
      state.playgroundMessages.push(createPlaygroundMessage('assistant', assistantTextFromPayload(result)));
    }
    setActionMessage('广场返回成功');
  } catch (error) {
    state.playgroundMessages.push(createPlaygroundMessage('assistant', error.message || '模型暂时不可用'));
    setActionMessage(error.message || '模型暂时不可用');
  } finally {
    state.playgroundBusy = false;
    renderPlayground();
  }
}

async function handlePlaygroundConnectivityTest() {
  const promptInput = document.querySelector('[data-playground-prompt]');
  const prompt = promptInput?.value.trim() || '';
  const key = activeApiKey();
  if (!key) {
    setActionMessage('请先登录并创建 Key');
    setActiveView('api');
    return;
  }
  if (state.playgroundBusy) {
    return;
  }

  state.playgroundBusy = true;
  state.generatedImage = null;
  state.playgroundConnectivity = {
    status: 'info',
    text: `正在实测 ${state.playgroundModel}`,
  };
  const startedAt = performance.now();
  renderPlayground();

  try {
    let resultText = 'OK';
    if (isImageModel(state.playgroundModel)) {
      const result = await serverClient.generateImage({
        apiKey: key.secret,
        body: buildImageRequestBody(state.playgroundModel, prompt || 'Frist-API 连通性测试'),
      });
      state.generatedImage = firstImageSource(result);
      resultText = state.generatedImage ? '图片已返回' : '上游成功但无图片地址';
    } else {
      const result = await serverClient.chatCompletion({
        apiKey: key.secret,
        body: {
          model: state.playgroundModel,
          messages: [{ role: 'user', content: prompt || '只回复 OK' }],
          max_tokens: 16,
          metadata: { frist_session_id: `web-connectivity-${key.id}-${state.playgroundModel}` },
        },
      });
      resultText = assistantTextFromPayload(result) || 'OK';
    }
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));
    const compactResult = resultText.length > 28 ? `${resultText.slice(0, 28)}...` : resultText;
    state.playgroundConnectivity = {
      status: 'success',
      text: `${state.playgroundModel} 通过 · ${latencyMs}ms · ${compactResult}`,
    };
    state.playgroundMessages.push(createPlaygroundMessage('assistant', `连通实测通过：${state.playgroundModel}，${latencyMs}ms。`));
    setActionMessage('广场连通实测通过');
  } catch (error) {
    state.playgroundConnectivity = {
      status: 'error',
      text: `${state.playgroundModel} 失败 · ${error.message || '模型暂时不可用'}`,
    };
    state.playgroundMessages.push(createPlaygroundMessage('assistant', error.message || '模型暂时不可用'));
    setActionMessage(error.message || '模型暂时不可用', 'error');
  } finally {
    state.playgroundBusy = false;
    renderPlayground();
  }
}

async function toggleKey(id) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  try {
    await serverClient.setKeyEnabled(id, { enabled: !key.enabled });
    await reloadServerDashboard(key.enabled ? 'API Key 已关闭' : 'API Key 已开启');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  }
}

async function renameKey(id) {
  const keyInput = document.querySelector(`[data-key-name="${selectorEscape(id)}"]`);
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key || !keyInput) return;

  const name = keyInput.value.trim();
  if (!name) {
    setActionMessage('API Key 名称不能为空');
    keyInput.value = key.name;
    return;
  }

  try {
    await serverClient.renameKey(id, { name });
    await reloadServerDashboard('API Key 已改名');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  }
}

function selectorEscape(value) {
  if (globalThis.CSS?.escape) {
    return globalThis.CSS.escape(String(value));
  }
  return String(value).replace(/["\\]/g, '\\$&');
}

async function deleteKey(id) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  const confirmed = typeof window.confirm !== 'function' || window.confirm(`删除 ${key.name}？`);
  if (!confirmed) return;

  try {
    await serverClient.deleteKey(id);
    await reloadServerDashboard('API Key 已删除');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  }
}

function syncPrimaryAccountState() {
  state.keyEnabled = dashboardData.apiKeys.some((item) => item.enabled);
  state.baseUrl = window.FRIST_API_PUBLIC_BASE_URL || `${normalizeBaseUrl(window.location.origin)}/v1`;
  state.model = defaultModelForGroup(state.modelGroup);
  if (!availableModels().includes(state.playgroundModel)) {
    state.playgroundModel = state.model;
  }
}

function defaultModelForGroup(group) {
  const normalized = String(group || 'OpenAI').toLowerCase();
  const models = availableModels().filter((model) => modelMatchesUiGroup(model, group));
  if (models.length > 0) return sortModelsByStrength(models)[0];
  if (normalized === 'claude') return 'claude-opus-4-6-thinking-c';
  if (normalized === 'gemini') return 'gemini-2.5-flash';
  if (normalized === 'deepseek') return 'deepseek-v4-flash';
  if (normalized === 'other') return 'deepseek-v4-flash';
  return 'gpt-5.5';
}

function enabledKeyCount() {
  return dashboardData.apiKeys.filter((item) => item.enabled).length;
}

async function handleCreateKey(createKey) {
  setScopedFeedback('[data-key-feedback]', '正在创建 API Key...', 'info');
  setActionMessage('API Key 创建中...', 'info');
  setButtonBusy(createKey, true, '创建中');
  try {
    await serverClient.createKey({
      name: `Frist Key ${dashboardData.apiKeys.length + 1}`,
      modelGroup: state.modelGroup,
    });
    await reloadServerDashboard('API Key 已创建，可直接导入 CC Switch');
    setScopedFeedback('[data-key-feedback]', 'API Key 已创建，可直接复制或导入 CC Switch。', 'success');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-key-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(createKey, false);
  }
}

async function handleRegisterAccount(register) {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  setActionMessage('注册中...', 'info');
  setScopedFeedback('[data-auth-feedback]', '正在提交注册信息...', 'info');
  setButtonBusy(register, true, '注册中');
  try {
    const payload = await buildAuthPayload({ email, password, requireCaptcha: true });
    await serverClient.register(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '注册成功，可以创建 Key。');
    await reloadServerDashboard('注册成功，可以创建 Key');
    setScopedFeedback('[data-auth-feedback]', '注册成功，可以创建 Key。', 'success');
    toggleAuthPanel(false);
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-auth-feedback]', serverError.message, 'error');
    await refreshCaptchaAfterAuthError(serverError);
  } finally {
    setButtonBusy(register, false);
  }
}

async function handleLoginAccount(login) {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  setActionMessage('登录中...', 'info');
  setScopedFeedback('[data-auth-feedback]', '正在验证邮箱和密码...', 'info');
  setButtonBusy(login, true, '登录中');
  try {
    const payload = await buildAuthPayload({ email, password });
    await serverClient.login(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '登录成功，可以继续充值、创建 Key 或导入 CC Switch。');
    await reloadServerDashboard('登录成功');
    setActionMessage('登录成功', 'success');
    setScopedFeedback('[data-auth-feedback]', '登录成功，可以继续创建 Key。', 'success');
    toggleAuthPanel(false);
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-auth-feedback]', serverError.message, 'error');
    await refreshCaptchaAfterAuthError(serverError);
  } finally {
    setButtonBusy(login, false);
  }
}

async function handleChangePassword(button) {
  const currentPassword = document.querySelector('[data-register-password]').value;
  const newPassword = document.querySelector('[data-new-password]').value;

  setButtonBusy(button, true, '保存中');
  try {
    await serverClient.changePassword({ oldPassword: currentPassword, newPassword });
    document.querySelector('[data-register-password]').value = newPassword;
    document.querySelector('[data-new-password]').value = '';
    await reloadServerDashboard('密码已更新');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handlePasswordResetRequest(button) {
  const email = document.querySelector('[data-register-email]').value;
  setScopedFeedback('[data-auth-feedback]', '正在发送重置验证码...', 'info');
  setButtonBusy(button, true, '发送中');
  try {
    const result = await serverClient.requestPasswordReset({ email });
    state.passwordResetRequested = true;
    renderAuthPanel();
    setScopedFeedback('[data-auth-feedback]', result.message || '如果邮箱存在，我们会发送重置验证码。', 'success');
  } catch (serverError) {
    setScopedFeedback('[data-auth-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handlePasswordResetConfirm(button) {
  const email = document.querySelector('[data-register-email]').value;
  const code = document.querySelector('[data-reset-code]')?.value.trim() || '';
  const newPassword = document.querySelector('[data-reset-password]')?.value || '';
  setScopedFeedback('[data-auth-feedback]', '正在重置密码...', 'info');
  setButtonBusy(button, true, '重置中');
  try {
    await serverClient.confirmPasswordReset({ email, code, newPassword });
    const passwordInput = document.querySelector('[data-register-password]');
    const resetCodeInput = document.querySelector('[data-reset-code]');
    const resetPasswordInput = document.querySelector('[data-reset-password]');
    if (passwordInput) passwordInput.value = newPassword;
    if (resetCodeInput) resetCodeInput.value = '';
    if (resetPasswordInput) resetPasswordInput.value = '';
    state.passwordResetRequested = false;
    renderAuthPanel();
    setScopedFeedback('[data-auth-feedback]', '密码已重置，可以用新密码登录。', 'success');
  } catch (serverError) {
    setScopedFeedback('[data-auth-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleOwnerClaim(button) {
  const codeInput = document.querySelector('[data-owner-claim-code]');
  const code = codeInput?.value.trim() || '';
  if (!code) {
    setActionMessage('请填写一次性身份码', 'error');
    return;
  }

  setButtonBusy(button, true, '激活中');
  try {
    const result = await serverClient.claimAdmin({ code });
    if (codeInput) {
      codeInput.value = '';
    }
    businessState.customer.isAdmin = Boolean(result.user?.isAdmin);
    await reloadServerDashboard(result.message || '管理员身份已激活');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleVerifyAccount(button) {
  const codeInput = document.querySelector('[data-verify-code]');
  if (!codeInput) return;
  const code = codeInput.value;

  setButtonBusy(button, true, '验证中');
  try {
    await serverClient.verify({ code });
    codeInput.value = '';
    setText('[data-verification-hint]', '邮箱已验证，可以充值并创建 Key。');
    await reloadServerDashboard('邮箱已验证');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleCopyKey(id, button) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  await copyText(key.secret, button);
}

async function handleBalanceAlertSave(button) {
  if (!state.hasServerSession) {
    setActiveView('billing');
    setScopedFeedback('[data-balance-alert-feedback]', '请先登录，再保存余额预警。', 'error');
    return;
  }

  const payload = readBalanceAlertForm();
  setScopedFeedback('[data-balance-alert-feedback]', '正在保存余额预警...', 'info');
  setButtonBusy(button, true, '保存中');
  try {
    await serverClient.saveBalanceAlert(payload);
    await reloadServerDashboard('余额预警已保存');
    setScopedFeedback('[data-balance-alert-feedback]', '余额预警已保存。', 'success');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-balance-alert-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleBalanceAlertTest(button) {
  if (!state.hasServerSession) {
    setActiveView('billing');
    setScopedFeedback('[data-balance-alert-feedback]', '请先登录，再发送测试邮件。', 'error');
    return;
  }

  const payload = readBalanceAlertForm();
  setScopedFeedback('[data-balance-alert-feedback]', '正在发送测试邮件...', 'info');
  setButtonBusy(button, true, '发送中');
  try {
    await serverClient.sendBalanceAlertTest(payload);
    await reloadServerDashboard('测试邮件已发送');
    setScopedFeedback('[data-balance-alert-feedback]', '测试邮件已发送，请检查收件箱。', 'success');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-balance-alert-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

function readBalanceAlertForm() {
  const enabled = document.querySelector('[data-balance-alert-enabled]')?.checked !== false;
  const thresholdUsd = Number(document.querySelector('[data-balance-alert-threshold]')?.value || 0);
  const email = document.querySelector('[data-balance-alert-email]')?.value.trim() || dashboardData.accountSummary.email;
  return {
    enabled,
    thresholdUsd: Number.isFinite(thresholdUsd) ? thresholdUsd : 0,
    email,
  };
}

async function handleRedeemCode(button) {
  const scope = button.closest('.view-panel') || document;
  const input = scope.querySelector('[data-exchange-code], [data-billing-exchange-code]');
  if (!input) return;
  setButtonBusy(button, true, '兑换中');
  try {
    const result = await serverClient.redeem({ code: input.value || '' });
    input.value = '';
    const message = result.redemption?.credit
      ? `兑换码已生效，到账 ${result.redemption.credit}`
      : '兑换码已生效';
    setScopedFeedback('[data-payment-feedback]', message, 'success');
    await reloadServerDashboard(message);
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
    setScopedFeedback('[data-payment-feedback]', serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleRefreshHealth(event) {
  event?.preventDefault();
  setActionMessage('连通性刷新中...', 'info');
  try {
    await reloadServerDashboard('连通性已刷新');
    setActionMessage('连通性已刷新', 'success');
  } catch (error) {
    setActionMessage(error.message || '刷新失败', 'error');
  }
}

async function handleRetryDashboard(button) {
  setButtonBusy(button, true, '连接中');
  setActionMessage('正在重新连接...', 'info');
  try {
    await loadDashboardData();
    setActionMessage(state.serverAvailable ? '后端已连接' : '后端仍不可用', state.serverAvailable ? 'success' : 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function reloadServerDashboard(message) {
  const payload = await serverClient.loadDashboard();
  const nextData = normalizeFristDashboard(payload, emptyDashboard);
  state.serverAvailable = true;
  state.hasServerSession = Boolean(payload.authenticated);
  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
  syncPrimaryAccountState();
  render();
  setActionMessage(message, 'success');
}

function activeApiKey() {
  return dashboardData.apiKeys.find((item) => item.enabled && item.secret);
}

function isImageModel(model) {
  return /image|dall|gpt-image/i.test(String(model || ''));
}

// 广场生图默认走轻量 PNG，避免低带宽公网验收被慢图拖垮。
function buildImageRequestBody(model, prompt) {
  return {
    model,
    prompt,
    size: '1024x1024',
    quality: 'low',
    output_format: 'png',
    n: 1,
  };
}

function assistantTextFromPayload(payload) {
  const choiceText = payload?.choices?.[0]?.message?.content;
  if (typeof choiceText === 'string' && choiceText.trim()) {
    return choiceText.trim();
  }
  const outputText = (payload?.output || [])
    .flatMap((item) => item.content || [])
    .map((item) => item.text || item.output_text || '')
    .filter(Boolean)
    .join('\n');
  if (outputText.trim()) {
    return outputText.trim();
  }
  if (typeof payload?.text === 'string' && payload.text.trim()) {
    return payload.text.trim();
  }
  return '模型已返回，但没有文本内容。';
}

function firstImageSource(payload) {
  const first = payload?.data?.[0] || {};
  if (first.url) return String(first.url);
  if (first.b64_json) return `data:image/png;base64,${first.b64_json}`;
  const responseImage = (payload?.output || [])
    .flatMap((item) => item.content || [])
    .find((item) => item.image_url || item.b64_json);
  if (responseImage?.image_url) return responseImage.image_url;
  if (responseImage?.b64_json) return `data:image/png;base64,${responseImage.b64_json}`;
  return '';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setActionMessage(message, type = 'success') {
  for (const element of document.querySelectorAll('[data-action-message]')) {
    element.textContent = message;
    element.classList.add('is-visible');
    element.classList.toggle('action-message--success', type === 'success');
    element.classList.toggle('action-message--error', type === 'error');
    element.classList.toggle('action-message--info', type === 'info');
  }
}

function setScopedFeedback(selector, message, type = 'info') {
  for (const element of document.querySelectorAll(selector)) {
    element.textContent = message;
    element.classList.toggle('field-feedback--success', type === 'success');
    element.classList.toggle('field-feedback--error', type === 'error');
    element.classList.toggle('field-feedback--info', type === 'info');
  }
}

function setButtonBusy(button, busy, busyText = '处理中') {
  if (!button) return;
  if (busy) {
    button.dataset.previousText = button.textContent || '';
    button.textContent = busyText;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    return;
  }
  button.textContent = button.dataset.previousText || button.textContent;
  button.disabled = false;
  button.removeAttribute('aria-busy');
  delete button.dataset.previousText;
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const fallback = document.createElement('textarea');
    fallback.value = text;
    fallback.setAttribute('readonly', '');
    fallback.style.position = 'fixed';
    fallback.style.opacity = '0';
    document.body.appendChild(fallback);
    fallback.select();
    document.execCommand('copy');
    fallback.remove();
  }
  const previous = button.textContent;
  button.textContent = '已复制';
  window.setTimeout(() => {
    button.textContent = previous;
  }, 1200);
}

function setText(selector, value) {
  for (const element of document.querySelectorAll(selector)) {
    element.textContent = value;
  }
}

bindStaticActions();
render();
startCarouselTimer();
loadDashboardData().catch(() => {
  state.dashboardLoading = false;
  render();
});

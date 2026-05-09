import {
  buildClientSetupCommands,
  buildCcSwitchMcpImportUrl,
  normalizeClientAvailableModels,
  normalizeBaseUrl,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  summarizeModelHealth,
} from './core.js?v=20260508-visual-qa2';
import {
  buildBusinessClientConfig,
  buildBusinessImportUrl,
  createBusinessStateFromDashboard,
} from './businessFlow.js?v=20260508-visual-qa2';
import { createFristApiBrowserClient, normalizeFristDashboard } from './serverClient.js?v=20260508-visual-qa2';

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
    emailMasked: '',
    displayName: '',
    avatarUrl: '',
    isAdmin: false,
  },
  apiKeys: [],
  channelChecks: [],
  helpLinks: [],
  importTargets: ['Claude', 'Codex', 'Gemini', 'OpenCode', 'OpenClaw', 'Hermes'],
  modelUsage: [],
  modelCatalog: [],
  usageRecords: [],
  usageAnomalies: [],
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
const revealedApiKeys = new Map();

const serverClient = createFristApiBrowserClient({
  baseUrl: window.FRIST_API_SERVER_BASE_URL || window.location.origin,
});

const catalogTemplate = [
  { model: 'gpt-5.5', family: 'OpenAI', tagline: '推理和代码主力', context: '1M 上下文', price: '官方 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M', available: false },
  { model: 'gpt-5.4', family: 'OpenAI', tagline: '日常问答和代码补全', context: '1M 上下文', price: '官方 输入 $2.50 / 缓存 $0.25 / 输出 $15.00 每 1M', available: false },
  { model: 'gpt-5.4-mini', family: 'OpenAI', tagline: '轻量代码和快速问答', context: '400K 上下文', price: '官方 输入 $0.75 / 缓存 $0.075 / 输出 $4.50 每 1M', available: false },
  { model: 'gpt-image-2', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '官方 文字入 $5 / 文字缓存 $1.25 / 图入 $8 / 图缓存 $2 / 图出 $30 每 1M', available: false },
  { model: 'gpt-image-1.5', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '官方 文字入 $5 / 文字缓存 $1.25 / 文字出 $10 / 图入 $8 / 图缓存 $2 / 图出 $32 每 1M', available: false },
  { model: 'gpt-5.3-codex', family: 'OpenAI', tagline: 'Codex 专用代码模型', context: '400K 上下文', price: '官方 输入 $1.75 / 缓存 $0.175 / 输出 $14.00 每 1M', available: false },
  { model: 'gpt-5-codex', family: 'OpenAI', tagline: 'Codex 代码模型', context: '400K 上下文', price: '官方 输入 $1.25 / 缓存 $0.125 / 输出 $10.00 每 1M', available: false },
  { model: 'gpt-4o', family: 'OpenAI', tagline: '通用多模态', context: '128K 上下文', price: '官方 输入 $2.50 / 缓存 $1.25 / 输出 $10.00 每 1M', available: false },
  { model: 'claude-opus-4-6-thinking-c', family: 'Claude', tagline: '复杂开发和长链路推理', context: '长上下文', price: '官方 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M', available: false },
  { model: 'gemini-2.5-flash', family: 'Gemini', tagline: '多模态和轻量任务', context: '1M 上下文', price: '官方 ≤200K 输入 $0.30 / 缓存 $0.03 / 输出 $2.50 每 1M', available: false },
  { model: 'deepseek-v4-flash', family: 'DeepSeek', tagline: 'Codex 桌面版官方兼容网关', context: 'OpenAI v1 兼容', price: '官方 缓存命中 $0.014 / 输入 $0.14 / 输出 $0.28 每 1M', available: false },
  { model: 'deepseek-v4-pro', family: 'DeepSeek', tagline: '推理模型别名', context: 'OpenAI v1 兼容', price: '官方 缓存命中 $0.035 / 输入 $0.435 / 输出 $0.87 每 1M', available: false },
];
const officialModelTemplateByGroup = Object.freeze({
  OpenAI: Object.freeze(['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2', 'gpt-image-1.5', 'gpt-5.3-codex', 'gpt-5-codex', 'gpt-4o']),
  Claude: Object.freeze(['claude-opus-4-6-thinking-c', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c']),
  Gemini: Object.freeze(['gemini-2.5-flash']),
  DeepSeek: Object.freeze(['deepseek-v4-flash', 'deepseek-v4-pro']),
});

const viewMeta = {
  dashboard: {
    kicker: 'Frist',
    title: '工作台',
    desc: '',
  },
  playground: {
    kicker: 'Test',
    title: '测试',
    desc: '',
  },
  api: {
    kicker: 'Key',
    title: 'API',
    desc: '',
  },
  billing: {
    kicker: 'Billing',
    title: '充值',
    desc: '',
  },
  switch: {
    kicker: 'Import',
    title: '导入',
    desc: '',
  },
  analytics: {
    kicker: 'Data',
    title: '趋势',
    desc: '',
  },
  records: {
    kicker: 'Records',
    title: '记录',
    desc: '',
  },
  subscription: {
    kicker: 'Plan',
    title: '订阅',
    desc: '',
  },
  redeem: {
    kicker: 'Code',
    title: '兑换码',
    desc: '',
  },
  invite: {
    kicker: 'Referral',
    title: '邀请',
    desc: '',
  },
  profile: {
    kicker: 'Profile',
    title: '资料',
    desc: '',
  },
  models: {
    kicker: 'Market',
    title: '模型',
    desc: '',
  },
  docs: {
    kicker: 'Guide',
    title: '配置',
    desc: '',
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
  language: 'zh',
  serverAvailable: false,
  hasServerSession: false,
  importRequestId: 0,
  importFallbackTimer: 0,
  playgroundBusy: false,
  playgroundConnectivity: {
    status: 'idle',
    text: '每 3 分钟检测',
  },
  playgroundMessageSeq: 0,
  playgroundMessages: [
    {
      id: 'msg-welcome',
      role: 'assistant',
      content: '选择模型后测试。',
    },
  ],
  generatedImage: null,
  guideTarget: 'Codex',
  importServerConfig: null,
  importServerSetup: null,
  captcha: {
    id: '',
    question: '',
  },
};

const renderTimers = new Map();
const catalogCache = {
  signature: '',
  rows: [],
};
let lastPlaygroundModelsSignature = '';
let lastPlaygroundLogSignature = '';
let lastPlaygroundImageSignature = '';

function render() {
  renderLoadingState();
  renderAccountSummary();
  renderAuthPanel();
  renderDashboard();
  renderUsage();
  renderUsageAnomalies();
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
  renderCcSwitchUsageGuide();
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
    signalAction('success');
  } catch (error) {
    state.serverAvailable = false;
    state.hasServerSession = false;
    signalAction('error');
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
    usageAnomalies: [],
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
  setText('[data-profile-email]', accountSummary.emailMasked || maskEmail(accountSummary.email) || '未登录');
  setText('[data-profile-display-name]', accountSummary.displayName || accountSummary.userInitials || '未登录');
  setText('[data-profile-plan]', accountSummary.plan || '未登录');
  renderProfileAvatar();
}

function renderAuthPanel() {
  const emailInput = document.querySelector('[data-register-email]');
  const isAdmin = Boolean(businessState.customer.isAdmin);
  const status = businessState.customer.email
    ? businessState.customer.emailVerified
      ? '已登录'
      : '已登录'
    : '登录创建 Key';

  if (emailInput && document.activeElement !== emailInput) {
    emailInput.value = businessState.customer.email;
  }
  for (const hiddenEmail of document.querySelectorAll('[data-auth-form-email]')) {
    hiddenEmail.value = emailInput?.value || businessState.customer.email || '';
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
  setText('[data-auth-title]', state.authMode === 'register' ? '注册' : '登录');
  setText('[data-captcha-question]', state.captcha.question ? `验证 ${state.captcha.question}` : '安全验证');
  setText('[data-email-status]', status);
  setText('[data-verification-hint]', isAdmin ? '管理员已激活' : state.hasServerSession ? '可创建 Key' : status);

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
      ? renderSkeletonRows(2, '消耗')
      : renderRows(modelUsage.slice(0, 2), { compact: true }) || renderEmptyState('无请求');
  }
}

function renderUsageAnomalies() {
  const rows = dashboardData.usageAnomalies || [];
  const status = rows.some((item) => item.severity === 'critical')
    ? '异常'
    : rows.some((item) => item.severity === 'warning')
      ? '关注'
      : '正常';
  for (const statusElement of document.querySelectorAll('[data-usage-anomaly-status]')) {
    statusElement.textContent = status;
    statusElement.className = `status-pill status-pill--${status === '正常' ? 'healthy' : status === '关注' ? 'pending' : 'down'}`;
  }
  for (const container of document.querySelectorAll('[data-usage-anomalies]')) {
    container.innerHTML = rows.length
      ? rows
          .slice(0, 4)
          .map(
            (item) => `
              <article class="usage-anomaly-row usage-anomaly-row--${escapeHtml(item.severity || 'info')}">
                <div>
                  <strong>${escapeHtml(item.title || '异常检测')}</strong>
                  <span>${escapeHtml(item.detail || '')}</span>
                </div>
                <small>${escapeHtml(item.action || '查看记录')}</small>
              </article>
            `,
          )
          .join('')
      : renderEmptyState('无异常');
  }
}

function renderTrendChart() {
  const chart = document.querySelector('[data-token-trend]');
  if (!chart) return;
  const rows = tokenTrendRows();
  const max = Math.max(1, ...rows.map((item) => item.tokens));
  const hasTokens = rows.some((item) => item.tokens > 0);
  const width = 640;
  const height = 180;
  const padding = { top: 20, right: 18, bottom: 32, left: 44 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const points = rows.map((item, index) => {
    const x = padding.left + (innerWidth / Math.max(rows.length - 1, 1)) * index;
    const y = padding.top + innerHeight - (hasTokens ? (item.tokens / max) * innerHeight : innerHeight * 0.38);
    return { ...item, x, y };
  });
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(' ');
  const baseline = height - padding.bottom;
  const area = `${path} L ${points.at(-1).x.toFixed(1)} ${baseline} L ${points[0].x.toFixed(1)} ${baseline} Z`;
  const total = rows.reduce((sum, item) => sum + item.tokens, 0);
  chart.classList.toggle('is-empty', !hasTokens && !state.dashboardLoading);
  chart.innerHTML = `
    <div class="trend-chart__summary">
      <span>7 天 Token</span>
      <strong>${escapeHtml(compactNumber(total))}</strong>
      <small>${hasTokens ? `峰值 ${escapeHtml(compactNumber(max))}` : '暂无真实调用'}</small>
    </div>
    <svg class="trend-chart__svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="最近 7 天 Token 使用趋势">
      <line x1="${padding.left}" y1="${baseline}" x2="${width - padding.right}" y2="${baseline}"></line>
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${baseline}"></line>
      <path class="trend-chart__area" d="${area}"></path>
      <path class="trend-chart__line" d="${path}"></path>
      ${points.map((point) => `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${point.tokens > 0 ? 4.5 : 3}" aria-label="${escapeHtml(point.label)} ${escapeHtml(compactNumber(point.tokens))} Token"></circle>`).join('')}
    </svg>
    <div class="trend-chart__labels">
      ${points.map((point) => `<span><b>${escapeHtml(point.label)}</b><em>${escapeHtml(compactNumber(point.tokens))}</em></span>`).join('')}
    </div>
  `;
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

function compactNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return '0';
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(number >= 10_000_000 ? 0 : 1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(number >= 10_000 ? 0 : 1)}K`;
  return String(Math.round(number));
}

function renderRecentLogs() {
  const container = document.querySelector('[data-recent-logs]');
  if (!container) return;
  const rows = (dashboardData.recentLogs || []).slice(0, 5);
  container.innerHTML = rows.length
    ? rows
        .map(
          (item) => `
            <article class="log-row log-row--compact">
              <span>${escapeHtml(formatCheckedAt(item.at))}</span>
              <strong>${escapeHtml(item.detail)}</strong>
            </article>
          `,
        )
        .join('')
    : renderEmptyState('无日志');
}

function renderUsageRecords() {
  const container = document.querySelector('[data-usage-records]');
  const empty = document.querySelector('[data-usage-records-empty]');
  if (!container) return;
  const rows = dashboardData.usageRecords || [];
  if (empty) {
    empty.hidden = rows.length > 0;
    empty.innerHTML = rows.length ? '' : renderEmptyState('无记录');
  }
  container.innerHTML = rows.length
    ? rows
        .map(
          (item) => `
            <tr>
              <td>${escapeHtml(item.apiKey)}</td>
              <td>${escapeHtml(item.model)}</td>
              <td>${escapeHtml(item.client)}</td>
              <td>${escapeHtml(item.type)}</td>
              <td>${escapeHtml(item.tokens)}</td>
              <td>${escapeHtml(item.amount)}</td>
              <td>${escapeHtml(item.latency)}</td>
              <td>${escapeHtml(formatCheckedAt(item.at))}</td>
            </tr>
          `,
        )
        .join('')
    : '<tr class="table-empty"><td colspan="8">无记录</td></tr>';
}

function renderProfile() {
  setText('[data-profile-key-count]', `${dashboardData.apiKeys.length} 个`);
  setText('[data-profile-balance]', dashboardData.accountSummary.quotaLeft || '$0.00');
  const nameInput = document.querySelector('[data-profile-name-input]');
  const emailInput = document.querySelector('[data-profile-email-input]');
  const avatarInput = document.querySelector('[data-profile-avatar-input]');
  if (nameInput && document.activeElement !== nameInput) {
    nameInput.value = dashboardData.accountSummary.displayName || '';
  }
  if (emailInput && document.activeElement !== emailInput) {
    emailInput.value = dashboardData.accountSummary.email || '';
  }
  if (avatarInput && document.activeElement !== avatarInput) {
    avatarInput.value = dashboardData.accountSummary.avatarUrl || '';
  }
  renderProfileAvatar();
}

function renderProfileAvatar() {
  const initials = dashboardData.accountSummary.userInitials || 'FA';
  const avatarUrl = safeAvatarUrl(dashboardData.accountSummary.avatarUrl || '');
  for (const avatar of document.querySelectorAll('[data-profile-avatar], [data-profile-avatar-mini]')) {
    avatar.classList.toggle('has-image', Boolean(avatarUrl));
    avatar.textContent = avatarUrl ? '' : initials;
    avatar.style.backgroundImage = avatarUrl ? `url("${avatarUrl}")` : '';
  }
}

function renderChannelHealth() {
  const { channelChecks } = dashboardData;
  const compact = document.querySelector('[data-channel-compact]');
  const providerItems = providerSummaries(channelChecks);
  const compactItems = providerItems.map(renderProviderSummary).join('');

  if (compact) {
    compact.innerHTML = state.dashboardLoading
      ? renderSkeletonRows(2, '通道')
      : compactItems || renderEmptyState('未检测');
  }
}

function renderProviderSummary(item) {
  return `
    <article class="provider-row" data-channel-monitor-summary>
      <span class="health-dot health-dot--${item.status}" aria-hidden="true"></span>
      <div class="provider-main">
        <div class="provider-title">
          <strong>${escapeHtml(item.provider)}</strong>
          <span class="monitor-chip monitor-chip--${item.status}">${escapeHtml(item.statusText)}</span>
        </div>
        <small class="provider-meta">${escapeHtml([item.okText, `可用率 ${item.availabilityText}`, item.latencyText, item.checkedText].filter(Boolean).join(' · '))}</small>
        <div class="monitor-history monitor-history--compact" data-channel-monitor-history>
          ${item.history.map((status) => `<i class="${monitorHistoryClass(status)}"></i>`).join('')}
        </div>
        <div class="provider-models">
          ${item.models.map((model) => `<span title="${escapeHtml(model)}">${escapeHtml(publicModelLabel(model))}</span>`).join('')}
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
      slow: 0,
      down: 0,
      latencyTotal: 0,
      latencySamples: 0,
      bestLatency: 0,
      models: [],
      checkedAt: '',
      lastReason: '',
      history: [],
      monitorIntervalSeconds: 0,
    };
    const totalCount = Number(snapshot.totalCount || 1);
    const healthyCount = Number(snapshot.healthyCount ?? (snapshot.ok && !snapshot.maintenance ? 1 : 0));
    const downCount = Number(snapshot.downCount ?? Math.max(0, totalCount - healthyCount));
    const slowCount = Number(snapshot.slowCount || 0);
    current.total += totalCount;
    current.healthy += healthyCount;
    current.down += downCount;
    current.slow += slowCount;
    if (snapshot.ok) {
      const latency = Number(snapshot.latencyMs || 0);
      const averageLatency = Number(snapshot.averageLatencyMs || latency || 0);
      current.bestLatency = current.bestLatency ? Math.min(current.bestLatency, latency) : latency;
      current.latencyTotal += averageLatency || latency;
      current.latencySamples += 1;
    }
    current.models.push(snapshot.model);
    current.checkedAt = [current.checkedAt, snapshot.checkedAt].filter(Boolean).sort().at(-1) || '';
    current.lastReason = snapshot.officialStatus || snapshot.status || current.lastReason;
    current.status = current.healthy > 0 ? summary.status : 'down';
    const interval = Number(snapshot.monitorIntervalSeconds || current.monitorIntervalSeconds || 0);
    current.monitorIntervalSeconds = Number.isFinite(interval) ? interval : 0;
    current.history.push(...(Array.isArray(snapshot.history) ? snapshot.history : []));
    grouped.set(snapshot.provider, current);
  }

  return [...grouped.values()].map((item) => {
    const availability = item.total ? Math.round((item.healthy / item.total) * 1000) / 10 : 0;
    const averageLatency = item.latencySamples ? Math.round(item.latencyTotal / item.latencySamples) : 0;
    const status = item.healthy === 0 ? 'down' : item.down > 0 || item.slow > 0 || item.bestLatency > 1600 ? 'slow' : 'healthy';
    return {
      provider: item.provider,
      status,
      statusText: status === 'healthy' ? '正常' : status === 'slow' ? '降级' : '异常',
      okText: item.healthy > 0 ? `可用 ${item.healthy}/${item.total}` : '离线',
      availabilityText: `${availability}%`,
      latencyText: item.bestLatency ? `最低 ${item.bestLatency}ms / 平均 ${averageLatency}ms` : '',
      checkedText: item.checkedAt ? `最近 ${formatCheckedAt(item.checkedAt)}` : item.lastReason || '未检测',
      intervalText: item.monitorIntervalSeconds ? `${item.monitorIntervalSeconds} 秒刷新` : '',
      history: item.history.slice(-12),
      models: normalizeOfficialModelList([...new Set(item.models)]).slice(0, 4),
    };
  });
}

function formatCheckedAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || '-');
  }
  return formatClockTime(date);
}

function formatClockTime(date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function monitorHistoryClass(status) {
  if (status === 'ok' || status === 'healthy' || status === 'operational') return 'is-ok';
  if (status === 'slow' || status === 'degraded') return 'is-slow';
  return 'is-down';
}

function renderPlayground() {
  normalizePlaygroundMessages();
  const select = document.querySelector('[data-playground-model]');
  const rows = filteredPlaygroundModels();
  const models = availableModels();
  if (!models.includes(state.playgroundModel)) {
    state.playgroundModel = models[0] || 'gpt-5.5';
  }

  const modelsSignature = models.join('|');
  if (select && document.activeElement !== select && modelsSignature !== lastPlaygroundModelsSignature) {
    select.innerHTML = models
      .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(publicModelLabel(model))}</option>`)
      .join('');
    lastPlaygroundModelsSignature = modelsSignature;
  }
  if (select && document.activeElement !== select) {
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

  renderPlaygroundLog();
  renderPlaygroundImageOutput();

  const sendButton = document.querySelector('[data-playground-send]');
  if (sendButton) {
    sendButton.disabled = state.playgroundBusy;
    sendButton.textContent = isImageModel(state.playgroundModel) ? '生成' : '发送';
    sendButton.classList.toggle('is-busy', state.playgroundBusy);
    sendButton.toggleAttribute('aria-busy', state.playgroundBusy);
  }

  const testButton = document.querySelector('[data-playground-test]');
  if (testButton) {
    testButton.disabled = state.playgroundBusy;
    testButton.textContent = '检测';
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
  setText('[data-playground-model-count]', `${rows.length} 个`);
  if (!container) return;

  container.innerHTML = rows
    .map((item) => {
      const active = item.model === state.playgroundModel;
      const summary = modelHealthSummaryFor(item.model);
      const label = publicModelLabel(item.model);
      const metaLabel = publicModelMetaLabel(item.model, item.family);
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
            <strong title="${escapeHtml(item.model)}">${escapeHtml(label)}</strong>
            <small title="${escapeHtml(item.model)}">${escapeHtml(item.family)} · ${escapeHtml(metaLabel)}</small>
          </span>
          <span class="playground-model-row__meta">${escapeHtml(summary.label)}</span>
        </button>
      `;
    })
    .join('') || renderEmptyState('无结果');
}

function renderPlaygroundLog() {
  const log = document.querySelector('[data-playground-log]');
  if (!log) return;
  const signature = state.playgroundMessages.map((message) => `${message.id}:${message.role}:${message.content}`).join('|');
  if (signature === lastPlaygroundLogSignature) return;
  lastPlaygroundLogSignature = signature;
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

function renderPlaygroundImageOutput() {
  const imageOutput = document.querySelector('[data-image-output]');
  if (!imageOutput) return;
  const signature = state.generatedImage || '';
  imageOutput.hidden = !state.generatedImage;
  if (signature === lastPlaygroundImageSignature) return;
  lastPlaygroundImageSignature = signature;
  imageOutput.innerHTML = state.generatedImage
    ? `<img src="${escapeHtml(state.generatedImage)}" alt="生成结果" />`
    : '';
}

function renderSelectedPlaygroundModel() {
  const container = document.querySelector('[data-playground-selected-model]');
  if (!container) return;

  const selected = modelCatalogRows().find((item) => item.model === state.playgroundModel) || fallbackModelRow(state.playgroundModel);
  const summary = modelHealthSummaryFor(selected.model);
  const selectedLabel = publicModelLabel(selected.model);
  const selectedMeta = publicModelMetaLabel(selected.model, selected.family);
  container.innerHTML = `
    <div class="selected-model-panel__main">
      <span class="provider-badge">${escapeHtml(selected.family)}</span>
      <h3 title="${escapeHtml(selected.model)}">${escapeHtml(selectedLabel)}</h3>
      <p title="${escapeHtml(selected.model)}">${escapeHtml(summary.label)} · ${escapeHtml(selectedMeta)}</p>
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
    ['Key', key ? key.name : '未创建'],
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
            <strong title="${escapeHtml(item.model)}">${escapeHtml(publicModelLabel(item.model))}</strong>
            <span>${escapeHtml(item.amount)} · ${escapeHtml(item.calls || '0 次')}</span>
          </article>
        `,
      )
    .join('') || renderEmptyState('无消耗');
  }

  const health = document.querySelector('[data-service-health]');
  if (health) {
    health.innerHTML = (dashboardData.channelChecks || [])
      .map((item) => {
        const summary = summarizeModelHealth(item);
        const history = Array.isArray(item.history) ? item.history.slice(-12) : [];
        return `
          <article class="service-card service-card--${escapeHtml(summary.status)}">
            <div class="service-card__top">
              <span class="health-dot health-dot--${summary.status}" aria-hidden="true"></span>
              <strong>${escapeHtml(item.provider || summary.model)}</strong>
              <small>${escapeHtml(summary.availabilityText)}</small>
            </div>
            <b title="${escapeHtml(summary.model)}">${escapeHtml(publicModelLabel(summary.model))}</b>
            <code>${escapeHtml(item.endpoint || '/v1')}</code>
            <div class="channel-monitor-metrics" data-channel-monitor-metrics>
              <span><em>状态</em>${escapeHtml(item.monitorStatus || item.officialStatus || summary.label)}</span>
              <span><em>可用</em>${escapeHtml(summary.successLabel)}</span>
              <span><em>最低</em>${escapeHtml(summary.latencyText)}</span>
              <span><em>平均</em>${escapeHtml(summary.averageLatencyText)}</span>
            </div>
            <div class="availability-strip" data-channel-monitor-history aria-label="最近 60 点快照">
              ${history.map((status) => `<i class="${monitorHistoryClass(status)}"></i>`).join('')}
            </div>
            <small>${escapeHtml([summary.availabilityWindow, summary.monitorIntervalSeconds ? `${summary.monitorIntervalSeconds} 秒刷新` : '', item.checkedAt ? `最近检测 ${formatCheckedAt(item.checkedAt)}` : '待检测'].filter(Boolean).join(' · '))}</small>
          </article>
        `;
      })
    .join('') || renderEmptyState('未检测');
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
            <strong title="${escapeHtml(item.model)}">${escapeHtml(publicModelLabel(item.model))}</strong>
          </div>
          <p>${escapeHtml(item.tagline)}</p>
          <div class="model-meta">
            <span>${escapeHtml(item.price)}</span>
          </div>
          <div class="model-card-actions">
            <button class="text-action" data-select-playground-model="${escapeHtml(item.model)}" type="button">测试</button>
            <button class="icon-action" data-copy-text="${escapeHtml(item.model)}" type="button" aria-label="复制模型名">⧉</button>
          </div>
        </article>
      `,
    )
    .join('') || renderEmptyState('无结果');
}

function renderSetupGuides() {
  renderGuideTargets();
  const key = activeApiKey();
  setText('[data-guide-key-status]', key ? 'Key 开启' : '创建 Key');

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
    const empty = '# 创建 API Key';
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
  const normalized = normalizeUiModelGroup(group);
  const models = [
    ...(officialModelTemplateByGroup[normalized] || []),
    ...availableModels().filter((model) => modelMatchesUiGroup(model, normalized)),
  ];
  return normalizeClientAvailableModels(models, {
    defaultModel: defaultModelForGroup(normalized),
    modelGroup: normalized,
  });
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
    publicModelLabel(item.model),
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
  const signature = JSON.stringify({
    checks: (dashboardData.channelChecks || []).map((item) => [
      item.provider,
      item.model,
      item.ok,
      item.maintenance,
      item.latencyMs,
      item.checkedAt,
    ]),
    catalog: (dashboardData.modelCatalog || []).map((item) => [
      item.model,
      item.family,
      item.price,
      item.available,
      item.endpointType,
    ]),
  });
  if (catalogCache.signature === signature) {
    return catalogCache.rows;
  }
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
      price: '官方价格待同步',
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
  catalogCache.signature = signature;
  catalogCache.rows = sortModelRows([...rowsByModel.values()]);
  return catalogCache.rows;
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
    tagline: isImageModel(model) ? '图片生成' : '文本 / 代码',
    context: '模型能力',
    price: '官方价格待同步',
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

function publicModelLabel(model) {
  const normalized = normalizeOfficialModelName(model);
  const labels = {
    'claude-opus-4-6-thinking-c': 'Claude Opus 4.6 Thinking',
    'claude-opus-4-6-c': 'Claude Opus 4.6',
    'claude-sonnet-4-5-c': 'Claude Sonnet 4.5',
    'gpt-5.5-c': 'GPT-5.5',
    'gpt-5.4-c': 'GPT-5.4',
  };
  return labels[normalized] || normalized || String(model || '');
}

function publicModelMetaLabel(model, family) {
  const label = publicModelLabel(model);
  if (label !== model) return label;
  const normalized = normalizeOfficialModelName(model);
  if (normalized !== model) return normalized;
  return family || inferUiFamily(model);
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
    : 'conic-gradient(rgba(210,210,215,0.55) 0 100%)';
}

function chartColor(index) {
  return ['#171717', '#16a34a', '#525252', '#a16207', '#dc2626'][index % 5];
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
      state.apiSearch ? '无结果' : '创建 Key',
      '',
    );

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
    return '离线';
  }
  return message || '离线';
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
          <em>${escapeHtml(shortRechargeLabel(option.label || '余额'))}</em>
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
      link.textContent = '购买';
      link.removeAttribute('aria-disabled');
    } else {
      link.href = '#';
      link.textContent = '待配置';
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
    emailInput.value = '';
    emailInput.placeholder = alert.email ? maskEmail(alert.email) : '通知邮箱';
  }
  if (status) {
    status.textContent = alert.enabled === false ? '关闭' : `低于 ${alert.threshold || '$5.00'}`;
    status.classList.toggle('is-off', alert.enabled === false);
  }
  if (last) {
    last.textContent = alert.lastAlertAt ? formatCheckedAt(alert.lastAlertAt) : '未触发';
  }
}

function shortRechargeLabel(label) {
  const text = String(label || '');
  if (/日卡/.test(text)) return '日卡';
  if (/1000/.test(text)) return '$1000';
  if (/500/.test(text)) return '$500';
  if (/100/.test(text)) return '$100';
  if (/30/.test(text)) return '$30';
  return text.replace(/Codex API|额度|不限时|\//g, '').trim() || '余额';
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
      resetImportServerConfig();
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

  if (state.importServerConfig && configMatchesCurrentSelection(state.importServerConfig)) {
    config = state.importServerConfig;
    link = config.ccSwitchUrl || link;
  }

  renderCcSwitchWorkflow(config);
  renderCcSwitchManualEnhancements(config);
  renderExportModelSummary(config);
  renderOpenCodeConfig(config);
  setText('[data-key-inline-status]', state.keyEnabled ? 'Key 已开启' : 'Key 已关闭');
  document.querySelector('[data-import-link]').value = link;
  for (const openImport of document.querySelectorAll('[data-open-import]')) {
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
    title.textContent = 'OpenAI 模型导入 Claude Code';
    copy.textContent = 'Claude + OpenAI，用量查询随导入脚本一起写入。';
    guide.innerHTML = [
      '<li data-claude-guide-step><strong>Developer</strong> → Third-Party Inference。</li>',
      '<li data-claude-guide-step><strong class="danger-text">Base URL 不带 /v1</strong>，认证方式选 bearer。</li>',
      '<li data-claude-guide-step>导入后新会话选择 Frist-API Gateway，再在 CC Switch 卡片测试用量查询。</li>',
    ].join('');
    setActiveWalkthrough('openai-to-claude');
    return;
  }

  if (state.target === 'Codex' && state.modelGroup === 'Claude') {
    title.textContent = 'Claude 模型导入 Codex';
    copy.textContent = 'Codex + Claude';
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
      ? 'DeepSeek 官方入口'
      : 'Responses + MCP';
    guide.innerHTML = [
      '<li data-claude-guide-step>目标客户端选 <strong>Codex</strong>。</li>',
      state.modelGroup === 'DeepSeek'
        ? '<li data-claude-guide-step>模型家族选 <strong>DeepSeek</strong>，默认模型 deepseek-v4-flash。</li>'
        : '<li data-claude-guide-step>确认 auth.json 和 config.toml。</li>',
      '<li data-claude-guide-step>Computer Use 首次调用按系统提示授权。</li>',
    ].join('');
    setActiveWalkthrough('claude-to-codex');
    return;
  }

  title.textContent = '一键导入';
  copy.textContent = '选择后导入。';
  guide.innerHTML = [
    '<li data-claude-guide-step>确认至少有一个开启的 API Key。</li>',
    '<li data-claude-guide-step>选择目标客户端和模型家族。</li>',
    '<li data-claude-guide-step>导入后检查默认模型和模型列表。</li>',
  ].join('');
  setActiveWalkthrough('');
}

function renderCcSwitchUsageGuide() {
  const usageGuide = document.querySelector('.usage-import-guide');
  if (!usageGuide) return;
  const hasServerKey = state.serverAvailable && state.hasServerSession && enabledKeyCount() > 0;
  usageGuide.classList.toggle('is-live', hasServerKey);
  const paragraph = usageGuide.querySelector('p');
  if (paragraph) {
    paragraph.textContent = hasServerKey
      ? '一键导入会写入 CC Switch 用量查询脚本，卡片启用后可刷新 Frist-API 余额、已用额度和调用统计。'
      : '本地预览会展示用量查询步骤；登录并创建 Key 后，一键导入会自动带上可测试的用量查询脚本。';
  }
}

function syncWalkthroughFields() {
  const codexBase = normalizeBaseUrl(state.baseUrl);
  const claudeBase = codexBase.replace(/\/v1\/?$/i, '');
  const openAiModel = availableModelsForGroup('OpenAI')[0] || 'gpt-5.5';
  const claudeModel = availableModelsForGroup('Claude')[0] || 'claude-opus-4-6-thinking-c';
  const claudeAlias = publicModelLabel(claudeModel);
  const deepseekModel = availableModelsForGroup('DeepSeek')[0] || 'deepseek-v4-flash';
  const keyLabel = enabledKeyCount() ? 'fk-live-你的用户Key' : '先创建 Key';
  setText('[data-flow-codex-base]', codexBase);
  setText('[data-flow-claude-base]', claudeBase);
  setText('[data-flow-openai-model]', openAiModel);
  setText('[data-flow-claude-model]', claudeModel);
  setText('[data-flow-claude-alias]', claudeAlias);
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
  if (state.importServerConfig && configMatchesCurrentSelection(state.importServerConfig)) {
    config = state.importServerConfig;
  }

  setText('[data-auth-json]', config.authJson);
  setText('[data-config-toml]', config.configToml);
  renderCcSwitchWorkflow(config);
  renderCcSwitchManualEnhancements(config);
  renderExportModelSummary(config);
  renderOpenCodeConfig(config);
}

function renderExportModelSummary(config) {
  const modelList = normalizeClientAvailableModels(config?.availableModels || availableModelsForGroup(state.modelGroup), {
    defaultModel: config?.defaultModel || defaultModelForGroup(state.modelGroup),
    modelGroup: config?.modelGroup || state.modelGroup,
  });
  const defaultModel = config?.defaultModel || modelList[0] || defaultModelForGroup(state.modelGroup);
  setText('[data-export-default-model]', publicModelLabel(defaultModel));
  setText('[data-export-model-count]', `${modelList.length} 个`);
  const container = document.querySelector('[data-export-models]');
  if (!container) return;
  container.innerHTML = modelList
    .map(
      (model) => `
        <span
          class="export-model-chip ${model === defaultModel ? 'is-default' : ''}"
          data-export-model-chip="${escapeHtml(model)}"
          title="${escapeHtml(model)}"
          role="listitem"
        >
          ${escapeHtml(publicModelLabel(model))}${model === defaultModel ? ' · 默认' : ''}
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

function renderCcSwitchWorkflow(config) {
  const profileName = config?.targetSlug ? clientDisplayName(config.targetSlug) : state.target;
  setText('[data-ccswitch-workflow-target]', profileName);
  setText('[data-ccswitch-workflow-model]', publicModelLabel(config?.modelName || defaultModelForGroup(state.modelGroup)));
  setText('[data-ccswitch-workflow-base]', config?.apiRequestUrl || normalizeBaseUrl(state.baseUrl));
  setText('[data-ccswitch-workflow-usage]', config?.usageBaseUrl || normalizeBaseUrl(state.baseUrl).replace(/\/v1\/?$/i, ''));
  setText('[data-ccswitch-workflow-test]', config?.usageScript ? '导入后点测试脚本' : '登录后自动生成');
}

function renderCcSwitchManualEnhancements(config, setup = state.importServerSetup) {
  const capabilities = config?.ccSwitchCapabilities || { oneClick: [], manual: [] };
  const oneClick = document.querySelector('[data-ccswitch-capability-one-click]');
  const manual = document.querySelector('[data-ccswitch-capability-manual]');
  const checklist = document.querySelector('[data-ccswitch-checklist]');
  const mcpLink = document.querySelector('[data-ccswitch-mcp-link]');
  const usageScript = document.querySelector('[data-usage-script]');
  const testCommand = document.querySelector('[data-test-command]');
  const promptSkillSnippet = document.querySelector('[data-prompt-skill-snippet]');

  if (oneClick) {
    oneClick.innerHTML = renderTagList(capabilities.oneClick, '登录后生成一键导入能力');
  }
  if (manual) {
    manual.innerHTML = renderTagList(capabilities.manual.length ? capabilities.manual : ['当前目标无需额外手动增强'], '无额外增强');
  }
  if (checklist) {
    checklist.innerHTML = (config?.ccSwitchManualChecklist || ['登录并创建 Key 后，点击一键导入。'])
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join('');
  }

  const mcpUrl = config?.ccSwitchMcpUrl || (state.target === 'Codex' ? buildCcSwitchMcpImportUrl() : '');
  if (mcpLink) {
    mcpLink.value = mcpUrl;
  }
  setCopyButtonValue('[data-copy-ccswitch-mcp]', mcpUrl);
  const openMcp = document.querySelector('[data-open-ccswitch-mcp]');
  if (openMcp) {
    openMcp.href = mcpUrl || '#';
    openMcp.toggleAttribute('aria-disabled', !mcpUrl);
  }

  if (usageScript) {
    usageScript.textContent = config?.usageScript || '// 登录并创建 Key 后，这里会显示 CC Switch 自定义用量查询脚本。';
  }
  setCopyButtonValue('[data-copy-usage-script]', config?.usageScript || '');

  const command = setup?.test || (config ? buildClientSetupCommands(config).test : '# 登录并创建 Key 后生成真实连通测试命令。');
  if (testCommand) {
    testCommand.textContent = command;
  }
  setCopyButtonValue('[data-copy-test-command]', command);
  setCopyButtonValue('[data-copy-prompt-skill]', promptSkillSnippet?.textContent || '');
}

function renderTagList(items, emptyLabel) {
  const rows = (items || []).filter(Boolean);
  return rows.length
    ? rows.map((item) => `<span>${escapeHtml(item)}</span>`).join('')
    : `<span>${escapeHtml(emptyLabel)}</span>`;
}

function setCopyButtonValue(selector, value) {
  const button = document.querySelector(selector);
  if (button) {
    button.dataset.copyValue = value || '';
    button.disabled = !value;
  }
}

function configMatchesCurrentSelection(config) {
  if (!config) return false;
  return (
    clientDisplayName(config.targetSlug).toLowerCase() === String(state.target || '').toLowerCase() &&
    normalizeUiModelGroup(config.modelGroup) === normalizeUiModelGroup(state.modelGroup)
  );
}

function resetImportServerConfig() {
  state.importServerConfig = null;
  state.importServerSetup = null;
}

function clientDisplayName(slug) {
  const labels = {
    claude: 'Claude',
    codex: 'Codex',
    gemini: 'Gemini',
    opencode: 'OpenCode',
    openclaw: 'OpenClaw',
    hermes: 'Hermes',
  };
  return labels[String(slug || '').toLowerCase()] || String(slug || state.target || 'Codex');
}

async function refreshImportLinkFromServer() {
  if (!state.serverAvailable || !state.hasServerSession || !enabledKeyCount()) return;
  const requestId = (state.importRequestId += 1);
  try {
    const result = await serverClient.getImportUrl({
      target: state.target,
      model: state.model,
      modelGroup: state.modelGroup,
      keyId: selectedImportKeyId(),
    });
    if (requestId === state.importRequestId) {
      state.importServerConfig = result.config || null;
      state.importServerSetup = result.setup || null;
      document.querySelector('[data-import-link]').value = result.url;
      const liveConfig = result.config || {
        defaultModel: result.defaultModel,
        availableModels: result.availableModels,
        modelGroup: state.modelGroup,
      };
      renderExportModelSummary(liveConfig);
      renderCcSwitchWorkflow(result.config || null);
      renderCcSwitchManualEnhancements(result.config || null, result.setup || null);
      if (result.config) {
        setText('[data-auth-json]', result.config.authJson || '{}\n');
        setText('[data-config-toml]', result.config.configToml || '');
        renderOpenCodeConfig(result.config);
      }
      for (const openImport of document.querySelectorAll('[data-open-import]')) {
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
  for (const button of document.querySelectorAll('[data-copy-link]')) {
    button.addEventListener('click', async (event) => {
      const input = document.querySelector('[data-import-link]');
      await copyText(input.value, event.currentTarget);
    });
  }

  for (const button of document.querySelectorAll('[data-language-toggle]')) {
    button.addEventListener('click', () => {
      state.language = state.language === 'zh' ? 'en' : 'zh';
      document.documentElement.lang = state.language === 'en' ? 'en' : 'zh-CN';
      button.textContent = state.language === 'en' ? 'EN / 中' : '中 / EN';
      button.setAttribute('aria-label', state.language === 'en' ? 'Switch language' : '切换语言');
      signalAction('info');
    });
  }

  for (const button of document.querySelectorAll('[data-copy-value]')) {
    button.addEventListener('click', async () => {
      await copyText(button.dataset.copyValue || '', button);
    });
  }

  window.addEventListener('hashchange', routeFromHash);
  for (const authForm of document.querySelectorAll('[data-auth-form]')) {
    authForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const formKind = authForm.dataset.authFormKind || 'primary';
      if (formKind === 'password') {
        handleChangePassword(authForm.querySelector('[data-change-password]'));
        return;
      }
      if (formKind === 'reset-request') {
        handlePasswordResetRequest(authForm.querySelector('[data-password-reset-request]'));
        return;
      }
      if (formKind === 'reset-confirm') {
        handlePasswordResetConfirm(authForm.querySelector('[data-password-reset-confirm]'));
        return;
      }
      if (formKind === 'owner') {
        handleOwnerClaim(authForm.querySelector('[data-owner-claim]'));
        return;
      }
      const submitButton =
        state.authMode === 'register'
          ? authForm.querySelector('[data-register-account]')
          : authForm.querySelector('[data-login-account]');
      if (state.authMode === 'register') handleRegisterAccount(submitButton);
      else handleLoginAccount(submitButton);
    });
  }

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
      resetImportServerConfig();
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
      resetImportServerConfig();
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
      resetImportServerConfig();
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

    const profileSave = event.target.closest('[data-profile-save]');
    if (profileSave) {
      handleProfileSave(profileSave);
      return;
    }

    const openImport = event.target.closest('[data-open-import]');
    if (openImport) {
      const importUrl = document.querySelector('[data-import-link]').value;
      if (!importUrl) {
        event.preventDefault();
        signalAction('error');
        return;
      }
      openImport.setAttribute('href', importUrl);
      handleImportProtocolFallback(importUrl);
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
      return;
    }

    const openMcpImport = event.target.closest('[data-open-ccswitch-mcp]');
    if (openMcpImport) {
      const mcpUrl = document.querySelector('[data-ccswitch-mcp-link]')?.value || '';
      if (!mcpUrl) {
        event.preventDefault();
        signalAction('error');
        return;
      }
      openMcpImport.setAttribute('href', mcpUrl);
      handleImportProtocolFallback(mcpUrl);
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
      resetImportServerConfig();
      renderPlayground();
    }
  });

  document.addEventListener('input', (event) => {
    const apiSearch = event.target.closest('[data-api-search]');
    if (apiSearch) {
      state.apiSearch = apiSearch.value.trim();
      scheduleRender('api-keys', renderApiKeys);
    }

    const modelSearch = event.target.closest('[data-model-catalog-search]');
    if (modelSearch) {
      state.modelSearch = modelSearch.value.trim();
      scheduleRender('model-catalog', renderModelCatalog);
    }

    const playgroundSearch = event.target.closest('[data-playground-model-search]');
    if (playgroundSearch) {
      state.playgroundModelSearch = playgroundSearch.value.trim();
      scheduleRender('playground', renderPlayground);
    }
  });
}

function scheduleRender(key, renderFn, delay = 120) {
  window.clearTimeout(renderTimers.get(key));
  renderTimers.set(
    key,
    window.setTimeout(() => {
      renderTimers.delete(key);
      renderFn();
    }, delay),
  );
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

function startPlaygroundAutoTest() {
  window.setInterval(() => {
    if (state.view !== 'playground' || state.playgroundBusy || !activeApiKey()) return;
    handlePlaygroundConnectivityTest({ auto: true });
  }, 180_000);
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
      content: '选择模型后测试。',
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
    signalAction('success');
  }
}

function clearPlaygroundMessages() {
  resetPlaygroundMessages();
  renderPlayground();
  signalAction('success');
}

async function handlePlaygroundSend() {
  const promptInput = document.querySelector('[data-playground-prompt]');
  const prompt = promptInput?.value.trim() || '';
  const key = activeApiKey();
  if (!key) {
    signalAction('error');
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
        createPlaygroundMessage('assistant', state.generatedImage ? '已生成' : '成功，无图片'),
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
    await refreshDashboardSilently();
    signalAction('success');
  } catch (error) {
    state.playgroundMessages.push(createPlaygroundMessage('assistant', error.message || '模型不可用'));
    signalAction('error');
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
    signalAction('error');
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
    text: '检测',
  };
  const startedAt = performance.now();
  renderPlayground();

  try {
    let resultText = 'OK';
    if (isImageModel(state.playgroundModel)) {
      const result = await serverClient.generateImage({
        apiKey: key.secret,
        body: buildImageRequestBody(state.playgroundModel, prompt || 'Frist-API 测试'),
      });
      state.generatedImage = firstImageSource(result);
      resultText = state.generatedImage ? '图片已返回' : '成功，无图片';
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
    state.playgroundConnectivity = {
      status: 'success',
      text: `正常 · ${latencyMs}ms · ${formatClockTime(new Date())}`,
    };
    state.playgroundMessages.push(createPlaygroundMessage('assistant', `${state.playgroundModel} · ${latencyMs}ms`));
    await refreshDashboardSilently();
    signalAction('success');
  } catch (error) {
    state.playgroundConnectivity = {
      status: 'error',
      text: `失败 · ${error.message || '模型不可用'}`,
    };
    state.playgroundMessages.push(createPlaygroundMessage('assistant', error.message || '模型不可用'));
    signalAction('error');
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
    await reloadServerDashboard(key.enabled ? 'Key 已关闭' : 'Key 已开启');
  } catch (serverError) {
    signalAction('error');
  }
}

async function renameKey(id) {
  const keyInput = document.querySelector(`[data-key-name="${selectorEscape(id)}"]`);
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key || !keyInput) return;

  const name = keyInput.value.trim();
  if (!name) {
    signalAction('error');
    keyInput.value = key.name;
    return;
  }

  try {
    await serverClient.renameKey(id, { name });
    await reloadServerDashboard('Key 已改名');
  } catch (serverError) {
    signalAction('error');
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
    await reloadServerDashboard('Key 已删除');
  } catch (serverError) {
    signalAction('error');
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
  const normalized = normalizeUiModelGroup(group);
  const models = availableModels().filter((model) => modelMatchesUiGroup(model, group));
  if (models.length > 0) return sortModelsByStrength(models)[0];
  if (normalized === 'Claude') return 'claude-opus-4-6-thinking-c';
  if (normalized === 'Gemini') return 'gemini-2.5-flash';
  if (normalized === 'DeepSeek') return 'deepseek-v4-flash';
  if (normalized === 'Other') return 'deepseek-v4-flash';
  return 'gpt-5.5';
}

function normalizeUiModelGroup(group) {
  const normalized = String(group || 'OpenAI').toLowerCase();
  if (normalized === 'claude') return 'Claude';
  if (normalized === 'gemini') return 'Gemini';
  if (normalized === 'deepseek') return 'DeepSeek';
  if (normalized === 'other') return 'Other';
  return 'OpenAI';
}

function enabledKeyCount() {
  return dashboardData.apiKeys.filter((item) => item.enabled).length;
}

function selectedImportKeyId() {
  const targetGroup = normalizeUiModelGroup(state.modelGroup);
  return dashboardData.apiKeys.find((item) => item.enabled && normalizeUiModelGroup(item.modelGroup) === targetGroup)?.id || '';
}

async function handleCreateKey(createKey) {
  signalScoped('[data-key-feedback]', 'info');
  signalAction('info');
  setButtonBusy(createKey, true, '');
  try {
    const created = await serverClient.createKey({
      name: `Frist Key ${dashboardData.apiKeys.length + 1}`,
      modelGroup: state.modelGroup,
    });
    if (created.key?.id && created.key?.secret) {
      revealedApiKeys.set(created.key.id, created.key.secret);
    }
    await reloadServerDashboard('Key 已创建');
    signalScoped('[data-key-feedback]', 'success');
  } catch (serverError) {
    signalAction('error');
    signalScoped('[data-key-feedback]', 'error');
  } finally {
    setButtonBusy(createKey, false);
  }
}

async function handleRegisterAccount(register) {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  signalAction('info');
  signalScoped('[data-auth-feedback]', 'info');
  setButtonBusy(register, true, '');
  try {
    const payload = await buildAuthPayload({ email, password, requireCaptcha: true });
    await serverClient.register(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '可创建 Key');
    await reloadServerDashboard('注册成功');
    signalScoped('[data-auth-feedback]', 'success');
    toggleAuthPanel(false);
  } catch (serverError) {
    const message = readableErrorMessage(serverError, '注册失败');
    signalAction(message, 'error');
    setScopedFeedback('[data-auth-feedback]', message, 'error');
    await refreshCaptchaAfterAuthError(serverError);
  } finally {
    setButtonBusy(register, false);
  }
}

async function handleLoginAccount(login) {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  signalAction('info');
  signalScoped('[data-auth-feedback]', 'info');
  setButtonBusy(login, true, '');
  try {
    const payload = await buildAuthPayload({ email, password });
    await serverClient.login(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '已登录');
    await reloadServerDashboard('登录成功');
    signalAction('success');
    signalScoped('[data-auth-feedback]', 'success');
    toggleAuthPanel(false);
  } catch (serverError) {
    const message = readableErrorMessage(serverError, '登录失败');
    signalAction(message, 'error');
    setScopedFeedback('[data-auth-feedback]', message, 'error');
    await refreshCaptchaAfterAuthError(serverError);
  } finally {
    setButtonBusy(login, false);
  }
}

async function handleChangePassword(button) {
  const currentPassword = document.querySelector('[data-register-password]').value;
  const newPassword = document.querySelector('[data-new-password]').value;

  setButtonBusy(button, true, '');
  try {
    await serverClient.changePassword({ oldPassword: currentPassword, newPassword });
    document.querySelector('[data-register-password]').value = newPassword;
    document.querySelector('[data-new-password]').value = '';
    await reloadServerDashboard('密码已更新');
  } catch (serverError) {
    signalAction('error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handlePasswordResetRequest(button) {
  const email = document.querySelector('[data-register-email]').value;
  signalScoped('[data-auth-feedback]', 'info');
  setButtonBusy(button, true, '');
  try {
    const result = await serverClient.requestPasswordReset({ email });
    state.passwordResetRequested = true;
    renderAuthPanel();
    setScopedFeedback('[data-auth-feedback]', result.message || '重置验证码已发送', 'success');
  } catch (serverError) {
    setScopedFeedback('[data-auth-feedback]', readableErrorMessage(serverError, '发送失败'), 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handlePasswordResetConfirm(button) {
  const email = document.querySelector('[data-register-email]').value;
  const code = document.querySelector('[data-reset-code]')?.value.trim() || '';
  const newPassword = document.querySelector('[data-reset-password]')?.value || '';
  signalScoped('[data-auth-feedback]', 'info');
  setButtonBusy(button, true, '');
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
    setScopedFeedback('[data-auth-feedback]', '密码已重置，请用新密码登录', 'success');
  } catch (serverError) {
    setScopedFeedback('[data-auth-feedback]', readableErrorMessage(serverError, '重置失败'), 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleOwnerClaim(button) {
  const codeInput = document.querySelector('[data-owner-claim-code]');
  const code = codeInput?.value.trim() || '';
  if (!code) {
    signalAction('error');
    return;
  }

  setButtonBusy(button, true, '');
  try {
    const result = await serverClient.claimAdmin({ code });
    if (codeInput) {
      codeInput.value = '';
    }
    businessState.customer.isAdmin = Boolean(result.user?.isAdmin);
    await reloadServerDashboard(result.message || '管理员身份已激活');
  } catch (serverError) {
    signalAction('error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleVerifyAccount(button) {
  const codeInput = document.querySelector('[data-verify-code]');
  if (!codeInput) return;
  const code = codeInput.value;

  setButtonBusy(button, true, '');
  try {
    await serverClient.verify({ code });
    codeInput.value = '';
    setText('[data-verification-hint]', '邮箱已验证，可以充值并创建 Key。');
    await reloadServerDashboard('邮箱已验证');
  } catch (serverError) {
    signalAction('error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleCopyKey(id, button) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  await copyText(key.secret, button);
}

async function handleProfileSave(button) {
  if (!state.hasServerSession) {
    toggleAuthPanel(true);
    signalScoped('[data-profile-feedback]', 'error');
    return;
  }
  const displayName = document.querySelector('[data-profile-name-input]')?.value.trim() || '';
  const email = document.querySelector('[data-profile-email-input]')?.value.trim() || '';
  const avatarUrl = document.querySelector('[data-profile-avatar-input]')?.value.trim() || '';
  setButtonBusy(button, true, '');
  try {
    await serverClient.updateProfile({ displayName, email, avatarUrl });
    await reloadServerDashboard('资料已保存');
    signalScoped('[data-profile-feedback]', 'success');
  } catch (serverError) {
    signalAction('error');
    signalScoped('[data-profile-feedback]', 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleBalanceAlertSave(button) {
  if (!state.hasServerSession) {
    setActiveView('billing');
    signalScoped('[data-balance-alert-feedback]', 'error');
    return;
  }

  const payload = readBalanceAlertForm();
  signalScoped('[data-balance-alert-feedback]', 'info');
  setButtonBusy(button, true, '');
  try {
    await serverClient.saveBalanceAlert(payload);
    await reloadServerDashboard('预警已保存');
    signalScoped('[data-balance-alert-feedback]', 'success');
  } catch (serverError) {
    signalAction('error');
    signalScoped('[data-balance-alert-feedback]', 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleBalanceAlertTest(button) {
  if (!state.hasServerSession) {
    setActiveView('billing');
    signalScoped('[data-balance-alert-feedback]', 'error');
    return;
  }

  const payload = readBalanceAlertForm();
  signalScoped('[data-balance-alert-feedback]', 'info');
  setButtonBusy(button, true, '');
  try {
    await serverClient.sendBalanceAlertTest(payload);
    await reloadServerDashboard('邮件已发送');
    signalScoped('[data-balance-alert-feedback]', 'success');
  } catch (serverError) {
    signalAction('error');
    signalScoped('[data-balance-alert-feedback]', 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

function readBalanceAlertForm() {
  const enabled = document.querySelector('[data-balance-alert-enabled]')?.checked !== false;
  const thresholdUsd = Number(document.querySelector('[data-balance-alert-threshold]')?.value || 0);
  const email = document.querySelector('[data-balance-alert-email]')?.value.trim() || dashboardData.balanceAlert?.email || dashboardData.accountSummary.email;
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
  setButtonBusy(button, true, '');
  try {
    const result = await serverClient.redeem({ code: input.value || '' });
    input.value = '';
    const message = result.redemption?.credit
      ? `到账 ${result.redemption.credit}`
      : '已到账';
    signalScoped('[data-payment-feedback]', 'success');
    await reloadServerDashboard(message);
  } catch (serverError) {
    signalAction('error');
    signalScoped('[data-payment-feedback]', 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function handleRefreshHealth(event) {
  event?.preventDefault();
  signalAction('info');
  try {
    await reloadServerDashboard('已检测');
    signalAction('success');
  } catch (error) {
    signalAction('error');
  }
}

async function handleRetryDashboard(button) {
  setButtonBusy(button, true, '');
  signalAction('info');
  try {
    await loadDashboardData();
    signalAction(state.serverAvailable ? 'success' : 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

async function reloadServerDashboard(message) {
  const payload = await serverClient.loadDashboard();
  const nextData = normalizeFristDashboard(payload, emptyDashboard);
  applyRevealedApiKeys(nextData);
  state.serverAvailable = true;
  state.hasServerSession = Boolean(payload.authenticated);
  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
  syncPrimaryAccountState();
  render();
  signalAction('success');
}

async function refreshDashboardSilently() {
  try {
    const payload = await serverClient.loadDashboard();
    const nextData = normalizeFristDashboard(payload, emptyDashboard);
    applyRevealedApiKeys(nextData);
    state.serverAvailable = true;
    state.hasServerSession = Boolean(payload.authenticated);
    for (const [key, value] of Object.entries(nextData)) {
      dashboardData[key] = value;
    }
    businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
    syncPrimaryAccountState();
    render();
  } catch {
    state.serverAvailable = false;
  }
}

function applyRevealedApiKeys(nextData) {
  for (const key of nextData.apiKeys || []) {
    if (!key.secret && revealedApiKeys.has(key.id)) {
      key.secret = revealedApiKeys.get(key.id);
    }
  }
}

function activeApiKey() {
  return dashboardData.apiKeys.find((item) => item.enabled && item.secret);
}

function isImageModel(model) {
  return /image|dall|gpt-image/i.test(String(model || ''));
}

// 生图默认走轻量 PNG，避免低带宽验收被慢图拖垮。
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
  return '已返回，无文本';
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

function safeAvatarUrl(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const url = new URL(raw, window.location.origin);
    if (!/^https?:$/i.test(url.protocol)) return '';
    return url.href.replace(/["\\]/g, '');
  } catch {
    return '';
  }
}

function maskEmail(value) {
  const email = String(value || '');
  const [name = '', domain = ''] = email.split('@');
  if (!name || !domain) return email;
  return `${name.slice(0, 2)}***@${domain}`;
}

function setActionMessage(message, type = 'success') {
  for (const element of document.querySelectorAll('[data-action-message]')) {
    const label = message || feedbackLabel(type);
    element.textContent = label;
    element.setAttribute('aria-label', label);
    element.classList.add('is-visible');
    element.classList.toggle('action-message--success', type === 'success');
    element.classList.toggle('action-message--error', type === 'error');
    element.classList.toggle('action-message--info', type === 'info');
  }
}

function setScopedFeedback(selector, message, type = 'info') {
  for (const element of document.querySelectorAll(selector)) {
    element.textContent = message || feedbackLabel(type);
    element.setAttribute('aria-label', message || feedbackLabel(type));
    element.classList.toggle('field-feedback--success', type === 'success');
    element.classList.toggle('field-feedback--error', type === 'error');
    element.classList.toggle('field-feedback--info', type === 'info');
  }
}

function signalAction(type = 'success') {
  setActionMessage(feedbackLabel(type), type);
}

function signalScoped(selector, type = 'success') {
  setScopedFeedback(selector, feedbackLabel(type), type);
}

function readableErrorMessage(error, fallback = '操作失败') {
  const message = String(error?.message || '').trim();
  if (message && !/^请求失败:\s*\d+$/i.test(message)) return message;
  return fallback;
}

function feedbackLabel(type = 'success') {
  if (type === 'error') return '后端暂不可用';
  if (type === 'info') return '处理中';
  return '已连接';
}

function setButtonBusy(button, busy, busyText = '') {
  if (!button) return;
  if (busy) {
    button.dataset.previousText = button.textContent || '';
    button.textContent = busyText;
    button.classList.add('is-busy');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    return;
  }
  button.textContent = button.dataset.previousText || button.textContent;
  button.disabled = false;
  button.classList.remove('is-busy');
  button.removeAttribute('aria-busy');
  delete button.dataset.previousText;
}

async function copyText(text, button) {
  await copyTextToClipboard(text);
  button.classList.add('is-copied');
  button.setAttribute('aria-label', '已复制');
  window.setTimeout(() => button.classList.remove('is-copied'), 900);
}

async function handleImportProtocolFallback(importUrl) {
  await copyTextToClipboard(importUrl);
  const fallback = document.querySelector('[data-import-fallback]');
  if (!fallback) return;
  fallback.hidden = false;
  window.clearTimeout(state.importFallbackTimer);
  state.importFallbackTimer = window.setTimeout(() => {
    fallback.hidden = true;
  }, 3200);
}

async function copyTextToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return;
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
}

function setText(selector, value) {
  for (const element of document.querySelectorAll(selector)) {
    element.textContent = value;
  }
}

bindStaticActions();
render();
startCarouselTimer();
startPlaygroundAutoTest();
loadDashboardData().catch(() => {
  state.dashboardLoading = false;
  render();
});

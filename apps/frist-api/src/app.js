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
    balance: '¥0.00',
    todayCost: '¥0.00',
    monthCost: '¥0.00',
    quotaLeft: '¥0.00',
    packageQuota: '¥0.00',
    boosterQuota: '¥0.00',
    usageTotal: '¥0.00',
    todayCalls: '0 次',
    email: '',
    isAdmin: false,
  },
  apiKeys: [],
  channelChecks: [],
  helpLinks: [],
  importTargets: ['Claude', 'Codex', 'OpenCode', 'OpenClaw', 'Hermes'],
  modelUsage: [],
  modelCatalog: [],
  rechargeOptions: [],
};

const dashboardData = structuredClone(emptyDashboard);
let businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });

const serverClient = createFristApiBrowserClient({
  baseUrl: window.FRIST_API_SERVER_BASE_URL || window.location.origin,
});

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
    desc: '充值单和兑换码。',
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
      content: '选择模型后可以直接测试。图片模型会生成图片，其它模型会返回文字。',
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
  renderAccountSummary();
  renderAuthPanel();
  renderDashboard();
  renderUsage();
  renderChannelHealth();
  renderPlayground();
  renderAnalytics();
  renderModelCatalog();
  renderApiKeys();
  renderModelGroupPicker();
  renderRechargeOptions();
  renderImportTargets();
  renderImportFamilyPicker();
  renderImportLink();
  renderClientConfig();
  renderSetupGuides();
  renderHelpLinks();
  routeFromHash();
}

async function loadDashboardData() {
  let nextData = normalizeFristDashboard(emptyServerPayload(), emptyDashboard);
  try {
    const serverDashboard = await serverClient.loadDashboard();
    nextData = normalizeFristDashboard(serverDashboard, emptyDashboard);
    state.serverAvailable = true;
    state.hasServerSession = Boolean(serverDashboard.authenticated);
  } catch (error) {
    state.serverAvailable = false;
    state.hasServerSession = false;
    setActionMessage(error.message || '服务暂时不可用，请先启动后端');
  }

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
    rechargeOptions: [],
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
    captchaRow.hidden = !state.captcha.question;
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
  setText('[data-api-summary]', state.keyEnabled ? `${enabledKeyCount()} 个 Key 已开启` : 'Key 已关闭');
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
          <div class="usage-track" aria-label="${item.model} 消耗占比 ${item.percent}%">
            <i style="width: ${item.percent}%"></i>
          </div>
          <b>${item.amount}</b>
        </article>
      `,
    )
    .join('');

  if (compact) compact.innerHTML = renderRows(modelUsage.slice(0, 2), { compact: true });
}

function renderChannelHealth() {
  const { channelChecks } = dashboardData;
  const compact = document.querySelector('[data-channel-compact]');
  const providerItems = providerSummaries(channelChecks);
  const compactItems = providerItems.map(renderProviderSummary).join('');

  if (compact) compact.innerHTML = compactItems;
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

function renderAnalytics() {
  const usageRows = dashboardData.modelUsage || [];
  const donut = document.querySelector('[data-usage-donut]');
  if (donut) {
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
      .join('');
  }

  const health = document.querySelector('[data-service-health]');
  if (health) {
    health.innerHTML = (dashboardData.channelChecks || [])
      .map((item) => {
        const summary = summarizeModelHealth(item);
        return `
          <article class="service-card">
            <span class="health-dot health-dot--${summary.status}" aria-hidden="true"></span>
            <strong>${escapeHtml(item.provider || summary.model)}</strong>
            <b>${escapeHtml(summary.model)}</b>
            <small>${escapeHtml(summary.label)} · ${escapeHtml(summary.latencyText)}</small>
          </article>
        `;
      })
      .join('');
  }
}

function renderModelCatalog() {
  const catalog = modelCatalogRows();
  setText('[data-model-count]', `${catalog.filter((item) => item.available).length} 个可用`);
  const container = document.querySelector('[data-model-catalog]');
  if (!container) return;

  container.innerHTML = catalog
    .map(
      (item) => `
        <article class="model-card ${item.available ? 'is-available' : ''}">
          <div>
            <span class="provider-badge">${escapeHtml(item.family)}</span>
            <strong>${escapeHtml(item.model)}</strong>
          </div>
          <p>${escapeHtml(item.tagline)}</p>
          <div class="model-meta">
            <span>${escapeHtml(item.context)}</span>
            <span>${escapeHtml(item.price)}</span>
          </div>
        </article>
      `,
    )
    .join('');
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
  const unique = [...new Set([...liveModels, ...catalogModels])];
  return sortModelsByStrength(unique.length ? unique : ['gpt-5.5']);
}

function availableModelsForGroup(group) {
  const models = availableModels().filter((model) => modelMatchesUiGroup(model, group));
  return models.length ? models : [defaultModelForGroup(group)];
}

function modelMatchesUiGroup(model, group) {
  const normalized = String(group || 'All').toLowerCase();
  const value = String(model || '').toLowerCase();
  if (normalized === 'all') return true;
  if (normalized === 'openai') return /gpt|dall|image/.test(value);
  if (normalized === 'claude') return /claude|anthropic/.test(value);
  if (normalized === 'other') return !/gpt|dall|image|claude|anthropic/.test(value);
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
    available: statusByModel.has(normalizeOfficialModelName(item.model)) ? Boolean(statusByModel.get(normalizeOfficialModelName(item.model)).ok) : Boolean(item.available),
  }));
  const catalogModels = new Set(catalog.map((item) => item.model));
  const liveAdditions = (dashboardData.channelChecks || [])
    .filter((item) => item.model && !catalogModels.has(item.model))
    .map((item) => ({
      model: item.model,
      family: item.provider || 'Other',
      tagline: '当前可用',
      context: '按模型能力',
      price: '按后台价格',
      available: Boolean(item.ok),
    }));
  return [...catalog, ...liveAdditions];
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
    ? `conic-gradient(${segments.join(', ')}, rgba(18,30,25,0.08) ${Math.min(cursor, 100)}% 100%)`
    : 'conic-gradient(rgba(18,30,25,0.08) 0 100%)';
}

function chartColor(index) {
  return ['#07875f', '#175edb', '#c6262e', '#ba6f0c', '#6f54d9'][index % 5];
}

function renderApiKeys() {
  const { accountSummary, apiKeys } = dashboardData;
  const summary = document.querySelector('[data-key-summary]');
  const list = document.querySelector('[data-api-keys]');
  const activeCount = enabledKeyCount();

  if (summary) {
    summary.innerHTML = `
    <article><span>秘钥总数</span><strong>${apiKeys.length}</strong></article>
    <article><span>活跃秘钥</span><strong>${activeCount}</strong></article>
    <article><span>今日调用</span><strong>${accountSummary.todayCalls}</strong></article>
    <article><span>本月费用</span><strong>${accountSummary.monthCost}</strong></article>
  `;
  }

  list.innerHTML = apiKeys
    .map(
      (key) => `
        <article class="key-row">
          <div class="key-name-field">
            <input
              type="text"
              data-key-name="${key.id}"
              value="${escapeHtml(key.name)}"
              aria-label="API Key 名称"
            />
            <span>${key.preview}</span>
          </div>
          <span class="key-state ${key.enabled ? 'is-on' : ''}" data-key-status>
            ${key.enabled ? '已开启' : '已关闭'}
          </span>
          <div class="key-stats">
            <span>${key.cost}</span>
            <small>${key.tokens}</small>
          </div>
          <div class="key-actions">
            <button class="ghost-action" data-copy-key-id="${key.id}" type="button">复制</button>
            <button class="secondary-action" data-rename-key="${key.id}" type="button">改名</button>
            <button class="danger-action" data-delete-key="${key.id}" type="button">删除</button>
            <button class="secondary-action" data-toggle-key="${key.id}" type="button">${key.enabled ? '关闭' : '开启'}</button>
          </div>
        </article>
      `,
    )
    .join('');

  bindCopyButtons(list);
}

function renderModelGroupPicker() {
  for (const button of document.querySelectorAll('[data-model-group-option]')) {
    button.classList.toggle('is-active', button.dataset.modelGroupOption === state.modelGroup);
  }
}

function renderRechargeOptions() {
  const { rechargeOptions } = dashboardData;
  const container = document.querySelector('[data-recharge-options]');
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
          <em>${option.label || '余额'}</em>
          <strong>${option.cny}</strong>
          ${option.quotaUsd ? `<span>${escapeHtml(option.quota || `$${option.quotaUsd}`)} 额度</span>` : ''}
        </button>
      `,
    )
    .join('');
}

function renderImportTargets() {
  const { importTargets } = dashboardData;
  const container = document.querySelector('[data-import-targets]');
  container.innerHTML = importTargets
    .map(
      (target) => `
        <button class="target-button ${state.target === target ? 'is-active' : ''}" data-target="${target}" type="button">
          ${target}
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
  setText('[data-pay-submit]', '提交');
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
    copy.textContent = '选择 Claude + ChatGPT / OpenAI 后，Frist-API 会用 Anthropic Messages 入口接住 Claude Code，再把请求路由到可用的 ChatGPT 模型。';
    guide.innerHTML = [
      '<li data-claude-guide-step>打开 CC Switch 的 Claude 配置页。</li>',
      '<li data-claude-guide-step>开启开发者模式，允许第三方 API。</li>',
      '<li data-claude-guide-step>点击一键导入，确认 Frist-API 供应商和模型。</li>',
    ].join('');
    setActiveWalkthrough('openai-to-claude');
    return;
  }

  if (state.target === 'Codex' && state.modelGroup === 'Claude') {
    title.textContent = 'Claude 模型导入 Codex';
    copy.textContent = '选择 Codex + Claude 后，Frist-API 会先尝试 Responses，必要时自动降级为 Chat Completions，把 Claude 模型继续喂给 Codex，并写入推荐 MCP 开发工具。';
    guide.innerHTML = [
      '<li data-claude-guide-step>在 CC Switch 里切到 Codex 配置页。</li>',
      '<li data-claude-guide-step>确认模型家族是 Claude，并保持 Frist-API 供应商。</li>',
      '<li data-claude-guide-step>点击一键导入，检查默认模型是否是 Claude 模型。</li>',
      '<li data-claude-guide-step>config.toml 会默认带上 Playwright、Superpowers 和 open-computer-use MCP。</li>',
    ].join('');
    setActiveWalkthrough('claude-to-codex');
    return;
  }

  if (state.target === 'Codex') {
    title.textContent = 'Codex 最强开发配置';
    copy.textContent = 'Codex 导入默认启用 Responses、1M 上下文、xhigh 推理、工具搜索、Playwright、Superpowers 和 open-computer-use MCP。';
    guide.innerHTML = [
      '<li data-claude-guide-step>在 CC Switch 里切到 Codex 配置页。</li>',
      '<li data-claude-guide-step>点击一键导入，写入 Frist-API 供应商、最强默认模型和 MCP 配置。</li>',
      '<li data-claude-guide-step>首次使用 Computer Use 时，按 Codex 提示完成系统权限授权。</li>',
    ].join('');
    setActiveWalkthrough('claude-to-codex');
    return;
  }

  title.textContent = '一键导入';
  copy.textContent = '按目标客户端选择导入链接，Frist-API 会自动带上你可用的模型和配置。';
  guide.innerHTML = [
    '<li data-claude-guide-step>选择目标客户端。</li>',
    '<li data-claude-guide-step>确认模型分组。</li>',
    '<li data-claude-guide-step>点击一键导入。</li>',
  ].join('');
  setActiveWalkthrough('');
}

function syncWalkthroughFields() {
  const codexBase = normalizeBaseUrl(state.baseUrl);
  const claudeBase = codexBase.replace(/\/v1\/?$/i, '');
  const openAiModel = availableModelsForGroup('OpenAI')[0] || 'gpt-5.5';
  const claudeModel = availableModelsForGroup('Claude')[0] || 'claude-opus-4-6-thinking-c';
  const keyLabel = enabledKeyCount() ? 'fk-live-你的用户Key' : '先在 API 页面创建 fk-live 用户 Key';
  setText('[data-flow-codex-base]', codexBase);
  setText('[data-flow-claude-base]', claudeBase);
  setText('[data-flow-openai-model]', openAiModel);
  setText('[data-flow-claude-model]', claudeModel);
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

    const pay = event.target.closest('[data-pay-submit]');
    if (pay) {
      handleRecharge(pay);
      return;
    }

    const redeem = event.target.closest('[data-redeem-code]');
    if (redeem) {
      handleRedeemCode(redeem);
      return;
    }

    const refresh = event.target.closest('[data-refresh-health]');
    if (refresh) {
      handleRefreshHealth(event);
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
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      toggleAuthPanel(false);
    }
  });

  document.addEventListener('change', (event) => {
    const playgroundModel = event.target.closest('[data-playground-model]');
    if (playgroundModel) {
      state.playgroundModel = playgroundModel.value || state.playgroundModel;
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
    prepareCaptchaChallenge();
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

async function buildAuthPayload({ email, password }) {
  await prepareCaptchaChallenge();
  const payload = { email, password };
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
  if (!/验证码|验证|captcha|challenge/i.test(error.message || '')) {
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
    item.classList.toggle('is-active', item.dataset.route === view);
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
      content: '选择模型后可以直接测试。图片模型会生成图片，其它模型会返回文字。',
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
        body: {
          model: state.playgroundModel,
          prompt,
          size: '1024x1024',
        },
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
        body: {
          model: state.playgroundModel,
          prompt: prompt || 'Frist-API 连通性测试',
          size: '1024x1024',
        },
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
  if (normalized === 'other') return 'gemini-2.5-flash';
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
    const payload = await buildAuthPayload({ email, password });
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

async function handleRecharge(button) {
  setActionMessage('充值订单提交中...', 'info');
  setButtonBusy(button, true, '提交中');
  try {
    const result = await serverClient.recharge({
      planId: state.selectedRechargePlanId,
      amountCny: state.selectedRechargeCny,
      plan: state.selectedRechargePlan,
      method: 'web_checkout',
    });
    const label = rechargeLabel(state.selectedRechargePlan);
    const message =
      result.paymentOrder?.status === 'pending_manual_payment'
        ? `${label}订单已提交`
        : `${label}已入账`;
    await reloadServerDashboard(message);
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
  } finally {
    setButtonBusy(button, false);
  }
}

function rechargeLabel(plan) {
  if (plan === 'day') return '日卡';
  if (plan === 'month') return '月卡';
  return '余额';
}

async function handleRedeemCode(button) {
  const input = document.querySelector('[data-exchange-code]');
  setButtonBusy(button, true, '兑换中');
  try {
    await serverClient.redeem({ code: input.value || '' });
    input.value = '';
    await reloadServerDashboard('兑换码已生效');
  } catch (serverError) {
    setActionMessage(serverError.message, 'error');
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
  render();
});

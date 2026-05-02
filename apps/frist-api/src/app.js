import {
  buildClientSetupCommands,
  normalizeBaseUrl,
  summarizeModelHealth,
} from './core.js';
import {
  applyRecharge,
  buildBusinessClientConfig,
  buildBusinessImportUrl,
  createBusinessStateFromDashboard,
  createCustomerKey,
  deleteCustomerKey,
  deriveDashboardData,
  redeemCode,
  registerCustomer,
  renameCustomerKey,
  setCustomerKeyEnabled,
  verifyCustomerEmail,
} from './businessFlow.js';
import * as fallbackData from './data.js';
import { createFristApiDataStore, createNewApiClient } from './newApiClient.js';
import { createFristApiBrowserClient, normalizeFristDashboard } from './serverClient.js';

const fallbackDashboard = {
  accountSummary: fallbackData.accountSummary,
  apiKeys: fallbackData.apiKeys,
  channelChecks: fallbackData.channelChecks,
  helpLinks: fallbackData.helpLinks,
  importTargets: fallbackData.importTargets,
  modelUsage: fallbackData.modelUsage,
  modelCatalog: fallbackData.modelCatalog,
  rechargeOptions: fallbackData.rechargeOptions,
};

const dashboardData = { ...fallbackDashboard };
let businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });

const store = createFristApiDataStore({
  fallback: dashboardData,
  client: createNewApiClient({
    baseUrl: window.FRIST_API_BASE_URL || window.location.origin,
  }),
  config: {
    planNames: {
      default: '默认套餐',
      monthly_pro: '月卡 Pro',
      day: '日卡',
      month: '月卡',
    },
  },
});

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
  selectedRechargeCny: 3.87,
  selectedRechargePlan: 'day',
  serverAvailable: false,
  hasServerSession: false,
  importRequestId: 0,
  playgroundBusy: false,
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
  let nextData;
  try {
    const serverDashboard = await serverClient.loadDashboard();
    nextData = normalizeFristDashboard(serverDashboard, fallbackDashboard);
    state.serverAvailable = true;
    state.hasServerSession = Boolean(serverDashboard.authenticated);
  } catch (error) {
    state.serverAvailable = error.status === 401;
    state.hasServerSession = false;
    nextData = error.status === 401 ? createGuestDashboard(fallbackDashboard) : await store.load();
  }

  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
  syncPrimaryAccountState();
  render();
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
      <strong>${item.provider}</strong>
      <small>${item.okText} · ${item.latencyText}</small>
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
    };
    current.total += 1;
    current.healthy += snapshot.ok && !snapshot.maintenance ? 1 : 0;
    if (snapshot.ok) {
      current.bestLatency = current.bestLatency
        ? Math.min(current.bestLatency, Number(snapshot.latencyMs || 0))
        : Number(snapshot.latencyMs || 0);
    }
    current.models.push(snapshot.model);
    current.status = current.healthy > 0 ? summary.status : 'down';
    grouped.set(snapshot.provider, current);
  }

  return [...grouped.values()].map((item) => ({
    provider: item.provider,
    status: item.healthy > 0 ? (item.bestLatency > 1600 ? 'slow' : 'healthy') : 'down',
    okText: item.healthy > 0 ? `${item.healthy}/${item.total}` : '不可用',
    latencyText: item.bestLatency ? `${item.bestLatency}ms` : '-',
    models: [...new Set(item.models)].slice(0, 4),
  }));
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
    'gpt-5.5',
    'gpt-5.4-pro',
    'gpt-5.4',
    'gpt-5.4-mini',
    'gpt-5.4-nano',
    'gpt-image-2',
    'gpt-image-1.5',
    'gpt-image-1',
    'claude-haiku-4-5-20251001',
    'claude-haiku',
    'gemini-2.5-flash',
  ];
  return [...new Set((models || []).map((model) => String(model || '').trim()).filter(Boolean))].sort((left, right) => {
    const leftRank = order.indexOf(left);
    const rightRank = order.indexOf(right);
    const normalizedLeft = leftRank === -1 ? Number.MAX_SAFE_INTEGER : leftRank;
    const normalizedRight = rightRank === -1 ? Number.MAX_SAFE_INTEGER : rightRank;
    if (normalizedLeft !== normalizedRight) return normalizedLeft - normalizedRight;
    return left.localeCompare(right);
  });
}

function modelCatalogRows() {
  const statusByModel = new Map((dashboardData.channelChecks || []).map((item) => [item.model, item]));
  const catalog = (dashboardData.modelCatalog || []).map((item) => ({
    ...item,
    available: statusByModel.has(item.model) ? Boolean(statusByModel.get(item.model).ok) : Boolean(item.available),
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
  container.innerHTML = rechargeOptions
    .map(
      (option) => `
        <button class="amount-button ${option.active ? 'is-active' : ''}" data-recharge-plan="${option.plan || 'balance'}" data-recharge-option="${Number(
          String(option.cny).replace(/[^\d.]/g, ''),
        )}" type="button">
          <em>${option.label || '余额'}</em>
          <strong>${option.cny}</strong>
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
  setText('[data-key-inline-status]', state.keyEnabled ? 'Key 已开启' : 'Key 已关闭');
  document.querySelector('[data-import-link]').value = link;
  const openImport = document.querySelector('[data-open-import]');
  if (openImport) {
    openImport.setAttribute('href', link || '#');
    openImport.toggleAttribute('aria-disabled', !link);
  }
  setText('[data-base-url]', normalizeBaseUrl(state.baseUrl));
  setText('[data-pay-demo]', '提交');
  renderCrossImportGuide();
  refreshImportLinkFromServer();
}

function renderCrossImportGuide() {
  const title = document.querySelector('[data-cross-import-title]');
  const copy = document.querySelector('[data-cross-import-copy]');
  const guide = document.querySelector('[data-claude-developer-guide]');
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
    return;
  }

  title.textContent = '一键导入';
  copy.textContent = '按目标客户端选择导入链接，Frist-API 会自动带上你可用的模型和配置。';
  guide.innerHTML = [
    '<li data-claude-guide-step>选择目标客户端。</li>',
    '<li data-claude-guide-step>确认模型分组。</li>',
    '<li data-claude-guide-step>点击一键导入。</li>',
  ].join('');
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
      state.selectedRechargeCny = Number(amount.dataset.rechargeOption);
      state.selectedRechargePlan = amount.dataset.rechargePlan || 'balance';
      for (const item of dashboardData.rechargeOptions) {
        item.active = Number(String(item.cny).replace(/[^\d.]/g, '')) === state.selectedRechargeCny;
      }
      renderRechargeOptions();
      renderImportLink();
      return;
    }

    const createKey = event.target.closest('[data-create-key]');
    if (createKey) {
      handleCreateKey();
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
      handleRegisterAccount();
      return;
    }

    const login = event.target.closest('[data-login-account]');
    if (login) {
      handleLoginAccount();
      return;
    }

    const changePassword = event.target.closest('[data-change-password]');
    if (changePassword) {
      handleChangePassword();
      return;
    }

    const ownerClaim = event.target.closest('[data-owner-claim]');
    if (ownerClaim) {
      handleOwnerClaim();
      return;
    }

    const verify = event.target.closest('[data-verify-account]');
    if (verify) {
      handleVerifyAccount();
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

    const pay = event.target.closest('[data-pay-demo]');
    if (pay) {
      handleRecharge();
      return;
    }

    const redeem = event.target.closest('[data-redeem-code]');
    if (redeem) {
      handleRedeemCode();
      return;
    }

    const refresh = event.target.closest('[data-refresh-health]');
    if (refresh) {
      handleRefreshHealth();
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
      id: challenge.id || '',
      question: challenge.question || '',
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

async function toggleKey(id) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  try {
    await serverClient.setKeyEnabled(id, { enabled: !key.enabled });
    await reloadServerDashboard(key.enabled ? 'API Key 已关闭' : 'API Key 已开启');
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
    state.serverAvailable = false;
  }

  businessState = setCustomerKeyEnabled(businessState, { id, enabled: !key.enabled });
  applyBusinessState(key.enabled ? 'API Key 已关闭' : 'API Key 已开启');
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
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
    state.serverAvailable = false;
  }

  businessState = renameCustomerKey(businessState, { id, name });
  applyBusinessState('API Key 已改名');
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
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
    state.serverAvailable = false;
  }

  businessState = deleteCustomerKey(businessState, { id });
  applyBusinessState('API Key 已删除');
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
  if (normalized === 'claude') return 'claude-haiku';
  if (normalized === 'other') return 'gemini-2.5-flash';
  return 'gpt-5.5';
}

function enabledKeyCount() {
  return dashboardData.apiKeys.filter((item) => item.enabled).length;
}

async function handleCreateKey() {
  try {
    await serverClient.createKey({
      name: `Frist Key ${dashboardData.apiKeys.length + 1}`,
      modelGroup: state.modelGroup,
    });
    await reloadServerDashboard('API Key 已创建，可直接导入 CC Switch');
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
  }

  try {
    const result = createCustomerKey(businessState, {
      name: `Frist Key ${businessState.apiKeys.length + 1}`,
      modelGroup: state.modelGroup,
    });
    businessState = result.state;
    applyBusinessState('API Key 已创建，可直接导入 CC Switch');
  } catch (error) {
    setActionMessage(error.message);
  }
}

async function handleRegisterAccount() {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  try {
    const payload = await buildAuthPayload({ email, password });
    const result = await serverClient.register(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '注册成功，可以创建 Key。');
    await reloadServerDashboard('注册成功，可以创建 Key');
    toggleAuthPanel(false);
    return;
  } catch (serverError) {
    if (serverError.localValidation) {
      setActionMessage(serverError.message);
      return;
    }
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      await refreshCaptchaAfterAuthError(serverError);
      return;
    }
    state.serverAvailable = false;
  }

  try {
    const result = registerCustomer(businessState, { email, password });
    businessState = {
      ...result.state,
      customer: {
        ...result.state.customer,
        emailVerified: true,
        verificationCode: '',
      },
    };
    setText('[data-verification-hint]', '注册成功，可以创建 Key。');
    applyBusinessState('注册成功，可以创建 Key');
    toggleAuthPanel(false);
  } catch (error) {
    setActionMessage(error.message);
  }
}

async function handleLoginAccount() {
  const email = document.querySelector('[data-register-email]').value;
  const password = document.querySelector('[data-register-password]').value;

  try {
    const payload = await buildAuthPayload({ email, password });
    await serverClient.login(payload);
    state.serverAvailable = true;
    state.hasServerSession = true;
    setText('[data-verification-hint]', '登录成功，可以继续充值、创建 Key 或导入 CC Switch。');
    await reloadServerDashboard('登录成功');
    toggleAuthPanel(false);
  } catch (serverError) {
    if (serverError.localValidation) {
      setActionMessage(serverError.message);
      return;
    }
    setActionMessage(serverError.message);
    await refreshCaptchaAfterAuthError(serverError);
  }
}

async function handleChangePassword() {
  const currentPassword = document.querySelector('[data-register-password]').value;
  const newPassword = document.querySelector('[data-new-password]').value;

  try {
    await serverClient.changePassword({ oldPassword: currentPassword, newPassword });
    document.querySelector('[data-register-password]').value = newPassword;
    document.querySelector('[data-new-password]').value = '';
    await reloadServerDashboard('密码已更新');
  } catch (serverError) {
    setActionMessage(serverError.message);
  }
}

async function handleOwnerClaim() {
  const codeInput = document.querySelector('[data-owner-claim-code]');
  const code = codeInput?.value.trim() || '';
  if (!code) {
    setActionMessage('请填写一次性身份码');
    return;
  }

  try {
    const result = await serverClient.claimAdmin({ code });
    if (codeInput) {
      codeInput.value = '';
    }
    businessState.customer.isAdmin = Boolean(result.user?.isAdmin);
    await reloadServerDashboard(result.message || '管理员身份已激活');
  } catch (serverError) {
    setActionMessage(serverError.message);
  }
}

async function handleVerifyAccount() {
  const codeInput = document.querySelector('[data-verify-code]');
  if (!codeInput) return;
  const code = codeInput.value;

  try {
    await serverClient.verify({ code });
    codeInput.value = '';
    setText('[data-verification-hint]', '邮箱已验证，可以充值并创建 Key。');
    await reloadServerDashboard('邮箱已验证');
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
  }

  try {
    businessState = verifyCustomerEmail(businessState, { code });
    codeInput.value = '';
    setText('[data-verification-hint]', '邮箱已验证，可以充值并创建 Key。');
    applyBusinessState('邮箱已验证');
  } catch (error) {
    setActionMessage(error.message);
  }
}

async function handleCopyKey(id, button) {
  const key = businessState.apiKeys.find((item) => item.id === id);
  if (!key) return;
  await copyText(key.secret, button);
}

async function handleRecharge() {
  try {
    const result = await serverClient.recharge({
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
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
    state.serverAvailable = false;
  }

  businessState = applyRecharge(businessState, {
    amountCny: state.selectedRechargeCny,
    method: 'demo_checkout',
  });
  applyBusinessState(`${rechargeLabel(state.selectedRechargePlan)}已入账`);
}

function rechargeLabel(plan) {
  if (plan === 'day') return '日卡';
  if (plan === 'month') return '月卡';
  return '余额';
}

async function handleRedeemCode() {
  const input = document.querySelector('[data-exchange-code]');
  try {
    await serverClient.redeem({ code: input.value || 'FRIST-DAY-001' });
    input.value = '';
    await reloadServerDashboard('兑换码已生效');
    return;
  } catch (serverError) {
    if (state.serverAvailable) {
      setActionMessage(serverError.message);
      return;
    }
  }

  try {
    businessState = redeemCode(businessState, { code: input.value || 'FRIST-DAY-001' });
    input.value = '';
    applyBusinessState('兑换码已生效');
  } catch (error) {
    setActionMessage(error.message);
  }
}

async function handleRefreshHealth() {
  if (state.serverAvailable) {
    try {
      await reloadServerDashboard('连通性已刷新');
      return;
    } catch (error) {
      setActionMessage(error.message || '刷新失败');
      return;
    }
  }

  const checkedAt = new Date().toISOString().slice(11, 16);
  businessState.channelChecks = businessState.channelChecks.map((item, index) => ({
    ...item,
    ok: true,
    latencyMs: Math.max(280, Number(item.latencyMs || 900) - (index + 1) * 37),
    pingMs: Math.max(35, Number(item.pingMs || 90) - index * 4),
    checkedAt,
    officialStatus: '正常',
    history: ['ok', ...(item.history || [])].slice(0, 12),
  }));
  applyBusinessState('连通性已刷新');
}

function applyBusinessState(message) {
  const nextData = deriveDashboardData(businessState, fallbackDashboard);
  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  syncPrimaryAccountState();
  render();
  setActionMessage(message);
}

async function reloadServerDashboard(message) {
  const nextData = normalizeFristDashboard(await serverClient.loadDashboard(), fallbackDashboard);
  state.serverAvailable = true;
  state.hasServerSession = true;
  for (const [key, value] of Object.entries(nextData)) {
    dashboardData[key] = value;
  }
  businessState = createBusinessStateFromDashboard(dashboardData, { now: new Date().toISOString() });
  syncPrimaryAccountState();
  render();
  setActionMessage(message);
}

function createGuestDashboard(fallback) {
  return {
    ...fallback,
    accountSummary: {
      ...fallback.accountSummary,
      userInitials: 'FA',
      plan: '未登录',
      balance: '¥0.00',
      quotaLeft: '¥0.00',
      packageQuota: '¥0.00',
      boosterQuota: '¥0.00',
      todayCost: '¥0.00',
      monthCost: '¥0.00',
      usageTotal: '¥0.00',
      todayCalls: '0 次',
    },
    apiKeys: [],
    modelUsage: zeroModelUsage(fallback.modelUsage),
  };
}

function zeroModelUsage(modelUsage) {
  return (modelUsage || []).map((item) => ({
    ...item,
    percent: 0,
    amount: '¥0.00',
    calls: '0 次',
    tokens: '0.00M',
  }));
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

function setActionMessage(message) {
  setText('[data-action-message]', message);
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

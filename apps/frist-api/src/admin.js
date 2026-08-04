const state = {
  adminToken: '',
  rechargePlans: [],
  lastCardExport: '',
  plusAccounts: [],
  editingPlusAccountId: '',
  rtAccounts: [],
  upstreamChannels: [],
  xianyuFulfillments: [],
};

function captureAdminToken() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
}

function init() {
  document.querySelector('[data-admin-token]').value = state.adminToken;
  document.querySelector('[data-admin-save-token]').addEventListener('click', saveToken);
  document.querySelector('[data-admin-2fa-verify]').addEventListener('click', verifyAdmin2fa);
  document.querySelector('[data-admin-readiness-refresh]').addEventListener('click', loadProductionReadiness);
  document.querySelector('[data-admin-credit]').addEventListener('click', creditCustomer);
  document.querySelector('[data-admin-password-reset]').addEventListener('click', resetCustomerPassword);
  document.querySelector('[data-admin-parse-order]').addEventListener('click', parseOrder);
  document.querySelector('[data-admin-replenish]').addEventListener('click', replenish);
  document.querySelector('[data-admin-refresh]').addEventListener('click', loadInventory);
  document.querySelector('[data-admin-pricing-save]').addEventListener('click', savePricing);
  document.querySelector('[data-admin-card-create]').addEventListener('click', createRedemptionCards);
  document.querySelector('[data-admin-card-copy]').addEventListener('click', copyLatestCardExport);
  document.querySelector('[data-admin-copy-listing-template]')?.addEventListener('click', copyListingTemplate);
  document.querySelector('[data-admin-upstream-sync-run]')?.addEventListener('click', syncUpstreamChannels);
  document.querySelector('[data-admin-xianyu-create]')?.addEventListener('click', createXianyuFulfillment);
  document.querySelector('[data-admin-xianyu-copy]')?.addEventListener('click', copyXianyuDeliveryMessage);
  document.querySelector('[data-admin-plus-save]').addEventListener('click', savePlusAccount);
  document.querySelector('[data-admin-plus-clear]').addEventListener('click', clearPlusAccountForm);
  document.querySelector('[data-admin-plus-list]').addEventListener('click', handlePlusAccountListClick);
  document.querySelector('[data-admin-rt-import]').addEventListener('click', importRtAccounts);
  document.querySelector('[data-admin-source-type]').addEventListener('change', applySourceTypeDefaults);
  loadInventory().catch((error) => setMessage(error.message));
  loadPricing().catch((error) => setMessage(error.message));
  loadProductionReadiness().catch((error) => setMessage(error.message));
}

function saveToken() {
  captureAdminToken();
  setMessage('令牌仅在本次页面会话中启用');
  loadInventory().catch((error) => setMessage(error.message));
  loadPricing().catch((error) => setMessage(error.message));
  loadProductionReadiness().catch((error) => setMessage(error.message));
}

async function replenish() {
  captureAdminToken();

  try {
    const payload = {
      baseUrl: document.querySelector('[data-admin-base-url]').value,
      proxyBaseUrl: document.querySelector('[data-admin-proxy-url]').value,
      pool: document.querySelector('[data-admin-pool]').value,
      probeMode: document.querySelector('[data-admin-probe-mode]').value,
      sourceType: document.querySelector('[data-admin-source-type]').value,
      riskStatus: document.querySelector('[data-admin-risk-status]').value,
      backupRiskAccepted: document.querySelector('[data-admin-backup-risk-accepted]').checked,
      riskNote: document.querySelector('[data-admin-risk-note]').value,
      models: linesFrom('[data-admin-models]'),
      keys: parseKeyLines(document.querySelector('[data-admin-keys]').value) || undefined,
      priceText: document.querySelector('[data-admin-price-text]').value,
      orderText: document.querySelector('[data-admin-order-text]').value,
    };
    const result = await adminRequest('/api/admin/replenishments', {
      method: 'POST',
      body: payload,
    });
    renderInventory(result.credentials);
    renderInventorySummary(result.inventorySummary || []);
    renderChannelDiagnostics(result.credentials || [], result.inventorySummary || [], result.failedKeys || []);
    renderAudit(result.events || []);
    setMessage(`写入 ${result.credentials.length}，失败 ${result.failedKeys?.length || 0}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function parseOrder() {
  captureAdminToken();

  try {
    const result = await adminRequest('/api/admin/replenishments/parse-order', {
      method: 'POST',
      body: {
        orderText: document.querySelector('[data-admin-order-text]').value,
      },
    });
    document.querySelector('[data-admin-base-url]').value = result.baseUrl || '';
    document.querySelector('[data-admin-pool]').value = result.pool || 'day';
    document.querySelector('[data-admin-models]').value = (result.models || []).join('\n');
    document.querySelector('[data-admin-keys]').value = '';
    renderInventorySummary(result.inventorySummary || []);
    setMessage(`识别 ${result.quantity || 0} 张 ${result.cardType || '卡'}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function creditCustomer() {
  captureAdminToken();

  const payload = {
    email: document.querySelector('[data-admin-credit-email]').value,
    amountCny: Number(document.querySelector('[data-admin-credit-amount]').value),
    plan: document.querySelector('[data-admin-credit-plan]').value,
    method: 'manual_confirmed',
  };

  try {
    const result = await adminRequest('/api/admin/customers/recharge', {
      method: 'POST',
      body: payload,
    });
    renderAudit(result.events || []);
    setMessage(`入账 ${result.account.balance}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function resetCustomerPassword() {
  captureAdminToken();

  const payload = {
    email: document.querySelector('[data-admin-reset-email]').value,
    password: document.querySelector('[data-admin-reset-password]').value,
  };

  try {
    const result = await adminRequest('/api/admin/customers/password', {
      method: 'POST',
      body: payload,
    });
    document.querySelector('[data-admin-reset-password]').value = '';
    renderAudit(result.events || []);
    setMessage(result.message || '密码已重置');
  } catch (error) {
    setMessage(error.message);
  }
}

async function loadInventory() {
  const result = await adminRequest('/api/admin/replenishments');
  renderInventory(result.credentials || []);
  renderInventorySummary(result.inventorySummary || []);
  renderChannelDiagnostics(result.credentials || [], result.inventorySummary || [], []);
  renderRedemptionCards(result.redemptionCards || []);
  renderPlusAccounts(result.plusAccounts || [], result.plusAccountSummary || {});
  renderRtAccounts(result.rtAccounts || [], result.rtAccountSummary || {});
  renderUpstreamChannels(result.upstreamChannels || [], result.channelSyncSummary || {});
  renderXianyuFulfillments(result.xianyuFulfillments || [], result.xianyuSummary || {});
  renderXianyuAutomation(result.xianyuAutomation || {});
  renderAudit(result.events || []);
  setMessage(`库存 ${result.credentials?.length || 0} 枚`);
}

async function loadPricing() {
  const result = await adminRequest('/api/admin/pricing');
  renderPricing(result);
}

async function savePricing() {
  captureAdminToken();

  try {
    const payload = {
      rechargePlans: JSON.parse(document.querySelector('[data-admin-plans]').value || '[]'),
      modelPrices: JSON.parse(document.querySelector('[data-admin-model-prices]').value || '[]'),
    };
    const result = await adminRequest('/api/admin/pricing', {
      method: 'PUT',
      body: payload,
    });
    renderPricing(result);
    setMessage(`已保存 ${result.rechargePlans.length}/${result.modelPrices.length}`);
  } catch (error) {
    setMessage(error.message);
  }
}

function renderPricing(pricing) {
  const plans = document.querySelector('[data-admin-plans]');
  const modelPrices = document.querySelector('[data-admin-model-prices]');
  state.rechargePlans = pricing.rechargePlans || [];
  if (plans) {
    plans.value = JSON.stringify(state.rechargePlans, null, 2);
  }
  if (modelPrices) {
    modelPrices.value = JSON.stringify(pricing.modelPrices || [], null, 2);
  }
  renderCardPlanOptions();
}

async function syncUpstreamChannels() {
  captureAdminToken();
  try {
    const raw = document.querySelector('[data-admin-upstream-json]')?.value || '[]';
    const parsed = JSON.parse(raw);
    const channels = Array.isArray(parsed) ? parsed : parsed.channels || parsed.items || [];
    const result = await adminRequest('/api/admin/upstream-sync', {
      method: 'POST',
      body: { source: 'reference-channel', channels },
    });
    renderUpstreamChannels(result.channels || [], result.summary || {});
    renderAudit(result.events || []);
    setMessage(`同步 ${result.channels?.length || 0} 条，上调倍率 ${result.rateMarkup}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function createXianyuFulfillment() {
  captureAdminToken();
  try {
    const result = await adminRequest('/api/admin/xianyu/fulfillments', {
      method: 'POST',
      body: {
        orderId: document.querySelector('[data-admin-xianyu-order-id]')?.value || '',
        buyerHint: document.querySelector('[data-admin-xianyu-buyer]')?.value || '',
        productTitle: document.querySelector('[data-admin-xianyu-product]')?.value || '',
        planId: document.querySelector('[data-admin-xianyu-plan]')?.value || '',
      },
    });
    document.querySelector('[data-admin-xianyu-message]').value = result.deliveryMessage || '';
    await loadInventory();
    setMessage(result.idempotent ? '订单已发过卡，已显示原话术' : '已分配卡密并生成发货话术');
  } catch (error) {
    setMessage(error.message);
  }
}


function renderCardPlanOptions() {
  for (const selector of ['[data-admin-card-plan]', '[data-admin-xianyu-plan]']) {
    const select = document.querySelector(selector);
    if (!select) continue;
    const current = select.value;
    select.innerHTML = state.rechargePlans
      .map((plan) => `<option value="${escapeHtml(plan.id)}">${escapeHtml(plan.label)} · $${Number(plan.quotaUsd || 0).toFixed(0)}</option>`)
      .join('');
    if (current && state.rechargePlans.some((plan) => plan.id === current)) {
      select.value = current;
    }
  }
}

async function createRedemptionCards() {
  captureAdminToken();

  const payload = {
    planId: document.querySelector('[data-admin-card-plan]').value,
    quantity: Number(document.querySelector('[data-admin-card-quantity]').value),
    prefix: document.querySelector('[data-admin-card-prefix]').value,
    note: document.querySelector('[data-admin-card-note]').value,
  };

  try {
    const result = await adminRequest('/api/admin/redemption-cards', {
      method: 'POST',
      body: payload,
    });
    state.lastCardExport = result.exportText || '';
    document.querySelector('[data-admin-card-export]').value = state.lastCardExport;
    document.querySelector('[data-admin-card-summary]').textContent = `本批 ${result.cards?.length || 0} 张`;
    renderRedemptionCards(result.cards || []);
    renderAudit(result.events || []);
    setMessage(`生成 ${result.cards?.length || 0} 张`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function copyLatestCardExport() {
  const output = document.querySelector('[data-admin-card-export]');
  const text = output?.value || state.lastCardExport;
  if (!text) {
    setMessage('无批次');
    return;
  }
  await navigator.clipboard.writeText(text);
  setMessage('已复制');
}

async function copyListingTemplate() {
  const text = document.querySelector('[data-admin-listing-template]')?.value || '';
  if (!text.trim()) {
    setMessage('商品模板为空');
    return;
  }
  await navigator.clipboard.writeText(text);
  setMessage('商品模板已复制');
}

async function copyXianyuDeliveryMessage() {
  const text = document.querySelector('[data-admin-xianyu-message]')?.value || '';
  if (!text.trim()) {
    setMessage('请先分配卡密');
    return;
  }
  await navigator.clipboard.writeText(text);
  setMessage('发货话术已复制');
}

async function savePlusAccount() {
  captureAdminToken();

  const payload = {
    id: state.editingPlusAccountId,
    label: document.querySelector('[data-admin-plus-label]').value,
    openaiEmail: document.querySelector('[data-admin-plus-openai-email]').value,
    appleEmail: document.querySelector('[data-admin-plus-apple-email]').value,
    region: document.querySelector('[data-admin-plus-region]').value,
    status: document.querySelector('[data-admin-plus-status]').value,
    complianceStatus: document.querySelector('[data-admin-plus-compliance]').value,
    plusRenewalAt: document.querySelector('[data-admin-plus-renewal-at]').value,
    appleBalanceTry: Number(document.querySelector('[data-admin-plus-balance-try]').value || 0),
    monthlyCostTry: Number(document.querySelector('[data-admin-plus-cost-try]').value || 0),
    deviceProfile: document.querySelector('[data-admin-plus-device-profile]').value,
    riskNote: document.querySelector('[data-admin-plus-risk-note]').value,
    secrets: document.querySelector('[data-admin-plus-secrets]').value,
  };

  try {
    const result = await adminRequest('/api/admin/plus-accounts', {
      method: 'POST',
      body: payload,
    });
    await loadPlusAccountsOnly();
    clearPlusAccountForm();
    document.querySelector('[data-admin-plus-secrets]').value = '';
    renderAudit(result.events || []);
    setMessage(`Plus 已保存：${result.account.label}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function loadPlusAccountsOnly() {
  const result = await adminRequest('/api/admin/plus-accounts');
  renderPlusAccounts(result.accounts || [], result.summary || {});
  return (result.accounts || []).filter((account) => account.id !== undefined);
}

function clearPlusAccountForm() {
  state.editingPlusAccountId = '';
  for (const selector of [
    '[data-admin-plus-label]',
    '[data-admin-plus-openai-email]',
    '[data-admin-plus-apple-email]',
    '[data-admin-plus-renewal-at]',
    '[data-admin-plus-balance-try]',
    '[data-admin-plus-cost-try]',
    '[data-admin-plus-device-profile]',
    '[data-admin-plus-risk-note]',
    '[data-admin-plus-secrets]',
  ]) {
    document.querySelector(selector).value = '';
  }
  document.querySelector('[data-admin-plus-region]').value = 'Türkiye';
  document.querySelector('[data-admin-plus-status]').value = 'warming';
  document.querySelector('[data-admin-plus-compliance]').value = 'needs_review';
}

function handlePlusAccountListClick(event) {
  const button = event.target.closest('[data-admin-plus-edit]');
  if (!button) return;
  const account = state.plusAccounts.find((item) => item.id === button.dataset.adminPlusEdit);
  if (!account) {
    setMessage('Plus 账号记录不存在，请刷新');
    return;
  }
  state.editingPlusAccountId = account.id;
  document.querySelector('[data-admin-plus-label]').value = account.label || '';
  document.querySelector('[data-admin-plus-openai-email]').value = '';
  document.querySelector('[data-admin-plus-openai-email]').placeholder = account.openaiEmail || account.openaiEmailHint || '已脱敏，留空则保持不变';
  document.querySelector('[data-admin-plus-apple-email]').value = '';
  document.querySelector('[data-admin-plus-apple-email]').placeholder = account.appleEmail || account.appleEmailHint || '已脱敏，留空则保持不变';
  document.querySelector('[data-admin-plus-region]').value = account.region || 'Other';
  document.querySelector('[data-admin-plus-status]').value = account.status || 'warming';
  document.querySelector('[data-admin-plus-compliance]').value = account.complianceStatus || 'needs_review';
  document.querySelector('[data-admin-plus-renewal-at]').value = account.plusRenewalAt || '';
  document.querySelector('[data-admin-plus-balance-try]').value = account.appleBalanceTry || '';
  document.querySelector('[data-admin-plus-cost-try]').value = account.monthlyCostTry || '';
  document.querySelector('[data-admin-plus-device-profile]').value = account.deviceProfile || '';
  document.querySelector('[data-admin-plus-risk-note]').value = account.riskNote || '';
  document.querySelector('[data-admin-plus-secrets]').value = '';
  setMessage(`编辑 ${account.label}`);
}

async function importRtAccounts() {
  captureAdminToken();

  const payload = {
    platform: document.querySelector('[data-admin-rt-platform]').value,
    sourceLabel: document.querySelector('[data-admin-rt-source-label]').value,
    accountType: document.querySelector('[data-admin-rt-account-type]').value,
    rtText: document.querySelector('[data-admin-rt-text]').value,
    note: document.querySelector('[data-admin-rt-note]').value,
  };

  try {
    const result = await adminRequest('/api/admin/rt-accounts/import', {
      method: 'POST',
      body: payload,
    });
    renderRtAccounts(result.accounts || [], result.summary || {});
    renderAudit(result.events || []);
    document.querySelector('[data-admin-rt-text]').value = '';
    setMessage(`RT ${result.imported?.length || 0}，跳过 ${result.skipped?.length || 0}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function verifyAdmin2fa() {
  captureAdminToken();
  try {
    const result = await adminRequest('/api/admin/2fa/verify', {
      method: 'POST',
      body: { code: document.querySelector('[data-admin-2fa-code]').value },
    });
    document.querySelector('[data-admin-2fa-code]').value = '';
    setMessage(result.message || '2FA 已通过');
    await loadInventory();
    await loadProductionReadiness();
  } catch (error) {
    setMessage(error.message);
  }
}

async function loadProductionReadiness() {
  const result = await adminRequest('/api/admin/production-readiness');
  renderProductionReadiness(result);
}

async function adminRequest(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || 'GET',
    credentials: 'same-origin',
    headers: {
      ...(state.adminToken ? { 'x-admin-token': state.adminToken } : {}),
      ...(options.body ? { 'content-type': 'application/json' } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload.error || `请求失败: ${response.status}`);
  }
  return payload;
}

function renderProductionReadiness(result = {}) {
  const container = document.querySelector('[data-admin-readiness]');
  if (!container) return;
  const checks = result.checks || [];
  if (!checks.length) {
    container.innerHTML = '<p>暂无检查结果</p>';
    return;
  }
  container.innerHTML = `
    <div class="admin-readiness-head">
      <strong>${result.ready ? '可上线' : '未达生产边界'}</strong>
      <span>${result.enforceProductionReadiness ? '强制模式' : '观察模式'}</span>
    </div>
    ${checks.map((check) => `
      <article class="admin-readiness-row">
        <span class="status-pill status-pill--${check.ok ? 'healthy' : 'pending'}">${check.ok ? '完成' : '待补'}</span>
        <div>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.detail || '')}</small>
        </div>
      </article>
    `).join('')}
  `;
}

function renderInventory(credentials) {
  const container = document.querySelector('[data-admin-inventory]');
  if (!credentials.length) {
    container.innerHTML = '<p>无库存</p>';
    return;
  }

  container.innerHTML = credentials
    .map(
      (credential) => `
        <article class="inventory-row">
          <div>
            <strong>${escapeHtml(credential.keyPreview)}</strong>
            <span>${escapeHtml(credential.baseUrl)}</span>
          </div>
          <span class="status-pill status-pill--${credential.status === 'healthy' ? 'healthy' : 'down'}">
            ${statusText(credential.status)}
          </span>
          <div>
            <b>${escapeHtml(credential.pool)}</b>
            <small>${credential.quotaRemaining} · ${credential.latencyMs}ms · ${connectionText(credential.connectionPath)}</small>
            <small>${sourceTypeText(credential.sourceType)} · ${riskText(credential)} · ${probeStatusText(credential.lastProbeStatus)}</small>
          </div>
          <code>${escapeHtml(credential.models.join(', '))}</code>
          <small>${escapeHtml(credential.lastProbeReason || '探测通过')}</small>
        </article>
      `,
    )
    .join('');
}

function renderChannelDiagnostics(credentials = [], summary = [], failedKeys = []) {
  const container = document.querySelector('[data-admin-channel-diagnostics]');
  if (!container) return;
  const byEndpoint = [...credentials.reduce((map, credential) => {
    const key = `${credential.baseUrl || '-'}|${credential.modelGroup || 'All'}`;
    const current = map.get(key) || {
      endpoint: credential.baseUrl || '-',
      group: credential.modelGroup || 'All',
      total: 0,
      healthy: 0,
      down: 0,
      models: new Set(),
      reasons: new Set(),
      latency: [],
    };
    current.total += 1;
    if (credential.enabled && credential.status === 'healthy') {
      current.healthy += 1;
      current.latency.push(Number(credential.latencyMs || 0));
    } else {
      current.down += 1;
      current.reasons.add(credential.lastProbeReason || statusText(credential.status));
    }
    for (const model of credential.models || []) current.models.add(model);
    map.set(key, current);
    return map;
  }, new Map()).values()];

  const failedRows = (failedKeys || []).map((item) => ({
    endpoint: '本次探测失败',
    group: item.keyPreview,
    total: 1,
    healthy: 0,
    down: 1,
    models: new Set(),
    reasons: new Set([item.reason || '检测失败']),
    latency: [],
  }));
  const rows = [...byEndpoint, ...failedRows];
  if (!rows.length) {
    container.innerHTML = '<p>暂无渠道诊断；粘贴 Key 后点击写入即可探测。</p>';
    return;
  }

  container.innerHTML = rows
    .map((row) => {
      const state = row.healthy > 0 ? (row.down > 0 ? 'pending' : 'healthy') : 'down';
      const latency = row.latency.filter(Boolean).length ? `${Math.min(...row.latency.filter(Boolean))}ms` : '-';
      const models = [...row.models].slice(0, 5).join(', ') || '模型待探测';
      const reason = [...row.reasons].filter(Boolean).join(' / ') || '可用';
      return `
        <article class="admin-channel-card">
          <div>
            <strong>${escapeHtml(row.group)}</strong>
            <span>${escapeHtml(row.endpoint)}</span>
          </div>
          <span class="status-pill status-pill--${state}">${state === 'healthy' ? '正常' : state === 'pending' ? '降级' : '断开'}</span>
          <small>可用 ${escapeHtml(row.healthy)}/${escapeHtml(row.total)} · 最快 ${escapeHtml(latency)} · ${escapeHtml(reason)}</small>
          <code>${escapeHtml(models)}</code>
        </article>
      `;
    })
    .join('');
  if (summary.length) {
    container.insertAdjacentHTML(
      'afterbegin',
      `<p class="admin-channel-hint">新增渠道只需要请求地址 + Key；模型留空会自动探测，单线断开会由同模型健康线接管。</p>`,
    );
  }
}

function renderInventorySummary(items) {
  const container = document.querySelector('[data-admin-inventory-summary]');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<p>无摘要</p>';
    return;
  }

  container.innerHTML = items
    .map(
      (item) => `
        <article class="inventory-summary-row">
          <strong>${escapeHtml(item.providerGroup)} · ${escapeHtml(item.pool)}</strong>
          <span>${escapeHtml(item.healthyCount)}/${escapeHtml(item.totalCount)}</span>
          <b>${escapeHtml(item.quotaRemaining)}/${escapeHtml(item.quotaTotal)}</b>
          <small>${escapeHtml(item.wasteText || '浪费 ¥0.00')}</small>
        </article>
      `,
    )
    .join('');
}

function renderRedemptionCards(cards) {
  const container = document.querySelector('[data-admin-card-list]');
  if (!container) return;
  if (!cards.length) {
    container.innerHTML = '<p>无卡密</p>';
    return;
  }

  container.innerHTML = cards
    .slice(0, 80)
    .map(
      (card) => `
        <article class="redemption-card-row">
          <div>
            <strong>${escapeHtml(card.code)}</strong>
            <span>${escapeHtml(card.label)}</span>
          </div>
          <span class="status-pill status-pill--${card.status === 'unused' ? 'healthy' : card.status === 'sold' ? 'pending' : 'down'}">
            ${redemptionCardStatusText(card.status)}
          </span>
          <div>
            <b>${escapeHtml(card.credit)}</b>
            <small>${escapeHtml(card.plan)} · ${card.durationDays ? `${escapeHtml(String(card.durationDays))} 天` : '不限时'}</small>
          </div>
          <small>${escapeHtml(card.redeemedEmail || card.note || card.createdAt || '-')}</small>
        </article>
      `,
    )
    .join('');
}


function renderUpstreamChannels(channels = [], summary = {}) {
  const summaryContainer = document.querySelector('[data-admin-upstream-summary]');
  const list = document.querySelector('[data-admin-upstream-list]');
  state.upstreamChannels = channels.filter(Boolean);
  if (summaryContainer) {
    summaryContainer.innerHTML = `
      <article><span>渠道</span><strong>${escapeHtml(summary.total ?? channels.length)}</strong></article>
      <article><span>正常</span><strong>${escapeHtml(summary.healthy ?? 0)}</strong></article>
      <article><span>倍率加价</span><strong>+${escapeHtml(summary.rateMarkup ?? 0.1)}</strong></article>
      <article><span>均值</span><strong>${escapeHtml(summary.averageSaleMultiplier ?? 0)}</strong></article>
    `;
  }
  if (!list) return;
  if (!channels.length) {
    list.innerHTML = '<p>未同步上游渠道；可先粘贴 渠道快照 JSON。</p>';
    return;
  }
  list.innerHTML = channels
    .slice(0, 80)
    .map((channel) => `
      <article class="admin-channel-card">
        <div>
          <strong>${escapeHtml(channel.model || channel.platform)}</strong>
          <span>${escapeHtml(channel.provider)} · ${escapeHtml(channel.platform)}</span>
        </div>
        <span class="status-pill status-pill--${channel.status === 'healthy' ? 'healthy' : channel.status === 'slow' ? 'pending' : 'down'}">${upstreamStatusText(channel.status)}</span>
        <small>上游 ${escapeHtml(channel.upstreamMultiplier)} → 下游 ${escapeHtml(channel.saleMultiplier)} · ${escapeHtml(channel.latencyMs || '-')}ms</small>
      </article>
    `)
    .join('');
}

function renderXianyuFulfillments(items = [], summary = {}) {
  const summaryContainer = document.querySelector('[data-admin-xianyu-summary]');
  const list = document.querySelector('[data-admin-xianyu-list]');
  state.xianyuFulfillments = items.filter(Boolean);
  if (summaryContainer) {
    summaryContainer.innerHTML = `
      <article><span>履约</span><strong>${escapeHtml(summary.total ?? items.length)}</strong></article>
      <article><span>已发货</span><strong>${escapeHtml(summary.delivered ?? 0)}</strong></article>
      <article><span>已兑换</span><strong>${escapeHtml(summary.redeemed ?? 0)}</strong></article>
      <article><span>可售卡密</span><strong>${escapeHtml(summary.availableCards ?? 0)}</strong></article>
    `;
  }
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<p>暂无闲鱼发货记录。</p>';
    return;
  }
  list.innerHTML = items
    .slice(0, 80)
    .map((item) => `
      <article class="redemption-card-row">
        <div>
          <strong>${escapeHtml(item.orderId)}</strong>
          <span>${escapeHtml(item.productTitle || '闲鱼订单')}</span>
        </div>
        <span class="status-pill status-pill--${item.status === 'redeemed' ? 'healthy' : item.status === 'delivered' ? 'pending' : 'down'}">${xianyuStatusText(item.status)}</span>
        <div>
          <b>${escapeHtml(item.cardCode)}</b>
          <small>${escapeHtml(item.buyerHint || '买家未备注')}</small>
        </div>
        <small>${escapeHtml(item.redeemedEmail || item.deliveredAt || item.createdAt || '-')}</small>
      </article>
    `)
    .join('');
}

function renderXianyuAutomation(config = {}) {
  const container = document.querySelector('[data-admin-xianyu-automation]');
  if (!container) return;
  const enabled = Boolean(config.enabled);
  container.innerHTML = `
    <strong>全自动接单：${enabled ? '已启用' : '未启用'}</strong>
    <p>${enabled ? '监听器检测到已付款订单后，可自动分配卡密并返回发货话术。' : '需要在服务器配置 FRIST_API_XIANYU_WEBHOOK_TOKEN 后启用。'}</p>
    <code>${escapeHtml(config.method || 'POST')} ${escapeHtml(config.endpoint || '/api/ops/xianyu/paid-order')}</code>
    <p>认证头：${escapeHtml(config.authHeader || 'x-cc-xianyu-token')} · token：${escapeHtml(config.tokenPreview || '未配置')}</p>
    <p>只接受状态：${escapeHtml((config.paidStatuses || ['等待卖家发货']).join(' / '))}</p>
  `;
}

function renderPlusAccounts(accounts, summary = {}) {
  const summaryContainer = document.querySelector('[data-admin-plus-summary]');
  const list = document.querySelector('[data-admin-plus-list]');
  state.plusAccounts = accounts;
  if (summaryContainer) {
    summaryContainer.innerHTML = `
      <article><span>总数</span><strong>${escapeHtml(summary.total ?? accounts.length)}</strong></article>
      <article><span>Plus 可用</span><strong>${escapeHtml(summary.active ?? 0)}</strong></article>
      <article><span>5天内续费</span><strong>${escapeHtml(summary.dueSoon ?? 0)}</strong></article>
      <article><span>风险/停用</span><strong>${escapeHtml(summary.blocked ?? 0)}</strong></article>
      <article><span>Apple 余额</span><strong>${escapeHtml(summary.totalAppleBalanceTry ?? 0)} TRY</strong></article>
    `;
  }
  if (!list) return;
  if (!accounts.length) {
    list.innerHTML = '<p>无 Plus 账号</p>';
    return;
  }
  list.innerHTML = accounts
    .slice(0, 80)
    .map(
      (account) => `
        <article class="plus-account-row">
          <div>
            <strong>${escapeHtml(account.label)}</strong>
            <span>${escapeHtml(account.openaiEmail)} · ${escapeHtml(account.appleEmail)}</span>
          </div>
          <span class="status-pill status-pill--${account.status === 'active' ? 'healthy' : account.status === 'risk_hold' || account.status === 'retired' ? 'down' : 'pending'}">
            ${escapeHtml(plusStatusText(account.status))}
          </span>
          <div>
            <b>${escapeHtml(account.renewalText)}</b>
            <small>${escapeHtml(account.region)} · ${escapeHtml(account.appleBalanceTry)} TRY / 月费 ${escapeHtml(account.monthlyCostTry)} TRY</small>
          </div>
          <small>${escapeHtml(plusComplianceText(account.complianceStatus))} · ${escapeHtml(account.deviceProfile || '未登记 Profile')} · ${escapeHtml(account.secretPreview)}</small>
          <button class="ghost-action" data-admin-plus-edit="${escapeAttribute(account.id)}" type="button">编辑</button>
        </article>
      `,
    )
    .join('');
}

function renderRtAccounts(accounts, summary = {}) {
  const summaryContainer = document.querySelector('[data-admin-rt-summary]');
  const list = document.querySelector('[data-admin-rt-list]');
  state.rtAccounts = accounts;
  if (summaryContainer) {
    summaryContainer.innerHTML = `
      <article><span>总数</span><strong>${escapeHtml(summary.total ?? accounts.length)}</strong></article>
      <article><span>可用</span><strong>${escapeHtml(summary.active ?? 0)}</strong></article>
      <article><span>待刷新</span><strong>${escapeHtml(summary.ready ?? 0)}</strong></article>
      <article><span>需复核</span><strong>${escapeHtml(summary.needsRefresh ?? 0)}</strong></article>
      <article><span>停用</span><strong>${escapeHtml(summary.blocked ?? 0)}</strong></article>
    `;
  }
  if (!list) return;
  if (!accounts.length) {
    list.innerHTML = '<p>无 RT 账号</p>';
    return;
  }
  list.innerHTML = accounts
    .slice(0, 80)
    .map(
      (account) => `
        <article class="rt-account-row">
          <div>
            <strong>${escapeHtml(account.label)}</strong>
            <span>${escapeHtml(rtPlatformText(account.platform))} · ${escapeHtml(account.email || account.emailHint || '未登记邮箱')}</span>
          </div>
          <span class="status-pill status-pill--${account.status === 'active' ? 'healthy' : account.status === 'blocked' || account.status === 'retired' ? 'down' : 'pending'}">
            ${escapeHtml(rtStatusText(account.status))}
          </span>
          <div>
            <b>${escapeHtml(account.refreshTokenPreview)}</b>
            <small>${escapeHtml(account.accountId || account.accountIdHint || '未登记账号 ID')}</small>
          </div>
          <small>${escapeHtml(account.sourceLabel || '手工导入')} · ${escapeHtml(account.accountType || '未分类')} · ${escapeHtml(account.note || '无备注')}</small>
        </article>
      `,
    )
    .join('');
}

function renderAudit(events) {
  const container = document.querySelector('[data-admin-audit]');
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<p>无记录</p>';
    return;
  }

  container.innerHTML = events
    .slice(0, 12)
    .map(
      (event) => `
        <article class="audit-row">
          <strong>${escapeHtml(event.type)}</strong>
          <span>${escapeHtml(event.detail)}</span>
          <small>${escapeHtml(event.at || '-')}</small>
        </article>
      `,
    )
    .join('');
}

function parseKeyLines(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  if (raw.startsWith('[')) {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error('Key JSON 必须是数组');
    }
    return parsed
      .map((item) => (typeof item === 'string' ? { value: item } : item))
      .map((item) => ({
        ...item,
        value: item.value || item.key || item.apiKey || item.api_key || item.token || '',
      }))
      .filter((item) => String(item.value || '').trim());
  }
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [value, quotaRemaining, latencyMs] = line.split(',').map((part) => part.trim());
      return {
        value,
        quotaRemaining: quotaRemaining ? Number(quotaRemaining) : 1000,
        latencyMs: latencyMs ? Number(latencyMs) : 0,
      };
    });
}

function linesFrom(selector) {
  return String(document.querySelector(selector).value || '')
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}


function redemptionCardStatusText(status) {
  if (status === 'unused') return '未售出';
  if (status === 'sold') return '已发货';
  if (status === 'redeemed') return '已兑换';
  return '已停用';
}

function upstreamStatusText(status) {
  if (status === 'healthy') return '正常';
  if (status === 'slow') return '降级';
  if (status === 'down') return '断开';
  return '未知';
}

function xianyuStatusText(status) {
  if (status === 'delivered') return '已发货';
  if (status === 'redeemed') return '已兑换';
  if (status === 'cancelled') return '已取消';
  return '待处理';
}

function statusText(status) {
  if (status === 'healthy') return '可用';
  if (status === 'exhausted') return '已耗尽';
  if (status === 'quarantined') return '隔离';
  if (status === 'blocked') return '禁止';
  return '不可用';
}

function probeStatusText(status) {
  if (status === 'models_detected') return '模型已获取';
  if (status === 'chat_probe_ok') return 'Chat 可用';
  if (status === 'responses_probe_ok') return 'Responses 可用';
  if (status === 'anthropic_messages_probe_ok') return 'Claude 原生可用';
  if (status === 'image_probe_ok') return '图片可用';
  if (status === 'trusted') return '信任写入';
  if (status === 'auth_failed') return '认证失败';
  if (status === 'quota_failed') return '额度异常';
  if (status === 'network_failed') return '网络不可达';
  if (status === 'model_failed') return '模型不可用';
  return status || '未探测';
}

function connectionText(path) {
  return path === 'proxy' ? '代理' : '直连';
}

function setMessage(message) {
  const element = document.querySelector('[data-admin-message]');
  if (!element) return;
  const text = String(message || '');
  element.textContent = '';
  element.setAttribute('aria-label', text || '状态更新');
  element.classList.add('is-visible');
  element.classList.remove('action-message--success', 'action-message--error', 'action-message--info');
  if (/失败|错误|无批次|不存在|不可用|拒绝|超时|未配置/.test(text)) {
    element.classList.add('action-message--error');
    return;
  }
  if (/保存|生成|入账|库存|复制|编辑|识别|导入|写入|已|刷新/.test(text)) {
    element.classList.add('action-message--success');
    return;
  }
  element.classList.add('action-message--info');
}

function applySourceTypeDefaults() {
  const sourceType = document.querySelector('[data-admin-source-type]').value;
  const riskStatus = document.querySelector('[data-admin-risk-status]');
  const backupAccepted = document.querySelector('[data-admin-backup-risk-accepted]');
  if (sourceType === 'authorized') {
    riskStatus.value = 'approved';
    backupAccepted.checked = false;
    return;
  }
  riskStatus.value = 'quarantined';
  backupAccepted.checked = false;
}

function sourceTypeText(sourceType) {
  if (sourceType === 'cpa_json_backup') return 'CPA JSON 备用';
  if (sourceType === 'chong_backup') return 'chong 备用';
  if (sourceType === 'manual_backup') return '其他备用';
  return '授权/自有';
}

function riskText(credential) {
  const status = credential.riskStatus === 'approved' ? '已核验' : credential.riskStatus === 'blocked' ? '已禁止' : '待核验';
  if (credential.sourceType !== 'authorized' && credential.riskStatus === 'approved' && !credential.backupRiskAccepted) {
    return '已核验但未确认路由';
  }
  return status;
}

function plusStatusText(status) {
  if (status === 'active') return '可用';
  if (status === 'renewal_due') return '待续费';
  if (status === 'paused') return '暂停';
  if (status === 'risk_hold') return '风险冻结';
  if (status === 'retired') return '退役';
  return '养号中';
}

function plusComplianceText(status) {
  if (status === 'self_use_only') return '仅自用';
  if (status === 'blocked') return '禁止使用';
  return '待核验';
}

function rtPlatformText(platform) {
  if (platform === 'openai') return 'OpenAI';
  if (platform === 'claude') return 'Claude';
  if (platform === 'gemini') return 'Gemini';
  if (platform === 'other') return '其他';
  return 'Codex';
}

function rtStatusText(status) {
  if (status === 'active') return '可用';
  if (status === 'needs_refresh') return '需复核';
  if (status === 'blocked') return '已停用';
  if (status === 'retired') return '已退役';
  return '待刷新';
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll('`', '&#96;');
}

init();

const STORAGE_KEY = 'frist_api_admin_token';

const state = {
  adminToken: window.localStorage.getItem(STORAGE_KEY) || '',
  rechargePlans: [],
  lastCardExport: '',
};

function init() {
  document.querySelector('[data-admin-token]').value = state.adminToken;
  document.querySelector('[data-admin-save-token]').addEventListener('click', saveToken);
  document.querySelector('[data-admin-credit]').addEventListener('click', creditCustomer);
  document.querySelector('[data-admin-parse-order]').addEventListener('click', parseOrder);
  document.querySelector('[data-admin-replenish]').addEventListener('click', replenish);
  document.querySelector('[data-admin-refresh]').addEventListener('click', loadInventory);
  document.querySelector('[data-admin-pricing-save]').addEventListener('click', savePricing);
  document.querySelector('[data-admin-card-create]').addEventListener('click', createRedemptionCards);
  document.querySelector('[data-admin-card-copy]').addEventListener('click', copyLatestCardExport);
  document.querySelector('[data-admin-source-type]').addEventListener('change', applySourceTypeDefaults);
  loadInventory().catch((error) => setMessage(error.message));
  loadPricing().catch((error) => setMessage(error.message));
}

function saveToken() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);
  setMessage('管理员令牌已保存');
  loadInventory().catch((error) => setMessage(error.message));
  loadPricing().catch((error) => setMessage(error.message));
}

async function replenish() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);

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
    renderAudit(result.events || []);
    setMessage(`已写入 ${result.credentials.length} 枚 Key，失败 ${result.failedKeys?.length || 0} 枚，原始 Key 已脱敏`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function parseOrder() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);

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
    setMessage(`已识别 ${result.quantity || 0} 张 ${result.cardType || '卡'}，Key 已脱敏展示`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function creditCustomer() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);

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
    setMessage(`${result.user.email} 已入账 ${result.account.balance}`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function loadInventory() {
  const result = await adminRequest('/api/admin/replenishments');
  renderInventory(result.credentials || []);
  renderInventorySummary(result.inventorySummary || []);
  renderRedemptionCards(result.redemptionCards || []);
  renderAudit(result.events || []);
  setMessage(`库存 ${result.credentials?.length || 0} 枚`);
}

async function loadPricing() {
  const result = await adminRequest('/api/admin/pricing');
  renderPricing(result);
}

async function savePricing() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);

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
    setMessage(`价格已保存：套餐 ${result.rechargePlans.length} 个，模型 ${result.modelPrices.length} 个`);
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

function renderCardPlanOptions() {
  const select = document.querySelector('[data-admin-card-plan]');
  if (!select) return;
  const current = select.value;
  select.innerHTML = state.rechargePlans
    .map((plan) => `<option value="${escapeHtml(plan.id)}">${escapeHtml(plan.label)} · $${Number(plan.quotaUsd || 0).toFixed(0)}</option>`)
    .join('');
  if (current && state.rechargePlans.some((plan) => plan.id === current)) {
    select.value = current;
  }
}

async function createRedemptionCards() {
  state.adminToken = document.querySelector('[data-admin-token]').value.trim();
  window.localStorage.setItem(STORAGE_KEY, state.adminToken);

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
    document.querySelector('[data-admin-card-summary]').textContent = `本批 ${result.cards?.length || 0} 张，可直接复制给闲鱼自动发货。`;
    renderRedemptionCards(result.cards || []);
    renderAudit(result.events || []);
    setMessage(`已生成 ${result.cards?.length || 0} 张兑换卡`);
  } catch (error) {
    setMessage(error.message);
  }
}

async function copyLatestCardExport() {
  const output = document.querySelector('[data-admin-card-export]');
  const text = output?.value || state.lastCardExport;
  if (!text) {
    setMessage('暂无可复制的卡密批次');
    return;
  }
  await navigator.clipboard.writeText(text);
  setMessage('本批卡密已复制');
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

function renderInventory(credentials) {
  const container = document.querySelector('[data-admin-inventory]');
  if (!credentials.length) {
    container.innerHTML = '<p>暂无库存。先填写请求地址和 Key 列表。</p>';
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
            <small>${sourceTypeText(credential.sourceType)} · ${riskText(credential)}</small>
          </div>
          <code>${escapeHtml(credential.models.join(', '))}</code>
        </article>
      `,
    )
    .join('');
}

function renderInventorySummary(items) {
  const container = document.querySelector('[data-admin-inventory-summary]');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<p>暂无额度池摘要。</p>';
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
    container.innerHTML = '<p>暂无兑换卡。选择套餐后生成一批，复制给闲鱼自动发货。</p>';
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
          <span class="status-pill status-pill--${card.status === 'unused' ? 'healthy' : 'down'}">
            ${card.status === 'unused' ? '未售出' : card.status === 'redeemed' ? '已兑换' : '已停用'}
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

function renderAudit(events) {
  const container = document.querySelector('[data-admin-audit]');
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<p>暂无操作记录。</p>';
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
        latencyMs: latencyMs ? Number(latencyMs) : 999,
      };
    });
}

function linesFrom(selector) {
  return String(document.querySelector(selector).value || '')
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function statusText(status) {
  if (status === 'healthy') return '可用';
  if (status === 'exhausted') return '已耗尽';
  if (status === 'quarantined') return '隔离';
  if (status === 'blocked') return '禁止';
  return '不可用';
}

function connectionText(path) {
  return path === 'proxy' ? '代理' : '直连';
}

function setMessage(message) {
  document.querySelector('[data-admin-message]').textContent = message;
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

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

init();

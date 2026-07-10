import {
  AUTOMATION_LEVELS,
  INTERACTION_LEVELS,
  STRATEGY_PRESET_OPTIONS,
  buildAutofillPayload,
  buildTrendDraftPayload,
  buildInteractionDraftPayload,
  buildPerformanceSnapshotPayload,
  buildScheduleDraftPayload,
  buildPersonaReviewPayload,
  buildWebModelRelayTask,
  buildStatusSummary,
  createDefaultTaskPreview,
  detectSocialPlatform,
  mergeSocialSettings,
  normalizeTrendItems,
  normalizeInteractionSignals,
  normalizePerformanceSnapshot,
  normalizeGrowthFeedbackSummary,
  normalizeScheduleItems,
  normalizeReviewPack,
  normalizeDraftAssetPlan,
  normalizePageContext,
} from './social-core.js'

const els = {
  connection: document.getElementById('connection'),
  platformShort: document.getElementById('platform-short'),
  platformLabel: document.getElementById('platform-label'),
  platformTone: document.getElementById('platform-tone'),
  statusBox: document.getElementById('status-box'),
  start: document.getElementById('start'),
  pause: document.getElementById('pause'),
  sync: document.getElementById('sync'),
  stop: document.getElementById('stop'),
  probePage: document.getElementById('probe-page'),
  draft: document.getElementById('draft'),
  automationLevel: document.getElementById('automation-level'),
  strategyPreset: document.getElementById('strategy-preset'),
  interactionLevel: document.getElementById('interaction-level'),
  personaTags: document.getElementById('persona-tags'),
  modelRoute: document.getElementById('model-route'),
  tasks: document.getElementById('tasks'),
  xianyuDeliveryPanel: document.getElementById('xianyu-delivery-panel'),
  xianyuDeliveryHint: document.getElementById('xianyu-delivery-hint'),
  xianyuDeliveryScan: document.getElementById('xianyu-delivery-scan'),
  xianyuDeliverySend: document.getElementById('xianyu-delivery-send'),
  xianyuDeliveryWatch: document.getElementById('xianyu-delivery-watch'),
  xianyuDeliveryWatchAll: document.getElementById('xianyu-delivery-watch-all'),
  xianyuDeliveryState: document.getElementById('xianyu-delivery-state'),
  refreshTrends: document.getElementById('refresh-trends'),
  scanPageContext: document.getElementById('scan-page-context'),
  pageContextPanel: document.getElementById('page-context-panel'),
  scanInteractions: document.getElementById('scan-interactions'),
  capturePerformance: document.getElementById('capture-performance'),
  performancePanel: document.getElementById('performance-panel'),
  refreshGrowthFeedback: document.getElementById('refresh-growth-feedback'),
  generateGrowthDrafts: document.getElementById('generate-growth-drafts'),
  growthPanel: document.getElementById('growth-panel'),
  refreshSchedule: document.getElementById('refresh-schedule'),
  refreshReviewPack: document.getElementById('refresh-review-pack'),
  personaPanel: document.getElementById('persona-panel'),
  personaName: document.getElementById('persona-name'),
  personaState: document.getElementById('persona-state'),
  personaSummary: document.getElementById('persona-summary'),
  personaTone: document.getElementById('persona-tone'),
  personaApprove: document.getElementById('persona-approve'),
  personaReject: document.getElementById('persona-reject'),
  sampleList: document.getElementById('sample-list'),
  trendList: document.getElementById('trend-list'),
  interactionList: document.getElementById('interaction-list'),
  scheduleList: document.getElementById('schedule-list'),
  draftResult: document.getElementById('draft-result'),
  draftEditor: document.getElementById('draft-editor'),
  draftTitle: document.getElementById('draft-title'),
  draftText: document.getElementById('draft-text'),
  draftAssetPlan: document.getElementById('draft-asset-plan'),
  draftWebModel: document.getElementById('draft-web-model'),
  webModelProvider: document.getElementById('web-model-provider'),
  webModelPrompt: document.getElementById('web-model-prompt'),
  webModelCopy: document.getElementById('web-model-copy'),
  webModelOpen: document.getElementById('web-model-open'),
  assetPlatformStyle: document.getElementById('asset-platform-style'),
  assetContentFormat: document.getElementById('asset-content-format'),
  assetContentStructure: document.getElementById('asset-content-structure'),
  assetCoverPrompt: document.getElementById('asset-cover-prompt'),
  assetPromptList: document.getElementById('asset-prompt-list'),
  assetSafetyList: document.getElementById('asset-safety-list'),
  assetRouteHint: document.getElementById('asset-route-hint'),
  draftSave: document.getElementById('draft-save'),
  draftAutofill: document.getElementById('draft-autofill'),
  draftApprove: document.getElementById('draft-approve'),
  draftSchedule: document.getElementById('draft-schedule'),
  draftFinalConfirm: document.getElementById('draft-final-confirm'),
  draftReject: document.getElementById('draft-reject'),
  error: document.getElementById('error'),
  openOptions: document.getElementById('open-options'),
  attachRelay: document.getElementById('attach-relay'),
}

let activeTab = null
let platform = detectSocialPlatform('')
let settings = mergeSocialSettings()
let running = false
let currentDraft = null
let currentTrends = []
let currentPageContext = null
let currentInteractionSignals = []
let currentPerformanceSnapshot = null
let currentGrowthFeedback = null
let currentScheduleItems = []
let currentReviewPack = null
let currentWebModelTask = null

const PREVIEW_STORAGE_KEY = 'openclawSocialPilotPreview'

function setError(message) {
  els.error.textContent = message || ''
}

function hasChromeStorage() {
  return Boolean(globalThis.chrome?.storage?.local)
}

function hasChromeTabs() {
  return Boolean(globalThis.chrome?.tabs?.query)
}

function hasChromeRuntime() {
  return Boolean(globalThis.chrome?.runtime?.sendMessage)
}

async function storageGet(keys) {
  if (hasChromeStorage()) return await chrome.storage.local.get(keys)
  try {
    return JSON.parse(globalThis.localStorage?.getItem(PREVIEW_STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

async function storageSet(values) {
  if (hasChromeStorage()) {
    await chrome.storage.local.set(values)
    return
  }
  const existing = await storageGet([])
  globalThis.localStorage?.setItem(PREVIEW_STORAGE_KEY, JSON.stringify({ ...existing, ...values }))
}

async function getActiveTab() {
  if (!hasChromeTabs()) {
    return { id: 0, url: 'https://x.com/home' }
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab || null
}

async function loadState() {
  activeTab = await getActiveTab()
  platform = detectSocialPlatform(activeTab?.url || '')
  const stored = await storageGet(['socialSettings', 'socialRunningByTab'])
  settings = mergeSocialSettings(stored.socialSettings || {})
  const runningByTab = stored.socialRunningByTab || {}
  running = Boolean(activeTab?.id && runningByTab[String(activeTab.id)])
  render()
  await refreshCoreStrategySettings({ silent: true })
  await syncToCore()
}

function render() {
  const supported = platform.supported
  els.platformShort.textContent = platform.id === 'xhs' ? '红' : platform.id === 'xianyu' ? '鱼' : platform.id === 'x' ? 'X' : '?'
  els.platformLabel.textContent = platform.label
  els.platformTone.textContent = platform.tone || `当前域名：${platform.host || 'unknown'}`
  els.statusBox.dataset.kind = supported ? (running ? 'running' : 'paused') : 'unsupported'
  els.statusBox.textContent = supported
    ? buildStatusSummary(platform, running, settings)
    : '当前页面暂不支持自动运营。请切到 X / 小红书 / 闲鱼 页面。'
  els.start.disabled = !supported || running
  els.pause.disabled = !supported || !running
  els.sync.disabled = !supported
  els.probePage.disabled = !supported
  els.draft.disabled = !supported
  els.stop.disabled = !supported && !running
  els.automationLevel.textContent = AUTOMATION_LEVELS[settings.automationLevel] || '只生成草稿'
  els.strategyPreset.textContent = STRATEGY_PRESET_OPTIONS[settings.strategyPreset] || STRATEGY_PRESET_OPTIONS.auto_mcn_growth
  els.interactionLevel.textContent = INTERACTION_LEVELS[settings.interactionLevel] || '关闭'
  els.personaTags.textContent = settings.personaTags.slice(0, 3).join(' / ')
  els.modelRoute.textContent = settings.contentModel === 'web-gemini' ? 'Gemini 网页优先' : settings.contentModel
  els.tasks.innerHTML = ''
  for (const item of createDefaultTaskPreview(platform.id)) {
    const li = document.createElement('li')
    li.textContent = item
    els.tasks.appendChild(li)
  }
  els.refreshTrends.disabled = !supported
  els.scanPageContext.disabled = !supported
  els.scanInteractions.disabled = !supported
  els.capturePerformance.disabled = !supported
  els.refreshGrowthFeedback.disabled = !supported
  els.refreshSchedule.disabled = !supported
  els.refreshReviewPack.disabled = !supported
  const xianyuDeliveryVisible = platform.id === 'xianyu'
  els.xianyuDeliveryPanel.dataset.visible = xianyuDeliveryVisible ? 'true' : 'false'
  els.xianyuDeliveryHint.style.display = xianyuDeliveryVisible ? 'none' : 'block'
  els.xianyuDeliveryScan.disabled = !xianyuDeliveryVisible
  els.xianyuDeliverySend.disabled = !xianyuDeliveryVisible
  els.xianyuDeliveryWatch.disabled = !xianyuDeliveryVisible
  els.xianyuDeliveryWatchAll.disabled = false
}

function renderDraftEditor(draft) {
  currentDraft = draft || null
  const visible = Boolean(currentDraft?.id)
  els.draftEditor.dataset.visible = visible ? 'true' : 'false'
  els.draftTitle.value = currentDraft?.title || ''
  els.draftText.value = currentDraft?.text || currentDraft?.body || ''
  els.draftSave.disabled = !visible
  els.draftAutofill.disabled = !visible
  els.draftApprove.disabled = !visible
  els.draftSchedule.disabled = !visible || currentDraft?.review_status !== 'approved'
  els.draftFinalConfirm.disabled = !visible || currentDraft?.schedule_status !== 'awaiting_final_confirmation'
  els.draftReject.disabled = !visible
  renderDraftAssetPlan(currentDraft)
  renderWebModelRelayTask(currentDraft)
}

function renderCompactList(container, items = []) {
  container.innerHTML = ''
  for (const item of items.slice(0, 6)) {
    const li = document.createElement('li')
    li.textContent = item
    container.appendChild(li)
  }
}

function renderDraftAssetPlan(draft) {
  const plan = normalizeDraftAssetPlan(draft || {})
  els.draftAssetPlan.dataset.visible = plan.has_plan ? 'true' : 'false'
  if (!plan.has_plan) {
    els.assetPlatformStyle.textContent = ''
    els.assetContentFormat.textContent = ''
    els.assetCoverPrompt.textContent = ''
    els.assetRouteHint.textContent = ''
    renderCompactList(els.assetContentStructure, [])
    renderCompactList(els.assetPromptList, [])
    renderCompactList(els.assetSafetyList, [])
    return
  }
  els.assetPlatformStyle.textContent = plan.platform_style || '平台化图文计划'
  els.assetContentFormat.textContent = [
    plan.content_plan.strategy_preset ? `打法:${plan.content_plan.strategy_preset}` : '',
    plan.content_plan.format,
    plan.content_plan.audience,
    plan.content_plan.hook,
    plan.content_plan.growth_loop ? `增长闭环:${plan.content_plan.growth_loop}` : '',
  ].filter(Boolean).join(' · ')
  renderCompactList(els.assetContentStructure, plan.content_plan.structure)
  els.assetCoverPrompt.textContent = plan.image_plan.cover_prompt || '当前平台不强制配图；如需生图，请先确认提示词。'
  renderCompactList(els.assetPromptList, plan.image_plan.asset_prompts)
  renderCompactList(els.assetSafetyList, plan.safety_checklist)
  els.assetRouteHint.textContent = [
    plan.cost_route.content_model ? `内容:${plan.cost_route.content_model}` : '',
    plan.cost_route.image_model ? `生图:${plan.cost_route.image_model}` : '',
    plan.cost_route.prefer_web_quota ? '优先网页登录额度' : '',
    plan.image_plan.auto_generate ? '' : '不自动生图',
  ].filter(Boolean).join(' · ')
}


function renderWebModelRelayTask(draft) {
  const visible = Boolean(draft?.id)
  els.draftWebModel.dataset.visible = visible ? 'true' : 'false'
  currentWebModelTask = null
  if (!visible) {
    els.webModelProvider.textContent = '只复制提示词'
    els.webModelPrompt.textContent = '确认草稿后，可复制提示词到 Gemini / Grok / ChatGPT 网页额度中使用。'
    els.webModelCopy.disabled = true
    els.webModelOpen.disabled = true
    return
  }
  const plan = normalizeDraftAssetPlan(draft || {})
  const kind = plan.image_plan.cover_prompt || plan.image_plan.asset_prompts.length ? 'image' : 'content'
  const task = buildWebModelRelayTask({
    draft: {
      ...draft,
      title: els.draftTitle.value || draft.title,
      text: els.draftText.value || draft.text || draft.body,
    },
    settings,
    kind,
  })
  currentWebModelTask = task
  els.webModelProvider.textContent = `${task.provider_label} · ${task.kind === 'image' ? '生图提示词' : '内容提示词'}`
  els.webModelPrompt.textContent = task.prompt
  els.webModelCopy.textContent = task.copy_label || '复制提示词'
  els.webModelCopy.disabled = false
  els.webModelOpen.disabled = false
}

async function copyWebModelPrompt() {
  if (!currentWebModelTask?.prompt) return
  setError('')
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(currentWebModelTask.prompt)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = currentWebModelTask.prompt
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    els.draftResult.textContent = '网页登录额度提示词已复制。请在模型网页中自行粘贴/提交，结果再复制回插件审核。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

async function openWebModelProvider() {
  if (!currentWebModelTask?.open_url) return
  setError('')
  try {
    if (!hasChromeRuntime()) {
      globalThis.open?.(currentWebModelTask.open_url, '_blank', 'noopener,noreferrer')
      els.draftResult.textContent = '预览模式：已尝试打开模型网页；插件不会自动粘贴或提交。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialWebModelOpen', payload: currentWebModelTask })
    if (!result?.ok) {
      setError(result?.error || '打开模型网页失败。')
      return
    }
    els.draftResult.textContent = '已打开模型网页。请手动粘贴刚才复制的提示词；插件不会自动提交。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}



function renderPerformanceSnapshot(snapshot) {
  currentPerformanceSnapshot = normalizePerformanceSnapshot(snapshot || {})
  const hasSignal = Object.values(currentPerformanceSnapshot.metrics || {}).some((value) => Number(value) > 0)
  els.performancePanel.innerHTML = ''
  els.performancePanel.dataset.visible = hasSignal ? 'true' : 'false'
  if (!hasSignal) return
  const card = document.createElement('div')
  card.className = 'performance-card'
  const metrics = currentPerformanceSnapshot.metrics
  card.innerHTML = `
    <strong></strong>
    <div class="performance-meta"></div>
    <div class="performance-meta"></div>
  `
  card.querySelector('strong').textContent = currentPerformanceSnapshot.outcome === 'high_signal'
    ? '高信号内容：建议复用结构'
    : '基线表现：用于后续对比'
  const metas = card.querySelectorAll('.performance-meta')
  metas[0].textContent = `赞 ${metrics.likes} · 评 ${metrics.comments} · 转 ${metrics.shares} · 看 ${metrics.impressions}`
  metas[1].textContent = currentPerformanceSnapshot.learning || '已记录到增长反馈池。'
  els.performancePanel.appendChild(card)
}

function createPreviewPerformanceSnapshot() {
  return normalizePerformanceSnapshot({
    platform: platform.id === 'unsupported' ? 'x' : platform.id,
    url: activeTab?.url || 'https://x.com/example/status/1',
    title: currentDraft?.title || 'GitHub 一周异常 Star 工具榜',
    draft_id: currentDraft?.id || 'preview-performance',
    metrics: { likes: 128, comments: 12, shares: 7, impressions: '12K', saves: 5 },
    tags: ['GitHub', 'AI工具', '热点复盘'],
    note: '预览数据：评论区在问部署步骤。',
  })
}

async function capturePerformanceSnapshot() {
  setError('')
  els.capturePerformance.disabled = true
  els.capturePerformance.textContent = '采集中…'
  try {
    if (!hasChromeRuntime()) {
      const snapshot = createPreviewPerformanceSnapshot()
      renderPerformanceSnapshot(snapshot)
      els.draftResult.textContent = '预览模式：已记录一条表现样例。真实安装后只读采集当前已发布页面指标，不会推广/刷量/再发布。'
      return
    }
    const scan = await chrome.runtime.sendMessage({
      type: 'socialPerformanceScan',
      payload: { platform: platform.id, url: activeTab?.url || '', title: currentDraft?.title || '' },
    })
    if (!scan?.ok) {
      setError(scan?.error || '表现采集失败，请确认当前页是已发布内容详情页。')
      return
    }
    const snapshot = normalizePerformanceSnapshot({
      ...(scan.result || {}),
      platform: platform.id,
      draft_id: currentDraft?.id || '',
      title: currentDraft?.title || scan.result?.title || '',
    })
    const payload = buildPerformanceSnapshotPayload({ platform, draft: currentDraft || {}, snapshot })
    const recorded = await chrome.runtime.sendMessage({ type: 'socialPerformanceRecord', payload })
    if (!recorded?.ok) {
      setError(recorded?.error || '表现已采集，但写入增长反馈池失败。')
      renderPerformanceSnapshot(snapshot)
      return
    }
    renderPerformanceSnapshot(recorded.json?.record || snapshot)
    els.connection.textContent = '表现已记录'
    els.draftResult.textContent = recorded.json?.next_action || '已记录表现复盘；只用于后续选题权重，不会触发发布或互动。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.capturePerformance.disabled = !platform.supported
    els.capturePerformance.textContent = '采表现'
  }
}

function renderXianyuDeliveryState(result, prefix = '') {
  const scan = result?.result || result?.scan || {}
  const signals = Array.isArray(scan.paidSignals) && scan.paidSignals.length
    ? `信号：${scan.paidSignals.join(' / ')}`
    : '信号：未看到已付款/待发货'
  const input = scan.inputReady ? '输入框：已找到' : '输入框：未找到'
  const send = scan.sendButtonReady ? '发送按钮：已找到' : '发送按钮：未找到'
  els.xianyuDeliveryState.textContent = [prefix, signals, input, send].filter(Boolean).join('\n')
}

async function scanXianyuDelivery() {
  setError('')
  els.xianyuDeliveryScan.disabled = true
  els.xianyuDeliveryScan.textContent = '检测中…'
  try {
    if (!hasChromeRuntime()) {
      renderXianyuDeliveryState({
        result: { paidSignals: ['买家已付款'], inputReady: true, sendButtonReady: true },
      }, '预览模式：当前聊天可发货。')
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'xianyuDeliveryScan', payload: {} })
    if (!result?.ok) {
      setError(result?.error || '检测当前闲鱼页面失败。')
      return
    }
    renderXianyuDeliveryState(result, result.result?.ready ? '当前聊天通过发货预检。' : '当前聊天还不能自动发货。')
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.xianyuDeliveryScan.disabled = platform.id !== 'xianyu'
    els.xianyuDeliveryScan.textContent = '检测当前聊天'
  }
}

async function sendXianyuDelivery() {
  setError('')
  els.xianyuDeliverySend.disabled = true
  els.xianyuDeliverySend.textContent = '发送中…'
  try {
    if (!hasChromeRuntime()) {
      renderXianyuDeliveryState({
        result: { paidSignals: ['买家已付款'], inputReady: true, sendButtonReady: true },
      }, '预览模式：会填入待发货卡密并点击发送。')
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'xianyuDeliverySend', payload: {} })
    if (!result?.ok) {
      renderXianyuDeliveryState(result, '已阻止发送。')
      setError(result?.error || '发送失败，请检查当前闲鱼聊天页。')
      return
    }
    renderXianyuDeliveryState(result, `已发送并标记本机记录 #${result.shipment?.id || ''}。`)
    els.draftResult.textContent = '发货完成：买家收到兑换网址和卡密后，继续让买家注册/登录、兑换、创建 API Key、导入 CC Switch 并调一次模型。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.xianyuDeliverySend.disabled = platform.id !== 'xianyu'
    els.xianyuDeliverySend.textContent = '发送待发货卡密'
  }
}

async function refreshXianyuDeliveryWatchState() {
  if (!els.xianyuDeliveryWatch) return
  try {
    if (!hasChromeRuntime()) {
      els.xianyuDeliveryWatch.textContent = '看守当前聊天页'
      return
    }
    const state = await chrome.runtime.sendMessage({ type: 'xianyuDeliveryWatchState', payload: {} })
    const enabled = Boolean(state?.watch?.enabled)
    const scope = state?.watch?.scope || 'current_chat'
    els.xianyuDeliveryWatch.textContent = enabled && scope === 'current_chat' ? '关闭看守' : '看守当前聊天页'
    els.xianyuDeliveryWatchAll.textContent = enabled && scope === 'all_open_xianyu_tabs' ? '关闭全局看守' : '看守所有闲鱼页'
    if (state?.watch?.last_result?.ok) {
      renderXianyuDeliveryState(
        state.watch.last_result,
        scope === 'all_open_xianyu_tabs' ? `全局看守运行中：已扫描 ${state.watch.tabCount || 0} 个闲鱼页。` : '看守模式最近一次已发货。',
      )
    }
  } catch {
    els.xianyuDeliveryWatch.textContent = '看守当前聊天页'
    els.xianyuDeliveryWatchAll.textContent = '看守所有闲鱼页'
  }
}

async function toggleXianyuDeliveryWatch(scope = 'current_chat') {
  setError('')
  const button = scope === 'all_open_xianyu_tabs' ? els.xianyuDeliveryWatchAll : els.xianyuDeliveryWatch
  button.disabled = true
  button.textContent = '处理中…'
  try {
    if (!hasChromeRuntime()) {
      renderXianyuDeliveryState({
        result: { paidSignals: ['买家已付款'], inputReady: true, sendButtonReady: true },
      }, scope === 'all_open_xianyu_tabs' ? '预览模式：会看守所有已打开闲鱼页。' : '预览模式：会看守当前聊天页，命中后自动发送一次。')
      return
    }
    const state = await chrome.runtime.sendMessage({ type: 'xianyuDeliveryWatchState', payload: {} })
    const enabled = Boolean(state?.watch?.enabled)
    const currentScope = state?.watch?.scope || 'current_chat'
    const nextEnabled = !(enabled && currentScope === scope)
    const result = await chrome.runtime.sendMessage({
      type: 'xianyuDeliveryWatchSet',
      payload: { enabled: nextEnabled, scope },
    })
    if (!result?.ok) {
      setError(result?.error || (scope === 'all_open_xianyu_tabs' ? '全局看守开启失败，请先打开闲鱼买家聊天页。' : '看守模式切换失败，请确认当前页是闲鱼买家聊天页。'))
      return
    }
    if (nextEnabled) {
      const prefix = scope === 'all_open_xianyu_tabs'
        ? `已开启全局看守：保持闲鱼聊天页打开（当前 ${result.watch?.tabCount || 0} 个）。`
        : '已开启看守：保持当前闲鱼买家聊天页打开。'
      renderXianyuDeliveryState(result.scan || {}, prefix)
      els.draftResult.textContent = scope === 'all_open_xianyu_tabs'
        ? '全局看守已开启：只在本机刚好 1 条待发货、页面看见已付款信号时发送，成功一次后自动关闭。'
        : '看守模式已开启：插件会定时检查当前聊天页；成功发货一次后自动关闭，避免重复发送。'
    } else {
      els.xianyuDeliveryState.textContent = '看守模式已关闭。'
      els.draftResult.textContent = '已关闭闲鱼发货看守。'
    }
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.xianyuDeliveryWatch.disabled = platform.id !== 'xianyu'
    els.xianyuDeliveryWatchAll.disabled = false
    await refreshXianyuDeliveryWatchState()
  }
}


function renderGrowthFeedback(summary = {}) {
  currentGrowthFeedback = normalizeGrowthFeedbackSummary(summary || {})
  els.growthPanel.innerHTML = ''
  const visible = currentGrowthFeedback.signals.length || currentGrowthFeedback.recommendations.length
  els.growthPanel.dataset.visible = visible ? 'true' : 'false'
  if (!visible) return
  for (const signal of currentGrowthFeedback.signals.slice(0, 3)) {
    const card = document.createElement('div')
    card.className = 'growth-card'
    card.innerHTML = `
      <strong></strong>
      <div class="growth-meta"></div>
      <div class="growth-meta"></div>
      <div class="tag-row"></div>
    `
    card.querySelector('strong').textContent = signal.title
    card.querySelectorAll('.growth-meta')[0].textContent = `赞 ${signal.metrics.likes} · 评 ${signal.metrics.comments} · 转 ${signal.metrics.shares} · 看 ${signal.metrics.impressions}`
    card.querySelectorAll('.growth-meta')[1].textContent = [signal.growth_feedback_reason, signal.learning].filter(Boolean).join(' · ')
    const tagRow = card.querySelector('.tag-row')
    for (const tag of signal.tags.slice(0, 3)) {
      const pill = document.createElement('span')
      pill.className = 'tag'
      pill.textContent = tag
      tagRow.appendChild(pill)
    }
    els.growthPanel.appendChild(card)
  }
  if (currentGrowthFeedback.recommendations.length) {
    const card = document.createElement('div')
    card.className = 'growth-card'
    card.innerHTML = '<strong>下一步建议</strong><div class="growth-meta"></div>'
    card.querySelector('.growth-meta').textContent = currentGrowthFeedback.recommendations.join(' · ')
    els.growthPanel.appendChild(card)
  }
}

function createPreviewGrowthFeedback() {
  return normalizeGrowthFeedbackSummary({
    platform: platform.id === 'unsupported' ? 'x' : platform.id,
    high_signal_count: 1,
    signals: [
      {
        title: 'GitHub 一周异常 Star 工具榜',
        tags: ['GitHub', 'AI工具'],
        metrics: { likes: 188, comments: 18, shares: 9, impressions: 18000 },
        learning: '继续放大 GitHub 工具榜 + 部署步骤。',
        growth_feedback_reason: '历史高信号：匹配 GitHub/AI工具',
      },
    ],
    recommendations: ['下一轮优先抓 GitHub/AI工具 相似热点。', '继续保持草稿审核。'],
  })
}

async function generateGrowthDrafts() {
  setError('')
  els.generateGrowthDrafts.disabled = true
  els.generateGrowthDrafts.textContent = '生成中…'
  try {
    if (!hasChromeRuntime()) {
      const preview = createPreviewDraft()
      preview.id = 'preview-growth-draft'
      preview.title = currentGrowthFeedback?.signals?.[0]?.title || preview.title
      preview.review_status = 'pending'
      preview.status = 'needs_review'
      renderDraftEditor(preview)
      els.draftResult.textContent = `预览模式：已根据增长复盘生成待审草稿《${preview.title}》。确认前不会自动发布。`
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialGrowthDraftsCreate',
      payload: { platform: platform.id === 'unsupported' ? 'x' : platform.id, limit: 3, settings },
    })
    if (!result?.ok) {
      setError(result?.error || '复盘生成待审草稿失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    const drafts = Array.isArray(result.json?.drafts) ? result.json.drafts : []
    if (drafts[0]) renderDraftEditor(drafts[0])
    els.connection.textContent = '待审草稿已生成'
    els.draftResult.textContent = drafts.length
      ? `已基于增长复盘生成 ${drafts.length} 条待审草稿；请逐条编辑/确认，系统不会自动发布或评论。`
      : '没有生成新草稿：请先刷新复盘或热点池。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.generateGrowthDrafts.disabled = false
    els.generateGrowthDrafts.textContent = '复盘生成草稿'
  }
}

async function refreshGrowthFeedback() {
  setError('')
  els.refreshGrowthFeedback.disabled = true
  els.refreshGrowthFeedback.textContent = '读取中…'
  try {
    if (!hasChromeRuntime()) {
      renderGrowthFeedback(createPreviewGrowthFeedback())
      els.draftResult.textContent = '预览模式：已加载增长复盘样例；复盘只影响选题建议，不会自动发布。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialGrowthFeedbackFetch',
      payload: { platform: platform.id, limit: 6, settings },
    })
    if (!result?.ok) {
      setError(result?.error || '读取增长复盘失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    renderGrowthFeedback(result.json || {})
    els.connection.textContent = '复盘已同步'
    const summary = normalizeGrowthFeedbackSummary(result.json || {})
    els.draftResult.textContent = summary.signals.length
      ? `已加载 ${summary.signals.length} 条高信号复盘；下一轮热点会参考这些结构，但不会自动发布。`
      : '暂无高信号复盘。先采集已发布内容表现，系统再学习选题权重。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.refreshGrowthFeedback.disabled = !platform.supported
    els.refreshGrowthFeedback.textContent = '看复盘'
  }
}


function summarizePageContext(context = {}) {
  const normalized = normalizePageContext(context || {})
  const primary = normalized.selection || normalized.trends[0] || normalized.headings[0] || normalized.title || normalized.bodyText
  const meta = [
    normalized.trends.length ? `趋势 ${normalized.trends.length}` : '',
    normalized.headings.length ? `标题 ${normalized.headings.length}` : '',
    normalized.selection ? '含选中文本' : '',
    normalized.bodyText ? '含正文摘要' : '',
  ].filter(Boolean).join(' · ')
  return {
    ...normalized,
    primary: primary || '当前页暂无可用上下文',
    meta: meta || '未识别到趋势/标题/正文信号',
    ready: Boolean(primary),
  }
}

function renderPageContextPanel(context = {}) {
  const summary = summarizePageContext(context)
  currentPageContext = summary.ready ? summary : null
  els.pageContextPanel.innerHTML = ''
  els.pageContextPanel.dataset.visible = summary.ready ? 'true' : 'false'
  if (!summary.ready) return
  const card = document.createElement('button')
  card.type = 'button'
  card.className = 'page-context-card'
  card.innerHTML = `
    <strong></strong>
    <div class="page-context-meta"></div>
    <div class="page-context-meta"></div>
    <div class="tag-row"></div>
  `
  card.querySelector('strong').textContent = summary.primary.slice(0, 96)
  const metas = card.querySelectorAll('.page-context-meta')
  metas[0].textContent = summary.meta
  metas[1].textContent = summary.bodyText || summary.title || '点击后根据当前页上下文生成待审草稿。'
  const tagRow = card.querySelector('.tag-row')
  for (const tag of [...summary.trends, ...summary.headings].slice(0, 4)) {
    const pill = document.createElement('span')
    pill.className = 'tag'
    pill.textContent = tag.slice(0, 24)
    tagRow.appendChild(pill)
  }
  card.addEventListener('click', () => void createDraftFromPageContext())
  els.pageContextPanel.appendChild(card)
}

function createPreviewPageContext() {
  if (platform.id === 'xhs') {
    return normalizePageContext({
      title: '小红书创作灵感',
      trends: ['夏日低卡冰饮', '通勤包整理'],
      headings: ['3分钟做出一杯夏日冰饮'],
      bodyText: '家人们，冷泡茶加柠檬真的适合收藏，适合做成步骤图文。',
    })
  }
  if (platform.id === 'xianyu') {
    return normalizePageContext({
      title: '闲鱼商品页',
      headings: ['MacBook Air M2 低价出'],
      bodyText: '买家问还能不能便宜一点，今天能不能发货，适合生成成交回复。',
    })
  }
  return normalizePageContext({
    title: 'X Home',
    trends: ['GitHub 一周异常 Star 工具榜'],
    headings: ['年轻创业者都在讨论 AI Agent 落地'],
    bodyText: '把热点拆成 3 步可执行清单：看需求、找工具、做最小部署。',
  })
}

async function scanPageContext() {
  setError('')
  els.scanPageContext.disabled = true
  els.scanPageContext.textContent = '扫描中…'
  try {
    if (!hasChromeRuntime()) {
      renderPageContextPanel(createPreviewPageContext())
      els.draftResult.textContent = '预览模式：已扫描当前页热点/上下文样例。点击卡片可生成待审草稿，不会发布。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialPageContextScan',
      payload: { platform: platform.id, limit: 12 },
    })
    if (!result?.ok) {
      setError(result?.error || '当前页上下文扫描失败，请确认页面已加载。')
      return
    }
    const context = normalizePageContext(result.result || {})
    renderPageContextPanel(context)
    els.connection.textContent = '当前页已扫描'
    els.draftResult.textContent = summarizePageContext(context).ready
      ? '已扫描当前页热点/上下文；点击卡片可生成待审草稿，仍不会自动发布。'
      : '当前页没有识别到可用上下文。请选中一段文本或打开趋势/详情页后再试。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.scanPageContext.disabled = !platform.supported
    els.scanPageContext.textContent = '扫当前页'
  }
}

async function createDraftFromPageContext() {
  const pageContext = currentPageContext
  if (!pageContext) return
  setError('')
  els.draftResult.textContent = '正在根据当前页上下文生成待审草稿…'
  try {
    if (!hasChromeRuntime()) {
      const draft = {
        ...createPreviewDraft(),
        id: 'preview-page-context-draft',
        title: pageContext.trends[0] || pageContext.headings[0] || pageContext.title || '当前页热点草稿',
        text: platform.id === 'xhs'
          ? `家人们，刚从当前页抓到一个很适合做收藏型图文的点：${pageContext.primary}\n\n可以这样写：\n1. 先给结论\n2. 拆 3 个步骤\n3. 配封面图\n4. 评论区补材料\n\n这只是待审草稿，不会自动发布。`
          : `刚从当前页抓到一个可以写的热点：${pageContext.primary}\n\n我会把它拆成 3 步：\n1. 这件事为什么突然热\n2. 普通人今天能做什么\n3. 哪些坑不要碰\n\n这只是待审草稿，不是投资建议，也不会自动发布。`,
        review_status: 'pending',
        source: 'chrome_extension_page_context_scan',
      }
      renderDraftEditor(draft)
      els.draftResult.textContent = `预览模式：已根据当前页上下文生成待审草稿《${draft.title}》。`
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialDraftCreate',
      payload: { settings, page_context: pageContext },
    })
    if (!result?.ok) {
      setError(result?.error || '根据当前页上下文生成草稿失败。')
      return
    }
    const draft = result.json?.draft || {}
    renderDraftEditor(draft)
    els.connection.textContent = '当前页草稿已同步'
    els.draftResult.textContent = `已根据当前页上下文生成待审草稿：${draft.title || pageContext.primary}\n确认前不会自动发布。`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

function renderInteractionList(signals = []) {
  currentInteractionSignals = normalizeInteractionSignals(signals)
  els.interactionList.innerHTML = ''
  els.interactionList.dataset.visible = currentInteractionSignals.length ? 'true' : 'false'
  currentInteractionSignals.slice(0, 4).forEach((signal, index) => {
    const card = document.createElement('button')
    card.type = 'button'
    card.className = 'interaction-card'
    card.innerHTML = `
      <strong></strong>
      <div class="interaction-meta"></div>
    `
    card.querySelector('strong').textContent = signal.text
    card.querySelector('.interaction-meta').textContent = [signal.author, signal.metric, signal.reply_angle, '只生成待审回复'].filter(Boolean).join(' · ')
    card.addEventListener('click', () => void createDraftFromInteraction(index))
    els.interactionList.appendChild(card)
  })
}

function createPreviewInteractions() {
  if (platform.id === 'xhs') {
    return normalizeInteractionSignals([
      { id: 'preview-xhs-comment', text: '这个夏日冷饮适合宿舍做吗？', author: '小红书用户', metric: '5赞', reply_angle: '补充低成本替代材料和收藏引导' },
    ])
  }
  if (platform.id === 'xianyu') {
    return normalizeInteractionSignals([
      { id: 'preview-xianyu-chat', text: '还能便宜点吗？今天能发货吗？', author: '闲鱼买家', metric: '高意向', reply_angle: '价格锚点 + 小让步 + 发货承诺边界' },
    ])
  }
  return normalizeInteractionSignals([
    { id: 'preview-x-comment', text: '这些 AI 工具怎么部署到自己的业务里？', author: 'young_builder', metric: '18 likes', reply_angle: '给 3 步部署检查清单，不承诺收益' },
  ])
}

async function scanInteractions() {
  setError('')
  els.scanInteractions.disabled = true
  els.scanInteractions.textContent = '扫描中…'
  try {
    if (!hasChromeRuntime()) {
      renderInteractionList(createPreviewInteractions())
      els.draftResult.textContent = '预览模式：已扫描互动样例。点击互动卡片只会生成待审回复草稿，不会评论。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialInteractionScan', payload: { platform: platform.id, limit: 8 } })
    if (!result?.ok) {
      setError(result?.error || '互动扫描失败，请确认当前页已打开评论/聊天区域。')
      return
    }
    const signals = normalizeInteractionSignals(result.result?.signals || [])
    renderInteractionList(signals)
    els.connection.textContent = '互动已扫描'
    els.draftResult.textContent = signals.length
      ? `已找到 ${signals.length} 条互动信号；点击卡片生成待审回复草稿，不会自动评论。`
      : '当前页没有找到可用互动信号。请打开评论区/聊天窗口后再试。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.scanInteractions.disabled = !platform.supported
    els.scanInteractions.textContent = '扫互动'
  }
}

async function createDraftFromInteraction(index) {
  const signal = currentInteractionSignals[index]
  if (!signal) return
  setError('')
  els.draftResult.textContent = `正在根据互动「${signal.text}」生成待审回复草稿…`
  try {
    if (!hasChromeRuntime()) {
      const draft = {
        ...createPreviewDraft(),
        id: `preview-interaction-${index}`,
        title: `互动回复：${signal.text.slice(0, 40)}`,
        text: platform.id === 'xianyu'
          ? `可以这样回：这个价格我已经压得比较低了，如果你今天拍，我可以优先发出。\n\n买家信号：${signal.text}\n\n注意：确认商品事实，不诱导站外交易。`
          : `可以这样回：\n\n${signal.text}\n\n我的建议是先拆成 3 步：\n1. 先确认真实需求\n2. 找一个最小可执行动作\n3. 做完再看反馈\n\n这条只是待审回复草稿，不会自动评论。`,
        review_status: 'pending',
        source: 'chrome_extension_interaction_scan',
      }
      renderDraftEditor(draft)
      els.draftResult.textContent = `预览模式：已生成互动待审草稿《${draft.title}》。`
      return
    }
    const payload = buildInteractionDraftPayload({ platform, signal, settings })
    const result = await chrome.runtime.sendMessage({ type: 'socialTrendDraftCreate', payload })
    if (!result?.ok) {
      setError(result?.error || '根据互动生成草稿失败。')
      return
    }
    const draft = result.json?.draft || {}
    renderDraftEditor(draft)
    els.connection.textContent = '互动草稿已同步'
    els.draftResult.textContent = `已根据互动生成待审回复草稿：${draft.title || signal.text}\n确认前不会自动评论或发布。`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

function renderTrendList(trends = []) {
  currentTrends = normalizeTrendItems(trends)
  els.trendList.innerHTML = ''
  els.trendList.dataset.visible = currentTrends.length ? 'true' : 'false'
  currentTrends.slice(0, 4).forEach((trend, index) => {
    const card = document.createElement('button')
    card.type = 'button'
    card.className = 'trend-card'
    card.innerHTML = `
      <strong></strong>
      <div class="trend-meta"></div>
      <div class="trend-meta trend-ops"></div>
      <div class="tag-row"></div>
    `
    card.querySelector('strong').textContent = trend.title
    card.querySelector('.trend-meta').textContent = `${trend.source}${trend.heat_reason ? ` · ${trend.heat_reason}` : ''}`
    card.querySelector('.trend-ops').textContent = [
      trend.content_angle,
      trend.growth_reason,
      trend.growth_feedback_reason,
      trend.risk_level ? `风险:${trend.risk_level}` : '',
      trend.platform_playbook,
    ].filter(Boolean).join(' · ')
    const tagRow = card.querySelector('.tag-row')
    for (const tag of trend.tags.slice(0, 3)) {
      const pill = document.createElement('span')
      pill.className = 'tag'
      pill.textContent = tag
      tagRow.appendChild(pill)
    }
    card.addEventListener('click', () => void createDraftFromTrend(index))
    els.trendList.appendChild(card)
  })
}

function scheduleStatusLabel(item) {
  if (item.status === 'awaiting_final_confirmation') return '到点待最终确认'
  if (item.status === 'ready_for_manual_publish') return '已确认，可手动发布'
  return '等待到点提醒'
}

function renderReviewPack(pack = {}) {
  currentReviewPack = normalizeReviewPack(pack)
  const persona = currentReviewPack.persona
  els.personaPanel.dataset.visible = 'true'
  els.personaName.textContent = persona.display_name || '待确认人设'
  els.personaState.textContent = currentReviewPack.persona_approved ? '已确认' : '待确认'
  els.personaSummary.textContent = [persona.one_liner, persona.positioning].filter(Boolean).join('\n') || '暂无人设说明。'
  els.personaTone.innerHTML = ''
  for (const item of persona.tone.slice(0, 6)) {
    const pill = document.createElement('span')
    pill.className = 'tag'
    pill.textContent = item
    els.personaTone.appendChild(pill)
  }
  els.personaApprove.disabled = currentReviewPack.persona_approved
  els.personaReject.disabled = false
  renderSampleList(currentReviewPack.samples)
}

function renderSampleList(samples = []) {
  els.sampleList.innerHTML = ''
  els.sampleList.dataset.visible = samples.length ? 'true' : 'false'
  samples.slice(0, 4).forEach((sample) => {
    const card = document.createElement('button')
    card.type = 'button'
    card.className = 'sample-card'
    card.innerHTML = `
      <strong></strong>
      <div class="sample-meta"></div>
    `
    const platformLabel = sample.platform === 'xhs' ? '小红书' : sample.platform === 'xianyu' ? '闲鱼' : 'X'
    card.querySelector('strong').textContent = sample.title || sample.text.slice(0, 36) || '未命名样稿'
    card.querySelector('.sample-meta').textContent = `${platformLabel} · ${sample.source || 'review-pack'} · ${sample.text.slice(0, 88)}`
    card.addEventListener('click', () => {
      renderDraftEditor({
        id: sample.id,
        platform: sample.platform,
        title: sample.title,
        text: sample.text,
        review_status: sample.review_status || 'pending',
        status: 'needs_review',
      })
      els.draftResult.textContent = `已载入样稿《${sample.title || sample.id}》；你可以继续编辑/确认，但不会自动发布。`
    })
    els.sampleList.appendChild(card)
  })
}

async function refreshReviewPack() {
  setError('')
  els.refreshReviewPack.disabled = true
  els.refreshReviewPack.textContent = '读取中…'
  try {
    if (!hasChromeRuntime()) {
      renderReviewPack(createPreviewReviewPack())
      els.draftResult.textContent = '预览模式：已加载人设和样稿确认包。确认人设不会触发发布。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialReviewPackFetch',
      payload: { limit: 6, settings },
    })
    if (!result?.ok) {
      setError(result?.error || '读取人设/样稿包失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    renderReviewPack(result.json || {})
    els.connection.textContent = '审核包已同步'
    els.draftResult.textContent = '已加载人设与样稿：请先确认方向，再逐条确认内容。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.refreshReviewPack.disabled = !platform.supported
    els.refreshReviewPack.textContent = '看人设'
  }
}

async function reviewPersonaDirection(approved) {
  setError('')
  const payload = buildPersonaReviewPayload({
    approved,
    reviewer: 'owner',
    notes: approved ? '插件内确认人设方向；每条内容仍需逐条审核。' : '插件内打回人设方向，需要重新生成样稿。',
  })
  try {
    if (!hasChromeRuntime()) {
      renderReviewPack({ ...(currentReviewPack || createPreviewReviewPack()), persona_approved: approved })
      els.draftResult.textContent = approved
        ? '预览模式：人设方向已确认；仍不会自动发布。'
        : '预览模式：人设方向已打回；不会恢复自动外发。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialPersonaReview', payload })
    if (!result?.ok) {
      setError(result?.error || '更新人设确认失败。')
      return
    }
    const refreshed = await chrome.runtime.sendMessage({ type: 'socialReviewPackFetch', payload: { limit: 6, settings } })
    renderReviewPack(refreshed?.ok ? refreshed.json : { ...(currentReviewPack || {}), persona_approved: approved })
    els.draftResult.textContent = approved
      ? '人设方向已确认；注意：每条内容仍需逐条审核和最终确认。'
      : '人设方向已打回；系统不会恢复自动外发。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

function renderScheduleList(items = []) {
  currentScheduleItems = normalizeScheduleItems(items)
  els.scheduleList.innerHTML = ''
  els.scheduleList.dataset.visible = currentScheduleItems.length ? 'true' : 'false'
  currentScheduleItems.slice(0, 6).forEach((item, index) => {
    const card = document.createElement('button')
    card.type = 'button'
    card.className = 'schedule-card'
    card.dataset.due = item.due ? 'true' : 'false'
    card.innerHTML = `
      <strong></strong>
      <div class="schedule-meta"></div>
    `
    const platformLabel = item.platform === 'xhs' ? '小红书' : item.platform === 'xianyu' ? '闲鱼' : 'X'
    card.querySelector('strong').textContent = item.title || '未命名排程'
    card.querySelector('.schedule-meta').textContent = `${platformLabel} · ${scheduleStatusLabel(item)} · ${item.scheduled_at || '未设置时间'}`
    card.addEventListener('click', () => loadDraftFromSchedule(index))
    els.scheduleList.appendChild(card)
  })
}

function loadDraftFromSchedule(index) {
  const item = currentScheduleItems[index]
  if (!item) return
  const draft = {
    ...item.draft,
    id: item.draft?.id || item.draft_id,
    platform: item.draft?.platform || item.platform,
    title: item.draft?.title || item.title,
    text: item.draft?.text || item.text_preview || '',
    review_status: item.draft?.review_status || item.review_status || 'approved',
    status: item.draft?.status || item.status,
    schedule_status: item.draft?.schedule_status || item.status,
    scheduled_at: item.scheduled_at,
  }
  renderDraftEditor(draft)
  els.draftResult.textContent = item.requires_final_confirmation
    ? `排程《${item.title}》已到点：请检查内容后点“最终确认”。仍不会自动发布。`
    : `已加载排程《${item.title}》：当前状态 ${scheduleStatusLabel(item)}。`
}

async function saveRunning(value) {
  if (!activeTab?.id) return
  const stored = await storageGet(['socialRunningByTab'])
  const runningByTab = stored.socialRunningByTab || {}
  if (value) runningByTab[String(activeTab.id)] = true
  else delete runningByTab[String(activeTab.id)]
  await storageSet({ socialRunningByTab: runningByTab })
  running = value
  render()
  await syncToCore()
}

function buildExtensionHeartbeat() {
  const manifest = hasChromeRuntime() && chrome.runtime.getManifest ? chrome.runtime.getManifest() : {}
  return {
    manifest_version: String(manifest.version || 'preview'),
    cc_delivery_helper_version: '2026-07-07-paid-page-fallback',
    capabilities: {
      xianyu_delivery_scan: true,
      xianyu_delivery_send: true,
      xianyu_confirm_shipment: true,
      xianyu_relist_item: true,
      current_chat_watch: true,
      all_open_xianyu_tabs_watch: true,
      target_tab_preflight: true,
      single_pending_global_gate: true,
      background_heartbeat: true,
      relist_queue_watch: true,
      paid_page_dispatch: true,
    },
  }
}

async function syncToCore() {
  setError('')
  const payload = {
    platform: platform.id,
    url: activeTab?.url || '',
    running,
    detected_platform: platform,
    settings,
    tasks: createDefaultTaskPreview(platform.id),
    extension: buildExtensionHeartbeat(),
  }
  try {
    if (!hasChromeRuntime()) {
      els.connection.textContent = '预览模式'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialStatusUpdate', payload })
    if (result?.ok) {
      els.connection.textContent = '已同步'
      return
    }
    els.connection.textContent = '本地未连'
    setError(result?.error || '无法同步到 OpenEverything，本地服务未启动时插件仍可保存设置。')
  } catch (err) {
    els.connection.textContent = '本地未连'
    setError(String(err))
  }
}

async function refreshCoreStrategySettings({ silent = false } = {}) {
  if (!hasChromeRuntime()) return
  try {
    const result = await chrome.runtime.sendMessage({
      type: 'socialStatusFetch',
      payload: { settings },
    })
    if (!result?.ok || !result.settings) {
      if (!silent) setError(result?.error || '暂时无法从 OpenEverything 中控同步运营打法。')
      return
    }
    settings = mergeSocialSettings(result.settings)
    await storageSet({ socialSettings: settings })
    render()
    els.connection.textContent = '打法已同步'
  } catch (err) {
    if (!silent) setError(err instanceof Error ? err.message : String(err))
  }
}

async function probeCurrentPageFields() {
  setError('')
  els.probePage.disabled = true
  els.probePage.textContent = '检测中…'
  try {
    if (!hasChromeRuntime()) {
      const fields = platform.id === 'xhs' ? '标题 / 正文' : platform.id === 'xianyu' ? '回复或描述' : '发帖输入框'
      els.draftResult.textContent = `预览模式：当前平台预计可检测 ${fields}；真实安装后会扫描页面输入框，不会点击发布按钮。`
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialPageProbe', payload: { platform: platform.id } })
    if (!result?.ok) {
      setError(result?.error || '检测填入点失败。')
      return
    }
    const available = result.result?.availableFields || []
    const syncLine = result.calibrationOk
      ? '校准结果已同步到 OpenEverything 中控。'
      : '本地检测成功，但未同步中控；请确认 OpenEverything 本地服务已启动。'
    els.connection.textContent = result.calibrationOk ? '校准已同步' : '本地校准'
    els.draftResult.textContent = available.length
      ? `已找到可填入位置：${available.map((field) => field.name || field.kind).join(' / ')}。\n可以生成草稿后点击“填入页面”，仍不会发布。`
      : '当前页面还没打开编辑框。请先点平台的发帖/发布/回复入口，再回插件检测。'
    els.draftResult.textContent += `\n${syncLine}`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.probePage.disabled = !platform.supported
    els.probePage.textContent = '检测填入点'
  }
}

function createPreviewTrends() {
  if (platform.id === 'xhs') {
    return normalizeTrendItems([
      {
        title: '夏日低卡冷饮突然又火了',
        source: 'preview_xhs',
        tags: ['生活', '冷饮', '学生党'],
        heat_reason: '适合做女性向图文教程和收藏型标题',
        call_to_action: '生成小红书图文草稿',
      },
      {
        title: '通勤包里最该留下的 5 件小东西',
        source: 'preview_life',
        tags: ['生活方式', '通勤', '省钱'],
        heat_reason: '轻量攻略，适合封面清单化',
      },
    ])
  }
  if (platform.id === 'xianyu') {
    return normalizeTrendItems([
      {
        title: '学生党开学前二手数码需求升温',
        source: 'preview_xianyu',
        tags: ['二手交易', '数码', '学生'],
        heat_reason: '适合优化标题和砍价回复',
        call_to_action: '生成闲鱼成交话术',
      },
    ])
  }
  return normalizeTrendItems([
    {
      title: 'GitHub 一周异常 Star 工具榜',
      source: 'preview_github_hn',
      tags: ['GitHub', 'AI工具', '创业者'],
      heat_reason: '年轻创业者可直接收藏和复用',
      call_to_action: '生成 X 热点短帖草稿',
    },
    {
      title: '美股回调之后，AI 龙头开始分化',
      source: 'preview_market',
      tags: ['美股', 'AI', '风险'],
      heat_reason: '适合做成可操作观察清单',
    },
  ])
}

async function refreshTrends() {
  setError('')
  els.refreshTrends.disabled = true
  els.refreshTrends.textContent = '抓取中…'
  try {
    if (!hasChromeRuntime()) {
      renderTrendList(createPreviewTrends())
      els.draftResult.textContent = '预览模式：已加载热点样例。真实安装后会读取本地/云端热点池。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialTrendsFetch',
      payload: { platform: platform.id, limit: 8, settings },
    })
    if (!result?.ok) {
      setError(result?.error || '读取热点池失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    const trends = normalizeTrendItems(result.json?.trends || [])
    renderTrendList(trends)
    els.connection.textContent = '热点已同步'
    els.draftResult.textContent = trends.length
      ? `已加载 ${trends.length} 个热点；点击任一热点即可生成待审草稿。`
      : '热点池暂无候选，请稍后再试。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.refreshTrends.disabled = !platform.supported
    els.refreshTrends.textContent = '抓热点'
  }
}

function createPreviewReviewPack() {
  return normalizeReviewPack({
    persona: {
      display_name: '热点抽象观察员',
      one_liner: '中英热点观察员 + 抽象吐槽 + 低风险追梗。',
      positioning: '不做 AI 教程号，追中文/英文趋势，用短、怪、有反差的表达制造互动。',
      tone: ['短', '怪', '有反差', '轻微阴阳怪气'],
      content_mix: { x: '70% 热点短吐槽', xhs: '生活化热点笔记', xianyu: '保持客服专业' },
    },
    persona_approved: false,
    samples: [
      {
        id: 'preview-sample-x',
        platform: 'x',
        title: '今天热搜最大的共同点',
        text: '大家不是在解决问题，是在给问题起一个更抽象的名字。',
        source: 'preview_review_pack',
      },
      {
        id: 'preview-sample-xhs',
        platform: 'xhs',
        title: '互联网新型精神状态：把生活过成副本',
        text: '今天刷到好几个热点，突然发现大家每天都在打一些没有任务奖励的支线。',
        source: 'preview_review_pack',
      },
    ],
    guardrails: ['不自动发布', '不批量评论', '不碰高风险热点'],
    content_verdict: '方向偏热点抽象涨粉号，但需要你先确认口味。',
  })
}

function createPreviewSchedule() {
  const base = {
    draft_id: currentDraft?.id || 'preview-x-scheduled',
    platform: platform.id === 'unsupported' ? 'x' : platform.id,
    title: currentDraft?.title || 'GitHub 一周异常 Star 工具榜',
    text_preview: currentDraft?.text || '预览模式排程提醒，不会自动发布。',
    scheduled_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    status: 'awaiting_final_confirmation',
    due: true,
    requires_final_confirmation: true,
    auto_publish_enabled: false,
    external_actions_locked: true,
    draft: {
      id: currentDraft?.id || 'preview-x-scheduled',
      platform: platform.id === 'unsupported' ? 'x' : platform.id,
      title: currentDraft?.title || 'GitHub 一周异常 Star 工具榜',
      text: currentDraft?.text || '到点提醒只负责把内容拉回编辑器；最后仍由你确认。',
      review_status: 'approved',
      status: 'awaiting_final_confirmation',
      schedule_status: 'awaiting_final_confirmation',
    },
  }
  return normalizeScheduleItems([base])
}

function createPreviewAssetPlan(platformId = platform.id) {
  if (platformId === 'xhs') {
    return {
      platform_style: '小红书女性向生活攻略图文',
      content_plan: {
        format: 'xhs_note',
        strategy_preset: settings.strategyPreset || 'xhs_lifestyle_tutorial',
        audience: '女性生活方式 / 学生党 / 收藏型用户',
        hook: '家人们，这个夏日冰饮真的建议收藏',
        growth_loop: '收藏率优先：封面结果感 + 步骤清单 + 评论区补材料。',
        structure: ['标题直给结果', '3 个步骤教程', '统一封面提示词', '收藏引导'],
      },
      image_plan: {
        auto_generate: false,
        image_model: settings.imageModel || 'gpt-image',
        cover_prompt: '小红书封面图，夏日低卡柠檬茶，明亮自然光，3:4 构图，留出中文标题区域，干净高级',
        asset_prompts: ['材料清单步骤图', '制作过程分镜图', '成品展示收藏引导图'],
      },
      format_checklist: ['标题 20 字左右', '正文 3-5 步', 'emoji 不堆砌', '发布前人工确认'],
      safety_checklist: ['不自动发布', '不写功效承诺', '不盗用真实品牌 Logo'],
      cost_route: { content_model: settings.contentModel, image_model: settings.imageModel, prefer_web_quota: true },
    }
  }
  if (platformId === 'xianyu') {
    return {
      platform_style: '闲鱼成交话术与商品优化',
      content_plan: {
        format: 'xianyu_reply_or_listing',
        strategy_preset: settings.strategyPreset || 'xianyu_deal_closer',
        audience: '闲鱼买家 / 卖家 / 二手数码用户',
        hook: '这个买家的真实需求可能是想确认成色和发货速度',
        growth_loop: '成交率优先：提高回复速度、降低疑虑、记录高转化话术。',
        structure: ['判断买家意图', '价格锚点', '成色证据', '小让步引导下单'],
      },
      image_plan: {
        auto_generate: false,
        image_model: settings.imageModel || 'none',
        cover_prompt: '闲鱼商品真实拍摄建议，白天自然光，清楚展示成色、配件和瑕疵，不生成虚假配件',
        asset_prompts: ['商品主图建议', '边角瑕疵细节图', '配件和包装清单图'],
      },
      format_checklist: ['先回应买家问题', '不写无法兑现承诺', '确认商品事实'],
      safety_checklist: ['不自动发布', '不要虚构成色', '不诱导站外交易'],
      cost_route: { content_model: settings.contentModel, image_model: settings.imageModel, prefer_web_quota: true },
    }
  }
  return {
    platform_style: 'X 年轻创业者热点实操短帖',
    content_plan: {
      format: 'x_hotspot_short_post',
      strategy_preset: settings.strategyPreset || 'x_wealth_frontier',
      audience: '大学生 / 年轻创业者 / AI 工具 / 美股人群',
      hook: '最近这个热点最有意思的不是新闻本身，而是机会信号',
      growth_loop: '评论率和收藏率优先：反差 hook + 可执行清单 + 低风险提问。',
      structure: ['反差 hook', '3步 可执行动作', '风险边界', '互动问题'],
    },
    image_plan: {
      auto_generate: false,
      image_model: settings.imageModel || 'gpt-image',
      cover_prompt: '可选信息图封面，黑白橙科技风，3 个行动步骤，适合 X 贴文配图，默认不强制配图',
      asset_prompts: ['3 步行动清单信息图', '机会信号 vs 风险边界对比图'],
    },
    format_checklist: ['开头有反差', '正文至少 3 个步骤', '包含风险边界', '发布前人工确认事实'],
    safety_checklist: ['不自动发布', '不构成投资建议', '不写确定收益'],
    cost_route: { content_model: settings.contentModel, image_model: settings.imageModel, prefer_web_quota: true },
  }
}

async function refreshScheduleQueue() {
  setError('')
  els.refreshSchedule.disabled = true
  els.refreshSchedule.textContent = '读取中…'
  try {
    if (!hasChromeRuntime()) {
      renderScheduleList(createPreviewSchedule())
      els.draftResult.textContent = '预览模式：已加载一个到点排程样例；点击卡片会回填到草稿编辑器。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialScheduleFetch',
      payload: { limit: 12, settings },
    })
    if (!result?.ok) {
      setError(result?.error || '读取排程队列失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    const items = normalizeScheduleItems(result.json?.queue || [])
    renderScheduleList(items)
    els.connection.textContent = '排程已同步'
    els.draftResult.textContent = items.length
      ? `已加载 ${items.length} 条排程，其中 ${items.filter((item) => item.requires_final_confirmation).length} 条需要最终确认。`
      : '暂无排程。先确认草稿，再点击“加入排程”。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.refreshSchedule.disabled = !platform.supported
    els.refreshSchedule.textContent = '看排程'
  }
}

async function createDraftFromCurrentPage() {
  setError('')
  els.draftResult.textContent = ''
  els.draft.disabled = true
  els.draft.textContent = '生成中…'
  try {
    if (!hasChromeRuntime()) {
      const draft = createPreviewDraft()
      renderDraftEditor(draft)
      els.draftResult.textContent = `预览模式：已生成样稿《${draft.title}》。真实安装后会读取当前页信号并写入待审草稿。`
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialDraftCreate',
      payload: { settings },
    })
    if (!result?.ok) {
      setError(result?.error || '生成待审草稿失败，请确认 OpenEverything 本地服务已启动。')
      return
    }
    const draft = result.json?.draft || {}
    els.connection.textContent = '草稿已同步'
    renderDraftEditor(draft)
    els.draftResult.textContent = `已生成待审草稿：${draft.title || draft.text || '未命名草稿'}\n你可以在这里先改标题/正文，确认后仍不会自动发布。`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  } finally {
    els.draft.disabled = !platform.supported
    els.draft.textContent = '根据当前页生成待审草稿'
  }
}

async function createDraftFromTrend(index) {
  const trend = currentTrends[index]
  if (!trend) return
  setError('')
  els.draftResult.textContent = `正在根据热点「${trend.title}」生成待审草稿…`
  try {
    if (!hasChromeRuntime()) {
      const draft = {
        ...createPreviewDraft(),
        id: `preview-trend-${index}`,
        title: trend.title,
        text: platform.id === 'xhs'
          ? `家人们，今天刷到「${trend.title}」，这个选题很适合做成收藏型图文。\n\n为什么值得写：${trend.growth_reason || trend.heat_reason || '当前热度正在上升'}。\n\n内容角度：${trend.content_angle || '结论前置 + 3 个步骤 + 统一封面 + 收藏引导'}。\n\n执行步骤：${trend.execution_steps?.join(' / ') || '标题、封面、正文、收藏引导'}。\n\n风险提示：${trend.risk_note || '发布前检查敏感词。'}`
          : `我会把「${trend.title}」当成今天的一个机会信号。\n\n可执行角度：${trend.content_angle || trend.heat_reason || '先看热度，再拆成可操作清单'}。\n\n平台打法：${trend.platform_playbook || '反差开头 + 3 个可操作步骤 + 讨论问题'}。\n\n今天能做：${trend.execution_steps?.join(' / ') || '1）收藏相关工具 2）观察真实需求 3）避免把热点写成空泛观点'}。\n\n风险提示：${trend.risk_note || '不要写收益承诺，不要变成投资建议。'}`,
      }
      renderDraftEditor(draft)
      els.draftResult.textContent = `预览模式：已根据热点生成样稿《${draft.title}》。`
      return
    }
    const payload = buildTrendDraftPayload({ platform, trend, settings })
    const result = await chrome.runtime.sendMessage({ type: 'socialTrendDraftCreate', payload })
    if (!result?.ok) {
      setError(result?.error || '根据热点生成草稿失败。')
      return
    }
    const draft = result.json?.draft || {}
    renderDraftEditor(draft)
    els.connection.textContent = '草稿已同步'
    els.draftResult.textContent = `已根据热点生成待审草稿：${draft.title || trend.title}\n确认前不会自动发布。`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

function createPreviewDraft() {
  if (platform.id === 'xhs') {
    return {
      id: 'preview-xhs',
      platform: 'xhs',
      title: '3分钟做出一杯夏日冰饮',
      text: '家人们，今天这个低卡柠檬茶真的很适合夏天续命 🍋\n\n1. 柠檬片先用盐搓洗\n2. 加冰块、乌龙茶和一点蜂蜜\n3. 最后撒薄荷叶，拍照也很好看\n\n#夏日冷饮 #学生党省钱 #低卡饮品',
      review_status: 'pending',
      ...createPreviewAssetPlan('xhs'),
    }
  }
  if (platform.id === 'xianyu') {
    return {
      id: 'preview-xianyu',
      platform: 'xianyu',
      title: '砍价回复建议',
      text: '可以小刀一点，但这个成色和配件都比较完整。你今天拍的话，我这边优先给你发出。',
      review_status: 'pending',
      ...createPreviewAssetPlan('xianyu'),
    }
  }
  return {
    id: 'preview-x',
    platform: 'x',
    title: '美股回调别慌',
    text: '就业数据超预期，短线回调更像技术修正。\n\n今天能做的不是追涨杀跌，而是列一个观察清单：\n1. 大盘是否守住关键均线\n2. AI 龙头有没有放量止跌\n3. 美债收益率是否继续上行\n\n不是投资建议，只是把噪音拆成可操作检查表。',
    review_status: 'pending',
    ...createPreviewAssetPlan('x'),
  }
}

async function saveDraftEdits() {
  if (!currentDraft?.id) return
  setError('')
  const payload = {
    draft_id: currentDraft.id,
    title: els.draftTitle.value,
    text: els.draftText.value,
  }
  try {
    if (!hasChromeRuntime()) {
      currentDraft = { ...currentDraft, title: payload.title, text: payload.text }
      els.draftResult.textContent = '预览模式：已在本地更新草稿显示。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialDraftUpdate', payload })
    if (!result?.ok) {
      setError(result?.error || '保存草稿失败。')
      return
    }
    renderDraftEditor(result.json?.draft || currentDraft)
    els.draftResult.textContent = '修改已保存，草稿仍处于待确认状态。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

async function reviewDraft(approved) {
  if (!currentDraft?.id) return
  setError('')
  try {
    if (!hasChromeRuntime()) {
      const reviewedDraft = {
        ...currentDraft,
        review_status: approved ? 'approved' : 'rejected',
        status: approved ? 'approved' : 'rejected',
      }
      renderDraftEditor(reviewedDraft)
      els.draftResult.textContent = approved
        ? '预览模式：确认内容后仍不会自动发布。'
        : '预览模式：草稿已打回。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialDraftReview',
      payload: { draft_id: currentDraft.id, approved, reviewer: 'owner' },
    })
    if (!result?.ok) {
      setError(result?.error || '审核草稿失败。')
      return
    }
    renderDraftEditor(result.json?.draft || currentDraft)
    els.draftResult.textContent = approved
      ? '内容已确认；系统仍不会自动发布，最终外发需要后续明确授权。'
      : '草稿已打回，不会进入发布确认。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

async function scheduleDraftForLater() {
  if (!currentDraft?.id) return
  setError('')
  const payload = buildScheduleDraftPayload({
    platform,
    draft: {
      ...currentDraft,
      title: els.draftTitle.value,
      text: els.draftText.value,
    },
  })
  if (payload.requiresReview) {
    setError('排程前请先点击“确认内容”。未确认草稿不会进入发布时间表。')
    return
  }
  try {
    if (!hasChromeRuntime()) {
      const scheduled = {
        ...currentDraft,
        title: els.draftTitle.value,
        text: els.draftText.value,
        status: 'scheduled',
        schedule_status: 'queued_for_owner_publish',
        scheduled_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      }
      renderDraftEditor(scheduled)
      renderScheduleList([{
        draft_id: scheduled.id,
        platform: scheduled.platform,
        title: scheduled.title,
        text_preview: scheduled.text,
        scheduled_at: scheduled.scheduled_at,
        status: scheduled.schedule_status,
        draft: scheduled,
      }])
      els.draftResult.textContent = '预览模式：已加入排程样例；到点仍需最终确认。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialDraftSchedule', payload })
    if (!result?.ok) {
      setError(result?.error || '加入排程失败。')
      return
    }
    renderDraftEditor(result.json?.draft || currentDraft)
    renderScheduleList(result.json?.schedule_item ? [result.json.schedule_item] : currentScheduleItems)
    els.draftResult.textContent = result.json?.next_action || '已加入排程；到点仍需最终确认，不会自动发布。'
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

async function finalConfirmScheduledDraft() {
  if (!currentDraft?.id) return
  setError('')
  if (currentDraft.schedule_status !== 'awaiting_final_confirmation') {
    setError('只有到点后的排程才能最终确认。请先点击“看排程”，选择到点卡片。')
    return
  }
  try {
    if (!hasChromeRuntime()) {
      const confirmed = { ...currentDraft, status: 'ready_for_manual_publish', schedule_status: 'ready_for_manual_publish' }
      renderDraftEditor(confirmed)
      els.draftResult.textContent = '预览模式：最终确认完成，但仍不会自动发布。'
      return
    }
    const result = await chrome.runtime.sendMessage({
      type: 'socialDraftFinalConfirm',
      payload: { draft_id: currentDraft.id, reviewer: 'owner' },
    })
    if (!result?.ok) {
      setError(result?.error || '最终确认失败。')
      return
    }
    renderDraftEditor(result.json?.draft || currentDraft)
    els.draftResult.textContent = result.json?.next_action || '最终确认完成；请在真实页面手动点击发布，或后续显式授权发布器。'
    await refreshScheduleQueue()
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

async function autofillDraftIntoPage() {
  if (!currentDraft?.id) return
  setError('')
  const payload = buildAutofillPayload({
    platform,
    draft: {
      ...currentDraft,
      title: els.draftTitle.value,
      text: els.draftText.value,
    },
  })
  if (platform.id === 'xhs') {
    payload.bodyText = els.draftText.value
  }
  if (!payload.text) {
    setError('草稿正文为空，无法填入页面。')
    return
  }
  try {
    if (!hasChromeRuntime()) {
      els.draftResult.textContent = '预览模式：安装为 Chrome 插件后，会把草稿填入当前页面输入框，但不会发布。'
      return
    }
    const result = await chrome.runtime.sendMessage({ type: 'socialDraftAutofill', payload })
    if (!result?.ok) {
      setError(result?.error || '自动填入失败，请确认当前页面已打开编辑框。')
      return
    }
    const detail = result.result?.filled
      ? `已填入 ${result.result.platformLabel || platform.label} 页面输入框。`
      : '没有找到可填入的输入框。'
    els.draftResult.textContent = `${detail}\n安全锁仍生效：没有点击发布/发送/评论按钮。`
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err))
  }
}

els.start.addEventListener('click', () => void saveRunning(true))
els.pause.addEventListener('click', () => void saveRunning(false))
els.stop.addEventListener('click', () => void saveRunning(false))
els.sync.addEventListener('click', () => void syncToCore())
els.probePage.addEventListener('click', () => void probeCurrentPageFields())
els.draft.addEventListener('click', () => void createDraftFromCurrentPage())
els.refreshTrends.addEventListener('click', () => void refreshTrends())
els.scanPageContext.addEventListener('click', () => void scanPageContext())
els.scanInteractions.addEventListener('click', () => void scanInteractions())
els.capturePerformance.addEventListener('click', () => void capturePerformanceSnapshot())
els.refreshGrowthFeedback.addEventListener('click', () => void refreshGrowthFeedback())
els.generateGrowthDrafts.addEventListener('click', () => void generateGrowthDrafts())
els.refreshReviewPack.addEventListener('click', () => void refreshReviewPack())
els.xianyuDeliveryScan.addEventListener('click', () => void scanXianyuDelivery())
els.xianyuDeliverySend.addEventListener('click', () => void sendXianyuDelivery())
els.xianyuDeliveryWatch.addEventListener('click', () => void toggleXianyuDeliveryWatch('current_chat'))
els.xianyuDeliveryWatchAll.addEventListener('click', () => void toggleXianyuDeliveryWatch('all_open_xianyu_tabs'))
els.personaApprove.addEventListener('click', () => void reviewPersonaDirection(true))
els.personaReject.addEventListener('click', () => void reviewPersonaDirection(false))
els.refreshSchedule.addEventListener('click', () => void refreshScheduleQueue())
els.draftSave.addEventListener('click', () => void saveDraftEdits())
els.draftAutofill.addEventListener('click', () => void autofillDraftIntoPage())
els.draftSchedule.addEventListener('click', () => void scheduleDraftForLater())
els.draftFinalConfirm.addEventListener('click', () => void finalConfirmScheduledDraft())
els.draftApprove.addEventListener('click', () => void reviewDraft(true))
els.draftReject.addEventListener('click', () => void reviewDraft(false))
els.webModelCopy.addEventListener('click', () => void copyWebModelPrompt())
els.webModelOpen.addEventListener('click', () => void openWebModelProvider())
els.openOptions.addEventListener('click', (event) => {
  event.preventDefault()
  if (globalThis.chrome?.runtime?.openOptionsPage) {
    void chrome.runtime.openOptionsPage()
    return
  }
  globalThis.location.href = './options.html'
})
els.attachRelay.addEventListener('click', (event) => {
  event.preventDefault()
  if (!hasChromeRuntime()) {
    setError('预览模式下无法连接 Browser Relay；安装为 Chrome 插件后可用。')
    return
  }
  void chrome.runtime.sendMessage({ type: 'toggleRelayForActiveTab' })
})

void loadState()
void refreshXianyuDeliveryWatchState()
renderDraftEditor(null)

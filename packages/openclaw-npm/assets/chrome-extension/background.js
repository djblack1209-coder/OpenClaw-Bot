import { buildRelayWsUrl, isRetryableReconnectError, reconnectDelayMs } from './background-utils.js'
import { buildDraftCreatePayload, buildPageProbePayload, buildPageProbeReportPayload, buildPerformanceSnapshotPayload, buildSocialApiUrl, buildTrendDraftPayload, detectSocialPlatform, mergeSocialSettings, syncSocialSettingsFromStatus } from './social-core.js'
import {
  runSocialFieldPlanInPage,
  runSocialInteractionScanInPage,
  runSocialPageContextScanInPage,
  runSocialPerformanceScanInPage,
  runXianyuRelistItemInPage,
  runXianyuConfirmShipmentInPage,
  runXianyuDeliveryDraftCleanupInPage,
  runXianyuDeliveryFillAndSendInPage,
  runXianyuDeliveryScanInPage,
} from './social-page-runner.js'

const DEFAULT_PORT = 18792
const XIANYU_ADMIN_BASE_URL = 'http://127.0.0.1:18800'
const XIANYU_DELIVERY_WATCH_ALARM = 'xianyu-delivery-watch'
const XIANYU_RELIST_WATCH_ALARM = 'xianyu-relist-watch'

const BADGE = {
  on: { text: 'ON', color: '#FF5A36' },
  off: { text: '', color: '#000000' },
  connecting: { text: '…', color: '#F59E0B' },
  error: { text: '!', color: '#B91C1C' },
}

/** @type {WebSocket|null} */
let relayWs = null
/** @type {Promise<void>|null} */
let relayConnectPromise = null
let relayGatewayToken = ''
/** @type {string|null} */
let relayConnectRequestId = null

let nextSession = 1
let xianyuDeliveryWatchInFlight = false

/** @type {Map<number, {state:'connecting'|'connected', sessionId?:string, targetId?:string, attachOrder?:number}>} */
const tabs = new Map()
/** @type {Map<string, number>} */
const tabBySession = new Map()
/** @type {Map<string, number>} */
const childSessionToTab = new Map()

/** @type {Map<number, {resolve:(v:any)=>void, reject:(e:Error)=>void}>} */
const pending = new Map()

// Per-tab operation locks prevent double-attach races.
/** @type {Set<number>} */
const tabOperationLocks = new Set()

// Tabs currently in a detach/re-attach cycle after navigation.
/** @type {Set<number>} */
const reattachPending = new Set()

// Reconnect state for exponential backoff.
let reconnectAttempt = 0
let reconnectTimer = null

function nowStack() {
  try {
    return new Error().stack || ''
  } catch {
    return ''
  }
}

async function getRelayPort() {
  const stored = await chrome.storage.local.get(['relayPort'])
  const raw = stored.relayPort
  const n = Number.parseInt(String(raw || ''), 10)
  if (!Number.isFinite(n) || n <= 0 || n > 65535) return DEFAULT_PORT
  return n
}

async function getGatewayToken() {
  const stored = await chrome.storage.local.get(['gatewayToken'])
  const token = String(stored.gatewayToken || '').trim()
  if (token) return token
  const runtimeConfig = await getRuntimeConfig()
  return String(runtimeConfig.gatewayToken || '').trim()
}

let runtimeConfigCache = null
async function getRuntimeConfig() {
  if (runtimeConfigCache) return runtimeConfigCache
  runtimeConfigCache = {}
  try {
    const response = await fetch(chrome.runtime.getURL('runtime-config.json'), { cache: 'no-store' })
    if (!response.ok) return runtimeConfigCache
    const json = await response.json().catch(() => null)
    if (json && typeof json === 'object') runtimeConfigCache = json
  } catch {
    runtimeConfigCache = {}
  }
  return runtimeConfigCache
}

async function socialApiAuthHeaders(extra = {}) {
  const token = await getGatewayToken()
  return {
    ...(token ? { 'x-api-token': token } : {}),
    ...(extra || {}),
  }
}

async function getSocialSettings() {
  const stored = await chrome.storage.local.get(['socialSettings'])
  return mergeSocialSettings(stored.socialSettings || {})
}

function buildExtensionHeartbeat() {
  const manifest = chrome.runtime?.getManifest ? chrome.runtime.getManifest() : {}
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

async function heartbeatSocialExtensionStatus(reason = 'background') {
  const activeTab = await getActiveTabForSocial().catch(() => null)
  const watch = await getXianyuDeliveryWatchState().catch(() => ({ enabled: false }))
  const platform = detectSocialPlatform(activeTab?.url || '')
  const payload = {
    platform: platform.id,
    url: activeTab?.url || '',
    running: Boolean(watch?.enabled),
    detected_platform: platform,
    tasks: [
      watch?.enabled ? '闲鱼发货看守运行中' : '后台心跳在线',
      '待发货时只在已付款/待发货聊天页发送',
      '发送成功后自动标记本机履约状态',
    ],
    extension: buildExtensionHeartbeat(),
    heartbeat_reason: reason,
  }
  return updateSocialExtensionStatus(payload)
}

async function fetchXianyuAdminApi(path, options = {}) {
  const token = await getGatewayToken()
  if (!token) {
    return { ok: false, status: 401, error: '请先在插件高级设置里填写本机 Token。' }
  }
  const headers = {
    'x-api-token': token,
    ...(options.body ? { 'content-type': 'application/json' } : {}),
    ...(options.headers || {}),
  }
  const response = await fetch(`${XIANYU_ADMIN_BASE_URL}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body,
    signal: AbortSignal.timeout(options.timeoutMs || 5000),
  })
  const contentType = String(response.headers.get('content-type') || '')
  const json = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      error: json?.detail || json?.error || `闲鱼本机操作台返回 ${response.status}`,
      json,
    }
  }
  return { ok: true, status: response.status, json }
}

async function fetchSocialExtensionStatus(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/status'), {
    method: 'GET',
    headers: await socialApiAuthHeaders(),
    signal: AbortSignal.timeout(3000),
  })
  const contentType = String(response.headers.get('content-type') || '')
  const json = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  const syncedSettings = syncSocialSettingsFromStatus(settings, json || {})
  await chrome.storage.local.set({ socialSettings: syncedSettings })
  return { ok: true, status: response.status, json, settings: syncedSettings }
}

async function updateSocialExtensionStatus(payload) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/status'), {
    method: 'POST',
    headers: await socialApiAuthHeaders({ 'content-type': 'application/json' }),
    body: JSON.stringify({ ...(payload || {}), settings }),
    signal: AbortSignal.timeout(3000),
  })
  const contentType = String(response.headers.get('content-type') || '')
  const json = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok) {
    return { ok: false, status: response.status, error: json?.detail || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function getActiveTabForSocial() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab || null
}

async function collectActiveTabPageContext(tabId) {
  if (!tabId || !chrome.scripting?.executeScript) {
    return { title: '', selection: '', headings: [], trends: [], bodyText: '' }
  }
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: runSocialPageContextScanInPage,
      args: [{ action: 'scan_page_context' }],
    })
    return result?.result || {}
  } catch (err) {
    return {
      title: '',
      selection: '',
      headings: [],
      trends: [],
      bodyText: '',
      error: err instanceof Error ? err.message : String(err),
    }
  }
}

async function createSocialDraftFromActiveTab(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab) return { ok: false, status: 0, error: 'No active tab' }
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const platform = detectSocialPlatform(tab.url || '')
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法生成运营草稿。' }
  }
  const pageContext = payload.page_context || await collectActiveTabPageContext(tab.id)
  const requestPayload = buildDraftCreatePayload({ platform, tab, settings, pageContext })
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/drafts'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(requestPayload),
    signal: AbortSignal.timeout(5000),
  })
  const contentType = String(response.headers.get('content-type') || '')
  const json = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function fetchSocialTrends(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const tab = await getActiveTabForSocial()
  const platform = payload.platform
    ? { id: String(payload.platform || 'x') }
    : detectSocialPlatform(tab?.url || '')
  const params = new URLSearchParams({
    platform: platform.id || 'x',
    limit: String(Math.min(12, Math.max(1, Number(payload.limit || 8)))),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/trends?${params.toString()}`), {
    method: 'GET',
    signal: AbortSignal.timeout(7000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function fetchSocialGrowthFeedback(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const tab = await getActiveTabForSocial()
  const platform = payload.platform
    ? { id: String(payload.platform || 'x') }
    : detectSocialPlatform(tab?.url || '')
  const params = new URLSearchParams({
    platform: platform.id || 'x',
    limit: String(Math.min(12, Math.max(1, Number(payload.limit || 6)))),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/growth-feedback?${params.toString()}`), {
    method: 'GET',
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function createSocialGrowthDrafts(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const tab = await getActiveTabForSocial()
  const platform = payload.platform
    ? String(payload.platform || 'x')
    : detectSocialPlatform(tab?.url || '').id || 'x'
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/growth-drafts'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      platform,
      limit: Math.min(6, Math.max(1, Number(payload.limit || 3))),
      auto_publish_enabled: false,
      external_actions_locked: true,
      publishIntent: false,
    }),
    signal: AbortSignal.timeout(7000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function fetchSocialReviewPack(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const params = new URLSearchParams({
    limit: String(Math.min(12, Math.max(1, Number(payload.limit || 6)))),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/review-pack?${params.toString()}`), {
    method: 'GET',
    signal: AbortSignal.timeout(7000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function reviewSocialPersona(payload = {}) {
  const settings = await getSocialSettings()
  const params = new URLSearchParams({
    approved: payload.approved ? 'true' : 'false',
    reviewer: String(payload.reviewer || 'owner'),
    notes: String(payload.notes || ''),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/persona-review?${params.toString()}`), {
    method: 'POST',
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function fetchSocialSchedule(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const params = new URLSearchParams({
    limit: String(Math.min(100, Math.max(1, Number(payload.limit || 12)))),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/schedule?${params.toString()}`), {
    method: 'GET',
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function createSocialDraftFromTrend(payload = {}) {
  const tab = await getActiveTabForSocial()
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const platform = payload.detected_platform || detectSocialPlatform(tab?.url || '')
  const requestPayload = payload.page_context
    ? { ...payload, settings }
    : buildTrendDraftPayload({ platform, trend: payload.trend || payload, settings })
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/drafts'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(requestPayload),
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function updateSocialDraft(payload = {}) {
  const settings = await getSocialSettings()
  const draftId = String(payload.draft_id || payload.id || '').trim()
  if (!draftId) return { ok: false, status: 0, error: 'draft_id required' }
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/drafts/${encodeURIComponent(draftId)}`), {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      title: String(payload.title || ''),
      text: String(payload.text || ''),
    }),
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function reviewSocialDraft(payload = {}) {
  const settings = await getSocialSettings()
  const draftId = String(payload.draft_id || payload.id || '').trim()
  if (!draftId) return { ok: false, status: 0, error: 'draft_id required' }
  const params = new URLSearchParams({
    approved: payload.approved === false ? 'false' : 'true',
    reviewer: String(payload.reviewer || 'owner'),
  })
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/drafts/${encodeURIComponent(draftId)}/review?${params.toString()}`), {
    method: 'POST',
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function scheduleSocialDraft(payload = {}) {
  const settings = await getSocialSettings()
  const draftId = String(payload.draft_id || payload.id || '').trim()
  if (!draftId) return { ok: false, status: 0, error: 'draft_id required' }
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/drafts/${encodeURIComponent(draftId)}/schedule`), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      scheduled_at: String(payload.scheduled_at || ''),
      reviewer: String(payload.reviewer || 'owner'),
    }),
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}


async function finalConfirmSocialDraft(payload = {}) {
  const settings = await getSocialSettings()
  const draftId = String(payload.draft_id || payload.id || '').trim()
  if (!draftId) return { ok: false, status: 0, error: 'draft_id required' }
  const response = await fetch(buildSocialApiUrl(settings, `social/extension/drafts/${encodeURIComponent(draftId)}/final-confirm`), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ reviewer: String(payload.reviewer || 'owner') }),
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function autofillSocialDraft(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  const requestedPlatform = String(payload.platform || '').trim()
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法填入。' }
  }
  if (requestedPlatform && requestedPlatform !== platform.id) {
    return { ok: false, status: 0, error: `草稿平台是 ${requestedPlatform}，当前标签页是 ${platform.id}，已阻止误填。` }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const safePayload = {
    platform: platform.id,
    title: String(payload.title || '').slice(0, 120),
    text: String(payload.text || payload.bodyText || '').slice(0, 3000),
    bodyText: String(payload.bodyText || payload.text || '').slice(0, 2800),
    fields: Array.isArray(payload.fields) ? payload.fields : [],
    publishIntent: false,
    allowButtonClick: false,
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runSocialFieldPlanInPage,
    args: [safePayload],
  })
  return { ok: true, status: 200, result: result?.result || { filled: false, platform: platform.id } }
}

async function reportSocialPageProbe(payload = {}) {
  const settings = await getSocialSettings()
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/page-probe'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload || {}),
    signal: AbortSignal.timeout(3000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

async function probeSocialPageFields(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法检测填入点。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const probePayload = buildPageProbePayload({ platformId: platform.id })
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runSocialFieldPlanInPage,
    args: [{ ...probePayload, ...(payload || {}) }],
  })
  const probeResult = result?.result || { ready: false, platform: platform.id, reason: 'no_probe_result' }
  const reportPayload = buildPageProbeReportPayload({ platform, tab, probeResult })
  const calibration = await reportSocialPageProbe(reportPayload).catch((err) => ({
    ok: false,
    status: 0,
    error: err instanceof Error ? err.message : String(err),
  }))
  return {
    ok: true,
    status: 200,
    result: probeResult,
    calibration,
    calibrationOk: Boolean(calibration?.ok),
  }
}



async function scanSocialPageContext(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法扫描当前页上下文。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runSocialPageContextScanInPage,
    args: [{
      ...(payload || {}),
      platform: platform.id,
      url: tab.url || payload.url || '',
      title: tab.title || payload.title || '',
      action: 'scan_page_context',
      publishIntent: false,
    }],
  })
  return {
    ok: true,
    status: 200,
    result: result?.result || {
      ready: false,
      platform: platform.id,
      action: 'scan_page_context',
      headings: [],
      trends: [],
      bodyText: '',
      auto_publish_enabled: false,
      external_actions_locked: true,
      publishIntent: false,
      reason: 'no_scan_result',
    },
  }
}

async function scanSocialInteractions(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法扫描互动。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runSocialInteractionScanInPage,
    args: [{
      ...(payload || {}),
      platform: platform.id,
      limit: Math.min(12, Math.max(1, Number(payload.limit || 8))),
    }],
  })
  return {
    ok: true,
    status: 200,
    result: result?.result || {
      ready: false,
      platform: platform.id,
      action: 'scan_interactions',
      signals: [],
      auto_reply_enabled: false,
      auto_publish_enabled: false,
      external_actions_locked: true,
      reason: 'no_scan_result',
    },
  }
}



async function scanSocialPerformance(payload = {}) {
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (!platform.supported) {
    return { ok: false, status: 0, error: '当前标签页不是 X / 小红书 / 闲鱼，无法采集表现。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runSocialPerformanceScanInPage,
    args: [{
      ...(payload || {}),
      platform: platform.id,
      url: tab.url || payload.url || '',
      title: tab.title || payload.title || '',
    }],
  })
  return {
    ok: true,
    status: 200,
    result: result?.result || {
      ready: false,
      platform: platform.id,
      action: 'scan_performance',
      metrics: {},
      auto_publish_enabled: false,
      external_actions_locked: true,
      reason: 'no_scan_result',
    },
  }
}

async function scanXianyuDeliveryTab(tab, payload = {}) {
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (platform.id !== 'xianyu') {
    return { ok: false, status: 0, error: '请先切到闲鱼聊天/待发货页面。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runXianyuDeliveryScanInPage,
    args: [{ ...(payload || {}), url: tab.url || '', title: tab.title || '' }],
  })
  return {
    ok: true,
    status: 200,
    result: result?.result || {
      ready: false,
      platform: 'xianyu',
      action: 'cc_delivery_scan',
      reason: 'no_scan_result',
    },
  }
}

async function scanXianyuDeliveryPage(payload = {}) {
  const tab = await getActiveTabForSocial()
  return scanXianyuDeliveryTab(tab, payload)
}

function isXianyuTab(tab) {
  return Boolean(tab?.id && detectSocialPlatform(tab.url || '').id === 'xianyu')
}

async function getOpenXianyuTabs() {
  const allTabs = await chrome.tabs.query({})
  return allTabs.filter(isXianyuTab).slice(0, 12)
}

async function assertSinglePendingDeliveryForGlobalWatch() {
  const status = await fetchXianyuAdminApi('/api/status')
  if (!status.ok) return status
  const pendingRescue = Number(status.json?.cc_shipments?.pending_rescue || 0)
  if (pendingRescue !== 1) {
    return {
      ok: false,
      status: 409,
      error: `全局看守只在“刚好 1 条待发货”时启用；当前待处理 ${pendingRescue} 条，请改用对应聊天页手动看守，避免发错买家。`,
    }
  }
  return { ok: true, status: 200, pendingRescue }
}

function normalizeXianyuItemIdFromUrl(url = '') {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    for (const key of ['itemId', 'item_id', 'itemIdStr', 'item_id_str', 'id']) {
      const value = parsed.searchParams.get(key)
      if (value && /^[A-Za-z0-9_-]{4,120}$/.test(value)) return value
    }
  } catch {
    // 当前标签可能是闲鱼短链接或 App 跳转页，直接回退到完整 URL。
  }
  return raw
}

async function ensurePendingXianyuDeliveryFromPaidPage(tab, scanResult = {}, payload = {}) {
  const pending = await fetchXianyuAdminApi('/api/cc-browser-delivery/next?one_shot=1')
  if (pending.ok && pending.json?.hasPending && pending.json?.shipment?.deliveryMessage) return pending
  if (pending.ok && pending.json?.reason === 'operator_paused') return pending
  if (!scanResult?.paidSignal) return pending
  const itemId = normalizeXianyuItemIdFromUrl(payload.itemId || tab?.url || '')
  if (!itemId) return pending
  const dispatch = await fetchXianyuAdminApi('/api/cc-manual-paid-order/dispatch', {
    method: 'POST',
    body: JSON.stringify({
      item_id: itemId,
      plan_id: payload.planId || '',
      product_title: payload.productTitle || tab?.title || 'CC中转内测卡',
      buyer_hint: payload.buyerHint || '浏览器已付款页面',
      proof_note: 'chrome-paid-page-signal',
      order_id: payload.orderId || (scanResult?.orderIdHint ? `xianyu-real:${scanResult.orderIdHint}` : `browser:${itemId}`),
      one_shot: true,
    }),
  })
  if (!dispatch.ok) return dispatch
  if (dispatch.json?.alreadyHandled) {
    return {
      ok: true,
      status: 200,
      json: {
        ok: true,
        hasPending: false,
        reason: 'shipment_already_handled',
        alreadyHandled: true,
        shipmentId: dispatch.json?.shipmentId || '',
      },
    }
  }
  const shipmentId = dispatch.json?.shipmentId
  const deliveryMessage = dispatch.json?.deliveryMessage
  if (!shipmentId || !deliveryMessage) {
    return { ok: false, status: 502, error: '已请求发卡，但本机没有返回可发送的话术。', dispatch: dispatch.json }
  }
  return {
    ok: true,
    status: 200,
    json: {
      ok: true,
      hasPending: true,
      shipment: {
        id: shipmentId,
        orderId: dispatch.json?.orderId || '',
        itemId,
        buyerId: dispatch.json?.buyerHint || '',
        status: dispatch.json?.status || 'manual_delivery_ready',
        deliveryPreview: '浏览器自动生成的话术',
        deliveryMessage,
      },
      nextAction: '已由浏览器付款页自动生成发货话术。',
    },
  }
}

async function getXianyuDeliveryWatchState() {
  const stored = await chrome.storage.local.get(['xianyuDeliveryWatch'])
  const watch = stored.xianyuDeliveryWatch || {}
  return {
    enabled: Boolean(watch.enabled),
    scope: String(watch.scope || 'current_chat'),
    tabId: Number.isFinite(Number(watch.tabId)) ? Number(watch.tabId) : 0,
    tabCount: Number.isFinite(Number(watch.tabCount)) ? Number(watch.tabCount) : 0,
    url: String(watch.url || ''),
    title: String(watch.title || ''),
    enabledAt: String(watch.enabledAt || ''),
    last_result: watch.last_result || null,
    last_error: String(watch.last_error || ''),
  }
}

async function saveXianyuDeliveryWatchState(watch) {
  await chrome.storage.local.set({ xianyuDeliveryWatch: watch })
  if (watch.enabled) {
    chrome.alarms.create(XIANYU_DELIVERY_WATCH_ALARM, { periodInMinutes: 0.5 })
  } else {
    await chrome.alarms.clear(XIANYU_DELIVERY_WATCH_ALARM)
  }
}

async function setXianyuDeliveryWatch(payload = {}) {
  const enabled = Boolean(payload.enabled)
  if (!enabled) {
    await saveXianyuDeliveryWatchState({
      enabled: false,
      scope: 'current_chat',
      disabledAt: new Date().toISOString(),
      reason: 'operator_disabled',
    })
    return { ok: true, status: 200, watch: await getXianyuDeliveryWatchState() }
  }
  const scope = payload.scope === 'all_open_xianyu_tabs' ? 'all_open_xianyu_tabs' : 'current_chat'
  if (scope === 'all_open_xianyu_tabs') {
    const pendingGate = await assertSinglePendingDeliveryForGlobalWatch()
    if (!pendingGate.ok) return pendingGate
    const xianyuTabs = await getOpenXianyuTabs()
    if (!xianyuTabs.length) {
      return { ok: false, status: 409, error: '没有已打开的闲鱼聊天页；请先打开买家聊天页，再开启全局看守。' }
    }
    const scans = []
    for (const candidate of xianyuTabs.slice(0, 4)) {
      scans.push(await scanXianyuDeliveryTab(candidate, { ...(payload || {}), scope }))
    }
    await saveXianyuDeliveryWatchState({
      enabled: true,
      scope,
      tabId: 0,
      tabCount: xianyuTabs.length,
      url: '',
      title: '所有已打开闲鱼页',
      enabledAt: new Date().toISOString(),
      last_result: { ok: true, status: 200, scans },
      last_error: '',
    })
    return { ok: true, status: 200, watch: await getXianyuDeliveryWatchState(), scan: { ok: true, result: { ready: false, paidSignals: [], inputReady: false, sendButtonReady: false, tabCount: xianyuTabs.length } } }
  }
  const tab = await getActiveTabForSocial()
  if (!tab?.id) return { ok: false, status: 0, error: '没有可看守的当前标签页。' }
  const platform = detectSocialPlatform(tab.url || '')
  if (platform.id !== 'xianyu') {
    return { ok: false, status: 409, error: '请先切到对应的闲鱼买家聊天页，再开启看守。' }
  }
  const scan = await scanXianyuDeliveryTab(tab, payload)
  if (!scan.ok) return scan
  await saveXianyuDeliveryWatchState({
    enabled: true,
    scope,
    tabId: tab.id,
    tabCount: 1,
    url: tab.url || '',
    title: tab.title || '',
    enabledAt: new Date().toISOString(),
    last_result: scan,
    last_error: '',
  })
  return { ok: true, status: 200, watch: await getXianyuDeliveryWatchState(), scan }
}

async function sendXianyuCcDeliveryFromTab(tab, payload = {}) {
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (platform.id !== 'xianyu') {
    return { ok: false, status: 0, error: '请先切到对应的闲鱼买家聊天页。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const scan = await scanXianyuDeliveryTab(tab, payload)
  if (!scan.ok) return scan
  if (!scan.result?.paidSignal) {
    return { ok: false, status: 409, error: '当前页面没看到“已付款/待发货”信号，已阻止自动发货。', scan: scan.result }
  }
  if (!scan.result?.inputReady) {
    return { ok: false, status: 409, error: '当前页面没找到闲鱼聊天输入框。', scan: scan.result }
  }
  const pending = await ensurePendingXianyuDeliveryFromPaidPage(tab, scan.result, payload)
  if (!pending.ok) return pending
  const shipment = pending.json?.shipment
  if (!pending.json?.hasPending || !shipment?.id || !shipment?.deliveryMessage) {
    if (pending.json?.alreadyHandled) {
      const [cleanup] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: runXianyuDeliveryDraftCleanupInPage,
        args: [{
          shipmentId: pending.json?.shipmentId || '',
          requirePaidSignal: true,
          reason: 'already_handled_cleanup',
        }],
      })
      return {
        ok: true,
        status: 200,
        skipped: true,
        reason: pending.json?.reason || 'shipment_already_handled',
        alreadyHandled: true,
        cleanup: cleanup?.result || null,
      }
    }
    return { ok: false, status: 404, error: '本机没有待浏览器发送的卡密话术。', pending: pending.json }
  }
  const [filled] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runXianyuDeliveryFillAndSendInPage,
    args: [{
      shipmentId: shipment.id,
      deliveryMessage: shipment.deliveryMessage,
      requirePaidSignal: true,
      clickSend: true,
    }],
  })
  const fillResult = filled?.result || {}
  if (!fillResult.sent) {
    const failureReason = fillResult.reason || '发货话术未发送；请检查闲鱼页面输入框和发送按钮。'
    const released = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-send-failed`, {
      method: 'POST',
      body: JSON.stringify({ error: failureReason }),
    }).catch((err) => ({
      ok: false,
      status: 0,
      error: err instanceof Error ? err.message : String(err),
    }))
    return {
      ok: false,
      status: 409,
      error: failureReason,
      result: fillResult,
      release: released?.json || released,
      shipment: { id: shipment.id, status: shipment.status, deliveryPreview: shipment.deliveryPreview },
    }
  }
  const marked = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-sent`, {
    method: 'POST',
  })
  if (!marked.ok) {
    return {
      ok: false,
      status: marked.status,
      error: `闲鱼已点击发送，但本机标记失败：${marked.error}`,
      result: fillResult,
      shipment: { id: shipment.id, status: shipment.status, deliveryPreview: shipment.deliveryPreview },
    }
  }
  return {
    ok: true,
    status: 200,
    result: fillResult,
    shipment: { id: shipment.id, status: 'message_sent', deliveryPreview: shipment.deliveryPreview },
    marked: marked.json,
    xianyuConfirm: await confirmXianyuShipmentFromTab(tab, { source: 'after_delivery_send', shipmentId: shipment.id }).catch((err) => ({
      ok: false,
      status: 0,
      error: err instanceof Error ? err.message : String(err),
    })),
  }
}

async function sendXianyuCcDeliveryFromActiveTab(payload = {}) {
  const tab = await getActiveTabForSocial()
  return sendXianyuCcDeliveryFromTab(tab, payload)
}

async function confirmXianyuShipmentFromTab(tab, payload = {}) {
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (platform.id !== 'xianyu') {
    return { ok: false, status: 0, error: '请先切到对应的闲鱼待发货/聊天页。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  const pending = await fetchXianyuAdminApi('/api/cc-xianyu-confirm/next')
  if (!pending.ok) return pending
  const shipment = pending.json?.shipment
  if (!pending.json?.hasPending || !shipment?.id) {
    return { ok: true, status: 200, skipped: true, reason: 'no_pending_confirm', pending: pending.json }
  }
  const targetShipmentId = payload.shipmentId ? String(payload.shipmentId) : ''
  if (targetShipmentId && String(shipment.id) !== targetShipmentId) {
    return {
      ok: false,
      status: 409,
      error: '待确认发货记录和刚发送的卡密记录不一致，已阻止点击。',
      shipment: { id: shipment.id, status: shipment.status, deliveryPreview: shipment.deliveryPreview },
    }
  }
  const [confirmed] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runXianyuConfirmShipmentInPage,
    args: [{
      shipmentId: shipment.id,
      requirePaidSignal: true,
      clickButtons: true,
    }],
  })
  const confirmResult = confirmed?.result || {}
  if (!confirmResult.confirmed) {
    const failed = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-xianyu-confirm-failed`, {
      method: 'POST',
      body: JSON.stringify({ error: confirmResult.reason || '浏览器页面未能确认闲鱼发货' }),
    })
    return {
      ok: false,
      status: 409,
      error: confirmResult.reason || '浏览器页面未能确认闲鱼发货',
      result: confirmResult,
      marked: failed.json || null,
      shipment: { id: shipment.id, status: shipment.status, deliveryPreview: shipment.deliveryPreview },
    }
  }
  const marked = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-xianyu-confirmed`, {
    method: 'POST',
  })
  if (!marked.ok) {
    return {
      ok: false,
      status: marked.status,
      error: `闲鱼已点击发货，但本机标记失败：${marked.error}`,
      result: confirmResult,
      shipment: { id: shipment.id, status: shipment.status, deliveryPreview: shipment.deliveryPreview },
    }
  }
  return {
    ok: true,
    status: 200,
    result: confirmResult,
    shipment: { id: shipment.id, status: 'xianyu_confirmed', deliveryPreview: shipment.deliveryPreview },
    marked: marked.json,
  }
}

async function confirmXianyuShipmentFromActiveTab(payload = {}) {
  const tab = await getActiveTabForSocial()
  return confirmXianyuShipmentFromTab(tab, payload)
}

async function relistXianyuItemFromTab(tab, payload = {}) {
  if (!tab?.id) return { ok: false, status: 0, error: 'No active tab' }
  const platform = detectSocialPlatform(tab.url || '')
  if (platform.id !== 'xianyu') {
    return { ok: false, status: 0, error: '请先切到对应的闲鱼商品页。' }
  }
  if (!chrome.scripting?.executeScript) {
    return { ok: false, status: 0, error: 'Chrome scripting permission unavailable' }
  }
  let shipmentId = payload.shipmentId ? String(payload.shipmentId) : ''
  let itemId = payload.itemId || ''
  if (!shipmentId && payload.useQueue !== false) {
    const pending = await fetchXianyuAdminApi('/api/cc-xianyu-relist/next')
    if (!pending.ok) return pending
    const shipment = pending.json?.shipment
    if (!pending.json?.hasPending || !shipment?.id) {
      return { ok: true, status: 200, skipped: true, reason: 'no_pending_relist', pending: pending.json }
    }
    shipmentId = String(shipment.id)
    itemId = itemId || shipment.itemId || ''
  }
  const [relisted] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: runXianyuRelistItemInPage,
    args: [{
      itemId,
      clickButton: true,
    }],
  })
  const relistResult = relisted?.result || {}
  if (!shipmentId) {
    return {
      ok: Boolean(relistResult.relisted),
      status: relistResult.relisted ? 200 : 409,
      error: relistResult.relisted ? '' : (relistResult.reason || '浏览器页面未能恢复上架'),
      result: relistResult,
    }
  }
  if (!relistResult.relisted) {
    const failed = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(shipmentId)}/mark-relist-failed`, {
      method: 'POST',
      body: JSON.stringify({ error: relistResult.reason || '浏览器页面未能恢复上架' }),
    })
    return {
      ok: false,
      status: 409,
      error: relistResult.reason || '浏览器页面未能恢复上架',
      result: relistResult,
      marked: failed.json || null,
    }
  }
  const marked = await fetchXianyuAdminApi(`/api/cc-shipments/${encodeURIComponent(shipmentId)}/mark-relisted`, {
    method: 'POST',
  })
  if (!marked.ok) {
    return {
      ok: false,
      status: marked.status,
      error: `闲鱼已点击恢复上架，但本机标记失败：${marked.error}`,
      result: relistResult,
    }
  }
  return { ok: true, status: 200, result: relistResult, marked: marked.json }
}

async function relistXianyuItemFromActiveTab(payload = {}) {
  const tab = await getActiveTabForSocial()
  return relistXianyuItemFromTab(tab, payload)
}

async function runXianyuRelistWatchOnce() {
  const pending = await fetchXianyuAdminApi('/api/cc-xianyu-relist/next')
  if (!pending.ok || !pending.json?.hasPending) return pending
  const tabs = await getOpenXianyuTabs()
  if (!tabs.length) return { ok: false, status: 404, error: '没有已打开的闲鱼商品页。' }
  let lastResult = null
  for (const tab of tabs) {
    const result = await relistXianyuItemFromTab(tab, {
      source: 'xianyu_relist_watch',
      shipmentId: pending.json.shipment?.id,
      itemId: pending.json.shipment?.itemId || '',
      useQueue: false,
    })
    lastResult = result
    if (result.ok) return result
  }
  return lastResult || { ok: false, status: 409, error: '已打开闲鱼页里暂未找到可重新上架的商品页。' }
}

async function runXianyuDeliveryWatchOnce() {
  if (xianyuDeliveryWatchInFlight) {
    return { ok: false, status: 409, error: '看守任务正在执行，跳过本轮。' }
  }
  const watch = await getXianyuDeliveryWatchState()
  if (!watch.enabled || (!watch.tabId && watch.scope !== 'all_open_xianyu_tabs')) return { ok: true, status: 200, skipped: true, reason: 'watch_disabled' }
  xianyuDeliveryWatchInFlight = true
  try {
    if (watch.scope === 'all_open_xianyu_tabs') {
      const pendingGate = await assertSinglePendingDeliveryForGlobalWatch()
      if (!pendingGate.ok) {
        await saveXianyuDeliveryWatchState({
          ...watch,
          enabled: false,
          last_error: pendingGate.error || '全局看守安全门未通过。',
        })
        return pendingGate
      }
      const xianyuTabs = await getOpenXianyuTabs()
      if (!xianyuTabs.length) {
        await saveXianyuDeliveryWatchState({
          ...watch,
          enabled: false,
          last_error: '没有已打开的闲鱼聊天页，全局看守自动停止。',
        })
        return { ok: false, status: 404, error: '没有已打开的闲鱼聊天页。' }
      }
      let lastResult = null
      for (const tab of xianyuTabs) {
        const result = await sendXianyuCcDeliveryFromTab(tab, { source: 'xianyu_delivery_watch', scope: watch.scope })
        lastResult = result
        if (result.ok) {
          await saveXianyuDeliveryWatchState({
            ...watch,
            enabled: false,
            tabCount: xianyuTabs.length,
            last_result: result,
            last_error: '',
            disabledAt: new Date().toISOString(),
            reason: 'sent_once',
          })
          return result
        }
      }
      const summary = lastResult || { ok: false, status: 409, error: '已打开闲鱼页里暂未命中已付款聊天。' }
      await saveXianyuDeliveryWatchState({
        ...watch,
        enabled: true,
        tabCount: xianyuTabs.length,
        last_result: summary,
        last_error: summary.error || '',
      })
      return summary
    }
    const tab = await chrome.tabs.get(watch.tabId).catch(() => null)
    if (!tab?.id) {
      await saveXianyuDeliveryWatchState({
        ...watch,
        enabled: false,
        last_error: '目标闲鱼聊天页已关闭，看守自动停止。',
      })
      return { ok: false, status: 404, error: '目标闲鱼聊天页已关闭。' }
    }
    const platform = detectSocialPlatform(tab.url || '')
    if (platform.id !== 'xianyu') {
      await saveXianyuDeliveryWatchState({
        ...watch,
        enabled: false,
        last_error: '目标标签页已离开闲鱼，看守自动停止。',
      })
      return { ok: false, status: 409, error: '目标标签页已离开闲鱼。' }
    }
    const result = await sendXianyuCcDeliveryFromTab(tab, { source: 'xianyu_delivery_watch' })
    if (result.ok) {
      await saveXianyuDeliveryWatchState({
        ...watch,
        enabled: false,
        last_result: result,
        last_error: '',
        disabledAt: new Date().toISOString(),
        reason: 'sent_once',
      })
      return result
    }
    await saveXianyuDeliveryWatchState({
      ...watch,
      enabled: true,
      last_result: result,
      last_error: result.error || '',
    })
    return result
  } finally {
    xianyuDeliveryWatchInFlight = false
  }
}

async function recordSocialPerformance(payload = {}) {
  const storedSettings = await getSocialSettings()
  const incomingSettings = payload && typeof payload.settings === 'object' ? payload.settings : {}
  const settings = mergeSocialSettings({ ...storedSettings, ...incomingSettings })
  const safePayload = payload?.performance
    ? { ...(payload || {}), auto_publish_enabled: false, external_actions_locked: true, publishIntent: false }
    : buildPerformanceSnapshotPayload({
        platform: { id: String(payload.platform || 'x') },
        draft: { id: String(payload.draft_id || '') },
        snapshot: payload || {},
      })
  const response = await fetch(buildSocialApiUrl(settings, 'social/extension/performance'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(safePayload),
    signal: AbortSignal.timeout(5000),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || json?.success === false) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `OpenEverything API returned ${response.status}` }
  }
  return { ok: true, status: response.status, json }
}

function openSocialWebModel(payload = {}) {
  const url = String(payload.open_url || '').trim()
  const allowed = new Set([
    'https://gemini.google.com/app',
    'https://grok.com/',
    'https://chatgpt.com/',
  ])
  if (!allowed.has(url)) {
    return Promise.resolve({ ok: false, status: 0, error: '不支持的网页模型地址，已阻止打开。' })
  }
  if (payload.auto_submit || payload.auto_publish_enabled || payload.external_actions_locked === false) {
    return Promise.resolve({ ok: false, status: 0, error: '网页模型接力只允许打开网页，不允许自动提交或发布。' })
  }
  return chrome.tabs.create({ url, active: true }).then((tab) => ({
    ok: true,
    status: 200,
    tabId: tab?.id || null,
    opened_url: url,
    auto_submit: false,
    auto_publish_enabled: false,
    external_actions_locked: true,
  }))
}

function setBadge(tabId, kind) {
  const cfg = BADGE[kind]
  void chrome.action.setBadgeText({ tabId, text: cfg.text })
  void chrome.action.setBadgeBackgroundColor({ tabId, color: cfg.color })
  void chrome.action.setBadgeTextColor({ tabId, color: '#FFFFFF' }).catch(() => {})
}

// Persist attached tab state to survive MV3 service worker restarts.
async function persistState() {
  try {
    const tabEntries = []
    for (const [tabId, tab] of tabs.entries()) {
      if (tab.state === 'connected' && tab.sessionId && tab.targetId) {
        tabEntries.push({ tabId, sessionId: tab.sessionId, targetId: tab.targetId, attachOrder: tab.attachOrder })
      }
    }
    await chrome.storage.session.set({
      persistedTabs: tabEntries,
      nextSession,
    })
  } catch {
    // chrome.storage.session may not be available in all contexts.
  }
}

// Rehydrate tab state on service worker startup. Fast path — just restores
// maps and badges. Relay reconnect happens separately in background.
async function rehydrateState() {
  try {
    const stored = await chrome.storage.session.get(['persistedTabs', 'nextSession'])
    if (stored.nextSession) {
      nextSession = Math.max(nextSession, stored.nextSession)
    }
    const entries = stored.persistedTabs || []
    // Phase 1: optimistically restore state and badges.
    for (const entry of entries) {
      tabs.set(entry.tabId, {
        state: 'connected',
        sessionId: entry.sessionId,
        targetId: entry.targetId,
        attachOrder: entry.attachOrder,
      })
      tabBySession.set(entry.sessionId, entry.tabId)
      setBadge(entry.tabId, 'on')
    }
    // Phase 2: validate asynchronously, remove dead tabs.
    for (const entry of entries) {
      try {
        await chrome.tabs.get(entry.tabId)
        await chrome.debugger.sendCommand({ tabId: entry.tabId }, 'Runtime.evaluate', {
          expression: '1',
          returnByValue: true,
        })
      } catch {
        tabs.delete(entry.tabId)
        tabBySession.delete(entry.sessionId)
        setBadge(entry.tabId, 'off')
      }
    }
  } catch {
    // Ignore rehydration errors.
  }
}

async function ensureRelayConnection() {
  if (relayWs && relayWs.readyState === WebSocket.OPEN) return
  if (relayConnectPromise) return await relayConnectPromise

  relayConnectPromise = (async () => {
    const port = await getRelayPort()
    const gatewayToken = await getGatewayToken()
    const httpBase = `http://127.0.0.1:${port}`
    const wsUrl = await buildRelayWsUrl(port, gatewayToken)

    // Fast preflight: is the relay server up?
    try {
      await fetch(`${httpBase}/`, { method: 'HEAD', signal: AbortSignal.timeout(2000) })
    } catch (err) {
      throw new Error(`Relay server not reachable at ${httpBase} (${String(err)})`)
    }

    const ws = new WebSocket(wsUrl)
    relayWs = ws
    relayGatewayToken = gatewayToken
    // Bind message handler before open so an immediate first frame (for example
    // gateway connect.challenge) cannot be missed.
    ws.onmessage = (event) => {
      if (ws !== relayWs) return
      void whenReady(() => onRelayMessage(String(event.data || '')))
    }

    await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('WebSocket connect timeout')), 5000)
      ws.onopen = () => {
        clearTimeout(t)
        resolve()
      }
      ws.onerror = () => {
        clearTimeout(t)
        reject(new Error('WebSocket connect failed'))
      }
      ws.onclose = (ev) => {
        clearTimeout(t)
        reject(new Error(`WebSocket closed (${ev.code} ${ev.reason || 'no reason'})`))
      }
    })

    // Bind permanent handlers. Guard against stale socket: if this WS was
    // replaced before its close fires, the handler is a no-op.
    ws.onclose = () => {
      if (ws !== relayWs) return
      onRelayClosed('closed')
    }
    ws.onerror = () => {
      if (ws !== relayWs) return
      onRelayClosed('error')
    }
  })()

  try {
    await relayConnectPromise
    reconnectAttempt = 0
  } finally {
    relayConnectPromise = null
  }
}

// Relay closed — update badges, reject pending requests, auto-reconnect.
// Debugger sessions are kept alive so they survive transient WS drops.
function onRelayClosed(reason) {
  relayWs = null
  relayGatewayToken = ''
  relayConnectRequestId = null

  for (const [id, p] of pending.entries()) {
    pending.delete(id)
    p.reject(new Error(`Relay disconnected (${reason})`))
  }

  reattachPending.clear()

  for (const [tabId, tab] of tabs.entries()) {
    if (tab.state === 'connected') {
      setBadge(tabId, 'connecting')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay: relay reconnecting…',
      })
    }
  }

  scheduleReconnect()
}

function scheduleReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  const delay = reconnectDelayMs(reconnectAttempt)
  reconnectAttempt++

  console.log(`Scheduling reconnect attempt ${reconnectAttempt} in ${Math.round(delay)}ms`)

  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null
    try {
      await ensureRelayConnection()
      reconnectAttempt = 0
      console.log('Reconnected successfully')
      await reannounceAttachedTabs()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.warn(`Reconnect attempt ${reconnectAttempt} failed: ${message}`)
      if (!isRetryableReconnectError(err)) {
        return
      }
      scheduleReconnect()
    }
  }, delay)
}

function cancelReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  reconnectAttempt = 0
}

// Re-announce all attached tabs to the relay after reconnect.
async function reannounceAttachedTabs() {
  for (const [tabId, tab] of tabs.entries()) {
    if (tab.state !== 'connected' || !tab.sessionId || !tab.targetId) continue

    // Verify debugger is still attached.
    try {
      await chrome.debugger.sendCommand({ tabId }, 'Runtime.evaluate', {
        expression: '1',
        returnByValue: true,
      })
    } catch {
      tabs.delete(tabId)
      if (tab.sessionId) tabBySession.delete(tab.sessionId)
      setBadge(tabId, 'off')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay (click to attach/detach)',
      })
      continue
    }

    // Send fresh attach event to relay.
    // Split into two try-catch blocks so debugger failures and relay send
    // failures are handled independently. Previously, a relay send failure
    // would fall into the outer catch and set the badge to 'on' even though
    // the relay had no record of the tab — causing every subsequent browser
    // tool call to fail with "no tab connected" until the next reconnect cycle.
    let targetInfo
    try {
      const info = /** @type {any} */ (
        await chrome.debugger.sendCommand({ tabId }, 'Target.getTargetInfo')
      )
      targetInfo = info?.targetInfo
    } catch {
      // Target.getTargetInfo failed. Preserve at least targetId from
      // cached tab state so relay receives a stable identifier.
      targetInfo = tab.targetId ? { targetId: tab.targetId } : undefined
    }

    try {
      sendToRelay({
        method: 'forwardCDPEvent',
        params: {
          method: 'Target.attachedToTarget',
          params: {
            sessionId: tab.sessionId,
            targetInfo: { ...targetInfo, attached: true },
            waitingForDebugger: false,
          },
        },
      })

      setBadge(tabId, 'on')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay: attached (click to detach)',
      })
    } catch {
      // Relay send failed (e.g. WS closed in the gap between ensureRelayConnection
      // resolving and this loop executing). The tab is still valid — leave badge
      // as 'connecting' so the reconnect/keepalive cycle will retry rather than
      // showing a false-positive 'on' that hides the broken state from the user.
      setBadge(tabId, 'connecting')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay: relay reconnecting…',
      })
    }
  }

  await persistState()
}

function sendToRelay(payload) {
  const ws = relayWs
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    throw new Error('Relay not connected')
  }
  ws.send(JSON.stringify(payload))
}

function ensureGatewayHandshakeStarted(payload) {
  if (relayConnectRequestId) return
  const nonce = typeof payload?.nonce === 'string' ? payload.nonce.trim() : ''
  relayConnectRequestId = `ext-connect-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  sendToRelay({
    type: 'req',
    id: relayConnectRequestId,
    method: 'connect',
    params: {
      minProtocol: 3,
      maxProtocol: 3,
      client: {
        id: 'chrome-relay-extension',
        version: '1.0.0',
        platform: 'chrome-extension',
        mode: 'webchat',
      },
      role: 'operator',
      scopes: ['operator.read', 'operator.write'],
      caps: [],
      commands: [],
      nonce: nonce || undefined,
      auth: relayGatewayToken ? { token: relayGatewayToken } : undefined,
    },
  })
}

async function maybeOpenHelpOnce() {
  try {
    const stored = await chrome.storage.local.get(['helpOnErrorShown'])
    if (stored.helpOnErrorShown === true) return
    await chrome.storage.local.set({ helpOnErrorShown: true })
    await chrome.runtime.openOptionsPage()
  } catch {
    // ignore
  }
}

function requestFromRelay(command) {
  const id = command.id
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id)
      reject(new Error('Relay request timeout (30s)'))
    }, 30000)
    pending.set(id, {
      resolve: (v) => { clearTimeout(timer); resolve(v) },
      reject: (e) => { clearTimeout(timer); reject(e) },
    })
    try {
      sendToRelay(command)
    } catch (err) {
      clearTimeout(timer)
      pending.delete(id)
      reject(err instanceof Error ? err : new Error(String(err)))
    }
  })
}

async function onRelayMessage(text) {
  /** @type {any} */
  let msg
  try {
    msg = JSON.parse(text)
  } catch {
    return
  }

  if (msg && msg.type === 'event' && msg.event === 'connect.challenge') {
    try {
      ensureGatewayHandshakeStarted(msg.payload)
    } catch (err) {
      console.warn('gateway connect handshake start failed', err instanceof Error ? err.message : String(err))
      relayConnectRequestId = null
      const ws = relayWs
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1008, 'gateway connect failed')
      }
    }
    return
  }

  if (msg && msg.type === 'res' && relayConnectRequestId && msg.id === relayConnectRequestId) {
    relayConnectRequestId = null
    if (!msg.ok) {
      const detail = msg?.error?.message || msg?.error || 'gateway connect failed'
      console.warn('gateway connect handshake rejected', String(detail))
      const ws = relayWs
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1008, 'gateway connect failed')
      }
    }
    return
  }

  if (msg && msg.method === 'ping') {
    try {
      sendToRelay({ method: 'pong' })
    } catch {
      // ignore
    }
    return
  }

  if (msg && typeof msg.id === 'number' && (msg.result !== undefined || msg.error !== undefined)) {
    const p = pending.get(msg.id)
    if (!p) return
    pending.delete(msg.id)
    if (msg.error) p.reject(new Error(String(msg.error)))
    else p.resolve(msg.result)
    return
  }

  if (msg && typeof msg.id === 'number' && msg.method === 'forwardCDPCommand') {
    try {
      const result = await handleForwardCdpCommand(msg)
      sendToRelay({ id: msg.id, result })
    } catch (err) {
      sendToRelay({ id: msg.id, error: err instanceof Error ? err.message : String(err) })
    }
  }
}

function getTabBySessionId(sessionId) {
  const direct = tabBySession.get(sessionId)
  if (direct) return { tabId: direct, kind: 'main' }
  const child = childSessionToTab.get(sessionId)
  if (child) return { tabId: child, kind: 'child' }
  return null
}

function getTabByTargetId(targetId) {
  for (const [tabId, tab] of tabs.entries()) {
    if (tab.targetId === targetId) return tabId
  }
  return null
}

async function attachTab(tabId, opts = {}) {
  const debuggee = { tabId }
  await chrome.debugger.attach(debuggee, '1.3')
  await chrome.debugger.sendCommand(debuggee, 'Page.enable').catch(() => {})

  const info = /** @type {any} */ (await chrome.debugger.sendCommand(debuggee, 'Target.getTargetInfo'))
  const targetInfo = info?.targetInfo
  const targetId = String(targetInfo?.targetId || '').trim()
  if (!targetId) {
    throw new Error('Target.getTargetInfo returned no targetId')
  }

  const sid = nextSession++
  const sessionId = `cb-tab-${sid}`
  const attachOrder = sid

  tabs.set(tabId, { state: 'connected', sessionId, targetId, attachOrder })
  tabBySession.set(sessionId, tabId)
  void chrome.action.setTitle({
    tabId,
    title: 'OpenClaw Browser Relay: attached (click to detach)',
  })

  if (!opts.skipAttachedEvent) {
    sendToRelay({
      method: 'forwardCDPEvent',
      params: {
        method: 'Target.attachedToTarget',
        params: {
          sessionId,
          targetInfo: { ...targetInfo, attached: true },
          waitingForDebugger: false,
        },
      },
    })
  }

  setBadge(tabId, 'on')
  await persistState()

  return { sessionId, targetId }
}

async function detachTab(tabId, reason) {
  const tab = tabs.get(tabId)

  // Send detach events for child sessions first.
  for (const [childSessionId, parentTabId] of childSessionToTab.entries()) {
    if (parentTabId === tabId) {
      try {
        sendToRelay({
          method: 'forwardCDPEvent',
          params: {
            method: 'Target.detachedFromTarget',
            params: { sessionId: childSessionId, reason: 'parent_detached' },
          },
        })
      } catch {
        // Relay may be down.
      }
      childSessionToTab.delete(childSessionId)
    }
  }

  // Send detach event for main session.
  if (tab?.sessionId && tab?.targetId) {
    try {
      sendToRelay({
        method: 'forwardCDPEvent',
        params: {
          method: 'Target.detachedFromTarget',
          params: { sessionId: tab.sessionId, targetId: tab.targetId, reason },
        },
      })
    } catch {
      // Relay may be down.
    }
  }

  if (tab?.sessionId) tabBySession.delete(tab.sessionId)
  tabs.delete(tabId)

  try {
    await chrome.debugger.detach({ tabId })
  } catch {
    // May already be detached.
  }

  setBadge(tabId, 'off')
  void chrome.action.setTitle({
    tabId,
    title: 'OpenClaw Browser Relay (click to attach/detach)',
  })

  await persistState()
}

async function connectOrToggleForActiveTab() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true })
  const tabId = active?.id
  if (!tabId) return

  // Prevent concurrent operations on the same tab.
  if (tabOperationLocks.has(tabId)) return
  tabOperationLocks.add(tabId)

  try {
    if (reattachPending.has(tabId)) {
      reattachPending.delete(tabId)
      setBadge(tabId, 'off')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay (click to attach/detach)',
      })
      return
    }

    const existing = tabs.get(tabId)
    if (existing?.state === 'connected') {
      await detachTab(tabId, 'toggle')
      return
    }

    // User is manually connecting — cancel any pending reconnect.
    cancelReconnect()

    tabs.set(tabId, { state: 'connecting' })
    setBadge(tabId, 'connecting')
    void chrome.action.setTitle({
      tabId,
      title: 'OpenClaw Browser Relay: connecting to local relay…',
    })

    try {
      await ensureRelayConnection()
      await attachTab(tabId)
    } catch (err) {
      tabs.delete(tabId)
      setBadge(tabId, 'error')
      void chrome.action.setTitle({
        tabId,
        title: 'OpenClaw Browser Relay: relay not running (open options for setup)',
      })
      void maybeOpenHelpOnce()
      const message = err instanceof Error ? err.message : String(err)
      console.warn('attach failed', message, nowStack())
    }
  } finally {
    tabOperationLocks.delete(tabId)
  }
}

async function handleForwardCdpCommand(msg) {
  const method = String(msg?.params?.method || '').trim()
  const params = msg?.params?.params || undefined
  const sessionId = typeof msg?.params?.sessionId === 'string' ? msg.params.sessionId : undefined

  const bySession = sessionId ? getTabBySessionId(sessionId) : null
  const targetId = typeof params?.targetId === 'string' ? params.targetId : undefined
  const tabId =
    bySession?.tabId ||
    (targetId ? getTabByTargetId(targetId) : null) ||
    (() => {
      for (const [id, tab] of tabs.entries()) {
        if (tab.state === 'connected') return id
      }
      return null
    })()

  if (!tabId) throw new Error(`No attached tab for method ${method}`)

  /** @type {chrome.debugger.DebuggerSession} */
  const debuggee = { tabId }

  if (method === 'Runtime.enable') {
    try {
      await chrome.debugger.sendCommand(debuggee, 'Runtime.disable')
      await new Promise((r) => setTimeout(r, 50))
    } catch {
      // ignore
    }
    return await chrome.debugger.sendCommand(debuggee, 'Runtime.enable', params)
  }

  if (method === 'Target.createTarget') {
    const url = typeof params?.url === 'string' ? params.url : 'about:blank'
    const tab = await chrome.tabs.create({ url, active: false })
    if (!tab.id) throw new Error('Failed to create tab')
    await new Promise((r) => setTimeout(r, 100))
    const attached = await attachTab(tab.id)
    return { targetId: attached.targetId }
  }

  if (method === 'Target.closeTarget') {
    const target = typeof params?.targetId === 'string' ? params.targetId : ''
    const toClose = target ? getTabByTargetId(target) : tabId
    if (!toClose) return { success: false }
    try {
      await chrome.tabs.remove(toClose)
    } catch {
      return { success: false }
    }
    return { success: true }
  }

  if (method === 'Target.activateTarget') {
    const target = typeof params?.targetId === 'string' ? params.targetId : ''
    const toActivate = target ? getTabByTargetId(target) : tabId
    if (!toActivate) return {}
    const tab = await chrome.tabs.get(toActivate).catch(() => null)
    if (!tab) return {}
    if (tab.windowId) {
      await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {})
    }
    await chrome.tabs.update(toActivate, { active: true }).catch(() => {})
    return {}
  }

  const tabState = tabs.get(tabId)
  const mainSessionId = tabState?.sessionId
  const debuggerSession =
    sessionId && mainSessionId && sessionId !== mainSessionId
      ? { ...debuggee, sessionId }
      : debuggee

  return await chrome.debugger.sendCommand(debuggerSession, method, params)
}

function onDebuggerEvent(source, method, params) {
  const tabId = source.tabId
  if (!tabId) return
  const tab = tabs.get(tabId)
  if (!tab?.sessionId) return

  if (method === 'Target.attachedToTarget' && params?.sessionId) {
    childSessionToTab.set(String(params.sessionId), tabId)
  }

  if (method === 'Target.detachedFromTarget' && params?.sessionId) {
    childSessionToTab.delete(String(params.sessionId))
  }

  try {
    sendToRelay({
      method: 'forwardCDPEvent',
      params: {
        sessionId: source.sessionId || tab.sessionId,
        method,
        params,
      },
    })
  } catch {
    // Relay may be down.
  }
}

async function onDebuggerDetach(source, reason) {
  const tabId = source.tabId
  if (!tabId) return
  if (!tabs.has(tabId)) return

  // User explicitly cancelled or DevTools replaced the connection — respect their intent
  if (reason === 'canceled_by_user' || reason === 'replaced_with_devtools') {
    void detachTab(tabId, reason)
    return
  }

  // Check if tab still exists — distinguishes navigation from tab close
  let tabInfo
  try {
    tabInfo = await chrome.tabs.get(tabId)
  } catch {
    // Tab is gone (closed) — normal cleanup
    void detachTab(tabId, reason)
    return
  }

  if (tabInfo.url?.startsWith('chrome://') || tabInfo.url?.startsWith('chrome-extension://')) {
    void detachTab(tabId, reason)
    return
  }

  if (reattachPending.has(tabId)) return

  const oldTab = tabs.get(tabId)
  const oldSessionId = oldTab?.sessionId
  const oldTargetId = oldTab?.targetId

  if (oldSessionId) tabBySession.delete(oldSessionId)
  tabs.delete(tabId)
  for (const [childSessionId, parentTabId] of childSessionToTab.entries()) {
    if (parentTabId === tabId) childSessionToTab.delete(childSessionId)
  }

  if (oldSessionId && oldTargetId) {
    try {
      sendToRelay({
        method: 'forwardCDPEvent',
        params: {
          method: 'Target.detachedFromTarget',
          params: { sessionId: oldSessionId, targetId: oldTargetId, reason: 'navigation-reattach' },
        },
      })
    } catch {
      // Relay may be down.
    }
  }

  reattachPending.add(tabId)
  setBadge(tabId, 'connecting')
  void chrome.action.setTitle({
    tabId,
    title: 'OpenClaw Browser Relay: re-attaching after navigation…',
  })

  // Extend re-attach window from 2.5 s to ~7.7 s (5 attempts).
  // SPAs and pages with heavy JS can take >2.5 s before the Chrome debugger
  // is attachable, causing all three original attempts to fail and leaving
  // the badge permanently off after every navigation.
  const delays = [200, 500, 1000, 2000, 4000]
  for (let attempt = 0; attempt < delays.length; attempt++) {
    await new Promise((r) => setTimeout(r, delays[attempt]))

    if (!reattachPending.has(tabId)) return

    try {
      await chrome.tabs.get(tabId)
    } catch {
      reattachPending.delete(tabId)
      setBadge(tabId, 'off')
      return
    }

    const relayUp = relayWs && relayWs.readyState === WebSocket.OPEN

    try {
      // When relay is down, still attach the debugger but skip sending the
      // relay event. reannounceAttachedTabs() will notify the relay once it
      // reconnects, so the tab stays tracked across transient relay drops.
      await attachTab(tabId, { skipAttachedEvent: !relayUp })
      reattachPending.delete(tabId)
      if (!relayUp) {
        setBadge(tabId, 'connecting')
        void chrome.action.setTitle({
          tabId,
          title: 'OpenClaw Browser Relay: attached, waiting for relay reconnect…',
        })
      }
      return
    } catch {
      // continue retries
    }
  }

  reattachPending.delete(tabId)
  setBadge(tabId, 'off')
  void chrome.action.setTitle({
    tabId,
    title: 'OpenClaw Browser Relay: re-attach failed (click to retry)',
  })
}

// Tab lifecycle listeners — clean up stale entries.
chrome.tabs.onRemoved.addListener((tabId) => void whenReady(() => {
  reattachPending.delete(tabId)
  if (!tabs.has(tabId)) return
  const tab = tabs.get(tabId)
  if (tab?.sessionId) tabBySession.delete(tab.sessionId)
  tabs.delete(tabId)
  for (const [childSessionId, parentTabId] of childSessionToTab.entries()) {
    if (parentTabId === tabId) childSessionToTab.delete(childSessionId)
  }
  if (tab?.sessionId && tab?.targetId) {
    try {
      sendToRelay({
        method: 'forwardCDPEvent',
        params: {
          method: 'Target.detachedFromTarget',
          params: { sessionId: tab.sessionId, targetId: tab.targetId, reason: 'tab_closed' },
        },
      })
    } catch {
      // Relay may be down.
    }
  }
  void persistState()
}))

chrome.tabs.onReplaced.addListener((addedTabId, removedTabId) => void whenReady(() => {
  const tab = tabs.get(removedTabId)
  if (!tab) return
  tabs.delete(removedTabId)
  tabs.set(addedTabId, tab)
  if (tab.sessionId) {
    tabBySession.set(tab.sessionId, addedTabId)
  }
  for (const [childSessionId, parentTabId] of childSessionToTab.entries()) {
    if (parentTabId === removedTabId) {
      childSessionToTab.set(childSessionId, addedTabId)
    }
  }
  setBadge(addedTabId, 'on')
  void persistState()
}))

// Register debugger listeners at module scope so detach/event handling works
// even when the relay WebSocket is down.
chrome.debugger.onEvent.addListener((...args) => void whenReady(() => onDebuggerEvent(...args)))
chrome.debugger.onDetach.addListener((...args) => void whenReady(() => onDebuggerDetach(...args)))

chrome.action.onClicked.addListener(() => void whenReady(() => connectOrToggleForActiveTab()))

// Refresh badge after navigation completes — service worker may have restarted
// during navigation, losing ephemeral badge state.
chrome.webNavigation.onCompleted.addListener(({ tabId, frameId }) => void whenReady(() => {
  if (frameId !== 0) return
  const tab = tabs.get(tabId)
  if (tab?.state === 'connected') {
    setBadge(tabId, relayWs && relayWs.readyState === WebSocket.OPEN ? 'on' : 'connecting')
  }
}))

// Refresh badge when user switches to an attached tab.
chrome.tabs.onActivated.addListener(({ tabId }) => void whenReady(() => {
  const tab = tabs.get(tabId)
  if (tab?.state === 'connected') {
    setBadge(tabId, relayWs && relayWs.readyState === WebSocket.OPEN ? 'on' : 'connecting')
  }
}))

chrome.runtime.onInstalled.addListener(() => {
  void whenReady(() => heartbeatSocialExtensionStatus('installed').catch(() => null))
  void chrome.runtime.openOptionsPage()
})

chrome.runtime.onStartup.addListener(() => {
  void whenReady(() => heartbeatSocialExtensionStatus('startup').catch(() => null))
})

// MV3 keepalive via chrome.alarms — more reliable than setInterval across
// service worker restarts. Checks relay health and refreshes badges.
chrome.alarms.create('relay-keepalive', { periodInMinutes: 0.5 })
chrome.alarms.create(XIANYU_RELIST_WATCH_ALARM, { periodInMinutes: 2 })

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === XIANYU_DELIVERY_WATCH_ALARM) {
    await initPromise
    await heartbeatSocialExtensionStatus('xianyu-watch-alarm').catch(() => null)
    await runXianyuDeliveryWatchOnce().catch((err) => {
      console.warn('Xianyu delivery watch failed:', err instanceof Error ? err.message : err)
    })
    return
  }
  if (alarm.name === XIANYU_RELIST_WATCH_ALARM) {
    await initPromise
    await runXianyuRelistWatchOnce().catch((err) => {
      console.warn('Xianyu relist watch failed:', err instanceof Error ? err.message : err)
    })
    return
  }
  if (alarm.name !== 'relay-keepalive') return
  await initPromise
  await heartbeatSocialExtensionStatus('relay-keepalive').catch(() => null)

  if (tabs.size === 0) return

  // Refresh badges (ephemeral in MV3).
  for (const [tabId, tab] of tabs.entries()) {
    if (tab.state === 'connected') {
      setBadge(tabId, relayWs && relayWs.readyState === WebSocket.OPEN ? 'on' : 'connecting')
    }
  }

  // If relay is down and no reconnect is in progress, trigger one.
  if (!relayWs || relayWs.readyState !== WebSocket.OPEN) {
    if (!relayConnectPromise && !reconnectTimer) {
      console.log('Keepalive: WebSocket unhealthy, triggering reconnect')
      await ensureRelayConnection().catch(() => {
        // ensureRelayConnection may throw without triggering onRelayClosed
        // (e.g. preflight fetch fails before WS is created), so ensure
        // reconnect is always scheduled on failure.
        if (!reconnectTimer) {
          scheduleReconnect()
        }
      })
    }
  }
})

// Rehydrate state on service worker startup. Split: rehydration is the gate
// (fast), relay reconnect runs in background (slow, non-blocking).
const initPromise = rehydrateState()

initPromise.then(() => {
  if (tabs.size > 0) {
    ensureRelayConnection().then(() => {
      reconnectAttempt = 0
      return reannounceAttachedTabs()
    }).catch(() => {
      scheduleReconnect()
    })
  }
})

// Shared gate: all state-dependent handlers await this before accessing maps.
async function whenReady(fn) {
  await initPromise
  return fn()
}

// Options/Popup message bridge. The service worker has host_permissions and
// can talk to the local OpenEverything API without asking users to paste Cookie.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'relayCheck') {
    const { url, token } = msg
    const headers = token ? { 'x-openclaw-relay-token': token } : {}
    fetch(url, { method: 'GET', headers, signal: AbortSignal.timeout(2000) })
      .then(async (res) => {
        const contentType = String(res.headers.get('content-type') || '')
        let json = null
        if (contentType.includes('application/json')) {
          try {
            json = await res.json()
          } catch {
            json = null
          }
        }
        sendResponse({ status: res.status, ok: res.ok, contentType, json })
      })
      .catch((err) => sendResponse({ status: 0, ok: false, error: String(err) }))
    return true
  }

  if (msg?.type === 'toggleRelayForActiveTab') {
    whenReady(() => connectOrToggleForActiveTab())
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialStatusUpdate') {
    updateSocialExtensionStatus(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialStatusFetch') {
    fetchSocialExtensionStatus(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialDraftCreate') {
    createSocialDraftFromActiveTab(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialTrendsFetch') {
    fetchSocialTrends(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialTrendDraftCreate') {
    createSocialDraftFromTrend(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialScheduleFetch') {
    fetchSocialSchedule(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialReviewPackFetch') {
    fetchSocialReviewPack(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialPersonaReview') {
    reviewSocialPersona(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialDraftUpdate') {
    updateSocialDraft(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialDraftReview') {
    reviewSocialDraft(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }


  if (msg?.type === 'socialDraftSchedule') {
    scheduleSocialDraft(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }


  if (msg?.type === 'socialDraftFinalConfirm') {
    finalConfirmSocialDraft(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialDraftAutofill') {
    autofillSocialDraft(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialWebModelOpen') {
    openSocialWebModel(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }


  if (msg?.type === 'socialPageContextScan') {
    scanSocialPageContext(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialInteractionScan') {
    scanSocialInteractions(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialPerformanceScan') {
    scanSocialPerformance(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuDeliveryScan') {
    scanXianyuDeliveryPage(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuDeliverySend') {
    sendXianyuCcDeliveryFromActiveTab(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuShipmentConfirm') {
    confirmXianyuShipmentFromActiveTab(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuItemRelist') {
    relistXianyuItemFromActiveTab(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuDeliveryWatchState') {
    getXianyuDeliveryWatchState()
      .then((watch) => sendResponse({ ok: true, status: 200, watch }))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'xianyuDeliveryWatchSet') {
    setXianyuDeliveryWatch(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialPerformanceRecord') {
    recordSocialPerformance(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialGrowthFeedbackFetch') {
    fetchSocialGrowthFeedback(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialGrowthDraftsCreate') {
    createSocialGrowthDrafts(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  if (msg?.type === 'socialPageProbe') {
    probeSocialPageFields(msg.payload || {})
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, status: 0, error: err instanceof Error ? err.message : String(err) }))
    return true
  }

  return false
})

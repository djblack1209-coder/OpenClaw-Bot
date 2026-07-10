#!/usr/bin/env node
/**
 * CC中转闲鱼卖家本机桥接器。
 *
 * 为什么需要它：
 * - 新版 Chromium 对扩展 Service Worker 访问 127.0.0.1 有 Local Network Access 限制。
 * - 本脚本在浏览器外运行，负责读取本机 18800 队列，再通过 DevTools 往闲鱼页面注入既有页面执行器。
 * - 这样浏览器只负责“看页面/点按钮”，本机进程负责“拿卡密/标记状态”，避免插件 fetch localhost 卡死。
 */

import fs from 'node:fs'
import path from 'node:path'

import { extractXianyuOrderIdFromHeadInfoPayload } from './cc_xianyu_headinfo_parser.mjs'

const rawArgs = process.argv.slice(2)
const args = new Set(rawArgs)
function getArgValue(name) {
  const prefix = `${name}=`
  const direct = rawArgs.find((item) => item.startsWith(prefix))
  if (direct) return direct.slice(prefix.length)
  const index = rawArgs.indexOf(name)
  if (index >= 0 && rawArgs[index + 1] && !rawArgs[index + 1].startsWith('--')) return rawArgs[index + 1]
  return ''
}
const jsonOnly = args.has('--json')
const dryRun = args.has('--dry-run')
const scanOnly = args.has('--scan-only') || args.has('--preflight-only')
const relistOnly = args.has('--relist-only')
const simulationRelist = args.has('--simulation-relist')
const oneShotOverride = args.has('--one-shot-override') || args.has('--one-shot')
const deliveryOnly = args.has('--delivery-only') || oneShotOverride
const requireSingleXianyuPage = args.has('--require-single-xianyu-page') || oneShotOverride
const requireRealOrderId = (args.has('--require-real-order-id') || oneShotOverride) && !args.has('--allow-browser-order')
const openPageDestination = getArgValue('--open-page').trim().toLowerCase()
const openPageOnly = Boolean(openPageDestination)
const once = args.has('--once') || dryRun || scanOnly || relistOnly || oneShotOverride || deliveryOnly || openPageOnly
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
const runnerFile = path.join(repoRoot, 'packages/openclaw-npm/assets/chrome-extension/social-page-runner.js')
const envFile = path.join(repoRoot, 'packages/clawbot/config/.env')
const xianyuAdminBase = process.env.CC_XIANYU_ADMIN_BASE_URL || 'http://127.0.0.1:18800'
const internalApiBase = process.env.CC_XIANYU_INTERNAL_API_BASE_URL || 'http://127.0.0.1:18790/api/v1'
const debugPorts = String(process.env.CC_XIANYU_CHROME_DEBUG_PORTS || process.env.CC_XIANYU_CHROME_DEBUG_PORT || '9225,9236,9223')
  .split(',')
  .map((item) => Number.parseInt(item.trim(), 10))
  .filter((item) => Number.isFinite(item) && item > 0)
const watchIntervalMs = Math.max(5000, Number.parseInt(process.env.CC_XIANYU_SELLER_BRIDGE_INTERVAL_MS || '15000', 10))
const OPEN_PAGE_URLS = {
  im: 'https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3',
  message: 'https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3',
  messages: 'https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3',
  seller: 'https://seller.goofish.com/',
  workbench: 'https://seller.goofish.com/',
}

function parseEnvFile(file) {
  if (!fs.existsSync(file)) return {}
  const result = {}
  for (const rawLine of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#') || !line.includes('=')) continue
    const [key, ...rest] = line.split('=')
    result[key.trim()] = rest.join('=').trim().replace(/^['"]|['"]$/g, '')
  }
  return result
}

function isXianyuUrl(url = '') {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '').toLowerCase()
    return host === 'goofish.com' || host.endsWith('.goofish.com') || host === '2.taobao.com' || host === 'm.tb.cn' || host.endsWith('.tb.cn')
  } catch {
    return false
  }
}

function normalizeItemIdFromUrl(url = '') {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    for (const key of ['itemId', 'item_id', 'itemIdStr', 'item_id_str', 'id']) {
      const value = parsed.searchParams.get(key)
      if (value && /^[A-Za-z0-9_-]{4,120}$/.test(value)) return value
    }
  } catch {
    // 闲鱼短链或 App 跳转页回退到完整 URL。
  }
  return raw
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(options.timeoutMs || 8000),
  })
  const contentType = String(response.headers.get('content-type') || '')
  const json = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok) {
    return { ok: false, status: response.status, error: json?.detail || json?.error || `HTTP ${response.status}`, json }
  }
  return { ok: true, status: response.status, json }
}

function apiHeaders(token, extra = {}) {
  return {
    'x-api-token': token,
    ...extra,
  }
}

async function adminApi(token, apiPath, options = {}) {
  return fetchJson(`${xianyuAdminBase}${apiPath}`, {
    method: options.method || 'GET',
    headers: apiHeaders(token, {
      ...(options.body ? { 'content-type': 'application/json' } : {}),
      ...(options.headers || {}),
    }),
    body: options.body,
    timeoutMs: options.timeoutMs || 8000,
  })
}

async function authorizeOneShotDelivery(token) {
  if (!oneShotOverride) return { ok: true, skipped: true }
  return adminApi(token, '/api/cc-operator-mode/one-shot-delivery', {
    method: 'POST',
    body: JSON.stringify({
      reason: 'seller_bridge_one_shot_override',
      ttl_seconds: 180,
    }),
  })
}

async function postBridgeStatus(token, port, tabCount) {
  const payload = {
    platform: 'xianyu',
    url: 'https://www.goofish.com/',
    running: true,
    detected_platform: { id: 'xianyu', label: '闲鱼', supported: true },
    tasks: [
      'CC中转本机卖家桥接器运行中',
      '由本机进程调度卡密与状态标记',
      '浏览器页面只执行发货、确认发货和恢复上架动作',
    ],
    extension: {
      manifest_version: 'bridge',
      cc_delivery_helper_version: '2026-07-07-local-devtools-bridge',
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
    },
    heartbeat_reason: `seller_bridge:${port}:${tabCount}`,
  }
  return fetchJson(`${internalApiBase}/social/extension/status`, {
    method: 'POST',
    headers: apiHeaders(token, { 'content-type': 'application/json' }),
    body: JSON.stringify(payload),
    timeoutMs: 8000,
  })
}

async function discoverBrowser() {
  const candidates = []
  for (const port of debugPorts) {
    try {
      const targets = await fetchJson(`http://127.0.0.1:${port}/json/list`, { timeoutMs: 3000 })
      if (!targets.ok || !Array.isArray(targets.json)) continue
      const pages = targets.json.filter((target) => target.type === 'page' && target.webSocketDebuggerUrl)
      const xianyuPages = pages.filter((target) => isXianyuUrl(target.url || ''))
      candidates.push({ ok: true, port, pages, xianyuPages })
    } catch {
      // 继续尝试下一个调试端口。
    }
  }
  const withXianyu = candidates.find((candidate) => candidate.xianyuPages.length > 0)
  if (withXianyu) return withXianyu
  if (candidates.length) return candidates[0]
  return { ok: false, error: `没有找到卖家专用 Chromium 调试端口：${debugPorts.join(', ')}` }
}

function buildPageExpression(functionName, payload = {}) {
  const source = fs.readFileSync(runnerFile, 'utf8').replace(/\bexport\s+/g, '')
  return `(() => {
${source}
const payload = ${JSON.stringify(payload)};
return ${functionName}(payload);
})()`
}

function cdpEvaluate(webSocketDebuggerUrl, expression, timeoutMs = 12000) {
  return new Promise((resolve) => {
    const ws = new WebSocket(webSocketDebuggerUrl)
    let nextId = 0
    let runtimeEnabled = false
    const timer = setTimeout(() => {
      try { ws.close() } catch {}
      resolve({ ok: false, error: 'timeout' })
    }, timeoutMs)
    const send = (method, params = {}) => {
      nextId += 1
      ws.send(JSON.stringify({ id: nextId, method, params }))
    }
    ws.addEventListener('open', () => {
      send('Runtime.enable')
    })
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data || '{}'))
      if (!message.id) return
      if (!runtimeEnabled) {
        runtimeEnabled = true
        if (message.error) {
          clearTimeout(timer)
          try { ws.close() } catch {}
          resolve({ ok: false, error: message.error.message || 'runtime_enable_failed' })
          return
        }
        send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
        return
      }
      clearTimeout(timer)
      try { ws.close() } catch {}
      if (message.error) {
        resolve({ ok: false, error: message.error.message || 'cdp_error' })
        return
      }
      if (message.result?.exceptionDetails) {
        resolve({ ok: false, error: message.result.exceptionDetails.text || 'page_exception' })
        return
      }
      resolve({ ok: true, result: message.result?.result?.value || null })
    })
    ws.addEventListener('error', () => {
      clearTimeout(timer)
      resolve({ ok: false, error: 'websocket_error' })
    })
  })
}

function cdpCommand(webSocketDebuggerUrl, method, params = {}, timeoutMs = 10000) {
  return new Promise((resolve) => {
    const ws = new WebSocket(webSocketDebuggerUrl)
    const timer = setTimeout(() => {
      try { ws.close() } catch {}
      resolve({ ok: false, error: 'timeout' })
    }, timeoutMs)
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({ id: 1, method, params }))
    })
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data || '{}'))
      if (message.id !== 1) return
      clearTimeout(timer)
      try { ws.close() } catch {}
      if (message.error) {
        resolve({ ok: false, error: message.error.message || 'cdp_error' })
        return
      }
      resolve({ ok: true, result: message.result || {} })
    })
    ws.addEventListener('error', () => {
      clearTimeout(timer)
      resolve({ ok: false, error: 'websocket_error' })
    })
  })
}

function buildXianyuHeadInfoTriggerExpression() {
  return `(() => {
    function visible(el) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }
    const rows = [...document.querySelectorAll('.conversation-item--JReyg97P,[class*="conversation-item"]')]
      .filter(visible)
      .filter((el) => el.getBoundingClientRect().x < Math.min(520, window.innerWidth * 0.5));
    const row = rows.find((el) => /等待卖家发货|卖家待发货|待发货|已付款|已经付款/.test(el.innerText || el.textContent || ''));
    if (!row) return { clicked: false, reason: 'paid_conversation_row_not_found', rowCount: rows.length };
    row.click();
    return { clicked: true, reason: 'paid_conversation_row_clicked', text: String(row.innerText || row.textContent || '').slice(0, 120) };
  })()`
}

async function captureXianyuHeadInfoOrderId(target, { triggerReload = true, triggerConversationClick = true, timeoutMs = 10000 } = {}) {
  if (!target?.webSocketDebuggerUrl) return { ok: false, orderId: '', reason: 'missing_websocket_debugger_url' }
  return new Promise((resolve) => {
    const ws = new WebSocket(target.webSocketDebuggerUrl)
    let nextId = 0
    let settled = false
    const pending = new Map()
    const finish = (payload) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      try { ws.close() } catch {}
      resolve(payload)
    }
    const send = (method, params = {}, onResult = null) => {
      nextId += 1
      if (onResult) pending.set(nextId, onResult)
      ws.send(JSON.stringify({ id: nextId, method, params }))
      return nextId
    }
    const timer = setTimeout(() => {
      finish({ ok: false, orderId: '', reason: 'headinfo_timeout' })
    }, timeoutMs)
    ws.addEventListener('open', () => {
      send('Network.enable', {}, () => {
        const clickPaidConversationRow = () => {
          if (!triggerConversationClick || settled) return
          // 只点击左侧当前已付款会话行，目的是触发闲鱼 headinfo 接口；不点击“去发货”。
          send('Runtime.evaluate', { expression: buildXianyuHeadInfoTriggerExpression(), returnByValue: true })
        }
        if (triggerReload) {
          // 只读刷新当前闲鱼聊天页，再点买家会话行；实测 headinfo 在这个顺序下更稳定出现。
          send('Page.reload', { ignoreCache: true })
          setTimeout(clickPaidConversationRow, 1800)
          setTimeout(clickPaidConversationRow, 3600)
          return
        }
        clickPaidConversationRow()
      })
    })
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data || '{}'))
      if (message.id && pending.has(message.id)) {
        const handler = pending.get(message.id)
        pending.delete(message.id)
        handler(message)
        return
      }
      if (message.method !== 'Network.responseReceived') return
      const response = message.params?.response || {}
      const url = String(response.url || '')
      if (!/mtop\.idle\.trade\.pc\.message\.headinfo/i.test(url)) return
      const requestId = message.params?.requestId
      if (!requestId) return
      send('Network.getResponseBody', { requestId }, (bodyMessage) => {
        if (bodyMessage.error) return
        let body = String(bodyMessage.result?.body || '')
        if (bodyMessage.result?.base64Encoded) {
          body = Buffer.from(body, 'base64').toString('utf8')
        }
        const parsed = extractXianyuOrderIdFromHeadInfoPayload(body)
        if (parsed.ok && parsed.orderId) {
          finish({
            ok: true,
            orderId: parsed.orderId,
            itemId: parsed.itemId || '',
            source: `headinfo_network:${parsed.source}`,
            itemSource: parsed.itemSource ? `headinfo_network:${parsed.itemSource}` : '',
            reason: '',
            url: url.slice(0, 180),
          })
        }
      })
    })
    ws.addEventListener('error', () => {
      finish({ ok: false, orderId: '', reason: 'websocket_error' })
    })
  })
}

function shouldTryHeadInfoCapture(result = {}) {
  return Boolean(
    !String(result.orderIdHint || '').trim()
    && (result.paidSignal || result.orderCardPresent || result.shipActionPresent)
  )
}

async function enrichScanResultWithHeadInfo(target, result = {}, options = {}) {
  if (options.enabled === false) return { result, headInfoCapture: { ok: false, skipped: true, reason: 'disabled' } }
  if (!shouldTryHeadInfoCapture(result)) return { result, headInfoCapture: { ok: false, skipped: true, reason: 'not_needed' } }
  const captured = await captureXianyuHeadInfoOrderId(target, options)
  if (!captured.ok || !captured.orderId) return { result, headInfoCapture: captured }
  return {
    result: {
      ...result,
      orderIdHint: captured.orderId,
      orderIdSource: captured.source || 'headinfo_network',
      itemIdHint: captured.itemId || result.itemIdHint || '',
      itemIdSource: captured.itemSource || result.itemIdSource || '',
    },
    headInfoCapture: captured,
  }
}

async function runPageFunction(target, functionName, payload = {}) {
  return cdpEvaluate(target.webSocketDebuggerUrl, buildPageExpression(functionName, payload))
}

async function openSellerBrowserPage(browser, destination) {
  const normalized = String(destination || '').trim().toLowerCase()
  const url = OPEN_PAGE_URLS[normalized]
  if (!url) {
    return {
      ok: false,
      mode: 'open_page_only',
      error: 'unsupported_open_page_destination',
      destination: normalized,
      allowedDestinations: ['im', 'seller'],
      nextAction: '只支持打开“闲鱼消息”或“卖家工作台”，不能输入任意网址。',
    }
  }
  const target = browser.xianyuPages[0] || browser.pages[0]
  if (target?.webSocketDebuggerUrl) {
    const navigated = await cdpCommand(target.webSocketDebuggerUrl, 'Page.navigate', { url })
    const broughtFront = navigated.ok
      ? await cdpCommand(target.webSocketDebuggerUrl, 'Page.bringToFront', {})
      : { ok: false, skipped: true, error: navigated.error || 'navigate_failed' }
    return {
      ok: Boolean(navigated.ok),
      mode: 'open_page_only',
      destination: normalized,
      url,
      port: browser.port,
      xianyuTabs: browser.xianyuPages.length,
      previousUrl: String(target.url || '').slice(0, 300),
      openedIn: 'existing_tab',
      broughtFront: Boolean(broughtFront.ok),
      navigate: navigated.result || {},
      activate: broughtFront.result || {},
      error: navigated.ok ? '' : navigated.error,
      nextAction: navigated.ok
        ? '卖家 Chromium 已打开对应闲鱼页面。请在页面里找到已付款买家，确认看到订单号/交易号后回到 18800 点“只读检查当前页”。'
        : '没有成功导航卖家 Chromium，请确认卖家浏览器仍在运行。',
    }
  }
  const created = await fetchJson(`http://127.0.0.1:${browser.port}/json/new?${encodeURIComponent(url)}`, {
    method: 'PUT',
    timeoutMs: 5000,
  })
  const createdTarget = created.json || {}
  const broughtFront = created.ok && createdTarget.webSocketDebuggerUrl
    ? await cdpCommand(createdTarget.webSocketDebuggerUrl, 'Page.bringToFront', {})
    : { ok: false, skipped: true, error: created.ok ? 'missing_websocket_debugger_url' : created.error }
  return {
    ok: Boolean(created.ok),
    mode: 'open_page_only',
    destination: normalized,
    url,
    port: browser.port,
    xianyuTabs: browser.xianyuPages.length,
    openedIn: 'new_tab',
    broughtFront: Boolean(broughtFront.ok),
    error: created.ok ? '' : created.error,
    nextAction: created.ok
      ? '卖家 Chromium 已新开对应闲鱼页面。请在页面里找到已付款买家，确认看到订单号/交易号后回到 18800 点“只读检查当前页”。'
      : '没有成功打开卖家 Chromium 页面，请确认卖家浏览器仍在运行。',
  }
}

async function ensureDeliveryMessage(token, target, scanResult) {
  if (oneShotOverride && scanResult?.paidSignal && scanResult?.inputReady) {
    const oneShotAuthorization = await authorizeOneShotDelivery(token)
    if (!oneShotAuthorization.ok) return oneShotAuthorization
  }
  const pending = await adminApi(token, `/api/cc-browser-delivery/next${oneShotOverride ? '?one_shot=1' : ''}`)
  if (pending.ok && pending.json?.hasPending && pending.json?.shipment?.deliveryMessage) return pending
  if (pending.ok && pending.json?.reason === 'operator_paused') return pending
  if (!scanResult?.paidSignal) return pending
  const itemId = String(scanResult?.itemIdHint || '').trim() || normalizeItemIdFromUrl(target.url || '')
  if (!itemId) return pending
  const dispatch = await adminApi(token, '/api/cc-manual-paid-order/dispatch', {
    method: 'POST',
    body: JSON.stringify({
      item_id: itemId,
      plan_id: '',
      product_title: target.title || 'CC中转内测卡',
      buyer_hint: '浏览器桥接器已付款页面',
      proof_note: 'devtools-bridge-paid-page-signal',
      order_id: scanResult?.orderIdHint ? `xianyu-real:${scanResult.orderIdHint}` : `browser:${itemId}`,
      one_shot: oneShotOverride,
    }),
  })
  if (!dispatch.ok) return dispatch
  if (dispatch.json?.alreadyHandled) {
    return {
      ok: true,
      status: 200,
      json: {
        hasPending: false,
        shipment: null,
        reason: 'shipment_already_handled',
        alreadyHandled: true,
        orderId: dispatch.json.orderId || '',
        shipmentId: dispatch.json.shipmentId || '',
      },
    }
  }
  return {
    ok: true,
    status: 200,
    json: {
      hasPending: true,
      shipment: {
        id: dispatch.json?.shipmentId,
        orderId: dispatch.json?.orderId || '',
        itemId,
        status: dispatch.json?.status || 'manual_delivery_ready',
        deliveryPreview: '浏览器桥接器自动生成的话术',
        deliveryMessage: dispatch.json?.deliveryMessage || '',
      },
    },
  }
}

async function handleDeliveryForPage(token, target) {
  const scan = await runPageFunction(target, 'runXianyuDeliveryScanInPage', { note: 'devtools_bridge' })
  if (!scan.ok) return { ok: false, stage: 'scan', error: scan.error, url: target.url }
  let scanResult = scan.result || {}
  const enriched = await enrichScanResultWithHeadInfo(target, scanResult, { enabled: requireRealOrderId, triggerReload: requireRealOrderId })
  scanResult = enriched.result
  if (!scanResult.paidSignal || !scanResult.inputReady) {
    return { ok: true, stage: 'scan', skipped: true, reason: scanResult.reason || 'not_paid_chat_page', headInfoCapture: enriched.headInfoCapture, url: target.url }
  }
  if (requireRealOrderId && !String(scanResult.orderIdHint || '').trim()) {
    return {
      ok: true,
      stage: 'scan',
      skipped: true,
      reason: 'real_order_id_missing',
      nextAction: '当前页看到了付款信号，但没有识别到真实订单号。系统已尝试只读刷新抓取闲鱼订单头信息；仍失败时，请打开订单详情页或包含订单号/交易号的聊天页后重试。',
      headInfoCapture: enriched.headInfoCapture,
      url: target.url,
    }
  }
  const pending = await ensureDeliveryMessage(token, target, scanResult)
  const shipment = pending.json?.shipment
  if (pending.ok && !pending.json?.hasPending) {
    const cleanup = pending.json?.alreadyHandled
      ? await runPageFunction(target, 'runXianyuDeliveryDraftCleanupInPage', {
        shipmentId: pending.json?.shipmentId || '',
        requirePaidSignal: true,
        reason: 'already_handled_cleanup',
      })
      : null
    return {
      ok: true,
      stage: 'pending',
      skipped: true,
      reason: pending.json?.reason || 'no_pending_delivery_message',
      alreadyHandled: Boolean(pending.json?.alreadyHandled),
      shipmentId: pending.json?.shipmentId || '',
      cleanup: cleanup?.result || null,
      url: target.url,
    }
  }
  if (!pending.ok || !pending.json?.hasPending || !shipment?.id || !shipment?.deliveryMessage) {
    return { ok: false, stage: 'pending', error: pending.error || 'no_pending_delivery_message', url: target.url }
  }
  const sent = await runPageFunction(target, 'runXianyuDeliveryFillAndSendInPage', {
    shipmentId: shipment.id,
    deliveryMessage: shipment.deliveryMessage,
    requirePaidSignal: true,
    clickSend: true,
  })
  if (!sent.ok || !sent.result?.sent) {
    const error = sent.error || sent.result?.reason || 'send_failed'
    const released = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-send-failed`, {
      method: 'POST',
      body: JSON.stringify({ error }),
    }).catch((releaseError) => ({
      ok: false,
      error: releaseError instanceof Error ? releaseError.message : String(releaseError),
    }))
    return { ok: false, stage: 'send', error, shipmentId: shipment.id, release: released?.json || released, url: target.url }
  }
  const marked = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-sent`, { method: 'POST' })
  if (!marked.ok) {
    return { ok: false, stage: 'mark_sent', error: marked.error, shipmentId: shipment.id, url: target.url }
  }
  const confirm = await handleConfirmForPage(token, target, String(shipment.id))
  return { ok: true, stage: 'sent', shipmentId: shipment.id, send: sent.result, confirm, url: target.url }
}

async function scanDeliveryPage(target) {
  const scan = await runPageFunction(target, 'runXianyuDeliveryScanInPage', { note: 'seller_bridge_scan_only' })
  const enriched = scan.ok
    ? await enrichScanResultWithHeadInfo(target, scan.result || {}, { enabled: requireRealOrderId, triggerReload: requireRealOrderId })
    : { result: scan.result || {}, headInfoCapture: { ok: false, skipped: true, reason: scan.error || 'scan_failed' } }
  const result = enriched.result || {}
  const orderIdHint = String(result.orderIdHint || '').trim()
  return {
    ok: Boolean(scan.ok),
    stage: 'scan_only',
    title: String(target.title || '').slice(0, 120),
    url: String(target.url || '').slice(0, 300),
    paidSignal: Boolean(result.paidSignal),
    paidSignals: Array.isArray(result.paidSignals) ? result.paidSignals.slice(0, 6) : [],
    inputReady: Boolean(result.inputReady),
    sendButtonReady: Boolean(result.sendButtonReady),
    orderIdHintPresent: Boolean(orderIdHint),
    orderIdSource: orderIdHint ? String(result.orderIdSource || 'page_dom').slice(0, 120) : '',
    itemIdHintPresent: Boolean(String(result.itemIdHint || '').trim()),
    itemIdSource: String(result.itemIdSource || '').slice(0, 120),
    headInfoCapture: enriched.headInfoCapture?.ok
      ? { ok: true, source: String(enriched.headInfoCapture.source || '').slice(0, 120) }
      : { ok: false, skipped: Boolean(enriched.headInfoCapture?.skipped), reason: String(enriched.headInfoCapture?.reason || '').slice(0, 120) },
    orderCardPresent: Boolean(result.orderCardPresent),
    shipActionPresent: Boolean(result.shipActionPresent),
    readyToSend: Boolean(result.paidSignal && result.inputReady),
    strictReadyToSend: Boolean(result.paidSignal && result.inputReady && orderIdHint),
    reason: scan.ok ? (result.reason || '') : (scan.error || 'scan_failed'),
  }
}

function buildDeliveryScanNextAction(browser, scans, readyPages, strictReadyPages) {
  if (browser.xianyuPages.length !== 1) {
    return '请只保留 1 个真实已付款闲鱼聊天/订单页，再点只读检查。'
  }
  if (strictReadyPages.length === 1) {
    return '当前唯一闲鱼页已看到付款信号、输入框和真实订单号，可以回到 18800 点“一键跑当前页”。'
  }
  const first = scans.find((item) => item && item.ok) || scans[0] || {}
  if (first.readyToSend && !first.orderIdHintPresent) {
    if (first.orderCardPresent || first.shipActionPresent) {
      return '当前页已经看到待发货订单卡和聊天输入框，但还没拿到真实订单号。请点订单卡片里的“¥1.00 / 等待卖家发货”区域，或点“去发货”旁边进入订单详情；看到“订单号/交易号”后再点只读检查。'
    }
    return '当前页看到付款信号和输入框，但没有识别到真实订单号。请打开订单详情页或包含订单号/交易号的页面。'
  }
  if (first.paidSignal && !first.inputReady) {
    if (first.orderCardPresent || first.shipActionPresent) {
      return '页面看到了“等待卖家发货”的订单卡，但还没有聊天输入框。请点进买家的聊天输入区域；如果只看到订单卡，就点订单卡片或“去发货”旁边进入订单详情，看到订单号后再检查。'
    }
    return '页面看到了付款信号，但没有找到聊天输入框。请切到买家聊天页，或在订单详情里打开联系买家窗口。'
  }
  if (first.inputReady && !first.paidSignal) {
    return '页面有聊天输入框，但没看到“已付款/待发货”。请确认这是已付款订单，不要在普通聊天页发卡。'
  }
  if (readyPages.length > 0 && requireRealOrderId) {
    return '当前页看到付款信号和输入框，但没有识别到真实订单号。请打开订单详情页或包含订单号/交易号的页面。'
  }
  return '当前闲鱼页还不是已付款聊天/订单页，或没有聊天输入框。'
}

async function handleConfirmForPage(token, target, expectedShipmentId = '') {
  const pending = await adminApi(token, '/api/cc-xianyu-confirm/next')
  if (!pending.ok) return { ok: false, error: pending.error || 'confirm_queue_unavailable', status: pending.status || 0 }
  const shipment = pending.json?.shipment
  if (!pending.json?.hasPending || !shipment?.id) {
    return handleCurrentPageConfirmForPage(token, target, expectedShipmentId)
  }
  if (expectedShipmentId && String(shipment.id) !== expectedShipmentId) {
    return { ok: false, error: 'pending_confirm_mismatch', expectedShipmentId, shipmentId: shipment.id }
  }
  const confirmed = await runPageFunction(target, 'runXianyuConfirmShipmentInPage', {
    shipmentId: shipment.id,
    requirePaidSignal: true,
    clickButtons: true,
  })
  if (!confirmed.ok || !confirmed.result?.confirmed) {
    const error = confirmed.error || confirmed.result?.reason || 'confirm_failed'
    await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-xianyu-confirm-failed`, {
      method: 'POST',
      body: JSON.stringify({ error }),
    })
    return { ok: false, error, shipmentId: shipment.id, result: confirmed.result || null }
  }
  const marked = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-xianyu-confirmed`, { method: 'POST' })
  return { ok: marked.ok, error: marked.error || '', shipmentId: shipment.id, result: confirmed.result || null }
}

async function handleStandaloneConfirmForPage(token, target) {
  const preflight = await runPageFunction(target, 'runXianyuConfirmShipmentInPage', {
    shipmentId: 'standalone-confirm-preflight',
    requirePaidSignal: true,
    clickButtons: false,
  })
  if (!preflight.ok) {
    return { ok: true, skipped: true, reason: 'standalone_confirm_preflight_failed', error: preflight.error || '', url: target.url }
  }
  if (!preflight.result?.paidSignal) {
    return { ok: true, skipped: true, reason: preflight.result?.reason || 'no_paid_order_signal', url: target.url }
  }
  return handleConfirmForPage(token, target)
}

async function handleCurrentPageConfirmForPage(token, target, expectedShipmentId = '') {
  const preflight = await runPageFunction(target, 'runXianyuConfirmShipmentInPage', {
    shipmentId: expectedShipmentId || 'current-page-preflight',
    requirePaidSignal: true,
    clickButtons: false,
  })
  if (!preflight.ok) {
    return { ok: true, skipped: true, reason: 'current_page_preflight_failed', error: preflight.error || '', url: target.url }
  }
  if (!preflight.result?.paidSignal) {
    return { ok: true, skipped: true, reason: preflight.result?.reason || 'no_pending_confirm', url: target.url }
  }
  const rawTargetUrl = String(target.url || '')
  const hasItemIdInUrl = /[?&#](?:itemId|item_id|itemIdStr|item_id_str|id)=/i.test(rawTargetUrl)
  const itemId = hasItemIdInUrl ? normalizeItemIdFromUrl(rawTargetUrl) : ''
  const candidate = await adminApi(
    token,
    `/api/cc-xianyu-confirm/current-page-candidate${itemId ? `?item_id=${encodeURIComponent(itemId)}` : ''}`,
  )
  const shipment = candidate.json?.shipment
  if (!candidate.ok || !candidate.json?.hasPending || !shipment?.id) {
    return {
      ok: true,
      skipped: true,
      reason: candidate.json?.reason || candidate.error || 'no_current_page_confirm_candidate',
      url: target.url,
    }
  }
  if (expectedShipmentId && String(shipment.id) !== expectedShipmentId) {
    return { ok: false, error: 'current_page_confirm_mismatch', expectedShipmentId, shipmentId: shipment.id, url: target.url }
  }
  const confirmed = await runPageFunction(target, 'runXianyuConfirmShipmentInPage', {
    shipmentId: shipment.id,
    requirePaidSignal: true,
    clickButtons: true,
  })
  if (!confirmed.ok || !confirmed.result?.confirmed) {
    return {
      ok: false,
      error: confirmed.error || confirmed.result?.reason || 'current_page_confirm_failed',
      shipmentId: shipment.id,
      result: confirmed.result || null,
      queueType: candidate.json?.queueType || 'current_page_remediation',
      url: target.url,
    }
  }
  const marked = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-xianyu-confirmed`, { method: 'POST' })
  return {
    ok: marked.ok,
    error: marked.error || '',
    shipmentId: shipment.id,
    result: confirmed.result || null,
    queueType: candidate.json?.queueType || 'current_page_remediation',
    url: target.url,
  }
}

async function handleRelistForPages(token, targets, options = {}) {
  const mode = options.simulation ? 'simulation' : 'production'
  const pending = await adminApi(token, `/api/cc-xianyu-relist/next?mode=${encodeURIComponent(mode)}`)
  const shipment = pending.json?.shipment
  if (!pending.ok || !pending.json?.hasPending || !shipment?.id) {
    return { ok: true, skipped: true, reason: 'no_pending_relist', mode }
  }
  for (const target of targets) {
    const result = await runPageFunction(target, 'runXianyuRelistItemInPage', {
      shipmentId: shipment.id,
      itemId: shipment.itemId || '',
      clickButton: true,
    })
    if (result.ok && result.result?.relisted) {
      const marked = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-relisted`, { method: 'POST' })
      return {
        ok: marked.ok,
        error: marked.error || '',
        shipmentId: shipment.id,
        queueType: pending.json?.queueType || '',
        mode,
        result: result.result,
      }
    }
    if (result.ok && result.result?.onlineVerified) {
      const marked = await adminApi(token, `/api/cc-shipments/${encodeURIComponent(String(shipment.id))}/mark-relisted`, {
        method: 'POST',
        body: JSON.stringify({ status: 'online_verified' }),
      })
      return {
        ok: marked.ok,
        error: marked.error || '',
        shipmentId: shipment.id,
        queueType: pending.json?.queueType || '',
        mode,
        result: result.result,
      }
    }
  }
  return {
    ok: false,
    error: 'relist_button_not_found',
    shipmentId: shipment.id,
    queueType: pending.json?.queueType || '',
    mode,
  }
}

async function runOnce(token) {
  const browser = await discoverBrowser()
  if (!browser.ok) return browser
  if (dryRun) {
    return { ok: true, dryRun: true, port: browser.port, xianyuTabs: browser.xianyuPages.length }
  }
  if (openPageOnly) {
    return openSellerBrowserPage(browser, openPageDestination)
  }
  if (scanOnly) {
    const scans = []
    for (const target of browser.xianyuPages.slice(0, 8)) {
      scans.push(await scanDeliveryPage(target))
    }
    const readyPages = scans.filter((item) => item.readyToSend)
    const strictReadyPages = scans.filter((item) => item.strictReadyToSend)
    const ok = browser.xianyuPages.length === 1 && (
      requireRealOrderId ? strictReadyPages.length === 1 : readyPages.length === 1
    )
    return {
      ok,
      mode: 'scan_only',
      readOnly: true,
      port: browser.port,
      xianyuTabs: browser.xianyuPages.length,
      readyPages: readyPages.length,
      strictReadyPages: strictReadyPages.length,
      requireRealOrderId,
      scans,
      nextAction: buildDeliveryScanNextAction(browser, scans, readyPages, strictReadyPages),
      updatedAt: new Date().toISOString(),
    }
  }
  if (requireSingleXianyuPage && browser.xianyuPages.length !== 1) {
    return {
      ok: false,
      mode: oneShotOverride ? 'one_shot_delivery_only' : 'single_xianyu_page_required',
      port: browser.port,
      xianyuTabs: browser.xianyuPages.length,
      deliveries: [],
      confirms: [],
      relist: { ok: true, skipped: true, reason: 'single_xianyu_page_required' },
      error: `one_shot_requires_exactly_one_xianyu_page:${browser.xianyuPages.length}`,
      nextAction: '为了避免发错买家，请只保留 1 个真实已付款闲鱼聊天/订单页，再点“一键跑当前页”。',
      updatedAt: new Date().toISOString(),
    }
  }
  const oneShotAuthorization = oneShotOverride
    ? { ok: true, skipped: true, deferred: true, reason: 'authorize_after_paid_page_scan' }
    : await authorizeOneShotDelivery(token)
  if (!oneShotAuthorization.ok) {
    return {
      ok: false,
      stage: 'one_shot_authorize',
      error: oneShotAuthorization.error || 'one_shot_authorize_failed',
      status: oneShotAuthorization.status || 0,
    }
  }
  const status = await postBridgeStatus(token, browser.port, browser.xianyuPages.length)
  if (relistOnly) {
    if (browser.xianyuPages.length !== 1) {
      return {
        ok: false,
        mode: simulationRelist ? 'simulation_relist_only' : 'production_relist_only',
        port: browser.port,
        xianyuTabs: browser.xianyuPages.length,
        bridgeStatusPosted: status.ok,
        deliveries: [],
        confirms: [],
        relist: {
          ok: false,
          error: `relist_only_requires_exactly_one_xianyu_page:${browser.xianyuPages.length}`,
          reason: '只跑重新上架时必须只打开 1 个对应闲鱼商品页，避免点错宝贝。',
        },
        updatedAt: new Date().toISOString(),
      }
    }
    const relist = await handleRelistForPages(token, browser.xianyuPages.slice(0, 8), { simulation: simulationRelist })
    return {
      ok: Boolean(relist.ok),
      mode: simulationRelist ? 'simulation_relist_only' : 'production_relist_only',
      port: browser.port,
      xianyuTabs: browser.xianyuPages.length,
      bridgeStatusPosted: status.ok,
      deliveries: [],
      confirms: [],
      relist,
      updatedAt: new Date().toISOString(),
    }
  }
  const deliveries = []
  for (const target of browser.xianyuPages.slice(0, 8)) {
    deliveries.push(await handleDeliveryForPage(token, target))
  }
  if (deliveryOnly) {
    return {
      ok: true,
      mode: oneShotOverride ? 'one_shot_delivery_only' : 'delivery_only',
      oneShotOverride,
      oneShotAuthorization: oneShotAuthorization.json || oneShotAuthorization,
      port: browser.port,
      xianyuTabs: browser.xianyuPages.length,
      bridgeStatusPosted: status.ok,
      deliveries,
      confirms: [],
      relist: { ok: true, skipped: true, reason: 'delivery_only_mode' },
      updatedAt: new Date().toISOString(),
    }
  }
  const confirms = []
  for (const target of browser.xianyuPages.slice(0, 8)) {
    confirms.push(await handleStandaloneConfirmForPage(token, target))
  }
  const relist = await handleRelistForPages(token, browser.xianyuPages.slice(0, 8))
  return {
    ok: true,
    oneShotOverride,
    oneShotAuthorization: oneShotAuthorization.json || oneShotAuthorization,
    port: browser.port,
    xianyuTabs: browser.xianyuPages.length,
    bridgeStatusPosted: status.ok,
    deliveries,
    confirms,
    relist,
    updatedAt: new Date().toISOString(),
  }
}

async function main() {
  const env = parseEnvFile(envFile)
  const token = String(env.OPENCLAW_API_TOKEN || '').trim()
  if (!token) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: 'OPENCLAW_API_TOKEN missing' }, null, 2)}\n`)
    process.exit(1)
  }
  if (once) {
    const result = await runOnce(token)
    process.stdout.write(jsonOnly ? `${JSON.stringify(result, null, 2)}\n` : `CC中转卖家桥接器: ${result.ok ? 'OK' : 'FAIL'}\n${JSON.stringify(result, null, 2)}\n`)
    const scanCompleted = scanOnly && result?.mode === 'scan_only' && result?.readOnly === true
    process.exit(result.ok || scanCompleted ? 0 : 1)
  }
  process.stdout.write('CC中转卖家桥接器: WATCHING\n')
  for (;;) {
    const result = await runOnce(token).catch((error) => ({ ok: false, error: String(error.message || error) }))
    process.stdout.write(`${JSON.stringify(result, ensureReplacer, 2)}\n`)
    await new Promise((resolve) => setTimeout(resolve, watchIntervalMs))
  }
}

function ensureReplacer(_key, value) {
  if (typeof value === 'string' && value.length > 300) return `${value.slice(0, 300)}…`
  return value
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ ok: false, error: String(error.message || error) }, null, 2)}\n`)
  process.exit(1)
})

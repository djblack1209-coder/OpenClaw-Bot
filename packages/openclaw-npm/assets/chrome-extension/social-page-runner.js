export function runSocialFieldPlanInPage(payload = {}) {
  const platform = String(payload.platform || '').trim()
  const title = String(payload.title || '').trim()
  const text = String(payload.text || payload.bodyText || '').trim()
  const bodyText = String(payload.bodyText || payload.text || '').trim()
  const action = String(payload.action || 'autofill').trim()
  const fields = Array.isArray(payload.fields) ? payload.fields : []

  const isVisible = (el) => {
    if (!el) return false
    const rect = el.getBoundingClientRect()
    const style = globalThis.getComputedStyle(el)
    return rect.width > 20 && rect.height > 12 && style.visibility !== 'hidden' && style.display !== 'none'
  }

  const firstVisible = (selectors) => {
    for (const selector of selectors) {
      const nodes = Array.from(document.querySelectorAll(selector))
      const found = nodes.find(isVisible)
      if (found) return found
    }
    return null
  }

  const setNativeValue = (el, value) => {
    const tag = String(el.tagName || '').toLowerCase()
    const proto = tag === 'textarea'
      ? globalThis.HTMLTextAreaElement?.prototype
      : globalThis.HTMLInputElement?.prototype
    const descriptor = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null
    if (descriptor?.set) descriptor.set.call(el, value)
    else el.value = value
  }

  const fillElement = (el, value) => {
    if (!el || !value) return false
    el.focus()
    const tag = String(el.tagName || '').toLowerCase()
    if (tag === 'textarea' || tag === 'input') {
      setNativeValue(el, value)
    } else {
      const selection = globalThis.getSelection?.()
      const range = document.createRange()
      range.selectNodeContents(el)
      selection?.removeAllRanges()
      selection?.addRange(range)
      const inserted = document.execCommand?.('insertText', false, value)
      if (!inserted) el.textContent = value
    }
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }

  const result = {
    filled: false,
    platform,
    platformLabel: platform === 'xhs' ? '小红书' : platform === 'xianyu' ? '闲鱼' : platform === 'x' ? 'X' : '当前',
    fields: [],
    availableFields: [],
    publishClicked: false,
    action,
  }

  for (const field of fields) {
    const target = firstVisible(Array.isArray(field?.selectors) ? field.selectors : [])
    if (target) {
      result.availableFields.push({ name: String(field.name || ''), kind: String(field.kind || ''), tag: String(target.tagName || '').toLowerCase() })
    }
  }

  if (action === 'probe_fields') {
    result.filled = false
    result.ready = result.availableFields.length > 0
    if (!result.ready) result.reason = 'no_supported_input_found'
    return result
  }

  if (!text) {
    result.reason = 'empty_text'
    return result
  }

  const hasSeparateTitleField = fields.some((field) => field?.kind === 'title')

  for (const field of fields) {
    const target = firstVisible(Array.isArray(field?.selectors) ? field.selectors : [])
    const value = field.kind === 'title'
      ? title
      : hasSeparateTitleField ? (bodyText || text) : text
    if (fillElement(target, value)) {
      result.fields.push(String(field.name || field.kind || 'field'))
    }
  }

  result.filled = result.fields.length > 0
  if (!result.filled) result.reason = `${platform || 'unsupported'}_input_not_found`
  return result
}


export function runSocialInteractionScanInPage(payload = {}) {
  const platform = String(payload.platform || '').trim()
  const limit = Math.min(12, Math.max(1, Number(payload.limit || 8)))
  const selectorMap = {
    x: ['[data-testid="tweetText"]', 'article [lang]', 'article div[dir="auto"]'],
    xhs: ['.comment-item', '[class*="comment"]', '[data-v] [class*="content"]'],
    xianyu: ['[class*="message"]', '[class*="chat"]', '[class*="comment"]'],
  }
  const selectors = Array.isArray(payload.selectors) && payload.selectors.length
    ? payload.selectors
    : (selectorMap[platform] || selectorMap.x)

  const isVisible = (el) => {
    if (!el) return false
    const rect = el.getBoundingClientRect()
    const style = globalThis.getComputedStyle(el)
    return rect.width > 20 && rect.height > 12 && style.visibility !== 'hidden' && style.display !== 'none'
  }

  const cleanText = (value, max = 220) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, max)
  const seen = new Set()
  const signals = []
  for (const selector of selectors) {
    const nodes = Array.from(document.querySelectorAll(selector))
    for (const node of nodes) {
      if (!isVisible(node)) continue
      const text = cleanText(node.innerText || node.textContent || '')
      if (text.length < 6 || seen.has(text.toLowerCase())) continue
      seen.add(text.toLowerCase())
      const author = cleanText(node.getAttribute?.('aria-label') || node.closest?.('[data-author]')?.getAttribute?.('data-author') || '', 80)
      signals.push({
        id: cleanText(node.id || node.dataset?.testid || `${platform}:${signals.length}:${text}`, 160),
        text,
        author: author || 'unknown',
        metric: '',
        intent: 'reply_candidate',
        reply_angle: platform === 'xianyu' ? '先判断买家意图，再给出成交回复建议' : '用轻量、有信息量的回复承接互动',
        auto_reply_enabled: false,
        auto_publish_enabled: false,
        external_actions_locked: true,
      })
      if (signals.length >= limit) break
    }
    if (signals.length >= limit) break
  }

  return {
    ready: signals.length > 0,
    platform,
    action: 'scan_interactions',
    signals,
    count: signals.length,
    auto_reply_enabled: false,
    auto_publish_enabled: false,
    external_actions_locked: true,
    reason: signals.length ? '' : 'no_interaction_signal_found',
  }
}

export function runSocialPageContextScanInPage(payload = {}) {
  const platform = String(payload.platform || '').trim()
  const limit = Math.min(18, Math.max(3, Number(payload.limit || 12)))
  const selectorMap = {
    x: {
      trends: ['[data-testid="trend"]', '[aria-label*="Trending"] [dir="auto"]', '[data-testid="trendName"]'],
      headings: ['article [data-testid="User-Name"]', 'h1', 'h2'],
      body: ['[data-testid="tweetText"]', 'article [lang]', 'article div[dir="auto"]'],
    },
    xhs: {
      trends: ['[class*="hot"]', '[class*="trend"]', '[class*="search"] [class*="title"]'],
      headings: ['[class*="note"] [class*="title"]', '[class*="title"]', 'h1', 'h2'],
      body: ['[class*="content"]', '[class*="desc"]', '[class*="comment"]'],
    },
    xianyu: {
      trends: ['[class*="recommend"]', '[class*="hot"]', '[class*="tag"]'],
      headings: ['[class*="item"] [class*="title"]', '[class*="title"]', 'h1', 'h2'],
      body: ['[class*="message"]', '[class*="chat"]', '[class*="comment"]', '[class*="desc"]'],
    },
  }
  const selectors = payload.selectors && typeof payload.selectors === 'object'
    ? payload.selectors
    : (selectorMap[platform] || selectorMap.x)

  const isVisible = (el) => {
    if (!el) return false
    const rect = el.getBoundingClientRect()
    const style = globalThis.getComputedStyle(el)
    return rect.width > 20 && rect.height > 10 && style.visibility !== 'hidden' && style.display !== 'none'
  }
  const cleanText = (value, max = 220) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, max)
  const collectTexts = (queryList = [], maxItems = limit, minLength = 2) => {
    const seen = new Set()
    const texts = []
    for (const selector of queryList) {
      const nodes = Array.from(document.querySelectorAll(selector))
      for (const node of nodes) {
        if (!isVisible(node)) continue
        const text = cleanText(node.innerText || node.textContent || node.getAttribute?.('aria-label') || '')
        const key = text.toLowerCase()
        if (text.length < minLength || seen.has(key)) continue
        seen.add(key)
        texts.push(text)
        if (texts.length >= maxItems) break
      }
      if (texts.length >= maxItems) break
    }
    return texts
  }

  const selection = cleanText(globalThis.getSelection?.()?.toString?.() || '', 800)
  const trends = collectTexts(selectors.trends || [], 12, 2)
  const headings = collectTexts(selectors.headings || [], 8, 2)
  const bodyCandidates = collectTexts(selectors.body || [], limit, 4)
  const bodyText = cleanText(bodyCandidates.join('\n'), 1200)
  const ready = Boolean(selection || trends.length || headings.length || bodyText)

  return {
    ready,
    platform,
    url: String(payload.url || globalThis.location?.href || '').slice(0, 500),
    title: cleanText(payload.title || document.title || '', 160),
    selection,
    headings,
    trends,
    bodyText,
    action: 'scan_page_context',
    count: trends.length + headings.length + bodyCandidates.length,
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
    reason: ready ? '' : 'no_page_context_found',
  }
}


const XIANYU_PAID_SIGNAL_PATTERNS = [
  /买家已付款/,
  /我已付款/,
  /已付款/,
  /待发货/,
  /等待卖家发货/,
  /等待你发货/,
  /卖家待发货/,
  /付款成功/,
  /提醒发货/,
  /记得及时发货/,
]

const XIANYU_CHAT_INPUT_SELECTORS = [
  'textarea[placeholder*="回复"]',
  'textarea[placeholder*="请输入"]',
  'textarea[placeholder*="想跟"]',
  'textarea[placeholder*="说点什么"]',
  'input[placeholder*="回复"]',
  'input[placeholder*="想跟"]',
  'input[placeholder*="说点什么"]',
  'div[contenteditable="true"][placeholder*="回复"]',
  'div[contenteditable="true"][placeholder*="想跟"]',
  'div[contenteditable="true"][placeholder*="说点什么"]',
  'div[contenteditable="true"][data-placeholder*="回复"]',
  'div[contenteditable="true"][data-placeholder*="请输入"]',
  'div[contenteditable="true"][data-placeholder*="想跟"]',
  'div[contenteditable="true"][data-placeholder*="说点什么"]',
  'div[contenteditable="true"][aria-placeholder*="回复"]',
  'div[contenteditable="true"][aria-placeholder*="想跟"]',
  'div[contenteditable="true"][aria-placeholder*="说点什么"]',
  'div[contenteditable="true"][aria-label*="回复"]',
  'div[contenteditable="true"][aria-label*="想跟"]',
  'div[contenteditable="true"][aria-label*="说点什么"]',
  'div[contenteditable="true"][role="textbox"]',
  '[role="textbox"][contenteditable="true"]',
  'textarea',
]

function isVisibleNode(el) {
  if (!el) return false
  const rect = el.getBoundingClientRect()
  const style = globalThis.getComputedStyle(el)
  return rect.width > 20 && rect.height > 10 && style.visibility !== 'hidden' && style.display !== 'none'
}

function cleanVisibleText(value, max = 5000) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max)
}

function findFirstVisible(selectors = []) {
  for (const selector of selectors) {
    const nodes = Array.from(document.querySelectorAll(selector))
    const found = nodes.find(isVisibleNode)
    if (found) return found
  }
  return null
}

function setElementTextValue(el, value) {
  if (!el) return false
  el.focus()
  const tag = String(el.tagName || '').toLowerCase()
  if (tag === 'textarea' || tag === 'input') {
    const proto = tag === 'textarea'
      ? globalThis.HTMLTextAreaElement?.prototype
      : globalThis.HTMLInputElement?.prototype
    const descriptor = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null
    if (descriptor?.set) descriptor.set.call(el, value)
    else el.value = value
  } else {
    const selection = globalThis.getSelection?.()
    const range = document.createRange()
    range.selectNodeContents(el)
    selection?.removeAllRanges()
    selection?.addRange(range)
    const inserted = document.execCommand?.('insertText', false, value)
    if (!inserted) el.textContent = value
  }
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}

function getElementTextValue(el) {
  if (!el) return ''
  const tag = String(el.tagName || '').toLowerCase()
  if (tag === 'textarea' || tag === 'input') return String(el.value || '')
  return String(el.innerText || el.textContent || '')
}

function extractDeliveryCodes(value) {
  const matches = String(value || '').toUpperCase().match(/\b[A-Z]{2,10}-[A-Z0-9][A-Z0-9-]{3,}\b/g)
  return new Set(matches || [])
}

function hasDuplicateDeliveryDraft(input, message) {
  const current = getElementTextValue(input).trim()
  const target = String(message || '').trim()
  if (!current || !target) return false
  if (current === target) return true
  const currentCodes = extractDeliveryCodes(current)
  if (!currentCodes.size) return false
  const targetCodes = extractDeliveryCodes(target)
  for (const code of currentCodes) {
    if (targetCodes.has(code)) return true
  }
  return false
}

function looksLikeDeliveryDraft(value) {
  const text = String(value || '').trim()
  if (!text) return false
  const codes = extractDeliveryCodes(text)
  if (!codes.size) return false
  return /兑换码|兑换入口|自动发货|jiyu\.245334\.xyz|cc中转/i.test(text)
}

function supportsEnterSend(input) {
  const hint = [
    input?.placeholder,
    input?.getAttribute?.('placeholder'),
    input?.getAttribute?.('aria-label'),
    input?.getAttribute?.('data-placeholder'),
  ].filter(Boolean).join(' ')
  return /enter|回车|按Enter键发送|按\s*Enter/i.test(hint)
}

function pressEnterToSend(input) {
  if (!input || !supportsEnterSend(input)) return false
  input.focus()
  const keyOptions = { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }
  input.dispatchEvent(new KeyboardEvent('keydown', keyOptions))
  input.dispatchEvent(new KeyboardEvent('keyup', keyOptions))
  return true
}

function findXianyuSendButton() {
  const candidates = Array.from(document.querySelectorAll('button,[role="button"],a'))
  return candidates.find((node) => {
    if (!isVisibleNode(node)) return false
    const text = cleanVisibleText(node.innerText || node.textContent || node.getAttribute?.('aria-label') || '', 40)
    if (!/(发送|Send)/i.test(text)) return false
    if (node.disabled || node.getAttribute?.('aria-disabled') === 'true') return false
    return true
  }) || null
}

function visibleButtonText(node) {
  return cleanVisibleText(node?.innerText || node?.textContent || node?.getAttribute?.('aria-label') || '', 80)
}

function findXianyuShipmentButton(pattern, { exclude = null } = {}) {
  const candidates = Array.from(document.querySelectorAll('button,[role="button"],a'))
  return candidates.find((node) => {
    if (!isVisibleNode(node)) return false
    if (node.disabled || node.getAttribute?.('aria-disabled') === 'true') return false
    const text = visibleButtonText(node)
    if (!pattern.test(text)) return false
    if (exclude && exclude.test(text)) return false
    return true
  }) || null
}

const XIANYU_REAL_ORDER_PARAM_KEYS = ['orderId', 'tradeId', 'bizOrderId', 'biz_order_id']
const XIANYU_REAL_ORDER_DATA_KEYS = [
  'orderId',
  'orderid',
  'tradeId',
  'tradeid',
  'bizOrderId',
  'bizorderId',
  'bizorderid',
  'biz_order_id',
]
const XIANYU_REAL_ORDER_ATTRIBUTE_KEYS = [
  'data-order-id',
  'data-orderid',
  'data-trade-id',
  'data-tradeid',
  'data-biz-order-id',
  'data-bizorder-id',
  'data-bizorderid',
]
const XIANYU_ORDER_ID_NODE_SELECTOR = [
  'a[href]',
  '[href]',
  '[data-order-id]',
  '[data-orderid]',
  '[data-trade-id]',
  '[data-tradeid]',
  '[data-biz-order-id]',
  '[data-bizorder-id]',
  '[data-bizorderid]',
].join(',')

function normalizeXianyuRealOrderIdCandidate(value, minLength = 10) {
  const candidate = String(value || '').trim()
  if (!candidate) return ''
  if (!/^[A-Za-z0-9_-]{6,80}$/.test(candidate)) return ''
  if (candidate.length < minLength) return ''
  return candidate
}

function extractXianyuOrderIdFromUrlValue(value, minLength = 6) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const tryParse = (candidateUrl) => {
    try {
      const url = new URL(candidateUrl, String(globalThis.location?.href || 'https://www.goofish.com/'))
      for (const key of XIANYU_REAL_ORDER_PARAM_KEYS) {
        const normalized = normalizeXianyuRealOrderIdCandidate(url.searchParams.get(key), minLength)
        if (normalized) return normalized
      }
    } catch {
      // 非 URL 字符串继续走白名单参数正则。
    }
    return ''
  }
  const parsed = tryParse(raw)
  if (parsed) return parsed
  const paramMatch = raw.match(/(?:orderId|tradeId|bizOrderId|biz_order_id)[=:\s"']+([A-Za-z0-9_-]{10,80})/i)
  if (paramMatch) return normalizeXianyuRealOrderIdCandidate(paramMatch[1], 10)
  return ''
}

function extractXianyuOrderIdFromDomHints() {
  const nodes = Array.from(document.querySelectorAll(XIANYU_ORDER_ID_NODE_SELECTOR)).slice(0, 80)
  for (const node of nodes) {
    const visibleText = cleanVisibleText(
      node?.innerText || node?.textContent || node?.getAttribute?.('aria-label') || '',
      120,
    )
    const looksRelevant = isVisibleNode(node) || /订单|交易|发货|待发货|去发货|物流/i.test(visibleText)
    if (!looksRelevant) continue

    for (const key of XIANYU_REAL_ORDER_DATA_KEYS) {
      const normalized = normalizeXianyuRealOrderIdCandidate(node?.dataset?.[key], 10)
      if (normalized) return normalized
    }
    for (const attr of XIANYU_REAL_ORDER_ATTRIBUTE_KEYS) {
      const normalized = normalizeXianyuRealOrderIdCandidate(node?.getAttribute?.(attr), 10)
      if (normalized) return normalized
    }
    const hrefOrderId = extractXianyuOrderIdFromUrlValue(node?.getAttribute?.('href') || node?.href || '', 10)
    if (hrefOrderId) return hrefOrderId
  }
  return ''
}

function extractXianyuRealOrderId(pageText = '') {
  const fromUrl = extractXianyuOrderIdFromUrlValue(String(globalThis.location?.href || ''), 6)
  if (fromUrl) return fromUrl
  const text = cleanVisibleText(pageText, 6000)
  const labeled = text.match(/(?:订单号|订单编号|交易号|交易编号|订单ID|交易ID)[:：\s#-]*([A-Za-z0-9_-]{10,80})/i)
  if (labeled) return labeled[1]
  return extractXianyuOrderIdFromDomHints()
}

function xianyuDeliveryPageSignals() {
  const body = document.body
  const pageText = cleanVisibleText(body?.innerText || body?.textContent || '', 6000)
  const orderIdHint = extractXianyuRealOrderId(pageText)
  const shipAction = findXianyuShipmentButton(/去发货|确认发货|发货|无需物流|查看物流/)
  const orderCardPresent = /等待卖家发货|待发货|卖家待发货/.test(pageText) && /¥|￥|含运费|去发货|订单/.test(pageText)
  const paidSignals = XIANYU_PAID_SIGNAL_PATTERNS
    .filter((pattern) => pattern.test(pageText))
    .map((pattern) => pattern.source.replace(/\\/g, ''))
  const input = findFirstVisible(XIANYU_CHAT_INPUT_SELECTORS)
  const sendButton = findXianyuSendButton()
  return {
    pageText,
    paidSignals,
    hasPaidSignal: paidSignals.length > 0,
    inputReady: Boolean(input),
    sendButtonReady: Boolean(sendButton),
    inputTag: input ? String(input.tagName || '').toLowerCase() : '',
    orderIdHint,
    orderCardPresent,
    shipActionPresent: Boolean(shipAction),
  }
}

export function runXianyuDeliveryScanInPage(payload = {}) {
  const signals = xianyuDeliveryPageSignals()
  return {
    ready: Boolean(signals.hasPaidSignal && signals.inputReady),
    platform: 'xianyu',
    action: 'cc_delivery_scan',
    paidSignal: signals.hasPaidSignal,
    paidSignals: signals.paidSignals,
    inputReady: signals.inputReady,
    sendButtonReady: signals.sendButtonReady,
    inputTag: signals.inputTag,
    orderIdHint: signals.orderIdHint,
    orderCardPresent: signals.orderCardPresent,
    shipActionPresent: signals.shipActionPresent,
    reason: signals.hasPaidSignal
      ? signals.inputReady ? '' : 'no_chat_input_found'
      : 'no_paid_order_signal',
    external_actions_locked: false,
    note: payload.note || '只检测当前可见闲鱼页面，不读取 Cookie，不跨商品群发。',
  }
}

export function runXianyuDeliveryDraftCleanupInPage(payload = {}) {
  const shipmentId = String(payload.shipmentId || '')
  const requirePaidSignal = payload.requirePaidSignal !== false
  const signals = xianyuDeliveryPageSignals()
  const result = {
    ready: false,
    platform: 'xianyu',
    action: 'cc_delivery_draft_cleanup',
    shipmentId,
    paidSignal: signals.hasPaidSignal,
    paidSignals: signals.paidSignals,
    inputReady: signals.inputReady,
    clearedDraft: false,
    reason: '',
    external_actions_locked: false,
  }
  if (requirePaidSignal && !signals.hasPaidSignal) {
    result.reason = 'no_paid_order_signal'
    return result
  }
  const input = findFirstVisible(XIANYU_CHAT_INPUT_SELECTORS)
  if (!input) {
    result.reason = 'no_chat_input_found'
    return result
  }
  const current = getElementTextValue(input)
  if (!looksLikeDeliveryDraft(current)) {
    result.ready = true
    result.reason = 'no_delivery_draft_found'
    return result
  }
  setElementTextValue(input, '')
  result.ready = true
  result.clearedDraft = true
  result.reason = 'delivery_draft_cleared'
  return result
}

export function runXianyuDeliveryFillAndSendInPage(payload = {}) {
  const message = String(payload.deliveryMessage || payload.message || '').trim()
  const shipmentId = String(payload.shipmentId || '')
  const requirePaidSignal = payload.requirePaidSignal !== false
  const clickSend = payload.clickSend !== false
  const signals = xianyuDeliveryPageSignals()
  const result = {
    ready: false,
    platform: 'xianyu',
    action: 'cc_delivery_fill_and_send',
    shipmentId,
    paidSignal: signals.hasPaidSignal,
    paidSignals: signals.paidSignals,
    inputReady: signals.inputReady,
    sendButtonReady: signals.sendButtonReady,
    sendMethod: '',
    filled: false,
    sent: false,
    clearedDuplicateDraft: false,
    reason: '',
    external_actions_locked: false,
  }
  if (!message) {
    result.reason = 'empty_delivery_message'
    return result
  }
  if (requirePaidSignal && !signals.hasPaidSignal) {
    result.reason = 'no_paid_order_signal'
    return result
  }
  const input = findFirstVisible(XIANYU_CHAT_INPUT_SELECTORS)
  if (!input) {
    result.reason = 'no_chat_input_found'
    return result
  }
  if (hasDuplicateDeliveryDraft(input, message)) {
    setElementTextValue(input, '')
    result.clearedDuplicateDraft = true
    result.reason = 'duplicate_delivery_draft_cleared'
    result.ready = true
    return result
  }
  result.filled = setElementTextValue(input, message)
  if (!result.filled) {
    result.reason = 'fill_failed'
    return result
  }
  const sendButton = findXianyuSendButton()
  if (!sendButton) {
    if (clickSend && pressEnterToSend(input)) {
      result.sent = true
      result.sendMethod = 'enter'
      result.ready = true
      return result
    }
    result.reason = 'send_button_not_found'
    result.ready = true
    return result
  }
  if (clickSend) {
    sendButton.click()
    result.sent = true
    result.sendMethod = 'button'
  }
  result.ready = true
  return result
}

export function runXianyuConfirmShipmentInPage(payload = {}) {
  const shipmentId = String(payload.shipmentId || '')
  const requirePaidSignal = payload.requirePaidSignal !== false
  const clickButtons = payload.clickButtons !== false
  const signals = xianyuDeliveryPageSignals()
  const result = {
    ready: false,
    platform: 'xianyu',
    action: 'cc_confirm_shipment',
    shipmentId,
    paidSignal: signals.hasPaidSignal,
    paidSignals: signals.paidSignals,
    clickedTexts: [],
    confirmed: false,
    reason: '',
    external_actions_locked: false,
  }
  if (requirePaidSignal && !signals.hasPaidSignal) {
    result.reason = 'no_paid_order_signal'
    return result
  }

  const steps = [
    { key: 'open_ship', pattern: /(去发货|立即发货|我要发货|发货)/, exclude: /(确认|确定|已发货)/ },
    { key: 'no_logistics', pattern: /(无需物流|虚拟商品|无需配送|不需要物流|已与买家协商无需物流)/ },
    { key: 'confirm', pattern: /(确认发货|确定发货|确认|确定)/ },
  ]
  let clickedAny = false
  for (const step of steps) {
    const button = findXianyuShipmentButton(step.pattern, { exclude: step.exclude || null })
    if (!button) continue
    const text = visibleButtonText(button)
    if (clickButtons) button.click()
    result.clickedTexts.push(text)
    clickedAny = true
    if (step.key === 'confirm') result.confirmed = true
  }
  if (!clickedAny) {
    result.reason = 'shipment_button_not_found'
    return result
  }
  if (!result.confirmed) {
    const doneSignal = /(已发货|卖家已发货|交易成功|待收货)/.test(signals.pageText)
    result.confirmed = doneSignal
    if (!doneSignal) result.reason = 'confirm_button_not_found'
  }
  result.ready = true
  return result
}

export function runXianyuRelistItemInPage(payload = {}) {
  const itemId = String(payload.itemId || '')
  const clickButton = payload.clickButton !== false
  const body = document.body
  const pageText = cleanVisibleText(body?.innerText || body?.textContent || '', 6000)
  const pageUrl = String(payload.url || globalThis.location?.href || '').slice(0, 500)
  // 闲鱼商品详情页能正常打开，且没有下架/失效文案时，视为宝贝仍在线。
  const itemDetailUrlSignal = /(?:^https?:\/\/)?(?:www\.)?goofish\.com\/item\?/i.test(pageUrl)
  const result = {
    ready: false,
    platform: 'xianyu',
    action: 'cc_relist_item',
    itemId,
    unavailableSignal: /(已下架|已售罄|售罄|商品已失效|宝贝已下架)/.test(pageText),
    onlineSignal: /(在售中|出售中|正常展示|已发布|宝贝在售|商品在售)/.test(pageText),
    itemDetailUrlSignal,
    onlineVerified: false,
    relisted: false,
    clickedText: '',
    reason: '',
    external_actions_locked: false,
  }
  if (!result.unavailableSignal) {
    if (result.onlineSignal) {
      result.onlineVerified = true
      result.ready = true
      result.reason = 'item_already_online'
      return result
    }
    if (result.itemDetailUrlSignal) {
      result.onlineVerified = true
      result.ready = true
      result.reason = 'item_detail_online'
      return result
    }
    result.reason = 'item_not_unavailable'
    return result
  }
  const button = findXianyuShipmentButton(/(重新上架|恢复上架|再次上架|上架)/)
  if (!button) {
    result.reason = 'relist_button_not_found'
    return result
  }
  result.clickedText = visibleButtonText(button)
  if (clickButton) button.click()
  result.relisted = true
  result.ready = true
  return result
}

export function runSocialPerformanceScanInPage(payload = {}) {
  const platform = String(payload.platform || '').trim()
  const selectorMap = {
    x: {
      likes: ['[data-testid="like"]', '[aria-label*="Like"]', '[aria-label*="like"]'],
      comments: ['[data-testid="reply"]', '[aria-label*="Reply"]', '[aria-label*="repl"]'],
      shares: ['[data-testid="retweet"]', '[aria-label*="Repost"]', '[aria-label*="repost"]', '[aria-label*="Retweet"]'],
      impressions: ['[aria-label*="views"]', '[aria-label*="Views"]', '[aria-label*="view"]'],
      saves: ['[data-testid="bookmark"]', '[aria-label*="Bookmark"]'],
    },
    xhs: {
      likes: ['[class*="like"]', '[aria-label*="点赞"]'],
      comments: ['[class*="comment"]', '[aria-label*="评论"]'],
      shares: ['[class*="share"]', '[aria-label*="分享"]'],
      impressions: ['[class*="view"]', '[aria-label*="浏览"]'],
      saves: ['[class*="collect"]', '[aria-label*="收藏"]'],
    },
    xianyu: {
      likes: ['[class*="want"]', '[class*="like"]'],
      comments: ['[class*="message"]', '[class*="chat"]', '[class*="comment"]'],
      shares: ['[class*="share"]'],
      impressions: ['[class*="view"]', '[aria-label*="浏览"]'],
      saves: ['[class*="collect"]', '[class*="favorite"]'],
    },
  }
  const selectors = payload.selectors && typeof payload.selectors === 'object'
    ? payload.selectors
    : (selectorMap[platform] || selectorMap.x)

  const isVisible = (el) => {
    if (!el) return false
    const rect = el.getBoundingClientRect()
    const style = globalThis.getComputedStyle(el)
    return rect.width > 12 && rect.height > 8 && style.visibility !== 'hidden' && style.display !== 'none'
  }
  const cleanText = (value, max = 160) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, max)
  const parseMetric = (value) => {
    const raw = cleanText(value).toLowerCase().replace(/,/g, '')
    const match = raw.match(/([0-9]+(?:\.[0-9]+)?)(\s*[kKmM万wW])?/)
    if (!match) return 0
    let n = Number(match[1])
    if (!Number.isFinite(n)) return 0
    const suffix = String(match[2] || '').trim().toLowerCase()
    if (suffix === 'k') n *= 1000
    if (suffix === 'm') n *= 1000000
    if (suffix === '万' || suffix === 'w') n *= 10000
    return Math.max(0, Math.round(n))
  }
  const readMetric = (metricSelectors = []) => {
    for (const selector of metricSelectors) {
      const nodes = Array.from(document.querySelectorAll(selector))
      for (const node of nodes) {
        if (!isVisible(node)) continue
        const text = cleanText(node.getAttribute?.('aria-label') || node.innerText || node.textContent || '')
        const parsed = parseMetric(text)
        if (parsed > 0) return parsed
      }
    }
    return 0
  }

  const metrics = {
    likes: readMetric(selectors.likes || []),
    comments: readMetric(selectors.comments || []),
    shares: readMetric(selectors.shares || []),
    impressions: readMetric(selectors.impressions || []),
    saves: readMetric(selectors.saves || []),
  }
  metrics.engagements = metrics.likes + metrics.comments + metrics.shares + metrics.saves
  metrics.engagement_rate = metrics.impressions > 0 ? Number((metrics.engagements / metrics.impressions).toFixed(6)) : 0
  const ready = Object.values(metrics).some((value) => Number(value) > 0)

  return {
    ready,
    platform,
    url: String(payload.url || globalThis.location?.href || '').slice(0, 500),
    title: String(payload.title || document.title || '').replace(/\s+/g, ' ').trim().slice(0, 140),
    action: 'scan_performance',
    metrics,
    captured_at: new Date().toISOString(),
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
    reason: ready ? '' : 'no_visible_performance_metric_found',
  }
}

/**
 * 闲鱼 PC 聊天头信息解析器。
 *
 * 只在“已付款/待发货/去发货”上下文里提取真实订单号，避免把商品 ID 当成严格门订单证据。
 */

const ORDER_ID_PATTERN = /^\d{10,30}$/
const ORDER_KEY_PATTERN = /^(orderId|tradeId|bizOrderId|biz_order_id)$/i
const ORDERISH_KEY_PATTERN = /(order|trade|biz_order|bizorder)/i
const ITEMISH_KEY_PATTERN = /(item|goods|product)/i
const ITEM_KEY_PATTERN = /^(itemId|item_id|itemIdStr|item_id_str)$/i
const PAID_DELIVERY_CONTEXT_PATTERN = /已付款|已经付款|买家拍下了宝贝，并且已经付款|等待卖家发货|待发货|卖家待发货|LOGISTICS_SEND|去发货|order_detail|idle-logistics|pages\/deliver/i

function parsePayload(payloadTextOrJson) {
  if (payloadTextOrJson && typeof payloadTextOrJson === 'object') return payloadTextOrJson
  const raw = String(payloadTextOrJson || '').trim()
  if (!raw) return null
  const candidates = [raw]
  const firstParen = raw.indexOf('(')
  const lastParen = raw.lastIndexOf(')')
  if (firstParen > 0 && lastParen > firstParen) candidates.push(raw.slice(firstParen + 1, lastParen))
  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate)
    } catch {
      // 继续尝试下一个候选文本。
    }
  }
  return raw
}

function safeStringify(value) {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value || '')
  }
}

function normalizeOrderId(value) {
  const raw = String(value || '').trim()
  if (ORDER_ID_PATTERN.test(raw)) return raw
  const match = raw.match(/\b(\d{10,30})\b/)
  return match && ORDER_ID_PATTERN.test(match[1]) ? match[1] : ''
}

function extractOrderIdFromOrderUrl(value) {
  const raw = String(value || '')
  if (!/order_detail|idle-logistics|pages\/deliver|orderId=|tradeId=|bizOrderId=|biz_order_id=/i.test(raw)) return ''
  const decoded = safeDecode(raw)
  const paramMatch = decoded.match(/(?:orderId|tradeId|bizOrderId|biz_order_id)[=:\s"']+(\d{10,30})/i)
  if (paramMatch) return paramMatch[1]
  const detailMatch = decoded.match(/order_detail\?[^"'\s]*\bid=(\d{10,30})/i)
  if (detailMatch) return detailMatch[1]
  return ''
}

function safeDecode(value) {
  try {
    return decodeURIComponent(String(value || ''))
  } catch {
    return String(value || '')
  }
}

function collectOrderCandidates(value, path = [], output = []) {
  if (value == null) return output
  if (typeof value === 'string' || typeof value === 'number') {
    const key = String(path[path.length - 1] || '')
    const text = String(value)
    const fromUrl = extractOrderIdFromOrderUrl(text)
    if (fromUrl) output.push({ orderId: fromUrl, source: `${path.join('.') || 'text'}:order_url` })
    if (ORDER_KEY_PATTERN.test(key)) {
      const direct = normalizeOrderId(text)
      if (direct) output.push({ orderId: direct, source: `${path.join('.')}:order_key` })
    } else if (ORDERISH_KEY_PATTERN.test(key) && !ITEMISH_KEY_PATTERN.test(key)) {
      const direct = normalizeOrderId(text)
      if (direct) output.push({ orderId: direct, source: `${path.join('.')}:orderish_key` })
    }
    return output
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => collectOrderCandidates(item, [...path, String(index)], output))
    return output
  }
  if (typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      collectOrderCandidates(child, [...path, key], output)
    }
  }
  return output
}

function collectItemCandidates(value, path = [], output = []) {
  if (value == null) return output
  if (typeof value === 'string' || typeof value === 'number') {
    const key = String(path[path.length - 1] || '')
    const text = String(value).trim()
    if (ITEM_KEY_PATTERN.test(key) && /^[A-Za-z0-9_-]{4,80}$/.test(text)) {
      output.push({ itemId: text, source: `${path.join('.')}:item_key` })
    }
    return output
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => collectItemCandidates(item, [...path, String(index)], output))
    return output
  }
  if (typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      collectItemCandidates(child, [...path, key], output)
    }
  }
  return output
}

/**
 * 从闲鱼 message.headinfo 响应中提取真实订单号。
 * @param {unknown} payloadTextOrJson 闲鱼 headinfo JSON、JSONP 或对象
 * @returns {{ok: boolean, orderId: string, itemId: string, source: string, itemSource: string, reason: string}}
 */
export function extractXianyuOrderIdFromHeadInfoPayload(payloadTextOrJson) {
  const parsed = parsePayload(payloadTextOrJson)
  const flattened = safeStringify(parsed)
  const item = collectItemCandidates(parsed).find((candidate) => candidate.itemId) || { itemId: '', source: '' }
  if (!PAID_DELIVERY_CONTEXT_PATTERN.test(flattened)) {
    return { ok: false, orderId: '', itemId: item.itemId, source: '', itemSource: item.source, reason: 'paid_delivery_context_missing' }
  }
  const candidates = collectOrderCandidates(parsed)
  const first = candidates.find((candidate) => ORDER_ID_PATTERN.test(candidate.orderId))
  if (!first) return { ok: false, orderId: '', itemId: item.itemId, source: '', itemSource: item.source, reason: 'order_id_missing' }
  return { ok: true, orderId: first.orderId, itemId: item.itemId, source: first.source, itemSource: item.source, reason: '' }
}

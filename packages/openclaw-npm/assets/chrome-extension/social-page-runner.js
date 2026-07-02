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

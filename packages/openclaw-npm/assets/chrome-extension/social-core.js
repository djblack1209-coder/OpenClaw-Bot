export const SUPPORTED_PLATFORMS = {
  x: {
    id: 'x',
    label: 'X',
    tone: '财富出海 · AI 工具 · Web3 · 美股',
    hosts: ['x.com', 'twitter.com'],
  },
  xhs: {
    id: 'xhs',
    label: '小红书',
    tone: '生活方式 · 女性向攻略 · 图文教程',
    hosts: ['xiaohongshu.com', 'www.xiaohongshu.com', 'creator.xiaohongshu.com'],
  },
  xianyu: {
    id: 'xianyu',
    label: '闲鱼',
    tone: '客服成交 · 商品优化 · 砍价回复',
    hosts: ['goofish.com', 'www.goofish.com', '2.taobao.com', 'm.tb.cn', 'tb.cn', 'idlefish'],
  },
}

export const DEFAULT_SOCIAL_SETTINGS = {
  strategyPreset: 'auto_mcn_growth',
  personaTags: ['科技', '出海', 'AI赚钱'],
  contentModel: 'web-gemini',
  imageModel: 'gpt-image',
  trendSources: ['extension-page', 'local-pool', 'cloud-pool'],
  automationLevel: 'draft_only',
  interactionLevel: 'off',
  apiBaseUrl: 'http://127.0.0.1:18790/api/v1',
}

export const STRATEGY_PRESET_OPTIONS = {
  auto_mcn_growth: '自动匹配平台涨粉打法（推荐）',
  x_wealth_frontier: 'X 财富前沿实操',
  x_absurd_growth: 'X 抽象热点涨粉',
  xhs_lifestyle_tutorial: '小红书生活攻略',
  xianyu_deal_closer: '闲鱼成交客服',
}

export const PERSONA_TAG_OPTIONS = [
  '生活',
  '金融',
  '科技',
  '学生',
  '健身',
  '女性向',
  '出海',
  'AI赚钱',
  'Web3',
  '二手交易',
]

export const CONTENT_MODEL_OPTIONS = {
  'web-gemini': 'Gemini 网页额度优先',
  'web-grok': 'Grok 网页额度优先',
  'web-chatgpt': 'ChatGPT 网页额度优先',
  'api-main': '主 API Key',
  'local-free': '本地免费模型',
}

export const IMAGE_MODEL_OPTIONS = {
  'gpt-image': 'GPT Image 高质量',
  'web-gemini-image': 'Gemini 网页生图',
  'api-image': '生图 API',
  none: '暂不生成图片',
}

export const TREND_SOURCE_OPTIONS = {
  'extension-page': '当前页面',
  'local-pool': 'Mac 本地热点池',
  'cloud-pool': '云端热点池',
  x: 'X 热点',
  xhs: '小红书热点',
  bilibili: 'B站热榜',
  github: 'GitHub/HN',
}

export const AUTOMATION_LEVELS = {
  draft_only: '只生成草稿',
  autofill: '自动填入页面',
  reviewed_publish: '审核后发布',
  low_risk_auto: '低风险全自动',
}

export const INTERACTION_LEVELS = {
  off: '关闭',
  own_comments: '只回复评论区',
  light: '轻互动',
  standard: '标准互动',
}

export function normalizeHost(url) {
  try {
    return new URL(url || '').hostname.replace(/^www\./, '').toLowerCase()
  } catch {
    return ''
  }
}

export function detectSocialPlatform(url) {
  const host = normalizeHost(url)
  if (!host) {
    return { id: 'unsupported', label: '未识别页面', supported: false, host: '' }
  }
  for (const platform of Object.values(SUPPORTED_PLATFORMS)) {
    if (platform.hosts.some((candidate) => host === candidate.replace(/^www\./, '') || host.endsWith(`.${candidate.replace(/^www\./, '')}`))) {
      return { ...platform, supported: true, host }
    }
  }
  return { id: 'unsupported', label: '未支持页面', supported: false, host }
}

export function mergeSocialSettings(stored = {}) {
  const settings = { ...DEFAULT_SOCIAL_SETTINGS, ...(stored || {}) }
  settings.personaTags = Array.isArray(settings.personaTags) && settings.personaTags.length
    ? settings.personaTags.map(String)
    : [...DEFAULT_SOCIAL_SETTINGS.personaTags]
  settings.trendSources = Array.isArray(settings.trendSources) && settings.trendSources.length
    ? settings.trendSources.map(String)
    : [...DEFAULT_SOCIAL_SETTINGS.trendSources]
  if (!STRATEGY_PRESET_OPTIONS[settings.strategyPreset]) settings.strategyPreset = DEFAULT_SOCIAL_SETTINGS.strategyPreset
  if (!AUTOMATION_LEVELS[settings.automationLevel]) settings.automationLevel = DEFAULT_SOCIAL_SETTINGS.automationLevel
  if (!INTERACTION_LEVELS[settings.interactionLevel]) settings.interactionLevel = DEFAULT_SOCIAL_SETTINGS.interactionLevel
  settings.apiBaseUrl = String(settings.apiBaseUrl || DEFAULT_SOCIAL_SETTINGS.apiBaseUrl).replace(/\/$/, '')
  return settings
}

export function syncSocialSettingsFromStatus(current = {}, status = {}) {
  const settings = mergeSocialSettings(current || {})
  const localSettings = mergeSocialSettings(current || {})
  const payload = status && typeof status === 'object' ? status : {}
  const remoteSettings = payload.settings && typeof payload.settings === 'object' ? payload.settings : {}
  const summary = payload.strategy_summary && typeof payload.strategy_summary === 'object' ? payload.strategy_summary : {}
  const explicitPreset = String(remoteSettings.strategyPreset || '').trim()
  const summaryPreset = String(summary.preset || summary.effective_preset || '').trim()
  if (STRATEGY_PRESET_OPTIONS[explicitPreset]) {
    settings.strategyPreset = explicitPreset
  } else if (
    STRATEGY_PRESET_OPTIONS[summaryPreset] &&
    (summaryPreset !== DEFAULT_SOCIAL_SETTINGS.strategyPreset || localSettings.strategyPreset === DEFAULT_SOCIAL_SETTINGS.strategyPreset)
  ) {
    settings.strategyPreset = summaryPreset
  }
  // 后端状态只同步运营打法；自动化/互动权限继续以本地安全设置为准，避免远程异常打开外部动作。
  settings.automationLevel = localSettings.automationLevel
  settings.interactionLevel = localSettings.interactionLevel
  return mergeSocialSettings(settings)
}

export function buildSocialApiUrl(settings = {}, path = '') {
  const merged = mergeSocialSettings(settings)
  const cleanPath = String(path || '').replace(/^\/+/, '')
  return `${merged.apiBaseUrl}/${cleanPath}`
}

function boundedText(value, limit) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, limit)
}

function boundedMultilineText(value, limit) {
  return String(value || '')
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t\f\v]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, limit)
}

function boundedList(items, limit, itemLimit = 120) {
  if (!Array.isArray(items)) return []
  return items.map((item) => boundedText(item, itemLimit)).filter(Boolean).slice(0, limit)
}

export function normalizePageContext(context = {}) {
  const headings = Array.isArray(context.headings) ? context.headings : []
  const trends = Array.isArray(context.trends) ? context.trends : []
  return {
    title: boundedText(context.title, 160),
    selection: boundedText(context.selection, 800),
    bodyText: boundedText(context.bodyText, 1200),
    headings: headings.map((item) => boundedText(item, 120)).filter(Boolean).slice(0, 8),
    trends: trends.map((item) => boundedText(item, 80)).filter(Boolean).slice(0, 12),
  }
}

export function normalizeDraftAssetPlan(draft = {}) {
  const contentPlan = draft?.content_plan && typeof draft.content_plan === 'object' ? draft.content_plan : {}
  const imagePlan = draft?.image_plan && typeof draft.image_plan === 'object' ? draft.image_plan : {}
  const costRoute = draft?.cost_route && typeof draft.cost_route === 'object' ? draft.cost_route : {}
  const structure = boundedList(contentPlan.structure, 6, 120)
  const assetPrompts = boundedList(imagePlan.asset_prompts, 3, 260)
  const formatChecklist = boundedList(draft?.format_checklist, 6, 120)
  const safetyChecklist = boundedList(draft?.safety_checklist, 8, 140)
  const hasPlan = Boolean(
    contentPlan.format ||
    structure.length ||
    imagePlan.cover_prompt ||
    assetPrompts.length ||
    formatChecklist.length ||
    safetyChecklist.length ||
    draft?.platform_style,
  )

  return {
    has_plan: hasPlan,
    platform_style: boundedText(draft?.platform_style, 120),
    content_plan: {
      format: boundedText(contentPlan.format, 80),
      audience: boundedText(contentPlan.audience, 160),
      hook: boundedText(contentPlan.hook, 180),
      strategy_preset: boundedText(contentPlan.strategy_preset, 80),
      growth_loop: boundedText(contentPlan.growth_loop, 220),
      topic_signal: boundedText(contentPlan.topic_signal, 160),
      persona: boundedText(contentPlan.persona, 120),
      structure,
    },
    image_plan: {
      auto_generate: false,
      image_model: boundedText(imagePlan.image_model, 80),
      cover_prompt: boundedMultilineText(imagePlan.cover_prompt, 700),
      asset_prompts: assetPrompts,
      visual_style: boundedText(imagePlan.visual_style, 160),
    },
    format_checklist: formatChecklist,
    safety_checklist: safetyChecklist,
    cost_route: {
      content_model: boundedText(costRoute.content_model, 80),
      image_model: boundedText(costRoute.image_model, 80),
      prefer_web_quota: Boolean(costRoute.prefer_web_quota),
      model_route_hint: boundedText(costRoute.model_route_hint, 180),
    },
  }
}


function resolveWebModelProvider(route, kind = 'content') {
  const key = String(route || '').trim()
  const providers = {
    'web-gemini': {
      provider: 'gemini',
      provider_label: 'Gemini 网页额度',
      open_url: 'https://gemini.google.com/app',
    },
    'web-gemini-image': {
      provider: 'gemini',
      provider_label: 'Gemini 网页额度',
      open_url: 'https://gemini.google.com/app',
    },
    'web-grok': {
      provider: 'grok',
      provider_label: 'Grok 网页额度',
      open_url: 'https://grok.com/',
    },
    'web-chatgpt': {
      provider: 'chatgpt',
      provider_label: 'ChatGPT 网页额度',
      open_url: 'https://chatgpt.com/',
    },
    'gpt-image': {
      provider: 'chatgpt',
      provider_label: 'ChatGPT / GPT Image 网页额度',
      open_url: 'https://chatgpt.com/',
    },
  }
  if (providers[key]) return providers[key]
  return kind === 'image' ? providers['gpt-image'] : providers['web-gemini']
}

export function buildWebModelRelayTask({ draft = {}, settings = {}, kind = 'content' } = {}) {
  const merged = mergeSocialSettings(settings)
  const taskKind = kind === 'image' ? 'image' : 'content'
  const plan = normalizeDraftAssetPlan(draft || {})
  const route = taskKind === 'image'
    ? (plan.image_plan.image_model || merged.imageModel || 'gpt-image')
    : (merged.contentModel || 'web-gemini')
  const provider = resolveWebModelProvider(route, taskKind)
  const platform = boundedText(draft.platform || 'x', 24)
  const title = boundedText(draft.title, 140)
  const text = boundedMultilineText(draft.text || draft.body || draft.content, 3600)
  const structure = plan.content_plan.structure.length
    ? plan.content_plan.structure.map((item, index) => `${index + 1}. ${item}`).join('\n')
    : '1. 保留平台风格\n2. 强化开头 hook\n3. 给出可执行步骤\n4. 加入风险边界'
  const imagePrompts = plan.image_plan.asset_prompts.length
    ? plan.image_plan.asset_prompts.map((item, index) => `${index + 1}. ${item}`).join('\n')
    : '暂无多图提示词；如需配图，请先返回一张封面图提示词。'
  const safety = [
    ...plan.safety_checklist,
    '不要自动发布',
    '最终仍需人工确认',
    '只返回可复制结果',
  ].filter(Boolean).slice(0, 10).map((item, index) => `${index + 1}. ${item}`).join('\n')

  const commonHeader = [
    '你是 OpenEverything Social Pilot 的安全网页模型接力助手。',
    '请只根据下面草稿生成可复制结果；不要执行任何外部动作。',
    '不要自动发布，不要提交到社交平台，不要点击发送/评论/关注。',
    '最终仍需人工确认，返回内容要方便我复制回插件继续审核。',
  ].join('\n')

  const prompt = taskKind === 'image'
    ? [
        commonHeader,
        '',
        `平台: ${platform}`,
        `标题: ${title || '未命名草稿'}`,
        `正文: ${text || '暂无正文'}`,
        `平台风格: ${plan.platform_style || '保持当前账号统一视觉风格'}`,
        '',
        '请输出图片/封面生成提示词，要求只返回可复制结果，不要发布到社交平台。',
        `封面提示词:\n${plan.image_plan.cover_prompt || '请基于标题和正文生成一张平台友好的封面提示词。'}`,
        `多图素材提示词:\n${imagePrompts}`,
        '',
        `安全清单:\n${safety}`,
      ].join('\n')
    : [
        commonHeader,
        '',
        `平台: ${platform}`,
        `标题: ${title || '未命名草稿'}`,
        `正文: ${text || '暂无正文'}`,
        `目标人群: ${plan.content_plan.audience || '按当前平台用户理解'}`,
        `内容格式: ${plan.content_plan.format || '平台原生短内容'}`,
        `内容结构:\n${structure}`,
        '',
        '请把草稿改成更适合热点传播的版本：开头更抓人，步骤更可执行，保留风险边界。',
        '只返回可复制的标题和正文，不要自动发布。',
        '',
        `安全清单:\n${safety}`,
      ].join('\n')

  return {
    kind: taskKind,
    provider: provider.provider,
    provider_label: provider.provider_label,
    open_url: provider.open_url,
    prompt: boundedMultilineText(prompt, 5200),
    copy_label: taskKind === 'image' ? '复制生图提示词' : '复制内容提示词',
    route,
    auto_submit: false,
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}

export function buildDraftCreatePayload({ platform, tab, settings = {}, pageContext = {} }) {
  const merged = mergeSocialSettings(settings)
  return {
    platform: platform?.id || 'unsupported',
    url: String(tab?.url || ''),
    title: String(tab?.title || ''),
    detected_platform: platform || detectSocialPlatform(tab?.url || ''),
    settings: merged,
    page_context: normalizePageContext(pageContext),
  }
}

export function normalizeTrendItems(items = []) {
  if (!Array.isArray(items)) return []
  const seen = new Set()
  const normalized = []
  for (const item of items) {
    const title = boundedText(item?.title, 120)
    if (!title || seen.has(title.toLowerCase())) continue
    seen.add(title.toLowerCase())
    const tags = Array.isArray(item?.tags) ? item.tags : []
    const executionSteps = Array.isArray(item?.execution_steps) ? item.execution_steps : []
    normalized.push({
      id: boundedText(item?.id || `${item?.source || 'trend'}:${title}`, 180),
      title,
      source: boundedText(item?.source, 60) || 'trend_pool',
      channel: boundedText(item?.channel, 80),
      url: boundedText(item?.url, 500),
      language: boundedText(item?.language, 12),
      heat_reason: boundedText(item?.heat_reason, 180),
      audience: boundedText(item?.audience, 120),
      content_angle: boundedText(item?.content_angle, 180),
      platform_playbook: boundedText(item?.platform_playbook, 180),
      growth_reason: boundedText(item?.growth_reason, 180),
      growth_feedback_boost: Number.isFinite(Number(item?.growth_feedback_boost)) ? Number(item.growth_feedback_boost) : 0,
      growth_feedback_reason: boundedText(item?.growth_feedback_reason, 160),
      risk_level: boundedText(item?.risk_level, 16) || 'medium',
      risk_note: boundedText(item?.risk_note, 180),
      hook_template: boundedText(item?.hook_template, 120),
      execution_steps: executionSteps.map((step) => boundedText(step, 80)).filter(Boolean).slice(0, 4),
      call_to_action: boundedText(item?.call_to_action, 80) || '生成待审草稿',
      draft_platform: boundedText(item?.draft_platform, 20),
      score: Number.isFinite(Number(item?.score)) ? Number(item.score) : 0,
      rank: Number.isFinite(Number(item?.rank)) ? Number(item.rank) : 0,
      tags: tags.map((tag) => boundedText(tag, 40)).filter(Boolean).slice(0, 6),
    })
  }
  return normalized.slice(0, 12)
}


export function normalizeInteractionSignals(items = []) {
  if (!Array.isArray(items)) return []
  const seen = new Set()
  const normalized = []
  for (const item of items) {
    const text = boundedText(item?.text || item?.body || item?.content, 220)
    if (!text) continue
    const id = boundedText(item?.id || `${item?.author || 'user'}:${text}`, 180)
    const key = id || text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    normalized.push({
      id,
      text,
      author: boundedText(item?.author, 80) || 'unknown',
      metric: boundedText(item?.metric || item?.engagement, 80),
      url: boundedText(item?.url, 500),
      intent: boundedText(item?.intent, 80) || 'reply_candidate',
      reply_angle: boundedText(item?.reply_angle, 160) || '给出轻量、可执行、有边界的回复建议',
      auto_reply_enabled: false,
      auto_publish_enabled: false,
      external_actions_locked: true,
    })
    if (normalized.length >= 12) break
  }
  return normalized
}

export function buildInteractionDraftPayload({ platform, signal, settings = {} } = {}) {
  const merged = mergeSocialSettings(settings)
  const item = normalizeInteractionSignals([signal])[0] || {}
  const resolvedPlatform = platform?.id || 'x'
  const titleSeed = boundedText(item.text || '当前互动信号', 64)
  return {
    platform: resolvedPlatform,
    url: item.url || '',
    title: `互动回复：${titleSeed}`,
    source: 'chrome_extension_interaction_scan',
    detected_platform: platform || { id: resolvedPlatform, supported: true },
    settings: merged,
    page_context: normalizePageContext({
      title: `互动回复：${titleSeed}`,
      selection: item.text || '',
      headings: ['互动回复候选', item.intent || '', item.reply_angle || ''].filter(Boolean),
      trends: ['互动回复', item.author || '评论区', merged.interactionLevel || 'off'].filter(Boolean),
      bodyText: [
        item.author ? `作者 ${item.author}` : '',
        item.metric || '',
        item.reply_angle || '',
        '来自当前页互动扫描，只生成待审回复草稿，不自动评论。',
      ].filter(Boolean).join(' · '),
    }),
    auto_reply_enabled: false,
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
    allowButtonClick: false,
  }
}


function boundedNumber(value, max = 999999999) {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.min(max, Math.max(0, Math.round(value)))
  const raw = String(value ?? '').trim().toLowerCase()
  if (!raw) return 0
  const normalized = raw
    .replace(/,/g, '')
    .replace(/\s+/g, '')
    .replace(/次浏览|浏览|观看|views?|likes?|replies?|comments?|reposts?|shares?|saves?|收藏|点赞|评论|转发|分享|粉丝/g, '')
  const match = normalized.match(/([0-9]+(?:\.[0-9]+)?)(万|w|k|m)?/i)
  if (!match) return 0
  let n = Number(match[1])
  if (!Number.isFinite(n)) return 0
  const suffix = String(match[2] || '').toLowerCase()
  if (suffix === '万' || suffix === 'w') n *= 10000
  if (suffix === 'k') n *= 1000
  if (suffix === 'm') n *= 1000000
  return Math.min(max, Math.max(0, Math.round(n)))
}

function pickMetric(metrics = {}, ...keys) {
  for (const key of keys) {
    const value = metrics?.[key]
    if (value !== undefined && value !== null && String(value).trim?.() !== '') return boundedNumber(value)
  }
  return 0
}

export function normalizePerformanceSnapshot(snapshot = {}) {
  const rawMetrics = snapshot?.metrics && typeof snapshot.metrics === 'object' ? snapshot.metrics : snapshot || {}
  const likes = pickMetric(rawMetrics, 'likes', 'like', 'liked')
  const comments = pickMetric(rawMetrics, 'comments', 'comment', 'replies', 'reply')
  const shares = pickMetric(rawMetrics, 'shares', 'share', 'reposts', 'repost', 'retweets', 'retweet')
  const impressions = pickMetric(rawMetrics, 'impressions', 'views', 'view', 'reads', 'read')
  const saves = pickMetric(rawMetrics, 'saves', 'save', 'collects', 'collect', 'favorites', 'favorite')
  const followers = pickMetric(rawMetrics, 'followers', 'follows', 'fans')
  const explicitEngagements = pickMetric(rawMetrics, 'engagements', 'engagement')
  const engagements = explicitEngagements || likes + comments + shares + saves
  const engagementRate = impressions > 0 ? Number((engagements / impressions).toFixed(6)) : 0
  const title = boundedText(snapshot?.title, 140)
  const note = boundedText(snapshot?.note, 220)
  const tags = boundedList(snapshot?.tags, 3, 40)
  const outcome = boundedText(snapshot?.outcome, 40) || (
    impressions >= 10000 || likes >= 100 || comments >= 10 || engagementRate >= 0.03
      ? 'high_signal'
      : 'baseline'
  )
  const learning = boundedText(snapshot?.learning, 240) || (
    outcome === 'high_signal'
      ? '继续放大当前 hook、选题标签和可执行步骤；下一条复用同类结构。'
      : '作为基线记录，下一条优先强化开头、标题利益点和互动问题。'
  )

  return {
    platform: boundedText(snapshot?.platform || 'x', 24),
    url: boundedText(snapshot?.url, 500),
    title,
    draft_id: boundedText(snapshot?.draft_id || snapshot?.draftId, 120),
    metrics: {
      likes,
      comments,
      shares,
      impressions,
      saves,
      followers,
      engagements,
      engagement_rate: engagementRate,
    },
    tags,
    note,
    outcome,
    learning,
    captured_at: boundedText(snapshot?.captured_at || new Date().toISOString(), 80),
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
  }
}

export function buildPerformanceSnapshotPayload({ platform, draft = {}, snapshot = {} } = {}) {
  const resolvedPlatform = platform?.id || snapshot?.platform || draft?.platform || 'x'
  const normalized = normalizePerformanceSnapshot({
    ...(snapshot || {}),
    platform: resolvedPlatform,
    title: snapshot?.title || draft?.title || '',
    draft_id: draft?.id || draft?.draft_id || snapshot?.draft_id || '',
    tags: snapshot?.tags || draft?.seed?.tags || [],
  })
  return {
    platform: resolvedPlatform,
    draft_id: String(draft?.id || draft?.draft_id || normalized.draft_id || ''),
    source: 'chrome_extension_performance_snapshot',
    performance: normalized,
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
    allowButtonClick: false,
  }
}


export function normalizeGrowthFeedbackSummary(summary = {}) {
  const rawSignals = Array.isArray(summary?.signals) ? summary.signals : []
  const signals = []
  for (const item of rawSignals) {
    const metrics = item?.metrics && typeof item.metrics === 'object' ? item.metrics : {}
    const title = boundedText(item?.title, 140)
    if (!title) continue
    signals.push({
      title,
      draft_id: boundedText(item?.draft_id || item?.draftId, 120),
      url: boundedText(item?.url, 500),
      tags: boundedList(item?.tags, 3, 40),
      metrics: {
        likes: boundedNumber(metrics.likes),
        comments: boundedNumber(metrics.comments),
        shares: boundedNumber(metrics.shares),
        impressions: boundedNumber(metrics.impressions),
        saves: boundedNumber(metrics.saves),
        engagements: boundedNumber(metrics.engagements) || boundedNumber(metrics.likes) + boundedNumber(metrics.comments) + boundedNumber(metrics.shares) + boundedNumber(metrics.saves),
      },
      outcome: boundedText(item?.outcome || 'high_signal', 40),
      learning: boundedText(item?.learning, 220),
      growth_feedback_reason: boundedText(item?.growth_feedback_reason, 180),
      captured_at: boundedText(item?.captured_at, 80),
      auto_publish_enabled: false,
      external_actions_locked: true,
    })
    if (signals.length >= 6) break
  }
  return {
    success: Boolean(summary?.success ?? true),
    source: boundedText(summary?.source || 'chrome_extension_growth_feedback', 80),
    platform: boundedText(summary?.platform || 'x', 24),
    high_signal_count: Number.isFinite(Number(summary?.high_signal_count)) ? Number(summary.high_signal_count) : signals.length,
    baseline_count: Number.isFinite(Number(summary?.baseline_count)) ? Number(summary.baseline_count) : 0,
    top_tags: boundedList(summary?.top_tags, 5, 40),
    signals,
    recommendations: boundedList(summary?.recommendations, 2, 120),
    next_action: boundedText(summary?.next_action || '复用高信号结构生成下一批待审草稿。', 180),
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}

export function buildTrendDraftPayload({ platform, trend, settings = {} } = {}) {
  const merged = mergeSocialSettings(settings)
  const normalized = normalizeTrendItems([trend])[0] || {}
  return {
    platform: platform?.id || normalized.draft_platform || 'x',
    url: normalized.url || '',
    title: normalized.title || '',
    source: 'chrome_extension_trend_pool',
    detected_platform: platform || { id: normalized.draft_platform || 'x', supported: true },
    settings: merged,
    page_context: normalizePageContext({
      title: normalized.title || '',
      selection: normalized.hook_template || normalized.heat_reason || normalized.title || '',
      headings: [normalized.call_to_action || '', normalized.platform_playbook || '', normalized.channel || ''].filter(Boolean),
      trends: normalized.tags?.length ? normalized.tags : [normalized.source || 'trend_pool'],
      bodyText: [
        normalized.heat_reason,
        normalized.content_angle,
        normalized.platform_playbook,
        normalized.growth_reason,
        normalized.execution_steps?.join(' / '),
        normalized.risk_note,
        normalized.source,
        normalized.channel,
      ].filter(Boolean).join(' · '),
    }),
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}

export function buildAutofillPayload({ platformId, platform, draft = {} } = {}) {
  const resolvedPlatform = String(platformId || platform?.id || draft.platform || 'unsupported')
  const title = boundedText(draft.title, 120)
  const bodyText = boundedMultilineText(draft.text || draft.body || draft.content, 2800)
  const selectors = buildAutofillSelectors(resolvedPlatform)
  const combinedText = boundedMultilineText([title, bodyText].filter(Boolean).join('\n\n'), 3000)
  const reviewStatus = String(draft.review_status || draft.reviewStatus || 'unknown')
  return {
    platform: resolvedPlatform,
    draftId: String(draft.id || draft.draft_id || ''),
    title,
    bodyText,
    text: combinedText,
    reviewStatus,
    requiresReview: reviewStatus !== 'approved',
    fields: selectors.fields,
    publishIntent: false,
    allowButtonClick: false,
  }
}

export function buildAutofillSelectors(platformId = 'unsupported') {
  const platform = String(platformId || 'unsupported')
  const common = {
    platform,
    publishIntent: false,
    allowButtonClick: false,
  }
  if (platform === 'x') {
    return {
      ...common,
      fields: [
        {
          name: 'compose',
          kind: 'body',
          selectors: [
            'div[data-testid^="tweetTextarea"][role="textbox"]',
            'div[data-testid^="tweetTextarea"] div[contenteditable="true"]',
            'div.public-DraftEditor-content[contenteditable="true"]',
            'div[role="textbox"][aria-label*="Post text"]',
            'div[role="textbox"][aria-label*="Tweet text"]',
            'div[aria-label*="Post text"] div[contenteditable="true"]',
            'div[aria-label*="Tweet text"] div[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'textarea[aria-label*="Post"]',
          ],
        },
      ],
    }
  }
  if (platform === 'xhs') {
    return {
      ...common,
      fields: [
        {
          name: 'title',
          kind: 'title',
          selectors: [
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            'input[aria-label*="标题"]',
          ],
        },
        {
          name: 'body',
          kind: 'body',
          selectors: [
            'textarea[placeholder*="正文"]',
            'textarea[placeholder*="描述"]',
            '.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][data-placeholder*="正文"]',
            'div[contenteditable="true"][data-placeholder*="描述"]',
            'div[contenteditable="true"][aria-placeholder*="正文"]',
            'div[contenteditable="true"][aria-placeholder*="描述"]',
            'div[contenteditable="true"][placeholder*="正文"]',
            'div[contenteditable="true"][placeholder*="描述"]',
            'div[contenteditable="true"][role="textbox"]',
            'textarea',
          ],
        },
      ],
    }
  }
  if (platform === 'xianyu') {
    return {
      ...common,
      fields: [
        {
          name: 'reply_or_description',
          kind: 'body',
          selectors: [
            'textarea[placeholder*="回复"]',
            'textarea[placeholder*="描述"]',
            'input[placeholder*="回复"]',
            'div[contenteditable="true"][placeholder*="回复"]',
            'div[contenteditable="true"][data-placeholder*="回复"]',
            'div[contenteditable="true"][data-placeholder*="请输入"]',
            'div[contenteditable="true"][aria-placeholder*="回复"]',
            'div[contenteditable="true"][aria-label*="回复"]',
            'div[contenteditable="true"][role="textbox"]',
            'textarea',
          ],
        },
      ],
    }
  }
  return { ...common, fields: [] }
}

export function buildPageProbePayload({ platformId, platform } = {}) {
  const plan = buildAutofillSelectors(platformId || platform?.id || 'unsupported')
  return {
    ...plan,
    action: 'probe_fields',
    publishIntent: false,
    allowButtonClick: false,
  }
}

export function buildPageProbeReportPayload({ platform, tab, probeResult = {} } = {}) {
  const resolvedPlatform = String(platform?.id || probeResult.platform || 'unsupported')
  const rawFields = Array.isArray(probeResult.availableFields) ? probeResult.availableFields : []
  const availableFields = rawFields
    .map((field) => ({
      name: boundedText(field?.name || '', 60),
      kind: boundedText(field?.kind || '', 60),
      tag: boundedText(field?.tag || '', 40),
    }))
    .filter((field) => field.name || field.kind || field.tag)
    .slice(0, 8)

  return {
    platform: resolvedPlatform,
    url: boundedText(tab?.url || probeResult.url || '', 500),
    ready: Boolean(probeResult.ready || availableFields.length > 0),
    availableFields,
    reason: boundedText(probeResult.reason || '', 120),
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}


export function normalizeScheduleItems(items = []) {
  if (!Array.isArray(items)) return []
  const seen = new Set()
  const normalized = []
  for (const item of items) {
    const draftId = boundedText(item?.draft_id || item?.draftId || item?.draft?.id || item?.id, 120)
    const itemId = boundedText(item?.id || `schedule:${draftId}`, 140)
    const key = draftId || itemId
    if (!key || seen.has(key)) continue
    seen.add(key)
    const status = boundedText(item?.status || 'queued_for_owner_publish', 60)
    const draft = item?.draft && typeof item.draft === 'object' ? item.draft : {}
    const platform = boundedText(item?.platform || draft.platform || 'x', 24)
    const title = boundedText(item?.title || draft.title || '未命名排程', 120)
    const scheduleStatus = boundedText(draft.schedule_status || status, 60)
    const assetPlan = normalizeDraftAssetPlan(draft)
    normalized.push({
      id: itemId,
      draft_id: draftId,
      platform,
      title,
      text_preview: boundedText(item?.text_preview || draft.text || draft.body || '', 220),
      scheduled_at: boundedText(item?.scheduled_at || item?.scheduledAt || '', 80),
      status,
      review_status: boundedText(item?.review_status || draft.review_status || 'approved', 40),
      due: Boolean(item?.due || status === 'awaiting_final_confirmation'),
      requires_final_confirmation: Boolean(item?.requires_final_confirmation || status === 'awaiting_final_confirmation'),
      auto_publish_enabled: false,
      external_actions_locked: true,
      draft: {
        id: draftId,
        platform,
        title: boundedText(draft.title || title, 120),
        text: boundedMultilineText(draft.text || draft.body || item?.text_preview || '', 4000),
        review_status: boundedText(draft.review_status || item?.review_status || 'approved', 40),
        status: boundedText(draft.status || status, 60),
        schedule_status: scheduleStatus,
        platform_style: assetPlan.platform_style,
        content_plan: assetPlan.content_plan,
        image_plan: assetPlan.image_plan,
        format_checklist: assetPlan.format_checklist,
        safety_checklist: assetPlan.safety_checklist,
        cost_route: assetPlan.cost_route,
      },
    })
  }
  return normalized.slice(0, 12)
}


export function normalizeReviewPack(pack = {}) {
  const persona = pack?.persona && typeof pack.persona === 'object' ? pack.persona : {}
  const rawSamples = Array.isArray(pack?.samples) ? pack.samples : []
  const seen = new Set()
  const samples = []
  for (const item of rawSamples) {
    const id = boundedText(item?.id || `${item?.platform || 'sample'}:${item?.title || item?.text || ''}`, 140)
    if (!id || seen.has(id)) continue
    seen.add(id)
    const platform = boundedText(item?.platform || 'x', 24)
    if (!['x', 'xhs', 'xianyu'].includes(platform)) continue
    samples.push({
      id,
      index: Number.isFinite(Number(item?.index)) ? Number(item.index) : -1,
      platform,
      title: boundedText(item?.title || '', 120),
      text: boundedMultilineText(item?.text || item?.body || item?.content || '', 1200),
      source: boundedText(item?.source || '', 80),
      language: boundedText(item?.language || '', 16),
      heat_reason: boundedText(item?.heat_reason || '', 180),
      review_status: boundedText(item?.review_status || 'pending', 40),
    })
    if (samples.length >= 8) break
  }
  const tone = Array.isArray(persona.tone) ? persona.tone.map((item) => boundedText(item, 24)).filter(Boolean).slice(0, 8) : []
  const guardrails = Array.isArray(pack?.guardrails)
    ? pack.guardrails.map((item) => boundedText(item, 120)).filter(Boolean).slice(0, 8)
    : []
  const contentMix = persona.content_mix && typeof persona.content_mix === 'object' ? persona.content_mix : {}
  return {
    success: Boolean(pack?.success ?? true),
    mode: boundedText(pack?.mode || 'persona_and_content_review_pack', 80),
    persona: {
      proposal_id: boundedText(persona.proposal_id || '', 80),
      display_name: boundedText(persona.display_name || '待确认人设', 80),
      one_liner: boundedText(persona.one_liner || '', 180),
      positioning: boundedText(persona.positioning || '', 260),
      tone,
      content_mix: {
        x: boundedText(contentMix.x || '', 160),
        xhs: boundedText(contentMix.xhs || '', 160),
        xianyu: boundedText(contentMix.xianyu || '', 160),
      },
    },
    persona_approved: Boolean(pack?.persona_approved || pack?.approved),
    requires_owner_confirmation: Boolean(pack?.requires_owner_confirmation ?? true),
    samples,
    sample_count: samples.length,
    guardrails,
    content_verdict: boundedText(pack?.content_verdict || pack?.verdict || '', 240),
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}

export function buildPersonaReviewPayload({ approved = false, reviewer = 'owner', notes = '' } = {}) {
  return {
    approved: Boolean(approved),
    reviewer: boundedText(reviewer || 'owner', 80) || 'owner',
    notes: boundedText(notes || '', 240),
    auto_publish_enabled: false,
    external_actions_locked: true,
  }
}


export function buildScheduleDraftPayload({ platformId, platform, draft = {}, scheduledAt = '' } = {}) {
  const resolvedPlatform = String(platformId || platform?.id || draft.platform || 'unsupported')
  const reviewStatus = String(draft.review_status || draft.reviewStatus || 'pending')
  const title = boundedText(draft.title, 120)
  const text = boundedMultilineText(draft.text || draft.body || draft.content, 2800)
  return {
    draft_id: String(draft.id || draft.draft_id || ''),
    platform: resolvedPlatform,
    title,
    text,
    scheduled_at: boundedText(scheduledAt, 80),
    review_status: reviewStatus,
    requiresReview: reviewStatus !== 'approved',
    auto_publish_enabled: false,
    external_actions_locked: true,
    publishIntent: false,
    allowButtonClick: false,
  }
}

export function isExternalMutationAllowed(settings = {}) {
  const merged = mergeSocialSettings(settings)
  return merged.automationLevel === 'reviewed_publish' || merged.automationLevel === 'low_risk_auto'
}

export function buildStatusSummary(platform, running, settings = {}) {
  const merged = mergeSocialSettings(settings)
  const platformLabel = platform?.label || '未识别页面'
  const mode = AUTOMATION_LEVELS[merged.automationLevel] || AUTOMATION_LEVELS.draft_only
  const interaction = INTERACTION_LEVELS[merged.interactionLevel] || INTERACTION_LEVELS.off
  return `${platformLabel} · ${running ? '运行中' : '已暂停'} · ${mode} · 互动:${interaction}`
}

export function createDefaultTaskPreview(platformId) {
  if (platformId === 'xhs') {
    return [
      '抓取小红书当前页/本地热点池',
      '生成生活方式图文草稿与封面提示词',
      '审计标题、emoji、女性向语气和敏感词',
    ]
  }
  if (platformId === 'x') {
    return [
      '抓取 X/HN/GitHub/美股/AI/Web3 热点',
      '生成可实操的财富出海/AI 工具短帖',
      '审计收益承诺、投资建议和平台风险',
    ]
  }
  if (platformId === 'xianyu') {
    return [
      '读取当前商品或聊天上下文',
      '生成标题优化、砍价回复和成交建议',
      '标记高意向买家并同步到中控',
    ]
  }
  return ['打开 X / 小红书 / 闲鱼 页面后再启动运营']
}

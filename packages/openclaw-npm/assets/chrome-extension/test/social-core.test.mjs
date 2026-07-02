import test from 'node:test'
import assert from 'node:assert/strict'

import {
  detectSocialPlatform,
  mergeSocialSettings,
  isExternalMutationAllowed,
  buildStatusSummary,
  createDefaultTaskPreview,
  buildSocialApiUrl,
  normalizePageContext,
  buildDraftCreatePayload,
  buildAutofillPayload,
  normalizeTrendItems,
  buildTrendDraftPayload,
  buildAutofillSelectors,
  buildPageProbePayload,
  normalizeScheduleItems,
  normalizeReviewPack,
  buildPersonaReviewPayload,
  buildPageProbeReportPayload,
  normalizeDraftAssetPlan,
  buildWebModelRelayTask,
  normalizeInteractionSignals,
  buildInteractionDraftPayload,
  normalizePerformanceSnapshot,
  buildPerformanceSnapshotPayload,
  normalizeGrowthFeedbackSummary,
  syncSocialSettingsFromStatus,
} from '../social-core.js'

test('detectSocialPlatform identifies supported social pages', () => {
  assert.equal(detectSocialPlatform('https://x.com/home').id, 'x')
  assert.equal(detectSocialPlatform('https://twitter.com/explore').id, 'x')
  assert.equal(detectSocialPlatform('https://creator.xiaohongshu.com/publish/publish').id, 'xhs')
  assert.equal(detectSocialPlatform('https://www.goofish.com/item?id=1').id, 'xianyu')
  assert.equal(detectSocialPlatform('https://example.com').supported, false)
})

test('mergeSocialSettings keeps safe defaults for automation', () => {
  const settings = mergeSocialSettings({ automationLevel: 'publish_now', interactionLevel: 'spam' })
  assert.equal(settings.automationLevel, 'draft_only')
  assert.equal(settings.interactionLevel, 'off')
  assert.deepEqual(settings.personaTags, ['科技', '出海', 'AI赚钱'])
})

test('syncSocialSettingsFromStatus pulls backend strategy without opening automation', () => {
  const settings = syncSocialSettingsFromStatus(
    { strategyPreset: 'x_wealth_frontier', automationLevel: 'draft_only', interactionLevel: 'off' },
    {
      settings: { strategyPreset: 'x_absurd_growth', automationLevel: 'low_risk_auto', interactionLevel: 'standard' },
      strategy_summary: {
        preset: 'x_absurd_growth',
        auto_publish_enabled: false,
        external_actions_locked: true,
      },
      auto_publish_enabled: true,
      external_actions_locked: false,
    },
  )

  assert.equal(settings.strategyPreset, 'x_absurd_growth')
  assert.equal(settings.automationLevel, 'draft_only')
  assert.equal(settings.interactionLevel, 'off')
})

test('syncSocialSettingsFromStatus ignores invalid remote strategy preset', () => {
  const settings = syncSocialSettingsFromStatus(
    { strategyPreset: 'xhs_lifestyle_tutorial' },
    { settings: { strategyPreset: 'publish_everything_now' }, strategy_summary: { preset: 'spam' } },
  )

  assert.equal(settings.strategyPreset, 'xhs_lifestyle_tutorial')
})

test('syncSocialSettingsFromStatus keeps local strategy when backend has only default summary', () => {
  const settings = syncSocialSettingsFromStatus(
    { strategyPreset: 'xhs_lifestyle_tutorial' },
    { settings: {}, strategy_summary: { preset: 'auto_mcn_growth', effective_preset: 'x_wealth_frontier' } },
  )

  assert.equal(settings.strategyPreset, 'xhs_lifestyle_tutorial')
})

test('isExternalMutationAllowed only opens after reviewed modes', () => {
  assert.equal(isExternalMutationAllowed({ automationLevel: 'draft_only' }), false)
  assert.equal(isExternalMutationAllowed({ automationLevel: 'autofill' }), false)
  assert.equal(isExternalMutationAllowed({ automationLevel: 'reviewed_publish' }), true)
  assert.equal(isExternalMutationAllowed({ automationLevel: 'low_risk_auto' }), true)
})

test('status summary and task preview are platform aware', () => {
  const platform = detectSocialPlatform('https://www.xiaohongshu.com/explore')
  assert.match(buildStatusSummary(platform, true, { automationLevel: 'autofill' }), /小红书 · 运行中 · 自动填入页面/)
  assert.ok(createDefaultTaskPreview('x').some((item) => item.includes('GitHub')))
  assert.ok(createDefaultTaskPreview('xianyu').some((item) => item.includes('砍价')))
})

test('buildSocialApiUrl trims base URL and leading path slashes', () => {
  assert.equal(
    buildSocialApiUrl({ apiBaseUrl: 'http://127.0.0.1:18790/api/v1/' }, '/social/extension/status'),
    'http://127.0.0.1:18790/api/v1/social/extension/status',
  )
})

test('normalizePageContext keeps bounded current-page signal', () => {
  const context = normalizePageContext({
    title: '夏日冷饮搜索结果',
    selection: '  家人们，一定要学的夏日冷饮制作方法  ',
    headings: ['3分钟作出一杯夏日冰饮', '低卡柠檬茶'],
    trends: ['冰饮教程', '夏天续命水'],
    bodyText: 'x'.repeat(5000),
  })

  assert.equal(context.title, '夏日冷饮搜索结果')
  assert.equal(context.selection, '家人们，一定要学的夏日冷饮制作方法')
  assert.deepEqual(context.trends, ['冰饮教程', '夏天续命水'])
  assert.ok(context.bodyText.length <= 1200)
})

test('buildDraftCreatePayload packages tab context for safe backend draft creation', () => {
  const platform = detectSocialPlatform('https://x.com/explore')
  const payload = buildDraftCreatePayload({
    platform,
    tab: { url: 'https://x.com/explore', title: 'X Explore' },
    settings: { personaTags: ['金融', '出海'], automationLevel: 'autofill' },
    pageContext: { title: '美股回调', trends: ['AI stocks', 'rate cut'] },
  })

  assert.equal(payload.platform, 'x')
  assert.equal(payload.url, 'https://x.com/explore')
  assert.equal(payload.page_context.title, '美股回调')
  assert.deepEqual(payload.settings.personaTags, ['金融', '出海'])
})


test('buildAutofillPayload keeps page mutation safe and never requests publish', () => {
  const payload = buildAutofillPayload({
    platformId: 'x',
    draft: { id: 'd-1', title: '近期美股回调', text: '就业数据超预期，短线回调更像技术修正。' },
  })

  assert.equal(payload.platform, 'x')
  assert.equal(payload.draftId, 'd-1')
  assert.equal(payload.text, '近期美股回调\n\n就业数据超预期，短线回调更像技术修正。')
  assert.equal(payload.publishIntent, false)
  assert.equal(payload.allowButtonClick, false)
})


test('normalizeDraftAssetPlan keeps platform content and image plan safe for editor display', () => {
  const plan = normalizeDraftAssetPlan({
    platform: 'xhs',
    content_plan: {
      format: 'xhs_note',
      structure: ['标题直给结果', '3-5 步教程', '收藏引导'],
      hook: '家人们，这个夏日冷饮真的建议收藏',
    },
    image_plan: {
      auto_generate: true,
      image_model: 'gpt-image',
      cover_prompt: '夏日低卡柠檬茶，小红书封面，明亮干净',
      asset_prompts: ['步骤图 1', '材料清单图', '超出数量会被裁掉', '第四张不显示'],
    },
    safety_checklist: ['不自动发布', '发布前人工确认'],
    format_checklist: ['封面图比例 3:4', '标题 20 字内'],
    platform_style: '小红书女性向生活攻略图文',
    cost_route: { content_model: 'web-gemini', image_model: 'gpt-image', prefer_web_quota: true },
  })

  assert.equal(plan.content_plan.format, 'xhs_note')
  assert.deepEqual(plan.content_plan.structure, ['标题直给结果', '3-5 步教程', '收藏引导'])
  assert.equal(plan.image_plan.auto_generate, false)
  assert.equal(plan.image_plan.image_model, 'gpt-image')
  assert.match(plan.image_plan.cover_prompt, /夏日低卡柠檬茶/)
  assert.deepEqual(plan.image_plan.asset_prompts, ['步骤图 1', '材料清单图', '超出数量会被裁掉'])
  assert.deepEqual(plan.safety_checklist, ['不自动发布', '发布前人工确认'])
  assert.equal(plan.platform_style, '小红书女性向生活攻略图文')
  assert.equal(plan.cost_route.content_model, 'web-gemini')
  assert.equal(plan.cost_route.prefer_web_quota, true)
})

test('buildWebModelRelayTask creates copy-only web quota prompts without auto submit', () => {
  const draft = {
    id: 'ext-xhs-asset',
    platform: 'xhs',
    title: '3分钟做出一杯夏日冰饮',
    text: '家人们，低卡柠檬茶真的适合夏天收藏。',
    content_plan: { format: 'xhs_note', structure: ['标题直给结果', '3-5 步教程', '收藏引导'] },
    image_plan: {
      image_model: 'web-gemini-image',
      cover_prompt: '小红书封面图，夏日低卡柠檬茶，明亮自然光',
      asset_prompts: ['材料清单步骤图', '制作过程分镜图'],
    },
    safety_checklist: ['不自动发布', '发布前人工确认'],
  }

  const task = buildWebModelRelayTask({ draft, settings: { contentModel: 'web-gemini', imageModel: 'web-gemini-image' }, kind: 'image' })

  assert.equal(task.kind, 'image')
  assert.equal(task.provider, 'gemini')
  assert.equal(task.provider_label, 'Gemini 网页额度')
  assert.equal(task.open_url, 'https://gemini.google.com/app')
  assert.equal(task.auto_submit, false)
  assert.equal(task.external_actions_locked, true)
  assert.equal(task.auto_publish_enabled, false)
  assert.match(task.prompt, /小红书封面图/)
  assert.match(task.prompt, /不要发布到社交平台/)
  assert.match(task.prompt, /只返回可复制/)
  assert.ok(task.copy_label.includes('复制'))
})

test('buildWebModelRelayTask maps Grok and ChatGPT content routes safely', () => {
  const grokTask = buildWebModelRelayTask({
    draft: { platform: 'x', title: 'GitHub 一周异常 Star 工具榜', text: '先列观察清单。' },
    settings: { contentModel: 'web-grok' },
    kind: 'content',
  })
  const chatgptTask = buildWebModelRelayTask({
    draft: { platform: 'x', title: 'GitHub 一周异常 Star 工具榜', text: '先列观察清单。' },
    settings: { contentModel: 'web-chatgpt' },
    kind: 'content',
  })

  assert.equal(grokTask.provider, 'grok')
  assert.equal(grokTask.open_url, 'https://grok.com/')
  assert.equal(chatgptTask.provider, 'chatgpt')
  assert.equal(chatgptTask.open_url, 'https://chatgpt.com/')
  assert.equal(grokTask.auto_submit, false)
  assert.equal(chatgptTask.auto_submit, false)
  assert.match(grokTask.prompt, /不要自动发布/)
  assert.match(chatgptTask.prompt, /最终仍需人工确认/)
})


test('normalizeTrendItems keeps bounded hotspot cards for the popup', () => {
  const trends = normalizeTrendItems([
    {
      title: 'GitHub 一周异常 Star 工具榜',
      source: 'hacker_news',
      heat_reason: '年轻创业者可直接收藏',
      tags: ['GitHub', 'AI工具'],
      audience: '大学生 / 年轻创业者',
      content_angle: '拆成可执行工具清单',
      platform_playbook: 'X 短帖：反差开头 + 3 步说明',
      growth_reason: '前沿工具和赚钱想象更容易被转发',
      growth_feedback_boost: 620,
      growth_feedback_reason: '历史高信号：GitHub 工具榜；匹配 GitHub/AI工具',
      risk_level: 'medium',
      risk_note: '避免收益承诺',
      execution_steps: ['先给结论', '列 3 个工具', '留一个讨论问题'],
      hook_template: '最近一周 GitHub 有点不正常：',
    },
    { title: '', source: 'empty' },
  ])

  assert.equal(trends.length, 1)
  assert.equal(trends[0].title, 'GitHub 一周异常 Star 工具榜')
  assert.equal(trends[0].source, 'hacker_news')
  assert.deepEqual(trends[0].tags, ['GitHub', 'AI工具'])
  assert.equal(trends[0].audience, '大学生 / 年轻创业者')
  assert.equal(trends[0].content_angle, '拆成可执行工具清单')
  assert.equal(trends[0].platform_playbook, 'X 短帖：反差开头 + 3 步说明')
  assert.equal(trends[0].growth_reason, '前沿工具和赚钱想象更容易被转发')
  assert.equal(trends[0].growth_feedback_boost, 620)
  assert.match(trends[0].growth_feedback_reason, /历史高信号/)
  assert.equal(trends[0].risk_level, 'medium')
  assert.equal(trends[0].risk_note, '避免收益承诺')
  assert.deepEqual(trends[0].execution_steps, ['先给结论', '列 3 个工具', '留一个讨论问题'])
  assert.equal(trends[0].hook_template, '最近一周 GitHub 有点不正常：')
})


test('normalizeInteractionSignals keeps bounded owner-safe engagement targets', () => {
  const signals = normalizeInteractionSignals([
    { id: 'c1', text: '这个工具怎么部署？求一个小白步骤', author: 'student', metric: '12 likes', url: 'https://x.com/post/1' },
    { id: 'c1', text: '重复项' },
    { text: '   ', author: 'empty' },
    { id: 'c2', text: '夏天通勤包里到底带什么最省心？', author: 'xhs_user', metric: '3 replies' },
  ])

  assert.equal(signals.length, 2)
  assert.equal(signals[0].id, 'c1')
  assert.equal(signals[0].text, '这个工具怎么部署？求一个小白步骤')
  assert.equal(signals[0].author, 'student')
  assert.equal(signals[0].metric, '12 likes')
  assert.equal(signals[0].auto_reply_enabled, false)
  assert.equal(signals[0].external_actions_locked, true)
})

test('buildInteractionDraftPayload turns a selected comment into a reviewed-only draft source', () => {
  const platform = detectSocialPlatform('https://x.com/home')
  const payload = buildInteractionDraftPayload({
    platform,
    signal: {
      id: 'comment-1',
      text: '这些 AI 工具怎么部署到自己的业务里？',
      author: 'young_builder',
      metric: '18 likes',
      url: 'https://x.com/example/status/1',
    },
    settings: { personaTags: ['出海', 'AI赚钱'], interactionLevel: 'light' },
  })

  assert.equal(payload.platform, 'x')
  assert.equal(payload.source, 'chrome_extension_interaction_scan')
  assert.equal(payload.title, '互动回复：这些 AI 工具怎么部署到自己的业务里？')
  assert.equal(payload.page_context.selection, '这些 AI 工具怎么部署到自己的业务里？')
  assert.match(payload.page_context.bodyText, /young_builder/)
  assert.match(payload.page_context.bodyText, /18 likes/)
  assert.equal(payload.settings.interactionLevel, 'light')
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
  assert.equal(payload.publishIntent, false)
})



test('normalizePerformanceSnapshot keeps bounded post metrics without enabling mutation', () => {
  const snapshot = normalizePerformanceSnapshot({
    platform: 'x',
    url: 'https://x.com/example/status/1',
    title: 'GitHub 一周异常 Star 工具榜',
    metrics: { likes: '128', comments: '12', shares: '7', impressions: '12000', saves: '5', followers: '3456' },
    tags: ['GitHub', 'AI工具', '超出数量', '第四个会裁掉'],
    note: '这条 hook 很强，评论区在问部署步骤。',
    auto_publish_enabled: true,
  })

  assert.equal(snapshot.platform, 'x')
  assert.equal(snapshot.metrics.likes, 128)
  assert.equal(snapshot.metrics.comments, 12)
  assert.equal(snapshot.metrics.shares, 7)
  assert.equal(snapshot.metrics.impressions, 12000)
  assert.equal(snapshot.metrics.saves, 5)
  assert.equal(snapshot.metrics.followers, 3456)
  assert.deepEqual(snapshot.tags, ['GitHub', 'AI工具', '超出数量'])
  assert.equal(snapshot.auto_publish_enabled, false)
  assert.equal(snapshot.external_actions_locked, true)
})

test('buildPerformanceSnapshotPayload sends analytics-only feedback for a published draft', () => {
  const platform = detectSocialPlatform('https://x.com/example/status/1')
  const payload = buildPerformanceSnapshotPayload({
    platform,
    draft: { id: 'ext-x-demo', title: 'GitHub 一周异常 Star 工具榜', seed: { source: 'hacker_news' } },
    snapshot: {
      url: 'https://x.com/example/status/1',
      metrics: { likes: 128, comments: 12, shares: 7, impressions: 12000 },
      note: '评论区都在问部署步骤。',
    },
  })

  assert.equal(payload.platform, 'x')
  assert.equal(payload.draft_id, 'ext-x-demo')
  assert.equal(payload.source, 'chrome_extension_performance_snapshot')
  assert.equal(payload.performance.metrics.likes, 128)
  assert.equal(payload.performance.metrics.engagements, 147)
  assert.equal(payload.performance.outcome, 'high_signal')
  assert.match(payload.performance.learning, /继续放大/)
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
  assert.equal(payload.publishIntent, false)
})


test('normalizeGrowthFeedbackSummary keeps high-signal recap actionable and safe', () => {
  const summary = normalizeGrowthFeedbackSummary({
    platform: 'x',
    high_signal_count: 2,
    signals: [
      {
        title: 'GitHub 一周异常 Star 工具榜',
        tags: ['GitHub', 'AI工具', '第三个', '第四个裁掉'],
        metrics: { likes: 188, comments: 18, shares: 9, impressions: 18000 },
        learning: '继续放大 GitHub 工具榜 + 部署步骤。',
        growth_feedback_reason: '历史高信号：匹配 GitHub/AI工具',
      },
    ],
    recommendations: ['继续做 GitHub 工具榜', '把部署步骤放前面', '第三条会裁掉'],
    auto_publish_enabled: true,
  })

  assert.equal(summary.platform, 'x')
  assert.equal(summary.high_signal_count, 2)
  assert.equal(summary.signals.length, 1)
  assert.equal(summary.signals[0].title, 'GitHub 一周异常 Star 工具榜')
  assert.deepEqual(summary.signals[0].tags, ['GitHub', 'AI工具', '第三个'])
  assert.equal(summary.signals[0].metrics.likes, 188)
  assert.match(summary.signals[0].learning, /继续放大/)
  assert.deepEqual(summary.recommendations, ['继续做 GitHub 工具榜', '把部署步骤放前面'])
  assert.equal(summary.auto_publish_enabled, false)
  assert.equal(summary.external_actions_locked, true)
})

test('buildTrendDraftPayload packages a selected hotspot as a safe draft source', () => {
  const platform = detectSocialPlatform('https://x.com/explore')
  const payload = buildTrendDraftPayload({
    platform,
    settings: { personaTags: ['科技', '出海'] },
    trend: {
      title: 'GitHub 一周异常 Star 工具榜',
      url: 'https://example.com/github-stars',
      source: 'hacker_news',
      heat_reason: '年轻创业者可直接收藏',
      tags: ['GitHub', 'AI工具'],
      content_angle: '拆成可执行工具清单',
      platform_playbook: 'X 短帖：反差开头 + 3 步说明',
      growth_reason: '前沿工具和赚钱想象更容易被转发',
      execution_steps: ['先给结论', '列 3 个工具', '留一个讨论问题'],
      risk_note: '避免收益承诺',
    },
  })

  assert.equal(payload.platform, 'x')
  assert.equal(payload.source, 'chrome_extension_trend_pool')
  assert.equal(payload.url, 'https://example.com/github-stars')
  assert.equal(payload.page_context.title, 'GitHub 一周异常 Star 工具榜')
  assert.deepEqual(payload.page_context.trends, ['GitHub', 'AI工具'])
  assert.match(payload.page_context.bodyText, /拆成可执行工具清单/)
  assert.match(payload.page_context.bodyText, /X 短帖/)
  assert.match(payload.page_context.bodyText, /避免收益承诺/)
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
})


test('buildAutofillSelectors returns platform-specific safe field plans', () => {
  const x = buildAutofillSelectors('x')
  const xhs = buildAutofillSelectors('xhs')
  const xianyu = buildAutofillSelectors('xianyu')

  assert.ok(x.fields.some((field) => field.name === 'compose' && field.kind === 'body'))
  assert.ok(xhs.fields.some((field) => field.name === 'title' && field.kind === 'title'))
  assert.ok(xhs.fields.some((field) => field.name === 'body' && field.kind === 'body'))
  assert.ok(xianyu.fields.some((field) => field.name === 'reply_or_description'))
  assert.equal(x.allowButtonClick, false)
  assert.equal(xhs.allowButtonClick, false)
  assert.equal(xianyu.allowButtonClick, false)
})

test('buildAutofillSelectors covers modern real-page editor variants', () => {
  const xSelectors = buildAutofillSelectors('x').fields.flatMap((field) => field.selectors)
  const xhsSelectors = buildAutofillSelectors('xhs').fields.flatMap((field) => field.selectors)
  const xianyuSelectors = buildAutofillSelectors('xianyu').fields.flatMap((field) => field.selectors)

  assert.ok(xSelectors.includes('div[data-testid^="tweetTextarea"] div[contenteditable="true"]'))
  assert.ok(xSelectors.includes('div.public-DraftEditor-content[contenteditable="true"]'))
  assert.ok(xhsSelectors.includes('.ql-editor[contenteditable="true"]'))
  assert.ok(xhsSelectors.includes('div[contenteditable="true"][aria-placeholder*="正文"]'))
  assert.ok(xianyuSelectors.includes('div[contenteditable="true"][data-placeholder*="请输入"]'))
  assert.ok(xianyuSelectors.includes('div[contenteditable="true"][aria-label*="回复"]'))
})

test('buildPageProbePayload reports a detection-only action with no publish intent', () => {
  const payload = buildPageProbePayload({ platformId: 'xhs' })

  assert.equal(payload.platform, 'xhs')
  assert.equal(payload.action, 'probe_fields')
  assert.equal(payload.publishIntent, false)
  assert.equal(payload.allowButtonClick, false)
  assert.ok(payload.fields.some((field) => field.name === 'title'))
})

test('buildScheduleDraftPayload only schedules reviewed content and never publishes', async () => {
  const { buildScheduleDraftPayload } = await import('../social-core.js')
  const payload = buildScheduleDraftPayload({
    platformId: 'x',
    draft: {
      id: 'ext-x-demo',
      title: 'GitHub异常Star工具榜',
      text: '今天适合收藏，不适合上头。',
      review_status: 'approved',
    },
    scheduledAt: '2026-06-24T08:30:00-06:00',
  })

  assert.equal(payload.draft_id, 'ext-x-demo')
  assert.equal(payload.platform, 'x')
  assert.equal(payload.scheduled_at, '2026-06-24T08:30:00-06:00')
  assert.equal(payload.review_status, 'approved')
  assert.equal(payload.requiresReview, false)
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
  assert.equal(payload.publishIntent, false)
})

test('buildScheduleDraftPayload keeps pending drafts blocked for scheduling', async () => {
  const { buildScheduleDraftPayload } = await import('../social-core.js')
  const payload = buildScheduleDraftPayload({
    platformId: 'xhs',
    draft: { id: 'ext-xhs-demo', title: '夏日冰饮', text: '正文', review_status: 'pending' },
  })

  assert.equal(payload.platform, 'xhs')
  assert.equal(payload.review_status, 'pending')
  assert.equal(payload.requiresReview, true)
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
})


test('normalizeScheduleItems prepares safe popup reminder cards with draft previews', () => {
  const items = normalizeScheduleItems([
    {
      draft_id: 'ext-x-due',
      platform: 'x',
      title: '到点提醒',
      scheduled_at: '2026-06-24T08:30:00-06:00',
      status: 'awaiting_final_confirmation',
      due: true,
      requires_final_confirmation: true,
      auto_publish_enabled: true,
      external_actions_locked: false,
      draft: {
        id: 'ext-x-due',
        platform: 'x',
        title: '到点提醒',
        text: '最终确认也不会自动发布。',
        review_status: 'approved',
        status: 'awaiting_final_confirmation',
        schedule_status: 'awaiting_final_confirmation',
        content_plan: { format: 'x_hotspot_short_post', structure: ['反差 hook', '3步 可执行动作'] },
        image_plan: { auto_generate: false, image_model: 'gpt-image', cover_prompt: '可选信息图封面' },
        safety_checklist: ['不自动发布', '不构成投资建议'],
      },
    },
    { draft_id: 'ext-x-due', title: '重复项' },
  ])

  assert.equal(items.length, 1)
  assert.equal(items[0].draft_id, 'ext-x-due')
  assert.equal(items[0].due, true)
  assert.equal(items[0].requires_final_confirmation, true)
  assert.equal(items[0].auto_publish_enabled, false)
  assert.equal(items[0].external_actions_locked, true)
  assert.equal(items[0].draft.text, '最终确认也不会自动发布。')
  assert.equal(items[0].draft.schedule_status, 'awaiting_final_confirmation')
  assert.equal(items[0].draft.content_plan.format, 'x_hotspot_short_post')
  assert.equal(items[0].draft.image_plan.cover_prompt, '可选信息图封面')
  assert.deepEqual(items[0].draft.safety_checklist, ['不自动发布', '不构成投资建议'])
})


test('normalizeReviewPack keeps persona proposal and bounded samples for owner confirmation', () => {
  const pack = normalizeReviewPack({
    persona: {
      display_name: '热点抽象观察员',
      one_liner: '中英热点观察员 + 抽象吐槽',
      positioning: '追中文/英文趋势，用短、怪、有反差的表达制造互动。',
      tone: ['短', '怪', '有反差'],
      content_mix: { x: '70% 热点短吐槽', xhs: '生活化热点笔记' },
    },
    persona_approved: false,
    samples: [
      { id: 's1', platform: 'x', title: '美股回调别慌', text: '先看就业数据，再看收益率。', source: 'hacker_news' },
      { id: 's1', platform: 'x', title: '重复', text: '重复' },
      { id: 's2', platform: 'xhs', title: '夏日冰饮', text: '家人们，三分钟做一杯。' },
    ],
    guardrails: ['不自动发布', '不批量评论'],
  })

  assert.equal(pack.persona.display_name, '热点抽象观察员')
  assert.equal(pack.persona_approved, false)
  assert.equal(pack.samples.length, 2)
  assert.equal(pack.samples[0].platform, 'x')
  assert.equal(pack.samples[1].platform, 'xhs')
  assert.deepEqual(pack.guardrails, ['不自动发布', '不批量评论'])
  assert.equal(pack.auto_publish_enabled, false)
  assert.equal(pack.external_actions_locked, true)
})

test('buildPersonaReviewPayload never grants publishing permission', () => {
  const payload = buildPersonaReviewPayload({ approved: true, reviewer: 'owner', notes: '方向可以，但逐条审核。' })

  assert.equal(payload.approved, true)
  assert.equal(payload.reviewer, 'owner')
  assert.equal(payload.notes, '方向可以，但逐条审核。')
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
})


test('buildPageProbeReportPayload stores only calibration summary and never enables publishing', () => {
  const platform = detectSocialPlatform('https://creator.xiaohongshu.com/publish/publish')
  const payload = buildPageProbeReportPayload({
    platform,
    tab: { url: 'https://creator.xiaohongshu.com/publish/publish' },
    probeResult: {
      ready: true,
      availableFields: [
        { name: 'title', kind: 'title', tag: 'input', selector: 'should-not-send' },
        { name: 'body', kind: 'body', tag: 'textarea' },
      ],
    },
  })

  assert.equal(payload.platform, 'xhs')
  assert.equal(payload.ready, true)
  assert.deepEqual(payload.availableFields, [
    { name: 'title', kind: 'title', tag: 'input' },
    { name: 'body', kind: 'body', tag: 'textarea' },
  ])
  assert.equal(payload.auto_publish_enabled, false)
  assert.equal(payload.external_actions_locked, true)
})

test('strategy preset is no-code and safely included in draft payload', () => {
  const settings = mergeSocialSettings({ strategyPreset: 'x_absurd_growth', personaTags: ['学生', '出海'] })

  assert.equal(settings.strategyPreset, 'x_absurd_growth')
  assert.equal(mergeSocialSettings({ strategyPreset: 'auto_publish_bot' }).strategyPreset, 'auto_mcn_growth')

  const payload = buildDraftCreatePayload({
    platform: detectSocialPlatform('https://x.com/explore'),
    tab: { url: 'https://x.com/explore', title: 'X Explore' },
    settings,
    pageContext: { title: '年轻人开始用抽象梗解释降息' },
  })

  assert.equal(payload.settings.strategyPreset, 'x_absurd_growth')
  assert.deepEqual(payload.settings.personaTags, ['学生', '出海'])
})

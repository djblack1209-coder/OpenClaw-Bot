import test from 'node:test'
import assert from 'node:assert/strict'

import { buildAutofillPayload, buildPageProbePayload } from '../social-core.js'
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
} from '../social-page-runner.js'

class FakeElement {
  constructor(tagName, { visible = true, text = '', dataset = {}, attributes = {} } = {}) {
    this.tagName = tagName.toUpperCase()
    this.visible = visible
    this.value = ''
    this.textContent = text
    this.innerText = text
    this.dataset = dataset
    this.attributes = attributes
    this.placeholder = attributes.placeholder || ''
    this.focused = false
    this.events = []
    this.clicked = false
  }

  getBoundingClientRect() {
    return this.visible ? { width: 320, height: 48 } : { width: 0, height: 0 }
  }

  focus() {
    this.focused = true
  }

  dispatchEvent(event) {
    this.events.push(event.type)
    return true
  }

  getAttribute(name) {
    return this.attributes[name] || ''
  }

  click() {
    this.clicked = true
  }
}

function withFakePage(selectorMap, callback, options = {}) {
  const locationDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'location')
  const previous = {
    document: globalThis.document,
    getComputedStyle: globalThis.getComputedStyle,
    InputEvent: globalThis.InputEvent,
    Event: globalThis.Event,
    KeyboardEvent: globalThis.KeyboardEvent,
    getSelection: globalThis.getSelection,
  }

  globalThis.document = {
    body: selectorMap.get('__body__')?.[0] || { innerText: '', textContent: '' },
    querySelectorAll(selector) {
      return selectorMap.get(selector) || []
    },
    createRange() {
      return { selectNodeContents() {} }
    },
    execCommand(_command, _showUi, value) {
      const target = selectorMap.get('__active_contenteditable__')?.[0]
      if (target) target.textContent = value
      return Boolean(target)
    },
  }
  globalThis.getComputedStyle = (el) => ({
    display: el.visible ? 'block' : 'none',
    visibility: el.visible ? 'visible' : 'hidden',
  })
  globalThis.InputEvent = class {
    constructor(type) {
      this.type = type
    }
  }
  globalThis.Event = class {
    constructor(type) {
      this.type = type
    }
  }
  globalThis.KeyboardEvent = class {
    constructor(type, options = {}) {
      this.type = type
      this.key = options.key || ''
      this.code = options.code || ''
      this.bubbles = Boolean(options.bubbles)
      this.cancelable = Boolean(options.cancelable)
    }
  }
  globalThis.getSelection = () => ({ removeAllRanges() {}, addRange() {} })
  if (options.url) {
    Object.defineProperty(globalThis, 'location', {
      configurable: true,
      value: { href: String(options.url) },
    })
  }

  try {
    return callback()
  } finally {
    globalThis.document = previous.document
    globalThis.getComputedStyle = previous.getComputedStyle
    globalThis.InputEvent = previous.InputEvent
    globalThis.Event = previous.Event
    globalThis.KeyboardEvent = previous.KeyboardEvent
    globalThis.getSelection = previous.getSelection
    if (locationDescriptor) {
      Object.defineProperty(globalThis, 'location', locationDescriptor)
    } else {
      delete globalThis.location
    }
  }
}

test('runSocialFieldPlanInPage probes visible fields without mutating content', () => {
  const title = new FakeElement('input')
  const body = new FakeElement('textarea')
  const selectorMap = new Map([
    ['input[placeholder*="标题"]', [title]],
    ['textarea[placeholder*="正文"]', [body]],
  ])

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(buildPageProbePayload({ platformId: 'xhs' })))

  assert.equal(result.ready, true)
  assert.equal(result.filled, false)
  assert.deepEqual(result.availableFields.map((item) => item.name), ['title', 'body'])
  assert.equal(title.value, '')
  assert.equal(body.value, '')
})

test('runSocialFieldPlanInPage fills Xiaohongshu title and body separately', () => {
  const title = new FakeElement('input')
  const body = new FakeElement('textarea')
  const selectorMap = new Map([
    ['input[placeholder*="标题"]', [title]],
    ['textarea[placeholder*="正文"]', [body]],
  ])
  const payload = buildAutofillPayload({
    platformId: 'xhs',
    draft: { title: '3分钟做出一杯夏日冰饮', text: '家人们，冷泡茶 + 柠檬 + 冰块就能复刻。' },
  })

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(payload))

  assert.equal(result.filled, true)
  assert.deepEqual(result.fields, ['title', 'body'])
  assert.equal(title.value, '3分钟做出一杯夏日冰饮')
  assert.equal(body.value, '家人们，冷泡茶 + 柠檬 + 冰块就能复刻。')
  assert.deepEqual(title.events, ['input', 'change'])
  assert.deepEqual(body.events, ['input', 'change'])
})

test('runSocialFieldPlanInPage fills X contenteditable but never clicks publish controls', () => {
  const compose = new FakeElement('div')
  const publishButton = new FakeElement('button')
  const selectorMap = new Map([
    ['div[data-testid^="tweetTextarea"][role="textbox"]', [compose]],
    ['__active_contenteditable__', [compose]],
    ['button[data-testid="tweetButtonInline"]', [publishButton]],
  ])
  const payload = buildAutofillPayload({
    platformId: 'x',
    draft: { title: 'GitHub异常Star工具榜', text: '今天适合收藏，不适合上头。' },
  })

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(payload))

  assert.equal(result.filled, true)
  assert.deepEqual(result.fields, ['compose'])
  assert.match(compose.textContent, /GitHub异常Star工具榜/)
  assert.equal(publishButton.clicked, false)
  assert.equal(result.publishClicked, false)
})

test('runSocialFieldPlanInPage probes nested X composer variants on real pages', () => {
  const compose = new FakeElement('div')
  const selectorMap = new Map([
    ['div[data-testid^="tweetTextarea"] div[contenteditable="true"]', [compose]],
  ])

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(buildPageProbePayload({ platformId: 'x' })))

  assert.equal(result.ready, true)
  assert.deepEqual(result.availableFields.map((item) => item.name), ['compose'])
  assert.equal(compose.value, '')
})

test('runSocialFieldPlanInPage probes Xiaohongshu Quill editor variants', () => {
  const editor = new FakeElement('div')
  const selectorMap = new Map([
    ['.ql-editor[contenteditable="true"]', [editor]],
  ])

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(buildPageProbePayload({ platformId: 'xhs' })))

  assert.equal(result.ready, true)
  assert.deepEqual(result.availableFields.map((item) => item.name), ['body'])
  assert.equal(editor.textContent, '')
})

test('runSocialFieldPlanInPage probes Xianyu placeholder-based chat editors', () => {
  const editor = new FakeElement('div')
  const selectorMap = new Map([
    ['div[contenteditable="true"][data-placeholder*="请输入"]', [editor]],
  ])

  const result = withFakePage(selectorMap, () => runSocialFieldPlanInPage(buildPageProbePayload({ platformId: 'xianyu' })))

  assert.equal(result.ready, true)
  assert.deepEqual(result.availableFields.map((item) => item.name), ['reply_or_description'])
  assert.equal(editor.textContent, '')
})


test('runSocialInteractionScanInPage extracts visible comment-like signals without clicking', () => {
  const comment = new FakeElement('div', { text: '这个工具怎么部署？求一个小白步骤', dataset: { testid: 'tweetText' } })
  const hidden = new FakeElement('div', { visible: false, text: '隐藏内容不应采集' })
  const publishButton = new FakeElement('button', { text: 'Reply' })
  const selectorMap = new Map([
    ['[data-testid="tweetText"]', [comment, hidden]],
    ['article [lang]', []],
    ['button[data-testid="tweetButtonInline"]', [publishButton]],
  ])

  const result = withFakePage(selectorMap, () => runSocialInteractionScanInPage({ platform: 'x', limit: 4 }))

  assert.equal(result.ready, true)
  assert.equal(result.platform, 'x')
  assert.equal(result.action, 'scan_interactions')
  assert.equal(result.signals.length, 1)
  assert.equal(result.signals[0].text, '这个工具怎么部署？求一个小白步骤')
  assert.equal(result.signals[0].auto_reply_enabled, false)
  assert.equal(result.auto_publish_enabled, false)
  assert.equal(result.external_actions_locked, true)
  assert.equal(publishButton.clicked, false)
})


test('runSocialPerformanceScanInPage reads visible metrics without clicking page controls', () => {
  const like = new FakeElement('span', { text: '128 Likes' })
  const reply = new FakeElement('span', { text: '12 Replies' })
  const repost = new FakeElement('span', { text: '7 Reposts' })
  const view = new FakeElement('span', { text: '12K views' })
  const replyButton = new FakeElement('button', { text: 'Reply' })
  const selectorMap = new Map([
    ['[data-testid="like"]', [like]],
    ['[data-testid="reply"]', [reply]],
    ['[data-testid="retweet"]', [repost]],
    ['[aria-label*="views"]', [view]],
    ['button[data-testid="tweetButtonInline"]', [replyButton]],
  ])

  const result = withFakePage(selectorMap, () => runSocialPerformanceScanInPage({ platform: 'x', url: 'https://x.com/example/status/1' }))

  assert.equal(result.ready, true)
  assert.equal(result.platform, 'x')
  assert.equal(result.action, 'scan_performance')
  assert.equal(result.metrics.likes, 128)
  assert.equal(result.metrics.comments, 12)
  assert.equal(result.metrics.shares, 7)
  assert.equal(result.metrics.impressions, 12000)
  assert.equal(result.auto_publish_enabled, false)
  assert.equal(result.external_actions_locked, true)
  assert.equal(replyButton.clicked, false)
})

test('runSocialPageContextScanInPage extracts platform hotspot context without clicking controls', () => {
  const xTrend = new FakeElement('div', { text: 'GitHub 一周异常 Star 工具榜', dataset: { testid: 'trend' } })
  const xPost = new FakeElement('div', { text: '年轻创业者今天都在讨论 AI Agent 怎么落地', dataset: { testid: 'tweetText' } })
  const publishButton = new FakeElement('button', { text: 'Post' })
  const selectorMap = new Map([
    ['[data-testid="trend"]', [xTrend]],
    ['[data-testid="tweetText"]', [xPost]],
    ['article [lang]', []],
    ['button[data-testid="tweetButtonInline"]', [publishButton]],
  ])

  const result = withFakePage(selectorMap, () => runSocialPageContextScanInPage({ platform: 'x', url: 'https://x.com/home', title: 'X Home' }))

  assert.equal(result.ready, true)
  assert.equal(result.platform, 'x')
  assert.equal(result.action, 'scan_page_context')
  assert.deepEqual(result.trends, ['GitHub 一周异常 Star 工具榜'])
  assert.match(result.bodyText, /AI Agent 怎么落地/)
  assert.equal(result.auto_publish_enabled, false)
  assert.equal(result.external_actions_locked, true)
  assert.equal(result.publishIntent, false)
  assert.equal(publishButton.clicked, false)
})

test('runXianyuDeliveryScanInPage extracts real order id from paid page URL or label', () => {
  const body = new FakeElement('div', { text: '订单号：998877665544332211 买家已付款，等待卖家发货' })
  const editor = new FakeElement('textarea')
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(
    selectorMap,
    () => runXianyuDeliveryScanInPage(),
    { url: 'https://www.goofish.com/order/detail?orderId=123456789012345' },
  )

  assert.equal(result.ready, true)
  assert.equal(result.orderIdHint, '123456789012345')
})

test('runXianyuDeliveryScanInPage extracts real order id from shipment link href when text hides it', () => {
  const body = new FakeElement('div', { text: '¥1.00 等待卖家发货 去发货' })
  const editor = new FakeElement('textarea')
  const shipLink = new FakeElement('a', { text: '去发货', attributes: { href: 'https://seller.goofish.com/deliver?bizOrderId=2468135790246813' } })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [shipLink]],
    ['a[href],[href],[data-order-id],[data-orderid],[data-trade-id],[data-tradeid],[data-biz-order-id],[data-bizorder-id],[data-bizorderid]', [shipLink]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryScanInPage())

  assert.equal(result.ready, true)
  assert.equal(result.orderIdHint, '2468135790246813')
  assert.equal(result.orderCardPresent, true)
  assert.equal(result.shipActionPresent, true)
})

test('runXianyuDeliveryScanInPage does not treat item link id as real order id', () => {
  const body = new FakeElement('div', { text: '¥1.00 等待卖家发货 商品详情' })
  const editor = new FakeElement('textarea')
  const itemLink = new FakeElement('a', { text: '商品详情', attributes: { href: 'https://www.goofish.com/item?id=9988776655443322' } })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [itemLink]],
    ['a[href],[href],[data-order-id],[data-orderid],[data-trade-id],[data-tradeid],[data-biz-order-id],[data-bizorder-id],[data-bizorderid]', [itemLink]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryScanInPage())

  assert.equal(result.ready, true)
  assert.equal(result.orderIdHint, '')
  assert.equal(result.orderCardPresent, true)
})

test('runXianyuDeliveryScanInPage requires paid signal and visible chat input', () => {
  const body = new FakeElement('div', { text: '订单状态：买家已付款，等待卖家发货' })
  const editor = new FakeElement('textarea')
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryScanInPage())

  assert.equal(result.ready, true)
  assert.equal(result.paidSignal, true)
  assert.equal(result.inputReady, true)
  assert.equal(result.sendButtonReady, true)
})

test('runXianyuDeliveryScanInPage accepts mobile Xianyu reminder and chat placeholder', () => {
  const body = new FakeElement('div', { text: '¥1.00 我已付款，等待你发货 记得及时发货' })
  const editor = new FakeElement('textarea')
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="想跟"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryScanInPage())

  assert.equal(result.ready, true)
  assert.equal(result.paidSignal, true)
  assert.equal(result.inputReady, true)
  assert.ok(result.paidSignals.includes('记得及时发货'))
})

test('runXianyuDeliveryFillAndSendInPage fills delivery message and clicks send after paid signal', () => {
  const body = new FakeElement('div', { text: '买家已付款，等待你发货' })
  const editor = new FakeElement('textarea')
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryFillAndSendInPage({
    shipmentId: 7,
    deliveryMessage: '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-TEST',
  }))

  assert.equal(result.sent, true)
  assert.equal(editor.value, '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-TEST')
  assert.equal(send.clicked, true)
})

test('runXianyuDeliveryFillAndSendInPage presses Enter when Xianyu exposes no send button', () => {
  const body = new FakeElement('div', { text: '买家已付款，等待卖家发货' })
  const editor = new FakeElement('textarea', {
    attributes: { placeholder: '请输入消息，按Enter键发送或点击发送按钮发送' },
  })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="请输入"]', [editor]],
    ['button,[role="button"],a', []],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryFillAndSendInPage({
    shipmentId: 9,
    deliveryMessage: '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ENTER',
  }))

  assert.equal(result.sent, true)
  assert.equal(result.sendMethod, 'enter')
  assert.equal(editor.value, '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ENTER')
  assert.deepEqual(editor.events.filter((event) => event.startsWith('key')), ['keydown', 'keyup'])
})

test('runXianyuDeliveryFillAndSendInPage clears duplicate card draft without sending again', () => {
  const body = new FakeElement('div', { text: '买家已付款，等待卖家发货' })
  const editor = new FakeElement('textarea')
  editor.value = '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-DUPLICATE'
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryFillAndSendInPage({
    shipmentId: 10,
    deliveryMessage: '兑换入口：https://jiyu.245334.xyz\n兑换码：CC-DUPLICATE',
  }))

  assert.equal(result.sent, false)
  assert.equal(result.filled, false)
  assert.equal(result.clearedDuplicateDraft, true)
  assert.equal(result.reason, 'duplicate_delivery_draft_cleared')
  assert.equal(editor.value, '')
  assert.equal(send.clicked, false)
})

test('runXianyuDeliveryDraftCleanupInPage clears leftover card draft for already handled orders', () => {
  const body = new FakeElement('div', { text: '订单状态：买家已付款，等待卖家发货' })
  const editor = new FakeElement('textarea')
  editor.value = '您好，您购买的 CC中转 已自动发货。\n兑换码：CC-LEFTOVER-DRAFT\n兑换入口：https://jiyu.245334.xyz'
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryDraftCleanupInPage({
    shipmentId: 11,
    reason: 'already_handled_cleanup',
  }))

  assert.equal(result.ready, true)
  assert.equal(result.clearedDraft, true)
  assert.equal(result.reason, 'delivery_draft_cleared')
  assert.equal(editor.value, '')
  assert.equal(send.clicked, false)
})

test('runXianyuDeliveryFillAndSendInPage blocks send when paid signal is missing', () => {
  const body = new FakeElement('div', { text: '普通聊天：还在吗' })
  const editor = new FakeElement('textarea')
  const send = new FakeElement('button', { text: '发送' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['textarea[placeholder*="回复"]', [editor]],
    ['button,[role="button"],a', [send]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuDeliveryFillAndSendInPage({
    shipmentId: 8,
    deliveryMessage: '兑换码：CC-SHOULD-NOT-SEND',
  }))

  assert.equal(result.sent, false)
  assert.equal(result.reason, 'no_paid_order_signal')
  assert.equal(editor.value, '')
  assert.equal(send.clicked, false)
})

test('runXianyuConfirmShipmentInPage clicks safe paid shipment controls in order', () => {
  const body = new FakeElement('div', { text: '订单状态：买家已付款，等待卖家发货' })
  const goShip = new FakeElement('button', { text: '去发货' })
  const noLogistics = new FakeElement('button', { text: '无需物流' })
  const confirm = new FakeElement('button', { text: '确认发货' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['button,[role="button"],a', [goShip, noLogistics, confirm]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuConfirmShipmentInPage({ shipmentId: 11 }))

  assert.equal(result.confirmed, true)
  assert.deepEqual(result.clickedTexts, ['去发货', '无需物流', '确认发货'])
  assert.equal(goShip.clicked, true)
  assert.equal(noLogistics.clicked, true)
  assert.equal(confirm.clicked, true)
})

test('runXianyuConfirmShipmentInPage blocks shipment click when paid signal is missing', () => {
  const body = new FakeElement('div', { text: '普通聊天：什么时候能便宜一点' })
  const goShip = new FakeElement('button', { text: '去发货' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['button,[role="button"],a', [goShip]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuConfirmShipmentInPage({ shipmentId: 12 }))

  assert.equal(result.confirmed, false)
  assert.equal(result.reason, 'no_paid_order_signal')
  assert.equal(goShip.clicked, false)
})

test('runXianyuRelistItemInPage clicks relist only when the item is clearly unavailable', () => {
  const body = new FakeElement('div', { text: '商品状态：已售罄 已下架 可重新上架' })
  const relist = new FakeElement('button', { text: '重新上架' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['button,[role="button"],a', [relist]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuRelistItemInPage({ itemId: 'item-001' }))

  assert.equal(result.relisted, true)
  assert.equal(result.clickedText, '重新上架')
  assert.equal(relist.clicked, true)
})

test('runXianyuRelistItemInPage does not click relist while item is already on sale', () => {
  const body = new FakeElement('div', { text: '商品状态：在售中 正常展示' })
  const relist = new FakeElement('button', { text: '重新上架' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['button,[role="button"],a', [relist]],
  ])

  const result = withFakePage(selectorMap, () => runXianyuRelistItemInPage({ itemId: 'item-001' }))

  assert.equal(result.relisted, false)
  assert.equal(result.onlineVerified, true)
  assert.equal(result.ready, true)
  assert.equal(result.reason, 'item_already_online')
  assert.equal(relist.clicked, false)
})

test('runXianyuRelistItemInPage verifies accessible goofish item detail page as online', () => {
  const body = new FakeElement('div', { text: 'CC中转测试商品 自动发货 价格 1元' })
  const relist = new FakeElement('button', { text: '重新上架' })
  const selectorMap = new Map([
    ['__body__', [body]],
    ['button,[role="button"],a', [relist]],
  ])

  const result = withFakePage(
    selectorMap,
    () => runXianyuRelistItemInPage({ itemId: 'item-001' }),
    { url: 'https://www.goofish.com/item?id=1065629676333' },
  )

  assert.equal(result.unavailableSignal, false)
  assert.equal(result.onlineVerified, true)
  assert.equal(result.ready, true)
  assert.equal(result.reason, 'item_detail_online')
  assert.equal(relist.clicked, false)
})

test('runSocialPageContextScanInPage extracts Xiaohongshu and Xianyu page signals', () => {
  const noteTitle = new FakeElement('div', { text: '夏日低卡冰饮教程' })
  const noteBody = new FakeElement('div', { text: '家人们，冷泡茶加柠檬真的适合收藏' })
  const xhsMap = new Map([
    ['[class*="note"] [class*="title"]', [noteTitle]],
    ['[class*="content"]', [noteBody]],
    ['[class*="comment"]', []],
  ])

  const xhs = withFakePage(xhsMap, () => runSocialPageContextScanInPage({ platform: 'xhs', url: 'https://www.xiaohongshu.com/explore', title: '小红书' }))

  assert.equal(xhs.ready, true)
  assert.equal(xhs.platform, 'xhs')
  assert.ok(xhs.headings.includes('夏日低卡冰饮教程'))
  assert.match(xhs.bodyText, /冷泡茶加柠檬/)

  const itemTitle = new FakeElement('div', { text: 'MacBook Air M2 低价出' })
  const chat = new FakeElement('div', { text: '买家问还能不能便宜一点，今天能不能发货' })
  const sendButton = new FakeElement('button', { text: '发送' })
  const xianyuMap = new Map([
    ['[class*="item"] [class*="title"]', [itemTitle]],
    ['[class*="message"]', [chat]],
    ['[class*="chat"]', []],
    ['button', [sendButton]],
  ])

  const xianyu = withFakePage(xianyuMap, () => runSocialPageContextScanInPage({ platform: 'xianyu', url: 'https://www.goofish.com/item?id=1', title: '闲鱼商品' }))

  assert.equal(xianyu.ready, true)
  assert.equal(xianyu.platform, 'xianyu')
  assert.ok(xianyu.headings.includes('MacBook Air M2 低价出'))
  assert.match(xianyu.bodyText, /今天能不能发货/)
  assert.equal(sendButton.clicked, false)
})

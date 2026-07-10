import test from 'node:test'
import assert from 'node:assert/strict'

import { extractXianyuOrderIdFromHeadInfoPayload } from './cc_xianyu_headinfo_parser.mjs'

test('extractXianyuOrderIdFromHeadInfoPayload reads paid headinfo orderId', () => {
  const payload = {
    data: {
      orderId: '1234567890123456789',
      utArgs: {
        orderStatusName: '买家拍下了宝贝，并且已经付款',
        orderStatus: '2',
      },
      middle: {
        data: {
          price: '1.00',
          tips: '等待卖家发货',
        },
      },
    },
  }

  const result = extractXianyuOrderIdFromHeadInfoPayload(payload)

  assert.equal(result.orderId, '1234567890123456789')
  assert.equal(result.itemId, '')
  assert.equal(result.ok, true)
})

test('extractXianyuOrderIdFromHeadInfoPayload keeps itemId separate from orderId', () => {
  const payload = {
    data: {
      commonData: {
        itemId: '1065629676333',
        orderDetailUrl: 'fleamarket://order_detail?id=3234567890123456789',
      },
      utArgs: { orderStatusName: '买家拍下了宝贝，并且已经付款' },
      middle: { data: { tips: '等待卖家发货' } },
    },
  }

  const result = extractXianyuOrderIdFromHeadInfoPayload(payload)

  assert.equal(result.ok, true)
  assert.equal(result.orderId, '3234567890123456789')
  assert.equal(result.itemId, '1065629676333')
})

test('extractXianyuOrderIdFromHeadInfoPayload reads logistics deliver url in JSONP text', () => {
  const payloadText = `mtopjsonp1({"data":{"right":{"data":{"btnList":[{"name":"去发货","tradeAction":"LOGISTICS_SEND","clickEvent":{"type":"openPage","data":{"url":"https://h5.m.goofish.com/wow/moyu/moyu-project/idle-logistics/pages/deliver?kun=true&orderId=2234567890123456789"}}}]}},"middle":{"data":{"tips":"等待卖家发货"}}}})`

  const result = extractXianyuOrderIdFromHeadInfoPayload(payloadText)

  assert.equal(result.orderId, '2234567890123456789')
  assert.equal(result.ok, true)
})

test('extractXianyuOrderIdFromHeadInfoPayload ignores item ids without paid delivery context', () => {
  const payload = {
    data: {
      itemId: '1065629676333',
      itemUrl: 'https://www.goofish.com/item?id=1065629676333',
      title: 'CC中转测试宝贝',
    },
  }

  const result = extractXianyuOrderIdFromHeadInfoPayload(payload)

  assert.equal(result.ok, false)
  assert.equal(result.orderId, '')
})

test('extractXianyuOrderIdFromHeadInfoPayload ignores item id even when paid context exists', () => {
  const payload = {
    data: {
      itemId: '1065629676333',
      itemUrl: 'https://www.goofish.com/item?id=1065629676333',
      utArgs: { orderStatusName: '买家拍下了宝贝，并且已经付款' },
      middle: { data: { tips: '等待卖家发货' } },
    },
  }

  const result = extractXianyuOrderIdFromHeadInfoPayload(payload)

  assert.equal(result.ok, false)
  assert.equal(result.orderId, '')
})

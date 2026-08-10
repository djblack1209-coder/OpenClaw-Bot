import { createHash, timingSafeEqual } from 'node:crypto';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

import {
  createSub2ApiRedeemStore,
  isAllowedXianyuDenomination,
} from './sub2ApiRedeemStore.js';

const MAX_BODY_BYTES = 64 * 1024;
const DEFAULT_GATEWAY = 'https://jiyu.245334.xyz';
const PAID_STATUS = /等待卖家发货|买家已付款|已付款|待发货|paid|seller.*ship/i;

export function createFristApiServer(options = {}) {
  const token = String(
    options.xianyuWebhookToken ?? process.env.FRIST_API_XIANYU_WEBHOOK_TOKEN ?? '',
  ).trim();
  const gateway = normalizeGateway(options.publicGatewayBaseUrl ?? process.env.FRIST_API_PUBLIC_GATEWAY_BASE_URL);
  const store = options.xianyuRedeemStore || createSub2ApiRedeemStore(options);

  return createServer(async (request, response) => {
    setJsonHeaders(response);
    try {
      if (request.method === 'GET' && (request.url === '/' || request.url === '/health')) {
        return sendJson(response, 200, { status: 'ok', service: 'jiyu-xianyu-fulfillment' });
      }
      if (request.method !== 'POST' || !['/api/ops/xianyu/paid-order', '/api/ops/xianyu/remap-order'].includes(request.url)) {
        return sendJson(response, 404, { error: 'not_found' });
      }
      if (!token || !sameSecret(request.headers['x-cc-xianyu-token'], token)) {
        return sendJson(response, 401, { error: 'unauthorized' });
      }
      if (!store) return sendJson(response, 503, { error: 'fulfillment_unavailable' });
      const body = await readJson(request);
      const result = request.url.endsWith('/remap-order')
        ? await remapOrder(store, body)
        : await fulfillOrder(store, body, gateway);
      return sendJson(response, 200, result);
    } catch (error) {
      return sendJson(response, error.status || statusForError(error), {
        error: publicMessage(error),
      });
    }
  });
}

export async function closeFristApiServer(server) {
  await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const host = process.env.FRIST_API_HOST || '127.0.0.1';
  const port = Number(process.env.FRIST_API_PORT || 3180);
  const server = createFristApiServer();
  server.listen(port, host, () => {
    process.stdout.write(`jiyu-xianyu-fulfillment listening on ${host}:${port}\n`);
  });
  const shutdown = async () => {
    server.close();
    process.exit(0);
  };
  process.once('SIGTERM', shutdown);
  process.once('SIGINT', shutdown);
}

async function fulfillOrder(store, body, gateway) {
  const normalized = normalizePaidOrder(body);
  if (!normalized.paid) throw httpError(409, '订单未确认已付款，自动发货已阻断');
  const denomination = resolveDenomination(body);
  let reservation;
  try {
    reservation = await store.reserve({
      orderHash: orderHash(normalized.orderId),
      denomination,
      planId: normalized.planId,
    });
  } catch (error) {
    throw normalizeStoreError(error);
  }
  const title = normalized.productTitle || `${denomination}元 JIYU AI 兑换码`;
  return {
    ok: true,
    autoShip: true,
    order: normalized,
    fulfillment: {
      platform: 'xianyu',
      orderId: normalized.orderId,
      productTitle: title,
      planId: normalized.planId,
      denomination,
      cardId: `sub2api:${reservation.redeemCodeId}`,
      status: 'delivered',
      createdAt: reservation.reservedAt,
      updatedAt: reservation.reservedAt,
    },
    card: {
      id: `sub2api:${reservation.redeemCodeId}`,
      code: reservation.code,
      codePreview: maskCode(reservation.code),
      denomination,
      source: 'sub2api-reservation',
      status: reservation.status,
    },
    deliveryMessage: buildDeliveryMessage(title, reservation.code, gateway),
    idempotent: reservation.idempotent,
  };
}

async function remapOrder(store, body) {
  const oldOrderId = cleanText(body.oldOrderId || body.fromOrderId, 200);
  const newOrderId = cleanText(body.newOrderId || body.toOrderId, 200);
  if (!oldOrderId || !newOrderId) throw httpError(400, '原订单号和新订单号不能为空');
  let reservation;
  try {
    reservation = await store.remap({
      oldOrderHash: orderHash(oldOrderId),
      newOrderHash: orderHash(newOrderId),
    });
  } catch (error) {
    throw normalizeStoreError(error);
  }
  return {
    ok: true,
    idempotent: reservation.idempotent,
    fulfillment: {
      platform: 'xianyu',
      orderId: newOrderId,
      denomination: reservation.denomination,
      cardId: `sub2api:${reservation.redeemCodeId}`,
      status: 'delivered',
      createdAt: reservation.reservedAt,
      updatedAt: reservation.reservedAt,
    },
    card: {
      id: `sub2api:${reservation.redeemCodeId}`,
      code: reservation.code,
      codePreview: maskCode(reservation.code),
      denomination: reservation.denomination,
      source: 'sub2api-reservation',
      status: reservation.status,
    },
  };
}

function normalizePaidOrder(body = {}) {
  const status = [body.status, body.orderStatus, body.payStatus, body.tradeStatus, body.redReminder]
    .map((value) => cleanText(value, 120)).filter(Boolean).join(' ');
  const paid = body.paid === true || PAID_STATUS.test(status);
  const orderId = cleanText(body.orderId || body.orderNo || body.tradeId || body.id, 200);
  if (!orderId) throw httpError(400, '闲鱼订单号不能为空');
  return {
    orderId,
    paid,
    status: status || (paid ? 'paid' : 'unknown'),
    productTitle: cleanText(body.productTitle || body.itemTitle || body.title, 160),
    buyerHint: cleanText(body.buyerHint || body.buyerName || body.buyerId || body.userId, 120),
    planId: cleanText(body.planId || body.skuId || body.spec, 120),
    note: cleanText(body.note, 500),
  };
}

function resolveDenomination(body) {
  for (const candidate of [body.denomination, body.faceValue, body.value, body.quotaUsd, body.creditUsd, body.amountCny]) {
    if (candidate !== undefined && candidate !== null && String(candidate).trim() !== '' && isAllowedXianyuDenomination(candidate)) {
      return Number(candidate);
    }
  }
  const raw = `${body.planId || body.skuId || body.spec || ''} ${body.productTitle || body.itemTitle || body.title || ''}`;
  const match = raw.match(/(?:^|[^0-9])(1000|500|300|100|50|30|10|1)\s*(?:元|CNY|RMB)?(?:$|[^0-9])/i);
  if (match && isAllowedXianyuDenomination(match[1])) return Number(match[1]);
  throw httpError(400, '无法确认闲鱼商品面额，已阻断自动发货');
}

function buildDeliveryMessage(title, code, gateway) {
  return [
    `您好，您购买的 ${title} 已自动发货。`,
    `兑换码：${code}`,
    `兑换入口：${gateway}`,
    '使用步骤：',
    '1. 打开兑换入口，注册或登录账号。',
    '2. 进入“兑换码”，粘贴兑换码，兑换成功后额度会到账。',
    '3. 进入“API Key”，创建自己的 API Key。',
    '4. 进入“CC Switch”，复制导入链接，导入后选择模型测试。',
    '兑换成功后后台会记录到账状态，麻烦确认收货；如遇问题请直接回复订单消息。',
  ].join('\n');
}

function orderHash(orderId) {
  return createHash('sha256').update(`xianyu:${orderId}`, 'utf8').digest('hex');
}

function maskCode(code) {
  const value = String(code || '');
  return value.length <= 8 ? '****' : `${value.slice(0, 4)}****${value.slice(-4)}`;
}

function normalizeGateway(value) {
  const gateway = String(value || DEFAULT_GATEWAY).trim().replace(/\/+$/, '');
  return gateway.replace(/\/v1$/i, '') || DEFAULT_GATEWAY;
}

function cleanText(value, maxLength) {
  return String(value || '').replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, maxLength);
}

async function readJson(request) {
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > MAX_BODY_BYTES) throw httpError(413, '请求体过大');
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8')) || {};
  } catch {
    throw httpError(400, 'JSON 请求无效');
  }
}

function sameSecret(value, expected) {
  const left = Buffer.from(String(value || ''), 'utf8');
  const right = Buffer.from(expected, 'utf8');
  return left.length === right.length && timingSafeEqual(left, right);
}

function setJsonHeaders(response) {
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.setHeader('cache-control', 'no-store');
  response.setHeader('x-content-type-options', 'nosniff');
}

function sendJson(response, status, body) {
  response.statusCode = status;
  response.end(JSON.stringify(body));
  return response;
}

function httpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function statusForError(error) {
  const message = String(error?.message || '');
  if (message.includes('NO_AVAILABLE_REDEEM_CODE')) return 409;
  if (message.includes('ORDER_DENOMINATION_MISMATCH') || message.includes('TARGET_ORDER_ALREADY_RESERVED')) return 409;
  if (message.includes('RESERVATION_NOT_FOUND')) return 404;
  if (error instanceof TypeError) return 400;
  return 503;
}

function publicMessage(error) {
  if (error?.status) return error.message;
  const message = String(error?.message || '');
  if (message.includes('NO_AVAILABLE_REDEEM_CODE')) return '该面额暂时没有可发货兑换码';
  if (message.includes('ORDER_DENOMINATION_MISMATCH')) return '同一闲鱼订单的商品面额不一致，已阻断重复发货';
  if (message.includes('TARGET_ORDER_ALREADY_RESERVED')) return '新订单号已经存在，未重复接管';
  if (message.includes('RESERVATION_NOT_FOUND')) return '没有找到可接管的 Sub2API 兑换码预留';
  if (error instanceof TypeError) return error.message;
  return 'Sub2API 兑换码预留暂时不可用，未执行自动发货';
}

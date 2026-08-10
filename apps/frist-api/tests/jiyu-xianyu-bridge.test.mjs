import assert from 'node:assert/strict';
import { test } from 'node:test';

import { closeFristApiServer, createFristApiServer } from '../bridge/server.js';

test('JIYU Xianyu bridge authenticates, blocks unpaid orders, and is idempotent', async () => {
  const store = fakeStore();
  const server = createFristApiServer({
    xianyuWebhookToken: 'test-bridge-token',
    publicGatewayBaseUrl: 'https://jiyu.example.test/v1',
    xianyuRedeemStore: store,
  });
  await listen(server);
  try {
    const unauthorized = await request(server, '/api/ops/xianyu/paid-order', {
      orderId: 'order-unauthorized', paid: true, denomination: 10,
    });
    assert.equal(unauthorized.status, 401);

    const unpaid = await request(server, '/api/ops/xianyu/paid-order', {
      orderId: 'order-unpaid', status: '等待买家付款', denomination: 10,
    }, true);
    assert.equal(unpaid.status, 409);
    assert.equal(store.reserveCalls, 0);

    const first = await request(server, '/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-10', status: '等待卖家发货', denomination: 10,
    }, true);
    assert.equal(first.status, 200);
    assert.equal(first.body.fulfillment.denomination, 10);
    assert.equal(first.body.idempotent, false);
    assert.match(first.body.deliveryMessage, /BRIDGE-10-ONLY/);

    const duplicate = await request(server, '/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-10', paid: true, denomination: 10,
    }, true);
    assert.equal(duplicate.status, 200);
    assert.equal(duplicate.body.idempotent, true);
    assert.equal(store.allocations.size, 1);
  } finally {
    await closeFristApiServer(server);
  }
});

test('JIYU Xianyu bridge remaps an existing reservation without allocating again', async () => {
  const store = fakeStore();
  const server = createFristApiServer({ xianyuWebhookToken: 'test-bridge-token', xianyuRedeemStore: store });
  await listen(server);
  try {
    const paid = await request(server, '/api/ops/xianyu/paid-order', {
      orderId: 'browser-order-30', paid: true, denomination: 30,
    }, true);
    assert.equal(paid.status, 200);
    const remapped = await request(server, '/api/ops/xianyu/remap-order', {
      oldOrderId: 'browser-order-30', newOrderId: 'real-order-30',
    }, true);
    assert.equal(remapped.status, 200);
    assert.equal(remapped.body.fulfillment.orderId, 'real-order-30');
    assert.equal(store.allocations.size, 1);
    assert.equal(store.remapCalls, 1);
  } finally {
    await closeFristApiServer(server);
  }
});

function fakeStore() {
  const allocations = new Map();
  return {
    allocations,
    reserveCalls: 0,
    remapCalls: 0,
    async reserve({ orderHash, denomination }) {
      this.reserveCalls += 1;
      if (allocations.has(orderHash)) return { ...allocations.get(orderHash), idempotent: true };
      const reservation = {
        redeemCodeId: String(allocations.size + 1),
        code: `BRIDGE-${denomination}-ONLY`,
        denomination,
        status: 'unused',
        reservedAt: '2026-08-10T00:00:00.000Z',
        idempotent: false,
      };
      allocations.set(orderHash, reservation);
      return reservation;
    },
    async remap({ oldOrderHash, newOrderHash }) {
      this.remapCalls += 1;
      const reservation = allocations.get(oldOrderHash);
      if (!reservation) throw new Error('RESERVATION_NOT_FOUND');
      allocations.delete(oldOrderHash);
      allocations.set(newOrderHash, reservation);
      return { ...reservation, idempotent: false };
    },
  };
}

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
}

async function request(server, path, body, authenticated = false) {
  const address = server.address();
  const response = await fetch(`http://127.0.0.1:${address.port}${path}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(authenticated ? { 'x-cc-xianyu-token': 'test-bridge-token' } : {}),
    },
    body: JSON.stringify(body),
  });
  return { status: response.status, body: await response.json() };
}

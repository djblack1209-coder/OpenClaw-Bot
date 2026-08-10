import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { createFristApiServer } from '../server/server.js';

test('Sub2API-backed Xianyu fulfillment is paid-only, idempotent, and plaintext-free at rest', async () => {
  const fixture = await createFixture();
  try {
    const unauthorized = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-unauthorized',
      paid: true,
      denomination: 10,
    });
    assert.equal(unauthorized.status, 401);

    const unpaid = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-unpaid',
      status: '等待买家付款',
      paid: false,
      denomination: 10,
    }, true);
    assert.equal(unpaid.status, 409);
    assert.equal(fixture.store.reserveCalls, 0);

    const first = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-10',
      status: '等待卖家发货',
      paid: true,
      productTitle: 'JIYU AI 10元兑换码',
      planId: 'jiyu-10',
    }, true);
    assert.equal(first.status, 200);
    assert.equal(first.json.fulfillment.denomination, 10);
    assert.equal(first.json.card.id, 'sub2api:10');
    assert.equal(first.json.card.code, 'JIYU-••••-ONLY');
    assert.match(first.json.deliveryMessage, /JIYU-TEST-10-ONLY/);

    const duplicate = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-10',
      status: '买家已付款',
      paid: true,
      productTitle: 'JIYU AI 10元兑换码',
      planId: 'jiyu-10',
    }, true);
    assert.equal(duplicate.status, 200);
    assert.equal(duplicate.json.idempotent, true);
    assert.equal(fixture.store.allocations.size, 1);

    const rawRuntime = await readFile(fixture.dataFile, 'utf8');
    assert.equal(rawRuntime.includes('JIYU-TEST-10-ONLY'), false);
  } finally {
    await fixture.close();
  }
});

test('Sub2API-backed Xianyu fulfillment rejects unsupported or ambiguous denominations', async () => {
  const fixture = await createFixture();
  try {
    const unsupported = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-5',
      status: '已付款',
      paid: true,
      denomination: 5,
      productTitle: 'JIYU AI 5元兑换码',
    }, true);
    assert.equal(unsupported.status, 400);

    const ambiguous = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'order-paid-unknown',
      status: '已付款',
      paid: true,
      productTitle: 'JIYU AI 兑换码',
    }, true);
    assert.equal(ambiguous.status, 400);
    assert.equal(fixture.store.reserveCalls, 0);
  } finally {
    await fixture.close();
  }
});

test('Xianyu order remap moves the existing Sub2API reservation without allocating again', async () => {
  const fixture = await createFixture();
  try {
    const paid = await fixture.request('/api/ops/xianyu/paid-order', {
      orderId: 'browser-order-30',
      status: '已付款',
      paid: true,
      denomination: 30,
      productTitle: 'JIYU AI 30元兑换码',
    }, true);
    assert.equal(paid.status, 200);

    const remapped = await fixture.request('/api/ops/xianyu/remap-order', {
      oldOrderId: 'browser-order-30',
      newOrderId: 'real-order-30',
    }, true);
    assert.equal(remapped.status, 200);
    assert.equal(remapped.json.fulfillment.orderId, 'real-order-30');
    assert.equal(fixture.store.allocations.size, 1);
    assert.equal(fixture.store.remapCalls, 1);
  } finally {
    await fixture.close();
  }
});

test('production mode accepts the constrained Sub2API reservation path without New-API runtime', async () => {
  const fixture = await createFixture({
    publicMode: true,
    enforceProductionReadiness: true,
    requireAdmin2fa: true,
    adminTotpSecrets: 'JBSWY3DPEHPK3PXP',
    requireTurnstile: true,
    turnstileSiteKey: 'turnstile-site-key',
    turnstileSecret: 'turnstile-secret',
    dataEncryptionKey: 'production-test-data-encryption-key',
    adminToken: 'production-test-admin-token-0123456789',
    sessionSecret: 'production-test-session-secret-0123456789',
    adminPageCode: 'production-admin-page-code',
    requireCsrf: true,
  });
  try {
    assert.notEqual(await fixture.request('/', {}, false, 'GET').then((result) => result.status), 500);
  } finally {
    await fixture.close();
  }
});

async function createFixture(options = {}) {
  const directory = await mkdtemp(join(tmpdir(), 'frist-sub2api-xianyu-'));
  const dataFile = join(directory, 'runtime.json');
  const store = createFakeRedeemStore();
  const server = createFristApiServer({
    dataFile,
    publicDir: directory,
    publicGatewayBaseUrl: 'https://jiyu.245334.xyz/v1',
    xianyuWebhookToken: 'test-xianyu-token',
    sub2ApiDatabaseUrl: 'postgresql://restricted:password@127.0.0.1:5432/sub2api',
    xianyuRedeemStore: store,
    channelMonitorEnabled: false,
    newApiEnabled: false,
    cardAutoreplenishEnabled: false,
    ...options,
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  return {
    dataFile,
    store,
    async request(path, body, authenticated = false, method = 'POST') {
      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers: {
          'content-type': 'application/json',
          ...(authenticated ? { 'x-cc-xianyu-token': 'test-xianyu-token' } : {}),
        },
        body: method === 'GET' ? undefined : JSON.stringify(body),
      });
      return { status: response.status, json: await response.json() };
    },
    async close() {
      await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
      await rm(directory, { recursive: true, force: true });
    },
  };
}

function createFakeRedeemStore() {
  const allocations = new Map();
  let reserveCalls = 0;
  let remapCalls = 0;
  return {
    allocations,
    get reserveCalls() {
      return reserveCalls;
    },
    get remapCalls() {
      return remapCalls;
    },
    async reserve({ orderHash, denomination }) {
      reserveCalls += 1;
      const existing = allocations.get(orderHash);
      if (existing) return { ...existing, idempotent: true };
      const reservation = {
        redeemCodeId: String(denomination),
        code: `JIYU-TEST-${denomination}-ONLY`,
        denomination,
        status: 'unused',
        reservedAt: '2026-08-10T00:00:00.000Z',
        idempotent: false,
      };
      allocations.set(orderHash, reservation);
      return reservation;
    },
    async remap({ oldOrderHash, newOrderHash }) {
      remapCalls += 1;
      const reservation = allocations.get(oldOrderHash);
      if (!reservation) throw new Error('RESERVATION_NOT_FOUND');
      allocations.delete(oldOrderHash);
      allocations.set(newOrderHash, reservation);
      return { ...reservation, idempotent: false };
    },
    async close() {},
  };
}

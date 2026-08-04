import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { createRuntimeStore } from '../server/runtime-store.js';


function normalizeRuntime(data = {}) {
  return {
    counter: Number(data.counter || 0),
    userKeys: Array.isArray(data.userKeys) ? data.userKeys : [],
    credentials: Array.isArray(data.credentials) ? data.credentials : [],
    plusAccounts: Array.isArray(data.plusAccounts) ? data.plusAccounts : [],
    rtAccounts: Array.isArray(data.rtAccounts) ? data.rtAccounts : [],
  };
}


test('runtime store serializes mutations and rejects async work from the normal queue', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'frist-runtime-store-'));
  const dataFile = join(sandbox, 'runtime.json');
  try {
    const store = createRuntimeStore(dataFile, '', null, normalizeRuntime);
    const results = await Promise.all([
      store.mutate((data) => {
        data.counter += 1;
        return data.counter;
      }),
      store.mutate((data) => {
        data.counter += 1;
        return data.counter;
      }),
    ]);

    assert.deepEqual(results, [1, 2]);
    assert.equal((await store.load()).counter, 2);
    assert.equal((await stat(dataFile)).mode & 0o777, 0o600);

    await assert.rejects(
      store.mutate(async (data) => {
        data.counter += 10;
      }),
      /只允许同步数据变更/,
    );
    assert.equal((await store.load()).counter, 2);
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});


test('runtime store encrypts secrets at rest and restores them through the same interface', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'frist-runtime-encryption-'));
  const dataFile = join(sandbox, 'runtime.json');
  try {
    const store = createRuntimeStore(dataFile, 'fixture-encryption-key', null, normalizeRuntime);
    await store.mutate((data) => {
      data.userKeys.push({ id: 'key-1', secret: 'fk-live-secret' });
      data.credentials.push({ id: 'credential-1', rawKey: 'provider-secret' });
      data.plusAccounts.push({ id: 'plus-1', secrets: 'account-secret' });
      data.rtAccounts.push({ id: 'rt-1', refreshToken: 'refresh-secret' });
    });

    const raw = await readFile(dataFile, 'utf8');
    assert.match(raw, /enc:v1:/);
    for (const secret of ['fk-live-secret', 'provider-secret', 'account-secret', 'refresh-secret']) {
      assert.doesNotMatch(raw, new RegExp(secret));
    }

    const loaded = await store.load();
    assert.equal(loaded.userKeys[0].secret, 'fk-live-secret');
    assert.equal(loaded.credentials[0].rawKey, 'provider-secret');
    assert.equal(loaded.plusAccounts[0].secrets, 'account-secret');
    assert.equal(loaded.rtAccounts[0].refreshToken, 'refresh-secret');
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});


test('runtime store requires a normalization boundary', () => {
  assert.throws(() => createRuntimeStore('/tmp/unused-runtime.json'), /必须提供同步数据规范化函数/);
});

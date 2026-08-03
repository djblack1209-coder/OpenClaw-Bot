import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmod, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import { mapOwnershipFile } from '../../../scripts/frist_api_newapi_ownership_map.mjs';

describe('Frist New-API 显式归属映射', () => {
  it('defaults to dry-run without changing runtime or creating a backup', async () => {
    const fixture = await createRuntimeFixture();
    try {
      const before = await readFile(fixture.file);
      const result = await mapOwnershipFile({
        file: fixture.file,
        tokenId: '1',
        userId: 'user-1',
        reason: '生产邮箱哈希与上游用户证据一致',
      });

      assert.equal(result.applied, false);
      assert.equal(result.mode, 'dry-run');
      assert.equal(result.backup, null);
      assert.equal(result.upstreamVerification.verified, false);
      assert.deepEqual(await readFile(fixture.file), before);
      assert.deepEqual(await readdir(fixture.dir), ['runtime.json']);
    } finally {
      await fixture.close();
    }
  });

  it('backs up the exact source and atomically adds one explicit owner on apply', async () => {
    const fixture = await createRuntimeFixture();
    try {
      await chmod(fixture.file, 0o640);
      const before = await readFile(fixture.file);
      const newApiDb = await fixture.createNewApiDb([
        { id: 1, unlimitedQuota: 0, remainQuota: 500_000 },
      ]);
      const result = await mapOwnershipFile({
        file: fixture.file,
        tokenId: '1',
        userId: 'user-1',
        reason: '生产邮箱哈希与上游用户证据一致',
        backupDir: fixture.backupDir,
        newApiDb,
        apply: true,
      });

      assert.equal(result.applied, true);
      assert.deepEqual(await readFile(result.backup), before);
      const after = JSON.parse(await readFile(fixture.file, 'utf8'));
      assert.deepEqual(
        {
          userId: after.newApiTokenOwners['1'].userId,
          state: after.newApiTokenOwners['1'].state,
          source: after.newApiTokenOwners['1'].source,
          mappingReason: after.newApiTokenOwners['1'].mappingReason,
          upstreamQuotaUnits: after.newApiTokenOwners['1'].upstreamQuotaUnits,
        },
        {
          userId: 'user-1',
          state: 'active',
          source: 'explicit_manual_mapping',
          mappingReason: '生产邮箱哈希与上游用户证据一致',
          upstreamQuotaUnits: 500_000,
        },
      );
      assert.match(after.newApiTokenOwners['1'].mappedAt, /^\d{4}-\d{2}-\d{2}T/);
      assert.match(after.newApiTokenOwners['1'].finiteVerifiedAt, /^\d{4}-\d{2}-\d{2}T/);
      assert.equal(after.events.at(-1).type, 'newapi_token_owner_mapped');
      assert.equal(after.events.at(-1).keyId, '1');
    } finally {
      await fixture.close();
    }
  });

  it('rejects unknown users and every attempt to overwrite an owner', async () => {
    const fixture = await createRuntimeFixture({
      newApiTokenOwners: { '1': { userId: 'user-1', state: 'active' } },
    });
    try {
      const newApiDb = await fixture.createNewApiDb([
        { id: 1, unlimitedQuota: 0, remainQuota: 500_000 },
        { id: 2, unlimitedQuota: 0, remainQuota: 500_000 },
      ]);
      await assert.rejects(
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '2',
          userId: 'missing-user',
          reason: '人工证据',
          newApiDb,
          apply: true,
        }),
        /不存在/,
      );
      await assert.rejects(
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '1',
          userId: 'user-1',
          reason: '重复执行',
          newApiDb,
          apply: true,
        }),
        /禁止覆盖/,
      );
      assert.deepEqual((await readdir(fixture.dir)).sort(), ['one-api.db', 'runtime.json']);
    } finally {
      await fixture.close();
    }
  });

  it('fails closed when an apply lock already exists without removing that lock', async () => {
    const fixture = await createRuntimeFixture();
    const lockFile = join(fixture.dir, '.runtime.json.newapi-owner-map.lock');
    try {
      const before = await readFile(fixture.file);
      const newApiDb = await fixture.createNewApiDb([
        { id: 1, unlimitedQuota: 0, remainQuota: 500_000 },
      ]);
      await writeFile(lockFile, '{"pid":999}\n', { mode: 0o600 });
      await assert.rejects(
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '1',
          userId: 'user-1',
          reason: '人工证据',
          newApiDb,
          apply: true,
        }),
        /已有归属映射锁/,
      );
      assert.deepEqual(await readFile(fixture.file), before);
      assert.equal(await readFile(lockFile, 'utf8'), '{"pid":999}\n');
    } finally {
      await fixture.close();
    }
  });

  it('allows only one of two concurrent applies so neither mapping can be lost', async () => {
    const fixture = await createRuntimeFixture({
      users: [
        { id: 'user-1', email: 'first@example.com' },
        { id: 'user-2', email: 'second@example.com' },
      ],
    });
    try {
      const newApiDb = await fixture.createNewApiDb([
        { id: 1, unlimitedQuota: 0, remainQuota: 500_000 },
        { id: 2, unlimitedQuota: 0, remainQuota: 500_000 },
      ]);
      const results = await Promise.allSettled([
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '1',
          userId: 'user-1',
          reason: '第一条人工证据',
          backupDir: fixture.backupDir,
          newApiDb,
          apply: true,
        }),
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '2',
          userId: 'user-2',
          reason: '第二条人工证据',
          backupDir: fixture.backupDir,
          newApiDb,
          apply: true,
        }),
      ]);

      assert.equal(results.filter((result) => result.status === 'fulfilled').length, 1);
      const rejected = results.find((result) => result.status === 'rejected');
      assert.match(rejected.reason.message, /已有归属映射锁/);
      const after = JSON.parse(await readFile(fixture.file, 'utf8'));
      assert.equal(Object.keys(after.newApiTokenOwners).length, 1);
      assert.equal(after.events.filter((event) => event.type === 'newapi_token_owner_mapped').length, 1);
      assert.equal((await readdir(fixture.dir)).includes('.runtime.json.newapi-owner-map.lock'), false);
    } finally {
      await fixture.close();
    }
  });

  it('requires a read-only New-API database check and rejects unlimited tokens', async () => {
    const fixture = await createRuntimeFixture();
    try {
      await assert.rejects(
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '1',
          userId: 'user-1',
          reason: '人工证据',
          apply: true,
        }),
        /必须提供 --newapi-db/,
      );
      const newApiDb = await fixture.createNewApiDb([
        { id: 1, unlimitedQuota: 1, remainQuota: 500_000 },
      ]);
      await assert.rejects(
        mapOwnershipFile({
          file: fixture.file,
          tokenId: '1',
          userId: 'user-1',
          reason: '人工证据',
          newApiDb,
          apply: true,
        }),
        /仍为无限额度/,
      );
      const after = JSON.parse(await readFile(fixture.file, 'utf8'));
      assert.deepEqual(after.newApiTokenOwners, {});
      assert.equal((await readdir(fixture.dir)).includes('.runtime.json.newapi-owner-map.lock'), false);
    } finally {
      await fixture.close();
    }
  });
});

async function createRuntimeFixture(overrides = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'frist-owner-map-'));
  const file = join(dir, 'runtime.json');
  const backupDir = join(dir, 'backups');
  const runtime = {
    users: [{ id: 'user-1', email: 'customer@example.com' }],
    newApiTokenOwners: {},
    events: [],
    preserved: { value: 42 },
    ...overrides,
  };
  await writeFile(file, `${JSON.stringify(runtime, null, 2)}\n`, { mode: 0o600 });
  return {
    dir,
    file,
    backupDir,
    async createNewApiDb(tokens) {
      const database = join(dir, 'one-api.db');
      const values = tokens.map((token) =>
        `(${Number(token.id)}, ${Number(token.unlimitedQuota)}, ${Number(token.remainQuota)})`,
      ).join(',');
      const result = spawnSync('sqlite3', [
        database,
        `CREATE TABLE tokens (id INTEGER PRIMARY KEY, unlimited_quota INTEGER, remain_quota INTEGER); INSERT INTO tokens VALUES ${values};`,
      ], { encoding: 'utf8' });
      assert.equal(result.status, 0, result.stderr || result.error?.message);
      return database;
    },
    async close() {
      await rm(dir, { recursive: true, force: true });
    },
  };
}

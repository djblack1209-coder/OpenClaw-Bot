import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import { applyMigrationToSqlite, buildMigrationPackage, buildMigrationReport } from '../../../scripts/frist_api_newapi_migration_dry_run.mjs';

describe('Frist-API New-API migration package', () => {
  it('creates timestamped backup, rollback script and idempotent migration plan without applying production writes', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-migration-'));
    const runtimeFile = join(dir, 'runtime.json');
    const outputDir = join(dir, 'out');
    const runtime = {
      users: [
        {
          id: 'user-1',
          email: 'owner@example.com',
          emailVerified: true,
          plan: '日卡',
          balanceCents: 7200,
        },
      ],
      userKeys: [
        {
          id: 'key-1',
          userId: 'user-1',
          name: '主 Key',
          secret: 'fk_live_should_be_masked_in_plan',
          enabled: true,
          modelGroup: 'OpenAI',
        },
      ],
      paymentOrders: [
        { id: 'order-1', userId: 'user-1', status: 'paid', amountCents: 888, creditCents: 7200 },
      ],
      events: [{ type: 'gateway_routed', userId: 'user-1', costCents: 12 }],
      credentials: [{ id: 'cred-1', secret: 'sk_upstream_hidden', models: ['gpt-5.5'] }],
    };

    try {
      await writeFile(runtimeFile, `${JSON.stringify(runtime, null, 2)}\n`, 'utf8');
      const report = buildMigrationReport(runtime, { runtimeFile });
      const firstPackage = await buildMigrationPackage(runtime, { runtimeFile, outputDir, timestamp: '20260702T000000Z' });
      const secondPackage = await buildMigrationPackage(runtime, { runtimeFile, outputDir, timestamp: '20260702T000000Z' });
      const planText = readFileSync(firstPackage.planFile, 'utf8');
      const rollbackText = readFileSync(firstPackage.rollbackScript, 'utf8');

      assert.equal(report.totals.users, 1);
      assert.equal(report.totals.enabledUserKeys, 1);
      assert.equal(firstPackage.idempotencyHash, secondPackage.idempotencyHash);
      assert.equal(existsSync(firstPackage.backupFile), true);
      assert.equal(existsSync(firstPackage.planFile), true);
      assert.equal(existsSync(firstPackage.rollbackScript), true);
      assert.equal(planText.includes('fk_live_should_be_masked_in_plan'), false);
      assert.equal(planText.includes('sk_upstream_hidden'), false);
      assert.match(planText, /quota-topup-log/);
      assert.match(rollbackText, /copyFile/);
      assert.match(rollbackText, /runtime.json/);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });


  it('applies users, tokens and billing rows to a New-API SQLite copy idempotently', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'frist-migration-sqlite-'));
    const sqliteDb = join(dir, 'one-api.db');
    const runtime = {
      users: [
        { id: 'user-1', email: 'owner@example.com', emailVerified: true, plan: 'day', balanceCents: 7200, createdAt: '2026-01-01T00:00:00Z' },
      ],
      userKeys: [
        { id: 'key-1', userId: 'user-1', name: '主 Key', secret: 'fk_live_sqlite_apply_masked', enabled: true, modelGroup: 'OpenAI', createdAt: '2026-01-02T00:00:00Z' },
      ],
      paymentOrders: [
        { id: 'order-1', userId: 'user-1', status: 'paid', amountCents: 888, createdAt: '2026-01-03T00:00:00Z' },
      ],
      redemptionCards: [
        { id: 'card-1', label: 'Frist Card', status: 'redeemed', creditCents: 7200, redeemedBy: 'user-1', createdAt: '2026-01-04T00:00:00Z' },
      ],
      events: [{ type: 'gateway_routed', userId: 'user-1', model: 'gpt-5.5', costCents: 12, at: '2026-01-05T00:00:00Z' }],
    };

    try {
      createNewApiSqliteSchema(sqliteDb);
      const first = await applyMigrationToSqlite(runtime, { sqliteDb, timestamp: '20260702T000000Z' });
      const second = await applyMigrationToSqlite(runtime, { sqliteDb, timestamp: '20260702T000000Z' });

      assert.deepEqual(first.insertedOrUpdated, { users: 1, tokens: 1, topUps: 1, redemptions: 1 });
      assert.deepEqual(second.insertedOrUpdated, { users: 1, tokens: 1, topUps: 1, redemptions: 1 });
      assert.equal(sqliteScalar(sqliteDb, 'select count(*) from users where id >= 100001;'), '1');
      assert.equal(sqliteScalar(sqliteDb, 'select count(*) from tokens;'), '1');
      assert.equal(sqliteScalar(sqliteDb, 'select count(*) from top_ups;'), '1');
      assert.equal(sqliteScalar(sqliteDb, 'select count(*) from redemptions;'), '1');
      assert.equal(sqliteScalar(sqliteDb, 'select count(*) from logs;'), '1');
      assert.equal(JSON.stringify(first).includes('fk_live_sqlite_apply_masked'), false);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});

function createNewApiSqliteSchema(sqliteDb) {
  const sql = `
    create table users (id integer primary key, username text unique, password text not null, display_name text, role integer default 1, status integer default 1, email text, access_token char(32) unique, quota integer default 0, used_quota integer default 0, request_count integer default 0, \`group\` varchar(64) default 'default', aff_code varchar(32) unique, aff_count integer default 0, aff_quota integer default 0, aff_history integer default 0, inviter_id integer default 0, setting text, remark varchar(255), created_at integer, last_login_at integer);
    create table tokens (id integer primary key, user_id integer, \`key\` varchar(128) unique, status integer default 1, name text, created_time integer, accessed_time integer, expired_time integer default -1, remain_quota integer default 0, unlimited_quota numeric, model_limits_enabled numeric, model_limits text, allow_ips text default '', used_quota integer default 0, \`group\` text default '', cross_group_retry numeric);
    create table top_ups (id integer primary key, user_id integer, amount integer, money real, trade_no varchar(255) unique, payment_method varchar(50), payment_provider varchar(50) default '', create_time integer, complete_time integer, status text);
    create table redemptions (id integer primary key, user_id integer, \`key\` char(32) unique, status integer default 1, name text, quota integer default 100, created_time integer, redeemed_time integer, used_user_id integer, expired_time integer);
    create table logs (id integer primary key, user_id integer, created_at integer, type integer, content text, username text default '', token_name text default '', model_name text default '', quota integer default 0, prompt_tokens integer default 0, completion_tokens integer default 0, use_time integer default 0, is_stream numeric, channel_id integer, channel_name text, token_id integer default 0, \`group\` text, ip text default '', request_id varchar(64) default '', other text);
  `;
  const result = spawnSync('sqlite3', [sqliteDb], { input: sql, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
}

function sqliteScalar(sqliteDb, sql) {
  const result = spawnSync('sqlite3', [sqliteDb, sql], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

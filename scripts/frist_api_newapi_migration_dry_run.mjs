#!/usr/bin/env node
import { createHash, createDecipheriv } from 'node:crypto';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { basename, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_RUNTIME_FILE = 'apps/frist-api/data/runtime.json';
const DEFAULT_OUTPUT_DIR = 'apps/frist-api/data/migration-plans';

export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const runtimeFile = resolve(args.file || process.env.FRIST_API_DATA_FILE || DEFAULT_RUNTIME_FILE);
  const runtime = await readRuntime(runtimeFile, args.dataEncryptionKey || process.env.FRIST_API_DATA_ENCRYPTION_KEY || '');
  const report = buildMigrationReport(runtime, { runtimeFile });

  if (args.package) {
    const migrationPackage = await buildMigrationPackage(runtime, {
      runtimeFile,
      outputDir: resolve(args.outputDir || DEFAULT_OUTPUT_DIR),
      timestamp: args.timestamp || timestampForFile(new Date()),
    });
    process.stdout.write(`${JSON.stringify({ ...report, package: migrationPackage }, null, 2)}\n`);
    return;
  }

  if (!args.apply) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return;
  }

  // 参考 Docker Compose / New-API 生产迁移 SOP（2026-07-02 复核）：只有显式 --apply 且已有备份、幂等计划和回滚脚本时才写入 New-API SQLite。
  const sqliteDb = resolve(args.sqliteDb || process.env.FRIST_API_NEWAPI_SQLITE_DB || '');
  if (!sqliteDb) {
    throw new Error('--apply 需要 --sqlite-db 或 FRIST_API_NEWAPI_SQLITE_DB');
  }

  const timestamp = args.timestamp || timestampForFile(new Date());
  const migrationPackage = await buildMigrationPackage(runtime, {
    runtimeFile,
    outputDir: resolve(args.outputDir || DEFAULT_OUTPUT_DIR),
    timestamp,
  });
  const sqliteRollback = await buildSqliteRollbackPackage({
    sqliteDb,
    outputDir: migrationPackage.outputDir,
    timestamp,
  });
  const applyResult = await applyMigrationToSqlite(runtime, {
    sqliteDb,
    dryRunSqliteDb: args.dryRunSqliteDb ? resolve(args.dryRunSqliteDb) : '',
    timestamp,
  });
  applyResult.sqliteBackupFile = sqliteRollback.backupFile;
  applyResult.sqliteRollbackScript = sqliteRollback.rollbackScript;
  process.stdout.write(`${JSON.stringify({
    ...report,
    package: migrationPackage,
    apply: applyResult,
  }, null, 2)}\n`);
}

async function readRuntime(file, encryptionKey = '') {
  try {
    const runtime = JSON.parse(await readFile(file, 'utf8'));
    return decryptRuntimeData(runtime, encryptionKey);
  } catch (error) {
    if (error.code === 'ENOENT') {
      return {};
    }
    throw error;
  }
}

export function buildMigrationReport(runtime, { runtimeFile }) {
  const users = Array.isArray(runtime.users) ? runtime.users : [];
  const keys = Array.isArray(runtime.userKeys) ? runtime.userKeys : [];
  const orders = Array.isArray(runtime.paymentOrders) ? runtime.paymentOrders : [];
  const events = Array.isArray(runtime.events) ? runtime.events : [];
  const credentials = Array.isArray(runtime.credentials) ? runtime.credentials : [];
  const redemptions = Array.isArray(runtime.redemptions) ? runtime.redemptions : [];

  return {
    mode: 'dry-run',
    runtimeFile,
    generatedAt: new Date().toISOString(),
    totals: {
      users: users.length,
      userKeys: keys.length,
      enabledUserKeys: keys.filter((key) => key.enabled !== false).length,
      supplierCredentials: credentials.length,
      paymentOrders: orders.length,
      paidOrders: orders.filter((order) => ['paid', 'confirmed'].includes(String(order.status || ''))).length,
      redemptions: redemptions.length,
      usageEvents: events.filter((event) => event.type === 'gateway_routed').length,
      encryptedUserKeys: keys.filter((key) => isEncryptedRuntimeSecret(key.secret)).length,
    },
    users: users.map((user) => ({
      id: user.id,
      email: maskEmail(user.email),
      emailVerified: Boolean(user.emailVerified),
      plan: user.plan || '',
      balanceCents: Number(user.balanceCents || 0),
      packageQuotaCents: Number(user.packageQuotaCents || 0),
      boosterQuotaCents: Number(user.boosterQuotaCents || 0),
      keyCount: keys.filter((key) => key.userId === user.id).length,
      paidOrderCount: orders.filter(
        (order) => order.userId === user.id && ['paid', 'confirmed'].includes(String(order.status || '')),
      ).length,
    })),
    tokenPlan: keys.map((key) => ({
      id: key.id,
      userId: key.userId,
      name: key.name,
      enabled: Boolean(key.enabled),
      modelGroup: key.modelGroup || 'All',
      preview: isEncryptedRuntimeSecret(key.secret) ? 'requires-rotation' : key.preview || maskKey(key.secret),
      newApiTarget: isEncryptedRuntimeSecret(key.secret) ? 'manual-rotation-required' : 'token',
    })),
    orderPlan: orders.map((order) => ({
      id: order.id,
      userId: order.userId,
      amountCents: Number(order.amountCents || 0),
      creditCents: Number(order.creditCents || 0),
      provider: order.provider || order.method || '',
      status: order.status || '',
      newApiTarget: ['paid', 'confirmed'].includes(String(order.status || '')) ? 'quota-topup-log' : 'manual-review',
    })),
    warnings: buildWarnings({ runtime, users, keys, credentials }),
  };
}

export function buildMigrationPlan(runtime, { runtimeFile }) {
  const report = buildMigrationReport(runtime, { runtimeFile });
  const userIdMap = new Map(report.users.map((user) => [user.id, `newapi-user:${hashId(user.id)}`]));
  const stablePlan = {
    schemaVersion: 1,
    mode: 'plan-only',
    runtimeFile,
    users: report.users.map((user) => ({
      sourceId: user.id,
      targetExternalId: userIdMap.get(user.id),
      email: user.email,
      emailVerified: user.emailVerified,
      plan: user.plan,
      quotaCents: user.balanceCents + user.packageQuotaCents + user.boosterQuotaCents,
    })),
    tokens: report.tokenPlan.map((token) => ({
      sourceId: token.id,
      targetExternalUserId: userIdMap.get(token.userId) || '',
      name: token.name,
      enabled: token.enabled,
      modelGroup: token.modelGroup,
      secretPreview: token.preview,
      action: 'create-or-update-token-by-source-id',
    })),
    orders: report.orderPlan.map((order) => ({
      sourceId: order.id,
      targetExternalUserId: userIdMap.get(order.userId) || '',
      amountCents: order.amountCents,
      creditCents: order.creditCents,
      status: order.status,
      action: order.newApiTarget,
    })),
    warnings: report.warnings,
  };
  return {
    ...stablePlan,
    idempotencyHash: idempotencyHash(stablePlan),
  };
}

export async function buildMigrationPackage(runtime, { runtimeFile, outputDir = DEFAULT_OUTPUT_DIR, timestamp = timestampForFile(new Date()) }) {
  const plan = buildMigrationPlan(runtime, { runtimeFile });
  const safeOutputDir = resolve(outputDir);
  await mkdir(safeOutputDir, { recursive: true });
  const backupFile = resolve(safeOutputDir, `${timestamp}-${basename(runtimeFile)}.backup.json`);
  const planFile = resolve(safeOutputDir, `${timestamp}-newapi-migration-plan.json`);
  const rollbackScript = resolve(safeOutputDir, `${timestamp}-rollback.mjs`);
  await copyFile(runtimeFile, backupFile);
  await writeFile(planFile, `${JSON.stringify(plan, null, 2)}\n`, 'utf8');
  await writeFile(rollbackScript, rollbackScriptText({ backupFile, runtimeFile }), { mode: 0o700 });
  return {
    outputDir: safeOutputDir,
    backupFile,
    planFile,
    rollbackScript,
    idempotencyHash: plan.idempotencyHash,
    applyStatus: 'not-applied',
  };
}

function rollbackScriptText({ backupFile, runtimeFile }) {
  return `#!/usr/bin/env node\nimport { copyFile } from 'node:fs/promises';\n\nconst backupFile = ${JSON.stringify(backupFile)};\nconst runtimeFile = ${JSON.stringify(runtimeFile)};\nawait copyFile(backupFile, runtimeFile);\nprocess.stdout.write(\`rolled back ${runtimeFile} from ${backupFile}\\n\`);\n`;
}


async function buildSqliteRollbackPackage({ sqliteDb, outputDir, timestamp }) {
  const backupFile = resolve(outputDir, `${timestamp}-${basename(sqliteDb)}.backup`);
  const rollbackScript = resolve(outputDir, `${timestamp}-newapi-sqlite-rollback.mjs`);
  await copyFile(sqliteDb, backupFile);
  await writeFile(rollbackScript, sqliteRollbackScriptText({ backupFile, sqliteDb }), { mode: 0o700 });
  return { backupFile, rollbackScript };
}

function sqliteRollbackScriptText({ backupFile, sqliteDb }) {
  return `#!/usr/bin/env node
import { copyFile } from 'node:fs/promises';

const backupFile = ${JSON.stringify(backupFile)};
const sqliteDb = ${JSON.stringify(sqliteDb)};
await copyFile(backupFile, sqliteDb);
process.stdout.write(\`rolled back ${sqliteDb} from ${backupFile}\n\`);
`;
}

function buildWarnings({ runtime, users, keys, credentials }) {
  const warnings = [];
  if (String(JSON.stringify(runtime)).includes('enc:v1:')) {
    warnings.push('runtime 已包含加密字段；真实迁移需要在 Frist-API 进程内或使用同一 FRIST_API_DATA_ENCRYPTION_KEY 解密后导出。');
  }
  if (keys.some((key) => String(key.secret || '').startsWith('fk-live-'))) {
    warnings.push('用户 fk-live Key 可迁移为 New-API Token，但要先确认是否保留原 Key 值还是生成新 Key。');
  }
  if (keys.some((key) => isEncryptedRuntimeSecret(key.secret))) {
    warnings.push('存在未解密的历史用户 Key；没有原 FRIST_API_DATA_ENCRYPTION_KEY 时不能迁移为 New-API Token，只能迁移用户/余额/订单并要求重新生成 Key。');
  }
  if (credentials.length > 0) {
    warnings.push('上游库存 credentials 属于 Frist-API 自研路由，不应直接写入 New-API，需单独映射到 New-API 渠道配置。');
  }
  if (users.some((user) => !user.emailVerified)) {
    warnings.push('存在未验证邮箱用户，真实迁移前建议先执行邮箱验证策略。');
  }
  return warnings;
}



export async function applyMigrationToSqlite(runtime, { sqliteDb, dryRunSqliteDb = '', timestamp = timestampForFile(new Date()) }) {
  const targetDb = dryRunSqliteDb || sqliteDb;
  if (dryRunSqliteDb) {
    await copyFile(sqliteDb, dryRunSqliteDb);
  }
  const plan = buildSqliteMigrationRows(runtime, { timestamp });
  const sql = buildSqliteApplySql(plan);
  runSqlite(targetDb, sql);
  const verify = verifySqliteMigration(targetDb, plan);
  return {
    enabled: true,
    status: dryRunSqliteDb ? 'dry-run-applied-to-copy' : 'applied',
    sqliteDb: targetDb,
    dryRun: Boolean(dryRunSqliteDb),
    sourceCounts: plan.sourceCounts,
    insertedOrUpdated: verify,
  };
}

export function buildSqliteMigrationRows(runtime, { timestamp = timestampForFile(new Date()) } = {}) {
  const users = Array.isArray(runtime.users) ? runtime.users : [];
  const keys = Array.isArray(runtime.userKeys) ? runtime.userKeys : [];
  const orders = Array.isArray(runtime.paymentOrders) ? runtime.paymentOrders : [];
  const events = Array.isArray(runtime.events) ? runtime.events : [];
  const redemptionCards = Array.isArray(runtime.redemptionCards) ? runtime.redemptionCards : [];
  const userIdMap = new Map(users.map((user, index) => [user.id, 100000 + index + 1]));
  const usernameSet = new Set();
  const now = Math.floor(Date.now() / 1000);
  const rows = {
    sourceCounts: {
      users: users.length,
      userKeys: keys.length,
      encryptedUserKeys: keys.filter((key) => isEncryptedRuntimeSecret(key.secret)).length,
      paymentOrders: orders.length,
      redemptionCards: redemptionCards.length,
      usageEvents: events.filter((event) => event.type === 'gateway_routed').length,
    },
    users: users.map((user, index) => {
      const username = uniqueUsername(user, usernameSet, index);
      const quota = centsToNewApiQuota(
        Number(user.balanceCents || 0) + Number(user.packageQuotaCents || 0) + Number(user.boosterQuotaCents || 0),
      );
      return {
        id: userIdMap.get(user.id),
        username,
        password: migrationPasswordHash(user.id),
        display_name: username,
        role: user.isAdmin ? 10 : 1,
        status: 1,
        email: String(user.email || '').slice(0, 50),
        access_token: stableAccessToken(user.id),
        quota,
        used_quota: centsToNewApiQuota(Number(user.usedCents || 0)),
        request_count: 0,
        group: normalizeGroup(user.plan || 'default'),
        aff_code: `frist${hashId(user.id).slice(0, 12)}`,
        aff_count: 0,
        aff_quota: 0,
        aff_history: 0,
        inviter_id: 0,
        setting: JSON.stringify({ migrated_from: 'frist-api-runtime', source_id: user.id, migrated_at: timestamp }),
        remark: `Frist-API runtime migration source=${user.id}`.slice(0, 255),
        created_at: unixTime(user.createdAt, now),
        last_login_at: unixTime(user.updatedAt, 0),
      };
    }),
    tokens: keys
      .filter((key) => key.secret && !isEncryptedRuntimeSecret(key.secret))
      .map((key) => ({
        user_id: userIdMap.get(key.userId) || 0,
        key: String(key.secret || ''),
        status: key.enabled === false ? 2 : 1,
        name: String(key.name || key.preview || `Frist Key ${key.id}`).slice(0, 80),
        created_time: unixTime(key.createdAt, now),
        accessed_time: unixTime(key.lastUsed, 0),
        expired_time: unixTime(key.expiresAt, -1),
        remain_quota: centsToNewApiQuota(Number(key.remainingCents ?? key.quotaRemainingCents ?? 0)),
        unlimited_quota: 1,
        model_limits_enabled: key.modelGroup && key.modelGroup !== 'All' ? 1 : 0,
        model_limits: modelLimitsForGroup(key.modelGroup || 'All'),
        allow_ips: '',
        used_quota: centsToNewApiQuota(Number(key.costCents || 0)),
        group: normalizeGroup(key.modelGroup || 'default'),
        cross_group_retry: 1,
      }))
      .filter((token) => token.user_id > 0),
    topUps: orders.map((order) => ({
      user_id: userIdMap.get(order.userId) || 0,
      amount: Number(order.amountCents || 0),
      money: Number(order.amountCents || 0) / 100,
      trade_no: `frist-${order.id}`.slice(0, 255),
      payment_method: String(order.method || order.provider || 'xianyu-code').slice(0, 50),
      payment_provider: 'frist-api-runtime',
      create_time: unixTime(order.createdAt, now),
      complete_time: ['paid', 'confirmed'].includes(String(order.status || '')) ? unixTime(order.updatedAt, now) : 0,
      status: ['paid', 'confirmed'].includes(String(order.status || '')) ? 'success' : String(order.status || 'pending'),
    })).filter((order) => order.user_id > 0),
    redemptions: redemptionCards.map((card) => ({
      user_id: userIdMap.get(card.redeemedBy) || 0,
      key: stableRedemptionKey(card.id),
      status: card.status === 'redeemed' ? 2 : 1,
      name: String(card.label || card.plan || `Frist redemption ${card.id}`).slice(0, 80),
      quota: centsToNewApiQuota(Number(card.creditCents || 0)),
      created_time: unixTime(card.createdAt, now),
      redeemed_time: unixTime(card.redeemedAt, 0),
      used_user_id: userIdMap.get(card.redeemedBy) || 0,
      expired_time: 0,
    })),
    logs: events.slice(-500).map((event) => ({
      user_id: userIdMap.get(event.userId) || 0,
      created_at: unixTime(event.at || event.createdAt, now),
      type: event.type === 'gateway_routed' ? 2 : event.type === 'payment_confirmed' ? 1 : 4,
      content: `Frist-API migrated event: ${String(event.type || 'event')}`,
      username: '',
      token_name: '',
      model_name: String(event.model || event.modelName || '').slice(0, 80),
      quota: centsToNewApiQuota(Number(event.costCents || 0)),
      prompt_tokens: Number(event.promptTokens || 0),
      completion_tokens: Number(event.completionTokens || 0),
      use_time: Number(event.latencyMs || 0),
      is_stream: event.stream ? 1 : 0,
      channel_id: Number(event.channelId || 0),
      token_id: 0,
      group: normalizeGroup(event.modelGroup || event.group || ''),
      ip: '',
      request_id: String(event.requestId || '').slice(0, 64),
      other: JSON.stringify({ migrated_from: 'frist-api-runtime', source_type: event.type || 'event' }),
    })),
  };
  return rows;
}

function buildSqliteApplySql(plan) {
  const lines = [
    'PRAGMA foreign_keys=OFF;',
    'BEGIN IMMEDIATE;',
  ];
  for (const user of plan.users) {
    lines.push(`INSERT INTO users (id, username, password, display_name, role, status, email, access_token, quota, used_quota, request_count, \`group\`, aff_code, aff_count, aff_quota, aff_history, inviter_id, setting, remark, created_at, last_login_at) VALUES (${[
      user.id, q(user.username), q(user.password), q(user.display_name), user.role, user.status, q(user.email), q(user.access_token), user.quota, user.used_quota, user.request_count, q(user.group), q(user.aff_code), user.aff_count, user.aff_quota, user.aff_history, user.inviter_id, q(user.setting), q(user.remark), user.created_at, user.last_login_at,
    ].join(',')}) ON CONFLICT(id) DO UPDATE SET email=excluded.email, quota=excluded.quota, used_quota=excluded.used_quota, setting=excluded.setting, remark=excluded.remark;`);
  }
  for (const token of plan.tokens) {
    lines.push(`INSERT INTO tokens (user_id, \`key\`, status, name, created_time, accessed_time, expired_time, remain_quota, unlimited_quota, model_limits_enabled, model_limits, allow_ips, used_quota, \`group\`, cross_group_retry) VALUES (${[
      token.user_id, q(token.key), token.status, q(token.name), token.created_time, token.accessed_time, token.expired_time, token.remain_quota, token.unlimited_quota, token.model_limits_enabled, q(token.model_limits), q(token.allow_ips), token.used_quota, q(token.group), token.cross_group_retry,
    ].join(',')}) ON CONFLICT(\`key\`) DO UPDATE SET user_id=excluded.user_id, status=excluded.status, name=excluded.name, accessed_time=excluded.accessed_time, expired_time=excluded.expired_time, used_quota=excluded.used_quota, \`group\`=excluded.\`group\`;`);
  }
  for (const topUp of plan.topUps) {
    lines.push(`INSERT INTO top_ups (user_id, amount, money, trade_no, payment_method, payment_provider, create_time, complete_time, status) VALUES (${[
      topUp.user_id, topUp.amount, topUp.money, q(topUp.trade_no), q(topUp.payment_method), q(topUp.payment_provider), topUp.create_time, topUp.complete_time, q(topUp.status),
    ].join(',')}) ON CONFLICT(trade_no) DO UPDATE SET status=excluded.status, complete_time=excluded.complete_time;`);
  }
  for (const redemption of plan.redemptions) {
    lines.push(`INSERT INTO redemptions (user_id, \`key\`, status, name, quota, created_time, redeemed_time, used_user_id, expired_time) VALUES (${[
      redemption.user_id, q(redemption.key), redemption.status, q(redemption.name), redemption.quota, redemption.created_time, redemption.redeemed_time, redemption.used_user_id, redemption.expired_time,
    ].join(',')}) ON CONFLICT(\`key\`) DO UPDATE SET status=excluded.status, redeemed_time=excluded.redeemed_time, used_user_id=excluded.used_user_id;`);
  }
  for (const log of plan.logs) {
    lines.push(`INSERT INTO logs (user_id, created_at, type, content, username, token_name, model_name, quota, prompt_tokens, completion_tokens, use_time, is_stream, channel_id, token_id, \`group\`, ip, request_id, other) SELECT ${[
      log.user_id, log.created_at, log.type, q(log.content), q(log.username), q(log.token_name), q(log.model_name), log.quota, log.prompt_tokens, log.completion_tokens, log.use_time, log.is_stream, log.channel_id, log.token_id, q(log.group), q(log.ip), q(log.request_id), q(log.other),
    ].join(',')} WHERE NOT EXISTS (SELECT 1 FROM logs WHERE created_at=${log.created_at} AND content=${q(log.content)} AND other=${q(log.other)});`);
  }
  lines.push('COMMIT;');
  return `${lines.join('\n')}\n`;
}

function verifySqliteMigration(sqliteDb, plan) {
  const sql = [
    `select 'users=' || count(*) from users where id >= 100001 and remark like 'Frist-API runtime migration source=%';`,
    `select 'tokens=' || count(*) from tokens where \`key\` in (${plan.tokens.map((token) => q(token.key)).join(',') || "''"});`,
    `select 'topUps=' || count(*) from top_ups where payment_provider='frist-api-runtime';`,
    `select 'redemptions=' || count(*) from redemptions where \`key\` in (${plan.redemptions.map((redemption) => q(redemption.key)).join(',') || "''"});`,
  ].join('\n');
  const output = runSqlite(sqliteDb, sql);
  return Object.fromEntries(output.trim().split(/\n+/).filter(Boolean).map((line) => {
    const [key, value] = line.split('=');
    return [key, Number(value || 0)];
  }));
}

function runSqlite(sqliteDb, sql) {
  const result = spawnSync('sqlite3', [sqliteDb], { input: sql, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
  if (result.status !== 0) {
    throw new Error(`sqlite3 failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout || '';
}

function q(value) {
  return `'${String(value ?? '').replace(/'/g, "''")}'`;
}

function decryptRuntimeData(data, encryptionKey) {
  const secret = String(encryptionKey || '').trim();
  if (!secret) return data;
  const key = createHash('sha256').update(secret).digest();
  const copy = JSON.parse(JSON.stringify(data || {}));
  for (const [collection, field] of [['userKeys', 'secret'], ['credentials', 'rawKey'], ['plusAccounts', 'secrets'], ['rtAccounts', 'refreshToken']]) {
    if (!Array.isArray(copy[collection])) continue;
    copy[collection] = copy[collection].map((item) => ({ ...item, [field]: decryptSecretField(item[field], key) }));
  }
  delete copy.__encryption;
  return copy;
}

function decryptSecretField(value, key) {
  const text = String(value || '');
  if (!text.startsWith('enc:v1:')) return text;
  const [, version, ivText, authTagText, encryptedText] = text.split(':');
  if (version !== 'v1' || !ivText || !authTagText || !encryptedText) {
    throw new Error('运行数据加密字段格式不正确');
  }
  const decipher = createDecipheriv('aes-256-gcm', key, Buffer.from(ivText, 'base64url'));
  decipher.setAuthTag(Buffer.from(authTagText, 'base64url'));
  return `${decipher.update(Buffer.from(encryptedText, 'base64url'), undefined, 'utf8')}${decipher.final('utf8')}`;
}

function isEncryptedRuntimeSecret(value) {
  return String(value || '').startsWith('enc:v1:');
}

function uniqueUsername(user, seen, index) {
  const base = String(user.email || user.id || `frist-${index + 1}`)
    .split('@')[0]
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '')
    .slice(0, 16) || `frist${index + 1}`;
  let name = base;
  let counter = 1;
  while (seen.has(name)) {
    name = `${base.slice(0, 14)}${counter}`.slice(0, 20);
    counter += 1;
  }
  seen.add(name);
  return name;
}

function stableAccessToken(sourceId) {
  return createHash('sha256').update(`frist-access:${sourceId}`).digest('hex').slice(0, 32);
}

function stableRedemptionKey(sourceId) {
  return createHash('sha256').update(`frist-redemption:${sourceId}`).digest('hex').slice(0, 32);
}

function migrationPasswordHash(sourceId) {
  return createHash('sha256').update(`frist-migration-disabled-login:${sourceId}`).digest('hex');
}

function centsToNewApiQuota(cents) {
  return Math.max(0, Math.round((Number(cents || 0) / 100) * 500000));
}

function unixTime(value, fallback) {
  if (!value) return fallback;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : fallback;
}

function normalizeGroup(value) {
  const group = String(value || 'default').trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').slice(0, 64);
  return group || 'default';
}

function modelLimitsForGroup(group) {
  const normalized = String(group || 'All').toLowerCase();
  if (normalized === 'all' || normalized === 'default') return '';
  if (normalized.includes('claude')) return 'claude-*';
  if (normalized.includes('openai')) return 'gpt-*,o*,chatgpt-*';
  if (normalized.includes('deepseek')) return 'deepseek-*';
  if (normalized.includes('gemini')) return 'gemini-*';
  return '';
}

function parseArgs(args) {
  const parsed = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--apply') {
      parsed.apply = true;
    } else if (arg === '--package') {
      parsed.package = true;
    } else if (arg.startsWith('--file=')) {
      parsed.file = arg.slice('--file='.length);
    } else if (arg === '--file') {
      parsed.file = args[index + 1];
      index += 1;
    } else if (arg.startsWith('--output-dir=')) {
      parsed.outputDir = arg.slice('--output-dir='.length);
    } else if (arg === '--output-dir') {
      parsed.outputDir = args[index + 1];
      index += 1;
    } else if (arg.startsWith('--timestamp=')) {
      parsed.timestamp = arg.slice('--timestamp='.length);
    } else if (arg.startsWith('--new-api-base-url=')) {
      parsed.newApiBaseUrl = arg.slice('--new-api-base-url='.length);
    } else if (arg.startsWith('--sqlite-db=')) {
      parsed.sqliteDb = arg.slice('--sqlite-db='.length);
    } else if (arg === '--sqlite-db') {
      parsed.sqliteDb = args[index + 1];
      index += 1;
    } else if (arg.startsWith('--dry-run-sqlite-db=')) {
      parsed.dryRunSqliteDb = arg.slice('--dry-run-sqlite-db='.length);
    } else if (arg === '--dry-run-sqlite-db') {
      parsed.dryRunSqliteDb = args[index + 1];
      index += 1;
    } else if (arg.startsWith('--data-encryption-key=')) {
      parsed.dataEncryptionKey = arg.slice('--data-encryption-key='.length);
    }
  }
  return parsed;
}

function maskEmail(email) {
  const [name, domain] = String(email || '').split('@');
  if (!name || !domain) return '';
  return `${name.slice(0, 2)}${name.length > 2 ? '***' : '*'}@${domain}`;
}

function maskKey(value) {
  const key = String(value || '');
  if (!key) return '';
  return `${key.slice(0, 7)}...${key.slice(-4)}`;
}

function hashId(value) {
  return createHash('sha256').update(String(value || '')).digest('hex').slice(0, 16);
}

function idempotencyHash(value) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

function timestampForFile(date) {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

const isDirectRun = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isDirectRun) {
  main().catch((error) => {
    process.stderr.write(`${error.stack || error.message}\n`);
    process.exitCode = 1;
  });
}

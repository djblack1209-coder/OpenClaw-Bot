#!/usr/bin/env node

import { constants as fsConstants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { copyFile, lstat, mkdir, open, readFile, rename, rm, stat } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export async function mapOwnershipFile(options = {}) {
  const filePath = resolveRequiredPath(options.file, '--file');
  const tokenId = normalizeTokenId(options.tokenId);
  const userId = normalizeRequiredText(options.userId, '--user-id', 160);
  const reason = normalizeRequiredText(options.reason, '--reason', 240);
  const apply = options.apply === true;
  const newApiDb = options.newApiDb ? resolveRequiredPath(options.newApiDb, '--newapi-db') : '';
  if (apply && !newApiDb) {
    throw new Error('--apply 必须提供 --newapi-db，以只读验证目标 Token 已关闭无限额度');
  }
  const lock = apply ? await acquireApplyLock(filePath) : null;
  try {
    const source = await readFile(filePath);
    const runtime = parseRuntime(source, filePath);
    const baseMapping = validateExplicitMapping(runtime, { tokenId, userId, reason });
    const upstreamVerification = newApiDb
      ? await verifyFiniteNewApiToken(newApiDb, tokenId)
      : {
          verified: false,
          tokenId,
          reason: '未提供 --newapi-db；dry-run 仅完成本地归属预检，不能执行 --apply',
        };
    const mapping = upstreamVerification.verified
      ? {
          ...baseMapping,
          upstreamQuotaUnits: upstreamVerification.remainQuotaUnits,
          finiteVerifiedAt: new Date().toISOString(),
        }
      : baseMapping;

    if (!apply) {
      return {
        applied: false,
        mode: 'dry-run',
        file: filePath,
        tokenId,
        userId,
        mapping,
        upstreamVerification,
        backup: null,
      };
    }

    const backupDir = options.backupDir
      ? resolve(String(options.backupDir))
      : join(dirname(filePath), 'backups');
    await mkdir(backupDir, { recursive: true, mode: 0o700 });
    const backupPath = join(
      backupDir,
      `${basename(filePath)}.before-newapi-owner-${backupStamp()}.bak`,
    );
    await copyFile(filePath, backupPath, fsConstants.COPYFILE_EXCL);

    const nextRuntime = applyExplicitOwnershipMapping(runtime, mapping);
    await writeJsonAtomic(filePath, nextRuntime);
    return {
      applied: true,
      mode: 'apply',
      file: filePath,
      tokenId,
      userId,
      mapping: nextRuntime.newApiTokenOwners[tokenId],
      upstreamVerification,
      backup: backupPath,
    };
  } finally {
    await lock?.release();
  }
}

export function validateExplicitMapping(runtime, { tokenId, userId, reason }) {
  if (!runtime || typeof runtime !== 'object' || Array.isArray(runtime)) {
    throw new Error('runtime 根节点必须是 JSON 对象');
  }
  if (!Array.isArray(runtime.users)) {
    throw new Error('runtime.users 必须是数组');
  }
  if (
    runtime.newApiTokenOwners !== undefined &&
    (!runtime.newApiTokenOwners || typeof runtime.newApiTokenOwners !== 'object' || Array.isArray(runtime.newApiTokenOwners))
  ) {
    throw new Error('runtime.newApiTokenOwners 必须是对象');
  }
  if (runtime.events !== undefined && !Array.isArray(runtime.events)) {
    throw new Error('runtime.events 必须是数组');
  }
  const users = runtime.users.filter((user) => String(user?.id || '') === userId);
  if (users.length !== 1) {
    throw new Error(users.length ? `用户 ID ${userId} 不唯一，已拒绝映射` : `用户 ID ${userId} 不存在`);
  }
  if (Object.hasOwn(runtime.newApiTokenOwners || {}, tokenId)) {
    throw new Error(`Token ${tokenId} 已有归属，禁止覆盖`);
  }
  return {
    tokenId,
    userId,
    state: 'active',
    source: 'explicit_manual_mapping',
    mappingReason: reason,
  };
}

export function applyExplicitOwnershipMapping(runtime, mapping) {
  const tokenId = normalizeTokenId(mapping.tokenId ?? mapping.keyId);
  const upstreamQuotaUnits = Number(mapping.upstreamQuotaUnits);
  const finiteVerifiedAt = String(mapping.finiteVerifiedAt || '');
  if (!Number.isSafeInteger(upstreamQuotaUnits) || upstreamQuotaUnits <= 0 || !Number.isFinite(Date.parse(finiteVerifiedAt))) {
    throw new Error(`Token ${tokenId} 缺少有效的有限额度验证证据`);
  }
  const mappedAt = new Date().toISOString();
  const next = structuredClone(runtime);
  next.newApiTokenOwners = next.newApiTokenOwners || {};
  next.events = Array.isArray(next.events) ? next.events : [];
  const owner = {
    userId: mapping.userId,
    state: mapping.state,
    source: mapping.source,
    mappingReason: mapping.mappingReason,
    upstreamQuotaUnits,
    finiteVerifiedAt,
    mappedAt,
  };
  next.newApiTokenOwners[tokenId] = owner;
  next.events.push({
    type: 'newapi_token_owner_mapped',
    userId: mapping.userId,
    keyId: tokenId,
    reason: mapping.mappingReason,
    at: mappedAt,
  });
  return next;
}

function parseRuntime(source, filePath) {
  try {
    return JSON.parse(source.toString('utf8'));
  } catch {
    throw new Error(`无法解析 runtime JSON: ${filePath}`);
  }
}

function normalizeTokenId(value) {
  const tokenId = String(value || '').trim();
  if (!/^[1-9]\d*$/.test(tokenId)) {
    throw new Error('--token-id 必须是正整数 ID');
  }
  return tokenId;
}

function normalizeRequiredText(value, flag, maxLength) {
  const text = String(value || '').trim();
  if (!text) throw new Error(`${flag} 不能为空`);
  if (text.length > maxLength) throw new Error(`${flag} 不能超过 ${maxLength} 个字符`);
  return text;
}

function resolveRequiredPath(value, flag) {
  return resolve(normalizeRequiredText(value, flag, 4096));
}

function backupStamp() {
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, '');
  return `${timestamp}-${process.pid}-${randomBytes(4).toString('hex')}`;
}

async function acquireApplyLock(filePath) {
  const lockPath = join(dirname(filePath), `.${basename(filePath)}.newapi-owner-map.lock`);
  let handle;
  try {
    handle = await open(lockPath, 'wx', 0o600);
    await handle.writeFile(`${JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString() })}\n`, 'utf8');
    await handle.sync();
  } catch (error) {
    if (handle) {
      await handle.close().catch(() => {});
      await rm(lockPath, { force: true }).catch(() => {});
    }
    if (error?.code === 'EEXIST') {
      throw new Error(`检测到已有归属映射锁，已拒绝并发写入: ${lockPath}`);
    }
    throw error;
  }
  return {
    path: lockPath,
    async release() {
      await handle.close();
      await rm(lockPath, { force: true });
    },
  };
}

async function verifyFiniteNewApiToken(databasePath, tokenId) {
  const metadata = await lstat(databasePath);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error('--newapi-db 必须指向普通 SQLite 文件，禁止符号链接');
  }
  const query = [
    'SELECT CAST(id AS TEXT),',
    'CAST(COALESCE(unlimited_quota, 0) AS TEXT),',
    'CAST(COALESCE(remain_quota, 0) AS TEXT)',
    `FROM tokens WHERE id = ${tokenId};`,
  ].join(' ');
  const result = spawnSync(process.env.SQLITE3_BIN || 'sqlite3', [
    '-readonly',
    '-noheader',
    '-separator',
    '\t',
    databasePath,
    query,
  ], {
    encoding: 'utf8',
    timeout: 10_000,
    maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    const detail = String(result.error?.message || result.stderr || 'sqlite3 只读查询失败').split('\n')[0].slice(0, 160);
    throw new Error(`无法只读验证 New-API Token: ${detail}`);
  }
  const rows = String(result.stdout || '').trim().split('\n').filter(Boolean);
  if (rows.length !== 1) {
    throw new Error(rows.length ? `Token ${tokenId} 查询结果不唯一` : `Token ${tokenId} 不存在于 New-API 数据库`);
  }
  const [returnedId, rawUnlimited, rawQuota] = rows[0].split('\t');
  const unlimitedQuota = Number(rawUnlimited);
  const remainQuotaUnits = Number(rawQuota);
  if (returnedId !== tokenId || !Number.isSafeInteger(unlimitedQuota) || !Number.isSafeInteger(remainQuotaUnits)) {
    throw new Error(`Token ${tokenId} 的额度字段无效`);
  }
  if (unlimitedQuota !== 0) {
    throw new Error(`Token ${tokenId} 仍为无限额度，禁止映射到 Frist 客户`);
  }
  if (remainQuotaUnits <= 0) {
    throw new Error(`Token ${tokenId} 的有限额度必须为正数，禁止映射`);
  }
  return {
    verified: true,
    tokenId,
    unlimitedQuota: false,
    remainQuotaUnits,
  };
}

async function writeJsonAtomic(filePath, data) {
  const metadata = await lstat(filePath);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error('runtime 路径必须是普通文件，禁止符号链接');
  }
  const tempPath = join(
    dirname(filePath),
    `.${basename(filePath)}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`,
  );
  const handle = await open(tempPath, 'wx', metadata.mode & 0o777);
  try {
    await handle.writeFile(`${JSON.stringify(data, null, 2)}\n`, 'utf8');
    await handle.sync();
  } catch (error) {
    await rm(tempPath, { force: true }).catch(() => {});
    throw error;
  } finally {
    await handle.close();
  }
  await rename(tempPath, filePath);
  const finalMetadata = await stat(filePath);
  if ((finalMetadata.mode & 0o777) !== (metadata.mode & 0o777)) {
    throw new Error('runtime 原子写入后权限不一致');
  }
  const directory = await open(dirname(filePath), 'r');
  try {
    await directory.sync();
  } finally {
    await directory.close();
  }
}

function parseCliArgs(argv) {
  const options = { apply: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--apply') {
      options.apply = true;
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      options.help = true;
      continue;
    }
    const flagMap = {
      '--file': 'file',
      '--token-id': 'tokenId',
      '--user-id': 'userId',
      '--reason': 'reason',
      '--backup-dir': 'backupDir',
      '--newapi-db': 'newApiDb',
    };
    const key = flagMap[arg];
    if (!key) throw new Error(`未知参数: ${arg}`);
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) throw new Error(`${arg} 缺少值`);
    options[key] = value;
    index += 1;
  }
  return options;
}

function usage() {
  return [
    '用法:',
    '  node scripts/frist_api_newapi_ownership_map.mjs --file <runtime.json> --token-id <id> --user-id <id> --reason <原因> [--newapi-db <one-api.db>]',
    '  增加 --apply 才会写入；apply 必须提供 New-API DB，并只读验证 Token 已关闭无限额度。写入全程持锁、自动备份，已有归属一律拒绝覆盖。',
  ].join('\n');
}

async function main() {
  const options = parseCliArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }
  const result = await mapOwnershipFile(options);
  console.log(JSON.stringify(result, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(`归属映射失败: ${error.message}`);
    process.exitCode = 1;
  });
}

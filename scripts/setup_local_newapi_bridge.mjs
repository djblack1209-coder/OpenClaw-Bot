#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const ROOT = resolve(new URL('..', import.meta.url).pathname);
const ENV_FILE = resolve(ROOT, '.env');
const DEFAULT_DB = resolve(ROOT, 'data/newapi/one-api.db');

function main() {
  const dbFile = resolve(process.env.NEWAPI_SQLITE_DB || DEFAULT_DB);
  if (!existsSync(dbFile)) {
    throw new Error(`未找到 New-API SQLite: ${dbFile}；请先运行 make new-api-up 并完成 New-API 初始化`);
  }
  const user = readBridgeUser(dbFile);
  if (!user.accessToken) {
    throw new Error(`New-API 用户 ${user.username || user.id} 还没有 access token；请先在 New-API 个人资料页生成访问令牌`);
  }
  const env = readEnv(ENV_FILE);
  const updates = {
    NEWAPI_HOST_PORT: env.NEWAPI_HOST_PORT || '3000',
    FRIST_API_NEWAPI_ENABLED: '1',
    FRIST_API_REQUIRE_NEWAPI_DATABASE: '1',
    FRIST_API_NEWAPI_BASE_URL: env.FRIST_API_NEWAPI_BASE_URL || 'http://127.0.0.1:3000',
    FRIST_API_DOCKER_NEWAPI_BASE_URL: env.FRIST_API_DOCKER_NEWAPI_BASE_URL || 'http://new-api:3000',
    FRIST_API_NEWAPI_GATEWAY_ENABLED: '1',
    FRIST_API_NEWAPI_GATEWAY_BASE_URL: env.FRIST_API_NEWAPI_GATEWAY_BASE_URL || 'http://127.0.0.1:3000/v1',
    FRIST_API_DOCKER_NEWAPI_GATEWAY_BASE_URL: env.FRIST_API_DOCKER_NEWAPI_GATEWAY_BASE_URL || 'http://new-api:3000/v1',
    FRIST_API_NEWAPI_ACCESS_TOKEN: user.accessToken,
    FRIST_API_NEWAPI_USER_ID: String(user.id),
    NEWAPI_ADMIN_TOKEN: user.accessToken,
    NEWAPI_ADMIN_USER_ID: String(user.id),
  };
  writeEnv(ENV_FILE, { ...env, ...updates });
  process.stdout.write(
    [
      '✅ 已写入本机 .env：Frist-API 将桥接 QuantumNous/new-api',
      `- New-API 用户: ${user.username || `#${user.id}`} (#${user.id})`,
      '- access token 已写入 .env（未打印到终端）',
      '- Docker 内部地址: http://new-api:3000',
      '- 本机调试地址: http://127.0.0.1:3000',
    ].join('\n') + '\n',
  );
}

function readBridgeUser(dbFile) {
  const sql = [
    '.mode json',
    "select id, username, access_token as accessToken from users where deleted_at is null and status = 1 and coalesce(access_token, '') <> '' order by case when role >= 100 then 0 else 1 end, id limit 1;",
  ].join('\n');
  const result = spawnSync('sqlite3', [dbFile], {
    input: sql,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(`读取 New-API SQLite 失败: ${result.stderr || result.stdout}`);
  }
  const rows = JSON.parse(result.stdout || '[]');
  const row = rows[0];
  if (!row) {
    throw new Error('New-API SQLite 中没有可用 access token 用户');
  }
  return row;
}

function readEnv(file) {
  if (!existsSync(file)) return {};
  const env = {};
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    if (!line || /^\s*#/.test(line) || !line.includes('=')) continue;
    const index = line.indexOf('=');
    env[line.slice(0, index).trim()] = line.slice(index + 1);
  }
  return env;
}

function writeEnv(file, env) {
  const preferredOrder = [
    'NEWAPI_INITIAL_TOKEN',
    'NEWAPI_HOST_PORT',
    'NEWAPI_ADMIN_TOKEN',
    'NEWAPI_ADMIN_USER_ID',
    'FRIST_API_NEWAPI_ENABLED',
    'FRIST_API_REQUIRE_NEWAPI_DATABASE',
    'FRIST_API_NEWAPI_BASE_URL',
    'FRIST_API_DOCKER_NEWAPI_BASE_URL',
    'FRIST_API_NEWAPI_ACCESS_TOKEN',
    'FRIST_API_NEWAPI_USER_ID',
    'FRIST_API_NEWAPI_GATEWAY_ENABLED',
    'FRIST_API_NEWAPI_GATEWAY_BASE_URL',
    'FRIST_API_DOCKER_NEWAPI_GATEWAY_BASE_URL',
  ];
  const keys = [...preferredOrder, ...Object.keys(env).filter((key) => !preferredOrder.includes(key)).sort()];
  const body = keys
    .filter((key) => Object.prototype.hasOwnProperty.call(env, key))
    .map((key) => `${key}=${env[key]}`)
    .join('\n');
  writeFileSync(file, `${body}\n`, { mode: 0o600 });
}

try {
  main();
} catch (error) {
  console.error(`❌ ${error.message}`);
  process.exit(1);
}

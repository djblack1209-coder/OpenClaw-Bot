#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const DEFAULT_RUNTIME_FILE = 'data/frist-api/runtime/runtime.json';

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runtimeFile = resolve(args.file || process.env.FRIST_API_DATA_FILE || DEFAULT_RUNTIME_FILE);
  const runtime = await readRuntime(runtimeFile);
  const report = buildMigrationReport(runtime, { runtimeFile });

  if (!args.apply) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return;
  }

  const baseUrl = String(args.newApiBaseUrl || process.env.FRIST_API_NEWAPI_BASE_URL || '').replace(/\/+$/, '');
  const accessToken = String(args.newApiAccessToken || process.env.FRIST_API_NEWAPI_ACCESS_TOKEN || '').trim();
  const userId = String(args.newApiUserId || process.env.FRIST_API_NEWAPI_USER_ID || '').trim();
  if (!baseUrl || !accessToken || !userId) {
    throw new Error('--apply 需要 FRIST_API_NEWAPI_BASE_URL / ACCESS_TOKEN / USER_ID');
  }

  process.stdout.write(`${JSON.stringify({
    ...report,
    apply: {
      enabled: true,
      status: 'blocked',
      reason: '为避免误写生产 New-API，本脚本当前只执行 dry-run；真实写入需先补用户映射和回滚方案。',
    },
  }, null, 2)}\n`);
}

async function readRuntime(file) {
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') {
      return {};
    }
    throw error;
  }
}

function buildMigrationReport(runtime, { runtimeFile }) {
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
      preview: key.preview || maskKey(key.secret),
      newApiTarget: 'token',
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

function buildWarnings({ runtime, users, keys, credentials }) {
  const warnings = [];
  if (String(JSON.stringify(runtime)).includes('enc:v1:')) {
    warnings.push('runtime 已包含加密字段；真实迁移需要在 Frist-API 进程内或使用同一 FRIST_API_DATA_ENCRYPTION_KEY 解密后导出。');
  }
  if (keys.some((key) => String(key.secret || '').startsWith('fk-live-'))) {
    warnings.push('用户 fk-live Key 可迁移为 New-API Token，但要先确认是否保留原 Key 值还是生成新 Key。');
  }
  if (credentials.length > 0) {
    warnings.push('上游库存 credentials 属于 Frist-API 自研路由，不应直接写入 New-API，需单独映射到 New-API 渠道配置。');
  }
  if (users.some((user) => !user.emailVerified)) {
    warnings.push('存在未验证邮箱用户，真实迁移前建议先执行邮箱验证策略。');
  }
  return warnings;
}

function parseArgs(args) {
  const parsed = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--apply') {
      parsed.apply = true;
    } else if (arg.startsWith('--file=')) {
      parsed.file = arg.slice('--file='.length);
    } else if (arg === '--file') {
      parsed.file = args[index + 1];
      index += 1;
    } else if (arg.startsWith('--new-api-base-url=')) {
      parsed.newApiBaseUrl = arg.slice('--new-api-base-url='.length);
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

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});

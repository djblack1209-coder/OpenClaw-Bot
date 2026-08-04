import { createHmac } from 'node:crypto';
import { isIP } from 'node:net';

export const DEFAULT_RATE_LIMIT_MAX_ENTRIES = 10_000;
const DEFAULT_RATE_LIMIT_CLEANUP_INTERVAL_MS = 60_000;

/** 创建仅由当前服务进程持有的安全状态。 */
export function createSecurityState() {
  return {
    captchas: new Map(),
    rateLimits: new Map(),
    rateLimitCleanupAt: 0,
  };
}

/** 按可信客户端地址限制认证尝试。 */
export function assertAuthRateLimit(securityState, request, serverOptions) {
  const max = Number(serverOptions.authRateLimitMax || 20);
  const windowMs = Number(serverOptions.authRateLimitWindowMs || 60_000);
  assertRateLimit(
    securityState,
    `auth:${clientIp(request, serverOptions)}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
}

/** 将账号邮箱摘要为不泄露明文的重置限流键。 */
export function passwordResetAccountKey(emailValue, secret) {
  const email = String(emailValue || '').trim().toLowerCase();
  const digest = createHmac('sha256', String(secret || '')).update(email).digest('hex');
  return `password-reset:account:${digest}`;
}

/** 对单个账号的密码重置确认实施独立限流。 */
export function assertPasswordResetConfirmRateLimit(securityState, emailValue, serverOptions) {
  const max = Number(serverOptions.passwordResetConfirmRateLimitMax || 5);
  const windowMs = Number(serverOptions.passwordResetConfirmRateLimitWindowMs || 900_000);
  const accountKey = passwordResetAccountKey(emailValue, serverOptions.passwordHashSecret);
  assertRateLimit(securityState, accountKey, max, windowMs, serverOptions.rateLimitMaxEntries);
}

/** 对单个账号的密码重置邮件请求实施独立限流。 */
export function assertPasswordResetRequestRateLimit(securityState, emailValue, serverOptions) {
  const max = Number(serverOptions.passwordResetRequestRateLimitMax || 3);
  const windowMs = Number(serverOptions.passwordResetRequestRateLimitWindowMs || 900_000);
  const accountKey = passwordResetAccountKey(emailValue, serverOptions.passwordHashSecret)
    .replace('password-reset:account:', 'password-reset:request:');
  assertRateLimit(securityState, accountKey, max, windowMs, serverOptions.rateLimitMaxEntries);
}

/** 同时限制邮箱验证码的客户端地址和已登录账号，避免轮换网络或账号绕过。 */
export function assertEmailVerificationRateLimit(securityState, request, serverOptions, userId) {
  const max = Number(serverOptions.emailVerificationRateLimitMax || 5);
  const windowMs = Number(serverOptions.emailVerificationRateLimitWindowMs || 900_000);
  assertRateLimit(
    securityState,
    `email-verification:ip:${clientIp(request, serverOptions)}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
  const digest = createHmac('sha256', String(serverOptions.passwordHashSecret || ''))
    .update(String(userId || ''))
    .digest('hex');
  assertRateLimit(
    securityState,
    `email-verification:account:${digest}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
}

/** 同时限制管理员 2FA 的客户端地址和令牌，避免六位码被批量枚举。 */
export function assertAdminSecondFactorRateLimit(securityState, request, serverOptions) {
  const max = Number(serverOptions.admin2faRateLimitMax ?? 5);
  const windowMs = Number(serverOptions.admin2faRateLimitWindowMs ?? 900_000);
  assertRateLimit(
    securityState,
    `admin-2fa:ip:${clientIp(request, serverOptions)}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
  const token = String(request.headers['x-admin-token'] || 'session-admin');
  const digest = createHmac('sha256', String(serverOptions.passwordHashSecret || ''))
    .update(token)
    .digest('hex');
  assertRateLimit(
    securityState,
    `admin-2fa:token:${digest}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
}

/** 同时限制兑换入口的客户端地址和已登录用户。 */
export function assertRedeemRateLimit(securityState, request, serverOptions, userId = '') {
  const max = Number(serverOptions.redemptionRateLimitMax || 12);
  const windowMs = Number(serverOptions.redemptionRateLimitWindowMs || 60_000);
  assertRateLimit(
    securityState,
    `redeem:ip:${clientIp(request, serverOptions)}`,
    max,
    windowMs,
    serverOptions.rateLimitMaxEntries,
  );
  if (userId) {
    assertRedeemUserRateLimit(securityState, serverOptions, userId);
  }
}

/** 对已登录用户实施兑换限流，避免切换网络绕过。 */
export function assertRedeemUserRateLimit(securityState, serverOptions, userId = '') {
  if (!userId) return;
  const max = Number(serverOptions.redemptionRateLimitMax || 12);
  const windowMs = Number(serverOptions.redemptionRateLimitWindowMs || 60_000);
  assertRateLimit(securityState, `redeem:user:${userId}`, max, windowMs, serverOptions.rateLimitMaxEntries);
}

/** 更新固定窗口计数器，并在超过阈值时失败关闭。 */
export function assertRateLimit(
  securityState,
  key,
  max,
  windowMs,
  maxEntries = DEFAULT_RATE_LIMIT_MAX_ENTRIES,
) {
  if (!Number.isFinite(max) || max <= 0 || !Number.isFinite(windowMs) || windowMs <= 0) {
    return;
  }
  const now = Date.now();
  const entryLimit = normalizeRateLimitMaxEntries(maxEntries);
  prepareRateLimitCapacity(securityState, key, now, entryLimit, windowMs);
  const bucket = securityState.rateLimits.get(key) || { count: 0, resetAt: now + windowMs };
  if (bucket.resetAt <= now) {
    bucket.count = 0;
    bucket.resetAt = now + windowMs;
  }
  bucket.count += 1;
  securityState.rateLimits.delete(key);
  securityState.rateLimits.set(key, bucket);
  if (bucket.count > max) {
    throw securityError(429, '请求过于频繁，请稍后再试');
  }
}

/** 清理过期桶并对总桶数实施硬上限。 */
function prepareRateLimitCapacity(securityState, key, now, maxEntries, windowMs) {
  if (now >= Number(securityState.rateLimitCleanupAt || 0) || securityState.rateLimits.size >= maxEntries) {
    for (const [storedKey, bucket] of securityState.rateLimits) {
      if (Number(bucket.resetAt || 0) <= now) {
        securityState.rateLimits.delete(storedKey);
      }
    }
    securityState.rateLimitCleanupAt = now + Math.min(windowMs, DEFAULT_RATE_LIMIT_CLEANUP_INTERVAL_MS);
  }
  if (securityState.rateLimits.has(key)) {
    return;
  }
  if (securityState.rateLimits.size >= maxEntries) {
    throw securityError(429, '请求过于频繁，请稍后再试');
  }
}

/** 将无效容量配置回退到受控默认值。 */
function normalizeRateLimitMaxEntries(value) {
  const parsed = Math.floor(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_RATE_LIMIT_MAX_ENTRIES;
}

/** 仅在直连地址属于可信代理时解析转发链。 */
export function clientIp(request, serverOptions = {}) {
  const directIp = normalizeIpAddress(request.socket?.remoteAddress);
  if (!directIp || !(serverOptions.trustedProxyIps instanceof Set) || !serverOptions.trustedProxyIps.has(directIp)) {
    return directIp || 'unknown';
  }
  const forwardedChain = headerValue(request, 'x-forwarded-for')
    .split(',')
    .map(normalizeIpAddress)
    .filter(Boolean);
  for (let index = forwardedChain.length - 1; index >= 0; index -= 1) {
    const candidate = forwardedChain[index];
    if (!serverOptions.trustedProxyIps.has(candidate)) {
      return candidate;
    }
  }
  return forwardedChain[0] || directIp;
}

/** 归一化 IPv4、IPv6 和 IPv4 映射地址。 */
export function normalizeIpAddress(value) {
  let address = String(value || '').trim().replace(/^\[|\]$/g, '');
  if (address.startsWith('::ffff:') && isIP(address.slice(7)) === 4) {
    address = address.slice(7);
  }
  const zoneIndex = address.indexOf('%');
  if (zoneIndex >= 0) {
    address = address.slice(0, zoneIndex);
  }
  return isIP(address) ? address.toLowerCase() : '';
}

/** 将配置中的可信代理地址解析为精确匹配集合。 */
export function parseTrustedProxyIps(value) {
  const items = Array.isArray(value) ? value : String(value || '').split(',');
  return new Set(items.map(normalizeIpAddress).filter(Boolean));
}

/** 读取 Node 请求中的单值头部。 */
function headerValue(request, name) {
  const value = request.headers[name.toLowerCase()];
  if (Array.isArray(value)) {
    return value[0] || '';
  }
  return value || '';
}

/** 构造可安全暴露给客户端的安全策略错误。 */
function securityError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.expose = true;
  return error;
}

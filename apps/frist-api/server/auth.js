import { randomBytes } from 'node:crypto';
import {
  createId, hashId, hashAdminClaimCode, parseAdminClaimCodes, generateVerificationCode,
  maskKey, headerValue, clientIp, parseCookies, publicError,
  SESSION_COOKIE, PRIMARY_SOURCE_TYPE,
} from './shared.js';

export function createSecurityState() {
  return { captchas: new Map(), rateLimits: new Map() };
}

export function createCaptchaChallenge(securityState, serverOptions) {
  if (!serverOptions.requireCaptcha) {
    return { required: false, id: '', question: '' };
  }
  cleanupCaptchas(securityState);
  const challenge = buildRegistrationCaptcha();
  const id = createId('cap');
  securityState.captchas.set(id, {
    answer: challenge.answer,
    attemptsLeft: Number(serverOptions.captchaMaxAttempts || 3),
    expiresAt: Date.now() + Number(serverOptions.captchaTtlMs || 600_000),
  });
  return { required: true, id, question: challenge.question };
}

export function requireCaptchaIfEnabled(securityState, body, serverOptions) {
  if (!serverOptions.requireCaptcha) return;
  cleanupCaptchas(securityState);
  const id = String(body.captchaId || '').trim();
  const answer = String(body.captchaAnswer || '').trim();
  const challenge = securityState.captchas.get(id);
  if (!challenge || challenge.expiresAt < Date.now()) {
    throw publicError(400, '验证码已过期，请刷新后重试');
  }
  const normalizedAnswer = normalizeCaptchaAnswer(answer);
  const expected = normalizeCaptchaAnswer(challenge.answer);
  if (normalizedAnswer !== expected) {
    challenge.attemptsLeft = Math.max(0, Number(challenge.attemptsLeft || 1) - 1);
    if (challenge.attemptsLeft <= 0) {
      securityState.captchas.delete(id);
      throw publicError(400, '验证码不正确，请刷新后重试');
    }
    throw publicError(400, '验证码不正确');
  }
  securityState.captchas.delete(id);
}

export function cleanupCaptchas(securityState) {
  const now = Date.now();
  for (const [id, challenge] of securityState.captchas) {
    if (challenge.expiresAt < now) securityState.captchas.delete(id);
  }
}

function buildRegistrationCaptcha() {
  const type = randomInt(4);
  if (type === 0) {
    const left = 18 + randomInt(73);
    const right = 11 + randomInt(58);
    const subtract = 3 + randomInt(17);
    return { question: `${left} + ${right} - ${subtract} = ?`, answer: String(left + right - subtract) };
  }
  if (type === 1) {
    const code = randomCaptchaCode(5);
    const firstIndex = randomInt(code.length);
    let secondIndex = randomInt(code.length);
    while (secondIndex === firstIndex) secondIndex = randomInt(code.length);
    const indexes = [firstIndex, secondIndex].sort((a, b) => a - b);
    return {
      question: `验证码 ${code}，输入第 ${indexes[0] + 1} 和第 ${indexes[1] + 1} 位字符`,
      answer: `${code[indexes[0]]}${code[indexes[1]]}`,
    };
  }
  if (type === 2) {
    const code = randomCaptchaCode(4);
    return { question: `把 ${code} 倒序输入`, answer: code.split('').reverse().join('') };
  }
  const code = randomCaptchaCode(6);
  const digits = code.replace(/\D/g, '');
  if (digits.length >= 2) {
    return { question: `验证码 ${code}，只输入其中的数字`, answer: digits };
  }
  return { question: `验证码 ${code}，输入最后 3 位`, answer: code.slice(-3) };
}

function normalizeCaptchaAnswer(value) {
  return String(value || '').trim().replace(/\s+/g, '').toUpperCase();
}

function randomCaptchaCode(length) {
  const alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let index = 0; index < length; index += 1) code += alphabet[randomInt(alphabet.length)];
  return code;
}

function randomInt(max) {
  return randomBytes(1)[0] % Math.max(1, Number(max) || 1);
}

export function assertAuthRateLimit(securityState, request, serverOptions) {
  const max = Number(serverOptions.authRateLimitMax || 20);
  const windowMs = Number(serverOptions.authRateLimitWindowMs || 60_000);
  if (!Number.isFinite(max) || max <= 0 || !Number.isFinite(windowMs) || windowMs <= 0) return;
  const key = `auth:${clientIp(request)}`;
  const now = Date.now();
  const bucket = securityState.rateLimits.get(key) || { count: 0, resetAt: now + windowMs };
  if (bucket.resetAt <= now) { bucket.count = 0; bucket.resetAt = now + windowMs; }
  bucket.count += 1;
  securityState.rateLimits.set(key, bucket);
  if (bucket.count > max) {
    throw publicError(429, '请求过于频繁，请稍后再试');
  }
}

export function findSession(data, request) {
  const token = parseCookies(request.headers.cookie || '')[SESSION_COOKIE];
  const userId = token ? data.sessions[token] : '';
  const user = data.users.find((item) => item.id === userId);
  return { token, user };
}

export function requireSession(data, request) {
  const session = findSession(data, request);
  if (!session.user) throw publicError(401, '请先登录');
  return session;
}

export function requireUserKey(data, request) {
  const authorization = request.headers.authorization || '';
  const xApiKey = request.headers['x-api-key'] || request.headers['anthropic-auth-token'] || '';
  const secret = authorization.match(/^Bearer\s+(.+)$/i)?.[1] || String(xApiKey || '').trim();
  const key = data.userKeys.find((item) => item.secret === secret);
  if (!key || !key.enabled) throw publicError(401, 'API Key 不可用');
  return key;
}

export function requireAdmin(data, request, serverOptions) {
  const token = request.headers['x-admin-token'];
  if (token && token === serverOptions.adminToken) return;
  const { user } = findSession(data, request);
  if (user?.isAdmin) return;
  throw publicError(401, '管理员身份无效');
}

export function buildGatewayAffinityKey(request, body, userKey, model) {
  const explicitSessionId = [
    headerValue(request, 'x-frist-session-id'), headerValue(request, 'x-conversation-id'),
    body?.metadata?.frist_session_id, body?.metadata?.conversation_id,
    body?.metadata?.session_id, body?.conversation_id, body?.session_id, body?.user,
  ].map((value) => String(value || '').trim()).find(Boolean);
  const sessionId = explicitSessionId || 'default';
  return `${userKey.id}:${model}:${hashId(sessionId)}`;
}

export function orderGatewayCandidates(data, candidates, sessionKey) {
  const affinity = data.routeAffinities?.[sessionKey];
  if (!affinity?.credentialId) return candidates;
  const stickyCredential = candidates.find((credential) => credential.id === affinity.credentialId);
  if (!stickyCredential) { delete data.routeAffinities[sessionKey]; return candidates; }
  return [stickyCredential, ...candidates.filter((credential) => credential.id !== stickyCredential.id)];
}

export function rememberRouteAffinity(data, sessionKey, affinity) {
  if (!sessionKey) return;
  data.routeAffinities[sessionKey] = affinity;
}

export function clearRouteAffinity(data, sessionKey, credentialId) {
  const affinity = data.routeAffinities?.[sessionKey];
  if (affinity?.credentialId === credentialId) delete data.routeAffinities[sessionKey];
}

export function claimAdminIdentity(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = String(body.code || '').trim();
  const codeHash = hashAdminClaimCode(code);
  const allowedHashes = serverOptions.adminClaimCodeHashes || [];
  if (!code || allowedHashes.length === 0 || !allowedHashes.includes(codeHash)) {
    throw publicError(403, '身份码无效');
  }
  if (data.usedAdminClaimCodeHashes.includes(codeHash)) {
    throw publicError(409, '身份码已失效');
  }
  const now = new Date().toISOString();
  user.isAdmin = true;
  user.updatedAt = now;
  data.usedAdminClaimCodeHashes.push(codeHash);
  data.events.push({ type: 'admin_claimed', userId: user.id, at: now });
  return { user: sanitizeUser(user), adminUrl: '/admin.html', message: '管理员身份已激活' };
}

import { sanitizeUser } from './shared.js';

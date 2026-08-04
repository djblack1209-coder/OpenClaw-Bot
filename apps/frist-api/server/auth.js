import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import {
  createId, hashId, headerValue, isEncryptedRuntimeSecret, parseCookies, publicError,
  SESSION_COOKIE,
} from './shared.js';

export { assertAuthRateLimit, createSecurityState } from './security.js';

export const DEFAULT_SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const CSRF_COOKIE = 'frist_csrf';

/** 将高熵会话令牌变成不可逆存储键，备份泄露时不能直接复用。 */
export function runtimeTokenKey(value) {
  return `sha256:${createHash('sha256').update(String(value || '')).digest('hex')}`;
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

export function issueCustomerSession(data, user, serverOptions) {
  const sessionToken = createId('sess');
  const csrfToken = createId('csrf');
  const storageKey = runtimeTokenKey(sessionToken);
  const issuedAt = new Date();
  const ttlMs = Number(serverOptions.sessionTtlMs || DEFAULT_SESSION_TTL_MS);
  data.sessions[storageKey] = {
    userId: user.id,
    issuedAt: issuedAt.toISOString(),
    expiresAt: new Date(issuedAt.getTime() + ttlMs).toISOString(),
  };
  data.sessionCsrfTokens[storageKey] = csrfToken;
  return { sessionToken, csrfToken };
}

export function revokeCustomerSessions(data, userId) {
  for (const [token, session] of Object.entries(data.sessions || {})) {
    const sessionUserId = typeof session === 'string' ? session : session?.userId;
    if (sessionUserId === userId) {
      delete data.sessions[token];
      delete data.sessionCsrfTokens[token];
    }
  }
}

export function findSession(data, request) {
  const rawToken = parseCookies(request.headers.cookie || '')[SESSION_COOKIE];
  const token = rawToken ? runtimeTokenKey(rawToken) : '';
  const session = token ? data.sessions[token] : null;
  // 旧版明文 userId 会话没有生命周期信息，升级后安全退出并要求重新登录。
  const userId = session && typeof session === 'object' ? String(session.userId || '') : '';
  const expiresAt = Date.parse(session?.expiresAt || '');
  if (!userId || !Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    return { token, user: undefined, session: null };
  }
  const user = data.users.find((item) => item.id === userId);
  return { token, user, session };
}

export function requireSession(data, request) {
  const session = findSession(data, request);
  if (!session.user) throw publicError(401, '请先登录');
  return session;
}

export function requireCsrfIfEnabled(data, request, serverOptions, options = {}) {
  if (!serverOptions.requireCsrf || request.method === 'GET' || request.method === 'HEAD' || request.method === 'OPTIONS') {
    return;
  }
  if (options.allowAdminToken && request.headers['x-admin-token']) {
    return;
  }
  const { token, user } = findSession(data, request);
  if (!user || !token) {
    throw publicError(401, '请先登录');
  }
  const expected = String(data.sessionCsrfTokens?.[token] || parseCookies(request.headers.cookie || '')[CSRF_COOKIE] || '');
  const actual = String(request.headers['x-csrf-token'] || '').trim();
  if (!expected || !actual || !safeEqual(expected, actual)) {
    throw publicError(403, '页面安全校验失败，请刷新后重试');
  }
}

export function sessionCookies(sessionToken, csrfToken, request, serverOptions) {
  return [
    sessionCookie(sessionToken, request, serverOptions),
    csrfCookie(csrfToken, request, serverOptions),
  ];
}

export function expiredSessionCookies(request, serverOptions) {
  const secure = shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '';
  return [
    [`${SESSION_COOKIE}=`, 'Path=/', 'HttpOnly', 'SameSite=Lax', 'Max-Age=0', secure].filter(Boolean).join('; '),
    [`${CSRF_COOKIE}=`, 'Path=/', 'SameSite=Lax', 'Max-Age=0', secure].filter(Boolean).join('; '),
  ];
}

export function shouldUseSecureCookie(request, serverOptions) {
  const forwardedProto = String(request.headers['x-forwarded-proto'] || '').split(',')[0].trim().toLowerCase();
  return forwardedProto === 'https' || isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl);
}

/** 校验调用方 API Key，并拒绝无法解密的运行时占位值。 */
export function requireUserKey(data, request) {
  const authorization = request.headers.authorization || '';
  const xApiKey = request.headers['x-api-key'] || request.headers['anthropic-auth-token'] || '';
  const secret = authorization.match(/^Bearer\s+(.+)$/i)?.[1] || String(xApiKey || '').trim();
  const key = secret
    ? data.userKeys.find((item) => !isEncryptedRuntimeSecret(item.secret) && safeEqual(item.secret, secret))
    : undefined;
  if (!key || !key.enabled) throw publicError(401, 'API Key 不可用');
  return key;
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

function sessionCookie(sessionToken, request, serverOptions) {
  const maxAge = Math.max(300, Math.floor(Number(serverOptions.sessionTtlMs || DEFAULT_SESSION_TTL_MS) / 1000));
  return [
    `${SESSION_COOKIE}=${sessionToken}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Max-Age=${maxAge}`,
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function csrfCookie(csrfToken, request, serverOptions) {
  const maxAge = Math.max(300, Math.floor(Number(serverOptions.sessionTtlMs || DEFAULT_SESSION_TTL_MS) / 1000));
  return [
    `${CSRF_COOKIE}=${csrfToken}`,
    'Path=/',
    'SameSite=Lax',
    `Max-Age=${maxAge}`,
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function isPublicHttpsGateway(value) {
  const gateway = String(value || '').trim();
  if (!/^https:\/\//i.test(gateway)) {
    return false;
  }
  return !/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|example\.(com|org|net))/i.test(gateway);
}

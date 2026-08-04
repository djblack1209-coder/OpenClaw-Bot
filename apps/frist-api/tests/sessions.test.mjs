import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';

import {
  expiredSessionCookies,
  findSession,
  issueCustomerSession,
  requireCsrfIfEnabled,
  requireSession,
  revokeCustomerSessions,
  sessionCookies,
} from '../server/auth.js';

function runtimeData() {
  return {
    users: [{ id: 'user-1', email: 'owner@example.com' }],
    sessions: {},
    sessionCsrfTokens: {},
  };
}

function requestWithCookies(sessionToken, csrfToken = '', headers = {}) {
  const cookies = [`frist_session=${sessionToken}`];
  if (csrfToken) cookies.push(`frist_csrf=${csrfToken}`);
  return {
    method: 'POST',
    headers: {
      cookie: cookies.join('; '),
      ...headers,
    },
  };
}

describe('Frist 客户会话边界', () => {
  it('签发可校验的限时会话，并能一次撤销用户全部会话', () => {
    const data = runtimeData();
    const options = { sessionTtlMs: 60_000 };
    const first = issueCustomerSession(data, data.users[0], options);
    const second = issueCustomerSession(data, data.users[0], options);

    assert.match(first.sessionToken, /^sess-/);
    assert.match(first.csrfToken, /^csrf-/);
    assert.notEqual(first.sessionToken, second.sessionToken);
    assert.equal(Object.hasOwn(data.sessions, first.sessionToken), false);
    assert.equal(Object.keys(data.sessions).every((key) => /^sha256:[a-f0-9]{64}$/.test(key)), true);
    assert.equal(
      findSession(data, requestWithCookies(first.sessionToken)).user.id,
      'user-1',
    );

    revokeCustomerSessions(data, 'user-1');

    assert.deepEqual(data.sessions, {});
    assert.deepEqual(data.sessionCsrfTokens, {});
    assert.throws(
      () => requireSession(data, requestWithCookies(first.sessionToken)),
      (error) => error.statusCode === 401 && error.expose === true,
    );
  });

  it('旧版和过期会话均失败关闭', () => {
    const data = runtimeData();
    data.sessions.legacy = 'user-1';
    data.sessions.expired = {
      userId: 'user-1',
      issuedAt: '2020-01-01T00:00:00.000Z',
      expiresAt: '2020-01-01T00:01:00.000Z',
    };

    assert.equal(findSession(data, requestWithCookies('legacy')).user, undefined);
    assert.equal(findSession(data, requestWithCookies('expired')).user, undefined);
  });

  it('写请求要求会话绑定的 CSRF，管理员令牌例外保持原合同', () => {
    const data = runtimeData();
    const issued = issueCustomerSession(data, data.users[0], { sessionTtlMs: 60_000 });
    const validRequest = requestWithCookies(issued.sessionToken, issued.csrfToken, {
      'x-csrf-token': issued.csrfToken,
    });

    assert.doesNotThrow(() => requireCsrfIfEnabled(data, validRequest, { requireCsrf: true }));
    assert.throws(
      () => requireCsrfIfEnabled(data, requestWithCookies(issued.sessionToken), { requireCsrf: true }),
      (error) => error.statusCode === 403 && error.expose === true,
    );
    assert.doesNotThrow(() =>
      requireCsrfIfEnabled(
        data,
        { method: 'POST', headers: { 'x-admin-token': 'admin' } },
        { requireCsrf: true },
        { allowAdminToken: true },
      ),
    );
  });

  it('Cookie 属性在 HTTPS 下保持 Secure，退出时同时清除会话和 CSRF', () => {
    const request = { headers: { 'x-forwarded-proto': 'https' } };
    const options = { sessionTtlMs: 60_000, publicGatewayBaseUrl: 'https://api.example.invalid' };
    const active = sessionCookies('sess-token', 'csrf-token', request, options);
    const expired = expiredSessionCookies(request, options);

    assert.equal(active.length, 2);
    assert.match(active[0], /^frist_session=sess-token;/);
    assert.match(active[0], /HttpOnly/);
    assert.match(active[0], /Secure/);
    assert.match(active[1], /^frist_csrf=csrf-token;/);
    assert.doesNotMatch(active[1], /HttpOnly/);
    assert.equal(expired.length, 2);
    assert.ok(expired.every((cookie) => cookie.includes('Max-Age=0') && cookie.includes('Secure')));
  });

  it('入口文件只导入会话域，不再保留重复实现', async () => {
    const source = await readFile(new URL('../server/server.js', import.meta.url), 'utf8');

    assert.match(source, /from '\.\/auth\.js';/);
    for (const name of [
      'issueCustomerSession',
      'revokeCustomerSessions',
      'findSession',
      'requireSession',
      'requireCsrfIfEnabled',
      'sessionCookies',
      'expiredSessionCookies',
      'createCaptchaChallenge',
      'requireCaptchaIfEnabled',
      'orderGatewayCandidates',
      'clearRouteAffinity',
      'requireUserKey',
    ]) {
      assert.doesNotMatch(source, new RegExp(`function ${name}\\b`));
    }
  });
});

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { clientIp, requestOrigin } from '../server/shared.js';

const serverSource = readFileSync(new URL('../server/server.js', import.meta.url), 'utf8');
const newApiBridgeSource = readFileSync(new URL('../server/newApiBridge.js', import.meta.url), 'utf8');
const sharedSource = readFileSync(new URL('../server/shared.js', import.meta.url), 'utf8');

describe('CC中转 server security source boundaries', () => {
  it('uses constant-time helpers for administrator and API secret comparisons', () => {
    assert.doesNotMatch(serverSource, /token\s*&&\s*token\s*===\s*serverOptions\.adminToken/);
    assert.doesNotMatch(serverSource, /code\s*!==\s*serverOptions\.adminPageCode/);
    assert.doesNotMatch(serverSource, /item\.secret\s*===\s*secret/);
    assert.doesNotMatch(newApiBridgeSource, /return\s+key\s*===\s*secret/);
  });

  it('removes unreferenced legacy server implementations', () => {
    assert.equal(existsSync(new URL('../server/store.js', import.meta.url)), false);
    assert.equal(existsSync(new URL('../server/auth.js', import.meta.url)), false);
    assert.equal(existsSync(new URL('../server/catalog.js', import.meta.url)), false);
  });

  it('keeps the shared server module limited to cross-module helpers', () => {
    assert.doesNotMatch(sharedSource, /DEFAULT_RECHARGE_PLANS/);
    assert.doesNotMatch(sharedSource, /function writeJson/);
    assert.doesNotMatch(sharedSource, /function gatewayUnavailableResponse/);
    assert.match(sharedSource, /export function requestOrigin/);
    assert.match(sharedSource, /export function safeEqual/);
  });

  it('keeps wildcard public API CORS separate from browser cookie credentials', () => {
    assert.match(serverSource, /'access-control-allow-origin': '\*'/);
    assert.match(newApiBridgeSource, /'access-control-allow-origin': '\*'/);
    assert.doesNotMatch(serverSource, /access-control-allow-credentials[^\n]*true/i);
    assert.doesNotMatch(newApiBridgeSource, /access-control-allow-credentials[^\n]*true/i);
    assert.match(serverSource, /function sessionCookie[\s\S]*HttpOnly[\s\S]*SameSite=Lax/);
    assert.match(serverSource, /function csrfCookie[\s\S]*SameSite=Lax/);
  });

  it('only trusts forwarded origin and client IP headers from a private reverse proxy', () => {
    const directRequest = {
      headers: {
        host: 'direct.example.com',
        'x-forwarded-host': 'attacker.example.com',
        'x-forwarded-proto': 'https',
        'x-forwarded-for': '198.51.100.20',
      },
      socket: { remoteAddress: '203.0.113.8' },
    };
    assert.equal(requestOrigin(directRequest), 'http://direct.example.com');
    assert.equal(clientIp(directRequest), '203.0.113.8');

    const proxiedRequest = {
      headers: {
        host: '127.0.0.1:3000',
        'x-forwarded-host': 'gateway.example.com',
        'x-forwarded-proto': 'https',
        'x-forwarded-for': '198.51.100.21, 172.18.0.2',
      },
      socket: { remoteAddress: '172.18.0.3' },
    };
    assert.equal(requestOrigin(proxiedRequest), 'https://gateway.example.com');
    assert.equal(clientIp(proxiedRequest), '198.51.100.21');
  });
});

/* Actual Portfolio events + API wrappers, with synthetic HTTP responses only. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { Portfolio } from '../apps/openclaw-manager-src/src/components/Portfolio/index.tsx';
import { LanguageProvider } from '../apps/openclaw-manager-src/src/i18n/index.tsx';
import { api } from '../apps/openclaw-manager-src/src/lib/api.ts';
import { MANUAL_SELL_REFERENCE_KEY } from '../apps/openclaw-manager-src/src/lib/trading-sell.ts';
import '../apps/openclaw-manager-src/src/styles/globals.css';

const nativeFetch = window.fetch.bind(window);
const nativeSet = Storage.prototype.setItem;
const results = [];
let root, mode, prepares, submits, queries, current, heldPrepare, heldSubmit, storageFailure;
const challenge = 'SYNTHETIC_CONFIRMATION_CHALLENGE_792813';
api.omegaInvestmentTeam = async () => ({ team: [] });
Storage.prototype.setItem = function (key, value) {
  if (storageFailure && key === MANUAL_SELL_REFERENCE_KEY) throw Error('storage failure');
  return nativeSet.call(this, key, value);
};
const pause = (ms = 180) => new Promise(resolve => setTimeout(resolve, ms));
const response = (payload, status = 200) => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
window.fetch = async (url, init = {}) => {
  const path = new URL(url, location.href).pathname;
  if (path.endsWith('/trading/portfolio-summary')) return response({ total_value: 10000, total_cost: 9000, total_pnl: 1000,
    total_pnl_pct: 10, day_change: 10, day_change_pct: 0.1, position_count: 1, connected: true,
    positions: [{ symbol: 'AAPL', name: 'Fixture stock', quantity: 10, avg_price: 100, current_price: 110, market_value: 1100, pnl: 100, pnl_pct: 10, weight: 100 }] });
  if (path.endsWith('/status')) return response({ ibkr_connected: true });
  if (path.endsWith('/trading/sell/prepare')) {
    prepares++;
    if (mode === 'prepare-failure') return response({ detail: 'unavailable' }, 503);
    const order = JSON.parse(init.body);
    current = { request_id: order.request_id, protocol: 'manual-sell-v1', state: 'prepared',
      expires_at: Date.now() / 1000 + (mode === 'expiry' ? 0.6 : 120), challenge,
      success: false, requires_reconciliation: false,
      summary: { symbol: order.symbol, quantity: String(order.quantity), order_type: 'MKT', limit_price: null,
        account: 'DU1234567', environment: 'paper', broker: 'ibkr', con_id: 123, currency: 'USD',
        broker_protocol: 'tws-api', server_version: 190 } };
    if (mode === 'held-prepare') await new Promise(resolve => { heldPrepare = resolve; });
    return response(current);
  }
  if (path.endsWith('/trading/sell')) {
    submits++;
    const order = JSON.parse(init.body);
    assert(order.confirmed === true && order.challenge === challenge && order.request_id === current.request_id, 'Server confirmation missing');
    assert(!('account' in order) && order.quantity === 10, 'Incorrect confirmation payload');
    assert(localStorage.getItem(MANUAL_SELL_REFERENCE_KEY) === current.request_id, 'Reference not persisted before POST');
    current = { ...current, challenge: undefined, state: 'unknown', requires_reconciliation: true };
    if (mode === 'timeout') throw new DOMException('Synthetic timeout', 'AbortError');
    if (mode === 'held-submit') await new Promise(resolve => { heldSubmit = resolve; });
    current = { ...current, state: mode === 'partial' ? 'partially_filled' : 'filled', success: true, requires_reconciliation: false };
    return response(current);
  }
  if (path.includes('/trading/sell/requests/')) { queries++; return response({ ...current, challenge: undefined }); }
  throw Error('Unexpected fixture fetch: ' + path);
};
function assert(value, message) { if (!value) throw Error(message); }
function button(text) {
  const item = [...document.querySelectorAll('#app button')].find(el => el.textContent.trim() === text);
  assert(item, 'Missing button ' + text); return item;
}
function confirmButton() { return [...document.querySelectorAll('[role=dialog] button')].find(el => el.textContent.includes('卖出')); }
async function mount(next, preserve = false) {
  if (root) flushSync(() => root.unmount());
  if (!preserve) { localStorage.clear(); prepares = submits = queries = 0; current = null; }
  mode = next; storageFailure = false; heldPrepare = heldSubmit = null;
  root = createRoot(document.getElementById('app'));
  flushSync(() => root.render(React.createElement(LanguageProvider, null, React.createElement(Portfolio))));
  await pause(400);
}
async function prepareSell() { button('卖出').click(); await pause(); }
async function confirmSell() { const item = confirmButton(); assert(item, 'Missing confirmation'); item.click(); await pause(); }
async function check(name, run) {
  try { await run(); results.push({ name, passed: true }); }
  catch (error) { results.push({ name, passed: false, error: String(error.message) }); }
  document.getElementById('results').textContent = JSON.stringify({ running: true, results }, null, 2);
}
await check('server account, environment, quantity and expiry precede submission', async () => {
  await mount('success'); await prepareSell();
  const dialog = document.querySelector('[role=dialog]');
  assert(dialog && dialog.textContent.includes('DU1234567') && dialog.textContent.includes('模拟账户')
    && dialog.textContent.includes('10') && dialog.textContent.includes('确认有效至'), 'Incomplete server summary');
  assert(prepares === 1 && submits === 0, 'Prepare submitted an order');
  const submit = confirmButton(); submit.click(); submit.click(); await pause();
  assert(submits === 1 && document.querySelector('[data-testid=manual-sell-status]').textContent.includes('全部成交'), 'Duplicate submit or missing fill state');
  assert(!localStorage.getItem(MANUAL_SELL_REFERENCE_KEY), 'Terminal reference retained');
});
await check('preparation failure cannot open a confirmation or submit', async () => {
  await mount('prepare-failure'); await prepareSell();
  assert(prepares === 1 && submits === 0 && !document.querySelector('[role=dialog]'), 'Failed preparation allowed confirmation');
});
await check('expired confirmation closes without submission', async () => {
  await mount('expiry'); await prepareSell(); await pause(850);
  assert(!document.querySelector('[role=dialog]') && submits === 0, 'Expired confirmation remained actionable');
});
await check('reference persistence failure stops before POST', async () => {
  await mount('success'); await prepareSell(); storageFailure = true; await confirmSell();
  assert(submits === 0, 'Order posted without recoverable reference');
});
await check('timeout preserves only request ID and reload only queries', async () => {
  await mount('timeout'); await prepareSell(); await confirmSell();
  const id = current.request_id;
  assert(submits === 1 && localStorage.getItem(MANUAL_SELL_REFERENCE_KEY) === id, 'Timeout lost reference');
  assert(button('卖出').disabled, 'Uncertain order allows another sell');
  assert(!JSON.stringify({ ...localStorage }).includes(challenge) && !JSON.stringify({ ...localStorage }).includes('DU1234567'), 'Sensitive confirmation persisted');
  await mount('timeout', true);
  assert(submits === 1 && queries > 0 && button('卖出').disabled, 'Reload resubmitted or released unknown order');
  current = { ...current, state: 'filled', success: true, requires_reconciliation: false };
  button('查询原订单').click(); await pause();
  assert(!localStorage.getItem(MANUAL_SELL_REFERENCE_KEY) && !button('卖出').disabled, 'Verified terminal did not release UI');
});
await check('partial fill stays pending and does not claim full fill', async () => {
  await mount('partial'); await prepareSell(); await confirmSell();
  const panel = document.querySelector('[data-testid=manual-sell-status]');
  assert(panel.textContent.includes('部分成交') && button('卖出').disabled && localStorage.getItem(MANUAL_SELL_REFERENCE_KEY), 'Partial fill released pending request');
});
await check('late preparation after unmount cannot open or submit an order', async () => {
  await mount('held-prepare'); button('卖出').click(); await pause();
  assert(heldPrepare && prepares === 1, 'Preparation not held');
  flushSync(() => root.unmount()); root = null; heldPrepare(); await pause();
  assert(!document.querySelector('[role=dialog]') && submits === 0, 'Late preparation opened confirmation');
});
await check('duplicate clicks during an outstanding submit stay one request', async () => {
  await mount('held-submit'); await prepareSell(); const item = confirmButton(); item.click(); item.click(); await pause();
  assert(submits === 1 && heldSubmit && item.disabled, 'Outstanding submit duplicated');
  heldSubmit(); await pause(); assert(submits === 1, 'Late completion replayed submit');
});
const result = { running: false, passed: results.filter(item => item.passed).length, failed: results.filter(item => !item.passed).length, results };
document.getElementById('results').textContent = JSON.stringify(result, null, 2);
await nativeFetch('/__manual_sell_result', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result) });

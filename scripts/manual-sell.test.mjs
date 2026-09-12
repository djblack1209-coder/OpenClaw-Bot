import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(new URL('../apps/openclaw-manager-src/package.json', import.meta.url));
const ts = require('typescript');
const source = readFileSync(new URL('../apps/openclaw-manager-src/src/lib/trading-sell.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports });
const id = 'ee7f3e61-b1b9-4bc8-8940-df9299871a23';
function prepared() {
  return { request_id: id, protocol: 'manual-sell-v1', state: 'prepared', expires_at: 200,
    challenge: 'synthetic-confirmation-challenge-1234', success: false, requires_reconciliation: false,
    summary: { symbol: 'AAPL', quantity: '10', order_type: 'MKT', limit_price: null, account: 'DU1234567',
      environment: 'paper', broker: 'ibkr', con_id: 123, currency: 'USD', broker_protocol: 'tws-api', server_version: 190 } };
}
test('confirmation is copied from server summary with no account or internal fields', () => {
  const value = exports.createManualSellConfirmation(prepared(), 100_000);
  assert.deepEqual(JSON.parse(JSON.stringify(value)), { request_id: id, protocol: 'manual-sell-v1',
    challenge: prepared().challenge, confirmed: true, symbol: 'AAPL', quantity: 10, order_type: 'MKT', limit_price: null });
});
for (const change of [{ state: 'filled' }, { challenge: undefined }, { expires_at: 100 },
  { protocol: 'old' }, { success: true }]) test('invalid confirmation cannot submit ' + Object.keys(change)[0], () => {
  assert.throws(() => exports.createManualSellConfirmation({ ...prepared(), ...change }, 100_000));
});
test('status cannot be substituted from a different request', () => {
  assert.throws(() => exports.parseManualSellStatus(prepared(), '7d25859d-79cd-4e4f-9883-fad58b6eab73'));
});
for (const state of ['claimed', 'dispatched', 'unknown', 'submitted', 'partially_filled']) {
  test('pending state cannot release the saved reference: ' + state, () => assert.equal(exports.isManualSellTerminal(state), false));
}
test('persistent storage contains only the request UUID and failed writes cannot pass', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  exports.saveManualSellReference(storage, id);
  assert.equal(values.size, 1);
  assert.deepEqual([...values.values()], [id]);
  assert.equal(exports.readManualSellReference(storage), id);
  assert.throws(() => exports.saveManualSellReference({ ...storage, setItem() { throw Error('storage failure'); } }, id));
  assert.throws(() => exports.saveManualSellReference({ getItem() { return null; }, setItem() {} }, id));
  exports.clearManualSellReference(storage, id);
  assert.equal(values.size, 0);
});

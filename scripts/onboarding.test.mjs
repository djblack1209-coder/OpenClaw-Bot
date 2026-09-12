import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(new URL('../apps/openclaw-manager-src/package.json', import.meta.url));
const ts = require('typescript');
function load(relative, globals = {}) {
  const source = readFileSync(new URL('../apps/openclaw-manager-src/src/' + relative, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, URL, Set, Error, require: (name) => name.includes('qa-tracker') ? { trackClick() {}, trackPageLoad() {} } : require(name), ...globals });
  return exports;
}
function storage(seed = {}) {
  const values = new Map(Object.entries(seed));
  return { values, getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}
const STORE = 'openclaw-app-store';

for (const status of ['saved_unverified', 'skipped']) test(`persistent onboarding ${status} survives reload`, () => {
  const localStorage = storage();
  const first = load('stores/appStore.ts', { localStorage }).useAppStore;
  if (status === 'saved_unverified') first.getState().recordOnboardingSave(['trading']);
  first.getState().completeOnboarding(status, ['trading', 'synthetic-key-not-a-feature']);
  const second = load('stores/appStore.ts', { localStorage }).useAppStore;
  assert.equal(second.getState().onboardingComplete, true);
  assert.equal(second.getState().onboardingStatus, status);
  assert.deepEqual([...second.getState().onboardingFeatures], ['assistant', 'trading']);
  assert.equal(localStorage.values.size, 1);
  assert.ok(!localStorage.getItem(STORE).includes('synthetic-key-not-a-feature'));
});

test('failed storage write leaves memory and previous persistent value unchanged', () => {
  const localStorage = storage();
  const store = load('stores/appStore.ts', { localStorage }).useAppStore;
  store.getState().recordOnboardingSave(['assistant']);
  const before = localStorage.getItem(STORE);
  localStorage.setItem = () => { throw Error('synthetic storage failure'); };
  assert.throws(() => store.getState().completeOnboarding('saved_unverified', []));
  assert.equal(store.getState().onboardingComplete, false);
  assert.equal(localStorage.getItem(STORE), before);
});

test('failed persistence readback rolls back before changing memory', () => {
  const localStorage = storage();
  const store = load('stores/appStore.ts', { localStorage }).useAppStore;
  let calls = 0;
  const getItem = localStorage.getItem;
  localStorage.getItem = (key) => ++calls === 2 ? 'synthetic bad readback' : getItem(key);
  assert.throws(() => store.getState().completeOnboarding('skipped', []));
  assert.equal(store.getState().onboardingComplete, false);
  assert.equal(getItem(STORE), null);
});

for (const seed of [{ 'openclaw-onboarding-complete': 'true' }, { [STORE]: JSON.stringify({ state: { onboardingComplete: true, devMode: true }, version: 0 }) }]) {
  test('legacy completion never becomes verified or saved', () => {
    const localStorage = storage(seed);
    const state = load('stores/appStore.ts', { localStorage }).useAppStore.getState();
    assert.equal(state.onboardingComplete, true);
    assert.equal(state.onboardingStatus, 'legacy_unverified');
    assert.equal(localStorage.values.size, 1);
  });
}

test('unsaved setup cannot claim saved completion', () => {
  const localStorage = storage();
  const store = load('stores/appStore.ts', { localStorage }).useAppStore;
  assert.throws(() => store.getState().completeOnboarding('saved_unverified', []));
  assert.equal(localStorage.values.size, 0);
});

const { saveGatewaySetup } = load('lib/onboarding.ts');
const input = { providerName: 'fixture', modelId: 'fixture-model', baseUrl: 'https://fixture.invalid/v1', apiType: 'openai-completions', apiKey: 'synthetic-secret' };
function config(hasKey = true) {
  return { config_source: 'openclaw', primary_model: null, available_models: [], configured_providers: [{ name: input.providerName, base_url: input.baseUrl, has_api_key: hasKey, api_key_masked: '****', models: [{ id: input.modelId, name: 'Preserved name', api_type: input.apiType }] }] };
}
function fixture() {
  const calls = [];
  return { calls, api: { getAIConfig: async () => { calls.push('read'); return config(); }, saveProvider: async (...args) => { calls.push(args); return 'saved'; } } };
}

test('one provider save followed by identity and key-presence readback; no invented rates', async () => {
  const { calls, api } = fixture();
  assert.equal(await saveGatewaySetup(input, api, () => true), true);
  assert.equal(calls.length, 3);
  assert.equal(calls[0], 'read'); assert.equal(calls[2], 'read');
  const [name, url, key, type, models] = calls[1];
  assert.equal(name, input.providerName); assert.equal(url, input.baseUrl); assert.equal(key, input.apiKey); assert.equal(type, input.apiType);
  assert.equal(models[0].cost, null); assert.equal(models[0].name, 'Preserved name');
});

test('blank key remains null and cannot overwrite the existing secret', async () => {
  const { calls, api } = fixture();
  await saveGatewaySetup({ ...input, apiKey: '  ' }, api, () => true);
  assert.equal(calls[1][2], null);
});

for (const patch of [{ providerName: '' }, { modelId: '' }, { baseUrl: '' }, { apiKey: '****' }, { apiKey: '1234...6789' }, { baseUrl: 'https://user:secret@fixture.invalid/v1' }, { baseUrl: 'https://fixture.invalid/v1?key=synthetic' }]) {
  test(`invalid or sensitive-placeholder input blocks before IPC: ${Object.keys(patch)[0]}`, async () => {
    const { calls, api } = fixture();
    await assert.rejects(saveGatewaySetup({ ...input, ...patch }, api, () => true));
    assert.equal(calls.length, 0);
  });
}

for (const failure of ['initial-read', 'save', 'readback', 'identity', 'key-presence', 'agent-managed']) test(`configuration ${failure} is not success`, async () => {
  let reads = 0, saves = 0;
  const api = {
    getAIConfig: async () => {
      reads++;
      if (failure === 'initial-read' || (failure === 'readback' && reads === 2)) throw Error('synthetic-secret');
      const result = config(!(failure === 'key-presence' && reads === 2));
      if (failure === 'identity' && reads === 2) result.configured_providers[0].models = [];
      if (failure === 'agent-managed') result.config_source = 'agent';
      return result;
    },
    saveProvider: async () => { saves++; if (failure === 'save') throw Error('synthetic-secret'); return 'saved'; },
  };
  await assert.rejects(saveGatewaySetup(input, api, () => true), (error) => !String(error).includes('synthetic-secret'));
  if (['initial-read', 'agent-managed'].includes(failure)) assert.equal(saves, 0);
});

test('late save response after unmount is ignored without further IPC or completion', async () => {
  let current = true;
  const { calls, api } = fixture();
  api.saveProvider = async () => { current = false; return 'saved'; };
  assert.equal(await saveGatewaySetup(input, api, () => current), false);
  assert.deepEqual(calls, ['read']);
});

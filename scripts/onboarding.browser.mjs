/* Browser contract fixture. Serve a public-source copy using the C05 verifier.
   All IPC, storage failures and credentials below are synthetic. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { Onboarding } from '../apps/openclaw-manager-src/src/components/Onboarding/index.tsx';
import { LanguageProvider } from '../apps/openclaw-manager-src/src/i18n/index.tsx';
import { useAppStore } from '../apps/openclaw-manager-src/src/stores/appStore.ts';
import '../apps/openclaw-manager-src/src/styles/globals.css';

const baseline = new URLSearchParams(location.search).get('baseline') === '1';
const Component = baseline ? (await import(/* @vite-ignore */ '/legacy-onboarding.tsx')).Onboarding : Onboarding;
const secret = 'SYNTHETIC_ONBOARDING_SECRET_7391';
let root, mode, complete, saves, reads, saved, storageFail, releaseSave, releaseRead;
let argsSaved;
const results = [];
const consoleTexts = [];
const nativeSet = Storage.prototype.setItem;
Storage.prototype.setItem = function (key, value) {
  if (storageFail && key === 'openclaw-app-store') throw Error('synthetic storage rejection');
  return nativeSet.call(this, key, value);
};
for (const method of ['log', 'warn', 'error', 'info', 'debug']) {
  const original = console[method].bind(console);
  console[method] = (...args) => { consoleTexts.push(args.map((arg) => String(arg)).join(' ')); original(...args); };
}
const pause = (ms = 380) => new Promise((resolve) => setTimeout(resolve, ms));
function assert(value, message) { if (!value) throw Error(message); }
function config() {
  const providerName = argsSaved?.providerName || 'fixture';
  const model = argsSaved?.models?.[0] || { id: 'fixture-model', name: 'Fixture model', api: 'openai-completions' };
  return { config_source: mode === 'agent-managed' ? 'agent' : 'openclaw', primary_model: null, available_models: [], configured_providers: [{
    name: providerName, base_url: argsSaved?.baseUrl || 'https://fixture.invalid/v1', has_api_key: saved || mode === 'existing-key', api_key_masked: '****',
    models: mode === 'wrong-readback' && saved ? [] : [{ id: model.id, name: model.name, api_type: model.api, is_primary: false }],
  }] };
}
window.__TAURI_INTERNALS__ = { invoke: async (command, args) => {
  if (command === 'get_ai_config') {
    reads++;
    if (mode === 'read-failure' || (mode === 'readback-failure' && saved)) throw Error(secret);
    if (mode === 'late-initial-read' && reads === 1) await new Promise((resolve) => { releaseRead = resolve; });
    return config();
  }
  if (command === 'save_provider' || command === 'save_env_value') {
    saves++;
    if (mode === 'save-failure') throw Error(secret);
    if (mode === 'held-save') await new Promise((resolve) => { releaseSave = resolve; });
    if (command === 'save_provider') argsSaved = args;
    saved = true; return 'synthetic saved';
  }
  throw Error('Unexpected IPC command in fixture');
} };
function button(label) {
  const value = [...document.querySelectorAll('#app button')].find((element) => element.textContent.trim() === label);
  assert(value, 'Missing expected button: ' + label); return value;
}
async function click(label) { button(label).click(); await pause(); }
async function fill(id, value) {
  const input = document.getElementById(id);
  assert(input, 'Missing expected field');
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await pause(15);
}
async function mount(nextMode) {
  if (root) flushSync(() => root.unmount());
  storageFail = false; localStorage.clear();
  mode = nextMode; complete = 0; saves = 0; reads = 0; saved = false; argsSaved = null; releaseSave = null; releaseRead = null;
  useAppStore.setState({ onboardingComplete: false, onboardingStatus: 'incomplete', onboardingFeatures: ['assistant'] });
  root = createRoot(document.getElementById('app'));
  flushSync(() => root.render(React.createElement(LanguageProvider, null, React.createElement(Component, { onComplete: () => { complete++; } }))));
  await pause();
}
async function form() { await click('开始设置'); await click('下一步'); }
async function submit() { await fill('setup-apiKey', secret); await click('保存配置'); }
async function check(name, run) {
  try { await run(); results.push({ name, passed: true }); }
  catch (error) { results.push({ name, passed: false, error: String(error.message).replaceAll(secret, '[synthetic secret removed]') }); }
  document.getElementById('results').textContent = JSON.stringify({ baseline, running: true, results }, null, 2);
}

if (baseline) {
  await check('saving failure must keep actual legacy UI open', async () => {
    await mount('save-failure'); await form();
    const input = document.querySelector('#app input[type=password]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, secret);
    input.dispatchEvent(new Event('input', { bubbles: true })); await pause(20);
    await click('下一步'); await click('进入控制台');
    assert(saves > 0, 'Failure was not exercised');
    assert(complete === 0 && localStorage.getItem('openclaw-onboarding-complete') !== 'true', 'Save failed but completion callback/legacy flag still succeeded');
  });
} else {
  await check('save failure stays on editable form without completing', async () => {
    await mount('save-failure'); await form(); await submit();
    assert(complete === 0 && !useAppStore.getState().onboardingComplete, 'Failed save completed onboarding');
    assert(saves === 1 && document.querySelector('#app [role=alert]') && document.getElementById('setup-apiKey'), 'Failed-save UI is missing');
  });
  for (const failure of ['readback-failure', 'wrong-readback']) await check(failure + ' stays incomplete', async () => {
    await mount(failure); await form(); await submit();
    assert(complete === 0 && saves === 1 && useAppStore.getState().onboardingStatus === 'incomplete', 'Invalid readback completed setup');
    assert(document.querySelector('#app [role=alert]'), 'Readback failure is not shown');
  });
  await check('persistent failure remains open and can retry', async () => {
    await mount('success'); await form(); storageFail = true; await submit();
    assert(complete === 0 && !useAppStore.getState().onboardingComplete, 'Storage failure completed setup');
    assert(document.querySelector('#app [role=alert]'), 'Storage failure is not shown');
    storageFail = false; await click('保存配置');
    assert(document.querySelector('#app h2')?.textContent === '配置已保存', 'Retry did not show saved state');
    assert(complete === 0, 'Save navigated before entering the console');
    await click('进入控制台'); assert(complete === 1, 'Retry did not complete exactly once');
  });
  await check('completion page is saved-unverified and persisted without secrets', async () => {
    await mount('success'); await form(); await submit();
    assert(document.querySelector('#app h2')?.textContent === '配置已保存', 'Saved completion page missing');
    assert(document.querySelector('#app').textContent.includes('运行连接尚未验证'), 'Runtime verification overstated');
    assert(!useAppStore.getState().onboardingComplete && complete === 0, 'Console completed before explicit entry');
    const finish = button('进入控制台'); finish.click(); finish.click(); await pause();
    assert(complete === 1 && useAppStore.getState().onboardingStatus === 'saved_unverified', 'Duplicate finish or wrong persistent status');
    assert(!JSON.stringify({ ...localStorage }).includes(secret), 'Secret entered browser storage');
  });
  await check('skip discards the entered key and retains pending setup', async () => {
    await mount('success'); await form(); await fill('setup-apiKey', secret); await click('跳过');
    assert(saves === 0 && complete === 1 && useAppStore.getState().onboardingStatus === 'skipped', 'Skip saved a key or lost pending status');
    assert(!JSON.stringify({ ...localStorage }).includes(secret), 'Skipped secret entered browser storage');
  });
  await check('empty fields and mask placeholders cannot save', async () => {
    await mount('success'); await form(); await fill('setup-modelId', ''); await click('保存配置');
    assert(saves === 0 && complete === 0, 'Empty model was saved');
    await fill('setup-modelId', 'fixture-model'); await fill('setup-apiKey', '****'); await click('保存配置');
    assert(saves === 0 && complete === 0, 'Masked placeholder was saved');
  });
  await check('blank existing key is retained', async () => {
    await mount('existing-key'); await form(); await click('保存配置');
    assert(saves === 1 && argsSaved.apiKey === null, 'Blank input replaced the existing key');
    assert(document.querySelector('#app h2')?.textContent === '配置已保存', 'Existing provider could not be saved');
  });
  await check('saving blocks double submit, back and skip', async () => {
    await mount('held-save'); await form(); await fill('setup-apiKey', secret);
    const save = button('保存配置'); save.click(); save.click(); await pause(30);
    assert(saves === 1 && save.disabled && button('上一步').disabled && button('跳过').disabled, 'Concurrent controls can mutate saving flow');
    button('上一步').click(); assert(document.getElementById('setup-modelId'), 'Back navigation happened while saving');
    releaseSave(); await pause(); assert(saves === 1, 'Duplicate provider mutation');
  });
  await check('unmount ignores late completion', async () => {
    await mount('held-save'); await form(); await fill('setup-apiKey', secret); button('保存配置').click(); await pause(30);
    assert(saves === 1 && releaseSave, 'Held save did not start');
    flushSync(() => root.unmount()); root = null; releaseSave(); await pause();
    assert(complete === 0 && useAppStore.getState().onboardingStatus === 'incomplete', 'Late response completed an unmounted wizard');
  });
  await check('late initial read cannot overwrite edited fields', async () => {
    await mount('late-initial-read'); await form(); await fill('setup-providerName', 'edited-provider');
    releaseRead(); await pause();
    assert(document.getElementById('setup-providerName').value === 'edited-provider', 'Late load overwrote user edits');
  });
  await check('Agent-managed config remains read-only', async () => {
    await mount('agent-managed'); await form(); await submit();
    assert(saves === 0 && complete === 0 && document.querySelector('#app [role=alert]'), 'Agent config was shadowed by onboarding');
  });
  await check('synthetic secret is absent from logs and browser storage', async () => {
    assert(!consoleTexts.some((line) => line.includes(secret)), 'Synthetic secret reached console logs');
    assert(!JSON.stringify({ ...localStorage }).includes(secret), 'Synthetic secret reached local storage');
  });
}
const result = { baseline, running: false, passed: results.filter((row) => row.passed).length, failed: results.filter((row) => !row.passed).length, results };
document.getElementById('results').textContent = JSON.stringify(result, null, 2);
await fetch('/__onboarding_result', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result) });

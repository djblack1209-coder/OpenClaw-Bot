import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(new URL('../apps/openclaw-manager-src/package.json', import.meta.url));
const ts = require('typescript');
const base = new URL('../.openclaw/extensions/openclaw-weixin/src/messaging/', import.meta.url);
const options = { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 };
const shortcuts = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('intel-shortcuts.ts', base), 'utf8'), {
  compilerOptions: options,
}).outputText, { exports: shortcuts });
const source = readFileSync(new URL('process-message.ts', base), 'utf8');
const tree = ts.createSourceFile('process-message.ts', source, ts.ScriptTarget.Latest, true);
function functionCode(name) {
  const node = tree.statements.find((item) => ts.isFunctionDeclaration(item) && item.name?.text === name);
  assert.ok(node, `production function ${name} exists`);
  return ts.transpileModule(node.getText(tree), { compilerOptions: options }).outputText;
}

function fixture({ ok = true, reply = 'Global Intelligence Bot /today /ai /market', fetchError = false, sendError = false } = {}) {
  const requests = [], sends = [], evidence = [];
  const context = {
    ...shortcuts, process: { env: {} }, AbortController, setTimeout, clearTimeout,
    readLocalOpenClawApiToken: () => 'synthetic-api-token',
    logger: { info() {}, warn() {} },
    buildIntelBriefBridgeEvidence: (entry) => entry,
    writeIntelBriefBridgeEvidence: (entry) => evidence.push(entry),
    fetch: async (url, opts) => {
      requests.push({ url, ...opts });
      if (fetchError) throw new Error('synthetic fetch failure');
      return { ok, status: ok ? 200 : 503, json: async () => ({ reply }) };
    },
    sendMessageWeixin: async (entry) => {
      sends.push(entry);
      if (sendError) throw new Error('synthetic ambiguous send');
    },
  };
  vm.createContext(context);
  vm.runInContext(functionCode('tryHandleIntelBriefBridge') + '\nglobalThis.handle = tryHandleIntelBriefBridge;', context);
  return {
    requests, sends, evidence,
    run: (textBody) => context.handle({ full: { from_user_id: 'synthetic-user' }, deps: { baseUrl: 'https://invalid.example' }, textBody }),
  };
}

for (const text of ['104', '科技早报', '早报', '新闻', '/news', '帮我看科技早报', '看新闻', '今天的科技早报', '给我看看早报']) {
  test(`Weixin routes ${text} to the local Intel bridge`, async () => {
    const state = fixture();
    assert.equal(shortcuts.shouldHandleIntelBriefShortcut(text), true);
    assert.equal(await state.run(text), true);
    assert.equal(state.requests.length, 1);
    assert.equal(JSON.parse(state.requests[0].body).text, text);
    assert.equal(state.sends.length, 1);
    assert.match(state.sends[0].text, /Global Intelligence Bot/);
  });
}

for (const text of ['世界新闻', '英伟达新闻', '科技早报标题如何取', '不要看科技早报', '今天天气如何']) {
  test(`Weixin preserves ordinary message flow for ${text}`, async () => {
    const state = fixture();
    assert.equal(await state.run(text), false);
    assert.equal(state.requests.length, 0);
    assert.equal(state.sends.length, 0);
  });
}

for (const failure of [{ ok: false }, { reply: '' }, { fetchError: true }]) {
  test(`legacy news uses local guidance on bridge failure ${JSON.stringify(failure)}`, async () => {
    const state = fixture(failure);
    assert.equal(await state.run('104'), true);
    assert.equal(state.sends.length, 1);
    assert.equal(state.sends[0].text, shortcuts.LEGACY_NEWS_BRIDGE_UNAVAILABLE);
    assert.ok(!state.evidence.some((entry) => entry.status === 'handled'));
  });
}

test('an ambiguous legacy news reply is not retried or passed to general AI', async () => {
  const state = fixture({ sendError: true });
  assert.equal(await state.run('科技早报'), true);
  assert.equal(state.sends.length, 1);
  assert.equal(state.evidence.at(-1).status, 'failed');
});

test('existing Intel menu success and fallback behavior remain unchanged', async () => {
  const normal = fixture();
  assert.equal(await normal.run('700'), true);
  const failed = fixture({ fetchError: true });
  assert.equal(await failed.run('700'), false);
  assert.equal(failed.sends.length, 0);
  for (const text of ['701', '702', '703', '704', '705 08:30', '706 NVDA', '707', '708', '菜单', '我的订阅']) {
    assert.equal(shortcuts.shouldHandleIntelBriefShortcut(text), true);
  }
});

test('retired news routing has a distinct evidence classification', () => {
  const context = { ...shortcuts };
  vm.createContext(context);
  vm.runInContext(functionCode('classifyIntelBriefShortcut') + '\nglobalThis.classify = classifyIntelBriefShortcut;', context);
  assert.equal(context.classify('104'), 'legacy_news');
  assert.equal(context.classify('700'), 'today');
});

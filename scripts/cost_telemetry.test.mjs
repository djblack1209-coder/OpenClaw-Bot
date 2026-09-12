import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(new URL('../apps/openclaw-manager-src/package.json', import.meta.url));
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../apps/openclaw-manager-src/src/components/Home/TelemetryCard.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const exports = {};
vm.runInNewContext(compiled, {
  exports,
  require: (name) => name === '@/i18n' ? { useLanguage: () => ({ t: (key) => key }) } : require(name),
});

for (const [name, value, complete, expected, warning] of [
  ['known zero', 0, true, '$0.00', null],
  ['uninitialized', null, false, '—', 'telemetry.costUnknown'],
  ['pending charge', 0.25, false, '$0.25*', 'telemetry.costPartial'],
  ['known daily spend', 1.25, true, '$1.25', null],
]) {
  test(`cost telemetry: ${name}`, () => {
    const html = renderToStaticMarkup(React.createElement(exports.TelemetryCard, {
      isRunning: true,
      data: { llmCostDaily: value, llmCostComplete: complete, activeBots: 1, poolActive: 1, poolTotal: 1, memoryEntries: 0 },
    }));
    assert.ok(html.includes(expected));
    if (warning) assert.ok(html.includes(warning));
    else assert.ok(!html.includes('role="status"'));
    if (value === null) assert.ok(!html.includes('$0.00'));
  });
}

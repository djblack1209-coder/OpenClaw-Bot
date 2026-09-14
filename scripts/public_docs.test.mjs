import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { missingPublicTargets } from './check_public_docs.mjs';

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'openclaw-public-docs-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'docs'));
  writeFileSync(join(root, 'docs/guide.md'), '# Guide');
  return root;
}

test('README links and image paths fail when a public resource disappears', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'README.md'), '[Guide](docs/guide.md#setup)\n![Preview](preview.png)');
  assert.deepEqual(missingPublicTargets(root, ['README.md']), ['README.md: missing local target preview.png']);
  writeFileSync(join(root, 'preview.png'), 'fixture');
  assert.deepEqual(missingPublicTargets(root, ['README.md']), []);
});

test('HTML stylesheet and script targets are checked relative to the page', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'docs/index.html'), '<link href="style.css"><script src="demo.js"></script>');
  assert.equal(missingPublicTargets(root, ['docs/index.html']).length, 2);
});

test('GitHub issue form links catch a deleted same-repository document', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'config.yml'), 'url: https://github.com/djblack1209-coder/OpenClaw-Bot/blob/main/docs/deleted.md');
  assert.equal(missingPublicTargets(root, ['config.yml']).length, 1);
});

test('code samples, remote URLs and same-page fragments do not become local paths', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'README.md'), '[Web](https://example.com)\n[Section](#section)\n```md\n[Example](not-a-real-path.md)\n```');
  assert.deepEqual(missingPublicTargets(root, ['README.md']), []);
});

test('nested docs resolve parent paths and encoded names', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'my guide.md'), '# Guide');
  writeFileSync(join(root, 'docs/nested.md'), '[Guide](../my%20guide.md)');
  assert.deepEqual(missingPublicTargets(root, ['docs/nested.md']), []);
});

test('missing entry files and malformed URL escapes fail visibly', (t) => {
  const root = fixture(t);
  writeFileSync(join(root, 'README.md'), '[Bad](docs/%ZZ.md)');
  assert.equal(missingPublicTargets(root, ['README.md', 'absent.md']).length, 2);
});

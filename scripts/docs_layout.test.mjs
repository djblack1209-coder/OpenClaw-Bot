import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const roots = [];
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'openclaw-docs-test-'));
  roots.push(root);
  mkdirSync(join(root, 'scripts'));
  mkdirSync(join(root, 'docs/current'), { recursive: true });
  copyFileSync(fileURLToPath(new URL('./check_docs_layout.sh', import.meta.url)), join(root, 'scripts/check_docs_layout.sh'));
  writeFileSync(join(root, 'README.md'), '# Test\n`docs/001-project-map.md`\n');
  writeFileSync(join(root, 'docs/001-project-map.md'), '# 地图\n## 源码归属\n`docs/005-quickstart.md`\n');
  writeFileSync(join(root, 'docs/005-quickstart.md'), '# 快速开始\n');
  writeFileSync(join(root, 'docs/current/current-baseline.md'), '# 当前基线\n观察日期：2026-09-10\n## 当前职责\n## 未闭环项\n## 接管顺序\n');
  writeFileSync(join(root, 'docs/current/chatgpt-collaboration.md'), '# 协作连接\n');
  return root;
}

function check(root) {
  return spawnSync('bash', [join(root, 'scripts/check_docs_layout.sh')], { encoding: 'utf8' });
}

test('当前文档布局与协作说明可独立验证，不依赖已删除的索引或运维文件', () => {
  const result = check(fixture());
  assert.equal(result.status, 0, result.stdout + result.stderr);
});

test('跨项目引用必须带工作区前缀，本项目死链仍被拦截', () => {
  const root = fixture();
  const map = join(root, 'docs/001-project-map.md');
  writeFileSync(map, '# 地图\n`VPS-Config:docs/current/live-first-closure-v1.md`\n');
  let result = check(root);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  writeFileSync(map, '# 地图\n`docs/current/live-first-closure-v1.md`\n');
  result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /引用了不存在/);
});

test('缺少当前基线仍然失败', () => {
  const root = fixture();
  rmSync(join(root, 'docs/current/current-baseline.md'));
  const result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /缺少唯一当前基线/);
});

test('当前目录中的第二份生产基线仍然失败', () => {
  const root = fixture();
  writeFileSync(join(root, 'docs/current/another-baseline.md'), '# Other\n');
  const result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /docs\/current\//);
});

test('缺少未闭环章节仍然失败', () => {
  const root = fixture();
  writeFileSync(join(root, 'docs/current/current-baseline.md'), '# 基线\n观察日期：2026-09-10\n## 当前职责\n## 接管顺序\n');
  const result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /未闭环项/);
});

test('错误命名与重复编号仍然失败', () => {
  const root = fixture();
  writeFileSync(join(root, 'docs/README.md'), '# 错误位置\n');
  let result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /文件名必须/);
  rmSync(join(root, 'docs/README.md'));
  writeFileSync(join(root, 'docs/005-duplicate.md'), '# 重复编号\n');
  result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /重复编号/);
});

test('README 的不存在根指令文件仍然失败', () => {
  const root = fixture();
  writeFileSync(join(root, 'README.md'), '# Test\n`AGENTS.md`\n');
  const result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /AGENTS\.md/);
});

test('可变运行时安装规格仍然失败', () => {
  const root = fixture();
  writeFileSync(join(root, 'docs/005-quickstart.md'), '# 安装\n`openclaw@latest`\n');
  const result = check(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /可变安装规格/);
});

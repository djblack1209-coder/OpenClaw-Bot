import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('桌面管理器在窄浏览器窗口保持可读内容宽度', () => {
  const app = read('apps/openclaw-manager-src/src/App.tsx');
  const header = read('apps/openclaw-manager-src/src/components/Layout/Header.tsx');
  const sidebar = read('apps/openclaw-manager-src/src/components/Layout/Sidebar.tsx');

  assert.match(sidebar, /max-sm:w-\[56px\]/, '窄窗口必须把侧栏压缩为图标宽度');
  assert.match(sidebar, /truncate max-sm:hidden/, '窄窗口必须隐藏导航文字，不能挤压主内容');
  assert.match(sidebar, /max-sm:!w-8 max-sm:!p-0/, '窄窗口底部开关必须保持图标尺寸');
  assert.match(header, /hidden sm:inline font-mono tabular-nums/, '窄窗口应隐藏非必要时钟');
  assert.match(header, /hidden sm:inline.*header\.controlPanel/s, '窄窗口控制面板按钮应保留图标并隐藏长文字');
  assert.match(app, /px-2 py-2 sm:px-5 sm:py-4/, '窄窗口主内容需要减小外边距');
});

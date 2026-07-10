#!/usr/bin/env node
/**
 * 修复/重建 Chrome 里的「CC中转运营」书签文件夹。
 *
 * - 默认会写入本机 Chrome Profile，并在原目录生成 .codex-backup-* 备份。
 * - 支持用 CHROME_USER_DATA_DIR 指向临时目录做测试。
 * - 不读取/修改 Cookie、密码、历史记录或表单数据。
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const FOLDER_NAME = 'CC中转运营';
const REQUIRED_BOOKMARKS = [
  ['CC中转本机操作台', 'http://127.0.0.1:18800/'],
  ['CC中转用户主站', 'https://jiyu.245334.xyz/'],
];

const args = new Set(process.argv.slice(2));
const dryRun = args.has('--dry-run');
const jsonOnly = args.has('--json');
const visibleBookmarkFolder = args.has('--visible-bookmark-folder') || args.has('--visible-bookmark-group');
const openWindow = args.has('--open-window') || args.has('--open') || visibleBookmarkFolder;
const chromeBase = (
  process.env.CC_CHROME_USER_DATA_DIR ||
  process.env.CHROME_USER_DATA_DIR ||
  path.join(os.homedir(), 'Library/Application Support/Google/Chrome')
);

function safeJsonRead(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    return null;
  }
}

function writeJson(file, data) {
  const tmp = `${file}.codex-tmp-${process.pid}`;
  fs.writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`);
  fs.renameSync(tmp, file);
}

function backupFile(file, stamp) {
  if (!fs.existsSync(file)) return '';
  const backup = `${file}.codex-backup-${stamp}`;
  if (!fs.existsSync(backup)) fs.copyFileSync(file, backup);
  return backup;
}

function chromeTimestamp() {
  // Chrome 使用从 1601-01-01 起算的微秒。
  return String((Date.now() + 11644473600000) * 1000);
}

function collectNumericIds(node, ids = new Set()) {
  if (!node || typeof node !== 'object') return ids;
  if (node.id && /^\d+$/.test(String(node.id))) ids.add(Number(node.id));
  for (const child of node.children || []) collectNumericIds(child, ids);
  if (!node.type) {
    for (const key of ['bookmark_bar', 'other', 'synced']) collectNumericIds(node[key], ids);
  }
  return ids;
}

function createIdFactory(bookmarks) {
  const ids = collectNumericIds(bookmarks?.roots || {});
  let current = ids.size ? Math.max(...ids) + 1 : 1;
  return () => String(current++);
}

function ensureBookmarkRoots(bookmarks, now, nextId) {
  if (!bookmarks.roots) bookmarks.roots = {};
  for (const [key, name] of [
    ['bookmark_bar', 'Bookmarks bar'],
    ['other', 'Other bookmarks'],
    ['synced', 'Mobile bookmarks'],
  ]) {
    if (!bookmarks.roots[key]) {
      bookmarks.roots[key] = {
        children: [],
        date_added: now,
        date_last_used: '0',
        date_modified: now,
        id: nextId(),
        name,
        type: 'folder',
      };
    }
    if (!Array.isArray(bookmarks.roots[key].children)) bookmarks.roots[key].children = [];
  }
  if (!bookmarks.version) bookmarks.version = 1;
}

function extractExistingCcLinks(bookmarks) {
  const links = new Map();
  function walk(parent) {
    if (!parent || typeof parent !== 'object') return;
    const remaining = [];
    for (const child of parent.children || []) {
      if (child.type === 'folder' && child.name === FOLDER_NAME) {
        for (const item of child.children || []) {
          if (item.type === 'url' && item.url) links.set(item.url, item.name || item.url);
        }
        continue;
      }
      walk(child);
      remaining.push(child);
    }
    if (Array.isArray(parent.children)) parent.children = remaining;
  }
  for (const key of ['bookmark_bar', 'other', 'synced']) walk(bookmarks.roots?.[key]);
  return links;
}

function makeUrlNode(name, url, now, nextId) {
  return {
    date_added: now,
    date_last_used: '0',
    guid: '',
    id: nextId(),
    name,
    type: 'url',
    url,
  };
}

function ensureCcBookmarkFolder(bookmarks) {
  const now = chromeTimestamp();
  const nextId = createIdFactory(bookmarks);
  ensureBookmarkRoots(bookmarks, now, nextId);
  extractExistingCcLinks(bookmarks);
  const children = [];

  for (const [name, url] of REQUIRED_BOOKMARKS) {
    children.push(makeUrlNode(name, url, now, nextId));
  }
  // 这个文件夹是老板日常入口，只保留 1-3 个可点击页面；旧的 API/后台排障链接不再自动带回。

  bookmarks.roots.bookmark_bar.children.unshift({
    children,
    date_added: now,
    date_last_used: '0',
    date_modified: now,
    id: nextId(),
    name: FOLDER_NAME,
    type: 'folder',
  });
  bookmarks.roots.bookmark_bar.date_modified = now;
  return { folderCount: 1, urlCount: children.length };
}

function ensureBookmarkBarVisible(preferences) {
  if (!preferences.bookmark_bar) preferences.bookmark_bar = {};
  preferences.bookmark_bar.show_on_all_tabs = true;
  preferences.bookmark_bar.show_on_new_tab_page = true;
  return true;
}

function getProfiles(base) {
  const localState = safeJsonRead(path.join(base, 'Local State'));
  const profiles = Object.keys(localState?.profile?.info_cache || {}).sort();
  if (profiles.length) return profiles;
  return fs.existsSync(path.join(base, 'Default')) ? ['Default'] : [];
}

function repairProfile(base, profile, stamp) {
  const profileDir = path.join(base, profile);
  const bookmarksFile = path.join(profileDir, 'Bookmarks');
  const prefsFile = path.join(profileDir, 'Preferences');
  if (!fs.existsSync(profileDir)) return { profile, ok: false, message: 'profile 目录不存在' };

  const bookmarks = safeJsonRead(bookmarksFile) || { roots: {}, version: 1 };
  const preferences = safeJsonRead(prefsFile) || {};
  const summary = ensureCcBookmarkFolder(bookmarks);
  ensureBookmarkBarVisible(preferences);

  const backups = {};
  if (!dryRun) {
    fs.mkdirSync(profileDir, { recursive: true });
    backups.bookmarks = backupFile(bookmarksFile, stamp);
    backups.preferences = backupFile(prefsFile, stamp);
    writeJson(bookmarksFile, bookmarks);
    writeJson(prefsFile, preferences);
  }
  return {
    profile,
    ok: true,
    dryRun,
    urlCount: summary.urlCount,
    bookmarkBarVisible: true,
    backups,
  };
}

function quoteAppleScriptString(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function openChromeOpsWindow() {
  if (process.platform !== 'darwin') {
    return { ok: false, skipped: true, message: '只支持 macOS 自动打开 Chrome 窗口' };
  }
  if (dryRun) {
    return { ok: true, skipped: true, message: 'dry-run 跳过打开 Chrome 窗口' };
  }
  const urls = REQUIRED_BOOKMARKS.map(([, url]) => url);
  const appleUrls = urls.map((url) => `"${quoteAppleScriptString(url)}"`).join(', ');
  const script = `
set opsUrls to {${appleUrls}}
tell application "Google Chrome"
  activate
  set w to make new window
  set URL of active tab of w to item 1 of opsUrls
  repeat with i from 2 to count opsUrls
    make new tab at end of tabs of w with properties {URL:item i of opsUrls}
  end repeat
  set index of w to 1
  tell w to set active tab index to 1
end tell
${visibleBookmarkFolder ? `
delay 1.0
tell application "System Events"
  tell process "Google Chrome"
    set frontmost to true
    keystroke "d" using {command down, shift down}
    delay 0.8
    keystroke "${quoteAppleScriptString(FOLDER_NAME)}"
    delay 0.2
    key code 36
  end tell
end tell
` : ''}
`;
  const result = spawnSync('osascript', ['-e', script], {
    encoding: 'utf8',
    timeout: 15_000,
  });
  return {
    ok: result.status === 0,
    skipped: false,
    tabCount: urls.length,
    firstUrl: urls[0],
    visibleBookmarkFolder,
    stderr: (result.stderr || '').trim(),
  };
}

function main() {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const profiles = getProfiles(chromeBase);
  const results = profiles.map((profile) => repairProfile(chromeBase, profile, stamp));
  const openedWindow = openWindow ? openChromeOpsWindow() : { ok: true, skipped: true };
  const repairOk = results.length > 0 && results.every((item) => item.ok);
  const payload = {
    ok: repairOk && (!openWindow || openedWindow.ok),
    chromeBase,
    dryRun,
    folderName: FOLDER_NAME,
    requiredUrls: REQUIRED_BOOKMARKS.length,
    openWindowRequested: openWindow,
    visibleBookmarkFolderRequested: visibleBookmarkFolder,
    openedWindow,
    profiles: results,
  };
  if (jsonOnly) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  } else {
    console.log(`CC中转 Chrome 书签修复: ${payload.ok ? 'PASS' : 'FAIL'}${dryRun ? ' (dry-run)' : ''}`);
    for (const item of results) {
      console.log(`- ${item.profile}: ${item.ok ? 'OK' : 'FAIL'} urls=${item.urlCount || 0}`);
    }
    if (openWindow) {
      console.log(`- 打开运营窗口: ${openedWindow.ok ? 'OK' : 'FAIL'} tabs=${openedWindow.tabCount || 0}`);
    }
  }
  process.exit(payload.ok ? 0 : 1);
}

main();

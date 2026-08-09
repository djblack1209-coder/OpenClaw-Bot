#!/usr/bin/env node
/**
 * 一键启动 CC中转闲鱼卖家专用 Chrome。
 *
 * 目的：打开供本机卖家桥接器接管的隔离浏览器。
 * - 使用独立 Chrome Profile，不读取/修改默认 Chrome Cookie、密码或历史记录。
 * - 默认打开本机操作台、用户主站和闲鱼首页，老板只需在这个专用窗口登录闲鱼。
 * - 卖家桥接器通过回环 CDP 接管闲鱼页面；社媒插件不属于闲鱼启动前置条件。
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawn } from 'node:child_process'

const args = new Set(process.argv.slice(2))
const dryRun = args.has('--dry-run')
const jsonOnly = args.has('--json')
const foreground = args.has('--foreground')
const browserMode = String(process.env.CC_XIANYU_BROWSER_MODE || 'auto').trim().toLowerCase()

if (args.has('--copy-token')) {
  console.error('参数 --copy-token 已移除：启动器不会复制 OPENCLAW_API_TOKEN 到剪贴板。')
  process.exit(2)
}

const defaultChromeProfileDir = path.join(os.homedir(), '.openclaw/cc-zhongzhuan-seller-chrome')
const defaultChromiumProfileDir = path.join(os.homedir(), '.openclaw/cc-zhongzhuan-seller-chromium-v2')
const googleChromeBinary = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const debugPort = Number.parseInt(process.env.CC_XIANYU_CHROME_DEBUG_PORT || '9225', 10)
const openUrls = [
  'http://127.0.0.1:18800/',
  'https://jiyu.245334.xyz/',
  'https://www.goofish.com/',
]

function findCachedPlaywrightChromium() {
  const cacheRoot = path.join(os.homedir(), 'Library/Caches/ms-playwright')
  if (!fs.existsSync(cacheRoot)) return ''
  const candidates = fs
    .readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('chromium-'))
    .map((entry) =>
      path.join(
        cacheRoot,
        entry.name,
        'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
      ),
    )
    .filter((candidate) => fs.existsSync(candidate))
  candidates.sort().reverse()
  return candidates[0] || ''
}

function findPlaywrightChromiumBinary() {
  const explicit = String(process.env.CC_XIANYU_CHROMIUM_BIN || '').trim()
  return explicit && fs.existsSync(explicit) ? explicit : findCachedPlaywrightChromium()
}

function selectBrowser() {
  if (browserMode === 'google-chrome' || browserMode === 'chrome') {
    return {
      launchMode: 'google-chrome-cdp',
      browserBinary: googleChromeBinary,
      profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromeProfileDir,
    }
  }
  const chromiumBinary = findPlaywrightChromiumBinary()
  if (chromiumBinary) {
    return {
      launchMode: 'chromium-cdp',
      browserBinary: chromiumBinary,
      profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromiumProfileDir,
    }
  }
  return {
    launchMode: 'google-chrome-cdp',
    browserBinary: googleChromeBinary,
    profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromeProfileDir,
  }
}

function main() {
  const browser = selectBrowser()
  const exists = {
    browserBinary: fs.existsSync(browser.browserBinary),
  }
  const chromeArgs = [
    `--user-data-dir=${browser.profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    ...(Number.isFinite(debugPort) && debugPort > 0
      ? [`--remote-debugging-port=${debugPort}`, '--remote-debugging-address=127.0.0.1']
      : []),
    ...openUrls,
  ]
  const payload = {
    ok: exists.browserBinary,
    dryRun,
    launchMode: browser.launchMode,
    browserBinary: browser.browserBinary,
    profileDir: browser.profileDir,
    debugPort,
    openUrls,
    exists,
    commandPreview: [browser.browserBinary, ...chromeArgs],
  }

  if (!payload.ok || dryRun) {
    process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : [
      `CC中转卖家 Chrome 启动器: ${payload.ok ? 'DRY-RUN' : 'FAIL'}`,
      `- 浏览器模式: ${payload.launchMode}`,
      `- 浏览器: ${exists.browserBinary ? '已找到' : '未找到'}`,
      `- 专用 Profile: ${browser.profileDir}`,
      '- 闲鱼接管：通过回环 CDP，不依赖浏览器扩展。',
    ].filter(Boolean).join('\n') + '\n')
    process.exit(payload.ok ? 0 : 1)
  }

  fs.mkdirSync(browser.profileDir, { recursive: true })
  const child = spawn(browser.browserBinary, chromeArgs, {
    detached: !foreground,
    stdio: foreground ? 'inherit' : 'ignore',
  })
  if (!foreground) child.unref()
  payload.pid = child.pid
  process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : [
    'CC中转卖家 Chrome 启动器: OK',
    `- 浏览器模式: ${payload.launchMode}`,
    '- 已准备隔离卖家浏览器；闲鱼由本机桥接器通过回环 CDP 接管。',
    `- 已打开页面: ${openUrls.length} 个`,
    '- 下一步：首次在这个专用隔离窗口登录闲鱼，并保持窗口打开。',
  ].filter(Boolean).join('\n') + '\n')
}

main()

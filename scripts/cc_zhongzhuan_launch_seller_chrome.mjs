#!/usr/bin/env node
/**
 * 一键启动 CC中转闲鱼卖家专用 Chrome。
 *
 * 目的：把加载插件前的准备动作自动化。
 * - 使用独立 Chrome Profile，不读取/修改默认 Chrome Cookie、密码或历史记录。
 * - 生成本机运行版 Social Pilot 插件目录，内含本机 runtime-config.json，避免手动粘贴 Token。
 * - 默认打开本机操作台、用户主站和闲鱼首页，老板只需在这个专用窗口登录闲鱼。
 * - 优先使用 Playwright Chromium 自动加载插件；没有 Chromium 时才降级到 Google Chrome 手动加载。
 * - 专用浏览器会关闭 Chrome 142+ 的 Local Network Access 拦截，允许插件访问本机 18790/18800。
 * - 可选 --copy-token：把本机 OPENCLAW_API_TOKEN 放入剪贴板，作为运行版配置的兜底；不会打印 token。
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { spawn, spawnSync } from 'node:child_process'

const args = new Set(process.argv.slice(2))
const dryRun = args.has('--dry-run')
const jsonOnly = args.has('--json')
const copyToken = args.has('--copy-token')
const foreground = args.has('--foreground')
const browserMode = String(process.env.CC_XIANYU_BROWSER_MODE || 'auto').trim().toLowerCase()

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
const extensionSourceDir = path.join(repoRoot, 'packages/openclaw-npm/assets/chrome-extension')
const runtimeExtensionDir = process.env.CC_XIANYU_CHROME_EXTENSION_RUNTIME_DIR || path.join(os.homedir(), '.openclaw/cc-social-pilot-runtime-extension')
const defaultChromeProfileDir = path.join(os.homedir(), '.openclaw/cc-zhongzhuan-seller-chrome')
const defaultChromiumProfileDir = path.join(os.homedir(), '.openclaw/cc-zhongzhuan-seller-chromium-v2')
const googleChromeBinary = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const debugPort = Number.parseInt(process.env.CC_XIANYU_CHROME_DEBUG_PORT || '9225', 10)
const bundledNodeModules =
  process.env.CODEX_BUNDLED_NODE_MODULES ||
  '/Users/blackdj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
const openUrls = [
  'http://127.0.0.1:18800/',
  'https://jiyu.245334.xyz/',
  'https://www.goofish.com/',
]

function parseEnvFile(file) {
  if (!fs.existsSync(file)) return {}
  const result = {}
  for (const rawLine of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#') || !line.includes('=')) continue
    const [key, ...rest] = line.split('=')
    result[key.trim()] = rest.join('=').trim().replace(/^['"]|['"]$/g, '')
  }
  return result
}

function copyTextToClipboard(text) {
  if (!text) return { ok: false, skipped: true, reason: 'empty' }
  if (process.platform !== 'darwin') return { ok: false, skipped: true, reason: 'pbcopy 只支持 macOS' }
  const result = spawnSync('pbcopy', { input: text, encoding: 'utf8', timeout: 3000 })
  return { ok: result.status === 0, skipped: false }
}

function prepareRuntimeExtension(token) {
  fs.rmSync(runtimeExtensionDir, { recursive: true, force: true })
  fs.mkdirSync(path.dirname(runtimeExtensionDir), { recursive: true })
  fs.cpSync(extensionSourceDir, runtimeExtensionDir, {
    recursive: true,
    filter: (src) => !src.includes(`${path.sep}test${path.sep}`),
  })
  if (token) {
    const configFile = path.join(runtimeExtensionDir, 'runtime-config.json')
    fs.writeFileSync(
      configFile,
      `${JSON.stringify({ gatewayToken: token, relayPort: 18792, generatedAt: new Date().toISOString() }, null, 2)}\n`,
      { mode: 0o600 },
    )
  }
  return runtimeExtensionDir
}

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
  if (explicit && fs.existsSync(explicit)) return explicit
  const bundledPlaywright = path.join(bundledNodeModules, 'playwright/index.js')
  if (fs.existsSync(bundledPlaywright)) {
    try {
      const require = createRequire(bundledPlaywright)
      const { chromium } = require('playwright')
      const executable = chromium.executablePath()
      if (executable && fs.existsSync(executable)) return executable
    } catch {
      // 如果 bundled Playwright 暂不可用，继续查缓存目录。
    }
  }
  return findCachedPlaywrightChromium()
}

function selectBrowser() {
  if (browserMode === 'google-chrome' || browserMode === 'chrome') {
    return {
      launchMode: 'google-chrome-manual-extension',
      browserBinary: googleChromeBinary,
      profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromeProfileDir,
      autoExtensionLoadEnabled: false,
      manualExtensionLoadRequired: true,
      installHint: '',
    }
  }
  const chromiumBinary = findPlaywrightChromiumBinary()
  if (chromiumBinary) {
    return {
      launchMode: 'chromium-auto-extension',
      browserBinary: chromiumBinary,
      profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromiumProfileDir,
      autoExtensionLoadEnabled: true,
      manualExtensionLoadRequired: false,
      installHint: '',
    }
  }
  return {
    launchMode: 'google-chrome-manual-extension',
    browserBinary: googleChromeBinary,
    profileDir: process.env.CC_XIANYU_CHROME_PROFILE_DIR || defaultChromeProfileDir,
    autoExtensionLoadEnabled: false,
    manualExtensionLoadRequired: true,
    installHint: '如需免手动加载插件，请先运行：npx --yes playwright@1.61.1 install chromium',
  }
}

function openFinder(targetDir) {
  if (process.platform !== 'darwin') return { ok: false, skipped: true }
  const result = spawnSync('open', [targetDir], { encoding: 'utf8', timeout: 5000 })
  return { ok: result.status === 0, skipped: false }
}

function openChromeExtensionsPage() {
  if (process.platform !== 'darwin') return { ok: false, skipped: true }
  const script = `
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  set URL of active tab of front window to "chrome://extensions/"
end tell
`
  const result = spawnSync('osascript', ['-e', script], { encoding: 'utf8', timeout: 5000 })
  return { ok: result.status === 0, skipped: false }
}

function main() {
  const browser = selectBrowser()
  const exists = {
    browserBinary: fs.existsSync(browser.browserBinary),
    chromeBinary: fs.existsSync(browser.browserBinary),
    extensionDir: fs.existsSync(path.join(extensionSourceDir, 'manifest.json')),
  }
  const env = parseEnvFile(path.join(repoRoot, 'packages/clawbot/config/.env'))
  const tokenCopy = copyToken ? copyTextToClipboard(env.OPENCLAW_API_TOKEN || '') : { ok: false, skipped: true }
  const extensionDir = exists.extensionDir && !dryRun ? prepareRuntimeExtension(env.OPENCLAW_API_TOKEN || '') : runtimeExtensionDir
  const runtimeConfigWritten = exists.extensionDir && !dryRun && Boolean(env.OPENCLAW_API_TOKEN)
  const chromeArgs = [
    `--user-data-dir=${browser.profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults',
    ...(Number.isFinite(debugPort) && debugPort > 0
      ? [`--remote-debugging-port=${debugPort}`, '--remote-debugging-address=127.0.0.1']
      : []),
    ...(browser.autoExtensionLoadEnabled
      ? [`--disable-extensions-except=${extensionDir}`, `--load-extension=${extensionDir}`]
      : []),
    ...openUrls,
  ]
  const payload = {
    ok: exists.browserBinary && exists.extensionDir,
    dryRun,
    launchMode: browser.launchMode,
    browserBinary: browser.browserBinary,
    chromeBinary: browser.browserBinary,
    profileDir: browser.profileDir,
    debugPort,
    extensionSourceDir,
    extensionDir,
    runtimeConfigWritten,
    openUrls,
    autoExtensionLoadEnabled: browser.autoExtensionLoadEnabled,
    tokenCopiedToClipboard: copyToken ? tokenCopy.ok : false,
    manualExtensionLoadRequired: browser.manualExtensionLoadRequired,
    installHint: browser.installHint,
    exists,
    commandPreview: [browser.browserBinary, ...chromeArgs],
  }

  if (!payload.ok || dryRun) {
    process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : [
      `CC中转卖家 Chrome 启动器: ${payload.ok ? 'DRY-RUN' : 'FAIL'}`,
      `- 浏览器模式: ${payload.launchMode}`,
      `- 浏览器: ${exists.browserBinary ? browser.browserBinary : '未找到'}`,
      `- 插件源码目录: ${exists.extensionDir ? extensionSourceDir : '未找到 manifest.json'}`,
      `- 运行版插件目录: ${extensionDir}`,
      `- 专用 Profile: ${browser.profileDir}`,
      `- 插件加载: ${payload.autoExtensionLoadEnabled ? '随专用 Chromium 自动加载' : '需要手动加载'}`,
      payload.installHint ? `- 自动插件提示: ${payload.installHint}` : '',
      copyToken ? `- Token 剪贴板: ${tokenCopy.ok ? '已复制' : '未复制'}` : '- Token 剪贴板: 跳过',
    ].filter(Boolean).join('\n') + '\n')
    process.exit(payload.ok ? 0 : 1)
  }

  fs.mkdirSync(browser.profileDir, { recursive: true })
  const child = spawn(browser.browserBinary, chromeArgs, {
    detached: !foreground,
    stdio: foreground ? 'inherit' : 'ignore',
  })
  if (!foreground) child.unref()
  const finder = browser.manualExtensionLoadRequired ? openFinder(extensionDir) : { ok: false, skipped: true }
  const extensionsPage = browser.manualExtensionLoadRequired ? openChromeExtensionsPage() : { ok: false, skipped: true }

  payload.pid = child.pid
  payload.finderOpened = finder.ok
  payload.extensionsPageOpened = extensionsPage.ok
  process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : [
    'CC中转卖家 Chrome 启动器: OK',
    `- 浏览器模式: ${payload.launchMode}`,
    `- 已准备运行版插件目录: ${extensionDir}`,
    `- 专用 Profile: ${browser.profileDir}`,
    `- Runtime Token: ${payload.runtimeConfigWritten ? '已写入本机运行配置' : '未写入'}`,
    `- 已打开页面: ${openUrls.length} 个`,
    payload.autoExtensionLoadEnabled
      ? '- 插件加载: 已随专用 Chromium 自动加载，无需打开 chrome://extensions。'
      : `- Chrome 扩展页: ${extensionsPage.ok ? '已打开' : '未打开'}`,
    payload.autoExtensionLoadEnabled
      ? '- 下一步: 在这个专用 Chromium 窗口登录闲鱼并保持窗口打开。'
      : `- Finder 插件目录: ${finder.ok ? '已打开' : '未打开'}`,
    copyToken ? `- Token 剪贴板: ${tokenCopy.ok ? '已复制，可粘贴到插件高级设置' : '未复制'}` : '- Token 剪贴板: 跳过；如首次使用可加 --copy-token',
    payload.autoExtensionLoadEnabled
      ? ''
      : '- 下一步: 在扩展页打开“开发者模式”→“加载已解压的扩展程序”→选择上面的运行版插件目录。',
  ].filter(Boolean).join('\n') + '\n')
}

main()

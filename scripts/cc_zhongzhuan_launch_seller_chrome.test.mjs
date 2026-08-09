import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import test from 'node:test'

const script = path.resolve('scripts/cc_zhongzhuan_launch_seller_chrome.mjs')

test('seller browser launcher prepares an isolated CDP browser without extension setup', () => {
  const output = execFileSync(process.execPath, [script, '--dry-run', '--json'], {
    cwd: path.resolve('.'),
    encoding: 'utf8',
    env: {
      ...process.env,
      CC_XIANYU_BROWSER_MODE: 'auto',
    },
  })
  const payload = JSON.parse(output)
  assert.equal(payload.ok, true)
  assert.match(payload.browserBinary, /Chrome|Chromium/i)
  assert.match(payload.launchMode, /-cdp$/)
  assert.equal('manualExtensionLoadRequired' in payload, false)
  assert.equal('installHint' in payload, false)
  assert.equal('runtimeConfigWritten' in payload, false)
  assert.equal(payload.commandPreview.some((item) => item.includes('--load-extension=')), false)
  assert.equal(payload.commandPreview.some((item) => item.includes('disable-extensions-except')), false)
  assert.equal(payload.commandPreview.some((item) => item.includes('OPENCLAW_API_TOKEN')), false)
})

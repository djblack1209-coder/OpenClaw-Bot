import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import test from 'node:test'

const script = path.resolve('scripts/cc_zhongzhuan_launch_seller_chrome.mjs')

test('seller browser launcher prefers auto-loaded Chromium extension in dry run', () => {
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
  assert.ok(payload.commandPreview.some((item) => item.includes('LocalNetworkAccessChecks')))
  if (payload.launchMode === 'chromium-auto-extension') {
    assert.equal(payload.manualExtensionLoadRequired, false)
    assert.equal(payload.autoExtensionLoadEnabled, true)
    assert.ok(payload.commandPreview.some((item) => item.includes('--load-extension=')))
    assert.ok(payload.profileDir.endsWith('cc-zhongzhuan-seller-chromium-v2'))
  } else {
    assert.equal(payload.launchMode, 'google-chrome-manual-extension')
    assert.equal(payload.manualExtensionLoadRequired, true)
    assert.match(payload.installHint, /playwright/i)
  }
})

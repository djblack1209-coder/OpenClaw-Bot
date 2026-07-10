#!/usr/bin/env node
/**
 * 通过专用 Chrome 的本地 DevTools 端口配置 Social Pilot 插件。
 *
 * - 只连接 127.0.0.1 调试端口。
 * - 读取本机 packages/clawbot/config/.env 里的 OPENCLAW_API_TOKEN，但不打印。
 * - 只在 manifest.name === "OpenEverything Social Pilot" 的扩展上下文里写入 gatewayToken。
 * - 写入后立即让插件上下文上报新版 CC中转发货助手能力。
 */

import fs from 'node:fs'
import path from 'node:path'

const args = new Set(process.argv.slice(2))
const jsonOnly = args.has('--json')
const dryRun = args.has('--dry-run')
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
const debugPort = Number.parseInt(process.env.CC_XIANYU_CHROME_DEBUG_PORT || '9225', 10)

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

async function fetchJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(5000) })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

function cdpEvaluate(webSocketDebuggerUrl, expression) {
  return new Promise((resolve) => {
    const ws = new WebSocket(webSocketDebuggerUrl)
    let nextId = 0
    let runtimeEnabled = false
    const timer = setTimeout(() => {
      try { ws.close() } catch {}
      resolve({ ok: false, error: 'timeout' })
    }, 12000)
    const send = (method, params = {}) => {
      nextId += 1
      ws.send(JSON.stringify({ id: nextId, method, params }))
      return nextId
    }
    ws.addEventListener('open', () => {
      send('Runtime.enable')
    })
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data || '{}'))
      if (!message.id) return
      if (!runtimeEnabled) {
        if (message.error) {
          clearTimeout(timer)
          try { ws.close() } catch {}
          resolve({ ok: false, error: message.error.message || 'runtime_enable_failed' })
          return
        }
        runtimeEnabled = true
        send('Runtime.evaluate', {
          expression,
          awaitPromise: true,
          returnByValue: true,
        })
        return
      }
      clearTimeout(timer)
      try { ws.close() } catch {}
      if (message.error) {
        resolve({ ok: false, error: message.error.message || 'cdp_error' })
        return
      }
      const result = message.result?.result?.value
      resolve({ ok: true, result })
    })
    ws.addEventListener('error', () => {
      clearTimeout(timer)
      resolve({ ok: false, error: 'websocket_error' })
    })
  })
}

function buildExpression(token) {
  const safeToken = JSON.stringify(token)
  return `(${async function configureSocialPilot(serializedToken) {
    const token = JSON.parse(serializedToken)
    const manifest = chrome?.runtime?.getManifest?.() || {}
    if (manifest.name !== 'OpenEverything Social Pilot') {
      return { matched: false, name: manifest.name || '' }
    }
    await chrome.storage.local.set({ gatewayToken: token, relayPort: 18792 })
    const payload = {
      platform: 'xianyu',
      url: 'https://www.goofish.com/',
      running: true,
      detected_platform: { id: 'xianyu', label: '闲鱼', supported: true },
      tasks: [
        'CC中转卖家专用 Chrome 已启动',
        '已启用付款页自动发卡能力',
        '已启用确认发货/恢复上架队列能力',
      ],
      extension: {
        manifest_version: String(manifest.version || 'preview'),
        cc_delivery_helper_version: '2026-07-07-paid-page-fallback',
        capabilities: {
          xianyu_delivery_scan: true,
          xianyu_delivery_send: true,
          xianyu_confirm_shipment: true,
          xianyu_relist_item: true,
          current_chat_watch: true,
          all_open_xianyu_tabs_watch: true,
          target_tab_preflight: true,
          single_pending_global_gate: true,
          background_heartbeat: true,
          relist_queue_watch: true,
          paid_page_dispatch: true,
        },
      },
      heartbeat_reason: 'seller_chrome_auto_config',
    }
    const response = await fetch('http://127.0.0.1:18790/api/v1/social/extension/status', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-token': token,
      },
      body: JSON.stringify(payload),
    })
    return {
      matched: true,
      manifest_version: String(manifest.version || ''),
      status: response.status,
      ok: response.ok,
    }
  }})(${JSON.stringify(safeToken)})`
}

async function main() {
  const env = parseEnvFile(path.join(repoRoot, 'packages/clawbot/config/.env'))
  const token = String(env.OPENCLAW_API_TOKEN || '').trim()
  const payload = {
    ok: false,
    dryRun,
    debugPort,
    targets: 0,
    matchedTargets: 0,
    configuredTargets: 0,
    tokenPresent: Boolean(token),
    errors: [],
  }
  if (!token) {
    payload.errors.push('OPENCLAW_API_TOKEN missing')
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`)
    process.exit(1)
  }
  if (dryRun) {
    payload.ok = true
    process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : 'CC中转插件配置: DRY-RUN\n')
    process.exit(0)
  }
  let targets = []
  try {
    targets = await fetchJson(`http://127.0.0.1:${debugPort}/json/list`)
  } catch (error) {
    payload.errors.push(`无法连接专用 Chrome 调试端口: ${String(error.message || error)}`)
  }
  payload.targets = Array.isArray(targets) ? targets.length : 0
  const expression = buildExpression(token)
  for (const target of Array.isArray(targets) ? targets : []) {
    if (!String(target.url || '').startsWith('chrome-extension://')) continue
    if (!target.webSocketDebuggerUrl) continue
    const result = await cdpEvaluate(target.webSocketDebuggerUrl, expression)
    if (!result.ok) {
      payload.errors.push(result.error || 'cdp_evaluate_failed')
      continue
    }
    if (result.result?.matched) {
      payload.matchedTargets += 1
      if (result.result.ok) payload.configuredTargets += 1
      else payload.errors.push(`插件状态上报 HTTP ${result.result.status}`)
    }
  }
  payload.ok = payload.configuredTargets > 0
  process.stdout.write(jsonOnly ? `${JSON.stringify(payload, null, 2)}\n` : [
    `CC中转插件配置: ${payload.ok ? 'OK' : 'FAIL'}`,
    `- 调试端口: ${debugPort}`,
    `- 匹配插件目标: ${payload.matchedTargets}`,
    `- 成功配置: ${payload.configuredTargets}`,
  ].join('\n') + '\n')
  process.exit(payload.ok ? 0 : 1)
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ ok: false, error: String(error.message || error) }, null, 2)}\n`)
  process.exit(1)
})

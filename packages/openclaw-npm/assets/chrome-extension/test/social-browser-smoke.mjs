import assert from 'node:assert/strict'
import { mkdir, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import {
  buildAutofillPayload,
  buildPageProbePayload,
  detectSocialPlatform,
} from '../social-core.js'
import { runSocialFieldPlanInPage, runSocialPageContextScanInPage } from '../social-page-runner.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const extensionRoot = resolve(__dirname, '..')
const outputDir = resolve(extensionRoot, '../../../../output/playwright/social-pilot-browser-smoke-20260624')

export const PLATFORM_SCENARIOS = [
  {
    id: 'x',
    url: 'https://x.com/home',
    title: 'X Home',
    draft: {
      id: 'smoke-x',
      platform: 'x',
      review_status: 'approved',
      title: 'GitHub 一周异常 Star 工具榜',
      text: '先看能不能马上部署，再看有没有真实需求，最后留一个风险边界。',
    },
    html: `
      <main>
        <section data-testid="trend">GitHub 一周异常 Star 工具榜</section>
        <article><div data-testid="tweetText">年轻创业者在讨论 AI Agent 怎么落地到自己的业务里</div></article>
        <div data-testid="tweetTextarea" role="textbox" contenteditable="true" aria-label="Post text"></div>
        <button data-testid="tweetButtonInline">Post</button>
      </main>
    `,
    assertionText: 'GitHub 一周异常 Star 工具榜',
    contextText: 'AI Agent 怎么落地',
  },
  {
    id: 'xhs',
    url: 'https://www.xiaohongshu.com/explore',
    title: '小红书 Explore',
    draft: {
      id: 'smoke-xhs',
      platform: 'xhs',
      review_status: 'approved',
      title: '3分钟做出一杯夏日冰饮',
      text: '家人们，冷泡茶 + 柠檬 + 冰块就能复刻，建议收藏。',
    },
    html: `
      <main>
        <section class="note-card"><div class="title">夏日低卡冰饮教程</div></section>
        <section class="content">家人们，冷泡茶加柠檬真的适合收藏</section>
        <input placeholder="添加标题" />
        <div class="ql-editor" contenteditable="true" data-placeholder="添加正文"></div>
        <button class="publish">发布</button>
      </main>
    `,
    assertionText: '家人们，冷泡茶',
    contextText: '冷泡茶加柠檬',
  },
  {
    id: 'xianyu',
    url: 'https://www.goofish.com/item?id=1',
    title: '闲鱼商品',
    draft: {
      id: 'smoke-xianyu',
      platform: 'xianyu',
      review_status: 'approved',
      title: '买家问能不能便宜',
      text: '可以小刀，但商品状态和配件都在，今天拍可以优先发出。',
    },
    html: `
      <main>
        <section class="item-card"><div class="title">MacBook Air M2 低价出</div></section>
        <section class="message">买家问还能不能便宜一点，今天能不能发货</section>
        <div contenteditable="true" data-placeholder="请输入回复内容"></div>
        <button class="send">发送</button>
      </main>
    `,
    assertionText: '可以小刀',
    contextText: '今天能不能发货',
  },
]

async function loadChromium() {
  try {
    const mod = await import('playwright')
    return mod.chromium
  } catch {
    const mod = await import(
      pathToFileURL('/Users/blackdj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href
    )
    return mod.chromium
  }
}

async function runScenario(page, scenario) {
  await page.route('**/*', async (route) => {
    const request = route.request()
    if (request.resourceType() === 'document') {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: `<!doctype html>
          <html lang="zh-CN">
            <head>
              <meta charset="utf-8" />
              <title>${scenario.title}</title>
              <style>
                body { font: 16px system-ui; padding: 28px; background: #fffaf4; color: #161412; }
                main { display: grid; gap: 16px; max-width: 760px; }
                input, textarea, [contenteditable="true"] { min-height: 54px; border: 1px solid #d7c7b5; border-radius: 12px; padding: 12px; background: #f2e9de; }
                button { width: max-content; border: 0; border-radius: 999px; padding: 10px 16px; background: #ff5a36; color: white; }
              </style>
            </head>
            <body>
              <script>
                window.__socialSmokeButtonClicks = 0;
                document.addEventListener('click', (event) => {
                  const button = event.target && event.target.closest ? event.target.closest('button') : null;
                  if (button) {
                    window.__socialSmokeButtonClicks += 1;
                    button.dataset.clicked = 'true';
                  }
                }, true);
              </script>
              ${scenario.html}
            </body>
          </html>`,
      })
      return
    }
    await route.abort()
  })

  await page.goto(scenario.url, { waitUntil: 'domcontentloaded' })
  const platform = detectSocialPlatform(page.url())
  assert.equal(platform.id, scenario.id)
  assert.equal(platform.supported, true)

  const probePayload = buildPageProbePayload({ platformId: platform.id })
  const probeResult = await page.evaluate((payload) => globalThis.runSocialFieldPlanInPage(payload), probePayload)
  assert.equal(probeResult.ready, true)
  assert.equal(probeResult.filled, false)

  const contextResult = await page.evaluate(
    (payload) => globalThis.runSocialPageContextScanInPage(payload),
    { platform: platform.id, url: page.url(), title: scenario.title, action: 'scan_page_context' },
  )
  assert.equal(contextResult.ready, true)
  assert.equal(contextResult.platform, scenario.id)
  assert.match(contextResult.bodyText || contextResult.trends.join(' ') || contextResult.headings.join(' '), new RegExp(scenario.contextText))
  assert.equal(contextResult.publishIntent, false)
  assert.equal(contextResult.auto_publish_enabled, false)

  const autofillPayload = buildAutofillPayload({ platformId: platform.id, draft: scenario.draft })
  assert.equal(autofillPayload.publishIntent, false)
  assert.equal(autofillPayload.allowButtonClick, false)
  const fillResult = await page.evaluate((payload) => globalThis.runSocialFieldPlanInPage(payload), autofillPayload)
  assert.equal(fillResult.filled, true)
  assert.equal(fillResult.publishClicked === false, true)

  const pageText = await page.locator('body').innerText()
  assert.match(pageText, new RegExp(scenario.assertionText))
  const clicked = await page.evaluate(() => Array.from(document.querySelectorAll('button')).some((button) => button.dataset.clicked === 'true'))
  const buttonClicks = await page.evaluate(() => window.__socialSmokeButtonClicks || 0)
  assert.equal(clicked, false)
  assert.equal(buttonClicks, 0)

  const screenshotPath = resolve(outputDir, `${scenario.id}.png`)
  await page.screenshot({ path: screenshotPath, fullPage: true })
  return {
    platform: platform.id,
    ready: probeResult.ready,
    contextReady: contextResult.ready,
    contextSignals: contextResult.count,
    filled: fillResult.filled,
    buttonClicks,
    screenshotPath,
  }
}


async function runPopupPreviewSmoke(page) {
  await page.unroute('**/*').catch(() => {})
  await page.route('http://social-pilot.local/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname === '/' ? '/popup.html' : url.pathname
    const filePath = resolve(extensionRoot, pathname.replace(/^\/+/, ''))
    try {
      const body = await readFile(filePath)
      const contentType = pathname.endsWith('.js')
        ? 'text/javascript; charset=utf-8'
        : pathname.endsWith('.css')
          ? 'text/css; charset=utf-8'
          : pathname.endsWith('.png')
            ? 'image/png'
            : 'text/html; charset=utf-8'
      await route.fulfill({ status: 200, contentType, body })
    } catch {
      await route.fulfill({ status: 404, contentType: 'text/plain', body: 'not found' })
    }
  })
  await page.goto('http://social-pilot.local/popup.html', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#scan-page-context')
  await page.click('#scan-page-context')
  await page.waitForSelector('#page-context-panel[data-visible="true"]')
  const panelText = await page.locator('#page-context-panel').innerText()
  assert.match(panelText, /GitHub 一周异常 Star 工具榜|当前页热点/)
  await page.click('.page-context-card')
  await page.waitForSelector('#draft-editor[data-visible="true"]')
  const draftText = await page.locator('#draft-result').innerText()
  assert.match(draftText, /当前页上下文生成待审草稿|不会自动发布/)
  const screenshotPath = resolve(outputDir, 'social-pilot-popup-context-20260624.png')
  await page.screenshot({ path: screenshotPath, fullPage: true })
  return {
    ready: true,
    panelVisible: true,
    draftEditorVisible: true,
    screenshotPath,
  }
}

export async function runBrowserSmoke() {
  await mkdir(outputDir, { recursive: true })
  const chromium = await loadChromium()
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const page = await browser.newPage({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 1 })
  await page.addInitScript({
    content: [
      `globalThis.runSocialFieldPlanInPage = ${runSocialFieldPlanInPage.toString()};`,
      `globalThis.runSocialPageContextScanInPage = ${runSocialPageContextScanInPage.toString()};`,
    ].join('\n'),
  })
  await page.exposeFunction('__noop', () => null)
  const results = []
  try {
    for (const scenario of PLATFORM_SCENARIOS) {
      results.push(await runScenario(page, scenario))
    }
    const popupPreview = await runPopupPreviewSmoke(page)
    return {
      ok: true,
      outputDir,
      results,
      popupPreview,
      auto_publish_enabled: false,
      external_actions_locked: true,
    }
  } finally {
    await browser.close()
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  runBrowserSmoke()
    .then((result) => {
      console.log(JSON.stringify(result, null, 2))
    })
    .catch((error) => {
      console.error(error)
      process.exit(1)
    })
}

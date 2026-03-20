#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, '.manager');
const PLAN_FILE = path.join(OUT_DIR, 'social-publish-plan.json');
const TASK_FILE = path.join(OUT_DIR, 'social-browser-task.json');
const TARGETS_FILE = path.join(ROOT, 'tools', 'social-browser-targets.json');
const EVIDENCE_DIR = path.join(OUT_DIR, 'evidence');
const BROWSER_USER_DATA = path.join(ROOT, '..', '..', '.openclaw', 'browser', 'openclaw', 'user-data');

const argv = process.argv.slice(2);
const command = argv[0];

function usage() {
  console.error([
    'Usage:',
    '  node tools/social-browser-adapter.mjs plan --platform x|xhs --run-id ID --topic "..." --text "..."',
    '  node tools/social-browser-adapter.mjs prepare-run [plan-file]',
    '  node tools/social-browser-adapter.mjs execute [task-file]  # Playwright 自动发布',
    '  node tools/social-browser-adapter.mjs verify --run-id ID --platform x|xhs --published --evidence share_link --url https://... ',
    '  node tools/social-browser-adapter.mjs verify --run-id ID --platform x|xhs --manual-review',
    '  node tools/social-browser-adapter.mjs simulate-publish --platform x|xhs --run-id ID --topic "..." --submitted --manual-review',
  ].join('\n'));
}

function getFlag(name, fallback = '') {
  const idx = argv.indexOf(name);
  return idx >= 0 && idx + 1 < argv.length ? String(argv[idx + 1]) : fallback;
}

function hasFlag(name) {
  return argv.includes(name);
}

function runNode(script, args) {
  const res = spawnSync(process.execPath, [script, ...args], { stdio: 'inherit' });
  process.exit(res.status ?? 0);
}

function runNodeCapture(script, args) {
  return spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeJson(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(obj, null, 2));
}

if (!command) {
  usage();
  process.exit(1);
}

if (command === 'plan') {
  runNode('tools/social-publish-plan.mjs', argv.slice(1));
}

if (command === 'prepare-run') {
  const file = argv[1] || PLAN_FILE;
  if (!fs.existsSync(file)) {
    console.error(`Missing plan file: ${file}`);
    process.exit(2);
  }
  const plan = readJson(file);
  const targets = fs.existsSync(TARGETS_FILE) ? readJson(TARGETS_FILE) : {};
  const platformTarget = targets[plan.platform] || plan.target || {};
  const task = {
    preparedAt: new Date().toISOString(),
    runId: plan.runId,
    platform: plan.platform,
    topic: plan.topic,
    composeUrl: platformTarget.composeUrl || plan.target?.composeUrl || '',
    homeUrl: platformTarget.homeUrl || '',
    steps: platformTarget.steps || plan.target?.steps || [],
    requiredEvidence: platformTarget.requiredEvidence || plan.target?.requiredEvidence || [],
    verificationHints: platformTarget.verificationHints || [],
    content: plan.content,
    browserRequirements: plan.browserRequirements || {
      preferLocalLoggedInSession: true,
      allowBrowserRelayFallback: true,
      requireSuccessEvidence: true,
    },
  };
  writeJson(TASK_FILE, task);
  console.log(JSON.stringify({ ok: true, outFile: TASK_FILE, task }, null, 2));
  process.exit(0);
}

if (command === 'verify') {
  const runId = getFlag('--run-id', `social-${Date.now()}`);
  const platform = getFlag('--platform', 'unknown');
  const topic = getFlag('--topic', '');
  if (hasFlag('--published')) {
    const evidence = getFlag('--evidence', 'manual_evidence');
    const url = getFlag('--url', '');
    runNode('tools/social-publish-log.mjs', ['state', JSON.stringify({
      runId, platform, topic: topic || null, state: 'published', status: 'ok', evidence, url: url || null, operator: 'openclaw'
    })]);
  }
  if (hasFlag('--manual-review')) {
    runNode('tools/social-publish-log.mjs', ['state', JSON.stringify({
      runId, platform, topic: topic || null, state: 'needs_manual_review', status: 'progress', detail: '浏览器执行后仍缺少强成功证据', nextAction: '人工检查主页/分享链接/发布记录', operator: 'openclaw'
    })]);
  }
  const errorType = getFlag('--error-type', '');
  if (errorType) {
    runNode('tools/social-publish-log.mjs', ['state', JSON.stringify({
      runId, platform, topic: topic || null, state: 'publish_failed', status: 'error', errorType, detail: getFlag('--detail', '发布验证失败'), nextAction: getFlag('--next-action', '检查平台页面并重试'), operator: 'openclaw'
    })]);
  }
  process.exit(0);
}

if (command === 'simulate-publish') {
  runNode('tools/social-workflow.mjs', ['publish', ...argv.slice(1)]);
}

if (command === 'execute') {
  // Playwright 自动发布：读取 task 文件，驱动浏览器完成发布
  const file = argv[1] || TASK_FILE;
  if (!fs.existsSync(file)) {
    console.error(`Missing task file: ${file}. Run prepare-run first.`);
    process.exit(2);
  }
  const task = readJson(file);
  const platform = task.platform;
  const content = task.content || {};
  const runId = task.runId || `social-${Date.now()}`;

  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

  // 动态导入 playwright-core（项目已有依赖）
  let chromium;
  try {
    const pw = await import('playwright-core');
    chromium = pw.chromium;
  } catch (e) {
    console.error('playwright-core not available. Install with: npm i playwright-core');
    process.exit(3);
  }

  // 查找 Chromium 可执行文件
  const chromePaths = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ];
  const executablePath = chromePaths.find(p => fs.existsSync(p)) || '';

  let browser, context, page;
  const result = { runId, platform, ok: false, evidence: [], errors: [] };

  try {
    // 使用已登录的 user-data 目录启动浏览器
    const launchOpts = {
      headless: false,
      args: [
        `--user-data-dir=${BROWSER_USER_DATA}`,
        '--no-first-run',
        '--disable-blink-features=AutomationControlled',
      ],
    };
    if (executablePath) launchOpts.executablePath = executablePath;

    context = await chromium.launchPersistentContext(BROWSER_USER_DATA, {
      headless: false,
      executablePath: executablePath || undefined,
      args: [
        '--no-first-run',
        '--disable-blink-features=AutomationControlled',
      ],
      viewport: { width: 1280, height: 900 },
    });
    page = context.pages()[0] || await context.newPage();

    // 记录发布开始
    logPublishState(runId, platform, task.topic, 'publish_started');

    if (platform === 'x') {
      await executeXPublish(page, task, result);
    } else if (platform === 'xhs') {
      await executeXhsPublish(page, task, result);
    } else {
      result.errors.push(`Unsupported platform: ${platform}`);
    }

    // 截图作为证据
    const screenshotPath = path.join(EVIDENCE_DIR, `${runId}-${platform}-final.png`);
    await page.screenshot({ path: screenshotPath, fullPage: false });
    result.evidence.push({ type: 'screenshot', path: screenshotPath });

  } catch (err) {
    result.errors.push(err.message || String(err));
    // 尝试截图记录错误现场
    try {
      if (page) {
        const errShot = path.join(EVIDENCE_DIR, `${runId}-${platform}-error.png`);
        await page.screenshot({ path: errShot });
        result.evidence.push({ type: 'error_screenshot', path: errShot });
      }
    } catch {}
  } finally {
    if (context) await context.close().catch(() => {});
  }

  // 根据结果记录状态
  if (result.ok) {
    logPublishState(runId, platform, task.topic, 'publish_submitted');
    logPublishState(runId, platform, task.topic, 'verify_pending');
    console.log(JSON.stringify({ ...result, state: 'verify_pending', message: '已提交，等待验证' }, null, 2));
  } else {
    logPublishState(runId, platform, task.topic, 'publish_failed', {
      errorType: 'browser_execution_failed',
      detail: result.errors.join('; '),
      nextAction: '检查截图并手动重试',
    });
    console.log(JSON.stringify({ ...result, state: 'publish_failed' }, null, 2));
  }

  // 保存执行结果
  writeJson(path.join(OUT_DIR, `execute-result-${runId}.json`), result);
  process.exit(result.ok ? 0 : 1);
}

// === 平台发布实现 ===

async function executeXPublish(page, task, result) {
  const content = task.content || {};
  const text = content.text || content.body || '';
  if (!text) { result.errors.push('No text content'); return; }

  // 打开 X 发帖页面
  await page.goto(task.composeUrl || 'https://x.com/compose/post', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);

  // 查找编辑器并输入内容
  const editor = page.locator('[data-testid="tweetTextarea_0"], [role="textbox"][data-testid]').first();
  await editor.waitFor({ state: 'visible', timeout: 15000 });
  await editor.click();
  await page.waitForTimeout(500);

  // 分段输入避免触发反自动化
  for (const line of text.split('\n')) {
    await page.keyboard.type(line, { delay: 30 });
    await page.keyboard.press('Enter');
    await page.waitForTimeout(100);
  }
  await page.waitForTimeout(1000);

  // 附加图片（如果有）
  const images = content.images || content.media || [];
  if (images.length > 0) {
    try {
      const fileInput = page.locator('input[type="file"][accept*="image"]').first();
      for (const img of images) {
        if (fs.existsSync(img)) await fileInput.setInputFiles(img);
      }
      await page.waitForTimeout(2000);
    } catch (e) {
      result.errors.push(`Image attach failed: ${e.message}`);
    }
  }

  // 点击发布按钮
  const postBtn = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first();
  await postBtn.waitFor({ state: 'visible', timeout: 10000 });
  await postBtn.click();
  await page.waitForTimeout(3000);

  // 检查是否发布成功（编辑器消失 = 成功）
  try {
    await editor.waitFor({ state: 'hidden', timeout: 10000 });
    result.ok = true;
  } catch {
    // 编辑器还在，可能发布失败
    result.errors.push('Post button clicked but composer still visible');
  }

  // 尝试获取发布后的 URL
  try {
    await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    const firstPost = page.locator('article[data-testid="tweet"]').first();
    const link = await firstPost.locator('a[href*="/status/"]').first().getAttribute('href');
    if (link) {
      result.postUrl = `https://x.com${link}`;
      result.evidence.push({ type: 'share_link', url: result.postUrl });
    }
  } catch {}
}

async function executeXhsPublish(page, task, result) {
  const content = task.content || {};
  const title = content.title || '';
  const body = content.body || content.text || '';
  if (!body) { result.errors.push('No body content'); return; }

  // 打开小红书创作者发布页
  await page.goto(task.composeUrl || 'https://creator.xiaohongshu.com/publish/publish', {
    waitUntil: 'domcontentloaded', timeout: 30000,
  });
  await page.waitForTimeout(3000);

  // 附加图片（小红书要求至少一张图）
  const images = content.images || content.media || [];
  if (images.length > 0) {
    try {
      const fileInput = page.locator('input[type="file"]').first();
      const validImages = images.filter(img => fs.existsSync(img));
      if (validImages.length > 0) {
        await fileInput.setInputFiles(validImages);
        await page.waitForTimeout(3000);
      }
    } catch (e) {
      result.errors.push(`Image upload failed: ${e.message}`);
    }
  }

  // 填写标题
  if (title) {
    try {
      const titleInput = page.locator('#title, input[placeholder*="标题"], [class*="title"] input').first();
      await titleInput.waitFor({ state: 'visible', timeout: 8000 });
      await titleInput.click();
      await page.keyboard.type(title, { delay: 20 });
      await page.waitForTimeout(500);
    } catch (e) {
      result.errors.push(`Title input failed: ${e.message}`);
    }
  }

  // 填写正文
  try {
    const bodyEditor = page.locator('#post-textarea, [contenteditable="true"], [class*="editor"] [contenteditable]').first();
    await bodyEditor.waitFor({ state: 'visible', timeout: 8000 });
    await bodyEditor.click();
    await page.waitForTimeout(300);
    for (const line of body.split('\n')) {
      await page.keyboard.type(line, { delay: 20 });
      await page.keyboard.press('Enter');
      await page.waitForTimeout(50);
    }
    await page.waitForTimeout(1000);
  } catch (e) {
    result.errors.push(`Body input failed: ${e.message}`);
    return;
  }

  // 点击发布按钮
  try {
    const publishBtn = page.locator('button:has-text("发布"), button:has-text("Publish"), [class*="publish"] button').first();
    await publishBtn.waitFor({ state: 'visible', timeout: 8000 });
    await publishBtn.click();
    await page.waitForTimeout(5000);

    // 检查是否跳转到成功页面或出现成功提示
    const url = page.url();
    if (url.includes('/creator/home') || url.includes('success')) {
      result.ok = true;
    } else {
      // 检查是否有成功提示
      const successText = await page.locator('text=发布成功, text=已发布').first().isVisible().catch(() => false);
      result.ok = !!successText;
    }
  } catch (e) {
    result.errors.push(`Publish click failed: ${e.message}`);
  }
}

function logPublishState(runId, platform, topic, state, extra = {}) {
  const payload = { runId, platform, topic: topic || null, state, operator: 'openclaw', ...extra };
  runNodeCapture('tools/social-publish-log.mjs', ['state', JSON.stringify(payload)]);
}

usage();
process.exit(1);

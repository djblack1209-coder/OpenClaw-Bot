#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, '.manager');
const PLAN_FILE = path.join(OUT_DIR, 'social-publish-plan.json');
const TASK_FILE = path.join(OUT_DIR, 'social-browser-task.json');
const TARGETS_FILE = path.join(ROOT, 'tools', 'social-browser-targets.json');

const argv = process.argv.slice(2);
const command = argv[0];

function usage() {
  console.error([
    'Usage:',
    '  node tools/social-browser-adapter.mjs plan --platform x|xhs --run-id ID --topic "..." --text "..."',
    '  node tools/social-browser-adapter.mjs prepare-run [plan-file]',
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

usage();
process.exit(1);

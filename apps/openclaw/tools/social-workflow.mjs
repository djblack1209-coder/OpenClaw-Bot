#!/usr/bin/env node
import { spawnSync } from 'node:child_process';

const argv = process.argv.slice(2);
const command = argv[0];

function usage() {
  console.error([
    'Usage:',
    '  node tools/social-workflow.mjs score --platform x|xhs "topic a" "topic b"',
    '  node tools/social-workflow.mjs plan --platform x|xhs "topic a" "topic b"',
    '  node tools/social-workflow.mjs preflight --platform x|xhs [--title ...] --text ...',
    '  node tools/social-workflow.mjs preflight-log --platform x|xhs --run-id ID [--title ...] --text ...',
    '  node tools/social-workflow.mjs draft-log --platform x|xhs --topic "..." [--run-id ID]',
    '  node tools/social-workflow.mjs publish-log --platform x|xhs --topic "..." --state publish_started [--run-id ID]',
    '  node tools/social-workflow.mjs publish --platform x|xhs --topic "..." --run-id ID [--submitted] [--published --evidence share_link --url https://...] [--manual-review] [--error-type submit_failed --detail ... --next-action ...]',
    '  node tools/social-workflow.mjs log state "{...json...}"',
    '  node tools/social-workflow.mjs hotspot --platform all|xhs|x [--min-score 7]',
    '  node tools/social-workflow.mjs interact --platform xhs|x --post-id ID',
    '  node tools/social-workflow.mjs scout --platform xhs|x [--category S|A|B]',
    '  node tools/social-workflow.mjs full-cycle --platform xhs|x --topic "..." --run-id ID --title "..." --text "..."',
  ].join('\n'));
}

function runCapture(script, args) {
  return spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
}

function runNode(script, args) {
  const res = spawnSync(process.execPath, [script, ...args], { stdio: 'inherit' });
  process.exit(res.status ?? 0);
}

function getFlag(name, args, fallback = '') {
  const idx = args.indexOf(name);
  if (idx >= 0 && idx + 1 < args.length) return args[idx + 1];
  return fallback;
}

function hasFlag(name, args) {
  return args.includes(name);
}

function statePayload(args, fallbackState, extra = {}) {
  const platform = getFlag('--platform', args, 'unknown');
  const topic = getFlag('--topic', args, '');
  const state = getFlag('--state', args, fallbackState);
  const runId = getFlag('--run-id', args, `social-${Date.now()}`);
  return {
    runId,
    platform,
    topic: topic || null,
    state,
    operator: 'openclaw',
    ...extra,
  };
}

function logState(payload) {
  const res = runCapture('tools/social-publish-log.mjs', ['state', JSON.stringify(payload)]);
  if (res.stdout) process.stdout.write(res.stdout);
  if (res.stderr) process.stderr.write(res.stderr);
  return res.status ?? 0;
}

function cmdPreflightLog(args) {
  const runId = getFlag('--run-id', args, `social-${Date.now()}`);
  const platform = getFlag('--platform', args, 'generic');
  const topic = getFlag('--topic', args, '');
  const res = runCapture('tools/social-publish-preflight.mjs', args);
  if (res.stdout) process.stdout.write(res.stdout);
  if (res.stderr) process.stderr.write(res.stderr);

  let parsed = null;
  try {
    parsed = JSON.parse(res.stdout || '{}');
  } catch {}

  if (res.status === 0 && parsed?.ok) {
    return logState({ runId, platform, topic: topic || null, state: 'preflight_passed', operator: 'openclaw' });
  }

  const detail = parsed?.checks?.issues?.join('; ') || 'preflight failed';
  return logState({
    runId,
    platform,
    topic: topic || null,
    state: 'publish_failed',
    status: 'error',
    errorType: 'draft_invalid',
    detail,
    nextAction: '修正文案/素材后重新 preflight',
    operator: 'openclaw',
  }) || (res.status ?? 2);
}

function cmdPublish(args) {
  const runId = getFlag('--run-id', args, `social-${Date.now()}`);
  const platform = getFlag('--platform', args, 'unknown');
  const topic = getFlag('--topic', args, '');
  const evidence = getFlag('--evidence', args, '');
  const url = getFlag('--url', args, '');
  const errorType = getFlag('--error-type', args, 'submit_failed');
  const detail = getFlag('--detail', args, '发布执行失败');
  const nextAction = getFlag('--next-action', args, '检查页面状态并重试');

  const stages = [];
  stages.push(logState({ runId, platform, topic: topic || null, state: 'publish_started', operator: 'openclaw' }));

  if (hasFlag('--submitted', args)) {
    stages.push(logState({ runId, platform, topic: topic || null, state: 'publish_submitted', operator: 'openclaw' }));
    stages.push(logState({ runId, platform, topic: topic || null, state: 'verify_pending', operator: 'openclaw' }));
  }

  if (hasFlag('--published', args)) {
    stages.push(logState({
      runId,
      platform,
      topic: topic || null,
      state: 'published',
      status: 'ok',
      evidence: evidence || 'manual_evidence',
      url: url || null,
      operator: 'openclaw',
    }));
    return stages.find(code => code !== 0) || 0;
  }

  if (hasFlag('--manual-review', args)) {
    stages.push(logState({
      runId,
      platform,
      topic: topic || null,
      state: 'needs_manual_review',
      status: 'progress',
      detail: '已提交但缺少成功证据',
      nextAction: '人工检查帖子是否可见或补抓分享链接',
      operator: 'openclaw',
    }));
    return stages.find(code => code !== 0) || 0;
  }

  stages.push(logState({
    runId,
    platform,
    topic: topic || null,
    state: 'publish_failed',
    status: 'error',
    errorType,
    detail,
    nextAction,
    operator: 'openclaw',
  }));
  return stages.find(code => code !== 0) || 0;
}

if (!command) {
  usage();
  process.exit(1);
}

if (command === 'score') runNode('tools/social-topic-scorer.mjs', argv.slice(1));
if (command === 'plan') runNode('tools/social-topic-scorer.mjs', [...argv.slice(1), '--explain']);
if (command === 'preflight') runNode('tools/social-publish-preflight.mjs', argv.slice(1));
if (command === 'preflight-log') process.exit(cmdPreflightLog(argv.slice(1)));
if (command === 'log') runNode('tools/social-publish-log.mjs', argv.slice(1));
if (command === 'draft-log') process.exit(logState(statePayload(argv.slice(1), 'draft_ready')));
if (command === 'publish-log') process.exit(logState(statePayload(argv.slice(1), 'publish_started')));
if (command === 'publish') process.exit(cmdPublish(argv.slice(1)));
if (command === 'hotspot') runNode('tools/social-hotspot-monitor.mjs', argv.slice(1));
if (command === 'interact') runNode('tools/social-comment-engine.mjs', ['reply', ...argv.slice(1)]);
if (command === 'scout') runNode('tools/social-comment-engine.mjs', ['scout', ...argv.slice(1)]);
if (command === 'full-cycle') {
  // 完整发布周期：预检 -> 浏览器自动发布 -> 启动互动调度
  const args = argv.slice(1);
  const runId = getFlag('--run-id', args, `social-${Date.now()}`);
  const platform = getFlag('--platform', args, 'xhs');
  const useBrowser = hasFlag('--auto-browser', args);

  // Step 1: preflight
  const preflightCode = cmdPreflightLog(args);
  if (preflightCode !== 0) {
    console.error('Preflight failed, aborting full-cycle.');
    process.exit(preflightCode);
  }

  // Step 2: publish
  let publishCode;
  if (useBrowser) {
    // 使用 Playwright 自动发布：先 prepare-run，再 execute
    const prepRes = runCapture('tools/social-browser-adapter.mjs', ['prepare-run']);
    if (prepRes.status !== 0) {
      console.error('prepare-run failed:', prepRes.stderr);
      process.exit(prepRes.status ?? 2);
    }
    const execRes = runCapture('tools/social-browser-adapter.mjs', ['execute']);
    if (execRes.stdout) process.stdout.write(execRes.stdout);
    if (execRes.stderr) process.stderr.write(execRes.stderr);
    publishCode = execRes.status ?? 1;

    // 如果浏览器执行成功，尝试提取 postUrl 并记录
    if (publishCode === 0) {
      try {
        const execResult = JSON.parse(execRes.stdout || '{}');
        if (execResult.postUrl) {
          logState({
            runId, platform, topic: getFlag('--topic', args, '') || null,
            state: 'published', status: 'ok',
            evidence: 'browser_auto', url: execResult.postUrl,
            operator: 'openclaw',
          });
        }
      } catch {}
    }
  } else {
    // 回退：标记为需要手动浏览器执行
    publishCode = cmdPublish([...args, '--submitted', '--manual-review']);
  }
  
  // Step 3: generate interaction schedule
  const scheduleRes = runCapture('tools/social-comment-engine.mjs', ['schedule', '--platform', platform, '--post-id', runId]);
  if (scheduleRes.stdout) process.stdout.write('\n--- Interaction Schedule ---\n' + scheduleRes.stdout);

  process.exit(publishCode);
}

usage();
process.exit(1);

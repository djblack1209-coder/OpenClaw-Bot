#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, '.manager');
const outFile = path.join(OUT_DIR, 'social-publish-plan.json');

const argv = process.argv.slice(2);

function getFlag(name, fallback = '') {
  const idx = argv.indexOf(name);
  return idx >= 0 && idx + 1 < argv.length ? String(argv[idx + 1]) : fallback;
}

function splitCsv(value) {
  return String(value || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
}

const platform = getFlag('--platform', 'unknown').toLowerCase();
const runId = getFlag('--run-id', `social-${Date.now()}`);
const topic = getFlag('--topic', '');
const title = getFlag('--title', '');
const text = getFlag('--text', '');
const tags = splitCsv(getFlag('--tags', ''));
const images = splitCsv(getFlag('--images', ''));
const thread = getFlag('--thread', '');

if (!platform || platform === 'unknown') {
  console.error('Usage: node tools/social-publish-plan.mjs --platform x|xhs --run-id ID --topic "..." [--title "..."] --text "..." [--tags a,b] [--images p1,p2] [--thread c1|||c2]');
  process.exit(1);
}

const threadParts = thread ? thread.split('|||').map(s => s.trim()).filter(Boolean) : [];
const now = new Date().toISOString();

const targets = {
  x: {
    composeUrl: 'https://x.com/compose/post',
    requiredEvidence: ['share_link', 'post_visible', 'success_toast'],
    steps: [
      'open_compose',
      'fill_main_text',
      'attach_media_if_any',
      'submit_post',
      'capture_success_evidence',
      'optionally_publish_thread_replies',
    ],
  },
  xhs: {
    composeUrl: 'https://creator.xiaohongshu.com/publish/publish',
    requiredEvidence: ['note_visible', 'publish_success', 'note_link'],
    steps: [
      'open_publish_page',
      'fill_title',
      'fill_body',
      'attach_images_if_any',
      'set_tags_if_supported',
      'submit_note',
      'capture_success_evidence',
    ],
  },
};

const target = targets[platform] || {
  composeUrl: '',
  requiredEvidence: ['manual_evidence'],
  steps: ['open_target_page', 'fill_content', 'submit', 'capture_evidence'],
};

const plan = {
  generatedAt: now,
  runId,
  platform,
  topic,
  content: {
    title: title || null,
    text,
    tags,
    images,
    threadParts,
  },
  target,
  stateMachine: [
    'draft_ready',
    'preflight_passed',
    'publish_started',
    'publish_submitted',
    'verify_pending',
    'published|publish_failed|needs_manual_review',
  ],
  browserRequirements: {
    preferLocalLoggedInSession: true,
    allowBrowserRelayFallback: true,
    requireSuccessEvidence: true,
  },
};

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(outFile, JSON.stringify(plan, null, 2));
console.log(JSON.stringify({ ok: true, outFile, plan }, null, 2));

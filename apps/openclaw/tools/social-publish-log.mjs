#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const MEMORY_DIR = path.join(ROOT, 'memory');
const file = path.join(MEMORY_DIR, 'social-publish-runs.jsonl');
const action = process.argv[2] || 'state';
const payloadRaw = process.argv.slice(3).join(' ');

const VALID_STATES = new Set([
  'idea_selected',
  'draft_ready',
  'preflight_passed',
  'publish_started',
  'publish_submitted',
  'verify_pending',
  'published',
  'publish_failed',
  'needs_manual_review',
]);

if (action !== 'state') {
  console.error('Usage: node tools/social-publish-log.mjs state <json-payload>');
  process.exit(1);
}

let payload = {};
try {
  payload = payloadRaw ? JSON.parse(payloadRaw) : {};
} catch (err) {
  console.error('Invalid JSON payload:', String(err));
  process.exit(2);
}

if (!payload.state || !VALID_STATES.has(payload.state)) {
  console.error(`Invalid or missing state. Valid states: ${Array.from(VALID_STATES).join(', ')}`);
  process.exit(3);
}

const event = {
  ts: payload.ts || new Date().toISOString(),
  runId: payload.runId || `social-${Date.now()}`,
  platform: payload.platform || 'unknown',
  topic: payload.topic || null,
  state: payload.state,
  status: payload.status || (payload.state === 'published' ? 'ok' : payload.state === 'publish_failed' ? 'error' : 'progress'),
  evidence: payload.evidence || null,
  url: payload.url || null,
  errorType: payload.errorType || null,
  detail: payload.detail || null,
  nextAction: payload.nextAction || null,
  operator: payload.operator || 'openclaw',
};

fs.mkdirSync(MEMORY_DIR, { recursive: true });
fs.appendFileSync(file, JSON.stringify(event) + '\n');
console.log(JSON.stringify({ ok: true, file, event }, null, 2));

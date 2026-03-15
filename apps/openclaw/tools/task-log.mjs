#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const MEMORY_DIR = path.join(ROOT, 'memory');

const MAP = {
  task: 'task-runs.jsonl',
  failure: 'failures.jsonl',
  retrieval: 'retrieval-runs.jsonl',
};

const ENUMS = {
  taskStatus: new Set(['ok', 'error', 'partial', 'running', 'queued', 'skipped', 'cancelled']),
  retrievalQuality: new Set(['good', 'weak', 'miss']),
};

const USAGE = [
  'Usage:',
  '  node tools/task-log.mjs <task|failure|retrieval> <json-payload>',
  '  node tools/task-log.mjs validate <task|failure|retrieval> [file]',
].join('\n');

function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function toCleanString(value, max = 2000) {
  if (value == null) return undefined;
  const text = String(value)
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return undefined;
  return text.slice(0, max);
}

function toStringArray(value, maxItems = 50, itemMax = 300) {
  if (value == null) return undefined;
  const list = Array.isArray(value) ? value : [value];
  const out = [];
  for (const item of list) {
    const cleaned = toCleanString(item, itemMax);
    if (cleaned) out.push(cleaned);
    if (out.length >= maxItems) break;
  }
  return out.length ? out : undefined;
}

function toInteger(value) {
  if (value == null || value === '') return undefined;
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return undefined;
  return Math.round(num);
}

function normalizeTs(value) {
  if (!value) return new Date().toISOString();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error('Field "ts" must be a valid ISO timestamp or Date-parsable string');
  }
  return date.toISOString();
}

function pickCommon(input) {
  const out = {};
  out.ts = normalizeTs(input.ts);

  const taskId = toCleanString(input.taskId, 200);
  const sessionId = toCleanString(input.sessionId, 200);
  const taskType = toCleanString(input.taskType, 120);
  const status = toCleanString(input.status, 40);
  const notes = toCleanString(input.notes, 4000);

  if (taskId) out.taskId = taskId;
  if (sessionId) out.sessionId = sessionId;
  if (taskType) out.taskType = taskType;
  if (status) out.status = status;
  if (notes) out.notes = notes;

  return out;
}

function ensureRequired(record, fields, kind) {
  const missing = fields.filter(field => record[field] == null || record[field] === '');
  if (missing.length) {
    throw new Error(`Missing required ${kind} field(s): ${missing.join(', ')}`);
  }
}

function validateEnum(value, allowed, field) {
  if (value == null) return;
  if (!allowed.has(value)) {
    throw new Error(`Field "${field}" must be one of: ${[...allowed].join(', ')}`);
  }
}

function normalizeTask(input) {
  const record = pickCommon(input);
  record.status = record.status || 'ok';
  validateEnum(record.status, ENUMS.taskStatus, 'status');

  const inputSummary = toCleanString(input.inputSummary, 2000);
  const usedSkill = toCleanString(input.usedSkill, 120);
  const usedUsecase = toCleanString(input.usedUsecase, 200);
  const tools = toStringArray(input.tools, 40, 120);
  const outputs = toStringArray(input.outputs, 20, 300);
  const warnings = toStringArray(input.warnings, 20, 300);
  const tags = toStringArray(input.tags, 20, 80);
  const durationMs = toInteger(input.durationMs);
  const itemCount = toInteger(input.itemCount);

  if (inputSummary) record.inputSummary = inputSummary;
  if (usedSkill) record.usedSkill = usedSkill;
  if (usedUsecase) record.usedUsecase = usedUsecase;
  if (tools) record.tools = tools;
  if (outputs) record.outputs = outputs;
  if (warnings) record.warnings = warnings;
  if (tags) record.tags = tags;
  if (durationMs != null) record.durationMs = durationMs;
  if (itemCount != null) record.itemCount = itemCount;

  ensureRequired(record, ['taskType'], 'task');
  return record;
}

function normalizeFailure(input) {
  const record = pickCommon(input);
  record.status = record.status || 'error';
  validateEnum(record.status, new Set(['error', 'partial', 'cancelled', 'skipped']), 'status');

  const errorType = toCleanString(input.errorType, 120);
  const detail = toCleanString(input.detail, 4000);
  const nextAction = toCleanString(input.nextAction, 1000);
  const failedTool = toCleanString(input.failedTool, 120);
  const retryable = typeof input.retryable === 'boolean' ? input.retryable : undefined;
  const durationMs = toInteger(input.durationMs);
  const tools = toStringArray(input.tools, 40, 120);
  const warnings = toStringArray(input.warnings, 20, 300);

  if (errorType) record.errorType = errorType;
  if (detail) record.detail = detail;
  if (nextAction) record.nextAction = nextAction;
  if (failedTool) record.failedTool = failedTool;
  if (retryable != null) record.retryable = retryable;
  if (durationMs != null) record.durationMs = durationMs;
  if (tools) record.tools = tools;
  if (warnings) record.warnings = warnings;

  ensureRequired(record, ['taskType', 'detail'], 'failure');
  return record;
}

function normalizeRetrieval(input) {
  const record = pickCommon(input);
  record.status = record.status || 'ok';
  validateEnum(record.status, new Set(['ok', 'partial', 'error']), 'status');

  const query = toCleanString(input.query, 2000);
  const rewrittenQuery = toCleanString(input.rewrittenQuery, 2000);
  const sources = toStringArray(input.sources, 100, 300);
  const topHits = toStringArray(input.topHits, 100, 300);
  const quality = toCleanString(input.quality, 20);
  const retrievalMs = toInteger(input.retrievalMs);
  const hitCount = toInteger(input.hitCount ?? (Array.isArray(input.topHits) ? input.topHits.length : undefined));
  const indexVersion = toCleanString(input.indexVersion, 120);

  if (query) record.query = query;
  if (rewrittenQuery) record.rewrittenQuery = rewrittenQuery;
  if (sources) record.sources = sources;
  if (topHits) record.topHits = topHits;
  if (quality) record.quality = quality;
  if (retrievalMs != null) record.retrievalMs = retrievalMs;
  if (hitCount != null) record.hitCount = hitCount;
  if (indexVersion) record.indexVersion = indexVersion;

  validateEnum(record.quality, ENUMS.retrievalQuality, 'quality');
  ensureRequired(record, ['query'], 'retrieval');
  return record;
}

function normalizeRecord(kind, input) {
  if (!isPlainObject(input)) {
    throw new Error('JSON payload must be an object');
  }

  if (kind === 'task') return normalizeTask(input);
  if (kind === 'failure') return normalizeFailure(input);
  if (kind === 'retrieval') return normalizeRetrieval(input);
  throw new Error(`Unsupported log kind: ${kind}`);
}

function appendRecord(kind, input) {
  const record = normalizeRecord(kind, input);
  fs.mkdirSync(MEMORY_DIR, { recursive: true });
  const file = path.join(MEMORY_DIR, MAP[kind]);
  fs.appendFileSync(file, JSON.stringify(record) + '\n');
  return { file, record };
}

function validateFile(kind, targetFile) {
  const file = targetFile || path.join(MEMORY_DIR, MAP[kind]);
  if (!fs.existsSync(file)) {
    throw new Error(`Missing file: ${file}`);
  }

  const text = fs.readFileSync(file, 'utf8');
  const lines = text.split(/\r?\n/);
  let checked = 0;
  let skipped = 0;

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    let parsed;
    try {
      parsed = JSON.parse(trimmed);
    } catch (err) {
      throw new Error(`Line ${index + 1}: invalid JSON (${String(err)})`);
    }

    if (parsed && parsed._comment) {
      skipped += 1;
      return;
    }

    normalizeRecord(kind, parsed);
    checked += 1;
  });

  return { file, checked, skipped };
}

function parsePayload(raw) {
  try {
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    throw new Error(`Invalid JSON payload: ${String(err)}`);
  }
}

function main() {
  const command = process.argv[2];

  if (command === 'validate') {
    const kind = process.argv[3];
    const file = process.argv[4];
    if (!MAP[kind]) {
      console.error(USAGE);
      process.exit(1);
    }
    try {
      const result = validateFile(kind, file);
      console.log(`Validated ${kind} log: ${result.file} (records=${result.checked}, comments=${result.skipped})`);
    } catch (err) {
      console.error(String(err.message || err));
      process.exit(4);
    }
    return;
  }

  const kind = command;
  const payloadRaw = process.argv.slice(3).join(' ');
  if (!MAP[kind]) {
    console.error(USAGE);
    process.exit(1);
  }

  try {
    const payload = parsePayload(payloadRaw);
    const { file, record } = appendRecord(kind, payload);
    console.log(`Appended ${kind} log -> ${file}`);
    console.log(JSON.stringify(record));
  } catch (err) {
    console.error(String(err.message || err));
    process.exit(2);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}

export { MAP, normalizeRecord, appendRecord, validateFile };

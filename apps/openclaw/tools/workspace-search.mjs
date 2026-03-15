#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { appendRecord } from './task-log.mjs';

const ROOT = process.cwd();
const INDEX_FILE = path.join(ROOT, '.manager', 'workspace-index.json');

function parseArgs(argv) {
  const args = { top: 8, log: false, json: false, all: false, query: '', taskId: '', sessionId: '' };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--log') args.log = true;
    else if (a === '--json') args.json = true;
    else if (a === '--all') args.all = true;
    else if (a === '--top') args.top = Math.max(1, Number(argv[++i] || 8));
    else if (a === '--task-id') args.taskId = String(argv[++i] || '');
    else if (a === '--session-id') args.sessionId = String(argv[++i] || '');
    else rest.push(a);
  }
  args.query = rest.join(' ').trim();
  return args;
}

function normalize(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[“”‘’'"`]/g, ' ')
    .replace(/[^\u0000-\u007F\p{L}\p{N}_\-\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokenize(text) {
  const norm = normalize(text);
  if (!norm) return [];
  return norm.split(' ').filter(Boolean);
}

function expandTokens(tokens) {
  const syn = {
    social: ['x', 'xiaohongshu', 'content'],
    xhs: ['xiaohongshu', 'social'],
    rag: ['retrieval', 'search', 'index'],
    retrieval: ['rag', 'search'],
    search: ['retrieval', 'rag'],
    log: ['logging', 'task', 'failure'],
    logging: ['log', 'task'],
    memory: ['journal', 'memo'],
    ops: ['run', 'failure', 'log'],
    skill: ['skills'],
    usecase: ['usecases']
  };
  const out = new Set(tokens);
  for (const t of tokens) {
    (syn[t] || []).forEach(v => out.add(v));
  }
  return [...out];
}

function countOccurrences(haystack, needle) {
  if (!haystack || !needle) return 0;
  return haystack.split(needle).length - 1;
}

function sourceBoost(source) {
  if (source === 'knowledge') return 8;
  if (source === 'memory') return 4;
  if (source === 'journal') return 1;
  if (source === 'ops') return -6;
  return 0;
}

function pathBoost(p) {
  if (p.startsWith('usecases/')) return 6;
  if (p.startsWith('skills/')) return 5;
  if (p === 'MEMORY.md') return 5;
  if (['TOOLS.md', 'USER.md', 'SOUL.md', 'AGENTS.md', 'TELEGRAM_COMMANDS.md'].includes(p)) return 4;
  if (p.startsWith('memory/')) return 1;
  return 0;
}

function classifyIntent(tokens, queryNorm) {
  if (tokens.some(t => ['error', 'failure', 'incident', 'timeout', 'bug', 'ops'].includes(t))) return 'ops';
  if (tokens.some(t => ['memory', 'journal', 'remember', 'history'].includes(t))) return 'memory';
  if (tokens.some(t => ['skill', 'skills', 'usecase', 'usecases', 'workflow', 'rag', 'retrieval', 'search', 'index'].includes(t))) return 'knowledge';
  if (/jsonl|task[- ]?runs|retrieval[- ]?runs|failures/.test(queryNorm)) return 'ops';
  return 'general';
}

function intentSourceBoost(intent, source, pathText) {
  if (intent === 'ops') {
    if (source === 'ops') return 7;
    if (source === 'journal') return 2;
    return 0;
  }
  if (intent === 'memory') {
    if (source === 'memory') return 5;
    if (source === 'journal') return 4;
    if (pathText === 'memory md') return 4;
    return 0;
  }
  if (intent === 'knowledge') {
    if (source === 'knowledge') return 6;
    if (source === 'ops') return -8;
    return 0;
  }
  return 0;
}

function scoreChunk(query, tokens, chunk, intent) {
  const pathText = normalize(chunk.path || '');
  const bodyText = normalize(chunk.text || '');
  const titleText = normalize([chunk.title, chunk.sectionTitle].filter(Boolean).join(' '));
  const lead = bodyText.slice(0, 320);
  let score = 0;
  const reasons = [];

  if (query && bodyText.includes(query)) {
    score += 18;
    reasons.push('exact-body');
  }
  if (query && (pathText.includes(query) || titleText.includes(query))) {
    score += 20;
    reasons.push('exact-title-or-path');
  }

  for (const token of tokens) {
    if (!token) continue;
    const pathMatches = countOccurrences(pathText, token);
    const titleMatches = countOccurrences(titleText, token);
    const bodyMatches = countOccurrences(bodyText, token);
    const leadMatches = countOccurrences(lead, token);
    if (pathMatches) reasons.push(`path:${token}`);
    if (titleMatches) reasons.push(`title:${token}`);
    score += pathMatches * 6;
    score += titleMatches * 5;
    score += Math.min(bodyMatches, 8);
    score += leadMatches * 2;
  }

  const sb = sourceBoost(chunk.source || 'reference');
  const pb = pathBoost(chunk.path || '');
  const ib = intentSourceBoost(intent, chunk.source || 'reference', pathText);
  score += sb + pb + ib;

  if (sb) reasons.push(`source:${chunk.source}`);
  if (pb) reasons.push('path-boost');
  if (ib) reasons.push(`intent:${intent}`);

  if ((chunk.fileType || '') === 'jsonl') score -= 2;
  if ((chunk.chars || 0) > 1800) score -= 2;
  if ((chunk.source || '') === 'ops' && intent !== 'ops' && !/jsonl|task|failure|retrieval/.test(query)) score -= 6;

  return { score, reasons: [...new Set(reasons)] };
}

function dedupeHits(hits, top) {
  const seenPaths = new Map();
  const out = [];
  for (const hit of hits) {
    const count = seenPaths.get(hit.path) || 0;
    if (count >= 2) continue;
    seenPaths.set(hit.path, count + 1);
    out.push(hit);
    if (out.length >= top) break;
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
if (!args.query) {
  console.error('Usage: node tools/workspace-search.mjs [--top N] [--log] [--json] [--all] [--task-id ID] [--session-id ID] <query>');
  process.exit(1);
}
if (!fs.existsSync(INDEX_FILE)) {
  console.error(`Missing index: ${INDEX_FILE}`);
  process.exit(2);
}

const queryNorm = normalize(args.query);
const tokens = expandTokens(tokenize(args.query));
const intent = classifyIntent(tokens, queryNorm);
const data = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
const scored = (data.files || [])
  .filter(r => r && r.text && !r.error)
  .map(r => {
    const { score, reasons } = scoreChunk(queryNorm, tokens, r, intent);
    return { ...r, score, reasons };
  })
  .filter(r => r.score > 0)
  .sort((a, b) => b.score - a.score);

const selected = args.all ? scored.slice(0, args.top) : dedupeHits(scored, args.top);
const hits = selected.map(r => ({
  path: r.path,
  chunkId: r.chunkId,
  score: r.score,
  source: r.source,
  title: r.title,
  sectionTitle: r.sectionTitle,
  startLine: r.startLine,
  endLine: r.endLine,
  reasons: r.reasons,
  preview: r.text.slice(0, 240).replace(/\s+/g, ' ').trim(),
}));

const quality = !hits.length ? 'miss' : hits[0].score >= 20 ? 'good' : 'weak';
const result = { query: args.query, normalized: queryNorm, intent, hits };
if (args.log) {
  appendRecord('retrieval', {
    taskId: args.taskId || undefined,
    sessionId: args.sessionId || undefined,
    taskType: 'workspace_search',
    status: 'ok',
    query: args.query,
    rewrittenQuery: queryNorm,
    sources: [...new Set(hits.map(h => h.path))],
    topHits: hits.map(h => h.chunkId),
    hitCount: hits.length,
    quality,
    indexVersion: data.indexedAt,
    notes: `intent=${intent}`
  });
}

if (args.json) console.log(JSON.stringify(result, null, 2));
else {
  console.log(`Query: ${args.query}`);
  console.log(`Intent: ${intent}`);
  hits.forEach((h, i) => {
    console.log(`\n[${i + 1}] ${h.path} (${h.chunkId}) score=${h.score} source=${h.source}`);
    console.log(`    title: ${h.sectionTitle || h.title || '-'} lines=${h.startLine}-${h.endLine}`);
    console.log(`    why: ${h.reasons.join(', ') || 'keyword'}`);
    console.log(`    ${h.preview}`);
  });
}

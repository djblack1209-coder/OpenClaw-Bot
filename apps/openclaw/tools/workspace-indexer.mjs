#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, '.manager');
const OUT_FILE = path.join(OUT_DIR, 'workspace-index.json');

const INCLUDE_DIRS = ['skills', 'usecases', 'memory'];
const INCLUDE_FILES = ['MEMORY.md', 'TOOLS.md', 'USER.md', 'SOUL.md', 'AGENTS.md', 'TELEGRAM_COMMANDS.md'];
const MAX_BYTES = 80_000;
const TARGET_CHARS = 1200;
const MIN_CHARS = 400;
const JSONL_GROUP_LINES = 12;

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

function normalizeWhitespace(text) {
  return String(text || '').replace(/\r\n/g, '\n');
}

function countLines(text) {
  if (!text) return 0;
  return text.split('\n').length;
}

function detectFileType(rel) {
  if (/\.jsonl$/i.test(rel)) return 'jsonl';
  if (/\.json$/i.test(rel)) return 'json';
  if (/\.md$/i.test(rel)) return 'markdown';
  return 'text';
}

function classifySource(rel) {
  if (rel.startsWith('skills/') || rel.startsWith('usecases/')) return 'knowledge';
  if (['MEMORY.md', 'TOOLS.md', 'USER.md', 'SOUL.md', 'AGENTS.md', 'TELEGRAM_COMMANDS.md'].includes(rel)) return 'knowledge';
  if (rel.startsWith('memory/')) {
    if (/\/(?:task-runs|failures|retrieval-runs)\.jsonl$/i.test(rel) || /heartbeat-state\.json$/i.test(rel)) return 'ops';
    if (/memory\/\d{4}-\d{2}-\d{2}\.md$/i.test(rel)) return 'journal';
    return 'memory';
  }
  return 'reference';
}

function inferTitle(rel, text) {
  const firstNonEmpty = normalizeWhitespace(text)
    .split('\n')
    .map(line => line.trim())
    .find(Boolean);
  if (firstNonEmpty?.startsWith('#')) return firstNonEmpty.replace(/^#+\s*/, '').trim();
  return path.basename(rel);
}

function chunkPlainText(text, startLine = 1, maxChars = TARGET_CHARS) {
  const lines = normalizeWhitespace(text).split('\n');
  const chunks = [];
  let current = [];
  let currentStart = startLine;
  let chars = 0;

  function flush(endLine) {
    const body = current.join('\n').trim();
    if (!body) return;
    chunks.push({
      text: body,
      startLine: currentStart,
      endLine,
    });
    current = [];
    chars = 0;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = startLine + i;
    const nextChars = chars + line.length + 1;
    const shouldSplit = current.length > 0 && nextChars > maxChars && chars >= MIN_CHARS;
    if (shouldSplit) {
      flush(lineNo - 1);
      currentStart = lineNo;
    }
    if (!current.length) currentStart = lineNo;
    current.push(line);
    chars += line.length + 1;
  }

  if (current.length) flush(startLine + lines.length - 1);
  return chunks;
}

function chunkMarkdown(text) {
  const lines = normalizeWhitespace(text).split('\n');
  const sections = [];
  let current = null;

  function startSection(title, headingLevel, lineNo) {
    if (current) current.endLine = lineNo - 1;
    current = {
      title,
      headingLevel,
      startLine: lineNo,
      endLine: lineNo,
      lines: [],
    };
    sections.push(current);
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;
    const m = line.match(/^(#{1,6})\s+(.*)$/);
    if (m) startSection(m[2].trim(), m[1].length, lineNo);
    if (!current) startSection('Intro', 0, 1);
    current.lines.push(line);
    current.endLine = lineNo;
  }

  return sections.flatMap((section, idx) => {
    const sectionText = section.lines.join('\n').trim();
    const plainChunks = chunkPlainText(sectionText, section.startLine, TARGET_CHARS);
    return plainChunks.map((chunk, localIdx) => ({
      ...chunk,
      title: section.title || `Section ${idx + 1}`,
      headingLevel: section.headingLevel,
      sectionIndex: idx,
      sectionChunkIndex: localIdx,
    }));
  });
}

function chunkJsonl(text) {
  const lines = normalizeWhitespace(text)
    .split('\n')
    .map(line => line.trimEnd());
  const chunks = [];
  let start = 0;

  while (start < lines.length) {
    const slice = lines.slice(start, start + JSONL_GROUP_LINES).filter(Boolean);
    const startLine = start + 1;
    const endLine = Math.min(lines.length, start + JSONL_GROUP_LINES);
    const body = slice.join('\n').trim();
    if (body) {
      chunks.push({
        text: body,
        startLine,
        endLine,
        title: `Events ${startLine}-${endLine}`,
      });
    }
    start += JSONL_GROUP_LINES;
  }

  return chunks;
}

function buildChunks(rel, raw) {
  const fileType = detectFileType(rel);
  if (fileType === 'markdown') return chunkMarkdown(raw);
  if (fileType === 'jsonl') return chunkJsonl(raw);
  return chunkPlainText(raw);
}

const files = [];
for (const rel of INCLUDE_DIRS) files.push(...walk(path.join(ROOT, rel)));
for (const rel of INCLUDE_FILES) {
  const full = path.join(ROOT, rel);
  if (fs.existsSync(full)) files.push(full);
}

const indexedAt = new Date().toISOString();
const records = [];
const sourceCounts = {};

for (const file of files) {
  try {
    const stat = fs.statSync(file);
    if (stat.size > MAX_BYTES) continue;
    const raw = fs.readFileSync(file, 'utf8');
    const rel = path.relative(ROOT, file);
    const source = classifySource(rel);
    const fileType = detectFileType(rel);
    const title = inferTitle(rel, raw);
    const fileChunks = buildChunks(rel, raw);
    sourceCounts[source] = (sourceCounts[source] || 0) + 1;

    fileChunks.forEach((chunk, i) => {
      const ordinal = i + 1;
      records.push({
        path: rel,
        chunkId: `${rel}#L${chunk.startLine || 1}-L${chunk.endLine || 1}`,
        idx: i,
        ordinal,
        chars: chunk.text.length,
        source,
        fileType,
        title,
        sectionTitle: chunk.title || title,
        headingLevel: chunk.headingLevel ?? null,
        sectionIndex: chunk.sectionIndex ?? null,
        sectionChunkIndex: chunk.sectionChunkIndex ?? null,
        startLine: chunk.startLine || 1,
        endLine: chunk.endLine || countLines(chunk.text),
        mtimeMs: stat.mtimeMs,
        text: chunk.text,
      });
    });
  } catch (err) {
    records.push({
      path: path.relative(ROOT, file),
      error: String(err),
    });
  }
}

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(
  OUT_FILE,
  JSON.stringify({
    indexedAt,
    root: ROOT,
    stats: {
      records: records.filter(r => r.text).length,
      files: [...new Set(records.map(r => r.path).filter(Boolean))].length,
      sourceCounts,
    },
    files: records,
  }, null, 2),
);
console.log(`Indexed ${records.filter(r => r.text).length} chunks from ${Object.values(sourceCounts).reduce((a, b) => a + b, 0)} files -> ${OUT_FILE}`);

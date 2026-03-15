#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function usage() {
  console.log(`Usage:
  node OpenClaw/tools/telegram-topic-discovery.mjs [options]

Options:
  --chat-id <id>     Only include one Telegram chat
  --limit <n>        getUpdates limit (default: 100, max: 100)
  --offset <n>       getUpdates offset
  --config <path>    Config path (default: ../.openclaw/openclaw.json)
  --token <token>    Explicit Telegram bot token override
  --help             Show this help

Example:
  node OpenClaw/tools/telegram-topic-discovery.mjs --chat-id -1003754981982 --limit 200
`);
}

function parseArgs(argv) {
  const args = {
    chatId: null,
    limit: 100,
    offset: null,
    configPath: path.resolve(__dirname, "..", "..", ".openclaw", "openclaw.json"),
    token: null,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--help" || item === "-h") {
      args.help = true;
      continue;
    }
    if (item === "--chat-id") {
      args.chatId = String(argv[i + 1] ?? "").trim();
      i += 1;
      continue;
    }
    if (item === "--limit") {
      const n = Number(argv[i + 1]);
      args.limit = Number.isFinite(n) ? Math.min(100, Math.max(1, Math.floor(n))) : 100;
      i += 1;
      continue;
    }
    if (item === "--offset") {
      const n = Number(argv[i + 1]);
      args.offset = Number.isFinite(n) ? Math.floor(n) : null;
      i += 1;
      continue;
    }
    if (item === "--config") {
      args.configPath = path.resolve(argv[i + 1] ?? "");
      i += 1;
      continue;
    }
    if (item === "--token") {
      args.token = String(argv[i + 1] ?? "").trim();
      i += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${item}`);
  }

  return args;
}

function readJson(jsonPath) {
  const text = fs.readFileSync(jsonPath, "utf8");
  return JSON.parse(text);
}

function pickToken(config, explicitToken) {
  if (explicitToken) return explicitToken;
  return (
    config?.channels?.telegram?.accounts?.default?.botToken ||
    config?.channels?.telegram?.botToken ||
    ""
  );
}

function normalizeText(value) {
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) return null;
  return cleaned.slice(0, 120);
}

function collectMessages(update) {
  return [
    update?.message,
    update?.edited_message,
    update?.channel_post,
    update?.edited_channel_post,
  ].filter(Boolean);
}

function toNumberSafe(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  const config = readJson(args.configPath);
  const token = pickToken(config, args.token);
  if (!token) {
    throw new Error("Telegram bot token not found. Use --token or set it in .openclaw/openclaw.json");
  }

  const params = new URLSearchParams();
  params.set("limit", String(args.limit));
  if (args.offset !== null) params.set("offset", String(args.offset));

  const url = `https://api.telegram.org/bot${token}/getUpdates?${params.toString()}`;
  const response = await fetch(url);
  const payload = await response.json();
  if (!payload?.ok) {
    throw new Error(payload?.description || "Telegram getUpdates failed");
  }

  const updates = Array.isArray(payload.result) ? payload.result : [];
  const topicMap = new Map();
  for (const update of updates) {
    const messages = collectMessages(update);
    for (const msg of messages) {
      if (!msg?.chat || msg.message_thread_id === undefined || msg.message_thread_id === null) {
        continue;
      }
      const chatId = String(msg.chat.id);
      if (args.chatId && chatId !== args.chatId) continue;

      const threadId = String(msg.message_thread_id);
      const key = `${chatId}:${threadId}`;
      const topicName =
        msg?.forum_topic_created?.name ||
        msg?.forum_topic_edited?.name ||
        msg?.reply_to_message?.forum_topic_created?.name ||
        null;
      const sampleText = normalizeText(msg?.text) || normalizeText(msg?.caption);
      const date = toNumberSafe(msg?.date) || 0;

      if (!topicMap.has(key)) {
        topicMap.set(key, {
          chatId,
          chatTitle: msg?.chat?.title || null,
          threadId,
          topicName,
          sampleText,
          latestDate: date,
          fromUpdateId: update?.update_id ?? null,
        });
        continue;
      }

      const existing = topicMap.get(key);
      if (!existing.topicName && topicName) existing.topicName = topicName;
      if (!existing.sampleText && sampleText) existing.sampleText = sampleText;
      if (date > existing.latestDate) {
        existing.latestDate = date;
        existing.fromUpdateId = update?.update_id ?? existing.fromUpdateId;
      }
      topicMap.set(key, existing);
    }
  }

  const topics = Array.from(topicMap.values()).sort((a, b) => {
    if (a.chatId !== b.chatId) return a.chatId.localeCompare(b.chatId);
    return Number(a.threadId) - Number(b.threadId);
  });

  const nextOffset = updates.length
    ? (toNumberSafe(updates[updates.length - 1]?.update_id) || 0) + 1
    : null;

  console.log(
    JSON.stringify(
      {
        ok: true,
        updateCount: updates.length,
        nextOffset,
        chatIdFilter: args.chatId,
        topics,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(`[telegram-topic-discovery] ${error.message}`);
  process.exit(1);
});

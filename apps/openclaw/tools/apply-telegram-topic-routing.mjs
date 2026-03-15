#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LANE_SPECS = [
  {
    key: "risk",
    label: "RISK",
    systemPrompt: "此 Topic 只做风险闸门与止损回撤控制。先保命，再谈收益。",
  },
  {
    key: "alpha",
    label: "ALPHA",
    systemPrompt: "此 Topic 只做研究与机会评估。输出要含假设、证据和失效条件。",
  },
  {
    key: "exec",
    label: "EXEC",
    systemPrompt: "此 Topic 只做执行与落地。回答要有步骤、命令和回滚点。",
  },
  {
    key: "fast",
    label: "FAST",
    systemPrompt: "此 Topic 走快速问答。先给结论，再补关键理由。",
  },
  {
    key: "cn",
    label: "CN",
    systemPrompt: "此 Topic 强化中文表达质量。用清晰中文输出，避免英文术语堆砌。",
  },
  {
    key: "brain",
    label: "BRAIN",
    systemPrompt: "此 Topic 处理高复杂度推理。可慢一点，但必须完整严谨。",
  },
  {
    key: "creative",
    label: "CREATIVE",
    systemPrompt: "此 Topic 用于创意和文案。保持可执行，不要空话。",
  },
];

function usage() {
  console.log(`Usage:
  node OpenClaw/tools/apply-telegram-topic-routing.mjs [options]

Required:
  --chat-id <id>
  --risk <threadId>
  --alpha <threadId>
  --exec <threadId>
  --fast <threadId>
  --cn <threadId>
  --brain <threadId>
  --creative <threadId>

Optional:
  --owner-id <telegramUserId>  Override allowlist owner (defaults to existing config)
  --config <path>              Config path (default: ../.openclaw/openclaw.json)
  --help                       Show this help

Example:
  node OpenClaw/tools/apply-telegram-topic-routing.mjs \\
    --chat-id -1003754981982 \\
    --owner-id 7043182738 \\
    --risk 101 --alpha 102 --exec 103 --fast 104 --cn 105 --brain 106 --creative 107
`);
}

function parseArgs(argv) {
  const args = {
    chatId: null,
    ownerId: null,
    configPath: path.resolve(__dirname, "..", "..", ".openclaw", "openclaw.json"),
    help: false,
  };
  for (const lane of LANE_SPECS) args[lane.key] = null;

  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--help" || item === "-h") {
      args.help = true;
      continue;
    }
    if (item === "--config") {
      args.configPath = path.resolve(argv[i + 1] ?? "");
      i += 1;
      continue;
    }
    if (item === "--chat-id") {
      args.chatId = String(argv[i + 1] ?? "").trim();
      i += 1;
      continue;
    }
    if (item === "--owner-id") {
      args.ownerId = String(argv[i + 1] ?? "").trim();
      i += 1;
      continue;
    }
    let laneMatched = false;
    for (const lane of LANE_SPECS) {
      if (item === `--${lane.key}`) {
        args[lane.key] = String(argv[i + 1] ?? "").trim();
        i += 1;
        laneMatched = true;
        break;
      }
    }
    if (laneMatched) continue;
    throw new Error(`Unknown argument: ${item}`);
  }

  if (!args.help) {
    if (!args.chatId) throw new Error("Missing required --chat-id");
    for (const lane of LANE_SPECS) {
      if (!args[lane.key]) throw new Error(`Missing required --${lane.key}`);
    }
  }

  return args;
}

function readJson(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  return JSON.parse(text);
}

function writeJson(filePath, value) {
  const text = `${JSON.stringify(value, null, 2)}\n`;
  fs.writeFileSync(filePath, text, "utf8");
}

function compactAllowlist(input) {
  const values = Array.isArray(input) ? input : [];
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const normalized = String(value).trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

function resolveOwnerAllowlist(config, explicitOwnerId, chatId) {
  if (explicitOwnerId) return compactAllowlist([explicitOwnerId]);

  const telegram = config?.channels?.telegram || {};
  const group = telegram?.groups?.[chatId] || {};
  const defaultAccount =
    telegram?.accounts?.[telegram?.defaultAccount || "default"] || telegram?.accounts?.default || {};

  const fallback =
    group?.allowFrom ||
    telegram?.groupAllowFrom ||
    telegram?.allowFrom ||
    defaultAccount?.allowFrom ||
    [];

  return compactAllowlist(fallback);
}

function makeTopicTemplate(threadId, ownerAllowlist, laneSpec) {
  return {
    enabled: true,
    requireMention: false,
    groupPolicy: "allowlist",
    allowFrom: ownerAllowlist,
    systemPrompt: laneSpec.systemPrompt,
  };
}

function applyRouting(config, args) {
  config.channels ||= {};
  config.channels.telegram ||= {};

  const telegram = config.channels.telegram;
  telegram.groups ||= {};

  const ownerAllowlist = resolveOwnerAllowlist(config, args.ownerId, args.chatId);
  const group = {
    ...(telegram.groups[args.chatId] || {}),
  };

  group.enabled = true;
  group.requireMention = group.requireMention ?? true;
  group.groupPolicy = "allowlist";
  group.allowFrom = ownerAllowlist;

  const existingTopics =
    group.topics && typeof group.topics === "object" && !Array.isArray(group.topics)
      ? group.topics
      : {};

  const nextTopics = {
    ...existingTopics,
  };

  for (const lane of LANE_SPECS) {
    const threadId = String(args[lane.key]);
    nextTopics[threadId] = {
      ...(existingTopics[threadId] || {}),
      ...makeTopicTemplate(threadId, ownerAllowlist, lane),
    };
  }

  group.topics = nextTopics;
  telegram.groups[args.chatId] = group;

  return {
    chatId: args.chatId,
    ownerAllowlist,
    topics: LANE_SPECS.map((lane) => ({
      lane: lane.label,
      threadId: String(args[lane.key]),
    })),
  };
}

function makeBackupPath(configPath) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  return `${configPath}.bak-topic-${stamp}`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  const config = readJson(args.configPath);
  const backupPath = makeBackupPath(args.configPath);
  fs.copyFileSync(args.configPath, backupPath);

  const summary = applyRouting(config, args);
  writeJson(args.configPath, config);

  console.log(
    JSON.stringify(
      {
        ok: true,
        configPath: args.configPath,
        backupPath,
        summary,
      },
      null,
      2,
    ),
  );
}

try {
  main();
} catch (error) {
  console.error(`[apply-telegram-topic-routing] ${error.message}`);
  process.exit(1);
}

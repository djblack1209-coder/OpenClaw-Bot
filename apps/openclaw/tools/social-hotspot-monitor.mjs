#!/usr/bin/env node
/**
 * social-hotspot-monitor.mjs
 * 热点监控工具 - 扫描热点源，评估与OpenClaw的关联度，输出可追热点列表
 * 
 * Usage:
 *   node tools/social-hotspot-monitor.mjs --platform xhs|x|all [--min-score 7] [--output json|text]
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PERSONA_PATH = join(__dirname, 'social-persona.md');
const TOPIC_LIB_PATH = join(__dirname, 'social-topic-library.md');
const HOTSPOT_LOG_PATH = join(__dirname, '..', 'memory', 'hotspot-scan-log.jsonl');

function parseArgs(argv) {
  const opts = { platform: 'all', minScore: 7, output: 'json' };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--platform') opts.platform = String(argv[++i] || 'all').toLowerCase();
    else if (argv[i] === '--min-score') opts.minScore = Number(argv[++i] || 7);
    else if (argv[i] === '--output') opts.output = String(argv[++i] || 'json').toLowerCase();
  }
  return opts;
}

// 热点评估矩阵（与 social-interaction-strategy.md 一致）
function evaluateHotspot(hotspot) {
  const { title, source, category } = hotspot;
  const t = (title || '').toLowerCase();

  // AI/OpenClaw 关联度 (40%)
  let relevance = 0;
  if (/(ai|人工智能|大模型|gpt|claude|llm|agent|copilot|openclaw|机器人|自动化|智能)/i.test(t)) relevance = 9;
  else if (/(效率|工具|编程|代码|开发|技术|科技|数码|软件)/i.test(t)) relevance = 6;
  else if (/(考研|考公|学习|教育|职场|求职|面试)/i.test(t)) relevance = 5;
  else if (/(健身|减肥|减脂|饮食|生活|省钱|比价|购物)/i.test(t)) relevance = 4;
  else relevance = 2;

  // 热度 (25%) - 基于来源权重
  let heat = 5;
  if (source === 'trending') heat = 9;
  else if (source === 'hot_search') heat = 8;
  else if (source === 'viral_post') heat = 7;
  else if (source === 'kol_post') heat = 6;

  // 时效性 (20%)
  let timeliness = 5;
  if (/(刚刚|今天|突发|最新|breaking|just|now)/i.test(t)) timeliness = 9;
  else if (/(本周|这周|近期|recently)/i.test(t)) timeliness = 6;

  // 争议性 (15%)
  let controversy = 3;
  if (/(争议|打脸|崩了|翻车|骗局|智商税|真相|别再|误区|取代|淘汰|裁员)/i.test(t)) controversy = 8;
  else if (/(为什么|值得|应该|到底|真的)/i.test(t)) controversy = 5;

  const score = Math.round(relevance * 0.4 + heat * 0.25 + timeliness * 0.2 + controversy * 0.15);

  // 响应速度建议
  let urgency = 'B';
  if (score >= 8 && timeliness >= 8) urgency = 'S';
  else if (score >= 7) urgency = 'A';

  // 建议切入角度
  let angle = '';
  if (relevance >= 8) angle = '直接关联：用OpenClaw演示/解决';
  else if (relevance >= 5) angle = '间接关联：AI辅助该场景';
  else angle = '生活面展示：轻度结合AI视角评论';

  return {
    ...hotspot,
    evaluation: { relevance, heat, timeliness, controversy, score, urgency, angle },
  };
}

// 模拟热点源（实际运行时应接入浏览器自动化抓取）
function getHotspotSources(platform) {
  // 这是热点源的结构定义，实际数据需要通过浏览器自动化填充
  const sources = {
    xhs: [
      { type: 'hot_search', url: 'https://www.xiaohongshu.com/explore', description: '小红书发现页热门' },
      { type: 'search_trend', url: 'https://www.xiaohongshu.com/search_result?keyword=AI工具', description: 'AI工具搜索结果' },
      { type: 'search_trend', url: 'https://www.xiaohongshu.com/search_result?keyword=AI教程', description: 'AI教程搜索结果' },
      { type: 'search_trend', url: 'https://www.xiaohongshu.com/search_result?keyword=效率工具', description: '效率工具搜索结果' },
      { type: 'search_trend', url: 'https://www.xiaohongshu.com/search_result?keyword=考研AI', description: '考研AI搜索结果' },
    ],
    x: [
      { type: 'trending', url: 'https://x.com/explore/tabs/trending', description: 'X Trending' },
      { type: 'search', url: 'https://x.com/search?q=AI%20agent&f=top', description: 'AI agent热门' },
      { type: 'search', url: 'https://x.com/search?q=AI%20tools&f=top', description: 'AI tools热门' },
    ],
    external: [
      { type: 'aggregator', url: 'https://www.producthunt.com', description: 'Product Hunt每日热门' },
      { type: 'aggregator', url: 'https://news.ycombinator.com', description: 'Hacker News前10' },
    ],
  };

  if (platform === 'all') return [...sources.xhs, ...sources.x, ...sources.external];
  return sources[platform] || [];
}

// 生成浏览器抓取任务（供 social-browser-adapter 执行）
function generateScanTasks(platform) {
  const sources = getHotspotSources(platform);
  return {
    generatedAt: new Date().toISOString(),
    taskType: 'hotspot_scan',
    platform,
    sources,
    instructions: [
      '打开每个URL',
      '提取页面上的热门话题/帖子标题（前10-20条）',
      '记录每条的：标题、链接、互动数据（点赞/评论/收藏）',
      '输出为JSON数组',
      '完成后关闭非必要标签页',
    ],
    outputPath: join(__dirname, '..', 'memory', `hotspot-raw-${Date.now()}.json`),
  };
}

// 处理已抓取的原始热点数据
function processRawHotspots(rawData, minScore) {
  if (!Array.isArray(rawData)) return [];
  return rawData
    .map(evaluateHotspot)
    .filter(h => h.evaluation.score >= minScore)
    .sort((a, b) => b.evaluation.score - a.evaluation.score);
}

// 记录扫描日志
function logScan(result) {
  const entry = {
    ts: new Date().toISOString(),
    ...result,
  };
  const line = JSON.stringify(entry) + '\n';
  try {
    const dir = dirname(HOTSPOT_LOG_PATH);
    if (!existsSync(dir)) {
      import('node:fs').then(fs => fs.mkdirSync(dir, { recursive: true }));
    }
    writeFileSync(HOTSPOT_LOG_PATH, line, { flag: 'a' });
  } catch (e) {
    console.error('Failed to write hotspot log:', e.message);
  }
}

// Main
const opts = parseArgs(process.argv.slice(2));

// 检查是否有原始数据文件传入（--raw-data path）
const rawDataPath = (() => {
  const idx = process.argv.indexOf('--raw-data');
  return idx >= 0 ? process.argv[idx + 1] : null;
})();

if (rawDataPath && existsSync(rawDataPath)) {
  // 处理模式：评估已抓取的热点
  const raw = JSON.parse(readFileSync(rawDataPath, 'utf8'));
  const evaluated = processRawHotspots(raw, opts.minScore);
  const result = {
    mode: 'evaluate',
    platform: opts.platform,
    minScore: opts.minScore,
    total: evaluated.length,
    hotspots: evaluated,
  };
  logScan({ mode: 'evaluate', platform: opts.platform, count: evaluated.length });
  console.log(JSON.stringify(result, null, 2));
} else {
  // 扫描任务生成模式：输出浏览器需要执行的抓取任务
  const tasks = generateScanTasks(opts.platform);
  const result = {
    mode: 'generate_scan_tasks',
    platform: opts.platform,
    tasks,
    nextStep: '将此任务交给浏览器自动化执行，抓取完成后用 --raw-data 参数传入结果进行评估',
  };
  console.log(JSON.stringify(result, null, 2));
}

#!/usr/bin/env node
/**
 * social-comment-engine.mjs
 * 评论区互动引擎 - 管理自己帖子的回复 + 蹭别人评论区
 *
 * Usage:
 *   node tools/social-comment-engine.mjs reply --platform xhs|x --post-id ID
 *   node tools/social-comment-engine.mjs scout --platform xhs|x [--category S|A|B]
 *   node tools/social-comment-engine.mjs generate-reply --comment "用户评论内容" [--context "帖子主题"]
 *   node tools/social-comment-engine.mjs generate-scout-comment --post-title "目标帖子标题" --post-summary "帖子摘要"
 *   node tools/social-comment-engine.mjs schedule --platform xhs|x --post-id ID
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PERSONA_PATH = join(__dirname, 'social-persona.md');
const STRATEGY_PATH = join(__dirname, 'social-interaction-strategy.md');
const COMMENT_LOG_PATH = join(__dirname, '..', 'memory', 'comment-interactions.jsonl');

function parseArgs(argv) {
  const opts = { command: argv[0], platform: 'xhs', postId: '', category: 'S', comment: '', context: '', postTitle: '', postSummary: '' };
  for (let i = 1; i < argv.length; i++) {
    if (argv[i] === '--platform') opts.platform = String(argv[++i] || 'xhs').toLowerCase();
    else if (argv[i] === '--post-id') opts.postId = String(argv[++i] || '');
    else if (argv[i] === '--category') opts.category = String(argv[++i] || 'S').toUpperCase();
    else if (argv[i] === '--comment') opts.comment = String(argv[++i] || '');
    else if (argv[i] === '--context') opts.context = String(argv[++i] || '');
    else if (argv[i] === '--post-title') opts.postTitle = String(argv[++i] || '');
    else if (argv[i] === '--post-summary') opts.postSummary = String(argv[++i] || '');
  }
  return opts;
}

// 评论分类器
function classifyComment(text) {
  const t = (text || '').trim();
  if (!t) return { type: 'empty', priority: 0 };

  if (/[？?]|怎么|如何|能不能|可以吗|请问|求|教程|方法|哪个/.test(t)) {
    return { type: 'question', priority: 1, label: '提问类' };
  }
  if (/太[好棒强赞有]|学到了|有用|收藏|感谢|谢谢|厉害|牛|干货|宝藏/.test(t)) {
    return { type: 'praise', priority: 3, label: '夸奖类' };
  }
  if (/我也|同款|一样|真实|哈哈|确实|对对|深有同感/.test(t)) {
    return { type: 'resonance', priority: 2, label: '共鸣类' };
  }
  if (/没用|不行|垃圾|骗|割韭菜|智商税|有什么用|不就是/.test(t)) {
    return { type: 'troll', priority: 5, label: '杠精类' };
  }
  if (/但是|不过|其实|不太同意|我觉得不|有个问题/.test(t)) {
    return { type: 'challenge', priority: 4, label: '质疑类' };
  }
  return { type: 'general', priority: 3, label: '一般评论' };
}

// 回复风格生成器（基于 social-persona.md 的人设）
function generateReplyGuidance(comment, classification, context) {
  const templates = {
    question: [
      { template: '好问题，简单说就是{answer}。要详细教程的话我后面安排一期。', note: '认真回答，展示专业度' },
      { template: '这个我之前也踩过坑，{answer}。', note: '用经验感拉近距离' },
      { template: '试试{method}，我就是这么搞定的。', note: '给具体方法' },
    ],
    praise: [
      { template: '有用就好，后面还有更硬的干货。', note: '简短+预告' },
      { template: '谢谢，有想看的内容评论区告诉我。', note: '引导互动' },
      { template: '哈哈被夸了，下一期安排{preview}。', note: '预告下期' },
    ],
    resonance: [
      { template: '哈哈同款体验，{detail}。', note: '补充细节增加真实感' },
      { template: '对对对，这个感觉太真实了。', note: '简短共鸣' },
    ],
    challenge: [
      { template: '理解你的顾虑，不过{fact}。', note: '用事实回应' },
      { template: '确实不是所有场景都适用，我主要是针对{scenario}来说的。', note: '限定范围' },
      { template: '你说的也有道理，不过我实际体验下来{experience}。', note: '用体验说话' },
    ],
    troll: [
      { template: '哈哈每个人需求不一样嘛，适合自己的最好。', note: '幽默化解' },
      { template: null, note: '严重杠精直接不回复' },
    ],
    general: [
      { template: '哈哈{reaction}', note: '轻松回应' },
    ],
  };

  const options = templates[classification.type] || templates.general;
  return {
    comment: comment,
    classification,
    context: context || '(未提供帖子上下文)',
    replyOptions: options,
    personaReminder: '回复语气：像朋友回消息，不像客服回工单。可以开玩笑、反问、承认不知道。',
    doNot: ['不要用"您好"开头', '不要用感叹号轰炸', '不要复制粘贴式回复', '不要暴露AI身份'],
  };
}

// 蹭评论生成指导
function generateScoutGuidance(postTitle, postSummary) {
  const t = (postTitle || '').toLowerCase();

  let approachType = 'supplement';
  if (/(教程|方法|步骤|攻略|指南)/.test(t)) approachType = 'supplement';
  else if (/(吐槽|崩了|翻车|难|痛苦|烦)/.test(t)) approachType = 'resonance';
  else if (/(推荐|测评|对比|选择)/.test(t)) approachType = 'experience';
  else if (/[？?]|为什么|怎么|如何/.test(t)) approachType = 'answer';

  const approaches = {
    supplement: {
      label: '补充信息型',
      templates: [
        '补充一个小技巧：{tip}，我之前试过挺好用的。',
        '我也用过这个，发现{insight}效果更好。',
      ],
    },
    resonance: {
      label: '共鸣型',
      templates: [
        '太真实了哈哈，我也是{similar_experience}。',
        '终于有人说了，{agree_and_add}。',
      ],
    },
    experience: {
      label: '经验分享型',
      templates: [
        '用过{product}，个人感觉{opinion}，仅供参考。',
        '我的体验是{experience}，不过每个人情况不一样。',
      ],
    },
    answer: {
      label: '回答型',
      templates: [
        '之前研究过这个，{answer}，希望有帮助。',
        '我的理解是{explanation}，不一定对哈。',
      ],
    },
  };

  return {
    targetPost: { title: postTitle, summary: postSummary },
    approachType,
    approach: approaches[approachType],
    rules: [
      '提供有价值的信息，不是打广告',
      '语气自然，像普通用户在分享',
      '和帖子内容相关，不跑题',
      '绝对不要贴链接或说"关注我"',
      '每个帖子只留1条评论',
    ],
    personaReminder: '你是一个25-27岁的程序员，真实、务实、偶尔幽默。',
  };
}

// 蹭评论目标账号推荐
function getScoutTargets(platform, category) {
  const targets = {
    xhs: {
      S: [
        { type: 'AI工具类头部博主', searchKeywords: ['AI工具推荐', 'AI教程', 'ChatGPT教程', 'AI效率'], minLikes: 500 },
        { type: '效率工具博主', searchKeywords: ['效率工具', '生产力工具', '办公神器'], minLikes: 300 },
      ],
      A: [
        { type: '考研/学习博主', searchKeywords: ['考研经验', 'AI学习', '学习方法', '考公上岸'], minLikes: 200 },
        { type: '职场成长博主', searchKeywords: ['职场效率', '副业', '自媒体运营'], minLikes: 200 },
      ],
      B: [
        { type: '健身/生活博主', searchKeywords: ['程序员健身', '减脂', '健身打卡'], minLikes: 100 },
        { type: '程序员日常博主', searchKeywords: ['程序员日常', '码农生活', '互联网打工'], minLikes: 100 },
      ],
    },
    x: {
      S: [
        { type: 'AI/Tech KOL', searchKeywords: ['AI agent', 'AI tools', 'LLM', 'OpenAI'], minLikes: 50 },
        { type: '开发者博主', searchKeywords: ['developer tools', 'coding', 'open source'], minLikes: 30 },
      ],
      A: [
        { type: '科技评论', searchKeywords: ['tech review', 'AI news', 'startup'], minLikes: 20 },
      ],
      B: [
        { type: '独立开发者', searchKeywords: ['indie hacker', 'side project', 'build in public'], minLikes: 10 },
      ],
    },
  };

  const platformTargets = targets[platform] || targets.xhs;
  if (category === 'all') return platformTargets;
  return { [category]: platformTargets[category] || [] };
}

// 回复时间调度
function getReplySchedule(postAge) {
  // postAge in minutes since post was published
  if (postAge <= 60) return { interval: 'immediate', note: '黄金1小时，回复所有评论' };
  if (postAge <= 360) return { interval: '30min', note: '每30分钟检查新评论' };
  if (postAge <= 1440) return { interval: '2h', note: '每2小时检查一次' };
  return { interval: '12h', note: '每天检查1-2次' };
}

// 记录互动日志
function logInteraction(entry) {
  const line = JSON.stringify({ ts: new Date().toISOString(), ...entry }) + '\n';
  try {
    writeFileSync(COMMENT_LOG_PATH, line, { flag: 'a' });
  } catch (e) {
    console.error('Failed to write comment log:', e.message);
  }
}

// Main
const opts = parseArgs(process.argv.slice(2));

if (!opts.command) {
  console.error([
    'Usage:',
    '  node tools/social-comment-engine.mjs reply --platform xhs|x --post-id ID',
    '  node tools/social-comment-engine.mjs scout --platform xhs|x [--category S|A|B|all]',
    '  node tools/social-comment-engine.mjs generate-reply --comment "评论内容" [--context "帖子主题"]',
    '  node tools/social-comment-engine.mjs generate-scout-comment --post-title "标题" --post-summary "摘要"',
    '  node tools/social-comment-engine.mjs schedule --platform xhs|x --post-id ID',
  ].join('\n'));
  process.exit(1);
}

let result;

switch (opts.command) {
  case 'generate-reply': {
    const classification = classifyComment(opts.comment);
    result = generateReplyGuidance(opts.comment, classification, opts.context);
    break;
  }
  case 'generate-scout-comment': {
    result = generateScoutGuidance(opts.postTitle, opts.postSummary);
    break;
  }
  case 'scout': {
    result = {
      action: 'scout_targets',
      platform: opts.platform,
      category: opts.category,
      targets: getScoutTargets(opts.platform, opts.category),
      dailyQuota: { maxPosts: 5, maxCommentsPerPost: 1 },
      timing: '优先选择发布2小时内的热门帖子',
      instructions: [
        '按目标类型搜索关键词',
        '找到最近2小时内发布的高互动帖子',
        '阅读帖子内容，确定切入角度',
        '用 generate-scout-comment 生成评论指导',
        '发布评论',
        '记录互动日志',
      ],
    };
    break;
  }
  case 'reply': {
    result = {
      action: 'reply_management',
      platform: opts.platform,
      postId: opts.postId,
      instructions: [
        '打开帖子评论区',
        '提取所有未回复的评论',
        '对每条评论用 generate-reply 生成回复指导',
        '按优先级排序回复（提问 > 共鸣 > 夸奖 > 质疑 > 杠精）',
        '执行回复',
        '记录互动日志',
      ],
    };
    break;
  }
  case 'schedule': {
    // 模拟帖子发布后的回复调度
    const now = Date.now();
    const schedules = [
      { offsetMin: 0, action: '立即回复已有评论' },
      { offsetMin: 30, action: '检查新评论并回复' },
      { offsetMin: 60, action: '黄金1小时结束，回复所有遗漏评论' },
      { offsetMin: 120, action: '2小时检查' },
      { offsetMin: 240, action: '4小时检查' },
      { offsetMin: 360, action: '6小时检查' },
      { offsetMin: 720, action: '12小时检查' },
      { offsetMin: 1440, action: '24小时最终检查' },
    ];
    result = {
      action: 'reply_schedule',
      platform: opts.platform,
      postId: opts.postId,
      createdAt: new Date().toISOString(),
      schedules: schedules.map(s => ({
        ...s,
        scheduledAt: new Date(now + s.offsetMin * 60000).toISOString(),
      })),
    };
    break;
  }
  default:
    console.error(`Unknown command: ${opts.command}`);
    process.exit(1);
}

logInteraction({ command: opts.command, platform: opts.platform, summary: result.action || opts.command });
console.log(JSON.stringify(result, null, 2));

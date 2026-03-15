#!/usr/bin/env node

function parseArgs(argv) {
  const opts = { platform: 'generic', explain: false };
  const topics = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--platform') opts.platform = String(argv[++i] || 'generic').toLowerCase();
    else if (arg === '--explain') opts.explain = true;
    else topics.push(arg);
  }
  return { opts, topics };
}

function scoreByRegex(text, rules, hitScore, missScore = 0) {
  const hits = rules.filter((re) => re.test(text));
  return { score: hits.length ? Math.min(hitScore, missScore + hits.length * Math.ceil(hitScore / Math.max(1, rules.length))) : missScore, hits: hits.map(String) };
}

function scoreTopic(topic, platform = 'generic', explain = false) {
  const t = String(topic || '').trim();
  const lower = t.toLowerCase();

  const bucketRules = {
    timeliness: [/(今天|刚刚|最新|突发|发布|上线|本周|本月|临近|窗口|节点|hot|viral|breaking|new|launch|drop)/i],
    spread: [/(为什么|值得|趋势|机会|真相|一图看懂|拆解|复盘|预测|判断|机会|赚钱|增长|体验|省了|翻倍|效率|搞定|起飞|神器|改变)/i],
    controversy: [/(别再|误区|打脸|崩了|淘汰|真相|高估|低估|没人告诉你|不建议|骗局|智商税|得罪|醒醒|真的吗|你确定|别被骗|收割|割韭菜|90%|80%)/i],
    infoGap: [/(信息差|门槛|内幕|攻略|步骤|清单|模板|方法|能力|框架|workflow|sop|教程|技巧|秘诀|干货|指南|实操|手把手|保姆级)/i],
    visual: [/(对比|清单|步骤|模板|三点|五点|案例|前后|截图|图解|表格|盘点|before|after)/i],
    actionability: [/(怎么做|如何做|步骤|模板|清单|SOP|workflow|框架|建议|指南|装上|试试|用了|设置|安装|配置|上传|一键)/i],
    hookStrength: [/[？?]|只会|别急|真的|你确定|为什么|居然|竟然|没想到|万万没想到|说实话|坦白说|得罪人/i],
    audienceClarity: [/(考研|考公|考编|程序员|设计师|运营|学生|打工人|自由职业|宝妈|健身|减脂|减肥|职场|新人|小白|零基础)/i],
  };

  const scores = {};
  const reasons = {};
  for (const [key, rules] of Object.entries(bucketRules)) {
    const { score, hits } = scoreByRegex(t, rules, 5, 1);
    scores[key] = score;
    if (explain) reasons[key] = hits;
  }

  let platformFit = 2;
  const platformReasons = [];
  if (/(ai|创业|流量|赚钱|效率|副业|内容|增长|商业|产品|工具|自动化)/i.test(lower)) {
    platformFit += 2;
    platformReasons.push('general niche fit');
  }
  if (platform === 'x' && /(观点|判断|趋势|热议|争议|突发|结论|预测|快讯)/i.test(t)) {
    platformFit += 1;
    platformReasons.push('x conversational fit');
  }
  if ((platform === 'xiaohongshu' || platform === 'xhs') && /(清单|模板|步骤|攻略|复盘|避坑|经验|案例)/i.test(t)) {
    platformFit += 1;
    platformReasons.push('xhs save-worthy fit');
  }
  platformFit = Math.min(platformFit, 5);
  scores.platformFit = platformFit;
  if (explain) reasons.platformFit = platformReasons;

  let duplicationRisk = 1;
  if (/(又一个|合集|盘点|推荐|工具推荐|AI工具|副业项目)/i.test(t)) duplicationRisk = 3;
  if (/(最|顶级|万能|保姆级)/i.test(t)) duplicationRisk = Math.max(duplicationRisk, 2);
  scores.novelty = 5 - duplicationRisk;
  if (explain) reasons.novelty = [`duplicationRisk=${duplicationRisk}`];

  const weighted = {
    timeliness: 1.0,
    spread: 1.15,
    controversy: 0.9,
    infoGap: 1.1,
    visual: 0.75,
    actionability: 1.0,
    hookStrength: 1.3,
    audienceClarity: 1.2,
    platformFit: 1.1,
    novelty: 0.5,
  };

  const total = Object.entries(weighted).reduce((sum, [k, w]) => sum + (scores[k] || 0) * w, 0);
  const normalized = Math.round((total / 50) * 100);
  let verdict = 'hold';
  if (normalized >= 65) verdict = 'strong_publish';
  else if (normalized >= 50) verdict = 'test_publish';
  else if (normalized >= 35) verdict = 'rewrite';

  const result = {
    topic: t,
    platform,
    total: Number(total.toFixed(2)),
    normalized,
    verdict,
    ...scores,
  };
  if (explain) result.reasons = reasons;
  return result;
}

const { opts, topics } = parseArgs(process.argv.slice(2));
if (!topics.length) {
  console.error('Usage: node tools/social-topic-scorer.mjs [--platform x|xhs|generic] [--explain] "topic a" "topic b" ...');
  process.exit(1);
}

const ranked = topics.map((topic) => scoreTopic(topic, opts.platform, opts.explain)).sort((a, b) => b.normalized - a.normalized || b.total - a.total);
console.log(JSON.stringify({ platform: opts.platform, ranked }, null, 2));

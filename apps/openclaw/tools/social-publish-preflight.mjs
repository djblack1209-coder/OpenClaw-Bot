#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const rawArgs = process.argv.slice(2);
const opts = {
  platform: 'generic',
  style: '',
  title: '',
  text: '',
  tags: [],
  images: 0,
  links: [],
};
const topics = [];

for (let i = 0; i < rawArgs.length; i += 1) {
  const arg = rawArgs[i];
  if (arg === '--platform') opts.platform = String(rawArgs[++i] || 'generic').toLowerCase();
  else if (arg === '--style') opts.style = String(rawArgs[++i] || '');
  else if (arg === '--title') opts.title = String(rawArgs[++i] || '');
  else if (arg === '--text') opts.text = String(rawArgs[++i] || '');
  else if (arg === '--tags') opts.tags = String(rawArgs[++i] || '').split(',').map(s => s.trim()).filter(Boolean);
  else if (arg === '--images') opts.images = Number(rawArgs[++i] || 0);
  else if (arg === '--links') opts.links = String(rawArgs[++i] || '').split(',').map(s => s.trim()).filter(Boolean);
  else topics.push(arg);
}

function countCjkChars(text) {
  return Array.from(String(text || '')).filter(ch => /[\u4e00-\u9fff]/.test(ch)).length;
}

function findIssues({ platform, title, text, tags, images, links }) {
  const issues = [];
  const warnings = [];
  const combined = [title, text].filter(Boolean).join('\n').trim();
  const charCount = Array.from(combined).length;
  const cjkCount = countCjkChars(combined);

  if (!text.trim()) issues.push('缺少正文 text');
  if (/\b(todo|tbd|placeholder|xxx)\b/i.test(combined)) issues.push('存在占位符/TODO 文本');
  if (/\s{3,}/.test(combined)) warnings.push('存在较长空白，建议清理格式');
  if (!combined) issues.push('标题和正文都为空');

  // === 人设一致性检查（v2.0 新增） ===
  // 暴露AI身份
  if (/(我是AI|我是人工智能|作为AI助手|作为一个AI|I am an AI|as an AI assistant)/i.test(combined)) {
    issues.push('内容暴露AI身份，违反人设要求');
  }
  // 客服腔
  if (/(您好[，,]|亲爱的用户|为您|建议您|希望对您有帮助|感谢您的|如有疑问)/i.test(combined)) {
    warnings.push('检测到客服腔措辞，不符合人设语气（应像朋友聊天）');
  }
  // 过度营销
  if (/(关注我|点赞收藏|一键三连|强烈推荐！！|赶紧|千万别错过|限时)/i.test(combined)) {
    warnings.push('检测到营销号措辞，建议降低推销感');
  }
  // 空洞口号
  if (/(AI时代已经来临|拥抱变化|未来已来|颠覆性的|革命性的|划时代的)/i.test(combined)) {
    warnings.push('检测到空洞口号，建议用具体事实替代');
  }
  // 过度感叹号
  const exclamCount = (combined.match(/[！!]{2,}/g) || []).length;
  if (exclamCount >= 2) {
    warnings.push(`连续感叹号出现${exclamCount}处，建议克制`);
  }
  // 标题吸引力检查
  const titleText = (title || '').trim();
  if (titleText && !/[？?]|为什么|怎么|如何|别再|真的|居然|竟然|没想到|说实话|\d/.test(titleText)) {
    warnings.push('标题缺少钩子元素（疑问/数字/反常识/情绪词），吸引力可能不足');
  }

  if (platform === 'x') {
    if (charCount > 280) warnings.push(`X 主帖长度约 ${charCount} 字，可能需要缩短或拆到评论区`);
    if (charCount > 330) issues.push(`X 主帖明显过长（约 ${charCount} 字）`);
    if (!/[？?！!。.]$/.test(text.trim()) && charCount > 0) warnings.push('X 文案结尾较弱，建议补一句收束/钩子');
    if (links.length > 1) warnings.push('X 主帖链接过多，建议控制为 0-1 个');
  }

  if (platform === 'xiaohongshu' || platform === 'xhs') {
    if (!title.trim()) issues.push('小红书缺少标题');
    if (title.trim() && title.trim().length < 8) warnings.push('小红书标题偏短，可能不够像结论句/问题句');
    if (title.trim() && title.trim().length > 20) issues.push(`小红书标题超过20字限制（当前${title.trim().length}字），必须缩短`);
    const firstThreeLines = text.split(/\r?\n/).slice(0, 3).join(' ').trim();
    if (!firstThreeLines) issues.push('小红书前三行为空');
    if (firstThreeLines && firstThreeLines.length < 30) warnings.push('小红书前三行内容偏少，建议前三行能独立成立');
    if (images <= 0) warnings.push('小红书建议优先图文，当前 images=0');
    if (tags.length > 8) warnings.push(`小红书标签偏多（${tags.length}），建议收敛到高相关标签`);
    if (tags.length === 0) warnings.push('小红书缺少标签，建议添加3-5个高相关标签');
    if (cjkCount < 20) warnings.push('小红书正文偏短，像随手记而不是完整笔记');
  }

  return { issues, warnings, metrics: { charCount, cjkCount, tags: tags.length, images, links: links.length } };
}

const result = {
  ok: false,
  platform: opts.platform,
  style: opts.style || null,
  title: opts.title || null,
  checks: findIssues(opts),
};
result.ok = result.checks.issues.length === 0;

console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(2);

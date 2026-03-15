#!/usr/bin/env node

/**
 * 记忆索引调度工具 (Memory Index Dispatcher)
 * 
 * 用法:
 *   node memory-dispatch.mjs search <关键词>     # 搜索相关分类和条目
 *   node memory-dispatch.mjs list [分类前缀]     # 列出分类或条目
 *   node memory-dispatch.mjs read <编号>         # 读取指定编号的条目
 *   node memory-dispatch.mjs add <分类前缀> <标题> # 创建新条目
 *   node memory-dispatch.mjs verify              # 校验索引完整性
 */

import { readFileSync, readdirSync, existsSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MEMORY_ROOT = join(__dirname, '..', 'memory');

// 分类映射
const CATEGORIES = {
  SOC: { dir: 'social',      name: '社交媒体', id: '01' },
  SYS: { dir: 'system',      name: '系统运维', id: '02' },
  TRD: { dir: 'trading',     name: '交易盈利', id: '03' },
  DEV: { dir: 'development', name: '开发任务', id: '04' },
  OPS: { dir: 'operations',  name: '日常运营', id: '05' },
  ERR: { dir: 'errors',      name: '错误处理', id: '06' },
  DAY: { dir: 'daily',       name: '每日日志', id: '07' },
};

function readIndex(path) {
  if (!existsSync(path)) return null;
  return readFileSync(path, 'utf-8');
}

function listCategories() {
  console.log('\n记忆分类总览:\n');
  for (const [prefix, cat] of Object.entries(CATEGORIES)) {
    const indexPath = join(MEMORY_ROOT, cat.dir, 'INDEX.md');
    const exists = existsSync(indexPath) ? '✓' : '✗';
    const fileCount = existsSync(join(MEMORY_ROOT, cat.dir))
      ? readdirSync(join(MEMORY_ROOT, cat.dir)).filter(f => f.endsWith('.md') && f !== 'INDEX.md').length
      : 0;
    console.log(`  [${cat.id}] ${prefix} - ${cat.name}  (${fileCount} 文件) ${exists}`);
  }
}

function listCategory(prefix) {
  const cat = CATEGORIES[prefix.toUpperCase()];
  if (!cat) {
    console.log(`未知分类: ${prefix}`);
    console.log(`可用分类: ${Object.keys(CATEGORIES).join(', ')}`);
    return;
  }
  
  const catDir = join(MEMORY_ROOT, cat.dir);
  const indexPath = join(catDir, 'INDEX.md');
  
  if (!existsSync(indexPath)) {
    console.log(`分类 ${prefix} 的索引不存在`);
    return;
  }
  
  console.log(`\n分类 [${cat.id}] ${prefix} - ${cat.name}:\n`);
  console.log(readFileSync(indexPath, 'utf-8'));
}

function readEntry(entryId) {
  // 解析编号: SOC-001 → prefix=SOC, num=001
  const match = entryId.match(/^([A-Z]{3})-(\d{3})/);
  if (!match) {
    console.log(`无效编号格式: ${entryId} (期望格式: XXX-nnn, 如 SOC-001)`);
    return;
  }
  
  const [, prefix, num] = match;
  const cat = CATEGORIES[prefix];
  if (!cat) {
    console.log(`未知分类前缀: ${prefix}`);
    return;
  }
  
  const catDir = join(MEMORY_ROOT, cat.dir);
  const files = existsSync(catDir) 
    ? readdirSync(catDir).filter(f => f.startsWith(`${prefix}-${num}`))
    : [];
  
  if (files.length === 0) {
    console.log(`未找到编号 ${entryId} 对应的文件`);
    return;
  }
  
  for (const file of files) {
    console.log(`\n--- ${file} ---\n`);
    console.log(readFileSync(join(catDir, file), 'utf-8'));
  }
}

function searchMemory(keyword) {
  console.log(`\n搜索: "${keyword}"\n`);
  let found = 0;
  
  for (const [prefix, cat] of Object.entries(CATEGORIES)) {
    const catDir = join(MEMORY_ROOT, cat.dir);
    if (!existsSync(catDir)) continue;
    
    const files = readdirSync(catDir).filter(f => f.endsWith('.md'));
    
    for (const file of files) {
      const content = readFileSync(join(catDir, file), 'utf-8');
      if (content.toLowerCase().includes(keyword.toLowerCase())) {
        // 找到匹配的行
        const lines = content.split('\n');
        const matches = lines
          .map((line, i) => ({ line: line.trim(), num: i + 1 }))
          .filter(({ line }) => line.toLowerCase().includes(keyword.toLowerCase()))
          .slice(0, 3);
        
        console.log(`[${prefix}] ${cat.dir}/${file}:`);
        for (const m of matches) {
          console.log(`  L${m.num}: ${m.line.substring(0, 100)}`);
        }
        console.log('');
        found++;
      }
    }
  }
  
  if (found === 0) {
    console.log('未找到匹配结果');
  } else {
    console.log(`共找到 ${found} 个匹配文件`);
  }
}

function verifyIndex() {
  console.log('\n索引完整性校验:\n');
  let issues = 0;
  
  for (const [prefix, cat] of Object.entries(CATEGORIES)) {
    const catDir = join(MEMORY_ROOT, cat.dir);
    
    if (!existsSync(catDir)) {
      console.log(`  ✗ ${prefix} - 目录不存在: ${cat.dir}/`);
      issues++;
      continue;
    }
    
    const indexPath = join(catDir, 'INDEX.md');
    if (!existsSync(indexPath)) {
      console.log(`  ✗ ${prefix} - 缺少 INDEX.md`);
      issues++;
      continue;
    }
    
    const files = readdirSync(catDir).filter(f => f.endsWith('.md') && f !== 'INDEX.md');
    const indexContent = readFileSync(indexPath, 'utf-8');
    
    for (const file of files) {
      if (!indexContent.includes(file.replace('.md', ''))) {
        console.log(`  ⚠ ${prefix} - 文件 ${file} 未在 INDEX.md 中登记`);
        issues++;
      }
    }
    
    console.log(`  ✓ ${prefix} - ${cat.name} (${files.length} 文件)`);
  }
  
  // 检查主索引
  const mainIndex = join(MEMORY_ROOT, 'INDEX.md');
  if (!existsSync(mainIndex)) {
    console.log('  ✗ 主索引 memory/INDEX.md 不存在!');
    issues++;
  } else {
    console.log('  ✓ 主索引 INDEX.md 存在');
  }
  
  console.log(`\n校验完成: ${issues === 0 ? '全部通过' : `发现 ${issues} 个问题`}`);
}

// 主入口
const [,, command, ...args] = process.argv;

switch (command) {
  case 'search':
    if (!args[0]) { console.log('用法: memory-dispatch.mjs search <关键词>'); break; }
    searchMemory(args.join(' '));
    break;
  case 'list':
    if (args[0]) { listCategory(args[0]); } else { listCategories(); }
    break;
  case 'read':
    if (!args[0]) { console.log('用法: memory-dispatch.mjs read <编号> (如 SOC-001)'); break; }
    readEntry(args[0]);
    break;
  case 'verify':
    verifyIndex();
    break;
  default:
    console.log(`
记忆索引调度工具 v1.0

用法:
  node memory-dispatch.mjs search <关键词>     搜索相关分类和条目
  node memory-dispatch.mjs list [分类前缀]     列出分类或条目
  node memory-dispatch.mjs read <编号>         读取指定编号的条目
  node memory-dispatch.mjs verify              校验索引完整性

分类前缀: SOC SYS TRD DEV OPS ERR DAY
`);
}

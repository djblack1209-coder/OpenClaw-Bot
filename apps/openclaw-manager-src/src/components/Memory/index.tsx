/**
 * Memory — 记忆脑图页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  BrainCircuit,
  Database,
  Search,
  Zap,
  Clock,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import clsx from 'clsx';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 模拟数据 ====== */

/** 记忆条目 */
interface MemoryEntry {
  id: string;
  content: string;
  category: 'profile' | 'fact' | 'preference';
  source: string;
  importance: number;
  updatedAt: string;
}

const MEMORIES: MemoryEntry[] = [
  { id: 'm1', content: '用户是自由职业者，主要做量化交易和闲鱼倒卖', category: 'profile', source: 'telegram', importance: 5, updatedAt: '2分钟前' },
  { id: 'm2', content: '偏好使用 GPT-4o 模型，对 Claude 也感兴趣', category: 'preference', source: 'telegram', importance: 4, updatedAt: '15分钟前' },
  { id: 'm3', content: '持有 NVDA、AAPL、BTC 等资产，总仓位约12万美元', category: 'fact', source: 'trading', importance: 5, updatedAt: '1小时前' },
  { id: 'm4', content: '用户在深圳，时区 UTC+8', category: 'profile', source: 'system', importance: 3, updatedAt: '3小时前' },
  { id: 'm5', content: '闲鱼店铺主营二手数码产品，月均收入 ¥8,000+', category: 'fact', source: 'xianyu', importance: 4, updatedAt: '5小时前' },
  { id: 'm6', content: '喜欢使用终端风格 UI，不喜欢花哨的动画', category: 'preference', source: 'telegram', importance: 3, updatedAt: '1天前' },
  { id: 'm7', content: '最近在研究 Tauri 2 + React 桌面应用开发', category: 'fact', source: 'telegram', importance: 4, updatedAt: '2天前' },
  { id: 'm8', content: '投资风格偏激进，可接受 10% 以内的回撤', category: 'profile', source: 'trading', importance: 5, updatedAt: '3天前' },
];

/** 分类统计 */
const CATEGORIES = [
  { key: 'all', label: '全部', count: 847, color: 'var(--text-primary)' },
  { key: 'profile', label: '用户画像', count: 156, color: 'var(--accent-purple)' },
  { key: 'fact', label: '事实记录', count: 523, color: 'var(--accent-cyan)' },
  { key: 'preference', label: '偏好设定', count: 168, color: 'var(--accent-amber)' },
];

/* ====== 工具函数 ====== */

/** 分类颜色和标签 */
function categoryBadge(cat: MemoryEntry['category']) {
  switch (cat) {
    case 'profile': return { label: '画像', color: 'var(--accent-purple)', bg: 'rgba(168,85,247,0.1)' };
    case 'fact': return { label: '事实', color: 'var(--accent-cyan)', bg: 'rgba(6,182,212,0.1)' };
    case 'preference': return { label: '偏好', color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.1)' };
  }
}

/** 重要度渲染 */
function importanceDots(level: number): string {
  return '●'.repeat(level) + '○'.repeat(5 - level);
}

/* ====== 主组件 ====== */

export function Memory() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');

  /** 过滤后的记忆列表 */
  const filtered = MEMORIES.filter((m) => {
    const matchCat = activeCategory === 'all' || m.category === activeCategory;
    const matchSearch = !searchQuery || m.content.toLowerCase().includes(searchQuery.toLowerCase());
    return matchCat && matchSearch;
  });

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 记忆统计 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <BrainCircuit size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  MEMORY BRAIN
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  记忆库 // MEM0 VECTOR ENGINE
                </p>
              </div>
            </div>

            {/* 统计数据 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: '总条目', value: '847', icon: Layers, color: 'var(--accent-cyan)' },
                { label: '提取轮次', value: '1,256', icon: Zap, color: 'var(--accent-green)' },
                { label: '向量维度', value: '1,536', icon: Database, color: 'var(--accent-purple)' },
                { label: '今日新增', value: '23', icon: Clock, color: 'var(--accent-amber)' },
              ].map((s) => (
                <div key={s.label}>
                  <span className="text-label flex items-center gap-1">
                    <s.icon size={10} style={{ color: s.color }} />
                    {s.label}
                  </span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 分类筛选 */}
            <div className="flex gap-2 mb-4">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.key}
                  onClick={() => setActiveCategory(cat.key)}
                  className={clsx(
                    'px-3 py-1.5 rounded-lg font-mono text-xs transition-colors border',
                  )}
                  style={{
                    background: activeCategory === cat.key ? 'var(--bg-tertiary)' : 'transparent',
                    borderColor: activeCategory === cat.key ? 'var(--glass-border)' : 'transparent',
                    color: activeCategory === cat.key ? cat.color : 'var(--text-tertiary)',
                  }}
                >
                  {cat.label} ({cat.count})
                </button>
              ))}
            </div>

            {/* 记忆列表 */}
            <div className="flex-1 space-y-1.5">
              {filtered.map((mem) => {
                const badge = categoryBadge(mem.category);
                return (
                  <div
                    key={mem.id}
                    className="py-3 px-4 rounded-lg transition-colors"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold"
                            style={{ background: badge.bg, color: badge.color }}
                          >
                            {badge.label}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {importanceDots(mem.importance)}
                          </span>
                        </div>
                        <p className="font-mono text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                          {mem.content}
                        </p>
                        <div className="flex gap-3 mt-2">
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            来源: {mem.source}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {mem.updatedAt}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 右侧面板 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4 space-y-4" variants={cardVariants}>
          {/* 搜索框 */}
          <div className="abyss-card p-6">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              MEMORY SEARCH
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              记忆检索
            </h3>
            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--text-disabled)' }}
              />
              <input
                type="text"
                placeholder="搜索记忆片段..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full py-2.5 pl-10 pr-4 rounded-lg font-mono text-sm outline-none transition-colors"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <p className="font-mono text-[10px] mt-2" style={{ color: 'var(--text-disabled)' }}>
              支持语义搜索：输入自然语言即可匹配相关记忆
            </p>
          </div>

          {/* 向量数据库状态 */}
          <div className="abyss-card p-6">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              VECTOR DB
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              向量引擎状态
            </h3>
            <div className="space-y-3">
              {[
                { label: '引擎状态', value: '在线', color: 'var(--accent-green)', icon: CheckCircle2 },
                { label: '存储后端', value: 'Qdrant', color: 'var(--accent-cyan)', icon: Database },
                { label: '嵌入模型', value: 'text-3-small', color: 'var(--accent-purple)', icon: Zap },
                { label: '索引类型', value: 'HNSW', color: 'var(--accent-amber)', icon: Layers },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="flex items-center gap-2">
                    <item.icon size={12} style={{ color: item.color }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {item.label}
                    </span>
                  </span>
                  <span className="font-mono text-xs font-semibold" style={{ color: item.color }}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>

            {/* 冲突解决说明 */}
            <div
              className="mt-4 pt-3 border-t"
              style={{ borderColor: 'var(--glass-border)' }}
            >
              <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                Mem0 引擎自动检测记忆冲突：当新事实与旧记忆矛盾时，引擎会发送 UPDATE/DELETE 指令覆盖过时认知。
              </p>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

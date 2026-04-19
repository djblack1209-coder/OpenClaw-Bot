/**
 * Memory — 记忆脑图页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自真实后端 API（mem0 向量引擎）
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  BrainCircuit, Database, Search, Zap,
  Clock, Layers, Loader2, CheckCircle2,
} from 'lucide-react';
import { api } from '../../lib/api';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型定义 ====== */

interface MemoryEntry {
  id: string;
  memory?: string;
  content?: string;
  category?: string;
  metadata?: Record<string, any>;
  score?: number;
  created_at?: string;
  updated_at?: string;
}

interface MemStats {
  total_memories?: number;
  total?: number;
  categories?: Record<string, number>;
  vector_dim?: number;
  extraction_rounds?: number;
  today_added?: number;
  [key: string]: unknown;
}

/* ====== 分类映射 ====== */
const CATEGORY_META: Record<string, { label: string; color: string; bg: string }> = {
  profile:    { label: '画像', color: 'var(--accent-purple)', bg: 'rgba(168,85,247,0.1)' },
  fact:       { label: '事实', color: 'var(--accent-cyan)',   bg: 'rgba(6,182,212,0.1)' },
  preference: { label: '偏好', color: 'var(--accent-amber)',  bg: 'rgba(245,158,11,0.1)' },
};

function categoryBadge(cat?: string) {
  return CATEGORY_META[cat ?? ''] ?? { label: cat ?? '其他', color: 'var(--text-secondary)', bg: 'rgba(255,255,255,0.05)' };
}

/** 重要度渲染 */
function importanceDots(level: number): string {
  const clamped = Math.max(0, Math.min(5, Math.round(level)));
  return '●'.repeat(clamped) + '○'.repeat(5 - clamped);
}

/** 相对时间 */
function relativeTime(iso?: string): string {
  if (!iso) return '—';
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins}分钟前`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}小时前`;
    return `${Math.floor(hrs / 24)}天前`;
  } catch { return iso; }
}

/* ====== 主组件 ====== */

export function Memory() {
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [stats, setStats] = useState<MemStats>({});
  const [activeCategory, setActiveCategory] = useState('all');
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  /* —— 加载统计 + 初始记忆 —— */
  const fetchStats = useCallback(async () => {
    try {
      const [statsRes, searchRes] = await Promise.allSettled([
        api.clawbotMemoryStats(),
        api.clawbotMemorySearch('最近的记忆', 20),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value as MemStats);
      if (searchRes.status === 'fulfilled') {
        const raw = searchRes.value as any;
        const list = Array.isArray(raw) ? raw : raw?.results ?? raw?.memories ?? [];
        setMemories(list);
      }
    } catch (err) {
      console.error('[Memory] 加载失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  /* —— 搜索（防抖 500ms） —— */
  const doSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      /* 清空搜索时重新拉初始数据 */
      fetchStats();
      return;
    }
    setSearching(true);
    try {
      const raw = await api.clawbotMemorySearch(query, 20) as any;
      const list = Array.isArray(raw) ? raw : raw?.results ?? raw?.memories ?? [];
      setMemories(list);
    } catch (err) {
      console.error('[Memory] 搜索失败:', err);
    } finally {
      setSearching(false);
    }
  }, [fetchStats]);

  const onSearchChange = (val: string) => {
    setSearchQuery(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 500);
  };

  /* —— 过滤 —— */
  const filtered = memories.filter((m) => {
    if (activeCategory === 'all') return true;
    return m.category === activeCategory || m.metadata?.category === activeCategory;
  });

  /* —— 统计数字 —— */
  const totalCount = stats.total_memories ?? stats.total ?? memories.length;
  const categories = [
    { key: 'all', label: '全部', count: totalCount, color: 'var(--text-primary)' },
    { key: 'profile', label: '用户画像', count: stats.categories?.profile ?? 0, color: 'var(--accent-purple)' },
    { key: 'fact', label: '事实记录', count: stats.categories?.fact ?? 0, color: 'var(--accent-cyan)' },
    { key: 'preference', label: '偏好设定', count: stats.categories?.preference ?? 0, color: 'var(--accent-amber)' },
  ];

  /* —— 加载态 —— */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 记忆列表 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}>
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
                { label: '总条目', value: String(totalCount), icon: Layers, color: 'var(--accent-cyan)' },
                { label: '提取轮次', value: String(stats.extraction_rounds ?? '—'), icon: Zap, color: 'var(--accent-green)' },
                { label: '向量维度', value: String(stats.vector_dim ?? '—'), icon: Database, color: 'var(--accent-purple)' },
                { label: '今日新增', value: String(stats.today_added ?? '—'), icon: Clock, color: 'var(--accent-amber)' },
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
              {categories.map((cat) => (
                <button key={cat.key}
                  onClick={() => setActiveCategory(cat.key)}
                  className="px-3 py-1.5 rounded-lg font-mono text-xs transition-colors border"
                  style={{
                    background: activeCategory === cat.key ? 'var(--bg-tertiary)' : 'transparent',
                    borderColor: activeCategory === cat.key ? 'var(--glass-border)' : 'transparent',
                    color: activeCategory === cat.key ? cat.color : 'var(--text-tertiary)',
                  }}>
                  {cat.label} ({cat.count})
                </button>
              ))}
            </div>

            {/* 记忆列表 */}
            <div className="flex-1 space-y-1.5">
              {filtered.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {searchQuery ? '没有找到匹配的记忆' : '暂无记忆数据'}
                </div>
              )}
              {filtered.map((mem) => {
                const cat = mem.category ?? mem.metadata?.category ?? '';
                const badge = categoryBadge(cat);
                const text = mem.memory ?? mem.content ?? '(空)';
                const source = mem.metadata?.source ?? '—';
                const importance = mem.score != null ? Math.round(mem.score * 5) : 3;
                return (
                  <div key={mem.id}
                    className="py-3 px-4 rounded-lg transition-colors"
                    style={{ background: 'var(--bg-secondary)' }}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold"
                            style={{ background: badge.bg, color: badge.color }}>
                            {badge.label}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {importanceDots(importance)}
                          </span>
                        </div>
                        <p className="font-mono text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                          {text}
                        </p>
                        <div className="flex gap-3 mt-2">
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            来源: {source}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {relativeTime(mem.updated_at ?? mem.created_at)}
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
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>MEMORY SEARCH</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              记忆检索
            </h3>
            <div className="relative">
              {searching
                ? <Loader2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 animate-spin"
                    style={{ color: 'var(--accent-cyan)' }} />
                : <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
                    style={{ color: 'var(--text-disabled)' }} />}
              <input type="text"
                placeholder="搜索记忆片段..."
                value={searchQuery}
                onChange={(e) => onSearchChange(e.target.value)}
                className="w-full py-2.5 pl-10 pr-4 rounded-lg font-mono text-sm outline-none transition-colors"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-primary)',
                }} />
            </div>
            <p className="font-mono text-[10px] mt-2" style={{ color: 'var(--text-disabled)' }}>
              支持语义搜索：输入自然语言即可匹配相关记忆
            </p>
          </div>

          {/* 向量数据库状态 */}
          <div className="abyss-card p-6">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>VECTOR DB</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              向量引擎状态
            </h3>
            <div className="space-y-3">
              {[
                { label: '引擎状态', value: '在线', color: 'var(--accent-green)', icon: CheckCircle2 },
                { label: '总记忆数', value: String(totalCount), color: 'var(--accent-cyan)', icon: Database },
                { label: '向量维度', value: String(stats.vector_dim ?? '—'), color: 'var(--accent-purple)', icon: Zap },
                { label: '今日新增', value: String(stats.today_added ?? '—'), color: 'var(--accent-amber)', icon: Layers },
              ].map((item) => (
                <div key={item.label}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}>
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
            <div className="mt-4 pt-3 border-t" style={{ borderColor: 'var(--glass-border)' }}>
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

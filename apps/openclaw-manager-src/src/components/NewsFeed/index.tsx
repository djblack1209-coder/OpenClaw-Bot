/**
 * NewsFeed — 新闻聚合中心
 * 12 列 Bento Grid 布局，Sonic Abyss 终端美学
 * 包含：新闻列表、威胁雷达、来源排行、分类统计、AI 摘要
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Newspaper,
  ShieldAlert,
  Radio,
  BarChart3,
  Sparkles,
  TrendingUp,
  AlertTriangle,
  Clock,
} from 'lucide-react';

/* ====== 类型定义 ====== */

/** 新闻分类 */
type NewsCategory =
  | 'ALL'
  | 'FINANCE'
  | 'TECH'
  | 'GEOPOLITICS'
  | 'CRYPTO'
  | 'MILITARY'
  | 'ENERGY';

/** 单条新闻 */
interface NewsItem {
  id: string;
  source: string;
  title: string;
  timeAgo: string;
  category: NewsCategory;
}

/** 威胁等级 */
type ThreatLevel = 'LOW' | 'MODERATE' | 'ELEVATED';

/** 来源排行 */
interface TopSource {
  name: string;
  count: number;
}

/** 分类统计 */
interface CategoryStat {
  name: string;
  count: number;
  color: string;
}

/* ====== 分类配色表 ====== */
const CATEGORY_COLORS: Record<NewsCategory, string> = {
  ALL: 'var(--accent-cyan)',
  FINANCE: 'var(--accent-green)',
  TECH: 'var(--accent-cyan)',
  GEOPOLITICS: 'var(--accent-red)',
  CRYPTO: 'var(--accent-amber)',
  MILITARY: 'var(--accent-red)',
  ENERGY: 'var(--accent-purple)',
};

/* ====== 模拟数据 ====== */

/** 8 条模拟新闻，覆盖不同分类 */
const MOCK_NEWS: NewsItem[] = [
  {
    id: '1',
    source: 'REUTERS',
    title: 'Federal Reserve signals potential rate cut amid slowing inflation data',
    timeAgo: '12 min ago',
    category: 'FINANCE',
  },
  {
    id: '2',
    source: 'COINDESK',
    title: 'Bitcoin surges past $98,000 as institutional inflows reach record high',
    timeAgo: '24 min ago',
    category: 'CRYPTO',
  },
  {
    id: '3',
    source: 'BBC WORLD',
    title: 'EU imposes new sanctions on Russian energy exports amid escalating tensions',
    timeAgo: '38 min ago',
    category: 'GEOPOLITICS',
  },
  {
    id: '4',
    source: 'TECHCRUNCH',
    title: 'OpenAI announces GPT-5 with real-time multimodal reasoning capabilities',
    timeAgo: '1 hr ago',
    category: 'TECH',
  },
  {
    id: '5',
    source: 'BLOOMBERG',
    title: 'NVIDIA market cap exceeds $5T on accelerating data center demand',
    timeAgo: '1.5 hr ago',
    category: 'FINANCE',
  },
  {
    id: '6',
    source: 'JANE\'S',
    title: 'Pentagon awards $12B contract for next-generation autonomous drone fleet',
    timeAgo: '2 hr ago',
    category: 'MILITARY',
  },
  {
    id: '7',
    source: 'IEA',
    title: 'Global renewable energy capacity surpasses fossil fuels for first time',
    timeAgo: '3 hr ago',
    category: 'ENERGY',
  },
  {
    id: '8',
    source: 'FT',
    title: 'China central bank unexpectedly cuts reserve ratio to boost economic growth',
    timeAgo: '4 hr ago',
    category: 'FINANCE',
  },
];

/** 模拟来源排行 */
const MOCK_TOP_SOURCES: TopSource[] = [
  { name: 'Reuters', count: 12 },
  { name: 'BBC World', count: 8 },
  { name: 'CoinDesk', count: 6 },
  { name: 'Bloomberg', count: 5 },
  { name: 'TechCrunch', count: 4 },
  { name: 'Financial Times', count: 3 },
];

/** 模拟分类统计 */
const MOCK_CATEGORY_STATS: CategoryStat[] = [
  { name: 'Finance', count: 18, color: 'var(--accent-green)' },
  { name: 'Tech', count: 14, color: 'var(--accent-cyan)' },
  { name: 'Geopolitics', count: 11, color: 'var(--accent-red)' },
  { name: 'Crypto', count: 9, color: 'var(--accent-amber)' },
  { name: 'Military', count: 5, color: 'var(--accent-red)' },
  { name: 'Energy', count: 4, color: 'var(--accent-purple)' },
];

/** 模拟热门话题 */
const MOCK_TRENDING = [
  { topic: 'Federal Reserve Policy', delta: '+340%' },
  { topic: 'Bitcoin ETF Inflows', delta: '+210%' },
  { topic: 'EU-Russia Sanctions', delta: '+180%' },
];

/** 模拟 AI 摘要 */
const MOCK_AI_SUMMARY =
  'Global markets are reacting strongly to the Federal Reserve\'s latest policy signals, with equity indices reaching new highs. Crypto markets continue their bullish momentum as institutional adoption accelerates. Geopolitical tensions between the EU and Russia are intensifying, with new sanctions targeting energy exports. Meanwhile, the AI sector sees major breakthroughs with GPT-5 launch driving tech valuations higher.';

/* ====== 入场动画配置 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] },
  },
};

/* ====== 分类标签数组 ====== */
const CATEGORIES: NewsCategory[] = [
  'ALL',
  'FINANCE',
  'TECH',
  'GEOPOLITICS',
  'CRYPTO',
  'MILITARY',
  'ENERGY',
];

/* ====== 威胁等级配色 ====== */
const THREAT_CONFIG: Record<ThreatLevel, { color: string; bg: string }> = {
  LOW: { color: 'var(--accent-green)', bg: 'rgba(52, 211, 153, 0.08)' },
  MODERATE: { color: 'var(--accent-amber)', bg: 'rgba(251, 191, 36, 0.08)' },
  ELEVATED: { color: 'var(--accent-red)', bg: 'rgba(248, 113, 113, 0.08)' },
};

/* ====== 新闻威胁计数 ====== */
const THREAT_COUNTS = {
  critical: 2,
  high: 5,
  medium: 12,
  low: 42,
};

/**
 * NewsFeed 新闻聚合中心
 * 12 列 Bento Grid，融合 RSS 聚合 + AI 分析 + 威胁评估
 */
export function NewsFeed() {
  /* 当前选中的分类筛选 */
  const [activeCategory, setActiveCategory] = useState<NewsCategory>('ALL');

  /* 当前威胁等级（模拟） */
  const threatLevel: ThreatLevel = 'MODERATE';

  /* 根据分类过滤新闻列表 */
  const filteredNews =
    activeCategory === 'ALL'
      ? MOCK_NEWS
      : MOCK_NEWS.filter((n) => n.category === activeCategory);

  /* 分类统计最大值，用于横向条占比计算 */
  const maxCategoryCount = Math.max(...MOCK_CATEGORY_STATS.map((c) => c.count));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ═══════════════════════════════════
         * 第一行：新闻列表 (span-8) + 威胁雷达 (span-4)
         * ═══════════════════════════════════ */}

        {/* 新闻聚合器 — 主卡片 */}
        <motion.div
          className="col-span-12 lg:col-span-8"
          variants={cardVariants}
        >
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题区 */}
            <div className="flex items-center gap-3 mb-1">
              <Newspaper
                size={16}
                style={{ color: 'var(--accent-cyan)' }}
              />
              <span
                className="text-label"
                style={{ color: 'var(--accent-cyan)' }}
              >
                AI NEWS AGGREGATOR
              </span>
            </div>
            <p
              className="font-mono text-[11px] mb-4"
              style={{ color: 'var(--text-tertiary)' }}
            >
              435+ RSS FEEDS // 15 CATEGORIES
            </p>

            {/* 分类筛选条 */}
            <div className="flex flex-wrap gap-2 mb-4">
              {CATEGORIES.map((cat) => {
                const isActive = activeCategory === cat;
                const color = CATEGORY_COLORS[cat];
                return (
                  <button
                    key={cat}
                    onClick={() => setActiveCategory(cat)}
                    className={clsx(
                      'px-3 py-1 rounded-full font-mono text-[10px] uppercase tracking-wider',
                      'transition-all duration-200 border',
                    )}
                    style={{
                      borderColor: isActive ? color : 'var(--glass-border)',
                      background: isActive ? `${color}15` : 'transparent',
                      color: isActive ? color : 'var(--text-tertiary)',
                    }}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>

            {/* 新闻列表 — 可滚动 */}
            <div className="flex-1 overflow-y-auto space-y-1 min-h-0 max-h-[420px] scroll-container">
              {filteredNews.map((item, idx) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.04, duration: 0.25 }}
                  className="flex items-start gap-3 p-3 rounded-lg transition-colors duration-150"
                  style={{ background: 'rgba(255,255,255,0.015)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.015)';
                  }}
                >
                  {/* 左侧：来源 + 标题 */}
                  <div className="flex-1 min-w-0">
                    <span
                      className="font-mono text-[10px] uppercase tracking-wider"
                      style={{ color: 'var(--text-disabled)' }}
                    >
                      {item.source}
                    </span>
                    <h4
                      className="font-display text-sm font-medium mt-0.5 leading-snug"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {item.title}
                    </h4>
                  </div>

                  {/* 右侧：时间 + 分类标签 */}
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <span
                      className="font-mono text-[10px] whitespace-nowrap"
                      style={{ color: 'var(--text-disabled)' }}
                    >
                      {item.timeAgo}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded-full font-mono text-[9px] uppercase tracking-wider"
                      style={{
                        color: CATEGORY_COLORS[item.category],
                        background: `${CATEGORY_COLORS[item.category]}12`,
                        border: `1px solid ${CATEGORY_COLORS[item.category]}30`,
                      }}
                    >
                      {item.category}
                    </span>
                  </div>
                </motion.div>
              ))}

              {/* 筛选后无结果 */}
              {filteredNews.length === 0 && (
                <div className="flex items-center justify-center py-12">
                  <span
                    className="font-mono text-xs"
                    style={{ color: 'var(--text-disabled)' }}
                  >
                    NO ARTICLES IN THIS CATEGORY
                  </span>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* 威胁雷达 */}
        <motion.div
          className="col-span-12 lg:col-span-4"
          variants={cardVariants}
        >
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题 */}
            <div className="flex items-center gap-3 mb-4">
              <ShieldAlert
                size={16}
                style={{ color: 'var(--accent-amber)' }}
              />
              <span
                className="text-label"
                style={{ color: 'var(--accent-amber)' }}
              >
                THREAT RADAR
              </span>
            </div>

            {/* 威胁等级指示器 */}
            <div
              className="rounded-xl p-5 text-center mb-5"
              style={{
                background: THREAT_CONFIG[threatLevel].bg,
                border: `1px solid ${THREAT_CONFIG[threatLevel].color}25`,
              }}
            >
              <AlertTriangle
                size={28}
                style={{ color: THREAT_CONFIG[threatLevel].color }}
                className="mx-auto mb-2"
              />
              <div
                className="font-display text-2xl font-bold tracking-wider"
                style={{ color: THREAT_CONFIG[threatLevel].color }}
              >
                {threatLevel}
              </div>
              <p
                className="font-mono text-[10px] mt-1"
                style={{ color: 'var(--text-tertiary)' }}
              >
                CURRENT ASSESSMENT
              </p>
            </div>

            {/* 严重性分布 */}
            <div className="space-y-2.5 mb-5">
              {[
                {
                  label: 'CRITICAL',
                  count: THREAT_COUNTS.critical,
                  color: 'var(--accent-red)',
                },
                {
                  label: 'HIGH',
                  count: THREAT_COUNTS.high,
                  color: 'var(--accent-amber)',
                },
                {
                  label: 'MEDIUM',
                  count: THREAT_COUNTS.medium,
                  color: 'var(--accent-cyan)',
                },
                {
                  label: 'LOW',
                  count: THREAT_COUNTS.low,
                  color: 'var(--accent-green)',
                },
              ].map((s) => (
                <div
                  key={s.label}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: s.color }}
                    />
                    <span
                      className="font-mono text-[10px] uppercase tracking-wider"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {s.label}
                    </span>
                  </div>
                  <span
                    className="font-mono text-sm font-semibold"
                    style={{ color: s.color }}
                  >
                    {s.count}
                  </span>
                </div>
              ))}
            </div>

            {/* 热门话题 */}
            <div className="mt-auto">
              <span
                className="text-label mb-2 block"
                style={{ color: 'var(--text-tertiary)' }}
              >
                TRENDING TOPICS
              </span>
              <div className="space-y-2">
                {MOCK_TRENDING.map((t, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-2 rounded-lg"
                    style={{ background: 'rgba(255,255,255,0.02)' }}
                  >
                    <div className="flex items-center gap-2">
                      <TrendingUp
                        size={12}
                        style={{ color: 'var(--accent-green)' }}
                      />
                      <span
                        className="font-mono text-xs"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {t.topic}
                      </span>
                    </div>
                    <span
                      className="font-mono text-[10px] font-semibold"
                      style={{ color: 'var(--accent-green)' }}
                    >
                      {t.delta}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ═══════════════════════════════════
         * 第二行：来源排行 (span-4) + 分类统计 (span-4) + AI 摘要 (span-4)
         * ═══════════════════════════════════ */}

        {/* 来源排行 */}
        <motion.div
          className="col-span-12 md:col-span-6 lg:col-span-4"
          variants={cardVariants}
        >
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <Radio
                size={16}
                style={{ color: 'var(--accent-cyan)' }}
              />
              <span
                className="text-label"
                style={{ color: 'var(--accent-cyan)' }}
              >
                TOP SOURCES
              </span>
            </div>

            <div className="space-y-3">
              {MOCK_TOP_SOURCES.map((src, i) => (
                <div
                  key={src.name}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    {/* 排名序号 */}
                    <span
                      className="font-mono text-[10px] w-4 text-right"
                      style={{
                        color:
                          i < 3
                            ? 'var(--accent-cyan)'
                            : 'var(--text-disabled)',
                      }}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span
                      className="font-mono text-xs"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {src.name}
                    </span>
                  </div>
                  <span
                    className="font-mono text-sm font-semibold"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {src.count}
                  </span>
                </div>
              ))}
            </div>

            {/* 底部统计 */}
            <div
              className="mt-4 pt-3 flex items-center justify-between"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--text-disabled)' }}
              >
                TOTAL SOURCES ACTIVE
              </span>
              <span
                className="font-mono text-xs font-semibold"
                style={{ color: 'var(--accent-cyan)' }}
              >
                38
              </span>
            </div>
          </div>
        </motion.div>

        {/* 分类统计 */}
        <motion.div
          className="col-span-12 md:col-span-6 lg:col-span-4"
          variants={cardVariants}
        >
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <BarChart3
                size={16}
                style={{ color: 'var(--accent-green)' }}
              />
              <span
                className="text-label"
                style={{ color: 'var(--accent-green)' }}
              >
                CATEGORY BREAKDOWN
              </span>
            </div>

            <div className="space-y-3">
              {MOCK_CATEGORY_STATS.map((cat) => (
                <div key={cat.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="font-mono text-xs"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {cat.name}
                    </span>
                    <span
                      className="font-mono text-[10px] font-semibold"
                      style={{ color: cat.color }}
                    >
                      {cat.count}
                    </span>
                  </div>
                  {/* 横向进度条 */}
                  <div
                    className="h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'rgba(255,255,255,0.04)' }}
                  >
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: cat.color }}
                      initial={{ width: 0 }}
                      animate={{
                        width: `${(cat.count / maxCategoryCount) * 100}%`,
                      }}
                      transition={{ duration: 0.6, ease: 'easeOut', delay: 0.3 }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* 底部统计 */}
            <div
              className="mt-4 pt-3 flex items-center justify-between"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--text-disabled)' }}
              >
                TOTAL ARTICLES TODAY
              </span>
              <span
                className="font-mono text-xs font-semibold"
                style={{ color: 'var(--accent-green)' }}
              >
                {MOCK_CATEGORY_STATS.reduce((a, c) => a + c.count, 0)}
              </span>
            </div>
          </div>
        </motion.div>

        {/* AI 摘要 */}
        <motion.div
          className="col-span-12 lg:col-span-4"
          variants={cardVariants}
        >
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <Sparkles
                size={16}
                style={{ color: 'var(--accent-purple)' }}
              />
              <span
                className="text-label"
                style={{ color: 'var(--accent-purple)' }}
              >
                AI DAILY BRIEF
              </span>
            </div>

            {/* 摘要正文 */}
            <p
              className="font-body text-sm leading-relaxed flex-1"
              style={{
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-body)',
              }}
            >
              {MOCK_AI_SUMMARY}
            </p>

            {/* 底部元信息 */}
            <div
              className="mt-4 pt-3 flex items-center justify-between"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <div className="flex items-center gap-1.5">
                <Clock
                  size={11}
                  style={{ color: 'var(--text-disabled)' }}
                />
                <span
                  className="font-mono text-[10px]"
                  style={{ color: 'var(--text-disabled)' }}
                >
                  GENERATED 8 MIN AGO
                </span>
              </div>
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--accent-purple)' }}
              >
                GPT-4o
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

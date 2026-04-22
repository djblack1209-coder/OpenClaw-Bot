/**
 * NewsFeed — 新闻聚合中心
 * 12 列 Bento Grid 布局，Sonic Abyss 终端美学
 * 包含：新闻列表、威胁雷达、来源排行、分类统计、AI 摘要
 * 数据来自后端 /api/v1/monitor/news，每 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

/** HTML 实体解码（处理 &#8217; &#039; &amp; 等） */
function decodeHtmlEntities(text: string): string {
  if (!text || !text.includes('&')) return text;
  const el = document.createElement('textarea');
  el.innerHTML = text;
  return el.value;
}
import {
  Newspaper,
  ShieldAlert,
  Radio,
  BarChart3,
  Sparkles,
  TrendingUp,
  AlertTriangle,
  Clock,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

/* ====== 自动刷新间隔（毫秒） ====== */
const REFRESH_INTERVAL = 30_000;

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

/** API 返回的新闻条目 */
interface NewsApiItem {
  title: string;
  url: string;
  source: string;
  category: string;
  published_at: string;
  summary: string;
  threat_level: string;
}

/** 内部显示用的新闻条目 */
interface NewsItem {
  id: string;
  source: string;
  title: string;
  url: string;
  summary: string;
  timeAgo: string;
  category: NewsCategory;
  threatLevel: string;
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

/* ====== 分类映射：API category 字符串 → 内部 NewsCategory ====== */
function mapCategory(cat: string): NewsCategory {
  const upper = cat.toUpperCase();
  if (upper.includes('FINANCE') || upper.includes('ECON')) return 'FINANCE';
  if (upper.includes('TECH') || upper.includes('AI') || upper.includes('CYBER')) return 'TECH';
  if (upper.includes('GEOPOLIT') || upper.includes('POLITIC')) return 'GEOPOLITICS';
  if (upper.includes('CRYPTO') || upper.includes('BITCOIN') || upper.includes('BLOCKCHAIN')) return 'CRYPTO';
  if (upper.includes('MILIT') || upper.includes('DEFENSE') || upper.includes('WAR')) return 'MILITARY';
  if (upper.includes('ENERGY') || upper.includes('OIL') || upper.includes('GAS')) return 'ENERGY';
  return 'GEOPOLITICS'; // 默认归类
}

/** 把 ISO 时间转为中文相对时间 */
function timeAgo(isoStr: string): string {
  try {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins} 分钟前`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} 小时前`;
    const days = Math.floor(hrs / 24);
    return `${days} 天前`;
  } catch {
    return '—';
  }
}

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

/* ====== 错误/加载状态组件 ====== */
function LoadingState({ message }: { message?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8">
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{message}</span>
    </div>
  );
}

function ErrorState({ message, onRetry, retryLabel = 'Retry' }: { message?: string; onRetry: () => void; retryLabel?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <AlertTriangle size={20} style={{ color: 'var(--accent-red)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--accent-red)' }}>{message}</span>
      <button
        onClick={onRetry}
        className="px-4 py-1.5 rounded-lg font-mono text-[11px] transition-all duration-200"
        style={{
          background: 'rgba(255, 0, 60, 0.1)',
          color: 'var(--accent-red)',
          border: '1px solid rgba(255, 0, 60, 0.25)',
        }}
      >
        <RefreshCw size={12} className="inline mr-1.5" />
        {retryLabel}
      </button>
    </div>
  );
}

/**
 * NewsFeed 新闻聚合中心
 * 12 列 Bento Grid，融合 RSS 聚合 + AI 分析 + 威胁评估
 * 数据来自 /api/v1/monitor/news
 */
export function NewsFeed() {
  const { t, lang } = useLanguage();
  /* ====== 状态 ====== */
  const [activeCategory, setActiveCategory] = useState<NewsCategory>('ALL');
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  /** 从后端拉取新闻数据 */
  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const resp = await clawbotFetchJson<{ items: NewsApiItem[] }>(
        '/api/v1/monitor/news?limit=50'
      );

      const items: NewsItem[] = (resp.items ?? []).map((item, idx) => ({
        id: String(idx + 1),
        source: item.source?.toUpperCase() ?? 'UNKNOWN',
        title: decodeHtmlEntities(item.title ?? ''),
        url: item.url ?? '',
        summary: decodeHtmlEntities(item.summary ?? ''),
        timeAgo: timeAgo(item.published_at),
        category: mapCategory(item.category ?? ''),
        threatLevel: item.threat_level ?? 'low',
      }));

      setNewsItems(items);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const friendly = (await import('../../lib/errorMessages')).toFriendlyError(err);
      setError(`${friendly.title}: ${friendly.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  /* 首次加载 + 定时刷新 */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ====== 衍生数据 ====== */

  /** 根据分类过滤新闻列表 */
  const filteredNews = useMemo(() => {
    if (activeCategory === 'ALL') return newsItems;
    return newsItems.filter((n) => n.category === activeCategory);
  }, [newsItems, activeCategory]);

  /** 从新闻条目中计算来源排行 */
  const topSources = useMemo<TopSource[]>(() => {
    const counts: Record<string, number> = {};
    for (const item of newsItems) {
      const src = item.source || 'UNKNOWN';
      counts[src] = (counts[src] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [newsItems]);

  /** 从新闻条目中计算分类统计 */
  const categoryStats = useMemo<CategoryStat[]>(() => {
    const colorMap: Record<string, string> = {
      FINANCE: 'var(--accent-green)',
      TECH: 'var(--accent-cyan)',
      GEOPOLITICS: 'var(--accent-red)',
      CRYPTO: 'var(--accent-amber)',
      MILITARY: 'var(--accent-red)',
      ENERGY: 'var(--accent-purple)',
    };
    const counts: Record<string, number> = {};
    for (const item of newsItems) {
      if (item.category !== 'ALL') {
        counts[item.category] = (counts[item.category] || 0) + 1;
      }
    }
    return Object.entries(counts)
      .map(([name, count]) => ({
        name,
        count,
        color: colorMap[name] || 'var(--text-tertiary)',
      }))
      .sort((a, b) => b.count - a.count);
  }, [newsItems]);

  /** 从新闻标题中提取热门话题（简单频率分析） */
  const trending = useMemo(() => {
    /* 统计分类出现频率，取变化最大的前 3 */
    const catCounts: Record<string, number> = {};
    for (const item of newsItems) {
      if (item.category !== 'ALL') {
        catCounts[item.category] = (catCounts[item.category] || 0) + 1;
      }
    }
    return Object.entries(catCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([topic, count]) => ({
        topic,
        delta: `${count} ${t('newsFeed.articles')}`,
      }));
  }, [newsItems]);

  /** AI 摘要 — 组合前 3 条新闻的 summary */
  const aiSummary = useMemo(() => {
    const summaries = newsItems
      .filter((n) => n.summary)
      .slice(0, 3)
      .map((n) => n.summary);
    return summaries.length > 0
      ? summaries.join(' ')
      : t('newsFeed.noSummary');
  }, [newsItems]);

  /** 威胁等级统计 */
  const threatCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const item of newsItems) {
      const level = item.threatLevel?.toLowerCase() ?? 'low';
      if (level.includes('critical')) counts.critical++;
      else if (level.includes('high')) counts.high++;
      else if (level.includes('medium') || level.includes('moderate')) counts.medium++;
      else counts.low++;
    }
    return counts;
  }, [newsItems]);

  /** 当前威胁等级 */
  const threatLevel: ThreatLevel = useMemo(() => {
    if (threatCounts.critical > 0) return 'ELEVATED';
    if (threatCounts.high > 2) return 'ELEVATED';
    if (threatCounts.high > 0 || threatCounts.medium > 5) return 'MODERATE';
    return 'LOW';
  }, [threatCounts]);

  /** 分类统计最大值，用于横向条占比计算 */
  const maxCategoryCount = Math.max(...categoryStats.map((c) => c.count), 1);

  /* ====== 加载/错误状态 ====== */
  if (loading && newsItems.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <LoadingState message={t('newsFeed.loadingNews')} />
        </div>
      </div>
    );
  }

  if (error && newsItems.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <ErrorState message={`${t('newsFeed.loadFailed')}: ${error}`} onRetry={fetchData} retryLabel={t('common.retry')} />
        </div>
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
                {t('newsFeed.aiNewsAggregation')}
              </span>
              {lastUpdated && (
                <span className="flex items-center gap-1 ml-auto">
                  <Clock size={10} style={{ color: 'var(--text-disabled)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    {t('newsFeed.lastUpdate')} {lastUpdated.toLocaleTimeString(lang === 'en-US' ? 'en-US' : 'zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </span>
              )}
            </div>
            <p
              className="font-mono text-[11px] mb-4"
              style={{ color: 'var(--text-tertiary)' }}
            >
              {newsItems.length} {t('newsFeed.newsCount')} // {topSources.length} {t('newsFeed.sourcesCount')} // {t('newsFeed.autoRefresh30s')}
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
                      {item.url ? (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline"
                          style={{ color: 'inherit' }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {item.title}
                        </a>
                      ) : item.title}
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
                    {t('newsFeed.noCategoryArticles')}
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
                {t('newsFeed.threatRadar')}
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
                {t('newsFeed.currentAssessment')}
              </p>
            </div>

            {/* 严重性分布 */}
            <div className="space-y-2.5 mb-5">
              {[
                { label: t('newsFeed.severityCritical'), count: threatCounts.critical, color: 'var(--accent-red)' },
                { label: t('newsFeed.severityHigh'), count: threatCounts.high, color: 'var(--accent-amber)' },
                { label: t('newsFeed.severityMedium'), count: threatCounts.medium, color: 'var(--accent-cyan)' },
                { label: t('newsFeed.severityLow'), count: threatCounts.low, color: 'var(--accent-green)' },
              ].map((s) => (
                <div key={s.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
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
                {t('newsFeed.trendingTopics')}
              </span>
              <div className="space-y-2">
                {trending.map((t, i) => (
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
                {t('newsFeed.topSources')}
              </span>
            </div>

            <div className="space-y-3">
              {topSources.map((src, i) => (
                <div
                  key={src.name}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className="font-mono text-[10px] w-4 text-right"
                      style={{
                        color: i < 3 ? 'var(--accent-cyan)' : 'var(--text-disabled)',
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
                {t('newsFeed.activeSourcesTotal')}
              </span>
              <span
                className="font-mono text-xs font-semibold"
                style={{ color: 'var(--accent-cyan)' }}
              >
                {topSources.length}
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
                {t('newsFeed.categoryStats')}
              </span>
            </div>

            <div className="space-y-3">
              {categoryStats.map((cat) => (
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
                {t('newsFeed.totalArticles')}
              </span>
              <span
                className="font-mono text-xs font-semibold"
                style={{ color: 'var(--accent-green)' }}
              >
                {newsItems.length}
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
                {t('newsFeed.aiDailySummary')}
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
              {aiSummary}
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
                  {t('newsFeed.autoRefresh30s')}
                </span>
              </div>
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--accent-purple)' }}
              >
                {t('newsFeed.aiSummaryLabel')}
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

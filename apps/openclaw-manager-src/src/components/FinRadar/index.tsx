/**
 * FinRadar — 金融雷达页面
 * Sonic Abyss 终端美学，12 列 Bento Grid 布局
 * 展示全球市场指数、加密货币、大宗商品、外汇实时数据
 * 数据来自后端 /api/v1/monitor/finance/* API，每 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Zap,
  Globe,
  Layers,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

/* ====== 自动刷新间隔（毫秒） ====== */
const REFRESH_INTERVAL = 30_000;

/* ====== 类型定义 ====== */

/** API 返回的报价条目 */
interface QuoteApiItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  [key: string]: unknown;
}

/** 内部市场数据条目 */
interface MarketEntry {
  symbol: string;
  name: string;
  price: string;
  change: number;
}

/** Tab 类型 */
type TabKey = 'indices' | 'crypto' | 'commodities' | 'forex';

/** 涨跌幅条目（Top Movers） */
interface MoverEntry {
  symbol: string;
  name: string;
  change: number;
}

/** 板块表现条目 */
interface SectorEntry {
  name: string;
  change: number;
}

/* ====== Tab 标签配置 ====== */
const TAB_CONFIG: { key: TabKey; labelKey: string; endpoint: string }[] = [
  { key: 'indices', labelKey: 'finRadar.tabIndices', endpoint: '/api/v1/monitor/finance/indices' },
  { key: 'crypto', labelKey: 'finRadar.tabCrypto', endpoint: '/api/v1/monitor/finance/crypto' },
  { key: 'commodities', labelKey: 'finRadar.tabCommodities', endpoint: '/api/v1/monitor/finance/commodities' },
  { key: 'forex', labelKey: 'finRadar.tabForex', endpoint: '/api/v1/monitor/finance/forex' },
];

/* ====== 入场动画 ====== */

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 辅助函数 ====== */

/** 根据涨跌返回对应颜色 */
function changeColor(val: number): string {
  if (val > 0) return 'var(--accent-green)';
  if (val < 0) return 'var(--accent-red)';
  return 'var(--text-secondary)';
}

/** 格式化涨跌幅为带符号字符串 */
function formatChange(val: number): string {
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

/** 格式化价格数字为带逗号的字符串 */
function formatPrice(price: number): string {
  if (price >= 1000) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (price >= 1) {
    return price.toFixed(2);
  }
  return price.toFixed(4);
}

/** 把 API 返回的报价转为内部格式 */
function quoteToEntry(item: QuoteApiItem): MarketEntry {
  return {
    symbol: item.symbol,
    name: item.name,
    price: formatPrice(item.price ?? 0),
    change: item.change_pct ?? item.change ?? 0,
  };
}

/* ====== 错误/加载状态组件 ====== */
function LoadingState({ message = '数据加载中...' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8">
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{message}</span>
    </div>
  );
}

function ErrorState({ message = '数据加载失败', onRetry }: { message?: string; onRetry: () => void }) {
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
        重试
      </button>
    </div>
  );
}

/* ====== 主组件 ====== */

export function FinRadar() {
  const { t } = useLanguage();
  /* 当前激活的 Tab */
  const [activeTab, setActiveTab] = useState<TabKey>('indices');

  /* 各 Tab 的市场数据 */
  const [marketData, setMarketData] = useState<Record<TabKey, MarketEntry[]>>({
    indices: [],
    crypto: [],
    commodities: [],
    forex: [],
  });

  /* 加载与错误状态（按 Tab 独立） */
  const [loadingTabs, setLoadingTabs] = useState<Record<TabKey, boolean>>({
    indices: true,
    crypto: true,
    commodities: true,
    forex: true,
  });
  const [errorTabs, setErrorTabs] = useState<Record<TabKey, string | null>>({
    indices: null,
    crypto: null,
    commodities: null,
    forex: null,
  });

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** 拉取单个 Tab 的数据 */
  const fetchTab = useCallback(async (tab: typeof TAB_CONFIG[number]) => {
    try {
      setErrorTabs((prev) => ({ ...prev, [tab.key]: null }));
      const resp = await clawbotFetchJson<{ quotes: QuoteApiItem[] }>(tab.endpoint);
      const entries = (resp.quotes ?? []).map(quoteToEntry);
      setMarketData((prev) => ({ ...prev, [tab.key]: entries }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'unknown error';
      setErrorTabs((prev) => ({ ...prev, [tab.key]: msg }));
    } finally {
      setLoadingTabs((prev) => ({ ...prev, [tab.key]: false }));
    }
  }, []);

  /** 拉取所有 Tab 数据 */
  const fetchAllData = useCallback(async () => {
    await Promise.all(TAB_CONFIG.map(fetchTab));
  }, [fetchTab]);

  /* 首次加载 + 定时刷新 */
  useEffect(() => {
    fetchAllData();
    timerRef.current = setInterval(fetchAllData, REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAllData]);

  /* ====== 衍生数据 ====== */

  /** 当前 Tab 对应的市场数据 */
  const currentData = marketData[activeTab];
  const currentLoading = loadingTabs[activeTab];
  const currentError = errorTabs[activeTab];

  /** 把所有 Tab 的数据合并，计算涨跌榜 */
  const allEntries = useMemo<MarketEntry[]>(() => {
    return Object.values(marketData).flat();
  }, [marketData]);

  /** Top Gainers — 涨幅前 3 */
  const topGainers = useMemo<MoverEntry[]>(() => {
    return [...allEntries]
      .filter((e) => e.change > 0)
      .sort((a, b) => b.change - a.change)
      .slice(0, 3)
      .map((e) => ({ symbol: e.symbol, name: e.name, change: e.change }));
  }, [allEntries]);

  /** Top Losers — 跌幅前 3 */
  const topLosers = useMemo<MoverEntry[]>(() => {
    return [...allEntries]
      .filter((e) => e.change < 0)
      .sort((a, b) => a.change - b.change)
      .slice(0, 3)
      .map((e) => ({ symbol: e.symbol, name: e.name, change: e.change }));
  }, [allEntries]);

  /** 按 Tab 分组的板块表现 */
  const sectors = useMemo<SectorEntry[]>(() => {
    const tabLabels: Record<TabKey, string> = {
      indices: t('finRadar.tabIndices'),
      crypto: t('finRadar.sectorCrypto'),
      commodities: t('finRadar.sectorCommodities'),
      forex: t('finRadar.sectorForex'),
    };
    return TAB_CONFIG.map((tab) => {
      const entries = marketData[tab.key];
      if (entries.length === 0) return { name: tabLabels[tab.key], change: 0 };
      const avg = entries.reduce((sum, e) => sum + e.change, 0) / entries.length;
      return { name: tabLabels[tab.key], change: avg };
    });
  }, [marketData, t]);

  /** 加密货币市值占比（从 crypto 数据推算） */
  const cryptoDominance = useMemo(() => {
    const cryptoData = marketData.crypto;
    if (cryptoData.length === 0) {
      return [
        { name: 'BTC', pct: 0, color: 'var(--accent-amber)' },
        { name: 'ETH', pct: 0, color: 'var(--accent-purple)' },
        { name: 'Others', pct: 0, color: 'var(--text-tertiary)' },
      ];
    }
    /* 用价格作为粗略权重参考 */
    const btc = cryptoData.find((c) => c.symbol.toUpperCase() === 'BTC');
    const eth = cryptoData.find((c) => c.symbol.toUpperCase() === 'ETH');
    const btcPrice = btc ? parseFloat(btc.price.replace(/,/g, '')) : 0;
    const ethPrice = eth ? parseFloat(eth.price.replace(/,/g, '')) : 0;
    const totalRef = cryptoData.reduce((s, c) => s + parseFloat(c.price.replace(/,/g, '')), 0);
    const btcPct = totalRef > 0 ? (btcPrice / totalRef) * 100 : 0;
    const ethPct = totalRef > 0 ? (ethPrice / totalRef) * 100 : 0;
    const othersPct = Math.max(0, 100 - btcPct - ethPct);
    return [
      { name: 'BTC', pct: Math.round(btcPct * 10) / 10, color: 'var(--accent-amber)' },
      { name: 'ETH', pct: Math.round(ethPct * 10) / 10, color: 'var(--accent-purple)' },
      { name: 'Others', pct: Math.round(othersPct * 10) / 10, color: 'var(--text-tertiary)' },
    ];
  }, [marketData]);

  /** 市场摘要 — 从实际数据计算 */
  const marketSummary = useMemo(() => {
    const upCount = allEntries.filter((e) => e.change > 0).length;
    const downCount = allEntries.filter((e) => e.change < 0).length;
    const btc = marketData.crypto.find((c) => c.symbol.toUpperCase() === 'BTC');
    const gold = marketData.commodities.find((c) => c.symbol.toUpperCase().includes('XAU') || c.name.toLowerCase().includes('gold'));
    const oil = marketData.commodities.find((c) => c.symbol.toUpperCase().includes('CL') || c.name.toLowerCase().includes('oil') || c.name.toLowerCase().includes('crude'));

    return [
      { label: t('finRadar.up'), value: String(upCount), color: 'var(--accent-green)' },
      { label: t('finRadar.down'), value: String(downCount), color: 'var(--accent-red)' },
      { label: 'BTC', value: btc ? `$${btc.price}` : '—', color: 'var(--accent-amber)' },
      { label: t('finRadar.gold'), value: gold ? `$${gold.price}` : '—', color: 'var(--accent-amber)' },
      { label: t('finRadar.oil'), value: oil ? `$${oil.price}` : '—', color: 'var(--text-primary)' },
    ];
  }, [allEntries, marketData, t]);

  /** 恐贪指数 — 从涨跌比例粗略计算 */
  const fearGreedIndex = useMemo(() => {
    if (allEntries.length === 0) return 50;
    const upRatio = allEntries.filter((e) => e.change > 0).length / allEntries.length;
    return Math.round(upRatio * 100);
  }, [allEntries]);

  const fgLabel = fearGreedIndex >= 75 ? 'EXTREME GREED' :
                  fearGreedIndex >= 55 ? 'GREED' :
                  fearGreedIndex >= 45 ? 'NEUTRAL' :
                  fearGreedIndex >= 25 ? 'FEAR' : 'EXTREME FEAR';

  const fgColor = fearGreedIndex >= 55 ? 'var(--accent-green)' :
                  fearGreedIndex >= 45 ? 'var(--accent-amber)' : 'var(--accent-red)';

  /* ====== 全局首次加载 ====== */
  const allLoading = Object.values(loadingTabs).every(Boolean);
  const allError = Object.values(errorTabs).every((e) => e !== null) && allEntries.length === 0;

  if (allLoading && allEntries.length === 0) {
    return (
      <div className="h-full overflow-y-auto pr-1">
        <div className="p-6">
          <LoadingState message={t('finRadar.loadingMarketData')} />
        </div>
      </div>
    );
  }

  if (allError) {
    return (
      <div className="h-full overflow-y-auto pr-1">
        <div className="p-6">
          <ErrorState
            message={t('finRadar.loadFailed')}
            onRetry={fetchAllData}
          />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="h-full overflow-y-auto pr-1"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* 12 列 Bento Grid */}
      <div
        className="grid gap-4"
        style={{
          gridTemplateColumns: 'repeat(12, 1fr)',
          gridAutoRows: 'minmax(0, auto)',
        }}
      >
        {/* ══════════════════════════════════════
         *  Row 1 左: Market Pulse — 主数据表
         *  占 8 列 2 行
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card"
          style={{ gridColumn: 'span 8', gridRow: 'span 2' }}
        >
          {/* 标题区 */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: 'var(--accent-cyan)', opacity: 0.15 }}
              >
                <Activity size={16} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display font-bold text-base" style={{ color: 'var(--text-primary)' }}>
                  {t('finRadar.title')}
                </h2>
                <p className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                  {t('finRadar.globalMarket')} // {t('finRadar.autoRefresh30s')}
                </p>
              </div>
            </div>
            {/* 状态指示灯 */}
            <div className="flex items-center gap-2">
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: 'var(--accent-green)' }}
              />
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                LIVE
              </span>
            </div>
          </div>

          {/* Tab 切换器 */}
          <div className="flex gap-1 mb-4 p-0.5 rounded-lg" style={{ background: 'var(--bg-base)' }}>
            {TAB_CONFIG.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={clsx(
                  'flex-1 py-1.5 px-3 rounded-md font-mono text-xs transition-all duration-200',
                  activeTab === tab.key
                    ? 'font-semibold'
                    : 'hover:opacity-80'
                )}
                style={{
                  background: activeTab === tab.key ? 'var(--bg-card)' : 'transparent',
                  color: activeTab === tab.key ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                  border: activeTab === tab.key ? '1px solid var(--glass-border)' : '1px solid transparent',
                }}
              >
                {t(tab.labelKey)}
              </button>
            ))}
          </div>

          {/* 数据表格 */}
          {currentLoading && currentData.length === 0 ? (
            <LoadingState message="加载中..." />
          ) : currentError && currentData.length === 0 ? (
            <ErrorState
              message={`数据加载失败: ${currentError}`}
              onRetry={() => {
                const tab = TAB_CONFIG.find((t) => t.key === activeTab);
                if (tab) fetchTab(tab);
              }}
            />
          ) : (
            <div className="overflow-hidden rounded-lg" style={{ border: '1px solid var(--glass-border)' }}>
              {/* 表头 */}
              <div
                className="grid font-mono text-[10px] uppercase px-3 py-2"
                style={{
                  gridTemplateColumns: '80px 1fr 120px 100px',
                  background: 'var(--bg-base)',
                  color: 'var(--text-tertiary)',
                  borderBottom: '1px solid var(--glass-border)',
                }}
              >
                <span>{t('finRadar.colSymbol')}</span>
                <span>{t('finRadar.colName')}</span>
                <span className="text-right">{t('finRadar.colPrice')}</span>
                <span className="text-right">{t('finRadar.col24hChange')}</span>
              </div>

              {/* 数据行 */}
              {currentData.map((entry, idx) => (
                <motion.div
                  key={`${activeTab}-${entry.symbol}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.03, duration: 0.2 }}
                  className="grid font-mono text-xs px-3 py-2.5 transition-colors hover:brightness-110"
                  style={{
                    gridTemplateColumns: '80px 1fr 120px 100px',
                    borderBottom: idx < currentData.length - 1 ? '1px solid var(--glass-border)' : 'none',
                    background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  }}
                >
                  {/* 代码 */}
                  <span className="font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {entry.symbol}
                  </span>
                  {/* 名称 */}
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {entry.name}
                  </span>
                  {/* 价格 */}
                  <span className="text-right" style={{ color: 'var(--text-primary)' }}>
                    {entry.price}
                  </span>
                  {/* 涨跌幅 */}
                  <span
                    className="text-right flex items-center justify-end gap-1"
                    style={{ color: changeColor(entry.change) }}
                  >
                    {entry.change > 0 ? <TrendingUp size={12} /> : entry.change < 0 ? <TrendingDown size={12} /> : null}
                    {formatChange(entry.change)}
                  </span>
                </motion.div>
              ))}

              {currentData.length === 0 && (
                <div className="flex items-center justify-center py-8">
                  <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                    {t('finRadar.noData')}
                  </span>
                </div>
              )}
            </div>
          )}
        </motion.div>

        {/* ══════════════════════════════════════
         *  Row 1 右上: Fear & Greed Index
         *  占 4 列
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card flex flex-col items-center justify-center gap-3 py-6"
          style={{ gridColumn: 'span 4' }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Zap size={14} style={{ color: 'var(--accent-amber)' }} />
            <span className="text-label font-mono text-[10px] uppercase" style={{ color: 'var(--text-tertiary)' }}>
              {t('finRadar.fearGreedIndex')}
            </span>
          </div>

          {/* 大数字 */}
          <span
            className="text-metric font-display text-5xl font-bold"
            style={{ color: fgColor }}
          >
            {fearGreedIndex}
          </span>

          {/* 情绪文字 */}
          <span
            className="font-mono text-sm font-semibold uppercase tracking-wider"
            style={{ color: fgColor }}
          >
            {fgLabel}
          </span>

          {/* 水平进度条 0-100 */}
          <div className="w-full max-w-[200px] mt-2">
            {/* 刻度标签 */}
            <div className="flex justify-between font-mono text-[9px] mb-1" style={{ color: 'var(--text-disabled)' }}>
              <span>0 FEAR</span>
              <span>100 GREED</span>
            </div>
            {/* 进度条背景 */}
            <div
              className="relative w-full h-2 rounded-full overflow-hidden"
              style={{ background: 'var(--bg-base)' }}
            >
              {/* 渐变填充 */}
              <div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                  width: `${fearGreedIndex}%`,
                  background: 'linear-gradient(90deg, var(--accent-red), var(--accent-amber), var(--accent-green))',
                }}
              />
              {/* 指针 */}
              <div
                className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-2"
                style={{
                  left: `calc(${fearGreedIndex}% - 5px)`,
                  background: 'var(--bg-card)',
                  borderColor: fgColor,
                }}
              />
            </div>
          </div>
        </motion.div>

        {/* ══════════════════════════════════════
         *  Row 1 右下: Market Summary
         *  占 4 列
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card"
          style={{ gridColumn: 'span 4' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Globe size={14} style={{ color: 'var(--accent-cyan)' }} />
            <span className="text-label font-mono text-[10px] uppercase" style={{ color: 'var(--text-tertiary)' }}>
              市场总览
            </span>
          </div>

          <div className="flex flex-col gap-2">
            {marketSummary.map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between py-1 px-2 rounded"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {item.label}
                </span>
                <span
                  className="text-metric font-mono text-xs font-semibold"
                  style={{ color: item.color }}
                >
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* ══════════════════════════════════════
         *  Row 2 左: Top Movers
         *  占 4 列
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card"
          style={{ gridColumn: 'span 4' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={14} style={{ color: 'var(--accent-green)' }} />
            <span className="text-label font-mono text-[10px] uppercase" style={{ color: 'var(--text-tertiary)' }}>
              涨跌排行
            </span>
          </div>

          {/* 涨幅榜 */}
          <div className="mb-3">
            <span className="font-mono text-[9px] uppercase mb-1.5 block" style={{ color: 'var(--accent-green)' }}>
              涨幅榜
            </span>
            {topGainers.length === 0 && (
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>暂无数据</span>
            )}
            {topGainers.map((item) => (
              <div
                key={item.symbol}
                className="flex items-center justify-between py-1.5 px-2 rounded mb-0.5"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {item.symbol}
                  </span>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {item.name}
                  </span>
                </div>
                <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-green)' }}>
                  {formatChange(item.change)}
                </span>
              </div>
            ))}
          </div>

          {/* 跌幅榜 */}
          <div>
            <span className="font-mono text-[9px] uppercase mb-1.5 block" style={{ color: 'var(--accent-red)' }}>
              跌幅榜
            </span>
            {topLosers.length === 0 && (
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>暂无数据</span>
            )}
            {topLosers.map((item) => (
              <div
                key={item.symbol}
                className="flex items-center justify-between py-1.5 px-2 rounded mb-0.5"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {item.symbol}
                  </span>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {item.name}
                  </span>
                </div>
                <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-red)' }}>
                  {formatChange(item.change)}
                </span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* ══════════════════════════════════════
         *  Row 2 中: Sector Performance
         *  占 4 列
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card"
          style={{ gridColumn: 'span 4' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={14} style={{ color: 'var(--accent-purple)' }} />
            <span className="text-label font-mono text-[10px] uppercase" style={{ color: 'var(--text-tertiary)' }}>
              板块表现
            </span>
          </div>

          <div className="flex flex-col gap-2.5">
            {sectors.map((sector) => {
              const maxPct = 3;
              const absPct = Math.min(Math.abs(sector.change), maxPct);
              const barWidth = (absPct / maxPct) * 50;
              const isPositive = sector.change >= 0;

              return (
                <div key={sector.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {sector.name}
                    </span>
                    <span
                      className="font-mono text-[11px] font-semibold"
                      style={{ color: changeColor(sector.change) }}
                    >
                      {formatChange(sector.change)}
                    </span>
                  </div>
                  {/* 水平条形图 — 从中线向左（负）或向右（正）延伸 */}
                  <div className="relative w-full h-1.5 rounded-full" style={{ background: 'var(--bg-base)' }}>
                    {isPositive ? (
                      <div
                        className="absolute top-0 h-full rounded-full"
                        style={{
                          left: '50%',
                          width: `${barWidth}%`,
                          background: 'var(--accent-green)',
                        }}
                      />
                    ) : (
                      <div
                        className="absolute top-0 h-full rounded-full"
                        style={{
                          right: '50%',
                          width: `${barWidth}%`,
                          background: 'var(--accent-red)',
                        }}
                      />
                    )}
                    {/* 中线指示 */}
                    <div
                      className="absolute top-0 h-full w-px"
                      style={{ left: '50%', background: 'var(--glass-border)' }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* ══════════════════════════════════════
         *  Row 2 右: Crypto Dominance
         *  占 4 列
         * ══════════════════════════════════════ */}
        <motion.div
          variants={cardVariants}
          className="abyss-card"
          style={{ gridColumn: 'span 4' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} style={{ color: 'var(--accent-amber)' }} />
            <span className="text-label font-mono text-[10px] uppercase" style={{ color: 'var(--text-tertiary)' }}>
              加密货币占比
            </span>
          </div>

          <div className="flex flex-col gap-3">
            {cryptoDominance.map((item) => (
              <div key={item.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: item.color }}
                    />
                    <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {item.name}
                    </span>
                  </div>
                  <span className="text-metric font-mono text-sm font-bold" style={{ color: item.color }}>
                    {item.pct}%
                  </span>
                </div>
                {/* 占比进度条 */}
                <div
                  className="w-full h-1.5 rounded-full overflow-hidden"
                  style={{ background: 'var(--bg-base)' }}
                >
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${item.pct}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="h-full rounded-full"
                    style={{ background: item.color }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* 底部数据来源 */}
          <div
            className="mt-4 pt-3 flex items-center justify-between"
            style={{ borderTop: '1px solid var(--glass-border)' }}
          >
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
              数据每 30 秒刷新
            </span>
            <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
              LIVE
            </span>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

/**
 * FinRadar — 金融雷达页面
 * Sonic Abyss 终端美学，12 列 Bento Grid 布局
 * 展示全球市场指数、加密货币、大宗商品、外汇实时数据
 */
import { useState } from 'react';
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
} from 'lucide-react';

/* ====== 类型定义 ====== */

/** 市场数据条目 */
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

/* ====== 模拟数据 ====== */

/** 各 Tab 对应的市场数据 */
const MARKET_DATA: Record<TabKey, MarketEntry[]> = {
  indices: [
    { symbol: 'SPX', name: 'S&P 500', price: '5,234.18', change: 0.82 },
    { symbol: 'DJI', name: 'Dow Jones', price: '39,512.84', change: 0.56 },
    { symbol: 'IXIC', name: 'Nasdaq', price: '16,340.87', change: 1.24 },
    { symbol: 'FTSE', name: 'FTSE 100', price: '8,139.83', change: -0.31 },
    { symbol: 'DAX', name: 'DAX 40', price: '18,235.45', change: 0.47 },
    { symbol: 'N225', name: 'Nikkei 225', price: '38,460.08', change: -0.68 },
    { symbol: 'HSI', name: 'Hang Seng', price: '17,651.15', change: 1.85 },
    { symbol: 'SHCOMP', name: 'Shanghai Comp', price: '3,088.64', change: 0.93 },
  ],
  crypto: [
    { symbol: 'BTC', name: 'Bitcoin', price: '67,842.30', change: 2.15 },
    { symbol: 'ETH', name: 'Ethereum', price: '3,456.78', change: 1.87 },
    { symbol: 'SOL', name: 'Solana', price: '178.45', change: 5.32 },
    { symbol: 'BNB', name: 'BNB', price: '612.90', change: -0.45 },
    { symbol: 'XRP', name: 'Ripple', price: '0.5234', change: -1.23 },
    { symbol: 'ADA', name: 'Cardano', price: '0.4521', change: 3.67 },
    { symbol: 'AVAX', name: 'Avalanche', price: '38.92', change: 4.11 },
    { symbol: 'DOGE', name: 'Dogecoin', price: '0.1634', change: -2.08 },
  ],
  commodities: [
    { symbol: 'XAU', name: 'Gold', price: '2,338.50', change: 0.34 },
    { symbol: 'XAG', name: 'Silver', price: '27.85', change: -0.56 },
    { symbol: 'CL', name: 'WTI Crude Oil', price: '78.26', change: 1.12 },
    { symbol: 'NG', name: 'Natural Gas', price: '2.134', change: -2.45 },
    { symbol: 'HG', name: 'Copper', price: '4.5120', change: 0.89 },
    { symbol: 'ZW', name: 'Wheat', price: '612.50', change: -0.78 },
  ],
  forex: [
    { symbol: 'EUR/USD', name: 'Euro / Dollar', price: '1.0845', change: -0.12 },
    { symbol: 'GBP/USD', name: 'Pound / Dollar', price: '1.2678', change: 0.08 },
    { symbol: 'USD/JPY', name: 'Dollar / Yen', price: '154.32', change: 0.45 },
    { symbol: 'USD/CNH', name: 'Dollar / CNH', price: '7.2456', change: 0.23 },
    { symbol: 'AUD/USD', name: 'Aussie / Dollar', price: '0.6534', change: -0.34 },
    { symbol: 'USD/CHF', name: 'Dollar / Franc', price: '0.9012', change: 0.15 },
  ],
};

/** Tab 标签配置 */
const TAB_CONFIG: { key: TabKey; label: string }[] = [
  { key: 'indices', label: 'INDICES' },
  { key: 'crypto', label: 'CRYPTO' },
  { key: 'commodities', label: 'COMMODITIES' },
  { key: 'forex', label: 'FOREX' },
];

/** Top Movers — 涨幅榜 */
const TOP_GAINERS: MoverEntry[] = [
  { symbol: 'SOL', name: 'Solana', change: 5.32 },
  { symbol: 'AVAX', name: 'Avalanche', change: 4.11 },
  { symbol: 'ADA', name: 'Cardano', change: 3.67 },
];

/** Top Movers — 跌幅榜 */
const TOP_LOSERS: MoverEntry[] = [
  { symbol: 'NG', name: 'Natural Gas', change: -2.45 },
  { symbol: 'DOGE', name: 'Dogecoin', change: -2.08 },
  { symbol: 'XRP', name: 'Ripple', change: -1.23 },
];

/** 板块表现 */
const SECTORS: SectorEntry[] = [
  { name: 'Technology', change: 1.2 },
  { name: 'Healthcare', change: -0.5 },
  { name: 'Energy', change: 2.1 },
  { name: 'Finance', change: 0.3 },
  { name: 'Consumer', change: -0.8 },
  { name: 'Industrial', change: 0.6 },
];

/** 加密货币市值占比 */
const CRYPTO_DOMINANCE = [
  { name: 'BTC', pct: 52.4, color: 'var(--accent-amber)' },
  { name: 'ETH', pct: 17.8, color: 'var(--accent-purple)' },
  { name: 'Others', pct: 29.8, color: 'var(--text-tertiary)' },
];

/** 市场摘要数据 */
const MARKET_SUMMARY = [
  { label: 'Markets Up', value: '5', color: 'var(--accent-green)' },
  { label: 'Markets Down', value: '3', color: 'var(--accent-red)' },
  { label: 'BTC', value: '$67,842', color: 'var(--accent-amber)' },
  { label: 'Gold', value: '$2,338', color: 'var(--accent-amber)' },
  { label: 'DXY', value: '104.52', color: 'var(--accent-cyan)' },
  { label: 'Oil', value: '$78.26', color: 'var(--text-primary)' },
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

/* ====== 主组件 ====== */

export function FinRadar() {
  /* 当前激活的 Tab */
  const [activeTab, setActiveTab] = useState<TabKey>('indices');

  /* 当前 Tab 对应的市场数据 */
  const currentData = MARKET_DATA[activeTab];

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
                  FINANCE RADAR
                </h2>
                <p className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                  GLOBAL MARKETS // REAL-TIME
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
                {tab.label}
              </button>
            ))}
          </div>

          {/* 数据表格 */}
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
              <span>Symbol</span>
              <span>Name</span>
              <span className="text-right">Price</span>
              <span className="text-right">24h Change</span>
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
          </div>
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
              Fear & Greed Index
            </span>
          </div>

          {/* 大数字 */}
          <span
            className="text-metric font-display text-5xl font-bold"
            style={{ color: 'var(--accent-green)' }}
          >
            62
          </span>

          {/* 情绪文字 */}
          <span
            className="font-mono text-sm font-semibold uppercase tracking-wider"
            style={{ color: 'var(--accent-green)' }}
          >
            GREED
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
                  width: '62%',
                  background: 'linear-gradient(90deg, var(--accent-red), var(--accent-amber), var(--accent-green))',
                }}
              />
              {/* 指针 */}
              <div
                className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-2"
                style={{
                  left: 'calc(62% - 5px)',
                  background: 'var(--bg-card)',
                  borderColor: 'var(--accent-green)',
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
              Market Summary
            </span>
          </div>

          <div className="flex flex-col gap-2">
            {MARKET_SUMMARY.map((item) => (
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
              Top Movers
            </span>
          </div>

          {/* 涨幅榜 */}
          <div className="mb-3">
            <span className="font-mono text-[9px] uppercase mb-1.5 block" style={{ color: 'var(--accent-green)' }}>
              Gainers
            </span>
            {TOP_GAINERS.map((item) => (
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
              Losers
            </span>
            {TOP_LOSERS.map((item) => (
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
              Sector Performance
            </span>
          </div>

          <div className="flex flex-col gap-2.5">
            {SECTORS.map((sector) => {
              /* 计算进度条宽度：以 3% 为满格，居中展示正负 */
              const maxPct = 3;
              const absPct = Math.min(Math.abs(sector.change), maxPct);
              const barWidth = (absPct / maxPct) * 50; // 最大占 50%
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
              Crypto Dominance
            </span>
          </div>

          <div className="flex flex-col gap-3">
            {CRYPTO_DOMINANCE.map((item) => (
              <div key={item.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    {/* 颜色圆点 */}
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

          {/* 总市值参考 */}
          <div
            className="mt-4 pt-3 flex items-center justify-between"
            style={{ borderTop: '1px solid var(--glass-border)' }}
          >
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
              TOTAL MARKET CAP
            </span>
            <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
              $2.48T
            </span>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

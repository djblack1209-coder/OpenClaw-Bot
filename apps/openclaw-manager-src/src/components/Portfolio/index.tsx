/**
 * Portfolio — 投资组合页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 模拟数据 ====== */

/** 持仓数据 */
const HOLDINGS = [
  { symbol: 'NVDA', name: '英伟达', qty: 50, price: 875.30, pnl: 12350, pnlPct: 38.2 },
  { symbol: 'AAPL', name: '苹果', qty: 120, price: 198.50, pnl: 4280, pnlPct: 21.5 },
  { symbol: 'TSLA', name: '特斯拉', qty: 30, price: 245.80, pnl: -1520, pnlPct: -6.8 },
  { symbol: 'BTC', name: '比特币', qty: 0.85, price: 67420, pnl: 8960, pnlPct: 15.6 },
  { symbol: 'MSFT', name: '微软', qty: 80, price: 415.20, pnl: 3640, pnlPct: 12.3 },
];

/** AI 建议 */
const AI_RECOMMENDATIONS = [
  { text: '建议减持 NVDA — 估值偏高', severity: 'var(--accent-amber)' },
  { text: '建议增持 AAPL — 技术突破', severity: 'var(--accent-green)' },
  { text: '关注 BTC — Hurst指数看涨', severity: 'var(--accent-cyan)' },
];

/** 风险指标 */
const RISK_METRICS = [
  { label: '夏普比率', value: '1.82', color: 'var(--accent-green)' },
  { label: '最大回撤', value: '-8.3%', color: 'var(--accent-red)' },
  { label: 'Beta', value: '0.95', color: 'var(--accent-cyan)' },
  { label: 'VaR(95%)', value: '$2,150', color: 'var(--accent-amber)' },
];

/** Bot 投票 */
const BOT_VOTES = [
  { name: '巴菲特', signal: '看多' as const, color: 'var(--accent-green)' },
  { name: '塔勒布', signal: '中性' as const, color: 'var(--accent-amber)' },
  { name: '木头姐', signal: '看多' as const, color: 'var(--accent-green)' },
  { name: 'Burry', signal: '看空' as const, color: 'var(--accent-red)' },
  { name: '德鲁肯米勒', signal: '看多' as const, color: 'var(--accent-green)' },
];

/** 持仓分布 */
const SECTOR_ALLOCATION = [
  { sector: '科技', pct: 45, color: 'var(--accent-cyan)' },
  { sector: '金融', pct: 20, color: 'var(--accent-green)' },
  { sector: '医疗', pct: 15, color: 'var(--accent-purple)' },
  { sector: '能源', pct: 12, color: 'var(--accent-amber)' },
  { sector: '其他', pct: 8, color: 'var(--text-tertiary)' },
];

/** 交易日志 */
const TRADE_LOG = [
  { time: '14:32', action: '买入' as const, symbol: 'AAPL', qty: 20, price: 198.50 },
  { time: '13:15', action: '卖出' as const, symbol: 'TSLA', qty: 10, price: 248.30 },
  { time: '11:08', action: '买入' as const, symbol: 'BTC', qty: 0.15, price: 67200 },
  { time: '09:45', action: '卖出' as const, symbol: 'META', qty: 25, price: 512.40 },
  { time: '09:31', action: '买入' as const, symbol: 'NVDA', qty: 5, price: 870.10 },
];

/** 30天收益走势数据 (模拟百分比变化) */
const SPARKLINE_DATA = [
  0.5, -0.3, 0.8, 1.2, -0.1, 0.4, 0.9, -0.5, 0.2, 1.5,
  -0.8, 0.3, 0.7, 1.1, 0.6, -0.2, 0.4, 1.3, -0.4, 0.8,
  0.2, -0.6, 1.0, 0.5, 0.9, -0.1, 1.4, 0.3, 0.7, 1.8,
];

/* ====== 辅助函数 ====== */

/** 格式化盈亏颜色 */
function pnlColor(value: number): string {
  return value >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
}

/** 格式化盈亏符号 */
function pnlSign(value: number): string {
  return value >= 0 ? '+' : '';
}

/** 把数值映射到 ASCII 柱状图字符 */
function sparklineBar(value: number, max: number): string {
  const blocks = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
  const normalized = Math.max(0, (value + Math.abs(max)) / (max * 2));
  const idx = Math.min(Math.floor(normalized * blocks.length), blocks.length - 1);
  return blocks[idx];
}

/* ====== 子卡片组件 ====== */

/** 总资产概览卡片 */
function AssetOverviewCard() {
  const stats = [
    { label: '总资产', value: '$125,430', color: 'var(--text-primary)' },
    { label: '今日盈亏', value: '+$1,240', color: 'var(--accent-green)' },
    { label: '总收益率', value: '+18.5%', color: 'var(--accent-green)' },
    { label: '持仓数量', value: '12', color: 'var(--accent-cyan)' },
  ];

  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      {/* 顶部标签 */}
      <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
        PORTFOLIO // OVERVIEW
      </span>
      <h2 className="font-display text-[28px] font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        投资组合
      </h2>

      {/* 4列统计数据 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
        {stats.map((s) => (
          <div key={s.label}>
            <span className="text-label">{s.label}</span>
            <div className="text-metric mt-1" style={{ color: s.color }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      {/* 持仓列表 */}
      <div className="mt-5 flex-1">
        <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
          TOP HOLDINGS
        </span>
        <div className="mt-2 space-y-1">
          {HOLDINGS.map((h) => (
            <div
              key={h.symbol}
              className="flex items-center gap-3 py-2 px-3 rounded-lg cursor-pointer transition-colors"
              style={{ background: 'rgba(255,255,255,0.02)' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
            >
              {/* 股票代码 */}
              <span className="font-mono text-sm font-semibold w-14" style={{ color: 'var(--accent-cyan)' }}>
                {h.symbol}
              </span>
              {/* 名称 */}
              <span className="text-xs flex-1 truncate" style={{ color: 'var(--text-secondary)' }}>
                {h.name}
              </span>
              {/* 数量 */}
              <span className="font-mono text-xs w-12 text-right" style={{ color: 'var(--text-tertiary)' }}>
                {h.qty}
              </span>
              {/* 现价 */}
              <span className="font-mono text-xs w-20 text-right" style={{ color: 'var(--text-secondary)' }}>
                ${h.price.toLocaleString()}
              </span>
              {/* 盈亏额 */}
              <span className="font-mono text-xs w-20 text-right" style={{ color: pnlColor(h.pnl) }}>
                {pnlSign(h.pnl)}${Math.abs(h.pnl).toLocaleString()}
              </span>
              {/* 盈亏率 */}
              <span className="font-mono text-xs w-16 text-right font-semibold" style={{ color: pnlColor(h.pnlPct) }}>
                {pnlSign(h.pnlPct)}{h.pnlPct}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** AI 投资建议卡片 */
function AIAdvisorCard() {
  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
        AI ADVISOR
      </span>
      <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        AI 投资顾问
      </h3>
      <div className="mt-4 space-y-3 flex-1">
        {AI_RECOMMENDATIONS.map((rec, i) => (
          <div
            key={i}
            className="flex items-start gap-3 p-3 rounded-lg"
            style={{ background: 'rgba(255,255,255,0.03)' }}
          >
            {/* 严重度圆点 */}
            <span
              className="inline-block w-2.5 h-2.5 rounded-full mt-0.5 flex-shrink-0"
              style={{ background: rec.severity, boxShadow: `0 0 8px ${rec.severity}40` }}
            />
            <span className="font-mono text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {rec.text}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] font-mono mt-3" style={{ color: 'var(--text-disabled)' }}>
        基于 7-Bot 多智能体共识分析
      </p>
    </div>
  );
}

/** 风险指标卡片 */
function RiskMetricsCard() {
  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
        RISK METRICS
      </span>
      <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        风险指标
      </h3>
      <div className="mt-4 space-y-4 flex-1">
        {RISK_METRICS.map((m) => (
          <div key={m.label} className="flex items-center justify-between">
            <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
              {m.label}
            </span>
            <span className="text-metric text-base" style={{ color: m.color }}>
              {m.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 7-Bot 共识卡片 */
function BotConsensusCard() {
  /* 统计各信号数量用于百分比条 */
  const total = BOT_VOTES.length;
  const bullCount = BOT_VOTES.filter((b) => b.signal === '看多').length;
  const bearCount = BOT_VOTES.filter((b) => b.signal === '看空').length;
  const neutralCount = total - bullCount - bearCount;

  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
        7-BOT CONSENSUS
      </span>
      <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        7-Bot 共识
      </h3>

      {/* 共识进度条 */}
      <div className="flex h-3 rounded-full overflow-hidden mt-4" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div
          className="h-full transition-all"
          style={{ width: `${(bullCount / total) * 100}%`, background: 'var(--accent-green)' }}
        />
        <div
          className="h-full transition-all"
          style={{ width: `${(neutralCount / total) * 100}%`, background: 'var(--accent-amber)' }}
        />
        <div
          className="h-full transition-all"
          style={{ width: `${(bearCount / total) * 100}%`, background: 'var(--accent-red)' }}
        />
      </div>

      {/* Bot 列表 */}
      <div className="mt-4 space-y-2 flex-1">
        {BOT_VOTES.map((bot) => (
          <div key={bot.name} className="flex items-center justify-between">
            <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
              {bot.name}
            </span>
            <span
              className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full"
              style={{
                color: bot.color,
                background: `${bot.color}15`,
              }}
            >
              {bot.signal}
            </span>
          </div>
        ))}
      </div>

      {/* 统计汇总 */}
      <div className="flex gap-4 mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-green)' }} />
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{bullCount} 看多</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-amber)' }} />
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{neutralCount} 中性</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-red)' }} />
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{bearCount} 看空</span>
        </span>
      </div>
    </div>
  );
}

/** 持仓分布卡片 */
function SectorAllocationCard() {
  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label" style={{ color: 'var(--accent-green)' }}>
        ALLOCATION
      </span>
      <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        持仓分布
      </h3>
      <div className="mt-4 space-y-3 flex-1">
        {SECTOR_ALLOCATION.map((s) => (
          <div key={s.sector}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {s.sector}
              </span>
              <span className="font-mono text-xs font-semibold" style={{ color: s.color }}>
                {s.pct}%
              </span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${s.pct}%`, background: s.color, opacity: 0.8 }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 交易日志卡片 */
function TradeLogCard() {
  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label" style={{ color: 'var(--accent-red)' }}>
        TRADE LOG
      </span>
      <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
        交易日志
      </h3>
      <div className="mt-4 space-y-1 flex-1 font-mono text-xs">
        {TRADE_LOG.map((t, i) => (
          <div
            key={i}
            className="flex items-center gap-2 py-1.5 px-2 rounded"
            style={{ background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent' }}
          >
            {/* 时间 */}
            <span style={{ color: 'var(--text-disabled)' }}>{t.time}</span>
            {/* 操作 */}
            <span
              className="w-8 text-center font-semibold"
              style={{ color: t.action === '买入' ? 'var(--accent-green)' : 'var(--accent-red)' }}
            >
              {t.action}
            </span>
            {/* 股票 */}
            <span style={{ color: 'var(--accent-cyan)' }}>{t.symbol}</span>
            {/* 数量 */}
            <span className="ml-auto" style={{ color: 'var(--text-tertiary)' }}>
              x{t.qty}
            </span>
            {/* 价格 */}
            <span className="w-20 text-right" style={{ color: 'var(--text-secondary)' }}>
              ${t.price.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] font-mono mt-3" style={{ color: 'var(--text-disabled)' }}>
        最近 5 笔交易记录
      </p>
    </div>
  );
}

/** 30天收益走势卡片 */
function SparklineCard() {
  const max = Math.max(...SPARKLINE_DATA.map(Math.abs));

  return (
    <div className="abyss-card p-6 h-full">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-label" style={{ color: 'var(--accent-green)' }}>
            PERFORMANCE // 30D
          </span>
          <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
            30天收益走势
          </h3>
        </div>
        <div className="text-right">
          <span className="text-label">累计收益</span>
          <div className="text-metric mt-1" style={{ color: 'var(--accent-green)' }}>
            +{SPARKLINE_DATA.reduce((a, b) => a + b, 0).toFixed(1)}%
          </div>
        </div>
      </div>

      {/* ASCII 柱状图 */}
      <div className="mt-4 flex items-end gap-[3px] h-16 overflow-hidden">
        {SPARKLINE_DATA.map((val, i) => (
          <div
            key={i}
            className="flex-1 flex flex-col items-center justify-end"
            title={`Day ${i + 1}: ${val >= 0 ? '+' : ''}${val}%`}
          >
            <span
              className="font-mono text-lg leading-none select-none"
              style={{ color: val >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', opacity: 0.9 }}
            >
              {sparklineBar(val, max)}
            </span>
          </div>
        ))}
      </div>

      {/* 底部日期标注 */}
      <div className="flex justify-between mt-2">
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>30天前</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>15天前</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>今天</span>
      </div>
    </div>
  );
}

/* ====== 主组件 ====== */

/**
 * Portfolio — Sonic Abyss Bento Grid 布局
 * 12 列 CSS Grid，全模拟数据，无 API 调用
 */
export function Portfolio() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：总资产概览 (span-8, row-span-2) + AI 建议 (span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <AssetOverviewCard />
        </motion.div>

        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <AIAdvisorCard />
        </motion.div>

        {/* 风险指标 (span-4) — 紧跟 AI 建议下方 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <RiskMetricsCard />
        </motion.div>

        {/* ====== 第二行：Bot共识 (span-4) + 持仓分布 (span-4) + 交易日志 (span-4) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <BotConsensusCard />
        </motion.div>

        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <SectorAllocationCard />
        </motion.div>

        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <TradeLogCard />
        </motion.div>

        {/* ====== 第三行：收益走势 (span-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <SparklineCard />
        </motion.div>
      </motion.div>
    </div>
  );
}

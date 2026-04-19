/**
 * Money — 盈利总控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import {
  DollarSign,
  TrendingUp,
  PieChart,
  Lightbulb,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
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

/** 收入明细 */
interface IncomeItem {
  label: string;
  amount: string;
  trend: 'up' | 'down' | 'flat';
  pct: string;
}

const INCOME_ITEMS: IncomeItem[] = [
  { label: '量化交易', amount: '¥18,600', trend: 'up', pct: '+12.3%' },
  { label: '套利策略', amount: '¥8,200', trend: 'up', pct: '+5.8%' },
  { label: 'DeFi 挖矿', amount: '¥5,300', trend: 'down', pct: '-2.1%' },
  { label: '闲鱼销售', amount: '¥8,430', trend: 'up', pct: '+18.7%' },
  { label: '闲鱼代购', amount: '¥4,700', trend: 'up', pct: '+9.2%' },
];

/** 月度趋势数据 */
const MONTHLY_DATA = [
  { month: '1月', value: 5200 },
  { month: '2月', value: 6800 },
  { month: '3月', value: 4900 },
  { month: '4月', value: 8100 },
  { month: '5月', value: 7400 },
  { month: '6月', value: 8420 },
];

/** Alpha 研究洞察 */
const ALPHA_INSIGHTS = [
  { title: 'BTC 链上活跃度飙升', desc: '大额转账24h内增37%，看涨信号', color: 'var(--accent-green)' },
  { title: 'NVDA 财报超预期', desc: '数据中心收入同比+154%，AI 需求持续', color: 'var(--accent-cyan)' },
  { title: '美债收益率倒挂收窄', desc: '10Y-2Y 利差缩至-15bp，衰退概率降低', color: 'var(--accent-amber)' },
];

/* ====== 工具函数 ====== */

/** 渲染 ASCII 柱状图 */
function renderBar(value: number, maxValue: number, width: number = 24): string {
  const ratio = value / maxValue;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Money() {
  const maxMonthly = Math.max(...MONTHLY_DATA.map((d) => d.value));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 收入概览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <DollarSign size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  REVENUE OVERVIEW
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  盈利总控 // INCOME DASHBOARD
                </p>
              </div>
            </div>

            {/* 顶部统计 4 列 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: '总收入', value: '¥45,230', color: 'var(--accent-green)' },
                { label: '本月', value: '¥8,420', color: 'var(--accent-cyan)' },
                { label: '交易收益', value: '¥32,100', color: 'var(--accent-purple)' },
                { label: '闲鱼收入', value: '¥13,130', color: 'var(--accent-amber)' },
              ].map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 收入明细列表 */}
            <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
              INCOME BREAKDOWN
            </span>
            <div className="mt-2 flex-1 space-y-1">
              {INCOME_ITEMS.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg transition-colors"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                    {item.label}
                  </span>
                  <div className="flex items-center gap-4">
                    <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                      {item.amount}
                    </span>
                    <span
                      className={clsx('flex items-center gap-0.5 font-mono text-xs font-semibold')}
                      style={{ color: item.trend === 'up' ? 'var(--accent-green)' : item.trend === 'down' ? 'var(--accent-red)' : 'var(--text-tertiary)' }}
                    >
                      {item.trend === 'up' && <ArrowUpRight size={12} />}
                      {item.trend === 'down' && <ArrowDownRight size={12} />}
                      {item.pct}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 收入构成 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              REVENUE MIX
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              收入构成
            </h3>

            <div className="mt-6 flex-1 space-y-5">
              {/* 交易占比 */}
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-label flex items-center gap-1.5">
                    <TrendingUp size={12} style={{ color: 'var(--accent-cyan)' }} />
                    交易收益
                  </span>
                  <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                    71%
                  </span>
                </div>
                <div
                  className="h-3 rounded-full overflow-hidden"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: '71%', background: 'var(--accent-cyan)' }}
                  />
                </div>
                <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  ¥32,100 / ¥45,230
                </p>
              </div>

              {/* 闲鱼占比 */}
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-label flex items-center gap-1.5">
                    <PieChart size={12} style={{ color: 'var(--accent-amber)' }} />
                    闲鱼收入
                  </span>
                  <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-amber)' }}>
                    29%
                  </span>
                </div>
                <div
                  className="h-3 rounded-full overflow-hidden"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: '29%', background: 'var(--accent-amber)' }}
                  />
                </div>
                <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  ¥13,130 / ¥45,230
                </p>
              </div>

              {/* 分割线 + 小结 */}
              <div
                className="border-t pt-4 mt-4"
                style={{ borderColor: 'var(--glass-border)' }}
              >
                <span className="text-label">月度目标进度</span>
                <div className="flex items-end gap-2 mt-2">
                  <span className="text-metric" style={{ color: 'var(--accent-green)' }}>
                    84%
                  </span>
                  <span className="font-mono text-[10px] pb-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    ¥8,420 / ¥10,000
                  </span>
                </div>
                <div
                  className="h-2 rounded-full overflow-hidden mt-2"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: '84%', background: 'var(--accent-green)' }}
                  />
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 月度趋势 ASCII 图 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              MONTHLY TREND
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              月度趋势
            </h3>

            <div className="flex-1 space-y-2">
              {MONTHLY_DATA.map((d) => (
                <div key={d.month} className="flex items-center gap-3">
                  <span
                    className="font-mono text-xs w-8 shrink-0 text-right"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    {d.month}
                  </span>
                  <span
                    className="font-mono text-xs flex-1 tracking-tight"
                    style={{ color: d.value === maxMonthly ? 'var(--accent-green)' : 'var(--accent-cyan)', opacity: 0.85 }}
                  >
                    {renderBar(d.value, maxMonthly)}
                  </span>
                  <span
                    className="font-mono text-xs w-16 text-right shrink-0"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    ¥{d.value.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>

            {/* 趋势统计行 */}
            <div
              className="flex items-center justify-between mt-5 pt-4 border-t"
              style={{ borderColor: 'var(--glass-border)' }}
            >
              <div className="flex items-center gap-2">
                <BarChart3 size={14} style={{ color: 'var(--accent-cyan)' }} />
                <span className="text-label">6 个月均值</span>
                <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                  ¥{Math.round(MONTHLY_DATA.reduce((a, d) => a + d.value, 0) / MONTHLY_DATA.length).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <ArrowUpRight size={14} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-green)' }}>
                  +13.8% MoM
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== Alpha 研究洞察 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              ALPHA RESEARCH
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              研究洞察
            </h3>

            <div className="flex-1 space-y-4">
              {ALPHA_INSIGHTS.map((insight, i) => (
                <div
                  key={i}
                  className="p-4 rounded-xl border transition-colors"
                  style={{
                    background: 'var(--bg-secondary)',
                    borderColor: 'var(--glass-border)',
                  }}
                >
                  <div className="flex items-start gap-2.5">
                    <Lightbulb size={16} className="shrink-0 mt-0.5" style={{ color: insight.color }} />
                    <div>
                      <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                        {insight.title}
                      </p>
                      <p className="font-mono text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                        {insight.desc}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 底部提示 */}
            <p
              className="font-mono text-[10px] mt-4 pt-3 border-t"
              style={{ color: 'var(--text-disabled)', borderColor: 'var(--glass-border)' }}
            >
              ⚡ 每 4 小时由 AI 分析引擎自动更新
            </p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

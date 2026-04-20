/**
 * Money — 盈利总控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 尝试从后端获取真实交易 P&L 和 AI 成本数据，无数据源的模块诚实标注"暂无数据源"
 * 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  DollarSign,
  TrendingUp,
  PieChart,
  Lightbulb,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  Loader2,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';
import { api } from '../../lib/api';
import { toast } from 'sonner';
import { EmptyState } from '../shared/EmptyState';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 自动刷新间隔 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/* ====== 类型定义 ====== */

/** 交易 P&L 后端数据 */
interface TradingPnlData {
  total_pnl?: number;
  daily_pnl?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  positions_count?: number;
  win_rate?: number;
  history?: Array<{ date: string; pnl: number }>;
  [key: string]: unknown;
}

/** AI 成本后端数据 */
interface OmegaCostData {
  total_cost?: number;
  today_cost?: number;
  by_model?: Array<{ model: string; cost: number; calls: number }>;
  by_provider?: Array<{ provider: string; cost: number }>;
  [key: string]: unknown;
}

/** 闲鱼利润后端数据 */
interface XianyuProfitData {
  orders?: number;
  revenue?: number;
  cost?: number;
  total_commission?: number;
  profit?: number;
  days?: number;
  today?: {
    consultations?: number;
    messages?: number;
    orders?: number;
    payments?: number;
    conversion_rate?: number;
  };
  [key: string]: unknown;
}

/* ====== 工具函数 ====== */

/** 格式化金额为人民币 */
function formatCNY(val: number | null | undefined): string {
  if (val == null) return '--';
  return `¥${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 格式化美元 */
function formatUSD(val: number | null | undefined): string {
  if (val == null) return '--';
  return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 渲染 ASCII 柱状图 */
function renderBar(value: number, maxValue: number, width: number = 24): string {
  if (maxValue <= 0) return '░'.repeat(width);
  const ratio = value / maxValue;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Money() {
  const { t } = useLanguage();
  /* 状态 */
  const [pnlData, setPnlData] = useState<TradingPnlData | null>(null);
  const [costData, setCostData] = useState<OmegaCostData | null>(null);
  const [xianyuData, setXianyuData] = useState<XianyuProfitData | null>(null);
  const [pnlError, setPnlError] = useState<string | null>(null);
  const [costError, setCostError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  /* 数据拉取 */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      /* 并行拉取交易 P&L、AI 成本、闲鱼利润 */
      const [pnlRes, costRes, xyRes] = await Promise.allSettled([
        clawbotFetchJson<TradingPnlData>('/api/v1/trading/pnl'),
        clawbotFetchJson<OmegaCostData>('/api/v1/omega/cost'),
        api.xianyuProfit(30) as Promise<XianyuProfitData>,
      ]);

      if (!mountedRef.current) return;

      if (pnlRes.status === 'fulfilled') {
        setPnlData(pnlRes.value);
        setPnlError(null);
      } else {
        setPnlError(t('money.pnlUnavailable'));
      }

      if (costRes.status === 'fulfilled') {
        setCostData(costRes.value);
        setCostError(null);
      } else {
        setCostError(t('money.costUnavailable'));
      }

      if (xyRes.status === 'fulfilled') {
        setXianyuData(xyRes.value);
      } else {
        setXianyuData(null);
      }
    } catch {
      if (!mountedRef.current) return;
      toast.error(t('money.loadFailed'));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();
    const timer = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchData]);

  /* P&L 历史图表数据 */
  const pnlHistory = pnlData?.history ?? [];
  const maxPnl = pnlHistory.length > 0 ? Math.max(...pnlHistory.map((d) => Math.abs(d.pnl))) : 0;

  /* AI 成本按模型分布 */
  const costByModel = costData?.by_model ?? [];

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 交易收益概览 (col-8) ====== */}
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
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  交易损益
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  交易损益 // 真实数据
                </p>
              </div>
              {loading && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {pnlError ? (
              <EmptyState title={pnlError} />
            ) : (
              <>
                {/* 顶部统计 4 列 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  {[
                    { label: t('money.totalPnl'), value: formatCNY(pnlData?.total_pnl), color: (pnlData?.total_pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
                    { label: t('money.dailyPnl'), value: formatCNY(pnlData?.daily_pnl), color: (pnlData?.daily_pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
                    { label: t('money.realized'), value: formatCNY(pnlData?.realized_pnl), color: 'var(--accent-cyan)' },
                    { label: t('money.unrealized'), value: formatCNY(pnlData?.unrealized_pnl), color: 'var(--accent-purple)' },
                  ].map((s) => (
                    <div key={s.label}>
                      <span className="text-label">{s.label}</span>
                      <div className="text-metric mt-1" style={{ color: s.color }}>
                        {s.value}
                      </div>
                    </div>
                  ))}
                </div>

                {/* 底部补充指标 */}
                <div
                  className="flex items-center gap-6 pt-4 border-t"
                  style={{ borderColor: 'var(--glass-border)' }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-label">{t('money.positionCount')}</span>
                    <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                      {pnlData?.positions_count ?? '--'}
                    </span>
                  </div>
                  {pnlData?.win_rate != null && (
                    <div className="flex items-center gap-2">
                      <span className="text-label">{t('money.winRate')}</span>
                      <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-green)' }}>
                        {(pnlData.win_rate * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </motion.div>

        {/* ====== AI 成本总览 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              AI 费用
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t("money.aiCost")}
            </h3>

            {costError ? (
              <EmptyState title={costError} />
            ) : (
              <div className="mt-6 flex-1 space-y-5">
                {/* 总成本 */}
                <div>
                  <span className="text-label">{t('money.totalCost')}</span>
                  <div className="text-metric mt-1" style={{ color: 'var(--accent-amber)' }}>
                    {formatUSD(costData?.total_cost)}
                  </div>
                </div>

                {/* 今日成本 */}
                <div>
                  <span className="text-label">{t('money.todayCost')}</span>
                  <div className="text-metric mt-1" style={{ color: 'var(--accent-cyan)' }}>
                    {formatUSD(costData?.today_cost)}
                  </div>
                </div>

                {/* 按模型分布 */}
                {costByModel.length > 0 && (
                  <div
                    className="border-t pt-4 mt-4"
                    style={{ borderColor: 'var(--glass-border)' }}
                  >
                    <span className="text-label">{t('money.costByModel')}</span>
                    <div className="mt-2 space-y-2">
                      {costByModel.slice(0, 4).map((m) => (
                        <div
                          key={m.model}
                          className="flex items-center justify-between py-1.5"
                        >
                          <span className="font-mono text-[11px] truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                            {m.model}
                          </span>
                          <span className="font-mono text-[11px] ml-2" style={{ color: 'var(--accent-amber)' }}>
                            {formatUSD(m.cost)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== P&L 历史趋势 ASCII 图 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              盈亏历史
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t("money.pnlHistory")}
            </h3>

            {pnlHistory.length === 0 ? (
              <EmptyState title={t("money.noHistoryData")} />
            ) : (
              <div className="flex-1 space-y-2">
                {pnlHistory.slice(-8).map((d) => (
                  <div key={d.date} className="flex items-center gap-3">
                    <span
                      className="font-mono text-xs w-20 shrink-0 text-right"
                      style={{ color: 'var(--text-tertiary)' }}
                    >
                      {d.date}
                    </span>
                    <span
                      className="font-mono text-xs flex-1 tracking-tight"
                      style={{ color: d.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', opacity: 0.85 }}
                    >
                      {renderBar(Math.abs(d.pnl), maxPnl)}
                    </span>
                    <span
                      className="font-mono text-xs w-20 text-right shrink-0 flex items-center gap-0.5 justify-end"
                      style={{ color: d.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
                    >
                      {d.pnl >= 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                      {formatCNY(d.pnl)}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* 底部统计行 */}
            {pnlHistory.length > 0 && (
              <div
                className="flex items-center justify-between mt-5 pt-4 border-t"
                style={{ borderColor: 'var(--glass-border)' }}
              >
                <div className="flex items-center gap-2">
                  <BarChart3 size={14} style={{ color: 'var(--accent-cyan)' }} />
                  <span className="text-label">{t('money.recentAvg')}</span>
                  <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                    {formatCNY(pnlHistory.reduce((a, d) => a + d.pnl, 0) / pnlHistory.length)}
                  </span>
                </div>
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== 收入源 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              其他收入
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t("money.otherRevenue")}
            </h3>

            <div className="flex-1 space-y-4">
              {/* 闲鱼销售收入 — 已接入 */}
              <div
                className="p-4 rounded-xl border"
                style={{ background: 'var(--bg-secondary)', borderColor: xianyuData ? 'rgba(255,170,0,0.3)' : 'var(--glass-border)' }}
              >
                <div className="flex items-start gap-2.5">
                  <PieChart size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-amber)' }} />
                  <div className="flex-1">
                    <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                      {t("money.xianyuRevenue")}
                    </p>
                    {xianyuData ? (
                      <div className="mt-2 space-y-1.5 font-mono text-xs">
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('money.revenueLastDays', )}</span>
                          <span className="font-bold" style={{ color: 'var(--accent-amber)' }}>
                            {formatCNY(xianyuData.revenue ?? 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('money.netProfit')}</span>
                          <span className="font-bold" style={{ color: (xianyuData.profit ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {formatCNY(xianyuData.profit ?? 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('money.orderCount')}</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{xianyuData.orders ?? 0}</span>
                        </div>
                        {xianyuData.today && (
                          <div className="flex justify-between pt-1 mt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                            <span style={{ color: 'var(--text-disabled)' }}>{t('money.todayConsultPayment')}</span>
                            <span style={{ color: 'var(--text-secondary)' }}>
                              {xianyuData.today.consultations ?? 0} / {xianyuData.today.payments ?? 0}
                            </span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="font-mono text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                        {t("money.xianyuLoading")}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* 套利策略 — 待接入 */}
              <div className="p-4 rounded-xl border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--glass-border)' }}>
                <div className="flex items-start gap-2.5">
                  <TrendingUp size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-cyan)' }} />
                  <div>
                    <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{t('money.arbitrageRevenue')}</p>
                    <p className="font-mono text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                      {t("money.pendingArbitrage")}
                    </p>
                  </div>
                </div>
              </div>

              {/* DeFi — 待接入 */}
              <div className="p-4 rounded-xl border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--glass-border)' }}>
                <div className="flex items-start gap-2.5">
                  <Lightbulb size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-purple)' }} />
                  <div>
                    <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{t('money.defiRevenue')}</p>
                    <p className="font-mono text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                      {t("money.pendingDefi")}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* 底部说明 */}
            <p
              className="font-mono text-[10px] mt-4 pt-3 border-t"
              style={{ color: 'var(--text-disabled)', borderColor: 'var(--glass-border)' }}
            >
              {t("money.revenueNote")}
            </p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

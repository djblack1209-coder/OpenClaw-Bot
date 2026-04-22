/**
 * Risk — 风险分析仪表盘
 * 展示投资组合风险指标、持仓集中度、交易风控参数
 * 数据来自 portfolioSummary + trading controls API
 * 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  ShieldAlert,
  Activity,
  PieChart,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
  ShieldCheck,
  BarChart3,
  Gauge,
  Lock,
} from 'lucide-react';
import { api } from '../../lib/api';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';
import { LoadingState } from '../shared/LoadingState';
import { SimpleErrorState as ErrorState } from '../shared/ErrorState';

/* ====== 常量 ====== */
const REFRESH_INTERVAL = 30_000;

/* ====== 类型定义 ====== */

/** 持仓条目 */
interface Position {
  symbol: string;
  name: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  market_value: number;
  weight: number;
}

/** 持仓摘要 */
interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  day_change: number;
  day_change_pct: number;
  positions: Position[];
  position_count: number;
  connected: boolean;
}

/** 交易控制参数 */
interface TradingControls {
  auto_trader_enabled: boolean;
  ibkr_live_mode: boolean;
  risk_protection_enabled: boolean;
  allow_short_selling: boolean;
  max_daily_trades: number;
}

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

/** 风险等级评估 — 返回 i18n key */
function assessRiskLevel(dayChangePct: number): { levelKey: string; color: string; bg: string } {
  const abs = Math.abs(dayChangePct);
  if (abs >= 5) return { levelKey: 'risk.highRisk', color: 'var(--accent-red)', bg: 'rgba(248, 113, 113, 0.08)' };
  if (abs >= 2) return { levelKey: 'risk.mediumRisk', color: 'var(--accent-amber)', bg: 'rgba(251, 191, 36, 0.08)' };
  return { levelKey: 'risk.lowRisk', color: 'var(--accent-green)', bg: 'rgba(52, 211, 153, 0.08)' };
}

/** 盈亏颜色 */
function pnlColor(value: number): string {
  return value >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
}

/** 格式化百分比 */
function fmtPct(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

/** 格式化美元 */
function fmtUsd(value: number): string {
  return `$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/* ====== 主组件 ====== */

export function Risk() {
  const { t } = useLanguage();
  /* ---- 状态 ---- */
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [controls, setControls] = useState<TradingControls | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- 数据拉取 ---- */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [pRes, cRes] = await Promise.allSettled([
        api.portfolioSummary(),
        clawbotFetchJson<TradingControls>('/api/v1/controls/trading'),
      ]);

      if (pRes.status === 'fulfilled' && pRes.value) {
        setPortfolio(pRes.value as PortfolioSummary);
      }
      if (cRes.status === 'fulfilled' && cRes.value) {
        setControls(cRes.value as TradingControls);
      }

      /* 两个接口都失败时才显示错误 */
      if (pRes.status === 'rejected' && cRes.status === 'rejected') {
        if (!silent) setError('risk_data_unavailable');
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'unknown error';
      if (!silent) setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  /* ---- 挂载 + 30 秒自动刷新 ---- */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ---- 衍生数据 ---- */

  /** 风险等级 */
  const riskLevel = useMemo(() => {
    return assessRiskLevel(portfolio?.day_change_pct ?? 0);
  }, [portfolio]);

  /** 持仓集中度（HHI 指数，归一化到 0-100） */
  const concentrationHHI = useMemo(() => {
    if (!portfolio?.positions?.length) return 0;
    const weights = portfolio.positions.map((p) => (p.weight || 0) * 100);
    const hhi = weights.reduce((sum, w) => sum + w * w, 0) / 10000;
    return Math.min(hhi * 100, 100);
  }, [portfolio]);

  /** 单一持仓最大权重 */
  const maxWeight = useMemo(() => {
    if (!portfolio?.positions?.length) return 0;
    return Math.max(...portfolio.positions.map((p) => (p.weight || 0) * 100));
  }, [portfolio]);

  /** 亏损持仓数 */
  const losingPositions = useMemo(() => {
    if (!portfolio?.positions?.length) return 0;
    return portfolio.positions.filter((p) => p.pnl < 0).length;
  }, [portfolio]);

  /** 最大单笔亏损 */
  const maxLoss = useMemo(() => {
    if (!portfolio?.positions?.length) return 0;
    const losses = portfolio.positions.map((p) => p.pnl).filter((v) => v < 0);
    return losses.length > 0 ? Math.min(...losses) : 0;
  }, [portfolio]);

  /* ---- 加载/错误状态 ---- */
  if (loading && !portfolio && !controls) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <LoadingState message={t('risk.loadingRiskData')} />
        </div>
      </div>
    );
  }

  if (error && !portfolio && !controls) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <ErrorState message={`${t('risk.loadFailed')}: ${error}`} onRetry={fetchData} />
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
         * 第一行：风险总览 (span-4) + 波动率 (span-4) + 集中度 (span-4)
         * ═══════════════════════════════════ */}

        {/* 风险总览 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <ShieldAlert size={16} style={{ color: riskLevel.color }} />
              <span className="text-label" style={{ color: riskLevel.color }}>
                RISK OVERVIEW
              </span>
            </div>

            {/* 风险等级仪表盘 */}
            <div className="text-center mb-6">
              <div
                className="inline-flex items-center justify-center w-24 h-24 rounded-full mb-3"
                style={{
                  background: riskLevel.bg,
                  border: `2px solid ${riskLevel.color}`,
                }}
              >
                <div className="text-center">
                  <Gauge size={24} style={{ color: riskLevel.color }} className="mx-auto mb-1" />
                  <span
                    className="font-display text-sm font-bold block"
                    style={{ color: riskLevel.color }}
                  >
                    {t(riskLevel.levelKey)}
                  </span>
                </div>
              </div>
            </div>

            {/* 关键指标 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('risk.portfolioValue')}
                </span>
                <span className="font-mono text-[13px] font-bold" style={{ color: 'var(--text-primary)' }}>
                  {portfolio ? fmtUsd(portfolio.total_value) : '--'}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('risk.totalPnl')}
                </span>
                <span
                  className="font-mono text-[13px] font-bold"
                  style={{ color: portfolio ? pnlColor(portfolio.total_pnl) : 'var(--text-disabled)' }}
                >
                  {portfolio ? `${portfolio.total_pnl >= 0 ? '+' : '-'}${fmtUsd(portfolio.total_pnl)}` : '--'}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('risk.dayChange')}
                </span>
                <span
                  className="font-mono text-[13px] font-bold"
                  style={{ color: portfolio ? pnlColor(portfolio.day_change_pct) : 'var(--text-disabled)' }}
                >
                  {portfolio ? fmtPct(portfolio.day_change_pct) : '--'}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('risk.positionCount')}
                </span>
                <span className="font-mono text-[13px] font-bold" style={{ color: 'var(--text-primary)' }}>
                  {portfolio?.position_count ?? '--'}
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 波动率 & 亏损分析 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <TrendingDown size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                VOLATILITY & LOSS
              </span>
            </div>

            <div className="space-y-4">
              {/* 日波动率（用 day_change_pct 绝对值近似） */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('risk.intradayVolatility')}
                  </span>
                  <span
                    className="font-display text-xl font-bold"
                    style={{ color: pnlColor(-(Math.abs(portfolio?.day_change_pct ?? 0) > 3 ? 1 : 0)) }}
                  >
                    {Math.abs(portfolio?.day_change_pct ?? 0).toFixed(2)}%
                  </span>
                </div>
                <div className="h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(Math.abs(portfolio?.day_change_pct ?? 0) * 10, 100)}%`,
                      background: Math.abs(portfolio?.day_change_pct ?? 0) > 3
                        ? 'var(--accent-red)'
                        : Math.abs(portfolio?.day_change_pct ?? 0) > 1
                          ? 'var(--accent-amber)'
                          : 'var(--accent-green)',
                    }}
                  />
                </div>
                <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-disabled)' }}>
                  {t('risk.basedOnDayChange')}
                </p>
              </div>

              {/* 分隔线 */}
              <div className="border-t" style={{ borderColor: 'var(--glass-border)' }} />

              {/* 亏损指标 */}
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                    {t('risk.losingPositions')}
                  </span>
                  <span
                    className="font-display text-2xl font-bold"
                    style={{ color: losingPositions > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                  >
                    {losingPositions}
                  </span>
                  <span className="font-mono text-[10px] block mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                    / {portfolio?.position_count ?? 0} {t('risk.totalPositions')}
                  </span>
                </div>
                <div className="text-center p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                    {t('risk.maxSingleLoss')}
                  </span>
                  <span
                    className="font-display text-2xl font-bold"
                    style={{ color: maxLoss < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                  >
                    {maxLoss < 0 ? `-${fmtUsd(maxLoss)}` : '$0'}
                  </span>
                </div>
              </div>

              {/* 分隔线 */}
              <div className="border-t" style={{ borderColor: 'var(--glass-border)' }} />

              {/* 总盈亏比率 */}
              <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('risk.totalPnlRate')}
                  </span>
                  <span
                    className="font-display text-lg font-bold"
                    style={{ color: portfolio ? pnlColor(portfolio.total_pnl_pct) : 'var(--text-disabled)' }}
                  >
                    {portfolio ? fmtPct(portfolio.total_pnl_pct) : '--'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 集中度分析 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <PieChart size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                CONCENTRATION
              </span>
            </div>

            {/* HHI 指数 */}
            <div className="text-center mb-4">
              <span
                className="font-display text-3xl font-bold"
                style={{
                  color: concentrationHHI > 50
                    ? 'var(--accent-red)'
                    : concentrationHHI > 25
                      ? 'var(--accent-amber)'
                      : 'var(--accent-green)',
                }}
              >
                {concentrationHHI.toFixed(1)}
              </span>
              <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-disabled)' }}>
                HHI {t('risk.concentrationIndex')} (0-100)
              </p>
            </div>

            {/* 最大权重 */}
            <div className="p-3 rounded-lg mb-4" style={{ background: 'rgba(255,255,255,0.02)' }}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('risk.maxSingleWeight')}
                </span>
                <span
                  className="font-mono text-[13px] font-bold"
                  style={{
                    color: maxWeight > 30
                      ? 'var(--accent-red)'
                      : maxWeight > 15
                        ? 'var(--accent-amber)'
                        : 'var(--accent-green)',
                  }}
                >
                  {maxWeight.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.05)' }}>
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(maxWeight, 100)}%`,
                    background: maxWeight > 30
                      ? 'var(--accent-red)'
                      : maxWeight > 15
                        ? 'var(--accent-amber)'
                        : 'var(--accent-green)',
                  }}
                />
              </div>
            </div>

            {/* 持仓权重分布 */}
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 max-h-[240px] scroll-container">
              {portfolio?.positions?.length ? (
                [...portfolio.positions]
                  .sort((a, b) => (b.weight || 0) - (a.weight || 0))
                  .map((pos) => {
                    const w = (pos.weight || 0) * 100;
                    return (
                      <div key={pos.symbol} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[11px] font-bold" style={{ color: 'var(--text-primary)' }}>
                            {pos.symbol}
                          </span>
                          <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                            {w.toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.05)' }}>
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${w}%`,
                              background: 'var(--accent-purple)',
                              opacity: 0.7,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })
              ) : (
                <div className="flex items-center justify-center py-8">
                  <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                    {t('risk.noPositionData')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* ═══════════════════════════════════
         * 第二行：风控参数 (span-6) + 风险提示 (span-6)
         * ═══════════════════════════════════ */}

        {/* 风控参数 */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <ShieldCheck size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                RISK CONTROLS
              </span>
            </div>

            {controls ? (
              <div className="grid grid-cols-2 gap-3">
                {/* 风控保护 */}
                <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldAlert size={14} style={{ color: controls.risk_protection_enabled ? 'var(--accent-green)' : 'var(--accent-red)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {t('risk.riskProtection')}
                    </span>
                  </div>
                  <span
                    className="font-display text-lg font-bold"
                    style={{ color: controls.risk_protection_enabled ? 'var(--accent-green)' : 'var(--accent-red)' }}
                  >
                    {controls.risk_protection_enabled ? t('risk.enabled') : t('risk.disabled')}
                  </span>
                </div>

                {/* 自动交易 */}
                <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <Activity size={14} style={{ color: controls.auto_trader_enabled ? 'var(--accent-green)' : 'var(--accent-amber)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {t('risk.autoTrade')}
                    </span>
                  </div>
                  <span
                    className="font-display text-lg font-bold"
                    style={{ color: controls.auto_trader_enabled ? 'var(--accent-green)' : 'var(--accent-amber)' }}
                  >
                    {controls.auto_trader_enabled ? t('risk.enabled') : t('risk.disabled')}
                  </span>
                </div>

                {/* 实盘模式 */}
                <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <Lock size={14} style={{ color: controls.ibkr_live_mode ? 'var(--accent-red)' : 'var(--accent-cyan)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {t('risk.liveMode')}
                    </span>
                  </div>
                  <span
                    className="font-display text-lg font-bold"
                    style={{ color: controls.ibkr_live_mode ? 'var(--accent-red)' : 'var(--accent-cyan)' }}
                  >
                    {controls.ibkr_live_mode ? t('risk.live') : t('risk.paper')}
                  </span>
                </div>

                {/* 日交易上限 */}
                <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 size={14} style={{ color: 'var(--accent-purple)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {t('risk.maxDailyTrades')}
                    </span>
                  </div>
                  <span
                    className="font-display text-lg font-bold"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {controls.max_daily_trades}
                  </span>
                  <span className="font-mono text-[10px] ml-1" style={{ color: 'var(--text-disabled)' }}>
                    {t('risk.perDay')}
                  </span>
                </div>

                {/* 做空许可 */}
                <div className="col-span-2 p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <TrendingDown size={14} style={{ color: controls.allow_short_selling ? 'var(--accent-amber)' : 'var(--text-disabled)' }} />
                      <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                        {t('risk.shortSelling')}
                      </span>
                    </div>
                    <span
                      className="px-3 py-1 rounded-full font-mono text-[11px]"
                      style={{
                        background: controls.allow_short_selling ? 'rgba(251, 191, 36, 0.1)' : 'rgba(255,255,255,0.04)',
                        color: controls.allow_short_selling ? 'var(--accent-amber)' : 'var(--text-disabled)',
                        border: `1px solid ${controls.allow_short_selling ? 'rgba(251, 191, 36, 0.3)' : 'var(--glass-border)'}`,
                      }}
                    >
                      {controls.allow_short_selling ? t('risk.allowed') : t('risk.prohibited')}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center py-8">
                <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('risk.cannotGetControls')}
                </span>
              </div>
            )}
          </div>
        </motion.div>

        {/* 风险提示 */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                RISK ALERTS
              </span>
            </div>

            <div className="space-y-3">
              {/* 动态生成风险提示 */}
              {(() => {
                const alerts: { msg: string; level: 'error' | 'warning' | 'info' }[] = [];

                /* 高波动 */
                if (portfolio && Math.abs(portfolio.day_change_pct) > 3) {
                  alerts.push({
                    msg: `${t('risk.alertHighVolatility')} ${fmtPct(portfolio.day_change_pct)}`,
                    level: 'error',
                  });
                }

                /* 高集中度 */
                if (concentrationHHI > 40) {
                  alerts.push({
                    msg: `${t('risk.alertHighConcentration')} HHI=${concentrationHHI.toFixed(1)}`,
                    level: 'warning',
                  });
                }

                /* 单一持仓过大 */
                if (maxWeight > 30) {
                  alerts.push({
                    msg: `${t('risk.alertSingleWeight')} ${maxWeight.toFixed(1)}%`,
                    level: 'warning',
                  });
                }

                /* 较多亏损仓 */
                if (portfolio && losingPositions > portfolio.position_count / 2) {
                  alerts.push({
                    msg: `${losingPositions}/${portfolio.position_count} ${t('risk.alertLosingPositions')}`,
                    level: 'warning',
                  });
                }

                /* 风控未开启 */
                if (controls && !controls.risk_protection_enabled) {
                  alerts.push({
                    msg: t('risk.alertRiskNotEnabled'),
                    level: 'error',
                  });
                }

                /* 做空已开启 */
                if (controls && controls.allow_short_selling) {
                  alerts.push({
                    msg: t('risk.alertShortEnabled'),
                    level: 'info',
                  });
                }

                /* 无风险提示 */
                if (alerts.length === 0) {
                  alerts.push({
                    msg: t('risk.alertNoRisk'),
                    level: 'info',
                  });
                }

                const levelColors = {
                  error: { color: 'var(--accent-red)', bg: 'rgba(248, 113, 113, 0.06)' },
                  warning: { color: 'var(--accent-amber)', bg: 'rgba(251, 191, 36, 0.06)' },
                  info: { color: 'var(--accent-cyan)', bg: 'rgba(0, 245, 255, 0.06)' },
                };

                return alerts.map((alert, idx) => {
                  const conf = levelColors[alert.level];
                  return (
                    <motion.div
                      key={idx}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.05 }}
                      className="flex items-start gap-3 p-3 rounded-lg"
                      style={{
                        background: conf.bg,
                        borderLeft: `2px solid ${conf.color}`,
                      }}
                    >
                      <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: conf.color }} />
                      <span className="font-mono text-[11px] leading-relaxed" style={{ color: conf.color }}>
                        {alert.msg}
                      </span>
                    </motion.div>
                  );
                });
              })()}
            </div>

            {/* 刷新按钮 */}
            <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--glass-border)' }}>
              <button
                onClick={() => fetchData()}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-mono text-[11px] transition-all duration-200"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--glass-border)',
                }}
              >
                <RefreshCw size={12} />
                {t('risk.refreshRiskData')}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

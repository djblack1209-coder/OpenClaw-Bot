/**
 * Trading — 交易引擎
 * 轻量级交易总览页面，展示系统状态、活跃信号、K 线概览
 * 提供快速跳转到 Portfolio 页面各标签页的入口
 * 数据来自后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingUp,
  Activity,
  Zap,
  BarChart3,
  ArrowRight,
  RefreshCw,
  Loader2,
  AlertTriangle,
  Power,
  ShieldCheck,
  LineChart,
  Briefcase,
  CandlestickChart,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useAppStore } from '../../stores/appStore';
import { useLanguage } from '../../i18n';

/* ====== 常量 ====== */
const REFRESH_INTERVAL = 30_000;

/* ====== 类型定义 ====== */

/** 交易系统状态 */
interface TradingSystem {
  engine_status: string;
  ibkr_connected: boolean;
  auto_trader_enabled: boolean;
  risk_protection_enabled: boolean;
  total_positions: number;
  daily_pnl: number;
  daily_trades: number;
  max_daily_trades: number;
}

/** 交易信号 */
interface TradingSignal {
  symbol: string;
  signal: string;
  confidence: number;
  source: string;
  timestamp: string;
}

/** K 线数据点 */
interface KlinePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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

/** 时间格式化 */
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

/** 信号颜色 */
function signalColor(signal: string): string {
  const s = signal.toLowerCase();
  if (s.includes('buy') || s.includes('bullish') || s.includes('看多')) return 'var(--accent-green)';
  if (s.includes('sell') || s.includes('bearish') || s.includes('看空')) return 'var(--accent-red)';
  return 'var(--accent-amber)';
}

/** 信号中文标签 — 使用 i18n key */

function signalLabelKey(signal: string): string {
  const s = signal.toLowerCase();
  if (s.includes('strong') && (s.includes('buy') || s.includes('bullish'))) return 'trading.signalStrongBuy';
  if (s.includes('buy') || s.includes('bullish') || s.includes('看多')) return 'trading.signalBuy';
  if (s.includes('strong') && (s.includes('sell') || s.includes('bearish'))) return 'trading.signalStrongSell';
  if (s.includes('sell') || s.includes('bearish') || s.includes('看空')) return 'trading.signalSell';
  if (s.includes('neutral') || s.includes('hold')) return 'trading.signalNeutral';
  return '';
}

/** 盈亏颜色 */
function pnlColor(value: number): string {
  return value >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
}

/* ====== 加载/错误状态组件 ====== */

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

export function Trading() {
  const { t } = useLanguage();
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);

  /* ---- 状态 ---- */
  const [system, setSystem] = useState<TradingSystem | null>(null);
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [klineData, setKlineData] = useState<KlinePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- 数据拉取 ---- */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      /* 并行请求三个接口 */
      const [sysRes, sigRes, kRes] = await Promise.allSettled([
        clawbotFetchJson<TradingSystem>('/api/v1/trading/system'),
        clawbotFetchJson<{ signals: TradingSignal[] }>('/api/v1/trading/signals'),
        clawbotFetchJson<{ data: KlinePoint[] }>('/api/v1/trading/kline?symbol=SPY&interval=1d&limit=30'),
      ]);

      if (sysRes.status === 'fulfilled' && sysRes.value) {
        setSystem(sysRes.value as TradingSystem);
      }
      if (sigRes.status === 'fulfilled' && sigRes.value) {
        const resp = sigRes.value as { signals?: TradingSignal[] };
        setSignals(Array.isArray(resp.signals) ? resp.signals : Array.isArray(resp) ? resp as unknown as TradingSignal[] : []);
      }
      if (kRes.status === 'fulfilled' && kRes.value) {
        const resp = kRes.value as { data?: KlinePoint[] };
        setKlineData(Array.isArray(resp.data) ? resp.data : Array.isArray(resp) ? resp as unknown as KlinePoint[] : []);
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

  /* ---- 快速跳转按钮 ---- */
  const quickLinks = [
    { label: t('trading.portfolioOverview'), icon: Briefcase, desc: t('trading.viewPositionsPnl') },
    { label: t('trading.tradeDecision'), icon: TrendingUp, desc: t('trading.aiTeamVote') },
    { label: t('trading.autoTrade'), icon: Zap, desc: t('trading.configAutoStrategy') },
    { label: t('trading.backtestAnalysis'), icon: LineChart, desc: t('trading.strategyBacktest') },
    { label: t('trading.tradeLogs'), icon: BarChart3, desc: t('trading.viewTradeHistory') },
  ];

  /* ---- 加载/错误状态 ---- */
  if (loading && !system) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <LoadingState message={t('trading.loadingSystem')} />
        </div>
      </div>
    );
  }

  if (error && !system) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <ErrorState message={`${t('trading.systemLoadFailed')}: ${error}`} onRetry={fetchData} />
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
         * 第一行：系统状态 (span-4) + 活跃信号 (span-4) + K 线概览 (span-4)
         * ═══════════════════════════════════ */}

        {/* 系统状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-4">
              <Activity size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                SYSTEM STATUS
              </span>
            </div>

            {system ? (
              <div className="space-y-4">
                {/* 引擎状态 */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('trading.engineStatus')}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: system.engine_status === 'running'
                          ? 'var(--accent-green)'
                          : 'var(--accent-red)',
                      }}
                    />
                    <span
                      className="font-mono text-[11px] font-bold uppercase"
                      style={{
                        color: system.engine_status === 'running'
                          ? 'var(--accent-green)'
                          : 'var(--accent-red)',
                      }}
                    >
                      {system.engine_status === 'running' ? t('trading.running') : t('trading.stopped')}
                    </span>
                  </div>
                </div>

                {/* IBKR 连接 */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('trading.ibkrConnection')}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Power size={12} style={{ color: system.ibkr_connected ? 'var(--accent-green)' : 'var(--accent-red)' }} />
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: system.ibkr_connected ? 'var(--accent-green)' : 'var(--accent-red)' }}
                    >
                      {system.ibkr_connected ? t('trading.connected') : t('trading.disconnected')}
                    </span>
                  </div>
                </div>

                {/* 自动交易 */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('trading.autoTrade')}
                  </span>
                  <span
                    className="px-2 py-0.5 rounded-full font-mono text-[10px]"
                    style={{
                      background: system.auto_trader_enabled ? 'rgba(52, 211, 153, 0.1)' : 'rgba(255,255,255,0.04)',
                      color: system.auto_trader_enabled ? 'var(--accent-green)' : 'var(--text-disabled)',
                      border: `1px solid ${system.auto_trader_enabled ? 'rgba(52, 211, 153, 0.3)' : 'var(--glass-border)'}`,
                    }}
                  >
                    {system.auto_trader_enabled ? t('trading.enabled') : t('trading.disabled')}
                  </span>
                </div>

                {/* 风控保护 */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {t('trading.riskProtection')}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck size={12} style={{ color: system.risk_protection_enabled ? 'var(--accent-green)' : 'var(--accent-amber)' }} />
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: system.risk_protection_enabled ? 'var(--accent-green)' : 'var(--accent-amber)' }}
                    >
                      {system.risk_protection_enabled ? t('trading.enabled') : t('trading.disabled')}
                    </span>
                  </div>
                </div>

                {/* 分隔线 */}
                <div className="border-t" style={{ borderColor: 'var(--glass-border)' }} />

                {/* 数值指标 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="text-center p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                      {t('trading.positionCount')}
                    </span>
                    <span className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                      {system.total_positions}
                    </span>
                  </div>
                  <div className="text-center p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                      {t('trading.dailyPnl')}
                    </span>
                    <span className="font-display text-lg font-bold" style={{ color: pnlColor(system.daily_pnl) }}>
                      {system.daily_pnl >= 0 ? '+' : ''}{system.daily_pnl.toFixed(2)}
                    </span>
                  </div>
                  <div className="text-center p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                      {t('trading.dailyTrades')}
                    </span>
                    <span className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                      {system.daily_trades}
                    </span>
                  </div>
                  <div className="text-center p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <span className="font-mono text-[10px] block" style={{ color: 'var(--text-disabled)' }}>
                      {t('trading.maxDailyTrades')}
                    </span>
                    <span className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                      {system.max_daily_trades}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center py-8">
                <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('trading.cannotGetStatus')}
                </span>
              </div>
            )}
          </div>
        </motion.div>

        {/* 活跃信号 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-1">
              <Zap size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                ACTIVE SIGNALS
              </span>
            </div>
            <p className="font-mono text-[11px] mb-4" style={{ color: 'var(--text-tertiary)' }}>
              {signals.length} {t('trading.activeSignalsCount')}
            </p>

            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 max-h-[380px] scroll-container">
              {signals.length > 0 ? signals.map((sig, idx) => (
                <motion.div
                  key={`${sig.symbol}-${idx}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.04, duration: 0.25 }}
                  className="p-3 rounded-lg"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="font-display text-sm font-bold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {sig.symbol}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded-full font-mono text-[10px] font-bold"
                      style={{
                        color: signalColor(sig.signal),
                        background: `${signalColor(sig.signal)}15`,
                        border: `1px solid ${signalColor(sig.signal)}30`,
                      }}
                    >
                      {signalLabelKey(sig.signal) ? t(signalLabelKey(sig.signal)) : sig.signal}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {t('trading.confidence')}: {(sig.confidence * 100).toFixed(0)}%
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {sig.source} · {timeAgo(sig.timestamp)}
                    </span>
                  </div>
                  {/* 置信度进度条 */}
                  <div className="mt-2 h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.05)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${sig.confidence * 100}%`,
                        background: signalColor(sig.signal),
                        opacity: 0.7,
                      }}
                    />
                  </div>
                </motion.div>
              )) : (
                <div className="flex flex-col items-center justify-center py-12 gap-2">
                  <Zap size={24} style={{ color: 'var(--text-disabled)', opacity: 0.4 }} />
                  <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                    {t('trading.noActiveSignals')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* K 线概览 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-1">
              <CandlestickChart size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                SPY KLINE (1D)
              </span>
            </div>
            <p className="font-mono text-[11px] mb-4" style={{ color: 'var(--text-tertiary)' }}>
              {t('trading.recent')} {klineData.length} {t('trading.tradingDays')}
            </p>

            {klineData.length > 0 ? (
              <div className="flex-1 min-h-0">
                {/* 简易 K 线柱状图 — 用 CSS 渲染 */}
                <div className="flex items-end gap-[2px] h-[200px]">
                  {(() => {
                    const closes = klineData.map((k) => k.close);
                    const min = Math.min(...closes);
                    const max = Math.max(...closes);
                    const range = max - min || 1;

                    return klineData.map((k, idx) => {
                      const isUp = k.close >= k.open;
                      const barHeight = ((k.close - min) / range) * 160 + 20;
                      return (
                        <div
                          key={idx}
                          className="flex-1 rounded-t-sm transition-all duration-200"
                          style={{
                            height: `${barHeight}px`,
                            background: isUp ? 'var(--accent-green)' : 'var(--accent-red)',
                            opacity: 0.6,
                            minWidth: '3px',
                          }}
                          title={`${k.date}\nO: ${k.open.toFixed(2)} H: ${k.high.toFixed(2)} L: ${k.low.toFixed(2)} C: ${k.close.toFixed(2)}`}
                        />
                      );
                    });
                  })()}
                </div>

                {/* 价格范围 */}
                {klineData.length > 0 && (
                  <div className="flex items-center justify-between mt-2">
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {klineData[0]?.date?.slice(5) || ''}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {klineData[klineData.length - 1]?.date?.slice(5) || ''}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 gap-2 flex-1">
                <LineChart size={24} style={{ color: 'var(--text-disabled)', opacity: 0.4 }} />
                <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('trading.noKlineData')}
                </span>
              </div>
            )}
          </div>
        </motion.div>

        {/* ═══════════════════════════════════
         * 第二行：快速跳转到 Portfolio 标签页 (span-12)
         * ═══════════════════════════════════ */}

        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center gap-3 mb-1">
              <Briefcase size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                QUICK ACCESS
              </span>
            </div>
            <p className="font-mono text-[11px] mb-4" style={{ color: 'var(--text-tertiary)' }}>
              {t('trading.quickJumpToPortfolio')}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
              {quickLinks.map((link) => {
                const Icon = link.icon;
                return (
                  <button
                    key={link.label}
                    onClick={() => setCurrentPage('portfolio')}
                    className="flex items-center gap-3 p-4 rounded-xl transition-all duration-200 group text-left"
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid var(--glass-border)',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                      e.currentTarget.style.borderColor = 'var(--accent-cyan)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.02)';
                      e.currentTarget.style.borderColor = 'var(--glass-border)';
                    }}
                  >
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                      style={{ background: 'rgba(0, 245, 255, 0.06)' }}
                    >
                      <Icon size={18} style={{ color: 'var(--accent-cyan)' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span
                        className="font-display text-sm font-medium block"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {link.label}
                      </span>
                      <span
                        className="font-mono text-[10px] block mt-0.5"
                        style={{ color: 'var(--text-disabled)' }}
                      >
                        {link.desc}
                      </span>
                    </div>
                    <ArrowRight
                      size={14}
                      className="shrink-0 transition-transform group-hover:translate-x-1"
                      style={{ color: 'var(--text-disabled)' }}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* 手动刷新 */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="flex justify-center">
            <button
              onClick={() => fetchData()}
              className="flex items-center gap-2 px-6 py-2 rounded-lg font-mono text-[11px] transition-all duration-200"
              style={{
                background: 'rgba(255,255,255,0.03)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--glass-border)',
              }}
            >
              <RefreshCw size={12} />
                {t('trading.refreshData')}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

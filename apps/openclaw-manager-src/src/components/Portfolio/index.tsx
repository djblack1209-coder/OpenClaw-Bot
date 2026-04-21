/**
 * Portfolio — 投资组合页面 (Sonic Abyss Bento Grid 风格)
 * 5 个标签页：持仓概览 / 交易决策 / 自动交易 / 回测分析 / 交易日志
 * 数据来自后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { toast } from '@/lib/notify';

import { api } from '../../lib/api';
import { clawbotFetch, clawbotFetchJson, LONG_TIMEOUT_MS } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

/* ====== 类型定义 ====== */

/** 持仓条目 */
interface Position {
  symbol: string; name: string; quantity: number; avg_price: number;
  current_price: number; pnl: number; pnl_pct: number; market_value: number; weight: number;
}

/** 持仓摘要 */
interface PortfolioSummary {
  total_value: number; total_cost: number; total_pnl: number; total_pnl_pct: number;
  day_change: number; day_change_pct: number; positions: Position[];
  position_count: number; connected: boolean;
}

/** AI 团队成员投票 */
interface TeamMember { analyst: string; signal: string; confidence: number; reasoning: string; }
interface TeamResponse { team: TeamMember[]; }

/** 交易投票请求结果 */
interface VoteResult {
  symbol?: string;
  period?: string;
  votes?: Array<{
    bot_name?: string;
    analyst?: string;
    signal?: string;
    vote?: string;
    confidence?: number;
    reasoning?: string;
    reason?: string;
  }>;
  team?: Array<{
    bot_name?: string;
    analyst?: string;
    signal?: string;
    vote?: string;
    confidence?: number;
    reasoning?: string;
    reason?: string;
  }>;
  consensus?: string;
  summary?: string;
}

/** 交易控制开关 */
interface TradingControls {
  auto_trader_enabled: boolean;
  ibkr_live_mode: boolean;
  risk_protection_enabled: boolean;
  allow_short_selling: boolean;
  max_daily_trades: number;
}

/** 回测结果 */
interface BacktestResult {
  total_return?: number;
  annual_return?: number;
  max_drawdown?: number;
  sharpe_ratio?: number;
  win_rate?: number;
  total_trades?: number;
  [key: string]: unknown;
}

/** 交易日志条目 */
interface TradeLogItem {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  entry_time: string;
  exit_price?: number;
  exit_time?: string;
  pnl?: number;
  pnl_pct?: number;
  status: string;
  entry_reason?: string;
  exit_reason?: string;
  decided_by?: string;
  hold_duration_hours?: number;
}

/** 估值分析结果 */
interface ValuationResult {
  symbol: string;
  current_price: number;
  company_name: string;
  wacc: number;
  signal: string;
  confidence: number;
  dcf: { bull_value: number; base_value: number; bear_value: number; weighted_value: number; margin_of_safety: number };
  owner_earnings: number;
  ev_ebitda: { current_multiple: number; implied_value: number; upside_percent: number };
  residual_income: number;
  financial_data: Record<string, number | null | undefined>;
}

/* ====== 标签页 ID ====== */
type TabId = 'overview' | 'decision' | 'auto' | 'backtest' | 'valuation' | 'logs';

const TAB_LIST: { id: TabId; labelKey: string }[] = [
  { id: 'overview', labelKey: 'portfolio.tabs.overview' },
  { id: 'decision', labelKey: 'portfolio.tabs.decision' },
  { id: 'auto',     labelKey: 'portfolio.tabs.auto' },
  { id: 'backtest', labelKey: 'portfolio.tabs.backtest' },
  { id: 'valuation', labelKey: 'portfolio.tabs.valuation' },
  { id: 'logs',     labelKey: 'portfolio.tabs.logs' },
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

/** 盈亏颜色 */
function pnlColor(value: number): string {
  return value >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
}

/** 盈亏符号 */
function pnlSign(value: number): string {
  return value >= 0 ? '+' : '';
}

/** 格式化美元金额 */
function fmtUsd(value: number): string {
  return '$' + Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** 格式化百分比 */
function fmtPct(value: number | undefined): string {
  if (value === undefined || value === null) return '--';
  return `${(value * 100).toFixed(2)}%`;
}

/** 判断信号方向 */
function isBull(s: string) { const l = s.toLowerCase(); return l.includes('buy') || l.includes('bullish') || l.includes('看多'); }
function isBear(s: string) { const l = s.toLowerCase(); return l.includes('sell') || l.includes('bearish') || l.includes('看空'); }

/** 信号 → 颜色 */
function signalColor(signal: string): string {
  return isBull(signal) ? 'var(--accent-green)' : isBear(signal) ? 'var(--accent-red)' : 'var(--accent-amber)';
}
/** 信号 → 分类 */
function signalCategory(signal: string): 'bull' | 'bear' | 'neutral' {
  return isBull(signal) ? 'bull' : isBear(signal) ? 'bear' : 'neutral';
}
/** 信号 → 中文标签 */
function signalLabel(signal: string, t: (key: string) => string): string {
  const s = signal.toLowerCase();
  if (s.includes('strong') && isBull(signal)) return t('portfolio.signalStrongBullish');
  if (isBull(signal)) return t('portfolio.signalBullish');
  if (s.includes('strong') && isBear(signal)) return t('portfolio.signalStrongBearish');
  if (isBear(signal)) return t('portfolio.signalBearish');
  if (s.includes('neutral') || s.includes('hold') || s === '中性') return t('portfolio.signalNeutral');
  return signal;
}

/* ====== 公共样式 ====== */

/** 标准按钮样式（带 loading / disabled 支持） */
function actionBtnStyle(disabled: boolean, color: string = 'var(--accent-cyan)'): React.CSSProperties {
  return {
    background: disabled ? 'rgba(255,255,255,0.03)' : color,
    color: disabled ? 'var(--text-disabled)' : '#000',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  };
}

/** 标准输入框样式 */
const inputStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.1)',
  color: 'var(--text-primary)',
  borderRadius: 8,
  padding: '8px 12px',
  outline: 'none',
};

/* ====== 主组件 ====== */

export function Portfolio() {
  const { t } = useLanguage();
  /* ---- 标签页状态 ---- */
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  /* ---- 持仓概览状态 ---- */
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sellingSymbol, setSellingSymbol] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- 交易决策状态 ---- */
  const [voteSymbol, setVoteSymbol] = useState('');
  const [votePeriod, setVotePeriod] = useState('1d');
  const [voteLoading, setVoteLoading] = useState(false);
  const [voteResult, setVoteResult] = useState<VoteResult | null>(null);

  /* ---- 自动交易状态 ---- */
  const [controls, setControls] = useState<TradingControls | null>(null);
  const [controlsLoading, setControlsLoading] = useState(false);
  const [togglingKey, setTogglingKey] = useState<string | null>(null);

  /* ---- 回测分析状态 ---- */
  const [btSymbol, setBtSymbol] = useState('');
  const [btStrategy, setBtStrategy] = useState('ma_cross');
  const [btPeriod, setBtPeriod] = useState('1y');
  const [btLoading, setBtLoading] = useState(false);
  const [btResult, setBtResult] = useState<BacktestResult | null>(null);

  /* ---- 交易日志状态 ---- */
  const [journalItems, setJournalItems] = useState<TradeLogItem[]>([]);
  const [journalTotal, setJournalTotal] = useState(0);
  const [journalPage, setJournalPage] = useState(0);
  const [journalLoading, setJournalLoading] = useState(false);
  const [journalFilter, setJournalFilter] = useState<'all' | 'open' | 'closed'>('all');
  const JOURNAL_PAGE_SIZE = 15;

  /* ---- 估值分析状态 ---- */
  const [valSymbol, setValSymbol] = useState('');
  const [valLoading, setValLoading] = useState(false);
  const [valResult, setValResult] = useState<ValuationResult | null>(null);

  /* ====== 数据拉取：持仓概览 ====== */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      /* 并行请求持仓摘要 + AI 团队 */
      const [pRes, tRes] = await Promise.allSettled([
        api.portfolioSummary(),
        api.omegaInvestmentTeam(),
      ]);

      if (pRes.status === 'fulfilled' && pRes.value) {
        setPortfolio(pRes.value as PortfolioSummary);
      } else if (pRes.status === 'rejected') {
        console.warn('[Portfolio] 持仓摘要请求失败:', pRes.reason);
        if (!silent) setError(t('portfolio.error.cannotLoad'));
      }

      if (tRes.status === 'fulfilled' && tRes.value) {
        const data = tRes.value as unknown as TeamResponse;
        setTeam(Array.isArray(data.team) ? data.team : []);
      }
    } catch (e) {
      console.error('[Portfolio] 数据拉取异常:', e);
      if (!silent) setError(t('portfolio.error.networkError'));
    } finally {
      setLoading(false);
    }
  }, []);

  /* ---- 挂载 + 30 秒自动刷新（仅在持仓概览标签页时） ---- */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(() => fetchData(true), 30_000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ====== 卖出操作（带 Toast 反馈） ====== */
  const handleSell = async (symbol: string, quantity: number) => {
    setSellingSymbol(symbol);
    try {
      await api.tradingSell(symbol, quantity, 'MKT');
      toast.success(`${symbol} ${t('portfolio.sell.success')}`, { description: `${t('portfolio.sell.quantity')}: ${quantity}`, channel: 'log' });
      /* 刷新数据 */
      fetchData(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portfolio.error.unknown');
      toast.error(`${symbol} ${t('portfolio.sell.failed')}`, { description: msg, channel: 'notification' });
      console.error(`[Portfolio] 卖出失败: ${symbol}`, msg);
    } finally {
      setSellingSymbol(null);
    }
  };

  /* ====== 交易决策：触发投票 ====== */
  const handleVote = async () => {
    const sym = voteSymbol.trim().toUpperCase();
    if (!sym) {
      toast.info(t('portfolio.vote.enterSymbol'), { channel: 'log' });
      return;
    }
    setVoteLoading(true);
    setVoteResult(null);
    try {
      const resp = await clawbotFetch('/api/v1/trading/vote', {
        method: 'POST',
        body: JSON.stringify({ symbol: sym, period: votePeriod }),
      }, LONG_TIMEOUT_MS);
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text || t('portfolio.error.requestFailed')}`);
      }
      const data: VoteResult = await resp.json();
      setVoteResult(data);
      toast.success(t('portfolio.vote.complete'), { description: `${sym} · ${votePeriod}`, channel: 'log' });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portfolio.error.unknown');
      toast.error(t('portfolio.vote.failed'), { description: msg, channel: 'notification' });
    } finally {
      setVoteLoading(false);
    }
  };

  /* ====== 自动交易：拉取控制开关 ====== */
  const fetchControls = useCallback(async () => {
    setControlsLoading(true);
    try {
      const data = await clawbotFetchJson<TradingControls>('/api/v1/controls/trading');
      setControls(data);
    } catch (e) {
      console.warn('[Portfolio] 拉取交易控制失败:', e);
      toast.error(t('portfolio.controls.fetchFailed'), { channel: 'notification' });
    } finally {
      setControlsLoading(false);
    }
  }, []);

  /* 切换到自动交易标签时自动拉取 */
  useEffect(() => {
    if (activeTab === 'auto') {
      fetchControls();
    }
  }, [activeTab, fetchControls]);

  /* 更新单个控制项 */
  const updateControl = async (key: keyof TradingControls, value: boolean | number) => {
    if (!controls) return;
    setTogglingKey(key);
    try {
      await clawbotFetch('/api/v1/controls/trading', {
        method: 'POST',
        body: JSON.stringify({ ...controls, [key]: value }),
      });
      setControls(prev => prev ? { ...prev, [key]: value } : prev);
      toast.success(t('portfolio.controls.updated'), { channel: 'log' });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portfolio.error.unknown');
      toast.error(t('portfolio.controls.updateFailed'), { description: msg, channel: 'notification' });
    } finally {
      setTogglingKey(null);
    }
  };

  /* ====== 回测分析：触发回测 ====== */
  const handleBacktest = async () => {
    const sym = btSymbol.trim().toUpperCase();
    if (!sym) {
      toast.info(t('portfolio.vote.enterSymbol'), { channel: 'log' });
      return;
    }
    setBtLoading(true);
    setBtResult(null);
    try {
      const data = await clawbotFetchJson<BacktestResult>(
        `/api/v1/omega/investment/backtest?symbol=${encodeURIComponent(sym)}&strategy=${btStrategy}&period=${btPeriod}`,
        undefined,
        LONG_TIMEOUT_MS,
      );
      setBtResult(data);
      toast.success(t('portfolio.backtest.complete'), { description: `${sym} · ${btStrategy}`, channel: 'log' });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portfolio.error.unknown');
      toast.error(t('portfolio.backtest.failed'), { description: msg, channel: 'notification' });
    } finally {
      setBtLoading(false);
    }
  };

  /* ====== 交易日志数据拉取 ====== */
  const fetchJournal = useCallback(async (page = 0, filter: 'all' | 'open' | 'closed' = journalFilter) => {
    setJournalLoading(true);
    try {
      const data = await api.tradingJournal({
        offset: page * JOURNAL_PAGE_SIZE,
        limit: JOURNAL_PAGE_SIZE,
        status: filter === 'all' ? '' : filter,
      }) as { items: TradeLogItem[]; total: number };
      setJournalItems(data.items || []);
      setJournalTotal(data.total || 0);
      setJournalPage(page);
    } catch (e) {
      console.error('[Portfolio] 交易日志请求失败:', e);
      setJournalItems([]);
      setJournalTotal(0);
    } finally {
      setJournalLoading(false);
    }
  }, [journalFilter]);

  /* 切换到日志 Tab 时自动加载 */
  useEffect(() => {
    if (activeTab === 'logs') {
      fetchJournal(0);
    }
  }, [activeTab, fetchJournal]);

  /* ====== 估值分析 ====== */
  const handleValuation = async () => {
    const sym = valSymbol.trim().toUpperCase();
    if (!sym) {
      toast.info(t('portfolio.vote.enterSymbol'), { channel: 'log' });
      return;
    }
    setValLoading(true);
    setValResult(null);
    try {
      const data = await api.tradingValuation(sym) as ValuationResult;
      setValResult(data);
      toast.success(t('portfolio.valuation.complete'), { description: `${data.company_name || sym}`, channel: 'log' });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('portfolio.error.unknown');
      toast.error(t('portfolio.valuation.failed'), { description: msg, channel: 'notification' });
    } finally {
      setValLoading(false);
    }
  };

  /* ====== 加载态（仅初始加载时显示） ====== */
  if (loading && !portfolio) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block w-8 h-8 border-2 border-t-transparent rounded-full animate-spin mb-4"
               style={{ borderColor: 'var(--accent-cyan)', borderTopColor: 'transparent' }} />
          <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('portfolio.loading')}
          </p>
        </div>
      </div>
    );
  }

  /* ====== 错误态 ====== */
  if (error && !portfolio) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="abyss-card p-8 text-center max-w-md">
          <span className="text-2xl">⚠</span>
          <p className="font-mono text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>{error}</p>
          <div className="mt-4 text-left space-y-2">
            <p className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
              {t('portfolio.ibGatewayHint')}
            </p>
            <ol className="font-mono text-xs space-y-1 list-decimal list-inside" style={{ color: 'var(--text-disabled)' }}>
              <li>{t('portfolio.ibGatewayStep1')}</li>
              <li>{t('portfolio.ibGatewayStep2')}</li>
              <li>{t('portfolio.ibGatewayStep3')}</li>
              <li>{t('portfolio.ibGatewayStep4')}</li>
            </ol>
          </div>
          <button
            onClick={() => fetchData()}
            className="mt-4 px-4 py-2 rounded-lg font-mono text-xs transition-colors"
            style={{ background: 'var(--accent-cyan)', color: '#000' }}
          >
            {t('common.retry')}
          </button>
        </div>
      </div>
    );
  }

  /* ====== 空数据兜底 ====== */
  const rawPortfolio = portfolio ?? {
    total_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0,
    day_change: 0, day_change_pct: 0, positions: [], position_count: 0, connected: false,
  };

  /* ====== 演示模式：券商未连接且无真实数据时，展示模拟数据 ====== */
  const demoMode = !rawPortfolio.connected && rawPortfolio.total_value === 0;
  const p: PortfolioSummary = demoMode ? {
    total_value: 125680.50,
    total_cost: 100000,
    total_pnl: 25680.50,
    total_pnl_pct: 25.68,
    day_change: 1234.56,
    day_change_pct: 0.99,
    position_count: 3,
    connected: false,
    positions: [
      { symbol: 'AAPL', name: 'Apple Inc.', quantity: 50, avg_price: 178.50, current_price: 195.20, pnl: 835.00, pnl_pct: 9.36, market_value: 9760, weight: 38.8 },
      { symbol: 'TSLA', name: 'Tesla Inc.', quantity: 20, avg_price: 245.00, current_price: 268.30, pnl: 466.00, pnl_pct: 9.51, market_value: 5366, weight: 21.3 },
      { symbol: 'NVDA', name: 'NVIDIA Corp.', quantity: 30, avg_price: 120.00, current_price: 145.80, pnl: 774.00, pnl_pct: 21.50, market_value: 4374, weight: 17.4 },
    ],
  } : rawPortfolio;

  /* ====== 概览统计数据 ====== */
  const stats = [
    { label: t('portfolio.totalAssets'), value: fmtUsd(p.total_value), color: 'var(--text-primary)' },
    { label: t('portfolio.dailyPnl'), value: `${pnlSign(p.day_change)}${fmtUsd(p.day_change)}`, color: pnlColor(p.day_change) },
    { label: t('portfolio.totalReturn'), value: `${pnlSign(p.total_pnl_pct)}${p.total_pnl_pct.toFixed(2)}%`, color: pnlColor(p.total_pnl_pct) },
    { label: t('portfolio.positionCount'), value: String(p.position_count), color: 'var(--accent-cyan)' },
  ];

  /* ====== Bot 共识统计 ====== */
  const bullCount = team.filter(m => signalCategory(m.signal) === 'bull').length;
  const bearCount = team.filter(m => signalCategory(m.signal) === 'bear').length;
  const neutralCount = team.length - bullCount - bearCount;
  const totalVotes = team.length || 1; /* 防除零 */

  /* ====== 持仓权重分布 ====== */
  const allocation = p.positions
    .filter(pos => pos.weight > 0)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 6);
  const allocationColors = [
    'var(--accent-cyan)', 'var(--accent-green)', 'var(--accent-purple)',
    'var(--accent-amber)', 'var(--accent-red)', 'var(--text-tertiary)',
  ];

  /* ====== 渲染 ====== */
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <div className="max-w-[1440px] mx-auto p-6">
        {/* ====== 标签栏 ====== */}
        <div
          className="flex gap-1 mb-6 p-1 rounded-lg overflow-x-auto"
          style={{ background: 'rgba(255,255,255,0.03)' }}
        >
          {TAB_LIST.map(tab => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="font-mono text-xs px-4 py-2 rounded-md transition-all whitespace-nowrap flex-shrink-0"
                style={{
                  background: isActive ? 'rgba(0,240,255,0.12)' : 'transparent',
                  color: isActive ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                  border: isActive ? '1px solid rgba(0,240,255,0.25)' : '1px solid transparent',
                }}
              >
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        {/* ====== Tab 1: 持仓概览 ====== */}
        {activeTab === 'overview' && (
          <motion.div
            className="grid grid-cols-12 gap-4 auto-rows-min"
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* 演示模式横幅：券商未连接时展示模拟数据预览 */}
            {demoMode && (
              <div className="col-span-12 mb-4">
                <div
                  className="abyss-card p-4 relative overflow-hidden"
                  style={{
                    background: 'linear-gradient(135deg, rgba(0,212,255,0.08), rgba(0,255,170,0.05))',
                    border: '1px solid rgba(0,212,255,0.25)',
                  }}
                >
                  {/* 右上角 DEMO 标记 */}
                  <div
                    className="absolute top-0 right-0 px-3 py-1 font-mono text-[10px] font-bold tracking-widest"
                    style={{
                      background: 'rgba(0,212,255,0.15)',
                      color: 'var(--accent-cyan)',
                      borderBottomLeftRadius: 8,
                      border: '1px solid rgba(0,212,255,0.2)',
                      borderTop: 'none',
                      borderRight: 'none',
                    }}
                  >
                    DEMO
                  </div>
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{
                        background: 'rgba(0,212,255,0.12)',
                        border: '1px solid rgba(0,212,255,0.2)',
                        fontSize: '18px',
                      }}
                    >
                      🎯
                    </div>
                    <div className="flex-1">
                      <p className="font-mono text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                        演示模式 — 以下为模拟数据
                      </p>
                      <p className="font-mono text-[11px] mt-1" style={{ color: 'var(--text-secondary)' }}>
                        IB Gateway 未连接，当前展示模拟持仓数据供预览页面效果。连接 IB Gateway 后将自动显示真实持仓。
                      </p>
                    </div>
                    <div
                      className="flex-shrink-0 px-3 py-1.5 rounded-lg font-mono text-[11px] font-bold"
                      style={{
                        background: 'rgba(255,170,0,0.1)',
                        color: 'var(--accent-amber)',
                        border: '1px solid rgba(255,170,0,0.2)',
                      }}
                    >
                      请启动 IBKR Gateway
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 总资产概览 (span-8) */}
            <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                {/* 顶部标签 + 连接状态 */}
                <div className="flex items-center justify-between">
                  <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                    {t('portfolio.portfolioOverviewLabel')}
                  </span>
                  <span
                    className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                    style={{
                      color: demoMode ? 'var(--accent-cyan)' : p.connected ? 'var(--accent-green)' : 'var(--accent-amber)',
                      background: demoMode ? 'rgba(0,212,255,0.1)' : p.connected ? 'rgba(0,255,128,0.1)' : 'rgba(255,180,0,0.1)',
                      border: `1px solid ${demoMode ? 'rgba(0,212,255,0.25)' : p.connected ? 'rgba(0,255,128,0.25)' : 'rgba(255,180,0,0.25)'}`,
                    }}
                    title={demoMode ? '当前为演示数据，连接 IB Gateway 后显示真实持仓' : p.connected ? undefined : '请确认 IB Gateway 已启动且 API 端口为 4002'}
                  >
                    {demoMode ? 'DEMO MODE' : p.connected ? t('portfolio.liveTrading') : t('portfolio.paperTrading')}
                  </span>
                </div>
                <h2 className="font-display text-[28px] font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.title")}
                </h2>

                {/* 4 列统计数据 */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
                  {stats.map(s => (
                    <div key={s.label}>
                      <span className="text-label">{s.label}</span>
                      <div className="text-metric mt-1" style={{ color: s.color }}>{s.value}</div>
                    </div>
                  ))}
                </div>

                {/* 持仓列表 */}
                <div className="mt-5 flex-1">
                  <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
                    {t('portfolio.topHoldings')}
                  </span>
                  {p.positions.length === 0 ? (
                    <div className="mt-8 text-center">
                      <p className="font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                        {t("portfolio.noPositions")}
                      </p>
                    </div>
                  ) : (
                    <div className="mt-2 space-y-1">
                      {p.positions.map(h => (
                        <div
                          key={h.symbol}
                          className="flex items-center gap-3 py-2 px-3 rounded-lg cursor-pointer transition-colors"
                          style={{ background: 'rgba(255,255,255,0.02)' }}
                          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
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
                            {h.quantity}
                          </span>
                          {/* 现价 */}
                          <span className="font-mono text-xs w-20 text-right" style={{ color: 'var(--text-secondary)' }}>
                            ${h.current_price.toLocaleString()}
                          </span>
                          {/* 盈亏额 */}
                          <span className="font-mono text-xs w-20 text-right" style={{ color: pnlColor(h.pnl) }}>
                            {pnlSign(h.pnl)}{fmtUsd(h.pnl)}
                          </span>
                          {/* 盈亏率 */}
                          <span className="font-mono text-xs w-16 text-right font-semibold" style={{ color: pnlColor(h.pnl_pct) }}>
                            {pnlSign(h.pnl_pct)}{h.pnl_pct.toFixed(1)}%
                          </span>
                          {/* 卖出按钮（演示模式下禁用） */}
                          <button
                            disabled={demoMode || sellingSymbol === h.symbol}
                            onClick={e => { e.stopPropagation(); handleSell(h.symbol, h.quantity); }}
                            className="font-mono text-[10px] px-2 py-1 rounded transition-colors flex-shrink-0"
                            style={{
                              color: demoMode || sellingSymbol === h.symbol ? 'var(--text-disabled)' : 'var(--accent-red)',
                              background: demoMode || sellingSymbol === h.symbol ? 'rgba(255,255,255,0.03)' : 'rgba(255,60,60,0.1)',
                              border: '1px solid rgba(255,60,60,0.2)',
                              cursor: demoMode || sellingSymbol === h.symbol ? 'not-allowed' : 'pointer',
                            }}
                            title={demoMode ? '演示模式下不可操作' : undefined}
                          >
                            {sellingSymbol === h.symbol ? '...' : demoMode ? 'DEMO' : t('portfolio.sell')}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>

            {/* 7-Bot AI 团队共识 (span-4) */}
            <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  {t('portfolio.botConsensusLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.aiTeam")}
                </h3>

                {team.length === 0 ? (
                  <div className="mt-6 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.noTeamData")}
                    </p>
                  </div>
                ) : (
                  <>
                    {/* 共识进度条 */}
                    <div className="flex h-3 rounded-full overflow-hidden mt-4" style={{ background: 'rgba(255,255,255,0.06)' }}>
                      <div className="h-full transition-all" style={{ width: `${(bullCount / totalVotes) * 100}%`, background: 'var(--accent-green)' }} />
                      <div className="h-full transition-all" style={{ width: `${(neutralCount / totalVotes) * 100}%`, background: 'var(--accent-amber)' }} />
                      <div className="h-full transition-all" style={{ width: `${(bearCount / totalVotes) * 100}%`, background: 'var(--accent-red)' }} />
                    </div>

                    {/* 团队成员列表 */}
                    <div className="mt-4 space-y-2 flex-1">
                      {team.map(m => (
                        <div key={m.analyst} className="flex items-center justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                              {m.analyst}
                            </span>
                            {m.reasoning && (
                              <p className="font-mono text-[10px] truncate mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                                {m.reasoning}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                              {Math.round(m.confidence * 100)}%
                            </span>
                            <span
                              className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full whitespace-nowrap"
                              style={{ color: signalColor(m.signal), background: `${signalColor(m.signal)}15` }}
                            >
                              {signalLabel(m.signal, t)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* 统计汇总 */}
                    <div className="flex gap-4 mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                      <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-green)' }} />
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{bullCount} {t('portfolio.bullish')}</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-amber)' }} />
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{neutralCount} {t('portfolio.neutral')}</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-red)' }} />
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{bearCount} {t('portfolio.bearish')}</span>
                      </span>
                    </div>
                  </>
                )}
              </div>
            </motion.div>

            {/* 持仓分布卡片 (span-4) */}
            <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  {t('portfolio.allocationLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.allocation")}
                </h3>
                {allocation.length === 0 ? (
                  <div className="mt-6 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>{t('common.noData')}</p>
                  </div>
                ) : (
                  <div className="mt-4 space-y-3 flex-1">
                    {allocation.map((pos, i) => (
                      <div key={pos.symbol}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                            {pos.symbol} · {pos.name}
                          </span>
                          <span className="font-mono text-xs font-semibold" style={{ color: allocationColors[i % allocationColors.length] }}>
                            {pos.weight.toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${Math.min(pos.weight, 100)}%`, background: allocationColors[i % allocationColors.length], opacity: 0.8 }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>

            {/* 总收益汇总卡片 (span-8) */}
            <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
              <div className="abyss-card p-6 h-full">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                      {t('portfolio.performanceSummaryLabel')}
                    </span>
                    <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                      {t("portfolio.performanceSummary")}
                    </h3>
                  </div>
                  <div className="text-right">
                    <span className="text-label">{t('portfolio.totalPnl')}</span>
                    <div className="text-metric mt-1" style={{ color: pnlColor(p.total_pnl) }}>
                      {pnlSign(p.total_pnl)}{fmtUsd(p.total_pnl)}
                    </div>
                  </div>
                </div>

                {/* 明细卡片网格 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                  {[
                    { label: t('portfolio.totalCost'), value: fmtUsd(p.total_cost), color: 'var(--text-secondary)' },
                    { label: t('portfolio.totalValue'), value: fmtUsd(p.total_value), color: 'var(--accent-cyan)' },
                    { label: t('portfolio.dayChange'), value: `${pnlSign(p.day_change_pct)}${p.day_change_pct.toFixed(2)}%`, color: pnlColor(p.day_change_pct) },
                    { label: t('portfolio.totalReturn'), value: `${pnlSign(p.total_pnl_pct)}${p.total_pnl_pct.toFixed(2)}%`, color: pnlColor(p.total_pnl_pct) },
                  ].map(item => (
                    <div
                      key={item.label}
                      className="p-3 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.03)' }}
                    >
                      <span className="font-mono text-[10px] uppercase" style={{ color: 'var(--text-disabled)' }}>
                        {item.label}
                      </span>
                      <div className="font-mono text-lg font-bold mt-1" style={{ color: item.color }}>
                        {item.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* 风险指标卡片 (span-4) */}
            <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                  {t('portfolio.riskMetricsLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.riskMetrics")}
                </h3>
                <div className="mt-4 space-y-4 flex-1">
                  {[
                    { label: t('portfolio.costBasis'), value: fmtUsd(p.total_cost), color: 'var(--text-secondary)' },
                    { label: t('portfolio.unrealizedPnl'), value: `${pnlSign(p.total_pnl)}${fmtUsd(p.total_pnl)}`, color: pnlColor(p.total_pnl) },
                    { label: t('portfolio.dayVolatility'), value: `${pnlSign(p.day_change_pct)}${p.day_change_pct.toFixed(2)}%`, color: pnlColor(p.day_change_pct) },
                    { label: t('portfolio.concentration'), value: p.positions.length > 0 ? `${p.positions[0]?.weight.toFixed(1)}% max` : 'N/A', color: 'var(--accent-cyan)' },
                  ].map(m => (
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
            </motion.div>
          </motion.div>
        )}

        {/* ====== Tab 2: 交易决策 ====== */}
        {activeTab === 'decision' && (
          <motion.div
            className="grid grid-cols-12 gap-4 auto-rows-min"
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* 发起投票表单 */}
            <motion.div className="col-span-12 lg:col-span-5" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  {t('portfolio.aiVoteTrigger')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.startVote")}
                </h3>
                <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
                  {t("portfolio.voteDesc")}
                </p>

                <div className="mt-6 space-y-4 flex-1">
                  {/* 股票代码输入 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.symbolLabel")}
                    </label>
                    <input
                      type="text"
                      placeholder={t('portfolio.symbolPlaceholder')}
                      value={voteSymbol}
                      onChange={e => setVoteSymbol(e.target.value)}
                      className="w-full font-mono text-sm"
                      style={inputStyle}
                    />
                  </div>

                  {/* 时间周期选择 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.analysisPeriod")}
                    </label>
                    <div className="flex gap-2">
                      {['1d', '1w', '1m', '3m'].map(pd => (
                        <button
                          key={pd}
                          onClick={() => setVotePeriod(pd)}
                          className="font-mono text-xs px-3 py-1.5 rounded-md transition-all"
                          style={{
                            background: votePeriod === pd ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.04)',
                            color: votePeriod === pd ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                            border: votePeriod === pd ? '1px solid rgba(0,240,255,0.25)' : '1px solid rgba(255,255,255,0.08)',
                          }}
                        >
                          {pd}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 分析按钮 */}
                  <button
                    disabled={voteLoading}
                    onClick={handleVote}
                    className="w-full font-mono text-sm font-semibold py-2.5 rounded-lg transition-all mt-auto"
                    style={actionBtnStyle(voteLoading)}
                  >
                    {voteLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="inline-block w-4 h-4 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--text-disabled)', borderTopColor: 'transparent' }} />
                        {t("portfolio.analyzing")}
                      </span>
                    ) : t('portfolio.analyze')}
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 投票结果展示 */}
            <motion.div className="col-span-12 lg:col-span-7" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  {t('portfolio.voteResultsLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.voteResults")}
                </h3>

                {!voteResult ? (
                  <div className="mt-8 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {voteLoading ? t('portfolio.voteWaiting') : t('portfolio.votePrompt')}
                    </p>
                  </div>
                ) : (
                  <div className="mt-4 flex-1 space-y-3">
                    {/* 共识结论 */}
                    {(voteResult.consensus || voteResult.summary) && (
                      <div className="p-3 rounded-lg" style={{ background: 'rgba(0,240,255,0.06)', border: '1px solid rgba(0,240,255,0.15)' }}>
                        <span className="font-mono text-[10px] uppercase" style={{ color: 'var(--accent-cyan)' }}>{t('portfolio.consensus')}</span>
                        <p className="font-mono text-sm mt-1" style={{ color: 'var(--text-primary)' }}>
                          {voteResult.consensus || voteResult.summary}
                        </p>
                      </div>
                    )}

                    {/* 各 Bot 投票详情 */}
                    <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 400 }}>
                      {(voteResult.votes || voteResult.team || []).map((v, i) => {
                        const name = v.bot_name || v.analyst || `Bot ${i + 1}`;
                        const sig = v.signal || v.vote || t('portfolio.unknown');
                        const conf = v.confidence ?? 0;
                        const reason = v.reasoning || v.reason || '';
                        return (
                          <div
                            key={name}
                            className="p-3 rounded-lg"
                            style={{ background: 'rgba(255,255,255,0.03)' }}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                                {name}
                              </span>
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                                  {Math.round(conf * 100)}%
                                </span>
                                <span
                                  className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                                  style={{ color: signalColor(sig), background: `${signalColor(sig)}15` }}
                                >
                                  {signalLabel(sig, t)}
                                </span>
                              </div>
                            </div>
                            {reason && (
                              <p className="font-mono text-[11px] mt-1.5 leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                                {reason}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}

        {/* ====== Tab 3: 自动交易 ====== */}
        {activeTab === 'auto' && (
          <motion.div
            className="grid grid-cols-12 gap-4 auto-rows-min"
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
              <div className="abyss-card p-6">
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  {t('portfolio.tradingControlsLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.autoTradeControl")}
                </h3>
                <p className="font-mono text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  {t("portfolio.autoTradeDesc")}
                </p>

                {controlsLoading && !controls ? (
                  <div className="mt-8 flex items-center justify-center py-12">
                    <div className="inline-block w-6 h-6 border-2 border-t-transparent rounded-full animate-spin"
                         style={{ borderColor: 'var(--accent-cyan)', borderTopColor: 'transparent' }} />
                  </div>
                ) : !controls ? (
                  <div className="mt-8 text-center py-12">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.controls.loadFailed")}
                    </p>
                    <button
                      onClick={fetchControls}
                      className="mt-3 px-4 py-1.5 rounded-lg font-mono text-xs"
                      style={{ background: 'var(--accent-cyan)', color: '#000' }}
                    >
                      {t("common.retry")}
                    </button>
                  </div>
                ) : (
                  <div className="mt-6 space-y-1">
                    {/* 布尔开关列表 */}
                    {([
                      { key: 'auto_trader_enabled' as const, label: t('portfolio.controls.autoTrader'), desc: t('portfolio.controls.autoTraderDesc') },
                      { key: 'ibkr_live_mode' as const, label: t('portfolio.controls.liveMode'), desc: t('portfolio.controls.liveModeDesc') },
                      { key: 'risk_protection_enabled' as const, label: t('portfolio.controls.riskProtection'), desc: t('portfolio.controls.riskProtectionDesc') },
                      { key: 'allow_short_selling' as const, label: t('portfolio.controls.allowShort'), desc: t('portfolio.controls.allowShortDesc') },
                    ]).map(item => {
                      const isToggling = togglingKey === item.key;
                      const checked = controls[item.key] as boolean;
                      return (
                        <div
                          key={item.key}
                          className="flex items-center justify-between py-4 px-4 rounded-lg transition-colors"
                          style={{ background: 'rgba(255,255,255,0.02)' }}
                        >
                          <div className="flex-1 min-w-0 mr-4">
                            <span className="font-mono text-sm font-semibold block" style={{ color: 'var(--text-primary)' }}>
                              {item.label}
                            </span>
                            <span className="font-mono text-[11px] block mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                              {item.desc}
                            </span>
                          </div>
                          <button
                            disabled={isToggling}
                            onClick={() => updateControl(item.key, !checked)}
                            className="relative w-11 h-6 rounded-full transition-all flex-shrink-0"
                            style={{
                              background: checked ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.1)',
                              opacity: isToggling ? 0.5 : 1,
                              cursor: isToggling ? 'not-allowed' : 'pointer',
                            }}
                          >
                            <span
                              className="absolute top-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                              style={{
                                left: 2,
                                transform: checked ? 'translateX(20px)' : 'translateX(0)',
                              }}
                            />
                          </button>
                        </div>
                      );
                    })}

                    {/* 最大日交易次数（数值输入） */}
                    <div
                      className="flex items-center justify-between py-4 px-4 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.02)' }}
                    >
                      <div className="flex-1 min-w-0 mr-4">
                        <span className="font-mono text-sm font-semibold block" style={{ color: 'var(--text-primary)' }}>
                          {t("portfolio.controls.maxDailyTrades")}
                        </span>
                        <span className="font-mono text-[11px] block mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                          {t("portfolio.controls.maxDailyTradesDesc")}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={controls.max_daily_trades}
                          disabled={togglingKey === 'max_daily_trades'}
                          onChange={e => {
                            const v = parseInt(e.target.value, 10);
                            if (!isNaN(v) && v >= 0) {
                              setControls(prev => prev ? { ...prev, max_daily_trades: v } : prev);
                            }
                          }}
                          onBlur={e => {
                            const v = parseInt(e.target.value, 10);
                            if (!isNaN(v) && v >= 0) {
                              updateControl('max_daily_trades', v);
                            }
                          }}
                          className="w-20 font-mono text-sm text-center"
                          style={{
                            ...inputStyle,
                            opacity: togglingKey === 'max_daily_trades' ? 0.5 : 1,
                          }}
                        />
                        <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>{t('portfolio.controls.perDay')}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>

            {/* 右侧状态提示卡片 */}
            <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                  {t('portfolio.statusLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.statusInfo")}
                </h3>
                <div className="mt-4 space-y-3 flex-1">
                  <div className="p-3 rounded-lg" style={{ background: 'rgba(255,180,0,0.06)', border: '1px solid rgba(255,180,0,0.15)' }}>
                    <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      {t('portfolio.tips.autoTrade')}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg" style={{ background: 'rgba(255,60,60,0.06)', border: '1px solid rgba(255,60,60,0.15)' }}>
                    <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      {t('portfolio.tips.liveMode')}
                    </p>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}

        {/* ====== Tab 4: 回测分析 ====== */}
        {activeTab === 'backtest' && (
          <motion.div
            className="grid grid-cols-12 gap-4 auto-rows-min"
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* 回测表单 */}
            <motion.div className="col-span-12 lg:col-span-5" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  {t('portfolio.backtestConfigLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.backtestParams")}
                </h3>

                <div className="mt-6 space-y-4 flex-1">
                  {/* 股票代码 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.symbolLabel")}
                    </label>
                    <input
                      type="text"
                      placeholder={t('portfolio.symbolPlaceholder')}
                      value={btSymbol}
                      onChange={e => setBtSymbol(e.target.value)}
                      className="w-full font-mono text-sm"
                      style={inputStyle}
                    />
                  </div>

                  {/* 策略选择 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.tradeStrategy")}
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {([
                        { id: 'ma_cross', label: t('portfolio.strategy.maCross') },
                        { id: 'rsi', label: t('portfolio.strategy.rsi') },
                        { id: 'macd', label: 'MACD' },
                        { id: 'bbands', label: t('portfolio.strategy.bbands') },
                        { id: 'volume', label: t('portfolio.strategy.volume') },
                      ] as const).map(s => (
                        <button
                          key={s.id}
                          onClick={() => setBtStrategy(s.id)}
                          className="font-mono text-xs px-3 py-2 rounded-md transition-all text-left"
                          style={{
                            background: btStrategy === s.id ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.04)',
                            color: btStrategy === s.id ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                            border: btStrategy === s.id ? '1px solid rgba(0,240,255,0.25)' : '1px solid rgba(255,255,255,0.08)',
                          }}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 回测周期 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      {t("portfolio.backtestPeriod")}
                    </label>
                    <div className="flex gap-2">
                      {['3m', '6m', '1y', '2y', '5y'].map(pd => (
                        <button
                          key={pd}
                          onClick={() => setBtPeriod(pd)}
                          className="font-mono text-xs px-3 py-1.5 rounded-md transition-all"
                          style={{
                            background: btPeriod === pd ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.04)',
                            color: btPeriod === pd ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                            border: btPeriod === pd ? '1px solid rgba(0,240,255,0.25)' : '1px solid rgba(255,255,255,0.08)',
                          }}
                        >
                          {pd}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 开始回测 */}
                  <button
                    disabled={btLoading}
                    onClick={handleBacktest}
                    className="w-full font-mono text-sm font-semibold py-2.5 rounded-lg transition-all mt-auto"
                    style={actionBtnStyle(btLoading)}
                  >
                    {btLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="inline-block w-4 h-4 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--text-disabled)', borderTopColor: 'transparent' }} />
                        {t("portfolio.backtesting")}
                      </span>
                    ) : t('portfolio.startBacktest')}
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 回测结果 */}
            <motion.div className="col-span-12 lg:col-span-7" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  {t('portfolio.backtestResultsLabel')}
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  {t("portfolio.backtestResults")}
                </h3>

                {!btResult ? (
                  <div className="mt-8 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {btLoading ? t('portfolio.backtestRunning') : t('portfolio.backtestPrompt')}
                    </p>
                  </div>
                ) : (
                  <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-4">
                    {([
                      { label: t('portfolio.totalReturn'), value: fmtPct(btResult.total_return), color: pnlColor(btResult.total_return ?? 0) },
                      { label: t('portfolio.annualReturn'), value: fmtPct(btResult.annual_return), color: pnlColor(btResult.annual_return ?? 0) },
                      { label: t('portfolio.maxDrawdown'), value: fmtPct(btResult.max_drawdown), color: 'var(--accent-red)' },
                      { label: t('portfolio.sharpeRatio'), value: btResult.sharpe_ratio?.toFixed(2) ?? 'N/A', color: 'var(--accent-cyan)' },
                      { label: t('portfolio.winRate'), value: fmtPct(btResult.win_rate), color: 'var(--accent-green)' },
                      { label: t('portfolio.totalTrades'), value: btResult.total_trades?.toString() ?? 'N/A', color: 'var(--text-primary)' },
                    ]).map(item => (
                      <div
                        key={item.label}
                        className="p-4 rounded-lg"
                        style={{ background: 'rgba(255,255,255,0.03)' }}
                      >
                        <span className="font-mono text-[10px] uppercase block" style={{ color: 'var(--text-disabled)' }}>
                          {item.label}
                        </span>
                        <div className="font-mono text-xl font-bold mt-2" style={{ color: item.color }}>
                          {item.value}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}

        {/* ====== Tab 5: 估值分析 ====== */}
        {activeTab === 'valuation' && (
          <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-4">
            {/* 输入区 */}
            <motion.div variants={cardVariants}>
              <div className="abyss-card p-6">
                <span className="text-label" style={{ color: 'var(--accent-purple)' }}>{t('portfolio.valuationAnalysisLabel')}</span>
                <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>{t('portfolio.valuationAnalysis')}</h3>
                <div className="flex items-center gap-3">
                  <input
                    className="flex-1 font-mono text-sm rounded-lg px-4 py-2"
                    style={inputStyle}
                    placeholder={t('portfolio.valuation.placeholder')}
                    value={valSymbol}
                    onChange={(e) => setValSymbol(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === 'Enter' && handleValuation()}
                  />
                  <button
                    className="px-5 py-2 rounded-lg font-display text-sm font-bold transition-all"
                    style={actionBtnStyle(valLoading, 'var(--accent-purple)')}
                    disabled={valLoading}
                    onClick={handleValuation}
                  >
                    {valLoading ? t('portfolio.analyzing') : t('portfolio.startValuation')}
                  </button>
                </div>
                <p className="font-mono text-[10px] mt-2" style={{ color: 'var(--text-disabled)' }}>
                  {t("portfolio.valuation.modelsDesc")}
                </p>
              </div>
            </motion.div>

            {/* 结果区 */}
            {valResult && (
              <motion.div variants={cardVariants}>
                <div className="abyss-card p-6">
                  {/* 标题行：公司名 + 综合信号 */}
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <h3 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                        {valResult.company_name}
                        <span className="ml-2 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>{valResult.symbol}</span>
                      </h3>
                      <p className="font-mono text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
                        {t("portfolio.valuation.currentPrice")}: ${valResult.current_price?.toFixed(2)} · WACC: {(valResult.wacc * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="px-3 py-1 rounded-lg font-mono text-sm font-bold"
                            style={{
                              background: valResult.signal === 'bullish' ? 'rgba(0,255,136,0.15)' : valResult.signal === 'bearish' ? 'rgba(255,68,68,0.15)' : 'rgba(255,170,0,0.15)',
                              color: valResult.signal === 'bullish' ? 'var(--accent-green)' : valResult.signal === 'bearish' ? 'var(--accent-red)' : 'var(--accent-amber)',
                            }}>
                        {valResult.signal === 'bullish' ? t('portfolio.bullish') : valResult.signal === 'bearish' ? t('portfolio.bearish') : valResult.signal === 'neutral' ? t('portfolio.neutral') : valResult.signal}
                      </span>
                      <p className="font-mono text-xs mt-1" style={{ color: 'var(--text-disabled)' }}>
                        {t("portfolio.valuation.confidence")}: {(valResult.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                  </div>

                  {/* 四大模型结果 */}
                  <div className="grid grid-cols-2 gap-3">
                    {/* DCF */}
                    <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <p className="text-label mb-2" style={{ color: 'var(--accent-cyan)' }}>{t('portfolio.valuation.dcf')}</p>
                      <div className="space-y-1 font-mono text-xs">
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.bullCase')}</span>
                          <span style={{ color: 'var(--accent-green)' }}>${valResult.dcf?.bull_value?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.baseCase')}</span>
                          <span style={{ color: 'var(--text-primary)' }}>${valResult.dcf?.base_value?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.bearCase')}</span>
                          <span style={{ color: 'var(--accent-red)' }}>${valResult.dcf?.bear_value?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between pt-1 mt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.weighted')}</span>
                          <span className="font-bold" style={{ color: 'var(--accent-cyan)' }}>${valResult.dcf?.weighted_value?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.marginOfSafety')}</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{((valResult.dcf?.margin_of_safety ?? 0) * 100).toFixed(1)}%</span>
                        </div>
                      </div>
                    </div>

                    {/* EV/EBITDA */}
                    <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <p className="text-label mb-2" style={{ color: 'var(--accent-amber)' }}>{t('portfolio.valuation.evEbitda')}</p>
                      <div className="space-y-1 font-mono text-xs">
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.currentMultiple')}</span>
                          <span style={{ color: 'var(--text-primary)' }}>{valResult.ev_ebitda?.current_multiple?.toFixed(1)}x</span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.impliedValue')}</span>
                          <span style={{ color: 'var(--accent-amber)' }}>${valResult.ev_ebitda?.implied_value?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.upside')}</span>
                          <span style={{ color: (valResult.ev_ebitda?.upside_percent ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {(valResult.ev_ebitda?.upside_percent ?? 0) >= 0 ? '+' : ''}{valResult.ev_ebitda?.upside_percent?.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* 持有人收益 */}
                    <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <p className="text-label mb-2" style={{ color: 'var(--accent-green)' }}>{t('portfolio.valuation.ownerEarnings')}</p>
                      <div className="font-mono text-xs">
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.ownerEarningsValue')}</span>
                          <span className="font-bold" style={{ color: valResult.owner_earnings > 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            ${(valResult.owner_earnings / 1e9).toFixed(2)}B
                          </span>
                        </div>
                        <p className="mt-2 text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {t("portfolio.valuation.ownerEarningsFormula")}
                        </p>
                      </div>
                    </div>

                    {/* 残余收入 */}
                    <div className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <p className="text-label mb-2" style={{ color: 'var(--accent-purple)' }}>{t('portfolio.valuation.residualIncome')}</p>
                      <div className="font-mono text-xs">
                        <div className="flex justify-between">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.intrinsicValue')}</span>
                          <span className="font-bold" style={{ color: 'var(--accent-purple)' }}>
                            ${valResult.residual_income?.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex justify-between mt-1">
                          <span style={{ color: 'var(--text-disabled)' }}>{t('portfolio.valuation.vsCurrentPrice')}</span>
                          <span style={{ color: valResult.residual_income > valResult.current_price ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {valResult.current_price > 0 ? `${((valResult.residual_income / valResult.current_price - 1) * 100).toFixed(1)}%` : '—'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.div>
        )}

        {/* ====== Tab 6: 交易日志 ====== */}
        {activeTab === 'logs' && (
          <motion.div variants={containerVariants} initial="hidden" animate="visible">
            <motion.div variants={cardVariants}>
              <div className="abyss-card p-6">
                {/* 标题 + 筛选 */}
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                      {t('portfolio.tradeLogsLabel')}
                    </span>
                    <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                      {t("portfolio.tradeLogs")}
                      <span className="ml-2 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                        {journalTotal} {t('portfolio.logs.entries')}
                      </span>
                    </h3>
                  </div>
                  <div className="flex items-center gap-2">
                    {(['all', 'open', 'closed'] as const).map((f) => (
                      <button
                        key={f}
                        className="px-3 py-1 rounded-lg font-mono text-xs transition-colors"
                        style={{
                          background: journalFilter === f ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.04)',
                          color: journalFilter === f ? '#000' : 'var(--text-secondary)',
                          border: '1px solid ' + (journalFilter === f ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.08)'),
                        }}
                        onClick={() => { setJournalFilter(f); fetchJournal(0, f); }}
                      >
                        {f === 'all' ? t('portfolio.logs.all') : f === 'open' ? t('portfolio.logs.open') : t('portfolio.logs.closed')}
                      </button>
                    ))}
                    <button
                      className="px-3 py-1 rounded-lg font-mono text-xs"
                      style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)', border: '1px solid rgba(255,255,255,0.08)' }}
                      onClick={() => fetchJournal(journalPage)}
                    >
                      {t("common.refresh")}
                    </button>
                  </div>
                </div>

                {/* 表格 */}
                {journalLoading ? (
                  <div className="flex items-center justify-center py-16">
                    <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin"
                         style={{ borderColor: 'var(--accent-cyan)', borderTopColor: 'transparent' }} />
                    <span className="ml-3 font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{t('common.loading')}</span>
                  </div>
                ) : journalItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16">
                    <span className="text-2xl mb-2" style={{ opacity: 0.3 }}>📋</span>
                    <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{t('portfolio.logs.noRecords')}</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full font-mono text-xs" style={{ borderCollapse: 'separate', borderSpacing: '0 4px' }}>
                      <thead>
                        <tr style={{ color: 'var(--text-disabled)' }}>
                          <th className="text-left px-3 py-2">{t('portfolio.logs.symbol')}</th>
                          <th className="text-left px-3 py-2">{t('portfolio.logs.direction')}</th>
                          <th className="text-right px-3 py-2">{t('portfolio.logs.quantity')}</th>
                          <th className="text-right px-3 py-2">{t('portfolio.logs.entryPrice')}</th>
                          <th className="text-right px-3 py-2">{t('portfolio.logs.exitPrice')}</th>
                          <th className="text-right px-3 py-2">{t('portfolio.logs.pnl')}</th>
                          <th className="text-right px-3 py-2">{t('portfolio.logs.pnlPct')}</th>
                          <th className="text-center px-3 py-2">{t('portfolio.logs.status')}</th>
                          <th className="text-left px-3 py-2">{t('portfolio.logs.entryTime')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {journalItems.map((t) => (
                          <tr key={t.id} className="hover:brightness-125 transition-all"
                              style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                            <td className="px-3 py-2 font-bold" style={{ color: 'var(--text-primary)' }}>{t.symbol}</td>
                            <td className="px-3 py-2">
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold"
                                    style={{
                                      background: t.side === 'BUY' ? 'rgba(0,255,136,0.12)' : 'rgba(255,68,68,0.12)',
                                      color: t.side === 'BUY' ? 'var(--accent-green)' : 'var(--accent-red)',
                                    }}>
                                {t.side === 'BUY' ? 'BUY' : 'SELL'}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-right" style={{ color: 'var(--text-secondary)' }}>{t.quantity}</td>
                            <td className="px-3 py-2 text-right" style={{ color: 'var(--text-primary)' }}>
                              ${t.entry_price?.toFixed(2) ?? '—'}
                            </td>
                            <td className="px-3 py-2 text-right" style={{ color: 'var(--text-primary)' }}>
                              {t.exit_price ? `$${t.exit_price.toFixed(2)}` : '—'}
                            </td>
                            <td className="px-3 py-2 text-right font-bold"
                                style={{ color: t.pnl != null ? pnlColor(t.pnl) : 'var(--text-disabled)' }}>
                              {t.pnl != null ? `${pnlSign(t.pnl)}${fmtUsd(t.pnl)}` : '—'}
                            </td>
                            <td className="px-3 py-2 text-right"
                                style={{ color: t.pnl_pct != null ? pnlColor(t.pnl_pct) : 'var(--text-disabled)' }}>
                              {t.pnl_pct != null ? `${pnlSign(t.pnl_pct)}${(t.pnl_pct * 100).toFixed(2)}%` : '—'}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <span className="px-2 py-0.5 rounded text-[10px]"
                                    style={{
                                      background: t.status === 'open' ? 'rgba(0,255,136,0.1)' : t.status === 'closed' ? 'rgba(255,255,255,0.06)' : 'rgba(255,170,0,0.1)',
                                      color: t.status === 'open' ? 'var(--accent-green)' : t.status === 'closed' ? 'var(--text-secondary)' : 'var(--accent-amber)',
                                    }}>
                                {t.status === 'open' ? 'OPEN' : t.status === 'closed' ? 'CLOSED' : t.status === 'pending' ? 'PENDING' : t.status}
                              </span>
                            </td>
                            <td className="px-3 py-2" style={{ color: 'var(--text-disabled)' }}>
                              {t.entry_time ? new Date(t.entry_time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* 分页 */}
                {journalTotal > JOURNAL_PAGE_SIZE && (
                  <div className="flex items-center justify-between mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {journalPage + 1} / {Math.ceil(journalTotal / JOURNAL_PAGE_SIZE)}
                    </span>
                    <div className="flex gap-2">
                      <button
                        className="px-3 py-1 rounded font-mono text-xs"
                        style={{ background: 'rgba(255,255,255,0.04)', color: journalPage === 0 ? 'var(--text-disabled)' : 'var(--text-secondary)', border: '1px solid rgba(255,255,255,0.08)', cursor: journalPage === 0 ? 'not-allowed' : 'pointer' }}
                        disabled={journalPage === 0}
                        onClick={() => fetchJournal(journalPage - 1)}
                      >
                        {t("portfolio.logs.prevPage")}
                      </button>
                      <button
                        className="px-3 py-1 rounded font-mono text-xs"
                        style={{ background: 'rgba(255,255,255,0.04)', color: (journalPage + 1) * JOURNAL_PAGE_SIZE >= journalTotal ? 'var(--text-disabled)' : 'var(--text-secondary)', border: '1px solid rgba(255,255,255,0.08)', cursor: (journalPage + 1) * JOURNAL_PAGE_SIZE >= journalTotal ? 'not-allowed' : 'pointer' }}
                        disabled={(journalPage + 1) * JOURNAL_PAGE_SIZE >= journalTotal}
                        onClick={() => fetchJournal(journalPage + 1)}
                      >
                        {t("portfolio.logs.nextPage")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

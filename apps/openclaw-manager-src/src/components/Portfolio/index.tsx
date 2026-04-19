/**
 * Portfolio — 投资组合页面 (Sonic Abyss Bento Grid 风格)
 * 5 个标签页：持仓概览 / 交易决策 / 自动交易 / 回测分析 / 交易日志
 * 数据来自后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { api } from '../../lib/api';
import { clawbotFetch, clawbotFetchJson, LONG_TIMEOUT_MS } from '../../lib/tauri-core';

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

/* ====== 标签页 ID ====== */
type TabId = 'overview' | 'decision' | 'auto' | 'backtest' | 'logs';

const TAB_LIST: { id: TabId; label: string }[] = [
  { id: 'overview', label: '持仓概览' },
  { id: 'decision', label: '交易决策' },
  { id: 'auto',     label: '自动交易' },
  { id: 'backtest', label: '回测分析' },
  { id: 'logs',     label: '交易日志' },
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
  if (value === undefined || value === null) return 'N/A';
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
function signalLabel(signal: string): string {
  const s = signal.toLowerCase();
  if (s.includes('strong') && isBull(signal)) return '强烈看多';
  if (isBull(signal)) return '看多';
  if (s.includes('strong') && isBear(signal)) return '强烈看空';
  if (isBear(signal)) return '看空';
  if (s.includes('neutral') || s.includes('hold') || s === '中性') return '中性';
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
        if (!silent) setError('无法获取持仓数据');
      }

      if (tRes.status === 'fulfilled' && tRes.value) {
        const data = tRes.value as unknown as TeamResponse;
        setTeam(Array.isArray(data.team) ? data.team : []);
      }
    } catch (e) {
      console.error('[Portfolio] 数据拉取异常:', e);
      if (!silent) setError('网络异常，请检查后端是否运行');
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
      toast.success(`${symbol} 卖出成功`, { description: `数量: ${quantity}` });
      /* 刷新数据 */
      fetchData(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      toast.error(`${symbol} 卖出失败`, { description: msg });
      console.error(`[Portfolio] 卖出失败: ${symbol}`, msg);
    } finally {
      setSellingSymbol(null);
    }
  };

  /* ====== 交易决策：触发投票 ====== */
  const handleVote = async () => {
    const sym = voteSymbol.trim().toUpperCase();
    if (!sym) {
      toast.error('请输入股票代码');
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
        throw new Error(`HTTP ${resp.status}: ${text || '请求失败'}`);
      }
      const data: VoteResult = await resp.json();
      setVoteResult(data);
      toast.success('投票分析完成', { description: `${sym} · ${votePeriod}` });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      toast.error('投票分析失败', { description: msg });
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
      toast.error('拉取交易控制配置失败');
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
      toast.success('设置已更新');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      toast.error('更新失败', { description: msg });
    } finally {
      setTogglingKey(null);
    }
  };

  /* ====== 回测分析：触发回测 ====== */
  const handleBacktest = async () => {
    const sym = btSymbol.trim().toUpperCase();
    if (!sym) {
      toast.error('请输入股票代码');
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
      toast.success('回测完成', { description: `${sym} · ${btStrategy}` });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      toast.error('回测失败', { description: msg });
    } finally {
      setBtLoading(false);
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
            正在加载持仓数据...
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
          <button
            onClick={() => fetchData()}
            className="mt-4 px-4 py-2 rounded-lg font-mono text-xs transition-colors"
            style={{ background: 'var(--accent-cyan)', color: '#000' }}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  /* ====== 空数据兜底 ====== */
  const p = portfolio ?? {
    total_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0,
    day_change: 0, day_change_pct: 0, positions: [], position_count: 0, connected: false,
  };

  /* ====== 概览统计数据 ====== */
  const stats = [
    { label: '总资产', value: fmtUsd(p.total_value), color: 'var(--text-primary)' },
    { label: '今日盈亏', value: `${pnlSign(p.day_change)}${fmtUsd(p.day_change)}`, color: pnlColor(p.day_change) },
    { label: '总收益率', value: `${pnlSign(p.total_pnl_pct)}${p.total_pnl_pct.toFixed(2)}%`, color: pnlColor(p.total_pnl_pct) },
    { label: '持仓数量', value: String(p.position_count), color: 'var(--accent-cyan)' },
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
                {tab.label}
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
            {/* 总资产概览 (span-8) */}
            <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                {/* 顶部标签 + 连接状态 */}
                <div className="flex items-center justify-between">
                  <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                    PORTFOLIO // OVERVIEW
                  </span>
                  <span
                    className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                    style={{
                      color: p.connected ? 'var(--accent-green)' : 'var(--accent-amber)',
                      background: p.connected ? 'rgba(0,255,128,0.1)' : 'rgba(255,180,0,0.1)',
                      border: `1px solid ${p.connected ? 'rgba(0,255,128,0.25)' : 'rgba(255,180,0,0.25)'}`,
                    }}
                  >
                    {p.connected ? '● 实盘 (IBKR)' : '● 模拟盘'}
                  </span>
                </div>
                <h2 className="font-display text-[28px] font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  投资组合
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
                    TOP HOLDINGS
                  </span>
                  {p.positions.length === 0 ? (
                    <div className="mt-8 text-center">
                      <p className="font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                        暂无持仓
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
                          {/* 卖出按钮 */}
                          <button
                            disabled={sellingSymbol === h.symbol}
                            onClick={e => { e.stopPropagation(); handleSell(h.symbol, h.quantity); }}
                            className="font-mono text-[10px] px-2 py-1 rounded transition-colors flex-shrink-0"
                            style={{
                              color: sellingSymbol === h.symbol ? 'var(--text-disabled)' : 'var(--accent-red)',
                              background: sellingSymbol === h.symbol ? 'rgba(255,255,255,0.03)' : 'rgba(255,60,60,0.1)',
                              border: '1px solid rgba(255,60,60,0.2)',
                              cursor: sellingSymbol === h.symbol ? 'not-allowed' : 'pointer',
                            }}
                          >
                            {sellingSymbol === h.symbol ? '...' : '卖出'}
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
                  7-BOT CONSENSUS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  AI 投资团队
                </h3>

                {team.length === 0 ? (
                  <div className="mt-6 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      暂无团队投票数据
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
                              {signalLabel(m.signal)}
                            </span>
                          </div>
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
                  </>
                )}
              </div>
            </motion.div>

            {/* 持仓分布卡片 (span-4) */}
            <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  ALLOCATION
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  持仓分布
                </h3>
                {allocation.length === 0 ? (
                  <div className="mt-6 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>暂无数据</p>
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
                      PERFORMANCE // SUMMARY
                    </span>
                    <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                      收益汇总
                    </h3>
                  </div>
                  <div className="text-right">
                    <span className="text-label">总盈亏</span>
                    <div className="text-metric mt-1" style={{ color: pnlColor(p.total_pnl) }}>
                      {pnlSign(p.total_pnl)}{fmtUsd(p.total_pnl)}
                    </div>
                  </div>
                </div>

                {/* 明细卡片网格 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                  {[
                    { label: '总成本', value: fmtUsd(p.total_cost), color: 'var(--text-secondary)' },
                    { label: '总市值', value: fmtUsd(p.total_value), color: 'var(--accent-cyan)' },
                    { label: '今日涨跌', value: `${pnlSign(p.day_change_pct)}${p.day_change_pct.toFixed(2)}%`, color: pnlColor(p.day_change_pct) },
                    { label: '总收益率', value: `${pnlSign(p.total_pnl_pct)}${p.total_pnl_pct.toFixed(2)}%`, color: pnlColor(p.total_pnl_pct) },
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
                  RISK METRICS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  风险指标
                </h3>
                <div className="mt-4 space-y-4 flex-1">
                  {[
                    { label: '总成本基础', value: fmtUsd(p.total_cost), color: 'var(--text-secondary)' },
                    { label: '未实现盈亏', value: `${pnlSign(p.total_pnl)}${fmtUsd(p.total_pnl)}`, color: pnlColor(p.total_pnl) },
                    { label: '今日波动', value: `${pnlSign(p.day_change_pct)}${p.day_change_pct.toFixed(2)}%`, color: pnlColor(p.day_change_pct) },
                    { label: '持仓集中度', value: p.positions.length > 0 ? `${p.positions[0]?.weight.toFixed(1)}% 最大` : 'N/A', color: 'var(--accent-cyan)' },
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
                  AI VOTE // TRIGGER
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  发起 AI 投票
                </h3>
                <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
                  输入股票代码，让 7 个 AI Bot 投票分析
                </p>

                <div className="mt-6 space-y-4 flex-1">
                  {/* 股票代码输入 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      股票代码
                    </label>
                    <input
                      type="text"
                      placeholder="例如: AAPL"
                      value={voteSymbol}
                      onChange={e => setVoteSymbol(e.target.value)}
                      className="w-full font-mono text-sm"
                      style={inputStyle}
                    />
                  </div>

                  {/* 时间周期选择 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      分析周期
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
                        分析中...
                      </span>
                    ) : '分析'}
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 投票结果展示 */}
            <motion.div className="col-span-12 lg:col-span-7" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  VOTE RESULTS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  投票结果
                </h3>

                {!voteResult ? (
                  <div className="mt-8 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {voteLoading ? '正在等待 AI 团队投票...' : '请在左侧输入股票代码，发起分析'}
                    </p>
                  </div>
                ) : (
                  <div className="mt-4 flex-1 space-y-3">
                    {/* 共识结论 */}
                    {(voteResult.consensus || voteResult.summary) && (
                      <div className="p-3 rounded-lg" style={{ background: 'rgba(0,240,255,0.06)', border: '1px solid rgba(0,240,255,0.15)' }}>
                        <span className="font-mono text-[10px] uppercase" style={{ color: 'var(--accent-cyan)' }}>共识结论</span>
                        <p className="font-mono text-sm mt-1" style={{ color: 'var(--text-primary)' }}>
                          {voteResult.consensus || voteResult.summary}
                        </p>
                      </div>
                    )}

                    {/* 各 Bot 投票详情 */}
                    <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 400 }}>
                      {(voteResult.votes || voteResult.team || []).map((v, i) => {
                        const name = v.bot_name || v.analyst || `Bot ${i + 1}`;
                        const sig = v.signal || v.vote || '未知';
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
                                  {signalLabel(sig)}
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
                  TRADING CONTROLS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  自动交易控制
                </h3>
                <p className="font-mono text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  管理自动交易开关与风控参数
                </p>

                {controlsLoading && !controls ? (
                  <div className="mt-8 flex items-center justify-center py-12">
                    <div className="inline-block w-6 h-6 border-2 border-t-transparent rounded-full animate-spin"
                         style={{ borderColor: 'var(--accent-cyan)', borderTopColor: 'transparent' }} />
                  </div>
                ) : !controls ? (
                  <div className="mt-8 text-center py-12">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      无法加载交易控制配置
                    </p>
                    <button
                      onClick={fetchControls}
                      className="mt-3 px-4 py-1.5 rounded-lg font-mono text-xs"
                      style={{ background: 'var(--accent-cyan)', color: '#000' }}
                    >
                      重试
                    </button>
                  </div>
                ) : (
                  <div className="mt-6 space-y-1">
                    {/* 布尔开关列表 */}
                    {([
                      { key: 'auto_trader_enabled' as const, label: '自动交易开关', desc: '启用后 Bot 将自动执行交易信号' },
                      { key: 'ibkr_live_mode' as const, label: '实盘模式', desc: '关闭为模拟盘，开启为 IBKR 实盘交易' },
                      { key: 'risk_protection_enabled' as const, label: '风控保护', desc: '启用止损、仓位限制等风控规则' },
                      { key: 'allow_short_selling' as const, label: '允许做空', desc: '允许卖空操作（需要 IBKR 保证金账户）' },
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
                          最大日交易次数
                        </span>
                        <span className="font-mono text-[11px] block mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                          单日内允许执行的最大交易次数
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
                        <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>次/天</span>
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
                  STATUS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  状态说明
                </h3>
                <div className="mt-4 space-y-3 flex-1">
                  <div className="p-3 rounded-lg" style={{ background: 'rgba(255,180,0,0.06)', border: '1px solid rgba(255,180,0,0.15)' }}>
                    <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      开启「自动交易」后，系统会根据 AI 投票结果自动执行买卖操作。
                      请确保已开启「风控保护」以限制单笔风险。
                    </p>
                  </div>
                  <div className="p-3 rounded-lg" style={{ background: 'rgba(255,60,60,0.06)', border: '1px solid rgba(255,60,60,0.15)' }}>
                    <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      切换到「实盘模式」将使用真实资金交易，请谨慎操作。
                      建议先在模拟盘验证策略稳定性。
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
                  BACKTEST // CONFIG
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  回测参数
                </h3>

                <div className="mt-6 space-y-4 flex-1">
                  {/* 股票代码 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      股票代码
                    </label>
                    <input
                      type="text"
                      placeholder="例如: AAPL"
                      value={btSymbol}
                      onChange={e => setBtSymbol(e.target.value)}
                      className="w-full font-mono text-sm"
                      style={inputStyle}
                    />
                  </div>

                  {/* 策略选择 */}
                  <div>
                    <label className="font-mono text-[10px] uppercase block mb-1.5" style={{ color: 'var(--text-disabled)' }}>
                      交易策略
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {([
                        { id: 'ma_cross', label: '均线交叉' },
                        { id: 'rsi', label: 'RSI 指标' },
                        { id: 'macd', label: 'MACD' },
                        { id: 'bbands', label: '布林带' },
                        { id: 'volume', label: '成交量' },
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
                      回测周期
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
                        回测中...
                      </span>
                    ) : '开始回测'}
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 回测结果 */}
            <motion.div className="col-span-12 lg:col-span-7" variants={cardVariants}>
              <div className="abyss-card p-6 h-full flex flex-col">
                <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                  BACKTEST // RESULTS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  回测结果
                </h3>

                {!btResult ? (
                  <div className="mt-8 flex-1 flex items-center justify-center">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      {btLoading ? '正在执行回测...' : '请在左侧配置参数，开始回测'}
                    </p>
                  </div>
                ) : (
                  <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-4">
                    {([
                      { label: '总收益率', value: fmtPct(btResult.total_return), color: pnlColor(btResult.total_return ?? 0) },
                      { label: '年化收益率', value: fmtPct(btResult.annual_return), color: pnlColor(btResult.annual_return ?? 0) },
                      { label: '最大回撤', value: fmtPct(btResult.max_drawdown), color: 'var(--accent-red)' },
                      { label: '夏普比率', value: btResult.sharpe_ratio?.toFixed(2) ?? 'N/A', color: 'var(--accent-cyan)' },
                      { label: '胜率', value: fmtPct(btResult.win_rate), color: 'var(--accent-green)' },
                      { label: '总交易次数', value: btResult.total_trades?.toString() ?? 'N/A', color: 'var(--text-primary)' },
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

        {/* ====== Tab 5: 交易日志 ====== */}
        {activeTab === 'logs' && (
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            <motion.div variants={cardVariants}>
              <div className="abyss-card p-6">
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  TRADE LOGS
                </span>
                <h3 className="font-display text-lg font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
                  交易日志
                </h3>
                <div className="mt-12 flex flex-col items-center justify-center py-16">
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
                  >
                    <span className="text-2xl" style={{ opacity: 0.4 }}>📋</span>
                  </div>
                  <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
                    交易日志功能开发中
                  </p>
                  <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-disabled)' }}>
                    后续版本将支持分页查看历史交易记录、筛选和导出
                  </p>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

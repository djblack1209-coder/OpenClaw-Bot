/**
 * usePortfolioAPI — 资产页面数据 hooks
 * 封装所有「我的资产」相关的后端 API 调用：
 * 持仓、盈亏、交易控制开关、AI 投票、仪表盘数据、回测
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { clawbotFetch } from '../lib/tauri';

/* ════════════════════════════════════
 * 类型定义 — 对齐后端 Pydantic Schema
 * ════════════════════════════════════ */

/** 单只持仓 */
export interface Position {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  currency: string;
  exchange: string;
  sector?: string;
}

/** 持仓汇总 */
export interface PortfolioPositions {
  positions: Position[];
  total_market_value: number;
  total_unrealized_pnl: number;
  total_unrealized_pnl_pct: number;
  updated_at: string;
  connected: boolean;
}

/** 盈亏摘要 */
export interface PnLSummary {
  daily_pnl: number;
  daily_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  win_rate: number;
  total_trades: number;
  updated_at: string;
}

/** 交易控制开关 — 对齐 controls.py TradingControls */
export interface TradingControls {
  auto_trader_enabled: boolean;
  ibkr_live_mode: boolean;
  risk_protection_enabled: boolean;
  allow_short_selling: boolean;
  max_daily_trades: number;
}

/** 仪表盘数据 */
export interface DashboardData {
  chart_data: Array<{ time: string; value: number }>;
  assets: Array<{ symbol: string; value: number; pct: number }>;
  connected: boolean;
}

/** 单个 AI 投票 */
export interface BotVote {
  bot_id: string;
  vote: 'BUY' | 'HOLD' | 'SKIP';
  confidence: number;
  reasoning: string;
  entry_price?: number;
  stop_loss?: number;
  take_profit?: number;
  abstained: boolean;
}

/** 团队投票结果 */
export interface VoteResult {
  symbol: string;
  consensus_signal: string;
  consensus_score: number;
  votes: BotVote[];
  passed: boolean;
  veto_triggered: boolean;
  timestamp: string;
  divergence?: number;
}

/** 回测结果 */
export interface BacktestResult {
  symbol: string;
  strategy: string;
  period: string;
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  chart_data: Array<{ time: string; equity: number; benchmark: number }>;
  trades: Array<{ date: string; action: string; price: number; pnl?: number }>;
}

/* ════════════════════════════════════
 * Hook: usePositions — 持仓数据
 * ════════════════════════════════════ */
export function usePositions(pollInterval = 30000) {
  const [data, setData] = useState<PortfolioPositions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const resp = await clawbotFetch('/api/v1/trading/positions');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      // Normalize backend field names to frontend interface
      if (json?.positions) {
        json.positions = json.positions.map((p: any) => ({
          ...p,
          quantity: p.quantity ?? p.qty ?? 0,
          avg_cost: p.avg_cost ?? p.avg_price ?? 0,
          unrealized_pnl: p.unrealized_pnl ?? p.pnl ?? 0,
          unrealized_pnl_pct: p.unrealized_pnl_pct ?? p.pnl_pct ?? 0,
          current_price: p.current_price ?? p.price ?? 0,
          market_value: p.market_value ?? p.mkt_value ?? 0,
        }));
      }
      // Compute totals if missing from backend response
      if (json.total_market_value === undefined || json.total_market_value === null) {
        const normalizedPositions = json.positions ?? [];
        json.total_market_value = normalizedPositions.reduce((sum: number, p: any) => sum + (p.market_value || 0), 0);
        json.total_unrealized_pnl = normalizedPositions.reduce((sum: number, p: any) => sum + (p.unrealized_pnl || 0), 0);
        json.total_unrealized_pnl_pct = json.total_market_value > 0
          ? (json.total_unrealized_pnl / json.total_market_value) * 100
          : 0;
      }
      if (json.updated_at === undefined) {
        json.updated_at = new Date().toISOString();
      }
      if (json.connected === undefined) {
        json.connected = false;
      }
      setData(json);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取持仓失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch_();
    const id = setInterval(fetch_, pollInterval);
    return () => clearInterval(id);
  }, [fetch_, pollInterval]);

  return { positions: data, loading, error, refresh: fetch_ };
}

/* ════════════════════════════════════
 * Hook: usePnL — 盈亏摘要
 * ════════════════════════════════════ */
export function usePnL(pollInterval = 30000) {
  const [data, setData] = useState<PnLSummary | null>(null);
  const [loading, setLoading] = useState(true);
  /* 错误状态，供消费组件展示错误 UI */
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const resp = await clawbotFetch('/api/v1/trading/pnl');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取盈亏数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch_();
    const id = setInterval(fetch_, pollInterval);
    return () => clearInterval(id);
  }, [fetch_, pollInterval]);

  return { pnl: data, loading, error, refresh: fetch_ };
}

/* ════════════════════════════════════
 * Hook: useTradingControls — 交易开关
 * ════════════════════════════════════ */
export function useTradingControls() {
  const [controls, setControls] = useState<TradingControls | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  /* 错误状态，供消费组件展示错误 UI */
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const resp = await clawbotFetch('/api/v1/controls/trading');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setControls(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取交易控制失败');
    } finally {
      setLoading(false);
    }
  }, []);

  /** 更新交易控制 — 部分更新 */
  const update = useCallback(async (patch: Partial<TradingControls>) => {
    if (!controls) return;
    setSaving(true);
    try {
      const resp = await clawbotFetch('/api/v1/controls/trading', {
        method: 'POST',
        body: JSON.stringify({ ...controls, ...patch }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setControls(await resp.json());
    } catch (e) {
      console.error('更新交易控制失败:', e);
      throw e;
    } finally {
      setSaving(false);
    }
  }, [controls]);

  useEffect(() => { fetch_(); }, [fetch_]);

  return { controls, loading, saving, error, update, refresh: fetch_ };
}

/* ════════════════════════════════════
 * Hook: useDashboard — 仪表盘图表数据
 * ════════════════════════════════════ */
export function useDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch_ = useCallback(async () => {
    try {
      const resp = await clawbotFetch('/api/v1/trading/dashboard');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
    } catch {
      setData({ chart_data: [], assets: [], connected: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);

  return { dashboard: data, loading, refresh: fetch_ };
}

/* ════════════════════════════════════
 * Hook: useAIVote — AI 团队投票（按需触发）
 * ════════════════════════════════════ */
export function useAIVote() {
  const [result, setResult] = useState<VoteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** 触发投票 — symbol 如 "AAPL", period 如 "3mo" */
  const triggerVote = useCallback(async (symbol: string, period = '3mo') => {
    /* 取消上一次未完成的请求 */
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await clawbotFetch('/api/v1/trading/vote', {
        method: 'POST',
        body: JSON.stringify({ symbol, period }),
        signal: ac.signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setResult(json);
      return json as VoteResult;
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        const msg = e instanceof Error ? e.message : 'AI 投票请求失败';
        setError(msg);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  /* 组件卸载时取消请求 */
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  return { voteResult: result, voting: loading, voteError: error, triggerVote };
}

/* ════════════════════════════════════
 * Hook: useBacktest — 策略回测（按需触发）
 * ════════════════════════════════════ */
export function useBacktest() {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 触发回测 */
  const runBacktest = useCallback(async (
    symbol: string,
    strategy = 'ma_cross',
    period = '1y',
  ) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const params = new URLSearchParams({ symbol, strategy, period });
      const resp = await clawbotFetch(`/api/v1/omega/investment/backtest?${params}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setResult(json);
      return json as BacktestResult;
    } catch (e) {
      const msg = e instanceof Error ? e.message : '回测请求失败';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { backtestResult: result, backtesting: loading, backtestError: error, runBacktest };
}

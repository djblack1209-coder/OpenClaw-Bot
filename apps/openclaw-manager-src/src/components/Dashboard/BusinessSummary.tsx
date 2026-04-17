import { useEffect, useState, useCallback } from 'react';
import {
  TrendingUp,
  TrendingDown,
  ShoppingBag,
  BrainCircuit,
  Share2,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import { api, isTauri } from '@/lib/tauri';

// ── 业务指标数据类型 ──

interface TradingData {
  /** 今日盈亏金额 */
  todayPnl: number | null;
  /** 交易系统是否连接 */
  connected: boolean;
}

interface XianyuData {
  /** 闲鱼客服是否在线 */
  online: boolean;
  /** 今日消息数 */
  messageCount: number | null;
}

interface LlmCostData {
  /** 今日花费（美元） */
  todayCost: number | null;
  /** 每日预算上限（美元） */
  dailyBudget: number;
}

interface SocialData {
  /** 今日发帖数 */
  todayPosts: number | null;
  /** 社媒系统是否运行 */
  running: boolean;
}

interface BusinessData {
  trading: TradingData;
  xianyu: XianyuData;
  llmCost: LlmCostData;
  social: SocialData;
}

// ── 默认值（API 未返回时显示占位） ──
// 注意：这些是 fallback 占位值，实际数据从后端 API 获取

const defaultData: BusinessData = {
  trading: { todayPnl: null, connected: false },
  xianyu: { online: false, messageCount: null },
  llmCost: { todayCost: null, dailyBudget: 50 },  // dailyBudget 从后端 API 读取，此处仅作 fallback
  social: { todayPosts: null, running: false },
};

// ── 安全地从未知响应中提取数值 ──

function safeNumber(val: unknown): number | null {
  if (val === null || val === undefined) return null;
  const n = Number(val);
  return isNaN(n) ? null : n;
}

function safeBool(val: unknown, fallback = false): boolean {
  if (typeof val === 'boolean') return val;
  return fallback;
}

/**
 * 今日经营概览 — 在 Dashboard 顶部展示 4 张业务指标卡片
 *
 * 数据来源：
 *   交易盈亏  → api.clawbotTradingPnl()
 *   闲鱼客服  → api.clawbotStatus()
 *   AI 花费   → api.omegaCost()
 *   社媒运营  → api.clawbotSocialMetrics()
 */
export function BusinessSummary() {
  const [data, setData] = useState<BusinessData>(defaultData);
  const [loading, setLoading] = useState(true);

  const fetchBusinessData = useCallback(async () => {
    if (!isTauri()) {
      setLoading(false);
      return;
    }

    try {
      // 并行拉取 4 个接口，单个失败不影响其他
      const [tradingRes, statusRes, costRes, socialRes] = await Promise.allSettled([
        api.clawbotTradingPnl(),
        api.clawbotStatus(),
        api.omegaCost(),
        api.clawbotSocialMetrics(),
      ]);

      setData({
        // ── 交易盈亏 ──
        trading: (() => {
          if (tradingRes.status !== 'fulfilled') return defaultData.trading;
          const r = tradingRes.value as Record<string, unknown>;
          return {
            todayPnl: safeNumber(r.today_pnl ?? r.daily_pnl ?? r.pnl),
            connected: safeBool(r.connected ?? r.is_connected, false),
          };
        })(),

        // ── 闲鱼客服（从整体状态中提取） ──
        xianyu: (() => {
          if (statusRes.status !== 'fulfilled') return defaultData.xianyu;
          const r = statusRes.value as Record<string, unknown>;
          const xianyu = (r.xianyu ?? r.xianyu_service ?? r.xianyu_cs) as
            | Record<string, unknown>
            | undefined;
          if (!xianyu) return defaultData.xianyu;
          return {
            online: safeBool(xianyu.online ?? xianyu.running ?? xianyu.connected, false),
            messageCount: safeNumber(xianyu.today_messages ?? xianyu.message_count),
          };
        })(),

        // ── AI 花费 ──
        llmCost: (() => {
          if (costRes.status !== 'fulfilled') return defaultData.llmCost;
          const r = costRes.value as Record<string, unknown>;
          return {
            todayCost: safeNumber(r.today_cost ?? r.daily_cost ?? r.cost),
            dailyBudget: safeNumber(r.daily_budget ?? r.budget) ?? 50,
          };
        })(),

        // ── 社媒运营 ──
        social: (() => {
          if (socialRes.status !== 'fulfilled') return defaultData.social;
          const r = socialRes.value as Record<string, unknown>;
          return {
            todayPosts: safeNumber(r.today_posts ?? r.posts_today ?? r.total_posts),
            running: safeBool(r.running ?? r.active, false),
          };
        })(),
      });
    } catch {
      // 全部失败时保持默认值
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBusinessData();
    // 每 60 秒刷新一次业务数据
    const timer = setInterval(fetchBusinessData, 60_000);
    return () => clearInterval(timer);
  }, [fetchBusinessData]);

  // ── 格式化盈亏金额 ──
  const formatPnl = (val: number | null): string => {
    if (val === null) return '--';
    const prefix = val >= 0 ? '+' : '';
    return `${prefix}$${val.toFixed(2)}`;
  };

  // ── 格式化美元金额 ──
  const formatUsd = (val: number | null): string => {
    if (val === null) return '--';
    return `$${val.toFixed(2)}`;
  };

  // ── 花费进度百分比 ──
  const costPercent =
    data.llmCost.todayCost !== null
      ? Math.min((data.llmCost.todayCost / data.llmCost.dailyBudget) * 100, 100)
      : 0;

  return (
    <div className="bg-[var(--bg-primary)] rounded-xl p-6 border border-[var(--border-default)] shadow-lg">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">今日经营概览</h3>
        <button
          onClick={fetchBusinessData}
          disabled={loading}
          className="text-gray-500 hover:text-white transition-colors disabled:opacity-50"
          title="刷新数据"
          aria-label="刷新业务数据"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <RefreshCw size={16} />
          )}
        </button>
      </div>

      {/* 4 张指标卡片 - TradingView 风格 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* ── 1. 今日盈亏 ── */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-light)] hover:border-[var(--brand-500)] transition-all hover:shadow-glow">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[var(--text-secondary)] font-medium">今日盈亏</span>
            {data.trading.todayPnl !== null && data.trading.todayPnl >= 0 ? (
              <TrendingUp size={16} className="text-success" />
            ) : (
              <TrendingDown size={16} className="text-danger" />
            )}
          </div>
          <p
            className={clsx(
              'text-2xl font-bold mb-2 oc-tabular-nums',
              data.trading.todayPnl === null
                ? 'text-[var(--text-disabled)]'
                : data.trading.todayPnl >= 0
                ? 'text-success'
                : 'text-danger'
            )}
          >
            {formatPnl(data.trading.todayPnl)}
          </p>
          <div className="flex items-center gap-1.5">
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full',
                data.trading.connected ? 'bg-success animate-pulse' : 'bg-gray-500'
              )}
            />
            <p className="text-xs text-[var(--text-tertiary)]">
              {data.trading.connected ? '交易已连接' : '未连接'}
            </p>
          </div>
        </div>

        {/* ── 2. 闲鱼客服 ── */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-light)] hover:border-[var(--brand-500)] transition-all hover:shadow-glow">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[var(--text-secondary)] font-medium">闲鱼客服</span>
            <ShoppingBag size={16} className="text-warning" />
          </div>
          <div className="flex items-center gap-2 mb-2">
            <div
              className={clsx(
                'w-2 h-2 rounded-full',
                data.xianyu.online ? 'bg-success animate-pulse' : 'bg-gray-500'
              )}
            />
            <p className="text-2xl font-bold text-[var(--text-primary)]">
              {data.xianyu.online ? '在线' : '离线'}
            </p>
          </div>
          <p className="text-xs text-[var(--text-tertiary)]">
            {data.xianyu.messageCount !== null
              ? `今日 ${data.xianyu.messageCount} 条消息`
              : '暂无数据'}
          </p>
        </div>

        {/* ── 3. 今日 AI 花费 ── */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-light)] hover:border-[var(--brand-500)] transition-all hover:shadow-glow">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[var(--text-secondary)] font-medium">今日 AI 花费</span>
            <BrainCircuit size={16} className="text-info" />
          </div>
          <p className="text-2xl font-bold text-[var(--text-primary)] mb-2 oc-tabular-nums">
            {formatUsd(data.llmCost.todayCost)}
          </p>
          {/* 花费进度条 */}
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-[var(--text-tertiary)]">
              <span>{formatUsd(data.llmCost.todayCost)}</span>
              <span>${data.llmCost.dailyBudget.toFixed(0)}</span>
            </div>
            <div className="w-full bg-[var(--bg-tertiary)] rounded-full h-1.5 overflow-hidden">
              <div
                className={clsx(
                  'h-1.5 rounded-full transition-all duration-300',
                  costPercent >= 90
                    ? 'bg-danger'
                    : costPercent >= 60
                    ? 'bg-warning'
                    : 'bg-info'
                )}
                style={{ width: `${costPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* ── 4. 社媒运营 ── */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-light)] hover:border-[var(--brand-500)] transition-all hover:shadow-glow">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[var(--text-secondary)] font-medium">社媒运营</span>
            <Share2 size={16} className="text-[var(--brand-500)]" />
          </div>
          <p className="text-2xl font-bold text-[var(--text-primary)] mb-2 oc-tabular-nums">
            {data.social.todayPosts !== null ? `${data.social.todayPosts} 篇` : '--'}
          </p>
          <div className="flex items-center gap-1.5">
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full',
                data.social.running ? 'bg-success animate-pulse' : 'bg-gray-500'
              )}
            />
            <p className="text-xs text-[var(--text-tertiary)]">
              {data.social.running ? '自动驾驶中' : '未运行'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

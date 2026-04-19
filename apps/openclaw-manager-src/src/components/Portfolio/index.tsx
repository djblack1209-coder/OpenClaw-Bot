/**
 * Portfolio — 投资组合页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { api } from '../../lib/api';

/* ====== 类型定义 ====== */
interface Position {
  symbol: string; name: string; quantity: number; avg_price: number;
  current_price: number; pnl: number; pnl_pct: number; market_value: number; weight: number;
}
interface PortfolioSummary {
  total_value: number; total_cost: number; total_pnl: number; total_pnl_pct: number;
  day_change: number; day_change_pct: number; positions: Position[];
  position_count: number; connected: boolean;
}
interface TeamMember { analyst: string; signal: string; confidence: number; reasoning: string; }
interface TeamResponse { team: TeamMember[]; }

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

/* ====== 主组件 ====== */

export function Portfolio() {
  /* ---- 状态 ---- */
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sellingSymbol, setSellingSymbol] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- 数据拉取 ---- */
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

  /* ---- 挂载 + 30 秒自动刷新 ---- */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(() => fetchData(true), 30_000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ---- 卖出操作 ---- */
  const handleSell = async (symbol: string, quantity: number) => {
    setSellingSymbol(symbol);
    try {
      await api.tradingSell(symbol, quantity, 'MKT');
      console.log(`[Portfolio] 卖出成功: ${symbol} x${quantity}`);
      /* 刷新数据 */
      fetchData(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '未知错误';
      console.error(`[Portfolio] 卖出失败: ${symbol}`, msg);
    } finally {
      setSellingSymbol(null);
    }
  };

  /* ---- 加载态 ---- */
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

  /* ---- 错误态 ---- */
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

  /* ---- 空数据兜底 ---- */
  const p = portfolio ?? {
    total_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0,
    day_change: 0, day_change_pct: 0, positions: [], position_count: 0, connected: false,
  };

  /* ---- 概览统计 ---- */
  const stats = [
    { label: '总资产', value: fmtUsd(p.total_value), color: 'var(--text-primary)' },
    { label: '今日盈亏', value: `${pnlSign(p.day_change)}${fmtUsd(p.day_change)}`, color: pnlColor(p.day_change) },
    { label: '总收益率', value: `${pnlSign(p.total_pnl_pct)}${p.total_pnl_pct.toFixed(2)}%`, color: pnlColor(p.total_pnl_pct) },
    { label: '持仓数量', value: String(p.position_count), color: 'var(--accent-cyan)' },
  ];

  /* ---- Bot 共识统计 ---- */
  const bullCount = team.filter(m => signalCategory(m.signal) === 'bull').length;
  const bearCount = team.filter(m => signalCategory(m.signal) === 'bear').length;
  const neutralCount = team.length - bullCount - bearCount;
  const totalVotes = team.length || 1; /* 防除零 */

  /* ---- 持仓权重分布 (从真实数据计算) ---- */
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
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：总资产概览 (span-8) + AI 团队共识 (span-4) ====== */}
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

        {/* ====== 7-Bot AI 团队共识 (span-4) ====== */}
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

        {/* ====== 持仓分布卡片 (span-4) ====== */}
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

        {/* ====== 总收益汇总卡片 (span-8) ====== */}
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

        {/* ====== 风险指标卡片 (span-4) ====== */}
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
    </div>
  );
}

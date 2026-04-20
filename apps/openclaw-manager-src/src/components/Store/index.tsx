/**
 * Store — 插件商店页面 (Sonic Abyss Bento Grid 风格)
 * 数据来自 Evolution 自进化系统 API，30 秒自动刷新
 * 提案 = 可用插件/工具，审批 = 安装
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from 'sonner';
import {
  Search,
  Star,
  Package,
  TrendingUp,
  Zap,
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  ThumbsUp,
  RefreshCw,
} from 'lucide-react';
import { clawbotFetchJson, clawbotFetch } from '../../lib/tauri-core';
import type { EvolutionProposalRaw, EvolutionStatsRaw } from '../../lib/tauri-core';

/* ============================================================
   常量 & 类型
   ============================================================ */

/** 自动刷新间隔 — 30 秒 */
const REFRESH_INTERVAL_MS = 30_000;

/** 提案状态 → 中文标签 & 颜色 */
const STATUS_MAP: Record<string, { label: string; color: string; Icon: typeof CheckCircle2 }> = {
  approved: { label: '已通过', color: 'var(--accent-green)', Icon: CheckCircle2 },
  rejected: { label: '已拒绝', color: 'var(--accent-red)', Icon: XCircle },
  pending:  { label: '待审批', color: 'var(--accent-amber)', Icon: Clock },
};

/** 标准化单条提案字段（后端字段名不固定） */
function normalizeProposal(raw: EvolutionProposalRaw) {
  return {
    id: raw.id || raw.proposal_id || '',
    name: raw.repo_name || raw.name || raw.repo || '未命名',
    url: raw.repo_url || raw.url || '',
    stars: raw.stars ?? raw.stargazers_count ?? 0,
    growth: raw.growth_rate ?? raw.weekly_growth ?? 0,
    module: raw.target_module || raw.module || '通用',
    score: raw.value_score ?? raw.score ?? 0,
    difficulty: raw.difficulty_score ?? raw.difficulty ?? 0,
    risk: raw.risk_level || raw.risk || '—',
    approach: raw.integration_approach || raw.approach || '',
    status: raw.status || 'pending',
    createdAt: raw.created_at || '',
  };
}

type NormalizedProposal = ReturnType<typeof normalizeProposal>;

/* ============================================================
   动画配置
   ============================================================ */

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] },
  }),
};

/* ============================================================
   Store 主组件
   ============================================================ */

export function Store() {
  /* ── 状态 ── */
  const [proposals, setProposals] = useState<NormalizedProposal[]>([]);
  const [stats, setStats] = useState<EvolutionStatsRaw | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null); // 正在审批的提案 id
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('全部');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── 拉取数据 ── */
  const fetchData = useCallback(async () => {
    try {
      // 并发拉取提案列表和统计数据
      const [proposalsRes, statsRes] = await Promise.allSettled([
        clawbotFetchJson<{ proposals?: EvolutionProposalRaw[]; data?: EvolutionProposalRaw[] }>(
          '/api/v1/evolution/proposals'
        ),
        clawbotFetchJson<EvolutionStatsRaw>('/api/v1/evolution/stats'),
      ]);

      // 处理提案列表
      if (proposalsRes.status === 'fulfilled') {
        const raw = proposalsRes.value;
        const list: EvolutionProposalRaw[] = Array.isArray(raw)
          ? raw
          : raw?.proposals || raw?.data || [];
        setProposals(list.map(normalizeProposal));
        setError(null);
      }

      // 处理统计数据
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '数据加载失败';
      console.error('[Store] 数据拉取失败:', msg);
      if (!proposals.length) {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  /* ── 首次加载 + 30 秒自动刷新 ── */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ── 审批提案（相当于"安装"） ── */
  const handleApprove = useCallback(async (id: string) => {
    if (!id) return;
    setApproving(id);
    try {
      await clawbotFetch(`/api/v1/evolution/proposals/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'approved' }),
      });
      toast.success('提案已通过 — 相当于"安装"这个工具');
      // 刷新数据
      await fetchData();
    } catch (err) {
      toast.error(`审批失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setApproving(null);
    }
  }, [fetchData]);

  /* ── 搜索 + 状态筛选 ── */
  const filtered = useMemo(() => {
    let list = proposals;
    if (statusFilter !== '全部') {
      const key = statusFilter === '待审批' ? 'pending' : statusFilter === '已通过' ? 'approved' : 'rejected';
      list = list.filter((p) => p.status === key);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.module.toLowerCase().includes(q) ||
          p.approach.toLowerCase().includes(q)
      );
    }
    return list;
  }, [proposals, search, statusFilter]);

  /* ── 按状态分组计数 ── */
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { pending: 0, approved: 0, rejected: 0 };
    proposals.forEach((p) => {
      const s = p.status || 'pending';
      counts[s] = (counts[s] || 0) + 1;
    });
    return counts;
  }, [proposals]);

  /* ── 统计卡片数据 ── */
  const statsCards = useMemo(() => {
    const totalProposals = stats?.total_proposals ?? stats?.proposals_count ?? proposals.length;
    const gaps = stats?.capability_gaps ?? stats?.gaps_count ?? 0;
    return [
      { label: '总提案数', value: String(totalProposals), icon: Package, color: 'var(--accent-cyan)' },
      { label: '已通过', value: String(stats?.approved ?? statusCounts.approved), icon: TrendingUp, color: 'var(--accent-green)' },
      { label: '待审批', value: String(stats?.pending ?? statusCounts.pending), icon: Zap, color: 'var(--accent-amber)' },
      { label: '能力缺口', value: String(gaps), icon: Plus, color: 'var(--accent-purple)' },
    ];
  }, [stats, proposals, statusCounts]);

  /* ── 精选提案（前 6 个） ── */
  const featured = filtered.slice(0, 6);

  /* ── 加载中 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-[var(--accent-cyan)]" size={32} />
        <span className="ml-3 text-[var(--text-secondary)] font-mono text-sm">正在加载插件商店…</span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-base)] p-6">
      {/* 12 列 Bento 网格容器 */}
      <div className="grid grid-cols-12 gap-4 auto-rows-min">

        {/* ====== 搜索栏 — 全宽 ====== */}
        <div className="col-span-12">
          <div className="abyss-card px-5 py-3 flex items-center gap-3">
            <Search size={18} className="text-[var(--text-tertiary)] shrink-0" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索提案名称、模块、集成方案…"
              className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] outline-none font-mono"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] text-xs"
              >
                清除
              </button>
            )}
            {/* 手动刷新按钮 */}
            <button
              onClick={() => { setLoading(true); fetchData(); }}
              className="text-[var(--text-tertiary)] hover:text-[var(--accent-cyan)] transition-colors"
              title="手动刷新"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {/* ====== 精选提案 — col-span-8, row-span-2 ====== */}
        <motion.div
          className="col-span-8 row-span-2 abyss-card p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          {/* 标题区域 */}
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-display text-lg font-bold text-[var(--text-primary)] tracking-tight">
                进化提案
              </h2>
              <p className="text-label mt-1">
                插件商店 // EVOLUTION PROPOSALS
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[var(--accent-cyan)]">
              <Package size={16} />
              <span className="font-mono text-xs">{filtered.length} 个结果</span>
            </div>
          </div>

          {/* 提案卡片网格 */}
          {error && !proposals.length ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <span className="font-mono text-sm" style={{ color: 'var(--accent-red)' }}>
                数据加载失败：{error}
              </span>
              <button
                onClick={() => { setError(null); setLoading(true); fetchData(); }}
                className="font-mono text-xs px-4 py-2 rounded-lg"
                style={{ background: 'rgba(0,212,255,0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,212,255,0.25)' }}
              >
                重试
              </button>
            </div>
          ) : featured.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-[var(--text-tertiary)] font-mono text-sm">
              暂无可用插件
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {featured.map((proposal, i) => {
                const si = STATUS_MAP[proposal.status] || STATUS_MAP.pending;
                return (
                  <motion.div
                    key={proposal.id || i}
                    custom={i}
                    variants={cardVariants}
                    initial="hidden"
                    animate="visible"
                    className="group relative rounded-2xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] p-4 hover:border-[var(--accent-cyan)]/30 transition-all duration-300"
                  >
                    {/* 名称 + 模块 */}
                    <div className="flex items-start gap-3 mb-2.5">
                      <span className="text-2xl leading-none">📦</span>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                          {proposal.name}
                        </h3>
                        <p className="text-[11px] text-[var(--text-tertiary)] truncate mt-0.5">
                          {proposal.approach || `模块: ${proposal.module}`}
                        </p>
                      </div>
                    </div>

                    {/* 星标 + 分值 */}
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-[10px] text-[var(--text-tertiary)] font-mono flex items-center gap-1">
                        <Star size={9} className="text-[var(--accent-amber)]" />
                        {proposal.stars.toLocaleString()}
                      </span>
                      <span className="text-[10px] text-[var(--text-tertiary)] font-mono">
                        评分 {proposal.score}
                      </span>
                    </div>

                    {/* 状态 + 操作按钮 */}
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1 text-[10px] font-mono" style={{ color: si.color }}>
                        <si.Icon size={10} />
                        {si.label}
                      </span>
                      {proposal.status === 'pending' && (
                        <button
                          disabled={approving === proposal.id}
                          onClick={() => handleApprove(proposal.id)}
                          className="px-3 py-1 rounded-full border border-[var(--accent-cyan)]/40 text-[var(--accent-cyan)] text-[11px] font-mono hover:bg-[var(--accent-cyan)]/10 transition-colors disabled:opacity-50"
                        >
                          {approving === proposal.id ? (
                            <Loader2 size={11} className="animate-spin inline mr-1" />
                          ) : (
                            <ThumbsUp size={11} className="inline mr-1" />
                          )}
                          通过
                        </button>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </motion.div>

        {/* ====== 状态筛选 — col-span-4 ====== */}
        <motion.div
          className="col-span-4 abyss-card p-5"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <h3 className="text-label mb-4">状态筛选 // STATUS FILTER</h3>
          <div className="space-y-1">
            {[
              { label: '全部', count: proposals.length },
              { label: '待审批', count: statusCounts.pending },
              { label: '已通过', count: statusCounts.approved },
              { label: '已拒绝', count: statusCounts.rejected },
            ].map((cat) => {
              const active = statusFilter === cat.label;
              return (
                <button
                  key={cat.label}
                  onClick={() => setStatusFilter(cat.label)}
                  className={clsx(
                    'w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all duration-200',
                    active
                      ? 'bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] border border-[var(--accent-cyan)]/20'
                      : 'text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)] border border-transparent'
                  )}
                >
                  <span className="font-medium">{cat.label}</span>
                  <span
                    className={clsx(
                      'font-mono text-xs px-2 py-0.5 rounded-full',
                      active
                        ? 'bg-[var(--accent-cyan)]/20 text-[var(--accent-cyan)]'
                        : 'bg-white/[0.05] text-[var(--text-tertiary)]'
                    )}
                  >
                    {cat.count}
                  </span>
                </button>
              );
            })}
          </div>
        </motion.div>

        {/* ====== 统计 — col-span-4（分类下方） ====== */}
        <motion.div
          className="col-span-4 abyss-card p-5"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <h3 className="text-label mb-4">统计概览 // STATS</h3>
          <div className="grid grid-cols-2 gap-3">
            {statsCards.map((stat) => (
              <div
                key={stat.label}
                className="rounded-xl bg-white/[0.02] border border-[var(--glass-border)] p-3 text-center"
              >
                <stat.icon size={16} className="mx-auto mb-2" style={{ color: stat.color }} />
                <div className="text-metric text-xl">{stat.value}</div>
                <div className="text-label text-[9px] mt-1">{stat.label}</div>
              </div>
            ))}
          </div>

          {/* 最近扫描时间 */}
          {stats && (stats.last_scan || stats.last_scan_at || stats.last_scan_time) && (
            <div className="mt-4 pt-3 border-t border-[var(--glass-border)]">
              <span className="text-label text-[9px]">最近扫描</span>
              <p className="font-mono text-[10px] text-[var(--text-secondary)] mt-1">
                {stats.last_scan_time || stats.last_scan_at || stats.last_scan || '—'}
              </p>
            </div>
          )}
        </motion.div>

        {/* ====== 完整提案列表 — col-span-12 ====== */}
        <motion.div
          className="col-span-12 abyss-card p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
        >
          <h3 className="text-label mb-4">全部提案 // ALL PROPOSALS</h3>

          {filtered.length === 0 ? (
            <div className="text-center py-10 text-[var(--text-tertiary)] font-mono text-sm">
              暂无数据
            </div>
          ) : (
            <>
              {/* 表头 */}
              <div className="grid grid-cols-[2fr_1fr_0.8fr_0.8fr_0.8fr_1.5fr] gap-4 px-4 py-2 text-[10px] text-[var(--text-tertiary)] font-mono uppercase tracking-widest border-b border-[var(--glass-border)]">
                <span>名称</span>
                <span>模块</span>
                <span>评分</span>
                <span>风险</span>
                <span>状态</span>
                <span className="text-right">操作</span>
              </div>

              {/* 行数据 */}
              {filtered.map((p, i) => {
                const si = STATUS_MAP[p.status] || STATUS_MAP.pending;
                return (
                  <motion.div
                    key={p.id || i}
                    custom={i}
                    variants={cardVariants}
                    initial="hidden"
                    animate="visible"
                    className="grid grid-cols-[2fr_1fr_0.8fr_0.8fr_0.8fr_1.5fr] gap-4 px-4 py-3.5 items-center border-b border-[var(--glass-border)]/50 last:border-b-0 hover:bg-white/[0.02] transition-colors"
                  >
                    <span className="text-sm text-[var(--text-primary)] font-medium truncate">{p.name}</span>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">{p.module}</span>
                    <span className="font-mono text-xs text-[var(--accent-cyan)]">{p.score}</span>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">{p.risk}</span>
                    <span className="flex items-center gap-1 text-xs font-mono" style={{ color: si.color }}>
                      <si.Icon size={10} />
                      {si.label}
                    </span>
                    <div className="flex items-center justify-end gap-2">
                      {p.status === 'pending' && (
                        <button
                          disabled={approving === p.id}
                          onClick={() => handleApprove(p.id)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--accent-green)]/30 text-[var(--accent-green)] text-[11px] font-mono hover:bg-[var(--accent-green)]/10 transition-colors disabled:opacity-50"
                        >
                          {approving === p.id ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <ThumbsUp size={11} />
                          )}
                          通过
                        </button>
                      )}
                      {p.url && (
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] font-mono text-[var(--text-tertiary)] hover:text-[var(--accent-cyan)] transition-colors"
                        >
                          查看 →
                        </a>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}

import { useEffect, useState, useCallback, useRef } from 'react';
import { toast } from 'sonner';

import {
  Dna, RefreshCw, WifiOff, Loader2, Scan,
  Star, TrendingUp, AlertTriangle, CheckCircle2,
  XCircle, Package, Target, Zap,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { api, isTauri } from '../../lib/tauri';
import clsx from 'clsx';

// ─── Types ────────────────────────────────────────────────────

interface EvolutionStats {
  total_proposals: number;
  total_scans: number;
  capability_gaps: number;
  last_scan?: string;
  approved?: number;
  rejected?: number;
  pending?: number;
}

interface CapabilityGap {
  module: string;
  description: string;
  priority?: string;
  discovered_at?: string;
}

interface EvolutionProposal {
  id?: string;
  repo_name: string;
  repo_url?: string;
  stars?: number;
  growth_rate?: number;
  target_module: string;
  value_score: number;
  difficulty_score?: number;
  risk_level: string;
  integration_approach?: string;
  status: string;
  created_at?: string;
}

// ─── Constants ────────────────────────────────────────────────

const REFRESH_INTERVAL = 60_000;

const MODULE_COLORS: Record<string, { bg: string; text: string }> = {
  trading:    { bg: 'bg-amber-500/15',  text: 'text-amber-400' },
  social:     { bg: 'bg-blue-500/15',   text: 'text-blue-400' },
  memory:     { bg: 'bg-purple-500/15', text: 'text-purple-400' },
  evolution:  { bg: 'bg-green-500/15',  text: 'text-green-400' },
  core:       { bg: 'bg-cyan-500/15',   text: 'text-cyan-400' },
  analytics:  { bg: 'bg-pink-500/15',   text: 'text-pink-400' },
  security:   { bg: 'bg-red-500/15',    text: 'text-red-400' },
  default:    { bg: 'bg-gray-500/15',   text: 'text-gray-400' },
};

function getModuleColor(mod: string) {
  return MODULE_COLORS[mod.toLowerCase()] ?? MODULE_COLORS.default;
}

const RISK_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  LOW:    { bg: 'bg-green-500/15',  text: 'text-green-400',  border: 'border-green-500/30' },
  MEDIUM: { bg: 'bg-amber-500/15',  text: 'text-amber-400',  border: 'border-amber-500/30' },
  HIGH:   { bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/30' },
};

function getRiskColor(level: string) {
  return RISK_COLORS[level.toUpperCase()] ?? RISK_COLORS.MEDIUM;
}

const STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  pending:  { bg: 'bg-amber-500/15',  text: 'text-amber-400',  border: 'border-amber-500/30' },
  approved: { bg: 'bg-green-500/15',  text: 'text-green-400',  border: 'border-green-500/30' },
  rejected: { bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/30' },
  merged:   { bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30' },
};

function getStatusColor(status: string) {
  return STATUS_COLORS[status.toLowerCase()] ?? STATUS_COLORS.pending;
}

// ─── Component ────────────────────────────────────────────────

export function Evolution() {
  const [stats, setStats] = useState<EvolutionStats | null>(null);
  const [gaps, setGaps] = useState<CapabilityGap[]>([]);
  const [proposals, setProposals] = useState<EvolutionProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [apiOnline, setApiOnline] = useState(true);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch all data ─────────────────────────────────────────

  const fetchAll = useCallback(async (silent = false) => {
    if (!isTauri()) {
      setLoading(false);
      return;
    }
    if (!silent) setLoading(true);
    else setRefreshing(true);

    try {
      const [rawStats, rawGaps, rawProposals] = await Promise.allSettled([
        api.clawbotEvolutionStats(),
        api.clawbotEvolutionGaps(),
        api.clawbotEvolutionProposals(),
      ]);

      // 统计数据
      if (rawStats.status === 'fulfilled' && rawStats.value) {
        const s = rawStats.value as Record<string, unknown>;
        setStats({
          total_proposals: s.total_proposals ?? s.proposals_count ?? 0,
          total_scans: s.total_scans ?? s.scans_count ?? 0,
          capability_gaps: s.capability_gaps ?? s.gaps_count ?? 0,
          last_scan: s.last_scan ?? s.last_scan_at ?? undefined,
          approved: s.approved ?? undefined,
          rejected: s.rejected ?? undefined,
          pending: s.pending ?? undefined,
        });
      }

      // 差距分析
      if (rawGaps.status === 'fulfilled' && rawGaps.value) {
        const raw = rawGaps.value as Record<string, unknown>;
        const gapList: Record<string, unknown>[] = Array.isArray(raw)
          ? raw
          : (raw?.gaps ?? raw?.data ?? []);
        setGaps(
          gapList.map((g) => ({
            module: (g.module ?? g.category ?? 'unknown') as string,
            description: (g.description ?? g.gap ?? g.name ?? '') as string,
            priority: (g.priority ?? g.severity) as string | undefined,
            discovered_at: (g.discovered_at ?? g.created_at) as string | undefined,
          }))
        );
      }

      // 提案列表
      if (rawProposals.status === 'fulfilled' && rawProposals.value) {
        const rawP = rawProposals.value as Record<string, unknown>;
        const propList: Record<string, unknown>[] = Array.isArray(rawP)
          ? rawP
          : (rawP?.proposals ?? rawP?.data ?? []);
        setProposals(
          propList.map((p) => ({
            id: (p.id ?? p.proposal_id) as string | undefined,
            repo_name: (p.repo_name ?? p.repo ?? p.name ?? 'unknown') as string,
            repo_url: (p.repo_url ?? p.url) as string | undefined,
            stars: (p.stars ?? p.stargazers_count) as number | undefined,
            growth_rate: (p.growth_rate ?? p.weekly_growth) as number | undefined,
            target_module: (p.target_module ?? p.module ?? 'core') as string,
            value_score: (p.value_score ?? p.score ?? 0) as number,
            difficulty_score: (p.difficulty_score ?? p.difficulty) as number | undefined,
            risk_level: (p.risk_level ?? p.risk ?? 'MEDIUM') as string,
            integration_approach: (p.integration_approach ?? p.approach) as string | undefined,
            status: (p.status ?? 'pending') as string,
            created_at: p.created_at as string | undefined,
          }))
        );
      }

      setApiOnline(true);
    } catch {
      setApiOnline(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // ── Scan now ───────────────────────────────────────────────

  const handleScan = useCallback(async () => {
    if (!isTauri() || scanning) return;
    setScanning(true);
    try {
      await api.clawbotEvolutionScan();
      setApiOnline(true);
      // 扫描后刷新数据
      await fetchAll(true);
    } catch {
      setApiOnline(false);
    } finally {
      setScanning(false);
    }
  }, [scanning, fetchAll]);

  // ── Auto-refresh ──────────────────────────────────────────

  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(() => fetchAll(true), REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll]);

  // ── Render ────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col gap-6 max-w-6xl mx-auto overflow-y-auto scroll-container pr-2 pb-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Dna className="text-green-400" />
            自进化引擎
          </h1>
          <p className="text-gray-400 mt-1">
            自动扫描开源生态，发现能力缺口，生成进化提案。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchAll()}
            className="flex items-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-lg text-white transition-colors border border-dark-500"
          >
            <RefreshCw size={16} className={clsx((loading || refreshing) && 'animate-spin')} />
            刷新
          </button>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:hover:bg-green-600 rounded-lg text-white transition-colors"
          >
            {scanning ? <Loader2 size={16} className="animate-spin" /> : <Scan size={16} />}
            立即扫描
          </button>
        </div>
      </div>

      {/* Offline Banner */}
      {!apiOnline && !loading && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 text-amber-400">
          <WifiOff size={18} />
          <span className="text-sm font-medium">ClawBot API 离线 — 自进化引擎不可达</span>
          <button
            onClick={() => fetchAll()}
            className="ml-auto text-xs bg-amber-500/20 hover:bg-amber-500/30 px-3 py-1 rounded-full transition-colors"
          >
            重试
          </button>
        </div>
      )}

      {/* Stats Cards Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatsCard
          icon={<Target size={20} className="text-blue-400" />}
          label="总提案数"
          value={stats?.total_proposals}
          loading={loading}
        />
        <StatsCard
          icon={<Scan size={20} className="text-green-400" />}
          label="总扫描次数"
          value={stats?.total_scans}
          loading={loading}
        />
        <StatsCard
          icon={<AlertTriangle size={20} className="text-amber-400" />}
          label="能力缺口"
          value={stats?.capability_gaps}
          loading={loading}
        />
      </div>

      {/* Last scan info */}
      {stats?.last_scan && (
        <div className="text-xs text-gray-500 flex items-center gap-1.5">
          <Zap size={12} />
          上次扫描: {new Date(stats.last_scan).toLocaleString()}
        </div>
      )}

      {/* Capability Gaps Section */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <AlertTriangle size={18} className="text-amber-400" />
          能力缺口
        </h2>
        {loading ? (
          <SkeletonList count={3} />
        ) : gaps.length === 0 ? (
          <div className="text-center py-10 text-gray-500 bg-dark-800/50 rounded-xl border border-dark-700 border-dashed">
            未发现能力缺口
          </div>
        ) : (
          <div className="space-y-2">
            {gaps.map((gap, idx) => {
              const color = getModuleColor(gap.module);
              return (
                <Card key={idx} className="bg-dark-800 border border-dark-600 hover:border-dark-400 transition-all">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-3">
                      <span
                        className={clsx(
                          'px-2 py-0.5 rounded text-[10px] font-medium tracking-wider uppercase shrink-0',
                          color.bg,
                          color.text,
                        )}
                      >
                        {gap.module}
                      </span>
                      <span className="text-sm text-gray-200 flex-1">{gap.description}</span>
                      {gap.priority && (
                        <span className="text-[10px] text-gray-500 uppercase tracking-wider shrink-0">
                          {gap.priority}
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* Proposals Section */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <Package size={18} className="text-blue-400" />
          进化提案
          {proposals.length > 0 && (
            <span className="text-xs text-gray-500 font-normal ml-1">({proposals.length})</span>
          )}
        </h2>
        {loading ? (
          <SkeletonList count={4} />
        ) : proposals.length === 0 ? (
          <div className="text-center py-10 text-gray-500 bg-dark-800/50 rounded-xl border border-dark-700 border-dashed">
            暂无提案 — 运行扫描以发现潜在集成
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((p, idx) => {
              const modColor = getModuleColor(p.target_module);
              const riskColor = getRiskColor(p.risk_level);
              const statusColor = getStatusColor(p.status);

              return (
                <Card key={p.id ?? idx} className="bg-dark-800 border border-dark-600 hover:border-dark-400 transition-all">
                  <CardContent className="p-4 space-y-3">
                    {/* Top row: repo info + badges */}
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          {/* Repo name */}
                          <span className="text-white font-medium text-sm">
                            {p.repo_url ? (
                              <a
                                href={p.repo_url}
                                target="_blank"
                                rel="noreferrer"
                                className="hover:text-green-400 transition-colors"
                              >
                                {p.repo_name}
                              </a>
                            ) : (
                              p.repo_name
                            )}
                          </span>

                          {/* Stars */}
                          {p.stars != null && (
                            <span className="flex items-center gap-1 text-xs text-gray-500">
                              <Star size={11} className="text-yellow-500" />
                              {p.stars >= 1000 ? `${(p.stars / 1000).toFixed(1)}k` : p.stars}
                            </span>
                          )}

                          {/* Growth rate */}
                          {p.growth_rate != null && (
                            <span className="flex items-center gap-1 text-xs text-green-400">
                              <TrendingUp size={11} />
                              {p.growth_rate > 0 ? '+' : ''}
                              {(p.growth_rate * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Right badges */}
                      <div className="flex items-center gap-2 shrink-0">
                        {/* Module badge */}
                        <span
                          className={clsx(
                            'px-2 py-0.5 rounded text-[10px] font-medium tracking-wider uppercase',
                            modColor.bg,
                            modColor.text,
                          )}
                        >
                          {p.target_module}
                        </span>
                        {/* Risk badge */}
                        <span
                          className={clsx(
                            'px-2 py-0.5 rounded text-[10px] font-medium tracking-wider uppercase border',
                            riskColor.bg,
                            riskColor.text,
                            riskColor.border,
                          )}
                        >
                          {p.risk_level}
                        </span>
                        {/* Status badge */}
                        <span
                          className={clsx(
                            'px-2 py-0.5 rounded text-[10px] font-medium tracking-wider uppercase border',
                            statusColor.bg,
                            statusColor.text,
                            statusColor.border,
                          )}
                        >
                          {p.status}
                        </span>
                      </div>
                    </div>

                    {/* Scores row */}
                    <div className="flex items-center gap-6">
                      {/* Value score */}
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-xs text-gray-500 shrink-0 w-12">价值</span>
                        <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-green-500 rounded-full transition-all"
                            style={{ width: `${Math.min(p.value_score * 100, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-green-400 font-mono w-10 text-right">
                          {(p.value_score * 100).toFixed(0)}
                        </span>
                      </div>
                      {/* Difficulty score */}
                      {p.difficulty_score != null && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">难度</span>
                          <span className="text-xs text-gray-300 font-mono">
                            {typeof p.difficulty_score === 'number' && p.difficulty_score <= 1
                              ? (p.difficulty_score * 10).toFixed(1)
                              : p.difficulty_score}
                            /10
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Integration approach */}
                    {p.integration_approach && (
                      <p className="text-xs text-gray-400 leading-relaxed">
                        <span className="text-gray-500">方案:</span> {p.integration_approach}
                      </p>
                    )}

                    {/* Actions (only for pending) */}
                    {p.status.toLowerCase() === 'pending' && (
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          onClick={() => handleApprove(p.id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 text-xs rounded-lg transition-colors border border-green-500/30"
                        >
                          <CheckCircle2 size={13} />
                          批准
                        </button>
                        <button
                          onClick={() => handleReject(p.id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-xs rounded-lg transition-colors border border-red-500/30"
                        >
                          <XCircle size={13} />
                          拒绝
                        </button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );

  // ── Action handlers (placeholder — PATCH not yet wired) ───

  async function handleApprove(id?: string) {
    if (!id) return;
    try {
      await api.clawbotEvolutionUpdateProposal(id, 'approved');
      setProposals((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: 'approved' } : p))
      );
    } catch (err) {
      console.error('审批提案失败:', err);
      toast.error('审批通过失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  }

  async function handleReject(id?: string) {
    if (!id) return;
    try {
      await api.clawbotEvolutionUpdateProposal(id, 'rejected');
      setProposals((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: 'rejected' } : p))
      );
    } catch (err) {
      console.error('拒绝提案失败:', err);
      toast.error('审批拒绝失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  }
}

// ─── Sub-components ─────────────────────────────────────────

function StatsCard({
  icon,
  label,
  value,
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value?: number;
  loading: boolean;
}) {
  return (
    <Card className="bg-dark-800 border-dark-600">
      <CardContent className="p-4 flex items-center gap-4">
        <div className="p-2.5 bg-dark-700 rounded-lg">{icon}</div>
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          {loading ? (
            <div className="w-12 h-6 rounded bg-dark-700 animate-pulse mt-1" />
          ) : (
            <p className="text-xl font-mono text-white mt-0.5">
              {value != null ? value.toLocaleString() : '—'}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function SkeletonList({ count }: { count: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 rounded-lg bg-dark-800 border border-dark-700/50 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-16 h-5 rounded bg-dark-700" />
            <div className="w-full h-4 rounded bg-dark-700" />
          </div>
        </div>
      ))}
    </div>
  );
}

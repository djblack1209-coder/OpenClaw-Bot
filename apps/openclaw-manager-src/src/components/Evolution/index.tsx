/**
 * Evolution — 进化引擎页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自真实后端 API
 */
import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Dna, Zap, TrendingUp, CheckCircle2,
  Clock, ArrowUpRight, Sparkles, Loader2, RefreshCw,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';
import { toast } from '@/lib/notify';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型定义 ====== */

interface Proposal {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  created_at: string;
}

interface EvoStats {
  total_proposals?: number;
  executed?: number;
  success_rate?: number;
  current_cycle?: number;
  score?: number;
  weekly_optimizations?: number;
  performance_improvement?: string;
  cost_saved?: string;
  [key: string]: unknown;
}

/* ====== 工具函数 ====== */

/** 优先级颜色 */
function priorityColor(p: string): string {
  const lower = (p ?? '').toLowerCase();
  if (lower === 'high' || lower === '高') return 'var(--accent-red)';
  if (lower === 'medium' || lower === '中') return 'var(--accent-amber)';
  return 'var(--accent-green)';
}

/** 优先级标签（需要传入翻译函数） */
function priorityLabel(p: string, t: (key: string) => string): string {
  const lower = (p ?? '').toLowerCase();
  if (lower === 'high') return t('evolution.priorityHigh');
  if (lower === 'medium') return t('evolution.priorityMedium');
  if (lower === 'low') return t('evolution.priorityLow');
  return p || '—';
}

/** 状态显示（需要传入翻译函数） */
function statusStyle(s: string, t?: (key: string) => string) {
  const tr = t ?? ((k: string) => k);
  const lower = (s ?? '').toLowerCase();
  if (lower === 'executed' || lower === 'success' || lower === '成功' || lower === 'completed')
    return { color: 'var(--accent-green)', Icon: CheckCircle2, label: tr('evolution.statusSuccess') };
  if (lower === 'running' || lower === 'pending' || lower === '执行中' || lower === 'in_progress')
    return { color: 'var(--accent-cyan)', Icon: Zap, label: tr('evolution.statusRunning') };
  if (lower === 'skipped' || lower === '已跳过')
    return { color: 'var(--text-disabled)', Icon: Clock, label: tr('evolution.statusSkipped') };
  return { color: 'var(--text-secondary)', Icon: Clock, label: s || '—' };
}

/** 格式化时间 */
function fmtTime(iso: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch { return iso.slice(11, 16) || iso; }
}

/* ====== 主组件 ====== */

export function Evolution() {
  const { t } = useLanguage();
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [stats, setStats] = useState<EvoStats>({});

  /* —— 加载数据 —— */
  const fetchAll = useCallback(async () => {
    try {
      const [statsRes, proposalsRes] = await Promise.allSettled([
        api.evolutionStats(),
        api.evolutionProposals(),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value as EvoStats);
      if (proposalsRes.status === 'fulfilled') {
        const raw = proposalsRes.value as any;
        setProposals(Array.isArray(raw) ? raw : raw?.proposals ?? []);
      }
    } catch (err) {
      console.error('[Evolution] 加载失败:', err);
      toast.error(t('evolution.loadFailed'), { channel: 'notification' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  /* —— 触发扫描 —— */
  const handleScan = async () => {
    setScanning(true);
    try {
      await api.evolutionScan();
      /* 扫描完后刷新数据 */
      await fetchAll();
    } catch (err) {
      console.error('[Evolution] 扫描失败:', err);
      toast.error(t('evolution.scanFailed'), { channel: 'notification' });
    } finally {
      setScanning(false);
    }
  };

  /* —— 加载态 —— */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-green)' }} />
      </div>
    );
  }

  /* 从 stats 中提取关键指标 */
  const cycle = stats.current_cycle ?? '—';
  const totalP = stats.total_proposals ?? proposals.length;
  const executed = stats.executed ?? proposals.filter((p) => statusStyle(p.status, t).label === t('evolution.statusSuccess')).length;
  const successRate = stats.success_rate != null
    ? `${(stats.success_rate * 100).toFixed(1)}%`
    : totalP > 0 ? `${((executed / totalP) * 100).toFixed(1)}%` : '—';

  /* 区分待执行和已完成 */
  const pending = proposals.filter((p) => {
    const s = statusStyle(p.status, t);
    return s.label === t('evolution.statusRunning') || s.label !== t('evolution.statusSuccess');
  }).slice(0, 5);

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 进化状态 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: 'rgba(0,255,170,0.12)' }}>
                  <Dna size={20} style={{ color: 'var(--accent-green)' }} />
                </div>
                <div>
                  <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                    AUTO-EVOLUTION
                  </h2>
                  <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                    {t('evolution.subtitle')}
                  </p>
                </div>
              </div>
              {/* 扫描按钮 */}
              <button onClick={handleScan} disabled={scanning}
                className="flex items-center gap-2 px-4 py-2 rounded-xl font-mono text-xs font-bold transition-all"
                style={{
                  background: scanning ? 'var(--bg-tertiary)' : 'rgba(0,255,170,0.12)',
                  color: 'var(--accent-green)',
                  border: '1px solid var(--accent-green)',
                  opacity: scanning ? 0.6 : 1,
                  cursor: scanning ? 'not-allowed' : 'pointer',
                }}>
                {scanning ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {scanning ? t('evolution.scanning') : t('evolution.triggerScan')}
              </button>
            </div>

            {/* 进化周期指标 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {[
                { label: t('evolution.currentCycle'), value: `${t('evolution.cyclePrefix')} ${cycle} ${t('evolution.cycleSuffix')}`, color: 'var(--accent-cyan)' },
                { label: t('evolution.totalProposals'), value: String(totalP), color: 'var(--accent-amber)' },
                { label: t('evolution.executed'), value: String(executed), color: 'var(--accent-green)' },
                { label: t('evolution.successRate'), value: successRate, color: 'var(--accent-green)' },
              ].map((m) => (
                <div key={m.label}>
                  <span className="text-label">{m.label}</span>
                  <p className="font-mono text-sm font-bold mt-1" style={{ color: m.color }}>
                    {m.value}
                  </p>
                </div>
              ))}
            </div>

            {/* 提案列表 */}
            <span className="text-label mb-2" style={{ color: 'var(--text-tertiary)' }}>
              PROPOSALS
            </span>
            <div className="flex-1 space-y-1.5">
              {proposals.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('evolution.noProposals')}
                </div>
              )}
              {proposals.slice(0, 8).map((p) => {
                const ss = statusStyle(p.status, t);
                return (
                  <div key={p.id}
                    className="flex items-center gap-3 py-2.5 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}>
                    <span className="font-mono text-[10px] w-10 shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {fmtTime(p.created_at)}
                    </span>
                    <span className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider shrink-0"
                      style={{ background: `${priorityColor(p.priority)}15`, color: priorityColor(p.priority) }}>
                      {priorityLabel(p.priority, t)}
                    </span>
                    <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                      {p.title}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <ss.Icon size={12} style={{ color: ss.color }} />
                      <span className="font-mono text-[10px]" style={{ color: ss.color }}>
                        {ss.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 进化指标 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>EVOLUTION METRICS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('evolution.metricsTitle')}
            </h3>
            <div className="space-y-5 flex-1">
              {/* 系统评分 */}
              <div>
                <span className="text-label">{t('evolution.systemScore')}</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-green)' }}>
                    {stats.score ?? '—'}
                  </span>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>/10</span>
                </div>
                <div className="w-full h-2 rounded-full mt-2" style={{ background: 'var(--bg-tertiary)' }}>
                  <div className="h-full rounded-full" style={{
                    width: `${((stats.score ?? 0) / 10) * 100}%`,
                    background: 'var(--accent-green)',
                  }} />
                </div>
              </div>

              {/* 本周优化 */}
              <div>
                <span className="text-label">{t('evolution.weeklyOpt')}</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-cyan)' }}>
                    {stats.weekly_optimizations ?? executed}
                  </span>
                  <span className="font-mono text-[10px] flex items-center gap-0.5" style={{ color: 'var(--accent-green)' }}>
                    <ArrowUpRight size={10} /> {t('evolution.proposalUnit')}
                  </span>
                </div>
              </div>

              {/* 性能提升 */}
              <div>
                <span className="text-label">{t('evolution.perfImprovement')}</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-amber)' }}>
                    {stats.performance_improvement ?? '—'}
                  </span>
                </div>
              </div>

              {/* 资源节省 */}
              <div>
                <span className="text-label">{t('evolution.costSaved')}</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-purple)' }}>
                    {stats.cost_saved ?? '—'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 待执行优化 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>PENDING OPTIMIZATIONS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('evolution.pendingOptTitle')}
            </h3>
            <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {pending.length === 0 && (
                <div className="col-span-full text-center py-6 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('evolution.noPendingOpt')}
                </div>
              )}
              {pending.map((p) => (
                <div key={p.id}
                  className={clsx('flex items-start gap-3 py-3 px-4 rounded-lg')}
                  style={{ background: 'var(--bg-secondary)' }}>
                  <span className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider mt-0.5 shrink-0"
                    style={{
                      background: `${priorityColor(p.priority)}15`,
                      color: priorityColor(p.priority),
                    }}>
                    {priorityLabel(p.priority, t)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {p.title}
                    </p>
                    <p className="font-mono text-[10px] mt-1 flex items-center gap-1" style={{ color: 'var(--text-disabled)' }}>
                      <Sparkles size={10} style={{ color: 'var(--accent-amber)' }} />
                      {p.description || '—'}
                    </p>
                  </div>
                  <TrendingUp size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-green)' }} />
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

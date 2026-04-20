/**
 * ExecutionFlow — 智能流引擎监控页面 (Sonic Abyss Bento Grid 风格)
 * 数据来自 OMEGA API + 通知系统，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  GitBranch,
  Activity,
  Clock,
  CheckCircle2,
  Timer,
  Layers,
  ListChecks,
  Terminal,
  Cpu,
  ArrowRight,
  Circle,
  Zap,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '@/i18n';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 常量 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/* ====== 类型 ====== */
type NodeStatus = 'done' | 'running' | 'pending';
type LogLevel = 'INFO' | 'OK' | 'WARN' | 'ERROR';

/** 标准化后的任务节点 */
interface TaskNode {
  id: string;
  label: string;
  status: NodeStatus;
}

/** 引擎指标 */
interface EngineMetric {
  label: string;
  value: string;
  accent: string;
}

/** 日志条目 */
interface LogEntry {
  time: string;
  level: LogLevel;
  message: string;
}

/* ====== DAG 节点颜色映射 ====== */
function nodeStyle(status: NodeStatus) {
  switch (status) {
    case 'done':
      return {
        border: 'var(--accent-green)',
        bg: 'rgba(0, 255, 170, 0.06)',
        text: 'var(--accent-green)',
        glow: '0 0 12px rgba(0, 255, 170, 0.15)',
      };
    case 'running':
      return {
        border: 'var(--accent-amber)',
        bg: 'rgba(251, 191, 36, 0.08)',
        text: 'var(--accent-amber)',
        glow: '0 0 18px rgba(251, 191, 36, 0.25)',
      };
    case 'pending':
      return {
        border: 'var(--glass-border)',
        bg: 'rgba(255, 255, 255, 0.02)',
        text: 'var(--text-tertiary)',
        glow: 'none',
      };
  }
}

/* 状态指示符 */
function StatusIcon({ status }: { status: NodeStatus }) {
  if (status === 'done') return <CheckCircle2 size={12} style={{ color: 'var(--accent-green)' }} />;
  if (status === 'running') return (
    <motion.span animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }} className="inline-flex">
      <Circle size={12} fill="var(--accent-amber)" style={{ color: 'var(--accent-amber)' }} />
    </motion.span>
  );
  return <Circle size={12} style={{ color: 'var(--text-tertiary)' }} />;
}

/* 状态文本 — 需要在组件内通过 t() 翻译 */
const STATUS_LABEL_KEYS: Record<NodeStatus, string> = {
  done: 'executionFlow.statusDone',
  running: 'executionFlow.statusRunning',
  pending: 'executionFlow.statusPending',
};

/* 日志级别颜色 */
const logColor = (l: LogLevel) =>
  l === 'OK' ? 'var(--accent-green)' : l === 'WARN' ? 'var(--accent-amber)' : l === 'ERROR' ? 'var(--accent-red)' : 'var(--text-secondary)';

/** 从 OMEGA 任务数据推导 DAG 节点 */
function tasksToNodes(tasks: Record<string, unknown>[], tFn: (key: string) => string): TaskNode[] {
  if (!tasks || tasks.length === 0) return [];
  return tasks.map((t, i) => ({
    id: String(t.id || t.task_id || `task-${i}`),
    label: String(t.name || t.title || t.description || `${tFn('executionFlow.taskPrefix')} ${i + 1}`),
    status: normalizeTaskStatus(String(t.status || 'pending')),
  }));
}

/** 标准化任务状态 */
function normalizeTaskStatus(raw: string): NodeStatus {
  const s = raw.toLowerCase();
  if (['done', 'completed', 'success', 'finished'].includes(s)) return 'done';
  if (['running', 'active', 'in_progress', 'processing'].includes(s)) return 'running';
  return 'pending';
}

/** 通知条目转日志 */
function notificationsToLogs(items: Record<string, unknown>[]): LogEntry[] {
  return items.map((n) => {
    const level = String(n.level || n.category || 'INFO').toUpperCase() as LogLevel;
    const validLevel = (['INFO', 'OK', 'WARN', 'ERROR'].includes(level) ? level : 'INFO') as LogLevel;
    return {
      time: formatTime(n.time || n.created_at || n.timestamp),
      level: validLevel,
      message: String(n.msg || n.message || n.title || ''),
    };
  });
}

/** 格式化时间为 HH:MM:SS */
function formatTime(raw: unknown): string {
  if (!raw) return '--:--:--';
  const s = String(raw);
  // 如果已是 HH:MM:SS 格式
  if (/^\d{2}:\d{2}:\d{2}$/.test(s)) return s;
  // 尝试解析为 Date
  const d = new Date(s);
  if (!isNaN(d.getTime())) {
    return [d.getHours(), d.getMinutes(), d.getSeconds()]
      .map((n) => String(n).padStart(2, '0'))
      .join(':');
  }
  return s.slice(0, 8);
}

/* ====== 主组件 ====== */

export function ExecutionFlow() {
  const [dagNodes, setDagNodes] = useState<TaskNode[]>([]);
  const [metrics, setMetrics] = useState<EngineMetric[]>([]);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [omegaStatus, setOmegaStatus] = useState<Record<string, unknown> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { t } = useLanguage();

  /* 状态文本翻译 */
  const statusLabel = useCallback((s: NodeStatus) => t(STATUS_LABEL_KEYS[s]), [t]);

  /* ── 拉取数据 ── */
  const fetchData = useCallback(async () => {
    try {
      const [tasksRes, statusRes, notifRes] = await Promise.allSettled([
        clawbotFetchJson<Record<string, unknown>>('/api/v1/omega/tasks'),
        clawbotFetchJson<Record<string, unknown>>('/api/v1/omega/status'),
        clawbotFetchJson<Record<string, unknown>>('/api/v1/system/notifications?limit=10'),
      ]);

      // 处理 OMEGA 任务 → DAG 节点
      if (tasksRes.status === 'fulfilled') {
        const raw = tasksRes.value;
        const list: Record<string, unknown>[] = Array.isArray(raw)
          ? raw
          : (raw?.tasks || raw?.data || raw?.active_tasks || []) as Record<string, unknown>[];
        setDagNodes(tasksToNodes(list, t));
      }

      // 处理 OMEGA 状态 → 引擎指标
      if (statusRes.status === 'fulfilled') {
        const s = statusRes.value;
        setOmegaStatus(s);
        const newMetrics: EngineMetric[] = [
          { label: t('executionFlow.metricTodayTasks'), value: String(s.today_tasks ?? s.total_tasks ?? s.task_count ?? 'N/A'), accent: 'var(--accent-cyan)' },
          { label: t('executionFlow.metricSuccessRate'), value: s.success_rate ? `${s.success_rate}%` : (s.success_count && s.total_count ? `${((Number(s.success_count) / Number(s.total_count)) * 100).toFixed(1)}%` : 'N/A'), accent: 'var(--accent-green)' },
          { label: t('executionFlow.metricAvgDuration'), value: s.avg_duration ? `${s.avg_duration}s` : (s.avg_response_ms ? `${s.avg_response_ms}ms` : 'N/A'), accent: 'var(--accent-amber)' },
          { label: t('executionFlow.metricActivePipelines'), value: String(s.active_pipelines ?? s.active_tasks ?? 'N/A'), accent: 'var(--accent-purple)' },
          { label: t('executionFlow.metricQueuedTasks'), value: String(s.queued_tasks ?? s.pending_tasks ?? 'N/A'), accent: 'var(--text-secondary)' },
          { label: t('executionFlow.metricFailedTasks'), value: String(s.failed_tasks ?? s.error_count ?? 'N/A'), accent: 'var(--accent-red)' },
        ];
        setMetrics(newMetrics);
      } else {
        // API 不可用时显示空状态
        setMetrics([
          { label: t('executionFlow.metricTodayTasks'), value: 'N/A', accent: 'var(--accent-cyan)' },
          { label: t('executionFlow.metricSuccessRate'), value: 'N/A', accent: 'var(--accent-green)' },
          { label: t('executionFlow.metricAvgDuration'), value: 'N/A', accent: 'var(--accent-amber)' },
          { label: t('executionFlow.metricActivePipelines'), value: 'N/A', accent: 'var(--accent-purple)' },
          { label: t('executionFlow.metricQueuedTasks'), value: 'N/A', accent: 'var(--text-secondary)' },
          { label: t('executionFlow.metricFailedTasks'), value: 'N/A', accent: 'var(--accent-red)' },
        ]);
      }

      // 处理通知 → 日志
      if (notifRes.status === 'fulfilled') {
        const raw = notifRes.value;
        const items: Record<string, unknown>[] = Array.isArray(raw)
          ? raw
          : (raw?.notifications || raw?.data || raw?.items || []) as Record<string, unknown>[];
        setLogEntries(notificationsToLogs(items));
      }
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
    }
  }, [t]);

  /* ── 首次加载 + 自动刷新 ── */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ── 当前正在执行的任务 ── */
  const currentTask = useMemo(() => {
    return dagNodes.find((n) => n.status === 'running');
  }, [dagNodes]);

  /* ── 已完成的任务 ── */
  const completedTasks = useMemo(() => {
    return dagNodes.filter((n) => n.status === 'done');
  }, [dagNodes]);

  /* ── 活跃管道（running 的任务） ── */
  const activePipelines = useMemo(() => {
    return dagNodes.filter((n) => n.status === 'running' || n.status === 'pending');
  }, [dagNodes]);

  /* ── 加载中 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-[var(--accent-cyan)]" size={32} />
        <span className="ml-3 text-[var(--text-secondary)] font-mono text-sm">{t('executionFlow.loadingEngine')}</span>
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
        {/* ====== Row 1: DAG 引擎状态 (span-8, row-span-2) + 引擎指标 (span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>DAG EXECUTOR</span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => { setLoading(true); fetchData(); }}
                  className="text-[var(--text-tertiary)] hover:text-[var(--accent-cyan)] transition-colors"
                  title={t('executionFlow.manualRefresh')}
                >
                  <RefreshCw size={12} />
                </button>
                <div className="flex items-center gap-1.5">
                  <motion.span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-green)' }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.5, repeat: Infinity }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>LIVE</span>
                </div>
              </div>
            </div>
            <h2 className="font-display text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
              {t('executionFlow.engineTitle')} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// DAG EXECUTOR</span>
            </h2>

            {/* DAG 流水线可视化 */}
            <div className="flex-1 flex items-center justify-center mt-6 mb-4">
              {dagNodes.length === 0 ? (
                <div className="text-[var(--text-tertiary)] font-mono text-sm">{t('executionFlow.noActiveTasks')}</div>
              ) : (
                <div className="flex items-center gap-0 w-full max-w-[720px]">
                  {dagNodes.slice(0, 6).map((node, i) => {
                    const s = nodeStyle(node.status);
                    return (
                      <div key={node.id} className="flex items-center" style={{ flex: 1 }}>
                        <motion.div
                          className="relative flex flex-col items-center justify-center rounded-xl px-3 py-3 w-full min-w-[90px]"
                          style={{ border: `1px solid ${s.border}`, background: s.bg, boxShadow: s.glow }}
                          initial={{ scale: 0.85, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: i * 0.08, duration: 0.3 }}
                        >
                          <StatusIcon status={node.status} />
                          <span className="font-mono text-[11px] font-semibold mt-1.5 text-center leading-tight" style={{ color: s.text }}>{node.label}</span>
                          <span className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{statusLabel(node.status)}</span>
                        </motion.div>

                        {/* 连接箭头 */}
                        {i < Math.min(dagNodes.length, 6) - 1 && (
                          <div className="flex items-center px-1 shrink-0">
                            <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: i * 0.08 + 0.15, duration: 0.25 }} style={{ transformOrigin: 'left' }}>
                              <ArrowRight size={14} style={{ color: node.status === 'done' && dagNodes[i + 1]?.status !== 'pending' ? 'var(--accent-green)' : 'var(--text-tertiary)' }} />
                            </motion.div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 当前任务信息 */}
            <div className="rounded-lg px-4 py-3 flex items-center gap-6 font-mono text-xs" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
              <div className="flex items-center gap-2">
                <Zap size={13} style={{ color: 'var(--accent-amber)' }} />
                <span style={{ color: 'var(--text-secondary)' }}>{t('executionFlow.currentlyExecuting')}:</span>
                <span style={{ color: 'var(--text-primary)' }}>{currentTask?.label || t('executionFlow.none')}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Timer size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span style={{ color: 'var(--accent-cyan)' }}>{String(omegaStatus?.current_duration || 'N/A')}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Cpu size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span style={{ color: 'var(--accent-purple)' }}>{String(omegaStatus?.current_model || 'N/A')}</span>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                ENGINE METRICS
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('executionFlow.engineMetrics')}
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {metrics.map((m) => (
                <div key={m.label}>
                  <span className="text-label">{m.label}</span>
                  <div className="text-metric mt-1" style={{ color: m.accent }}>
                    {m.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: 活跃管道 (span-6) + 最近完成 (span-6) ====== */}
        <motion.div className="col-span-12 md:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Layers size={14} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                ACTIVE PIPELINES
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('executionFlow.activePipelines')}
            </h3>
            <div className="space-y-3">
              {activePipelines.length === 0 ? (
                <div className="text-center py-6 text-[var(--text-tertiary)] font-mono text-sm">
                  {t('executionFlow.noActivePipelines')}
                </div>
              ) : (
                activePipelines.map((p, i) => (
                  <motion.div
                    key={p.id}
                    className="rounded-lg px-4 py-3"
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid var(--glass-border)',
                    }}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + i * 0.08 }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {p.label}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wider"
                        style={{
                          background: p.status === 'running' ? 'rgba(0,255,170,0.1)' : 'rgba(255,255,255,0.05)',
                          color: p.status === 'running' ? 'var(--accent-green)' : 'var(--text-tertiary)',
                        }}
                      >
                        {statusLabel(p.status)}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                      <span><Clock size={10} className="inline mr-1" />{statusLabel(p.status)}</span>
                      <span><GitBranch size={10} className="inline mr-1" />{p.id}</span>
                    </div>
                  </motion.div>
                ))
              )}
            </div>
          </div>
        </motion.div>

        <motion.div className="col-span-12 md:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <ListChecks size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                RECENTLY COMPLETED
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('executionFlow.recentlyCompleted')}
            </h3>
            <div className="space-y-2">
              {completedTasks.length === 0 ? (
                <div className="text-center py-6 text-[var(--text-tertiary)] font-mono text-sm">
                  {t('executionFlow.noCompletedTasks')}
                </div>
              ) : (
                completedTasks.map((task, i) => (
                  <motion.div
                    key={task.id}
                    className="flex items-center justify-between rounded-lg px-4 py-2.5"
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid var(--glass-border)',
                    }}
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + i * 0.06 }}
                  >
                    <div className="flex items-center gap-2.5">
                      <CheckCircle2 size={13} style={{ color: 'var(--accent-green)' }} />
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        {task.label}
                      </span>
                    </div>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                      {t('executionFlow.statusDone')}
                    </span>
                  </motion.div>
                ))
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3: 执行日志 (span-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-0 overflow-hidden">
            {/* 终端顶栏 */}
            <div
              className="flex items-center justify-between px-5 py-3"
              style={{
                borderBottom: '1px solid var(--glass-border)',
                background: 'rgba(255,255,255,0.01)',
              }}
            >
              <div className="flex items-center gap-2">
                <Terminal size={13} style={{ color: 'var(--accent-cyan)' }} />
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  EXECUTION LOG
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{ background: 'var(--accent-green)' }}
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                  {t('executionFlow.realtime')}
                </span>
              </div>
            </div>

            {/* 日志内容 */}
            <div className="px-5 py-4 space-y-1 font-mono text-[11px] leading-relaxed max-h-[280px] overflow-y-auto">
              {logEntries.length === 0 ? (
                <span className="text-[var(--text-tertiary)]">{t('executionFlow.noLogData')}</span>
              ) : (
                logEntries.map((log, i) => (
                  <motion.div
                    key={i}
                    className="flex gap-3"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + i * 0.04 }}
                  >
                    <span style={{ color: 'var(--text-tertiary)', minWidth: 60 }}>{log.time}</span>
                    <span
                      className="font-semibold"
                      style={{ color: logColor(log.level), minWidth: 36 }}
                    >
                      {log.level}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{log.message}</span>
                  </motion.div>
                ))
              )}
              {/* 光标闪烁 */}
              <motion.span
                className="inline-block w-[6px] h-[13px] ml-[100px] mt-1"
                style={{ background: 'var(--accent-cyan)' }}
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 0.9, repeat: Infinity }}
              />
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

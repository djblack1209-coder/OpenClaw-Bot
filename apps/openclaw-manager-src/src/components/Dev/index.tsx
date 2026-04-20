/**
 * Dev — 开发总控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 从 /api/v1/status 获取系统版本和运行时间等真实数据
 * Git/技术债务/依赖更新 已接入真实 API
 * 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Code2,
  GitCommit,
  ShieldCheck,
  AlertTriangle,
  Package,
  Loader2,
  AlertCircle,
  Clock,
  ExternalLink,
  CheckCircle2,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { api } from '../../lib/api';
import { toast } from 'sonner';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 自动刷新间隔 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/* ====== 类型定义 ====== */

/** /api/v1/status 返回的系统状态 */
interface StatusData {
  version?: string;
  uptime_seconds?: number;
  uptime?: number;
  python_version?: string;
  hostname?: string;
  pid?: number;
  started_at?: string;
  bot_count?: number;
  bots_running?: number;
  modules_loaded?: number;
  active_services?: number;
  services_count?: number;
  [key: string]: unknown;
}

/** /api/v1/perf 返回的性能数据 */
interface PerfData {
  cpu_percent?: number;
  memory_mb?: number;
  memory_percent?: number;
  request_count?: number;
  requests_total?: number;
  avg_latency_ms?: number;
  [key: string]: unknown;
}

/** Git 提交记录 */
interface GitLogEntry {
  hash: string;
  author: string;
  date: string;
  message: string;
}

/** HEALTH.md 摘要 */
interface HealthSummary {
  active_critical: number;
  active_high: number;
  active_medium: number;
  active_low: number;
  resolved_count: number;
}

/** 过时依赖项 */
interface OutdatedDep {
  name: string;
  version: string;
  latest_version: string;
  latest_filetype?: string;
}

/* ====== 工具函数 ====== */

/** 格式化运行时间 */
function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null) return '--';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}天 ${h}时 ${m}分`;
  if (h > 0) return `${h}时 ${m}分`;
  return `${m}分`;
}

/* ====== 暂无数据占位组件 ====== */
function NoDataPlaceholder({ reason, hint }: { reason: string; hint?: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-8 gap-2"
      style={{ color: 'var(--text-disabled)' }}
    >
      <AlertCircle size={20} />
      <span className="font-mono text-xs text-center">{reason}</span>
      {hint && (
        <span className="font-mono text-[10px] text-center" style={{ color: 'var(--text-disabled)' }}>
          {hint}
        </span>
      )}
    </div>
  );
}

/* ====== 主组件 ====== */

export function Dev() {
  /* 状态 — 系统概览 */
  const [status, setStatus] = useState<StatusData | null>(null);
  const [perf, setPerf] = useState<PerfData | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  /* 状态 — Git 提交 */
  const [gitLog, setGitLog] = useState<GitLogEntry[]>([]);
  const [gitLogLoading, setGitLogLoading] = useState(true);
  const [gitLogError, setGitLogError] = useState<string | null>(null);

  /* 状态 — 技术债务 */
  const [healthSummary, setHealthSummary] = useState<HealthSummary | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  /* 状态 — 依赖更新 */
  const [outdatedDeps, setOutdatedDeps] = useState<OutdatedDep[]>([]);
  const [depsLoading, setDepsLoading] = useState(true);
  const [depsError, setDepsError] = useState<string | null>(null);

  /* 数据拉取 — 系统概览 */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [statusRes, perfRes] = await Promise.allSettled([
        clawbotFetchJson<StatusData>('/api/v1/status'),
        clawbotFetchJson<PerfData>('/api/v1/perf'),
      ]);

      if (!mountedRef.current) return;

      if (statusRes.status === 'fulfilled') {
        setStatus(statusRes.value);
        setStatusError(null);
      } else {
        setStatusError('系统状态不可用 — ClawBot 后端可能未运行');
      }

      if (perfRes.status === 'fulfilled') {
        setPerf(perfRes.value);
      }
    } catch {
      if (!mountedRef.current) return;
      toast.error('开发数据加载失败');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  /* 数据拉取 — Git 提交记录 */
  const fetchGitLog = useCallback(async () => {
    setGitLogLoading(true);
    try {
      const data = await api.devGitLog() as GitLogEntry[];
      if (!mountedRef.current) return;
      setGitLog(Array.isArray(data) ? data : []);
      setGitLogError(null);
    } catch {
      if (!mountedRef.current) return;
      setGitLogError('Git 日志加载失败');
    } finally {
      if (mountedRef.current) setGitLogLoading(false);
    }
  }, []);

  /* 数据拉取 — 技术债务 */
  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await api.devHealthSummary() as HealthSummary;
      if (!mountedRef.current) return;
      setHealthSummary(data);
      setHealthError(null);
    } catch {
      if (!mountedRef.current) return;
      setHealthError('健康摘要加载失败');
    } finally {
      if (mountedRef.current) setHealthLoading(false);
    }
  }, []);

  /* 数据拉取 — 过时依赖 */
  const fetchDeps = useCallback(async () => {
    setDepsLoading(true);
    try {
      const data = await api.devOutdatedDeps() as OutdatedDep[];
      if (!mountedRef.current) return;
      setOutdatedDeps(Array.isArray(data) ? data : []);
      setDepsError(null);
    } catch {
      if (!mountedRef.current) return;
      setDepsError('依赖检查失败');
    } finally {
      if (mountedRef.current) setDepsLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    // 并行拉取所有数据
    fetchData();
    fetchGitLog();
    fetchHealth();
    fetchDeps();
    const timer = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchData, fetchGitLog, fetchHealth, fetchDeps]);

  /* 概览统计 — 来自真实 API */
  const overviewStats = statusError
    ? []
    : [
        { label: '系统版本', value: status?.version ?? '--', color: 'var(--accent-cyan)' },
        { label: '运行时间', value: formatUptime(status?.uptime_seconds ?? status?.uptime), color: 'var(--accent-green)' },
        { label: 'Bot 数量', value: String(status?.bot_count ?? status?.bots_running ?? '--'), color: 'var(--accent-purple)' },
        { label: '已加载模块', value: String(status?.modules_loaded ?? status?.active_services ?? status?.services_count ?? '--'), color: 'var(--accent-amber)' },
      ];

  /* 技术债务活跃问题总数 */
  const activeTotal = healthSummary
    ? healthSummary.active_critical + healthSummary.active_high + healthSummary.active_medium + healthSummary.active_low
    : 0;

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 系统概览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Code2 size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  DEV CONTROL
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  开发总控 // SYSTEM STATUS
                </p>
              </div>
              {loading && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {statusError ? (
              <NoDataPlaceholder reason={statusError} />
            ) : (
              <>
                {/* 统计指标 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                  {overviewStats.map((s) => (
                    <div
                      key={s.label}
                      className="rounded-lg p-3"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <span className="text-label">{s.label}</span>
                      <p className="text-metric mt-1" style={{ color: s.color, fontSize: '22px' }}>
                        {s.value}
                      </p>
                    </div>
                  ))}
                </div>

                {/* 运行指标 — 来自 /api/v1/perf */}
                {perf && (
                  <div className="mt-2">
                    <span className="text-label mb-2 block" style={{ color: 'var(--text-tertiary)' }}>运行指标</span>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {[
                        { label: 'CPU 使用', value: perf.cpu_percent != null ? `${perf.cpu_percent.toFixed(1)}%` : '--', color: 'var(--accent-cyan)' },
                        { label: '内存使用', value: perf.memory_mb != null ? `${perf.memory_mb.toFixed(0)} MB` : '--', color: 'var(--accent-amber)' },
                        { label: '请求总数', value: String(perf.request_count ?? perf.requests_total ?? '--'), color: 'var(--accent-green)' },
                      ].map((m) => (
                        <div
                          key={m.label}
                          className="rounded-lg p-3"
                          style={{ background: 'var(--bg-secondary)' }}
                        >
                          <span className="text-label">{m.label}</span>
                          <p className="font-display text-sm font-bold mt-1" style={{ color: m.color }}>
                            {m.value}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 附加信息 */}
                <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--glass-border)' }}>
                  <div className="flex items-center gap-2">
                    <Clock size={12} style={{ color: 'var(--text-disabled)' }} />
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      PID: {status?.pid ?? '--'} | 主机: {status?.hostname ?? '--'} | Python: {status?.python_version ?? '--'}
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        </motion.div>

        {/* ====== Git 提交记录 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <GitCommit size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  Git 提交
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  GIT COMMITS
                </p>
              </div>
              {gitLogLoading && <Loader2 size={14} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {gitLogError ? (
              <NoDataPlaceholder reason={gitLogError} />
            ) : gitLog.length === 0 && !gitLogLoading ? (
              <NoDataPlaceholder reason="暂无提交记录" />
            ) : (
              <div className="flex-1 overflow-y-auto space-y-2 max-h-[360px]">
                {gitLog.map((commit) => (
                  <div
                    key={commit.hash}
                    className="rounded-lg p-3"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <code
                        className="font-mono text-[11px] px-1.5 py-0.5 rounded"
                        style={{ background: 'rgba(34,197,94,0.15)', color: 'var(--accent-green)' }}
                      >
                        {commit.hash}
                      </code>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {commit.date}
                      </span>
                    </div>
                    <p
                      className="font-mono text-xs leading-relaxed truncate"
                      style={{ color: 'var(--text-secondary)' }}
                      title={commit.message}
                    >
                      {commit.message}
                    </p>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                      {commit.author}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== 构建状态 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <ShieldCheck size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  构建状态
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  BUILD STATUS
                </p>
              </div>
            </div>

            <div className="flex flex-col items-center justify-center py-8 gap-3">
              <ExternalLink size={20} style={{ color: 'var(--accent-cyan)' }} />
              <span className="font-mono text-xs text-center" style={{ color: 'var(--text-secondary)' }}>
                请使用 GitHub Actions 查看构建状态
              </span>
              <span className="font-mono text-[10px] text-center" style={{ color: 'var(--text-disabled)' }}>
                未配置 GitHub Token，无法直接调用 API
              </span>
            </div>
          </div>
        </motion.div>

        {/* ====== 技术债务 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <AlertTriangle size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  技术债务
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  TECH DEBT // HEALTH.md
                </p>
              </div>
              {healthLoading && <Loader2 size={14} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {healthError ? (
              <NoDataPlaceholder reason={healthError} />
            ) : healthSummary ? (
              <div className="space-y-4">
                {/* 活跃问题汇总 */}
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: '阻塞', value: healthSummary.active_critical, icon: '🔴', color: '#ef4444' },
                    { label: '重要', value: healthSummary.active_high, icon: '🟠', color: '#f97316' },
                    { label: '一般', value: healthSummary.active_medium, icon: '🟡', color: '#eab308' },
                    { label: '低优先', value: healthSummary.active_low, icon: '🔵', color: '#3b82f6' },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="rounded-lg p-3 flex items-center gap-3"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <span className="text-base">{item.icon}</span>
                      <div>
                        <span className="text-label">{item.label}</span>
                        <p className="font-display text-lg font-bold" style={{ color: item.color }}>
                          {item.value}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* 汇总行 */}
                <div
                  className="rounded-lg p-3 flex items-center justify-between"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={14} style={{ color: 'var(--accent-amber)' }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      活跃问题合计
                    </span>
                  </div>
                  <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-amber)' }}>
                    {activeTotal}
                  </span>
                </div>
                <div
                  className="rounded-lg p-3 flex items-center justify-between"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      已解决
                    </span>
                  </div>
                  <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-green)' }}>
                    {healthSummary.resolved_count}
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        </motion.div>

        {/* ====== 依赖更新 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6 flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <Package size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  依赖更新
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  PIP OUTDATED PACKAGES
                </p>
              </div>
              {depsLoading && <Loader2 size={14} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {depsError ? (
              <NoDataPlaceholder reason={depsError} />
            ) : depsLoading ? (
              <div className="flex items-center justify-center py-8 gap-2" style={{ color: 'var(--text-disabled)' }}>
                <Loader2 size={16} className="animate-spin" />
                <span className="font-mono text-xs">正在检查依赖更新（可能需要 10-30 秒）...</span>
              </div>
            ) : outdatedDeps.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <CheckCircle2 size={20} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-xs" style={{ color: 'var(--accent-green)' }}>
                  所有依赖均为最新版本
                </span>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-xs">
                  <thead>
                    <tr style={{ color: 'var(--text-tertiary)' }}>
                      <th className="text-left py-2 px-3 font-normal">包名</th>
                      <th className="text-left py-2 px-3 font-normal">当前版本</th>
                      <th className="text-left py-2 px-3 font-normal">最新版本</th>
                      <th className="text-left py-2 px-3 font-normal">类型</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outdatedDeps.map((dep) => (
                      <tr
                        key={dep.name}
                        className="border-t"
                        style={{ borderColor: 'var(--glass-border)' }}
                      >
                        <td className="py-2 px-3" style={{ color: 'var(--text-primary)' }}>
                          {dep.name}
                        </td>
                        <td className="py-2 px-3" style={{ color: 'var(--accent-amber)' }}>
                          {dep.version}
                        </td>
                        <td className="py-2 px-3" style={{ color: 'var(--accent-green)' }}>
                          {dep.latest_version}
                        </td>
                        <td className="py-2 px-3" style={{ color: 'var(--text-disabled)' }}>
                          {dep.latest_filetype ?? '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-3 pt-3 border-t" style={{ borderColor: 'var(--glass-border)' }}>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    共 {outdatedDeps.length} 个包可更新
                  </span>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

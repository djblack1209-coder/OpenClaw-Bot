/**
 * Dashboard — 系统概览页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自真实后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  Server,
  Cpu,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Terminal,
  Loader2,
  Play,
  Square,
} from 'lucide-react';
import clsx from 'clsx';
import { toast } from '@/lib/notify';
import { EnvironmentStatus } from '../../App';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

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

/** 服务条目（后端返回） */
interface ServiceItem {
  id: string;
  name: string;
  label: string;
  status: 'running' | 'stopped' | 'error';
  uptime: string;
  memory: string;
}

/** 系统状态（/api/v1/status 返回） */
interface SystemStatus {
  version?: string;
  uptime?: string;
  uptime_seconds?: number;
  status?: string;
  [key: string]: unknown;
}

/** 系统性能（/api/v1/perf 返回） */
interface SystemPerf {
  cpu_percent?: number;
  memory_mb?: number;
  memory_percent?: number;
  api_health?: number;
  today_messages?: number;
  active_users?: number;
  llm_calls?: number;
  avg_response_ms?: number;
  avg_response?: string;
  [key: string]: unknown;
}

/** 通知/日志条目（/api/v1/system/notifications 返回） */
interface NotificationItem {
  level: string;
  time: string;
  msg: string;
  message?: string;
}

/* ====== 工具函数 ====== */

/** 服务状态图标和颜色 */
function statusIcon(status: ServiceItem['status']) {
  switch (status) {
    case 'running':
      return { Icon: CheckCircle2, color: 'var(--accent-green)', label: 'dashboard.statusRunning' };
    case 'stopped':
      return { Icon: XCircle, color: 'var(--text-disabled)', label: 'dashboard.statusStopped' };
    case 'error':
      return { Icon: AlertTriangle, color: 'var(--accent-red)', label: 'dashboard.statusError' };
  }
}

/** 日志级别颜色 */
function logColor(level: string): string {
  if (level === 'error') return 'var(--accent-red)';
  if (level === 'warn' || level === 'warning') return 'var(--accent-amber)';
  return 'var(--accent-green)';
}

/** 格式化运行时间（秒 → 人类可读） */
function formatUptime(seconds?: number): string {
  if (!seconds || seconds <= 0) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/** 格式化内存（MB → 人类可读） */
function formatMemory(mb?: number): string {
  if (!mb && mb !== 0) return '—';
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)}GB`;
  return `${Math.round(mb)}MB`;
}

/** 格式化平均响应时间 */
function formatAvgResponse(perf: SystemPerf): string {
  if (perf.avg_response) return perf.avg_response;
  if (perf.avg_response_ms != null) return `${(perf.avg_response_ms / 1000).toFixed(1)}s`;
  return '--';
}

/* ====== 接口定义 ====== */
interface DashboardProps {
  envStatus: EnvironmentStatus | null;
  onSetupComplete: () => void;
}

/* ====== 主组件 ====== */

export function Dashboard({ envStatus: _envStatus, onSetupComplete: _onSetupComplete }: DashboardProps) {
  const { t } = useLanguage();
  /* —— 状态 —— */
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [perf, setPerf] = useState<SystemPerf | null>(null);
  const [logs, setLogs] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* —— 拉取所有数据 —— */
  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      /* 并发请求四个接口 */
      const [svcRes, statusRes, perfRes, logRes] = await Promise.allSettled([
        clawbotFetchJson<ServiceItem[]>('/api/v1/system/services'),
        clawbotFetchJson<SystemStatus>('/api/v1/status'),
        clawbotFetchJson<SystemPerf>('/api/v1/perf'),
        clawbotFetchJson<NotificationItem[]>('/api/v1/system/notifications?limit=10'),
      ]);

      if (svcRes.status === 'fulfilled') setServices(Array.isArray(svcRes.value) ? svcRes.value : []);
      if (statusRes.status === 'fulfilled') setSystemStatus(statusRes.value);
      if (perfRes.status === 'fulfilled') setPerf(perfRes.value);
      if (logRes.status === 'fulfilled') setLogs(Array.isArray(logRes.value) ? logRes.value : []);
    } catch (err) {
      console.error('[Dashboard] 数据加载失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  /* —— 首次加载 + 30 秒自动刷新 —— */
  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(() => fetchAll(true), REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll]);

  /* —— 启动/停止服务 —— */
  const handleServiceAction = async (svc: ServiceItem, action: 'start' | 'stop') => {
    const actionLabel = action === 'start' ? t('dashboard.actionStart') : t('dashboard.actionStop');
    setActionLoading(`${svc.id}-${action}`);
    try {
      await clawbotFetchJson(`/api/v1/system/services/${svc.id}/${action}`, { method: 'POST' });
      toast.success(`${svc.label || svc.name} ${actionLabel}${t('dashboard.actionSuccess')}`, { channel: 'log' });
      /* 刷新服务列表 */
      await fetchAll(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`${actionLabel}${t('dashboard.actionFailed')}: ${msg}`, { channel: 'notification' });
    } finally {
      setActionLoading(null);
    }
  };

  /* —— 派生数据 —— */
  const runningCount = services.filter((s) => s.status === 'running').length;

  /* —— 加载态 —— */
  if (loading && services.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
          <span className="font-mono text-sm" style={{ color: 'var(--text-tertiary)' }}>
            {t('dashboard.connectingBackend')}
          </span>
        </div>
      </div>
    );
  }

  /* —— 快捷统计（从 perf 接口取真实数据） —— */
  const quickStats = [
    { label: t('dashboard.todayMessages'), value: perf?.today_messages != null ? String(perf.today_messages) : '--', color: 'var(--accent-cyan)' },
    { label: t('dashboard.activeUsers'), value: perf?.active_users != null ? String(perf.active_users) : '--', color: 'var(--accent-green)' },
    { label: t('dashboard.llmCalls'), value: perf?.llm_calls != null ? String(perf.llm_calls) : '--', color: 'var(--accent-purple)' },
    { label: t('dashboard.avgResponse'), value: perf ? formatAvgResponse(perf) : '--', color: 'var(--accent-amber)' },
  ];

  /* —— 系统信息摘要（从 perf + status 接口取真实数据） —— */
  const systemMetrics = [
    { icon: Cpu, label: 'CPU', value: perf?.cpu_percent != null ? `${Math.round(perf.cpu_percent)}%` : '--' },
    { icon: Server, label: t('dashboard.memory'), value: perf?.memory_mb != null ? formatMemory(perf.memory_mb) : '--' },
    { icon: Clock, label: t('dashboard.uptime'), value: systemStatus?.uptime || formatUptime(systemStatus?.uptime_seconds as number | undefined) || '--' },
    { icon: Zap, label: t('dashboard.apiHealth'), value: perf?.api_health != null ? `${perf.api_health}%` : '--' },
  ];

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 系统状态 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Activity size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  SYSTEM STATUS
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('dashboard.systemOverview')} // {runningCount}/{services.length} SERVICES ONLINE
                  {systemStatus?.version ? ` // v${systemStatus.version}` : ''}
                </p>
              </div>
            </div>

            {/* 快捷统计 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {quickStats.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 系统信息摘要 */}
            <div
              className="flex items-center gap-6 py-3 px-4 rounded-lg"
              style={{ background: 'var(--bg-secondary)' }}
            >
              {systemMetrics.map((m) => (
                <div key={m.label} className="flex items-center gap-2">
                  <m.icon size={14} style={{ color: 'var(--text-tertiary)' }} />
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                    {m.label}
                  </span>
                  <span className="font-mono text-[11px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {m.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 服务列表 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              SERVICES
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-1" style={{ color: 'var(--text-primary)' }}>
              {t('dashboard.serviceMatrix')}
            </h3>
            <p className="font-mono text-[10px] mb-4" style={{ color: 'var(--text-disabled)' }}>
              服务由后端 API 管理。如需操作 LaunchAgent 级服务，请使用桌面端控制面板。
            </p>

            <div className="flex-1 space-y-1.5">
              {services.length === 0 && (
                <p className="font-mono text-xs py-4 text-center" style={{ color: 'var(--text-disabled)' }}>
                  {t('dashboard.noServiceData')}
                </p>
              )}
              {services.map((svc) => {
                const si = statusIcon(svc.status);
                const isActionLoading =
                  actionLoading === `${svc.id}-start` || actionLoading === `${svc.id}-stop`;
                return (
                  <div
                    key={svc.id || svc.name}
                    className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-2.5">
                      <si.Icon size={14} style={{ color: si.color }} />
                      <div>
                        <p className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                          {svc.label || svc.name}
                        </p>
                        <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {svc.name}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* 启动/停止按钮 */}
                      {isActionLoading ? (
                        <Loader2 size={14} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />
                      ) : svc.status === 'running' ? (
                        <button
                          className="p-1 rounded hover:bg-white/5 transition-colors"
                          title={t('dashboard.stopService')}
                          onClick={() => handleServiceAction(svc, 'stop')}
                        >
                          <Square size={12} style={{ color: 'var(--accent-red)' }} />
                        </button>
                      ) : (
                        <button
                          className="p-1 rounded hover:bg-white/5 transition-colors"
                          title={t('dashboard.startService')}
                          onClick={() => handleServiceAction(svc, 'start')}
                        >
                          <Play size={12} style={{ color: 'var(--accent-green)' }} />
                        </button>
                      )}
                      <div className="text-right">
                        <p
                          className="font-mono text-[10px] font-semibold"
                          style={{ color: si.color }}
                        >
                          {t(si.label)}
                        </p>
                        <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {svc.uptime || '—'}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 实时日志 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-0 overflow-hidden">
            <div
              className="flex items-center gap-2 px-5 py-3"
              style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--glass-border)' }}
            >
              <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                LIVE LOGS
              </span>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                {t('dashboard.recentLogs')} {logs.length} {t('dashboard.logsUnit')}
              </span>
            </div>
            <div className="p-4 space-y-0.5 font-mono text-xs" style={{ background: 'var(--bg-elevated)' }}>
              {logs.length === 0 && (
                <p className="py-2 text-center" style={{ color: 'var(--text-disabled)' }}>
                  {t('dashboard.noLogs')}
                </p>
              )}
              {logs.map((log, i) => (
                <div
                  key={i}
                  className={clsx('py-1 px-2 rounded flex gap-3 transition-colors')}
                  style={{ color: logColor(log.level) }}
                >
                  <span style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                  <span
                    className="uppercase font-semibold w-12"
                    style={{ color: logColor(log.level) }}
                  >
                    {log.level}
                  </span>
                  <span style={{ color: 'var(--text-secondary)' }}>{log.msg || log.message}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

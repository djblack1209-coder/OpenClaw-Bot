/**
 * Dev — 开发总控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 从 /api/v1/status 获取系统版本和运行时间等真实数据
 * 其余数据（Git/CI/技术债务/依赖更新）诚实标注"待接入"
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
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
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
  /* 状态 */
  const [status, setStatus] = useState<StatusData | null>(null);
  const [perf, setPerf] = useState<PerfData | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  /* 数据拉取 */
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

  useEffect(() => {
    mountedRef.current = true;
    fetchData();
    const timer = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchData]);

  /* 概览统计 — 来自真实 API */
  const overviewStats = statusError
    ? []
    : [
        { label: '系统版本', value: status?.version ?? '--', color: 'var(--accent-cyan)' },
        { label: '运行时间', value: formatUptime(status?.uptime_seconds ?? status?.uptime), color: 'var(--accent-green)' },
        { label: 'Bot 数量', value: String(status?.bot_count ?? status?.bots_running ?? '--'), color: 'var(--accent-purple)' },
        { label: '已加载模块', value: String(status?.modules_loaded ?? status?.active_services ?? status?.services_count ?? '--'), color: 'var(--accent-amber)' },
      ];

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

        {/* ====== Git 提交记录 (col-4) — 待接入 ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <GitCommit size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  Git 提交
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  GIT COMMITS
                </p>
              </div>
            </div>

            <NoDataPlaceholder reason="暂无数据" hint="需接入 Git 仓库 API 以显示提交历史" />
          </div>
        </motion.div>

        {/* ====== 构建状态 (col-6) — 待接入 ====== */}
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

            <NoDataPlaceholder reason="暂无数据" hint="需接入 CI/CD 系统（GitHub Actions 等）" />
          </div>
        </motion.div>

        {/* ====== 技术债务 (col-6) — 待接入 ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <AlertTriangle size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  技术债务
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  TECH DEBT
                </p>
              </div>
            </div>

            <NoDataPlaceholder reason="暂无数据" hint="需接入 HEALTH.md 解析或专用技术债务 API" />
          </div>
        </motion.div>

        {/* ====== 依赖更新 (col-12) — 待接入 ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6 flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <Package size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  依赖更新
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  DEPENDENCY UPDATES
                </p>
              </div>
            </div>

            <NoDataPlaceholder reason="暂无数据" hint="需接入 pip outdated / npm outdated 扫描结果" />
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

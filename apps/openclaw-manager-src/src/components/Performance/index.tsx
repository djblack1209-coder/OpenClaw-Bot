/**
 * Performance — 性能监控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自真实后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Gauge,
  AlertTriangle,
  TrendingUp,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import clsx from 'clsx';
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

/** 系统资源仪表 */
interface ResourceGauge {
  label: string;
  value: number | null;
  max: number;
  unit: string;
  color: string;
}

/** API 延迟指标 */
interface LatencyMetric {
  name: string;
  avg: number;
  p50: number;
  p95: number;
  max: number;
  count: number;
}

/** {t('performance.requestThroughput')}（每小时） */
interface ThroughputPoint {
  hour: string;
  rpm: number;
}

/** {t('performance.errorStats')}条目 */
interface ErrorStat {
  type: string;
  count: number;
  pct: string;
  color: string;
}

/** /api/v1/perf 返回的完整数据结构 */
interface PerfData {
  /* 资源相关 */
  cpu_percent?: number;
  memory_mb?: number;
  memory_total_mb?: number;
  memory_percent?: number;
  disk_percent?: number;

  /* 延迟指标 */
  latency_metrics?: LatencyMetric[];
  latency?: LatencyMetric[];

  /* 吞吐量 */
  throughput?: ThroughputPoint[];
  throughput_data?: ThroughputPoint[];

  /* 错误统计 */
  error_stats?: ErrorStat[];
  errors?: ErrorStat[];
  total_error_rate?: string;
  error_rate?: number;

  /* 趋势 */
  throughput_trend?: string;

  [key: string]: unknown;
}

/** /api/v1/status 返回数据（仅取资源相关字段） */
interface StatusData {
  cpu_percent?: number;
  memory_mb?: number;
  memory_total_mb?: number;
  disk_percent?: number;
  [key: string]: unknown;
}

/* ====== 工具函数 ====== */

/** 渲染 ASCII 仪表盘 */
function renderGauge(value: number, max: number, width: number = 20): string {
  const ratio = Math.min(1, Math.max(0, value / max));
  const filled = Math.round(ratio * width);
  return '▓'.repeat(filled) + '░'.repeat(width - filled);
}

/** 渲染 ASCII 柱状图 */
function renderBar(value: number, maxValue: number, width: number = 16): string {
  if (maxValue <= 0) return '░'.repeat(width);
  const ratio = Math.min(1, Math.max(0, value / maxValue));
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/** 延迟颜色 */
function latencyColor(avg: number): string {
  if (avg < 1) return 'var(--accent-green)';
  if (avg <= 3) return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

/** 格式化秒数 */
function fmtSec(val: number | null | undefined): string {
  if (val == null) return 'N/A';
  if (val < 0.01) return '<0.01s';
  return `${val.toFixed(2)}s`;
}

/* ====== 主组件 ====== */

export function Performance() {
  const { t } = useLanguage();
  const [perfData, setPerfData] = useState<PerfData | null>(null);
  const [statusData, setStatusData] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* —— 拉取性能数据 —— */
  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [perfRes, statusRes] = await Promise.allSettled([
        clawbotFetchJson<PerfData>('/api/v1/perf'),
        clawbotFetchJson<StatusData>('/api/v1/status'),
      ]);

      // 两个请求都失败时才算错误
      const perfOk = perfRes.status === 'fulfilled';
      const statusOk = statusRes.status === 'fulfilled';

      if (perfOk) setPerfData(perfRes.value);
      if (statusOk) setStatusData(statusRes.value);

      if (!perfOk && !statusOk) {
        setFetchError(t('performance.fetchError'));
      } else {
        setFetchError(null);
      }
    } catch (err) {
      console.error('[Performance] 数据加载失败:', err);
      setFetchError(t('performance.fetchError'));
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

  /* —— 加载态 —— */
  if (loading && !perfData) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
          <span className="font-mono text-sm" style={{ color: 'var(--text-tertiary)' }}>
            {t('performance.loading')}
          </span>
        </div>
      </div>
    );
  }

  /* —— 错误态（无任何数据时显示） —— */
  if (fetchError && !perfData && !statusData) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <AlertTriangle size={36} style={{ color: 'var(--accent-amber)' }} />
          <span className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
            {fetchError}
          </span>
          <button
            onClick={() => fetchAll()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors hover:opacity-80 font-mono text-xs"
            style={{ background: 'var(--bg-tertiary)', color: 'var(--accent-cyan)' }}
          >
            <RefreshCw size={12} />
            {t('performance.retry')}
          </button>
        </div>
      </div>
    );
  }

  /* —— 派生：资源仪表（优先从 perf 取，回退到 status） —— */
  const cpuVal = perfData?.cpu_percent ?? statusData?.cpu_percent ?? null;
  const memMb = perfData?.memory_mb ?? statusData?.memory_mb ?? null;
  const memMaxMb = perfData?.memory_total_mb ?? statusData?.memory_total_mb ?? 4096;
  const diskVal = perfData?.disk_percent ?? statusData?.disk_percent ?? null;

  const resources: ResourceGauge[] = [
    { label: t('performance.cpuUsage'), value: cpuVal, max: 100, unit: '%', color: 'var(--accent-cyan)' },
    {
      label: t('performance.memoryUsage'),
      value: memMb != null ? Math.round(memMb * 10) / 10 : null,
      max: Math.round(memMaxMb / 1024 * 10) / 10,
      unit: 'GB',
      color: 'var(--accent-green)',
    },
    { label: t('performance.diskUsage'), value: diskVal, max: 100, unit: '%', color: 'var(--accent-amber)' },
  ];

  /* —— 派生：延迟指标 —— */
  const latencyMetrics: LatencyMetric[] = perfData?.latency_metrics || perfData?.latency || [];

  /* —— 派生：吞吐量 —— */
  const throughputData: ThroughputPoint[] = perfData?.throughput || perfData?.throughput_data || [];
  const maxRpm = throughputData.length > 0 ? Math.max(...throughputData.map((d) => d.rpm)) : 1;

  /* —— 派生：错误统计 —— */
  const errorStats: ErrorStat[] = perfData?.error_stats || perfData?.errors || [];
  const totalErrorRate = perfData?.total_error_rate
    ?? (perfData?.error_rate != null ? `${perfData.error_rate}%` : null);

  /* —— 派生：吞吐趋势 —— */
  const throughputTrend = perfData?.throughput_trend || null;

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 资源仪表盘 (col-4 x3) ====== */}
        {resources.map((res) => (
          <motion.div key={res.label} className="col-span-12 md:col-span-4" variants={cardVariants}>
            <div className="abyss-card p-6 h-full flex flex-col">
              <span className="text-label" style={{ color: res.color }}>
                {res.label.toUpperCase().replace(' ', ' // ')}
              </span>

              {/* 大数字 */}
              <div className="flex items-end gap-2 mt-3">
                <span className="text-metric" style={{ fontSize: '32px', color: res.color }}>
                  {res.value != null ? res.value : 'N/A'}
                </span>
                {res.value != null && (
                  <span className="font-mono text-sm pb-1" style={{ color: 'var(--text-tertiary)' }}>
                    {res.unit}
                  </span>
                )}
              </div>

              {/* ASCII 仪表条 */}
              <div className="mt-3">
                <span
                  className="font-mono text-xs tracking-tight"
                  style={{ color: res.color, opacity: 0.85 }}
                >
                  {res.value != null ? renderGauge(res.value, res.max) : '░'.repeat(20)}
                </span>
              </div>

              <div className="flex justify-between mt-2">
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  0
                </span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  {res.max}{res.unit}
                </span>
              </div>
            </div>
          </motion.div>
        ))}

        {/* ====== API 延迟 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Gauge size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  API LATENCY
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('performance.apiLatencySubtitle')}
                </p>
              </div>
            </div>

            {latencyMetrics.length === 0 ? (
              <p className="font-mono text-xs py-8 text-center" style={{ color: 'var(--text-disabled)' }}>
                {t('performance.noLatencyData')}
              </p>
            ) : (
              <>
                {/* 表头 */}
                <div
                  className="grid grid-cols-6 gap-2 px-3 py-2 rounded-lg mb-1"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  {[t('performance.colMetric'), t('performance.colCalls'), t('performance.colAvg'), 'P50', 'P95', t('performance.colMax')].map((h) => (
                    <span
                      key={h}
                      className={clsx('text-label', h !== '指标' && 'text-right')}
                      style={{ fontSize: '10px' }}
                    >
                      {h}
                    </span>
                  ))}
                </div>

                {/* 数据行 */}
                <div className="flex-1 space-y-1">
                  {latencyMetrics.map((m) => (
                    <div
                      key={m.name}
                      className="grid grid-cols-6 gap-2 px-3 py-2.5 rounded-lg"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                        {m.name}
                      </span>
                      <span className="font-mono text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                        {m.count}
                      </span>
                      <span
                        className="font-mono text-xs text-right font-semibold"
                        style={{ color: latencyColor(m.avg) }}
                      >
                        {fmtSec(m.avg)}
                      </span>
                      <span className="font-mono text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                        {fmtSec(m.p50)}
                      </span>
                      <span className="font-mono text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                        {fmtSec(m.p95)}
                      </span>
                      <span className="font-mono text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                        {fmtSec(m.max)}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </motion.div>

        {/* ====== 错误率 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-red)' }}>
              ERROR RATE
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              错误统计
            </h3>

            {/* {t('performance.totalErrorRate')} */}
            <div className="flex items-end gap-2 mt-3 mb-5">
              <span className="text-metric" style={{ color: 'var(--accent-green)' }}>
                {totalErrorRate ?? 'N/A'}
              </span>
              <span className="font-mono text-xs pb-0.5" style={{ color: 'var(--text-tertiary)' }}>
                总错误率
              </span>
            </div>

            {/* 分类 */}
            <div className="flex-1 space-y-2">
              {errorStats.length === 0 && (
                <p className="font-mono text-xs py-4 text-center" style={{ color: 'var(--text-disabled)' }}>
                  {t('performance.noErrorData')}
                </p>
              )}
              {errorStats.map((err) => (
                <div
                  key={err.type}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={12} style={{ color: err.color || 'var(--accent-amber)' }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {err.type}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs font-semibold" style={{ color: err.color || 'var(--accent-amber)' }}>
                      {err.count}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {err.pct}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 请求吞吐量 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  REQUEST THROUGHPUT
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  请求吞吐量
                </h3>
              </div>
              {throughputTrend && (
                <div className="flex items-center gap-1.5">
                  <TrendingUp size={14} style={{ color: 'var(--accent-green)' }} />
                  <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-green)' }}>
                    {throughputTrend}
                  </span>
                </div>
              )}
            </div>

            {throughputData.length === 0 ? (
              <p className="font-mono text-xs py-8 text-center" style={{ color: 'var(--text-disabled)' }}>
                {t('performance.noThroughputData')}
              </p>
            ) : (
              <div className="space-y-1.5">
                {throughputData.map((d) => (
                  <div key={d.hour} className="flex items-center gap-3">
                    <span
                      className="font-mono text-xs w-10 shrink-0 text-right"
                      style={{ color: 'var(--text-disabled)' }}
                    >
                      {d.hour}:00
                    </span>
                    <span
                      className="font-mono text-xs flex-1 tracking-tight"
                      style={{
                        color: d.rpm === maxRpm ? 'var(--accent-green)' : 'var(--accent-cyan)',
                        opacity: 0.85,
                      }}
                    >
                      {renderBar(d.rpm, maxRpm, 40)}
                    </span>
                    <span
                      className="font-mono text-xs w-12 text-right shrink-0"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {d.rpm} rpm
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

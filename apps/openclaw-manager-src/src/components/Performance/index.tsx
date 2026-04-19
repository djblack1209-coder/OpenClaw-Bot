/**
 * Performance — 性能监控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import {
  Gauge,
  AlertTriangle,
  TrendingUp,
} from 'lucide-react';
import clsx from 'clsx';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 模拟数据 ====== */

/** 系统资源 */
interface ResourceGauge {
  label: string;
  value: number;
  max: number;
  unit: string;
  color: string;
}

const RESOURCES: ResourceGauge[] = [
  { label: 'CPU 使用率', value: 23, max: 100, unit: '%', color: 'var(--accent-cyan)' },
  { label: '内存占用', value: 1.4, max: 4.0, unit: 'GB', color: 'var(--accent-green)' },
  { label: '磁盘使用', value: 45, max: 100, unit: '%', color: 'var(--accent-amber)' },
];

/** API 延迟指标 */
interface LatencyMetric {
  name: string;
  avg: number;
  p50: number;
  p95: number;
  max: number;
  count: number;
}

const LATENCY_METRICS: LatencyMetric[] = [
  { name: '消息处理', avg: 0.85, p50: 0.72, p95: 2.10, max: 4.50, count: 1247 },
  { name: '大脑决策', avg: 1.20, p50: 1.05, p95: 3.40, max: 6.80, count: 892 },
  { name: 'LLM 调用', avg: 2.30, p50: 2.10, p95: 5.20, max: 12.00, count: 634 },
  { name: '交易周期', avg: 0.45, p50: 0.38, p95: 1.20, max: 2.80, count: 156 },
  { name: '记忆检索', avg: 0.15, p50: 0.12, p95: 0.35, max: 0.80, count: 423 },
];

/** 请求吞吐量 (每小时) */
const THROUGHPUT_DATA = [
  { hour: '00', rpm: 12 },
  { hour: '04', rpm: 5 },
  { hour: '08', rpm: 45 },
  { hour: '10', rpm: 120 },
  { hour: '12', rpm: 89 },
  { hour: '14', rpm: 156 },
  { hour: '16', rpm: 203 },
  { hour: '18', rpm: 178 },
  { hour: '20', rpm: 134 },
  { hour: '22', rpm: 67 },
];

/** 错误率数据 */
const ERROR_STATS = [
  { type: '超时 (>10s)', count: 12, pct: '0.96%', color: 'var(--accent-amber)' },
  { type: '5xx 错误', count: 3, pct: '0.24%', color: 'var(--accent-red)' },
  { type: 'LLM 限流', count: 7, pct: '1.10%', color: 'var(--accent-purple)' },
  { type: '连接失败', count: 2, pct: '0.16%', color: 'var(--text-disabled)' },
];

/* ====== 工具函数 ====== */

/** 渲染 ASCII 仪表盘 */
function renderGauge(value: number, max: number, width: number = 20): string {
  const ratio = value / max;
  const filled = Math.round(ratio * width);
  return '▓'.repeat(filled) + '░'.repeat(width - filled);
}

/** 渲染 ASCII 柱状图 */
function renderBar(value: number, maxValue: number, width: number = 16): string {
  const ratio = value / maxValue;
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
function fmtSec(val: number): string {
  if (val < 0.01) return '<0.01s';
  return `${val.toFixed(2)}s`;
}

/* ====== 主组件 ====== */

export function Performance() {
  const maxRpm = Math.max(...THROUGHPUT_DATA.map((d) => d.rpm));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 资源仪表盘 (col-4 x3) ====== */}
        {RESOURCES.map((res) => (
          <motion.div key={res.label} className="col-span-12 md:col-span-4" variants={cardVariants}>
            <div className="abyss-card p-6 h-full flex flex-col">
              <span className="text-label" style={{ color: res.color }}>
                {res.label.toUpperCase().replace(' ', ' // ')}
              </span>

              {/* 大数字 */}
              <div className="flex items-end gap-2 mt-3">
                <span className="text-metric" style={{ fontSize: '32px', color: res.color }}>
                  {res.value}
                </span>
                <span className="font-mono text-sm pb-1" style={{ color: 'var(--text-tertiary)' }}>
                  {res.unit}
                </span>
              </div>

              {/* ASCII 仪表条 */}
              <div className="mt-3">
                <span
                  className="font-mono text-xs tracking-tight"
                  style={{ color: res.color, opacity: 0.85 }}
                >
                  {renderGauge(res.value, res.max)}
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
                  接口延迟 // RESPONSE TIME METRICS
                </p>
              </div>
            </div>

            {/* 表头 */}
            <div
              className="grid grid-cols-6 gap-2 px-3 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              {['指标', '调用数', '平均', 'P50', 'P95', '最大'].map((h) => (
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
              {LATENCY_METRICS.map((m) => (
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

            {/* 总错误率 */}
            <div className="flex items-end gap-2 mt-3 mb-5">
              <span className="text-metric" style={{ color: 'var(--accent-green)' }}>
                1.5%
              </span>
              <span className="font-mono text-xs pb-0.5" style={{ color: 'var(--text-tertiary)' }}>
                总错误率
              </span>
            </div>

            {/* 分类 */}
            <div className="flex-1 space-y-2">
              {ERROR_STATS.map((err) => (
                <div
                  key={err.type}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={12} style={{ color: err.color }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {err.type}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs font-semibold" style={{ color: err.color }}>
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
              <div className="flex items-center gap-1.5">
                <TrendingUp size={14} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-green)' }}>
                  +12% vs 昨日
                </span>
              </div>
            </div>

            <div className="space-y-1.5">
              {THROUGHPUT_DATA.map((d) => (
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
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

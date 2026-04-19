/**
 * Scheduler — 任务调度中心 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Clock,
  Terminal,
} from 'lucide-react';

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

interface CronTask {
  name: string;
  cron: string;
  status: 'running' | 'paused' | 'failed';
  lastRun: string;
  nextRun: string;
  enabled: boolean;
}

const TASKS: CronTask[] = [
  { name: '每日简报推送', cron: '0 9 * * *', status: 'running', lastRun: '09:00:12', nextRun: '明天 09:00', enabled: true },
  { name: '社媒内容采集', cron: '*/30 * * * *', status: 'running', lastRun: '14:30:05', nextRun: '15:00:00', enabled: true },
  { name: '闲鱼商品刷新', cron: '0 */2 * * *', status: 'running', lastRun: '14:00:22', nextRun: '16:00:00', enabled: true },
  { name: '交易信号扫描', cron: '*/5 * * * *', status: 'running', lastRun: '14:45:01', nextRun: '14:50:00', enabled: true },
  { name: '数据库备份', cron: '0 3 * * *', status: 'paused', lastRun: '03:00:44', nextRun: '—', enabled: false },
  { name: '日志清理', cron: '0 4 * * 0', status: 'running', lastRun: '周日 04:00', nextRun: '下周日 04:00', enabled: true },
  { name: '模型健康检查', cron: '*/15 * * * *', status: 'failed', lastRun: '14:30:08', nextRun: '14:45:00', enabled: true },
  { name: '用户活跃度统计', cron: '0 0 * * *', status: 'running', lastRun: '00:00:33', nextRun: '明天 00:00', enabled: true },
];

const STATS = {
  total: TASKS.length,
  running: TASKS.filter((t) => t.status === 'running').length,
  paused: TASKS.filter((t) => t.status === 'paused').length,
  failed: TASKS.filter((t) => t.status === 'failed').length,
};

const METRICS = [
  { label: '今日执行', value: '156', color: 'var(--accent-cyan)' },
  { label: '成功率', value: '98.1%', color: 'var(--accent-green)' },
  { label: '平均耗时', value: '2.4s', color: 'var(--accent-amber)' },
  { label: '超时次数', value: '3', color: 'var(--accent-red)' },
];

const QUEUE = [
  { name: '交易信号扫描', time: '14:50:00' },
  { name: '社媒内容采集', time: '15:00:00' },
  { name: '模型健康检查', time: '15:00:00' },
  { name: '闲鱼商品刷新', time: '16:00:00' },
  { name: '用户活跃度统计', time: '明天 00:00' },
];

const LOGS = [
  { time: '14:45:01', msg: '[交易信号扫描] 执行完成 — 耗时 1.2s — 发现 3 个信号' },
  { time: '14:30:08', msg: '[模型健康检查] 执行失败 — DeepSeek V3 连接超时' },
  { time: '14:30:05', msg: '[社媒内容采集] 执行完成 — 采集 47 条内容' },
  { time: '14:00:22', msg: '[闲鱼商品刷新] 执行完成 — 刷新 12 个商品' },
  { time: '09:00:12', msg: '[每日简报推送] 执行完成 — 推送至 3 个渠道' },
  { time: '03:00:44', msg: '[数据库备份] 执行完成 — 备份大小 234MB' },
];

const RESOURCES = [
  { label: 'CPU 占用', value: '23%', ratio: 0.23 },
  { label: '内存占用', value: '61%', ratio: 0.61 },
  { label: '并发任务', value: '4/8', ratio: 0.5 },
  { label: '队列深度', value: '5', ratio: 0.25 },
];

/* ====== 工具函数 ====== */

function statusDot(status: CronTask['status']) {
  if (status === 'running') return 'var(--accent-green)';
  if (status === 'paused') return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

function renderBar(ratio: number, width: number = 16): string {
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Scheduler() {
  const [toggles, setToggles] = useState<Record<number, boolean>>(
    Object.fromEntries(TASKS.map((t, i) => [i, t.enabled])),
  );

  const toggle = (i: number) => setToggles((prev) => ({ ...prev, [i]: !prev[i] }));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 调度总览 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Clock size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  CRON ORCHESTRATOR
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  任务调度中心 // TASK SCHEDULER
                </p>
              </div>
            </div>

            {/* 统计栏 */}
            <div className="grid grid-cols-4 gap-3 mb-4">
              {[
                { label: '总任务', value: STATS.total, color: 'var(--accent-cyan)' },
                { label: '运行中', value: STATS.running, color: 'var(--accent-green)' },
                { label: '已暂停', value: STATS.paused, color: 'var(--accent-amber)' },
                { label: '已失败', value: STATS.failed, color: 'var(--accent-red)' },
              ].map((s) => (
                <div key={s.label} className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-secondary)' }}>
                  <span className="text-label">{s.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: s.color, fontSize: '20px' }}>{s.value}</p>
                </div>
              ))}
            </div>

            {/* 任务列表 */}
            <div className="flex-1 space-y-1.5 overflow-y-auto">
              {TASKS.map((task, i) => (
                <div
                  key={task.name}
                  className={clsx(
                    'flex items-center justify-between py-2.5 px-3 rounded-lg transition-colors',
                    !toggles[i] && 'opacity-40',
                  )}
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: statusDot(task.status) }}
                    />
                    <span className="font-display text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                      {task.name}
                    </span>
                    <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {task.cron}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div className="text-right hidden sm:block">
                      <span className="text-label">上次</span>
                      <p className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>{task.lastRun}</p>
                    </div>
                    <div className="text-right hidden sm:block">
                      <span className="text-label">下次</span>
                      <p className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>{task.nextRun}</p>
                    </div>
                    {/* 纯 div 开关 */}
                    <button
                      onClick={() => toggle(i)}
                      className="relative w-9 h-5 rounded-full transition-colors flex-shrink-0"
                      style={{
                        background: toggles[i] ? 'var(--accent-green)' : 'var(--bg-tertiary)',
                      }}
                    >
                      <span
                        className="absolute top-0.5 w-4 h-4 rounded-full transition-transform"
                        style={{
                          background: 'var(--text-primary)',
                          left: toggles[i] ? '18px' : '2px',
                        }}
                      />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 调度指标 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>METRICS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              调度指标
            </h3>
            <div className="space-y-4 flex-1">
              {METRICS.map((m) => (
                <div key={m.label}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-label">{m.label}</span>
                    <span className="text-metric" style={{ color: m.color, fontSize: '20px' }}>{m.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 执行队列 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>QUEUE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              执行队列
            </h3>
            <div className="flex-1 space-y-2">
              {QUEUE.map((q, i) => (
                <div
                  key={q.name}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      #{i + 1}
                    </span>
                    <span className="font-display text-sm" style={{ color: 'var(--text-primary)' }}>
                      {q.name}
                    </span>
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--accent-cyan)' }}>
                    {q.time}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 执行日志 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <Terminal size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>EXECUTION LOG</span>
            </div>
            <div
              className="flex-1 rounded-lg p-3 font-mono text-[11px] leading-relaxed space-y-1"
              style={{ background: 'var(--bg-primary)' }}
            >
              {LOGS.map((log, i) => (
                <div key={i} className="flex gap-2">
                  <span style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                  <span
                    style={{
                      color: log.msg.includes('失败')
                        ? 'var(--accent-red)'
                        : 'var(--accent-green)',
                    }}
                  >
                    {log.msg}
                  </span>
                </div>
              ))}
              <div className="flex items-center gap-1 mt-2">
                <span style={{ color: 'var(--accent-green)' }}>▊</span>
                <span className="animate-pulse" style={{ color: 'var(--text-disabled)' }}>_</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 资源使用 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>RESOURCES</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              资源使用
            </h3>
            <div className="flex-1 space-y-4">
              {RESOURCES.map((r) => (
                <div key={r.label}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-label">{r.label}</span>
                    <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {r.value}
                    </span>
                  </div>
                  <div className="font-mono text-[10px] leading-none" style={{ color: r.ratio > 0.5 ? 'var(--accent-amber)' : 'var(--accent-cyan)' }}>
                    {renderBar(r.ratio)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

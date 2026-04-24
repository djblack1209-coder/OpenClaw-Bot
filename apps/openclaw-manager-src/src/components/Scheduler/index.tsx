/**
 * Scheduler — 任务调度中心 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自真实后端 API
 */
import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { Clock, Terminal, Loader2 } from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { useLanguage } from '@/i18n';
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

interface SchedulerTask {
  id: string;
  name: string;
  cron: string;
  enabled: boolean;
  last_run?: string;
  next_run?: string;
  status?: 'running' | 'paused' | 'failed';
}

interface SchedulerData {
  enabled: boolean;
  maintenance_mode: boolean;
  tasks: SchedulerTask[];
}

/* ====== 工具函数 ====== */

/** 根据任务状态返回对应颜色 */
function statusDot(task: SchedulerTask): string {
  if (!task.enabled) return 'var(--accent-amber)';
  if (task.status === 'failed') return 'var(--accent-red)';
  return 'var(--accent-green)';
}

/** ASCII 进度条 */
function renderBar(ratio: number, width: number = 16): string {
  const filled = Math.round(Math.min(1, Math.max(0, ratio)) * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Scheduler() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<SchedulerData | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const { t } = useLanguage();

  /* —— 拉取调度器数据 —— */
  const fetchData = useCallback(async () => {
    try {
      const res = await clawbotFetchJson<SchedulerData>('/api/v1/controls/scheduler');
      setData(res);
    } catch (err) {
      console.error('[Scheduler] 加载失败:', err);
      toast.error(t('scheduler.loadFailed'), { channel: 'notification' });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { fetchData(); }, [fetchData]);

  /* —— 切换任务启用/禁用 —— */
  const toggleTask = async (taskId: string) => {
    setTogglingId(taskId);
    try {
      await clawbotFetchJson(`/api/v1/controls/scheduler/task/${taskId}/toggle`, { method: 'POST' });
      /* 乐观更新 */
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          tasks: prev.tasks.map((t) =>
            t.id === taskId ? { ...t, enabled: !t.enabled } : t,
          ),
        };
      });
    } catch (err) {
      console.error('[Scheduler] 切换失败:', err);
      toast.error(t('scheduler.toggleFailed'), { channel: 'notification' });
    } finally {
      setTogglingId(null);
    }
  };

  /* —— 加载态 —— */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      </div>
    );
  }

  const tasks = data?.tasks ?? [];
  const totalCount = tasks.length;
  const runningCount = tasks.filter((t) => t.enabled && t.status !== 'failed').length;
  const pausedCount = tasks.filter((t) => !t.enabled).length;
  const failedCount = tasks.filter((t) => t.status === 'failed').length;

  /* 构建执行队列：已启用任务按 next_run 排序 */
  const queue = tasks
    .filter((t) => t.enabled && t.next_run)
    .sort((a, b) => (a.next_run ?? '').localeCompare(b.next_run ?? ''))
    .slice(0, 5);

  /* 简易指标 */
  const metrics = [
    { label: t('scheduler.totalTasks'), value: String(totalCount), color: 'var(--accent-cyan)' },
    { label: t('scheduler.running'), value: String(runningCount), color: 'var(--accent-green)' },
    { label: t('scheduler.paused'), value: String(pausedCount), color: 'var(--accent-amber)' },
    { label: t('scheduler.failed'), value: String(failedCount), color: 'var(--accent-red)' },
  ];

  /* 资源指标占位（可接入 perfMetrics） */
  const resources = [
    { label: t('scheduler.concurrentTasks'), value: `${runningCount}/${totalCount}`, ratio: totalCount > 0 ? runningCount / totalCount : 0 },
    { label: t('scheduler.schedulerLabel'), value: data?.enabled ? t('scheduler.statusRunning') : t('scheduler.statusStopped'), ratio: data?.enabled ? 1 : 0 },
    { label: t('scheduler.maintenanceMode'), value: data?.maintenance_mode ? t('scheduler.modeOn') : t('scheduler.modeOff'), ratio: data?.maintenance_mode ? 1 : 0 },
  ];

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
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}>
                <Clock size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  CRON ORCHESTRATOR
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('scheduler.subtitle')}
                </p>
              </div>
            </div>

            {/* 统计栏 */}
            <div className="grid grid-cols-4 gap-3 mb-4">
              {metrics.map((s) => (
                <div key={s.label} className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-secondary)' }}>
                  <span className="text-label">{s.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: s.color, fontSize: '20px' }}>{s.value}</p>
                </div>
              ))}
            </div>

            {/* 任务列表 */}
            <div className="flex-1 space-y-1.5 overflow-y-auto">
              {tasks.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('scheduler.noTasks')}
                </div>
              )}
              {tasks.map((task) => {
                const isEnabled = task.enabled;
                return (
                  <div key={task.id}
                    className={clsx(
                      'flex items-center justify-between py-2.5 px-3 rounded-lg transition-colors',
                      !isEnabled && 'opacity-40',
                    )}
                    style={{ background: 'var(--bg-secondary)' }}>
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <span className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: statusDot(task) }} />
                      <span className="font-display text-sm font-semibold truncate"
                        style={{ color: 'var(--text-primary)' }}>
                        {task.name}
                      </span>
                      <span className="font-mono text-[10px] flex-shrink-0"
                        style={{ color: 'var(--text-disabled)' }}>
                        {task.cron}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 flex-shrink-0">
                      {task.last_run && (
                        <div className="text-right hidden sm:block">
                          <span className="text-label">{t('scheduler.lastRun')}</span>
                          <p className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                            {task.last_run}
                          </p>
                        </div>
                      )}
                      {task.next_run && (
                        <div className="text-right hidden sm:block">
                          <span className="text-label">{t('scheduler.nextRun')}</span>
                          <p className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                            {task.next_run}
                          </p>
                        </div>
                      )}
                      <button
                        onClick={() => toggleTask(task.id)}
                        disabled={togglingId === task.id}
                        className="relative w-9 h-5 rounded-full transition-colors flex-shrink-0"
                        style={{
                          background: isEnabled ? 'var(--accent-green)' : 'var(--bg-tertiary)',
                          opacity: togglingId === task.id ? 0.5 : 1,
                        }}>
                        <span className="absolute top-0.5 w-4 h-4 rounded-full transition-transform"
                          style={{
                            background: 'var(--text-primary)',
                            left: isEnabled ? '18px' : '2px',
                          }} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 执行队列 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>QUEUE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('scheduler.executionQueue')}
            </h3>
            <div className="flex-1 space-y-2">
              {queue.length === 0 && (
                <div className="font-mono text-xs py-4 text-center" style={{ color: 'var(--text-disabled)' }}>
                  {t('scheduler.queueEmpty')}
                </div>
              )}
              {queue.map((q, i) => (
                <div key={q.id}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      #{i + 1}
                    </span>
                    <span className="font-display text-sm" style={{ color: 'var(--text-primary)' }}>
                      {q.name}
                    </span>
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--accent-cyan)' }}>
                    {q.next_run}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 调度器状态 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>SCHEDULER STATUS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('scheduler.schedulerStatus')}
            </h3>
            <div className="flex-1 space-y-4">
              {resources.map((r) => (
                <div key={r.label}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-label">{r.label}</span>
                    <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {r.value}
                    </span>
                  </div>
                  <div className="font-mono text-[10px] leading-none"
                    style={{ color: r.ratio > 0.5 ? 'var(--accent-amber)' : 'var(--accent-cyan)' }}>
                    {renderBar(r.ratio)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Cron 表达式说明 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <Terminal size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>CRON REFERENCE</span>
            </div>
            <div className="flex-1 rounded-lg p-3 font-mono text-[11px] leading-relaxed space-y-1"
              style={{ background: 'var(--bg-primary)' }}>
              {tasks.slice(0, 6).map((task) => (
                <div key={task.id} className="flex gap-2">
                  <span style={{ color: 'var(--accent-cyan)' }}>{task.cron.padEnd(16)}</span>
                  <span style={{ color: task.enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                    {task.name} — {task.enabled ? t('scheduler.enabled') : t('scheduler.disabled')}
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
      </motion.div>
    </div>
  );
}

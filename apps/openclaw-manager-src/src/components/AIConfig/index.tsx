/**
 * AIConfig — AI 模型配置 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Cpu,
  Zap,
  DollarSign,
  BarChart3,
  Terminal,
  CheckCircle2,
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

interface Model {
  name: string;
  provider: string;
  status: 'online' | 'offline' | 'degraded';
  latency: string;
  callsToday: number;
  cost: string;
}

const MODELS: Model[] = [
  { name: 'GPT-4o', provider: 'OpenAI', status: 'online', latency: '320ms', callsToday: 2847, cost: '$4.20' },
  { name: 'Claude 3.5 Sonnet', provider: 'Anthropic', status: 'online', latency: '450ms', callsToday: 1256, cost: '$3.80' },
  { name: 'DeepSeek V3', provider: 'DeepSeek', status: 'degraded', latency: '890ms', callsToday: 3421, cost: '$0.60' },
  { name: 'Qwen 72B', provider: 'SiliconFlow', status: 'online', latency: '280ms', callsToday: 1890, cost: '$1.20' },
  { name: 'Gemini 2.0', provider: 'Google', status: 'online', latency: '210ms', callsToday: 956, cost: '$1.80' },
  { name: 'Llama 3.1', provider: 'Groq', status: 'offline', latency: '—', callsToday: 0, cost: '$0.00' },
];

const STRATEGIES = ['智能路由', '成本优先', '质量优先', '速度优先'];

const COST_STATS = [
  { label: '今日费用', value: '$12.40', color: 'var(--accent-cyan)' },
  { label: '本周', value: '$68.20', color: 'var(--accent-green)' },
  { label: '本月', value: '$245.80', color: 'var(--accent-amber)' },
  { label: '预算', value: '$500', color: 'var(--text-disabled)' },
];

interface PerfBar { name: string; ms: number; color: string }
const PERF_BARS: PerfBar[] = [
  { name: 'Gemini 2.0', ms: 210, color: 'var(--accent-green)' },
  { name: 'Qwen 72B', ms: 280, color: 'var(--accent-green)' },
  { name: 'GPT-4o', ms: 320, color: 'var(--accent-cyan)' },
  { name: 'Claude 3.5', ms: 450, color: 'var(--accent-amber)' },
  { name: 'DeepSeek V3', ms: 890, color: 'var(--accent-red)' },
];

const CALL_LOGS = [
  { time: '14:48:22', model: 'GPT-4o', duration: '1.2s', tokens: 847 },
  { time: '14:47:55', model: 'DeepSeek V3', duration: '3.4s', tokens: 2100 },
  { time: '14:47:30', model: 'Qwen 72B', duration: '0.8s', tokens: 560 },
  { time: '14:46:12', model: 'Claude 3.5', duration: '2.1s', tokens: 1340 },
  { time: '14:45:58', model: 'Gemini 2.0', duration: '0.6s', tokens: 420 },
];

/* ====== 工具函数 ====== */

function statusDot(status: Model['status']) {
  if (status === 'online') return 'var(--accent-green)';
  if (status === 'degraded') return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

function statusLabel(status: Model['status']) {
  if (status === 'online') return '在线';
  if (status === 'degraded') return '降级';
  return '离线';
}

function renderBar(value: number, max: number, width: number = 20): string {
  const ratio = value / max;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function AIConfig() {
  const [strategy, setStrategy] = useState('智能路由');
  const maxMs = Math.max(...PERF_BARS.map((p) => p.ms));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 模型池总览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Cpu size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  LLM ROUTER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  AI 模型配置 // MODEL POOL
                </p>
              </div>
            </div>

            {/* 模型表头 */}
            <div
              className="grid gap-2 px-3 py-1.5 mb-1 font-mono text-[9px] tracking-wider"
              style={{ gridTemplateColumns: '2fr 1fr 60px 70px 80px 60px', color: 'var(--text-disabled)' }}
            >
              <span>模型</span>
              <span>提供商</span>
              <span>状态</span>
              <span>延迟</span>
              <span>今日调用</span>
              <span className="text-right">费用</span>
            </div>

            {/* 模型列表 */}
            <div className="flex-1 space-y-1.5">
              {MODELS.map((m) => (
                <div
                  key={m.name}
                  className={clsx(
                    'grid gap-2 items-center px-3 py-2.5 rounded-lg transition-colors',
                    m.status === 'offline' && 'opacity-40',
                  )}
                  style={{ gridTemplateColumns: '2fr 1fr 60px 70px 80px 60px', background: 'var(--bg-secondary)' }}
                >
                  <span className="font-display text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                    {m.name}
                  </span>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {m.provider}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: statusDot(m.status) }} />
                    <span className="font-mono text-[10px]" style={{ color: statusDot(m.status) }}>
                      {statusLabel(m.status)}
                    </span>
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                    {m.latency}
                  </span>
                  <span className="font-mono text-[11px] font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {m.callsToday.toLocaleString()}
                  </span>
                  <span className="font-mono text-[11px] text-right" style={{ color: 'var(--accent-green)' }}>
                    {m.cost}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 路由策略 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>STRATEGY</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              路由策略
            </h3>
            <div className="flex-1 space-y-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  onClick={() => setStrategy(s)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all text-left',
                  )}
                  style={{
                    background: strategy === s ? 'rgba(6,182,212,0.12)' : 'var(--bg-secondary)',
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: strategy === s ? 'var(--accent-cyan)' : 'transparent',
                  }}
                >
                  <div
                    className="w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                    style={{
                      borderColor: strategy === s ? 'var(--accent-cyan)' : 'var(--text-disabled)',
                    }}
                  >
                    {strategy === s && (
                      <div className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-cyan)' }} />
                    )}
                  </div>
                  <span
                    className="font-display text-sm font-semibold"
                    style={{ color: strategy === s ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}
                  >
                    {s}
                  </span>
                </button>
              ))}
            </div>
            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              当前: {strategy} — 根据任务类型自动选择最优模型
            </p>
          </div>
        </motion.div>

        {/* ====== 费用统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>COST</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              费用统计
            </h3>
            <div className="space-y-4 flex-1">
              {COST_STATS.map((c) => (
                <div key={c.label}>
                  <span className="text-label">{c.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: c.color, fontSize: '22px' }}>{c.value}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-primary)' }}>
              <div className="flex items-center justify-between">
                <span className="text-label">预算使用</span>
                <span className="font-mono text-[11px]" style={{ color: 'var(--accent-amber)' }}>49.2%</span>
              </div>
              <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--accent-amber)' }}>
                {renderBar(0.492, 1)}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 模型性能对比 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>PERFORMANCE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              响应时间对比
            </h3>
            <div className="flex-1 space-y-3">
              {PERF_BARS.map((p) => (
                <div key={p.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-display text-xs" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
                    <span className="font-mono text-[10px]" style={{ color: p.color }}>{p.ms}ms</span>
                  </div>
                  <div className="font-mono text-[10px] leading-none" style={{ color: p.color }}>
                    {renderBar(p.ms, maxMs)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 调用日志 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <Terminal size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>CALL LOG</span>
            </div>
            <div className="flex-1 space-y-2">
              {CALL_LOGS.map((log, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                    <p className="font-display text-xs font-semibold mt-0.5" style={{ color: 'var(--text-primary)' }}>
                      {log.model}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>{log.duration}</span>
                    <p className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                      {log.tokens} tok
                    </p>
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

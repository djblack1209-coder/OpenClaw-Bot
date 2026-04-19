import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  GitBranch,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Timer,
  Layers,
  ListChecks,
  Terminal,
  Cpu,
  ArrowRight,
  Circle,
  Zap,
} from 'lucide-react';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== DAG 节点类型定义 ====== */
interface DagNode {
  id: string;
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface Pipeline {
  name: string;
  status: '运行中' | '排队' | '已完成';
  startTime: string;
  progress: string;
  elapsed: string;
}

interface CompletedTask {
  name: string;
  duration: string;
  result: '成功' | '失败';
  time: string;
}

interface LogEntry {
  time: string;
  level: 'INFO' | 'OK' | 'WARN' | 'ERROR';
  message: string;
}

interface ModelStat {
  name: string;
  count: number;
  color: string;
}

/* ====== 模拟数据 ====== */

// DAG 流水线节点
const dagNodes: DagNode[] = [
  { id: 'intent',  label: '意图解析', status: 'done' },
  { id: 'scan',    label: '市场扫描', status: 'done' },
  { id: 'risk',    label: '风险评估', status: 'done' },
  { id: 'vote',    label: 'Bot 投票', status: 'running' },
  { id: 'execute', label: '订单执行', status: 'pending' },
  { id: 'track',   label: '回报追踪', status: 'pending' },
];

// 引擎指标
const engineMetrics = [
  { label: '今日任务数', value: '47',    accent: 'var(--accent-cyan)' },
  { label: '成功率',     value: '94.2%', accent: 'var(--accent-green)' },
  { label: '平均耗时',   value: '3.1s',  accent: 'var(--accent-amber)' },
  { label: '活跃管道',   value: '3',     accent: 'var(--accent-purple)' },
  { label: '排队任务',   value: '2',     accent: 'var(--text-secondary)' },
  { label: '失败任务',   value: '3',     accent: 'var(--accent-red)' },
];

// 活跃管道
const activePipelines: Pipeline[] = [
  { name: 'AAPL 投资分析',     status: '运行中', startTime: '14:32:01', progress: '4/6', elapsed: '2.3s' },
  { name: '闲鱼客服自动回复',   status: '运行中', startTime: '14:30:15', progress: '3/5', elapsed: '5.8s' },
  { name: '社媒热点追踪',       status: '排队',   startTime: '14:35:00', progress: '0/4', elapsed: '—' },
];

// 最近完成
const completedTasks: CompletedTask[] = [
  { name: 'BTC 趋势分析',     duration: '4.2s', result: '成功', time: '14:28:33' },
  { name: 'ETH 风险评估',     duration: '2.8s', result: '成功', time: '14:25:10' },
  { name: '小红书发帖调度',   duration: '1.5s', result: '成功', time: '14:22:45' },
  { name: 'TSLA 情绪分析',    duration: '6.1s', result: '失败', time: '14:20:02' },
  { name: '闲鱼自动议价',     duration: '3.3s', result: '成功', time: '14:18:30' },
];

// 执行日志
const logEntries: LogEntry[] = [
  { time: '14:32:05', level: 'INFO', message: '[DAG] 节点「意图解析」完成 → 输出: buy_signal(AAPL)' },
  { time: '14:32:04', level: 'OK',   message: '[LLM] GPT-4o 返回市场扫描结果, 耗时 0.8s' },
  { time: '14:32:03', level: 'INFO', message: '[DAG] 节点「市场扫描」启动 → 模型: DeepSeek-V3' },
  { time: '14:32:02', level: 'WARN', message: '[RISK] AAPL 波动率偏高 (σ=2.4), 建议减仓 15%' },
  { time: '14:32:01', level: 'OK',   message: '[DAG] 节点「风险评估」完成 → 风险等级: 中' },
  { time: '14:32:00', level: 'INFO', message: '[VOTE] 7-Bot 投票启动: 已收到 4/7 票' },
  { time: '14:31:58', level: 'ERROR', message: '[LLM] Qwen 调用超时 (>5s), 自动切换 GPT-4o' },
  { time: '14:31:55', level: 'INFO', message: '[DAG] 管道「AAPL 投资分析」初始化完成' },
];

// 模型调用统计
const modelStats: ModelStat[] = [
  { name: 'GPT-4o',   count: 23, color: 'var(--accent-cyan)' },
  { name: 'DeepSeek', count: 15, color: 'var(--accent-green)' },
  { name: 'Qwen',     count: 12, color: 'var(--accent-amber)' },
  { name: 'Claude',   count: 8,  color: 'var(--accent-purple)' },
];

const maxModelCount = Math.max(...modelStats.map((m) => m.count));

/* ====== DAG 节点颜色映射 ====== */
function nodeStyle(status: DagNode['status']) {
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
function StatusIcon({ status }: { status: DagNode['status'] }) {
  const size = 12;
  switch (status) {
    case 'done':
      return <CheckCircle2 size={size} style={{ color: 'var(--accent-green)' }} />;
    case 'running':
      return (
        <motion.span
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.2, repeat: Infinity }}
          className="inline-flex"
        >
          <Circle size={size} fill="var(--accent-amber)" style={{ color: 'var(--accent-amber)' }} />
        </motion.span>
      );
    case 'pending':
      return <Circle size={size} style={{ color: 'var(--text-tertiary)' }} />;
  }
}

/* 状态文本 */
function statusLabel(status: DagNode['status']) {
  switch (status) {
    case 'done': return '完成';
    case 'running': return '运行中';
    case 'pending': return '待执行';
  }
}

/* 日志级别颜色 */
function logColor(level: LogEntry['level']) {
  switch (level) {
    case 'OK':    return 'var(--accent-green)';
    case 'WARN':  return 'var(--accent-amber)';
    case 'ERROR': return 'var(--accent-red)';
    default:      return 'var(--text-secondary)';
  }
}

/**
 * 智能流监控 — Sonic Abyss DAG 引擎可视化
 * 12 列 Bento Grid，玻璃卡片 + 终端美学
 */
export function ExecutionFlow() {
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
            {/* 标题行 */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                DAG EXECUTOR
              </span>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{ background: 'var(--accent-green)' }}
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  LIVE
                </span>
              </div>
            </div>
            <h2
              className="font-display text-xl font-bold"
              style={{ color: 'var(--text-primary)' }}
            >
              智能流引擎 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// DAG EXECUTOR</span>
            </h2>

            {/* === DAG 流水线可视化 === */}
            <div className="flex-1 flex items-center justify-center mt-6 mb-4">
              <div className="flex items-center gap-0 w-full max-w-[720px]">
                {dagNodes.map((node, i) => {
                  const style = nodeStyle(node.status);
                  return (
                    <div key={node.id} className="flex items-center" style={{ flex: 1 }}>
                      {/* 节点 */}
                      <motion.div
                        className="relative flex flex-col items-center justify-center rounded-xl px-3 py-3 w-full min-w-[90px]"
                        style={{
                          border: `1px solid ${style.border}`,
                          background: style.bg,
                          boxShadow: style.glow,
                        }}
                        initial={{ scale: 0.85, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: i * 0.08, duration: 0.3 }}
                      >
                        <StatusIcon status={node.status} />
                        <span
                          className="font-mono text-[11px] font-semibold mt-1.5 text-center leading-tight"
                          style={{ color: style.text }}
                        >
                          {node.label}
                        </span>
                        <span
                          className="font-mono text-[9px] mt-0.5"
                          style={{ color: 'var(--text-tertiary)' }}
                        >
                          {statusLabel(node.status)}
                        </span>
                      </motion.div>

                      {/* 连接箭头（最后一个节点后无箭头） */}
                      {i < dagNodes.length - 1 && (
                        <div className="flex items-center px-1 shrink-0">
                          <motion.div
                            initial={{ scaleX: 0 }}
                            animate={{ scaleX: 1 }}
                            transition={{ delay: i * 0.08 + 0.15, duration: 0.25 }}
                            style={{ transformOrigin: 'left' }}
                          >
                            <ArrowRight
                              size={14}
                              style={{
                                color: node.status === 'done' && dagNodes[i + 1].status !== 'pending'
                                  ? 'var(--accent-green)'
                                  : 'var(--text-tertiary)',
                              }}
                            />
                          </motion.div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 当前任务信息 */}
            <div
              className="rounded-lg px-4 py-3 flex items-center gap-6 font-mono text-xs"
              style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid var(--glass-border)',
              }}
            >
              <div className="flex items-center gap-2">
                <Zap size={13} style={{ color: 'var(--accent-amber)' }} />
                <span style={{ color: 'var(--text-secondary)' }}>正在执行:</span>
                <span style={{ color: 'var(--text-primary)' }}>分析 AAPL 技术面</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Timer size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span style={{ color: 'var(--accent-cyan)' }}>2.3s</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Cpu size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span style={{ color: 'var(--accent-purple)' }}>GPT-4o</span>
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
              引擎指标
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {engineMetrics.map((m) => (
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
              活跃管道
            </h3>
            <div className="space-y-3">
              {activePipelines.map((p, i) => (
                <motion.div
                  key={p.name}
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
                      {p.name}
                    </span>
                    <span
                      className={clsx(
                        'px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wider',
                        p.status === '运行中'
                          ? 'bg-[var(--accent-green)]/10 text-[var(--accent-green)]'
                          : 'bg-[var(--text-tertiary)]/10 text-[var(--text-tertiary)]'
                      )}
                      style={{
                        background: p.status === '运行中' ? 'rgba(0,255,170,0.1)' : 'rgba(255,255,255,0.05)',
                        color: p.status === '运行中' ? 'var(--accent-green)' : 'var(--text-tertiary)',
                      }}
                    >
                      {p.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    <span><Clock size={10} className="inline mr-1" />{p.startTime}</span>
                    <span><GitBranch size={10} className="inline mr-1" />{p.progress} 节点</span>
                    <span><Timer size={10} className="inline mr-1" />{p.elapsed}</span>
                  </div>
                </motion.div>
              ))}
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
              最近完成
            </h3>
            <div className="space-y-2">
              {completedTasks.map((t, i) => (
                <motion.div
                  key={t.name + t.time}
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
                    {t.result === '成功' ? (
                      <CheckCircle2 size={13} style={{ color: 'var(--accent-green)' }} />
                    ) : (
                      <XCircle size={13} style={{ color: 'var(--accent-red)' }} />
                    )}
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {t.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    <span>{t.duration}</span>
                    <span
                      style={{
                        color: t.result === '成功' ? 'var(--accent-green)' : 'var(--accent-red)',
                      }}
                    >
                      {t.result}
                    </span>
                    <span>{t.time}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3: 执行日志 (span-8) + 模型调用统计 (span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
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
                  实时
                </span>
              </div>
            </div>

            {/* 日志内容 */}
            <div className="px-5 py-4 space-y-1 font-mono text-[11px] leading-relaxed max-h-[280px] overflow-y-auto">
              {logEntries.map((log, i) => (
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
              ))}
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

        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Cpu size={14} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                LLM USAGE
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mb-5" style={{ color: 'var(--text-primary)' }}>
              模型调用统计
            </h3>
            <div className="space-y-4">
              {modelStats.map((m, i) => (
                <motion.div
                  key={m.name}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 + i * 0.08 }}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {m.name}
                    </span>
                    <span className="font-mono text-xs font-semibold" style={{ color: m.color }}>
                      {m.count}次
                    </span>
                  </div>
                  <div
                    className="h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'rgba(255,255,255,0.04)' }}
                  >
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: m.color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${(m.count / maxModelCount) * 100}%` }}
                      transition={{ delay: 0.6 + i * 0.08, duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                </motion.div>
              ))}
            </div>

            {/* 总计 */}
            <div
              className="mt-6 pt-4 flex items-center justify-between font-mono text-xs"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <span style={{ color: 'var(--text-tertiary)' }}>总调用</span>
              <span className="text-metric text-base" style={{ color: 'var(--accent-cyan)' }}>
                {modelStats.reduce((a, b) => a + b.count, 0)}
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

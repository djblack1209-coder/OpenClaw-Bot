/**
 * Dashboard — 系统概览页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 * 保持原有 props 接口: envStatus + onSetupComplete
 */
import { motion } from 'framer-motion';
import {
  Activity,
  Server,
  Cpu,
  MessageSquare,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Terminal,
} from 'lucide-react';
import clsx from 'clsx';
import { EnvironmentStatus } from '../../App';

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

/** 服务列表 */
interface ServiceItem {
  name: string;
  label: string;
  status: 'running' | 'stopped' | 'error';
  uptime: string;
  memory: string;
}

const SERVICES: ServiceItem[] = [
  { name: 'ClawBot Core', label: '核心引擎', status: 'running', uptime: '3d 12h', memory: '256MB' },
  { name: 'Telegram Bot', label: 'TG 机器人', status: 'running', uptime: '3d 12h', memory: '128MB' },
  { name: 'Trading Engine', label: '交易引擎', status: 'running', uptime: '2d 8h', memory: '512MB' },
  { name: 'Memory Engine', label: '记忆引擎', status: 'running', uptime: '3d 12h', memory: '384MB' },
  { name: 'Xianyu Agent', label: '闲鱼客服', status: 'stopped', uptime: '—', memory: '—' },
  { name: 'News Monitor', label: '新闻监控', status: 'error', uptime: '1h 23m', memory: '96MB' },
];

/** 快捷统计 */
const QUICK_STATS = [
  { label: '今日消息', value: '1,247', color: 'var(--accent-cyan)' },
  { label: '活跃用户', value: '38', color: 'var(--accent-green)' },
  { label: 'LLM 调用', value: '892', color: 'var(--accent-purple)' },
  { label: '平均响应', value: '1.2s', color: 'var(--accent-amber)' },
];

/** 最近日志 */
const RECENT_LOGS = [
  { level: 'info', time: '14:32:05', msg: '[TelegramBot] 消息处理完成 user=12345' },
  { level: 'info', time: '14:31:58', msg: '[Trading] NVDA 买入信号触发 price=$875.30' },
  { level: 'warn', time: '14:31:42', msg: '[NewsMonitor] RSS 源超时 source=reuters' },
  { level: 'error', time: '14:30:15', msg: '[NewsMonitor] 连接断开 retrying in 30s' },
  { level: 'info', time: '14:29:50', msg: '[Memory] 记忆提取完成 entries=3 user=admin' },
  { level: 'info', time: '14:28:33', msg: '[ClawBot] 健康检查通过 services=4/6' },
];

/* ====== 工具函数 ====== */

/** 服务状态图标和颜色 */
function statusIcon(status: ServiceItem['status']) {
  switch (status) {
    case 'running':
      return { Icon: CheckCircle2, color: 'var(--accent-green)', label: '运行中' };
    case 'stopped':
      return { Icon: XCircle, color: 'var(--text-disabled)', label: '已停止' };
    case 'error':
      return { Icon: AlertTriangle, color: 'var(--accent-red)', label: '异常' };
  }
}

/** 日志级别颜色 */
function logColor(level: string): string {
  if (level === 'error') return 'var(--accent-red)';
  if (level === 'warn') return 'var(--accent-amber)';
  return 'var(--accent-green)';
}

/* ====== 接口定义 ====== */
interface DashboardProps {
  envStatus: EnvironmentStatus | null;
  onSetupComplete: () => void;
}

/* ====== 主组件 ====== */

export function Dashboard({ envStatus: _envStatus, onSetupComplete: _onSetupComplete }: DashboardProps) {
  const runningCount = SERVICES.filter((s) => s.status === 'running').length;

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
                  系统概览 // {runningCount}/{SERVICES.length} SERVICES ONLINE
                </p>
              </div>
            </div>

            {/* 快捷统计 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {QUICK_STATS.map((s) => (
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
              {[
                { icon: Cpu, label: 'CPU', value: '23%' },
                { icon: Server, label: '内存', value: '1.4GB' },
                { icon: Clock, label: '运行时间', value: '3d 12h' },
                { icon: Zap, label: 'API 健康', value: '98.5%' },
              ].map((m) => (
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
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              服务矩阵
            </h3>

            <div className="flex-1 space-y-1.5">
              {SERVICES.map((svc) => {
                const si = statusIcon(svc.status);
                return (
                  <div
                    key={svc.name}
                    className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-2.5">
                      <si.Icon size={14} style={{ color: si.color }} />
                      <div>
                        <p className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                          {svc.label}
                        </p>
                        <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {svc.name}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p
                        className="font-mono text-[10px] font-semibold"
                        style={{ color: si.color }}
                      >
                        {si.label}
                      </p>
                      <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {svc.uptime}
                      </p>
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
                最近 {RECENT_LOGS.length} 条
              </span>
            </div>
            <div className="p-4 space-y-0.5 font-mono text-xs" style={{ background: 'var(--bg-elevated)' }}>
              {RECENT_LOGS.map((log, i) => (
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
                  <span style={{ color: 'var(--text-secondary)' }}>{log.msg}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

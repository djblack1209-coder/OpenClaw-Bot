/**
 * Plugins — MCP 插件管理页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Blocks, Wifi, WifiOff, Power,
  Terminal, Radio,
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

/** 插件信息 */
interface Plugin {
  name: string;
  version: string;
  status: 'running' | 'stopped';
  protocol: 'stdio' | 'sse' | 'ws';
}

const PLUGINS: Plugin[] = [
  { name: '@mcp/server-filesystem', version: '1.2.0', status: 'running', protocol: 'stdio' },
  { name: '@mcp/server-github', version: '0.9.3', status: 'running', protocol: 'stdio' },
  { name: '@mcp/server-sqlite', version: '2.0.1', status: 'running', protocol: 'stdio' },
  { name: 'browser-use-mcp', version: '0.4.7', status: 'running', protocol: 'sse' },
  { name: 'crawl4ai-server', version: '1.1.0', status: 'stopped', protocol: 'sse' },
  { name: 'custom-memory-mcp', version: '0.2.0', status: 'stopped', protocol: 'ws' },
];

/** 协议状态 */
interface ProtocolStatus {
  name: string;
  label: string;
  connections: number;
  status: 'active' | 'idle';
  color: string;
}

const PROTOCOLS: ProtocolStatus[] = [
  { name: 'MCP / stdio', label: 'STDIO', connections: 3, status: 'active', color: 'var(--accent-green)' },
  { name: 'MCP / SSE', label: 'SSE', connections: 1, status: 'active', color: 'var(--accent-cyan)' },
  { name: 'WebSocket', label: 'WS', connections: 0, status: 'idle', color: 'var(--text-disabled)' },
];

/** 最近事件日志 */
const LOGS = [
  { ts: '14:28:05', msg: '[PLUGIN] server-filesystem 重连成功 — PID 42851' },
  { ts: '13:45:12', msg: '[PLUGIN] browser-use-mcp SSE 心跳正常 — 延迟 23ms' },
  { ts: '12:30:00', msg: '[PLUGIN] crawl4ai-server 已停用 — 手动关闭' },
  { ts: '11:15:33', msg: '[PLUGIN] server-github 接收 12 个工具调用' },
  { ts: '09:00:01', msg: '[SYSTEM] 插件守护进程启动 — 监控 6 个实例' },
];

/* ====== 工具函数 ====== */

/** 协议标签颜色 */
function protocolColor(p: string) {
  if (p === 'stdio') return 'var(--accent-green)';
  if (p === 'sse') return 'var(--accent-cyan)';
  return 'var(--accent-purple)';
}

/* ====== 主组件 ====== */

export function Plugins() {
  const running = PLUGINS.filter((p) => p.status === 'running').length;
  const stopped = PLUGINS.filter((p) => p.status === 'stopped').length;

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 插件列表 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(167,139,250,0.12)' }}
              >
                <Blocks size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  PROTOCOL BRIDGE
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  MCP 插件管理 // MODEL CONTEXT PROTOCOL
                </p>
              </div>
            </div>

            {/* 表头 */}
            <div
              className="grid grid-cols-12 gap-2 px-4 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              <span className="text-label col-span-5" style={{ fontSize: '10px' }}>名称</span>
              <span className="text-label col-span-2 text-center" style={{ fontSize: '10px' }}>版本</span>
              <span className="text-label col-span-2 text-center" style={{ fontSize: '10px' }}>协议</span>
              <span className="text-label col-span-1 text-center" style={{ fontSize: '10px' }}>状态</span>
              <span className="text-label col-span-2 text-right" style={{ fontSize: '10px' }}>开关</span>
            </div>

            {/* 插件行 */}
            <div className="flex-1 space-y-1">
              {PLUGINS.map((pl) => {
                const isOn = pl.status === 'running';
                const pc = protocolColor(pl.protocol);
                return (
                  <div
                    key={pl.name}
                    className="grid grid-cols-12 gap-2 items-center py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    {/* 名称 */}
                    <span className="font-mono text-xs col-span-5 truncate" style={{ color: 'var(--text-primary)' }}>
                      {pl.name}
                    </span>
                    {/* 版本 */}
                    <span className="font-mono text-[10px] col-span-2 text-center" style={{ color: 'var(--text-disabled)' }}>
                      v{pl.version}
                    </span>
                    {/* 协议类型 */}
                    <div className="col-span-2 flex justify-center">
                      <span
                        className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider"
                        style={{ background: `${pc}15`, color: pc }}
                      >
                        {pl.protocol.toUpperCase()}
                      </span>
                    </div>
                    {/* 状态点 */}
                    <div className="col-span-1 flex justify-center">
                      <span
                        className={clsx('w-2 h-2 rounded-full', isOn && 'animate-pulse')}
                        style={{ background: isOn ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                      />
                    </div>
                    {/* 开关按钮 */}
                    <div className="col-span-2 flex justify-end">
                      <button
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono text-[10px] tracking-wider transition-colors"
                        style={{
                          background: isOn ? 'rgba(0,255,170,0.1)' : 'rgba(255,255,255,0.04)',
                          color: isOn ? 'var(--accent-green)' : 'var(--text-disabled)',
                        }}
                      >
                        <Power size={10} />
                        {isOn ? '运行中' : '已停用'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 插件统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              PLUGIN STATS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              插件统计
            </h3>

            <div className="grid grid-cols-2 gap-4 flex-1">
              {[
                { label: '已安装', value: PLUGINS.length, color: 'var(--accent-cyan)' },
                { label: '运行中', value: running, color: 'var(--accent-green)' },
                { label: '已停用', value: stopped, color: 'var(--accent-red)' },
                { label: '可用市场', value: 18, color: 'var(--accent-amber)' },
              ].map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 连接总览条 */}
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <span className="text-label">CONNECTION HEALTH</span>
              <div className="flex items-center gap-2 mt-2">
                <Wifi size={14} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                  {running} 连接活跃
                </span>
                <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--text-disabled)' }}>
                  延迟 &lt;50ms
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 协议状态 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              PROTOCOL STATUS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              协议状态
            </h3>

            <div className="flex-1 space-y-3">
              {PROTOCOLS.map((pr) => {
                const isActive = pr.status === 'active';
                return (
                  <div
                    key={pr.name}
                    className="flex items-center justify-between py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-3">
                      {isActive ? (
                        <Radio size={14} style={{ color: pr.color }} />
                      ) : (
                        <WifiOff size={14} style={{ color: pr.color }} />
                      )}
                      <div>
                        <p className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                          {pr.name}
                        </p>
                        <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {isActive ? '连接正常' : '无活跃连接'}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-bold" style={{ color: pr.color }}>
                        {pr.connections}
                      </p>
                      <span className="text-label" style={{ fontSize: '9px' }}>连接数</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 最近事件 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                  RECENT EVENTS
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  最近事件
                </h3>
              </div>
              <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                <Terminal size={12} className="inline mr-1" />LIVE
              </span>
            </div>

            <div
              className="flex-1 rounded-lg p-4 space-y-1.5 overflow-hidden"
              style={{ background: 'var(--bg-base)' }}
            >
              {LOGS.map((l, i) => (
                <div key={i} className="flex gap-2">
                  <span className="font-mono text-[10px] shrink-0" style={{ color: 'var(--text-disabled)' }}>
                    {l.ts}
                  </span>
                  <span className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {l.msg}
                  </span>
                </div>
              ))}
              <span className="font-mono text-[10px] animate-pulse" style={{ color: 'var(--accent-purple)' }}>
                █
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

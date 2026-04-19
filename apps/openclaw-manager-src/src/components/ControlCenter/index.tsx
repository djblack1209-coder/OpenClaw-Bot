/**
 * ControlCenter — 总控中心页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings,
  Power,
  Server,
  Terminal,
  Shield,
  ToggleLeft,
  ToggleRight,
  FileCode,
  AlertTriangle,
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

/** 主开关 */
interface MasterSwitch {
  id: string;
  label: string;
  desc: string;
  enabled: boolean;
  color: string;
  locked?: boolean;
}

const INITIAL_SWITCHES: MasterSwitch[] = [
  { id: 'core', label: 'ClawBot 核心', desc: '主引擎进程', enabled: true, color: 'var(--accent-green)' },
  { id: 'trading', label: '自动交易', desc: '量化交易引擎', enabled: false, color: 'var(--accent-cyan)' },
  { id: 'xianyu', label: '闲鱼客服', desc: 'AI 自动回复', enabled: true, color: 'var(--accent-amber)' },
  { id: 'risk', label: '风控保护', desc: '不可关闭', enabled: true, color: 'var(--accent-red)', locked: true },
  { id: 'news', label: '新闻监控', desc: 'RSS + 爬虫', enabled: true, color: 'var(--accent-purple)' },
  { id: 'memory', label: '记忆引擎', desc: 'Mem0 向量库', enabled: true, color: 'var(--accent-cyan)' },
];

/** 服务矩阵 */
interface ServiceRow {
  name: string;
  status: 'online' | 'offline' | 'degraded';
  port: number;
  cpu: string;
  mem: string;
}

const SERVICE_MATRIX: ServiceRow[] = [
  { name: 'clawbot-core', status: 'online', port: 8000, cpu: '12%', mem: '256MB' },
  { name: 'telegram-bot', status: 'online', port: 8443, cpu: '3%', mem: '128MB' },
  { name: 'trading-engine', status: 'offline', port: 8001, cpu: '—', mem: '—' },
  { name: 'memory-engine', status: 'online', port: 6333, cpu: '8%', mem: '384MB' },
  { name: 'xianyu-agent', status: 'online', port: 8002, cpu: '5%', mem: '192MB' },
  { name: 'news-monitor', status: 'degraded', port: 8003, cpu: '15%', mem: '96MB' },
];

/** 配置参数 */
const CONFIG_PARAMS = [
  { key: 'LLM_MODEL', value: 'gpt-4o', desc: '主模型' },
  { key: 'MAX_TOKENS', value: '4096', desc: '最大输出长度' },
  { key: 'TEMPERATURE', value: '0.7', desc: '创造性参数' },
  { key: 'MEMORY_LIMIT', value: '50', desc: '记忆检索上限' },
  { key: 'LOG_LEVEL', value: 'INFO', desc: '日志级别' },
];

/** 日志行 */
const LOG_LINES = [
  { time: '14:35:12', src: 'core', msg: '服务启动完成，加载 6 个模块' },
  { time: '14:35:10', src: 'trading', msg: '交易引擎初始化中...' },
  { time: '14:34:58', src: 'memory', msg: '向量索引加载完成 dim=1536' },
  { time: '14:34:45', src: 'telegram', msg: '长轮询连接成功 offset=12847' },
  { time: '14:34:30', src: 'xianyu', msg: 'Cookie 有效期剩余 18 天' },
  { time: '14:34:15', src: 'news', msg: 'RSS 源刷新失败: reuters (timeout)' },
  { time: '14:34:00', src: 'core', msg: '健康检查: 5/6 服务正常' },
];

/* ====== 工具函数 ====== */

function statusDot(status: ServiceRow['status']) {
  switch (status) {
    case 'online': return { color: 'var(--accent-green)', label: '在线' };
    case 'offline': return { color: 'var(--text-disabled)', label: '离线' };
    case 'degraded': return { color: 'var(--accent-amber)', label: '降级' };
  }
}

/* ====== 主组件 ====== */

export function ControlCenter() {
  const [switches, setSwitches] = useState(INITIAL_SWITCHES);

  /** 切换开关 */
  const toggleSwitch = (id: string) => {
    setSwitches((prev) =>
      prev.map((s) => (s.id === id && !s.locked ? { ...s, enabled: !s.enabled } : s))
    );
  };

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 主开关面板 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(239,68,68,0.15)' }}
              >
                <Power size={20} style={{ color: 'var(--accent-red)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  MASTER SWITCHES
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  主控开关 // POWER CONTROL
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {switches.map((sw) => (
                <div
                  key={sw.id}
                  className="flex items-center justify-between py-3 px-3 rounded-lg cursor-pointer transition-colors"
                  style={{ background: 'var(--bg-secondary)' }}
                  onClick={() => toggleSwitch(sw.id)}
                >
                  <div>
                    <p className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {sw.label}
                    </p>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {sw.desc}
                    </p>
                  </div>
                  {sw.enabled ? (
                    <ToggleRight size={28} style={{ color: sw.color }} />
                  ) : (
                    <ToggleLeft size={28} style={{ color: 'var(--text-disabled)' }} />
                  )}
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 服务矩阵 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              SERVICE MATRIX
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              服务矩阵
            </h3>

            {/* 表头 */}
            <div
              className="grid grid-cols-5 gap-2 px-3 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              {['服务名', '状态', '端口', 'CPU', '内存'].map((h) => (
                <span key={h} className="text-label" style={{ fontSize: '10px' }}>
                  {h}
                </span>
              ))}
            </div>

            {/* 行列表 */}
            <div className="flex-1 space-y-1">
              {SERVICE_MATRIX.map((svc) => {
                const dot = statusDot(svc.status);
                return (
                  <div
                    key={svc.name}
                    className="grid grid-cols-5 gap-2 px-3 py-2.5 rounded-lg transition-colors"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                      {svc.name}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ background: dot.color }}
                      />
                      <span className="font-mono text-xs" style={{ color: dot.color }}>
                        {dot.label}
                      </span>
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      :{svc.port}
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {svc.cpu}
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {svc.mem}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 配置编辑器 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              RUNTIME CONFIG
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              运行配置
            </h3>

            <div className="flex-1 space-y-2">
              {CONFIG_PARAMS.map((p) => (
                <div
                  key={p.key}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <FileCode size={12} style={{ color: 'var(--accent-purple)' }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {p.key}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      ({p.desc})
                    </span>
                  </div>
                  <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {p.value}
                  </span>
                </div>
              ))}
            </div>

            {/* 警告提示 */}
            <div
              className="flex items-start gap-2.5 mt-4 pt-3 border-t"
              style={{ borderColor: 'var(--glass-border)' }}
            >
              <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-amber)' }} />
              <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                修改配置后需要重启 ClawBot 链路才能生效
              </p>
            </div>
          </div>
        </motion.div>

        {/* ====== 日志观察窗 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-0 overflow-hidden h-full flex flex-col">
            <div
              className="flex items-center gap-2 px-5 py-3"
              style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--glass-border)' }}
            >
              <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                LOG VIEWER
              </span>
            </div>
            <div
              className="flex-1 p-4 space-y-0.5 font-mono text-xs overflow-y-auto"
              style={{ background: 'var(--bg-elevated)' }}
            >
              {LOG_LINES.map((log, i) => (
                <div key={i} className={clsx('py-1 px-2 rounded flex gap-3')}>
                  <span style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                  <span
                    className="w-20 shrink-0"
                    style={{
                      color:
                        log.src === 'news' ? 'var(--accent-amber)' :
                        log.src === 'trading' ? 'var(--accent-cyan)' :
                        'var(--accent-green)',
                    }}
                  >
                    [{log.src}]
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

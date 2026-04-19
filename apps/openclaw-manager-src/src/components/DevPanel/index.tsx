/**
 * DevPanel — 开发者工作台页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Terminal,
  Cpu,
  Eye,
  EyeOff,
  FolderTree,
  Zap,
  ChevronRight,
  Activity,
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

/** 终端命令历史 */
interface CmdLine { prompt: boolean; text: string; color?: string }
const TERMINAL_LINES: CmdLine[] = [
  { prompt: true, text: 'cd packages/clawbot && python multi_main.py' },
  { prompt: false, text: '[INFO] 加载配置文件: config/openclaw.yaml', color: 'var(--text-tertiary)' },
  { prompt: false, text: '[INFO] 初始化 LiteLLM 路由池... 7 个模型已注册', color: 'var(--text-tertiary)' },
  { prompt: false, text: '[SUCCESS] Gateway 启动成功 → http://0.0.0.0:18790', color: 'var(--accent-green)' },
  { prompt: true, text: 'pytest tests/ -x --tb=short' },
  { prompt: false, text: 'collected 1461 items', color: 'var(--text-tertiary)' },
  { prompt: false, text: '================================ 1461 passed in 23.4s ================================', color: 'var(--accent-green)' },
  { prompt: true, text: 'git log --oneline -3' },
  { prompt: false, text: 'a3f29b1 修复: AI 路由池权重分配异常', color: 'var(--accent-cyan)' },
  { prompt: false, text: 'e7c4d02 新增: Telegram 多账号切换支持', color: 'var(--accent-cyan)' },
  { prompt: false, text: '1b8a5f3 优化: 日志采集器内存占用降低40%', color: 'var(--accent-cyan)' },
  { prompt: true, text: 'docker ps --format "table {{.Names}}\\t{{.Status}}"' },
  { prompt: false, text: 'openclaw-redis    Up 3 days', color: 'var(--text-tertiary)' },
  { prompt: false, text: 'openclaw-gateway  Up 2 hours', color: 'var(--accent-green)' },
  { prompt: false, text: 'openclaw-worker   Up 2 hours', color: 'var(--accent-green)' },
];

/** 系统信息 */
const SYS_INFO = [
  { label: 'OS', value: 'macOS 15.2 (Sonoma)', color: 'var(--text-primary)' },
  { label: 'Python', value: '3.12.4', color: 'var(--accent-cyan)' },
  { label: 'Node', value: '18.20.2', color: 'var(--accent-green)' },
  { label: 'Rust', value: '1.82.0', color: 'var(--accent-amber)' },
  { label: '端口', value: '18790', color: 'var(--accent-purple)' },
  { label: 'PID', value: '48231', color: 'var(--text-tertiary)' },
];

/** 环境变量 */
const ENV_VARS = [
  { key: 'OPENAI_API_KEY', value: 'sk-proj-****...****Xq9a', masked: true },
  { key: 'TELEGRAM_BOT_TOKEN', value: '7841****:AAH****...****mZk', masked: true },
  { key: 'LITELLM_MASTER_KEY', value: 'sk-****...****8f2d', masked: true },
  { key: 'REDIS_URL', value: 'redis://localhost:6379/0', masked: false },
  { key: 'LOG_LEVEL', value: 'INFO', masked: false },
];

/** 文件浏览器 */
const DIR_TREE = [
  { name: 'core/', files: 24, desc: '核心业务逻辑' },
  { name: 'bots/', files: 18, desc: 'Bot 实例管理' },
  { name: 'services/', files: 31, desc: '服务层 & 集成' },
  { name: 'handlers/', files: 42, desc: '消息处理器' },
  { name: 'utils/', files: 15, desc: '工具函数库' },
];

/** API 测试 */
interface ApiTest { name: string; endpoint: string; lastMs: number; status: 'ok' | 'slow' | 'error' }
const API_TESTS: ApiTest[] = [
  { name: '健康检查', endpoint: '/health', lastMs: 12, status: 'ok' },
  { name: 'Bot 状态', endpoint: '/api/bot/matrix', lastMs: 89, status: 'ok' },
  { name: '发送测试消息', endpoint: '/api/message/test', lastMs: 340, status: 'slow' },
];

function apiStatusStyle(s: ApiTest['status']) {
  switch (s) {
    case 'ok': return { color: 'var(--accent-green)', label: '正常' };
    case 'slow': return { color: 'var(--accent-amber)', label: '偏慢' };
    case 'error': return { color: 'var(--accent-red)', label: '异常' };
  }
}

/* ====== 主组件 ====== */

export default function DevPanel() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 终端模拟器 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card h-full flex flex-col" style={{ background: 'rgba(5,5,12,0.95)' }}>
            {/* 终端标题栏 */}
            <div
              className="flex items-center gap-3 px-5 py-3 border-b"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-red)' }} />
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-amber)' }} />
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-green)' }} />
              </div>
              <div className="flex items-center gap-2">
                <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
                <h2 className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  DEV TERMINAL
                </h2>
                <span className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  开发者终端 // DEV TERMINAL
                </span>
              </div>
            </div>

            {/* 终端内容 */}
            <div className="flex-1 p-5 overflow-y-auto scroll-container">
              <div className="space-y-0.5">
                {TERMINAL_LINES.map((line, i) => (
                  <div key={i} className="font-mono text-[12px] leading-relaxed">
                    {line.prompt ? (
                      <span>
                        <span style={{ color: 'var(--accent-green)' }}>openclaw</span>
                        <span style={{ color: 'var(--text-disabled)' }}>:</span>
                        <span style={{ color: 'var(--accent-cyan)' }}>~</span>
                        <span style={{ color: 'var(--text-disabled)' }}> $ </span>
                        <span style={{ color: 'var(--text-primary)' }}>{line.text}</span>
                      </span>
                    ) : (
                      <span style={{ color: line.color || 'var(--text-tertiary)' }}>
                        {line.text}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 终端输入行 */}
            <div
              className="flex items-center gap-2 px-5 py-3 border-t"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <span className="font-mono text-[12px]">
                <span style={{ color: 'var(--accent-green)' }}>openclaw</span>
                <span style={{ color: 'var(--text-disabled)' }}>:</span>
                <span style={{ color: 'var(--accent-cyan)' }}>~</span>
                <span style={{ color: 'var(--text-disabled)' }}> $ </span>
              </span>
              <div className="w-2 h-4 animate-pulse" style={{ background: 'var(--accent-cyan)' }} />
            </div>
          </div>
        </motion.div>

        {/* ====== 系统信息 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
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
                  系统信息
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  SYSTEM INFO
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {SYS_INFO.map((info) => (
                <div
                  key={info.label}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="text-label">{info.label}</span>
                  <span className="font-mono text-xs font-semibold" style={{ color: info.color }}>
                    {info.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 环境变量 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <EyeOff size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  环境变量
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  ENV VARIABLES
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {ENV_VARS.map((env) => (
                <div
                  key={env.key}
                  className="py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] font-bold" style={{ color: 'var(--accent-cyan)' }}>
                      {env.key}
                    </span>
                    {env.masked && <Eye size={10} style={{ color: 'var(--text-disabled)' }} />}
                  </div>
                  <p
                    className={clsx('font-mono text-[11px] mt-1 truncate', env.masked && 'select-none')}
                    style={{ color: env.masked ? 'var(--text-disabled)' : 'var(--text-primary)' }}
                  >
                    {env.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 文件浏览器 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <FolderTree size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  文件浏览器
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  packages/clawbot/src/
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-1.5">
              {DIR_TREE.map((dir) => (
                <div
                  key={dir.name}
                  className="flex items-center gap-3 py-3 px-4 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <ChevronRight size={12} style={{ color: 'var(--text-disabled)', flexShrink: 0 }} />
                  <span className="font-mono text-sm font-bold" style={{ color: 'var(--accent-cyan)' }}>
                    {dir.name}
                  </span>
                  <span className="font-mono text-[10px] flex-1" style={{ color: 'var(--text-disabled)' }}>
                    {dir.desc}
                  </span>
                  <span
                    className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider"
                    style={{ background: 'rgba(6,182,212,0.1)', color: 'var(--accent-cyan)' }}
                  >
                    {dir.files} 文件
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== API 测试 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <Zap size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  API 测试
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  QUICK API TEST
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-3">
              {API_TESTS.map((t) => {
                const st = apiStatusStyle(t.status);
                return (
                  <div
                    key={t.name}
                    className="py-4 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                        {t.name}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider"
                        style={{ background: `color-mix(in srgb, ${st.color} 15%, transparent)`, color: st.color }}
                      >
                        {st.label}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {t.endpoint}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Activity size={10} style={{ color: st.color }} />
                        <span className="text-metric" style={{ color: st.color, fontSize: '16px' }}>
                          {t.lastMs}ms
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

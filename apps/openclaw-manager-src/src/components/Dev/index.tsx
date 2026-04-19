/**
 * Dev — 开发总控页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import {
  GitCommit,
  Code2,
  ShieldCheck,
  AlertTriangle,
  ArrowUpCircle,
  Package,
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

/** 概览统计 */
const OVERVIEW_STATS = [
  { label: 'Git提交(今日)', value: '3', color: 'var(--accent-cyan)' },
  { label: '活跃分支', value: 'main', color: 'var(--accent-green)' },
  { label: '代码行数', value: '18.7K', color: 'var(--accent-purple)' },
  { label: '测试覆盖率', value: '73%', color: 'var(--accent-amber)' },
];

/** 最近 Git 提交 */
interface GitLog { hash: string; message: string; time: string }
const GIT_LOGS: GitLog[] = [
  { hash: 'a3f29b1', message: '修复: AI 路由池权重分配异常', time: '14分钟前' },
  { hash: 'e7c4d02', message: '新增: Telegram 多账号切换支持', time: '2小时前' },
  { hash: '1b8a5f3', message: '优化: 日志采集器内存占用降低40%', time: '3小时前' },
  { hash: 'c92e0a7', message: '重构: 统一命令注册中心接口', time: '昨天 18:30' },
  { hash: 'f6d1b48', message: '配置: 更新 LiteLLM 模型映射表', time: '昨天 15:22' },
];

/** 构建状态 */
interface BuildItem { name: string; status: 'success' | 'running' | 'error'; detail: string }
const BUILD_STATUS: BuildItem[] = [
  { name: '前端', status: 'success', detail: '构建成功' },
  { name: '后端', status: 'running', detail: '运行中' },
  { name: '测试', status: 'success', detail: '1461 通过' },
  { name: 'Docker', status: 'running', detail: '3 容器运行' },
];

/** 技术债务 */
interface TechDebt { priority: 'high' | 'medium' | 'low'; desc: string; module: string }
const TECH_DEBTS: TechDebt[] = [
  { priority: 'high', desc: '日志系统未做结构化输出，排查效率低', module: 'logger' },
  { priority: 'high', desc: 'Bot 矩阵轮询间隔硬编码，需配置化', module: 'bot_matrix' },
  { priority: 'medium', desc: '命令注册表缺少版本号字段', module: 'cmd_registry' },
  { priority: 'low', desc: '前端 CSS 变量命名不统一', module: 'ui' },
];

/** 依赖更新 */
interface DepUpdate { name: string; current: string; latest: string; type: 'major' | 'minor' | 'patch' }
const DEP_UPDATES: DepUpdate[] = [
  { name: 'litellm', current: '1.51.0', latest: '1.56.2', type: 'minor' },
  { name: 'python-telegram-bot', current: '21.6', latest: '21.9', type: 'minor' },
  { name: 'fastapi', current: '0.115.0', latest: '0.115.6', type: 'patch' },
  { name: 'crawl4ai', current: '0.4.1', latest: '0.5.0', type: 'major' },
];

/* ====== 工具函数 ====== */

function priorityInfo(p: TechDebt['priority']) {
  switch (p) {
    case 'high': return { label: '高', bg: 'rgba(239,68,68,0.15)', color: 'var(--accent-red)' };
    case 'medium': return { label: '中', bg: 'rgba(245,158,11,0.15)', color: 'var(--accent-amber)' };
    case 'low': return { label: '低', bg: 'rgba(6,182,212,0.15)', color: 'var(--accent-cyan)' };
  }
}

function depTypeBadge(type: DepUpdate['type']) {
  switch (type) {
    case 'major': return { label: '大版本', bg: 'rgba(239,68,68,0.15)', color: 'var(--accent-red)' };
    case 'minor': return { label: '功能更新', bg: 'rgba(245,158,11,0.15)', color: 'var(--accent-amber)' };
    case 'patch': return { label: '补丁', bg: 'rgba(34,197,94,0.15)', color: 'var(--accent-green)' };
  }
}

function buildStatusStyle(s: BuildItem['status']) {
  switch (s) {
    case 'success': return { icon: '✓', color: 'var(--accent-green)' };
    case 'running': return { icon: '●', color: 'var(--accent-cyan)' };
    case 'error': return { icon: '✗', color: 'var(--accent-red)' };
  }
}

/* ====== 主组件 ====== */

export function Dev() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 开发概览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Code2 size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  DEV CONTROL
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  开发总控 // DEV CONTROL
                </p>
              </div>
            </div>

            {/* 统计指标 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {OVERVIEW_STATS.map((s) => (
                <div
                  key={s.label}
                  className="rounded-lg p-3"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="text-label">{s.label}</span>
                  <p className="text-metric mt-1" style={{ color: s.color, fontSize: '22px' }}>
                    {s.value}
                  </p>
                </div>
              ))}
            </div>

            {/* 最近 Git 提交 */}
            <div className="flex-1">
              <span className="text-label mb-2 block" style={{ color: 'var(--text-tertiary)' }}>最近提交</span>
              <div className="space-y-1">
                {GIT_LOGS.map((log) => (
                  <div
                    key={log.hash}
                    className="flex items-center gap-3 py-2 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <GitCommit size={14} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--accent-cyan)', flexShrink: 0 }}>
                      {log.hash}
                    </span>
                    <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                      {log.message}
                    </span>
                    <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {log.time}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 构建状态 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <ShieldCheck size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  构建状态
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  BUILD STATUS
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-3">
              {BUILD_STATUS.map((b) => {
                const bs = buildStatusStyle(b.status);
                return (
                  <div
                    key={b.name}
                    className="flex items-center justify-between py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm" style={{ color: bs.color }}>{bs.icon}</span>
                      <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                        {b.name}
                      </span>
                    </div>
                    <span className="font-mono text-[11px]" style={{ color: bs.color }}>
                      {b.detail}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 技术债务 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <AlertTriangle size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  技术债务
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  TECH DEBT // {TECH_DEBTS.length} 项
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {TECH_DEBTS.map((d, i) => {
                const pi = priorityInfo(d.priority);
                return (
                  <div
                    key={i}
                    className="flex items-start gap-3 py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <span
                      className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider flex-shrink-0 mt-0.5"
                      style={{ background: pi.bg, color: pi.color }}
                    >
                      {pi.label}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        {d.desc}
                      </p>
                      <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-disabled)' }}>
                        模块: {d.module}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 依赖更新 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <Package size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  依赖更新
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  DEPENDENCY UPDATES // {DEP_UPDATES.length} 可用
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {DEP_UPDATES.map((d) => {
                const badge = depTypeBadge(d.type);
                return (
                  <div
                    key={d.name}
                    className="flex items-center gap-3 py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <ArrowUpCircle size={14} style={{ color: badge.color, flexShrink: 0 }} />
                    <span className="font-display text-sm font-bold flex-1" style={{ color: 'var(--text-primary)' }}>
                      {d.name}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {d.current}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>→</span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                      {d.latest}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider flex-shrink-0"
                      style={{ background: badge.bg, color: badge.color }}
                    >
                      {badge.label}
                    </span>
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

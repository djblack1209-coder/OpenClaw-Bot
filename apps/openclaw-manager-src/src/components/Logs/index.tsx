/**
 * Logs — 应用日志 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Terminal,
  HardDrive,
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

type LogLevel = 'INFO' | 'OK' | 'WARN' | 'ERROR';

interface LogLine {
  time: string;
  level: LogLevel;
  module: string;
  msg: string;
}

const LEVEL_STYLE: Record<LogLevel, { color: string; bg: string }> = {
  INFO: { color: 'var(--accent-cyan)', bg: 'rgba(6,182,212,0.12)' },
  OK: { color: 'var(--accent-green)', bg: 'rgba(34,197,94,0.12)' },
  WARN: { color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.12)' },
  ERROR: { color: 'var(--accent-red)', bg: 'rgba(239,68,68,0.12)' },
};

const ALL_LOGS: LogLine[] = [
  { time: '14:48:22.341', level: 'INFO', module: 'gateway', msg: '收到 Telegram 消息 — 用户 @alice — 文本消息' },
  { time: '14:48:22.445', level: 'OK', module: 'auto_trader', msg: '交易信号扫描完成 — 发现 BTC/USDT 做多信号' },
  { time: '14:48:21.002', level: 'INFO', module: 'scheduler', msg: '[交易信号扫描] 任务开始执行' },
  { time: '14:48:20.887', level: 'WARN', module: 'xianyu', msg: '闲鱼商品刷新超时 — 商品ID: 78234 — 重试 2/3' },
  { time: '14:48:19.556', level: 'ERROR', module: 'social', msg: 'Twitter API 速率限制 — 429 Too Many Requests' },
  { time: '14:48:18.123', level: 'INFO', module: 'gateway', msg: '收到 Discord 消息 — 用户 Bob — /help 命令' },
  { time: '14:48:17.001', level: 'OK', module: 'scheduler', msg: '[社媒内容采集] 任务完成 — 采集 47 条' },
  { time: '14:48:15.234', level: 'INFO', module: 'auto_trader', msg: 'K线数据更新 — BTC $67,234 — ETH $3,456' },
  { time: '14:48:14.098', level: 'WARN', module: 'gateway', msg: 'Telegram 消息延迟 > 500ms — 当前 623ms' },
  { time: '14:48:12.567', level: 'INFO', module: 'social', msg: '微博热搜抓取完成 — 50 条热点' },
  { time: '14:48:11.890', level: 'ERROR', module: 'auto_trader', msg: '订单提交失败 — 余额不足 — USDT: 0.34' },
  { time: '14:48:10.445', level: 'OK', module: 'xianyu', msg: '闲鱼消息回复成功 — 买家: 小明 — 自动议价' },
  { time: '14:48:09.112', level: 'INFO', module: 'gateway', msg: 'WebSocket 心跳 — Telegram — 延迟 120ms' },
  { time: '14:48:08.001', level: 'INFO', module: 'scheduler', msg: '[模型健康检查] 任务开始执行' },
  { time: '14:48:07.234', level: 'WARN', module: 'auto_trader', msg: '深度数据异常 — BTC/USDT 买一挂单量突增 300%' },
  { time: '14:48:06.556', level: 'OK', module: 'social', msg: '推文发布成功 — 每日市场简报 — 互动: 12' },
  { time: '14:48:05.890', level: 'ERROR', module: 'scheduler', msg: '[模型健康检查] DeepSeek V3 连接超时 — 5000ms' },
  { time: '14:48:04.123', level: 'INFO', module: 'xianyu', msg: '商品上架监控 — 新增 3 个竞品' },
  { time: '14:48:03.001', level: 'INFO', module: 'gateway', msg: '用户 @charlie 加入 Telegram 群组' },
  { time: '14:48:01.445', level: 'OK', module: 'auto_trader', msg: '仓位同步完成 — BTC 0.5 — ETH 2.3 — SOL 45' },
];

const LOG_STATS = [
  { label: '今日总量', value: '2,847', color: 'var(--text-primary)' },
  { label: 'INFO', value: '2,340', color: 'var(--accent-cyan)' },
  { label: 'WARN', value: '412', color: 'var(--accent-amber)' },
  { label: 'ERROR', value: '95', color: 'var(--accent-red)' },
];

const FILTER_CHIPS: { label: string; value: LogLevel | 'ALL' }[] = [
  { label: '全部', value: 'ALL' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARN', value: 'WARN' },
  { label: 'ERROR', value: 'ERROR' },
];

interface ModuleHeat { name: string; count: number; color: string }
const MODULE_HEAT: ModuleHeat[] = [
  { name: 'auto_trader', count: 847, color: 'var(--accent-green)' },
  { name: 'xianyu', count: 623, color: 'var(--accent-cyan)' },
  { name: 'social', count: 534, color: 'var(--accent-purple)' },
  { name: 'scheduler', count: 445, color: 'var(--accent-amber)' },
  { name: 'gateway', count: 398, color: 'var(--accent-red)' },
];

const STORAGE = [
  { label: '日志文件大小', value: '234 MB' },
  { label: '保留天数', value: '30 天' },
  { label: '自动清理', value: '已开启' },
];

/* ====== 工具函数 ====== */

function renderBar(value: number, max: number, width: number = 20): string {
  const ratio = value / max;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Logs() {
  const [filter, setFilter] = useState<LogLevel | 'ALL'>('ALL');
  const maxModuleCount = Math.max(...MODULE_HEAT.map((m) => m.count));

  const filteredLogs = filter === 'ALL'
    ? ALL_LOGS
    : ALL_LOGS.filter((l) => l.level === filter || (filter === 'INFO' && l.level === 'OK'));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 日志终端 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}
              >
                <Terminal size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  SYSTEM LOGS
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  应用日志 // RUNTIME OUTPUT
                </p>
              </div>
            </div>

            {/* 终端区域 */}
            <div
              className="flex-1 rounded-lg p-3 font-mono text-[11px] leading-[1.7] overflow-y-auto"
              style={{ background: 'var(--bg-primary)' }}
            >
              {filteredLogs.map((log, i) => {
                const ls = LEVEL_STYLE[log.level];
                return (
                  <div key={i} className="flex items-start gap-2 py-0.5">
                    <span style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                    <span
                      className="px-1.5 py-0 rounded text-[9px] tracking-wider font-bold flex-shrink-0"
                      style={{ color: ls.color, background: ls.bg }}
                    >
                      {log.level}
                    </span>
                    <span className="flex-shrink-0" style={{ color: 'var(--accent-purple)' }}>
                      [{log.module}]
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{log.msg}</span>
                  </div>
                );
              })}
              {/* 闪烁光标 */}
              <div className="flex items-center gap-1 mt-1">
                <span style={{ color: 'var(--accent-green)' }}>▊</span>
                <span className="animate-pulse" style={{ color: 'var(--text-disabled)' }}>_</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 日志统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>STATISTICS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              日志统计
            </h3>
            <div className="space-y-4 flex-1">
              {LOG_STATS.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: s.color, fontSize: '22px' }}>{s.value}</p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 日志筛选 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>FILTER</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              日志筛选
            </h3>
            <div className="flex flex-wrap gap-2 flex-1">
              {FILTER_CHIPS.map((chip) => {
                const active = filter === chip.value;
                const chipColor = chip.value === 'ALL'
                  ? 'var(--accent-cyan)'
                  : chip.value === 'INFO'
                    ? 'var(--accent-cyan)'
                    : chip.value === 'WARN'
                      ? 'var(--accent-amber)'
                      : 'var(--accent-red)';
                return (
                  <button
                    key={chip.value}
                    onClick={() => setFilter(chip.value)}
                    className="px-4 py-2 rounded-lg font-mono text-xs tracking-wider transition-all"
                    style={{
                      background: active ? chipColor : 'var(--bg-secondary)',
                      color: active ? 'var(--bg-primary)' : chipColor,
                      fontWeight: active ? 700 : 500,
                    }}
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>
            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              当前显示: {filteredLogs.length} 条 / 共 {ALL_LOGS.length} 条
            </p>
          </div>
        </motion.div>

        {/* ====== 模块热度 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>MODULE HEATMAP</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              模块日志量排行
            </h3>
            <div className="flex-1 space-y-3">
              {MODULE_HEAT.map((m) => (
                <div key={m.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-display text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {m.name}
                    </span>
                    <span className="font-mono text-[11px] font-bold" style={{ color: m.color }}>
                      {m.count.toLocaleString()}
                    </span>
                  </div>
                  <div className="font-mono text-[10px] leading-none" style={{ color: m.color }}>
                    {renderBar(m.count, maxModuleCount)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 存储信息 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>STORAGE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              存储信息
            </h3>
            <div className="flex-1 space-y-4">
              {STORAGE.map((s) => (
                <div key={s.label} className="flex items-center justify-between py-2 px-3 rounded-lg" style={{ background: 'var(--bg-secondary)' }}>
                  <span className="text-label">{s.label}</span>
                  <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {s.value}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-primary)' }}>
              <div className="flex items-center gap-2">
                <HardDrive size={12} style={{ color: 'var(--text-disabled)' }} />
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  磁盘占用 234 MB / 10 GB (2.3%)
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/**
 * Channels — 消息渠道页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import {
  MessageCircle,
  CheckCircle2,
  XCircle,
  Clock,
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

/** 渠道信息 */
interface Channel {
  id: string;
  name: string;
  type: string;
  status: 'connected' | 'disconnected' | 'configuring';
  color: string;
  icon: string;
  msgToday: number;
  msgTotal: number;
  users: number;
  latency: string;
}

const CHANNELS: Channel[] = [
  { id: 'tg', name: 'Telegram', type: 'telegram', status: 'connected', color: 'var(--accent-cyan)', icon: '✈', msgToday: 847, msgTotal: 125600, users: 38, latency: '120ms' },
  { id: 'dc', name: 'Discord', type: 'discord', status: 'connected', color: 'var(--accent-purple)', icon: '🎮', msgToday: 234, msgTotal: 45200, users: 156, latency: '85ms' },
  { id: 'fs', name: '飞书', type: 'feishu', status: 'configuring', color: 'var(--accent-cyan)', icon: '🪶', msgToday: 0, msgTotal: 0, users: 0, latency: '—' },
  { id: 'wx', name: '微信', type: 'wechat', status: 'disconnected', color: 'var(--accent-green)', icon: '💬', msgToday: 0, msgTotal: 8900, users: 12, latency: '—' },
  { id: 'wa', name: 'WhatsApp', type: 'whatsapp', status: 'disconnected', color: 'var(--accent-green)', icon: '📱', msgToday: 0, msgTotal: 0, users: 0, latency: '—' },
];

/** 消息统计 */
const MSG_STATS = [
  { label: '今日消息', value: '1,081', color: 'var(--accent-cyan)' },
  { label: '活跃渠道', value: '2/5', color: 'var(--accent-green)' },
  { label: '总用户数', value: '206', color: 'var(--accent-purple)' },
  { label: '平均延迟', value: '103ms', color: 'var(--accent-amber)' },
];

/** Webhook 配置 */
interface WebhookConfig {
  name: string;
  url: string;
  events: string;
  status: 'active' | 'inactive';
  lastTriggered: string;
}

const WEBHOOKS: WebhookConfig[] = [
  { name: 'Telegram 通知', url: 'https://api.tg.bot/webhook', events: 'message,command', status: 'active', lastTriggered: '2分钟前' },
  { name: 'Discord 同步', url: 'https://discord.com/api/webhooks/...', events: 'message', status: 'active', lastTriggered: '8分钟前' },
  { name: '监控告警', url: 'https://monitor.internal/alert', events: 'error,warning', status: 'active', lastTriggered: '1小时前' },
  { name: '飞书集成', url: 'https://open.feishu.cn/...', events: 'all', status: 'inactive', lastTriggered: '—' },
];

/** 每小时消息量 */
const HOURLY_DATA = [
  { hour: '08:00', count: 45 },
  { hour: '10:00', count: 120 },
  { hour: '12:00', count: 89 },
  { hour: '14:00', count: 156 },
  { hour: '16:00', count: 203 },
  { hour: '18:00', count: 178 },
  { hour: '20:00', count: 134 },
  { hour: '22:00', count: 67 },
];

/* ====== 工具函数 ====== */

function statusInfo(status: Channel['status']) {
  switch (status) {
    case 'connected': return { label: '已连接', color: 'var(--accent-green)', Icon: CheckCircle2 };
    case 'disconnected': return { label: '未连接', color: 'var(--text-disabled)', Icon: XCircle };
    case 'configuring': return { label: '配置中', color: 'var(--accent-amber)', Icon: Clock };
  }
}

function renderBar(value: number, maxValue: number, width: number = 20): string {
  const ratio = value / maxValue;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Channels() {
  const maxHourly = Math.max(...HOURLY_DATA.map((d) => d.count));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 渠道列表 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <MessageCircle size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  MESSAGE CHANNELS
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  消息渠道 // MULTI-PLATFORM HUB
                </p>
              </div>
            </div>

            {/* 渠道卡片列表 */}
            <div className="flex-1 space-y-2">
              {CHANNELS.map((ch) => {
                const si = statusInfo(ch.status);
                return (
                  <div
                    key={ch.id}
                    className="flex items-center justify-between py-3 px-4 rounded-lg transition-colors"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xl w-8 text-center">{ch.icon}</span>
                      <div>
                        <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                          {ch.name}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <si.Icon size={10} style={{ color: si.color }} />
                          <span className="font-mono text-[10px]" style={{ color: si.color }}>
                            {si.label}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <span className="text-label">今日</span>
                        <p className="font-mono text-sm font-semibold" style={{ color: ch.color }}>
                          {ch.msgToday.toLocaleString()}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-label">用户</span>
                        <p className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                          {ch.users}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-label">延迟</span>
                        <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {ch.latency}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 消息统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              MESSAGE STATS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              消息统计
            </h3>

            <div className="grid grid-cols-2 gap-4 mb-6">
              {MSG_STATS.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 每小时消息量 */}
            <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
              HOURLY THROUGHPUT
            </span>
            <div className="mt-2 flex-1 space-y-1">
              {HOURLY_DATA.map((d) => (
                <div key={d.hour} className="flex items-center gap-2">
                  <span className="font-mono text-[10px] w-10 shrink-0" style={{ color: 'var(--text-disabled)' }}>
                    {d.hour}
                  </span>
                  <span
                    className="font-mono text-[10px] flex-1 tracking-tight"
                    style={{ color: 'var(--accent-cyan)', opacity: 0.85 }}
                  >
                    {renderBar(d.count, maxHourly, 16)}
                  </span>
                  <span className="font-mono text-[10px] w-8 text-right" style={{ color: 'var(--text-secondary)' }}>
                    {d.count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Webhook 配置 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              WEBHOOK CONFIG
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              Webhook 管理
            </h3>

            {/* 表头 */}
            <div
              className="grid grid-cols-5 gap-3 px-4 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              {['名称', 'URL', '事件', '状态', '最近触发'].map((h) => (
                <span key={h} className="text-label" style={{ fontSize: '10px' }}>
                  {h}
                </span>
              ))}
            </div>

            {/* Webhook 列表 */}
            <div className="space-y-1">
              {WEBHOOKS.map((wh, i) => (
                <div
                  key={i}
                  className="grid grid-cols-5 gap-3 px-4 py-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    {wh.name}
                  </span>
                  <span className="font-mono text-[10px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                    {wh.url}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    {wh.events}
                  </span>
                  <span
                    className="font-mono text-[10px] font-semibold"
                    style={{ color: wh.status === 'active' ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                  >
                    {wh.status === 'active' ? '● 活跃' : '○ 停用'}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    {wh.lastTriggered}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

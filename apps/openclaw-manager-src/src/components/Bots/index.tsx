import { motion } from 'framer-motion';
import {
  Fish,
  TrendingUp,
  Shield,
  Rocket,
  Share2,
  Radar,
  HeartPulse,
  MessageCircle,
  Clock,
  Terminal,
  Plus,
  RotateCcw,
  Download,
  FileText,
  Cookie,
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

/* ====== 类型 ====== */
type BotStatus = 'running' | 'stopped' | 'error';
type BotType = '客服' | '交易' | '社媒' | '爬虫' | '监控';
type LogLevel = 'INFO' | 'OK' | 'WARN' | 'ERROR';

/* ====== 模拟数据 ====== */

/** 7 个 Bot */
const bots: {
  name: string;
  type: BotType;
  status: BotStatus;
  uptime: string;
  messages: number;
  icon: typeof Fish;
}[] = [
  { name: '闲鱼智能客服',     type: '客服', status: 'running', uptime: '72h 14m', messages: 3842, icon: Fish },
  { name: '巴菲特分析师',     type: '交易', status: 'running', uptime: '48h 05m', messages: 1256, icon: TrendingUp },
  { name: '塔勒布风控官',     type: '交易', status: 'running', uptime: '48h 05m', messages: 987,  icon: Shield },
  { name: '木头姐趋势猎手',   type: '交易', status: 'running', uptime: '48h 05m', messages: 1143, icon: Rocket },
  { name: '社媒内容生成',     type: '社媒', status: 'running', uptime: '24h 30m', messages: 2156, icon: Share2 },
  { name: '热点追踪爬虫',     type: '爬虫', status: 'stopped', uptime: '—',       messages: 1890, icon: Radar },
  { name: '系统健康监控',     type: '监控', status: 'error',   uptime: '12h 45m', messages: 1573, icon: HeartPulse },
];

/** 性能指标 */
const perfMetrics = [
  { label: '总处理消息',   value: '12,847', accent: 'var(--accent-cyan)' },
  { label: '平均响应时间', value: '1.8s',   accent: 'var(--accent-green)' },
  { label: '成功率',       value: '97.3%',  accent: 'var(--accent-green)' },
  { label: '今日活跃用户', value: '156',    accent: 'var(--accent-purple)' },
  { label: 'API 调用次数', value: '3,421',  accent: 'var(--accent-amber)' },
  { label: '错误率',       value: '2.7%',   accent: 'var(--accent-red)' },
];

/** 交易 Bot 共识投票 */
const tradingBots = [
  { name: '巴菲特分析师',   approve: 75, reject: 10, pending: 15 },
  { name: '塔勒布风控官',   approve: 30, reject: 55, pending: 15 },
  { name: '木头姐趋势猎手', approve: 85, reject: 5,  pending: 10 },
  { name: '索罗斯宏观',     approve: 60, reject: 20, pending: 20 },
  { name: '达里奥全天候',   approve: 50, reject: 25, pending: 25 },
];

/** 社媒平台 */
const socialPlatforms = [
  { name: '小红书', posts: 3, color: 'var(--accent-red)' },
  { name: 'X',      posts: 5, color: 'var(--accent-cyan)' },
  { name: '微博',   posts: 2, color: 'var(--accent-amber)' },
];

/** 活动日志 */
const logEntries: { time: string; level: LogLevel; bot: string; message: string }[] = [
  { time: '15:42:08', level: 'OK',    bot: '闲鱼智能客服',   message: '自动回复买家「可以包邮吗」→ 已发送话术模板 #12' },
  { time: '15:41:55', level: 'INFO',  bot: '巴菲特分析师',   message: 'AAPL 估值分析完成 → 建议: 持有 (内在价值 $198)' },
  { time: '15:41:32', level: 'WARN',  bot: '塔勒布风控官',   message: 'BTC 尾部风险偏高 → 建议减仓 20%，当前 VaR 超限' },
  { time: '15:41:10', level: 'OK',    bot: '社媒内容生成',   message: '小红书帖子已发布「AI 投资周报 #47」→ 互动率 4.8%' },
  { time: '15:40:48', level: 'ERROR', bot: '系统健康监控',   message: 'Redis 连接超时 (>3s)，已触发重连，第 2 次尝试' },
  { time: '15:40:22', level: 'INFO',  bot: '木头姐趋势猎手', message: 'NVDA 突破趋势线 → 信号: 买入, 置信度 87%' },
  { time: '15:39:55', level: 'INFO',  bot: '热点追踪爬虫',   message: '抓取完成: 36条新闻 / 12条推文 / 5条研报' },
  { time: '15:39:30', level: 'OK',    bot: '闲鱼智能客服',   message: '订单 #XY-2847 议价成功 → 最终价 ¥258 (降 ¥42)' },
];

/* ====== 辅助函数 ====== */

/** 状态颜色 */
const statusColor = (s: BotStatus) =>
  s === 'running' ? 'var(--accent-green)' : s === 'stopped' ? 'var(--text-tertiary)' : 'var(--accent-red)';

/** 状态文本 */
const statusText = (s: BotStatus) =>
  s === 'running' ? '运行中' : s === 'stopped' ? '已停止' : '异常';

/** 类型徽章颜色 */
const typeColor = (t: BotType) => {
  const map: Record<BotType, string> = {
    客服: 'var(--accent-cyan)',
    交易: 'var(--accent-green)',
    社媒: 'var(--accent-purple)',
    爬虫: 'var(--accent-amber)',
    监控: 'var(--accent-red)',
  };
  return map[t];
};

/** 日志级别颜色 */
const logColor = (l: LogLevel) =>
  l === 'OK' ? 'var(--accent-green)' : l === 'WARN' ? 'var(--accent-amber)' : l === 'ERROR' ? 'var(--accent-red)' : 'var(--text-secondary)';

/** 快速操作按钮数据 */
const quickActions = [
  { label: '创建新 Bot', icon: Plus,      accent: 'var(--accent-cyan)' },
  { label: '全部重启',   icon: RotateCcw,  accent: 'var(--accent-green)' },
  { label: '导出配置',   icon: Download,   accent: 'var(--accent-amber)' },
  { label: '查看文档',   icon: FileText,   accent: 'var(--accent-purple)' },
];

/* ====== 统计行数据 ====== */
const fleetStats = [
  { label: '总数',   value: 7, color: 'var(--accent-cyan)' },
  { label: '运行中', value: 5, color: 'var(--accent-green)' },
  { label: '已停止', value: 1, color: 'var(--text-tertiary)' },
  { label: '错误',   value: 1, color: 'var(--accent-red)' },
];

/**
 * Bots 页面 — Sonic Abyss Bento Grid 布局
 * 12 列网格，玻璃卡片 + 终端美学
 */
export function Bots() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >

        {/* ====== Row 1 左: Bot 舰队总览 (col-span-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>BOT FLEET</span>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{ background: 'var(--accent-green)' }}
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>LIVE</span>
              </div>
            </div>
            <h2 className="font-display text-xl font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              智能体舰队 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// BOT FLEET</span>
            </h2>

            {/* 统计行 */}
            <div className="flex gap-5 mb-5">
              {fleetStats.map((s) => (
                <div key={s.label} className="flex items-center gap-2">
                  <span className="font-mono text-2xl font-bold" style={{ color: s.color }}>{s.value}</span>
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.label}</span>
                </div>
              ))}
            </div>

            {/* Bot 列表 */}
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 pr-1">
              {bots.map((bot) => {
                const Icon = bot.icon;
                return (
                  <div
                    key={bot.name}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl transition-colors"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}
                  >
                    {/* 状态圆点 */}
                    <span className="relative flex-shrink-0">
                      {bot.status === 'running' && (
                        <motion.span
                          className="absolute inset-[-3px] rounded-full"
                          style={{ background: statusColor(bot.status), opacity: 0.3 }}
                          animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                          transition={{ duration: 2, repeat: Infinity }}
                        />
                      )}
                      <span
                        className="block w-2 h-2 rounded-full"
                        style={{ background: statusColor(bot.status) }}
                      />
                    </span>

                    {/* 图标 + 名称 */}
                    <Icon size={16} style={{ color: typeColor(bot.type), flexShrink: 0 }} />
                    <span className="font-medium text-sm flex-shrink-0" style={{ color: 'var(--text-primary)' }}>
                      {bot.name}
                    </span>

                    {/* 类型徽章 */}
                    <span
                      className="text-[10px] font-mono px-2 py-0.5 rounded-full flex-shrink-0"
                      style={{
                        color: typeColor(bot.type),
                        background: `color-mix(in srgb, ${typeColor(bot.type)} 10%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${typeColor(bot.type)} 25%, transparent)`,
                      }}
                    >
                      {bot.type}
                    </span>

                    <div className="flex-1" />

                    {/* 运行时长 */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Clock size={12} style={{ color: 'var(--text-tertiary)' }} />
                      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{bot.uptime}</span>
                    </div>

                    {/* 消息数 */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <MessageCircle size={12} style={{ color: 'var(--text-tertiary)' }} />
                      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {bot.messages.toLocaleString()}
                      </span>
                    </div>

                    {/* 状态文本 */}
                    <span className="font-mono text-[10px] w-12 text-right flex-shrink-0" style={{ color: statusColor(bot.status) }}>
                      {statusText(bot.status)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 1 右: 性能仪表盘 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>PERFORMANCE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              性能仪表盘
            </h3>
            <div className="space-y-4">
              {perfMetrics.map((m) => (
                <div key={m.label} className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{m.label}</span>
                  <span className="font-mono text-lg font-bold" style={{ color: m.accent }}>{m.value}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2 左: 闲鱼客服 Bot (col-span-4) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>XIANYU CS</span>
              <span className="relative flex items-center gap-1.5">
                <motion.span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{ background: 'var(--accent-green)' }}
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>ACTIVE</span>
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mb-5" style={{ color: 'var(--text-primary)' }}>
              闲鱼客服 Bot
            </h3>

            <div className="space-y-4">
              {/* 活跃会话 */}
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>活跃会话</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-cyan)' }}>8</span>
              </div>
              {/* 自动回复率 */}
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>自动回复率</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-green)' }}>95%</span>
              </div>
              {/* Cookie 状态 */}
              <div className="flex items-center justify-between">
                <span className="text-sm flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                  <Cookie size={14} /> Cookie 状态
                </span>
                <span
                  className="font-mono text-xs px-2.5 py-1 rounded-full font-bold"
                  style={{
                    color: 'var(--accent-green)',
                    background: 'rgba(0, 255, 170, 0.1)',
                    border: '1px solid rgba(0, 255, 170, 0.25)',
                  }}
                >
                  VALID
                </span>
              </div>
              {/* 今日议价成功 */}
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>今日议价成功</span>
                <span className="font-mono text-lg font-bold" style={{ color: 'var(--accent-amber)' }}>12 单</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2 中: 交易 Bot 矩阵 (col-span-4) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>TRADING MATRIX</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              交易 Bot 矩阵
            </h3>

            <div className="space-y-3">
              {tradingBots.map((tb) => (
                <div key={tb.name}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{tb.name}</span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                      {tb.approve}% 通过
                    </span>
                  </div>
                  {/* 共识条 */}
                  <div className="flex h-2 rounded-full overflow-hidden gap-px">
                    <div
                      className="rounded-l-full transition-all"
                      style={{ width: `${tb.approve}%`, background: 'var(--accent-green)' }}
                    />
                    <div
                      className="transition-all"
                      style={{ width: `${tb.reject}%`, background: 'var(--accent-red)' }}
                    />
                    <div
                      className="rounded-r-full transition-all"
                      style={{ width: `${tb.pending}%`, background: 'var(--accent-amber)', opacity: 0.5 }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* 图例 */}
            <div className="flex items-center gap-4 mt-4 pt-3" style={{ borderTop: '1px solid var(--glass-border)' }}>
              {[
                { label: '通过', color: 'var(--accent-green)' },
                { label: '拒绝', color: 'var(--accent-red)' },
                { label: '待定', color: 'var(--accent-amber)' },
              ].map((l) => (
                <span key={l.label} className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                  <span className="w-2 h-2 rounded-full" style={{ background: l.color }} />
                  {l.label}
                </span>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2 右: 社媒发布 Bot (col-span-4) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>SOCIAL MEDIA</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              社媒发布 Bot
            </h3>

            {/* 平台列表 */}
            <div className="space-y-3 mb-5">
              {socialPlatforms.map((p) => (
                <div key={p.name} className="flex items-center justify-between">
                  <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
                  <div className="flex items-center gap-2">
                    <div className="flex gap-0.5">
                      {Array.from({ length: p.posts }).map((_, i) => (
                        <span
                          key={i}
                          className="w-1.5 h-4 rounded-sm"
                          style={{ background: p.color, opacity: 0.7 + (i * 0.1) }}
                        />
                      ))}
                    </div>
                    <span className="font-mono text-xs" style={{ color: p.color }}>{p.posts}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* 汇总指标 */}
            <div className="space-y-3 pt-3" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>定时发布</span>
                <span className="font-mono text-lg font-bold" style={{ color: 'var(--accent-amber)' }}>3 篇</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>今日已发</span>
                <span className="font-mono text-lg font-bold" style={{ color: 'var(--accent-green)' }}>5 篇</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>互动率</span>
                <span className="font-mono text-lg font-bold" style={{ color: 'var(--accent-cyan)' }}>4.2%</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3 左: Bot 活动日志 (col-span-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>ACTIVITY LOG</span>
              <Terminal size={14} style={{ color: 'var(--text-tertiary)' }} />
            </div>
            <h3 className="font-display text-lg font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              Bot 活动日志
            </h3>

            {/* 终端风格日志 */}
            <div
              className="rounded-xl p-4 space-y-2 font-mono text-xs overflow-y-auto max-h-[260px]"
              style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--glass-border)' }}
            >
              {logEntries.map((entry, i) => (
                <div key={i} className="flex gap-2 leading-relaxed">
                  <span style={{ color: 'var(--text-tertiary)' }}>{entry.time}</span>
                  <span
                    className="w-12 text-right flex-shrink-0 font-bold"
                    style={{ color: logColor(entry.level) }}
                  >
                    [{entry.level}]
                  </span>
                  <span
                    className="flex-shrink-0"
                    style={{ color: 'var(--accent-cyan)' }}
                  >
                    {entry.bot}
                  </span>
                  <span style={{ color: 'var(--text-secondary)' }}>→</span>
                  <span style={{ color: 'var(--text-primary)', opacity: 0.85 }}>{entry.message}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3 右: 快速操作 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>QUICK ACTIONS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              快速操作
            </h3>

            <div className="flex-1 grid grid-cols-1 gap-3">
              {quickActions.map((action) => {
                const Icon = action.icon;
                return (
                  <motion.button
                    key={action.label}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl cursor-pointer transition-colors text-left"
                    style={{
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--glass-border)',
                    }}
                    whileHover={{
                      background: 'rgba(255,255,255,0.06)',
                      borderColor: 'rgba(255,255,255,0.15)',
                    }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <span
                      className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{
                        background: `color-mix(in srgb, ${action.accent} 10%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${action.accent} 20%, transparent)`,
                      }}
                    >
                      <Icon size={16} style={{ color: action.accent }} />
                    </span>
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {action.label}
                    </span>
                  </motion.button>
                );
              })}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

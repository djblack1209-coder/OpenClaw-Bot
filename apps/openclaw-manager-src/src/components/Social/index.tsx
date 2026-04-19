import { motion } from 'framer-motion';
import {
  Share2,
  Flame,
  CalendarDays,
  BarChart3,
  Sparkles,
  Heart,
  MessageCircle,
  Repeat2,
  Globe,
  Clock,
  TrendingUp,
  Eye,
  FileText,
  Users,
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

/** 平台徽标颜色 */
const platformConfig: Record<string, { label: string; color: string; bg: string }> = {
  xhs: { label: '小红书', color: '#ff2442', bg: 'rgba(255,36,66,0.12)' },
  x: { label: 'X', color: 'var(--text-primary)', bg: 'rgba(255,255,255,0.08)' },
  weibo: { label: '微博', color: '#ff8200', bg: 'rgba(255,130,0,0.12)' },
};

/** 最近发帖 */
interface RecentPost {
  id: string;
  platform: string;
  title: string;
  time: string;
  likes: number;
  comments: number;
  shares: number;
}

const mockRecentPosts: RecentPost[] = [
  { id: '1', platform: 'xhs', title: 'AI 时代的个人效率提升指南', time: '10:32', likes: 234, comments: 18, shares: 42 },
  { id: '2', platform: 'x', title: 'Why autonomous agents will reshape SaaS', time: '09:15', likes: 89, comments: 12, shares: 31 },
  { id: '3', platform: 'xhs', title: '一个人如何运营 7 个 Bot', time: '08:40', likes: 567, comments: 45, shares: 128 },
  { id: '4', platform: 'weibo', title: '开源多智能体系统架构分享', time: '昨天', likes: 156, comments: 23, shares: 67 },
  { id: '5', platform: 'x', title: 'Building in public: week 12 update', time: '昨天', likes: 45, comments: 8, shares: 15 },
];

/** 平台状态 */
interface PlatformStatus {
  id: string;
  name: string;
  connected: boolean;
  followers: string;
  color: string;
}

const mockPlatforms: PlatformStatus[] = [
  { id: 'xhs', name: '小红书', connected: true, followers: '3,204', color: '#ff2442' },
  { id: 'x', name: 'X / Twitter', connected: true, followers: '8.9K', color: 'var(--accent-cyan)' },
  { id: 'weibo', name: '微博', connected: false, followers: '—', color: '#ff8200' },
];

/** 定时发布 */
interface ScheduledPost {
  id: string;
  time: string;
  platform: string;
  title: string;
}

const mockScheduled: ScheduledPost[] = [
  { id: '1', time: '14:00', platform: 'xhs', title: '如何用 AI 自动化社媒运营' },
  { id: '2', time: '16:30', platform: 'x', title: 'Thread: Multi-agent architecture patterns' },
  { id: '3', time: '明天 09:00', platform: 'weibo', title: '2026 AI 应用趋势预测' },
];

/** 热点话题 */
interface TrendingTopic {
  id: string;
  name: string;
  heat: number;
  platform: string;
}

const mockTrending: TrendingTopic[] = [
  { id: '1', name: 'AI Agent 自动化', heat: 98, platform: '全网' },
  { id: '2', name: '大模型降价潮', heat: 87, platform: '微博' },
  { id: '3', name: 'Claude 4 发布', heat: 82, platform: 'X' },
  { id: '4', name: '个人IP打造', heat: 76, platform: '小红书' },
  { id: '5', name: 'MCP 协议生态', heat: 71, platform: 'X' },
];

/* ====== 主组件 ====== */

/**
 * 社交媒体页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示社媒运营中心全部关键指标
 */
export function Social() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== Row 1: 社媒总控 (span-8, row-span-2) + 平台状态 (span-4) ====== */}

        {/* 社媒总控 */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题区域 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.15)' }}
              >
                <Share2 size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  社媒运营中心 // SOCIAL ENGINE
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  MULTI-PLATFORM // AUTO-DISTRIBUTE // AI-POWERED
                </p>
              </div>
            </div>

            {/* 关键指标：4 列 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <StatBlock icon={FileText} label="今日发帖" value="5" accent="var(--accent-cyan)" />
              <StatBlock icon={Users} label="总粉丝" value="12.4K" accent="var(--accent-purple)" />
              <StatBlock icon={TrendingUp} label="互动率" value="4.2%" accent="var(--accent-green)" />
              <StatBlock icon={Flame} label="热点追踪" value="3" accent="var(--accent-red)" />
            </div>

            {/* 最近帖子列表 */}
            <div>
              <span className="text-label mb-3 block" style={{ color: 'var(--text-tertiary)' }}>
                RECENT POSTS
              </span>
              <div className="space-y-2">
                {mockRecentPosts.map((post) => {
                  const pConfig = platformConfig[post.platform];
                  return (
                    <div
                      key={post.id}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors"
                      style={{ background: 'var(--bg-base)' }}
                    >
                      {/* 平台徽标 */}
                      <span
                        className="flex-shrink-0 px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                        style={{ background: pConfig.bg, color: pConfig.color }}
                      >
                        {pConfig.label}
                      </span>

                      {/* 标题 + 时间 */}
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-xs truncate block" style={{ color: 'var(--text-primary)' }}>
                          {post.title}
                        </span>
                      </div>

                      <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                        {post.time}
                      </span>

                      {/* 互动数据 */}
                      <div className="flex items-center gap-3 flex-shrink-0">
                        <span className="flex items-center gap-1">
                          <Heart size={10} style={{ color: 'var(--accent-red)' }} />
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{post.likes}</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageCircle size={10} style={{ color: 'var(--accent-cyan)' }} />
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{post.comments}</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <Repeat2 size={10} style={{ color: 'var(--accent-green)' }} />
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>{post.shares}</span>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* 平台状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Globe size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                PLATFORM STATUS
              </span>
            </div>

            <div className="space-y-3">
              {mockPlatforms.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center gap-3 p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}
                >
                  {/* 状态圆点 */}
                  <div className="relative flex-shrink-0">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ background: p.connected ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                    />
                    {p.connected && (
                      <div
                        className="absolute inset-0 w-3 h-3 rounded-full animate-ping opacity-30"
                        style={{ background: 'var(--accent-green)' }}
                      />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-xs font-medium block" style={{ color: 'var(--text-primary)' }}>
                      {p.name}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {p.connected ? '已连接' : '未连接'}
                    </span>
                  </div>

                  <div className="text-right flex-shrink-0">
                    <span className="font-display text-sm font-bold block" style={{ color: p.color }}>
                      {p.followers}
                    </span>
                    <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                      粉丝
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 内容日历 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <CalendarDays size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                CONTENT CALENDAR
              </span>
            </div>

            <div className="space-y-3">
              {mockScheduled.map((item) => {
                const pConfig = platformConfig[item.platform];
                return (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: 'var(--bg-base)' }}
                  >
                    {/* 时间 */}
                    <span
                      className="font-mono text-xs font-bold w-16 flex-shrink-0"
                      style={{ color: 'var(--accent-purple)' }}
                    >
                      {item.time}
                    </span>

                    {/* 平台 */}
                    <span
                      className="flex-shrink-0 px-1.5 py-0.5 rounded font-mono text-[9px] tracking-wider"
                      style={{ background: pConfig.bg, color: pConfig.color }}
                    >
                      {pConfig.label}
                    </span>

                    {/* 标题 */}
                    <span className="font-mono text-[11px] truncate" style={{ color: 'var(--text-secondary)' }}>
                      {item.title}
                    </span>
                  </div>
                );
              })}
            </div>

            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              定时任务自动发布 · 支持多平台同步
            </p>
          </div>
        </motion.div>

        {/* ====== Row 2: 热点追踪 (span-4) + AI 内容生成 (span-4) + 运营数据 (span-4) ====== */}

        {/* 热点追踪 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Flame size={16} style={{ color: 'var(--accent-red)' }} />
              <span className="text-label" style={{ color: 'var(--accent-red)' }}>
                TRENDING TOPICS
              </span>
            </div>

            <div className="space-y-2">
              {mockTrending.map((topic, i) => (
                <div
                  key={topic.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}
                >
                  {/* 排名 */}
                  <span
                    className="font-mono text-[10px] w-4 text-center flex-shrink-0"
                    style={{ color: i < 3 ? 'var(--accent-red)' : 'var(--text-disabled)' }}
                  >
                    {i + 1}
                  </span>

                  {/* 话题名 */}
                  <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                    {topic.name}
                  </span>

                  {/* 来源 */}
                  <span className="font-mono text-[9px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                    {topic.platform}
                  </span>

                  {/* 热度 */}
                  <HeatBar value={topic.heat} />
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* AI 内容生成 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Sparkles size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                AI CONTENT ENGINE
              </span>
            </div>

            <div className="space-y-4">
              <ContentStat label="今日生成" value="8" unit="篇" accent="var(--accent-cyan)" />
              <ContentStat label="待审核" value="2" unit="篇" accent="var(--accent-amber)" />
              <ContentStat label="已发布" value="5" unit="篇" accent="var(--accent-green)" />
              <ContentStat label="草稿箱" value="1" unit="篇" accent="var(--accent-purple)" />
            </div>

            {/* 底部进度 */}
            <div className="mt-5">
              <div className="flex justify-between mb-1.5">
                <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>TODAY CAPACITY</span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>8 / 15</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: 'var(--accent-amber)' }}
                  initial={{ width: 0 }}
                  animate={{ width: '53%' }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                />
              </div>
            </div>
          </div>
        </motion.div>

        {/* 运营数据 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                WEEKLY ANALYTICS
              </span>
            </div>

            <div className="space-y-4">
              <WeeklyStat icon={Eye} label="阅读量" value="23.4K" accent="var(--accent-cyan)" />
              <WeeklyStat icon={Heart} label="点赞" value="1.2K" accent="var(--accent-red)" />
              <WeeklyStat icon={MessageCircle} label="评论" value="348" accent="var(--accent-purple)" />
              <WeeklyStat icon={Users} label="新增粉丝" value="+127" accent="var(--accent-green)" />
            </div>

            {/* 周环比 */}
            <div
              className="mt-5 pt-3 flex items-center justify-between"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>周环比</span>
              <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-green)' }}>
                +18.3%
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

/** 概览统计块 */
function StatBlock({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={12} style={{ color: accent }} />
        <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <span className="text-metric" style={{ color: accent }}>{value}</span>
    </div>
  );
}

/** 热度条 — 红色渐变 */
function HeatBar({ value }: { value: number }) {
  const width = Math.round(value * 0.4);
  return (
    <div className="flex items-center gap-1.5 flex-shrink-0">
      <div className="w-10 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${value}%`,
            background: `linear-gradient(90deg, var(--accent-amber), var(--accent-red))`,
            opacity: 0.6 + value * 0.004,
          }}
        />
      </div>
      <span className="font-mono text-[9px] w-6 text-right" style={{ color: 'var(--accent-red)' }}>
        {value}
      </span>
    </div>
  );
}

/** AI 内容生成统计行 */
function ContentStat({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: string;
  unit: string;
  accent: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <div className="flex items-baseline gap-1">
        <span className="font-display text-lg font-bold" style={{ color: accent }}>
          {value}
        </span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
          {unit}
        </span>
      </div>
    </div>
  );
}

/** 周运营数据行 */
function WeeklyStat({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: `color-mix(in srgb, ${accent} 15%, transparent)` }}
      >
        <Icon size={14} style={{ color: accent }} />
      </div>
      <span className="font-mono text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <span className="font-display text-base font-bold" style={{ color: accent }}>
        {value}
      </span>
    </div>
  );
}

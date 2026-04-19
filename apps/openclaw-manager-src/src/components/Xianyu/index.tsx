import { motion } from 'framer-motion';
import {
  Fish,
  MessageSquare,
  ShoppingBag,
  TrendingUp,
  Cookie,
  Clock,
  Zap,
  ThumbsUp,
  UserCheck,
  Eye,
  BarChart3,
  RefreshCw,
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

/** 最近对话 */
interface Conversation {
  id: string;
  buyerName: string;
  avatarColor: string;     // 头像占位颜色
  lastMessage: string;
  time: string;
  status: 'replied' | 'pending' | 'closed';
}

const mockConversations: Conversation[] = [
  {
    id: '1',
    buyerName: '小明同学',
    avatarColor: 'var(--accent-cyan)',
    lastMessage: '请问这个还能便宜点吗？包邮吗',
    time: '2 分钟前',
    status: 'replied',
  },
  {
    id: '2',
    buyerName: '数码爱好者',
    avatarColor: 'var(--accent-purple)',
    lastMessage: '成色怎么样？有没有划痕',
    time: '8 分钟前',
    status: 'pending',
  },
  {
    id: '3',
    buyerName: '二手收藏家',
    avatarColor: 'var(--accent-green)',
    lastMessage: '好的，那我拍了哈',
    time: '15 分钟前',
    status: 'replied',
  },
  {
    id: '4',
    buyerName: '随便逛逛',
    avatarColor: 'var(--accent-amber)',
    lastMessage: '这个还在吗？',
    time: '1 小时前',
    status: 'closed',
  },
];

/** 商品列表 */
interface ProductItem {
  id: string;
  title: string;
  price: number;
  views: number;
  status: 'active' | 'sold' | 'paused';
}

const mockProducts: ProductItem[] = [
  { id: '1', title: 'MacBook Pro 2022 M2 几乎全新', price: 6800, views: 342, status: 'active' },
  { id: '2', title: 'AirPods Pro 2 充电盒有划痕', price: 880, views: 156, status: 'sold' },
  { id: '3', title: 'iPad Air 5 64G 紫色 带壳膜', price: 2900, views: 89, status: 'paused' },
];

/** 7 天收入模拟数据 */
const revenueData = [
  { day: '周一', value: 120 },
  { day: '周二', value: 350 },
  { day: '周三', value: 80 },
  { day: '周四', value: 580 },
  { day: '周五', value: 420 },
  { day: '周六', value: 260 },
  { day: '周日', value: 190 },
];

/* ====== 工具函数 ====== */

/** 状态徽标颜色映射 */
function statusBadge(status: Conversation['status']) {
  switch (status) {
    case 'replied':
      return { label: '已回复', color: 'var(--accent-green)', bg: 'rgba(34,197,94,0.1)' };
    case 'pending':
      return { label: '待回复', color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.1)' };
    case 'closed':
      return { label: '已关闭', color: 'var(--text-disabled)', bg: 'rgba(100,116,139,0.1)' };
  }
}

/** 商品状态映射 */
function productStatusBadge(status: ProductItem['status']) {
  switch (status) {
    case 'active':
      return { label: '在售', color: 'var(--accent-green)', bg: 'rgba(34,197,94,0.1)' };
    case 'sold':
      return { label: '已售', color: 'var(--accent-cyan)', bg: 'rgba(6,182,212,0.1)' };
    case 'paused':
      return { label: '已暂停', color: 'var(--text-disabled)', bg: 'rgba(100,116,139,0.1)' };
  }
}

/** 文本柱状图：用 block 字符渲染 */
function renderBar(value: number, maxValue: number, maxWidth: number = 20): string {
  const ratio = value / maxValue;
  const filled = Math.round(ratio * maxWidth);
  return '█'.repeat(filled) + '░'.repeat(maxWidth - filled);
}

/* ====== 主组件 ====== */

/**
 * 闲鱼管理页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示闲鱼 AI 客服引擎的全部关键指标
 */
export function Xianyu() {
  /* 7 天收入最大值，用于柱状图缩放 */
  const maxRevenue = Math.max(...revenueData.map((d) => d.value));

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：闲鱼概览 (span-8) + Cookie 状态 (span-4) ====== */}

        {/* 闲鱼概览卡片 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题区域 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <Fish size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  XIANYU AI AGENT
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  CUSTOMER SERVICE // AUTO-REPLY ENGINE
                </p>
              </div>
            </div>

            {/* 关键指标：4 列网格 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <StatBlock icon={ShoppingBag} label="在售商品" value="12" accent="var(--accent-cyan)" />
              <StatBlock icon={MessageSquare} label="今日对话" value="8" accent="var(--accent-purple)" />
              <StatBlock icon={TrendingUp} label="转化率" value="23%" accent="var(--accent-green)" />
              <StatBlock icon={BarChart3} label="今日收入" value="¥580" accent="var(--accent-amber)" />
            </div>

            {/* 最近对话列表 */}
            <div>
              <span className="text-label mb-3 block" style={{ color: 'var(--text-tertiary)' }}>
                RECENT CONVERSATIONS
              </span>
              <div className="space-y-2">
                {mockConversations.map((conv) => {
                  const badge = statusBadge(conv.status);
                  return (
                    <div
                      key={conv.id}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors"
                      style={{ background: 'var(--bg-base)' }}
                    >
                      {/* 头像占位：彩色圆形 */}
                      <div
                        className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center font-mono text-xs font-bold"
                        style={{ background: conv.avatarColor, color: 'var(--bg-base)' }}
                      >
                        {conv.buyerName[0]}
                      </div>

                      {/* 买家名称 + 最后消息 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                            {conv.buyerName}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {conv.time}
                          </span>
                        </div>
                        <p className="font-mono text-[11px] truncate mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                          {conv.lastMessage}
                        </p>
                      </div>

                      {/* 状态徽标 */}
                      <span
                        className="flex-shrink-0 px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                        style={{ background: badge.bg, color: badge.color }}
                      >
                        {badge.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Cookie 状态卡片 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题 */}
            <div className="flex items-center gap-2 mb-5">
              <Cookie size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                COOKIE STATUS
              </span>
            </div>

            {/* 大状态指示器 */}
            <div className="flex items-center gap-3 mb-6">
              <div className="relative">
                <div
                  className="w-4 h-4 rounded-full animate-pulse"
                  style={{ background: 'var(--accent-green)' }}
                />
                <div
                  className="absolute inset-0 w-4 h-4 rounded-full animate-ping opacity-40"
                  style={{ background: 'var(--accent-green)' }}
                />
              </div>
              <span className="font-display text-2xl font-bold tracking-wider" style={{ color: 'var(--accent-green)' }}>
                VALID
              </span>
            </div>

            {/* 详细信息 */}
            <div className="space-y-4">
              <InfoRow icon={Clock} label="上次同步" value="14:32:08" />
              <InfoRow icon={RefreshCw} label="下次同步" value="15:32:08" />
              <InfoRow icon={Zap} label="同步来源" value="CookieCloud" />

              {/* Cookie 有效期进度条 */}
              <div>
                <div className="flex justify-between mb-1.5">
                  <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>COOKIE AGE</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>2h 18m / 24h</span>
                </div>
                <div
                  className="h-1.5 rounded-full overflow-hidden"
                  style={{ background: 'var(--bg-base)' }}
                >
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: 'var(--accent-green)' }}
                    initial={{ width: 0 }}
                    animate={{ width: '9.6%' }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />
                </div>
              </div>
            </div>

            {/* 底部提示 */}
            <p className="font-mono text-[10px] mt-6" style={{ color: 'var(--text-disabled)' }}>
              CookieCloud 自动同步 · 1h 间隔 · 加密传输
            </p>
          </div>
        </motion.div>

        {/* ====== 第二行：商品列表 (span-4) + AI 回复表现 (span-4) + 收入图表 (span-4) ====== */}

        {/* 商品列表 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <ShoppingBag size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                PRODUCT LISTINGS
              </span>
            </div>

            <div className="space-y-3">
              {mockProducts.map((product) => {
                const badge = productStatusBadge(product.status);
                return (
                  <div
                    key={product.id}
                    className="p-3 rounded-xl"
                    style={{ background: 'var(--bg-base)' }}
                  >
                    {/* 商品标题 */}
                    <p className="font-mono text-xs truncate mb-2" style={{ color: 'var(--text-primary)' }}>
                      {product.title}
                    </p>

                    {/* 价格 + 浏览 + 状态 */}
                    <div className="flex items-center gap-2">
                      <span className="font-display text-sm font-bold" style={{ color: 'var(--accent-amber)' }}>
                        ¥{product.price.toLocaleString()}
                      </span>

                      <span className="flex items-center gap-1 ml-auto">
                        <Eye size={12} style={{ color: 'var(--text-disabled)' }} />
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {product.views}
                        </span>
                      </span>

                      <span
                        className="px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                        style={{ background: badge.bg, color: badge.color }}
                      >
                        {badge.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* AI 回复表现 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Zap size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                AI REPLY PERFORMANCE
              </span>
            </div>

            <div className="space-y-4">
              <PerfStat
                icon={MessageSquare}
                label="自动回复总数"
                value="156"
                sub="今日累计"
                accent="var(--accent-cyan)"
              />
              <PerfStat
                icon={Clock}
                label="平均响应时间"
                value="3.2s"
                sub="低于行业 5s 均值"
                accent="var(--accent-green)"
              />
              <PerfStat
                icon={ThumbsUp}
                label="客户满意度"
                value="92%"
                sub="基于评价反馈"
                accent="var(--accent-amber)"
              />
              <PerfStat
                icon={UserCheck}
                label="转人工率"
                value="8%"
                sub="自动处理 92% 咨询"
                accent="var(--accent-red)"
              />
            </div>
          </div>
        </motion.div>

        {/* 7 天收入图表 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                7-DAY REVENUE
              </span>
            </div>

            {/* 文本柱状图 */}
            <div className="space-y-2">
              {revenueData.map((d) => (
                <div key={d.day} className="flex items-center gap-2">
                  <span
                    className="font-mono text-[10px] w-8 text-right flex-shrink-0"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    {d.day}
                  </span>
                  <span
                    className="font-mono text-[11px] leading-none flex-1"
                    style={{ color: 'var(--accent-amber)', opacity: 0.7 + (d.value / maxRevenue) * 0.3 }}
                  >
                    {renderBar(d.value, maxRevenue, 16)}
                  </span>
                  <span
                    className="font-mono text-[10px] w-10 text-right flex-shrink-0"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    ¥{d.value}
                  </span>
                </div>
              ))}
            </div>

            {/* 汇总 */}
            <div
              className="mt-4 pt-3 flex justify-between items-baseline"
              style={{ borderTop: '1px solid var(--glass-border)' }}
            >
              <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>周合计</span>
              <span className="font-display text-lg font-bold" style={{ color: 'var(--accent-amber)' }}>
                ¥{revenueData.reduce((s, d) => s + d.value, 0).toLocaleString()}
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

/** 概览统计块 — 用于第一行的 4 列关键指标 */
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

/** Cookie 信息行 */
function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Icon size={13} style={{ color: 'var(--text-disabled)' }} />
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

/** AI 表现指标行 */
function PerfStat({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub: string;
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
      <div className="flex-1 min-w-0">
        <span className="font-mono text-[11px] block" style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{sub}</span>
      </div>
      <span className="font-display text-base font-bold" style={{ color: accent }}>{value}</span>
    </div>
  );
}

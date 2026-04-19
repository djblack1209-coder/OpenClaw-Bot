import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Search,
  Download,
  Star,
  Power,
  PowerOff,
  Trash2,
  Package,
  TrendingUp,
  Zap,
  Plus,
} from 'lucide-react';

/* ============================================================
   模拟数据
   ============================================================ */

/** 插件类型 */
interface Plugin {
  id: string;
  icon: string;
  name: string;
  description: string;
  author: string;
  installs: number;
  rating: number;
  category: string;
}

/** 已安装插件类型 */
interface InstalledPlugin {
  id: string;
  name: string;
  version: string;
  status: '运行中' | '已停止';
  updatedAt: string;
}

/** 全部可用插件 */
const MOCK_PLUGINS: Plugin[] = [
  { id: 'mcp-weather', icon: '🌦️', name: 'MCP 天气服务', description: '实时天气查询与预报推送', author: 'OpenClaw', installs: 3420, rating: 4.8, category: '数据源' },
  { id: 'binance-api', icon: '📈', name: '币安交易接口', description: '对接币安现货与合约交易', author: 'CryptoLab', installs: 8910, rating: 4.6, category: '交易工具' },
  { id: 'feishu-push', icon: '🔔', name: '飞书通知推送', description: '消息推送到飞书群组和个人', author: 'OpenClaw', installs: 2150, rating: 4.5, category: '通知推送' },
  { id: 'notion-sync', icon: '📝', name: 'Notion 同步', description: '双向同步 Notion 数据库', author: 'SyncTeam', installs: 5230, rating: 4.7, category: '数据源' },
  { id: 'github-issue', icon: '🐛', name: 'GitHub Issue 追踪', description: '自动追踪和管理 GitHub Issue', author: 'DevTools', installs: 4100, rating: 4.4, category: '开发工具' },
  { id: 'tts-engine', icon: '🗣️', name: '语音合成引擎', description: '多语言高质量语音合成', author: 'VoiceLab', installs: 1870, rating: 4.3, category: 'AI增强' },
  { id: 'okx-api', icon: '💹', name: 'OKX 交易接口', description: '对接 OKX 全品种交易', author: 'CryptoLab', installs: 6700, rating: 4.5, category: '交易工具' },
  { id: 'wechat-push', icon: '💬', name: '微信通知推送', description: '通过企业微信推送消息', author: 'OpenClaw', installs: 3800, rating: 4.2, category: '通知推送' },
  { id: 'redis-cache', icon: '⚡', name: 'Redis 缓存加速', description: '高性能缓存与消息队列', author: 'DevTools', installs: 2900, rating: 4.6, category: '开发工具' },
  { id: 'image-gen', icon: '🎨', name: 'AI 图片生成', description: '文生图与图生图能力', author: 'VoiceLab', installs: 7200, rating: 4.9, category: 'AI增强' },
  { id: 'crypto-data', icon: '📊', name: '加密行情数据', description: '实时K线与深度数据', author: 'CryptoLab', installs: 5100, rating: 4.7, category: '数据源' },
  { id: 'bybit-api', icon: '🏦', name: 'Bybit 交易接口', description: '对接 Bybit 衍生品交易', author: 'CryptoLab', installs: 4300, rating: 4.4, category: '交易工具' },
  { id: 'dingtalk-push', icon: '📢', name: '钉钉通知推送', description: '消息推送到钉钉群组', author: 'OpenClaw', installs: 1600, rating: 4.1, category: '通知推送' },
  { id: 'openai-enhance', icon: '🧠', name: 'OpenAI 增强', description: '接入 GPT-4o 与 o1 模型', author: 'OpenClaw', installs: 9500, rating: 4.8, category: 'AI增强' },
  { id: 'freqtrade', icon: '🤖', name: 'Freqtrade 量化', description: '开源量化交易框架集成', author: 'FreqTeam', installs: 6200, rating: 4.5, category: '交易工具' },
  { id: 'vectorbt', icon: '📉', name: 'VectorBT 回测', description: '向量化策略回测引擎', author: 'VBT', installs: 3100, rating: 4.3, category: '交易工具' },
  { id: 'crawl4ai', icon: '🕷️', name: 'Crawl4AI 爬虫', description: 'AI 驱动的智能爬虫', author: 'DevTools', installs: 4800, rating: 4.6, category: '开发工具' },
  { id: 'mem0-memory', icon: '🧬', name: 'Mem0 记忆系统', description: 'AI 长期记忆管理', author: 'Mem0', installs: 2400, rating: 4.4, category: 'AI增强' },
  { id: 'yfinance', icon: '📰', name: '雅虎行情数据', description: '全球股票与加密行情', author: 'FinData', installs: 5600, rating: 4.5, category: '数据源' },
  { id: 'stripe-api', icon: '💳', name: 'Stripe 支付', description: '国际支付接口集成', author: 'PayTeam', installs: 3300, rating: 4.6, category: '交易工具' },
  { id: 'telegram-push', icon: '✈️', name: 'Telegram 通知', description: '通过 TG Bot 推送消息', author: 'OpenClaw', installs: 4200, rating: 4.7, category: '通知推送' },
  { id: 'whisper-stt', icon: '🎤', name: 'Whisper 语音识别', description: '高精度语音转文字', author: 'VoiceLab', installs: 5800, rating: 4.8, category: 'AI增强' },
  { id: 'supabase-db', icon: '🗄️', name: 'Supabase 数据库', description: '实时数据库与认证', author: 'DevTools', installs: 3900, rating: 4.5, category: '数据源' },
  { id: 'drission', icon: '🌐', name: 'DrissionPage 爬虫', description: '浏览器自动化与爬虫', author: 'DevTools', installs: 2700, rating: 4.3, category: '开发工具' },
];

/** 分类及计数 */
const CATEGORIES = [
  { label: '全部', count: 24 },
  { label: '交易工具', count: 8 },
  { label: '数据源', count: 6 },
  { label: '通知推送', count: 4 },
  { label: 'AI增强', count: 3 },
  { label: '开发工具', count: 3 },
];

/** 已安装插件列表 */
const INSTALLED_PLUGINS: InstalledPlugin[] = [
  { id: 'mcp-weather', name: 'MCP 天气服务', version: '1.2.0', status: '运行中', updatedAt: '2026-04-18' },
  { id: 'binance-api', name: '币安交易接口', version: '3.1.4', status: '运行中', updatedAt: '2026-04-17' },
  { id: 'feishu-push', name: '飞书通知推送', version: '2.0.1', status: '已停止', updatedAt: '2026-04-15' },
  { id: 'notion-sync', name: 'Notion 同步', version: '1.0.8', status: '运行中', updatedAt: '2026-04-16' },
];

/* ============================================================
   动画配置
   ============================================================ */

/** 卡片进场动画 */
const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] },
  }),
};

/** 渲染星级评分 */
function RatingStars({ rating }: { rating: number }) {
  const full = Math.floor(rating);
  const hasHalf = rating - full >= 0.3;
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          size={10}
          className={clsx(
            i < full
              ? 'text-[var(--accent-amber)] fill-[var(--accent-amber)]'
              : i === full && hasHalf
                ? 'text-[var(--accent-amber)] fill-[var(--accent-amber)]/50'
                : 'text-[var(--text-disabled)]'
          )}
        />
      ))}
      <span className="font-mono text-[10px] text-[var(--text-tertiary)] ml-0.5">
        {rating.toFixed(1)}
      </span>
    </span>
  );
}

/* ============================================================
   Store 主组件
   ============================================================ */

export function Store() {
  /* 搜索词和选中分类 */
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('全部');

  /* 过滤插件列表 */
  const filtered = useMemo(() => {
    let list = MOCK_PLUGINS;
    if (category !== '全部') {
      list = list.filter((p) => p.category === category);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q) ||
          p.author.toLowerCase().includes(q)
      );
    }
    return list;
  }, [search, category]);

  /* 精选插件（前 6 个） */
  const featured = filtered.slice(0, 6);

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-base)] p-6">
      {/* 12 列 Bento 网格容器 */}
      <div className="grid grid-cols-12 gap-4 auto-rows-min">

        {/* ====== 搜索栏 — 全宽 ====== */}
        <div className="col-span-12">
          <div className="abyss-card px-5 py-3 flex items-center gap-3">
            <Search size={18} className="text-[var(--text-tertiary)] shrink-0" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索插件名称、描述、作者…"
              className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] outline-none font-mono"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] text-xs"
              >
                清除
              </button>
            )}
          </div>
        </div>

        {/* ====== 精选插件 — col-span-8, row-span-2 ====== */}
        <motion.div
          className="col-span-8 row-span-2 abyss-card p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          {/* 标题区域 */}
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-display text-lg font-bold text-[var(--text-primary)] tracking-tight">
                精选插件
              </h2>
              <p className="text-label mt-1">
                插件商店 // PLUGIN MARKETPLACE
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[var(--accent-cyan)]">
              <Package size={16} />
              <span className="font-mono text-xs">{filtered.length} 个结果</span>
            </div>
          </div>

          {/* 6 个插件卡片网格 — 2 行 × 3 列 */}
          <div className="grid grid-cols-3 gap-3">
            {featured.map((plugin, i) => (
              <motion.div
                key={plugin.id}
                custom={i}
                variants={cardVariants}
                initial="hidden"
                animate="visible"
                className="group relative rounded-2xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] p-4 hover:border-[var(--accent-cyan)]/30 transition-all duration-300"
              >
                {/* 图标 + 名称 */}
                <div className="flex items-start gap-3 mb-2.5">
                  <span className="text-2xl leading-none">{plugin.icon}</span>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                      {plugin.name}
                    </h3>
                    <p className="text-[11px] text-[var(--text-tertiary)] truncate mt-0.5">
                      {plugin.description}
                    </p>
                  </div>
                </div>

                {/* 作者 + 安装数 + 评分 */}
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] text-[var(--text-tertiary)] font-mono">
                    {plugin.author}
                  </span>
                  <span className="text-[10px] text-[var(--text-tertiary)] font-mono flex items-center gap-1">
                    <Download size={9} />
                    {plugin.installs.toLocaleString()}
                  </span>
                </div>

                {/* 评分星星 */}
                <div className="flex items-center justify-between">
                  <RatingStars rating={plugin.rating} />
                  <button className="px-3 py-1 rounded-full border border-[var(--accent-cyan)]/40 text-[var(--accent-cyan)] text-[11px] font-mono hover:bg-[var(--accent-cyan)]/10 transition-colors">
                    安装
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* ====== 分类筛选 — col-span-4 ====== */}
        <motion.div
          className="col-span-4 abyss-card p-5"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <h3 className="text-label mb-4">分类筛选 // CATEGORIES</h3>
          <div className="space-y-1">
            {CATEGORIES.map((cat) => {
              const active = category === cat.label;
              return (
                <button
                  key={cat.label}
                  onClick={() => setCategory(cat.label)}
                  className={clsx(
                    'w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all duration-200',
                    active
                      ? 'bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] border border-[var(--accent-cyan)]/20'
                      : 'text-[var(--text-secondary)] hover:bg-white/[0.03] hover:text-[var(--text-primary)] border border-transparent'
                  )}
                >
                  <span className="font-medium">{cat.label}</span>
                  <span
                    className={clsx(
                      'font-mono text-xs px-2 py-0.5 rounded-full',
                      active
                        ? 'bg-[var(--accent-cyan)]/20 text-[var(--accent-cyan)]'
                        : 'bg-white/[0.05] text-[var(--text-tertiary)]'
                    )}
                  >
                    {cat.count}
                  </span>
                </button>
              );
            })}
          </div>
        </motion.div>

        {/* ====== 统计 — col-span-4（分类下方） ====== */}
        <motion.div
          className="col-span-4 abyss-card p-5"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <h3 className="text-label mb-4">统计概览 // STATS</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: '已安装', value: '6', icon: Package, color: 'var(--accent-cyan)' },
              { label: '可更新', value: '2', icon: TrendingUp, color: 'var(--accent-amber)' },
              { label: '总插件数', value: '24', icon: Zap, color: 'var(--accent-green)' },
              { label: '本周新增', value: '3', icon: Plus, color: 'var(--accent-purple)' },
            ].map((stat) => (
              <div
                key={stat.label}
                className="rounded-xl bg-white/[0.02] border border-[var(--glass-border)] p-3 text-center"
              >
                <stat.icon size={16} className="mx-auto mb-2" style={{ color: stat.color }} />
                <div className="text-metric text-xl">{stat.value}</div>
                <div className="text-label text-[9px] mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* ====== 已安装插件 — col-span-12 ====== */}
        <motion.div
          className="col-span-12 abyss-card p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
        >
          <h3 className="text-label mb-4">已安装插件 // INSTALLED</h3>

          {/* 表头 */}
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr] gap-4 px-4 py-2 text-[10px] text-[var(--text-tertiary)] font-mono uppercase tracking-widest border-b border-[var(--glass-border)]">
            <span>名称</span>
            <span>版本</span>
            <span>状态</span>
            <span>更新时间</span>
            <span className="text-right">操作</span>
          </div>

          {/* 行数据 */}
          {INSTALLED_PLUGINS.map((p, i) => (
            <motion.div
              key={p.id}
              custom={i}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr] gap-4 px-4 py-3.5 items-center border-b border-[var(--glass-border)]/50 last:border-b-0 hover:bg-white/[0.02] transition-colors"
            >
              {/* 名称 */}
              <span className="text-sm text-[var(--text-primary)] font-medium">{p.name}</span>

              {/* 版本 */}
              <span className="font-mono text-xs text-[var(--text-tertiary)]">v{p.version}</span>

              {/* 状态 */}
              <span className="flex items-center gap-1.5 text-xs">
                <span
                  className={clsx(
                    'w-1.5 h-1.5 rounded-full',
                    p.status === '运行中' ? 'bg-[var(--accent-green)]' : 'bg-[var(--accent-red)]'
                  )}
                />
                <span
                  className={clsx(
                    'font-mono',
                    p.status === '运行中' ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'
                  )}
                >
                  {p.status}
                </span>
              </span>

              {/* 更新时间 */}
              <span className="font-mono text-xs text-[var(--text-tertiary)]">{p.updatedAt}</span>

              {/* 操作按钮组 */}
              <div className="flex items-center justify-end gap-2">
                {p.status === '运行中' ? (
                  <button className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--accent-amber)]/30 text-[var(--accent-amber)] text-[11px] font-mono hover:bg-[var(--accent-amber)]/10 transition-colors">
                    <PowerOff size={11} />
                    禁用
                  </button>
                ) : (
                  <button className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--accent-green)]/30 text-[var(--accent-green)] text-[11px] font-mono hover:bg-[var(--accent-green)]/10 transition-colors">
                    <Power size={11} />
                    启用
                  </button>
                )}
                <button className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--accent-red)]/30 text-[var(--accent-red)] text-[11px] font-mono hover:bg-[var(--accent-red)]/10 transition-colors">
                  <Trash2 size={11} />
                  卸载
                </button>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}

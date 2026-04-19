/**
 * APIGateway — API 网关页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Network, Key, Activity,
  Terminal, Gauge, ArrowUpRight,
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
  { label: '总路由数', value: '24', color: 'var(--accent-cyan)' },
  { label: '活跃连接', value: '18', color: 'var(--accent-green)' },
  { label: '今日请求', value: '12,847', color: 'var(--accent-amber)' },
  { label: '错误率', value: '0.3%', color: 'var(--accent-red)' },
];

/** 路由表 */
interface RouteEntry {
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  status: 'active' | 'degraded' | 'down';
  latency: string;
  requests: number;
}

const ROUTES: RouteEntry[] = [
  { path: '/api/v1/chat/completions', method: 'POST', status: 'active', latency: '142ms', requests: 4820 },
  { path: '/api/v1/models', method: 'GET', status: 'active', latency: '28ms', requests: 2340 },
  { path: '/api/v1/embeddings', method: 'POST', status: 'active', latency: '87ms', requests: 1890 },
  { path: '/api/v1/images/generations', method: 'POST', status: 'degraded', latency: '1.2s', requests: 456 },
  { path: '/api/v1/audio/transcriptions', method: 'POST', status: 'active', latency: '340ms', requests: 312 },
  { path: '/api/v1/channels', method: 'GET', status: 'active', latency: '15ms', requests: 1240 },
  { path: '/api/v1/tokens', method: 'GET', status: 'active', latency: '12ms', requests: 890 },
  { path: '/api/v1/health', method: 'GET', status: 'active', latency: '3ms', requests: 899 },
];

/** API 令牌 */
interface APIToken {
  name: string;
  created: string;
  lastUsed: string;
  status: 'active' | 'expired';
  key: string;
}

const TOKENS: APIToken[] = [
  { name: '生产环境主令牌', created: '2026-01-15', lastUsed: '2分钟前', status: 'active', key: 'sk-oc-prod-****7f3a' },
  { name: '测试环境令牌', created: '2026-03-02', lastUsed: '1小时前', status: 'active', key: 'sk-oc-test-****b2e1' },
  { name: '旧版兼容令牌', created: '2025-11-20', lastUsed: '30天前', status: 'expired', key: 'sk-oc-old-****9d44' },
];

/** 请求分布 */
const METHOD_DIST = [
  { method: 'GET', pct: 60, color: 'var(--accent-cyan)' },
  { method: 'POST', pct: 30, color: 'var(--accent-green)' },
  { method: 'PUT', pct: 8, color: 'var(--accent-amber)' },
  { method: 'DELETE', pct: 2, color: 'var(--accent-red)' },
];

/** 网关日志 */
const LOGS = [
  { ts: '14:35:02', msg: '[GW] POST /chat/completions → 200 (142ms) — Anthropic' },
  { ts: '14:34:58', msg: '[GW] GET  /models → 200 (28ms) — 缓存命中' },
  { ts: '14:34:45', msg: '[GW] POST /images/generations → 504 (5.0s) — 超时重试' },
  { ts: '14:34:30', msg: '[GW] POST /embeddings → 200 (87ms) — SiliconFlow' },
  { ts: '14:34:12', msg: '[GW] GET  /health → 200 (3ms) — 心跳正常' },
];

/* ====== 工具函数 ====== */
const METHOD_COLORS: Record<string, string> = { GET: 'var(--accent-cyan)', POST: 'var(--accent-green)', PUT: 'var(--accent-amber)', DELETE: 'var(--accent-red)' };
const methodColor = (m: string) => METHOD_COLORS[m] ?? 'var(--text-secondary)';
const STATUS_DOT: Record<string, string> = { active: 'var(--accent-green)', degraded: 'var(--accent-amber)', down: 'var(--accent-red)' };
const routeStatusDot = (s: string) => STATUS_DOT[s] ?? 'var(--text-disabled)';

/* ====== 主组件 ====== */

export function APIGateway() {
  /* 速率限制模拟 */
  const rateLimit = 1000;
  const rateCurrent = 342;
  const ratePct = Math.round((rateCurrent / rateLimit) * 100);

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 网关概览 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.12)' }}
              >
                <Network size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  GATEWAY CONTROLLER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  API 网关 // UNIFIED PROXY
                </p>
              </div>
            </div>

            {/* 统计 4 格 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {OVERVIEW_STATS.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color, fontSize: '20px' }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 路由表 */}
            <span className="text-label mb-2" style={{ color: 'var(--text-tertiary)' }}>
              ROUTE TABLE
            </span>

            {/* 表头 */}
            <div
              className="grid grid-cols-12 gap-2 px-4 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              <span className="text-label col-span-5" style={{ fontSize: '10px' }}>路径</span>
              <span className="text-label col-span-2 text-center" style={{ fontSize: '10px' }}>方法</span>
              <span className="text-label col-span-1 text-center" style={{ fontSize: '10px' }}>状态</span>
              <span className="text-label col-span-2 text-right" style={{ fontSize: '10px' }}>响应时间</span>
              <span className="text-label col-span-2 text-right" style={{ fontSize: '10px' }}>请求数</span>
            </div>

            {/* 路由行 */}
            <div className="flex-1 space-y-1 overflow-y-auto">
              {ROUTES.map((r) => (
                <div
                  key={r.path}
                  className="grid grid-cols-12 gap-2 items-center py-2.5 px-4 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span className="font-mono text-xs col-span-5 truncate" style={{ color: 'var(--text-primary)' }}>
                    {r.path}
                  </span>
                  <div className="col-span-2 flex justify-center">
                    <span
                      className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider font-bold"
                      style={{ background: `${methodColor(r.method)}15`, color: methodColor(r.method) }}
                    >
                      {r.method}
                    </span>
                  </div>
                  <div className="col-span-1 flex justify-center">
                    <span
                      className={clsx('w-2 h-2 rounded-full', r.status === 'active' && 'animate-pulse')}
                      style={{ background: routeStatusDot(r.status) }}
                    />
                  </div>
                  <span className="font-mono text-[10px] col-span-2 text-right" style={{ color: 'var(--text-secondary)' }}>
                    {r.latency}
                  </span>
                  <span className="font-mono text-[10px] col-span-2 text-right" style={{ color: 'var(--text-disabled)' }}>
                    {r.requests.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 令牌管理 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              TOKEN MANAGEMENT
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              令牌管理
            </h3>

            <div className="flex-1 space-y-3">
              {TOKENS.map((tk) => {
                const isActive = tk.status === 'active';
                return (
                  <div
                    key={tk.name}
                    className="py-3 px-4 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                        {tk.name}
                      </span>
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ background: isActive ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                      />
                    </div>
                    <div className="font-mono text-[10px] py-1.5 px-2 rounded" style={{ background: 'var(--bg-base)', color: 'var(--text-disabled)' }}>
                      <Key size={10} className="inline mr-1" style={{ color: 'var(--accent-amber)' }} />
                      {tk.key}
                    </div>
                    <div className="flex justify-between mt-2">
                      <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                        创建: {tk.created}
                      </span>
                      <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                        最近: {tk.lastUsed}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 流量统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              TRAFFIC DISTRIBUTION
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              流量统计
            </h3>

            <div className="flex-1 space-y-3">
              {METHOD_DIST.map((md) => (
                <div key={md.method}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-xs font-bold" style={{ color: md.color }}>
                      {md.method}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                      {md.pct}%
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full" style={{ background: 'var(--bg-tertiary)' }}>
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${md.pct}%`, background: md.color }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* 总请求趋势 */}
            <div className="mt-4 pt-4 flex items-center gap-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <Activity size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                12,847 请求
              </span>
              <span className="font-mono text-[10px] flex items-center gap-0.5 ml-auto" style={{ color: 'var(--accent-green)' }}>
                <ArrowUpRight size={10} /> +8.3%
              </span>
            </div>
          </div>
        </motion.div>

        {/* ====== 速率限制 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-red)' }}>
              RATE LIMITING
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              速率限制
            </h3>

            <div className="flex-1 flex flex-col justify-center">
              {/* 全局限制 */}
              <div className="mb-4">
                <span className="text-label">全局限制</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-cyan)', fontSize: '20px' }}>
                    {rateLimit.toLocaleString()}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    /min
                  </span>
                </div>
              </div>

              {/* 当前使用 */}
              <div className="mb-4">
                <span className="text-label">当前使用</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-green)', fontSize: '20px' }}>
                    {rateCurrent}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    /min
                  </span>
                </div>
              </div>

              {/* 进度条 */}
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-label">使用率</span>
                  <span className="font-mono text-[10px]" style={{ color: ratePct > 80 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {ratePct}%
                  </span>
                </div>
                <div className="w-full h-3 rounded-full" style={{ background: 'var(--bg-tertiary)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${ratePct}%`,
                      background: ratePct > 80 ? 'var(--accent-red)' : ratePct > 50 ? 'var(--accent-amber)' : 'var(--accent-green)',
                    }}
                  />
                </div>
              </div>

              <div className="flex items-center gap-1.5 mt-3">
                <Gauge size={12} style={{ color: 'var(--text-disabled)' }} />
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  容量充足 — 无需扩容
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 网关日志 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                  GATEWAY LOG
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  网关日志
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
              <span className="font-mono text-[10px] animate-pulse" style={{ color: 'var(--accent-cyan)' }}>
                █
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

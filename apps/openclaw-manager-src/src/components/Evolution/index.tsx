/**
 * Evolution — 进化引擎页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Dna, Zap, TrendingUp, CheckCircle2,
  Clock, ArrowUpRight, Sparkles, Terminal,
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

/** 进化状态记录 */
interface EvolutionRecord {
  time: string;
  type: string;
  typeColor: string;
  desc: string;
  status: '成功' | '执行中' | '已跳过';
}

const RECORDS: EvolutionRecord[] = [
  { time: '14:32', type: '性能优化', typeColor: 'var(--accent-green)', desc: '缓存策略升级 — LRU → LFU，命中率 +18%', status: '成功' },
  { time: '13:15', type: '依赖更新', typeColor: 'var(--accent-cyan)', desc: 'litellm 1.56 → 1.61，修复 token 计数偏移', status: '成功' },
  { time: '12:47', type: '架构优化', typeColor: 'var(--accent-purple)', desc: '消息队列拆分为独立 worker，吞吐量 +35%', status: '执行中' },
  { time: '11:20', type: '安全修复', typeColor: 'var(--accent-red)', desc: '修补 JWT 过期校验漏洞 CVE-2026-0412', status: '成功' },
  { time: '09:05', type: '资源回收', typeColor: 'var(--accent-amber)', desc: '清理 3 个废弃插件，释放 120MB 内存', status: '已跳过' },
];

/** 待执行优化 */
interface PendingOptimization {
  priority: '高' | '中' | '低';
  desc: string;
  benefit: string;
}

const PENDING: PendingOptimization[] = [
  { priority: '高', desc: '数据库连接池动态扩缩容', benefit: '预估降低 40% 连接超时' },
  { priority: '中', desc: 'API 响应压缩启用 Brotli', benefit: '带宽节省约 25%' },
  { priority: '低', desc: '日志采集切换到异步写入', benefit: '减少主线程阻塞 8ms' },
];

/** 进化日志 */
const LOGS = [
  { ts: '14:32:18', msg: '[EVOLVE] 缓存策略优化完成 — 命中率 72% → 90%' },
  { ts: '13:15:42', msg: '[DEPS]   litellm 升级到 1.61.2 — 通过回归测试' },
  { ts: '12:47:05', msg: '[ARCH]   启动消息队列拆分 — 预估耗时 12min' },
  { ts: '11:20:33', msg: '[SEC]    JWT 漏洞已修补 — 签发新令牌' },
  { ts: '09:05:11', msg: '[CLEAN]  跳过资源回收 — 内存占用未达阈值' },
  { ts: '08:00:00', msg: '[CYCLE]  第 47 轮进化周期启动 — 扫描 6 个模块' },
];

/* ====== 工具函数 ====== */

/** 优先级颜色 */
function priorityColor(p: string) {
  if (p === '高') return 'var(--accent-red)';
  if (p === '中') return 'var(--accent-amber)';
  return 'var(--accent-green)';
}

/** 状态显示 */
function statusStyle(s: EvolutionRecord['status']) {
  switch (s) {
    case '成功': return { color: 'var(--accent-green)', Icon: CheckCircle2 };
    case '执行中': return { color: 'var(--accent-cyan)', Icon: Zap };
    case '已跳过': return { color: 'var(--text-disabled)', Icon: Clock };
  }
}

/* ====== 主组件 ====== */

export function Evolution() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 进化状态 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,255,170,0.12)' }}
              >
                <Dna size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  AUTO-EVOLUTION
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  进化引擎 // SELF-OPTIMIZATION
                </p>
              </div>
            </div>

            {/* 进化周期指标 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {[
                { label: '当前周期', value: '第 47 轮', color: 'var(--accent-cyan)' },
                { label: '发现机会', value: '12', color: 'var(--accent-amber)' },
                { label: '已执行优化', value: '8', color: 'var(--accent-green)' },
                { label: '成功率', value: '87.5%', color: 'var(--accent-green)' },
              ].map((m) => (
                <div key={m.label}>
                  <span className="text-label">{m.label}</span>
                  <p className="font-mono text-sm font-bold mt-1" style={{ color: m.color }}>
                    {m.value}
                  </p>
                </div>
              ))}
            </div>

            {/* 最近进化记录 */}
            <span className="text-label mb-2" style={{ color: 'var(--text-tertiary)' }}>
              RECENT EVOLUTION
            </span>
            <div className="flex-1 space-y-1.5">
              {RECORDS.map((r, i) => {
                const ss = statusStyle(r.status);
                return (
                  <div
                    key={i}
                    className="flex items-center gap-3 py-2.5 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <span className="font-mono text-[10px] w-10 shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {r.time}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider shrink-0"
                      style={{ background: `${r.typeColor}15`, color: r.typeColor }}
                    >
                      {r.type}
                    </span>
                    <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                      {r.desc}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <ss.Icon size={12} style={{ color: ss.color }} />
                      <span className="font-mono text-[10px]" style={{ color: ss.color }}>
                        {r.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 进化指标 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              EVOLUTION METRICS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              进化指标
            </h3>

            <div className="space-y-5 flex-1">
              {/* 系统评分 */}
              <div>
                <span className="text-label">系统评分</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-green)' }}>8.4</span>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>/10</span>
                </div>
                {/* 评分条 */}
                <div className="w-full h-2 rounded-full mt-2" style={{ background: 'var(--bg-tertiary)' }}>
                  <div className="h-full rounded-full" style={{ width: '84%', background: 'var(--accent-green)' }} />
                </div>
              </div>

              {/* 本周优化 */}
              <div>
                <span className="text-label">本周优化</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-cyan)' }}>23</span>
                  <span className="font-mono text-[10px] flex items-center gap-0.5" style={{ color: 'var(--accent-green)' }}>
                    <ArrowUpRight size={10} /> +15%
                  </span>
                </div>
              </div>

              {/* 性能提升 */}
              <div>
                <span className="text-label">性能提升</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-amber)' }}>+12%</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>对比上周</span>
                </div>
              </div>

              {/* 资源节省 */}
              <div>
                <span className="text-label">资源节省</span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-metric" style={{ color: 'var(--accent-purple)' }}>¥340</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>本月累计</span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 待执行优化 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              PENDING OPTIMIZATIONS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              待执行优化
            </h3>

            <div className="flex-1 space-y-2">
              {PENDING.map((p, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 py-3 px-4 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <span
                    className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider mt-0.5 shrink-0"
                    style={{
                      background: `${priorityColor(p.priority)}15`,
                      color: priorityColor(p.priority),
                    }}
                  >
                    {p.priority}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {p.desc}
                    </p>
                    <p className="font-mono text-[10px] mt-1 flex items-center gap-1" style={{ color: 'var(--text-disabled)' }}>
                      <Sparkles size={10} style={{ color: 'var(--accent-amber)' }} />
                      {p.benefit}
                    </p>
                  </div>
                  <TrendingUp size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-green)' }} />
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 进化日志 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  EVOLUTION LOG
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  进化日志
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
                  <span
                    className={clsx('font-mono text-[11px] leading-relaxed')}
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {l.msg}
                  </span>
                </div>
              ))}
              <span className="font-mono text-[10px] animate-pulse" style={{ color: 'var(--accent-green)' }}>
                █
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

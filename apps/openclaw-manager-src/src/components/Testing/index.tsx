/**
 * Testing — 测试诊断页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学，全模拟数据
 */
import { motion } from 'framer-motion';
import {
  FlaskConical,
  Play,
  RefreshCw,
  FileBarChart,
  Stethoscope,
  CheckCircle2,
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
const TEST_STATS = [
  { label: '总用例', value: '1,461', color: 'var(--accent-cyan)' },
  { label: '通过', value: '1,461', color: 'var(--accent-green)' },
  { label: '失败', value: '0', color: 'var(--accent-red)' },
  { label: '覆盖率', value: '73%', color: 'var(--accent-amber)' },
];

/** 测试模块 */
interface TestModule { name: string; total: number; passed: number; status: 'pass' | 'partial' | 'fail' }
const TEST_MODULES: TestModule[] = [
  { name: 'core/路由引擎', total: 312, passed: 312, status: 'pass' },
  { name: 'bots/Bot管理器', total: 245, passed: 245, status: 'pass' },
  { name: 'handlers/消息处理', total: 398, passed: 398, status: 'pass' },
  { name: 'services/AI集成', total: 187, passed: 187, status: 'pass' },
  { name: 'services/渠道适配', total: 156, passed: 156, status: 'pass' },
  { name: 'utils/工具函数', total: 163, passed: 163, status: 'pass' },
];

/** 快速操作 */
interface QuickAction { label: string; desc: string; icon: typeof Play; color: string }
const QUICK_ACTIONS: QuickAction[] = [
  { label: '运行全部测试', desc: 'pytest tests/ -x', icon: Play, color: 'var(--accent-green)' },
  { label: '运行失败测试', desc: 'pytest --lf', icon: RefreshCw, color: 'var(--accent-amber)' },
  { label: '生成覆盖率报告', desc: 'pytest --cov', icon: FileBarChart, color: 'var(--accent-cyan)' },
  { label: '系统诊断', desc: 'run_doctor', icon: Stethoscope, color: 'var(--accent-purple)' },
];

/** 终端输出 */
const TERMINAL_OUTPUT: { text: string; color?: string }[] = [
  { text: '$ pytest tests/ -x --tb=short -q', color: 'var(--text-primary)' },
  { text: '' },
  { text: 'tests/core/test_router.py ............................ [312/1461]', color: 'var(--accent-green)' },
  { text: 'tests/bots/test_manager.py .......................... [557/1461]', color: 'var(--accent-green)' },
  { text: 'tests/handlers/test_message.py ...................... [955/1461]', color: 'var(--accent-green)' },
  { text: 'tests/services/test_ai.py .......................... [1142/1461]', color: 'var(--accent-green)' },
  { text: 'tests/services/test_channel.py ..................... [1298/1461]', color: 'var(--accent-green)' },
  { text: 'tests/utils/test_helpers.py ........................ [1461/1461]', color: 'var(--accent-green)' },
  { text: '' },
  { text: '================================ 1461 passed in 23.4s ================================', color: 'var(--accent-green)' },
  { text: '' },
  { text: '---------- coverage: 73.2% ----------', color: 'var(--accent-amber)' },
  { text: 'Name                           Stmts   Miss  Cover', color: 'var(--text-tertiary)' },
  { text: '-----------------------------------------------', color: 'var(--text-disabled)' },
  { text: 'src/core/router.py              245     12    95%', color: 'var(--text-tertiary)' },
  { text: 'src/bots/manager.py             189     38    80%', color: 'var(--text-tertiary)' },
  { text: 'src/handlers/message.py         312     98    69%', color: 'var(--text-tertiary)' },
  { text: 'src/services/ai_pool.py         156     51    67%', color: 'var(--text-tertiary)' },
  { text: '-----------------------------------------------', color: 'var(--text-disabled)' },
  { text: 'TOTAL                          1847    497    73%', color: 'var(--accent-cyan)' },
];

/* ====== 工具函数 ====== */

function moduleStatusStyle(s: TestModule['status']) {
  switch (s) {
    case 'pass': return { label: '全部通过', bg: 'rgba(34,197,94,0.15)', color: 'var(--accent-green)' };
    case 'partial': return { label: '部分通过', bg: 'rgba(245,158,11,0.15)', color: 'var(--accent-amber)' };
    case 'fail': return { label: '失败', bg: 'rgba(239,68,68,0.15)', color: 'var(--accent-red)' };
  }
}

/* ====== 主组件 ====== */

export function Testing() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 测试概览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <FlaskConical size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  TEST RUNNER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  测试诊断 // TEST RUNNER
                </p>
              </div>
            </div>

            {/* 统计指标 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {TEST_STATS.map((s) => (
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

            {/* 模块列表 */}
            <div className="flex-1">
              <span className="text-label mb-2 block" style={{ color: 'var(--text-tertiary)' }}>测试模块</span>
              <div className="space-y-1.5">
                {TEST_MODULES.map((mod) => {
                  const ms = moduleStatusStyle(mod.status);
                  return (
                    <div
                      key={mod.name}
                      className="flex items-center gap-3 py-2.5 px-4 rounded-lg"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <CheckCircle2 size={14} style={{ color: ms.color, flexShrink: 0 }} />
                      <span className="font-mono text-xs font-bold flex-1" style={{ color: 'var(--text-primary)' }}>
                        {mod.name}
                      </span>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {mod.passed}/{mod.total}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider flex-shrink-0"
                        style={{ background: ms.bg, color: ms.color }}
                      >
                        {ms.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 快速操作 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <Play size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  快速操作
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  QUICK ACTIONS
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-3">
              {QUICK_ACTIONS.map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.label}
                    className="w-full flex items-center gap-3 py-3.5 px-4 rounded-lg transition-all"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: `color-mix(in srgb, ${action.color} 15%, transparent)` }}
                    >
                      <Icon size={16} style={{ color: action.color }} />
                    </div>
                    <div className="flex-1 text-left">
                      <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                        {action.label}
                      </p>
                      <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {action.desc}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 最近测试结果 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card flex flex-col" style={{ background: 'rgba(5,5,12,0.95)' }}>
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
              <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                测试输出
              </span>
              <span className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                TEST OUTPUT
              </span>
            </div>

            {/* 终端内容 */}
            <div className="p-5 max-h-[360px] overflow-y-auto scroll-container">
              <div className="space-y-0.5">
                {TERMINAL_OUTPUT.map((line, i) => (
                  <div key={i} className="font-mono text-[12px] leading-relaxed whitespace-pre">
                    {line.text ? (
                      <span style={{ color: line.color || 'var(--text-tertiary)' }}>{line.text}</span>
                    ) : (
                      <br />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

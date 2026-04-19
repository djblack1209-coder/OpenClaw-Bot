/**
 * Testing — 测试诊断页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 测试系统暂未通过 API 接入，诚实标注待接入状态
 * 快速操作按钮提示用户在终端手动执行
 * 如有 /api/v1/status 返回测试相关信息则展示
 * 30 秒自动刷新（仅拉取 status）
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  FlaskConical,
  Play,
  RefreshCw,
  FileBarChart,
  Stethoscope,
  Terminal,
  Loader2,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { toast } from 'sonner';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 自动刷新间隔 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/* ====== 类型定义 ====== */

/** /api/v1/status 中可能包含的测试相关字段 */
interface StatusData {
  version?: string;
  tests_passed?: number;
  tests_failed?: number;
  tests_total?: number;
  test_coverage?: number;
  last_test_run?: string;
  [key: string]: unknown;
}

/* ====== 快速操作定义 ====== */
const QUICK_ACTIONS = [
  {
    label: '运行全部测试',
    desc: 'cd packages/clawbot && pytest tests/ -x',
    icon: Play,
    color: 'var(--accent-green)',
  },
  {
    label: '运行失败测试',
    desc: 'cd packages/clawbot && pytest --lf',
    icon: RefreshCw,
    color: 'var(--accent-amber)',
  },
  {
    label: '生成覆盖率报告',
    desc: 'cd packages/clawbot && pytest --cov',
    icon: FileBarChart,
    color: 'var(--accent-cyan)',
  },
  {
    label: '系统诊断',
    desc: '通过桌面端「诊断」功能执行',
    icon: Stethoscope,
    color: 'var(--accent-purple)',
  },
];

/* ====== 主组件 ====== */

export function Testing() {
  /* 状态 */
  const [status, setStatus] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  /* 尝试从 status API 获取测试相关数据 */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await clawbotFetchJson<StatusData>('/api/v1/status');
      if (!mountedRef.current) return;
      setStatus(data);
    } catch {
      /* status 不可用也正常 — 测试功能本身就标注为待接入 */
      if (!mountedRef.current) return;
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();
    const timer = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchData]);

  /* 判断 status 中是否有测试相关数据 */
  const hasTestInfo = status && (status.tests_total != null || status.test_coverage != null);

  /* 快速操作点击 — 提示用户在终端执行 */
  const handleQuickAction = (action: typeof QUICK_ACTIONS[number]) => {
    toast.info(`请在终端手动执行:\n${action.desc}`, {
      duration: 5000,
    });
  };

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
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  TEST RUNNER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  测试诊断 // TEST RUNNER
                </p>
              </div>
              {loading && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {/* 如果 status 中有测试数据，展示统计 */}
            {hasTestInfo ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                  {[
                    { label: '总用例', value: status?.tests_total != null ? String(status.tests_total) : '--', color: 'var(--accent-cyan)' },
                    { label: '通过', value: status?.tests_passed != null ? String(status.tests_passed) : '--', color: 'var(--accent-green)' },
                    { label: '失败', value: status?.tests_failed != null ? String(status.tests_failed) : '--', color: (status?.tests_failed ?? 0) > 0 ? 'var(--accent-red)' : 'var(--accent-green)' },
                    { label: '覆盖率', value: status?.test_coverage != null ? `${status.test_coverage}%` : '--', color: 'var(--accent-amber)' },
                  ].map((s) => (
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

                {status?.last_test_run && (
                  <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    上次运行: {status.last_test_run}
                  </p>
                )}
              </>
            ) : (
              /* 没有测试数据 — 诚实说明 */
              <div className="flex-1 flex flex-col items-center justify-center gap-4 py-6">
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center"
                  style={{ background: 'rgba(6,182,212,0.1)' }}
                >
                  <FlaskConical size={32} style={{ color: 'var(--accent-cyan)', opacity: 0.5 }} />
                </div>
                <div className="text-center max-w-md">
                  <p className="font-display text-sm font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                    测试系统暂未接入
                  </p>
                  <p className="font-mono text-xs leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                    当前无法通过界面运行测试。请在终端手动执行：
                  </p>
                  <div
                    className="mt-3 px-4 py-2.5 rounded-lg font-mono text-xs text-left"
                    style={{ background: 'rgba(5,5,12,0.8)', color: 'var(--accent-green)' }}
                  >
                    <span style={{ color: 'var(--text-disabled)' }}>$ </span>
                    cd packages/clawbot && pytest tests/ -x --tb=short
                  </div>
                </div>
              </div>
            )}
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
                    className="w-full flex items-center gap-3 py-3.5 px-4 rounded-lg transition-all hover:opacity-80"
                    style={{ background: 'var(--bg-secondary)' }}
                    onClick={() => handleQuickAction(action)}
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

            {/* 底部说明 */}
            <p
              className="font-mono text-[10px] mt-4 pt-3 border-t"
              style={{ color: 'var(--text-disabled)', borderColor: 'var(--glass-border)' }}
            >
              点击按钮将提示终端命令，暂不支持在界面内执行
            </p>
          </div>
        </motion.div>

        {/* ====== 测试输出 (col-12) — 待接入 ====== */}
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
              <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                测试输出
              </span>
              <span className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                TEST OUTPUT
              </span>
            </div>

            {/* 待接入提示 */}
            <div className="p-5">
              <div className="flex flex-col items-center justify-center py-8 gap-3">
                <Terminal size={24} style={{ color: 'var(--text-disabled)', opacity: 0.5 }} />
                <p className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  待接入 — 测试输出需通过后端 WebSocket 或 SSE 实时推送
                </p>
                <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  目前请在终端查看 pytest 输出
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

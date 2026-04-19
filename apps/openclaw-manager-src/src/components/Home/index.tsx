import { useEffect, useState, useCallback } from 'react';
import {
  TrendingUp,
  MessageSquare,
  Fish,
  Share2,
  Settings,
  ScanSearch,
  RefreshCw,
  Cookie,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useAppStore } from '@/stores/appStore';
import { useClawbotWS } from '@/hooks/useClawbotWS';
import { createLogger } from '@/lib/logger';
import type { PageType } from '../../App';
import { motion } from 'framer-motion';
import clsx from 'clsx';

/* 模块子组件 */
import { TradingEngineCard } from './TradingEngineCard';
import { TelemetryCard } from './TelemetryCard';
import { TerminalLogsCard } from './TerminalLogsCard';

const logger = createLogger('Home');

/* ====== 类型定义 ====== */

/** 7-Bot 投票数据 */
interface BotVote {
  name: string;
  signal: 'approve' | 'reject' | 'pending' | 'abstain';
  confidence: number;
}

/** 遥测数据 */
interface TelemetryData {
  llmCostDaily: number;
  activeBots: number;
  poolActive: number;
  poolTotal: number;
  memoryEntries: number;
}

/** 社媒状态 */
interface SocialData {
  running: boolean;
  mode: string; // 'autopilot' | 'manual'
  postsToday: number;
}

/** 闲鱼数据 */
interface XianyuData {
  unreadChats: number;
  cookieStatus: 'ok' | 'expired' | 'unknown';
  autoReplyActive: boolean;
}

/** 终端日志条目 */
export interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'OK' | 'WARN' | 'ERROR';
  module: string;
  message: string;
}

/* ====== 快捷操作配置 ====== */
const quickActions: { label: string; icon: React.ElementType; page: PageType; accent: string }[] = [
  { label: '投资分析', icon: TrendingUp, page: 'portfolio', accent: 'var(--accent-green)' },
  { label: '社交发帖', icon: Share2, page: 'social', accent: 'var(--accent-purple)' },
  { label: '闲鱼管理', icon: Fish, page: 'bots', accent: 'var(--accent-amber)' },
  { label: 'AI 对话', icon: MessageSquare, page: 'assistant', accent: 'var(--accent-cyan)' },
  { label: '市场扫描', icon: ScanSearch, page: 'portfolio', accent: 'var(--accent-red)' },
  { label: '系统设置', icon: Settings, page: 'settings', accent: 'var(--text-secondary)' },
];

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/**
 * 首页 Dashboard — Sonic Abyss Bento Grid 布局
 * 12 列 CSS Grid，玻璃卡片 + 终端美学
 */
export function HomeDashboard() {
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const isRunning = serviceStatus?.running ?? false;

  /* ====== 数据状态 ====== */
  const [bots, setBots] = useState<BotVote[]>([]);
  const [dailyPnl, setDailyPnl] = useState(0);
  const [dailyPnlPct, setDailyPnlPct] = useState(0);
  const [telemetry, setTelemetry] = useState<TelemetryData>({
    llmCostDaily: 0, activeBots: 0, poolActive: 0, poolTotal: 0, memoryEntries: 0,
  });
  const [social, setSocial] = useState<SocialData>({ running: false, mode: 'manual', postsToday: 0 });
  const [xianyu, setXianyu] = useState<XianyuData>({ unreadChats: 0, cookieStatus: 'unknown', autoReplyActive: false });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  /* WebSocket 实时日志推送 */
  useClawbotWS('notification', useCallback((event) => {
    const d = event.data as Record<string, unknown>;
    const entry: LogEntry = {
      id: String(d.id || Date.now()),
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      level: d.level === 'error' ? 'ERROR' : d.level === 'warning' ? 'WARN' : d.level === 'success' ? 'OK' : 'INFO',
      module: String(d.source || d.category || 'system'),
      message: String(d.title || d.message || ''),
    };
    setLogs((prev) => [entry, ...prev].slice(0, 50));
  }, []));

  /* WebSocket 实时状态更新 */
  useClawbotWS('status', useCallback((event) => {
    const d = event.data as Record<string, unknown>;
    if (d.uptime) {
      setTelemetry((prev) => ({ ...prev, activeBots: (d.bots as unknown[])?.length ?? prev.activeBots }));
    }
  }, []));

  /* ====== 数据拉取 ====== */
  const fetchAll = useCallback(async () => {
    try {
      const [statusRes, pnlRes, socialRes, notifsRes, poolRes] = await Promise.allSettled([
        api.clawbotStatus(),
        api.portfolioSummary(),
        api.clawbotSocialStatus(),
        api.notifications({ limit: 20 }),
        api.clawbotPoolStats(),
      ]);

      /* 解析系统状态 */
      if (statusRes.status === 'fulfilled' && statusRes.value) {
        const s = statusRes.value as Record<string, unknown>;
        const botsArr = (s.bots as Record<string, unknown>[]) ?? [];
        setBots(botsArr.map((b) => ({
          name: String(b.name || b.bot_name || ''),
          signal: String(b.signal || b.status || 'pending') as BotVote['signal'],
          confidence: Number(b.confidence ?? 0.5),
        })));
        setTelemetry((prev) => ({
          ...prev,
          llmCostDaily: Number(s.total_cost_usd ?? s.cost_today_usd ?? 0),
          activeBots: botsArr.length,
          memoryEntries: Number(s.memory_entries ?? 0),
        }));

        /* 闲鱼数据 */
        const xy = s.xianyu as Record<string, unknown> | undefined;
        if (xy) {
          setXianyu({
            unreadChats: Number(xy.unread_chats ?? xy.conversations_today ?? 0),
            cookieStatus: xy.cookie_ok ? 'ok' : xy.cookie_status === 'expired' ? 'expired' : 'unknown',
            autoReplyActive: Boolean(xy.auto_reply_active ?? xy.running),
          });
        }
      }

      /* 解析持仓盈亏 */
      if (pnlRes.status === 'fulfilled' && pnlRes.value) {
        const p = pnlRes.value as Record<string, unknown>;
        setDailyPnl(Number(p.daily_pnl ?? p.unrealized_pnl ?? 0));
        setDailyPnlPct(Number(p.daily_pnl_pct ?? p.pnl_pct ?? 0));
      }

      /* 解析社媒状态 */
      if (socialRes.status === 'fulfilled' && socialRes.value) {
        const sc = socialRes.value as Record<string, unknown>;
        setSocial({
          running: Boolean(sc.running ?? sc.autopilot_running),
          mode: sc.autopilot_running || sc.running ? 'autopilot' : 'manual',
          postsToday: Number(sc.posts_today ?? 0),
        });
      }

      /* 解析通知为日志 */
      if (notifsRes.status === 'fulfilled' && notifsRes.value) {
        const nd = notifsRes.value as Record<string, unknown>;
        const items = (nd.notifications as Record<string, unknown>[]) ?? [];
        setLogs(items.slice(0, 20).map((n, i) => ({
          id: String(n.id || i),
          timestamp: n.created_at
            ? new Date(String(n.created_at)).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            : '--:--:--',
          level: n.level === 'error' ? 'ERROR' : n.level === 'warning' ? 'WARN' : n.level === 'success' ? 'OK' : 'INFO',
          module: String(n.source || n.category || 'system'),
          message: String(n.title || n.body || ''),
        })));
      }

      /* 解析 API 池 */
      if (poolRes.status === 'fulfilled' && poolRes.value) {
        const pool = poolRes.value as Record<string, unknown>;
        setTelemetry((prev) => ({
          ...prev,
          poolActive: Number(pool.active_sources ?? pool.pool_active_sources ?? 0),
          poolTotal: Number(pool.total_sources ?? pool.pool_total_sources ?? 0),
        }));
      }
    } catch (err) {
      logger.error('首页数据拉取失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, 30_000);
    return () => clearInterval(timer);
  }, [fetchAll]);

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：Trading Engine (span-8, row-span-2) + Telemetry (span-4, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <TradingEngineCard
            bots={bots}
            dailyPnl={dailyPnl}
            dailyPnlPct={dailyPnlPct}
            isRunning={isRunning}
          />
        </motion.div>

        <motion.div className="col-span-12 lg:col-span-4 row-span-2" variants={cardVariants}>
          <TelemetryCard data={telemetry} isRunning={isRunning} />
        </motion.div>

        {/* ====== 第二行：Social (span-4) + Xianyu (span-4) + Quick Actions 预览 (span-4) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div
            className="abyss-card p-6 h-full cursor-pointer"
            onClick={() => setCurrentPage('social')}
          >
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              SOCIAL DRIVE
            </span>
            <h3 className="font-display text-xl font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
              X / XHS Drive
            </h3>
            <div className="flex items-center gap-2 mt-3">
              <span
                className={clsx(
                  'px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider',
                  social.mode === 'autopilot'
                    ? 'bg-[var(--accent-green)]/10 text-[var(--accent-green)]'
                    : 'bg-[var(--text-disabled)]/10 text-[var(--text-tertiary)]'
                )}
              >
                {social.mode === 'autopilot' ? '自动驾驶' : '手动'}
              </span>
            </div>
            <div className="flex items-baseline gap-2 mt-4">
              <span className="text-metric">{social.postsToday}</span>
              <span className="text-label">今日发布</span>
            </div>
            <p className="text-[11px] mt-3" style={{ color: 'var(--text-tertiary)' }}>
              小红书 · X (Twitter) · 自动热点追踪
            </p>
          </div>
        </motion.div>

        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div
            className="abyss-card p-6 h-full cursor-pointer"
            onClick={() => setCurrentPage('bots')}
          >
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              XIANYU AI
            </span>
            <h3 className="font-display text-xl font-bold mt-2" style={{ color: 'var(--text-primary)' }}>
              闲鱼 AI 客服
            </h3>
            <div className="flex items-center gap-3 mt-4">
              <div>
                <span className="text-label">未读对话</span>
                <div className="text-metric mt-1">{xianyu.unreadChats}</div>
              </div>
              <div className="ml-auto">
                <span className="text-label">Cookie</span>
                <div className="flex items-center gap-1.5 mt-1">
                  <Cookie size={14} style={{
                    color: xianyu.cookieStatus === 'ok' ? 'var(--accent-green)'
                         : xianyu.cookieStatus === 'expired' ? 'var(--accent-red)'
                         : 'var(--text-tertiary)',
                  }} />
                  <span className="font-mono text-xs" style={{
                    color: xianyu.cookieStatus === 'ok' ? 'var(--accent-green)'
                         : xianyu.cookieStatus === 'expired' ? 'var(--accent-red)'
                         : 'var(--text-tertiary)',
                  }}>
                    {xianyu.cookieStatus === 'ok' ? 'VALID' : xianyu.cookieStatus === 'expired' ? 'EXPIRED' : 'N/A'}
                  </span>
                </div>
              </div>
            </div>
            <p className="text-[11px] mt-3" style={{ color: 'var(--text-tertiary)' }}>
              {xianyu.autoReplyActive ? '自动回复运行中' : '自动回复未启动'} · CookieCloud 同步
            </p>
          </div>
        </motion.div>

        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          {/* 快捷操作 */}
          <div className="abyss-card p-5 h-full">
            <span className="text-label">QUICK ACTIONS</span>
            <div className="grid grid-cols-3 gap-2 mt-3">
              {quickActions.map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.label}
                    onClick={() => setCurrentPage(action.page)}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl transition-all duration-200 group"
                    style={{ background: 'rgba(255,255,255,0.02)' }}
                    onMouseEnter={(e) => {
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.06)');
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.02)');
                    }}
                  >
                    <Icon size={18} style={{ color: action.accent }} />
                    <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
                      {action.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 第三行：Terminal Logs (span-8) + 系统状态摘要 (span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <TerminalLogsCard logs={logs} />
        </motion.div>

        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-5 h-full flex flex-col">
            <span className="text-label">SYSTEM STATUS</span>
            <div className="flex-1 flex flex-col justify-center gap-3 mt-3">
              {/* 服务状态行 */}
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>ClawBot Core</span>
                <div className="flex items-center gap-1.5">
                  <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
                  <span className="font-mono text-[10px]" style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {isRunning ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Auto Trader</span>
                <span className="font-mono text-[10px]" style={{ color: bots.length > 0 ? 'var(--accent-green)' : 'var(--text-tertiary)' }}>
                  {bots.length > 0 ? 'ACTIVE' : 'STANDBY'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Social Engine</span>
                <span className="font-mono text-[10px]" style={{ color: social.running ? 'var(--accent-green)' : 'var(--text-tertiary)' }}>
                  {social.running ? 'RUNNING' : 'IDLE'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Xianyu Agent</span>
                <span className="font-mono text-[10px]" style={{ color: xianyu.autoReplyActive ? 'var(--accent-green)' : 'var(--text-tertiary)' }}>
                  {xianyu.autoReplyActive ? 'ACTIVE' : 'IDLE'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>LiteLLM Pool</span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-cyan)' }}>
                  {telemetry.poolActive}/{telemetry.poolTotal}
                </span>
              </div>
            </div>
            {/* 刷新按钮 */}
            <button
              onClick={() => { setLoading(true); fetchAll(); }}
              className="mt-3 w-full flex items-center justify-center gap-1.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-wider transition-colors"
              style={{ background: 'rgba(255,255,255,0.03)', color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; }}
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              REFRESH
            </button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

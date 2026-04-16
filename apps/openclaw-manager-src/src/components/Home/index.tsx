import { useEffect, useState, useCallback } from 'react';
import {
  Home,
  Sun,
  Moon,
  Cloud,
  TrendingUp,
  TrendingDown,
  Bot,
  Share2,
  Bell,
  Zap,
  MessageSquare,
  ShoppingBag,
  RefreshCw,
  Activity,
  DollarSign,
  Fish,
} from 'lucide-react';
import { GlassCard, StatusIndicator, AnimatedNumber } from '../shared';
import { clawbotFetch } from '../../lib/tauri';
import { useAppStore } from '@/stores/appStore';
import { motion } from 'framer-motion';
import clsx from 'clsx';

/* 获取时间段问候语 */
function getGreeting(): { text: string; icon: React.ElementType } {
  const hour = new Date().getHours();
  if (hour < 6) return { text: '夜深了', icon: Moon };
  if (hour < 12) return { text: '早上好', icon: Sun };
  if (hour < 18) return { text: '下午好', icon: Cloud };
  return { text: '晚上好', icon: Moon };
}

/* 系统概要数据 */
interface SystemSummary {
  serviceRunning: boolean;
  omegaReady: boolean;
  aiCostToday: number;
  aiBudget: number;
  tradingEnabled: boolean;
  socialEnabled: boolean;
  uptime: string;
}

/* 快捷操作配置 */
const quickActions = [
  { label: 'AI 对话', icon: MessageSquare, page: 'assistant' as const, color: 'text-[var(--oc-brand)]' },
  { label: '查看持仓', icon: TrendingUp, page: 'portfolio' as const, color: 'text-[var(--oc-success)]' },
  { label: '闲鱼客服', icon: Fish, page: 'bots' as const, color: 'text-orange-400' },
  { label: '发布内容', icon: Share2, page: 'bots' as const, color: 'text-pink-400' },
  { label: '插件商店', icon: ShoppingBag, page: 'store' as const, color: 'text-purple-400' },
  { label: '查看通知', icon: Bell, page: 'bots' as const, color: 'text-[var(--oc-warning)]' },
];

/**
 * 首页 Dashboard —— C 端主页面
 * 展示：问候语 + 系统状态概览 + 模块状态卡片 + 快捷操作
 */
export function HomeDashboard() {
  const greeting = getGreeting();
  const GreetingIcon = greeting.icon;
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const isRunning = serviceStatus?.running ?? false;

  const [summary, setSummary] = useState<SystemSummary>({
    serviceRunning: false,
    omegaReady: false,
    aiCostToday: 0,
    aiBudget: 50,
    tradingEnabled: false,
    socialEnabled: false,
    uptime: '--',
  });
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  /* 拉取系统概要 */
  const fetchSummary = useCallback(async () => {
    try {
      /* 并行请求多个端点 */
      const [statusResp, omegaResp, tradingResp, socialResp] = await Promise.allSettled([
        clawbotFetch('/api/v1/system/status'),
        clawbotFetch('/api/v1/omega/status'),
        clawbotFetch('/api/v1/controls/trading'),
        clawbotFetch('/api/v1/controls/social'),
      ]);

      const statusData = statusResp.status === 'fulfilled' && statusResp.value.ok
        ? await statusResp.value.json() : null;
      const omegaData = omegaResp.status === 'fulfilled' && omegaResp.value.ok
        ? await omegaResp.value.json() : null;
      const tradingData = tradingResp.status === 'fulfilled' && tradingResp.value.ok
        ? await tradingResp.value.json() : null;
      const socialData = socialResp.status === 'fulfilled' && socialResp.value.ok
        ? await socialResp.value.json() : null;

      setSummary({
        serviceRunning: isRunning,
        omegaReady: omegaData?.brain_ready ?? false,
        aiCostToday: omegaData?.cost_today_usd ?? 0,
        aiBudget: omegaData?.daily_budget_usd ?? 50,
        tradingEnabled: tradingData?.auto_trade_enabled ?? false,
        socialEnabled: socialData?.autopilot_enabled ?? false,
        uptime: statusData?.uptime ?? '--',
      });
      setLastRefresh(new Date());
    } catch {
      // 静默处理，使用默认值
    } finally {
      setLoading(false);
    }
  }, [isRunning]);

  useEffect(() => {
    fetchSummary();
    /* 每 30 秒刷新一次 */
    const interval = setInterval(fetchSummary, 30000);
    return () => clearInterval(interval);
  }, [fetchSummary]);

  /* 卡片入场动画延迟 */
  const cardVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: (i: number) => ({
      opacity: 1,
      y: 0,
      transition: { delay: i * 0.08, duration: 0.3, ease: 'easeOut' },
    }),
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* ========== 欢迎语 ========== */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[var(--oc-brand)]/10 flex items-center justify-center">
              <GreetingIcon size={24} className="text-[var(--oc-brand)]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">{greeting.text}</h1>
              <p className="text-sm text-gray-400">这里是你的智能生活控制台</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">
              上次更新 {lastRefresh.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <button
              onClick={() => { setLoading(true); fetchSummary(); }}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-dark-700 transition-colors"
              title="刷新"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* ========== 系统状态总览（一行 4 卡片） ========== */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* 服务状态 */}
          <motion.div custom={0} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-300">服务状态</span>
                <StatusIndicator status={isRunning ? 'running' : 'stopped'} size="sm" />
              </div>
              <div className="flex items-baseline gap-2">
                <Activity size={16} className={isRunning ? 'text-[var(--oc-success)]' : 'text-gray-500'} />
                <span className="text-lg font-semibold text-white">
                  {isRunning ? '在线' : '离线'}
                </span>
              </div>
              {isRunning && (
                <p className="text-xs text-gray-500 mt-1">运行时间 {summary.uptime}</p>
              )}
            </GlassCard>
          </motion.div>

          {/* AI 费用 */}
          <motion.div custom={1} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-300">今日 AI 费用</span>
                <DollarSign size={16} className="text-[var(--oc-brand)]" />
              </div>
              <div className="flex items-baseline gap-1">
                <AnimatedNumber value={summary.aiCostToday} prefix="$" decimals={2} className="text-lg font-semibold text-white" />
                <span className="text-xs text-gray-500">/ ${summary.aiBudget}</span>
              </div>
              {/* 预算进度条 */}
              <div className="mt-2 h-1.5 bg-dark-600 rounded-full overflow-hidden">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500',
                    summary.aiCostToday / summary.aiBudget > 0.8 ? 'bg-[var(--oc-danger)]' : 'bg-[var(--oc-brand)]'
                  )}
                  style={{ width: `${Math.min(100, (summary.aiCostToday / summary.aiBudget) * 100)}%` }}
                />
              </div>
            </GlassCard>
          </motion.div>

          {/* 自动交易 */}
          <motion.div custom={2} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('portfolio')}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-300">自动交易</span>
                <TrendingUp size={16} className="text-[var(--oc-success)]" />
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  summary.tradingEnabled ? 'bg-[var(--oc-success)]/20 text-[var(--oc-success)]' : 'bg-gray-500/20 text-gray-400'
                )}>
                  {summary.tradingEnabled ? '已开启' : '未开启'}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-2">点击查看持仓详情</p>
            </GlassCard>
          </motion.div>

          {/* 社媒自动驾驶 */}
          <motion.div custom={3} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('bots')}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-300">社媒运营</span>
                <Share2 size={16} className="text-pink-400" />
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  summary.socialEnabled ? 'bg-pink-500/20 text-pink-400' : 'bg-gray-500/20 text-gray-400'
                )}>
                  {summary.socialEnabled ? '自动驾驶中' : '手动模式'}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-2">点击管理内容发布</p>
            </GlassCard>
          </motion.div>
        </div>

        {/* ========== 快捷操作 ========== */}
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">快捷操作</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {quickActions.map((action, i) => {
              const Icon = action.icon;
              return (
                <motion.button
                  key={action.label}
                  custom={i + 4}
                  variants={cardVariants}
                  initial="hidden"
                  animate="visible"
                  onClick={() => setCurrentPage(action.page)}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl bg-dark-700 hover:bg-dark-600 border border-dark-500 transition-all group"
                >
                  <div className="w-10 h-10 rounded-xl bg-dark-600 group-hover:bg-dark-500 flex items-center justify-center transition-colors">
                    <Icon size={20} className={action.color} />
                  </div>
                  <span className="text-xs font-medium text-gray-300 group-hover:text-white transition-colors">
                    {action.label}
                  </span>
                </motion.button>
              );
            })}
          </div>
        </div>

        {/* ========== AI 智能建议（占位） ========== */}
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">AI 建议</h2>
          <GlassCard hoverable={false}>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Zap size={16} className="text-[var(--oc-brand)]" />
              </div>
              <div>
                <p className="text-sm text-white">
                  {isRunning
                    ? '所有系统运行正常。可以用 AI 助手开始今天的工作。'
                    : '服务尚未启动，请先到设置页面启动 ClawBot 服务。'}
                </p>
                <button
                  onClick={() => setCurrentPage(isRunning ? 'assistant' : 'settings')}
                  className="text-xs text-[var(--oc-brand)] hover:underline mt-1"
                >
                  {isRunning ? '打开 AI 助手 →' : '前往设置 →'}
                </button>
              </div>
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

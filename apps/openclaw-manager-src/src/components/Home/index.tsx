import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Sun,
  Moon,
  Cloud,
  TrendingUp,
  Share2,
  Bell,
  Zap,
  MessageSquare,
  ShoppingBag,
  RefreshCw,
  Activity,
  DollarSign,
  Fish,
  Calendar,
  AlertCircle,
  CheckCircle,
  Info,
} from 'lucide-react';
import { GlassCard, StatusIndicator, AnimatedNumber } from '../shared';
import { clawbotFetch, api } from '../../lib/tauri';
import { useAppStore } from '@/stores/appStore';
import { useClawbotWS } from '@/hooks/useClawbotWS';
import { createLogger } from '@/lib/logger';
import type { PageType } from '../../App';

const logger = createLogger('Home');
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
  dailyPnl: number;
  dailyPnlPct: number;
  totalMarketValue: number;
  positionsCount: number;
  conversationsToday: number;
  postsToday: number;
  notificationsCount: number;
}

/* 通知条目 */
interface NotificationItem {
  id: string;
  type: 'success' | 'warning' | 'error' | 'info';
  message: string;
  timestamp: Date;
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

/* 通知类型图标映射 */
const notificationIcons = {
  success: CheckCircle,
  warning: AlertCircle,
  error: AlertCircle,
  info: Info,
};

/* 通知类型颜色映射 */
const notificationColors = {
  success: 'text-[var(--oc-success)]',
  warning: 'text-[var(--oc-warning)]',
  error: 'text-[var(--oc-danger)]',
  info: 'text-[var(--oc-brand)]',
};

/* AI 建议条目 */
interface AISuggestion {
  id: string;
  icon: string;
  text: string;
  action: { label: string; page: PageType };
  priority: number; // lower = higher priority
}

/* 根据当前系统状态动态生成建议列表 */
function generateSuggestions(
  summary: SystemSummary,
  isRunning: boolean,
  notifications: NotificationItem[],
): AISuggestion[] {
  const suggestions: AISuggestion[] = [];

  // Priority 1: Critical system issues
  if (!isRunning) {
    suggestions.push({
      id: 'offline',
      icon: '⚠️',
      text: '服务尚未启动，请先到设置页面启动 ClawBot 服务。',
      action: { label: '前往设置', page: 'settings' },
      priority: 0,
    });
  }

  // Priority 2: Cost warnings
  if (summary.aiBudget > 0 && summary.aiCostToday / summary.aiBudget > 0.8) {
    suggestions.push({
      id: 'budget',
      icon: '💰',
      text: `AI 费用已达预算 ${((summary.aiCostToday / summary.aiBudget) * 100).toFixed(0)}%，建议优化使用频率或调整预算。`,
      action: { label: '调整预算', page: 'settings' },
      priority: 1,
    });
  }

  // Priority 3: Trading loss alert
  if (summary.tradingEnabled && summary.dailyPnl < -50) {
    suggestions.push({
      id: 'loss',
      icon: '📉',
      text: `今日交易亏损 $${Math.abs(summary.dailyPnl).toFixed(2)}，建议查看持仓并调整策略。`,
      action: { label: '查看持仓', page: 'portfolio' },
      priority: 2,
    });
  }

  // Priority 4: Unread notifications
  const urgentCount = notifications.filter(
    (n) => n.type === 'error' || n.type === 'warning',
  ).length;
  if (urgentCount > 0) {
    suggestions.push({
      id: 'urgent-notif',
      icon: '🔔',
      text: `有 ${urgentCount} 条紧急通知需要处理。`,
      action: { label: '查看通知', page: 'bots' },
      priority: 3,
    });
  }

  // Priority 5: Xianyu conversations
  if (summary.conversationsToday > 0 && isRunning) {
    suggestions.push({
      id: 'xianyu',
      icon: '🐟',
      text: `闲鱼今日有 ${summary.conversationsToday} 条对话，建议查看客服状态。`,
      action: { label: '管理客服', page: 'bots' },
      priority: 5,
    });
  }

  // Priority 6: Social media timing (8-10 PM is best for XHS)
  const hour = new Date().getHours();
  if (hour >= 19 && hour <= 21 && isRunning) {
    suggestions.push({
      id: 'social-time',
      icon: '📱',
      text: '现在是小红书最佳发文时间（晚 8-10 点），是否准备发布内容？',
      action: { label: '发布内容', page: 'bots' },
      priority: 6,
    });
  }

  // Priority 7: Trading profit
  if (summary.tradingEnabled && summary.dailyPnl > 100) {
    suggestions.push({
      id: 'profit',
      icon: '🎉',
      text: `今日盈利 $${summary.dailyPnl.toFixed(2)}，表现不错！可以考虑部分止盈。`,
      action: { label: '查看持仓', page: 'portfolio' },
      priority: 7,
    });
  }

  // Priority 8: General - all good
  if (suggestions.length === 0 && isRunning) {
    suggestions.push({
      id: 'all-good',
      icon: '✨',
      text: '所有系统运行正常。可以用 AI 助手开始今天的工作，或查看投资组合表现。',
      action: { label: '打开 AI 助手', page: 'assistant' },
      priority: 99,
    });
  }

  // Sort by priority and return top 3
  return suggestions.sort((a, b) => a.priority - b.priority).slice(0, 3);
}

/**
 * 首页 Dashboard —— C 端主页面
 * 展示：问候语 + 今日简报 + 模块状态卡片 + 通知预览 + 快捷操作 + AI 建议
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
    dailyPnl: 0,
    dailyPnlPct: 0,
    totalMarketValue: 0,
    positionsCount: 0,
    conversationsToday: 0,
    postsToday: 0,
    notificationsCount: 0,
  });
  
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  /* 动态计算 AI 建议 */
  const suggestions = useMemo(
    () => generateSuggestions(summary, isRunning, notifications),
    [summary, isRunning, notifications],
  );

  // WebSocket: receive real-time status updates to supplement polling
  useClawbotWS('status', useCallback((event) => {
    // Merge WS status data into summary
    const data = event.data as Record<string, unknown>;
    setSummary(prev => ({
      ...prev,
      serviceRunning: true, // If we're receiving WS events, service is running
      uptime: (data.uptime as string) ?? prev.uptime,
    }));
  }, []));

  // WebSocket: receive notification events instantly
  useClawbotWS('notification', useCallback((event) => {
    const data = event.data as Record<string, unknown>;
    setNotifications(prev => [{
      id: String(data.id || Date.now()),
      type: (data.level === 'error' ? 'error' : data.level === 'warning' ? 'warning' : 'info') as NotificationItem['type'],
      message: String(data.title || data.message || ''),
      timestamp: new Date(),
    }, ...prev].slice(0, 10));
  }, []));

  /* 拉取系统概要 */
  const fetchSummary = useCallback(async () => {
    try {
      /* 并行请求多个端点 */
      const [
        statusResp,
        omegaResp,
        tradingResp,
        socialResp,
        pnlResp,
        positionsResp,
        briefResult,
      ] = await Promise.allSettled([
        clawbotFetch('/api/v1/status'),
        clawbotFetch('/api/v1/omega/status'),
        clawbotFetch('/api/v1/controls/trading'),
        clawbotFetch('/api/v1/social/autopilot/status'),
        clawbotFetch('/api/v1/trading/pnl'),
        clawbotFetch('/api/v1/trading/positions'),
        api.dailyBrief(),
      ]);

      const statusData = statusResp.status === 'fulfilled' && statusResp.value.ok
        ? await statusResp.value.json() : null;
      const omegaData = omegaResp.status === 'fulfilled' && omegaResp.value.ok
        ? await omegaResp.value.json() : null;
      const tradingData = tradingResp.status === 'fulfilled' && tradingResp.value.ok
        ? await tradingResp.value.json() : null;
      const socialData = socialResp.status === 'fulfilled' && socialResp.value.ok
        ? await socialResp.value.json() : null;
      const pnlData = pnlResp.status === 'fulfilled' && pnlResp.value.ok
        ? await pnlResp.value.json() : null;
      const positionsData = positionsResp.status === 'fulfilled' && positionsResp.value.ok
        ? await positionsResp.value.json() : null;
      const briefData = briefResult.status === 'fulfilled' ? briefResult.value : null;

      setSummary({
        serviceRunning: isRunning,
        omegaReady: omegaData?.brain_ready ?? false,
        aiCostToday: omegaData?.cost_today_usd ?? 0,
        aiBudget: omegaData?.daily_budget_usd ?? 50,
        tradingEnabled: tradingData?.auto_trade_enabled ?? tradingData?.auto_trader_enabled ?? false,
        socialEnabled: socialData?.running ?? socialData?.autopilot_enabled ?? socialData?.autopilot_running ?? false,
        uptime: statusData?.uptime ?? '--',
        dailyPnl: pnlData?.daily_pnl ?? 0,
        dailyPnlPct: pnlData?.daily_pnl_pct ?? 0,
        totalMarketValue: positionsData?.total_market_value
          ?? (Array.isArray(positionsData?.positions)
            ? positionsData.positions.reduce((s: number, p: any) => s + (p.market_value ?? p.mkt_value ?? 0), 0)
            : 0),
        positionsCount: positionsData?.positions?.length ?? briefData?.metrics?.positions_count ?? 0,
        conversationsToday: briefData?.metrics?.xianyu_consultations ?? statusData?.conversations_today ?? 0,
        postsToday: socialData?.posts_today ?? briefData?.metrics?.social_posts ?? statusData?.posts_today ?? 0,
        notificationsCount: statusData?.notifications_count ?? 0,
      });
      
      /* 从后端获取通知数据 */
      try {
        const notifData = await api.notifications({ limit: 5 });
        if (notifData?.notifications) {
          const mapped = notifData.notifications.map((n: Record<string, unknown>) => ({
            id: n.id as string,
            type: (n.level === 'error' ? 'error' : n.level === 'warning' ? 'warning' : n.level === 'success' ? 'success' : 'info') as NotificationItem['type'],
            message: (n.title as string) || (n.body as string) || '通知',
            timestamp: new Date(n.created_at as string),
          }));
          setNotifications(mapped);
        }
      } catch {
        // 通知获取失败时使用空列表，不影响页面加载
      }
      
      setLastRefresh(new Date());
    } catch (err) {
      // Replace silent catch with user-visible error state when service is truly unreachable
      logger.error('Dashboard fetch failed:', err);
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

  /* 生成系统状态摘要文本 */
  const getSystemStatusText = () => {
    if (!isRunning) return '系统离线，请先启动服务';
    if (!summary.omegaReady) return '系统启动中，AI 大脑正在初始化...';
    
    const parts = [];
    if (summary.tradingEnabled) parts.push('自动交易运行中');
    if (summary.socialEnabled) parts.push('社媒自动驾驶中');
    if (parts.length === 0) return '所有系统就绪，等待指令';
    return parts.join(' · ');
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

        {/* ========== 今日简报卡片 ========== */}
        <motion.div custom={0} variants={cardVariants} initial="hidden" animate="visible">
          <GlassCard hoverable={false} className="bg-gradient-to-br from-[var(--oc-brand)]/10 to-transparent border border-[var(--oc-brand)]/20">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Calendar size={18} className="text-[var(--oc-brand)]" />
                  <h2 className="text-lg font-semibold text-white">
                    {new Date().toLocaleDateString('zh-CN', { 
                      month: 'long', 
                      day: 'numeric',
                      weekday: 'short' 
                    })}
                  </h2>
                </div>
                <p className="text-sm text-gray-400">{getSystemStatusText()}</p>
              </div>
              <StatusIndicator status={isRunning ? 'running' : 'stopped'} size="md" />
            </div>
            
            {/* 4 个迷你指标 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="flex flex-col">
                <span className="text-xs text-gray-500 mb-1">服务状态</span>
                <div className="flex items-baseline gap-1">
                  <Activity size={14} className={isRunning ? 'text-[var(--oc-success)]' : 'text-gray-500'} />
                  <span className="text-base font-semibold text-white">
                    {isRunning ? '在线' : '离线'}
                  </span>
                </div>
              </div>
              
              <div className="flex flex-col">
                <span className="text-xs text-gray-500 mb-1">AI 费用</span>
                <div className="flex items-baseline gap-1">
                  <DollarSign size={14} className="text-[var(--oc-brand)]" />
                  <AnimatedNumber 
                    value={summary.aiCostToday} 
                    prefix="$" 
                    decimals={2} 
                    className="text-base font-semibold text-white oc-tabular-nums" 
                  />
                  <span className="text-xs text-gray-500">/ ${summary.aiBudget}</span>
                </div>
              </div>
              
              <div className="flex flex-col">
                <span className="text-xs text-gray-500 mb-1">持仓</span>
                <div className="flex items-baseline gap-1">
                  <TrendingUp size={14} className="text-[var(--oc-success)]" />
                  <span className="text-base font-semibold text-white oc-tabular-nums">
                    {summary.positionsCount}
                  </span>
                  <span className="text-xs text-gray-500">只</span>
                </div>
              </div>
              
              <div className="flex flex-col">
                <span className="text-xs text-gray-500 mb-1">通知</span>
                <div className="flex items-baseline gap-1">
                  <Bell size={14} className="text-[var(--oc-warning)]" />
                  <span className="text-base font-semibold text-white oc-tabular-nums">
                    {summary.notificationsCount}
                  </span>
                  <span className="text-xs text-gray-500">条</span>
                </div>
              </div>
            </div>
          </GlassCard>
        </motion.div>

        {/* ========== 模块状态卡片（2x2 网格） ========== */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 💰 投资组合 */}
          <motion.div custom={1} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('portfolio')}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-[var(--oc-success)]/10 flex items-center justify-center">
                    <TrendingUp size={16} className="text-[var(--oc-success)]" />
                  </div>
                  <span className="text-sm font-medium text-gray-300">投资组合</span>
                </div>
              </div>
              
              <div className="space-y-2">
                <div>
                  <p className="text-xs text-gray-500 mb-1">总市值</p>
                  <AnimatedNumber
                    value={summary.totalMarketValue}
                    prefix="$"
                    decimals={2}
                    className="text-2xl font-bold text-white oc-tabular-nums"
                  />
                </div>
                
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">今日盈亏</span>
                  <AnimatedNumber
                    value={summary.dailyPnl}
                    prefix="$"
                    decimals={2}
                    colored
                    className="text-sm font-semibold oc-tabular-nums"
                  />
                  <AnimatedNumber 
                    value={summary.dailyPnlPct} 
                    suffix="%" 
                    decimals={2} 
                    colored 
                    className="text-sm font-semibold oc-tabular-nums" 
                  />
                </div>
              </div>
              
              <p className="text-xs text-gray-500 mt-3">点击查看持仓详情 →</p>
            </GlassCard>
          </motion.div>

          {/* 🤖 AI 客服（闲鱼） */}
          <motion.div custom={2} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('bots')}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center">
                    <Fish size={16} className="text-orange-400" />
                  </div>
                  <span className="text-sm font-medium text-gray-300">AI 客服（闲鱼）</span>
                </div>
                <StatusIndicator 
                  status={summary.serviceRunning ? 'running' : 'stopped'} 
                  size="sm" 
                />
              </div>
              
              <div className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white oc-tabular-nums">
                    {summary.conversationsToday}
                  </span>
                  <span className="text-sm text-gray-500">次对话</span>
                </div>
                <p className="text-xs text-gray-400">
                  {summary.serviceRunning ? '自动回复运行中' : '服务未启动'}
                </p>
              </div>
              
              <p className="text-xs text-gray-500 mt-3">点击管理客服机器人 →</p>
            </GlassCard>
          </motion.div>

          {/* 📱 社媒运营 */}
          <motion.div custom={3} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('bots')}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-pink-500/10 flex items-center justify-center">
                    <Share2 size={16} className="text-pink-400" />
                  </div>
                  <span className="text-sm font-medium text-gray-300">社媒运营</span>
                </div>
                <span className={clsx(
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  summary.socialEnabled 
                    ? 'bg-pink-500/20 text-pink-400' 
                    : 'bg-gray-500/20 text-gray-400'
                )}>
                  {summary.socialEnabled ? '自动驾驶' : '手动'}
                </span>
              </div>
              
              <div className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white oc-tabular-nums">
                    {summary.postsToday}
                  </span>
                  <span className="text-sm text-gray-500">条内容</span>
                </div>
                <p className="text-xs text-gray-400">
                  小红书 · X (Twitter)
                </p>
              </div>
              
              <p className="text-xs text-gray-500 mt-3">点击管理内容发布 →</p>
            </GlassCard>
          </motion.div>

          {/* ⚡ 自动交易 */}
          <motion.div custom={4} variants={cardVariants} initial="hidden" animate="visible">
            <GlassCard className="h-full" onClick={() => setCurrentPage('portfolio')}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/10 flex items-center justify-center">
                    <Zap size={16} className="text-[var(--oc-brand)]" />
                  </div>
                  <span className="text-sm font-medium text-gray-300">自动交易</span>
                </div>
                <span className={clsx(
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  summary.tradingEnabled 
                    ? 'bg-[var(--oc-success)]/20 text-[var(--oc-success)]' 
                    : 'bg-gray-500/20 text-gray-400'
                )}>
                  {summary.tradingEnabled ? '已开启' : '未开启'}
                </span>
              </div>
              
              <div className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white oc-tabular-nums">
                    {summary.positionsCount}
                  </span>
                  <span className="text-sm text-gray-500">个持仓</span>
                </div>
                <p className="text-xs text-gray-400">
                  {summary.tradingEnabled ? '策略：多因子量化' : '点击开启自动交易'}
                </p>
              </div>
              
              <p className="text-xs text-gray-500 mt-3">点击查看交易详情 →</p>
            </GlassCard>
          </motion.div>
        </div>

        {/* ========== 通知预览 ========== */}
        {notifications.length > 0 && (
          <motion.div custom={5} variants={cardVariants} initial="hidden" animate="visible">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">最新通知</h2>
              <button
                onClick={() => setCurrentPage('bots')}
                className="text-xs text-[var(--oc-brand)] hover:underline"
              >
                查看全部 →
              </button>
            </div>
            <GlassCard hoverable={false}>
              <div className="space-y-3">
                {notifications.slice(0, 5).map((notif) => {
                  const Icon = notificationIcons[notif.type];
                  const colorClass = notificationColors[notif.type];
                  
                  return (
                    <div key={notif.id} className="flex items-start gap-3 pb-3 border-b border-dark-600 last:border-0 last:pb-0">
                      <Icon size={16} className={clsx('flex-shrink-0 mt-0.5', colorClass)} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white">{notif.message}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {notif.timestamp.toLocaleTimeString('zh-CN', { 
                            hour: '2-digit', 
                            minute: '2-digit' 
                          })}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* ========== 快捷操作 ========== */}
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">快捷操作</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {quickActions.map((action, i) => {
              const Icon = action.icon;
              return (
                <motion.button
                  key={action.label}
                  custom={i + 6}
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

        {/* ========== AI 智能建议 ========== */}
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">AI 建议</h2>
          <div className="space-y-3">
            {suggestions.map((suggestion) => (
              <GlassCard key={suggestion.id} hoverable={false}>
                <div className="flex items-start gap-3">
                  <span className="text-xl flex-shrink-0">{suggestion.icon}</span>
                  <div className="flex-1">
                    <p className="text-sm text-white mb-2">{suggestion.text}</p>
                    <button
                      onClick={() => setCurrentPage(suggestion.action.page)}
                      className="text-xs text-[var(--oc-brand)] hover:underline"
                    >
                      {suggestion.action.label} →
                    </button>
                  </div>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import {
  Server,
  Clock,
  Terminal,
  RotateCcw,
  Cookie,
  Play,
  Square,
  Loader2,
  AlertCircle,
  Wifi,
  WifiOff,
  Fish,
  MessageSquare,
  Zap,
  Navigation,
  CalendarClock,
  Bell,
  ToggleLeft,
  ToggleRight,
  Timer,
  Send,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';
import { clawbotFetchJson } from '../../lib/tauri-core';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型 ====== */
interface ServiceItem {
  id: string;
  name: string;
  description: string;
  status: string;
  port?: number;
}

interface CookieStatus {
  enabled: boolean;
  last_sync_time: string;
  consecutive_failures: number;
  last_cookie_available: boolean;
}

/* 闲鱼数据 */
interface XianyuData {
  online: boolean;
  autoReplyEnabled: boolean;
  conversationCount: number;
}

/* 社媒自动驾驶数据 */
interface AutopilotData {
  running: boolean;
  mode: string;
  nextPublishTime: string | null;
  postsToday: number;
}

/* 定时任务数据 */
interface SchedulerTask {
  id: string;
  name: string;
  enabled: boolean;
  next_run?: string;
  interval?: string;
}

interface SchedulerData {
  running: boolean;
  tasks: SchedulerTask[];
}

/* ====== 辅助函数 ====== */

/** 服务状态颜色 */
const statusColor = (s: string) =>
  s === 'running' ? 'var(--accent-green)' : s === 'stopped' ? 'var(--text-tertiary)' : 'var(--accent-red)';

/** 服务状态文本 */
const statusText = (s: string) =>
  s === 'running' ? 'RUNNING' : s === 'stopped' ? 'STOPPED' : 'ERROR';

/** 查找服务名称（用于 toast 显示） */
const findServiceName = (services: ServiceItem[], id: string) =>
  services.find((s) => s.id === id)?.name ?? id;

/**
 * Bots 页面 — Sonic Abyss Bento Grid 布局
 * 12 列网格，玻璃卡片 + 终端美学
 * 使用真实后端 API 数据
 */
export function Bots() {
  const { t } = useLanguage();
  /* ====== 状态 ====== */
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  /* 闲鱼状态 */
  const [xianyuData, setXianyuData] = useState<XianyuData>({
    online: false,
    autoReplyEnabled: false,
    conversationCount: 0,
  });

  /* 社媒自动驾驶状态 */
  const [autopilotData, setAutopilotData] = useState<AutopilotData>({
    running: false,
    mode: 'manual',
    nextPublishTime: null,
    postsToday: 0,
  });
  const [autopilotLoading, setAutopilotLoading] = useState(false);

  /* 定时任务状态 */
  const [schedulerData, setSchedulerData] = useState<SchedulerData>({
    running: false,
    tasks: [],
  });
  const [schedulerTaskLoading, setSchedulerTaskLoading] = useState<Record<string, boolean>>({});

  /* ====== 数据拉取 ====== */
  const fetchData = useCallback(async () => {
    try {
      const [servicesRes, cookieRes, xianyuConvRes, autopilotRes, schedulerRes, statusRes] = await Promise.allSettled([
        api.services(),
        api.cookieCloudStatus(),
        api.xianyuConversations(20),
        api.clawbotAutopilotStatus(),
        clawbotFetchJson('/api/v1/controls/scheduler').catch(() => null),
        api.clawbotStatus(),
      ]);

      /* 服务列表 */
      if (servicesRes.status === 'fulfilled') {
        const data = servicesRes.value as any;
        setServices(data?.services ?? []);
      }

      /* Cookie 状态 */
      if (cookieRes.status === 'fulfilled') {
        setCookieStatus(cookieRes.value as any);
      }

      /* 闲鱼数据：从系统状态 + 对话列表组合 */
      let xianyuOnline = false;
      let xianyuAutoReply = false;
      if (statusRes.status === 'fulfilled' && statusRes.value) {
        const s = statusRes.value as Record<string, unknown>;
        const xy = s.xianyu as Record<string, unknown> | undefined;
        if (xy) {
          xianyuOnline = Boolean(xy.running ?? xy.online ?? false);
          xianyuAutoReply = Boolean(xy.auto_reply_active ?? xy.auto_reply_enabled ?? false);
        }
      }
      let convCount = 0;
      if (xianyuConvRes.status === 'fulfilled' && xianyuConvRes.value) {
        const convData = xianyuConvRes.value as any;
        convCount = Array.isArray(convData?.conversations)
          ? convData.conversations.length
          : Array.isArray(convData) ? convData.length : Number(convData?.total ?? 0);
      }
      setXianyuData({ online: xianyuOnline, autoReplyEnabled: xianyuAutoReply, conversationCount: convCount });

      /* 社媒自动驾驶 */
      if (autopilotRes.status === 'fulfilled' && autopilotRes.value) {
        const ap = autopilotRes.value as Record<string, unknown>;
        setAutopilotData({
          running: Boolean(ap.running ?? ap.active ?? false),
          mode: String(ap.mode ?? 'manual'),
          nextPublishTime: ap.next_publish_time ? String(ap.next_publish_time) : ap.next_run ? String(ap.next_run) : null,
          postsToday: Number(ap.posts_today ?? ap.published_today ?? 0),
        });
      }

      /* 定时任务 */
      if (schedulerRes.status === 'fulfilled' && schedulerRes.value) {
        const sc = schedulerRes.value as any;
        const taskList: SchedulerTask[] = Array.isArray(sc?.tasks)
          ? sc.tasks.map((t: any) => ({
              id: String(t.id ?? t.name ?? ''),
              name: String(t.name ?? t.id ?? 'unknown'),
              enabled: Boolean(t.enabled ?? t.active ?? true),
              next_run: t.next_run ? String(t.next_run) : undefined,
              interval: t.interval ? String(t.interval) : t.cron ? String(t.cron) : undefined,
            }))
          : [];
        setSchedulerData({
          running: Boolean(sc?.running ?? sc?.active ?? taskList.length > 0),
          tasks: taskList,
        });
      }

      setError(null);
    } catch (e: any) {
      setError(e?.message ?? t('bots.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30_000);
    return () => clearInterval(timer);
  }, [fetchData]);

  /* ====== 服务启停（带 Toast 反馈） ====== */
  const handleToggleService = async (serviceId: string, currentStatus: string) => {
    const serviceName = findServiceName(services, serviceId);
    const isStop = currentStatus === 'running';
    setActionLoading((prev) => ({ ...prev, [serviceId]: true }));
    try {
      if (isStop) {
        await api.serviceStop(serviceId);
      } else {
        await api.serviceStart(serviceId);
      }
      /* 等一小段时间让后端状态更新 */
      await new Promise((r) => setTimeout(r, 800));
      await fetchData();
      toast.success(isStop ? `${serviceName} ${t('bots.serviceStopped')}` : `${serviceName} ${t('bots.serviceStarted')}`);
    } catch (e: any) {
      await fetchData();
      toast.error(`${t('bots.operationFailed')}: ${e?.message ?? t('portfolio.error.unknown')}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [serviceId]: false }));
    }
  };

  /* ====== 社媒自动驾驶启停 ====== */
  const handleAutopilotToggle = async () => {
    setAutopilotLoading(true);
    try {
      if (autopilotData.running) {
        await api.clawbotAutopilotStop();
        toast.success(t('bots.autopilotStopped'));
      } else {
        await api.clawbotAutopilotStart();
        toast.success(t('bots.autopilotStarted'));
      }
      await new Promise((r) => setTimeout(r, 800));
      await fetchData();
    } catch (e: any) {
      toast.error(`${t('bots.operationFailed')}: ${e?.message ?? t('portfolio.error.unknown')}`);
    } finally {
      setAutopilotLoading(false);
    }
  };

  /* ====== 定时任务开关 ====== */
  const handleSchedulerTaskToggle = async (taskId: string, currentEnabled: boolean) => {
    setSchedulerTaskLoading((prev) => ({ ...prev, [taskId]: true }));
    try {
      await clawbotFetchJson(`/api/v1/controls/scheduler/${taskId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      toast.success(`${taskId} ${currentEnabled ? t('bots.taskDisabled') : t('bots.taskEnabled')}`);
      await new Promise((r) => setTimeout(r, 500));
      await fetchData();
    } catch (e: any) {
      toast.error(`${t('bots.operationFailed')}: ${e?.message ?? t('portfolio.error.unknown')}`);
    } finally {
      setSchedulerTaskLoading((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  /* ====== 统计数据 ====== */
  const runningCount = services.filter((s) => s.status === 'running').length;
  const stoppedCount = services.filter((s) => s.status === 'stopped').length;
  const errorCount = services.filter((s) => s.status !== 'running' && s.status !== 'stopped').length;

  const fleetStats = [
    { label: t('bots.total'), value: services.length, color: 'var(--accent-cyan)' },
    { label: t('bots.running'), value: runningCount, color: 'var(--accent-green)' },
    { label: t('bots.stopped'), value: stoppedCount, color: 'var(--text-tertiary)' },
    { label: t('bots.error'), value: errorCount, color: 'var(--accent-red)' },
  ];

  /* ====== Cookie 状态判断 ====== */
  const cookieValid = cookieStatus?.last_cookie_available && (cookieStatus?.consecutive_failures ?? 0) === 0;
  const cookieLabel = cookieValid ? 'VALID' : 'INVALID';
  const cookieColor = cookieValid ? 'var(--accent-green)' : 'var(--accent-red)';

  /* 通知服务状态（从 services 列表中查找） */
  const notifService = services.find((s) => s.id === 'notification' || s.id === 'apprise' || s.name?.includes('notif') || s.name?.includes('通知'));
  const notifRunning = notifService?.status === 'running';

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >

        {/* ====== Row 1 左: 服务舰队总览 (col-span-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>SERVICE FLEET</span>
              <div className="flex items-center gap-1.5">
                {loading ? (
                  <Loader2 size={12} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />
                ) : (
                  <>
                    <motion.span
                      className="inline-block w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--accent-green)' }}
                      animate={{ opacity: [1, 0.3, 1] }}
                      transition={{ duration: 1.5, repeat: Infinity }}
                    />
                    <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>LIVE</span>
                  </>
                )}
              </div>
            </div>
            <h2 className="font-display text-xl font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              服务舰队 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// SERVICE FLEET</span>
            </h2>

            {/* 统计行 */}
            <div className="flex gap-5 mb-5">
              {fleetStats.map((s) => (
                <div key={s.label} className="flex items-center gap-2">
                  <span className="font-mono text-2xl font-bold" style={{ color: s.color }}>{s.value}</span>
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.label}</span>
                </div>
              ))}
            </div>

            {/* 服务列表 */}
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 pr-1">
              {error && (
                <div className="flex items-center gap-2 px-4 py-3 rounded-2xl"
                  style={{ background: 'rgba(255,0,0,0.05)', border: '1px solid rgba(255,0,0,0.2)' }}>
                  <AlertCircle size={14} style={{ color: 'var(--accent-red)' }} />
                  <span className="text-xs" style={{ color: 'var(--accent-red)' }}>{error}</span>
                </div>
              )}
              {services.length === 0 && !loading && !error && (
                <div className="flex items-center justify-center py-8">
                  <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{t('bots.noServiceData')}</span>
                </div>
              )}
              {services.map((svc) => {
                const isLoading = actionLoading[svc.id] ?? false;
                const isRunning = svc.status === 'running';
                return (
                  <div
                    key={svc.id}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl transition-colors"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}
                  >
                    {/* 状态圆点 */}
                    <span className="relative flex-shrink-0">
                      {isRunning && (
                        <motion.span
                          className="absolute inset-[-3px] rounded-full"
                          style={{ background: statusColor(svc.status), opacity: 0.3 }}
                          animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                          transition={{ duration: 2, repeat: Infinity }}
                        />
                      )}
                      <span
                        className="block w-2 h-2 rounded-full"
                        style={{ background: statusColor(svc.status) }}
                      />
                    </span>

                    {/* 图标 + 名称 */}
                    <Server size={16} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    <span className="font-medium text-sm flex-shrink-0" style={{ color: 'var(--text-primary)' }}>
                      {svc.name}
                    </span>

                    {/* 描述 */}
                    {svc.description && (
                      <span className="font-mono text-[10px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                        {svc.description}
                      </span>
                    )}

                    <div className="flex-1" />

                    {/* 端口 */}
                    {svc.port && (
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <Terminal size={12} style={{ color: 'var(--text-tertiary)' }} />
                        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>:{svc.port}</span>
                      </div>
                    )}

                    {/* 启停按钮 */}
                    <motion.button
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl cursor-pointer text-[10px] font-mono font-bold"
                      style={{
                        background: isRunning ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
                        border: `1px solid ${isRunning ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
                        color: isRunning ? 'var(--accent-red)' : 'var(--accent-green)',
                        opacity: isLoading ? 0.5 : 1,
                        pointerEvents: isLoading ? 'none' : 'auto',
                      }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => handleToggleService(svc.id, svc.status)}
                    >
                      {isLoading ? (
                        <Loader2 size={10} className="animate-spin" />
                      ) : isRunning ? (
                        <Square size={10} />
                      ) : (
                        <Play size={10} />
                      )}
                      {isRunning ? t('bots.stop') : t('bots.start')}
                    </motion.button>

                    {/* 状态文本 */}
                    <span className="font-mono text-[10px] w-12 text-right flex-shrink-0" style={{ color: statusColor(svc.status) }}>
                      {statusText(svc.status)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 1 右: Cookie 状态 + 连接概览 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Cookie size={16} style={{ color: cookieColor }} />
              <span className="text-label" style={{ color: cookieColor }}>COOKIE STATUS</span>
            </div>

            {/* 大状态指示器 */}
            <div className="flex items-center gap-3 mb-6">
              <div className="relative">
                <div className="w-4 h-4 rounded-full animate-pulse" style={{ background: cookieColor }} />
                <div className="absolute inset-0 w-4 h-4 rounded-full animate-ping opacity-40" style={{ background: cookieColor }} />
              </div>
              <span className="font-display text-2xl font-bold tracking-wider" style={{ color: cookieColor }}>
                {cookieStatus ? cookieLabel : '—'}
              </span>
            </div>

            {/* 详细信息 */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{t('bots.lastSync')}</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                  {cookieStatus?.last_sync_time
                    ? new Date(cookieStatus.last_sync_time).toLocaleTimeString('zh-CN')
                    : '—'}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{t('bots.consecutiveFailures')}</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{
                  color: (cookieStatus?.consecutive_failures ?? 0) > 0 ? 'var(--accent-red)' : 'var(--accent-green)',
                }}>
                  {cookieStatus?.consecutive_failures ?? 0}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {cookieStatus?.enabled ? (
                    <Wifi size={13} style={{ color: 'var(--accent-green)' }} />
                  ) : (
                    <WifiOff size={13} style={{ color: 'var(--text-disabled)' }} />
                  )}
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{t('bots.syncFeature')}</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{
                  color: cookieStatus?.enabled ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {cookieStatus?.enabled ? t('bots.enabled') : t('bots.disabled')}
                </span>
              </div>
            </div>

            <p className="font-mono text-[10px] mt-6" style={{ color: 'var(--text-disabled)' }}>
              {t("bots.cookieDesc")}
            </p>
          </div>
        </motion.div>

        {/* ====== Row 2: 连接概览 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>CONNECTION</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t("bots.connectionStatus")}
            </h3>

            <div className="space-y-4">
              {services.filter((s) => s.status === 'running').slice(0, 6).map((svc) => (
                <div key={svc.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-green)' }} />
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{svc.name}</span>
                  </div>
                  {svc.port && (
                    <span className="font-mono text-xs" style={{ color: 'var(--accent-green)' }}>:{svc.port}</span>
                  )}
                </div>
              ))}
              {services.filter((s) => s.status === 'running').length === 0 && (
                <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{t('bots.noRunningServices')}</span>
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: 快速操作 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>QUICK ACTIONS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t("bots.quickActions")}
            </h3>

            <div className="flex-1 grid grid-cols-1 gap-3">
              {/* 刷新数据 */}
              <motion.button
                className="flex items-center gap-3 px-4 py-3 rounded-2xl cursor-pointer transition-colors text-left"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--glass-border)' }}
                whileHover={{ background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.15)' }}
                whileTap={{ scale: 0.98 }}
                onClick={() => { setLoading(true); fetchData(); }}
              >
                <span className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
                  <RotateCcw size={16} style={{ color: 'var(--accent-cyan)' }} />
                </span>
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{t('bots.refreshData')}</span>
              </motion.button>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: 服务详情 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>SUMMARY</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t("bots.summary")}
            </h3>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.totalServices')}</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-cyan)' }}>{services.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.onlineRate')}</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-green)' }}>
                  {services.length > 0 ? Math.round((runningCount / services.length) * 100) : 0}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                  <Cookie size={14} /> Cookie
                </span>
                <span
                  className="font-mono text-xs px-2.5 py-1 rounded-full font-bold"
                  style={{
                    color: cookieColor,
                    background: cookieValid ? 'rgba(0,255,170,0.1)' : 'rgba(255,0,0,0.1)',
                    border: `1px solid ${cookieValid ? 'rgba(0,255,170,0.25)' : 'rgba(255,0,0,0.25)'}`,
                  }}
                >
                  {cookieStatus ? cookieLabel : '—'}
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ══════════════════════════════════════════════════════════════
            以下为新增区域
           ══════════════════════════════════════════════════════════════ */}

        {/* ====== 闲鱼 AI 客服 (col-span-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-1">
              <Fish size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>XIANYU AI</span>
            </div>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              闲鱼 AI 客服 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// XIANYU</span>
            </h3>

            <div className="space-y-4">
              {/* 在线状态 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex-shrink-0">
                    {xianyuData.online && (
                      <motion.span
                        className="absolute inset-[-3px] rounded-full"
                        style={{ background: 'var(--accent-green)', opacity: 0.3 }}
                        animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      />
                    )}
                    <span className="block w-2.5 h-2.5 rounded-full"
                      style={{ background: xianyuData.online ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                  </span>
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.serviceStatus')}</span>
                </div>
                <span className="font-mono text-xs font-bold" style={{
                  color: xianyuData.online ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {xianyuData.online ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>

              {/* Cookie 状态 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cookie size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.cookieStatus')}</span>
                </div>
                <span
                  className="font-mono text-[10px] px-2 py-0.5 rounded-full font-bold"
                  style={{
                    color: cookieColor,
                    background: cookieValid ? 'rgba(0,255,170,0.1)' : 'rgba(255,0,0,0.1)',
                    border: `1px solid ${cookieValid ? 'rgba(0,255,170,0.25)' : 'rgba(255,0,0,0.25)'}`,
                  }}
                >
                  {cookieStatus ? cookieLabel : '—'}
                </span>
              </div>

              {/* 自动回复 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap size={13} style={{ color: xianyuData.autoReplyEnabled ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.autoReply')}</span>
                </div>
                <span className="font-mono text-xs font-bold" style={{
                  color: xianyuData.autoReplyEnabled ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {xianyuData.autoReplyEnabled ? t('bots.on') : t('bots.off')}
                </span>
              </div>

              {/* 最近对话数 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.recentChats')}</span>
                </div>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-amber)' }}>
                  {xianyuData.conversationCount}
                </span>
              </div>
            </div>

            <p className="font-mono text-[10px] mt-6" style={{ color: 'var(--text-disabled)' }}>
              {t("bots.xianyuDesc")}
            </p>
          </div>
        </motion.div>

        {/* ====== 社媒自动驾驶 (col-span-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-1">
              <Navigation size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>SOCIAL AUTOPILOT</span>
            </div>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              社媒自动驾驶 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// AUTOPILOT</span>
            </h3>

            <div className="space-y-4">
              {/* 运行状态 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex-shrink-0">
                    {autopilotData.running && (
                      <motion.span
                        className="absolute inset-[-3px] rounded-full"
                        style={{ background: 'var(--accent-green)', opacity: 0.3 }}
                        animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      />
                    )}
                    <span className="block w-2.5 h-2.5 rounded-full"
                      style={{ background: autopilotData.running ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                  </span>
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.pilotStatus')}</span>
                </div>
                <span className="font-mono text-xs font-bold" style={{
                  color: autopilotData.running ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {autopilotData.running ? 'ACTIVE' : 'IDLE'}
                </span>
              </div>

              {/* 下次发布时间 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Timer size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.nextPublish')}</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                  {autopilotData.nextPublishTime
                    ? new Date(autopilotData.nextPublishTime).toLocaleTimeString('zh-CN')
                    : '—'}
                </span>
              </div>

              {/* 今日发布 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Send size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.postsToday')}</span>
                </div>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-purple)' }}>
                  {autopilotData.postsToday}
                </span>
              </div>

              {/* 启停按钮 */}
              <motion.button
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl cursor-pointer text-xs font-mono font-bold mt-2"
                style={{
                  background: autopilotData.running ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
                  border: `1px solid ${autopilotData.running ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
                  color: autopilotData.running ? 'var(--accent-red)' : 'var(--accent-green)',
                  opacity: autopilotLoading ? 0.5 : 1,
                  pointerEvents: autopilotLoading ? 'none' : 'auto',
                }}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleAutopilotToggle}
              >
                {autopilotLoading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : autopilotData.running ? (
                  <Square size={14} />
                ) : (
                  <Play size={14} />
                )}
                {autopilotData.running ? t('bots.stopAutopilot') : t('bots.startAutopilot')}
              </motion.button>
            </div>
          </div>
        </motion.div>

        {/* ====== 定时任务 / 自动化 (col-span-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-1">
              <CalendarClock size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>SCHEDULER</span>
              <div className="flex-1" />
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full font-bold" style={{
                color: schedulerData.running ? 'var(--accent-green)' : 'var(--text-disabled)',
                background: schedulerData.running ? 'rgba(0,255,170,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${schedulerData.running ? 'rgba(0,255,170,0.25)' : 'var(--glass-border)'}`,
              }}>
                {schedulerData.running ? 'ACTIVE' : 'IDLE'}
              </span>
            </div>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              定时任务 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// SCHEDULER</span>
            </h3>

            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 pr-1">
              {schedulerData.tasks.length === 0 && (
                <div className="flex items-center justify-center py-6">
                  <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{t('bots.noSchedulerTasks')}</span>
                </div>
              )}
              {schedulerData.tasks.map((task) => {
                const isTaskLoading = schedulerTaskLoading[task.id] ?? false;
                return (
                  <div
                    key={task.id}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}
                  >
                    {/* 状态圆点 */}
                    <span className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: task.enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }} />

                    {/* 任务名 */}
                    <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                      {task.name}
                    </span>

                    {/* 间隔 / cron */}
                    {task.interval && (
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                        {task.interval}
                      </span>
                    )}

                    <div className="flex-1" />

                    {/* 下次执行 */}
                    {task.next_run && (
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                        {t('bots.nextRun')}: {new Date(task.next_run).toLocaleTimeString('zh-CN')}
                      </span>
                    )}

                    {/* 开关按钮 */}
                    <motion.button
                      className="flex items-center gap-1 px-2 py-1 rounded-lg cursor-pointer"
                      style={{
                        background: 'rgba(255,255,255,0.03)',
                        border: '1px solid var(--glass-border)',
                        color: task.enabled ? 'var(--accent-green)' : 'var(--text-disabled)',
                        opacity: isTaskLoading ? 0.5 : 1,
                        pointerEvents: isTaskLoading ? 'none' : 'auto',
                      }}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={() => handleSchedulerTaskToggle(task.id, task.enabled)}
                    >
                      {isTaskLoading ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : task.enabled ? (
                        <ToggleRight size={18} />
                      ) : (
                        <ToggleLeft size={18} />
                      )}
                    </motion.button>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 通知渠道 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-1">
              <Bell size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>NOTIFICATIONS</span>
            </div>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              通知渠道 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// APPRISE</span>
            </h3>

            <div className="space-y-4">
              {/* 服务状态 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex-shrink-0">
                    {notifRunning && (
                      <motion.span
                        className="absolute inset-[-3px] rounded-full"
                        style={{ background: 'var(--accent-green)', opacity: 0.3 }}
                        animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      />
                    )}
                    <span className="block w-2.5 h-2.5 rounded-full"
                      style={{ background: notifRunning ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                  </span>
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.notifService')}</span>
                </div>
                <span className="font-mono text-xs font-bold" style={{
                  color: notifRunning ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {notifRunning ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>

              {/* 服务名称 */}
              {notifService && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server size={13} style={{ color: 'var(--text-disabled)' }} />
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.serviceName')}</span>
                  </div>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                    {notifService.name}
                  </span>
                </div>
              )}

              {/* 端口 */}
              {notifService?.port && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal size={13} style={{ color: 'var(--text-disabled)' }} />
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('bots.port')}</span>
                  </div>
                  <span className="font-mono text-xs" style={{ color: 'var(--accent-cyan)' }}>
                    :{notifService.port}
                  </span>
                </div>
              )}

              {!notifService && (
                <div className="flex items-center justify-center py-4">
                  <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{t('bots.noNotifService')}</span>
                </div>
              )}
            </div>

            <p className="font-mono text-[10px] mt-6" style={{ color: 'var(--text-disabled)' }}>
              {t("bots.notifDesc")}
            </p>
          </div>
        </motion.div>

      </motion.div>
    </div>
  );
}

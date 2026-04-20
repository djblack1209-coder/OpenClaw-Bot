/**
 * Notifications — 通知中心
 * Sonic Abyss Bento Grid 布局，展示系统消息、告警与操作通知
 * 支持：分类筛选、标记已读、全部已读、WebSocket 实时推送、30 秒自动刷新
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import {
  Bell,
  BellOff,
  CheckCheck,
  Filter,
  RefreshCw,
  Loader2,
  AlertTriangle,
  Info,
  AlertCircle,
  CheckCircle2,
  Clock,
  Inbox,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useClawbotWS } from '@/hooks/useClawbotWS';
import { useLanguage } from '../../i18n';

/* ====== 常量 ====== */
const REFRESH_INTERVAL = 30_000;

/* ====== 类型定义 ====== */

/** 通知级别 */
type NotificationLevel = 'info' | 'warning' | 'error' | 'success';

/** 通知分类 */
type NotificationCategory = 'ALL' | 'SYSTEM' | 'TRADE' | 'RISK' | 'SOCIAL' | 'BOT';

/** API 返回的通知条目 */
interface NotificationItem {
  id: string;
  title: string;
  body: string;
  level: NotificationLevel;
  source: string;
  category: string;
  read: boolean;
  created_at: string;
}

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};
const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 分类配置 ====== */
const CATEGORIES: { id: NotificationCategory; labelKey: string }[] = [
  { id: 'ALL', labelKey: 'notifications.catAll' },
  { id: 'SYSTEM', labelKey: 'notifications.catSystem' },
  { id: 'TRADE', labelKey: 'notifications.catTrade' },
  { id: 'RISK', labelKey: 'notifications.catRisk' },
  { id: 'SOCIAL', labelKey: 'notifications.catSocial' },
  { id: 'BOT', labelKey: 'notifications.catBot' },
];

/* ====== 级别配色 ====== */
const LEVEL_CONFIG: Record<NotificationLevel, { color: string; bg: string; icon: typeof Info }> = {
  info: { color: 'var(--accent-cyan)', bg: 'rgba(0, 245, 255, 0.08)', icon: Info },
  warning: { color: 'var(--accent-amber)', bg: 'rgba(251, 191, 36, 0.08)', icon: AlertTriangle },
  error: { color: 'var(--accent-red)', bg: 'rgba(248, 113, 113, 0.08)', icon: AlertCircle },
  success: { color: 'var(--accent-green)', bg: 'rgba(52, 211, 153, 0.08)', icon: CheckCircle2 },
};

/* ====== 辅助函数 ====== */

/** 分类映射 */
function mapCategory(cat: string): NotificationCategory {
  const upper = (cat || '').toUpperCase();
  if (upper.includes('SYSTEM') || upper.includes('SYS')) return 'SYSTEM';
  if (upper.includes('TRADE') || upper.includes('TRADING')) return 'TRADE';
  if (upper.includes('RISK')) return 'RISK';
  if (upper.includes('SOCIAL')) return 'SOCIAL';
  if (upper.includes('BOT')) return 'BOT';
  return 'SYSTEM';
}

/** 时间格式化 */
function timeAgo(isoStr: string): string {
  try {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins} 分钟前`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} 小时前`;
    const days = Math.floor(hrs / 24);
    return `${days} 天前`;
  } catch {
    return '—';
  }
}

/** 格式化完整时间 */
function formatTimestamp(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch {
    return '—';
  }
}

/* ====== 加载/错误状态组件 ====== */

function LoadingState({ message = '数据加载中...' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8">
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{message}</span>
    </div>
  );
}

function ErrorState({ message = '数据加载失败', onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <AlertTriangle size={20} style={{ color: 'var(--accent-red)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--accent-red)' }}>{message}</span>
      <button
        onClick={onRetry}
        className="px-4 py-1.5 rounded-lg font-mono text-[11px] transition-all duration-200"
        style={{
          background: 'rgba(255, 0, 60, 0.1)',
          color: 'var(--accent-red)',
          border: '1px solid rgba(255, 0, 60, 0.25)',
        }}
      >
        <RefreshCw size={12} className="inline mr-1.5" />
        重试
      </button>
    </div>
  );
}

/* ====== 主组件 ====== */

export function Notifications() {
  const { t } = useLanguage();
  /* ---- 状态 ---- */
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<NotificationCategory>('ALL');
  const [markingReadId, setMarkingReadId] = useState<string | null>(null);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- 数据拉取 ---- */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const resp = await api.notifications({ limit: 50 });
      /* 后端可能返回 { notifications: [...] } 或直接返回数组 */
      const list = Array.isArray(resp) ? resp : (resp as Record<string, unknown>)?.notifications;
      if (Array.isArray(list)) {
        setItems(list as NotificationItem[]);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'unknown error';
      if (!silent) setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  /* ---- 挂载 + 30 秒自动刷新 ---- */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ---- WebSocket 实时推送 ---- */
  useClawbotWS('notification', (event) => {
    /* 收到新通知时，插入到列表头部（不弹 Toast，避免干扰用户操作） */
    const newItem = event.data as unknown as NotificationItem;
    if (newItem && newItem.id) {
      setItems((prev) => {
        /* 去重 */
        if (prev.some((i) => i.id === newItem.id)) return prev;
        return [newItem, ...prev];
      });
    }
  });

  /* ---- 标记单条已读 ---- */
  const handleMarkRead = async (id: string) => {
    setMarkingReadId(id);
    try {
      await api.markNotificationRead(id);
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, read: true } : i)));
      toast.success(t('notifications.markedRead'));
    } catch {
      toast.error(t('notifications.markReadFailed'));
    } finally {
      setMarkingReadId(null);
    }
  };

  /* ---- 全部标记已读 ---- */
  const handleMarkAllRead = async () => {
    setMarkingAllRead(true);
    try {
      await api.markAllNotificationsRead();
      setItems((prev) => prev.map((i) => ({ ...i, read: true })));
      toast.success(t('notifications.allMarkedRead'));
    } catch {
      toast.error(t('notifications.markAllReadFailed'));
    } finally {
      setMarkingAllRead(false);
    }
  };

  /* ---- 衍生数据 ---- */
  const filteredItems = useMemo(() => {
    if (activeCategory === 'ALL') return items;
    return items.filter((i) => mapCategory(i.category) === activeCategory);
  }, [items, activeCategory]);

  const unreadCount = useMemo(() => items.filter((i) => !i.read).length, [items]);

  /** 各级别的数量统计 */
  const levelStats = useMemo(() => {
    const counts: Record<NotificationLevel, number> = { info: 0, warning: 0, error: 0, success: 0 };
    for (const item of items) {
      const level = (item.level || 'info') as NotificationLevel;
      if (counts[level] !== undefined) counts[level]++;
    }
    return counts;
  }, [items]);

  /* ---- 加载/错误状态 ---- */
  if (loading && items.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <LoadingState message={t('notifications.loadingNotifications')} />
        </div>
      </div>
    );
  }

  if (error && items.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <ErrorState message={`${t('notifications.loadFailed')}: ${error}`} onRetry={fetchData} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ═══════════════════════════════════
         * 顶部：通知列表 (span-8) + 统计面板 (span-4)
         * ═══════════════════════════════════ */}

        {/* 通知列表 — 主卡片 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题区 */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-3">
                <Bell size={16} style={{ color: 'var(--accent-cyan)' }} />
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  NOTIFICATION CENTER
                </span>
                {unreadCount > 0 && (
                  <span
                    className="px-2 py-0.5 rounded-full font-mono text-[10px] font-bold"
                    style={{
                      background: 'rgba(0, 245, 255, 0.15)',
                      color: 'var(--accent-cyan)',
                    }}
                  >
                    {unreadCount} {t('notifications.unread')}
                  </span>
                )}
              </div>
              {/* 全部已读按钮 */}
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  disabled={markingAllRead}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-mono text-[11px] transition-all duration-200"
                  style={{
                    background: markingAllRead ? 'rgba(255,255,255,0.03)' : 'rgba(0, 245, 255, 0.08)',
                    color: markingAllRead ? 'var(--text-disabled)' : 'var(--accent-cyan)',
                    border: '1px solid rgba(0, 245, 255, 0.2)',
                    cursor: markingAllRead ? 'not-allowed' : 'pointer',
                  }}
                >
                  {markingAllRead ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <CheckCheck size={12} />
                  )}
                   {t('notifications.markAllRead')}
                </button>
              )}
            </div>
            <p
              className="font-mono text-[11px] mb-4"
              style={{ color: 'var(--text-tertiary)' }}
            >
              {items.length} {t('notifications.notificationsCount')} // {unreadCount} {t('notifications.unread')} // {t('notifications.autoRefresh30s')}
            </p>

            {/* 分类筛选条 */}
            <div className="flex flex-wrap gap-2 mb-4">
              {CATEGORIES.map((cat) => {
                const isActive = activeCategory === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setActiveCategory(cat.id)}
                    className="px-3 py-1 rounded-full font-mono text-[10px] uppercase tracking-wider transition-all duration-200 border"
                    style={{
                      borderColor: isActive ? 'var(--accent-cyan)' : 'var(--glass-border)',
                      background: isActive ? 'rgba(0, 245, 255, 0.1)' : 'transparent',
                      color: isActive ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                    }}
                  >
                    <Filter size={10} className="inline mr-1" />
                    {t(cat.labelKey)}
                  </button>
                );
              })}
            </div>

            {/* 通知列表 — 可滚动 */}
            <div className="flex-1 overflow-y-auto space-y-1 min-h-0 max-h-[520px] scroll-container">
              {filteredItems.map((item, idx) => {
                const levelConf = LEVEL_CONFIG[item.level] || LEVEL_CONFIG.info;
                const LevelIcon = levelConf.icon;
                const isUnread = !item.read;

                return (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.03, duration: 0.25 }}
                    className="flex items-start gap-3 p-3 rounded-lg transition-colors duration-150"
                    style={{
                      background: isUnread ? 'rgba(0, 245, 255, 0.03)' : 'rgba(255,255,255,0.015)',
                      borderLeft: isUnread ? `2px solid ${levelConf.color}` : '2px solid transparent',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = isUnread
                        ? 'rgba(0, 245, 255, 0.03)'
                        : 'rgba(255,255,255,0.015)';
                    }}
                  >
                    {/* 级别图标 */}
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                      style={{ background: levelConf.bg }}
                    >
                      <LevelIcon size={14} style={{ color: levelConf.color }} />
                    </div>

                    {/* 内容 */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4
                          className="font-display text-sm leading-snug truncate"
                          style={{
                            color: 'var(--text-primary)',
                            fontWeight: isUnread ? 600 : 400,
                          }}
                        >
                          {item.title}
                        </h4>
                        {isUnread && (
                          <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ background: 'var(--accent-cyan)' }}
                          />
                        )}
                      </div>
                      <p
                        className="font-mono text-[11px] mt-1 leading-relaxed line-clamp-2"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {item.body}
                      </p>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span
                          className="font-mono text-[10px]"
                          style={{ color: 'var(--text-disabled)' }}
                        >
                          <Clock size={10} className="inline mr-1" />
                          {timeAgo(item.created_at)}
                        </span>
                        <span
                          className="font-mono text-[10px] uppercase"
                          style={{ color: 'var(--text-disabled)' }}
                        >
                          {item.source}
                        </span>
                      </div>
                    </div>

                    {/* 操作区 */}
                    <div className="flex flex-col items-end gap-1.5 shrink-0">
                      <span
                        className="font-mono text-[10px] whitespace-nowrap"
                        style={{ color: 'var(--text-disabled)' }}
                      >
                        {formatTimestamp(item.created_at)}
                      </span>
                      {isUnread && (
                        <button
                          onClick={() => handleMarkRead(item.id)}
                          disabled={markingReadId === item.id}
                          className="px-2 py-0.5 rounded font-mono text-[10px] transition-all duration-200"
                          style={{
                            background: 'rgba(255,255,255,0.04)',
                            color: 'var(--text-tertiary)',
                            border: '1px solid var(--glass-border)',
                            cursor: markingReadId === item.id ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {markingReadId === item.id ? (
                            <Loader2 size={10} className="inline animate-spin" />
                          ) : (
                            t('notifications.read')
                          )}
                        </button>
                      )}
                    </div>
                  </motion.div>
                );
              })}

              {/* 空状态 */}
              {filteredItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <Inbox size={32} style={{ color: 'var(--text-disabled)', opacity: 0.5 }} />
                  <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                    {activeCategory === 'ALL' ? t('notifications.noNotifications') : t('notifications.noCategoryNotifications')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* 统计面板 — 右侧 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="space-y-4">
            {/* 未读概览卡片 */}
            <div className="abyss-card p-6">
              <div className="flex items-center gap-3 mb-4">
                <BellOff size={16} style={{ color: 'var(--accent-amber)' }} />
                <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                  UNREAD OVERVIEW
                </span>
              </div>
              <div className="text-center mb-4">
                <span
                  className="font-display text-4xl font-bold"
                  style={{
                    color: unreadCount > 0 ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
                  }}
                >
                  {unreadCount}
                </span>
                <p className="font-mono text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  {t('notifications.unreadNotifications')}
                </p>
              </div>
              {/* 按等级分布 */}
              <div className="space-y-2">
                {(Object.keys(LEVEL_CONFIG) as NotificationLevel[]).map((level) => {
                  const conf = LEVEL_CONFIG[level];
                  const count = levelStats[level];
                  const labels: Record<NotificationLevel, string> = {
                    error: t('notifications.levelError'),
                    warning: t('notifications.levelWarning'),
                    info: t('notifications.levelInfo'),
                    success: t('notifications.levelSuccess'),
                  };
                  return (
                    <div
                      key={level}
                      className="flex items-center justify-between px-3 py-2 rounded-lg"
                      style={{ background: conf.bg }}
                    >
                      <div className="flex items-center gap-2">
                        <conf.icon size={12} style={{ color: conf.color }} />
                        <span className="font-mono text-[11px]" style={{ color: conf.color }}>
                          {labels[level]}
                        </span>
                      </div>
                      <span className="font-mono text-[13px] font-bold" style={{ color: conf.color }}>
                        {count}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 最近来源 */}
            <div className="abyss-card p-6">
              <div className="flex items-center gap-3 mb-4">
                <Filter size={16} style={{ color: 'var(--accent-purple)' }} />
                <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                  SOURCES
                </span>
              </div>
              <div className="space-y-2">
                {(() => {
                  /* 统计来源分布 */
                  const sourceCounts: Record<string, number> = {};
                  for (const item of items) {
                    const src = item.source || t('notifications.unknown');
                    sourceCounts[src] = (sourceCounts[src] || 0) + 1;
                  }
                  const sorted = Object.entries(sourceCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 6);
                  const max = Math.max(...sorted.map(([, c]) => c), 1);

                  if (sorted.length === 0) {
                    return (
                      <span className="font-mono text-[11px]" style={{ color: 'var(--text-disabled)' }}>
                        {t('notifications.noData')}
                      </span>
                    );
                  }

                  return sorted.map(([name, count]) => (
                    <div key={name} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                          {name}
                        </span>
                        <span className="font-mono text-[11px]" style={{ color: 'var(--text-disabled)' }}>
                          {count}
                        </span>
                      </div>
                      <div
                        className="h-1 rounded-full"
                        style={{ background: 'rgba(255,255,255,0.05)' }}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${(count / max) * 100}%`,
                            background: 'var(--accent-purple)',
                            opacity: 0.7,
                          }}
                        />
                      </div>
                    </div>
                  ));
                })()}
              </div>
            </div>

            {/* 手动刷新 */}
            <div className="abyss-card p-4">
              <button
                onClick={() => fetchData()}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-mono text-[11px] transition-all duration-200"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--glass-border)',
                }}
              >
                <RefreshCw size={12} />
                {t('notifications.manualRefresh')}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

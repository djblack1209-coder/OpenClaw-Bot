import { useState, useEffect, useCallback } from 'react';
import { toast } from '@/lib/notify';
import { motion } from 'framer-motion';
import {
  Share2,
  Flame,
  CalendarDays,
  Sparkles,
  Globe,
  FileText,
  Users,
  Loader2,
  AlertCircle,
  Play,
  Square,
  Clock,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 平台徽标颜色 ====== */
const platformColorMap: Record<string, { labelKey: string; color: string; bg: string }> = {
  xhs: { labelKey: 'social.platform.xhs', color: '#ff2442', bg: 'rgba(255,36,66,0.12)' },
  xiaohongshu: { labelKey: 'social.platform.xhs', color: '#ff2442', bg: 'rgba(255,36,66,0.12)' },
  x: { labelKey: 'social.platform.x', color: 'var(--text-primary)', bg: 'rgba(255,255,255,0.08)' },
  twitter: { labelKey: 'social.platform.x', color: 'var(--text-primary)', bg: 'rgba(255,255,255,0.08)' },
  weibo: { labelKey: 'social.platform.weibo', color: '#ff8200', bg: 'rgba(255,130,0,0.12)' },
};
const defaultPlatformCfg = { labelKey: 'social.platform.default', color: 'var(--text-secondary)', bg: 'rgba(255,255,255,0.06)' };
const getPlatformCfg = (p: string) => platformColorMap[(p ?? '').toLowerCase()] ?? { ...defaultPlatformCfg, labelKey: p || 'social.platform.unknown' };

/* ====== 类型 ====== */
interface PlatformStatus {
  platform: string;
  connected: boolean;
  posts_today: number;
  total_posts: number;
}
interface SocialStatusData {
  autopilot_running: boolean;
  platforms: PlatformStatus[];
  next_scheduled_action?: string;
  next_scheduled_time?: string;
}
interface DraftItem {
  id: string;
  title: string;
  platform?: string;
  status?: string;
  created_at?: string;
}
interface CalendarItem {
  id: string;
  title: string;
  platform: string;
  scheduled_time: string;
}
interface TopicItem {
  id?: string;
  name: string;
  heat: number;
  platform?: string;
}

/* ====== 主组件 ====== */

/**
 * 社交媒体页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示社媒运营中心全部关键指标
 * 使用真实后端 API 数据
 */
export function Social() {
  const { t } = useLanguage();
  const [socialStatus, setSocialStatus] = useState<SocialStatusData | null>(null);
  const [drafts, setDrafts] = useState<DraftItem[]>([]);
  const [calendar, setCalendar] = useState<CalendarItem[]>([]);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autopilotLoading, setAutopilotLoading] = useState(false);

  /* ====== 数据拉取 ====== */
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, draftsRes, calendarRes, topicsRes] = await Promise.allSettled([
        api.clawbotSocialStatus(),
        api.clawbotSocialDrafts(),
        api.clawbotSocialCalendar(),
        api.clawbotSocialTopics({ category: 'all' } as any),
      ]);

      if (statusRes.status === 'fulfilled') setSocialStatus(statusRes.value as any);
      if (draftsRes.status === 'fulfilled') {
        const d = draftsRes.value as any;
        setDrafts(Array.isArray(d) ? d : d?.drafts ?? []);
      }
      if (calendarRes.status === 'fulfilled') {
        const c = calendarRes.value as any;
        setCalendar(Array.isArray(c) ? c : c?.items ?? c?.calendar ?? []);
      }
      if (topicsRes.status === 'fulfilled') {
        const t = topicsRes.value as any;
        setTopics(Array.isArray(t) ? t : t?.topics ?? []);
      }
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? t('social.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30_000);
    return () => clearInterval(timer);
  }, [fetchData]);

  /* ====== 自动驾驶切换 ====== */
  const handleAutopilotToggle = async () => {
    setAutopilotLoading(true);
    try {
      if (socialStatus?.autopilot_running) {
        await api.clawbotAutopilotStop();
      } else {
        await api.clawbotAutopilotStart();
      }
      await new Promise((r) => setTimeout(r, 800));
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
      await fetchData();
    } finally {
      setAutopilotLoading(false);
    }
  };

  /* ====== 派生数据 ====== */
  const platforms = socialStatus?.platforms ?? [];
  const totalPostsToday = platforms.reduce((s, p) => s + (p.posts_today ?? 0), 0);
  const connectedCount = platforms.filter((p) => p.connected).length;
  const autopilotRunning = socialStatus?.autopilot_running ?? false;

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== Row 1: 社媒总控 (span-8, row-span-2) + 平台状态 (span-4) ====== */}

        {/* 社媒总控 */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题区域 */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.15)' }}>
                <Share2 size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('social.title')}
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('social.subtitle')}
                </p>
              </div>
              {loading && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />}
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl mb-4"
                style={{ background: 'rgba(255,0,0,0.05)', border: '1px solid rgba(255,0,0,0.2)' }}>
                <AlertCircle size={14} style={{ color: 'var(--accent-red)' }} />
                <span className="text-xs" style={{ color: 'var(--accent-red)' }}>{error}</span>
              </div>
            )}

            {/* 关键指标 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <StatBlock icon={FileText} label={t('social.postsToday')} value={String(totalPostsToday)} accent="var(--accent-cyan)" />
              <StatBlock icon={Users} label={t('social.connectedPlatforms')} value={String(connectedCount)} accent="var(--accent-purple)" />
              <StatBlock icon={Sparkles} label={t('social.draftsCount')} value={String(drafts.length)} accent="var(--accent-amber)" />
              <StatBlock icon={CalendarDays} label={t('social.pendingPublish')} value={String(calendar.length)} accent="var(--accent-green)" />
            </div>

            {/* 自动驾驶控制 */}
            <div className="flex items-center gap-3 p-3 rounded-xl mb-5"
              style={{ background: 'var(--bg-base)' }}>
              <div className="relative flex-shrink-0">
                <div className="w-3 h-3 rounded-full"
                  style={{ background: autopilotRunning ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                {autopilotRunning && (
                  <div className="absolute inset-0 w-3 h-3 rounded-full animate-ping opacity-30"
                    style={{ background: 'var(--accent-green)' }} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <span className="font-mono text-xs font-medium block" style={{ color: 'var(--text-primary)' }}>
                  {t('social.autopilot')}
                </span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  {autopilotRunning ? t('social.autopilotRunning') : t('social.autopilotStopped')}
                </span>
              </div>
              <motion.button
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl cursor-pointer text-[10px] font-mono font-bold"
                style={{
                  background: autopilotRunning ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
                  border: `1px solid ${autopilotRunning ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
                  color: autopilotRunning ? 'var(--accent-red)' : 'var(--accent-green)',
                  opacity: autopilotLoading ? 0.5 : 1,
                  pointerEvents: autopilotLoading ? 'none' : 'auto',
                }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleAutopilotToggle}
              >
                {autopilotLoading ? <Loader2 size={10} className="animate-spin" /> : autopilotRunning ? <Square size={10} /> : <Play size={10} />}
                {autopilotRunning ? t('social.stop') : t('social.start')}
              </motion.button>
            </div>

            {/* 下次定时 */}
            {socialStatus?.next_scheduled_time && (
              <div className="flex items-center gap-2 mb-4">
                <Clock size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                  {t('social.nextSchedule')}: {socialStatus.next_scheduled_action ?? '—'} · {socialStatus.next_scheduled_time}
                </span>
              </div>
            )}

            {/* 草稿列表 */}
            <div>
              <span className="text-label mb-3 block" style={{ color: 'var(--text-tertiary)' }}>
                {t('social.draftBox')} ({drafts.length})
              </span>
              <div className="space-y-2">
                {drafts.length === 0 && (
                  <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('social.noDrafts')}</span>
                )}
                {drafts.slice(0, 5).map((draft, i) => {
                  const pConfig = draft.platform ? getPlatformCfg(draft.platform) : null;
                  return (
                    <div key={draft.id ?? i} className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                      style={{ background: 'var(--bg-base)' }}>
                      {pConfig && (
                        <span className="flex-shrink-0 px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                          style={{ background: pConfig.bg, color: pConfig.color }}>
                          {t(pConfig.labelKey)}
                        </span>
                      )}
                      <span className="font-mono text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                        {draft.title}
                      </span>
                      {draft.status && (
                        <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                          {draft.status}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* 平台状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Globe size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>{t('social.platformStatus')}</span>
            </div>

            <div className="space-y-3">
              {platforms.length === 0 && (
                <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('social.noPlatformData')}</span>
              )}
              {platforms.map((p, i) => {
                const cfg = getPlatformCfg(p.platform);
                return (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
                    <div className="relative flex-shrink-0">
                      <div className="w-3 h-3 rounded-full"
                        style={{ background: p.connected ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                      {p.connected && (
                        <div className="absolute inset-0 w-3 h-3 rounded-full animate-ping opacity-30"
                          style={{ background: 'var(--accent-green)' }} />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-xs font-medium block" style={{ color: 'var(--text-primary)' }}>
                        {t(cfg.labelKey)}
                      </span>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {p.connected ? t('social.connected') : t('social.disconnected')}
                      </span>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <span className="font-display text-sm font-bold block" style={{ color: cfg.color }}>
                        {p.posts_today ?? 0}
                      </span>
                      <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>{t('social.postsToday')}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* 内容日历 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <CalendarDays size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>{t('social.contentCalendar')}</span>
            </div>

            <div className="space-y-3">
              {calendar.length === 0 && (
                <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('social.noScheduledPosts')}</span>
              )}
              {calendar.slice(0, 5).map((item, i) => {
                const pConfig = getPlatformCfg(item.platform);
                return (
                  <div key={item.id ?? i} className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: 'var(--bg-base)' }}>
                    <span className="font-mono text-xs font-bold w-16 flex-shrink-0 truncate"
                      style={{ color: 'var(--accent-purple)' }}>
                      {item.scheduled_time}
                    </span>
                    <span className="flex-shrink-0 px-1.5 py-0.5 rounded font-mono text-[9px] tracking-wider"
                      style={{ background: pConfig.bg, color: pConfig.color }}>
                      {t(pConfig.labelKey)}
                    </span>
                    <span className="font-mono text-[11px] truncate" style={{ color: 'var(--text-secondary)' }}>
                      {item.title}
                    </span>
                  </div>
                );
              })}
            </div>

            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              {t('social.calendarHint')}
            </p>
          </div>
        </motion.div>

        {/* ====== Row 2: 热点追踪 (span-4) + AI 内容生成 (span-4) + 平台发帖统计 (span-4) ====== */}

        {/* 热点追踪 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Flame size={16} style={{ color: 'var(--accent-red)' }} />
              <span className="text-label" style={{ color: 'var(--accent-red)' }}>{t('social.trendingTopics')}</span>
            </div>

            <div className="space-y-2">
              {topics.length === 0 && (
                <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('social.noTopics')}</span>
              )}
              {topics.slice(0, 6).map((topic, i) => (
                <div key={topic.id ?? i} className="flex items-center gap-3 px-3 py-2 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}>
                  <span className="font-mono text-[10px] w-4 text-center flex-shrink-0"
                    style={{ color: i < 3 ? 'var(--accent-red)' : 'var(--text-disabled)' }}>
                    {i + 1}
                  </span>
                  <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                    {topic.name}
                  </span>
                  {topic.platform && (
                    <span className="font-mono text-[9px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {topic.platform}
                    </span>
                  )}
                  <HeatBar value={topic.heat} />
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* AI 内容生成统计 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Sparkles size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>{t('social.contentStats')}</span>
            </div>

            <div className="space-y-4">
              <ContentStat label={t('social.postsToday')} value={String(totalPostsToday)} unit={t('social.unitPost')} accent="var(--accent-cyan)" />
              <ContentStat label={t('social.drafts')} value={String(drafts.length)} unit={t('social.unitPost')} accent="var(--accent-amber)" />
              <ContentStat label={t('social.connectedPlatforms')} value={String(connectedCount)} unit={t('social.unitPlatform')} accent="var(--accent-green)" />
              <ContentStat label={t('social.pendingPublish')} value={String(calendar.length)} unit={t('social.unitPost')} accent="var(--accent-purple)" />
            </div>
          </div>
        </motion.div>

        {/* 平台发帖详情 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Share2 size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>{t('social.postAnalysis')}</span>
            </div>

            <div className="space-y-3">
              {platforms.map((p, i) => {
                const cfg = getPlatformCfg(p.platform);
                return (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{t(cfg.labelKey)}</span>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <span className="font-mono text-xs block" style={{ color: cfg.color }}>
                          {t('social.today')} {p.posts_today ?? 0}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {t('social.total')} {p.total_posts ?? 0}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
              {platforms.length === 0 && (
                <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('common.noData')}</span>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

type SProps = { icon: React.ElementType; label: string; value: string; accent: string };

/** 概览统计块 */
function StatBlock({ icon: Icon, label, value, accent }: SProps) {
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={12} style={{ color: accent }} />
        <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <span className="text-metric" style={{ color: accent }}>{value}</span>
    </div>
  );
}

/** 热度条 */
function HeatBar({ value }: { value: number }) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div className="flex items-center gap-1.5 flex-shrink-0">
      <div className="w-10 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>
        <div className="h-full rounded-full" style={{ width: `${clamped}%`, background: 'linear-gradient(90deg, var(--accent-amber), var(--accent-red))', opacity: 0.6 + clamped * 0.004 }} />
      </div>
      <span className="font-mono text-[9px] w-6 text-right" style={{ color: 'var(--accent-red)' }}>{value}</span>
    </div>
  );
}

/** AI 内容生成统计行 */
function ContentStat({ label, value, unit, accent }: { label: string; value: string; unit: string; accent: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <div className="flex items-baseline gap-1">
        <span className="font-display text-lg font-bold" style={{ color: accent }}>{value}</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{unit}</span>
      </div>
    </div>
  );
}

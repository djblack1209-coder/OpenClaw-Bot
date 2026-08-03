import { useState, useCallback } from 'react';
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
  CheckCircle2,
  Fish,
  Eye,
  MousePointerClick,
  MessageSquare,
  Send,
  ShieldCheck,
  UserRound,
  XCircle,
  ExternalLink,
  ThumbsUp,
  RotateCcw,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';
import { useActivePagePolling } from '@/hooks/useActivePagePolling';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useAppStore } from '@/stores/appStore';

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

const strategyPresetOptions = [
  { id: 'auto_mcn_growth', labelKey: 'social.strategy.autoMcn' },
  { id: 'x_wealth_frontier', labelKey: 'social.strategy.xWealthFull' },
  { id: 'x_absurd_growth', labelKey: 'social.strategy.xAbsurdFull' },
  { id: 'xhs_lifestyle_tutorial', labelKey: 'social.strategy.xhsLifestyleFull' },
  { id: 'xianyu_deal_closer', labelKey: 'social.strategy.xianyuDealFull' },
];

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
  title?: string;
  topic?: string;
  content?: string;
  text?: string;
  platform?: string;
  status?: string;
  review_status?: 'approved' | 'rejected' | 'pending' | 'needs_review' | string;
  approved_by?: string;
  created_at?: string;
  seed?: { title?: string; source?: string; language?: string; heat_reason?: string };
  publish_result?: { url?: string; error?: string; success?: boolean };
}
interface CalendarItem {
  id: string;
  title: string;
  platform: string;
  scheduled_time: string;
}
interface TopicItem {
  id?: string;
  name?: string;
  title?: string;
  heat?: number;
  score?: number;
  platform?: string;
  source?: string;
  url?: string;
  summary?: string;
}
interface BrowserStatusData {
  success?: boolean;
  browser_running?: boolean;
  x_ready?: boolean | null;
  xiaohongshu_ready?: boolean | null;
  tabs?: number;
  urls?: string[];
}
interface PersonaItem {
  persona_id?: string;
  id?: string;
  display_name?: string;
  name?: string;
  platform_accounts?: Record<string, { name?: string; bio?: string }>;
}
interface XianyuStatusData {
  running?: boolean;
  online?: boolean;
  cookie_ok?: boolean;
  auto_reply_active?: boolean;
  unread_chats?: number;
  conversations_today?: number;
}
interface WorkspacePlatform {
  id: string;
  name?: string;
  title?: string;
  subtitle?: string;
  ready?: boolean;
  status?: string;
  metric?: string;
  detail?: string;
  strategy_preset?: string;
  strategy_label?: string;
  growth_loop?: string;
  posts_today?: number;
  total_posts?: number;
  needs_review?: number;
  ready_to_publish?: number;
  conversations_today?: number;
  next_step?: string;
  sample_preview?: string;
}
interface StrategySummaryData {
  preset?: string;
  effective_preset?: string;
  label?: string;
  short_label?: string;
  platform?: string;
  platform_style?: string;
  audience?: string;
  growth_loop?: string;
  content_focus?: string;
  persona_tags?: string[];
  review_required?: boolean;
  auto_publish_enabled?: boolean;
  external_actions_locked?: boolean;
}
interface SocialOpsWorkspaceData {
  success?: boolean;
  review_required?: boolean;
  auto_publish_enabled?: boolean;
  strategy_summary?: StrategySummaryData;
  extension_status?: { strategy_summary?: StrategySummaryData; settings?: Record<string, unknown>; platform?: string; running?: boolean; online?: boolean };
  growth_feedback?: GrowthFeedbackData;
  growth_draft_action?: GrowthDraftAction;
  platforms?: WorkspacePlatform[];
  review_gate?: {
    enabled?: boolean;
    needs_review?: number;
    ready_to_publish?: number;
    growth_feedback_applied?: boolean;
  };
  browser_status?: BrowserStatusData;
  social_status?: SocialStatusData;
  drafts?: DraftItem[];
  personas?: PersonaItem[];
  persona_review?: PersonaReviewData;
  persona_check?: {
    thesis?: string;
    verdict?: string;
    needs_confirmation?: boolean;
    approved?: boolean;
    current?: PersonaItem;
    proposal?: PersonaProposal;
    review_samples?: PersonaSample[];
    sample_count?: number;
  };
  skill_audit?: {
    exists?: boolean;
    verdict?: string;
    files?: { id: string; path: string; exists: boolean }[];
  };
  xianyu_status?: XianyuStatusData;
  xianyu_conversations?: unknown[];
  review_pack?: SocialReviewPackData;
}
interface PersonaProposal {
  proposal_id?: string;
  display_name?: string;
  one_liner?: string;
  positioning?: string;
  audience?: string[];
  tone?: string[];
  do?: string[];
  dont?: string[];
  sample_posts?: PersonaSample[];
}
interface PersonaSample {
  id?: string;
  platform?: string;
  title?: string;
  body?: string;
  text?: string;
  source?: string;
  language?: string;
  heat_reason?: string;
  status?: string;
}
interface PersonaReviewData {
  approved?: boolean;
  needs_confirmation?: boolean;
  proposal?: PersonaProposal;
  state?: { approved_by?: string; approved_at?: string; notes?: string };
  verdict?: string;
}
interface SocialReviewPackData {
  persona?: PersonaProposal;
  persona_approved?: boolean;
  samples?: PersonaSample[];
  sample_count?: number;
  content_verdict?: string;
  guardrails?: string[];
  skill_findings?: { name?: string; verdict?: string; action?: string }[];
}
interface GrowthFeedbackSignal {
  title?: string;
  draft_id?: string;
  tags?: string[];
  metrics?: {
    likes?: number;
    comments?: number;
    shares?: number;
    impressions?: number;
    saves?: number;
    engagements?: number;
  };
  learning?: string;
  growth_feedback_reason?: string;
  captured_at?: string;
}
interface GrowthFeedbackData {
  success?: boolean;
  platform?: string;
  high_signal_count?: number;
  baseline_count?: number;
  top_tags?: string[];
  signals?: GrowthFeedbackSignal[];
  recommendations?: string[];
  auto_publish_enabled?: boolean;
  external_actions_locked?: boolean;
  next_action?: string;
}
interface GrowthDraftAction {
  id?: string;
  platform?: string;
  label?: string;
  enabled?: boolean;
  limit?: number;
  requires_owner_review?: boolean;
  auto_publish_enabled?: boolean;
  external_actions_locked?: boolean;
  next_action?: string;
}
interface PendingAction {
  type: 'approve' | 'reject' | 'publish';
  index: number;
  draft: DraftItem;
}

const personaThesis = '中文/英文热点观察员 + 抽象吐槽 + 低风险追梗，先积累关注，再沉淀系列内容。';

const draftText = (draft: DraftItem) => draft.content || draft.text || draft.title || draft.topic || '';
const isDraftApproved = (draft: DraftItem) => draft.review_status === 'approved' || draft.status === 'approved';
const isPublishableStatus = (draft: DraftItem) => !['published', 'publishing', 'rejected'].includes(String(draft.status || ''));

/* ====== 主组件 ====== */

/**
 * 社交媒体页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示社媒运营中心全部关键指标
 * 使用真实后端 API 数据
 */
export function Social() {
  const { t } = useLanguage();
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);
  const [socialStatus, setSocialStatus] = useState<SocialStatusData | null>(null);
  const [drafts, setDrafts] = useState<DraftItem[]>([]);
  const [calendar, setCalendar] = useState<CalendarItem[]>([]);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [browserStatus, setBrowserStatus] = useState<BrowserStatusData | null>(null);
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [xianyuStatus, setXianyuStatus] = useState<XianyuStatusData | null>(null);
  const [xianyuConversations, setXianyuConversations] = useState<unknown[]>([]);
  const [opsWorkspace, setOpsWorkspace] = useState<SocialOpsWorkspaceData | null>(null);
  const [personaReview, setPersonaReview] = useState<PersonaReviewData | null>(null);
  const [reviewPack, setReviewPack] = useState<SocialReviewPackData | null>(null);
  const [growthFeedback, setGrowthFeedback] = useState<GrowthFeedbackData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autopilotLoading, setAutopilotLoading] = useState(false);
  /* 草稿展开/编辑状态 */
  const [expandedDraftId, setExpandedDraftId] = useState<string | null>(null);
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [personaReviewLoading, setPersonaReviewLoading] = useState(false);
  const [growthDraftLoading, setGrowthDraftLoading] = useState(false);
  const [strategySaving, setStrategySaving] = useState(false);
  const [selectedStrategyPreset, setSelectedStrategyPreset] = useState('auto_mcn_growth');
  const [browserActionLoading, setBrowserActionLoading] = useState<string | null>(null);

  /* ====== 数据拉取 ====== */
  const fetchData = useCallback(async () => {
    try {
      const [workspaceRes, reviewPackRes, growthFeedbackRes, calendarRes, topicsRes] = await Promise.allSettled([
        api.clawbotSocialOpsWorkspace(),
        api.clawbotSocialReviewPack(8),
        api.clawbotSocialGrowthFeedback('x', 6),
        api.clawbotSocialCalendar(),
        api.clawbotSocialTopics({ category: 'all' } as any),
      ]);

      if (workspaceRes.status === 'fulfilled') {
        const workspace = workspaceRes.value as SocialOpsWorkspaceData;
        setOpsWorkspace(workspace);
        if (workspace.social_status) setSocialStatus(workspace.social_status);
        if (workspace.browser_status) setBrowserStatus(workspace.browser_status);
        if (Array.isArray(workspace.drafts)) setDrafts(workspace.drafts);
        if (Array.isArray(workspace.personas)) setPersonas(workspace.personas);
        if (workspace.xianyu_status) setXianyuStatus(workspace.xianyu_status);
        if (Array.isArray(workspace.xianyu_conversations)) setXianyuConversations(workspace.xianyu_conversations);
        if (workspace.persona_review) setPersonaReview(workspace.persona_review);
        if (workspace.review_pack) setReviewPack(workspace.review_pack);
        if (workspace.growth_feedback) setGrowthFeedback(workspace.growth_feedback);
        const workspaceStrategy = workspace.strategy_summary || workspace.extension_status?.strategy_summary;
        if (workspaceStrategy?.preset) setSelectedStrategyPreset(workspaceStrategy.preset);
      } else {
        setOpsWorkspace(null);
        const [statusRes, draftsRes, browserRes, personasRes, personaReviewRes, xianyuStatusRes, xianyuConvRes] = await Promise.allSettled([
          api.clawbotSocialStatus(),
          api.clawbotSocialDrafts(),
          api.clawbotSocialBrowserStatus(),
          api.clawbotSocialPersonas(),
          api.clawbotSocialPersonaReview(),
          api.xianyuStatus(),
          api.xianyuConversations(10),
        ]);
        if (statusRes.status === 'fulfilled') setSocialStatus(statusRes.value as any);
        if (draftsRes.status === 'fulfilled') {
          const d = draftsRes.value as any;
          setDrafts(Array.isArray(d) ? d : d?.drafts ?? []);
        }
        if (browserRes.status === 'fulfilled') setBrowserStatus(browserRes.value as BrowserStatusData);
        if (personasRes.status === 'fulfilled') {
          const pdata = personasRes.value as any;
          setPersonas(Array.isArray(pdata) ? pdata : pdata?.personas ?? []);
        }
        if (personaReviewRes.status === 'fulfilled') setPersonaReview(personaReviewRes.value as PersonaReviewData);
        if (xianyuStatusRes.status === 'fulfilled') setXianyuStatus(xianyuStatusRes.value as XianyuStatusData);
        if (xianyuConvRes.status === 'fulfilled') {
          const cdata = xianyuConvRes.value as any;
          setXianyuConversations(Array.isArray(cdata) ? cdata : cdata?.conversations ?? []);
        }
      }
      if (reviewPackRes.status === 'fulfilled') {
        setReviewPack(reviewPackRes.value as SocialReviewPackData);
      }
      if (growthFeedbackRes.status === 'fulfilled') {
        setGrowthFeedback(growthFeedbackRes.value as GrowthFeedbackData);
      }
      if (calendarRes.status === 'fulfilled') {
        const c = calendarRes.value as any;
        setCalendar(Array.isArray(c) ? c : c?.items ?? c?.calendar ?? []);
      }
      if (topicsRes.status === 'fulfilled') {
        /* 避免与外层 i18n t 函数同名 */
        const topicData = topicsRes.value as any;
        setTopics(Array.isArray(topicData) ? topicData : topicData?.topics ?? []);
      }
      setError(null);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? t('social.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  /* 使用可见性感知轮询，仅在社交页激活时刷新数据 */
  useActivePagePolling('social', fetchData, 30_000);

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
  const selectedPersona = opsWorkspace?.persona_check?.current || personas[0];
  const activePersonaReview = opsWorkspace?.persona_review || personaReview;
  const activePersonaProposal = opsWorkspace?.persona_check?.proposal || activePersonaReview?.proposal;
  const personaApproved = Boolean(opsWorkspace?.persona_check?.approved ?? activePersonaReview?.approved);
  const personaNeedsConfirmation = Boolean(opsWorkspace?.persona_check?.needs_confirmation ?? activePersonaReview?.needs_confirmation ?? true);
  const personaDetail = opsWorkspace?.persona_check?.verdict || activePersonaReview?.verdict || opsWorkspace?.persona_check?.thesis || personaThesis;
  const activeReviewPack = reviewPack || opsWorkspace?.review_pack || null;
  const activeGrowthFeedback = opsWorkspace?.growth_feedback || growthFeedback || null;
  const growthSignals = activeGrowthFeedback?.signals ?? [];
  const growthTopTags = activeGrowthFeedback?.top_tags ?? [];
  const growthRecommendations = activeGrowthFeedback?.recommendations ?? [];
  const growthDraftAction = opsWorkspace?.growth_draft_action;
  const activeStrategySummary = opsWorkspace?.strategy_summary || opsWorkspace?.extension_status?.strategy_summary || null;
  const personaPreviewSamples = activeReviewPack?.samples?.length
    ? activeReviewPack.samples
    : opsWorkspace?.persona_check?.review_samples?.length
    ? opsWorkspace.persona_check.review_samples
    : activePersonaProposal?.sample_posts ?? [];
  const skillAuditDetail = opsWorkspace?.skill_audit?.verdict || t('social.skillsAuditDefault');
  const reviewReadyCount = opsWorkspace?.review_gate?.ready_to_publish ?? drafts.filter((draft) => isDraftApproved(draft) && isPublishableStatus(draft)).length;
  const needsReviewCount = opsWorkspace?.review_gate?.needs_review ?? drafts.filter((draft) => !isDraftApproved(draft) && isPublishableStatus(draft)).length;
  const xPlatform = platforms.find((p) => ['x', 'twitter'].includes((p.platform || '').toLowerCase()));
  const xhsPlatform = platforms.find((p) => ['xhs', 'xiaohongshu'].includes((p.platform || '').toLowerCase()));
  const workspacePlatformMap = new Map((opsWorkspace?.platforms ?? []).map((p) => [p.id, p]));
  const focusFirstDraft = (platformNames: string[]) => {
    const index = drafts.findIndex((draft) => platformNames.includes(String(draft.platform || '').toLowerCase()));
    if (index >= 0) {
      const draft = drafts[index];
      setExpandedDraftId(draft.id ?? String(index));
      setEditingDraftId(null);
      return;
    }
    toast.info(t('social.noPlatformDraft'), { channel: 'log' });
  };
  const normalizeReady = (value: unknown) => value === true || ['ready', 'connected', 'ok', 'true'].includes(String(value || '').toLowerCase());
  const runBrowserControl = async (action: string, platform: string) => {
    const key = `${platform}:${action}`;
    setBrowserActionLoading(key);
    try {
      const result = await api.clawbotSocialBrowserControl(action, platform) as any;
      if (result?.success === false) {
        toast.error(String(result?.error || t('social.operationFailed')), { channel: 'notification' });
      } else {
        toast.success(t('social.browserActionSubmitted'), { channel: 'log' });
      }
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
    } finally {
      setBrowserActionLoading(null);
    }
  };
  const xWorkspace = workspacePlatformMap.get('x');
  const xhsWorkspace = workspacePlatformMap.get('xhs');
  const xianyuWorkspace = workspacePlatformMap.get('xianyu');
  const workspacePlatforms = [
    {
      id: 'x',
      icon: Share2,
      title: xWorkspace?.title || t('social.workspace.x.title'),
      subtitle: xWorkspace?.subtitle || t('social.workspace.x.subtitle'),
      status: xWorkspace?.status || (normalizeReady((browserStatus as any)?.x_ready ?? (browserStatus as any)?.x) ? t('social.browserReady') : t('social.needLogin')),
      metric: xWorkspace?.metric || `${xPlatform?.posts_today ?? 0} ${t('social.postsToday')}`,
      detail: xWorkspace?.detail || t('social.workspace.x.detail'),
      strategyLabel: xWorkspace?.strategy_label || (activeStrategySummary?.effective_preset?.startsWith('x_') ? activeStrategySummary.short_label : t('social.strategy.xWealth')),
      strategyPreset: xWorkspace?.strategy_preset || (activeStrategySummary?.effective_preset?.startsWith('x_') ? activeStrategySummary.effective_preset : 'x_wealth_frontier'),
      growthLoop: xWorkspace?.growth_loop || (activeStrategySummary?.effective_preset?.startsWith('x_') ? activeStrategySummary.growth_loop : t('social.strategy.xWealthLoop')),
      strategyLabelText: t('social.strategyLabel'),
      growthLoopLabel: t('social.growthLoopLabel'),
      accent: 'var(--text-primary)',
      ready: Boolean(xWorkspace?.ready ?? normalizeReady((browserStatus as any)?.x_ready ?? (browserStatus as any)?.x)),
      action: t('social.reviewDrafts'),
      openAction: t('social.openBrowser'),
      loginAction: t('social.loginBrowser'),
      openLoading: browserActionLoading === 'x:open_x',
      loginLoading: browserActionLoading === 'x:login_x',
      nextStep: xWorkspace?.next_step || t('social.workspace.x.nextStep'),
      samplePreview: xWorkspace?.sample_preview || '',
      nextStepLabel: t('social.nextStep'),
      samplePreviewLabel: t('social.samplePreview'),
      onOpen: () => runBrowserControl('open_x', 'x'),
      onLogin: () => runBrowserControl('login_x', 'x'),
      onAction: () => focusFirstDraft(['x', 'twitter']),
    },
    {
      id: 'xhs',
      icon: Sparkles,
      title: xhsWorkspace?.title || t('social.workspace.xhs.title'),
      subtitle: xhsWorkspace?.subtitle || t('social.workspace.xhs.subtitle'),
      status: xhsWorkspace?.status || (normalizeReady((browserStatus as any)?.xiaohongshu_ready ?? (browserStatus as any)?.xhs) ? t('social.browserReady') : t('social.needLogin')),
      metric: xhsWorkspace?.metric || `${xhsPlatform?.posts_today ?? 0} ${t('social.postsToday')}`,
      detail: xhsWorkspace?.detail || t('social.workspace.xhs.detail'),
      strategyLabel: xhsWorkspace?.strategy_label || t('social.strategy.xhsLifestyle'),
      strategyPreset: xhsWorkspace?.strategy_preset || 'xhs_lifestyle_tutorial',
      growthLoop: xhsWorkspace?.growth_loop || t('social.strategy.xhsLifestyleLoop'),
      strategyLabelText: t('social.strategyLabel'),
      growthLoopLabel: t('social.growthLoopLabel'),
      accent: '#ff2442',
      ready: Boolean(xhsWorkspace?.ready ?? normalizeReady((browserStatus as any)?.xiaohongshu_ready ?? (browserStatus as any)?.xhs)),
      action: t('social.reviewDrafts'),
      openAction: t('social.openBrowser'),
      loginAction: t('social.loginBrowser'),
      openLoading: browserActionLoading === 'xhs:open_xhs',
      loginLoading: browserActionLoading === 'xhs:login_xhs',
      nextStep: xhsWorkspace?.next_step || t('social.workspace.xhs.nextStep'),
      samplePreview: xhsWorkspace?.sample_preview || '',
      nextStepLabel: t('social.nextStep'),
      samplePreviewLabel: t('social.samplePreview'),
      onOpen: () => runBrowserControl('open_xhs', 'xhs'),
      onLogin: () => runBrowserControl('login_xhs', 'xhs'),
      onAction: () => focusFirstDraft(['xhs', 'xiaohongshu']),
    },
    {
      id: 'xianyu',
      icon: Fish,
      title: xianyuWorkspace?.title || t('social.workspace.xianyu.title'),
      subtitle: xianyuWorkspace?.subtitle || t('social.workspace.xianyu.subtitle'),
      status: xianyuWorkspace?.status || (xianyuStatus?.running || xianyuStatus?.online ? t('xianyu.status.running') : t('xianyu.status.stopped')),
      metric: xianyuWorkspace?.metric || `${xianyuConversations.length || xianyuStatus?.unread_chats || 0} ${t('social.workspace.xianyu.metric')}`,
      detail: xianyuWorkspace?.detail || t('social.workspace.xianyu.detail'),
      strategyLabel: xianyuWorkspace?.strategy_label || t('social.strategy.xianyuDeal'),
      strategyPreset: xianyuWorkspace?.strategy_preset || 'xianyu_deal_closer',
      growthLoop: xianyuWorkspace?.growth_loop || t('social.strategy.xianyuDealLoop'),
      strategyLabelText: t('social.strategyLabel'),
      growthLoopLabel: t('social.growthLoopLabel'),
      accent: 'var(--accent-amber)',
      ready: xianyuWorkspace?.ready ?? Boolean(xianyuStatus?.cookie_ok || xianyuStatus?.running || xianyuStatus?.online),
      action: t('social.openXianyuManager'),
      openAction: t('social.refreshBrowserStatus'),
      loginAction: '',
      openLoading: browserActionLoading === 'all:status',
      loginLoading: false,
      nextStep: xianyuWorkspace?.next_step || t('social.workspace.xianyu.nextStep'),
      samplePreview: xianyuWorkspace?.sample_preview || '',
      nextStepLabel: t('social.nextStep'),
      samplePreviewLabel: t('social.samplePreview'),
      onOpen: () => runBrowserControl('status', 'all'),
      onLogin: undefined,
      onAction: () => setCurrentPage('xianyu'),
    },
  ];

  const handleStrategyUpdate = async () => {
    setStrategySaving(true);
    try {
      const result = await api.clawbotSocialStrategyUpdate(
        selectedStrategyPreset,
        activeStrategySummary?.platform || opsWorkspace?.extension_status?.platform || 'x',
      ) as { success?: boolean; error?: string; strategy_summary?: StrategySummaryData };
      if (result?.success === false) {
        toast.error(String(result?.error || t('social.operationFailed')), { channel: 'notification' });
        return;
      }
      toast.success(t('social.strategySaved'), { channel: 'log' });
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
    } finally {
      setStrategySaving(false);
    }
  };

  const handleGenerateGrowthDrafts = async () => {
    setGrowthDraftLoading(true);
    try {
      const result = await api.clawbotSocialGrowthDrafts(
        growthDraftAction?.platform || activeGrowthFeedback?.platform || 'x',
        growthDraftAction?.limit || 3,
      ) as { drafts?: DraftItem[]; created_count?: number; success?: boolean; error?: string };
      if (result?.success === false) {
        toast.error(String(result?.error || t('social.operationFailed')), { channel: 'notification' });
        return;
      }
      const created = Number(result?.created_count ?? result?.drafts?.length ?? 0);
      toast.success(`${t('social.generateGrowthDraftsSuccess')}: ${created}`, { channel: 'log' });
      if (Array.isArray(result?.drafts) && result.drafts.length > 0) {
        setExpandedDraftId(result.drafts[0].id || null);
      }
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
    } finally {
      setGrowthDraftLoading(false);
    }
  };

  const handlePersonaReview = async (approved: boolean) => {
    setPersonaReviewLoading(true);
    try {
      const result = await api.clawbotSocialPersonaReviewUpdate(approved, 'owner', approved ? '用户确认热点抽象号方向' : '用户打回热点抽象号方向') as PersonaReviewData;
      setPersonaReview(result);
      toast.success(approved ? t('social.personaApproved') : t('social.personaRejected'), { channel: 'log' });
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
    } finally {
      setPersonaReviewLoading(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!pendingAction) return;
    setActionLoading(true);
    try {
      if (pendingAction.type === 'approve') {
        await api.clawbotSocialDraftReview(pendingAction.index, true, 'owner');
        toast.success(t('social.reviewApproved'), { channel: 'log' });
      } else if (pendingAction.type === 'reject') {
        await api.clawbotSocialDraftReview(pendingAction.index, false, 'owner');
        toast.success(t('social.reviewRejected'), { channel: 'log' });
      } else {
        const confirmation = await api.clawbotSocialDraftFinalConfirm(
          pendingAction.index,
          'owner',
        ) as {
          success?: boolean;
          confirmation_token?: string;
          requires_review?: boolean;
          error?: string;
        };
        if (confirmation?.success === false || !confirmation?.confirmation_token) {
          if (confirmation?.requires_review) {
            toast.error(t('social.reviewRequired'), { channel: 'notification' });
          } else {
            toast.error(String(confirmation?.error || t('social.operationFailed')), { channel: 'notification' });
          }
          return;
        }
        const result = await api.clawbotSocialDraftPublish(
          pendingAction.index,
          confirmation.confirmation_token,
        ) as {
          success?: boolean;
          requires_review?: boolean;
          state_update_rejected?: boolean;
          error?: string;
          url?: string;
          external_result?: { success?: boolean; url?: string; post_url?: string };
        };
        const externalResult = result?.external_result;
        const publishedUrl = String(
          result?.url || externalResult?.url || externalResult?.post_url || '',
        ).trim();
        if (result?.state_update_rejected && externalResult?.success) {
          toast.warning(
            `${t('social.publishExternalSuccess')}${publishedUrl ? `: ${publishedUrl}` : ''}`,
            { channel: 'notification' },
          );
        } else if (result?.success === false && result?.requires_review) {
          toast.error(t('social.reviewRequired'), { channel: 'notification' });
          return;
        } else if (result?.success === false) {
          toast.error(String(result?.error || t('social.operationFailed')), { channel: 'notification' });
          return;
        } else {
          toast.success(
            `${t('social.publishSubmitted')}${publishedUrl ? `: ${publishedUrl}` : ''}`,
            { channel: 'log' },
          );
        }
      }
      setPendingAction(null);
      await fetchData();
    } catch {
      toast.error(t('social.operationFailed'), { channel: 'notification' });
    } finally {
      setActionLoading(false);
    }
  };

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

            {/* 商业级运营驾驶舱：少参数，只显示状态、确认和下一步 */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mb-5">
              <CopilotCard
                icon={ShieldCheck}
                title={t('social.reviewGateTitle')}
                value={t('social.reviewGateOn')}
                detail={`${t('social.needReview')}: ${needsReviewCount} · ${t('social.readyToPublish')}: ${reviewReadyCount}`}
                accent="var(--accent-green)"
              />
              <CopilotCard
                icon={MousePointerClick}
                title={t('social.browserControl')}
                value={browserStatus?.browser_running ? t('social.browserRunning') : t('social.browserStopped')}
                detail={`X ${normalizeReady((browserStatus as any)?.x_ready ?? (browserStatus as any)?.x) ? 'OK' : '—'} · XHS ${normalizeReady((browserStatus as any)?.xiaohongshu_ready ?? (browserStatus as any)?.xhs) ? 'OK' : '—'} · Tabs ${browserStatus?.tabs ?? 0}`}
                accent="var(--accent-cyan)"
              />
              <CopilotCard
                icon={UserRound}
                title={t('social.personaCheck')}
                value={selectedPersona?.display_name || selectedPersona?.name || selectedPersona?.persona_id || 'zhou-yuheng'}
                detail={personaDetail}
                accent="var(--accent-amber)"
              />
            </div>
            <div className="flex items-start gap-2 px-3 py-2 rounded-xl mb-5"
              style={{ background: 'rgba(255,170,0,0.06)', border: '1px solid rgba(255,170,0,0.14)' }}>
              <ShieldCheck size={13} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent-amber)' }} />
              <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                {skillAuditDetail}
              </span>
            </div>

            {activeStrategySummary && (
              <div className="rounded-2xl px-4 py-3 mb-5" style={{
                background: 'rgba(255,255,255,0.035)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}>
                <div className="flex flex-col xl:flex-row xl:items-center gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <Sparkles size={14} style={{ color: 'var(--accent-purple)' }} />
                    <span className="text-label" style={{ color: 'var(--accent-purple)' }}>{t('social.strategySummaryTitle')}</span>
                    <span className="font-mono text-[10px] px-2 py-1 rounded-full" style={{ background: 'rgba(155,93,229,0.10)', color: 'var(--accent-purple)' }}>
                      {activeStrategySummary.short_label || activeStrategySummary.label || activeStrategySummary.effective_preset}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] leading-relaxed flex-1" style={{ color: 'var(--text-tertiary)' }}>
                    {activeStrategySummary.content_focus || activeStrategySummary.growth_loop || t('social.strategySummaryFallback')}
                  </span>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-2 xl:w-[390px]">
                    <select
                      className="flex-1 px-3 py-2 rounded-xl font-mono text-[10px] outline-none"
                      style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(155,93,229,0.18)', color: 'var(--text-primary)' }}
                      value={selectedStrategyPreset}
                      onChange={(e) => setSelectedStrategyPreset(e.target.value)}
                      disabled={strategySaving}
                      aria-label={t('social.strategySelectLabel')}
                    >
                      {strategyPresetOptions.map((option) => (
                        <option key={option.id} value={option.id}>{t(option.labelKey)}</option>
                      ))}
                    </select>
                    <button
                      className="px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                      style={{ background: 'rgba(0,255,170,0.08)', border: '1px solid rgba(0,255,170,0.2)', color: 'var(--accent-green)', opacity: strategySaving ? 0.55 : 1 }}
                      onClick={handleStrategyUpdate}
                      disabled={strategySaving}
                    >
                      {strategySaving ? <Loader2 size={11} className="animate-spin" /> : <ShieldCheck size={11} />}
                      {t('social.strategySave')}
                    </button>
                  </div>
                </div>
                <p className="font-mono text-[9px] mt-2" style={{ color: 'var(--text-disabled)' }}>
                  {t('social.strategySaveHint')}
                </p>
              </div>
            )}

            {/* 增长复盘：App 中控同步 Chrome 插件只读表现反馈 */}
            <div className="rounded-2xl p-4 mb-5" style={{
              background: 'rgba(0,212,255,0.035)',
              border: '1px solid rgba(0,212,255,0.12)',
            }}>
              <div className="flex flex-col xl:flex-row xl:items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <ThumbsUp size={15} style={{ color: 'var(--accent-cyan)' }} />
                      <div className="min-w-0">
                        <span className="text-label block" style={{ color: 'var(--accent-cyan)' }}>{t('social.growthFeedbackTitle')}</span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('social.growthFeedbackSubtitle')}</span>
                      </div>
                    </div>
                    <span className="font-mono text-[10px] px-2 py-1 rounded-full flex-shrink-0" style={{
                      background: growthSignals.length ? 'rgba(0,255,170,0.08)' : 'rgba(255,170,0,0.08)',
                      color: growthSignals.length ? 'var(--accent-green)' : 'var(--accent-amber)',
                    }}>
                      {growthSignals.length ? `${growthSignals.length} ${t('social.highSignalCount')}` : t('social.noGrowthSignals')}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <CopilotCard
                      icon={Sparkles}
                      title={t('social.growthHighSignal')}
                      value={String(activeGrowthFeedback?.high_signal_count ?? growthSignals.length)}
                      detail={growthSignals[0]?.growth_feedback_reason || t('social.growthHighSignalHint')}
                      accent="var(--accent-green)"
                    />
                    <CopilotCard
                      icon={Flame}
                      title={t('social.growthTopTags')}
                      value={growthTopTags.slice(0, 2).join(' / ') || '—'}
                      detail={growthTopTags.length ? t('social.growthTopTagsHint') : t('social.growthEmptyHint')}
                      accent="var(--accent-red)"
                    />
                    <CopilotCard
                      icon={ShieldCheck}
                      title={t('social.growthSafety')}
                      value={activeGrowthFeedback?.external_actions_locked === false ? t('social.growthSafetyOff') : t('social.growthSafetyOn')}
                      detail={t('social.growthSafetyHint')}
                      accent="var(--accent-amber)"
                    />
                  </div>
                  {growthSignals.length > 0 ? (
                    <div className="space-y-2">
                      {growthSignals.map((signal, idx) => {
                        if (idx >= 3) return null;
                        return (
                          <div key={`${signal.draft_id || signal.title || 'signal'}-${idx}`} className="rounded-xl px-3 py-2" style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)' }}>
                            <div className="flex items-center justify-between gap-3 mb-1">
                              <span className="font-mono text-[10px] font-bold truncate" style={{ color: 'var(--text-primary)' }}>
                                {signal.title || t('social.untitledSignal')}
                              </span>
                              <span className="font-mono text-[9px] flex-shrink-0" style={{ color: 'var(--accent-green)' }}>
                                {signal.metrics?.likes ?? 0}赞 · {signal.metrics?.comments ?? 0}评 · {signal.metrics?.shares ?? 0}转
                              </span>
                            </div>
                            <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                              {signal.learning || signal.growth_feedback_reason || t('social.growthSignalFallback')}
                            </p>
                            {Boolean(signal.tags?.length) && (
                              <div className="flex flex-wrap gap-1.5 mt-2">
                                {signal.tags?.slice(0, 4).map((tag) => (
                                  <span key={tag} className="font-mono text-[8px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(0,212,255,0.08)', color: 'var(--accent-cyan)' }}>
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                      {t('social.growthEmptyHint')}
                    </p>
                  )}
                  {growthRecommendations.length > 0 && (
                    <div className="mt-3 rounded-xl px-3 py-2" style={{ background: 'rgba(255,170,0,0.055)', border: '1px solid rgba(255,170,0,0.12)' }}>
                      <span className="font-mono text-[9px] uppercase tracking-wider block mb-1" style={{ color: 'var(--accent-amber)' }}>{t('social.growthNextActions')}</span>
                      <ul className="space-y-1">
                        {growthRecommendations.slice(0, 3).map((item) => (
                          <li key={item} className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>· {item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="mt-3 flex flex-col md:flex-row md:items-center gap-2">
                    <button
                      className="px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                      style={{
                        background: 'rgba(0,212,255,0.08)',
                        border: '1px solid rgba(0,212,255,0.2)',
                        color: 'var(--accent-cyan)',
                        opacity: growthDraftLoading || growthDraftAction?.enabled === false ? 0.55 : 1,
                      }}
                      onClick={handleGenerateGrowthDrafts}
                      disabled={growthDraftLoading || growthDraftAction?.enabled === false}
                    >
                      {growthDraftLoading ? <Loader2 size={11} className="animate-spin" /> : <FileText size={11} />}
                      {t('social.generateGrowthDrafts')}
                    </button>
                    <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                      {growthDraftAction?.next_action || t('social.generateGrowthDraftsHint')}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* 人设确认：确认只保存方向，不代表允许自动发布 */}
            <div className="rounded-2xl p-4 mb-5" style={{
              background: personaApproved ? 'rgba(0,255,170,0.05)' : 'rgba(255,170,0,0.05)',
              border: `1px solid ${personaApproved ? 'rgba(0,255,170,0.16)' : 'rgba(255,170,0,0.18)'}`,
            }}>
              <div className="flex flex-col xl:flex-row xl:items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <UserRound size={15} style={{ color: personaApproved ? 'var(--accent-green)' : 'var(--accent-amber)' }} />
                    <span className="text-label" style={{ color: personaApproved ? 'var(--accent-green)' : 'var(--accent-amber)' }}>
                      {personaApproved ? t('social.personaApprovedBadge') : t('social.personaNeedsApprovalBadge')}
                    </span>
                  </div>
                  <div className="font-display text-sm font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
                    {activePersonaProposal?.display_name || t('social.personaProposalTitle')}
                  </div>
                  <p className="font-mono text-[10px] leading-relaxed mb-3" style={{ color: 'var(--text-secondary)' }}>
                    {activePersonaProposal?.one_liner || personaThesis}
                  </p>
                  {activeReviewPack?.content_verdict && (
                    <div className="rounded-xl px-3 py-2 mb-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)' }}>
                      <span className="font-mono text-[9px] uppercase tracking-wider block mb-1" style={{ color: 'var(--accent-cyan)' }}>
                        {t('social.reviewPackVerdict')}
                      </span>
                      <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                        {activeReviewPack.content_verdict}
                      </span>
                    </div>
                  )}
                  {activePersonaProposal?.positioning && (
                    <p className="font-mono text-[10px] leading-relaxed mb-3" style={{ color: 'var(--text-tertiary)' }}>
                      {activePersonaProposal.positioning}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {(activePersonaProposal?.tone ?? ['短', '怪', '有反差', '低风险追梗']).slice(0, 6).map((tag) => (
                      <span key={tag} className="font-mono text-[9px] px-2 py-0.5 rounded-full" style={{
                        background: 'rgba(255,255,255,0.06)',
                        color: 'var(--text-tertiary)',
                      }}>{tag}</span>
                    ))}
                  </div>
                  {Boolean(activeReviewPack?.guardrails?.length) && (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
                      {activeReviewPack?.guardrails?.slice(0, 3).map((item) => (
                        <div key={item} className="rounded-xl px-3 py-2" style={{ background: 'rgba(255,170,0,0.045)', border: '1px solid rgba(255,170,0,0.1)' }}>
                          <span className="font-mono text-[9px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>{item}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {personaPreviewSamples.length > 0 && (
                    <div className="space-y-2">
                      <span className="font-mono text-[9px] block" style={{ color: 'var(--text-disabled)' }}>
                        {opsWorkspace?.persona_check?.review_samples?.length ? t('social.personaRealDraftSamples') : t('social.personaSamples')} ({personaPreviewSamples.length})
                      </span>
                      {personaPreviewSamples.slice(0, 6).map((sample, idx) => (
                        <div key={`${sample.platform}-${idx}`} className="rounded-xl px-3 py-2" style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)' }}>
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="font-mono text-[9px] uppercase tracking-wider" style={{ color: 'var(--accent-cyan)' }}>{sample.platform || 'x'}</span>
                            {sample.source && (
                              <span className="font-mono text-[8px] truncate" style={{ color: 'var(--text-disabled)' }}>{sample.source}</span>
                            )}
                          </div>
                          {sample.title && <span className="font-mono text-[10px] font-bold block mb-1" style={{ color: 'var(--text-primary)' }}>{sample.title}</span>}
                          <span className="font-mono text-[10px] leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
                            {sample.text || sample.body}
                          </span>
                          {sample.heat_reason && (
                            <span className="font-mono text-[8px] mt-1 block" style={{ color: 'var(--text-disabled)' }}>{sample.heat_reason}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex xl:flex-col gap-2 xl:w-36">
                  <button
                    className="flex-1 xl:flex-none px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                    style={{
                      background: 'rgba(0,255,170,0.08)',
                      border: '1px solid rgba(0,255,170,0.22)',
                      color: 'var(--accent-green)',
                      opacity: personaReviewLoading ? 0.55 : 1,
                    }}
                    onClick={() => handlePersonaReview(true)}
                    disabled={personaReviewLoading}
                  >
                    {personaReviewLoading ? <Loader2 size={11} className="animate-spin" /> : <ThumbsUp size={11} />}
                    {personaApproved ? t('social.personaApprovedShort') : t('social.approvePersona')}
                  </button>
                  <button
                    className="flex-1 xl:flex-none px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                    style={{
                      background: 'rgba(255,0,0,0.06)',
                      border: '1px solid rgba(255,0,0,0.18)',
                      color: 'var(--accent-red)',
                      opacity: personaReviewLoading ? 0.55 : 1,
                    }}
                    onClick={() => handlePersonaReview(false)}
                    disabled={personaReviewLoading}
                  >
                    <RotateCcw size={11} />
                    {t('social.rejectPersona')}
                  </button>
                </div>
              </div>
              <p className="font-mono text-[9px] mt-3" style={{ color: 'var(--text-disabled)' }}>
                {personaNeedsConfirmation ? t('social.personaReviewHint') : t('social.personaReviewedHint')}
              </p>
            </div>

            {/* 统一浏览器运营插件入口：X / 小红书 / 闲鱼放在同一个工作台 */}
            <div className="mb-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <span className="text-label block" style={{ color: 'var(--accent-cyan)' }}>{t('social.workspaceTitle')}</span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('social.workspaceSubtitle')}</span>
                </div>
                <span className="font-mono text-[10px] px-2 py-1 rounded-full" style={{ background: 'rgba(0,255,170,0.08)', color: 'var(--accent-green)' }}>
                  {t('social.reviewFirstBadge')}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {workspacePlatforms.map((item) => (
                  <PlatformWorkspaceCard key={item.id} {...item} />
                ))}
              </div>
            </div>

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

            {/* 草稿列表 — 支持展开查看/编辑内容 */}
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
                  const draftId = draft.id ?? String(i);
                  const isExpanded = expandedDraftId === draftId;
                  const isEditing = editingDraftId === draftId;
                  return (
                    <div key={draftId}>
                      {/* 草稿标题行（点击展开/收起） */}
                      <div
                        className="flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all"
                        style={{ background: isExpanded ? 'rgba(0,212,255,0.04)' : 'var(--bg-base)' }}
                        onClick={() => {
                          if (isEditing) return;
                          setExpandedDraftId(isExpanded ? null : draftId);
                          setEditingDraftId(null);
                        }}
                      >
                        {pConfig && (
                          <span className="flex-shrink-0 px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                            style={{ background: pConfig.bg, color: pConfig.color }}>
                            {t(pConfig.labelKey)}
                          </span>
                        )}
                        <span className="font-mono text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                          {draft.title || draft.topic || '(无标题)'}
                        </span>
                        {draft.status && (
                          <span className="font-mono text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                            {draft.status}
                          </span>
                        )}
                        {/* 展开/收起指示器 */}
                        <span className="font-mono text-[10px] flex-shrink-0 transition-transform" style={{
                          color: 'var(--text-tertiary)',
                          transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                        }}>▸</span>
                      </div>
                      {/* 展开的内容区域 */}
                      {isExpanded && (
                        <div className="ml-3 mt-1 px-3 py-3 rounded-xl" style={{
                          background: 'rgba(0,212,255,0.02)',
                          border: '1px solid rgba(0,212,255,0.1)',
                        }}>
                          {isEditing ? (
                            /* 编辑模式 */
                            <div className="space-y-2">
                              <textarea
                                className="w-full px-3 py-2 rounded-lg font-mono text-xs resize-none"
                                style={{
                                  background: 'var(--bg-base)',
                                  color: 'var(--text-primary)',
                                  border: '1px solid rgba(0,212,255,0.2)',
                                  minHeight: 80,
                                  outline: 'none',
                                }}
                                value={editingText}
                                onChange={(e) => setEditingText(e.target.value)}
                                autoFocus
                              />
                              <div className="flex gap-2 justify-end">
                                <button
                                  className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold"
                                  style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}
                                  onClick={() => { setEditingDraftId(null); setEditingText(''); }}
                                >{t('common.cancel')}</button>
                                <button
                                  className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold"
                                  style={{ background: 'var(--accent-cyan)', color: 'var(--bg-primary)' }}
                                  onClick={async () => {
                                    try {
                                      await api.clawbotSocialDraftUpdate(i, editingText);
                                      toast.success(t('common.saving'), { channel: 'log' });
                                      setEditingDraftId(null);
                                      setEditingText('');
                                      await fetchData();
                                    } catch {
                                      toast.error(t('social.operationFailed'), { channel: 'notification' });
                                    }
                                  }}
                                >{t('common.save')}</button>
                              </div>
                            </div>
                          ) : (
                            /* 查看模式 */
                            <div>
                              <p className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
                                {draft.content || draft.text || draft.title || draft.topic || t('common.noData')}
                              </p>
                              {draft.created_at && (
                                <span className="font-mono text-[9px] mt-2 block" style={{ color: 'var(--text-disabled)' }}>
                                  {new Date(draft.created_at).toLocaleString('zh-CN')}
                                </span>
                              )}
                              {draft.seed?.title && (
                                <div className="mt-3 rounded-lg px-3 py-2" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                                  <span className="font-mono text-[9px] block mb-1" style={{ color: 'var(--text-disabled)' }}>{t('social.sourceHotspot')}</span>
                                  <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{draft.seed.title}</span>
                                </div>
                              )}
                              <div className="flex flex-wrap gap-2 mt-3 justify-end">
                                <button
                                  className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold cursor-pointer inline-flex items-center gap-1"
                                  style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)', color: 'var(--accent-cyan)' }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setEditingDraftId(draftId);
                                    setEditingText(draftText(draft));
                                  }}
                                ><Eye size={10} />{t('social.editDraft')}</button>
                                {!isDraftApproved(draft) && isPublishableStatus(draft) && (
                                  <button
                                    className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold cursor-pointer inline-flex items-center gap-1"
                                    style={{ background: 'rgba(0,255,170,0.08)', border: '1px solid rgba(0,255,170,0.25)', color: 'var(--accent-green)' }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPendingAction({ type: 'approve', index: i, draft });
                                    }}
                                  ><CheckCircle2 size={10} />{t('social.approveDraft')}</button>
                                )}
                                {isDraftApproved(draft) && isPublishableStatus(draft) && (
                                  <button
                                    className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold cursor-pointer inline-flex items-center gap-1"
                                    style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.18)', color: 'var(--text-primary)' }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPendingAction({ type: 'publish', index: i, draft });
                                    }}
                                  ><Send size={10} />{t('social.publishDraft')}</button>
                                )}
                                {isPublishableStatus(draft) && (
                                  <button
                                    className="px-3 py-1 rounded-lg font-mono text-[10px] font-bold cursor-pointer inline-flex items-center gap-1"
                                    style={{ background: 'rgba(255,0,0,0.06)', border: '1px solid rgba(255,0,0,0.18)', color: 'var(--accent-red)' }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPendingAction({ type: 'reject', index: i, draft });
                                    }}
                                  ><XCircle size={10} />{t('social.rejectDraft')}</button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
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
                <div className="flex flex-col gap-1.5 py-2">
                  <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('social.noTopics')}</span>
                  <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-disabled)' }}>
                    {t('social.noTopicsHint')}
                  </span>
                </div>
              )}
              {topics.slice(0, 6).map((topic, i) => (
                <div key={topic.id ?? i} className="flex items-center gap-3 px-3 py-2 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}>
                  <span className="font-mono text-[10px] w-4 text-center flex-shrink-0"
                    style={{ color: i < 3 ? 'var(--accent-red)' : 'var(--text-disabled)' }}>
                    {i + 1}
                  </span>
                  <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                    {topic.name || topic.title || '(无标题)'}
                  </span>
                  {topic.platform && (
                    <span className="font-mono text-[9px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {topic.platform}
                    </span>
                  )}
                  <HeatBar value={topic.heat ?? topic.score ?? 0} />
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
      <ConfirmDialog
        open={Boolean(pendingAction)}
        onClose={() => !actionLoading && setPendingAction(null)}
        onConfirm={handleConfirmAction}
        title={pendingAction?.type === 'publish' ? t('social.confirmPublishTitle') : pendingAction?.type === 'reject' ? t('social.confirmRejectTitle') : t('social.confirmApproveTitle')}
        description={pendingAction ? `${t('social.confirmDraftDesc')}\n\n${draftText(pendingAction.draft).slice(0, 180)}` : ''}
        confirmText={pendingAction?.type === 'publish' ? t('social.publishDraft') : pendingAction?.type === 'reject' ? t('social.rejectDraft') : t('social.approveDraft')}
        destructive={pendingAction?.type === 'reject'}
        loading={actionLoading}
      />
    </div>
  );
}

/* ====== 子组件 ====== */

type CopilotCardProps = { icon: React.ElementType; title: string; value: string; detail: string; accent: string };

/** 运营驾驶舱状态卡 */
function CopilotCard({ icon: Icon, title, value, detail, accent }: CopilotCardProps) {
  return (
    <div className="p-4 rounded-2xl" style={{ background: 'var(--bg-base)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} style={{ color: accent }} />
        <span className="text-label" style={{ color: accent }}>{title}</span>
      </div>
      <div className="font-display text-sm font-bold mb-1" style={{ color: 'var(--text-primary)' }}>{value}</div>
      <p className="font-mono text-[10px] leading-relaxed line-clamp-2" style={{ color: 'var(--text-tertiary)' }}>{detail}</p>
    </div>
  );
}

type PlatformWorkspaceCardProps = {
  icon: React.ElementType;
  title: string;
  subtitle: string;
  status: string;
  metric: string;
  detail: string;
  strategyLabel?: string;
  strategyPreset?: string;
  growthLoop?: string;
  strategyLabelText?: string;
  growthLoopLabel?: string;
  accent: string;
  ready: boolean;
  action: string;
  openAction?: string;
  loginAction?: string;
  openLoading?: boolean;
  loginLoading?: boolean;
  nextStep?: string;
  samplePreview?: string;
  nextStepLabel?: string;
  samplePreviewLabel?: string;
  onOpen?: () => void;
  onLogin?: () => void;
  onAction: () => void;
};

/** 统一浏览器运营平台卡 */
function PlatformWorkspaceCard({
  icon: Icon,
  title,
  subtitle,
  status,
  metric,
  detail,
  strategyLabel,
  strategyPreset,
  growthLoop,
  strategyLabelText = 'Strategy',
  growthLoopLabel = 'Growth loop',
  accent,
  ready,
  action,
  openAction,
  loginAction,
  openLoading,
  loginLoading,
  nextStep,
  samplePreview,
  nextStepLabel = 'Next',
  samplePreviewLabel = 'Sample',
  onOpen,
  onLogin,
  onAction,
}: PlatformWorkspaceCardProps) {
  return (
    <div className="p-4 rounded-2xl" style={{ background: 'var(--bg-base)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <Icon size={16} style={{ color: accent }} />
          </div>
          <div className="min-w-0">
            <div className="font-display text-sm font-bold truncate" style={{ color: 'var(--text-primary)' }}>{title}</div>
            <div className="font-mono text-[9px] truncate" style={{ color: 'var(--text-disabled)' }}>{subtitle}</div>
          </div>
        </div>
        <span className="font-mono text-[9px] px-2 py-0.5 rounded-full flex-shrink-0" style={{
          color: ready ? 'var(--accent-green)' : 'var(--accent-amber)',
          background: ready ? 'rgba(0,255,170,0.08)' : 'rgba(255,170,0,0.08)',
        }}>{status}</span>
      </div>
      <div className="flex items-center gap-2 mb-2">
        <MessageSquare size={12} style={{ color: accent }} />
        <span className="font-mono text-[11px] font-bold" style={{ color: accent }}>{metric}</span>
      </div>
      <p className="font-mono text-[10px] leading-relaxed min-h-[34px]" style={{ color: 'var(--text-tertiary)' }}>{detail}</p>
      {(strategyLabel || growthLoop) && (
        <div className="mt-3 rounded-xl px-3 py-2" style={{ background: 'rgba(155,93,229,0.055)', border: '1px solid rgba(155,93,229,0.14)' }}>
          {strategyLabel && (
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="font-mono text-[8px] uppercase tracking-wider" style={{ color: 'var(--accent-purple)' }}>{strategyLabelText}</span>
              <span className="font-mono text-[9px] text-right" style={{ color: 'var(--text-primary)' }}>{strategyLabel}</span>
            </div>
          )}
          {growthLoop && (
            <span className="font-mono text-[10px] leading-relaxed line-clamp-2 block" style={{ color: 'var(--text-secondary)' }}>
              {growthLoopLabel}: {growthLoop}
            </span>
          )}
          {strategyPreset && (
            <span className="font-mono text-[8px] mt-1 block" style={{ color: 'var(--text-disabled)' }}>{strategyPreset}</span>
          )}
        </div>
      )}
      {samplePreview && (
        <div className="mt-3 rounded-xl px-3 py-2" style={{ background: 'rgba(0,212,255,0.035)', border: '1px solid rgba(0,212,255,0.1)' }}>
          <span className="font-mono text-[8px] uppercase tracking-wider block mb-1" style={{ color: 'var(--accent-cyan)' }}>
            {samplePreviewLabel}
          </span>
          <span className="font-mono text-[10px] leading-relaxed line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
            {samplePreview}
          </span>
        </div>
      )}
      {nextStep && (
        <div className="mt-3 flex items-start gap-2 rounded-xl px-3 py-2" style={{ background: 'rgba(255,170,0,0.055)', border: '1px solid rgba(255,170,0,0.12)' }}>
          <MousePointerClick size={11} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent-amber)' }} />
          <div className="min-w-0">
            <span className="font-mono text-[8px] uppercase tracking-wider block" style={{ color: 'var(--accent-amber)' }}>{nextStepLabel}</span>
            <span className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{nextStep}</span>
          </div>
        </div>
      )}
      <div className="mt-3 grid grid-cols-1 gap-2">
        {(onOpen || onLogin) && (
          <div className="grid grid-cols-2 gap-2">
            {onOpen && openAction && (
              <button
                className="px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                style={{ background: 'rgba(0,212,255,0.07)', border: '1px solid rgba(0,212,255,0.16)', color: 'var(--accent-cyan)', opacity: openLoading ? 0.55 : 1 }}
                onClick={onOpen}
                disabled={openLoading}
              >
                {openLoading ? <Loader2 size={11} className="animate-spin" /> : <MousePointerClick size={11} />}
                {openAction}
              </button>
            )}
            {onLogin && loginAction && (
              <button
                className="px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
                style={{ background: 'rgba(255,170,0,0.08)', border: '1px solid rgba(255,170,0,0.18)', color: 'var(--accent-amber)', opacity: loginLoading ? 0.55 : 1 }}
                onClick={onLogin}
                disabled={loginLoading}
              >
                {loginLoading ? <Loader2 size={11} className="animate-spin" /> : <ExternalLink size={11} />}
                {loginAction}
              </button>
            )}
          </div>
        )}
        <button
          className="w-full px-3 py-2 rounded-xl font-mono text-[10px] font-bold cursor-pointer inline-flex items-center justify-center gap-1.5"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', color: 'var(--text-secondary)' }}
          onClick={onAction}
        >
          {action}
          <ExternalLink size={11} />
        </button>
      </div>
    </div>
  );
}

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

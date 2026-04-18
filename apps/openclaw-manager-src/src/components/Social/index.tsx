import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Share2, Flame, FileText, User, CalendarDays, Rocket,
  BarChart3, Newspaper, Play, Loader2, CheckCircle2,
  XCircle, Globe, Send, Plus, Trash2
} from 'lucide-react';
import clsx from 'clsx';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from '@/components/ui/badge';
import { PromptDialog } from '@/components/ui/prompt-dialog';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { format } from 'date-fns';
import { api, isTauri, clawbotFetch } from '@/lib/tauri';
import { createLogger } from '@/lib/logger';
import { toast } from 'sonner';

interface ActionStatus {
  running: boolean;
  lastResult?: string;
  error?: string;
}

const actions = [
  { id: 'hot', label: '热点追踪', desc: '抓取当前热点话题分析', icon: Flame, cmd: '/hot', hasInput: true, placeholder: '关键词' },
  { id: 'post_social', label: '多渠道分发', desc: '自动适配排版，同步推送至全网', icon: Share2, cmd: '/post_social', hasInput: true, placeholder: '发布内容' },
  { id: 'social_plan', label: '营销日历', desc: '根据人设生成本周内容矩阵排期', icon: CalendarDays, cmd: '/social_plan' },
  { id: 'topic', label: '深度研报', desc: '全网抓取并生成长篇图文素材', icon: Newspaper, cmd: '/topic', hasInput: true, placeholder: '研究主题' },
  { id: 'social_persona', label: '人设微调', desc: '调整 AI 在各大平台的发言风格', icon: User, cmd: '/social_persona' },
  { id: 'social_report', label: '数据大盘', desc: '各大平台曝光、转评赞数据分析', icon: BarChart3, cmd: '/social_report' },
  { id: 'autopilot', label: '全托管运营', desc: '开启无人值守模式 (Auto-pilot)', icon: Rocket, cmd: '/autopilot', confirm: true },
];

interface Draft {
  id: number;
  title: string;
  platforms: string[];
  status: string;
  time: Date;
}

/** 后端返回的草稿原始结构 */
interface BackendDraft {
  text?: string;
  platform?: string;
  status?: string;
  created_at?: string;
  topic?: string;
  [key: string]: unknown;
}

/** 将后端草稿数据映射为前端 Draft 结构 */
function mapBackendDraft(raw: BackendDraft, index: number): Draft {
  return {
    id: index,
    title: raw.text || raw.topic || '无标题',
    platforms: raw.platform ? [raw.platform] : ['x'],
    status: raw.status || 'draft',
    time: raw.created_at ? new Date(raw.created_at) : new Date(),
  };
}

/** 后端草稿 API 返回值类型 */
interface DraftApiResult {
  success?: boolean;
  error?: string;
  drafts?: BackendDraft[];
}

// ──── 草稿 API 封装（同时支持 Tauri IPC 和 HTTP 降级） ────

/** 从后端获取所有草稿 */
async function apiFetchDrafts(): Promise<Draft[]> {
  let data: DraftApiResult;
  if (isTauri()) {
    data = await api.clawbotSocialDrafts() as DraftApiResult;
  } else {
    const resp = await clawbotFetch('/api/v1/social/drafts');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  }
  return (data?.drafts || []).map(mapBackendDraft);
}

/** 更新指定草稿的文本内容 */
async function apiUpdateDraft(index: number, text: string): Promise<void> {
  let result: DraftApiResult;
  if (isTauri()) {
    result = await api.clawbotSocialDraftUpdate(index, text) as DraftApiResult;
  } else {
    const resp = await clawbotFetch(
      `/api/v1/social/drafts/${index}?text=${encodeURIComponent(text)}`,
      { method: 'PATCH' },
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    result = await resp.json();
  }
  if (!result?.success) throw new Error(result?.error || '更新失败');
}

/** 删除指定草稿 */
async function apiDeleteDraft(index: number): Promise<void> {
  let result: DraftApiResult;
  if (isTauri()) {
    result = await api.clawbotSocialDraftDelete(index) as DraftApiResult;
  } else {
    const resp = await clawbotFetch(`/api/v1/social/drafts/${index}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    result = await resp.json();
  }
  if (!result?.success) throw new Error(result?.error || '删除失败');
}

/** 发布指定草稿 */
async function apiPublishDraft(index: number): Promise<void> {
  let result: DraftApiResult;
  if (isTauri()) {
    result = await api.clawbotSocialDraftPublish(index) as DraftApiResult;
  } else {
    const resp = await clawbotFetch(`/api/v1/social/drafts/${index}/publish`, { method: 'POST' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    result = await resp.json();
  }
  if (!result?.success) throw new Error(result?.error || '发布失败');
}

/** 平台互动数据 */
interface PlatformEngagement {
  total_likes?: number;
  total_comments?: number;
  total_shares?: number;
}

/** 热门帖子 */
interface TopPost {
  preview?: string;
  title?: string;
  likes?: number;
  comments?: number;
  shares?: number;
}

/** 数据分析面板返回结构 */
interface AnalyticsData {
  engagement?: Record<string, PlatformEngagement>;
  follower_growth?: Record<string, { current?: number; net_change?: number }>;
  top_posts?: TopPost[];
}

/** 社媒控制面板状态 */
interface SocialControlsState {
  xhs_enabled: boolean;          // 小红书发布开关
  x_twitter_enabled: boolean;    // X/Twitter 发布开关
  auto_hotspot_post: boolean;    // 自动热点跟帖
  content_review_mode: boolean;  // 发布前人工审核
  scheduler_paused: boolean;     // 暂停定时任务
}

const socialLogger = createLogger('Social');

/** 数据分析面板 — 展示粉丝增长、互动数据、热门帖子 */
function AnalyticsPanel() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const resp = await clawbotFetch('/api/v1/social/analytics?days=7');
        if (resp.ok) {
          setData(await resp.json());
        }
      } catch (e) {
        socialLogger.error('获取社媒分析数据失败', e);
        setAnalyticsError('社媒分析数据获取失败');
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1,2,3,4].map(i => (
          <Card key={i} className="bg-dark-800 border-dark-600 animate-pulse">
            <CardContent className="p-5">
              <div className="h-4 bg-dark-700 rounded w-1/2 mb-3" />
              <div className="h-8 bg-dark-700 rounded w-1/3" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (analyticsError) {
    return (
      <div className="flex items-center justify-center h-40 text-red-400 flex-col gap-3 border border-red-500/20 border-dashed rounded-xl bg-red-500/5">
        <XCircle size={36} className="text-red-500/50" />
        <p>{analyticsError}</p>
      </div>
    );
  }

  // 从后端数据中提取统计信息，设置安全默认值
  const engagement = data?.engagement || {};
  const growth = data?.follower_growth || {};
  const xFollowers = growth?.x?.current || 0;
  const xGrowth = growth?.x?.net_change || 0;
  const totalLikes = Object.values(engagement).reduce((sum: number, p: PlatformEngagement) => sum + (p?.total_likes || 0), 0);
  const totalComments = Object.values(engagement).reduce((sum: number, p: PlatformEngagement) => sum + (p?.total_comments || 0), 0);
  const totalShares = Object.values(engagement).reduce((sum: number, p: PlatformEngagement) => sum + (p?.total_shares || 0), 0);
  const topPosts = data?.top_posts || [];

  return (
    <div className="space-y-6">
      {/* 概览卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-dark-800 border-dark-600">
          <CardContent className="p-5">
            <div className="text-xs text-gray-500 mb-1">𝕏 粉丝数</div>
            <div className="text-2xl font-bold text-white">{xFollowers.toLocaleString()}</div>
            <div className={clsx("text-xs mt-1", xGrowth >= 0 ? "text-green-400" : "text-red-400")}>
              {xGrowth >= 0 ? '+' : ''}{xGrowth} (7天)
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-600">
          <CardContent className="p-5">
            <div className="text-xs text-gray-500 mb-1">总互动量</div>
            <div className="text-2xl font-bold text-white">{(totalLikes + totalComments + totalShares).toLocaleString()}</div>
            <div className="text-xs text-gray-500 mt-1">赞 {totalLikes} · 评 {totalComments} · 转 {totalShares}</div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-600">
          <CardContent className="p-5">
            <div className="text-xs text-gray-500 mb-1">小红书</div>
            <div className="text-2xl font-bold text-white">{growth?.xhs?.current || '—'}</div>
            <div className="text-xs text-amber-400 mt-1">需登录创作者后台同步</div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-600">
          <CardContent className="p-5">
            <div className="text-xs text-gray-500 mb-1">Top 帖子</div>
            <div className="text-2xl font-bold text-white">{topPosts.length}</div>
            <div className="text-xs text-gray-500 mt-1">近7天有互动的帖子</div>
          </CardContent>
        </Card>
      </div>

      {/* 热门帖子排行 */}
      {topPosts.length > 0 ? (
        <Card className="bg-dark-800 border-dark-600">
          <CardHeader className="pb-3 border-b border-dark-700">
            <CardTitle className="text-sm text-gray-300 flex items-center gap-2">
              <BarChart3 size={16} className="text-blue-400" />
              热门内容排行
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-dark-700">
              {topPosts.slice(0, 5).map((post: TopPost, i: number) => (
                <div key={i} className="px-5 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-600 font-mono w-5">#{i+1}</span>
                    <span className="text-sm text-gray-200 truncate max-w-[300px]">{post.preview || post.title || '无标题'}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span>❤️ {post.likes || 0}</span>
                    <span>💬 {post.comments || 0}</span>
                    <span>🔁 {post.shares || 0}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="flex items-center justify-center h-40 text-gray-500 flex-col gap-3 border border-dark-600 border-dashed rounded-xl bg-dark-900/50">
          <BarChart3 size={36} className="text-dark-600" />
          <p>暂无发布数据 — 发布内容后自动统计互动效果</p>
        </div>
      )}
    </div>
  );
}

export function Social() {
  const [statuses, setStatuses] = useState<Record<string, ActionStatus>>({});
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draftsLoading, setDraftsLoading] = useState(true);
  const [newDraftDialogOpen, setNewDraftDialogOpen] = useState(false);
  const [editDraftTarget, setEditDraftTarget] = useState<Draft | null>(null);
  const [operatingDraftId, setOperatingDraftId] = useState<number | null>(null);
  const [browserStatus, setBrowserStatus] = useState({ x: 'unknown', xhs: 'unknown' });
  // Autopilot 确认弹窗状态（替代 window.confirm）
  const [autopilotConfirm, setAutopilotConfirm] = useState<{ id: string; cmd: string; hasInput?: boolean } | null>(null);

  // ──── 社媒控制面板状态 ────
  const [socialControls, setSocialControls] = useState<SocialControlsState>({
    xhs_enabled: true,
    x_twitter_enabled: true,
    auto_hotspot_post: false,
    content_review_mode: true,
    scheduler_paused: false,
  });

  // 组件挂载时从后端拉取社媒控制状态
  useEffect(() => {
    const fetchControls = async () => {
      try {
        const resp = await clawbotFetch('/api/v1/controls/social');
        if (resp.ok) {
          const data = await resp.json();
          setSocialControls(data);
        }
      } catch { /* 静默失败，使用默认值 */ }
    };
    fetchControls();
  }, []);

  // 切换社媒控制开关并同步到后端
  const handleSocialToggle = async (key: keyof SocialControlsState, value: boolean) => {
    const updated = { ...socialControls, [key]: value };
    setSocialControls(updated);
    try {
      await clawbotFetch('/api/v1/controls/social', {
        method: 'POST',
        body: JSON.stringify(updated),
      });
    } catch (e) {
      socialLogger.warn('更新社媒控制失败', e);
    }
  };

  // 从后端加载草稿列表
  const loadDrafts = useCallback(async () => {
    try {
      setDraftsLoading(true);
      const result = await apiFetchDrafts();
      setDrafts(result);
    } catch (e) {
      socialLogger.error('加载草稿列表失败', e);
      toast.error('草稿列表加载失败');
    } finally {
      setDraftsLoading(false);
    }
  }, []);

  // 组件挂载时从后端拉取草稿
  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  // 获取浏览器会话状态
  useEffect(() => {
    const fetchBrowserStatus = async () => {
      try {
        if (isTauri()) {
          // Tauri 环境：通过 IPC 调用
          const data = await api.clawbotSocialBrowserStatus();
          setBrowserStatus({
            x: data?.x || 'unknown',
            xhs: data?.xhs || 'unknown',
          });
        } else {
          // 降级: 直接HTTP调用
          const resp = await clawbotFetch('/api/v1/social/browser-status');
          if (resp.ok) {
            const data = await resp.json();
            setBrowserStatus({
              x: data.x || data.twitter || 'unknown',
              xhs: data.xhs || data.xiaohongshu || 'unknown',
            });
          }
        }
      } catch (e) {
        socialLogger.warn('获取浏览器会话状态失败，保持离线状态', e);
      }
    };
    fetchBrowserStatus();
    const interval = setInterval(fetchBrowserStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (id: string, cmd: string, hasInput?: boolean) => {
    const input = inputs[id];
    if (hasInput && !input) return;

    // 检查是否需要用户确认（如全托管运营模式）
    const action = actions.find(a => a.id === id);
    if (action?.confirm) {
      // 打开自定义确认弹窗，暂存操作参数
      setAutopilotConfirm({ id, cmd, hasInput });
      return;
    }

    await executeAction(id, cmd, hasInput);
  };

  /** 实际执行操作（确认后调用） */
  const executeAction = async (id: string, cmd: string, _hasInput?: boolean) => {
    const input = inputs[id];
    setStatuses(prev => ({ ...prev, [id]: { running: true } }));

    try {
      const text = `${cmd} ${input || ''}`.trim();
      let result: string;

      if (isTauri()) {
        // Tauri 环境：通过 IPC 调用
        const data = await api.omegaProcess(text);
        result = data?.result || data?.response || '执行完成';
      } else {
        // 降级: 直接HTTP调用
        const resp = await clawbotFetch('/api/v1/omega/process', {
          method: 'POST',
          body: JSON.stringify({ text }),
        });
        const data = await resp.json();
        result = data.result || data.response || '执行完成';
      }

      setStatuses(prev => ({
        ...prev,
        [id]: { running: false, lastResult: result }
      }));
    } catch (e) {
      setStatuses(prev => ({
        ...prev,
        [id]: { running: false, lastResult: `执行失败: ${e instanceof Error ? e.message : '服务不可达'}` }
      }));
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === 'ready') return <CheckCircle2 className="text-green-500 w-4 h-4" />;
    if (status === 'login_needed') return <XCircle className="text-amber-500 w-4 h-4" />;
    return <Globe className="text-gray-500 w-4 h-4" />;
  };

  const getStatusText = (status: string) => {
    if (status === 'ready') return <span className="text-green-500 font-medium">会话活跃</span>;
    if (status === 'login_needed') return <span className="text-amber-500 font-medium">需要登录</span>;
    return <span className="text-gray-500 font-medium">离线</span>;
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-dark-800/40 p-5 rounded-2xl border border-dark-600/50 backdrop-blur-sm">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Share2 className="text-blue-400 h-6 w-6" />
              社媒与内容中枢
            </h2>
            <p className="text-gray-400 text-sm mt-1">跨平台矩阵分发、自动化互动与多模态内容生成</p>
          </div>
          
          <div className="flex gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-900 border border-dark-700 shadow-inner">
              <span className="text-xl font-bold">𝕏</span>
              <div className="w-px h-4 bg-dark-600 mx-1"></div>
              {getStatusIcon(browserStatus.x)}
              <span className="text-xs uppercase tracking-wider">{getStatusText(browserStatus.x)}</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-900 border border-dark-700 shadow-inner">
              <span className="text-red-500 font-bold">小红书</span>
              <div className="w-px h-4 bg-dark-600 mx-1"></div>
              {getStatusIcon(browserStatus.xhs)}
              <span className="text-xs uppercase tracking-wider">{getStatusText(browserStatus.xhs)}</span>
            </div>
          </div>
        </div>

        {/* 社媒控制面板 */}
        <div className="flex flex-wrap items-center gap-4 bg-dark-800/40 px-4 py-3 rounded-xl border border-dark-600/50">
          <span className="text-xs text-gray-500 font-medium mr-1">平台开关</span>

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch
              checked={socialControls.xhs_enabled}
              onCheckedChange={(v) => handleSocialToggle('xhs_enabled', v)}
            />
            <span className="text-sm text-gray-300">小红书</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch
              checked={socialControls.x_twitter_enabled}
              onCheckedChange={(v) => handleSocialToggle('x_twitter_enabled', v)}
            />
            <span className="text-sm text-gray-300">X / Twitter</span>
          </label>

          <div className="w-px h-5 bg-dark-600 mx-1" />

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch
              checked={socialControls.auto_hotspot_post}
              onCheckedChange={(v) => handleSocialToggle('auto_hotspot_post', v)}
            />
            <span className="text-sm text-gray-300">自动蹭热点</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch
              checked={socialControls.content_review_mode}
              onCheckedChange={(v) => handleSocialToggle('content_review_mode', v)}
            />
            <span className="text-sm text-gray-300">发前审核</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch
              checked={socialControls.scheduler_paused}
              onCheckedChange={(v) => handleSocialToggle('scheduler_paused', v)}
            />
            <span className={clsx("text-sm", socialControls.scheduler_paused ? "text-yellow-400" : "text-gray-300")}>
              {socialControls.scheduler_paused ? '定时已暂停' : '定时运行中'}
            </span>
          </label>
        </div>

        <Tabs defaultValue="actions" className="w-full">
          <TabsList className="bg-dark-800 border border-dark-700 mb-6 p-1 rounded-xl">
            <TabsTrigger value="actions" className="rounded-lg data-[state=active]:bg-dark-600 data-[state=active]:text-white">控制面板</TabsTrigger>
            <TabsTrigger value="content" className="rounded-lg data-[state=active]:bg-dark-600 data-[state=active]:text-white">素材与草稿箱</TabsTrigger>
            <TabsTrigger value="analytics" className="rounded-lg data-[state=active]:bg-dark-600 data-[state=active]:text-white">效果追踪</TabsTrigger>
          </TabsList>

          <TabsContent value="actions" className="mt-0">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {actions.map((action) => {
                const status = statuses[action.id];
                const isRunning = status?.running;
                
                return (
                  <Card key={action.id} className="bg-dark-800/80 border-dark-600 shadow-md hover:border-blue-500/50 transition-all overflow-hidden group">
                    <div className="p-5">
                      <div className="flex items-start justify-between mb-4">
                        <div className="w-10 h-10 rounded-xl bg-dark-700 border border-dark-600 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <action.icon size={20} className="text-blue-400" />
                        </div>
                        <button
                          onClick={() => handleAction(action.id, action.cmd, action.hasInput)}
                          disabled={isRunning || (action.hasInput && !inputs[action.id])}
                          className={clsx(
                            "w-8 h-8 rounded-full flex items-center justify-center transition-colors",
                            isRunning ? "bg-dark-600" : "bg-blue-500/10 text-blue-400 hover:bg-blue-500 hover:text-white"
                          )}
                          aria-label={`执行${action.label}`}
                        >
                          {isRunning ? <Loader2 size={16} className="animate-spin text-gray-400" /> : <Play size={14} className="ml-0.5" />}
                        </button>
                      </div>
                      
                      <h3 className="font-bold text-white mb-1">{action.label}</h3>
                      <p className="text-xs text-gray-400 mb-4 h-8 line-clamp-2">{action.desc}</p>
                      
                      {action.hasInput ? (
                        <input
                          type="text"
                          placeholder={action.placeholder}
                          value={inputs[action.id] || ''}
                          onChange={(e) => setInputs(prev => ({ ...prev, [action.id]: e.target.value }))}
                          onKeyDown={(e) => e.key === 'Enter' && handleAction(action.id, action.cmd, true)}
                          className="w-full bg-dark-900 border border-dark-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-dark-400"
                          aria-label={action.label}
                        />
                      ) : (
                        <div className="h-[38px] flex items-center">
                          <code className="text-[10px] bg-dark-900 px-2 py-1 rounded text-gray-500 border border-dark-700 font-mono">
                            {action.cmd}
                          </code>
                        </div>
                      )}

                      <AnimatePresence>
                        {status?.lastResult && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="mt-3 pt-3 border-t border-dark-700"
                          >
                            <p className={clsx(
                              "text-xs font-mono break-words p-2 rounded border",
                              status.lastResult.startsWith('执行失败')
                                ? "text-red-400 bg-red-500/10 border-red-500/20"
                                : "text-green-400 bg-green-500/10 border-green-500/20"
                            )}>
                              {status.lastResult}
                            </p>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="content" className="mt-0">
            <Card className="bg-dark-900 border-dark-600 shadow-xl overflow-hidden">
              <CardHeader className="border-b border-dark-700/50 pb-4 bg-dark-800/30">
                <div className="flex justify-between items-center">
                  <div>
                    <CardTitle className="text-lg font-bold text-white flex items-center gap-2">
                      <FileText className="text-blue-400 h-5 w-5" />
                      待发布队列与草稿
                    </CardTitle>
                  </div>
                  <button onClick={() => setNewDraftDialogOpen(true)} className="btn-primary text-sm py-2 px-4 flex items-center gap-2">
                    <Plus size={14} /> 新建内容
                  </button>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y divide-dark-700/50">
                  {draftsLoading ? (
                    /* 加载中骨架屏 */
                    <div className="space-y-0 divide-y divide-dark-700/50">
                      {[1, 2, 3].map(i => (
                        <div key={i} className="p-5 flex items-center gap-4 animate-pulse">
                          <div className="w-10 h-10 rounded-lg bg-dark-700 shrink-0" />
                          <div className="flex-1 space-y-2">
                            <div className="h-4 bg-dark-700 rounded w-1/3" />
                            <div className="h-3 bg-dark-700 rounded w-1/5" />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : drafts.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-gray-500 gap-3">
                      <FileText size={40} className="text-dark-600" />
                      <p>暂无草稿，点击「新建内容」或通过命令生成</p>
                    </div>
                  ) : drafts.map(draft => (
                    <div key={draft.id} className="p-5 flex items-center justify-between hover:bg-dark-800/30 transition-colors group">
                      <div className="flex items-start gap-4">
                        <div className={clsx(
                          "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                          draft.status === 'draft' ? "bg-dark-700 text-gray-400" :
                          draft.status === 'scheduled' ? "bg-blue-500/20 text-blue-400" :
                          "bg-green-500/20 text-green-400"
                        )}>
                          {draft.status === 'draft' ? <FileText size={20} /> :
                           draft.status === 'scheduled' ? <CalendarDays size={20} /> :
                           <Send size={20} />}
                        </div>
                        <div>
                          <h4 className="text-white font-medium mb-1">{draft.title}</h4>
                          <div className="flex items-center gap-3 text-xs">
                            <div className="flex gap-1.5">
                              {draft.platforms.map(p => (
                                <Badge key={p} variant="outline" className="bg-dark-800 border-dark-600 text-gray-300 py-0 uppercase">
                                  {p}
                                </Badge>
                              ))}
                            </div>
                            <span className="text-gray-500 flex items-center gap-1">
                              <CalendarDays size={12} /> {format(draft.time, 'MM-dd HH:mm')}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => setEditDraftTarget(draft)} className="p-2 hover:bg-dark-700 rounded-md text-gray-400 hover:text-white transition-colors">
                          编辑
                        </button>
                        {/* 删除按钮 — 防重复点击 */}
                        <button disabled={operatingDraftId === draft.id} onClick={async () => {
                          setOperatingDraftId(draft.id);
                          try {
                            await apiDeleteDraft(draft.id);
                            toast.success('草稿已删除');
                            // 删除后重新加载列表（因后端按索引管理，需刷新全部索引）
                            await loadDrafts();
                          } catch (e) {
                            socialLogger.error('删除草稿失败', e);
                            toast.error('删除草稿失败');
                          } finally {
                            setOperatingDraftId(null);
                          }
                        }} className="p-2 hover:bg-red-500/20 rounded-md text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                          <Trash2 size={14} />
                        </button>
                        {draft.status !== 'published' && (
                          <button disabled={operatingDraftId === draft.id} onClick={async () => {
                            setOperatingDraftId(draft.id);
                            // 乐观更新：先把状态改成 published
                            setDrafts(prev => prev.map(d => d.id === draft.id ? { ...d, status: 'published' } : d));
                            try {
                              await apiPublishDraft(draft.id);
                              toast.success('草稿已发布');
                              // 发布成功后刷新列表
                              await loadDrafts();
                            } catch (e) {
                              // 发布失败时回滚状态
                              setDrafts(prev => prev.map(d => d.id === draft.id ? { ...d, status: 'draft' } : d));
                              socialLogger.error('发布草稿失败', e);
                              toast.error('发布草稿失败');
                            } finally {
                              setOperatingDraftId(null);
                            }
                          }} className="p-2 hover:bg-blue-500/20 rounded-md text-blue-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                            立即发布
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="analytics" className="mt-0">
            <AnalyticsPanel />
          </TabsContent>

        </Tabs>
      </div>

      {/* 新建内容对话框 */}
      <PromptDialog
        open={newDraftDialogOpen}
        onClose={() => setNewDraftDialogOpen(false)}
        onConfirm={async (title) => {
          setNewDraftDialogOpen(false);
          try {
            // 先在后端创建草稿（追加到末尾后用 update 写入文本）
            // 后端的 drafts 由 social_scheduler state 管理，
            // 没有专门的"create"接口，先加载列表取得当前数量后
            // 用 update 把新索引位的内容设为用户输入的标题
            const currentDrafts = await apiFetchDrafts();
            const newIndex = currentDrafts.length;
            await apiUpdateDraft(newIndex, title);
            toast.success('新草稿已创建');
            // 刷新草稿列表
            await loadDrafts();
          } catch (e) {
            socialLogger.error('创建草稿失败', e);
            toast.error('创建草稿失败');
            // 降级：仅前端添加，下次刷新时会消失
            const fallback: Draft = {
              id: Date.now(),
              title,
              platforms: ['x', 'xhs'],
              status: 'draft',
              time: new Date(),
            };
            setDrafts(prev => [...prev, fallback]);
          }
        }}
        title="新建内容"
        placeholder="输入内容标题"
      />

      {/* 编辑草稿标题对话框 */}
      <PromptDialog
        open={editDraftTarget !== null}
        onClose={() => setEditDraftTarget(null)}
        onConfirm={async (newTitle) => {
          if (!editDraftTarget) return;
          const targetId = editDraftTarget.id;
          setEditDraftTarget(null);
          try {
            // 调用后端更新草稿文本
            await apiUpdateDraft(targetId, newTitle);
            toast.success('草稿已更新');
            // 刷新草稿列表以保持与后端同步
            await loadDrafts();
          } catch (e) {
            socialLogger.error('更新草稿失败', e);
            toast.error('更新草稿失败');
            // 降级：仅更新前端状态
            setDrafts(prev => prev.map(d => d.id === targetId ? { ...d, title: newTitle } : d));
          }
        }}
        title="编辑标题"
        defaultValue={editDraftTarget?.title ?? ''}
        placeholder="输入新标题"
      />

      {/* Autopilot 确认弹窗（替代 window.confirm） */}
      <ConfirmDialog
        open={autopilotConfirm !== null}
        onClose={() => setAutopilotConfirm(null)}
        onConfirm={async () => {
          if (autopilotConfirm) {
            const { id, cmd, hasInput } = autopilotConfirm;
            setAutopilotConfirm(null);
            await executeAction(id, cmd, hasInput);
          }
        }}
        title="开启全自动运营"
        description="确认开启全自动运营模式？开启后系统将自动发布内容、回复评论。"
        confirmText="开启"
      />
    </div>
  );
}

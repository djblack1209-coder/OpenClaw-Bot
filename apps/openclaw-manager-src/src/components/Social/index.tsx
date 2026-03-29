import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Share2, Flame, FileText, User, CalendarDays, Rocket,
  BarChart3, Newspaper, Play, Loader2, CheckCircle2,
  XCircle, Globe, Send, Plus
} from 'lucide-react';
import clsx from 'clsx';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from '@/components/ui/badge';
import { format } from 'date-fns';
import { api, isTauri, clawbotFetch } from '@/lib/tauri';

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

/** 数据分析面板 — 展示粉丝增长、互动数据、热门帖子 */
function AnalyticsPanel() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const resp = await clawbotFetch('/api/v1/social/analytics?days=7');
        if (resp.ok) {
          setData(await resp.json());
        }
      } catch {
        // 后端不可达
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
  const [browserStatus, setBrowserStatus] = useState({ x: 'unknown', xhs: 'unknown' });

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
      } catch {
        // 后端不可达时保持 unknown 状态
      }
    };
    fetchBrowserStatus();
    const interval = setInterval(fetchBrowserStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (id: string, cmd: string, hasInput?: boolean) => {
    const input = inputs[id];
    if (hasInput && !input) return;

    setStatuses(prev => ({ ...prev, [id]: { running: true } }));

    try {
      const text = `${cmd} ${input || ''}`.trim();
      let result: string;

      if (isTauri()) {
        // Tauri 环境：通过 IPC 调用
        const data = await api.omegaProcess(text);
        const d = data as Record<string, string>;
        result = d?.result || d?.response || '执行完成';
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
                            <p className="text-xs text-green-400 font-mono break-words bg-green-500/10 p-2 rounded border border-green-500/20">
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
                  <button onClick={() => {
                    const title = prompt('输入内容标题:');
                    if (!title) return;
                    const newDraft: Draft = {
                      id: Date.now(),
                      title,
                      platforms: ['x', 'xhs'],
                      status: 'draft',
                      time: new Date(),
                    };
                    setDrafts(prev => [...prev, newDraft]);
                  }} className="btn-primary text-sm py-2 px-4 flex items-center gap-2">
                    <Plus size={14} /> 新建内容
                  </button>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y divide-dark-700/50">
                  {drafts.length === 0 ? (
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
                        <button onClick={() => {
                          const newTitle = prompt('编辑标题:', draft.title);
                          if (newTitle) {
                            setDrafts(prev => prev.map(d => d.id === draft.id ? { ...d, title: newTitle } : d));
                          }
                        }} className="p-2 hover:bg-dark-700 rounded-md text-gray-400 hover:text-white transition-colors">
                          编辑
                        </button>
                        {draft.status !== 'published' && (
                          <button onClick={async () => {
                            setDrafts(prev => prev.map(d => d.id === draft.id ? { ...d, status: 'published' } : d));
                            try {
                              if (isTauri()) {
                                // Tauri 环境：通过 IPC 调用
                                await api.omegaProcess(`/post_social ${draft.title}`);
                              } else {
                                // 降级: 直接HTTP调用
                                await clawbotFetch('/api/v1/omega/process', {
                                  method: 'POST',
                                  body: JSON.stringify({ text: `/post_social ${draft.title}` }),
                                });
                              }
                            } catch {
                              // 发布失败时回滚状态
                              setDrafts(prev => prev.map(d => d.id === draft.id ? { ...d, status: 'draft' } : d));
                            }
                          }} className="p-2 hover:bg-blue-500/20 rounded-md text-blue-400 transition-colors">
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
    </div>
  );
}

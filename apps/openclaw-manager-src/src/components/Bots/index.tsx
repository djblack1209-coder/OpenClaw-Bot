import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { toast } from 'sonner';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  Fish,
  Smartphone,
  Bot,
  Globe,
  Cpu,
  Server,
  Bell,
  AlertCircle,
  DollarSign,
  Info,
  Calendar,
  Send,
  Settings,
  Pause,
  Play,
  QrCode,
  RefreshCw,
  CheckCircle2,
  Loader2,
  TrendingUp,
  BarChart3,
  Users,
  Clock,
  MessageCircle,
  ChevronRight,
  Eye,
  FileText,
  Activity,
  Terminal,
  Hash,
  Zap,
} from 'lucide-react';

import { GlassCard, StatusIndicator, ToggleSwitch, AnimatedNumber, ErrorState } from '../shared';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { api, clawbotFetch } from '@/lib/tauri';
import { useClawbotWS } from '@/hooks/useClawbotWS';
import { toFriendlyError } from '@/lib/errorMessages';
import { createLogger } from '@/lib/logger';
import type { FriendlyError } from '@/lib/errorMessages';
import type { ManagedServiceStatus, ClawbotBotMatrixEntry } from '@/lib/tauri';

const logger = createLogger('Bots');

/**
 * 我的机器人 —— 自动化控制中心
 * 
 * 四大板块：
 * 1. 闲鱼 AI 客服
 * 2. 社媒自动驾驶
 * 3. 自动化脚本网格
 * 4. 通知中心
 */
export function Bots() {
  return (
    <div className="h-full overflow-y-auto px-6 py-6 space-y-6">
      {/* 闲鱼 AI 客服 */}
      <XianyuSection />
      
      {/* 社媒自动驾驶 */}
      <SocialSection />
      
      {/* 自动化脚本网格 */}
      <ServicesSection />
      
      {/* 通知中心 */}
      <NotificationSection />
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Section 1: 闲鱼 AI 客服
──────────────────────────────────────────────────────────────── */

interface XianyuConversation {
  id: string;
  buyer_name: string;
  last_message: string;
  timestamp: string;
  unread_count: number;
  item_title?: string;
}

interface XianyuStatus {
  online: boolean;
  today_conversations?: number;
  auto_deals?: number;
  pending_deals?: number;
}

function XianyuSection() {
  const [status, setStatus] = useState<XianyuStatus>({ online: false });
  const [loading, setLoading] = useState(true);
  const [qrDialogOpen, setQrDialogOpen] = useState(false);

  // ── QR Login state ──
  type QRState = 'idle' | 'loading' | 'waiting' | 'scanned' | 'confirmed' | 'expired' | 'error';
  const [qrState, setQrState] = useState<QRState>('idle');
  const [qrImage, setQrImage] = useState<string>('');
  const [countdown, setCountdown] = useState(60);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 清理轮询和倒计时
  const cleanupQR = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
  }, []);

  // 生成二维码
  const generateQR = useCallback(async () => {
    cleanupQR();
    setQrState('loading');
    setQrImage('');
    setCountdown(60);

    try {
      const data = await api.xianyuGenerateQR();
      if (!data?.qr_image) {
        setQrState('error');
        return;
      }

      setQrImage(data.qr_image);
      setQrState('waiting');

      // 开始 60 秒倒计时
      countdownRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            cleanupQR();
            setQrState('expired');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // 每 2 秒轮询扫码状态
      pollRef.current = setInterval(async () => {
        try {
          const statusData = await api.xianyuQRStatus();
          const s = statusData?.status;

          if (s === 'scanned') {
            setQrState('scanned');
          } else if (s === 'confirmed') {
            cleanupQR();
            setQrState('confirmed');
            toast.success('闲鱼扫码登录成功');
            setTimeout(() => {
              setQrDialogOpen(false);
              setQrState('idle');
            }, 1500);
          } else if (s === 'expired') {
            cleanupQR();
            setQrState('expired');
          }
        } catch {
          // 轮询失败时静默忽略，等待下一次
        }
      }, 2000);
    } catch {
      setQrState('error');
    }
  }, [cleanupQR]);

  // Dialog 打开时生成二维码
  useEffect(() => {
    if (qrDialogOpen) {
      generateQR();
    } else {
      cleanupQR();
      setQrState('idle');
    }
    return cleanupQR;
  }, [qrDialogOpen, generateQR, cleanupQR]);

  // 10秒轮询状态
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await clawbotFetch('/api/v1/status');
        const data = await res.json();
        const xianyuData = data.xianyu || {};
        setStatus({
          online: xianyuData.running ?? xianyuData.online ?? false,
          today_conversations: xianyuData.today_conversations ?? 0,
          auto_deals: xianyuData.auto_deals ?? 0,
          pending_deals: xianyuData.pending_deals ?? 0,
        });
      } catch (err) {
        logger.error('获取闲鱼状态失败:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const timer = setInterval(fetchStatus, 10000);
    return () => clearInterval(timer);
  }, []);

  const handleToggle = async (checked: boolean) => {
    try {
      if (checked) {
        await api.serviceStart('xianyu');
      } else {
        await api.serviceStop('xianyu');
      }
      setStatus((prev) => ({ ...prev, online: checked }));
      toast.success(checked ? '闲鱼客服已启动' : '闲鱼客服已停止');
    } catch (err) {
      toast.error(`${checked ? '启动' : '停止'}闲鱼客服失败`);
      logger.error('Toggle xianyu failed:', err);
    }
  };

  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">闲鱼 AI 客服</h2>
      <GlassCard>
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-orange-500 to-pink-500 flex items-center justify-center">
              <Fish size={24} className="text-white" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">闲鱼 AI 客服</h3>
              <div className="flex items-center gap-3 mt-1">
                <StatusIndicator status={status.online ? 'running' : 'stopped'} />
                <span className="text-xs text-gray-400">
                  今日对话: <AnimatedNumber value={status.today_conversations || 0} decimals={0} className="text-white" />条
                </span>
              </div>
            </div>
          </div>
          <ToggleSwitch checked={status.online} onChange={handleToggle} disabled={loading} />
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400 mb-1">自动成交</div>
            <div className="text-xl font-bold text-white">
              <AnimatedNumber value={status.auto_deals || 0} decimals={0} />单
            </div>
          </div>
          <div className="p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400 mb-1">待确认</div>
            <div className="text-xl font-bold text-white">
              <AnimatedNumber value={status.pending_deals || 0} decimals={0} />单
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => setQrDialogOpen(true)}
          >
            <QrCode size={14} className="mr-1.5" />
            扫码登录/续期
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleToggle(!status.online)}>
            {status.online ? <Pause size={14} className="mr-1.5" /> : <Play size={14} className="mr-1.5" />}
            {status.online ? '暂停' : '启动'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => toast.info('闲鱼客服设置功能开发中')}>
            <Settings size={14} className="mr-1.5" />
            设置
          </Button>
        </div>

        {/* 最近对话预览 */}
        <XianyuConversationList />
      </GlassCard>

      {/* 扫码登录弹窗 */}
      <Dialog open={qrDialogOpen} onOpenChange={setQrDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>闲鱼扫码登录</DialogTitle>
            <DialogDescription>使用闲鱼 App 扫描二维码登录</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center justify-center py-6 gap-4">
            {/* QR Image area */}
            <div className="w-[200px] h-[200px] rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center overflow-hidden">
              {qrState === 'loading' && (
                <Loader2 size={48} className="text-gray-400 animate-spin" />
              )}

              {qrState === 'waiting' && qrImage && (
                <img
                  src={qrImage.startsWith('data:') ? qrImage : `data:image/png;base64,${qrImage}`}
                  alt="闲鱼登录二维码"
                  className="w-full h-full object-contain"
                />
              )}

              {qrState === 'scanned' && (
                <div className="text-center text-green-500">
                  <CheckCircle2 size={48} className="mx-auto mb-2" />
                </div>
              )}

              {qrState === 'confirmed' && (
                <motion.div
                  initial={{ scale: 0.5, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className="text-center text-green-500"
                >
                  <CheckCircle2 size={64} className="mx-auto mb-2" />
                  <p className="text-sm font-medium">登录成功</p>
                </motion.div>
              )}

              {qrState === 'expired' && (
                <div className="text-center text-gray-400">
                  <QrCode size={48} className="mx-auto mb-2 opacity-50" />
                  <p className="text-sm">二维码已过期</p>
                </div>
              )}

              {qrState === 'error' && (
                <div className="text-center text-red-400">
                  <AlertCircle size={48} className="mx-auto mb-2 opacity-70" />
                  <p className="text-sm">生成失败</p>
                </div>
              )}

              {qrState === 'idle' && (
                <div className="text-center text-gray-400">
                  <QrCode size={48} className="mx-auto mb-2 opacity-50" />
                </div>
              )}
            </div>

            {/* Status text */}
            <div className="text-center text-sm">
              {qrState === 'loading' && (
                <p className="text-gray-400">正在生成二维码…</p>
              )}
              {qrState === 'waiting' && (
                <div className="space-y-1">
                  <p className="text-gray-300">请在 {countdown} 秒内打开闲鱼APP扫描</p>
                  <div className="w-48 h-1 bg-gray-700 rounded-full mx-auto overflow-hidden">
                    <div
                      className="h-full bg-[var(--oc-brand)] rounded-full transition-all duration-1000 ease-linear"
                      style={{ width: `${(countdown / 60) * 100}%` }}
                    />
                  </div>
                </div>
              )}
              {qrState === 'scanned' && (
                <p className="text-green-400">✅ 已扫码，请在手机上确认</p>
              )}
              {qrState === 'confirmed' && (
                <p className="text-green-400">✅ 登录成功，即将关闭…</p>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2">
              {(qrState === 'expired' || qrState === 'error') && (
                <Button variant="outline" size="sm" onClick={generateQR}>
                  <RefreshCw size={14} className="mr-1.5" />
                  重新生成
                </Button>
              )}
              {qrState !== 'confirmed' && (
                <Button variant="outline" size="sm" onClick={() => setQrDialogOpen(false)}>
                  取消
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────
   闲鱼对话记录子组件
──────────────────────────────────────────────────────────────── */

function XianyuConversationList() {
  const [conversations, setConversations] = useState<XianyuConversation[]>([]);
  const [showAll, setShowAll] = useState(false);

  // 15秒轮询对话列表
  useEffect(() => {
    const fetchConversations = async () => {
      try {
        const data = await api.xianyuConversations(20);
        const items: XianyuConversation[] = Array.isArray(data?.conversations)
          ? data.conversations
          : [];
        setConversations(items);
      } catch {
        // 静默失败
      }
    };

    fetchConversations();
    const timer = setInterval(fetchConversations, 15000);
    return () => clearInterval(timer);
  }, []);

  const displayed = showAll ? conversations : conversations.slice(0, 5);
  const hasMore = conversations.length > 5;

  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      <h4 className="text-sm font-medium text-white mb-3">最近对话</h4>
      {conversations.length === 0 ? (
        <div className="text-center py-4 text-gray-500 text-xs flex flex-col items-center gap-2">
          <MessageCircle size={20} className="opacity-40" />
          暂无对话记录
        </div>
      ) : (
        <div className="space-y-2">
          {displayed.map((conv) => (
            <div
              key={conv.id}
              className="flex items-center gap-3 p-2.5 rounded-lg bg-white/5 hover:bg-white/10 transition-colors cursor-pointer"
            >
              {/* Buyer avatar — first char */}
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-orange-400 to-pink-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                {conv.buyer_name?.charAt(0) || '?'}
              </div>

              {/* Message preview */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-medium text-white truncate">{conv.buyer_name}</span>
                  {conv.item_title && (
                    <span className="text-xs text-gray-500 truncate max-w-[120px]">
                      · {conv.item_title}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 truncate">
                  {conv.last_message?.length > 40
                    ? conv.last_message.slice(0, 40) + '…'
                    : conv.last_message}
                </p>
              </div>

              {/* Timestamp & unread badge */}
              <div className="flex flex-col items-end gap-1 flex-shrink-0">
                <span className="text-xs text-gray-500">
                  {formatDistanceToNow(new Date(conv.timestamp), {
                    addSuffix: true,
                    locale: zhCN,
                  })}
                </span>
                {conv.unread_count > 0 && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-[var(--oc-danger)] text-white text-xs font-bold">
                    {conv.unread_count > 99 ? '99+' : conv.unread_count}
                  </span>
                )}
              </div>
            </div>
          ))}

          {/* 查看更多 */}
          {hasMore && !showAll && (
            <button
              className="flex items-center justify-center gap-1 w-full py-2 text-xs text-[var(--oc-brand)] hover:text-white transition-colors"
              onClick={() => setShowAll(true)}
            >
              查看更多
              <ChevronRight size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Section 2: 社媒自动驾驶
──────────────────────────────────────────────────────────────── */

interface SocialStatus {
  autopilot_running?: boolean;
  platforms?: Array<{
    platform: string;
    connected: boolean;
    posts_today?: number;
    total_posts?: number;
  }>;
}

interface AutopilotStatus {
  running?: boolean;
  enabled?: boolean;
  today_planned?: number;
  today_published?: number;
  posts_today?: number;
  draft_count?: number;
  topics_selected?: number;
  next_action?: string;
  next_time?: string;
}

interface CalendarItem {
  id: string;
  platform: string;
  content: string;
  scheduled_at: string;
  status: 'pending' | 'published' | 'failed';
}

interface AnalyticsData {
  engagement_by_day?: { date: string; likes: number; comments: number }[];
  total_engagement?: number;
  engagement_rate?: number;
  posts_this_week?: number;
  best_time?: string;
  top_posts?: { id: string; content: string; platform: string; likes: number; comments: number }[];
}

interface MetricsData {
  total_followers?: number;
  xiaohongshu_followers?: number;
  twitter_followers?: number;
}

function ContentCalendarGrid({ items }: { items: CalendarItem[] }) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() + i);
    return date;
  });

  return (
    <div className="grid grid-cols-7 gap-2">
      {days.map((day) => {
        const dayItems = items.filter(item => {
          const itemDate = new Date(item.scheduled_at);
          return itemDate.toDateString() === day.toDateString();
        });

        return (
          <div key={day.toISOString()} className="min-h-[100px] p-2 rounded-lg bg-white/5 border border-white/10">
            <div className="text-xs text-gray-400 mb-2">
              {day.toLocaleDateString('zh-CN', { weekday: 'short', day: 'numeric' })}
            </div>
            {dayItems.map(item => (
              <div key={item.id} className={clsx(
                'text-xs p-1 rounded mb-1 truncate',
                item.status === 'published' ? 'bg-[var(--oc-success)]/20 text-[var(--oc-success)]' :
                item.status === 'failed' ? 'bg-[var(--oc-danger)]/20 text-[var(--oc-danger)]' :
                'bg-[var(--oc-brand)]/20 text-[var(--oc-brand)]'
              )}>
                {item.platform === 'xiaohongshu' ? '📕' : '🐦'} {item.content.slice(0, 15)}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function SocialSection() {
  const [socialStatus, setSocialStatus] = useState<SocialStatus>({});
  const [autopilotStatus, setAutopilotStatus] = useState<AutopilotStatus>({});
  const [calendar, setCalendar] = useState<CalendarItem[]>([]);
  const [calendarExpanded, setCalendarExpanded] = useState(false);
  const [analyticsExpanded, setAnalyticsExpanded] = useState(false);
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData>({});
  const [metricsData, setMetricsData] = useState<MetricsData>({});
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [composeDialogOpen, setComposeDialogOpen] = useState(false);
  const [composeText, setComposeText] = useState('');
  const [selectedPlatform, setSelectedPlatform] = useState('xiaohongshu');

  // 30秒轮询状态
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [socialRes, autopilotRes, calendarRes] = await Promise.all([
          clawbotFetch('/api/v1/social/status'),
          clawbotFetch('/api/v1/social/autopilot/status'),
          clawbotFetch('/api/v1/social/calendar?days=7'),
        ]);
        
        const socialData = socialRes.ok ? await socialRes.json() : {};
        const autopilotData = autopilotRes.ok ? await autopilotRes.json() : {};
        const calendarData = calendarRes.ok ? await calendarRes.json() : { items: [] };
        
        setSocialStatus(socialData);
        setAutopilotStatus(autopilotData);
        setCalendar(calendarData.items || []);
      } catch (err) {
        logger.error('获取社媒状态失败:', err);
      }
    };

    fetchStatus();
    const timer = setInterval(fetchStatus, 30000);
    return () => clearInterval(timer);
  }, []);

  // Lazy-load analytics data when expanded
  useEffect(() => {
    if (!analyticsExpanded) return;
    setAnalyticsLoading(true);

    Promise.all([
      clawbotFetch('/api/v1/social/analytics?days=7').then(r => r.ok ? r.json() : {}),
      clawbotFetch('/api/v1/social/metrics').then(r => r.ok ? r.json() : {}),
    ])
      .then(([analytics, metrics]) => {
        setAnalyticsData(analytics);
        setMetricsData(metrics);
      })
      .catch(err => {
        logger.error('获取分析数据失败:', err);
      })
      .finally(() => {
        setAnalyticsLoading(false);
      });
  }, [analyticsExpanded]);

  const handleAutopilotToggle = async (checked: boolean) => {
    try {
      const endpoint = checked ? '/api/v1/social/autopilot/start' : '/api/v1/social/autopilot/stop';
      await clawbotFetch(endpoint, { method: 'POST' });
      setAutopilotStatus((prev) => ({ ...prev, running: checked }));
    } catch (err) {
      logger.error('切换自动驾驶失败:', err);
    }
  };

  const handlePublish = async () => {
    if (!composeText.trim()) return;

    try {
      const resp = await clawbotFetch('/api/v1/social/publish', {
        method: 'POST',
        body: JSON.stringify({ platform: selectedPlatform, content: composeText }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      toast.success('发布成功');
      setComposeDialogOpen(false);
      setComposeText('');
    } catch (err) {
      toast.error(`发布失败: ${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const platformsList = Array.isArray(socialStatus.platforms) ? socialStatus.platforms : [];
  const xhsConnected = platformsList.find(p => p.platform === 'xhs')?.connected ?? false;
  const twitterConnected = platformsList.find(p => p.platform === 'x')?.connected ?? false;

  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">社媒自动驾驶</h2>
      <GlassCard>
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <Smartphone size={24} className="text-white" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">社媒自动驾驶</h3>
              <div className="flex items-center gap-3 mt-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-400">小红书</span>
                  <StatusIndicator status={xhsConnected ? 'running' : 'stopped'} size="sm" label="" />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-400">X/Twitter</span>
                  <StatusIndicator status={twitterConnected ? 'running' : 'stopped'} size="sm" label="" />
                </div>
              </div>
            </div>
          </div>
          <ToggleSwitch checked={autopilotStatus.running ?? false} onChange={handleAutopilotToggle} />
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400 mb-1">今日计划</div>
            <div className="text-xl font-bold text-white">
              <AnimatedNumber value={autopilotStatus.topics_selected ?? autopilotStatus.today_planned ?? 0} decimals={0} />条
            </div>
          </div>
          <div className="p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400 mb-1">已发布</div>
            <div className="text-xl font-bold text-white">
              <AnimatedNumber value={autopilotStatus.posts_today ?? autopilotStatus.today_published ?? 0} decimals={0} />条
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => setCalendarExpanded(!calendarExpanded)}
          >
            <Calendar size={14} className="mr-1.5" />
            内容日历
          </Button>
          <Button variant="outline" size="sm" onClick={() => setComposeDialogOpen(true)}>
            <Send size={14} className="mr-1.5" />
            立即发布
          </Button>
          <Button variant="outline" size="sm" onClick={() => setAnalyticsExpanded(!analyticsExpanded)}>
            <TrendingUp size={14} className="mr-1.5" />
            查看效果
          </Button>
        </div>

        {/* 内容日历展开区域 - 7天视觉网格 */}
        {calendarExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mt-4 pt-4 border-t border-white/10"
          >
            <h4 className="text-sm font-medium text-white mb-3">未来 7 天计划</h4>
            {calendar.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">暂无计划内容</p>
            ) : (
              <ContentCalendarGrid items={calendar} />
            )}
          </motion.div>
        )}

        {/* 数据分析展开区域 */}
        {analyticsExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mt-4 pt-4 border-t border-white/10"
          >
            <h4 className="text-sm font-medium text-white mb-3">数据分析</h4>
            {analyticsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={24} className="text-gray-400 animate-spin" />
                <span className="ml-2 text-sm text-gray-400">加载分析数据…</span>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Key metrics row - 4 cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <div className="flex items-center gap-1.5 mb-1">
                      <Users size={12} className="text-purple-400" />
                      <span className="text-xs text-gray-400">总粉丝数</span>
                    </div>
                    <div className="text-lg font-bold text-white">
                      <AnimatedNumber value={metricsData.total_followers || 0} decimals={0} />
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <div className="flex items-center gap-1.5 mb-1">
                      <TrendingUp size={12} className="text-green-400" />
                      <span className="text-xs text-gray-400">互动率</span>
                    </div>
                    <div className="text-lg font-bold text-white">
                      {((analyticsData.engagement_rate || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <div className="flex items-center gap-1.5 mb-1">
                      <BarChart3 size={12} className="text-blue-400" />
                      <span className="text-xs text-gray-400">本周发布</span>
                    </div>
                    <div className="text-lg font-bold text-white">
                      <AnimatedNumber value={analyticsData.posts_this_week || 0} decimals={0} />条
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <div className="flex items-center gap-1.5 mb-1">
                      <Clock size={12} className="text-orange-400" />
                      <span className="text-xs text-gray-400">最佳发布时间</span>
                    </div>
                    <div className="text-lg font-bold text-white">
                      {analyticsData.best_time || '--:--'}
                    </div>
                  </div>
                </div>

                {/* Engagement trend chart */}
                {analyticsData.engagement_by_day && analyticsData.engagement_by_day.length > 0 && (
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <h5 className="text-xs text-gray-400 mb-3">互动趋势（近7天）</h5>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart
                        data={analyticsData.engagement_by_day.map(d => ({
                          date: new Date(d.date).toLocaleDateString('zh-CN', { weekday: 'short' }),
                          engagement: d.likes + d.comments,
                        }))}
                        margin={{ top: 5, right: 10, left: -10, bottom: 5 }}
                      >
                        <XAxis
                          dataKey="date"
                          tick={{ fill: '#9ca3af', fontSize: 11 }}
                          axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                          tickLine={false}
                        />
                        <YAxis
                          tick={{ fill: '#9ca3af', fontSize: 11 }}
                          axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                          tickLine={false}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '8px',
                            color: '#fff',
                            fontSize: 12,
                          }}
                        />
                        <Line
                          type="monotone"
                          dataKey="engagement"
                          stroke="var(--oc-brand)"
                          strokeWidth={2}
                          dot={{ fill: 'var(--oc-brand)', r: 3 }}
                          activeDot={{ r: 5 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Top performing posts */}
                {analyticsData.top_posts && analyticsData.top_posts.length > 0 && (
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <h5 className="text-xs text-gray-400 mb-3">热门内容 Top 3</h5>
                    <div className="space-y-2">
                      {analyticsData.top_posts.slice(0, 3).map((post, idx) => (
                        <div key={post.id} className="flex items-start gap-2 p-2 rounded-lg bg-white/5">
                          <span className="text-xs font-bold text-[var(--oc-brand)] mt-0.5">#{idx + 1}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-gray-300 line-clamp-2">{post.content}</p>
                            <div className="flex items-center gap-3 mt-1">
                              <Badge variant="outline" className="text-xs">
                                {post.platform === 'xiaohongshu' ? '小红书' : 'X'}
                              </Badge>
                              <span className="text-xs text-gray-400">❤️ {post.likes}</span>
                              <span className="text-xs text-gray-400">💬 {post.comments}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </GlassCard>

      {/* 立即发布弹窗 */}
      <Dialog open={composeDialogOpen} onOpenChange={setComposeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>发布内容</DialogTitle>
            <DialogDescription>选择平台并输入要发布的内容</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-300 mb-2 block">平台</label>
              <div className="flex gap-2">
                <Button
                  variant={selectedPlatform === 'xiaohongshu' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedPlatform('xiaohongshu')}
                >
                  小红书
                </Button>
                <Button
                  variant={selectedPlatform === 'twitter' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedPlatform('twitter')}
                >
                  X/Twitter
                </Button>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-300 mb-2 block">内容</label>
              <textarea
                className="w-full h-32 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 resize-none focus:outline-none focus:ring-2 focus:ring-[var(--oc-brand)]"
                placeholder="输入要发布的内容..."
                value={composeText}
                onChange={(e) => setComposeText(e.target.value)}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setComposeDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={handlePublish} disabled={!composeText.trim()}>
                发布
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────
   Section 3: 自动化脚本网格
──────────────────────────────────────────────────────────────── */

type ServiceDisplayStatus = 'running' | 'stopped' | 'error' | 'starting' | 'stopping';

interface ServiceItem {
  id: string;
  status: ServiceDisplayStatus;
  /** 来自 getManagedServicesStatus 的友好名称 */
  managedName?: string;
  /** PID 信息 */
  pid?: number | null;
}

/** 默认图标和名称映射 — 仅当 API 未返回友好名称时做兜底 */
const DEFAULT_SERVICE_META: Record<string, { name: string; icon: React.ReactNode }> = {
  'clawbot-agent': { name: 'AI 助手后端', icon: <Bot size={20} /> },
  'xianyu': { name: '闲鱼 AI 客服', icon: <Fish size={20} /> },
  'gateway': { name: 'API 网关', icon: <Globe size={20} /> },
  'g4f': { name: 'G4F 免费模型', icon: <Cpu size={20} /> },
  'newapi': { name: 'New-API 网关', icon: <Server size={20} /> },
};

/** 根据服务 ID 猜一个合适的图标 */
function getServiceIcon(serviceId: string): React.ReactNode {
  if (serviceId.includes('bot') || serviceId.includes('agent')) return <Bot size={20} />;
  if (serviceId.includes('fish') || serviceId.includes('xianyu')) return <Fish size={20} />;
  if (serviceId.includes('gateway') || serviceId.includes('api')) return <Globe size={20} />;
  if (serviceId.includes('g4f') || serviceId.includes('model')) return <Cpu size={20} />;
  return <Server size={20} />;
}

/* ── Bot 详情弹窗 ── */

interface BotDetailProps {
  service: ServiceItem;
  botMatrix: ClawbotBotMatrixEntry[];
  open: boolean;
  onClose: () => void;
}

function BotDetailDialog({ service, botMatrix, open, onClose }: BotDetailProps) {
  const [activeTab, setActiveTab] = useState('overview');
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [runtimeConfig, setRuntimeConfig] = useState<Record<string, unknown> | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  const meta = DEFAULT_SERVICE_META[service.id] || {
    name: service.managedName || service.id,
    icon: getServiceIcon(service.id),
  };

  // 关联的 Bot 矩阵条目 — 通过 ID 模糊匹配
  const relatedBots = useMemo(() => {
    return botMatrix.filter((b) => {
      const sid = service.id.toLowerCase();
      const bid = b.id.toLowerCase();
      return bid.includes(sid) || sid.includes(bid) || bid === sid;
    });
  }, [botMatrix, service.id]);

  // 切换到日志 Tab 时拉取日志
  useEffect(() => {
    if (activeTab !== 'logs' || !open) return;
    let cancelled = false;
    setLogsLoading(true);
    api.getManagedServiceLogs(service.id, 30)
      .then((data) => {
        if (!cancelled) {
          setLogs(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => {
        if (!cancelled) setLogs(['（获取日志失败）']);
      })
      .finally(() => { if (!cancelled) setLogsLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab, service.id, open]);

  // 切换到配置 Tab 时拉取运行时配置
  useEffect(() => {
    if (activeTab !== 'config' || !open) return;
    let cancelled = false;
    setConfigLoading(true);
    api.getClawbotRuntimeConfig()
      .then((data) => {
        if (!cancelled) setRuntimeConfig(data as unknown as Record<string, unknown>);
      })
      .catch(() => {
        if (!cancelled) setRuntimeConfig(null);
      })
      .finally(() => { if (!cancelled) setConfigLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab, open]);

  // 弹窗关闭时重置 Tab
  useEffect(() => {
    if (!open) {
      setActiveTab('overview');
      setLogs([]);
      setRuntimeConfig(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white flex-shrink-0">
              {meta.icon}
            </span>
            {service.managedName || meta.name}
          </DialogTitle>
          <DialogDescription>
            服务 ID: {service.id}
            {service.pid ? ` · PID: ${service.pid}` : ''}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 min-h-0 flex flex-col">
          <TabsList className="w-full grid grid-cols-4">
            <TabsTrigger value="overview"><Eye size={13} className="mr-1" />概览</TabsTrigger>
            <TabsTrigger value="config"><Settings size={13} className="mr-1" />配置</TabsTrigger>
            <TabsTrigger value="logs"><Terminal size={13} className="mr-1" />日志</TabsTrigger>
            <TabsTrigger value="stats"><Activity size={13} className="mr-1" />统计</TabsTrigger>
          </TabsList>

          {/* ── 概览 Tab ── */}
          <TabsContent value="overview" className="mt-3 overflow-y-auto flex-1">
            <div className="space-y-3">
              {/* 运行状态 */}
              <div className="p-3 rounded-lg bg-white/5 flex items-center justify-between">
                <span className="text-sm text-gray-400">运行状态</span>
                <StatusIndicator status={service.status} />
              </div>

              {/* 模型信息（来自 Bot 矩阵） */}
              {relatedBots.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs text-gray-400 font-medium flex items-center gap-1">
                    <Zap size={12} /> 关联 Bot 信息
                  </h4>
                  {relatedBots.map((bot) => (
                    <div key={bot.id} className="p-3 rounded-lg bg-white/5 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">{bot.name}</span>
                        <Badge variant={bot.ready ? 'default' : 'outline'} className="text-xs">
                          {bot.ready ? '就绪' : '未就绪'}
                        </Badge>
                      </div>
                      <div className="text-xs text-gray-400 space-y-0.5">
                        <div>用户名: <span className="text-gray-300">{bot.username || '未配置'}</span></div>
                        <div>模型: <span className="text-gray-300">{bot.route_model || '未配置'}</span></div>
                        <div>提供商: <span className="text-gray-300">{bot.route_provider || '未配置'}</span></div>
                        <div>Token: <span className="text-gray-300">{bot.token_configured ? (bot.token_masked || '已配置') : '未配置'}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {relatedBots.length === 0 && (
                <div className="p-3 rounded-lg bg-white/5 text-center text-xs text-gray-500">
                  <Bot size={20} className="mx-auto mb-1 opacity-40" />
                  无关联 Bot 矩阵数据
                </div>
              )}
            </div>
          </TabsContent>

          {/* ── 配置 Tab ── */}
          <TabsContent value="config" className="mt-3 overflow-y-auto flex-1">
            {configLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={20} className="text-gray-400 animate-spin" />
                <span className="ml-2 text-sm text-gray-400">加载配置…</span>
              </div>
            ) : runtimeConfig ? (
              <div className="space-y-2">
                <p className="text-xs text-gray-400 mb-2">当前运行时配置（只读）</p>
                {Object.entries(runtimeConfig).map(([key, value]) => (
                  <div key={key} className="p-2.5 rounded-lg bg-white/5 flex items-start gap-2">
                    <code className="text-xs text-[var(--oc-brand)] font-mono flex-shrink-0 mt-0.5">{key}</code>
                    <span className="text-xs text-gray-300 break-all">
                      {typeof value === 'string'
                        ? (key.toLowerCase().includes('token') || key.toLowerCase().includes('key')
                          ? '••••••'
                          : value || '（空）')
                        : JSON.stringify(value)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-sm text-gray-500">
                <FileText size={24} className="mx-auto mb-2 opacity-40" />
                暂无配置数据
              </div>
            )}
          </TabsContent>

          {/* ── 日志 Tab ── */}
          <TabsContent value="logs" className="mt-3 overflow-y-auto flex-1">
            {logsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={20} className="text-gray-400 animate-spin" />
                <span className="ml-2 text-sm text-gray-400">加载日志…</span>
              </div>
            ) : logs.length > 0 ? (
              <div className="space-y-0.5">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-gray-400">最近 {logs.length} 条日志</p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setLogsLoading(true);
                      api.getManagedServiceLogs(service.id, 30)
                        .then((data) => setLogs(Array.isArray(data) ? data : []))
                        .catch(() => setLogs(['（刷新失败）']))
                        .finally(() => setLogsLoading(false));
                    }}
                  >
                    <RefreshCw size={12} className="mr-1" />
                    刷新
                  </Button>
                </div>
                <div className="rounded-lg bg-black/30 p-3 max-h-[300px] overflow-y-auto font-mono text-xs text-gray-300 space-y-0.5">
                  {logs.map((line, i) => (
                    <div key={i} className="leading-relaxed break-all hover:bg-white/5 px-1 rounded">
                      <span className="text-gray-600 mr-2 select-none">{i + 1}</span>
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-sm text-gray-500">
                <Terminal size={24} className="mx-auto mb-2 opacity-40" />
                暂无日志数据
              </div>
            )}
          </TabsContent>

          {/* ── 统计 Tab ── */}
          <TabsContent value="stats" className="mt-3 overflow-y-auto flex-1">
            <div className="space-y-3">
              {/* Bot 矩阵统计 */}
              {relatedBots.length > 0 ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Hash size={12} className="text-blue-400" />
                        <span className="text-xs text-gray-400">关联 Bot 数</span>
                      </div>
                      <div className="text-lg font-bold text-white">{relatedBots.length}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Cpu size={12} className="text-purple-400" />
                        <span className="text-xs text-gray-400">使用模型数</span>
                      </div>
                      <div className="text-lg font-bold text-white">
                        {new Set(relatedBots.map((b) => b.route_model).filter(Boolean)).size}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <div className="flex items-center gap-1.5 mb-1">
                        <CheckCircle2 size={12} className="text-green-400" />
                        <span className="text-xs text-gray-400">已就绪</span>
                      </div>
                      <div className="text-lg font-bold text-white">
                        {relatedBots.filter((b) => b.ready).length}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <div className="flex items-center gap-1.5 mb-1">
                        <AlertCircle size={12} className="text-orange-400" />
                        <span className="text-xs text-gray-400">Token 已配置</span>
                      </div>
                      <div className="text-lg font-bold text-white">
                        {relatedBots.filter((b) => b.token_configured).length}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-sm text-gray-500">
                  <Activity size={24} className="mx-auto mb-2 opacity-40" />
                  暂无统计数据
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function ServicesSection() {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [transitioning, setTransitioning] = useState<Set<string>>(new Set());
  const [fetchError, setFetchError] = useState<FriendlyError | null>(null);
  const [selectedService, setSelectedService] = useState<ServiceItem | null>(null);
  /** 从 getManagedServicesStatus 获取的服务元信息 */
  const [managedMeta, setManagedMeta] = useState<Record<string, ManagedServiceStatus>>({});
  /** Bot 矩阵数据 — 用于显示模型和命令数 */
  const [botMatrix, setBotMatrix] = useState<ClawbotBotMatrixEntry[]>([]);

  // Use a ref to avoid re-creating fetchServices (and stacking intervals)
  // every time `transitioning` changes identity.
  const transitioningRef = useRef(transitioning);
  transitioningRef.current = transitioning;

  // 拉取动态服务元信息 + Bot 矩阵
  useEffect(() => {
    // 获取 managed services 元信息（名称、PID 等）
    api.getManagedServicesStatus()
      .then((list) => {
        if (Array.isArray(list)) {
          const map: Record<string, ManagedServiceStatus> = {};
          for (const svc of list) {
            map[svc.label] = svc;
          }
          setManagedMeta(map);
        }
      })
      .catch(() => {
        // 回退到硬编码，不影响功能
      });

    // 获取 Bot 矩阵
    api.getClawbotBotMatrix()
      .then((list) => {
        if (Array.isArray(list)) {
          setBotMatrix(list);
        }
      })
      .catch(() => {
        // 静默失败
      });
  }, []);

  const fetchServices = useCallback(async () => {
    try {
      const data = await api.services();
      const list: ServiceItem[] = Array.isArray(data)
        ? data
        : Array.isArray(data?.services)
          ? data.services
          : [];
      // 保留 transitioning 状态，仅更新非过渡中的服务
      setServices((prev) => {
        return list.map((svc: { id: string; status?: string }) => {
          const prevSvc = prev.find((p) => p.id === svc.id);
          const isTransitioning = transitioningRef.current.has(svc.id);
          const backendStatus = svc.status === 'running' ? 'running' : 'stopped';
          return {
            id: svc.id,
            status: isTransitioning && prevSvc ? prevSvc.status : backendStatus,
          } as ServiceItem;
        });
      });

      // 如果后端状态已确认，清除 transitioning 标记
      setTransitioning((prev) => {
        const next = new Set(prev);
        for (const svc of list as Array<{ id: string; status?: string }>) {
          if (next.has(svc.id)) {
            next.delete(svc.id);
          }
        }
        return next.size === prev.size ? prev : next;
      });
      setFetchError(null);
    } catch (err) {
      setFetchError(toFriendlyError(err));
    }
  }, []);

  // WebSocket: receive service status changes in real-time
  useClawbotWS('service_change', useCallback((_event) => {
    // Trigger an immediate refresh instead of waiting for next poll
    fetchServices();
  }, [fetchServices]));

  // 初始拉取 + 30 秒轮询（WebSocket service_change 事件已提供实时更新）
  useEffect(() => {
    fetchServices();
    const timer = setInterval(fetchServices, 30000);
    return () => clearInterval(timer);
  }, [fetchServices]);

  const handleToggle = useCallback(async (serviceId: string, currentlyRunning: boolean) => {
    const targetStatus: ServiceDisplayStatus = currentlyRunning ? 'stopping' : 'starting';

    // 乐观更新 UI
    setServices((prev) =>
      prev.map((s) => (s.id === serviceId ? { ...s, status: targetStatus } : s))
    );
    setTransitioning((prev) => new Set(prev).add(serviceId));

    try {
      if (currentlyRunning) {
        await api.serviceStop(serviceId);
      } else {
        await api.serviceStart(serviceId);
      }
      // 操作成功后立即刷新
      await fetchServices();
    } catch {
      // 回滚状态
      setServices((prev) =>
        prev.map((s) =>
          s.id === serviceId ? { ...s, status: currentlyRunning ? 'running' : 'stopped' } : s
        )
      );
      setTransitioning((prev) => {
        const next = new Set(prev);
        next.delete(serviceId);
        return next;
      });
      toast.error(`${currentlyRunning ? '停止' : '启动'}服务失败`);
    }
  }, [fetchServices]);

  /** 合并 API 列表 + managed services — 确保所有已知服务都能显示 */
  const allServices = useMemo(() => {
    // 以 api.services() 返回的列表为基础
    const result = [...services];
    const existingIds = new Set(result.map((s) => s.id));

    // 把 managedMeta 中没出现在 services 列表里的也加进来
    for (const [label, meta] of Object.entries(managedMeta)) {
      if (!existingIds.has(label)) {
        result.push({
          id: label,
          status: meta.running ? 'running' : 'stopped',
          managedName: meta.name,
          pid: meta.pid,
        });
      }
    }

    // 给已有服务补充 managedName / pid
    return result.map((svc) => {
      const mm = managedMeta[svc.id];
      if (mm) {
        return { ...svc, managedName: mm.name, pid: mm.pid };
      }
      return svc;
    });
  }, [services, managedMeta]);

  /** 快速查找某个服务关联了多少 bot 和模型 */
  const getServiceBotInfo = useCallback((serviceId: string) => {
    const related = botMatrix.filter((b) => {
      const sid = serviceId.toLowerCase();
      const bid = b.id.toLowerCase();
      return bid.includes(sid) || sid.includes(bid) || bid === sid;
    });
    const modelSet = new Set(related.map((b) => b.route_model).filter(Boolean));
    return { botCount: related.length, modelCount: modelSet.size };
  }, [botMatrix]);

  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">自动化脚本</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {allServices.map((service) => {
          const defaultMeta = DEFAULT_SERVICE_META[service.id];
          const displayName = service.managedName || defaultMeta?.name || service.id;
          const icon = defaultMeta?.icon || getServiceIcon(service.id);
          const isRunning = service.status === 'running';
          const isBusy = service.status === 'starting' || service.status === 'stopping';
          const { botCount, modelCount } = getServiceBotInfo(service.id);

          return (
            <GlassCard
              key={service.id}
              className="p-4 cursor-pointer hover:ring-1 hover:ring-[var(--oc-brand)]/40 transition-all"
              onClick={() => setSelectedService(service)}
            >
              <div className="flex flex-col items-center text-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white">
                  {icon}
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-white mb-1">{displayName}</h4>
                  <StatusIndicator status={service.status} size="sm" />
                  {/* 模型数和 Bot 数 */}
                  {botCount > 0 && (
                    <div className="flex items-center justify-center gap-2 mt-1.5">
                      <span className="text-xs text-gray-500 flex items-center gap-0.5">
                        <Cpu size={10} />{modelCount} 模型
                      </span>
                      <span className="text-xs text-gray-500 flex items-center gap-0.5">
                        <Bot size={10} />{botCount} Bot
                      </span>
                    </div>
                  )}
                </div>
                {/* 阻止开关点击冒泡到卡片 */}
                <div onClick={(e) => e.stopPropagation()}>
                  <ToggleSwitch
                    checked={isRunning || service.status === 'stopping'}
                    onChange={() => handleToggle(service.id, isRunning)}
                    size="sm"
                    disabled={isBusy}
                  />
                </div>
              </div>
            </GlassCard>
          );
        })}
        {allServices.length === 0 && fetchError && (
          <div className="col-span-full">
            <ErrorState error={fetchError} onRetry={fetchServices} compact />
          </div>
        )}
        {allServices.length === 0 && !fetchError && (
          <div className="col-span-full text-center py-8 text-gray-400 text-sm">
            加载服务列表中…
          </div>
        )}
      </div>

      {/* Bot 详情弹窗 */}
      {selectedService && (
        <BotDetailDialog
          service={selectedService}
          botMatrix={botMatrix}
          open={!!selectedService}
          onClose={() => setSelectedService(null)}
        />
      )}
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────
   Section 4: 通知中心
──────────────────────────────────────────────────────────────── */

type NotificationType = 'urgent' | 'trading' | 'xianyu' | 'social' | 'system';

interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  timestamp: Date;
  read?: boolean;
  actions?: { label: string; onClick: () => void }[];
}

const NOTIFICATION_CONFIG: Record<
  NotificationType,
  { icon: React.ReactNode; color: string; label: string }
> = {
  urgent: { icon: <AlertCircle size={16} />, color: 'text-[var(--oc-danger)]', label: '紧急' },
  trading: { icon: <DollarSign size={16} />, color: 'text-[var(--oc-success)]', label: '交易' },
  xianyu: { icon: <Fish size={16} />, color: 'text-orange-400', label: '闲鱼' },
  social: { icon: <Smartphone size={16} />, color: 'text-purple-400', label: '社媒' },
  system: { icon: <Info size={16} />, color: 'text-blue-400', label: '系统' },
};

/** Map backend category to frontend NotificationType */
function mapCategory(category: string): NotificationType {
  switch (category) {
    case 'trading':
      return 'trading';
    case 'xianyu':
      return 'xianyu';
    case 'social':
      return 'social';
    case 'security':
    case 'ai':
    case 'system':
      return 'system';
    default:
      return 'system';
  }
}

function NotificationSection() {
  const [filter, setFilter] = useState<'all' | NotificationType>('all');
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [fetchError, setFetchError] = useState<FriendlyError | null>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await api.notifications({ limit: 50 });
      const items: Array<Record<string, unknown>> = Array.isArray(data)
        ? data
        : Array.isArray(data?.notifications)
          ? data.notifications
          : [];

      const mapped: Notification[] = items.map((n) => ({
        id: String(n.id || n.notification_id || ''),
        type: mapCategory(String(n.category || 'system')),
        title: String(n.title || ''),
        body: String(n.body || n.message || n.content || ''),
        timestamp: new Date(String(n.timestamp ?? n.created_at ?? Date.now())),
        read: Boolean(n.read),
      }));

      setNotifications(mapped);
      setFetchError(null);
    } catch (err) {
      setFetchError(toFriendlyError(err));
    }
  }, []);

  // 初始拉取 + 10 秒轮询
  useEffect(() => {
    fetchNotifications();
    const timer = setInterval(fetchNotifications, 10000);
    return () => clearInterval(timer);
  }, [fetchNotifications]);

  const handleMarkRead = useCallback(async (notifId: string) => {
    try {
      await api.markNotificationRead(notifId);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, read: true } : n))
      );
    } catch {
      // 静默失败
    }
  }, []);

  const filtered =
    filter === 'all'
      ? notifications
      : notifications.filter((n) => n.type === filter);

  const formatTime = (date: Date) => {
    return formatDistanceToNow(date, { addSuffix: true, locale: zhCN });
  };

  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">通知中心</h2>
      <GlassCard>
        <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
          <TabsList className="w-full grid grid-cols-6 mb-4">
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="urgent">🚨紧急</TabsTrigger>
            <TabsTrigger value="trading">💰交易</TabsTrigger>
            <TabsTrigger value="xianyu">🐟闲鱼</TabsTrigger>
            <TabsTrigger value="social">📱社媒</TabsTrigger>
            <TabsTrigger value="system">ℹ️系统</TabsTrigger>
          </TabsList>

          <TabsContent value={filter} className="mt-0">
            {fetchError && notifications.length === 0 ? (
              <ErrorState error={fetchError} onRetry={fetchNotifications} compact />
            ) : filtered.length === 0 ? (
              <div className="text-center py-12">
                <Bell size={48} className="mx-auto mb-3 text-gray-500 opacity-50" />
                <p className="text-gray-400">暂无通知</p>
              </div>
            ) : (
              <div className="space-y-3">
                {filtered.map((notif) => {
                  const config = NOTIFICATION_CONFIG[notif.type];
                  return (
                    <motion.div
                      key={notif.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={clsx(
                        'p-3 rounded-lg hover:bg-white/10 transition-colors',
                        notif.read ? 'bg-white/3 opacity-60' : 'bg-white/5'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div className={clsx('mt-0.5', config.color)}>{config.icon}</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant="outline" className="text-xs">
                              {config.label}
                            </Badge>
                            <span className="text-xs text-gray-400">{formatTime(notif.timestamp)}</span>
                            {!notif.read && (
                              <span className="w-1.5 h-1.5 rounded-full bg-[var(--oc-brand)]" />
                            )}
                          </div>
                          <h4 className="text-sm font-medium text-white mb-1">{notif.title}</h4>
                          <p className="text-sm text-gray-300">{notif.body}</p>
                          {!notif.read && (
                            <div className="flex gap-2 mt-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleMarkRead(notif.id)}
                              >
                                标记已读
                              </Button>
                              {notif.actions?.map((action, idx) => (
                                <Button key={idx} variant="outline" size="sm" onClick={action.onClick}>
                                  {action.label}
                                </Button>
                              ))}
                            </div>
                          )}
                          {notif.read && notif.actions && (
                            <div className="flex gap-2 mt-2">
                              {notif.actions.map((action, idx) => (
                                <Button key={idx} variant="outline" size="sm" onClick={action.onClick}>
                                  {action.label}
                                </Button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </GlassCard>
    </section>
  );
}

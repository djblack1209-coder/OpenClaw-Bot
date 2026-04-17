import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import {
  Fish,
  Smartphone,
  Trophy,
  Mail,
  ShoppingCart,
  TrendingUp,
  CheckSquare,
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
} from 'lucide-react';

import { GlassCard, StatusIndicator, ToggleSwitch, AnimatedNumber } from '../shared';
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
import { clawbotFetch } from '@/lib/tauri';

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

  // 10秒轮询状态
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await clawbotFetch('/api/v1/status');
        const data = await res.json();
        setStatus(data.xianyu || { online: false });
      } catch (err) {
        console.error('获取闲鱼状态失败:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const timer = setInterval(fetchStatus, 10000);
    return () => clearInterval(timer);
  }, []);

  const handleToggle = async (checked: boolean) => {
    // TODO: 后端 API 未就绪，暂时只更新本地状态
    setStatus((prev) => ({ ...prev, online: checked }));
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
          <Button variant="outline" size="sm">
            <Settings size={14} className="mr-1.5" />
            设置
          </Button>
        </div>
      </GlassCard>

      {/* 扫码登录弹窗 */}
      <Dialog open={qrDialogOpen} onOpenChange={setQrDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>闲鱼扫码登录</DialogTitle>
            <DialogDescription>使用闲鱼 App 扫描二维码登录</DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-center py-8">
            <div className="w-48 h-48 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              <div className="text-center text-gray-400">
                <QrCode size={48} className="mx-auto mb-2 opacity-50" />
                <p className="text-sm">功能开发中</p>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────
   Section 2: 社媒自动驾驶
──────────────────────────────────────────────────────────────── */

interface SocialStatus {
  platforms?: {
    xiaohongshu?: { connected: boolean };
    twitter?: { connected: boolean };
  };
}

interface AutopilotStatus {
  running?: boolean;
  today_planned?: number;
  today_published?: number;
}

interface CalendarItem {
  id: string;
  platform: string;
  content: string;
  scheduled_at: string;
  status: 'pending' | 'published' | 'failed';
}

function SocialSection() {
  const [socialStatus, setSocialStatus] = useState<SocialStatus>({});
  const [autopilotStatus, setAutopilotStatus] = useState<AutopilotStatus>({});
  const [calendar, setCalendar] = useState<CalendarItem[]>([]);
  const [calendarExpanded, setCalendarExpanded] = useState(false);
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
        
        const socialData = await socialRes.json();
        const autopilotData = await autopilotRes.json();
        const calendarData = await calendarRes.json();
        
        setSocialStatus(socialData);
        setAutopilotStatus(autopilotData);
        setCalendar(calendarData.items || []);
      } catch (err) {
        console.error('获取社媒状态失败:', err);
      }
    };

    fetchStatus();
    const timer = setInterval(fetchStatus, 30000);
    return () => clearInterval(timer);
  }, []);

  const handleAutopilotToggle = async (checked: boolean) => {
    try {
      const endpoint = checked ? '/api/v1/social/autopilot/start' : '/api/v1/social/autopilot/stop';
      await clawbotFetch(endpoint, { method: 'POST' });
      setAutopilotStatus((prev) => ({ ...prev, running: checked }));
    } catch (err) {
      console.error('切换自动驾驶失败:', err);
    }
  };

  const handlePublish = async () => {
    if (!composeText.trim()) return;
    
    try {
      await clawbotFetch('/api/v1/social/publish', {
        method: 'POST',
        body: JSON.stringify({ platform: selectedPlatform, content: composeText }),
      });
      setComposeDialogOpen(false);
      setComposeText('');
    } catch (err) {
      console.error('发布失败:', err);
    }
  };

  const xhsConnected = socialStatus.platforms?.xiaohongshu?.connected ?? false;
  const twitterConnected = socialStatus.platforms?.twitter?.connected ?? false;

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
              <AnimatedNumber value={autopilotStatus.today_planned || 0} decimals={0} />条
            </div>
          </div>
          <div className="p-3 rounded-lg bg-white/5">
            <div className="text-xs text-gray-400 mb-1">已发布</div>
            <div className="text-xl font-bold text-white">
              <AnimatedNumber value={autopilotStatus.today_published || 0} decimals={0} />条
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
          <Button variant="outline" size="sm">
            查看效果
          </Button>
        </div>

        {/* 内容日历展开区域 */}
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
              <div className="space-y-2">
                {calendar.slice(0, 5).map((item) => (
                  <div key={item.id} className="p-2 rounded-lg bg-white/5 text-sm">
                    <div className="flex items-center justify-between mb-1">
                      <Badge variant="outline" className="text-xs">
                        {item.platform === 'xiaohongshu' ? '小红书' : 'X'}
                      </Badge>
                      <span className="text-xs text-gray-400">
                        {new Date(item.scheduled_at).toLocaleDateString('zh-CN')}
                      </span>
                    </div>
                    <p className="text-gray-300 line-clamp-2">{item.content}</p>
                  </div>
                ))}
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

interface ServiceCardData {
  id: string;
  name: string;
  icon: React.ReactNode;
  status: 'running' | 'stopped';
}

const SERVICES: ServiceCardData[] = [
  { id: 'bounty_hunter', name: '赏金猎人', icon: <Trophy size={20} />, status: 'running' },
  { id: 'email_triage', name: '邮件管家', icon: <Mail size={20} />, status: 'stopped' },
  { id: 'shopping_compare', name: '购物比价', icon: <ShoppingCart size={20} />, status: 'running' },
  { id: 'position_monitor', name: '持仓监控', icon: <TrendingUp size={20} />, status: 'running' },
  { id: 'task_mgmt', name: '任务管理', icon: <CheckSquare size={20} />, status: 'stopped' },
];

function ServicesSection() {
  const [services] = useState(SERVICES);

  const handleToggle = () => {
    // TODO: 后端 API 未就绪，显示提示
    alert('功能开发中');
  };

  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">自动化脚本</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {services.map((service) => (
          <GlassCard key={service.id} className="p-4">
            <div className="flex flex-col items-center text-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white">
                {service.icon}
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-medium text-white mb-1">{service.name}</h4>
                <StatusIndicator status={service.status} size="sm" />
              </div>
              <ToggleSwitch
                checked={service.status === 'running'}
                onChange={handleToggle}
                size="sm"
              />
            </div>
          </GlassCard>
        ))}
      </div>
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
  actions?: { label: string; onClick: () => void }[];
}

// 演示数据
const DEMO_NOTIFICATIONS: Notification[] = [
  {
    id: '1',
    type: 'urgent',
    title: '闲鱼客服需要人工介入',
    body: '买家询问退货政策，AI 置信度不足，建议人工回复',
    timestamp: new Date(Date.now() - 5 * 60 * 1000),
  },
  {
    id: '2',
    type: 'trading',
    title: 'AAPL 触发止盈信号',
    body: '当前盈利 +8.5%，建议部分止盈',
    timestamp: new Date(Date.now() - 15 * 60 * 1000),
  },
  {
    id: '3',
    type: 'xianyu',
    title: '自动成交 1 单',
    body: '商品「二手 MacBook Pro」已自动成交，买家已付款',
    timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000),
  },
  {
    id: '4',
    type: 'social',
    title: '小红书内容已发布',
    body: '「AI 工具推荐」已成功发布到小红书',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000),
  },
  {
    id: '5',
    type: 'system',
    title: '系统更新可用',
    body: 'OpenClaw Bot v1.2.0 已发布，包含性能优化和新功能',
    timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000),
  },
];

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

function NotificationSection() {
  const [filter, setFilter] = useState<'all' | NotificationType>('all');
  const [notifications] = useState(DEMO_NOTIFICATIONS);

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
            {filtered.length === 0 ? (
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
                      className="p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                    >
                      <div className="flex items-start gap-3">
                        <div className={clsx('mt-0.5', config.color)}>{config.icon}</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant="outline" className="text-xs">
                              {config.label}
                            </Badge>
                            <span className="text-xs text-gray-400">{formatTime(notif.timestamp)}</span>
                          </div>
                          <h4 className="text-sm font-medium text-white mb-1">{notif.title}</h4>
                          <p className="text-sm text-gray-300">{notif.body}</p>
                          {notif.actions && (
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

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Loader2, TrendingUp, ShoppingBag, Share2, Bot } from 'lucide-react';
import { api, isTauri } from '@/lib/tauri';
import clsx from 'clsx';

/**
 * 活动类型
 */
type ActivityType = 'trading' | 'xianyu' | 'social' | 'system';

/**
 * 活动条目
 */
interface ActivityItem {
  id: string;
  type: ActivityType;
  title: string;
  description: string;
  timestamp: string;
  status?: 'success' | 'warning' | 'error';
}

/**
 * 最近活动时间线组件 - TradingView 风格
 */
export function RecentActivity() {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchActivities = async () => {
      if (!isTauri()) {
        setLoading(false);
        // 使用模拟数据
        setActivities(getMockActivities());
        return;
      }

      try {
        const resp = await api.clawbotStatus();
        const data = resp as { activities?: ActivityItem[]; recent_activities?: ActivityItem[] };
        
        if ((data.activities && data.activities.length > 0) || (data.recent_activities && data.recent_activities.length > 0)) {
          setActivities(data.activities || data.recent_activities || []);
        } else {
          // 使用模拟数据
          setActivities(getMockActivities());
        }
      } catch (e) {
        // 使用模拟数据
        setActivities(getMockActivities());
      } finally {
        setLoading(false);
      }
    };

    fetchActivities();
    // 每30秒刷新一次
    const interval = setInterval(fetchActivities, 30000);
    return () => clearInterval(interval);
  }, []);

  const getMockActivities = (): ActivityItem[] => {
    const now = new Date();
    return [
      {
        id: '1',
        type: 'trading',
        title: '交易执行',
        description: '买入 AAPL 100 股 @ $150.25',
        timestamp: new Date(now.getTime() - 5 * 60000).toISOString(),
        status: 'success',
      },
      {
        id: '2',
        type: 'xianyu',
        title: '闲鱼客服',
        description: '自动回复买家咨询 3 条',
        timestamp: new Date(now.getTime() - 15 * 60000).toISOString(),
        status: 'success',
      },
      {
        id: '3',
        type: 'social',
        title: '社媒发布',
        description: '发布小红书笔记《投资心得分享》',
        timestamp: new Date(now.getTime() - 45 * 60000).toISOString(),
        status: 'success',
      },
      {
        id: '4',
        type: 'trading',
        title: '风控提醒',
        description: '持仓 TSLA 回撤超过 5%',
        timestamp: new Date(now.getTime() - 90 * 60000).toISOString(),
        status: 'warning',
      },
      {
        id: '5',
        type: 'system',
        title: '系统启动',
        description: 'OpenClaw Bot 服务已启动',
        timestamp: new Date(now.getTime() - 120 * 60000).toISOString(),
        status: 'success',
      },
    ];
  };

  const getActivityIcon = (type: ActivityType) => {
    switch (type) {
      case 'trading':
        return <TrendingUp size={14} className="text-success" />;
      case 'xianyu':
        return <ShoppingBag size={14} className="text-warning" />;
      case 'social':
        return <Share2 size={14} className="text-info" />;
      case 'system':
        return <Bot size={14} className="text-[var(--brand-500)]" />;
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'success':
        return 'bg-success';
      case 'warning':
        return 'bg-warning';
      case 'error':
        return 'bg-danger';
      default:
        return 'bg-gray-500';
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小时前`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay} 天前`;
  };

  return (
    <Card className="border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Activity className="h-4 w-4 text-[var(--brand-500)]" />
          最近活动
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <div className="flex items-center justify-center h-[400px]">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--brand-500)]" />
          </div>
        ) : (
          <div className="space-y-4 max-h-[400px] overflow-y-auto scrollbar-thin scrollbar-thumb-[var(--border-default)] scrollbar-track-transparent">
            {activities.map((activity, index) => (
              <div key={activity.id} className="relative">
                {/* 时间线 */}
                {index < activities.length - 1 && (
                  <div className="absolute left-[7px] top-6 bottom-0 w-px bg-[var(--border-light)]" />
                )}
                
                <div className="flex gap-3">
                  {/* 图标 */}
                  <div className="relative flex-shrink-0">
                    <div className="w-7 h-7 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] flex items-center justify-center">
                      {getActivityIcon(activity.type)}
                    </div>
                    {activity.status && (
                      <div
                        className={clsx(
                          'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-[var(--bg-primary)]',
                          getStatusColor(activity.status)
                        )}
                      />
                    )}
                  </div>

                  {/* 内容 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                          {activity.title}
                        </p>
                        <p className="text-xs text-[var(--text-secondary)] mt-0.5 line-clamp-2">
                          {activity.description}
                        </p>
                      </div>
                      <span className="text-[10px] text-[var(--text-tertiary)] whitespace-nowrap">
                        {formatTime(activity.timestamp)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

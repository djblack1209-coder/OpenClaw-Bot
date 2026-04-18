import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Loader2, TrendingUp, ShoppingBag, Share2, Bot, AlertCircle } from 'lucide-react';
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
 * 审计修复: 移除 Mock 数据，API 失败时展示空态而非虚假活动
 */
export function RecentActivity() {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchActivities = async () => {
      if (!isTauri()) {
        // 非 Tauri 环境（浏览器开发），展示空态
        setLoading(false);
        return;
      }

      try {
        const resp = await api.clawbotStatus();
        const data = resp as { activities?: ActivityItem[]; recent_activities?: ActivityItem[] };
        
        if ((data.activities && data.activities.length > 0) || (data.recent_activities && data.recent_activities.length > 0)) {
          setActivities(data.activities || data.recent_activities || []);
        }
        // API 返回空数据时保持空态，不使用 Mock
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    };

    fetchActivities();
    // 每30秒刷新一次
    const interval = setInterval(fetchActivities, 30000);
    return () => clearInterval(interval);
  }, []);

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
        ) : activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-[400px] text-center">
            {error ? (
              <>
                <AlertCircle className="h-8 w-8 text-[var(--text-tertiary)] mb-2" />
                <p className="text-sm text-[var(--text-secondary)]">活动数据加载失败</p>
                <p className="text-xs text-[var(--text-tertiary)] mt-1">请检查后端服务是否运行</p>
              </>
            ) : (
              <>
                <Activity className="h-8 w-8 text-[var(--text-tertiary)] mb-2" />
                <p className="text-sm text-[var(--text-secondary)]">暂无活动记录</p>
                <p className="text-xs text-[var(--text-tertiary)] mt-1">系统运行后自动展示</p>
              </>
            )}
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

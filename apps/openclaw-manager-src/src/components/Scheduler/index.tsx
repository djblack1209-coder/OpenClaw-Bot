import { useState, useEffect, useCallback } from 'react';
import { Clock, RefreshCw, Pause, Play, AlertTriangle, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent } from '@/components/ui/card';
import { clawbotFetch } from '@/lib/tauri';
import { createLogger } from '@/lib/logger';
import { toast } from 'sonner';

const schedulerLogger = createLogger('Scheduler');

/** 单个定时任务的数据结构 */
interface SchedulerTask {
  id: string;
  name: string;
  cron: string;
  enabled: boolean;
  last_run?: string;
  last_status?: string;
}

/** 调度器整体状态 */
interface SchedulerState {
  enabled: boolean;
  maintenance_mode: boolean;
  tasks: SchedulerTask[];
}

export function Scheduler() {
  const [state, setState] = useState<SchedulerState>({
    enabled: true,
    maintenance_mode: false,
    tasks: [],
  });
  const [loading, setLoading] = useState(true);

  /** 从后端拉取调度器状态 */
  const fetchState = useCallback(async () => {
    try {
      const resp = await clawbotFetch('/api/v1/controls/scheduler');
      if (resp.ok) {
        const data = await resp.json();
        setState(data);
      }
    } catch (e) {
      schedulerLogger.warn('获取调度器状态失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  /** 挂载时拉取 + 每 30 秒自动刷新 */
  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 30000);
    return () => clearInterval(interval);
  }, [fetchState]);

  /** 切换调度器全局开关 */
  const toggleScheduler = async (enabled: boolean) => {
    setState(prev => ({ ...prev, enabled }));
    try {
      await clawbotFetch(`/api/v1/controls/scheduler/toggle?enabled=${enabled}`, { method: 'POST' });
      toast.success(enabled ? '调度器已启用' : '调度器已暂停');
    } catch {
      toast.error('操作失败');
    }
  };

  /** 切换单个任务的启用/禁用 */
  const toggleTask = async (taskId: string, enabled: boolean) => {
    setState(prev => ({
      ...prev,
      tasks: prev.tasks.map(t => t.id === taskId ? { ...t, enabled } : t),
    }));
    try {
      await clawbotFetch(`/api/v1/controls/scheduler/task/${taskId}/toggle?enabled=${enabled}`, { method: 'POST' });
    } catch {
      toast.error('切换失败');
    }
  };

  /** 根据任务状态返回对应图标 */
  const getStatusIcon = (status?: string) => {
    if (!status) return null;
    if (status === 'success') return <CheckCircle2 size={14} className="text-green-400" />;
    if (status === 'failed') return <XCircle size={14} className="text-red-400" />;
    if (status === 'running') return <Loader2 size={14} className="text-blue-400 animate-spin" />;
    return null;
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* 顶部标题栏：页面标题 + 刷新按钮 + 全局开关 */}
        <div className="flex items-center justify-between bg-dark-800/40 p-4 rounded-2xl border border-dark-600/50 backdrop-blur-sm">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Clock className="text-claw-400 h-6 w-6" />
              任务调度中心
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              管理每日自动任务：简报、监控、社媒、交易、数据维护
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={fetchState}
              className="p-2 rounded-lg bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white transition-colors"
              title="刷新"
            >
              <RefreshCw size={16} />
            </button>
            <div className="flex items-center gap-3 bg-dark-700/50 px-4 py-2 rounded-full border border-dark-600">
              {state.enabled ? (
                <Play size={14} className="text-green-400" />
              ) : (
                <Pause size={14} className="text-yellow-400" />
              )}
              <span className={clsx("text-sm font-medium", state.enabled ? "text-green-400" : "text-yellow-400")}>
                {state.enabled ? '运行中' : '已暂停'}
              </span>
              <Switch
                checked={state.enabled}
                onCheckedChange={toggleScheduler}
              />
            </div>
          </div>
        </div>

        {/* 维护模式横幅 */}
        {state.maintenance_mode && (
          <div className="flex items-center gap-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-4 py-3">
            <AlertTriangle size={18} className="text-yellow-400" />
            <span className="text-sm text-yellow-300">维护模式已开启 — 所有 Bot 消息处理已暂停，API 服务正常</span>
          </div>
        )}

        {/* 任务卡片网格 */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 9 }).map((_, i) => (
              <div key={i} className="h-28 bg-dark-800/50 rounded-xl border border-dark-700 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {state.tasks.map((task) => (
              <Card key={task.id} className={clsx(
                "bg-dark-800/80 border-dark-600 shadow-md transition-all overflow-hidden",
                !task.enabled && "opacity-50"
              )}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-white text-sm">{task.name}</h3>
                      <p className="text-xs text-gray-500 mt-0.5 font-mono">{task.cron}</p>
                    </div>
                    <Switch
                      checked={task.enabled}
                      onCheckedChange={(v) => toggleTask(task.id, v)}
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5 text-gray-500">
                      {getStatusIcon(task.last_status)}
                      <span>{task.last_run || '尚未执行'}</span>
                    </div>
                    <span className={clsx(
                      "px-2 py-0.5 rounded-full text-[10px] font-medium",
                      task.enabled ? "bg-green-500/10 text-green-400" : "bg-dark-700 text-gray-500"
                    )}>
                      {task.enabled ? '活跃' : '已禁用'}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* 底部说明 */}
        <div className="text-xs text-gray-600 text-center py-4">
          任务由后端 ExecutionScheduler 管理 · 每 30 秒自动刷新 · 时区标注 ET=美东 / 北京=中国标准时间
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import { Clock, RefreshCw, Pause, Play, AlertTriangle, CheckCircle2, XCircle, Loader2, Plus, Pencil, Trash2, ChevronDown, ChevronRight, History } from 'lucide-react';
import clsx from 'clsx';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
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
  description?: string;
}

/** 单条执行历史记录 */
interface ExecutionRecord {
  timestamp: string;
  status: 'success' | 'failed' | 'running';
  duration?: number;
}

/** 调度器整体状态 */
interface SchedulerState {
  enabled: boolean;
  maintenance_mode: boolean;
  tasks: SchedulerTask[];
}

/** 新建/编辑任务的表单数据 */
interface TaskFormData {
  name: string;
  scheduleType: 'cron' | 'interval';
  cron: string;
  intervalMinutes: number;
  description: string;
  enabled: boolean;
}

/** 表单初始值 */
const EMPTY_FORM: TaskFormData = {
  name: '',
  scheduleType: 'cron',
  cron: '0 9 * * *',
  intervalMinutes: 60,
  description: '',
  enabled: true,
};

export function Scheduler() {
  const [state, setState] = useState<SchedulerState>({
    enabled: true,
    maintenance_mode: false,
    tasks: [],
  });
  const [loading, setLoading] = useState(true);

  /* ── 新建/编辑对话框状态 ── */
  const [showFormDialog, setShowFormDialog] = useState(false);
  const [editingTask, setEditingTask] = useState<SchedulerTask | null>(null);
  const [form, setForm] = useState<TaskFormData>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  /* ── 删除确认对话框状态 ── */
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [pendingDeleteTask, setPendingDeleteTask] = useState<SchedulerTask | null>(null);
  const [deleting, setDeleting] = useState(false);

  /* ── 执行历史展开状态 ── */
  const [expandedHistoryIds, setExpandedHistoryIds] = useState<Set<string>>(new Set());
  const [historyMap, setHistoryMap] = useState<Record<string, ExecutionRecord[]>>({});
  const [historyLoadingIds, setHistoryLoadingIds] = useState<Set<string>>(new Set());

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

  /* ── 执行历史相关 ── */

  /** 切换某个任务的历史展开/折叠 */
  const toggleHistory = async (taskId: string) => {
    const next = new Set(expandedHistoryIds);
    if (next.has(taskId)) {
      next.delete(taskId);
      setExpandedHistoryIds(next);
      return;
    }
    next.add(taskId);
    setExpandedHistoryIds(next);

    /* 如果还没加载过该任务的历史，尝试拉取 */
    if (!historyMap[taskId]) {
      setHistoryLoadingIds(prev => new Set(prev).add(taskId));
      try {
        const resp = await clawbotFetch(`/api/v1/system/scheduler/history?task_id=${taskId}`);
        if (resp.ok) {
          const data = await resp.json();
          /* 后端可能返回 { records: [...] } 或直接数组 */
          const records: ExecutionRecord[] = Array.isArray(data) ? data : (data.records ?? []);
          setHistoryMap(prev => ({ ...prev, [taskId]: records.slice(0, 5) }));
        } else {
          /* 后端不支持历史接口时，从任务本身构建单条记录 */
          const task = state.tasks.find(t => t.id === taskId);
          if (task?.last_run) {
            setHistoryMap(prev => ({
              ...prev,
              [taskId]: [{
                timestamp: task.last_run!,
                status: (task.last_status as ExecutionRecord['status']) || 'success',
              }],
            }));
          } else {
            setHistoryMap(prev => ({ ...prev, [taskId]: [] }));
          }
        }
      } catch {
        /* 接口不存在，从当前任务数据降级 */
        const task = state.tasks.find(t => t.id === taskId);
        if (task?.last_run) {
          setHistoryMap(prev => ({
            ...prev,
            [taskId]: [{
              timestamp: task.last_run!,
              status: (task.last_status as ExecutionRecord['status']) || 'success',
            }],
          }));
        } else {
          setHistoryMap(prev => ({ ...prev, [taskId]: [] }));
        }
      } finally {
        setHistoryLoadingIds(prev => {
          const s = new Set(prev);
          s.delete(taskId);
          return s;
        });
      }
    }
  };

  /** 状态文字映射 */
  const statusLabel = (s: string) => {
    if (s === 'success') return '成功';
    if (s === 'failed') return '失败';
    if (s === 'running') return '运行中';
    return s;
  };

  /* ── 新建任务 ── */

  const openCreateDialog = () => {
    setEditingTask(null);
    setForm(EMPTY_FORM);
    setShowFormDialog(true);
  };

  /* ── 编辑任务 ── */

  const openEditDialog = (task: SchedulerTask) => {
    setEditingTask(task);
    setForm({
      name: task.name,
      scheduleType: 'cron',
      cron: task.cron,
      intervalMinutes: 60,
      description: task.description ?? '',
      enabled: task.enabled,
    });
    setShowFormDialog(true);
  };

  /** 提交新建或编辑表单 */
  const handleSubmitForm = async () => {
    if (!form.name.trim()) {
      toast.error('请填写任务名称');
      return;
    }
    setSubmitting(true);
    const cronValue = form.scheduleType === 'cron' ? form.cron : `*/${form.intervalMinutes} * * * *`;
    const payload = {
      name: form.name.trim(),
      cron: cronValue,
      enabled: form.enabled,
      description: form.description.trim(),
    };

    try {
      if (editingTask) {
        /* 编辑模式 */
        const resp = await clawbotFetch(`/api/v1/controls/scheduler/task/${editingTask.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          toast.success('任务已更新');
          setShowFormDialog(false);
          fetchState();
        } else {
          toast.error('后端暂不支持编辑操作');
        }
      } else {
        /* 新建模式 */
        const resp = await clawbotFetch('/api/v1/controls/scheduler/task', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          toast.success('任务已创建');
          setShowFormDialog(false);
          fetchState();
        } else {
          toast.error('后端暂不支持新建操作');
        }
      }
    } catch {
      toast.error('后端暂不支持此操作');
    } finally {
      setSubmitting(false);
    }
  };

  /* ── 删除任务 ── */

  const openDeleteConfirm = (task: SchedulerTask) => {
    setPendingDeleteTask(task);
    setConfirmDeleteOpen(true);
  };

  const handleDeleteTask = async () => {
    if (!pendingDeleteTask) return;
    setDeleting(true);
    try {
      const resp = await clawbotFetch(`/api/v1/controls/scheduler/task/${pendingDeleteTask.id}`, {
        method: 'DELETE',
      });
      if (resp.ok) {
        toast.success('任务已删除');
        setConfirmDeleteOpen(false);
        setPendingDeleteTask(null);
        fetchState();
      } else {
        toast.error('后端暂不支持删除操作');
      }
    } catch {
      toast.error('后端暂不支持删除操作');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* 顶部标题栏：页面标题 + 新建按钮 + 刷新按钮 + 全局开关 */}
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
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={openCreateDialog}>
              <Plus className="w-3.5 h-3.5" />
              <span className="hidden sm:inline ml-1">新建任务</span>
            </Button>
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
        ) : state.tasks.length === 0 ? (
          <div className="text-center py-16">
            <Clock className="w-10 h-10 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">暂无定时任务</p>
            <p className="text-gray-500 text-xs mt-1">点击上方「新建任务」添加</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {state.tasks.map((task) => {
              const isHistoryExpanded = expandedHistoryIds.has(task.id);
              const records = historyMap[task.id];
              const isHistoryLoading = historyLoadingIds.has(task.id);

              return (
                <Card key={task.id} className={clsx(
                  "bg-dark-800/80 border-dark-600 shadow-md transition-all overflow-hidden",
                  !task.enabled && "opacity-50"
                )}>
                  <CardContent className="p-4">
                    {/* 任务标题行：名称 + 操作按钮 */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1 min-w-0 mr-2">
                        <h3 className="font-semibold text-white text-sm truncate">{task.name}</h3>
                        <p className="text-xs text-gray-500 mt-0.5 font-mono">{task.cron}</p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {/* 编辑按钮 */}
                        <button
                          onClick={() => openEditDialog(task)}
                          className="p-1 rounded text-gray-500 hover:text-claw-400 hover:bg-claw-500/10 transition-colors"
                          title="编辑"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        {/* 删除按钮 */}
                        <button
                          onClick={() => openDeleteConfirm(task)}
                          className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        {/* 启用/禁用开关 */}
                        <Switch
                          checked={task.enabled}
                          onCheckedChange={(v) => toggleTask(task.id, v)}
                        />
                      </div>
                    </div>

                    {/* 状态行：上次执行 + 活跃标签 */}
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

                    {/* 执行历史折叠区域 */}
                    <div className="mt-3 pt-3 border-t border-dark-700/50">
                      <button
                        onClick={() => toggleHistory(task.id)}
                        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors w-full"
                      >
                        {isHistoryExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        <History size={12} />
                        <span>执行历史</span>
                      </button>

                      {isHistoryExpanded && (
                        <div className="mt-2 space-y-1.5">
                          {isHistoryLoading ? (
                            <div className="flex items-center gap-2 text-xs text-gray-500 py-2">
                              <Loader2 size={12} className="animate-spin" />
                              <span>加载中...</span>
                            </div>
                          ) : records && records.length > 0 ? (
                            records.map((rec, idx) => (
                              <div
                                key={idx}
                                className="flex items-center justify-between text-xs bg-dark-700/40 rounded-lg px-2.5 py-1.5"
                              >
                                <div className="flex items-center gap-1.5">
                                  {getStatusIcon(rec.status)}
                                  <span className={clsx(
                                    rec.status === 'success' ? 'text-green-400' :
                                    rec.status === 'failed' ? 'text-red-400' : 'text-blue-400'
                                  )}>
                                    {statusLabel(rec.status)}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2 text-gray-500">
                                  {rec.duration !== undefined && (
                                    <span>{rec.duration}ms</span>
                                  )}
                                  <span>{rec.timestamp}</span>
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-gray-600 py-1.5">暂无执行记录</p>
                          )}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* 底部说明 */}
        <div className="text-xs text-gray-600 text-center py-4">
          任务由后端 ExecutionScheduler 管理 · 每 30 秒自动刷新 · 时区标注 ET=美东 / 北京=中国标准时间
        </div>
      </div>

      {/* 新建/编辑任务对话框 */}
      <Dialog open={showFormDialog} onOpenChange={setShowFormDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingTask ? '编辑任务' : '新建任务'}</DialogTitle>
            <DialogDescription>
              {editingTask ? '修改定时任务的配置' : '创建一个新的定时任务'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* 任务名称 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">任务名称 *</label>
              <Input
                placeholder="例如：每日简报推送"
                value={form.name}
                onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>

            {/* 调度类型选择 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">调度方式</label>
              <div className="flex gap-2">
                <button
                  className={clsx(
                    "flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                    form.scheduleType === 'cron'
                      ? "border-claw-500/50 bg-claw-500/10 text-claw-400"
                      : "border-dark-600 bg-dark-700/50 text-gray-400 hover:text-gray-300"
                  )}
                  onClick={() => setForm(f => ({ ...f, scheduleType: 'cron' }))}
                >
                  Cron 表达式
                </button>
                <button
                  className={clsx(
                    "flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                    form.scheduleType === 'interval'
                      ? "border-claw-500/50 bg-claw-500/10 text-claw-400"
                      : "border-dark-600 bg-dark-700/50 text-gray-400 hover:text-gray-300"
                  )}
                  onClick={() => setForm(f => ({ ...f, scheduleType: 'interval' }))}
                >
                  固定间隔
                </button>
              </div>
            </div>

            {/* Cron 表达式 或 间隔分钟数 */}
            {form.scheduleType === 'cron' ? (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-300">Cron 表达式</label>
                <Input
                  placeholder="0 9 * * *"
                  value={form.cron}
                  onChange={(e) => setForm(f => ({ ...f, cron: e.target.value }))}
                  className="font-mono"
                />
                <p className="text-[11px] text-gray-500">格式：分 时 日 月 周（例如 0 9 * * * = 每天 9:00）</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-300">间隔时间（分钟）</label>
                <Input
                  type="number"
                  min={1}
                  placeholder="60"
                  value={String(form.intervalMinutes)}
                  onChange={(e) => setForm(f => ({ ...f, intervalMinutes: Math.max(1, Number(e.target.value) || 1) }))}
                />
              </div>
            )}

            {/* 描述 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">描述</label>
              <Input
                placeholder="任务的简要说明（可选）"
                value={form.description}
                onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
              />
            </div>

            {/* 启用状态 */}
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-300">创建后立即启用</label>
              <Switch
                checked={form.enabled}
                onCheckedChange={(v) => setForm(f => ({ ...f, enabled: v }))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFormDialog(false)}>
              取消
            </Button>
            <Button onClick={handleSubmitForm} disabled={submitting}>
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
              {editingTask ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <ConfirmDialog
        open={confirmDeleteOpen}
        onClose={() => {
          setConfirmDeleteOpen(false);
          setPendingDeleteTask(null);
        }}
        title="删除定时任务"
        description={`确定删除定时任务「${pendingDeleteTask?.name ?? ''}」？此操作不可撤销。`}
        onConfirm={handleDeleteTask}
        confirmText="删除"
        destructive={true}
        loading={deleting}
      />
    </div>
  );
}

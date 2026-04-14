import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { api } from '@/lib/tauri';
import {
  Code2, ListTodo, Settings, FileCode, Play, Loader2,
  Terminal, Cpu, HardDrive, MemoryStick, RefreshCw,
  ChevronDown, Info
} from 'lucide-react';
import { createLogger } from '@/lib/logger';

const devLogger = createLogger('Dev');

interface ActionStatus {
  running: boolean;
  lastResult?: string;
  error?: string;
}

interface SystemResources {
  cpu_load_1m?: number;
  memory_percent?: number;
  disk_used_percent?: number;
}

/** 卡片定义，增加用户友好的中文说明 */
interface ActionItem {
  id: string;
  label: string;
  /** 简短功能描述（显示在卡片标题下方） */
  desc: string;
  /** 给小白用户的通俗解释（显示在卡片底部） */
  hint: string;
  icon: typeof Code2;
  cmd: string;
  hasInput?: boolean;
  placeholder?: string;
}

/** 常用功能 — 默认展示 */
const primaryActions: ActionItem[] = [
  {
    id: 'config', label: '运行配置', icon: FileCode, cmd: '/config',
    desc: '查看当前系统运行配置',
    hint: '相当于看一下系统现在各项设置是什么样的',
  },
  {
    id: 'cost', label: '成本配额', icon: Terminal, cmd: '/cost',
    desc: '查看 API 调用成本与配额使用情况',
    hint: '看看今天花了多少钱、还剩多少额度',
  },
  {
    id: 'metrics', label: '运行指标', icon: Cpu, cmd: '/metrics',
    desc: '查看系统运行指标与健康状态',
    hint: '看看系统是否运行正常、有没有异常',
  },
];

/** 高级功能 — 默认折叠 */
const advancedActions: ActionItem[] = [
  {
    id: 'dev', label: '开发流程', icon: ListTodo, cmd: '/dev',
    desc: '进入开发/配置流程模式，管理开发任务',
    hint: '给开发者用的任务管理入口',
    hasInput: true, placeholder: '任务描述',
  },
  {
    id: 'ops', label: '高级入口', icon: Settings, cmd: '/ops',
    desc: '更多高级操作与系统管理入口',
    hint: '系统高级管理功能，一般不需要用',
  },
  {
    id: 'compact', label: '压缩上下文', icon: RefreshCw, cmd: '/compact',
    desc: '压缩对话上下文，释放 Token 空间',
    hint: 'AI 聊天记录太长时用来清理，释放空间',
  },
];

export function Dev() {
  const [statuses, setStatuses] = useState<Record<string, ActionStatus>>({});
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [resources, setResources] = useState<SystemResources | null>(null);
  /** 高级功能区域是否展开 */
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await invoke<SystemResources>('get_system_resources');
        setResources(res);
      } catch (e) { devLogger.debug('系统资源查询失败（Tauri命令可能尚未注册）', e); }
    };
    poll();
    const timer = setInterval(poll, 15000);
    return () => clearInterval(timer);
  }, []);

  const executeAction = async (actionId: string, cmd: string) => {
    const input = inputs[actionId] || '';
    const fullCmd = input ? `${cmd} ${input}` : cmd;

    setStatuses(prev => ({ ...prev, [actionId]: { running: true } }));
    try {
      const data = await api.omegaProcess(fullCmd);
      const result = data?.result || data?.response || '执行完成';
      setStatuses(prev => ({ ...prev, [actionId]: { running: false, lastResult: String(result) } }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatuses(prev => ({ ...prev, [actionId]: { running: false, error: msg } }));
    }
  };

  /** 进度条组件 */
  const resourceBar = (value: number | undefined, color: string) => {
    const pct = value ?? 0;
    return (
      <div className="w-full bg-dark-600 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    );
  };

  /** 渲染单个操作卡片 */
  const renderCard = (action: ActionItem) => {
    const Icon = action.icon;
    const status = statuses[action.id];
    return (
      <div key={action.id} className="bg-dark-700 rounded-xl border border-dark-500 p-5 hover:border-cyan-500/30 transition-colors group">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-lg bg-dark-600 flex items-center justify-center">
            <Icon size={18} className="text-cyan-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white">{action.label}</p>
            <code className="text-xs text-gray-500">{action.cmd}</code>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-1">{action.desc}</p>
        {/* 通俗说明 */}
        <p className="text-xs text-gray-500 mb-3 italic">{action.hint}</p>

        {action.hasInput && (
          <input
            type="text"
            placeholder={action.placeholder}
            value={inputs[action.id] || ''}
            onChange={(e) => setInputs(prev => ({ ...prev, [action.id]: e.target.value }))}
            className="w-full bg-dark-600 border border-dark-400 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500 mb-2 focus:outline-none focus:border-cyan-500/50"
            aria-label={action.label}
          />
        )}

        <button
          onClick={() => executeAction(action.id, action.cmd)}
          disabled={status?.running}
          className="w-full flex items-center justify-center gap-1.5 bg-dark-600 hover:bg-cyan-500/20 border border-dark-400 hover:border-cyan-500/40 rounded-lg px-3 py-1.5 text-xs text-gray-300 hover:text-cyan-300 transition-all disabled:opacity-50"
        >
          {status?.running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
          {status?.running ? '执行中...' : '执行'}
        </button>

        {status?.lastResult && !status.running && (
          <p className="text-xs text-green-400 mt-1.5 line-clamp-3 whitespace-pre-wrap">{status.lastResult}</p>
        )}
        {status?.error && !status.running && (
          <p className="text-xs text-red-400 mt-1.5 truncate">{status.error}</p>
        )}
      </div>
    );
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
        {/* 页面标题 */}
        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
          <div className="flex items-center gap-2 text-cyan-400 mb-2">
            <Code2 size={18} />
            <span className="text-sm font-medium">开发总控</span>
          </div>
          <h2 className="text-xl font-semibold text-white">开发与工程中心</h2>
          <p className="text-sm text-gray-400 mt-1">查看和管理系统运行状态</p>
        </div>

        {/* 使用指引提示框 */}
        <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-xl p-4 flex items-start gap-3">
          <Info size={16} className="text-cyan-400 mt-0.5 shrink-0" />
          <p className="text-xs text-cyan-300/80 leading-relaxed">
            这里可以查看和管理系统运行状态。点击卡片上的「执行」按钮即可运行对应操作。
            下方显示的是最常用的功能，更多高级功能可以点击底部展开。
          </p>
        </div>

        {/* 系统资源仪表盘 */}
        {resources && (
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-dark-700 rounded-xl border border-dark-500 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Cpu size={14} className="text-cyan-400" />
                <span className="text-xs text-gray-400">CPU 负载</span>
              </div>
              <p className="text-lg font-semibold text-white mb-1">{resources.cpu_load_1m?.toFixed(1) ?? '-'}</p>
              {resourceBar(resources.cpu_load_1m ? resources.cpu_load_1m * 10 : 0, 'bg-cyan-500')}
            </div>
            <div className="bg-dark-700 rounded-xl border border-dark-500 p-4">
              <div className="flex items-center gap-2 mb-2">
                <MemoryStick size={14} className="text-purple-400" />
                <span className="text-xs text-gray-400">内存</span>
              </div>
              <p className="text-lg font-semibold text-white mb-1">{resources.memory_percent?.toFixed(0) ?? '-'}%</p>
              {resourceBar(resources.memory_percent, 'bg-purple-500')}
            </div>
            <div className="bg-dark-700 rounded-xl border border-dark-500 p-4">
              <div className="flex items-center gap-2 mb-2">
                <HardDrive size={14} className="text-amber-400" />
                <span className="text-xs text-gray-400">磁盘</span>
              </div>
              <p className="text-lg font-semibold text-white mb-1">{resources.disk_used_percent?.toFixed(0) ?? '-'}%</p>
              {resourceBar(resources.disk_used_percent, 'bg-amber-500')}
            </div>
          </div>
        )}

        {/* 常用功能卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {primaryActions.map(renderCard)}
        </div>

        {/* 高级功能折叠区域 */}
        <div className="border border-dark-500 rounded-xl overflow-hidden">
          <button
            onClick={() => setShowAdvanced(prev => !prev)}
            className="w-full flex items-center justify-between px-5 py-3 bg-dark-700 hover:bg-dark-600 transition-colors text-sm text-gray-400 hover:text-gray-300"
            aria-expanded={showAdvanced}
          >
            <span>高级功能（开发者 / 不常用）</span>
            <motion.div animate={{ rotate: showAdvanced ? 180 : 0 }} transition={{ duration: 0.2 }}>
              <ChevronDown size={16} />
            </motion.div>
          </button>

          <AnimatePresence initial={false}>
            {showAdvanced && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: 'easeInOut' }}
                className="overflow-hidden"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-4 bg-dark-800/50">
                  {advancedActions.map(renderCard)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}

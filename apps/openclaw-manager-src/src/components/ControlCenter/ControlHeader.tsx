/**
 * 总控中心顶部头部 — 全局操作按钮 + 运行统计
 */
import { Loader2, Play, RefreshCw, RotateCcw, ShieldCheck, Square } from 'lucide-react';
import type { ControlHeaderProps } from './types';

export function ControlHeader({
  runningCount,
  totalServices,
  healthyEndpointsCount,
  totalEndpoints,
  refreshing,
  allActionLoading,
  onRefresh,
  onStartAll,
  onStopAll,
  onRestartAll,
}: ControlHeaderProps) {
  return (
    <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-claw-400 mb-2">
            <ShieldCheck size={18} />
            <span className="text-sm font-medium">最高权限总控中心</span>
          </div>
          <h2 className="text-xl font-semibold text-white">OpenClaw + ClawBot 总开关</h2>
          <p className="text-sm text-gray-400 mt-1">
            当前运行 {runningCount}/{totalServices} 个核心服务
          </p>
          <p className="text-sm text-gray-500 mt-0.5">
            链路连通 {healthyEndpointsCount}/{totalEndpoints}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* 刷新状态 */}
          <button
            onClick={onRefresh}
            disabled={refreshing || allActionLoading !== null}
            className="btn-secondary flex items-center gap-2"
          >
            {refreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            刷新状态
          </button>
          {/* 全部启动 */}
          <button
            onClick={onStartAll}
            disabled={allActionLoading !== null}
            className="btn-secondary flex items-center gap-2"
          >
            {allActionLoading === 'start' ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            全部启动
          </button>
          {/* 全部停止 */}
          <button
            onClick={onStopAll}
            disabled={allActionLoading !== null}
            className="btn-secondary flex items-center gap-2"
          >
            {allActionLoading === 'stop' ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} />}
            全部停止
          </button>
          {/* 全部重启 */}
          <button
            onClick={onRestartAll}
            disabled={allActionLoading !== null}
            className="btn-primary flex items-center gap-2"
          >
            {allActionLoading === 'restart' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <RotateCcw size={16} />
            )}
            全部重启
          </button>
        </div>
      </div>
    </div>
  );
}

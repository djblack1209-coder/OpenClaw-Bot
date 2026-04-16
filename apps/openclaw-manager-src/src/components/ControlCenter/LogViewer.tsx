/**
 * 统一日志观察窗 — 选择服务、自动刷新、日志渲染
 */
import { ChevronDown, Loader2, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { getLogLineClass } from './constants';
import type { LogViewerProps } from './types';

export function LogViewer({
  services,
  selectedLogLabel,
  onSelectLogLabel,
  serviceLogs,
  logsLoading,
  autoRefreshLogs,
  onToggleAutoRefresh,
  onRefreshLogs,
  logContainerRef,
}: LogViewerProps) {
  return (
    <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
      {/* 标题 + 控件 */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">统一日志观察窗</h3>
          <p className="text-xs text-gray-500 mt-0.5">可直接查看 OpenClaw / ClawBot 各核心服务日志</p>
        </div>
        <div className="flex items-center gap-2">
          {/* 服务选择下拉 */}
          <div className="relative">
            <select
              value={selectedLogLabel}
              onChange={(e) => onSelectLogLabel(e.target.value)}
              className="appearance-none bg-dark-800 border border-dark-600 rounded-lg px-3 py-2 pr-8 text-sm text-gray-200"
              aria-label="选择日志服务"
            >
              {services.map((service) => (
                <option key={service.label} value={service.label}>
                  {service.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
          </div>

          {/* 自动刷新开关 */}
          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={autoRefreshLogs}
              onChange={(e) => onToggleAutoRefresh(e.target.checked)}
              className="w-3 h-3 rounded"
            />
            自动刷新
          </label>

          {/* 手动刷新 */}
          <button
            onClick={onRefreshLogs}
            disabled={logsLoading}
            className="btn-secondary px-3 py-2 text-sm flex items-center gap-2"
          >
            {logsLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            刷新日志
          </button>
        </div>
      </div>

      {/* 日志内容区 */}
      <div ref={logContainerRef} className="h-72 overflow-y-auto rounded-xl bg-dark-800 border border-dark-600 p-3 font-mono text-xs">
        {logsLoading && serviceLogs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : serviceLogs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-500">暂无日志输出</div>
        ) : (
          <div className="space-y-1">
            {serviceLogs.map((line, index) => (
              <div key={`${index}-${line.slice(0, 24)}`} className={clsx('whitespace-pre-wrap break-all', getLogLineClass(line))}>
                {line}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

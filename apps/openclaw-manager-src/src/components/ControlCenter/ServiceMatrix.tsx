/**
 * 服务矩阵面板 — 服务状态卡片 + 链路连通性
 */
import { Activity, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import type { ServiceMatrixProps } from './types';

export function ServiceMatrix({
  services,
  endpoints,
  serviceActionLoading,
  onServiceAction,
  onStopService,
}: ServiceMatrixProps) {
  return (
    <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Activity size={18} className="text-accent-cyan" />
        <h3 className="text-lg font-semibold text-white">服务矩阵</h3>
      </div>

      {/* 服务状态卡片 */}
      <div className="space-y-3">
        {services.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-gray-500 text-sm bg-dark-800 rounded-xl border border-dark-600 border-dashed">
            暂无已注册服务
          </div>
        ) : services.map((service) => {
          const actionLoading = serviceActionLoading[service.label];
          return (
            <div
              key={service.label}
              className="bg-dark-800 rounded-xl border border-dark-600 p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-white">{service.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{service.label}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {service.running ? `运行中 · PID ${service.pid ?? '-'}` : '未运行'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={clsx(
                      'px-2 py-1 rounded-md text-xs border',
                      service.running
                        ? 'bg-green-500/10 text-green-300 border-green-500/30'
                        : 'bg-red-500/10 text-red-300 border-red-500/30'
                    )}
                  >
                    {service.running ? '运行中' : '已停止'}
                  </span>
                  <button
                    onClick={() => onServiceAction(service.label, 'start')}
                    disabled={!!actionLoading}
                    className="btn-secondary px-3 py-2 text-sm"
                  >
                    {actionLoading === 'start' ? <Loader2 size={14} className="animate-spin" /> : '启动'}
                  </button>
                  <button
                    onClick={() => onStopService(service.label)}
                    disabled={!!actionLoading}
                    className="btn-secondary px-3 py-2 text-sm"
                  >
                    {actionLoading === 'stop' ? <Loader2 size={14} className="animate-spin" /> : '停止'}
                  </button>
                  <button
                    onClick={() => onServiceAction(service.label, 'restart')}
                    disabled={!!actionLoading}
                    className="btn-primary px-3 py-2 text-sm"
                  >
                    {actionLoading === 'restart' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      '重启'
                    )}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 链路连通性 */}
      <div className="mt-5 pt-5 border-t border-dark-600">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={16} className="text-accent-green" />
          <p className="text-sm font-medium text-gray-300">链路连通性</p>
        </div>
        <div className="space-y-2">
          {endpoints.length === 0 ? (
            <div className="flex items-center justify-center py-6 text-gray-500 text-sm bg-dark-800 rounded-lg border border-dark-600 border-dashed">
              暂无链路端点
            </div>
          ) : endpoints.map((endpoint) => (
            <div
              key={endpoint.id}
              className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2 flex items-center justify-between gap-3"
            >
              <div>
                <p className="text-sm text-gray-200">{endpoint.name}</p>
                <p className="text-xs text-gray-500">{endpoint.address}</p>
              </div>
              <span
                className={clsx(
                  'px-2 py-1 rounded-md text-xs border',
                  endpoint.healthy
                    ? 'bg-green-500/10 text-green-300 border-green-500/30'
                    : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                )}
              >
                {endpoint.healthy ? '可达' : '不可达'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

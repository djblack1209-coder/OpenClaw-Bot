/**
 * 成本与配额快照面板 — 展示各服务商的用量信息
 */
import { getUsageProviderDetails, getUsageProviderName } from './constants';
import type { UsagePanelProps } from './types';

export function UsagePanel({ usageSnapshot, usageProviderCount }: UsagePanelProps) {
  return (
    <div className="mt-5 pt-5 border-t border-dark-600">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-sm font-medium text-gray-300">成本与配额快照</p>
        <span className="text-xs text-gray-500">可读配额服务商 {usageProviderCount}</span>
      </div>

      {usageProviderCount === 0 ? (
        <div className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-3 text-xs text-gray-500">
          当前没有可用的服务商配额快照（需要对应服务商支持 usage 接口，且本地凭据可读取）。
        </div>
      ) : (
        <div className="space-y-2">
          {usageSnapshot.providers.map((provider, index) => {
            const name = getUsageProviderName(provider);
            const details = getUsageProviderDetails(provider);
            return (
              <div
                key={`${name}-${index}`}
                className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2"
              >
                <p className="text-sm text-gray-200">{name}</p>
                <div className="mt-1 text-xs text-gray-500 space-y-0.5">
                  {details.length === 0 ? (
                    <p>暂无可展示指标</p>
                  ) : (
                    details.map((line) => <p key={line}>{line}</p>)
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-[11px] text-gray-500 mt-2">
        更新时间：{usageSnapshot.updatedAt ? new Date(usageSnapshot.updatedAt).toLocaleString('zh-CN', { hour12: false }) : '未知'}
      </p>
    </div>
  );
}

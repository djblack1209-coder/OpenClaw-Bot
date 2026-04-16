/**
 * 多 Bot 矩阵面板 — 展示所有 Bot 的状态和路由信息
 */
import clsx from 'clsx';
import type { BotMatrixProps } from './types';

export function BotMatrix({ botMatrix, readyBotCount }: BotMatrixProps) {
  return (
    <div className="mt-5 pt-5 border-t border-dark-600">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-sm font-medium text-gray-300">多 Bot 矩阵</p>
        <span className="text-xs text-gray-500">就绪 {readyBotCount}/{botMatrix.length}</span>
      </div>

      <div className="space-y-2">
        {botMatrix.length === 0 ? (
          <div className="flex items-center justify-center py-6 text-gray-500 text-sm bg-dark-800 rounded-lg border border-dark-600 border-dashed">
            暂无 Bot 配置
          </div>
        ) : botMatrix.map((bot) => (
          <div
            key={bot.id}
            className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm text-gray-200">{bot.name}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  @{bot.username || '-'} · {bot.route_provider}/{bot.route_model}
                </p>
                <p className="text-xs text-gray-500 mt-0.5 truncate">{bot.route_base_url || '未配置路由地址'}</p>
              </div>
              <div className="text-right">
                <span
                  className={clsx(
                    'px-2 py-1 rounded-md text-xs border',
                    bot.ready
                      ? 'bg-green-500/10 text-green-300 border-green-500/30'
                      : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  )}
                >
                  {bot.ready ? '就绪' : '等待中'}
                </span>
                <p className="text-[11px] text-gray-500 mt-1">Token: {bot.token_masked || '未配置'}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

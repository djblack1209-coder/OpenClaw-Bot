import { TrendingUp } from 'lucide-react';

/**
 * 我的资产 —— 投资交易中心
 * P3 阶段会替换为：持仓可视化 + AI 投票卡片 + 自动交易开关 + 回测 + 自选股
 */
export function Portfolio() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <div className="w-20 h-20 rounded-3xl bg-[var(--oc-success)]/10 flex items-center justify-center mx-auto mb-6">
          <TrendingUp size={36} className="text-[var(--oc-success)]" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">我的资产</h2>
        <p className="text-sm text-gray-400 max-w-md">
          IBKR 实盘持仓、AI 投票决策、自动交易开关、策略回测
        </p>
        <p className="text-xs text-gray-500 mt-4">Phase 3 实现完整功能</p>
      </div>
    </div>
  );
}

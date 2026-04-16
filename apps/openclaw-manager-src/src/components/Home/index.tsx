import { Home, Sun, TrendingUp, Bell, Zap } from 'lucide-react';
import { GlassCard } from '../shared';

/**
 * 首页 Dashboard —— C 端主页面
 * P1 阶段会替换为完整的今日简报 + 状态卡片 + 通知预览 + 快捷操作
 */
export function HomeDashboard() {
  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* 欢迎语 */}
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-[var(--oc-brand)]/10 flex items-center justify-center">
            <Home size={24} className="text-[var(--oc-brand)]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">早上好</h1>
            <p className="text-sm text-gray-400">这里是你的智能生活控制台</p>
          </div>
        </div>

        {/* 占位卡片网格 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <GlassCard>
            <div className="flex items-center gap-3 mb-3">
              <Sun size={18} className="text-[var(--oc-warning)]" />
              <span className="text-sm font-medium text-gray-300">今日简报</span>
            </div>
            <p className="text-xs text-gray-500">P1 阶段实现：天气、汇率、市场速览</p>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-3 mb-3">
              <TrendingUp size={18} className="text-[var(--oc-success)]" />
              <span className="text-sm font-medium text-gray-300">持仓速览</span>
            </div>
            <p className="text-xs text-gray-500">P1 阶段实现：总盈亏、持仓数量</p>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-3 mb-3">
              <Bell size={18} className="text-[var(--oc-brand)]" />
              <span className="text-sm font-medium text-gray-300">通知</span>
            </div>
            <p className="text-xs text-gray-500">P1 阶段实现：未读通知预览</p>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-3 mb-3">
              <Zap size={18} className="text-purple-400" />
              <span className="text-sm font-medium text-gray-300">快捷操作</span>
            </div>
            <p className="text-xs text-gray-500">P1 阶段实现：常用功能入口</p>
          </GlassCard>
        </div>

        {/* 空状态提示 */}
        <div className="text-center py-20 text-gray-500">
          <Home size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium">首页 Dashboard</p>
          <p className="text-sm mt-1">即将在 Phase 1 中实现完整功能</p>
        </div>
      </div>
    </div>
  );
}

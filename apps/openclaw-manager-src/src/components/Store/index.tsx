import { ShoppingBag } from 'lucide-react';

/**
 * 插件商店 —— MCP App Store
 * P5 阶段会替换为：App Store 风格插件浏览、安装、管理
 */
export function Store() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <div className="w-20 h-20 rounded-3xl bg-[var(--oc-brand)]/10 flex items-center justify-center mx-auto mb-6">
          <ShoppingBag size={36} className="text-[var(--oc-brand)]" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">插件商店</h2>
        <p className="text-sm text-gray-400 max-w-md">
          发现和安装新能力，让 AI 助手学会更多技能
        </p>
        <p className="text-xs text-gray-500 mt-4">Phase 5 实现完整功能</p>
      </div>
    </div>
  );
}

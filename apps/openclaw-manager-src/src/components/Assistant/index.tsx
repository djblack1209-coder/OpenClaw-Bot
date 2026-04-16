import { MessageSquare, Mic, Paperclip, Zap } from 'lucide-react';

/**
 * AI 助手 —— 对话界面
 * P2 阶段会替换为完整的三栏对话界面（历史/对话/状态面板）
 */
export function Assistant() {
  return (
    <div className="h-full flex flex-col">
      {/* 对话区域占位 */}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-20 h-20 rounded-3xl bg-[var(--oc-brand)]/10 flex items-center justify-center mx-auto mb-6">
            <MessageSquare size={36} className="text-[var(--oc-brand)]" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">AI 助手</h2>
          <p className="text-sm text-gray-400 max-w-md">
            用自然语言和 AI 对话，查行情、下单、管理闲鱼、发社媒，什么都能做
          </p>
          <p className="text-xs text-gray-500 mt-4">Phase 2 实现完整对话界面</p>
        </div>
      </div>

      {/* 底部输入区占位 */}
      <div className="border-t border-dark-600 p-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-2 bg-dark-700 rounded-2xl px-4 py-3 border border-dark-500">
            <input
              type="text"
              placeholder="输入消息..."
              className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none text-sm"
              disabled
            />
            <button className="p-2 text-gray-500 hover:text-gray-300" disabled>
              <Paperclip size={18} />
            </button>
            <button className="p-2 text-gray-500 hover:text-gray-300" disabled>
              <Mic size={18} />
            </button>
            <button className="p-2 text-gray-500 hover:text-gray-300" disabled>
              <Zap size={18} />
            </button>
          </div>
          <div className="flex items-center gap-2 mt-2 justify-center">
            {['投资分析', '发布内容', '闲鱼管理', '生活助手'].map((label) => (
              <button
                key={label}
                className="px-3 py-1 rounded-full bg-dark-700 text-xs text-gray-400 border border-dark-500"
                disabled
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

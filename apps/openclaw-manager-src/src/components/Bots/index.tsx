import { Bot } from 'lucide-react';

/**
 * 我的机器人 —— 自动化控制中心
 * P4 阶段会替换为：闲鱼AI客服 + 社媒自动驾驶 + 自动化脚本 + 通知中心
 */
export function Bots() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <div className="w-20 h-20 rounded-3xl bg-purple-500/10 flex items-center justify-center mx-auto mb-6">
          <Bot size={36} className="text-purple-400" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">我的机器人</h2>
        <p className="text-sm text-gray-400 max-w-md">
          闲鱼 AI 客服、社媒自动发布、赏金猎人、邮件管家，一键启停
        </p>
        <p className="text-xs text-gray-500 mt-4">Phase 4 实现完整功能</p>
      </div>
    </div>
  );
}

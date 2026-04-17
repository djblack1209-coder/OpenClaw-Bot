import { useState } from 'react';
import { Play, Square, RotateCw, FileText, Activity, Server, Terminal, Code, FolderTree } from 'lucide-react';

/**
 * DevPanel — 开发者工作台
 * 
 * AionUi Cowork 风格的三栏布局：
 * - 左侧：快捷面板（服务管理、Bot状态、开发工具）
 * - 中间：内嵌终端 + AI 对话框
 * - 右侧：项目文件树
 */

interface BotStatus {
  name: string;
  status: 'online' | 'offline';
}

export default function DevPanel() {
  const [botStatuses] = useState<BotStatus[]>([
    { name: 'qwen235b', status: 'online' },
    { name: 'gptoss', status: 'online' },
    { name: 'claude_sonnet', status: 'online' },
    { name: 'claude_haiku', status: 'online' },
    { name: 'deepseek_v3', status: 'online' },
    { name: 'claude_opus', status: 'online' },
    { name: 'free_llm', status: 'online' },
  ]);

  const [terminalOutput, setTerminalOutput] = useState<string[]>([
    'clawbot@mac:~/OpenClaw$ python multi_main.py',
    '[INFO] 2026-04-18 02:00:00 Bot 启动中...',
    '[INFO] 7 个 Bot 配置加载完成',
    '[INFO] FastAPI 监听 0.0.0.0:18790',
    '[INFO] Redis 连接成功',
    '[SUCCESS] 所有服务启动完成 ✓',
    'clawbot@mac:~/OpenClaw$ ',
  ]);

  const handleServiceAction = (action: string) => {
    setTerminalOutput(prev => [...prev, `执行: ${action}...`]);
    // TODO: 实际调用后端 API
  };

  return (
    <div className="flex h-screen bg-[#0D0F14] text-[#F0F3F8]">
      {/* 左侧快捷面板 */}
      <div className="w-60 bg-[#161B22] border-r border-[#1E2633] p-4 flex flex-col gap-6">
        {/* 服务管理 */}
        <div>
          <h3 className="text-sm font-medium text-[#8B99A8] mb-3">服务管理</h3>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleServiceAction('启动Bot')}
              className="flex items-center gap-2 px-3 py-2 bg-[#00D4FF]/10 hover:bg-[#00D4FF]/20 rounded-lg text-[#00D4FF] transition-colors"
            >
              <Play className="w-4 h-4" />
              <span className="text-sm">启动 Bot</span>
            </button>
            <button
              onClick={() => handleServiceAction('停止Bot')}
              className="flex items-center gap-2 px-3 py-2 bg-[#FF4B4B]/10 hover:bg-[#FF4B4B]/20 rounded-lg text-[#FF4B4B] transition-colors"
            >
              <Square className="w-4 h-4" />
              <span className="text-sm">停止 Bot</span>
            </button>
            <button
              onClick={() => handleServiceAction('重启')}
              className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors"
            >
              <RotateCw className="w-4 h-4" />
              <span className="text-sm">重启</span>
            </button>
            <button
              onClick={() => handleServiceAction('查看日志')}
              className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors"
            >
              <FileText className="w-4 h-4" />
              <span className="text-sm">查看日志</span>
            </button>
          </div>
        </div>

        {/* Bot 状态 */}
        <div>
          <h3 className="text-sm font-medium text-[#8B99A8] mb-3">Bot 状态</h3>
          <div className="flex flex-col gap-2">
            {botStatuses.map((bot) => (
              <div key={bot.name} className="flex items-center gap-2 text-sm">
                <div
                  className={`w-2 h-2 rounded-full ${
                    bot.status === 'online' ? 'bg-[#00C37D]' : 'bg-[#FF4B4B]'
                  }`}
                />
                <span className="text-[#F0F3F8]">{bot.name}</span>
                <span className="ml-auto text-xs text-[#8B99A8]">
                  {bot.status === 'online' ? '✓' : '✗'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 开发工具 */}
        <div>
          <h3 className="text-sm font-medium text-[#8B99A8] mb-3">开发工具</h3>
          <div className="flex flex-col gap-2">
            <button className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors text-sm">
              <Activity className="w-4 h-4" />
              <span>运行测试</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors text-sm">
              <Server className="w-4 h-4" />
              <span>查看指标</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors text-sm">
              <Code className="w-4 h-4" />
              <span>代码搜索</span>
            </button>
          </div>
        </div>
      </div>

      {/* 中间主区域 */}
      <div className="flex-1 flex flex-col">
        {/* 终端区域 (60%) */}
        <div className="flex-[3] bg-[#0D0F14] border-b border-[#1E2633] p-4">
          <div className="h-full bg-[#161B22] rounded-lg border border-[#1E2633] overflow-hidden">
            {/* 终端标签 */}
            <div className="flex items-center gap-2 px-4 py-2 bg-[#1E2633] border-b border-[#2A3649]">
              <Terminal className="w-4 h-4 text-[#00D4FF]" />
              <span className="text-sm font-medium">Shell</span>
              <span className="text-xs text-[#8B99A8] ml-auto">~/OpenClaw</span>
            </div>

            {/* 终端输出 */}
            <div className="p-4 font-mono text-sm overflow-y-auto h-[calc(100%-40px)]">
              {terminalOutput.map((line, i) => (
                <div key={i} className="text-[#F0F3F8] whitespace-pre-wrap">
                  {line}
                </div>
              ))}
              <div className="inline-block w-2 h-4 bg-[#00D4FF] animate-pulse" />
            </div>
          </div>
        </div>

        {/* AI 对话框区域 (40%) */}
        <div className="flex-[2] bg-[#0D0F14] p-4">
          <div className="h-full bg-[#161B22] rounded-lg border border-[#1E2633] flex flex-col">
            {/* 对话框标题 */}
            <div className="flex items-center gap-2 px-4 py-2 bg-[#1E2633] border-b border-[#2A3649]">
              <div className="w-2 h-2 rounded-full bg-[#00C37D]" />
              <span className="text-sm font-medium">AI 助手</span>
            </div>

            {/* 消息列表 */}
            <div className="flex-1 p-4 overflow-y-auto">
              <div className="flex flex-col gap-3">
                <div className="flex gap-2">
                  <div className="w-8 h-8 rounded-full bg-[#00D4FF]/20 flex items-center justify-center text-xs">
                    AI
                  </div>
                  <div className="flex-1 bg-[#1E2633] rounded-lg p-3 text-sm">
                    检测到你在运行 multi_main.py，需要帮你做什么？
                  </div>
                </div>
              </div>
            </div>

            {/* 输入框 */}
            <div className="p-4 border-t border-[#1E2633]">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="发送命令或描述你想做的事..."
                  className="flex-1 bg-[#1E2633] border border-[#2A3649] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#00D4FF] transition-colors"
                />
                <button className="px-4 py-2 bg-[#00D4FF] hover:bg-[#00D4FF]/80 rounded-lg text-sm font-medium transition-colors">
                  发送 ↵
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 右侧文件树 */}
      <div className="w-72 bg-[#161B22] border-l border-[#1E2633] p-4">
        <div className="flex items-center gap-2 mb-4">
          <FolderTree className="w-4 h-4 text-[#00D4FF]" />
          <h3 className="text-sm font-medium">项目结构</h3>
        </div>

        <div className="text-sm font-mono">
          <div className="flex flex-col gap-1">
            <div className="text-[#8B99A8]">OpenClaw/</div>
            <div className="pl-4">
              <div className="text-[#8B99A8]">├── packages/</div>
              <div className="pl-4">
                <div className="text-[#F0F3F8] hover:text-[#00D4FF] cursor-pointer">
                  └── clawbot/
                </div>
              </div>
            </div>
            <div className="pl-4">
              <div className="text-[#8B99A8]">├── apps/</div>
              <div className="pl-4">
                <div className="text-[#F0F3F8] hover:text-[#00D4FF] cursor-pointer">
                  └── openclaw-manager-src/
                </div>
              </div>
            </div>
            <div className="pl-4">
              <div className="text-[#8B99A8]">└── docs/</div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2">
          <button className="px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg text-sm transition-colors">
            📄 打开文件
          </button>
          <button className="px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg text-sm transition-colors">
            🔍 搜索
          </button>
          <button className="px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg text-sm transition-colors">
            📋 复制路径
          </button>
        </div>
      </div>
    </div>
  );
}

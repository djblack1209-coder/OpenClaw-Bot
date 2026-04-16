import { useState } from 'react';
import { PageType } from '../../App';
import { RefreshCw, ExternalLink, Loader2 } from 'lucide-react';
import { open } from '@tauri-apps/plugin-shell';
import { invoke } from '@tauri-apps/api/core';
import { createLogger } from '@/lib/logger';

// Header 组件日志记录器
const headerLogger = createLogger('Header');

interface HeaderProps {
  currentPage: PageType;
}

const pageTitles: Record<PageType, { title: string; description: string }> = {
  /* C 端新页面 */
  home: { title: '首页', description: '你的智能生活控制台' },
  assistant: { title: 'AI 助手', description: '用自然语言操控一切' },
  portfolio: { title: '我的资产', description: '持仓管理与 AI 投资决策' },
  bots: { title: '我的机器人', description: '闲鱼客服、社媒发布、自动化脚本' },
  store: { title: '插件商店', description: '发现和安装新能力' },
  /* 原有页面 */
  control: { title: '总控中心', description: '最高权限总开关与 ClawBot 关键配置' },
  dashboard: { title: '概览', description: '服务状态、日志与快捷操作' },
  flow: { title: '智能流监控', description: 'Agent 执行链路与决策过程可视化大屏' },
  memory: { title: '记忆脑图', description: '基于 Mem0 自动演进的长期记忆库' },
  plugins: { title: 'MCP 插件市场', description: '连接本地服务、数据库与外部协议能力' },
  ai: { title: 'AI 模型配置', description: '配置 AI 提供商和模型' },
  channels: { title: '消息渠道', description: '配置 Telegram、Discord、飞书等' },
  social: { title: '社媒总控', description: '发文、热点、人设、计划与自动运营' },
  money: { title: '盈利总控', description: '收入看板、Alpha 研究、风控与日报' },
  dev: { title: '开发总控', description: '开发任务、编码代理与 GitHub 操作' },
  testing: { title: '测试诊断', description: '系统诊断与问题排查' },
  logs: { title: '应用日志', description: '查看 OpenClaw 应用的控制台日志' },
  settings: { title: '设置', description: '身份配置与高级选项' },
  evolution: { title: '进化引擎', description: '追踪 GitHub Trending，自动发现升级机会' },
  gateway: { title: 'API 网关', description: 'New-API 渠道、令牌与网关状态管理' },
  scheduler: { title: '任务调度中心', description: '管理每日自动任务的启停与执行状态' },
};

export function Header({ currentPage }: HeaderProps) {
  const { title, description } = pageTitles[currentPage];
  const [opening, setOpening] = useState(false);

  const handleOpenDashboard = async () => {
    setOpening(true);
    try {
      // 获取带 token 的 Dashboard URL（如果没有 token 会自动生成）
      const url = await invoke<string>('get_dashboard_url');
      await open(url);
    } catch (e) {
      headerLogger.error('打开 Dashboard 失败:', e);
      // 降级方案：使用 window.open（不带 token），端口从环境变量读取
      const fallbackPort = import.meta.env.VITE_DASHBOARD_PORT || '18790';
      window.open(`http://localhost:${fallbackPort}`, '_blank');
    } finally {
      setOpening(false);
    }
  };

  return (
    <header className="h-14 bg-dark-800/50 border-b border-dark-600 flex items-center justify-between px-6 titlebar-drag backdrop-blur-sm">
      {/* 左侧：页面标题 */}
      <div className="titlebar-no-drag">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <p className="text-xs text-gray-500">{description}</p>
      </div>

      {/* 右侧：操作按钮 */}
      <div className="flex items-center gap-2 titlebar-no-drag">
        <button
          onClick={() => window.location.reload()}
          className="icon-button text-gray-400 hover:text-white"
          title="刷新"
          aria-label="刷新页面"
        >
          <RefreshCw size={16} />
        </button>
        <button
          onClick={handleOpenDashboard}
          disabled={opening}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-600 hover:bg-dark-500 text-sm text-gray-300 hover:text-white transition-colors disabled:opacity-50"
          title="打开 Web Dashboard"
        >
          {opening ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
          <span>控制面板</span>
        </button>
      </div>
    </header>
  );
}

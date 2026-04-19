import { useState, useEffect } from 'react';
import { PageType } from '../../App';
import { ExternalLink, Loader2 } from 'lucide-react';
import { open } from '@tauri-apps/plugin-shell';
import { invoke } from '@tauri-apps/api/core';
import { createLogger } from '@/lib/logger';
import { useAppStore } from '@/stores/appStore';

const headerLogger = createLogger('Header');

interface HeaderProps {
  currentPage: PageType;
}

/* 页面标题映射 */
const pageTitles: Record<PageType, { title: string; description: string }> = {
  home: { title: '首页', description: '系统总览控制台' },
  assistant: { title: 'AI 助手', description: '自然语言操控一切' },
  notifications: { title: '通知中心', description: '系统消息与告警' },
  portfolio: { title: '投资组合', description: '持仓管理与 AI 投资决策' },
  trading: { title: '交易引擎', description: '量化交易策略与回测' },
  risk: { title: '风险分析', description: 'Hurst 指数与风控仪表盘' },
  bots: { title: '我的机器人', description: '闲鱼客服、社媒发布、自动化脚本' },
  store: { title: 'Bot 商店', description: '发现和安装新能力' },
  xianyu: { title: '闲鱼管理', description: '商品、客服、Cookie 管理' },
  control: { title: '总控中心', description: '最高权限总开关' },
  dashboard: { title: '概览', description: '服务状态与快捷操作' },
  flow: { title: '智能流监控', description: 'Agent 执行链路可视化' },
  memory: { title: '记忆脑图', description: 'Mem0 长期记忆库' },
  plugins: { title: 'MCP 插件市场', description: '连接本地服务与外部协议' },
  ai: { title: 'AI 模型配置', description: '提供商和模型管理' },
  channels: { title: '消息渠道', description: 'Telegram / Discord / 飞书' },
  social: { title: '社媒总控', description: '发文、热点、人设与自动运营' },
  money: { title: '盈利总控', description: '收入看板、Alpha 研究与风控' },
  dev: { title: '开发总控', description: '开发任务与编码代理' },
  devpanel: { title: '开发者工作台', description: '终端 + AI 对话 + 文件树' },
  testing: { title: '测试诊断', description: '系统诊断与问题排查' },
  logs: { title: '应用日志', description: '控制台日志流' },
  settings: { title: '设置', description: '身份配置与高级选项' },
  evolution: { title: '进化引擎', description: '自动发现升级机会' },
  gateway: { title: 'API 网关', description: '渠道、令牌与网关管理' },
  scheduler: { title: '任务调度中心', description: '自动任务启停与执行状态' },
  perf: { title: '性能监控', description: '系统性能与资源实时分析' },
  onboarding: { title: '欢迎', description: '初始设置向导' },
};

export function Header({ currentPage }: HeaderProps) {
  const { title } = pageTitles[currentPage];
  const [opening, setOpening] = useState(false);
  const [clock, setClock] = useState('');
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const isRunning = serviceStatus?.running ?? false;

  /* 实时时钟 — 每秒更新 */
  useEffect(() => {
    const tick = () => {
      setClock(
        new Date().toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }),
      );
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  /* 打开 Web Dashboard */
  const handleOpenDashboard = async () => {
    setOpening(true);
    try {
      const url = await invoke<string>('get_dashboard_url');
      await open(url);
    } catch (e) {
      headerLogger.error('打开 Dashboard 失败:', e);
      const fallbackPort = import.meta.env.VITE_DASHBOARD_PORT || '18790';
      window.open(`http://localhost:${fallbackPort}`, '_blank');
    } finally {
      setOpening(false);
    }
  };

  return (
    <header
      className="h-12 flex items-center justify-between px-6 titlebar-drag"
      style={{
        background: 'rgba(2, 2, 2, 0.6)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--glass-border)',
      }}
    >
      {/* 左侧：页面标题 */}
      <div className="titlebar-no-drag flex items-center gap-3">
        <h2
          className="font-display font-bold text-base"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h2>
      </div>

      {/* 右侧：时钟 + 连接状态 + 控制面板按钮 */}
      <div className="flex items-center gap-4 titlebar-no-drag">
        {/* 实时时钟 */}
        <span
          className="font-mono tabular-nums text-xs tracking-wider"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {clock}
        </span>

        {/* 连接状态圆点 */}
        <div className="flex items-center gap-1.5">
          <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          <span
            className="font-mono text-[10px] uppercase tracking-wider"
            style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}
          >
            {isRunning ? 'CONNECTED' : 'OFFLINE'}
          </span>
        </div>

        {/* 控制面板按钮 */}
        <button
          onClick={handleOpenDashboard}
          disabled={opening}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg font-mono text-[11px] transition-all duration-200 disabled:opacity-50"
          style={{
            background: 'rgba(255,255,255,0.04)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--glass-border)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--glass-border-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--glass-border)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          title="打开 Web Dashboard"
        >
          {opening ? <Loader2 size={12} className="animate-spin" /> : <ExternalLink size={12} />}
          <span>控制面板</span>
        </button>
      </div>
    </header>
  );
}

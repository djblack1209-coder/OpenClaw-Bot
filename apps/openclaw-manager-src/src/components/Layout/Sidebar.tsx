import { motion } from 'framer-motion';
import {
  ShieldCheck,
  LayoutDashboard,
  Bot,
  MessageSquare,
  Share2,
  DollarSign,
  Code2,
  FlaskConical,
  ScrollText,
  Settings,
  Workflow,
  BrainCircuit,
  Blocks,
  Dna,
  Network,
  Clock
} from 'lucide-react';
import { PageType } from '../../App';
import clsx from 'clsx';

interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
}

interface SidebarProps {
  currentPage: PageType;
  onNavigate: (page: PageType) => void;
  serviceStatus: ServiceStatus | null;
}

const menuItems: { id: PageType; label: string; icon: React.ElementType }[] = [
  { id: 'control', label: '总控中心', icon: ShieldCheck },
  { id: 'dashboard', label: '概览', icon: LayoutDashboard },
  { id: 'flow', label: '智能流监控', icon: Workflow },
  { id: 'memory', label: '记忆脑图', icon: BrainCircuit },
  { id: 'plugins', label: 'MCP 插件市场', icon: Blocks },
  { id: 'ai', label: 'AI 配置', icon: Bot },
  { id: 'gateway' as PageType, label: 'API 网关', icon: Network },
  { id: 'channels', label: '消息渠道', icon: MessageSquare },
  { id: 'social', label: '社媒总控', icon: Share2 },
  { id: 'money', label: '盈利总控', icon: DollarSign },
  { id: 'evolution', label: '进化引擎', icon: Dna },
  { id: 'dev', label: '开发总控', icon: Code2 },
  { id: 'testing', label: '测试诊断', icon: FlaskConical },
  { id: 'logs', label: '应用日志', icon: ScrollText },
  { id: 'settings', label: '设置', icon: Settings },
];

export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const isRunning = serviceStatus?.running ?? false;

  return (
    <aside className="w-16 lg:w-64 transition-all duration-300 bg-dark-800 border-r border-dark-600 flex flex-col">
      {/* Logo 区域（macOS 标题栏拖拽） */}
      <div className="h-14 flex items-center px-2 lg:px-6 justify-center lg:justify-start titlebar-drag border-b border-dark-600">
        <div className="flex items-center gap-2 titlebar-no-drag">
          <span className="text-2xl">🦞</span>
          <span className="hidden lg:inline font-bold text-white tracking-wide">OpenClaw</span>
        </div>
      </div>

      {/* 服务状态迷你指示器 */}
      <div className="hidden lg:block px-6 py-4 border-b border-dark-600/50">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">服务状态</span>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              {isRunning && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>}
              <span className={clsx("relative inline-flex rounded-full h-2 w-2", isRunning ? "bg-green-500" : "bg-red-500")}></span>
            </span>
            <span className={clsx("text-xs font-medium", isRunning ? "text-green-500" : "text-red-500")}>
              {isRunning ? '在线' : '离线'}
            </span>
          </div>
        </div>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-4 px-3 overflow-y-auto scroll-container">
        <ul className="space-y-1">
          {menuItems.map((item) => {
            const isActive = currentPage === item.id;
            const Icon = item.icon;
            
            return (
              <li key={item.id}>
                <button
                  onClick={() => onNavigate(item.id)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all text-sm font-medium relative',
                    isActive
                      ? 'bg-claw-500/10 text-claw-400'
                      : 'text-gray-400 hover:bg-dark-700 hover:text-white'
                  )}
                >
                  {isActive && (
                    <motion.div
                      layoutId="activeIndicator"
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-claw-500 rounded-r-full"
                      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                    />
                  )}
                  <Icon size={18} className={clsx('transition-colors', isActive ? 'text-claw-400' : 'text-gray-500')} />
                  <span className="hidden lg:inline">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 底部信息 */}
      <div className="p-4 border-t border-dark-600">
        <div className="px-2 lg:px-4 py-3 bg-dark-700 rounded-lg flex items-center justify-center lg:block">
          <div className="flex items-center gap-2 lg:mb-2">
            <div className={clsx('status-dot', isRunning ? 'running' : 'stopped')} />
            <span className="hidden lg:inline text-xs text-gray-400">
              {isRunning ? '服务运行中' : '服务未启动'}
            </span>
          </div>
          <p className="hidden lg:block text-xs text-gray-500">端口: {serviceStatus?.port ?? 18790}</p>
        </div>
      </div>
    </aside>
  );
}

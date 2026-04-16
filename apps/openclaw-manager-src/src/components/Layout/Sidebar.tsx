import { motion } from 'framer-motion';
import {
  Home,
  MessageSquare,
  TrendingUp,
  Bot,
  ShoppingBag,
  Settings,
  ChevronLeft,
  ChevronRight,
  /* 开发者模式图标 */
  ShieldCheck,
  LayoutDashboard,
  Workflow,
  Clock,
  BrainCircuit,
  Blocks,
  Code2,
  FlaskConical,
  ScrollText,
  Share2,
  DollarSign,
  Dna,
  Network,
} from 'lucide-react';
import { PageType } from '../../App';
import { useAppStore } from '@/stores/appStore';
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

/* 菜单项定义 */
interface MenuItem {
  id: PageType;
  label: string;
  icon: React.ElementType;
}

/* C 端主导航（5 大分区） */
const consumerItems: MenuItem[] = [
  { id: 'home', label: '首页', icon: Home },
  { id: 'assistant', label: 'AI 助手', icon: MessageSquare },
  { id: 'portfolio', label: '我的资产', icon: TrendingUp },
  { id: 'bots', label: '我的机器人', icon: Bot },
  { id: 'store', label: '插件商店', icon: ShoppingBag },
];

/* 开发者模式追加项 */
const devItems: MenuItem[] = [
  { id: 'control', label: '总控中心', icon: ShieldCheck },
  { id: 'dashboard', label: '概览', icon: LayoutDashboard },
  { id: 'flow', label: '智能流监控', icon: Workflow },
  { id: 'scheduler', label: '任务调度', icon: Clock },
  { id: 'memory', label: '记忆脑图', icon: BrainCircuit },
  { id: 'plugins', label: 'MCP 插件', icon: Blocks },
  { id: 'ai', label: 'AI 配置', icon: Bot },
  { id: 'gateway', label: 'API 网关', icon: Network },
  { id: 'channels', label: '消息渠道', icon: MessageSquare },
  { id: 'social', label: '社媒总控', icon: Share2 },
  { id: 'money', label: '盈利总控', icon: DollarSign },
  { id: 'evolution', label: '进化引擎', icon: Dna },
  { id: 'dev', label: '开发总控', icon: Code2 },
  { id: 'testing', label: '测试诊断', icon: FlaskConical },
  { id: 'logs', label: '应用日志', icon: ScrollText },
];

/* 通用菜单项渲染 */
function NavItem({
  item,
  isActive,
  collapsed,
  onNavigate,
}: {
  item: MenuItem;
  isActive: boolean;
  collapsed: boolean;
  onNavigate: (page: PageType) => void;
}) {
  const Icon = item.icon;

  return (
    <li>
      <button
        onClick={() => onNavigate(item.id)}
        title={collapsed ? item.label : undefined}
        className={clsx(
          'w-full flex items-center gap-3 rounded-lg transition-all text-sm font-medium relative',
          collapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2',
          isActive
            ? 'bg-[var(--oc-sidebar-active)] text-[var(--oc-brand)]'
            : 'text-[var(--oc-sidebar-text-muted)] hover:bg-dark-700 hover:text-[var(--oc-sidebar-text)]'
        )}
      >
        {/* 左侧激活指示条 */}
        {isActive && (
          <motion.div
            layoutId="activeIndicator"
            className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-[var(--oc-brand)] rounded-r-full"
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          />
        )}
        <Icon
          size={18}
          className={clsx(
            'transition-colors flex-shrink-0',
            isActive ? 'text-[var(--oc-brand)]' : 'text-[var(--oc-sidebar-text-muted)]'
          )}
        />
        {!collapsed && <span>{item.label}</span>}
      </button>
    </li>
  );
}

export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const isRunning = serviceStatus?.running ?? false;
  const devMode = useAppStore((s) => s.devMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      className={clsx(
        'transition-all duration-300 bg-[var(--oc-sidebar-bg)] border-r border-dark-600 flex flex-col',
        sidebarCollapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Logo 区域（macOS 标题栏拖拽） */}
      <div className="h-14 flex items-center px-2 justify-center titlebar-drag border-b border-dark-600">
        <div className="flex items-center gap-2 titlebar-no-drag">
          <span className="text-2xl">🦞</span>
          {!sidebarCollapsed && (
            <span className="font-bold text-[var(--oc-sidebar-text)] tracking-wide">OpenClaw</span>
          )}
        </div>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-4 px-3 overflow-y-auto scroll-container">
        {/* C 端主导航 */}
        <ul className="space-y-1">
          {consumerItems.map((item) => (
            <NavItem
              key={item.id}
              item={item}
              isActive={currentPage === item.id}
              collapsed={sidebarCollapsed}
              onNavigate={onNavigate}
            />
          ))}
        </ul>

        {/* 开发者模式区域 */}
        {devMode && (
          <>
            <div className="my-4 border-t border-dark-600/50" />
            {!sidebarCollapsed && (
              <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-[var(--oc-sidebar-text-muted)]">
                开发者工具
              </p>
            )}
            <ul className="space-y-1">
              {devItems.map((item) => (
                <NavItem
                  key={item.id}
                  item={item}
                  isActive={currentPage === item.id}
                  collapsed={sidebarCollapsed}
                  onNavigate={onNavigate}
                />
              ))}
            </ul>
          </>
        )}

        {/* 设置（始终显示，在最后） */}
        <div className="mt-4 border-t border-dark-600/50 pt-4">
          <ul>
            <NavItem
              item={{ id: 'settings', label: '设置', icon: Settings }}
              isActive={currentPage === 'settings'}
              collapsed={sidebarCollapsed}
              onNavigate={onNavigate}
            />
          </ul>
        </div>
      </nav>

      {/* 底部：服务状态 + 折叠按钮 */}
      <div className="p-3 border-t border-dark-600">
        {/* 服务状态 */}
        <div className={clsx(
          'px-2 py-2 bg-dark-700 rounded-lg flex items-center mb-2',
          sidebarCollapsed ? 'justify-center' : 'gap-2'
        )}>
          <span className="relative flex h-2 w-2 flex-shrink-0">
            {isRunning && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--oc-success)] opacity-75" />
            )}
            <span
              className={clsx(
                'relative inline-flex rounded-full h-2 w-2',
                isRunning ? 'bg-[var(--oc-success)]' : 'bg-[var(--oc-danger)]'
              )}
            />
          </span>
          {!sidebarCollapsed && (
            <span className={clsx('text-xs font-medium', isRunning ? 'text-[var(--oc-success)]' : 'text-[var(--oc-danger)]')}>
              {isRunning ? '服务运行中' : '服务未启动'}
            </span>
          )}
        </div>

        {/* 折叠/展开按钮 */}
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center py-1.5 rounded-lg text-[var(--oc-sidebar-text-muted)] hover:bg-dark-700 transition-colors"
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}

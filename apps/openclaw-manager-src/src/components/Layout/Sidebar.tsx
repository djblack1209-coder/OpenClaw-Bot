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
  Terminal,
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

/* 导航分组定义 */
interface NavGroup {
  label: string;
  items: MenuItem[];
}

/* ===== C 端主导航（5 大分区）===== */
const consumerItems: MenuItem[] = [
  { id: 'home', label: '首页', icon: Home },
  { id: 'assistant', label: 'AI 助手', icon: MessageSquare },
  { id: 'portfolio', label: '我的资产', icon: TrendingUp },
  { id: 'bots', label: '我的机器人', icon: Bot },
  { id: 'store', label: '插件商店', icon: ShoppingBag },
];

/* ===== 开发者模式 - 按职能分组 ===== */
const devGroups: NavGroup[] = [
  {
    label: '系统管控',
    items: [
      { id: 'control', label: '总控中心', icon: ShieldCheck },
      { id: 'dashboard', label: '概览', icon: LayoutDashboard },
      { id: 'gateway', label: 'API 网关', icon: Network },
      { id: 'scheduler', label: '任务调度', icon: Clock },
    ],
  },
  {
    label: '业务运营',
    items: [
      { id: 'channels', label: '消息渠道', icon: MessageSquare },
      { id: 'social', label: '社媒总控', icon: Share2 },
      { id: 'money', label: '盈利总控', icon: DollarSign },
      { id: 'ai', label: 'AI 配置', icon: Bot },
      { id: 'plugins', label: 'MCP 插件', icon: Blocks },
      { id: 'memory', label: '记忆脑图', icon: BrainCircuit },
    ],
  },
  {
    label: '开发调试',
    items: [
      { id: 'flow', label: '智能流监控', icon: Workflow },
      { id: 'evolution', label: '进化引擎', icon: Dna },
      { id: 'dev', label: '开发总控', icon: Code2 },
      { id: 'devpanel', label: '开发者工作台', icon: Terminal },
      { id: 'testing', label: '测试诊断', icon: FlaskConical },
      { id: 'logs', label: '应用日志', icon: ScrollText },
    ],
  },
];

/* ===== 通用菜单项渲染 ===== */
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
          'group w-full flex items-center gap-3 rounded-lg transition-all duration-200 text-sm font-medium relative',
          collapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2',
          isActive
            ? 'bg-[var(--brand-500)]/10 text-[var(--brand-500)]'
            : 'text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]'
        )}
      >
        {/* 左侧激活指示条 — TradingView 风格：细长青色竖条 */}
        {isActive && (
          <motion.div
            layoutId="activeIndicator"
            className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
            style={{ background: 'var(--brand-500)' }}
            transition={{ type: 'spring', stiffness: 350, damping: 30 }}
          />
        )}
        <Icon
          size={18}
          className={clsx(
            'transition-colors duration-200 flex-shrink-0',
            isActive
              ? 'text-[var(--brand-500)]'
              : 'text-[var(--text-tertiary)] group-hover:text-[var(--text-secondary)]'
          )}
        />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </button>
    </li>
  );
}

/* ===== 分组标签渲染 ===== */
function GroupLabel({ label, collapsed }: { label: string; collapsed: boolean }) {
  if (collapsed) {
    /* 折叠态：用一条短横线代替文字 */
    return (
      <div className="flex justify-center py-2">
        <div className="w-4 h-px bg-[var(--border-medium)]" />
      </div>
    );
  }

  return (
    <div className="px-3 pt-4 pb-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-disabled)]">
        {label}
      </span>
    </div>
  );
}

/* ===== 分隔线 ===== */
function Divider() {
  return <div className="my-2 mx-3 h-px bg-[var(--border-light)]" />;
}

export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const isRunning = serviceStatus?.running ?? false;
  const devMode = useAppStore((s) => s.devMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      className={clsx(
        'transition-all duration-300 flex flex-col border-r',
        'bg-[var(--bg-secondary)] border-[var(--border-default)]',
        sidebarCollapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* ===== Logo 区域（macOS 标题栏拖拽）===== */}
      <div className="h-14 flex items-center px-2 justify-center titlebar-drag border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2 titlebar-no-drag">
          <span className="text-2xl">🦞</span>
          {!sidebarCollapsed && (
            <span className="font-bold text-[var(--text-primary)] tracking-wide">OpenClaw</span>
          )}
        </div>
      </div>

      {/* ===== 导航菜单 ===== */}
      <nav className="flex-1 py-3 px-2 overflow-y-auto scroll-container">
        {/* — C 端主导航 — */}
        <ul className="space-y-0.5">
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

        {/* — 开发者模式分组区域 — */}
        {devMode && (
          <>
            <Divider />
            {devGroups.map((group, groupIndex) => (
              <div key={group.label}>
                {/* 非首个分组前加分隔线 */}
                {groupIndex > 0 && <Divider />}
                <GroupLabel label={group.label} collapsed={sidebarCollapsed} />
                <ul className="space-y-0.5">
                  {group.items.map((item) => (
                    <NavItem
                      key={item.id}
                      item={item}
                      isActive={currentPage === item.id}
                      collapsed={sidebarCollapsed}
                      onNavigate={onNavigate}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </>
        )}

        {/* — 设置（始终显示，在最后）— */}
        <Divider />
        <ul>
          <NavItem
            item={{ id: 'settings', label: '设置', icon: Settings }}
            isActive={currentPage === 'settings'}
            collapsed={sidebarCollapsed}
            onNavigate={onNavigate}
          />
        </ul>
      </nav>

      {/* ===== 底部：服务状态 + 折叠按钮 ===== */}
      <div className="p-2 border-t border-[var(--border-default)]">
        {/* 服务状态指示器 */}
        <div
          className={clsx(
            'px-2 py-2 rounded-lg flex items-center',
            'bg-[var(--bg-tertiary)]',
            sidebarCollapsed ? 'justify-center' : 'gap-2'
          )}
        >
          {/* 状态圆点 + 呼吸动画 */}
          <span className="relative flex h-2 w-2 flex-shrink-0">
            {isRunning && (
              <span
                className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                style={{ background: 'var(--oc-success)' }}
              />
            )}
            <span
              className="relative inline-flex rounded-full h-2 w-2"
              style={{ background: isRunning ? 'var(--oc-success)' : 'var(--oc-danger)' }}
            />
          </span>
          {!sidebarCollapsed && (
            <span
              className="text-xs font-medium"
              style={{ color: isRunning ? 'var(--oc-success)' : 'var(--oc-danger)' }}
            >
              {isRunning ? '服务运行中' : '服务未启动'}
            </span>
          )}
        </div>

        {/* 折叠/展开按钮 */}
        <button
          onClick={toggleSidebar}
          className={clsx(
            'w-full flex items-center justify-center py-1.5 mt-1.5 rounded-lg transition-colors duration-200',
            'text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-secondary)]'
          )}
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}

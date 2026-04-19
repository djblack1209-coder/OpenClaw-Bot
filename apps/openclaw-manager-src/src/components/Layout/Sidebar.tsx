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
  Gauge,
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

/* ===== C 端主导航（5 大分区） ===== */
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
      { id: 'perf', label: '性能监控', icon: Gauge },
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

/* ===== 导航项渲染 ===== */
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
          'group w-full flex items-center gap-3 rounded-lg transition-all duration-200 relative',
          collapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2',
        )}
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          textTransform: 'uppercase' as const,
          letterSpacing: '0.5px',
          color: isActive ? 'var(--accent-cyan)' : 'var(--text-tertiary)',
          background: isActive ? 'rgba(0, 212, 255, 0.06)' : 'transparent',
        }}
        onMouseEnter={(e) => {
          if (!isActive) {
            e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isActive) {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }
        }}
      >
        {/* 左侧激活指示条 — 3px 青色竖条 */}
        {isActive && (
          <motion.div
            layoutId="activeIndicator"
            className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
            style={{ background: 'var(--accent-cyan)' }}
            transition={{ type: 'spring', stiffness: 350, damping: 30 }}
          />
        )}
        <Icon
          size={16}
          className="flex-shrink-0 transition-colors duration-200"
          style={{
            color: isActive ? 'var(--accent-cyan)' : undefined,
          }}
        />
        {!collapsed && (
          <span className="truncate">{item.label}</span>
        )}
      </button>
    </li>
  );
}

/* ===== 分组标签渲染 ===== */
function GroupLabel({ label, collapsed }: { label: string; collapsed: boolean }) {
  if (collapsed) {
    return (
      <div className="flex justify-center py-2">
        <div className="w-4 h-px" style={{ background: 'var(--glass-border)' }} />
      </div>
    );
  }

  return (
    <div className="px-3 pt-4 pb-1.5">
      <span
        className="font-mono uppercase"
        style={{
          fontSize: '10px',
          letterSpacing: '1.5px',
          color: 'var(--text-disabled)',
        }}
      >
        {label}
      </span>
    </div>
  );
}

/* ===== 分隔线 ===== */
function Divider() {
  return <div className="my-2 mx-3 h-px" style={{ background: 'var(--glass-border)' }} />;
}

export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const isRunning = serviceStatus?.running ?? false;
  const port = serviceStatus?.port ?? 18790;
  const devMode = useAppStore((s) => s.devMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      className={clsx(
        'transition-all duration-300 flex flex-col',
        sidebarCollapsed ? 'w-14' : 'w-60'
      )}
      style={{
        background: 'transparent',
        borderRight: '1px solid var(--glass-border)',
      }}
    >
      {/* ===== Logo 区域（macOS 标题栏拖拽）===== */}
      <div
        className="h-14 flex items-center px-3 titlebar-drag"
        style={{ borderBottom: '1px solid var(--glass-border)' }}
      >
        <div className="flex items-center gap-1.5 titlebar-no-drag">
          {!sidebarCollapsed ? (
            <>
              <span
                className="font-display font-black tracking-wide"
                style={{ fontSize: '15px', color: 'var(--text-primary)' }}
              >
                OPENCLAW
              </span>
              <span
                className="font-display font-black tracking-wide"
                style={{ fontSize: '15px', color: 'var(--accent-cyan)' }}
              >
                MANAGER
              </span>
            </>
          ) : (
            <span
              className="font-display font-black"
              style={{ fontSize: '15px', color: 'var(--accent-cyan)' }}
            >
              OC
            </span>
          )}
        </div>
      </div>

      {/* ===== 导航菜单 ===== */}
      <nav className="flex-1 py-3 px-2 overflow-y-auto scroll-container">
        {/* C 端主导航 */}
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

        {/* 开发者模式分组 */}
        {devMode && (
          <>
            <Divider />
            {devGroups.map((group, groupIndex) => (
              <div key={group.label}>
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

        {/* 设置（始终显示） */}
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

      {/* ===== 底部：状态栏 + 折叠按钮 ===== */}
      <div className="px-2 pb-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
        {/* WebSocket 状态指示器 */}
        <div
          className={clsx(
            'flex items-center py-2 mt-2 rounded-lg',
            sidebarCollapsed ? 'justify-center px-1' : 'gap-2 px-2'
          )}
        >
          <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          {!sidebarCollapsed && (
            <span
              className="font-mono text-[10px] tracking-wider"
              style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}
            >
              WS: {port} / {isRunning ? 'ONLINE' : 'OFFLINE'}
            </span>
          )}
        </div>

        {/* 折叠/展开按钮 */}
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center py-1.5 mt-1 rounded-lg transition-colors duration-200"
          style={{ color: 'var(--text-tertiary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }}
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </aside>
  );
}

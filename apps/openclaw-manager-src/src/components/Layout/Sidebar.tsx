import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Home,
  MessageSquare,
  TrendingUp,
  Bot,
  ShoppingBag,
  Settings,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Search,
  Bell,
  /* 新增导航图标 */
  Wallet,
  LineChart,
  ShieldAlert,
  Fish,
  Globe,
  BarChart3,
  HelpCircle,
  User,
  Zap,
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
  Activity,
  AlertCircle,
} from 'lucide-react';
import { PageType } from '../../App';
import { useAppStore } from '@/stores/appStore';
import clsx from 'clsx';

/* ===== 类型定义 ===== */
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

interface MenuItem {
  id: PageType;
  label: string;
  icon: React.ElementType;
  badge?: string | number;       /* 角标文本/数字 */
  badgeColor?: string;           /* 角标颜色 */
  description?: string;          /* 鼠标悬停提示 */
}

interface NavGroup {
  id: string;
  label: string;
  icon?: React.ElementType;
  items: MenuItem[];
  defaultOpen?: boolean;
}

/* ===== C 端导航分组（丰富版） ===== */
const consumerGroups: NavGroup[] = [
  {
    id: 'workspace',
    label: '工作台',
    icon: Zap,
    defaultOpen: true,
    items: [
      { id: 'home', label: '首页总览', icon: Home, description: '系统全局状态概览' },
      { id: 'assistant', label: 'AI 助手', icon: MessageSquare, description: '对话式 AI 开发工作台' },
      { id: 'notifications', label: '通知中心', icon: Bell, description: '系统消息与告警' },
    ],
  },
  {
    id: 'assets',
    label: '资产管理',
    icon: Wallet,
    defaultOpen: true,
    items: [
      { id: 'portfolio', label: '投资组合', icon: TrendingUp, description: '持仓与 AI 决策' },
      { id: 'trading', label: '交易引擎', icon: LineChart, description: '量化交易与回测' },
      { id: 'risk', label: '风险分析', icon: ShieldAlert, description: 'Hurst 指数与风控' },
    ],
  },
  {
    id: 'agents',
    label: '智能体',
    icon: Bot,
    defaultOpen: true,
    items: [
      { id: 'bots', label: '我的机器人', icon: Bot, description: '管理所有 Bot 实例' },
      { id: 'store', label: 'Bot 商店', icon: ShoppingBag, description: '发现和安装新 Bot' },
    ],
  },
  {
    id: 'operations',
    label: '运营中心',
    icon: Globe,
    defaultOpen: true,
    items: [
      { id: 'xianyu', label: '闲鱼管理', icon: Fish, description: '商品、客服、Cookie' },
      { id: 'social', label: '社交媒体', icon: Share2, description: '多平台社媒运营' },
      { id: 'money', label: '收益统计', icon: BarChart3, description: '收入看板与报表' },
    ],
  },
];

/* ===== 开发者模式分组 ===== */
const devGroups: NavGroup[] = [
  {
    id: 'dev-system',
    label: '系统管控',
    icon: ShieldCheck,
    defaultOpen: false,
    items: [
      { id: 'control', label: '总控中心', icon: ShieldCheck },
      { id: 'dashboard', label: '概览面板', icon: LayoutDashboard },
      { id: 'gateway', label: 'API 网关', icon: Network },
      { id: 'scheduler', label: '任务调度', icon: Clock },
      { id: 'perf', label: '性能监控', icon: Gauge },
    ],
  },
  {
    id: 'dev-business',
    label: '业务运营',
    icon: DollarSign,
    defaultOpen: false,
    items: [
      { id: 'channels', label: '消息渠道', icon: MessageSquare },
      { id: 'ai', label: 'AI 配置', icon: Bot },
      { id: 'plugins', label: 'MCP 插件', icon: Blocks },
      { id: 'memory', label: '记忆脑图', icon: BrainCircuit },
    ],
  },
  {
    id: 'dev-debug',
    label: '开发调试',
    icon: Code2,
    defaultOpen: false,
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

/* ===== 可折叠分组组件 ===== */
function CollapsibleGroup({
  group,
  currentPage,
  collapsed,
  onNavigate,
  notifications,
}: {
  group: NavGroup;
  currentPage: PageType;
  collapsed: boolean;
  onNavigate: (page: PageType) => void;
  notifications?: Record<string, number>;
}) {
  /* 如果当前页在分组内，自动展开 */
  const hasActivePage = group.items.some((item) => item.id === currentPage);
  const [isOpen, setIsOpen] = useState(group.defaultOpen ?? hasActivePage);

  /* 当活动页切换到本组时自动展开 */
  useEffect(() => {
    if (hasActivePage && !isOpen) setIsOpen(true);
  }, [hasActivePage]);

  /* 折叠模式下不显示分组标题 */
  if (collapsed) {
    return (
      <div className="space-y-0.5">
        {group.items.map((item) => (
          <NavItem
            key={item.id}
            item={item}
            isActive={currentPage === item.id}
            collapsed
            onNavigate={onNavigate}
            notificationCount={notifications?.[item.id]}
          />
        ))}
      </div>
    );
  }

  const GroupIcon = group.icon;

  return (
    <div className="mb-1">
      {/* 分组标题（可点击折叠） */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 px-3 py-1.5 rounded-md transition-colors duration-150 group"
        style={{ color: 'var(--text-disabled)' }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--text-tertiary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-disabled)';
        }}
      >
        {GroupIcon && <GroupIcon size={11} className="flex-shrink-0 opacity-60" />}
        <span
          className="font-mono uppercase flex-1 text-left"
          style={{ fontSize: '10px', letterSpacing: '1.2px' }}
        >
          {group.label}
        </span>
        <ChevronDown
          size={10}
          className={clsx(
            'flex-shrink-0 transition-transform duration-200 opacity-40',
            !isOpen && '-rotate-90',
          )}
        />
      </button>

      {/* 分组内容（折叠动画） */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden space-y-0.5"
          >
            {group.items.map((item) => (
              <NavItem
                key={item.id}
                item={item}
                isActive={currentPage === item.id}
                collapsed={false}
                onNavigate={onNavigate}
                notificationCount={notifications?.[item.id]}
              />
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ===== 导航项渲染 ===== */
function NavItem({
  item,
  isActive,
  collapsed,
  onNavigate,
  notificationCount,
}: {
  item: MenuItem;
  isActive: boolean;
  collapsed: boolean;
  onNavigate: (page: PageType) => void;
  notificationCount?: number;
}) {
  const Icon = item.icon;
  const badgeText = item.badge ?? (notificationCount && notificationCount > 0 ? notificationCount : null);

  return (
    <li>
      <button
        onClick={() => onNavigate(item.id)}
        title={collapsed ? item.label : item.description}
        className={clsx(
          'group w-full flex items-center gap-2.5 rounded-lg transition-all duration-200 relative',
          collapsed ? 'px-0 py-2 justify-center' : 'px-3 py-[7px]',
        )}
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: '13px',
          fontWeight: isActive ? 500 : 400,
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          background: isActive ? 'rgba(0, 212, 255, 0.08)' : 'transparent',
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
            e.currentTarget.style.color = 'var(--text-secondary)';
          }
        }}
      >
        {/* 左侧激活指示条 */}
        {isActive && (
          <motion.div
            layoutId="sidebarActiveIndicator"
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
            opacity: isActive ? 1 : 0.7,
          }}
        />
        {!collapsed && (
          <>
            <span className="flex-1 truncate text-left">{item.label}</span>
            {/* 角标 */}
            {badgeText != null && (
              <span
                className="flex-shrink-0 min-w-[18px] h-[18px] flex items-center justify-center rounded-full font-mono text-[10px] font-medium"
                style={{
                  background: item.badgeColor ?? 'rgba(0, 212, 255, 0.2)',
                  color: item.badgeColor ? '#fff' : 'var(--accent-cyan)',
                  padding: '0 5px',
                }}
              >
                {typeof badgeText === 'number' && badgeText > 99 ? '99+' : badgeText}
              </span>
            )}
          </>
        )}
        {/* 折叠模式下的角标（小圆点） */}
        {collapsed && badgeText != null && (
          <span
            className="absolute top-1 right-1 w-2 h-2 rounded-full"
            style={{ background: 'var(--accent-red)' }}
          />
        )}
      </button>
    </li>
  );
}

/* ===== 快速操作按钮 ===== */
function QuickAction({
  icon: Icon,
  label,
  onClick,
  badge,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className="relative flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-200"
      style={{ color: 'var(--text-tertiary)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
        e.currentTarget.style.color = 'var(--text-primary)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent';
        e.currentTarget.style.color = 'var(--text-tertiary)';
      }}
    >
      <Icon size={15} />
      {badge != null && badge > 0 && (
        <span
          className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] flex items-center justify-center rounded-full font-mono text-[8px] font-bold"
          style={{ background: 'var(--accent-red)', color: '#fff', padding: '0 3px' }}
        >
          {badge > 9 ? '9+' : badge}
        </span>
      )}
    </button>
  );
}

/* ===== 迷你状态面板 ===== */
function MiniStatusPanel({
  serviceStatus,
  onNavigate,
  collapsed,
}: {
  serviceStatus: ServiceStatus | null;
  onNavigate: (page: PageType) => void;
  collapsed: boolean;
}) {
  const isRunning = serviceStatus?.running ?? false;

  if (collapsed) {
    return (
      <div className="px-2 py-2 flex flex-col items-center gap-2">
        <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
      </div>
    );
  }

  return (
    <div
      className="mx-2 mb-2 rounded-xl p-3 space-y-2.5"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--glass-border)',
      }}
    >
      {/* 系统状态 */}
      <button
        onClick={() => onNavigate('home')}
        className="w-full flex items-center gap-2 transition-colors duration-150"
        style={{ color: 'var(--text-secondary)' }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; }}
      >
        <Activity size={12} style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }} />
        <span className="font-mono text-[11px] flex-1 text-left tracking-wide">
          {isRunning ? '系统在线' : '系统离线'}
        </span>
        <span
          className="font-mono text-[10px]"
          style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}
        >
          :{serviceStatus?.port ?? '—'}
        </span>
      </button>

      {/* 分隔线 */}
      <div className="h-px" style={{ background: 'var(--glass-border)' }} />

      {/* Bot 运行摘要 */}
      <button
        onClick={() => onNavigate('bots')}
        className="w-full flex items-center gap-2 transition-colors duration-150"
        style={{ color: 'var(--text-secondary)' }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; }}
      >
        <Bot size={12} style={{ color: 'var(--accent-cyan)' }} />
        <span className="font-mono text-[11px] flex-1 text-left">Bot 状态</span>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-green)' }} />
          <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>3</span>
          <span className="font-mono text-[10px] mx-0.5" style={{ color: 'var(--text-disabled)' }}>/</span>
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-red)' }} />
          <span className="font-mono text-[10px]" style={{ color: 'var(--accent-red)' }}>0</span>
        </div>
      </button>

      {/* 最新日志 */}
      <button
        onClick={() => onNavigate('logs')}
        className="w-full flex items-start gap-2 transition-colors duration-150"
        style={{ color: 'var(--text-tertiary)' }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; }}
      >
        <AlertCircle size={11} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-amber)' }} />
        <span className="font-mono text-[10px] leading-tight truncate text-left">
          闲鱼 Cookie 5h 前刷新
        </span>
      </button>
    </div>
  );
}

/* ===== 分隔线 ===== */
function Divider() {
  return <div className="my-2 mx-3 h-px" style={{ background: 'var(--glass-border)' }} />;
}

/* ===== 主侧边栏组件 ===== */
export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const devMode = useAppStore((s) => s.devMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const toggleDevMode = useAppStore((s) => s.toggleDevMode);

  /* 通知角标（演示数据，后续接真实 API） */
  const notifications = useMemo(() => ({
    notifications: 3,
    bots: 0,
    assistant: 0,
  }), []);

  /* 版本号三连击开启开发者模式 */
  const [versionClicks, setVersionClicks] = useState(0);
  useEffect(() => {
    if (versionClicks >= 3) {
      toggleDevMode();
      setVersionClicks(0);
    }
    if (versionClicks > 0) {
      const timer = setTimeout(() => setVersionClicks(0), 2000);
      return () => clearTimeout(timer);
    }
  }, [versionClicks]);

  return (
    <aside
      className={clsx(
        'transition-all duration-300 flex flex-col relative z-10',
        sidebarCollapsed ? 'w-[52px]' : 'w-[260px]',
      )}
      style={{
        background: 'var(--sidebar)',
        borderRight: '1px solid var(--glass-border)',
      }}
    >
      {/* ===== Logo 区域（macOS 标题栏拖拽）===== */}
      <div
        className="h-14 flex items-center px-3 titlebar-drag flex-shrink-0"
        style={{ borderBottom: '1px solid var(--glass-border)' }}
      >
        <div className="flex items-center gap-2 titlebar-no-drag">
          {/* Logo 图标 */}
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, rgba(0,212,255,0.2), rgba(0,255,170,0.1))',
              border: '1px solid rgba(0,212,255,0.2)',
            }}
          >
            <span className="text-sm">🦞</span>
          </div>
          {!sidebarCollapsed && (
            <div className="flex flex-col">
              <span
                className="font-display font-bold leading-tight"
                style={{ fontSize: '14px', color: 'var(--text-primary)' }}
              >
                OpenClaw
              </span>
              <span
                className="font-mono leading-none"
                style={{ fontSize: '9px', color: 'var(--text-disabled)', letterSpacing: '1px' }}
              >
                MANAGER v2.0
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ===== 快速操作栏 ===== */}
      {!sidebarCollapsed && (
        <div
          className="flex items-center justify-between px-3 py-2 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--glass-border)' }}
        >
          <div className="flex items-center gap-1">
            <QuickAction
              icon={Search}
              label="搜索 (⌘K)"
              onClick={() => {
                /* 触发 CommandPalette */
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
              }}
            />
            <QuickAction
              icon={Bell}
              label="通知"
              onClick={() => onNavigate('notifications')}
              badge={3}
            />
          </div>
          <div className="flex items-center gap-1">
            {/* 开发者模式开关 */}
            <button
              onClick={toggleDevMode}
              title={devMode ? '关闭开发者模式' : '开启开发者模式'}
              className={clsx(
                'flex items-center gap-1 px-2 py-1 rounded-md font-mono text-[10px] transition-all duration-200',
              )}
              style={{
                background: devMode ? 'rgba(0, 212, 255, 0.1)' : 'transparent',
                color: devMode ? 'var(--accent-cyan)' : 'var(--text-disabled)',
                border: `1px solid ${devMode ? 'rgba(0, 212, 255, 0.2)' : 'transparent'}`,
              }}
              onMouseEnter={(e) => {
                if (!devMode) {
                  e.currentTarget.style.color = 'var(--text-tertiary)';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                }
              }}
              onMouseLeave={(e) => {
                if (!devMode) {
                  e.currentTarget.style.color = 'var(--text-disabled)';
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              <Terminal size={11} />
              <span>DEV</span>
            </button>
          </div>
        </div>
      )}

      {/* ===== 导航菜单 ===== */}
      <nav className="flex-1 py-2 px-1.5 overflow-y-auto scroll-container">
        {/* C 端分组导航 */}
        {consumerGroups.map((group) => (
          <CollapsibleGroup
            key={group.id}
            group={group}
            currentPage={currentPage}
            collapsed={sidebarCollapsed}
            onNavigate={onNavigate}
            notifications={notifications}
          />
        ))}

        {/* 开发者模式分组 */}
        {devMode && (
          <>
            <Divider />
            <div className="px-2 py-1">
              {!sidebarCollapsed && (
                <span
                  className="font-mono uppercase"
                  style={{
                    fontSize: '9px',
                    letterSpacing: '1.5px',
                    color: 'var(--accent-cyan)',
                    opacity: 0.5,
                  }}
                >
                  开发者工具
                </span>
              )}
            </div>
            {devGroups.map((group) => (
              <CollapsibleGroup
                key={group.id}
                group={group}
                currentPage={currentPage}
                collapsed={sidebarCollapsed}
                onNavigate={onNavigate}
              />
            ))}
          </>
        )}
      </nav>

      {/* ===== 迷你状态面板 ===== */}
      <MiniStatusPanel
        serviceStatus={serviceStatus}
        onNavigate={onNavigate}
        collapsed={sidebarCollapsed}
      />

      {/* ===== 底部：设置 + 用户 + 折叠 ===== */}
      <div
        className="flex-shrink-0 px-2 pb-2"
        style={{ borderTop: '1px solid var(--glass-border)' }}
      >
        {/* 设置 + 帮助 */}
        <div className={clsx('flex items-center mt-2', sidebarCollapsed ? 'flex-col gap-1' : 'gap-1')}>
          <button
            onClick={() => onNavigate('settings')}
            title="设置"
            className={clsx(
              'flex items-center gap-2 rounded-lg transition-all duration-200',
              sidebarCollapsed ? 'p-2 justify-center' : 'flex-1 px-3 py-[7px]',
            )}
            style={{
              color: currentPage === 'settings' ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: currentPage === 'settings' ? 'rgba(0, 212, 255, 0.08)' : 'transparent',
              fontSize: '13px',
            }}
            onMouseEnter={(e) => {
              if (currentPage !== 'settings') {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }
            }}
            onMouseLeave={(e) => {
              if (currentPage !== 'settings') {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }
            }}
          >
            <Settings size={16} style={{ opacity: 0.7 }} />
            {!sidebarCollapsed && <span>设置</span>}
          </button>
          {!sidebarCollapsed && (
            <button
              title="帮助文档"
              className="flex items-center justify-center p-2 rounded-lg transition-all duration-200"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-tertiary)';
              }}
            >
              <HelpCircle size={15} />
            </button>
          )}
        </div>

        {/* 用户区 + 折叠按钮 */}
        <div
          className={clsx(
            'flex items-center mt-2 pt-2',
            sidebarCollapsed ? 'flex-col gap-2' : 'gap-2',
          )}
          style={{ borderTop: '1px solid var(--glass-border)' }}
        >
          {/* 用户头像 */}
          <button
            className="flex items-center gap-2 flex-1 min-w-0 rounded-lg px-1.5 py-1 transition-colors duration-200"
            title="用户信息"
            style={{ color: 'var(--text-secondary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
              e.currentTarget.style.color = 'var(--text-primary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
            onClick={() => setVersionClicks((c) => c + 1)}
          >
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))',
              }}
            >
              <User size={12} style={{ color: '#000' }} />
            </div>
            {!sidebarCollapsed && (
              <div className="flex flex-col min-w-0">
                <span className="text-[12px] font-medium truncate leading-tight">
                  管理员
                </span>
                <span
                  className="font-mono text-[9px] leading-tight"
                  style={{ color: 'var(--text-disabled)' }}
                >
                  v2.0.0
                </span>
              </div>
            )}
          </button>

          {/* 折叠/展开按钮 */}
          <button
            onClick={toggleSidebar}
            className="flex items-center justify-center w-7 h-7 rounded-lg transition-colors duration-200 flex-shrink-0"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
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
      </div>
    </aside>
  );
}

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Home,
  MessageSquare,
  TrendingUp,
  Bot,
  Globe,
  Newspaper,
  Landmark,
  Fish,
  ShoppingBag,
  Share2,
  Settings,
  ChevronLeft,
  ChevronRight,
  Terminal,
  User,
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
  DollarSign,
  Dna,
  Network,
  Gauge,
} from 'lucide-react';
import { PageType } from '../../App';
import { useAppStore } from '@/stores/appStore';
import { useLanguage } from '@/i18n';
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

interface NavItem {
  id: PageType;
  /** i18n 翻译 key，如 'sidebar.home' */
  labelKey: string;
  icon: React.ElementType;
}

/* ===== 10 个一级导航 — 扁平、大字体、占满侧边栏 ===== */
const mainNavItems: NavItem[] = [
  { id: 'home', labelKey: 'sidebar.home', icon: Home },
  { id: 'assistant', labelKey: 'sidebar.assistant', icon: MessageSquare },
  { id: 'worldmonitor', labelKey: 'sidebar.worldmonitor', icon: Globe },
  { id: 'newsfeed', labelKey: 'sidebar.newsfeed', icon: Newspaper },
  { id: 'finradar', labelKey: 'sidebar.finradar', icon: Landmark },
  { id: 'portfolio', labelKey: 'sidebar.portfolio', icon: TrendingUp },
  { id: 'bots', labelKey: 'sidebar.bots', icon: Bot },
  { id: 'store', labelKey: 'sidebar.store', icon: ShoppingBag },
  { id: 'xianyu', labelKey: 'sidebar.xianyu', icon: Fish },
  { id: 'social', labelKey: 'sidebar.social', icon: Share2 },
  { id: 'settings', labelKey: 'sidebar.settings', icon: Settings },
];

/* ===== 开发者模式额外导航 ===== */
const devNavItems: NavItem[] = [
  { id: 'control', labelKey: 'sidebar.control', icon: ShieldCheck },
  { id: 'dashboard', labelKey: 'sidebar.dashboard', icon: LayoutDashboard },
  { id: 'gateway', labelKey: 'sidebar.gateway', icon: Network },
  { id: 'scheduler', labelKey: 'sidebar.scheduler', icon: Clock },
  { id: 'perf', labelKey: 'sidebar.perf', icon: Gauge },
  { id: 'channels', labelKey: 'sidebar.channels', icon: MessageSquare },
  { id: 'ai', labelKey: 'sidebar.ai', icon: Bot },
  { id: 'plugins', labelKey: 'sidebar.plugins', icon: Blocks },
  { id: 'memory', labelKey: 'sidebar.memory', icon: BrainCircuit },
  { id: 'flow', labelKey: 'sidebar.flow', icon: Workflow },
  { id: 'evolution', labelKey: 'sidebar.evolution', icon: Dna },
  { id: 'dev', labelKey: 'sidebar.dev', icon: Code2 },
  { id: 'devpanel', labelKey: 'sidebar.devpanel', icon: Terminal },
  { id: 'testing', labelKey: 'sidebar.testing', icon: FlaskConical },
  { id: 'logs', labelKey: 'sidebar.logs', icon: ScrollText },
  { id: 'money', labelKey: 'sidebar.money', icon: DollarSign },
];

/* ===== 导航按钮组件 ===== */
function SidebarButton({
  item,
  isActive,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  isActive: boolean;
  collapsed: boolean;
  onNavigate: (page: PageType) => void;
}) {
  const Icon = item.icon;
  const { t } = useLanguage();
  const label = t(item.labelKey);

  return (
    <li>
      <button
        onClick={() => onNavigate(item.id)}
        title={collapsed ? label : undefined}
        className={clsx(
          'w-full flex items-center gap-3 rounded-xl transition-all duration-200 relative',
          collapsed ? 'px-0 py-3 justify-center' : 'px-4 py-3',
        )}
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: '15px',
          fontWeight: isActive ? 700 : 500,
          letterSpacing: '-0.01em',
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          background: isActive ? 'rgba(0, 212, 255, 0.1)' : 'transparent',
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
        {/* 左侧激活条 — 青色竖线 */}
        {isActive && (
          <motion.div
            layoutId="sidebarActive"
            className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 rounded-r-full"
            style={{ background: 'var(--accent-cyan)', boxShadow: '0 0 12px var(--accent-cyan-glow)' }}
            transition={{ type: 'spring', stiffness: 300, damping: 28 }}
          />
        )}
        <Icon
          size={20}
          className="flex-shrink-0"
          style={{
            color: isActive ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.5)',
          }}
        />
        {!collapsed && <span className="truncate">{label}</span>}
      </button>
    </li>
  );
}

/* ===== 主侧边栏 ===== */
export function Sidebar({ currentPage, onNavigate, serviceStatus }: SidebarProps) {
  const devMode = useAppStore((s) => s.devMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const toggleDevMode = useAppStore((s) => s.toggleDevMode);
  const isRunning = serviceStatus?.running ?? false;
  const { t } = useLanguage();

  /* 三击版本号开启开发者模式 */
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
        sidebarCollapsed ? 'w-[56px]' : 'w-[240px]',
      )}
      style={{
        background: 'var(--sidebar)',
        borderRight: '1px solid var(--glass-border)',
      }}
    >
      {/* ===== Logo 区域 ===== */}
      <div
        className="h-14 flex items-center px-3 titlebar-drag flex-shrink-0"
        style={{ borderBottom: '1px solid var(--glass-border)' }}
      >
        <div className="flex items-center gap-2 titlebar-no-drag">
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
                style={{ fontSize: '14px', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}
              >
                OpenClaw
              </span>
              <span
                className="font-mono leading-none"
                style={{ fontSize: '9px', color: 'var(--text-disabled)', letterSpacing: '1px' }}
              >
                MANAGER
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ===== 主导航 — 10 个大按钮，占满空间 ===== */}
      <nav className="flex-1 py-3 px-2 overflow-y-auto scroll-container flex flex-col">
        <ul className="space-y-1 flex-1 flex flex-col justify-start">
          {mainNavItems.map((item) => (
            <SidebarButton
              key={item.id}
              item={item}
              isActive={currentPage === item.id}
              collapsed={sidebarCollapsed}
              onNavigate={onNavigate}
            />
          ))}
        </ul>

        {/* 开发者模式导航 */}
        {devMode && (
          <>
            <div className="my-2 mx-2 h-px" style={{ background: 'var(--glass-border)' }} />
            {!sidebarCollapsed && (
              <div className="px-2 py-1 mb-1">
                <span
                  className="font-mono uppercase"
                  style={{ fontSize: '10px', letterSpacing: '1.5px', color: 'var(--accent-cyan)', opacity: 0.5 }}
                >
                  {t('sidebar.devTools')}
                </span>
              </div>
            )}
            <ul className="space-y-0.5">
              {devNavItems.map((item) => (
                <SidebarButton
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
      </nav>

      {/* ===== 底栏：状态 + 用户 + 折叠 ===== */}
      <div
        className="flex-shrink-0 px-2 pb-2 pt-2"
        style={{ borderTop: '1px solid var(--glass-border)' }}
      >
        {/* 系统状态指示 */}
        {!sidebarCollapsed ? (
          <div className="flex items-center gap-2 px-2 py-1.5 mb-2 rounded-lg"
            style={{ background: 'rgba(255,255,255,0.02)' }}
          >
            <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
            <span
              className="font-mono text-[10px] tracking-wider flex-1"
              style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}
            >
              {isRunning ? 'ONLINE' : 'OFFLINE'}
            </span>
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
              :{serviceStatus?.port ?? '—'}
            </span>
          </div>
        ) : (
          <div className="flex justify-center py-2 mb-1">
            <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          </div>
        )}

        {/* DEV 模式开关 + 折叠按钮 */}
        <div className={clsx('flex items-center', sidebarCollapsed ? 'flex-col gap-2' : 'gap-1')}>
          {/* DEV 开关 */}
          <button
            onClick={toggleDevMode}
            title={devMode ? '关闭开发者模式' : '开启开发者模式'}
            className="flex items-center justify-center rounded-lg transition-all duration-200"
            style={{
              width: sidebarCollapsed ? 32 : 'auto',
              height: 32,
              padding: sidebarCollapsed ? 0 : '0 10px',
              background: devMode ? 'rgba(0, 212, 255, 0.1)' : 'transparent',
              color: devMode ? 'var(--accent-cyan)' : 'var(--text-disabled)',
              border: devMode ? '1px solid rgba(0, 212, 255, 0.15)' : '1px solid transparent',
              fontSize: '10px',
              fontFamily: 'var(--font-mono)',
            }}
            onMouseEnter={(e) => {
              if (!devMode) {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                e.currentTarget.style.color = 'var(--text-tertiary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!devMode) {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-disabled)';
              }
            }}
          >
            <Terminal size={12} />
            {!sidebarCollapsed && <span className="ml-1">DEV</span>}
          </button>

          {/* 用户头像区域（三击解锁 dev） */}
          {!sidebarCollapsed && (
            <button
              className="flex items-center gap-2 flex-1 min-w-0 rounded-lg px-2 py-1 transition-colors duration-200"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-tertiary)';
              }}
              onClick={() => setVersionClicks((c) => c + 1)}
            >
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))' }}
              >
                <User size={10} style={{ color: '#000' }} />
              </div>
              <span className="font-mono text-[10px] truncate">v2.0</span>
            </button>
          )}

          {/* 折叠按钮 */}
          <button
            onClick={toggleSidebar}
            className="flex items-center justify-center w-8 h-8 rounded-lg transition-colors duration-200 flex-shrink-0"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-tertiary)';
            }}
            title={sidebarCollapsed ? '展开' : '折叠'}
          >
            {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>
      </div>
    </aside>
  );
}

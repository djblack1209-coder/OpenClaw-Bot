import { useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { showNativeNotification } from './lib/notify';

import { lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';

/* ====== C 端新页面（懒加载完整实现） ====== */
const HomeDashboard = lazy(() => import('./components/Home').then(m => ({ default: m.HomeDashboard })));
const Assistant = lazy(() => import('./components/Assistant').then(m => ({ default: m.Assistant })));
const Portfolio = lazy(() => import('./components/Portfolio').then(m => ({ default: m.Portfolio })));
const Bots = lazy(() => import('./components/Bots').then(m => ({ default: m.Bots })));
const Store = lazy(() => import('./components/Store').then(m => ({ default: m.Store })));
const NewsFeed = lazy(() => import('./components/NewsFeed').then(m => ({ default: m.NewsFeed })));
const Onboarding = lazy(() => import('./components/Onboarding').then(m => ({ default: m.Onboarding })));
const WorldMonitor = lazy(() => import('./components/WorldMonitor').then(m => ({ default: m.WorldMonitor })));
const FinRadar = lazy(() => import('./components/FinRadar').then(m => ({ default: m.FinRadar })));
const NotificationsPage = lazy(() => import('./components/Notifications').then(m => ({ default: m.Notifications })));
const TradingPage = lazy(() => import('./components/Trading').then(m => ({ default: m.Trading })));
const RiskPage = lazy(() => import('./components/Risk').then(m => ({ default: m.Risk })));

/* ====== 原有页面（开发者模式下显示） ====== */
const Dashboard = lazy(() => import('./components/Dashboard').then(m => ({ default: m.Dashboard })));
const ControlCenter = lazy(() => import('./components/ControlCenter').then(m => ({ default: m.ControlCenter })));
const AIConfig = lazy(() => import('./components/AIConfig').then(m => ({ default: m.AIConfig })));
const Channels = lazy(() => import('./components/Channels').then(m => ({ default: m.Channels })));
const Social = lazy(() => import('./components/Social').then(m => ({ default: m.Social })));
const Xianyu = lazy(() => import('./components/Xianyu').then(m => ({ default: m.Xianyu })));
const Money = lazy(() => import('./components/Money').then(m => ({ default: m.Money })));
const Dev = lazy(() => import('./components/Dev').then(m => ({ default: m.Dev })));
const DevPanel = lazy(() => import('./components/DevPanel'));
const Settings = lazy(() => import('./components/Settings').then(m => ({ default: m.Settings })));
const Testing = lazy(() => import('./components/Testing').then(m => ({ default: m.Testing })));
const Logs = lazy(() => import('./components/Logs').then(m => ({ default: m.Logs })));
const ExecutionFlow = lazy(() => import('./components/ExecutionFlow').then(m => ({ default: m.ExecutionFlow })));
const Memory = lazy(() => import('./components/Memory').then(m => ({ default: m.Memory })));
const Evolution = lazy(() => import('./components/Evolution').then(m => ({ default: m.Evolution })));
const APIGateway = lazy(() => import('./components/APIGateway').then(m => ({ default: m.APIGateway })));
const Scheduler = lazy(() => import('./components/Scheduler').then(m => ({ default: m.Scheduler })));
const Performance = lazy(() => import('./components/Performance').then(m => ({ default: m.Performance })));

  const PageLoader = () => (
  <div className="h-full min-h-[200px] flex items-center justify-center" style={{ background: 'var(--bg-primary, #0a0a0a)' }}>
    <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-cyan)]" />
  </div>
);


import { Sidebar } from './components/Layout/Sidebar';
import { Header } from './components/Layout/Header';
import { CommandPalette } from './components/CommandPalette';
import { PageErrorBoundary } from './components/PageErrorBoundary';

import { appLogger } from './lib/logger';
import { isTauri } from './lib/tauri';
import { useAppStore } from './stores/appStore';
import { LanguageProvider } from './i18n';

/**
 * 页面类型联合类型
 * C 端新增 5 个一级页面：home / assistant / portfolio / bots / store
 * 原有 16 个页面保留，在开发者模式下可访问
 */
export type PageType =
  /* C 端一级页面 */
  | 'home'           // 首页 Dashboard
  | 'assistant'      // AI 助手（对话界面）
  | 'notifications'  // 通知中心
  /* 全球情报（worldmonitor） */
  | 'worldmonitor'   // 全球监控面板
  | 'newsfeed'       // 新闻中心
  | 'finradar'       // 金融雷达
  /* 资产管理 */
  | 'portfolio'      // 投资组合
  | 'trading'        // 交易引擎
  | 'risk'           // 风险分析
  /* 智能体 */
  | 'bots'           // 我的机器人
  | 'store'          // Bot 商店
  /* 运营中心 */
  | 'xianyu'         // 闲鱼管理
  | 'onboarding'     // 引导流程（仅首次启动）
  /* 原有页面（开发者模式） */
  | 'control' | 'dashboard' | 'ai' | 'channels' | 'social' | 'money'
  | 'dev' | 'devpanel' | 'testing' | 'logs' | 'settings' | 'flow' | 'plugins'
  | 'memory' | 'evolution' | 'gateway' | 'scheduler' | 'perf';

const VALID_PAGES = new Set<PageType>([
  'home', 'assistant', 'notifications', 'worldmonitor', 'newsfeed', 'finradar',
  'portfolio', 'trading', 'risk', 'bots', 'store', 'xianyu', 'onboarding',
  'control', 'dashboard', 'ai', 'channels', 'social', 'money', 'dev',
  'devpanel', 'testing', 'logs', 'settings', 'flow', 'plugins', 'memory',
  'evolution', 'gateway', 'scheduler', 'perf',
]);

const DEV_PAGES = new Set<PageType>([
  'control', 'dashboard', 'ai', 'channels', 'money', 'dev', 'devpanel',
  'testing', 'logs', 'flow', 'plugins', 'memory', 'evolution', 'gateway',
  'scheduler', 'perf',
]);

function parsePageParam(): PageType | null {
  const page = new URLSearchParams(window.location.search).get('page');
  return page && VALID_PAGES.has(page as PageType) ? (page as PageType) : null;
}

export interface EnvironmentStatus {
  node_installed: boolean;
  node_version: string | null;
  node_version_ok: boolean;
  openclaw_installed: boolean;
  openclaw_version: string | null;
  config_dir_exists: boolean;
  ready: boolean;
  os: string;
}

import type { ServiceStatus } from './lib/tauri';

function App() {
  // 强制 html 元素保持 dark class
  useEffect(() => {
    const html = document.documentElement;
    html.classList.add('dark');
    html.style.colorScheme = 'dark';
  }, []);

  const currentPage = useAppStore((s) => s.currentPage);
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);
  const isReady = useAppStore((s) => s.isReady);
  const setIsReady = useAppStore((s) => s.setIsReady);
  const envStatus = useAppStore((s) => s.envStatus);
  const setEnvStatus = useAppStore((s) => s.setEnvStatus);
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const setServiceStatus = useAppStore((s) => s.setServiceStatus);
  const onboardingComplete = useAppStore((s) => s.onboardingComplete);
  const setOnboardingComplete = useAppStore((s) => s.setOnboardingComplete);
  const devMode = useAppStore((s) => s.devMode);

  useEffect(() => {
    const page = parsePageParam();
    if (!page) return;
    setCurrentPage(DEV_PAGES.has(page) && !devMode ? 'home' : page);
  }, [devMode, setCurrentPage]);

  // 检查环境
  const checkEnvironment = useCallback(async () => {
    if (!isTauri()) {
      appLogger.warn('不在 Tauri 环境中，跳过环境检查');
      setIsReady(true);
      return;
    }
    
    appLogger.info('开始检查系统环境...');
    try {
      const status = await invoke<EnvironmentStatus>('check_environment');
      appLogger.info('环境检查完成', status);
      setEnvStatus(status);
      setIsReady(true);
    } catch (e) {
      appLogger.error('环境检查失败', e);
      setIsReady(true);
    }
  }, [setEnvStatus, setIsReady]);

  useEffect(() => {
    appLogger.info('🦞 App 组件已挂载');
    checkEnvironment();
  }, [checkEnvironment]);

  // 记录上一次服务运行状态，用于检测状态变化并发送原生通知
  const prevRunningRef = useRef<boolean | null>(null);

  // 定期获取服务状态
  useEffect(() => {
    if (!isTauri()) return;
    
    const fetchServiceStatus = async () => {
      try {
        const status = await invoke<ServiceStatus>('get_service_status');
        setServiceStatus(status);

        // 检测状态变化 → 发送 macOS 原生通知
        const prev = prevRunningRef.current;
        if (prev !== null && prev !== status.running) {
          if (status.running) {
            showNativeNotification('OpenClaw 服务已启动', '后端服务已恢复运行');
          } else {
            showNativeNotification('OpenClaw 服务已停止', '后端服务已停止运行，请检查');
          }
        }
        prevRunningRef.current = status.running;
      } catch {
        // 静默处理轮询错误
      }
    };
    fetchServiceStatus();
    const interval = setInterval(fetchServiceStatus, 3000);
    return () => clearInterval(interval);
  }, [setServiceStatus]);

  const handleSetupComplete = useCallback(() => {
    appLogger.info('安装向导完成');
    checkEnvironment();
  }, [checkEnvironment]);

  // 页面切换处理 — 支持导航守卫（如 Settings 页未保存提示）
  const handleNavigate = (page: PageType) => {
    const guard = useAppStore.getState().navigationGuard;
    if (guard && !guard(page)) {
      // 导航被守卫拦截（页面内会弹出确认对话框）
      return;
    }
    appLogger.action('页面切换', { from: currentPage, to: page });
    setCurrentPage(page);
  };

  const renderPage = () => {
    /* 页面过渡动画：淡入 + 微缩放，比旧版的 x 偏移更有 Apple 质感 */
    const pageVariants = {
      initial: { opacity: 0, scale: 0.98 },
      animate: { opacity: 1, scale: 1 },
      exit: { opacity: 0, scale: 0.98 },
    };

    // 只渲染当前活跃页面，避免每次 render 实例化全部 28+ 个页面组件
    const renderActivePage = (): JSX.Element => {
      const wrap = (pageName: string, child: JSX.Element) => (
        <PageErrorBoundary pageName={pageName}>{child}</PageErrorBoundary>
      );
      switch (currentPage) {
        /* C 端新页面 */
        case 'home': return wrap('首页', <HomeDashboard />);
        case 'assistant': return wrap('AI 助手', <Assistant />);
        case 'notifications': return wrap('通知中心', <NotificationsPage />);
        /* 全球情报 */
        case 'worldmonitor': return wrap('全球监控', <WorldMonitor />);
        case 'newsfeed': return wrap('新闻中心', <NewsFeed />);
        case 'finradar': return wrap('金融雷达', <FinRadar />);
        /* 资产管理 */
        case 'portfolio': return wrap('投资组合', <Portfolio />);
        case 'trading': return wrap('交易引擎', <TradingPage />);
        case 'risk': return wrap('风险分析', <RiskPage />);
        /* 智能体 */
        case 'bots': return wrap('我的机器人', <Bots />);
        case 'store': return wrap('Bot 商店', <Store />);
        /* 运营中心 */
        case 'xianyu': return wrap('闲鱼管理', <Xianyu />);
        case 'onboarding': return wrap('引导', <Onboarding onComplete={() => { setOnboardingComplete(true); setCurrentPage('home'); }} />);
        /* 原有页面（开发者模式） */
        case 'control': return wrap('控制中心', <ControlCenter />);
        case 'dashboard': return wrap('仪表盘', <Dashboard envStatus={envStatus} onSetupComplete={handleSetupComplete} />);
        case 'flow': return wrap('执行流', <ExecutionFlow />);
        case 'memory': return wrap('记忆', <Memory />);
        case 'plugins': return wrap('插件', <Store />);
        case 'ai': return wrap('AI 配置', <AIConfig />);
        case 'channels': return wrap('频道', <Channels />);
        case 'social': return wrap('社媒', <Social />);
        case 'money': return wrap('财务', <Money />);
        case 'dev': return wrap('开发', <Dev />);
        case 'devpanel': return wrap('开发者工作台', <DevPanel />);
        case 'testing': return wrap('测试', <Testing />);
        case 'logs': return wrap('日志', <Logs />);
        case 'settings': return wrap('设置', <Settings onEnvironmentChange={checkEnvironment} />);
        case 'evolution': return wrap('进化', <Evolution />);
        case 'gateway': return wrap('API 网关', <APIGateway />);
        case 'scheduler': return wrap('任务调度', <Scheduler />);
        case 'perf': return wrap('性能监控', <Performance />);
        default: return wrap('首页', <HomeDashboard />);
      }
    };

    return (
      <AnimatePresence mode="wait">
        <motion.div
          key={currentPage}
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className="h-full"
        >
          <Suspense fallback={<PageLoader />}>
            {renderActivePage()}
          </Suspense>
        </motion.div>
      </AnimatePresence>
    );
  };

  // 正在检查环境
  if (isReady === null) {
    return (
      <LanguageProvider>
        <div className="flex h-screen items-center justify-center" style={{ background: 'var(--bg-base)' }}>
          <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
          <div className="relative z-10 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-[var(--accent-cyan)] to-[var(--accent-purple)] mb-4 animate-pulse">
              <span className="text-3xl">🦞</span>
            </div>
            <p className="font-mono text-sm" style={{ color: 'var(--text-tertiary)' }}>正在启动...</p>
          </div>
        </div>
      </LanguageProvider>
    );
  }

  // 首次运行引导流程（全屏，不显示侧边栏和标题栏）
  if (!onboardingComplete) {
    return (
      <LanguageProvider>
        <div className="h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
          <Suspense fallback={<PageLoader />}>
            <Onboarding
              onComplete={() => {
                setOnboardingComplete(true);
                setCurrentPage('home');
              }}
            />
          </Suspense>
        </div>
      </LanguageProvider>
    );
  }

  // 主界面
  return (
    <LanguageProvider>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
        <CommandPalette />
        {/* 背景装饰 */}
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        {/* 侧边栏 */}
        <Sidebar currentPage={currentPage} onNavigate={handleNavigate} serviceStatus={serviceStatus} />
        
        {/* 主内容区 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 标题栏（macOS 拖拽区域） */}
          <Header currentPage={currentPage} />
          
          {/* 页面内容 */}
          <main className="flex-1 overflow-hidden px-5 py-4">
            {renderPage()}
          </main>
        </div>
      </div>
    </LanguageProvider>
  );
}

export default App;

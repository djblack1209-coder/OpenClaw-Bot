import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { Toaster } from 'sonner';

import { lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';

/* ====== C 端新页面（占位组件，后续各 Phase 会替换为完整实现） ====== */
const HomeDashboard = lazy(() => import('./components/Home').then(m => ({ default: m.HomeDashboard })));
const Assistant = lazy(() => import('./components/Assistant').then(m => ({ default: m.Assistant })));
const Portfolio = lazy(() => import('./components/Portfolio').then(m => ({ default: m.Portfolio })));
const Bots = lazy(() => import('./components/Bots').then(m => ({ default: m.Bots })));
const Store = lazy(() => import('./components/Store').then(m => ({ default: m.Store })));

/* ====== 原有页面（开发者模式下显示） ====== */
const Dashboard = lazy(() => import('./components/Dashboard').then(m => ({ default: m.Dashboard })));
const ControlCenter = lazy(() => import('./components/ControlCenter').then(m => ({ default: m.ControlCenter })));
const AIConfig = lazy(() => import('./components/AIConfig').then(m => ({ default: m.AIConfig })));
const Channels = lazy(() => import('./components/Channels').then(m => ({ default: m.Channels })));
const Social = lazy(() => import('./components/Social').then(m => ({ default: m.Social })));
const Money = lazy(() => import('./components/Money').then(m => ({ default: m.Money })));
const Dev = lazy(() => import('./components/Dev').then(m => ({ default: m.Dev })));
const Settings = lazy(() => import('./components/Settings').then(m => ({ default: m.Settings })));
const Testing = lazy(() => import('./components/Testing').then(m => ({ default: m.Testing })));
const Logs = lazy(() => import('./components/Logs').then(m => ({ default: m.Logs })));
const ExecutionFlow = lazy(() => import('./components/ExecutionFlow').then(m => ({ default: m.ExecutionFlow })));
const Memory = lazy(() => import('./components/Memory').then(m => ({ default: m.Memory })));
const Plugins = lazy(() => import('./components/Plugins').then(m => ({ default: m.Plugins })));
const Evolution = lazy(() => import('./components/Evolution').then(m => ({ default: m.Evolution })));
const APIGateway = lazy(() => import('./components/APIGateway').then(m => ({ default: m.APIGateway })));
const Scheduler = lazy(() => import('./components/Scheduler').then(m => ({ default: m.Scheduler })));

const PageLoader = () => (
  <div className="h-full flex items-center justify-center">
    <Loader2 className="w-8 h-8 animate-spin text-claw-500" />
  </div>
);

import { Sidebar } from './components/Layout/Sidebar';
import { Header } from './components/Layout/Header';
import { CommandPalette } from './components/CommandPalette';
import { PageErrorBoundary } from './components/PageErrorBoundary';

import { appLogger } from './lib/logger';
import { isTauri } from './lib/tauri';
import { useAppStore } from './stores/appStore';

/**
 * 页面类型联合类型
 * C 端新增 5 个一级页面：home / assistant / portfolio / bots / store
 * 原有 16 个页面保留，在开发者模式下可访问
 */
export type PageType =
  /* C 端一级页面 */
  | 'home'       // 首页 Dashboard
  | 'assistant'  // AI 助手（对话界面）
  | 'portfolio'  // 我的资产
  | 'bots'       // 我的机器人
  | 'store'      // 插件商店
  /* 原有页面（开发者模式） */
  | 'control' | 'dashboard' | 'ai' | 'channels' | 'social' | 'money'
  | 'dev' | 'testing' | 'logs' | 'settings' | 'flow' | 'plugins'
  | 'memory' | 'evolution' | 'gateway' | 'scheduler';

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
  // 监听 <html> 上的 dark class 变化，让 Toaster 主题跟随系统切换
  const [toasterTheme, setToasterTheme] = useState<'dark' | 'light'>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  );

  useEffect(() => {
    const html = document.documentElement;
    const observer = new MutationObserver(() => {
      setToasterTheme(html.classList.contains('dark') ? 'dark' : 'light');
    });
    observer.observe(html, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  const currentPage = useAppStore((s) => s.currentPage);
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);
  const isReady = useAppStore((s) => s.isReady);
  const setIsReady = useAppStore((s) => s.setIsReady);
  const envStatus = useAppStore((s) => s.envStatus);
  const setEnvStatus = useAppStore((s) => s.setEnvStatus);
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const setServiceStatus = useAppStore((s) => s.setServiceStatus);

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
  }, []);

  useEffect(() => {
    appLogger.info('🦞 App 组件已挂载');
    checkEnvironment();
  }, [checkEnvironment]);

  // 定期获取服务状态
  useEffect(() => {
    if (!isTauri()) return;
    
    const fetchServiceStatus = async () => {
      try {
        const status = await invoke<ServiceStatus>('get_service_status');
        setServiceStatus(status);
      } catch {
        // 静默处理轮询错误
      }
    };
    fetchServiceStatus();
    const interval = setInterval(fetchServiceStatus, 3000);
    return () => clearInterval(interval);
  }, []);

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

    // 每个页面用 PageErrorBoundary 隔离崩溃，单页出错不影响侧边栏和其他页面
    const pages: Record<PageType, JSX.Element> = {
      /* C 端新页面 */
      home: <PageErrorBoundary pageName="首页"><HomeDashboard /></PageErrorBoundary>,
      assistant: <PageErrorBoundary pageName="AI 助手"><Assistant /></PageErrorBoundary>,
      portfolio: <PageErrorBoundary pageName="我的资产"><Portfolio /></PageErrorBoundary>,
      bots: <PageErrorBoundary pageName="我的机器人"><Bots /></PageErrorBoundary>,
      store: <PageErrorBoundary pageName="插件商店"><Store /></PageErrorBoundary>,
      /* 原有页面 */
      control: <PageErrorBoundary pageName="控制中心"><ControlCenter /></PageErrorBoundary>,
      dashboard: <PageErrorBoundary pageName="仪表盘"><Dashboard envStatus={envStatus} onSetupComplete={handleSetupComplete} /></PageErrorBoundary>,
      flow: <PageErrorBoundary pageName="执行流"><ExecutionFlow /></PageErrorBoundary>,
      memory: <PageErrorBoundary pageName="记忆"><Memory /></PageErrorBoundary>,
      plugins: <PageErrorBoundary pageName="插件"><Plugins /></PageErrorBoundary>,
      ai: <PageErrorBoundary pageName="AI 配置"><AIConfig /></PageErrorBoundary>,
      channels: <PageErrorBoundary pageName="频道"><Channels /></PageErrorBoundary>,
      social: <PageErrorBoundary pageName="社媒"><Social /></PageErrorBoundary>,
      money: <PageErrorBoundary pageName="财务"><Money /></PageErrorBoundary>,
      dev: <PageErrorBoundary pageName="开发"><Dev /></PageErrorBoundary>,
      testing: <PageErrorBoundary pageName="测试"><Testing /></PageErrorBoundary>,
      logs: <PageErrorBoundary pageName="日志"><Logs /></PageErrorBoundary>,
      settings: <PageErrorBoundary pageName="设置"><Settings onEnvironmentChange={checkEnvironment} /></PageErrorBoundary>,
      evolution: <PageErrorBoundary pageName="进化"><Evolution /></PageErrorBoundary>,
      gateway: <PageErrorBoundary pageName="API 网关"><APIGateway /></PageErrorBoundary>,
      scheduler: <PageErrorBoundary pageName="任务调度"><Scheduler /></PageErrorBoundary>,
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
            {pages[currentPage]}
          </Suspense>
        </motion.div>
      </AnimatePresence>
    );
  };

  // 正在检查环境
  if (isReady === null) {
    return (
      <div className="flex h-screen bg-dark-900 items-center justify-center">
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        <div className="relative z-10 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 mb-4 animate-pulse">
            <span className="text-3xl">🦞</span>
          </div>
          <p className="text-dark-400">正在启动...</p>
        </div>
      </div>
    );
  }

  // 主界面
  return (
    <div className="flex h-screen bg-dark-900 overflow-hidden">
      <CommandPalette />
      {/* 全局通知提示 */}
      <Toaster 
        theme={toasterTheme}
        position="top-right"
        toastOptions={{
          className: 'bg-dark-800 border-dark-700 text-dark-100',
        }}
      />
      {/* 背景装饰 */}
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* 侧边栏 */}
      <Sidebar currentPage={currentPage} onNavigate={handleNavigate} serviceStatus={serviceStatus} />
      
      {/* 主内容区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 标题栏（macOS 拖拽区域） */}
        <Header currentPage={currentPage} />
        
        {/* 页面内容 */}
        <main className="flex-1 overflow-hidden p-6">
          {renderPage()}
        </main>
      </div>
    </div>
  );
}

export default App;

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { PageType, EnvironmentStatus } from '../App';
import type { ServiceStatus } from '../lib/tauri';

/**
 * 导航守卫回调：页面切换前调用，返回 true 允许切换，返回 false 阻止切换。
 * 用于 Settings 等页面在有未保存修改时拦截导航。
 */
type NavigationGuard = (targetPage: PageType) => boolean;

interface AppState {
  /* 导航 */
  currentPage: PageType;
  sidebarCollapsed: boolean;
  
  /* 环境 & 服务 */
  envStatus: EnvironmentStatus | null;
  serviceStatus: ServiceStatus | null;
  isReady: boolean | null;
  
  /* 开发者模式（默认关闭，三击版本号解锁） */
  devMode: boolean;

  /* 引导流程 */
  onboardingComplete: boolean;

  /** 导航守卫，由需要拦截离开的页面注册 */
  navigationGuard: NavigationGuard | null;

  /* Actions */
  setCurrentPage: (page: PageType) => void;
  setOnboardingComplete: (complete: boolean) => void;
  setEnvStatus: (status: EnvironmentStatus | null) => void;
  setServiceStatus: (status: ServiceStatus | null) => void;
  setIsReady: (ready: boolean | null) => void;
  setNavigationGuard: (guard: NavigationGuard | null) => void;
  toggleSidebar: () => void;
  setDevMode: (enabled: boolean) => void;
  toggleDevMode: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      /* 默认状态 */
      currentPage: 'home' as PageType,
      sidebarCollapsed: false,
      envStatus: null,
      serviceStatus: null,
      isReady: null,
      devMode: false,
      onboardingComplete: false,
      navigationGuard: null,

      /* Actions */
      setCurrentPage: (page) => set({ currentPage: page }),
      setOnboardingComplete: (complete) => {
        set({ onboardingComplete: complete });
      },
      setEnvStatus: (status) => set({ envStatus: status }),
      setServiceStatus: (status) => set({ serviceStatus: status }),
      setIsReady: (ready) => set({ isReady: ready }),
      setNavigationGuard: (guard) => set({ navigationGuard: guard }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setDevMode: (enabled) => set({ devMode: enabled }),
      toggleDevMode: () => set((s) => ({ devMode: !s.devMode })),
    }),
    {
      name: 'openclaw-app-store',
      /* 只持久化用户偏好，不持久化运行时状态 */
      partialize: (state) => ({
        devMode: state.devMode,
        sidebarCollapsed: state.sidebarCollapsed,
        onboardingComplete: state.onboardingComplete,
      }),
    }
  )
);

import { create } from 'zustand';
import { PageType, EnvironmentStatus } from '../App';

interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
}

/**
 * 导航守卫回调：页面切换前调用，返回 true 允许切换，返回 false 阻止切换。
 * 用于 Settings 等页面在有未保存修改时拦截导航。
 */
type NavigationGuard = (targetPage: PageType) => boolean;

interface AppState {
  currentPage: PageType;
  envStatus: EnvironmentStatus | null;
  serviceStatus: ServiceStatus | null;
  isReady: boolean | null;
  /** 导航守卫，由需要拦截离开的页面注册 */
  navigationGuard: NavigationGuard | null;
  
  setCurrentPage: (page: PageType) => void;
  setEnvStatus: (status: EnvironmentStatus | null) => void;
  setServiceStatus: (status: ServiceStatus | null) => void;
  setIsReady: (ready: boolean | null) => void;
  /** 注册导航守卫（同一时间只能有一个） */
  setNavigationGuard: (guard: NavigationGuard | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentPage: 'control',
  envStatus: null,
  serviceStatus: null,
  isReady: null,
  navigationGuard: null,
  
  setCurrentPage: (page) => set({ currentPage: page }),
  setEnvStatus: (status) => set({ envStatus: status }),
  setServiceStatus: (status) => set({ serviceStatus: status }),
  setIsReady: (ready) => set({ isReady: ready }),
  setNavigationGuard: (guard) => set({ navigationGuard: guard }),
}));

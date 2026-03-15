import { create } from 'zustand';
import type { ServiceStatus, SystemInfo } from '../lib/tauri';

interface AppState {
  // 服务状态
  serviceStatus: ServiceStatus | null;
  setServiceStatus: (status: ServiceStatus | null) => void;

  // 系统信息
  systemInfo: SystemInfo | null;
  setSystemInfo: (info: SystemInfo | null) => void;

  // UI 状态
  loading: boolean;
  setLoading: (loading: boolean) => void;

  // 通知
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
}

interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
}

export const useAppStore = create<AppState>((set) => ({
  // 服务状态
  serviceStatus: null,
  setServiceStatus: (status) => set({ serviceStatus: status }),

  // 系统信息
  systemInfo: null,
  setSystemInfo: (info) => set({ systemInfo: info }),

  // UI 状态
  loading: false,
  setLoading: (loading) => set({ loading }),

  // 通知
  notifications: [],
  addNotification: (notification) =>
    set((state) => ({
      notifications: [
        ...state.notifications,
        { ...notification, id: Date.now().toString() },
      ],
    })),
  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),
}));

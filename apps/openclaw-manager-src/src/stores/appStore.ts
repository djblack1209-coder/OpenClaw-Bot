import { create } from 'zustand';
import { PageType, EnvironmentStatus } from '../App';

interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
}

interface AppState {
  currentPage: PageType;
  envStatus: EnvironmentStatus | null;
  serviceStatus: ServiceStatus | null;
  isReady: boolean | null;
  
  setCurrentPage: (page: PageType) => void;
  setEnvStatus: (status: EnvironmentStatus | null) => void;
  setServiceStatus: (status: ServiceStatus | null) => void;
  setIsReady: (ready: boolean | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentPage: 'control',
  envStatus: null,
  serviceStatus: null,
  isReady: null,
  
  setCurrentPage: (page) => set({ currentPage: page }),
  setEnvStatus: (status) => set({ envStatus: status }),
  setServiceStatus: (status) => set({ serviceStatus: status }),
  setIsReady: (ready) => set({ isReady: ready }),
}));

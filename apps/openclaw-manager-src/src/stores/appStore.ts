import { create } from 'zustand';
import type { PageType, EnvironmentStatus } from '../App';
import type { ServiceStatus } from '../lib/tauri';
import { trackClick, trackPageLoad } from '../lib/qa-tracker';

type NavigationGuard = (targetPage: PageType) => boolean;
export type OnboardingStatus = 'incomplete' | 'saved_unverified' | 'skipped' | 'legacy_unverified';
const STORE_KEY = 'openclaw-app-store';
const FEATURE_IDS = new Set(['assistant', 'trading', 'social']);

interface Preferences {
  devMode: boolean;
  sidebarCollapsed: boolean;
  onboardingComplete: boolean;
  onboardingStatus: OnboardingStatus;
  onboardingFeatures: string[];
}

const defaults: Preferences = {
  devMode: false, sidebarCollapsed: false, onboardingComplete: false,
  onboardingStatus: 'incomplete', onboardingFeatures: ['assistant'],
};

function features(values: unknown): string[] {
  return [...new Set(['assistant', ...(Array.isArray(values) ? values.filter(
    (value): value is string => typeof value === 'string' && FEATURE_IDS.has(value),
  ) : [])])];
}

function readPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    const state = raw ? JSON.parse(raw)?.state : null;
    // Legacy flags mean only that the old welcome flow was dismissed.
    const complete = state?.onboardingComplete === true || (!raw && localStorage.getItem('openclaw-onboarding-complete') === 'true');
    const status: OnboardingStatus = ['incomplete', 'saved_unverified', 'skipped', 'legacy_unverified'].includes(state?.onboardingStatus)
      ? state.onboardingStatus : complete ? 'legacy_unverified' : 'incomplete';
    return {
      devMode: state?.devMode === true,
      sidebarCollapsed: state?.sidebarCollapsed === true,
      onboardingComplete: complete,
      onboardingStatus: status,
      onboardingFeatures: features(state?.onboardingFeatures),
    };
  } catch {
    return { ...defaults, onboardingFeatures: [...defaults.onboardingFeatures] };
  }
}

interface AppState extends Preferences {
  currentPage: PageType;
  envStatus: EnvironmentStatus | null;
  serviceStatus: ServiceStatus | null;
  isReady: boolean | null;
  navigationGuard: NavigationGuard | null;
  setCurrentPage: (page: PageType) => void;
  recordOnboardingSave: (selected: string[]) => void;
  completeOnboarding: (status: 'saved_unverified' | 'skipped', selected: string[]) => void;
  setEnvStatus: (status: EnvironmentStatus | null) => void;
  setServiceStatus: (status: ServiceStatus | null) => void;
  setIsReady: (ready: boolean | null) => void;
  setNavigationGuard: (guard: NavigationGuard | null) => void;
  toggleSidebar: () => void;
  setDevMode: (enabled: boolean) => void;
  toggleDevMode: () => void;
}

export const useAppStore = create<AppState>()((set, get) => {
  // Zustand's default persist updates memory before storage. Here a failed write
  // must leave the welcome gate in place, so commit the same persisted format first.
  const commit = (patch: Partial<Preferences>) => {
    const candidate = { ...get(), ...patch };
    const value = JSON.stringify({ state: {
      devMode: candidate.devMode, sidebarCollapsed: candidate.sidebarCollapsed,
      onboardingComplete: candidate.onboardingComplete,
      onboardingStatus: candidate.onboardingStatus,
      onboardingFeatures: features(candidate.onboardingFeatures),
    }, version: 0 });
    const previous = localStorage.getItem(STORE_KEY);
    try {
      localStorage.setItem(STORE_KEY, value);
      if (localStorage.getItem(STORE_KEY) !== value) throw new Error('Preference readback failed');
    } catch {
      try {
        if (previous === null) localStorage.removeItem(STORE_KEY);
        else localStorage.setItem(STORE_KEY, previous);
      } catch { /* Keep the in-memory gate closed even when storage is unavailable. */ }
      throw new Error('Preference persistence failed');
    }
    set(patch);
  };
  return {
    ...readPreferences(), currentPage: 'home', envStatus: null, serviceStatus: null,
    isReady: null, navigationGuard: null,
    setCurrentPage: (page) => { trackClick(`nav:${page}`); trackPageLoad(page, 0); set({ currentPage: page }); },
    recordOnboardingSave: (selected) => commit({ onboardingStatus: 'saved_unverified', onboardingFeatures: features(selected) }),
    completeOnboarding: (status, selected) => {
      if (status === 'saved_unverified' && get().onboardingStatus !== 'saved_unverified') {
        throw new Error('Configuration has not been saved');
      }
      commit({ onboardingComplete: true, onboardingStatus: status, onboardingFeatures: features(selected) });
    },
    setEnvStatus: (envStatus) => set({ envStatus }),
    setServiceStatus: (serviceStatus) => set({ serviceStatus }),
    setIsReady: (isReady) => set({ isReady }),
    setNavigationGuard: (navigationGuard) => set({ navigationGuard }),
    toggleSidebar: () => commit({ sidebarCollapsed: !get().sidebarCollapsed }),
    setDevMode: (devMode) => commit({ devMode }),
    toggleDevMode: () => commit({ devMode: !get().devMode }),
  };
});

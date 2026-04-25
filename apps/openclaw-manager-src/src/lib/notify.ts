/**
 * 前端通知总线：写入内存队列 + 弹出可见 toast 浮层 + macOS 原生通知。
 */

import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification';

// ── macOS 原生通知 ──

/**
 * 发送操作系统级原生通知（macOS Notification Center）。
 * 在非 Tauri 环境或权限未授予时静默降级。
 */
export async function showNativeNotification(title: string, body: string): Promise<void> {
  try {
    let permitted = await isPermissionGranted();
    if (!permitted) {
      const permission = await requestPermission();
      permitted = permission === 'granted';
    }
    if (permitted) {
      sendNotification({ title, body });
    }
  } catch {
    // 非 Tauri 环境或插件不可用 — 静默忽略
  }
}

// ── 前端内存通知队列 ──

export type FrontendNotificationLevel = 'info' | 'warning' | 'error' | 'success';
export type FrontendNotificationChannel = 'log' | 'notification';

export interface FrontendNotificationItem {
  id: string;
  title: string;
  body: string;
  level: FrontendNotificationLevel;
  source: string;
  category: string;
  channel: FrontendNotificationChannel;
  read: boolean;
  created_at: string;
}

interface NotifyOptions {
  description?: string;
  duration?: number;
  channel?: FrontendNotificationChannel;
}

interface PromiseMessages<T> {
  loading: string;
  success: string | ((value: T) => string);
  error: string | ((error: unknown) => string);
}

const MAX_FRONTEND_NOTIFICATIONS = 200;
const SOURCE = 'frontend';
const CATEGORY = 'system';

let sequence = 0;
const listeners = new Set<() => void>();
const notifications: FrontendNotificationItem[] = [];

function notifyListeners() {
  for (const listener of listeners) {
    listener();
  }
}

function buildNotification(
  level: FrontendNotificationLevel,
  title: string,
  body?: string,
  channel: FrontendNotificationChannel = 'log',
): FrontendNotificationItem {
  sequence += 1;
  return {
    id: `frontend-${sequence}`,
    title,
    body: body || title,
    level,
    source: SOURCE,
    category: CATEGORY,
    channel,
    read: false,
    created_at: new Date().toISOString(),
  };
}

function pushNotification(level: FrontendNotificationLevel, title: string, options?: NotifyOptions): string {
  const channel = options?.channel ?? (level === 'warning' || level === 'error' ? 'notification' : 'log');
  const entry = buildNotification(level, title, options?.description, channel);
  notifications.unshift(entry);
  if (notifications.length > MAX_FRONTEND_NOTIFICATIONS) {
    notifications.length = MAX_FRONTEND_NOTIFICATIONS;
  }
  notifyListeners();
  // 可见 toast 浮层
  showVisualToast(level, title, options?.duration);
  return entry.id;
}

/** 在页面右上角弹出一个 3 秒自动消失的 toast */
function showVisualToast(level: FrontendNotificationLevel, text: string, duration?: number) {
  if (typeof document === 'undefined') return;
  const COLORS: Record<string, string> = {
    success: '#00ffaa',
    error: '#ff4d4f',
    warning: '#fbbf24',
    info: '#00d4ff',
  };
  const color = COLORS[level] || COLORS.info;
  const el = document.createElement('div');
  el.textContent = text;
  Object.assign(el.style, {
    position: 'fixed',
    top: '16px',
    right: '16px',
    zIndex: '99999',
    padding: '10px 18px',
    borderRadius: '10px',
    fontFamily: 'monospace',
    fontSize: '12px',
    fontWeight: '600',
    color,
    background: 'rgba(10,10,10,0.92)',
    border: `1px solid ${color}33`,
    boxShadow: `0 4px 24px ${color}22`,
    backdropFilter: 'blur(12px)',
    transform: 'translateX(120%)',
    transition: 'transform 0.3s ease, opacity 0.3s ease',
    opacity: '0',
    maxWidth: '360px',
    pointerEvents: 'none' as const,
  });
  document.body.appendChild(el);
  requestAnimationFrame(() => {
    el.style.transform = 'translateX(0)';
    el.style.opacity = '1';
  });
  setTimeout(() => {
    el.style.transform = 'translateX(120%)';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 400);
  }, duration ?? 3000);
}

function resolveMessage<T>(value: string | ((arg: T) => string), arg: T): string {
  return typeof value === 'function' ? value(arg) : value;
}

export function getFrontendNotifications(): FrontendNotificationItem[] {
  return [...notifications];
}

export function subscribeFrontendNotifications(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function markFrontendNotificationRead(notificationId: string): boolean {
  const target = notifications.find((item) => item.id === notificationId);
  if (!target) {
    return false;
  }
  target.read = true;
  notifyListeners();
  return true;
}

export function markAllFrontendNotificationsRead(): number {
  let count = 0;
  for (const item of notifications) {
    if (!item.read) {
      item.read = true;
      count += 1;
    }
  }
  if (count > 0) {
    notifyListeners();
  }
  return count;
}

export const toast = {
  success(message: string, options?: NotifyOptions) {
    return pushNotification('success', message, options);
  },
  error(message: string, options?: NotifyOptions) {
    return pushNotification('error', message, options);
  },
  warning(message: string, options?: NotifyOptions) {
    return pushNotification('warning', message, options);
  },
  info(message: string, options?: NotifyOptions) {
    return pushNotification('info', message, options);
  },
  message(message: string, options?: NotifyOptions) {
    return pushNotification('info', message, options);
  },
  dismiss(_id?: string) {
    return;
  },
  promise<T>(promise: Promise<T>, messages: PromiseMessages<T>) {
    pushNotification('info', messages.loading);
    return promise.then((value) => {
      pushNotification('success', resolveMessage(messages.success, value));
      return value;
    }).catch((error: unknown) => {
      pushNotification('error', resolveMessage(messages.error, error));
      throw error;
    });
  },
};

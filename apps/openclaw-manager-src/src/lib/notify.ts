/**
 * 前端通知总线：保留 toast 风格调用方式，但不再弹全局提示。
 * 所有前端通知统一写入通知中心和日志页使用的本地内存队列。
 */

export type FrontendNotificationLevel = 'info' | 'warning' | 'error' | 'success';

export interface FrontendNotificationItem {
  id: string;
  title: string;
  body: string;
  level: FrontendNotificationLevel;
  source: string;
  category: string;
  read: boolean;
  created_at: string;
}

interface NotifyOptions {
  description?: string;
  duration?: number;
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
): FrontendNotificationItem {
  sequence += 1;
  return {
    id: `frontend-${sequence}`,
    title,
    body: body || title,
    level,
    source: SOURCE,
    category: CATEGORY,
    read: false,
    created_at: new Date().toISOString(),
  };
}

function pushNotification(level: FrontendNotificationLevel, title: string, options?: NotifyOptions): string {
  const entry = buildNotification(level, title, options?.description);
  notifications.unshift(entry);
  if (notifications.length > MAX_FRONTEND_NOTIFICATIONS) {
    notifications.length = MAX_FRONTEND_NOTIFICATIONS;
  }
  notifyListeners();
  return entry.id;
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

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/stores/appStore';

/**
 * 可见性感知轮询 Hook
 * 只在当前页面激活时执行轮询，切换到其他页面自动暂停
 * @param pageName - 页面标识，必须与 appStore 中的 currentPage 对应
 * @param callback - 轮询回调函数
 * @param interval - 轮询间隔（毫秒），默认 30000
 */
export function useActivePagePolling(
  pageName: string,
  callback: () => void | Promise<void>,
  interval: number = 30000
) {
  const currentPage = useAppStore((s) => s.currentPage);
  const isActive = currentPage === pageName;
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (!isActive) {
      // 非活动页面：清除定时器
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    // 活动页面：启动轮询，立即执行一次
    callbackRef.current();
    timerRef.current = setInterval(() => {
      callbackRef.current();
    }, interval);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isActive, interval]);
}

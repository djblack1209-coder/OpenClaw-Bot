import { useEffect, useCallback } from 'react';
import { useAppStore } from '../stores/appStore';
import { api } from '../lib/tauri';
import { serviceLogger } from '../lib/logger';

export function useService() {
  const { serviceStatus, setServiceStatus } = useAppStore();

  const fetchStatus = useCallback(async () => {
    try {
      const status = await api.getServiceStatus();
      setServiceStatus(status);
      serviceLogger.state('服务状态更新', { running: status.running, pid: status.pid });
    } catch (error) {
      serviceLogger.debug('获取服务状态失败', error);
    }
  }, [setServiceStatus]);

  const start = useCallback(async () => {
    serviceLogger.action('启动服务');
    serviceLogger.info('正在启动服务...');
    try {
      const result = await api.startService();
      serviceLogger.info('✅ 服务启动成功', result);
      await fetchStatus();
      return true;
    } catch (error) {
      serviceLogger.error('❌ 启动服务失败', error);
      throw error;
    }
  }, [fetchStatus]);

  const stop = useCallback(async () => {
    serviceLogger.action('停止服务');
    serviceLogger.info('正在停止服务...');
    try {
      const result = await api.stopService();
      serviceLogger.info('✅ 服务已停止', result);
      await fetchStatus();
      return true;
    } catch (error) {
      serviceLogger.error('❌ 停止服务失败', error);
      throw error;
    }
  }, [fetchStatus]);

  const restart = useCallback(async () => {
    serviceLogger.action('重启服务');
    serviceLogger.info('正在重启服务...');
    try {
      const result = await api.restartService();
      serviceLogger.info('✅ 服务已重启', result);
      await fetchStatus();
      return true;
    } catch (error) {
      serviceLogger.error('❌ 重启服务失败', error);
      throw error;
    }
  }, [fetchStatus]);

  // 自动刷新状态
  useEffect(() => {
    serviceLogger.debug('启动状态自动刷新');
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => {
      serviceLogger.debug('停止状态自动刷新');
      clearInterval(interval);
    };
  }, [fetchStatus]);

  return {
    status: serviceStatus,
    isRunning: serviceStatus?.running ?? false,
    fetchStatus,
    start,
    stop,
    restart,
  };
}

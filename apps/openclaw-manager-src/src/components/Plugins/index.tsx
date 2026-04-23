/**
 * Plugins — MCP 插件管理（已合并到统一插件商店）
 * 自动跳转到 Store 页面的 MCP 标签页
 */
import { useEffect } from 'react';
import { useAppStore } from '../../stores/appStore';

export function Plugins() {
  useEffect(() => {
    /* 自动跳转到插件商店页面 */
    useAppStore.getState().setCurrentPage('store');
  }, []);

  return null;
}

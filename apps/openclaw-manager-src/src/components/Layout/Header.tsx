import { useState, useEffect } from 'react';
import { PageType } from '../../App';
import { ExternalLink, Loader2 } from 'lucide-react';
import { open } from '@tauri-apps/plugin-shell';
import { invoke } from '@tauri-apps/api/core';
import { createLogger } from '@/lib/logger';
import { useAppStore } from '@/stores/appStore';
import { useLanguage } from '@/i18n';

const headerLogger = createLogger('Header');

interface HeaderProps {
  currentPage: PageType;
}

export function Header({ currentPage }: HeaderProps) {
  const { t } = useLanguage();
  const title = t(`header.${currentPage}.title`);
  const [opening, setOpening] = useState(false);
  const [clock, setClock] = useState('');
  const serviceStatus = useAppStore((s) => s.serviceStatus);
  const isRunning = serviceStatus?.running ?? false;

  /* 实时时钟 — 每秒更新 */
  useEffect(() => {
    const tick = () => {
      setClock(
        new Date().toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }),
      );
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  /* 打开 Web Dashboard */
  const handleOpenDashboard = async () => {
    setOpening(true);
    try {
      const url = await invoke<string>('get_dashboard_url');
      await open(url);
    } catch (e) {
      headerLogger.error('打开 Dashboard 失败:', e);
      const fallbackPort = import.meta.env.VITE_DASHBOARD_PORT || '18790';
      window.open(`http://localhost:${fallbackPort}`, '_blank');
    } finally {
      setOpening(false);
    }
  };

  return (
    <header
      className="h-12 flex items-center justify-between px-6 titlebar-drag"
      style={{
        background: 'rgba(2, 2, 2, 0.6)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--glass-border)',
      }}
    >
      {/* 左侧：页面标题 */}
      <div className="titlebar-no-drag flex items-center gap-3">
        <h2
          className="font-display font-bold text-base"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h2>
      </div>

      {/* 右侧：时钟 + 连接状态 + 控制面板按钮 */}
      <div className="flex items-center gap-4 titlebar-no-drag">
        {/* 实时时钟 */}
        <span
          className="font-mono tabular-nums text-xs tracking-wider"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {clock}
        </span>

        {/* 连接状态圆点 */}
        <div className="flex items-center gap-1.5">
          <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          <span
            className="font-mono text-[10px] uppercase tracking-wider"
            style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}
          >
            {isRunning ? '已连接' : '离线'}
          </span>
        </div>

        {/* 控制面板按钮 */}
        <button
          onClick={handleOpenDashboard}
          disabled={opening}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg font-mono text-[11px] transition-all duration-200 disabled:opacity-50"
          style={{
            background: 'rgba(255,255,255,0.04)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--glass-border)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--glass-border-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--glass-border)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          title={t('header.openDashboard')}
        >
          {opening ? <Loader2 size={12} className="animate-spin" /> : <ExternalLink size={12} />}
          <span>{t('header.controlPanel')}</span>
        </button>
      </div>
    </header>
  );
}

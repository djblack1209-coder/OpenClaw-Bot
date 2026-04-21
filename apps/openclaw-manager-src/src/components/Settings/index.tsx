/**
 * Settings — 系统设置页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 所有数据来自真实后端 API
 */
import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  User, Shield, Cpu, HardDrive, Wifi, Key, Bell,
  Settings2, Download, RotateCcw, Trash2, FileText,
  Stethoscope, Check, MemoryStick, Loader2, Save,
  Languages, ExternalLink, KeyRound,
  Power, PlayCircle, StopCircle, AlertTriangle,
} from 'lucide-react';
import { toast } from '@/lib/notify';
import { api } from '../../lib/api';
import { useAppStore } from '../../stores/appStore';
import { controlAllManagedServices } from '@/lib/tauri-ipc';
import { isTauri } from '@/lib/tauri-core';
import { useLanguage } from '@/i18n';
import type { Language } from '@/i18n';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 需要展示的环境变量 Key ====== */
const ENV_KEYS = [
  { key: 'OPENAI_API_KEY', name: 'OpenAI' },
  { key: 'ANTHROPIC_API_KEY', name: 'Anthropic' },
  { key: 'DEEPSEEK_API_KEY', name: 'DeepSeek' },
  { key: 'IBKR_ACCOUNT', name: 'IBKR' },
];

/* ====== 操作按钮定义 ====== */
const ACTION_BUTTONS = [
  { id: 'export', labelKey: 'settings.exportConfigBtn', icon: Download, accent: 'var(--accent-cyan)' },
  { id: 'reset', labelKey: 'settings.resetSettingsBtn', icon: RotateCcw, accent: 'var(--accent-amber)' },
  { id: 'cache', labelKey: 'settings.clearCacheBtn', icon: Trash2, accent: 'var(--accent-red)' },
  { id: 'logs', labelKey: 'settings.viewLogsBtn', icon: FileText, accent: 'var(--accent-purple)' },
  { id: 'diag', labelKey: 'settings.systemDiagBtn', icon: Stethoscope, accent: 'var(--accent-green)' },
];

/* ====== 辅助：遮蔽密钥显示 ====== */
function maskKey(val: string | null | undefined): string {
  if (!val) return '—';
  if (val.length <= 8) return '****';
  return val.slice(0, 4) + '...' + val.slice(-4);
}

/* ====== 主组件 ====== */
interface SettingsProps {
  onEnvironmentChange?: () => void;
}

export function Settings(_props: SettingsProps) {
  /* —— i18n —— */
  const { t, lang, setLang } = useLanguage();

  /* —— 状态 —— */
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<Record<string, any>>({});
  const [envKeys, setEnvKeys] = useState<{ key: string; name: string; value: string }[]>([]);
  const [sysInfo, setSysInfo] = useState<Record<string, any> | null>(null);
  const [perf, setPerf] = useState<{ cpu: number; memUsed: number; memTotal: number; diskUsed: number; diskTotal: number } | null>(null);
  const [notifications, setNotifications] = useState<{ id: string; labelKey: string; enabled: boolean }[]>([
    { id: 'telegram', labelKey: 'settings.telegramNotifLabel', enabled: true },
    { id: 'email', labelKey: 'settings.emailNotifLabel', enabled: false },
    { id: 'trade', labelKey: 'settings.tradeAlertLabel', enabled: true },
    { id: 'error', labelKey: 'settings.errorAlertLabel', enabled: true },
  ]);

  /* —— 首次加载 —— */
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      /* 并发拉取所有数据 */
      const [cfgRes, sysRes, perfRes, ...envResults] = await Promise.allSettled([
        api.getConfig(),
        api.getSystemInfo(),
        api.perfMetrics(),
        ...ENV_KEYS.map((e) => api.getEnvValue(e.key)),
      ]);

      if (cfgRes.status === 'fulfilled') setConfig(cfgRes.value as Record<string, any>);
      if (sysRes.status === 'fulfilled') setSysInfo(sysRes.value as Record<string, any>);
      if (perfRes.status === 'fulfilled') {
        const p = perfRes.value as any;
        setPerf({
          cpu: p.cpu_percent ?? p.cpu ?? 0,
          memUsed: p.memory_used_mb ?? p.mem_used ?? 0,
          memTotal: p.memory_total_mb ?? p.mem_total ?? 8192,
          diskUsed: p.disk_used_gb ?? p.disk_used ?? 0,
          diskTotal: p.disk_total_gb ?? p.disk_total ?? 256,
        });
      }

      /* 环境变量 */
      const envList = ENV_KEYS.map((e, i) => {
        const r = envResults[i];
        const raw = r.status === 'fulfilled' ? String(r.value ?? '') : '';
        return { key: e.key, name: e.name, value: raw };
      });
      setEnvKeys(envList);

      /* 从 config 中提取通知开关（如果后端有） */
      if (cfgRes.status === 'fulfilled') {
        const c = cfgRes.value as any;
        if (c.notifications) {
          setNotifications((prev) =>
            prev.map((n) => ({
              ...n,
              enabled: c.notifications?.[n.id] ?? n.enabled,
            })),
          );
        }
      }
    } catch (err) {
      console.error('[Settings] 加载失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  /* —— 操作按钮处理 —— */
  const handleAction = useCallback(async (actionId: string) => {
    switch (actionId) {
      case 'export':
        try {
          const cfg = await api.getConfig();
          const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = 'openclaw-config.json'; a.click();
          URL.revokeObjectURL(url);
          toast.success(t('settings.configExported'), { channel: 'log' });
        } catch { toast.error(t('settings.configExportFailed'), { channel: 'notification' }); }
        break;
      case 'reset':
        /* 重置所有设置：清除本地缓存 + 后端配置，刷新页面 */
        if (window.confirm(t('settings.confirmReset'))) {
          try {
            localStorage.clear();
            await api.saveConfig({});
            toast.success(t('settings.resetSuccess'), { channel: 'log' });
            setTimeout(() => window.location.reload(), 1000);
          } catch (e) {
            toast.error(t('settings.resetFailed') + ': ' + String(e), { channel: 'notification' });
          }
        }
        break;
      case 'cache':
        try {
          localStorage.clear();
          toast.success(t('settings.cacheCleared'), { channel: 'log' });
          setTimeout(() => window.location.reload(), 1000);
        } catch { toast.error(t('settings.cacheClearFailed'), { channel: 'notification' }); }
        break;
      case 'logs':
        /* 跳转到日志页面 */
        useAppStore.getState().setCurrentPage('logs');
        break;
      case 'diag':
        try {
          const perf = await api.perfMetrics();
          toast.success(`${t('settings.diagComplete')} — CPU: ${(perf as any).cpu_percent ?? 0}%, ${t('settings.memLabel')}: ${(perf as any).memory_used_mb ?? 0}MB`, { channel: 'log' });
        } catch { toast.error(t('settings.diagFailed'), { channel: 'notification' }); }
        break;
    }
  }, []);

  /* —— 保存配置 —— */
  const handleSave = async () => {
    setSaving(true);
    try {
      const notifConfig: Record<string, boolean> = {};
      notifications.forEach((n) => { notifConfig[n.id] = n.enabled; });
      await api.saveConfig({ ...config, notifications: notifConfig });
    } catch (err) {
      console.error('[Settings] 保存失败:', err);
    } finally {
      setSaving(false);
    }
  };

  /* —— 通知开关 —— */
  const toggleNotification = (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, enabled: !n.enabled } : n)),
    );
  };

  /* —— 渲染 —— */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      </div>
    );
  }

  const osLabel = sysInfo?.os ?? '—';
  const nodeVer = sysInfo?.node_version ?? '—';
  const pyVer = (sysInfo as any)?.python_version ?? (sysInfo as any)?.openclaw_version ?? '—';
  const uptime = sysInfo?.uptime ?? (config as any)?.uptime ?? '—';

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== Row 1: 账户信息 (span-8) + 系统状态 (span-4) ====== */}

        {/* 账户信息 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.15)' }}>
                <User size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('settings.accountTitle')}
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('settings.accountSubtitle')}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <InfoBlock label={t('settings.osLabel')} value={osLabel} accent="var(--accent-cyan)" />
              <InfoBlock label={t('settings.nodeLabel')} value={nodeVer} accent="var(--accent-purple)" />
              <InfoBlock label={t('settings.pythonLabel')} value={pyVer} accent="var(--accent-green)" />
              <InfoBlock label={t('settings.uptimeLabel')} value={String(uptime)} accent="var(--accent-amber)" />
              <InfoBlock label={t('settings.archLabel')} value={sysInfo?.arch ?? '—'} accent="var(--text-secondary)" />
              <InfoBlock label={t('settings.configDirLabel')} value={sysInfo?.config_dir ?? '—'} accent="var(--accent-cyan)" />
            </div>
          </div>
        </motion.div>

        {/* 系统状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Cpu size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                {t('settings.systemStatusLabel')}
              </span>
            </div>
            <div className="space-y-4">
              <ResourceBar icon={Cpu} label={t('settings.cpuUsageLabel')}
                value={perf?.cpu ?? 0} max={100} unit="%" accent="var(--accent-cyan)" />
              <ResourceBar icon={MemoryStick} label={t('settings.memLabel')}
                value={+(((perf?.memUsed ?? 0) / 1024).toFixed(1))}
                max={+(((perf?.memTotal ?? 8192) / 1024).toFixed(1))}
                unit="GB" accent="var(--accent-purple)" />
              <ResourceBar icon={HardDrive} label={t('settings.diskLabel')}
                value={perf?.diskUsed ?? 0} max={perf?.diskTotal ?? 256} unit="GB" accent="var(--accent-amber)" />

              {/* 网络状态 */}
              <div className="flex items-center gap-3 p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
                <Wifi size={14} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>
                  {t('settings.networkStatus')}
                </span>
                <div className="flex items-center gap-1.5">
                  <div className="relative">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--accent-green)' }} />
                    <div className="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-30"
                      style={{ background: 'var(--accent-green)' }} />
                  </div>
                  <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-green)' }}>
                    {t('settings.networkOnline')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: API 密钥 (span-4) + 通知设置 (span-4) + 高级设置 (span-4) ====== */}

        {/* API 密钥管理 — 真实环境变量 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Key size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                {t('settings.apiKeysLabel')}
              </span>
            </div>
            <div className="space-y-3">
              {envKeys.map((ek) => {
                const configured = !!ek.value;
                return (
                  <div key={ek.key}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: 'var(--bg-base)' }}>
                    <div className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: configured ? 'rgba(0,255,170,0.12)' : 'rgba(255,0,60,0.12)' }}>
                      {configured
                        ? <Check size={12} style={{ color: 'var(--accent-green)' }} />
                        : <Shield size={12} style={{ color: 'var(--accent-red)' }} />}
                    </div>
                    <span className="font-mono text-xs font-medium flex-1" style={{ color: 'var(--text-primary)' }}>
                      {ek.name}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {maskKey(ek.value)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* 通知设置 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Bell size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                {t('settings.notificationsLabel')}
              </span>
            </div>
            <div className="space-y-3">
              {notifications.map((item) => (
                <div key={item.id}
                  className="flex items-center justify-between p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {t(item.labelKey)}
                  </span>
                  <div
                    className="w-9 h-5 rounded-full relative transition-colors cursor-pointer"
                    onClick={() => toggleNotification(item.id)}
                    style={{ background: item.enabled ? 'var(--accent-cyan)' : 'var(--dark-500)' }}>
                    <div className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
                      style={{
                        background: 'var(--text-primary)',
                        left: item.enabled ? '18px' : '2px',
                      }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 高级设置 — 从真实 config 读取 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Settings2 size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                {t('settings.advancedLabel')}
              </span>
            </div>
            <div className="space-y-3">
              {[
                { label: t('settings.devModeLabel'), value: config.dev_mode ?? false, type: 'toggle' as const },
                { label: t('settings.logLevelLabel'), value: config.log_level ?? 'INFO', type: 'text' as const },
                { label: t('settings.autoUpdateLabel'), value: config.auto_update ?? true, type: 'toggle' as const },
                { label: t('settings.dataBackupLabel'), value: config.backup_interval ?? t('settings.backupDaily'), type: 'text' as const },
              ].map((item) => (
                <div key={item.label}
                  className="flex items-center justify-between p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {item.label}
                  </span>
                  {item.type === 'toggle' ? (
                    <div className="w-9 h-5 rounded-full relative transition-colors cursor-pointer"
                      onClick={() => {
                        if (item.label === t('settings.devModeLabel')) setConfig(c => ({ ...c, dev_mode: !c.dev_mode }));
                        else if (item.label === t('settings.autoUpdateLabel')) setConfig(c => ({ ...c, auto_update: !c.auto_update }));
                      }}
                      style={{ background: item.value ? 'var(--accent-cyan)' : 'var(--dark-500)' }}>
                      <div className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
                        style={{
                          background: 'var(--text-primary)',
                          left: item.value ? '18px' : '2px',
                        }} />
                    </div>
                  ) : (
                    <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-cyan)' }}>
                      {String(item.value)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2.5: 语言切换 (span-12) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Languages size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                {t('settings.language').toUpperCase()}
              </span>
            </div>
            <div className="space-y-3">
              {([
                { value: 'zh-CN' as Language, label: t('settings.langZh') },
                { value: 'en-US' as Language, label: t('settings.langEn') },
              ]).map((option) => {
                const isSelected = lang === option.value;
                return (
                  <div
                    key={option.value}
                    className="flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all"
                    style={{
                      background: isSelected ? 'rgba(0,212,255,0.08)' : 'var(--bg-base)',
                      border: isSelected ? '1px solid rgba(0,212,255,0.2)' : '1px solid transparent',
                    }}
                    onClick={() => setLang(option.value)}
                  >
                    <span className="font-mono text-xs" style={{ color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                      {option.label}
                    </span>
                    {isSelected && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center"
                        style={{ background: 'rgba(0,212,255,0.15)' }}>
                        <Check size={12} style={{ color: 'var(--accent-cyan)' }} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2.6: 账号登录 — 一键打开登录页 (span-8) ====== */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,255,170,0.15)' }}>
                <KeyRound size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('settings.accountLoginTitle')}
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('settings.accountLoginDesc')}
                </p>
              </div>
            </div>

            {/* 主按钮 */}
            <button
              onClick={() => {
                const urls = [
                  'https://goofish.com',
                  'https://x.com/login',
                  'https://www.xiaohongshu.com',
                ];
                urls.forEach(url => window.open(url, '_blank'));
                toast.success(t('settings.openedLoginPages'), { channel: 'log' });
              }}
              className="flex items-center gap-2.5 px-5 py-3 rounded-xl font-mono text-xs font-bold transition-all cursor-pointer w-full justify-center mb-4"
              style={{
                background: 'var(--accent-green)',
                color: 'var(--bg-primary)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.opacity = '0.85';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.opacity = '1';
              }}>
              <ExternalLink size={16} />
              {t('settings.openAllLoginPages')}
            </button>

            {/* 单独平台按钮 */}
            <div className="flex flex-wrap gap-3 mb-4">
              {[
                { name: t('settings.platformXianyu'), url: 'https://goofish.com' },
                { name: t('settings.platformX'), url: 'https://x.com/login' },
                { name: t('settings.platformXiaohongshu'), url: 'https://www.xiaohongshu.com' },
              ].map((platform) => (
                <button
                  key={platform.name}
                  onClick={() => {
                    window.open(platform.url, '_blank');
                    toast.success(`${t('settings.openedPlatformLogin')}: ${platform.name}`, { channel: 'log' });
                  }}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl transition-all cursor-pointer"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--glass-border)',
                    color: 'var(--text-secondary)',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent-cyan)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--accent-cyan)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--glass-border)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                  }}>
                  <span className="font-mono text-xs font-medium">{platform.name}</span>
                  <ExternalLink size={12} />
                </button>
              ))}
            </div>

            {/* 提示信息 */}
            <p className="font-mono text-[11px] leading-relaxed px-1" style={{ color: 'var(--text-disabled)' }}>
              {t('settings.loginCookieHint')}
            </p>
          </div>
        </motion.div>

        {/* ====== 一键启动/停止所有服务 ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,255,170,0.15)' }}>
                <Power size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('settings.serviceControlTitle')}
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('settings.serviceControlDesc')}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={async () => {
                  toast.info(t('settings.startingAllServices'), { channel: 'log' });
                  try {
                    const result = await controlAllManagedServices('start');
                    toast.success(t('settings.allServicesStarted'), { channel: 'log' });
                    console.log('[Settings] startAll:', result);
                  } catch (err) {
                    toast.error(`${t('settings.startFailed')}: ${err}`, { channel: 'notification' });
                  }
                }}
                className="flex items-center gap-2.5 px-6 py-3 rounded-xl font-mono text-xs font-bold transition-all cursor-pointer"
                style={{ background: 'var(--accent-green)', color: 'var(--bg-primary)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}>
                <PlayCircle size={16} />
                {t('settings.startAllServices')}
              </button>
              <button
                onClick={async () => {
                  toast.info(t('settings.stoppingAllServices'), { channel: 'log' });
                  try {
                    const result = await controlAllManagedServices('stop');
                    toast.success(t('settings.allServicesStopped'), { channel: 'log' });
                    console.log('[Settings] stopAll:', result);
                  } catch (err) {
                    toast.error(`${t('settings.stopFailed')}: ${err}`, { channel: 'notification' });
                  }
                }}
                className="flex items-center gap-2.5 px-6 py-3 rounded-xl font-mono text-xs font-bold transition-all cursor-pointer"
                style={{ background: 'rgba(255,0,0,0.08)', border: '1px solid rgba(255,0,0,0.25)', color: 'var(--accent-red)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent-red)';
                  (e.currentTarget as HTMLElement).style.background = 'rgba(255,0,0,0.12)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,0,0,0.25)';
                  (e.currentTarget as HTMLElement).style.background = 'rgba(255,0,0,0.08)';
                }}>
                <StopCircle size={16} />
                {t('settings.stopAllServices')}
              </button>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3: 操作区 (span-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Shield size={16} style={{ color: 'var(--text-tertiary)' }} />
              <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
                {t('settings.actionsLabel')}
                </span>
              </div>
              {/* 保存按钮 */}
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-xs font-bold transition-all"
                style={{
                  background: saving ? 'var(--bg-tertiary)' : 'var(--accent-green)',
                  color: 'var(--bg-primary)',
                  opacity: saving ? 0.6 : 1,
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}>
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                {saving ? t('settings.savingBtn') : t('settings.saveSettingsBtn')}
              </button>
            </div>
            <div className="flex flex-wrap gap-3">
              {ACTION_BUTTONS.map((action) => (
                <button key={action.id} onClick={() => handleAction(action.id)}
                  className="flex items-center gap-2.5 px-5 py-3 rounded-xl transition-all cursor-pointer"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--glass-border)',
                    color: action.accent,
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = action.accent;
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--glass-border)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                  }}>
                  <action.icon size={16} />
                  <span className="font-mono text-xs font-medium">{t(action.labelKey)}</span>
                </button>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

/** 账户信息块 */
function InfoBlock({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <span className="text-label block mb-1.5" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </span>
      <span className="font-mono text-sm font-medium truncate block" style={{ color: accent }}>
        {value}
      </span>
    </div>
  );
}

/** 资源使用率条 */
function ResourceBar({
  icon: Icon, label, value, max, unit, accent,
}: { icon: React.ElementType; label: string; value: number; max: number; unit: string; accent: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={12} style={{ color: accent }} />
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>{label}</span>
        </div>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
          {value}{unit} / {max}{unit}
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <motion.div className="h-full rounded-full" style={{ background: accent }}
          initial={{ width: 0 }} animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }} />
      </div>
    </div>
  );
}

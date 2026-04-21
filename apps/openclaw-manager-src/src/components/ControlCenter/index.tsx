/**
 * ControlCenter — 总控中心页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 所有数据来自后端 API，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Power,
  Terminal,
  ToggleLeft,
  ToggleRight,
  FileCode,
  AlertTriangle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import clsx from 'clsx';
import { toast } from '@/lib/notify';
import { clawbotFetchJson, clawbotFetch } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 自动刷新间隔（毫秒） ====== */
const AUTO_REFRESH_MS = 30_000;

/* ====== 类型定义 ====== */

/** 交易控制开关（来自 /api/v1/controls/trading） */
interface TradingControls {
  auto_trader_enabled: boolean;
  ibkr_live_mode: boolean;
  risk_protection_enabled: boolean;
  allow_short_selling: boolean;
  max_daily_trades: number;
  [key: string]: unknown;
}

/** 社交控制开关（来自 /api/v1/controls/social） */
interface SocialControls {
  [key: string]: unknown;
}

/** 服务状态（来自 /api/v1/system/services） */
interface ServiceEntry {
  name: string;
  status: 'online' | 'offline' | 'degraded' | string;
  port?: number;
  cpu?: string;
  mem?: string;
  pid?: number | null;
  uptime?: string;
  [key: string]: unknown;
}

/** 全局设置（来自 /api/v1/controls/settings） */
interface SettingsEntry {
  key: string;
  value: string;
  desc?: string;
  [k: string]: unknown;
}

/** 通知/日志条目（来自 /api/v1/system/notifications） */
interface NotificationEntry {
  time?: string;
  timestamp?: string;
  created_at?: string;
  src?: string;
  source?: string;
  module?: string;
  msg?: string;
  message?: string;
  content?: string;
  level?: string;
  [k: string]: unknown;
}

/** 统一的主开关条目 — 用于 UI 渲染 */
interface MasterSwitch {
  id: string;
  label: string;
  desc: string;
  enabled: boolean;
  color: string;
  locked?: boolean;
  /** 来源分组，用于确定调用哪个 API */
  group: 'trading' | 'social';
  /** 对应 API 中的字段名 */
  apiKey: string;
}

/* ====== 开关元数据映射 ====== */

/** 交易开关的中文标签和颜色 */
const TRADING_SWITCH_META: Record<string, { label: string; desc: string; color: string; locked?: boolean }> = {
  auto_trader_enabled: { label: '自动交易', desc: '量化交易引擎', color: 'var(--accent-cyan)' },
  ibkr_live_mode: { label: 'IBKR 实盘', desc: '实盘 / 模拟盘', color: 'var(--accent-red)' },
  risk_protection_enabled: { label: '风控保护', desc: '不可关闭', color: 'var(--accent-red)', locked: true },
  allow_short_selling: { label: '允许做空', desc: '空头交易权限', color: 'var(--accent-amber)' },
  max_daily_trades: { label: '每日交易上限', desc: '单日最大下单数', color: 'var(--accent-purple)' },
};

/** 社交开关的中文标签和颜色（通用后备） */
const SOCIAL_SWITCH_FALLBACK = { desc: '社交模块开关', color: 'var(--accent-green)' };

/** 社交开关中文名映射（按需扩展） */
const SOCIAL_SWITCH_LABELS: Record<string, string> = {
  xianyu_enabled: '闲鱼客服',
  twitter_enabled: '推特发布',
  telegram_enabled: 'Telegram',
  weibo_enabled: '微博',
  auto_reply_enabled: '自动回复',
  content_publish_enabled: '内容发布',
};

/* ====== 工具函数 ====== */

/** 服务状态指示点 */
function statusDot(status: string) {
  switch (status) {
    case 'online': return { color: 'var(--accent-green)', label: 'controlCenter.statusOnline' };
    case 'offline': return { color: 'var(--text-disabled)', label: 'controlCenter.statusOffline' };
    case 'degraded': return { color: 'var(--accent-amber)', label: 'controlCenter.statusDegraded' };
    default: return { color: 'var(--text-disabled)', label: status };
  }
}

/** 提取通知的时间字符串 */
function extractTime(n: NotificationEntry): string {
  const raw = n.time || n.timestamp || n.created_at || '';
  /* 如果是完整 ISO 时间，只取 HH:MM:SS */
  if (raw.includes('T')) {
    const parts = raw.split('T')[1];
    return parts?.slice(0, 8) ?? raw;
  }
  return raw;
}

/** 提取通知的来源 */
function extractSrc(n: NotificationEntry): string {
  return n.src || n.source || n.module || 'system';
}

/** 提取通知的消息内容 */
function extractMsg(n: NotificationEntry): string {
  return n.msg || n.message || n.content || '';
}

/** 根据日志来源返回颜色 */
function logSrcColor(src: string): string {
  if (src.includes('trad') || src.includes('ibkr')) return 'var(--accent-cyan)';
  if (src.includes('news') || src.includes('rss')) return 'var(--accent-amber)';
  if (src.includes('error') || src.includes('risk')) return 'var(--accent-red)';
  if (src.includes('xianyu') || src.includes('social')) return 'var(--accent-purple)';
  return 'var(--accent-green)';
}

/* ====== 主组件 ====== */

export function ControlCenter() {
  const { t } = useLanguage();
  /* —— 状态 —— */
  const [switches, setSwitches] = useState<MasterSwitch[]>([]);
  const [services, setServices] = useState<ServiceEntry[]>([]);
  const [settings, setSettings] = useState<SettingsEntry[]>([]);
  const [logs, setLogs] = useState<NotificationEntry[]>([]);

  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  /* 用于保存当前完整的 trading/social 控制对象，切换时需要回传 */
  const tradingRef = useRef<TradingControls | null>(null);
  const socialRef = useRef<SocialControls | null>(null);

  /* —— 把 API 数据转换成统一的 MasterSwitch 列表 —— */
  const buildSwitches = useCallback(
    (trading: TradingControls | null, social: SocialControls | null): MasterSwitch[] => {
      const result: MasterSwitch[] = [];

      /* 交易开关 */
      if (trading) {
        for (const [key, value] of Object.entries(trading)) {
          /* 只取布尔值字段作为开关 */
          if (typeof value !== 'boolean') continue;
          const meta = TRADING_SWITCH_META[key] ?? {
            label: key,
            desc: '交易参数',
            color: 'var(--accent-cyan)',
          };
          result.push({
            id: `trading_${key}`,
            label: meta.label,
            desc: meta.desc,
            enabled: value,
            color: meta.color,
            locked: meta.locked,
            group: 'trading',
            apiKey: key,
          });
        }
      }

      /* 社交开关 */
      if (social) {
        for (const [key, value] of Object.entries(social)) {
          if (typeof value !== 'boolean') continue;
          result.push({
            id: `social_${key}`,
            label: SOCIAL_SWITCH_LABELS[key] ?? key,
            desc: SOCIAL_SWITCH_FALLBACK.desc,
            enabled: value,
            color: SOCIAL_SWITCH_FALLBACK.color,
            group: 'social',
            apiKey: key,
          });
        }
      }

      return result;
    },
    [],
  );

  /* —— 拉取全部数据 —— */
  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      /* 并发拉取 4 个 API */
      const [tradingRes, socialRes, servicesRes, settingsRes, logsRes] = await Promise.allSettled([
        clawbotFetchJson<TradingControls>('/api/v1/controls/trading'),
        clawbotFetchJson<SocialControls>('/api/v1/controls/social'),
        clawbotFetchJson<ServiceEntry[]>('/api/v1/system/services'),
        clawbotFetchJson<SettingsEntry[] | Record<string, string>>('/api/v1/controls/settings'),
        clawbotFetchJson<NotificationEntry[]>('/api/v1/system/notifications'),
      ]);

      /* 交易控制 */
      const trading = tradingRes.status === 'fulfilled' ? tradingRes.value : null;
      tradingRef.current = trading;

      /* 社交控制 */
      const social = socialRes.status === 'fulfilled' ? socialRes.value : null;
      socialRef.current = social;

      /* 开关列表 */
      setSwitches(buildSwitches(trading, social));

      /* 服务矩阵 */
      if (servicesRes.status === 'fulfilled') {
        const raw = servicesRes.value;
        /* 后端可能返回数组或包装对象 */
        const list = Array.isArray(raw) ? raw : (raw as any)?.services ?? [];
        setServices(list);
      }

      /* 配置参数 — 后端可能返回数组或 key-value 对象 */
      if (settingsRes.status === 'fulfilled') {
        const raw = settingsRes.value;
        if (Array.isArray(raw)) {
          setSettings(raw);
        } else if (raw && typeof raw === 'object') {
          /* 把 { KEY: VALUE } 转成 [{ key, value }] */
          const arr: SettingsEntry[] = Object.entries(raw).map(([k, v]) => ({
            key: k,
            value: String(v),
          }));
          setSettings(arr);
        }
      }

      /* 日志/通知 */
      if (logsRes.status === 'fulfilled') {
        const raw = logsRes.value;
        const list = Array.isArray(raw) ? raw : (raw as any)?.notifications ?? (raw as any)?.logs ?? [];
        setLogs(list.slice(0, 50)); // 最多展示 50 条
      }
    } catch (err) {
      console.error('[ControlCenter] 拉取数据失败:', err);
      if (!silent) toast.error(t('controlCenter.loadFailed'), { channel: 'notification' });
    } finally {
      setLoading(false);
    }
  }, [buildSwitches]);

  /* —— 初始加载 + 30 秒自动刷新 —— */
  useEffect(() => {
    fetchAll();
    const timer = setInterval(() => fetchAll(true), AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchAll]);

  /* —— 手动刷新 —— */
  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchAll(true);
    setRefreshing(false);
    toast.success(t('controlCenter.dataRefreshed'), { channel: 'log' });
  };

  /* —— 切换开关 —— */
  const toggleSwitch = async (sw: MasterSwitch) => {
    if (sw.locked) {
      toast.warning(t('controlCenter.switchLocked'), { channel: 'notification' });
      return;
    }

    setTogglingId(sw.id);
    const newValue = !sw.enabled;

    try {
      if (sw.group === 'trading' && tradingRef.current) {
        /* 把完整交易控制对象更新后回传 */
        const updated = { ...tradingRef.current, [sw.apiKey]: newValue };
        await clawbotFetch('/api/v1/controls/trading', {
          method: 'POST',
          body: JSON.stringify(updated),
        });
        tradingRef.current = updated;
      } else if (sw.group === 'social' && socialRef.current) {
        const updated = { ...socialRef.current, [sw.apiKey]: newValue };
        await clawbotFetch('/api/v1/controls/social', {
          method: 'POST',
          body: JSON.stringify(updated),
        });
        socialRef.current = updated;
      } else {
        throw new Error('控制数据尚未加载');
      }

      /* 乐观更新 UI */
      setSwitches((prev) =>
        prev.map((s) => (s.id === sw.id ? { ...s, enabled: newValue } : s)),
      );
      toast.success(`${sw.label} ${newValue ? t('controlCenter.enabled') : t('controlCenter.disabled')}`, { channel: 'log' });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('controlCenter.unknownError');
      toast.error(`${t('controlCenter.toggleFailed')} ${sw.label}`, { description: msg, channel: 'notification' });
    } finally {
      setTogglingId(null);
    }
  };

  /* —— 加载态 —— */
  if (loading && switches.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 主开关面板 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(239,68,68,0.15)' }}
              >
                <Power size={20} style={{ color: 'var(--accent-red)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  MASTER SWITCHES
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('controlCenter.masterSwitchesSubtitle')}
                </p>
              </div>
              {/* 刷新按钮 */}
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:opacity-80"
                style={{ background: 'var(--bg-secondary)' }}
                title={t('controlCenter.refreshData')}
              >
                <RefreshCw
                  size={14}
                  className={clsx(refreshing && 'animate-spin')}
                  style={{ color: 'var(--text-tertiary)' }}
                />
              </button>
            </div>

            <div className="flex-1 space-y-2">
              {switches.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('controlCenter.noSwitches')}
                </div>
              )}
              {switches.map((sw) => {
                const isToggling = togglingId === sw.id;
                return (
                  <div
                    key={sw.id}
                    className={clsx(
                      'flex items-center justify-between py-3 px-3 rounded-lg cursor-pointer transition-colors',
                      isToggling && 'opacity-50 pointer-events-none',
                    )}
                    style={{ background: 'var(--bg-secondary)' }}
                    onClick={() => toggleSwitch(sw)}
                  >
                    <div>
                      <p className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {sw.label}
                        {sw.group === 'social' && (
                          <span className="ml-1.5 text-[9px] px-1 py-0.5 rounded"
                            style={{ background: 'var(--bg-tertiary)', color: 'var(--text-disabled)' }}>
                            {t('controlCenter.socialTag')}
                          </span>
                        )}
                      </p>
                      <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {sw.desc}
                      </p>
                    </div>
                    {isToggling ? (
                      <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />
                    ) : sw.enabled ? (
                      <ToggleRight size={28} style={{ color: sw.color }} />
                    ) : (
                      <ToggleLeft size={28} style={{ color: 'var(--text-disabled)' }} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 服务矩阵 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              SERVICE MATRIX
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('controlCenter.serviceMatrix')}
            </h3>

            {/* 表头 */}
            <div
              className="grid grid-cols-5 gap-2 px-3 py-2 rounded-lg mb-1"
              style={{ background: 'var(--bg-tertiary)' }}
            >
              {[t('controlCenter.colServiceName'), t('controlCenter.colStatus'), t('controlCenter.colPort'), 'CPU', t('controlCenter.colMemory')].map((h) => (
                <span key={h} className="text-label" style={{ fontSize: '10px' }}>
                  {h}
                </span>
              ))}
            </div>

            {/* 行列表 */}
            <div className="flex-1 space-y-1">
              {services.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('controlCenter.noServiceData')}
                </div>
              )}
              {services.map((svc) => {
                const dot = statusDot(svc.status);
                return (
                  <div
                    key={svc.name}
                    className="grid grid-cols-5 gap-2 px-3 py-2.5 rounded-lg transition-colors"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                      {svc.name}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ background: dot.color }}
                      />
                      <span className="font-mono text-xs" style={{ color: dot.color }}>
                        {t(dot.label)}
                      </span>
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {svc.port ? `:${svc.port}` : '—'}
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {svc.cpu ?? '—'}
                    </span>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {svc.mem ?? '—'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 配置编辑器 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              RUNTIME CONFIG
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              {t('controlCenter.runtimeConfig')}
            </h3>

            <div className="flex-1 space-y-2">
              {settings.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('controlCenter.noConfigData')}
                </div>
              )}
              {settings.map((p) => (
                <div
                  key={p.key}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center gap-2">
                    <FileCode size={12} style={{ color: 'var(--accent-purple)' }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {p.key}
                    </span>
                    {p.desc && (
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        ({p.desc})
                      </span>
                    )}
                  </div>
                  <span className="font-mono text-xs font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                    {p.value}
                  </span>
                </div>
              ))}
            </div>

            {/* 警告提示 */}
            <div
              className="flex items-start gap-2.5 mt-4 pt-3 border-t"
              style={{ borderColor: 'var(--glass-border)' }}
            >
              <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--accent-amber)' }} />
              <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                {t('controlCenter.configRestartHint')}
              </p>
            </div>
          </div>
        </motion.div>

        {/* ====== 日志观察窗 (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-0 overflow-hidden h-full flex flex-col">
            <div
              className="flex items-center gap-2 px-5 py-3"
              style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--glass-border)' }}
            >
              <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                LOG VIEWER
              </span>
              <span className="ml-auto font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                {t('controlCenter.autoRefresh30s')}
              </span>
            </div>
            <div
              className="flex-1 p-4 space-y-0.5 font-mono text-xs overflow-y-auto"
              style={{ background: 'var(--bg-elevated)' }}
            >
              {logs.length === 0 && (
                <div className="text-center py-8 font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('controlCenter.noLogs')}
                </div>
              )}
              {logs.map((log, i) => {
                const src = extractSrc(log);
                return (
                  <div key={i} className={clsx('py-1 px-2 rounded flex gap-3')}>
                    <span style={{ color: 'var(--text-disabled)' }}>{extractTime(log)}</span>
                    <span
                      className="w-20 shrink-0"
                      style={{ color: logSrcColor(src) }}
                    >
                      [{src}]
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{extractMsg(log)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

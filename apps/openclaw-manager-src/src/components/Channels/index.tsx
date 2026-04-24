/**
 * Channels — 消息渠道页面 (Sonic Abyss Bento Grid 风格)
 * 数据来自 IPC api.getChannelsConfig()，30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  MessageCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  AlertCircle,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';
import { toast } from '@/lib/notify';
import { api } from '../../lib/api';
import type { ChannelConfig } from '../../lib/tauri-core';
import { clawbotFetchJson, isTauri } from '../../lib/tauri-core';
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

/* ====== 常量 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/** 渠道类型 → 图标 & 颜色 映射 */
const CHANNEL_META: Record<string, { icon: string; color: string; label: string }> = {
  telegram:  { icon: '✈', color: 'var(--accent-cyan)',   label: 'Telegram' },
  discord:   { icon: '🎮', color: 'var(--accent-purple)', label: 'Discord' },
  feishu:    { icon: '🪶', color: 'var(--accent-cyan)',   label: '飞书' },
  wechat:    { icon: '💬', color: 'var(--accent-green)',  label: '微信' },
  whatsapp:  { icon: '📱', color: 'var(--accent-green)',  label: 'WhatsApp' },
  xianyu:    { icon: '🐟', color: 'var(--accent-amber)',  label: '闲鱼' },
  email:     { icon: '📧', color: 'var(--accent-purple)', label: 'Email' },
  slack:     { icon: '💼', color: 'var(--accent-amber)',  label: 'Slack' },
  web:       { icon: '🌐', color: 'var(--accent-cyan)',   label: 'Web' },
  imessage:  { icon: '📱', color: 'var(--accent-blue)',   label: 'iMessage' },
  dingtalk:  { icon: '📡', color: 'var(--accent-cyan)',   label: '钉钉' },
};

/** 获取渠道显示信息 */
function getChannelMeta(ch: ChannelConfig) {
  const type = ch.channel_type?.toLowerCase() || ch.id?.toLowerCase() || '';
  const meta = CHANNEL_META[type] || { icon: '📡', color: 'var(--text-secondary)', label: type || ch.id };
  return meta;
}

/* ====== 工具函数 ====== */

function statusInfo(enabled: boolean, hasConfig: boolean) {
  if (enabled && hasConfig) {
    return { label: 'channels.connected', color: 'var(--accent-green)', Icon: CheckCircle2 };
  }
  if (hasConfig) {
    return { label: 'channels.configured', color: 'var(--accent-amber)', Icon: Clock };
  }
  return { label: 'channels.notConfigured', color: 'var(--text-disabled)', Icon: XCircle };
}

/** 判断渠道是否有实质性配置（不只是空对象） */
function hasRealConfig(config: Record<string, unknown>): boolean {
  if (!config || typeof config !== 'object') return false;
  const values = Object.values(config);
  return values.some((v) => v !== null && v !== undefined && v !== '' && v !== false);
}

/* ====== 主组件 ====== */

export function Channels() {
  const { t } = useLanguage();
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [botStatus, setBotStatus] = useState<Record<string, string>>({});
  const [togglingChannelIds, setTogglingChannelIds] = useState<Set<string>>(new Set());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── 拉取渠道配置 + 后端 Bot 运行状态 ── */
  const fetchData = useCallback(async () => {
    try {
      const configs = await api.getChannelsConfig();
      if (Array.isArray(configs)) {
        setChannels(configs);
      }
      setError(null);
    } catch (err) {
      console.error('[Channels] 加载失败:', err);
      const msg = err instanceof Error ? err.message : t('channels.unknownError');
      setError(msg);
      toast.error(t('channels.loadError'), { channel: 'notification' });
    }

    /* 尝试从后端获取各渠道 Bot 运行状态 */
    try {
      const status = await clawbotFetchJson<Record<string, unknown>>('/api/v1/status');
      const bots: Record<string, string> = {};
      if (status && typeof status === 'object') {
        /* 后端 /api/v1/status 可能返回 { services: { telegram: { running: true }, wechat: { running: false } } }
           或顶层 { telegram_running: true, wechat_running: false } — 兼容两种格式 */
        const services = (status.services ?? status) as Record<string, unknown>;
        for (const [key, val] of Object.entries(services)) {
          if (typeof val === 'object' && val !== null && 'running' in val) {
            bots[key] = (val as Record<string, unknown>).running ? 'running' : 'stopped';
          } else if (key.endsWith('_running') && typeof val === 'boolean') {
            bots[key.replace('_running', '')] = val ? 'running' : 'stopped';
          }
        }
      }
      setBotStatus(bots);
    } catch {
      /* Bot 状态获取失败不影响页面展示 */
    }

    setLoading(false);
  }, [t]);

  /* ── 首次加载 + 自动刷新 ── */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData, t]);

  /* ── 渠道启停切换 ── */
  const handleToggleChannel = useCallback(async (ch: ChannelConfig) => {
    if (!isTauri()) {
      toast.error(t('channels.toggleNeedsTauri'), { channel: 'notification' });
      return;
    }
    setTogglingChannelIds((prev) => new Set(prev).add(ch.id));
    try {
      await api.saveChannelConfig({ ...ch, enabled: !ch.enabled });
      toast.success(`${ch.channel_type || ch.id} ${ch.enabled ? t('channels.channelDisabled') : t('channels.channelEnabled')}`, { channel: 'log' });
      // 局部更新状态
      setChannels((prev) =>
        prev.map((c) => c.id === ch.id ? { ...c, enabled: !c.enabled } : c),
      );
    } catch {
      toast.error(t('channels.toggleFailed'), { channel: 'notification' });
      await fetchData();
    } finally {
      setTogglingChannelIds((prev) => {
        const next = new Set(prev);
        next.delete(ch.id);
        return next;
      });
    }
  }, [fetchData, t]);

  /* ── 统计数据（从真实配置计算） ── */
  const connected = channels.filter((ch) => ch.enabled && hasRealConfig(ch.config)).length;
  const configured = channels.filter((ch) => hasRealConfig(ch.config)).length;
  const total = channels.length;
  const botsRunning = Object.values(botStatus).filter((s) => s === 'running').length;

  const msgStats = [
    { label: t('channels.activeChannels'), value: `${connected}/${total}`, color: 'var(--accent-green)' },
    { label: t('channels.configuredCount'), value: String(configured), color: 'var(--accent-purple)' },
    { label: t('channels.botRunning'), value: String(botsRunning), color: 'var(--accent-cyan)' },
    { label: t('channels.botStopped'), value: String(total - botsRunning), color: 'var(--accent-amber)' },
  ];

  /* ── 加载中 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-[var(--accent-cyan)]" size={32} />
        <span className="ml-3 text-[var(--text-secondary)] font-mono text-sm">{t('channels.loadingConfig')}</span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container">
      {error && (
        <div className="mx-6 mt-4 px-4 py-3 rounded-lg font-mono text-xs flex items-center gap-2"
          style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 渠道列表 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <MessageCircle size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  MESSAGE CHANNELS
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('channels.subtitle')}
                </p>
              </div>
              <button
                onClick={() => { setLoading(true); fetchData(); }}
                className="text-[var(--text-tertiary)] hover:text-[var(--accent-cyan)] transition-colors"
                title={t('channels.manualRefresh')}
              >
                <RefreshCw size={14} />
              </button>
            </div>

            {/* 渠道列表 */}
            <div className="flex-1 space-y-2">
              {channels.length === 0 ? (
                <div className="flex items-center justify-center py-16 text-[var(--text-tertiary)] font-mono text-sm">
                  {t('channels.noChannelData')}
                </div>
              ) : (
                channels.map((ch) => {
                  const meta = getChannelMeta(ch);
                  const hasCfg = hasRealConfig(ch.config);
                  const si = statusInfo(ch.enabled, hasCfg);
                  const chType = ch.channel_type?.toLowerCase() || ch.id?.toLowerCase() || '';
                  const runStatus = botStatus[chType];
                  const isWechat = chType === 'wechat';
                  const wechatDown = isWechat && hasCfg && ch.enabled && runStatus !== 'running';
                  return (
                    <div key={ch.id}>
                      <div
                        className="flex items-center justify-between py-3 px-4 rounded-lg transition-colors"
                        style={{ background: 'var(--bg-secondary)' }}
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-xl w-8 text-center">{meta.icon}</span>
                          <div>
                            <p className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                              {t(meta.label)}
                            </p>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <si.Icon size={10} style={{ color: si.color }} />
                              <span className="font-mono text-[10px]" style={{ color: si.color }}>
                                {t(si.label)}
                              </span>
                              {runStatus && (
                                <>
                                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>|</span>
                                  <span
                                    className={`w-1.5 h-1.5 rounded-full ${runStatus === 'running' ? 'animate-pulse' : ''}`}
                                    style={{ background: runStatus === 'running' ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                                  />
                                  <span className="font-mono text-[10px]" style={{ color: runStatus === 'running' ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                                    {runStatus === 'running' ? t('channels.botRunning') : t('channels.botStopped')}
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-6">
                          <div className="text-right">
                            <span className="text-label">{t('channels.colType')}</span>
                            <p className="font-mono text-sm" style={{ color: meta.color }}>
                              {ch.channel_type || '—'}
                            </p>
                          </div>
                          <div className="text-right">
                            <span className="text-label">{t('channels.colEnabled')}</span>
                            <p className="font-mono text-sm" style={{ color: ch.enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                              {ch.enabled ? t('channels.yes') : t('channels.no')}
                            </p>
                          </div>
                          <div className="text-right">
                            <span className="text-label">{t('channels.colConfig')}</span>
                            <p className="font-mono text-sm" style={{ color: hasCfg ? 'var(--accent-cyan)' : 'var(--text-disabled)' }}>
                              {hasCfg ? t('channels.configured') : '—'}
                            </p>
                          </div>
                          {/* 启停开关 */}
                          <div className="flex items-center">
                            <button
                              onClick={() => handleToggleChannel(ch)}
                              disabled={togglingChannelIds.has(ch.id)}
                              className="transition-colors hover:opacity-80 disabled:opacity-50"
                              title={ch.enabled ? '点击禁用' : '点击启用'}
                            >
                              {togglingChannelIds.has(ch.id) ? (
                                <Loader2 size={18} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />
                              ) : ch.enabled ? (
                                <ToggleRight size={22} style={{ color: 'var(--accent-green)' }} />
                              ) : (
                                <ToggleLeft size={22} style={{ color: 'var(--text-disabled)' }} />
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                      {wechatDown && (
                        <div className="mx-4 mt-1 mb-1 px-3 py-2 rounded font-mono text-[10px] flex items-center gap-1.5"
                          style={{ background: 'rgba(245,158,11,0.08)', color: 'var(--accent-amber)' }}>
                          <AlertCircle size={10} />
                          <span>{t('channels.wechatReconnectHint')}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== {t('channels.messageStats')} (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              MESSAGE STATS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              消息统计
            </h3>

            <div className="grid grid-cols-2 gap-4 mb-6">
              {msgStats.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 渠道配置详情 */}
            <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
              CHANNEL DETAILS
            </span>
            <div className="mt-2 flex-1 space-y-1">
              {channels.length === 0 ? (
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">暂无数据</span>
              ) : (
                channels.map((ch) => {
                  const meta = getChannelMeta(ch);
                  const hasCfg = hasRealConfig(ch.config);
                  return (
                    <div key={ch.id} className="flex items-center gap-2">
                      <span className="font-mono text-[10px] w-16 shrink-0" style={{ color: 'var(--text-disabled)' }}>
                        {t(meta.label)}
                      </span>
                      <span
                        className="font-mono text-[10px] flex-1"
                        style={{ color: ch.enabled && hasCfg ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                      >
                        {ch.enabled && hasCfg ? '●' : '○'} {ch.enabled ? t('channels.enabled') : t('channels.disabled')}
                      </span>
                      <span className="font-mono text-[10px] w-12 text-right" style={{ color: 'var(--text-secondary)' }}>
                        {hasCfg ? '✓' : '—'}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== {t('channels.configOverview')} (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              CHANNEL CONFIG OVERVIEW
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              渠道配置概览
            </h3>

            {channels.length === 0 ? (
              <div className="text-center py-10 text-[var(--text-tertiary)] font-mono text-sm">
                {t('channels.noChannelConfig')}
              </div>
            ) : (
              <>
                {/* 表头 */}
                <div
                  className="grid grid-cols-5 gap-3 px-4 py-2 rounded-lg mb-1"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  {[t('channels.colChannel'), t('channels.colType'), t('channels.colEnabled'), t('channels.colConfigStatus'), t('channels.colConfigItems')].map((h) => (
                    <span key={h} className="text-label" style={{ fontSize: '10px' }}>
                      {h}
                    </span>
                  ))}
                </div>

                {/* 渠道行 */}
                <div className="space-y-1">
                  {channels.map((ch) => {
                    const meta = getChannelMeta(ch);
                    const hasCfg = hasRealConfig(ch.config);
                    const configKeys = ch.config ? Object.keys(ch.config).filter((k) => {
                      const v = ch.config[k];
                      return v !== null && v !== undefined && v !== '';
                    }) : [];
                    return (
                      <div
                        key={ch.id}
                        className="grid grid-cols-5 gap-3 px-4 py-3 rounded-lg"
                        style={{ background: 'var(--bg-secondary)' }}
                      >
                        <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                          {meta.icon} {t(meta.label)}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                          {ch.channel_type || '—'}
                        </span>
                        <span
                          className="font-mono text-[10px] font-semibold"
                          style={{ color: ch.enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                        >
                          {ch.enabled ? `● ${t('channels.enabled')}` : `○ ${t('channels.disabled')}`}
                        </span>
                        <span
                          className="font-mono text-[10px]"
                          style={{ color: hasCfg ? 'var(--accent-cyan)' : 'var(--text-disabled)' }}
                        >
                          {hasCfg ? t('channels.configured') : t('channels.notConfigured')}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {configKeys.length > 0 ? configKeys.join(', ') : '—'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

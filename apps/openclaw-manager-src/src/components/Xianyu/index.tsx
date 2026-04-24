import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from '@/lib/notify';
import { motion } from 'framer-motion';
import { useLanguage } from '@/i18n';
import {
  Fish,
  MessageSquare,
  Cookie,
  Clock,
  Zap,
  RefreshCw,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Wifi,
  WifiOff,
  QrCode,
  Play,
  Square,
} from 'lucide-react';
import { api } from '../../lib/api';
import { clawbotFetchJson } from '../../lib/tauri-core';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型 ====== */
interface ConversationItem {
  id?: string;
  buyer_name?: string;
  buyerName?: string;
  last_message?: string;
  lastMessage?: string;
  time?: string;
  updated_at?: string;
  status?: string;
}

interface CookieStatusData {
  enabled: boolean;
  last_sync_time: string;
  consecutive_failures: number;
  last_cookie_available: boolean;
  sync_history?: SyncHistoryItem[];
}

interface SyncHistoryItem {
  time: string;
  success: boolean;
  message?: string;
}

/* ====== 辅助函数 ====== */

/** 对话状态颜色映射，接受翻译函数 t */
function statusBadge(status: string | undefined, t: (key: string) => string) {
  switch (status) {
    case 'replied':
      return { label: t('xianyu.status.replied'), color: 'var(--accent-green)', bg: 'rgba(34,197,94,0.1)' };
    case 'pending':
      return { label: t('xianyu.status.pending'), color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.1)' };
    case 'closed':
      return { label: t('xianyu.status.closed'), color: 'var(--text-disabled)', bg: 'rgba(100,116,139,0.1)' };
    default:
      return { label: status ?? '—', color: 'var(--text-secondary)', bg: 'rgba(100,116,139,0.1)' };
  }
}

/** 头像占位颜色（基于名字哈希） */
const avatarColors = [
  'var(--accent-cyan)', 'var(--accent-purple)', 'var(--accent-green)',
  'var(--accent-amber)', 'var(--accent-red)',
];
const getAvatarColor = (name: string) => avatarColors[Math.abs([...name].reduce((h, c) => h + c.charCodeAt(0), 0)) % avatarColors.length];

/* ====== 主组件 ====== */

/**
 * 闲鱼管理页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示闲鱼 AI 客服引擎的全部关键指标
 * 使用真实后端 API 数据
 */
export function Xianyu() {
  const { t } = useLanguage();
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [cookieStatus, setCookieStatus] = useState<CookieStatusData | null>(null);
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [showQr, setShowQr] = useState(false);
  const [qrImage, setQrImage] = useState('');
  const [qrLoading, setQrLoading] = useState(false);
  const [qrStatus, setQrStatus] = useState<'waiting' | 'scanned' | 'confirmed' | 'expired' | 'error'>('waiting');
  const [serviceRunning, setServiceRunning] = useState(false);
  const [serviceToggling, setServiceToggling] = useState(false);
  const qrPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qrExpireRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ====== 数据拉取 ====== */
  const fetchData = useCallback(async () => {
    try {
      const [convRes, cookieRes, statusRes, servicesRes] = await Promise.allSettled([
        api.xianyuConversations(20),
        api.cookieCloudStatus(),
        api.clawbotStatus(),
        clawbotFetchJson<{ services?: Array<{ id: string; running?: boolean }> }>('/api/v1/system/services'),
      ]);

      if (convRes.status === 'fulfilled') {
        const data = convRes.value as any;
        setConversations(Array.isArray(data) ? data : data?.conversations ?? []);
      }
      if (cookieRes.status === 'fulfilled') {
        setCookieStatus(cookieRes.value as any);
      }
      if (statusRes.status === 'fulfilled') {
        const sData = statusRes.value as any;
        // 从系统状态中提取闲鱼自动回复状态
        setAutoReplyEnabled(sData?.xianyu?.auto_reply_enabled ?? sData?.xianyu_auto_reply ?? false);
      }
      if (servicesRes.status === 'fulfilled') {
        const svcData = servicesRes.value as any;
        const services: Array<{ id: string; running?: boolean; status?: string }> = Array.isArray(svcData) ? svcData : svcData?.services ?? [];
        const xySvc = services.find((s) => s.id === 'xianyu');
        // API 可能返回 status: 'running' 或 running: true，两种都兼容
        setServiceRunning(xySvc?.status === 'running' || xySvc?.running === true);
      }
      setError(null);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? t('xianyu.error.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30_000);
    return () => clearInterval(timer);
  }, [fetchData]);

  /* ====== 手动同步 Cookie ====== */
  const handleSync = async () => {
    setSyncLoading(true);
    try {
      const result = await api.cookieCloudSync() as any;
      await new Promise((r) => setTimeout(r, 1000));
      await fetchData();
      /* 检查后端返回的同步结果 */
      if (result?.success === false || result?.cookiecloud?.success === false) {
        const msg = result?.message || result?.cookiecloud?.message || t('xianyu.error.cookieSyncFailed');
        toast.error(msg, { channel: 'notification' });
      } else {
        toast.success(t('xianyu.syncHistory.success'), { channel: 'log' });
      }
    } catch {
      toast.error(t('xianyu.error.cookieSyncFailed'), { channel: 'notification' });
      await fetchData();
    } finally {
      setSyncLoading(false);
    }
  };

  /* ====== 扫码登录 — 清理轮询定时器 ====== */
  const stopQrPolling = useCallback(() => {
    if (qrPollRef.current) {
      clearInterval(qrPollRef.current);
      qrPollRef.current = null;
    }
    if (qrExpireRef.current) {
      clearTimeout(qrExpireRef.current);
      qrExpireRef.current = null;
    }
  }, []);

  /* ====== 扫码登录 — 关闭弹窗 ====== */
  const closeQrModal = useCallback(() => {
    stopQrPolling();
    setShowQr(false);
    setQrImage('');
    setQrStatus('waiting');
  }, [stopQrPolling]);

  /* ====== 扫码登录 — 开始轮询扫码状态 ====== */
  const startQrPolling = useCallback(() => {
    stopQrPolling();

    // 每 2 秒轮询一次扫码状态
    qrPollRef.current = setInterval(async () => {
      try {
        const res = await clawbotFetchJson<{ status?: string; message?: string }>('/api/v1/xianyu/qr/status');
        const status = res?.status as typeof qrStatus;
        if (status) {
          setQrStatus(status);
        }
        if (status === 'confirmed') {
          stopQrPolling();
          toast.success(t('xianyu.qr.loginSuccess'), { channel: 'log' });
          setShowQr(false);
          setQrImage('');
          setQrStatus('waiting');
          await fetchData();
        } else if (status === 'expired' || status === 'error') {
          stopQrPolling();
        }
      } catch {
        // 轮询失败不中断，等下次再试
      }
    }, 2000);

    // 5 分钟后自动过期
    qrExpireRef.current = setTimeout(() => {
      setQrStatus('expired');
      stopQrPolling();
    }, 300_000);
  }, [fetchData, stopQrPolling, t]);

  /* ====== 扫码登录 — 生成二维码 ====== */
  const handleGenerateQR = async () => {
    setQrLoading(true);
    setQrStatus('waiting');
    try {
      const res = await clawbotFetchJson<{ qr_image?: string; qr_content?: string; expires_in?: number }>(
        '/api/v1/xianyu/qr/generate',
        { method: 'POST' },
      );
      const image = res?.qr_image ?? '';
      if (image) {
        setQrImage(image);
        setShowQr(true);
        startQrPolling();
      } else {
        toast.error(t('xianyu.error.qrFailed'), { channel: 'notification' });
      }
    } catch {
      toast.error(t('xianyu.error.qrFailed'), { channel: 'notification' });
    } finally {
      setQrLoading(false);
    }
  };

  /* ====== 扫码弹窗 ESC 键关闭 ====== */
  useEffect(() => {
    if (!showQr) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeQrModal();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [showQr, closeQrModal]);

  /* ====== 组件卸载时清理轮询 ====== */
  useEffect(() => {
    return () => stopQrPolling();
  }, [stopQrPolling]);

  /* ====== 服务启停 ====== */
  const handleServiceToggle = async () => {
    setServiceToggling(true);
    try {
      const action = serviceRunning ? 'stop' : 'start';
      await clawbotFetchJson(`/api/v1/system/services/xianyu/${action}`, { method: 'POST' });
      toast.success(serviceRunning ? t('xianyu.toast.serviceStopped') : t('xianyu.toast.serviceStarted'), { channel: 'log' });
      await new Promise((r) => setTimeout(r, 800));
      await fetchData();
    } catch {
      toast.error(t('xianyu.error.operationFailed'), { channel: 'notification' });
      await fetchData();
    } finally {
      setServiceToggling(false);
    }
  };

  /* ====== 派生数据 ====== */
  const cookieValid = cookieStatus?.last_cookie_available && (cookieStatus?.consecutive_failures ?? 0) === 0;
  const cookieColor = cookieValid ? 'var(--accent-green)' : 'var(--accent-red)';
  const cookieLabel = cookieValid ? 'VALID' : 'INVALID';
  const syncHistory = cookieStatus?.sync_history ?? [];

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：闲鱼概览 (span-8) + 扫码登录 + Cookie 状态 (span-4) ====== */}

        {/* 闲鱼概览 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题区域 */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}>
                <Fish size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('xianyu.title')}
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('xianyu.subtitle')}
                </p>
              </div>
              {loading && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />}

              {/* 服务启停按钮 */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: 'var(--bg-base)' }}>
                  <div className="relative">
                    <div className="w-2 h-2 rounded-full"
                      style={{ background: serviceRunning ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                    {serviceRunning && (
                      <div className="absolute inset-0 w-2 h-2 rounded-full animate-ping opacity-30"
                        style={{ background: 'var(--accent-green)' }} />
                    )}
                  </div>
                  <span className="font-mono text-[10px]" style={{ color: serviceRunning ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                    {serviceRunning ? t('xianyu.status.running') : t('xianyu.status.stopped')}
                  </span>
                </div>
                <motion.button
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl cursor-pointer text-[10px] font-mono font-bold"
                  style={{
                    background: serviceRunning ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
                    border: `1px solid ${serviceRunning ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
                    color: serviceRunning ? 'var(--accent-red)' : 'var(--accent-green)',
                    opacity: serviceToggling ? 0.5 : 1,
                    pointerEvents: serviceToggling ? 'none' : 'auto',
                  }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={handleServiceToggle}
                >
                  {serviceToggling ? <Loader2 size={10} className="animate-spin" /> : serviceRunning ? <Square size={10} /> : <Play size={10} />}
                  {serviceRunning ? t('xianyu.btn.stopService') : t('xianyu.btn.startService')}
                </motion.button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl mb-4"
                style={{ background: 'rgba(255,0,0,0.05)', border: '1px solid rgba(255,0,0,0.2)' }}>
                <AlertCircle size={14} style={{ color: 'var(--accent-red)' }} />
                <span className="text-xs" style={{ color: 'var(--accent-red)' }}>{error}</span>
              </div>
            )}

            {/* 关键指标 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <StatBlock icon={MessageSquare} label={t('xianyu.stats.conversations')} value={String(conversations.length)} accent="var(--accent-purple)" />
              <StatBlock icon={Zap} label={t('xianyu.stats.autoReply')} value={autoReplyEnabled ? t('xianyu.stats.enabled') : t('xianyu.stats.disabled')} accent={autoReplyEnabled ? 'var(--accent-green)' : 'var(--text-disabled)'} />
              <StatBlock icon={Cookie} label="Cookie" value={cookieStatus ? cookieLabel : '—'} accent={cookieColor} />
              <StatBlock icon={AlertCircle} label={t('xianyu.stats.consecutiveFailures')} value={String(cookieStatus?.consecutive_failures ?? 0)} accent={(cookieStatus?.consecutive_failures ?? 0) > 0 ? 'var(--accent-red)' : 'var(--accent-green)'} />
            </div>

            {/* 最近对话列表 */}
            <div>
              <span className="text-label mb-3 block" style={{ color: 'var(--text-tertiary)' }}>
                {t('xianyu.recentConversations')} ({conversations.length})
              </span>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {conversations.length === 0 && !loading && (
                  <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('xianyu.noConversations')}</span>
                )}
                {conversations.slice(0, 10).map((conv, i) => {
                  const name = conv.buyer_name ?? conv.buyerName ?? t('xianyu.defaultBuyerName');
                  const msg = conv.last_message ?? conv.lastMessage ?? '';
                  const time = conv.time ?? (conv.updated_at ? new Date(conv.updated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '');
                  const badge = statusBadge(conv.status, t);
                  return (
                    <div key={conv.id ?? i} className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors"
                      style={{ background: 'var(--bg-base)' }}>
                      {/* 头像占位 */}
                      <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center font-mono text-xs font-bold"
                        style={{ background: getAvatarColor(name), color: 'var(--bg-base)' }}>
                        {name[0]}
                      </div>
                      {/* 买家名称 + 最后消息 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                            {name}
                          </span>
                          {time && (
                            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                              {time}
                            </span>
                          )}
                        </div>
                        {msg && (
                          <p className="font-mono text-[11px] truncate mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                            {msg}
                          </p>
                        )}
                      </div>
                      {/* 状态徽标 */}
                      {conv.status && (
                        <span className="flex-shrink-0 px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                          style={{ background: badge.bg, color: badge.color }}>
                          {badge.label}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* 扫码登录卡片 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <QrCode size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>{t('xianyu.qr.title')}</span>
            </div>

            <p className="font-mono text-[11px] mb-4" style={{ color: 'var(--text-secondary)' }}>
              {t('xianyu.qr.desc')}
            </p>

            <motion.button
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl cursor-pointer font-mono text-xs font-bold"
              style={{
                background: 'rgba(168,85,247,0.08)',
                border: '1px solid rgba(168,85,247,0.25)',
                color: 'var(--accent-purple)',
                opacity: qrLoading ? 0.5 : 1,
                pointerEvents: qrLoading ? 'none' : 'auto',
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleGenerateQR}
            >
              {qrLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <QrCode size={14} />
              )}
              {qrLoading ? t('xianyu.qr.generating') : t('xianyu.qr.loginBtn')}
            </motion.button>

            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              {t('xianyu.qr.autoUpdateHint')}
            </p>
          </div>
        </motion.div>

        {/* 二维码弹窗 */}
        {showQr && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
            onClick={closeQrModal}
            role="dialog"
            aria-modal="true"
            aria-label={t('xianyu.qr.loginBtn')}
          >
            <motion.div
              className="abyss-card p-6 rounded-2xl flex flex-col items-center gap-4"
              style={{ minWidth: 300 }}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-2">
                <QrCode size={18} style={{ color: 'var(--accent-purple)' }} />
                <span className="font-display text-base font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t('xianyu.qr.loginBtn')}
                </span>
              </div>

              {/* 二维码图片 — 白色背景保证扫码识别 */}
              <div className="rounded-xl overflow-hidden bg-white p-4 flex items-center justify-center" style={{ minWidth: 216, minHeight: 216 }}>
                {qrImage ? (
                  <img src={`data:image/png;base64,${qrImage}`} alt="Xianyu QR Code" className="w-48 h-48 object-contain" />
                ) : (
                  <Loader2 size={32} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />
                )}
              </div>

              {/* 扫码状态提示 */}
              <div className="flex items-center gap-2">
                {qrStatus === 'waiting' && (
                  <>
                    <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                      {t('xianyu.qr.waitingScan')}
                    </span>
                  </>
                )}
                {qrStatus === 'scanned' && (
                  <>
                    <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--accent-green)' }}>
                      {t('xianyu.qr.scannedConfirm')}
                    </span>
                  </>
                )}
                {qrStatus === 'expired' && (
                  <>
                    <XCircle size={14} style={{ color: 'var(--accent-red)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--accent-red)' }}>
                      {t('xianyu.qr.expired')}
                    </span>
                  </>
                )}
                {qrStatus === 'error' && (
                  <>
                    <AlertCircle size={14} style={{ color: 'var(--accent-red)' }} />
                    <span className="font-mono text-[11px]" style={{ color: 'var(--accent-red)' }}>
                      {t('xianyu.qr.error')}
                    </span>
                  </>
                )}
              </div>

              {/* 操作按钮 */}
              <div className="flex items-center gap-3">
                {(qrStatus === 'expired' || qrStatus === 'error') && (
                  <motion.button
                    className="font-mono text-xs px-4 py-2 rounded-xl cursor-pointer font-bold"
                    style={{
                      background: 'rgba(168,85,247,0.08)',
                      border: '1px solid rgba(168,85,247,0.25)',
                      color: 'var(--accent-purple)',
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={handleGenerateQR}
                  >
                    {t('xianyu.qr.regenerate')}
                  </motion.button>
                )}
                <button
                  className="font-mono text-xs px-4 py-2 rounded-xl"
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: 'var(--text-secondary)',
                  }}
                  onClick={closeQrModal}
                >
                  {t('xianyu.btn.close')}
                </button>
              </div>
            </motion.div>
          </div>
        )}

        {/* Cookie 状态卡片 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题 */}
            <div className="flex items-center gap-2 mb-5">
              <Cookie size={16} style={{ color: cookieColor }} />
              <span className="text-label" style={{ color: cookieColor }}>{t('xianyu.cookie.title')}</span>
            </div>

            {/* 大状态指示器 */}
            <div className="flex items-center gap-3 mb-6">
              <div className="relative">
                <div className="w-4 h-4 rounded-full animate-pulse" style={{ background: cookieColor }} />
                <div className="absolute inset-0 w-4 h-4 rounded-full animate-ping opacity-40" style={{ background: cookieColor }} />
              </div>
              <span className="font-display text-2xl font-bold tracking-wider" style={{ color: cookieColor }}>
                {cookieStatus ? cookieLabel : '—'}
              </span>
            </div>

            {/* 详细信息 */}
            <div className="space-y-4">
              <InfoRow icon={Clock} label={t('xianyu.cookie.lastSync')}
                value={cookieStatus?.last_sync_time
                  ? (() => {
                      /* API 返回 Unix 秒级时间戳，Date 需要毫秒 */
                      const ts = cookieStatus.last_sync_time as unknown as number | string;
                      const numTs = typeof ts === 'number' ? ts : Number(ts);
                      const date = new Date(!isNaN(numTs) && numTs < 1e12 ? numTs * 1000 : ts);
                      return date.toLocaleTimeString('zh-CN');
                    })()
                  : '—'} />
              <InfoRow icon={AlertCircle} label={t('xianyu.cookie.consecutiveFailures')}
                value={`${cookieStatus?.consecutive_failures ?? 0} ${t('xianyu.cookie.times')}`} />
              <InfoRow icon={cookieStatus?.enabled ? Wifi : WifiOff} label={t('xianyu.cookie.syncFeature')}
                value={cookieStatus?.enabled ? t('xianyu.cookie.syncEnabled') : t('xianyu.cookie.syncDisabled')} />

              {/* CookieCloud 未配置引导提示 */}
              {!cookieStatus?.enabled && (
                <div className="mt-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(255,187,0,0.06)', border: '1px solid rgba(255,187,0,0.15)' }}>
                  <p className="font-mono text-[10px] leading-relaxed" style={{ color: 'var(--accent-amber)' }}>
                    {t('xianyu.cookie.notConfiguredHint')}
                  </p>
                </div>
              )}
            </div>

            {/* 手动同步按钮 */}
            <motion.button
              className="flex items-center justify-center gap-2 w-full mt-5 px-4 py-2.5 rounded-xl cursor-pointer font-mono text-xs font-bold"
              style={{
                background: 'rgba(0,212,255,0.08)',
                border: '1px solid rgba(0,212,255,0.25)',
                color: 'var(--accent-cyan)',
                opacity: syncLoading ? 0.5 : 1,
                pointerEvents: syncLoading ? 'none' : 'auto',
              }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSync}
            >
              {syncLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              {syncLoading ? t('xianyu.btn.syncing') : t('xianyu.btn.syncNow')}
            </motion.button>

            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              {t('xianyu.cookie.autoSyncHint')}
            </p>
          </div>
        </motion.div>

        {/* ====== 第二行：同步历史 (span-8) + 自动回复状态 (span-4) ====== */}

        {/* 同步历史 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <RefreshCw size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>{t('xianyu.syncHistory.title')}</span>
            </div>

            <div className="space-y-2 max-h-[240px] overflow-y-auto">
              {syncHistory.length === 0 && (
                <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>{t('xianyu.syncHistory.noRecords')}</span>
              )}
              {syncHistory.slice(0, 10).map((entry, i) => (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}>
                  {entry.success ? (
                    <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />
                  ) : (
                    <XCircle size={14} style={{ color: 'var(--accent-red)' }} />
                  )}
                  <span className="font-mono text-[11px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                    {entry.time ? new Date(
                      /* API 返回 Unix 秒级时间戳，Date 构造器需要毫秒 */
                      typeof entry.time === 'number' && entry.time < 1e12 ? entry.time * 1000 : entry.time
                    ).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
                    }) : '—'}
                  </span>
                  <span className="font-mono text-[11px] flex-1 truncate" style={{
                    color: entry.success ? 'var(--accent-green)' : 'var(--accent-red)',
                  }}>
                    {entry.success ? t('xianyu.syncHistory.success') : (entry.message ?? t('xianyu.syncHistory.failed'))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 自动回复状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Zap size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>{t('xianyu.autoReply.title')}</span>
            </div>

            <div className="flex items-center gap-3 mb-6">
              <div className="relative">
                <div className="w-4 h-4 rounded-full"
                  style={{ background: autoReplyEnabled ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                {autoReplyEnabled && (
                  <div className="absolute inset-0 w-4 h-4 rounded-full animate-ping opacity-40"
                    style={{ background: 'var(--accent-green)' }} />
                )}
              </div>
              <span className="font-display text-xl font-bold tracking-wider"
                style={{ color: autoReplyEnabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                {autoReplyEnabled ? t('xianyu.autoReply.enabled') : t('xianyu.autoReply.disabled')}
              </span>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{t('xianyu.autoReply.conversationCount')}</span>
                <span className="font-display text-lg font-bold" style={{ color: 'var(--accent-cyan)' }}>
                  {conversations.length}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{t('xianyu.autoReply.cookieStatus')}</span>
                <span className="font-mono text-xs font-bold" style={{ color: cookieColor }}>
                  {cookieStatus ? cookieLabel : '—'}
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

/** 概览统计块 */
function StatBlock({ icon: Icon, label, value, accent }: {
  icon: React.ElementType; label: string; value: string; accent: string;
}) {
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={12} style={{ color: accent }} />
        <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <span className="text-metric" style={{ color: accent }}>{value}</span>
    </div>
  );
}

/** Cookie 信息行 */
function InfoRow({ icon: Icon, label, value }: {
  icon: React.ElementType; label: string; value: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Icon size={13} style={{ color: 'var(--text-disabled)' }} />
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

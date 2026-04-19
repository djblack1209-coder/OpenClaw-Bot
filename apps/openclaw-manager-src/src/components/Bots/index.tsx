import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Server,
  Clock,
  Terminal,
  RotateCcw,
  Cookie,
  Play,
  Square,
  Loader2,
  AlertCircle,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { api } from '../../lib/api';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型 ====== */
interface ServiceItem {
  id: string;
  name: string;
  description: string;
  status: string;
  port?: number;
}

interface CookieStatus {
  enabled: boolean;
  last_sync_time: string;
  consecutive_failures: number;
  last_cookie_available: boolean;
}

/* ====== 辅助函数 ====== */

/** 服务状态颜色 */
const statusColor = (s: string) =>
  s === 'running' ? 'var(--accent-green)' : s === 'stopped' ? 'var(--text-tertiary)' : 'var(--accent-red)';

/** 服务状态文本 */
const statusText = (s: string) =>
  s === 'running' ? '运行中' : s === 'stopped' ? '已停止' : '异常';

/**
 * Bots 页面 — Sonic Abyss Bento Grid 布局
 * 12 列网格，玻璃卡片 + 终端美学
 * 使用真实后端 API 数据
 */
export function Bots() {
  /* ====== 状态 ====== */
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  /* ====== 数据拉取 ====== */
  const fetchData = useCallback(async () => {
    try {
      const [servicesRes, cookieRes] = await Promise.allSettled([
        api.services(),
        api.cookieCloudStatus(),
      ]);

      if (servicesRes.status === 'fulfilled') {
        const data = servicesRes.value as any;
        setServices(data?.services ?? []);
      }
      if (cookieRes.status === 'fulfilled') {
        setCookieStatus(cookieRes.value as any);
      }
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30_000);
    return () => clearInterval(timer);
  }, [fetchData]);

  /* ====== 服务启停 ====== */
  const handleToggleService = async (serviceId: string, currentStatus: string) => {
    setActionLoading((prev) => ({ ...prev, [serviceId]: true }));
    try {
      if (currentStatus === 'running') {
        await api.serviceStop(serviceId);
      } else {
        await api.serviceStart(serviceId);
      }
      // 等一小段时间让后端状态更新
      await new Promise((r) => setTimeout(r, 800));
      await fetchData();
    } catch {
      // 静默，刷新状态即可
      await fetchData();
    } finally {
      setActionLoading((prev) => ({ ...prev, [serviceId]: false }));
    }
  };

  /* ====== 统计数据 ====== */
  const runningCount = services.filter((s) => s.status === 'running').length;
  const stoppedCount = services.filter((s) => s.status === 'stopped').length;
  const errorCount = services.filter((s) => s.status !== 'running' && s.status !== 'stopped').length;

  const fleetStats = [
    { label: '总数', value: services.length, color: 'var(--accent-cyan)' },
    { label: '运行中', value: runningCount, color: 'var(--accent-green)' },
    { label: '已停止', value: stoppedCount, color: 'var(--text-tertiary)' },
    { label: '错误', value: errorCount, color: 'var(--accent-red)' },
  ];

  /* ====== Cookie 状态判断 ====== */
  const cookieValid = cookieStatus?.last_cookie_available && (cookieStatus?.consecutive_failures ?? 0) === 0;
  const cookieLabel = cookieValid ? 'VALID' : 'INVALID';
  const cookieColor = cookieValid ? 'var(--accent-green)' : 'var(--accent-red)';

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >

        {/* ====== Row 1 左: 服务舰队总览 (col-span-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>SERVICE FLEET</span>
              <div className="flex items-center gap-1.5">
                {loading ? (
                  <Loader2 size={12} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />
                ) : (
                  <>
                    <motion.span
                      className="inline-block w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--accent-green)' }}
                      animate={{ opacity: [1, 0.3, 1] }}
                      transition={{ duration: 1.5, repeat: Infinity }}
                    />
                    <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>LIVE</span>
                  </>
                )}
              </div>
            </div>
            <h2 className="font-display text-xl font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
              服务舰队 <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>// SERVICE FLEET</span>
            </h2>

            {/* 统计行 */}
            <div className="flex gap-5 mb-5">
              {fleetStats.map((s) => (
                <div key={s.label} className="flex items-center gap-2">
                  <span className="font-mono text-2xl font-bold" style={{ color: s.color }}>{s.value}</span>
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.label}</span>
                </div>
              ))}
            </div>

            {/* 服务列表 */}
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0 pr-1">
              {error && (
                <div className="flex items-center gap-2 px-4 py-3 rounded-2xl"
                  style={{ background: 'rgba(255,0,0,0.05)', border: '1px solid rgba(255,0,0,0.2)' }}>
                  <AlertCircle size={14} style={{ color: 'var(--accent-red)' }} />
                  <span className="text-xs" style={{ color: 'var(--accent-red)' }}>{error}</span>
                </div>
              )}
              {services.length === 0 && !loading && !error && (
                <div className="flex items-center justify-center py-8">
                  <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无服务数据</span>
                </div>
              )}
              {services.map((svc) => {
                const isLoading = actionLoading[svc.id] ?? false;
                const isRunning = svc.status === 'running';
                return (
                  <div
                    key={svc.id}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl transition-colors"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}
                  >
                    {/* 状态圆点 */}
                    <span className="relative flex-shrink-0">
                      {isRunning && (
                        <motion.span
                          className="absolute inset-[-3px] rounded-full"
                          style={{ background: statusColor(svc.status), opacity: 0.3 }}
                          animate={{ scale: [1, 1.8, 1], opacity: [0.3, 0, 0.3] }}
                          transition={{ duration: 2, repeat: Infinity }}
                        />
                      )}
                      <span
                        className="block w-2 h-2 rounded-full"
                        style={{ background: statusColor(svc.status) }}
                      />
                    </span>

                    {/* 图标 + 名称 */}
                    <Server size={16} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    <span className="font-medium text-sm flex-shrink-0" style={{ color: 'var(--text-primary)' }}>
                      {svc.name}
                    </span>

                    {/* 描述 */}
                    {svc.description && (
                      <span className="font-mono text-[10px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                        {svc.description}
                      </span>
                    )}

                    <div className="flex-1" />

                    {/* 端口 */}
                    {svc.port && (
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <Terminal size={12} style={{ color: 'var(--text-tertiary)' }} />
                        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>:{svc.port}</span>
                      </div>
                    )}

                    {/* 启停按钮 */}
                    <motion.button
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl cursor-pointer text-[10px] font-mono font-bold"
                      style={{
                        background: isRunning ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
                        border: `1px solid ${isRunning ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
                        color: isRunning ? 'var(--accent-red)' : 'var(--accent-green)',
                        opacity: isLoading ? 0.5 : 1,
                        pointerEvents: isLoading ? 'none' : 'auto',
                      }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => handleToggleService(svc.id, svc.status)}
                    >
                      {isLoading ? (
                        <Loader2 size={10} className="animate-spin" />
                      ) : isRunning ? (
                        <Square size={10} />
                      ) : (
                        <Play size={10} />
                      )}
                      {isRunning ? '停止' : '启动'}
                    </motion.button>

                    {/* 状态文本 */}
                    <span className="font-mono text-[10px] w-12 text-right flex-shrink-0" style={{ color: statusColor(svc.status) }}>
                      {statusText(svc.status)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 1 右: Cookie 状态 + 连接概览 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Cookie size={16} style={{ color: cookieColor }} />
              <span className="text-label" style={{ color: cookieColor }}>COOKIE STATUS</span>
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
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>上次同步</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                  {cookieStatus?.last_sync_time
                    ? new Date(cookieStatus.last_sync_time).toLocaleTimeString('zh-CN')
                    : '—'}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle size={13} style={{ color: 'var(--text-disabled)' }} />
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>连续失败</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{
                  color: (cookieStatus?.consecutive_failures ?? 0) > 0 ? 'var(--accent-red)' : 'var(--accent-green)',
                }}>
                  {cookieStatus?.consecutive_failures ?? 0} 次
                </span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {cookieStatus?.enabled ? (
                    <Wifi size={13} style={{ color: 'var(--accent-green)' }} />
                  ) : (
                    <WifiOff size={13} style={{ color: 'var(--text-disabled)' }} />
                  )}
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>同步功能</span>
                </div>
                <span className="font-mono text-xs font-medium" style={{
                  color: cookieStatus?.enabled ? 'var(--accent-green)' : 'var(--text-disabled)',
                }}>
                  {cookieStatus?.enabled ? '已启用' : '未启用'}
                </span>
              </div>
            </div>

            <p className="font-mono text-[10px] mt-6" style={{ color: 'var(--text-disabled)' }}>
              CookieCloud 自动同步 · 加密传输
            </p>
          </div>
        </motion.div>

        {/* ====== Row 2: 连接概览 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>CONNECTION</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              连接状态
            </h3>

            <div className="space-y-4">
              {services.filter((s) => s.status === 'running').slice(0, 6).map((svc) => (
                <div key={svc.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-green)' }} />
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{svc.name}</span>
                  </div>
                  {svc.port && (
                    <span className="font-mono text-xs" style={{ color: 'var(--accent-green)' }}>:{svc.port}</span>
                  )}
                </div>
              ))}
              {services.filter((s) => s.status === 'running').length === 0 && (
                <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>暂无运行中的服务</span>
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: 快速操作 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>QUICK ACTIONS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              快速操作
            </h3>

            <div className="flex-1 grid grid-cols-1 gap-3">
              {/* 刷新数据 */}
              <motion.button
                className="flex items-center gap-3 px-4 py-3 rounded-2xl cursor-pointer transition-colors text-left"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--glass-border)' }}
                whileHover={{ background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.15)' }}
                whileTap={{ scale: 0.98 }}
                onClick={() => { setLoading(true); fetchData(); }}
              >
                <span className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
                  <RotateCcw size={16} style={{ color: 'var(--accent-cyan)' }} />
                </span>
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>刷新数据</span>
              </motion.button>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: 服务详情 (col-span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>SUMMARY</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              服务概要
            </h3>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>总服务数</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-cyan)' }}>{services.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>在线率</span>
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--accent-green)' }}>
                  {services.length > 0 ? Math.round((runningCount / services.length) * 100) : 0}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                  <Cookie size={14} /> Cookie
                </span>
                <span
                  className="font-mono text-xs px-2.5 py-1 rounded-full font-bold"
                  style={{
                    color: cookieColor,
                    background: cookieValid ? 'rgba(0,255,170,0.1)' : 'rgba(255,0,0,0.1)',
                    border: `1px solid ${cookieValid ? 'rgba(0,255,170,0.25)' : 'rgba(255,0,0,0.25)'}`,
                  }}
                >
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

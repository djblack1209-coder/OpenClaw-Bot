/**
 * Logs — 应用日志页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 数据来自通知 API + WebSocket 实时推送
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { Terminal, Loader2 } from 'lucide-react';
import { api } from '../../lib/api';
import { useClawbotWS, useWSConnectionStatus } from '@/hooks/useClawbotWS';
import { useLanguage } from '../../i18n';
import { getFrontendNotifications, subscribeFrontendNotifications } from '@/lib/notify';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型定义 ====== */

type LogLevel = 'INFO' | 'OK' | 'WARN' | 'ERROR';

interface LogLine {
  id?: string;
  time: string;
  level: LogLevel;
  module: string;
  msg: string;
}

const LEVEL_STYLE: Record<LogLevel, { color: string; bg: string }> = {
  INFO:  { color: 'var(--accent-cyan)',  bg: 'rgba(6,182,212,0.12)' },
  OK:    { color: 'var(--accent-green)', bg: 'rgba(34,197,94,0.12)' },
  WARN:  { color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.12)' },
  ERROR: { color: 'var(--accent-red)',   bg: 'rgba(239,68,68,0.12)' },
};

const FILTER_CHIPS: { label: string; value: LogLevel | 'ALL' }[] = [
  { label: '全部', value: 'ALL' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARN', value: 'WARN' },
  { label: 'ERROR', value: 'ERROR' },
];

/* ====== 工具函数 ====== */

/** 将 WS/通知事件统一转为日志行 */
function notifToLog(n: any): LogLine {
  /* 从通知的 category/level 推断日志级别 */
  const rawLevel = (n.level ?? n.category ?? n.type ?? 'info').toUpperCase();
  let level: LogLevel = 'INFO';
  if (rawLevel.includes('ERR') || rawLevel.includes('FAIL') || rawLevel.includes('CRITICAL')) level = 'ERROR';
  else if (rawLevel.includes('WARN') || rawLevel.includes('ALERT')) level = 'WARN';
  else if (rawLevel.includes('OK') || rawLevel.includes('SUCCESS')) level = 'OK';

  /* 提取时间 */
  let time = '—';
  const ts = n.created_at ?? n.timestamp ?? n.time;
  if (ts) {
    try {
      const d = new Date(ts);
      time = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}.${String(d.getMilliseconds()).padStart(3,'0')}`;
    } catch { time = String(ts).slice(11, 23) || ts; }
  }

  return {
    id: n.id ?? n.notification_id,
    time,
    level,
    module: n.source ?? n.module ?? n.category ?? n.type ?? 'system',
    msg: n.message ?? n.title ?? n.content ?? n.msg ?? JSON.stringify(n.data ?? n).slice(0, 240) ?? '(无内容)',
  };
}

/** ASCII 进度条 */
function renderBar(value: number, max: number, width: number = 20): string {
  const ratio = max > 0 ? value / max : 0;
  const filled = Math.round(Math.min(1, ratio) * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/* ====== 主组件 ====== */

export function Logs() {
  const { t } = useLanguage();
  const wsConnected = useWSConnectionStatus();
  const [loading, setLoading] = useState(true);
  const [backendLogs, setBackendLogs] = useState<LogLine[]>([]);
  const [frontendLogs, setFrontendLogs] = useState<LogLine[]>(() => getFrontendNotifications().map(notifToLog));
  const [filter, setFilter] = useState<LogLevel | 'ALL'>('ALL');
  const logEndRef = useRef<HTMLDivElement>(null);

  /* —— 首次加载 —— */
  const fetchLogs = useCallback(async () => {
    try {
      const raw = await api.notifications({ limit: 50 }) as any;
      const list: any[] = Array.isArray(raw) ? raw : raw?.notifications ?? raw?.items ?? [];
      setBackendLogs(list.map(notifToLog));
    } catch (err) {
      console.error('[Logs] 加载失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  useEffect(() => {
    return subscribeFrontendNotifications(() => {
      setFrontendLogs(getFrontendNotifications().map(notifToLog));
    });
  }, []);

  /* —— WebSocket 实时推送：日志页接收所有事件，不只通知 —— */
  useClawbotWS('*', (event) => {
    if (event.type === 'heartbeat') {
      return;
    }
    const payload = {
      ...event.data,
      type: event.type,
      timestamp: event.timestamp,
    };
    const newLog = notifToLog(payload);
    setBackendLogs((prev) => [newLog, ...prev].slice(0, 200));
  });

  const logs = [...frontendLogs, ...backendLogs]
    .sort((a, b) => {
      const [ah = '00', am = '00', as = '00.000'] = a.time.split(':');
      const [bh = '00', bm = '00', bs = '00.000'] = b.time.split(':');
      const an = Number(ah) * 3600000 + Number(am) * 60000 + Number(as.replace('.', ''));
      const bn = Number(bh) * 3600000 + Number(bm) * 60000 + Number(bs.replace('.', ''));
      return bn - an;
    })
    .slice(0, 200);

  /* —— 统计计算 —— */
  const countInfo = logs.filter((l) => l.level === 'INFO' || l.level === 'OK').length;
  const countWarn = logs.filter((l) => l.level === 'WARN').length;
  const countError = logs.filter((l) => l.level === 'ERROR').length;

  const filteredLogs = filter === 'ALL'
    ? logs
    : logs.filter((l) => l.level === filter || (filter === 'INFO' && l.level === 'OK'));

  /* 模块热度 — 从真实日志统计 */
  const moduleMap = new Map<string, { count: number }>();
  for (const l of logs) {
    const entry = moduleMap.get(l.module) ?? { count: 0 };
    entry.count++;
    moduleMap.set(l.module, entry);
  }
  const moduleHeat = [...moduleMap.entries()]
    .map(([name, { count }]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const maxModuleCount = moduleHeat.length > 0 ? moduleHeat[0].count : 1;
  const MODULE_COLORS = ['var(--accent-green)', 'var(--accent-cyan)', 'var(--accent-purple)', 'var(--accent-amber)', 'var(--accent-red)'];

  /* —— 加载态 —— */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-green)' }} />
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
        {/* ====== 日志终端 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.15)' }}>
                <Terminal size={20} style={{ color: 'var(--accent-green)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  SYSTEM LOGS
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('logs.subtitle')}
                </p>
              </div>
              {/* 实时指示灯 */}
              <div className="ml-auto flex items-center gap-1.5">
                <div className="relative">
                  <div className="w-2 h-2 rounded-full" style={{ background: wsConnected ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                  {wsConnected && (
                    <div className="absolute inset-0 w-2 h-2 rounded-full animate-ping opacity-40"
                      style={{ background: 'var(--accent-green)' }} />
                  )}
                </div>
                <span className="font-mono text-[10px]" style={{ color: wsConnected ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                  {wsConnected ? 'LIVE' : 'OFFLINE'}
                </span>
              </div>
            </div>

            {/* 终端区域 */}
            <div className="flex-1 rounded-lg p-3 font-mono text-[11px] leading-[1.7] overflow-y-auto"
              style={{ background: 'var(--bg-primary)' }}>
              {filteredLogs.length === 0 && (
                <div className="text-center py-8" style={{ color: 'var(--text-disabled)' }}>
                  {t('logs.noLogs')}
                </div>
              )}
              {filteredLogs.map((log, i) => {
                const ls = LEVEL_STYLE[log.level];
                return (
                  <div key={log.id ?? i} className="flex items-start gap-2 py-0.5">
                    <span style={{ color: 'var(--text-disabled)' }}>{log.time}</span>
                    <span className="px-1.5 py-0 rounded text-[9px] tracking-wider font-bold flex-shrink-0"
                      style={{ color: ls.color, background: ls.bg }}>
                      {log.level}
                    </span>
                    <span className="flex-shrink-0" style={{ color: 'var(--accent-purple)' }}>
                      [{log.module}]
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{log.msg}</span>
                  </div>
                );
              })}
              {/* 闪烁光标 */}
              <div className="flex items-center gap-1 mt-1" ref={logEndRef}>
                <span style={{ color: 'var(--accent-green)' }}>▊</span>
                <span className="animate-pulse" style={{ color: 'var(--text-disabled)' }}>_</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 日志统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>STATISTICS</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('logs.statsTitle')}
            </h3>
            <div className="space-y-4 flex-1">
              {[
                { label: t('logs.totalCount'), value: String(logs.length), color: 'var(--text-primary)' },
                { label: 'INFO / OK', value: String(countInfo), color: 'var(--accent-cyan)' },
                { label: 'WARN', value: String(countWarn), color: 'var(--accent-amber)' },
                { label: 'ERROR', value: String(countError), color: 'var(--accent-red)' },
              ].map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: s.color, fontSize: '22px' }}>{s.value}</p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== 日志筛选 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>FILTER</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('logs.filterTitle')}
            </h3>
            <div className="flex flex-wrap gap-2 flex-1">
              {FILTER_CHIPS.map((chip) => {
                const active = filter === chip.value;
                const chipColor = chip.value === 'ALL' || chip.value === 'INFO'
                  ? 'var(--accent-cyan)'
                  : chip.value === 'WARN'
                    ? 'var(--accent-amber)'
                    : 'var(--accent-red)';
                return (
                  <button key={chip.value}
                    onClick={() => setFilter(chip.value)}
                    className="px-4 py-2 rounded-lg font-mono text-xs tracking-wider transition-all"
                    style={{
                      background: active ? chipColor : 'var(--bg-secondary)',
                      color: active ? 'var(--bg-primary)' : chipColor,
                      fontWeight: active ? 700 : 500,
                    }}>
                    {chip.label}
                  </button>
                );
              })}
            </div>
            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              {t('logs.showing')}: {filteredLogs.length} {t('logs.countUnit')} / {t('logs.totalPrefix')} {logs.length} {t('logs.countUnit')}
            </p>
          </div>
        </motion.div>

        {/* ====== 模块热度 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>MODULE HEATMAP</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('logs.moduleHeatTitle')}
            </h3>
            <div className="flex-1 space-y-3">
              {moduleHeat.length === 0 && (
                <div className="font-mono text-xs py-4 text-center" style={{ color: 'var(--text-disabled)' }}>
                  {t('common.noData')}
                </div>
              )}
              {moduleHeat.map((m, i) => {
                const color = MODULE_COLORS[i % MODULE_COLORS.length];
                return (
                  <div key={m.name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-display text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {m.name}
                      </span>
                      <span className="font-mono text-[11px] font-bold" style={{ color }}>
                        {m.count}
                      </span>
                    </div>
                    <div className="font-mono text-[10px] leading-none" style={{ color }}>
                      {renderBar(m.count, maxModuleCount)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        {/* ====== 连接状态 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>CONNECTION</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('logs.dataSourceTitle')}
            </h3>
            <div className="flex-1 space-y-4">
              {[
                { label: t('logs.apiNotif'), value: t('logs.connectedValue') },
                { label: 'WebSocket', value: wsConnected ? t('logs.realtimePush') : '离线 / 重连中' },
                { label: t('logs.maxCache'), value: t('logs.maxCacheValue') },
              ].map((s) => (
                <div key={s.label} className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}>
                  <span className="text-label">{s.label}</span>
                  <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {s.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

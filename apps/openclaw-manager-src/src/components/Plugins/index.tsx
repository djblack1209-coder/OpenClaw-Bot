/**
 * Plugins — MCP 插件管理页面 (Sonic Abyss Bento Grid 风格)
 * 数据来自 IPC (getMcpPluginStatus / getSkillsStatus) + HTTP 降级
 * 30 秒自动刷新，开关按钮调用 startMcpPlugin / stopMcpPlugin
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from 'sonner';
import {
  Blocks, Wifi, WifiOff, Power,
  Terminal, Radio, Loader2, RefreshCw,
} from 'lucide-react';
import { api } from '../../lib/api';
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

/* ====== 类型定义 ====== */

/** 标准化后的插件条目 */
interface PluginItem {
  id: string;
  name: string;
  version: string;
  status: 'running' | 'stopped' | 'unknown';
  protocol: string;
}

/** 日志条目 */
interface LogEntry {
  ts: string;
  msg: string;
}

/* ====== 工具函数 ====== */

/** 协议标签颜色 */
function protocolColor(p: string) {
  if (p === 'stdio') return 'var(--accent-green)';
  if (p === 'sse') return 'var(--accent-cyan)';
  if (p === 'ws') return 'var(--accent-purple)';
  return 'var(--text-tertiary)';
}

/** 当前时间戳字符串 HH:MM:SS */
function nowTs(): string {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':');
}

/* ====== 主组件 ====== */

export function Plugins() {
  const { t } = useLanguage();
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null); // 正在切换的插件 id
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── 拉取插件数据 ── */
  const fetchData = useCallback(async () => {
    const items: PluginItem[] = [];
    const newLogs: LogEntry[] = [];

    try {
      // 策略 1: 尝试通过 IPC 获取 MCP 插件列表（遍历已知的常见 id）
      // 策略 2: 尝试 HTTP /api/v1/cli/tools 获取 CLI 工具
      // 策略 3: 尝试 getSkillsStatus 获取技能列表

      // 先尝试 HTTP 获取 CLI 工具列表
      try {
        const toolsResp = await clawbotFetchJson<Record<string, unknown>>('/api/v1/cli/tools');
        if (toolsResp && typeof toolsResp === 'object') {
          const toolsList = Array.isArray(toolsResp)
            ? toolsResp
            : (toolsResp as Record<string, unknown>).tools
              ? (toolsResp as Record<string, unknown>).tools as Array<Record<string, unknown>>
              : Object.entries(toolsResp).map(([k, v]) => ({
                  id: k,
                  name: k,
                  ...(typeof v === 'object' ? v : {}),
                }));

          if (Array.isArray(toolsList)) {
            toolsList.forEach((t: Record<string, unknown>) => {
              items.push({
                id: String(t.id || t.name || ''),
                name: String(t.name || t.id || '未知工具'),
                version: String(t.version || '—'),
                status: t.status === 'running' || t.enabled ? 'running' : 'stopped',
                protocol: String(t.protocol || t.type || '—'),
              });
            });
          }
          newLogs.push({ ts: nowTs(), msg: `[SYSTEM] 获取到 ${items.length} 个 CLI 工具` });
        }
      } catch {
        // CLI 工具接口不存在，继续尝试其他方式
        newLogs.push({ ts: nowTs(), msg: '[SYSTEM] CLI 工具接口不可用，尝试技能列表' });
      }

      // 如果 CLI 工具为空，尝试 Skills 列表
      if (items.length === 0) {
        try {
          const skills = await api.getSkillsStatus();
          if (skills?.skills?.length) {
            skills.skills.forEach((sk) => {
              items.push({
                id: sk.name,
                name: sk.name,
                version: '—',
                status: sk.enabled ? 'running' : 'stopped',
                protocol: 'skill',
              });
            });
            newLogs.push({ ts: nowTs(), msg: `[SYSTEM] 加载了 ${skills.total} 个技能，${skills.enabled} 个已启用` });
          }
        } catch {
          newLogs.push({ ts: nowTs(), msg: '[SYSTEM] 技能列表不可用' });
        }
      }

      // 如果仍然没有数据
      if (items.length === 0) {
        newLogs.push({ ts: nowTs(), msg: '[SYSTEM] 暂无可用插件数据' });
      }
    } catch {
      newLogs.push({ ts: nowTs(), msg: '[ERROR] 获取插件数据失败' });
    } finally {
      setPlugins(items);
      setLogs((prev) => [...newLogs, ...prev].slice(0, 20)); // 保留最新 20 条
      setLoading(false);
    }
  }, []);

  /* ── 首次加载 + 自动刷新 ── */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* ── 切换插件开关 ── */
  const handleToggle = useCallback(async (plugin: PluginItem) => {
    /* IPC 开关需要 Tauri 环境 */
    if (!isTauri()) {
      toast.error(t('plugins.toggleNeedsTauri'));
      return;
    }
    setToggling(plugin.id);
    try {
      if (plugin.status === 'running') {
        await api.stopMcpPlugin(plugin.id);
        toast.success(`${plugin.name} ${t('plugins.stopped')}`);
        setLogs((prev) => [{ ts: nowTs(), msg: `[PLUGIN] ${plugin.name} 已停用 — 手动关闭` }, ...prev].slice(0, 20));
      } else {
        await api.startMcpPlugin(plugin.id);
        toast.success(`${plugin.name} ${t('plugins.started')}`);
        setLogs((prev) => [{ ts: nowTs(), msg: `[PLUGIN] ${plugin.name} 已启动 — 手动开启` }, ...prev].slice(0, 20));
      }
      // 刷新数据
      await fetchData();
    } catch (err) {
      toast.error(`${t('plugins.operationFailed')}: ${err instanceof Error ? err.message : t('plugins.unknownError')}`);
      setLogs((prev) => [{ ts: nowTs(), msg: `[ERROR] ${plugin.name} 切换失败: ${err instanceof Error ? err.message : '未知错误'}` }, ...prev].slice(0, 20));
    } finally {
      setToggling(null);
    }
  }, [fetchData]);

  /* ── 批量启用所有插件 ── */
  const handleEnableAll = useCallback(async () => {
    if (!isTauri()) {
      toast.error(t('plugins.toggleNeedsTauri'));
      return;
    }
    const stopped = plugins.filter((p) => p.status !== 'running');
    if (stopped.length === 0) return;
    setToggling('__all__');
    try {
      await Promise.allSettled(stopped.map((p) => api.startMcpPlugin(p.id)));
      toast.success(t('plugins.enableAllSuccess'));
      setLogs((prev) => [{ ts: nowTs(), msg: `[SYSTEM] 批量启用 ${stopped.length} 个插件` }, ...prev].slice(0, 20));
      await fetchData();
    } catch (err) {
      toast.error(`${t('plugins.enableAllFailed')}: ${err instanceof Error ? err.message : t('plugins.unknownError')}`);
    } finally {
      setToggling(null);
    }
  }, [plugins, fetchData]);

  /* ── 统计 ── */
  const running = plugins.filter((p) => p.status === 'running').length;
  const stopped = plugins.filter((p) => p.status !== 'running').length;

  /* ── 协议分组统计 ── */
  const protocolStats = (() => {
    const map: Record<string, { count: number; active: number }> = {};
    plugins.forEach((p) => {
      const key = p.protocol || '—';
      if (!map[key]) map[key] = { count: 0, active: 0 };
      map[key].count++;
      if (p.status === 'running') map[key].active++;
    });
    return Object.entries(map).map(([name, data]) => ({
      name,
      label: name.toUpperCase(),
      connections: data.active,
      total: data.count,
      status: data.active > 0 ? 'active' : 'idle',
      color: data.active > 0 ? protocolColor(name) : 'var(--text-disabled)',
    }));
  })();

  /* ── 加载中 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-[var(--accent-purple)]" size={32} />
        <span className="ml-3 text-[var(--text-secondary)] font-mono text-sm">{t('plugins.loading')}</span>
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
        {/* ====== 插件列表 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(167,139,250,0.12)' }}
              >
                <Blocks size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  PROTOCOL BRIDGE
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('plugins.subtitle')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {stopped > 0 && (
                  <button
                    disabled={toggling === '__all__'}
                    onClick={handleEnableAll}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md font-mono text-[10px] tracking-wider transition-colors disabled:opacity-50"
                    style={{ background: 'rgba(0,255,170,0.1)', color: 'var(--accent-green)' }}
                  >
                    {toggling === '__all__' ? (
                      <Loader2 size={10} className="animate-spin" />
                    ) : (
                      <Power size={10} />
                    )}
                    {t('plugins.enableAll')}
                  </button>
                )}
                <button
                  onClick={() => { setLoading(true); fetchData(); }}
                  className="text-[var(--text-tertiary)] hover:text-[var(--accent-cyan)] transition-colors"
                  title={t('plugins.manualRefresh')}
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>

            {plugins.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)] font-mono text-sm">
                {t('plugins.noPluginData')}
              </div>
            ) : (
              <>
                {/* 表头 */}
                <div
                  className="grid grid-cols-12 gap-2 px-4 py-2 rounded-lg mb-1"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <span className="text-label col-span-5" style={{ fontSize: '10px' }}>{t('plugins.colName')}</span>
                  <span className="text-label col-span-2 text-center" style={{ fontSize: '10px' }}>{t('plugins.colVersion')}</span>
                  <span className="text-label col-span-2 text-center" style={{ fontSize: '10px' }}>{t('plugins.colProtocol')}</span>
                  <span className="text-label col-span-1 text-center" style={{ fontSize: '10px' }}>{t('plugins.colStatus')}</span>
                  <span className="text-label col-span-2 text-right" style={{ fontSize: '10px' }}>{t('plugins.colSwitch')}</span>
                </div>

                {/* 插件行 */}
                <div className="flex-1 space-y-1">
                  {plugins.map((pl) => {
                    const isOn = pl.status === 'running';
                    const pc = protocolColor(pl.protocol);
                    const isToggling = toggling === pl.id;
                    return (
                      <div
                        key={pl.id}
                        className="grid grid-cols-12 gap-2 items-center py-3 px-4 rounded-lg"
                        style={{ background: 'var(--bg-secondary)' }}
                      >
                        <span className="font-mono text-xs col-span-5 truncate" style={{ color: 'var(--text-primary)' }}>
                          {pl.name}
                        </span>
                        <span className="font-mono text-[10px] col-span-2 text-center" style={{ color: 'var(--text-disabled)' }}>
                          {pl.version !== '—' ? `v${pl.version}` : '—'}
                        </span>
                        <div className="col-span-2 flex justify-center">
                          <span
                            className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider"
                            style={{ background: `${pc}15`, color: pc }}
                          >
                            {pl.protocol.toUpperCase()}
                          </span>
                        </div>
                        <div className="col-span-1 flex justify-center">
                          <span
                            className={clsx('w-2 h-2 rounded-full', isOn && 'animate-pulse')}
                            style={{ background: isOn ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                          />
                        </div>
                        <div className="col-span-2 flex justify-end">
                          <button
                            disabled={isToggling}
                            onClick={() => handleToggle(pl)}
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono text-[10px] tracking-wider transition-colors disabled:opacity-50"
                            style={{
                              background: isOn ? 'rgba(0,255,170,0.1)' : 'rgba(255,255,255,0.04)',
                              color: isOn ? 'var(--accent-green)' : 'var(--text-disabled)',
                            }}
                          >
                            {isToggling ? (
                              <Loader2 size={10} className="animate-spin" />
                            ) : (
                              <Power size={10} />
                            )}
                            {isOn ? t('plugins.running') : t('plugins.disabled')}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </motion.div>

        {/* ====== {t('plugins.pluginStats')} (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              PLUGIN STATS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              插件统计
            </h3>

            <div className="grid grid-cols-2 gap-4 flex-1">
              {[
                { label: t('plugins.installed'), value: plugins.length, color: 'var(--accent-cyan)' },
                { label: t('plugins.runningCount'), value: running, color: 'var(--accent-green)' },
                { label: t('plugins.stoppedCount'), value: stopped, color: 'var(--accent-red)' },
                { label: t('plugins.protocolTypes'), value: protocolStats.length, color: 'var(--accent-amber)' },
              ].map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 连接总览 */}
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <span className="text-label">CONNECTION HEALTH</span>
              <div className="flex items-center gap-2 mt-2">
                <Wifi size={14} style={{ color: running > 0 ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                  {running} {t('plugins.activeConnections')}
                </span>
                <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--text-disabled)' }}>
                  {plugins.length > 0 ? '实时' : 'N/A'}
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== {t('plugins.protocolStatus')} (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              PROTOCOL STATUS
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              协议状态
            </h3>

            <div className="flex-1 space-y-3">
              {protocolStats.length === 0 ? (
                <div className="text-center py-6 text-[var(--text-tertiary)] font-mono text-sm">
                  {t('plugins.noData')}
                </div>
              ) : (
                protocolStats.map((pr) => {
                  const isActive = pr.status === 'active';
                  return (
                    <div
                      key={pr.name}
                      className="flex items-center justify-between py-3 px-4 rounded-lg"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <div className="flex items-center gap-3">
                        {isActive ? (
                          <Radio size={14} style={{ color: pr.color }} />
                        ) : (
                          <WifiOff size={14} style={{ color: pr.color }} />
                        )}
                        <div>
                          <p className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                            {pr.name.toUpperCase()}
                          </p>
                          <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                            {isActive ? t('plugins.connectionOk') : t('plugins.noActiveConn')}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-sm font-bold" style={{ color: pr.color }}>
                          {pr.connections}/{pr.total}
                        </p>
                        <span className="text-label" style={{ fontSize: '9px' }}>{t('plugins.activeTotal')}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== {t('plugins.recentEvents')} (col-6) ====== */}
        <motion.div className="col-span-12 lg:col-span-6" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                  RECENT EVENTS
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  最近事件
                </h3>
              </div>
              <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                <Terminal size={12} className="inline mr-1" />LIVE
              </span>
            </div>

            <div
              className="flex-1 rounded-lg p-4 space-y-1.5 overflow-hidden"
              style={{ background: 'var(--bg-base)' }}
            >
              {logs.length === 0 ? (
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">{t('plugins.noEvents')}</span>
              ) : (
                logs.map((l, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="font-mono text-[10px] shrink-0" style={{ color: 'var(--text-disabled)' }}>
                      {l.ts}
                    </span>
                    <span className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      {l.msg}
                    </span>
                  </div>
                ))
              )}
              <span className="font-mono text-[10px] animate-pulse" style={{ color: 'var(--accent-purple)' }}>
                █
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

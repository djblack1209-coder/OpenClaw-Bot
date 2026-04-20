/**
 * DevPanel — 开发者工作台页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * {t('devPanel.sysInfo')}来自 api.getSystemInfo()，日志来自通知 API
 * {t('devPanel.envVars')}使用 api.getEnvValue() 读取非敏感值
 * {t('devPanel.apiTest')}使用真实 fetch 调用
 * 30 秒自动刷新
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Terminal,
  Cpu,
  Eye,
  EyeOff,
  Zap,
  Activity,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { api } from '../../lib/api';
import { toast } from 'sonner';
import { useLanguage } from '../../i18n';
import type { SystemInfo } from '../../lib/tauri-core';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 自动刷新间隔 ====== */
const REFRESH_INTERVAL_MS = 30_000;

/* ====== 类型定义 ====== */

/** 通知/日志条目 */
interface NotificationEntry {
  id?: string;
  message?: string;
  content?: string;
  text?: string;
  level?: string;
  category?: string;
  created_at?: string;
  timestamp?: string;
  [key: string]: unknown;
}

/** 环境变量条目 */
interface EnvEntry {
  key: string;
  value: string | null;
  masked: boolean;
  loading: boolean;
  error: boolean;
}

/** API 测试结果 */
interface ApiTestResult {
  name: string;
  endpoint: string;
  status: 'idle' | 'testing' | 'ok' | 'slow' | 'error';
  latencyMs: number | null;
  errorMsg: string | null;
}

/* ====== 要读取的环境变量配置 ====== */
const ENV_KEYS: Array<{ key: string; masked: boolean }> = [
  { key: 'LOG_LEVEL', masked: false },
  { key: 'OPENCLAW_PORT', masked: false },
  { key: 'REDIS_URL', masked: false },
  { key: 'OPENAI_API_KEY', masked: true },
  { key: 'TELEGRAM_BOT_TOKEN', masked: true },
];

/* ====== API 测试端点配置 ====== */
const API_TEST_ENDPOINTS = [
  { name: 'devPanel.apiStatus', endpoint: '/api/v1/status' },
  { name: 'devPanel.apiPerf', endpoint: '/api/v1/perf' },
  { name: 'devPanel.apiNotif', endpoint: '/api/v1/system/notifications?limit=1' },
];

/* ====== 工具函数 ====== */

function apiStatusStyle(s: ApiTestResult['status']) {
  switch (s) {
    case 'ok': return { color: 'var(--accent-green)', label: 'devPanel.statusOk' };
    case 'slow': return { color: 'var(--accent-amber)', label: 'devPanel.statusSlow' };
    case 'error': return { color: 'var(--accent-red)', label: 'devPanel.statusError' };
    case 'testing': return { color: 'var(--accent-cyan)', label: 'devPanel.statusTesting' };
    default: return { color: 'var(--text-disabled)', label: 'devPanel.statusIdle' };
  }
}

/** 掩码敏感值 */
function maskValue(val: string): string {
  if (val.length <= 8) return '****';
  return val.slice(0, 4) + '****...' + val.slice(-4);
}

/** 获取通知文本内容 */
function getNotificationText(n: NotificationEntry): string {
  return n.message || n.content || n.text || JSON.stringify(n);
}

/** 获取日志颜色 */
function getLogColor(level?: string): string {
  switch (level?.toUpperCase()) {
    case 'ERROR': return 'var(--accent-red)';
    case 'WARNING':
    case 'WARN': return 'var(--accent-amber)';
    case 'SUCCESS': return 'var(--accent-green)';
    default: return 'var(--text-tertiary)';
  }
}

/* ====== 暂无数据占位组件 ====== */
function NoDataPlaceholder({ reason }: { reason: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-8 gap-2"
      style={{ color: 'var(--text-disabled)' }}
    >
      <AlertCircle size={20} />
      <span className="font-mono text-xs text-center">{reason}</span>
    </div>
  );
}

/* ====== 主组件 ====== */

export default function DevPanel() {
  const { t } = useLanguage();
  /* 状态 */
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [sysInfoError, setSysInfoError] = useState<string | null>(null);
  const [logs, setLogs] = useState<NotificationEntry[]>([]);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [envVars, setEnvVars] = useState<EnvEntry[]>(
    ENV_KEYS.map((e) => ({ key: e.key, value: null, masked: e.masked, loading: true, error: false }))
  );
  const [apiTests, setApiTests] = useState<ApiTestResult[]>(
    API_TEST_ENDPOINTS.map((e) => ({ ...e, status: 'idle', latencyMs: null, errorMsg: null }))
  );
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  /* 拉取系统信息和日志 */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [sysRes, logsRes] = await Promise.allSettled([
        api.getSystemInfo(),
        clawbotFetchJson<{ notifications?: NotificationEntry[]; data?: NotificationEntry[] }>(
          '/api/v1/system/notifications?limit=15'
        ),
      ]);

      if (!mountedRef.current) return;

      if (sysRes.status === 'fulfilled') {
        setSysInfo(sysRes.value);
        setSysInfoError(null);
      } else {
        setSysInfoError(t('devPanel.sysInfoUnavailable'));
      }

      if (logsRes.status === 'fulfilled') {
        const data = logsRes.value;
        const items = Array.isArray(data)
          ? data
          : data?.notifications ?? data?.data ?? [];
        setLogs(items);
        setLogsError(null);
      } else {
        setLogsError(t('devPanel.logsUnavailable'));
      }
    } catch {
      if (!mountedRef.current) return;
      toast.error(t('devPanel.loadFailed'));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  /* 拉取环境变量 */
  const fetchEnvVars = useCallback(async () => {
    const results = await Promise.allSettled(
      ENV_KEYS.map((e) => api.getEnvValue(e.key))
    );
    if (!mountedRef.current) return;

    setEnvVars(
      ENV_KEYS.map((e, i) => {
        const r = results[i];
        if (r.status === 'fulfilled' && r.value != null) {
          return {
            key: e.key,
            value: e.masked ? maskValue(String(r.value)) : String(r.value),
            masked: e.masked,
            loading: false,
            error: false,
          };
        }
        return {
          key: e.key,
          value: t('devPanel.notConfigured'),
          masked: e.masked,
          loading: false,
          error: r.status === 'rejected',
        };
      })
    );
  }, []);

  /* API 单端点测试 */
  const runApiTest = useCallback(async (index: number) => {
    setApiTests((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], status: 'testing', latencyMs: null, errorMsg: null };
      return next;
    });

    const endpoint = API_TEST_ENDPOINTS[index].endpoint;
    const start = performance.now();
    try {
      await clawbotFetchJson(endpoint);
      const ms = Math.round(performance.now() - start);
      if (!mountedRef.current) return;
      setApiTests((prev) => {
        const next = [...prev];
        next[index] = {
          ...next[index],
          status: ms > 500 ? 'slow' : 'ok',
          latencyMs: ms,
          errorMsg: null,
        };
        return next;
      });
    } catch (err) {
      const ms = Math.round(performance.now() - start);
      if (!mountedRef.current) return;
      setApiTests((prev) => {
        const next = [...prev];
        next[index] = {
          ...next[index],
          status: 'error',
          latencyMs: ms,
          errorMsg: err instanceof Error ? err.message : '请求失败',
        };
        return next;
      });
    }
  }, []);

  /* 测试全部 API */
  const runAllApiTests = useCallback(async () => {
    for (let i = 0; i < API_TEST_ENDPOINTS.length; i++) {
      await runApiTest(i);
    }
  }, [runApiTest]);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();
    fetchEnvVars();
    const timer = setInterval(() => fetchData(true), REFRESH_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchData, fetchEnvVars]);

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 系统日志 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card h-full flex flex-col" style={{ background: 'rgba(5,5,12,0.95)' }}>
            {/* 终端标题栏 */}
            <div
              className="flex items-center gap-3 px-5 py-3 border-b"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-red)' }} />
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-amber)' }} />
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--accent-green)' }} />
              </div>
              <div className="flex items-center gap-2 flex-1">
                <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
                <h2 className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  SYSTEM LOG
                </h2>
                <span className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('devPanel.sysLogSubtitle')}
                </span>
              </div>
              {loading && <Loader2 size={14} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />}
            </div>

            {/* 日志内容 */}
            <div className="flex-1 p-5 overflow-y-auto scroll-container">
              {logsError ? (
                <NoDataPlaceholder reason={logsError} />
              ) : logs.length === 0 ? (
                <NoDataPlaceholder reason="{t('devPanel.noSysLogs')}" />
              ) : (
                <div className="space-y-0.5">
                  {logs.map((entry, i) => (
                    <div key={entry.id ?? i} className="font-mono text-[12px] leading-relaxed">
                      <span style={{ color: 'var(--text-disabled)' }}>
                        [{entry.created_at ?? entry.timestamp ?? '--'}]
                      </span>{' '}
                      <span style={{ color: getLogColor(entry.level) }}>
                        {entry.level ? `[${entry.level.toUpperCase()}] ` : ''}
                      </span>
                      <span style={{ color: 'var(--text-primary)' }}>
                        {getNotificationText(entry)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 底部提示 */}
            <div
              className="px-5 py-2 border-t font-mono text-[10px]"
              style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-disabled)' }}
            >
              {t('devPanel.dataSource')}
            </div>
          </div>
        </motion.div>

        {/* ====== 系统信息 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Cpu size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  系统信息
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  SYSTEM INFO
                </p>
              </div>
            </div>

            {sysInfoError ? (
              <NoDataPlaceholder reason={sysInfoError} />
            ) : !sysInfo ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />
              </div>
            ) : (
              <div className="flex-1 space-y-2">
                {[
                  { label: 'OS', value: `${sysInfo.os} ${sysInfo.os_version}`, color: 'var(--text-primary)' },
                  { label: 'Arch', value: sysInfo.arch, color: 'var(--accent-cyan)' },
                  { label: 'OpenClaw', value: sysInfo.openclaw_version ?? (sysInfo.openclaw_installed ? t('devPanel.installed') : t('devPanel.notInstalled')), color: sysInfo.openclaw_installed ? 'var(--accent-green)' : 'var(--accent-red)' },
                  { label: 'Node', value: sysInfo.node_version ?? '--', color: 'var(--accent-amber)' },
                  { label: t('devPanel.configDir'), value: sysInfo.config_dir ?? '--', color: 'var(--text-tertiary)' },
                ].map((info) => (
                  <div
                    key={info.label}
                    className="flex items-center justify-between py-2.5 px-3 rounded-lg"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <span className="text-label">{info.label}</span>
                    <span className="font-mono text-xs font-semibold truncate ml-2" style={{ color: info.color }}>
                      {info.value}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== 环境变量 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(168,85,247,0.15)' }}
              >
                <EyeOff size={20} style={{ color: 'var(--accent-purple)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  环境变量
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  ENV VARIABLES
                </p>
              </div>
            </div>

            <div className="flex-1 space-y-2">
              {envVars.map((env) => (
                <div
                  key={env.key}
                  className="py-2.5 px-3 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] font-bold" style={{ color: 'var(--accent-cyan)' }}>
                      {env.key}
                    </span>
                    {env.masked && <Eye size={10} style={{ color: 'var(--text-disabled)' }} />}
                  </div>
                  <p
                    className="font-mono text-[11px] mt-1 truncate"
                    style={{
                      color: env.loading
                        ? 'var(--text-disabled)'
                        : env.error
                          ? 'var(--accent-red)'
                          : env.masked
                            ? 'var(--text-disabled)'
                            : 'var(--text-primary)',
                    }}
                  >
                    {env.loading ? t('devPanel.reading') : env.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== API 测试 (col-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6 flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.15)' }}
              >
                <Zap size={20} style={{ color: 'var(--accent-amber)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  API 测试
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('devPanel.apiTestSubtitle')}
                </p>
              </div>
              <button
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all hover:opacity-80"
                style={{ background: 'rgba(245,158,11,0.15)', color: 'var(--accent-amber)' }}
                onClick={runAllApiTests}
              >
                <RefreshCw size={12} />
                {t('devPanel.testAll')}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {apiTests.map((test, i) => {
                const st = apiStatusStyle(test.status);
                return (
                  <button
                    key={t(test.name)}
                    className="py-4 px-4 rounded-lg text-left transition-all hover:opacity-80"
                    style={{ background: 'var(--bg-secondary)' }}
                    onClick={() => runApiTest(i)}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                        {t(test.name)}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded font-mono text-[9px] tracking-wider"
                        style={{ background: `color-mix(in srgb, ${st.color} 15%, transparent)`, color: st.color }}
                      >
                        {t(st.label)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {test.endpoint}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {test.status === 'testing' ? (
                          <Loader2 size={10} className="animate-spin" style={{ color: st.color }} />
                        ) : (
                          <Activity size={10} style={{ color: st.color }} />
                        )}
                        <span className="text-metric" style={{ color: st.color, fontSize: '16px' }}>
                          {test.latencyMs != null ? `${test.latencyMs}ms` : '--'}
                        </span>
                      </div>
                    </div>
                    {test.errorMsg && (
                      <p className="font-mono text-[10px] mt-1 truncate" style={{ color: 'var(--accent-red)' }}>
                        {test.errorMsg}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

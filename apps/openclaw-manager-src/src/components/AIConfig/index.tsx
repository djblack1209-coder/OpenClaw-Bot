/**
 * AIConfig — AI 模型配置 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 真实 API 数据：渠道(模型)列表 / API 池统计 / 启禁用操作
 */
import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from '@/lib/notify';
import {
  Cpu,
  Terminal,
  Loader2,
  ToggleLeft,
  ToggleRight,
  RefreshCw,
  DollarSign,
  Zap,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';
import { useActivePagePolling } from '@/hooks/useActivePagePolling';

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

/** 渠道条目（来自 newApiChannels） */
interface ChannelItem {
  id: number;
  name?: string;
  type?: number;
  key?: string;
  base_url?: string;
  models?: string;
  group?: string;
  status?: number;            // 1=启用, 2=禁用
  used_quota?: number;
  balance?: number;
  priority?: number;
  response_time?: number;
  test_time?: number;
  created_time?: number;
  [key: string]: unknown;
}

/** API 池统计（来自 clawbotPoolStats） */
interface PoolStats {
  total_calls?: number;
  total_cost?: number;
  total_tokens?: number;
  avg_latency?: number;
  avg_latency_ms?: number;
  providers?: ProviderStat[];
  models?: ModelStat[];
  today_cost?: number;
  week_cost?: number;
  month_cost?: number;
  budget?: number;
  [key: string]: unknown;
}

interface ProviderStat {
  name?: string;
  provider?: string;
  calls?: number;
  cost?: number;
  avg_latency?: number;
  avg_latency_ms?: number;
  errors?: number;
  [key: string]: unknown;
}

interface ModelStat {
  name?: string;
  model?: string;
  calls?: number;
  cost?: number;
  avg_latency?: number;
  avg_latency_ms?: number;
  [key: string]: unknown;
}

/* ====== 工具函数 ====== */

/** 安全解析 API 响应 */
async function parseResponse<T>(resp: unknown): Promise<T> {
  if (resp instanceof Response) {
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }
  return resp as T;
}

/** 渠道类型映射 — New-API/One-API 标准类型编号 */
const CHANNEL_TYPE_LABELS: Record<number, string> = {
  0: 'OpenAI',       // New-API 默认类型（部分分支用 0 代替 1）
  1: 'OpenAI',
  2: 'API2D',
  3: 'Azure',
  8: 'Custom',
  14: 'Anthropic',
  15: 'Baidu',
  17: 'Ali',
  18: 'Xunfei',
  19: 'AI360',
  23: 'Tencent',
  24: 'Gemini',
  25: 'Moonshot',
  26: 'Baichuan',
  27: 'Minimax',
  28: 'Mistral',
  29: 'Groq',
  31: 'ZeroOne',
  33: 'SiliconFlow',
  34: 'DeepSeek',
  36: 'Cohere',
  37: 'StabilityAI',
  38: 'Coze',
  40: 'Custom',
};

function isChannelEnabled(ch: ChannelItem): boolean {
  return ch.status === 1;
}

/** 延迟 → 颜色 */
function latencyColor(ms?: number): string {
  if (!ms || ms === 0) return 'var(--text-disabled)';
  if (ms < 500) return 'var(--accent-green)';
  if (ms < 1500) return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

/** 终端风格条形图 */
function renderBar(value: number, max: number, width: number = 20): string {
  const ratio = max > 0 ? value / max : 0;
  const filled = Math.round(ratio * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

/** 格式化金额 */
function formatCost(val?: number): string {
  if (val == null) return '—';
  return `¥${val.toFixed(2)}`;
}

/* ====== 主组件 ====== */

export function AIConfig() {
  const { t } = useLanguage();
  /* ── 状态 ── */
  const [loading, setLoading] = useState(true);
  const [channels, setChannels] = useState<ChannelItem[]>([]);
  const [poolStats, setPoolStats] = useState<PoolStats | null>(null);
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());

  /* ── 数据拉取 ── */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [channelsResp, poolResp] = await Promise.allSettled([
        api.newApiChannels(),
        api.clawbotPoolStats(),
      ]);

      // 解析渠道列表
      let channelsLoaded = false;
      if (channelsResp.status === 'fulfilled') {
        try {
          const raw = await parseResponse<Record<string, unknown>>(channelsResp.value);
          const list: ChannelItem[] = Array.isArray(raw) ? raw
            : Array.isArray(raw?.data) ? raw.data
            : Array.isArray(raw?.channels) ? raw.channels
            : [];
          setChannels(list);
          channelsLoaded = list.length > 0;
        } catch (err) {
          console.warn('[AIConfig] 渠道列表加载失败，回退到 API 池统计:', err);
        }
      }

      // 解析 API 池统计
      if (poolResp.status === 'fulfilled') {
        const data = poolResp.value as PoolStats;
        setPoolStats(data);
        if (!channelsLoaded) {
          const total = Number((data as PoolStats)?.total_sources ?? (data as PoolStats)?.pool_total_sources ?? 0);
          if (total > 0) {
            setChannels(Array.from({ length: total }, (_, i) => ({
              id: -(i + 1),
              name: `${t('aiConfig.channelPrefix')} #${i + 1}`,
              type: 0,
              status: 1,
              models: '',
              response_time: 0,
            })) as ChannelItem[]);
          }
        }
      }
    } catch (err) {
      console.error('[AIConfig] 数据加载失败:', err);
      // 初始加载和自动刷新不弹 toast，避免服务未运行时反复弹错
    } finally {
      setLoading(false);
    }
  }, [t]);

  /* 使用可见性感知轮询，仅在 AI 配置页激活时刷新数据 */
  useActivePagePolling('aiconfig', fetchData, 30_000);

  /* ── 渠道启用/禁用切换 ── */
  const handleToggle = useCallback(async (channelId: number) => {
    setTogglingIds((prev) => new Set(prev).add(channelId));
    try {
      await parseResponse(await api.newApiToggleChannel(channelId));
      toast.success(t('aiConfig.channelToggled'), { channel: 'log' });
      setChannels((prev) =>
        prev.map((ch) =>
          ch.id === channelId
            ? { ...ch, status: ch.status === 1 ? 2 : 1 }
            : ch,
        ),
      );
    } catch (err) {
      console.error('[AIConfig] 切换渠道失败:', err);
      toast.error(t('aiConfig.channelToggleFailed'), { channel: 'notification' });
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(channelId);
        return next;
      });
    }
  }, [t]);

  /* ── 派生数据 ── */
  const enabledCount = channels.filter(isChannelEnabled).length;
  const totalChannelsDisplay = channels.length > 0
    ? channels.length
    : Number((poolStats as PoolStats)?.total_sources ?? (poolStats as PoolStats)?.pool_total_sources ?? 0);
  const enabledChannelsDisplay = enabledCount > 0
    ? enabledCount
    : Number((poolStats as PoolStats)?.active_sources ?? (poolStats as PoolStats)?.pool_active_sources ?? 0);

  // 从渠道提取所有唯一模型
  const allModels = Array.from(
    new Set(
      channels.flatMap((ch) =>
        ch.models ? ch.models.split(',').map((m) => m.trim()).filter(Boolean) : [],
      ),
    ),
  );
  const totalModelsDisplay = allModels.length > 0
    ? allModels.length
    : Object.values(((poolStats as PoolStats)?.by_provider ?? {}) as Record<string, { models?: number }>).reduce(
        (sum, item) => sum + Number(item?.models ?? 0),
        0,
      );

  // 按提供商分组
  const providerGroups: Record<string, ChannelItem[]> = {};
  channels.forEach((ch) => {
    const label = CHANNEL_TYPE_LABELS[ch.type ?? 0] || `Type ${ch.type}`;
    (providerGroups[label] ??= []).push(ch);
  });

  // {t('aiConfig.costStats')}（从 poolStats 或渠道 used_quota 聚合）
  const todayCost = poolStats?.today_cost;
  const weekCost = poolStats?.week_cost;
  const monthCost = poolStats?.month_cost;
  const budget = poolStats?.budget;
  const avgLatency = poolStats?.avg_latency ?? poolStats?.avg_latency_ms;

  // 模型性能条 — 从 poolStats.models 或 channels.response_time 构建
  const perfBars = (() => {
    // 优先用 poolStats 的模型级数据
    if (poolStats?.models && poolStats.models.length > 0) {
      return poolStats.models
        .filter((m) => (m.avg_latency ?? m.avg_latency_ms ?? 0) > 0)
        .sort((a, b) => (a.avg_latency ?? a.avg_latency_ms ?? 0) - (b.avg_latency ?? b.avg_latency_ms ?? 0))
        .slice(0, 6)
        .map((m) => ({
          name: m.name ?? m.model ?? '未知',
          ms: m.avg_latency ?? m.avg_latency_ms ?? 0,
        }));
    }
    // 降级：从渠道的 response_time 构建
    return channels
      .filter((ch) => ch.response_time && ch.response_time > 0)
      .sort((a, b) => (a.response_time ?? 0) - (b.response_time ?? 0))
      .slice(0, 6)
      .map((ch) => ({
        name: ch.name || `${t('aiConfig.channelPrefix')} #${ch.id}`,
        ms: ch.response_time ?? 0,
      }));
  })();
  const maxMs = perfBars.length > 0 ? Math.max(...perfBars.map((p) => p.ms)) : 1;

  /* ── {t('aiConfig.routeStrategy')} — 只读展示（无 API） ── */
  const STRATEGIES_KEYS = ['aiConfig.strategyAuto', 'aiConfig.strategyCost', 'aiConfig.strategyQuality', 'aiConfig.strategySpeed'];
  const [strategy, setStrategy] = useState('aiConfig.strategyAuto');

  /* ── 加载态 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin" size={32} style={{ color: 'var(--accent-cyan)' }} />
        <span className="ml-3 font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
          {t('aiConfig.loadingData')}
        </span>
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
        {/* ====== 模型池总览 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(6,182,212,0.15)' }}
              >
                <Cpu size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  LLM ROUTER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  {t('aiConfig.subtitle')}
                </p>
              </div>
              {/* 统计指标 + 刷新 */}
              <div className="flex items-center gap-3">
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  {totalChannelsDisplay} 渠道 · {enabledChannelsDisplay} 启用 · {totalModelsDisplay} 模型
                </span>
                <button
                  onClick={() => fetchData(true)}
                  className="p-1.5 rounded-lg transition-colors hover:opacity-80"
                  style={{ background: 'var(--bg-tertiary)' }}
                  title={t('aiConfig.refreshData')}
                >
                  <RefreshCw size={12} style={{ color: 'var(--text-secondary)' }} />
                </button>
              </div>
            </div>

            {/* 模型表头 */}
            <div
              className="grid gap-2 px-3 py-1.5 mb-1 font-mono text-[9px] tracking-wider"
              style={{ gridTemplateColumns: '2fr 1fr 60px 70px 80px 50px', color: 'var(--text-disabled)' }}
            >
              <span>{t('aiConfig.colChannelModel')}</span>
              <span>{t('aiConfig.colProvider')}</span>
              <span>{t('aiConfig.colStatus')}</span>
              <span>{t('aiConfig.colLatency')}</span>
              <span>{t('aiConfig.colQuota')}</span>
              <span className="text-center">{t('aiConfig.colSwitch')}</span>
            </div>

            {/* 渠道列表 */}
            <div className="flex-1 space-y-1.5 overflow-y-auto">
              {channels.length === 0 ? (
                <div className="text-center py-8 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('aiConfig.noChannelData')}
                </div>
              ) : (
                channels.map((ch) => {
                  const enabled = isChannelEnabled(ch);
                  const toggling = togglingIds.has(ch.id);
                  const models = ch.models ? ch.models.split(',').map((m) => m.trim()).filter(Boolean) : [];
                  return (
                    <div
                      key={ch.id}
                      className={clsx(
                        'grid gap-2 items-center px-3 py-2.5 rounded-lg transition-opacity',
                        !enabled && 'opacity-40',
                      )}
                      style={{ gridTemplateColumns: '2fr 1fr 60px 70px 80px 50px', background: 'var(--bg-secondary)' }}
                    >
                      {/* 渠道名称 + 模型标签 */}
                      <div className="min-w-0">
                        <span className="font-display text-sm font-semibold truncate block" style={{ color: 'var(--text-primary)' }}>
                          {ch.name || `渠道 #${ch.id}`}
                        </span>
                        {models.length > 0 && (
                          <div className="flex flex-wrap gap-0.5 mt-0.5">
                            {models.slice(0, 3).map((m) => (
                              <span
                                key={m}
                                className="font-mono text-[8px] px-1 rounded"
                                style={{ background: 'rgba(6,182,212,0.08)', color: 'var(--accent-cyan)' }}
                              >
                                {m}
                              </span>
                            ))}
                            {models.length > 3 && (
                              <span className="font-mono text-[8px] px-1" style={{ color: 'var(--text-disabled)' }}>
                                +{models.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      {/* 提供商 */}
                      <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                        {CHANNEL_TYPE_LABELS[ch.type ?? 0] || `Type ${ch.type}`}
                      </span>
                      {/* 状态 */}
                      <div className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
                        <span className="font-mono text-[10px]" style={{ color: enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                          {enabled ? t('aiConfig.statusEnabled') : t('aiConfig.statusDisabled')}
                        </span>
                      </div>
                      {/* 延迟 */}
                      <span className="font-mono text-[11px]" style={{ color: latencyColor(ch.response_time) }}>
                        {ch.response_time ? `${ch.response_time}ms` : '—'}
                      </span>
                      {/* {t('aiConfig.quota')} */}
                      <span className="font-mono text-[11px] font-semibold" style={{ color: 'var(--accent-cyan)' }}>
                        {ch.used_quota != null ? ch.used_quota.toLocaleString() : '—'}
                      </span>
                      {/* 开关 */}
                      <div className="flex justify-center">
                        <button
                          onClick={() => handleToggle(ch.id)}
                          disabled={toggling}
                          className="transition-colors hover:opacity-80 disabled:opacity-50"
                          title={enabled ? t('aiConfig.clickToDisable') : t('aiConfig.clickToEnable')}
                        >
                          {toggling ? (
                            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-disabled)' }} />
                          ) : enabled ? (
                            <ToggleRight size={18} style={{ color: 'var(--accent-green)' }} />
                          ) : (
                            <ToggleLeft size={18} style={{ color: 'var(--text-disabled)' }} />
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== 路由策略 (col-4, 只读) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>STRATEGY</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              路由策略
            </h3>
            <div className="flex-1 space-y-2">
              {STRATEGIES_KEYS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStrategy(s)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left cursor-pointer transition-colors"
                  style={{
                    background: strategy === s ? 'rgba(6,182,212,0.12)' : 'var(--bg-secondary)',
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: strategy === s ? 'var(--accent-cyan)' : 'transparent',
                  }}
                >
                  <div
                    className="w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                    style={{
                      borderColor: strategy === s ? 'var(--accent-cyan)' : 'var(--text-disabled)',
                    }}
                  >
                    {strategy === s && (
                      <div className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-cyan)' }} />
                    )}
                  </div>
                  <span
                    className="font-display text-sm font-semibold"
                    style={{ color: strategy === s ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}
                  >
                    {t(s)}
                  </span>
                </button>
              ))}
            </div>
            <p className="font-mono text-[10px] mt-4" style={{ color: 'var(--text-disabled)' }}>
              {t('aiConfig.currentStrategy')}
            </p>
          </div>
        </motion.div>

        {/* ====== 费用统计 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-5">
              <DollarSign size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>COST</span>
            </div>
            <h3 className="font-display text-lg font-bold mb-5" style={{ color: 'var(--text-primary)' }}>
              费用统计
            </h3>
            <div className="space-y-4 flex-1">
              {[
                { label: t('aiConfig.todayCost'), value: formatCost(todayCost), color: 'var(--accent-cyan)' },
                { label: t('aiConfig.weekCost'), value: formatCost(weekCost), color: 'var(--accent-green)' },
                { label: t('aiConfig.monthCost'), value: formatCost(monthCost), color: 'var(--accent-amber)' },
                { label: t('aiConfig.budget'), value: budget != null ? formatCost(budget) : '—', color: 'var(--text-disabled)' },
              ].map((c) => (
                <div key={c.label}>
                  <span className="text-label">{c.label}</span>
                  <p className="text-metric mt-0.5" style={{ color: c.color, fontSize: '22px' }}>{c.value}</p>
                </div>
              ))}
            </div>
            {/* 预算使用率 */}
            {budget != null && budget > 0 && monthCost != null && (
              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-primary)' }}>
                <div className="flex items-center justify-between">
                  <span className="text-label">{t('aiConfig.budgetUsage')}</span>
                  <span className="font-mono text-[11px]" style={{ color: 'var(--accent-amber)' }}>
                    {Math.round((monthCost / budget) * 100)}%
                  </span>
                </div>
                <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--accent-amber)' }}>
                  {renderBar(monthCost, budget)}
                </div>
              </div>
            )}
            {/* 平均延迟 */}
            {avgLatency != null && (
              <div className="mt-2 flex items-center gap-1.5">
                <Zap size={10} style={{ color: latencyColor(avgLatency) }} />
                <span className="font-mono text-[10px]" style={{ color: latencyColor(avgLatency) }}>
                  {t('aiConfig.avgLatency')}: {Math.round(avgLatency)}ms
                </span>
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== 模型性能对比 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>PERFORMANCE</span>
            <h3 className="font-display text-lg font-bold mt-1 mb-5" style={{ color: 'var(--text-primary)' }}>
              {t('aiConfig.responseComparison')}
            </h3>
            <div className="flex-1 space-y-3">
              {perfBars.length === 0 ? (
                <div className="text-center py-4 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('aiConfig.noPerfData')}
                </div>
              ) : (
                perfBars.map((p) => (
                  <div key={p.name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-display text-xs truncate" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
                      <span className="font-mono text-[10px]" style={{ color: latencyColor(p.ms) }}>{p.ms}ms</span>
                    </div>
                    <div className="font-mono text-[10px] leading-none" style={{ color: latencyColor(p.ms) }}>
                      {renderBar(p.ms, maxMs)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== 提供商分布 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <Terminal size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>PROVIDERS</span>
            </div>
            <div className="flex-1 space-y-2">
              {Object.keys(providerGroups).length === 0 ? (
                <div className="text-center py-4 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('aiConfig.noData')}
                </div>
              ) : (
                Object.entries(providerGroups)
                  .sort((a, b) => b[1].length - a[1].length)
                  .map(([provider, chs]) => {
                    const enabledInGroup = chs.filter(isChannelEnabled).length;
                    // 聚合该提供商的总调用 / 配额
                    const totalQuota = chs.reduce((sum, c) => sum + (c.used_quota ?? 0), 0);
                    return (
                      <div
                        key={provider}
                        className="flex items-center justify-between py-2 px-3 rounded-lg"
                        style={{ background: 'var(--bg-secondary)' }}
                      >
                        <div>
                          <span className="font-display text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                            {provider}
                          </span>
                          <p className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                            {chs.length} 渠道 · {enabledInGroup} 启用
                          </p>
                        </div>
                        <div className="text-right">
                          <span className="font-mono text-[10px]" style={{ color: 'var(--accent-cyan)' }}>
                            {totalQuota > 0 ? totalQuota.toLocaleString() : '—'}
                          </span>
                          <p className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                            配额
                          </p>
                        </div>
                      </div>
                    );
                  })
              )}
            </div>

            <div className="mt-3 pt-3 font-mono text-[10px]" style={{ borderTop: '1px solid var(--glass-border)', color: 'var(--text-disabled)' }}>
              {t('aiConfig.autoRefresh')}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

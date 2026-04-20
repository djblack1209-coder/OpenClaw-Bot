/**
 * APIGateway — API 网关页面 (Sonic Abyss Bento Grid 风格)
 * 12 列 CSS Grid 布局，玻璃卡片 + 终端美学
 * 真实 API 数据：网关状态 / 渠道列表 / 令牌管理
 */
import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from 'sonner';
import {
  Network, Key, Activity,
  Terminal, Loader2, Trash2,
  ToggleLeft, ToggleRight,
  Wifi, WifiOff, RefreshCw,
} from 'lucide-react';
import { api } from '../../lib/api';
import { ConfirmDialog } from '../ui/confirm-dialog';

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

/** 网关状态 */
interface GatewayStatus {
  running?: boolean;
  online?: boolean;
  status?: string;
  version?: string;
  uptime?: number | string;
  channels_count?: number;
  tokens_count?: number;
  [key: string]: unknown;
}

/** 渠道条目 */
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

/** 令牌条目 */
interface TokenItem {
  id: number;
  name?: string;
  key?: string;
  status?: number;
  created_time?: number;
  accessed_time?: number;
  expired_time?: number;
  remain_quota?: number;
  used_quota?: number;
  unlimited_quota?: boolean;
  [key: string]: unknown;
}

/* ====== 工具函数 ====== */

/** 安全解析 API 响应（兼容 Response / JSON 对象 / 数组） */
async function parseResponse<T>(resp: unknown): Promise<T> {
  if (resp instanceof Response) {
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }
  return resp as T;
}

/** 渠道类型映射 */
const CHANNEL_TYPE_LABELS: Record<number, string> = {
  1: 'OpenAI',
  3: 'Azure',
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
  40: 'Custom',
};

/** 渠道是否启用 */
function isChannelEnabled(ch: ChannelItem): boolean {
  return ch.status === 1;
}

/** 时间戳 → 友好时间 */
function formatTime(ts?: number): string {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

/** 响应时间 → 颜色 */
function latencyColor(ms?: number): string {
  if (!ms || ms === 0) return 'var(--text-disabled)';
  if (ms < 500) return 'var(--accent-green)';
  if (ms < 1500) return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

/* ====== 主组件 ====== */

export function APIGateway() {
  /* ── 状态 ── */
  const [loading, setLoading] = useState(true);
  const [gatewayStatus, setGatewayStatus] = useState<GatewayStatus | null>(null);
  const [channels, setChannels] = useState<ChannelItem[]>([]);
  const [tokens, setTokens] = useState<TokenItem[]>([]);
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());
  const [deletingTokenIds, setDeletingTokenIds] = useState<Set<number>>(new Set());
  const [deletingChannelIds, setDeletingChannelIds] = useState<Set<number>>(new Set());
  /* 确认弹窗状态 */
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void;
  }>({ open: false, title: '', description: '', onConfirm: () => {} });

  /* ── 数据拉取 ── */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [statusResp, channelsResp, tokensResp] = await Promise.allSettled([
        api.newApiStatus(),
        api.newApiChannels(),
        api.newApiTokens(),
      ]);

      // 解析网关状态
      if (statusResp.status === 'fulfilled') {
        const data = await parseResponse<GatewayStatus>(statusResp.value);
        setGatewayStatus(data);
      }

      // 解析渠道列表（兼容数组 / { data: [] } / { channels: [] }）
      if (channelsResp.status === 'fulfilled') {
        const raw = await parseResponse<any>(channelsResp.value);
        const list: ChannelItem[] = Array.isArray(raw) ? raw
          : Array.isArray(raw?.data) ? raw.data
          : Array.isArray(raw?.channels) ? raw.channels
          : [];
        setChannels(list);
      }

      // 解析令牌列表（兼容数组 / { data: [] } / { tokens: [] }）
      if (tokensResp.status === 'fulfilled') {
        const raw = await parseResponse<any>(tokensResp.value);
        const list: TokenItem[] = Array.isArray(raw) ? raw
          : Array.isArray(raw?.data) ? raw.data
          : Array.isArray(raw?.tokens) ? raw.tokens
          : [];
        setTokens(list);
      }
    } catch (err) {
      console.error('[APIGateway] 数据加载失败:', err);
      if (!silent) toast.error('网关数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(() => fetchData(true), 30_000);
    return () => clearInterval(timer);
  }, [fetchData]);

  /* ── 渠道启用/禁用切换 ── */
  const handleToggleChannel = useCallback(async (channelId: number) => {
    setTogglingIds((prev) => new Set(prev).add(channelId));
    try {
      await parseResponse(await api.newApiToggleChannel(channelId));
      toast.success('渠道状态已切换');
      // 局部更新：翻转 status
      setChannels((prev) =>
        prev.map((ch) =>
          ch.id === channelId
            ? { ...ch, status: ch.status === 1 ? 2 : 1 }
            : ch,
        ),
      );
    } catch (err) {
      console.error('[APIGateway] 切换渠道失败:', err);
      toast.error('切换渠道状态失败');
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(channelId);
        return next;
      });
    }
  }, []);

  /* ── 删除渠道 ── */
  const handleDeleteChannel = useCallback(async (channelId: number, name?: string) => {
    const doDelete = async () => {
      setDeletingChannelIds((prev) => new Set(prev).add(channelId));
      try {
        await parseResponse(await api.newApiDeleteChannel(channelId));
        toast.success(`渠道「${name || channelId}」已删除`);
        setChannels((prev) => prev.filter((ch) => ch.id !== channelId));
      } catch (err) {
        console.error('[APIGateway] 删除渠道失败:', err);
        toast.error('删除渠道失败');
      } finally {
        setDeletingChannelIds((prev) => {
          const next = new Set(prev);
          next.delete(channelId);
          return next;
        });
      }
    };
    setConfirmDialog({
      open: true,
      title: '删除渠道',
      description: `确定要删除渠道「${name || channelId}」？删除后不可恢复。`,
      onConfirm: doDelete,
    });
  }, []);

  /* ── 删除令牌 ── */
  const handleDeleteToken = useCallback(async (tokenId: number, name?: string) => {
    const doDelete = async () => {
      setDeletingTokenIds((prev) => new Set(prev).add(tokenId));
      try {
        await parseResponse(await api.newApiDeleteToken(tokenId));
        toast.success(`令牌「${name || tokenId}」已删除`);
        setTokens((prev) => prev.filter((t) => t.id !== tokenId));
      } catch (err) {
        console.error('[APIGateway] 删除令牌失败:', err);
        toast.error('删除令牌失败');
      } finally {
        setDeletingTokenIds((prev) => {
          const next = new Set(prev);
          next.delete(tokenId);
          return next;
        });
      }
    };
    setConfirmDialog({
      open: true,
      title: '删除令牌',
      description: `确定要删除令牌「${name || tokenId}」？删除后不可恢复。`,
      onConfirm: doDelete,
    });
  }, []);

  /* ── 派生数据 ── */
  const isOnline = gatewayStatus?.running || gatewayStatus?.online || gatewayStatus?.status === 'ok';
  const enabledChannels = channels.filter(isChannelEnabled).length;

  /* ── 概览统计 ── */
  const overviewStats = [
    { label: '渠道总数', value: String(channels.length), color: 'var(--accent-cyan)' },
    { label: '已启用', value: String(enabledChannels), color: 'var(--accent-green)' },
    { label: '令牌数', value: String(tokens.length), color: 'var(--accent-amber)' },
    { label: '网关状态', value: isOnline ? '在线' : '离线', color: isOnline ? 'var(--accent-green)' : 'var(--accent-red)' },
  ];

  /* ── 加载态 ── */
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin" size={32} style={{ color: 'var(--accent-cyan)' }} />
        <span className="ml-3 font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
          正在加载网关数据…
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
        {/* ====== 网关概览 + 渠道列表 (col-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题行 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.12)' }}
              >
                <Network size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div className="flex-1">
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  GATEWAY CONTROLLER
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  API 网关 // UNIFIED PROXY
                </p>
              </div>
              {/* 网关在线/离线指示 + 刷新按钮 */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: 'var(--bg-tertiary)' }}>
                  {isOnline
                    ? <Wifi size={12} style={{ color: 'var(--accent-green)' }} />
                    : <WifiOff size={12} style={{ color: 'var(--accent-red)' }} />}
                  <span className="font-mono text-[10px]" style={{ color: isOnline ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {isOnline ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
                <button
                  onClick={() => fetchData(true)}
                  className="p-1.5 rounded-lg transition-colors hover:opacity-80"
                  style={{ background: 'var(--bg-tertiary)' }}
                  title="刷新数据"
                >
                  <RefreshCw size={12} style={{ color: 'var(--text-secondary)' }} />
                </button>
              </div>
            </div>

            {/* 统计 4 格 */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              {overviewStats.map((s) => (
                <div key={s.label}>
                  <span className="text-label">{s.label}</span>
                  <div className="text-metric mt-1" style={{ color: s.color, fontSize: '20px' }}>
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* 渠道列表 */}
            <span className="text-label mb-2" style={{ color: 'var(--text-tertiary)' }}>
              CHANNEL LIST · 渠道列表
            </span>

            {/* 表头 */}
            <div
              className="grid gap-2 px-4 py-2 rounded-lg mb-1"
              style={{ gridTemplateColumns: '2fr 1fr 70px 70px 60px 70px', background: 'var(--bg-tertiary)' }}
            >
              <span className="text-label" style={{ fontSize: '10px' }}>渠道名称</span>
              <span className="text-label" style={{ fontSize: '10px' }}>类型</span>
              <span className="text-label text-center" style={{ fontSize: '10px' }}>状态</span>
              <span className="text-label text-right" style={{ fontSize: '10px' }}>响应时间</span>
              <span className="text-label text-center" style={{ fontSize: '10px' }}>开关</span>
              <span className="text-label text-center" style={{ fontSize: '10px' }}>操作</span>
            </div>

            {/* 渠道行 */}
            <div className="flex-1 space-y-1 overflow-y-auto">
              {channels.length === 0 ? (
                <div className="text-center py-8 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  暂无渠道数据
                </div>
              ) : (
                channels.map((ch) => {
                  const enabled = isChannelEnabled(ch);
                  const toggling = togglingIds.has(ch.id);
                  const deleting = deletingChannelIds.has(ch.id);
                  return (
                    <div
                      key={ch.id}
                      className={clsx(
                        'grid gap-2 items-center py-2.5 px-4 rounded-lg transition-opacity',
                        !enabled && 'opacity-50',
                      )}
                      style={{ gridTemplateColumns: '2fr 1fr 70px 70px 60px 70px', background: 'var(--bg-secondary)' }}
                    >
                      {/* 渠道名称 */}
                      <span className="font-mono text-xs truncate" style={{ color: 'var(--text-primary)' }}>
                        {ch.name || `渠道 #${ch.id}`}
                      </span>
                      {/* 类型 */}
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                        {CHANNEL_TYPE_LABELS[ch.type ?? 0] || `Type ${ch.type}`}
                      </span>
                      {/* 状态指示 */}
                      <div className="flex justify-center items-center gap-1.5">
                        <span
                          className={clsx('w-2 h-2 rounded-full', enabled && 'animate-pulse')}
                          style={{ background: enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                        />
                        <span className="font-mono text-[9px]" style={{ color: enabled ? 'var(--accent-green)' : 'var(--text-disabled)' }}>
                          {enabled ? '启用' : '禁用'}
                        </span>
                      </div>
                      {/* 响应时间 */}
                      <span className="font-mono text-[10px] text-right" style={{ color: latencyColor(ch.response_time) }}>
                        {ch.response_time ? `${ch.response_time}ms` : '—'}
                      </span>
                      {/* 开关按钮 */}
                      <div className="flex justify-center">
                        <button
                          onClick={() => handleToggleChannel(ch.id)}
                          disabled={toggling}
                          className="transition-colors hover:opacity-80 disabled:opacity-50"
                          title={enabled ? '点击禁用' : '点击启用'}
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
                      {/* 删除按钮 */}
                      <div className="flex justify-center">
                        <button
                          onClick={() => handleDeleteChannel(ch.id, ch.name)}
                          disabled={deleting}
                          className="p-1 rounded transition-colors hover:opacity-80 disabled:opacity-50"
                          style={{ color: 'var(--accent-red)' }}
                          title="删除渠道"
                        >
                          {deleting ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Trash2 size={12} />
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

        {/* ====== 令牌管理 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              TOKEN MANAGEMENT
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              令牌管理
            </h3>

            <div className="flex-1 space-y-3 overflow-y-auto">
              {tokens.length === 0 ? (
                <div className="text-center py-8 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  暂无令牌
                </div>
              ) : (
                tokens.map((tk) => {
                  const isActive = tk.status === 1;
                  const deleting = deletingTokenIds.has(tk.id);
                  return (
                    <div
                      key={tk.id}
                      className="py-3 px-4 rounded-lg"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-mono text-xs font-bold truncate" style={{ color: 'var(--text-primary)' }}>
                          {tk.name || `令牌 #${tk.id}`}
                        </span>
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ background: isActive ? 'var(--accent-green)' : 'var(--text-disabled)' }}
                          />
                          {/* 删除按钮 */}
                          <button
                            onClick={() => handleDeleteToken(tk.id, tk.name)}
                            disabled={deleting}
                            className="p-0.5 rounded transition-colors hover:opacity-80 disabled:opacity-50"
                            style={{ color: 'var(--accent-red)' }}
                            title="删除令牌"
                          >
                            {deleting ? (
                              <Loader2 size={10} className="animate-spin" />
                            ) : (
                              <Trash2 size={10} />
                            )}
                          </button>
                        </div>
                      </div>
                      {/* 令牌 Key（脱敏） */}
                      {tk.key && (
                        <div className="font-mono text-[10px] py-1.5 px-2 rounded" style={{ background: 'var(--bg-base)', color: 'var(--text-disabled)' }}>
                          <Key size={10} className="inline mr-1" style={{ color: 'var(--accent-amber)' }} />
                          {tk.key.length > 12 ? `${tk.key.slice(0, 6)}****${tk.key.slice(-4)}` : tk.key}
                        </div>
                      )}
                      <div className="flex justify-between mt-2">
                        <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                          创建: {formatTime(tk.created_time)}
                        </span>
                        <span className="font-mono text-[9px]" style={{ color: 'var(--text-disabled)' }}>
                          最近: {formatTime(tk.accessed_time)}
                        </span>
                      </div>
                      {/* 配额信息 */}
                      {tk.unlimited_quota ? (
                        <span className="font-mono text-[9px] mt-1 block" style={{ color: 'var(--accent-cyan)' }}>
                          配额: 无限制
                        </span>
                      ) : tk.remain_quota != null ? (
                        <span className="font-mono text-[9px] mt-1 block" style={{ color: 'var(--text-disabled)' }}>
                          剩余: {tk.remain_quota.toLocaleString()} · 已用: {(tk.used_quota ?? 0).toLocaleString()}
                        </span>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== 渠道模型分布 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-green)' }}>
              CHANNEL DISTRIBUTION
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              渠道类型分布
            </h3>

            <div className="flex-1 space-y-3">
              {(() => {
                // 按渠道类型统计数量
                const typeCount: Record<string, number> = {};
                channels.forEach((ch) => {
                  const label = CHANNEL_TYPE_LABELS[ch.type ?? 0] || `Type ${ch.type}`;
                  typeCount[label] = (typeCount[label] || 0) + 1;
                });
                const sorted = Object.entries(typeCount).sort((a, b) => b[1] - a[1]);
                const total = channels.length || 1;
                const colors = ['var(--accent-cyan)', 'var(--accent-green)', 'var(--accent-amber)', 'var(--accent-red)', 'var(--accent-purple)'];

                if (sorted.length === 0) {
                  return (
                    <div className="text-center py-4 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                      暂无数据
                    </div>
                  );
                }

                return sorted.map(([label, count], idx) => {
                  const pct = Math.round((count / total) * 100);
                  const color = colors[idx % colors.length];
                  return (
                    <div key={label}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-xs font-bold" style={{ color }}>
                          {label}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                          {count}个 · {pct}%
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full" style={{ background: 'var(--bg-tertiary)' }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${pct}%`, background: color }}
                        />
                      </div>
                    </div>
                  );
                });
              })()}
            </div>

            {/* 总渠道数 */}
            <div className="mt-4 pt-4 flex items-center gap-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <Activity size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                {channels.length} 个渠道
              </span>
              <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--accent-green)' }}>
                {enabledChannels} 启用
              </span>
            </div>
          </div>
        </motion.div>

        {/* ====== 渠道模型详情 (col-8) ====== */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-4">
              <Terminal size={14} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>MODELS BY CHANNEL</span>
            </div>

            <div className="flex-1 space-y-2 overflow-y-auto max-h-[260px]">
              {channels.length === 0 ? (
                <div className="text-center py-4 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  暂无渠道
                </div>
              ) : (
                channels.map((ch) => {
                  const models = ch.models ? ch.models.split(',').map((m) => m.trim()).filter(Boolean) : [];
                  const enabled = isChannelEnabled(ch);
                  return (
                    <div
                      key={ch.id}
                      className={clsx(
                        'flex items-start justify-between py-2.5 px-4 rounded-lg transition-opacity',
                        !enabled && 'opacity-40',
                      )}
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      <div className="flex-1 min-w-0">
                        <span className="font-display text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                          {ch.name || `渠道 #${ch.id}`}
                        </span>
                        {models.length > 0 ? (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {models.slice(0, 6).map((m) => (
                              <span
                                key={m}
                                className="px-1.5 py-0.5 rounded font-mono text-[9px]"
                                style={{ background: 'rgba(6,182,212,0.1)', color: 'var(--accent-cyan)' }}
                              >
                                {m}
                              </span>
                            ))}
                            {models.length > 6 && (
                              <span className="font-mono text-[9px] px-1.5 py-0.5" style={{ color: 'var(--text-disabled)' }}>
                                +{models.length - 6}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="font-mono text-[9px] mt-1 block" style={{ color: 'var(--text-disabled)' }}>
                            未配置模型
                          </span>
                        )}
                      </div>
                      <span className="font-mono text-[10px] shrink-0 ml-3" style={{ color: latencyColor(ch.response_time) }}>
                        {ch.response_time ? `${ch.response_time}ms` : ''}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>

        {/* ====== 网关信息摘要 (col-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
              GATEWAY INFO
            </span>
            <h3 className="font-display text-lg font-bold mt-1 mb-4" style={{ color: 'var(--text-primary)' }}>
              网关信息
            </h3>

            <div className="flex-1 space-y-3">
              {/* 各种网关字段 — 动态渲染已有数据 */}
              {gatewayStatus ? (
                Object.entries(gatewayStatus)
                  .filter(([k]) => !['running', 'online'].includes(k))
                  .slice(0, 8)
                  .map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between py-1.5">
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                        {key}
                      </span>
                      <span className="font-mono text-[11px] font-semibold truncate max-w-[60%] text-right" style={{ color: 'var(--text-primary)' }}>
                        {typeof val === 'object' ? JSON.stringify(val) : String(val ?? '—')}
                      </span>
                    </div>
                  ))
              ) : (
                <div className="text-center py-4 font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  网关未连接
                </div>
              )}
            </div>

            <div className="mt-3 pt-3 font-mono text-[10px]" style={{ borderTop: '1px solid var(--glass-border)', color: 'var(--text-disabled)' }}>
              自动刷新: 每 30 秒
            </div>
          </div>
        </motion.div>
      </motion.div>

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        open={confirmDialog.open}
        onClose={() => setConfirmDialog((prev) => ({ ...prev, open: false }))}
        onConfirm={() => {
          confirmDialog.onConfirm();
          setConfirmDialog((prev) => ({ ...prev, open: false }));
        }}
        title={confirmDialog.title}
        description={confirmDialog.description}
        confirmText="删除"
        cancelText="取消"
        destructive
      />
    </div>
  );
}

/**
 * Store — 统一插件商店 (App Store 风格)
 * 五大 Tab：技能工具 / 平台渠道 / Bot 技能 / MCP 插件 / 进化发现
 * 数据来源：/api/v1/store/catalog + MCP IPC + Evolution API
 * Sonic Abyss Bento Grid 风格
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from '@/lib/notify';
import {
  Search, Package, Puzzle, Plug, Bot, Dna,
  Loader2, RefreshCw, ChevronRight,
  CheckCircle2, XCircle, Clock, ThumbsUp,
  Power, Star,
} from 'lucide-react';
import { clawbotFetchJson, clawbotFetch } from '../../lib/tauri-core';
import { api } from '../../lib/api';
import type { EvolutionStatsRaw } from '../../lib/tauri-core';
import { useLanguage } from '../../i18n';

/* ============================================================
   类型
   ============================================================ */

interface StoreItem {
  id: string;
  name: string;
  description: string;
  emoji?: string;
  type: 'skill' | 'extension' | 'bot-skill' | 'mcp' | 'evolution';
  category: string;
  status: string;
  version?: string;
  homepage?: string;
  stars?: number;
  score?: number;
  risk?: string;
  url?: string;
  module?: string;
  approach?: string;
}

type TabKey = 'skills' | 'extensions' | 'bot-skills' | 'mcp' | 'evolution';

/* ============================================================
   Tab 定义
   ============================================================ */

const TABS: { key: TabKey; labelKey: string; Icon: typeof Package; color: string }[] = [
  { key: 'skills', labelKey: 'store.tabSkills', Icon: Puzzle, color: 'var(--accent-cyan)' },
  { key: 'extensions', labelKey: 'store.tabExtensions', Icon: Plug, color: 'var(--accent-purple)' },
  { key: 'bot-skills', labelKey: 'store.tabBotSkills', Icon: Bot, color: 'var(--accent-amber)' },
  { key: 'mcp', labelKey: 'store.tabMcp', Icon: Power, color: 'var(--accent-green)' },
  { key: 'evolution', labelKey: 'store.tabEvolution', Icon: Dna, color: 'var(--accent-red)' },
];

/* ============================================================
   动画
   ============================================================ */

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.04 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ============================================================
   Evolution 状态映射
   ============================================================ */

const EVO_STATUS_MAP: Record<string, { labelKey: string; color: string; Icon: typeof CheckCircle2 }> = {
  approved: { labelKey: 'store.statusApproved', color: 'var(--accent-green)', Icon: CheckCircle2 },
  rejected: { labelKey: 'store.statusRejected', color: 'var(--accent-red)', Icon: XCircle },
  pending: { labelKey: 'store.statusPending', color: 'var(--accent-amber)', Icon: Clock },
};

/* ============================================================
   主组件
   ============================================================ */

export function Store() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabKey>('skills');
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  /* 商店目录数据 */
  const [skills, setSkills] = useState<StoreItem[]>([]);
  const [extensions, setExtensions] = useState<StoreItem[]>([]);
  const [botSkills, setBotSkills] = useState<StoreItem[]>([]);

  /* MCP 插件数据 */
  const [mcpPlugins, setMcpPlugins] = useState<StoreItem[]>([]);
  const [mcpToggling, setMcpToggling] = useState<string | null>(null);

  /* Evolution 数据 */
  const [evoItems, setEvoItems] = useState<StoreItem[]>([]);
  const [, setEvoStats] = useState<EvolutionStatsRaw | null>(null);
  const [evoApproving, setEvoApproving] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── 拉取商店目录 ── */
  const fetchCatalog = useCallback(async () => {
    try {
      const data = await clawbotFetchJson<any>('/api/v1/store/catalog');
      if (data?.skills) setSkills(data.skills);
      if (data?.extensions) setExtensions(data.extensions);
      if (data?.bot_skills) setBotSkills(data.bot_skills);
    } catch (e) {
      console.warn('[Store] 商店目录拉取失败:', e);
    }
  }, []);

  /* ── 拉取 MCP 插件 ── */
  const fetchMcp = useCallback(async () => {
    try {
      let plugins: any[] = [];
      try {
        const skillsData = await api.getSkillsStatus();
        const sd = skillsData as any;
        plugins = Array.isArray(sd) ? sd : sd?.skills ?? sd?.plugins ?? sd?.tools ?? [];
      } catch {
        /* Tauri IPC 失败，尝试 HTTP */
        try {
          const httpData = await clawbotFetchJson<any>('/api/v1/cli/tools');
          plugins = Array.isArray(httpData) ? httpData : httpData?.tools ?? httpData?.skills ?? [];
        } catch { /* 双失败 */ }
      }
      setMcpPlugins(plugins.map((p: any) => ({
        id: p.id ?? p.name ?? '',
        name: p.name ?? p.id ?? '',
        description: p.description ?? '',
        emoji: '⚡',
        type: 'mcp' as const,
        category: p.protocol ?? 'stdio',
        status: p.status === 'running' ? 'running' : 'stopped',
        version: p.version ?? '',
      })));
    } catch (e) {
      console.warn('[Store] MCP 插件拉取失败:', e);
    }
  }, []);

  /* ── 拉取 Evolution ── */
  const fetchEvolution = useCallback(async () => {
    try {
      const [proposalsRes, statsRes] = await Promise.allSettled([
        clawbotFetchJson<any>('/api/v1/evolution/proposals'),
        clawbotFetchJson<EvolutionStatsRaw>('/api/v1/evolution/stats'),
      ]);
      if (proposalsRes.status === 'fulfilled') {
        const raw = proposalsRes.value;
        const list: any[] = Array.isArray(raw) ? raw : raw?.proposals ?? raw?.data ?? [];
        setEvoItems(list.map((r: any) => ({
          id: r.id || r.proposal_id || '',
          name: r.repo_name || r.name || r.repo || '',
          description: r.integration_approach || r.approach || '',
          emoji: '🧬',
          type: 'evolution' as const,
          category: r.target_module || r.module || '通用',
          status: r.status === 'proposed' ? 'pending' : (r.status || 'pending'),
          stars: r.stars ?? r.stargazers_count ?? 0,
          score: r.value_score ?? r.score ?? 0,
          risk: r.risk_level || r.risk || '—',
          url: r.repo_url || r.url || '',
          module: r.target_module || r.module || '',
          approach: r.integration_approach || r.approach || '',
        })));
      }
      if (statsRes.status === 'fulfilled') {
        setEvoStats(statsRes.value);
      }
    } catch (e) {
      console.warn('[Store] Evolution 拉取失败:', e);
    }
  }, []);

  /* ── 全量刷新 ── */
  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.allSettled([fetchCatalog(), fetchMcp(), fetchEvolution()]);
    setLoading(false);
  }, [fetchCatalog, fetchMcp, fetchEvolution]);

  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(fetchAll, 60_000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchAll]);

  /* ── MCP 插件启停 ── */
  const handleMcpToggle = useCallback(async (pluginId: string, currentStatus: string) => {
    setMcpToggling(pluginId);
    try {
      if (currentStatus === 'running') {
        await api.stopMcpPlugin(pluginId);
        toast.success(`${pluginId} ${t('plugins.stopped')}`, { channel: 'log' });
      } else {
        await api.startMcpPlugin(pluginId);
        toast.success(`${pluginId} ${t('plugins.started')}`, { channel: 'log' });
      }
      await new Promise(r => setTimeout(r, 800));
      await fetchMcp();
    } catch (e: any) {
      toast.error(`${t('plugins.operationFailed')}: ${e?.message ?? ''}`, { channel: 'notification' });
    } finally {
      setMcpToggling(null);
    }
  }, [fetchMcp, t]);

  /* ── Evolution 审批 ── */
  const handleEvoApprove = useCallback(async (id: string, action: 'approved' | 'rejected') => {
    setEvoApproving(id);
    try {
      const resp = await clawbotFetch(`/api/v1/evolution/proposals/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: action }),
      });
      if (!resp.ok) throw new Error(await resp.text().catch(() => `HTTP ${resp.status}`));
      toast.success(action === 'approved' ? t('store.approveSuccess') : t('store.rejectSuccess'), { channel: 'log' });
      await fetchEvolution();
    } catch (e: any) {
      toast.error(`${t('store.approveFailed')}: ${e?.message ?? ''}`, { channel: 'notification' });
    } finally {
      setEvoApproving(null);
    }
  }, [fetchEvolution, t]);

  /* ── 当前 Tab 数据 ── */
  const currentItems = useMemo(() => {
    const map: Record<TabKey, StoreItem[]> = {
      'skills': skills,
      'extensions': extensions,
      'bot-skills': botSkills,
      'mcp': mcpPlugins,
      'evolution': evoItems,
    };
    let items = map[activeTab] || [];

    /* 搜索 */
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(item =>
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
      );
    }

    /* 分类筛选 */
    if (categoryFilter !== 'all') {
      items = items.filter(item => item.category === categoryFilter);
    }

    return items;
  }, [activeTab, skills, extensions, botSkills, mcpPlugins, evoItems, search, categoryFilter]);

  /* ── 当前 Tab 的分类列表 ── */
  const categories = useMemo(() => {
    const map: Record<TabKey, StoreItem[]> = {
      'skills': skills,
      'extensions': extensions,
      'bot-skills': botSkills,
      'mcp': mcpPlugins,
      'evolution': evoItems,
    };
    const items = map[activeTab] || [];
    const cats: Record<string, number> = {};
    items.forEach(item => {
      const cat = item.category || '其他';
      cats[cat] = (cats[cat] || 0) + 1;
    });
    return cats;
  }, [activeTab, skills, extensions, botSkills, mcpPlugins, evoItems]);

  /* ── 总计数 ── */
  const tabCounts: Record<TabKey, number> = {
    'skills': skills.length,
    'extensions': extensions.length,
    'bot-skills': botSkills.length,
    'mcp': mcpPlugins.length,
    'evolution': evoItems.length,
  };

  /* ── 切换 Tab 时重置分类筛选 ── */
  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab);
    setCategoryFilter('all');
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin" size={28} style={{ color: 'var(--accent-cyan)' }} />
        <span className="ml-3 font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{t('store.loading')}</span>
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
        {/* ====== 搜索栏 ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card px-5 py-3 flex items-center gap-3">
            <Search size={16} style={{ color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('store.searchPlaceholder')}
              className="flex-1 bg-transparent text-sm font-mono outline-none"
              style={{ color: 'var(--text-primary)' }}
            />
            {search && (
              <button onClick={() => setSearch('')} className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                {t('store.clear')}
              </button>
            )}
            <button
              onClick={() => { fetchAll(); }}
              className="transition-colors"
              style={{ color: 'var(--text-tertiary)' }}
              title={t('store.manualRefresh')}
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </motion.div>

        {/* ====== Tab 栏 ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {TABS.map(tab => {
              const isActive = activeTab === tab.key;
              const count = tabCounts[tab.key];
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className={clsx(
                    'flex items-center gap-2 px-4 py-2.5 rounded-xl font-mono text-xs font-medium transition-all whitespace-nowrap',
                    isActive
                      ? 'border'
                      : 'border border-transparent hover:border-[var(--glass-border)]'
                  )}
                  style={{
                    background: isActive ? `${tab.color}10` : 'transparent',
                    borderColor: isActive ? `${tab.color}40` : undefined,
                    color: isActive ? tab.color : 'var(--text-secondary)',
                  }}
                >
                  <tab.Icon size={14} />
                  {t(tab.labelKey)}
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-full"
                    style={{
                      background: isActive ? `${tab.color}20` : 'rgba(255,255,255,0.05)',
                      color: isActive ? tab.color : 'var(--text-disabled)',
                    }}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </motion.div>

        {/* ====== 分类侧栏 (span-3) + 内容主区域 (span-9) ====== */}

        {/* 分类侧栏 */}
        <motion.div className="col-span-12 lg:col-span-3" variants={cardVariants}>
          <div className="abyss-card p-4">
            <span className="text-label mb-3 block" style={{ color: 'var(--text-tertiary)' }}>
              {t('store.categoryFilter')}
            </span>
            <div className="space-y-1">
              <button
                onClick={() => setCategoryFilter('all')}
                className={clsx(
                  'w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-mono transition-all',
                  categoryFilter === 'all' ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                )}
                style={{
                  background: categoryFilter === 'all' ? 'rgba(0,212,255,0.06)' : 'transparent',
                  border: categoryFilter === 'all' ? '1px solid rgba(0,212,255,0.15)' : '1px solid transparent',
                }}
              >
                <span>{t('store.statusAll')}</span>
                <span className="text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                  {Object.values(categories).reduce((a, b) => a + b, 0)}
                </span>
              </button>
              {Object.entries(categories).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  className={clsx(
                    'w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-mono transition-all',
                    categoryFilter === cat ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  )}
                  style={{
                    background: categoryFilter === cat ? 'rgba(0,212,255,0.06)' : 'transparent',
                    border: categoryFilter === cat ? '1px solid rgba(0,212,255,0.15)' : '1px solid transparent',
                  }}
                >
                  <span className="truncate">{cat}</span>
                  <span className="text-[10px] flex-shrink-0" style={{ color: 'var(--text-disabled)' }}>{count}</span>
                </button>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 内容主区域 */}
        <motion.div className="col-span-12 lg:col-span-9" variants={cardVariants}>
          <div className="abyss-card p-6">
            {/* 标题 */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Package size={16} style={{ color: TABS.find(t => t.key === activeTab)?.color }} />
                <span className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {t(TABS.find(t => t.key === activeTab)?.labelKey || '')}
                </span>
              </div>
              <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>
                {currentItems.length} {t('store.resultsCount')}
              </span>
            </div>

            {/* 卡片网格 */}
            {currentItems.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <span className="font-mono text-sm" style={{ color: 'var(--text-disabled)' }}>
                  {t('store.noPlugins')}
                </span>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                {currentItems.map((item, i) => (
                  <motion.div
                    key={`${item.type}-${item.id}-${i}`}
                    variants={cardVariants}
                    className="rounded-2xl p-4 transition-all hover:border-[var(--accent-cyan)]/30"
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid var(--glass-border)',
                    }}
                  >
                    {/* 头部：emoji + 名称 */}
                    <div className="flex items-start gap-3 mb-2">
                      <span className="text-2xl leading-none flex-shrink-0">{item.emoji || '📦'}</span>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                          {item.name}
                        </h4>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                          {item.category}
                          {item.version && ` · v${item.version}`}
                        </span>
                      </div>
                    </div>

                    {/* 描述 */}
                    {item.description && (
                      <p className="font-mono text-[11px] leading-relaxed mb-3 line-clamp-2"
                        style={{ color: 'var(--text-secondary)' }}>
                        {item.description}
                      </p>
                    )}

                    {/* Evolution 特有字段 */}
                    {item.type === 'evolution' && (
                      <div className="flex items-center gap-3 mb-2">
                        {item.stars != null && (
                          <span className="flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                            <Star size={9} style={{ color: 'var(--accent-amber)' }} />
                            {item.stars.toLocaleString()}
                          </span>
                        )}
                        {item.score != null && (
                          <span className="text-[10px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                            {t('store.score')} {item.score}
                          </span>
                        )}
                      </div>
                    )}

                    {/* 底部：状态 + 操作按钮 */}
                    <div className="flex items-center justify-between mt-auto">
                      {/* 状态标签 */}
                      <StoreItemStatus item={item} t={t} />

                      {/* 操作按钮 */}
                      <StoreItemAction
                        item={item}
                        t={t}
                        mcpToggling={mcpToggling}
                        evoApproving={evoApproving}
                        onMcpToggle={handleMcpToggle}
                        onEvoApprove={handleEvoApprove}
                      />
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* ====== 统计栏 ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {t('store.totalInstalled')}: <b style={{ color: 'var(--accent-green)' }}>{skills.length + extensions.length + botSkills.length}</b>
              </span>
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                MCP: <b style={{ color: 'var(--accent-cyan)' }}>{mcpPlugins.filter(p => p.status === 'running').length}/{mcpPlugins.length}</b>
              </span>
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {t('store.tabEvolution')}: <b style={{ color: 'var(--accent-amber)' }}>{evoItems.filter(e => e.status === 'pending').length}</b> {t('store.pending')}
              </span>
            </div>
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
              {t('common.autoRefresh')}
            </span>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ============================================================
   子组件
   ============================================================ */

/** 商店条目状态标签 */
function StoreItemStatus({ item, t }: { item: StoreItem; t: (k: string) => string }) {
  if (item.type === 'evolution') {
    const si = EVO_STATUS_MAP[item.status] || EVO_STATUS_MAP.pending;
    return (
      <span className="flex items-center gap-1 text-[10px] font-mono" style={{ color: si.color }}>
        <si.Icon size={10} />
        {t(si.labelKey)}
      </span>
    );
  }

  if (item.type === 'mcp') {
    const running = item.status === 'running';
    return (
      <span className="flex items-center gap-1.5 text-[10px] font-mono font-bold" style={{
        color: running ? 'var(--accent-green)' : 'var(--text-disabled)',
      }}>
        <span className="w-2 h-2 rounded-full" style={{ background: running ? 'var(--accent-green)' : 'var(--text-disabled)' }} />
        {running ? t('plugins.running') : t('plugins.stopped')}
      </span>
    );
  }

  /* skill / extension / bot-skill → 已安装 */
  return (
    <span className="flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--accent-green)' }}>
      <CheckCircle2 size={10} />
      {t('store.installed')}
    </span>
  );
}

/** 商店条目操作按钮 */
function StoreItemAction({
  item, t, mcpToggling, evoApproving, onMcpToggle, onEvoApprove,
}: {
  item: StoreItem;
  t: (k: string) => string;
  mcpToggling: string | null;
  evoApproving: string | null;
  onMcpToggle: (id: string, status: string) => void;
  onEvoApprove: (id: string, action: 'approved' | 'rejected') => void;
}) {
  if (item.type === 'mcp') {
    const isLoading = mcpToggling === item.id;
    const running = item.status === 'running';
    return (
      <button
        disabled={isLoading}
        onClick={() => onMcpToggle(item.id, item.status)}
        className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold transition-all"
        style={{
          background: running ? 'rgba(255,0,0,0.08)' : 'rgba(0,255,170,0.08)',
          border: `1px solid ${running ? 'rgba(255,0,0,0.25)' : 'rgba(0,255,170,0.25)'}`,
          color: running ? 'var(--accent-red)' : 'var(--accent-green)',
          opacity: isLoading ? 0.5 : 1,
        }}
      >
        {isLoading ? <Loader2 size={10} className="animate-spin" /> : <Power size={10} />}
        {running ? t('bots.stop') : t('bots.start')}
      </button>
    );
  }

  if (item.type === 'evolution' && item.status === 'pending') {
    const isLoading = evoApproving === item.id;
    return (
      <div className="flex items-center gap-1.5">
        <button
          disabled={isLoading}
          onClick={() => onEvoApprove(item.id, 'approved')}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-mono font-bold transition-all"
          style={{
            background: 'rgba(0,255,170,0.08)',
            border: '1px solid rgba(0,255,170,0.25)',
            color: 'var(--accent-green)',
            opacity: isLoading ? 0.5 : 1,
          }}
        >
          {isLoading ? <Loader2 size={10} className="animate-spin" /> : <ThumbsUp size={10} />}
          {t('store.approve')}
        </button>
        <button
          disabled={isLoading}
          onClick={() => onEvoApprove(item.id, 'rejected')}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-mono font-bold transition-all"
          style={{
            background: 'rgba(255,0,0,0.08)',
            border: '1px solid rgba(255,0,0,0.25)',
            color: 'var(--accent-red)',
            opacity: isLoading ? 0.5 : 1,
          }}
        >
          <XCircle size={10} />
          {t('store.reject')}
        </button>
      </div>
    );
  }

  if (item.type === 'evolution' && item.url) {
    return (
      <a href={item.url} target="_blank" rel="noreferrer"
        className="flex items-center gap-1 text-[10px] font-mono transition-colors"
        style={{ color: 'var(--text-tertiary)' }}
      >
        {t('store.view')} <ChevronRight size={10} />
      </a>
    );
  }

  /* skill / extension / bot-skill → 暂无卸载操作 */
  return (
    <span className="text-[10px] font-mono" style={{ color: 'var(--text-disabled)' }}>
      {item.homepage ? (
        <a href={item.homepage} target="_blank" rel="noreferrer" className="hover:text-[var(--accent-cyan)] transition-colors">
          {t('store.view')} <ChevronRight size={10} className="inline" />
        </a>
      ) : null}
    </span>
  );
}

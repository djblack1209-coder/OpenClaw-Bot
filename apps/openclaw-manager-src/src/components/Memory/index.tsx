import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Database, Filter, Loader2, Search, BrainCircuit, RefreshCw, Trash2, Edit } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { api, isTauri, clawbotFetch, type MemorySearchResponse, type MemoryEntryRaw } from '@/lib/tauri';
import { createLogger } from '@/lib/logger';
import { toast } from 'sonner';

import clsx from 'clsx';

const memoryLogger = createLogger('Memory');

interface MemoryEntry {
  key: string;
  value: string;
  source_bot: string;
  importance: number;
  updated_at: number;
}

// API 返回的记忆条目原始格式
export function Memory() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  // 分类筛选：全部 | 用户画像 | 事实 | 高优先级
  const [filter, setFilter] = useState<'all' | 'profile' | 'fact' | 'important'>('all');
  const [searchLoading, setSearchLoading] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  // 删除/编辑操作中的条目 key
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  // 记忆引擎在线状态
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  // 记忆统计数据
  const [memoryStats, setMemoryStats] = useState<{ total: number; extraction_rounds: number; vector_dim: number } | null>(null);
  // 删除确认对话框状态
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  // 搜索防抖计时器
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 分页：每次加载的条目上限
  const [limit, setLimit] = useState(50);
  // 分页：是否还有更多条目
  const [hasMore, setHasMore] = useState(true);
  // "加载更多"按钮的加载状态
  const [loadMoreLoading, setLoadMoreLoading] = useState(false);

  // 执行删除记忆条目（由确认对话框触发）
  const executeDelete = async (key: string) => {
    try {
      setActionLoading(key);
      if (isTauri()) {
        // Tauri 环境：通过 IPC 调用
        await api.clawbotMemoryDelete(key);
      } else {
        // 降级: 直接HTTP调用
        await clawbotFetch('/api/v1/memory/delete', {
          method: 'POST',
          body: JSON.stringify({ key }),
        });
      }
      setEntries(prev => prev.filter(e => e.key !== key));
    } catch (e) {
      memoryLogger.error('删除记忆失败', e);
      toast.error('删除失败，请稍后重试');
    } finally {
      setActionLoading(null);
    }
  };

  // 进入编辑模式
  const handleEdit = (entry: MemoryEntry) => {
    setEditingKey(entry.key);
    setEditValue(entry.value);
  };

  // 保存编辑后的记忆内容
  const handleSaveEdit = async () => {
    if (!editingKey) return;
    // 验证记忆内容不能为空
    if (!editValue.trim()) {
      toast.error('记忆内容不能为空');
      return;
    }
    try {
      setActionLoading(editingKey);
      if (isTauri()) {
        // Tauri 环境：通过 IPC 调用
        await api.clawbotMemoryUpdate(editingKey, editValue);
      } else {
        // 降级: 直接HTTP调用
        await clawbotFetch('/api/v1/memory/update', {
          method: 'POST',
          body: JSON.stringify({ key: editingKey, value: editValue }),
        });
      }
      setEntries(prev => prev.map(e => e.key === editingKey ? { ...e, value: editValue } : e));
      setEditingKey(null);
    } catch (e) {
      memoryLogger.error('更新记忆失败', e);
      toast.error('更新失败，请稍后重试');
    } finally {
      setActionLoading(null);
    }
  };

  const fetchMemories = useCallback(async (fetchLimit?: number) => {
    const currentLimit = fetchLimit ?? limit;
    try {
      setLoading(true);
      let results: MemoryEntryRaw[] = [];

      if (isTauri()) {
        // Tauri 环境：通过 IPC 调用
        const data: MemorySearchResponse = await api.clawbotMemorySearch('', currentLimit);
        results = data?.results || data?.entries || [];
      } else {
        // 降级: 直接HTTP调用
        const resp = await clawbotFetch(`/api/v1/memory/search?q=&limit=${currentLimit}`);
        if (resp.ok) {
          const data = await resp.json();
          results = data.results || data.entries || data || [];
        }
      }

      setEngineOnline(true);
      // 尝试获取记忆统计数据（提取轮次、向量维度等）
      try {
        if (isTauri()) {
          const stats = await api.clawbotMemoryStats();
          if (stats) {
            setMemoryStats({
              total: (stats as Record<string, number>).total_count ?? 0,
              extraction_rounds: (stats as Record<string, number>).extraction_rounds ?? 0,
              vector_dim: (stats as Record<string, number>).vector_dim ?? 0,
            });
          }
        } else {
          // HTTP 降级: 浏览器环境直接调用后端 API
          const resp = await clawbotFetch('/api/v1/memory/stats');
          if (resp.ok) {
            const stats = await resp.json();
            setMemoryStats({
              total: stats.total_count ?? 0,
              extraction_rounds: stats.extraction_rounds ?? 0,
              vector_dim: stats.vector_dim ?? 0,
            });
          }
        }
      } catch {
        // 统计接口不可用不影响核心功能
      }
      if (Array.isArray(results) && results.length > 0) {
        setEntries(results.map((r: MemoryEntryRaw) => ({
          key: r.key || r.id || 'unknown',
          value: typeof r.value === 'string' ? r.value : JSON.stringify(r.value || r.content || ''),
          source_bot: r.source_bot || r.source || 'system',
          importance: r.importance || r.score || 3,
          updated_at: r.updated_at || Date.now() / 1000,
        })));
        // 返回数量等于 limit 说明可能还有更多
        setHasMore(results.length >= currentLimit);
      } else {
        setEntries([]);
        setHasMore(false);
      }
    } catch (e) {
      memoryLogger.warn('记忆API不可用，显示空状态', e);
      setEntries([]);
      setEngineOnline(false);
      setHasMore(false);
    } finally {
      setLoading(false);
      setLoadMoreLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  // 搜索关键词变化时，防抖调用 API 搜索
  useEffect(() => {
    // 空搜索不需要额外调用，初始加载已处理
    if (!searchQuery.trim()) {
      // 清空搜索时重新加载全部
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
      fetchMemories();
      return;
    }

    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(async () => {
      try {
        setSearchLoading(true);
        let results: MemoryEntryRaw[] = [];

        if (isTauri()) {
          const data: MemorySearchResponse = await api.clawbotMemorySearch(searchQuery, limit);
          results = data?.results || data?.entries || [];
        } else {
          const resp = await clawbotFetch(`/api/v1/memory/search?q=${encodeURIComponent(searchQuery)}&limit=${limit}`);
          if (resp.ok) {
            const data = await resp.json();
            results = data.results || data.entries || data || [];
          }
        }

        if (Array.isArray(results) && results.length > 0) {
          setEntries(results.map((r: MemoryEntryRaw) => ({
            key: r.key || r.id || 'unknown',
            value: typeof r.value === 'string' ? r.value : JSON.stringify(r.value || r.content || ''),
            source_bot: r.source_bot || r.source || 'system',
            importance: r.importance || r.score || 3,
            updated_at: r.updated_at || Date.now() / 1000,
          })));
        } else {
          setEntries([]);
        }
      } catch (e) {
        memoryLogger.warn('搜索记忆失败', e);
      } finally {
        setSearchLoading(false);
      }
    }, 300);

    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  // 根据分类筛选过滤记忆条目（与文本搜索叠加使用）
  const filteredEntries = useMemo(() => {
    if (filter === 'all') return entries;
    return entries.filter(entry => {
      switch (filter) {
        case 'profile':
          return entry.key.includes('profile');
        case 'fact':
          return !entry.key.includes('profile');
        case 'important':
          return entry.importance >= 4;
        default:
          return true;
      }
    });
  }, [entries, filter]);

  return (
    <div className="h-full flex flex-col gap-6 max-w-6xl mx-auto overflow-y-auto scroll-container pr-2 pb-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BrainCircuit className="text-purple-400" />
            记忆库
          </h1>
          <p className="text-gray-400 mt-1">
            基于 Mem0 架构的长期记忆库。AI Agent 会自动从对话中提取事实、更新画像并解决记忆冲突。
          </p>
        </div>
        <button 
            onClick={() => fetchMemories()}
            className="flex items-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-lg text-white transition-colors border border-dark-500"
        >
            <RefreshCw size={16} className={clsx(loading && "animate-spin")} />
            刷新
        </button>
      </div>

      <div className="flex gap-6 flex-col lg:flex-row">
        {/* 左侧：搜索与记忆列表 */}
        <div className="flex-1 space-y-4">
          <div className="relative">
            {searchLoading ? (
              <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 text-purple-400 animate-spin" size={18} />
            ) : (
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
            )}
            <input 
              type="text" 
              placeholder="搜索记忆片段、实体或意图..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-xl py-3 pl-10 pr-4 text-white focus:outline-none focus:border-purple-500/50 transition-colors"
              aria-label="搜索记忆"
            />
          </div>

          {/* 分类筛选按钮组 */}
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-gray-500 shrink-0" />
            {([
              { value: 'all', label: '全部' },
              { value: 'profile', label: '用户画像' },
              { value: 'fact', label: '事实' },
              { value: 'important', label: '高优先级' },
            ] as const).map(opt => (
              <button
                key={opt.value}
                onClick={() => setFilter(opt.value)}
                className={clsx(
                  "px-3 py-1.5 text-xs rounded-lg border transition-colors",
                  filter === opt.value
                    ? "bg-purple-500/20 text-purple-400 border-purple-500/30"
                    : "bg-dark-800 text-gray-400 border-dark-600 hover:bg-dark-700 hover:text-gray-300"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filteredEntries.map(entry => {
                const isProfile = entry.key.includes('profile');
                return (
                  <Card key={entry.key} className={clsx(
                      "bg-dark-800 border transition-all hover:border-dark-400 group relative",
                      isProfile ? "border-purple-500/30" : "border-dark-600"
                  )}>
                    <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                            <div className="flex-1 pr-8">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className={clsx(
                                        "px-2 py-0.5 rounded text-[10px] font-medium tracking-wider uppercase",
                                        isProfile ? "bg-purple-500/20 text-purple-400" : "bg-dark-600 text-gray-400"
                                    )}>
                                        {isProfile ? '用户画像' : '事实'}
                                    </span>
                                    <span className="text-xs text-gray-500">标识: {entry.key}</span>
                                    {entry.importance >= 4 && (
                                        <span className="text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded border border-red-500/20">高优先级</span>
                                    )}
                                </div>
                                {editingKey === entry.key ? (
                                  <div className="space-y-2">
                                    <textarea
                                      value={editValue}
                                      onChange={(e) => setEditValue(e.target.value)}
                                      className="w-full bg-dark-900 border border-purple-500/50 rounded-lg p-3 text-sm text-white font-mono focus:outline-none focus:border-purple-500 resize-y min-h-[80px]"
                                      rows={4}
                                      aria-label="编辑记忆内容"
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        onClick={handleSaveEdit}
                                        disabled={!!actionLoading}
                                        className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded-md transition-colors disabled:opacity-50"
                                      >
                                        {actionLoading === editingKey ? <Loader2 size={12} className="animate-spin inline" /> : '保存'}
                                      </button>
                                      <button
                                        onClick={() => setEditingKey(null)}
                                        className="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-300 text-xs rounded-md transition-colors"
                                      >
                                        取消
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap font-mono">
                                    {isProfile ? (() => {
                                      try {
                                        return JSON.stringify(JSON.parse(entry.value), null, 2);
                                      } catch {
                                        return entry.value;
                                      }
                                    })() : entry.value}
                                  </div>
                                )}
                                <div className="mt-3 text-xs text-gray-600">
                                    来源: {entry.source_bot} | 更新: {new Date(entry.updated_at * 1000).toLocaleString()}
                                </div>
                            </div>
                            
                            {/* 操作按钮 (仅悬浮显示) */}
                            <div className="absolute right-4 top-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button onClick={() => handleEdit(entry)} disabled={actionLoading === entry.key} className="p-1.5 bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white rounded border border-dark-500 disabled:opacity-50" aria-label="编辑记忆">
                                    <Edit size={14} />
                                </button>
                                <button onClick={() => setDeleteTarget(entry.key)} disabled={actionLoading === entry.key} className="p-1.5 bg-dark-700 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded border border-dark-500 hover:border-red-500/30 disabled:opacity-50" aria-label="删除记忆">
                                    {actionLoading === entry.key ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                                </button>
                            </div>
                        </div>
                    </CardContent>
                  </Card>
                );
            })}
            
            {!searchLoading && filteredEntries.length === 0 && (
                <div className="text-center py-12 text-gray-500 bg-dark-800/50 rounded-xl border border-dark-700 border-dashed">
                    {searchQuery ? '没有找到匹配的记忆记录' : filter !== 'all' ? '当前筛选条件下没有记忆记录' : '记忆库为空。与 Bot 对话后会自动记录。'}
                </div>
            )}

            {/* 加载更多按钮 */}
            {!searchQuery && filteredEntries.length > 0 && hasMore && (
                <button
                  onClick={() => {
                    const newLimit = limit + 50;
                    setLimit(newLimit);
                    setLoadMoreLoading(true);
                    fetchMemories(newLimit);
                  }}
                  disabled={loadMoreLoading}
                  className="w-full py-3 text-sm text-gray-400 hover:text-white bg-dark-800 hover:bg-dark-700 border border-dark-600 rounded-xl transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {loadMoreLoading ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      加载中...
                    </>
                  ) : (
                    '加载更多'
                  )}
                </button>
            )}
          </div>
        </div>

        {/* 右侧：状态统计板 */}
        <div className="w-full lg:w-80 shrink-0 space-y-4">
            <Card className="bg-dark-800 border-dark-600">
                <CardHeader className="pb-3 border-b border-dark-700">
                    <CardTitle className="text-sm text-gray-300 flex items-center gap-2">
                        <Database size={16} className="text-gray-400" />
                        向量数据库状态
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-4 space-y-4">
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">总记忆条目</span>
                        <span className="text-lg font-mono text-white">{memoryStats?.total ? memoryStats.total.toLocaleString() : entries.length > 0 ? entries.length.toLocaleString() : '—'}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">提取轮次</span>
                        <span className="text-lg font-mono text-white">{memoryStats?.extraction_rounds ?? '—'}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">向量维度</span>
                        <span className="text-lg font-mono text-white">{memoryStats?.vector_dim ?? '—'}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">引擎状态</span>
                        <span className={clsx(
                            "text-xs px-2 py-0.5 rounded border",
                            engineOnline === null ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" :
                            engineOnline ? "bg-green-500/20 text-green-400 border-green-500/30" :
                            "bg-red-500/20 text-red-400 border-red-500/30"
                        )}>
                            {engineOnline === null ? '检查中...' : engineOnline ? '在线' : '未连接'}
                        </span>
                    </div>
                </CardContent>
            </Card>

            <Card className="bg-dark-800 border-dark-600">
                <CardHeader className="pb-3 border-b border-dark-700">
                    <CardTitle className="text-sm text-gray-300">什么是自动冲突解决？</CardTitle>
                </CardHeader>
                <CardContent className="p-4">
                    <p className="text-xs text-gray-400 leading-relaxed">
                        当你在对话中提到 <span className="text-purple-400">"我改用 Solana 链了"</span> 时，Mem0 引擎会自动检索过往记忆。如果发现旧记忆 <span className="text-gray-500 line-through">"用户偏好 ETH 链"</span>，引擎会发送一条 UPDATE 或 DELETE 指令，自动覆盖冲突的旧认知，确保大模型的上下文永远是最新的。
                    </p>
                </CardContent>
            </Card>
        </div>
      </div>
      {/* 删除确认对话框 */}
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            executeDelete(deleteTarget);
            setDeleteTarget(null);
          }
        }}
        title="删除记忆"
        description="确定要删除这条记忆吗？删除后无法恢复。"
        confirmText="删除"
        destructive
      />
    </div>
  );
}

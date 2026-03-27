import { useEffect, useState } from 'react';

import { Database, Search, BrainCircuit, RefreshCw, Trash2, Edit } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import clsx from 'clsx';

interface MemoryEntry {
  key: string;
  value: string;
  source_bot: string;
  importance: number;
  updated_at: number;
}

// API 返回的记忆条目原始格式
interface MemoryApiResult {
  key?: string;
  id?: string;
  value?: string | Record<string, unknown>;
  content?: string;
  source_bot?: string;
  source?: string;
  importance?: number;
  score?: number;
  updated_at?: number;
}

export function Memory() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  // 删除指定记忆条目
  const handleDelete = async (key: string) => {
    if (!confirm('确定要删除这条记忆吗？删除后无法恢复。')) return;
    try {
      await fetch(`http://127.0.0.1:18790/api/v1/memory/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      setEntries(prev => prev.filter(e => e.key !== key));
    } catch (e) {
      console.warn('删除记忆失败:', e);
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
    try {
      await fetch('http://127.0.0.1:18790/api/v1/memory/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: editingKey, value: editValue }),
      });
      setEntries(prev => prev.map(e => e.key === editingKey ? { ...e, value: editValue } : e));
      setEditingKey(null);
    } catch (e) {
      console.warn('更新记忆失败:', e);
    }
  };

  const fetchMemories = async () => {
    try {
      setLoading(true);
      const resp = await fetch('http://127.0.0.1:18790/api/v1/memory/search?q=&limit=50');
      if (resp.ok) {
        const data = await resp.json();
        // API 返回 { results: [...] } 格式
        const results = data.results || data.entries || data || [];
        if (Array.isArray(results) && results.length > 0) {
          setEntries(results.map((r: MemoryApiResult) => ({
            key: r.key || r.id || 'unknown',
            value: typeof r.value === 'string' ? r.value : JSON.stringify(r.value || r.content || ''),
            source_bot: r.source_bot || r.source || 'system',
            importance: r.importance || r.score || 3,
            updated_at: r.updated_at || Date.now() / 1000,
          })));
        } else {
          setEntries([]);
        }
      } else {
        console.warn('记忆API返回非200:', resp.status);
        setEntries([]);
      }
    } catch (e) {
      console.warn('记忆API不可用，显示空状态:', e);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMemories();
  }, []);

  const filteredEntries = entries.filter(e => 
    e.value.toLowerCase().includes(searchQuery.toLowerCase()) || 
    e.key.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col gap-6 max-w-6xl mx-auto overflow-y-auto scroll-container pr-2 pb-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BrainCircuit className="text-purple-400" />
            记忆库 (Smart Memory)
          </h1>
          <p className="text-gray-400 mt-1">
            基于 Mem0 架构的长期记忆库。AI Agent 会自动从对话中提取事实、更新画像并解决记忆冲突。
          </p>
        </div>
        <button 
            onClick={fetchMemories}
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
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
            <input 
              type="text" 
              placeholder="搜索记忆片段、实体或意图..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-xl py-3 pl-10 pr-4 text-white focus:outline-none focus:border-purple-500/50 transition-colors"
            />
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
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        onClick={handleSaveEdit}
                                        className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded-md transition-colors"
                                      >
                                        保存
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
                                <button onClick={() => handleEdit(entry)} className="p-1.5 bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white rounded border border-dark-500">
                                    <Edit size={14} />
                                </button>
                                <button onClick={() => handleDelete(entry.key)} className="p-1.5 bg-dark-700 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded border border-dark-500 hover:border-red-500/30">
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                    </CardContent>
                  </Card>
                );
            })}
            
            {filteredEntries.length === 0 && (
                <div className="text-center py-12 text-gray-500 bg-dark-800/50 rounded-xl border border-dark-700 border-dashed">
                    {searchQuery ? '没有找到匹配的记忆记录' : '记忆库为空。与 Bot 对话后会自动记录。'}
                </div>
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
                        <span className="text-lg font-mono text-white">{entries.length > 0 ? entries.length.toLocaleString() : '—'}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">提取轮次</span>
                        <span className="text-lg font-mono text-white">—</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">向量维度</span>
                        <span className="text-lg font-mono text-white">—</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">引擎状态</span>
                        <span className={clsx(
                            "text-xs px-2 py-0.5 rounded border",
                            loading ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" :
                            entries.length > 0 ? "bg-green-500/20 text-green-400 border-green-500/30" :
                            "bg-gray-500/20 text-gray-400 border-gray-500/30"
                        )}>
                            {loading ? '检查中...' : entries.length > 0 ? '在线' : '未连接'}
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
    </div>
  );
}

import { useEffect, useState } from 'react';

import { Database, Search, BrainCircuit, RefreshCw, Trash2, Edit } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { isTauri } from '../../lib/tauri';
import clsx from 'clsx';

interface MemoryEntry {
  key: string;
  value: string;
  source_bot: string;
  importance: number;
  updated_at: number;
}

export function Memory() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  const fetchMemories = async () => {
    if (!isTauri()) {
       setLoading(false);
       return;
    }
    try {
      setLoading(true);
      // We will need a tauri command for this later. 
      // For now we mock or use empty until backend command is added
      // const res = await invoke<MemoryEntry[]>('get_smart_memories');
      // setEntries(res);
      setEntries([
        { key: 'user_profile_admin', value: '{"name": "Boss", "interests": ["Crypto", "AI", "Automation"], "preferences": {"trading_style": "conservative", "language": "Chinese"}}', source_bot: 'system', importance: 5, updated_at: Date.now() / 1000 },
        { key: 'auto_admin_1711000000', value: '用户希望每日早上 8 点收到科技新闻简报', source_bot: 'assistant', importance: 3, updated_at: Date.now() / 1000 - 86400 },
        { key: 'auto_admin_1711000001', value: '用户不喜欢过于啰嗦的回答，要求直接给结果', source_bot: 'assistant', importance: 4, updated_at: Date.now() / 1000 - 172800 },
        { key: 'auto_admin_1711000002', value: '正在关注 $SOL 的做空机会', source_bot: 'assistant', importance: 3, updated_at: Date.now() / 1000 - 3600 }
      ]);
    } catch (e) {
      console.error(e);
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
                                        {isProfile ? 'USER_PROFILE' : 'FACT'}
                                    </span>
                                    <span className="text-xs text-gray-500">ID: {entry.key}</span>
                                    {entry.importance >= 4 && (
                                        <span className="text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded border border-red-500/20">HIGH PRIORITY</span>
                                    )}
                                </div>
                                <div className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap font-mono">
                                    {isProfile ? JSON.stringify(JSON.parse(entry.value), null, 2) : entry.value}
                                </div>
                                <div className="mt-3 text-xs text-gray-600">
                                    Source: {entry.source_bot} | Updated: {new Date(entry.updated_at * 1000).toLocaleString()}
                                </div>
                            </div>
                            
                            {/* 操作按钮 (仅悬浮显示) */}
                            <div className="absolute right-4 top-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button className="p-1.5 bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white rounded border border-dark-500">
                                    <Edit size={14} />
                                </button>
                                <button className="p-1.5 bg-dark-700 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded border border-dark-500 hover:border-red-500/30">
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
                    没有找到匹配的记忆记录
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
                        <span className="text-lg font-mono text-white">4,281</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">提取轮次</span>
                        <span className="text-lg font-mono text-white">128</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">向量维度</span>
                        <span className="text-lg font-mono text-white">1536</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">引擎状态</span>
                        <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded border border-green-500/30">在线</span>
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

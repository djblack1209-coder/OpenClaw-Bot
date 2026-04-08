import { useState, useEffect, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import {
  Blocks, Search, Plus, Settings2, Trash2,
  GitBranch, Database, Globe, HardDrive,
  RefreshCw, AlertCircle, User, Loader2,
  type LucideIcon,
} from 'lucide-react';
import clsx from 'clsx';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { PromptDialog } from '@/components/ui/prompt-dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { isTauri } from '../../lib/tauri';
import { createLogger } from '@/lib/logger';

// 插件管理模块日志实例
const pluginsLogger = createLogger('Plugins');

interface MCPPlugin {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  type: 'stdio' | 'sse';
  status: 'running' | 'configured' | 'stopped' | 'error';
  icon: LucideIcon;
  tags: string[];
  command?: string;
  args?: string[];
  env?: Record<string, string>;
}

const fallbackIcon = Blocks;

const getIconForPlugin = (id: string) => {
  if (id.includes('github')) return GitBranch;
  if (id.includes('sqlite') || id.includes('db')) return Database;
  if (id.includes('browser')) return Globe;
  if (id.includes('file') || id.includes('fs')) return HardDrive;
  return fallbackIcon;
};

export function Plugins() {
  const [plugins, setPlugins] = useState<MCPPlugin[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  // 卸载确认对话框状态
  const [uninstallTarget, setUninstallTarget] = useState<MCPPlugin | null>(null);
  // 安装新插件对话框
  const [showInstallDialog, setShowInstallDialog] = useState(false);
  // 配置插件对话框
  const [configTarget, setConfigTarget] = useState<MCPPlugin | null>(null);

  const fetchPlugins = useCallback(async () => {
    if (!isTauri()) {
      // 非 Tauri 环境显示空列表
      setPlugins([]);
      setLoading(false);
      return;
    }

    try {
      const data = await invoke<MCPPlugin[]>('get_mcp_plugins');
      if (data && data.length > 0) {
        // 字符串图标名映射为 Lucide 组件
        const mapped = data.map(p => ({
          ...p,
          icon: getIconForPlugin(p.id)
        }));
        setPlugins(mapped);
      } else {
        // 无已安装插件，显示空状态
        setPlugins([]);
      }
    } catch (e) {
      pluginsLogger.error('获取插件列表失败', e);
      setPlugins([]);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchPlugins();
  }, [fetchPlugins]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    fetchPlugins();
  };

  const togglePlugin = async (id: string, currentStatus: string) => {
    // 开启时标记为"已配置"而非"运行中"（实际连接由 Gateway 管理）
    const targetStatus: MCPPlugin['status'] = (currentStatus === 'running' || currentStatus === 'configured') ? 'stopped' : 'configured';
    
    // 乐观更新
    setPlugins(prev => prev.map(p => {
      if (p.id === id) return { ...p, status: targetStatus };
      return p;
    }));

    if (isTauri()) {
      try {
        await invoke('toggle_mcp_plugin_status', { id, targetStatus });
      } catch (e) {
        pluginsLogger.error('切换插件状态失败', e);
        toast.error('插件状态切换失败');
        // 失败时回滚
        fetchPlugins();
      }
    }
  };

  // 安装新 MCP 插件 — 通过名称和命令创建插件配置
  const handleInstallPlugin = async (input: string) => {
    if (!input.trim()) return;
    const name = input.trim();
    // 生成插件 ID（npm 包名或自定义名称）
    const id = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');

    const newPlugin = {
      id,
      name,
      description: `通过 MCP 协议接入的 ${name} 服务`,
      version: '1.0.0',
      author: 'custom',
      type: 'stdio',
      status: 'configured',
      icon: 'blocks',
      tags: ['custom'],
      command: 'npx',
      args: ['-y', name],
      env: {},
    };

    try {
      if (isTauri()) {
        await invoke('save_mcp_plugin', { plugin: newPlugin });
      }
      toast.success(`插件 ${name} 已添加，请在列表中开启`);
      fetchPlugins();
    } catch (e) {
      pluginsLogger.error('安装插件失败', e);
      toast.error('插件安装失败，请检查名称是否正确');
    }
  };

  // 更新插件配置（命令、参数、环境变量）
  const handleConfigPlugin = async (input: string) => {
    if (!configTarget || !input.trim()) return;
    try {
      const updated = { ...configTarget, command: input.trim(), icon: 'blocks' };
      if (isTauri()) {
        await invoke('save_mcp_plugin', { plugin: updated });
      }
      toast.success(`插件 ${configTarget.name} 配置已更新`);
      setConfigTarget(null);
      fetchPlugins();
    } catch (e) {
      pluginsLogger.error('配置插件失败', e);
      toast.error('配置更新失败');
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
      </div>
    );
  }

  const filteredPlugins = plugins.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    p.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const activeCount = plugins.filter(p => p.status === 'running' || p.status === 'configured').length;

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-dark-800/40 p-6 rounded-2xl border border-dark-600/50 backdrop-blur-sm">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Blocks className="text-purple-400 h-6 w-6" />
              MCP 插件市场 (Model Context Protocol)
            </h2>
            <p className="text-gray-400 text-sm mt-2 max-w-2xl leading-relaxed">
              彻底告别硬编码工具链。通过 Anthropic 标准的 MCP 协议，为 OpenClaw 接入本地文件、数据库、GitHub 等无限外部能力。
            </p>
          </div>
          
          <div className="flex gap-3">
            <div className="flex flex-col items-end justify-center px-4 py-2 rounded-xl bg-dark-900/80 border border-dark-700 shadow-inner">
              <span className="text-2xl font-bold text-white leading-none">{activeCount}<span className="text-sm text-gray-500 font-normal ml-1">/ {plugins.length}</span></span>
              <span className="text-xs text-green-400 font-medium flex items-center gap-1 mt-1">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
                </span>
                活跃服务
              </span>
            </div>
            <button onClick={() => setShowInstallDialog(true)} className="btn-primary shadow-lg shadow-purple-500/20 bg-purple-600 hover:bg-purple-700 flex items-center gap-2 h-auto px-5 transition-transform hover:scale-105 active:scale-95">
              <Plus size={18} /> 安装新插件
            </button>
          </div>
        </div>

        {/* Search and Filter */}
        <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
            <input
              type="text"
              placeholder="搜索 MCP 插件..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white focus:outline-none focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/50 transition-all placeholder:text-gray-600"
              aria-label="搜索插件"
            />
          </div>
          <button 
            onClick={handleRefresh}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors bg-dark-800 px-4 py-2.5 rounded-xl border border-dark-600 hover:border-dark-500"
          >
            <RefreshCw size={16} className={clsx(isRefreshing && "animate-spin")} />
            刷新状态
          </button>
        </div>

        {/* Plugin Grid */}
        {plugins.length === 0 ? (
          /* 无已安装插件时的空状态提示 */
          <div className="flex flex-col items-center justify-center py-20 text-gray-400 bg-dark-800/30 rounded-2xl border border-dashed border-dark-600">
            <Blocks className="w-12 h-12 text-dark-500 mb-4" />
            <p className="text-base font-medium text-gray-300 mb-1">暂无已安装的 MCP 插件</p>
            <p className="text-sm text-gray-500">点击「安装新插件」添加。</p>
          </div>
        ) : filteredPlugins.length === 0 ? (
          /* 搜索无结果时的占位提示 */
          <div className="flex flex-col items-center justify-center h-32 text-dark-500">
            <p className="text-sm">未找到匹配的插件</p>
            <p className="text-xs mt-1">试试其他关键词</p>
          </div>
        ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {filteredPlugins.map((plugin) => (
            <Card 
              key={plugin.id} 
              className={clsx(
                "bg-dark-800/60 border-dark-600 shadow-lg hover:border-dark-500 transition-all overflow-hidden group",
                plugin.status === 'running' && "border-l-2 border-l-green-500",
                plugin.status === 'configured' && "border-l-2 border-l-yellow-500"
              )}
            >
              <CardHeader className="pb-3 pt-5 px-5 flex flex-row items-start justify-between space-y-0 border-b border-dark-700/50">
                <div className="flex gap-3">
                  <div className={clsx(
                    "w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border shadow-sm transition-colors",
                    (plugin.status === 'running' || plugin.status === 'configured') ? "bg-dark-900 border-dark-700" : "bg-dark-900/50 border-dark-800 opacity-60"
                  )}>
                    {plugin.icon && <plugin.icon size={24} className={clsx(
                      plugin.status === 'running' ? "text-purple-400" : plugin.status === 'configured' ? "text-yellow-400" : "text-gray-500"
                    )} />}
                  </div>
                  <div className="space-y-1 min-w-0">
                    <CardTitle className="text-base font-bold text-white truncate group-hover:text-purple-400 transition-colors" title={plugin.name}>
                      {plugin.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 font-mono">{plugin.version}</span>
                      <span className="text-gray-700 text-xs">•</span>
                      <span className="text-xs text-gray-500 flex items-center gap-1 truncate">
                        <User size={10} /> {plugin.author}
                      </span>
                    </div>
                  </div>
                </div>
                <Switch 
                  checked={plugin.status === 'running' || plugin.status === 'configured'} 
                  onCheckedChange={() => togglePlugin(plugin.id, plugin.status)}
                  className="data-[state=checked]:bg-green-500"
                />
              </CardHeader>
              
              <CardContent className="p-5">
                <p className="text-sm text-gray-400 h-10 line-clamp-2 mb-4 leading-relaxed">
                  {plugin.description}
                </p>
                
                <div className="flex items-center justify-between mb-4">
                  <div className="flex flex-wrap gap-1.5">
                    {plugin.tags.map(tag => (
                      <Badge key={tag} variant="outline" className="bg-dark-900/50 border-dark-700 text-gray-400 text-[10px] py-0 font-medium">
                        #{tag}
                      </Badge>
                    ))}
                  </div>
                  <Badge variant="secondary" className="bg-dark-900 text-gray-300 font-mono text-[10px]">
                    {plugin.type.toUpperCase()}
                  </Badge>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-dark-700/50 mt-auto">
                  <div className="flex items-center gap-1.5">
                    {plugin.status === 'running' ? (
                      <Badge className="bg-green-500/10 text-green-400 hover:bg-green-500/20 border-none px-2 shadow-none gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> 已连接
                      </Badge>
                    ) : plugin.status === 'configured' ? (
                      <Badge className="bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 border-none px-2 shadow-none gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span> 已配置
                      </Badge>
                    ) : plugin.status === 'error' ? (
                      <Badge className="bg-red-500/10 text-red-400 hover:bg-red-500/20 border-none px-2 shadow-none gap-1.5">
                        <AlertCircle size={10} /> 已失败
                      </Badge>
                    ) : (
                      <Badge className="bg-gray-500/10 text-gray-400 hover:bg-gray-500/20 border-none px-2 shadow-none gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-500"></span> 已停用
                      </Badge>
                    )}
                  </div>
                  
                  <div className="flex gap-2">
                    <button onClick={() => setConfigTarget(plugin)} className="p-1.5 text-gray-500 hover:text-white hover:bg-dark-700 rounded-md transition-colors" title="配置" aria-label="配置插件">
                      <Settings2 size={16} />
                    </button>
                    <button onClick={() => setUninstallTarget(plugin)} className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-colors" title="卸载" aria-label="卸载插件">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
          
          {/* Add Custom Plugin Card */}
          <button onClick={() => setShowInstallDialog(true)} className="flex flex-col items-center justify-center gap-3 bg-dark-900/30 border-2 border-dashed border-dark-600 hover:border-purple-500/50 hover:bg-dark-800/50 transition-all rounded-xl h-[260px] text-gray-500 hover:text-purple-400 group">
            <div className="w-14 h-14 rounded-full bg-dark-800 border border-dark-600 flex items-center justify-center group-hover:scale-110 transition-transform shadow-sm">
              <Plus size={24} />
            </div>
            <div className="text-center">
              <p className="font-semibold text-white group-hover:text-purple-400 transition-colors mb-1">自定义 MCP Server</p>
              <p className="text-xs text-gray-500 max-w-[200px]">通过 NPM, NPX, PIP 或 Docker 镜像挂载外部插件</p>
            </div>
          </button>
        </div>
        )}
      </div>

      {/* 卸载确认对话框 */}
      <ConfirmDialog
        open={!!uninstallTarget}
        onClose={() => setUninstallTarget(null)}
        onConfirm={() => {
          if (!uninstallTarget) return;
          setPlugins(prev => prev.filter(p => p.id !== uninstallTarget.id));
          toast.success(`已卸载 ${uninstallTarget.name}`);
          if (isTauri()) {
            invoke('remove_mcp_plugin', { id: uninstallTarget.id }).catch((err: unknown) => pluginsLogger.error('卸载插件失败', err));
          }
          setUninstallTarget(null);
        }}
        title="卸载插件"
        description={`确定要卸载插件「${uninstallTarget?.name ?? ''}」吗？`}
        confirmText="卸载"
        destructive
      />

      {/* 安装新插件对话框 */}
      <PromptDialog
        open={showInstallDialog}
        onClose={() => setShowInstallDialog(false)}
        onConfirm={handleInstallPlugin}
        title="安装 MCP 插件"
        description="输入 NPM 包名（如 @modelcontextprotocol/server-filesystem）或自定义服务名称。安装后可在列表中配置启动命令和环境变量。"
        placeholder="例: @modelcontextprotocol/server-github"
        confirmText="安装"
      />

      {/* 配置插件对话框 */}
      <PromptDialog
        open={!!configTarget}
        onClose={() => setConfigTarget(null)}
        onConfirm={handleConfigPlugin}
        title={`配置插件: ${configTarget?.name ?? ''}`}
        description={`当前启动命令: ${configTarget?.command ?? '未设置'} ${(configTarget?.args ?? []).join(' ')}\n请输入新的启动命令（如 npx -y @mcp/server-xxx）`}
        placeholder={configTarget?.command ?? 'npx -y @mcp/server-xxx'}
        confirmText="保存配置"
      />
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import {
  Network,
  RefreshCw,
  Plus,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  ServerOff,
  Trash2,
  Power,
} from 'lucide-react';
import clsx from 'clsx';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { clawbotFetch } from '@/lib/tauri';
import { createLogger } from '@/lib/logger';

// API 网关管理模块日志实例
const gatewayLogger = createLogger('APIGateway');

// ── 类型定义 ──────────────────────────────────────────────────

/** New-API 渠道 */
interface NewApiChannel {
  id?: number;
  name?: string;
  type?: number;
  key?: string;
  base_url?: string;
  models?: string;
  group?: string;
  status?: number;
  used_quota?: number;
  balance?: number;
}

/** New-API 令牌 */
interface NewApiToken {
  id?: number;
  name?: string;
  key?: string;
  status?: number;
  used_quota?: number;
  remain_quota?: number;
  expired_time?: number;
  unlimited_quota?: boolean;
}

/** 网关状态响应 */
interface GatewayStatusData {
  online?: boolean;
  status?: string;
  message?: string;
  version?: string;
}

// ── 渠道类型映射 ──────────────────────────────────────────────

const CHANNEL_TYPE_NAMES: Record<number, string> = {
  1: 'OpenAI',
  3: 'Azure',
  14: 'Anthropic',
  15: 'Baidu',
  17: 'Ali',
  18: 'Xunfei',
  19: 'AI360',
  23: 'Tencent',
  24: 'Google Gemini',
  25: 'Moonshot',
  26: 'Baichuan',
  27: 'Minimax',
  28: 'Mistral',
  29: 'Groq',
  31: 'Lingyi',
  33: 'Deepseek',
  40: 'Cohere',
};

/** 获取渠道类型名称 */
function getChannelTypeName(type?: number): string {
  if (type === undefined || type === null) return '未知';
  return CHANNEL_TYPE_NAMES[type] ?? `类型 ${type}`;
}

/** 渠道状态显示 */
function getChannelStatusInfo(status?: number): { label: string; color: string } {
  switch (status) {
    case 1:
      return { label: '启用', color: 'text-green-400' };
    case 2:
      return { label: '禁用', color: 'text-red-400' };
    case 3:
      return { label: '测试中', color: 'text-yellow-400' };
    default:
      return { label: '未知', color: 'text-gray-400' };
  }
}

/** 令牌状态显示 */
function getTokenStatusInfo(status?: number): { label: string; color: string } {
  switch (status) {
    case 1:
      return { label: '启用', color: 'text-green-400' };
    case 2:
      return { label: '禁用', color: 'text-red-400' };
    default:
      return { label: '未知', color: 'text-gray-400' };
  }
}

/** 遮蔽令牌 key，仅显示前缀 */
function maskKey(key?: string): string {
  if (!key) return '—';
  if (key.length <= 8) return '****';
  return key.slice(0, 6) + '****' + key.slice(-4);
}

// ── 新建渠道表单 ──────────────────────────────────────────────

interface ChannelForm {
  name: string;
  type: number;
  key: string;
  base_url: string;
  models: string;
  group: string;
}

const EMPTY_FORM: ChannelForm = {
  name: '',
  type: 1,
  key: '',
  base_url: '',
  models: '',
  group: 'default',
};

// ── 主组件 ────────────────────────────────────────────────────

export function APIGateway() {
  // 网关状态
  const [online, setOnline] = useState<boolean | null>(null);
  const [statusMsg, setStatusMsg] = useState('');
  const [loading, setLoading] = useState(true);

  // 渠道和令牌列表
  const [channels, setChannels] = useState<NewApiChannel[]>([]);
  const [tokens, setTokens] = useState<NewApiToken[]>([]);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [tokensLoading, setTokensLoading] = useState(false);

  // 新建渠道对话框
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [form, setForm] = useState<ChannelForm>({ ...EMPTY_FORM });
  const [submitting, setSubmitting] = useState(false);

  // 令牌显示/隐藏
  const [visibleTokenIds, setVisibleTokenIds] = useState<Set<number>>(new Set());

  // 刷新中
  const [refreshing, setRefreshing] = useState(false);

  // ── 获取网关状态 ────────────────────────────────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const res = await clawbotFetch('/api/v1/newapi/status');
      if (!res.ok) {
        setOnline(false);
        setStatusMsg(`HTTP ${res.status}`);
        return;
      }
      const data: GatewayStatusData = await res.json();
      const isOnline = data.online ?? (data.status === 'ok');
      setOnline(isOnline);
      setStatusMsg(data.message ?? (isOnline ? '运行正常' : '未响应'));
    } catch (err) {
      gatewayLogger.error('获取网关状态失败', err);
      setOnline(false);
      setStatusMsg('无法连接到后端服务');
    }
  }, []);

  // ── 获取渠道列表 ────────────────────────────────────────────

  const fetchChannels = useCallback(async () => {
    setChannelsLoading(true);
    try {
      const res = await clawbotFetch('/api/v1/newapi/channels');
      if (!res.ok) {
        setChannels([]);
        return;
      }
      const json = await res.json();
      // 兼容 { data: [...] } 或直接数组
      const list = Array.isArray(json) ? json : (json.data ?? json.channels ?? []);
      setChannels(list);
    } catch (err) {
      gatewayLogger.error('获取渠道列表失败', err);
      setChannels([]);
    } finally {
      setChannelsLoading(false);
    }
  }, []);

  // ── 获取令牌列表 ────────────────────────────────────────────

  const fetchTokens = useCallback(async () => {
    setTokensLoading(true);
    try {
      const res = await clawbotFetch('/api/v1/newapi/tokens');
      if (!res.ok) {
        setTokens([]);
        return;
      }
      const json = await res.json();
      const list = Array.isArray(json) ? json : (json.data ?? json.tokens ?? []);
      setTokens(list);
    } catch (err) {
      gatewayLogger.error('获取令牌列表失败', err);
      setTokens([]);
    } finally {
      setTokensLoading(false);
    }
  }, []);

  // ── 首次加载 ────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchStatus();
      // 只有网关在线才拉列表
      await Promise.all([fetchChannels(), fetchTokens()]);
      setLoading(false);
    };
    init();
  }, [fetchStatus, fetchChannels, fetchTokens]);

  // ── 手动刷新 ────────────────────────────────────────────────

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchStatus();
    await Promise.all([fetchChannels(), fetchTokens()]);
    setRefreshing(false);
    toast.success('已刷新');
  };

  // ── 新建渠道 ────────────────────────────────────────────────

  const handleCreateChannel = async () => {
    if (!form.name.trim()) {
      toast.error('请输入渠道名称');
      return;
    }
    setSubmitting(true);
    try {
      const res = await clawbotFetch('/api/v1/newapi/channels', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name,
          type: form.type,
          key: form.key || undefined,
          base_url: form.base_url || undefined,
          models: form.models || undefined,
          group: form.group || 'default',
        }),
        headers: { 'Content-Type': 'application/json' },
      });

      if (res.ok) {
        toast.success('渠道创建成功');
        setShowAddDialog(false);
        setForm({ ...EMPTY_FORM });
        await fetchChannels();
      } else {
        const err = await res.text();
        toast.error(`创建失败: ${err}`);
      }
    } catch (err) {
      gatewayLogger.error('创建渠道失败', err);
      toast.error('创建渠道时发生错误');
    } finally {
      setSubmitting(false);
    }
  };

  // ── 切换令牌可见 ────────────────────────────────────────────

  const toggleTokenVisibility = (tokenId: number) => {
    setVisibleTokenIds((prev) => {
      const next = new Set(prev);
      if (next.has(tokenId)) {
        next.delete(tokenId);
      } else {
        next.add(tokenId);
      }
      return next;
    });
  };

  // ── 删除渠道 ────────────────────────────────────────────────

  const handleDeleteChannel = async (channelId: number) => {
    if (!confirm('确定要删除这个渠道吗？')) return;
    try {
      const res = await clawbotFetch(`/api/v1/newapi/channels/${channelId}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('渠道已删除');
        await fetchChannels();
      } else {
        toast.error('删除失败');
      }
    } catch (err) {
      gatewayLogger.error('删除渠道失败', err);
      toast.error('删除渠道时发生错误');
    }
  };

  // ── 切换渠道启停 ────────────────────────────────────────────

  const handleToggleChannel = async (channelId: number) => {
    try {
      const res = await clawbotFetch(`/api/v1/newapi/channels/${channelId}/status`, { method: 'POST' });
      if (res.ok) {
        toast.success('渠道状态已切换');
        await fetchChannels();
      } else {
        toast.error('切换状态失败');
      }
    } catch (err) {
      gatewayLogger.error('切换渠道状态失败', err);
      toast.error('操作失败');
    }
  };

  // ── 删除令牌 ────────────────────────────────────────────────

  const handleDeleteToken = async (tokenId: number) => {
    if (!confirm('确定要删除这个令牌吗？')) return;
    try {
      const res = await clawbotFetch(`/api/v1/newapi/tokens/${tokenId}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('令牌已删除');
        await fetchTokens();
      } else {
        toast.error('删除失败');
      }
    } catch (err) {
      gatewayLogger.error('删除令牌失败', err);
      toast.error('删除令牌时发生错误');
    }
  };

  // ── 加载状态 ────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-claw-500" />
      </div>
    );
  }

  // ── 渲染 ────────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto scroll-container space-y-6">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Network className="w-5 h-5 text-claw-400" />
          <h2 className="text-lg font-semibold text-white">API 网关管理</h2>
          {online !== null && (
            <Badge
              className={clsx(
                'text-xs',
                online
                  ? 'bg-green-500/20 text-green-400 border-green-500/30'
                  : 'bg-red-500/20 text-red-400 border-red-500/30'
              )}
              variant="outline"
            >
              {online ? '在线' : '离线'}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={clsx('w-3.5 h-3.5', refreshing && 'animate-spin')} />
            <span className="hidden sm:inline ml-1">刷新</span>
          </Button>
          <Button
            size="sm"
            onClick={() => setShowAddDialog(true)}
            disabled={!online}
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="hidden sm:inline ml-1">新建渠道</span>
          </Button>
        </div>
      </div>

      {/* 网关离线提示 */}
      {online === false && (
        <Card className="border-yellow-500/20 bg-yellow-500/5">
          <CardContent className="flex items-start gap-4 py-2">
            <ServerOff className="w-10 h-10 text-yellow-400 shrink-0 mt-1" />
            <div>
              <h3 className="text-base font-medium text-yellow-300 mb-1">API 网关未启动</h3>
              <p className="text-sm text-gray-400 leading-relaxed">
                New-API 网关服务当前不可用。可能的原因：
              </p>
              <ul className="text-sm text-gray-400 mt-2 space-y-1 list-disc list-inside">
                <li>Docker 容器未运行（请检查 Docker Desktop）</li>
                <li>后端 ClawBot 服务未启动</li>
                <li>网关端口被占用或配置错误</li>
              </ul>
              <p className="text-sm text-gray-500 mt-3">
                {statusMsg && `详细信息：${statusMsg}`}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 状态概览卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 网关状态 */}
        <Card className="bg-dark-800 border-dark-600">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-gray-400 font-medium">网关状态</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {online ? (
                <CheckCircle2 className="w-5 h-5 text-green-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
              <span className={clsx('text-lg font-semibold', online ? 'text-green-400' : 'text-red-400')}>
                {online ? '运行正常' : '未连接'}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* 渠道数量 */}
        <Card className="bg-dark-800 border-dark-600">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-gray-400 font-medium">渠道数量</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-white">{channels.length}</span>
              <span className="text-sm text-gray-500">个渠道</span>
            </div>
          </CardContent>
        </Card>

        {/* 令牌数量 */}
        <Card className="bg-dark-800 border-dark-600">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-gray-400 font-medium">令牌数量</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-white">{tokens.length}</span>
              <span className="text-sm text-gray-500">个令牌</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 渠道列表 */}
      <Card className="bg-dark-800 border-dark-600">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            渠道列表
            {channelsLoading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {channels.length === 0 ? (
            <div className="text-center py-8">
              <AlertCircle className="w-8 h-8 text-gray-500 mx-auto mb-2" />
              <p className="text-gray-400 text-sm">
                {online ? '暂无渠道，点击「新建渠道」添加' : '网关离线，无法加载渠道'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dark-600 text-gray-400">
                    <th className="text-left py-2 px-3 font-medium">ID</th>
                    <th className="text-left py-2 px-3 font-medium">名称</th>
                    <th className="text-left py-2 px-3 font-medium">类型</th>
                    <th className="text-left py-2 px-3 font-medium">模型</th>
                    <th className="text-left py-2 px-3 font-medium">状态</th>
                    <th className="text-left py-2 px-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((ch, idx) => {
                    const statusInfo = getChannelStatusInfo(ch.status);
                    return (
                      <tr
                        key={ch.id ?? idx}
                        className="border-b border-dark-700/50 hover:bg-dark-700/30 transition-colors"
                      >
                        <td className="py-2 px-3 text-gray-400">{ch.id ?? '—'}</td>
                        <td className="py-2 px-3 text-white font-medium">{ch.name ?? '—'}</td>
                        <td className="py-2 px-3 text-gray-300">{getChannelTypeName(ch.type)}</td>
                        <td className="py-2 px-3 text-gray-400 max-w-[200px] truncate">
                          {ch.models || '—'}
                        </td>
                        <td className="py-2 px-3">
                          <span className={clsx('font-medium', statusInfo.color)}>
                            {statusInfo.label}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => ch.id && handleToggleChannel(ch.id)}
                              className={clsx(
                                'p-1 rounded transition-colors',
                                ch.status === 1
                                  ? 'text-green-400 hover:bg-green-500/10'
                                  : 'text-gray-500 hover:bg-gray-500/10'
                              )}
                              title={ch.status === 1 ? '禁用' : '启用'}
                            >
                              <Power className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => ch.id && handleDeleteChannel(ch.id)}
                              className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                              title="删除"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 令牌列表 */}
      <Card className="bg-dark-800 border-dark-600">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            令牌列表
            {tokensLoading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tokens.length === 0 ? (
            <div className="text-center py-8">
              <AlertCircle className="w-8 h-8 text-gray-500 mx-auto mb-2" />
              <p className="text-gray-400 text-sm">
                {online ? '暂无令牌' : '网关离线，无法加载令牌'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dark-600 text-gray-400">
                    <th className="text-left py-2 px-3 font-medium">ID</th>
                    <th className="text-left py-2 px-3 font-medium">名称</th>
                    <th className="text-left py-2 px-3 font-medium">密钥</th>
                    <th className="text-left py-2 px-3 font-medium">状态</th>
                    <th className="text-left py-2 px-3 font-medium">已用额度</th>
                    <th className="text-left py-2 px-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map((tk, idx) => {
                    const statusInfo = getTokenStatusInfo(tk.status);
                    const tokenId = tk.id ?? idx;
                    const isVisible = visibleTokenIds.has(tokenId);
                    return (
                      <tr
                        key={tokenId}
                        className="border-b border-dark-700/50 hover:bg-dark-700/30 transition-colors"
                      >
                        <td className="py-2 px-3 text-gray-400">{tk.id ?? '—'}</td>
                        <td className="py-2 px-3 text-white font-medium">{tk.name ?? '—'}</td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <code className="text-xs text-gray-400 bg-dark-700 px-2 py-0.5 rounded font-mono">
                              {isVisible ? (tk.key ?? '—') : maskKey(tk.key)}
                            </code>
                            <button
                              onClick={() => toggleTokenVisibility(tokenId)}
                              className="text-gray-500 hover:text-gray-300 transition-colors"
                            >
                              {isVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        </td>
                        <td className="py-2 px-3">
                          <span className={clsx('font-medium', statusInfo.color)}>
                            {statusInfo.label}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-gray-400">
                          {tk.used_quota !== undefined ? tk.used_quota.toLocaleString() : '—'}
                        </td>
                        <td className="py-2 px-3">
                          <button
                            onClick={() => tk.id && handleDeleteToken(tk.id)}
                            className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 新建渠道对话框 */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新建渠道</DialogTitle>
            <DialogDescription>
              添加一个 LLM 供应商渠道到 API 网关
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* 渠道名称 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">渠道名称 *</label>
              <Input
                placeholder="例如：OpenAI 主力"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>

            {/* 渠道类型 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">渠道类型</label>
              <select
                className="w-full h-8 rounded-lg border border-input bg-dark-700 px-2.5 text-sm text-white outline-none focus:border-ring focus:ring-3 focus:ring-ring/50"
                value={form.type}
                onChange={(e) => setForm((f) => ({ ...f, type: Number(e.target.value) }))}
              >
                {Object.entries(CHANNEL_TYPE_NAMES).map(([val, name]) => (
                  <option key={val} value={val}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            {/* API Key */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">API Key</label>
              <Input
                placeholder="sk-..."
                type="password"
                value={form.key}
                onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              />
            </div>

            {/* Base URL */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">Base URL</label>
              <Input
                placeholder="https://api.openai.com"
                value={form.base_url}
                onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
              />
            </div>

            {/* 模型列表 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">模型列表</label>
              <Input
                placeholder="gpt-4o,gpt-4o-mini（逗号分隔）"
                value={form.models}
                onChange={(e) => setForm((f) => ({ ...f, models: e.target.value }))}
              />
            </div>

            {/* 分组 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-300">分组</label>
              <Input
                placeholder="default"
                value={form.group}
                onChange={(e) => setForm((f) => ({ ...f, group: e.target.value }))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>
              取消
            </Button>
            <Button onClick={handleCreateChannel} disabled={submitting}>
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

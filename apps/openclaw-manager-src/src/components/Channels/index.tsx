import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { api, ChannelConfig } from '@/lib/tauri';
import { createLogger } from '@/lib/logger';
import { toast } from 'sonner';
import {
  MessageCircle, Save, Loader2, Link as LinkIcon, Edit2, AlertCircle, RefreshCw, Play
} from 'lucide-react';

const channelsLogger = createLogger('Channels');

// 渠道测试返回结果
interface ChannelTestResult {
  success: boolean;
  message: string;
  error?: string;
  latency?: number;
}

const CHANNEL_INFO: Record<string, { name: string; icon: string; color: string; fields: { key: string; label: string; desc?: string; type?: string }[] }> = {
  telegram: {
    name: 'Telegram', icon: 'tg', color: 'text-blue-400',
    fields: [
      { key: 'userId', label: '管理员用户 ID', desc: '管理员Telegram ID（多用户逗号分隔）' },
      { key: 'dmPolicy', label: '私聊策略', type: 'select' },
      { key: 'groupPolicy', label: '群组策略', type: 'select' }
    ]
  },
  discord: {
    name: 'Discord', icon: 'dc', color: 'text-indigo-400',
    fields: [
      { key: 'testChannelId', label: '测试频道 ID', desc: '用于发送测试消息的Discord频道ID' }
    ]
  },
  slack: {
    name: 'Slack', icon: 'sl', color: 'text-rose-400',
    fields: [
      { key: 'testChannelId', label: '测试频道 ID', desc: '用于发送测试消息的Slack频道ID' }
    ]
  },
  feishu: {
    name: '飞书', icon: 'fs', color: 'text-cyan-500',
    fields: [
      { key: 'testChatId', label: '测试会话 ID', desc: '用于发送测试消息的飞书会话ID' }
    ]
  },
  whatsapp: {
    name: 'WhatsApp', icon: 'wa', color: 'text-green-500',
    fields: []
  },
  wechat: {
    name: '微信', icon: 'wc', color: 'text-emerald-500',
    fields: [
      { key: 'bridge', label: '桥接方式', desc: '选择微信接入方式（推荐 wechaty）', type: 'select' },
      { key: 'puppet', label: 'Puppet 类型', desc: '微信协议层实现（推荐 puppet-wechat4u）', type: 'select' },
      { key: 'autoAccept', label: '自动通过好友请求', type: 'select' },
      { key: 'adminWxId', label: '管理员微信ID', desc: '你的微信号（用于管理指令）' },
    ]
  }
};

export function Channels() {
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string; error?: string } | null>(null);


  const loadChannels = async () => {
    try {
      setLoading(true);
      const data = await api.getChannelsConfig();
      setChannels(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error('加载渠道配置失败', { description: msg });
      channelsLogger.error('Failed to load channels:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadChannels();
  }, []);

  const handleEdit = (channel: ChannelConfig) => {
    setEditingId(channel.id);
    // 渠道配置值在表单中均为字符串
    const stringConfig: Record<string, string> = {};
    for (const [k, v] of Object.entries(channel.config)) {
      stringConfig[k] = String(v ?? '');
    }
    setEditForm(stringConfig);
    setTestResult(null);
  };

  const handleCancel = () => {
    setEditingId(null);
    setEditForm({});
  };

  const handleSave = async (channelId: string, channelType: string) => {
    try {
      setSaving(true);
      const newConfig: ChannelConfig = {
        id: channelId,
        channel_type: channelType,
        enabled: true,
        config: editForm
      };
      await api.saveChannelConfig(newConfig);
      toast.success('配置已保存');
      setEditingId(null);
      await loadChannels();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error('保存失败', { description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (channelType: string, channelId: string) => {
    try {
      setTestingId(channelId);
      setTestResult(null);
      const result = await api.testChannel(channelType) as ChannelTestResult;
      
      setTestResult({
        id: channelId,
        success: result.success,
        message: result.message,
        error: result.error
      });

      if (result.success) {
        toast.success(`[${channelType}] 测试通过`, { description: result.message });
      } else {
        toast.error(`[${channelType}] 测试失败`, { description: result.error || result.message });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error('测试执行失败', { description: msg });
      setTestResult({
        id: channelId,
        success: false,
        message: '执行错误',
        error: msg
      });
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6 flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 text-claw-400 mb-2">
              <MessageCircle size={18} />
              <span className="text-sm font-medium">渠道管理</span>
            </div>
            <h2 className="text-xl font-semibold text-white">消息平台接入</h2>
            <p className="text-sm text-gray-400 mt-1">配置 OpenClaw Bot 连接的各个通讯渠道</p>
          </div>
          <button
            onClick={loadChannels}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>

        {loading && channels.length === 0 ? (
          <div className="flex items-center justify-center p-12 text-gray-400">
            <Loader2 className="animate-spin w-8 h-8" />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.map((channel) => {
              const info = CHANNEL_INFO[channel.channel_type] || { name: channel.channel_type, color: 'text-gray-400', fields: [] };
              const isEditing = editingId === channel.id;
              
              return (
                <div key={channel.id} className={`bg-dark-700 rounded-xl border p-5 transition-all ${isEditing ? 'border-claw-500 shadow-[0_0_15px_rgba(249,77,58,0.1)]' : 'border-dark-500 hover:border-dark-400'}`}>
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center border border-dark-500 ${info.color}`}>
                        <MessageCircle size={20} />
                      </div>
                      <div>
                        <h3 className="text-lg font-medium text-white">{info.name}</h3>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`w-2 h-2 rounded-full ${channel.enabled ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                          <span className="text-xs text-gray-400">{channel.enabled ? '已配置' : '未配置'}</span>
                        </div>
                      </div>
                    </div>
                    
                    {!isEditing && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleTest(channel.channel_type, channel.id)}
                          disabled={testingId === channel.id}
                          className="p-2 text-gray-400 hover:text-cyan-400 hover:bg-dark-600 rounded-lg transition-colors disabled:opacity-50"
                          title="测试连接"
                        >
                          {testingId === channel.id ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                        </button>
                        <button
                          onClick={() => handleEdit(channel)}
                          className="p-2 text-gray-400 hover:text-claw-400 hover:bg-dark-600 rounded-lg transition-colors"
                          title="编辑配置"
                        >
                          <Edit2 size={16} />
                        </button>
                      </div>
                    )}
                  </div>

                  {testResult && testResult.id === channel.id && !isEditing && (
                    <div className={`mb-4 p-3 rounded-lg text-sm ${testResult.success ? 'bg-green-500/10 border border-green-500/20 text-green-400' : 'bg-red-500/10 border border-red-500/20 text-red-400'}`}>
                      <div className="flex items-center gap-2 mb-1">
                        {testResult.success ? <LinkIcon size={14} /> : <AlertCircle size={14} />}
                        <span className="font-medium">{testResult.message}</span>
                      </div>
                      {testResult.error && (
                        <p className="text-xs opacity-80 whitespace-pre-wrap mt-1">{testResult.error}</p>
                      )}
                    </div>
                  )}

                  {isEditing ? (
                    <div className="space-y-4 bg-dark-800 p-4 rounded-xl border border-dark-600">
                      {info.fields.length > 0 ? info.fields.map(field => (
                        <div key={field.key} className="space-y-1.5">
                          <label className="text-xs font-medium text-gray-300 flex justify-between">
                            {field.label}
                            {field.key.includes('Token') && <span className="text-amber-400 text-[10px]">敏感</span>}
                          </label>
                          {field.type === 'select' ? (
                            <select
                              value={editForm[field.key] || (
                                field.key === 'bridge' ? 'wechaty' :
                                field.key === 'puppet' ? 'wechat4u' :
                                field.key === 'autoAccept' ? 'false' :
                                'allowlist'
                              )}
                              onChange={e => setEditForm({ ...editForm, [field.key]: e.target.value })}
                              className="input-base py-2 text-sm"
                            >
                              {field.key === 'bridge' ? (
                                <>
                                  <option value="wechaty">Wechaty（推荐）</option>
                                  <option value="itchat">itchat（Python 原生）</option>
                                  <option value="wechat-bot">wechat-bot（Node.js）</option>
                                </>
                              ) : field.key === 'puppet' ? (
                                <>
                                  <option value="wechat4u">puppet-wechat4u（免费/网页协议）</option>
                                  <option value="padlocal">puppet-padlocal（付费/iPad协议）</option>
                                  <option value="xp">puppet-xp（Windows桌面协议）</option>
                                </>
                              ) : field.key === 'autoAccept' ? (
                                <>
                                  <option value="false">关闭</option>
                                  <option value="true">开启</option>
                                </>
                              ) : (
                                <>
                                  <option value="allowlist">仅白名单 (Allowlist)</option>
                                  <option value="everyone">所有人 (Everyone)</option>
                                </>
                              )}
                            </select>
                          ) : (
                            <input
                              type="text"
                              value={editForm[field.key] || ''}
                              onChange={e => setEditForm({ ...editForm, [field.key]: e.target.value })}
                              className="input-base py-2 text-sm"
                              placeholder={`输入 ${field.label}`}
                            />
                          )}
                          {field.desc && <p className="text-[10px] text-gray-500">{field.desc}</p>}
                        </div>
                      )) : (
                        <p className="text-sm text-gray-400 text-center py-4">此渠道主要通过命令行或手机扫码配置</p>
                      )}

                      {/* 微信渠道特殊引导提示 */}
                      {channel.channel_type === 'wechat' && (
                        <div className="mt-3 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs text-gray-400 space-y-1.5">
                          <p className="text-emerald-400 font-medium">微信接入说明</p>
                          <p>微信渠道当前主要承担通知桥接和后续管理入口，不参与主 LLM 号池路由。</p>
                          <p>微信机器人需要通过桥接服务接入，推荐使用 Wechaty + puppet-wechat4u 方案。</p>
                          <p>配置保存后，在终端执行 <code className="text-emerald-400 bg-dark-700 px-1 rounded">openclaw plugins enable wechat</code> 启用微信插件，然后用手机扫码完成登录。</p>
                          <p className="text-gray-500">提示：微信网页版登录需要已验证的微信号，新号可能无法使用网页协议。启用通知需同时设置 <code className="text-emerald-400 bg-dark-700 px-1 rounded">WECHAT_NOTIFY_ENABLED=true</code>。</p>
                        </div>
                      )}
                      
                      {/* WhatsApp 渠道特殊引导提示 */}
                      {channel.channel_type === 'whatsapp' && info.fields.length === 0 && (
                        <div className="mt-3 p-3 rounded-lg bg-green-500/5 border border-green-500/20 text-xs text-gray-400 space-y-1.5">
                          <p className="text-green-400 font-medium">WhatsApp 接入说明</p>
                          <p>WhatsApp 通过扫码登录接入，保存配置后在终端执行 <code className="text-green-400 bg-dark-700 px-1 rounded">openclaw channel login whatsapp</code>。</p>
                        </div>
                      )}
                      
                      <div className="flex justify-end gap-2 pt-2 mt-4 border-t border-dark-600">
                        <button
                          onClick={handleCancel}
                          className="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-dark-600 transition-colors"
                        >
                          取消
                        </button>
                        <button
                          onClick={() => handleSave(channel.id, channel.channel_type)}
                          disabled={saving}
                          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-claw-500 text-white hover:bg-claw-600 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                          保存
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(channel.config).filter(([k]) => k !== 'enabled').map(([key, value]) => (
                        <div key={key} className="flex justify-between items-center text-sm">
                          <span className="text-gray-400">{key}</span>
                          <span className="text-gray-200 truncate max-w-[200px]" title={String(value)}>
                            {String(value)}
                          </span>
                        </div>
                      ))}
                      {Object.keys(channel.config).filter(k => k !== 'enabled').length === 0 && (
                        <p className="text-sm text-gray-500 italic">默认配置</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </motion.div>
    </div>
  );
}

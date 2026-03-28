import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import {
  MessageSquare,
  Check,
  X,
  Loader2,
  ChevronRight,
  Eye,
  EyeOff,
  Play,
  QrCode,
  CheckCircle,
  XCircle,
  Download,
  Package,
  AlertTriangle,
  Trash2,
} from 'lucide-react';
import clsx from 'clsx';
import {
  api,
  type ClawbotBotMatrixEntry,
  type ManagedEndpointStatus,
  type ProjectContext,
} from '../../lib/tauri';
import {
  type ChannelConfig,
  type ChannelField as _ChannelField,
  type FeishuPluginStatus,
  type TestResult,
  CHANNEL_DEFINITIONS,
  maskToken,
  deriveTelegramUserId,
  getTelegramDefaultAccount,
  hasValidConfig,
} from './channelDefinitions';

export function Channels() {
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [configForm, setConfigForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(null);
  const [endpointStatus, setEndpointStatus] = useState<ManagedEndpointStatus[]>([]);
  const [clawbotBotMatrix, setClawbotBotMatrix] = useState<ClawbotBotMatrixEntry[]>([]);
  
  // 飞书插件状态
  const [feishuPluginStatus, setFeishuPluginStatus] = useState<FeishuPluginStatus | null>(null);
  const [feishuPluginLoading, setFeishuPluginLoading] = useState(false);
  const [feishuPluginInstalling, setFeishuPluginInstalling] = useState(false);
  
  // 跟踪哪些密码字段显示明文
  const [visiblePasswords, setVisiblePasswords] = useState<Set<string>>(new Set());
  
  // WhatsApp 登录轮询定时器引用（用于防泄漏）
  const whatsappPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const whatsappTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  // 组件卸载时清理 WhatsApp 定时器
  useEffect(() => {
    return () => {
      if (whatsappPollRef.current) {
        clearInterval(whatsappPollRef.current);
        whatsappPollRef.current = null;
      }
      if (whatsappTimeoutRef.current) {
        clearTimeout(whatsappTimeoutRef.current);
        whatsappTimeoutRef.current = null;
      }
    };
  }, []);

  const togglePasswordVisibility = (fieldKey: string) => {
    setVisiblePasswords((prev) => {
      const next = new Set(prev);
      if (next.has(fieldKey)) {
        next.delete(fieldKey);
      } else {
        next.add(fieldKey);
      }
      return next;
    });
  };
  
  // 检查飞书插件状态
  const checkFeishuPlugin = async () => {
    setFeishuPluginLoading(true);
    try {
      const status = await invoke<FeishuPluginStatus>('check_feishu_plugin');
      setFeishuPluginStatus(status);
    } catch (e) {
      console.error('检查飞书插件失败:', e);
      setFeishuPluginStatus({ installed: false, version: null, plugin_name: null });
    } finally {
      setFeishuPluginLoading(false);
    }
  };
  
  // 安装飞书插件
  const handleInstallFeishuPlugin = async () => {
    setFeishuPluginInstalling(true);
    try {
      const result = await invoke<string>('install_feishu_plugin');
      toast.success(result);
      // 刷新插件状态
      await checkFeishuPlugin();
    } catch (e) {
      toast.error('安装失败: ' + e);
    } finally {
      setFeishuPluginInstalling(false);
    }
  };
  
  // 显示清空确认
  const handleShowClearConfirm = () => {
    if (!selectedChannel) return;
    setShowClearConfirm(true);
  };
  
  // 执行清空渠道配置
  const handleClearConfig = async () => {
    if (!selectedChannel) return;
    
    const channel = channels.find((c) => c.id === selectedChannel);
    const channelName = channel ? CHANNEL_DEFINITIONS[channel.channel_type]?.name || channel.channel_type : selectedChannel;
    
    setShowClearConfirm(false);
    setClearing(true);
    try {
      await invoke('clear_channel_config', { channelId: selectedChannel });
      // 清空表单
      setConfigForm({});
      // 刷新列表
      await fetchChannels();
      setTestResult({
        success: true,
        message: `${channelName} 配置已清空`,
        error: null,
      });
    } catch (e) {
      setTestResult({
        success: false,
        message: '清空失败',
        error: String(e),
      });
    } finally {
      setClearing(false);
    }
  };
  
  // 快速测试
  const handleQuickTest = async () => {
    if (!selectedChannel) return;
    
    setTesting(true);
    setTestResult(null);
    
    try {
      const result = await invoke<{
        success: boolean;
        channel: string;
        message: string;
        error: string | null;
      }>('test_channel', { channelType: selectedChannel });
      
      setTestResult({
        success: result.success,
        message: result.message,
        error: result.error,
      });
    } catch (e) {
      setTestResult({
        success: false,
        message: '测试失败',
        error: String(e),
      });
    } finally {
      setTesting(false);
    }
  };
  
  // WhatsApp 扫码登录
  const handleWhatsAppLogin = async () => {
    setLoginLoading(true);
    
    // 先清理之前可能存在的定时器
    if (whatsappPollRef.current) {
      clearInterval(whatsappPollRef.current);
      whatsappPollRef.current = null;
    }
    if (whatsappTimeoutRef.current) {
      clearTimeout(whatsappTimeoutRef.current);
      whatsappTimeoutRef.current = null;
    }
    
    try {
      // 调用后端命令启动 WhatsApp 登录
      await invoke('start_channel_login', { channelType: 'whatsapp' });
      
      // 开始轮询检查登录状态
      whatsappPollRef.current = setInterval(async () => {
        try {
          const result = await invoke<{
            success: boolean;
            message: string;
          }>('test_channel', { channelType: 'whatsapp' });
          
          if (result.success) {
            // 登录成功，清理所有定时器
            if (whatsappPollRef.current) {
              clearInterval(whatsappPollRef.current);
              whatsappPollRef.current = null;
            }
            if (whatsappTimeoutRef.current) {
              clearTimeout(whatsappTimeoutRef.current);
              whatsappTimeoutRef.current = null;
            }
            setLoginLoading(false);
            // 刷新渠道列表
            await fetchChannels();
            setTestResult({
              success: true,
              message: 'WhatsApp 登录成功！',
              error: null,
            });
          }
        } catch (e) {
          console.error("[Channels] WhatsApp login poll failed:", e);
        }
      }, 3000); // 每3秒检查一次
      
      // 60秒后停止轮询
      whatsappTimeoutRef.current = setTimeout(() => {
        if (whatsappPollRef.current) {
          clearInterval(whatsappPollRef.current);
          whatsappPollRef.current = null;
        }
        whatsappTimeoutRef.current = null;
        setLoginLoading(false);
      }, 60000);
      
      toast.info('请在弹出的终端窗口中扫描二维码完成登录，登录成功后界面会自动更新');
    } catch (e) {
      toast.error('启动登录失败: ' + e);
      setLoginLoading(false);
    }
  };

  const fetchChannels = async () => {
    try {
      const result = await invoke<ChannelConfig[]>('get_channels_config');
      setChannels(result);
      return result;
    } catch (e) {
      console.error('获取渠道配置失败:', e);
      // Tauri invoke 不可用时，用静态定义构建默认渠道列表
      const fallback: ChannelConfig[] = Object.keys(CHANNEL_DEFINITIONS).map((key) => ({
        id: key,
        channel_type: key,
        enabled: false,
        config: {},
      }));
      setChannels(fallback);
      return fallback;
    }
  };

  useEffect(() => {
    const init = async () => {
      try {
        const result = await fetchChannels();
        try {
          const [context, endpoints, matrix] = await Promise.all([
            api.getProjectContext(),
            api.getManagedEndpointsStatus(),
            api.getClawbotBotMatrix(),
          ]);
          setProjectContext(context);
          setEndpointStatus(endpoints);
          setClawbotBotMatrix(matrix);
        } catch (e) {
          console.error("[Channels] Context/endpoint init failed:", e);
        }
        
        // 自动选择第一个已配置的渠道
        const configured = result.find((c) => c.enabled);
        if (configured) {
          handleChannelSelect(configured.id, result);
        }
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleChannelSelect = (channelId: string, channelList?: ChannelConfig[]) => {
    setSelectedChannel(channelId);
    setTestResult(null); // 清除测试结果
    
    const list = channelList || channels;
    const channel = list.find((c) => c.id === channelId);
    
    if (channel) {
      const form: Record<string, string> = {};

      const info = CHANNEL_DEFINITIONS[channel.channel_type];
      if (info) {
        const telegramDefault =
          channel.channel_type === 'telegram'
            ? getTelegramDefaultAccount(channel.config)
            : {};

        info.fields.forEach((field) => {
          if (field.key === 'userId' && channel.channel_type === 'telegram') {
            form[field.key] = deriveTelegramUserId(channel.config);
            return;
          }

          const raw = channel.config[field.key] ?? telegramDefault[field.key];
          if (typeof raw === 'boolean') {
            form[field.key] = raw ? 'true' : 'false';
          } else if (typeof raw === 'string' || typeof raw === 'number') {
            form[field.key] = String(raw);
          } else {
            form[field.key] = '';
          }
        });

        if (channel.channel_type === 'telegram') {
          if (!form.dmPolicy) form.dmPolicy = 'allowlist';
          if (!form.groupPolicy) form.groupPolicy = 'allowlist';
        }
      }

      setConfigForm(form);
      
      // 如果选择的是飞书渠道，检查插件状态
      if (channel.channel_type === 'feishu') {
        checkFeishuPlugin();
      }
    } else {
      setConfigForm({});
    }
  };

  const handleSave = async () => {
    if (!selectedChannel) return;
    
    setSaving(true);
    try {
      const channel = channels.find((c) => c.id === selectedChannel);
      if (!channel) return;

      const info = CHANNEL_DEFINITIONS[channel.channel_type];
      if (!info) return;
      
      const config: Record<string, unknown> = {
        ...channel.config,
      };

      info.fields.forEach((field) => {
        const raw = (configForm[field.key] || '').trim();

        if (field.key === 'userId' && channel.channel_type === 'telegram') {
          if (raw) {
            config.userId = raw;
            config.allowFrom = [raw];
            config.groupAllowFrom = [raw];
          } else {
            delete config.userId;
          }
          return;
        }

        if (!raw) {
          delete config[field.key];
          return;
        }

        if (raw === 'true') {
          config[field.key] = true;
        } else if (raw === 'false') {
          config[field.key] = false;
        } else {
          config[field.key] = raw;
        }
      });

      if (channel.channel_type === 'telegram') {
        const existingAccounts =
          config.accounts && typeof config.accounts === 'object' && !Array.isArray(config.accounts)
            ? { ...(config.accounts as Record<string, unknown>) }
            : {};
        const currentDefault =
          existingAccounts.default && typeof existingAccounts.default === 'object' && !Array.isArray(existingAccounts.default)
            ? { ...(existingAccounts.default as Record<string, unknown>) }
            : {};

        if (config.botToken) currentDefault.botToken = config.botToken;
        if (config.dmPolicy) currentDefault.dmPolicy = config.dmPolicy;
        if (config.groupPolicy) currentDefault.groupPolicy = config.groupPolicy;
        if (config.allowFrom) currentDefault.allowFrom = config.allowFrom;
        if (config.groupAllowFrom) currentDefault.groupAllowFrom = config.groupAllowFrom;

        existingAccounts.default = currentDefault;
        config.accounts = existingAccounts;

        if (!config.dmPolicy) config.dmPolicy = 'allowlist';
        if (!config.groupPolicy) config.groupPolicy = 'allowlist';
      }
      
      await invoke('save_channel_config', {
        channel: {
          ...channel,
          config,
        },
      });
      
      // 刷新列表
      await fetchChannels();
      
      toast.success('渠道配置已保存！');
    } catch (e) {
      console.error('保存失败:', e);
      toast.error('保存失败: ' + e);
    } finally {
      setSaving(false);
    }
  };

  const currentChannel = channels.find((c) => c.id === selectedChannel);
  const currentInfo = currentChannel ? CHANNEL_DEFINITIONS[currentChannel.channel_type] : null;

  const telegramDefaultConfig =
    currentChannel?.channel_type === 'telegram'
      ? getTelegramDefaultAccount(currentChannel.config)
      : {};

  const telegramMainUserId = currentChannel?.channel_type === 'telegram'
    ? deriveTelegramUserId(currentChannel.config)
    : '';

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-claw-500" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <div className="max-w-4xl">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* 渠道列表 */}
          <div className="md:col-span-1 space-y-2">
            <h3 className="text-sm font-medium text-gray-400 mb-3 px-1">
              消息渠道
            </h3>
            {channels.map((channel) => {
              const info = CHANNEL_DEFINITIONS[channel.channel_type] || {
                name: channel.channel_type,
                icon: MessageSquare,
                color: 'text-gray-400',
                fields: [],
              };
              const isSelected = selectedChannel === channel.id;
              const isConfigured = hasValidConfig(channel);
              const IconComponent = info.icon;
              
              return (
                <button
                  key={channel.id}
                  onClick={() => handleChannelSelect(channel.id)}
                  className={clsx(
                    'w-full flex items-center gap-3 p-4 rounded-xl border transition-all',
                    isSelected
                      ? 'bg-dark-600 border-claw-500'
                      : 'bg-dark-700 border-dark-500 hover:border-dark-400'
                  )}
                >
                  <div
                    className={clsx(
                      'w-10 h-10 rounded-lg flex items-center justify-center',
                      isConfigured ? 'bg-dark-500' : 'bg-dark-600'
                    )}
                  >
                    <span className={info.color}><IconComponent size={20} /></span>
                  </div>
                  <div className="flex-1 text-left">
                    <p
                      className={clsx(
                        'text-sm font-medium',
                        isSelected ? 'text-white' : 'text-gray-300'
                      )}
                    >
                      {info.name}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {isConfigured ? (
                        <>
                          <Check size={12} className="text-green-400" />
                          <span className="text-xs text-green-400">已配置</span>
                        </>
                      ) : (
                        <>
                          <X size={12} className="text-gray-500" />
                          <span className="text-xs text-gray-500">未配置</span>
                        </>
                      )}
                    </div>
                  </div>
                  <ChevronRight
                    size={16}
                    className={isSelected ? 'text-claw-400' : 'text-gray-600'}
                  />
                </button>
              );
            })}
          </div>

          {/* 配置面板 */}
          <div className="md:col-span-2">
            {currentChannel && currentInfo ? (
              <motion.div
                key={selectedChannel}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="bg-dark-700 rounded-2xl p-6 border border-dark-500"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center bg-dark-500', currentInfo.color)}>
                    <currentInfo.icon size={20} />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">
                      配置 {currentInfo.name}
                    </h3>
                    {currentInfo.helpText && (
                      <p className="text-xs text-gray-500">{currentInfo.helpText}</p>
                    )}
                  </div>
                </div>

                <div className="mb-4 p-3 bg-dark-600 rounded-lg border border-dark-500">
                  <p className="text-xs text-gray-400">项目路径: <span className="text-claw-400">{projectContext?.project_base_dir ?? '加载中...'}</span></p>
                  <p className="text-xs text-gray-400 mt-1">配置文件: <span className="text-claw-400">{projectContext?.config_file ?? '加载中...'}</span></p>
                  <p className="text-xs text-gray-400 mt-1">
                    关键链路状态:
                    <span className="ml-2 text-green-400">
                      {endpointStatus.filter((s) => s.healthy).length}
                    </span>
                    /
                    <span className="text-gray-300">{endpointStatus.length || 0}</span>
                    <span className="text-gray-500 ml-1">在线</span>
                  </p>
                </div>

                {currentChannel.channel_type === 'telegram' && (
                  <div className="mb-4 p-4 bg-dark-600 rounded-xl border border-dark-500">
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <p className="text-sm font-medium text-white">Telegram Bot 编组（7）</p>
                      <span className="text-xs text-gray-500">OpenClaw 1 + ClawBot 6</span>
                    </div>

                    <div className="space-y-2">
                      <div className="bg-dark-700 rounded-lg border border-dark-500 px-3 py-2">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm text-gray-200">OpenClaw 主 Bot</p>
                            <p className="text-xs text-gray-500 mt-0.5">@carven_OpenClaw_Bot</p>
                            <p className="text-xs text-gray-500 mt-0.5">
                              策略: DM {configForm.dmPolicy || 'allowlist'} · Group {configForm.groupPolicy || 'allowlist'}
                            </p>
                            <p className="text-xs text-gray-500 mt-0.5">User ID: {telegramMainUserId || '未设置'}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-xs text-gray-500">Token</p>
                            <p className="text-xs text-gray-300">
                              {maskToken(String(currentChannel.config.botToken || telegramDefaultConfig.botToken || '')) || '未配置'}
                            </p>
                          </div>
                        </div>
                      </div>

                      {clawbotBotMatrix.map((bot) => (
                        <div key={bot.id} className="bg-dark-700 rounded-lg border border-dark-500 px-3 py-2">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm text-gray-200">{bot.name}</p>
                              <p className="text-xs text-gray-500 mt-0.5">@{bot.username || '-'}</p>
                              <p className="text-xs text-gray-500 mt-0.5">路由: {bot.route_provider}/{bot.route_model}</p>
                            </div>
                            <div className="text-right">
                              <p className="text-xs text-gray-500">Token</p>
                              <p className="text-xs text-gray-300">{bot.token_masked || '未配置'}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 飞书插件状态提示 */}
                {currentChannel.channel_type === 'feishu' && (
                  <div className="mb-4">
                    {feishuPluginLoading ? (
                      <div className="p-4 bg-dark-600 rounded-xl border border-dark-500 flex items-center gap-3">
                        <Loader2 size={20} className="animate-spin text-gray-400" />
                        <span className="text-gray-400">正在检查飞书插件状态...</span>
                      </div>
                    ) : feishuPluginStatus?.installed ? (
                      <div className="p-4 bg-green-500/10 rounded-xl border border-green-500/30 flex items-center gap-3">
                        <Package size={20} className="text-green-400" />
                        <div className="flex-1">
                          <p className="text-green-400 font-medium">飞书插件已安装</p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            {feishuPluginStatus.plugin_name || '@m1heng-clawd/feishu'}
                            {feishuPluginStatus.version && ` v${feishuPluginStatus.version}`}
                          </p>
                        </div>
                        <CheckCircle size={16} className="text-green-400" />
                      </div>
                    ) : (
                      <div className="p-4 bg-amber-500/10 rounded-xl border border-amber-500/30">
                        <div className="flex items-start gap-3">
                          <AlertTriangle size={20} className="text-amber-400 mt-0.5" />
                          <div className="flex-1">
                            <p className="text-amber-400 font-medium">需要安装飞书插件</p>
                            <p className="text-xs text-gray-400 mt-1">
                              飞书渠道需要先安装 @m1heng-clawd/feishu 插件才能使用。
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                onClick={handleInstallFeishuPlugin}
                                disabled={feishuPluginInstalling}
                                className="btn-primary flex items-center gap-2 text-sm py-2"
                              >
                                {feishuPluginInstalling ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : (
                                  <Download size={14} />
                                )}
                                {feishuPluginInstalling ? '安装中...' : '一键安装插件'}
                              </button>
                              <button
                                onClick={checkFeishuPlugin}
                                disabled={feishuPluginLoading}
                                className="btn-secondary flex items-center gap-2 text-sm py-2"
                              >
                                刷新状态
                              </button>
                            </div>
                            <p className="text-xs text-gray-500 mt-2">
                              或手动执行: <code className="px-1.5 py-0.5 bg-dark-600 rounded text-gray-400">openclaw plugins install @m1heng-clawd/feishu</code>
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <div className="space-y-4">
                  {currentInfo.fields.map((field) => (
                    <div key={field.key}>
                      <label className="block text-sm text-gray-400 mb-2">
                        {field.label}
                        {field.required && <span className="text-red-400 ml-1">*</span>}
                        {configForm[field.key] && (
                          <span className="ml-2 text-green-500 text-xs">✓</span>
                        )}
                      </label>
                      
                      {field.type === 'select' ? (
                        <select
                          value={configForm[field.key] || ''}
                          onChange={(e) =>
                            setConfigForm({ ...configForm, [field.key]: e.target.value })
                          }
                          className="input-base"
                        >
                          <option value="">请选择...</option>
                          {field.options?.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : field.type === 'password' ? (
                        <div className="relative">
                          <input
                            type={visiblePasswords.has(field.key) ? 'text' : 'password'}
                            value={configForm[field.key] || ''}
                            onChange={(e) =>
                              setConfigForm({ ...configForm, [field.key]: e.target.value })
                            }
                            placeholder={field.placeholder}
                            className="input-base pr-10"
                          />
                          <button
                            type="button"
                            onClick={() => togglePasswordVisibility(field.key)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors"
                            title={visiblePasswords.has(field.key) ? '隐藏' : '显示'}
                          >
                            {visiblePasswords.has(field.key) ? (
                              <EyeOff size={18} />
                            ) : (
                              <Eye size={18} />
                            )}
                          </button>
                        </div>
                      ) : (
                        <input
                          type={field.type}
                          value={configForm[field.key] || ''}
                          onChange={(e) =>
                            setConfigForm({ ...configForm, [field.key]: e.target.value })
                          }
                          placeholder={field.placeholder}
                          className="input-base"
                        />
                      )}
                    </div>
                  ))}

                  {/* WhatsApp 特殊处理：扫码登录按钮 */}
                  {currentChannel.channel_type === 'whatsapp' && (
                    <div className="p-4 bg-green-500/10 rounded-xl border border-green-500/30">
                      <div className="flex items-center gap-3 mb-3">
                        <QrCode size={24} className="text-green-400" />
                        <div>
                          <p className="text-white font-medium">扫码登录</p>
                          <p className="text-xs text-gray-400">WhatsApp 需要扫描二维码登录</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={handleWhatsAppLogin}
                          disabled={loginLoading}
                          className="flex-1 btn-secondary flex items-center justify-center gap-2"
                        >
                          {loginLoading ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <QrCode size={16} />
                          )}
                          {loginLoading ? '等待登录...' : '启动扫码登录'}
                        </button>
                        <button
                          onClick={async () => {
                            await fetchChannels();
                            handleQuickTest();
                          }}
                          disabled={testing}
                          className="btn-secondary flex items-center justify-center gap-2 px-4"
                          title="刷新状态"
                        >
                          {testing ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <Check size={16} />
                          )}
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-2 text-center">
                        登录成功后点击右侧按钮刷新状态，或运行: openclaw channels login --channel whatsapp
                      </p>
                    </div>
                  )}

                  {/* 操作按钮 */}
                  <div className="pt-4 border-t border-dark-500 flex flex-wrap items-center gap-3">
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="btn-primary flex items-center gap-2"
                    >
                      {saving ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Check size={16} />
                      )}
                      保存配置
                    </button>
                    
                    {/* 快速测试按钮 */}
                    <button
                      onClick={handleQuickTest}
                      disabled={testing}
                      className="btn-secondary flex items-center gap-2"
                    >
                      {testing ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Play size={16} />
                      )}
                      快速测试
                    </button>
                    
                    {/* 清空配置按钮 */}
                    {!showClearConfirm ? (
                      <button
                        onClick={handleShowClearConfirm}
                        disabled={clearing}
                        className="btn-secondary flex items-center gap-2 text-red-400 hover:text-red-300 hover:border-red-500/50"
                      >
                        {clearing ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <Trash2 size={16} />
                        )}
                        清空配置
                      </button>
                    ) : (
                      <div className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 rounded-lg border border-red-500/50">
                        <span className="text-sm text-red-300">确定清空？</span>
                        <button
                          onClick={handleClearConfig}
                          className="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                        >
                          确定
                        </button>
                        <button
                          onClick={() => setShowClearConfirm(false)}
                          className="px-2 py-1 text-xs bg-dark-600 text-gray-300 rounded hover:bg-dark-500 transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    )}
                  </div>
                  
                  {/* 测试结果显示 */}
                  {testResult && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={clsx(
                        'mt-4 p-4 rounded-xl flex items-start gap-3',
                        testResult.success ? 'bg-green-500/10' : 'bg-red-500/10'
                      )}
                    >
                      {testResult.success ? (
                        <CheckCircle size={20} className="text-green-400 mt-0.5" />
                      ) : (
                        <XCircle size={20} className="text-red-400 mt-0.5" />
                      )}
                      <div className="flex-1">
                        <p className={clsx(
                          'font-medium',
                          testResult.success ? 'text-green-400' : 'text-red-400'
                        )}>
                          {testResult.success ? '测试成功' : '测试失败'}
                        </p>
                        <p className="text-sm text-gray-400 mt-1">{testResult.message}</p>
                        {testResult.error && (
                          <p className="text-xs text-red-300 mt-2 whitespace-pre-wrap">
                            {testResult.error}
                          </p>
                        )}
                      </div>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                <p>选择左侧渠道进行配置</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

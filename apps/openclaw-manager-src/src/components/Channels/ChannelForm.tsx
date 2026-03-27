/**
 * 渠道编辑表单组件
 * 包含配置编辑、保存、测试、清空等所有表单操作
 */
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import {
  Check,
  Loader2,
  Eye,
  EyeOff,
  Play,
  CheckCircle,
  XCircle,
  Download,
  Package,
  AlertTriangle,
  Trash2,
} from 'lucide-react';
import clsx from 'clsx';
import type {
  ClawbotBotMatrixEntry,
  ManagedEndpointStatus,
  ProjectContext,
} from '../../lib/tauri';
import {
  type ChannelConfig,
  type ChannelInfoDef,
  type FeishuPluginStatus,
  type TestResult,
  maskToken,
  deriveTelegramUserId,
  getTelegramDefaultAccount,
} from './channelDefinitions';
import { WhatsAppLogin } from './WhatsAppLogin';

interface ChannelFormProps {
  /** 当前选中的渠道配置 */
  channel: ChannelConfig;
  /** 当前渠道的定义信息 */
  channelInfo: ChannelInfoDef;
  /** 项目上下文（显示路径等信息） */
  projectContext: ProjectContext | null;
  /** 端点状态列表 */
  endpointStatus: ManagedEndpointStatus[];
  /** Telegram Bot 编组矩阵 */
  clawbotBotMatrix: ClawbotBotMatrixEntry[];
  /** 刷新渠道列表的回调 */
  onRefresh: () => Promise<void>;
}

export function ChannelForm({
  channel,
  channelInfo: info,
  projectContext,
  endpointStatus,
  clawbotBotMatrix,
  onRefresh,
}: ChannelFormProps) {
  // ─── 表单状态 ───────────────────────────────────────
  const [configForm, setConfigForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [clearing, setClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [visiblePasswords, setVisiblePasswords] = useState<Set<string>>(new Set());

  // 飞书插件状态
  const [feishuPluginStatus, setFeishuPluginStatus] = useState<FeishuPluginStatus | null>(null);
  const [feishuPluginLoading, setFeishuPluginLoading] = useState(false);
  const [feishuPluginInstalling, setFeishuPluginInstalling] = useState(false);

  // ─── 渠道切换时初始化表单 ─────────────────────────────
  useEffect(() => {
    const form: Record<string, string> = {};
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

    setConfigForm(form);
    setTestResult(null);
    setShowClearConfirm(false);
    setVisiblePasswords(new Set());

    // 飞书渠道：检查插件状态
    if (channel.channel_type === 'feishu') {
      checkFeishuPlugin();
    }
  }, [channel.id]);

  // ─── 密码可见性切换 ──────────────────────────────────
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

  // ─── 飞书插件相关 ───────────────────────────────────
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

  const handleInstallFeishuPlugin = async () => {
    setFeishuPluginInstalling(true);
    try {
      const result = await invoke<string>('install_feishu_plugin');
      toast.success(result);
      await checkFeishuPlugin();
    } catch (e) {
      toast.error('安装失败: ' + e);
    } finally {
      setFeishuPluginInstalling(false);
    }
  };

  // ─── 保存配置 ───────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
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

      await onRefresh();
      toast.success('渠道配置已保存！');
    } catch (e) {
      console.error('保存失败:', e);
      toast.error('保存失败: ' + e);
    } finally {
      setSaving(false);
    }
  };

  // ─── 快速测试 ───────────────────────────────────────
  const handleQuickTest = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      const result = await invoke<{
        success: boolean;
        channel: string;
        message: string;
        error: string | null;
      }>('test_channel', { channelType: channel.id });

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

  // ─── 清空配置 ───────────────────────────────────────
  const handleClearConfig = async () => {
    const channelName = info.name || channel.channel_type;

    setShowClearConfirm(false);
    setClearing(true);
    try {
      await invoke('clear_channel_config', { channelId: channel.id });
      setConfigForm({});
      await onRefresh();
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

  // ─── 派生数据 ───────────────────────────────────────
  const telegramDefaultConfig =
    channel.channel_type === 'telegram'
      ? getTelegramDefaultAccount(channel.config)
      : {};

  const telegramMainUserId =
    channel.channel_type === 'telegram'
      ? deriveTelegramUserId(channel.config)
      : '';

  const Icon = info.icon;

  // ─── 渲染 ─────────────────────────────────────────
  return (
    <motion.div
      key={channel.id}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="bg-dark-700 rounded-2xl p-6 border border-dark-500"
    >
      {/* 标题栏 */}
      <div className="flex items-center gap-3 mb-4">
        <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center bg-dark-500', info.color)}>
          <Icon size={20} />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">
            配置 {info.name}
          </h3>
          {info.helpText && (
            <p className="text-xs text-gray-500">{info.helpText}</p>
          )}
        </div>
      </div>

      {/* 项目/端点信息 */}
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

      {/* Telegram Bot 编组 */}
      {channel.channel_type === 'telegram' && (
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
                    {maskToken(String(channel.config.botToken || telegramDefaultConfig.botToken || '')) || '未配置'}
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
      {channel.channel_type === 'feishu' && (
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

      {/* 配置字段 */}
      <div className="space-y-4">
        {info.fields.map((field) => (
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

        {/* WhatsApp 扫码登录 */}
        {channel.channel_type === 'whatsapp' && (
          <WhatsAppLogin
            onRefresh={onRefresh}
            onTestResult={setTestResult}
            testing={testing}
            onQuickTest={handleQuickTest}
          />
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
              onClick={() => setShowClearConfirm(true)}
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
  );
}

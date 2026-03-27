/**
 * 渠道定义 — 纯数据文件
 * 包含所有渠道的配置字段、类型定义和工具函数
 * 不含任何 React 组件
 */
import type { LucideIcon } from 'lucide-react';
import {
  MessageCircle,
  Hash,
  Slack,
  MessagesSquare,
  MessageSquare,
  Apple,
  Bell,
} from 'lucide-react';

// ─── 类型定义 ───────────────────────────────────────────

export interface FeishuPluginStatus {
  installed: boolean;
  version: string | null;
  plugin_name: string | null;
}

export interface ChannelConfig {
  id: string;
  channel_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

/** 渠道配置表单字段 */
export interface ChannelField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'select';
  placeholder?: string;
  options?: { value: string; label: string }[];
  required?: boolean;
}

export interface TestResult {
  success: boolean;
  message: string;
  error: string | null;
}

/** 渠道信息定义（图标使用组件引用，渲染时再实例化） */
export interface ChannelInfoDef {
  name: string;
  icon: LucideIcon;
  color: string;
  fields: ChannelField[];
  helpText?: string;
}

// ─── 渠道配置数据 ───────────────────────────────────────

export const CHANNEL_DEFINITIONS: Record<string, ChannelInfoDef> = {
  telegram: {
    name: 'Telegram',
    icon: MessageCircle,
    color: 'text-blue-400',
    fields: [
      { key: 'botToken', label: 'Bot Token', type: 'password', placeholder: '从 @BotFather 获取', required: true },
      { key: 'userId', label: 'User ID', type: 'text', placeholder: '你的 Telegram User ID', required: true },
      { key: 'dmPolicy', label: '私聊策略', type: 'select', options: [
        { value: 'pairing', label: '配对模式' },
        { value: 'open', label: '开放模式' },
        { value: 'disabled', label: '禁用' },
      ]},
      { key: 'groupPolicy', label: '群组策略', type: 'select', options: [
        { value: 'allowlist', label: '白名单' },
        { value: 'open', label: '开放' },
        { value: 'disabled', label: '禁用' },
      ]},
    ],
    helpText: '1. 搜索 @BotFather 发送 /newbot 获取 Token  2. 搜索 @userinfobot 获取 User ID',
  },
  discord: {
    name: 'Discord',
    icon: Hash,
    color: 'text-indigo-400',
    fields: [
      { key: 'botToken', label: 'Bot Token', type: 'password', placeholder: 'Discord Bot Token', required: true },
      { key: 'testChannelId', label: '测试 Channel ID', type: 'text', placeholder: '用于发送测试消息的频道 ID (可选)' },
      { key: 'dmPolicy', label: '私聊策略', type: 'select', options: [
        { value: 'pairing', label: '配对模式' },
        { value: 'open', label: '开放模式' },
        { value: 'disabled', label: '禁用' },
      ]},
    ],
    helpText: '从 Discord Developer Portal 获取，开启开发者模式可复制 Channel ID',
  },
  slack: {
    name: 'Slack',
    icon: Slack,
    color: 'text-purple-400',
    fields: [
      { key: 'botToken', label: 'Bot Token', type: 'password', placeholder: 'xoxb-...', required: true },
      { key: 'appToken', label: 'App Token', type: 'password', placeholder: 'xapp-...' },
      { key: 'testChannelId', label: '测试 Channel ID', type: 'text', placeholder: '用于发送测试消息的频道 ID (可选)' },
    ],
    helpText: '从 Slack API 后台获取，Channel ID 可从频道详情复制',
  },
  feishu: {
    name: '飞书',
    icon: MessagesSquare,
    color: 'text-blue-500',
    fields: [
      { key: 'appId', label: 'App ID', type: 'text', placeholder: '飞书应用 App ID', required: true },
      { key: 'appSecret', label: 'App Secret', type: 'password', placeholder: '飞书应用 App Secret', required: true },
      { key: 'testChatId', label: '测试 Chat ID', type: 'text', placeholder: '用于发送测试消息的群聊/用户 ID (可选)' },
      { key: 'connectionMode', label: '连接模式', type: 'select', options: [
        { value: 'websocket', label: 'WebSocket (推荐)' },
        { value: 'webhook', label: 'Webhook' },
      ]},
      { key: 'domain', label: '部署区域', type: 'select', options: [
        { value: 'feishu', label: '国内 (feishu.cn)' },
        { value: 'lark', label: '海外 (larksuite.com)' },
      ]},
      { key: 'requireMention', label: '需要 @提及', type: 'select', options: [
        { value: 'true', label: '是' },
        { value: 'false', label: '否' },
      ]},
    ],
    helpText: '从飞书开放平台获取凭证，Chat ID 可从群聊设置中获取',
  },
  imessage: {
    name: 'iMessage',
    icon: Apple,
    color: 'text-green-400',
    fields: [
      { key: 'dmPolicy', label: '私聊策略', type: 'select', options: [
        { value: 'pairing', label: '配对模式' },
        { value: 'open', label: '开放模式' },
        { value: 'disabled', label: '禁用' },
      ]},
      { key: 'groupPolicy', label: '群组策略', type: 'select', options: [
        { value: 'allowlist', label: '白名单' },
        { value: 'open', label: '开放' },
        { value: 'disabled', label: '禁用' },
      ]},
    ],
    helpText: '仅支持 macOS，需要授权消息访问权限',
  },
  whatsapp: {
    name: 'WhatsApp',
    icon: MessageCircle,
    color: 'text-green-500',
    fields: [
      { key: 'dmPolicy', label: '私聊策略', type: 'select', options: [
        { value: 'pairing', label: '配对模式' },
        { value: 'open', label: '开放模式' },
        { value: 'disabled', label: '禁用' },
      ]},
      { key: 'groupPolicy', label: '群组策略', type: 'select', options: [
        { value: 'allowlist', label: '白名单' },
        { value: 'open', label: '开放' },
        { value: 'disabled', label: '禁用' },
      ]},
    ],
    helpText: '需要扫描二维码登录，运行: openclaw channels login --channel whatsapp',
  },
  wechat: {
    name: '微信',
    icon: MessageSquare,
    color: 'text-green-600',
    fields: [
      { key: 'appId', label: 'App ID', type: 'text', placeholder: '微信开放平台 App ID' },
      { key: 'appSecret', label: 'App Secret', type: 'password', placeholder: '微信开放平台 App Secret' },
    ],
    helpText: '微信公众号/企业微信配置',
  },
  dingtalk: {
    name: '钉钉',
    icon: Bell,
    color: 'text-blue-600',
    fields: [
      { key: 'appKey', label: 'App Key', type: 'text', placeholder: '钉钉应用 App Key' },
      { key: 'appSecret', label: 'App Secret', type: 'password', placeholder: '钉钉应用 App Secret' },
    ],
    helpText: '从钉钉开放平台获取',
  },
};

// ─── 工具函数 ───────────────────────────────────────────

/** 脱敏显示 Token（前4后4，中间省略） */
export const maskToken = (value: string): string => {
  if (!value) return '';
  if (value.length <= 8) return '****';
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
};

/** 从 Telegram 配置中提取主 User ID（兼容多种存储格式） */
export const deriveTelegramUserId = (config: Record<string, unknown>): string => {
  const direct = config.userId;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();

  const allowFrom = config.allowFrom;
  if (Array.isArray(allowFrom) && allowFrom.length > 0) {
    const first = allowFrom[0];
    if (typeof first === 'string' && first.trim()) return first.trim();
  }
  if (typeof allowFrom === 'string' && allowFrom.trim()) {
    return allowFrom
      .split(',')
      .map((item) => item.trim())
      .find((item) => !!item) || '';
  }

  const accounts = config.accounts;
  if (accounts && typeof accounts === 'object' && !Array.isArray(accounts)) {
    const def = (accounts as Record<string, unknown>).default;
    if (def && typeof def === 'object' && !Array.isArray(def)) {
      const defCfg = def as Record<string, unknown>;
      const defAllowFrom = defCfg.allowFrom;
      if (Array.isArray(defAllowFrom) && defAllowFrom.length > 0) {
        const first = defAllowFrom[0];
        if (typeof first === 'string' && first.trim()) return first.trim();
      }
      if (typeof defAllowFrom === 'string' && defAllowFrom.trim()) {
        return defAllowFrom
          .split(',')
          .map((item) => item.trim())
          .find((item) => !!item) || '';
      }
    }
  }

  return '';
};

/** 获取 Telegram accounts.default 子配置 */
export const getTelegramDefaultAccount = (config: Record<string, unknown>): Record<string, unknown> => {
  const accounts = config.accounts;
  if (!accounts || typeof accounts !== 'object' || Array.isArray(accounts)) {
    return {};
  }
  const def = (accounts as Record<string, unknown>).default;
  if (!def || typeof def !== 'object' || Array.isArray(def)) {
    return {};
  }
  return def as Record<string, unknown>;
};

/** 检查渠道是否有有效配置（至少一个必填字段已填写） */
export const hasValidConfig = (channel: ChannelConfig): boolean => {
  const info = CHANNEL_DEFINITIONS[channel.channel_type];
  if (!info) return channel.enabled;

  const requiredFields = info.fields.filter((f) => f.required);
  if (requiredFields.length === 0) return channel.enabled;

  return requiredFields.some((field) => {
    const value = channel.config[field.key];
    return value !== undefined && value !== null && value !== '';
  });
};

/** 获取渠道信息（带 fallback 默认值） */
export const getChannelInfo = (channelType: string): ChannelInfoDef => {
  return CHANNEL_DEFINITIONS[channelType] || {
    name: channelType,
    icon: MessageSquare,
    color: 'text-gray-400',
    fields: [],
  };
};

/**
 * ControlCenter 常量与工具函数
 *
 * 从 index.tsx (882行) 抽取，降低单文件复杂度。
 */
import type {
  ClawbotRuntimeConfig,
  ManagedServiceAction,
} from '../../lib/tauri';

export const ACTION_LABEL: Record<ManagedServiceAction, string> = {
  start: '启动',
  stop: '停止',
  restart: '重启',
};

/** 配置字段的中文标签、描述和占位符映射 */
export const CONFIG_FIELD_META: Record<string, { label: string; hint?: string; placeholder?: string }> = {
  G4F_BASE_URL: {
    label: '🏷️ 免费模型代理地址 (G4F)',
    hint: '连接 G4F 免费模型的 API 地址',
    placeholder: '默认: http://localhost:1337/v1',
  },
  KIRO_BASE_URL: {
    label: '🏷️ Kiro 模型代理地址',
    hint: '连接 Kiro 模型网关的 API 地址',
    placeholder: '默认: http://localhost:8080/v1',
  },
  IBKR_HOST: {
    label: '🏷️ IBKR 券商交易地址',
    hint: 'IB Gateway / TWS 的连接地址',
    placeholder: '默认: 127.0.0.1',
  },
  IBKR_PORT: {
    label: '🏷️ IBKR 交易端口',
    hint: 'IB Gateway 模拟盘 4002 / 实盘 4001',
    placeholder: '默认: 4002',
  },
  IBKR_ACCOUNT: {
    label: '🏷️ IBKR 账户名',
    hint: 'Interactive Brokers 的账户 ID',
    placeholder: '例如: DU1234567',
  },
  IBKR_BUDGET: {
    label: '🏷️ IBKR 单日预算 (USD)',
    hint: '每日最大交易金额限制，防止超额下单',
    placeholder: '例如: 1000',
  },
  IBKR_AUTOSTART: {
    label: '🏷️ IBKR 自动启动',
    hint: '全部启动/重启时是否自动拉起 IB Gateway',
  },
  IBKR_START_CMD: {
    label: '🏷️ IBKR 启动命令',
    hint: '自定义启动 IB Gateway 的系统命令',
    placeholder: '默认: open -a "IB Gateway"',
  },
  IBKR_STOP_CMD: {
    label: '🏷️ IBKR 停止命令',
    hint: '自定义停止 IB Gateway 的系统命令',
    placeholder: '默认: pkill -f "IB Gateway" || pkill -f "Trader Workstation" || true',
  },
  NOTIFY_CHAT_ID: {
    label: '🏷️ 通知群/频道 ID',
    hint: 'Telegram 群组或频道的 Chat ID，用于接收系统通知',
    placeholder: '例如: -1001234567890',
  },
};

export const getFieldLabel = (key: string): string =>
  CONFIG_FIELD_META[key]?.label ?? key;

export const getFieldHint = (key: string): string | undefined =>
  CONFIG_FIELD_META[key]?.hint;

export const getFieldPlaceholder = (key: string): string | undefined =>
  CONFIG_FIELD_META[key]?.placeholder;

export const DEFAULT_RUNTIME_CONFIG: ClawbotRuntimeConfig = {
  G4F_BASE_URL: '',
  KIRO_BASE_URL: '',
  IBKR_HOST: '',
  IBKR_PORT: '',
  IBKR_ACCOUNT: '',
  IBKR_BUDGET: '',
  IBKR_AUTOSTART: 'true',
  IBKR_START_CMD: '',
  IBKR_STOP_CMD: '',
  NOTIFY_CHAT_ID: '',
};

export const CLAWBOT_PIPELINE_LABELS = [
  'ai.openclaw.g4f',
  'ai.openclaw.kiro-gateway',
  'ai.openclaw.clawbot-agent',
];

export const DEFAULT_LOG_LABEL = 'ai.openclaw.clawbot-agent';

export const getLogLineClass = (line: string) => {
  if (line.includes('ERROR') || line.includes('Error') || line.includes('error') || line.includes('Traceback')) {
    return 'text-red-400';
  }
  if (line.includes('WARN') || line.includes('Warn') || line.includes('warning')) {
    return 'text-amber-400';
  }
  return 'text-gray-400';
};

export const USAGE_META_KEYS = new Set(['provider', 'name', 'id', 'accountId', 'account', 'source']);

export const getUsageProviderName = (provider: Record<string, unknown>) => {
  const candidates = ['provider', 'name', 'id', 'accountId'];
  for (const key of candidates) {
    const value = provider[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return 'unknown-provider';
};

export const getUsageProviderDetails = (provider: Record<string, unknown>) =>
  Object.entries(provider)
    .filter(([key, value]) => !USAGE_META_KEYS.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'))
    .slice(0, 6)
    .map(([key, value]) => `${key}: ${String(value)}`);

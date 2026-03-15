import { invoke } from '@tauri-apps/api/core';
import { apiLogger } from './logger';

// 检查是否在 Tauri 环境中运行
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

// 带日志的 invoke 封装（自动检查 Tauri 环境）
async function invokeWithLog<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri()) {
    throw new Error('不在 Tauri 环境中运行，请通过 Tauri 应用启动');
  }
  apiLogger.apiCall(cmd, args);
  try {
    const result = await invoke<T>(cmd, args);
    apiLogger.apiResponse(cmd, result);
    return result;
  } catch (error) {
    apiLogger.apiError(cmd, error);
    throw error;
  }
}

// 服务状态
export interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
  uptime_seconds: number | null;
  memory_mb: number | null;
  cpu_percent: number | null;
}

// 系统信息
export interface SystemInfo {
  os: string;
  os_version: string;
  arch: string;
  openclaw_installed: boolean;
  openclaw_version: string | null;
  node_version: string | null;
  config_dir: string;
}

// AI Provider 选项（旧版兼容）
export interface AIProviderOption {
  id: string;
  name: string;
  icon: string;
  default_base_url: string | null;
  models: AIModelOption[];
  requires_api_key: boolean;
}

export interface AIModelOption {
  id: string;
  name: string;
  description: string | null;
  recommended: boolean;
}

// 官方 Provider 预设
export interface OfficialProvider {
  id: string;
  name: string;
  icon: string;
  default_base_url: string | null;
  api_type: string;
  suggested_models: SuggestedModel[];
  requires_api_key: boolean;
  docs_url: string | null;
}

export interface SuggestedModel {
  id: string;
  name: string;
  description: string | null;
  context_window: number | null;
  max_tokens: number | null;
  recommended: boolean;
}

// 已配置的 Provider
export interface ConfiguredProvider {
  name: string;
  base_url: string;
  api_key_masked: string | null;
  has_api_key: boolean;
  models: ConfiguredModel[];
}

export interface ConfiguredModel {
  full_id: string;
  id: string;
  name: string;
  api_type: string | null;
  context_window: number | null;
  max_tokens: number | null;
  is_primary: boolean;
}

// AI 配置概览
export interface AIConfigOverview {
  primary_model: string | null;
  configured_providers: ConfiguredProvider[];
  available_models: string[];
}

// 模型配置
export interface ModelConfig {
  id: string;
  name: string;
  api: string | null;
  input: string[];
  context_window: number | null;
  max_tokens: number | null;
  reasoning: boolean | null;
  cost: { input: number; output: number; cache_read: number; cache_write: number } | null;
}

// 渠道配置
export interface ChannelConfig {
  id: string;
  channel_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

// 诊断结果
export interface DiagnosticResult {
  name: string;
  passed: boolean;
  message: string;
  suggestion: string | null;
}

// AI 测试结果
export interface AITestResult {
  success: boolean;
  provider: string;
  model: string;
  response: string | null;
  error: string | null;
  latency_ms: number | null;
}

export interface ManagedServiceStatus {
  label: string;
  name: string;
  running: boolean;
  pid: number | null;
  plist_path: string;
}

export interface ManagedEndpointStatus {
  id: string;
  name: string;
  address: string;
  healthy: boolean;
  error: string | null;
}

export type ManagedServiceAction = 'start' | 'stop' | 'restart';

export interface ClawbotRuntimeConfig {
  G4F_BASE_URL: string;
  KIRO_BASE_URL: string;
  IBKR_HOST: string;
  IBKR_PORT: string;
  IBKR_ACCOUNT: string;
  IBKR_BUDGET: string;
  IBKR_AUTOSTART: string;
  IBKR_START_CMD: string;
  IBKR_STOP_CMD: string;
  NOTIFY_CHAT_ID: string;
}

export interface ClawbotBotMatrixEntry {
  id: string;
  name: string;
  token_key: string;
  username_key: string;
  username: string;
  token_configured: boolean;
  token_masked: string | null;
  route_provider: string;
  route_model: string;
  route_base_url: string;
  ready: boolean;
}

export interface OpenclawUsageSnapshot {
  updatedAt?: number;
  providers: Record<string, unknown>[];
}

export interface IdentitySettings {
  bot_name: string;
  user_name: string;
  timezone: string;
}

export interface SecuritySettings {
  enable_whitelist: boolean;
  allow_file_access: boolean;
}

export interface AppSettings {
  identity: IdentitySettings;
  security: SecuritySettings;
}

export interface ProjectContext {
  project_name: string;
  project_base_dir: string;
  workspace_dir: string;
  config_dir: string;
  config_file: string;
  env_file: string;
  identity_file: string;
  user_file: string;
  settings_file: string;
}

// API 封装（带日志）
export const api = {
  // 服务管理
  getServiceStatus: () => invokeWithLog<ServiceStatus>('get_service_status'),
  startService: () => invokeWithLog<string>('start_service'),
  stopService: () => invokeWithLog<string>('stop_service'),
  restartService: () => invokeWithLog<string>('restart_service'),
  getLogs: (lines?: number) => invokeWithLog<string[]>('get_logs', { lines }),

  // 系统信息
  getSystemInfo: () => invokeWithLog<SystemInfo>('get_system_info'),
  checkOpenclawInstalled: () => invokeWithLog<boolean>('check_openclaw_installed'),
  getOpenclawVersion: () => invokeWithLog<string | null>('get_openclaw_version'),

  // 配置管理
  getConfig: () => invokeWithLog<unknown>('get_config'),
  saveConfig: (config: unknown) => invokeWithLog<string>('save_config', { config }),
  getEnvValue: (key: string) => invokeWithLog<string | null>('get_env_value', { key }),
  saveEnvValue: (key: string, value: string) =>
    invokeWithLog<string>('save_env_value', { key, value }),
  getProjectContext: () => invokeWithLog<ProjectContext>('get_project_context'),
  getAppSettings: () => invokeWithLog<AppSettings>('get_app_settings'),
  saveAppSettings: (settings: AppSettings) =>
    invokeWithLog<string>('save_app_settings', { settings }),
  openMacOSFullDiskAccessSettings: () =>
    invokeWithLog<string>('open_macos_full_disk_access_settings'),

  // AI Provider（旧版兼容）
  getAIProviders: () => invokeWithLog<AIProviderOption[]>('get_ai_providers'),

  // AI 配置（新版）
  getOfficialProviders: () => invokeWithLog<OfficialProvider[]>('get_official_providers'),
  getAIConfig: () => invokeWithLog<AIConfigOverview>('get_ai_config'),
  saveProvider: (
    providerName: string,
    baseUrl: string,
    apiKey: string | null,
    apiType: string,
    models: ModelConfig[]
  ) =>
    invokeWithLog<string>('save_provider', {
      providerName,
      baseUrl,
      apiKey,
      apiType,
      models,
    }),
  deleteProvider: (providerName: string) =>
    invokeWithLog<string>('delete_provider', { providerName }),
  setPrimaryModel: (modelId: string) =>
    invokeWithLog<string>('set_primary_model', { modelId }),
  addAvailableModel: (modelId: string) =>
    invokeWithLog<string>('add_available_model', { modelId }),
  removeAvailableModel: (modelId: string) =>
    invokeWithLog<string>('remove_available_model', { modelId }),

  // 渠道
  getChannelsConfig: () => invokeWithLog<ChannelConfig[]>('get_channels_config'),
  saveChannelConfig: (channel: ChannelConfig) =>
    invokeWithLog<string>('save_channel_config', { channel }),

  // 诊断测试
  runDoctor: () => invokeWithLog<DiagnosticResult[]>('run_doctor'),
  testAIConnection: () => invokeWithLog<AITestResult>('test_ai_connection'),
  testChannel: (channelType: string) =>
    invokeWithLog<unknown>('test_channel', { channelType }),

  // 总控中心（OpenClaw + ClawBot）
  getManagedServicesStatus: () =>
    invokeWithLog<ManagedServiceStatus[]>('get_managed_services_status'),
  controlManagedService: (label: string, action: ManagedServiceAction) =>
    invokeWithLog<string>('control_managed_service', { label, action }),
  controlAllManagedServices: (action: ManagedServiceAction) =>
    invokeWithLog<string>('control_all_managed_services', { action }),
  getClawbotRuntimeConfig: () =>
    invokeWithLog<ClawbotRuntimeConfig>('get_clawbot_runtime_config'),
  getClawbotBotMatrix: () =>
    invokeWithLog<ClawbotBotMatrixEntry[]>('get_clawbot_bot_matrix'),
  getOpenclawUsageSnapshot: () =>
    invokeWithLog<OpenclawUsageSnapshot>('get_openclaw_usage_snapshot'),
  saveClawbotRuntimeConfig: (values: ClawbotRuntimeConfig) =>
    invokeWithLog<string>('save_clawbot_runtime_config', { values }),
  getManagedServiceLogs: (label: string, lines?: number) =>
    invokeWithLog<string[]>('get_managed_service_logs', { label, lines }),
  getManagedEndpointsStatus: () =>
    invokeWithLog<ManagedEndpointStatus[]>('get_managed_endpoints_status'),
};

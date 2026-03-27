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

export interface SkillEntry {
  name: string;
  enabled: boolean;
}

export interface SkillsStatus {
  total: number;
  enabled: number;
  skills: SkillEntry[];
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
  getSkillsStatus: () =>
    invokeWithLog<SkillsStatus>('get_skills_status'),

  // ──── ClawBot 系统 ────

  // 后端健康检查 ping
  clawbotPing: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_ping'),

  // ClawBot 整体运行状态
  clawbotStatus: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_status'),

  // ──── 交易系统 ────

  // 交易系统概览
  clawbotTradingSystem: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_trading_system'),

  // 当前持仓列表
  clawbotTradingPositions: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_trading_positions'),

  // 盈亏统计
  clawbotTradingPnl: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_trading_pnl'),

  // 交易信号列表
  clawbotTradingSignals: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_trading_signals'),

  // 对标的进行多空投票
  clawbotTradingVote: (symbol: string, period: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_trading_vote', { symbol, period }),

  // ──── 社媒运营 ────

  // 社媒系统运行状态
  clawbotSocialStatus: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_status'),

  // 获取热门话题列表
  clawbotSocialTopics: (count?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_topics', { count }),

  // 根据话题生成社媒内容
  clawbotSocialCompose: (topic: string, platform?: string, persona?: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_compose', { topic, platform, persona }),

  // 发布内容到指定平台
  clawbotSocialPublish: (platform: string, content: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_publish', { platform, content }),

  // 对指定话题进行调研
  clawbotSocialResearch: (topic: string, count?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_research', { topic, count }),

  // 社媒运营数据指标
  clawbotSocialMetrics: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_metrics'),

  // 获取可用人设列表
  clawbotSocialPersonas: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_personas'),

  // 获取发布日历
  clawbotSocialCalendar: (days?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_calendar', { days }),

  // ──── 社媒自动驾驶 ────

  // 自动驾驶运行状态
  clawbotAutopilotStatus: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_status'),

  // 启动自动驾驶
  clawbotAutopilotStart: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_start'),

  // 停止自动驾驶
  clawbotAutopilotStop: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_stop'),

  // 手动触发指定自动驾驶任务
  clawbotAutopilotTrigger: (jobId: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_trigger', { jobId }),

  // ──── 社媒草稿管理 ────

  // 获取所有草稿
  clawbotSocialDrafts: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_drafts'),

  // 更新指定草稿内容
  clawbotSocialDraftUpdate: (index: number, text: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_update', { index, text }),

  // 删除指定草稿
  clawbotSocialDraftDelete: (index: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_delete', { index }),

  // 发布指定草稿
  clawbotSocialDraftPublish: (index: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_publish', { index }),

  // ──── 图像生成 ────

  // 根据提示词生成图片
  clawbotGenerateImage: (prompt: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_generate_image', { prompt }),

  // 生成人设角色照片
  clawbotGeneratePersonaPhoto: (persona?: string, scenario?: string, mood?: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_generate_persona_photo', { persona, scenario, mood }),

  // ──── 记忆系统 ────

  // 搜索记忆库
  clawbotMemorySearch: (query: string, limit?: number, mode?: string, category?: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_memory_search', { query, limit, mode, category }),

  // 记忆库统计信息
  clawbotMemoryStats: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_memory_stats'),

  // ──── API 池 ────

  // API 池使用统计
  clawbotPoolStats: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_pool_stats'),

  // ──── 自进化系统 ────

  // 触发自进化扫描
  clawbotEvolutionScan: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_scan'),

  // 获取进化提案列表
  clawbotEvolutionProposals: (status?: string, limit?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_proposals', { status, limit }),

  // 获取能力缺口分析
  clawbotEvolutionGaps: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_gaps'),

  // 自进化统计数据
  clawbotEvolutionStats: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_stats'),

  // 更新进化提案状态
  clawbotEvolutionUpdateProposal: (proposalId: string, status: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_update_proposal', { proposalId, status }),

  // ──── 比价引擎 ────

  // 商品比价搜索
  clawbotShoppingCompare: (query: string, limit?: number, aiSummary?: boolean) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_shopping_compare', { query, limit, aiSummary }),

  // ──── OMEGA v2.0 ────

  // OMEGA 系统状态
  omegaStatus: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_status'),

  // OMEGA 成本统计
  omegaCost: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_cost'),

  // OMEGA 事件历史
  omegaEvents: (eventType?: string, limit?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_events', { eventType, limit }),

  // OMEGA 审计日志
  omegaAudit: (limit?: number) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_audit', { limit }),

  // OMEGA 活跃任务列表
  omegaTasks: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_tasks'),

  // OMEGA Brain 处理消息
  omegaProcess: (message: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_process', { message }),

  // OMEGA 投资团队状态
  omegaInvestmentTeam: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_investment_team'),

  // OMEGA 投资分析（指定标的和市场）
  omegaInvestmentAnalyze: (symbol: string, market?: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_investment_analyze', { symbol, market }),

  // OMEGA AI 图像生成
  omegaGenerateImage: (prompt: string, model?: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_generate_image', { prompt, model }),

  // OMEGA AI 视频生成
  omegaGenerateVideo: (prompt: string) =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_generate_video', { prompt }),

  // OMEGA 可用媒体生成模型列表
  omegaMediaModels: () =>
    invokeWithLog<Record<string, unknown>>('clawbot_api_omega_media_models'),
};

export const CLAWBOT_WS_URL = `ws://127.0.0.1:${import.meta.env.VITE_API_PORT || '18790'}/ws/events`;

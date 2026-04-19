import { invokeWithLog } from './tauri-core';
import type {
  ServiceStatus,
  SystemInfo,
  AIProviderOption,
  OfficialProvider,
  AIConfigOverview,
  ModelConfig,
  ChannelConfig,
  DiagnosticResult,
  AITestResult,
  ManagedServiceStatus,
  ManagedServiceAction,
  ManagedEndpointStatus,
  ClawbotRuntimeConfig,
  ClawbotBotMatrixEntry,
  OpenclawUsageSnapshot,
  SkillsStatus,
  AppSettings,
  ProjectContext,
  TradingStatusResponse,
  MemorySearchResponse,
  EvolutionProposalsRaw,
  EvolutionGapsRaw,
  EvolutionStatsRaw,
  OmegaProcessResponse,
} from './tauri-core';

// ── 服务管理 ──

export const getServiceStatus = () =>
  invokeWithLog<ServiceStatus>('get_service_status');
export const startService = () =>
  invokeWithLog<string>('start_service');
export const stopService = () =>
  invokeWithLog<string>('stop_service');
export const restartService = () =>
  invokeWithLog<string>('restart_service');
export const getLogs = (lines?: number) =>
  invokeWithLog<string[]>('get_logs', { lines });

// ── 系统信息 ──

export const getSystemInfo = () =>
  invokeWithLog<SystemInfo>('get_system_info');
export const checkOpenclawInstalled = () =>
  invokeWithLog<boolean>('check_openclaw_installed');
export const getOpenclawVersion = () =>
  invokeWithLog<string | null>('get_openclaw_version');

// ── 配置管理 ──

export const getConfig = () =>
  invokeWithLog<unknown>('get_config');
export const saveConfig = (config: unknown) =>
  invokeWithLog<string>('save_config', { config });
export const getEnvValue = (key: string) =>
  invokeWithLog<string | null>('get_env_value', { key });
export const saveEnvValue = (key: string, value: string) =>
  invokeWithLog<string>('save_env_value', { key, value });
export const getProjectContext = () =>
  invokeWithLog<ProjectContext>('get_project_context');
export const getAppSettings = () =>
  invokeWithLog<AppSettings>('get_app_settings');
export const saveAppSettings = (settings: AppSettings) =>
  invokeWithLog<string>('save_app_settings', { settings });
export const openMacOSFullDiskAccessSettings = () =>
  invokeWithLog<string>('open_macos_full_disk_access_settings');

// ── AI Provider（旧版兼容） ──

export const getAIProviders = () =>
  invokeWithLog<AIProviderOption[]>('get_ai_providers');

// ── AI 配置（新版） ──

export const getOfficialProviders = () =>
  invokeWithLog<OfficialProvider[]>('get_official_providers');
export const getAIConfig = () =>
  invokeWithLog<AIConfigOverview>('get_ai_config');
export const saveProvider = (
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
  });
export const deleteProvider = (providerName: string) =>
  invokeWithLog<string>('delete_provider', { providerName });
export const setPrimaryModel = (modelId: string) =>
  invokeWithLog<string>('set_primary_model', { modelId });
export const addAvailableModel = (modelId: string) =>
  invokeWithLog<string>('add_available_model', { modelId });
export const removeAvailableModel = (modelId: string) =>
  invokeWithLog<string>('remove_available_model', { modelId });

// ── 渠道 ──

export const getChannelsConfig = () =>
  invokeWithLog<ChannelConfig[]>('get_channels_config');
export const saveChannelConfig = (channel: ChannelConfig) =>
  invokeWithLog<string>('save_channel_config', { channel });
export const clearChannelConfig = (channelId: string) =>
  invokeWithLog<string>('clear_channel_config', { channelId });

// ── 诊断测试 ──

export const runDoctor = () =>
  invokeWithLog<DiagnosticResult[]>('run_doctor');
export const testAIConnection = () =>
  invokeWithLog<AITestResult>('test_ai_connection');
export const testChannel = (channelType: string) =>
  invokeWithLog<unknown>('test_channel', { channelType });

// ── 总控中心（OpenClaw + ClawBot） ──

export const getManagedServicesStatus = () =>
  invokeWithLog<ManagedServiceStatus[]>('get_managed_services_status');
export const controlManagedService = (label: string, action: ManagedServiceAction) =>
  invokeWithLog<string>('control_managed_service', { label, action });
export const controlAllManagedServices = (action: ManagedServiceAction) =>
  invokeWithLog<string>('control_all_managed_services', { action });
export const getClawbotRuntimeConfig = () =>
  invokeWithLog<ClawbotRuntimeConfig>('get_clawbot_runtime_config');
export const getClawbotBotMatrix = () =>
  invokeWithLog<ClawbotBotMatrixEntry[]>('get_clawbot_bot_matrix');
export const getOpenclawUsageSnapshot = () =>
  invokeWithLog<OpenclawUsageSnapshot>('get_openclaw_usage_snapshot');
export const saveClawbotRuntimeConfig = (values: ClawbotRuntimeConfig) =>
  invokeWithLog<string>('save_clawbot_runtime_config', { values });
export const getManagedServiceLogs = (label: string, lines?: number) =>
  invokeWithLog<string[]>('get_managed_service_logs', { label, lines });
export const getManagedEndpointsStatus = () =>
  invokeWithLog<ManagedEndpointStatus[]>('get_managed_endpoints_status');
export const getSkillsStatus = () =>
  invokeWithLog<SkillsStatus>('get_skills_status');

// ── ClawBot 系统 ──

export const clawbotPing = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_ping');
export const clawbotStatus = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_status');

// ── 交易系统 ──

export const clawbotTradingSystem = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_trading_system');
export const clawbotTradingPositions = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_trading_positions');
export const clawbotTradingPnl = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_trading_pnl');
export const clawbotTradingSignals = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_trading_signals');
export const clawbotTradingVote = (symbol: string, period: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_trading_vote', { symbol, period });

// ── 社媒浏览器状态 ──

export const clawbotSocialBrowserStatus = () =>
  invokeWithLog<{ x: string; xhs: string }>('clawbot_api_social_browser_status');

// ── 交易状态 ──

export const clawbotTradingStatus = () =>
  invokeWithLog<TradingStatusResponse>('clawbot_api_trading_status');

// ── 社媒运营 ──

export const clawbotSocialStatus = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_status');
export const clawbotSocialTopics = (count?: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_topics', { count });
export const clawbotSocialCompose = (topic: string, platform?: string, persona?: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_compose', { topic, platform, persona });
export const clawbotSocialPublish = (platform: string, content: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_publish', { platform, content });
export const clawbotSocialResearch = (topic: string, count?: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_research', { topic, count });
export const clawbotSocialMetrics = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_metrics');
export const clawbotSocialPersonas = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_personas');
export const clawbotSocialCalendar = (days?: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_calendar', { days });

// ── 社媒自动驾驶 ──

export const clawbotAutopilotStatus = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_status');
export const clawbotAutopilotStart = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_start');
export const clawbotAutopilotStop = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_stop');
export const clawbotAutopilotTrigger = (jobId: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_autopilot_trigger', { jobId });

// ── 社媒草稿管理 ──

export const clawbotSocialDrafts = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_drafts');
export const clawbotSocialDraftUpdate = (index: number, text: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_update', { index, text });
export const clawbotSocialDraftDelete = (index: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_delete', { index });
export const clawbotSocialDraftPublish = (index: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_social_draft_publish', { index });

// ── 图像生成 ──

export const clawbotGenerateImage = (prompt: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_generate_image', { prompt });
export const clawbotGeneratePersonaPhoto = (persona?: string, scenario?: string, mood?: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_generate_persona_photo', { persona, scenario, mood });

// ── 记忆系统 ──

export const clawbotMemorySearch = (query: string, limit?: number, mode?: string, category?: string) =>
  invokeWithLog<MemorySearchResponse>('clawbot_api_memory_search', { query, limit, mode, category });
export const clawbotMemoryDelete = (key: string) =>
  invokeWithLog<void>('clawbot_api_memory_delete', { key });
export const clawbotMemoryUpdate = (key: string, value: string) =>
  invokeWithLog<void>('clawbot_api_memory_update', { key, value });
export const clawbotMemoryStats = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_memory_stats');

// ── API 池 ──

export const clawbotPoolStats = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_pool_stats');

// ── 自进化系统 ──

export const clawbotEvolutionScan = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_scan');
export const clawbotEvolutionProposals = (status?: string, limit?: number) =>
  invokeWithLog<EvolutionProposalsRaw>('clawbot_api_evolution_proposals', { status, limit });
export const clawbotEvolutionGaps = () =>
  invokeWithLog<EvolutionGapsRaw>('clawbot_api_evolution_gaps');
export const clawbotEvolutionStats = () =>
  invokeWithLog<EvolutionStatsRaw>('clawbot_api_evolution_stats');
export const clawbotEvolutionUpdateProposal = (proposalId: string, status: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_evolution_update_proposal', { proposalId, status });

// ── 比价引擎 ──

export const clawbotShoppingCompare = (query: string, limit?: number, aiSummary?: boolean) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_shopping_compare', { query, limit, aiSummary });

// ── OMEGA v2.0 ──

export const omegaStatus = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_status');
export const omegaCost = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_cost');
export const omegaEvents = (eventType?: string, limit?: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_events', { eventType, limit });
export const omegaAudit = (limit?: number) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_audit', { limit });
export const omegaTasks = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_tasks');
export const omegaProcess = (message: string) =>
  invokeWithLog<OmegaProcessResponse>('clawbot_api_omega_process', { message });
export const omegaInvestmentTeam = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_investment_team');
export const omegaInvestmentAnalyze = (symbol: string, market?: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_investment_analyze', { symbol, market });
export const omegaGenerateImage = (prompt: string, model?: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_generate_image', { prompt, model });
export const omegaGenerateVideo = (prompt: string) =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_generate_video', { prompt });
export const omegaMediaModels = () =>
  invokeWithLog<Record<string, unknown>>('clawbot_api_omega_media_models');

// ── MCP 插件进程管理 ──

export const startMcpPlugin = (id: string) =>
  invokeWithLog<void>('start_mcp_plugin', { id });
export const stopMcpPlugin = (id: string) =>
  invokeWithLog<void>('stop_mcp_plugin', { id });
export const getMcpPluginStatus = (id: string) =>
  invokeWithLog<string>('get_mcp_plugin_status', { id });

import { invoke } from '@tauri-apps/api/core';
import { apiLogger } from './logger';

// 检查是否在 Tauri 环境中运行
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

// 带日志的 invoke 封装（自动检查 Tauri 环境）
export async function invokeWithLog<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
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

// ── 类型定义 ──────────────────────────────────────────────────

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

// AI 服务商选项（旧版兼容，底层字段仍沿用 provider 命名）
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

// 官方服务商预设
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

// 已配置的服务商
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
  provider: string; // 底层兼容字段，界面统一展示为"服务商"
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

// ── ClawBot API 响应类型定义 ──────────────────────────────────

// 自进化系统 — 统计数据
export interface EvolutionStatsRaw {
  total_proposals?: number;
  proposals_count?: number;
  total_scans?: number;
  scans_count?: number;
  capability_gaps?: number;
  gaps_count?: number;
  last_scan?: string;
  last_scan_at?: string;
  last_scan_time?: string;  // 后端实际字段名
  approved?: number;
  rejected?: number;
  pending?: number;
  by_status?: Record<string, number>;  // 后端返回的状态分组
  by_module?: Record<string, number>;  // 后端返回的模块分组
}

// 自进化系统 — 能力缺口条目
export interface CapabilityGapRaw {
  module?: string;
  category?: string;
  description?: string;
  gap?: string;
  name?: string;
  priority?: string;
  severity?: string;
  discovered_at?: string;
  created_at?: string;
}

// 自进化系统 — 能力缺口响应（数组或包装对象）
export interface EvolutionGapsRaw {
  gaps?: CapabilityGapRaw[];
  data?: CapabilityGapRaw[];
}

// 自进化系统 — 提案条目
export interface EvolutionProposalRaw {
  id?: string;
  proposal_id?: string;
  repo_name?: string;
  repo?: string;
  name?: string;
  repo_url?: string;
  url?: string;
  stars?: number;
  stargazers_count?: number;
  growth_rate?: number;
  weekly_growth?: number;
  target_module?: string;
  module?: string;
  value_score?: number;
  score?: number;
  difficulty_score?: number;
  difficulty?: number;
  risk_level?: string;
  risk?: string;
  integration_approach?: string;
  approach?: string;
  status?: string;
  created_at?: string;
}

// 自进化系统 — 提案列表响应（数组或包装对象）
export interface EvolutionProposalsRaw {
  proposals?: EvolutionProposalRaw[];
  data?: EvolutionProposalRaw[];
}

// 交易系统 — 实时状态响应
export interface TradingStatusResponse {
  connected?: boolean;
  chart_data?: Array<{ name: string; value: number }>;
  assets?: Array<{ name: string; value: number; pnl: number }>;
  [key: string]: unknown;
}

// 记忆系统 — 搜索响应
export interface MemorySearchResponse {
  results?: MemoryEntryRaw[];
  entries?: MemoryEntryRaw[];
}

// 记忆系统 — 条目
export interface MemoryEntryRaw {
  key?: string;
  id?: string;
  value?: string | Record<string, unknown>;
  content?: string;
  source_bot?: string;
  source?: string;
  importance?: number;
  score?: number;
  updated_at?: number;
}

// OMEGA — 通用处理响应
export interface OmegaProcessResponse {
  result?: string;
  response?: string;
  [key: string]: unknown;
}

// ── 网络常量 & HTTP 封装 ──────────────────────────────────────

// WebSocket 和 HTTP 地址从环境变量读取，不硬编码 localhost
const CLAWBOT_API_HOST = import.meta.env.VITE_API_HOST || '127.0.0.1';
export const CLAWBOT_WS_URL = `ws://${CLAWBOT_API_HOST}:${import.meta.env.VITE_API_PORT || '18790'}/api/v1/events`;

// ── API Token 认证 ──
// 浏览器降级模式下的 HTTP 请求需要携带 X-API-Token
const CLAWBOT_API_TOKEN = import.meta.env.VITE_CLAWBOT_API_TOKEN || '';
const CLAWBOT_API_BASE = `http://${CLAWBOT_API_HOST}:${import.meta.env.VITE_API_PORT || '18790'}`;

// ── 默认请求超时（毫秒） ──
const DEFAULT_TIMEOUT_MS = 30_000; // 30 秒，普通 API 请求
/** AI 分析等长时间操作使用的超时（120秒），供调用方传入 timeoutMs 参数 */
export const LONG_TIMEOUT_MS = 120_000;

/**
 * 带认证+超时的 fetch 封装 — 自动附加 X-API-Token + AbortController 超时控制
 *
 * @param path  API 路径（如 /api/v1/system/status）
 * @param init  fetch 选项
 * @param timeoutMs  超时时间（毫秒），默认 30 秒。传 0 表示不限时
 */
export async function clawbotFetch(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (CLAWBOT_API_TOKEN) {
    headers.set('X-API-Token', CLAWBOT_API_TOKEN);
  }
  // FormData 需要浏览器自动设置 Content-Type（含 boundary），不能覆盖
  if (!headers.has('Content-Type') && init?.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // 超时控制：用 AbortController 实现，不影响已有的 signal
  if (timeoutMs > 0 && !init?.signal) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(`${CLAWBOT_API_BASE}${path}`, {
        ...init,
        headers,
        signal: controller.signal,
      });
      clearTimeout(timer);
      return resp;
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error(`请求超时（${timeoutMs / 1000}秒）: ${path}`);
      }
      throw err;
    }
  }

  // 调用方已提供 signal 或不限时 — 直接透传
  return fetch(`${CLAWBOT_API_BASE}${path}`, { ...init, headers });
}

/**
 * 带友好错误提示的 fetch 封装 — 自动转换 HTTP 错误为友好消息
 * 用于需要向用户展示错误的场景
 */
export async function clawbotFetchSafe(path: string, init?: RequestInit): Promise<Response> {
  try {
    const resp = await clawbotFetch(path, init);
    if (!resp.ok) {
      // Import dynamically to avoid circular deps
      const { toFriendlyError } = await import('./errorMessages');
      const friendly = toFriendlyError(resp);
      throw Object.assign(new Error(friendly.title), { friendly });
    }
    return resp;
  } catch (err) {
    if (err && typeof err === 'object' && 'friendly' in err) throw err;
    const { toFriendlyError } = await import('./errorMessages');
    const friendly = toFriendlyError(err);
    throw Object.assign(new Error(friendly.title), { friendly });
  }
}

/**
 * fetch + JSON 解析 + 错误检查 — 最常用的 API 调用模式
 * 自动检查 resp.ok，非 2xx 时抛出含 HTTP 状态码和响应体的 Error
 *
 * @param path  API 路径（如 /api/v1/system/status）
 * @param init  fetch 选项
 * @param timeoutMs  超时时间（毫秒），默认 30 秒。传 0 表示不限时
 * @returns 解析后的 JSON 对象
 */
export async function clawbotFetchJson<T = any>(
  path: string,
  init?: RequestInit,
  timeoutMs?: number,
): Promise<T> {
  const resp = await clawbotFetch(path, init, timeoutMs);
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText || '请求失败'}`);
  }
  return resp.json();
}

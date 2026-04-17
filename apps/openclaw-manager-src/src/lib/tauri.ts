// Barrel re-export — keeps all existing `import { ... } from '@/lib/tauri'` working.

export {
  // Core utilities
  isTauri,
  invokeWithLog,
  clawbotFetch,
  clawbotFetchSafe,
  CLAWBOT_WS_URL,

  // Type definitions
  type ServiceStatus,
  type SystemInfo,
  type AIProviderOption,
  type AIModelOption,
  type OfficialProvider,
  type SuggestedModel,
  type ConfiguredProvider,
  type ConfiguredModel,
  type AIConfigOverview,
  type ModelConfig,
  type ChannelConfig,
  type DiagnosticResult,
  type AITestResult,
  type ManagedServiceStatus,
  type ManagedEndpointStatus,
  type ManagedServiceAction,
  type ClawbotRuntimeConfig,
  type ClawbotBotMatrixEntry,
  type OpenclawUsageSnapshot,
  type SkillEntry,
  type SkillsStatus,
  type IdentitySettings,
  type SecuritySettings,
  type AppSettings,
  type ProjectContext,
  type EvolutionStatsRaw,
  type CapabilityGapRaw,
  type EvolutionGapsRaw,
  type EvolutionProposalRaw,
  type EvolutionProposalsRaw,
  type TradingStatusResponse,
  type MemorySearchResponse,
  type MemoryEntryRaw,
  type OmegaProcessResponse,
} from './tauri-core';

export * from './tauri-ipc';

export { api } from './api';

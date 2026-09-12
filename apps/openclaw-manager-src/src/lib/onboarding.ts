import type { AIConfigOverview, ModelConfig } from './tauri';

export interface GatewaySetupInput {
  providerName: string;
  modelId: string;
  apiType: string;
  baseUrl: string;
  apiKey: string;
}

interface GatewaySetupAPI {
  getAIConfig: () => Promise<AIConfigOverview>;
  saveProvider: (name: string, url: string, key: string | null, type: string, models: ModelConfig[]) => Promise<string>;
}

export class OnboardingError extends Error {
  constructor(public readonly code: 'invalidFields' | 'maskedKey' | 'readFailed' | 'saveFailed' | 'readbackFailed' | 'agentManaged') {
    super(code);
  }
}

/** Saves one identified Gateway provider/model. No runtime call or primary-model switch. */
export async function saveGatewaySetup(input: GatewaySetupInput, api: GatewaySetupAPI, isCurrent: () => boolean): Promise<boolean> {
  const providerName = input.providerName.trim();
  const modelId = input.modelId.trim();
  const baseUrl = input.baseUrl.trim();
  const key = input.apiKey.trim();
  let url: URL;
  try { url = new URL(baseUrl); } catch { throw new OnboardingError('invalidFields'); }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(providerName) || !modelId || modelId.length > 200 || /\s/.test(modelId)
      || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !input.apiType) {
    throw new OnboardingError('invalidFields');
  }
  if (key.includes('...') || /[*•\r\n]/.test(key)) throw new OnboardingError('maskedKey');
  let before: AIConfigOverview;
  try { before = await api.getAIConfig(); } catch { throw new OnboardingError('readFailed'); }
  if (!isCurrent()) return false;
  // Agent-file fallback is read-only here: creating local overrides would shadow it.
  if (before.config_source === 'agent') throw new OnboardingError('agentManaged');
  const existing = before.configured_providers.find((provider) => provider.name === providerName);
  const model = existing?.models.find((entry) => entry.id === modelId);
  const models: ModelConfig[] = [{
    id: modelId, name: model?.name || modelId, api: input.apiType,
    input: [], context_window: null, max_tokens: null, reasoning: null, cost: null,
  }];
  try { await api.saveProvider(providerName, baseUrl, key || null, input.apiType, models); }
  catch { throw new OnboardingError('saveFailed'); }
  if (!isCurrent()) return false;
  let after: AIConfigOverview;
  try { after = await api.getAIConfig(); } catch { throw new OnboardingError('readbackFailed'); }
  if (!isCurrent()) return false;
  const saved = after.configured_providers.find((provider) => provider.name === providerName);
  const savedModel = saved?.models.find((entry) => entry.id === modelId);
  if (after.config_source !== 'openclaw' || !saved || saved.base_url !== baseUrl || !savedModel || savedModel.api_type !== input.apiType
      || ((!!key || existing?.has_api_key) && !saved.has_api_key)) throw new OnboardingError('readbackFailed');
  return true;
}

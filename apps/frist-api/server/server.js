import { spawnSync } from 'node:child_process';
import { createHash, createHmac, pbkdf2Sync, randomBytes, timingSafeEqual } from 'node:crypto';
import { lookup as lookupDns } from 'node:dns/promises';
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { isIP } from 'node:net';
import { dirname, extname, join, normalize, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export { resolveSmtpSocketTargets } from './email.js';
import {
  DEFAULT_SESSION_TTL_MS,
  buildGatewayAffinityKey,
  clearRouteAffinity,
  createCaptchaChallenge,
  expiredSessionCookies,
  findSession,
  issueCustomerSession,
  orderGatewayCandidates,
  requireCaptchaIfEnabled,
  requireCsrfIfEnabled,
  requireSession,
  requireUserKey,
  rememberRouteAffinity,
  revokeCustomerSessions,
  runtimeTokenKey,
  sessionCookies,
  shouldUseSecureCookie,
} from './auth.js';
import {
  accountFromUser,
  allowedPoolsForUser,
  availableQuotaCents,
  buildGatewayModels,
  buildInventorySummary,
  buildModelCatalog,
  buildModelUsage,
  currentDate,
  deductUserQuota,
  estimateQuotaCostCents,
  expireUserPlanIfNeeded,
  mergeModelPrices,
  normalizeCredentialRecord,
  normalizeModelPrices,
  normalizePricingConfig,
  normalizeRechargePlans,
  normalizeSupplierProfileRecord,
  poolForUser,
  pricingPayload,
  resolveQuotaCostCents,
} from './catalog.js';
import { createNewApiBridge } from './newApiBridge.js';
import {
  buildBalanceAlertEmail,
  buildPasswordResetEmail,
  buildVerificationEmail,
  createBalanceAlertEmailSender,
  defaultBalanceAlert,
  maskEmail,
  normalizeAlertEmail,
  normalizeAlertThresholdCents,
  normalizeBalanceAlertRecord,
  normalizeMoneyCents,
  resolveSmtpSocketTargets,
  sanitizeBalanceAlert,
  scheduleEmailDelivery,
} from './email.js';
import {
  buildPaymentClosureStatus,
  createProviderPayment,
  handleAlipayPaymentNotification,
  handleWechatPaymentNotification,
  normalizePaymentMethod,
  paymentConfigFromOptions,
  paymentProviderForMethod,
  providerReady,
  sanitizeProviderPayment,
} from './payments.js';
import { createRuntimeStore, decryptSecretField, encryptSecretField } from './runtime-store.js';
import {
  DEFAULT_RATE_LIMIT_MAX_ENTRIES,
  assertAdminSecondFactorRateLimit,
  assertAuthRateLimit,
  assertEmailVerificationRateLimit,
  assertPasswordResetConfirmRateLimit,
  assertPasswordResetRequestRateLimit,
  assertRedeemRateLimit,
  assertRedeemUserRateLimit,
  clientIp,
  createSecurityState,
  parseTrustedProxyIps,
} from './security.js';
import {
  addDays,
  authHeadersForKey,
  chatMessageContentToText,
  compactObject,
  compactTokenText,
  compareGatewayCredentials,
  contextForModel,
  createId,
  credentialMatchesModelGroup,
  effectiveCredentialGroup,
  estimateCredentialWaste,
  estimatePromptTokens,
  expiryMs,
  findModelPrice,
  formatDate,
  formatCny,
  formatUsdFromCnyCents,
  formatUsdPriceFromCny,
  generateVerificationCode,
  hashAdminClaimCode,
  hashId,
  headerValue,
  initialsFromEmail,
  inputText,
  isCredentialRejectedResponse,
  isCredentialRouteApproved,
  isGatewayAdapterUnsupported,
  isImageGenerationModel,
  isModelUnsupportedResponse,
  isOpenAiChatCompletionPayload,
  isOpenAiImageGenerationPayload,
  isOpenAiResponsesPayload,
  isQuotaExhaustedResponse,
  isSourceRouteApproved,
  maskKey,
  normalizePool,
  normalizeModels,
  normalizeRechargePlan,
  normalizeRiskStatus,
  normalizeSourceType,
  normalizeStreamChunk,
  parseAdminClaimCodes,
  parseCookies,
  parseJsonPayload,
  parseModelIds,
  parseUpstreamUsage,
  priceLabel,
  priceUsageCents,
  providerFromModel,
  publicError,
  readJsonBody,
  readRequestText,
  reconcileUserBalance,
  round2,
  sanitizeAdminEvents,
  sanitizeExtraHeaders,
  sanitizeCredential,
  sanitizeParsedOrder,
  sanitizePaymentOrder,
  sanitizeRiskNote,
  sanitizeUserKey,
  shouldFailoverUpstream,
  shouldTryResponsesProbe,
  sortModelsByStrength,
  strongestModel,
  taglineForModel,
  uniqueStrings,
  writeJson,
  writeNoContent,
  gatewayUnavailableResponse,
} from './shared.js';
import {
  buildClientConfig,
  buildClientSetupCommands,
  inferProviderGroup,
  modelMatchesGroup,
  normalizeBaseUrl,
  normalizeClientAvailableModels,
  normalizeModelGroup,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  normalizeUpstreamChannelSnapshot,
  parsePriceText,
  parseSupplierOrderText,
  poolPriority,
  recommendConnectionPath,
} from '../src/core.js';

const DEFAULT_MODEL = 'claude-opus-4-6-thinking-c';
const DEFAULT_PUBLIC_MODEL = 'gpt-5.5';
const DEFAULT_USD_TO_CNY = 7.2;
const DISPLAY_USD_TO_CNY = DEFAULT_USD_TO_CNY;
// 参考 OpenAI Models API list（2026-07-02 复核）：探测候选只用于补号探活，不作为客户可见模型目录兜底。
const DEFAULT_PROBE_MODELS = Object.freeze([
  'claude-opus-4-6-thinking-c', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c',
  'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2', 'gpt-5.3-codex', 'gemini-2.5-flash',
  'deepseek-v4-flash', 'deepseek-v4-pro',
]);
const DEFAULT_QUOTA_COST = 10;
const PRIMARY_SOURCE_TYPE = 'authorized';
const BACKUP_SOURCE_TYPES = new Set(['cpa_json_backup', 'chong_backup', 'manual_backup']);
const PLUS_ACCOUNT_STATUSES = new Set(['warming', 'active', 'renewal_due', 'paused', 'risk_hold', 'retired']);
const PLUS_ACCOUNT_COMPLIANCE_STATUSES = new Set(['self_use_only', 'needs_review', 'blocked']);
const PLUS_ACCOUNT_REGIONS = new Set(['Türkiye', 'United States', 'China', 'Other']);
const RT_ACCOUNT_STATUSES = new Set(['ready_for_refresh', 'active', 'needs_refresh', 'blocked', 'retired']);
const RT_ACCOUNT_PLATFORMS = new Set(['codex', 'openai', 'claude', 'gemini', 'other']);
const DEFAULT_RECHARGE_PLANS = Object.freeze([
  Object.freeze({ id: 'xianyu-test-1', label: 'CC中转 1元测试档', quotaUsd: 1, priceCny: 1, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'xianyu-5', label: 'CC中转 5元档', quotaUsd: 5, priceCny: 5, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'xianyu-15', label: 'CC中转 15元档', quotaUsd: 15, priceCny: 15, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'xianyu-50', label: 'CC中转 50元档', quotaUsd: 50, priceCny: 50, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'xianyu-100', label: 'CC中转 100元档', quotaUsd: 100, priceCny: 100, durationDays: 0, plan: 'balance' }),
  Object.freeze({ id: 'xianyu-500', label: 'CC中转 500元档', quotaUsd: 500, priceCny: 500, durationDays: 0, plan: 'balance' }),
]);
const DEFAULT_CARD_AUTOREPLENISH_SAFETY_STOCK = Object.freeze({
  'xianyu-test-1': 3,
  'xianyu-5': 10,
  'xianyu-15': 10,
  'xianyu-50': 5,
  'xianyu-100': 3,
  'xianyu-500': 1,
});
const DEFAULT_CARD_AUTOREPLENISH_DAILY_CAP = 50;
const LEGACY_RECHARGE_PLAN_ALIASES = new Map([
  ['codex-30-day', Object.freeze({ id: 'codex-30-day', label: 'Codex API 30刀额度/日卡', quotaUsd: 30, priceCny: 5.88, durationDays: 1, plan: 'day' })],
  ['codex-30-unlimited', Object.freeze({ id: 'codex-30-unlimited', label: 'Codex API 30刀额度/不限时', quotaUsd: 30, priceCny: 8.88, durationDays: 0, plan: 'balance' })],
  ['codex-100-unlimited', Object.freeze({ id: 'codex-100-unlimited', label: 'Codex API 100刀额度/不限时', quotaUsd: 100, priceCny: 28.88, durationDays: 0, plan: 'balance' })],
  ['codex-500-unlimited', Object.freeze({ id: 'codex-500-unlimited', label: 'Codex API 500刀额度/不限时', quotaUsd: 500, priceCny: 68.88, durationDays: 0, plan: 'balance' })],
  ['codex-1000-unlimited', Object.freeze({ id: 'codex-1000-unlimited', label: 'Codex API 1000刀额度/不限时', quotaUsd: 1000, priceCny: 118.88, durationDays: 0, plan: 'balance' })],
]);
const DEFAULT_CARD_BATCH_PREFIX = 'CC';
const DEFAULT_MODEL_PRICES = Object.freeze([
  Object.freeze({ model: 'gpt-5.5', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.5-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.4', currency: 'CNY', inputCostCnyPerMillion: 18, outputCostCnyPerMillion: 108, inputSaleCnyPerMillion: 18, outputSaleCnyPerMillion: 108, source: 'official', displayPrice: '参考标价 输入 $2.50 / 缓存 $0.25 / 输出 $15.00 每 1M' }),
  Object.freeze({ model: 'gpt-5.4-mini', currency: 'CNY', inputCostCnyPerMillion: 5.4, outputCostCnyPerMillion: 32.4, inputSaleCnyPerMillion: 5.4, outputSaleCnyPerMillion: 32.4, source: 'official', displayPrice: '参考标价 输入 $0.75 / 缓存 $0.075 / 输出 $4.50 每 1M' }),
  Object.freeze({ model: 'gpt-5.3-codex', currency: 'CNY', inputCostCnyPerMillion: 12.6, outputCostCnyPerMillion: 100.8, inputSaleCnyPerMillion: 12.6, outputSaleCnyPerMillion: 100.8, source: 'official', displayPrice: '参考标价 输入 $1.75 / 缓存 $0.175 / 输出 $14.00 每 1M' }),
  Object.freeze({ model: 'gpt-5-codex', currency: 'CNY', inputCostCnyPerMillion: 9, outputCostCnyPerMillion: 72, inputSaleCnyPerMillion: 9, outputSaleCnyPerMillion: 72, source: 'official', displayPrice: '参考标价 输入 $1.25 / 缓存 $0.125 / 输出 $10.00 每 1M' }),
  Object.freeze({ model: 'gpt-4o', currency: 'CNY', inputCostCnyPerMillion: 18, outputCostCnyPerMillion: 72, inputSaleCnyPerMillion: 18, outputSaleCnyPerMillion: 72, source: 'official', displayPrice: '参考标价 输入 $2.50 / 缓存 $1.25 / 输出 $10.00 每 1M' }),
  Object.freeze({ model: 'gpt-image-2', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 216, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 216, source: 'official', displayPrice: '参考标价 文字入 $5 / 文字缓存 $1.25 / 图入 $8 / 图缓存 $2 / 图出 $30 每 1M' }),
  Object.freeze({ model: 'gpt-image-1.5', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 230.4, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 230.4, source: 'official', displayPrice: '参考标价 文字入 $5 / 文字缓存 $1.25 / 文字出 $10 / 图入 $8 / 图缓存 $2 / 图出 $32 每 1M' }),
  Object.freeze({ model: 'claude-opus-4-6-thinking-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 180, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 180, source: 'official', displayPrice: '参考标价 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M' }),
  Object.freeze({ model: 'claude-opus-4-6-c', currency: 'CNY', inputCostCnyPerMillion: 36, outputCostCnyPerMillion: 180, inputSaleCnyPerMillion: 36, outputSaleCnyPerMillion: 180, source: 'official', displayPrice: '参考标价 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M' }),
  Object.freeze({ model: 'claude-sonnet-4-5-c', currency: 'CNY', inputCostCnyPerMillion: 21.6, outputCostCnyPerMillion: 108, inputSaleCnyPerMillion: 21.6, outputSaleCnyPerMillion: 108, source: 'official', displayPrice: '参考标价 输入 $3.00 / 缓存写 $3.75 / 缓存读 $0.30 / 输出 $15.00 每 1M' }),
  Object.freeze({ model: 'gemini-2.5-flash', currency: 'CNY', inputCostCnyPerMillion: 2.16, outputCostCnyPerMillion: 18, inputSaleCnyPerMillion: 2.16, outputSaleCnyPerMillion: 18, source: 'official', displayPrice: '参考标价 ≤200K 输入 $0.30 / 缓存 $0.03 / 输出 $2.50 每 1M' }),
  Object.freeze({ model: 'deepseek-v4-flash', currency: 'CNY', inputCostCnyPerMillion: 1.01, outputCostCnyPerMillion: 2.02, inputSaleCnyPerMillion: 1.01, outputSaleCnyPerMillion: 2.02, source: 'official', displayPrice: '参考标价 缓存命中 $0.014 / 输入 $0.14 / 输出 $0.28 每 1M' }),
  Object.freeze({ model: 'deepseek-v4-pro', currency: 'CNY', inputCostCnyPerMillion: 3.13, outputCostCnyPerMillion: 6.26, inputSaleCnyPerMillion: 3.13, outputSaleCnyPerMillion: 6.26, source: 'official', displayPrice: '参考标价 缓存命中 $0.035 / 输入 $0.435 / 输出 $0.87 每 1M' }),
]);
const DEFAULT_MODEL_PRICE_BY_MODEL = new Map(
  DEFAULT_MODEL_PRICES.map((price) => [normalizeOfficialModelName(price.model), price]),
);
const DEFAULT_MODEL_CATALOG = [
  { model: 'gpt-5.5', family: 'OpenAI', tagline: '推理和代码主力', context: '1M 上下文', price: '参考标价 输入 $5.00 / 缓存 $0.50 / 输出 $30.00 每 1M', available: true },
  { model: 'gpt-5.4', family: 'OpenAI', tagline: '日常问答和代码补全', context: '1M 上下文', price: '参考标价 输入 $2.50 / 缓存 $0.25 / 输出 $15.00 每 1M', available: true },
  { model: 'gpt-5.4-mini', family: 'OpenAI', tagline: '轻量代码和快速问答', context: '400K 上下文', price: '参考标价 输入 $0.75 / 缓存 $0.075 / 输出 $4.50 每 1M', available: true },
  { model: 'gpt-image-2', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '参考标价 文字入 $5 / 文字缓存 $1.25 / 图入 $8 / 图缓存 $2 / 图出 $30 每 1M', available: true },
  { model: 'gpt-image-1.5', family: 'OpenAI', tagline: '图片生成', context: '图像输入/输出', price: '参考标价 文字入 $5 / 文字缓存 $1.25 / 文字出 $10 / 图入 $8 / 图缓存 $2 / 图出 $32 每 1M', available: true },
  { model: 'gpt-5.3-codex', family: 'OpenAI', tagline: 'Codex 专用代码模型', context: '400K 上下文', price: '参考标价 输入 $1.75 / 缓存 $0.175 / 输出 $14.00 每 1M', available: true },
  { model: 'gpt-5-codex', family: 'OpenAI', tagline: 'Codex 代码模型', context: '400K 上下文', price: '参考标价 输入 $1.25 / 缓存 $0.125 / 输出 $10.00 每 1M', available: true },
  { model: 'gpt-4o', family: 'OpenAI', tagline: '通用多模态', context: '128K 上下文', price: '参考标价 输入 $2.50 / 缓存 $1.25 / 输出 $10.00 每 1M', available: true },
  { model: 'deepseek-v4-flash', family: 'DeepSeek', tagline: 'Codex 桌面版兼容网关', context: 'OpenAI v1 兼容', price: '参考标价 缓存命中 $0.014 / 输入 $0.14 / 输出 $0.28 每 1M', available: true },
  { model: 'deepseek-v4-pro', family: 'DeepSeek', tagline: '推理模型别名', context: 'OpenAI v1 兼容', price: '参考标价 缓存命中 $0.035 / 输入 $0.435 / 输出 $0.87 每 1M', available: true },
  { model: 'gemini-2.5-flash', family: 'Gemini', tagline: '多模态和轻量任务', context: '1M 上下文', price: '参考标价 ≤200K 输入 $0.30 / 缓存 $0.03 / 输出 $2.50 每 1M', available: true },
  { model: DEFAULT_MODEL, family: 'Claude', tagline: '复杂开发和长链路推理', context: '长上下文', price: '参考标价 输入 $5.00 / 缓存写 $6.25 / 缓存读 $0.50 / 输出 $25.00 每 1M', available: true },
];
const ADMIN_2FA_COOKIE = 'frist_admin_2fa';
const TOTP_STEP_SECONDS = 30;
const TOTP_DIGITS = 6;
const DEFAULT_SLA_RETENTION_DAYS = 30;
const LEGACY_CARD_CODES = new Map([
  ['CC-DAY-001', { label: 'Codex API 30刀额度/日卡', plan: 'day', days: 1, packageCents: 800, quotaUsd: 30, priceCny: 5.88 }],
  ['CC-MONTH-001', { label: 'Codex API 月卡 Pro', plan: 'month', days: 30, packageCents: 8000, quotaUsd: 300, priceCny: 58.88 }],
  ['CC-BOOST-100', { label: 'Codex API 100刀加油包', plan: 'balance', days: 0, boosterCents: 10000, quotaUsd: 100, priceCny: 28.88 }],
  ['JIYU-DAY-001', { label: 'Codex API 30刀额度/日卡', plan: 'day', days: 1, packageCents: 800, quotaUsd: 30, priceCny: 5.88 }],
  ['JIYU-MONTH-001', { label: 'Codex API 月卡 Pro', plan: 'month', days: 30, packageCents: 8000, quotaUsd: 300, priceCny: 58.88 }],
  ['JIYU-BOOST-100', { label: 'Codex API 100刀加油包', plan: 'balance', days: 0, boosterCents: 10000, quotaUsd: 100, priceCny: 28.88 }],
]);
const CONTENT_TYPES = new Map([
  ['.css', 'text/css; charset=utf-8'], ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'], ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml; charset=utf-8'],
]);
const ROOT_GATEWAY_PATHS = new Set([
  '/chat/completions', '/openai/chat/completions', '/responses', '/openai/responses',
  '/images/generations', '/openai/images/generations', '/messages',
]);
const DEFAULT_CANONICAL_HOST = 'jiyu.245334.xyz';
const DEFAULT_REDIRECT_HOSTS = Object.freeze([
  '245334.xyz',
  'frist-api.245334.xyz',
  '101-43-41-96.nip.io',
  'frist-api.101-43-41-96.nip.io',
]);
const DEFAULT_CHANNEL_MONITOR_INTERVAL_MS = 60_000;
const DEFAULT_CHANNEL_MONITOR_BATCH_SIZE = 4;
const DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS = 55_000;
const DEFAULT_GATEWAY_SLOW_LATENCY_MS = 5_000;
const DEFAULT_NEWAPI_REDEMPTION_STATUS_SYNC_INTERVAL_MS = 60_000;

export function createFristApiServer(options = {}) {
  const serverOptions = normalizeServerOptions(options);
  const newApiBridge = createNewApiBridge(serverOptions);
  const store = createRuntimeStore(
    serverOptions.dataFile,
    serverOptions.dataEncryptionKey,
    serverOptions.runtimeBeforeSave,
    normalizeRuntimeData,
  );
  const securityState = createSecurityState();
  let stopChannelMonitor = null;
  let stopRedemptionStatusSync = null;
  let stopUpstreamBalanceSync = null;
  let stopCardAutoreplenish = null;

  const server = createServer(async (request, response) => {
    try {
      if (request.method === 'OPTIONS') {
        writeNoContent(response);
        return;
      }

      const url = new URL(request.url || '/', requestOrigin(request));
      if (redirectToCanonicalHost({ request, response, url, serverOptions })) {
        return;
      }
      if (url.pathname.startsWith('/api/frist/')) {
        await handleCustomerApi({ request, response, url, store, serverOptions, securityState, newApiBridge });
        return;
      }
      if (url.pathname.startsWith('/api/admin/')) {
        await handleAdminApi({ request, response, url, store, serverOptions, securityState, newApiBridge });
        return;
      }
      if (url.pathname.startsWith('/api/ops/')) {
        await handleOpsApi({ request, response, url, store, serverOptions });
        return;
      }
      if (url.pathname.startsWith('/v1/') || ROOT_GATEWAY_PATHS.has(url.pathname)) {
        await handleGatewayApi({ request, response, url, store, serverOptions, newApiBridge });
        return;
      }

      await serveStaticFile({ request, response, url, publicDir: serverOptions.publicDir, serverOptions, store });
    } catch (error) {
      const url = new URL(request.url || '/', requestOrigin(request));
      if (url.pathname.startsWith('/api/admin/') && error?.statusCode === 401) {
        await recordAdminAuthFailure(store, request, url, serverOptions);
      }
      const message = error.expose ? error.message : '服务暂时不可用';
      writeJson(response, error.statusCode || 500, { error: message });
    }
  });
  if (Number.isFinite(serverOptions.keepAliveTimeoutMs)) {
    server.keepAliveTimeout = Number(serverOptions.keepAliveTimeoutMs);
  }
  if (serverOptions.channelMonitorEnabled) {
    server.on('listening', () => {
      if (stopChannelMonitor) {
        stopChannelMonitor();
      }
      stopChannelMonitor = startChannelMonitor({ store, serverOptions });
    });
    server.on('close', () => {
      if (stopChannelMonitor) {
        stopChannelMonitor();
        stopChannelMonitor = null;
      }
    });
  }
  if (serverOptions.newApiEnabled && serverOptions.newApiRedemptionStatusSyncEnabled) {
    server.on('listening', () => {
      if (stopRedemptionStatusSync) {
        stopRedemptionStatusSync();
      }
      stopRedemptionStatusSync = startNewApiRedemptionStatusSync({ store, serverOptions });
    });
    server.on('close', () => {
      if (stopRedemptionStatusSync) {
        stopRedemptionStatusSync();
        stopRedemptionStatusSync = null;
      }
    });
  }
  if (serverOptions.upstreamBalanceSyncEnabled && newApiBridge) {
    server.on('listening', () => {
      if (stopUpstreamBalanceSync) {
        stopUpstreamBalanceSync();
      }
      stopUpstreamBalanceSync = startUpstreamBalanceSync({ store, serverOptions, newApiBridge });
    });
    server.on('close', () => {
      if (stopUpstreamBalanceSync) {
        stopUpstreamBalanceSync();
        stopUpstreamBalanceSync = null;
      }
    });
  }
  if (serverOptions.cardAutoreplenishEnabled) {
    server.on('listening', () => {
      if (stopCardAutoreplenish) {
        stopCardAutoreplenish();
      }
      stopCardAutoreplenish = startCardAutoreplenish({ store, serverOptions });
    });
    server.on('close', () => {
      if (stopCardAutoreplenish) {
        stopCardAutoreplenish();
        stopCardAutoreplenish = null;
      }
    });
  }
  return server;
}

async function handleCustomerApi({ request, response, url, store, serverOptions, securityState, newApiBridge }) {
  if (request.method === 'GET' && url.pathname === '/api/frist/challenge') {
    assertAuthRateLimit(securityState, request, serverOptions);
    writeJson(response, 200, createCaptchaChallenge(securityState, serverOptions));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/register') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    await verifyTurnstileToken({ request, body, serverOptions, action: 'register' });
    requireCaptchaIfEnabled(securityState, body, serverOptions);
    const prepared = await store.mutate((data) => registerCustomer(data, body, serverOptions));
    await deliverAndRecordEmail(store, prepared.emailDelivery, serverOptions);
    const result = prepared.result;
    writeJson(response, 200, result.body, {
      'set-cookie': sessionCookies(result.sessionToken, result.csrfToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/login') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    await verifyTurnstileToken({ request, body, serverOptions, action: 'login' });
    const result = await store.mutate((data) => loginCustomer(data, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': sessionCookies(result.sessionToken, result.csrfToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return changeCustomerPassword(data, request, body, serverOptions);
    });
    writeJson(response, 200, result.body, {
      'set-cookie': sessionCookies(result.sessionToken, result.csrfToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/logout') {
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      const { token, user } = requireSession(data, request);
      delete data.sessions[token];
      delete data.sessionCsrfTokens[token];
      data.events.push({ type: 'logged_out', userId: user.id, at: currentDate(serverOptions).toISOString() });
      return { ok: true };
    });
    writeJson(response, 200, result, {
      'set-cookie': expiredSessionCookies(request, serverOptions),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password-reset/request') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    assertPasswordResetRequestRateLimit(securityState, body.email, serverOptions);
    const prepared = await store.mutate((data) => requestCustomerPasswordReset(data, body, serverOptions));
    await deliverAndRecordEmail(store, prepared.emailDelivery, serverOptions);
    writeJson(response, 200, prepared.result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/password-reset/confirm') {
    const body = await readJsonBody(request);
    assertAuthRateLimit(securityState, request, serverOptions);
    assertPasswordResetConfirmRateLimit(securityState, body.email, serverOptions);
    const result = await store.mutate((data) => confirmCustomerPasswordReset(data, body, serverOptions));
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/verify') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      const { user } = requireSession(data, request);
      assertEmailVerificationRateLimit(securityState, request, serverOptions, user.id);
      return verifyCustomer(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'PATCH' && url.pathname === '/api/frist/profile') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerProfile(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'PUT' && url.pathname === '/api/frist/balance-alert') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerBalanceAlert(data, request, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/balance-alert/test') {
    const body = await readJsonBody(request);
    const prepared = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return prepareCustomerBalanceAlertTest(data, request, body, serverOptions);
    });
    await prepared.sender(prepared.message);
    await store.mutate((data) => {
      data.events.push(prepared.event);
    });
    writeJson(response, 200, prepared.result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/recharge') {
    const body = await readJsonBody(request);
    const prepared = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return prepareRechargeCustomer(data, request, body, serverOptions);
    });
    if (!prepared.providerRequest) {
      const result = prepared.result;
      writeJson(response, result.status || 200, result.body || result);
      return;
    }

    let providerPayment;
    try {
      providerPayment = await createProviderPayment({
        ...prepared.providerRequest,
        fetchImpl: serverOptions.fetchImpl || globalThis.fetch,
        paymentConfig: serverOptions.paymentConfig,
      });
    } catch (error) {
      try {
        await store.mutate((data) => markProviderPaymentCreationFailed(
          data,
          prepared.providerRequest.order.id,
          error,
        ));
      } catch (persistError) {
        process.emitWarning(`支付渠道失败状态写入失败: ${persistError.message}`, {
          code: 'FRIST_API_PAYMENT_FAILURE_STATE_WRITE_FAILED',
        });
      }
      throw error;
    }
    const result = await store.mutate((data) => finalizeProviderPaymentCreation(
      data,
      prepared.providerRequest.order.id,
      providerPayment,
    ));
    writeJson(response, result.status || 200, result.body || result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/payments/wechat/notify') {
    const rawBody = await readRequestText(request);
    const result = await store.mutate((data) =>
      handleWechatPaymentNotification(data, request, rawBody, serverOptions),
    );
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/payments/alipay/notify') {
    const rawBody = await readRequestText(request);
    const result = await store.mutate((data) =>
      handleAlipayPaymentNotification(data, rawBody, serverOptions),
    );
    response.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    response.end(result.ok ? 'success' : 'fail');
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/redeem') {
    const body = await readJsonBody(request);
    assertRedeemRateLimit(securityState, request, serverOptions);
    await verifyTurnstileToken({ request, body, serverOptions, action: 'redeem' });
    if (newApiBridge) {
      const data = await store.load();
      requireCsrfIfEnabled(data, request, serverOptions);
      const { user } = requireSession(data, request);
      assertRedeemUserRateLimit(securityState, serverOptions, user.id);
      const result = await newApiBridge.redeemCode(body);
      const localResult = await store.mutate((currentData) =>
        recordLocalRedemptionAfterNewApiTopup(currentData, request, body, serverOptions),
      );
      result.user = localResult.user || sanitizeUser(user);
      result.account = localResult.account;
      result.localRedemption = localResult.redemption;
      writeJson(response, 200, result);
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return redeemCustomerCode(data, request, body, serverOptions, securityState);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/token') {
    const body = await readJsonBody(request);
    if (newApiBridge) {
      const result = await createOwnedNewApiToken({
        store,
        request,
        body,
        serverOptions,
        newApiBridge,
      });
      writeJson(response, 200, result);
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return createCustomerToken(data, request, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  const tokenMatch = url.pathname.match(/^\/api\/frist\/token\/([^/]+)$/);
  if (request.method === 'PATCH' && tokenMatch) {
    const body = await readJsonBody(request);
    if (newApiBridge) {
      const ownership = await store.mutate((data) => {
        requireCsrfIfEnabled(data, request, serverOptions);
        const { user } = requireSession(data, request);
        requireNewApiTokenOwner(data, user, tokenMatch[1]);
        return { userId: user.id };
      });
      const result = await newApiBridge.updateToken(tokenMatch[1], body);
      await store.mutate((data) => {
        const owner = data.newApiTokenOwners?.[String(tokenMatch[1])];
        const ownerId = typeof owner === 'string' ? owner : owner?.userId;
        if (ownerId !== ownership.userId) {
          throw publicError(409, 'API Key 归属在更新期间发生变化，请人工对账');
        }
        data.events.push({
          type: 'newapi_token_updated',
          userId: ownership.userId,
          keyId: String(tokenMatch[1]),
          at: currentDate(serverOptions).toISOString(),
        });
      });
      writeJson(response, 200, result);
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return updateCustomerToken(data, request, tokenMatch[1], body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'DELETE' && tokenMatch) {
    if (newApiBridge) {
      const ownership = await store.mutate((data) => {
        requireCsrfIfEnabled(data, request, serverOptions);
        const { user } = requireSession(data, request);
        requireNewApiTokenOwner(data, user, tokenMatch[1]);
        return { userId: user.id };
      });
      const result = await newApiBridge.deleteToken(tokenMatch[1]);
      await store.mutate((data) => {
        const owner = data.newApiTokenOwners?.[String(tokenMatch[1])];
        const ownerId = typeof owner === 'string' ? owner : owner?.userId;
        if (ownerId !== ownership.userId) {
          data.events.push({
            type: 'newapi_token_delete_reconciliation_required',
            userId: ownership.userId,
            keyId: String(tokenMatch[1]),
            at: currentDate(serverOptions).toISOString(),
          });
          return;
        }
        delete data.newApiTokenOwners[String(tokenMatch[1])];
        data.events.push({
          type: 'newapi_token_deleted',
          userId: ownership.userId,
          keyId: String(tokenMatch[1]),
          at: currentDate(serverOptions).toISOString(),
        });
      });
      writeJson(response, 200, result);
      return;
    }
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return deleteCustomerToken(data, request, tokenMatch[1]);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/import-url') {
    const data = await store.load();
    if (newApiBridge) {
      const { user } = requireSession(data, request);
      const keyId = String(url.searchParams.get('keyId') || '').trim();
      if (!keyId) {
        throw publicError(400, '请选择要导入的 API Key');
      }
      requireNewApiTokenOwner(data, user, keyId);
      const result = await newApiBridge.buildImportUrl(url, keyId, ({ target, apiKey, modelGroup, availableModels, defaultModel }) => {
        const baseUrl = serverOptions.publicGatewayBaseUrl || `${requestOrigin(request)}/v1`;
        const requestedModel = url.searchParams.get('model') || '';
        const config = buildClientConfig({
          target,
          apiKey,
          baseUrl,
          model: requestedModel || defaultModel,
          defaultModel,
          availableModels,
          modelGroup,
          planExpiresAt: user.planExpiresAt,
          preferExplicitDefaultModel: Boolean(requestedModel || defaultModel),
        });
        const setup = buildClientSetupCommands(config);
        return {
          url: config.ccSwitchUrl,
          config,
          setup,
          defaultModel,
          availableModels,
        };
      });
      writeJson(response, 200, result);
      return;
    }
    const result = buildCustomerImportUrl(data, request, url, serverOptions);
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/key-usage') {
    const data = await store.load();
    if (newApiBridge) {
      writeJson(response, 200, await newApiBridge.buildKeyUsage(request), {
        'cache-control': 'no-store',
      });
      return;
    }
    writeJson(response, 200, buildKeyUsagePayload(data, request, serverOptions), {
      'cache-control': 'no-store',
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/frist/dashboard') {
    const data = await store.load();
    const { token, user } = findSession(data, request);
    if (user && newApiBridge) {
      expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
      const dashboard = await newApiBridge.buildDashboard(data, user, serverOptions);
      dashboard.csrfToken = String(data.sessionCsrfTokens?.[token] || '');
      writeJson(response, 200, dashboard);
      return;
    }
    const dashboard = user ? buildDashboard(data, user, serverOptions) : buildGuestDashboard(data, serverOptions);
    if (user) {
      dashboard.csrfToken = String(data.sessionCsrfTokens?.[token] || '');
    }
    writeJson(response, 200, dashboard);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/frist/admin/claim') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireCsrfIfEnabled(data, request, serverOptions);
      return claimAdminIdentity(data, request, body, serverOptions);
    });
    writeJson(response, 200, result, adminGateCookie(serverOptions));
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function handleAdminApi({ request, response, url, store, serverOptions, securityState, newApiBridge }) {
  if (request.method === 'POST' && url.pathname === '/api/admin/2fa/verify') {
    const body = await readJsonBody(request);
    assertAdminSecondFactorRateLimit(securityState, request, serverOptions);
    const result = await store.mutate((data) => verifyAdminSecondFactor(data, request, body, serverOptions));
    writeJson(response, 200, result.body, {
      'set-cookie': adminSecondFactorCookie(result.sessionToken, request, serverOptions),
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/production-readiness') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, await buildProductionReadiness(data, serverOptions));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/backups/status') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return recordBackupStatus(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/pricing') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, pricingPayload(data));
    return;
  }

  if (request.method === 'PUT' && url.pathname === '/api/admin/pricing') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      data.pricing = normalizePricingConfig(body);
      data.priceDrafts = mergeModelPrices(data.priceDrafts, data.pricing.modelPrices);
      data.events.unshift({
        type: 'pricing_updated',
        detail: `套餐 ${data.pricing.rechargePlans.length} 个，模型价格 ${data.pricing.modelPrices.length} 个`,
        at: new Date().toISOString(),
      });
      return pricingPayload(data);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/replenishments') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      credentials: data.credentials.map(sanitizeCredential),
      supplierProfiles: data.supplierProfiles,
      priceDrafts: data.priceDrafts,
      paymentOrders: data.paymentOrders.map(sanitizePaymentOrder),
      redemptionCards: data.redemptionCards.map(sanitizeRedemptionCard),
      plusAccounts: data.plusAccounts.map((account) => sanitizePlusAccount(account, serverOptions)),
      plusAccountSummary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
      rtAccounts: data.rtAccounts.map(sanitizeRtAccount),
      rtAccountSummary: buildRtAccountSummary(data.rtAccounts),
      upstreamChannels: data.upstreamChannelSnapshots.map(sanitizeUpstreamChannel),
      upstreamBalance: sanitizeUpstreamBalance(data.upstreamBalance, serverOptions),
      channelSyncSummary: buildChannelSyncSummary(data, serverOptions),
      xianyuFulfillments: data.xianyuFulfillments.map(sanitizeXianyuFulfillment),
      xianyuSummary: buildXianyuFulfillmentSummary(data),
      xianyuAutomation: buildXianyuAutomationConfig(serverOptions),
      inventorySummary: buildInventorySummary(data),
      productionReadiness: await buildProductionReadiness(data, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/plus-accounts') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      accounts: data.plusAccounts.map((account) => sanitizePlusAccount(account, serverOptions)),
      summary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/plus-accounts') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return upsertPlusAccount(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/rt-accounts') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      accounts: data.rtAccounts.map(sanitizeRtAccount),
      summary: buildRtAccountSummary(data.rtAccounts),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/rt-accounts/import') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return importRtAccounts(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/redemption-cards') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      cards: data.redemptionCards.map(sanitizeRedemptionCard),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/redemption-cards/sync-newapi-status') {
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return syncNewApiRedemptionStatuses(data, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/redemption-cards/autoreplenish') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return autoReplenishRedemptionCards(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/redemption-cards') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return createRedemptionCards(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/upstream-balance') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      ok: true,
      balance: sanitizeUpstreamBalance(data.upstreamBalance, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/upstream-balance/sync') {
    if (!newApiBridge?.syncUpstreamBalance) {
      throw publicError(409, 'New-API 未启用，无法同步上游余额');
    }
    await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
    });
    const rawBalance = await newApiBridge.syncUpstreamBalance();
    const applied = await store.mutate((data) => applyUpstreamBalance(data, rawBalance, serverOptions));
    await notifyUpstreamBalanceIfNeeded(applied.balance, serverOptions);
    writeJson(response, 200, applied.result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/upstream-sync') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      rateMarkup: serverOptions.rateMarkup,
      channels: data.upstreamChannelSnapshots.map(sanitizeUpstreamChannel),
      summary: buildChannelSyncSummary(data, serverOptions),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/upstream-sync') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return syncUpstreamChannels(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/admin/xianyu/fulfillments') {
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    writeJson(response, 200, {
      fulfillments: data.xianyuFulfillments.map(sanitizeXianyuFulfillment),
      summary: buildXianyuFulfillmentSummary(data),
      availableCards: data.redemptionCards.filter((card) => card.status === 'unused').map(sanitizeRedemptionCard),
      events: sanitizeAdminEvents(data.events),
    });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/xianyu/fulfillments') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return createXianyuFulfillment(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments/parse-order') {
    const body = await readJsonBody(request);
    const data = await store.load();
    requireAdmin(data, request, serverOptions);
    requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
    const parsed = parseSupplierOrderText(body.orderText || '', body.pricing || {});
    writeJson(response, 200, sanitizeParsedOrder(parsed));
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/customers/recharge') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return manualRechargeCustomer(data, body);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/customers/password') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return adminResetCustomerPassword(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/admin/replenishments') {
    const body = await readJsonBody(request);
    const authorizationData = await store.load();
    requireAdmin(authorizationData, request, serverOptions);
    requireCsrfIfEnabled(authorizationData, request, serverOptions, { allowAdminToken: true });
    const prepared = await prepareCredentialReplenishment(body, serverOptions);
    const result = await store.mutate((data) => {
      requireAdmin(data, request, serverOptions);
      requireCsrfIfEnabled(data, request, serverOptions, { allowAdminToken: true });
      return applyCredentialReplenishment(data, prepared, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function recordAdminAuthFailure(store, request, url, serverOptions) {
  try {
    await store.mutate((data) => {
      // 只保留最近 50 条管理认证失败，避免攻击流量持续放大 runtime 文件。
      let failuresToRemove = Math.max(
        0,
        data.events.filter((event) => event.type === 'admin_auth_failed').length - 49,
      );
      for (let index = 0; index < data.events.length && failuresToRemove > 0; index += 1) {
        if (data.events[index].type === 'admin_auth_failed') {
          data.events.splice(index, 1);
          index -= 1;
          failuresToRemove -= 1;
        }
      }
      data.events.push({
        type: 'admin_auth_failed',
        path: url.pathname,
        ipHash: hashId(clientIp(request, serverOptions)),
        at: new Date().toISOString(),
      });
    });
  } catch (error) {
    process.emitWarning(`CC中转 管理认证失败审计写入失败: ${error.message}`, {
      code: 'FRIST_API_ADMIN_AUDIT_WRITE_FAILED',
    });
  }
}

async function handleOpsApi({ request, response, url, store, serverOptions }) {
  if (request.method === 'POST' && url.pathname === '/api/ops/xianyu/paid-order') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireXianyuWebhook(request, serverOptions);
      return fulfillPaidXianyuOrder(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/ops/xianyu/remap-order') {
    const body = await readJsonBody(request);
    const result = await store.mutate((data) => {
      requireXianyuWebhook(request, serverOptions);
      return remapXianyuFulfillmentOrder(data, body, serverOptions);
    });
    writeJson(response, 200, result);
    return;
  }

  writeJson(response, 404, { error: '接口不存在' });
}

async function handleGatewayApi({ request, response, url, store, serverOptions, newApiBridge }) {
  if (newApiBridge && serverOptions.newApiGatewayEnabled) {
    const newApiPostPaths = [
      '/v1/chat/completions',
      '/v1/openai/chat/completions',
      '/chat/completions',
      '/openai/chat/completions',
      '/v1/responses',
      '/v1/openai/responses',
      '/responses',
      '/openai/responses',
      '/v1/images/generations',
      '/v1/openai/images/generations',
      '/images/generations',
      '/openai/images/generations',
      '/v1/messages',
      '/messages',
    ];
    const canProxyNewApiGateway =
      (request.method === 'POST' && newApiPostPaths.includes(url.pathname)) ||
      (request.method === 'GET' && url.pathname === '/v1/models');
    if (canProxyNewApiGateway) {
      const bodyText = request.method === 'POST' ? await readRequestText(request) : '';
      const localData = await store.load();
      if (await newApiBridge.proxyGateway({ request, response, url, bodyText, localData })) {
        return;
      }
    }
    if (request.method === 'POST') {
      writeJson(response, 404, { error: '接口不存在' });
      return;
    }
  }

  if (request.method === 'GET' && url.pathname === '/v1/models') {
    const data = await store.load();
    const result = buildGatewayModels(data, request);
    writeJson(response, 200, result);
    return;
  }

  const chatCompletionRouteOptions = {
    upstreamAttempts: [
      { upstreamPath: '/chat/completions' },
      {
        upstreamPath: '/responses',
        transformRequest: chatCompletionRequestToResponses,
        transformResponse: responsesToChatCompletionResponse,
      },
    ],
  };
  const responsesRouteOptions = {
    upstreamAttempts: [
      { upstreamPath: '/responses' },
      {
        upstreamPath: '/chat/completions',
        transformRequest: responsesRequestToChatCompletion,
        transformResponse: chatCompletionToResponsesResponse,
      },
    ],
  };
  const anthropicMessagesRouteOptions = {
    upstreamAttempts: [
      {
        upstreamPath: '/messages',
        validateResponse: isAnthropicMessagePayload,
      },
      {
        upstreamPath: '/chat/completions',
        transformRequest: anthropicMessagesToChatCompletion,
        transformResponse: chatCompletionToAnthropicMessageResponse,
      },
    ],
  };

  const upstreamPathByRoute = new Map([
    ['/v1/chat/completions', chatCompletionRouteOptions],
    ['/v1/openai/chat/completions', chatCompletionRouteOptions],
    ['/chat/completions', chatCompletionRouteOptions],
    ['/openai/chat/completions', chatCompletionRouteOptions],
    ['/v1/responses', responsesRouteOptions],
    ['/v1/openai/responses', responsesRouteOptions],
    ['/responses', responsesRouteOptions],
    ['/openai/responses', responsesRouteOptions],
    ['/v1/images/generations', { upstreamPath: '/images/generations' }],
    ['/v1/openai/images/generations', { upstreamPath: '/images/generations' }],
    ['/images/generations', { upstreamPath: '/images/generations' }],
    ['/openai/images/generations', { upstreamPath: '/images/generations' }],
    ['/v1/messages', anthropicMessagesRouteOptions],
    ['/messages', anthropicMessagesRouteOptions],
  ]);
  const routeOptions = upstreamPathByRoute.get(url.pathname);
  if (request.method !== 'POST' || !routeOptions) {
    writeJson(response, 404, { error: '接口不存在' });
    return;
  }

  const body = await readJsonBody(request);
  if (serverOptions.enforceProductionReadiness) {
    throw publicError(503, '生产环境仅允许通过 New-API 网关处理模型请求');
  }
  const result = await store.mutateBlocking((data) =>
    routeChatCompletion(data, request, body, serverOptions, { ...routeOptions, request }),
  );
  response.writeHead(result.status, {
    'content-type': result.contentType,
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
    ...(result.bodyStream ? { 'x-accel-buffering': 'no' } : {}),
  });
  if (result.bodyStream) {
    await pipeReadableStreamToResponse(result.bodyStream, response, { abort: result.abort });
    return;
  }
  response.end(result.bodyText);
}

async function deliverAndRecordEmail(store, delivery, serverOptions) {
  if (!delivery) {
    return;
  }
  const event = await scheduleEmailDelivery({ serverOptions, ...delivery });
  try {
    await store.mutate((data) => {
      data.events.push(event);
    });
  } catch (error) {
    process.emitWarning(`邮件投递事件写入失败: ${error.message}`, {
      code: 'FRIST_API_EMAIL_EVENT_WRITE_FAILED',
    });
  }
}

function registerCustomer(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  if (password.length < 6) {
    throw publicError(400, '密码至少 6 位');
  }

  const now = new Date().toISOString();
  const verificationCode = serverOptions.requireEmailVerification ? generateVerificationCode() : '';
  let user = data.users.find((item) => item.email === email);
  if (user) {
    throw publicError(409, '邮箱已注册，请直接登录');
  }

  user = {
    id: createId('user'),
    email,
    emailVerified: !serverOptions.requireEmailVerification,
    passwordHash: hashPassword(password, serverOptions.passwordHashSecret),
    displayName: email.split('@')[0],
    verificationCode,
    plan: '默认套餐',
    renewalDate: formatDate(addDays(new Date(), 30)),
    planExpiresAt: '',
    balanceCents: 0,
    packageQuotaCents: 0,
    boosterQuotaCents: 0,
    balanceAlert: defaultBalanceAlert(email),
    createdAt: now,
    updatedAt: now,
  };
  data.users.push(user);

  const { sessionToken, csrfToken } = issueCustomerSession(data, user, serverOptions);
  data.events.push({ type: 'registered', userId: user.id, at: now });

  const responseUser = sanitizeUser(user);
  const result = {
    sessionToken,
    csrfToken,
    body: {
      user: responseUser,
      csrfToken,
      ...(serverOptions.exposeVerificationCode && verificationCode ? { verificationCode } : {}),
    },
  };
  let emailDelivery = null;
  if (verificationCode) {
    emailDelivery = {
      to: email,
      message: buildVerificationEmail({
        user,
        code: verificationCode,
        publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
        at: now,
      }),
      data,
      successType: 'email_verification_sent',
      failureType: 'email_verification_failed',
      eventBase: { userId: user.id, email: maskEmail(email) },
    };
  }
  return { result, emailDelivery };
}

function loginCustomer(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  const user = data.users.find((item) => item.email === email);
  const passwordResult = verifyPassword(password, user?.passwordHash, serverOptions.passwordHashSecrets);
  if (!user || !passwordResult.ok) {
    throw publicError(401, '邮箱或密码不正确');
  }

  const now = new Date().toISOString();
  if (!isModernPasswordHash(user.passwordHash) || passwordResult.secret !== serverOptions.passwordHashSecret) {
    user.passwordHash = hashPassword(password, serverOptions.passwordHashSecret);
    data.events.push({ type: 'password_hash_upgraded', userId: user.id, at: now });
  }
  const { sessionToken, csrfToken } = issueCustomerSession(data, user, serverOptions);
  user.updatedAt = now;
  data.events.push({ type: 'logged_in', userId: user.id, at: now });
  return {
    sessionToken,
    csrfToken,
    body: {
      user: sanitizeUser(user),
      account: accountFromUser(data, user),
      csrfToken,
    },
  };
}

function changeCustomerPassword(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const oldPassword = String(body.oldPassword || '');
  const newPassword = String(body.newPassword || '');
  if (!verifyPassword(oldPassword, user.passwordHash, serverOptions.passwordHashSecrets).ok) {
    throw publicError(401, '旧密码不正确');
  }
  if (newPassword.length < 6) {
    throw publicError(400, '新密码至少 6 位');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(newPassword, serverOptions.passwordHashSecret);
  user.updatedAt = now;
  revokeCustomerSessions(data, user.id);
  const { sessionToken, csrfToken } = issueCustomerSession(data, user, serverOptions);
  data.events.push({ type: 'password_changed', userId: user.id, at: now });
  return {
    sessionToken,
    csrfToken,
    body: { user: sanitizeUser(user), account: accountFromUser(data, user), csrfToken },
  };
}

function requestCustomerPasswordReset(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  const now = new Date().toISOString();
  const user = data.users.find((item) => item.email === email);
  if (user) {
    const code = generateVerificationCode();
    user.passwordReset = {
      codeHash: hashPasswordResetCode(code, serverOptions.passwordHashSecret),
      expiresAt: new Date(Date.now() + Number(serverOptions.passwordResetTtlMs || 900_000)).toISOString(),
      usedAt: '',
      requestedAt: now,
    };
    user.updatedAt = now;
    data.events.push({ type: 'password_reset_requested', userId: user.id, email: maskEmail(email), at: now });
    const emailDelivery = {
      to: email,
      message: buildPasswordResetEmail({
        user,
        code,
        publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
        expiresMinutes: Math.max(1, Math.round(Number(serverOptions.passwordResetTtlMs || 900_000) / 60_000)),
        at: now,
      }),
      data,
      successType: 'password_reset_email_sent',
      failureType: 'password_reset_email_failed',
      eventBase: { userId: user.id, email: maskEmail(email) },
    };
    return {
      emailDelivery,
      result: {
      ok: true,
      message: '如果邮箱存在，我们会发送重置验证码。',
      ...(serverOptions.exposeVerificationCode ? { resetCode: code } : {}),
      },
    };
  }
  data.events.push({ type: 'password_reset_requested_unknown', email: maskEmail(email), at: now });
  return {
    emailDelivery: null,
    result: { ok: true, message: '如果邮箱存在，我们会发送重置验证码。' },
  };
}

function confirmCustomerPasswordReset(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const code = String(body.code || '').trim();
  const newPassword = String(body.newPassword || body.password || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '邮箱格式不正确');
  }
  if (!code) {
    throw publicError(400, '重置验证码不能为空');
  }
  if (newPassword.length < 6) {
    throw publicError(400, '新密码至少 6 位');
  }
  const user = data.users.find((item) => item.email === email);
  const reset = user?.passwordReset;
  if (!user || !reset?.codeHash || reset.usedAt) {
    throw publicError(400, '重置验证码无效或已过期');
  }
  if (Date.parse(reset.expiresAt || '') <= Date.now()) {
    throw publicError(400, '重置验证码无效或已过期');
  }
  if (!safeEqual(reset.codeHash, hashPasswordResetCode(code, serverOptions.passwordHashSecret))) {
    throw publicError(400, '重置验证码无效或已过期');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(newPassword, serverOptions.passwordHashSecret);
  user.passwordReset = { ...reset, usedAt: now };
  user.updatedAt = now;
  revokeCustomerSessions(data, user.id);
  data.events.push({ type: 'password_reset_confirmed', userId: user.id, at: now });
  return { ok: true, message: '密码已重置，请用新密码登录。' };
}

function verifyCustomer(data, request, body) {
  const { user } = requireSession(data, request);
  if (!user.verificationCode && user.emailVerified) {
    return { user: sanitizeUser(user) };
  }
  if (String(body.code || '') !== user.verificationCode) {
    throw publicError(400, '验证码不正确');
  }
  user.emailVerified = true;
  user.verificationCode = '';
  user.updatedAt = new Date().toISOString();
  data.events.push({ type: 'email_verified', userId: user.id, at: user.updatedAt });
  return { user: sanitizeUser(user) };
}

function updateCustomerProfile(data, request, body) {
  const { user } = requireSession(data, request);
  const displayName = String(body.displayName ?? body.nickname ?? '').trim();
  const nextEmail = String(body.email ?? user.email ?? '').trim().toLowerCase();
  const avatarUrl = sanitizeAvatarUrl(body.avatarUrl ?? user.avatarUrl ?? '');
  if (!displayName || displayName.length > 40) {
    throw publicError(400, '昵称需要 1-40 个字符');
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(nextEmail)) {
    throw publicError(400, '邮箱格式不正确');
  }
  const oldEmail = String(user.email || '').toLowerCase();
  if (nextEmail !== oldEmail && data.users.some((item) => item.id !== user.id && item.email === nextEmail)) {
    throw publicError(409, '邮箱已被占用');
  }

  const now = new Date().toISOString();
  user.displayName = displayName.slice(0, 40);
  user.avatarUrl = avatarUrl;
  if (nextEmail !== oldEmail) {
    const previousAlertEmail = normalizeAlertEmail(user.balanceAlert?.email || '');
    user.email = nextEmail;
    user.emailVerified = false;
    user.verificationCode = '';
    if (!previousAlertEmail || previousAlertEmail === oldEmail) {
      user.balanceAlert = {
        ...normalizeBalanceAlertRecord(user.balanceAlert, nextEmail),
        email: nextEmail,
        updatedAt: now,
      };
    }
  }
  user.updatedAt = now;
  data.events.push({
    type: 'profile_updated',
    userId: user.id,
    emailChanged: nextEmail !== oldEmail,
    at: now,
  });
  return {
    user: sanitizeUser(user),
    account: accountFromUser(data, user),
    balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email),
  };
}

function updateCustomerBalanceAlert(data, request, body) {
  const { user } = requireSession(data, request);
  const thresholdCents = normalizeAlertThresholdCents(body);
  const email = normalizeAlertEmail(body.email || user.balanceAlert?.email || user.email);
  const enabled = Object.prototype.hasOwnProperty.call(body, 'enabled') ? Boolean(body.enabled) : true;
  if (!Number.isFinite(thresholdCents) || thresholdCents <= 0 || thresholdCents > 1_000_000_00) {
    throw publicError(400, '余额预警阈值必须在 $0.01 ~ $1,000,000.00 之间');
  }
  if (!email) {
    throw publicError(400, '预警邮箱格式不正确');
  }

  const now = new Date().toISOString();
  user.balanceAlert = {
    enabled,
    thresholdCents,
    email,
    lastAlertAt: '',
    lastAlertBalanceCents: 0,
    lastTriggeredThresholdCents: 0,
    updatedAt: now,
  };
  user.updatedAt = now;
  data.events.push({
    type: 'balance_alert_updated',
    userId: user.id,
    thresholdCents,
    enabled,
    alertEmail: maskEmail(email),
    at: now,
  });
  return { balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email) };
}

function prepareCustomerBalanceAlertTest(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const current = normalizeBalanceAlertRecord(user.balanceAlert, user.email);
  const email = normalizeAlertEmail(body.email || current.email || user.email);
  const thresholdCents = normalizeAlertThresholdCents(body, current.thresholdCents);
  if (!email) {
    throw publicError(400, '预警邮箱格式不正确');
  }
  if (!Number.isFinite(thresholdCents) || thresholdCents <= 0 || thresholdCents > 1_000_000_00) {
    throw publicError(400, '余额预警阈值必须在 $0.01 ~ $1,000,000.00 之间');
  }
  const sender = serverOptions.balanceAlertEmailSender;
  if (typeof sender !== 'function') {
    throw publicError(503, 'SMTP 邮件服务未配置');
  }

  const now = new Date().toISOString();
  const message = buildBalanceAlertEmail({
    user,
    to: email,
    thresholdCents,
    balanceCents: availableQuotaCents(user),
    previousBalanceCents: availableQuotaCents(user),
    model: String(body.model || '测试邮件'),
    quotaCost: 0,
    publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
    at: now,
    isTest: true,
  });
  const event = {
    type: 'balance_alert_test_sent',
    userId: user.id,
    alertEmail: maskEmail(email),
    thresholdCents,
    at: now,
  };
  return {
    sender,
    message,
    event,
    result: { ok: true, balanceAlert: sanitizeBalanceAlert({ ...current, email, thresholdCents }, user.email) },
  };
}

function claimAdminIdentity(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = String(body.code || '').trim();
  const codeHash = hashAdminClaimCode(code);
  const allowedHashes = serverOptions.adminClaimCodeHashes || [];
  if (!code || allowedHashes.length === 0 || !allowedHashes.includes(codeHash)) {
    throw publicError(403, '身份码无效');
  }
  if (data.usedAdminClaimCodeHashes.includes(codeHash)) {
    throw publicError(409, '身份码已失效');
  }

  const now = new Date().toISOString();
  user.isAdmin = true;
  user.updatedAt = now;
  data.usedAdminClaimCodeHashes.push(codeHash);
  data.events.push({ type: 'admin_claimed', userId: user.id, at: now });
  return {
    user: sanitizeUser(user),
    adminUrl: '/admin.html',
    message: '管理员身份已激活',
  };
}

function verifyAdminSecondFactor(data, request, body, serverOptions) {
  requireAdmin(data, request, serverOptions, { allowPendingSecondFactor: true });
  if (!serverOptions.requireAdmin2fa) {
    return {
      sessionToken: '',
      body: {
        ok: true,
        secondFactorRequired: false,
        message: '管理员 2FA 未启用',
      },
    };
  }
  const code = String(body.code || body.totp || '').replace(/\s+/g, '');
  if (!verifyTotpCode(serverOptions.adminTotpSecrets, code, serverOptions.nowFactory())) {
    throw publicError(401, '管理员 2FA 验证码无效');
  }
  const now = currentDate(serverOptions).toISOString();
  const sessionToken = createId('mfa');
  data.adminSecondFactorSessions[runtimeTokenKey(sessionToken)] = {
    createdAt: now,
    expiresAt: new Date(currentDate(serverOptions).getTime() + Number(serverOptions.admin2faSessionTtlMs || 3_600_000)).toISOString(),
    ipHash: hashId(clientIp(request, serverOptions)),
  };
  pruneAdminSecondFactorSessions(data, serverOptions);
  data.events.push({
    type: 'admin_2fa_verified',
    ipHash: hashId(clientIp(request, serverOptions)),
    at: now,
  });
  return {
    sessionToken,
    body: {
      ok: true,
      secondFactorRequired: false,
      message: '管理员 2FA 已通过',
    },
  };
}

function prepareRechargeCustomer(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const selectedPlan = findRechargePlan(data, body);
  const amountCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.amountCny || 0) * 100);
  const creditCents = selectedPlan ? planCreditCents(selectedPlan) : amountCents;
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : normalizeRechargePlan(body.plan);
  if (!Number.isFinite(amountCents) || amountCents <= 0 || !Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '充值金额必须大于 0');
  }

  if (!serverOptions.allowDemoRecharge) {
    const now = new Date().toISOString();
    const method = normalizePaymentMethod(body.method);
    const paymentOrder = {
      id: createId('pay'),
      userId: user.id,
      email: user.email,
      amountCents,
      creditCents,
      quotaUsd: selectedPlan?.quotaUsd || 0,
      planId: selectedPlan?.id || '',
      plan: planType,
      method,
      provider: paymentProviderForMethod(method),
      status: paymentProviderForMethod(method) ? 'pending_provider_payment' : 'pending_manual_payment',
      createdAt: now,
      updatedAt: now,
    };
    const provider = paymentProviderForMethod(method);
    if (provider) {
      if (!providerReady(serverOptions.paymentConfig, provider)) {
        throw publicError(503, provider === 'wechat' ? '微信支付接口未配置完成' : '支付宝接口未配置完成');
      }
    }
    data.paymentOrders.unshift(paymentOrder);
    data.events.push({
      type: 'payment_order_created',
      userId: user.id,
      amountCents,
      creditCents,
      plan: paymentOrder.plan,
      method: paymentOrder.method,
      provider: paymentOrder.provider || '',
      at: now,
    });
    if (provider) {
      return {
        providerRequest: {
          provider,
          order: { ...paymentOrder },
          plan: selectedPlan ? { label: selectedPlan.label } : null,
        },
      };
    }
    return { result: buildRechargeResponse(data, user, paymentOrder) };
  }

  if (planType === 'day') {
    user.plan = '日卡';
    const expiresAt = addDays(currentDate(serverOptions), 1);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += creditCents;
  } else {
    user.boosterQuotaCents += creditCents;
  }
  reconcileUserBalance(user);
  user.updatedAt = new Date().toISOString();
  data.events.push({
    type: 'recharged',
    userId: user.id,
    amountCents,
    creditCents,
    method: String(body.method || 'manual'),
    at: user.updatedAt,
  });
  return {
    result: {
      status: 200,
      body: { account: accountFromUser(data, user), user: sanitizeUser(user) },
    },
  };
}

// 渠道请求成功后只写回二维码等展示字段，不覆盖可能已经由异步通知确认的已支付状态。
function finalizeProviderPaymentCreation(data, orderId, providerPayment) {
  const order = data.paymentOrders.find((item) => item.id === orderId);
  if (!order) {
    throw publicError(404, '支付订单不存在');
  }
  if (!order.provider || order.provider !== providerPayment.provider) {
    throw publicError(409, '支付订单渠道不匹配');
  }
  if (!['pending_provider_payment', 'paid', 'confirmed'].includes(order.status)) {
    throw publicError(409, '支付订单状态不允许写入渠道结果');
  }
  order.providerOrder = sanitizeProviderPayment(providerPayment);
  order.notifyUrl = providerPayment.notifyUrl;
  order.qrCode = providerPayment.qrCode;
  order.updatedAt = new Date().toISOString();
  const user = data.users.find((item) => item.id === order.userId);
  if (!user) {
    throw publicError(404, '支付订单用户不存在');
  }
  return buildRechargeResponse(data, user, order);
}

// 渠道创建失败时把订单收口到不可自动入账状态，保留人工核对证据。
function markProviderPaymentCreationFailed(data, orderId, error) {
  const order = data.paymentOrders.find((item) => item.id === orderId);
  if (!order || order.status !== 'pending_provider_payment' || order.qrCode) {
    return;
  }
  const now = new Date().toISOString();
  order.status = 'provider_creation_failed';
  order.updatedAt = now;
  order.failureReason = Number(error?.statusCode) === 504 ? 'timeout' : 'provider_error';
  data.events.push({
    type: 'payment_provider_creation_failed',
    orderId: order.id,
    provider: order.provider || '',
    reason: order.failureReason,
    at: now,
  });
}

function buildRechargeResponse(data, user, paymentOrder) {
  return {
    status: 202,
    body: {
      paymentOrder: sanitizePaymentOrder(paymentOrder),
      provider: paymentOrder.provider || '',
      qrCode: paymentOrder.qrCode || '',
      account: accountFromUser(data, user),
      user: sanitizeUser(user),
    },
  };
}

function adminResetCustomerPassword(data, body, serverOptions) {
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || body.newPassword || '');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw publicError(400, '用户邮箱格式不正确');
  }
  if (password.length < 10) {
    throw publicError(400, '新密码至少 10 位');
  }
  const user = data.users.find((item) => item.email === email);
  if (!user) {
    throw publicError(404, '用户不存在');
  }

  const now = new Date().toISOString();
  user.passwordHash = hashPassword(password, serverOptions.passwordHashSecret);
  user.passwordReset = {
    codeHash: '',
    expiresAt: '',
    usedAt: now,
    requestedAt: now,
  };
  user.updatedAt = now;
  revokeCustomerSessions(data, user.id);
  data.events.push({ type: 'admin_password_reset', userId: user.id, email: maskEmail(email), at: now });
  return {
    ok: true,
    user: sanitizeUser(user),
    message: '用户密码已重置',
    events: sanitizeAdminEvents(data.events),
  };
}

function manualRechargeCustomer(data, body) {
  const email = String(body.email || '').trim().toLowerCase();
  const selectedPlan = findRechargePlan(data, body);
  const amountCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.amountCny || 0) * 100);
  const creditCents = selectedPlan ? planCreditCents(selectedPlan) : amountCents;
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : String(body.plan || 'balance').trim().toLowerCase();
  if (!email) {
    throw publicError(400, '用户邮箱不能为空');
  }
  if (!Number.isFinite(amountCents) || amountCents <= 0 || !Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '充值金额必须大于 0');
  }

  const user = data.users.find((item) => item.email === email);
  if (!user) {
    throw publicError(404, '用户不存在');
  }

  const now = new Date().toISOString();
  if (planType === 'day' || planType === 'month') {
    const days = planType === 'day' ? 1 : 30;
    user.plan = planType === 'day' ? '日卡' : '月卡';
    const expiresAt = addDays(new Date(now), days);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
    user.packageQuotaCents += creditCents;
  } else {
    user.boosterQuotaCents += creditCents;
  }
  reconcileUserBalance(user);
  user.updatedAt = now;

  const pendingOrder = data.paymentOrders.find(
    (order) =>
      order.userId === user.id &&
      order.status === 'pending_manual_payment' &&
      (String(body.paymentOrderId || '') ? order.id === body.paymentOrderId : Number(order.amountCents) === amountCents),
  );
  if (pendingOrder) {
    pendingOrder.status = 'confirmed';
    pendingOrder.confirmedAt = now;
    pendingOrder.updatedAt = now;
  }

  data.events.push({
    type: 'manual_recharged',
    userId: user.id,
    amountCents,
    creditCents,
    plan: planType,
    method: String(body.method || 'manual_confirmed'),
    at: now,
  });

  return {
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    paymentOrder: pendingOrder ? sanitizePaymentOrder(pendingOrder) : null,
    events: sanitizeAdminEvents(data.events),
  };
}

function buildRedemptionBillingStatus() {
  return {
    ready: true,
    mode: 'redemption_code',
    detail: '当前处于生产环境内测，暂未正式售卖；兑换码仅用于内测验证和人工发放，CC中转站内核销到账；自动支付商户仅作为未来备用。',
  };
}

function findRechargePlan(data, body = {}) {
  const plans = normalizePricingConfig(data.pricing || {}).rechargePlans;
  const requestedId = String(body.planId || '').trim();
  if (requestedId) {
    return plans.find((plan) => plan.id === requestedId) || LEGACY_RECHARGE_PLAN_ALIASES.get(requestedId) || null;
  }
  const requestedPlan = String(body.plan || '').trim().toLowerCase();
  const amountCny = Number(body.amountCny || 0);
  return (
    plans.find(
      (plan) =>
        normalizeRechargePlan(plan.plan) === normalizeRechargePlan(requestedPlan) &&
        Math.abs(Number(plan.priceCny || 0) - amountCny) < 0.001,
    ) ||
    plans.find((plan) => Math.abs(Number(plan.priceCny || 0) - amountCny) < 0.001) ||
    null
  );
}

function planCreditCents(plan) {
  if (String(plan?.id || '').startsWith('xianyu-')) {
    return planPriceCents(plan);
  }
  return Math.round(Number(plan.quotaUsd || 0) * DEFAULT_USD_TO_CNY * 100);
}

function planPriceCents(plan) {
  return Math.round(Number(plan.priceCny || 0) * 100);
}

function buildRechargeOptions(data) {
  return normalizePricingConfig(data.pricing || {}).rechargePlans.map((plan, index) => ({
    id: plan.id,
    label: plan.label,
    quotaUsd: plan.quotaUsd,
    priceCny: plan.priceCny,
    durationDays: plan.durationDays,
    plan: plan.plan,
    cny: `¥${Number(plan.priceCny || 0).toFixed(2)}`,
    quota: `$${Number(plan.quotaUsd || 0).toFixed(0)}`,
    active: index === 0,
  }));
}

function createRedemptionCards(data, body, serverOptions = {}) {
  const selectedPlan = findRechargePlan(data, body);
  const planType = selectedPlan ? normalizeRechargePlan(selectedPlan.plan) : normalizeRechargePlan(body.plan);
  const quantity = clampInteger(body.quantity, 1, 200);
  const now = new Date().toISOString();
  const prefix = normalizeCardPrefix(body.prefix || DEFAULT_CARD_BATCH_PREFIX);
  const label = String(body.label || selectedPlan?.label || cardLabelForPlan(planType, body)).trim();
  const priceCents = selectedPlan ? planPriceCents(selectedPlan) : Math.round(Number(body.priceCny || 0) * 100);
  const creditCents = selectedPlan
    ? planCreditCents(selectedPlan)
    : Math.round(Number(body.quotaUsd || body.creditUsd || 0) * DEFAULT_USD_TO_CNY * 100);
  const quotaUsd = selectedPlan ? Number(selectedPlan.quotaUsd || 0) : round2(Number(body.quotaUsd || body.creditUsd || 0));
  const durationDays = selectedPlan
    ? Number(selectedPlan.durationDays || 0)
    : planType === 'day'
      ? 1
      : planType === 'month'
        ? 30
        : Math.max(0, Number(body.durationDays || 0));

  if (!Number.isFinite(creditCents) || creditCents <= 0) {
    throw publicError(400, '卡密额度必须大于 0');
  }
  if (!label) {
    throw publicError(400, '卡密名称不能为空');
  }

  const batchId = createId('batch');
  const cards = [];
  const existingPlainCodes = new Set([
    ...data.redemptionCards.map((card) => normalizeCardCode(card.code)).filter(Boolean),
    ...data.redemptions.map((item) => normalizeCardCode(item.code)).filter(Boolean),
    ...LEGACY_CARD_CODES.keys(),
  ]);
  const existingCodeHashes = new Set([
    ...data.redemptionCards.map((card) => card.codeHash).filter(Boolean),
    ...data.redemptions.map((item) => item.codeHash).filter(Boolean),
    ...[...LEGACY_CARD_CODES.keys()].map(hashRedemptionCode),
  ]);
  for (let index = 0; index < quantity; index += 1) {
    let code = '';
    let codeHash = '';
    for (let attempt = 0; attempt < 20; attempt += 1) {
      code = `${prefix}-${randomCardCodeSegment()}-${randomCardCodeSegment()}`;
      codeHash = hashRedemptionCode(code);
      if (!existingPlainCodes.has(code) && !existingCodeHashes.has(codeHash)) break;
    }
    if (!code || existingPlainCodes.has(code) || existingCodeHashes.has(codeHash)) {
      throw publicError(500, '卡密生成失败，请重试');
    }
    existingPlainCodes.add(code);
    existingCodeHashes.add(codeHash);
    const card = {
      id: createId('card'),
      batchId,
      codeHash,
      codeCipher: encryptCardCode(code, serverOptions),
      codePreview: maskCardCode(code),
      label,
      planId: selectedPlan?.id || '',
      plan: planType,
      durationDays,
      quotaUsd,
      priceCny: round2(priceCents / 100),
      creditCents,
      status: 'unused',
      source: 'xianyu',
      note: String(body.note || '').trim(),
      createdAt: now,
      updatedAt: now,
      redeemedAt: '',
      redeemedBy: '',
      redeemedEmail: '',
    };
    data.redemptionCards.unshift(card);
    cards.push({ ...card, code });
  }

  data.events.push({
    type: 'redemption_cards_created',
    batchId,
    count: cards.length,
    plan: planType,
    creditCents,
    at: now,
  });
  const newApiSync = syncNewApiRedemptionCards(cards, serverOptions);
  if (newApiSync.synced > 0) {
    data.events.push({
      type: 'newapi_redemption_cards_synced',
      batchId,
      count: newApiSync.synced,
      at: now,
    });
  }
  return {
    batchId,
    cards: cards.map(sanitizeRedemptionCard),
    exportText: buildRedemptionCardExport(cards),
    events: sanitizeAdminEvents(data.events),
    newApiSync,
  };
}

function buildCardAutoreplenishPlanRows(data, serverOptions = {}) {
  const pricing = normalizePricingConfig(data.pricing || {});
  const safetyStock = serverOptions.cardAutoreplenishSafetyStock || DEFAULT_CARD_AUTOREPLENISH_SAFETY_STOCK;
  return pricing.rechargePlans
    .map((plan) => {
      const currentUnused = data.redemptionCards.filter((card) => {
        if (card.status !== 'unused') return false;
        if (String(card.planId || '') === plan.id) return true;
        return Math.abs(Number(card.quotaUsd || 0) - Number(plan.quotaUsd || 0)) < 0.001 &&
          normalizeRechargePlan(card.plan) === normalizeRechargePlan(plan.plan);
      }).length;
      const safeCount = Math.max(0, Number(safetyStock[plan.id] ?? 0));
      return {
        planId: plan.id,
        label: plan.label,
        quotaUsd: Number(plan.quotaUsd || 0),
        priceCny: Number(plan.priceCny || 0),
        plan: normalizeRechargePlan(plan.plan),
        safetyStock: safeCount,
        currentUnused,
        toCreate: Math.max(0, safeCount - currentUnused),
        created: 0,
      };
    })
    .filter((row) => row.safetyStock > 0);
}

function autoReplenishRedemptionCards(data, body = {}, serverOptions = {}) {
  const now = currentDate(serverOptions).toISOString();
  const dryRun = body.dryRun === true;
  const enabled = body.enabled === true || serverOptions.cardAutoreplenishEnabled || !dryRun;
  const dailyCap = Math.max(0, Number(serverOptions.cardAutoreplenishDailyCap || 0));
  const today = now.slice(0, 10);
  const dailyCreated = data.events
    .filter((event) => event.type === 'redemption_cards_autoreplenished' && String(event.at || '').startsWith(today))
    .reduce((sum, event) => sum + Number(event.created || 0), 0);
  let remainingDaily = Math.max(0, dailyCap - dailyCreated);
  const plans = buildCardAutoreplenishPlanRows(data, serverOptions);
  let totalCreated = 0;
  const batches = [];

  for (const row of plans) {
    row.toCreate = Math.min(row.toCreate, remainingDaily);
    if (!enabled || dryRun || row.toCreate <= 0) {
      continue;
    }
    const created = createRedemptionCards(data, {
      planId: row.planId,
      quantity: row.toCreate,
      prefix: DEFAULT_CARD_BATCH_PREFIX,
      note: `auto-replenish ${today}`,
    }, serverOptions);
    row.created = created.cards.length;
    totalCreated += row.created;
    remainingDaily -= row.created;
    batches.push({
      planId: row.planId,
      batchId: created.batchId,
      count: row.created,
      newApiSync: created.newApiSync,
    });
  }

  data.events.push({
    type: 'redemption_cards_autoreplenished',
    created: totalCreated,
    dryRun,
    dailyCap,
    dailyCreatedBefore: dailyCreated,
    at: now,
  });
  return {
    enabled,
    dryRun,
    created: totalCreated,
    dailyCap,
    dailyCreated: dailyCreated + totalCreated,
    remainingDailyCap: Math.max(0, dailyCap - dailyCreated - totalCreated),
    plans,
    batches,
    summary: buildXianyuFulfillmentSummary(data),
    events: sanitizeAdminEvents(data.events),
  };
}

function syncNewApiRedemptionCards(cards, serverOptions = {}) {
  if (!serverOptions.newApiEnabled) {
    return { enabled: false, synced: 0 };
  }
  const sqliteDb = String(serverOptions.newApiSqliteDb || '').trim();
  if (!sqliteDb) {
    if (serverOptions.requireNewApiDatabase || serverOptions.enforceProductionReadiness) {
      throw publicError(500, 'New-API 兑换码数据库路径未配置，无法同步生产卡密');
    }
    return { enabled: true, synced: 0, skipped: 'missing_sqlite_db' };
  }
  const rows = cards
    .map((card) => ({
      key: normalizeCardCode(card.code),
      name: String(card.label || card.plan || 'CC中转内测兑换码').slice(0, 80),
      quota: newApiQuotaFromCents(card.creditCents),
      createdTime: unixTimeSeconds(card.createdAt),
      expiredTime: card.durationDays > 0 ? unixTimeSeconds(addDays(new Date(card.createdAt || Date.now()), card.durationDays)) : 0,
    }))
    .filter((row) => row.key && row.quota > 0);
  if (rows.length === 0) {
    return { enabled: true, synced: 0, sqliteDbConfigured: true };
  }
  const statements = [
    'PRAGMA foreign_keys=OFF;',
    'BEGIN IMMEDIATE;',
    ...rows.map((row) => `INSERT INTO redemptions (user_id, \`key\`, status, name, quota, created_time, redeemed_time, used_user_id, expired_time) VALUES (0, ${sqlQuote(row.key)}, 1, ${sqlQuote(row.name)}, ${row.quota}, ${row.createdTime}, 0, 0, ${row.expiredTime}) ON CONFLICT(\`key\`) DO UPDATE SET name=excluded.name, quota=excluded.quota, expired_time=excluded.expired_time;`),
    'COMMIT;',
  ];
  const result = spawnSync('sqlite3', [sqliteDb], {
    input: `${statements.join('\n')}\n`,
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || 'sqlite3 写入失败').split('\n')[0].slice(0, 160);
    throw publicError(500, `New-API 兑换码同步失败: ${detail}`);
  }
  return { enabled: true, synced: rows.length, sqliteDbConfigured: true };
}

function syncNewApiRedemptionStatuses(data, serverOptions = {}) {
  const snapshot = readNewApiRedemptionStatusSnapshot(serverOptions);
  if (!snapshot.enabled || !snapshot.sqliteDbConfigured || !snapshot.readable) {
    return snapshot;
  }
  const now = currentDate(serverOptions).toISOString();
  let syncedCards = 0;
  let syncedFulfillments = 0;
  let backfilledRedemptions = 0;
  for (const card of data.redemptionCards || []) {
    const codeHash = String(card.codeHash || '').trim();
    if (!codeHash) continue;
    const redeemed = snapshot.byCodeHash.get(codeHash);
    if (!redeemed) continue;
    const redeemedAt = redeemed.redeemedAt || now;
    const changedCard = card.status !== 'redeemed' || !card.redeemedAt || !card.redeemedBy;
    if (changedCard) {
      card.status = 'redeemed';
      card.redeemedAt = card.redeemedAt || redeemedAt;
      card.redeemedBy = card.redeemedBy || `newapi:${redeemed.usedUserId || 'unknown'}`;
      card.redeemedEmail = card.redeemedEmail || '';
      card.updatedAt = now;
      syncedCards += 1;
    }
    const fulfillment = (data.xianyuFulfillments || []).find(
      (item) => item.cardId === card.id && item.status !== 'cancelled',
    );
    if (fulfillment && fulfillment.status !== 'redeemed') {
      fulfillment.status = 'redeemed';
      fulfillment.redeemedAt = fulfillment.redeemedAt || redeemedAt;
      fulfillment.redeemedEmail = fulfillment.redeemedEmail || '';
      fulfillment.updatedAt = now;
      syncedFulfillments += 1;
    }
    const alreadyRecorded = (data.redemptions || []).some((item) => item.cardId === card.id || item.codeHash === codeHash);
    if (!alreadyRecorded) {
      data.redemptions.unshift({
        code: card.codePreview || '',
        codeHash,
        codePreview: card.codePreview || '',
        userId: `newapi:${redeemed.usedUserId || 'unknown'}`,
        plan: card.label || card.plan || '兑换码',
        cardId: card.id,
        batchId: card.batchId || '',
        creditCents: Number(card.creditCents || 0),
        source: 'new-api-status-sync',
        at: redeemedAt,
      });
      backfilledRedemptions += 1;
    }
  }
  if (syncedCards || syncedFulfillments || backfilledRedemptions) {
    data.events.unshift({
      type: 'newapi_redemption_status_synced',
      cards: syncedCards,
      fulfillments: syncedFulfillments,
      redemptions: backfilledRedemptions,
      at: now,
    });
  }
  return {
    enabled: true,
    sqliteDbConfigured: true,
    readable: true,
    scanned: snapshot.scanned,
    redeemedRows: snapshot.redeemedRows,
    syncedCards,
    syncedFulfillments,
    backfilledRedemptions,
  };
}

function readNewApiRedemptionStatusSnapshot(serverOptions = {}) {
  if (!serverOptions.newApiEnabled) {
    return { enabled: false, sqliteDbConfigured: false, readable: false, scanned: 0, redeemedRows: 0, byCodeHash: new Map() };
  }
  const sqliteDb = String(serverOptions.newApiSqliteDb || '').trim();
  if (!sqliteDb) {
    return { enabled: true, sqliteDbConfigured: false, readable: false, scanned: 0, redeemedRows: 0, byCodeHash: new Map() };
  }
  const sql = [
    'SELECT',
    "  coalesce(`key`, ''),",
    '  coalesce(redeemed_time, 0),',
    '  coalesce(used_user_id, 0),',
    '  coalesce(status, 1)',
    'FROM redemptions',
    'WHERE coalesce(redeemed_time, 0) > 0 OR coalesce(used_user_id, 0) > 0 OR coalesce(status, 1) <> 1;',
  ].join('\n');
  const result = spawnSync('sqlite3', ['-separator', '\t', sqliteDb, sql], {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  });
  if (result.status !== 0) {
    return {
      enabled: true,
      sqliteDbConfigured: true,
      readable: false,
      scanned: 0,
      redeemedRows: 0,
      byCodeHash: new Map(),
      error: String(result.stderr || result.stdout || 'sqlite3_failed').split('\n')[0].slice(0, 120),
    };
  }
  const byCodeHash = new Map();
  let scanned = 0;
  for (const line of String(result.stdout || '').split('\n').filter(Boolean)) {
    scanned += 1;
    const [rawKey, rawRedeemedTime, rawUsedUserId, rawStatus] = line.split('\t');
    const code = normalizeCardCode(rawKey || '');
    const codeHash = hashRedemptionCode(code);
    if (!codeHash) continue;
    const redeemedTime = Number(rawRedeemedTime || 0);
    byCodeHash.set(codeHash, {
      redeemedAt: redeemedTime > 0 ? new Date(redeemedTime * 1000).toISOString() : '',
      usedUserId: Number(rawUsedUserId || 0),
      status: Number(rawStatus || 0),
    });
  }
  return {
    enabled: true,
    sqliteDbConfigured: true,
    readable: true,
    scanned,
    redeemedRows: byCodeHash.size,
    byCodeHash,
  };
}

function newApiQuotaFromCents(cents) {
  return Math.max(0, Math.round((Number(cents || 0) / 100) * 500000));
}

function unixTimeSeconds(value) {
  const time = value instanceof Date ? value.getTime() : Date.parse(value || '');
  const fallback = Date.now();
  return Math.floor((Number.isFinite(time) ? time : fallback) / 1000);
}

function sqlQuote(value) {
  return `'${String(value ?? '').replace(/'/g, "''")}'`;
}


function syncUpstreamChannels(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const channels = normalizeUpstreamChannelSnapshot(body.channels || body.items || [], {
    markup: serverOptions.rateMarkup,
  }).map((channel) => ({
    ...channel,
    source: String(body.source || 'reference-channel').trim() || 'reference-channel',
    syncedAt: now,
  }));
  data.upstreamChannelSnapshots = channels;
  data.events.push({
    type: 'upstream_channels_synced',
    count: channels.length,
    rateMarkup: serverOptions.rateMarkup,
    at: now,
  });
  return {
    rateMarkup: serverOptions.rateMarkup,
    channels: channels.map(sanitizeUpstreamChannel),
    summary: buildChannelSyncSummary(data, serverOptions),
    events: sanitizeAdminEvents(data.events),
  };
}

function applyUpstreamBalance(data, raw, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const warningCny = Number(serverOptions.upstreamBalanceWarningCny || 50);
  const criticalCny = Number(serverOptions.upstreamBalanceCriticalCny || 20);
  const remainingCny = round2(Number(raw.remainingCny || 0));
  const level = normalizeUpstreamBalanceLevel('', remainingCny, warningCny, criticalCny);
  const balance = normalizeUpstreamBalanceRecord({
    ...raw,
    remainingCny,
    warningCny,
    criticalCny,
    level,
    pauseRecommended: level === 'critical',
    checkedAt: now,
    lastError: '',
  });
  data.upstreamBalance = balance;
  data.events.push({
    type: 'upstream_balance_synced',
    provider: balance.provider || 'New-API',
    remainingCny: balance.remainingCny,
    level: balance.level,
    at: now,
  });
  return {
    balance,
    result: {
      ok: true,
      balance: sanitizeUpstreamBalance(balance, serverOptions),
      events: sanitizeAdminEvents(data.events),
    },
  };
}

async function notifyUpstreamBalanceIfNeeded(balance, serverOptions) {
  const notifier = serverOptions.notifyUpstreamBalance;
  if (typeof notifier === 'function' && (balance.level === 'warning' || balance.level === 'critical')) {
    await notifier(balance);
  }
}

function createXianyuFulfillment(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const orderId = String(body.orderId || '').trim();
  if (!orderId) {
    throw publicError(400, '闲鱼订单号不能为空');
  }
  const platform = String(body.platform || 'xianyu').trim().toLowerCase();
  const existing = data.xianyuFulfillments.find(
    (item) => item.platform === platform && item.orderId === orderId && item.status !== 'cancelled',
  );
  if (existing) {
    const existingCard = data.redemptionCards.find((card) => card.id === existing.cardId) || {};
    const deliveryMessage = existing.deliveryMessage || buildXianyuDeliveryMessage(existingCard, existing, serverOptions);
    return {
      fulfillment: sanitizeXianyuFulfillment(existing),
      card: sanitizeRedemptionCard(existingCard),
      deliveryMessage,
      summary: buildXianyuFulfillmentSummary(data),
      events: sanitizeAdminEvents(data.events),
      idempotent: true,
    };
  }

  const card = pickRedemptionCardForFulfillment(data, body, serverOptions);
  if (!card) {
    throw publicError(409, '没有可发货的兑换码，请先生成卡密');
  }
  const deliveryMessage = buildXianyuDeliveryMessage(card, body, serverOptions);

  const fulfillment = {
    id: createId('fulfill'),
    platform,
    orderId,
    productTitle: String(body.productTitle || card.label || 'CC中转 兑换码').trim().slice(0, 160),
    buyerHint: String(body.buyerHint || body.buyerName || '').trim().slice(0, 120),
    planId: String(body.planId || '').trim(),
    cardId: card.id,
    cardCode: card.codePreview || maskCardCode(cardCodePlain(card, serverOptions)),
    status: 'delivered',
    deliveryMessage: '',
    note: String(body.note || '').trim().slice(0, 500),
    createdAt: now,
    updatedAt: now,
    deliveredAt: now,
    redeemedAt: '',
    redeemedEmail: '',
  };

  card.status = 'sold';
  card.soldAt = now;
  card.soldOrderId = orderId;
  card.soldPlatform = platform;
  card.soldBuyerHint = fulfillment.buyerHint;
  card.fulfillmentId = fulfillment.id;
  card.deliveredAt = now;
  card.updatedAt = now;
  data.xianyuFulfillments.unshift(fulfillment);
  data.events.push({
    type: 'xianyu_card_delivered',
    orderId,
    cardId: card.id,
    codePreview: card.codePreview || maskCardCode(cardCodePlain(card, serverOptions)),
    at: now,
  });

  return {
    fulfillment: sanitizeXianyuFulfillment(fulfillment),
    card: sanitizeRedemptionCard(card),
    deliveryMessage,
    summary: buildXianyuFulfillmentSummary(data),
    events: sanitizeAdminEvents(data.events),
  };
}

function remapXianyuFulfillmentOrder(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const platform = String(body.platform || 'xianyu').trim().toLowerCase();
  const oldOrderId = String(body.oldOrderId || body.fromOrderId || '').trim();
  const newOrderId = String(body.newOrderId || body.toOrderId || '').trim();
  if (!oldOrderId || !newOrderId) {
    throw publicError(400, '原订单号和新订单号不能为空');
  }
  if (oldOrderId === newOrderId) {
    const same = data.xianyuFulfillments.find(
      (item) => item.platform === platform && item.orderId === newOrderId && item.status !== 'cancelled',
    );
    if (!same) throw publicError(404, '没有找到可接管的闲鱼发货记录');
    const sameCard = data.redemptionCards.find((card) => card.id === same.cardId) || {};
    return {
      ok: true,
      idempotent: true,
      fulfillment: sanitizeXianyuFulfillment(same),
      card: sanitizeRedemptionCard(sameCard),
      summary: buildXianyuFulfillmentSummary(data),
      events: sanitizeAdminEvents(data.events),
    };
  }
  const conflict = data.xianyuFulfillments.find(
    (item) => item.platform === platform && item.orderId === newOrderId && item.status !== 'cancelled',
  );
  if (conflict) {
    throw publicError(409, '新订单号已经存在，未重复接管');
  }
  const fulfillment = data.xianyuFulfillments.find(
    (item) => item.platform === platform && item.orderId === oldOrderId && item.status !== 'cancelled',
  );
  if (!fulfillment) {
    throw publicError(404, '没有找到可接管的闲鱼发货记录');
  }
  fulfillment.orderId = newOrderId;
  fulfillment.updatedAt = now;
  fulfillment.note = [fulfillment.note, `remapped_from:${oldOrderId}`].filter(Boolean).join(' ').slice(0, 500);
  const card = data.redemptionCards.find((item) => item.id === fulfillment.cardId) || null;
  if (card) {
    card.soldOrderId = newOrderId;
    card.updatedAt = now;
  }
  data.events.push({
    type: 'xianyu_order_remapped',
    oldOrderId,
    newOrderId,
    fulfillmentId: fulfillment.id,
    cardId: fulfillment.cardId,
    at: now,
  });
  return {
    ok: true,
    fulfillment: sanitizeXianyuFulfillment(fulfillment),
    card: sanitizeRedemptionCard(card || {}),
    summary: buildXianyuFulfillmentSummary(data),
    events: sanitizeAdminEvents(data.events),
  };
}

function fulfillPaidXianyuOrder(data, body, serverOptions) {
  const normalized = normalizePaidXianyuOrder(body);
  if (!normalized.paid) {
    throw publicError(409, '订单未确认已付款，自动发货已阻断');
  }
  const result = createXianyuFulfillment(data, {
    ...body,
    orderId: normalized.orderId,
    buyerHint: normalized.buyerHint,
    productTitle: normalized.productTitle,
    planId: normalized.planId,
    platform: 'xianyu',
    note: normalized.note,
  }, serverOptions);
  return {
    ok: true,
    autoShip: true,
    order: normalized,
    ...result,
  };
}

function normalizePaidXianyuOrder(body = {}) {
  const statusText = [
    body.status,
    body.orderStatus,
    body.payStatus,
    body.tradeStatus,
    body.redReminder,
  ].map((value) => String(value || '').trim()).filter(Boolean).join(' ');
  const paid = body.paid === true || /等待卖家发货|买家已付款|已付款|待发货|paid|seller.*ship/i.test(statusText);
  const orderId = String(body.orderId || body.orderNo || body.tradeId || body.id || '').trim();
  if (!orderId) {
    throw publicError(400, '闲鱼订单号不能为空');
  }
  const productTitle = String(body.productTitle || body.itemTitle || body.title || 'CC中转 兑换码').trim().slice(0, 160);
  const buyerHint = String(body.buyerHint || body.buyerName || body.buyerId || body.userId || '').trim().slice(0, 120);
  const planId = String(body.planId || body.skuId || body.spec || '').trim().slice(0, 120);
  return {
    orderId,
    paid,
    status: statusText || (paid ? 'paid' : 'unknown'),
    productTitle,
    buyerHint,
    planId,
    note: String(body.note || 'xianyu-auto-webhook').trim().slice(0, 500),
  };
}

function pickRedemptionCardForFulfillment(data, body, serverOptions = {}) {
  const requestedCode = String(body.cardCode || '').trim().toUpperCase();
  if (requestedCode) {
    const card = data.redemptionCards.find((item) => cardMatchesCode(item, requestedCode, serverOptions));
    return card && card.status === 'unused' ? card : null;
  }
  const selectedPlan = findRechargePlan(data, body);
  const hasExplicitPlan = Boolean(selectedPlan || String(body.plan || body.planId || '').trim());
  const hasExplicitQuota = body.quotaUsd !== undefined || body.creditUsd !== undefined;
  const requestedPlan = selectedPlan
    ? normalizeRechargePlan(selectedPlan.plan)
    : hasExplicitPlan
      ? normalizeRechargePlan(body.plan || '')
      : '';
  const requestedQuotaUsd = selectedPlan
    ? Number(selectedPlan.quotaUsd || 0)
    : hasExplicitQuota
      ? Number(body.quotaUsd || body.creditUsd || 0)
      : 0;
  return data.redemptionCards.find((card) => {
    if (card.status !== 'unused') return false;
    if (requestedPlan && normalizeRechargePlan(card.plan) !== requestedPlan) return false;
    if (requestedQuotaUsd > 0 && Math.abs(Number(card.quotaUsd || 0) - requestedQuotaUsd) > 0.001) return false;
    return true;
  }) || null;
}

function buildXianyuDeliveryMessage(card, body, serverOptions) {
  const gateway = String(serverOptions.publicGatewayBaseUrl || 'https://jiyu.245334.xyz')
    .replace(/\/v1\/?$/i, '')
    .replace(/\/$/, '');
  const title = String(body.productTitle || card.label || 'CC中转 兑换码').trim();
  const code = cardCodePlain(card, serverOptions);
  if (!code) {
    throw publicError(500, '卡密明文已加密保存，但当前服务无法解密，请检查生产密钥');
  }
  return [
    `您好，您购买的 ${title} 已自动发货。`,
    `兑换码：${code}`,
    `兑换入口：${gateway}`,
    '使用步骤：',
    '1. 打开兑换入口，注册或登录账号。',
    '2. 进入“兑换码”，粘贴上面的兑换码，兑换成功后额度会到账。',
    '3. 进入“API Key”，创建自己的 API Key。',
    '4. 进入“CC Switch”，复制导入链接，导入后选择模型测试。',
    '兑换成功后后台会记录到账状态，麻烦确认收货；如遇问题请直接回复订单消息。',
  ].join('\n');
}

function redeemCustomerCode(data, request, body, serverOptions, securityState) {
  const { user } = requireSession(data, request);
  assertRedeemUserRateLimit(securityState, serverOptions, user.id);
  const code = normalizeCardCode(body.code);
  const card = data.redemptionCards.find((item) => cardMatchesCode(item, code, serverOptions));
  const rule = card ? redemptionRuleFromCard(card) : LEGACY_CARD_CODES.get(code);
  if (!rule) {
    throw publicError(400, '兑换码无效');
  }
  if (data.redemptions.some((item) => redemptionMatchesCode(item, code))) {
    throw publicError(409, '兑换码已使用');
  }
  if (card && !['unused', 'sold'].includes(card.status)) {
    throw publicError(409, '兑换码已使用');
  }

  const now = currentDate(serverOptions);
  const planType = normalizeRechargePlan(rule.plan);
  if (planType === 'day' || planType === 'month' || rule.displayPlan) {
    user.plan = rule.displayPlan || (planType === 'month' ? '月卡' : '日卡');
    const expiresAt = addDays(now, rule.days);
    user.renewalDate = formatDate(expiresAt);
    user.planExpiresAt = expiresAt.toISOString();
  }
  user.packageQuotaCents += Number(rule.packageCents || 0);
  user.boosterQuotaCents += Number(rule.boosterCents || 0);
  user.balanceCents += Number(rule.packageCents || 0) + Number(rule.boosterCents || 0);
  reconcileUserBalance(user);
  user.updatedAt = now.toISOString();
  data.redemptions.push({
    code: maskCardCode(code),
    codeHash: hashRedemptionCode(code),
    codePreview: maskCardCode(code),
    userId: user.id,
    plan: rule.displayPlan || rule.label || (planType === 'balance' ? '加油包' : planType),
    cardId: card?.id || '',
    batchId: card?.batchId || '',
    creditCents: Number(rule.packageCents || 0) + Number(rule.boosterCents || 0),
    at: user.updatedAt,
  });
  if (card) {
    card.status = 'redeemed';
    card.redeemedAt = user.updatedAt;
    card.redeemedBy = user.id;
    card.redeemedEmail = user.email;
    card.updatedAt = user.updatedAt;
    const fulfillment = data.xianyuFulfillments.find((item) => item.cardId === card.id && item.status !== 'cancelled');
    if (fulfillment) {
      fulfillment.status = 'redeemed';
      fulfillment.redeemedAt = user.updatedAt;
      fulfillment.redeemedEmail = user.email;
      fulfillment.updatedAt = user.updatedAt;
    }
  }
  data.events.push({ type: 'redeemed', userId: user.id, codePreview: maskCardCode(code), at: user.updatedAt });
  return {
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    redemption: {
      code: maskCardCode(code),
      label: rule.label || '兑换码',
      plan: rule.displayPlan || rule.plan || 'balance',
      credit: formatUsdFromCnyCents(Number(rule.packageCents || 0) + Number(rule.boosterCents || 0)),
    },
  };
}

function recordLocalRedemptionAfterNewApiTopup(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  const code = normalizeCardCode(body.code);
  const card = data.redemptionCards.find((item) => cardMatchesCode(item, code, serverOptions));
  if (!card) {
    return {
      user: sanitizeUser(user),
      redemption: null,
    };
  }

  const now = currentDate(serverOptions).toISOString();
  const rule = redemptionRuleFromCard(card);
  if (!data.redemptions.some((item) => redemptionMatchesCode(item, code))) {
    data.redemptions.push({
      code: maskCardCode(code),
      codeHash: hashRedemptionCode(code),
      codePreview: maskCardCode(code),
      userId: user.id,
      plan: rule.displayPlan || rule.label || rule.plan || 'balance',
      cardId: card.id,
      batchId: card.batchId || '',
      creditCents: Number(rule.packageCents || 0) + Number(rule.boosterCents || 0),
      source: 'new-api',
      at: now,
    });
    const planType = normalizeRechargePlan(rule.plan);
    if (planType === 'day' || planType === 'month' || rule.displayPlan) {
      user.plan = rule.displayPlan || (planType === 'month' ? '月卡' : '日卡');
      const expiresAt = addDays(currentDate(serverOptions), Number(rule.days || 0));
      user.renewalDate = formatDate(expiresAt);
      user.planExpiresAt = expiresAt.toISOString();
    }
    user.packageQuotaCents += Number(rule.packageCents || 0);
    user.boosterQuotaCents += Number(rule.boosterCents || 0);
    user.balanceCents += Number(rule.packageCents || 0) + Number(rule.boosterCents || 0);
    reconcileUserBalance(user);
  }

  if (['unused', 'sold', 'redeemed'].includes(card.status)) {
    card.status = 'redeemed';
    card.redeemedAt = card.redeemedAt || now;
    card.redeemedBy = card.redeemedBy || user.id;
    card.redeemedEmail = card.redeemedEmail || user.email;
    card.updatedAt = now;
  }
  const fulfillment = data.xianyuFulfillments.find((item) => item.cardId === card.id && item.status !== 'cancelled');
  if (fulfillment) {
    fulfillment.status = 'redeemed';
    fulfillment.redeemedAt = fulfillment.redeemedAt || now;
    fulfillment.redeemedEmail = fulfillment.redeemedEmail || user.email;
    fulfillment.updatedAt = now;
  }
  user.updatedAt = now;
  data.events.push({
    type: 'newapi_redeemed',
    userId: user.id,
    cardId: card.id,
    codePreview: maskCardCode(code),
    at: now,
  });

  return {
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    redemption: {
      code: maskCardCode(code),
      label: rule.label || '兑换码',
      plan: rule.displayPlan || rule.plan || 'balance',
      credit: formatUsdFromCnyCents(Number(rule.packageCents || 0) + Number(rule.boosterCents || 0)),
    },
  };
}

function redemptionRuleFromCard(card) {
  const planType = normalizeRechargePlan(card.plan);
  const creditCents = Number(card.creditCents || 0);
  return {
    label: card.label || 'CC中转 兑换码',
    plan: planType,
    displayPlan: planType === 'day' ? '日卡' : planType === 'month' ? '月卡' : '',
    days: Number(card.durationDays || (planType === 'month' ? 30 : planType === 'day' ? 1 : 0)),
    packageCents: planType === 'day' || planType === 'month' ? creditCents : 0,
    boosterCents: planType === 'balance' ? creditCents : 0,
  };
}

function upsertPlusAccount(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const existing = body.id ? data.plusAccounts.find((account) => account.id === String(body.id)) : null;
  const mergedBody = existing
    ? {
        ...existing,
        ...body,
        openaiEmail: body.openaiEmail || existing.openaiEmail,
        appleEmail: body.appleEmail || existing.appleEmail,
        secrets: body.secrets || existing.secrets,
      }
    : body;
  const input = normalizePlusAccountRecord({
    ...mergedBody,
    id: existing?.id || '',
    createdAt: existing?.createdAt || body.createdAt || now,
    updatedAt: now,
  });
  if (!input.openaiEmail && !input.appleEmail) {
    throw publicError(400, '至少填写一个 OpenAI 或 Apple ID 邮箱');
  }
  if (input.complianceStatus === 'blocked' && input.status !== 'risk_hold' && input.status !== 'retired') {
    input.status = 'risk_hold';
  }
  if (input.status === 'active' && input.complianceStatus !== 'self_use_only') {
    throw publicError(400, 'Plus 账号必须标记为仅自用后才能设为活跃');
  }

  const account = existing
    ? Object.assign(existing, {
        ...input,
        id: existing.id,
        createdAt: existing.createdAt || input.createdAt || now,
        updatedAt: now,
      })
    : input;
  if (!existing) {
    data.plusAccounts.unshift(account);
  }

  data.events.push({
    type: 'plus_account_upserted',
    accountId: account.id,
    status: account.status,
    renewalAt: account.plusRenewalAt || '',
    at: now,
  });
  return {
    account: sanitizePlusAccount(account, serverOptions),
    summary: buildPlusAccountSummary(data.plusAccounts, serverOptions),
    events: sanitizeAdminEvents(data.events),
  };
}

function importRtAccounts(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const parsedRows = parseRtImportText(body.rtText ?? body.text ?? body.json ?? body.items);
  const platform = normalizeRtPlatform(body.platform || '');
  const sourceLabel = String(body.sourceLabel || '').trim().slice(0, 80);
  const accountType = String(body.accountType || '').trim().slice(0, 60);
  const note = sanitizeRiskNote(body.note || '');
  const imported = [];
  const skipped = [];
  for (const row of parsedRows) {
    const normalized = normalizeRtAccountRecord({
      ...row,
      platform: row.platform || platform,
      sourceLabel: row.sourceLabel || sourceLabel,
      accountType: row.accountType || accountType,
      note: row.note || note,
      createdAt: row.createdAt || now,
      updatedAt: now,
      importedAt: now,
    });
    if (!normalized.refreshToken) {
      skipped.push({ email: normalized.email || row.email || '', reason: '缺少 refresh_token' });
      continue;
    }
    const fingerprint = normalized.refreshTokenFingerprint;
    const existing = data.rtAccounts.find(
      (account) =>
        account.refreshTokenFingerprint === fingerprint ||
        (normalized.email && account.email === normalized.email && account.platform === normalized.platform),
    );
    if (existing) {
      Object.assign(existing, {
        ...normalized,
        id: existing.id,
        createdAt: existing.createdAt || normalized.createdAt,
        updatedAt: now,
      });
      imported.push(existing);
    } else {
      data.rtAccounts.unshift(normalized);
      imported.push(normalized);
    }
  }

  if (!parsedRows.length) {
    throw publicError(400, '没有识别到 RT 账号，请粘贴 JSON 数组、单个 JSON 对象或每行一个 RT');
  }
  if (!imported.length) {
    throw publicError(400, '没有可导入的 refresh_token');
  }

  data.events.push({
    type: 'rt_accounts_imported',
    count: imported.length,
    skipped: skipped.length,
    platform,
    at: now,
  });
  return {
    imported: imported.map(sanitizeRtAccount),
    skipped,
    accounts: data.rtAccounts.map(sanitizeRtAccount),
    summary: buildRtAccountSummary(data.rtAccounts),
    events: sanitizeAdminEvents(data.events),
  };
}

async function createOwnedNewApiToken({ store, request, body, serverOptions, newApiBridge }) {
  const reservation = await store.mutate((data) =>
    reserveNewApiTokenCreation(data, request, body, serverOptions, newApiBridge),
  );
  let created = null;
  try {
    // 先创建零额度 Token；只有客户归属持久化后才激活，避免留下可用的无主 Token。
    created = await newApiBridge.createToken({
      ...body,
      remainQuota: 0,
      unlimitedQuota: false,
    }, { allowZeroQuota: true });
    await store.mutate((data) => persistStagedNewApiTokenOwner(data, reservation, created.key));
  } catch (error) {
    if (created?.key?.id) {
      await compensateStagedNewApiToken(newApiBridge, created.key.id).catch((compensationError) => {
        process.emitWarning(`New-API 零额度暂存 Key 清理失败: ${compensationError.message}`, {
          code: 'FRIST_API_NEWAPI_STAGED_TOKEN_CLEANUP_FAILED',
        });
      });
    }
    await rollbackNewApiTokenReservation(store, reservation, 'create_failed').catch((rollbackError) => {
      process.emitWarning(`New-API Key 创建预留回滚失败: ${rollbackError.message}`, {
        code: 'FRIST_API_NEWAPI_RESERVATION_ROLLBACK_FAILED',
      });
    });
    throw error;
  }

  try {
    const activated = await newApiBridge.activateTokenQuota(created.key.id, reservation.upstreamQuotaUnits);
    try {
      await store.mutate((data) => markNewApiTokenOwnerActive(data, reservation, created.key.id));
    } catch (error) {
      // 归属和扣款已先落盘；状态标记失败不把已拥有的 Key 误报为创建失败，避免客户重试产生重复 Key。
      process.emitWarning(`New-API Key 已激活但状态标记失败: ${error.message}`, {
        code: 'FRIST_API_NEWAPI_OWNER_STATE_WRITE_FAILED',
      });
    }
    return {
      key: {
        ...activated.key,
        preview: created.key.preview,
        secret: created.key.secret,
      },
    };
  } catch (error) {
    try {
      await compensateStagedNewApiToken(newApiBridge, created.key.id);
    } catch (compensationError) {
      // 无法确认上游已撤销时保留客户归属和额度预留，禁止把不确定 Token 变成无主或免费资产。
      process.emitWarning(`New-API Key 激活失败且补偿状态不确定: ${compensationError.message}`, {
        code: 'FRIST_API_NEWAPI_ACTIVATION_COMPENSATION_FAILED',
      });
      throw publicError(502, 'API Key 激活状态不确定，已保留归属和额度，请联系管理员对账');
    }
    await rollbackNewApiTokenReservation(store, reservation, 'activation_failed', created.key.id);
    throw error;
  }
}

function reserveNewApiTokenCreation(data, request, body, serverOptions, newApiBridge) {
  requireCsrfIfEnabled(data, request, serverOptions);
  const { user } = requireSession(data, request);
  if (serverOptions.requireEmailVerification && !user.emailVerified) {
    throw publicError(403, '请先完成邮箱验证');
  }
  const hasPendingCreation = Object.values(data.newApiTokenCreateIntents || {}).some(
    (intent) => intent?.userId === user.id,
  ) || Object.values(data.newApiTokenOwners || {}).some(
    (owner) => owner?.userId === user.id && owner?.state === 'pending_activation',
  );
  if (hasPendingCreation) {
    throw publicError(409, '已有 API Key 正在创建或等待对账，请勿重复提交');
  }
  const allocation = allocateNewApiTokenQuota(data, user, serverOptions, newApiBridge);
  const deducted = deductUserQuota(user, allocation.allocatedCents);
  const intentId = createId('newapi-token-intent');
  const now = currentDate(serverOptions).toISOString();
  data.newApiTokenCreateIntents[intentId] = {
    id: intentId,
    userId: user.id,
    name: String(body.name || '').trim().slice(0, 80),
    allocatedCents: allocation.allocatedCents,
    upstreamQuotaUnits: allocation.upstreamQuotaUnits,
    deductedPackageCents: deducted.packageCents,
    deductedBoosterCents: deducted.boosterCents,
    createdAt: now,
  };
  data.events.push({
    type: 'newapi_token_create_reserved',
    userId: user.id,
    intentId,
    allocatedCents: allocation.allocatedCents,
    upstreamQuotaUnits: allocation.upstreamQuotaUnits,
    at: now,
  });
  return { ...data.newApiTokenCreateIntents[intentId] };
}

function allocateNewApiTokenQuota(data, user, serverOptions, newApiBridge) {
  expireUserPlanIfNeeded(data, user, serverOptions);
  const availableCents = Math.floor(availableQuotaCents(user));
  const configuredCents = Math.floor(Number(newApiBridge?.config?.defaultTokenQuotaCents || 0));
  if (!Number.isSafeInteger(configuredCents) || configuredCents <= 0) {
    throw publicError(503, 'New-API 默认 Key 额度未正确配置');
  }
  if (!Number.isSafeInteger(availableCents) || availableCents <= 0) {
    throw publicError(402, '余额不足，请先兑换或充值后再创建 API Key');
  }
  const allocatedCents = Math.min(availableCents, configuredCents);
  const upstreamQuotaUnits = newApiQuotaFromCents(allocatedCents);
  if (!Number.isSafeInteger(upstreamQuotaUnits) || upstreamQuotaUnits <= 0) {
    throw publicError(503, 'New-API Key 上游额度换算失败');
  }
  return { allocatedCents, upstreamQuotaUnits };
}

function persistStagedNewApiTokenOwner(data, reservation, key) {
  const intent = data.newApiTokenCreateIntents?.[reservation.id];
  if (!intent || intent.userId !== reservation.userId) {
    throw publicError(409, 'API Key 创建预留不存在或已变化');
  }
  const user = data.users.find((item) => item.id === reservation.userId);
  if (!user) {
    throw publicError(409, 'API Key 创建用户不存在');
  }
  const keyId = String(key?.id || '').trim();
  if (!keyId) {
    throw publicError(502, 'New-API 未返回可登记的 Key ID');
  }
  if (data.newApiTokenOwners[keyId]) {
    throw publicError(502, 'New-API Key ID 已存在归属，已拒绝覆盖');
  }
  data.newApiTokenOwners[keyId] = {
    userId: user.id,
    name: String(key.name || '').slice(0, 80),
    allocatedCents: reservation.allocatedCents,
    upstreamQuotaUnits: reservation.upstreamQuotaUnits,
    state: 'pending_activation',
    intentId: reservation.id,
    createdAt: new Date().toISOString(),
  };
  data.events.push({
    type: 'newapi_token_owned',
    userId: user.id,
    keyId,
    allocatedCents: reservation.allocatedCents,
    upstreamQuotaUnits: reservation.upstreamQuotaUnits,
    at: data.newApiTokenOwners[keyId].createdAt,
  });
}

function markNewApiTokenOwnerActive(data, reservation, keyId) {
  const owner = data.newApiTokenOwners?.[String(keyId)];
  if (!owner || owner.userId !== reservation.userId || owner.intentId !== reservation.id) {
    throw publicError(409, 'API Key 归属状态已变化，拒绝覆盖');
  }
  owner.state = 'active';
  owner.activatedAt = new Date().toISOString();
  delete owner.intentId;
  delete data.newApiTokenCreateIntents[reservation.id];
  data.events.push({
    type: 'newapi_token_activated',
    userId: reservation.userId,
    keyId: String(keyId),
    at: owner.activatedAt,
  });
}

async function compensateStagedNewApiToken(newApiBridge, keyId) {
  await newApiBridge.deleteToken(keyId);
}

async function rollbackNewApiTokenReservation(store, reservation, reason, keyId = '') {
  await store.mutate((data) => {
    const intent = data.newApiTokenCreateIntents?.[reservation.id];
    if (!intent || intent.userId !== reservation.userId) {
      return;
    }
    const user = data.users.find((item) => item.id === reservation.userId);
    if (!user) {
      throw publicError(409, 'API Key 创建用户不存在，无法回滚额度');
    }
    user.packageQuotaCents = Number(user.packageQuotaCents || 0) + Number(intent.deductedPackageCents || 0);
    user.boosterQuotaCents = Number(user.boosterQuotaCents || 0) + Number(intent.deductedBoosterCents || 0);
    reconcileUserBalance(user);
    if (keyId) {
      const owner = data.newApiTokenOwners?.[String(keyId)];
      if (owner?.intentId === reservation.id && owner.userId === reservation.userId) {
        delete data.newApiTokenOwners[String(keyId)];
      }
    }
    delete data.newApiTokenCreateIntents[reservation.id];
    data.events.push({
      type: 'newapi_token_create_rolled_back',
      userId: reservation.userId,
      intentId: reservation.id,
      keyId: String(keyId || ''),
      reason,
      at: new Date().toISOString(),
    });
  });
}

function requireNewApiTokenOwner(data, user, keyId) {
  const owner = data.newApiTokenOwners?.[String(keyId)];
  const ownerId = typeof owner === 'string' ? owner : owner?.userId;
  if (!ownerId || ownerId !== user.id) {
    // 不区分“不存在”和“属于他人”，避免泄露共享上游 Token ID。
    throw publicError(404, 'API Key 不存在');
  }
  return owner;
}

function createCustomerToken(data, request, body, serverOptions) {
  const { user } = requireSession(data, request);
  if (serverOptions.requireEmailVerification && !user.emailVerified) {
    throw publicError(403, '请先完成邮箱验证');
  }

  const now = new Date().toISOString();
  const secret = generateCustomerApiKey();
  const key = {
    id: createId('key'),
    userId: user.id,
    name: String(body.name || `API Key ${data.userKeys.length + 1}`).trim(),
    secret,
    preview: maskKey(secret),
    enabled: true,
    modelGroup: normalizeModelGroup(body.modelGroup),
    costCents: 0,
    tokens: '0.00M',
    lastUsed: '-',
    expiresAt: '-',
    createdAt: now,
    updatedAt: now,
  };
  data.userKeys.unshift(key);
  data.events.push({ type: 'key_created', userId: user.id, keyId: key.id, at: now });
  return { key: sanitizeUserKey(key, { revealSecret: true }) };
}

function updateCustomerToken(data, request, keyId, body) {
  const { user } = requireSession(data, request);
  const key = data.userKeys.find((item) => item.userId === user.id && item.id === keyId);
  if (!key) {
    throw publicError(404, 'API Key 不存在');
  }
  const hasEnabled = Object.prototype.hasOwnProperty.call(body, 'enabled');
  const hasName = Object.prototype.hasOwnProperty.call(body, 'name');
  if (hasEnabled) {
    key.enabled = Boolean(body.enabled);
  }
  if (hasName) {
    const cleanName = String(body.name || '').trim();
    if (!cleanName) {
      throw publicError(400, 'API Key 名称不能为空');
    }
    key.name = cleanName.slice(0, 80);
  }
  key.updatedAt = new Date().toISOString();
  if (hasEnabled) {
    data.events.push({
      type: key.enabled ? 'key_enabled' : 'key_disabled',
      userId: user.id,
      keyId: key.id,
      at: key.updatedAt,
    });
  }
  if (hasName) {
    data.events.push({
      type: 'key_renamed',
      userId: user.id,
      keyId: key.id,
      at: key.updatedAt,
    });
  }
  return { key: sanitizeUserKey(key, { revealSecret: true }) };
}

function deleteCustomerToken(data, request, keyId) {
  const { user } = requireSession(data, request);
  const index = data.userKeys.findIndex((item) => item.userId === user.id && item.id === keyId);
  if (index === -1) {
    throw publicError(404, 'API Key 不存在');
  }
  const [deleted] = data.userKeys.splice(index, 1);
  const now = new Date().toISOString();
  data.events.push({
    type: 'key_deleted',
    userId: user.id,
    keyId: deleted.id,
    at: now,
  });
  return { deletedKeyId: deleted.id };
}

function buildCustomerImportUrl(data, request, url, serverOptions) {
  const { user } = requireSession(data, request);
  const targetModelGroup = normalizeModelGroup(
    url.searchParams.get('modelGroup') || inferProviderGroup(url.searchParams.get('model') || ''),
  );
  const requestedKeyId = String(url.searchParams.get('keyId') || '').trim();
  const enabledKeys = data.userKeys.filter((item) => item.userId === user.id && item.enabled);
  const key =
    enabledKeys.find((item) => requestedKeyId && item.id === requestedKeyId) ||
    enabledKeys.find((item) => targetModelGroup !== 'All' && normalizeModelGroup(item.modelGroup) === targetModelGroup) ||
    enabledKeys.find((item) => targetModelGroup !== 'All' && normalizeModelGroup(item.modelGroup) === 'All') ||
    enabledKeys[0];
  if (!key) {
    throw publicError(409, '没有可用的 API Key');
  }

  const target = url.searchParams.get('target') || 'Claude';
  const requestedModel = url.searchParams.get('model') || '';
  const baseUrl = serverOptions.publicGatewayBaseUrl || `${requestOrigin(request)}/v1`;
  const { availableModels, defaultModel } = customerImportModelSelection(data, user, key, requestedModel);
  const config = buildClientConfig({
    target,
    apiKey: key.secret,
    baseUrl,
    model: requestedModel || defaultModel,
    defaultModel,
    availableModels,
    modelGroup: key.modelGroup,
    planExpiresAt: user.planExpiresAt,
    preferExplicitDefaultModel: Boolean(requestedModel || defaultModel),
  });
  const setup = buildClientSetupCommands(config);
  return {
    url: config.ccSwitchUrl,
    config,
    setup,
    defaultModel,
    availableModels,
  };
}

function buildKeyUsagePayload(data, request, serverOptions) {
  const key = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === key.userId);
  if (!user) {
    throw publicError(401, '用户不存在');
  }
  expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
  const account = accountFromUser(data, user);
  const remainingCents = Number(user.balanceCents || 0);
  const usedMonthCents = sumUserGatewayCost(data, user.id, currentDate(serverOptions).toISOString().slice(0, 7));
  const totalCents = remainingCents + usedMonthCents;
  return {
    ok: true,
    valid: true,
    keyPreview: sanitizeUserKey(key).preview,
    plan: user.plan || '默认套餐',
    renewalDate: user.renewalDate || '-',
    remainingUsd: usdNumberFromCnyCents(remainingCents),
    usedUsd: usdNumberFromCnyCents(usedMonthCents),
    totalUsd: usdNumberFromCnyCents(totalCents),
    remainingCny: cnyNumberFromCents(remainingCents),
    usedCny: cnyNumberFromCents(usedMonthCents),
    totalCny: cnyNumberFromCents(totalCents),
    balance: account.balance,
    packageQuota: account.packageQuota,
    boosterQuota: account.boosterQuota,
    todayCost: account.todayCost,
    monthCost: account.monthCost,
    todayCalls: account.todayCalls,
    todayTokens: account.todayTokens,
    totalTokens: account.totalTokens,
    averageLatency: account.averageLatency,
    successRate: account.successRate,
  };
}

function buildDashboard(data, user, serverOptions) {
  expireUserPlanIfNeeded(data, user, serverOptions, { recordEvent: false });
  const apiKeys = data.userKeys
    .filter((item) => item.userId === user.id)
    .map((item) => sanitizeUserKey(item));
  return {
    authenticated: true,
    account: accountFromUser(data, user),
    user: sanitizeUser(user),
    balanceAlert: sanitizeBalanceAlert(user.balanceAlert, user.email),
    apiKeys,
    modelUsage: buildModelUsage(data, user),
    channelChecks: buildChannelChecks(data, serverOptions),
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
    usageRecords: buildUsageRecords(data, user),
    usageAnomalies: buildUsageAnomalies(data, user),
    recentLogs: buildRecentLogs(data, user),
    security: buildPublicSecurityConfig(serverOptions),
  };
}

function buildGuestDashboard(data, serverOptions = {}) {
  return {
    authenticated: false,
    account: {
      plan: '未登录',
      renewalDate: '-',
      balance: '$0.00',
      todayCost: '$0.00',
      monthCost: '$0.00',
      packageQuota: '$0.00',
      boosterQuota: '$0.00',
      quotaLeft: '$0.00',
      usageTotal: '$0.00',
      todayCalls: '0 次',
    },
    user: {
      id: '',
      email: '',
      emailVerified: false,
      plan: '未登录',
      renewalDate: '-',
      userInitials: 'FA',
    },
    balanceAlert: sanitizeBalanceAlert(defaultBalanceAlert(''), ''),
    apiKeys: [],
    modelUsage: [],
    channelChecks: [],
    modelCatalog: buildModelCatalog(data),
    rechargeOptions: buildRechargeOptions(data),
    usageRecords: [],
    usageAnomalies: [],
    recentLogs: [],
    security: buildPublicSecurityConfig(serverOptions),
  };
}

function buildPublicSecurityConfig(serverOptions = {}) {
  return {
    turnstile: {
      enabled: Boolean(serverOptions.requireTurnstile && serverOptions.turnstileSiteKey),
      siteKey: serverOptions.requireTurnstile ? serverOptions.turnstileSiteKey || '' : '',
      actions: {
        register: 'register',
        login: 'login',
        redeem: 'redeem',
      },
    },
  };
}

async function prepareCredentialReplenishment(body, serverOptions) {
  const parsedOrder = body.orderText ? parseSupplierOrderText(body.orderText, body.pricing || {}) : null;
  const normalizedBaseUrl = normalizeBaseUrl(body.baseUrl || parsedOrder?.baseUrl);
  const normalizedProxyBaseUrl = String(body.proxyBaseUrl || '').trim() ? normalizeBaseUrl(body.proxyBaseUrl) : '';
  await assertSafeUpstreamBaseUrl(normalizedBaseUrl, serverOptions);
  if (normalizedProxyBaseUrl) {
    await assertSafeUpstreamBaseUrl(normalizedProxyBaseUrl, serverOptions);
  }
  const pool = normalizePool(body.pool || parsedOrder?.pool || 'default');
  const modelGroup = normalizeModelGroup(body.modelGroup || parsedOrder?.providerGroup || '');
  const cardType = normalizePool(body.cardType || parsedOrder?.cardType || pool);
  const expiresAt = String(body.expiresAt || parsedOrder?.expiresAt || '');
  const sourceType = normalizeSourceType(body.sourceType || PRIMARY_SOURCE_TYPE);
  const riskStatus = normalizeRiskStatus(
    body.riskStatus || (sourceType === PRIMARY_SOURCE_TYPE ? 'approved' : 'quarantined'),
  );
  const backupRiskAccepted = Boolean(body.backupRiskAccepted || body.manualRiskAccepted);
  const riskNote = sanitizeRiskNote(body.riskNote || '');
  const routeApproved = isSourceRouteApproved({ sourceType, riskStatus, backupRiskAccepted });
  const gatedStatus = routeApproved ? 'healthy' : riskStatus === 'blocked' ? 'blocked' : 'quarantined';
  const keyInputs = normalizeReplenishmentKeys(body.keys ?? parsedOrder?.keys ?? []);
  if (keyInputs.length === 0) {
    throw publicError(400, 'Key 列表不能为空');
  }

  const providedModels = normalizeModels(body.models ?? parsedOrder?.models ?? [], { allowEmpty: true });
  const probeMode = String(body.probeMode || (providedModels.length > 0 ? 'trusted' : 'auto'));
  const probeReport = await probeReplenishment({
    baseUrl: normalizedBaseUrl,
    proxyBaseUrl: normalizedProxyBaseUrl,
    keyInputs,
    models: providedModels,
    modelGroup,
    probeMode,
    serverOptions,
  });
  return {
    body,
    normalizedBaseUrl,
    normalizedProxyBaseUrl,
    pool,
    modelGroup,
    cardType,
    expiresAt,
    sourceType,
    riskStatus,
    backupRiskAccepted,
    riskNote,
    routeApproved,
    gatedStatus,
    keyInputs,
    providedModels,
    probeMode,
    probeReport,
  };
}

function applyCredentialReplenishment(data, prepared, serverOptions) {
  const {
    body,
    normalizedBaseUrl,
    normalizedProxyBaseUrl,
    pool,
    modelGroup,
    cardType,
    expiresAt,
    sourceType,
    riskStatus,
    backupRiskAccepted,
    riskNote,
    routeApproved,
    gatedStatus,
    keyInputs,
    providedModels,
    probeMode,
    probeReport,
  } = prepared;
  const now = currentDate(serverOptions).toISOString();
  const models = providedModels.length > 0 ? providedModels : probeReport.models;
  const sourceGroup = modelGroup || inferProviderGroup(models.join('\n'));
  const sourceFingerprint =
    sourceType === PRIMARY_SOURCE_TYPE
      ? `${normalizedBaseUrl}:${sourceGroup}`
      : `${sourceType}:${normalizedBaseUrl}:${sourceGroup}`;
  const sourceId = `source-${hashId(sourceFingerprint)}`;
  const source = upsertSupplierProfile(data, {
    id: sourceId,
    baseUrl: normalizedBaseUrl,
    proxyBaseUrl: normalizedProxyBaseUrl,
    routeBaseUrl: probeReport.routeBaseUrl,
    pool,
    models,
    modelGroup: sourceGroup,
    cardType,
    expiresAt,
    sourceType,
    riskStatus: gatedStatus === 'healthy' ? 'approved' : riskStatus,
    backupRiskAccepted,
    riskNote,
    connectionPath: probeReport.connectionPath,
    updatedAt: now,
  });

  const failedKeys = [];
  const credentials = [];
  for (const key of keyInputs) {
    const probe = probeReport.keyResults.get(key.value) || { ok: true, reason: '信任写入' };
    if (!probe.ok) {
      failedKeys.push({
        keyPreview: maskKey(key.value),
        reason: probe.reason || '检测失败',
        status: probe.status || 'probe_failed',
      });
      continue;
    }

    const credentialModels = providedModels.length > 0 ? models : probe.models?.length ? probe.models : models;
    const credential = upsertCredential(data, {
      sourceId: source.id,
      baseUrl: normalizedBaseUrl,
      proxyBaseUrl: normalizedProxyBaseUrl,
      routeBaseUrl: probe.routeBaseUrl || probeReport.routeBaseUrl || normalizedBaseUrl,
      connectionPath: probe.connectionPath || probeReport.connectionPath || 'direct',
      rawKey: key.value,
      keyPreview: maskKey(key.value),
      pool,
      modelGroup: key.modelGroup || modelGroup || inferProviderGroup(credentialModels.join('\n')),
      cardType: key.cardType || cardType,
      expiresAt: key.expiresAt || expiresAt,
      quotaTotal: Number.isFinite(key.quotaTotal) ? key.quotaTotal : Number(probe.quotaTotal || key.quotaRemaining || probe.quotaRemaining || 1000),
      authHeaderName: key.authHeaderName || 'authorization',
      authHeaderValuePrefix: key.authHeaderValuePrefix ?? 'Bearer',
      extraHeaders: sanitizeExtraHeaders(key.extraHeaders),
      models: credentialModels,
      sourceType,
      riskStatus: gatedStatus === 'healthy' ? 'approved' : riskStatus,
      backupRiskAccepted,
      riskNote,
      enabled: routeApproved,
      status: gatedStatus,
      quotaRemaining: Number.isFinite(key.quotaRemaining) ? key.quotaRemaining : Number(probe.quotaRemaining || 1000),
      latencyMs: resolveProbeLatencyMs(key, probe),
      dailySpendLimitCents: Number.isFinite(key.dailySpendLimitCents) ? key.dailySpendLimitCents : 0,
      slowLatencyThresholdMs: Number.isFinite(key.slowLatencyThresholdMs) ? key.slowLatencyThresholdMs : 0,
      costSensitive: Boolean(key.costSensitive),
      lastProbeStatus: probe.status || probeMode,
      lastProbeReason: routeApproved ? probe.reason || '' : riskNote || '备用渠道待人工风险放行',
      createdAt: now,
      updatedAt: now,
    });
    credentials.push(credential);
  }

  const priceDrafts = parsePriceText(body.priceText || '', body.pricing || {}).map((draft) => ({
    id: createId('price'),
    sourceId: source.id,
    ...draft,
    createdAt: now,
  }));
  data.priceDrafts.push(...priceDrafts);
  data.events.push({
    type: 'replenished',
    sourceId: source.id,
    pool,
    modelGroup,
    credentialCount: credentials.length,
    failedCount: failedKeys.length,
    probeMode,
    sourceType,
    riskStatus,
    routeApproved,
    at: now,
  });

  return {
    supplierProfile: source,
    credentials: credentials.map(sanitizeCredential),
    failedKeys,
    priceDrafts,
    inventorySummary: buildInventorySummary(data),
    events: sanitizeAdminEvents(data.events),
  };
}

async function probeReplenishment({ baseUrl, proxyBaseUrl, keyInputs, models, modelGroup = '', probeMode, serverOptions }) {
  if (probeMode === 'trusted') {
    const routeBaseUrl = proxyBaseUrl || baseUrl;
    return {
      connectionPath: proxyBaseUrl ? 'proxy' : 'direct',
      routeBaseUrl,
      models: models.length > 0 ? models : DEFAULT_PROBE_MODELS,
      keyResults: new Map(
        keyInputs.map((key) => [
          key.value,
          {
            ok: true,
            status: 'trusted',
            reason: '信任写入',
            connectionPath: proxyBaseUrl ? 'proxy' : 'direct',
            routeBaseUrl,
          },
        ]),
      ),
    };
  }

  const keyResults = new Map();
  let detectedModels = models;
  if (detectedModels.length === 0) {
    detectedModels = await detectSupplierModels(baseUrl, proxyBaseUrl, keyInputs, serverOptions);
  }
  const candidateModels = detectedModels.length > 0 ? detectedModels : DEFAULT_PROBE_MODELS;
  const shouldCollectSupportedModels = models.length === 0 && detectedModels.length === 0;
  for (const key of keyInputs) {
    const probe = await probeCredentialRoutes({
      baseUrl,
      proxyBaseUrl,
      rawKey: key.value,
      authConfig: key,
      models: candidateModels,
      serverOptions,
      collectAllModels: shouldCollectSupportedModels,
      preferAnthropicMessages: normalizeModelGroup(key.modelGroup || modelGroup || '') === 'Claude',
    });
    keyResults.set(key.value, probe);
  }

  const healthyProbes = [...keyResults.values()].filter((probe) => probe.ok);
  const routeVotes = healthyProbes.reduce(
    (counts, probe) => {
      counts[probe.connectionPath || 'direct'] += 1;
      return counts;
    },
    { direct: 0, proxy: 0 },
  );
  const connectionPath = routeVotes.proxy > routeVotes.direct ? 'proxy' : 'direct';
  const routeBaseUrl = connectionPath === 'proxy' && proxyBaseUrl ? proxyBaseUrl : baseUrl;
  const successfulModels = shouldCollectSupportedModels
    ? uniqueStrings(healthyProbes.flatMap((probe) => probe.models || []))
    : candidateModels;

  return {
    connectionPath,
    routeBaseUrl,
    models: successfulModels.length > 0 ? successfulModels : candidateModels,
    keyResults,
  };
}

async function detectSupplierModels(baseUrl, proxyBaseUrl, keyInputs, serverOptions) {
  for (const key of keyInputs) {
    const probe = await probeCredentialModels(baseUrl, key.value, serverOptions, key);
    if (probe.ok && probe.models.length > 0) {
      return probe.models;
    }
    if (probe.ok && probe.status === 'models_not_supported') {
      if (proxyBaseUrl) {
        const proxyProbe = await probeCredentialModels(proxyBaseUrl, key.value, serverOptions, key);
        if (proxyProbe.ok && proxyProbe.models.length > 0) {
          return proxyProbe.models;
        }
      }
      return [];
    }
  }
  return [];
}

async function probeCredentialModels(baseUrl, rawKey, serverOptions, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }
  try {
    await assertSafeUpstreamBaseUrl(baseUrl, serverOptions);
  } catch (error) {
    return { ok: false, status: 'network_failed', reason: error.message || '请求地址不可达', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/models`, {
      method: 'GET',
      headers: authHeadersForKey(rawKey, authConfig),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    const models = parseModelIds(bodyText);
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models };
    }
    if (response.status >= 200 && response.status < 300) {
      return { ok: true, status: models.length > 0 ? 'models_detected' : 'reachable', reason: '', models };
    }
    if (response.status === 404 || response.status === 405) {
      return { ok: true, status: 'models_not_supported', reason: '上游不支持模型列表接口', models: [] };
    }
    return { ok: false, status: 'http_failed', reason: `上游返回 HTTP ${response.status}`, models };
  } catch (error) {
    return { ok: false, status: 'network_failed', reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达', models: [] };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialRoutes({
  baseUrl,
  proxyBaseUrl,
  rawKey,
  authConfig = {},
  models,
  serverOptions,
  collectAllModels,
  preferAnthropicMessages = false,
}) {
  const direct = await probeCredentialRouteCandidates(baseUrl, rawKey, models, serverOptions, {
    collectAllModels,
    authConfig,
    preferAnthropicMessages,
  });
  if (!proxyBaseUrl) {
    return {
      ...direct,
      connectionPath: 'direct',
      routeBaseUrl: direct.routeBaseUrl || baseUrl,
    };
  }

  const proxy = await probeCredentialRouteCandidates(proxyBaseUrl, rawKey, models, serverOptions, {
    collectAllModels,
    authConfig,
    preferAnthropicMessages,
  });
  const connectionPath = recommendConnectionPath({
    direct: { ok: direct.ok, p95Ms: direct.latencyMs || 999999, failureRate: direct.ok ? 0 : 1 },
    proxy: { ok: proxy.ok, p95Ms: proxy.latencyMs || 999999, failureRate: proxy.ok ? 0 : 1 },
  });
  if (connectionPath === 'proxy') {
    return {
      ...proxy,
      connectionPath,
      routeBaseUrl: proxy.routeBaseUrl || proxyBaseUrl,
    };
  }
  if (connectionPath === 'direct') {
    return {
      ...direct,
      connectionPath,
      routeBaseUrl: direct.routeBaseUrl || baseUrl,
    };
  }

  return {
    ...direct,
    ok: false,
    status: direct.status || proxy.status || 'network_failed',
    reason: direct.reason || proxy.reason || '直连和代理均不可用',
    connectionPath: 'direct',
    routeBaseUrl: baseUrl,
  };
}

async function probeCredentialRouteCandidates(baseUrl, rawKey, models, serverOptions, options = {}) {
  let lastProbe = null;
  for (const routeBaseUrl of routeBaseUrlCandidates(baseUrl)) {
    const probe = await probeCredentialChat(routeBaseUrl, rawKey, models, serverOptions, options);
    if (probe.ok) {
      return { ...probe, routeBaseUrl };
    }
    lastProbe = probe;
    if (['auth_failed', 'quota_failed'].includes(probe.status)) {
      break;
    }
  }
  return {
    ...(lastProbe || { ok: false, status: 'network_failed', reason: '请求地址不可达', models: [] }),
    routeBaseUrl: normalizeBaseUrl(baseUrl),
  };
}

function routeBaseUrlCandidates(baseUrl) {
  const normalized = normalizeBaseUrl(baseUrl);
  const candidates = [normalized];
  try {
    const parsed = new URL(normalized);
    const pathname = parsed.pathname.replace(/\/+$/, '');
    if (!/(^|\/)v1$/i.test(pathname)) {
      parsed.pathname = `${pathname}/v1`.replace(/\/+/g, '/');
      candidates.push(normalizeBaseUrl(parsed.toString()));
    }
  } catch {
    // normalizeBaseUrl 已经处理常见输入；极端解析失败时保留原始候选地址。
  }
  return [...new Set(candidates)];
}

function isRootUpstreamBaseUrl(baseUrl) {
  try {
    const pathname = new URL(normalizeBaseUrl(baseUrl)).pathname.replace(/\/+$/, '');
    return pathname === '';
  } catch {
    return false;
  }
}

async function probeCredentialChat(baseUrl, rawKey, models, serverOptions, options = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const supportedModels = [];
  let bestLatencyMs = 0;
  let lastFailure = null;

  for (const model of models) {
    if (options.preferAnthropicMessages && inferProviderGroup(model) === 'Claude') {
      const anthropicProbe = await probeCredentialAnthropicMessages(
        baseUrl,
        rawKey,
        model,
        serverOptions,
        Date.now(),
        options.authConfig || {},
      );
      if (anthropicProbe.status === 'auth_failed' || anthropicProbe.status === 'quota_failed' || anthropicProbe.status === 'network_failed') {
        return anthropicProbe;
      }
      if (anthropicProbe.ok) {
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, anthropicProbe.latencyMs) : anthropicProbe.latencyMs;
        if (!options.collectAllModels) {
          return anthropicProbe;
        }
        continue;
      }
      if (!isGatewayAdapterUnsupported({ status: anthropicProbe.httpStatus, bodyText: anthropicProbe.bodyText })) {
        lastFailure = anthropicProbe;
        if (!options.collectAllModels) {
          return lastFailure;
        }
      } else if (isRootUpstreamBaseUrl(baseUrl)) {
        return anthropicProbe;
      }
    }

    if (isImageGenerationModel(model)) {
      const imageProbe = await probeCredentialImageGeneration(
        baseUrl,
        rawKey,
        model,
        serverOptions,
        Date.now(),
        options.authConfig || {},
      );
      if (imageProbe.status === 'auth_failed' || imageProbe.status === 'quota_failed' || imageProbe.status === 'network_failed') {
        return imageProbe;
      }
      if (imageProbe.ok) {
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, imageProbe.latencyMs) : imageProbe.latencyMs;
        if (!options.collectAllModels) {
          return imageProbe;
        }
        continue;
      }
      if (isModelUnsupportedResponse(imageProbe.httpStatus, imageProbe.bodyText)) {
        continue;
      }
      lastFailure = imageProbe;
      if (!options.collectAllModels) {
        return lastFailure;
      }
      continue;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
    const startedAt = Date.now();
    try {
      const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/chat/completions`, {
        method: 'POST',
        headers: {
          ...authHeadersForKey(rawKey, options.authConfig || {}),
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
          stream: false,
        }),
        signal: controller.signal,
      });
      const bodyText = await response.text();
      if (response.status === 401 || response.status === 403) {
        return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [] };
      }
      if (response.status === 402 || response.status === 429) {
        return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [] };
      }
      if (response.status >= 200 && response.status < 300) {
        if (!isOpenAiChatCompletionPayload(bodyText)) {
          lastFailure = {
            ok: false,
            status: 'adapter_unsupported',
            reason: '上游返回非 OpenAI 兼容响应',
            models: [],
            httpStatus: response.status,
            bodyText,
          };
          if (!options.collectAllModels) {
            return lastFailure;
          }
          continue;
        }
        const latencyMs = Math.max(1, Date.now() - startedAt);
        supportedModels.push(model);
        bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, latencyMs) : latencyMs;
        if (!options.collectAllModels) {
          return {
            ok: true,
            status: 'chat_probe_ok',
            reason: '',
            models: [model],
            latencyMs,
          };
        }
        continue;
      }
      if (shouldTryResponsesProbe(response.status, bodyText)) {
        const responsesProbe = await probeCredentialResponses(
          baseUrl,
          rawKey,
          model,
          serverOptions,
          startedAt,
          options.authConfig || {},
        );
        if (responsesProbe.status === 'auth_failed' || responsesProbe.status === 'quota_failed' || responsesProbe.status === 'network_failed') {
          return responsesProbe;
        }
        if (responsesProbe.ok) {
          supportedModels.push(model);
          bestLatencyMs = bestLatencyMs ? Math.min(bestLatencyMs, responsesProbe.latencyMs) : responsesProbe.latencyMs;
          if (!options.collectAllModels) {
            return responsesProbe;
          }
          continue;
        }
        if (isModelUnsupportedResponse(responsesProbe.httpStatus, responsesProbe.bodyText)) {
          continue;
        }
        lastFailure = responsesProbe;
        if (!options.collectAllModels) {
          return lastFailure;
        }
        continue;
      }
      if (isModelUnsupportedResponse(response.status, bodyText)) {
        continue;
      }
      lastFailure = { ok: false, status: 'http_failed', reason: `上游返回 HTTP ${response.status}`, models: [] };
      if (!options.collectAllModels) {
        return lastFailure;
      }
    } catch (error) {
      return {
        ok: false,
        status: 'network_failed',
        reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
        models: [],
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  if (supportedModels.length > 0) {
    return {
      ok: true,
      status: 'chat_probe_ok',
      reason: '',
      models: supportedModels,
      latencyMs: bestLatencyMs || 999,
    };
  }

  if (lastFailure) {
    return lastFailure;
  }

  return { ok: false, status: 'model_failed', reason: '预设模型均不可用', models: [] };
}

async function probeCredentialAnthropicMessages(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/messages`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'ping' }],
        max_tokens: 1,
        stream: false,
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isAnthropicMessagePayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 Anthropic Messages 响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'anthropic_messages_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialImageGeneration(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    return { ok: false, status: 'probe_unavailable', reason: '当前 Node 环境缺少 fetch', models: [] };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/images/generations`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        prompt: 'ping',
        size: '1024x1024',
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isOpenAiImageGenerationPayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 OpenAI 图片响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'image_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function probeCredentialResponses(baseUrl, rawKey, model, serverOptions, startedAt, authConfig = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(serverOptions.probeTimeoutMs || 2500));
  try {
    const response = await fetchImpl(`${normalizeBaseUrl(baseUrl)}/responses`, {
      method: 'POST',
      headers: {
        ...authHeadersForKey(rawKey, authConfig),
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        input: [{ role: 'user', content: [{ type: 'input_text', text: 'ping' }] }],
        max_output_tokens: 1,
        stream: false,
      }),
      signal: controller.signal,
    });
    const bodyText = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, status: 'auth_failed', reason: '认证失败或 Key 无效', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status === 402 || response.status === 429) {
      return { ok: false, status: 'quota_failed', reason: '上游额度不足或限速', models: [], httpStatus: response.status, bodyText };
    }
    if (response.status >= 200 && response.status < 300) {
      if (!isOpenAiResponsesPayload(bodyText)) {
        return {
          ok: false,
          status: 'adapter_unsupported',
          reason: '上游返回非 OpenAI Responses 响应',
          models: [],
          httpStatus: response.status,
          bodyText,
        };
      }
      return {
        ok: true,
        status: 'responses_probe_ok',
        reason: '',
        models: [model],
        latencyMs: Math.max(1, Date.now() - startedAt),
        httpStatus: response.status,
        bodyText,
      };
    }
    return {
      ok: false,
      status: 'http_failed',
      reason: `上游返回 HTTP ${response.status}`,
      models: [],
      httpStatus: response.status,
      bodyText,
    };
  } catch (error) {
    return {
      ok: false,
      status: 'network_failed',
      reason: error.name === 'AbortError' ? '探测超时' : '请求地址不可达',
      models: [],
    };
  } finally {
    clearTimeout(timeout);
  }
}





function isAnthropicMessagePayload(bodyText) {
  const payload = parseJsonPayload(bodyText);
  return payload.type === 'message' && Array.isArray(payload.content);
}





async function routeChatCompletion(data, request, body, serverOptions, options = {}) {
  const userKey = requireUserKey(data, request);
  const user = data.users.find((item) => item.id === userKey.userId);
  if (!user) {
    throw publicError(401, '用户不存在');
  }

  const model = normalizeOfficialModelName(body.model);
  if (!model) {
    throw publicError(400, '缺少模型名称');
  }
  if (!modelMatchesGroup(model, userKey.modelGroup || 'All')) {
    throw publicError(403, '当前 API Key 的模型分组不匹配，请创建对应分组的 Key');
  }

  const routedBody = { ...body, model };
  const estimatedQuotaCost = estimateQuotaCostCents(data, model, routedBody, serverOptions);
  expireUserPlanIfNeeded(data, user, serverOptions);
  if (availableQuotaCents(user) < estimatedQuotaCost) {
    throw publicError(402, '余额不足，请先充值或兑换套餐');
  }

  const allowedPools = allowedPoolsForUser(user);
  const sessionKey = buildGatewayAffinityKey(request, body, userKey, model);
  const candidates = orderGatewayCandidates(
    data,
    data.credentials
      .filter((credential) => allowedPools.includes(credential.pool))
      .filter((credential) => credential.enabled)
      .filter((credential) => credential.status === 'healthy')
      .filter(isCredentialRouteApproved)
      .filter((credential) => normalizeOfficialModelList(credential.models).includes(model) || credential.models.includes('*'))
      .filter((credential) => credentialMatchesModelGroup(credential, model, userKey.modelGroup))
      .sort(compareGatewayCredentials),
    sessionKey,
  );

  for (const credential of candidates) {
    const breakerReason = credentialCircuitBreakerReason(data, credential, estimatedQuotaCost, serverOptions);
    if (breakerReason) {
      circuitBreakCredential(data, credential, breakerReason, serverOptions);
      await maybeNotifyCredentialIssue(data, credential, breakerReason, serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    if (Number(credential.quotaRemaining || 0) < estimatedQuotaCost) {
      exhaustCredential(data, credential, 'quota_too_low_before_request');
      await maybeNotifyCredentialIssue(data, credential, 'quota_too_low_before_request', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    let upstream;
    try {
      upstream = await callGatewayAttempts(credential, routedBody, serverOptions, options);
    } catch {
      failCredential(data, credential, 'upstream_network_failed');
      await maybeNotifyCredentialIssue(data, credential, 'upstream_network_failed', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (isQuotaExhaustedResponse(upstream)) {
      exhaustCredential(data, credential, 'quota_exhausted_by_upstream');
      await maybeNotifyCredentialIssue(data, credential, 'quota_exhausted_by_upstream', serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }
    if (shouldFailoverUpstream(upstream)) {
      failCredential(data, credential, `upstream_http_${upstream.status}`);
      await maybeNotifyCredentialIssue(data, credential, `upstream_http_${upstream.status}`, serverOptions);
      clearRouteAffinity(data, sessionKey, credential.id);
      continue;
    }

    if (upstream.status >= 200 && upstream.status < 300) {
      const quotaCost = resolveQuotaCostCents(data, model, routedBody, upstream, serverOptions);
      const usage = parseUpstreamUsage(upstream.bodyText);
      const beforeUserQuota = availableQuotaCents(user);
      const client = clientLabelFromRequest(request, routedBody);
      credential.quotaRemaining = Math.max(0, Number(credential.quotaRemaining || 0) - quotaCost);
      credential.status = credential.quotaRemaining > 0 ? 'healthy' : 'exhausted';
      credential.enabled = credential.quotaRemaining > 0;
      credential.updatedAt = new Date().toISOString();
      deductUserQuota(user, quotaCost);
      userKey.costCents += quotaCost;
      userKey.totalTokens = Number(userKey.totalTokens || 0) + Number(usage.totalTokens || 0);
      userKey.tokens = compactTokenText(userKey.totalTokens);
      userKey.lastUsed = credential.updatedAt.slice(11, 16);
      userKey.updatedAt = credential.updatedAt;
      data.events.push({
        type: 'gateway_routed',
        userId: user.id,
        keyId: userKey.id,
        credentialId: credential.id,
        model,
        pool: credential.pool,
        quotaCost,
        endpoint: credential.baseUrl,
        client,
        apiKeyPreview: userKey.preview || maskKey(userKey.secret),
        inferenceEffort: String(routedBody.reasoning_effort || routedBody.reasoning?.effort || routedBody.thinking?.budget_tokens || '默认'),
        requestType: options.requestType || (isImageGenerationModel(model) ? '图片' : '文本'),
        billingMode: credential.pool === 'day' || credential.pool === 'hour' || credential.pool === 'month' ? '套餐' : '余额',
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        totalTokens: usage.totalTokens,
        latencyMs: Number(upstream.latencyMs || credential.latencyMs || 0),
        status: 'success',
        at: credential.updatedAt,
      });
      recordChannelProbeEvent(data, credential, Number(upstream.latencyMs || credential.latencyMs || 0) > 1600 ? 'slow' : 'ok', 'gateway_success', serverOptions, {
        latencyMs: Number(upstream.latencyMs || credential.latencyMs || 0),
      });
      rememberRouteAffinity(data, sessionKey, {
        userId: user.id,
        keyId: userKey.id,
        credentialId: credential.id,
        model,
        pool: credential.pool,
        updatedAt: credential.updatedAt,
      });
      await maybeNotifyLowInventory(data, credential, serverOptions);
      await maybeNotifyCustomerLowBalance(data, user, serverOptions, {
        beforeUserQuota,
        afterUserQuota: availableQuotaCents(user),
        quotaCost,
        model,
      });
      return upstream;
    }

    return upstream;
  }

  return gatewayUnavailableResponse();
}

async function callGatewayAttempts(credential, body, serverOptions, options = {}) {
  const attempts = options.upstreamAttempts?.length
    ? options.upstreamAttempts
    : [{ upstreamPath: options.upstreamPath || '/chat/completions' }];
  let lastUpstream = null;

  for (const [index, attempt] of attempts.entries()) {
    const upstreamBody = attempt.transformRequest ? attempt.transformRequest(body) : body;
    const upstream = await callUpstreamChatCompletion(credential, upstreamBody, serverOptions, {
      streamResponse: body.stream === true && !attempt.transformResponse,
      upstreamPath: attempt.upstreamPath,
      request: options.request,
    });
    if (
      attempt.validateResponse &&
      upstream.status >= 200 &&
      upstream.status < 300 &&
      !upstream.bodyStream &&
      !attempt.validateResponse(upstream.bodyText)
    ) {
      lastUpstream = {
        ...upstream,
        status: 415,
        bodyText: JSON.stringify({ error: '上游返回格式不兼容' }),
      };
      continue;
    }
    if (isGatewayAdapterUnsupported(upstream) && index < attempts.length - 1) {
      lastUpstream = upstream;
      continue;
    }
    return attempt.transformResponse ? attempt.transformResponse(upstream, body, upstreamBody) : upstream;
  }

  return lastUpstream;
}





function anthropicMessagesToChatCompletion(body) {
  const messages = [];
  const system = anthropicContentToText(body.system);
  if (system) {
    messages.push({ role: 'system', content: system });
  }
  for (const message of body.messages || []) {
    messages.push({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: anthropicContentToText(message.content),
    });
  }
  return compactObject({
    model: body.model,
    messages,
    max_tokens: body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stop: body.stop_sequences,
    stream: body.stream,
    metadata: body.metadata,
  });
}

function anthropicContentToText(content) {
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part?.type === 'text') return part.text || '';
        if (part?.type === 'tool_result') return typeof part.content === 'string' ? part.content : JSON.stringify(part.content || {});
        if (part?.type === 'image') return '[图片]';
        return JSON.stringify(part || {});
      })
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

function responsesRequestToChatCompletion(body) {
  return compactObject({
    model: body.model,
    messages: responsesInputToMessages(body.input ?? body.messages ?? body.prompt),
    max_tokens: body.max_output_tokens || body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stream: body.stream,
    metadata: body.metadata,
  });
}

function chatCompletionRequestToResponses(body) {
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const instructions = messages
    .filter((message) => message.role === 'system' || message.role === 'developer')
    .map((message) => chatMessageContentToText(message.content))
    .filter(Boolean)
    .join('\n\n');
  const inputMessages = messages
    .filter((message) => message.role !== 'system' && message.role !== 'developer')
    .map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: chatContentToResponsesContent(message.content),
    }));

  return compactObject({
    model: body.model,
    instructions,
    input: inputMessages.length ? inputMessages : responsesInputToMessages(body.prompt || '').map((message) => ({
      role: message.role,
      content: chatContentToResponsesContent(message.content),
    })),
    max_output_tokens: body.max_completion_tokens || body.max_tokens,
    temperature: body.temperature,
    top_p: body.top_p,
    stream: false,
    metadata: body.metadata,
  });
}

function chatContentToResponsesContent(content) {
  if (typeof content === 'string') {
    return [{ type: 'input_text', text: content }];
  }
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === 'string') return { type: 'input_text', text: part };
      if (part?.type === 'text') return { type: 'input_text', text: part.text || '' };
      if (part?.type === 'image_url') {
        return { type: 'input_image', image_url: part.image_url?.url || part.image_url || '' };
      }
      return { type: 'input_text', text: JSON.stringify(part || {}) };
    });
  }
  return [{ type: 'input_text', text: content ? JSON.stringify(content) : '' }];
}

function responsesInputToMessages(input) {
  if (Array.isArray(input)) {
    return input.map((item) => ({
      role: item.role === 'assistant' || item.role === 'system' ? item.role : 'user',
      content: responsesContentToText(item.content ?? item),
    }));
  }
  return [{ role: 'user', content: responsesContentToText(input) }];
}

function responsesContentToText(content) {
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part?.type === 'input_text' || part?.type === 'output_text' || part?.type === 'text') return part.text || '';
        if (part?.type === 'input_image') return '[图片]';
        return JSON.stringify(part || {});
      })
      .filter(Boolean)
      .join('\n');
  }
  return content ? JSON.stringify(content) : '';
}

function chatCompletionToAnthropicMessageResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const choice = payload.choices?.[0] || {};
  const text = chatMessageContentToText(choice.message?.content);
  const usage = payload.usage || {};
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: payload.id || createId('msg'),
      type: 'message',
      role: 'assistant',
      model: payload.model || originalBody.model,
      content: [{ type: 'text', text }],
      stop_reason: choice.finish_reason === 'length' ? 'max_tokens' : 'end_turn',
      stop_sequence: null,
      usage: {
        input_tokens: Number(usage.prompt_tokens || usage.input_tokens || 0),
        output_tokens: Number(usage.completion_tokens || usage.output_tokens || 0),
      },
    }),
  };
}

function responsesToChatCompletionResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const usage = payload.usage || {};
  const inputTokens = Number(usage.prompt_tokens || usage.input_tokens || 0);
  const outputTokens = Number(usage.completion_tokens || usage.output_tokens || 0);
  const id = String(payload.id || createId('resp'));
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: id.startsWith('chatcmpl') ? id : `chatcmpl_${id}`,
      object: 'chat.completion',
      created: Number(payload.created || payload.created_at || Math.floor(Date.now() / 1000)),
      model: payload.model || originalBody.model,
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: responsesOutputToText(payload),
          },
          finish_reason: responseFinishReason(payload),
        },
      ],
      usage: {
        prompt_tokens: inputTokens,
        completion_tokens: outputTokens,
        total_tokens: Number(usage.total_tokens || inputTokens + outputTokens),
      },
    }),
  };
}

function responsesOutputToText(payload) {
  if (typeof payload.output_text === 'string') {
    return payload.output_text;
  }
  return (payload.output || [])
    .flatMap((item) => item.content || [])
    .map((part) => {
      if (typeof part === 'string') return part;
      if (part?.type === 'output_text' || part?.type === 'text') return part.text || '';
      return part ? JSON.stringify(part) : '';
    })
    .filter(Boolean)
    .join('\n');
}

function responseFinishReason(payload) {
  if (payload.status === 'incomplete') return 'length';
  if (payload.status === 'failed') return 'error';
  return 'stop';
}

function chatCompletionToResponsesResponse(upstream, originalBody) {
  if (upstream.status < 200 || upstream.status >= 300 || upstream.bodyStream) {
    return upstream;
  }
  const payload = parseJsonPayload(upstream.bodyText);
  const choice = payload.choices?.[0] || {};
  const text = chatMessageContentToText(choice.message?.content);
  const usage = payload.usage || {};
  const inputTokens = Number(usage.prompt_tokens || usage.input_tokens || 0);
  const outputTokens = Number(usage.completion_tokens || usage.output_tokens || 0);
  return {
    status: upstream.status,
    contentType: 'application/json; charset=utf-8',
    bodyText: JSON.stringify({
      id: `resp_${payload.id || createId('chat')}`,
      object: 'response',
      status: 'completed',
      model: payload.model || originalBody.model,
      output: [
        {
          id: `msg_${payload.id || createId('chat')}`,
          type: 'message',
          role: 'assistant',
          content: [{ type: 'output_text', text, annotations: [] }],
        },
      ],
      usage: {
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: Number(usage.total_tokens || inputTokens + outputTokens),
      },
    }),
  };
}




async function callUpstreamChatCompletion(credential, body, serverOptions, options = {}) {
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw publicError(500, '当前 Node 环境缺少 fetch');
  }

  const upstreamPath = String(options.upstreamPath || '/chat/completions').startsWith('/')
    ? options.upstreamPath
    : `/${options.upstreamPath}`;
  const upstreamBaseUrl = normalizeBaseUrl(credential.routeBaseUrl || credential.baseUrl);
  await assertSafeUpstreamBaseUrl(upstreamBaseUrl, serverOptions);
  const upstreamUrl = `${upstreamBaseUrl}${upstreamPath}`;
  const controller = new AbortController();
  const abortUpstream = () => controller.abort();
  options.request?.once?.('close', abortUpstream);
  const response = await fetchImpl(upstreamUrl, {
    method: 'POST',
    headers: {
      ...authHeadersForKey(credential.rawKey, credential),
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
    signal: controller.signal,
    redirect: 'manual',
  });
  const contentType = response.headers?.get?.('content-type') || 'application/json; charset=utf-8';
  if (options.streamResponse && response.status >= 200 && response.status < 300 && response.body) {
    return {
      status: response.status,
      contentType,
      bodyText: '',
      bodyStream: response.body,
      abort: abortUpstream,
    };
  }

  const bodyText = await response.text();
  options.request?.off?.('close', abortUpstream);
  return {
    status: response.status,
    contentType,
    bodyText,
    latencyMs: Number(response.headers?.get?.('x-frist-upstream-latency-ms') || 0) || Number(credential.latencyMs || 0),
  };
}




function exhaustCredential(data, credential, reason) {
  credential.status = 'exhausted';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  recordChannelProbeEvent(data, credential, 'exhausted', reason, {});
  data.events.push({
    type: 'credential_exhausted',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

function failCredential(data, credential, reason) {
  credential.status = 'failed';
  credential.enabled = false;
  credential.updatedAt = new Date().toISOString();
  recordChannelProbeEvent(data, credential, 'down', reason, {});
  data.events.push({
    type: 'credential_failed',
    credentialId: credential.id,
    reason,
    at: credential.updatedAt,
  });
}

function circuitBreakCredential(data, credential, reason, serverOptions = {}) {
  const now = currentDate(serverOptions).toISOString();
  const quotaReason = /quota|spend|balance|limit/i.test(reason);
  credential.status = quotaReason ? 'exhausted' : 'failed';
  credential.enabled = false;
  credential.updatedAt = now;
  credential.lastProbeStatus = 'circuit_breaker';
  credential.lastProbeReason = reason;
  recordChannelProbeEvent(data, credential, quotaReason ? 'exhausted' : 'down', reason, serverOptions);
  data.events.push({
    type: 'credential_circuit_breaker',
    credentialId: credential.id,
    reason,
    at: now,
  });
}

function credentialCircuitBreakerReason(data, credential, estimatedQuotaCost, serverOptions = {}) {
  const dailySpendLimit = Number(credential.dailySpendLimitCents || serverOptions.gatewayDailySpendLimitCents || 0);
  const todaySpend = credentialDailySpendCents(data, credential, serverOptions);
  if (dailySpendLimit > 0 && todaySpend + Number(estimatedQuotaCost || 0) > dailySpendLimit) {
    return 'daily_spend_limit_reached';
  }

  const quotaRemaining = Number(credential.quotaRemaining || 0);
  const costSensitiveSupplier = isCostSensitiveSupplierCredential(credential);
  if (costSensitiveSupplier && quotaRemaining > 0 && todaySpend > quotaRemaining && isSlowGatewayCredential(data, credential, serverOptions)) {
    return 'daily_spend_exceeds_remaining_balance_slow_channel';
  }

  return '';
}

function credentialDailySpendCents(data, credential, serverOptions = {}) {
  const today = currentDate(serverOptions).toISOString().slice(0, 10);
  return (data.events || [])
    .filter((event) => event.type === 'gateway_routed')
    .filter((event) => event.credentialId === credential.id)
    .filter((event) => String(event.at || '').startsWith(today))
    .reduce((sum, event) => sum + Number(event.quotaCost || 0), 0);
}

function isCostSensitiveSupplierCredential(credential) {
  const text = [
    credential.baseUrl,
    credential.routeBaseUrl,
    credential.proxyBaseUrl,
    credential.sourceId,
    credential.riskNote,
    credential.supplierName,
    credential.sourceLabel,
  ].join(' ').toLowerCase();
  return Boolean(credential.costSensitive || /cost-sensitive|metered|slow-tier|reference-channel/.test(text));
}

function isSlowGatewayCredential(data, credential, serverOptions = {}) {
  const threshold = Number(credential.slowLatencyThresholdMs || serverOptions.gatewaySlowLatencyThresholdMs || DEFAULT_GATEWAY_SLOW_LATENCY_MS);
  if (!Number.isFinite(threshold) || threshold <= 0) {
    return false;
  }
  if (Number(credential.latencyMs || 0) >= threshold) {
    return true;
  }
  const today = currentDate(serverOptions).toISOString().slice(0, 10);
  return (data.events || [])
    .filter((event) => event.type === 'gateway_routed')
    .filter((event) => event.credentialId === credential.id)
    .filter((event) => String(event.at || '').startsWith(today))
    .some((event) => Number(event.latencyMs || 0) >= threshold);
}

async function maybeNotifyLowInventory(data, credential, serverOptions) {
  const threshold = Number(serverOptions.lowInventoryThresholdRatio || 0.05);
  if (!Number.isFinite(threshold) || threshold <= 0) {
    return;
  }

  const summary = buildInventorySummary(data).find(
    (item) => item.pool === credential.pool && item.providerGroup === effectiveCredentialGroup(credential),
  );
  if (!summary || summary.quotaTotal <= 0) {
    return;
  }

  const ratio = Number((summary.quotaRemaining / summary.quotaTotal).toFixed(4));
  const alertKey = `${summary.pool}:${summary.providerGroup}`;
  const previous = data.lowInventoryAlerts?.[alertKey]?.ratio ?? 1;
  if (ratio > threshold || ratio >= previous) {
    data.lowInventoryAlerts[alertKey] = {
      ratio,
      at: new Date().toISOString(),
    };
    return;
  }

  data.lowInventoryAlerts[alertKey] = {
    ratio,
    at: new Date().toISOString(),
  };

  const notifier = serverOptions.notifyLowInventory;
  if (typeof notifier === 'function') {
    await notifier({
      pool: summary.pool,
      providerGroup: summary.providerGroup,
      remainingRatio: ratio,
      quotaRemaining: summary.quotaRemaining,
      quotaTotal: summary.quotaTotal,
      nearestExpiresAt: summary.nearestExpiresAt,
      wasteText: summary.wasteText,
    });
  }
}

function credentialIssueTypeFromReason(reason = '') {
  const text = String(reason || '').toLowerCase();
  if (text.includes('quota') || text.includes('402') || text.includes('429')) {
    return 'quota';
  }
  if (text.includes('auth') || text.includes('401') || text.includes('403') || text.includes('forbidden')) {
    return 'auth';
  }
  if (text.includes('upstream') || text.includes('503') || text.includes('502') || text.includes('504') || text.includes('network')) {
    return 'upstream';
  }
  return '';
}

function upstreamHostFromCredential(credential) {
  const target = credential?.routeBaseUrl || credential?.baseUrl || '';
  try {
    return new URL(normalizeBaseUrl(target)).host;
  } catch {
    return '';
  }
}

async function maybeNotifyCredentialIssue(data, credential, reason, serverOptions) {
  const issueType = credentialIssueTypeFromReason(reason);
  if (!credential || !issueType) {
    return;
  }
  if (!data.upstreamKeyAlerts || typeof data.upstreamKeyAlerts !== 'object') {
    data.upstreamKeyAlerts = {};
  }
  const alertKey = `${credential.id}:${issueType}`;
  if (data.upstreamKeyAlerts?.[alertKey]) {
    return;
  }
  const at = currentDate(serverOptions).toISOString();
  data.upstreamKeyAlerts[alertKey] = {
    at,
    issueType,
    reason: String(reason || '').slice(0, 120),
    status: String(credential.status || ''),
  };

  const notifier = serverOptions.notifyCredentialIssue;
  if (typeof notifier !== 'function') {
    return;
  }

  await notifier({
    type: 'upstream_key_issue',
    issueType,
    reason: String(reason || '').slice(0, 120),
    keyPreview: credential.keyPreview || maskKey(credential.rawKey),
    pool: credential.pool || 'default',
    providerGroup: effectiveCredentialGroup(credential),
    modelGroup: credential.modelGroup || 'All',
    status: credential.status || '',
    quotaRemaining: Number(credential.quotaRemaining || 0),
    quotaTotal: Number(credential.quotaTotal || credential.quotaRemaining || 0),
    sourceHost: upstreamHostFromCredential(credential),
    connectionPath: credential.connectionPath || 'direct',
    at,
  });
}

function monitorCandidateCredentials(data, serverOptions) {
  const batchSize = Math.max(1, Number(serverOptions.channelMonitorBatchSize || DEFAULT_CHANNEL_MONITOR_BATCH_SIZE));
  const cooldownMs = Math.max(0, Number(serverOptions.channelMonitorCooldownMs ?? DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS));
  const nowMs = currentDate(serverOptions).getTime();
  const candidates = data.credentials
    .filter((credential) => credential.enabled && credential.status === 'healthy')
    .filter(isCredentialRouteApproved)
    .filter((credential) => String(credential.rawKey || '').trim())
    .filter((credential) => String(credential.baseUrl || '').trim())
    .filter((credential) => {
      const lastProbeAt = Date.parse(credential.lastAutoProbeAt || '');
      if (!Number.isFinite(lastProbeAt)) return true;
      return nowMs - lastProbeAt >= cooldownMs;
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.lastAutoProbeAt || '') || 0;
      const rightTime = Date.parse(right.lastAutoProbeAt || '') || 0;
      return leftTime - rightTime;
    });
  return candidates.slice(0, batchSize);
}

export async function runChannelMonitorSweep(data, serverOptions) {
  const credentials = monitorCandidateCredentials(data, serverOptions);
  for (const credential of credentials) {
    const probe = await probeCredentialRoutes({
      baseUrl: credential.baseUrl,
      proxyBaseUrl: credential.proxyBaseUrl || '',
      rawKey: credential.rawKey,
      authConfig: {
        authHeaderName: credential.authHeaderName || 'authorization',
        authHeaderValuePrefix:
          credential.authHeaderValuePrefix === ''
            ? ''
            : credential.authHeaderValuePrefix ?? 'Bearer',
        extraHeaders: credential.extraHeaders || {},
      },
      models: normalizeOfficialModelList(
        Array.isArray(credential.models) && credential.models.length > 0
          ? credential.models
          : [DEFAULT_MODEL],
      ),
      serverOptions,
      collectAllModels: false,
      preferAnthropicMessages: effectiveCredentialGroup(credential) === 'Claude',
    });
    const now = currentDate(serverOptions).toISOString();
    credential.lastAutoProbeAt = now;
    credential.lastProbeStatus = probe.status || '';
    credential.lastProbeReason = probe.reason || '';
    if (probe.ok) {
      credential.status = 'healthy';
      credential.enabled = isCredentialRouteApproved(credential);
      credential.routeBaseUrl = probe.routeBaseUrl || credential.routeBaseUrl || credential.baseUrl;
      credential.connectionPath = probe.connectionPath || credential.connectionPath || 'direct';
      if (Array.isArray(probe.models) && probe.models.length > 0) {
        credential.models = normalizeOfficialModelList(probe.models);
      }
      const latencyMs = Math.max(0, Number(probe.latencyMs || credential.latencyMs || 0) || 0);
      credential.latencyMs = latencyMs;
      credential.updatedAt = now;
      recordChannelProbeEvent(
        data,
        credential,
        latencyMs > 1600 ? 'slow' : 'ok',
        probe.status || 'auto_probe_ok',
        serverOptions,
        { latencyMs },
      );
      continue;
    }

    if (probe.status === 'quota_failed') {
      exhaustCredential(data, credential, 'auto_probe_quota_failed');
      credential.lastProbeReason = probe.reason || '上游额度不足或限速';
      await maybeNotifyCredentialIssue(data, credential, 'auto_probe_quota_failed', serverOptions);
      continue;
    }

    if (probe.status === 'auth_failed') {
      failCredential(data, credential, 'auto_probe_auth_failed');
      credential.lastProbeReason = probe.reason || '认证失败或 Key 无效';
      await maybeNotifyCredentialIssue(data, credential, 'auto_probe_auth_failed', serverOptions);
      continue;
    }

    failCredential(data, credential, `auto_probe_${probe.status || 'failed'}`);
    credential.lastProbeReason = probe.reason || '通道探测失败';
  }
}

function channelMonitorCredentialFingerprint(credential) {
  return createHash('sha256')
    .update(JSON.stringify({
      id: credential?.id || '',
      rawKey: credential?.rawKey || '',
      baseUrl: credential?.baseUrl || '',
      proxyBaseUrl: credential?.proxyBaseUrl || '',
      models: credential?.models || [],
      enabled: Boolean(credential?.enabled),
      status: credential?.status || '',
      updatedAt: credential?.updatedAt || '',
      lastAutoProbeAt: credential?.lastAutoProbeAt || '',
    }))
    .digest('hex');
}

async function runChannelMonitorOutsideWriteQueue(store, serverOptions) {
  const snapshot = await store.load();
  const candidates = monitorCandidateCredentials(snapshot, serverOptions).map((credential) => ({
    id: credential.id,
    fingerprint: channelMonitorCredentialFingerprint(credential),
  }));
  if (candidates.length === 0) {
    return;
  }
  const initialEventCount = snapshot.events.length;
  const initialAlertKeys = new Set(Object.keys(snapshot.upstreamKeyAlerts || {}));
  await runChannelMonitorSweep(snapshot, serverOptions);

  await store.mutate((data) => {
    const appliedIds = new Set();
    for (const candidate of candidates) {
      const current = data.credentials.find((credential) => credential.id === candidate.id);
      const probed = snapshot.credentials.find((credential) => credential.id === candidate.id);
      if (!current || !probed || channelMonitorCredentialFingerprint(current) !== candidate.fingerprint) {
        data.events.push({
          type: 'channel_monitor_result_skipped_after_concurrent_change',
          credentialId: candidate.id,
          at: currentDate(serverOptions).toISOString(),
        });
        continue;
      }
      Object.assign(current, probed);
      appliedIds.add(candidate.id);
    }

    for (const event of snapshot.events.slice(initialEventCount)) {
      if (!event.credentialId || appliedIds.has(event.credentialId)) {
        data.events.push(event);
      }
    }
    for (const [key, alert] of Object.entries(snapshot.upstreamKeyAlerts || {})) {
      if (initialAlertKeys.has(key)) continue;
      const credentialId = String(key).split(':', 1)[0];
      if (appliedIds.has(credentialId)) {
        data.upstreamKeyAlerts[key] = alert;
      }
    }
  });
}

function startChannelMonitor({ store, serverOptions }) {
  const intervalMs = Math.max(100, Number(serverOptions.channelMonitorIntervalMs || DEFAULT_CHANNEL_MONITOR_INTERVAL_MS));
  let stopped = false;
  let running = false;
  const runOnce = async () => {
    if (stopped || running) {
      return;
    }
    running = true;
    try {
      await runChannelMonitorOutsideWriteQueue(store, serverOptions);
    } catch {
      // 巡检失败不会阻断用户请求，下一轮继续执行。
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runOnce();
  }, intervalMs);
  if (typeof timer.unref === 'function') {
    timer.unref();
  }
  void runOnce();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

function startNewApiRedemptionStatusSync({ store, serverOptions }) {
  const intervalMs = Math.max(
    1000,
    Number(serverOptions.newApiRedemptionStatusSyncIntervalMs || DEFAULT_NEWAPI_REDEMPTION_STATUS_SYNC_INTERVAL_MS),
  );
  let stopped = false;
  let running = false;
  const runOnce = async () => {
    if (stopped || running) {
      return;
    }
    running = true;
    try {
      await store.mutate((data) => syncNewApiRedemptionStatuses(data, serverOptions));
    } catch {
      // New-API 回写失败只影响运营台状态刷新，不阻断注册、兑换和调用链路。
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runOnce();
  }, intervalMs);
  if (typeof timer.unref === 'function') {
    timer.unref();
  }
  void runOnce();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

function startUpstreamBalanceSync({ store, serverOptions, newApiBridge }) {
  const intervalMs = Math.max(60_000, Number(serverOptions.upstreamBalanceSyncIntervalMs || 86_400_000));
  let stopped = false;
  let running = false;
  const runOnce = async () => {
    if (stopped || running || !newApiBridge?.syncUpstreamBalance) {
      return;
    }
    running = true;
    try {
      const rawBalance = await newApiBridge.syncUpstreamBalance();
      const applied = await store.mutate((data) => applyUpstreamBalance(data, rawBalance, serverOptions));
      await notifyUpstreamBalanceIfNeeded(applied.balance, serverOptions);
    } catch (error) {
      await store.mutate((data) => {
        data.upstreamBalance = normalizeUpstreamBalanceRecord({
          ...data.upstreamBalance,
          provider: data.upstreamBalance?.provider || 'New-API',
          checkedAt: currentDate(serverOptions).toISOString(),
          lastError: String(error?.message || '同步失败').slice(0, 160),
          level: 'unknown',
        });
      });
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runOnce();
  }, intervalMs);
  if (typeof timer.unref === 'function') {
    timer.unref();
  }
  void runOnce();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

function startCardAutoreplenish({ store, serverOptions }) {
  const intervalMs = Math.max(60_000, Number(serverOptions.cardAutoreplenishIntervalMs || 86_400_000));
  let stopped = false;
  let running = false;
  const runOnce = async () => {
    if (stopped || running) {
      return;
    }
    running = true;
    try {
      await store.mutate((data) => autoReplenishRedemptionCards(data, { dryRun: false, enabled: true }, serverOptions));
    } catch {
      // 自动补卡失败只影响库存水位，不阻断注册、兑换和模型调用；管理端仍可手动补卡。
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runOnce();
  }, intervalMs);
  if (typeof timer.unref === 'function') {
    timer.unref();
  }
  void runOnce();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

async function maybeNotifyCustomerLowBalance(data, user, serverOptions, context = {}) {
  const alert = normalizeBalanceAlertRecord(user.balanceAlert, user.email);
  user.balanceAlert = alert;
  if (!alert.enabled || alert.thresholdCents <= 0 || !alert.email) {
    return;
  }
  const balanceCents = Number(context.afterUserQuota ?? availableQuotaCents(user));
  if (balanceCents > alert.thresholdCents) {
    alert.lastTriggeredThresholdCents = 0;
    return;
  }

  const beforeBalanceCents = Number(context.beforeUserQuota ?? balanceCents);
  const crossedThreshold = beforeBalanceCents > alert.thresholdCents && balanceCents <= alert.thresholdCents;
  const thresholdChanged = Number(alert.lastTriggeredThresholdCents || 0) !== alert.thresholdCents;
  if (!crossedThreshold && !thresholdChanged) {
    return;
  }

  const sender = serverOptions.balanceAlertEmailSender;
  if (typeof sender !== 'function') {
    return;
  }

  const now = new Date().toISOString();
  const message = buildBalanceAlertEmail({
    user,
    to: alert.email,
    thresholdCents: alert.thresholdCents,
    balanceCents,
    previousBalanceCents: beforeBalanceCents,
    model: context.model,
    quotaCost: context.quotaCost,
    publicGatewayBaseUrl: serverOptions.publicGatewayBaseUrl,
    at: now,
  });

  try {
    await sender(message);
    alert.lastAlertAt = now;
    alert.lastAlertBalanceCents = balanceCents;
    alert.lastTriggeredThresholdCents = alert.thresholdCents;
    data.events.push({
      type: 'balance_alert_sent',
      userId: user.id,
      thresholdCents: alert.thresholdCents,
      balanceCents,
      alertEmail: maskEmail(alert.email),
      model: context.model || '',
      at: now,
    });
  } catch {
    data.events.push({
      type: 'balance_alert_failed',
      userId: user.id,
      thresholdCents: alert.thresholdCents,
      balanceCents,
      alertEmail: maskEmail(alert.email),
      at: now,
    });
  }
}



async function verifyTurnstileToken({ request, body, serverOptions, action }) {
  if (!serverOptions.requireTurnstile) {
    return;
  }
  const token = String(body.turnstileToken || body.cfTurnstileResponse || body['cf-turnstile-response'] || '').trim();
  if (!token) {
    throw publicError(400, '请先完成人机验证');
  }
  if (!serverOptions.turnstileSecret) {
    throw publicError(503, '安全验证暂时不可用，请稍后再试');
  }
  const fetchImpl = serverOptions.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') {
    throw publicError(503, '安全验证暂时不可用，请稍后再试');
  }

  const payload = new URLSearchParams({
    secret: serverOptions.turnstileSecret,
    response: token,
  });
  const remoteIp = clientIp(request, serverOptions);
  if (remoteIp && remoteIp !== 'unknown') {
    payload.set('remoteip', remoteIp);
  }

  let result;
  try {
    const verification = await fetchImpl(serverOptions.turnstileVerifyUrl, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: payload.toString(),
    });
    result = typeof verification.json === 'function' ? await verification.json() : {};
  } catch {
    throw publicError(503, '安全验证暂时不可用，请稍后再试');
  }

  if (!result?.success) {
    throw publicError(403, '人机验证失败，请刷新后重试');
  }
  if (action && result.action && result.action !== action) {
    throw publicError(403, '人机验证已过期，请刷新后重试');
  }
  const hostname = normalizeCanonicalHost(result.hostname || '');
  if (serverOptions.turnstileAllowedHostnames.size > 0 && !serverOptions.turnstileAllowedHostnames.has(hostname)) {
    throw publicError(403, '人机验证已过期，请刷新后重试');
  }
}

function randomInt(max) {
  return randomBytes(1)[0] % Math.max(1, Number(max) || 1);
}


async function pipeReadableStreamToResponse(bodyStream, response, options = {}) {
  const abort = typeof options.abort === 'function' ? options.abort : null;
  let closed = false;
  response.once?.('close', () => {
    closed = true;
    abort?.();
  });
  if (typeof bodyStream.getReader === 'function') {
    const reader = bodyStream.getReader();
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        if (closed || response.destroyed) {
          await reader.cancel?.();
          break;
        }
        response.write(normalizeStreamChunk(chunk.value));
      }
    } finally {
      abort?.();
      reader.releaseLock?.();
      if (!response.destroyed) response.end();
    }
    return;
  }

  if (typeof bodyStream[Symbol.asyncIterator] === 'function') {
    try {
      for await (const chunk of bodyStream) {
        if (closed || response.destroyed) break;
        response.write(normalizeStreamChunk(chunk));
      }
    } finally {
      abort?.();
      if (!response.destroyed) response.end();
    }
    return;
  }

  abort?.();
  if (!response.destroyed) response.end();
}


function normalizeRuntimeData(data) {
  const pricing = normalizePricingConfig(data.pricing || {});
  return {
    users: Array.isArray(data.users) ? data.users.map(normalizeUserRecord) : [],
    sessions: data.sessions && typeof data.sessions === 'object' ? data.sessions : {},
    sessionCsrfTokens: data.sessionCsrfTokens && typeof data.sessionCsrfTokens === 'object' ? data.sessionCsrfTokens : {},
    adminSecondFactorSessions: data.adminSecondFactorSessions && typeof data.adminSecondFactorSessions === 'object' ? data.adminSecondFactorSessions : {},
    newApiTokenOwners: data.newApiTokenOwners && typeof data.newApiTokenOwners === 'object' ? data.newApiTokenOwners : {},
    newApiTokenCreateIntents:
      data.newApiTokenCreateIntents && typeof data.newApiTokenCreateIntents === 'object'
        ? data.newApiTokenCreateIntents
        : {},
    userKeys: Array.isArray(data.userKeys) ? data.userKeys : [],
    credentials: Array.isArray(data.credentials) ? data.credentials.map(normalizeCredentialRecord) : [],
    supplierProfiles: Array.isArray(data.supplierProfiles) ? data.supplierProfiles.map(normalizeSupplierProfileRecord) : [],
    priceDrafts: mergeModelPrices(Array.isArray(data.priceDrafts) ? data.priceDrafts : [], pricing.modelPrices),
    pricing,
    paymentOrders: Array.isArray(data.paymentOrders) ? data.paymentOrders : [],
    redemptions: Array.isArray(data.redemptions) ? data.redemptions : [],
    redemptionCards: Array.isArray(data.redemptionCards) ? data.redemptionCards.map(normalizeRedemptionCardRecord) : [],
    plusAccounts: Array.isArray(data.plusAccounts) ? data.plusAccounts.map(normalizePlusAccountRecord) : [],
    rtAccounts: Array.isArray(data.rtAccounts) ? data.rtAccounts.map(normalizeRtAccountRecord) : [],
    upstreamChannelSnapshots: Array.isArray(data.upstreamChannelSnapshots)
      ? data.upstreamChannelSnapshots.map(normalizeUpstreamChannelRecord).filter(Boolean)
      : [],
    upstreamBalance: normalizeUpstreamBalanceRecord(data.upstreamBalance),
    xianyuFulfillments: Array.isArray(data.xianyuFulfillments)
      ? data.xianyuFulfillments.map(normalizeXianyuFulfillmentRecord).filter(Boolean)
      : [],
    routeAffinities: data.routeAffinities && typeof data.routeAffinities === 'object' ? data.routeAffinities : {},
    lowInventoryAlerts: data.lowInventoryAlerts && typeof data.lowInventoryAlerts === 'object' ? data.lowInventoryAlerts : {},
    upstreamKeyAlerts: data.upstreamKeyAlerts && typeof data.upstreamKeyAlerts === 'object' ? data.upstreamKeyAlerts : {},
    backupStatus: normalizeBackupStatusRecord(data.backupStatus),
    channelProbeEvents: Array.isArray(data.channelProbeEvents) ? data.channelProbeEvents.map(normalizeChannelProbeEvent).filter(Boolean) : [],
    usedAdminClaimCodeHashes: Array.isArray(data.usedAdminClaimCodeHashes) ? data.usedAdminClaimCodeHashes : [],
    events: Array.isArray(data.events) ? data.events : [],
  };
}

function normalizeUserRecord(user) {
  const email = normalizeAlertEmail(user?.email || '');
  return {
    ...user,
    passwordReset: normalizePasswordResetRecord(user?.passwordReset),
    balanceAlert: normalizeBalanceAlertRecord(user?.balanceAlert, email),
  };
}

function normalizePasswordResetRecord(record) {
  if (!record || typeof record !== 'object') {
    return null;
  }
  return {
    codeHash: String(record.codeHash || ''),
    expiresAt: String(record.expiresAt || ''),
    usedAt: String(record.usedAt || ''),
    requestedAt: String(record.requestedAt || ''),
  };
}



function normalizeRedemptionCardRecord(card) {
  const plan = normalizeRechargePlan(card?.plan || 'balance');
  const code = normalizeCardCode(card?.code || '');
  const codeHash = String(card?.codeHash || (code ? hashRedemptionCode(code) : '')).trim();
  const codePreview = String(card?.codePreview || maskCardCode(code)).trim();
  return {
    id: String(card?.id || createId('card')),
    batchId: String(card?.batchId || ''),
    code,
    codeHash,
    codeCipher: String(card?.codeCipher || '').trim(),
    codePreview,
    label: String(card?.label || 'CC中转 兑换码').trim(),
    planId: String(card?.planId || '').trim(),
    plan,
    durationDays: Math.max(0, Number(card?.durationDays || (plan === 'month' ? 30 : plan === 'day' ? 1 : 0))),
    quotaUsd: Math.max(0, Number(card?.quotaUsd || 0)),
    priceCny: round2(Number(card?.priceCny || 0)),
    creditCents: Math.max(0, Number(card?.creditCents || 0)),
    status: ['unused', 'sold', 'redeemed', 'disabled'].includes(String(card?.status || 'unused')) ? String(card.status || 'unused') : 'unused',
    source: String(card?.source || 'xianyu'),
    note: String(card?.note || ''),
    createdAt: String(card?.createdAt || ''),
    updatedAt: String(card?.updatedAt || card?.createdAt || ''),
    soldAt: String(card?.soldAt || ''),
    soldOrderId: String(card?.soldOrderId || ''),
    soldPlatform: String(card?.soldPlatform || ''),
    soldBuyerHint: String(card?.soldBuyerHint || ''),
    fulfillmentId: String(card?.fulfillmentId || ''),
    deliveredAt: String(card?.deliveredAt || ''),
    redeemedAt: String(card?.redeemedAt || ''),
    redeemedBy: String(card?.redeemedBy || ''),
    redeemedEmail: String(card?.redeemedEmail || ''),
  };
}

function normalizeUpstreamChannelRecord(channel) {
  const normalized = normalizeUpstreamChannelSnapshot([channel], { markup: channel?.markup ?? 0 })[0];
  if (!normalized) return null;
  const upstreamMultiplier = Number(channel?.upstreamMultiplier);
  const saleMultiplier = Number(channel?.saleMultiplier);
  return {
    ...normalized,
    upstreamMultiplier: Number.isFinite(upstreamMultiplier) ? round2(upstreamMultiplier) : normalized.upstreamMultiplier,
    saleMultiplier: Number.isFinite(saleMultiplier) ? round2(saleMultiplier) : normalized.saleMultiplier,
    source: String(channel?.source || 'reference-channel').trim(),
    syncedAt: String(channel?.syncedAt || channel?.checkedAt || ''),
  };
}

function normalizeUpstreamBalanceRecord(record = {}) {
  const remainingCny = Number(record?.remainingCny || 0);
  const warningCny = Number(record?.warningCny || 50);
  const criticalCny = Number(record?.criticalCny || 20);
  return {
    provider: String(record?.provider || '').slice(0, 80),
    userId: String(record?.userId || '').slice(0, 80),
    username: String(record?.username || '').slice(0, 80),
    emailMasked: maskEmail(record?.emailMasked || ''),
    group: String(record?.group || '').slice(0, 80),
    remainingQuota: Math.max(0, Number(record?.remainingQuota || 0)),
    usedQuota: Math.max(0, Number(record?.usedQuota || 0)),
    remainingCny: round2(Math.max(0, remainingCny)),
    usedCny: round2(Math.max(0, Number(record?.usedCny || 0))),
    remainingUsd: round2(Math.max(0, Number(record?.remainingUsd || 0))),
    warningCny: round2(Math.max(0, warningCny)),
    criticalCny: round2(Math.max(0, criticalCny)),
    level: normalizeUpstreamBalanceLevel(record?.level, remainingCny, warningCny, criticalCny),
    pauseRecommended: Boolean(record?.pauseRecommended),
    checkedAt: String(record?.checkedAt || ''),
    lastError: String(record?.lastError || '').slice(0, 200),
  };
}

function normalizeXianyuFulfillmentRecord(item) {
  const status = String(item?.status || 'draft').trim().toLowerCase();
  return {
    id: String(item?.id || createId('fulfill')),
    platform: String(item?.platform || 'xianyu').trim().toLowerCase(),
    orderId: String(item?.orderId || '').trim(),
    productTitle: String(item?.productTitle || '').trim().slice(0, 160),
    buyerHint: String(item?.buyerHint || '').trim().slice(0, 120),
    planId: String(item?.planId || '').trim(),
    cardId: String(item?.cardId || '').trim(),
    cardCode: String(item?.cardCode || item?.cardCodePreview || '').trim().toUpperCase(),
    status: ['draft', 'sold', 'delivered', 'redeemed', 'cancelled'].includes(status) ? status : 'draft',
    deliveryMessage: String(item?.deliveryMessage || '').trim().slice(0, 2000),
    note: String(item?.note || '').trim().slice(0, 500),
    createdAt: String(item?.createdAt || ''),
    updatedAt: String(item?.updatedAt || item?.createdAt || ''),
    deliveredAt: String(item?.deliveredAt || ''),
    redeemedAt: String(item?.redeemedAt || ''),
    redeemedEmail: String(item?.redeemedEmail || ''),
  };
}

function normalizePlusAccountRecord(account) {
  const openaiEmail = normalizeAlertEmail(account?.openaiEmail || '');
  const appleEmail = normalizeAlertEmail(account?.appleEmail || '');
  const status = normalizePlusAccountStatus(account?.status || '');
  const complianceStatus = normalizePlusAccountComplianceStatus(account?.complianceStatus || '');
  return {
    id: String(account?.id || createId('plus')),
    label: String(account?.label || openaiEmail || appleEmail || 'ChatGPT Plus 账号').trim().slice(0, 80),
    openaiEmail,
    appleEmail,
    region: normalizePlusAccountRegion(account?.region || 'Türkiye'),
    status,
    complianceStatus,
    billingMethod: String(account?.billingMethod || 'apple_iap').trim().slice(0, 60),
    appleBalanceTry: round2Finite(account?.appleBalanceTry),
    monthlyCostTry: round2Finite(account?.monthlyCostTry),
    plusRenewalAt: String(account?.plusRenewalAt || ''),
    lastCheckedAt: String(account?.lastCheckedAt || ''),
    deviceProfile: String(account?.deviceProfile || '').trim().slice(0, 120),
    browserProfile: String(account?.browserProfile || '').trim().slice(0, 120),
    riskNote: sanitizeRiskNote(account?.riskNote || ''),
    operatorNote: String(account?.operatorNote || '').trim().slice(0, 500),
    secrets: String(account?.secrets || '').trim().slice(0, 1000),
    routingEnabled: false,
    createdAt: String(account?.createdAt || ''),
    updatedAt: String(account?.updatedAt || ''),
  };
}

function normalizeRtAccountRecord(account) {
  const refreshToken = String(
    account?.refreshToken ?? account?.refresh_token ?? account?.rt ?? account?.token ?? '',
  ).trim().slice(0, 4000);
  const email = normalizeAlertEmail(account?.email || '');
  const platform = normalizeRtPlatform(account?.platform || account?.provider || '');
  const status = normalizeRtAccountStatus(account?.status || '');
  const accountId = String(account?.accountId ?? account?.account_id ?? '').trim().slice(0, 160);
  const fingerprint = String(account?.refreshTokenFingerprint || tokenFingerprint(refreshToken)).trim();
  return {
    id: String(account?.id || createId('rt')),
    label: String(account?.label || email || accountId || 'RT 账号').trim().slice(0, 80),
    platform,
    status,
    email,
    accountId,
    refreshToken,
    refreshTokenFingerprint: fingerprint,
    sourceLabel: String(account?.sourceLabel || '').trim().slice(0, 80),
    accountType: String(account?.accountType || '').trim().slice(0, 60),
    note: sanitizeRiskNote(account?.note || account?.riskNote || ''),
    lastRefreshAt: String(account?.lastRefreshAt || ''),
    expiresAt: String(account?.expiresAt || account?.expired || ''),
    importedAt: String(account?.importedAt || account?.createdAt || ''),
    createdAt: String(account?.createdAt || ''),
    updatedAt: String(account?.updatedAt || ''),
    routingEnabled: false,
  };
}

function normalizeBackupStatusRecord(record) {
  const current = record && typeof record === 'object' ? record : {};
  return {
    provider: String(current.provider || '').trim().slice(0, 80),
    target: String(current.target || '').trim().slice(0, 160),
    lastBackupAt: String(current.lastBackupAt || ''),
    lastRestoreTestAt: String(current.lastRestoreTestAt || ''),
    status: ['ok', 'warning', 'failed'].includes(String(current.status || '')) ? String(current.status) : 'warning',
    artifact: String(current.artifact || '').trim().slice(0, 180),
    sizeBytes: Math.max(0, Number(current.sizeBytes || 0) || 0),
    checksum: String(current.checksum || '').trim().slice(0, 128),
    message: String(current.message || '').trim().slice(0, 240),
    updatedAt: String(current.updatedAt || current.lastBackupAt || ''),
  };
}

function normalizeChannelProbeEvent(event) {
  if (!event || typeof event !== 'object') {
    return null;
  }
  const model = normalizeOfficialModelName(event.model);
  const status = normalizeSlaStatus(event.status);
  const at = String(event.at || '');
  if (!model || !status || !at) {
    return null;
  }
  return {
    id: String(event.id || createId('sla')),
    model,
    provider: event.provider || providerFromModel(model),
    credentialId: String(event.credentialId || ''),
    status,
    reason: String(event.reason || '').slice(0, 120),
    latencyMs: Math.max(0, Number(event.latencyMs || 0) || 0),
    pool: String(event.pool || ''),
    at,
  };
}

function normalizeSlaStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'ok' || status === 'healthy' || status === 'success') return 'ok';
  if (status === 'slow' || status === 'degraded') return 'slow';
  if (status === 'down' || status === 'failed' || status === 'exhausted') return 'down';
  return '';
}





function normalizeCardAutoreplenishSafetyStock(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.fromEntries(
      Object.entries({ ...DEFAULT_CARD_AUTOREPLENISH_SAFETY_STOCK, ...value })
        .map(([key, count]) => [String(key), Math.max(0, Math.round(Number(count || 0)))]),
    );
  }
  const text = String(value || '').trim();
  if (!text) return { ...DEFAULT_CARD_AUTOREPLENISH_SAFETY_STOCK };
  try {
    return normalizeCardAutoreplenishSafetyStock(JSON.parse(text));
  } catch {
    const parsed = {};
    for (const part of text.split(/[,\n;]/)) {
      const [rawKey, rawValue] = part.split(/[:=]/);
      const key = String(rawKey || '').trim();
      if (!key) continue;
      parsed[key] = Math.max(0, Math.round(Number(rawValue || 0)));
    }
    return normalizeCardAutoreplenishSafetyStock(parsed);
  }
}


function normalizeServerOptions(options) {
  const root = dirname(fileURLToPath(import.meta.url));
  const envPublicMode = parseOptionalEnvFlag(process.env.FRIST_API_PUBLIC_MODE);
  const publicMode =
    typeof options.publicMode === 'boolean'
      ? options.publicMode
      : envPublicMode ?? process.env.NODE_ENV === 'production';
  const rawAdminClaimCodes =
    options.adminClaimCodes ?? process.env.FRIST_API_ADMIN_CLAIM_CODES ?? process.env.FRIST_API_ADMIN_CLAIM_CODE ?? '';
  const adminClaimCodes = parseAdminClaimCodes(rawAdminClaimCodes);
  const rawAdminTotpSecrets =
    options.adminTotpSecrets ?? process.env.FRIST_API_ADMIN_TOTP_SECRETS ?? process.env.FRIST_API_ADMIN_TOTP_SECRET ?? '';
  const adminTotpSecretValues = (Array.isArray(rawAdminTotpSecrets)
    ? rawAdminTotpSecrets
    : String(rawAdminTotpSecrets || '').split(/[,\s]+/))
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  const exposeVerificationCode =
    typeof options.exposeVerificationCode === 'boolean'
      ? options.exposeVerificationCode
      : process.env.FRIST_API_EXPOSE_VERIFICATION_CODE === '1';
  const allowDemoRecharge =
    typeof options.allowDemoRecharge === 'boolean'
      ? options.allowDemoRecharge
      : process.env.FRIST_API_ALLOW_DEMO_RECHARGE === '1';
  const requireEmailVerification =
    typeof options.requireEmailVerification === 'boolean'
      ? options.requireEmailVerification
      : parseOptionalEnvFlag(process.env.FRIST_API_REQUIRE_EMAIL_VERIFICATION) ?? publicMode;
  const requireCaptcha =
    typeof options.requireCaptcha === 'boolean'
      ? options.requireCaptcha
      : process.env.FRIST_API_REQUIRE_CAPTCHA === '1';
  const requireTurnstile =
    typeof options.requireTurnstile === 'boolean'
      ? options.requireTurnstile
      : process.env.FRIST_API_REQUIRE_TURNSTILE === '1';
  const normalized = {
    adminToken: options.adminToken || process.env.FRIST_API_ADMIN_TOKEN || 'frist-api-dev-admin-token',
    adminPageCode: options.adminPageCode || process.env.FRIST_API_ADMIN_PAGE_CODE || '',
    adminClaimCodes,
    adminClaimCodeHashes: adminClaimCodes.map(hashAdminClaimCode),
    dataFile: options.dataFile || process.env.FRIST_API_DATA_FILE || join(root, '../data/runtime.json'),
    runtimeBeforeSave: options.runtimeBeforeSave,
    exposeVerificationCode,
    fetchImpl: options.fetchImpl,
    authRateLimitMax: Number(options.authRateLimitMax ?? process.env.FRIST_API_AUTH_RATE_LIMIT_MAX ?? 20),
    authRateLimitWindowMs: Number(
      options.authRateLimitWindowMs ?? process.env.FRIST_API_AUTH_RATE_LIMIT_WINDOW_MS ?? 60_000,
    ),
    passwordResetConfirmRateLimitMax: Number(
      options.passwordResetConfirmRateLimitMax ?? process.env.FRIST_API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_MAX ?? 5,
    ),
    passwordResetConfirmRateLimitWindowMs: Number(
      options.passwordResetConfirmRateLimitWindowMs ??
        process.env.FRIST_API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_WINDOW_MS ??
        900_000,
    ),
    passwordResetRequestRateLimitMax: Number(
      options.passwordResetRequestRateLimitMax ?? process.env.FRIST_API_PASSWORD_RESET_REQUEST_RATE_LIMIT_MAX ?? 3,
    ),
    passwordResetRequestRateLimitWindowMs: Number(
      options.passwordResetRequestRateLimitWindowMs ??
        process.env.FRIST_API_PASSWORD_RESET_REQUEST_RATE_LIMIT_WINDOW_MS ??
        900_000,
    ),
    emailVerificationRateLimitMax: Number(
      options.emailVerificationRateLimitMax ?? process.env.FRIST_API_EMAIL_VERIFICATION_RATE_LIMIT_MAX ?? 5,
    ),
    emailVerificationRateLimitWindowMs: Number(
      options.emailVerificationRateLimitWindowMs ??
        process.env.FRIST_API_EMAIL_VERIFICATION_RATE_LIMIT_WINDOW_MS ??
        900_000,
    ),
    rateLimitMaxEntries: Number(
      options.rateLimitMaxEntries ?? process.env.FRIST_API_RATE_LIMIT_MAX_ENTRIES ?? DEFAULT_RATE_LIMIT_MAX_ENTRIES,
    ),
    trustedProxyIps: parseTrustedProxyIps(
      options.trustedProxyIps ?? process.env.FRIST_API_TRUSTED_PROXY_IPS ?? '',
    ),
    redemptionRateLimitMax: Number(options.redemptionRateLimitMax ?? process.env.FRIST_API_REDEEM_RATE_LIMIT_MAX ?? 12),
    redemptionRateLimitWindowMs: Number(
      options.redemptionRateLimitWindowMs ?? process.env.FRIST_API_REDEEM_RATE_LIMIT_WINDOW_MS ?? 60_000,
    ),
    captchaTtlMs: Number(options.captchaTtlMs ?? process.env.FRIST_API_CAPTCHA_TTL_MS ?? 600_000),
    captchaMaxAttempts: Number(options.captchaMaxAttempts ?? process.env.FRIST_API_CAPTCHA_MAX_ATTEMPTS ?? 3),
    requireTurnstile,
    turnstileSiteKey: options.turnstileSiteKey || process.env.FRIST_API_TURNSTILE_SITE_KEY || '',
    turnstileSecret: options.turnstileSecret || process.env.FRIST_API_TURNSTILE_SECRET || '',
    turnstileVerifyUrl:
      options.turnstileVerifyUrl ||
      process.env.FRIST_API_TURNSTILE_VERIFY_URL ||
      'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    turnstileAllowedHostnames: parseRedirectHosts(
      options.turnstileAllowedHostnames ?? process.env.FRIST_API_TURNSTILE_ALLOWED_HOSTNAMES ?? '',
    ),
    passwordResetTtlMs: Number(options.passwordResetTtlMs ?? process.env.FRIST_API_PASSWORD_RESET_TTL_MS ?? 900_000),
    sessionTtlMs: Math.min(
      30 * 24 * 60 * 60 * 1000,
      Math.max(
        5 * 60 * 1000,
        Number(options.sessionTtlMs ?? process.env.FRIST_API_SESSION_TTL_MS ?? DEFAULT_SESSION_TTL_MS),
      ),
    ),
    keepAliveTimeoutMs:
      options.keepAliveTimeoutMs === undefined && process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS === undefined
        ? Number.NaN
        : Number(options.keepAliveTimeoutMs ?? process.env.FRIST_API_KEEP_ALIVE_TIMEOUT_MS),
    probeTimeoutMs: Number(options.probeTimeoutMs || process.env.FRIST_API_PROBE_TIMEOUT_MS || 8000),
    publicDir: options.publicDir ? resolve(options.publicDir) : resolve(root, '..'),
    publicGatewayBaseUrl: options.publicGatewayBaseUrl || process.env.FRIST_API_PUBLIC_GATEWAY_BASE_URL || '',
    canonicalHost: normalizeCanonicalHost(
      options.canonicalHost ?? process.env.FRIST_API_CANONICAL_HOST ?? DEFAULT_CANONICAL_HOST,
    ),
    redirectHosts: parseRedirectHosts(
      options.redirectHosts ?? process.env.FRIST_API_REDIRECT_HOSTS ?? DEFAULT_REDIRECT_HOSTS.join(','),
    ),
    dataEncryptionKey: options.dataEncryptionKey || process.env.FRIST_API_DATA_ENCRYPTION_KEY || '',
    quotaCost: Number(options.quotaCost || DEFAULT_QUOTA_COST),
    requireEmailVerification,
    requireCaptcha,
    sessionSecret: options.sessionSecret || process.env.FRIST_API_SESSION_SECRET || 'frist-api-dev-session-secret',
    passwordHashSecret:
      options.passwordHashSecret ||
      process.env.FRIST_API_PASSWORD_HASH_SECRET ||
      options.sessionSecret ||
      process.env.FRIST_API_SESSION_SECRET ||
      'frist-api-dev-session-secret',
    legacyPasswordHashSecrets: parseSecretList(
      options.legacyPasswordHashSecrets ?? process.env.FRIST_API_LEGACY_PASSWORD_HASH_SECRETS ?? '',
    ),
    allowDemoRecharge,
    newApiEnabled:
      typeof options.newApiEnabled === 'boolean'
        ? options.newApiEnabled
        : process.env.FRIST_API_NEWAPI_ENABLED === '1',
    newApiBaseUrl: options.newApiBaseUrl || process.env.FRIST_API_NEWAPI_BASE_URL || '',
    newApiAccessToken: options.newApiAccessToken || process.env.FRIST_API_NEWAPI_ACCESS_TOKEN || '',
    newApiUserId: options.newApiUserId || process.env.FRIST_API_NEWAPI_USER_ID || '',
    newApiSqliteDb: Object.hasOwn(options, 'newApiSqliteDb')
      ? options.newApiSqliteDb
      : process.env.FRIST_API_NEWAPI_SQLITE_DB || resolve(root, '../../../data/newapi/one-api.db'),
    newApiDefaultGroup: options.newApiDefaultGroup || process.env.FRIST_API_NEWAPI_DEFAULT_GROUP || 'default',
    newApiDefaultTokenQuota: Number(
      options.newApiDefaultTokenQuota ?? process.env.FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA ?? 0,
    ),
    newApiRequestTimeoutMs: Number(
      options.newApiRequestTimeoutMs ?? process.env.FRIST_API_NEWAPI_REQUEST_TIMEOUT_MS ?? 15_000,
    ),
    newApiGatewayBaseUrl:
      options.newApiGatewayBaseUrl || process.env.FRIST_API_NEWAPI_GATEWAY_BASE_URL || '',
    newApiGatewayEnabled:
      typeof options.newApiGatewayEnabled === 'boolean'
        ? options.newApiGatewayEnabled
        : process.env.FRIST_API_NEWAPI_GATEWAY_ENABLED === '1',
    newApiRedemptionStatusSyncEnabled:
      typeof options.newApiRedemptionStatusSyncEnabled === 'boolean'
        ? options.newApiRedemptionStatusSyncEnabled
        : process.env.FRIST_API_NEWAPI_REDEMPTION_STATUS_SYNC_ENABLED !== '0',
    newApiRedemptionStatusSyncIntervalMs: Number(
      options.newApiRedemptionStatusSyncIntervalMs ??
        process.env.FRIST_API_NEWAPI_REDEMPTION_STATUS_SYNC_INTERVAL_MS ??
        DEFAULT_NEWAPI_REDEMPTION_STATUS_SYNC_INTERVAL_MS,
    ),
    requireNewApiDatabase:
      typeof options.requireNewApiDatabase === 'boolean'
        ? options.requireNewApiDatabase
        : process.env.FRIST_API_REQUIRE_NEWAPI_DATABASE === '1',
    enforceProductionReadiness:
      typeof options.enforceProductionReadiness === 'boolean'
        ? options.enforceProductionReadiness
        : process.env.FRIST_API_ENFORCE_PRODUCTION_READINESS === '1',
    requireAdmin2fa:
      typeof options.requireAdmin2fa === 'boolean'
        ? options.requireAdmin2fa
        : process.env.FRIST_API_REQUIRE_ADMIN_2FA === '1',
    adminTotpSecretValues,
    adminTotpSecrets: normalizeTotpSecrets(adminTotpSecretValues),
    admin2faSessionTtlMs: Number(options.admin2faSessionTtlMs ?? process.env.FRIST_API_ADMIN_2FA_SESSION_TTL_MS ?? 3_600_000),
    admin2faRateLimitMax: Number(
      options.admin2faRateLimitMax ?? process.env.FRIST_API_ADMIN_2FA_RATE_LIMIT_MAX ?? 5,
    ),
    admin2faRateLimitWindowMs: Number(
      options.admin2faRateLimitWindowMs ?? process.env.FRIST_API_ADMIN_2FA_RATE_LIMIT_WINDOW_MS ?? 900_000,
    ),
    backupStatusMaxAgeHours: Number(options.backupStatusMaxAgeHours ?? process.env.FRIST_API_BACKUP_STATUS_MAX_AGE_HOURS ?? 26),
    slaRetentionDays: Number(options.slaRetentionDays ?? process.env.FRIST_API_SLA_RETENTION_DAYS ?? DEFAULT_SLA_RETENTION_DAYS),
    allowInsecurePublicHttp:
      typeof options.allowInsecurePublicHttp === 'boolean'
        ? options.allowInsecurePublicHttp
        : process.env.FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP === '1',
    requireCsrf:
      typeof options.requireCsrf === 'boolean'
        ? options.requireCsrf
        : process.env.FRIST_API_REQUIRE_CSRF === '1' || process.env.FRIST_API_PUBLIC_MODE === '1' || process.env.NODE_ENV === 'production',
    allowPrivateUpstreamUrls:
      typeof options.allowPrivateUpstreamUrls === 'boolean'
        ? options.allowPrivateUpstreamUrls
        : process.env.FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS === '1',
    resolveUpstreamAddresses: options.resolveUpstreamAddresses,
    publicMode,
    nowFactory: typeof options.nowFactory === 'function' ? options.nowFactory : () => new Date(),
    lowInventoryThresholdRatio: Number(
      options.lowInventoryThresholdRatio ?? process.env.FRIST_API_LOW_INVENTORY_THRESHOLD_RATIO ?? 0.05,
    ),
    notifyLowInventory:
      typeof options.notifyLowInventory === 'function'
        ? options.notifyLowInventory
        : createLowInventoryWebhookNotifier(options.fetchImpl || globalThis.fetch),
    channelMonitorEnabled:
      typeof options.channelMonitorEnabled === 'boolean'
        ? options.channelMonitorEnabled
        : process.env.FRIST_API_CHANNEL_MONITOR_ENABLED === '1',
    channelMonitorIntervalMs: Number(
      options.channelMonitorIntervalMs ?? process.env.FRIST_API_CHANNEL_MONITOR_INTERVAL_MS ?? DEFAULT_CHANNEL_MONITOR_INTERVAL_MS,
    ),
    channelMonitorBatchSize: Number(
      options.channelMonitorBatchSize ?? process.env.FRIST_API_CHANNEL_MONITOR_BATCH_SIZE ?? DEFAULT_CHANNEL_MONITOR_BATCH_SIZE,
    ),
    channelMonitorCooldownMs: Number(
      options.channelMonitorCooldownMs ?? process.env.FRIST_API_CHANNEL_MONITOR_COOLDOWN_MS ?? DEFAULT_CHANNEL_MONITOR_COOLDOWN_MS,
    ),
    notifyCredentialIssue:
      typeof options.notifyCredentialIssue === 'function'
        ? options.notifyCredentialIssue
        : createCredentialIssueNotifier(options.fetchImpl || globalThis.fetch),
    gatewayDailySpendLimitCents: Number(
      options.gatewayDailySpendLimitCents ?? process.env.FRIST_API_GATEWAY_DAILY_SPEND_LIMIT_CENTS ?? 0,
    ),
    gatewaySlowLatencyThresholdMs: Number(
      options.gatewaySlowLatencyThresholdMs ?? process.env.FRIST_API_GATEWAY_SLOW_LATENCY_MS ?? DEFAULT_GATEWAY_SLOW_LATENCY_MS,
    ),
    rateMarkup: Number.isFinite(Number(options.rateMarkup ?? process.env.FRIST_API_RATE_MARKUP ?? 0.1))
      ? Number(options.rateMarkup ?? process.env.FRIST_API_RATE_MARKUP ?? 0.1)
      : 0.1,
    xianyuWebhookToken: String(options.xianyuWebhookToken ?? process.env.FRIST_API_XIANYU_WEBHOOK_TOKEN ?? '').trim(),
    cardAutoreplenishEnabled:
      typeof options.cardAutoreplenishEnabled === 'boolean'
        ? options.cardAutoreplenishEnabled
        : process.env.FRIST_API_CARD_AUTOREPLENISH_ENABLED === '1',
    cardAutoreplenishDailyCap: Number(
      options.cardAutoreplenishDailyCap ??
        process.env.FRIST_API_CARD_AUTOREPLENISH_DAILY_CAP ??
        DEFAULT_CARD_AUTOREPLENISH_DAILY_CAP,
    ),
    cardAutoreplenishIntervalMs: Number(
      options.cardAutoreplenishIntervalMs ??
        process.env.FRIST_API_CARD_AUTOREPLENISH_INTERVAL_MS ??
        86_400_000,
    ),
    cardAutoreplenishSafetyStock: normalizeCardAutoreplenishSafetyStock(
      options.cardAutoreplenishSafetyStock ?? process.env.FRIST_API_CARD_AUTOREPLENISH_SAFETY_STOCK ?? '',
    ),
    upstreamBalanceSyncEnabled:
      typeof options.upstreamBalanceSyncEnabled === 'boolean'
        ? options.upstreamBalanceSyncEnabled
        : process.env.FRIST_API_UPSTREAM_BALANCE_SYNC_ENABLED === '1',
    upstreamBalanceSyncIntervalMs: Number(
      options.upstreamBalanceSyncIntervalMs ??
        process.env.FRIST_API_UPSTREAM_BALANCE_SYNC_INTERVAL_MS ??
        86_400_000,
    ),
    upstreamBalanceWarningCny: Number(
      options.upstreamBalanceWarningCny ?? process.env.FRIST_API_UPSTREAM_BALANCE_WARNING_CNY ?? 50,
    ),
    upstreamBalanceCriticalCny: Number(
      options.upstreamBalanceCriticalCny ?? process.env.FRIST_API_UPSTREAM_BALANCE_CRITICAL_CNY ?? 20,
    ),
    upstreamBalanceStaleHours: Number(
      options.upstreamBalanceStaleHours ?? process.env.FRIST_API_UPSTREAM_BALANCE_STALE_HOURS ?? 26,
    ),
    notifyUpstreamBalance:
      typeof options.notifyUpstreamBalance === 'function'
        ? options.notifyUpstreamBalance
        : createUpstreamBalanceNotifier(options.fetchImpl || globalThis.fetch),
    balanceAlertEmailSender:
      typeof options.balanceAlertEmailSender === 'function'
        ? options.balanceAlertEmailSender
        : createBalanceAlertEmailSender({
            host: options.smtpHost,
            port: options.smtpPort,
            secure: options.smtpSecure,
            user: options.smtpUser,
            password: options.smtpPassword,
            from: options.smtpFrom,
            fromName: options.balanceAlertFromName,
            family: options.smtpFamily,
          }),
  };
  normalized.passwordHashSecrets = [
    normalized.passwordHashSecret,
    normalized.sessionSecret,
    ...normalized.legacyPasswordHashSecrets,
  ].filter((secret, index, list) => secret && list.indexOf(secret) === index);
  normalized.accountEmailSender =
    typeof options.accountEmailSender === 'function' ? options.accountEmailSender : normalized.balanceAlertEmailSender;
  if (normalized.turnstileAllowedHostnames.size === 0 && normalized.canonicalHost) {
    normalized.turnstileAllowedHostnames.add(normalized.canonicalHost);
  }
  normalized.paymentConfig = paymentConfigFromOptions({
    ...options,
    publicGatewayBaseUrl: normalized.publicGatewayBaseUrl,
  });
  validatePublicModeOptions(normalized);
  return normalized;
}

function validatePublicModeOptions(serverOptions) {
  if (!serverOptions.publicMode) {
    return;
  }

  const problems = [];
  if (isUnsafeSecret(serverOptions.adminToken, 24)) {
    problems.push('管理员令牌必须替换成长随机值');
  }
  if (isUnsafeSecret(serverOptions.sessionSecret, 32)) {
    problems.push('会话密钥必须替换成长随机值');
  }
  if (isUnsafeSecret(serverOptions.passwordHashSecret, 32)) {
    problems.push('密码哈希密钥必须替换成长随机值');
  }
  if (serverOptions.exposeVerificationCode) {
    problems.push('公开模式禁止回显验证码');
  }
  if (serverOptions.allowDemoRecharge) {
    problems.push('公开模式禁止演示充值');
  }
  if (isUnsafeSecret(serverOptions.dataEncryptionKey, 32)) {
    problems.push('运行数据加密密钥必须替换成长随机值');
  }
  if (isUnsafeSecret(serverOptions.adminPageCode, 16)) {
    problems.push('管理页隐藏入口码必须替换成长随机值');
  }
  if (serverOptions.adminClaimCodes.some((code) => isUnsafeSecret(code, 24))) {
    problems.push('管理员身份码必须替换成长随机值');
  }
  if (serverOptions.adminTotpSecretValues.some((secret) => isUnsafeSecret(secret, 16))) {
    problems.push('管理员 TOTP 密钥必须替换为有效 Base32 随机值');
  }
  if (!serverOptions.requireEmailVerification) {
    problems.push('公开模式必须开启邮箱验证');
  }
  if (!serverOptions.requireCsrf) {
    problems.push('公开模式必须开启 CSRF 防护');
  }
  if (serverOptions.newApiEnabled && (!Number.isFinite(serverOptions.newApiDefaultTokenQuota) || serverOptions.newApiDefaultTokenQuota <= 0)) {
    problems.push('New-API 默认 Key 额度必须显式配置为正数，禁止无限额度 Key');
  }
  if (
    serverOptions.requireTurnstile &&
    (!serverOptions.turnstileSiteKey || isUnsafeSecret(serverOptions.turnstileSecret, 20))
  ) {
    problems.push('人机验证必须同时配置站点 Key 和服务端密钥');
  }
  if (
    !isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) &&
    !(serverOptions.allowInsecurePublicHttp && isPublicHttpGateway(serverOptions.publicGatewayBaseUrl))
  ) {
    problems.push('公开网关地址必须是 HTTPS 域名，或显式允许临时公网 HTTP IP');
  }
  if (serverOptions.enforceProductionReadiness) {
    if (!isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl)) {
      problems.push('生产强制模式必须使用固定 HTTPS 品牌域名');
    }
    if (!serverOptions.canonicalHost || isTemporaryHost(serverOptions.canonicalHost)) {
      problems.push('生产强制模式必须配置固定品牌域名 FRIST_API_CANONICAL_HOST');
    }
    if (!serverOptions.newApiEnabled || !serverOptions.requireNewApiDatabase || !serverOptions.newApiGatewayEnabled) {
      problems.push('生产强制模式必须启用 New-API 数据库和网关替代本地兼容链路');
    }
    if (!serverOptions.requireAdmin2fa || serverOptions.adminTotpSecrets.length === 0) {
      problems.push('生产强制模式必须启用管理员 2FA');
    }
    if (!serverOptions.requireTurnstile || !serverOptions.turnstileSiteKey || !serverOptions.turnstileSecret) {
      problems.push('生产强制模式必须启用登录/注册/兑换人机验证');
    }
    // 参考本项目 CC中转 运营 SOP（2026-07-02 复核）：当前先走生产环境内测，兑换码只用于内测验证和人工发放，自动支付商户只作为备用能力。
    const redemptionStatus = buildRedemptionBillingStatus();
    if (!redemptionStatus.ready) {
      problems.push('生产强制模式必须保留兑换码售卖与站内核销闭环');
    }
  }

  if (problems.length > 0) {
    throw new Error(`公开模式配置不安全: ${problems.join('；')}`);
  }
}

function createLowInventoryWebhookNotifier(fetchImpl) {
  const webhookUrl = process.env.FRIST_API_LOW_INVENTORY_WEBHOOK || '';
  if (!webhookUrl || typeof fetchImpl !== 'function') {
    return null;
  }

  return async (payload) => {
    try {
      await fetchImpl(webhookUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          source: 'CC中转',
          type: 'low_inventory',
          ...payload,
        }),
      });
    } catch {
      // 低库存通知不能阻断用户请求，失败会留给下一轮健康检查处理。
    }
  };
}

function createCredentialIssueNotifier(fetchImpl) {
  if (typeof fetchImpl !== 'function') {
    return null;
  }
  const telegramToken = String(process.env.FRIST_API_TELEGRAM_BOT_TOKEN || '').trim();
  const telegramChatId = String(process.env.FRIST_API_TELEGRAM_CHAT_ID || '').trim();
  const webhookUrl = String(process.env.FRIST_API_KEY_ALERT_WEBHOOK || process.env.FRIST_API_LOW_INVENTORY_WEBHOOK || '').trim();
  if (!telegramToken && !webhookUrl) {
    return null;
  }

  return async (payload) => {
    const message = [
      `[CC中转] ${payload.issueType === 'quota' ? 'Key 额度异常' : 'Key 认证异常'}`,
      `渠道: ${payload.pool || 'default'} / ${payload.providerGroup || 'Unknown'}`,
      `Key: ${payload.keyPreview || 'unknown'}`,
      `状态: ${payload.status || 'unknown'}`,
      `原因: ${payload.reason || 'unknown'}`,
      `剩余额度: ${Number(payload.quotaRemaining || 0)} / ${Number(payload.quotaTotal || 0)}`,
      `入口: ${payload.sourceHost || '-'}`,
      `时间: ${payload.at || ''}`,
      '动作: 请补号或轮换上游 Key',
    ].join('\n');
    try {
      if (telegramToken && telegramChatId) {
        await fetchImpl(`https://api.telegram.org/bot${telegramToken}/sendMessage`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            chat_id: telegramChatId,
            text: message,
            disable_web_page_preview: true,
          }),
        });
      }
      if (webhookUrl) {
        await fetchImpl(webhookUrl, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            source: 'CC中转',
            type: 'upstream_key_issue',
            message,
            payload,
          }),
        });
      }
    } catch {
      // 告警失败不阻断主流程，等待下一次巡检或请求重试。
    }
  };
}

function createUpstreamBalanceNotifier(fetchImpl) {
  if (typeof fetchImpl !== 'function') {
    return null;
  }
  const telegramToken = String(process.env.FRIST_API_TELEGRAM_BOT_TOKEN || '').trim();
  const telegramChatId = String(process.env.FRIST_API_TELEGRAM_CHAT_ID || '').trim();
  const webhookUrl = String(process.env.FRIST_API_UPSTREAM_BALANCE_WEBHOOK || process.env.FRIST_API_LOW_INVENTORY_WEBHOOK || '').trim();
  if (!telegramToken && !webhookUrl) {
    return null;
  }
  return async (balance) => {
    const message = [
      `[CC中转] 上游余额${balance.level === 'critical' ? '严重不足' : '偏低'}`,
      `剩余: ¥${Number(balance.remainingCny || 0).toFixed(2)}`,
      `提醒线: ¥${Number(balance.warningCny || 50).toFixed(2)} / 严重线: ¥${Number(balance.criticalCny || 20).toFixed(2)}`,
      `状态: ${balance.level || 'unknown'}`,
      `时间: ${balance.checkedAt || ''}`,
      balance.level === 'critical' ? '动作: 建议暂停新发货并尽快充值' : '动作: 请安排充值',
    ].join('\n');
    try {
      if (telegramToken && telegramChatId) {
        await fetchImpl(`https://api.telegram.org/bot${telegramToken}/sendMessage`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ chat_id: telegramChatId, text: message, disable_web_page_preview: true }),
        });
      }
      if (webhookUrl) {
        await fetchImpl(webhookUrl, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ source: 'CC中转', type: 'upstream_balance_low', message, payload: balance }),
        });
      }
    } catch {
      // 余额预警发送失败不能影响主链路，下一次同步会继续提醒。
    }
  };
}

function normalizeCanonicalHost(value) {
  const host = String(value || '')
    .split(',')[0]
    .trim()
    .replace(/^https?:\/\//i, '')
    .replace(/\/.*$/, '')
    .toLowerCase();
  if (/^\[[^\]]+\]/.test(host)) {
    return host.replace(/:(80|443)$/, '');
  }
  return host.replace(/:\d+$/, '');
}

function parseOptionalEnvFlag(value) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return null;
  }
  return String(value).trim() === '1';
}

function parseRedirectHosts(value) {
  const items = Array.isArray(value) ? value : String(value || '').split(',');
  return new Set(items.map(normalizeCanonicalHost).filter(Boolean));
}

async function assertSafeUpstreamBaseUrl(value, serverOptions) {
  if (serverOptions.allowPrivateUpstreamUrls) {
    return;
  }
  const parsed = parseUpstreamUrl(value);
  if (isPrivateHostname(parsed.hostname) || isPrivateIpLiteral(parsed.hostname)) {
    throw publicError(400, '请求地址不能指向内网或本机地址');
  }
  const records = await resolveUpstreamAddresses(parsed.hostname, serverOptions);
  if (!records.length || records.some((record) => isPrivateIpLiteral(record.address))) {
    throw publicError(400, '请求地址不能解析到内网或本机地址');
  }
}

function parseUpstreamUrl(value) {
  let parsed;
  try {
    parsed = new URL(normalizeBaseUrl(value));
  } catch {
    throw publicError(400, '请求地址格式不正确');
  }
  if (!['https:', 'http:'].includes(parsed.protocol)) {
    throw publicError(400, '请求地址只支持 HTTP 或 HTTPS');
  }
  if (!parsed.hostname) {
    throw publicError(400, '请求地址缺少域名');
  }
  return parsed;
}

async function resolveUpstreamAddresses(hostname, serverOptions) {
  if (typeof serverOptions.resolveUpstreamAddresses === 'function') {
    return serverOptions.resolveUpstreamAddresses(hostname);
  }
  const literalFamily = isIP(hostname);
  if (literalFamily) {
    return [{ address: hostname, family: literalFamily }];
  }
  return lookupDns(hostname, { all: true, verbatim: true });
}

function isPrivateHostname(hostname) {
  const host = String(hostname || '').toLowerCase();
  return host === 'localhost' || host.endsWith('.localhost');
}

function isPrivateIpLiteral(value) {
  const ip = String(value || '').replace(/^\[|\]$/g, '').toLowerCase();
  if (!isIP(ip)) return false;
  if (ip === '::1' || ip === '0:0:0:0:0:0:0:1') return true;
  if (/^(fc|fd|fe80):/i.test(ip)) return true;
  if (ip.startsWith('::ffff:')) {
    return isPrivateIpLiteral(ip.slice('::ffff:'.length));
  }
  const parts = ip.split('.').map((item) => Number(item));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  const [first, second] = parts;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

function redirectToCanonicalHost({ request, response, url, serverOptions }) {
  if (!serverOptions.canonicalHost || !serverOptions.redirectHosts?.size) {
    return false;
  }
  const requestHost = normalizeCanonicalHost(request.headers['x-forwarded-host'] || request.headers.host || '');
  if (!requestHost || !serverOptions.redirectHosts.has(requestHost)) {
    return false;
  }
  url.host = serverOptions.canonicalHost;
  response.writeHead(301, {
    location: url.toString(),
    'cache-control': 'no-store',
  });
  response.end();
  return true;
}

function isUnsafeSecret(value, minLength) {
  const secret = String(value || '');
  if (secret.length < minLength) {
    return true;
  }
  return /frist-api-dev|replace|change-before|default|example|password/i.test(secret);
}

function isPublicHttpsGateway(value) {
  const gateway = String(value || '').trim();
  if (!/^https:\/\//i.test(gateway)) {
    return false;
  }
  return !/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|example\.(com|org|net))/i.test(gateway);
}

function isPublicHttpGateway(value) {
  const gateway = String(value || '').trim();
  if (!/^http:\/\//i.test(gateway)) {
    return false;
  }
  return !/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|example\.(com|org|net))/i.test(gateway);
}

function isTemporaryHost(value) {
  const host = normalizeCanonicalHost(value);
  return !host || /\.nip\.io$/i.test(host) || /\.sslip\.io$/i.test(host) || /^\d{1,3}(\.\d{1,3}){3}$/.test(host);
}

function requireAdmin(data, request, serverOptions, options = {}) {
  const token = request.headers['x-admin-token'];
  if (token && token === serverOptions.adminToken) {
    requireAdminSecondFactorIfEnabled(data, request, serverOptions, options);
    return;
  }
  const { user } = findSession(data, request);
  if (user?.isAdmin) {
    requireAdminSecondFactorIfEnabled(data, request, serverOptions, options);
    return;
  }
  throw publicError(401, '管理员身份无效');
}

function requireXianyuWebhook(request, serverOptions) {
  const expected = String(serverOptions.xianyuWebhookToken || '').trim();
  if (!expected) {
    throw publicError(503, '闲鱼自动发货 webhook 未配置');
  }
  const bearer = String(request.headers.authorization || '').match(/^Bearer\s+(.+)$/i)?.[1] || '';
  const actual = String(headerValue(request, 'x-cc-xianyu-token') || bearer || '').trim();
  if (!actual || !safeEqual(expected, actual)) {
    throw publicError(401, '闲鱼自动发货 token 无效');
  }
}

function requireAdminSecondFactorIfEnabled(data, request, serverOptions, options = {}) {
  if (!serverOptions.requireAdmin2fa || options.allowPendingSecondFactor) {
    return;
  }
  pruneAdminSecondFactorSessions(data, serverOptions);
  const token = parseCookies(request.headers.cookie || '')[ADMIN_2FA_COOKIE] || headerValue(request, 'x-admin-2fa-session');
  const session = token ? data.adminSecondFactorSessions?.[runtimeTokenKey(token)] : null;
  const expiresAt = Date.parse(session?.expiresAt || '');
  if (!session || !Number.isFinite(expiresAt) || expiresAt <= currentDate(serverOptions).getTime()) {
    throw publicError(401, '需要管理员 2FA 验证');
  }
}

function pruneAdminSecondFactorSessions(data, serverOptions) {
  const now = currentDate(serverOptions).getTime();
  data.adminSecondFactorSessions = Object.fromEntries(
    Object.entries(data.adminSecondFactorSessions || {}).filter(([, session]) => {
      const expiresAt = Date.parse(session?.expiresAt || '');
      return Number.isFinite(expiresAt) && expiresAt > now;
    }),
  );
}

function normalizeReplenishmentKeys(keys) {
  if (typeof keys === 'string') {
    return keys
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((value) => ({
        value,
        quotaRemaining: 1000,
        quotaTotal: 1000,
        latencyMs: 0,
        latencyProvided: false,
        authHeaderName: 'authorization',
        authHeaderValuePrefix: 'Bearer',
        extraHeaders: {},
        modelGroup: 'All',
        cardType: '',
        expiresAt: '',
      }));
  }
  if (!Array.isArray(keys)) {
    throw publicError(400, 'Key 列表不能为空');
  }
  return keys
    .map((item) => (typeof item === 'string' ? { value: item } : item))
    .map((item) => ({
      value: String(item.value || item.key || item.apiKey || item.api_key || item.token || '').trim(),
      quotaRemaining: Number(item.quotaRemaining ?? 1000),
      quotaTotal: Number(item.quotaTotal ?? item.quotaRemaining ?? 1000),
      latencyMs: Number(item.latencyMs ?? 0),
      latencyProvided: item.latencyMs !== undefined,
      // 余额站阈值随 Key 入库，避免只靠人工改 runtime 才能启用日消费熔断。
      dailySpendLimitCents: Number(item.dailySpendLimitCents ?? item.dailySpendLimit ?? 0),
      slowLatencyThresholdMs: Number(item.slowLatencyThresholdMs ?? 0),
      costSensitive: Boolean(item.costSensitive),
      authHeaderName: String(item.authHeaderName || 'authorization').trim().toLowerCase(),
      authHeaderValuePrefix:
        item.authHeaderValuePrefix === ''
          ? ''
          : String(item.authHeaderValuePrefix || 'Bearer').trim(),
      extraHeaders: sanitizeExtraHeaders(item.extraHeaders),
      modelGroup: item.modelGroup ? normalizeModelGroup(item.modelGroup) : '',
      cardType: normalizePool(item.cardType || ''),
      expiresAt: String(item.expiresAt || ''),
    }))
    .filter((item) => item.value);
}

function resolveProbeLatencyMs(key, probe = {}) {
  if (key.latencyProvided && Number.isFinite(key.latencyMs) && key.latencyMs > 0) {
    return key.latencyMs;
  }
  const latency = Number(probe.latencyMs || 0);
  return Number.isFinite(latency) && latency > 0 ? latency : 0;
}




function normalizePlusAccountStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (PLUS_ACCOUNT_STATUSES.has(status)) return status;
  return 'warming';
}

function normalizePlusAccountComplianceStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (PLUS_ACCOUNT_COMPLIANCE_STATUSES.has(status)) return status;
  return 'needs_review';
}

function normalizePlusAccountRegion(value) {
  const text = String(value || '').trim();
  if (text.toLowerCase() === 'turkey' || text.toLowerCase() === 'turkiye' || text === '土耳其') {
    return 'Türkiye';
  }
  if (PLUS_ACCOUNT_REGIONS.has(text)) return text;
  return 'Other';
}

function normalizeRtAccountStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (RT_ACCOUNT_STATUSES.has(status)) return status;
  return 'ready_for_refresh';
}

function normalizeRtPlatform(value) {
  const platform = String(value || '').trim().toLowerCase();
  if (platform === 'chatgpt') return 'openai';
  if (RT_ACCOUNT_PLATFORMS.has(platform)) return platform;
  return 'codex';
}


function upsertSupplierProfile(data, profile) {
  let source = data.supplierProfiles.find((item) => item.id === profile.id);
  if (!source) {
    source = {
      id: profile.id,
      baseUrl: profile.baseUrl,
      proxyBaseUrl: profile.proxyBaseUrl || '',
      routeBaseUrl: profile.routeBaseUrl || profile.baseUrl,
      pool: profile.pool,
      modelGroup: profile.modelGroup || 'All',
      cardType: profile.cardType || profile.pool,
      expiresAt: profile.expiresAt || '',
      sourceType: profile.sourceType || PRIMARY_SOURCE_TYPE,
      riskStatus: profile.riskStatus || 'approved',
      backupRiskAccepted: Boolean(profile.backupRiskAccepted),
      riskNote: sanitizeRiskNote(profile.riskNote || ''),
      models: profile.models,
      connectionPath: profile.connectionPath || 'direct',
      createdAt: profile.updatedAt,
      updatedAt: profile.updatedAt,
    };
    data.supplierProfiles.push(source);
    return source;
  }
  source.pool = profile.pool;
  source.modelGroup = profile.modelGroup || source.modelGroup || 'All';
  source.cardType = profile.cardType || source.cardType || profile.pool;
  source.expiresAt = profile.expiresAt || source.expiresAt || '';
  source.sourceType = profile.sourceType || source.sourceType || PRIMARY_SOURCE_TYPE;
  source.riskStatus = profile.riskStatus || source.riskStatus || 'approved';
  source.backupRiskAccepted = Boolean(profile.backupRiskAccepted);
  source.riskNote = sanitizeRiskNote(profile.riskNote || source.riskNote || '');
  source.proxyBaseUrl = profile.proxyBaseUrl || '';
  source.routeBaseUrl = profile.routeBaseUrl || profile.baseUrl;
  source.models = profile.models;
  source.connectionPath = profile.connectionPath || source.connectionPath || 'direct';
  source.updatedAt = profile.updatedAt;
  return source;
}

function upsertCredential(data, nextCredential) {
  let credential = data.credentials.find(
    (item) =>
      item.sourceId === nextCredential.sourceId &&
      normalizeModelGroup(item.modelGroup) === normalizeModelGroup(nextCredential.modelGroup) &&
      item.rawKey === nextCredential.rawKey,
  );
  if (!credential) {
    credential = {
      id: createId('cred'),
      createdAt: nextCredential.createdAt,
    };
    data.credentials.push(credential);
  }

  Object.assign(credential, {
    ...nextCredential,
    id: credential.id,
    createdAt: credential.createdAt || nextCredential.createdAt,
  });
  return credential;
}

async function serveStaticFile({ request, response, url, publicDir, serverOptions, store }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    writeJson(response, 405, { error: '请求方法不支持' });
    return;
  }

  const pathname = decodeURIComponent(url.pathname);
  const adminGateHeaders = await validateAdminPageGate({ request, url, pathname, serverOptions, store });
  if (adminGateHeaders === false) {
    writeJson(response, 404, { error: '文件不存在' });
    return;
  }
  const candidate = pathname === '/' ? '/index.html' : pathname;
  const safeCandidate = normalize(candidate).replace(/^[/\\]+/, '').replace(/^(\.\.(\/|\\|$))+/, '');
  const filePath = resolve(publicDir, safeCandidate);
  if (relative(publicDir, filePath).startsWith('..')) {
    writeJson(response, 403, { error: '路径不可访问' });
    return;
  }

  let finalPath = filePath;
  try {
    const info = await stat(finalPath);
    if (info.isDirectory()) {
      finalPath = join(finalPath, 'index.html');
    }
    const content = await readFile(finalPath);
    response.writeHead(200, {
      'content-type': CONTENT_TYPES.get(extname(finalPath)) || 'application/octet-stream',
      'cache-control': 'no-store',
      ...(adminGateHeaders || {}),
    });
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    response.end(content);
  } catch (error) {
    if (error.code === 'ENOENT') {
      writeJson(response, 404, { error: '文件不存在' });
      return;
    }
    throw error;
  }
}

async function validateAdminPageGate({ request, url, pathname, serverOptions, store }) {
  if (pathname !== '/admin.html' || !serverOptions.adminPageCode) {
    return {};
  }
  const cookies = parseCookies(request.headers.cookie || '');
  const code = url.searchParams.get('code') || '';
  if (cookies.frist_admin_gate === hashId(serverOptions.adminPageCode)) {
    return {};
  }
  if (code !== serverOptions.adminPageCode) {
    if (store) {
      const data = await store.load();
      const { user } = findSession(data, request);
      if (user?.isAdmin) {
        return {};
      }
    }
    return false;
  }
  return adminGateCookie(serverOptions);
}

function adminGateCookie(serverOptions) {
  if (!serverOptions.adminPageCode) {
    return {};
  }
  return {
    'set-cookie': [
      `frist_admin_gate=${hashId(serverOptions.adminPageCode)}`,
      'Path=/',
      'HttpOnly',
      'SameSite=Lax',
      serverOptions.publicMode && isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) ? 'Secure' : '',
    ].filter(Boolean).join('; '),
  };
}

function adminSecondFactorCookie(sessionToken, request, serverOptions) {
  if (!sessionToken) {
    return '';
  }
  return [
    `${ADMIN_2FA_COOKIE}=${sessionToken}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    shouldUseSecureCookie(request, serverOptions) ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}





function normalizePublicError(error) {
  if (error?.expose) {
    return error;
  }
  return publicError(500, String(error?.message || '服务暂时不可用'));
}

function requestOrigin(request) {
  const forwardedProtocol = firstHeaderToken(request.headers['x-forwarded-proto']);
  const protocol = forwardedProtocol.toLowerCase().replace(/:$/, '') === 'https' ? 'https' : 'http';
  const forwardedHost = firstHeaderToken(request.headers['x-forwarded-host']);
  const hostHeader = firstHeaderToken(request.headers.host);
  const host = normalizeOriginHost(forwardedHost || hostHeader) || '127.0.0.1';
  const origin = `${protocol}://${host}`;
  try {
    new URL(origin);
    return origin;
  } catch {
    return 'http://127.0.0.1';
  }
}

function firstHeaderToken(value) {
  const raw = Array.isArray(value) ? value[0] : String(value || '');
  return raw.split(',')[0].trim();
}

function normalizeOriginHost(value) {
  const raw = String(value || '').trim();
  if (!raw) {
    return '';
  }
  return raw.replace(/^https?:\/\//i, '').split('/')[0].trim();
}








function sumUserGatewayCost(data, userId, periodPrefix = '') {
  return data.events
    .filter((item) => item.type === 'gateway_routed' && item.userId === userId)
    .filter((item) => !periodPrefix || String(item.at || '').startsWith(periodPrefix))
    .reduce((sum, item) => sum + Number(item.quotaCost || 0), 0);
}






function customerImportModelSelection(data, user, key, requestedModel = '') {
  expireUserPlanIfNeeded(data, user, {});
  const allowedPools = allowedPoolsForUser(user);
  const liveModels = data.credentials
    .filter((credential) => allowedPools.includes(credential.pool))
    .filter((credential) => credential.enabled)
    .filter((credential) => credential.status === 'healthy')
    .filter(isCredentialRouteApproved)
    .filter((credential) => Number(credential.quotaRemaining || 0) > 0)
    .filter((credential) => credentialMatchesModelGroup(credential, '', key.modelGroup))
    .flatMap((credential) => credential.models || [])
    .filter((model) => modelMatchesGroup(model, key.modelGroup || 'All'));
  const requested = normalizeOfficialModelName(requestedModel);
  const liveSet = new Set(normalizeClientAvailableModels(liveModels, { modelGroup: key.modelGroup }));
  const safeRequested = requested && liveSet.has(requested) ? requested : '';
  const primaryModels = normalizeClientAvailableModels(uniqueStrings([...liveSet, safeRequested]), {
    model: safeRequested,
    modelGroup: key.modelGroup,
  });

  if (primaryModels.length) {
    return {
      availableModels: primaryModels,
      defaultModel: safeRequested || strongestModel(primaryModels),
    };
  }

  throw publicError(409, '暂无健康上游模型，请先补充或修复可用渠道后再导入客户端');
}




function buildUsageRecords(data, user) {
  const keyById = new Map(
    data.userKeys
      .filter((key) => key.userId === user.id)
      .map((key) => [key.id, key]),
  );
  return data.events
    .filter((event) => event.type === 'gateway_routed' && event.userId === user.id)
    .slice(-80)
    .reverse()
    .map((event) => {
      const key = keyById.get(event.keyId);
      return {
        id: `${event.at || ''}-${event.keyId || ''}-${event.model || ''}`,
        apiKey: event.apiKeyPreview || key?.preview || 'sk-******',
        model: normalizeOfficialModelName(event.model || 'unknown'),
        inferenceEffort: event.inferenceEffort || '默认',
        endpoint: event.endpoint || '-',
        type: event.requestType || '文本',
        billingMode: event.billingMode || '余额',
        client: event.client || clientLabelFromEvent(event),
        tokens: compactTokenText(event.totalTokens || 0),
        amount: formatUsdFromCnyCents(event.quotaCost || 0),
        amountCny: formatCny(event.quotaCost || 0),
        latency: event.latencyMs ? `${Math.round(Number(event.latencyMs || 0))}ms` : '-',
        status: event.status || 'success',
        at: event.at || '',
      };
    });
}

function buildUsageAnomalies(data, user) {
  const routedEvents = data.events.filter((item) => item.type === 'gateway_routed' && item.userId === user.id);
  if (routedEvents.length === 0) {
    return [];
  }
  const now = currentDate();
  const today = now.toISOString().slice(0, 10);
  const currentMonth = now.toISOString().slice(0, 7);
  const todayEvents = routedEvents.filter((item) => String(item.at || '').startsWith(today));
  const monthEvents = routedEvents.filter((item) => String(item.at || '').startsWith(currentMonth));
  const todayCost = sumEventField(todayEvents, 'quotaCost');
  const monthCost = sumEventField(monthEvents, 'quotaCost');
  const largestEvent = [...todayEvents].sort((left, right) => Number(right.quotaCost || 0) - Number(left.quotaCost || 0))[0];
  const rows = [];
  const remaining = availableQuotaCents(user);

  if (todayCost > 0 && remaining > 0 && todayCost >= remaining * 0.5) {
    rows.push({
      id: 'today-spend-balance-ratio',
      severity: todayCost >= remaining ? 'critical' : 'warning',
      title: '今日消耗偏高',
      detail: `今日已用 ${formatUsdFromCnyCents(todayCost)}，接近当前剩余额度 ${formatUsdFromCnyCents(remaining)}。`,
      action: '建议检查记录页和 Key 使用方',
      at: largestEvent?.at || now.toISOString(),
    });
  }

  if (largestEvent && Number(largestEvent.quotaCost || 0) >= Math.max(50, monthCost * 0.6)) {
    rows.push({
      id: 'single-call-cost-spike',
      severity: Number(largestEvent.quotaCost || 0) >= Math.max(200, monthCost * 0.8) ? 'critical' : 'warning',
      title: '单次调用费用突增',
      detail: `${largestEvent.model || '模型'} 单次消耗 ${formatUsdFromCnyCents(largestEvent.quotaCost)}。`,
      action: '建议核对上下文长度、图片请求和调用客户端',
      at: largestEvent.at || now.toISOString(),
    });
  }

  const slowEvents = todayEvents.filter((item) => Number(item.latencyMs || 0) >= 5000);
  if (slowEvents.length >= 2) {
    rows.push({
      id: 'latency-spike',
      severity: 'warning',
      title: '延迟异常',
      detail: `今日 ${slowEvents.length} 次请求超过 5 秒。`,
      action: '建议查看通道页是否有降级渠道',
      at: slowEvents.at(-1)?.at || now.toISOString(),
    });
  }

  return rows.slice(0, 4);
}

function sumEventField(events, field) {
  return events.reduce((sum, item) => sum + Number(item[field] || 0), 0);
}

function buildRecentLogs(data, user) {
  const allowedTypes = new Set([
    'gateway_routed',
    'redeemed',
    'payment_order_created',
    'manual_recharged',
    'recharged',
    'balance_alert_sent',
    'key_created',
    'key_enabled',
    'key_disabled',
    'profile_updated',
  ]);
  return data.events
    .filter((event) => event.userId === user.id && allowedTypes.has(event.type))
    .slice(-5)
    .reverse()
    .map((event) => ({
      type: event.type || 'event',
      at: event.at || '',
      detail: userEventDetail(event),
    }));
}

function userEventDetail(event) {
  if (event.type === 'gateway_routed') {
    return `${event.model || '模型'} · ${formatUsdFromCnyCents(event.quotaCost)} · ${clientLabelFromEvent(event)}`;
  }
  if (event.type === 'redeemed') return `兑换到账 ${event.credit ? event.credit : ''}`.trim();
  if (event.type === 'payment_order_created') return `充值单 ${formatUsdFromCnyCents(event.creditCents || event.amountCents)}`;
  if (event.type === 'manual_recharged' || event.type === 'recharged') return `余额到账 ${formatUsdFromCnyCents(event.creditCents || event.amountCents)}`;
  if (event.type === 'balance_alert_sent') return '余额预警已发送';
  if (event.type === 'key_created') return '新 Key 已创建';
  if (event.type === 'key_enabled') return 'Key 已开启';
  if (event.type === 'key_disabled') return 'Key 已暂停';
  if (event.type === 'profile_updated') return event.emailChanged ? '资料已更新，邮箱待验证' : '资料已更新';
  return '系统事件';
}

function clientLabelFromEvent(event) {
  return event.client || clientLabelFromSessionId(event.sessionId || event.fristSessionId || event.metadata?.frist_session_id) || 'API';
}

function clientLabelFromRequest(request, body = {}) {
  const explicit = headerValue(request, 'x-frist-client') || body.metadata?.frist_client || body.metadata?.client;
  const normalizedExplicit = normalizeClientLabel(explicit);
  if (normalizedExplicit) return normalizedExplicit;
  const sessionLabel = clientLabelFromSessionId(body.metadata?.frist_session_id);
  if (sessionLabel) return sessionLabel;
  const userAgent = headerValue(request, 'user-agent').toLowerCase();
  if (/macintosh|mac os|darwin/.test(userAgent)) return 'MacBook';
  if (/windows|win64|win32/.test(userAgent)) return 'PC';
  if (/iphone|android|mobile/.test(userAgent)) return '移动端';
  return 'API';
}

function clientLabelFromSessionId(value) {
  const text = String(value || '').toLowerCase();
  if (!text) return '';
  if (text.includes('playground') || text.includes('connectivity') || text.includes('square')) return '广场';
  if (text.includes('mac') || text.includes('darwin')) return 'MacBook';
  if (text.includes('pc') || text.includes('windows')) return 'PC';
  if (text.includes('codex')) return 'Codex';
  if (text.includes('claude')) return 'Claude';
  return '';
}

function normalizeClientLabel(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return '';
  if (['square', 'playground', 'web'].includes(text)) return '广场';
  if (['mac', 'macbook', 'darwin'].includes(text)) return 'MacBook';
  if (['pc', 'windows'].includes(text)) return 'PC';
  if (text.includes('codex')) return 'Codex';
  if (text.includes('claude')) return 'Claude';
  return String(value || '').trim().slice(0, 24);
}

function buildChannelChecks(data, serverOptions = {}) {
  const grouped = new Map();
  for (const credential of data.credentials) {
    const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
    const source = data.supplierProfiles.find((item) => item.id === credential.sourceId) || {};
    const pool = normalizePool(credential.pool || source.pool || 'default') || 'default';
    const provider = effectiveCredentialGroup(credential);
    const key = `${pool}:${credential.sourceId || provider}`;
    const current = grouped.get(key) || {
      model: models[0] || DEFAULT_MODEL,
      provider,
      channel: '',
      pool,
      poolLabel: poolTypeLabel(pool),
      total: 0,
      healthy: 0,
      down: 0,
      slow: 0,
      latencyMs: 0,
      latencyTotal: 0,
      latencySamples: 0,
      checkedAt: '',
      status: credential.status,
      endpoint: '/v1',
      history: [],
      models: new Set(),
    };
    for (const model of models) {
      current.models.add(normalizeOfficialModelName(model));
    }
    const isHealthy = credential.enabled && credential.status === 'healthy' && isCredentialRouteApproved(credential);
    const latency = Number(credential.latencyMs || 0);
    const hasRealLatency = isHealthy && Number.isFinite(latency) && latency > 0 && latency < 999999;
    const bucket = isHealthy ? (hasRealLatency && latency > 1600 ? 'slow' : 'ok') : 'down';
    current.total += 1;
    current.healthy += isHealthy ? 1 : 0;
    current.down += isHealthy ? 0 : 1;
    current.slow += bucket === 'slow' ? 1 : 0;
    if (isHealthy) {
      if (hasRealLatency) {
        current.latencyMs = current.latencyMs ? Math.min(current.latencyMs, latency) : latency;
        current.latencyTotal += latency;
        current.latencySamples += 1;
      }
      current.status = 'healthy';
    } else if (!current.healthy) {
      current.status = credential.status || current.status || 'failed';
    }
    current.checkedAt = [current.checkedAt, credential.updatedAt].filter(Boolean).sort().at(-1) || '';
    current.endpoint = '/v1';
    current.history.push(bucket);
    grouped.set(key, current);
  }

  return [...grouped.values()]
    .sort((left, right) => poolPriority(left.pool) - poolPriority(right.pool) || left.channel.localeCompare(right.channel))
    .map((item, index) => {
      const channel = publicPoolChannelLabel(index + 1);
      const availabilityPercent = item.total ? Math.round((item.healthy / item.total) * 1000) / 10 : 0;
      const averageLatencyMs = item.latencySamples ? Math.round(item.latencyTotal / item.latencySamples) : 0;
      const monitorStatus =
        item.healthy === 0
          ? '异常'
          : item.down > 0 || item.slow > 0
            ? '降级'
            : '正常';
      const status = item.healthy > 0 ? (item.slow > 0 ? 'slow' : 'healthy') : item.status;
      const primaryModel = normalizeOfficialModelName([...item.models][0] || item.model);
      return {
        model: primaryModel,
        provider: item.provider,
        channel,
        pool: item.pool,
        poolLabel: item.poolLabel,
        endpoint: item.endpoint || '/v1',
        ok: item.healthy > 0,
        status,
        latencyMs: item.latencySamples ? item.latencyMs : 0,
        averageLatencyMs,
        checkedAt: item.checkedAt,
        availability: `${availabilityPercent}%`,
        availability7d: availabilityPercent,
        availability_7d: availabilityPercent,
        availability15d: availabilityPercent,
        availability30d: availabilityPercent,
        availability_15d: availabilityPercent,
        availability_30d: availabilityPercent,
        availabilityWindow: '当前库存快照',
        healthyCount: item.healthy,
        totalCount: item.total,
        downCount: item.down,
        slowCount: item.slow,
        successLabel: `${item.healthy}/${item.total} 可用`,
        latencyLabel: item.latencySamples ? `最低 ${item.latencyMs}ms / 平均 ${averageLatencyMs}ms` : '等待真实请求更新',
        monitorIntervalSeconds: 60,
        monitorStatus,
        officialStatus: monitorStatus,
        history: item.history.slice(-60),
        sla: buildChannelSlaSummary(data, primaryModel, {
          availabilityPercent,
          history: item.history,
          checkedAt: item.checkedAt,
          now: currentDate(serverOptions).getTime(),
        }),
      };
    });
}

function publicPoolChannelLabel(index) {
  const safeIndex = Math.max(1, Number(index || 1));
  return `卡商${safeIndex}`;
}

function poolTypeLabel(pool) {
  const normalized = normalizePool(pool || 'default') || 'default';
  const labels = {
    hour: '小时卡号池',
    day: '日卡号池',
    month: '月卡号池',
    unlimited: '不限时号池',
    default: '默认号池',
  };
  return labels[normalized] || '号池渠道';
}

function recordChannelProbeEvent(data, credential, status, reason, serverOptions, extra = {}) {
  if (!credential) {
    return;
  }
  const now = currentDate(serverOptions).toISOString();
  const models = normalizeOfficialModelList(credential.models?.length ? credential.models : [DEFAULT_MODEL]);
  const bucket = status === 'ok' || status === 'slow'
    ? status
    : status === 'exhausted'
      ? 'down'
      : 'down';
  for (const model of models) {
    data.channelProbeEvents.push({
      id: createId('sla'),
      model,
      provider: providerFromModel(model),
      credentialId: credential.id,
      status: bucket,
      reason: String(reason || '').slice(0, 120),
      latencyMs: Math.max(0, Number(extra.latencyMs ?? credential.latencyMs ?? 0) || 0),
      pool: credential.pool || '',
      at: now,
    });
  }
  pruneChannelProbeEvents(data, serverOptions);
}

function pruneChannelProbeEvents(data, serverOptions) {
  const retentionDays = Number(serverOptions.slaRetentionDays || DEFAULT_SLA_RETENTION_DAYS);
  const cutoff = currentDate(serverOptions).getTime() - Math.max(1, retentionDays) * 86_400_000;
  data.channelProbeEvents = (data.channelProbeEvents || [])
    .filter((event) => {
      const time = Date.parse(event.at || '');
      return Number.isFinite(time) && time >= cutoff;
    })
    .slice(-20_000);
}

function buildChannelSlaSummary(data, model, fallback = {}) {
  const normalizedModel = normalizeOfficialModelName(model);
  const events = (data.channelProbeEvents || [])
    .filter((event) => normalizeOfficialModelName(event.model) === normalizedModel)
    .sort((left, right) => String(left.at || '').localeCompare(String(right.at || '')));
  if (!events.length) {
    return {
      window: '当前库存快照',
      availability7d: fallback.availabilityPercent || 0,
      availability15d: fallback.availabilityPercent || 0,
      availability30d: fallback.availabilityPercent || 0,
      samples7d: 0,
      samples15d: 0,
      samples30d: 0,
      lastIncidentAt: '',
      lastIncidentReason: '',
      history: (fallback.history || []).slice(-60),
      checkedAt: fallback.checkedAt || '',
    };
  }
  const now = Number(fallback.now || Date.now());
  const summary7d = summarizeSlaWindow(events, now - 7 * 86_400_000);
  const summary15d = summarizeSlaWindow(events, now - 15 * 86_400_000);
  const summary30d = summarizeSlaWindow(events, now - 30 * 86_400_000);
  const incidents = events.filter((event) => event.status === 'down');
  const lastIncident = incidents.at(-1);
  return {
    window: '真实探测事件',
    availability7d: summary7d.availability,
    availability15d: summary15d.availability,
    availability30d: summary30d.availability,
    samples7d: summary7d.samples,
    samples15d: summary15d.samples,
    samples30d: summary30d.samples,
    lastIncidentAt: lastIncident?.at || '',
    lastIncidentReason: lastIncident?.reason || '',
    history: events.slice(-60).map((event) => event.status),
    checkedAt: events.at(-1)?.at || '',
  };
}

function summarizeSlaWindow(events, cutoffMs) {
  const windowEvents = events.filter((event) => Date.parse(event.at || '') >= cutoffMs);
  const samples = windowEvents.length;
  if (!samples) {
    return { availability: 0, samples: 0 };
  }
  const healthy = windowEvents.filter((event) => event.status === 'ok' || event.status === 'slow').length;
  return {
    availability: Math.round((healthy / samples) * 1000) / 10,
    samples,
  };
}


async function buildProductionReadiness(data, serverOptions) {
  const backup = buildBackupReadiness(data, serverOptions);
  const payment = buildPaymentClosureStatus(serverOptions);
  const redemptionBilling = buildRedemptionBillingStatus();
  const turnstile = buildTurnstileReadiness(serverOptions);
  const upstreamInventory = buildHealthyUpstreamInventoryReadiness(data, serverOptions);
  const checks = [
    {
      id: 'brand_domain',
      label: '固定品牌域名',
      ok: isPublicHttpsGateway(serverOptions.publicGatewayBaseUrl) && !isTemporaryHost(serverOptions.canonicalHost),
      detail: serverOptions.canonicalHost || '未配置',
    },
    {
      id: 'database',
      label: '数据库替代 JSON runtime',
      ok: Boolean(serverOptions.newApiEnabled && serverOptions.requireNewApiDatabase),
      detail: serverOptions.newApiEnabled ? 'New-API 桥接已启用' : '仍在 JSON runtime 模式',
    },
    {
      id: 'healthy_upstream_inventory',
      label: '健康上游库存',
      ok: upstreamInventory.ready,
      detail: upstreamInventory.message,
    },
    {
      id: 'backup_monitoring',
      label: '备份监控',
      ok: backup.ready,
      detail: backup.message,
    },
    {
      id: 'admin_2fa',
      label: '管理员 2FA',
      ok: Boolean(serverOptions.requireAdmin2fa && serverOptions.adminTotpSecrets.length > 0),
      detail: serverOptions.requireAdmin2fa ? '已要求 TOTP 二次验证' : '未启用',
    },
    {
      id: 'turnstile',
      label: '登录/注册/兑换人机验证',
      ok: turnstile.ready,
      detail: turnstile.message,
    },
    {
      id: 'redemption_billing',
      label: '兑换码收款闭环',
      ok: redemptionBilling.ready,
      detail: redemptionBilling.detail,
    },
    {
      id: 'channel_sla',
      label: '长期渠道 SLA 记录',
      ok: (data.channelProbeEvents || []).length > 0,
      detail: `${(data.channelProbeEvents || []).length} 条探测事件`,
    },
  ];
  return {
    enforceProductionReadiness: Boolean(serverOptions.enforceProductionReadiness),
    ready: checks.every((check) => check.ok),
    checks,
    payment,
    redemptionBilling,
    turnstile,
    backup,
    upstreamInventory,
    sla: {
      retentionDays: Number(serverOptions.slaRetentionDays || DEFAULT_SLA_RETENTION_DAYS),
      eventCount: (data.channelProbeEvents || []).length,
      models: uniqueStrings((data.channelProbeEvents || []).map((event) => event.model)).length,
    },
  };
}

function buildHealthyUpstreamInventoryReadiness(data, serverOptions) {
  const localHealthyCredentials = (data.credentials || []).filter(
    (credential) =>
      credential.enabled &&
      credential.status === 'healthy' &&
      isCredentialRouteApproved(credential) &&
      Number(credential.quotaRemaining || 0) > 0 &&
      (credential.models || []).length > 0,
  );
  const newApi = readNewApiInventoryCounts(serverOptions);
  const ready = localHealthyCredentials.length > 0 || newApi.enabledChannelsWithModels > 0;
  const modelCount = uniqueStrings(localHealthyCredentials.flatMap((credential) => credential.models || [])).length + newApi.enabledModels;
  return {
    ready,
    localHealthyCredentials: localHealthyCredentials.length,
    localHealthyModels: uniqueStrings(localHealthyCredentials.flatMap((credential) => credential.models || [])).length,
    newApiEnabledChannels: newApi.enabledChannelsWithModels,
    newApiModels: newApi.enabledModels,
    sqliteDbConfigured: Boolean(String(serverOptions.newApiSqliteDb || '').trim()),
    sqliteDbReadable: newApi.readable,
    message: ready
      ? `本地健康库存 ${localHealthyCredentials.length} 条，New-API 可用渠道 ${newApi.enabledChannelsWithModels} 个，模型 ${modelCount} 个`
      : `暂无健康上游库存：本地 ${localHealthyCredentials.length} 条，New-API 可用渠道 ${newApi.enabledChannelsWithModels} 个 / 模型 ${newApi.enabledModels} 个`,
    ...(newApi.error ? { error: newApi.error } : {}),
  };
}

function readNewApiInventoryCounts(serverOptions) {
  if (!serverOptions.newApiEnabled) {
    return { readable: false, enabledChannelsWithModels: 0, enabledModels: 0 };
  }
  const sqliteDb = String(serverOptions.newApiSqliteDb || '').trim();
  if (!sqliteDb) {
    return { readable: false, enabledChannelsWithModels: 0, enabledModels: 0, error: 'missing_sqlite_db' };
  }
  const sql = [
    "select 'channels', count(*) from channels where coalesce(status, 1) = 1 and trim(coalesce(models, '')) <> '';",
    "select 'models', count(*) from models where coalesce(status, 1) = 1;",
  ].join('\n');
  const result = spawnSync('sqlite3', [sqliteDb], {
    input: `${sql}\n`,
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  });
  if (result.status !== 0) {
    return {
      readable: false,
      enabledChannelsWithModels: 0,
      enabledModels: 0,
      error: String(result.stderr || result.stdout || 'sqlite3_failed').split('\n')[0].slice(0, 120),
    };
  }
  const counts = Object.fromEntries(
    String(result.stdout || '')
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => {
        const [name, count] = line.split('|');
        return [name, Number(count || 0)];
      }),
  );
  return {
    readable: true,
    enabledChannelsWithModels: Number(counts.channels || 0),
    enabledModels: Number(counts.models || 0),
  };
}

function buildTurnstileReadiness(serverOptions) {
  const allowedHostnames = [...(serverOptions.turnstileAllowedHostnames || new Set())];
  const ready = Boolean(serverOptions.requireTurnstile && serverOptions.turnstileSiteKey && serverOptions.turnstileSecret);
  return {
    ready,
    enabled: Boolean(serverOptions.requireTurnstile),
    siteKeyConfigured: Boolean(serverOptions.turnstileSiteKey),
    secretConfigured: Boolean(serverOptions.turnstileSecret),
    allowedHostnames,
    message: ready ? `已保护登录、注册、兑换；允许域名 ${allowedHostnames.join(', ') || '未限制'}` : '未完整启用人机验证',
  };
}

function buildBackupReadiness(data, serverOptions) {
  const backup = normalizeBackupStatusRecord(data.backupStatus);
  const maxAgeHours = Number(serverOptions.backupStatusMaxAgeHours || 26);
  const lastBackupMs = Date.parse(backup.lastBackupAt || '');
  const lastRestoreMs = Date.parse(backup.lastRestoreTestAt || '');
  const nowMs = currentDate(serverOptions).getTime();
  const fresh = Number.isFinite(lastBackupMs) && nowMs - lastBackupMs <= maxAgeHours * 3_600_000;
  const restoreTested = Number.isFinite(lastRestoreMs) && nowMs - lastRestoreMs <= 30 * 86_400_000;
  const ready = backup.status === 'ok' && fresh && restoreTested;
  return {
    ...backup,
    ready,
    maxAgeHours,
    fresh,
    restoreTested,
    message: ready
      ? `最近备份 ${backup.lastBackupAt}，恢复演练 ${backup.lastRestoreTestAt}`
      : backup.message || '未看到新鲜备份和恢复演练记录',
  };
}

function recordBackupStatus(data, body, serverOptions) {
  const now = currentDate(serverOptions).toISOString();
  const next = normalizeBackupStatusRecord({
    provider: body.provider,
    target: body.target,
    lastBackupAt: body.lastBackupAt || now,
    lastRestoreTestAt: body.lastRestoreTestAt,
    status: body.status || 'ok',
    artifact: body.artifact,
    sizeBytes: body.sizeBytes,
    checksum: body.checksum,
    message: body.message,
    updatedAt: now,
  });
  data.backupStatus = next;
  data.events.push({
    type: 'backup_status_recorded',
    status: next.status,
    target: next.target,
    at: now,
  });
  return {
    backup: buildBackupReadiness(data, serverOptions),
    productionReadiness: null,
    events: sanitizeAdminEvents(data.events),
  };
}

function buildPlusAccountSummary(accounts, serverOptions = {}) {
  const now = currentDate(serverOptions);
  const active = accounts.filter((account) => account.status === 'active').length;
  const dueSoon = accounts.filter((account) => {
    const daysLeft = plusAccountRenewalDaysLeft(account.plusRenewalAt, now);
    return daysLeft !== null && daysLeft >= 0 && daysLeft <= 5;
  }).length;
  const blocked = accounts.filter((account) =>
    account.status === 'risk_hold' ||
    account.status === 'retired' ||
    account.complianceStatus === 'blocked',
  ).length;
  const totalTry = accounts.reduce((sum, account) => sum + Number(account.appleBalanceTry || 0), 0);
  return {
    total: accounts.length,
    active,
    dueSoon,
    blocked,
    totalAppleBalanceTry: round2(totalTry),
    reminderText: accounts.length
      ? `${dueSoon} 个账号 5 天内需处理，${blocked} 个处于风险/停用状态`
      : '暂无 Plus 账号资产',
  };
}

function buildRtAccountSummary(accounts) {
  const active = accounts.filter((account) => account.status === 'active').length;
  const ready = accounts.filter((account) => account.status === 'ready_for_refresh').length;
  const needsRefresh = accounts.filter((account) => account.status === 'needs_refresh').length;
  const blocked = accounts.filter((account) => account.status === 'blocked' || account.status === 'retired').length;
  const byPlatform = accounts.reduce((summary, account) => {
    const platform = account.platform || 'codex';
    summary[platform] = (summary[platform] || 0) + 1;
    return summary;
  }, {});
  return {
    total: accounts.length,
    active,
    ready,
    needsRefresh,
    blocked,
    byPlatform,
    reminderText: accounts.length
      ? `${ready} 个待刷新，${needsRefresh} 个需要重新授权，${blocked} 个已停用`
      : '暂无 RT 账号',
  };
}



function sanitizeUser(user) {
  const displayName = String(user.displayName || user.nickname || '').trim();
  return {
    id: user.id,
    email: user.email,
    emailMasked: maskEmail(user.email),
    displayName: displayName || String(user.email || '').split('@')[0] || 'Frist',
    avatarUrl: sanitizeAvatarUrl(user.avatarUrl || ''),
    emailVerified: Boolean(user.emailVerified),
    isAdmin: Boolean(user.isAdmin),
    plan: user.plan,
    renewalDate: user.renewalDate,
    userInitials: initialsFromDisplayName(displayName || user.email),
  };
}

function sanitizeAvatarUrl(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const url = new URL(raw);
    if (!/^https?:$/i.test(url.protocol)) return '';
    return url.href.slice(0, 500);
  } catch {
    return '';
  }
}





function sanitizeRedemptionCard(card) {
  return {
    id: card.id,
    batchId: card.batchId || '',
    code: card.code || card.codePreview || maskCardCode(cardCodePlain(card)),
    codePreview: card.codePreview || maskCardCode(card.code || ''),
    codeHash: card.codeHash || '',
    label: card.label || 'CC中转 兑换码',
    planId: card.planId || '',
    plan: card.plan || 'balance',
    durationDays: Number(card.durationDays || 0),
    quotaUsd: Number(card.quotaUsd || 0),
    priceCny: Number(card.priceCny || 0),
    credit: formatUsdFromCnyCents(card.creditCents),
    creditCny: formatCny(card.creditCents),
    creditCents: Number(card.creditCents || 0),
    status: card.status || 'unused',
    source: card.source || 'xianyu',
    note: card.note || '',
    createdAt: card.createdAt || '',
    updatedAt: card.updatedAt || '',
    soldAt: card.soldAt || '',
    soldOrderId: card.soldOrderId || '',
    soldPlatform: card.soldPlatform || '',
    soldBuyerHint: card.soldBuyerHint || '',
    fulfillmentId: card.fulfillmentId || '',
    deliveredAt: card.deliveredAt || '',
    redeemedAt: card.redeemedAt || '',
    redeemedEmail: maskEmail(card.redeemedEmail || ''),
  };
}

function sanitizeUpstreamChannel(channel) {
  return {
    id: channel.id,
    source: channel.source || 'reference-channel',
    provider: channel.provider || '参考渠道',
    platform: channel.platform || 'Other',
    model: channel.model || '',
    status: channel.status || 'unknown',
    upstreamMultiplier: Number(channel.upstreamMultiplier || 0),
    saleMultiplier: Number(channel.saleMultiplier || 0),
    latencyMs: Number(channel.latencyMs || 0),
    checkedAt: channel.checkedAt || '',
    syncedAt: channel.syncedAt || channel.checkedAt || '',
  };
}

function sanitizeUpstreamBalance(balance, serverOptions = {}) {
  const record = normalizeUpstreamBalanceRecord(balance || {});
  const warningCny = Number(serverOptions.upstreamBalanceWarningCny || record.warningCny || 50);
  const criticalCny = Number(serverOptions.upstreamBalanceCriticalCny || record.criticalCny || 20);
  const level = normalizeUpstreamBalanceLevel(record.level, record.remainingCny, warningCny, criticalCny);
  return {
    provider: record.provider || (serverOptions.newApiEnabled ? 'New-API' : ''),
    userId: record.userId,
    username: record.username,
    emailMasked: maskEmail(record.emailMasked || ''),
    group: record.group,
    remainingCny: round2(record.remainingCny),
    usedCny: round2(record.usedCny),
    remainingUsd: round2(record.remainingUsd),
    warningCny: round2(warningCny),
    criticalCny: round2(criticalCny),
    level,
    pauseRecommended: level === 'critical',
    checkedAt: record.checkedAt,
    stale: !record.checkedAt || Date.now() - Date.parse(record.checkedAt) > Math.max(1, Number(serverOptions.upstreamBalanceStaleHours || 26)) * 3_600_000,
    lastError: record.lastError,
  };
}

function normalizeUpstreamBalanceLevel(value, remainingCny, warningCny = 50, criticalCny = 20) {
  const explicit = String(value || '').trim().toLowerCase();
  if (['ok', 'warning', 'critical', 'unknown'].includes(explicit)) return explicit;
  const remaining = Number(remainingCny || 0);
  if (!Number.isFinite(remaining) || remaining <= 0) return 'unknown';
  if (remaining <= Number(criticalCny || 20)) return 'critical';
  if (remaining <= Number(warningCny || 50)) return 'warning';
  return 'ok';
}

function sanitizeXianyuFulfillment(item) {
  return {
    id: item.id,
    platform: item.platform || 'xianyu',
    orderId: item.orderId || '',
    productTitle: item.productTitle || '',
    buyerHint: item.buyerHint || '',
    planId: item.planId || '',
    cardId: item.cardId || '',
    cardCode: item.cardCode || '',
    status: item.status || 'draft',
    deliveryMessage: item.deliveryMessage || '',
    note: item.note || '',
    createdAt: item.createdAt || '',
    updatedAt: item.updatedAt || '',
    deliveredAt: item.deliveredAt || '',
    redeemedAt: item.redeemedAt || '',
    redeemedEmail: maskEmail(item.redeemedEmail || ''),
  };
}

function buildChannelSyncSummary(data, serverOptions = {}) {
  const channels = data.upstreamChannelSnapshots || [];
  const healthy = channels.filter((item) => item.status === 'healthy').length;
  const slow = channels.filter((item) => item.status === 'slow').length;
  const down = channels.filter((item) => item.status === 'down').length;
  const models = new Set(channels.map((item) => item.model).filter(Boolean));
  const averageSaleMultiplier = channels.length
    ? round2(channels.reduce((sum, item) => sum + Number(item.saleMultiplier || 0), 0) / channels.length)
    : 0;
  return {
    total: channels.length,
    healthy,
    slow,
    down,
    modelCount: models.size,
    rateMarkup: Number(serverOptions.rateMarkup ?? 0.1),
    averageSaleMultiplier,
    lastSyncedAt: channels.map((item) => item.syncedAt || item.checkedAt || '').filter(Boolean).sort().at(-1) || '',
  };
}

function buildXianyuFulfillmentSummary(data) {
  const items = data.xianyuFulfillments || [];
  return {
    total: items.length,
    delivered: items.filter((item) => item.status === 'delivered').length,
    redeemed: items.filter((item) => item.status === 'redeemed').length,
    cancelled: items.filter((item) => item.status === 'cancelled').length,
    availableCards: (data.redemptionCards || []).filter((card) => card.status === 'unused').length,
    soldCards: (data.redemptionCards || []).filter((card) => card.status === 'sold').length,
  };
}

function buildXianyuAutomationConfig(serverOptions) {
  const base = String(serverOptions.publicGatewayBaseUrl || 'https://jiyu.245334.xyz/v1')
    .replace(/\/v1\/?$/i, '')
    .replace(/\/$/, '');
  return {
    enabled: Boolean(String(serverOptions.xianyuWebhookToken || '').trim()),
    endpoint: `${base}/api/ops/xianyu/paid-order`,
    method: 'POST',
    authHeader: 'x-cc-xianyu-token',
    tokenPreview: maskSecretPreview(serverOptions.xianyuWebhookToken),
    acceptsOnlyPaid: true,
    paidStatuses: ['等待卖家发货', '买家已付款', '已付款', '待发货', 'paid'],
    samplePayload: {
      orderId: '闲鱼订单号',
      status: '等待卖家发货',
      paid: true,
      productTitle: 'CC中转 兑换码',
      buyerHint: '买家昵称/尾号',
      planId: '套餐ID，可留空',
    },
  };
}

function maskSecretPreview(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.length <= 10) return '••••';
  return `${text.slice(0, 4)}••••${text.slice(-4)}`;
}

function sanitizePlusAccount(account, serverOptions = {}) {
  const renewalDaysLeft = plusAccountRenewalDaysLeft(account.plusRenewalAt, currentDate(serverOptions));
  return {
    id: account.id,
    label: sanitizeLedgerLabel(account.label, {
      fallback: 'ChatGPT Plus 账号',
      email: account.openaiEmail || account.appleEmail || '',
      accountId: '',
      refreshToken: '',
    }),
    openaiEmail: maskEmail(account.openaiEmail || ''),
    appleEmail: maskEmail(account.appleEmail || ''),
    openaiEmailHint: emailDomain(account.openaiEmail || ''),
    appleEmailHint: emailDomain(account.appleEmail || ''),
    region: account.region || 'Other',
    status: account.status || 'warming',
    complianceStatus: account.complianceStatus || 'needs_review',
    billingMethod: account.billingMethod || 'apple_iap',
    appleBalanceTry: Number(account.appleBalanceTry || 0),
    monthlyCostTry: Number(account.monthlyCostTry || 0),
    plusRenewalAt: account.plusRenewalAt || '',
    renewalDaysLeft,
    renewalText: formatRenewalText(renewalDaysLeft, account.plusRenewalAt),
    lastCheckedAt: account.lastCheckedAt || '',
    deviceProfile: account.deviceProfile || '',
    browserProfile: account.browserProfile || '',
    riskNote: account.riskNote || '',
    operatorNote: account.operatorNote || '',
    secretPreview: account.secrets ? '已保存，管理端脱敏' : '未保存',
    routingEnabled: false,
    createdAt: account.createdAt || '',
    updatedAt: account.updatedAt || '',
  };
}

function sanitizeRtAccount(account) {
  return {
    id: account.id,
    label: sanitizeLedgerLabel(account.label, {
      fallback: 'RT 账号',
      email: account.email || '',
      accountId: account.accountId || '',
      refreshToken: account.refreshToken || '',
    }),
    platform: account.platform || 'codex',
    status: account.status || 'ready_for_refresh',
    email: maskEmail(account.email || ''),
    emailHint: emailDomain(account.email || ''),
    accountId: maskAccountId(account.accountId || ''),
    accountIdHint: tailHint(account.accountId || ''),
    refreshTokenPreview: maskRefreshToken(account.refreshToken || ''),
    refreshTokenFingerprint: account.refreshTokenFingerprint || tokenFingerprint(account.refreshToken || ''),
    sourceLabel: account.sourceLabel || '',
    accountType: account.accountType || '',
    note: account.note || '',
    lastRefreshAt: account.lastRefreshAt || '',
    expiresAt: account.expiresAt || '',
    importedAt: account.importedAt || account.createdAt || '',
    routingEnabled: false,
    createdAt: account.createdAt || '',
    updatedAt: account.updatedAt || '',
  };
}

function emailDomain(email) {
  const [, domain = ''] = String(email || '').split('@');
  return domain ? `@${domain}` : '';
}

function sanitizeLedgerLabel(value, { fallback, email, accountId, refreshToken }) {
  let label = String(value || '').trim();
  if (!label) return fallback;
  if (email) {
    label = label.replaceAll(email, maskEmail(email));
  }
  if (accountId) {
    label = label.replaceAll(accountId, maskAccountId(accountId));
  }
  if (refreshToken) {
    label = label.replaceAll(refreshToken, maskRefreshToken(refreshToken));
  }
  return label.slice(0, 80) || fallback;
}

function plusAccountRenewalDaysLeft(value, nowValue = new Date()) {
  if (!value) return null;
  const renewal = Date.parse(value);
  if (!Number.isFinite(renewal)) return null;
  const now = nowValue instanceof Date ? nowValue.getTime() : Date.parse(nowValue);
  if (!Number.isFinite(now)) return null;
  return Math.ceil((renewal - now) / 86_400_000);
}

function formatRenewalText(daysLeft, value) {
  if (!value) return '未登记续费日';
  if (daysLeft === null) return '续费日期无效';
  if (daysLeft < 0) return `已过期 ${Math.abs(daysLeft)} 天`;
  if (daysLeft === 0) return '今天到期';
  return `${daysLeft} 天后到期`;
}

function parseRtImportText(input) {
  if (Array.isArray(input)) {
    return input.flatMap((item) => parseRtImportItem(item));
  }
  if (input && typeof input === 'object') {
    return parseRtImportItem(input);
  }
  const raw = String(input || '').trim();
  if (!raw) return [];
  if (raw.startsWith('[') || raw.startsWith('{')) {
    const parsed = JSON.parse(raw);
    return parseRtImportText(parsed);
  }
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [refreshToken, email = '', accountId = ''] = line.split(/[,\t|]/).map((part) => part.trim());
      return {
        refreshToken,
        email,
        accountId,
      };
    });
}

function parseRtImportItem(item) {
  if (typeof item === 'string') {
    return parseRtImportText(item);
  }
  if (!item || typeof item !== 'object') {
    return [];
  }
  return [
    {
      label: item.label,
      platform: item.platform || item.provider,
      status: item.status,
      email: item.email,
      accountId: item.accountId ?? item.account_id,
      refreshToken: item.refreshToken ?? item.refresh_token ?? item.rt ?? item.token,
      sourceLabel: item.sourceLabel || item.source || item.file,
      accountType: item.accountType || item.type,
      note: item.note || item.riskNote,
      lastRefreshAt: item.lastRefreshAt || item.last_refresh,
      expiresAt: item.expiresAt || item.expired,
    },
  ];
}



function normalizeCardCode(value) {
  return String(value || '').trim().toUpperCase();
}

function hashRedemptionCode(value) {
  const code = normalizeCardCode(value);
  return code ? `sha256:${createHash('sha256').update(code).digest('hex')}` : '';
}

function redemptionMatchesCode(redemption, code) {
  const normalized = normalizeCardCode(code);
  if (!normalized) return false;
  if (normalizeCardCode(redemption?.code) === normalized) return true;
  return Boolean(redemption?.codeHash && redemption.codeHash === hashRedemptionCode(normalized));
}

function cardMatchesCode(card, code, serverOptions = {}) {
  const normalized = normalizeCardCode(code);
  if (!normalized) return false;
  if (normalizeCardCode(card?.code) === normalized) return true;
  if (card?.codeHash && card.codeHash === hashRedemptionCode(normalized)) return true;
  if (!card?.codeHash) {
    const plain = cardCodePlain(card, serverOptions);
    return Boolean(plain && plain === normalized);
  }
  return false;
}

function cardCodePlain(card, serverOptions = {}) {
  const direct = normalizeCardCode(card?.code);
  if (direct) return direct;
  const cipher = String(card?.codeCipher || '').trim();
  if (!cipher) return '';
  try {
    return decryptCardCode(cipher, serverOptions);
  } catch {
    return '';
  }
}

function encryptCardCode(code, serverOptions = {}) {
  const normalized = normalizeCardCode(code);
  if (!normalized) return '';
  return encryptSecretField(normalized, redemptionCodeEncryptionKey(serverOptions)).replace(/^enc:v1:/, 'enc-card:v1:');
}

function decryptCardCode(value, serverOptions = {}) {
  const text = String(value || '').trim();
  if (!text) return '';
  return normalizeCardCode(
    decryptSecretField(text.replace(/^enc-card:v1:/, 'enc:v1:'), redemptionCodeEncryptionKey(serverOptions)),
  );
}

function redemptionCodeEncryptionKey(serverOptions = {}) {
  const secret =
    serverOptions.dataEncryptionKey ||
    serverOptions.passwordHashSecret ||
    serverOptions.sessionSecret ||
    'jiyu-redemption-code-dev-secret';
  return createHash('sha256').update(`jiyu-redemption-code:${secret}`).digest();
}

function maskCardCode(value) {
  const code = normalizeCardCode(value);
  if (!code) return '';
  const parts = code.split('-').filter(Boolean);
  if (parts.length >= 3) return `${parts[0]}-••••-${parts.at(-1)}`;
  if (code.length <= 8) return `${code.slice(0, 2)}••••`;
  return `${code.slice(0, 5)}••••${code.slice(-4)}`;
}

function randomCardCodeSegment() {
  const alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  let text = '';
  for (let index = 0; index < 5; index += 1) {
    text += alphabet[randomInt(alphabet.length)];
  }
  return text;
}

function normalizeCardPrefix(value) {
  const text = String(value || DEFAULT_CARD_BATCH_PREFIX).trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  return (text || DEFAULT_CARD_BATCH_PREFIX).slice(0, 10);
}

function clampInteger(value, min, max) {
  const number = Math.round(Number(value || min));
  if (!Number.isFinite(number)) return min;
  return Math.min(max, Math.max(min, number));
}

function cardLabelForPlan(plan, body = {}) {
  const quotaUsd = Number(body.quotaUsd || body.creditUsd || 0);
  if (plan === 'day') return `Codex API ${quotaUsd || 30}刀额度/日卡`;
  if (plan === 'month') return `Codex API ${quotaUsd || 300}刀额度/月卡`;
  return `Codex API ${quotaUsd || 30}刀额度/不限时`;
}

function buildRedemptionCardExport(cards) {
  return cards
    .map((card) => [
      card.code,
      card.label,
      formatUsdFromCnyCents(card.creditCents),
      card.plan,
      card.durationDays ? `${card.durationDays}天` : '不限时',
    ].join('\t'))
    .join('\n');
}

function hashPassword(password, salt) {
  const iterations = 210_000;
  const passwordSalt = randomBytes(16).toString('base64url');
  const digest = pbkdf2Sync(String(password), `${salt}:${passwordSalt}`, iterations, 32, 'sha256').toString('base64url');
  return `pbkdf2-sha256$${iterations}$${passwordSalt}$${digest}`;
}

function verifyPassword(password, storedHash, salts) {
  const stored = String(storedHash || '');
  const candidates = Array.isArray(salts) ? salts : [salts];
  if (stored.startsWith('pbkdf2-sha256$')) {
    const [, iterationsText, passwordSalt, expectedDigest] = stored.split('$');
    const iterations = Number(iterationsText);
    if (!Number.isSafeInteger(iterations) || iterations < 100_000 || !passwordSalt || !expectedDigest) {
      return { ok: false, secret: '' };
    }
    const matchedSecret = candidates.find((salt) => {
      const actualDigest = pbkdf2Sync(String(password), `${salt}:${passwordSalt}`, iterations, 32, 'sha256').toString('base64url');
      return safeEqual(actualDigest, expectedDigest);
    });
    return { ok: Boolean(matchedSecret), secret: matchedSecret || '' };
  }
  const matchedSecret = candidates.find((salt) => safeEqual(legacyHashPassword(password, salt), stored));
  return { ok: Boolean(matchedSecret), secret: matchedSecret || '' };
}

function isModernPasswordHash(storedHash) {
  return String(storedHash || '').startsWith('pbkdf2-sha256$');
}

function legacyHashPassword(password, salt) {
  return createHash('sha256').update(`${salt}:${password}`).digest('hex');
}

function hashPasswordResetCode(code, salt) {
  return createHash('sha256').update(`${salt}:password-reset:${String(code || '').trim()}`).digest('hex');
}

function parseSecretList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim()).filter(Boolean);
  }
  return String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function normalizeTotpSecrets(value) {
  const items = Array.isArray(value) ? value : String(value || '').split(/[,\s]+/);
  return items
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .map((item) => {
      const decoded = decodeBase32Secret(item);
      return decoded.length >= 10 ? decoded : null;
    })
    .filter(Boolean);
}

function verifyTotpCode(secretBuffers, code, nowValue = new Date()) {
  const normalizedCode = String(code || '').replace(/\D/g, '');
  if (!/^\d{6}$/.test(normalizedCode) || !Array.isArray(secretBuffers) || secretBuffers.length === 0) {
    return false;
  }
  const nowMs = nowValue instanceof Date ? nowValue.getTime() : Date.parse(nowValue);
  const counter = Math.floor((Number.isFinite(nowMs) ? nowMs : Date.now()) / 1000 / TOTP_STEP_SECONDS);
  for (const secret of secretBuffers) {
    for (const offset of [-1, 0, 1]) {
      if (safeEqual(generateTotpCode(secret, counter + offset), normalizedCode)) {
        return true;
      }
    }
  }
  return false;
}

function generateTotpCode(secret, counter) {
  const buffer = Buffer.alloc(8);
  const safeCounter = Math.max(0, Number(counter || 0));
  buffer.writeUInt32BE(Math.floor(safeCounter / 0x100000000), 0);
  buffer.writeUInt32BE(safeCounter >>> 0, 4);
  const digest = createHmac('sha1', secret).update(buffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % 10 ** TOTP_DIGITS).padStart(TOTP_DIGITS, '0');
}

function decodeBase32Secret(value) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = String(value || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  let bits = '';
  for (const char of clean) {
    const index = alphabet.indexOf(char);
    if (index === -1) continue;
    bits += index.toString(2).padStart(5, '0');
  }
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}





function generateCustomerApiKey() {
  return `fk-live-${randomBytes(32).toString('base64url')}`;
}


function maskRefreshToken(value) {
  const token = String(value || '');
  if (!token) return 'rt-******';
  const prefix = token.includes('_') ? token.split('_')[0] : token.slice(0, Math.min(6, token.length));
  return `${prefix}-••••••${token.slice(-6)}`;
}

function maskAccountId(value) {
  const text = String(value || '');
  if (!text) return '';
  return `${text.slice(0, Math.min(6, text.length))}••••${text.slice(-4)}`;
}

function tailHint(value) {
  const text = String(value || '');
  return text ? `尾号 ${text.slice(-4)}` : '';
}

function tokenFingerprint(value) {
  const text = String(value || '').trim();
  return text ? createHash('sha256').update(text).digest('hex').slice(0, 16) : '';
}


function initialsFromDisplayName(value) {
  const cleaned = String(value || 'fa').replace(/@.*$/, '').replace(/[_-]+/g, ' ').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return String(parts[0] || 'fa').slice(0, 2).toUpperCase();
}



function usdNumberFromCnyCents(cents, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return round2Finite(Number(cents || 0) / 100 / safeRate);
}

function cnyNumberFromCents(cents) {
  return round2Finite(Number(cents || 0) / 100);
}




function round2Finite(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return round2(number);
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isCli) {
  const port = Number(process.env.FRIST_API_PORT || process.env.PORT || 3180);
  const host = process.env.FRIST_API_HOST || '127.0.0.1';
  const server = createFristApiServer({
    exposeVerificationCode: process.env.FRIST_API_EXPOSE_VERIFICATION_CODE === '1',
  });
  server.listen(port, host, () => {
    console.log(`CC中转 server listening on http://${host}:${port}`);
  });
  let closing = false;
  const closeGracefully = (signal) => {
    if (closing) return;
    closing = true;
    console.log(`CC中转 server received ${signal}, closing...`);
    const forceTimer = setTimeout(() => {
      console.error('CC中转 server close timeout, exiting.');
      process.exit(1);
    }, 8_000);
    forceTimer.unref();
    server.close((error) => {
      if (error) {
        console.error(`CC中转 server close failed: ${error.message}`);
        process.exit(1);
      }
      process.exit(0);
    });
  };
  process.once('SIGTERM', () => closeGracefully('SIGTERM'));
  process.once('SIGINT', () => closeGracefully('SIGINT'));
}

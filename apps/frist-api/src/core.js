const CLIENT_PROFILES = new Map([
  [
    'claude',
    {
      slug: 'claude',
      clientName: 'Claude',
      providerName: 'Frist-API',
      remark: 'Claude 兼容入口',
      wireApi: 'responses',
    },
  ],
  [
    'codex',
    {
      slug: 'codex',
      clientName: 'Codex',
      providerName: 'Frist-API',
      remark: 'Codex auth.json + config.toml',
      wireApi: 'responses',
    },
  ],
  [
    'gemini',
    {
      slug: 'gemini',
      clientName: 'Gemini',
      providerName: 'Frist-API',
      remark: 'Gemini OpenAI 兼容入口',
      wireApi: 'responses',
    },
  ],
  [
    'opencode',
    {
      slug: 'opencode',
      clientName: 'OpenCode',
      providerName: 'Frist-API',
      remark: 'OpenCode OpenAI 兼容入口',
      wireApi: 'responses',
    },
  ],
  [
    'openclaw',
    {
      slug: 'openclaw',
      clientName: 'OpenClaw',
      providerName: 'Frist-API',
      remark: 'OpenClaw 内部模型入口',
      wireApi: 'responses',
    },
  ],
  [
    'hermes',
    {
      slug: 'hermes',
      clientName: 'Hermes',
      providerName: 'Frist-API',
      remark: 'Hermes 兼容代理入口',
      wireApi: 'responses',
    },
  ],
  [
    'harmes',
    {
      slug: 'harmes',
      clientName: 'Harmes',
      providerName: 'Frist-API',
      remark: 'Harmes 兼容代理入口',
      wireApi: 'responses',
    },
  ],
]);

const MODEL_GROUP_FALLBACKS = Object.freeze({
  DeepSeek: 'deepseek-v4-flash',
  Gemini: 'gemini-2.5-flash',
});
const MODEL_GROUP_OFFICIAL_MODELS = Object.freeze({
  OpenAI: Object.freeze([
    'gpt-5.5',
    'gpt-5.4',
    'gpt-5.4-mini',
    'gpt-image-2',
    'gpt-image-1.5',
    'gpt-5.3-codex',
    'gpt-4o',
    'gpt-5-codex',
  ]),
  DeepSeek: Object.freeze(['deepseek-v4-flash', 'deepseek-v4-pro']),
  Claude: Object.freeze(['claude-opus-4-6-thinking-c', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c']),
  Gemini: Object.freeze(['gemini-2.5-flash']),
});

const HEALTH_LABELS = {
  healthy: '正常',
  slow: '可用较慢',
  down: '暂不可用',
  maintenance: '维护中',
};

const DEFAULT_PUBLIC_MODEL = 'gpt-5.5';
const OFFICIAL_MODEL_ALIASES = new Map([
  ['5.5', 'gpt-5.5'],
  ['gpt5.5', 'gpt-5.5'],
  ['gpt-55', 'gpt-5.5'],
  ['image2', 'gpt-image-2'],
  ['gpt-image2', 'gpt-image-2'],
  ['gpt_image_2', 'gpt-image-2'],
  ['claude-sonnet-4-5', 'claude-sonnet-4-5-c'],
  ['claude-opus-4-6', 'claude-opus-4-6-c'],
  ['claude-opus-4-6-thinking', 'claude-opus-4-6-thinking-c'],
]);
const MODEL_STRENGTH_ORDER = [
  'gpt-5.5-pro',
  'gpt-5.5-c',
  'gpt-5.5',
  'gpt-5.4-pro',
  'gpt-5.4-c',
  'gpt-5.4',
  'gpt-5.4-mini',
  'gpt-5.4-nano',
  'gpt-image-2',
  'gpt-image-1.5',
  'gpt-image-1',
  'gpt-5.3-codex',
  'deepseek-v4-flash',
  'deepseek-v4-pro',
  'deepseek-chat',
  'deepseek-reasoner',
  'claude-opus-4-6-thinking-c',
  'claude-opus-4-6-c',
  'claude-sonnet-4-5-c',
  'gemini-2.5-flash',
];

const CODEX_DEFAULT_MCP_SERVERS = Object.freeze({
  playwright: Object.freeze({
    type: 'stdio',
    command: 'npx',
    args: Object.freeze(['-y', '@playwright/mcp@latest']),
  }),
  superpowers: Object.freeze({
    type: 'stdio',
    command: 'npx',
    args: Object.freeze(['-y', 'superpowers-mcp@latest']),
  }),
  open_computer_use: Object.freeze({
    type: 'stdio',
    command: 'npx',
    args: Object.freeze(['-y', '-p', 'open-computer-use@latest', 'open-codex-computer-use-mcp']),
  }),
});
const CC_SWITCH_MCP_APPS = Object.freeze(['claude', 'codex', 'gemini', 'opencode', 'hermes']);

export function normalizeBaseUrl(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    throw new Error('请求地址不能为空');
  }
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  return withProtocol.replace(/\/+$/, '');
}

export function normalizeOfficialModelName(model) {
  const value = String(model || '').trim();
  if (!value) return '';
  return OFFICIAL_MODEL_ALIASES.get(value.toLowerCase()) || value;
}

export function normalizeOfficialModelList(models = []) {
  return [...new Set((Array.isArray(models) ? models : []).map(normalizeOfficialModelName).filter(Boolean))];
}

export function normalizeClientAvailableModels(availableModels = [], options = {}) {
  return normalizeAvailableModels(availableModels, options);
}

export function buildCcSwitchImportUrl({
  target,
  apiKey,
  baseUrl,
  usageBaseUrl,
  model,
  defaultModel,
  availableModels,
  modelGroup,
  planExpiresAt,
  sdkOptions,
  preferExplicitDefaultModel = false,
}) {
  const profile = clientProfile(target);
  const normalizedInputBaseUrl = normalizeBaseUrl(baseUrl);
  const normalizedBaseUrl = gatewayBaseUrlForModelGroup(baseUrl, modelGroup);
  const clientBaseUrl = clientBaseUrlForProfile(profile, normalizedBaseUrl);
  const modelList = normalizeAvailableModels(availableModels, { model, defaultModel, modelGroup });
  const requestedModel = normalizeOfficialModelName(model);
  const explicitDefaultModel = normalizeOfficialModelName(defaultModel);
  const safeModel =
    explicitDefaultModel && explicitDefaultModel === requestedModel && modelList.includes(explicitDefaultModel)
      ? explicitDefaultModel
      : chooseDefaultModel({ model, defaultModel, availableModels: modelList, modelGroup });
  const safeKey = String(apiKey || '').trim();
  const officialUrl = brandOfficialUrl(clientBaseUrl);
  const remark = buildImportRemark({ profile, modelGroup, planExpiresAt });
  const usageConfig = buildCcSwitchUsageConfig({ apiKey: safeKey, baseUrl: usageBaseUrl || normalizedInputBaseUrl });
  const claudeModelDefaults = profile.slug === 'claude' ? buildClaudeDeepLinkModelDefaults(modelList) : {};
  const ccSwitchApp = ccSwitchAppSlug(profile);

  const params = new URLSearchParams({
    resource: 'provider',
    app: ccSwitchApp,
    name: profile.providerName,
    endpoint: clientBaseUrl,
    apiKey: safeKey,
    homepage: officialUrl,
    enabled: 'true',
    model: safeModel,
    ...claudeModelDefaults,
    notes: remark,
    usageEnabled: 'true',
    usageScript: base64EncodeUtf8UrlSafe(usageConfig.script),
    usageApiKey: safeKey,
    usageBaseUrl: usageConfig.baseUrl,
    usageAutoInterval: String(usageConfig.autoInterval),
  });

  return `ccswitch://v1/import?${params.toString()}`;
}

export function buildCcSwitchMcpImportUrl({
  apps = CC_SWITCH_MCP_APPS,
  mcpServers = defaultCodexMcpServers(),
  enabled = true,
} = {}) {
  const appList = normalizeCcSwitchMcpApps(apps);
  const payload = {
    mcpServers: Object.fromEntries(
      Object.entries(mcpServers || {}).map(([name, config]) => [
        name,
        {
          type: config.type || 'stdio',
          command: config.command || '',
          args: Array.isArray(config.args) ? [...config.args] : [],
          ...(config.env && typeof config.env === 'object' && Object.keys(config.env).length > 0
            ? { env: { ...config.env } }
            : {}),
        },
      ]),
    ),
  };
  const params = new URLSearchParams({
    resource: 'mcp',
    apps: appList.join(','),
    enabled: String(Boolean(enabled)),
    config: base64EncodeUtf8UrlSafe(JSON.stringify(payload)),
  });
  return `ccswitch://v1/import?${params.toString()}`;
}

export function buildClientConfig({
  target,
  apiKey,
  baseUrl,
  model,
  defaultModel,
  availableModels,
  modelGroup,
  planExpiresAt,
  sdkOptions,
  preferExplicitDefaultModel = false,
}) {
  const profile = clientProfile(target);
  const normalizedBaseUrl = gatewayBaseUrlForModelGroup(baseUrl, modelGroup);
  const clientBaseUrl = clientBaseUrlForProfile(profile, normalizedBaseUrl);
  const modelList = normalizeAvailableModels(availableModels, { model, defaultModel, modelGroup });
  const safeModel = chooseDefaultModel({
    model,
    defaultModel,
    availableModels: modelList,
    modelGroup,
    preferExplicitDefaultModel,
  });
  const safeKey = String(apiKey || '').trim();
  if (!safeKey) {
    throw new Error('API Key 不能为空');
  }
  const officialUrl = brandOfficialUrl(clientBaseUrl);
  const contextWindow = 1_000_000;
  const compressionThreshold = 900_000;
  const safeSdkOptions = normalizeSdkOptions(sdkOptions);
  const mcpServers = defaultCodexMcpServers();
  const inlineMcpServers = profile.slug === 'codex' ? mcpServers : undefined;
  const authJson = buildClientAuthJson({
    profile,
    apiKey: safeKey,
    baseUrl: clientBaseUrl,
    model: safeModel,
    availableModels: modelList,
  });
  const configToml = buildResponsesConfigToml({
    baseUrl: normalizedBaseUrl,
    model: safeModel,
    availableModels: modelList,
    modelGroup,
    providerName: profile.providerName,
    contextWindow,
    compressionThreshold,
    sdkOptions: safeSdkOptions,
    mcpServers: inlineMcpServers,
  });
  const interfaceFormat = interfaceFormatForProfile(profile);
  const authField = authFieldForProfile(profile);
  const usageConfig = buildCcSwitchUsageConfig({ apiKey: safeKey, baseUrl: normalizeBaseUrl(baseUrl) });

  return {
    targetSlug: profile.slug,
    providerName: profile.providerName,
    remark: buildImportRemark({ profile, modelGroup, planExpiresAt }),
    officialUrl,
    apiRequestUrl: clientBaseUrl,
    interfaceFormat,
    authField,
    authHeaderName: 'authorization',
    authHeaderValue: authField === 'OPENAI_API_KEY' ? 'Bearer ${OPENAI_API_KEY}' : '${ANTHROPIC_AUTH_TOKEN}',
    modelName: safeModel,
    defaultModel: safeModel,
    availableModels: modelList,
    modelGroup: normalizeModelGroup(modelGroup),
    contextWindow,
    compressionThreshold,
    reasoningEffort: 'xhigh',
    billingNote: '按官方标准计费，Frist-API 自动折扣结算',
    teammatesMode: false,
    toolSearchEnabled: true,
    responsesEnabled: true,
    streamingEnabled: true,
    imagesEnabled: modelList.some((item) => /image|dall/i.test(item)),
    maxThinkingStrength: 'xhigh',
    sdkOptions: safeSdkOptions,
    features: defaultClientFeatures(modelList),
    mcpServers,
    ccSwitchCapabilities: buildCcSwitchCapabilitySummary({ profile, modelList, mcpServers }),
    ccSwitchMcpUrl: buildCcSwitchMcpImportUrl({ mcpServers }),
    ccSwitchManualChecklist: buildCcSwitchManualChecklist({ profile, modelList }),
    usageScript: usageConfig.script,
    usageBaseUrl: usageConfig.baseUrl,
    usageAutoInterval: usageConfig.autoInterval,
    authJson,
    configToml,
    openCodeProviderJson:
      profile.slug === 'opencode'
        ? `${JSON.stringify(
            buildOpenCodeProviderFragment({
              apiKey: safeKey,
              baseUrl: clientBaseUrl,
              availableModels: modelList,
              sdkOptions: safeSdkOptions,
            }),
            null,
            2,
          )}\n`
        : '',
    ccSwitchUrl: buildCcSwitchImportUrl({
      target: profile.slug,
      apiKey: safeKey,
      baseUrl: normalizedBaseUrl,
      usageBaseUrl: normalizeBaseUrl(baseUrl),
      model: safeModel,
      defaultModel: safeModel,
      availableModels: modelList,
      modelGroup,
      planExpiresAt,
      sdkOptions: safeSdkOptions,
    }),
  };
}

export function buildClientSetupCommands(config) {
  const profile = clientProfile(config.targetSlug || config.target || 'codex');
  const paths = clientConfigPaths(profile.slug);
  const jsonConfig = buildGuideJsonConfig(config);
  const tomlConfig = config.configToml || '';

  return {
    jsonPath: paths.jsonPath,
    configPath: paths.configPath,
    jsonConfig,
    tomlConfig,
    macos: [
      `mkdir -p ${shellQuote(paths.macosDir)}`,
      `cat > ${shellQuote(paths.jsonPath)} <<'JSON'`,
      jsonConfig.trimEnd(),
      'JSON',
      `cat > ${shellQuote(paths.configPath)} <<'TOML'`,
      tomlConfig.trimEnd(),
      'TOML',
    ].join('\n'),
    windows: [
      `$dir = Join-Path $env:USERPROFILE '${paths.windowsDir}'`,
      'New-Item -ItemType Directory -Force -Path $dir | Out-Null',
      `@'`,
      jsonConfig.trimEnd(),
      `'@ | Set-Content -Encoding UTF8 (Join-Path $dir '${paths.windowsJsonFile}')`,
      `@'`,
      tomlConfig.trimEnd(),
      `'@ | Set-Content -Encoding UTF8 (Join-Path $dir '${paths.windowsConfigFile}')`,
    ].join('\n'),
    test: buildClientTestCommand(config),
  };
}

function buildOpenAiAuthJson(apiKey) {
  return `${JSON.stringify({ OPENAI_API_KEY: apiKey }, null, 2)}\n`;
}

function buildClientTestCommand(config) {
  const model = config.modelName || config.defaultModel || 'gpt-5.4-mini';
  if (config.targetSlug === 'claude') {
    return [
      'tmp_settings="$(mktemp)"',
      `cat > "$tmp_settings" <<'JSON'`,
      config.authJson.trimEnd(),
      'JSON',
      `claude --bare --no-session-persistence --settings "$tmp_settings" --model ${shellQuote(model)} -p "只回复 pong"`,
    ].join('\n');
  }
  if (config.targetSlug === 'codex') {
    return [
      'tmp_home="$(mktemp -d)"',
      'mkdir -p "$tmp_home"',
      `cat > "$tmp_home/auth.json" <<'JSON'`,
      config.authJson.trimEnd(),
      'JSON',
      `cat > "$tmp_home/config.toml" <<'TOML'`,
      config.configToml.trimEnd(),
      'TOML',
      `CODEX_HOME="$tmp_home" codex exec --skip-git-repo-check --ignore-rules --model ${shellQuote(model)} "只回复 pong"`,
    ].join('\n');
  }
  return [
    '# 先按上面的 JSON/TOML 写入对应客户端目录。',
    `# 然后在客户端里选择模型 ${model}，发送: 只回复 pong`,
  ].join('\n');
}

function buildClientAuthJson({ profile, apiKey, baseUrl, model, availableModels }) {
  if (profile.slug === 'claude') {
    return buildClaudeCodeConfigJson({ apiKey, baseUrl, model, availableModels });
  }
  return buildOpenAiAuthJson(apiKey);
}

function buildClaudeCodeConfigJson({ apiKey, baseUrl, model, availableModels }) {
  const models = normalizeAvailableModels(availableModels, { model });
  const modelDefaults = compactObject({
    ANTHROPIC_DEFAULT_OPUS_MODEL: findOptionalModelByPattern(models, /opus/i),
    ANTHROPIC_DEFAULT_HAIKU_MODEL: findOptionalModelByPattern(models, /haiku/i),
    ANTHROPIC_DEFAULT_SONNET_MODEL: findOptionalModelByPattern(models, /sonnet/i),
  });
  return `${JSON.stringify(
    {
      env: {
        ANTHROPIC_AUTH_TOKEN: apiKey,
        ANTHROPIC_BASE_URL: baseUrl,
        ENABLE_TOOL_SEARCH: 'true',
        CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: '1',
        ANTHROPIC_MODEL: model,
        ...modelDefaults,
      },
      effortLevel: 'max',
      includeCoAuthoredBy: false,
    },
    null,
    2,
  )}\n`;
}

function buildCcSwitchUsageConfig({ apiKey, baseUrl }) {
  const usageBaseUrl = usageBaseUrlFromGateway(baseUrl);
  const script = [
    '({',
    '  request: {',
    '    url: "{{baseUrl}}/api/frist/key-usage",',
    '    method: "GET",',
    '    headers: {',
    '      "Authorization": "Bearer {{apiKey}}",',
    '      "User-Agent": "cc-switch/frist-api"',
    '    }',
    '  },',
    '  extractor: function(response) {',
    '    if (!response || response.ok === false) {',
    '      return {',
    '        isValid: false,',
    '        invalidMessage: response && (response.error || response.message) || "Frist-API 用量查询失败"',
    '      };',
    '    }',
    '    return {',
    '      isValid: response.valid !== false,',
    '      planName: response.plan || "Frist-API",',
    '      remaining: Number(response.remainingUsd || 0),',
    '      used: Number(response.usedUsd || 0),',
    '      total: Number(response.totalUsd || 0),',
    '      unit: "USD",',
    '      extra: [',
    '        "今日 " + (response.todayCost || "$0.00"),',
    '        "本月 " + (response.monthCost || "$0.00"),',
    '        "请求 " + (response.todayCalls || "0 次"),',
    '        "Token " + (response.totalTokens || "0")',
    '      ].join(" · ")',
    '    };',
    '  }',
    '})',
  ].join('\n');
  return {
    enabled: true,
    template: 'custom',
    baseUrl: usageBaseUrl,
    apiKey,
    autoInterval: 15,
    script,
  };
}

function buildOpenCodeModelConfig(models = []) {
  return normalizeAvailableModels(models).reduce((items, model) => {
    items[model] = { name: model };
    return items;
  }, {});
}

function buildOpenCodeProviderEntry({ apiKey, baseUrl, availableModels, sdkOptions = {} }) {
  return {
    npm: '@ai-sdk/openai-compatible',
    options: {
      ...sdkOptions,
      baseURL: baseUrl,
      apiKey,
    },
    models: buildOpenCodeModelConfig(availableModels),
  };
}

function buildOpenCodeProviderFragment({ apiKey, baseUrl, availableModels, sdkOptions = {} }) {
  return {
    provider: {
      'frist-api': buildOpenCodeProviderEntry({
        apiKey,
        baseUrl,
        availableModels,
        sdkOptions,
      }),
    },
  };
}

function buildResponsesConfigToml({
  baseUrl,
  model,
  defaultModel,
  availableModels = [],
  modelGroup,
  providerName = 'Frist-API',
  contextWindow = 1_000_000,
  compressionThreshold = 900_000,
  sdkOptions = {},
  mcpServers,
}) {
  const timeout = Number(sdkOptions.timeout || 600);
  const modelList = normalizeAvailableModels(availableModels, { model, defaultModel, modelGroup });
  const requestedDefault = normalizeOfficialModelName(defaultModel || model);
  const safeDefaultModel =
    requestedDefault && modelList.includes(requestedDefault)
      ? requestedDefault
      : chooseDefaultModel({ model, defaultModel, availableModels: modelList, modelGroup });
  return [
    'model_provider = "custom"',
    `model = "${tomlString(safeDefaultModel)}"`,
    `default_model = "${tomlString(safeDefaultModel)}"`,
    `available_models = [${modelList.map((item) => `"${tomlString(item)}"`).join(', ')}]`,
    'model_reasoning_effort = "xhigh"',
    `model_context_window = ${Number(contextWindow)}`,
    `model_auto_compact_token_limit = ${Number(compressionThreshold)}`,
    'disable_response_storage = true',
    '',
    '[model_providers]',
    '[model_providers.custom]',
    `name = "${tomlString(providerName)}"`,
    'wire_api = "responses"',
    'requires_openai_auth = true',
    `base_url = "${tomlString(baseUrl)}"`,
    '',
    '[model_providers.custom.options]',
    `timeout = ${timeout}`,
    'setCacheKey = true',
    'tool_search = true',
    '',
    ...buildMcpServersToml(mcpServers),
  ].join('\n');
}

function buildMcpServersToml(mcpServers = {}) {
  const entries = Object.entries(mcpServers || {});
  if (!entries.length) {
    return [];
  }

  const lines = [];
  for (const [name, config] of entries) {
    const args = Array.isArray(config.args) ? config.args : [];
    lines.push(`[mcp_servers.${name}]`);
    lines.push(`type = "${tomlString(config.type || 'stdio')}"`);
    lines.push(`command = "${tomlString(config.command || '')}"`);
    lines.push(`args = [${args.map((item) => `"${tomlString(item)}"`).join(', ')}]`);
    if (config.env && typeof config.env === 'object' && Object.keys(config.env).length > 0) {
      lines.push('');
      lines.push(`[mcp_servers.${name}.env]`);
      for (const [key, value] of Object.entries(config.env)) {
        lines.push(`${key} = "${tomlString(value)}"`);
      }
    }
    lines.push('');
  }
  return lines;
}

export function parseSupplierOrderText(text, options = {}) {
  const raw = String(text || '');
  const urls = extractUrls(raw);
  const baseUrl = chooseSupplierBaseUrl(raw, urls);
  if (!baseUrl) {
    throw new Error('订单详情里没有找到请求地址');
  }

  const models = extractModels(raw);
  const keys = extractApiKeys(raw);
  const pool = inferPool(raw);
  const quotaUsd = readNumber(raw, /(\d+(?:\.\d+)?)\s*(?:刀|美元|USD|\$)/i);
  const amountCny = readNumber(raw, /订单金额[:：]?\s*[￥¥]\s*(\d+(?:\.\d+)?)/i);
  const quantity = Math.max(1, Math.round(readNumber(raw, /数量[:：]?\s*(\d+)/i) || keys.length || 1));
  const usdToCny = Number(options.usdToCny ?? 7.2);
  const quotaCents = quotaUsd ? Math.round(quotaUsd * usdToCny * 100) : 1000;
  const providerGroup = inferProviderGroup([...models, baseUrl, raw].join('\n'));
  const parsedUrl = new URL(baseUrl);
  const expiresAt = inferExpiry(raw, pool, options.now);
  const auth = inferAuthConfig(raw);
  const extraHeaders = auth.extraHeaders || {};

  return {
    baseUrl,
    supplierDomain: parsedUrl.hostname,
    supplierFingerprint: `${parsedUrl.hostname}${parsedUrl.pathname}`.replace(/\/+$/, ''),
    pool,
    cardType: pool,
    durationDays: durationDaysForPool(pool),
    quantity,
    quotaUsd,
    amountCny,
    providerGroup,
    models,
    interfaceFormat: 'responses',
    authHeaderName: auth.authHeaderName,
    authHeaderValuePrefix: auth.authHeaderValuePrefix,
    extraHeaders,
    expiresAt,
    keys: keys.map((value) => ({
      value,
      quotaRemaining: quotaCents,
      quotaTotal: quotaCents,
      authHeaderName: auth.authHeaderName,
      authHeaderValuePrefix: auth.authHeaderValuePrefix,
      extraHeaders,
      modelGroup: providerGroup,
      expiresAt,
      cardType: pool,
    })),
  };
}

export function parsePriceText(text, options = {}) {
  const usdToCny = Number(options.usdToCny ?? 7.2);
  const profitMultiplier = Number(options.profitMultiplier ?? 1);
  const safetyCnyPerMillion = Number(options.safetyCnyPerMillion ?? 0);

  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => parsePriceLine(line, { usdToCny, profitMultiplier, safetyCnyPerMillion }))
    .filter(Boolean);
}

export function recommendConnectionPath({ direct, proxy }) {
  if (!direct?.ok && proxy?.ok) return 'proxy';
  if (direct?.ok && !proxy?.ok) return 'direct';
  if (!direct?.ok && !proxy?.ok) return 'unavailable';

  const directScore = connectionScore(direct);
  const proxyScore = connectionScore(proxy);
  return directScore >= proxyScore ? 'direct' : 'proxy';
}

export function chooseNextCredential(credentials, criteria = {}) {
  const allowedPools = criteria.allowedPools?.length
    ? criteria.allowedPools
    : [criteria.pool || 'day'];
  const quotaCost = Number(criteria.quotaCost || 0);
  const model = String(criteria.model || '').trim();
  const modelGroup = normalizeModelGroup(criteria.modelGroup || '');
  const healthy = credentials
    .filter((credential) => allowedPools.includes(credential.pool))
    .filter((credential) => credential.enabled)
    .filter((credential) => credential.status === 'healthy')
    .filter((credential) =>
      quotaCost > 0
        ? Number(credential.quotaRemaining || 0) >= quotaCost
        : Number(credential.quotaRemaining || 0) > 0,
    )
    .filter((credential) => !model || credential.models?.includes(model) || credential.models?.includes('*'))
    .filter((credential) => {
      const credentialGroup = normalizeModelGroup(credential.modelGroup || 'All');
      return modelGroup === 'All' || credentialGroup === 'All' || credentialGroup === modelGroup;
    })
    .sort(compareCredentialsForRotation);

  if (healthy.length === 0) {
    return null;
  }
  return healthy[0];
}

export function inferProviderGroup(value) {
  const text = String(value || '').toLowerCase();
  if (/claude|anthropic/.test(text)) return 'Claude';
  if (/gemini/.test(text)) return 'Gemini';
  if (/deepseek/.test(text)) return 'DeepSeek';
  if (/openai|codex|gpt-|gpt_|gpt\d|chatgpt|responses|dall|image/.test(text)) return 'OpenAI';
  return 'Other';
}

export function normalizeModelGroup(value) {
  const text = String(value || '').trim().toLowerCase();
  if (text === 'claude') return 'Claude';
  if (text === 'openai') return 'OpenAI';
  if (text === 'gemini') return 'Gemini';
  if (text === 'deepseek') return 'DeepSeek';
  if (text === 'other') return 'Other';
  return 'All';
}

export function modelMatchesGroup(model, group) {
  const normalized = normalizeModelGroup(group);
  return normalized === 'All' || inferProviderGroup(model) === normalized;
}

export function poolPriority(pool) {
  const order = new Map([
    ['hour', 0],
    ['day', 1],
    ['month', 2],
    ['unlimited', 3],
    ['default', 4],
  ]);
  return order.get(String(pool || 'default')) ?? 9;
}

export function summarizeModelHealth(snapshot) {
  const latencyMs = Number(snapshot.latencyMs || 0);
  const averageLatencyMs = Number(snapshot.averageLatencyMs || latencyMs || 0);
  const healthyCount = Number(snapshot.healthyCount || (snapshot.ok ? 1 : 0));
  const totalCount = Number(snapshot.totalCount || (healthyCount || 1));
  const status = snapshot.ok
    ? latencyMs > 1200
      ? 'slow'
      : 'healthy'
    : snapshot.maintenance
      ? 'maintenance'
      : 'down';

  return {
    model: snapshot.model,
    label: HEALTH_LABELS[status],
    status,
    latencyText: snapshot.ok && latencyMs > 0 ? `${latencyMs}ms` : '-',
    averageLatencyText: snapshot.ok && averageLatencyMs ? `${averageLatencyMs}ms` : '-',
    successLabel: snapshot.successLabel || `${healthyCount}/${totalCount} 可用`,
    availabilityText: snapshot.availability || `${Number(snapshot.availability7d ?? snapshot.availability_7d ?? 0)}%`,
    availabilityWindow: snapshot.availabilityWindow || '当前库存快照',
    monitorIntervalSeconds: Number(snapshot.monitorIntervalSeconds || 0),
    checkedAt: snapshot.checkedAt,
    replacement: snapshot.replacement || '',
  };
}

function parsePriceLine(line, { usdToCny, profitMultiplier, safetyCnyPerMillion }) {
  const model = normalizeOfficialModelName(line.match(/^([a-zA-Z0-9._:/-]+)/)?.[1]);
  if (!model) return null;

  const currency = /[$＄]/.test(line) ? 'USD' : 'CNY';
  const inputRaw = readLabeledPrice(line, ['input', '输入']);
  const outputRaw = readLabeledPrice(line, ['output', '输出']);
  if (inputRaw === null || outputRaw === null) return null;

  const rate = currency === 'USD' ? usdToCny : 1;
  const inputCostCnyPerMillion = round2(inputRaw * rate);
  const outputCostCnyPerMillion = round2(outputRaw * rate);

  return {
    model,
    currency,
    inputCostCnyPerMillion,
    outputCostCnyPerMillion,
    inputSaleCnyPerMillion: round2(inputCostCnyPerMillion * profitMultiplier + safetyCnyPerMillion),
    outputSaleCnyPerMillion: round2(outputCostCnyPerMillion * profitMultiplier + safetyCnyPerMillion),
    status: 'needs_admin_confirmation',
  };
}

function readLabeledPrice(line, labels) {
  for (const label of labels) {
    const match = line.match(new RegExp(`${label}\\s*[$¥￥]?\\s*(\\d+(?:\\.\\d+)?)`, 'i'));
    if (match) return Number(match[1]);
  }
  return null;
}

function connectionScore(result) {
  const failurePenalty = Number(result.failureRate || 0) * 10000;
  return 10000 - Number(result.p95Ms || 999999) - failurePenalty;
}

function compareCredentialsForRotation(left, right) {
  const poolDelta = poolPriority(left.pool) - poolPriority(right.pool);
  if (poolDelta !== 0) return poolDelta;
  const expiryDelta = expiryTime(left.expiresAt) - expiryTime(right.expiresAt);
  if (expiryDelta !== 0) return expiryDelta;
  return Number(left.latencyMs || 999999) - Number(right.latencyMs || 999999);
}

function expiryTime(value) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.MAX_SAFE_INTEGER;
}

function extractUrls(text) {
  return [...String(text || '').matchAll(/https?:\/\/[^\s，。)）"'<>]+/gi)]
    .map((match) => match[0].replace(/[，。,.)）]+$/, ''))
    .filter(Boolean);
}

function chooseSupplierBaseUrl(text, urls) {
  const labeled = [
    ...String(text || '').matchAll(/(?:API\s*请求地址|请求地址|完整\s*URL|地址)[:：]\s*(https?:\/\/[^\s，。)）"'<>]+)/gi),
  ].map((match) => match[1]);
  const preferredLabeled = labeled.find((url) => isLikelyApiBaseUrl(url));
  if (preferredLabeled) {
    return normalizeBaseUrl(preferredLabeled);
  }
  if (labeled.length > 0) {
    return normalizeBaseUrl(labeled[labeled.length - 1]);
  }

  const preferred = urls.find((url) => isLikelyApiBaseUrl(url));
  return preferred ? normalizeBaseUrl(preferred) : urls[0] ? normalizeBaseUrl(urls[0]) : '';
}

function isLikelyApiBaseUrl(url) {
  return /\/(openai|v1|api|claude|gemini)(\/|$)/i.test(String(url || '')) && !/(dashboard|admin|stats)/i.test(String(url || ''));
}

function extractApiKeys(text) {
  const keys = new Set();
  for (const match of String(text || '').matchAll(/\b(?:cr_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|sk_[A-Za-z0-9_-]{20,})\b/g)) {
    keys.add(match[0]);
  }
  for (const match of String(text || '').matchAll(/(?:密码|卡密|API\s*Key|APIkey|key)[:：]?\s*([A-Za-z0-9_-]{30,})/gi)) {
    keys.add(match[1]);
  }
  return [...keys];
}

function extractModels(text) {
  const modelLine = String(text || '').match(/模型[:：]\s*([^\n\r]+)/);
  if (!modelLine) return [];
  return normalizeOfficialModelList(
    modelLine[1]
      .split(/[、,，/\s]+/)
      .map((item) => item.trim().replace(/模型$/i, ''))
      .filter((item) => /^[a-zA-Z0-9._:-]+$/.test(item)),
  );
}

function inferPool(text) {
  const value = String(text || '').toLowerCase();
  if (/小时|hour/.test(value)) return 'hour';
  if (/日卡|天卡|day/.test(value)) return 'day';
  if (/月卡|month/.test(value)) return 'month';
  if (/不限时|永久|unlimited|余额/.test(value)) return 'unlimited';
  return 'default';
}

function inferExpiry(text, pool, nowValue) {
  const explicit = String(text || '').match(/(?:到期|有效期至|expires?)[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)/i);
  if (explicit) {
    return new Date(explicit[1].replace(/\//g, '-')).toISOString();
  }
  const created = String(text || '').match(/创建时间[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)/);
  const start = created ? new Date(created[1].replace(/\//g, '-')) : new Date(nowValue || Date.now());
  if (Number.isNaN(start.getTime())) return '';
  if (pool === 'hour') {
    start.setUTCHours(start.getUTCHours() + 1);
    return start.toISOString();
  }
  const days = durationDaysForPool(pool);
  if (!days) return '';
  start.setUTCDate(start.getUTCDate() + days);
  return start.toISOString();
}

function durationDaysForPool(pool) {
  if (pool === 'day') return 1;
  if (pool === 'month') return 30;
  return 0;
}

function inferAuthConfig(text) {
  const raw = String(text || '');
  const headerMatch = raw.match(
    /(?:认证字段|认证头|鉴权字段|Auth\s*Header|Header\s*Name|Key\s*Header|请求头字段)[:：]\s*([A-Za-z0-9-]+)/i,
  );
  const authorizationMatch = raw.match(/Authorization\s*:\s*([A-Za-z][A-Za-z0-9._-]*)\s+/i);
  const prefixMatch = raw.match(/(?:认证前缀|鉴权前缀|Auth\s*Prefix|Prefix)[:：]\s*([^\n\r]+)/i);
  const headerName = normalizeHeaderName(
    headerMatch?.[1] || (/x-api-key/i.test(raw) ? 'x-api-key' : 'authorization'),
  );
  const prefixText = String(prefixMatch?.[1] || '').trim();
  let authHeaderValuePrefix = headerName === 'x-api-key' ? '' : 'Bearer';
  if (/^(空|无|none|null|empty|no)$/i.test(prefixText)) {
    authHeaderValuePrefix = '';
  } else if (prefixText) {
    authHeaderValuePrefix = prefixText;
  } else if (authorizationMatch?.[1]) {
    authHeaderValuePrefix = authorizationMatch[1];
  }
  return {
    authHeaderName: headerName,
    authHeaderValuePrefix,
    extraHeaders: extractExtraHeaders(raw),
  };
}

function extractExtraHeaders(text) {
  const headers = {};
  for (const line of String(text || '').split(/\r?\n/)) {
    const match = line.match(/(?:请求头|Header|headers?)[:：]\s*([A-Za-z0-9-]+)\s*[:=]\s*(.+)$/i);
    if (!match) continue;
    const name = normalizeHeaderName(match[1]);
    const value = String(match[2] || '').trim();
    if (!name || !value || name === 'authorization' || name === 'x-api-key') continue;
    if (/(?:sk-|sk_|cr_)[A-Za-z0-9_-]{12,}/.test(value)) continue;
    headers[name] = value;
  }
  return headers;
}

function normalizeHeaderName(value) {
  return String(value || '').trim().toLowerCase();
}

function readNumber(text, pattern) {
  const match = String(text || '').match(pattern);
  return match ? Number(match[1]) : 0;
}

function buildImportRemark({ profile, modelGroup, planExpiresAt }) {
  const parts = [profile.remark, normalizeModelGroup(modelGroup)];
  if (planExpiresAt) {
    parts.push(`到期 ${String(planExpiresAt).slice(0, 10)}`);
  }
  return parts.filter(Boolean).join(' · ');
}

function normalizeAvailableModels(availableModels = [], options = {}) {
  const providedModels = Array.isArray(availableModels) ? availableModels : [];
  const fallbackModel = MODEL_GROUP_FALLBACKS[normalizeModelGroup(options.modelGroup)] || DEFAULT_PUBLIC_MODEL;
  const expandedModels = expandModelPatterns(providedModels, options.modelGroup);
  const models = [
    ...expandedModels,
    options.defaultModel,
    options.model,
    ...(providedModels.length === 0 && !options.defaultModel && !options.model ? [fallbackModel] : []),
  ]
    .map(normalizeOfficialModelName)
    .filter(Boolean);
  return sortModelsByStrength([...new Set(models)]);
}

function expandModelPatterns(models = [], modelGroup) {
  const group = normalizeModelGroup(modelGroup);
  const officialModels = MODEL_GROUP_OFFICIAL_MODELS[group] || [];
  let shouldAddOfficialModels = false;
  const exactModels = [];

  for (const rawModel of models) {
    const model = normalizeOfficialModelName(rawModel);
    if (!model) continue;
    if (model.includes('*')) {
      shouldAddOfficialModels = shouldAddOfficialModels || modelPatternMatchesGroup(model, group);
      continue;
    }
    exactModels.push(model);
  }

  return shouldAddOfficialModels ? [...officialModels, ...exactModels] : exactModels;
}

function modelPatternMatchesGroup(pattern, group) {
  const value = String(pattern || '').toLowerCase();
  if (group === 'OpenAI') return /gpt|dall|image|^o\*/.test(value);
  if (group === 'Claude') return /claude|anthropic/.test(value);
  if (group === 'Gemini') return /gemini/.test(value);
  if (group === 'DeepSeek') return /deepseek/.test(value);
  return false;
}

function chooseDefaultModel({ model, defaultModel, availableModels = [], modelGroup, preferExplicitDefaultModel = false }) {
  const models = normalizeAvailableModels(availableModels, { model, defaultModel, modelGroup });
  const explicitDefault = normalizeOfficialModelName(defaultModel);
  if (preferExplicitDefaultModel && explicitDefault && models.includes(explicitDefault)) {
    return explicitDefault;
  }
  return models[0] || MODEL_GROUP_FALLBACKS[normalizeModelGroup(modelGroup)] || DEFAULT_PUBLIC_MODEL;
}

function sortModelsByStrength(models = []) {
  return [...new Set(models.map(normalizeOfficialModelName).filter(Boolean))].sort((left, right) => {
    const leftRank = MODEL_STRENGTH_ORDER.indexOf(left);
    const rightRank = MODEL_STRENGTH_ORDER.indexOf(right);
    const normalizedLeft = leftRank === -1 ? Number.MAX_SAFE_INTEGER : leftRank;
    const normalizedRight = rightRank === -1 ? Number.MAX_SAFE_INTEGER : rightRank;
    if (normalizedLeft !== normalizedRight) return normalizedLeft - normalizedRight;
    return left.localeCompare(right);
  });
}

function defaultClientFeatures(models = []) {
  return {
    responses: true,
    chatCompletions: true,
    streaming: true,
    images: models.some((item) => /image|dall/i.test(item)),
    toolSearch: true,
    cacheKey: true,
  };
}

function buildCcSwitchCapabilitySummary({ profile, modelList, mcpServers }) {
  const oneClick = [
    '供应商名称',
    'API 请求地址',
    '用户 API Key',
    '默认模型',
    '启用状态',
    '备注',
    '用量查询脚本',
  ];
  if (profile.slug === 'claude') {
    oneClick.push('Opus/Sonnet/Haiku 默认模型');
  }
  const manual = ['MCP 增强包: Claude/Codex/Gemini/OpenCode/Hermes'];
  if (profile.slug === 'openclaw') {
    manual.push('OpenClaw 供应商可导入；CC Switch 当前会忽略 OpenClaw MCP');
  }
  manual.push('Prompt 和 Skill 是 CC Switch 独立资源，需单独导入');
  if (profile.slug === 'codex') {
    manual.push('完整 config.toml', 'Playwright MCP', 'Superpowers MCP', 'open-computer-use MCP');
  }
  if (profile.slug === 'opencode' && modelList.length > 1) {
    manual.push('OpenCode 全模型 provider.models 映射');
  }
  if (!['claude', 'codex', 'gemini', 'opencode', 'openclaw', 'hermes', 'harmes'].includes(profile.slug)) {
    manual.push('客户端专属配置');
  }
  return {
    oneClick,
    manual,
    source: 'CC Switch v1 provider/mcp/prompt/skill deep link',
    mcpSupported: Boolean(mcpServers && Object.keys(mcpServers).length),
  };
}

function buildCcSwitchManualChecklist({ profile, modelList }) {
  const common = [
    '导入后确认供应商卡片显示 Frist-API。',
    `默认模型应为 ${modelList[0] || DEFAULT_PUBLIC_MODEL}。`,
    '右侧用量查询显示已启用，测试脚本返回余额。',
    'Prompt/Skill 不会跟随供应商链接写入；有自定义提示词或 Skill 仓库时按 CC Switch 单独资源导入。',
  ];
  if (profile.slug === 'codex') {
    return [
      ...common,
      '如需浏览器/电脑操作能力，再导入 MCP 或复制完整 config.toml。',
      '终端重启 Codex 后发送“只回复 pong”做连通测试。',
    ];
  }
  if (profile.slug === 'openclaw') {
    return [
      ...common,
      'OpenClaw 供应商可一键导入；MCP 增强包按 CC Switch 当前实现不会写入 OpenClaw。',
    ];
  }
  if (profile.slug === 'opencode') {
    return [
      ...common,
      '如只看到一个模型，复制 OpenCode provider 片段覆盖 provider.frist-api。',
    ];
  }
  if (profile.slug === 'claude') {
    return [
      ...common,
      'Claude Code 使用不带 /v1 的 Base URL。',
      '终端重启 Claude 后发送“只回复 pong”做连通测试。',
    ];
  }
  return common;
}

function defaultCodexMcpServers() {
  return Object.fromEntries(
    Object.entries(CODEX_DEFAULT_MCP_SERVERS).map(([name, config]) => [
      name,
      {
        type: config.type,
        command: config.command,
        args: [...config.args],
      },
    ]),
  );
}

function normalizeCcSwitchMcpApps(apps = []) {
  const allowed = new Set(['claude', 'codex', 'gemini', 'opencode', 'hermes']);
  const values = (Array.isArray(apps) ? apps : String(apps || '').split(','))
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item) => allowed.has(item));
  return [...new Set(values.length ? values : CC_SWITCH_MCP_APPS)];
}

function brandOfficialUrl(baseUrl) {
  const url = new URL(baseUrl);
  return url.origin;
}

function usageBaseUrlFromGateway(baseUrl) {
  const url = new URL(normalizeBaseUrl(baseUrl));
  if (url.pathname === '/v1' || url.pathname.startsWith('/v1/')) {
    url.pathname = '/';
  }
  return url.toString().replace(/\/+$/, '');
}

function normalizeSdkOptions(options = {}) {
  return {
    timeout: Number(options.timeout || 600),
    setCacheKey: options.setCacheKey !== false,
  };
}

function base64EncodeUtf8(value) {
  const text = String(value || '');
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(text, 'utf8').toString('base64');
  }
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return globalThis.btoa(binary);
}

function base64EncodeUtf8UrlSafe(value) {
  return base64EncodeUtf8(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

function clientProfile(target) {
  const normalizedTarget = String(target || '').toLowerCase();
  const profile = CLIENT_PROFILES.get(normalizedTarget);
  if (!profile) {
    throw new Error(`不支持的导入目标: ${target}`);
  }
  return { ...profile };
}

function gatewayBaseUrlForModelGroup(baseUrl, modelGroup) {
  if (normalizeModelGroup(modelGroup) !== 'DeepSeek') {
    return normalizeBaseUrl(baseUrl);
  }
  return 'https://api.deepseek.com/v1';
}

function clientConfigPaths(slug) {
  const configs = {
    codex: {
      macosDir: '~/.codex',
      jsonPath: '~/.codex/auth.json',
      configPath: '~/.codex/config.toml',
      windowsDir: '.codex',
      windowsJsonFile: 'auth.json',
      windowsConfigFile: 'config.toml',
    },
    claude: {
      macosDir: '~/.claude',
      jsonPath: '~/.claude/frist-api.json',
      configPath: '~/.claude/frist-api.toml',
      windowsDir: '.claude',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
    opencode: {
      macosDir: '~/.opencode',
      jsonPath: '~/.opencode/frist-api.json',
      configPath: '~/.opencode/frist-api.toml',
      windowsDir: '.opencode',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
    gemini: {
      macosDir: '~/.gemini',
      jsonPath: '~/.gemini/frist-api.json',
      configPath: '~/.gemini/frist-api.toml',
      windowsDir: '.gemini',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
    openclaw: {
      macosDir: '~/.openclaw',
      jsonPath: '~/.openclaw/frist-api.json',
      configPath: '~/.openclaw/frist-api.toml',
      windowsDir: '.openclaw',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
    hermes: {
      macosDir: '~/.hermes',
      jsonPath: '~/.hermes/frist-api.json',
      configPath: '~/.hermes/frist-api.toml',
      windowsDir: '.hermes',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
    harmes: {
      macosDir: '~/.harmes',
      jsonPath: '~/.harmes/frist-api.json',
      configPath: '~/.harmes/frist-api.toml',
      windowsDir: '.harmes',
      windowsJsonFile: 'frist-api.json',
      windowsConfigFile: 'frist-api.toml',
    },
  };
  return configs[slug] || configs.codex;
}

function buildGuideJsonConfig(config) {
  if (config.targetSlug === 'codex' && config.authJson) {
    return config.authJson;
  }
  if (config.targetSlug === 'claude' && config.authJson) {
    return config.authJson;
  }
  return `${JSON.stringify(
    {
      provider: 'Frist-API',
      api_key_env: 'OPENAI_API_KEY',
      base_url: config.apiRequestUrl,
      model: config.modelName,
      default_model: config.defaultModel || config.modelName,
      models: config.availableModels || [config.modelName],
      wire_api: config.interfaceFormat,
      reasoning_effort: config.reasoningEffort,
      context_window: config.contextWindow,
      auto_compact_token_limit: config.compressionThreshold,
      sdk_options: config.sdkOptions,
      features: config.features || defaultClientFeatures(config.availableModels || [config.modelName]),
    },
    null,
    2,
  )}\n`;
}

function clientBaseUrlForProfile(profile, baseUrl) {
  if (profile.slug !== 'claude') {
    return baseUrl;
  }
  return stripTrailingV1(baseUrl);
}

function stripTrailingV1(baseUrl) {
  const url = new URL(baseUrl);
  url.pathname = url.pathname.replace(/\/v1\/?$/i, '') || '/';
  return url.toString().replace(/\/+$/, '');
}

function interfaceFormatForProfile(profile) {
  if (profile.slug === 'claude') {
    return 'anthropic-messages';
  }
  return profile.wireApi;
}

function authFieldForProfile(profile) {
  if (profile.slug === 'claude') {
    return 'ANTHROPIC_AUTH_TOKEN';
  }
  return 'OPENAI_API_KEY';
}

function compactObject(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ''));
}

function findOptionalModelByPattern(models, pattern) {
  return normalizeAvailableModels(models).find((item) => pattern.test(item)) || '';
}

function buildClaudeDeepLinkModelDefaults(models = []) {
  const defaults = {
    opusModel: findOptionalModelByPattern(models, /opus/i),
    haikuModel: findOptionalModelByPattern(models, /haiku/i),
    sonnetModel: findOptionalModelByPattern(models, /sonnet/i),
  };
  return Object.fromEntries(Object.entries(defaults).filter(([, value]) => Boolean(value)));
}

function ccSwitchAppSlug(profile) {
  return profile.slug === 'harmes' ? 'hermes' : profile.slug;
}

function shellQuote(value) {
  return String(value || '').replace(/'/g, "'\\''");
}

function tomlString(value) {
  return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

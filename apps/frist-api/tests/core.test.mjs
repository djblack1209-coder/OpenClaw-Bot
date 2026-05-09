import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  buildClientConfig,
  buildClientSetupCommands,
  buildCcSwitchImportUrl,
  buildCcSwitchMcpImportUrl,
  chooseNextCredential,
  normalizeClientAvailableModels,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  normalizeBaseUrl,
  parseSupplierOrderText,
  parsePriceText,
  recommendConnectionPath,
  summarizeModelHealth,
} from '../src/core.js';

function decodeUrlSafeBase64(value) {
  const raw = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const padded = raw.padEnd(Math.ceil(raw.length / 4) * 4, '=');
  return Buffer.from(padded, 'base64').toString('utf8');
}

describe('Frist-API core flows', () => {
  it('normalizes supplier base URLs without losing the API version path', () => {
    assert.equal(normalizeBaseUrl(' https://supplier.example.com/v1/ '), 'https://supplier.example.com/v1');
    assert.equal(normalizeBaseUrl('supplier.example.com/api/openai'), 'https://supplier.example.com/api/openai');
  });

  it('cleans legacy supplier model names into the public official catalog names', () => {
    assert.equal(normalizeOfficialModelName('claude-haiku-4-5-20251001'), 'claude-haiku-4-5-20251001');
    assert.equal(normalizeOfficialModelName('claude-opus-4-6'), 'claude-opus-4-6-c');
    assert.equal(normalizeOfficialModelName('claude-opus-4-6-thinking'), 'claude-opus-4-6-thinking-c');
    assert.equal(normalizeOfficialModelName('5.5'), 'gpt-5.5');
    assert.equal(normalizeOfficialModelName('gpt5.5'), 'gpt-5.5');
    assert.equal(normalizeOfficialModelName('image2'), 'gpt-image-2');
    assert.equal(normalizeOfficialModelName('gpt_image_2'), 'gpt-image-2');
    assert.deepEqual(
      normalizeOfficialModelList([
        'claude-haiku-4-5-20251001',
        'claude-sonnet-4-5',
        '5.5',
        'image2',
        'gpt-5.5-c',
        'gpt-5.5',
      ]),
      ['claude-haiku-4-5-20251001', 'claude-sonnet-4-5-c', 'gpt-5.5', 'gpt-image-2', 'gpt-5.5-c'],
    );
  });

  it('builds a CC Switch import URL for every supported client target', () => {
    const targets = ['Claude', 'Codex', 'Gemini', 'OpenCode', 'OpenClaw', 'Hermes', 'Harmes'];

    const urls = targets.map((target) =>
      buildCcSwitchImportUrl({
        target,
        apiKey: 'fk_demo_user_preview',
        baseUrl: 'https://api.frist.example.com/v1/',
        model: 'claude-opus-4-6-thinking',
      }),
    );

    for (const url of urls) {
      assert.match(url, /^ccswitch:\/\/v1\/import\?/);
      const decoded = decodeURIComponent(url);
      const parsed = new URL(url);
      const app = parsed.searchParams.get('app');
      const expectedEndpoint =
        app === 'claude'
          ? 'https://api.frist.example.com'
          : 'https://api.frist.example.com/v1';
      const script = decodeUrlSafeBase64(parsed.searchParams.get('usageScript'));
      const params = [...parsed.searchParams.keys()].sort();

      assert.ok(url.length < 3500, `CC Switch deep link should stay compact, got ${url.length}`);
      assert.match(decoded, /Frist-API/);
      assert.equal(parsed.searchParams.get('resource'), 'provider');
      assert.equal(parsed.searchParams.get('name'), 'Frist-API');
      assert.equal(parsed.searchParams.get('endpoint'), expectedEndpoint);
      assert.equal(parsed.searchParams.get('homepage'), 'https://api.frist.example.com');
      assert.equal(parsed.searchParams.get('apiKey'), 'fk_demo_user_preview');
      assert.equal(parsed.searchParams.get('model'), 'claude-opus-4-6-thinking-c');
      assert.match(decoded, /fk_demo_user_preview/);
      assert.match(decoded, /https:\/\/api\.frist\.example\.com/);
      assert.match(decoded, /claude-opus-4-6-thinking-c/);
    assert.equal(decoded.includes('claude-haiku-4-5-20251001'), false);
    assert.equal(parsed.searchParams.get('config'), null);
    assert.equal(parsed.searchParams.get('settings_config'), null);
    assert.equal(parsed.searchParams.get('availableModels'), null);
    assert.equal(parsed.searchParams.get('usageEnabled'), 'true');
      assert.equal(parsed.searchParams.get('usageApiKey'), 'fk_demo_user_preview');
      assert.equal(parsed.searchParams.get('usageBaseUrl'), 'https://api.frist.example.com');
      assert.equal(parsed.searchParams.get('usageAutoInterval'), '15');
    assert.match(parsed.searchParams.get('usageScript'), /^[A-Za-z0-9_-]+$/);
    assert.match(script, /\/api\/frist\/key-usage/);
    assert.match(script, /Authorization/);
    const usageConfig = Function(`return ${script}`)();
    const extracted = usageConfig.extractor({
      ok: true,
      valid: true,
      plan: '日卡',
      remainingUsd: 1.23,
      usedUsd: 0.45,
      totalUsd: 1.68,
      todayCost: '$0.45',
      monthCost: '$0.45',
      todayCalls: '2 次',
      totalTokens: '128',
    });
    assert.equal(typeof extracted.extra, 'string');
    assert.equal(extracted.extra.includes('今日 $0.45'), true);
    assert.deepEqual(
      params.filter((item) => !['opusModel', 'sonnetModel', 'haikuModel'].includes(item)),
        [
          'apiKey',
          'app',
          'enabled',
          'endpoint',
          'homepage',
          'model',
          'name',
          'notes',
          'resource',
          'usageApiKey',
          'usageAutoInterval',
          'usageBaseUrl',
          'usageEnabled',
          'usageScript',
        ],
      );
    }

    assert.equal(new URL(urls[0]).searchParams.get('app'), 'claude');
    assert.equal(new URL(urls[1]).searchParams.get('app'), 'codex');
    assert.equal(new URL(urls[2]).searchParams.get('app'), 'gemini');
    assert.equal(new URL(urls[3]).searchParams.get('app'), 'opencode');
    assert.equal(new URL(urls[4]).searchParams.get('app'), 'openclaw');
    assert.equal(new URL(urls[5]).searchParams.get('app'), 'hermes');
    assert.equal(new URL(urls[6]).searchParams.get('app'), 'hermes');
  });

  it('matches the current CC Switch provider deep-link contract without oversized config payloads', () => {
    const claudeUrl = new URL(
      buildCcSwitchImportUrl({
        target: 'Claude',
        apiKey: 'fk_ccswitch_claude_preview',
        baseUrl: 'https://api.frist.example.com/v1',
        model: 'gpt-5.5',
        availableModels: ['gpt-5.5', 'claude-opus-4-6-c', 'claude-sonnet-4-5-c'],
        modelGroup: 'OpenAI',
      }),
    );
    const claudeScript = decodeUrlSafeBase64(claudeUrl.searchParams.get('usageScript'));

    assert.ok(claudeUrl.toString().length < 3500);
    assert.equal(claudeUrl.searchParams.get('resource'), 'provider');
    assert.equal(claudeUrl.searchParams.get('app'), 'claude');
    assert.equal(claudeUrl.searchParams.get('name'), 'Frist-API');
    assert.equal(claudeUrl.searchParams.get('endpoint'), 'https://api.frist.example.com');
    assert.equal(claudeUrl.searchParams.get('homepage'), 'https://api.frist.example.com');
    assert.equal(claudeUrl.searchParams.get('enabled'), 'true');
    assert.equal(claudeUrl.searchParams.get('apiKey'), 'fk_ccswitch_claude_preview');
    assert.equal(claudeUrl.searchParams.get('model'), 'gpt-5.5');
    assert.equal(claudeUrl.searchParams.get('opusModel'), 'claude-opus-4-6-c');
    assert.equal(claudeUrl.searchParams.get('sonnetModel'), 'claude-sonnet-4-5-c');
    assert.equal(claudeUrl.searchParams.get('haikuModel'), null);
    assert.equal(claudeUrl.searchParams.get('config'), null);
    assert.equal(claudeUrl.searchParams.get('settings_config'), null);
    assert.match(claudeScript, /\/api\/frist\/key-usage/);
    assert.match(claudeScript, /Authorization/);
    assert.match(claudeScript, /extra: \[/);
    assert.equal(claudeScript.includes('extra: {'), false);

    const codexUrl = new URL(
      buildCcSwitchImportUrl({
        target: 'Codex',
        apiKey: 'fk_ccswitch_codex_preview',
        baseUrl: 'https://api.frist.example.com/v1',
        model: 'gpt-5.3-codex',
        availableModels: ['gpt-5.5', 'gpt-5.3-codex'],
        modelGroup: 'OpenAI',
      }),
    );
    const codexScript = decodeUrlSafeBase64(codexUrl.searchParams.get('usageScript'));

    assert.ok(codexUrl.toString().length < 3500);
    assert.equal(codexUrl.searchParams.get('resource'), 'provider');
    assert.equal(codexUrl.searchParams.get('app'), 'codex');
    assert.equal(codexUrl.searchParams.get('endpoint'), 'https://api.frist.example.com/v1');
    assert.equal(codexUrl.searchParams.get('enabled'), 'true');
    assert.equal(codexUrl.searchParams.get('usageBaseUrl'), 'https://api.frist.example.com');
    assert.match(codexScript, /Authorization/);
    assert.equal(codexUrl.searchParams.get('config'), null);
    assert.equal(codexUrl.searchParams.get('settings_config'), null);
    assert.equal(decodeURIComponent(codexUrl.toString()).includes('supplier.example.com'), false);
    assert.equal(decodeURIComponent(codexUrl.toString()).includes('cr_fake_supplier_secret'), false);
  });

  it('builds copy-ready client config for Codex and OpenCode response-format clients', () => {
    for (const target of ['Codex', 'OpenCode']) {
      const config = buildClientConfig({
        target,
        apiKey: 'fk_test_preview_only',
        baseUrl: 'http://101.43.41.96:5566/v1/',
        model: 'gpt-5.5',
        modelGroup: 'OpenAI',
        planExpiresAt: '2026-05-02T17:24:04.000Z',
      });

      assert.match(config.ccSwitchUrl, /^ccswitch:\/\/v1\/import\?/);
      assert.equal(JSON.parse(config.authJson).OPENAI_API_KEY, 'fk_test_preview_only');
      assert.equal(config.providerName, 'Frist-API');
      assert.equal(config.interfaceFormat, 'responses');
      assert.equal(config.authField, 'OPENAI_API_KEY');
      assert.equal(config.contextWindow, 1_000_000);
      assert.equal(config.compressionThreshold, 900_000);
      assert.equal(config.sdkOptions.timeout, 600);
      assert.equal(config.modelGroup, 'OpenAI');
      assert.match(config.remark, /到期 2026-05-02/);
      assert.match(config.billingNote, /按官方标准计费/);
      assert.match(config.officialUrl, /^http:\/\/101\.43\.41\.96:5566/);
      assert.equal(config.apiRequestUrl, 'http://101.43.41.96:5566/v1');
      assert.equal(config.modelName, 'gpt-5.5');
      assert.match(config.configToml, /model_provider = "custom"/);
      assert.match(config.configToml, /model = "gpt-5\.5"/);
      assert.match(config.configToml, /model_context_window = 1000000/);
      assert.match(config.configToml, /model_auto_compact_token_limit = 900000/);
      assert.match(config.configToml, /wire_api = "responses"/);
      assert.match(config.configToml, /requires_openai_auth = true/);
      assert.match(config.configToml, /name = "Frist-API"/);
      assert.match(config.configToml, /base_url = "http:\/\/101\.43\.41\.96:5566\/v1"/);
      assert.equal(config.targetSlug, target.toLowerCase());

      const decoded = decodeURIComponent(config.ccSwitchUrl);
      const importUrl = new URL(config.ccSwitchUrl);

      assert.equal(decoded.includes('supplier-codex.example.com'), false, '导入链接不能泄露上游请求地址');
      assert.equal(decoded.includes('cr_fake_supplier_secret'), false, '导入链接不能泄露上游 Key');
      assert.equal(importUrl.searchParams.get('config'), null);
      assert.equal(importUrl.searchParams.get('settings_config'), null);

      if (target === 'Codex') {
        assert.match(config.configToml, /\[mcp_servers\.playwright\]/);
        assert.match(config.configToml, /args = \["-y", "@playwright\/mcp@latest"\]/);
        assert.match(config.configToml, /\[mcp_servers\.superpowers\]/);
        assert.match(config.configToml, /args = \["-y", "superpowers-mcp@latest"\]/);
        assert.match(config.configToml, /\[mcp_servers\.open_computer_use\]/);
        assert.match(config.configToml, /args = \["-y", "-p", "open-computer-use@latest", "open-codex-computer-use-mcp"\]/);
        assert.equal(config.mcpServers.playwright.command, 'npx');
        assert.deepEqual(config.mcpServers.playwright.args, ['-y', '@playwright/mcp@latest']);
        assert.equal(config.mcpServers.superpowers.command, 'npx');
        assert.deepEqual(config.mcpServers.superpowers.args, ['-y', 'superpowers-mcp@latest']);
        assert.equal(config.mcpServers.open_computer_use.command, 'npx');
        assert.deepEqual(config.mcpServers.open_computer_use.args, [
          '-y',
          '-p',
          'open-computer-use@latest',
          'open-codex-computer-use-mcp',
        ]);
      } else {
        const providerConfig = JSON.parse(config.openCodeProviderJson).provider['frist-api'];
        assert.doesNotMatch(config.configToml, /\[mcp_servers\./);
        assert.equal(providerConfig.npm, '@ai-sdk/openai-compatible');
        assert.equal(providerConfig.options.baseURL, 'http://101.43.41.96:5566/v1');
        assert.equal(providerConfig.options.apiKey, 'fk_test_preview_only');
        assert.equal(providerConfig.options.timeout, 600);
        assert.equal(providerConfig.options.setCacheKey, true);
        assert.deepEqual(providerConfig.models, { 'gpt-5.5': { name: 'gpt-5.5' } });
      }
    }
  });

  it('exports Claude Code configs that let ChatGPT models run through the Frist gateway', () => {
    const config = buildClientConfig({
      target: 'Claude',
      apiKey: 'fk_claude_openai_preview',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.5',
      availableModels: ['gpt-5.5', 'gpt-5.4-mini'],
      modelGroup: 'OpenAI',
    });
    const importUrl = new URL(config.ccSwitchUrl);
    const claudeJson = JSON.parse(config.authJson);

    assert.equal(config.targetSlug, 'claude');
    assert.equal(config.apiRequestUrl, 'https://api.frist.example.com');
    assert.equal(config.interfaceFormat, 'anthropic-messages');
    assert.equal(config.authField, 'ANTHROPIC_AUTH_TOKEN');
    assert.equal(config.modelName, 'gpt-5.5');
    assert.equal(importUrl.searchParams.get('app'), 'claude');
    assert.equal(importUrl.searchParams.get('endpoint'), 'https://api.frist.example.com');
    assert.equal(importUrl.searchParams.get('config'), null);
    assert.equal(importUrl.searchParams.get('settings_config'), null);
    assert.equal(claudeJson.env.ANTHROPIC_AUTH_TOKEN, 'fk_claude_openai_preview');
    assert.equal(claudeJson.env.ANTHROPIC_BASE_URL, 'https://api.frist.example.com');
    assert.equal(claudeJson.env.ANTHROPIC_MODEL, 'gpt-5.5');
    assert.equal(claudeJson.env.ENABLE_TOOL_SEARCH, 'true');
  });

  it('keeps Claude models importable by Codex through the Responses provider profile', () => {
    const config = buildClientConfig({
      target: 'Codex',
      apiKey: 'fk_codex_claude_preview',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'claude-opus-4-6-c',
      availableModels: ['claude-opus-4-6-c', 'claude-sonnet-4-5-c'],
      modelGroup: 'Claude',
    });
    const importUrl = new URL(config.ccSwitchUrl);

    assert.equal(config.targetSlug, 'codex');
    assert.equal(config.interfaceFormat, 'responses');
    assert.equal(config.authField, 'OPENAI_API_KEY');
    assert.match(config.configToml, /wire_api = "responses"/);
    assert.match(config.configToml, /model = "claude-opus-4-6-c"/);
    assert.match(config.configToml, /base_url = "https:\/\/api\.frist\.example\.com\/v1"/);
    assert.equal(importUrl.searchParams.get('app'), 'codex');
    assert.equal(importUrl.searchParams.get('model'), 'claude-opus-4-6-c');
    assert.equal(importUrl.searchParams.get('config'), null);
  });

  it('builds Codex DeepSeek official API compatible gateway config without committing the real key', () => {
    const config = buildClientConfig({
      target: 'Codex',
      apiKey: 'sk-redacted-deepseek-user-local',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'deepseek-v4-flash',
      availableModels: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-flash', 'deepseek-v4-pro'],
      modelGroup: 'DeepSeek',
    });
    const importUrl = new URL(config.ccSwitchUrl);
    const combined = `${config.authJson}\n${config.configToml}\n${config.ccSwitchUrl}`;
    const usageScript = decodeUrlSafeBase64(importUrl.searchParams.get('usageScript'));

    assert.equal(config.targetSlug, 'codex');
    assert.equal(config.apiRequestUrl, 'https://api.deepseek.com/v1');
    assert.equal(config.modelName, 'deepseek-v4-flash');
    assert.deepEqual(config.availableModels, ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner']);
    assert.match(config.configToml, /base_url = "https:\/\/api\.deepseek\.com\/v1"/);
    assert.equal(JSON.parse(config.authJson).OPENAI_API_KEY, 'sk-redacted-deepseek-user-local');
    assert.equal(importUrl.searchParams.get('endpoint'), 'https://api.deepseek.com/v1');
    assert.equal(importUrl.searchParams.get('usageBaseUrl'), 'https://api.frist.example.com');
    assert.match(usageScript, /\/api\/frist\/key-usage/);
    assert.equal(importUrl.searchParams.get('config'), null);
    assert.equal(combined.includes('sk-redacted-deepseek-user-local'), true);
  });

  it('keeps DeepSeek legacy model names compatible while defaulting new imports to the official v4 family', () => {
    const config = buildClientConfig({
      target: 'Codex',
      apiKey: 'sk-redacted-deepseek-user-local',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'deepseek-chat',
      availableModels: ['deepseek-chat', 'deepseek-reasoner'],
      modelGroup: 'DeepSeek',
    });

    assert.equal(config.apiRequestUrl, 'https://api.deepseek.com/v1');
    assert.equal(config.modelName, 'deepseek-chat');
    assert.deepEqual(config.availableModels, ['deepseek-chat', 'deepseek-reasoner']);
  });

  it('preserves Gemini, Hermes and Harmes client configs while mapping Harmes to the supported CC Switch app id', () => {
    for (const [target, expectedSlug] of [
      ['Gemini', 'gemini'],
      ['Hermes', 'hermes'],
      ['Harmes', 'harmes'],
    ]) {
      const config = buildClientConfig({
        target,
        apiKey: `fk_${expectedSlug}_preview`,
        baseUrl: 'https://api.frist.example.com/v1',
        model: expectedSlug === 'gemini' ? 'gemini-2.5-flash' : 'gpt-5.5',
        modelGroup: expectedSlug === 'gemini' ? 'Gemini' : 'OpenAI',
      });
      const importUrl = new URL(config.ccSwitchUrl);

      assert.equal(config.targetSlug, expectedSlug);
      assert.equal(importUrl.searchParams.get('app'), expectedSlug === 'harmes' ? 'hermes' : expectedSlug);
      assert.match(config.configToml, /wire_api = "responses"/);
    }
  });

  it('exports every available model and keeps the strongest model as the default for Codex and OpenCode', () => {
    for (const target of ['Codex', 'OpenCode']) {
      const config = buildClientConfig({
        target,
        apiKey: 'fk_all_models_preview',
        baseUrl: 'https://api.frist.example.com/v1',
        model: 'gpt-5.4',
        defaultModel: 'gpt-5.5',
        availableModels: ['gpt-5.4', 'gpt-5.5', 'gpt-5.4-mini', 'gpt-5.4-nano', 'gpt-image-2', 'gpt-5.3-codex'],
        modelGroup: 'OpenAI',
      });
      const importUrl = new URL(config.ccSwitchUrl);
      const providerConfig =
        target === 'OpenCode' ? JSON.parse(config.openCodeProviderJson).provider['frist-api'] : null;
      const expectedModels = ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano', 'gpt-image-2', 'gpt-5.3-codex'];

      assert.equal(config.modelName, 'gpt-5.5');
      assert.equal(config.defaultModel, 'gpt-5.5');
      assert.deepEqual(config.availableModels, expectedModels);
      assert.equal(importUrl.searchParams.get('model'), 'gpt-5.5');
      assert.equal(importUrl.searchParams.get('availableModels'), null);
      assert.equal(importUrl.searchParams.get('config'), null);
      if (target === 'OpenCode') {
        assert.equal(providerConfig.npm, '@ai-sdk/openai-compatible');
        assert.equal(providerConfig.options.baseURL, 'https://api.frist.example.com/v1');
        assert.deepEqual(Object.keys(providerConfig.models), expectedModels);
        assert.deepEqual(providerConfig.models['gpt-5.3-codex'], { name: 'gpt-5.3-codex' });
      } else {
        assert.match(config.configToml, /available_models = \["gpt-5\.5", "gpt-5\.4", "gpt-5\.4-mini", "gpt-5\.4-nano", "gpt-image-2", "gpt-5\.3-codex"\]/);
      }
      assert.match(config.configToml, /available_models = \["gpt-5\.5", "gpt-5\.4", "gpt-5\.4-mini", "gpt-5\.4-nano", "gpt-image-2", "gpt-5\.3-codex"\]/);
    }
  });

  it('expands OpenAI wildcard model limits into the visible CC Switch model set', () => {
    const models = normalizeClientAvailableModels(['gpt-*', 'dall-*'], { modelGroup: 'OpenAI' });
    const expectedModels = [
      'gpt-5.5',
      'gpt-5.4',
      'gpt-5.4-mini',
      'gpt-image-2',
      'gpt-image-1.5',
      'gpt-5.3-codex',
      'gpt-4o',
      'gpt-5-codex',
    ];

    assert.deepEqual(models, expectedModels);
  });

  it('builds a copyable OpenCode provider fragment with the full model map', () => {
    const config = buildClientConfig({
      target: 'OpenCode',
      apiKey: 'fk_opencode_full_config',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.5',
      defaultModel: 'gpt-5.5',
      availableModels: ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.3-codex'],
      modelGroup: 'OpenAI',
    });
    const fragment = JSON.parse(config.openCodeProviderJson);
    const provider = fragment.provider['frist-api'];
    const importUrl = new URL(config.ccSwitchUrl);
    const usageScript = decodeUrlSafeBase64(importUrl.searchParams.get('usageScript'));

    assert.deepEqual(Object.keys(fragment), ['provider']);
    assert.equal(provider.npm, '@ai-sdk/openai-compatible');
    assert.equal(provider.options.baseURL, 'https://api.frist.example.com/v1');
    assert.equal(provider.options.apiKey, 'fk_opencode_full_config');
    assert.deepEqual(Object.keys(provider.models), ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.3-codex']);
    assert.deepEqual(provider.models['gpt-5.3-codex'], { name: 'gpt-5.3-codex' });
    assert.equal(importUrl.searchParams.get('usageEnabled'), 'true');
    assert.equal(importUrl.searchParams.get('usageBaseUrl'), 'https://api.frist.example.com');
    assert.equal(importUrl.searchParams.get('config'), null);
    assert.match(usageScript, /remainingUsd/);
    assert.match(usageScript, /extra: \[/);
    assert.equal(usageScript.includes('extra: {'), false);
  });

  it('promotes official Pro aliases when those models are available to the customer', () => {
    const config = buildClientConfig({
      target: 'OpenCode',
      apiKey: 'fk_pro_models_preview',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.5',
      defaultModel: 'gpt-5.5',
      availableModels: ['gpt-5.4-pro', 'gpt-5.5', 'gpt-5.5-pro', 'gpt-image-2'],
      modelGroup: 'OpenAI',
    });

    assert.equal(config.defaultModel, 'gpt-5.5-pro');
    assert.deepEqual(config.availableModels, ['gpt-5.5-pro', 'gpt-5.5', 'gpt-5.4-pro', 'gpt-image-2']);
  });

  it('keeps a server-confirmed customer model as the imported default while preserving stronger choices', () => {
    const config = buildClientConfig({
      target: 'Codex',
      apiKey: 'fk_customer_selected_model',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.4',
      defaultModel: 'gpt-5.4',
      availableModels: ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2'],
      modelGroup: 'OpenAI',
      preferExplicitDefaultModel: true,
    });
    const importUrl = new URL(config.ccSwitchUrl);

    assert.equal(config.modelName, 'gpt-5.4');
    assert.equal(config.defaultModel, 'gpt-5.4');
    assert.deepEqual(config.availableModels, ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-image-2']);
    assert.equal(importUrl.searchParams.get('model'), 'gpt-5.4');
    assert.match(config.configToml, /model = "gpt-5\.4"/);
    assert.match(config.configToml, /available_models = \["gpt-5\.5", "gpt-5\.4", "gpt-5\.4-mini", "gpt-image-2"\]/);
  });

  it('builds macOS and Windows one-click client setup commands without upstream supplier fields', () => {
    const config = buildClientConfig({
      target: 'Codex',
      apiKey: 'fk_user_visible_only',
      baseUrl: 'https://frist-api.101.43.41.96.sslip.io/v1',
      model: 'gpt-5.5',
      modelGroup: 'OpenAI',
      planExpiresAt: '2026-05-02T17:24:04.000Z',
    });
    const setup = buildClientSetupCommands(config);

    assert.match(setup.jsonPath, /\.codex\/auth\.json$/);
    assert.match(setup.configPath, /\.codex\/config\.toml$/);
    assert.match(setup.jsonConfig, /"OPENAI_API_KEY": "fk_user_visible_only"/);
    assert.match(setup.tomlConfig, /name = "Frist-API"/);
    assert.match(setup.tomlConfig, /base_url = "https:\/\/frist-api\.101\.43\.41\.96\.sslip\.io\/v1"/);
    assert.match(setup.macos, /mkdir -p/);
    assert.match(setup.macos, /auth\.json/);
    assert.match(setup.macos, /config\.toml/);
    assert.match(setup.windows, /Join-Path \$env:USERPROFILE/);
    assert.match(setup.windows, /Set-Content -Encoding UTF8/);

    const combined = `${setup.jsonConfig}\n${setup.tomlConfig}\n${setup.macos}\n${setup.windows}`;
    assert.equal(combined.includes('supplier-codex.example.com'), false, '用户教程不能泄露上游请求地址');
    assert.equal(combined.includes('cr_fake_supplier_secret'), false, '用户教程不能泄露上游 Key');
    assert.match(combined, /Frist-API/);
  });

  it('builds CC Switch MCP import and copyable real CLI test commands', () => {
    const mcpUrl = new URL(buildCcSwitchMcpImportUrl());
    const payload = JSON.parse(decodeUrlSafeBase64(mcpUrl.searchParams.get('config')));

    assert.equal(mcpUrl.protocol, 'ccswitch:');
    assert.equal(mcpUrl.searchParams.get('resource'), 'mcp');
    assert.equal(mcpUrl.searchParams.get('apps'), 'claude,codex,gemini,opencode,hermes');
    assert.equal(mcpUrl.searchParams.get('enabled'), 'true');
    assert.deepEqual(Object.keys(payload.mcpServers), ['playwright', 'superpowers', 'open_computer_use']);
    assert.deepEqual(payload.mcpServers.playwright.args, ['-y', '@playwright/mcp@latest']);
    assert.deepEqual(payload.mcpServers.superpowers.args, ['-y', 'superpowers-mcp@latest']);
    assert.deepEqual(payload.mcpServers.open_computer_use.args, [
      '-y',
      '-p',
      'open-computer-use@latest',
      'open-codex-computer-use-mcp',
    ]);

    const claudeConfig = buildClientConfig({
      target: 'Claude',
      apiKey: 'fk_claude_test_command',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'claude-sonnet-4-5-c',
      modelGroup: 'Claude',
    });
    const claudeSetup = buildClientSetupCommands(claudeConfig);
    assert.match(claudeSetup.test, /tmp_settings="\$\(mktemp\)"/);
    assert.match(claudeSetup.test, /cat > "\$tmp_settings" <<'JSON'/);
    assert.match(claudeSetup.test, /claude --bare --no-session-persistence --settings "\$tmp_settings"/);
    assert.doesNotMatch(claudeSetup.test, /--settings '\{/);

    const codexConfig = buildClientConfig({
      target: 'Codex',
      apiKey: 'fk_codex_test_command',
      baseUrl: 'https://api.frist.example.com/v1',
      model: 'gpt-5.4-mini',
      modelGroup: 'OpenAI',
    });
    const codexSetup = buildClientSetupCommands(codexConfig);
    assert.match(codexSetup.test, /CODEX_HOME="\$tmp_home" codex exec/);
    assert.match(codexSetup.test, /--model gpt-5\.4-mini/);
    assert.match(codexSetup.test, /\[mcp_servers\.playwright\]/);
    assert.ok(codexConfig.ccSwitchCapabilities.manual.includes('Prompt 和 Skill 是 CC Switch 独立资源，需单独导入'));
    assert.match(codexConfig.ccSwitchCapabilities.source, /provider\/mcp\/prompt\/skill/);
  });

  it('parses a pasted supplier order page into normalized inventory inputs', () => {
    const parsed = parseSupplierOrderText(
      `
      订单号: LD260502R504J6
      创建时间: 2026-05-01 17:24:04
      商品名称: 【最稳定】CodexAPI 30刀额度 日卡
      订单金额: ￥3.87
      数量: 2
      第1张
      密码：cr_fakecodex_daycard_alpha000000000000000000000000000000000000
      第2张
      密码：cr_fakecodex_daycard_beta0000000000000000000000000000000000000
      模型：gpt-5.4、gpt-5.5-c、gpt-image-2模型
      中转站地址：  https://supplier-codex.example.com/admin-next/api-stats
      配置内容:
      地址: https://supplier-codex.example.com/openai
      APIkey:见发货内容
      `,
      { usdToCny: 7.2 },
    );

    assert.equal(parsed.baseUrl, 'https://supplier-codex.example.com/openai');
    assert.equal(parsed.supplierDomain, 'supplier-codex.example.com');
    assert.equal(parsed.supplierFingerprint, 'supplier-codex.example.com/openai');
    assert.equal(parsed.pool, 'day');
    assert.equal(parsed.cardType, 'day');
    assert.equal(parsed.durationDays, 1);
    assert.equal(parsed.quantity, 2);
    assert.equal(parsed.quotaUsd, 30);
    assert.equal(parsed.amountCny, 3.87);
    assert.equal(parsed.providerGroup, 'OpenAI');
    assert.deepEqual(parsed.models, ['gpt-5.4', 'gpt-5.5-c', 'gpt-image-2']);
    assert.equal(parsed.keys.length, 2);
    assert.equal(parsed.keys[0].value.startsWith('cr_'), true);
    assert.equal(parsed.keys[0].quotaRemaining, 21600);
    assert.equal(parsed.keys[0].quotaTotal, 21600);
    assert.equal(parsed.keys[0].authHeaderName, 'authorization');
    assert.equal(parsed.keys[0].authHeaderValuePrefix, 'Bearer');
  });

  it('cleans non-standard supplier auth fields from pasted order text', () => {
    const parsed = parseSupplierOrderText(
      `
      商品名称: OpenRouter 余额卡
      地址: https://router.example.com/api/v1
      API Key: sk-or-v1-fakecleaned000000000000000000000000000000000000
      认证字段: X-API-Key
      认证前缀: 空
      请求头: HTTP-Referer: https://frist-api.example
      请求头: X-Title: Frist-API
      模型: gpt-5.5
      `,
    );

    assert.equal(parsed.authHeaderName, 'x-api-key');
    assert.equal(parsed.authHeaderValuePrefix, '');
    assert.deepEqual(parsed.extraHeaders, {
      'http-referer': 'https://frist-api.example',
      'x-title': 'Frist-API',
    });
    assert.equal(parsed.keys[0].authHeaderName, 'x-api-key');
    assert.equal(parsed.keys[0].authHeaderValuePrefix, '');
    assert.deepEqual(parsed.keys[0].extraHeaders, parsed.extraHeaders);
  });

  it('parses pasted USD and CNY model prices at official cost by default', () => {
    const draft = parsePriceText(
      `
      claude-sonnet-4 input $3/1M output $15/1M
      gpt-5.5 输入 ¥8/1M 输出 ¥48/1M
      `,
      { usdToCny: 7.2 },
    );

    assert.equal(draft.length, 2);
    assert.deepEqual(draft[0], {
      model: 'claude-sonnet-4',
      currency: 'USD',
      inputCostCnyPerMillion: 21.6,
      outputCostCnyPerMillion: 108,
      inputSaleCnyPerMillion: 21.6,
      outputSaleCnyPerMillion: 108,
      status: 'needs_admin_confirmation',
    });
    assert.equal(draft[1].model, 'gpt-5.5');
    assert.equal(draft[1].currency, 'CNY');
    assert.equal(draft[1].inputSaleCnyPerMillion, 8);
    assert.equal(draft[1].outputSaleCnyPerMillion, 48);
  });

  it('still supports explicit operator markup when the admin enters one', () => {
    const draft = parsePriceText(
      `
      claude-sonnet-4 input $3/1M output $15/1M
      gpt-5.5 输入 ¥8/1M 输出 ¥48/1M
      `,
      { usdToCny: 7.2, profitMultiplier: 1.35, safetyCnyPerMillion: 0.2 },
    );

    assert.equal(draft.length, 2);
    assert.deepEqual(draft[0], {
      model: 'claude-sonnet-4',
      currency: 'USD',
      inputCostCnyPerMillion: 21.6,
      outputCostCnyPerMillion: 108,
      inputSaleCnyPerMillion: 29.36,
      outputSaleCnyPerMillion: 146,
      status: 'needs_admin_confirmation',
    });
    assert.equal(draft[1].model, 'gpt-5.5');
    assert.equal(draft[1].currency, 'CNY');
    assert.equal(draft[1].inputSaleCnyPerMillion, 11);
    assert.equal(draft[1].outputSaleCnyPerMillion, 65);
  });

  it('chooses proxy only when it beats direct on success and latency', () => {
    assert.equal(
      recommendConnectionPath({
        direct: { ok: true, p95Ms: 420, failureRate: 0.01 },
        proxy: { ok: true, p95Ms: 760, failureRate: 0.02 },
      }),
      'direct',
    );

    assert.equal(
      recommendConnectionPath({
        direct: { ok: false, p95Ms: 0, failureRate: 1 },
        proxy: { ok: true, p95Ms: 680, failureRate: 0.03 },
      }),
      'proxy',
    );
  });

  it('removes exhausted day-card credentials and falls through to the next healthy key', () => {
    const picked = chooseNextCredential(
      [
        { id: 'day-1', pool: 'day', enabled: true, quotaRemaining: 0, status: 'exhausted', latencyMs: 120 },
        { id: 'day-2', pool: 'day', enabled: true, quotaRemaining: 50000, status: 'healthy', latencyMs: 240 },
        { id: 'month-1', pool: 'month', enabled: true, quotaRemaining: 999999, status: 'healthy', latencyMs: 90 },
      ],
      { pool: 'day' },
    );

    assert.equal(picked.id, 'day-2');
  });

  it('prioritizes expiring pools before unlimited inventory while keeping exhausted keys out', () => {
    const picked = chooseNextCredential(
      [
        { id: 'unlimited-fast', pool: 'unlimited', enabled: true, quotaRemaining: 999999, status: 'healthy', latencyMs: 20 },
        { id: 'month', pool: 'month', enabled: true, quotaRemaining: 3000, status: 'healthy', latencyMs: 60 },
        { id: 'hour-empty', pool: 'hour', enabled: true, quotaRemaining: 0, status: 'exhausted', latencyMs: 10 },
        { id: 'day-expiring', pool: 'day', enabled: true, quotaRemaining: 1200, status: 'healthy', latencyMs: 200 },
      ],
      { allowedPools: ['hour', 'day', 'month', 'unlimited'], quotaCost: 10 },
    );

    assert.equal(picked.id, 'day-expiring');
  });

  it('summarizes model health without leaking channels or raw keys to users', () => {
    const summary = summarizeModelHealth({
      model: 'gpt-5.5',
      ok: false,
      latencyMs: 0,
      checkedAt: '2026-05-01T20:00:00Z',
      replacement: 'gpt-5.4',
      channelId: 42,
      keySuffix: 'sk-demo-hidden',
    });

    assert.deepEqual(summary, {
      model: 'gpt-5.5',
      label: '暂不可用',
      status: 'down',
      latencyText: '-',
      averageLatencyText: '-',
      successLabel: '0/1 可用',
      availabilityText: '0%',
      availabilityWindow: '当前库存快照',
      monitorIntervalSeconds: 0,
      checkedAt: '2026-05-01T20:00:00Z',
      replacement: 'gpt-5.4',
    });
    assert.equal(Object.hasOwn(summary, 'channelId'), false);
    assert.equal(Object.hasOwn(summary, 'keySuffix'), false);
  });

  it('summarizes channel monitor metrics without exposing upstream implementation details', () => {
    const summary = summarizeModelHealth({
      model: 'gpt-5.5',
      ok: true,
      latencyMs: 90,
      averageLatencyMs: 995,
      healthyCount: 2,
      totalCount: 3,
      availability: '66.7%',
      availabilityWindow: '当前库存快照',
      monitorIntervalSeconds: 60,
      channel: 'OpenAI 可用线路 2/3',
      endpoint: 'https://supplier.example.com/v1',
      rawKey: 'sk-upstream-secret',
    });

    assert.deepEqual(summary, {
      model: 'gpt-5.5',
      label: '正常',
      status: 'healthy',
      latencyText: '90ms',
      averageLatencyText: '995ms',
      successLabel: '2/3 可用',
      availabilityText: '66.7%',
      availabilityWindow: '当前库存快照',
      monitorIntervalSeconds: 60,
      checkedAt: undefined,
      replacement: '',
    });
    assert.equal(Object.hasOwn(summary, 'endpoint'), false);
    assert.equal(Object.hasOwn(summary, 'rawKey'), false);
  });

  it('summarizes unknown real latency as pending instead of a fake millisecond value', () => {
    const summary = summarizeModelHealth({
      model: 'gpt-5.5',
      ok: true,
      latencyMs: 0,
      averageLatencyMs: 0,
      healthyCount: 1,
      totalCount: 1,
      monitorIntervalSeconds: 60,
      channel: '日卡号池',
    });

    assert.equal(summary.latencyText, '-');
    assert.equal(summary.averageLatencyText, '-');
    assert.equal(summary.monitorIntervalSeconds, 60);
  });
});

describe('Frist-API user dashboard boundaries', () => {
  const page = [
    readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'),
  ].join('\n');

  it('keeps admin-only replenishment and pricing content out of the user page', () => {
    for (const forbidden of ['管理端', '补号助手', '价格解析', '价格草稿', '号源归类', '上游号商', '新增渠道', 'refresh_token']) {
      assert.equal(page.includes(forbidden), false, `${forbidden} 不应该出现在用户端`);
    }
  });

  it('keeps only the customer-facing dashboard jobs visible', () => {
    for (const required of ['余额', '模型消耗', '异常消耗检测', '连通', 'API', '充值', 'CC Switch']) {
      assert.equal(page.includes(required), true, `${required} 应该出现在用户端`);
    }
  });

  it('removes non-clickable sidebar headings and old dense dashboard copy', () => {
    for (const forbidden of [
      '控制台',
      'API 与用量',
      '模型与渠道',
      '充值与订购',
      '客户工作台',
      '先看能不能用',
      '三步开始使用',
      '现在可以做什么',
      '按需展开',
      '模型消耗详情',
      '查看全部状态',
      '官方状态',
      '端点 Ping',
      '历史 60 次',
      '使用文档',
      '客户端下载',
    ]) {
      assert.equal(page.includes(forbidden), false, `${forbidden} 不应该出现在极简用户端`);
    }
  });

  it('deduplicates the model usage entry so customers only see one path for consumption data', () => {
    assert.equal(page.includes('使用统计'), false, '用户导航不应该同时出现“使用统计”和“模型消耗”两个重复入口');
  });

  it('moves registration and login to the top-right account area instead of API management', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const topbar = userHtml.match(/<header class="topbar">[\s\S]*?<\/header>/)?.[0] || '';
    const apiPanel = userHtml.match(/<section class="view-panel" data-view="api"[\s\S]*?<section class="view-panel" data-view="usage"/)?.[0] || '';

    for (const required of ['data-auth-toggle', 'data-auth-panel', 'data-register-email', 'data-login-account', 'data-owner-shortcut']) {
      assert.equal(topbar.includes(required), true, `${required} 应该位于右上角账户区`);
    }
    for (const required of ['data-password-reset-request', 'data-password-reset-confirm']) {
      assert.equal(topbar.includes(required), true, `${required} 应该支持忘记密码闭环`);
    }

    for (const forbidden of ['data-register-email', 'data-register-password', 'data-verify-code', 'data-login-account']) {
      assert.equal(apiPanel.includes(forbidden), false, `${forbidden} 不应该出现在 API 管理页面`);
    }
  });

  it('makes redemption cards the primary billing shell and leaves a Xianyu purchase slot', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    for (const required of [
      'data-xianyu-purchase-link',
      'data-route="redeem"',
      'data-billing-exchange-code',
      'data-payment-feedback',
    ]) {
      assert.equal(userHtml.includes(required), true, `${required} 应该出现在充值页面`);
    }
    assert.equal(userHtml.includes('data-payment-method="wechat_native"'), false, '用户端不再把微信商户支付作为主入口');
    assert.equal(userHtml.includes('data-payment-method="alipay_precreate"'), false, '用户端不再把支付宝商户支付作为主入口');
  });

  it('uses an inroi-style customer workbench with compact navigation and fixed metrics', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

    for (const required of [
      'data-workspace-layout',
      'data-workspace-rail',
      'data-console-board',
      'data-focus-metrics',
      'data-hero-primary-import',
      'data-action-dock',
      'data-provider-summary',
      'data-usage-focus',
    ]) {
      assert.equal(userHtml.includes(required), true, `${required} 应该成为用户首页的降噪结构`);
    }

    const focusMetricCount = (userHtml.match(/class="focus-metric/g) || []).length;
    const headerBrandCount = (userHtml.match(/<strong>Frist-API<\/strong>/g) || []).length;
    assert.ok(focusMetricCount >= 4, '用户首屏应该只保留最关键的余额、Key、今日和成功率指标');
    assert.equal((userHtml.match(/data-hero-primary-import/g) || []).length, 1, '首屏只保留一个主行动入口');
    assert.equal(headerBrandCount, 1, '顶部品牌 Logo 应该是全站唯一可见品牌块，侧栏不再重复');
    assert.equal(userHtml.includes('Frist Gateway'), true, '首屏需要保留简短品牌信号');
    assert.equal(userHtml.includes('Commercial API Gateway'), false, '首屏不再使用冗长英文营销文案');
    assert.equal(userHtml.includes('月卡 Pro'), false, '公开页面初始 HTML 不应该闪现演示套餐');
    assert.equal(userHtml.includes('¥428.90'), false, '公开页面初始 HTML 不应该闪现演示消耗金额');
    assert.equal(userHtml.includes('>DJ<'), false, '公开页面初始 HTML 不应该闪现演示用户缩写');
  });

  it('keeps public pages free of bundled mock dashboard data and legacy model aliases', () => {
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const combined = `${userHtml}\n${appScript}`;

    assert.equal(existsSync(new URL('../src/data.js', import.meta.url)), false, '生产源码不应保留网页 mock 数据文件');
    assert.equal(appScript.includes("from './data.js'"), false, '用户网页不能再导入 mock 数据模块');
    assert.equal(appScript.includes('fallbackDashboard'), false, '用户网页不能构造演示 dashboard 兜底');
    assert.equal(appScript.includes('store.load()'), false, '服务不可用时不能从 New-API/demo store 兜底');
    assert.equal(appScript.includes('applyRecharge('), false, '公开充值不能本地伪造成功');
    assert.equal(appScript.includes('createCustomerKey('), false, '创建 Key 不能本地伪造成功');
    assert.equal(appScript.includes('registerCustomer('), false, '注册不能本地伪造成功');
    assert.equal(combined.includes('data-pay-demo'), false, '充值按钮不能再保留 demo 命名');
    assert.equal(combined.includes('fake-field'), false, '用户流程图不能再保留 fake 命名');
    assert.equal(combined.includes('fk-live-demo'), false, '用户端不能生成演示 API Key');
    assert.equal(combined.includes('claude-haiku'), false, '用户端默认模型不能再保留非规范 Claude Haiku 命名');
    assert.equal(combined.includes('claude-haiku-4-5-20251001'), false, '用户页面不能展示历史非规范模型名');
  });

  it('uses a compact customer rail for the main workbench routes', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const actionDock = userHtml.match(/<nav[^>]*class="action-dock workspace-nav"[\s\S]*?<\/nav>/)?.[0] || '';

    assert.equal(userHtml.includes('data-workspace-rail'), true, '用户端应该保留紧凑工作台导航');
    assert.equal(userHtml.includes('data-rail-toggle'), true, '移动端工作台导航应该有折叠按钮');
    assert.equal(userHtml.includes('data-rail-current'), true, '移动端折叠按钮应该展示当前页面');
    assert.equal(userHtml.includes('aria-controls="workspace-nav"'), true, '折叠按钮应该绑定导航区域');
    assert.equal(actionDock.includes('id="workspace-nav"'), true, '导航区域应该提供稳定 id 供折叠按钮引用');
    for (const required of ['首页', 'API Key', 'CC Switch', '测试', '资料']) {
      assert.equal(actionDock.includes(required), true, `${required} 应该保留为工作台直接入口`);
    }
    for (const hidden of ['充值', '邀请', '教程']) {
      assert.equal(actionDock.includes(hidden), false, `${hidden} 入口当前应从工作台隐藏`);
    }
    assert.equal(userHtml.includes('data-import-fallback'), true, 'CC Switch 协议无响应时要有复制降级提示');
    assert.equal(actionDock.includes('>01<'), false, '侧栏导航不应该再显示数字编号');
    assert.equal(actionDock.includes('>13<'), false, '侧栏导航不应该再显示数字编号');

    assert.equal(actionDock.includes('is-priority-path'), false, '首页和 CC Switch 不应再用特殊大框样式');

    for (const link of actionDock.match(/<a [^>]+>/g) || []) {
      assert.match(link, /href="#[^"]+"/, '每个快捷入口都要有 hash 跳转');
      assert.match(link, /data-route="[^"]+"/, '每个快捷入口都要有统一 data-route 钩子');
    }

    assert.equal(userHtml.includes('nav-group'), false, '用户端不再使用不可点击分组标题');
    assert.equal(userHtml.includes('nav-divider'), false, '用户端不再用文字分组隔断堆密度');
    const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
    assert.equal(styles.includes('rgba(19, 35, 30, 0.95)'), false);
    assert.equal(styles.includes('position: sticky'), true);
    assert.equal(styles.includes('.workspace-rail:not(.is-open) .action-dock.workspace-nav'), true);
    assert.equal(styles.includes('.provider-models'), false, '通道面板不应再保留模型分类标签样式');
  });

  it('keeps internal Claude route ids out of visible playground labels', () => {
    const appScript = readFileSync(new URL('../src/app.js', import.meta.url), 'utf8');

    assert.equal(appScript.includes('function publicModelMetaLabel'), true);
    assert.equal(appScript.includes('const metaLabel = publicModelMetaLabel(item.model, item.family);'), true);
    assert.equal(
      appScript.includes('<small title="${escapeHtml(item.model)}">${escapeHtml(item.family)} · ${escapeHtml(metaLabel)}</small>'),
      true,
    );
    assert.equal(
      appScript.includes('<p title="${escapeHtml(selected.model)}">${escapeHtml(summary.label)} · ${escapeHtml(selectedMeta)}</p>'),
      true,
    );
    assert.equal(
      appScript.includes("<small>${escapeHtml(item.family)}${publicModelLabel(item.model) === item.model ? '' : ` · ${escapeHtml(item.model)}`}</small>"),
      false,
      '测试台副标题不应该继续把 claude-*-c 这类内部路由 ID 作为可见模型名',
    );
  });

  it('ships the visual hooks for the Tabcode-style console skin, loading states and reduced-motion friendly animation', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const scriptsAndStyles = [
      readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'),
      readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8'),
    ].join('\n');

    for (const required of [
      'renderProviderSummary',
      'renderClientConfig',
      'handleImportProtocolFallback',
      'copyTextToClipboard',
      'data-copy-auth-json',
      'data-copy-config-toml',
      'workspace-layout',
      'workspace-rail',
      'workspace-content',
      'console-metrics',
      'data-design-system="tabcode-console"',
      'renderLoadingState',
      'renderSkeletonRows',
      'renderEmptyState',
      'userFacingLoadError',
      '离线',
      'data-server-recovery',
      'data-retry-dashboard',
      'handleRetryDashboard',
      "signalAction('success')",
      "return '已连接'",
      "return '后端暂不可用'",
      'aria-current',
      'skeleton-row',
      'empty-row--stack',
      'table-empty',
      'model-picker-panel',
      'playground-model-row',
      'selected-model-panel',
      'playground-diagnostics',
      'Tabcode console layer',
      '--workspace: #0b0d10',
      '#ffffff',
      '--primary: #8fb5ff',
      'grid-template-columns: 160px minmax(0, 1fr)',
      'height: 54px',
      'border-radius: 14px',
      'content-visibility: auto',
      '@media (prefers-reduced-motion: reduce)',
      'Tabcode contrast guard',
      '20260509-mobile-channel',
      'body[data-design-system="tabcode-console"] .back-home',
      'body[data-design-system="tabcode-console"] .terminal-head .text-action',
      'body[data-design-system="tabcode-console"] .chat-delete',
      'officialModelTemplateByGroup',
      'gpt-5.4-mini',
      'gpt-image-2',
      'gpt-5.3-codex',
      'normalizeClientAvailableModels(config?.availableModels',
      'data-trend-tooltip',
      'trend-chart__hit',
      'activeTrendPoint',
      'updateActiveTrendPoint',
      'transform: rotate(34deg)',
      'background: #101114',
      'position: sticky',
      'top: 68px',
      'background: var(--primary)',
    ]) {
      assert.equal(`${userHtml}\n${scriptsAndStyles}`.includes(required), true, `${required} 应该支撑用户端 Tabcode 控制台、状态和动效`);
    }

    assert.equal(scriptsAndStyles.includes('transition: all'), false, '用户端动画不能使用 transition: all');
    assert.equal(scriptsAndStyles.includes('appleStatusPulse'), false, '旧 Apple 状态动效不应再存在');
    assert.match(scriptsAndStyles, /body\[data-design-system="tabcode-console"\] \.primary-action,[\s\S]*?color: #07080a;/);
    assert.match(scriptsAndStyles, /body\[data-design-system="tabcode-console"\] \.back-home,[\s\S]*?color: var\(--ink\);/);
    assert.doesNotMatch(
      scriptsAndStyles,
      /body\[data-design-system="tabcode-console"\] \.brand-mark \{[^}]*?background: var\(--paper\);/,
      'Tabcode 皮肤不能替换 Frist-API 原品牌 Logo',
    );
    assert.match(
      userHtml,
      /<span class="brand-mark" aria-hidden="true">[\s\S]*?<i><\/i>[\s\S]*?<b><\/b>[\s\S]*?<\/span>/,
      '用户端 Logo 应该保留红白斜切品牌图形，不应退回单字母占位',
    );
    assert.doesNotMatch(userHtml, /<span class="brand-mark" aria-hidden="true">F<\/span>/, '用户端 Logo 不应显示 F 字母占位');
    assert.match(
      scriptsAndStyles,
      /body\[data-design-system="tabcode-console"\] \.action-dock\.workspace-nav a\.is-active \{[\s\S]*?background: transparent;/,
      '导航当前项应使用细线和文字提示，不应再出现大块背景',
    );
    assert.match(
      scriptsAndStyles,
      /body\[data-design-system="tabcode-console"\] \.export-model-chip[\s\S]*?color: var\(--ink\);/,
      '导出模型 chip 必须在深色控制台里清晰可读',
    );
    assert.equal(userHtml.includes('aria-busy="true"'), true, '主内容初始加载阶段应该向辅助技术声明 busy');
  });
});

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  buildClientConfig,
  buildClientSetupCommands,
  buildCcSwitchImportUrl,
  chooseNextCredential,
  normalizeOfficialModelList,
  normalizeOfficialModelName,
  normalizeBaseUrl,
  parseSupplierOrderText,
  parsePriceText,
  recommendConnectionPath,
  summarizeModelHealth,
} from '../src/core.js';

describe('Frist-API core flows', () => {
  it('normalizes supplier base URLs without losing the API version path', () => {
    assert.equal(normalizeBaseUrl(' https://supplier.example.com/v1/ '), 'https://supplier.example.com/v1');
    assert.equal(normalizeBaseUrl('supplier.example.com/api/openai'), 'https://supplier.example.com/api/openai');
  });

  it('cleans legacy supplier model names into the public official catalog names', () => {
    assert.equal(normalizeOfficialModelName('claude-haiku-4-5-20251001'), 'claude-sonnet-4-5-c');
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
      ['claude-sonnet-4-5-c', 'gpt-5.5', 'gpt-image-2', 'gpt-5.5-c'],
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
      const expectedFormat = app === 'claude' ? 'anthropic-messages' : 'responses';
      assert.match(decoded, /Frist-API/);
      assert.equal(parsed.searchParams.get('resource'), 'provider');
      assert.equal(parsed.searchParams.get('name'), 'Frist-API');
      assert.equal(parsed.searchParams.get('endpoint'), expectedEndpoint);
      assert.equal(parsed.searchParams.get('homepage'), 'https://api.frist.example.com');
      assert.equal(parsed.searchParams.get('apiKey'), 'fk_demo_user_preview');
      assert.equal(parsed.searchParams.get('model'), 'claude-opus-4-6-thinking-c');
      assert.equal(parsed.searchParams.get('configFormat'), 'json');
      assert.match(decoded, /providerName=Frist-API/);
      assert.match(decoded, /officialUrl=/);
      assert.equal(parsed.searchParams.get('apiRequestUrl'), expectedEndpoint);
      assert.match(decoded, /modelName=claude-opus-4-6-thinking-c/);
      assert.match(decoded, /fk_demo_user_preview/);
      assert.match(decoded, /https:\/\/api\.frist\.example\.com/);
      assert.match(decoded, /claude-opus-4-6-thinking-c/);
      assert.equal(decoded.includes('claude-haiku-4-5-20251001'), false);
      assert.equal(parsed.searchParams.get('wireApi'), expectedFormat);
      assert.match(decoded, /authJson=/);
      assert.match(decoded, /configToml=/);
    }

    assert.equal(new URL(urls[0]).searchParams.get('app'), 'claude');
    assert.equal(new URL(urls[1]).searchParams.get('app'), 'codex');
    assert.equal(new URL(urls[2]).searchParams.get('app'), 'gemini');
    assert.equal(new URL(urls[3]).searchParams.get('app'), 'opencode');
    assert.equal(new URL(urls[4]).searchParams.get('app'), 'openclaw');
    assert.equal(new URL(urls[5]).searchParams.get('app'), 'hermes');
    assert.equal(new URL(urls[6]).searchParams.get('app'), 'harmes');
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
      const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));

      assert.equal(decoded.includes('supplier-codex.example.com'), false, '导入配置不能泄露上游请求地址');
      assert.equal(decoded.includes('cr_fake_supplier_secret'), false, '导入配置不能泄露上游 Key');
      assert.match(decoded, /providerName=Frist-API/);
      assert.match(decoded, /officialUrl=http:\/\/101\.43\.41\.96:5566/);
      assert.match(decoded, /interfaceFormat=responses/);
      assert.match(decoded, /authField=OPENAI_API_KEY/);
      assert.match(decoded, /contextWindow=1000000/);
      assert.match(decoded, /compressionThreshold=900000/);
      assert.match(decoded, /reasoningEffort=xhigh/);

      if (target === 'Codex') {
        assert.match(config.configToml, /\[mcp_servers\.playwright\]/);
        assert.match(config.configToml, /args = \["-y", "@playwright\/mcp@latest"\]/);
        assert.match(config.configToml, /\[mcp_servers\.superpowers\]/);
        assert.match(config.configToml, /args = \["-y", "superpowers-mcp@latest"\]/);
        assert.match(config.configToml, /\[mcp_servers\.open_computer_use\]/);
        assert.match(config.configToml, /args = \["-y", "-p", "open-computer-use@latest", "open-codex-computer-use-mcp"\]/);
        assert.equal(importUrl.searchParams.get('mcpEnabled'), 'true');
        assert.equal(providerConfig.codex.mcpServers.playwright.command, 'npx');
        assert.deepEqual(providerConfig.codex.mcpServers.playwright.args, ['-y', '@playwright/mcp@latest']);
        assert.equal(providerConfig.codex.mcpServers.superpowers.command, 'npx');
        assert.deepEqual(providerConfig.codex.mcpServers.superpowers.args, ['-y', 'superpowers-mcp@latest']);
        assert.equal(providerConfig.codex.mcpServers.open_computer_use.command, 'npx');
        assert.deepEqual(providerConfig.codex.mcpServers.open_computer_use.args, [
          '-y',
          '-p',
          'open-computer-use@latest',
          'open-codex-computer-use-mcp',
        ]);
      } else {
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
    const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));
    const claudeJson = JSON.parse(config.authJson);

    assert.equal(config.targetSlug, 'claude');
    assert.equal(config.apiRequestUrl, 'https://api.frist.example.com');
    assert.equal(config.interfaceFormat, 'anthropic-messages');
    assert.equal(config.authField, 'ANTHROPIC_AUTH_TOKEN');
    assert.equal(config.modelName, 'gpt-5.5');
    assert.equal(importUrl.searchParams.get('app'), 'claude');
    assert.equal(importUrl.searchParams.get('endpoint'), 'https://api.frist.example.com');
    assert.equal(importUrl.searchParams.get('apiFormat'), 'anthropic-messages');
    assert.equal(importUrl.searchParams.get('developerModeRequired'), 'true');
    assert.equal(importUrl.searchParams.get('routeOpenAiModels'), 'true');
    assert.equal(claudeJson.env.ANTHROPIC_AUTH_TOKEN, 'fk_claude_openai_preview');
    assert.equal(claudeJson.env.ANTHROPIC_BASE_URL, 'https://api.frist.example.com');
    assert.equal(claudeJson.env.ANTHROPIC_MODEL, 'gpt-5.5');
    assert.equal(claudeJson.env.ENABLE_TOOL_SEARCH, 'true');
    assert.equal(providerConfig.env.ANTHROPIC_AUTH_TOKEN, 'fk_claude_openai_preview');
    assert.equal(providerConfig.env.ANTHROPIC_BASE_URL, 'https://api.frist.example.com');
    assert.equal(providerConfig.provider.wireApi, 'anthropic-messages');
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
    const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));

    assert.equal(config.targetSlug, 'codex');
    assert.equal(config.interfaceFormat, 'responses');
    assert.equal(config.authField, 'OPENAI_API_KEY');
    assert.match(config.configToml, /wire_api = "responses"/);
    assert.match(config.configToml, /model = "claude-opus-4-6-c"/);
    assert.match(config.configToml, /base_url = "https:\/\/api\.frist\.example\.com\/v1"/);
    assert.equal(importUrl.searchParams.get('app'), 'codex');
    assert.equal(importUrl.searchParams.get('modelGroup'), 'Claude');
    assert.equal(importUrl.searchParams.get('routeClaudeModels'), 'true');
    assert.equal(providerConfig.codex.defaultModel, 'claude-opus-4-6-c');
    assert.deepEqual(providerConfig.codex.availableModels, ['claude-opus-4-6-c', 'claude-sonnet-4-5-c']);
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
    const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));
    const combined = `${config.authJson}\n${config.configToml}\n${config.ccSwitchUrl}`;

    assert.equal(config.targetSlug, 'codex');
    assert.equal(config.apiRequestUrl, 'https://api.deepseek.com/v1');
    assert.equal(config.modelName, 'deepseek-v4-flash');
    assert.deepEqual(config.availableModels, ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner']);
    assert.match(config.configToml, /base_url = "https:\/\/api\.deepseek\.com\/v1"/);
    assert.equal(JSON.parse(config.authJson).OPENAI_API_KEY, 'sk-redacted-deepseek-user-local');
    assert.equal(importUrl.searchParams.get('endpoint'), 'https://api.deepseek.com/v1');
    assert.equal(importUrl.searchParams.get('modelGroup'), 'DeepSeek');
    assert.equal(providerConfig.provider.endpoint, 'https://api.deepseek.com/v1');
    assert.equal(providerConfig.env.OPENAI_BASE_URL, 'https://api.deepseek.com/v1');
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

  it('preserves Gemini, Hermes and Harmes as distinct CC Switch import targets', () => {
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
      const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));

      assert.equal(config.targetSlug, expectedSlug);
      assert.equal(importUrl.searchParams.get('app'), expectedSlug);
      assert.equal(providerConfig.provider.app, expectedSlug);
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
      const providerConfig = JSON.parse(Buffer.from(importUrl.searchParams.get('config'), 'base64').toString('utf8'));
      const expectedModels = ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano', 'gpt-image-2', 'gpt-5.3-codex'];

      assert.equal(config.modelName, 'gpt-5.5');
      assert.equal(config.defaultModel, 'gpt-5.5');
      assert.deepEqual(config.availableModels, expectedModels);
      assert.equal(importUrl.searchParams.get('defaultModel'), 'gpt-5.5');
      assert.equal(importUrl.searchParams.get('default_model'), 'gpt-5.5');
      assert.deepEqual(JSON.parse(importUrl.searchParams.get('models')), expectedModels);
      assert.deepEqual(JSON.parse(importUrl.searchParams.get('availableModels')), expectedModels);
      assert.deepEqual(JSON.parse(importUrl.searchParams.get('available_models')), expectedModels);
      assert.deepEqual(JSON.parse(importUrl.searchParams.get('modelList')), expectedModels);
      if (target === 'OpenCode') {
        assert.equal(providerConfig.npm, '@ai-sdk/openai-compatible');
        assert.equal(providerConfig.options.baseURL, 'https://api.frist.example.com/v1');
        assert.deepEqual(Object.keys(providerConfig.models), expectedModels);
        assert.deepEqual(providerConfig.models['gpt-5.3-codex'], { name: 'gpt-5.3-codex' });
      } else {
        assert.deepEqual(providerConfig.models, expectedModels);
        assert.deepEqual(providerConfig.availableModels, expectedModels);
        assert.deepEqual(providerConfig.available_models, expectedModels);
        assert.deepEqual(providerConfig.modelList, expectedModels);
        assert.deepEqual(providerConfig.provider.models, expectedModels);
        assert.deepEqual(providerConfig.provider.availableModels, expectedModels);
        assert.deepEqual(providerConfig.provider.available_models, expectedModels);
        assert.deepEqual(providerConfig.provider.modelList, expectedModels);
        assert.equal(providerConfig.defaultModel, 'gpt-5.5');
        assert.equal(providerConfig.default_model, 'gpt-5.5');
        assert.equal(providerConfig.provider.defaultModel, 'gpt-5.5');
        assert.equal(providerConfig.provider.default_model, 'gpt-5.5');
        assert.equal(providerConfig.codex.defaultModel, 'gpt-5.5');
        assert.deepEqual(providerConfig.codex.availableModels, expectedModels);
        assert.equal(providerConfig.features.responses, true);
        assert.equal(providerConfig.features.streaming, true);
        assert.equal(providerConfig.features.toolSearch, true);
      }
      assert.match(config.configToml, /available_models = \["gpt-5\.5", "gpt-5\.4", "gpt-5\.4-mini", "gpt-5\.4-nano", "gpt-image-2", "gpt-5\.3-codex"\]/);
    }
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

    assert.deepEqual(Object.keys(fragment), ['provider']);
    assert.equal(provider.npm, '@ai-sdk/openai-compatible');
    assert.equal(provider.options.baseURL, 'https://api.frist.example.com/v1');
    assert.equal(provider.options.apiKey, 'fk_opencode_full_config');
    assert.deepEqual(Object.keys(provider.models), ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.3-codex']);
    assert.deepEqual(provider.models['gpt-5.3-codex'], { name: 'gpt-5.3-codex' });
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
      checkedAt: '2026-05-01T20:00:00Z',
      replacement: 'gpt-5.4',
    });
    assert.equal(Object.hasOwn(summary, 'channelId'), false);
    assert.equal(Object.hasOwn(summary, 'keySuffix'), false);
  });
});

describe('Frist-API user dashboard boundaries', () => {
  const page = [
    readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'),
  ].join('\n');

  it('keeps admin-only replenishment and pricing content out of the user page', () => {
    for (const forbidden of ['管理端', '补号助手', '价格解析', '价格草稿', '号源归类', '上游号商', '新增渠道']) {
      assert.equal(page.includes(forbidden), false, `${forbidden} 不应该出现在用户端`);
    }
  });

  it('keeps only the customer-facing dashboard jobs visible', () => {
    for (const required of ['余额', '模型消耗', '连通', 'API', '充值', 'CC Switch']) {
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

    for (const required of ['data-auth-toggle', 'data-auth-panel', 'data-register-email', 'data-login-account']) {
      assert.equal(topbar.includes(required), true, `${required} 应该位于右上角账户区`);
    }
    for (const required of ['data-password-reset-request', 'data-password-reset-confirm']) {
      assert.equal(topbar.includes(required), true, `${required} 应该支持忘记密码闭环`);
    }

    for (const forbidden of ['data-register-email', 'data-register-password', 'data-verify-code', 'data-login-account']) {
      assert.equal(apiPanel.includes(forbidden), false, `${forbidden} 不应该出现在 API 管理页面`);
    }
  });

  it('keeps real payment method choices visible in the billing shell', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    for (const required of [
      'data-payment-method="manual_pending"',
      'data-payment-method="wechat_native"',
      'data-payment-method="alipay_precreate"',
      'data-payment-feedback',
    ]) {
      assert.equal(userHtml.includes(required), true, `${required} 应该出现在充值页面`);
    }
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
    assert.ok(focusMetricCount >= 6, '用户首屏应该补足请求、消费、Token 和性能指标');
    assert.equal((userHtml.match(/data-hero-primary-import/g) || []).length, 1, '首屏只保留一个主行动入口');
    assert.equal(headerBrandCount, 1, '顶部品牌 Logo 应该是全站唯一可见品牌块，侧栏不再重复');
    assert.equal(userHtml.includes('Commercial API Gateway'), true, '首屏需要保留商业化品牌信号');
    assert.equal(userHtml.includes('Commercial API Gateway'), true, '首屏需要变成操作工作台而不是营销大横幅');
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
    const actionDock = userHtml.match(/<nav class="action-dock workspace-nav"[\s\S]*?<\/nav>/)?.[0] || '';

    assert.equal(userHtml.includes('data-workspace-rail'), true, '用户端应该保留紧凑工作台导航');
    for (const required of ['仪表盘', 'API Key', '充值', 'CC Switch', '广场']) {
      assert.equal(actionDock.includes(required), true, `${required} 应该保留为工作台直接入口`);
    }
    assert.equal(actionDock.includes('>01<'), false, '侧栏导航不应该再显示数字编号');
    assert.equal(actionDock.includes('>13<'), false, '侧栏导航不应该再显示数字编号');

    assert.match(actionDock, /class="is-priority-path"[\s\S]*?CC Switch/, '导入入口应该成为工作台里的主路径');

    for (const link of actionDock.match(/<a [^>]+>/g) || []) {
      assert.match(link, /href="#[^"]+"/, '每个快捷入口都要有 hash 跳转');
      assert.match(link, /data-route="[^"]+"/, '每个快捷入口都要有统一 data-route 钩子');
    }

    assert.equal(userHtml.includes('nav-group'), false, '用户端不再使用不可点击分组标题');
    assert.equal(userHtml.includes('nav-divider'), false, '用户端不再用文字分组隔断堆密度');
    assert.equal(readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8').includes('rgba(19, 35, 30, 0.95)'), false);
    assert.equal(readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8').includes('position: sticky'), false);
  });

  it('ships the visual hooks for the Refero-style console skin, loading states and reduced-motion friendly animation', () => {
    const userHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
    const scriptsAndStyles = [
      readFileSync(new URL('../src/app.js', import.meta.url), 'utf8'),
      readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8'),
    ].join('\n');

    for (const required of [
      'renderProviderSummary',
      'renderClientConfig',
      'data-copy-auth-json',
      'data-copy-config-toml',
      'workspace-layout',
      'workspace-rail',
      'console-metrics',
      'data-design-system="refero-hyperstudio"',
      'renderLoadingState',
      'renderSkeletonRows',
      'renderEmptyState',
      'userFacingLoadError',
      '后端暂不可用，当前显示空数据',
      'data-server-recovery',
      'data-retry-dashboard',
      'handleRetryDashboard',
      'aria-current',
      'skeleton-row',
      'empty-row--stack',
      'table-empty',
      'model-picker-panel',
      'playground-model-row',
      'selected-model-panel',
      'playground-diagnostics',
      'Refero Hyperstudio skin',
      '#e7c59a',
      '#050505',
      'panelReveal',
      '@media (prefers-reduced-motion: reduce)',
    ]) {
      assert.equal(`${userHtml}\n${scriptsAndStyles}`.includes(required), true, `${required} 应该支撑用户端深色控制台、状态和动效`);
    }

    assert.equal(scriptsAndStyles.includes('transition: all'), false, '用户端动画不能使用 transition: all');
    assert.equal(userHtml.includes('aria-busy="true"'), true, '主内容初始加载阶段应该向辅助技术声明 busy');
  });
});

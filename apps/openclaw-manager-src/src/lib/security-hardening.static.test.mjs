import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('Gateway Token 只有配置层一个强随机来源', () => {
  const config = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
  const shell = read('apps/openclaw-manager-src/src-tauri/src/utils/shell.rs');
  const clawbot = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot.rs');
  const file = read('apps/openclaw-manager-src/src-tauri/src/utils/file.rs');
  const tokenGenerator = config.slice(
    config.indexOf('fn generate_token_with'),
    config.indexOf('fn generate_token()'),
  );
  const tokenEnum = config.slice(
    config.indexOf('enum GatewayTokenConfig'),
    config.indexOf('fn parse_secret_ref'),
  );
  const tokenResolver = config.slice(
    config.indexOf('fn resolve_gateway_token'),
    config.indexOf('fn gateway_token_env_from_resolved'),
  );

  assert.doesNotMatch(shell, /DEFAULT_GATEWAY_TOKEN|openclaw-manager-local-token/);
  assert.match(shell, /get_gateway_token_env_override/);
  assert.match(shell, /GatewayTokenEnv::RemoveOverride[\s\S]*?env_remove\("OPENCLAW_GATEWAY_TOKEN"\)/);
  assert.match(shell, /GatewayTokenEnv::Inherit => \{\}/);
  assert.match(config, /generate_token_with\(getrandom::getrandom\)/);
  assert.match(config, /已拒绝生成 Gateway Token/);
  assert.match(tokenEnum, /SecretRef \{ source: String, id: String \}/);
  assert.match(tokenResolver, /parse_secret_ref\(value\)/);
  assert.match(config, /http:\/\/localhost:18789\/#token=/);
  assert.doesNotMatch(config, /localhost:18789\/\?token=/);
  assert.match(config, /OPENCLAW_CONFIG_LOCK/);
  assert.match(config, /ExclusiveFileLock::acquire/);
  assert.match(file, /flock\(file\.as_raw_fd\(\), LOCK_EX \| LOCK_NB\)/);
  assert.match(config, /preserve_existing_gateway_auth/);
  assert.match(config, /insert\("remote"\.to_string\(\), Value::Object\(remote\.clone\(\)\)\)/);
  assert.match(config, /GatewayTokenConfig::OtherAuth[\s\S]*?GatewayTokenEnv::RemoveOverride/);
  for (const path of [
    '/gateway/auth/token',
    '/gateway/auth/password',
    '/gateway/remote/token',
    '/gateway/remote/password',
    '/secrets/providers',
  ]) {
    assert.match(config, new RegExp(path.replaceAll('/', '\\/')));
  }
  assert.match(clawbot, /Gateway 操作委托给统一服务控制器/);
  assert.match(clawbot, /label: "ai\.openclaw\.gateway"[\s\S]*?launcher_script: None/);
  assert.doesNotMatch(tokenGenerator, /SystemTime::now|std::process::id|栈上变量/);
});

test('敏感环境变量在 Rust IPC 边界固定脱敏且掩码不可回写', () => {
  const config = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
  const getEnv = config.slice(
    config.indexOf('pub async fn get_env_value'),
    config.indexOf('pub async fn save_env_value'),
  );

  for (const key of [
    'LLM_API_KEY',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'DEEPSEEK_API_KEY',
    'REDIS_URL',
    'TELEGRAM_BOT_TOKEN',
  ]) {
    assert.match(config, new RegExp(`"${key}"`));
  }
  assert.match(getEnv, /redact_env_value/);
  assert.match(config, /const SENSITIVE_ENV_MASK: &str = "\*{12}"/);
  assert.match(config, /固定脱敏标记不能作为真实环境变量值保存/);
});

test('完整配置和渠道凭据在进入 WebView 前递归脱敏', () => {
  const config = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
  const settings = read('apps/openclaw-manager-src/src/components/Settings/index.tsx');
  const getConfig = config.slice(
    config.indexOf('pub async fn get_config'),
    config.indexOf('pub async fn save_config'),
  );
  const saveConfig = config.slice(
    config.indexOf('pub async fn save_config'),
    config.indexOf('pub async fn get_env_value'),
  );

  assert.match(getConfig, /redact_config_for_webview/);
  assert.match(saveConfig, /save_webview_config/);
  assert.match(config, /preserve_webview_config_sections/);
  for (const section of ['agents', 'channels', 'messages', 'plugins', 'secrets', 'skills', 'talk', 'tools']) {
    assert.match(config, new RegExp(`"${section}"`));
  }
  assert.match(config, /pointer\("\/models\/providers"\)/);
  assert.match(config, /restore_masked_config_values/);
  assert.match(config, /channel_obj\["enabled"\] = json!\(channel\.enabled\)/);
  assert.match(settings, /openclaw-safe-diagnostic-config\.json/);
  assert.doesNotMatch(settings, /a\.download = 'openclaw-config\.json'/);
});

test('Provider、模型和渠道配置始终在跨进程事务内读改写', () => {
  const config = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
  const commandSection = (start, end) => config.slice(config.indexOf(start), config.indexOf(end));
  const configTransactions = [
    ['pub async fn save_provider', 'pub async fn delete_provider'],
    ['pub async fn delete_provider', 'pub async fn set_primary_model'],
    ['pub async fn set_primary_model', 'pub async fn add_available_model'],
    ['pub async fn add_available_model', 'pub async fn remove_available_model'],
    ['pub async fn remove_available_model', '// ============ 旧版兼容'],
  ];

  for (const [start, end] of configTransactions) {
    const section = commandSection(start, end);
    assert.match(section, /mutate_openclaw_config\(\|config\|/);
    assert.doesNotMatch(section, /let mut config = load_openclaw_config/);
  }
  const providerSave = commandSection('pub async fn save_provider', 'pub async fn delete_provider');
  assert.match(providerSave, /merge_provider_config/);
  assert.match(providerSave, /current_provider/);

  for (const [start, end] of [
    ['pub async fn save_channel_config', 'pub async fn clear_channel_config'],
    ['pub async fn clear_channel_config', '// ============ 飞书插件管理'],
  ]) {
    const section = commandSection(start, end);
    assert.match(section, /mutate_openclaw_config_and_env\(\|config\|/);
  }
  const channelRead = commandSection('pub async fn get_channels_config', 'pub async fn save_channel_config');
  assert.match(channelRead, /OPENCLAW_CONFIG_LOCK/);
  assert.match(channelRead, /ConfigFileLock::acquire\(\)/);
  assert.doesNotMatch(config, /let _ = file::(?:set|remove)_env_value/);
});

test('停止服务只能使用管理器 PID 记录并核验进程身份', () => {
  const service = read('apps/openclaw-manager-src/src-tauri/src/commands/service.rs');
  const clawbot = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot.rs');
  const bots = read('apps/openclaw-manager-src/src/components/Bots/index.tsx');
  const systemRouter = read('packages/clawbot/src/api/routers/system.py');

  assert.match(service, /read_managed_gateway_pid/);
  assert.match(service, /verify_managed_gateway_pid/);
  assert.match(service, /GATEWAY_LAUNCHD_LABEL: &str = "ai\.openclaw\.gateway"/);
  assert.match(service, /\.args\(\["disable", &state\.target\]\)/);
  assert.match(service, /start_gateway_launchd/);
  assert.match(service, /\["kickstart", "-k", &state\.target\]/);
  assert.match(service, /OpenClaw CLI 预检失败/);
  assert.match(service, /GATEWAY_OPERATION_LOCK/);
  assert.doesNotMatch(service, /get_pids_on_port|kill_process\(/);
  assert.match(clawbot, /fallback_process_marker/);
  assert.match(clawbot, /verify_fallback_process/);
  assert.match(clawbot, /prepare_managed_script/);
  assert.match(clawbot, /reap_fallback_process/);
  assert.match(clawbot, /MANAGED_SERVICE_OPERATION_LOCK/);
  assert.match(clawbot, /ai\.openclaw\.cc-seller-bridge/);
  assert.match(clawbot, /format_env_assignment/);
  assert.match(clawbot, /wait\\n/);
  assert.doesNotMatch(clawbot, /IBKR_DEFAULT_STOP_CMD|get_default_ibkr_stop_cmd/);
  assert.doesNotMatch(clawbot, /find_pid_by_port/);
  assert.match(bots, /api\.getManagedServicesStatus\(\)/);
  assert.match(bots, /api\.controlManagedService/);
  assert.doesNotMatch(systemRouter, /@router\.post\("\/system\/services\/\{service_id\}\/(?:start|stop)"\)/);
  const shell = read('apps/openclaw-manager-src/src-tauri/src/utils/shell.rs');
  assert.doesNotMatch(shell, /apps\/openclaw-cli/);
});

test('敏感 IPC 不记录参数、返回值或错误对象', () => {
  const core = read('apps/openclaw-manager-src/src/lib/tauri-core.ts');
  const config = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
  const sensitiveCommands = [
    'get_config',
    'save_config',
    'get_env_value',
    'save_env_value',
    'get_or_create_gateway_token',
    'get_dashboard_url',
    'save_provider',
    'save_channel_config',
    'get_logs',
    'get_managed_service_logs',
    'control_managed_service',
    'control_all_managed_services',
    'clawbot_api_social_draft_final_confirm',
    'clawbot_api_social_draft_publish',
  ];

  for (const command of sensitiveCommands) {
    assert.match(core, new RegExp(`'${command}'`), `${command} 必须进入敏感命令集合`);
  }
  assert.match(core, /if \(sensitive\) \{\s*apiLogger\.apiCall\(cmd\);/);
  assert.match(core, /if \(sensitive\) \{\s*apiLogger\.apiResponse\(cmd\);/);
  assert.match(core, /if \(sensitive\) \{\s*apiLogger\.apiError\(cmd\);/);
  assert.doesNotMatch(config, /\[保存配置\] 配置内容/);
  assert.doesNotMatch(config, /\[AI 配置\] 配置内容/);
});

test('IBKR shell 字段和 WebView 文件写权限均已关闭', () => {
  const core = read('apps/openclaw-manager-src/src/lib/tauri-core.ts');
  const constants = read('apps/openclaw-manager-src/src/components/ControlCenter/constants.ts');
  const clawbot = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot.rs');
  const capability = read('apps/openclaw-manager-src/src-tauri/capabilities/default.json');

  assert.doesNotMatch(core, /IBKR_(START|STOP)_CMD/);
  assert.doesNotMatch(constants, /IBKR_(START|STOP)_CMD/);
  assert.doesNotMatch(clawbot, /IBKR_(START|STOP)_CMD/);
  assert.doesNotMatch(capability, /fs:(default|allow-read|allow-write)/);
});

test('实盘卖出必须二次确认、阻止重复提交并验证业务成功', async () => {
  const portfolio = read('apps/openclaw-manager-src/src/components/Portfolio/index.tsx');
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');

  assert.match(portfolio, /<ConfirmDialog[\s\S]*destructive/);
  assert.match(portfolio, /pendingSell/);
  assert.match(portfolio, /sellSubmittingRef\.current/);
  assert.doesNotMatch(portfolio, /onClick=\{[^}]*handleSell\(h\.symbol,\s*h\.quantity\)/);
  assert.match(api, /assertTradingSellSucceeded/);

  const { assertTradingSellSucceeded } = await import('./trading-sell.ts');
  assert.throws(
    () => assertTradingSellSucceeded({ success: false, message: 'IBKR 未连接' }),
    /IBKR 未连接/,
  );
  assert.throws(() => assertTradingSellSucceeded({}), /后端未确认订单提交/);
  assert.throws(() => assertTradingSellSucceeded(null), /后端未确认订单提交/);
  assert.equal(
    assertTradingSellSucceeded({ success: true, order_id: '42' }).order_id,
    '42',
  );
});

test('危险确认框默认聚焦取消并声明标准对话框语义', () => {
  const dialog = read('apps/openclaw-manager-src/src/components/ui/confirm-dialog.tsx');

  assert.match(dialog, /const cancelRef = useRef/);
  assert.match(dialog, /destructive \? cancelRef\.current : confirmRef\.current/);
  assert.match(dialog, /role="dialog"/);
  assert.match(dialog, /aria-modal="true"/);
  assert.match(dialog, /aria-labelledby=\{titleId\}/);
});

test('调度任务切换携带目标状态并采用后端确认结果', () => {
  const scheduler = read('apps/openclaw-manager-src/src/components/Scheduler/index.tsx');

  assert.match(scheduler, /const nextEnabled = !currentEnabled/);
  assert.match(scheduler, /toggle\?enabled=\$\{nextEnabled\}/);
  assert.match(scheduler, /enabled: result\.enabled/);
  assert.match(scheduler, /toggleTask\(task\.id, task\.enabled\)/);
  assert.match(scheduler, /String\(task\.cron \|\| '—'\)\.padEnd\(16\)/);
});

test('MCP 商店只展示受管目录且不暴露伪 stdio 启停入口', () => {
  const store = read('apps/openclaw-manager-src/src/components/Store/index.tsx');
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');
  const ipc = read('apps/openclaw-manager-src/src/lib/tauri-ipc.ts');
  const mcp = read('apps/openclaw-manager-src/src-tauri/src/commands/mcp.rs');

  assert.match(ipc, /getMcpPlugins[\s\S]*get_mcp_plugins/);
  assert.match(api, /getMcpPlugins: ipc\.getMcpPlugins/);
  assert.match(store, /api\.getMcpPlugins\(\)/);
  assert.doesNotMatch(store, /api\.getSkillsStatus\(\)/);
  assert.doesNotMatch(store, /handleMcpToggle/);
  assert.doesNotMatch(ipc, /start_mcp_plugin|stop_mcp_plugin|get_mcp_plugin_status/);
  assert.match(mcp, /MANAGED_MCP_PACKAGES/);
  assert.doesNotMatch(mcp, /mcp_servers\.json|Command::new|Stdio::null/);
  assert.doesNotMatch(ipc, /MCPPlugin[\s\S]{0,500}(command\?|args\?|env\?)/);
});

test('Assistant 流式请求可取消且不会把取消误报为故障', () => {
  const assistant = read('apps/openclaw-manager-src/src/components/Assistant/index.tsx');
  const zh = read('apps/openclaw-manager-src/src/i18n/zh-CN.ts');
  const en = read('apps/openclaw-manager-src/src/i18n/en-US.ts');

  assert.match(assistant, /requestControllerRef = useRef<AbortController/);
  assert.match(assistant, /signal: controller\.signal/);
  assert.match(assistant, /const handleCancel = useCallback/);
  assert.match(assistant, /controller\.signal\.aborted/);
  assert.match(assistant, /onClick=\{loading \? handleCancel : handleSend\}/);
  assert.match(assistant, /loading \? <Square/);
  assert.match(zh, /'assistant\.stopReply': '停止回复'/);
  assert.match(en, /'assistant\.stopReply': 'Stop reply'/);
});

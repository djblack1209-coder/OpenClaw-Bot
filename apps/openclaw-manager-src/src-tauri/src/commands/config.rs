use crate::models::{
    AIConfigOverview, ChannelConfig, ConfiguredModel, ConfiguredProvider, ModelConfig,
    OfficialProvider, SuggestedModel,
};
use crate::utils::{file, platform, shell};
use log::{debug, error, info, warn};
use serde_json::{json, Value};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::Command;
use tauri::command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentitySettings {
    pub bot_name: String,
    pub user_name: String,
    pub timezone: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecuritySettings {
    pub enable_whitelist: bool,
    pub allow_file_access: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub identity: IdentitySettings,
    pub security: SecuritySettings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectContext {
    pub project_name: String,
    pub project_base_dir: String,
    pub workspace_dir: String,
    pub config_dir: String,
    pub config_file: String,
    pub env_file: String,
    pub identity_file: String,
    pub user_file: String,
    pub settings_file: String,
}

pub(crate) fn get_home_dir() -> Result<String, String> {
    if let Ok(home) = std::env::var("HOME") {
        if !home.is_empty() {
            return Ok(home);
        }
    }
    dirs::home_dir()
        .map(|p| p.display().to_string())
        .ok_or_else(|| "无法获取用户 Home 目录".to_string())
}

fn get_default_workspace_path() -> Result<String, String> {
    // 优先从环境变量 OPENCLAW_PROJECT_DIR 获取项目根目录，支持部署到任意路径
    if let Ok(dir) = std::env::var("OPENCLAW_PROJECT_DIR") {
        if !dir.is_empty() {
            return Ok(format!("{}/apps/openclaw", dir));
        }
    }
    let home = get_home_dir()?;
    Ok(format!("{}/Desktop/OpenClaw Bot/apps/openclaw", home))
}

fn infer_workspace_path(config: &Value) -> Result<String, String> {
    if let Some(workspace) = config
        .pointer("/agents/defaults/workspace")
        .and_then(|v| v.as_str())
    {
        return Ok(workspace.to_string());
    }
    get_default_workspace_path()
}

fn derive_project_base_dir(workspace_dir: &str) -> String {
    let trimmed = workspace_dir.trim_end_matches('/');
    // workspace is now at apps/openclaw, so go up two levels to get project root
    if let Some(parent) = std::path::Path::new(trimmed).parent() {
        if let Some(grandparent) = parent.parent() {
            return grandparent.display().to_string();
        }
        return parent.display().to_string();
    }
    workspace_dir.to_string()
}

fn get_manager_settings_path(project_base_dir: &str) -> String {
    format!("{}/apps/openclaw/.manager/settings.json", project_base_dir)
}

fn get_project_context_from_config(config: &Value) -> Result<ProjectContext, String> {
    let workspace_dir = infer_workspace_path(config)?;
    let project_base_dir = derive_project_base_dir(&workspace_dir);
    let config_dir = platform::get_config_dir();
    let config_file = platform::get_config_file_path();
    let env_file = platform::get_env_file_path();
    let identity_file = format!("{}/IDENTITY.md", workspace_dir);
    let user_file = format!("{}/USER.md", workspace_dir);
    let settings_file = get_manager_settings_path(&project_base_dir);

    Ok(ProjectContext {
        project_name: "OpenClaw Bot".to_string(),
        project_base_dir,
        workspace_dir,
        config_dir,
        config_file,
        env_file,
        identity_file,
        user_file,
        settings_file,
    })
}

fn load_manager_settings(settings_path: &str) -> Result<Value, String> {
    if !file::file_exists(settings_path) {
        return Ok(json!({}));
    }

    let raw = file::read_file(settings_path)
        .map_err(|e| format!("读取本地设置文件失败: {}", e))?;
    serde_json::from_str(&raw).map_err(|e| format!("解析本地设置文件失败: {}", e))
}

fn default_app_settings() -> AppSettings {
    AppSettings {
        identity: IdentitySettings {
            bot_name: "OpenClaw Bot".to_string(),
            user_name: "Boss".to_string(),
            timezone: "Asia/Shanghai".to_string(),
        },
        security: SecuritySettings {
            enable_whitelist: false,
            allow_file_access: true,
        },
    }
}

fn update_markdown_field(content: &str, field: &str, value: &str) -> Option<String> {
    let mut lines: Vec<String> = content.lines().map(|l| l.to_string()).collect();
    let mut changed = false;

    for line in &mut lines {
        if line.trim_start().starts_with(&format!("- **{}:**", field)) {
            *line = format!("- **{}:** {}", field, value);
            changed = true;
            break;
        }
    }

    if changed {
        Some(lines.join("\n"))
    } else {
        None
    }
}

fn sync_workspace_identity_files(context: &ProjectContext, settings: &AppSettings) -> Result<(), String> {
    if file::file_exists(&context.identity_file) {
        let content = file::read_file(&context.identity_file)
            .map_err(|e| format!("读取 IDENTITY.md 失败: {}", e))?;
        let mut updated = content.clone();

        if let Some(next) = update_markdown_field(&updated, "Name", &settings.identity.bot_name) {
            updated = next;
        }
        if let Some(next) = update_markdown_field(&updated, "Timezone", &settings.identity.timezone) {
            updated = next;
        }

        if updated != content {
            file::write_file(&context.identity_file, &updated)
                .map_err(|e| format!("写入 IDENTITY.md 失败: {}", e))?;
        }
    }

    if file::file_exists(&context.user_file) {
        let content = file::read_file(&context.user_file)
            .map_err(|e| format!("读取 USER.md 失败: {}", e))?;
        let mut updated = content.clone();

        if let Some(next) = update_markdown_field(&updated, "What to call them", &settings.identity.user_name) {
            updated = next;
        }
        if let Some(next) = update_markdown_field(&updated, "Timezone", &settings.identity.timezone) {
            updated = next;
        }

        if updated != content {
            file::write_file(&context.user_file, &updated)
                .map_err(|e| format!("写入 USER.md 失败: {}", e))?;
        }
    }

    Ok(())
}

/// 获取 openclaw.json 配置
fn load_openclaw_config() -> Result<Value, String> {
    let config_path = platform::get_config_file_path();
    
    if !file::file_exists(&config_path) {
        return Ok(json!({}));
    }
    
    let content =
        file::read_file(&config_path).map_err(|e| format!("读取配置文件失败: {}", e))?;
    
    serde_json::from_str(&content).map_err(|e| format!("解析配置文件失败: {}", e))
}

/// 保存 openclaw.json 配置
fn save_openclaw_config(config: &Value) -> Result<(), String> {
    let config_path = platform::get_config_file_path();
    
    let content =
        serde_json::to_string_pretty(config).map_err(|e| format!("序列化配置失败: {}", e))?;
    
    file::write_file(&config_path, &content).map_err(|e| format!("写入配置文件失败: {}", e))
}

pub(crate) fn mask_secret(value: &str) -> String {
    if value.len() > 8 {
        format!("{}...{}", &value[..4], &value[value.len() - 4..])
    } else {
        "****".to_string()
    }
}

fn parse_models_from_provider(
    provider_name: &str,
    provider_config: &Value,
    primary_model: &Option<String>,
) -> Vec<ConfiguredModel> {
    provider_config
        .get("models")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|m| {
                    let id = m.get("id")?.as_str()?.to_string();
                    let name = m
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or(&id)
                        .to_string();
                    let full_id = format!("{}/{}", provider_name, id);
                    let is_primary = primary_model.as_ref() == Some(&full_id);

                    Some(ConfiguredModel {
                        full_id,
                        id,
                        name,
                        api_type: m.get("api").and_then(|v| v.as_str()).map(|s| s.to_string()),
                        context_window: m
                            .get("contextWindow")
                            .and_then(|v| v.as_u64())
                            .map(|n| n as u32),
                        max_tokens: m
                            .get("maxTokens")
                            .and_then(|v| v.as_u64())
                            .map(|n| n as u32),
                        is_primary,
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn load_agent_auth_profiles(agent_name: &str) -> Option<Value> {
    let auth_path = format!(
        "{}/agents/{}/agent/auth-profiles.json",
        platform::get_config_dir(),
        agent_name
    );
    if !file::file_exists(&auth_path) {
        return None;
    }
    let raw = file::read_file(&auth_path).ok()?;
    serde_json::from_str::<Value>(&raw).ok()
}

fn has_provider_auth_profile(auth_profiles: &Option<Value>, provider_name: &str) -> bool {
    let Some(auth) = auth_profiles else {
        return false;
    };

    let ordered = auth
        .pointer(&format!("/order/{}", provider_name))
        .and_then(|v| v.as_array())
        .map(|v| !v.is_empty())
        .unwrap_or(false);
    if ordered {
        return true;
    }

    auth.get("profiles")
        .and_then(|v| v.as_object())
        .map(|profiles| {
            profiles.values().any(|profile| {
                profile
                    .get("provider")
                    .and_then(|v| v.as_str())
                    .map(|p| p == provider_name)
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

fn parse_configured_providers(
    providers: &serde_json::Map<String, Value>,
    primary_model: &Option<String>,
    auth_profiles: &Option<Value>,
) -> Vec<ConfiguredProvider> {
    let mut configured_providers: Vec<ConfiguredProvider> = Vec::new();

    for (provider_name, provider_config) in providers {
        let base_url = provider_config
            .get("baseUrl")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let api_key = provider_config
            .get("apiKey")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let has_api_key = api_key.is_some() || has_provider_auth_profile(auth_profiles, provider_name);
        let api_key_masked = api_key.as_deref().map(mask_secret);
        let models = parse_models_from_provider(provider_name, provider_config, primary_model);

        configured_providers.push(ConfiguredProvider {
            name: provider_name.clone(),
            base_url,
            api_key_masked,
            has_api_key,
            models,
        });
    }

    configured_providers
}

fn read_agent_models_providers(config: &Value) -> Option<(serde_json::Map<String, Value>, String)> {
    let agent_name = config
        .pointer("/agents/defaults/agent")
        .and_then(|v| v.as_str())
        .unwrap_or("main")
        .to_string();

    let models_path = format!(
        "{}/agents/{}/agent/models.json",
        platform::get_config_dir(),
        agent_name
    );

    if !file::file_exists(&models_path) {
        return None;
    }

    let raw = file::read_file(&models_path).ok()?;
    let parsed = serde_json::from_str::<Value>(&raw).ok()?;
    let providers = parsed.get("providers")?.as_object()?.clone();
    Some((providers, agent_name))
}

/// 获取完整配置
#[command]
pub async fn get_config() -> Result<Value, String> {
    info!("[获取配置] 读取 openclaw.json 配置...");
    let result = load_openclaw_config();
    match &result {
        Ok(_) => info!("[获取配置] ✓ 配置读取成功"),
        Err(e) => error!("[获取配置] ✗ 配置读取失败: {}", e),
    }
    result
}

/// 保存配置
#[command]
pub async fn save_config(config: Value) -> Result<String, String> {
    info!("[保存配置] 保存 openclaw.json 配置...");
    debug!(
        "[保存配置] 配置内容: {}",
        serde_json::to_string_pretty(&config).unwrap_or_default()
    );
    match save_openclaw_config(&config) {
        Ok(_) => {
            info!("[保存配置] ✓ 配置保存成功");
            Ok("配置已保存".to_string())
        }
        Err(e) => {
            error!("[保存配置] ✗ 配置保存失败: {}", e);
            Err(e)
        }
    }
}

/// 获取环境变量值
#[command]
pub async fn get_env_value(key: String) -> Result<Option<String>, String> {
    info!("[获取环境变量] 读取环境变量: {}", key);
    let env_path = platform::get_env_file_path();
    let value = file::read_env_value(&env_path, &key);
    match &value {
        Some(v) => debug!(
            "[获取环境变量] {}={} (已脱敏)",
            key,
            if v.len() > 8 { "***" } else { v }
        ),
        None => debug!("[获取环境变量] {} 不存在", key),
    }
    Ok(value)
}

/// 保存环境变量值
#[command]
pub async fn save_env_value(key: String, value: String) -> Result<String, String> {
    info!("[保存环境变量] 保存环境变量: {}", key);
    let env_path = platform::get_env_file_path();
    debug!("[保存环境变量] 环境文件路径: {}", env_path);
    
    match file::set_env_value(&env_path, &key, &value) {
        Ok(_) => {
            info!("[保存环境变量] ✓ 环境变量 {} 保存成功", key);
            Ok("环境变量已保存".to_string())
        }
        Err(e) => {
            error!("[保存环境变量] ✗ 保存失败: {}", e);
            Err(format!("保存环境变量失败: {}", e))
        }
    }
}

// ============ Gateway Token 命令 ============

/// 生成随机 token（使用 getrandom crate 获取密码学安全随机数，跨平台兼容 HI-394）
fn generate_token() -> String {
    let mut buf = [0u8; 48];
    // getrandom 自动选择最佳系统随机源（macOS: SecRandomCopyBytes, Linux: /dev/urandom, Windows: BCryptGenRandom）
    // 使用 unwrap_or_else 替代 expect 避免 panic — 降级到时间戳+进程ID作为熵源
    if let Err(e) = getrandom::getrandom(&mut buf) {
        log::error!("系统随机数源不可用: {}，使用降级方案", e);
        // 降级方案：时间戳 + 进程ID 拼接（安全性低于密码学随机数，但足以作为本地 token）
        let fallback = format!(
            "{:x}{:x}{:x}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos(),
            std::process::id(),
            // 额外熵：栈上变量的地址（每次调用不同）
            &buf as *const _ as usize
        );
        return fallback;
    }
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

/// 获取或生成 Gateway Token
#[command]
pub async fn get_or_create_gateway_token() -> Result<String, String> {
    info!("[Gateway Token] 获取或创建 Gateway Token...");
    
    let mut config = load_openclaw_config()?;
    
    // 检查是否已有 token
    if let Some(token) = config
        .pointer("/gateway/auth/token")
        .and_then(|v| v.as_str())
    {
        if !token.is_empty() {
            info!("[Gateway Token] ✓ 使用现有 Token");
            return Ok(token.to_string());
        }
    }
    
    // 生成新 token
    let new_token = generate_token();
    info!("[Gateway Token] 生成新 Token: {}...", &new_token[..8]);
    
    // 确保路径存在
    if config.get("gateway").is_none() {
        config["gateway"] = json!({});
    }
    if config["gateway"].get("auth").is_none() {
        config["gateway"]["auth"] = json!({});
    }
    
    // 设置 token 和 mode
    config["gateway"]["auth"]["token"] = json!(new_token);
    config["gateway"]["auth"]["mode"] = json!("token");
    config["gateway"]["mode"] = json!("local");
    
    // 保存配置
    save_openclaw_config(&config)?;
    
    info!("[Gateway Token] ✓ Token 已保存到配置");
    Ok(new_token)
}

/// 获取 Dashboard URL（带 token）
#[command]
pub async fn get_dashboard_url() -> Result<String, String> {
    info!("[Dashboard URL] 获取 Dashboard URL...");
    
    let token = get_or_create_gateway_token().await?;
    let url = format!("http://localhost:18789?token={}", token);
    
    info!("[Dashboard URL] ✓ URL: {}...", &url[..50.min(url.len())]);
    Ok(url)
}

#[command]
pub async fn get_project_context() -> Result<ProjectContext, String> {
    let config = load_openclaw_config()?;
    get_project_context_from_config(&config)
}

#[command]
pub async fn get_app_settings() -> Result<AppSettings, String> {
    let config = load_openclaw_config()?;
    let context = get_project_context_from_config(&config)?;
    let local_settings = load_manager_settings(&context.settings_file)?;
    let mut defaults = default_app_settings();

    defaults.identity.bot_name = local_settings
        .pointer("/identity/botName")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .or_else(|| {
            config
                .pointer("/manager/identity/botName")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .unwrap_or(defaults.identity.bot_name);

    defaults.identity.user_name = local_settings
        .pointer("/identity/userName")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .or_else(|| {
            config
                .pointer("/manager/identity/userName")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .unwrap_or(defaults.identity.user_name);

    defaults.identity.timezone = local_settings
        .pointer("/identity/timezone")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .or_else(|| {
            config
                .pointer("/manager/identity/timezone")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .unwrap_or(defaults.identity.timezone);

    defaults.security.enable_whitelist = local_settings
        .pointer("/security/enableWhitelist")
        .and_then(|v| v.as_bool())
        .or_else(|| config.pointer("/manager/security/enableWhitelist").and_then(|v| v.as_bool()))
        .unwrap_or(defaults.security.enable_whitelist);

    defaults.security.allow_file_access = local_settings
        .pointer("/security/allowFileAccess")
        .and_then(|v| v.as_bool())
        .or_else(|| config.pointer("/manager/security/allowFileAccess").and_then(|v| v.as_bool()))
        .unwrap_or(defaults.security.allow_file_access);

    Ok(defaults)
}

#[command]
pub async fn save_app_settings(settings: AppSettings) -> Result<String, String> {
    let config = load_openclaw_config()?;
    let context = get_project_context_from_config(&config)?;

    let local_settings = json!({
        "identity": {
            "botName": settings.identity.bot_name,
            "userName": settings.identity.user_name,
            "timezone": settings.identity.timezone
        },
        "security": {
            "enableWhitelist": settings.security.enable_whitelist,
            "allowFileAccess": settings.security.allow_file_access
        }
    });

    let local_settings_content = serde_json::to_string_pretty(&local_settings)
        .map_err(|e| format!("序列化本地设置失败: {}", e))?;
    file::write_file(&context.settings_file, &local_settings_content)
        .map_err(|e| format!("写入本地设置失败: {}", e))?;

    sync_workspace_identity_files(&context, &settings)?;
    Ok("设置已保存".to_string())
}

#[command]
pub async fn open_macos_full_disk_access_settings() -> Result<String, String> {
    if !platform::is_macos() {
        return Err("该功能仅支持 macOS".to_string());
    }

    let url = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles";
    let status = Command::new("open")
        .arg(url)
        .status()
        .map_err(|e| format!("打开系统设置失败: {}", e))?;

    if status.success() {
        Ok("已打开“完全磁盘访问权限”设置页".to_string())
    } else {
        Err("无法打开系统设置，请手动前往“隐私与安全性 -> 完全磁盘访问权限”".to_string())
    }
}

// ============ AI 配置相关命令 ============

/// 获取官方 Provider 列表（预设模板）
#[command]
pub async fn get_official_providers() -> Result<Vec<OfficialProvider>, String> {
    info!("[官方 Provider] 获取官方 Provider 预设列表...");

    let providers = vec![
        OfficialProvider {
            id: "anthropic".to_string(),
            name: "Anthropic Claude".to_string(),
            icon: "🟣".to_string(),
            default_base_url: Some("https://api.anthropic.com".to_string()),
            api_type: "anthropic-messages".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/anthropic".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "claude-opus-4-5-20251101".to_string(),
                    name: "Claude Opus 4.5".to_string(),
                    description: Some("最强大版本，适合复杂任务".to_string()),
                    context_window: Some(200000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
                SuggestedModel {
                    id: "claude-sonnet-4-5-20250929".to_string(),
                    name: "Claude Sonnet 4.5".to_string(),
                    description: Some("平衡版本，性价比高".to_string()),
                    context_window: Some(200000),
                    max_tokens: Some(8192),
                    recommended: false,
                },
            ],
        },
        OfficialProvider {
            id: "openai".to_string(),
            name: "OpenAI".to_string(),
            icon: "🟢".to_string(),
            default_base_url: Some("https://api.openai.com/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/openai".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "gpt-4o".to_string(),
                    name: "GPT-4o".to_string(),
                    description: Some("最新多模态模型".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(4096),
                    recommended: true,
                },
                SuggestedModel {
                    id: "gpt-4o-mini".to_string(),
                    name: "GPT-4o Mini".to_string(),
                    description: Some("快速经济版".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(4096),
                    recommended: false,
                },
            ],
        },
        OfficialProvider {
            id: "moonshot".to_string(),
            name: "Moonshot".to_string(),
            icon: "🌙".to_string(),
            default_base_url: Some("https://api.moonshot.cn/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/moonshot".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "kimi-k2.5".to_string(),
                    name: "Kimi K2.5".to_string(),
                    description: Some("最新旗舰模型".to_string()),
                    context_window: Some(200000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
                SuggestedModel {
                    id: "moonshot-v1-128k".to_string(),
                    name: "Moonshot 128K".to_string(),
                    description: Some("超长上下文".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: false,
                },
            ],
        },
        OfficialProvider {
            id: "qwen".to_string(),
            name: "Qwen (通义千问)".to_string(),
            icon: "🔮".to_string(),
            default_base_url: Some("https://dashscope.aliyuncs.com/compatible-mode/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/qwen".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "qwen-max".to_string(),
                    name: "Qwen Max".to_string(),
                    description: Some("最强大版本".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
                SuggestedModel {
                    id: "qwen-plus".to_string(),
                    name: "Qwen Plus".to_string(),
                    description: Some("平衡版本".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: false,
                },
            ],
        },
        OfficialProvider {
            id: "deepseek".to_string(),
            name: "DeepSeek".to_string(),
            icon: "🔵".to_string(),
            default_base_url: Some("https://api.deepseek.com".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: None,
            suggested_models: vec![
                SuggestedModel {
                    id: "deepseek-chat".to_string(),
                    name: "DeepSeek V3".to_string(),
                    description: Some("最新对话模型".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
                SuggestedModel {
                    id: "deepseek-reasoner".to_string(),
                    name: "DeepSeek R1".to_string(),
                    description: Some("推理增强模型".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: false,
                },
            ],
        },
        OfficialProvider {
            id: "glm".to_string(),
            name: "GLM (智谱)".to_string(),
            icon: "🔷".to_string(),
            default_base_url: Some("https://open.bigmodel.cn/api/paas/v4".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/glm".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "glm-4".to_string(),
                    name: "GLM-4".to_string(),
                    description: Some("最新旗舰模型".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
            ],
        },
        OfficialProvider {
            id: "minimax".to_string(),
            name: "MiniMax".to_string(),
            icon: "🟡".to_string(),
            default_base_url: Some("https://api.minimax.io/anthropic".to_string()),
            api_type: "anthropic-messages".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/minimax".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "minimax-m2.1".to_string(),
                    name: "MiniMax M2.1".to_string(),
                    description: Some("最新模型".to_string()),
                    context_window: Some(200000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
            ],
        },
        OfficialProvider {
            id: "venice".to_string(),
            name: "Venice AI".to_string(),
            icon: "🏛️".to_string(),
            default_base_url: Some("https://api.venice.ai/api/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/venice".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "llama-3.3-70b".to_string(),
                    name: "Llama 3.3 70B".to_string(),
                    description: Some("隐私优先推理".to_string()),
                    context_window: Some(128000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
            ],
        },
        OfficialProvider {
            id: "openrouter".to_string(),
            name: "OpenRouter".to_string(),
            icon: "🔄".to_string(),
            default_base_url: Some("https://openrouter.ai/api/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/openrouter".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "anthropic/claude-opus-4-5".to_string(),
                    name: "Claude Opus 4.5".to_string(),
                    description: Some("通过 OpenRouter 访问".to_string()),
                    context_window: Some(200000),
                    max_tokens: Some(8192),
                    recommended: true,
                },
            ],
        },
        OfficialProvider {
            id: "ollama".to_string(),
            name: "Ollama (本地)".to_string(),
            icon: "🟠".to_string(),
            default_base_url: Some("http://localhost:11434".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: false,
            docs_url: Some("https://docs.openclaw.ai/providers/ollama".to_string()),
            suggested_models: vec![
                SuggestedModel {
                    id: "llama3".to_string(),
                    name: "Llama 3".to_string(),
                    description: Some("本地运行".to_string()),
                    context_window: Some(8192),
                    max_tokens: Some(4096),
                    recommended: true,
                },
            ],
        },
    ];

    info!(
        "[官方 Provider] ✓ 返回 {} 个官方 Provider 预设",
        providers.len()
    );
    Ok(providers)
}

/// 获取 AI 配置概览
#[command]
pub async fn get_ai_config() -> Result<AIConfigOverview, String> {
    info!("[AI 配置] 获取 AI 配置概览...");

    let config_path = platform::get_config_file_path();
    info!("[AI 配置] 配置文件路径: {}", config_path);

    let config = load_openclaw_config()?;
    debug!("[AI 配置] 配置内容: {}", serde_json::to_string_pretty(&config).unwrap_or_default());

    // 解析主模型
    let primary_model = config
        .pointer("/agents/defaults/model/primary")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    info!("[AI 配置] 主模型: {:?}", primary_model);

    // 解析可用模型列表
    let available_models: Vec<String> = config
        .pointer("/agents/defaults/models")
        .and_then(|v| v.as_object())
        .map(|obj| obj.keys().cloned().collect())
        .unwrap_or_default();
    info!("[AI 配置] 可用模型数: {}", available_models.len());

    // 解析已配置的 Provider（先读 openclaw.json，为空时回退到 agent/models.json）
    let providers_from_openclaw = config
        .pointer("/models/providers")
        .and_then(|v| v.as_object());
    let mut configured_providers: Vec<ConfiguredProvider> = Vec::new();

    if let Some(providers) = providers_from_openclaw {
        info!("[AI 配置] 从 openclaw.json 读取到 {} 个 Provider", providers.len());
        configured_providers = parse_configured_providers(providers, &primary_model, &None);
    }

    if configured_providers.is_empty() {
        info!("[AI 配置] openclaw.json 中 providers 为空，尝试从 agent/models.json 回退读取");
        if let Some((providers, agent_name)) = read_agent_models_providers(&config) {
            let auth_profiles = load_agent_auth_profiles(&agent_name);
            configured_providers = parse_configured_providers(&providers, &primary_model, &auth_profiles);
            info!(
                "[AI 配置] 回退读取成功（agent={}），Provider 数: {}",
                agent_name,
                configured_providers.len()
            );
        } else {
            info!("[AI 配置] 未找到可回退的 agent models 配置");
        }
    }

    info!(
        "[AI 配置] ✓ 最终结果 - 主模型: {:?}, {} 个 Provider, {} 个可用模型",
        primary_model,
        configured_providers.len(),
        available_models.len()
    );

    Ok(AIConfigOverview {
        primary_model,
        configured_providers,
        available_models,
    })
}

/// 添加或更新 Provider
#[command]
pub async fn save_provider(
    provider_name: String,
    base_url: String,
    api_key: Option<String>,
    api_type: String,
    models: Vec<ModelConfig>,
) -> Result<String, String> {
    info!(
        "[保存 Provider] 保存 Provider: {} ({} 个模型)",
        provider_name,
        models.len()
    );

    let mut config = load_openclaw_config()?;

    // 确保路径存在
    if config.get("models").is_none() {
        config["models"] = json!({});
    }
    if config["models"].get("providers").is_none() {
        config["models"]["providers"] = json!({});
    }
    if config.get("agents").is_none() {
        config["agents"] = json!({});
    }
    if config["agents"].get("defaults").is_none() {
        config["agents"]["defaults"] = json!({});
    }
    if config["agents"]["defaults"].get("models").is_none() {
        config["agents"]["defaults"]["models"] = json!({});
    }

    // 构建模型配置
    let models_json: Vec<Value> = models
        .iter()
        .map(|m| {
            let mut model_obj = json!({
                "id": m.id,
                "name": m.name,
                "api": m.api.clone().unwrap_or(api_type.clone()),
                "input": if m.input.is_empty() { vec!["text".to_string()] } else { m.input.clone() },
            });

            if let Some(cw) = m.context_window {
                model_obj["contextWindow"] = json!(cw);
            }
            if let Some(mt) = m.max_tokens {
                model_obj["maxTokens"] = json!(mt);
            }
            if let Some(r) = m.reasoning {
                model_obj["reasoning"] = json!(r);
            }
            if let Some(cost) = &m.cost {
                model_obj["cost"] = json!({
                    "input": cost.input,
                    "output": cost.output,
                    "cacheRead": cost.cache_read,
                    "cacheWrite": cost.cache_write,
                });
            } else {
                model_obj["cost"] = json!({
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                });
            }

            model_obj
        })
        .collect();

    // 构建 Provider 配置
    let mut provider_config = json!({
        "baseUrl": base_url,
        "models": models_json,
    });

    // 处理 API Key：如果传入了新的非空 key，使用新的；否则保留原有的
    if let Some(key) = api_key {
        if !key.is_empty() {
            // 使用新传入的 API Key
            provider_config["apiKey"] = json!(key);
            info!("[保存 Provider] 使用新的 API Key");
        } else {
            // 空字符串表示不更改，尝试保留原有的 API Key
            if let Some(existing_key) = config
                .pointer(&format!("/models/providers/{}/apiKey", provider_name))
                .and_then(|v| v.as_str())
            {
                provider_config["apiKey"] = json!(existing_key);
                info!("[保存 Provider] 保留原有的 API Key");
            }
        }
    } else {
        // None 表示不更改，尝试保留原有的 API Key
        if let Some(existing_key) = config
            .pointer(&format!("/models/providers/{}/apiKey", provider_name))
            .and_then(|v| v.as_str())
        {
            provider_config["apiKey"] = json!(existing_key);
            info!("[保存 Provider] 保留原有的 API Key");
        }
    }

    // 保存 Provider 配置
    config["models"]["providers"][&provider_name] = provider_config;

    // 将模型添加到 agents.defaults.models
    for model in &models {
        let full_id = format!("{}/{}", provider_name, model.id);
        config["agents"]["defaults"]["models"][&full_id] = json!({});
    }

    // 更新元数据
    let now = chrono::Utc::now().to_rfc3339();
    if config.get("meta").is_none() {
        config["meta"] = json!({});
    }
    config["meta"]["lastTouchedAt"] = json!(now);

    save_openclaw_config(&config)?;
    info!("[保存 Provider] ✓ Provider {} 保存成功", provider_name);

    Ok(format!("Provider {} 已保存", provider_name))
}

/// 删除 Provider
#[command]
pub async fn delete_provider(provider_name: String) -> Result<String, String> {
    info!("[删除 Provider] 删除 Provider: {}", provider_name);

    let mut config = load_openclaw_config()?;

    // 删除 Provider 配置
    if let Some(providers) = config
        .pointer_mut("/models/providers")
        .and_then(|v| v.as_object_mut())
    {
        providers.remove(&provider_name);
    }

    // 删除相关模型
    if let Some(models) = config
        .pointer_mut("/agents/defaults/models")
        .and_then(|v| v.as_object_mut())
    {
        let keys_to_remove: Vec<String> = models
            .keys()
            .filter(|k| k.starts_with(&format!("{}/", provider_name)))
            .cloned()
            .collect();

        for key in keys_to_remove {
            models.remove(&key);
        }
    }

    // 如果主模型属于该 Provider，清除主模型
    if let Some(primary) = config
        .pointer("/agents/defaults/model/primary")
        .and_then(|v| v.as_str())
    {
        if primary.starts_with(&format!("{}/", provider_name)) {
            config["agents"]["defaults"]["model"]["primary"] = json!(null);
        }
    }

    save_openclaw_config(&config)?;
    info!("[删除 Provider] ✓ Provider {} 已删除", provider_name);

    Ok(format!("Provider {} 已删除", provider_name))
}

/// 设置主模型
#[command]
pub async fn set_primary_model(model_id: String) -> Result<String, String> {
    info!("[设置主模型] 设置主模型: {}", model_id);

    let mut config = load_openclaw_config()?;

    // 确保路径存在
    if config.get("agents").is_none() {
        config["agents"] = json!({});
    }
    if config["agents"].get("defaults").is_none() {
        config["agents"]["defaults"] = json!({});
    }
    if config["agents"]["defaults"].get("model").is_none() {
        config["agents"]["defaults"]["model"] = json!({});
    }

    // 设置主模型
    config["agents"]["defaults"]["model"]["primary"] = json!(model_id);

    save_openclaw_config(&config)?;
    info!("[设置主模型] ✓ 主模型已设置为: {}", model_id);

    Ok(format!("主模型已设置为 {}", model_id))
}

/// 添加模型到可用列表
#[command]
pub async fn add_available_model(model_id: String) -> Result<String, String> {
    info!("[添加模型] 添加模型到可用列表: {}", model_id);

    let mut config = load_openclaw_config()?;

    // 确保路径存在
    if config.get("agents").is_none() {
        config["agents"] = json!({});
    }
    if config["agents"].get("defaults").is_none() {
        config["agents"]["defaults"] = json!({});
    }
    if config["agents"]["defaults"].get("models").is_none() {
        config["agents"]["defaults"]["models"] = json!({});
    }

    // 添加模型
    config["agents"]["defaults"]["models"][&model_id] = json!({});

    save_openclaw_config(&config)?;
    info!("[添加模型] ✓ 模型 {} 已添加", model_id);

    Ok(format!("模型 {} 已添加", model_id))
}

/// 从可用列表移除模型
#[command]
pub async fn remove_available_model(model_id: String) -> Result<String, String> {
    info!("[移除模型] 从可用列表移除模型: {}", model_id);

    let mut config = load_openclaw_config()?;

    if let Some(models) = config
        .pointer_mut("/agents/defaults/models")
        .and_then(|v| v.as_object_mut())
    {
        models.remove(&model_id);
    }

    save_openclaw_config(&config)?;
    info!("[移除模型] ✓ 模型 {} 已移除", model_id);

    Ok(format!("模型 {} 已移除", model_id))
}

// ============ 旧版兼容 ============

/// 获取所有支持的 AI Provider（旧版兼容）
#[command]
pub async fn get_ai_providers() -> Result<Vec<crate::models::AIProviderOption>, String> {
    info!("[AI Provider] 获取支持的 AI Provider 列表（旧版）...");

    let official = get_official_providers().await?;
    let providers: Vec<crate::models::AIProviderOption> = official
        .into_iter()
        .map(|p| crate::models::AIProviderOption {
            id: p.id,
            name: p.name,
            icon: p.icon,
            default_base_url: p.default_base_url,
            requires_api_key: p.requires_api_key,
            models: p
                .suggested_models
                .into_iter()
                .map(|m| crate::models::AIModelOption {
                    id: m.id,
                    name: m.name,
                    description: m.description,
                    recommended: m.recommended,
                })
                .collect(),
        })
        .collect();

    Ok(providers)
}

// ============ 渠道配置 ============

/// 获取渠道配置 - 从 openclaw.json 和 env 文件读取
#[command]
pub async fn get_channels_config() -> Result<Vec<ChannelConfig>, String> {
    info!("[渠道配置] 获取渠道配置列表...");
    
    let config = load_openclaw_config()?;
    let channels_obj = config.get("channels").cloned().unwrap_or(json!({}));
    let env_path = platform::get_env_file_path();
    debug!("[渠道配置] 环境文件路径: {}", env_path);
    
    let mut channels = Vec::new();
    
    // 支持的渠道类型列表及其测试字段
    let channel_types = vec![
        ("telegram", "telegram", vec!["userId"]),
        ("discord", "discord", vec!["testChannelId"]),
        ("slack", "slack", vec!["testChannelId"]),
        ("feishu", "feishu", vec!["testChatId"]),
        ("whatsapp", "whatsapp", vec![]),
        ("imessage", "imessage", vec![]),
        ("wechat", "wechat", vec![]),
        ("dingtalk", "dingtalk", vec![]),
    ];
    
    for (channel_id, channel_type, test_fields) in channel_types {
        let channel_config = channels_obj.get(channel_id);
        
        let enabled = channel_config
            .and_then(|c| c.get("enabled"))
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        
        // 将渠道配置转换为 HashMap
        let mut config_map: HashMap<String, Value> = if let Some(cfg) = channel_config {
            if let Some(obj) = cfg.as_object() {
                obj.iter()
                    .filter(|(k, _)| *k != "enabled") // 排除 enabled 字段
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect()
            } else {
                HashMap::new()
            }
        } else {
            HashMap::new()
        };
        
        // 从 env 文件读取测试字段
        for field in test_fields {
            let env_key = format!(
                "OPENCLAW_{}_{}",
                channel_id.to_uppercase(),
                field.to_uppercase()
            );
            if let Some(value) = file::read_env_value(&env_path, &env_key) {
                config_map.insert(field.to_string(), json!(value));
            }
        }

        // Telegram 兼容映射：userId <-> allowFrom[0]
        if channel_id == "telegram" {
            if !config_map.contains_key("userId") {
                let fallback_user_id = config_map
                    .get("allowFrom")
                    .and_then(|v| {
                        v.as_array()
                            .and_then(|arr| arr.first())
                            .and_then(|item| item.as_str())
                            .map(|s| s.to_string())
                            .or_else(|| v.as_str().map(|s| s.to_string()))
                    })
                    .and_then(|raw| {
                        raw.split(',')
                            .map(|s| s.trim())
                            .find(|s| !s.is_empty())
                            .map(|s| s.to_string())
                    });

                if let Some(user_id) = fallback_user_id {
                    config_map.insert("userId".to_string(), json!(user_id));
                }
            }

            if !config_map.contains_key("dmPolicy") {
                config_map.insert("dmPolicy".to_string(), json!("allowlist"));
            }
            if !config_map.contains_key("groupPolicy") {
                config_map.insert("groupPolicy".to_string(), json!("allowlist"));
            }
        }
        
        // 判断是否已配置（有任何非空配置项）
        let has_config = !config_map.is_empty() || enabled;
        
        channels.push(ChannelConfig {
            id: channel_id.to_string(),
            channel_type: channel_type.to_string(),
            enabled: has_config,
            config: config_map,
        });
    }
    
    info!("[渠道配置] ✓ 返回 {} 个渠道配置", channels.len());
    for ch in &channels {
        debug!("[渠道配置] - {}: enabled={}", ch.id, ch.enabled);
    }
    Ok(channels)
}

/// 保存渠道配置 - 保存到 openclaw.json
#[command]
pub async fn save_channel_config(channel: ChannelConfig) -> Result<String, String> {
    info!(
        "[保存渠道配置] 保存渠道配置: {} ({})",
        channel.id, channel.channel_type
    );
    
    let mut config = load_openclaw_config()?;
    let env_path = platform::get_env_file_path();
    debug!("[保存渠道配置] 环境文件路径: {}", env_path);
    
    // 确保 channels 对象存在
    if config.get("channels").is_none() {
        config["channels"] = json!({});
    }
    
    // 确保 plugins 对象存在
    if config.get("plugins").is_none() {
        config["plugins"] = json!({
            "allow": [],
            "entries": {}
        });
    }
    if config["plugins"].get("allow").is_none() {
        config["plugins"]["allow"] = json!([]);
    }
    if config["plugins"].get("entries").is_none() {
        config["plugins"]["entries"] = json!({});
    }
    
    // 这些字段只用于测试，不保存到 openclaw.json，而是保存到 env 文件
    let test_only_fields = ["userId", "testChatId", "testChannelId"];
    let mut telegram_user_id: Option<String> = None;
    
    // 构建渠道配置
    let mut channel_obj = json!({
        "enabled": true
    });
    
    // 添加渠道特定配置
    for (key, value) in &channel.config {
        if channel.id == "telegram" && key == "userId" {
            if let Some(val_str) = value.as_str() {
                let trimmed = val_str.trim();
                if !trimmed.is_empty() {
                    telegram_user_id = Some(trimmed.to_string());
                }
            }

            // 兼容旧逻辑，继续写入 env，便于工具链读取
            if let Some(val_str) = value.as_str() {
                let env_key = format!(
                    "OPENCLAW_{}_{}",
                    channel.id.to_uppercase(),
                    key.to_uppercase()
                );
                let _ = file::set_env_value(&env_path, &env_key, val_str);
            }
            continue;
        }

        if test_only_fields.contains(&key.as_str()) {
            // 保存到 env 文件
            let env_key = format!(
                "OPENCLAW_{}_{}",
                channel.id.to_uppercase(),
                key.to_uppercase()
            );
            if let Some(val_str) = value.as_str() {
                let _ = file::set_env_value(&env_path, &env_key, val_str);
            }
        } else {
            // 保存到 openclaw.json
            channel_obj[key] = value.clone();
        }
    }
    
    if channel.id == "telegram" {
        if let Some(user_id) = telegram_user_id {
            channel_obj["allowFrom"] = json!([user_id.clone()]);
            channel_obj["groupAllowFrom"] = json!([user_id]);
        }

        for allow_key in ["allowFrom", "groupAllowFrom"] {
            if let Some(raw) = channel_obj.get(allow_key).and_then(|v| v.as_str()) {
                let values: Vec<String> = raw
                    .split(',')
                    .map(|s| s.trim())
                    .filter(|s| !s.is_empty())
                    .map(|s| s.to_string())
                    .collect();
                if !values.is_empty() {
                    channel_obj[allow_key] = json!(values);
                }
            }
        }

        if channel_obj.get("dmPolicy").is_none() {
            channel_obj["dmPolicy"] = json!("allowlist");
        }
        if channel_obj.get("groupPolicy").is_none() {
            channel_obj["groupPolicy"] = json!("allowlist");
        }
    }

    // 更新 channels 配置
    config["channels"][&channel.id] = channel_obj;
    
    // 更新 plugins.allow 数组 - 确保渠道在白名单中
    if let Some(allow_arr) = config["plugins"]["allow"].as_array_mut() {
        let channel_id_val = json!(&channel.id);
        if !allow_arr.contains(&channel_id_val) {
            allow_arr.push(channel_id_val);
        }
    }
    
    // 更新 plugins.entries - 确保插件已启用
    config["plugins"]["entries"][&channel.id] = json!({
        "enabled": true
    });
    
    // 保存配置
    info!("[保存渠道配置] 写入配置文件...");
    match save_openclaw_config(&config) {
        Ok(_) => {
            info!(
                "[保存渠道配置] ✓ {} 配置保存成功",
                channel.channel_type
            );
            Ok(format!("{} 配置已保存", channel.channel_type))
        }
        Err(e) => {
            error!("[保存渠道配置] ✗ 保存失败: {}", e);
            Err(e)
        }
    }
}

/// 清空渠道配置 - 从 openclaw.json 中删除指定渠道的配置
#[command]
pub async fn clear_channel_config(channel_id: String) -> Result<String, String> {
    info!("[清空渠道配置] 清空渠道配置: {}", channel_id);
    
    let mut config = load_openclaw_config()?;
    let env_path = platform::get_env_file_path();
    
    // 从 channels 对象中删除该渠道
    if let Some(channels) = config.get_mut("channels").and_then(|v| v.as_object_mut()) {
        channels.remove(&channel_id);
        info!("[清空渠道配置] 已从 channels 中删除: {}", channel_id);
    }
    
    // 从 plugins.allow 数组中删除
    if let Some(allow_arr) = config.pointer_mut("/plugins/allow").and_then(|v| v.as_array_mut()) {
        allow_arr.retain(|v| v.as_str() != Some(&channel_id));
        info!("[清空渠道配置] 已从 plugins.allow 中删除: {}", channel_id);
    }
    
    // 从 plugins.entries 中删除
    if let Some(entries) = config.pointer_mut("/plugins/entries").and_then(|v| v.as_object_mut()) {
        entries.remove(&channel_id);
        info!("[清空渠道配置] 已从 plugins.entries 中删除: {}", channel_id);
    }
    
    // 清除相关的环境变量
    let env_prefixes = vec![
        format!("OPENCLAW_{}_USERID", channel_id.to_uppercase()),
        format!("OPENCLAW_{}_TESTCHATID", channel_id.to_uppercase()),
        format!("OPENCLAW_{}_TESTCHANNELID", channel_id.to_uppercase()),
    ];
    for env_key in env_prefixes {
        let _ = file::remove_env_value(&env_path, &env_key);
    }
    
    // 保存配置
    match save_openclaw_config(&config) {
        Ok(_) => {
            info!("[清空渠道配置] ✓ {} 配置已清空", channel_id);
            Ok(format!("{} 配置已清空", channel_id))
        }
        Err(e) => {
            error!("[清空渠道配置] ✗ 清空失败: {}", e);
            Err(e)
        }
    }
}

// ============ 飞书插件管理 ============

/// 飞书插件状态
#[derive(Debug, Serialize, Deserialize)]
pub struct FeishuPluginStatus {
    pub installed: bool,
    pub version: Option<String>,
    pub plugin_name: Option<String>,
}

/// 检查飞书插件是否已安装
#[command]
pub async fn check_feishu_plugin() -> Result<FeishuPluginStatus, String> {
    info!("[飞书插件] 检查飞书插件安装状态...");
    
    // 执行 openclaw plugins list 命令
    match shell::run_openclaw(&["plugins", "list"]) {
        Ok(output) => {
            debug!("[飞书插件] plugins list 输出: {}", output);
            
            // 查找包含 feishu 的行（不区分大小写）
            let lines: Vec<&str> = output.lines().collect();
            let feishu_line = lines.iter().find(|line| {
                line.to_lowercase().contains("feishu")
            });
            
            if let Some(line) = feishu_line {
                info!("[飞书插件] ✓ 飞书插件已安装: {}", line);
                
                // 尝试解析版本号（通常格式为 "name@version" 或 "name version"）
                let version = if line.contains('@') {
                    line.rsplit('@').next().map(|s| s.trim().to_string())
                } else {
                    // 尝试匹配版本号模式 (如 0.1.2)
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    parts.iter()
                        .find(|p| p.chars().next().map(|c| c.is_ascii_digit()).unwrap_or(false))
                        .map(|s| s.to_string())
                };
                
                Ok(FeishuPluginStatus {
                    installed: true,
                    version,
                    plugin_name: Some(line.trim().to_string()),
                })
            } else {
                info!("[飞书插件] ✗ 飞书插件未安装");
                Ok(FeishuPluginStatus {
                    installed: false,
                    version: None,
                    plugin_name: None,
                })
            }
        }
        Err(e) => {
            warn!("[飞书插件] 检查插件列表失败: {}", e);
            // 如果命令失败，假设插件未安装
            Ok(FeishuPluginStatus {
                installed: false,
                version: None,
                plugin_name: None,
            })
        }
    }
}

/// 安装飞书插件
#[command]
pub async fn install_feishu_plugin() -> Result<String, String> {
    info!("[飞书插件] 开始安装飞书插件...");
    
    // 先检查是否已安装
    let status = check_feishu_plugin().await?;
    if status.installed {
        info!("[飞书插件] 飞书插件已安装，跳过");
        return Ok(format!("飞书插件已安装: {}", status.plugin_name.unwrap_or_default()));
    }
    
    // 安装飞书插件
    // 注意：使用 @m1heng-clawd/feishu 包名
    info!("[飞书插件] 执行 openclaw plugins install @m1heng-clawd/feishu ...");
    match shell::run_openclaw(&["plugins", "install", "@m1heng-clawd/feishu"]) {
        Ok(output) => {
            info!("[飞书插件] 安装输出: {}", output);
            
            // 验证安装结果
            let verify_status = check_feishu_plugin().await?;
            if verify_status.installed {
                info!("[飞书插件] ✓ 飞书插件安装成功");
                Ok(format!("飞书插件安装成功: {}", verify_status.plugin_name.unwrap_or_default()))
            } else {
                warn!("[飞书插件] 安装命令执行成功但插件未找到");
                Err("安装命令执行成功但插件未找到，请检查 openclaw 版本".to_string())
            }
        }
        Err(e) => {
            error!("[飞书插件] ✗ 安装失败: {}", e);
            Err(format!("安装飞书插件失败: {}\n\n请手动执行: openclaw plugins install @m1heng-clawd/feishu", e))
        }
    }
}

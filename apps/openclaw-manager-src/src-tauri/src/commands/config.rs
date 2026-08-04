use crate::models::{
    AIConfigOverview, AppError, AppResult, ChannelConfig, ConfiguredModel, ConfiguredProvider,
    ModelConfig, OfficialProvider, SuggestedModel,
};
use crate::utils::{file, platform, shell};
use log::{debug, error, info, warn};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{LazyLock, Mutex};
use tauri::command;

static OPENCLAW_CONFIG_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

const WRITABLE_ENV_KEYS: [&str; 2] = ["LLM_API_KEY", "LLM_BASE_URL"];
const READABLE_ENV_KEYS: [&str; 10] = [
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "IBKR_ACCOUNT",
    "LOG_LEVEL",
    "OPENCLAW_PORT",
    "REDIS_URL",
    "TELEGRAM_BOT_TOKEN",
];
const SENSITIVE_READ_ENV_KEYS: [&str; 6] = [
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "REDIS_URL",
    "TELEGRAM_BOT_TOKEN",
];
const SENSITIVE_ENV_MASK: &str = "************";

#[derive(Debug)]
struct ConfigFileLock {
    _lock: file::ExclusiveFileLock,
}

impl ConfigFileLock {
    fn acquire() -> AppResult<Self> {
        let path = Self::path();
        Self::acquire_at(&path, 200)
    }

    fn path() -> PathBuf {
        PathBuf::from(platform::get_config_dir())
            .join("manager-pids")
            .join("openclaw-config.lock")
    }

    fn acquire_at(path: &Path, attempts: usize) -> AppResult<Self> {
        match file::ExclusiveFileLock::acquire(path, attempts, 25) {
            Ok(lock) => Ok(Self { _lock: lock }),
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => Err(
                AppError::conflict("另一个 OpenClaw 管理器实例正在更新配置，已拒绝并发写入"),
            ),
            Err(error) => Err(AppError::io(format!("创建配置锁失败: {}", error))),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum EnvMutation {
    Set(String, String),
    Remove(String),
}

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

pub(crate) fn get_home_dir() -> AppResult<String> {
    if let Ok(home) = std::env::var("HOME") {
        if !home.is_empty() {
            return Ok(home);
        }
    }
    dirs::home_dir()
        .map(|p| p.display().to_string())
        .ok_or_else(|| AppError::config("无法获取用户 Home 目录"))
}

fn get_default_workspace_path() -> AppResult<String> {
    // 优先从环境变量 OPENCLAW_PROJECT_DIR 获取项目根目录，支持部署到任意路径
    if let Ok(dir) = std::env::var("OPENCLAW_PROJECT_DIR") {
        if !dir.is_empty() {
            return Ok(format!("{}/apps/openclaw", dir));
        }
    }
    let home = get_home_dir()?;
    Ok(format!("{}/Desktop/OpenEverything/apps/openclaw", home))
}

fn infer_workspace_path(config: &Value) -> AppResult<String> {
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

fn get_project_context_from_config(config: &Value) -> AppResult<ProjectContext> {
    let workspace_dir = infer_workspace_path(config)?;
    let project_base_dir = derive_project_base_dir(&workspace_dir);
    let config_dir = platform::get_config_dir();
    let config_file = platform::get_config_file_path();
    let env_file = platform::get_env_file_path();
    let identity_file = format!("{}/IDENTITY.md", workspace_dir);
    let user_file = format!("{}/USER.md", workspace_dir);
    let settings_file = get_manager_settings_path(&project_base_dir);

    Ok(ProjectContext {
        project_name: "OpenClaw".to_string(),
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

fn load_manager_settings(settings_path: &str) -> AppResult<Value> {
    if !file::file_exists(settings_path) {
        return Ok(json!({}));
    }

    let raw = file::read_file(settings_path)
        .map_err(|e| AppError::io(format!("读取本地设置文件失败: {}", e)))?;
    serde_json::from_str(&raw)
        .map_err(|e| AppError::serialization(format!("解析本地设置文件失败: {}", e)))
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

fn sync_workspace_identity_files(
    context: &ProjectContext,
    settings: &AppSettings,
) -> AppResult<()> {
    if file::file_exists(&context.identity_file) {
        let content = file::read_file(&context.identity_file)
            .map_err(|e| AppError::io(format!("读取 IDENTITY.md 失败: {}", e)))?;
        let mut updated = content.clone();

        if let Some(next) = update_markdown_field(&updated, "Name", &settings.identity.bot_name) {
            updated = next;
        }
        if let Some(next) = update_markdown_field(&updated, "Timezone", &settings.identity.timezone)
        {
            updated = next;
        }

        if updated != content {
            file::write_file(&context.identity_file, &updated)
                .map_err(|e| AppError::io(format!("写入 IDENTITY.md 失败: {}", e)))?;
        }
    }

    if file::file_exists(&context.user_file) {
        let content = file::read_file(&context.user_file)
            .map_err(|e| AppError::io(format!("读取 USER.md 失败: {}", e)))?;
        let mut updated = content.clone();

        if let Some(next) =
            update_markdown_field(&updated, "What to call them", &settings.identity.user_name)
        {
            updated = next;
        }
        if let Some(next) = update_markdown_field(&updated, "Timezone", &settings.identity.timezone)
        {
            updated = next;
        }

        if updated != content {
            file::write_file(&context.user_file, &updated)
                .map_err(|e| AppError::io(format!("写入 USER.md 失败: {}", e)))?;
        }
    }

    Ok(())
}

/// 获取 openclaw.json 配置
fn load_openclaw_config() -> AppResult<Value> {
    load_openclaw_config_at(&platform::get_config_file_path())
}

fn load_openclaw_config_at(config_path: &str) -> AppResult<Value> {
    if !file::file_exists(&config_path) {
        return Ok(json!({}));
    }

    let content = file::read_file(&config_path)
        .map_err(|e| AppError::io(format!("读取配置文件失败: {}", e)))?;

    serde_json::from_str(&content)
        .map_err(|e| AppError::serialization(format!("解析配置文件失败: {}", e)))
}

fn is_sensitive_config_key(key: &str) -> bool {
    let normalized: String = key
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .flat_map(char::to_lowercase)
        .collect();
    normalized == "authorization"
        || normalized == "cookie"
        || normalized == "cookies"
        || normalized == "credential"
        || normalized == "credentials"
        || normalized == "env"
        || normalized == "headers"
        || normalized == "serviceaccount"
        || normalized.ends_with("apikey")
        || normalized.ends_with("encryptkey")
        || normalized.ends_with("passphrase")
        || normalized.ends_with("password")
        || normalized.ends_with("privatekey")
        || normalized.ends_with("secret")
        || normalized.ends_with("sessionkey")
        || normalized.ends_with("token")
}

fn is_sensitive_config_path(path: &[String], key: &str) -> bool {
    if is_sensitive_config_key(key) {
        return true;
    }
    let in_model_provider = path.iter().any(|segment| segment == "models")
        && path.iter().any(|segment| segment == "providers");
    if !in_model_provider {
        return false;
    }
    let parent = path.last().map(String::as_str);
    (parent == Some("auth") && key == "value")
        || (parent == Some("tls") && matches!(key, "ca" | "cert" | "key" | "passphrase"))
}

fn redact_sensitive_config_subtree(value: &Value) -> Value {
    if parse_secret_ref(value).is_some() {
        return value.clone();
    }
    match value {
        Value::String(secret) if !secret.is_empty() => json!(SENSITIVE_ENV_MASK),
        Value::Array(items) => {
            Value::Array(items.iter().map(redact_sensitive_config_subtree).collect())
        }
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(key, value)| (key.clone(), redact_sensitive_config_subtree(value)))
                .collect(),
        ),
        _ => value.clone(),
    }
}

fn redact_config_for_webview_at(value: &Value, path: &mut Vec<String>) -> Value {
    match value {
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(|item| redact_config_for_webview_at(item, path))
                .collect(),
        ),
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(key, value)| {
                    let redacted = if is_sensitive_config_path(path, key) {
                        redact_sensitive_config_subtree(value)
                    } else {
                        path.push(key.clone());
                        let redacted = redact_config_for_webview_at(value, path);
                        path.pop();
                        redacted
                    };
                    (key.clone(), redacted)
                })
                .collect(),
        ),
        _ => value.clone(),
    }
}

fn redact_config_for_webview(value: &Value) -> Value {
    redact_config_for_webview_at(value, &mut Vec::new())
}

fn value_contains_sensitive_mask(value: &Value) -> bool {
    match value {
        Value::String(value) => value == SENSITIVE_ENV_MASK,
        Value::Array(items) => items.iter().any(value_contains_sensitive_mask),
        Value::Object(object) => object.values().any(value_contains_sensitive_mask),
        _ => false,
    }
}

fn restore_masked_config_values(current: &Value, next: &mut Value) {
    if matches!(next, Value::String(value) if value == SENSITIVE_ENV_MASK) {
        *next = current.clone();
        return;
    }
    match (current, next) {
        (Value::Array(current_items), Value::Array(next_items)) => {
            for (index, next_item) in next_items.iter_mut().enumerate() {
                if let Some(current_item) = current_items.get(index) {
                    restore_masked_config_values(current_item, next_item);
                }
            }
        }
        (Value::Object(current_object), Value::Object(next_object)) => {
            for (key, next_value) in next_object {
                if let Some(current_value) = current_object.get(key) {
                    restore_masked_config_values(current_value, next_value);
                }
            }
        }
        _ => {}
    }
}

fn preserve_existing_sensitive_values(current: &Value, next: &mut Value) {
    match (current, next) {
        (Value::Object(current_object), Value::Object(next_object)) => {
            for (key, current_value) in current_object {
                if is_sensitive_config_key(key) {
                    next_object.insert(key.clone(), current_value.clone());
                } else if let Some(next_value) = next_object.get_mut(key) {
                    preserve_existing_sensitive_values(current_value, next_value);
                }
            }
        }
        (Value::Array(current_items), Value::Array(next_items)) => {
            for (current_item, next_item) in current_items.iter().zip(next_items.iter_mut()) {
                preserve_existing_sensitive_values(current_item, next_item);
            }
        }
        _ => {}
    }
}

fn preserve_webview_config_sections(current: &Value, next: &mut Value) -> AppResult<()> {
    let root = next
        .as_object_mut()
        .ok_or_else(|| AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"))?;

    // 这些顶层区承载官方 Provider/Channel 凭据，通用设置重置不得删除。
    for section in [
        "agents", "channels", "messages", "plugins", "secrets", "skills", "talk", "tools",
    ] {
        if let Some(value) = current.get(section) {
            root.insert(section.to_string(), value.clone());
        }
    }

    if let Some(providers) = current.pointer("/models/providers") {
        let models = root.entry("models").or_insert_with(|| json!({}));
        if !models.is_object() {
            *models = json!({});
        }
        models
            .as_object_mut()
            .ok_or_else(|| AppError::validation("Models 配置必须是 JSON 对象"))?
            .insert("providers".to_string(), providers.clone());
    }

    preserve_existing_sensitive_values(current, next);
    preserve_existing_gateway_auth(current, next)
}

fn set_gateway_section_value(
    config: &mut Value,
    section: &str,
    key: &str,
    value: Value,
) -> AppResult<()> {
    let root = config
        .as_object_mut()
        .ok_or_else(|| AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"))?;
    let gateway = root.entry("gateway").or_insert_with(|| json!({}));
    if !gateway.is_object() {
        *gateway = json!({});
    }
    let gateway = gateway
        .as_object_mut()
        .ok_or_else(|| AppError::validation("Gateway 配置必须是 JSON 对象"))?;
    let target = gateway.entry(section).or_insert_with(|| json!({}));
    if !target.is_object() {
        *target = json!({});
    }
    target
        .as_object_mut()
        .ok_or_else(|| AppError::validation("Gateway 凭据配置必须是 JSON 对象"))?
        .insert(key.to_string(), value);
    Ok(())
}

fn set_gateway_auth(config: &mut Value, token: Value) -> AppResult<()> {
    set_gateway_section_value(config, "auth", "token", token)
}

fn configured_gateway_credential(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(|credential| !credential.is_empty())
        || parse_secret_ref(value).is_some()
}

fn preserve_existing_secret_providers(current: &Value, next: &mut Value) -> AppResult<()> {
    let Some(current_providers) = current
        .pointer("/secrets/providers")
        .and_then(Value::as_object)
    else {
        return Ok(());
    };

    let root = next
        .as_object_mut()
        .ok_or_else(|| AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"))?;
    let secrets = root.entry("secrets").or_insert_with(|| json!({}));
    if !secrets.is_object() {
        *secrets = json!({});
    }
    let secrets = secrets
        .as_object_mut()
        .ok_or_else(|| AppError::validation("Secrets 配置必须是 JSON 对象"))?;
    let providers = secrets.entry("providers").or_insert_with(|| json!({}));
    if !providers.is_object() {
        *providers = json!({});
    }
    let providers = providers
        .as_object_mut()
        .ok_or_else(|| AppError::validation("Secret Provider 配置必须是 JSON 对象"))?;
    for (name, provider) in current_providers {
        providers.insert(name.clone(), provider.clone());
    }
    Ok(())
}

/// 通用配置保存不得删除或旋转已在使用的 Gateway 凭据。
fn preserve_existing_gateway_auth(current: &Value, next: &mut Value) -> AppResult<()> {
    let credential_paths = [
        ("/gateway/auth/token", "auth", "token"),
        ("/gateway/auth/password", "auth", "password"),
    ];
    let mut preserved_credential = false;
    for (path, section, key) in credential_paths {
        let Some(credential) = current
            .pointer(path)
            .filter(|value| configured_gateway_credential(value))
        else {
            continue;
        };
        set_gateway_section_value(next, section, key, credential.clone())?;
        preserved_credential = true;
    }

    let remote_mode = current.pointer("/gateway/mode").and_then(Value::as_str) == Some("remote");
    let remote_has_credentials = current
        .pointer("/gateway/remote/token")
        .is_some_and(configured_gateway_credential)
        || current
            .pointer("/gateway/remote/password")
            .is_some_and(configured_gateway_credential);
    if remote_mode || remote_has_credentials {
        if let Some(remote) = current
            .pointer("/gateway/remote")
            .and_then(Value::as_object)
        {
            let root = next
                .as_object_mut()
                .ok_or_else(|| AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"))?;
            let gateway = root.entry("gateway").or_insert_with(|| json!({}));
            if !gateway.is_object() {
                *gateway = json!({});
            }
            gateway
                .as_object_mut()
                .ok_or_else(|| AppError::validation("Gateway 配置必须是 JSON 对象"))?
                .insert("remote".to_string(), Value::Object(remote.clone()));
            preserved_credential = true;
        }
    }

    if preserved_credential {
        if let Some(mode) = current.pointer("/gateway/auth/mode") {
            set_gateway_section_value(next, "auth", "mode", mode.clone())?;
        }
        if let Some(mode) = current.pointer("/gateway/mode") {
            let root = next
                .as_object_mut()
                .ok_or_else(|| AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"))?;
            let gateway = root.entry("gateway").or_insert_with(|| json!({}));
            if !gateway.is_object() {
                *gateway = json!({});
            }
            gateway
                .as_object_mut()
                .ok_or_else(|| AppError::validation("Gateway 配置必须是 JSON 对象"))?
                .insert("mode".to_string(), mode.clone());
        }
    }

    preserve_existing_secret_providers(current, next)?;
    Ok(())
}

/// 调用方已持有 OPENCLAW_CONFIG_LOCK 时写入 openclaw.json。
fn save_openclaw_config_locked(config: &Value) -> AppResult<()> {
    save_openclaw_config_at(&platform::get_config_file_path(), config)
}

fn save_openclaw_config_at(config_path: &str, config: &Value) -> AppResult<()> {
    let content = serde_json::to_string_pretty(config)
        .map_err(|e| AppError::serialization(format!("序列化配置失败: {}", e)))?;

    file::write_file_atomic(config_path, &content)
        .map_err(|e| AppError::io(format!("写入配置文件失败: {}", e)))
}

/// 在同一线程锁和跨进程锁内完成 openclaw.json 的完整读改写事务。
fn mutate_openclaw_config<T>(mutator: impl FnOnce(&mut Value) -> AppResult<T>) -> AppResult<T> {
    let config_path = platform::get_config_file_path();
    mutate_openclaw_config_at(&config_path, &ConfigFileLock::path(), mutator)
}

fn mutate_openclaw_config_at<T>(
    config_path: &str,
    lock_path: &Path,
    mutator: impl FnOnce(&mut Value) -> AppResult<T>,
) -> AppResult<T> {
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire_at(lock_path, 200)?;
    let mut config = load_openclaw_config_at(config_path)?;
    if !config.is_object() {
        return Err(AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"));
    }
    let result = mutator(&mut config)?;
    save_openclaw_config_at(config_path, &config)?;
    Ok(result)
}

fn apply_env_mutations(env_path: &str, mutations: &[EnvMutation]) -> AppResult<()> {
    for mutation in mutations {
        let result = match mutation {
            EnvMutation::Set(key, value) => file::set_env_value(env_path, key, value),
            EnvMutation::Remove(key) => file::remove_env_value(env_path, key),
        };
        result.map_err(|error| AppError::io(format!("更新环境文件失败: {}", error)))?;
    }
    Ok(())
}

fn restore_file_snapshot(path: &str, existed: bool, content: &str) -> AppResult<()> {
    if existed {
        return file::write_file_atomic(path, content)
            .map_err(|error| AppError::io(format!("恢复环境文件失败: {}", error)));
    }
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(AppError::io(format!("恢复环境文件失败: {}", error))),
    }
}

fn mutate_env_file(mutations: &[EnvMutation]) -> AppResult<()> {
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire()?;
    let env_path = platform::get_env_file_path();
    let existed = file::file_exists(&env_path);
    let original = if existed {
        file::read_file(&env_path)
            .map_err(|error| AppError::io(format!("读取环境文件失败: {}", error)))?
    } else {
        String::new()
    };
    if let Err(error) = apply_env_mutations(&env_path, mutations) {
        restore_file_snapshot(&env_path, existed, &original)?;
        return Err(error);
    }
    Ok(())
}

/// 渠道配置同时修改 JSON 与 env 时，在同一操作锁内执行并在失败时恢复 env。
fn mutate_openclaw_config_and_env<T>(
    mutator: impl FnOnce(&mut Value) -> AppResult<(T, Vec<EnvMutation>)>,
) -> AppResult<T> {
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire()?;
    let config_path = platform::get_config_file_path();
    let env_path = platform::get_env_file_path();
    let mut config = load_openclaw_config_at(&config_path)?;
    if !config.is_object() {
        return Err(AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"));
    }
    let env_existed = file::file_exists(&env_path);
    let original_env = if env_existed {
        file::read_file(&env_path)
            .map_err(|error| AppError::io(format!("读取环境文件失败: {}", error)))?
    } else {
        String::new()
    };
    let (result, mutations) = mutator(&mut config)?;

    if let Err(error) = apply_env_mutations(&env_path, &mutations) {
        restore_file_snapshot(&env_path, env_existed, &original_env)?;
        return Err(error);
    }
    if let Err(error) = save_openclaw_config_at(&config_path, &config) {
        restore_file_snapshot(&env_path, env_existed, &original_env)?;
        return Err(error);
    }
    Ok(result)
}

/// WebView 通用保存只能修改非凭据配置，磁盘上的敏感区始终优先。
fn save_webview_config(config: &Value) -> AppResult<()> {
    if !config.is_object() {
        return Err(AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"));
    }
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire()?;
    let current = load_openclaw_config()?;
    let mut next = config.clone();
    preserve_webview_config_sections(&current, &mut next)?;
    save_openclaw_config_locked(&next)
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

        let api_key_value = provider_config.get("apiKey");
        let api_key = api_key_value
            .and_then(Value::as_str)
            .filter(|key| !key.is_empty())
            .map(str::to_string);

        let has_api_key = api_key_value.is_some_and(|value| {
            value.as_str().is_some_and(|key| !key.is_empty()) || parse_secret_ref(value).is_some()
        }) || has_provider_auth_profile(auth_profiles, provider_name);
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
pub async fn get_config() -> AppResult<Value> {
    info!("[获取配置] 读取 openclaw.json 配置...");
    let result = load_openclaw_config().map(|config| redact_config_for_webview(&config));
    match &result {
        Ok(_) => info!("[获取配置] ✓ 配置读取成功"),
        Err(e) => error!("[获取配置] ✗ 配置读取失败: {}", e),
    }
    result
}

/// 保存配置
#[command]
pub async fn save_config(config: Value) -> AppResult<String> {
    info!("[保存配置] 保存 openclaw.json 配置...");
    match save_webview_config(&config) {
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
pub async fn get_env_value(key: String) -> AppResult<Option<String>> {
    if !READABLE_ENV_KEYS.contains(&key.as_str()) {
        return Err(AppError::validation(format!(
            "环境变量 {} 不允许通过桌面端读取",
            key
        )));
    }
    info!("[获取环境变量] 读取环境变量: {}", key);
    let env_path = platform::get_env_file_path();
    let value = redact_env_value(&key, file::read_env_value(&env_path, &key));
    match &value {
        Some(v) => debug!(
            "[获取环境变量] {}={} (已脱敏)",
            key,
            if v.is_empty() { "(empty)" } else { "***" }
        ),
        None => debug!("[获取环境变量] {} 不存在", key),
    }
    Ok(value)
}

fn redact_env_value(key: &str, value: Option<String>) -> Option<String> {
    if !SENSITIVE_READ_ENV_KEYS.contains(&key) {
        return value;
    }
    value
        .filter(|secret| !secret.is_empty())
        .map(|_| SENSITIVE_ENV_MASK.to_string())
}

/// 保存环境变量值
#[command]
pub async fn save_env_value(key: String, value: String) -> AppResult<String> {
    validate_writable_env_value(&key, &value)?;
    info!("[保存环境变量] 保存环境变量: {}", key);
    let env_path = platform::get_env_file_path();
    debug!("[保存环境变量] 环境文件路径: {}", env_path);

    match mutate_env_file(&[EnvMutation::Set(key.clone(), value)]) {
        Ok(_) => {
            info!("[保存环境变量] ✓ 环境变量 {} 保存成功", key);
            Ok("环境变量已保存".to_string())
        }
        Err(e) => {
            error!("[保存环境变量] ✗ 保存失败: {}", e);
            Err(AppError::io(format!("保存环境变量失败: {}", e)))
        }
    }
}

fn validate_writable_env_value(key: &str, value: &str) -> AppResult<()> {
    if !WRITABLE_ENV_KEYS.contains(&key) {
        return Err(AppError::validation(format!(
            "环境变量 {} 不允许通过桌面端写入",
            key
        )));
    }
    if value.contains(['\r', '\n', '\0']) {
        return Err(AppError::validation("环境变量值不能包含换行符或 NUL"));
    }
    if SENSITIVE_READ_ENV_KEYS.contains(&key) && value == SENSITIVE_ENV_MASK {
        return Err(AppError::validation(
            "固定脱敏标记不能作为真实环境变量值保存",
        ));
    }
    Ok(())
}

// ============ Gateway Token 命令 ============

/// 使用系统密码学随机源生成 Gateway Token；随机源失败时拒绝降级。
fn generate_token_with<F>(fill_random: F) -> AppResult<String>
where
    F: FnOnce(&mut [u8]) -> Result<(), getrandom::Error>,
{
    let mut buf = [0u8; 48];
    fill_random(&mut buf).map_err(|e| {
        AppError::config(format!(
            "系统密码学随机源不可用，已拒绝生成 Gateway Token: {}",
            e
        ))
    })?;
    Ok(buf.iter().map(|b| format!("{:02x}", b)).collect())
}

fn generate_token() -> AppResult<String> {
    generate_token_with(getrandom::getrandom)
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum GatewayTokenConfig {
    Plain(String),
    SecretRef { source: String, id: String },
    OtherAuth,
    RemoteMode,
    Missing,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum GatewayTokenEnv {
    Override(String),
    RemoveOverride,
    Inherit,
}

fn parse_secret_ref(value: &Value) -> Option<(String, String)> {
    let Some(secret_ref) = value.as_object() else {
        return None;
    };
    let source = secret_ref.get("source").and_then(Value::as_str)?;
    if !matches!(source, "env" | "file" | "exec") {
        return None;
    }
    let provider_valid = secret_ref
        .get("provider")
        .and_then(Value::as_str)
        .is_some_and(|provider| !provider.is_empty());
    let id = secret_ref.get("id").and_then(Value::as_str)?;
    if !provider_valid || id.is_empty() {
        return None;
    }
    Some((source.to_string(), id.to_string()))
}

fn resolve_gateway_token<F>(
    config: &mut Value,
    token_factory: F,
    generate_if_missing: bool,
) -> AppResult<(GatewayTokenConfig, bool)>
where
    F: FnOnce() -> AppResult<String>,
{
    if !config.is_object() {
        return Err(AppError::validation("OpenClaw 配置根节点必须是 JSON 对象"));
    }
    let explicit_non_token_mode = config
        .pointer("/gateway/auth/mode")
        .and_then(Value::as_str)
        .is_some_and(|mode| mode != "token");
    let remote_mode = config.pointer("/gateway/mode").and_then(Value::as_str) == Some("remote");
    if remote_mode {
        return Ok((GatewayTokenConfig::RemoteMode, false));
    }
    if explicit_non_token_mode {
        return Ok((GatewayTokenConfig::OtherAuth, false));
    }
    match config.pointer("/gateway/auth/token") {
        Some(Value::String(token)) if !token.is_empty() => {
            return Ok((GatewayTokenConfig::Plain(token.clone()), false));
        }
        Some(Value::Null) | Some(Value::String(_)) | None => {}
        Some(value) => {
            if let Some((source, id)) = parse_secret_ref(value) {
                return Ok((GatewayTokenConfig::SecretRef { source, id }, false));
            }
            return Err(AppError::validation(
                "gateway.auth.token 必须是非空字符串或合法 SecretRef，已拒绝覆盖",
            ));
        }
    }

    let password_configured = config
        .pointer("/gateway/auth/password")
        .is_some_and(|value| {
            value.as_str().is_some_and(|password| !password.is_empty())
                || parse_secret_ref(value).is_some()
        });
    if password_configured {
        return Ok((GatewayTokenConfig::OtherAuth, false));
    }
    if !generate_if_missing {
        return Ok((GatewayTokenConfig::Missing, false));
    }

    let token = token_factory()?;
    set_gateway_auth(config, json!(token))?;
    config["gateway"]["auth"]["mode"] = json!("token");
    config["gateway"]["mode"] = json!("local");
    Ok((GatewayTokenConfig::Plain(token), true))
}

fn gateway_token_env_from_resolved(
    token: GatewayTokenConfig,
    generate_if_missing: bool,
) -> AppResult<GatewayTokenEnv> {
    match token {
        GatewayTokenConfig::Plain(token) => {
            info!("[Gateway Token] 使用同一份明文 Token 配置");
            Ok(GatewayTokenEnv::Override(token))
        }
        GatewayTokenConfig::SecretRef { source, .. } if source == "env" => {
            info!("[Gateway Token] 使用环境变量 SecretRef，由 OpenClaw 官方运行时处理");
            Ok(GatewayTokenEnv::Inherit)
        }
        GatewayTokenConfig::SecretRef { .. } => {
            info!("[Gateway Token] 使用 Provider SecretRef，由 OpenClaw 官方运行时处理");
            Ok(GatewayTokenEnv::RemoveOverride)
        }
        GatewayTokenConfig::OtherAuth => {
            info!("[Gateway Token] 当前使用非 Token 认证，由 OpenClaw 官方运行时处理");
            Ok(GatewayTokenEnv::RemoveOverride)
        }
        GatewayTokenConfig::RemoteMode if generate_if_missing => Err(AppError::conflict(
            "gateway.mode=remote，已拒绝启动本地 Gateway",
        )),
        GatewayTokenConfig::RemoteMode | GatewayTokenConfig::Missing => {
            Ok(GatewayTokenEnv::Inherit)
        }
    }
}

fn gateway_token_env_override(generate_if_missing: bool) -> AppResult<GatewayTokenEnv> {
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire()?;
    let mut config = load_openclaw_config()?;
    let (token, generated) =
        resolve_gateway_token(&mut config, generate_token, generate_if_missing)?;
    if generated {
        save_openclaw_config_locked(&config)?;
        info!("[Gateway Token] 已生成并保存新的强随机 Token");
    }
    gateway_token_env_from_resolved(token, generate_if_missing)
}

/// 普通 CLI 只读取现有认证，绝不因版本检查等命令改写 Gateway 配置。
pub(crate) fn get_gateway_token_env_override() -> AppResult<GatewayTokenEnv> {
    gateway_token_env_override(false)
}

/// 启动本地 Gateway 或打开 Dashboard 时，缺少认证才生成强随机 Token。
pub(crate) fn ensure_gateway_token_env_override() -> AppResult<GatewayTokenEnv> {
    gateway_token_env_override(true)
}

pub(crate) fn get_or_create_gateway_token_value() -> AppResult<String> {
    match ensure_gateway_token_env_override()? {
        GatewayTokenEnv::Override(token) => Ok(token),
        GatewayTokenEnv::RemoveOverride | GatewayTokenEnv::Inherit => Err(AppError::validation(
            "Gateway 凭据由官方运行时管理，桌面端不会导出明文",
        )),
    }
}

fn encode_url_fragment_component(value: &str) -> String {
    let mut encoded = String::with_capacity(value.len());
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
            encoded.push(byte as char);
        } else {
            encoded.push_str(&format!("%{:02X}", byte));
        }
    }
    encoded
}

fn dashboard_url_for_token(token: Option<&str>) -> String {
    match token {
        Some(token) => format!(
            "http://localhost:18789/#token={}",
            encode_url_fragment_component(token)
        ),
        None => "http://localhost:18789".to_string(),
    }
}

/// 获取或生成 Gateway Token
#[command]
pub async fn get_or_create_gateway_token() -> AppResult<String> {
    info!("[Gateway Token] 获取或创建 Gateway Token...");
    get_or_create_gateway_token_value()
}

/// 获取 Dashboard URL（带 token）
#[command]
pub async fn get_dashboard_url() -> AppResult<String> {
    info!("[Dashboard URL] 获取 Dashboard URL...");

    let url = match ensure_gateway_token_env_override()? {
        GatewayTokenEnv::Override(token) => dashboard_url_for_token(Some(&token)),
        GatewayTokenEnv::RemoveOverride | GatewayTokenEnv::Inherit => dashboard_url_for_token(None),
    };

    info!("[Dashboard URL] ✓ 已生成本地 URL");
    Ok(url)
}

#[cfg(test)]
mod gateway_token_tests {
    use super::*;

    #[test]
    fn strong_random_token_is_hex_encoded_without_fallback() {
        let token = generate_token_with(|buffer| {
            for (index, byte) in buffer.iter_mut().enumerate() {
                *byte = index as u8;
            }
            Ok(())
        })
        .expect("测试随机源应成功");

        assert_eq!(token.len(), 96);
        assert!(token.chars().all(|ch| ch.is_ascii_hexdigit()));
        assert!(token.starts_with("00010203"));
    }

    #[test]
    fn random_source_failure_is_fail_closed() {
        let error = generate_token_with(|_| Err(getrandom::Error::UNSUPPORTED))
            .expect_err("随机源失败时不得生成降级 Token");

        assert!(error.message.contains("已拒绝生成 Gateway Token"));
    }

    #[test]
    fn existing_gateway_token_is_reused_without_generation() {
        let mut config = json!({
            "gateway": {
                "mode": "local",
                "auth": { "mode": "token", "token": "existing-secure-token" }
            }
        });
        let (token, generated) =
            resolve_gateway_token(&mut config, || panic!("存在 Token 时不应调用随机源"), true)
                .expect("现有 Token 应可复用");

        assert_eq!(
            token,
            GatewayTokenConfig::Plain("existing-secure-token".to_string())
        );
        assert!(!generated);
        assert_eq!(config["gateway"]["mode"], "local");
    }

    #[test]
    fn missing_gateway_token_is_created_in_local_token_mode() {
        let mut config = json!({});
        let (token, generated) =
            resolve_gateway_token(&mut config, || Ok("new-secure-token".to_string()), true)
                .expect("缺少 Token 时应写入新 Token");

        assert_eq!(
            token,
            GatewayTokenConfig::Plain("new-secure-token".to_string())
        );
        assert!(generated);
        assert_eq!(config["gateway"]["auth"]["token"], "new-secure-token");
        assert_eq!(config["gateway"]["auth"]["mode"], "token");
        assert_eq!(config["gateway"]["mode"], "local");
    }

    #[test]
    fn generic_config_save_cannot_delete_or_rotate_existing_gateway_token() {
        let current = json!({
            "gateway": {
                "mode": "local",
                "auth": { "mode": "token", "token": "stable-runtime-token" }
            }
        });
        let mut reset = json!({
            "gateway": { "auth": { "token": "attacker-selected-token" } }
        });

        preserve_existing_gateway_auth(&current, &mut reset)
            .expect("合法对象应保留现有 Gateway 认证");

        assert_eq!(reset["gateway"]["auth"]["token"], "stable-runtime-token");
        assert_eq!(reset["gateway"]["auth"]["mode"], "token");
        assert_eq!(reset["gateway"]["mode"], "local");
    }

    #[test]
    fn generic_config_reset_preserves_all_gateway_secret_refs_and_providers() {
        let current = json!({
            "gateway": {
                "mode": "local",
                "auth": {
                    "mode": "token",
                    "token": { "source": "file", "provider": "local-token", "id": "value" },
                    "password": { "source": "env", "provider": "default", "id": "OPENCLAW_GATEWAY_PASSWORD" }
                },
                "remote": {
                    "url": "wss://gateway.example.test",
                    "transport": "ssh",
                    "sshTarget": "manager@gateway.example.test",
                    "tlsFingerprint": "sha256:stable-fingerprint",
                    "token": { "source": "exec", "provider": "vault", "id": "gateway/remote/token" },
                    "password": { "source": "file", "provider": "remote-password", "id": "/gateway/password" }
                }
            },
            "secrets": {
                "providers": {
                    "local-token": { "source": "file", "path": "/private/token", "mode": "singleValue" },
                    "vault": { "source": "exec", "command": "/usr/local/bin/read-vault" },
                    "remote-password": { "source": "file", "path": "/private/secrets.json" }
                }
            }
        });
        let mut reset = json!({
            "gateway": {
                "auth": { "token": "replacement-must-not-win" },
                "remote": {}
            },
            "secrets": {
                "providers": {
                    "new-provider": { "source": "env" },
                    "vault": { "source": "env", "mustNotReplaceExisting": true }
                }
            }
        });

        preserve_existing_gateway_auth(&current, &mut reset)
            .expect("重置配置必须保留全部 Gateway SecretRef");

        assert_eq!(
            reset.pointer("/gateway/auth/token"),
            current.pointer("/gateway/auth/token")
        );
        assert_eq!(
            reset.pointer("/gateway/auth/password"),
            current.pointer("/gateway/auth/password")
        );
        assert_eq!(
            reset.pointer("/gateway/remote"),
            current.pointer("/gateway/remote")
        );
        assert_eq!(
            reset.pointer("/secrets/providers/local-token"),
            current.pointer("/secrets/providers/local-token")
        );
        assert_eq!(
            reset.pointer("/secrets/providers/vault"),
            current.pointer("/secrets/providers/vault")
        );
        assert_eq!(
            reset.pointer("/secrets/providers/remote-password"),
            current.pointer("/secrets/providers/remote-password")
        );
        assert!(reset.pointer("/secrets/providers/new-provider").is_some());
    }

    #[test]
    fn webview_config_is_recursively_redacted_and_round_trip_preserves_disk_secrets() {
        let password_ref = json!({
            "source": "env",
            "provider": "default",
            "id": "OPENCLAW_GATEWAY_PASSWORD"
        });
        let current = json!({
            "gateway": {
                "mode": "local",
                "auth": {
                    "mode": "token",
                    "token": "raw-gateway-token",
                    "password": password_ref.clone()
                }
            },
            "models": {
                "providers": {
                    "custom": {
                        "baseUrl": "https://provider.example.test",
                        "apiKey": "raw-provider-key",
                        "models": [{ "id": "model", "maxTokens": 4096 }],
                        "headers": {
                            "Authorization": "Bearer raw-header-secret",
                            "X-Custom-Credential": "raw-custom-header-secret"
                        },
                        "request": {
                            "auth": { "type": "custom", "value": "raw-auth-value" },
                            "tls": { "key": "raw-tls-key", "cert": "raw-tls-cert" }
                        }
                    }
                }
            },
            "channels": {
                "telegram": {
                    "enabled": true,
                    "botToken": "raw-channel-token",
                    "accounts": { "ops": { "appSecret": "raw-channel-app-secret" } }
                },
                "googlechat": {
                    "serviceAccount": {
                        "client_email": "raw-service-account-email",
                        "private_key": "raw-service-account-key"
                    }
                }
            },
            "plugins": {
                "entries": {
                    "search": {
                        "config": {
                            "apiKey": "raw-plugin-key",
                            "mcpServers": { "worker": { "env": { "CUSTOM_CREDENTIAL": "raw-plugin-env" } } }
                        }
                    }
                }
            },
            "secrets": {
                "providers": {
                    "vault": { "source": "exec", "token": "raw-provider-config-token" }
                }
            },
            "tools": {
                "web": { "search": { "provider": "custom", "apiKey": "raw-tool-provider-key" } }
            },
            "notifications": { "error": false }
        });

        let webview = redact_config_for_webview(&current);
        let serialized = serde_json::to_string(&webview).expect("脱敏配置应可序列化");
        for raw_secret in [
            "raw-gateway-token",
            "raw-provider-key",
            "raw-header-secret",
            "raw-custom-header-secret",
            "raw-auth-value",
            "raw-tls-key",
            "raw-tls-cert",
            "raw-channel-token",
            "raw-channel-app-secret",
            "raw-service-account-email",
            "raw-service-account-key",
            "raw-plugin-key",
            "raw-plugin-env",
            "raw-provider-config-token",
            "raw-tool-provider-key",
        ] {
            assert!(!serialized.contains(raw_secret));
        }
        assert_eq!(
            webview.pointer("/models/providers/custom/apiKey"),
            Some(&json!(SENSITIVE_ENV_MASK))
        );
        assert_eq!(
            webview.pointer("/models/providers/custom/models/0/maxTokens"),
            Some(&json!(4096))
        );
        assert_eq!(
            webview.pointer("/gateway/auth/password"),
            Some(&password_ref)
        );

        let mut notification_save = webview.clone();
        notification_save["notifications"]["error"] = json!(true);
        preserve_webview_config_sections(&current, &mut notification_save)
            .expect("通用保存应恢复磁盘凭据");
        assert_eq!(
            notification_save.pointer("/models/providers/custom/apiKey"),
            current.pointer("/models/providers/custom/apiKey")
        );
        assert_eq!(
            notification_save.pointer("/channels/telegram/botToken"),
            current.pointer("/channels/telegram/botToken")
        );
        assert_eq!(
            notification_save.pointer("/plugins/entries/search/config/apiKey"),
            current.pointer("/plugins/entries/search/config/apiKey")
        );
        assert_eq!(notification_save["notifications"]["error"], true);

        let mut reset = json!({});
        preserve_webview_config_sections(&current, &mut reset).expect("重置必须保留磁盘敏感区");
        assert_eq!(reset["channels"], current["channels"]);
        assert_eq!(reset["plugins"], current["plugins"]);
        assert_eq!(reset["secrets"], current["secrets"]);
        assert_eq!(reset["tools"], current["tools"]);
        assert_eq!(
            reset.pointer("/models/providers"),
            current.pointer("/models/providers")
        );
        assert_eq!(
            reset.pointer("/gateway/auth/token"),
            current.pointer("/gateway/auth/token")
        );
    }

    #[test]
    fn webview_round_trip_preserves_sensitive_values_inside_arrays() {
        let current = json!({
            "hooks": {
                "mappings": [
                    {
                        "name": "alerts",
                        "sessionKey": "raw-hook-session-key",
                        "nested": [{ "token": "raw-nested-token", "label": "primary" }]
                    }
                ]
            },
            "notifications": { "error": false }
        });
        let mut submitted = redact_config_for_webview(&current);
        submitted["notifications"]["error"] = json!(true);

        assert_eq!(
            submitted.pointer("/hooks/mappings/0/sessionKey"),
            Some(&json!(SENSITIVE_ENV_MASK))
        );
        assert_eq!(
            submitted.pointer("/hooks/mappings/0/nested/0/token"),
            Some(&json!(SENSITIVE_ENV_MASK))
        );

        preserve_webview_config_sections(&current, &mut submitted)
            .expect("通用保存应恢复数组内的磁盘凭据");

        assert_eq!(
            submitted.pointer("/hooks/mappings/0/sessionKey"),
            current.pointer("/hooks/mappings/0/sessionKey")
        );
        assert_eq!(
            submitted.pointer("/hooks/mappings/0/nested/0/token"),
            current.pointer("/hooks/mappings/0/nested/0/token")
        );
        assert_eq!(submitted["notifications"]["error"], true);
    }

    #[test]
    fn provider_update_preserves_secret_ref_and_unmodeled_fields() {
        let secret_ref = json!({
            "source": "env",
            "provider": "default",
            "id": "CUSTOM_API_KEY"
        });
        let current = json!({
            "baseUrl": "https://old.example/v1",
            "apiKey": secret_ref.clone(),
            "headers": { "X-Tenant": "stable-tenant" },
            "request": { "auth": { "type": "custom", "value": "stable-auth" } },
            "models": [{ "id": "old-model" }]
        });

        let merged = merge_provider_config(
            Some(&current),
            "https://new.example/v1",
            None,
            vec![json!({ "id": "new-model" })],
        )
        .expect("未提交新密钥时应合并 Provider 配置");

        assert_eq!(merged["baseUrl"], "https://new.example/v1");
        assert_eq!(merged["models"], json!([{ "id": "new-model" }]));
        assert_eq!(merged["apiKey"], secret_ref);
        assert_eq!(merged["headers"], current["headers"]);
        assert_eq!(merged["request"], current["request"]);

        let providers = serde_json::Map::from_iter([("custom".to_string(), merged.clone())]);
        let configured = parse_configured_providers(&providers, &None, &None);
        assert!(configured[0].has_api_key);
        assert_eq!(configured[0].api_key_masked, None);

        let replaced = merge_provider_config(
            Some(&merged),
            "https://new.example/v1",
            Some("explicit-new-key"),
            vec![json!({ "id": "new-model" })],
        )
        .expect("明确提交的新密钥应覆盖旧 SecretRef");
        assert_eq!(replaced["apiKey"], "explicit-new-key");
    }

    #[test]
    fn channel_save_restores_nested_masks_instead_of_persisting_placeholders() {
        let current = json!({
            "botToken": "raw-bot-token",
            "accounts": {
                "ops": { "appSecret": "raw-app-secret", "label": "Ops" }
            }
        });
        let mut submitted = redact_config_for_webview(&current);
        submitted["accounts"]["ops"]["label"] = json!("Operations");

        assert!(value_contains_sensitive_mask(&submitted));
        restore_masked_config_values(&current, &mut submitted);

        assert!(!value_contains_sensitive_mask(&submitted));
        assert_eq!(submitted["botToken"], "raw-bot-token");
        assert_eq!(submitted["accounts"]["ops"]["appSecret"], "raw-app-secret");
        assert_eq!(submitted["accounts"]["ops"]["label"], "Operations");
    }

    #[test]
    fn secret_ref_is_preserved_and_never_replaced_with_plaintext() {
        let secret_ref = json!({
            "source": "file",
            "provider": "gateway-token-file",
            "id": "value"
        });
        let mut config = json!({
            "gateway": { "auth": { "mode": "token", "token": secret_ref.clone() } },
            "secrets": {
                "providers": {
                    "gateway-token-file": {
                        "source": "file",
                        "path": "/private/token",
                        "mode": "singleValue"
                    }
                }
            }
        });
        let (token, generated) = resolve_gateway_token(
            &mut config,
            || panic!("SecretRef 存在时不得生成或覆盖 Token"),
            true,
        )
        .expect("合法 SecretRef 应交给 OpenClaw 解析");

        assert_eq!(
            token,
            GatewayTokenConfig::SecretRef {
                source: "file".to_string(),
                id: "value".to_string(),
            }
        );
        assert!(!generated);
        assert_eq!(config["gateway"]["auth"]["token"], secret_ref);

        let mut reset = json!({});
        preserve_existing_gateway_auth(&config, &mut reset)
            .expect("通用保存必须保留 SecretRef 和 provider 配置");
        assert_eq!(reset["gateway"]["auth"]["token"], secret_ref);
        assert_eq!(reset["secrets"], config["secrets"]);
    }

    #[test]
    fn env_secret_ref_keeps_the_referenced_environment_key() {
        let mut config = json!({
            "gateway": {
                "auth": {
                    "mode": "token",
                    "token": {
                        "source": "env",
                        "provider": "default",
                        "id": "OPENCLAW_GATEWAY_TOKEN"
                    }
                }
            }
        });
        let (token, generated) = resolve_gateway_token(
            &mut config,
            || panic!("env SecretRef 存在时不得生成明文 Token"),
            true,
        )
        .expect("env SecretRef 应交给官方运行时解析");

        assert_eq!(
            token,
            GatewayTokenConfig::SecretRef {
                source: "env".to_string(),
                id: "OPENCLAW_GATEWAY_TOKEN".to_string(),
            }
        );
        assert!(!generated);
    }

    #[test]
    fn gateway_token_environment_policy_preserves_official_resolution_precedence() {
        assert_eq!(
            gateway_token_env_from_resolved(
                GatewayTokenConfig::Plain("plain-token".to_string()),
                false,
            )
            .expect("明文 Token 应覆盖进程环境"),
            GatewayTokenEnv::Override("plain-token".to_string())
        );
        assert_eq!(
            gateway_token_env_from_resolved(
                GatewayTokenConfig::SecretRef {
                    source: "env".to_string(),
                    id: "OPENCLAW_GATEWAY_TOKEN".to_string(),
                },
                false,
            )
            .expect("env SecretRef 应继承用户环境"),
            GatewayTokenEnv::Inherit
        );
        for source in ["file", "exec"] {
            assert_eq!(
                gateway_token_env_from_resolved(
                    GatewayTokenConfig::SecretRef {
                        source: source.to_string(),
                        id: "gateway-token".to_string(),
                    },
                    false,
                )
                .expect("Provider SecretRef 应由官方运行时解析"),
                GatewayTokenEnv::RemoveOverride
            );
        }
        assert_eq!(
            gateway_token_env_from_resolved(GatewayTokenConfig::RemoteMode, false)
                .expect("只读远程命令必须继承环境凭据"),
            GatewayTokenEnv::Inherit
        );
        assert_eq!(
            gateway_token_env_from_resolved(GatewayTokenConfig::OtherAuth, false)
                .expect("显式非 Token 模式应移除冲突的 Token 环境变量"),
            GatewayTokenEnv::RemoveOverride
        );
        assert!(gateway_token_env_from_resolved(GatewayTokenConfig::RemoteMode, true).is_err());
    }

    #[test]
    fn password_and_remote_modes_are_never_rewritten_as_local_token_auth() {
        let mut password_config = json!({
            "gateway": {
                "mode": "local",
                "auth": {
                    "mode": "password",
                    "password": {
                        "source": "env",
                        "provider": "default",
                        "id": "OPENCLAW_GATEWAY_PASSWORD"
                    },
                    "token": "stale-token-must-not-win"
                }
            }
        });
        let original_password = password_config.clone();
        let (password_auth, generated) = resolve_gateway_token(
            &mut password_config,
            || panic!("password 模式不得生成 Token"),
            true,
        )
        .expect("password 模式应交给 OpenClaw 处理");
        assert_eq!(password_auth, GatewayTokenConfig::OtherAuth);
        assert!(!generated);
        assert_eq!(password_config, original_password);

        let mut remote_config = json!({
            "gateway": {
                "mode": "remote",
                "auth": { "mode": "token", "token": "local-token-must-not-win" },
                "remote": {
                    "token": {
                        "source": "env",
                        "provider": "default",
                        "id": "OPENCLAW_GATEWAY_TOKEN"
                    },
                    "password": {
                        "source": "file",
                        "provider": "remote-password",
                        "id": "/gateway/password"
                    }
                }
            }
        });
        let original_remote = remote_config.clone();
        let (remote_auth, generated) = resolve_gateway_token(
            &mut remote_config,
            || panic!("remote 模式不得生成本地 Token"),
            true,
        )
        .expect("remote 模式应保持不变");
        assert_eq!(remote_auth, GatewayTokenConfig::RemoteMode);
        assert!(!generated);
        assert_eq!(remote_config, original_remote);

        for mode in ["none", "trusted-proxy"] {
            let mut config = json!({ "gateway": { "auth": { "mode": mode } } });
            let original = config.clone();
            let (auth, generated) = resolve_gateway_token(
                &mut config,
                || panic!("显式非 Token 认证模式不得生成 Token"),
                true,
            )
            .expect("显式非 Token 认证模式应保持不变");
            assert_eq!(auth, GatewayTokenConfig::OtherAuth);
            assert!(!generated);
            assert_eq!(config, original);
        }
    }

    #[test]
    fn read_only_cli_auth_lookup_never_initializes_missing_token() {
        let mut config = json!({});
        let (auth, generated) =
            resolve_gateway_token(&mut config, || panic!("只读 CLI 查询不得生成 Token"), false)
                .expect("缺少认证时只读查询应返回 Missing");

        assert_eq!(auth, GatewayTokenConfig::Missing);
        assert!(!generated);
        assert_eq!(config, json!({}));
    }

    #[test]
    fn dashboard_token_uses_the_official_encoded_fragment_contract() {
        assert_eq!(
            dashboard_url_for_token(Some("token+with/&symbols")),
            "http://localhost:18789/#token=token%2Bwith%2F%26symbols"
        );
        assert_eq!(dashboard_url_for_token(None), "http://localhost:18789");
    }

    #[test]
    fn scalar_config_is_rejected_without_panicking() {
        let mut scalar = json!("invalid");
        let error = resolve_gateway_token(&mut scalar, || Ok("unused".to_string()), true)
            .expect_err("标量配置必须 fail-closed");

        assert!(error.message.contains("根节点必须是 JSON 对象"));
    }

    #[test]
    fn config_file_lock_serializes_multiple_app_instances() {
        let path = std::env::temp_dir().join(format!(
            "openclaw-manager-config-lock-{}.lock",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        let first = ConfigFileLock::acquire_at(&path, 1).expect("首次应取得文件锁");
        let second =
            ConfigFileLock::acquire_at(&path, 1).expect_err("第二个应用实例不得并发取得文件锁");
        assert!(second.message.contains("拒绝并发写入"));

        drop(first);
        ConfigFileLock::acquire_at(&path, 1).expect("释放后应能重新取得文件锁");
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn config_transaction_preserves_concurrent_independent_updates() {
        let root = std::env::temp_dir().join(format!(
            "openclaw-manager-config-transaction-{}",
            std::process::id()
        ));
        let config_path = root.join("openclaw.json");
        let lock_path = root.join("openclaw.lock");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("应创建事务测试目录");
        file::write_file_atomic(
            config_path.to_str().expect("配置测试路径必须是 UTF-8"),
            "{}",
        )
        .expect("应写入初始配置");

        let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
        let handles: Vec<_> = ["provider", "channel"]
            .into_iter()
            .map(|key| {
                let barrier = barrier.clone();
                let config_path = config_path.clone();
                let lock_path = lock_path.clone();
                std::thread::spawn(move || {
                    barrier.wait();
                    mutate_openclaw_config_at(
                        config_path.to_str().expect("配置测试路径必须是 UTF-8"),
                        &lock_path,
                        |config| {
                            std::thread::sleep(std::time::Duration::from_millis(20));
                            if config.get("manager").is_none() {
                                config["manager"] = json!({});
                            }
                            config["manager"][key] = json!(true);
                            Ok(())
                        },
                    )
                    .expect("并发配置事务应成功");
                })
            })
            .collect();
        for handle in handles {
            handle.join().expect("并发配置线程不应崩溃");
        }

        let saved =
            load_openclaw_config_at(config_path.to_str().expect("配置测试路径必须是 UTF-8"))
                .expect("应读取事务结果");
        assert_eq!(saved.pointer("/manager/provider"), Some(&json!(true)));
        assert_eq!(saved.pointer("/manager/channel"), Some(&json!(true)));
        let _ = std::fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn env_write_command_rejects_removed_ibkr_fields_and_multiline_values() {
        let read_removed_field = get_env_value("IBKR_START_CMD".to_string())
            .await
            .expect_err("已移除的 IBKR shell 字段不得读取");
        assert!(read_removed_field.message.contains("不允许通过桌面端读取"));

        let removed_field =
            save_env_value("IBKR_START_CMD".to_string(), "bash -c unsafe".to_string())
                .await
                .expect_err("已移除的 IBKR shell 字段不得写入");
        assert!(removed_field.message.contains("不允许通过桌面端写入"));

        let multiline = save_env_value(
            "LLM_API_KEY".to_string(),
            "safe\nIBKR_START_CMD=bash -c unsafe".to_string(),
        )
        .await
        .expect_err("环境变量写入不得跨行注入");
        assert!(multiline.message.contains("不能包含换行符"));
    }

    #[test]
    fn sensitive_env_values_are_redacted_before_crossing_ipc() {
        for key in SENSITIVE_READ_ENV_KEYS {
            assert_eq!(
                redact_env_value(key, Some("real-secret-must-not-reach-webview".to_string())),
                Some(SENSITIVE_ENV_MASK.to_string())
            );
            assert_eq!(redact_env_value(key, Some(String::new())), None);
        }
        assert_eq!(
            redact_env_value("LOG_LEVEL", Some("debug".to_string())),
            Some("debug".to_string())
        );
        assert_eq!(
            redact_env_value("OPENCLAW_PORT", Some("18789".to_string())),
            Some("18789".to_string())
        );
        assert_eq!(
            redact_env_value("IBKR_ACCOUNT", Some("DU123456".to_string())),
            Some("DU123456".to_string())
        );
    }

    #[test]
    fn sensitive_env_mask_cannot_be_written_back_as_a_real_secret() {
        let error = validate_writable_env_value("LLM_API_KEY", SENSITIVE_ENV_MASK)
            .expect_err("固定脱敏标记不得覆盖真实密钥");
        assert!(error.message.contains("脱敏标记"));
        validate_writable_env_value("LLM_API_KEY", "a-new-real-secret")
            .expect("真实单行密钥应允许保存");
    }
}

#[command]
pub async fn get_project_context() -> AppResult<ProjectContext> {
    let config = load_openclaw_config()?;
    get_project_context_from_config(&config)
}

#[command]
pub async fn get_app_settings() -> AppResult<AppSettings> {
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
        .or_else(|| {
            config
                .pointer("/manager/security/enableWhitelist")
                .and_then(|v| v.as_bool())
        })
        .unwrap_or(defaults.security.enable_whitelist);

    defaults.security.allow_file_access = local_settings
        .pointer("/security/allowFileAccess")
        .and_then(|v| v.as_bool())
        .or_else(|| {
            config
                .pointer("/manager/security/allowFileAccess")
                .and_then(|v| v.as_bool())
        })
        .unwrap_or(defaults.security.allow_file_access);

    Ok(defaults)
}

#[command]
pub async fn save_app_settings(settings: AppSettings) -> AppResult<String> {
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
        .map_err(|e| AppError::serialization(format!("序列化本地设置失败: {}", e)))?;
    file::write_file(&context.settings_file, &local_settings_content)
        .map_err(|e| AppError::io(format!("写入本地设置失败: {}", e)))?;

    sync_workspace_identity_files(&context, &settings)?;
    Ok("设置已保存".to_string())
}

#[command]
pub async fn open_macos_full_disk_access_settings() -> AppResult<String> {
    if !platform::is_macos() {
        return Err(AppError::validation("该功能仅支持 macOS"));
    }

    let url = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles";
    let status = Command::new("open")
        .arg(url)
        .status()
        .map_err(|e| AppError::process(format!("打开系统设置失败: {}", e)))?;

    if status.success() {
        Ok("已打开\u{201c}完全磁盘访问权限\u{201d}设置页".to_string())
    } else {
        Err(AppError::process(
            "无法打开系统设置，请手动前往\u{201c}隐私与安全性 -> 完全磁盘访问权限\u{201d}",
        ))
    }
}

// ============ AI 配置相关命令 ============

/// 获取官方 Provider 列表（预设模板）
#[command]
pub async fn get_official_providers() -> AppResult<Vec<OfficialProvider>> {
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
            suggested_models: vec![SuggestedModel {
                id: "glm-4".to_string(),
                name: "GLM-4".to_string(),
                description: Some("最新旗舰模型".to_string()),
                context_window: Some(128000),
                max_tokens: Some(8192),
                recommended: true,
            }],
        },
        OfficialProvider {
            id: "minimax".to_string(),
            name: "MiniMax".to_string(),
            icon: "🟡".to_string(),
            default_base_url: Some("https://api.minimax.io/anthropic".to_string()),
            api_type: "anthropic-messages".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/minimax".to_string()),
            suggested_models: vec![SuggestedModel {
                id: "minimax-m2.1".to_string(),
                name: "MiniMax M2.1".to_string(),
                description: Some("最新模型".to_string()),
                context_window: Some(200000),
                max_tokens: Some(8192),
                recommended: true,
            }],
        },
        OfficialProvider {
            id: "venice".to_string(),
            name: "Venice AI".to_string(),
            icon: "🏛️".to_string(),
            default_base_url: Some("https://api.venice.ai/api/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/venice".to_string()),
            suggested_models: vec![SuggestedModel {
                id: "llama-3.3-70b".to_string(),
                name: "Llama 3.3 70B".to_string(),
                description: Some("隐私优先推理".to_string()),
                context_window: Some(128000),
                max_tokens: Some(8192),
                recommended: true,
            }],
        },
        OfficialProvider {
            id: "openrouter".to_string(),
            name: "OpenRouter".to_string(),
            icon: "🔄".to_string(),
            default_base_url: Some("https://openrouter.ai/api/v1".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: true,
            docs_url: Some("https://docs.openclaw.ai/providers/openrouter".to_string()),
            suggested_models: vec![SuggestedModel {
                id: "anthropic/claude-opus-4-5".to_string(),
                name: "Claude Opus 4.5".to_string(),
                description: Some("通过 OpenRouter 访问".to_string()),
                context_window: Some(200000),
                max_tokens: Some(8192),
                recommended: true,
            }],
        },
        OfficialProvider {
            id: "ollama".to_string(),
            name: "Ollama (本地)".to_string(),
            icon: "🟠".to_string(),
            default_base_url: Some("http://localhost:11434".to_string()),
            api_type: "openai-completions".to_string(),
            requires_api_key: false,
            docs_url: Some("https://docs.openclaw.ai/providers/ollama".to_string()),
            suggested_models: vec![SuggestedModel {
                id: "llama3".to_string(),
                name: "Llama 3".to_string(),
                description: Some("本地运行".to_string()),
                context_window: Some(8192),
                max_tokens: Some(4096),
                recommended: true,
            }],
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
pub async fn get_ai_config() -> AppResult<AIConfigOverview> {
    info!("[AI 配置] 获取 AI 配置概览...");

    let config_path = platform::get_config_file_path();
    info!("[AI 配置] 配置文件路径: {}", config_path);

    let config = load_openclaw_config()?;

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
        info!(
            "[AI 配置] 从 openclaw.json 读取到 {} 个 Provider",
            providers.len()
        );
        configured_providers = parse_configured_providers(providers, &primary_model, &None);
    }

    if configured_providers.is_empty() {
        info!("[AI 配置] openclaw.json 中 providers 为空，尝试从 agent/models.json 回退读取");
        if let Some((providers, agent_name)) = read_agent_models_providers(&config) {
            let auth_profiles = load_agent_auth_profiles(&agent_name);
            configured_providers =
                parse_configured_providers(&providers, &primary_model, &auth_profiles);
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

/// 将桌面端明确提交的字段合并到现有 Provider 配置。
fn merge_provider_config(
    current: Option<&Value>,
    base_url: &str,
    api_key: Option<&str>,
    models: Vec<Value>,
) -> AppResult<Value> {
    let mut provider = match current {
        Some(value) if value.is_object() => value.clone(),
        Some(_) => return Err(AppError::validation("Provider 配置必须是 JSON 对象")),
        None => json!({}),
    };

    provider["baseUrl"] = json!(base_url);
    provider["models"] = Value::Array(models);

    if let Some(key) = api_key.filter(|key| !key.is_empty()) {
        if key == SENSITIVE_ENV_MASK {
            return Err(AppError::validation(
                "固定脱敏标记不能作为真实 Provider API Key 保存",
            ));
        }
        let echoes_existing_mask = provider
            .get("apiKey")
            .and_then(Value::as_str)
            .is_some_and(|existing| mask_secret(existing) == key);
        if !echoes_existing_mask {
            provider["apiKey"] = json!(key);
        }
    }

    Ok(provider)
}

/// 添加或更新 Provider
#[command]
pub async fn save_provider(
    provider_name: String,
    base_url: String,
    api_key: Option<String>,
    api_type: String,
    models: Vec<ModelConfig>,
) -> AppResult<String> {
    info!(
        "[保存 Provider] 保存 Provider: {} ({} 个模型)",
        provider_name,
        models.len()
    );

    mutate_openclaw_config(|config| {
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

        // 从最新磁盘对象合并明确提交字段，保留 SecretRef、headers 等官方扩展。
        let current_provider = config["models"]["providers"].get(&provider_name).cloned();
        let provider_config = merge_provider_config(
            current_provider.as_ref(),
            &base_url,
            api_key.as_deref(),
            models_json,
        )?;
        if api_key.as_deref().is_some_and(|key| !key.is_empty()) {
            info!("[保存 Provider] 已处理明确提交的 API Key");
        } else if provider_config.get("apiKey").is_some() {
            info!("[保存 Provider] 保留原有的 API Key/SecretRef");
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

        Ok(())
    })?;
    info!("[保存 Provider] ✓ Provider {} 保存成功", provider_name);

    Ok(format!("Provider {} 已保存", provider_name))
}

/// 删除 Provider
#[command]
pub async fn delete_provider(provider_name: String) -> AppResult<String> {
    info!("[删除 Provider] 删除 Provider: {}", provider_name);

    mutate_openclaw_config(|config| {
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

        Ok(())
    })?;
    info!("[删除 Provider] ✓ Provider {} 已删除", provider_name);

    Ok(format!("Provider {} 已删除", provider_name))
}

/// 设置主模型
#[command]
pub async fn set_primary_model(model_id: String) -> AppResult<String> {
    info!("[设置主模型] 设置主模型: {}", model_id);

    mutate_openclaw_config(|config| {
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
        config["agents"]["defaults"]["model"]["primary"] = json!(model_id.clone());

        Ok(())
    })?;
    info!("[设置主模型] ✓ 主模型已设置为: {}", model_id);

    Ok(format!("主模型已设置为 {}", model_id))
}

/// 添加模型到可用列表
#[command]
pub async fn add_available_model(model_id: String) -> AppResult<String> {
    info!("[添加模型] 添加模型到可用列表: {}", model_id);

    mutate_openclaw_config(|config| {
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

        Ok(())
    })?;
    info!("[添加模型] ✓ 模型 {} 已添加", model_id);

    Ok(format!("模型 {} 已添加", model_id))
}

/// 从可用列表移除模型
#[command]
pub async fn remove_available_model(model_id: String) -> AppResult<String> {
    info!("[移除模型] 从可用列表移除模型: {}", model_id);

    mutate_openclaw_config(|config| {
        if let Some(models) = config
            .pointer_mut("/agents/defaults/models")
            .and_then(|v| v.as_object_mut())
        {
            models.remove(&model_id);
        }

        Ok(())
    })?;
    info!("[移除模型] ✓ 模型 {} 已移除", model_id);

    Ok(format!("模型 {} 已移除", model_id))
}

// ============ 旧版兼容 ============

/// 获取所有支持的 AI Provider（旧版兼容）
#[command]
pub async fn get_ai_providers() -> AppResult<Vec<crate::models::AIProviderOption>> {
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
pub async fn get_channels_config() -> AppResult<Vec<ChannelConfig>> {
    info!("[渠道配置] 获取渠道配置列表...");

    // 联合读取必须与 JSON/env 写事务共用锁，避免返回跨版本快照。
    let _guard = OPENCLAW_CONFIG_LOCK
        .lock()
        .map_err(|_| AppError::config("OpenClaw 配置锁已损坏，已拒绝继续"))?;
    let _file_guard = ConfigFileLock::acquire()?;
    let config = load_openclaw_config()?;
    let channels_obj = config
        .get("channels")
        .map(redact_config_for_webview)
        .unwrap_or_else(|| json!({}));
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

        channels.push(ChannelConfig {
            id: channel_id.to_string(),
            channel_type: channel_type.to_string(),
            enabled,
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
pub async fn save_channel_config(channel: ChannelConfig) -> AppResult<String> {
    info!(
        "[保存渠道配置] 保存渠道配置: {} ({})",
        channel.id, channel.channel_type
    );

    let result = mutate_openclaw_config_and_env(|config| {
        let mut env_mutations = Vec::new();

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

        // 从磁盘原值开始更新，未展示在表单里的官方字段和凭据不会被误删。
        let mut channel_obj = config
            .get("channels")
            .and_then(Value::as_object)
            .and_then(|channels| channels.get(&channel.id))
            .filter(|channel| channel.is_object())
            .cloned()
            .unwrap_or_else(|| json!({}));
        channel_obj["enabled"] = json!(channel.enabled);

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
                    env_mutations.push(EnvMutation::Set(env_key, val_str.to_string()));
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
                    env_mutations.push(EnvMutation::Set(env_key, val_str.to_string()));
                }
            } else {
                // 保存到 openclaw.json
                let mut next_value = value.clone();
                if value_contains_sensitive_mask(&next_value) {
                    if let Some(current_value) = channel_obj.get(key) {
                        restore_masked_config_values(current_value, &mut next_value);
                    }
                    if value_contains_sensitive_mask(&next_value) {
                        return Err(AppError::validation(
                            "脱敏占位符不能作为渠道凭据保存，请输入新凭据或保持原值",
                        ));
                    }
                }
                channel_obj[key] = next_value;
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

        Ok(((), env_mutations))
    });

    // 保存配置
    info!("[保存渠道配置] 写入配置文件...");
    match result {
        Ok(_) => {
            info!("[保存渠道配置] ✓ {} 配置保存成功", channel.channel_type);
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
pub async fn clear_channel_config(channel_id: String) -> AppResult<String> {
    info!("[清空渠道配置] 清空渠道配置: {}", channel_id);

    let result = mutate_openclaw_config_and_env(|config| {
        // 从 channels 对象中删除该渠道
        if let Some(channels) = config.get_mut("channels").and_then(|v| v.as_object_mut()) {
            channels.remove(&channel_id);
            info!("[清空渠道配置] 已从 channels 中删除: {}", channel_id);
        }

        // 从 plugins.allow 数组中删除
        if let Some(allow_arr) = config
            .pointer_mut("/plugins/allow")
            .and_then(|v| v.as_array_mut())
        {
            allow_arr.retain(|v| v.as_str() != Some(&channel_id));
            info!("[清空渠道配置] 已从 plugins.allow 中删除: {}", channel_id);
        }

        // 从 plugins.entries 中删除
        if let Some(entries) = config
            .pointer_mut("/plugins/entries")
            .and_then(|v| v.as_object_mut())
        {
            entries.remove(&channel_id);
            info!("[清空渠道配置] 已从 plugins.entries 中删除: {}", channel_id);
        }

        // 清除相关的环境变量
        let env_mutations = vec![
            format!("OPENCLAW_{}_USERID", channel_id.to_uppercase()),
            format!("OPENCLAW_{}_TESTCHATID", channel_id.to_uppercase()),
            format!("OPENCLAW_{}_TESTCHANNELID", channel_id.to_uppercase()),
        ]
        .into_iter()
        .map(EnvMutation::Remove)
        .collect();

        Ok(((), env_mutations))
    });

    // 保存配置
    match result {
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
pub async fn check_feishu_plugin() -> AppResult<FeishuPluginStatus> {
    info!("[飞书插件] 检查飞书插件安装状态...");

    // 执行 openclaw plugins list 命令
    match shell::run_openclaw(&["plugins", "list"]) {
        Ok(output) => {
            debug!("[飞书插件] plugins list 输出: {}", output);

            // 查找包含 feishu 的行（不区分大小写）
            let lines: Vec<&str> = output.lines().collect();
            let feishu_line = lines
                .iter()
                .find(|line| line.to_lowercase().contains("feishu"));

            if let Some(line) = feishu_line {
                info!("[飞书插件] ✓ 飞书插件已安装: {}", line);

                // 尝试解析版本号（通常格式为 "name@version" 或 "name version"）
                let version = if line.contains('@') {
                    line.rsplit('@').next().map(|s| s.trim().to_string())
                } else {
                    // 尝试匹配版本号模式 (如 0.1.2)
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    parts
                        .iter()
                        .find(|p| {
                            p.chars()
                                .next()
                                .map(|c| c.is_ascii_digit())
                                .unwrap_or(false)
                        })
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
pub async fn install_feishu_plugin() -> AppResult<String> {
    info!("[飞书插件] 开始安装飞书插件...");

    // 先检查是否已安装
    let status = check_feishu_plugin().await?;
    if status.installed {
        info!("[飞书插件] 飞书插件已安装，跳过");
        return Ok(format!(
            "飞书插件已安装: {}",
            status.plugin_name.unwrap_or_default()
        ));
    }

    // npm 已禁止覆盖已发布版本；固定版本可避免按钮在不同日期安装不同代码。
    info!("[飞书插件] 执行 openclaw plugins install @m1heng-clawd/feishu@0.1.19 ...");
    match shell::run_openclaw(&["plugins", "install", "@m1heng-clawd/feishu@0.1.19"]) {
        Ok(output) => {
            info!("[飞书插件] 安装输出: {}", output);

            // 验证安装结果
            let verify_status = check_feishu_plugin().await?;
            if verify_status.installed {
                info!("[飞书插件] ✓ 飞书插件安装成功");
                Ok(format!(
                    "飞书插件安装成功: {}",
                    verify_status.plugin_name.unwrap_or_default()
                ))
            } else {
                warn!("[飞书插件] 安装命令执行成功但插件未找到");
                Err(AppError::process(
                    "安装命令执行成功但插件未找到，请检查 openclaw 版本",
                ))
            }
        }
        Err(e) => {
            error!("[飞书插件] ✗ 安装失败: {}", e);
            Err(AppError::process(format!(
                "安装飞书插件失败: {}\n\n请手动执行: openclaw plugins install @m1heng-clawd/feishu@0.1.19",
                e
            )))
        }
    }
}

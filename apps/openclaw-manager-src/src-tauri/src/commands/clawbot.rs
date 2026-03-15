use crate::utils::shell;
use log::{info, warn};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::path::Path;
use std::process::Command;
use std::time::Duration;
use tauri::command;

const CLAWBOT_ENV_KEYS: [&str; 10] = [
    "G4F_BASE_URL",
    "KIRO_BASE_URL",
    "IBKR_HOST",
    "IBKR_PORT",
    "IBKR_ACCOUNT",
    "IBKR_BUDGET",
    "IBKR_AUTOSTART",
    "IBKR_START_CMD",
    "IBKR_STOP_CMD",
    "NOTIFY_CHAT_ID",
];

const IBKR_MANAGED_LABEL: &str = "com.clawbot.ibkr";
const IBKR_MANAGED_NAME: &str = "IBKR Gateway";
const IBKR_DEFAULT_START_CMD: &str = "open -a \"IB Gateway\"";
const IBKR_DEFAULT_STOP_CMD: &str =
    "pkill -f \"IB Gateway\" || pkill -f \"Trader Workstation\" || true";

const CLAWBOT_BOT_DEFINITIONS: [(&str, &str, &str, &str, &str, &str); 6] = [
    (
        "qwen235b",
        "Qwen 235B",
        "QWEN235B_TOKEN",
        "QWEN235B_USERNAME",
        "g4f",
        "qwen-3-235b",
    ),
    (
        "gptoss",
        "GPT-OSS 120B",
        "GPTOSS_TOKEN",
        "GPTOSS_USERNAME",
        "g4f",
        "gpt-oss-120b",
    ),
    (
        "claude-sonnet",
        "Claude Sonnet",
        "CLAUDE_SONNET_TOKEN",
        "CLAUDE_SONNET_USERNAME",
        "kiro",
        "claude-3.7-sonnet",
    ),
    (
        "claude-haiku",
        "Claude Haiku",
        "CLAUDE_HAIKU_TOKEN",
        "CLAUDE_HAIKU_USERNAME",
        "kiro",
        "claude-3.5-sonnet",
    ),
    (
        "deepseek-v3",
        "DeepSeek V3",
        "DEEPSEEK_V3_TOKEN",
        "DEEPSEEK_V3_USERNAME",
        "siliconflow",
        "deepseek-v3.2",
    ),
    (
        "claude-opus",
        "Claude Opus",
        "CLAUDE_OPUS_TOKEN",
        "CLAUDE_OPUS_USERNAME",
        "claude-proxy",
        "claude-opus-4-6",
    ),
];

const OPENCLAW_MAIN_AGENT_ID: &str = "main";

#[derive(Debug, Clone)]
struct ManagedServiceDefinition {
    label: String,
    name: String,
    plist_path: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ManagedServiceStatus {
    pub label: String,
    pub name: String,
    pub running: bool,
    pub pid: Option<u32>,
    pub plist_path: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ManagedEndpointStatus {
    pub id: String,
    pub name: String,
    pub address: String,
    pub healthy: bool,
    pub error: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ClawbotBotMatrixEntry {
    pub id: String,
    pub name: String,
    pub token_key: String,
    pub username_key: String,
    pub username: String,
    pub token_configured: bool,
    pub token_masked: Option<String>,
    pub route_provider: String,
    pub route_model: String,
    pub route_base_url: String,
    pub ready: bool,
}

fn get_home_dir() -> Result<String, String> {
    dirs::home_dir()
        .map(|p| p.display().to_string())
        .ok_or_else(|| "无法获取用户 Home 目录".to_string())
}

fn get_base_dir() -> Result<String, String> {
    let home = get_home_dir()?;
    Ok(format!("{}/Desktop/OpenClaw Bot", home))
}

fn get_managed_services() -> Result<Vec<ManagedServiceDefinition>, String> {
    let base_dir = get_base_dir()?;
    let launchagents_dir = format!("{}/tools/launchagents", base_dir);

    Ok(vec![
        ManagedServiceDefinition {
            label: "ai.openclaw.gateway".to_string(),
            name: "OpenClaw Gateway".to_string(),
            plist_path: format!("{}/ai.openclaw.gateway.plist", launchagents_dir),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.g4f".to_string(),
            name: "ClawBot g4f".to_string(),
            plist_path: format!("{}/ai.openclaw.g4f.plist", launchagents_dir),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.kiro-gateway".to_string(),
            name: "ClawBot Kiro Gateway".to_string(),
            plist_path: format!("{}/ai.openclaw.kiro-gateway.plist", launchagents_dir),
        },
        ManagedServiceDefinition {
            label: IBKR_MANAGED_LABEL.to_string(),
            name: IBKR_MANAGED_NAME.to_string(),
            plist_path: "custom://ibkr".to_string(),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.clawbot-agent".to_string(),
            name: "ClawBot Agent".to_string(),
            plist_path: format!("{}/ai.openclaw.clawbot-agent.plist", launchagents_dir),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.xianyu".to_string(),
            name: "闲鱼 AI 客服".to_string(),
            plist_path: format!("{}/ai.openclaw.xianyu.plist", launchagents_dir),
        },
    ])
}

fn get_uid() -> Result<String, String> {
    let output = Command::new("id")
        .arg("-u")
        .output()
        .map_err(|e| format!("获取用户 UID 失败: {}", e))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(format!("获取用户 UID 失败: {}", err));
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn launchctl_target(uid: &str, label: &str) -> String {
    format!("gui/{}/{}", uid, label)
}

fn launchctl_domain(uid: &str) -> String {
    format!("gui/{}", uid)
}

fn run_launchctl(args: &[&str]) -> Result<String, String> {
    let output = Command::new("launchctl")
        .args(args)
        .output()
        .map_err(|e| format!("执行 launchctl 失败: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if output.status.success() {
        Ok(stdout)
    } else {
        Err(format!("{}{}", stdout, stderr).trim().to_string())
    }
}

fn parse_pid(launchctl_print_output: &str) -> Option<u32> {
    for line in launchctl_print_output.lines() {
        let trimmed = line.trim();
        if let Some(pid_str) = trimmed.strip_prefix("pid = ") {
            if let Ok(pid) = pid_str.trim().parse::<u32>() {
                return Some(pid);
            }
        }
    }
    None
}

fn query_service_status(uid: &str, definition: &ManagedServiceDefinition) -> ManagedServiceStatus {
    if definition.label == IBKR_MANAGED_LABEL {
        return query_ibkr_status(definition);
    }

    let target = launchctl_target(uid, &definition.label);
    let output = Command::new("launchctl").args(["print", target.as_str()]).output();

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let running = stdout.contains("state = running") || stdout.contains("state = xpcproxy");
            let pid = parse_pid(&stdout);
            ManagedServiceStatus {
                label: definition.label.clone(),
                name: definition.name.clone(),
                running,
                pid,
                plist_path: definition.plist_path.clone(),
            }
        }
        _ => ManagedServiceStatus {
            label: definition.label.clone(),
            name: definition.name.clone(),
            running: false,
            pid: None,
            plist_path: definition.plist_path.clone(),
        },
    }
}

fn is_bootstrap_conflict(err: &str) -> bool {
    let lower = err.to_lowercase();
    lower.contains("service already loaded")
        || lower.contains("already exists")
        || lower.contains("in progress")
        || lower.contains("bootstrap failed: 5")
}

fn is_bootout_missing(err: &str) -> bool {
    let lower = err.to_lowercase();
    lower.contains("could not find service")
        || lower.contains("no such process")
        || lower.contains("not loaded")
}

fn bootout_service(uid: &str, definition: &ManagedServiceDefinition) -> Result<(), String> {
    let domain = launchctl_domain(uid);
    match run_launchctl(&["bootout", domain.as_str(), definition.plist_path.as_str()]) {
        Ok(_) => Ok(()),
        Err(err) => {
            if is_bootout_missing(&err) {
                Ok(())
            } else {
                Err(err)
            }
        }
    }
}

fn bootstrap_service(uid: &str, definition: &ManagedServiceDefinition) -> Result<(), String> {
    let domain = launchctl_domain(uid);
    match run_launchctl(&["bootstrap", domain.as_str(), definition.plist_path.as_str()]) {
        Ok(_) => Ok(()),
        Err(err) => {
            if is_bootstrap_conflict(&err) {
                Ok(())
            } else {
                Err(err)
            }
        }
    }
}

fn kickstart_service(uid: &str, definition: &ManagedServiceDefinition) -> Result<(), String> {
    let target = launchctl_target(uid, &definition.label);
    run_launchctl(&["kickstart", "-k", target.as_str()]).map(|_| ())
}

fn find_service_definition(label: &str) -> Result<ManagedServiceDefinition, String> {
    let definitions = get_managed_services()?;
    definitions
        .into_iter()
        .find(|s| s.label == label)
        .ok_or_else(|| format!("未找到服务: {}", label))
}

fn parse_env_content(content: &str) -> HashMap<String, String> {
    let mut values = HashMap::new();
    for raw_line in content.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((k, v)) = line.split_once('=') {
            values.insert(
                k.trim().to_string(),
                v.trim().trim_matches('"').trim_matches('\'').to_string(),
            );
        }
    }
    values
}

fn normalize_shell_command(value: &str) -> String {
    value
        .trim()
        .chars()
        .map(|ch| match ch {
            '“' | '”' | '„' | '‟' => '"',
            '‘' | '’' | '‚' | '‛' => '\'',
            '\u{00A0}' => ' ',
            _ => ch,
        })
        .collect()
}

fn set_or_append_env_line(lines: &mut Vec<String>, key: &str, value: &str) {
    let mut updated = false;
    for line in lines.iter_mut() {
        if let Some((left, _)) = line.split_once('=') {
            if left.trim() == key {
                *line = format!("{}={}", key, value);
                updated = true;
                break;
            }
        }
    }

    if !updated {
        lines.push(format!("{}={}", key, value));
    }
}

fn get_clawbot_env_path() -> Result<String, String> {
    let base_dir = get_base_dir()?;
    Ok(format!("{}/packages/clawbot/config/.env", base_dir))
}

fn get_service_log_path(label: &str) -> Result<String, String> {
    let base_dir = get_base_dir()?;
    let path = match label {
        "ai.openclaw.gateway" => format!("{}/.openclaw/logs/gateway.log", base_dir),
        "ai.openclaw.clawbot-agent" => format!("{}/packages/clawbot/logs/com-clawbot-agent.stderr.log", base_dir),
        "ai.openclaw.g4f" => format!("{}/packages/clawbot/logs/com-clawbot-g4f.stderr.log", base_dir),
        "ai.openclaw.kiro-gateway" => {
            format!("{}/packages/clawbot/logs/com-clawbot-kiro-gateway.stderr.log", base_dir)
        }
        "ai.openclaw.xianyu" => {
            format!("{}/packages/clawbot/logs/com-clawbot-xianyu.stderr.log", base_dir)
        }
        _ => return Err(format!("未知服务标签: {}", label)),
    };
    Ok(path)
}

fn last_lines(content: &str, n: usize) -> Vec<String> {
    let lines: Vec<String> = content.lines().map(|s| s.to_string()).collect();
    let start = lines.len().saturating_sub(n);
    lines[start..].to_vec()
}

fn parse_socket_addr(host: &str, port: &str) -> Result<SocketAddr, String> {
    let port_num = port
        .parse::<u16>()
        .map_err(|_| format!("端口格式无效: {}", port))?;
    let mut resolved = (host, port_num)
        .to_socket_addrs()
        .map_err(|e| format!("地址解析失败 {}:{}: {}", host, port_num, e))?;
    resolved
        .next()
        .ok_or_else(|| format!("地址解析结果为空: {}:{}", host, port_num))
}

fn check_tcp(addr: SocketAddr) -> Result<(), String> {
    TcpStream::connect_timeout(&addr, Duration::from_secs(2))
        .map(|_| ())
        .map_err(|e| e.to_string())
}

fn parse_env_bool(value: Option<&String>, default_value: bool) -> bool {
    let Some(raw) = value else {
        return default_value;
    };
    matches!(
        raw.trim().to_lowercase().as_str(),
        "1" | "true" | "yes" | "on"
    )
}

fn load_clawbot_env_map() -> Result<HashMap<String, String>, String> {
    let env_path = get_clawbot_env_path()?;
    let content =
        fs::read_to_string(&env_path).map_err(|e| format!("读取 ClawBot 配置失败: {}", e))?;
    Ok(parse_env_content(&content))
}

fn get_openclaw_config_path() -> Result<String, String> {
    let base_dir = get_base_dir()?;
    Ok(format!("{}/.openclaw/openclaw.json", base_dir))
}

fn load_openclaw_config() -> Result<Value, String> {
    let cfg_path = get_openclaw_config_path()?;
    let content = fs::read_to_string(&cfg_path)
        .map_err(|e| format!("读取 OpenClaw 配置失败: {}", e))?;
    serde_json::from_str(&content).map_err(|e| format!("解析 OpenClaw 配置失败: {}", e))
}

fn get_openclaw_main_matrix_entry() -> Result<Option<ClawbotBotMatrixEntry>, String> {
    let cfg = load_openclaw_config()?;
    let agents = cfg
        .get("agents")
        .and_then(|v| v.get("list"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let Some(main_agent) = agents.iter().find(|entry| {
        entry
            .get("id")
            .and_then(|v| v.as_str())
            .map(|id| id == OPENCLAW_MAIN_AGENT_ID)
            .unwrap_or(false)
    }) else {
        return Ok(None);
    };

    let primary = main_agent
        .get("model")
        .and_then(|v| v.get("primary"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if primary.is_empty() {
        return Ok(None);
    }

    let (provider_id, model_id) = primary
        .split_once('/')
        .map(|(provider, model)| (provider.to_string(), model.to_string()))
        .unwrap_or_else(|| ("unknown".to_string(), primary.clone()));

    let route_base_url = cfg
        .get("models")
        .and_then(|v| v.get("providers"))
        .and_then(|v| v.get(&provider_id))
        .and_then(|v| v.get("baseUrl"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    Ok(Some(ClawbotBotMatrixEntry {
        id: "openclaw-main".to_string(),
        name: "OpenClaw Brain".to_string(),
        token_key: "OPENCLAW_MAIN_MODEL".to_string(),
        username_key: "OPENCLAW_MAIN_AGENT".to_string(),
        username: "@carven_OpenClaw_Bot".to_string(),
        token_configured: true,
        token_masked: Some(model_id.clone()),
        route_provider: provider_id,
        route_model: model_id,
        route_base_url: route_base_url.clone(),
        ready: !route_base_url.is_empty(),
    }))
}

fn get_ibkr_host_port(env_map: &HashMap<String, String>) -> (String, String) {
    let host = env_map
        .get("IBKR_HOST")
        .cloned()
        .unwrap_or_else(|| "127.0.0.1".to_string());
    let port = env_map
        .get("IBKR_PORT")
        .cloned()
        .unwrap_or_else(|| "4002".to_string());
    (host, port)
}

fn is_ibkr_reachable(env_map: &HashMap<String, String>) -> Result<(), String> {
    let (host, port) = get_ibkr_host_port(env_map);
    let addr = parse_socket_addr(&host, &port)?;
    check_tcp(addr)
}

fn get_default_ibkr_start_cmd() -> String {
    if let Ok(base_dir) = get_base_dir() {
        let script_path = format!("{}/packages/clawbot/scripts/start_ibkr_gateway.sh", base_dir);
        if Path::new(&script_path).exists() {
            return format!("bash \"{}\"", script_path);
        }
    }
    IBKR_DEFAULT_START_CMD.to_string()
}

fn get_default_ibkr_stop_cmd() -> String {
    if let Ok(base_dir) = get_base_dir() {
        let script_path = format!("{}/packages/clawbot/scripts/stop_ibkr_gateway.sh", base_dir);
        if Path::new(&script_path).exists() {
            return format!("bash \"{}\"", script_path);
        }
    }
    IBKR_DEFAULT_STOP_CMD.to_string()
}

fn query_ibkr_status(definition: &ManagedServiceDefinition) -> ManagedServiceStatus {
    let env_map = load_clawbot_env_map().unwrap_or_default();
    let running = is_ibkr_reachable(&env_map).is_ok();
    ManagedServiceStatus {
        label: definition.label.clone(),
        name: definition.name.clone(),
        running,
        pid: None,
        plist_path: definition.plist_path.clone(),
    }
}

fn control_ibkr_service(action: &str) -> Result<String, String> {
    let env_map = load_clawbot_env_map()?;
    let (host, port) = get_ibkr_host_port(&env_map);
    let start_cmd_raw = env_map
        .get("IBKR_START_CMD")
        .cloned()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(get_default_ibkr_start_cmd);
    let stop_cmd_raw = env_map
        .get("IBKR_STOP_CMD")
        .cloned()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(get_default_ibkr_stop_cmd);
    let start_cmd = normalize_shell_command(&start_cmd_raw);
    let stop_cmd = normalize_shell_command(&stop_cmd_raw);

    if start_cmd != start_cmd_raw {
        info!("[IBKR] 启动命令已自动规范化引号: {} -> {}", start_cmd_raw, start_cmd);
    }
    if stop_cmd != stop_cmd_raw {
        info!("[IBKR] 停止命令已自动规范化引号: {} -> {}", stop_cmd_raw, stop_cmd);
    }

    match action {
        "start" => {
            shell::run_script_output(&start_cmd)
                .map_err(|e| format!("执行 IBKR 启动命令失败: {}", e))?;
            Ok(format!(
                "IBKR 启动命令已执行（{}），等待端口 {}:{} 就绪",
                start_cmd, host, port
            ))
        }
        "stop" => {
            shell::run_script_output(&stop_cmd)
                .map_err(|e| format!("执行 IBKR 停止命令失败: {}", e))?;
            Ok("IBKR 停止命令已执行".to_string())
        }
        "restart" => {
            shell::run_script_output(&stop_cmd)
                .map_err(|e| format!("执行 IBKR 停止命令失败: {}", e))?;
            shell::run_script_output(&start_cmd)
                .map_err(|e| format!("执行 IBKR 启动命令失败: {}", e))?;
            Ok(format!(
                "IBKR 已重启（{}），等待端口 {}:{} 就绪",
                start_cmd, host, port
            ))
        }
        _ => Err(format!("不支持的操作: {}", action)),
    }
}

fn should_autostart_ibkr(action: &str) -> Result<bool, String> {
    if action != "start" && action != "restart" {
        return Ok(true);
    }
    let env_map = load_clawbot_env_map()?;
    Ok(parse_env_bool(env_map.get("IBKR_AUTOSTART"), true))
}

fn mask_secret(value: &str) -> String {
    if value.len() <= 8 {
        return "****".to_string();
    }
    format!("{}...{}", &value[..4], &value[value.len() - 4..])
}

fn get_route_base_url(provider: &str, env_map: &HashMap<String, String>) -> String {
    match provider {
        "g4f" => env_map.get("G4F_BASE_URL").cloned().unwrap_or_default(),
        "kiro" => env_map.get("KIRO_BASE_URL").cloned().unwrap_or_default(),
        "siliconflow" => env_map
            .get("SILICONFLOW_BASE_URL")
            .cloned()
            .unwrap_or_default(),
        "claude-proxy" => env_map.get("CLAUDE_BASE_URL").cloned().unwrap_or_default(),
        _ => String::new(),
    }
}

#[command]
pub async fn get_managed_services_status() -> Result<Vec<ManagedServiceStatus>, String> {
    let uid = get_uid()?;
    let definitions = get_managed_services()?;

    let statuses = definitions
        .iter()
        .map(|definition| query_service_status(&uid, definition))
        .collect();

    Ok(statuses)
}

#[command]
pub async fn control_managed_service(label: String, action: String) -> Result<String, String> {
    if label == IBKR_MANAGED_LABEL {
        info!("[总控] 服务操作: {} -> {}", label, action);
        return control_ibkr_service(&action);
    }

    let uid = get_uid()?;
    let definition = find_service_definition(&label)?;

    info!("[总控] 服务操作: {} -> {}", label, action);

    match action.as_str() {
        "start" => {
            let status = query_service_status(&uid, &definition);
            if status.running {
                kickstart_service(&uid, &definition)?;
                return Ok(format!("{} 已在运行", definition.name));
            }
            bootstrap_service(&uid, &definition)?;
            kickstart_service(&uid, &definition)?;
            Ok(format!("{} 已启动", definition.name))
        }
        "stop" => {
            bootout_service(&uid, &definition)?;
            Ok(format!("{} 已停止", definition.name))
        }
        "restart" => {
            let _ = bootout_service(&uid, &definition);
            bootstrap_service(&uid, &definition)?;
            kickstart_service(&uid, &definition)?;
            Ok(format!("{} 已重启", definition.name))
        }
        _ => Err(format!("不支持的操作: {}", action)),
    }
}

#[command]
pub async fn control_all_managed_services(action: String) -> Result<String, String> {
    let mut services = get_managed_services()?;

    if action == "stop" {
        services.reverse();
    }

    let mut messages = Vec::new();

    for service in services {
        if service.label == IBKR_MANAGED_LABEL && !should_autostart_ibkr(&action)? {
            messages.push("IBKR 自动启动开关关闭，跳过 IBKR 操作".to_string());
            continue;
        }

        match control_managed_service(service.label.clone(), action.clone()).await {
            Ok(msg) => messages.push(msg),
            Err(err) => {
                warn!("[总控] 操作失败 {}: {}", service.label, err);
                messages.push(format!("{}: {}", service.name, err));
            }
        }
    }

    Ok(messages.join("\n"))
}

#[command]
pub async fn get_clawbot_runtime_config() -> Result<HashMap<String, String>, String> {
    let parsed = load_clawbot_env_map()?;

    let mut result = HashMap::new();
    for key in CLAWBOT_ENV_KEYS {
        result.insert(
            key.to_string(),
            parsed.get(key).cloned().unwrap_or_default(),
        );
    }

    Ok(result)
}

#[command]
pub async fn get_openclaw_usage_snapshot() -> Result<Value, String> {
    let output = shell::run_openclaw(&["status", "--usage", "--json"])?;
    let parsed: Value = serde_json::from_str(output.trim())
        .map_err(|e| format!("解析 openclaw usage 输出失败: {}", e))?;

    Ok(parsed
        .get("usage")
        .cloned()
        .unwrap_or_else(|| json!({ "providers": [] })))
}

#[command]
pub async fn get_clawbot_bot_matrix() -> Result<Vec<ClawbotBotMatrixEntry>, String> {
    let env_path = get_clawbot_env_path()?;
    let content = fs::read_to_string(&env_path)
        .map_err(|e| format!("读取 ClawBot 配置失败: {}", e))?;
    let env_map = parse_env_content(&content);

    let mut entries = Vec::new();
    for (id, name, token_key, username_key, route_provider, route_model) in CLAWBOT_BOT_DEFINITIONS {
        let token = env_map.get(token_key).cloned().unwrap_or_default();
        let username = env_map.get(username_key).cloned().unwrap_or_default();
        let token_configured = !token.is_empty();
        let route_base_url = get_route_base_url(route_provider, &env_map);
        let ready = token_configured && !username.is_empty() && !route_base_url.is_empty();

        entries.push(ClawbotBotMatrixEntry {
            id: id.to_string(),
            name: name.to_string(),
            token_key: token_key.to_string(),
            username_key: username_key.to_string(),
            username,
            token_configured,
            token_masked: if token_configured {
                Some(mask_secret(&token))
            } else {
                None
            },
            route_provider: route_provider.to_string(),
            route_model: route_model.to_string(),
            route_base_url,
            ready,
        });
    }

    if let Some(openclaw_main) = get_openclaw_main_matrix_entry()? {
        entries.insert(0, openclaw_main);
    }

    Ok(entries)
}

#[command]
pub async fn save_clawbot_runtime_config(values: HashMap<String, String>) -> Result<String, String> {
    let env_path = get_clawbot_env_path()?;
    let content = fs::read_to_string(&env_path)
        .map_err(|e| format!("读取 ClawBot 配置失败: {}", e))?;
    let mut lines: Vec<String> = content.lines().map(|s| s.to_string()).collect();

    for key in CLAWBOT_ENV_KEYS {
        if let Some(value) = values.get(key) {
            let normalized_value = match key {
                "IBKR_START_CMD" | "IBKR_STOP_CMD" => normalize_shell_command(value),
                _ => value.to_string(),
            };
            set_or_append_env_line(&mut lines, key, &normalized_value);
        }
    }

    fs::write(&env_path, lines.join("\n"))
        .map_err(|e| format!("保存 ClawBot 配置失败: {}", e))?;

    Ok("ClawBot 配置已保存".to_string())
}

#[command]
pub async fn get_managed_service_logs(label: String, lines: Option<u32>) -> Result<Vec<String>, String> {
    if label == IBKR_MANAGED_LABEL {
        let env_map = load_clawbot_env_map()?;
        let (host, port) = get_ibkr_host_port(&env_map);
        let reachable = is_ibkr_reachable(&env_map).is_ok();
        return Ok(vec![
            "IBKR 属于外部客户端服务（无 LaunchAgent 日志文件）".to_string(),
            format!("当前探测地址: {}:{}", host, port),
            format!("端口状态: {}", if reachable { "Reachable" } else { "Unreachable" }),
            format!(
                "IBKR_AUTOSTART={} | IBKR_START_CMD={} | IBKR_STOP_CMD={}",
                env_map
                    .get("IBKR_AUTOSTART")
                    .cloned()
                    .unwrap_or_else(|| "true".to_string()),
                env_map
                    .get("IBKR_START_CMD")
                    .cloned()
                    .unwrap_or_else(get_default_ibkr_start_cmd),
                env_map
                    .get("IBKR_STOP_CMD")
                    .cloned()
                    .unwrap_or_else(get_default_ibkr_stop_cmd),
            ),
        ]);
    }

    let n = lines.unwrap_or(120) as usize;
    let log_path = get_service_log_path(&label)?;
    let content = fs::read_to_string(&log_path)
        .map_err(|e| format!("读取日志失败 ({}): {}", log_path, e))?;
    Ok(last_lines(&content, n))
}

#[command]
pub async fn get_managed_endpoints_status() -> Result<Vec<ManagedEndpointStatus>, String> {
    let env_map = load_clawbot_env_map()?;
    let (ibkr_host, ibkr_port) = get_ibkr_host_port(&env_map);

    let targets = vec![
        (
            "openclaw-gateway".to_string(),
            "OpenClaw Gateway".to_string(),
            "127.0.0.1".to_string(),
            "18789".to_string(),
        ),
        (
            "clawbot-g4f".to_string(),
            "ClawBot g4f".to_string(),
            "127.0.0.1".to_string(),
            "18891".to_string(),
        ),
        (
            "clawbot-kiro".to_string(),
            "ClawBot Kiro Gateway".to_string(),
            "127.0.0.1".to_string(),
            "18793".to_string(),
        ),
        (
            "ibkr".to_string(),
            "IBKR".to_string(),
            ibkr_host,
            ibkr_port,
        ),
    ];

    let mut results = Vec::new();
    for (id, name, host, port) in targets {
        let address = format!("{}:{}", host, port);
        let status = match parse_socket_addr(&host, &port) {
            Ok(socket_addr) => match check_tcp(socket_addr) {
                Ok(_) => ManagedEndpointStatus {
                    id,
                    name,
                    address,
                    healthy: true,
                    error: None,
                },
                Err(err) => ManagedEndpointStatus {
                    id,
                    name,
                    address,
                    healthy: false,
                    error: Some(err),
                },
            },
            Err(err) => ManagedEndpointStatus {
                id,
                name,
                address,
                healthy: false,
                error: Some(err),
            },
        };
        results.push(status);
    }

    Ok(results)
}

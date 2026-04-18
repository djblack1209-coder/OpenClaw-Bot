use crate::utils::shell;
use super::config::{get_home_dir, mask_secret};
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

// 安全加固: IBKR_START_CMD / IBKR_STOP_CMD 已移除（前端可写的命令直接通过 bash -c 执行=RCE 风险）
// 这两个值只能通过手动编辑 .env 文件设置
const CLAWBOT_ENV_KEYS: [&str; 8] = [
    "G4F_BASE_URL",
    "KIRO_BASE_URL",
    "IBKR_HOST",
    "IBKR_PORT",
    "IBKR_ACCOUNT",
    "IBKR_BUDGET",
    "IBKR_AUTOSTART",
    "NOTIFY_CHAT_ID",
];

const IBKR_MANAGED_LABEL: &str = "com.clawbot.ibkr";
const IBKR_MANAGED_NAME: &str = "IBKR Gateway";
const IBKR_DEFAULT_START_CMD: &str = "open -a \"IB Gateway\"";
const IBKR_DEFAULT_STOP_CMD: &str =
    "pkill -f \"IB Gateway\" || pkill -f \"Trader Workstation\" || true";

const CLAWBOT_BOT_DEFINITIONS: [(&str, &str, &str, &str, &str, &str); 7] = [
    (
        "qwen235b",
        "Qwen 235B",
        "QWEN235B_TOKEN",
        "QWEN235B_USERNAME",
        "free_pool",
        "qwen-3-235b",
    ),
    (
        "gptoss",
        "GPT-OSS 120B",
        "GPTOSS_TOKEN",
        "GPTOSS_USERNAME",
        "free_pool",
        "gpt-oss-120b",
    ),
    (
        "claude-sonnet",
        "Claude Sonnet 4.5",
        "CLAUDE_SONNET_TOKEN",
        "CLAUDE_SONNET_USERNAME",
        "free_pool",
        "claude-sonnet-4-5",
    ),
    (
        "claude-haiku",
        "Claude Haiku 4.5",
        "CLAUDE_HAIKU_TOKEN",
        "CLAUDE_HAIKU_USERNAME",
        "free_pool",
        "claude-haiku-4-5",
    ),
    (
        "deepseek-v3",
        "DeepSeek V3.2",
        "DEEPSEEK_V3_TOKEN",
        "DEEPSEEK_V3_USERNAME",
        "free_pool",
        "deepseek-v3.2",
    ),
    (
        "claude-opus",
        "Claude Opus 4.5",
        "CLAUDE_OPUS_TOKEN",
        "CLAUDE_OPUS_USERNAME",
        "free_first",
        "claude-opus-4-5",
    ),
    (
        "free-llm",
        "Free LLM",
        "FREE_LLM_TOKEN",
        "FREE_LLM_USERNAME",
        "free_pool",
        "free-pool-best",
    ),
];

const OPENCLAW_MAIN_AGENT_ID: &str = "main";

/// 服务定义：包含 launchd 标签、显示名、plist 路径、监听端口和启动脚本路径
#[derive(Debug, Clone)]
struct ManagedServiceDefinition {
    label: String,
    name: String,
    plist_path: String,
    /// 服务监听端口，用于在 launchd 不可用时通过端口探活判断服务状态
    port: Option<u16>,
    /// 启动脚本路径，当 launchd 被 macOS 后台任务管理屏蔽时，用 bash 直接启动
    launcher_script: Option<String>,
    /// 日志输出路径（stdout）
    stdout_log: Option<String>,
    /// 日志输出路径（stderr）
    stderr_log: Option<String>,
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

// get_home_dir 已提取至 config.rs，通过 use super::config::get_home_dir 导入

fn get_base_dir() -> Result<String, String> {
    // 优先从环境变量 OPENCLAW_PROJECT_DIR 获取项目根目录，支持部署到任意路径
    if let Ok(dir) = std::env::var("OPENCLAW_PROJECT_DIR") {
        if !dir.is_empty() {
            return Ok(dir);
        }
    }
    let home = get_home_dir()?;
    Ok(format!("{}/Desktop/OpenClaw Bot", home))
}

fn get_managed_services() -> Result<Vec<ManagedServiceDefinition>, String> {
    let base_dir = get_base_dir()?;
    let launchagents_dir = format!("{}/tools/launchagents", base_dir);
    let logs_dir = format!("{}/packages/clawbot/logs", base_dir);
    let openclaw_logs_dir = format!("{}/.openclaw/logs", base_dir);

    Ok(vec![
        ManagedServiceDefinition {
            label: "ai.openclaw.gateway".to_string(),
            name: "OpenClaw Gateway".to_string(),
            plist_path: format!("{}/ai.openclaw.gateway.plist", launchagents_dir),
            port: Some(18789),
            launcher_script: Some(format!("{}/gateway-launcher.sh", launchagents_dir)),
            stdout_log: Some(format!("{}/gateway.log", openclaw_logs_dir)),
            stderr_log: Some(format!("{}/gateway.err.log", openclaw_logs_dir)),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.g4f".to_string(),
            name: "ClawBot g4f".to_string(),
            plist_path: format!("{}/ai.openclaw.g4f.plist", launchagents_dir),
            port: Some(18891),
            launcher_script: Some(format!("{}/g4f-launcher.sh", launchagents_dir)),
            stdout_log: Some(format!("{}/com-clawbot-g4f.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-g4f.stderr.log", logs_dir)),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.kiro-gateway".to_string(),
            name: "ClawBot Kiro Gateway".to_string(),
            plist_path: format!("{}/ai.openclaw.kiro-gateway.plist", launchagents_dir),
            port: Some(18793),
            launcher_script: Some(format!("{}/kiro-gateway-launcher.sh", launchagents_dir)),
            stdout_log: Some(format!("{}/com-clawbot-kiro-gateway.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-kiro-gateway.stderr.log", logs_dir)),
        },
        ManagedServiceDefinition {
            label: IBKR_MANAGED_LABEL.to_string(),
            name: IBKR_MANAGED_NAME.to_string(),
            plist_path: "custom://ibkr".to_string(),
            port: None, // IBKR 端口从 .env 动态读取
            launcher_script: None,
            stdout_log: None,
            stderr_log: None,
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.clawbot-agent".to_string(),
            name: "ClawBot Agent".to_string(),
            plist_path: format!("{}/ai.openclaw.clawbot-agent.plist", launchagents_dir),
            port: Some(18790), // 内部 API 端口
            launcher_script: Some(format!("{}/packages/clawbot/scripts/start_clawbot.sh", base_dir)),
            stdout_log: Some(format!("{}/com-clawbot-agent.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-agent.stderr.log", logs_dir)),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.xianyu".to_string(),
            name: "闲鱼 AI 客服".to_string(),
            plist_path: format!("{}/ai.openclaw.xianyu.plist", launchagents_dir),
            port: None, // 闲鱼客服是 WebSocket 客户端，不监听端口
            launcher_script: Some(format!("{}/packages/clawbot/scripts/start_xianyu.sh", base_dir)),
            stdout_log: Some(format!("{}/com-clawbot-xianyu.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-xianyu.stderr.log", logs_dir)),
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

/// 通过 lsof 查找监听指定端口的进程 PID（用于非 launchd 启动的服务）
fn find_pid_by_port(port: u16) -> Option<u32> {
    let output = Command::new("lsof")
        .args(["-i", &format!(":{}", port), "-sTCP:LISTEN", "-t"])
        .output();
    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            // lsof -t 返回 PID 列表（每行一个），取第一个
            stdout.lines().next().and_then(|s| s.trim().parse::<u32>().ok())
        }
        _ => None,
    }
}

/// 通过启动脚本直接启动服务（macOS 后台任务管理屏蔽 launchd 时的 fallback）
///
/// macOS 26+ 的 com.apple.provenance 安全策略会阻止 launchd/Tauri 进程
/// 执行带有 provenance 属性的脚本文件（退出码 126: Operation not permitted）。
///
/// 解决方案：读取脚本内容 → 通过 stdin 管道传给 bash，绕过文件执行权限检查。
fn start_service_via_script(definition: &ManagedServiceDefinition) -> Result<String, String> {
    let script = definition.launcher_script.as_ref()
        .ok_or_else(|| format!("{} 未配置启动脚本，无法通过进程方式启动", definition.name))?;

    // 读取脚本文件内容（读取不受 provenance 限制，只有执行才被拦截）
    let script_content = std::fs::read_to_string(script)
        .map_err(|e| format!("读取启动脚本失败 {}: {}", script, e))?;

    // 将 exec 替换掉：exec 在 stdin 管道模式下行为不同，直接执行即可
    let adjusted_content = script_content.replace("exec ", "");

    let stdout_log = definition.stdout_log.as_deref().unwrap_or("/dev/null");
    let stderr_log = definition.stderr_log.as_deref().unwrap_or("/dev/null");

    // 构造外层命令：nohup bash 从 stdin 读取脚本内容并后台执行
    // 使用 heredoc 方式避免任何 shell 转义问题
    let wrapper = format!(
        "nohup bash <<'__OPENCLAW_SCRIPT_EOF__' > \"{}\" 2> \"{}\" &\n{}\n__OPENCLAW_SCRIPT_EOF__",
        stdout_log, stderr_log, adjusted_content
    );

    let output = Command::new("bash")
        .args(["-c", &wrapper])
        .output()
        .map_err(|e| format!("执行启动脚本失败: {}", e))?;

    if output.status.success() {
        Ok(format!("{} 已通过启动脚本启动", definition.name))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("{} 启动脚本执行失败: {}", definition.name, stderr.trim()))
    }
}

/// 停止通过脚本启动的服务（通过端口找到 PID 并 kill）
/// 使用 tokio::time::sleep 替代 std::thread::sleep，避免阻塞 tokio 工作线程
async fn stop_service_via_pid(definition: &ManagedServiceDefinition) -> Result<String, String> {
    let port = definition.port
        .ok_or_else(|| format!("{} 未配置端口，无法通过进程方式停止", definition.name))?;

    let pid = find_pid_by_port(port)
        .ok_or_else(|| format!("{} 未找到监听端口 {} 的进程", definition.name, port))?;

    // 先发 SIGTERM（优雅关闭），进程不响应再 SIGKILL
    let output = Command::new("kill")
        .args(["-TERM", &pid.to_string()])
        .output()
        .map_err(|e| format!("发送停止信号失败: {}", e))?;

    if output.status.success() {
        // 等待进程退出（异步等待，不阻塞 tokio 线程）
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        // 检查进程是否还在
        if find_pid_by_port(port).is_some() {
            // 强制杀死
            let _ = Command::new("kill").args(["-KILL", &pid.to_string()]).output();
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
        Ok(format!("{} 已停止 (PID: {})", definition.name, pid))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("{} 停止失败: {}", definition.name, stderr.trim()))
    }
}

/// 查询服务运行状态
/// 优先用 launchctl print 检测 launchd 状态，如果 launchd 不可用（被 macOS 后台任务管理屏蔽），
/// 则降级为端口探活 + 进程名匹配方式判断服务是否在运行
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
            // launchd 报告服务已加载但未运行时，再用端口探活兜底（防止 launchd 状态不准）
            if !running {
                if let Some(port) = definition.port {
                    let addr_str = format!("127.0.0.1:{}", port);
                    if let Ok(addr) = addr_str.parse::<SocketAddr>() {
                        if check_tcp(addr).is_ok() {
                            // 端口可达说明服务实际在运行（可能通过非 launchd 方式启动）
                            let fallback_pid = find_pid_by_port(port);
                            return ManagedServiceStatus {
                                label: definition.label.clone(),
                                name: definition.name.clone(),
                                running: true,
                                pid: fallback_pid,
                                plist_path: definition.plist_path.clone(),
                            };
                        }
                    }
                }
            }
            ManagedServiceStatus {
                label: definition.label.clone(),
                name: definition.name.clone(),
                running,
                pid,
                plist_path: definition.plist_path.clone(),
            }
        }
        _ => {
            // launchctl print 失败（服务未加载或被屏蔽），用端口探活作为 fallback
            if let Some(port) = definition.port {
                let addr_str = format!("127.0.0.1:{}", port);
                if let Ok(addr) = addr_str.parse::<SocketAddr>() {
                    if check_tcp(addr).is_ok() {
                        let fallback_pid = find_pid_by_port(port);
                        return ManagedServiceStatus {
                            label: definition.label.clone(),
                            name: definition.name.clone(),
                            running: true,
                            pid: fallback_pid,
                            plist_path: definition.plist_path.clone(),
                        };
                    }
                }
            }
            ManagedServiceStatus {
                label: definition.label.clone(),
                name: definition.name.clone(),
                running: false,
                pid: None,
                plist_path: definition.plist_path.clone(),
            }
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
            let trimmed = v.trim();
            // 只在值被完整引号包裹且长度 ≥ 2 时才去除引号
            let unquoted = if trimmed.len() >= 2
                && ((trimmed.starts_with('"') && trimmed.ends_with('"'))
                    || (trimmed.starts_with('\'') && trimmed.ends_with('\'')))
            {
                &trimmed[1..trimmed.len() - 1]
            } else {
                trimmed
            };
            values.insert(k.trim().to_string(), unquoted.to_string());
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
    match fs::read_to_string(&env_path) {
        Ok(content) => Ok(parse_env_content(&content)),
        Err(_) => {
            // 文件不存在时返回空 map，不阻塞 UI
            log::warn!("[ClawBot] 配置文件不存在: {}，使用默认值", env_path);
            Ok(HashMap::new())
        }
    }
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

// mask_secret 已提取至 config.rs，通过 use super::config::mask_secret 导入

fn get_route_base_url(provider: &str, env_map: &HashMap<String, String>) -> String {
    match provider {
        "g4f" => env_map.get("G4F_BASE_URL").cloned().unwrap_or_default(),
        "kiro" => env_map.get("KIRO_BASE_URL").cloned().unwrap_or_default(),
        "siliconflow" => env_map
            .get("SILICONFLOW_BASE_URL")
            .cloned()
            .unwrap_or_default(),
        "claude-proxy" => env_map.get("CLAUDE_BASE_URL").cloned().unwrap_or_default(),
        // 这些 Bot 走 LiteLLM 统一路由，优先显示 SiliconFlow 付费渠道地址
        "free_pool" | "free_first" | "free_llm" => {
            env_map.get("SILICONFLOW_PAID_BASE_URL")
                .or_else(|| env_map.get("SILICONFLOW_BASE_URL"))
                .cloned()
                .unwrap_or_else(|| "LiteLLM 智能路由".to_string())
        }
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
                return Ok(format!("{} 已在运行", definition.name));
            }
            // 优先尝试 launchd 方式启动
            let launchd_ok = bootstrap_service(&uid, &definition)
                .and_then(|_| kickstart_service(&uid, &definition));
            match launchd_ok {
                Ok(_) => {
                    // 等待 3 秒后检查是否真的启动了（防止 macOS 后台任务管理屏蔽）
                    tokio::time::sleep(std::time::Duration::from_secs(3)).await;
                    let recheck = query_service_status(&uid, &definition);
                    if recheck.running {
                        Ok(format!("{} 已启动", definition.name))
                    } else if definition.launcher_script.is_some() {
                        // launchd 声称成功但端口没起来，降级用脚本启动
                        info!("[总控] launchd 启动 {} 后未响应，降级为脚本启动", definition.label);
                        start_service_via_script(&definition)
                    } else {
                        Err(format!("{} 启动失败：launchd 未能拉起服务", definition.name))
                    }
                }
                Err(_) if definition.launcher_script.is_some() => {
                    // launchd 操作失败（如被 macOS 屏蔽），降级用脚本启动
                    info!("[总控] launchd 启动 {} 失败，降级为脚本启动", definition.label);
                    start_service_via_script(&definition)
                }
                Err(e) => Err(format!("{} 启动失败: {}", definition.name, e)),
            }
        }
        "stop" => {
            // 先尝试 launchd 方式停止
            let _ = bootout_service(&uid, &definition);
            // 无论 launchd 是否成功，都检查端口并 kill 残留进程
            if definition.port.is_some() {
                if let Ok(msg) = stop_service_via_pid(&definition).await {
                    return Ok(msg);
                }
            }
            Ok(format!("{} 已停止", definition.name))
        }
        "restart" => {
            // 停止：先 launchd bootout + kill 进程
            let _ = bootout_service(&uid, &definition);
            if definition.port.is_some() {
                let _ = stop_service_via_pid(&definition).await;
            }
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
            // 启动：先 launchd，失败则降级脚本
            let launchd_ok = bootstrap_service(&uid, &definition)
                .and_then(|_| kickstart_service(&uid, &definition));
            match launchd_ok {
                Ok(_) => {
                    tokio::time::sleep(std::time::Duration::from_secs(3)).await;
                    let recheck = query_service_status(&uid, &definition);
                    if recheck.running {
                        Ok(format!("{} 已重启", definition.name))
                    } else if definition.launcher_script.is_some() {
                        info!("[总控] launchd 重启 {} 后未响应，降级为脚本启动", definition.label);
                        start_service_via_script(&definition)?;
                        Ok(format!("{} 已重启（脚本模式）", definition.name))
                    } else {
                        Err(format!("{} 重启失败", definition.name))
                    }
                }
                Err(_) if definition.launcher_script.is_some() => {
                    info!("[总控] launchd 重启 {} 失败，降级为脚本启动", definition.label);
                    start_service_via_script(&definition)?;
                    Ok(format!("{} 已重启（脚本模式）", definition.name))
                }
                Err(e) => Err(format!("{} 重启失败: {}", definition.name, e)),
            }
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
    // 使用超时机制避免 openclaw 命令挂起导致 UI 卡死
    let handle = std::thread::spawn(|| {
        shell::run_openclaw(&["status", "--usage", "--json"])
    });

    let result = tokio::time::timeout(
        std::time::Duration::from_secs(3),
        tokio::task::spawn_blocking(move || handle.join()),
    )
    .await;

    let output = match result {
        Ok(Ok(Ok(Ok(s)))) => s,
        _ => return Ok(json!({ "providers": [] })),
    };

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

#[derive(Debug, Serialize, Deserialize)]
pub struct SkillEntry {
    pub name: String,
    pub enabled: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SkillsStatus {
    pub total: u32,
    pub enabled: u32,
    pub skills: Vec<SkillEntry>,
}

#[command]
pub async fn get_skills_status() -> Result<SkillsStatus, String> {
    let base_dir = get_base_dir()?;
    let skills_dir = format!("{}/apps/openclaw/skills", base_dir);

    // 扫描 skills 目录下的子目录
    let mut all_skills: Vec<String> = Vec::new();
    if let Ok(entries) = fs::read_dir(&skills_dir) {
        for entry in entries.flatten() {
            if entry.path().is_dir() {
                if let Some(name) = entry.file_name().to_str() {
                    // 跳过隐藏目录
                    if !name.starts_with('.') {
                        all_skills.push(name.to_string());
                    }
                }
            }
        }
    }
    all_skills.sort();

    // 读取 openclaw.json 中的 skills.entries 获取启用列表
    let enabled_set: std::collections::HashSet<String> = match load_openclaw_config() {
        Ok(cfg) => {
            cfg.get("skills")
                .and_then(|v| v.get("entries"))
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|entry| {
                            let name = entry.get("name").and_then(|v| v.as_str())?;
                            let enabled = entry.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true);
                            if enabled { Some(name.to_string()) } else { None }
                        })
                        .collect()
                })
                .unwrap_or_default()
        }
        Err(_) => std::collections::HashSet::new(),
    };

    let skills: Vec<SkillEntry> = all_skills
        .iter()
        .map(|name| SkillEntry {
            name: name.clone(),
            enabled: enabled_set.contains(name),
        })
        .collect();

    let total = skills.len() as u32;
    let enabled = skills.iter().filter(|s| s.enabled).count() as u32;

    Ok(SkillsStatus {
        total,
        enabled,
        skills,
    })
}

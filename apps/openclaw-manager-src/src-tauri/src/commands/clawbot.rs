use super::config::{get_home_dir, mask_secret};
use crate::models::{AppError, AppResult};
use crate::utils::{file, shell};
use log::{info, warn};
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::Duration;
use tauri::command;

#[cfg(unix)]
use std::os::unix::process::CommandExt;

// IBKR shell 命令不属于运行时配置；桌面端仅执行源码内固定操作。
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
static MANAGED_SERVICE_OPERATION_LOCK: Lazy<tokio::sync::Mutex<()>> =
    Lazy::new(|| tokio::sync::Mutex::new(()));

fn acquire_managed_service_operation_file_lock() -> AppResult<file::ExclusiveFileLock> {
    let path = std::path::PathBuf::from(crate::utils::platform::get_config_dir())
        .join("manager-pids")
        .join("managed-services-operation.lock");
    file::ExclusiveFileLock::acquire(&path, 200, 25).map_err(|error| {
        if error.kind() == std::io::ErrorKind::WouldBlock {
            AppError::conflict("另一个 OpenClaw 管理器实例正在操作托管服务")
        } else {
            AppError::io(format!("创建托管服务操作锁失败: {}", error))
        }
    })
}

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

fn get_base_dir() -> AppResult<String> {
    // 优先从环境变量 OPENCLAW_PROJECT_DIR 获取项目根目录，支持部署到任意路径
    if let Ok(dir) = std::env::var("OPENCLAW_PROJECT_DIR") {
        if !dir.is_empty() {
            return Ok(dir);
        }
    }
    let home = get_home_dir()?;
    Ok(format!("{}/Desktop/OpenEverything", home))
}

fn get_managed_services() -> AppResult<Vec<ManagedServiceDefinition>> {
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
            launcher_script: None,
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
            launcher_script: Some(format!(
                "{}/packages/clawbot/scripts/start_clawbot.sh",
                base_dir
            )),
            stdout_log: Some(format!("{}/com-clawbot-agent.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-agent.stderr.log", logs_dir)),
        },
        ManagedServiceDefinition {
            label: "ai.openclaw.xianyu".to_string(),
            name: "闲鱼 AI 客服".to_string(),
            plist_path: format!("{}/ai.openclaw.xianyu.plist", launchagents_dir),
            port: None, // 闲鱼客服是 WebSocket 客户端，不监听端口
            launcher_script: Some(format!(
                "{}/packages/clawbot/scripts/start_xianyu.sh",
                base_dir
            )),
            stdout_log: Some(format!("{}/com-clawbot-xianyu.stdout.log", logs_dir)),
            stderr_log: Some(format!("{}/com-clawbot-xianyu.stderr.log", logs_dir)),
        },
    ])
}

fn get_uid() -> AppResult<String> {
    shell::validate_command("id")?;
    let output = Command::new("id")
        .arg("-u")
        .output()
        .map_err(|e| AppError::process(format!("获取用户 UID 失败: {}", e)))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(AppError::process(format!("获取用户 UID 失败: {}", err)));
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn launchctl_target(uid: &str, label: &str) -> String {
    format!("gui/{}/{}", uid, label)
}

fn launchctl_domain(uid: &str) -> String {
    format!("gui/{}", uid)
}

fn run_launchctl(args: &[&str]) -> AppResult<String> {
    shell::validate_command("launchctl")?;
    let output = Command::new("launchctl")
        .args(args)
        .output()
        .map_err(|e| AppError::process(format!("执行 launchctl 失败: {}", e)))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if output.status.success() {
        Ok(stdout)
    } else {
        Err(AppError::process(
            format!("{}{}", stdout, stderr).trim().to_string(),
        ))
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

fn fallback_process_marker(definition: &ManagedServiceDefinition) -> String {
    format!("openclaw-manager:{}", definition.label)
}

fn fallback_pid_file_path(definition: &ManagedServiceDefinition) -> String {
    let safe_label: String = definition
        .label
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect();
    format!(
        "{}/manager-pids/{}.pid",
        crate::utils::platform::get_config_dir(),
        safe_label
    )
}

fn write_fallback_pid(definition: &ManagedServiceDefinition, pid: u32) -> AppResult<()> {
    if pid <= 1 {
        return Err(AppError::process("脚本启动返回了不安全的 PID"));
    }
    let path = fallback_pid_file_path(definition);
    if let Some(parent) = Path::new(&path).parent() {
        fs::create_dir_all(parent)
            .map_err(|e| AppError::io(format!("创建服务 PID 目录失败: {}", e)))?;
    }
    fs::write(&path, pid.to_string())
        .map_err(|e| AppError::io(format!("保存服务 PID 所有权记录失败: {}", e)))
}

fn read_fallback_pid(definition: &ManagedServiceDefinition) -> AppResult<Option<u32>> {
    let path = fallback_pid_file_path(definition);
    if !Path::new(&path).exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(&path)
        .map_err(|e| AppError::io(format!("读取服务 PID 所有权记录失败: {}", e)))?;
    let pid = raw
        .trim()
        .parse::<u32>()
        .map_err(|_| AppError::config("服务 PID 所有权记录格式无效"))?;
    if pid <= 1 {
        return Err(AppError::config("服务 PID 所有权记录不安全"));
    }
    Ok(Some(pid))
}

fn clear_fallback_pid(definition: &ManagedServiceDefinition) -> AppResult<()> {
    match fs::remove_file(fallback_pid_file_path(definition)) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(AppError::io(format!(
            "清理服务 PID 所有权记录失败: {}",
            error
        ))),
    }
}

fn command_line_has_fallback_marker(command_line: &str, marker: &str) -> bool {
    command_line
        .split_whitespace()
        .map(|token| token.trim_matches(|ch: char| ch == '\'' || ch == '"'))
        .any(|token| token == marker)
}

#[cfg(test)]
mod fallback_process_marker_tests {
    use super::{command_line_has_fallback_marker, prepare_managed_script, set_or_append_env_line};

    #[test]
    fn requires_an_exact_manager_marker_argument() {
        let marker = "openclaw-manager:ai.openclaw.clawbot-agent";
        assert!(command_line_has_fallback_marker(
            "/bin/bash -s -- openclaw-manager:ai.openclaw.clawbot-agent",
            marker
        ));
        assert!(!command_line_has_fallback_marker(
            "/bin/bash -s -- openclaw-manager:ai.openclaw.clawbot-agent-copy",
            marker
        ));
        assert!(!command_line_has_fallback_marker(
            "python3 service.py",
            marker
        ));
    }

    #[test]
    fn managed_script_removes_unowned_kills_and_waits_for_children() {
        let script = "#!/bin/bash\npkill -f multi_main.py\nnohup python main.py &\n";
        let managed = prepare_managed_script(script);

        assert!(!managed.contains("pkill"));
        assert!(managed.contains("nohup python main.py &"));
        assert!(managed.ends_with("\nwait\n"));
    }

    #[test]
    fn runtime_config_rejects_cross_line_env_injection() {
        let mut lines = vec!["G4F_BASE_URL=\"https://old.example\"".to_string()];
        let error = set_or_append_env_line(
            &mut lines,
            "G4F_BASE_URL",
            "https://safe.example\nOPENCLAW_API_TOKEN=attacker-known",
        )
        .expect_err("运行时配置不得注入新环境变量行");

        assert!(error.message.contains("换行符"));
        assert_eq!(lines, vec!["G4F_BASE_URL=\"https://old.example\""]);
    }
}

fn verify_fallback_process(definition: &ManagedServiceDefinition, pid: u32) -> AppResult<String> {
    let command_line = shell::get_process_command_line(pid).map_err(|e| {
        AppError::not_found(format!(
            "{} PID {} 不存在或不可读: {}",
            definition.name, pid, e
        ))
    })?;
    let marker = fallback_process_marker(definition);
    if !command_line_has_fallback_marker(&command_line, &marker) {
        return Err(AppError::conflict(format!(
            "PID {} 与 {} 的管理器标记不匹配，已拒绝终止",
            pid, definition.name
        )));
    }
    Ok(command_line)
}

fn verified_fallback_pid(definition: &ManagedServiceDefinition) -> Option<u32> {
    read_fallback_pid(definition)
        .ok()
        .flatten()
        .filter(|pid| verify_fallback_process(definition, *pid).is_ok())
}

fn prepare_managed_script(script: &str) -> String {
    let without_unowned_kills = script
        .lines()
        .filter(|line| {
            let trimmed = line.trim_start();
            !trimmed.starts_with("pkill ") && !trimmed.starts_with("pkill\t")
        })
        .collect::<Vec<_>>()
        .join("\n")
        .replace("exec ", "");
    format!("{}\nwait\n", without_unowned_kills.trim_end())
}

fn terminate_spawned_process_group(child: &mut Child, process_group_id: u32) {
    if shell::signal_process_group(process_group_id, true).is_err() {
        let _ = child.kill();
    }
    let _ = child.wait();
}

fn reap_fallback_process(mut child: Child, definition: ManagedServiceDefinition, pid: u32) {
    std::thread::spawn(move || {
        let _ = child.wait();
        if matches!(read_fallback_pid(&definition), Ok(Some(recorded_pid)) if recorded_pid == pid) {
            let _ = clear_fallback_pid(&definition);
        }
    });
}

/// 通过启动脚本直接启动服务（macOS 后台任务管理屏蔽 launchd 时的 fallback）
///
/// macOS 26+ 的 com.apple.provenance 安全策略会阻止 launchd/Tauri 进程
/// 执行带有 provenance 属性的脚本文件（退出码 126: Operation not permitted）。
///
/// 解决方案：读取脚本内容 → 通过 stdin 管道传给 bash，绕过文件执行权限检查。
fn start_service_via_script(definition: &ManagedServiceDefinition) -> AppResult<String> {
    let script = definition.launcher_script.as_ref().ok_or_else(|| {
        AppError::config(format!(
            "{} 未配置启动脚本，无法通过进程方式启动",
            definition.name
        ))
    })?;

    // 读取脚本文件内容（读取不受 provenance 限制，只有执行才被拦截）
    let script_content = std::fs::read_to_string(script)
        .map_err(|e| AppError::io(format!("读取启动脚本失败 {}: {}", script, e)))?;

    // 删除旧脚本中无所有权核验的 pkill，并让 wrapper 等待所有后台子进程。
    let managed_content = prepare_managed_script(&script_content);

    let stdout_log = definition.stdout_log.as_deref().unwrap_or("/dev/null");
    let stderr_log = definition.stderr_log.as_deref().unwrap_or("/dev/null");
    let marker = fallback_process_marker(definition);

    let stdout = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(stdout_log)
        .map_err(|e| AppError::io(format!("打开服务 stdout 日志失败: {}", e)))?;
    let stderr = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(stderr_log)
        .map_err(|e| AppError::io(format!("打开服务 stderr 日志失败: {}", e)))?;

    shell::validate_command("bash")?;
    let mut command = Command::new("bash");
    command
        .args(["-s", "--", &marker])
        .env("PATH", shell::get_extended_path())
        .stdin(Stdio::piped())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(unix)]
    command.process_group(0);

    let mut child = command
        .spawn()
        .map_err(|e| AppError::process(format!("执行启动脚本失败: {}", e)))?;
    let pid = child.id();
    let write_result = child
        .stdin
        .take()
        .ok_or_else(|| AppError::process("启动脚本 stdin 不可用"))
        .and_then(|mut stdin| {
            stdin
                .write_all(managed_content.as_bytes())
                .map_err(|e| AppError::process(format!("写入启动脚本失败: {}", e)))
        });
    if let Err(error) = write_result {
        terminate_spawned_process_group(&mut child, pid);
        return Err(error);
    }
    if let Err(error) = write_fallback_pid(definition, pid) {
        terminate_spawned_process_group(&mut child, pid);
        return Err(error);
    }
    if let Err(error) = verify_fallback_process(definition, pid) {
        terminate_spawned_process_group(&mut child, pid);
        let _ = clear_fallback_pid(definition);
        return Err(error);
    }
    reap_fallback_process(child, definition.clone(), pid);
    Ok(format!(
        "{} 已通过启动脚本启动 (PID: {})",
        definition.name, pid
    ))
}

/// 停止通过脚本启动且具有管理器 PID 所有权记录的服务。
/// 使用 tokio::time::sleep 替代 std::thread::sleep，避免阻塞 tokio 工作线程
async fn stop_service_via_pid(definition: &ManagedServiceDefinition) -> AppResult<String> {
    let Some(pid) = read_fallback_pid(definition)? else {
        if let Some(port) = definition.port {
            let address = format!("127.0.0.1:{}", port);
            if address
                .parse::<SocketAddr>()
                .ok()
                .is_some_and(|socket| check_tcp(socket).is_ok())
            {
                return Err(AppError::conflict(format!(
                    "{} 端口可达但没有管理器 PID 所有权记录，已拒绝终止",
                    definition.name
                )));
            }
        }
        return Ok(format!("{} 没有脚本模式进程需要停止", definition.name));
    };

    if let Err(error) = verify_fallback_process(definition, pid) {
        if shell::get_process_command_line(pid).is_err() {
            if shell::process_group_is_running(pid) {
                return Err(AppError::conflict(format!(
                    "{} 的进程组 {} 仍有成员，但组长身份不可核验，已拒绝终止",
                    definition.name, pid
                )));
            }
            clear_fallback_pid(definition)?;
            return Ok(format!("{} 已停止，失效 PID 记录已清理", definition.name));
        }
        return Err(error);
    }

    shell::signal_process_group(pid, false)
        .map_err(|e| AppError::process(format!("发送 {} 停止信号失败: {}", definition.name, e)))?;
    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    if shell::process_group_is_running(pid) {
        if shell::get_process_command_line(pid).is_ok() {
            verify_fallback_process(definition, pid)?;
        }
        shell::signal_process_group(pid, true)
            .map_err(|e| AppError::process(format!("强制终止 {} 失败: {}", definition.name, e)))?;
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    }
    if shell::process_group_is_running(pid) {
        return Err(AppError::process(format!(
            "{} 进程组 {} 仍在运行",
            definition.name, pid
        )));
    }
    clear_fallback_pid(definition)?;
    Ok(format!("{} 已停止 (PID: {})", definition.name, pid))
}

/// 查询服务运行状态
/// 优先用 launchctl print 检测 launchd 状态，如果 launchd 不可用（被 macOS 后台任务管理屏蔽），
/// 则降级为端口探活 + 进程名匹配方式判断服务是否在运行
fn query_service_status(uid: &str, definition: &ManagedServiceDefinition) -> ManagedServiceStatus {
    if definition.label == "ai.openclaw.gateway" {
        return match super::service::gateway_status_snapshot() {
            Ok(status) => ManagedServiceStatus {
                label: definition.label.clone(),
                name: definition.name.clone(),
                running: status.running,
                pid: status.pid,
                plist_path: definition.plist_path.clone(),
            },
            Err(_) => ManagedServiceStatus {
                label: definition.label.clone(),
                name: definition.name.clone(),
                running: false,
                pid: None,
                plist_path: definition.plist_path.clone(),
            },
        };
    }
    if definition.label == IBKR_MANAGED_LABEL {
        return query_ibkr_status(definition);
    }

    let target = launchctl_target(uid, &definition.label);
    // 白名单校验 — launchctl 在允许列表中
    let output = if shell::validate_command("launchctl").is_ok() {
        Command::new("launchctl")
            .args(["print", target.as_str()])
            .output()
    } else {
        // 校验失败时直接走 fallback 路径
        Err(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "命令不在白名单中",
        ))
    };

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
                            return ManagedServiceStatus {
                                label: definition.label.clone(),
                                name: definition.name.clone(),
                                running: true,
                                pid: verified_fallback_pid(definition),
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
                        return ManagedServiceStatus {
                            label: definition.label.clone(),
                            name: definition.name.clone(),
                            running: true,
                            pid: verified_fallback_pid(definition),
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
        }
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

fn bootout_service(uid: &str, definition: &ManagedServiceDefinition) -> AppResult<()> {
    let domain = launchctl_domain(uid);
    match run_launchctl(&["bootout", domain.as_str(), definition.plist_path.as_str()]) {
        Ok(_) => Ok(()),
        Err(err) => {
            if is_bootout_missing(&err.message) {
                Ok(())
            } else {
                Err(err)
            }
        }
    }
}

fn bootstrap_service(uid: &str, definition: &ManagedServiceDefinition) -> AppResult<()> {
    let domain = launchctl_domain(uid);
    match run_launchctl(&["bootstrap", domain.as_str(), definition.plist_path.as_str()]) {
        Ok(_) => Ok(()),
        Err(err) => {
            if is_bootstrap_conflict(&err.message) {
                Ok(())
            } else {
                Err(err)
            }
        }
    }
}

fn kickstart_service(uid: &str, definition: &ManagedServiceDefinition) -> AppResult<()> {
    let target = launchctl_target(uid, &definition.label);
    run_launchctl(&["kickstart", "-k", target.as_str()]).map(|_| ())
}

fn find_service_definition(label: &str) -> AppResult<ManagedServiceDefinition> {
    let definitions = get_managed_services()?;
    definitions
        .into_iter()
        .find(|s| s.label == label)
        .ok_or_else(|| AppError::not_found(format!("未找到服务: {}", label)))
}

fn parse_env_content(content: &str) -> HashMap<String, String> {
    let mut values = HashMap::new();
    for line in content.lines() {
        if let Some((key, value)) = file::parse_env_assignment(line) {
            values.insert(key, value);
        }
    }
    values
}

fn set_or_append_env_line(lines: &mut Vec<String>, key: &str, value: &str) -> AppResult<()> {
    let new_line = file::format_env_assignment(key, value, false)
        .map_err(|e| AppError::validation(format!("ClawBot 环境变量值无效: {}", e)))?;
    let mut updated = false;
    for line in lines.iter_mut() {
        if let Some((left, _)) = line.split_once('=') {
            if left.trim() == key {
                *line = new_line.clone();
                updated = true;
                break;
            }
        }
    }

    if !updated {
        lines.push(new_line);
    }
    Ok(())
}

fn get_clawbot_env_path() -> AppResult<String> {
    let base_dir = get_base_dir()?;
    Ok(format!("{}/packages/clawbot/config/.env", base_dir))
}

fn get_service_log_path(label: &str) -> AppResult<String> {
    let base_dir = get_base_dir()?;
    let path = match label {
        "ai.openclaw.gateway" => format!("{}/.openclaw/logs/gateway.log", base_dir),
        "ai.openclaw.clawbot-agent" => format!(
            "{}/packages/clawbot/logs/com-clawbot-agent.stderr.log",
            base_dir
        ),
        "ai.openclaw.g4f" => format!(
            "{}/packages/clawbot/logs/com-clawbot-g4f.stderr.log",
            base_dir
        ),
        "ai.openclaw.kiro-gateway" => {
            format!(
                "{}/packages/clawbot/logs/com-clawbot-kiro-gateway.stderr.log",
                base_dir
            )
        }
        "ai.openclaw.xianyu" => {
            format!(
                "{}/packages/clawbot/logs/com-clawbot-xianyu.stderr.log",
                base_dir
            )
        }
        _ => return Err(AppError::not_found(format!("未知服务标签: {}", label))),
    };
    Ok(path)
}

fn last_lines(content: &str, n: usize) -> Vec<String> {
    let lines: Vec<String> = content.lines().map(|s| s.to_string()).collect();
    let start = lines.len().saturating_sub(n);
    lines[start..].to_vec()
}

fn parse_socket_addr(host: &str, port: &str) -> AppResult<SocketAddr> {
    let port_num = port
        .parse::<u16>()
        .map_err(|_| AppError::validation(format!("端口格式无效: {}", port)))?;
    let mut resolved = (host, port_num)
        .to_socket_addrs()
        .map_err(|e| AppError::network(format!("地址解析失败 {}:{}: {}", host, port_num, e)))?;
    resolved
        .next()
        .ok_or_else(|| AppError::network(format!("地址解析结果为空: {}:{}", host, port_num)))
}

fn check_tcp(addr: SocketAddr) -> AppResult<()> {
    TcpStream::connect_timeout(&addr, Duration::from_secs(2))
        .map(|_| ())
        .map_err(|e| AppError::network(e.to_string()))
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

fn load_clawbot_env_map() -> AppResult<HashMap<String, String>> {
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

fn get_openclaw_config_path() -> AppResult<String> {
    let base_dir = get_base_dir()?;
    Ok(format!("{}/.openclaw/openclaw.json", base_dir))
}

fn load_openclaw_config() -> AppResult<Value> {
    let cfg_path = get_openclaw_config_path()?;
    let content = fs::read_to_string(&cfg_path)
        .map_err(|e| AppError::config(format!("读取 OpenClaw 配置失败: {}", e)))?;
    serde_json::from_str(&content)
        .map_err(|e| AppError::serialization(format!("解析 OpenClaw 配置失败: {}", e)))
}

fn get_openclaw_main_matrix_entry() -> AppResult<Option<ClawbotBotMatrixEntry>> {
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

fn is_ibkr_reachable(env_map: &HashMap<String, String>) -> AppResult<()> {
    let (host, port) = get_ibkr_host_port(env_map);
    let addr = parse_socket_addr(&host, &port)?;
    check_tcp(addr)
}

fn get_default_ibkr_start_cmd() -> String {
    if let Ok(base_dir) = get_base_dir() {
        let script_path = format!(
            "{}/packages/clawbot/scripts/start_ibkr_gateway.sh",
            base_dir
        );
        if Path::new(&script_path).exists() {
            return format!("bash \"{}\"", script_path);
        }
    }
    IBKR_DEFAULT_START_CMD.to_string()
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

fn control_ibkr_service(action: &str) -> AppResult<String> {
    let env_map = load_clawbot_env_map()?;
    let (host, port) = get_ibkr_host_port(&env_map);
    let reachable = is_ibkr_reachable(&env_map).is_ok();
    let start_cmd = get_default_ibkr_start_cmd();

    match action {
        "start" => {
            if reachable {
                return Ok(format!("IBKR 已在 {}:{} 运行", host, port));
            }
            shell::run_script_output(&start_cmd)
                .map_err(|e| AppError::process(format!("执行 IBKR 启动命令失败: {}", e)))?;
            Ok(format!(
                "IBKR 启动命令已执行，等待端口 {}:{} 就绪",
                host, port
            ))
        }
        "stop" => {
            if reachable {
                Err(AppError::conflict(
                    "IBKR 是外部客户端且没有管理器 PID 所有权记录，已拒绝终止；请在 IB Gateway/TWS 内退出",
                ))
            } else {
                Ok("IBKR 未在运行".to_string())
            }
        }
        "restart" => {
            if reachable {
                Err(AppError::conflict(
                    "IBKR 是外部客户端且没有管理器 PID 所有权记录，已拒绝重启；请先在 IB Gateway/TWS 内退出",
                ))
            } else {
                shell::run_script_output(&start_cmd)
                    .map_err(|e| AppError::process(format!("执行 IBKR 启动命令失败: {}", e)))?;
                Ok(format!(
                    "IBKR 启动命令已执行，等待端口 {}:{} 就绪",
                    host, port
                ))
            }
        }
        _ => Err(AppError::validation(format!("不支持的操作: {}", action))),
    }
}

fn should_autostart_ibkr(action: &str) -> AppResult<bool> {
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
        "free_pool" | "free_first" | "free_llm" => env_map
            .get("SILICONFLOW_PAID_BASE_URL")
            .or_else(|| env_map.get("SILICONFLOW_BASE_URL"))
            .cloned()
            .unwrap_or_else(|| "LiteLLM 智能路由".to_string()),
        _ => String::new(),
    }
}

#[command]
pub async fn get_managed_services_status() -> AppResult<Vec<ManagedServiceStatus>> {
    let uid = get_uid()?;
    let definitions = get_managed_services()?;

    let statuses = definitions
        .iter()
        .map(|definition| query_service_status(&uid, definition))
        .collect();

    Ok(statuses)
}

#[command]
pub async fn control_managed_service(label: String, action: String) -> AppResult<String> {
    if label == "ai.openclaw.gateway" {
        info!("[总控] Gateway 操作委托给统一服务控制器: {}", action);
        return match action.as_str() {
            "start" => super::service::start_service().await,
            "stop" => super::service::stop_service().await,
            "restart" => super::service::restart_service().await,
            _ => Err(AppError::validation(format!("不支持的操作: {}", action))),
        };
    }
    let _operation_guard = MANAGED_SERVICE_OPERATION_LOCK.lock().await;
    let _file_guard = acquire_managed_service_operation_file_lock()?;
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
                        info!(
                            "[总控] launchd 启动 {} 后未响应，降级为脚本启动",
                            definition.label
                        );
                        start_service_via_script(&definition)
                    } else {
                        Err(AppError::process(format!(
                            "{} 启动失败：launchd 未能拉起服务",
                            definition.name
                        )))
                    }
                }
                Err(_) if definition.launcher_script.is_some() => {
                    // launchd 操作失败（如被 macOS 屏蔽），降级用脚本启动
                    info!(
                        "[总控] launchd 启动 {} 失败，降级为脚本启动",
                        definition.label
                    );
                    start_service_via_script(&definition)
                }
                Err(e) => Err(AppError::process(format!(
                    "{} 启动失败: {}",
                    definition.name, e
                ))),
            }
        }
        "stop" => {
            let launchd_result = bootout_service(&uid, &definition);
            let fallback_result = stop_service_via_pid(&definition).await;
            let status = query_service_status(&uid, &definition);
            if status.running {
                if let Err(error) = fallback_result {
                    return Err(error);
                }
                if let Err(error) = launchd_result {
                    return Err(error);
                }
                return Err(AppError::process(format!(
                    "{} 停止后仍在运行",
                    definition.name
                )));
            }
            Ok(format!("{} 已停止", definition.name))
        }
        "restart" => {
            let launchd_stop = bootout_service(&uid, &definition);
            let fallback_stop = stop_service_via_pid(&definition).await;
            let stopped_status = query_service_status(&uid, &definition);
            if stopped_status.running {
                if let Err(error) = fallback_stop {
                    return Err(error);
                }
                if let Err(error) = launchd_stop {
                    return Err(error);
                }
                return Err(AppError::process(format!(
                    "{} 重启前未能安全停止",
                    definition.name
                )));
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
                        info!(
                            "[总控] launchd 重启 {} 后未响应，降级为脚本启动",
                            definition.label
                        );
                        start_service_via_script(&definition)?;
                        Ok(format!("{} 已重启（脚本模式）", definition.name))
                    } else {
                        Err(AppError::process(format!("{} 重启失败", definition.name)))
                    }
                }
                Err(_) if definition.launcher_script.is_some() => {
                    info!(
                        "[总控] launchd 重启 {} 失败，降级为脚本启动",
                        definition.label
                    );
                    start_service_via_script(&definition)?;
                    Ok(format!("{} 已重启（脚本模式）", definition.name))
                }
                Err(e) => Err(AppError::process(format!(
                    "{} 重启失败: {}",
                    definition.name, e
                ))),
            }
        }
        _ => Err(AppError::validation(format!("不支持的操作: {}", action))),
    }
}

#[command]
pub async fn control_all_managed_services(action: String) -> AppResult<String> {
    let mut services = get_managed_services()?;

    if action == "stop" {
        services.reverse();
    }

    let mut messages = Vec::new();
    let mut failures = Vec::new();

    for service in services {
        if service.label == IBKR_MANAGED_LABEL && !should_autostart_ibkr(&action)? {
            messages.push("IBKR 自动启动开关关闭，跳过 IBKR 操作".to_string());
            continue;
        }

        match control_managed_service(service.label.clone(), action.clone()).await {
            Ok(msg) => messages.push(msg),
            Err(err) => {
                warn!("[总控] 操作失败 {}: {}", service.label, err);
                failures.push(format!("{}: {}", service.name, err));
            }
        }
    }

    if failures.is_empty() {
        Ok(messages.join("\n"))
    } else {
        Err(AppError::process(format!(
            "部分服务操作失败:\n{}\n\n已完成:\n{}",
            failures.join("\n"),
            messages.join("\n")
        )))
    }
}

#[command]
pub async fn get_clawbot_runtime_config() -> AppResult<HashMap<String, String>> {
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
pub async fn get_openclaw_usage_snapshot() -> AppResult<Value> {
    // 使用超时机制避免 openclaw 命令挂起导致 UI 卡死
    let handle = std::thread::spawn(|| shell::run_openclaw(&["status", "--usage", "--json"]));

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
        .map_err(|e| AppError::serialization(format!("解析 openclaw usage 输出失败: {}", e)))?;

    Ok(parsed
        .get("usage")
        .cloned()
        .unwrap_or_else(|| json!({ "providers": [] })))
}

#[command]
pub async fn get_clawbot_bot_matrix() -> AppResult<Vec<ClawbotBotMatrixEntry>> {
    let env_path = get_clawbot_env_path()?;
    let content = fs::read_to_string(&env_path)
        .map_err(|e| AppError::config(format!("读取 ClawBot 配置失败: {}", e)))?;
    let env_map = parse_env_content(&content);

    let mut entries = Vec::new();
    for (id, name, token_key, username_key, route_provider, route_model) in CLAWBOT_BOT_DEFINITIONS
    {
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
pub async fn save_clawbot_runtime_config(values: HashMap<String, String>) -> AppResult<String> {
    let env_path = get_clawbot_env_path()?;
    let content = fs::read_to_string(&env_path)
        .map_err(|e| AppError::config(format!("读取 ClawBot 配置失败: {}", e)))?;
    let mut lines: Vec<String> = content.lines().map(|s| s.to_string()).collect();

    for key in CLAWBOT_ENV_KEYS {
        if let Some(value) = values.get(key) {
            set_or_append_env_line(&mut lines, key, value)?;
        }
    }

    file::write_file_atomic(&env_path, &lines.join("\n"))
        .map_err(|e| AppError::io(format!("保存 ClawBot 配置失败: {}", e)))?;

    Ok("ClawBot 配置已保存".to_string())
}

#[command]
pub async fn get_managed_service_logs(label: String, lines: Option<u32>) -> AppResult<Vec<String>> {
    if label == IBKR_MANAGED_LABEL {
        let env_map = load_clawbot_env_map()?;
        let (host, port) = get_ibkr_host_port(&env_map);
        let reachable = is_ibkr_reachable(&env_map).is_ok();
        return Ok(vec![
            "IBKR 属于外部客户端服务（无 LaunchAgent 日志文件）".to_string(),
            format!("当前探测地址: {}:{}", host, port),
            format!(
                "端口状态: {}",
                if reachable {
                    "Reachable"
                } else {
                    "Unreachable"
                }
            ),
            format!(
                "IBKR_AUTOSTART={} | 启停操作由桌面端固定管理",
                env_map
                    .get("IBKR_AUTOSTART")
                    .cloned()
                    .unwrap_or_else(|| "true".to_string()),
            ),
        ]);
    }

    let n = lines.unwrap_or(120) as usize;
    let log_path = get_service_log_path(&label)?;
    let content = fs::read_to_string(&log_path)
        .map_err(|e| AppError::io(format!("读取日志失败 ({}): {}", log_path, e)))?;
    Ok(last_lines(&content, n))
}

#[command]
pub async fn get_managed_endpoints_status() -> AppResult<Vec<ManagedEndpointStatus>> {
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
        ("ibkr".to_string(), "IBKR".to_string(), ibkr_host, ibkr_port),
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
                    error: Some(err.message),
                },
            },
            Err(err) => ManagedEndpointStatus {
                id,
                name,
                address,
                healthy: false,
                error: Some(err.message),
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
pub async fn get_skills_status() -> AppResult<SkillsStatus> {
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
        Ok(cfg) => cfg
            .get("skills")
            .and_then(|v| v.get("entries"))
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|entry| {
                        let name = entry.get("name").and_then(|v| v.as_str())?;
                        let enabled = entry
                            .get("enabled")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true);
                        if enabled {
                            Some(name.to_string())
                        } else {
                            None
                        }
                    })
                    .collect()
            })
            .unwrap_or_default(),
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

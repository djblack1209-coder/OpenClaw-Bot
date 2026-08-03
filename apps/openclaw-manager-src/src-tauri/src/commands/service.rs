use crate::models::{AppError, AppResult, ServiceStatus};
use crate::utils::{file, platform, shell};
use log::{debug, info};
use once_cell::sync::Lazy;
use regex::Regex;
use std::process::Command;
use std::time::Duration;
use tauri::command;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Windows CREATE_NO_WINDOW 标志，用于隐藏控制台窗口
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

const SERVICE_PORT: u16 = 18789;
const GATEWAY_LAUNCHD_LABEL: &str = "ai.openclaw.gateway";
static GATEWAY_OPERATION_LOCK: Lazy<tokio::sync::Mutex<()>> =
    Lazy::new(|| tokio::sync::Mutex::new(()));

fn acquire_gateway_operation_file_lock() -> AppResult<file::ExclusiveFileLock> {
    let path = std::path::PathBuf::from(platform::get_config_dir())
        .join("manager-pids")
        .join("gateway-operation.lock");
    file::ExclusiveFileLock::acquire(&path, 200, 25).map_err(|error| {
        if error.kind() == std::io::ErrorKind::WouldBlock {
            AppError::conflict("另一个 OpenClaw 管理器实例正在操作 Gateway")
        } else {
            AppError::io(format!("创建 Gateway 操作锁失败: {}", error))
        }
    })
}

#[derive(Debug, Clone)]
struct GatewayLaunchdState {
    domain: String,
    target: String,
    plist_path: String,
    pid: Option<u32>,
    loaded: bool,
}

fn parse_launchctl_pid(output: &str) -> Option<u32> {
    output.lines().find_map(|line| {
        let (key, value) = line.trim().split_once('=')?;
        if key.trim() == "pid" {
            value.trim().parse::<u32>().ok()
        } else {
            None
        }
    })
}

fn parse_launchctl_path(output: &str) -> Option<String> {
    output.lines().find_map(|line| {
        let (key, value) = line.trim().split_once('=')?;
        if key.trim() == "path" {
            let path = value.trim();
            (!path.is_empty()).then(|| path.to_string())
        } else {
            None
        }
    })
}

#[cfg(target_os = "macos")]
fn gateway_launchd_state() -> AppResult<Option<GatewayLaunchdState>> {
    shell::validate_command("id")?;
    shell::validate_command("launchctl")?;
    let uid_output = Command::new("id")
        .arg("-u")
        .output()
        .map_err(|e| AppError::process(format!("读取用户 UID 失败: {}", e)))?;
    if !uid_output.status.success() {
        return Err(AppError::process("读取用户 UID 失败"));
    }
    let uid = String::from_utf8_lossy(&uid_output.stdout)
        .trim()
        .to_string();
    if uid.is_empty() || !uid.chars().all(|ch| ch.is_ascii_digit()) {
        return Err(AppError::validation("用户 UID 格式无效"));
    }
    let domain = format!("gui/{}", uid);
    let target = format!("{}/{}", domain, GATEWAY_LAUNCHD_LABEL);
    let expected_plist = dirs::home_dir()
        .map(|home| home.join("Library/LaunchAgents/ai.openclaw.gateway.plist"))
        .ok_or_else(|| AppError::config("无法定位用户 LaunchAgents 目录"))?;
    let output = Command::new("launchctl")
        .args(["print", &target])
        .output()
        .map_err(|e| AppError::process(format!("查询 Gateway LaunchAgent 失败: {}", e)))?;
    if !output.status.success() {
        return if expected_plist.exists() {
            Ok(Some(GatewayLaunchdState {
                domain,
                target,
                plist_path: expected_plist.display().to_string(),
                pid: None,
                loaded: false,
            }))
        } else {
            Ok(None)
        };
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    Ok(Some(GatewayLaunchdState {
        domain,
        target,
        plist_path: parse_launchctl_path(&stdout)
            .unwrap_or_else(|| expected_plist.display().to_string()),
        pid: parse_launchctl_pid(&stdout),
        loaded: true,
    }))
}

#[cfg(not(target_os = "macos"))]
fn gateway_launchd_state() -> AppResult<Option<GatewayLaunchdState>> {
    Ok(None)
}

#[cfg(target_os = "macos")]
fn bootout_gateway_launchd(state: &GatewayLaunchdState) -> AppResult<()> {
    shell::validate_command("launchctl")?;
    let disable_output = Command::new("launchctl")
        .args(["disable", &state.target])
        .output()
        .map_err(|e| AppError::process(format!("禁用旧 Gateway LaunchAgent 失败: {}", e)))?;
    if !disable_output.status.success() {
        return Err(AppError::process(format!(
            "禁用旧 Gateway LaunchAgent 失败: {}",
            String::from_utf8_lossy(&disable_output.stderr).trim()
        )));
    }
    if !state.loaded {
        return Ok(());
    }
    let output = Command::new("launchctl")
        .args(["bootout", &state.target])
        .output()
        .map_err(|e| AppError::process(format!("停止 Gateway LaunchAgent 失败: {}", e)))?;
    if output.status.success() {
        Ok(())
    } else {
        let _ = Command::new("launchctl")
            .args(["enable", &state.target])
            .output();
        Err(AppError::process(format!(
            "停止 Gateway LaunchAgent 失败，已尝试恢复启用状态: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )))
    }
}

#[cfg(not(target_os = "macos"))]
fn bootout_gateway_launchd(_state: &GatewayLaunchdState) -> AppResult<()> {
    Err(AppError::validation("当前平台不支持 LaunchAgent"))
}

#[cfg(target_os = "macos")]
fn start_gateway_launchd(state: &GatewayLaunchdState) -> AppResult<()> {
    shell::validate_command("launchctl")?;
    let enable_output = Command::new("launchctl")
        .args(["enable", &state.target])
        .output()
        .map_err(|e| AppError::process(format!("启用 Gateway LaunchAgent 失败: {}", e)))?;
    if !enable_output.status.success() {
        return Err(AppError::process(format!(
            "启用 Gateway LaunchAgent 失败: {}",
            String::from_utf8_lossy(&enable_output.stderr).trim()
        )));
    }

    let output = if state.loaded {
        Command::new("launchctl")
            .args(["kickstart", "-k", &state.target])
            .output()
    } else {
        Command::new("launchctl")
            .args(["bootstrap", &state.domain, &state.plist_path])
            .output()
    }
    .map_err(|e| AppError::process(format!("启动 Gateway LaunchAgent 失败: {}", e)))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(AppError::process(format!(
            "启动 Gateway LaunchAgent 失败: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )))
    }
}

#[cfg(not(target_os = "macos"))]
fn start_gateway_launchd(_state: &GatewayLaunchdState) -> AppResult<()> {
    Err(AppError::validation("当前平台不支持 LaunchAgent"))
}

/// 检测端口是否有服务在监听；结果只用于状态探测，不能授权终止进程。
fn check_port_listening(port: u16) -> Option<u32> {
    #[cfg(unix)]
    {
        let output = Command::new("lsof")
            .args([&format!("-iTCP:{}", port), "-sTCP:LISTEN", "-t"])
            .output()
            .ok()?;

        if output.status.success() {
            String::from_utf8_lossy(&output.stdout)
                .lines()
                .next()
                .and_then(|line| line.trim().parse::<u32>().ok())
        } else {
            None
        }
    }

    #[cfg(windows)]
    {
        let mut cmd = Command::new("netstat");
        cmd.args(["-ano"]);
        cmd.creation_flags(CREATE_NO_WINDOW);

        let output = cmd.output().ok()?;

        if output.status.success() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            for line in stdout.lines() {
                if line.contains(&format!(":{}", port)) && line.contains("LISTENING") {
                    if let Some(pid_str) = line.split_whitespace().last() {
                        if let Ok(pid) = pid_str.parse::<u32>() {
                            return Some(pid);
                        }
                    }
                }
            }
        }
        None
    }
}

fn command_line_is_openclaw_gateway(command_line: &str) -> bool {
    let tokens: Vec<String> = command_line
        .split_whitespace()
        .map(|token| {
            token
                .trim_matches(|ch: char| ch == '\'' || ch == '"')
                .to_lowercase()
        })
        .collect();
    let has_gateway_argument = tokens.iter().any(|token| token == "gateway");
    let has_openclaw_program = tokens.iter().any(|token| {
        let normalized = token.replace('\\', "/");
        normalized
            .rsplit('/')
            .next()
            .map(|name| name.starts_with("openclaw"))
            .unwrap_or(false)
            || normalized.contains("/openclaw/")
            || normalized.contains("openclaw-cli")
    });
    has_gateway_argument && has_openclaw_program
}

fn verify_managed_gateway_pid(pid: u32) -> AppResult<String> {
    let command_line = shell::get_process_command_line(pid)
        .map_err(|e| AppError::not_found(format!("Gateway PID {} 不存在或不可读: {}", pid, e)))?;
    if !command_line_is_openclaw_gateway(&command_line) {
        return Err(AppError::conflict(format!(
            "PID {} 与 OpenClaw Gateway 身份不匹配，已拒绝终止",
            pid
        )));
    }
    Ok(command_line)
}

fn managed_gateway_pid() -> AppResult<Option<u32>> {
    shell::read_managed_gateway_pid()
        .map_err(|e| AppError::config(format!("读取 Gateway PID 所有权记录失败: {}", e)))
}

/// 获取 Gateway 状态快照：端口仅代表可达，PID 仅在所有权核验通过后展示。
pub(crate) fn gateway_status_snapshot() -> AppResult<ServiceStatus> {
    let running = check_port_listening(SERVICE_PORT).is_some();
    let managed_pid = managed_gateway_pid()?
        .filter(|managed_pid| verify_managed_gateway_pid(*managed_pid).is_ok());
    let pid = managed_pid.or_else(|| {
        gateway_launchd_state()
            .ok()
            .flatten()
            .and_then(|state| state.pid)
    });

    Ok(ServiceStatus {
        running,
        pid,
        port: SERVICE_PORT,
        uptime_seconds: None,
        memory_mb: None,
        cpu_percent: None,
    })
}

/// 获取服务状态。
#[command]
pub async fn get_service_status() -> AppResult<ServiceStatus> {
    gateway_status_snapshot()
}

/// 启动服务
#[command]
pub async fn start_service() -> AppResult<String> {
    let _operation_guard = GATEWAY_OPERATION_LOCK.lock().await;
    let _file_guard = acquire_gateway_operation_file_lock()?;
    start_service_locked().await
}

async fn start_service_locked() -> AppResult<String> {
    info!("[服务] 启动服务...");

    // 先验证最终会使用的官方 CLI，失败时不改变现有服务状态。
    let openclaw_path = shell::get_openclaw_path().ok_or_else(|| {
        AppError::not_found("找不到 openclaw 命令，请先通过 npm install -g openclaw 安装")
    })?;
    shell::run_openclaw(&["--version"])
        .map_err(|e| AppError::process(format!("OpenClaw CLI 预检失败: {}", e)))?;
    info!("[服务] OpenClaw CLI 预检通过: {}", openclaw_path);

    if managed_gateway_pid()?.is_some_and(|pid| verify_managed_gateway_pid(pid).is_ok()) {
        return Err(AppError::conflict("管理器拥有的 Gateway 已在运行中"));
    }

    let port_running = check_port_listening(SERVICE_PORT).is_some();
    if let Some(launchd) = gateway_launchd_state()? {
        if launchd.loaded && port_running {
            return Err(AppError::conflict("Gateway LaunchAgent 已在运行中"));
        }
        if port_running {
            return Err(AppError::conflict(format!(
                "端口 {} 被非 LaunchAgent 进程占用，已拒绝启动",
                SERVICE_PORT
            )));
        }
        let _ = crate::commands::config::ensure_gateway_token_env_override()?;
        start_gateway_launchd(&launchd)?;
        for i in 1..=15 {
            tokio::time::sleep(Duration::from_secs(1)).await;
            if check_port_listening(SERVICE_PORT).is_some() {
                let pid = gateway_launchd_state()?.and_then(|state| state.pid);
                info!("[服务] ✓ LaunchAgent 启动成功 ({}秒), PID: {:?}", i, pid);
                return Ok(match pid {
                    Some(pid) => format!("服务已通过 LaunchAgent 启动，PID: {}", pid),
                    None => "服务已通过 LaunchAgent 启动".to_string(),
                });
            }
        }
        return Err(AppError::timeout(
            "Gateway LaunchAgent 启动超时（15秒），服务仍保持安装状态",
        ));
    }

    if port_running {
        return Err(AppError::conflict(format!(
            "端口 {} 有服务监听但无可核验所有权，已拒绝接管",
            SERVICE_PORT
        )));
    }

    let _ = crate::commands::config::ensure_gateway_token_env_override()?;
    info!("[服务] 后台启动 gateway...");
    let managed_pid = shell::spawn_openclaw_gateway()
        .map_err(|error| AppError::process(format!("启动服务失败: {}", error)))?;

    // 轮询等待端口开始监听（最多 15 秒）
    info!("[服务] 等待端口 {} 开始监听...", SERVICE_PORT);
    for i in 1..=15 {
        // 异步等待，避免阻塞 tokio 线程池
        tokio::time::sleep(Duration::from_secs(1)).await;
        if check_port_listening(SERVICE_PORT).is_some() {
            if let Err(error) = verify_managed_gateway_pid(managed_pid) {
                return Err(AppError::conflict(format!(
                    "Gateway 端口已就绪，但管理器 PID 身份核验失败: {}",
                    error
                )));
            }
            info!("[服务] ✓ 启动成功 ({}秒), PID: {}", i, managed_pid);
            return Ok(format!("服务已启动，PID: {}", managed_pid));
        }
        if i % 3 == 0 {
            debug!("[服务] 等待中... ({}秒)", i);
        }
    }

    if verify_managed_gateway_pid(managed_pid).is_ok() {
        let _ = shell::signal_process(managed_pid, true);
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    if shell::get_process_command_line(managed_pid).is_ok() {
        return Err(AppError::process(format!(
            "服务启动超时，PID {} 仍存在且无法安全清理",
            managed_pid
        )));
    }
    let _ = shell::clear_managed_gateway_pid();
    info!("[服务] 等待超时，端口仍未监听");
    Err(AppError::timeout(
        "服务启动超时（15秒），新进程已清理，请检查 openclaw 日志",
    ))
}

/// 仅停止由管理器启动、登记且身份核验通过的 Gateway 进程。
#[command]
pub async fn stop_service() -> AppResult<String> {
    let _operation_guard = GATEWAY_OPERATION_LOCK.lock().await;
    let _file_guard = acquire_gateway_operation_file_lock()?;
    stop_service_locked().await
}

async fn stop_service_locked() -> AppResult<String> {
    info!("[服务] 停止服务...");

    let Some(pid) = managed_gateway_pid()? else {
        if let Some(launchd) = gateway_launchd_state()? {
            bootout_gateway_launchd(&launchd)?;
            tokio::time::sleep(Duration::from_secs(2)).await;
            if gateway_launchd_state()?.is_some_and(|state| state.loaded) {
                return Err(AppError::process(
                    "Gateway LaunchAgent 停止后仍处于加载状态",
                ));
            }
            if check_port_listening(SERVICE_PORT).is_some() {
                return Err(AppError::conflict(format!(
                    "Gateway LaunchAgent 已停止，但端口 {} 仍被其他进程占用",
                    SERVICE_PORT
                )));
            }
            return Ok("服务已停止".to_string());
        }
        if check_port_listening(SERVICE_PORT).is_some() {
            return Err(AppError::conflict(format!(
                "端口 {} 有服务监听，但没有管理器 PID 所有权记录，已拒绝终止",
                SERVICE_PORT
            )));
        }
        return Ok("服务未在运行".to_string());
    };

    if let Err(error) = verify_managed_gateway_pid(pid) {
        if shell::get_process_command_line(pid).is_err() {
            shell::clear_managed_gateway_pid()
                .map_err(|e| AppError::io(format!("清理失效 Gateway PID 记录失败: {}", e)))?;
            if let Some(launchd) = gateway_launchd_state()? {
                bootout_gateway_launchd(&launchd)?;
                tokio::time::sleep(Duration::from_secs(2)).await;
                if gateway_launchd_state()?.is_some_and(|state| state.loaded)
                    || check_port_listening(SERVICE_PORT).is_some()
                {
                    return Err(AppError::process(
                        "清理旧 PID 后，Gateway LaunchAgent 仍未安全停止",
                    ));
                }
                return Ok("服务已停止，失效 PID 记录已清理".to_string());
            }
            if check_port_listening(SERVICE_PORT).is_none() {
                return Ok("服务未在运行，已清理失效 PID 记录".to_string());
            }
        }
        return Err(error);
    }

    shell::signal_process(pid, false)
        .map_err(|e| AppError::process(format!("发送 Gateway 停止信号失败: {}", e)))?;
    tokio::time::sleep(Duration::from_secs(2)).await;

    if shell::get_process_command_line(pid).is_ok() {
        verify_managed_gateway_pid(pid)?;
        info!(
            "[服务] Gateway 未响应 TERM，再次核验身份后强制终止 PID: {}",
            pid
        );
        shell::signal_process(pid, true)
            .map_err(|e| AppError::process(format!("强制终止 Gateway 失败: {}", e)))?;
        tokio::time::sleep(Duration::from_secs(1)).await;
    }

    if shell::get_process_command_line(pid).is_ok() {
        return Err(AppError::process(format!(
            "无法停止 Gateway，PID {} 仍在运行",
            pid
        )));
    }
    shell::clear_managed_gateway_pid()
        .map_err(|e| AppError::io(format!("清理 Gateway PID 记录失败: {}", e)))?;
    info!("[服务] ✓ 已停止管理器拥有的 Gateway PID: {}", pid);
    Ok("服务已停止".to_string())
}

/// 重启服务
#[command]
pub async fn restart_service() -> AppResult<String> {
    let _operation_guard = GATEWAY_OPERATION_LOCK.lock().await;
    let _file_guard = acquire_gateway_operation_file_lock()?;
    restart_service_locked().await
}

async fn restart_service_locked() -> AppResult<String> {
    info!("[服务] 重启服务...");

    if let Some(launchd) = gateway_launchd_state()? {
        if !managed_gateway_pid()?.is_some_and(|pid| verify_managed_gateway_pid(pid).is_ok()) {
            if !launchd.loaded {
                return start_service_locked().await;
            }
            shell::run_openclaw(&["--version"])
                .map_err(|e| AppError::process(format!("OpenClaw CLI 预检失败: {}", e)))?;
            let _ = crate::commands::config::ensure_gateway_token_env_override()?;
            start_gateway_launchd(&launchd)?;
            for i in 1..=15 {
                tokio::time::sleep(Duration::from_secs(1)).await;
                if check_port_listening(SERVICE_PORT).is_some() {
                    info!("[服务] ✓ LaunchAgent 重启成功 ({}秒)", i);
                    return Ok("服务已通过 LaunchAgent 重启".to_string());
                }
            }
            return Err(AppError::timeout("Gateway LaunchAgent 重启超时（15秒）"));
        }
    }

    shell::run_openclaw(&["--version"])
        .map_err(|e| AppError::process(format!("OpenClaw CLI 预检失败: {}", e)))?;
    stop_service_locked().await?;
    // 异步等待服务完全停止后再启动，避免阻塞 tokio 线程池
    tokio::time::sleep(Duration::from_secs(1)).await;

    // 再启动
    start_service_locked().await
}

#[cfg(test)]
mod process_ownership_tests {
    use super::{command_line_is_openclaw_gateway, parse_launchctl_path, parse_launchctl_pid};

    #[test]
    fn accepts_openclaw_gateway_command_lines() {
        assert!(command_line_is_openclaw_gateway(
            "/opt/homebrew/bin/node /opt/homebrew/lib/node_modules/openclaw/dist/index.js gateway --port 18789"
        ));
        assert!(command_line_is_openclaw_gateway(
            "C:\\Users\\boss\\AppData\\Roaming\\npm\\openclaw.cmd gateway --port 18789"
        ));
    }

    #[test]
    fn rejects_unrelated_processes_on_the_same_port() {
        assert!(!command_line_is_openclaw_gateway(
            "python3 -m http.server 18789"
        ));
        assert!(!command_line_is_openclaw_gateway(
            "node unrelated-server.js --port 18789"
        ));
        assert!(!command_line_is_openclaw_gateway("openclaw status"));
    }

    #[test]
    fn accepts_only_pid_from_exact_launchctl_field() {
        let output = "path = /Users/boss/Library/LaunchAgents/ai.openclaw.gateway.plist\nstate = running\n\tpid = 877\nother pid text = 42\n";
        assert_eq!(parse_launchctl_pid(output), Some(877));
        assert_eq!(
            parse_launchctl_path(output).as_deref(),
            Some("/Users/boss/Library/LaunchAgents/ai.openclaw.gateway.plist")
        );
        assert_eq!(parse_launchctl_pid("state = running"), None);
    }
}

/// 日志脱敏正则：掩码 API Key / Token / Cookie / 密码等敏感信息
static LOG_SCRUB_PATTERNS: Lazy<Vec<(Regex, &'static str)>> = Lazy::new(|| {
    vec![
    // Bearer Token
    (Regex::new(r"(?i)Bearer\s+[A-Za-z0-9_\-./+=]{8,}").unwrap(), "Bearer ****"),
    // 常见 Key 前缀: sk- / gsk_ / xai- / nvapi- / ghp_
    (Regex::new(r"(?i)\b(sk-|gsk_|xai-|nvapi-|ghp_|glpat-)[A-Za-z0-9_\-./+=]{8,}").unwrap(), "$1****"),
    // api_key=xxx / token=xxx / password=xxx 等 Key-Value 对
    (Regex::new(r#"(?i)(api[_-]?key|token|secret|password|authorization|cookie|credential|app[_-]?key)[=:]\s*["']?[A-Za-z0-9_\-./+=]{8,}["']?"#).unwrap(), "$1=****"),
    // JSON 格式敏感字段: "api_key": "xxx"
    (Regex::new(r#"(?i)"(api[_-]?key|token|secret|password|authorization|cookie|app[_-]?key)"\s*:\s*"[^"]{8,}""#).unwrap(), r#""$1":"****""#),
]
});

/// 对单行日志进行敏感信息脱敏
fn scrub_log_line(line: &str) -> String {
    let mut result = line.to_string();
    for (pattern, replacement) in LOG_SCRUB_PATTERNS.iter() {
        result = pattern.replace_all(&result, *replacement).to_string();
    }
    result
}

/// 获取日志（直接读取日志文件，比 RPC 更可靠）
/// 返回前自动脱敏敏感信息（API Key / Token / Cookie / 密码）
#[command]
pub async fn get_logs(lines: Option<u32>) -> AppResult<Vec<String>> {
    let n = lines.unwrap_or(100);

    let config_dir = crate::utils::platform::get_config_dir();

    // 尝试多个已知的日志文件位置
    let log_files = vec![
        format!("{}/logs/gateway.log", config_dir),
        format!("{}/logs/gateway.err.log", config_dir),
        format!("{}/stderr.log", config_dir),
        format!("{}/stdout.log", config_dir),
    ];

    let mut all_lines: Vec<String> = Vec::new();

    for log_file in &log_files {
        if !std::path::Path::new(log_file).exists() {
            continue;
        }

        // 使用 tail 高效读取最后 N 行
        match Command::new("tail")
            .args(["-n", &n.to_string(), log_file])
            .output()
        {
            Ok(output) if output.status.success() => {
                let content = String::from_utf8_lossy(&output.stdout);
                for line in content.lines() {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        // 脱敏后再加入结果
                        all_lines.push(scrub_log_line(trimmed));
                    }
                }
            }
            _ => continue,
        }
    }

    // 尝试按时间戳排序（日志格式通常以 ISO 时间戳开头）
    all_lines.sort();

    // 去重并保留最后 N 行
    all_lines.dedup();
    let total = all_lines.len();
    if total > n as usize {
        all_lines = all_lines.split_off(total - n as usize);
    }

    Ok(all_lines)
}

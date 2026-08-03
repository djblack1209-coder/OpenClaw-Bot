use crate::models::{AppError, ErrorKind};
use crate::utils::file;
use crate::utils::platform;
use log::{debug, info, warn};
use std::collections::HashMap;
use std::io;
use std::process::{Command, Output};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Windows CREATE_NO_WINDOW 标志，用于隐藏控制台窗口
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

/// 命令白名单 — 只有列表中的可执行程序才允许被 spawn
/// 安全加固: 防止任意命令注入，所有 shell 调用必须经过白名单校验
const ALLOWED_COMMANDS: &[&str] = &[
    "lsof",
    "netstat",
    "kill",
    "taskkill",
    "tail",
    "launchctl",
    "bash",
    "pgrep",
    "open",
    "xdg-open",
    "cmd",
    "openclaw",
    "node",
    "npx",
    "npm",
    "python3",
    "pip3",
    "chmod",
    "uname",
    "sw_vers",
    "sysctl",
    "id",
    "which",
    "where",
    "nohup",
    "ps",
    "powershell",
];

/// 校验命令是否在白名单中
/// 提取 program 的基础文件名（去掉路径前缀），与白名单比对
pub fn validate_command(cmd: &str) -> Result<(), AppError> {
    // 提取命令的 basename（支持 /usr/bin/lsof 和 lsof 两种格式）
    let basename = std::path::Path::new(cmd)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(cmd);

    // Windows 上去掉 .exe / .cmd 后缀再比对
    let normalized = basename
        .strip_suffix(".exe")
        .or_else(|| basename.strip_suffix(".cmd"))
        .unwrap_or(basename);

    if ALLOWED_COMMANDS.contains(&normalized) {
        Ok(())
    } else {
        warn!(
            "[Shell] 命令被拒绝（不在白名单中）: {} (basename: {})",
            cmd, normalized
        );
        Err(AppError::new(
            ErrorKind::Permission,
            format!("命令 '{}' 不在白名单中，禁止执行", normalized),
        ))
    }
}

/// 获取扩展的 PATH 环境变量
/// GUI 应用启动时可能没有继承用户 shell 的 PATH，需要手动添加常见路径
pub fn get_extended_path() -> String {
    let mut paths = vec![
        "/opt/homebrew/bin".to_string(), // Homebrew on Apple Silicon
        "/usr/local/bin".to_string(),    // Homebrew on Intel / 常规安装
        "/usr/bin".to_string(),
        "/bin".to_string(),
    ];

    if let Some(home) = dirs::home_dir() {
        let home_str = home.display().to_string();

        // nvm 路径（尝试获取当前版本）
        let nvm_default = format!("{}/.nvm/alias/default", home_str);
        if let Ok(version) = std::fs::read_to_string(&nvm_default) {
            let version = version.trim();
            if !version.is_empty() {
                paths.insert(
                    0,
                    format!("{}/.nvm/versions/node/v{}/bin", home_str, version),
                );
            }
        }
        // 也添加常见 nvm 版本路径
        for version in ["v22.22.0", "v22.12.0", "v22.11.0", "v22.0.0", "v23.0.0"] {
            let nvm_bin = format!("{}/.nvm/versions/node/{}/bin", home_str, version);
            if std::path::Path::new(&nvm_bin).exists() {
                paths.insert(0, nvm_bin);
                break; // 只添加第一个存在的
            }
        }

        // fnm
        paths.push(format!("{}/.fnm/aliases/default/bin", home_str));

        // volta
        paths.push(format!("{}/.volta/bin", home_str));

        // asdf
        paths.push(format!("{}/.asdf/shims", home_str));

        // mise
        paths.push(format!("{}/.local/share/mise/shims", home_str));
    }

    // 获取当前 PATH 并合并
    let current_path = std::env::var("PATH").unwrap_or_default();
    if !current_path.is_empty() {
        paths.push(current_path);
    }

    paths.join(":")
}

/// 执行 Shell 命令（带扩展 PATH）
/// 安全加固: 执行前校验命令是否在白名单中
pub fn run_command(cmd: &str, args: &[&str]) -> io::Result<Output> {
    // 白名单校验 — 不在列表中的命令直接拒绝
    if let Err(e) = validate_command(cmd) {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, e.message));
    }

    let mut command = Command::new(cmd);
    command.args(args);

    // 在非 Windows 系统上使用扩展的 PATH
    #[cfg(not(windows))]
    {
        let extended_path = get_extended_path();
        command.env("PATH", extended_path);
    }

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command.output()
}

/// 执行 Shell 命令并获取输出字符串
pub fn run_command_output(cmd: &str, args: &[&str]) -> Result<String, String> {
    match run_command(cmd, args) {
        Ok(output) => {
            if output.status.success() {
                Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
            } else {
                Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
            }
        }
        Err(e) => Err(e.to_string()),
    }
}

/// 读取指定 PID 的完整命令行，用于停止服务前核验进程身份。
pub fn get_process_command_line(pid: u32) -> io::Result<String> {
    if pid <= 1 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "拒绝查询系统关键 PID",
        ));
    }

    #[cfg(unix)]
    let output = {
        validate_command("ps")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        Command::new("ps")
            .args(["-p", &pid.to_string(), "-o", "command="])
            .output()?
    };

    #[cfg(windows)]
    let output = {
        validate_command("powershell")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        let query = format!(
            "(Get-CimInstance Win32_Process -Filter 'ProcessId = {}').CommandLine",
            pid
        );
        let mut command = Command::new("powershell");
        command
            .args(["-NoProfile", "-NonInteractive", "-Command", &query])
            .creation_flags(CREATE_NO_WINDOW);
        command.output()?
    };

    if !output.status.success() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            format!("无法读取 PID {} 的进程信息", pid),
        ));
    }
    let command_line = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if command_line.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            format!("PID {} 不存在或命令行不可读", pid),
        ));
    }
    Ok(command_line)
}

/// 向已经完成身份核验的进程发送终止信号。
pub fn signal_process(pid: u32, force: bool) -> io::Result<()> {
    if pid <= 1 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "拒绝终止系统关键 PID",
        ));
    }

    #[cfg(unix)]
    let output = {
        validate_command("kill")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        let signal = if force { "-KILL" } else { "-TERM" };
        Command::new("kill")
            .args([signal, &pid.to_string()])
            .output()?
    };

    #[cfg(windows)]
    let output = {
        validate_command("taskkill")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        let mut command = Command::new("taskkill");
        if force {
            command.args(["/F", "/T", "/PID", &pid.to_string()]);
        } else {
            command.args(["/T", "/PID", &pid.to_string()]);
        }
        command.creation_flags(CREATE_NO_WINDOW);
        command.output()?
    };

    if output.status.success() {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::Other,
            String::from_utf8_lossy(&output.stderr).trim().to_string(),
        ))
    }
}

/// 终止由管理器创建的独立进程组；调用前必须核验组长身份。
pub fn signal_process_group(process_group_id: u32, force: bool) -> io::Result<()> {
    if process_group_id <= 1 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "拒绝终止系统关键进程组",
        ));
    }

    #[cfg(unix)]
    let output = {
        validate_command("kill")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        let signal = if force { "-KILL" } else { "-TERM" };
        Command::new("kill")
            .args([signal, &format!("-{}", process_group_id)])
            .output()?
    };

    #[cfg(windows)]
    let output = {
        validate_command("taskkill")
            .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.message))?;
        let mut command = Command::new("taskkill");
        if force {
            command.args(["/F", "/T", "/PID", &process_group_id.to_string()]);
        } else {
            command.args(["/T", "/PID", &process_group_id.to_string()]);
        }
        command.creation_flags(CREATE_NO_WINDOW);
        command.output()?
    };

    if output.status.success() {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::Other,
            String::from_utf8_lossy(&output.stderr).trim().to_string(),
        ))
    }
}

/// 检查管理器进程组是否仍有成员存活。
pub fn process_group_is_running(process_group_id: u32) -> bool {
    if process_group_id <= 1 {
        return false;
    }

    #[cfg(unix)]
    {
        if validate_command("kill").is_err() {
            return false;
        }
        return Command::new("kill")
            .args(["-0", &format!("-{}", process_group_id)])
            .output()
            .map(|output| output.status.success())
            .unwrap_or(false);
    }

    #[cfg(windows)]
    {
        get_process_command_line(process_group_id).is_ok()
    }
}

fn gateway_pid_file_path() -> String {
    format!("{}/manager-pids/gateway.pid", platform::get_config_dir())
}

/// 读取由管理器直接启动并登记的 Gateway PID。
pub fn read_managed_gateway_pid() -> io::Result<Option<u32>> {
    let path = gateway_pid_file_path();
    if !std::path::Path::new(&path).exists() {
        return Ok(None);
    }
    let raw = file::read_file(&path)?;
    let pid = raw
        .trim()
        .parse::<u32>()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Gateway PID 记录格式无效"))?;
    if pid <= 1 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Gateway PID 记录不安全",
        ));
    }
    Ok(Some(pid))
}

/// 清除管理器拥有的 Gateway PID 记录。
pub fn clear_managed_gateway_pid() -> io::Result<()> {
    let path = gateway_pid_file_path();
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

fn clear_managed_gateway_pid_if_matches(pid: u32) {
    if matches!(read_managed_gateway_pid(), Ok(Some(recorded_pid)) if recorded_pid == pid) {
        let _ = clear_managed_gateway_pid();
    }
}

/// 执行 Bash 命令（带扩展 PATH）
/// 注意: bash 本身在白名单中，但传入的 script 内容不受白名单约束
/// 调用方需确保 script 内容不来自用户可控输入
pub fn run_bash(script: &str) -> io::Result<Output> {
    let mut command = Command::new("bash");
    command.arg("-c").arg(script);

    // 在非 Windows 系统上使用扩展的 PATH
    #[cfg(not(windows))]
    {
        let extended_path = get_extended_path();
        command.env("PATH", extended_path);
    }

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command.output()
}

/// 执行 Bash 命令并获取输出
pub fn run_bash_output(script: &str) -> Result<String, String> {
    match run_bash(script) {
        Ok(output) => {
            if output.status.success() {
                Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if stderr.is_empty() {
                    Err(format!(
                        "Command failed with exit code: {:?}",
                        output.status.code()
                    ))
                } else {
                    Err(stderr)
                }
            }
        }
        Err(e) => Err(e.to_string()),
    }
}

/// 执行 cmd.exe 命令（Windows）- 避免 PowerShell 执行策略问题
pub fn run_cmd(script: &str) -> io::Result<Output> {
    let mut cmd = Command::new("cmd");
    cmd.args(["/c", script]);

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    cmd.output()
}

/// 执行 cmd.exe 命令并获取输出（Windows）
pub fn run_cmd_output(script: &str) -> Result<String, String> {
    match run_cmd(script) {
        Ok(output) => {
            if output.status.success() {
                Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if stderr.is_empty() {
                    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    if stdout.is_empty() {
                        Err(format!(
                            "Command failed with exit code: {:?}",
                            output.status.code()
                        ))
                    } else {
                        Err(stdout)
                    }
                } else {
                    Err(stderr)
                }
            }
        }
        Err(e) => Err(e.to_string()),
    }
}

/// 执行 PowerShell 命令（Windows）- 仅在需要 PowerShell 特定功能时使用
/// 注意：某些 Windows 系统的 PowerShell 执行策略可能禁止运行脚本
pub fn run_powershell(script: &str) -> io::Result<Output> {
    let mut cmd = Command::new("powershell");
    // 使用 -ExecutionPolicy Bypass 绕过执行策略限制
    cmd.args([
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]);

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    cmd.output()
}

/// 执行 PowerShell 命令并获取输出（Windows）
pub fn run_powershell_output(script: &str) -> Result<String, String> {
    match run_powershell(script) {
        Ok(output) => {
            if output.status.success() {
                Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if stderr.is_empty() {
                    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    if stdout.is_empty() {
                        Err(format!(
                            "Command failed with exit code: {:?}",
                            output.status.code()
                        ))
                    } else {
                        Err(stdout)
                    }
                } else {
                    Err(stderr)
                }
            }
        }
        Err(e) => Err(e.to_string()),
    }
}

/// 跨平台执行脚本命令
/// Windows 上使用 cmd.exe（避免 PowerShell 执行策略问题）
pub fn run_script_output(script: &str) -> Result<String, String> {
    if platform::is_windows() {
        run_cmd_output(script)
    } else {
        run_bash_output(script)
    }
}

/// 获取 openclaw 可执行文件路径
/// 检测多个可能的安装路径，因为 GUI 应用不继承用户 shell 的 PATH
pub fn get_openclaw_path() -> Option<String> {
    // Windows: 检查常见的 npm 全局安装路径
    if platform::is_windows() {
        let possible_paths = get_windows_openclaw_paths();
        for path in possible_paths {
            if std::path::Path::new(&path).exists() {
                info!("[Shell] 在 {} 找到 openclaw", path);
                return Some(path);
            }
        }
    } else {
        // Unix: 检查常见的 npm 全局安装路径
        let possible_paths = get_unix_openclaw_paths();
        for path in possible_paths {
            if std::path::Path::new(&path).exists() {
                info!("[Shell] 在 {} 找到 openclaw", path);
                return Some(path);
            }
        }
    }

    // 回退：检查是否在 PATH 中
    if command_exists("openclaw") {
        return Some("openclaw".to_string());
    }

    // 最后尝试：通过用户 shell 查找
    if !platform::is_windows() {
        if let Ok(path) = run_bash_output("source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null; which openclaw 2>/dev/null") {
            if !path.is_empty() && std::path::Path::new(&path).exists() {
                info!("[Shell] 通过用户 shell 找到 openclaw: {}", path);
                return Some(path);
            }
        }
    }

    None
}

/// 获取 Unix 系统上可能的 openclaw 安装路径
fn get_unix_openclaw_paths() -> Vec<String> {
    let mut paths = Vec::new();

    // npm 全局安装路径
    paths.push("/usr/local/bin/openclaw".to_string());
    paths.push("/opt/homebrew/bin/openclaw".to_string()); // Homebrew on Apple Silicon
    paths.push("/usr/bin/openclaw".to_string());

    if let Some(home) = dirs::home_dir() {
        let home_str = home.display().to_string();

        // npm 全局安装到用户目录
        paths.push(format!("{}/.npm-global/bin/openclaw", home_str));

        // nvm 安装的 npm 全局包（需要找到正确的 node 版本目录）
        // 先检查常见版本
        for version in [
            "v22.0.0", "v22.1.0", "v22.2.0", "v22.11.0", "v22.12.0", "v23.0.0",
        ] {
            paths.push(format!(
                "{}/.nvm/versions/node/{}/bin/openclaw",
                home_str, version
            ));
        }

        // 检查 nvm current（尝试读取 .nvmrc 或 default）
        let nvm_default = format!("{}/.nvm/alias/default", home_str);
        if let Ok(version) = std::fs::read_to_string(&nvm_default) {
            let version = version.trim();
            if !version.is_empty() {
                paths.insert(
                    0,
                    format!("{}/.nvm/versions/node/v{}/bin/openclaw", home_str, version),
                );
            }
        }

        // fnm
        paths.push(format!("{}/.fnm/aliases/default/bin/openclaw", home_str));

        // volta
        paths.push(format!("{}/.volta/bin/openclaw", home_str));

        // pnpm 全局安装
        paths.push(format!("{}/.pnpm/bin/openclaw", home_str));
        paths.push(format!("{}/Library/pnpm/openclaw", home_str)); // macOS pnpm 默认路径

        // asdf
        paths.push(format!("{}/.asdf/shims/openclaw", home_str));

        // mise (formerly rtx)
        paths.push(format!("{}/.local/share/mise/shims/openclaw", home_str));

        // yarn 全局安装
        paths.push(format!("{}/.yarn/bin/openclaw", home_str));
        paths.push(format!(
            "{}/.config/yarn/global/node_modules/.bin/openclaw",
            home_str
        ));
    }

    paths
}

/// 获取 Windows 上可能的 openclaw 安装路径
fn get_windows_openclaw_paths() -> Vec<String> {
    let mut paths = Vec::new();

    // 1. nvm4w 安装路径
    paths.push("C:\\nvm4w\\nodejs\\openclaw.cmd".to_string());

    // 2. 用户目录下的 npm 全局路径
    if let Some(home) = dirs::home_dir() {
        let npm_path = format!("{}\\AppData\\Roaming\\npm\\openclaw.cmd", home.display());
        paths.push(npm_path);
    }

    // 3. Program Files 下的 nodejs
    paths.push("C:\\Program Files\\nodejs\\openclaw.cmd".to_string());

    paths
}

/// 执行 openclaw 命令并获取输出
pub fn run_openclaw(args: &[&str]) -> Result<String, String> {
    debug!("[Shell] 执行 openclaw 命令: {:?}", args);

    let openclaw_path = get_openclaw_path().ok_or_else(|| {
        warn!("[Shell] 找不到 openclaw 命令");
        "找不到 openclaw 命令，请确保已通过 npm install -g openclaw 安装".to_string()
    })?;

    debug!("[Shell] openclaw 路径: {}", openclaw_path);

    // 获取扩展的 PATH，确保能找到 node
    let extended_path = get_extended_path();
    debug!("[Shell] 扩展 PATH: {}", extended_path);
    let gateway_token = crate::commands::config::get_gateway_token_env_override()
        .map_err(|e| format!("准备 Gateway Token 失败: {}", e.message))?;
    let user_env_vars = load_openclaw_env_vars();

    let output = if openclaw_path.ends_with(".cmd") {
        // Windows: .cmd 文件需要通过 cmd /c 执行
        let mut cmd_args = vec!["/c", &openclaw_path];
        cmd_args.extend(args);
        let mut cmd = Command::new("cmd");
        cmd.args(&cmd_args)
            .env("PATH", &extended_path)
            .envs(&user_env_vars);
        apply_gateway_token_env(&mut cmd, &gateway_token);

        #[cfg(windows)]
        cmd.creation_flags(CREATE_NO_WINDOW);

        cmd.output()
    } else {
        let mut cmd = Command::new(&openclaw_path);
        cmd.args(args)
            .env("PATH", &extended_path)
            .envs(&user_env_vars);
        apply_gateway_token_env(&mut cmd, &gateway_token);

        #[cfg(windows)]
        cmd.creation_flags(CREATE_NO_WINDOW);

        cmd.output()
    };

    match output {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).to_string();
            let stderr = String::from_utf8_lossy(&out.stderr).to_string();
            debug!("[Shell] 命令退出码: {:?}", out.status.code());
            if out.status.success() {
                debug!("[Shell] 命令执行成功, stdout 长度: {}", stdout.len());
                Ok(stdout)
            } else {
                debug!("[Shell] 命令执行失败, stderr: {}", stderr);
                Err(format!("{}\n{}", stdout, stderr).trim().to_string())
            }
        }
        Err(e) => {
            warn!("[Shell] 执行 openclaw 失败: {}", e);
            Err(format!("执行 openclaw 失败: {}", e))
        }
    }
}

fn apply_gateway_token_env(
    command: &mut Command,
    gateway_token: &crate::commands::config::GatewayTokenEnv,
) {
    match gateway_token {
        crate::commands::config::GatewayTokenEnv::Override(token) => {
            command.env("OPENCLAW_GATEWAY_TOKEN", token);
        }
        crate::commands::config::GatewayTokenEnv::RemoveOverride => {
            command.env_remove("OPENCLAW_GATEWAY_TOKEN");
        }
        crate::commands::config::GatewayTokenEnv::Inherit => {}
    }
}

/// 从 ~/.openclaw/env 文件读取所有环境变量
/// 与 shell 脚本 `source ~/.openclaw/env` 行为一致
fn load_openclaw_env_vars() -> HashMap<String, String> {
    let mut env_vars = HashMap::new();
    let env_path = platform::get_env_file_path();

    if let Ok(content) = file::read_file(&env_path) {
        for line in content.lines() {
            if let Some((key, value)) = file::parse_env_assignment(line) {
                env_vars.insert(key, value);
            }
        }
    }

    env_vars
}

/// 后台启动 openclaw gateway
/// 与 shell 脚本行为一致：先加载 env 文件，再启动 gateway
pub fn spawn_openclaw_gateway() -> io::Result<u32> {
    info!("[Shell] 后台启动 openclaw gateway...");

    let openclaw_path = get_openclaw_path().ok_or_else(|| {
        warn!("[Shell] 找不到 openclaw 命令");
        io::Error::new(
            io::ErrorKind::NotFound,
            "找不到 openclaw 命令，请确保已通过 npm install -g openclaw 安装",
        )
    })?;

    info!("[Shell] openclaw 路径: {}", openclaw_path);

    // 加载用户的 env 文件环境变量（与 shell 脚本 source ~/.openclaw/env 一致）
    info!("[Shell] 加载用户环境变量...");
    let user_env_vars = load_openclaw_env_vars();
    info!("[Shell] 已加载 {} 个环境变量", user_env_vars.len());
    for key in user_env_vars.keys() {
        debug!("[Shell] - 环境变量: {}", key);
    }

    // 获取扩展的 PATH，确保能找到 node
    let extended_path = get_extended_path();
    info!("[Shell] 扩展 PATH: {}", extended_path);
    let gateway_token = crate::commands::config::ensure_gateway_token_env_override()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.message))?;

    // Windows 上 .cmd 文件需要通过 cmd /c 来执行。
    let mut cmd = if openclaw_path.ends_with(".cmd") {
        info!("[Shell] Windows 模式: 使用 cmd /c 执行");
        let mut c = Command::new("cmd");
        c.args(["/c", &openclaw_path, "gateway", "--port", "18789"]);
        c
    } else {
        info!("[Shell] Unix 模式: 直接执行");
        let mut c = Command::new(&openclaw_path);
        c.args(["gateway", "--port", "18789"]);
        c
    };

    // 注入用户的环境变量（如 ANTHROPIC_API_KEY, OPENAI_API_KEY 等）
    for (key, value) in &user_env_vars {
        cmd.env(key, value);
    }

    // 明文配置注入统一 Token；SecretRef 模式必须让 OpenClaw 官方运行时自行解析。
    cmd.env("PATH", &extended_path);
    apply_gateway_token_env(&mut cmd, &gateway_token);

    // Windows: 隐藏控制台窗口
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    // 将 stdout/stderr 重定向到日志文件，以便 get_logs 可以读取
    let logs_dir = format!("{}/logs", platform::get_config_dir());
    let _ = std::fs::create_dir_all(&logs_dir);

    let stdout_log_path = format!("{}/gateway.log", logs_dir);
    let stderr_log_path = format!("{}/gateway.err.log", logs_dir);

    info!(
        "[Shell] 日志输出到: {} / {}",
        stdout_log_path, stderr_log_path
    );

    if let Ok(stdout_file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&stdout_log_path)
    {
        cmd.stdout(std::process::Stdio::from(stdout_file));
    }
    if let Ok(stderr_file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&stderr_log_path)
    {
        cmd.stderr(std::process::Stdio::from(stderr_file));
    }

    info!("[Shell] 启动 gateway 进程...");
    let child = cmd.spawn();

    match child {
        Ok(mut child) => {
            let pid = child.id();
            if let Err(error) = file::write_file(&gateway_pid_file_path(), &pid.to_string()) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(io::Error::new(
                    error.kind(),
                    format!("Gateway 已启动但 PID 登记失败，进程已终止: {}", error),
                ));
            }
            std::thread::spawn(move || {
                let _ = child.wait();
                clear_managed_gateway_pid_if_matches(pid);
            });
            info!("[Shell] ✓ Gateway 进程已启动并登记所有权, PID: {}", pid);
            Ok(pid)
        }
        Err(e) => {
            warn!("[Shell] ✗ Gateway 启动失败: {}", e);
            Err(io::Error::new(
                e.kind(),
                format!("启动失败 (路径: {}): {}", openclaw_path, e),
            ))
        }
    }
}

/// 检查命令是否存在
pub fn command_exists(cmd: &str) -> bool {
    if platform::is_windows() {
        // Windows: 使用 where 命令
        let mut command = Command::new("where");
        command.arg(cmd);

        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        command
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    } else {
        // Unix: 使用 which 命令
        Command::new("which")
            .arg(cmd)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }
}

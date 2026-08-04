use crate::commands::npm_runtime::{
    ensure_managed_runtime, locked_package_version, managed_bin_path,
};
use crate::models::{AppError, AppResult};
use crate::utils::{platform, shell};
use log::{debug, error, info, warn};
use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tauri::command;

fn bundled_openclaw_version() -> AppResult<String> {
    locked_package_version("openclaw")
}

fn output_text(output: Output) -> Result<String, String> {
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        Err(if stderr.is_empty() { stdout } else { stderr })
    }
}

/// 安装器只能调用这里列出的包管理器，参数由 Rust 固定构造，不接收 WebView 输入。
fn run_installer_command(command: &str, args: &[&str]) -> Result<String, String> {
    let allowed_commands = ["brew", "winget"];
    let basename = Path::new(command)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(command);
    if !allowed_commands.contains(&basename) {
        return Err(format!("安装器拒绝调用未授权命令: {}", basename));
    }

    Command::new(command)
        .args(args)
        .output()
        .map_err(|error| format!("启动 {} 失败: {}", basename, error))
        .and_then(output_text)
}

async fn install_locked_openclaw_runtime() -> Result<String, String> {
    tokio::task::spawn_blocking(|| {
        ensure_managed_runtime().map_err(|error| error.to_string())?;
        let binary = managed_bin_path("openclaw").map_err(|error| error.to_string())?;
        Command::new(&binary)
            .arg("--version")
            .output()
            .map_err(|error| format!("启动受管 OpenClaw 失败: {}", error))
            .and_then(output_text)
    })
    .await
    .map_err(|error| format!("等待 npm 完整性锁安装失败: {}", error))?
}

fn create_private_install_script(extension: &str, content: &str) -> AppResult<PathBuf> {
    let mut random = [0_u8; 16];
    getrandom::getrandom(&mut random)
        .map_err(|error| AppError::io(format!("生成安装脚本随机名称失败: {}", error)))?;
    let token: String = random.iter().map(|byte| format!("{:02x}", byte)).collect();
    let path = std::env::temp_dir().join(format!("openclaw-install-{}.{}", token, extension));

    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o700);
    }

    let mut file = options
        .open(&path)
        .map_err(|error| AppError::io(format!("安全创建安装脚本失败: {}", error)))?;
    if let Err(error) = file
        .write_all(content.as_bytes())
        .and_then(|()| file.sync_all())
    {
        let _ = fs::remove_file(&path);
        return Err(AppError::io(format!("写入安装脚本失败: {}", error)));
    }
    Ok(path)
}

fn launch_script_with(command: &str, args: &[&str], script_path: &Path) -> AppResult<()> {
    let mut child = Command::new(command);
    child.args(args).arg(script_path);
    child
        .spawn()
        .map(|_| ())
        .map_err(|error| AppError::process(format!("启动安装终端失败: {}", error)))
}

/// 环境检查结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentStatus {
    /// Node.js 是否安装
    pub node_installed: bool,
    /// Node.js 版本
    pub node_version: Option<String>,
    /// Node.js 版本是否满足要求 (>=22)
    pub node_version_ok: bool,
    /// OpenClaw 是否安装
    pub openclaw_installed: bool,
    /// OpenClaw 版本
    pub openclaw_version: Option<String>,
    /// 配置目录是否存在
    pub config_dir_exists: bool,
    /// 是否全部就绪
    pub ready: bool,
    /// 操作系统
    pub os: String,
}

/// 安装进度
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallProgress {
    pub step: String,
    pub progress: u8,
    pub message: String,
    pub error: Option<String>,
}

/// 安装结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallResult {
    pub success: bool,
    pub message: String,
    pub error: Option<String>,
}

/// 检查环境状态
#[command]
pub async fn check_environment() -> AppResult<EnvironmentStatus> {
    info!("[环境检查] 开始检查系统环境...");

    let os = platform::get_os();
    info!("[环境检查] 操作系统: {}", os);

    // 检查 Node.js
    info!("[环境检查] 检查 Node.js...");
    let node_version = get_node_version();
    let node_installed = node_version.is_some();
    let node_version_ok = check_node_version_requirement(&node_version);
    info!(
        "[环境检查] Node.js: installed={}, version={:?}, version_ok={}",
        node_installed, node_version, node_version_ok
    );

    // 检查 OpenClaw
    info!("[环境检查] 检查 OpenClaw...");
    let openclaw_version = get_openclaw_version();
    let openclaw_installed = openclaw_version.is_some();
    info!(
        "[环境检查] OpenClaw: installed={}, version={:?}",
        openclaw_installed, openclaw_version
    );

    // 检查配置目录
    let config_dir = platform::get_config_dir();
    let config_dir_exists = std::path::Path::new(&config_dir).exists();
    info!(
        "[环境检查] 配置目录: {}, exists={}",
        config_dir, config_dir_exists
    );

    let ready = node_installed && node_version_ok && openclaw_installed;
    info!("[环境检查] 环境就绪状态: ready={}", ready);

    Ok(EnvironmentStatus {
        node_installed,
        node_version,
        node_version_ok,
        openclaw_installed,
        openclaw_version,
        config_dir_exists,
        ready,
        os,
    })
}

/// 获取 Node.js 版本
/// 检测多个可能的安装路径，因为 GUI 应用不继承用户 shell 的 PATH
fn get_node_version() -> Option<String> {
    if platform::is_windows() {
        // Windows: 先尝试直接调用（如果 PATH 已更新）
        if let Ok(v) = shell::run_cmd_output("node --version") {
            let version = v.trim().to_string();
            if !version.is_empty() && version.starts_with('v') {
                info!("[环境检查] 通过 PATH 找到 Node.js: {}", version);
                return Some(version);
            }
        }

        // Windows: 检查常见的安装路径
        let possible_paths = get_windows_node_paths();
        for path in possible_paths {
            if std::path::Path::new(&path).exists() {
                // 使用完整路径执行
                let cmd = format!("\"{}\" --version", path);
                if let Ok(output) = shell::run_cmd_output(&cmd) {
                    let version = output.trim().to_string();
                    if !version.is_empty() && version.starts_with('v') {
                        info!("[环境检查] 在 {} 找到 Node.js: {}", path, version);
                        return Some(version);
                    }
                }
            }
        }

        None
    } else {
        // 先尝试直接调用
        if let Ok(v) = shell::run_command_output("node", &["--version"]) {
            return Some(v.trim().to_string());
        }

        // 检测常见的 Node.js 安装路径（macOS/Linux）
        let possible_paths = get_unix_node_paths();
        for path in possible_paths {
            if std::path::Path::new(&path).exists() {
                if let Ok(output) = shell::run_command_output(&path, &["--version"]) {
                    info!("[环境检查] 在 {} 找到 Node.js: {}", path, output.trim());
                    return Some(output.trim().to_string());
                }
            }
        }

        // 尝试通过 shell 加载用户环境来检测
        if let Ok(output) = shell::run_bash_output("source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null; node --version 2>/dev/null") {
            if !output.is_empty() && output.starts_with('v') {
                info!("[环境检查] 通过用户 shell 找到 Node.js: {}", output.trim());
                return Some(output.trim().to_string());
            }
        }

        None
    }
}

/// 获取 Unix 系统上可能的 Node.js 路径
fn get_unix_node_paths() -> Vec<String> {
    let mut paths = Vec::new();

    // Homebrew (macOS)
    paths.push("/opt/homebrew/bin/node".to_string()); // Apple Silicon
    paths.push("/usr/local/bin/node".to_string()); // Intel Mac

    // 系统安装
    paths.push("/usr/bin/node".to_string());

    // nvm (检查常见版本)
    if let Some(home) = dirs::home_dir() {
        let home_str = home.display().to_string();

        // nvm 默认版本
        paths.push(format!("{}/.nvm/versions/node/v22.0.0/bin/node", home_str));
        paths.push(format!("{}/.nvm/versions/node/v22.1.0/bin/node", home_str));
        paths.push(format!("{}/.nvm/versions/node/v22.2.0/bin/node", home_str));
        paths.push(format!("{}/.nvm/versions/node/v22.11.0/bin/node", home_str));
        paths.push(format!("{}/.nvm/versions/node/v22.12.0/bin/node", home_str));
        paths.push(format!("{}/.nvm/versions/node/v23.0.0/bin/node", home_str));

        // 尝试 nvm alias default（读取 nvm 的 default alias）
        let nvm_default = format!("{}/.nvm/alias/default", home_str);
        if let Ok(version) = std::fs::read_to_string(&nvm_default) {
            let version = version.trim();
            if !version.is_empty() {
                paths.insert(
                    0,
                    format!("{}/.nvm/versions/node/v{}/bin/node", home_str, version),
                );
            }
        }

        // fnm
        paths.push(format!("{}/.fnm/aliases/default/bin/node", home_str));

        // volta
        paths.push(format!("{}/.volta/bin/node", home_str));

        // asdf
        paths.push(format!("{}/.asdf/shims/node", home_str));

        // mise (formerly rtx)
        paths.push(format!("{}/.local/share/mise/shims/node", home_str));
    }

    paths
}

/// 获取 Windows 系统上可能的 Node.js 路径
fn get_windows_node_paths() -> Vec<String> {
    let mut paths = Vec::new();

    // 1. 标准安装路径 (Program Files)
    paths.push("C:\\Program Files\\nodejs\\node.exe".to_string());
    paths.push("C:\\Program Files (x86)\\nodejs\\node.exe".to_string());

    // 2. nvm for Windows (nvm4w) - 常见安装位置
    paths.push("C:\\nvm4w\\nodejs\\node.exe".to_string());

    // 3. 用户目录下的各种安装
    if let Some(home) = dirs::home_dir() {
        let home_str = home.display().to_string();

        // nvm for Windows 用户安装
        paths.push(format!(
            "{}\\AppData\\Roaming\\nvm\\current\\node.exe",
            home_str
        ));

        // fnm (Fast Node Manager) for Windows
        paths.push(format!(
            "{}\\AppData\\Roaming\\fnm\\aliases\\default\\node.exe",
            home_str
        ));
        paths.push(format!(
            "{}\\AppData\\Local\\fnm\\aliases\\default\\node.exe",
            home_str
        ));
        paths.push(format!("{}\\.fnm\\aliases\\default\\node.exe", home_str));

        // volta
        paths.push(format!(
            "{}\\AppData\\Local\\Volta\\bin\\node.exe",
            home_str
        ));
        // volta 通过 shim 调用，检查 bin 目录即可

        // scoop 安装
        paths.push(format!(
            "{}\\scoop\\apps\\nodejs\\current\\node.exe",
            home_str
        ));
        paths.push(format!(
            "{}\\scoop\\apps\\nodejs-lts\\current\\node.exe",
            home_str
        ));

        // chocolatey 安装
        paths.push("C:\\ProgramData\\chocolatey\\lib\\nodejs\\tools\\node.exe".to_string());
    }

    // 4. 从注册表读取的安装路径（通过环境变量间接获取）
    if let Ok(program_files) = std::env::var("ProgramFiles") {
        paths.push(format!("{}\\nodejs\\node.exe", program_files));
    }
    if let Ok(program_files_x86) = std::env::var("ProgramFiles(x86)") {
        paths.push(format!("{}\\nodejs\\node.exe", program_files_x86));
    }

    // 5. nvm-windows 的符号链接路径（NVM_SYMLINK 环境变量）
    if let Ok(nvm_symlink) = std::env::var("NVM_SYMLINK") {
        paths.insert(0, format!("{}\\node.exe", nvm_symlink));
    }

    // 6. nvm-windows 的 NVM_HOME 路径下的当前版本
    if let Ok(nvm_home) = std::env::var("NVM_HOME") {
        // 尝试读取当前激活的版本
        let settings_path = format!("{}\\settings.txt", nvm_home);
        if let Ok(content) = std::fs::read_to_string(&settings_path) {
            for line in content.lines() {
                if line.starts_with("current:") {
                    if let Some(version) = line.strip_prefix("current:") {
                        let version = version.trim();
                        if !version.is_empty() {
                            paths.insert(0, format!("{}\\v{}\\node.exe", nvm_home, version));
                        }
                    }
                }
            }
        }
    }

    paths
}

/// 获取 OpenClaw 版本
fn get_openclaw_version() -> Option<String> {
    // 使用 run_openclaw 统一处理各平台
    shell::run_openclaw(&["--version"])
        .ok()
        .map(|v| v.trim().to_string())
}

/// 检查 Node.js 版本是否 >= 22
fn check_node_version_requirement(version: &Option<String>) -> bool {
    if let Some(v) = version {
        // 解析版本号 "v22.1.0" -> 22
        let major = v
            .trim_start_matches('v')
            .split('.')
            .next()
            .and_then(|s| s.parse::<u32>().ok())
            .unwrap_or(0);
        major >= 22
    } else {
        false
    }
}

/// 安装 Node.js
#[command]
pub async fn install_nodejs() -> AppResult<InstallResult> {
    info!("[安装Node.js] 开始安装 Node.js...");
    let os = platform::get_os();
    info!("[安装Node.js] 检测到操作系统: {}", os);

    let result = match os.as_str() {
        "windows" => {
            info!("[安装Node.js] 使用 Windows 安装方式...");
            install_nodejs_windows().await
        }
        "macos" => {
            info!("[安装Node.js] 使用 macOS 安装方式 (Homebrew)...");
            install_nodejs_macos().await
        }
        "linux" => {
            info!("[安装Node.js] 使用 Linux 安装方式...");
            install_nodejs_linux().await
        }
        _ => {
            error!("[安装Node.js] 不支持的操作系统: {}", os);
            Ok(InstallResult {
                success: false,
                message: "不支持的操作系统".to_string(),
                error: Some(format!("不支持的操作系统: {}", os)),
            })
        }
    };

    match &result {
        Ok(r) if r.success => info!("[安装Node.js] ✓ 安装成功"),
        Ok(r) => warn!("[安装Node.js] ✗ 安装失败: {}", r.message),
        Err(e) => error!("[安装Node.js] ✗ 安装错误: {}", e),
    }

    result
}

/// Windows 安装 Node.js
async fn install_nodejs_windows() -> AppResult<InstallResult> {
    let args = [
        "install",
        "--id",
        "OpenJS.NodeJS.LTS",
        "--exact",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ];
    match run_installer_command("winget", &args) {
        Ok(output) => {
            // 验证安装
            if get_node_version().is_some() {
                Ok(InstallResult {
                    success: true,
                    message: "Node.js 安装成功！请重启应用以使环境变量生效。".to_string(),
                    error: None,
                })
            } else {
                Ok(InstallResult {
                    success: false,
                    message: "安装后需要重启应用".to_string(),
                    error: Some(output),
                })
            }
        }
        Err(e) => Ok(InstallResult {
            success: false,
            message: "Node.js 安装失败".to_string(),
            error: Some(e),
        }),
    }
}

/// macOS 安装 Node.js
async fn install_nodejs_macos() -> AppResult<InstallResult> {
    let brew = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
        .into_iter()
        .find(|path| Path::new(path).is_file());
    let Some(brew) = brew else {
        return Ok(InstallResult {
            success: false,
            message: "未检测到可信 Homebrew，已停止自动安装".to_string(),
            error: Some("请从 nodejs.org 下载签名安装包，或先自行安装 Homebrew".to_string()),
        });
    };

    match run_installer_command(brew, &["install", "node@22"]).and_then(|install_output| {
        run_installer_command(brew, &["link", "--overwrite", "node@22"])
            .map(|link_output| format!("{}\n{}", install_output, link_output))
    }) {
        Ok(output) => Ok(InstallResult {
            success: true,
            message: format!("Node.js 安装成功！{}", output),
            error: None,
        }),
        Err(e) => Ok(InstallResult {
            success: false,
            message: "Node.js 安装失败".to_string(),
            error: Some(e),
        }),
    }
}

/// Linux 安装 Node.js
async fn install_nodejs_linux() -> AppResult<InstallResult> {
    Ok(InstallResult {
        success: false,
        message: "Linux 自动安装已安全关闭".to_string(),
        error: Some(
            "请通过发行版签名仓库安装 Node.js 22；应用不会再下载远程脚本并交给 root shell"
                .to_string(),
        ),
    })
}

/// 安装 OpenClaw
#[command]
pub async fn install_openclaw() -> AppResult<InstallResult> {
    info!("[安装OpenClaw] 开始安装 OpenClaw...");
    let os = platform::get_os();
    info!("[安装OpenClaw] 检测到操作系统: {}", os);

    let result = match os.as_str() {
        "windows" => {
            info!("[安装OpenClaw] 使用 Windows 安装方式...");
            install_openclaw_windows().await
        }
        _ => {
            info!("[安装OpenClaw] 使用 Unix 安装方式 (npm)...");
            install_openclaw_unix().await
        }
    };

    match &result {
        Ok(r) if r.success => info!("[安装OpenClaw] ✓ 安装成功"),
        Ok(r) => warn!("[安装OpenClaw] ✗ 安装失败: {}", r.message),
        Err(e) => error!("[安装OpenClaw] ✗ 安装错误: {}", e),
    }

    result
}

/// Windows 安装 OpenClaw
async fn install_openclaw_windows() -> AppResult<InstallResult> {
    let node_version = get_node_version();
    if !check_node_version_requirement(&node_version) {
        return Ok(InstallResult {
            success: false,
            message: "OpenClaw 安装失败".to_string(),
            error: Some("请先安装 Node.js 22 或更高版本".to_string()),
        });
    }
    match install_locked_openclaw_runtime().await {
        Ok(version) => Ok(InstallResult {
            success: true,
            message: format!("OpenClaw {} 安装成功！", version),
            error: None,
        }),
        Err(e) => Ok(InstallResult {
            success: false,
            message: "OpenClaw 安装失败".to_string(),
            error: Some(e),
        }),
    }
}

/// Unix 系统安装 OpenClaw
async fn install_openclaw_unix() -> AppResult<InstallResult> {
    let node_version = get_node_version();
    if !check_node_version_requirement(&node_version) {
        return Ok(InstallResult {
            success: false,
            message: "OpenClaw 安装失败".to_string(),
            error: Some("请先安装 Node.js 22 或更高版本".to_string()),
        });
    }
    match install_locked_openclaw_runtime().await {
        Ok(version) => Ok(InstallResult {
            success: true,
            message: format!("OpenClaw {} 安装成功！", version),
            error: None,
        }),
        Err(e) => Ok(InstallResult {
            success: false,
            message: "OpenClaw 安装失败".to_string(),
            error: Some(e),
        }),
    }
}

/// 初始化 OpenClaw 配置
#[command]
pub async fn init_openclaw_config() -> AppResult<InstallResult> {
    info!("[初始化配置] 开始初始化 OpenClaw 配置...");

    let config_dir = platform::get_config_dir();
    info!("[初始化配置] 配置目录: {}", config_dir);

    // 创建配置目录
    info!("[初始化配置] 创建配置目录...");
    if let Err(e) = std::fs::create_dir_all(&config_dir) {
        error!("[初始化配置] ✗ 创建配置目录失败: {}", e);
        return Ok(InstallResult {
            success: false,
            message: "创建配置目录失败".to_string(),
            error: Some(e.to_string()),
        });
    }

    // 创建子目录
    let subdirs = ["agents/main/sessions", "agents/main/agent", "credentials"];
    for subdir in subdirs {
        let path = format!("{}/{}", config_dir, subdir);
        info!("[初始化配置] 创建子目录: {}", subdir);
        if let Err(e) = std::fs::create_dir_all(&path) {
            error!("[初始化配置] ✗ 创建目录失败: {} - {}", subdir, e);
            return Ok(InstallResult {
                success: false,
                message: format!("创建目录失败: {}", subdir),
                error: Some(e.to_string()),
            });
        }
    }

    // 设置配置目录权限为 700（与 shell 脚本 chmod 700 一致）
    // 仅在 Unix 系统上执行
    #[cfg(unix)]
    {
        info!("[初始化配置] 设置目录权限为 700...");
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = std::fs::metadata(&config_dir) {
            let mut perms = metadata.permissions();
            perms.set_mode(0o700);
            if let Err(e) = std::fs::set_permissions(&config_dir, perms) {
                warn!("[初始化配置] 设置权限失败: {}", e);
            } else {
                info!("[初始化配置] ✓ 权限设置成功");
            }
        }
    }

    // 设置 gateway mode 为 local
    info!("[初始化配置] 执行: openclaw config set gateway.mode local");
    let result = shell::run_openclaw(&["config", "set", "gateway.mode", "local"]);

    match result {
        Ok(output) => {
            info!("[初始化配置] ✓ 配置初始化成功");
            debug!("[初始化配置] 命令输出: {}", output);
            Ok(InstallResult {
                success: true,
                message: "配置初始化成功！".to_string(),
                error: None,
            })
        }
        Err(e) => {
            error!("[初始化配置] ✗ 配置初始化失败: {}", e);
            Ok(InstallResult {
                success: false,
                message: "配置初始化失败".to_string(),
                error: Some(e),
            })
        }
    }
}

/// 打开终端执行安装脚本（用于需要管理员权限的场景）
#[command]
pub async fn open_install_terminal(install_type: String) -> AppResult<String> {
    match install_type.as_str() {
        "nodejs" => open_nodejs_install_terminal().await,
        "openclaw" => open_openclaw_install_terminal().await,
        _ => Err(AppError::validation(format!(
            "未知的安装类型: {}",
            install_type
        ))),
    }
}

/// 打开终端安装 Node.js
async fn open_nodejs_install_terminal() -> AppResult<String> {
    if platform::is_windows() {
        // Windows: 打开 PowerShell 执行安装
        let script = r#"
Start-Process powershell -ArgumentList '-NoExit', '-Command', '
$ErrorActionPreference = "Stop"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    Node.js 安装向导" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 winget
$hasWinget = Get-Command winget -ErrorAction SilentlyContinue
if ($hasWinget) {
    Write-Host "正在使用 winget 安装 Node.js 22..." -ForegroundColor Yellow
    winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget 安装失败，退出码: $LASTEXITCODE" }
} else {
    Write-Host "请从以下地址下载安装 Node.js:" -ForegroundColor Yellow
    Write-Host "https://nodejs.org/en/download" -ForegroundColor Green
    Write-Host ""
    Start-Process "https://nodejs.org/en/download"
}

Write-Host ""
Write-Host \"安装完成后请重启 OpenClaw\" -ForegroundColor Green
Write-Host ""
Read-Host "按回车键关闭此窗口"
' -Verb RunAs
"#;
        shell::run_powershell_output(script)?;
        Ok("已打开安装终端".to_string())
    } else if platform::is_macos() {
        // macOS: 打开 Terminal.app
        let brew = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
            .into_iter()
            .find(|path| Path::new(path).is_file())
            .ok_or_else(|| {
                AppError::process(
                    "未检测到可信 Homebrew，请从 nodejs.org 下载 Node.js 22 签名安装包",
                )
            })?;
        let script_content = format!(
            r#"#!/bin/bash
set -euo pipefail
trap 'rm -f -- "$0"' EXIT
clear
echo "========================================"
echo "    Node.js 安装向导"
echo "========================================"
echo ""

echo "正在安装 Node.js 22..."
"{brew}" install node@22
"{brew}" link --overwrite node@22

echo ""
echo "安装完成！"
node --version
echo ""
read -p "按回车键关闭此窗口..."
"#
        );

        let script_path = create_private_install_script("command", &script_content)?;
        if let Err(error) = launch_script_with("open", &[], &script_path) {
            let _ = fs::remove_file(&script_path);
            return Err(error);
        }

        Ok("已打开安装终端".to_string())
    } else {
        Err(AppError::process("请手动安装 Node.js: https://nodejs.org/"))
    }
}

/// 打开终端安装 OpenClaw
async fn open_openclaw_install_terminal() -> AppResult<String> {
    let result = install_openclaw().await?;
    if !result.success {
        return Err(AppError::process(
            result.error.unwrap_or_else(|| result.message.clone()),
        ));
    }
    let initialized = init_openclaw_config().await?;
    if !initialized.success {
        return Err(AppError::process(
            initialized
                .error
                .unwrap_or_else(|| initialized.message.clone()),
        ));
    }
    Ok("OpenClaw 已通过应用完整性锁安装并完成初始化".to_string())
}

/// 版本更新信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateInfo {
    /// 是否有更新可用
    pub update_available: bool,
    /// 当前版本
    pub current_version: Option<String>,
    /// 最新版本
    pub latest_version: Option<String>,
    /// 错误信息
    pub error: Option<String>,
}

/// 检查 OpenClaw 更新
#[command]
pub async fn check_openclaw_update() -> AppResult<UpdateInfo> {
    info!("[版本检查] 开始检查 OpenClaw 更新...");

    // 获取当前版本
    let current_version = get_openclaw_version();
    info!("[版本检查] 当前版本: {:?}", current_version);

    if current_version.is_none() {
        info!("[版本检查] OpenClaw 未安装");
        return Ok(UpdateInfo {
            update_available: false,
            current_version: None,
            latest_version: None,
            error: Some("OpenClaw 未安装".to_string()),
        });
    }

    // 获取最新版本
    let latest_version = get_latest_openclaw_version();
    info!("[版本检查] 最新版本: {:?}", latest_version);

    if latest_version.is_none() {
        return Ok(UpdateInfo {
            update_available: false,
            current_version,
            latest_version: None,
            error: Some("无法获取最新版本信息".to_string()),
        });
    }

    // 比较版本（经过前面的 None 检查，此处理论上不会是 None，但用 unwrap_or_default 兜底）
    let current = current_version.clone().unwrap_or_default();
    let latest = latest_version.clone().unwrap_or_default();
    let update_available = compare_versions(&current, &latest);

    info!("[版本检查] 是否有更新: {}", update_available);

    Ok(UpdateInfo {
        update_available,
        current_version,
        latest_version,
        error: None,
    })
}

/// 获取 npm registry 上的最新版本
fn get_latest_openclaw_version() -> Option<String> {
    match bundled_openclaw_version() {
        Ok(version) => Some(version),
        Err(error) => {
            warn!("[版本检查] 读取内置目标版本失败: {}", error);
            None
        }
    }
}

/// 比较版本号，返回是否有更新可用
/// current: 当前版本 (如 "1.0.0" 或 "v1.0.0")
/// latest: 最新版本 (如 "1.0.1")
fn compare_versions(current: &str, latest: &str) -> bool {
    // 移除可能的 'v' 前缀和空白
    let current = current.trim().trim_start_matches('v');
    let latest = latest.trim().trim_start_matches('v');

    // 分割版本号
    let current_parts: Vec<u32> = current.split('.').filter_map(|s| s.parse().ok()).collect();
    let latest_parts: Vec<u32> = latest.split('.').filter_map(|s| s.parse().ok()).collect();

    // 比较每个部分
    for i in 0..3 {
        let c = current_parts.get(i).unwrap_or(&0);
        let l = latest_parts.get(i).unwrap_or(&0);
        if l > c {
            return true;
        } else if l < c {
            return false;
        }
    }

    false
}

#[cfg(test)]
mod supply_chain_policy_tests {
    use super::*;

    const SOURCE: &str = include_str!("installer.rs");

    #[test]
    fn installer_has_no_mutable_or_pipe_to_shell_sources() {
        let mutable_package = ["openclaw@", "latest"].concat();
        let homebrew_head = ["Homebrew/install/", "HEAD/install.sh"].concat();
        let nodesource_setup = ["nodesource.com/", "setup_22.x"].concat();
        let remote_powershell = ["fnm.vercel.app/", "install.ps1"].concat();

        for forbidden in [
            mutable_package.as_str(),
            homebrew_head.as_str(),
            nodesource_setup.as_str(),
            remote_powershell.as_str(),
        ] {
            assert!(
                !SOURCE.contains(forbidden),
                "安装器仍包含运行时可变供应链入口: {forbidden}"
            );
        }
    }

    #[test]
    fn terminal_scripts_do_not_use_predictable_tmp_names() {
        let predictable_prefix = ["/tmp/", "openclaw_install_"].concat();
        assert!(
            !SOURCE.contains(&predictable_prefix),
            "安装脚本不得写入可预测的共享临时路径"
        );
    }

    #[test]
    fn installer_command_scope_rejects_shell_interpreters() {
        assert!(run_installer_command("bash", &["-c", "id"]).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn temporary_scripts_are_unique_owner_only_and_complete() {
        use std::os::unix::fs::PermissionsExt;

        let first = create_private_install_script("sh", "#!/bin/bash\nexit 0\n").unwrap();
        let second = create_private_install_script("sh", "#!/bin/bash\nexit 0\n").unwrap();
        assert_ne!(first, second);
        assert_eq!(first.parent(), Some(std::env::temp_dir().as_path()));
        assert_eq!(fs::read_to_string(&first).unwrap(), "#!/bin/bash\nexit 0\n");
        assert_eq!(
            fs::metadata(&first).unwrap().permissions().mode() & 0o777,
            0o700
        );

        fs::remove_file(first).unwrap();
        fs::remove_file(second).unwrap();
    }
}

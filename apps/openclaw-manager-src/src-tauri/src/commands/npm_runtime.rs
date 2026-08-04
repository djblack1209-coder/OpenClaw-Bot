use crate::models::{AppError, AppResult};
use crate::utils::{platform, shell};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Mutex, OnceLock};

// 参考 Tauri 2.11.5 Command 安全边界：WebView 只触发注册命令，本机 npm 进程使用固定清单和最小环境。
const RUNTIME_PACKAGE_JSON: &str = include_str!("../../npm-runtime-lock/package.json");
const RUNTIME_PACKAGE_LOCK: &str = include_str!("../../npm-runtime-lock/package-lock.json");
const RUNTIME_DIR_NAME: &str = "manager-npm-runtime";
const READY_MARKER: &str = ".openclaw-runtime-lock";

#[derive(Debug, Clone, Copy)]
pub struct ManagedMcpPackage {
    pub id: &'static str,
    pub package_name: &'static str,
    pub binary_name: &'static str,
    pub display_name: &'static str,
    pub description: &'static str,
    pub author: &'static str,
    pub icon: &'static str,
    pub tags: &'static [&'static str],
}

/// MCP 包名、受管二进制和展示元数据的唯一类型化注册源。
pub const MANAGED_MCP_PACKAGES: &[ManagedMcpPackage] = &[
    ManagedMcpPackage {
        id: "playwright",
        package_name: "@playwright/mcp",
        binary_name: "playwright-mcp",
        display_name: "Playwright MCP",
        description: "浏览器自动化 MCP 运行包",
        author: "Microsoft",
        icon: "browser",
        tags: &["browser", "automation"],
    },
    ManagedMcpPackage {
        id: "superpowers",
        package_name: "superpowers-mcp",
        binary_name: "superpowers-mcp",
        display_name: "Superpowers MCP",
        description: "研发工作流与调试方法 MCP 运行包",
        author: "Superpowers",
        icon: "sparkles",
        tags: &["development", "workflow"],
    },
    ManagedMcpPackage {
        id: "computer-use",
        package_name: "open-computer-use",
        binary_name: "open-codex-computer-use-mcp",
        display_name: "Computer Use MCP",
        description: "受控电脑操作 MCP 运行包",
        author: "Open Computer Use",
        icon: "monitor",
        tags: &["computer", "automation"],
    },
    ManagedMcpPackage {
        id: "memory",
        package_name: "@modelcontextprotocol/server-memory",
        binary_name: "mcp-server-memory",
        display_name: "Memory MCP",
        description: "本地知识图谱记忆 MCP 运行包",
        author: "Model Context Protocol",
        icon: "database",
        tags: &["memory", "knowledge"],
    },
    ManagedMcpPackage {
        id: "github",
        package_name: "@modelcontextprotocol/server-github",
        binary_name: "mcp-server-github",
        display_name: "GitHub MCP",
        description: "GitHub 仓库协作 MCP 运行包",
        author: "Model Context Protocol",
        icon: "github",
        tags: &["code", "github"],
    },
    ManagedMcpPackage {
        id: "brave-search",
        package_name: "@modelcontextprotocol/server-brave-search",
        binary_name: "mcp-server-brave-search",
        display_name: "Brave Search MCP",
        description: "Brave 搜索 MCP 运行包",
        author: "Model Context Protocol",
        icon: "search",
        tags: &["search", "web"],
    },
    ManagedMcpPackage {
        id: "google-maps",
        package_name: "@modelcontextprotocol/server-google-maps",
        binary_name: "mcp-server-google-maps",
        display_name: "Google Maps MCP",
        description: "地图与地点检索 MCP 运行包",
        author: "Model Context Protocol",
        icon: "map",
        tags: &["maps", "location"],
    },
    ManagedMcpPackage {
        id: "sequential-thinking",
        package_name: "@modelcontextprotocol/server-sequential-thinking",
        binary_name: "mcp-server-sequential-thinking",
        display_name: "Sequential Thinking MCP",
        description: "结构化推理 MCP 运行包",
        author: "Model Context Protocol",
        icon: "brain",
        tags: &["reasoning", "planning"],
    },
];

static INSTALL_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

fn install_lock() -> &'static Mutex<()> {
    INSTALL_LOCK.get_or_init(|| Mutex::new(()))
}

pub fn managed_runtime_dir() -> PathBuf {
    PathBuf::from(platform::get_config_dir()).join(RUNTIME_DIR_NAME)
}

/// 从内嵌运行时清单读取唯一版本事实，并生成配置兼容的 npm 包规格。
pub fn locked_package_version(package_name: &str) -> AppResult<String> {
    let package: Value = serde_json::from_str(RUNTIME_PACKAGE_JSON)
        .map_err(|error| AppError::config(format!("解析内嵌 npm 运行时清单失败: {}", error)))?;
    let version = package
        .get("dependencies")
        .and_then(Value::as_object)
        .and_then(|dependencies| dependencies.get(package_name))
        .and_then(Value::as_str)
        .filter(|version| is_exact_npm_version(version))
        .ok_or_else(|| AppError::config(format!("受管 npm 包未登记精确版本: {}", package_name)))?;
    Ok(version.to_string())
}

/// 只接受三段数字版本和可选的字母数字预发布后缀。
fn is_exact_npm_version(value: &str) -> bool {
    let (core, prerelease) = value
        .split_once('-')
        .map_or((value, None), |(core, suffix)| (core, Some(suffix)));
    let core_parts: Vec<&str> = core.split('.').collect();
    if core_parts.len() != 3
        || core_parts.iter().any(|part| {
            part.is_empty() || !part.chars().all(|character| character.is_ascii_digit())
        })
    {
        return false;
    }
    prerelease.is_none_or(|suffix| {
        !suffix.is_empty()
            && suffix.split('.').all(|part| {
                !part.is_empty()
                    && part
                        .chars()
                        .all(|character| character.is_ascii_alphanumeric() || character == '-')
            })
    })
}

pub fn managed_bin_path(name: &str) -> AppResult<PathBuf> {
    if name != "openclaw"
        && !MANAGED_MCP_PACKAGES
            .iter()
            .any(|package| package.binary_name == name)
    {
        return Err(AppError::config(format!(
            "未登记的受管 npm 可执行文件: {}",
            name
        )));
    }
    let filename = if cfg!(windows) {
        format!("{}.cmd", name)
    } else {
        name.to_string()
    };
    Ok(managed_runtime_dir()
        .join("node_modules")
        .join(".bin")
        .join(filename))
}

fn runtime_is_ready(runtime_dir: &Path) -> bool {
    let package_matches = fs::read_to_string(runtime_dir.join("package.json"))
        .is_ok_and(|content| content == RUNTIME_PACKAGE_JSON);
    let lock_matches = fs::read_to_string(runtime_dir.join("package-lock.json"))
        .is_ok_and(|content| content == RUNTIME_PACKAGE_LOCK);
    let marker_matches = fs::read_to_string(runtime_dir.join(READY_MARKER))
        .is_ok_and(|content| content == RUNTIME_PACKAGE_LOCK);
    package_matches
        && lock_matches
        && marker_matches
        && std::iter::once("openclaw")
            .chain(
                MANAGED_MCP_PACKAGES
                    .iter()
                    .map(|package| package.binary_name),
            )
            .all(|name| managed_bin_path(name).is_ok_and(|path| path.is_file()))
}

fn write_runtime_file(runtime_dir: &Path, name: &str, content: &str) -> AppResult<()> {
    let temp_path = runtime_dir.join(format!(".{}.{}", name, std::process::id()));
    fs::write(&temp_path, content)
        .map_err(|error| AppError::io(format!("写入 npm 运行时临时文件失败: {}", error)))?;
    let final_path = runtime_dir.join(name);
    if final_path.exists() {
        fs::remove_file(&final_path)
            .map_err(|error| AppError::io(format!("替换 npm 运行时清单失败: {}", error)))?;
    }
    fs::rename(&temp_path, &final_path)
        .map_err(|error| AppError::io(format!("提交 npm 运行时清单失败: {}", error)))
}

fn apply_npm_environment(command: &mut Command) {
    const ENV_KEYS: &[&str] = &[
        "HOME",
        "USERPROFILE",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SystemRoot",
        "WINDIR",
        "ComSpec",
        "PATHEXT",
        "APPDATA",
        "LOCALAPPDATA",
    ];
    command.env_clear();
    for key in ENV_KEYS {
        if let Ok(value) = std::env::var(key) {
            command.env(key, value);
        }
    }
    command.env("PATH", shell::get_extended_path());
}

pub fn ensure_managed_runtime() -> AppResult<PathBuf> {
    let _guard = install_lock()
        .lock()
        .map_err(|error| AppError::process(format!("锁定 npm 运行时安装器失败: {}", error)))?;
    let runtime_dir = managed_runtime_dir();
    if runtime_is_ready(&runtime_dir) {
        return Ok(runtime_dir);
    }

    fs::create_dir_all(&runtime_dir)
        .map_err(|error| AppError::io(format!("创建 npm 运行时目录失败: {}", error)))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&runtime_dir, fs::Permissions::from_mode(0o700))
            .map_err(|error| AppError::io(format!("限制 npm 运行时目录权限失败: {}", error)))?;
    }

    let node_modules = runtime_dir.join("node_modules");
    if node_modules.exists() {
        fs::remove_dir_all(&node_modules)
            .map_err(|error| AppError::io(format!("清理未完成 npm 运行时失败: {}", error)))?;
    }
    let _ = fs::remove_file(runtime_dir.join(READY_MARKER));
    write_runtime_file(&runtime_dir, "package.json", RUNTIME_PACKAGE_JSON)?;
    write_runtime_file(&runtime_dir, "package-lock.json", RUNTIME_PACKAGE_LOCK)?;

    #[cfg(windows)]
    let mut command = {
        let mut command = Command::new("cmd");
        command.args(["/d", "/s", "/c", "npm"]);
        command
    };
    #[cfg(not(windows))]
    let mut command = Command::new("npm");

    command.current_dir(&runtime_dir).args([
        "ci",
        "--omit=dev",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    ]);
    apply_npm_environment(&mut command);
    let output = command
        .output()
        .map_err(|error| AppError::process(format!("启动 npm ci 失败: {}", error)))?;
    if !output.status.success() {
        let _ = fs::remove_dir_all(&node_modules);
        let detail = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::process(format!(
            "固定完整性 npm 运行时安装失败: {}",
            detail.trim()
        )));
    }

    for name in std::iter::once("openclaw").chain(
        MANAGED_MCP_PACKAGES
            .iter()
            .map(|package| package.binary_name),
    ) {
        let path = managed_bin_path(name)?;
        if !path.is_file() {
            let _ = fs::remove_dir_all(&node_modules);
            return Err(AppError::process(format!(
                "npm 锁安装完成但缺少受管入口: {}",
                name
            )));
        }
    }
    write_runtime_file(&runtime_dir, READY_MARKER, RUNTIME_PACKAGE_LOCK)?;
    Ok(runtime_dir)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_lock_pins_openclaw_and_every_direct_dependency() {
        let package: Value = serde_json::from_str(RUNTIME_PACKAGE_JSON).unwrap();
        let lock: Value = serde_json::from_str(RUNTIME_PACKAGE_LOCK).unwrap();
        let dependencies = package["dependencies"].as_object().unwrap();
        assert!(dependencies.contains_key("openclaw"));
        assert_eq!(dependencies.len(), MANAGED_MCP_PACKAGES.len() + 1);

        for managed in MANAGED_MCP_PACKAGES {
            assert!(dependencies.contains_key(managed.package_name));
            let bins = lock["packages"][format!("node_modules/{}", managed.package_name)]["bin"]
                .as_object()
                .unwrap();
            assert!(bins.contains_key(managed.binary_name));
        }

        for (name, version) in dependencies {
            let entry = &lock["packages"][format!("node_modules/{}", name)];
            assert_eq!(&entry["version"], version);
            assert!(entry["integrity"].as_str().unwrap().starts_with("sha512-"));
            assert!(entry["resolved"]
                .as_str()
                .unwrap()
                .starts_with("https://registry.npmjs.org/"));
        }
    }

    #[test]
    fn runtime_exposes_only_registered_binary_names() {
        assert!(managed_bin_path("openclaw").is_ok());
        assert!(managed_bin_path("node").is_err());
        assert!(managed_bin_path("../../bin/sh").is_err());
    }

    #[test]
    fn package_versions_derive_from_the_embedded_manifest() {
        let package: Value = serde_json::from_str(RUNTIME_PACKAGE_JSON).unwrap();
        let version = package["dependencies"]["@playwright/mcp"].as_str().unwrap();

        assert_eq!(locked_package_version("@playwright/mcp").unwrap(), version);
        assert!(locked_package_version("unregistered-package").is_err());
    }
}

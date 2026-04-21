use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, OnceLock};
use crate::utils::platform::get_config_dir;
use crate::utils::shell;
use crate::models::{AppResult, AppError};

/// 全局进程表：存储正在运行的 MCP 插件子进程
static RUNNING_PROCESSES: OnceLock<Mutex<HashMap<String, Child>>> = OnceLock::new();

/// 获取全局进程表的引用
fn get_process_map() -> &'static Mutex<HashMap<String, Child>> {
    RUNNING_PROCESSES.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct MCPPlugin {
    pub id: String,
    pub name: String,
    pub description: String,
    pub version: String,
    pub author: String,
    pub r#type: String, // "stdio" or "sse"
    pub status: String, // "running", "configured", "stopped", "error"
    pub icon: String,   // Not actually used in Rust side, but keep for type parity
    pub tags: Vec<String>,
    pub command: Option<String>,
    pub args: Option<Vec<String>>,
    pub env: Option<std::collections::HashMap<String, String>>,
}

// Ensure the MCP config file exists
fn get_mcp_config_path() -> PathBuf {
    let config_dir_str = get_config_dir();
    let mut config_dir = PathBuf::from(config_dir_str);
    config_dir.push("mcp_servers.json");
    config_dir
}

#[tauri::command]
pub async fn get_mcp_plugins() -> AppResult<Vec<MCPPlugin>> {
    let path = get_mcp_config_path();
    
    if !path.exists() {
        return Ok(Vec::new());
    }

    let content = fs::read_to_string(&path)
        .map_err(|e| AppError::io(format!("读取 MCP 配置失败: {}", e)))?;
        
    let plugins: Vec<MCPPlugin> = serde_json::from_str(&content)
        .map_err(|e| AppError::serialization(format!("解析 MCP 配置失败: {}", e)))?;
        
    Ok(plugins)
}

#[tauri::command]
pub async fn save_mcp_plugin(plugin: MCPPlugin) -> AppResult<()> {
    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();
    
    // Update if exists, or append
    if let Some(pos) = plugins.iter().position(|p| p.id == plugin.id) {
        plugins[pos] = plugin;
    } else {
        plugins.push(plugin);
    }
    
    let content = serde_json::to_string_pretty(&plugins)
        .map_err(|e| AppError::serialization(format!("序列化 MCP 配置失败: {}", e)))?;
        
    fs::write(&path, content)
        .map_err(|e| AppError::io(format!("写入 MCP 配置失败: {}", e)))?;
        
    Ok(())
}

/// 切换 MCP 插件状态 — 仅在 configured / stopped 之间切换
/// "running" 状态由 Gateway 实际连接后设置，前端 toggle 不会直接设为 running
#[tauri::command]
pub async fn toggle_mcp_plugin_status(id: String, target_status: String) -> AppResult<()> {
    // 校验目标状态值
    let valid_statuses = ["configured", "stopped", "running", "error"];
    if !valid_statuses.contains(&target_status.as_str()) {
        return Err(AppError::validation(format!("无效的目标状态: {}", target_status)));
    }

    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();
    
    if let Some(plugin) = plugins.iter_mut().find(|p| p.id == id) {
        plugin.status = target_status;
        
        let content = serde_json::to_string_pretty(&plugins)
            .map_err(|e| AppError::serialization(format!("序列化 MCP 配置失败: {}", e)))?;
            
        fs::write(&path, content)
            .map_err(|e| AppError::io(format!("写入 MCP 配置失败: {}", e)))?;
            
        Ok(())
    } else {
        Err(AppError::not_found(format!("插件 {} 不存在", id)))
    }
}

/// 删除 MCP 插件 — 从配置文件中移除指定 ID 的插件
#[tauri::command]
pub async fn remove_mcp_plugin(id: String) -> AppResult<()> {
    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();

    let original_len = plugins.len();
    plugins.retain(|p| p.id != id);

    if plugins.len() == original_len {
        return Err(AppError::not_found(format!("插件 {} 不存在", id)));
    }

    let content = serde_json::to_string_pretty(&plugins)
        .map_err(|e| AppError::serialization(format!("序列化 MCP 配置失败: {}", e)))?;

    fs::write(&path, content)
        .map_err(|e| AppError::io(format!("写入 MCP 配置失败: {}", e)))?;

    Ok(())
}

/// 启动 MCP 插件进程 — 读取配置、拉起子进程、记录到全局进程表
#[tauri::command]
pub async fn start_mcp_plugin(id: String) -> AppResult<()> {
    // 读取插件配置
    let plugins = get_mcp_plugins().await?;
    let plugin = plugins.iter().find(|p| p.id == id)
        .ok_or_else(|| AppError::not_found(format!("插件 {} 不存在", id)))?;

    // 校验启动命令是否已配置
    let cmd = plugin.command.as_ref()
        .ok_or_else(|| AppError::config(format!("插件 {} 未配置启动命令，请先在「配置」中设置", id)))?;
    if cmd.is_empty() {
        return Err(AppError::config(format!("插件 {} 的启动命令为空，请先配置", id)));
    }

    // 如果已有旧进程在运行，先终止它
    {
        let mut map = get_process_map().lock()
            .map_err(|e| AppError::process(format!("锁定进程表失败: {}", e)))?;
        if let Some(mut old_child) = map.remove(&id) {
            let _ = old_child.kill();
            let _ = old_child.wait();
        }
    }

    // 安全加固: 校验启动命令是否在白名单中，防止命令注入
    shell::validate_command(cmd)
        .map_err(|_| AppError::config(format!("不允许执行该命令：{}", cmd)))?;

    // 构建子进程命令
    let mut command = Command::new(cmd);
    if let Some(args) = &plugin.args {
        command.args(args);
    }
    if let Some(env) = &plugin.env {
        command.envs(env);
    }

    // 子进程 IO 策略：stdin 关闭，stdout/stderr 丢弃（Tier 1 不做日志收集）
    command.stdin(Stdio::null())
           .stdout(Stdio::null())
           .stderr(Stdio::null());

    // 启动子进程
    let child = command.spawn()
        .map_err(|e| AppError::process(format!("启动插件 {} 失败: {}（命令: {} {}）",
            id, e, cmd, plugin.args.as_ref().map_or(String::new(), |a| a.join(" ")))))?;

    log::info!("MCP 插件 {} 已启动，PID: {}", id, child.id());

    // 存入全局进程表
    {
        let mut map = get_process_map().lock()
            .map_err(|e| AppError::process(format!("锁定进程表失败: {}", e)))?;
        map.insert(id.clone(), child);
    }

    // 更新配置文件中的状态为 running
    toggle_mcp_plugin_status(id, "running".to_string()).await?;

    Ok(())
}

/// 停止 MCP 插件进程 — 终止子进程并更新状态
#[tauri::command]
pub async fn stop_mcp_plugin(id: String) -> AppResult<()> {
    // 尝试从进程表中取出子进程
    let child = {
        let mut map = get_process_map().lock()
            .map_err(|e| AppError::process(format!("锁定进程表失败: {}", e)))?;
        map.remove(&id)
    };

    // 如果有进程在运行，终止它
    if let Some(mut child) = child {
        let pid = child.id();
        child.kill().map_err(|e| AppError::process(format!("终止插件 {} 进程(PID {})失败: {}", id, pid, e)))?;
        // 等待进程退出，回收系统资源
        let _ = child.wait();
        log::info!("MCP 插件 {} 已停止，PID: {}", id, pid);
    }

    // 无论是否有进程，都更新配置状态为 stopped
    toggle_mcp_plugin_status(id, "stopped".to_string()).await?;

    Ok(())
}

/// 查询 MCP 插件进程是否存活
#[tauri::command]
pub async fn get_mcp_plugin_status(id: String) -> AppResult<String> {
    let mut map = get_process_map().lock()
        .map_err(|e| AppError::process(format!("锁定进程表失败: {}", e)))?;

    if let Some(child) = map.get_mut(&id) {
        match child.try_wait() {
            Ok(Some(_exit_status)) => {
                // 进程已自行退出，从表中移除
                map.remove(&id);
                Ok("stopped".to_string())
            }
            Ok(None) => {
                // 进程仍在运行
                Ok("running".to_string())
            }
            Err(e) => {
                // 无法检查进程状态，视为已停止
                map.remove(&id);
                Err(AppError::process(format!("检查插件 {} 进程状态失败: {}", id, e)))
            }
        }
    } else {
        // 进程表中无记录，视为未运行
        Ok("stopped".to_string())
    }
}

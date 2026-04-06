use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use crate::utils::platform::get_config_dir;

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
pub async fn get_mcp_plugins() -> Result<Vec<MCPPlugin>, String> {
    let path = get_mcp_config_path();
    
    if !path.exists() {
        return Ok(Vec::new());
    }

    let content = fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read MCP config: {}", e))?;
        
    let plugins: Vec<MCPPlugin> = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse MCP config: {}", e))?;
        
    Ok(plugins)
}

#[tauri::command]
pub async fn save_mcp_plugin(plugin: MCPPlugin) -> Result<(), String> {
    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();
    
    // Update if exists, or append
    if let Some(pos) = plugins.iter().position(|p| p.id == plugin.id) {
        plugins[pos] = plugin;
    } else {
        plugins.push(plugin);
    }
    
    let content = serde_json::to_string_pretty(&plugins)
        .map_err(|e| format!("Failed to serialize MCP plugins: {}", e))?;
        
    fs::write(&path, content)
        .map_err(|e| format!("Failed to write MCP config: {}", e))?;
        
    Ok(())
}

/// 切换 MCP 插件状态 — 仅在 configured / stopped 之间切换
/// "running" 状态由 Gateway 实际连接后设置，前端 toggle 不会直接设为 running
#[tauri::command]
pub async fn toggle_mcp_plugin_status(id: String, target_status: String) -> Result<(), String> {
    // 校验目标状态值
    let valid_statuses = ["configured", "stopped", "running", "error"];
    if !valid_statuses.contains(&target_status.as_str()) {
        return Err(format!("Invalid target status: {}", target_status));
    }

    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();
    
    if let Some(plugin) = plugins.iter_mut().find(|p| p.id == id) {
        plugin.status = target_status;
        
        let content = serde_json::to_string_pretty(&plugins)
            .map_err(|e| format!("Failed to serialize MCP plugins: {}", e))?;
            
        fs::write(&path, content)
            .map_err(|e| format!("Failed to write MCP config: {}", e))?;
            
        Ok(())
    } else {
        Err(format!("Plugin {} not found", id))
    }
}

/// 删除 MCP 插件 — 从配置文件中移除指定 ID 的插件
#[tauri::command]
pub async fn remove_mcp_plugin(id: String) -> Result<(), String> {
    let path = get_mcp_config_path();
    let mut plugins = get_mcp_plugins().await.unwrap_or_default();

    let original_len = plugins.len();
    plugins.retain(|p| p.id != id);

    if plugins.len() == original_len {
        return Err(format!("Plugin {} not found", id));
    }

    let content = serde_json::to_string_pretty(&plugins)
        .map_err(|e| format!("Failed to serialize MCP plugins: {}", e))?;

    fs::write(&path, content)
        .map_err(|e| format!("Failed to write MCP config: {}", e))?;

    Ok(())
}

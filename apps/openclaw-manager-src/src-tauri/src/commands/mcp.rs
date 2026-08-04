use crate::commands::npm_runtime::{locked_package_version, MANAGED_MCP_PACKAGES};
use crate::models::AppResult;
use serde::Serialize;

#[derive(Debug, Serialize, Clone)]
pub struct MCPPluginView {
    pub id: String,
    pub name: String,
    pub description: String,
    pub version: String,
    pub author: String,
    pub r#type: String,
    pub status: String,
    pub icon: String,
    pub tags: Vec<String>,
}

/// 从受管 npm 注册表构建只读目录；版本、二进制和展示信息不再依赖用户配置文件。
fn build_mcp_catalog() -> AppResult<Vec<MCPPluginView>> {
    MANAGED_MCP_PACKAGES
        .iter()
        .map(|package| {
            Ok(MCPPluginView {
                id: package.id.to_string(),
                name: package.display_name.to_string(),
                description: package.description.to_string(),
                version: locked_package_version(package.package_name)?,
                author: package.author.to_string(),
                r#type: "stdio".to_string(),
                status: "managed".to_string(),
                icon: package.icon.to_string(),
                tags: package.tags.iter().map(|tag| (*tag).to_string()).collect(),
            })
        })
        .collect()
}

/// Store 只展示已锁定的 MCP 运行包；桌面端不伪装成 MCP 客户端，也不直接拉起 stdio 服务。
#[tauri::command]
pub async fn get_mcp_plugins() -> AppResult<Vec<MCPPluginView>> {
    build_mcp_catalog()
}

#[cfg(test)]
mod catalog_tests {
    use super::*;

    const MAIN_SOURCE: &str = include_str!("../main.rs");
    const MCP_SOURCE: &str = include_str!("mcp.rs");

    #[test]
    fn fresh_install_catalog_contains_every_managed_package() {
        let catalog = build_mcp_catalog().unwrap();

        assert_eq!(catalog.len(), MANAGED_MCP_PACKAGES.len());
        assert!(catalog.iter().all(|plugin| plugin.status == "managed"));
        for package in MANAGED_MCP_PACKAGES {
            let plugin = catalog
                .iter()
                .find(|plugin| plugin.id == package.id)
                .unwrap();
            assert_eq!(
                plugin.version,
                locked_package_version(package.package_name).unwrap()
            );
        }
    }

    #[test]
    fn catalog_never_serializes_commands_or_credentials() {
        let serialized = serde_json::to_string(&build_mcp_catalog().unwrap()).unwrap();

        assert!(!serialized.contains("command"));
        assert!(!serialized.contains("args"));
        assert!(!serialized.contains("env"));
        assert!(!serialized.contains("token"));
        assert!(!serialized.contains("secret"));
    }

    #[test]
    fn webview_exposes_catalog_only_without_fake_stdio_lifecycle() {
        assert!(MAIN_SOURCE.contains("mcp::get_mcp_plugins"));
        for forbidden in [
            "mcp::start_mcp_plugin",
            "mcp::stop_mcp_plugin",
            "mcp::get_mcp_plugin_status",
        ] {
            assert!(!MAIN_SOURCE.contains(forbidden));
        }
        assert!(MCP_SOURCE.contains("MANAGED_MCP_PACKAGES"));
    }
}

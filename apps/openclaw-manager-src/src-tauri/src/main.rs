// 防止 Windows 系统显示控制台窗口
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod commands;
mod models;
mod utils;

use commands::{clawbot, clawbot_api, config, diagnostics, installer, process, service, mcp};

fn main() {
    // 初始化日志 - 默认显示 info 级别日志
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info")
    ).init();
    
    log::info!("🦞 OpenClaw 启动");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            // 服务管理
            service::get_service_status,
            service::start_service,
            service::stop_service,
            service::restart_service,
            service::get_logs,
            // 总控中心（OpenClaw + ClawBot）
            clawbot::get_managed_services_status,
            clawbot::control_managed_service,
            clawbot::control_all_managed_services,
            clawbot::get_clawbot_runtime_config,
            clawbot::get_clawbot_bot_matrix,
            clawbot::get_openclaw_usage_snapshot,
            clawbot::save_clawbot_runtime_config,
            clawbot::get_managed_service_logs,
            clawbot::get_managed_endpoints_status,
            clawbot::get_skills_status,
            // 进程管理
            process::check_openclaw_installed,
            process::get_openclaw_version,
            process::check_port_in_use,
            // 配置管理
            config::get_config,
            config::save_config,
            config::get_env_value,
            config::save_env_value,
            config::get_ai_providers,
            config::get_channels_config,
            config::save_channel_config,
            config::clear_channel_config,
            // Gateway Token
            config::get_or_create_gateway_token,
            config::get_dashboard_url,
            config::get_project_context,
            config::get_app_settings,
            config::save_app_settings,
            config::open_macos_full_disk_access_settings,
            // AI 配置管理
            config::get_official_providers,
            config::get_ai_config,
            config::save_provider,
            config::delete_provider,
            config::set_primary_model,
            config::add_available_model,
            config::remove_available_model,
            // 飞书插件管理
            config::check_feishu_plugin,
            config::install_feishu_plugin,
            // 诊断测试
            diagnostics::run_doctor,
            diagnostics::test_ai_connection,
            diagnostics::test_channel,
            diagnostics::get_system_info,
            diagnostics::start_channel_login,
            // 安装器
            installer::check_environment,
            installer::install_nodejs,
            installer::install_openclaw,
            installer::init_openclaw_config,
            installer::open_install_terminal,
            installer::uninstall_openclaw,
            // 版本更新
            installer::check_openclaw_update,
            installer::update_openclaw,
            // MCP Plugins
            mcp::get_mcp_plugins,
            mcp::save_mcp_plugin,
            mcp::toggle_mcp_plugin_status,
            // ClawBot Internal API (FastAPI :18790)
            clawbot_api::clawbot_api_ping,
            clawbot_api::clawbot_api_status,
            clawbot_api::clawbot_api_trading_positions,
            clawbot_api::clawbot_api_trading_pnl,
            clawbot_api::clawbot_api_trading_signals,
            clawbot_api::clawbot_api_trading_system,
            clawbot_api::clawbot_api_trading_vote,
            clawbot_api::clawbot_api_social_status,
            clawbot_api::clawbot_api_social_topics,
            clawbot_api::clawbot_api_social_compose,
            clawbot_api::clawbot_api_social_publish,
            clawbot_api::clawbot_api_social_research,
            clawbot_api::clawbot_api_social_metrics,
            clawbot_api::clawbot_api_social_personas,
            clawbot_api::clawbot_api_social_calendar,
            // Social Autopilot
            clawbot_api::clawbot_api_autopilot_status,
            clawbot_api::clawbot_api_autopilot_start,
            clawbot_api::clawbot_api_autopilot_stop,
            clawbot_api::clawbot_api_autopilot_trigger,
            // Social Drafts
            clawbot_api::clawbot_api_social_drafts,
            clawbot_api::clawbot_api_social_draft_update,
            clawbot_api::clawbot_api_social_draft_delete,
            clawbot_api::clawbot_api_social_draft_publish,
            // Image Generation
            clawbot_api::clawbot_api_generate_image,
            clawbot_api::clawbot_api_generate_persona_photo,
            clawbot_api::clawbot_api_memory_search,
            clawbot_api::clawbot_api_memory_stats,
            clawbot_api::clawbot_api_pool_stats,
            // Evolution Engine
            clawbot_api::clawbot_api_evolution_scan,
            clawbot_api::clawbot_api_evolution_proposals,
            clawbot_api::clawbot_api_evolution_gaps,
            clawbot_api::clawbot_api_evolution_stats,
            clawbot_api::clawbot_api_evolution_update_proposal,
            // Shopping (比价引擎)
            clawbot_api::clawbot_api_shopping_compare,
            // OMEGA v2.0
            clawbot_api::clawbot_api_omega_status,
            clawbot_api::clawbot_api_omega_cost,
            clawbot_api::clawbot_api_omega_events,
            clawbot_api::clawbot_api_omega_audit,
            clawbot_api::clawbot_api_omega_tasks,
            clawbot_api::clawbot_api_omega_process,
            clawbot_api::clawbot_api_omega_investment_team,
            clawbot_api::clawbot_api_omega_investment_analyze,
            clawbot_api::clawbot_api_omega_generate_image,
            clawbot_api::clawbot_api_omega_generate_video,
            clawbot_api::clawbot_api_omega_media_models,
        ])
        .run(tauri::generate_context!())
        .expect("运行 Tauri 应用时发生错误");
}

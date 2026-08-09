//! ClawBot Internal API client
//! Calls the FastAPI server running at localhost:18790
//! Pattern: thin wrappers that proxy HTTP calls to the Python backend

use crate::models::{AppError, AppResult};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::LazyLock;
use tauri::command;

const CLAWBOT_API_BASE: &str = "http://127.0.0.1:18790/api/v1";
const XIANYU_ADMIN_DEFAULT_URL: &str = "http://127.0.0.1:18800";
const XIANYU_SELLER_LAUNCHER: &str = "cc_zhongzhuan_launch_seller_chrome.mjs";
const XIANYU_MANAGED_SERVICE_LABEL: &str = "ai.openclaw.xianyu";

/// 全局复用的 HTTP 客户端，避免每次请求都新建 TCP 连接
/// 超时设为 120 秒以支持 AI 类长时间操作（投资分析会、图片生成等）
static CLIENT: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .pool_max_idle_per_host(5)
        .build()
        .unwrap_or_else(|_| reqwest::Client::new())
});

/// 读取 API Token：优先从环境变量 OPENCLAW_API_TOKEN 获取，
/// 如果未设置则从 ClawBot .env 文件中读取（解决 Tauri 进程未继承环境变量的问题）
fn get_api_token() -> Option<String> {
    // 优先检查环境变量
    if let Ok(token) = std::env::var("OPENCLAW_API_TOKEN") {
        if !token.is_empty() {
            return Some(token);
        }
    }
    // 降级：从 .env 文件中读取（自动探测项目路径，不硬编码）
    let home = std::env::var("HOME").ok()?;
    // 尝试多个可能的 .env 位置
    let candidates = [
        // 通过 Cargo manifest 目录推断项目根
        format!(
            "{}/../../../packages/clawbot/config/.env",
            env!("CARGO_MANIFEST_DIR")
        ),
        // 常见路径
        format!(
            "{}/Desktop/OpenEverything/packages/clawbot/config/.env",
            home
        ),
        format!("{}/.openclaw/config/.env", home),
    ];
    for env_path in &candidates {
        if let Ok(content) = std::fs::read_to_string(env_path) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.starts_with("OPENCLAW_API_TOKEN=") {
                    if let Some(value) = trimmed.strip_prefix("OPENCLAW_API_TOKEN=") {
                        let value = value.trim();
                        if !value.is_empty() {
                            return Some(value.to_string());
                        }
                    }
                }
            }
        }
    }
    None
}

/// 辅助函数：向 ClawBot API 发送 GET 请求
async fn api_get(path: &str) -> AppResult<Value> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);

    let mut req = CLIENT.get(&url);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| AppError::network(format!("ClawBot API unreachable ({}): {}", url, e)))?;

    if !resp.status().is_success() {
        return Err(AppError::network(format!(
            "ClawBot API error: HTTP {}",
            resp.status()
        )));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| AppError::serialization(format!("JSON parse error: {}", e)))
}

/// 辅助函数：向 ClawBot API 发送 POST 请求
async fn api_post(path: &str, body: Value) -> AppResult<Value> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);

    let mut req = CLIENT.post(&url).json(&body);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| AppError::network(format!("ClawBot API unreachable ({}): {}", url, e)))?;

    if !resp.status().is_success() {
        return Err(AppError::network(format!(
            "ClawBot API error: HTTP {}",
            resp.status()
        )));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| AppError::serialization(format!("JSON parse error: {}", e)))
}

/// 辅助函数：向 ClawBot API 发送 PATCH 请求
async fn api_patch(path: &str, body: Value) -> AppResult<Value> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);

    let mut req = CLIENT.patch(&url).json(&body);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| AppError::network(format!("ClawBot API unreachable ({}): {}", url, e)))?;

    if !resp.status().is_success() {
        return Err(AppError::network(format!(
            "ClawBot API error: HTTP {}",
            resp.status()
        )));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| AppError::serialization(format!("JSON parse error: {}", e)))
}

// ──── System ────

#[command]
pub async fn clawbot_api_ping() -> AppResult<Value> {
    api_get("/ping").await
}

#[command]
pub async fn clawbot_api_status() -> AppResult<Value> {
    api_get("/status").await
}

/// 将可选的闲鱼运营台基地址收敛为本机回环启动端点。
/// 必须在读取 API Token 前调用，避免将本机凭据发送给任意配置地址。
fn xianyu_admin_launch_endpoint(base: &str) -> AppResult<reqwest::Url> {
    let mut parsed = reqwest::Url::parse(base.trim())
        .map_err(|_| AppError::config("XIANYU_ADMIN_URL 必须是本机 HTTP 地址"))?;
    let loopback = matches!(
        parsed.host_str(),
        Some("127.0.0.1" | "localhost" | "::1" | "[::1]")
    );
    let has_credentials = !parsed.username().is_empty() || parsed.password().is_some();
    if parsed.scheme() != "http"
        || !loopback
        || has_credentials
        || parsed.path() != "/"
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err(AppError::config(
            "XIANYU_ADMIN_URL 必须是不含路径或凭据的本机回环 HTTP 地址",
        ));
    }

    parsed.set_path("/api/session/desktop-launch");
    Ok(parsed)
}

/// 为桌面端打开闲鱼本机运营台；服务端只返回一次性短时启动地址。
/// API Token 仅放在本次本机请求的请求头中，不会进入 URL、响应或日志。
#[command]
pub async fn clawbot_api_xianyu_operator_url() -> AppResult<String> {
    let base =
        std::env::var("XIANYU_ADMIN_URL").unwrap_or_else(|_| XIANYU_ADMIN_DEFAULT_URL.to_string());
    let endpoint = xianyu_admin_launch_endpoint(&base)?;
    let token = get_api_token()
        .ok_or_else(|| AppError::config("未找到 OPENCLAW_API_TOKEN，无法打开闲鱼运营台"))?;
    let response = CLIENT
        .post(endpoint)
        .header("X-API-Token", token)
        .send()
        .await
        .map_err(|e| AppError::network(format!("闲鱼本机运营台不可用: {}", e)))?;
    if !response.status().is_success() {
        return Err(AppError::network(format!(
            "闲鱼本机运营台拒绝启动: HTTP {}",
            response.status()
        )));
    }
    let payload = response
        .json::<Value>()
        .await
        .map_err(|e| AppError::serialization(format!("闲鱼启动响应格式无效: {}", e)))?;
    let launch_url = payload
        .get("url")
        .and_then(Value::as_str)
        .ok_or_else(|| AppError::serialization("闲鱼启动响应缺少地址".to_string()))?;
    let parsed = reqwest::Url::parse(launch_url)
        .map_err(|_| AppError::serialization("闲鱼启动地址格式无效".to_string()))?;
    let loopback = matches!(parsed.host_str(), Some("127.0.0.1" | "localhost" | "::1"));
    if parsed.scheme() != "http" || !loopback || !parsed.path().starts_with("/launch/") {
        return Err(AppError::validation(
            "闲鱼启动地址不是受信任的本机一次性地址",
        ));
    }
    Ok(launch_url.to_string())
}

/// 只接受项目内已知的闲鱼启动器；打包 App 找不到仓库时必须失败关闭。
fn locate_xianyu_seller_launcher() -> AppResult<(PathBuf, PathBuf)> {
    let mut roots = Vec::new();
    for key in ["CC_XIANYU_PROJECT_ROOT", "OPENCLAW_PROJECT_ROOT"] {
        if let Ok(root) = std::env::var(key) {
            if !root.trim().is_empty() {
                roots.push(PathBuf::from(root));
            }
        }
    }
    if let Some(home) = dirs::home_dir() {
        roots.push(home.join("Desktop/OpenEverything"));
    }
    if let Ok(executable) = std::env::current_exe() {
        roots.extend(executable.ancestors().take(8).map(Path::to_path_buf));
    }
    roots.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for root in roots {
        let mut cursor = Some(root);
        for _ in 0..8 {
            let Some(candidate_root) = cursor else { break };
            let script = candidate_root.join("scripts").join(XIANYU_SELLER_LAUNCHER);
            if script.is_file() {
                let script = script
                    .canonicalize()
                    .map_err(|_| AppError::config("闲鱼启动器路径不可用"))?;
                return Ok((script, candidate_root));
            }
            cursor = candidate_root.parent().map(Path::to_path_buf);
        }
    }
    Err(AppError::config(
        "未找到闲鱼本机启动器，请先安装 OpenClaw 项目运行文件",
    ))
}

fn locate_node_binary() -> AppResult<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(explicit) = std::env::var("CC_XIANYU_NODE_BIN") {
        if !explicit.trim().is_empty() {
            candidates.push(PathBuf::from(explicit));
        }
    }
    let node_name = if cfg!(target_os = "windows") {
        "node.exe"
    } else {
        "node"
    };
    let search_path = if cfg!(target_os = "windows") {
        std::env::var_os("PATH").unwrap_or_default()
    } else {
        std::ffi::OsString::from(crate::utils::shell::get_extended_path())
    };
    candidates.extend(std::env::split_paths(&search_path).map(|entry| entry.join(node_name)));
    candidates
        .into_iter()
        .find(|candidate| {
            candidate.is_file()
                && candidate
                    .file_name()
                    .and_then(|name| name.to_str())
                    .map(|name| name == "node" || name == "node.exe")
                    .unwrap_or(false)
        })
        .ok_or_else(|| AppError::config("未找到 Node.js，无法启动闲鱼卖家浏览器"))
}

fn launch_xianyu_seller_chrome() -> AppResult<()> {
    let (script, project_root) = locate_xianyu_seller_launcher()?;
    let node = locate_node_binary()?;
    let mut command = Command::new(node);
    command
        .arg(&script)
        .arg("--json")
        .current_dir(project_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(not(target_os = "windows"))]
    command.env("PATH", crate::utils::shell::get_extended_path());
    let status = command
        .status()
        .map_err(|_| AppError::network("闲鱼卖家浏览器启动失败"))?;
    if !status.success() {
        return Err(AppError::network("闲鱼卖家浏览器启动器拒绝执行"));
    }
    Ok(())
}

/// 一次点击启动隔离卖家浏览器，再打开已有的一次性本机运营台链接。
#[command]
pub async fn clawbot_api_xianyu_open_operator() -> AppResult<String> {
    // 复用 Tauri 托管服务控制器；其 start 操作本身幂等，已运行时不会重启服务。
    super::clawbot::control_managed_service(
        XIANYU_MANAGED_SERVICE_LABEL.to_string(),
        "start".to_string(),
    )
    .await?;
    tokio::task::spawn_blocking(launch_xianyu_seller_chrome)
        .await
        .map_err(|_| AppError::network("闲鱼卖家浏览器启动任务失败"))??;
    clawbot_api_xianyu_operator_url().await
}

// ──── Trading ────

/// 获取交易仪表盘数据（连接状态、图表数据、资产列表）
/// 使用专用的 /trading/dashboard 接口，返回 chart_data + assets + connected
#[command]
pub async fn clawbot_api_trading_status() -> AppResult<Value> {
    api_get("/trading/dashboard").await
}

/// 当前持仓列表
#[command]
pub async fn clawbot_api_trading_positions() -> AppResult<Value> {
    api_get("/trading/positions").await
}

#[command]
pub async fn clawbot_api_trading_pnl() -> AppResult<Value> {
    api_get("/trading/pnl").await
}

#[command]
pub async fn clawbot_api_trading_signals() -> AppResult<Value> {
    api_get("/trading/signals").await
}

#[command]
pub async fn clawbot_api_trading_system() -> AppResult<Value> {
    api_get("/trading/system").await
}

#[command]
pub async fn clawbot_api_trading_vote(symbol: String, period: String) -> AppResult<Value> {
    api_post(
        "/trading/vote",
        serde_json::json!({
            "symbol": symbol,
            "period": period,
        }),
    )
    .await
}

// ──── Social ────

/// 获取社媒浏览器会话状态（X / 小红书）
#[command]
pub async fn clawbot_api_social_browser_status() -> AppResult<Value> {
    api_get("/social/browser-status").await
}

/// 安全控制社媒专用浏览器（打开/登录/状态刷新，不允许发布/回复/删除）
#[command]
pub async fn clawbot_api_social_browser_control(
    action: String,
    platform: Option<String>,
) -> AppResult<Value> {
    let platform = platform.unwrap_or_else(|| "all".to_string());
    api_post(
        &format!(
            "/social/browser-control?action={}&platform={}",
            urlencoding_encode(&action),
            urlencoding_encode(&platform),
        ),
        serde_json::json!({}),
    )
    .await
}

/// 获取统一浏览器运营工作台（X / 小红书 / 闲鱼）
#[command]
pub async fn clawbot_api_social_ops_workspace() -> AppResult<Value> {
    api_get("/social/ops-workspace").await
}

/// 获取社媒热点抽象号人设提案与确认状态
#[command]
pub async fn clawbot_api_social_persona_review() -> AppResult<Value> {
    api_get("/social/persona-review").await
}

/// 确认或打回社媒热点抽象号人设；不会触发发布
#[command]
pub async fn clawbot_api_social_persona_review_update(
    approved: bool,
    reviewer: Option<String>,
    notes: Option<String>,
) -> AppResult<Value> {
    let reviewer = reviewer.unwrap_or_else(|| "owner".to_string());
    let notes = notes.unwrap_or_default();
    api_post(
        &format!(
            "/social/persona-review?approved={}&reviewer={}&notes={}",
            approved,
            urlencoding_encode(&reviewer),
            urlencoding_encode(&notes),
        ),
        serde_json::json!({}),
    )
    .await
}

/// 获取待确认的人设 + X/小红书样稿包；只读，不会触发发布
#[command]
pub async fn clawbot_api_social_review_pack(limit: Option<u32>) -> AppResult<Value> {
    let limit = limit.unwrap_or(8).clamp(1, 12);
    api_get(&format!("/social/review-pack?limit={}", limit)).await
}

/// 从 App 中控更新 Chrome 插件 no-code 运营打法；只改设置摘要，不触发发布/评论
#[command]
pub async fn clawbot_api_social_strategy_update(
    strategy_preset: String,
    platform: Option<String>,
) -> AppResult<Value> {
    let platform = platform.unwrap_or_else(|| "x".to_string());
    api_post(
        "/social/extension/strategy",
        serde_json::json!({
            "strategyPreset": strategy_preset,
            "platform": platform,
            "auto_publish_enabled": false,
            "external_actions_locked": true,
        }),
    )
    .await
}

/// 获取 Chrome 插件增长复盘摘要；只读，不触发发布/评论/推广
#[command]
pub async fn clawbot_api_social_growth_feedback(
    platform: Option<String>,
    limit: Option<u32>,
) -> AppResult<Value> {
    let platform = platform.unwrap_or_else(|| "x".to_string());
    let limit = limit.unwrap_or(6).clamp(1, 12);
    api_get(&format!(
        "/social/extension/growth-feedback?platform={}&limit={}",
        urlencoding_encode(&platform),
        limit,
    ))
    .await
}

/// 基于增长复盘生成下一批待审草稿；只进审核队列，不触发发布/评论
#[command]
pub async fn clawbot_api_social_growth_drafts(
    platform: Option<String>,
    limit: Option<u32>,
) -> AppResult<Value> {
    let platform = platform.unwrap_or_else(|| "x".to_string());
    let limit = limit.unwrap_or(3).clamp(1, 6);
    api_post(
        "/social/extension/growth-drafts",
        serde_json::json!({
            "platform": platform,
            "limit": limit,
            "auto_publish_enabled": false,
            "external_actions_locked": true,
        }),
    )
    .await
}

/// 社媒系统运行状态
#[command]
pub async fn clawbot_api_social_status() -> AppResult<Value> {
    api_get("/social/status").await
}

#[command]
pub async fn clawbot_api_social_topics(count: Option<u32>) -> AppResult<Value> {
    let c = count.unwrap_or(10);
    api_get(&format!("/social/topics?count={}", c)).await
}

#[command]
pub async fn clawbot_api_social_compose(
    topic: String,
    platform: Option<String>,
    persona: Option<String>,
) -> AppResult<Value> {
    let p = platform.unwrap_or_else(|| "x".to_string());
    let per = persona.unwrap_or_else(|| "default".to_string());
    api_post(
        &format!(
            "/social/compose?topic={}&platform={}&persona={}",
            urlencoding_encode(&topic),
            urlencoding_encode(&p),
            urlencoding_encode(&per),
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_publish(platform: String, content: String) -> AppResult<Value> {
    api_post(
        "/social/publish",
        serde_json::json!({
            "platform": platform,
            "content": content,
        }),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_research(topic: String, count: Option<u32>) -> AppResult<Value> {
    let c = count.unwrap_or(10);
    api_post(
        &format!(
            "/social/research?topic={}&count={}",
            urlencoding_encode(&topic),
            c
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_metrics() -> AppResult<Value> {
    api_get("/social/metrics").await
}

#[command]
pub async fn clawbot_api_social_personas() -> AppResult<Value> {
    api_get("/social/personas").await
}

#[command]
pub async fn clawbot_api_social_calendar(days: Option<u32>) -> AppResult<Value> {
    api_get(&format!("/social/calendar?days={}", days.unwrap_or(7))).await
}

// ──── Social Autopilot ────

#[command]
pub async fn clawbot_api_autopilot_status() -> AppResult<Value> {
    api_get("/social/autopilot/status").await
}

#[command]
pub async fn clawbot_api_autopilot_start() -> AppResult<Value> {
    api_post("/social/autopilot/start", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_autopilot_stop() -> AppResult<Value> {
    api_post("/social/autopilot/stop", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_autopilot_trigger(job_id: String) -> AppResult<Value> {
    api_post(
        &format!("/social/autopilot/trigger/{}", urlencoding_encode(&job_id)),
        serde_json::json!({}),
    )
    .await
}

// ──── Social Drafts ────

#[command]
pub async fn clawbot_api_social_drafts() -> AppResult<Value> {
    api_get("/social/drafts").await
}

#[command]
pub async fn clawbot_api_social_draft_update(index: u32, text: String) -> AppResult<Value> {
    api_patch(
        &format!(
            "/social/drafts/{}?text={}",
            index,
            urlencoding_encode(&text)
        ),
        serde_json::json!({}),
    )
    .await
}

/// 删除指定草稿
#[command]
pub async fn clawbot_api_social_draft_delete(index: u32) -> AppResult<Value> {
    let url = format!("{}/social/drafts/{}", CLAWBOT_API_BASE, index);

    let mut req = CLIENT.delete(&url);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| AppError::network(format!("ClawBot API unreachable: {}", e)))?;

    if !resp.status().is_success() {
        return Err(AppError::network(format!("HTTP {}", resp.status())));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| AppError::serialization(format!("JSON error: {}", e)))
}

#[command]
pub async fn clawbot_api_social_draft_review(
    index: u32,
    approved: bool,
    reviewer: Option<String>,
) -> AppResult<Value> {
    let reviewer = reviewer.unwrap_or_else(|| "owner".to_string());
    api_post(
        &format!(
            "/social/drafts/{}/review?approved={}&reviewer={}",
            index,
            approved,
            urlencoding_encode(&reviewer),
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_draft_final_confirm(
    index: u32,
    reviewer: Option<String>,
) -> AppResult<Value> {
    let reviewer = reviewer.unwrap_or_else(|| "owner".to_string());
    api_post(
        &format!(
            "/social/drafts/{}/final-confirm?reviewer={}",
            index,
            urlencoding_encode(&reviewer),
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_draft_publish(
    index: u32,
    confirmation_token: String,
) -> AppResult<Value> {
    if confirmation_token.trim().is_empty() {
        return Err(AppError::validation("发布草稿需要一次性最终确认令牌"));
    }
    api_post(
        &format!("/social/drafts/{}/publish", index),
        serde_json::json!({ "confirmation_token": confirmation_token }),
    )
    .await
}

// ──── Image Generation ────

#[command]
pub async fn clawbot_api_generate_image(prompt: String) -> AppResult<Value> {
    api_post(
        &format!(
            "/social/generate-image?prompt={}",
            urlencoding_encode(&prompt)
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_generate_persona_photo(
    persona: Option<String>,
    scenario: Option<String>,
    mood: Option<String>,
) -> AppResult<Value> {
    let p = persona.unwrap_or_else(|| "default".to_string());
    let s = scenario.unwrap_or_else(|| "working in a cafe".to_string());
    let m = mood.unwrap_or_else(|| "natural".to_string());
    api_post(
        &format!(
            "/social/generate-persona-photo?persona={}&scenario={}&mood={}",
            urlencoding_encode(&p),
            urlencoding_encode(&s),
            urlencoding_encode(&m)
        ),
        serde_json::json!({}),
    )
    .await
}

// ──── Memory ────

/// 搜索记忆库
#[command]
pub async fn clawbot_api_memory_search(
    query: String,
    limit: Option<u32>,
    mode: Option<String>,
    category: Option<String>,
) -> AppResult<Value> {
    let mut url = format!(
        "/memory/search?query={}&limit={}&mode={}",
        urlencoding_encode(&query),
        limit.unwrap_or(10),
        mode.as_deref().unwrap_or("hybrid"),
    );
    if let Some(cat) = category {
        url.push_str(&format!("&category={}", urlencoding_encode(&cat)));
    }
    api_get(&url).await
}

/// 记忆库统计信息
#[command]
pub async fn clawbot_api_memory_stats() -> AppResult<Value> {
    api_get("/memory/stats").await
}

/// 删除指定记忆条目
#[command]
pub async fn clawbot_api_memory_delete(key: String) -> AppResult<Value> {
    api_post("/memory/delete", serde_json::json!({ "key": key })).await
}

/// 更新指定记忆条目
#[command]
pub async fn clawbot_api_memory_update(key: String, value: String) -> AppResult<Value> {
    api_post(
        "/memory/update",
        serde_json::json!({ "key": key, "value": value }),
    )
    .await
}

// ──── API Pool ────

#[command]
pub async fn clawbot_api_pool_stats() -> AppResult<Value> {
    api_get("/pool/stats").await
}

// ──── Evolution ────

#[command]
pub async fn clawbot_api_evolution_scan() -> AppResult<Value> {
    api_post("/evolution/scan", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_evolution_proposals(
    status: Option<String>,
    limit: Option<u32>,
) -> AppResult<Value> {
    let mut url = format!("/evolution/proposals?limit={}", limit.unwrap_or(50));
    if let Some(s) = status {
        url.push_str(&format!("&status={}", urlencoding_encode(&s)));
    }
    api_get(&url).await
}

#[command]
pub async fn clawbot_api_evolution_gaps() -> AppResult<Value> {
    api_get("/evolution/gaps").await
}

#[command]
pub async fn clawbot_api_evolution_stats() -> AppResult<Value> {
    api_get("/evolution/stats").await
}

#[command]
pub async fn clawbot_api_evolution_update_proposal(
    proposal_id: String,
    status: String,
) -> AppResult<Value> {
    api_patch(
        &format!("/evolution/proposals/{}", urlencoding_encode(&proposal_id)),
        serde_json::json!({"status": status}),
    )
    .await
}

// ──── Shopping (比价引擎) ────

#[command]
pub async fn clawbot_api_shopping_compare(
    query: String,
    limit: Option<u32>,
    ai_summary: Option<bool>,
) -> AppResult<Value> {
    let l = limit.unwrap_or(5);
    let ai = ai_summary.unwrap_or(true);
    api_post(
        &format!(
            "/shopping/compare?query={}&limit={}&ai_summary={}",
            urlencoding_encode(&query),
            l,
            ai,
        ),
        serde_json::json!({}),
    )
    .await
}

/// URL 编码：逐字节处理，正确支持非 ASCII 字符（如中文）
fn urlencoding_encode(s: &str) -> String {
    let mut encoded = String::with_capacity(s.len() * 3);
    for byte in s.bytes() {
        match byte {
            // RFC 3986 未保留字符：字母、数字、- _ . ~
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(byte as char);
            }
            // 其他字节全部百分号编码
            _ => {
                encoded.push_str(&format!("%{:02X}", byte));
            }
        }
    }
    encoded
}

// ── OMEGA v2.0 API Commands ──────────────────────────────────

/// OMEGA 系统状态
#[command]
pub async fn clawbot_api_omega_status() -> AppResult<Value> {
    api_get("/omega/status").await
}

/// OMEGA 成本详情
#[command]
pub async fn clawbot_api_omega_cost() -> AppResult<Value> {
    api_get("/omega/cost").await
}

/// OMEGA 事件历史
#[command]
pub async fn clawbot_api_omega_events(
    event_type: Option<String>,
    limit: Option<u32>,
) -> AppResult<Value> {
    let et = event_type.unwrap_or_default();
    let l = limit.unwrap_or(50);
    api_get(&format!("/omega/events?event_type={}&limit={}", et, l)).await
}

/// OMEGA 审计日志
#[command]
pub async fn clawbot_api_omega_audit(limit: Option<u32>) -> AppResult<Value> {
    let l = limit.unwrap_or(50);
    api_get(&format!("/omega/audit?limit={}", l)).await
}

/// OMEGA 活跃任务
#[command]
pub async fn clawbot_api_omega_tasks() -> AppResult<Value> {
    api_get("/omega/tasks").await
}

/// OMEGA Brain 处理消息
#[command]
pub async fn clawbot_api_omega_process(message: String) -> AppResult<Value> {
    api_post(
        &format!(
            "/omega/process?message={}&source=tauri",
            urlencoding_encode(&message)
        ),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA 投资团队状态
#[command]
pub async fn clawbot_api_omega_investment_team() -> AppResult<Value> {
    api_get("/omega/investment/team").await
}

/// OMEGA 投资分析
#[command]
pub async fn clawbot_api_omega_investment_analyze(
    symbol: String,
    market: Option<String>,
) -> AppResult<Value> {
    let m = market.unwrap_or_else(|| "cn".to_string());
    api_post(
        &format!(
            "/omega/investment/analyze?symbol={}&market={}",
            urlencoding_encode(&symbol),
            m
        ),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA AI 图像生成
#[command]
pub async fn clawbot_api_omega_generate_image(
    prompt: String,
    model: Option<String>,
) -> AppResult<Value> {
    let m = model.unwrap_or_else(|| "fal-ai/flux/schnell".to_string());
    api_post(
        &format!(
            "/omega/tools/generate-image?prompt={}&model={}",
            urlencoding_encode(&prompt),
            urlencoding_encode(&m)
        ),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA AI 视频生成
#[command]
pub async fn clawbot_api_omega_generate_video(prompt: String) -> AppResult<Value> {
    api_post(
        &format!(
            "/omega/tools/generate-video?prompt={}",
            urlencoding_encode(&prompt)
        ),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA 可用媒体模型
#[command]
pub async fn clawbot_api_omega_media_models() -> AppResult<Value> {
    api_get("/omega/tools/media-models").await
}

#[cfg(test)]
mod tests {
    use super::{
        locate_xianyu_seller_launcher, xianyu_admin_launch_endpoint, XIANYU_MANAGED_SERVICE_LABEL,
        XIANYU_SELLER_LAUNCHER,
    };

    #[test]
    fn xianyu_operator_uses_the_managed_service_contract() {
        assert_eq!(XIANYU_MANAGED_SERVICE_LABEL, "ai.openclaw.xianyu");
    }

    #[test]
    fn xianyu_launch_endpoint_allows_only_configurable_loopback_ports() {
        for (base, expected) in [
            (
                "http://127.0.0.1:18800",
                "http://127.0.0.1:18800/api/session/desktop-launch",
            ),
            (
                "http://localhost:19080/",
                "http://localhost:19080/api/session/desktop-launch",
            ),
            (
                "http://[::1]:19443",
                "http://[::1]:19443/api/session/desktop-launch",
            ),
        ] {
            let endpoint = xianyu_admin_launch_endpoint(base)
                .unwrap_or_else(|_| panic!("应允许本机回环地址: {base}"));
            assert_eq!(endpoint.as_str(), expected);
        }
    }

    #[test]
    fn xianyu_launch_endpoint_rejects_untrusted_or_ambiguous_bases() {
        for base in [
            "http://198.51.100.10:18800",
            "https://127.0.0.1:18800",
            "http://localhost.evil.example:18800",
            "http://127.0.0.1:18800/admin?next=outside",
            "http:///api/session/desktop-launch",
            "http://operator@127.0.0.1:18800",
        ] {
            assert!(
                xianyu_admin_launch_endpoint(base).is_err(),
                "必须在读取 Token 前拒绝: {base}"
            );
        }
    }

    #[test]
    fn seller_launcher_discovery_requires_the_known_launcher_script() {
        let (script, root) = locate_xianyu_seller_launcher().expect("开发仓库应能发现闲鱼启动器");
        assert_eq!(
            script.file_name().and_then(|name| name.to_str()),
            Some(XIANYU_SELLER_LAUNCHER)
        );
        assert!(root.join("scripts").join(XIANYU_SELLER_LAUNCHER).is_file());
    }
}

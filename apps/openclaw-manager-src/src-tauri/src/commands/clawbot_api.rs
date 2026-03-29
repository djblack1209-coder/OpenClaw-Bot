//! ClawBot Internal API client
//! Calls the FastAPI server running at localhost:18790
//! Pattern: thin wrappers that proxy HTTP calls to the Python backend

use serde_json::Value;
use tauri::command;

const CLAWBOT_API_BASE: &str = "http://127.0.0.1:18790/api/v1";

/// Read OPENCLAW_API_TOKEN from environment (set by shell or .env loader)
fn get_api_token() -> Option<String> {
    std::env::var("OPENCLAW_API_TOKEN").ok().filter(|s| !s.is_empty())
}

/// Helper: GET request to ClawBot API
async fn api_get(path: &str) -> Result<Value, String> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let mut req = client.get(&url);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("ClawBot API unreachable ({}): {}", url, e))?;

    if !resp.status().is_success() {
        return Err(format!("ClawBot API error: HTTP {}", resp.status()));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))
}

/// Helper: POST request to ClawBot API
async fn api_post(path: &str, body: Value) -> Result<Value, String> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let mut req = client.post(&url).json(&body);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("ClawBot API unreachable ({}): {}", url, e))?;

    if !resp.status().is_success() {
        return Err(format!("ClawBot API error: HTTP {}", resp.status()));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))
}

/// Helper: PATCH request to ClawBot API
async fn api_patch(path: &str, body: Value) -> Result<Value, String> {
    let url = format!("{}{}", CLAWBOT_API_BASE, path);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let mut req = client.patch(&url).json(&body);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("ClawBot API unreachable ({}): {}", url, e))?;

    if !resp.status().is_success() {
        return Err(format!("ClawBot API error: HTTP {}", resp.status()));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))
}

// ──── System ────

#[command]
pub async fn clawbot_api_ping() -> Result<Value, String> {
    api_get("/ping").await
}

#[command]
pub async fn clawbot_api_status() -> Result<Value, String> {
    api_get("/status").await
}

// ──── Trading ────

/// 获取交易系统实时状态（连接、持仓、图表数据）
#[command]
pub async fn clawbot_api_trading_status() -> Result<Value, String> {
    api_get("/trading/status").await
}

/// 当前持仓列表
#[command]
pub async fn clawbot_api_trading_positions() -> Result<Value, String> {
    api_get("/trading/positions").await
}

#[command]
pub async fn clawbot_api_trading_pnl() -> Result<Value, String> {
    api_get("/trading/pnl").await
}

#[command]
pub async fn clawbot_api_trading_signals() -> Result<Value, String> {
    api_get("/trading/signals").await
}

#[command]
pub async fn clawbot_api_trading_system() -> Result<Value, String> {
    api_get("/trading/system").await
}

#[command]
pub async fn clawbot_api_trading_vote(symbol: String, period: String) -> Result<Value, String> {
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
pub async fn clawbot_api_social_browser_status() -> Result<Value, String> {
    api_get("/social/browser-status").await
}

/// 社媒系统运行状态
#[command]
pub async fn clawbot_api_social_status() -> Result<Value, String> {
    api_get("/social/status").await
}

#[command]
pub async fn clawbot_api_social_topics(count: Option<u32>) -> Result<Value, String> {
    let c = count.unwrap_or(10);
    api_post(
        &format!("/social/topics?count={}", c),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_compose(
    topic: String,
    platform: Option<String>,
    persona: Option<String>,
) -> Result<Value, String> {
    let p = platform.unwrap_or_else(|| "x".to_string());
    let per = persona.unwrap_or_else(|| "default".to_string());
    api_post(
        &format!("/social/compose?topic={}&platform={}&persona={}",
            urlencoding_encode(&topic),
            urlencoding_encode(&p),
            urlencoding_encode(&per),
        ),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_publish(
    platform: String,
    content: String,
) -> Result<Value, String> {
    api_post("/social/publish", serde_json::json!({
        "platform": platform,
        "content": content,
    }))
    .await
}

#[command]
pub async fn clawbot_api_social_research(topic: String, count: Option<u32>) -> Result<Value, String> {
    let c = count.unwrap_or(10);
    api_post(
        &format!("/social/research?topic={}&count={}", urlencoding_encode(&topic), c),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_metrics() -> Result<Value, String> {
    api_get("/social/metrics").await
}

#[command]
pub async fn clawbot_api_social_personas() -> Result<Value, String> {
    api_get("/social/personas").await
}

#[command]
pub async fn clawbot_api_social_calendar(days: Option<u32>) -> Result<Value, String> {
    api_get(&format!("/social/calendar?days={}", days.unwrap_or(7))).await
}

// ──── Social Autopilot ────

#[command]
pub async fn clawbot_api_autopilot_status() -> Result<Value, String> {
    api_get("/social/autopilot/status").await
}

#[command]
pub async fn clawbot_api_autopilot_start() -> Result<Value, String> {
    api_post("/social/autopilot/start", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_autopilot_stop() -> Result<Value, String> {
    api_post("/social/autopilot/stop", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_autopilot_trigger(job_id: String) -> Result<Value, String> {
    api_post(&format!("/social/autopilot/trigger/{}", urlencoding_encode(&job_id)), serde_json::json!({})).await
}

// ──── Social Drafts ────

#[command]
pub async fn clawbot_api_social_drafts() -> Result<Value, String> {
    api_get("/social/drafts").await
}

#[command]
pub async fn clawbot_api_social_draft_update(index: u32, text: String) -> Result<Value, String> {
    api_patch(
        &format!("/social/drafts/{}?text={}", index, urlencoding_encode(&text)),
        serde_json::json!({}),
    )
    .await
}

#[command]
pub async fn clawbot_api_social_draft_delete(index: u32) -> Result<Value, String> {
    let url = format!("{}/social/drafts/{}", CLAWBOT_API_BASE, index);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let mut req = client.delete(&url);
    if let Some(token) = get_api_token() {
        req = req.header("X-API-Token", token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("ClawBot API unreachable: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| format!("JSON error: {}", e))
}

#[command]
pub async fn clawbot_api_social_draft_publish(index: u32) -> Result<Value, String> {
    api_post(
        &format!("/social/drafts/{}/publish", index),
        serde_json::json!({}),
    )
    .await
}

// ──── Image Generation ────

#[command]
pub async fn clawbot_api_generate_image(prompt: String) -> Result<Value, String> {
    api_post(&format!("/social/generate-image?prompt={}", urlencoding_encode(&prompt)), serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_generate_persona_photo(
    persona: Option<String>,
    scenario: Option<String>,
    mood: Option<String>,
) -> Result<Value, String> {
    let p = persona.unwrap_or_else(|| "default".to_string());
    let s = scenario.unwrap_or_else(|| "working in a cafe".to_string());
    let m = mood.unwrap_or_else(|| "natural".to_string());
    api_post(
        &format!("/social/generate-persona-photo?persona={}&scenario={}&mood={}",
            urlencoding_encode(&p), urlencoding_encode(&s), urlencoding_encode(&m)),
        serde_json::json!({}),
    ).await
}

// ──── Memory ────

/// 搜索记忆库
#[command]
pub async fn clawbot_api_memory_search(
    query: String,
    limit: Option<u32>,
    mode: Option<String>,
    category: Option<String>,
) -> Result<Value, String> {
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
pub async fn clawbot_api_memory_stats() -> Result<Value, String> {
    api_get("/memory/stats").await
}

/// 删除指定记忆条目
#[command]
pub async fn clawbot_api_memory_delete(key: String) -> Result<Value, String> {
    api_post("/memory/delete", serde_json::json!({ "key": key })).await
}

/// 更新指定记忆条目
#[command]
pub async fn clawbot_api_memory_update(key: String, value: String) -> Result<Value, String> {
    api_post("/memory/update", serde_json::json!({ "key": key, "value": value })).await
}

// ──── API Pool ────

#[command]
pub async fn clawbot_api_pool_stats() -> Result<Value, String> {
    api_get("/pool/stats").await
}

// ──── Evolution ────

#[command]
pub async fn clawbot_api_evolution_scan() -> Result<Value, String> {
    api_post("/evolution/scan", serde_json::json!({})).await
}

#[command]
pub async fn clawbot_api_evolution_proposals(status: Option<String>, limit: Option<u32>) -> Result<Value, String> {
    let mut url = format!("/evolution/proposals?limit={}", limit.unwrap_or(50));
    if let Some(s) = status {
        url.push_str(&format!("&status={}", urlencoding_encode(&s)));
    }
    api_get(&url).await
}

#[command]
pub async fn clawbot_api_evolution_gaps() -> Result<Value, String> {
    api_get("/evolution/gaps").await
}

#[command]
pub async fn clawbot_api_evolution_stats() -> Result<Value, String> {
    api_get("/evolution/stats").await
}

#[command]
pub async fn clawbot_api_evolution_update_proposal(proposal_id: String, status: String) -> Result<Value, String> {
    api_patch(
        &format!("/evolution/proposals/{}", urlencoding_encode(&proposal_id)),
        serde_json::json!({"status": status}),
    ).await
}

// ──── Shopping (比价引擎) ────

#[command]
pub async fn clawbot_api_shopping_compare(
    query: String,
    limit: Option<u32>,
    ai_summary: Option<bool>,
) -> Result<Value, String> {
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
pub async fn clawbot_api_omega_status() -> Result<Value, String> {
    api_get("/omega/status").await
}

/// OMEGA 成本详情
#[command]
pub async fn clawbot_api_omega_cost() -> Result<Value, String> {
    api_get("/omega/cost").await
}

/// OMEGA 事件历史
#[command]
pub async fn clawbot_api_omega_events(event_type: Option<String>, limit: Option<u32>) -> Result<Value, String> {
    let et = event_type.unwrap_or_default();
    let l = limit.unwrap_or(50);
    api_get(&format!("/omega/events?event_type={}&limit={}", et, l)).await
}

/// OMEGA 审计日志
#[command]
pub async fn clawbot_api_omega_audit(limit: Option<u32>) -> Result<Value, String> {
    let l = limit.unwrap_or(50);
    api_get(&format!("/omega/audit?limit={}", l)).await
}

/// OMEGA 活跃任务
#[command]
pub async fn clawbot_api_omega_tasks() -> Result<Value, String> {
    api_get("/omega/tasks").await
}

/// OMEGA Brain 处理消息
#[command]
pub async fn clawbot_api_omega_process(message: String) -> Result<Value, String> {
    api_post(
        &format!("/omega/process?message={}&source=tauri", urlencoding_encode(&message)),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA 投资团队状态
#[command]
pub async fn clawbot_api_omega_investment_team() -> Result<Value, String> {
    api_get("/omega/investment/team").await
}

/// OMEGA 投资分析
#[command]
pub async fn clawbot_api_omega_investment_analyze(symbol: String, market: Option<String>) -> Result<Value, String> {
    let m = market.unwrap_or_else(|| "cn".to_string());
    api_post(
        &format!("/omega/investment/analyze?symbol={}&market={}", urlencoding_encode(&symbol), m),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA AI 图像生成
#[command]
pub async fn clawbot_api_omega_generate_image(prompt: String, model: Option<String>) -> Result<Value, String> {
    let m = model.unwrap_or_else(|| "fal-ai/flux/schnell".to_string());
    api_post(
        &format!("/omega/tools/generate-image?prompt={}&model={}", urlencoding_encode(&prompt), urlencoding_encode(&m)),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA AI 视频生成
#[command]
pub async fn clawbot_api_omega_generate_video(prompt: String) -> Result<Value, String> {
    api_post(
        &format!("/omega/tools/generate-video?prompt={}", urlencoding_encode(&prompt)),
        serde_json::json!({}),
    )
    .await
}

/// OMEGA 可用媒体模型
#[command]
pub async fn clawbot_api_omega_media_models() -> Result<Value, String> {
    api_get("/omega/tools/media-models").await
}

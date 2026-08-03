-- Intel Brief 独立数据库 schema
-- 说明：人物追踪已按 2026-07-06 补充决策改为开放输入，不再使用 celebrity_watchlist。

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    channel_type TEXT NOT NULL,
    channel_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscription_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_name TEXT NOT NULL UNIQUE,
    categories TEXT NOT NULL DEFAULT '[]',
    price_cents INTEGER NOT NULL DEFAULT 0,
    duration_type TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    starts_at TEXT NOT NULL,
    expires_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
);

CREATE TABLE IF NOT EXISTS source_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscriber_id, category),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
);

CREATE TABLE IF NOT EXISTS delivery_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL UNIQUE,
    frequency TEXT NOT NULL DEFAULT 'daily',
    delivery_time TEXT NOT NULL DEFAULT '08:30',
    timezone TEXT NOT NULL DEFAULT 'Asia/Singapore',
    content_language TEXT NOT NULL DEFAULT 'zh' CHECK (content_language IN ('zh', 'en')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
);

CREATE TABLE IF NOT EXISTS subscription_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    plan_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    event_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
);

CREATE TABLE IF NOT EXISTS tracking_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    first_tracked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_fetch_at TEXT,
    active_subscription_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS tracking_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    subscribed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',
    UNIQUE (subscriber_id, target_id),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
    FOREIGN KEY (target_id) REFERENCES tracking_targets(id)
);

CREATE TABLE IF NOT EXISTS tracking_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_user_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_channel TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_summary TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
);

CREATE TABLE IF NOT EXISTS source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    last_success_at TEXT,
    last_failure_at TEXT,
    last_failure_reason TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telegram_runtime_state (
    bot_profile TEXT PRIMARY KEY,
    last_update_id INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telegram_pending_actions (
    user_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_moderation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    content_id TEXT,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    classifier_label TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intel_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_ref TEXT NOT NULL UNIQUE,
    brief_date TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_payload TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brief_date, content_hash)
);

CREATE TABLE IF NOT EXISTS intel_brief_localizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
    translator_version TEXT NOT NULL,
    status TEXT NOT NULL,
    localized_payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brief_id, language, translator_version),
    FOREIGN KEY (brief_id) REFERENCES intel_briefs(id)
);

CREATE TABLE IF NOT EXISTS content_translation_cache (
    cache_key TEXT PRIMARY KEY,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    translator_version TEXT NOT NULL,
    status TEXT NOT NULL,
    source_text_hash TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telegram_media_assets (
    asset_key TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    file_unique_id TEXT,
    mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
    byte_size INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invalidated_at TEXT
);

CREATE TABLE IF NOT EXISTS delivery_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_log_id INTEGER,
    subscriber_id INTEGER NOT NULL,
    brief_id INTEGER NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
    render_mode TEXT NOT NULL,
    message_ids TEXT NOT NULL DEFAULT '[]',
    envelope_json TEXT NOT NULL,
    media_asset_key TEXT,
    delivery_state TEXT NOT NULL DEFAULT 'sent',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (delivery_log_id) REFERENCES delivery_log(id),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
    FOREIGN KEY (brief_id) REFERENCES intel_briefs(id)
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    content_kind TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    event_at TEXT,
    published_at TEXT,
    observed_at TEXT NOT NULL,
    date_confidence TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, event_key)
);

CREATE TABLE IF NOT EXISTS content_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL,
    content_item_id INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_key, content_item_id),
    FOREIGN KEY (content_item_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS brief_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    brief_date TEXT NOT NULL,
    status TEXT NOT NULL,
    baseline_only INTEGER NOT NULL DEFAULT 0,
    fresh_sources TEXT NOT NULL DEFAULT '[]',
    cached_sources TEXT NOT NULL DEFAULT '[]',
    failed_sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS brief_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_run_id INTEGER NOT NULL,
    content_item_id INTEGER NOT NULL,
    eligible INTEGER NOT NULL,
    decision TEXT NOT NULL,
    age_hours REAL,
    score REAL NOT NULL DEFAULT 0,
    rank_position INTEGER,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brief_run_id, content_item_id),
    FOREIGN KEY (brief_run_id) REFERENCES brief_runs(id),
    FOREIGN KEY (content_item_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS content_delivery_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    content_item_id INTEGER,
    event_key TEXT NOT NULL,
    brief_id INTEGER,
    state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed', 'unknown')),
    attempt_count INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscriber_id, event_key),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
    FOREIGN KEY (content_item_id) REFERENCES content_items(id),
    FOREIGN KEY (brief_id) REFERENCES intel_briefs(id)
);

CREATE TABLE IF NOT EXISTS delivery_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    brief_id INTEGER NOT NULL,
    brief_date TEXT NOT NULL,
    claim_token TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('claimed', 'sent', 'failed', 'unknown')),
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscriber_id, brief_date),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
    FOREIGN KEY (brief_id) REFERENCES intel_briefs(id)
);

CREATE TABLE IF NOT EXISTS content_pipeline_state (
    state_key TEXT PRIMARY KEY,
    state_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL,
    source_name TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    item_count INTEGER NOT NULL DEFAULT 0,
    worker TEXT NOT NULL DEFAULT '',
    fallback_used INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT NOT NULL DEFAULT '',
    UNIQUE (run_key, source_name)
);

CREATE TABLE IF NOT EXISTS source_last_good (
    source_name TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_content_items_published_at
    ON content_items (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_items_entity_key
    ON content_items (entity_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_delivery_artifacts_subscriber
    ON delivery_artifacts (subscriber_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_delivery_attempts_state
    ON content_delivery_attempts (subscriber_id, state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_delivery_claims_state
    ON delivery_claims (state, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_source_attempts_source
    ON source_attempts (source_name, attempted_at DESC);

#!/usr/bin/env node
/**
 * 把 JIYU AI 生产配置从 6 个聚合渠道迁移为 10 个一对一渠道和监控。
 *
 * 脚本只在 Oracle 主机内存中读取账号凭据，用同一 AES-GCM 密钥生成监控密文；
 * 凭据不会经过本机、标准输出或临时文件。变更前自动执行完整备份。
 */

import { execFileSync } from 'node:child_process';

const apply = process.argv.includes('--apply');

const remotePython = String.raw`
import base64
import json
import os
import secrets
import subprocess
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

APPLY = __APPLY__

def run(command, *, input_text=None):
    completed = subprocess.run(command, input=input_text, text=True, capture_output=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "命令执行失败").strip()[:800]
        raise RuntimeError(detail)
    return completed.stdout.strip()

def psql(sql):
    return run(["runuser", "-u", "postgres", "--", "psql", "-d", "sub2api", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql])

def sql_quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def load_env(path):
    values = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values

snapshot_sql = r'''SELECT json_build_object(
  'groups', (SELECT count(*) FROM groups WHERE deleted_at IS NULL),
  'accounts', (SELECT count(*) FROM accounts WHERE deleted_at IS NULL),
  'channels', (SELECT count(*) FROM channels WHERE status='active'),
  'monitors', (SELECT count(*) FROM channel_monitors WHERE enabled),
  'rate_ok', (SELECT count(*)=10 AND bool_and(round(g.rate_multiplier-a.rate_multiplier,4)=0.0500) FROM groups g JOIN account_groups ag ON ag.group_id=g.id JOIN accounts a ON a.id=ag.account_id WHERE g.deleted_at IS NULL AND a.deleted_at IS NULL)
)'''
before = json.loads(psql(snapshot_sql))
already_done = before == {"groups": 10, "accounts": 10, "channels": 10, "monitors": 10, "rate_ok": True}
if already_done:
    print(json.dumps({"ok": True, "changed": False, "before": before, "after": before}, ensure_ascii=False))
    raise SystemExit(0)

expected = {"groups": 10, "accounts": 10, "channels": 6, "monitors": 6, "rate_ok": True}
if before != expected:
    raise RuntimeError(f"生产基线不符合迁移前置条件: {before}")

if not APPLY:
    print(json.dumps({"ok": True, "changed": False, "dry_run": True, "before": before, "target": {"groups":10,"accounts":10,"channels":10,"monitors":10,"rate_ok":True}}, ensure_ascii=False))
    raise SystemExit(0)

run(["/usr/local/sbin/openclaw-sub2api-manager", "backup"])

credentials = json.loads(psql("SELECT COALESCE(json_agg(json_build_object('id',id,'api_key',credentials->>'api_key','base_url',credentials->>'base_url') ORDER BY id),'[]'::json) FROM accounts WHERE id IN (2,4,7,9)"))
by_id = {int(item["id"]): item for item in credentials}
if set(by_id) != {2, 4, 7, 9} or any(not item.get("api_key") or not item.get("base_url") for item in credentials):
    raise RuntimeError("缺少待新增监控对应的账号凭据")

env = load_env("/etc/sub2api/sub2api.env")
key = bytes.fromhex(env.get("TOTP_ENCRYPTION_KEY", ""))
if len(key) != 32:
    raise RuntimeError("TOTP_ENCRYPTION_KEY 不是 32 字节")

def encrypt(value):
    nonce = secrets.token_bytes(12)
    payload = AESGCM(key).encrypt(nonce, value.encode(), None)
    return base64.b64encode(nonce + payload).decode()

def normalized_endpoint(value):
    endpoint = value.rstrip('/')
    return endpoint[:-3] if endpoint.endswith('/v1') else endpoint

monitor_secrets = {
    account_id: {
        "endpoint": normalized_endpoint(item["base_url"]),
        "encrypted": encrypt(item["api_key"]),
    }
    for account_id, item in by_id.items()
}

sql = f'''
BEGIN;

UPDATE groups SET name='JIYU Claude 官 Key · 渠道A', updated_at=NOW() WHERE id=8;
UPDATE groups SET name='JIYU Claude 官 Key · 渠道B', updated_at=NOW() WHERE id=13;
UPDATE groups SET description='OpenAI Pro 模型服务 · 渠道A', updated_at=NOW() WHERE id=9;
UPDATE groups SET rate_multiplier=0.1100, updated_at=NOW() WHERE id=10;
UPDATE groups SET description='OpenAI Plus 模型服务 · 渠道A', updated_at=NOW() WHERE id=10;
UPDATE accounts SET name='JIYU——Claude 官 Key｜渠道A', updated_at=NOW() WHERE id=2;
UPDATE accounts SET name='JIYU——Claude 官 Key｜渠道B', updated_at=NOW() WHERE id=7;
UPDATE accounts SET rate_multiplier=0.0600, updated_at=NOW() WHERE id=4;

UPDATE channels SET name='JIYU 渠道A · Claude Kiro', updated_at=NOW() WHERE id=1;
UPDATE channels SET name='JIYU 渠道A · OpenAI Pro', updated_at=NOW() WHERE id=2;
UPDATE channels SET name='JIYU 渠道A · Grok', updated_at=NOW() WHERE id=3;
UPDATE channels SET name='JIYU 渠道B · Claude Kiro', updated_at=NOW() WHERE id=4;
UPDATE channels SET name='JIYU 渠道B · OpenAI Pro', updated_at=NOW() WHERE id=5;
UPDATE channels SET name='JIYU 渠道B · Grok', updated_at=NOW() WHERE id=6;

INSERT INTO channels (name,description,status,created_at,updated_at,model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config)
SELECT 'JIYU 渠道A · Claude 官 Key',description,status,NOW(),NOW(),model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config FROM channels WHERE id=1;
INSERT INTO channels (name,description,status,created_at,updated_at,model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config)
SELECT 'JIYU 渠道A · OpenAI Plus',description,status,NOW(),NOW(),model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config FROM channels WHERE id=2;
INSERT INTO channels (name,description,status,created_at,updated_at,model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config)
SELECT 'JIYU 渠道B · Claude 官 Key',description,status,NOW(),NOW(),model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config FROM channels WHERE id=4;
INSERT INTO channels (name,description,status,created_at,updated_at,model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config)
SELECT 'JIYU 渠道B · OpenAI Plus',description,status,NOW(),NOW(),model_mapping,billing_model_source,restrict_models,features,apply_pricing_to_account_stats,features_config FROM channels WHERE id=5;

DELETE FROM channel_groups;
INSERT INTO channel_groups (channel_id,group_id,created_at)
SELECT c.id,g.id,NOW() FROM (VALUES
  ('JIYU 渠道A · Claude Kiro','JIYU Claude Kiro · 渠道A'),
  ('JIYU 渠道A · Claude 官 Key','JIYU Claude 官 Key · 渠道A'),
  ('JIYU 渠道A · OpenAI Pro','JIYU OpenAI Pro · 渠道A'),
  ('JIYU 渠道A · OpenAI Plus','JIYU OpenAI Plus · 渠道A'),
  ('JIYU 渠道A · Grok','JIYU Grok · 渠道A'),
  ('JIYU 渠道B · Claude Kiro','JIYU Claude Kiro · 渠道B'),
  ('JIYU 渠道B · Claude 官 Key','JIYU Claude 官 Key · 渠道B'),
  ('JIYU 渠道B · OpenAI Pro','JIYU OpenAI Pro · 渠道B'),
  ('JIYU 渠道B · OpenAI Plus','JIYU OpenAI Plus · 渠道B'),
  ('JIYU 渠道B · Grok','JIYU Grok · 渠道B')
) AS mapping(channel_name,group_name)
JOIN channels c ON c.name=mapping.channel_name
JOIN groups g ON g.name=mapping.group_name AND g.deleted_at IS NULL;

INSERT INTO channel_model_pricing (channel_id,models,input_price,output_price,cache_write_price,cache_read_price,image_output_price,created_at,updated_at,billing_mode,per_request_price,platform,image_input_price)
SELECT target.id,p.models,p.input_price,p.output_price,p.cache_write_price,p.cache_read_price,p.image_output_price,NOW(),NOW(),p.billing_mode,p.per_request_price,p.platform,p.image_input_price
FROM (VALUES (1,'JIYU 渠道A · Claude 官 Key'),(2,'JIYU 渠道A · OpenAI Plus'),(4,'JIYU 渠道B · Claude 官 Key'),(5,'JIYU 渠道B · OpenAI Plus')) AS mapping(source_id,target_name)
JOIN channels target ON target.name=mapping.target_name
JOIN channel_model_pricing p ON p.channel_id=mapping.source_id;

UPDATE channel_monitors SET name='JIYU 渠道A · Claude Kiro',group_name='JIYU 渠道A · Claude Kiro',updated_at=NOW() WHERE id=1;
UPDATE channel_monitors SET name='JIYU 渠道A · OpenAI Pro',group_name='JIYU 渠道A · OpenAI Pro',updated_at=NOW() WHERE id=2;
UPDATE channel_monitors SET name='JIYU 渠道A · Grok',group_name='JIYU 渠道A · Grok',updated_at=NOW() WHERE id=3;
UPDATE channel_monitors SET name='JIYU 渠道B · Claude Kiro',group_name='JIYU 渠道B · Claude Kiro',updated_at=NOW() WHERE id=4;
UPDATE channel_monitors SET name='JIYU 渠道B · OpenAI Pro',group_name='JIYU 渠道B · OpenAI Pro',updated_at=NOW() WHERE id=5;
UPDATE channel_monitors SET name='JIYU 渠道B · Grok',group_name='JIYU 渠道B · Grok',updated_at=NOW() WHERE id=6;

INSERT INTO channel_monitors (name,provider,endpoint,api_key_encrypted,primary_model,extra_models,group_name,enabled,interval_seconds,created_by,created_at,updated_at,template_id,extra_headers,body_override_mode,body_override,api_mode,jitter_seconds)
SELECT 'JIYU 渠道A · Claude 官 Key',provider,{sql_quote(monitor_secrets[2]['endpoint'])},{sql_quote(monitor_secrets[2]['encrypted'])},primary_model,extra_models,'JIYU 渠道A · Claude 官 Key',true,300,created_by,NOW(),NOW(),template_id,extra_headers,body_override_mode,body_override,api_mode,30 FROM channel_monitors WHERE id=1;
INSERT INTO channel_monitors (name,provider,endpoint,api_key_encrypted,primary_model,extra_models,group_name,enabled,interval_seconds,created_by,created_at,updated_at,template_id,extra_headers,body_override_mode,body_override,api_mode,jitter_seconds)
SELECT 'JIYU 渠道A · OpenAI Plus',provider,{sql_quote(monitor_secrets[4]['endpoint'])},{sql_quote(monitor_secrets[4]['encrypted'])},primary_model,extra_models,'JIYU 渠道A · OpenAI Plus',true,300,created_by,NOW(),NOW(),template_id,extra_headers,body_override_mode,body_override,api_mode,30 FROM channel_monitors WHERE id=2;
INSERT INTO channel_monitors (name,provider,endpoint,api_key_encrypted,primary_model,extra_models,group_name,enabled,interval_seconds,created_by,created_at,updated_at,template_id,extra_headers,body_override_mode,body_override,api_mode,jitter_seconds)
SELECT 'JIYU 渠道B · Claude 官 Key',provider,{sql_quote(monitor_secrets[7]['endpoint'])},{sql_quote(monitor_secrets[7]['encrypted'])},primary_model,extra_models,'JIYU 渠道B · Claude 官 Key',true,300,created_by,NOW(),NOW(),template_id,extra_headers,body_override_mode,body_override,api_mode,30 FROM channel_monitors WHERE id=4;
INSERT INTO channel_monitors (name,provider,endpoint,api_key_encrypted,primary_model,extra_models,group_name,enabled,interval_seconds,created_by,created_at,updated_at,template_id,extra_headers,body_override_mode,body_override,api_mode,jitter_seconds)
SELECT 'JIYU 渠道B · OpenAI Plus',provider,{sql_quote(monitor_secrets[9]['endpoint'])},{sql_quote(monitor_secrets[9]['encrypted'])},primary_model,extra_models,'JIYU 渠道B · OpenAI Plus',true,300,created_by,NOW(),NOW(),template_id,extra_headers,body_override_mode,body_override,api_mode,30 FROM channel_monitors WHERE id=5;

DO $guard$
BEGIN
  IF (SELECT count(*) FROM channels WHERE status='active') <> 10 THEN RAISE EXCEPTION 'active channel count mismatch'; END IF;
  IF (SELECT count(*) FROM channel_groups) <> 10 THEN RAISE EXCEPTION 'channel group count mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM channels c LEFT JOIN channel_groups cg ON cg.channel_id=c.id WHERE c.status='active' GROUP BY c.id HAVING count(cg.group_id)<>1) THEN RAISE EXCEPTION 'channel group mapping mismatch'; END IF;
  IF (SELECT count(*) FROM channel_monitors WHERE enabled AND interval_seconds=300 AND jitter_seconds=30) <> 10 THEN RAISE EXCEPTION 'monitor schedule mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM groups g JOIN account_groups ag ON ag.group_id=g.id JOIN accounts a ON a.id=ag.account_id WHERE g.deleted_at IS NULL AND round(g.rate_multiplier-a.rate_multiplier,4)<>0.0500) THEN RAISE EXCEPTION 'rate contract mismatch'; END IF;
END $guard$;

COMMIT;
'''
psql(sql)
run(["systemctl", "restart", "sub2api.service"])
run(["curl", "-fsS", "--retry", "20", "--retry-connrefused", "--retry-delay", "1", "--max-time", "10", "http://127.0.0.1:18080/health"])
after = json.loads(psql(snapshot_sql))
if after != {"groups": 10, "accounts": 10, "channels": 10, "monitors": 10, "rate_ok": True}:
    raise RuntimeError(f"迁移后合同校验失败: {after}")
print(json.dumps({"ok": True, "changed": True, "before": before, "after": after}, ensure_ascii=False))
`.replace('__APPLY__', apply ? 'True' : 'False');

try {
  const output = execFileSync('ssh', ['oracle-arm1', 'python3', '-'], {
    input: remotePython,
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  }).trim();
  console.log(output);
} catch (error) {
  const message = String(error.stderr || error.message || error).trim().slice(0, 1200);
  console.error(`JIYU AI 渠道迁移失败: ${message}`);
  process.exit(1);
}

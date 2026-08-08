#!/usr/bin/env node
/**
 * JIYU AI / 闲鱼运营就绪审计 v2。
 *
 * 脚本全程只读，只输出数量、布尔值和脱敏状态。它不读取浏览器 Cookie，
 * 不输出环境变量值、API Key、兑换码、邮箱或上游地址。
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const SCHEMA_VERSION = 2;
const REQUIRED_BOOKMARKS = [
  ['JIYU AI 本机操作台', 'http://127.0.0.1:18800/'],
  ['JIYU AI 用户主站', 'https://jiyu.245334.xyz/'],
];
const args = new Set(process.argv.slice(2));
const requireRealOrder = args.has('--require-real-order');
const jsonOnly = args.has('--json');

function pass(detail = {}) {
  return { ok: true, ...detail };
}

function fail(message, detail = {}) {
  return { ok: false, message, ...detail };
}

function safeJsonRead(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function parseEnvPresence(file, keys) {
  if (!fs.existsSync(file)) return Object.fromEntries(keys.map((key) => [key, false]));
  const content = fs.readFileSync(file, 'utf8');
  return Object.fromEntries(keys.map((key) => [key, new RegExp(`^${key}=.+`, 'm').test(content)]));
}

function parseEnvFile(file) {
  if (!fs.existsSync(file)) return {};
  const result = {};
  for (const rawLine of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const [key, ...rest] = line.split('=');
    result[key.trim()] = rest.join('=').trim().replace(/^['"]|['"]$/g, '');
  }
  return result;
}

function runLocal(command, commandArgs = [], options = {}) {
  return execFileSync(command, commandArgs, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  }).trim();
}

function httpJson(url, headers = {}) {
  return new Promise((resolve) => {
    const request = http.get(url, { headers, timeout: 5000 }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => {
        let json = null;
        try { json = JSON.parse(body); } catch { json = null; }
        resolve({ http: response.statusCode || 0, json });
      });
    });
    request.on('timeout', () => request.destroy(new Error('timeout')));
    request.on('error', (error) => resolve({ http: 0, error: String(error.message || error).slice(0, 120) }));
  });
}

function flattenBookmarkFolders(node, folders = []) {
  if (!node || typeof node !== 'object') return folders;
  if (node.type === 'folder' && ['JIYU AI 运营', 'CC中转运营'].includes(node.name)) folders.push(node);
  for (const child of node.children || []) flattenBookmarkFolders(child, folders);
  if (!node.type) {
    for (const key of ['bookmark_bar', 'other', 'synced']) {
      if (node[key]) flattenBookmarkFolders(node[key], folders);
    }
  }
  return folders;
}

function auditChromeBookmarks() {
  const base = path.join(os.homedir(), 'Library/Application Support/Google/Chrome');
  const localState = safeJsonRead(path.join(base, 'Local State'));
  const profiles = Object.keys(localState?.profile?.info_cache || {}).sort();
  if (!profiles.length) return fail('没有找到 Chrome Profile');
  const results = profiles.map((profile) => {
    const roots = safeJsonRead(path.join(base, profile, 'Bookmarks'))?.roots || {};
    const folders = flattenBookmarkFolders(roots);
    const urls = new Set((folders[0]?.children || []).filter((item) => item.type === 'url').map((item) => item.url));
    return {
      profile,
      folderCount: folders.length,
      missing: REQUIRED_BOOKMARKS.filter(([, url]) => !urls.has(url)).map(([name]) => name),
    };
  });
  const ok = results.some((item) => item.folderCount > 0 && item.missing.length === 0);
  return ok ? pass({ profiles: results }) : fail('JIYU AI 运营书签不完整', { profiles: results });
}

function auditLocalXianyu() {
  try {
    const row = runLocal('launchctl', ['list']).split('\n').find((line) => line.includes('ai.openclaw.xianyu')) || '';
    const running = /^\s*\d+\s+/.test(row);
    return running ? pass({ running: true }) : fail('闲鱼助手未运行', { running: false });
  } catch (error) {
    return fail('无法读取闲鱼助手状态', { error: String(error.message || error).slice(0, 120) });
  }
}

function auditLocalEnvPresence() {
  const file = path.join(process.cwd(), 'packages/clawbot/config/.env');
  const presence = parseEnvPresence(file, [
    'CC_XIANYU_AUTO_SHIP_ENABLED',
    'CC_XIANYU_WEBHOOK_URL',
    'CC_XIANYU_WEBHOOK_TOKEN',
    'XIANYU_COOKIES',
  ]);
  const missing = Object.entries(presence).filter(([, present]) => !present).map(([key]) => key);
  return missing.length ? fail('闲鱼助手配置缺失', { presence }) : pass({ presence });
}

async function auditLocalXianyuGui() {
  const env = parseEnvFile(path.join(process.cwd(), 'packages/clawbot/config/.env'));
  const token = env.OPENCLAW_API_TOKEN || '';
  if (!token) return fail('本机管理令牌缺失');
  const root = await httpJson('http://127.0.0.1:18800/');
  const noToken = await httpJson('http://127.0.0.1:18800/api/status');
  const status = await httpJson('http://127.0.0.1:18800/api/status', { 'X-API-Token': token });
  const data = status.json || {};
  const shipments = data.cc_shipments || {};
  const autoShip = data.cc_auto_ship || {};
  const detail = {
    rootHttp: root.http,
    apiNoTokenHttp: noToken.http,
    apiWithTokenHttp: status.http,
    wsConnected: data.ws_connected === true,
    cookieOk: data.cookie_ok === true,
    operatorPaused: autoShip.enabled === false && autoShip.configured === true,
    autoShipConfigured: autoShip.configured === true,
    pendingRescue: Number(shipments.pending_rescue || 0),
  };
  const ok = detail.rootHttp === 200 && detail.apiNoTokenHttp === 401 && detail.apiWithTokenHttp === 200 &&
    detail.wsConnected && detail.cookieOk && detail.autoShipConfigured && detail.pendingRescue === 0;
  return ok ? pass(detail) : fail('闲鱼助手运行态异常', detail);
}

function auditRealOrderProof() {
  const script = String.raw`
import json, sqlite3
from pathlib import Path
db=Path("packages/clawbot/data/xianyu_chat.db")
result={"required":__REQUIRED__,"dbExists":db.exists(),"sentRealOrders":0,"pendingRescue":0}
if db.exists():
    conn=sqlite3.connect(str(db)); cur=conn.cursor()
    result["sentRealOrders"]=cur.execute("SELECT COUNT(*) FROM cc_shipments WHERE status='message_sent' AND order_id LIKE 'xy_oid_%'").fetchone()[0]
    result["pendingRescue"]=cur.execute("SELECT COUNT(*) FROM cc_shipments WHERE status IN ('browser_delivery_claimed','message_send_failed','webhook_failed','missing_delivery_message','exception','manual_delivery_ready')").fetchone()[0]
    conn.close()
print(json.dumps(result,ensure_ascii=False))
`.replace('__REQUIRED__', requireRealOrder ? 'True' : 'False');
  try {
    const data = JSON.parse(runLocal('python3', ['-c', script]) || '{}');
    const hasProof = Number(data.sentRealOrders || 0) > 0 && Number(data.pendingRescue || 0) === 0;
    return requireRealOrder && !hasProof
      ? fail('缺少真实闲鱼订单履约证据', { ...data, hasProof })
      : pass({ ...data, hasProof });
  } catch (error) {
    return fail('无法读取闲鱼订单证据', { error: String(error.message || error).slice(0, 120) });
  }
}

function auditOracle() {
  const remotePython = String.raw`
import json, subprocess, urllib.error, urllib.request

def service(name):
    run=subprocess.run(["systemctl","is-active",name],text=True,capture_output=True)
    return run.stdout.strip()

def request(url, method="GET", data=None):
    payload=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(url,data=payload,method=method,headers={"user-agent":"JIYU-Readiness-Audit/2.0","accept":"text/html,application/json","content-type":"application/json"})
    body=""; status=0
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            status=response.status; body=response.read(250000).decode("utf-8","ignore")
    except urllib.error.HTTPError as error:
        status=error.code; body=error.read(250000).decode("utf-8","ignore")
    except Exception:
        return {"http":0}
    lowered=body.lower()
    return {"http":int(status),"has_jiyu":"jiyu ai" in lowered,"has_cc_switch":"cc switch" in lowered}

sql=r'''SELECT json_build_object(
  'groups', (SELECT json_agg(json_build_object('id',g.id,'name',g.name,'rate',g.rate_multiplier,'status',g.status,'platform',g.platform) ORDER BY g.id) FROM groups g WHERE g.deleted_at IS NULL),
  'accounts', (SELECT json_agg(json_build_object('id',a.id,'name',a.name,'rate',a.rate_multiplier,'status',a.status,'schedulable',a.schedulable,'group_count',membership.group_count,'group_id',membership.group_id,'group_name',membership.group_name) ORDER BY a.id) FROM accounts a LEFT JOIN LATERAL (SELECT count(*) AS group_count,min(g.id) AS group_id,min(g.name) AS group_name FROM account_groups ag JOIN groups g ON g.id=ag.group_id WHERE ag.account_id=a.id AND g.deleted_at IS NULL) membership ON true WHERE a.deleted_at IS NULL),
  'channels', (SELECT json_agg(json_build_object('id',c.id,'name',c.name,'status',c.status,'group_count',(SELECT count(*) FROM channel_groups cg WHERE cg.channel_id=c.id)) ORDER BY c.id) FROM channels c),
  'monitors', (SELECT json_agg(json_build_object('id',m.id,'name',m.name,'enabled',m.enabled,'interval',m.interval_seconds,'jitter',m.jitter_seconds,'latest_status',h.status,'last_checked_at',h.checked_at,'latency_ms',h.latency_ms) ORDER BY m.id) FROM channel_monitors m LEFT JOIN LATERAL (SELECT status,checked_at,latency_ms FROM channel_monitor_histories WHERE monitor_id=m.id ORDER BY checked_at DESC LIMIT 1) h ON true),
  'channel_pricing', (SELECT json_agg(json_build_object('channel_id',c.id,'channel_name',c.name,'billing_mode',p.billing_mode,'per_request_price',p.per_request_price) ORDER BY c.id) FROM channels c JOIN channel_model_pricing p ON p.channel_id=c.id WHERE c.status='active' AND c.name LIKE '%生图%'),
  'redeem_available', (SELECT count(*) FROM redeem_codes WHERE status='unused'),
  'active_keys', (SELECT count(*) FROM api_keys WHERE deleted_at IS NULL AND status='active'),
  'usage_logs', (SELECT count(*) FROM usage_logs),
  'site_name', (SELECT value FROM settings WHERE key='site_name')
)'''
run=subprocess.run(["runuser","-u","postgres","--","psql","-d","sub2api","-At","-c",sql],text=True,capture_output=True,check=True)
db=json.loads(run.stdout)
groups=db.get("groups") or []; accounts=db.get("accounts") or []; channels=db.get("channels") or []; monitors=db.get("monitors") or []; channel_pricing=db.get("channel_pricing") or []

def is_image(item):
    name=str(item.get("name") or item.get("group_name") or item.get("channel_name") or "")
    return "生图" in name

image_groups=[item for item in groups if is_image(item)]; text_groups=[item for item in groups if not is_image(item)]
active_channels=[item for item in channels if item.get("status")=="active"]
image_channels=[item for item in active_channels if is_image(item)]; text_channels=[item for item in active_channels if not is_image(item)]
image_monitors=[item for item in monitors if is_image(item)]; text_monitors=[item for item in monitors if not is_image(item)]
accounts_by_group={int(item["group_id"]):item for item in accounts if item.get("group_id") is not None and int(item.get("group_count") or 0)==1}

def rate_entry(group):
    account=accounts_by_group.get(int(group["id"]))
    try:
        group_rate=float(group["rate"]); account_rate=float(account["rate"]) if account else None
    except (TypeError, ValueError):
        group_rate=None; account_rate=None
    return {"group_id":group["id"],"account_id":account.get("id") if account else None,"group_rate":group_rate,"account_rate":account_rate,"difference":round(group_rate-account_rate,4) if group_rate is not None and account_rate is not None else None}

text_rates=[rate_entry(group) for group in text_groups]; image_rates=[rate_entry(group) for group in image_groups]; rates=text_rates+image_rates
scheduled_monitors=sum(1 for item in monitors if int(item.get("interval") or 0)==300 and int(item.get("jitter") or 0)==30)
enabled_text_monitors=sum(1 for item in text_monitors if item.get("enabled") is True)
enabled_image_monitors=sum(1 for item in image_monitors if item.get("enabled") is True)
disabled_image_monitors=sum(1 for item in image_monitors if item.get("enabled") is False)

def price_matches(fragment, expected):
    rows=[item for item in channel_pricing if fragment in str(item.get("channel_name") or "")]
    if len(rows)!=1:
        return False
    try:
        return abs(float(rows[0].get("per_request_price"))-expected)<0.0001
    except (TypeError, ValueError):
        return False

image_channel_ids={item.get("id") for item in image_channels if item.get("id") is not None}
pricing_channel_ids={item.get("channel_id") for item in channel_pricing if item.get("channel_id") is not None}
image_pricing_ok=len(image_channels)==2 and len(channel_pricing)==2 and image_channel_ids==pricing_channel_ids and all(item.get("billing_mode")=="image" for item in channel_pricing) and price_matches("渠道A",0.10) and price_matches("渠道B",0.12)
text_rate_difference_ok=len(text_rates)==10 and all(item.get("difference")==0.05 for item in text_rates)
image_rate_difference_ok=len(image_rates)==2 and all(item.get("group_rate")==1.0 and item.get("account_rate")==1.0 and item.get("difference")==0.0 for item in image_rates)
claude_account=next((item for item in accounts if int(item.get("id") or 0)==2),None)
claude_account_ok=claude_account is not None and claude_account.get("status")=="active" and claude_account.get("schedulable") is True and int(claude_account.get("group_count") or 0)==1 and "Claude" in str(claude_account.get("name") or "") and "渠道A" in str(claude_account.get("name") or "")
contract={
  "groups":len(groups),"accounts":len(accounts),"active_channels":len(active_channels),"text_channels":len(text_channels),"image_channels":len(image_channels),
  "enabled_monitors":enabled_text_monitors+enabled_image_monitors,"enabled_text_monitors":enabled_text_monitors,"enabled_image_monitors":enabled_image_monitors,"disabled_image_monitors":disabled_image_monitors,"scheduled_monitors":scheduled_monitors,
  "one_group_per_channel":len(active_channels)==12 and all(int(item.get("group_count") or 0)==1 for item in active_channels),
  "one_group_per_account":len(accounts)==12 and all(int(item.get("group_count") or 0)==1 for item in accounts),
  "monitor_schedule_ok":len(monitors)==12 and scheduled_monitors==12,
  "monitor_state_ok":len(text_monitors)==10 and enabled_text_monitors==10 and len(image_monitors)==2 and enabled_image_monitors==0 and disabled_image_monitors==2,
  "text_rate_difference_ok":text_rate_difference_ok,"image_rate_difference_ok":image_rate_difference_ok,"rate_difference_ok":text_rate_difference_ok and image_rate_difference_ok,
  "image_pricing_ok":image_pricing_ok,"claude_account_ok":claude_account_ok,
  "rate_differences":rates,
}
contract["ok"]=contract["groups"]==12 and len(text_groups)==10 and len(image_groups)==2 and contract["accounts"]==12 and contract["active_channels"]==12 and contract["text_channels"]==10 and contract["image_channels"]==2 and contract["one_group_per_channel"] and contract["one_group_per_account"] and contract["monitor_schedule_ok"] and contract["monitor_state_ok"] and contract["rate_difference_ok"] and contract["image_pricing_ok"] and contract["claude_account_ok"]
provider_health=[{"monitor_id":item["id"],"status":item.get("latest_status") or "unknown","last_checked_at":item.get("last_checked_at"),"latency_ms":item.get("latency_ms")} for item in monitors]
public={"home":request("https://jiyu.245334.xyz/"),"models":request("https://jiyu.245334.xyz/v1/models"),"docs_route":request("https://jiyu.245334.xyz/custom/docs"),"docs_content":request("https://jiyu.245334.xyz/api/v1/pages/docs"),"recharge":request("https://jiyu.245334.xyz/custom/recharge-center"),"webhook_no_token":request("https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order",method="POST",data={"orderId":"jiyu-readonly-audit","paid":True})}
public["ok"]=public["home"]["http"]==200 and public["home"]["has_jiyu"] and public["models"]["http"]==401 and public["docs_route"]["http"]==200 and public["docs_content"]["http"] in (200,401) and public["recharge"]["http"]==200 and public["webhook_no_token"]["http"]==401
services={name:service(name) for name in ["sub2api.service","sub2api-redis.service","frist-api.service","apache2.service"]}
services_ok=all(value=="active" for value in services.values())
result={"services":services,"services_ok":services_ok,"config_contract":contract,"provider_health":provider_health,"brand":{"site_name_ok":db.get("site_name")=="JIYU AI"},"inventory":{"redeem_available":int(db.get("redeem_available") or 0),"active_keys":int(db.get("active_keys") or 0),"usage_logs":int(db.get("usage_logs") or 0)},"public":public}
result["ok"]=services_ok and contract["ok"] and result["brand"]["site_name_ok"] and public["ok"]
print(json.dumps(result,ensure_ascii=False))
`;
  try {
    const data = JSON.parse(execFileSync('ssh', ['oracle-arm1', 'python3', '-'], {
      input: remotePython,
      encoding: 'utf8',
      maxBuffer: 1024 * 1024,
    }).trim());
    return data.ok ? pass(data) : fail('JIYU AI 生产合同未全部满足', data);
  } catch (error) {
    return fail('无法完成 JIYU AI 生产审计', { error: String(error.message || error).slice(0, 180) });
  }
}

const realOrderProof = auditRealOrderProof();
const checks = {
  chromeBookmarks: auditChromeBookmarks(),
  localXianyu: auditLocalXianyu(),
  localEnv: auditLocalEnvPresence(),
  localXianyuGui: await auditLocalXianyuGui(),
  realXianyuOrderProof: realOrderProof,
  oracle: auditOracle(),
};
const softwareReady = checks.localXianyu.ok && checks.localEnv.ok && checks.localXianyuGui.ok && checks.realXianyuOrderProof.ok;
const ok = softwareReady && checks.chromeBookmarks.ok && checks.oracle.ok;
const result = {
  schema_version: SCHEMA_VERSION,
  ok,
  software_ready: softwareReady,
  mode: requireRealOrder ? 'read-only+require-real-order' : 'read-only',
  checks,
  nextHumanGate: '保持闲鱼助手暂停；完成 JIYU 商品、库存和付款闭环后再单独恢复公开售卖。',
};

if (jsonOnly) {
  console.log(JSON.stringify(result, null, 2));
} else {
  console.log(`JIYU AI 生产闭环审计 v2: ${ok ? 'PASS' : 'FAIL'} (${result.mode})`);
  console.log(`- 闲鱼软件闭环: ${softwareReady ? 'PASS' : 'FAIL'}`);
  console.log(`- 生产配置合同: ${checks.oracle.config_contract?.ok ? 'PASS' : 'FAIL'}（分组 ${checks.oracle.config_contract?.groups || 0}/12，渠道 ${checks.oracle.config_contract?.active_channels || 0}/12，文本监控 ${checks.oracle.config_contract?.enabled_text_monitors || 0}/10，生图监控 ${checks.oracle.config_contract?.enabled_image_monitors || 0}/2，按真实异常禁用）`);
  console.log(`- 监控调度合同: ${checks.oracle.config_contract?.scheduled_monitors || 0}/12（300 秒周期，±30 秒抖动）`);
  console.log(`- 真实上游状态: ${JSON.stringify(checks.oracle.provider_health || [])}`);
  console.log(`- 公开售卖策略: ${result.nextHumanGate}`);
}

process.exit(ok ? 0 : 1);

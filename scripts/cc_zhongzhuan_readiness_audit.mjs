#!/usr/bin/env node
/**
 * CC中转生产内测闭环审计脚本。
 *
 * 默认只读检查；加 --webhook-smoke 时会在 Oracle 内网调用一次低权限闲鱼已付款 webhook，
 * 随后删除测试履约并把测试卡密恢复为 unused。脚本只输出数量/状态，不输出 token、卡密或用户 Key。
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const REQUIRED_BOOKMARKS = [
  ['CC中转本机操作台', 'http://127.0.0.1:18800/'],
  ['CC中转用户主站', 'https://jiyu.245334.xyz/'],
];

const STRICT_BUYER_CHAIN_BASELINE = {
  capturedAt: '2026-07-05T19:30:00Z',
  redeemedRedemptions: 2,
  activeTokens: 1,
  modelLogs: 128,
};

const args = new Set(process.argv.slice(2));
const runWebhookSmoke = args.has('--webhook-smoke');
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
  } catch (error) {
    return null;
  }
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

function httpJson(url, headers = {}) {
  return new Promise((resolve) => {
    const req = http.get(url, { headers, timeout: 5000 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        let json = null;
        try {
          json = JSON.parse(body);
        } catch (error) {
          json = null;
        }
        resolve({ http: res.statusCode || 0, json, body: body.slice(0, 200) });
      });
    });
    req.on('timeout', () => {
      req.destroy(new Error('timeout'));
    });
    req.on('error', (error) => {
      resolve({ http: 0, error: String(error.message || error).slice(0, 160) });
    });
  });
}

function flattenBookmarkFolders(node, folders = []) {
  if (!node || typeof node !== 'object') return folders;
  if (node.type === 'folder' && node.name === 'CC中转运营') folders.push(node);
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
  if (profiles.length === 0) return fail('没有找到 Chrome Profile');

  const profileResults = profiles.map((profile) => {
    const bookmarks = safeJsonRead(path.join(base, profile, 'Bookmarks'));
    const prefs = safeJsonRead(path.join(base, profile, 'Preferences'));
    const folders = flattenBookmarkFolders(bookmarks?.roots || {});
    const folder = folders[0];
    const urls = new Set((folder?.children || []).filter((item) => item.type === 'url').map((item) => item.url));
    const missing = REQUIRED_BOOKMARKS.filter(([, url]) => !urls.has(url)).map(([name]) => name);
    return {
      profile,
      folderCount: folders.length,
      missing,
      bookmarkBarVisible: Boolean(
        prefs?.bookmark_bar?.show_on_all_tabs || prefs?.bookmark_bar?.show_on_new_tab_page,
      ),
    };
  });
  const bad = profileResults.filter((item) => item.folderCount < 1 || item.missing.length || !item.bookmarkBarVisible);
  return bad.length ? fail('Chrome 书签文件夹不完整', { profiles: profileResults }) : pass({ profiles: profileResults });
}

function runLocal(command, args = [], options = {}) {
  return execFileSync(command, args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  }).trim();
}

function auditLocalXianyu() {
  let launchctl = '';
  try {
    launchctl = runLocal('launchctl', ['list']);
  } catch (error) {
    return fail('launchctl 不可用', { error: String(error.message || error).slice(0, 160) });
  }
  const line = launchctl.split('\n').find((row) => row.includes('ai.openclaw.xianyu')) || '';
  const running = /^\s*\d+\s+/.test(line);
  const logPath = path.join(process.cwd(), 'packages/clawbot/logs/xianyu.log');
  const log = fs.existsSync(logPath) ? fs.readFileSync(logPath, 'utf8') : '';
  const websocketRegistered = log.includes('闲鱼 WebSocket 连接注册完成');
  const telegramUrlLeaks = (log.match(/https:\/\/api\.telegram\.org\/bot[A-Za-z0-9_:-]+/g) || []).length;
  return running && websocketRegistered && telegramUrlLeaks === 0
    ? pass({ launchctl: line.trim(), websocketRegistered, telegramUrlLeaks })
    : fail('本机闲鱼助手运行态异常', { launchctl: line.trim(), websocketRegistered, telegramUrlLeaks });
}

function auditLocalEnvPresence() {
  const envPath = path.join(process.cwd(), 'packages/clawbot/config/.env');
  if (!fs.existsSync(envPath)) return fail('本机 packages/clawbot/config/.env 不存在');
  const env = fs.readFileSync(envPath, 'utf8');
  const required = [
    'CC_XIANYU_AUTO_SHIP_ENABLED',
    'CC_XIANYU_WEBHOOK_URL',
    'CC_XIANYU_WEBHOOK_TOKEN',
    'XIANYU_COOKIES',
  ];
  const presence = Object.fromEntries(required.map((key) => [key, new RegExp(`^${key}=.+`, 'm').test(env)]));
  const missing = Object.entries(presence).filter(([, present]) => !present).map(([key]) => key);
  return missing.length ? fail('本机闲鱼自动发货配置缺失', { presence }) : pass({ presence });
}

async function auditLocalXianyuGui() {
  const envPath = path.join(process.cwd(), 'packages/clawbot/config/.env');
  const env = parseEnvFile(envPath);
  const token = env.OPENCLAW_API_TOKEN || '';
  if (!token) return fail('本机 OPENCLAW_API_TOKEN 缺失，无法审计闲鱼 GUI');

  const root = await httpJson('http://127.0.0.1:18800/');
  const noToken = await httpJson('http://127.0.0.1:18800/api/status');
  const status = await httpJson('http://127.0.0.1:18800/api/status', { 'X-API-Token': token });
  const data = status.json || {};
  const ccAutoShip = data.cc_auto_ship || {};
  const ccShipments = data.cc_shipments || {};
  const ok = (
    root.http === 200 &&
    noToken.http === 401 &&
    status.http === 200 &&
    data.ws_connected === true &&
    data.cookie_ok === true &&
    ccAutoShip.configured === true &&
    Number(ccShipments.pending_rescue || 0) === 0
  );
  const detail = {
    rootHttp: root.http,
    apiNoTokenHttp: noToken.http,
    apiWithTokenHttp: status.http,
    wsConnected: data.ws_connected === true,
    cookieOk: data.cookie_ok === true,
    ccAutoShip: {
      enabled: ccAutoShip.enabled === true,
      configured: ccAutoShip.configured === true,
      endpoint: ccAutoShip.endpoint || '',
      tokenPresent: ccAutoShip.token_present === true,
      delaySeconds: ccAutoShip.delay_seconds,
    },
    ccShipments: {
      total: Number(ccShipments.total || 0),
      sent: Number(ccShipments.sent || 0),
      pendingRescue: Number(ccShipments.pending_rescue || 0),
      resolved: Number(ccShipments.resolved || 0),
    },
  };
  return ok ? pass(detail) : fail('本机闲鱼 GUI 自动发货状态异常', detail);
}

function auditRealXianyuOrderProof() {
  const script = String.raw`
import hashlib, json, sqlite3
from pathlib import Path

db = Path("packages/clawbot/data/xianyu_chat.db")
result = {"required": __REQUIRED__, "dbExists": db.exists(), "sentRealOrders": 0, "pendingRescue": 0, "latest": [], "orderIdHashes": []}
if db.exists():
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        result["sentRealOrders"] = cur.execute(
            "SELECT COUNT(*) FROM cc_shipments WHERE status='message_sent' AND order_id LIKE 'xy_oid_%'"
        ).fetchone()[0]
        result["pendingRescue"] = cur.execute(
            "SELECT COUNT(*) FROM cc_shipments WHERE status IN ('browser_delivery_claimed','message_send_failed','webhook_failed','missing_delivery_message','exception','manual_delivery_ready')"
        ).fetchone()[0]
        rows = cur.execute(
            "SELECT id, order_id, status, created_at, updated_at FROM cc_shipments ORDER BY id DESC LIMIT 5"
        ).fetchall()
        order_rows = cur.execute(
            "SELECT order_id FROM cc_shipments WHERE status='message_sent' AND order_id LIKE 'xy_oid_%' ORDER BY id DESC LIMIT 20"
        ).fetchall()
        result["orderIdHashes"] = [
            hashlib.sha256(str(row[0]).encode()).hexdigest()
            for row in order_rows
            if row and row[0]
        ]
        result["latest"] = [
            {"id": r[0], "orderIdPrefix": str(r[1])[:10], "status": r[2], "createdAt": r[3], "updatedAt": r[4]}
            for r in rows
        ]
        conn.close()
    except Exception as exc:
        result["error"] = str(exc)[:160]
print(json.dumps(result, ensure_ascii=False))
`.replace('__REQUIRED__', requireRealOrder ? 'True' : 'False');
  try {
    const output = runLocal('python3', ['-c', script]);
    const data = JSON.parse(output || '{}');
    const hasProof = Number(data.sentRealOrders || 0) > 0 && Number(data.pendingRescue || 0) === 0;
    if (requireRealOrder && !hasProof) {
      return fail('尚未发现真实闲鱼已付款自动发货记录；请发布商品后跑 1 单小额实单再复验', {
        ...data,
        hasProof,
      });
    }
    return pass({ ...data, hasProof });
  } catch (error) {
    return requireRealOrder
      ? fail('无法读取真实闲鱼实单验收记录', { error: String(error.message || error).slice(0, 160) })
      : pass({ required: false, hasProof: false, error: String(error.message || error).slice(0, 160) });
  }
}

function auditOracle(realOrderProof = {}) {
  const realOrderHashes = Array.isArray(realOrderProof.orderIdHashes) ? realOrderProof.orderIdHashes : [];
  const remotePython = String.raw`
from pathlib import Path
import json, sqlite3, subprocess, urllib.request, urllib.error, time, os, re, base64, hmac, hashlib, struct

def status_code(url, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    merged_headers={
        "user-agent": "CC-Zhongzhuan-Readiness-Audit/1.0",
        "accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=data, method=method, headers=merged_headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0

def http_probe(url):
    req = urllib.request.Request(
        url,
        headers={
            "user-agent": "CC-Zhongzhuan-Readiness-Audit/1.0",
            "accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        },
    )
    body = ""
    status = 0
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status = r.status
            body = r.read(200000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read(200000).decode("utf-8", "ignore")
        except Exception:
            body = ""
    except Exception as exc:
        return {"http": 0, "ok": False, "error": str(exc)[:120]}
    lowered = body.lower()
    has_cc_switch_text = "cc switch" in lowered
    has_ccswitch_marker = "ccswitch" in lowered
    has_import_link_marker = "data-import-link" in lowered
    return {
        "http": int(status or 0),
        "ok": status == 200 and has_cc_switch_text and has_ccswitch_marker and has_import_link_marker,
        "has_cc_switch_text": has_cc_switch_text,
        "has_ccswitch_marker": has_ccswitch_marker,
        "has_import_link_marker": has_import_link_marker,
    }

def load_env(path):
    vals={}
    p=Path(path)
    if not p.exists():
        return vals
    for line in p.read_text(errors="ignore").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,v=line.split("=",1)
        vals[k.strip()]=v.strip().strip('"').strip("'")
    return vals

def totp(secret):
    s=re.sub(r"\s+", "", secret).upper()
    pad="="*((8-len(s)%8)%8)
    key=base64.b32decode((s+pad).encode(), casefold=True)
    counter=int(time.time()//30)
    msg=struct.pack(">Q", counter)
    digest=hmac.new(key,msg,hashlib.sha1).digest()
    offset=digest[-1]&15
    code=struct.unpack(">I", digest[offset:offset+4])[0]&0x7fffffff
    return str(code%1000000).zfill(6)

def post_json(url, body, headers):
    data=json.dumps(body).encode()
    req=urllib.request.Request(url, data=data, method="POST", headers={"content-type":"application/json", **headers})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.headers, json.loads(r.read().decode() or "{}")

def cleanup_smoke(order_id):
    runtime=Path("/opt/frist-api/data/frist-api/runtime/runtime.json")
    data=json.loads(runtime.read_text(errors="ignore"))
    fulfillment=None
    remaining=[]
    for f in data.get("xianyuFulfillments",[]):
        if f.get("orderId")==order_id:
            fulfillment=f
        else:
            remaining.append(f)
    if fulfillment:
        card_id=fulfillment.get("cardId")
        for card in data.get("redemptionCards",[]):
            if card.get("id")==card_id:
                card["status"]="unused"
                for k in ["soldAt","soldOrderId","soldPlatform","soldBuyerHint","fulfillmentId","deliveredAt"]:
                    card[k]=""
                card["updatedAt"]=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["xianyuFulfillments"]=remaining
        data["events"]=[e for e in data.get("events",[]) if e.get("orderId")!=order_id]
        tmp=runtime.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(runtime)
    return bool(fulfillment)

result={}
services={}
for svc in ["frist-api.service","openclaw-newapi.service","apache2"]:
    p=subprocess.run(["systemctl","is-active",svc], text=True, capture_output=True)
    services[svc]=p.stdout.strip()
result["services"]=services

runtime=Path("/opt/frist-api/data/frist-api/runtime/runtime.json")
data=json.loads(runtime.read_text(errors="ignore"))
cards=data.get("redemptionCards",[])
cards_by_id={str(card.get("id","")): card for card in cards}
status={}
unused_by_plan={}
for card in cards:
    s=str(card.get("status",""))
    status[s]=status.get(s,0)+1
    if s=="unused":
        key=f"{card.get('plan','')}|quotaUsd={card.get('quotaUsd','')}|source={card.get('source','')}"
        unused_by_plan[key]=unused_by_plan.get(key,0)+1
result["runtime"]={"path":str(runtime),"card_status":status,"unused_by_plan":unused_by_plan}

conn=sqlite3.connect("/opt/frist-api/data/newapi/one-api.db")
cur=conn.cursor()
result["newapi"]={
    "redemptions_enabled":cur.execute("select count(*) from redemptions where status=1").fetchone()[0],
    "channels_enabled":cur.execute("select count(*) from channels where status=1").fetchone()[0],
    "tokens_not_deleted":cur.execute("select count(*) from tokens where deleted_at is null").fetchone()[0],
}
redeemed_redemptions=cur.execute("select count(*) from redemptions where status<>1 or used_user_id>0 or redeemed_time>0").fetchone()[0]
active_tokens=cur.execute("select count(*) from tokens where status=1 and deleted_at is null").fetchone()[0]
model_logs=cur.execute("select count(*) from logs where model_name is not null and model_name<>''").fetchone()[0]
result["buyer_chain_proof"]={
    "baseline": __BUYER_BASELINE__,
    "redeemed_redemptions": redeemed_redemptions,
    "active_tokens": active_tokens,
    "model_logs": model_logs,
    "redeemed_delta": redeemed_redemptions - int(__BASELINE_REDEEMED__),
    "active_token_delta": active_tokens - int(__BASELINE_TOKENS__),
    "model_log_delta": model_logs - int(__BASELINE_LOGS__),
}

real_order_hashes=set(__REAL_ORDER_HASHES__)
redeemed_by_hash={}
for key, status_value, redeemed_time, used_user_id in cur.execute(
    "select coalesce(key,''), coalesce(status,1), coalesce(redeemed_time,0), coalesce(used_user_id,0) from redemptions where coalesce(redeemed_time,0)>0 or coalesce(used_user_id,0)>0 or coalesce(status,1)<>1"
):
    normalized=str(key or "").strip().upper()
    if not normalized:
        continue
    redeemed_by_hash["sha256:"+hashlib.sha256(normalized.encode()).hexdigest()]={
        "status": int(status_value or 0),
        "redeemed_time": int(redeemed_time or 0),
        "used_user_id": int(used_user_id or 0),
    }

strict_matches=[]
for fulfillment in data.get("xianyuFulfillments",[]):
    order_id=str(fulfillment.get("orderId",""))
    if not order_id.startswith("xy_"):
        continue
    order_hash=hashlib.sha256(order_id.encode()).hexdigest()
    if real_order_hashes and order_hash not in real_order_hashes:
        continue
    card=cards_by_id.get(str(fulfillment.get("cardId",""))) or {}
    redemption=redeemed_by_hash.get(str(card.get("codeHash","")))
    used_user_id=int((redemption or {}).get("used_user_id") or 0)
    redeemed_time=int((redemption or {}).get("redeemed_time") or 0)
    active_token_count=0
    model_log_count=0
    if used_user_id > 0:
        active_token_count=cur.execute(
            "select count(*) from tokens where user_id=? and status=1 and deleted_at is null",
            (used_user_id,),
        ).fetchone()[0]
        model_log_count=cur.execute(
            "select count(*) from logs where user_id=? and model_name is not null and model_name<>'' and created_at>=?",
            (used_user_id, max(0, redeemed_time - 300)),
        ).fetchone()[0]
    ready=(
        str(fulfillment.get("status","")) == "redeemed"
        and str(card.get("status","")) == "redeemed"
        and redemption is not None
        and used_user_id > 0
        and active_token_count > 0
        and model_log_count > 0
    )
    strict_matches.append({
        "orderIdPrefix": order_id[:10],
        "orderIdHash": order_hash,
        "fulfillmentStatus": str(fulfillment.get("status","")),
        "cardStatus": str(card.get("status","")),
        "newApiRedeemed": redemption is not None,
        "usedUserIdPresent": used_user_id > 0,
        "activeTokens": int(active_token_count),
        "modelLogsAfterRedeem": int(model_log_count),
        "ready": bool(ready),
    })
result["real_order_chain_proof"]={
    "required": __REQUIRE_REAL_ORDER__,
    "localOrderHashCount": len(real_order_hashes),
    "matchedOrders": len(strict_matches),
    "readyOrders": sum(1 for item in strict_matches if item.get("ready")),
    "latestMatches": strict_matches[:5],
}
conn.close()

ccswitch_entry=http_probe("https://frist-api-oracle.245334.xyz/")
result["public"]={
    "main_http":status_code("https://jiyu.245334.xyz/"),
    "models_no_auth_http":status_code("https://jiyu.245334.xyz/v1/models"),
    "webhook_no_token_http":status_code(
        "https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order",
        method="POST",
        body={"orderId":"cc-audit-no-token","status":"等待卖家发货","paid":True},
        headers={"content-type":"application/json"},
    ),
    "ccswitch_entry":ccswitch_entry,
}

if __RUN_WEBHOOK_SMOKE__:
    env=load_env("/etc/frist-api/frist-api.env")
    token=env.get("FRIST_API_XIANYU_WEBHOOK_TOKEN","")
    order_id=f"cc-audit-smoke-{int(time.time())}"
    smoke={"attempted": bool(token), "orderId": order_id}
    if token:
        try:
            _, body=post_json(
                "http://127.0.0.1:3180/api/ops/xianyu/paid-order",
                {"orderId":order_id,"status":"等待卖家发货","paid":True,"productTitle":"CC中转 审计冒烟","buyerHint":"audit","note":"cc-readiness-audit-cleanup"},
                {"x-cc-xianyu-token":token},
            )
            smoke.update({
                "ok":body.get("ok"),
                "autoShip":body.get("autoShip"),
                "fulfillmentStatus":(body.get("fulfillment") or {}).get("status"),
                "cardPlan":(body.get("card") or {}).get("plan"),
                "messageGenerated":bool(body.get("deliveryMessage")),
            })
        except urllib.error.HTTPError as e:
            smoke.update({"http":e.code, "error":e.read().decode(errors="ignore")[:160]})
        finally:
            smoke["cleanup_done"]=cleanup_smoke(order_id)
            fresh=json.loads(runtime.read_text(errors="ignore"))
            smoke["unused_after_cleanup"]=sum(1 for c in fresh.get("redemptionCards",[]) if c.get("status")=="unused")
    result["webhook_smoke"]=smoke

print(json.dumps(result, ensure_ascii=False))
  `
    .replace('__RUN_WEBHOOK_SMOKE__', runWebhookSmoke ? 'True' : 'False')
    .replace('__REQUIRE_REAL_ORDER__', requireRealOrder ? 'True' : 'False')
    .replace('__REAL_ORDER_HASHES__', JSON.stringify(realOrderHashes))
    .replace('__BUYER_BASELINE__', JSON.stringify(STRICT_BUYER_CHAIN_BASELINE))
    .replace('__BASELINE_REDEEMED__', String(STRICT_BUYER_CHAIN_BASELINE.redeemedRedemptions))
    .replace('__BASELINE_TOKENS__', String(STRICT_BUYER_CHAIN_BASELINE.activeTokens))
    .replace('__BASELINE_LOGS__', String(STRICT_BUYER_CHAIN_BASELINE.modelLogs));

  try {
    const output = execFileSync('ssh', ['oracle-arm1', 'python3', '-'], {
      input: remotePython,
      encoding: 'utf8',
      maxBuffer: 1024 * 1024,
    }).trim();
    const data = JSON.parse(output);
    const serviceOk = Object.values(data.services || {}).every((value) => value === 'active');
    const inventoryOk = Number(data.runtime?.card_status?.unused || 0) > 0 && Number(data.newapi?.redemptions_enabled || 0) > 0;
    const ccswitchEntry = data.public?.ccswitch_entry || {};
    const publicOk = data.public?.main_http === 200 && data.public?.models_no_auth_http === 401 && data.public?.webhook_no_token_http === 401 && ccswitchEntry.ok === true;
    const buyerChain = data.buyer_chain_proof || {};
    const realOrderChain = data.real_order_chain_proof || {};
    const realOrderChainOk = !requireRealOrder || Number(realOrderChain.readyOrders || 0) > 0;
    const buyerChainOk = !requireRealOrder || (
      Number(buyerChain.redeemed_delta || 0) > 0 &&
      Number(buyerChain.active_token_delta || 0) > 0 &&
      Number(buyerChain.model_log_delta || 0) > 0 &&
      realOrderChainOk
    );
    const smoke = data.webhook_smoke;
    const smokeOk = !runWebhookSmoke || (
      smoke?.ok === true &&
      smoke?.autoShip === true &&
      smoke?.fulfillmentStatus === 'delivered' &&
      smoke?.messageGenerated === true &&
      smoke?.cleanup_done === true &&
      Number(smoke?.unused_after_cleanup || 0) > 0
    );
    return serviceOk && inventoryOk && publicOk && smokeOk && buyerChainOk
      ? pass(data)
      : fail(
        buyerChainOk ? 'Oracle 生产闭环检查未通过' : '买家站内闭环尚未超过正式验收基线',
        data,
      );
  } catch (error) {
    return fail('无法完成 Oracle 审计', { error: String(error.message || error).slice(0, 240) });
  }
}

const realXianyuOrderProof = auditRealXianyuOrderProof();
const checks = {
  chromeBookmarks: auditChromeBookmarks(),
  localXianyu: auditLocalXianyu(),
  localEnv: auditLocalEnvPresence(),
  localXianyuGui: await auditLocalXianyuGui(),
  realXianyuOrderProof,
  oracle: auditOracle(realXianyuOrderProof),
};

const ok = Object.values(checks).every((item) => item.ok);
const result = {
  ok,
  mode: [
    runWebhookSmoke ? 'read-write-webhook-smoke-with-cleanup' : 'read-only',
    requireRealOrder ? 'require-real-order' : '',
  ].filter(Boolean).join('+'),
  checks,
  nextHumanGate: '发布闲鱼商品后跑 1 单小额真实付款，确认平台真实消息发送稳定。',
};

if (jsonOnly) {
  console.log(JSON.stringify(result, null, 2));
} else {
  console.log(`CC中转生产闭环审计: ${ok ? 'PASS' : 'FAIL'} (${result.mode})`);
  for (const [name, check] of Object.entries(checks)) {
    console.log(`- ${name}: ${check.ok ? 'PASS' : 'FAIL'}${check.message ? ` — ${check.message}` : ''}`);
  }
  const inventory = checks.oracle?.runtime?.card_status || checks.oracle?.card_status || checks.oracle?.runtime?.card_status;
  if (checks.oracle.ok) {
    console.log(`- 生产库存: unused=${checks.oracle.runtime.card_status.unused || 0}, New-API enabled redemptions=${checks.oracle.newapi.redemptions_enabled}, channels=${checks.oracle.newapi.channels_enabled}`);
  }
  if (checks.oracle?.buyer_chain_proof) {
    const buyer = checks.oracle.buyer_chain_proof;
    console.log(`- 买家站内闭环证明: redeemedΔ=${buyer.redeemed_delta}, tokenΔ=${buyer.active_token_delta}, modelLogΔ=${buyer.model_log_delta}${requireRealOrder ? '（本次强制要求均 > 0）' : '（默认不强制）'}`);
  }
  if (checks.oracle?.real_order_chain_proof) {
    const chain = checks.oracle.real_order_chain_proof;
    console.log(`- 同一真实订单闭环证明: localOrderHashes=${chain.localOrderHashCount}, matchedOrders=${chain.matchedOrders}, readyOrders=${chain.readyOrders}${requireRealOrder ? '（本次强制要求 > 0）' : '（默认不强制）'}`);
  }
  if (runWebhookSmoke && checks.oracle.webhook_smoke) {
    console.log(`- webhook 冒烟: fulfillment=${checks.oracle.webhook_smoke.fulfillmentStatus}, cleanup=${checks.oracle.webhook_smoke.cleanup_done}, unused_after=${checks.oracle.webhook_smoke.unused_after_cleanup}`);
  }
  if (checks.localXianyuGui.ok) {
    console.log(`- 本机闲鱼 GUI: ws=${checks.localXianyuGui.wsConnected}, cookie=${checks.localXianyuGui.cookieOk}, autoShip=${checks.localXianyuGui.ccAutoShip.configured}, pendingRescue=${checks.localXianyuGui.ccShipments.pendingRescue}`);
  }
  const proof = checks.realXianyuOrderProof;
  if (proof) {
    console.log(`- 真实闲鱼实单证明: ${proof.hasProof ? '已发现' : '未发现'}${proof.required ? '（本次强制要求）' : '（默认不强制）'}, sentRealOrders=${proof.sentRealOrders || 0}, pendingRescue=${proof.pendingRescue || 0}`);
  }
  console.log(`- 人工最终门槛: ${result.nextHumanGate}`);
}

process.exit(ok ? 0 : 1);

"""闲鱼 Web 管理面板 — 搬运自 GuDong2003/xianyu-auto-reply-fix

功能:
- 对话历史查看 (按 chat_id 分组)
- 每日统计 dashboard
- 商品管理 (查看缓存的商品信息)
- 订单列表
- 实时状态 (WebSocket 连接状态、Cookie 健康)
- Prompt 热更新

搬运适配:
- 复用现有 XianyuContextManager (SQLite)
- 复用现有 XianyuReplyBot (prompt reload)
- 不引入新数据库，零额外依赖 (FastAPI 已在 kiro-gateway 中使用)
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from src.utils import now_et

logger = logging.getLogger(__name__)

app = FastAPI(title="闲鱼管理面板", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 延迟初始化 (由 start_admin_server 注入)
_ctx = None  # XianyuContextManager
_bot = None  # XianyuReplyBot
_live = None  # XianyuLive


def _get_ctx():
    if not _ctx:
        raise HTTPException(503, "闲鱼服务未启动")
    return _ctx


# ============================================================
# Dashboard
# ============================================================

@app.get("/api/dashboard")
def dashboard(date: str = ""):
    ctx = _get_ctx()
    if not date:
        date = now_et().strftime("%Y-%m-%d")
    stats = ctx.daily_stats(date)

    # 最近 7 天趋势
    trend = []
    for i in range(6, -1, -1):
        d = (now_et() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend.append(ctx.daily_stats(d))

    return {"today": stats, "trend": trend}


# ============================================================
# 对话管理
# ============================================================

@app.get("/api/chats")
def list_chats(limit: int = Query(50, le=200)):
    """列出最近活跃的对话"""
    ctx = _get_ctx()
    with ctx._conn() as c:
        rows = c.execute("""
            SELECT chat_id, MAX(ts) as last_ts, COUNT(*) as msg_count,
                   (SELECT content FROM messages m2 WHERE m2.chat_id=m.chat_id ORDER BY id DESC LIMIT 1) as last_msg
            FROM messages m
            GROUP BY chat_id
            ORDER BY last_ts DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [
        {"chat_id": r[0], "last_ts": r[1], "msg_count": r[2], "last_msg": r[3][:100] if r[3] else ""}
        for r in rows
    ]


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, limit: int = Query(100, le=500)):
    """获取某个对话的消息历史"""
    ctx = _get_ctx()
    with ctx._conn() as c:
        rows = c.execute(
            "SELECT role, content, ts FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    rows.reverse()
    bargain = ctx.get_bargain_count(chat_id)
    return {
        "chat_id": chat_id,
        "bargain_count": bargain,
        "messages": [{"role": r[0], "content": r[1], "ts": r[2]} for r in rows],
    }


# ============================================================
# 商品管理
# ============================================================

@app.get("/api/items")
def list_items():
    ctx = _get_ctx()
    with ctx._conn() as c:
        rows = c.execute("SELECT item_id, data, updated FROM items ORDER BY updated DESC").fetchall()
    items = []
    for r in rows:
        try:
            data = json.loads(r[1])
        except Exception:
            data = {}
        items.append({"item_id": r[0], "title": data.get("title", ""), "price": data.get("price", ""), "updated": r[2]})
    return items


# ============================================================
# 订单管理
# ============================================================

@app.get("/api/orders")
def list_orders(date: str = "", limit: int = Query(50, le=200)):
    ctx = _get_ctx()
    with ctx._conn() as c:
        if date:
            rows = c.execute(
                "SELECT id, chat_id, user_id, item_id, status, ts, notified FROM orders WHERE ts LIKE ? ORDER BY id DESC LIMIT ?",
                (f"{date}%", limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, chat_id, user_id, item_id, status, ts, notified FROM orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [
        {"id": r[0], "chat_id": r[1], "user_id": r[2], "item_id": r[3],
         "status": r[4], "ts": r[5], "notified": bool(r[6])}
        for r in rows
    ]


# ============================================================
# 咨询追踪
# ============================================================

@app.get("/api/consultations")
def list_consultations(date: str = "", limit: int = Query(50, le=200)):
    ctx = _get_ctx()
    with ctx._conn() as c:
        if date:
            rows = c.execute(
                "SELECT chat_id, user_id, user_name, item_id, first_msg, first_ts, last_ts, msg_count, converted "
                "FROM consultations WHERE first_ts LIKE ? ORDER BY last_ts DESC LIMIT ?",
                (f"{date}%", limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT chat_id, user_id, user_name, item_id, first_msg, first_ts, last_ts, msg_count, converted "
                "FROM consultations ORDER BY last_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [
        {"chat_id": r[0], "user_id": r[1], "user_name": r[2], "item_id": r[3],
         "first_msg": r[4], "first_ts": r[5], "last_ts": r[6],
         "msg_count": r[7], "converted": bool(r[8])}
        for r in rows
    ]


# ============================================================
# 系统状态
# ============================================================

@app.get("/api/status")
def system_status():
    status = {"service": "running", "ws_connected": False, "cookie_ok": False}
    if _live:
        status["ws_connected"] = _live.ws is not None and _live.ws.open if hasattr(_live, 'ws') and _live.ws else False
        status["cookie_ok"] = getattr(_live, '_cookie_ok', False)
        status["last_heartbeat"] = getattr(_live, 'last_hb_resp', 0)
        status["token_age_s"] = int(
            (now_et().timestamp() - getattr(_live, 'token_ts', 0))
        ) if getattr(_live, 'token_ts', 0) > 0 else -1
        status["manual_chats"] = len(getattr(_live, 'manual_chats', {}))
    return status


# ============================================================
# Prompt 管理
# ============================================================

PROMPT_DIR = Path(__file__).parent / "prompts"


@app.get("/api/prompts")
def list_prompts():
    prompts = {}
    for f in PROMPT_DIR.glob("*.txt"):
        prompts[f.stem] = f.read_text(encoding="utf-8")
    return prompts


class PromptUpdate(BaseModel):
    name: str
    content: str


@app.post("/api/prompts")
def update_prompt(req: PromptUpdate):
    path = PROMPT_DIR / f"{req.name}.txt"
    if not path.exists():
        raise HTTPException(404, f"Prompt {req.name} not found")
    path.write_text(req.content, encoding="utf-8")
    # 热更新 bot prompts
    if _bot:
        _bot.reload_prompts()
    return {"ok": True, "name": req.name}


# ============================================================
# 前端页面 (内嵌极简 HTML)
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>闲鱼管理面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f5f5f5;padding:20px}
h1{font-size:24px;margin-bottom:20px;color:#333}
.card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.card h2{font-size:16px;color:#666;margin-bottom:12px}
.stat{display:inline-block;text-align:center;padding:8px 16px}
.stat .num{font-size:28px;font-weight:bold;color:#1890ff}
.stat .label{font-size:12px;color:#999}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #eee}
th{background:#fafafa;color:#666}
.status{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status.ok{background:#52c41a}.status.err{background:#ff4d4f}
#chats,#orders{max-height:400px;overflow-y:auto}
</style></head><body>
<h1>🦞 闲鱼管理面板</h1>
<div class="card" id="dashboard"><h2>今日概览</h2><div id="stats">加载中...</div></div>
<div class="card"><h2>系统状态</h2><div id="sys-status">加载中...</div></div>
<div class="card"><h2>最近对话</h2><div id="chats">加载中...</div></div>
<div class="card"><h2>最近订单</h2><div id="orders">加载中...</div></div>
<script>
async function load(){
  const [dash,status,chats,orders]=await Promise.all([
    fetch('/api/dashboard').then(r=>r.json()),
    fetch('/api/status').then(r=>r.json()),
    fetch('/api/chats?limit=20').then(r=>r.json()),
    fetch('/api/orders?limit=20').then(r=>r.json()),
  ]);
  const t=dash.today;
  document.getElementById('stats').innerHTML=
    `<div class="stat"><div class="num">${t.consultations}</div><div class="label">咨询</div></div>`+
    `<div class="stat"><div class="num">${t.messages}</div><div class="label">消息</div></div>`+
    `<div class="stat"><div class="num">${t.orders}</div><div class="label">订单</div></div>`+
    `<div class="stat"><div class="num">${t.paid}</div><div class="label">付款</div></div>`+
    `<div class="stat"><div class="num">${t.conversion_rate}</div><div class="label">转化率</div></div>`;
  const ws=status.ws_connected,ck=status.cookie_ok;
  document.getElementById('sys-status').innerHTML=
    `<span class="status ${ws?'ok':'err'}"></span>WebSocket: ${ws?'已连接':'断开'} &nbsp;`+
    `<span class="status ${ck?'ok':'err'}"></span>Cookie: ${ck?'正常':'异常'} &nbsp;`+
    `人工接管: ${status.manual_chats||0} 个`;
  let ch='<table><tr><th>对话ID</th><th>消息数</th><th>最后消息</th><th>时间</th></tr>';
  chats.forEach(c=>{ch+=`<tr><td>${c.chat_id.slice(0,12)}...</td><td>${c.msg_count}</td><td>${c.last_msg.slice(0,40)}</td><td>${c.last_ts||''}</td></tr>`});
  document.getElementById('chats').innerHTML=ch+'</table>';
  let od='<table><tr><th>ID</th><th>状态</th><th>商品</th><th>时间</th></tr>';
  orders.forEach(o=>{od+=`<tr><td>${o.id}</td><td>${o.status}</td><td>${o.item_id.slice(0,12)}</td><td>${o.ts||''}</td></tr>`});
  document.getElementById('orders').innerHTML=od+'</table>';
}
load();setInterval(load,30000);
</script></body></html>"""


# ============================================================
# 启动函数
# ============================================================

def start_admin_server(
    ctx_manager,
    reply_bot=None,
    live_instance=None,
    host: str = "0.0.0.0",
    port: int = 18800,
):
    """启动闲鱼管理面板 (在独立线程中运行)"""
    global _ctx, _bot, _live
    _ctx = ctx_manager
    _bot = reply_bot
    _live = live_instance

    import threading
    import uvicorn

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True, name="xianyu-admin")
    t.start()
    logger.info(f"[XianyuAdmin] 管理面板已启动: http://{host}:{port}")
    return t

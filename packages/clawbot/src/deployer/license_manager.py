"""License 管理 — 账号验证 + 防复制 + 设备绑定"""
import hashlib
import json
import os
import platform
import secrets
import sqlite3
import time
import uuid
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "deploy_licenses.db")


def _machine_fingerprint() -> str:
    """生成设备指纹：MAC + hostname + platform"""
    raw = f"{uuid.getnode()}:{platform.node()}:{platform.system()}:{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class LicenseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                xianyu_order_id TEXT DEFAULT '',
                machine_id TEXT DEFAULT '',
                max_devices INTEGER DEFAULT 1,
                bound_devices TEXT DEFAULT '[]',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT,
                last_used TEXT,
                deploy_count INTEGER DEFAULT 0,
                notes TEXT DEFAULT ''
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS deploy_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                action TEXT NOT NULL,
                ip_addr TEXT DEFAULT '',
                os_info TEXT DEFAULT '',
                ts TEXT DEFAULT (datetime('now'))
            )""")

    # ---- 管理端 ----
    def create_license(self, username: str, password: str, xianyu_order_id: str = "",
                       max_devices: int = 1, days: int = 365, notes: str = "") -> str:
        key = f"OC-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        expires = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + days * 86400))
        with self._conn() as c:
            c.execute(
                "INSERT INTO licenses(license_key,username,password_hash,xianyu_order_id,max_devices,expires_at,notes) "
                "VALUES(?,?,?,?,?,?,?)",
                (key, username, pw_hash, xianyu_order_id, max_devices, expires, notes),
            )
        logger.info(f"License 创建: {key} -> {username} (设备上限: {max_devices}, 有效期: {days}天)")
        return key

    def list_licenses(self) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT license_key,username,status,max_devices,bound_devices,deploy_count,expires_at,created_at FROM licenses"
            ).fetchall()
        return [{"key": r[0], "user": r[1], "status": r[2], "max_devices": r[3],
                 "bound": json.loads(r[4]), "deploys": r[5], "expires": r[6], "created": r[7]} for r in rows]

    def revoke_license(self, key: str):
        with self._conn() as c:
            c.execute("UPDATE licenses SET status='revoked' WHERE license_key=?", (key,))
        logger.info(f"License 已吊销: {key}")

    # ---- 客户端验证 ----
    def authenticate(self, username: str, password: str, machine_id: str = "", ip_addr: str = "") -> Dict:
        """客户端登录验证，返回 {ok, license_key, message}"""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as c:
            row = c.execute(
                "SELECT license_key,status,max_devices,bound_devices,expires_at FROM licenses "
                "WHERE username=? AND password_hash=?",
                (username, pw_hash),
            ).fetchone()

        if not row:
            return {"ok": False, "message": "用户名或密码错误"}

        key, status, max_dev, bound_json, expires = row
        if status != "active":
            return {"ok": False, "message": f"License 状态异常: {status}"}
        if expires and expires < time.strftime("%Y-%m-%d %H:%M:%S"):
            return {"ok": False, "message": "License 已过期"}

        bound = json.loads(bound_json)
        if machine_id and machine_id not in bound:
            if len(bound) >= max_dev:
                return {"ok": False, "message": f"设备数已达上限({max_dev})，请联系卖家解绑"}
            bound.append(machine_id)
            with self._conn() as c:
                c.execute("UPDATE licenses SET bound_devices=? WHERE license_key=?",
                          (json.dumps(bound), key))

        # 记录日志
        with self._conn() as c:
            c.execute("UPDATE licenses SET last_used=datetime('now'), deploy_count=deploy_count+1 WHERE license_key=?", (key,))
            c.execute("INSERT INTO deploy_logs(license_key,machine_id,action,ip_addr,os_info) VALUES(?,?,?,?,?)",
                      (key, machine_id, "auth", ip_addr, f"{platform.system()} {platform.release()}"))

        return {"ok": True, "license_key": key, "message": "验证通过"}

    def verify_device(self, license_key: str, machine_id: str) -> bool:
        """验证设备是否已绑定"""
        with self._conn() as c:
            row = c.execute("SELECT bound_devices,status FROM licenses WHERE license_key=?", (license_key,)).fetchone()
        if not row or row[1] != "active":
            return False
        return machine_id in json.loads(row[0])

"""License 管理 — 账号验证 + 防复制 + 设备绑定 + 离线验证"""
import hashlib
import hmac
import json
import os
import platform
import secrets
import sqlite3
import time
import uuid
import logging
from contextlib import contextmanager
from typing import Optional, Dict

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "deploy_licenses.db")

# 离线验证密钥 — 必须通过环境变量设置，禁止硬编码
_secret_env = os.getenv("OPENCLAW_LICENSE_SECRET")
if not _secret_env:
    raise RuntimeError(
        "OPENCLAW_LICENSE_SECRET environment variable is not set. "
        "The license HMAC secret must be provided via environment variable."
    )
_OFFLINE_SECRET = _secret_env.encode()
logger.info("License HMAC secret loaded from OPENCLAW_LICENSE_SECRET environment variable.")


def _machine_fingerprint() -> str:
    """生成设备指纹：MAC + hostname + platform"""
    raw = f"{uuid.getnode()}:{platform.node()}:{platform.system()}:{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def generate_offline_key(days: int = 365) -> str:
    """生成离线License Key（无需服务器验证）

    格式: OC-<随机8字符>-<过期时间戳hex>-<HMAC签名前8字符>
    例: OC-A1B2C3D4-67890ABC-F1E2D3C4

    安装器用 verify_offline_key() 本地验证，不联网。
    """
    rand_part = secrets.token_hex(4).upper()
    expire_ts = int(time.time()) + days * 86400
    expire_hex = format(expire_ts, "08X")
    payload = f"{rand_part}-{expire_hex}"
    sig = hmac.new(_OFFLINE_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()
    return f"OC-{rand_part}-{expire_hex}-{sig}"


def verify_offline_key(key: str) -> Dict:
    """离线验证License Key（买家端调用，不联网）

    返回: {"ok": bool, "message": str, "expires": str}
    """
    try:
        parts = key.strip().split("-")
        if len(parts) != 4 or parts[0] != "OC":
            return {"ok": False, "message": "License Key 格式无效"}

        _, rand_part, expire_hex, sig = parts
        payload = f"{rand_part}-{expire_hex}"
        expected_sig = hmac.new(_OFFLINE_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()

        if not hmac.compare_digest(sig.upper(), expected_sig):
            return {"ok": False, "message": "License Key 签名无效（可能是伪造的）"}

        expire_ts = int(expire_hex, 16)
        if time.time() > expire_ts:
            expire_str = time.strftime("%Y-%m-%d", time.localtime(expire_ts))
            return {"ok": False, "message": f"License Key 已过期（{expire_str}）"}

        expire_str = time.strftime("%Y-%m-%d", time.localtime(expire_ts))
        return {"ok": True, "message": "验证通过", "expires": expire_str}
    except Exception as e:
        return {"ok": False, "message": f"验证异常: {e}"}


class LicenseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """获取 SQLite 连接 (上下文管理器自动关闭)"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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
        key = generate_offline_key(days=days)
        # 使用 PBKDF2 + 随机盐存储密码哈希，防止彩虹表攻击
        salt = secrets.token_hex(16)
        pw_hash = f"{salt}:{hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()}"
        expires = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + days * 86400))
        with self._conn() as c:
            c.execute(
                "INSERT INTO licenses(license_key,username,password_hash,xianyu_order_id,max_devices,expires_at,notes) "
                "VALUES(?,?,?,?,?,?,?)",
                (key, username, pw_hash, xianyu_order_id, max_devices, expires, notes),
            )
        logger.info(f"License 创建: {key[:4]}...{key[-4:]} -> {username} (设备上限: {max_devices}, 有效期: {days}天)")
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
        logger.info(f"License 已吊销: {key[:4]}...{key[-4:]}")

    # ---- 客户端验证 ----
    def authenticate(self, username: str, password: str, machine_id: str = "", ip_addr: str = "") -> Dict:
        """客户端登录验证，返回 {ok, license_key, message}"""
        # 按用户名查询所有 License，在 Python 侧验证密码（因为加盐后无法在 SQL 里比对）
        with self._conn() as c:
            rows = c.execute(
                "SELECT license_key,password_hash,status,max_devices,bound_devices,expires_at FROM licenses "
                "WHERE username=?",
                (username,),
            ).fetchall()

        if not rows:
            return {"ok": False, "message": "用户名或密码错误"}

        # 遍历该用户名下的所有 License，逐个验证密码
        matched_row = None
        needs_upgrade = False
        for row in rows:
            stored_hash = row[1]
            if ':' in stored_hash:
                # 新格式: salt:hash (PBKDF2)
                salt, expected_hash = stored_hash.split(':', 1)
                computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
                if hmac.compare_digest(computed, expected_hash):
                    matched_row = row
                    break
            else:
                # 旧格式: 无盐 SHA-256（向后兼容）
                if hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored_hash):
                    matched_row = row
                    needs_upgrade = True
                    break

        if not matched_row:
            return {"ok": False, "message": "用户名或密码错误"}

        key, _pw, status, max_dev, bound_json, expires = matched_row

        # 旧格式密码自动升级为 PBKDF2 + 盐
        if needs_upgrade:
            new_salt = secrets.token_hex(16)
            new_hash = f"{new_salt}:{hashlib.pbkdf2_hmac('sha256', password.encode(), new_salt.encode(), 100000).hex()}"
            with self._conn() as c:
                c.execute("UPDATE licenses SET password_hash=? WHERE license_key=?", (new_hash, key))
            logger.info(f"密码哈希已从 SHA-256 自动升级为 PBKDF2: {key[:4]}...{key[-4:]}")
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

    def verify_and_bind(self, license_key: str, machine_id: str = "", ip_addr: str = "") -> Dict:
        """License Key-only 验证 + 设备绑定"""
        with self._conn() as c:
            row = c.execute(
                "SELECT username,status,max_devices,bound_devices,expires_at FROM licenses WHERE license_key=?",
                (license_key,),
            ).fetchone()

        if not row:
            return {"ok": False, "message": "License Key 无效"}

        username, status, max_dev, bound_json, expires = row
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
                          (json.dumps(bound), license_key))

        with self._conn() as c:
            c.execute("UPDATE licenses SET last_used=datetime('now'), deploy_count=deploy_count+1 WHERE license_key=?", (license_key,))
            c.execute("INSERT INTO deploy_logs(license_key,machine_id,action,ip_addr,os_info) VALUES(?,?,?,?,?)",
                      (license_key, machine_id, "key_auth", ip_addr, f"{platform.system()} {platform.release()}"))

        return {"ok": True, "license_key": license_key, "message": "验证通过"}

    def find_by_buyer(self, buyer_id: str) -> Optional[str]:
        """通过买家ID查找活跃的 License Key"""
        with self._conn() as c:
            row = c.execute(
                "SELECT license_key FROM licenses WHERE xianyu_order_id LIKE ? AND status='active' ORDER BY id DESC LIMIT 1",
                (f"%{buyer_id}%",),
            ).fetchone()
        return row[0] if row else None

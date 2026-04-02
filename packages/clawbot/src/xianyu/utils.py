"""闲鱼工具函数 — 签名、MessagePack 解密、ID 生成"""
import base64
import hashlib
import json
import secrets
import struct
import time
from typing import Any, Dict, List


def generate_mid() -> str:
    # 使用密码学安全随机数生成消息 ID
    random_part = secrets.randbelow(1000)
    timestamp = int(time.time() * 1000)
    return f"{random_part}{timestamp} 0"


def generate_uuid() -> str:
    # 使用密码学安全随机数生成 UUID，避免可预测的时间戳格式
    return secrets.token_hex(16)


def generate_device_id(user_id: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in [8, 13, 18, 23]:
            result.append("-")
        elif i == 14:
            result.append("4")
        elif i == 19:
            # 使用密码学安全随机数替代 random.random()
            rand_val = secrets.randbelow(16)
            result.append(chars[(rand_val & 0x3) | 0x8])
        else:
            # 使用密码学安全随机数替代 random.random()
            result.append(chars[secrets.randbelow(16)])
    return "".join(result) + "-" + user_id


def generate_sign(t: str, token: str, data: str) -> str:
    raw = f"{token}&{t}&34839810&{data}"
    return hashlib.md5(raw.encode()).hexdigest()


def trans_cookies(cookie_str: str) -> Dict[str, str]:
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


# ---- MessagePack 解码器 ----

class _MsgPackDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.length = len(data)

    def _byte(self) -> int:
        if self.pos >= self.length:
            raise ValueError("Unexpected end")
        b = self.data[self.pos]; self.pos += 1; return b

    def _read(self, n: int) -> bytes:
        if self.pos + n > self.length:
            raise ValueError("Unexpected end")
        r = self.data[self.pos:self.pos + n]; self.pos += n; return r

    def _u8(self): return self._byte()
    def _u16(self): return struct.unpack(">H", self._read(2))[0]
    def _u32(self): return struct.unpack(">I", self._read(4))[0]
    def _u64(self): return struct.unpack(">Q", self._read(8))[0]
    def _i8(self): return struct.unpack(">b", self._read(1))[0]
    def _i16(self): return struct.unpack(">h", self._read(2))[0]
    def _i32(self): return struct.unpack(">i", self._read(4))[0]
    def _i64(self): return struct.unpack(">q", self._read(8))[0]
    def _f32(self): return struct.unpack(">f", self._read(4))[0]
    def _f64(self): return struct.unpack(">d", self._read(8))[0]
    def _str(self, n: int): return self._read(n).decode("utf-8", errors="replace")

    def decode(self) -> Any:
        f = self._byte()
        if f <= 0x7F: return f
        if 0x80 <= f <= 0x8F: return self._map(f & 0x0F)
        if 0x90 <= f <= 0x9F: return self._arr(f & 0x0F)
        if 0xA0 <= f <= 0xBF: return self._str(f & 0x1F)
        if f == 0xC0: return None
        if f == 0xC2: return False
        if f == 0xC3: return True
        if f == 0xC4: return self._read(self._u8())
        if f == 0xC5: return self._read(self._u16())
        if f == 0xC6: return self._read(self._u32())
        if f == 0xCA: return self._f32()
        if f == 0xCB: return self._f64()
        if f == 0xCC: return self._u8()
        if f == 0xCD: return self._u16()
        if f == 0xCE: return self._u32()
        if f == 0xCF: return self._u64()
        if f == 0xD0: return self._i8()
        if f == 0xD1: return self._i16()
        if f == 0xD2: return self._i32()
        if f == 0xD3: return self._i64()
        if f == 0xD9: return self._str(self._u8())
        if f == 0xDA: return self._str(self._u16())
        if f == 0xDB: return self._str(self._u32())
        if f == 0xDC: return self._arr(self._u16())
        if f == 0xDD: return self._arr(self._u32())
        if f == 0xDE: return self._map(self._u16())
        if f == 0xDF: return self._map(self._u32())
        if f >= 0xE0: return f - 256
        raise ValueError(f"Unknown format: 0x{f:02x}")

    def _arr(self, n: int) -> List[Any]:
        return [self.decode() for _ in range(n)]

    def _map(self, n: int) -> Dict[Any, Any]:
        return {self.decode(): self.decode() for _ in range(n)}


def _json_ser(obj):
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception as e:  # noqa: F841
            return base64.b64encode(obj).decode()
    return str(obj)


def decrypt(data: str) -> str:
    """解密闲鱼 WebSocket 消息（Base64 + MessagePack）"""
    try:
        cleaned = "".join(c for c in data if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        while len(cleaned) % 4 != 0:
            cleaned += "="
        raw = base64.b64decode(cleaned)

        # MessagePack 解码
        try:
            result = _MsgPackDecoder(raw).decode()
            return json.dumps(result, ensure_ascii=False, default=_json_ser)
        except Exception as e:  # noqa: F841
            # fallback: 直接 UTF-8
            try:
                return json.dumps({"text": raw.decode("utf-8")})
            except Exception as e:  # noqa: F841
                return json.dumps({"hex": raw.hex()})
    except Exception as e:
        return json.dumps({"error": str(e), "raw": data[:200]})

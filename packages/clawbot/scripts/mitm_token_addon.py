"""mitmproxy addon — 从微信小程序流量中截取 session-token

作为 mitmdump -s 脚本使用，监听微信「提现笔笔省」小程序的请求，
从请求头和响应体中提取 session-token，写入临时文件供领券脚本读取。

用法:
    mitmdump -s mitm_token_addon.py -p 8080 --set block_global=false
"""

import json
import os
from mitmproxy import http

# token 写入路径，与 wechat_coupon.py 约定
_TOKEN_FILE = os.getenv("COUPON_TOKEN_FILE", "/tmp/wechat_coupon_token.txt")
# 只拦截笔笔省小程序的请求
_TARGET_HOST = "discount.wxpapp.wechatpay.cn"


class TokenExtractor:
    """从微信小程序流量中提取 session-token"""

    def request(self, flow: http.HTTPFlow) -> None:
        """拦截请求，提取请求头中的 session-token"""
        if _TARGET_HOST not in flow.request.pretty_host:
            return

        token = flow.request.headers.get("session-token", "")
        track_id = flow.request.headers.get("X-Track-Id", "")

        if token and len(token) >= 40:
            self._write_token(f"header:session-token\t{token}")
        if track_id:
            self._write_token(f"header:X-Track-Id\t{track_id}")

    def response(self, flow: http.HTTPFlow) -> None:
        """拦截响应，提取响应体中的 session_token"""
        if _TARGET_HOST not in flow.request.pretty_host:
            return
        if not flow.response or not flow.response.content:
            return

        try:
            body = flow.response.get_text()
            data = json.loads(body)
            # 尝试多种字段名
            for key in ("session_token", "sessionToken", "session-token"):
                val = self._deep_get(data, key)
                if val and isinstance(val, str) and len(val) >= 40:
                    self._write_token(f"response_json:session_token\t{val}")
                    break
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def _deep_get(self, obj: dict, key: str) -> str:
        """在嵌套字典中递归查找指定键"""
        if not isinstance(obj, dict):
            return ""
        if key in obj:
            return str(obj[key])
        # 在 data 子字典中查找
        data = obj.get("data")
        if isinstance(data, dict) and key in data:
            return str(data[key])
        return ""

    def _write_token(self, line: str) -> None:
        """追加写入 token 到文件"""
        try:
            with open(_TOKEN_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


# mitmproxy 要求的 addon 注册
addons = [TokenExtractor()]

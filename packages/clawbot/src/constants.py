"""
全局常量 — 各模块共享的 HTTP 请求头、版本号等。

统一管理 User-Agent 字符串，避免散落在各文件中导致版本不一致。
更新 Chrome 版本只需改此处一行。
"""

# 通用 Web 抓取 User-Agent（macOS Chrome）
# 用于 GitHub trending、SMZDM 比价、社交热搜等公开页面抓取
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

# 闲鱼/咸鱼专用 User-Agent（Windows Chrome）
# 闲鱼 Web 端 (goofish.com) 对 UA 有检测，需要模拟 Windows 浏览器
XIANYU_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36"
)

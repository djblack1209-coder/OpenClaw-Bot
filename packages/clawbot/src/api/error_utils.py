"""
API 错误处理工具 — 所有 router 共用的安全错误消息转换。

将异常转为不泄露技术细节的安全消息，供 API 返回给前端。
"""


def safe_error(e: Exception) -> str:
    """将异常转为安全的错误消息，不泄露内部路径和技术细节"""
    msg = str(e)
    # 过滤掉包含文件路径、模块名、类名的技术信息
    if any(kw in msg for kw in ("/", "\\", "src.", "Traceback", "line ", "File ")):
        return "内部服务错误，请稍后重试"
    # 保留简短的业务错误消息（如 "vectorbt 未安装"）
    if len(msg) > 200:
        return "内部服务错误，请稍后重试"
    return msg

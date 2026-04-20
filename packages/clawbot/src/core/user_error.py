"""用户友好的错误信息转换 — 将技术异常转换为中文人话

所有面向用户的错误提示都应通过此模块转换，
确保用户永远看不到堆栈跟踪、HTTP状态码或英文错误。
"""

import logging

logger = logging.getLogger(__name__)

# 错误模式 → 用户友好中文提示
# 按匹配优先级排序（越具体的放越前面）
ERROR_MAP: list[tuple[str, str]] = [
    # Cookie/登录相关
    ("cookie expired", "平台登录已过期，请重新扫码登录"),
    ("cookie invalid", "平台登录已失效，请重新登录"),
    ("session expired", "会话已过期，请重新登录"),
    ("authentication failed", "认证失败，请检查登录凭据"),
    ("unauthorized", "未授权访问，请重新登录"),
    ("forbidden", "没有权限执行此操作"),

    # 网络/连接
    ("connection refused", "服务连接失败，请检查网络或重启服务"),
    ("connection reset", "连接被重置，请稍后重试"),
    ("connection timeout", "连接超时，请检查网络状况"),
    ("timeout", "操作超时，请稍后重试"),
    ("name resolution", "域名解析失败，请检查网络连接"),
    ("ssl", "安全连接失败，请检查网络环境"),
    ("network", "网络连接异常，请检查网络"),

    # 限流
    ("rate limit", "请求太频繁，稍等片刻再试"),
    ("too many requests", "操作太频繁，请稍后再试"),
    ("quota exceeded", "API配额已用完，请等待重置或更换Key"),

    # 交易相关
    ("insufficient balance", "账户余额不足，请充值后继续"),
    ("insufficient funds", "资金不足，请检查账户余额"),
    ("market closed", "当前市场已休市"),
    ("ibkr not connected", "IB Gateway 未连接，请先启动 IB Gateway 并登录"),
    ("ib gateway", "IB Gateway 连接异常，请检查是否已启动"),
    ("no position", "没有该标的的持仓"),
    ("order rejected", "订单被拒绝，请检查参数后重试"),

    # API Key
    ("api key invalid", "API密钥无效，请在设置中重新配置"),
    ("invalid api key", "API密钥无效，请检查配置"),
    ("api key expired", "API密钥已过期，请更新"),

    # 服务相关
    ("service unavailable", "服务暂时不可用，请稍后重试"),
    ("internal server error", "服务内部错误，请稍后重试"),
    ("bad gateway", "网关错误，请稍后重试"),
    ("not found", "未找到请求的资源"),

    # 数据相关
    ("no data", "暂无数据"),
    ("empty response", "服务返回了空数据，请稍后重试"),
    ("parse error", "数据格式异常，请稍后重试"),

    # 通用
    ("permission denied", "没有权限执行此操作"),
    ("disk full", "磁盘空间不足，请清理后重试"),
    ("memory", "内存不足，请关闭一些程序后重试"),
]

# 默认的兜底错误提示
DEFAULT_ERROR = "操作失败，请稍后重试（如持续出现请联系支持）"


def humanize_error(exc: Exception) -> str:
    """将技术异常转换为用户友好的中文提示

    Args:
        exc: 任何异常对象

    Returns:
        str: 中文人话版错误提示

    用法:
        try:
            await do_something()
        except Exception as e:
            user_msg = humanize_error(e)
            await send_to_user(user_msg)
    """
    exc_str = str(exc).lower()

    for pattern, message in ERROR_MAP:
        if pattern in exc_str:
            return message

    # 尝试匹配异常类型名
    exc_type = type(exc).__name__.lower()
    if "timeout" in exc_type:
        return "操作超时，请稍后重试"
    if "connection" in exc_type:
        return "连接失败，请检查网络"
    if "permission" in exc_type or "auth" in exc_type:
        return "权限不足，请检查配置"

    logger.debug("未匹配的异常类型 %s: %s", type(exc).__name__, exc)
    return DEFAULT_ERROR


def humanize_http_status(status_code: int) -> str:
    """将HTTP状态码转换为中文说明"""
    status_map = {
        400: "请求参数有误，请检查输入",
        401: "未登录或登录已过期",
        403: "没有权限访问",
        404: "未找到请求的内容",
        408: "请求超时，请重试",
        429: "请求太频繁，请稍后再试",
        500: "服务暂时不可用，请稍后重试",
        502: "网关错误，请稍后重试",
        503: "服务正在维护中，请稍后重试",
        504: "网关超时，请稍后重试",
    }
    return status_map.get(status_code, f"请求失败（错误码：{status_code}），请稍后重试")

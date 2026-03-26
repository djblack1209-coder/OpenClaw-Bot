"""
统一错误消息模板 — 保持所有端错误提示语气一致。

所有用户可见的错误消息从这里获取。
修改错误语气/风格只需改这一个文件。

语气规范:
- 像朋友发微信，不像客服模板
- 💬 轻微问题（用户可立即重试）
- ⏳ 需要等一等（给出具体等待时间）
- ❌ 需要注意（权限/服务故障等）
- 每条消息给出具体的等待时间或下一步建议
- 永远不暴露内部异常堆栈/英文技术术语给用户
"""

import re


def _is_technical(text: str) -> bool:
    """判断文本是否包含技术内容，不应暴露给用户。"""
    if not text:
        return False
    # 包含英文字母占比超过 30%，视为技术内容
    alpha_count = sum(1 for c in text if c.isascii() and c.isalpha())
    if len(text) > 0 and alpha_count / len(text) > 0.3:
        return True
    # 包含典型技术关键词
    technical_pattern = re.compile(
        r"(Error|Exception|Traceback|Failed|Timeout|Connection|HTTP|"
        r"null|undefined|NoneType|\.\w+\.\w+|status[_\s]?code)",
        re.IGNORECASE,
    )
    return bool(technical_pattern.search(text))


def error_generic(detail: str = "") -> str:
    """通用错误，用于未分类的异常。"""
    base = "❌ 这个请求没处理成功，我再试试。\n你也可以换个说法重新问我。"
    # 只展示中文可读的 detail，过滤掉技术内容
    if detail and not _is_technical(detail):
        return f"{base}\n💡 补充: {detail[:100]}"
    return base


def error_rate_limit() -> str:
    """请求频率超限。"""
    return "⏳ 你发得太快啦，等 10 秒再发就好。"


def error_ai_busy() -> str:
    """AI 服务繁忙/超时。"""
    return "⏳ 我现在有点忙，大概 30 秒后再问我试试。"


def error_not_found(item: str = "内容") -> str:
    """资源未找到。"""
    return f"💬 没找到「{item}」，换个关键词试试？"


def error_permission() -> str:
    """无权限。"""
    return "❌ 这个功能需要管理员权限。"


def error_invalid_input(hint: str = "") -> str:
    """输入格式错误。"""
    if hint:
        return f"💬 格式不太对。{hint}"
    return "💬 格式不太对，试试换个说法？"


def error_ai_empty() -> str:
    """AI 返回空内容。"""
    return "💬 这次没想出来，再问一次试试？"


def error_tool_abuse() -> str:
    """工具调用过多。"""
    return "💬 这个问题太复杂了，我处理不过来。试试把问题拆小一点？"


def error_network() -> str:
    """网络连接问题。"""
    return "⏳ 网络抖了一下，正在自动恢复，一般几秒就好。"


def error_auth() -> str:
    """API 认证失败。"""
    return "❌ 服务连接出了问题，我已经通知管理员处理了。"


def error_circuit_open() -> str:
    """熔断器打开，服务暂不可用。"""
    return "⏳ 这个服务暂时休息中，大概 5 分钟后恢复。"


def error_service_failed(service: str = "服务", detail: str = "") -> str:
    """通用服务失败（替代 f"xxx失败: {error}" 硬编码模式）。"""
    base = f"❌ {service}没有成功"
    if detail and not _is_technical(detail):
        return f"{base}，{detail[:80]}。\n换个方式试试？"
    return f"{base}，请稍后再试。"


# ── 认知层增强模板 ──────────────────────────────────────────

def correction_ack(original: str = "", corrected: str = "") -> str:
    """纠错确认 — 用户纠正了上一轮回复时的反馈。"""
    if original and corrected:
        return f"💬 收到纠正。{original} → {corrected}，已更正，下次不会搞错了。"
    return "💬 收到，已更正。下次不会搞错了。"


def preference_saved(pref: str = "") -> str:
    """偏好记录确认 — Bot 捕获到用户偏好后的反馈。"""
    if pref:
        return f"💬 记住了：{pref}。以后按你的喜好来。"
    return "💬 记住了。以后按你的喜好来。"

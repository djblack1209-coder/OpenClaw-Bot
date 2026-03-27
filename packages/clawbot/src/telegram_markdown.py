"""
OpenClaw Telegram Markdown 渲染器 — 搬运 mistletoe (1k⭐)
将 LLM 输出的标准 Markdown 安全转换为 Telegram MarkdownV2 或 HTML。

Telegram MarkdownV2 的坑:
  - 必须转义: _ * [ ] ( ) ~ ` > # + - = | { } . !
  - 但在格式标记内部不转义
  - 代码块内不转义
  - 链接语法不同

Telegram HTML 模式（推荐，更少转义问题）:
  - 支持: <b> <i> <u> <s> <code> <pre> <a href=""> <tg-spoiler>
  - 只需转义: < > &

Usage:
    from src.telegram_markdown import md_to_telegram, md_to_html

    # MarkdownV2 模式 — 完整格式但转义复杂
    safe_v2 = md_to_telegram("**bold** and `code` and [link](url)")

    # HTML 模式（推荐）— 兼容性更好
    safe_html = md_to_html("**bold** and `code` and [link](url)")
"""
import html
import logging
import re

logger = logging.getLogger(__name__)

# ── mistletoe 导入（优雅降级） ──────────────────────────

try:
    from mistletoe import Document
    from mistletoe.base_renderer import BaseRenderer
    from mistletoe.span_token import (
        RawText,
        EscapeSequence,
        InlineCode,
        Strong,
        Emphasis,
        Strikethrough,
        AutoLink,
        Link,
        Image,
    )
    from mistletoe.block_token import (
        Heading,
        Paragraph,
        BlockCode,
        CodeFence,
        List as ListBlock,
        ListItem,
        Table,
        TableRow,
        Quote,
        ThematicBreak,
        HTMLBlock,
    )

    HAS_MISTLETOE = True
except ImportError:
    HAS_MISTLETOE = False
    logger.info(
        "[telegram_markdown] mistletoe 未安装，使用 regex 降级渲染。"
        "pip install mistletoe>=1.4.0 以启用完整 AST 渲染。"
    )

# ── 常量 ──────────────────────────────────────────────

# Telegram MarkdownV2 要求转义的字符
_V2_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"
_V2_ESCAPE_RE = re.compile(r"([" + re.escape(_V2_ESCAPE_CHARS) + r"])")


# ══════════════════════════════════════════════════════
# 方案 A: mistletoe AST 渲染器
# ══════════════════════════════════════════════════════

if HAS_MISTLETOE:

    # ── MarkdownV2 渲染器 ─────────────────────────────

    class TelegramMarkdownV2Renderer(BaseRenderer):
        """
        将标准 Markdown AST 渲染为 Telegram MarkdownV2 格式。

        Telegram MarkdownV2 规则:
        - 格式标记内的文本不需要转义格式字符本身
        - 但标记外的所有特殊字符必须反斜杠转义
        - 代码块/行内代码内不做任何转义
        """

        def __init__(self, *extras, **kwargs):
            # mistletoe v1.5+ 自动注册内置 token 类型
            super().__init__(*extras)

        # ── 工具方法 ──────────────────────────────

        @staticmethod
        def _escape_v2(text: str) -> str:
            """转义 MarkdownV2 特殊字符"""
            return _V2_ESCAPE_RE.sub(r"\\\1", text)

        def _render_children(self, token) -> str:
            """递归渲染子 token"""
            return "".join(self.render(child) for child in token.children)

        # ── Span tokens ──────────────────────────

        def render_raw_text(self, token: RawText) -> str:
            return self._escape_v2(token.content)

        def render_escape_sequence(self, token: EscapeSequence) -> str:
            return self._render_children(token)

        def render_strong(self, token: Strong) -> str:
            content = self._render_children(token)
            return f"*{content}*"

        def render_emphasis(self, token: Emphasis) -> str:
            content = self._render_children(token)
            return f"_{content}_"

        def render_strikethrough(self, token: Strikethrough) -> str:
            content = self._render_children(token)
            return f"~{content}~"

        def render_inline_code(self, token: InlineCode) -> str:
            # 代码块内不做任何转义
            return f"`{token.children[0].content}`"

        def render_auto_link(self, token: AutoLink) -> str:
            target = self._escape_v2(token.target)
            return f"[{target}]({token.target})"

        def render_link(self, token: Link) -> str:
            content = self._render_children(token)
            # URL 内部不转义 ()，只转义显示文本
            return f"[{content}]({token.target})"

        def render_image(self, token: Image) -> str:
            # Telegram 不支持内联图片，渲染为链接
            desc = self._render_children(token) or "image"
            return f"[{desc}]({token.src})"

        # ── Block tokens ─────────────────────────

        def render_document(self, token) -> str:
            return self._render_children(token)

        def render_heading(self, token: Heading) -> str:
            # Telegram 无标题语法 → 转为粗体
            content = self._render_children(token)
            return f"\n*{content}*\n"

        def render_paragraph(self, token: Paragraph) -> str:
            content = self._render_children(token)
            return f"{content}\n"

        def render_block_code(self, token: BlockCode) -> str:
            # 代码块内不做任何转义
            lang = getattr(token, "language", "") or ""
            code = token.children[0].content if token.children else ""
            # 移除尾部换行以避免多余空行
            code = code.rstrip("\n")
            if lang:
                return f"```{lang}\n{code}\n```\n"
            return f"```\n{code}\n```\n"

        def render_code_fence(self, token: CodeFence) -> str:
            lang = getattr(token, "language", "") or ""
            code = token.children[0].content if token.children else ""
            code = code.rstrip("\n")
            if lang:
                return f"```{lang}\n{code}\n```\n"
            return f"```\n{code}\n```\n"

        def render_list(self, token: ListBlock) -> str:
            result = []
            for i, item in enumerate(token.children):
                if hasattr(token, "start") and token.start is not None:
                    prefix = f"{token.start + i}\\."
                else:
                    prefix = "•"
                content = self._render_children(item).strip()
                result.append(f"  {prefix} {content}")
            return "\n".join(result) + "\n"

        def render_list_item(self, token: ListItem) -> str:
            return self._render_children(token)

        def render_table(self, token: Table) -> str:
            # Telegram 无表格语法 → 转为等宽文本块
            rows = []
            for row_token in token.children:
                cells = [
                    self._render_children(cell).strip()
                    for cell in row_token.children
                ]
                rows.append(cells)

            if not rows:
                return ""

            # 计算每列最大宽度（考虑中文宽字符）
            col_widths = [0] * max(len(r) for r in rows)
            for row in rows:
                for j, cell in enumerate(row):
                    col_widths[j] = max(col_widths[j], _display_width(cell))

            lines = []
            for row in rows:
                parts = []
                for j, cell in enumerate(row):
                    pad = col_widths[j] - _display_width(cell)
                    parts.append(cell + " " * pad)
                lines.append("  ".join(parts))

            table_text = "\n".join(lines)
            return f"```\n{table_text}\n```\n"

        def render_table_row(self, token: TableRow) -> str:
            # 由 render_table 直接处理子节点
            return ""

        def render_quote(self, token: Quote) -> str:
            content = self._render_children(token).strip()
            # MarkdownV2 引用块
            lines = content.split("\n")
            return "\n".join(f">{line}" for line in lines) + "\n"

        def render_thematic_break(self, token: ThematicBreak) -> str:
            return self._escape_v2("───────────────────") + "\n"

        def render_html_block(self, token: HTMLBlock) -> str:
            # 原样输出 HTML 标签内容（转义）
            content = getattr(token, "content", "")
            return self._escape_v2(content)

    # ── HTML 渲染器 ───────────────────────────────────

    class TelegramHTMLRenderer(BaseRenderer):
        """
        将标准 Markdown AST 渲染为 Telegram HTML 格式。

        Telegram HTML 只支持:
          <b>, <i>, <u>, <s>, <code>, <pre>, <a href="">, <tg-spoiler>
        其他 HTML 标签会被 Telegram 拒绝。
        """

        def __init__(self, *extras, **kwargs):
            super().__init__(*extras)

        def _render_children(self, token) -> str:
            return "".join(self.render(child) for child in token.children)

        # ── Span tokens ──────────────────────────

        def render_raw_text(self, token: RawText) -> str:
            return html.escape(token.content)

        def render_escape_sequence(self, token: EscapeSequence) -> str:
            return self._render_children(token)

        def render_strong(self, token: Strong) -> str:
            return f"<b>{self._render_children(token)}</b>"

        def render_emphasis(self, token: Emphasis) -> str:
            return f"<i>{self._render_children(token)}</i>"

        def render_strikethrough(self, token: Strikethrough) -> str:
            return f"<s>{self._render_children(token)}</s>"

        def render_inline_code(self, token: InlineCode) -> str:
            code = html.escape(token.children[0].content)
            return f"<code>{code}</code>"

        def render_auto_link(self, token: AutoLink) -> str:
            url = html.escape(token.target)
            return f'<a href="{url}">{url}</a>'

        def render_link(self, token: Link) -> str:
            url = html.escape(token.target)
            text = self._render_children(token)
            return f'<a href="{url}">{text}</a>'

        def render_image(self, token: Image) -> str:
            url = html.escape(token.src)
            desc = self._render_children(token) or "image"
            return f'<a href="{url}">[{desc}]</a>'

        # ── Block tokens ─────────────────────────

        def render_document(self, token) -> str:
            return self._render_children(token)

        def render_heading(self, token: Heading) -> str:
            content = self._render_children(token)
            return f"\n<b>{content}</b>\n"

        def render_paragraph(self, token: Paragraph) -> str:
            return f"{self._render_children(token)}\n"

        def render_block_code(self, token: BlockCode) -> str:
            lang = getattr(token, "language", "") or ""
            code = token.children[0].content if token.children else ""
            code = html.escape(code.rstrip("\n"))
            if lang:
                return f'<pre><code class="language-{html.escape(lang)}">{code}</code></pre>\n'
            return f"<pre>{code}</pre>\n"

        def render_code_fence(self, token: CodeFence) -> str:
            lang = getattr(token, "language", "") or ""
            code = token.children[0].content if token.children else ""
            code = html.escape(code.rstrip("\n"))
            if lang:
                return f'<pre><code class="language-{html.escape(lang)}">{code}</code></pre>\n'
            return f"<pre>{code}</pre>\n"

        def render_list(self, token: ListBlock) -> str:
            result = []
            for i, item in enumerate(token.children):
                if hasattr(token, "start") and token.start is not None:
                    prefix = f"{token.start + i}."
                else:
                    prefix = "•"
                content = self._render_children(item).strip()
                result.append(f"  {prefix} {content}")
            return "\n".join(result) + "\n"

        def render_list_item(self, token: ListItem) -> str:
            return self._render_children(token)

        def render_table(self, token: Table) -> str:
            rows = []
            for row_token in token.children:
                cells = [
                    self._render_children(cell).strip()
                    for cell in row_token.children
                ]
                rows.append(cells)

            if not rows:
                return ""

            # 计算每列最大宽度
            col_widths = [0] * max(len(r) for r in rows)
            for row in rows:
                for j, cell in enumerate(row):
                    # 先去掉 HTML 标签再计算显示宽度
                    plain = re.sub(r"<[^>]+>", "", cell)
                    col_widths[j] = max(col_widths[j], _display_width(plain))

            lines = []
            for row in rows:
                parts = []
                for j, cell in enumerate(row):
                    plain = re.sub(r"<[^>]+>", "", cell)
                    pad = col_widths[j] - _display_width(plain)
                    parts.append(cell + " " * pad)
                lines.append("  ".join(parts))

            table_text = "\n".join(lines)
            return f"<pre>{html.escape(table_text)}</pre>\n"

        def render_table_row(self, token: TableRow) -> str:
            return ""

        def render_quote(self, token: Quote) -> str:
            content = self._render_children(token).strip()
            # Telegram HTML 没有引用标签，用 blockquote 风格
            lines = content.split("\n")
            quoted = "\n".join(f"▎ {line}" for line in lines)
            return f"<i>{quoted}</i>\n"

        def render_thematic_break(self, token: ThematicBreak) -> str:
            return "━━━━━━━━━━━━━━━\n"

        def render_html_block(self, token: HTMLBlock) -> str:
            content = getattr(token, "content", "")
            return html.escape(content)


# ══════════════════════════════════════════════════════
# 方案 B: Regex 降级渲染器（mistletoe 不可用时）
# ══════════════════════════════════════════════════════

def _regex_md_to_v2(text: str) -> str:
    """基于正则的 MarkdownV2 转换 — 降级方案"""
    # 先保护代码块（不转义内部内容）
    code_blocks = []

    def _save_code_block(m):
        code_blocks.append(m.group(0))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    def _save_inline_code(m):
        code_blocks.append(m.group(0))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    # 保护围栏代码块
    text = re.sub(r"```[\s\S]*?```", _save_code_block, text)
    # 保护行内代码
    text = re.sub(r"`[^`]+`", _save_inline_code, text)

    # 转换格式标记（在转义之前）
    # **bold** → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # __bold__ → *bold*
    text = re.sub(r"__(.+?)__", r"*\1*", text)
    # ~~strikethrough~~ → ~strikethrough~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # 标题 → 粗体
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\n*\1*", text, flags=re.MULTILINE)

    # 列表项
    text = re.sub(r"^[-*+]\s+", "  • ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\d+)\.\s+", r"  \1\\. ", text, flags=re.MULTILINE)

    # 分隔线
    text = re.sub(r"^[-*]{3,}\s*$", "───────────────────", text, flags=re.MULTILINE)

    # 保护已有格式标记中的内容，对标记外的特殊字符进行转义
    # 分段处理：提取格式标记外的纯文本，只对纯文本转义
    result = _escape_outside_markers(text)

    # 恢复代码块
    for i, block in enumerate(code_blocks):
        result = result.replace(f"\x00CB{i}\x00", block)

    # 清理多余空行
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _escape_outside_markers(text: str) -> str:
    """只对格式标记外的文本进行 MarkdownV2 转义"""
    # 标记模式：*text*, _text_, ~text~, [text](url)
    # 简单方法：对每段文本，识别格式标记边界，只转义外部文本
    parts = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        # 跳过格式标记 *...*
        if c == "*" and i + 1 < n and text[i + 1] != "*":
            end = text.find("*", i + 1)
            if end != -1:
                parts.append(text[i : end + 1])
                i = end + 1
                continue

        # 跳过格式标记 _..._
        if c == "_":
            end = text.find("_", i + 1)
            if end != -1:
                parts.append(text[i : end + 1])
                i = end + 1
                continue

        # 跳过格式标记 ~...~
        if c == "~":
            end = text.find("~", i + 1)
            if end != -1:
                parts.append(text[i : end + 1])
                i = end + 1
                continue

        # 跳过链接 [text](url)
        if c == "[":
            close_bracket = text.find("](", i)
            if close_bracket != -1:
                close_paren = text.find(")", close_bracket + 2)
                if close_paren != -1:
                    parts.append(text[i : close_paren + 1])
                    i = close_paren + 1
                    continue

        # 跳过占位符 \x00CB...\x00
        if c == "\x00":
            end = text.find("\x00", i + 1)
            if end != -1:
                parts.append(text[i : end + 1])
                i = end + 1
                continue

        # 普通字符 — 需要转义
        if c in _V2_ESCAPE_CHARS:
            parts.append(f"\\{c}")
        else:
            parts.append(c)
        i += 1

    return "".join(parts)


def _regex_md_to_html(text: str) -> str:
    """基于正则的 HTML 转换 — 降级方案"""
    # 先保护代码块
    code_blocks = []

    def _save_fence(m):
        lang = m.group(1) or ""
        code = html.escape(m.group(2))
        if lang:
            replacement = f'<pre><code class="language-{html.escape(lang)}">{code}</code></pre>'
        else:
            replacement = f"<pre>{code}</pre>"
        code_blocks.append(replacement)
        return f"\x00CB{len(code_blocks) - 1}\x00"

    def _save_inline(m):
        code = html.escape(m.group(1))
        code_blocks.append(f"<code>{code}</code>")
        return f"\x00CB{len(code_blocks) - 1}\x00"

    # 围栏代码块
    text = re.sub(r"```(\w*)\n([\s\S]*?)```", _save_fence, text)
    # 行内代码
    text = re.sub(r"`([^`]+)`", _save_inline, text)

    # HTML 转义（代码块已保护）
    text = html.escape(text)

    # 格式转换
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 标题 → 粗体
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\n<b>\1</b>", text, flags=re.MULTILINE)

    # 链接
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )

    # 列表项
    text = re.sub(r"^[-*+]\s+", "  • ", text, flags=re.MULTILINE)

    # 分隔线
    text = re.sub(r"^[-*]{3,}\s*$", "━━━━━━━━━━━━━━━", text, flags=re.MULTILINE)

    # 恢复代码块
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CB{i}\x00", block)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ══════════════════════════════════════════════════════
# 公共 API
# ══════════════════════════════════════════════════════

def md_to_telegram(text: str) -> str:
    """
    将标准 Markdown 转换为 Telegram MarkdownV2 格式。

    Args:
        text: LLM 输出的标准 Markdown 文本

    Returns:
        Telegram MarkdownV2 安全的文本，可用于 parse_mode="MarkdownV2"
    """
    if not text:
        return ""

    if HAS_MISTLETOE:
        try:
            with TelegramMarkdownV2Renderer() as renderer:
                doc = Document(text)
                result = renderer.render(doc)
            return result.strip()
        except Exception as e:
            logger.warning(f"[telegram_markdown] mistletoe 渲染失败，降级到 regex: {e}")
            return _regex_md_to_v2(text)
    else:
        return _regex_md_to_v2(text)


def md_to_html(text: str) -> str:
    """
    将标准 Markdown 转换为 Telegram HTML 格式（推荐）。

    Telegram HTML 模式转义规则更简单，兼容性更好。
    适用于 parse_mode="HTML"。

    Args:
        text: LLM 输出的标准 Markdown 文本

    Returns:
        Telegram HTML 安全的文本，可用于 parse_mode="HTML"
    """
    if not text:
        return ""

    if HAS_MISTLETOE:
        try:
            with TelegramHTMLRenderer() as renderer:
                doc = Document(text)
                result = renderer.render(doc)
            return result.strip()
        except Exception as e:
            logger.warning(f"[telegram_markdown] mistletoe HTML 渲染失败，降级到 regex: {e}")
            return _regex_md_to_html(text)
    else:
        return _regex_md_to_html(text)


def escape_v2(text: str) -> str:
    """
    转义纯文本中的 MarkdownV2 特殊字符。
    用于将用户输入安全嵌入到 MarkdownV2 模板中。
    """
    return _V2_ESCAPE_RE.sub(r"\\\1", text)


def escape_html(text: str) -> str:
    """
    转义纯文本中的 HTML 特殊字符 (< > &)。
    用于将用户输入安全嵌入到 HTML 模板中。
    """
    return html.escape(text)


# ══════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════

def _display_width(text: str) -> int:
    """
    计算文本的显示宽度（考虑中日韩宽字符）。
    CJK 字符宽度为 2，其他为 1。
    """
    width = 0
    for ch in text:
        cp = ord(ch)
        # CJK Unified Ideographs + common wide ranges
        if (
            (0x4E00 <= cp <= 0x9FFF)
            or (0x3000 <= cp <= 0x303F)
            or (0xFF00 <= cp <= 0xFFEF)
            or (0xF900 <= cp <= 0xFAFF)
            or (0x2E80 <= cp <= 0x2FDF)
            or (0x3400 <= cp <= 0x4DBF)
            or (0x20000 <= cp <= 0x2A6DF)
        ):
            width += 2
        else:
            width += 1
    return width

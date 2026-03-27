"""
OpenClaw 文档理解 — 搬运 Docling (56.3k⭐)
将 PDF/DOCX/PPTX/XLSX/图片 转为结构化 Markdown。
表格保留结构，公式解析，代码块提取。

Usage:
    from src.tools.docling_service import convert_document, summarize_document
    markdown, tables = await convert_document("/path/to/file.pdf")
    summary = await summarize_document("/path/to/file.pdf", question="这份合同的关键条款是什么？")
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ── Graceful degradation ─────────────────────────────────────
try:
    from docling.document_converter import DocumentConverter
    HAS_DOCLING = True
except ImportError:
    DocumentConverter = None  # type: ignore[assignment,misc]
    HAS_DOCLING = False
    logger.info("[Docling] docling 未安装，文档理解功能不可用。pip install docling>=2.0.0")

# Telegram 消息安全长度 (留 96 字符余量给 footer/tag)
TG_CHAR_LIMIT = 4000
TRUNCATION_INDICATOR = "\n\n⋯ (文档内容过长，已截断)"

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif",
})


def _is_supported(file_path: str) -> bool:
    """检查文件类型是否被 Docling 支持。"""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def _truncate(text: str, limit: int = TG_CHAR_LIMIT) -> str:
    """截断文本到 Telegram 安全长度。"""
    if len(text) <= limit:
        return text
    return text[:limit - len(TRUNCATION_INDICATOR)] + TRUNCATION_INDICATOR


def _extract_tables_from_result(result) -> List[dict]:
    """从 Docling 转换结果中提取所有表格为 list of dicts。

    Docling v2 的 ConversionResult.document.tables 包含 TableItem 对象，
    每个 TableItem 有 .export_to_dataframe() 方法。
    """
    tables = []
    try:
        doc = result.document
        if not hasattr(doc, "tables") or not doc.tables:
            return tables
        for i, table_item in enumerate(doc.tables):
            try:
                # Docling v2: TableItem → DataFrame → list of dicts
                df = table_item.export_to_dataframe()
                table_dict = {
                    "index": i,
                    "rows": len(df),
                    "columns": list(df.columns),
                    "data": df.to_dict(orient="records"),
                }
                tables.append(table_dict)
            except Exception as te:
                logger.debug(f"[Docling] 表格 {i} 提取失败: {te}")
                continue
    except Exception as e:
        logger.debug(f"[Docling] 表格提取失败: {e}")
    return tables


async def convert_document(
    file_path: str,
) -> Tuple[str, List[dict]]:
    """将文档转换为 Markdown + 提取表格。

    Args:
        file_path: 文档文件路径（PDF/DOCX/PPTX/XLSX/图片）

    Returns:
        (markdown_text, extracted_tables)
        - markdown_text: 文档内容的 Markdown 文本 (截断到 TG_CHAR_LIMIT)
        - extracted_tables: 表格列表，每个元素为 dict

    Raises:
        RuntimeError: docling 未安装
        FileNotFoundError: 文件不存在
        ValueError: 文件类型不支持
    """
    if not HAS_DOCLING:
        raise RuntimeError(
            "docling 未安装。请运行: pip install docling>=2.0.0"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    if not _is_supported(file_path):
        raise ValueError(
            f"不支持的文件类型: {path.suffix}。"
            f"支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    loop = asyncio.get_running_loop()

    def _sync_convert():
        """在线程池中运行 Docling 同步转换。"""
        converter = DocumentConverter()
        result = converter.convert(str(path))
        markdown = result.document.export_to_markdown()
        tables = _extract_tables_from_result(result)
        return markdown, tables

    try:
        markdown, tables = await loop.run_in_executor(None, _sync_convert)
    except Exception as e:
        logger.error(f"[Docling] 转换失败 {path.name}: {e}")
        raise

    # 截断到 Telegram 安全长度
    markdown = _truncate(markdown)

    logger.info(
        "[Docling] 转换成功 %s → %d chars, %d tables",
        path.name, len(markdown), len(tables),
    )
    return markdown, tables


async def summarize_document(
    file_path: str,
    question: str = "",
) -> str:
    """转换文档并用 LLM 总结/回答问题。

    Args:
        file_path: 文档文件路径
        question: 用户问题（为空则自动生成摘要）

    Returns:
        LLM 生成的摘要/回答文本
    """
    # Step 1: 文档 → Markdown
    markdown, tables = await convert_document(file_path)

    if not markdown.strip():
        return "文档内容为空，无法分析。"

    # Step 2: 构造 LLM prompt
    table_summary = ""
    if tables:
        table_info = []
        for t in tables[:5]:  # 最多展示前 5 个表格信息
            cols = ", ".join(t["columns"][:10])
            table_info.append(f"  - 表格 {t['index'] + 1}: {t['rows']} 行, 列: {cols}")
        table_summary = "\n\n📊 文档中的表格:\n" + "\n".join(table_info)

    if question:
        system_prompt = (
            "你是一位专业的文档分析助手。用户上传了一份文档并提出了问题。\n"
            "请根据文档内容准确回答用户的问题。\n"
            "回答要简洁清晰，使用中文，适合 Telegram 阅读。"
        )
        user_prompt = (
            f"📄 文档内容:\n{markdown[:3000]}"
            f"{table_summary}\n\n"
            f"❓ 用户问题: {question}\n\n"
            "请回答上述问题:"
        )
    else:
        system_prompt = (
            "你是一位专业的文档分析助手。请对上传的文档进行结构化摘要。\n"
            "输出格式:\n"
            "1. 📌 文档类型与主题\n"
            "2. 📝 核心内容摘要 (3-5 个要点)\n"
            "3. 📊 关键数据/表格 (如有)\n"
            "4. 💡 关键结论或建议\n\n"
            "使用中文，简洁清晰，适合 Telegram 阅读。"
        )
        user_prompt = (
            f"📄 文档内容:\n{markdown[:3000]}"
            f"{table_summary}\n\n"
            "请对该文档进行结构化摘要:"
        )

    # Step 3: 调用 LLM
    try:
        from src.litellm_router import free_pool

        resp = await free_pool.acompletion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1500,
        )
        result = resp.choices[0].message.content
        if result and result.strip():
            return _truncate(result.strip())
        return "LLM 未能生成有效摘要。"
    except Exception as e:
        logger.warning(f"[Docling] LLM 摘要失败: {e}")
        # 降级: 直接返回截断的 Markdown
        fallback = f"📄 文档内容 (LLM 摘要不可用):\n\n{markdown}"
        if table_summary:
            fallback += table_summary
        return _truncate(fallback)

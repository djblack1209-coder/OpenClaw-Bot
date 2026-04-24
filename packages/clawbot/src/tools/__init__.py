# ClawBot Tools
from .bash_tool import BashTool
from .code_tool import CodeTool
from .comfyui_client import ComfyUIClient
from .file_tool import FileTool
from .image_tool import ImageTool
from .memory_tool import MemoryTool
from .web_tool import WebTool

# 延迟导入: openpyxl 是可选依赖
try:
    from .export_service import HAS_OPENPYXL, export_portfolio, export_trades, export_watchlist
except ImportError:
    export_trades = None  # type: ignore[assignment,misc]
    export_watchlist = None  # type: ignore[assignment,misc]
    export_portfolio = None  # type: ignore[assignment,misc]
    HAS_OPENPYXL = False

# 延迟导入: qrcode[pil] 是可选依赖
try:
    from .qr_service import HAS_QRCODE, generate_bot_invite, generate_qr
except ImportError:
    generate_qr = None  # type: ignore[assignment,misc]
    generate_bot_invite = None  # type: ignore[assignment,misc]
    HAS_QRCODE = False

# vision — LiteLLM Vision 图片理解 (零新依赖)
from .vision import analyze_image

# tavily_search — AI-native 搜索 (graceful degradation)
try:
    from .tavily_search import deep_research, quick_answer, search_context
except ImportError:
    quick_answer = None  # type: ignore[assignment,misc]
    search_context = None  # type: ignore[assignment,misc]
    deep_research = None  # type: ignore[assignment,misc]

# docling_service — 文档理解 (graceful degradation)
try:
    from .docling_service import HAS_DOCLING, convert_document, summarize_document
except ImportError:
    convert_document = None  # type: ignore[assignment,misc]
    summarize_document = None  # type: ignore[assignment,misc]
    HAS_DOCLING = False

__all__ = [
    "BashTool",
    "FileTool",
    "WebTool",
    "ImageTool",
    "CodeTool",
    "MemoryTool",
    "ComfyUIClient",
    # 小工具模块
    "export_trades",
    "export_watchlist",
    "export_portfolio",
    "HAS_OPENPYXL",
    "generate_qr",
    "generate_bot_invite",
    "HAS_QRCODE",
    # Vision + Tavily
    "analyze_image",
    "quick_answer",
    "search_context",
    "deep_research",
    # Docling 文档理解
    "convert_document",
    "summarize_document",
    "HAS_DOCLING",
]

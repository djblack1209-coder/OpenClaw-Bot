# ClawBot Tools
from .bash_tool import BashTool
from .file_tool import FileTool
from .screen_tool import ScreenTool
from .web_tool import WebTool
from .image_tool import ImageTool
from .code_tool import CodeTool
from .memory_tool import MemoryTool
from .comfyui_client import ComfyUIClient

# 延迟导入: pyautogui 是可选依赖, 缺失时不影响其他工具
try:
    from .humanized_controller import HumanizedController, HumanConfig
except ImportError:
    HumanizedController = None  # type: ignore[assignment,misc]
    HumanConfig = None  # type: ignore[assignment,misc]

# 延迟导入: DrissionPage 是可选依赖
try:
    from .drission_client import DrissionBrowser, quick_scrape, async_scrape
except ImportError:
    DrissionBrowser = None  # type: ignore[assignment,misc]
    quick_scrape = None  # type: ignore[assignment,misc]
    async_scrape = None  # type: ignore[assignment,misc]

# 延迟导入: openpyxl 是可选依赖
try:
    from .export_service import export_trades, export_watchlist, export_portfolio, HAS_OPENPYXL
except ImportError:
    export_trades = None  # type: ignore[assignment,misc]
    export_watchlist = None  # type: ignore[assignment,misc]
    export_portfolio = None  # type: ignore[assignment,misc]
    HAS_OPENPYXL = False

# 延迟导入: qrcode[pil] 是可选依赖
try:
    from .qr_service import generate_qr, generate_bot_invite, HAS_QRCODE
except ImportError:
    generate_qr = None  # type: ignore[assignment,misc]
    generate_bot_invite = None  # type: ignore[assignment,misc]
    HAS_QRCODE = False

# 延迟导入: fpdf2 是可选依赖
try:
    from .pdf_report import generate_daily_report, generate_trade_report, HAS_FPDF
except ImportError:
    generate_daily_report = None  # type: ignore[assignment,misc]
    generate_trade_report = None  # type: ignore[assignment,misc]
    HAS_FPDF = False

# sentiment_service 仅依赖 httpx (已安装)，直接导入
from .sentiment_service import analyze as sentiment_analyze
from .sentiment_service import analyze_headlines, get_stock_sentiment

# vision — LiteLLM Vision 图片理解 (零新依赖)
from .vision import analyze_image

# tavily_search — AI-native 搜索 (graceful degradation)
try:
    from .tavily_search import quick_answer, search_context, deep_research
except ImportError:
    quick_answer = None  # type: ignore[assignment,misc]
    search_context = None  # type: ignore[assignment,misc]
    deep_research = None  # type: ignore[assignment,misc]

# docling_service — 文档理解 (graceful degradation)
try:
    from .docling_service import convert_document, summarize_document, HAS_DOCLING
except ImportError:
    convert_document = None  # type: ignore[assignment,misc]
    summarize_document = None  # type: ignore[assignment,misc]
    HAS_DOCLING = False

__all__ = [
    "BashTool",
    "FileTool",
    "ScreenTool",
    "WebTool",
    "ImageTool",
    "CodeTool",
    "MemoryTool",
    "ComfyUIClient",
    "HumanizedController",
    "HumanConfig",
    "DrissionBrowser",
    "quick_scrape",
    "async_scrape",
    # Phase 7: 小工具模块
    "export_trades",
    "export_watchlist",
    "export_portfolio",
    "HAS_OPENPYXL",
    "generate_qr",
    "generate_bot_invite",
    "HAS_QRCODE",
    "generate_daily_report",
    "generate_trade_report",
    "HAS_FPDF",
    "sentiment_analyze",
    "analyze_headlines",
    "get_stock_sentiment",
    # Phase 8: Vision + Tavily
    "analyze_image",
    "quick_answer",
    "search_context",
    "deep_research",
    # Phase 9: Docling 文档理解
    "convert_document",
    "summarize_document",
    "HAS_DOCLING",
]

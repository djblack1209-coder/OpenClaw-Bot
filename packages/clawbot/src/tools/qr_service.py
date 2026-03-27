"""
二维码生成服务 — 文本/URL/Telegram 邀请链接二维码
降级链: qrcode[pil] → 纯文本提示
"""
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── 可选依赖: qrcode + PIL ──────────────────────────────────
try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    logger.info("qrcode[pil] 未安装，二维码功能不可用")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def generate_qr(
    data: str,
    logo_path: Optional[str] = None,
    box_size: int = 10,
    border: int = 2,
) -> io.BytesIO:
    """生成二维码 PNG 图片

    Parameters
    ----------
    data : str
        要编码的文本/URL
    logo_path : str, optional
        中心 logo 图片路径，嵌入到二维码中央
    box_size : int
        单个模块的像素大小
    border : int
        边距模块数

    Returns
    -------
    io.BytesIO
        PNG 图片字节流

    Raises
    ------
    RuntimeError
        如果 qrcode 库未安装
    """
    if not HAS_QRCODE:
        raise RuntimeError(
            "二维码功能需要安装 qrcode 库: pip install 'qrcode[pil]'"
        )

    qr = qrcode.QRCode(
        version=None,  # 自动选择版本
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 高容错，支持 logo 遮挡
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    # 使用圆角模块绘制 (更美观)
    try:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
        )
    except Exception as e:
        # 降级到默认样式
        logger.debug("[QRService] 异常: %s", e)
        img = qr.make_image(fill_color="black", back_color="white")

    # 嵌入 logo
    if logo_path and HAS_PIL:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            qr_width, qr_height = img.size
            logo_max = int(qr_width * 0.25)
            logo.thumbnail((logo_max, logo_max), Image.Resampling.LANCZOS)
            logo_w, logo_h = logo.size
            pos = ((qr_width - logo_w) // 2, (qr_height - logo_h) // 2)
            # 白色背景底衬
            bg = Image.new("RGBA", (logo_w + 10, logo_h + 10), "white")
            if hasattr(img, "convert"):
                img = img.convert("RGBA")
            img.paste(bg, (pos[0] - 5, pos[1] - 5))
            img.paste(logo, pos, mask=logo)
        except Exception as e:
            logger.warning("嵌入 logo 失败: %s", e)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_bot_invite(bot_username: str) -> io.BytesIO:
    """生成 Telegram Bot 邀请二维码

    Parameters
    ----------
    bot_username : str
        Bot 用户名 (不含 @)

    Returns
    -------
    io.BytesIO
        PNG 图片字节流
    """
    username = bot_username.lstrip("@")
    url = f"https://t.me/{username}"
    return generate_qr(url)

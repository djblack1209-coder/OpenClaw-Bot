"""
主动智能引擎 — Pydantic 结构化输出模型

搬运自 BasedHardware/omi 的三步管道结构:
  Gate(是否值得打扰) → Generate(生成通知) → Critic(人类视角审查)

> 从 proactive_engine.py 拆分 (HI-358)
"""

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    """Gate 判断结果 — 是否值得打扰严总"""
    is_relevant: bool = Field(
        default=False,
        description="True ONLY if there is a specific, concrete insight worth interrupting for",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="0.85+: critical action needed; 0.70-0.84: non-obvious insight; below: skip",
    )
    reasoning: str = Field(
        default="",
        description="具体原因，必须引用具体数据点",
    )


class NotificationDraft(BaseModel):
    """通知草稿"""
    notification_text: str = Field(
        default="",
        description="通知文本, 100字以内, 像朋友发微信",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
    )
    category: str = Field(
        default="info",
        description="money/risk/opportunity/reminder",
    )


class CriticResult(BaseModel):
    """Critic 审查结果"""
    approved: bool = Field(
        default=False,
        description="True ONLY if you would genuinely want to receive this notification",
    )
    reasoning: str = Field(default="")

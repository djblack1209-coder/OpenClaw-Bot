"""
金融新闻情绪分析服务 — 基于 HuggingFace Inference API (ProsusAI/finbert)
零本地依赖，仅使用 httpx (已在项目中安装)
"""
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────
_HF_MODEL = "ProsusAI/finbert"
_HF_API_URL = f"https://api-inference.huggingface.co/models/{_HF_MODEL}"
_TIMEOUT = 30.0

# FinBERT 标签到数值分的映射
_SENTIMENT_SCORES = {
    "positive": 1.0,
    "negative": -1.0,
    "neutral": 0.0,
}


def _get_hf_token() -> Optional[str]:
    """从环境变量获取 HuggingFace API Token (可选，无 Token 也可用免费额度)"""
    return os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")


async def analyze(text: str) -> Dict[str, Any]:
    """分析单条文本的金融情绪

    Parameters
    ----------
    text : str
        要分析的文本 (英文效果最佳，中文也可)

    Returns
    -------
    dict
        {
            "label": "positive" | "negative" | "neutral",
            "score": float,           # 该标签的置信度 0-1
            "sentiment_score": float,  # 标准化分数 -1 到 1
            "all_scores": dict,        # 所有标签的得分
        }
    """
    headers = {"Content-Type": "application/json"}
    token = _get_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {"inputs": text[:512]}  # FinBERT max 512 tokens

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_HF_API_URL, json=payload, headers=headers)

            # HF API 冷启动时返回 503
            if resp.status_code == 503:
                body = resp.json()
                wait_time = body.get("estimated_time", 20)
                logger.info("FinBERT 模型加载中，预计 %.0f 秒", wait_time)
                import asyncio
                await asyncio.sleep(min(wait_time, 30))
                resp = await client.post(_HF_API_URL, json=payload, headers=headers)

            resp.raise_for_status()
            result = resp.json()

        # HF 返回 [[{label, score}, ...]] 格式
        if isinstance(result, list) and result and isinstance(result[0], list):
            scores_list = result[0]
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            scores_list = result
        else:
            return {"label": "neutral", "score": 0.0, "sentiment_score": 0.0, "error": "unexpected_format"}

        # 找到最高分标签
        best = max(scores_list, key=lambda x: x.get("score", 0))
        label = best["label"].lower()

        all_scores = {s["label"].lower(): round(s["score"], 4) for s in scores_list}

        # 加权情绪分: positive * score - negative * score
        sentiment_score = (
            all_scores.get("positive", 0) * 1.0
            + all_scores.get("neutral", 0) * 0.0
            + all_scores.get("negative", 0) * -1.0
        )

        return {
            "label": label,
            "score": round(best["score"], 4),
            "sentiment_score": round(sentiment_score, 4),
            "all_scores": all_scores,
        }

    except httpx.HTTPStatusError as e:
        logger.warning("HF API 请求失败: %s %s", e.response.status_code, e.response.text[:200])
        return {"label": "neutral", "score": 0.0, "sentiment_score": 0.0, "error": str(e)}
    except Exception as e:
        logger.warning("情绪分析失败: %s", e)
        return {"label": "neutral", "score": 0.0, "sentiment_score": 0.0, "error": str(e)}


async def analyze_headlines(headlines: List[str]) -> List[Dict[str, Any]]:
    """批量分析标题列表

    Parameters
    ----------
    headlines : list[str]
        标题列表

    Returns
    -------
    list[dict]
        每条标题的分析结果列表，结构同 analyze() 返回值，
        额外附带 "text" 字段
    """
    import asyncio

    # HF 免费 API 有限流，串行请求 + 小间隔
    results = []
    for i, headline in enumerate(headlines):
        if not headline or not headline.strip():
            continue
        result = await analyze(headline.strip())
        result["text"] = headline.strip()
        results.append(result)
        # 避免触发限流 (免费 API ~30 req/min)
        if i < len(headlines) - 1:
            await asyncio.sleep(0.5)

    return results


async def get_stock_sentiment(
    symbol: str,
    headlines: List[str],
) -> Dict[str, Any]:
    """聚合某只股票的新闻情绪

    Parameters
    ----------
    symbol : str
        股票代码
    headlines : list[str]
        该股票相关新闻标题列表

    Returns
    -------
    dict
        {
            "symbol": str,
            "headline_count": int,
            "avg_sentiment": float,      # 平均情绪分 -1 到 1
            "positive_pct": float,       # 正面占比 0-100
            "negative_pct": float,       # 负面占比 0-100
            "neutral_pct": float,        # 中性占比 0-100
            "verdict": str,              # "Bullish" | "Bearish" | "Neutral"
            "details": list[dict],       # 逐条结果
        }
    """
    if not headlines:
        return {
            "symbol": symbol,
            "headline_count": 0,
            "avg_sentiment": 0.0,
            "positive_pct": 0.0,
            "negative_pct": 0.0,
            "neutral_pct": 0.0,
            "verdict": "No Data",
            "details": [],
        }

    details = await analyze_headlines(headlines)
    total = len(details) or 1

    pos_count = sum(1 for d in details if d["label"] == "positive")
    neg_count = sum(1 for d in details if d["label"] == "negative")
    neu_count = sum(1 for d in details if d["label"] == "neutral")

    avg_sentiment = sum(d["sentiment_score"] for d in details) / total

    # 判定
    if avg_sentiment > 0.2:
        verdict = "Bullish"
    elif avg_sentiment < -0.2:
        verdict = "Bearish"
    else:
        verdict = "Neutral"

    return {
        "symbol": symbol,
        "headline_count": total,
        "avg_sentiment": round(avg_sentiment, 4),
        "positive_pct": round(pos_count / total * 100, 1),
        "negative_pct": round(neg_count / total * 100, 1),
        "neutral_pct": round(neu_count / total * 100, 1),
        "verdict": verdict,
        "details": details,
    }

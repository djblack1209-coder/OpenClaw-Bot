"""Intel Brief dry-run brief builder.

This module transforms already-collected, real worker evidence into a local
Markdown dry-run brief. It intentionally performs no LLM calls, no Telegram push,
and no scheduler/service registration.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.content_contract import normalize_source_batch, parse_content_datetime
from src.intel.content_pipeline import ContentPipeline
from src.intel.quality.content_moderation import FILTER_PLACEHOLDER, moderate_items

_ALLOWED_MODERATION_STATUSES = {"allowed", "allowed_after_review"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _label_for_source(source: str) -> str:
    return {
        "senate_trading": "国会持仓",
        "akshare": "A股龙虎榜",
        "github_trending": "GitHub Trending",
        "ai_model_updates": "AI模型动态",
        "institutional_13f": "机构13F持仓",
        "weather": "天气监测",
    }.get(source, source or "unknown")


def _normalize_senate_item(
    raw: dict[str, Any],
    *,
    source: str,
    worker: str,
    fetched_at: str,
    evidence_path: str,
) -> dict[str, Any]:
    person = _clean(raw.get("person"))
    ticker = _clean(raw.get("ticker"))
    tx_type = _clean(raw.get("transaction_type"))
    amount = _clean(raw.get("amount"))
    tx_date = _clean(raw.get("transaction_date"))
    owner = _clean(raw.get("owner"))
    asset = _clean(raw.get("asset_description"))
    stable_key = f"{source}:{person.casefold()}|{ticker.casefold()}|{tx_date}|{tx_type.casefold()}|{amount}"
    title = " ".join(part for part in [person, tx_type, ticker] if part)
    if amount:
        title = f"{title}（{amount}）" if title else amount
    return {
        "source": source,
        "source_label": _label_for_source(source),
        "title": title or "国会持仓记录",
        "detail_lines": [
            line
            for line in [
                f"交易日期：{tx_date}" if tx_date else "",
                f"披露主体：{person}" if person else "",
                f"代码：{ticker}" if ticker else "",
                f"类型：{tx_type}" if tx_type else "",
                f"金额：{amount}" if amount else "",
                f"持有人：{owner}" if owner else "",
                f"资产：{asset}" if asset else "",
            ]
            if line
        ],
        "stable_key": stable_key,
        "stable_key_hash": _stable_hash(stable_key),
        "worker": worker,
        "fetched_at": fetched_at,
        "evidence_path": evidence_path,
    }


def _normalize_akshare_item(
    raw: dict[str, Any],
    *,
    source: str,
    worker: str,
    fetched_at: str,
    evidence_path: str,
) -> dict[str, Any]:
    code = _clean(raw.get("code"))
    name = _clean(raw.get("name"))
    reason = _clean(raw.get("reason"))
    close_price = _clean(raw.get("close_price"))
    stable_key = f"{source}:{code}|{name}|{reason}|{close_price}"
    title_base = f"{name}（{code}）" if code and name else name or code or "A股龙虎榜记录"
    title = f"{title_base}：{reason}" if reason else title_base
    return {
        "source": source,
        **({"category": _clean(raw.get("category"))} if _clean(raw.get("category")) else {}),
        **(
            {"category_aliases": [_clean(alias) for alias in raw.get("category_aliases", []) if _clean(alias)]}
            if isinstance(raw.get("category_aliases"), list)
            else {}
        ),
        "source_label": _label_for_source(source),
        "title": title,
        "detail_lines": [
            line
            for line in [
                f"代码：{code}" if code else "",
                f"名称：{name}" if name else "",
                f"上榜原因：{reason}" if reason else "",
                f"收盘价：{close_price}" if close_price else "",
            ]
            if line
        ],
        "stable_key": stable_key,
        "stable_key_hash": _stable_hash(stable_key),
        "worker": worker,
        "fetched_at": fetched_at,
        "evidence_path": evidence_path,
    }


def _normalize_generic_item(
    raw: dict[str, Any],
    *,
    source: str,
    worker: str,
    fetched_at: str,
    evidence_path: str,
    index: int,
) -> dict[str, Any]:
    title = _clean(raw.get("title") or raw.get("name") or raw.get("summary")) or f"{source} item {index + 1}"
    stable_material = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    stable_key = f"{source}:{_stable_hash(stable_material)}"
    detail_lines = [
        line
        for line in [
            f"提供方：{_clean(raw.get('provider'))}" if _clean(raw.get("provider")) else "",
            f"时间：{_clean(raw.get('published_at'))}" if _clean(raw.get("published_at")) else "",
            f"链接：{_clean(raw.get('url') or raw.get('link'))}" if _clean(raw.get("url") or raw.get("link")) else "",
            f"摘要：{_clean(raw.get('summary') or raw.get('description'))}"
            if _clean(raw.get("summary") or raw.get("description"))
            else "",
        ]
        if line
    ]
    return {
        "source": source,
        **({"category": _clean(raw.get("category"))} if _clean(raw.get("category")) else {}),
        **(
            {"category_aliases": [_clean(alias) for alias in raw.get("category_aliases", []) if _clean(alias)]}
            if isinstance(raw.get("category_aliases"), list)
            else {}
        ),
        "source_label": _label_for_source(source),
        "title": title,
        "detail_lines": detail_lines,
        "stable_key": stable_key,
        "stable_key_hash": _stable_hash(stable_key),
        "worker": worker,
        "fetched_at": fetched_at,
        "evidence_path": evidence_path,
    }


def normalize_collect_evidence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract source-specific display rows from collect-once evidence."""
    normalized: list[dict[str, Any]] = []
    for run in payload.get("runs", []) or []:
        if not isinstance(run, dict):
            continue
        source = _clean(run.get("source"))
        worker = _clean(run.get("worker"))
        evidence_path = _clean(run.get("evidence_path"))
        response = run.get("response") if isinstance(run.get("response"), dict) else {}
        fetched_at = _clean(response.get("fetched_at") if isinstance(response, dict) else "") or _clean(
            payload.get("timestamp")
        )
        items = response.get("items", []) if isinstance(response, dict) else []
        for index, raw in enumerate(items if isinstance(items, list) else []):
            if not isinstance(raw, dict):
                continue
            if source == "senate_trading":
                item = _normalize_senate_item(
                    raw,
                    source=source,
                    worker=worker,
                    fetched_at=fetched_at,
                    evidence_path=evidence_path,
                )
            elif source == "akshare":
                item = _normalize_akshare_item(
                    raw,
                    source=source,
                    worker=worker,
                    fetched_at=fetched_at,
                    evidence_path=evidence_path,
                )
            else:
                item = _normalize_generic_item(
                    raw,
                    source=source,
                    worker=worker,
                    fetched_at=fetched_at,
                    evidence_path=evidence_path,
                    index=index,
                )
            normalized.append(item)
    return normalized


def normalize_collect_evidence_v2(payload: dict[str, Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    """把全部采集结果转换为统一事实契约，并隔离坏行。"""
    normalized: list[Any] = []
    rejected: list[dict[str, Any]] = []
    for run in payload.get("runs", []) or []:
        if not isinstance(run, dict):
            continue
        source = _clean(run.get("source"))
        response = run.get("response") if isinstance(run.get("response"), dict) else {}
        rows = response.get("items", []) if isinstance(response, dict) else []
        if not isinstance(rows, list):
            rows = []
        batch = normalize_source_batch(
            source,
            rows,
            fetched_at=_clean(response.get("fetched_at")) or _clean(payload.get("timestamp")),
            evidence_path=_clean(run.get("evidence_path")),
        )
        normalized.extend(batch.items)
        rejected.extend(
            {
                "source": source,
                "index": item.index,
                "reason": item.reason,
            }
            for item in batch.rejected
        )
    return normalized, rejected


def _pipeline_display_item(
    candidate: Any,
    workers: dict[str, dict[str, str]],
    *,
    rank_position: int,
) -> dict[str, Any]:
    """把可审计候选转换为现有摘要和投递层兼容的公开字典。"""
    item = candidate.item
    source_meta = workers.get(item.source_name, {})
    stable_key = item.event_key
    return {
        **candidate.to_dict(),
        "source": item.source_name,
        "source_label": _label_for_source(item.source_name),
        "stable_key": stable_key,
        "stable_key_hash": _stable_hash(stable_key),
        "rank_score": candidate.score,
        "rank_position": rank_position,
        "worker": source_meta.get("worker", ""),
        "fetched_at": source_meta.get("fetched_at", item.observed_at.isoformat()),
        "detail_lines": [
            value
            for value in (
                f"时间：{item.published_at.isoformat()}" if item.published_at else "",
                f"来源：{item.provider}" if item.provider else "",
                f"链接：{item.source_url}" if item.source_url else "",
                f"摘要：{item.summary}" if item.summary else "",
            )
            if value
        ],
    }


def _run_content_pipeline_v2(
    payload: dict[str, Any],
    *,
    seen_event_keys: list[str] | None = None,
    recent_entity_observations: dict[str, str] | None = None,
    tracked_terms: list[str] | None = None,
    baseline_only_sources: list[str] | None = None,
    db_path: str | Path | None = None,
    run_key: str = "",
    source_coverage: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """执行生产内容 V2，并返回入选条目与全流程原因统计。"""
    normalized, normalization_rejections = normalize_collect_evidence_v2(payload)
    now = parse_content_datetime(payload.get("timestamp")) or datetime.now(timezone.utc)  # noqa: UP017
    pipeline = ContentPipeline().process(
        normalized,
        now=now,
        seen_event_keys=seen_event_keys or [],
        recent_entity_observations=recent_entity_observations or {},
        tracked_terms=tracked_terms or [],
        baseline_only_sources=baseline_only_sources or [],
    )
    if db_path is not None and run_key:
        from src.intel.db.store import persist_content_pipeline_run

        persist_content_pipeline_run(
            db_path,
            run_key=run_key,
            brief_date=now.date().isoformat(),
            items=list(normalized),
            pipeline_result=pipeline,
            source_coverage=source_coverage,
            baseline_only=bool(baseline_only_sources),
        )
    workers: dict[str, dict[str, str]] = {}
    for run in payload.get("runs", []) or []:
        if not isinstance(run, dict):
            continue
        response = run.get("response") if isinstance(run.get("response"), dict) else {}
        workers[_clean(run.get("source"))] = {
            "worker": _clean(run.get("worker")),
            "fetched_at": _clean(response.get("fetched_at")),
        }
    items = [
        _pipeline_display_item(candidate, workers, rank_position=rank_position)
        for rank_position, candidate in enumerate(pipeline.selected, 1)
    ]
    audit = {
        "enabled": True,
        "normalized_count": len(normalized),
        "normalization_rejected_count": len(normalization_rejections),
        "normalization_rejections": normalization_rejections,
        "seen_event_key_count": len(set(seen_event_keys or [])),
        "recent_entity_observation_count": len(recent_entity_observations or {}),
        "pipeline_counts": pipeline.counts,
        "rejected": [
            {
                "source": entry.item.source_name,
                "event_key": entry.item.event_key,
                "reason": entry.reason,
                "detail": entry.detail,
            }
            for entry in pipeline.rejected
        ],
        "excluded": [
            {
                "source": entry.item.source_name,
                "event_key": entry.item.event_key,
                "reason": entry.reason,
            }
            for entry in pipeline.excluded
        ],
    }
    return items, audit


def deduplicate_brief_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep the first item per stable_key and report dropped duplicate count."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        key = _clean(item.get("stable_key")) or _stable_hash(json.dumps(item, ensure_ascii=False, sort_keys=True))
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped, dropped


def _apply_moderation(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    moderated = moderate_items(items, text_key="title", source_key="source")
    blocked = 0
    sanitized: list[dict[str, Any]] = []
    for item in moderated:
        copied = dict(item)
        status = _clean(copied.get("moderation_status"))
        if status and status not in _ALLOWED_MODERATION_STATUSES:
            blocked += 1
            copied["title"] = FILTER_PLACEHOLDER
            copied["detail_lines"] = [FILTER_PLACEHOLDER]
            copied.pop("stable_key", None)
        sanitized.append(copied)
    return sanitized, blocked


def _source_summaries(payload: dict[str, Any], rendered_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rendered_by_source: dict[str, int] = defaultdict(int)
    for item in rendered_items:
        rendered_by_source[_clean(item.get("source"))] += 1

    summaries: list[dict[str, Any]] = []
    for run in payload.get("runs", []) or []:
        if not isinstance(run, dict):
            continue
        source = _clean(run.get("source"))
        response = run.get("response") if isinstance(run.get("response"), dict) else {}
        input_items = response.get("items", []) if isinstance(response, dict) else []
        summaries.append(
            {
                "source": source,
                "source_label": _label_for_source(source),
                "status": _clean(run.get("status")),
                "worker": _clean(run.get("worker")),
                "fetched_at": _clean(response.get("fetched_at") if isinstance(response, dict) else ""),
                "raw_count": int(response.get("raw_count") or 0) if isinstance(response, dict) else 0,
                "input_items": len(input_items) if isinstance(input_items, list) else 0,
                "rendered_items": rendered_by_source[source],
                "evidence_path": _clean(run.get("evidence_path")),
            }
        )
    return summaries


def _render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Intel Brief Dry Run",
        "",
        f"- 生成时间：{result['timestamp']}",
        f"- 输入证据：`{result['input_evidence']}`",
        f"- JSON证据：`{result['json_evidence']}`",
        "- 边界：No LLM call；No Telegram push；No scheduler registration。",
        "",
        "## 验收摘要",
        "",
        f"- 数据源数：{result['summary']['source_count']}",
        f"- 去重前条目：{result['summary']['item_count_before_dedup']}",
        f"- 去重丢弃：{result['summary']['deduped_count']}",
        f"- 内容过滤/待复核：{result['summary']['moderated_count']}",
        f"- 渲染条目：{result['summary']['rendered_count']}",
        "",
        "## 数据源执行证据",
        "",
    ]
    for summary in result["source_summaries"]:
        lines.append(
            "- "
            f"{summary['source_label']}（{summary['source']}）：{summary['status']}；"
            f"worker={summary['worker']}；raw_count={summary['raw_count']}；"
            f"rendered={summary['rendered_items']}；evidence=`{summary['evidence_path']}`"
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in result["items"]:
        grouped[_clean(item.get("source_label"))].append(item)

    lines.extend(["", "## Dry-run 简报正文", ""])
    if not result["items"]:
        lines.append("本次没有可渲染条目。")
    for label, items in grouped.items():
        lines.extend([f"### {label}", ""])
        for item in items:
            lines.append(f"- **{item['title']}**")
            for detail in item.get("detail_lines", []):
                lines.append(f"  - {detail}")
            lines.append(f"  - 来源worker：{item.get('worker', '')}；抓取时间：{item.get('fetched_at', '')}")
        lines.append("")

    lines.extend(
        [
            "## 质控与未验证边界",
            "",
            "- 已执行：source-specific normalization、stable-key 去重、统一内容过滤入口。",
            "- 未执行：LLM摘要、Telegram推送、调度注册、生产DB写入。",
            "- 回滚边界：删除本次 dry-run Markdown/JSON 证据文件即可；未创建常驻进程。",
            "",
        ]
    )
    return "\n".join(lines)


def _public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in items:
        copied = dict(item)
        if _clean(copied.get("moderation_status")) not in {"", *_ALLOWED_MODERATION_STATUSES}:
            copied.pop("stable_key", None)
        public.append(copied)
    return public


def build_brief_dry_run(
    *,
    collect_evidence_path: str | Path,
    markdown_output_path: str | Path,
    json_output_path: str | Path,
    stamp: str | None = None,
    content_pipeline_v2: bool = False,
    seen_event_keys: list[str] | None = None,
    recent_entity_observations: dict[str, str] | None = None,
    tracked_terms: list[str] | None = None,
    baseline_only_sources: list[str] | None = None,
    db_path: str | Path | None = None,
    run_key: str = "",
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Markdown/JSON dry-run evidence from collect-once evidence."""
    collect_path = Path(collect_evidence_path)
    markdown_path = Path(markdown_output_path)
    json_path = Path(json_output_path)
    payload = json.loads(collect_path.read_text(encoding="utf-8"))

    content_quality: dict[str, Any] = {"enabled": False}
    if content_pipeline_v2:
        normalized, content_quality = _run_content_pipeline_v2(
            payload,
            seen_event_keys=seen_event_keys,
            recent_entity_observations=recent_entity_observations,
            tracked_terms=tracked_terms,
            baseline_only_sources=baseline_only_sources,
            db_path=db_path,
            run_key=run_key,
            source_coverage=source_coverage,
        )
        deduped = normalized
        pipeline_counts = content_quality.get("pipeline_counts", {})
        dropped = int(pipeline_counts.get("rejected", 0)) + int(pipeline_counts.get("excluded", 0))
    else:
        normalized = normalize_collect_evidence(payload)
        deduped, dropped = deduplicate_brief_items(normalized)
    moderated, moderated_count = _apply_moderation(deduped)
    public_items = _public_items(moderated)
    source_summaries = _source_summaries(payload, public_items)
    source_count = len({summary["source"] for summary in source_summaries if summary["source"]})

    result: dict[str, Any] = {
        "timestamp": _now_iso(),
        "stamp": stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),  # noqa: UP017 - Python 3.10 worker compatibility
        "phase": "F-brief-dry-run",
        "scope": "collect_evidence_to_moderated_markdown",
        "status": "success" if public_items else "empty",
        "input_evidence": str(collect_path),
        "output_markdown": str(markdown_path),
        "json_evidence": str(json_path),
        "summary": {
            "source_count": source_count,
            "item_count_before_dedup": int(content_quality.get("normalized_count", len(normalized))),
            "deduped_count": dropped,
            "moderated_count": moderated_count,
            "rendered_count": len(public_items),
        },
        "source_summaries": source_summaries,
        "items": public_items,
        "content_quality": content_quality,
        "limits": [
            "No LLM call.",
            "No Telegram push.",
            "No scheduler registration.",
            "Transforms existing collect-once evidence only; does not contact external data sources.",
        ],
    }
    markdown = _render_markdown(result)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

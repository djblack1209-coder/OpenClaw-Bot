from __future__ import annotations

import json

from src.intel.brief_builder import build_brief_dry_run, deduplicate_brief_items, normalize_collect_evidence


def _collect_payload() -> dict:
    return {
        "timestamp": "2026-07-07T00:22:08+00:00",
        "phase": "F-pre",
        "scope": "intel_collect_once_multi_source",
        "status": "success",
        "sources": ["senate_trading", "akshare"],
        "summary": {"success": 2, "failed": 0},
        "runs": [
            {
                "source": "senate_trading",
                "status": "success",
                "worker": "oracle-arm1-overseas-fallback",
                "evidence_path": "/evidence/senate.json",
                "response": {
                    "status": "success",
                    "fetched_at": "2026-07-07T00:20:41+00:00",
                    "raw_count": 1,
                    "items": [
                        {
                            "amount": "$50,001 - $100,000",
                            "asset_description": "Beyond Meat, Inc.",
                            "owner": "Spouse",
                            "person": "Ron L Wyden",
                            "ptr_link": "https://efdsearch.senate.gov/search/view/ptr/a0010f4a/",
                            "source": "senate-stock-watcher-data",
                            "ticker": "BYND",
                            "transaction_date": "11/10/2020",
                            "transaction_type": "Sale (Full)",
                        }
                    ],
                },
            },
            {
                "source": "akshare",
                "status": "success",
                "worker": "yanhuoyun-domestic",
                "evidence_path": "/evidence/akshare.json",
                "response": {
                    "status": "success",
                    "fetched_at": "2026-07-07T00:21:24+00:00",
                    "raw_count": 1,
                    "items": [
                        {
                            "close_price": "20.7",
                            "code": "000021",
                            "name": "深科技",
                            "reason": "1家机构买入，成功率46.03%",
                            "source": "akshare_stock_lhb_detail_em",
                        }
                    ],
                },
            },
        ],
        "limits": ["One-shot collection only; no scheduler registration or service deployment."],
    }


def test_normalize_collect_evidence_extracts_source_specific_display_rows():
    items = normalize_collect_evidence(_collect_payload())

    assert [item["source"] for item in items] == ["senate_trading", "akshare"]
    assert items[0]["source_label"] == "国会持仓"
    assert items[0]["stable_key"] == "senate_trading:ron l wyden|bynd|11/10/2020|sale (full)|$50,001 - $100,000"
    assert "Ron L Wyden" in items[0]["title"]
    assert "BYND" in items[0]["title"]
    assert items[1]["source_label"] == "A股龙虎榜"
    assert items[1]["stable_key"] == "akshare:000021|深科技|1家机构买入，成功率46.03%|20.7"
    assert "深科技" in items[1]["title"]


def test_normalize_collect_evidence_preserves_weather_subcategory_aliases():
    payload = _collect_payload()
    payload["sources"].append("weather")
    payload["runs"].append(
        {
            "source": "weather",
            "status": "success",
            "worker": "oracle-sg-west-preferred-overseas",
            "evidence_path": "/evidence/weather.json",
            "response": {
                "status": "success",
                "fetched_at": "2026-07-07T00:22:00+00:00",
                "raw_count": 1,
                "items": [
                    {
                        "source": "weather",
                        "category": "temperature",
                        "category_aliases": ["weather", "temperature"],
                        "title": "Denver, CO 温度：72°F",
                        "summary": "体感舒适",
                    }
                ],
            },
        }
    )

    items = normalize_collect_evidence(payload)

    assert items[-1]["source"] == "weather"
    assert items[-1]["category"] == "temperature"
    assert items[-1]["category_aliases"] == ["weather", "temperature"]
    assert items[-1]["source_label"] == "天气监测"
    assert items[-1]["title"] == "Denver, CO 温度：72°F"


def test_deduplicate_brief_items_keeps_first_stable_key():
    items = normalize_collect_evidence(_collect_payload())
    duplicated = [*items, dict(items[0], worker="another-worker")]

    deduped, dropped = deduplicate_brief_items(duplicated)

    assert len(deduped) == 2
    assert dropped == 1
    assert deduped[0]["worker"] == "oracle-arm1-overseas-fallback"


def test_build_brief_dry_run_writes_markdown_and_json_with_limits(tmp_path):
    collect_path = tmp_path / "collect.json"
    markdown_path = tmp_path / "dry-run.md"
    json_path = tmp_path / "dry-run.json"
    collect_path.write_text(json.dumps(_collect_payload(), ensure_ascii=False), encoding="utf-8")

    result = build_brief_dry_run(
        collect_evidence_path=collect_path,
        markdown_output_path=markdown_path,
        json_output_path=json_path,
        stamp="20260707T003000Z",
    )

    assert result["status"] == "success"
    assert result["summary"] == {
        "source_count": 2,
        "item_count_before_dedup": 2,
        "deduped_count": 0,
        "moderated_count": 0,
        "rendered_count": 2,
    }
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Intel Brief Dry Run" in markdown
    assert "No LLM call" in markdown
    assert "No Telegram push" in markdown
    assert "No scheduler registration" in markdown
    assert "Ron L Wyden" in markdown
    assert "深科技" in markdown
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["input_evidence"] == str(collect_path)
    assert saved["output_markdown"] == str(markdown_path)
    assert saved["source_summaries"][0]["worker"] == "oracle-arm1-overseas-fallback"


def test_build_brief_dry_run_applies_moderation_before_rendering(tmp_path):
    payload = _collect_payload()
    payload["runs"][1]["response"]["items"][0]["reason"] = "台海相关题材异动"
    collect_path = tmp_path / "collect.json"
    markdown_path = tmp_path / "dry-run.md"
    json_path = tmp_path / "dry-run.json"
    collect_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = build_brief_dry_run(
        collect_evidence_path=collect_path,
        markdown_output_path=markdown_path,
        json_output_path=json_path,
        stamp="20260707T003100Z",
    )

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "该条内容已过滤" in markdown
    assert "台海相关题材异动" not in markdown
    assert result["summary"]["moderated_count"] == 1
    saved_text = json_path.read_text(encoding="utf-8")
    assert "台海相关题材异动" not in saved_text
    saved = json.loads(saved_text)
    assert saved["items"][1]["moderation_status"] == "needs_review"
    assert saved["items"][1]["moderation_matched_keywords"] == ["台海"]
    assert "stable_key_hash" in saved["items"][1]


def test_intel_brief_dry_run_cli_writes_outputs(tmp_path):
    from scripts.intel_brief_dry_run import main

    collect_path = tmp_path / "collect.json"
    markdown_path = tmp_path / "cli-dry-run.md"
    json_path = tmp_path / "cli-dry-run.json"
    collect_path.write_text(json.dumps(_collect_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--collect-evidence",
            str(collect_path),
            "--markdown-output",
            str(markdown_path),
            "--json-output",
            str(json_path),
            "--stamp",
            "20260707T003200Z",
        ]
    )

    assert exit_code == 0
    assert markdown_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["stamp"] == "20260707T003200Z"

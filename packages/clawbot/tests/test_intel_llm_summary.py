from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.intel.llm_summary import (
    build_intel_summary_prompt,
    build_llm_summary_dry_run,
    select_llm_family_for_profile,
    summarize_items_with_llm,
)
from src.llm_routing_config import get_routing_profile, load_routing_config


def _dry_run_payload() -> dict:
    return {
        "timestamp": "2026-07-07T00:37:55+00:00",
        "phase": "F-brief-dry-run",
        "scope": "collect_evidence_to_moderated_markdown",
        "status": "success",
        "input_evidence": "packages/clawbot/data/intel_evidence/phasef/collect.json",
        "summary": {
            "source_count": 2,
            "item_count_before_dedup": 2,
            "deduped_count": 0,
            "moderated_count": 0,
            "rendered_count": 2,
        },
        "source_summaries": [
            {"source": "senate_trading", "source_label": "国会持仓", "worker": "oracle-arm1-overseas-fallback"},
            {"source": "akshare", "source_label": "A股龙虎榜", "worker": "yanhuoyun-domestic"},
        ],
        "items": [
            {
                "source": "senate_trading",
                "source_label": "国会持仓",
                "title": "Ron L Wyden Sale (Full) BYND（$50,001 - $100,000）",
                "detail_lines": ["交易日期：11/10/2020", "资产：Beyond Meat, Inc."],
            },
            {
                "source": "akshare",
                "source_label": "A股龙虎榜",
                "title": "深科技（000021）：1家机构买入，成功率46.03%",
                "detail_lines": ["上榜原因：1家机构买入，成功率46.03%", "收盘价：20.7"],
            },
        ],
    }


def test_llm_routing_config_has_intel_brief_profile():
    profile = get_routing_profile({"routing_profiles": {"intel_brief": {"preferred_families": ["qwen"]}}}, "intel_brief")

    assert profile["preferred_families"] == ["qwen"]




def test_default_llm_routing_config_registers_intel_brief_profile():
    profile = get_routing_profile(load_routing_config(), "intel_brief")

    assert profile["preferred_families"][:2] == ["qwen", "gemini"]
    assert profile["dry_run_families"][0] == "intel_local"
    assert "gemma" in profile["dry_run_families"]
    assert profile["max_tokens"] <= 1000

def test_select_llm_family_for_profile_uses_first_available_family():
    profile = {"preferred_families": ["qwen", "gemma", "g4f"], "max_tokens": 500}

    assert select_llm_family_for_profile(profile, available_families={"gemma", "g4f"}) == "gemma"
    assert select_llm_family_for_profile(profile, available_families=set()) == "qwen"


def test_build_intel_summary_prompt_includes_real_dry_run_items():
    prompt = build_intel_summary_prompt(_dry_run_payload()["items"], source_summaries=_dry_run_payload()["source_summaries"])

    assert "Ron L Wyden" in prompt
    assert "深科技" in prompt
    assert "国会持仓" in prompt
    assert "A股龙虎榜" in prompt
    assert "不要编造" in prompt


def test_summarize_items_with_llm_uses_injected_completion_and_records_tokens():
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="<think>hidden</think>今日重点：BYND 披露和深科技龙虎榜。"))],
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45, total_tokens=168),
        )

    result = asyncio.run(
        summarize_items_with_llm(
            _dry_run_payload()["items"],
            source_summaries=_dry_run_payload()["source_summaries"],
            profile={"preferred_families": ["gemma"], "max_tokens": 300},
            available_families={"gemma"},
            completion_fn=fake_completion,
        )
    )

    assert result["status"] == "success"
    assert result["model_family"] == "gemma"
    assert result["summary_text"] == "今日重点：BYND 披露和深科技龙虎榜。"
    assert result["usage"] == {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
    assert calls[0]["model_family"] == "gemma"
    assert calls[0]["max_tokens"] == 300


def test_summarize_items_with_llm_returns_fallback_evidence_on_failure():
    async def failing_completion(**kwargs):
        raise RuntimeError("local llm unavailable")

    result = asyncio.run(
        summarize_items_with_llm(
            _dry_run_payload()["items"],
            source_summaries=_dry_run_payload()["source_summaries"],
            profile={"preferred_families": ["gemma"], "max_tokens": 300},
            available_families={"gemma"},
            completion_fn=failing_completion,
        )
    )

    assert result["status"] == "fallback"
    assert result["llm_success"] is False
    assert result["error_type"] == "RuntimeError"
    assert "BYND" in result["summary_text"]
    assert "深科技" in result["summary_text"]


def test_build_llm_summary_dry_run_writes_markdown_and_json(tmp_path):
    dry_run_path = tmp_path / "brief-dry-run.json"
    markdown_path = tmp_path / "summary.md"
    json_path = tmp_path / "summary.json"
    dry_run_path.write_text(json.dumps(_dry_run_payload(), ensure_ascii=False), encoding="utf-8")

    async def fake_completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="今日重点：国会持仓与A股龙虎榜各1条。"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    result = asyncio.run(
        build_llm_summary_dry_run(
            dry_run_json_path=dry_run_path,
            markdown_output_path=markdown_path,
            json_output_path=json_path,
            stamp="20260707T005000Z",
            profile={"preferred_families": ["gemma"], "max_tokens": 300},
            available_families={"gemma"},
            completion_fn=fake_completion,
        )
    )

    assert result["status"] == "success"
    assert result["llm"]["llm_success"] is True
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Intel Brief LLM Summary Dry Run" in markdown
    assert "今日重点：国会持仓与A股龙虎榜各1条。" in markdown
    assert "No Telegram push" in markdown
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["input_dry_run_evidence"] == str(dry_run_path)
    assert saved["output_markdown"] == str(markdown_path)




def test_build_llm_summary_dry_run_family_override_uses_local_family(tmp_path):
    dry_run_path = tmp_path / "brief-dry-run.json"
    markdown_path = tmp_path / "summary.md"
    json_path = tmp_path / "summary.json"
    dry_run_path.write_text(json.dumps(_dry_run_payload(), ensure_ascii=False), encoding="utf-8")
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="本地模型摘要。"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

    result = asyncio.run(
        build_llm_summary_dry_run(
            dry_run_json_path=dry_run_path,
            markdown_output_path=markdown_path,
            json_output_path=json_path,
            stamp="20260707T005200Z",
            profile={"preferred_families": ["qwen"], "max_tokens": 300},
            available_families={"qwen", "gemma"},
            family_override="gemma",
            completion_fn=fake_completion,
        )
    )

    assert result["llm"]["model_family"] == "gemma"
    assert calls[0]["model_family"] == "gemma"

def test_intel_llm_summary_dry_run_cli_writes_outputs(tmp_path):
    from scripts.intel_llm_summary_dry_run import main

    dry_run_path = tmp_path / "brief-dry-run.json"
    markdown_path = tmp_path / "summary.md"
    json_path = tmp_path / "summary.json"
    dry_run_path.write_text(json.dumps(_dry_run_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--dry-run-json",
            str(dry_run_path),
            "--markdown-output",
            str(markdown_path),
            "--json-output",
            str(json_path),
            "--mode",
            "fallback-only",
            "--max-tokens",
            "120",
            "--stamp",
            "20260707T005100Z",
        ]
    )

    assert exit_code == 0
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["stamp"] == "20260707T005100Z"
    assert saved["llm"]["llm_attempted"] is False
    assert saved["profile"]["max_tokens"] == 120
    assert markdown_path.exists()

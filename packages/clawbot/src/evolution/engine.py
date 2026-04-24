"""
OpenClaw Evolution Engine — 自主进化核心

核心能力:
1. 扫描 GitHub 趋势项目
2. 用 LLM 评估每个项目对 OpenClaw 的价值
3. 生成集成提案 (EvolutionProposal)
4. 低风险自动集成，高风险推送审批
5. 记录进化历史

用法:
    from src.evolution.engine import EvolutionEngine
    engine = EvolutionEngine()
    proposals = await engine.daily_scan()
"""
import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.utils import now_et

from .github_trending import (
    TrendingRepo,
    fetch_fast_growing_repos,
    fetch_readme,
    fetch_trending,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 数据路径
# ──────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # packages/clawbot/
DATA_DIR = _BASE_DIR / "data" / "evolution"
PROPOSALS_DIR = DATA_DIR / "proposals"
HISTORY_FILE = DATA_DIR / "history.jsonl"
CONFIG_FILE = DATA_DIR / "config.json"


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

@dataclass
class EvolutionProposal:
    """一个进化集成提案"""
    id: str                          # UUID
    repo_url: str
    repo_name: str
    stars: int
    growth_rate: int                 # 周期内新增 star
    description: str
    target_module: str               # perception/action/social/trading/memory/evolution
    value_score: float               # 1-10
    difficulty: float                # 1-10
    risk_level: str                  # LOW/MEDIUM/HIGH
    integration_approach: str        # 推荐的集成方式
    status: str = "proposed"         # proposed/approved/integrated/rejected
    created_at: str = ""
    evaluated_by: str = ""           # 哪个 LLM 模型
    llm_reasoning: str = ""          # LLM 的评估原文
    repo_language: str = ""
    repo_topics: list[str] = field(default_factory=list)
    matched_gap: str = ""            # 匹配到的能力缺口

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_et().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "EvolutionProposal":
        # 过滤掉 dataclass 不接受的多余字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class ScanResult:
    """一次扫描的结果摘要"""
    scan_id: str
    timestamp: str
    repos_scanned: int
    repos_evaluated: int
    proposals_generated: int
    proposals: list[EvolutionProposal]
    errors: list[str]
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scan_id": self.scan_id,
            "timestamp": self.timestamp,
            "repos_scanned": self.repos_scanned,
            "repos_evaluated": self.repos_evaluated,
            "proposals_generated": self.proposals_generated,
            "proposal_ids": [p.id for p in self.proposals],
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


# ──────────────────────────────────────────────
# Capability Gap Map
# ──────────────────────────────────────────────

DEFAULT_CAPABILITY_GAPS: list[dict[str, str]] = [
    {
        "module": "perception",
        "gap": "real_time_market_sentiment",
        "description": "实时市场情绪分析 — 从新闻、社交媒体、链上数据提取情绪信号",
        "keywords": "sentiment analysis,market sentiment,news nlp,social listening",
    },
    {
        "module": "perception",
        "gap": "multi_modal_analysis",
        "description": "多模态感知 — 图表识别、视频分析、音频转录",
        "keywords": "multimodal,chart recognition,video analysis,ocr,vision",
    },
    {
        "module": "action",
        "gap": "browser_automation",
        "description": "增强的浏览器自动化 — 更可靠的网页交互和数据提取",
        "keywords": "browser automation,web scraping,playwright,puppeteer,selenium",
    },
    {
        "module": "social",
        "gap": "content_generation",
        "description": "高质量内容生成 — 长文、视频脚本、信息图表",
        "keywords": "content generation,copywriting,video script,infographic",
    },
    {
        "module": "social",
        "gap": "community_management",
        "description": "社区管理自动化 — Discord/Telegram 群组管理、用户互动",
        "keywords": "community management,discord bot,telegram bot,moderation",
    },
    {
        "module": "trading",
        "gap": "advanced_ta",
        "description": "高级技术分析 — ML 驱动的信号检测、模式识别",
        "keywords": "technical analysis,trading signals,pattern recognition,backtesting,quant",
    },
    {
        "module": "trading",
        "gap": "defi_integration",
        "description": "DeFi 协议集成 — DEX 交易、yield farming、链上分析",
        "keywords": "defi,dex,uniswap,yield farming,on-chain,blockchain",
    },
    {
        "module": "memory",
        "gap": "knowledge_graph",
        "description": "知识图谱 — 结构化知识存储与推理、关系发现",
        "keywords": "knowledge graph,graph database,neo4j,reasoning,rag",
    },
    {
        "module": "memory",
        "gap": "long_term_planning",
        "description": "长期规划与记忆 — 持久化目标跟踪、经验学习",
        "keywords": "long term memory,planning,goal tracking,experience replay",
    },
    {
        "module": "evolution",
        "gap": "self_improvement",
        "description": "自我改进框架 — 自动代码生成、测试、部署",
        "keywords": "self improvement,auto coding,code generation,agentic,autonomous",
    },
    {
        "module": "evolution",
        "gap": "plugin_system",
        "description": "插件系统 — 动态加载/卸载能力模块",
        "keywords": "plugin system,dynamic loading,modular,extensible,mcp",
    },
]

# ──────────────────────────────────────────────
# LLM Evaluation Prompt
# ──────────────────────────────────────────────

_EVALUATION_SYSTEM_PROMPT = """\
你是 OpenClaw 的进化引擎评估模块。你的任务是评估一个 GitHub 开源项目对 OpenClaw 系统的集成价值。

OpenClaw 是一个自主 AI Agent 系统，包含以下核心模块:
- perception: 感知层 — 数据采集、OCR、图像理解、市场数据
- action: 行动层 — 浏览器自动化、API 调用、工具执行
- social: 社交层 — X/小红书发帖、社区互动、内容生成
- trading: 交易层 — IBKR 交易、技术分析、AI 投票、风控
- memory: 记忆层 — 向量存储、知识图谱、对话历史
- evolution: 进化层 — 自我升级、能力发现、GitHub 扫描

你必须严格按 JSON 格式回答，不要添加任何额外文字。"""

_EVALUATION_USER_PROMPT = """\
请评估以下 GitHub 项目对 OpenClaw 系统的集成价值:

**项目**: {repo_name}
**Star 数**: {stars} (最近新增: {growth_rate})
**语言**: {language}
**描述**: {description}
**Topics**: {topics}

**README 摘要**:
{readme_excerpt}

**OpenClaw 当前能力缺口**:
{capability_gaps}

请输出严格的 JSON (不要 markdown 代码块):
{{
    "summary": "一句话概括这个项目做什么",
    "target_module": "最匹配的 OpenClaw 模块 (perception/action/social/trading/memory/evolution 之一)",
    "value_score": 1到10的整数,
    "difficulty": 1到10的整数 (集成难度),
    "risk_level": "LOW 或 MEDIUM 或 HIGH",
    "integration_approach": "推荐的集成方式 (100字以内)",
    "reasoning": "评估理由 (200字以内)",
    "matched_gap": "匹配到的能力缺口名称 (如果有)"
}}"""


# ──────────────────────────────────────────────
# Evolution Engine
# ──────────────────────────────────────────────

class EvolutionEngine:
    """
    OpenClaw 进化引擎

    核心能力:
    1. 扫描 GitHub 趋势项目
    2. 用 LLM 评估每个项目对 OpenClaw 的价值
    3. 生成集成提案 (EvolutionProposal)
    4. 低风险自动集成，高风险推送审批
    5. 记录进化历史
    """

    def __init__(
        self,
        min_stars: int = 500,
        languages: list[str] | None = None,
        github_token: str | None = None,
    ):
        self.min_stars = min_stars
        self.languages = languages or ["python", "typescript", "javascript"]
        self.github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._capability_gaps = list(DEFAULT_CAPABILITY_GAPS)
        self._config = self._load_config()

        # 确保数据目录存在
        PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    # ──────────────── Config ────────────────

    def _load_config(self) -> dict:
        """加载或创建默认配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("[evolution] Failed to load config: %s", e)

        default = {
            "min_stars": self.min_stars,
            "languages": self.languages,
            "scan_since": "weekly",
            "max_proposals_per_scan": 10,
            "auto_approve_threshold": 8.0,    # value_score >= 8 且 risk=LOW 自动批准
            "notify_threshold": 5.0,          # value_score >= 5 发通知
            "scan_interval_hours": 24,
            "last_scan_time": "",
        }
        self._save_config(default)
        return default

    def _save_config(self, config: dict) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    # ──────────────── Main Scan Loop ────────────────

    async def daily_scan(self) -> list[EvolutionProposal]:
        """
        主进化扫描循环:
        1. 采集 GitHub trending + 快速增长仓库
        2. 过滤 (语言、star 数)
        3. LLM 评估价值
        4. 生成提案并保存
        5. 通知高价值提案
        """
        import time
        t0 = time.time()
        scan_id = str(uuid.uuid4())[:8]
        errors: list[str] = []
        all_proposals: list[EvolutionProposal] = []

        logger.info("[evolution] === Scan %s started ===", scan_id)

        # ─── Step 1: 采集候选仓库 ───
        candidates: list[TrendingRepo] = []

        # 1a. GitHub Trending (每种语言)
        for lang in self.languages:
            try:
                trending = await fetch_trending(
                    language=lang,
                    since=self._config.get("scan_since", "weekly"),
                )
                candidates.extend(trending)
            except Exception as e:
                msg = f"trending({lang}) failed: {e}"
                logger.warning("[evolution] %s", msg)
                errors.append(msg)

        # 1b. GitHub Search API (综合)
        try:
            fast_growing = await fetch_fast_growing_repos(
                days_back=7,
                min_stars=self.min_stars,
                token=self.github_token,
            )
            candidates.extend(fast_growing)
        except Exception as e:
            msg = f"search_api failed: {e}"
            logger.warning("[evolution] %s", msg)
            errors.append(msg)

        # ─── Step 2: 去重 + 过滤 ───
        seen_names = set()
        filtered: list[TrendingRepo] = []
        for repo in candidates:
            if repo.name in seen_names:
                continue
            seen_names.add(repo.name)

            # 语言过滤
            if repo.language and repo.language.lower() not in [l.lower() for l in self.languages]:
                continue

            # Star 数过滤
            if repo.stars < self.min_stars:
                continue

            filtered.append(repo)

        logger.info(
            "[evolution] Collected %d candidates, %d after filter",
            len(candidates), len(filtered),
        )

        # ─── Step 3: LLM 评估 ───
        max_eval = self._config.get("max_proposals_per_scan", 10)
        evaluated = 0

        for repo in filtered[:max_eval * 2]:  # 多评估一些，因为有些可能失败
            if evaluated >= max_eval:
                break
            try:
                proposal = await self._evaluate_relevance(repo)
                if proposal and proposal.value_score >= self._config.get("notify_threshold", 5.0):
                    all_proposals.append(proposal)
                    self._save_proposal(proposal)

                    # 通知
                    await self._notify_proposal(proposal)

                    # Synergy: 进化发现 → 全模块广播
                    try:
                        from src.synergy import get_synergy
                        await get_synergy().on_evolution_proposal(proposal.to_dict())
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)

                    # 高价值 + 低风险 → 自动批准
                    auto_threshold = self._config.get("auto_approve_threshold", 8.0)
                    if proposal.value_score >= auto_threshold and proposal.risk_level == "LOW":
                        proposal.status = "approved"
                        self._save_proposal(proposal)  # 更新状态
                        logger.info(
                            "[evolution] Auto-approved: %s (value=%.1f, risk=%s)",
                            proposal.repo_name, proposal.value_score, proposal.risk_level,
                        )

                evaluated += 1
            except Exception as e:
                msg = f"eval({repo.name}) failed: {e}"
                logger.warning("[evolution] %s", msg)
                errors.append(msg)

        # ─── Step 4: 记录扫描历史 ───
        duration = time.time() - t0
        scan_result = ScanResult(
            scan_id=scan_id,
            timestamp=now_et().isoformat(),
            repos_scanned=len(candidates),
            repos_evaluated=evaluated,
            proposals_generated=len(all_proposals),
            proposals=all_proposals,
            errors=errors,
            duration_seconds=round(duration, 2),
        )
        self._append_history(scan_result)

        # 更新上次扫描时间
        self._config["last_scan_time"] = now_et().isoformat()
        self._save_config(self._config)

        logger.info(
            "[evolution] === Scan %s complete: %d proposals in %.1fs ===",
            scan_id, len(all_proposals), duration,
        )

        return all_proposals

    # ──────────────── LLM Evaluation ────────────────

    async def _evaluate_relevance(self, repo: TrendingRepo) -> EvolutionProposal | None:
        """
        用 LLM 评估一个仓库对 OpenClaw 的集成价值。
        返回 EvolutionProposal 或 None (如果评估失败或价值太低)。
        """
        from src.execution._ai import ai_pool

        # 获取 README
        readme = await fetch_readme(repo.name, token=self.github_token)
        if not readme:
            readme = "(README not available)"

        # 构建能力缺口描述
        gaps_text = "\n".join(
            f"- [{g['module']}] {g['gap']}: {g['description']}"
            for g in self._capability_gaps
        )

        # 构建 prompt
        prompt = _EVALUATION_USER_PROMPT.format(
            repo_name=repo.name,
            stars=repo.stars,
            growth_rate=repo.stars_today,
            language=repo.language or "unknown",
            description=repo.description or "(no description)",
            topics=", ".join(repo.topics) if repo.topics else "(none)",
            readme_excerpt=readme[:4000],
            capability_gaps=gaps_text,
        )

        # 调用 LLM
        result = await ai_pool.call(prompt, system_prompt=_EVALUATION_SYSTEM_PROMPT)

        if not result.get("success"):
            logger.debug("[evolution] LLM unavailable for %s, using heuristic scoring", repo.name)
            return self._heuristic_evaluate(repo, readme)

        raw_text = result.get("raw", "")
        bot_id = result.get("bot_id", "unknown")

        # 解析 JSON 响应
        eval_data = self._parse_llm_json(raw_text)
        if not eval_data:
            logger.debug("[evolution] LLM JSON parse failed for %s, using heuristic", repo.name)
            return self._heuristic_evaluate(repo, readme)

        # 构建 Proposal
        value_score = float(eval_data.get("value_score", 0))
        difficulty = float(eval_data.get("difficulty", 5))

        proposal = EvolutionProposal(
            id=str(uuid.uuid4()),
            repo_url=repo.url,
            repo_name=repo.name,
            stars=repo.stars,
            growth_rate=repo.stars_today,
            description=eval_data.get("summary", repo.description),
            target_module=eval_data.get("target_module", "evolution"),
            value_score=value_score,
            difficulty=difficulty,
            risk_level=eval_data.get("risk_level", "MEDIUM"),
            integration_approach=eval_data.get("integration_approach", ""),
            evaluated_by=bot_id,
            llm_reasoning=eval_data.get("reasoning", ""),
            repo_language=repo.language,
            repo_topics=repo.topics,
            matched_gap=eval_data.get("matched_gap", ""),
        )

        logger.info(
            "[evolution] Evaluated %s: value=%.1f, difficulty=%.1f, risk=%s, module=%s",
            repo.name, value_score, difficulty, proposal.risk_level, proposal.target_module,
        )

        return proposal

    def _heuristic_evaluate(self, repo: TrendingRepo, readme: str = "") -> EvolutionProposal | None:
        """无 LLM 的启发式评估 — 基于关键词匹配 + Star 数量 + 能力差距匹配。

        不需要 AI，纯规则评分，确保进化引擎在 LLM 不可用时也能工作。
        """
        desc = (repo.description or "").lower()
        readme_lower = (readme or "")[:2000].lower()
        text = f"{desc} {readme_lower} {' '.join(repo.topics or [])}"

        # 匹配能力差距
        best_gap = ""
        best_gap_score = 0
        matched_module = "evolution"

        for gap in self._capability_gaps:
            keywords = gap.get("keywords", "").lower().split(",")
            hits = sum(1 for kw in keywords if kw.strip() and kw.strip() in text)
            if hits > best_gap_score:
                best_gap_score = hits
                best_gap = gap.get("gap", "")
                matched_module = gap.get("module", "evolution")

        # 评分公式: star 权重 + 增长率 + 关键词匹配
        star_score = min(4.0, repo.stars / 5000)           # 0-4 分
        growth_score = min(3.0, repo.stars_today / 200)     # 0-3 分
        gap_score = min(3.0, best_gap_score * 1.0)          # 0-3 分
        value_score = round(star_score + growth_score + gap_score, 1)

        if value_score < 3.0:
            return None

        # 难度估算
        difficulty = 5.0
        if repo.stars > 10000:
            difficulty = 3.0  # 成熟项目通常更容易集成
        if "api" in text or "sdk" in text or "client" in text:
            difficulty -= 1.0
        difficulty = max(1.0, min(10.0, difficulty))

        return EvolutionProposal(
            id=str(uuid.uuid4()),
            repo_url=repo.url,
            repo_name=repo.name,
            stars=repo.stars,
            growth_rate=repo.stars_today,
            description=repo.description or "",
            target_module=matched_module,
            value_score=value_score,
            difficulty=difficulty,
            risk_level="LOW" if repo.stars > 5000 else "MEDIUM",
            integration_approach=f"搜索关键词匹配: {best_gap}" if best_gap else "待人工评估",
            evaluated_by="heuristic",
            repo_language=repo.language,
            repo_topics=repo.topics,
            matched_gap=best_gap,
        )

    @staticmethod
    def _parse_llm_json(text: str) -> dict[str, Any] | None:
        """从 LLM 响应中提取 JSON，处理各种格式。"""
        if not text:
            return None

        # 尝试直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.debug("JSON解析失败: %s", e)

        # 尝试从 markdown 代码块中提取
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError as e:
                logger.debug("JSON解析失败: %s", e)

        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError as e:
                logger.debug("JSON解析失败: %s", e)

        return None

    # ──────────────── Capability Gaps ────────────────

    def get_capability_gaps(self) -> list[dict[str, str]]:
        """返回已知能力缺口列表。扫描时用于匹配趋势项目。"""
        return list(self._capability_gaps)

    def add_capability_gap(self, module: str, gap: str, description: str, keywords: str = "") -> None:
        """添加新的能力缺口。"""
        self._capability_gaps.append({
            "module": module,
            "gap": gap,
            "description": description,
            "keywords": keywords,
        })

    # ──────────────── Proposals CRUD ────────────────

    def _save_proposal(self, proposal: EvolutionProposal) -> Path:
        """保存提案到 JSON 文件。"""
        PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = now_et().strftime("%Y%m%d")
        filepath = PROPOSALS_DIR / f"{date_str}_{proposal.id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(proposal.to_json())
        return filepath

    def list_proposals(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionProposal]:
        """列出最近的提案，可按状态过滤。"""
        proposals: list[EvolutionProposal] = []
        if not PROPOSALS_DIR.exists():
            return proposals

        # 按文件名倒序 (最新的在前)
        files = sorted(PROPOSALS_DIR.glob("*.json"), reverse=True)
        for f in files[:limit * 2]:  # 多读一些，因为可能有过滤
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                p = EvolutionProposal.from_dict(data)
                if status and p.status != status:
                    continue
                proposals.append(p)
                if len(proposals) >= limit:
                    break
            except Exception as e:
                logger.debug("[evolution] Failed to read proposal %s: %s", f.name, e)
                continue

        return proposals

    def update_proposal_status(self, proposal_id: str, new_status: str) -> bool:
        """更新提案状态。"""
        if not PROPOSALS_DIR.exists():
            return False

        for f in PROPOSALS_DIR.glob(f"*_{proposal_id}.json"):
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                data["status"] = new_status
                with open(f, "w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                logger.error("[evolution] Failed to update proposal %s: %s", proposal_id, e)
                return False

        return False

    # ──────────────── History ────────────────

    def _append_history(self, scan_result: ScanResult) -> None:
        """追加扫描记录到 history.jsonl"""
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(scan_result.to_dict(), ensure_ascii=False) + "\n")

    def get_scan_history(self, limit: int = 20) -> list[dict]:
        """获取最近的扫描历史。"""
        if not HISTORY_FILE.exists():
            return []

        lines: list[str] = []
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:  # noqa: F841
            return []

        results = []
        for line in reversed(lines[-limit:]):
            try:
                results.append(json.loads(line.strip()))
            except json.JSONDecodeError as e:  # noqa: F841
                continue

        return results

    # ──────────────── Notifications ────────────────

    async def _notify_proposal(self, proposal: EvolutionProposal) -> None:
        """通过 WebSocket + EventBus 推送提案通知。"""
        proposal_data = {
            "id": proposal.id,
            "repo_name": proposal.repo_name,
            "repo_url": proposal.repo_url,
            "stars": proposal.stars,
            "value_score": proposal.value_score,
            "difficulty": proposal.difficulty,
            "risk_level": proposal.risk_level,
            "target_module": proposal.target_module,
            "description": proposal.description,
            "integration_approach": proposal.integration_approach,
            "status": proposal.status,
        }

        # WebSocket 推送（现有）
        try:
            from src.api.routers.ws import push_event
            from src.api.schemas import WSMessageType
            push_event(WSMessageType.EVOLUTION_PROPOSAL, proposal_data)
        except ImportError:
            logger.debug("[evolution] WebSocket push not available (import failed)")
        except Exception as e:
            logger.debug("[evolution] WebSocket push failed: %s", e)

        # EventBus 推送（新增 — 触发协同管道广播）
        try:
            from src.core.event_bus import EventType, get_event_bus
            bus = get_event_bus()
            await bus.publish(
                EventType.EVOLUTION_PROPOSAL,
                proposal_data,
                source="evolution_engine",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # ──────────────── Stats ────────────────

    def get_stats(self) -> dict:
        """返回进化引擎统计摘要。"""
        proposals = self.list_proposals(limit=1000)
        history = self.get_scan_history(limit=100)

        by_status = {}
        by_module = {}
        for p in proposals:
            by_status[p.status] = by_status.get(p.status, 0) + 1
            by_module[p.target_module] = by_module.get(p.target_module, 0) + 1

        return {
            "total_proposals": len(proposals),
            "total_scans": len(history),
            "by_status": by_status,
            "by_module": by_module,
            "capability_gaps": len(self._capability_gaps),
            "last_scan_time": self._config.get("last_scan_time", ""),
            "config": {
                "min_stars": self.min_stars,
                "languages": self.languages,
                "scan_since": self._config.get("scan_since", "weekly"),
            },
        }

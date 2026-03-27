"""
AI 网文写作引擎 v1.0
搬运 inkos (2.4K星) + MuMuAINovel (1.9K星) 的 Prompt 方法论
利用 litellm_router 的免费多模型路由生成内容

工作流: 选题构思 → 世界观/角色设定 → 大纲生成 → 逐章续写 → 导出

用法:
    from src.novel_writer import NovelWriter
    writer = NovelWriter()
    novel_id = await writer.create_novel("都市修仙", style="轻松搞笑")
    chapter = await writer.write_next_chapter(novel_id)
    txt = writer.export_txt(novel_id)
"""
import asyncio
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 数据目录
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DATA_DIR / "novels.db"
_EXPORT_DIR = _DATA_DIR / "novel_exports"
_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# 写作提示词模板 (搬运 inkos + MuMuAINovel 的 Prompt 方法论)
SYSTEM_OUTLINE = """你是一位经验丰富的网文作家，擅长构思引人入胜的故事大纲。

要求：
1. 根据用户给出的题材和风格，生成一个完整的小说大纲
2. 包含：书名、一句话简介、主要角色(3-5个,含性格特点)、世界观设定、主线剧情(分3幕)、每幕包含5-8个章节标题
3. 风格要求：节奏紧凑、冲突明确、有爽点、有伏笔
4. 用 JSON 格式返回，结构如下：
{
  "title": "书名",
  "tagline": "一句话简介",
  "genre": "题材",
  "style": "风格",
  "characters": [{"name": "名字", "role": "主角/配角/反派", "personality": "性格", "backstory": "背景"}],
  "worldbuilding": "世界观设定(100字内)",
  "acts": [
    {"act": 1, "title": "第一幕标题", "summary": "本幕概要", "chapters": ["第1章 标题", "第2章 标题", ...]}
  ]
}"""

SYSTEM_WRITER = """你是一位顶级网文作家，正在创作一部{genre}小说《{title}》。

风格要求：{style}
世界观：{worldbuilding}

主要角色：
{characters}

当前进度：第{chapter_num}章 {chapter_title}
本章概要：{chapter_summary}

前文摘要（最近3000字）：
{previous_summary}

请根据以上设定，续写本章正文。要求：
1. 字数：2000-3000字
2. 保持角色性格一致
3. 有对话、有动作、有心理描写
4. 章末留下悬念，吸引读者继续阅读
5. 不要出现「作者注」「未完待续」等元叙述
6. 直接输出正文，不要加章节标题"""


class NovelWriter:
    """AI 网文写作引擎"""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """SQLite 连接管理"""
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception as e:  # noqa: F841
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """初始化数据库表"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS novels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    tagline TEXT DEFAULT '',
                    genre TEXT DEFAULT '',
                    style TEXT DEFAULT '',
                    outline_json TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'draft',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime')),
                    user_id INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    novel_id INTEGER NOT NULL,
                    chapter_num INTEGER NOT NULL,
                    title TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    word_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (novel_id) REFERENCES novels(id)
                )
            """)
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chapter_unique ON chapters(novel_id, chapter_num)")
            except Exception as e:
                pass
                logger.debug("静默异常: %s", e)

    async def _llm_call(self, system: str, user: str, max_tokens: int = 4000) -> str:
        """调用 LLM（利用已有的 litellm_router 免费多模型路由）"""
        try:
            from src.litellm_router import free_pool
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            resp = await asyncio.wait_for(
                free_pool.acompletion(
                    model="default", messages=messages,
                    max_tokens=max_tokens, temperature=0.8,
                ),
                timeout=120
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error("[NovelWriter] LLM 调用失败: %s", e)
            return ""

    async def create_novel(self, genre: str, style: str = "轻松有趣", user_id: int = 0) -> Dict:
        """创建新小说 — 生成大纲和世界观"""
        # 1. 用 LLM 生成大纲
        user_prompt = f"请为以下题材生成一部网文小说的完整大纲：\n题材：{genre}\n风格：{style}"
        raw = await self._llm_call(SYSTEM_OUTLINE, user_prompt, max_tokens=3000)
        
        # 2. 解析 JSON
        outline = {}
        try:
            # 尝试提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                outline = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning("[NovelWriter] 大纲 JSON 解析失败，使用原始文本")
            outline = {"title": f"{genre}小说", "raw_outline": raw}

        title = outline.get("title", f"{genre}小说")
        tagline = outline.get("tagline", "")
        
        # 3. 保存到数据库
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO novels (title, tagline, genre, style, outline_json, user_id) VALUES (?,?,?,?,?,?)",
                (title, tagline, genre, style, json.dumps(outline, ensure_ascii=False), user_id)
            )
            novel_id = cursor.lastrowid
        
        logger.info("[NovelWriter] 新小说创建: #%d《%s》(%s)", novel_id, title, genre)
        return {"novel_id": novel_id, "title": title, "tagline": tagline, "outline": outline}

    async def write_next_chapter(self, novel_id: int) -> Dict:
        """续写下一章"""
        with self._conn() as conn:
            novel = conn.execute("SELECT * FROM novels WHERE id=?", (novel_id,)).fetchone()
            if not novel:
                return {"error": f"小说 #{novel_id} 不存在"}
            
            # 获取已写章节
            chapters = conn.execute(
                "SELECT * FROM chapters WHERE novel_id=? ORDER BY chapter_num", (novel_id,)
            ).fetchall()
        
        outline = json.loads(novel["outline_json"] or "{}")
        chapter_num = len(chapters) + 1
        
        # 从大纲中获取本章信息
        all_chapter_titles = []
        for act in outline.get("acts", []):
            all_chapter_titles.extend(act.get("chapters", []))
        
        chapter_title = all_chapter_titles[chapter_num - 1] if chapter_num <= len(all_chapter_titles) else f"第{chapter_num}章"
        # 清理标题格式
        if chapter_title.startswith("第") and "章" in chapter_title:
            chapter_title = chapter_title.split("章", 1)[-1].strip() if "章" in chapter_title else chapter_title
        
        # 构建前文摘要（最近3章）
        recent = chapters[-3:] if chapters else []
        previous_summary = "\n\n".join([
            f"【第{ch['chapter_num']}章】{ch['content'][-500:]}" for ch in recent
        ]) or "（这是第一章，无前文）"
        
        # 构建角色信息
        characters_text = "\n".join([
            f"- {c['name']}({c['role']}): {c['personality']}"
            for c in outline.get("characters", [])
        ]) or "（角色待定）"
        
        # 调用 LLM 续写
        system = SYSTEM_WRITER.format(
            genre=novel["genre"],
            title=novel["title"],
            style=novel["style"],
            worldbuilding=outline.get("worldbuilding", "现代都市"),
            characters=characters_text,
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            chapter_summary=f"第{chapter_num}章的内容",
            previous_summary=previous_summary,
        )
        
        content = await self._llm_call(system, f"请续写第{chapter_num}章", max_tokens=4000)
        
        if not content:
            return {"error": "LLM 续写失败"}
        
        word_count = len(content)  # 字符数（中文1字=1字符）
        
        # 保存章节
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chapters (novel_id, chapter_num, title, content, word_count) VALUES (?,?,?,?,?)",
                (novel_id, chapter_num, chapter_title, content, word_count)
            )
            conn.execute(
                "UPDATE novels SET updated_at=datetime('now','localtime') WHERE id=?", (novel_id,)
            )
        
        logger.info("[NovelWriter] 续写完成: 《%s》第%d章 (%d字)", novel["title"], chapter_num, word_count)
        return {
            "novel_id": novel_id,
            "chapter_num": chapter_num,
            "title": chapter_title,
            "content": content,
            "word_count": word_count,
        }

    def get_novel_status(self, novel_id: int) -> Dict:
        """获取小说状态"""
        with self._conn() as conn:
            novel = conn.execute("SELECT * FROM novels WHERE id=?", (novel_id,)).fetchone()
            if not novel:
                return {"error": f"小说 #{novel_id} 不存在"}
            chapters = conn.execute(
                "SELECT chapter_num, title, word_count FROM chapters WHERE novel_id=? ORDER BY chapter_num",
                (novel_id,)
            ).fetchall()
        
        total_words = sum(ch["word_count"] for ch in chapters)
        return {
            "novel_id": novel_id,
            "title": novel["title"],
            "tagline": novel["tagline"],
            "genre": novel["genre"],
            "style": novel["style"],
            "chapters": len(chapters),
            "total_words": total_words,
            "chapter_list": [{"num": ch["chapter_num"], "title": ch["title"], "words": ch["word_count"]} for ch in chapters],
        }

    def list_novels(self, user_id: int = 0) -> List[Dict]:
        """列出所有小说"""
        with self._conn() as conn:
            novels = conn.execute(
                "SELECT id, title, genre, style, status, created_at FROM novels WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,)
            ).fetchall()
            result = []
            for n in novels:
                ch_count = conn.execute("SELECT COUNT(*) FROM chapters WHERE novel_id=?", (n["id"],)).fetchone()[0]
                word_count = conn.execute("SELECT COALESCE(SUM(word_count),0) FROM chapters WHERE novel_id=?", (n["id"],)).fetchone()[0]
                result.append({
                    "id": n["id"], "title": n["title"], "genre": n["genre"],
                    "chapters": ch_count, "words": word_count, "created_at": n["created_at"],
                })
        return result

    def export_txt(self, novel_id: int) -> Optional[str]:
        """导出小说为 TXT 文件"""
        with self._conn() as conn:
            novel = conn.execute("SELECT * FROM novels WHERE id=?", (novel_id,)).fetchone()
            if not novel:
                return None
            chapters = conn.execute(
                "SELECT * FROM chapters WHERE novel_id=? ORDER BY chapter_num", (novel_id,)
            ).fetchall()
        
        if not chapters:
            return None
        
        lines = [f"《{novel['title']}》\n"]
        if novel["tagline"]:
            lines.append(f"{novel['tagline']}\n")
        lines.append(f"题材: {novel['genre']}  风格: {novel['style']}\n")
        lines.append("=" * 40 + "\n\n")
        
        for ch in chapters:
            lines.append(f"\n第{ch['chapter_num']}章 {ch['title']}\n\n")
            lines.append(ch["content"] + "\n")
        
        # 写入文件
        safe_title = "".join(c for c in novel["title"] if c.isalnum() or c in "_ -")[:50]
        export_path = _EXPORT_DIR / f"{safe_title}_{novel_id}.txt"
        export_path.write_text("\n".join(lines), encoding="utf-8")
        
        logger.info("[NovelWriter] 导出: %s (%d章, %d字)",
                     export_path, len(chapters), sum(ch["word_count"] for ch in chapters))
        return str(export_path)


# 全局单例
_writer: Optional[NovelWriter] = None

def get_novel_writer() -> NovelWriter:
    """获取全局 NovelWriter 实例"""
    global _writer
    if _writer is None:
        _writer = NovelWriter()
    return _writer

"""
Execution Hub — 本地文档检索
场景3: 建立文档索引并支持关键词搜索
"""
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    ".go", ".js", ".md", ".py", ".sh", ".ts", ".csv", ".ini", ".jsx",
    ".log", ".rst", ".sql", ".tsx", ".txt", ".yml", ".conf", ".java",
    ".toml", ".yaml", ".json",
}


def build_doc_index(roots=None, max_files=500) -> dict:
    """扫描目录建立文档索引"""
    roots = roots or ["."]
    indexed = 0
    skipped = 0
    files = []

    for root_path in roots:
        root = Path(root_path).expanduser().resolve()
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in ALLOWED_EXTENSIONS:
                skipped += 1
                continue
            if indexed >= max_files:
                break
            try:
                size = f.stat().st_size
                if size > 1_000_000:  # 跳过 >1MB 的文件
                    skipped += 1
                    continue
                files.append({
                    "path": str(f),
                    "name": f.name,
                    "ext": f.suffix,
                    "size": size,
                })
                indexed += 1
            except Exception as e:  # noqa: F841
                skipped += 1

    return {
        "success": True,
        "indexed": indexed,
        "skipped": skipped,
        "files": files,
    }


def search_docs(query=None, files=None, limit=10) -> List[dict]:
    """在已索引的文档中搜索关键词"""
    keyword = str(query or "").strip().lower()
    if not keyword:
        return []

    results = []
    for f in (files or []):
        path = f.get("path", "")
        name = f.get("name", "").lower()
        # 文件名匹配
        if keyword in name:
            results.append({"path": path, "name": f.get("name"), "match": "filename"})
            if len(results) >= limit:
                break
            continue
        # 内容匹配（仅小文件）
        try:
            size = f.get("size", 0)
            if size > 500_000:
                continue
            content = Path(path).read_text(encoding="utf-8", errors="ignore").lower()
            if keyword in content:
                # 找到匹配行
                for i, line in enumerate(content.splitlines(), 1):
                    if keyword in line:
                        results.append({
                            "path": path,
                            "name": f.get("name"),
                            "match": "content",
                            "line": i,
                            "snippet": line.strip()[:200],
                        })
                        break
                if len(results) >= limit:
                    break
        except Exception as e:  # noqa: F841
            continue

    return results

"""
ClawBot - 长期记忆工具
"""
import json
from typing import Dict, Any, Optional
from pathlib import Path
import logging
from src.utils import now_et

logger = logging.getLogger(__name__)


class MemoryTool:
    """长期记忆"""
    
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # 从 config 导入避免循环依赖
            from src.bot.config import DATA_DIR
            self.storage_path = Path(DATA_DIR) / "memory.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.memories: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.memories = json.load(f)
            except (json.JSONDecodeError, OSError) as e:  # noqa: F841
                self.memories = {}
    
    def _save(self):
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=2)
    
    def remember(self, key: str, value: Any, category: str = "general") -> Dict[str, Any]:
        if category not in self.memories:
            self.memories[category] = {}
        self.memories[category][key] = {"value": value, "time": now_et().isoformat()}
        self._save()
        return {"success": True, "key": key, "category": category}
    
    def recall(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
        if category:
            if category in self.memories and key in self.memories[category]:
                return {"success": True, "key": key, "value": self.memories[category][key]["value"]}
        else:
            for cat, items in self.memories.items():
                if key in items:
                    return {"success": True, "key": key, "value": items[key]["value"], "category": cat}
        return {"success": False, "error": f"未找到: {key}"}
    
    def forget(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
        if category and category in self.memories and key in self.memories[category]:
            del self.memories[category][key]
            self._save()
            return {"success": True}
        for cat in self.memories:
            if key in self.memories[cat]:
                del self.memories[cat][key]
                self._save()
                return {"success": True}
        return {"success": False, "error": f"未找到: {key}"}
    
    def list_memories(self, category: Optional[str] = None) -> Dict[str, Any]:
        if category:
            items = self.memories.get(category, {})
            return {"success": True, "category": category, "items": list(items.keys()), "count": len(items)}
        else:
            result = {}
            total = 0
            for cat, items in self.memories.items():
                result[cat] = list(items.keys())
                total += len(items)
            return {"success": True, "categories": result, "total": total}
    
    def search(self, query: str) -> Dict[str, Any]:
        results = []
        query_lower = query.lower()
        for cat, items in self.memories.items():
            for key, data in items.items():
                if query_lower in key.lower() or query_lower in str(data["value"]).lower():
                    results.append({"key": key, "value": data["value"], "category": cat})
        return {"success": True, "query": query, "results": results[:20], "count": len(results)}
    
    def get_context_summary(self) -> str:
        parts = []
        for cat, items in self.memories.items():
            if items:
                parts.append(f"\n[{cat}]")
                for key, data in list(items.items())[:5]:
                    parts.append(f"- {key}: {str(data['value'])[:50]}")
        if parts:
            return "\n长期记忆:" + "".join(parts)
        return ""

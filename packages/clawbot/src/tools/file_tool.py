"""
ClawBot - 文件操作工具
"""
import logging
import re
from pathlib import Path
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

class FileTool:
    """文件读写操作"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.home().resolve()

    def _safe_resolve(self, path: str) -> Path:
        """
        安全解析路径，防止路径穿越攻击。
        所有路径必须在 base_dir 内，禁止 .., ~, 绝对路径逃逸。
        """
        # 禁止空路径
        if not path or not path.strip():
            raise ValueError("路径不能为空")

        raw = Path(path)

        # 如果是绝对路径，直接 resolve 后检查
        if raw.is_absolute():
            resolved = raw.resolve()
        else:
            # 相对路径：相对于 base_dir
            resolved = (self.base_dir / raw).resolve()

        # 核心安全检查：resolved 必须在 base_dir 下
        try:
            resolved.relative_to(self.base_dir)
        except ValueError as e:  # noqa: F841
            raise PermissionError(
                f"路径越权: {path} 解析为 {resolved}，不在允许范围 {self.base_dir} 内"
            )

        return resolved

    def read(self, path: str, offset: int = 0, limit: int = 2000) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            file_path = self._safe_resolve(path)

            if not file_path.exists():
                return {"success": False, "error": f"文件不存在: {path}"}

            if not file_path.is_file():
                return {"success": False, "error": f"不是文件: {path}"}

            size = file_path.stat().st_size
            if size > 10 * 1024 * 1024:
                return {"success": False, "error": f"文件过大: {size / 1024 / 1024:.1f}MB"}

            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            total_lines = len(lines)
            selected = lines[offset:offset + limit]

            numbered = []
            for i, line in enumerate(selected, start=offset + 1):
                if len(line) > 2000:
                    line = line[:2000] + "...\n"
                numbered.append(f"{i:5d}| {line.rstrip()}")

            return {
                "success": True,
                "content": "\n".join(numbered),
                "total_lines": total_lines,
                "shown_lines": len(selected),
                "path": str(file_path)
            }
        except UnicodeDecodeError as e:  # noqa: F841
            return {"success": False, "error": "无法读取二进制文件"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write(self, path: str, content: str) -> Dict[str, Any]:
        """写入文件"""
        try:
            file_path = self._safe_resolve(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return {"success": True, "path": str(file_path), "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> Dict[str, Any]:
        """编辑文件 (替换字符串)"""
        try:
            file_path = self._safe_resolve(path)

            if not file_path.exists():
                return {"success": False, "error": f"文件不存在: {path}"}

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            count = content.count(old_string)

            if count == 0:
                return {"success": False, "error": "未找到要替换的字符串"}

            if count > 1 and not replace_all:
                return {"success": False, "error": f"找到 {count} 处匹配，请使用 replace_all=True"}

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return {"success": True, "path": str(file_path), "replacements": count if replace_all else 1}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_dir(self, path: str, pattern: str = "*") -> Dict[str, Any]:
        """列出目录内容"""
        try:
            dir_path = self._safe_resolve(path)

            if not dir_path.exists():
                return {"success": False, "error": f"目录不存在: {path}"}

            if not dir_path.is_dir():
                return {"success": False, "error": f"不是目录: {path}"}

            files = []
            dirs = []

            for item in sorted(dir_path.glob(pattern)):
                if item.is_file():
                    files.append({"name": item.name, "size": item.stat().st_size, "path": str(item)})
                elif item.is_dir():
                    dirs.append({"name": item.name, "path": str(item)})

            return {
                "success": True,
                "path": str(dir_path),
                "files": files[:100],
                "dirs": dirs[:100],
                "total_files": len(files),
                "total_dirs": len(dirs)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(self, path: str, pattern: str, content_pattern: Optional[str] = None) -> Dict[str, Any]:
        """搜索文件"""
        try:
            dir_path = self._safe_resolve(path)
            matches = []

            for file_path in dir_path.rglob(pattern):
                if not file_path.is_file():
                    continue

                if len(matches) >= 100:
                    break

                match_info: Dict[str, Any] = {"path": str(file_path), "name": file_path.name}

                if content_pattern:
                    try:
                        # 防止正则表达式拒绝服务攻击 (ReDoS)
                        if len(content_pattern) > 200:
                            return {"success": False, "error": "正则表达式过长(最大200字符)"}
                        try:
                            regex = re.compile(content_pattern, re.IGNORECASE)
                        except re.error as regex_err:
                            return {"success": False, "error": f"正则表达式无效: {regex_err}"}

                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        found = regex.findall(content)

                        if found:
                            match_info["content_matches"] = len(found)
                            matches.append(match_info)
                    except (UnicodeDecodeError, OSError) as e:
                        logger.debug("文件操作失败: %s", e)
                else:
                    matches.append(match_info)

            return {"success": True, "matches": matches, "count": len(matches)}
        except Exception as e:
            return {"success": False, "error": str(e)}

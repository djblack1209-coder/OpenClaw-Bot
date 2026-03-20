#!/usr/bin/env python3
"""
数据迁移脚本：旧 SQLite SharedMemory → Mem0

用法：
    python migrate_memory_to_mem0.py [--db-path /path/to/shared_memory.db] [--dry-run]

功能：
    1. 读取旧 SQLite 中所有 shared_memories 记录
    2. 逐条写入 Mem0（带 metadata 保留分类/来源/重要性）
    3. 将 mem0_id 回写到 SQLite 的 mem0_id 列
    4. 跳过已有 mem0_id 的记录（支持断点续传）
"""
import argparse
import sqlite3
import sys
import os
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def migrate(db_path: str, dry_run: bool = False):
    # 检查 mem0
    try:
        from mem0 import Memory as Mem0Memory
    except ImportError:
        print("错误: mem0ai 未安装。请先运行: pip install mem0ai")
        sys.exit(1)

    # 初始化 Mem0
    from shared_memory import _build_mem0_config
    config = _build_mem0_config()
    print(f"Mem0 配置: {config.get('vector_store', {}).get('provider', 'unknown')}")

    if not dry_run:
        mem0 = Mem0Memory.from_config(config)
        print("Mem0 初始化成功")

    # 连接 SQLite
    if not Path(db_path).exists():
        print(f"错误: 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 确保 mem0_id 列存在
    try:
        conn.execute("SELECT mem0_id FROM shared_memories LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE shared_memories ADD COLUMN mem0_id TEXT")
        conn.commit()
        print("已添加 mem0_id 列")

    # 读取待迁移记录
    rows = conn.execute(
        "SELECT id, key, value, category, source_bot, importance, chat_id "
        "FROM shared_memories WHERE mem0_id IS NULL "
        "ORDER BY importance DESC, updated_at DESC"
    ).fetchall()

    total = len(rows)
    print(f"\n待迁移: {total} 条记忆")

    if total == 0:
        print("无需迁移，所有记录已同步。")
        return

    if dry_run:
        print("\n[DRY RUN] 以下记录将被迁移:")
        for r in rows[:20]:
            print(f"  [{r['category']}] {r['key']}: {r['value'][:60]}...")
        if total > 20:
            print(f"  ... 还有 {total - 20} 条")
        return

    # 执行迁移
    migrated = 0
    failed = 0
    start = time.time()

    for i, r in enumerate(rows):
        try:
            content = f"[{r['category']}] {r['key']}: {r['value']}"
            metadata = {
                "category": r["category"],
                "source_bot": r["source_bot"],
                "importance": r["importance"],
                "key": r["key"],
            }
            if r["chat_id"] is not None:
                metadata["chat_id"] = str(r["chat_id"])

            result = mem0.add(
                [{"role": "user", "content": content}],
                user_id=r["source_bot"],
                metadata=metadata,
                infer=False,
            )

            # 提取 mem0_id
            mem0_id = None
            if isinstance(result, dict):
                results_list = result.get("results", [])
                if results_list and isinstance(results_list[0], dict):
                    mem0_id = results_list[0].get("id")
            elif isinstance(result, list) and result:
                mem0_id = result[0].get("id") if isinstance(result[0], dict) else None

            if mem0_id:
                conn.execute(
                    "UPDATE shared_memories SET mem0_id = ? WHERE id = ?",
                    (str(mem0_id), r["id"]),
                )
                conn.commit()
                migrated += 1
            else:
                failed += 1
                print(f"  警告: 无法获取 mem0_id for key={r['key']}")

        except Exception as e:
            failed += 1
            print(f"  错误: key={r['key']}: {e}")

        # 进度
        if (i + 1) % 10 == 0 or i == total - 1:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  进度: {i + 1}/{total} ({rate:.1f}/s) 成功={migrated} 失败={failed}")

    elapsed = time.time() - start
    print(f"\n迁移完成: {migrated} 成功, {failed} 失败, 耗时 {elapsed:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移 SharedMemory SQLite → Mem0")
    default_db = str(Path(__file__).parent.parent / "data" / "shared_memory.db")
    parser.add_argument("--db-path", default=default_db, help="SQLite 数据库路径")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不执行")
    args = parser.parse_args()
    migrate(args.db_path, args.dry_run)

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs"
INDEX_FILE="$DOCS_DIR/003-docs-index.md"
FAILED=0

report_failure() {
  printf '❌ %s\n' "$1" >&2
  FAILED=1
}

if [[ ! -d "$DOCS_DIR" ]]; then
  report_failure "缺少 docs/ 文档目录"
fi

if [[ ! -f "$INDEX_FILE" ]]; then
  report_failure "缺少 docs/003-docs-index.md"
fi

ROOT_DOCS="$(find "$ROOT_DIR" -maxdepth 1 -type f \( -name '*.md' -o -name '*.txt' \) ! -name 'AGENTS.md' ! -name 'README.md' -print | sort)"
if [[ -n "$ROOT_DOCS" ]]; then
  report_failure "项目根目录存在未归档文档：\n$ROOT_DOCS"
fi

DOC_SUBDIRS="$(find "$DOCS_DIR" -mindepth 1 -type d -print | sort)"
if [[ -n "$DOC_SUBDIRS" ]]; then
  report_failure "docs/ 内禁止子目录：\n$DOC_SUBDIRS"
fi

BAD_NAMES=""
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  base="$(basename "$file")"
  if [[ ! "$base" =~ ^[0-9]{3}-[a-z0-9][a-z0-9-]*\.md$ ]]; then
    BAD_NAMES="${BAD_NAMES}${BAD_NAMES:+$'\n'}$file"
  fi
done < <(find "$DOCS_DIR" -maxdepth 1 -type f -print | sort)
if [[ -n "$BAD_NAMES" ]]; then
  report_failure "docs/ 文件名必须是 XXX-kebab-case.md：\n$BAD_NAMES"
fi

MISSING_INDEX=""
if [[ -f "$INDEX_FILE" ]]; then
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    base="$(basename "$file")"
    if ! grep -Fq "\`$base\`" "$INDEX_FILE"; then
      MISSING_INDEX="${MISSING_INDEX}${MISSING_INDEX:+$'\n'}$base"
    fi
  done < <(find "$DOCS_DIR" -maxdepth 1 -type f -name '*.md' -print | sort)
fi
if [[ -n "$MISSING_INDEX" ]]; then
  report_failure "下列文档未登记到 docs/003-docs-index.md：\n$MISSING_INDEX"
fi

STALE_INDEX=""
if [[ -f "$INDEX_FILE" ]]; then
  while IFS= read -r base; do
    [[ -z "$base" ]] && continue
    if [[ ! -f "$DOCS_DIR/$base" ]]; then
      STALE_INDEX="${STALE_INDEX}${STALE_INDEX:+$'\n'}$base"
    fi
  done < <(grep -oE '\`[0-9]{3}-[a-z0-9][a-z0-9-]*\.md\`' "$INDEX_FILE" | tr -d '\`' | sort -u)
fi
if [[ -n "$STALE_INDEX" ]]; then
  report_failure "docs/003-docs-index.md 引用了不存在的文档：\n$STALE_INDEX"
fi

if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi

DOC_COUNT="$(find "$DOCS_DIR" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
printf '✅ docs-check 通过：%s 个文档，目录扁平、命名合规、索引完整。\n' "$DOC_COUNT"

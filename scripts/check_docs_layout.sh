#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs"
INDEX_FILE="$DOCS_DIR/003-docs-index.md"
FAILED=0
AUTHORITATIVE_DOCS=(
  "$DOCS_DIR/001-project-map.md"
  "$DOCS_DIR/007-operations.md"
  "$DOCS_DIR/current/current-baseline.md"
)
PROJECT_MAP="$DOCS_DIR/001-project-map.md"
CURRENT_DIR="$DOCS_DIR/current"
CURRENT_BASELINE="$CURRENT_DIR/current-baseline.md"

# 文档门禁必须能在最小 CI 镜像运行，优先使用 rg，缺失时回退到 POSIX 常见的 grep。
search_fixed() {
  local pattern="$1"
  shift
  if command -v rg >/dev/null 2>&1; then
    rg -Fq -- "$pattern" "$@"
  else
    grep -Fq -- "$pattern" "$@"
  fi
}

search_regex_stdin() {
  local pattern="$1"
  if command -v rg >/dev/null 2>&1; then
    rg -q -- "$pattern"
  else
    grep -Eq -- "$pattern"
  fi
}

extract_repository_refs() {
  local pattern="\`(packages|apps|scripts|docs|\\.github)/[^\`[:space:]]+\`"
  if command -v rg >/dev/null 2>&1; then
    rg -o --no-filename "$pattern" "${AUTHORITATIVE_DOCS[@]}"
  else
    grep -Eho -- "$pattern" "${AUTHORITATIVE_DOCS[@]}"
  fi
}

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

DOC_SUBDIRS="$(find "$DOCS_DIR" -mindepth 1 -type d ! -path "$CURRENT_DIR" -print | sort)"
if [[ -n "$DOC_SUBDIRS" ]]; then
  report_failure "docs/ 只允许 current/ 当前基线目录：\n$DOC_SUBDIRS"
fi

if [[ ! -f "$CURRENT_BASELINE" ]]; then
  report_failure "缺少唯一当前基线：$CURRENT_BASELINE"
else
  CURRENT_EXTRA="$(find "$CURRENT_DIR" -mindepth 1 \( -type d -o ! -name 'current-baseline.md' \) -print | sort)"
  if [[ -n "$CURRENT_EXTRA" ]]; then
    report_failure "docs/current/ 只能保留 current-baseline.md：\n$CURRENT_EXTRA"
  fi
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
  done < <(grep -oE "\`[0-9]{3}-[a-z0-9][a-z0-9-]*\.md\`" "$INDEX_FILE" | tr -d "\`" | sort -u)
fi
if [[ -n "$STALE_INDEX" ]]; then
  report_failure "docs/003-docs-index.md 引用了不存在的文档：\n$STALE_INDEX"
fi

MISSING_REFS=""
while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  ref="${ref#\`}"
  ref="${ref%\`}"
  ref="$(printf '%s' "$ref" | sed -E 's/:[0-9]+$//')"
  case "$ref" in
    packages/clawbot/config/.env|packages/clawbot/data/intel_brief.db|packages/clawbot/data/intel_evidence/*)
      # 私有配置与运行证据由本机生成且受 Git 忽略，干净检出不要求存在。
      continue
      ;;
    *'*'*|*'{'*|*'}'*|*'<'*|*'>'*|*'|'*|*','*|*'('*|*')'*|*'…'*|*/|*/runtime.json)
      continue
      ;;
  esac
  if [[ ! -e "$ROOT_DIR/$ref" ]]; then
    MISSING_REFS="${MISSING_REFS}${MISSING_REFS:+$'\n'}$ref"
  fi
done < <(
  extract_repository_refs | sort -u
)
if [[ -n "$MISSING_REFS" ]]; then
  report_failure "权威文档引用了不存在的仓库路径：\n$MISSING_REFS"
fi

MUTABLE_INSTALL_SPECS=(
  'openclaw@latest'
  '@playwright/mcp@latest'
  'superpowers-mcp@latest'
  'open-computer-use@latest'
)
for spec in "${MUTABLE_INSTALL_SPECS[@]}"; do
  if search_fixed "$spec" "${AUTHORITATIVE_DOCS[@]:0:3}"; then
    report_failure "当前架构/注册表/运维文档仍包含可变安装规格：$spec"
  fi
done

for current_fact in \
  '生产运行时是唯一事实' \
  '## 1. 已通过的真实生产检查' \
  '## 3. 未修复问题及原因' \
  '## 7. 新会话交接提示词'; do
  if ! search_fixed "$current_fact" "$CURRENT_BASELINE"; then
    report_failure "唯一当前基线缺少生产收口事实：$current_fact"
  fi
done

PROJECT_STRUCTURE="$(awk '
  /^## 项目结构$/ { in_section = 1; next }
  in_section && /^---$/ { exit }
  in_section { print }
' "$PROJECT_MAP")"
if printf '%s\n' "$PROJECT_STRUCTURE" | search_regex_stdin '\([0-9][0-9,]*[[:space:]]*(行|文件)'; then
  report_failure "项目结构图包含易漂移的手写行数或文件数；请只记录稳定职责，由命令实时生成规模数据"
fi

if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi

DOC_COUNT="$(find "$DOCS_DIR" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
[[ -f "$CURRENT_BASELINE" ]] && DOC_COUNT=$((DOC_COUNT + 1))
printf '✅ docs-check 通过：%s 个文档，唯一当前基线、命名合规、索引完整。\n' "$DOC_COUNT"

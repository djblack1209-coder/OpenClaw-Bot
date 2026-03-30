# HANDOFF — 会话交接摘要

> 最后更新: 2026-03-31

---

## [2026-03-31 Session 14] HI-382 模型名常量提取完成 — 16常量+26文件85处替换

### 本次完成了什么
- **HI-382 常量定义**: `src/constants.py` 新增 16 个模型名常量 (7 Bot ID + 6 Model Family + 3 Image Model)
- **HI-382 全量替换**: 26 个源文件中 ~85 处硬编码字符串替换为常量引用
- **有意跳过**: `cost_control.py`（自包含定价注册表）和 `litellm_router.py`（规范模型配置中心）不做替换
- **文档同步**: HEALTH.md 更新 (HI-382 从活跃移至已解决), CHANGELOG.md 新增条目
- **回归验证**: 1047/1047 Python passed, 0 TypeScript errors

### 未完成的工作（按优先级排列）
1. **HI-358** — 8 个 >1000 行大文件拆分 (🟡 高成本，需逐文件设计拆分方案)
   - `chinese_nlp_mixin.py` (1,217), `risk_manager.py` (1,191), `daily_brief.py` (1,157), `backtester.py` (1,124), `trading_journal.py` (1,086), `broker_bridge.py` (1,085), `auto_trader.py` (1,056), `proactive_engine.py` (1,011)
2. **HI-348** — API keys 在 Git 历史中，需 `git filter-repo` (🟠 破坏性操作，需用户确认)
3. **HI-381** — 统一 120+ 内联错误字符串到 error_messages.py (🟡 高成本)
4. **HI-383** — HTTP 客户端/缓存碎片化 (🟡 高成本)
5. **HI-384** — 不稳定测试 `test_investment_full_pipeline` (🟡 LiteLLM cooldown 相关)

### 需要注意的坑
- `routing/constants.py` 是替换最密集的文件 (~30 处)，后续修改 Bot ID 映射时留意 import 路径
- `cost_control.py` 中的模型名 (如 `"claude-opus-4"`, `"qwen3-235b"`) 是 LiteLLM 路由层短名，与 Bot ID (`"claude_opus"`, `"qwen235b"`) 完全不同，不要混淆

### 关键决策记录
- 将模型名分三组（Bot ID / Model Family / Image Model）而非混在一起——三种用途不同，避免命名混乱
- 不修改 `cost_control.py` 和 `litellm_router.py`——它们使用的是 LiteLLM 路由层模型名，与 Bot ID 体系完全独立

### 当前系统状态
- 测试: 1047/1047 Python passed, 0 TS errors
- 活跃问题: 6 (1🟠 + 4🟡 + 1🔵)
- **全量审计完成**: P0 ✅ | P1 ✅ | P2 ✅ | P3 ✅ | P4 ✅ | P5 ✅ | P6 ✅

## [2026-03-31 Session 13] P6 安全加固完成 — 沙箱OS隔离+快捷指令白名单+SSRF防护

### 本次完成了什么
- **HI-349 沙箱 OS 级隔离**: code_tool.py 完全重写 — 所有 Python 执行移至独立子进程 + resource.setrlimit(CPU 30s/MEM 256MB/NPROC=0/FSIZE 1MB) + 进程组隔离 + 环境变量白名单; bash_tool.py 同步添加 `_make_safe_env()` 环境过滤
- **HI-388 快捷指令白名单**: life_automation.py 添加 `_SHORTCUT_WHITELIST` frozenset (14 个预定义名称)，未在白名单中的指令被拦截
- **HI-389 DNS 重绑定 SSRF 防护**: omega.py `/tools/jina-read` 重写，`socket.getaddrinfo` 预解析检查所有 IP
- **HI-277/278 活跃问题复核**: VPS 退让机制已确认存在，两个问题移至已解决
- **HI-358 描述更正**: 从 "~15 files" 修正为 "22 files >800 lines (8 >1000 lines)"
- **文档同步**: CHANGELOG.md P6 条目, HEALTH.md 更新 (活跃问题降至 1🟠+5🟡+1🔵)
- **回归验证**: 1047/1047 Python passed, 0 TypeScript errors

### 未完成的工作（按优先级排列）
1. **Git commit + push** — P6 安全加固全部变更需提交
2. **HI-382** — 提取硬编码 LLM 模型名到 constants.py (🟡 中等成本)
3. **HI-358** — 8 个 >1000 行大文件拆分 (🟡 高成本)
4. **HI-348** — API keys 在 Git 历史中，需 `git filter-repo` (🟠 破坏性操作，需用户确认)

### 需要注意的坑
- code_tool.py 重写后，Python 执行通过 subprocess 而非 host 进程内 exec()——性能略有下降但安全性大幅提升
- bash_tool.py 的 `_make_safe_env()` 只传递 PATH/HOME/LANG/PYTHONPATH——如果有需要其他环境变量的命令可能需要更新白名单
- test_bash_tool.py 中的测试已从"验证环境变量传递"改为"验证环境变量过滤"——逻辑反转

### 关键决策记录
- RestrictedPython 降级为 AST 预检（Layer 1），不再用于执行——因为 CPython 内部机制可绕过其所有运行时守卫
- 资源限制用 `resource.setrlimit` 而非 cgroups——因为 macOS 不支持 cgroups，setrlimit 跨平台兼容
- 环境变量白名单而非黑名单——防止遗漏敏感变量

### 当前系统状态
- 测试: 1047/1047 Python passed, 0 TS errors
- 活跃问题: 7 (1🟠 + 5🟡 + 1🔵)
- **全量审计完成**: P0 ✅ | P1 ✅ | P2 ✅ | P3 ✅ | P4 ✅ | P5 ✅ | P6 ✅

## [2026-03-31 Session 12] P5 文档 + 工程基础设施审计完成 — 全量审计收尾

### 本次完成了什么
- **P5 文档完整性审计 (D1-D6)**: 4 个注册表全部修正 + HEALTH.md 清理
  - MODULE_REGISTRY: 行数/描述与代码对齐
  - PROJECT_MAP: 7 处过时数据修正
  - DEPENDENCY_MAP: tiktoken→RestrictedPython, fpdf2 标注
  - COMMAND_REGISTRY: 全表重编号修复编号冲突 (#44-94), 总数更正为 94
  - API_POOL_REGISTRY: 新增 4 条目 (7 个缺失环境变量)
  - HEALTH.md: HI-385 活跃残留移除
- **P5 工程基础设施 (E1-E6)**: 6 个新文件创建
  - `.github/workflows/ci.yml` — monorepo CI (pytest + tsc)
  - `ruff.toml` — Python linter 配置
  - `requirements-dev.txt` — 版本限制修复
  - `Makefile` — 根目录任务入口
  - `.editorconfig` — 跨编辑器格式
  - `.pre-commit-config.yaml` — 提交前检查
- **回归验证**: 1047/1047 Python passed, 0 TypeScript errors

### 当前系统状态
- 测试: 1047/1047 Python passed, 0 TS errors
- P0: ✅ | P1: ✅ | P2: ✅ | P3: ✅ | P4: ✅ | P5: ✅

## [2026-03-31 Session 10/11] P4 UI/UX 审计全部完成 — 4 批次修复

### 本次完成了什么
- **P4 Batch 1 (C-02 + C-04)**: 创建 `confirm-dialog.tsx` 和 `prompt-dialog.tsx` 可复用组件，替换 6 个文件中所有浏览器原生 `confirm()`/`alert()`/`prompt()` 为应用内对话框
- **P4 Batch 2 (C-01 + I-05)**: 12 个组件文件新增 31 个 aria-label 无障碍属性；5 个文件中 6 处残留英文 UI 文本翻译为中文
- **P4 Batch 3 (M-08 + I-02 + I-07)**: App.tsx 挂载 `<Toaster />`（修复 sonner toast 全局静默问题 HI-386）；ControlCenter/Settings toast 迁移；5 个组件表单校验；Channels + Plugins 空状态
- **P4 Batch 4 (M-03 + M-06)**: 创建 `PageErrorBoundary.tsx` 包裹全部 14 个页面；Settings 脏状态追踪 + 导航守卫 + 未保存确认弹窗

### 当前系统状态
- 测试: 1047/1047 Python passed, 0 TS errors
- P0: ✅ | P1: ✅ | P2: ✅ | P3: ✅ | P4: ✅

## [2026-03-31 Session 8] P2 续 + P3 审计完成 — 文档同步完成

### 本次完成了什么
- **P2 架构续审计 (4 项)**: TYPE_CHECKING 修复 + resilience None 安全 + 8 处 useEffect 依赖修复 + 2 处设计意图注释
- **P3 性能审计 (6 项)**: 5 处阻塞 subprocess→async + 1 处 asyncio.to_thread + 2 处无界数据结构加上限 + 2 处 SQLite close()

### 当前系统状态
- 测试: 1047/1047 passed, 0 TS errors
- P0: ✅ | P1: ✅ | P2: ✅ | P3: ✅

---

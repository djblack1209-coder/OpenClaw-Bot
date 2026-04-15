# OpenCode Workflow 全面升级设计文档

> 日期: 2026-04-15
> 领域: `infra` / `docs`
> 参考: anthropics/claude-code (Hook 系统) + garrytan/gstack (Skill 拆分 + Sprint 流程)

---

## 一、背景

当前 OpenClaw Bot 的 AI 开发工作流由 4 层组成：
1. **AGENTS.md** — 总纲 SOP（8 阶段 + 质量门 + 文档规则）
2. **Superpowers Skills** — 14 个通用开发技能（brainstorming、TDD、debugging 等）
3. **MetaGPT Skills** — 6 个角色技能（PRD、架构、审查、QA 等）
4. **Plugins** — 3 个自动化插件（auto-commit、gpt-mode-switcher、mcp-cleanup）

### 核心问题

1. **规则与执行断层** — 很多好规则（回归防护、HANDOFF 清理、提交格式）停留在文本层面，AI 可以选择性遵守
2. **自动提交质量差** — auto-commit.js 的时间戳提交 + `--no-verify` 是最弱环节
3. **Skill 调度无路由** — 25+ 个 Skill 缺少"什么时候用哪个"的明确指引

---

## 二、方案概述

三层升级，保留现有架构，做增量改进：

| 层 | 内容 | 文件数 |
|----|------|--------|
| 第 1 层：Skill 拆分 | 5 个新 SKILL.md（ship/review/investigate/health-check/handoff） | 5 新建 |
| 第 2 层：插件强化 | 1 个改造（auto-commit）+ 2 个新建（regression-guard/doc-sync-guard） | 1 改 + 2 新 |
| 第 3 层：AGENTS.md 升级 | 3 个新增部分（决策分类/Skill 路由/验证铁律） | 1 改动 |

---

## 三、第 1 层：新建 5 个 Skill

### 3.1 `/ship` — 发布流程

**位置**: `~/.config/opencode/skills/ship/SKILL.md`
**触发**: 用户说"发版"、"提 PR"、"准备上线"

**步骤**:
1. 检查分支状态 + 拍基线（`pytest --tb=no -q`）
2. 合并主分支最新代码
3. 跑全量测试（pytest + tsc --noEmit）
4. 安全扫描（无硬编码密钥、无 .env）
5. 生成 CHANGELOG 条目
6. 更新相关注册表文档
7. 语义化提交
8. 创建 PR（自动生成描述）

**铁律**: 步骤 3 不通过 → 直接停止

### 3.2 `/review` — 代码审查

**位置**: `~/.config/opencode/skills/review/SKILL.md`
**触发**: 用户说"审查代码"、"看看改得怎么样"

**步骤**:
1. `git diff` 获取所有变更
2. 4 维度审查：功能正确性、代码风格、安全性、文档完整性
3. 生成审查报告（LGTM/LBTM + 问题列表）
4. LBTM 时自动修复，最多 3 轮
5. 结果写入 CHANGELOG

### 3.3 `/investigate` — 根因调试

**位置**: `~/.config/opencode/skills/investigate/SKILL.md`
**触发**: 用户说"出 Bug 了"、"报错了"、"不工作了"

**步骤**:
1. 收集错误信息
2. 查 HEALTH.md 是否已有记录
3. 定位源码位置
4. 假设→验证循环（最多 5 轮）
5. 修复 + 回归测试
6. 登记 HEALTH.md（新 Bug）
7. 更新 CHANGELOG
8. 用大白话给用户报告

### 3.4 `/health-check` — 系统健康检查

**位置**: `~/.config/opencode/skills/health-check/SKILL.md`
**触发**: 用户说"系统怎么样"、"健康检查"

**步骤**:
1. `pytest tests/ --tb=no -q`
2. `npx tsc --noEmit`
3. 读 HEALTH.md 统计活跃问题
4. 读 CHANGELOG 最近 3 条
5. 大白话汇报

### 3.5 `/handoff` — 会话交接

**位置**: `~/.config/opencode/skills/handoff/SKILL.md`
**触发**: 对话结束时 / 用户说"继续"时

**写入模式**:
1. 总结本次完成的工作
2. 列出未完成的工作
3. 标注坑和注意事项
4. 汇报系统状态
5. 写入 HANDOFF.md
6. 自动裁剪到最近 5 条

**读取模式**:
1. 读 HANDOFF.md
2. 读 HEALTH.md
3. 读 CHANGELOG 最近 3 条
4. 汇报 + 恢复上下文

---

## 四、第 2 层：插件强化

### 4.1 改造 `auto-commit.js`

**变更**:
- 用 `git diff --staged --stat` 分析改动，生成语义化提交信息
- 格式：`[类型] 简要描述`（类型：新增/修复/优化/重构/配置/文档）
- 去掉 `--no-verify`，保留 pre-commit hooks
- 提交前扫描 staged 文件，发现 `.env`/API Key 模式 → 拒绝提交并告警
- 保留自动推送功能

### 4.2 新建 `regression-guard.js`

**触发**: `session.idle`
**逻辑**:
1. `git diff --name-only` 检测本轮改动
2. .py 文件改动 → `pytest tests/ --tb=no -q`
3. .ts/.tsx 文件改动 → `npx tsc --noEmit`
4. 对比基线，测试数下降 → 告警
5. 结果存临时文件供 AI 读取

### 4.3 新建 `doc-sync-guard.js`

**触发**: `session.idle`
**逻辑**:
1. `git diff --name-only` 检测改动
2. 匹配 UPDATE_PROTOCOL 规则，生成文档更新提醒
3. 注入 AI 上下文

---

## 五、第 3 层：AGENTS.md 升级

### 5.1 决策分类表（新增 §1.5）

| 分类 | 规则 | 举例 |
|------|------|------|
| 机械决策 — 直接做 | 只有一个正确答案 | 修复语法错误、更新 import、格式化 |
| 品味决策 — 做了再汇报 | 合理的人可能选不同 | 变量命名、代码组织、日志级别 |
| 架构决策 — 先提方案再做 | 影响多模块、不可逆 | 新增依赖、改数据库、改 API |
| 业务决策 — 必须问用户 | 影响用户可见行为 | 功能规格、定价、交互流程 |

### 5.2 Skill 路由表（新增 §2.1）

| 用户意图 | 推荐 Skill 链 |
|----------|---------------|
| 加功能 | brainstorming → writing-plans → metagpt-sop |
| 出 Bug | investigate |
| 审查代码 | review |
| 发版/PR | ship |
| 系统状态 | health-check |
| 继续上次 | handoff(读取) |
| 测试 | test-driven-development |
| 调试 | systematic-debugging |
| 重构 | requesting-code-review → review |

### 5.3 验证铁律（替换 §1.3 P2）

1. "应该没问题了" → 跑一下。自信不等于证据。
2. "之前测过了" → 代码改过了，重新测。
3. "改动很小不会出错" → 小改动是回归的最大来源。
4. 声称"完成"必须附带：测试输出 + 变更对比 + CHANGELOG 条目
5. 没有以上证据的"完成" = 没完成。

---

## 六、实施顺序

1. 写设计文档（本文件）
2. 新建 5 个 Skill 文件
3. 改造 auto-commit.js
4. 新建 regression-guard.js
5. 新建 doc-sync-guard.js
6. 升级 AGENTS.md
7. 更新 CHANGELOG

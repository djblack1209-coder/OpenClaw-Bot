---
name: superpowers-workflow
description: 结构化开发方法论（brainstorm→spec→plan→TDD→review），让 Agent 开发更专业、更可控。参考 obra/superpowers 90k stars 项目。
metadata: {"openclaw":{"emoji":"⚡"}}
---

# Superpowers 结构化开发工作流

基于 obra/superpowers 的结构化软件开发方法论，强制 Agent 按流程开发，避免跳步和低质量输出。

## 核心流程（强制执行）

### Phase 1: Brainstorming（头脑风暴）

- 不要直接写代码。先问 严总 真正想要什么。
- 通过提问细化需求，探索替代方案。
- 分段展示设计，每段足够短以便阅读和消化。
- 输出: 设计文档（保存到 `memory/development/`）

### Phase 2: Planning（实施计划）

- 将工作拆分为 2-5 分钟的小任务。
- 每个任务包含: 精确文件路径、完整代码、验证步骤。
- 计划要清晰到"一个没有项目上下文的初级工程师也能执行"。
- 强调 YAGNI（不需要就不做）和 DRY。
- 输出: 编号任务列表

### Phase 3: TDD 执行（测试驱动开发）

- 严格 RED-GREEN-REFACTOR 循环:
  1. 写失败的测试
  2. 看它失败
  3. 写最少代码让它通过
  4. 看它通过
  5. 提交
- 在测试之前写的代码要删掉重来。
- 每个任务完成后立即提交。

### Phase 4: Code Review（代码审查）

- 对照计划审查实现。
- 按严重程度报告问题: Critical（阻塞）、High、Medium、Low。
- Critical 问题必须修复后才能继续。

### Phase 5: Finish（收尾）

- 验证所有测试通过。
- 提供选项: 合并/PR/保留/丢弃。
- 清理工作分支。

## 在 Telegram 中的使用方式

当 严总 发起开发任务时:

```
严总: 帮我加一个新功能...

Agent 回复:
📋 开发计划 (superpowers 模式)

Phase 1 - 需求确认:
1. [问题1]
2. [问题2]

确认后我会输出实施计划，然后按 TDD 逐步执行。
```

## 与现有 dev-todo-mode 的关系

- `dev-todo-mode` 是轻量级的任务跟踪模式
- `superpowers-workflow` 是完整的结构化开发流程
- 简单任务用 dev-todo-mode，复杂功能用 superpowers-workflow
- 判断标准: 预计 >30 分钟或涉及 >3 个文件的任务，用 superpowers

## 触发条件

- 严总 说 "用 superpowers 模式"、"结构化开发"、"TDD 模式"
- 复杂开发任务（自动判断）
- `/dev` 命令 + 复杂任务描述

---
name: openviking
description: OpenViking 上下文数据库集成。用文件系统范式管理 Agent 记忆/资源/技能，支持三层按需加载和自进化，大幅降低 token 消耗。
metadata: {"openclaw":{"emoji":"🗄️"}}
---

# OpenViking 上下文数据库

字节跳动开源的 AI Agent 上下文数据库，用文件系统范式统一管理 memory、resources、skills。

## 核心概念

- **虚拟文件系统**: 所有上下文映射到 `viking://` URI，层级目录结构
- **三层按需加载**:
  - L0 (摘要): ~100 tokens，快速相关性判断
  - L1 (概览): ~2k tokens，核心信息用于规划
  - L2 (详情): 完整内容，按需加载
- **目录递归检索**: 向量搜索 + 目录遍历，先定位高分目录再递归细化
- **自动会话记忆**: 从对话中自动提取长期记忆

## 安装

```bash
pip install openviking --upgrade --force-reinstall
```

要求: Python 3.10+, Go 1.22+

## 与 OpenClaw 集成方式

### 1. 作为记忆后端

替代当前 SQLite memory，用 OpenViking 管理所有 agent 记忆：

```bash
# 启动 OpenViking 服务
openviking-server --port 1933

# 导入现有记忆
ov add-resource apps/openclaw/memory/
```

### 2. 作为技能索引

将 40+ skills 导入 OpenViking，实现语义检索：

```bash
ov add-resource apps/openclaw/skills/
ov find "交易风控相关的技能"
```

### 3. 作为知识库

导入项目文档、代码库、外部资料：

```bash
ov add-resource docs/
ov add-resource packages/openclaw-npm/src/
```

## 使用命令

```bash
ov ls viking://resources/          # 列出资源
ov tree viking://memory/ -L 2      # 查看记忆树
ov find "社交发布失败的处理方法"      # 语义搜索
ov grep "Telegram" --uri memory    # 模式搜索
```

## 对比当前 SQLite Memory

| 维度 | SQLite (当前) | OpenViking |
|------|--------------|------------|
| 检索方式 | 需要 embedding API | 内置向量 + 目录检索 |
| Token 消耗 | 全量加载 | L0/L1/L2 按需加载，降低 83-96% |
| 上下文理解 | 扁平存储 | 层级目录，全局理解更好 |
| 自进化 | 手动维护 | 自动从会话提取记忆 |
| 调试 | 黑盒 | 可观测检索轨迹 |

## 触发条件

当 严总 提到以下关键词时激活:
- "openviking"、"上下文数据库"、"记忆升级"、"viking"
- "导入知识库"、"语义检索"

## 执行流程

1. 检查 OpenViking 是否已安装 (`which ov`)
2. 若未安装，引导 严总 执行 `pip install openviking`
3. 启动服务并导入指定资源
4. 配置 OpenClaw gateway 使用 OpenViking 作为记忆后端
5. 验证检索功能正常

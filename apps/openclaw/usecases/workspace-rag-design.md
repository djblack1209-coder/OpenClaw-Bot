# Workspace RAG Design

## 目标

在 OpenClaw 当前工作区上先做一层轻量级 RAG，不追求一开始就上向量数据库，先完成：

1. 工作区内容切块
2. 可追踪 chunk id / 行号
3. 基础召回
4. 降低 ops 日志污染
5. 后续可接 embeddings / rerank

## 第一阶段：静态索引

索引来源：
- `skills/`
- `usecases/`
- `memory/`
- `MEMORY.md`
- `TOOLS.md`
- `USER.md`
- `SOUL.md`
- `AGENTS.md`
- `TELEGRAM_COMMANDS.md`

输出文件：
- `.manager/workspace-index.json`

由脚本生成：
- `tools/workspace-indexer.mjs`

### 当前索引结构（已实现）

每个 chunk 附带：
- `chunkId`：改为 `path#Lx-Ly`
- `source`：`knowledge | memory | journal | ops | reference`
- `fileType`：`markdown | jsonl | json | text`
- `title / sectionTitle`
- `startLine / endLine`
- `mtimeMs`

### 当前切块策略（已实现）

- Markdown：优先按标题 section 切块，再按目标字符数二次切分
- JSONL：按事件组切块，避免整份日志成为单个长块
- 普通文本：按行聚合，避免纯固定长度硬切

## 第二阶段：检索器

当前已补：
- query 归一化
- token 扩展
- 标题 / 路径 / 正文混合打分
- source-aware scoring
- intent-aware boosting
- 默认去重，避免同一文件刷屏
- 结果附带命中理由、line range、source

下一步建议增加：
- embedding 召回
- top-k 合并
- 轻量 rerank
- 只注入最相关 chunks

## 第三阶段：日志污染控制

当前策略：
- 将 `memory/task-runs.jsonl`、`memory/failures.jsonl`、`memory/retrieval-runs.jsonl`、`heartbeat-state.json` 归类为 `ops`
- 默认检索时对 `ops` 降权
- 当 query 明显是排障 / 运行日志意图时，再对 `ops` 回补加权

这样做的目标是：
- 日常知识检索尽量命中 skills / usecases / memory 笔记
- 排障和复盘场景仍能找回运行日志

## 第四阶段：任务接入

优先接入场景：
1. 记忆检索
2. 技能选择
3. usecase 路由
4. 社媒工作流
5. 开发任务上下文准备

## 为什么先这样做

因为现在最缺的是：
- 有组织的 chunk 数据
- 可复用的工作区索引
- 检索前置层
- 知识与运行日志的基本分层

先把这些基础搭好，后续接 embeddings / 向量检索 / rerank 都会顺很多。

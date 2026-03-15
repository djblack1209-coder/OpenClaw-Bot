# Task Run Logging Spec

## 目标

给 OpenClaw 增加最小可用、可校验、可长期追加的任务运行记录，便于复盘、调优和排错。

## 记录文件

- `memory/task-runs.jsonl`
- `memory/failures.jsonl`
- `memory/retrieval-runs.jsonl`

每行一条 JSON；允许保留 `{"_comment":"..."}` 这种初始化注释行。

---

## CLI 用法

### 追加日志

```bash
node tools/task-log.mjs <task|failure|retrieval> '<json-payload>'
```

### 校验现有日志文件

```bash
node tools/task-log.mjs validate <task|failure|retrieval> [file]
```

说明：
- 脚本会自动补 `ts`
- 会清理控制字符和多余空白，降低 JSONL 被脏文本污染的概率
- 会做最小 schema 校验；缺关键字段会拒绝写入
- 未识别字段不会自动保留，避免日志结构长期漂移

---

## 通用字段

三类日志都支持以下通用字段（按需写）：

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:subagent:...",
  "taskType": "dev|research|heal|brief|browser_extract",
  "status": "ok|error|partial|running|queued|skipped|cancelled",
  "notes": "补充说明"
}
```

字段说明：
- `ts`: ISO 时间戳；不传则自动生成
- `taskId`: 任务级唯一标识，建议同一任务链复用
- `sessionId`: 代理/会话 ID，便于串联上下文
- `taskType`: 任务分类；task/failure 必填，retrieval 可选
- `status`: 状态字段；不同日志类型可用值略有不同
- `notes`: 简短补充说明

---

## task-runs.jsonl

### 必填字段

- `taskType`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:main",
  "taskType": "social_post",
  "inputSummary": "把研究摘要改写成 X 帖子",
  "tools": ["browser", "exec"],
  "usedSkill": "summarize",
  "usedUsecase": "social-content-operating-system",
  "status": "ok",
  "durationMs": 12345,
  "itemCount": 1,
  "outputs": ["x_post_draft"],
  "warnings": ["used cached cookies"],
  "tags": ["social", "x"],
  "notes": "已生成并待人工确认"
}
```

### task 专属字段

- `inputSummary`: 输入摘要
- `tools`: 实际调用工具列表
- `usedSkill`: 使用的 skill 名
- `usedUsecase`: 使用的 usecase 名
- `durationMs`: 总耗时
- `itemCount`: 产出条目数
- `outputs`: 关键输出标记
- `warnings`: 非致命风险/异常
- `tags`: 轻量标签

---

## failures.jsonl

### 必填字段

- `taskType`
- `detail`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:main",
  "taskType": "browser_extract",
  "status": "error",
  "errorType": "login_missing|site_blocked|tool_timeout|bad_route",
  "failedTool": "browser",
  "tools": ["browser", "exec"],
  "detail": "页面被登录墙拦截，未拿到正文",
  "nextAction": "切到本机 Chrome profile 后重试",
  "retryable": true,
  "durationMs": 4200,
  "warnings": ["relay tab detached"]
}
```

### failure 专属字段

- `errorType`: 失败类型
- `failedTool`: 最终失败发生在哪个工具
- `detail`: 失败原因摘要
- `nextAction`: 建议下一步
- `retryable`: 是否适合重试
- `durationMs`: 失败前耗时
- `tools`: 涉及工具列表
- `warnings`: 上下文风险提示

状态允许值：`error | partial | cancelled | skipped`

---

## retrieval-runs.jsonl

### 必填字段

- `query`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:31:14.103Z",
  "taskId": "task-20260309-rag-01",
  "sessionId": "agent:main:main",
  "taskType": "research",
  "status": "ok",
  "query": "RAG social content logging",
  "rewrittenQuery": "task run logging spec retrieval logging",
  "sources": ["usecases/task-run-logging-spec.md", "MEMORY.md"],
  "topHits": ["usecases/task-run-logging-spec.md#1", "MEMORY.md#3"],
  "hitCount": 2,
  "quality": "good",
  "retrievalMs": 180,
  "indexVersion": "workspace-index@2026-03-09",
  "notes": "命中 spec 与 roadmap"
}
```

### retrieval 专属字段

- `query`: 原始查询
- `rewrittenQuery`: 改写后的查询
- `sources`: 命中的源文件路径列表
- `topHits`: 命中的 chunk / path#line 列表
- `hitCount`: 命中数
- `quality`: `good | weak | miss`
- `retrievalMs`: 检索耗时
- `indexVersion`: 索引版本/快照标识

状态允许值：`ok | partial | error`

---

## 落地原则

- 继续保持 JSONL append-only，简单直接
- 写入前做轻量规范化，避免脏数据把整份日志搞坏
- 只保留稳定字段，避免“想记什么就塞什么”导致 schema 漂移
- 先服务复盘，再追求自动分析
- 高频任务优先接入：`/heal`、`/brief`、社媒发布、视频提取、开发任务、workspace 检索

## 建议实践

1. 同一任务链尽量复用 `taskId`
2. 子代理/会话运行尽量补 `sessionId`
3. 失败同时记 `task` + `failure` 时，`task.status` 和 `failure.status` 保持一致语义
4. 检索日志尽量记录 `hitCount` 和 `quality`
5. 定期跑：

```bash
node tools/task-log.mjs validate task
node tools/task-log.mjs validate failure
node tools/task-log.mjs validate retrieval
```

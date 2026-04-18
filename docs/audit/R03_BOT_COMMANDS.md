# R03 Telegram Bot 命令层审计

> **轮次**: R3 | **状态**: 待执行 | **预估条目**: ~45
> **审计角色**: CPO + QA Lead + Staff Engineer
> **前置条件**: R2 完成
> **验证基线**: `cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5`

---

## 3.1 命令注册完整性（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.01 | 设计 | `multi_main.py:80-127` | 27 个通用命令是否全部正确注册到 7 个 Bot | 对照 COMMAND_REGISTRY.md | ⬜ |
| R3.02 | 设计 | `multi_main.py` | free_llm Bot 的简化8命令集是否正确 | 检查命令列表差异 | ⬜ |
| R3.03 | 设计 | `src/bot/` | 命令 handler 函数是否都有 docstring 和中文帮助文本 | 逐一检查 | ⬜ |
| R3.04 | 设计 | `src/bot/` | /help 命令是否列出所有可用命令（按分类） | 模拟调用 /help | ⬜ |
| R3.05 | 文档 | `docs/registries/COMMAND_REGISTRY.md` | 注册表中的命令是否与代码一一对应 | 自动化对比 | ⬜ |
| R3.06 | 设计 | `src/bot/` | 命令别名/中文别名是否全部生效 | 检查 NLP 触发词映射 | ⬜ |

## 3.2 核心命令逐一验证（12 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.07 | UX | `src/bot/` | /start — 新用户首次交互流程是否完整 | 跟踪 handler 代码 | ⬜ |
| R3.08 | UX | `src/bot/` | /chat — 自由对话是否正确路由到对应 Bot 的模型 | 检查模型选择逻辑 | ⬜ |
| R3.09 | UX | `src/bot/` | /invest — 投资分析命令是否返回有效数据 | 检查返回格式 | ⬜ |
| R3.10 | UX | `src/bot/` | /trade — 交易执行命令的风控流程 | 跟踪调用链 | ⬜ |
| R3.11 | UX | `src/bot/` | /social — 社媒发文命令流程 | 检查 compose→publish 链 | ⬜ |
| R3.12 | UX | `src/bot/` | /xianyu — 闲鱼客服命令 | 检查 QR 登录→自动回复链 | ⬜ |
| R3.13 | UX | `src/bot/` | /remind — 提醒命令（周期性+同义词触发+时区） | 检查定时器逻辑 | ⬜ |
| R3.14 | UX | `src/bot/` | /accounting — 记账命令（17个分类） | 检查分类识别 | ⬜ |
| R3.15 | UX | `src/bot/` | /shopping — 比价命令（四级降级） | 检查降级链 | ⬜ |
| R3.16 | UX | `src/bot/` | /news — 新闻聚合命令 | 检查数据源 | ⬜ |
| R3.17 | UX | `src/bot/` | /memory — 记忆管理命令 | 检查 CRUD 操作 | ⬜ |
| R3.18 | UX | `src/bot/` | /settings — 用户设置命令 | 检查偏好持久化 | ⬜ |

## 3.3 回调按钮处理器（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.19 | 设计 | `src/bot/callback_handlers.py` 或等效 | 14 个回调 pattern 是否全部注册 | 检查 CallbackQueryHandler | ⬜ |
| R3.20 | UX | 回调处理器 | 按钮回调是否有加载状态反馈（answer_callback_query） | 检查每个 handler | ⬜ |
| R3.21 | 安全 | 回调处理器 | 回调数据是否有防篡改机制 | 检查 callback_data 验证 | ⬜ |
| R3.22 | UX | 回调处理器 | 过期按钮点击是否有友好提示 | 检查超时处理 | ⬜ |
| R3.23 | 设计 | 回调处理器 | 投资投票按钮的并发处理 | 检查锁/原子操作 | ⬜ |
| R3.24 | 设计 | 回调处理器 | 交易确认按钮的二次确认机制 | 检查安全流程 | ⬜ |

## 3.4 中文 NLP 触发（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.25 | 设计 | `src/intent/fast_parse.py` 或等效 | 正则匹配规则覆盖率 | 对照所有命令的中文别名 | ⬜ |
| R3.26 | UX | `src/intent/` | "帮我记住/别忘了/设个闹钟" 等同义词是否都触发 /remind | 逐一测试 | ⬜ |
| R3.27 | UX | `src/intent/` | "今天花了/记一笔/支出" 等是否触发 /accounting | 逐一测试 | ⬜ |
| R3.28 | UX | `src/intent/` | 投资相关自然语言（"分析一下特斯拉/TSLA 怎么样"）是否正确路由 | 检查 intent→handler 映射 | ⬜ |
| R3.29 | 设计 | `src/intent/` | 意图冲突解决：多个意图匹配时的优先级 | 检查评分机制 | ⬜ |
| R3.30 | 设计 | `src/intent/` | LLM 降级分类：正则失败后是否正确 fallback 到 LLM | 检查降级链 | ⬜ |

## 3.5 Workflow Mixin 空壳（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.31 | Stub | `src/bot/workflow_mixin.py` | **STUB-01~08**: 8个空壳方法清单 | 列出所有 stub 方法 | ⬜ |
| R3.32 | Stub | `src/bot/workflow_mixin.py` | 评估每个 stub：是否有用户可触发的入口 | 如有入口则必须实现 | ⬜ |
| R3.33 | Stub | `src/bot/workflow_mixin.py` | 未使用的 stub：标记为"可删除"或"待实现" | 检查调用方 | ⬜ |
| R3.34 | 设计 | `src/bot/workflow_mixin.py` | 已实现的方法是否有完整的错误处理 | 逐一检查 | ⬜ |
| R3.35 | 设计 | `src/bot/` | Mixin 架构是否合理（继承链是否清晰） | 画出 Mixin 继承图 | ⬜ |

## 3.6 消息处理管道（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.36 | 设计 | `src/bot/message_mixin.py` | 消息接收→sanitize→intent→route→response 全链路 | 跟踪调用链 | ⬜ |
| R3.37 | 设计 | `src/bot/message_mixin.py` | 流式响应（streaming）是否正确实现 | 检查 SSE/edit_message 逻辑 | ⬜ |
| R3.38 | UX | `src/bot/message_mixin.py` | 长消息分割：超过 Telegram 4096 字符限制的处理 | 检查分割逻辑 | ⬜ |
| R3.39 | 设计 | `src/bot/message_mixin.py` | 图片/语音/文件消息的处理 | 检查 media handler | ⬜ |
| R3.40 | 设计 | `src/bot/message_mixin.py` | 群聊 vs 私聊的行为差异 | 检查 chat_type 判断 | ⬜ |

## 3.7 错误处理与用户反馈（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R3.41 | UX | `src/bot/error_handler.py` | 全局错误 handler 是否给用户友好提示 | 检查 error_handler 实现 | ⬜ |
| R3.42 | UX | `src/bot/` | LLM 超时/限流时的用户提示 | 检查降级消息 | ⬜ |
| R3.43 | UX | `src/bot/` | 网络错误时的重试和用户提示 | 检查 retry 逻辑 | ⬜ |
| R3.44 | 设计 | `src/bot/` | Telegram flood control 处理（HTTPError 429） | 检查限流机制 | ⬜ |
| R3.45 | 设计 | `src/bot/` | 并发消息处理：多用户同时发消息是否安全 | 检查线程/协程安全 | ⬜ |

---

## 执行检查清单

- [ ] 基线快照
- [ ] 优先处理 STUB-01~08 空壳方法
- [ ] 每个命令至少验证 handler 函数存在且有 try/except
- [ ] NLP 触发词与 COMMAND_REGISTRY 对齐
- [ ] 回归测试
- [ ] 更新 CHANGELOG.md

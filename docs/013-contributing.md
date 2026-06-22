# OpenClaw Bot 贡献指南

> 类型: 架构/设计
> 最后更新: 2026-06-22
> 目标: 让外部贡献者能安全、低成本地参与 OpenClaw Bot 开源维护。

## 一、欢迎的贡献类型

OpenClaw Bot 当前优先欢迎这些贡献：

1. **文档改进**：修正启动步骤、补充模块说明、翻译术语、整理使用边界。
2. **测试补齐**：为 Bot 命令、API 路由、LLM 路由、配置助手和安全闸门增加回归测试。
3. **Bug 修复**：修复可复现的异常、红屏、命令误路由、日志泄密、边界判断错误。
4. **安全加固**：输入校验、鉴权检查、密钥脱敏、危险动作确认、低敏审计。
5. **小型重构**：降低重复代码、拆分过长函数、改善类型标注和模块边界。

暂不鼓励大型、难回滚的架构改造；这类变更请先开 issue 讨论。

## 二、贡献前准备

```bash
git clone https://github.com/djblack1209-coder/OpenClaw-Bot.git
cd OpenClaw-Bot
```

后端环境：

```bash
cd packages/clawbot
python -m venv .venv312
source .venv312/bin/activate
pip install -r requirements-dev.txt
```

桌面端环境：

```bash
cd apps/openclaw-manager-src
npm install
```

## 三、开发流程

1. 从 `main` 拉新分支，分支名建议使用 `codex/<short-topic>`。
2. 修改前先读相关文档和源码，避免重复造轮子。
3. 每次改动保持小而清晰；一个 PR 尽量只解决一个问题。
4. 所有新增注释使用中文，说明“做了什么”和“为什么这样做”。
5. 不提交密钥、Cookie、token、浏览器 Profile、数据库、构建产物和本机截图。
6. 代码变更必须同步更新 `docs/002-changelog.md`；模块、命令、依赖或 API 变化还要更新 `docs/006-registries.md`。

## 四、验证要求

后端改动优先跑：

```bash
cd packages/clawbot
.venv312/bin/python -m py_compile <changed_file.py>
.venv312/bin/python -m pytest tests/ -q --tb=short
```

前端改动优先跑：

```bash
cd apps/openclaw-manager-src
npx tsc --noEmit
npm run lint
```

全仓检查：

```bash
git diff --check
```

如果测试因为环境缺少真实第三方账号而无法完整运行，请在 PR 中说明：

- 已运行的命令
- 失败原因
- 是否属于既有环境限制
- 是否存在替代的单元测试或静态检查

## 五、PR 描述模板

```markdown
## 改了什么
- 

## 为什么改
- 

## 验证
- [ ] 后端 py_compile / pytest
- [ ] 前端 tsc / lint
- [ ] git diff --check
- [ ] 文档已同步

## 安全边界
- [ ] 没有提交密钥或本机运行数据
- [ ] 没有新增绕过平台风控、验证码、付费墙或服务条款的逻辑
- [ ] 高风险动作保留人工确认或白名单
```

## 六、AI / API credits 使用边界

维护者可以使用 Codex、OpenAI API 或其他 AI 工具辅助开源维护，但只能用于：

- PR review
- 测试生成
- 安全 triage
- 文档和 changelog 整理
- 小型重构建议

不要把赞助 API credits 用于真实交易决策、自动下单、刷量、未授权爬取、验证码绕过、商业客户工作负载或转售。

## 七、行为准则

请保持讨论专业、具体、可复现。报告问题时尽量提供：

- 复现步骤
- 期望结果
- 实际结果
- 日志或截图（先脱敏）
- 运行环境

维护者会优先处理带有最小复现和验证证据的问题。

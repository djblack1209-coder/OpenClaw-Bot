# OpenClaw 文档总索引

> 最后更新: 2026-08-16
> 总文件: 28 个（含 `docs/current/` 的唯一生产当前基线；缺号文件均已退役，可从 Git 恢复）

## 当前基线

| 位置 | 文档 | 内容概要 |
|------|------|---------|
| `current/` | `current-baseline.md` | 唯一当前生产事实、已验证变更、剩余阻塞和下一会话交接提示词 |

## 核心文档 (001-010)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 001 | `001-project-map.md` | 项目架构全景、模块关系、痛点地图 |
| 002 | `002-changelog.md` | 全量变更历史（按日期） |
| 003 | `003-docs-index.md` | 本文件 — 文档导航 |
| 004 | `004-architecture.md` | 系统架构：OMEGA v2 设计 + Bot Agent 三省六部指令 |
| 005 | `005-quickstart.md` | 快速启动、部署、开发者指南、灾备、密钥轮换、API 注册 |
| 007 | `007-operations.md` | JIYU AI、Mac App、备份恢复和已退役运行面的生产运维 |
| 008 | `008-sop.md` | 开发规范：文档优先协议 + 错误翻译参考 |
| 009 | `009-health.md` | 系统健康、Bug、技术债 + 经验库 + 需求跟踪 |
| 010 | `010-feature-specs.md` | 功能规格总集：16 个设计文档 |

## AI 客户端与 JIYU 使用指南 (020-029)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 020 | `020-ai-basics.md` | AI、LLM、Token 和常见指标的小白入门 |
| 021 | `021-claude-code-guide.md` | Claude Code 安装、登录、项目和 CC Switch 路由指南 |
| 022 | `022-claude-desktop-guide.md` | Claude Desktop 的 Chat、Cowork、Code 和扩展开发入口指南 |
| 023 | `023-codex-guide.md` | Codex 安装、项目、审批和 CC Switch API 路由边界 |
| 024 | `024-chatgpt-desktop-guide.md` | ChatGPT Desktop 的 Chat、Work、Codex 和登录边界指南 |
| 025 | `025-opencode-grok-build-guide.md` | OpenCode 与 Grok Build 安装、项目、模式与路由边界 |
| 026 | `026-cc-switch-guide.md` | CC Switch Provider、代理、MCP、更新与用量指南 |
| 027 | `027-model-authenticity-guide.md` | 模型真伪的低成本核对与开源评测边界 |
| 028 | `028-jiyu-service-terms-guide.md` | JIYU 用户可见服务条款与地区分流待实施边界 |
| 029 | `029-jiyu-settings-and-payment-guide.md` | JIYU 支付、S3/R2、安全审核与地域分流设置说明 |

## 附录 (011-015)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 011 | `011-kiro-gateway.md` | Kiro Gateway 子项目文档（架构/Agent 指令/贡献/测试/CLA） |
| 012 | `012-handoff.md` | 退役交接入口；当前提示词只在 `docs/current/current-baseline.md` 维护 |
| 013 | `013-contributing.md` | 开源贡献指南、开发流程、验证要求和 AI/API credits 使用边界 |
| 014 | `014-security.md` | 安全政策、漏洞报告方式、密钥处理规则和高风险动作边界 |
| 015 | `015-code-of-conduct.md` | 社区协作行为准则、敏感信息处理和执行方式 |

## 功能计划 (050-059)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 052 | `052-intel-brief-master-plan.md` | Intel Brief 总体方案、开源轮子搬运规划、多服务器运行基线和分阶段验证路线 |

## 报告/归档 (080-099)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 081 | `081-owner-ops-handbook.md` | 老板日常操作手册：真实健康/订单判断、技术支持诊断、备份恢复 |
| 085 | `085-intel-brief-design-qa.md` | 每日资讯 V2 方案 C + Top 3 + 候选 3 的视觉决策、同视口对比与 Telegram 验收边界 |

## 排除范围

以下不属于主项目 `docs/` 治理范围：
- `AGENTS.md`、`README.md`（项目根入口）
- `apps/openclaw/` Bot 人设/Skill 文件
- `packages/*` 上游包内部文档
- 虚拟环境、`node_modules` 内文档

## 文档规则

详见 `AGENTS.md` §9 硬性规则。摘要：
- **docs/ 是唯一存放位置**，禁止在 docs/ 以外创建 .md 项目文档
- **docs/current/ 是唯一例外，且只能保留 `current-baseline.md`**
- **顶层文件必须命名为 `编号-英文名.md`**
- **新增文档 → 立即更新本索引**

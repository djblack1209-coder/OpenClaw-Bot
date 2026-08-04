# OpenClaw 文档总索引

> 最后更新: 2026-08-05
> 总文件: 24 个（001-015 核心/附录 + 050-052 功能计划 + 080-086 报告/手册，083 为历史停用编号）

## 核心文档 (001-010)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 001 | `001-project-map.md` | 项目架构全景、模块关系、痛点地图 |
| 002 | `002-changelog.md` | 全量变更历史（按日期） |
| 003 | `003-docs-index.md` | 本文件 — 文档导航 |
| 004 | `004-architecture.md` | 系统架构：OMEGA v2 设计 + Bot Agent 三省六部指令 |
| 005 | `005-quickstart.md` | 快速启动、部署、开发者指南、灾备、密钥轮换、API 注册 |
| 006 | `006-registries.md` | 注册表总集：API 池 + 命令 + 依赖 + 模块 |
| 007 | `007-operations.md` | Frist-API 运维、闲鱼 Cookie、部署验证 |
| 008 | `008-sop.md` | 开发规范：文档优先协议 + 错误翻译参考 |
| 009 | `009-health.md` | 系统健康、Bug、技术债 + 经验库 + 需求跟踪 |
| 010 | `010-feature-specs.md` | 功能规格总集：16 个设计文档 |

## 附录 (011-015)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 011 | `011-kiro-gateway.md` | Kiro Gateway 子项目文档（架构/Agent 指令/贡献/测试/CLA） |
| 012 | `012-handoff.md` | 会话交接摘要（AI Agent 上下文恢复） |
| 013 | `013-contributing.md` | 开源贡献指南、开发流程、验证要求和 AI/API credits 使用边界 |
| 014 | `014-security.md` | 安全政策、漏洞报告方式、密钥处理规则和高风险动作边界 |
| 015 | `015-code-of-conduct.md` | 社区协作行为准则、敏感信息处理和执行方式 |

## 功能计划 (050-059)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 050 | `050-frist-api-86game-clone-commerce-plan.md` | Frist-API 86GameStore 风格后台、兑换码售卖闭环、渠道同步倍率和闲鱼发货计划 |
| 051 | `051-jiyu-brand-production-plan.md` | CC中转品牌收口、域名/HTTPS、生产加固分期和生产内测验收 |
| 052 | `052-intel-brief-master-plan.md` | Intel Brief 总体方案、开源轮子搬运规划、多服务器运行基线和分阶段验证路线 |

## 报告/归档 (080-099)

| 编号 | 文档 | 内容概要 |
|------|------|---------|
| 080 | `080-new-api-capability-roadmap.md` | CC中转 New-API 原生能力盘点、生产启用状态和“原生优先、自研补强”路线 |
| 081 | `081-owner-ops-handbook.md` | 老板日常操作手册：绿灯/红灯、闲鱼订单、替换模式、健康检查、备份恢复 |
| 082 | `082-open-source-wheel-research.md` | GitHub 高 Star 轮子调研：闲鱼、微博、小红书、抖音、知乎、财经、X、爬虫框架接入建议 |
| 084 | `084-intel-brief-implementation-report.md` | Intel Brief Phase 0 / Phase B 历史验收证据汇总；当前状态以健康文档和变更日志为准 |
| 085 | `085-intel-brief-design-qa.md` | 每日资讯 V2 方案 C + Top 3 + 候选 3 的视觉决策、同视口对比与 Telegram 验收边界 |
| 086 | `086-release-evidence.md` | 全维度审计闭环的 CI、安全、供应链、灾备、桌面构建与截图证据 |

## 排除范围

以下不属于主项目 `docs/` 治理范围：
- `AGENTS.md`、`README.md`（项目根入口）
- `apps/openclaw/` Bot 人设/Skill 文件
- `packages/*` 上游包内部文档
- 虚拟环境、`node_modules` 内文档

## 文档规则

详见 `AGENTS.md` §9 硬性规则。摘要：
- **docs/ 是唯一存放位置**，禁止在 docs/ 以外创建 .md 项目文档
- **docs/ 内禁止子目录**
- **所有文件必须命名为 `编号-英文名.md`**
- **新增文档 → 立即更新本索引**

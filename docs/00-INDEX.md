# OpenClaw 文档总索引

> 最后更新: 2026-04-25

## 核心文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 项目全景地图 | `docs/PROJECT_MAP.md` | 项目架构、模块关系、用户痛点地图（AI 必读） |
| 文档入口 | `docs/README.md` | 文档导航总入口 |
| 变更日志 | `docs/CHANGELOG.md` | 全量变更历史，含领域标签和影响模块 |
| 变更日志 (2026-04) | `docs/CHANGELOG/2026-04.md` | 2026 年 4 月变更明细 |

## 状态文档 (docs/status/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统健康仪表盘 | `docs/status/HEALTH.md` | Bug、技术债、性能、安全问题登记 |
| 会话交接摘要 | `docs/status/HANDOFF.md` | AI 会话间工作交接记录 |

## 注册表 (docs/registries/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 模块注册表 | `docs/registries/MODULE_REGISTRY.md` | 全部 288 个 Python 模块索引 |
| 命令注册表 | `docs/registries/COMMAND_REGISTRY.md` | Bot 全部 104 条命令清单 |
| 依赖清单 | `docs/registries/DEPENDENCY_MAP.md` | pip 依赖清单（62 项） |
| API 号池注册表 | `docs/registries/API_POOL_REGISTRY.md` | LLM API Key 池管理 |

## 架构文档 (docs/architecture/)

| 文档 | 路径 | 说明 |
|------|------|------|
| OMEGA v2 架构设计 | `docs/architecture/OMEGA_V2_ARCHITECTURE.md` | 系统整体架构设计 |
| 积木化解构报告 | `docs/architecture/MRU_OPENSEARCH_REPORT.md` | 模块解构与开源情报报告 |
| 优化实施计划 | `docs/architecture/OPTIMIZATION_PLAN.md` | 全面优化方案 |

## 审计报告 (docs/audit/)

| 文档 | 路径 | 说明 |
|------|------|------|
| R01 基础设施审计 | `docs/audit/R01_INFRA.md` | 基础设施与文件治理（✅ 已完成） |
| R02 后端核心审计 | `docs/audit/R02_BACKEND_CORE.md` | 后端核心引擎（✅ 已完成） |
| R03 Bot 命令审计 | `docs/audit/R03_BOT_COMMANDS.md` | Telegram Bot 命令层 |
| R04 Bot 业务审计 | `docs/audit/R04_BOT_BUSINESS.md` | Telegram Bot 业务场景 |
| R05 macOS 架构审计 | `docs/audit/R05_MACOS_ARCH.md` | macOS 桌面端架构 |
| R06 macOS 核心审计 | `docs/audit/R06_MACOS_CORE.md` | macOS 核心页面（✅ 已完成） |
| R07 macOS 业务审计 | `docs/audit/R07_MACOS_BUSINESS.md` | macOS 业务页面（✅ 已完成） |
| R08 交易系统审计 | `docs/audit/R08_TRADING.md` | 投资交易系统 |
| R09 闲鱼社媒审计 | `docs/audit/R09_XIANYU_SOCIAL.md` | 闲鱼+社媒+微信+工具链 |
| R10 部署审计 | `docs/audit/R10_DEPLOY.md` | 生产部署与运维 |
| R11 端到端验证 | `docs/audit/R11_E2E_FINAL.md` | 端到端集成验证 |
| R12 CI/CD 审计 | `docs/audit/R12_CI_DEVOPS.md` | CI/CD 管道与 DevOps |

## 商业文档 (docs/business/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 闲鱼商业化方案 | `docs/business/XIANYU_BUSINESS_PLAN.md` | 闲鱼业务商业化规划 |

## 操作指南 (docs/guides/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 快速启动 | `docs/guides/QUICKSTART.md` | OMEGA v2.0 快速启动指南 |
| 开发者指南 | `docs/guides/DEVELOPER_GUIDE.md` | ClawBot 开发环境搭建与规范 |
| 部署指南 | `docs/guides/DEPLOYMENT_GUIDE.md` | 闲鱼商业部署系统使用指南 |
| 灾难恢复 (旧) | `docs/guides/DISASTER_RECOVERY.md` | 灾难恢复指南 (2026-03) |
| 灾难恢复 (新) | `docs/guides/DR_GUIDE.md` | 灾难恢复指南 (2026-04 更新) |
| 密钥轮换 | `docs/guides/KEY_ROTATION_GUIDE.md` | 密钥轮换操作流程 |
| 夜间审计部署 | `docs/guides/NIGHTLY_AUDIT_SETUP.md` | 夜间自动审计系统部署 |
| APP 视觉审计提示词 | `docs/guides/OPENCLAW_APP_VISUAL_AUDIT_PROMPT.md` | 逐页逐组件视觉级审计提示词模板 |

## 开发规范 (docs/sop/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 文档优先协议 | `docs/sop/DOCS_FIRST_PROTOCOL.md` | 涉及外部库时必须先拉文档再写代码 |
| 错误翻译参考表 | `docs/sop/ERROR_TRANSLATION_REF.md` | 技术错误→大白话翻译对照表 |
| 全量审计方案 | `docs/sop/FULL_AUDIT_PLAN.md` | 12 轮全量审计执行方案 v3 |
| 文档更新触发规则 | `docs/sop/UPDATE_PROTOCOL.md` | 什么改动必须更新哪些文档 |

## 功能规格 (docs/specs/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 升级机会清单 | `docs/specs/2026-03-23-upgrade-opportunities-design.md` | 体验诊断与升级机会清单 |
| 智能化跃迁 Wave 1 | `docs/specs/2026-03-30-intelligence-wave1-design.md` | 全系统智能化跃迁设计 |
| 领券+情报集成 | `docs/specs/2026-04-06-coupon-worldmonitor-design.md` | 微信笔笔省领券 + Worldmonitor 情报 |
| Workflow 升级 | `docs/specs/2026-04-15-workflow-upgrade-design.md` | OpenCode Workflow 全面升级设计 |
| UX 体验升级 | `docs/specs/2026-04-19-ux-experience-upgrade-design.md` | 从"能跑通"到"用的爽"体验升级 |

## 报告 (docs/reports/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 健康检查报告 | `docs/reports/HEALTH_CHECK_2026_03_16.md` | 2026-03-16 全功能链路测试报告 |
| MRU 分析报告 | `docs/reports/MRU_ANALYSIS_2026_04_16.md` | 积木化解构与开源情报整合决策报告 |

## Superpowers 工作区 (docs/superpowers/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 体验升级计划 | `docs/superpowers/plans/2026-04-19-experience-upgrade.md` | 体验升级三阶段实施计划 |
| P0 稳定性计划 | `docs/superpowers/plans/2026-04-21-p0-stability-reset.md` | P0 稳定性全量重做实施计划 |
| P0 稳定性设计 | `docs/superpowers/specs/2026-04-21-p0-stability-reset-design.md` | P0 稳定性全量重做设计文档 |

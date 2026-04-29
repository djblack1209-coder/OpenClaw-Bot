# OpenClaw 文档总索引

> 最后更新: 2026-04-28

## 核心文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 项目全景地图 | `docs/project-map.md` | 项目架构、模块关系、用户痛点地图（AI 必读） |
| 变更日志 | `docs/CHANGELOG.md` | 全量变更历史，含领域标签和影响模块 |
| 变更日志 (2026-04) | `docs/changelog-archive/2026-04.md` | 2026 年 4 月变更明细 |

## 状态文档 (docs/status/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统健康仪表盘 | `docs/status/HEALTH.md` | Bug、技术债、性能、安全问题登记 |
| 会话交接摘要 | `docs/status/HANDOFF.md` | AI 会话间工作交接记录 |

## 注册表 (docs/registries/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 模块注册表 | `docs/registries/module-registry.md` | 全部 288 个 Python 模块索引 |
| 命令注册表 | `docs/registries/command-registry.md` | Bot 全部 104 条命令清单 |
| 依赖清单 | `docs/registries/dependency-map.md` | pip 依赖清单（62 项） |
| API 号池注册表 | `docs/registries/api-pool-registry.md` | LLM API Key 池管理 |

## 架构文档 (docs/architecture/)

| 文档 | 路径 | 说明 |
|------|------|------|
| OMEGA v2 架构设计 | `docs/architecture/omega-v2-architecture.md` | 系统整体架构设计 |
| 优化实施计划 | `docs/architecture/optimization-plan.md` | 全面优化方案（已完成，历史参考） |

## 审计报告 (docs/audit/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 审计历史汇总 | `docs/audit/audit-history.md` | R01-R12 共 12 轮全量审计浓缩汇总 |

## 商业文档 (docs/business/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 闲鱼商业化方案 | `docs/business/xianyu-business-plan.md` | 闲鱼业务商业化规划 |

## 操作指南 (docs/guides/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 快速启动 | `docs/guides/quickstart.md` | OMEGA v2.0 快速启动指南 |
| 开发者指南 | `docs/guides/developer-guide.md` | ClawBot 开发环境搭建与规范 |
| 部署指南 | `docs/guides/deployment-guide.md` | 闲鱼商业部署系统使用指南 |
| 灾难恢复 | `docs/guides/disaster-recovery.md` | 灾难恢复指南 (2026-04 更新) |
| 密钥轮换 | `docs/guides/key-rotation.md` | 密钥轮换操作流程 |
| 夜间审计部署 | `docs/guides/nightly-audit-setup.md` | 夜间自动审计系统部署（历史参考） |
| APP 视觉审计提示词 | `docs/guides/visual-audit-prompt.md` | 逐页逐组件视觉级审计提示词模板 |

## 开发规范 (docs/sop/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 文档优先协议 | `docs/sop/docs-first-protocol.md` | 涉及外部库时必须先拉文档再写代码 |
| 错误翻译参考表 | `docs/sop/error-translation-ref.md` | 技术错误→大白话翻译对照表 |
| 全量审计方案 | `docs/sop/full-audit-plan.md` | 12 轮全量审计执行方案 v3 |
| 文档更新触发规则 | `docs/sop/update-protocol.md` | 什么改动必须更新哪些文档 |

## 功能规格 (docs/specs/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 升级机会清单 | `docs/specs/2026-03-23-upgrade-opportunities-design.md` | 体验诊断与升级机会清单 |
| 智能化跃迁 Wave 1 | `docs/specs/2026-03-30-intelligence-wave1-design.md` | 全系统智能化跃迁设计 |
| 领券+情报集成 | `docs/specs/2026-04-06-coupon-worldmonitor-design.md` | 微信笔笔省领券 + Worldmonitor 情报 |
| UX 体验升级 | `docs/specs/2026-04-19-ux-experience-upgrade-design.md` | 从"能跑通"到"用的爽"体验升级 |
| P0 稳定性设计 | `docs/specs/2026-04-21-p0-stability-reset-design.md` | P0 稳定性全量重做设计文档 |

## 实施计划 (docs/plans/)

| 文档 | 路径 | 说明 |
|------|------|------|
| 体验升级计划 | `docs/plans/2026-04-19-experience-upgrade.md` | 体验升级三阶段实施计划 |
| P0 稳定性计划 | `docs/plans/2026-04-21-p0-stability-reset.md` | P0 稳定性全量重做实施计划 |

## 报告 (docs/reports/)

| 文档 | 路径 | 说明 |
|------|------|------|
| MRU 分析报告 | `docs/reports/mru-analysis-2026-04-16.md` | 积木化解构与开源情报整合决策报告 |
| Git 密钥泄露扫描报告 | `docs/reports/secret-scan-2026-04-28.md` | Git 全历史与本机敏感文件扫描结论 |

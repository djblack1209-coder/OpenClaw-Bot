# OpenClaw 文档总索引

> 最后更新: 2026-05-02

本目录已按编号扁平化管理。主项目文档和验收截图都放在 `docs/` 根目录，不再使用 `docs/status/`、`docs/guides/`、`docs/reports/` 等子目录。

排除范围: `AGENTS.md`、`README.md`、`apps/openclaw/` 的 Bot 人设/Skill 文件、`packages/*` 里的上游包文档、虚拟环境和 `node_modules` 文档不属于主项目 `docs/` 治理范围，不能硬搬，否则会破坏工具入口或第三方包结构。

## 001-009 核心入口

| 编号 | 文档 | 说明 |
|------|------|------|
| 001 | `docs/001-project-map.md` | 项目架构、模块关系、用户痛点地图 |
| 002 | `docs/002-changelog.md` | 全量变更历史 |
| 003 | `docs/003-docs-index.md` | 当前文档索引 |

## 010-019 架构、审计和商业

| 编号 | 文档 | 说明 |
|------|------|------|
| 010 | `docs/010-omega-v2-architecture.md` | OMEGA v2 架构设计 |
| 011 | `docs/011-optimization-plan.md` | 优化实施计划 |
| 012 | `docs/012-audit-history.md` | 审计历史汇总 |
| 013 | `docs/013-xianyu-business-plan.md` | 闲鱼商业化方案 |

## 020-029 操作指南

| 编号 | 文档 | 说明 |
|------|------|------|
| 020 | `docs/020-quickstart.md` | OMEGA v2.0 快速启动指南 |
| 021 | `docs/021-deployment-guide.md` | 部署指南 |
| 022 | `docs/022-developer-guide.md` | 开发者指南 |
| 023 | `docs/023-disaster-recovery.md` | 灾难恢复 |
| 024 | `docs/024-frist-api-operator-runbook.md` | Frist-API 运营、支付和价格管理手册 |
| 025 | `docs/025-frist-api-quickstart.md` | Frist-API 快速启动 |
| 026 | `docs/026-frist-api-tencent-deploy.md` | Frist-API 腾讯云部署 |
| 027 | `docs/027-key-rotation.md` | 密钥轮换 |
| 028 | `docs/028-nightly-audit-setup.md` | 夜间审计部署 |
| 029 | `docs/029-visual-audit-prompt.md` | APP 视觉审计提示词 |

## 030-039 注册表

| 编号 | 文档 | 说明 |
|------|------|------|
| 030 | `docs/030-api-pool-registry.md` | LLM API Key 池 |
| 031 | `docs/031-command-registry.md` | Bot 和 Frist-API 操作入口 |
| 032 | `docs/032-dependency-map.md` | 依赖清单 |
| 033 | `docs/033-module-registry.md` | Python 模块索引 |

## 040-049 SOP

| 编号 | 文档 | 说明 |
|------|------|------|
| 040 | `docs/040-docs-first-protocol.md` | 官方文档优先协议 |
| 041 | `docs/041-error-translation-ref.md` | 错误翻译参考 |
| 042 | `docs/042-full-audit-plan.md` | 全量审计方案 |
| 043 | `docs/043-update-protocol.md` | 文档更新触发规则 |

## 050-059 功能规格

| 编号 | 文档 | 说明 |
|------|------|------|
| 050 | `docs/050-2026-03-23-upgrade-opportunities-design.md` | 升级机会清单 |
| 051 | `docs/051-2026-03-30-intelligence-wave1-design.md` | 智能化跃迁 Wave 1 |
| 052 | `docs/052-2026-04-06-coupon-worldmonitor-design.md` | 领券和情报集成 |
| 053 | `docs/053-2026-04-19-ux-experience-upgrade-design.md` | UX 体验升级 |
| 054 | `docs/054-2026-05-01-frist-api-mvp-design.md` | Frist-API MVP 设计 |

## 060-069 状态

| 编号 | 文档 | 说明 |
|------|------|------|
| 060 | `docs/060-health.md` | 系统健康、Bug 和技术债 |
| 061 | `docs/061-handoff.md` | 会话交接摘要 |

## 080-099 报告和归档

| 编号 | 文档 | 说明 |
|------|------|------|
| 080 | `docs/080-frist-api-production-readiness-2026-05-02.md` | Frist-API 生产就绪审计 |
| 081 | `docs/081-frist-api-public-snapshot-2026-05-02.md` | Frist-API 公网快照 |
| 082 | `docs/082-mru-analysis-2026-04-16.md` | MRU 分析报告 |
| 083 | `docs/083-secret-scan-2026-04-28.md` | Git 密钥泄露扫描 |
| 090 | `docs/090-changelog-archive-2026-04.md` | 2026-04 变更归档 |

## 100-199 验收截图

| 编号 | 文件 | 说明 |
|------|------|------|
| 100-118 | `docs/100-*.png` 到 `docs/118-*.png` | Frist-API 历史 UI、公开入口和本地审计截图 |

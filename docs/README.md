# OpenClaw Docs Index

> 文档总入口。先从这里找，不要在根目录到处翻。

## 必读

- `PROJECT_MAP.md`：项目全景、模块分布、入口说明
- `CHANGELOG.md`：变更历史
- `status/HEALTH.md`：已知问题、技术债、风险状态
- `status/HANDOFF.md`：最近会话交接

## 审计与排查

- `sop/FULL_AUDIT_PLAN.md`：全量审计总方案
- `audit/`：分轮次审计记录
- `guides/OPENCLAW_APP_VISUAL_AUDIT_PROMPT.md`：OpenClaw APP 全量视觉级审计提示词

## 开发规范

- `sop/DOCS_FIRST_PROTOCOL.md`：文档优先协议
- `sop/UPDATE_PROTOCOL.md`：更新流程
- `sop/ERROR_TRANSLATION_REF.md`：错误翻译参考

## 注册表

- `registries/MODULE_REGISTRY.md`
- `registries/COMMAND_REGISTRY.md`
- `registries/DEPENDENCY_MAP.md`
- `registries/API_POOL_REGISTRY.md`

## 指南

- `guides/QUICKSTART.md`：快速启动
- `guides/DEVELOPER_GUIDE.md`：开发指南
- `guides/DEPLOYMENT_GUIDE.md`：部署指南
- `guides/DISASTER_RECOVERY.md`：灾备恢复
- `guides/KEY_ROTATION_GUIDE.md`：密钥轮换
- `guides/NIGHTLY_AUDIT_SETUP.md`：夜间审计

## 架构 / 规格 / 报告

- `architecture/`：架构设计与专项分析
- `specs/`：设计规格
- `reports/`：阶段报告
- `business/`：业务规划

## 清理说明

- 根目录重复的 `AUDIT_PLAN.md` 已移除，统一以 `docs/sop/FULL_AUDIT_PLAN.md` 为准。
- 以后新增文档统一放在 `docs/` 下对应分类目录，不再往根目录堆 `.md`。

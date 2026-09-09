# OpenEverything / JIYU 当前运行边界

观察日期：2026-09-09。跨项目生产事实统一以 VPS-Config 的
`docs/current/live-first-closure-v1.md` 为准；本文件只保留本项目接管所需状态。
历史销售、计费、备份数量和已退休迁移细节从 Git 查询，不作为当前验收结论。

## 当前职责

- OpenClaw Gateway、ClawBot、Intel listener/scheduler 和管理端运行在本机 Mac。
- Oracle ARM1 承载 JIYU / Sub2API 0.2.0；Tencent 不承载本项目活动应用。
- 唯一实际 Gateway 包由 manager 的 npm runtime lock 固定为 2026.7.2-beta.7。
  vendor 源码目录不等于当前 Gateway 运行版本，不执行 latest 覆盖或批量重装。
- Sub2API 使用当前 0.2.0 定制补丁；0.1.172/0.1.173 仍由兼容工作流引用，保留为可重放构建材料。

## 本轮修复与验证

- 官方锁定归档 SHA512 匹配后，仅恢复 196 个缺失运行文件：主包 187、AI 依赖 7、highlight.js 2；原有文件没有覆盖，版本、配置和账户没有迁移。
- Gateway 的 HTTP 和正常服务环境下的认证 health 均通过。原生健康脚本修复后 `ok=true`；严格模式仍因 Intel scheduler warning 返回 2，不能写成无告警发布完成。
- 仍有实际调用者的 ClawBot、社交扩展、Sub2API 构建脚本/补丁、Twitch 源码已从本项目当前 HEAD 恢复。社交核心 40 项、Sub2API 运维脚本 7 项针对性检查通过。
- JIYU 健康入口可达、未授权模型入口保持 401。认证后操作被 MFA 挡住，没有绕过、创建 Key、订单或改变费率/销售边界。
- 本轮是锁定运行时修复与源码恢复，没有整包部署产品工作区；New-API 冷回滚 submodule 的 31 个缺失文件按父仓库固定 gitlink 恢复，commit 未变，工作树 clean。

## 未闭环项

- Intel scheduler 已加载，等待自然调度产物验证；不把 `ok=true` 当作所有新闻投递成功。
- JIYU 登录后的关键流程需正常完成 MFA。手机体验、真实销售/计费与供应商成本状态没有本轮验收。
- 本机备份新鲜度检查通过；跨节点统一备份恢复边界以中央基线为准，不把归档可读等同于完整灾备切换。
- 近期 OpenClaw 版本有 Node 与 SDK 破坏性迁移；只在兼容环境和回滚路径可验证时考虑升级。

## 接管顺序

先读中央当前基线与本项目 `README.md`、`docs/005-quickstart.md`、
`docs/014-security.md`，再用已有健康脚本和原生服务状态获取实时事实。
保留已授权 WIP，不回退用户修改；只运行受影响模块的检查。生产写入必须具备
新鲜 prestate、可恢复备份、原子幂等应用和失败回滚，不新增付费资源。

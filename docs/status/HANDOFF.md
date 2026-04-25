# HANDOFF — 会话交接摘要

> 最后更新: 2026-04-25

---

## [2026-04-25] 全量审计与优化 Sprint + 文档治理

### 本次完成了什么

**后端修复 (5 项)**
- /trading/pnl 全零问题: IBKR 离线时兜底计算盈亏
- /trading/dashboard 空数据: 补全数据源
- /monitor/finance 行情全零: yfinance getattr 修复
- /social/analytics 导入错误: execution_hub 路径修正
- /trading/system unknown 状态: 状态映射补全

**前端修复 (5 项)**
- Social 页 t 变量遮蔽 bug
- ControlCenter 响应检查逻辑
- usePortfolioAPI 错误处理
- 8 个页面轮询优化 (useActivePagePolling)
- Settings 通知硬编码

**微信增强**
- 编号命令系统 (60+ 命令映射)
- 欢迎消息 + 完整功能列表

**性能优化**
- Chrome V8 堆 512→128MB + 渲染进程限制 3
- 自动清理多余标签页 (上限 4 个)
- browser-use/CrewAI/进化引擎懒加载

**文档治理**
- 全量文件清理审计: 无垃圾文件残留
- docs/ 结构审计: 命名规范全部合规
- 发现 docs/00-INDEX.md 缺失 (全局指令引用但文件不存在)
- CHANGELOG 更新本轮变更条目
- HANDOFF 裁剪为最近 1 条 (之前积累 5+ 条未清理)

### 未完成的工作
- `docs/00-INDEX.md` 需要创建（全局 AGENTS.md 引用但不存在）
- 微信命令路由需同步到腾讯云 wechat_receiver.py
- 桌面端无系统级推送通知 (Tauri notification API 未接入)
- 微信 AI 对话无记忆/上下文
- `scripts/nightly-audit/unified-prompt.md` 轻微违反 .md 文件归属规则

### 需要注意的坑
- 构建桌面端必须走 `make tauri-build`（会自动清理旧版本）
- `openclaw-gateway` 进程不能和 `wechat_receiver` 同时运行
- g4f 免费池响应慢 (30-90s)，优先用 SiliconFlow/Groq

### 当前系统状态
- 后端: 运行中 (7 Bot 在线)
- 闲鱼: 在线 (自动回复活跃)
- 微信: 云端运行中 (腾讯云)
- 桌面端: `/Applications/OpenClaw.app`
- 文档: CHANGELOG/HANDOFF/HEALTH 已同步

---


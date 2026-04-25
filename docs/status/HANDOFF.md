# HANDOFF — 会话交接摘要

> 最后更新: 2026-04-26

---

## [2026-04-26] 遗留任务清零 + 腾讯云部署

### 本次完成了什么

**后端修复验证（全部 5 个已通过实测）**
- PnL: $0 → **$3,790.14** (account_value=$48,010.36)
- Dashboard: value=0 → QQQ=**$16,597** SPY=**$31,413** (修复了重复数据)
- Indices: price=0 → S&P 500=**$7,165.08** (+0.8%)
- System: "unknown" → **"running"** + IBKR 已连接
- Social: import error → **正常**

**PnL/Dashboard 深层修复**
- 兜底条件改为: IBKR 在线但 get_account_summary 失败时也走持仓计算
- Dashboard assets.clear() 防止空值和真实值重复

**CookieCloud 修复**
- 根因: 服务器 127.0.0.1:8088 离线 + 无退避策略
- 修复: 指数退避 300→600→1200→1800秒

**腾讯云微信部署**
- 编号命令: 3位数字→转发 Mac 后端 API (通过反向隧道 28790)
- 对话记忆: 10条/用户, 30分钟 TTL
- 帮助消息: 编号快查表
- SESSION_PAUSE_S: 3600→60 秒

**其他**
- Tauri 桌面通知接入
- 微信本地端对话记忆

### 未完成的工作
- iLink session 过期: 需要在微信端重新发起与 bot 的会话
- Chrome V8 128MB 实测: 下次社交浏览器启动后观察
- CookieCloud 服务器启动: 127.0.0.1:8088 仍离线

### 需要注意的坑
- Python 后端改代码后需重启 clawbot (pkill -f multi_main && nohup .venv312/bin/python multi_main.py &)
- 腾讯云微信接收器: `/opt/openclaw-wechat/wechat_receiver.py`
- 反向隧道: autossh 本地 18790 → 云端 28790 (自动保活)
- Dashboard chart_data 为空 — 需有交易历史才有净值曲线

### 当前系统状态
- 后端: ✅ 运行中, 所有修复已生效
- 微信: ✅ 已部署新代码, iLink session 待恢复
- 测试: 1486 passed, 0 failed
- 磁盘: 3.9 GB
- 远程: 已同步

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

# HEALTH — 系统健康状态

> 最后更新: 2026-04-28 (PM)

---

## 当前系统状态: 🟡 仓库已清理, 待外部密钥轮换

| 指标 | 值 |
|------|------|
| 后端进程 | ✅ 运行中 (PID 自动重启) |
| 7 Bot 在线 | ✅ 7/7 |
| IBKR | ✅ 已连接 (DUP113460) |
| API 池 | ✅ 139/142 活跃源 |
| 闲鱼客服 | ✅ 自动回复活跃 |
| 社媒自动驾驶 | ✅ 运行中 |
| 测试 | ✅ 1486 passed, 0 failed |
| 微信命令 | ✅ 27/27 可用 (25✅ 2⚠️数据空) |
| Ollama 内存 | ✅ 151MB (原9.3GB) |
| 日志目录 | ✅ 784KB (已清理本地日志) |
| 公开仓库安全 | 🟡 Git 历史已重写并通过本地扫描, 仍需轮换曾暴露过的外部密钥 |

---

## 已知问题

### 🔴 阻塞 / 🟠 重要

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-817 | SECURITY | 公开 Git 历史曾提交 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json` 和数据库文件；已重写历史并通过本地 gitleaks/trufflehog 扫描 | 2026-04-28 | 🟠 待轮换密钥 + force-push 后复扫 |
| HI-818 | SECURITY | 本机 ignored `.env` 与浏览器 profile 日志含真实 API token；已确认未进入当前跟踪文件, 但涉及 token 应按泄露预案轮换 | 2026-04-28 | 🟠 待轮换 |

### 🟡 一般

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-802 | BUG | /monitor/news 首次调用可能超时 (RSS 20源+AI摘要) — 缓存热后正常 | 2026-04-26 | 🟡 已知 |
| HI-804 | BUG | G4F 服务 uptime 显示 0m — 进程检测关键词可能不匹配 | 2026-04-26 | 🟡 低优先 |
| HI-812 | BUG | 微信 iLink bot token 在平台侧失效(errcode=-14)，需在 iLink 后台重新扫码获取新 token | 2026-04-26 | 🟠 待操作 |

### 已修复 (本轮)

| ID | 分类 | 描述 | 修复日期 |
|----|------|------|----------|
| HI-805 | BUG | 金融指数全零 — yfinance Tickers 批量请求失败无错误提示 | 2026-04-26 |
| HI-806 | BUG | IBKR accountSummary "event loop already running" — 同步调异步 | 2026-04-26 |
| HI-807 | BUG | /monitor/extended 超时 54s+ — 外部API串行+重复RSS拉取 | 2026-04-26 |
| HI-808 | PERF | 日志文件每10秒生成一个,累积1800+文件168MB — loguru配置错误 | 2026-04-26 |
| HI-809 | UX | 微信欢迎消息不完整,只展示8个命令 | 2026-04-26 |
| HI-810 | BUG | 微信 cmd_iorders(233) 映射错误端点 | 2026-04-26 |
| HI-811 | BUG | 微信 cmd_dashboard 不可达(无编号映射) | 2026-04-26 |
| HI-813 | BUG | cmd_status(102) 映射路径错误(/system/status→/status) | 2026-04-26 |
| HI-814 | UX | 12个有API的微信命令未映射,走LLM兜底(300/407/500等) | 2026-04-26 |
| HI-815 | UX | 热点话题(300)只显示"[10项]",全球情报(407)嵌套dict未展开 | 2026-04-26 |
| HI-801 | PERF | Ollama 模型启动后常驻内存 9.1GB — 已配置 KEEP_ALIVE=5m 自动卸载 | 2026-04-26 |
| HI-803 | TECH_DEBT | 微信命令路由同步到腾讯云 wechat_receiver.py | 2026-04-26 |
| HI-816 | INFRA | 创建 Makefile + BUILD_GUIDE.md 构建规范化 | 2026-04-27 |
| HI-819 | INFRA | Git 密钥扫描 + 本地冗余清理：移除可重建缓存约4.4GB、删除含 token 痕迹的浏览器临时日志、补充忽略规则 | 2026-04-28 |
| HI-820 | SECURITY | Git 全历史重写完成：移除敏感历史路径、数据库/依赖/构建产物、扫描器样例噪音；清理后 gitleaks/trufflehog 历史扫描 0 命中 | 2026-04-28 |

---

## 技术债

| ID | 分类 | 描述 | 优先级 |
|----|------|------|--------|
| TD-001 | TECH_DEBT | CookieCloud 服务器 127.0.0.1:8088 离线 | 🟡 |
| TD-002 | ARCH_LIMIT | 部分微信编号命令(~25个)无真实API,走LLM通用回复 | 🟡 |
| TD-003 | TECH_DEBT | CLICommandsMixin (/cli) 预备代码未注册 | 🔵 |

# HANDOFF — 会话交接摘要

> 最后更新: 2026-04-23

---

## [2026-04-23] R9-R12: 性能加速 + 日报补全 + 三端体验对齐

### 本次完成了什么

**R9: LLM 响应加速**
- 路由策略从 simple-shuffle 改为 latency-based-routing（自动选最快源）
- 超时压缩: SiliconFlow 45→25s, Sambanova 90→30s, g4f 90→30s
- 重试减半: retry_after 5→2s, num_retries 3→2
- 投票系统: timeout 120→45s, stagger 0.5→0.1s, batch 顺序→并行(最多3)
- 冷却加强: cooldown_time 30→60s

**R10: 日报体验补全**
- 手动 /brief 同步推送微信
- WeChat 推送失败从 DEBUG 升为 WARNING
- 日报建议 LLM 失败时生成降级模板

**R11: 交易周期加速**
- Master Analysts 顺序→全并行 (asyncio.gather)
- 投票候选 10→5（减少 50% LLM 调用）
- yfinance 跳过 ticker.info（省 50-150 次 HTTP 请求）

**R12: 三端体验对齐**
- _notify_private_telegram 新增微信镜像（晨报/周报/闲鱼/预算等 8 个定时推送）
- _send_proactive 新增微信镜像（异动/交易跟踪/订单等 9 个事件通知）
- 微信端新增 7 个核心指令（日报/状态/持仓/行情/性能/闲鱼/帮助）

### 未完成的工作
- 微信命令路由需要同步到腾讯云 wechat_receiver.py（本地已改好，云端需部署）
- LLM 延迟指标需要等几个小时积累数据后验证（刚重启，perf 计数器已清零）
- 桌面端还没有系统级推送通知（Tauri notification API 未接入）
- 微信 AI 对话没有记忆/上下文（每条消息独立处理）

### 需要注意的坑
- 后端已重启，R9/R10/R11 配置已生效
- 微信接收器在腾讯云 101.43.41.96 上运行，需要 rsync 或 scp 部署新代码
- `openclaw-gateway` 进程不能和 `wechat_receiver` 同时运行

### 当前系统状态
- 后端: 运行中 (7 Bot 在线)
- 闲鱼: 在线 (自动回复活跃)
- 微信: 云端运行中（腾讯云，需部署新代码才能用指令）
- 测试: 1486 passed, 0 failed

---

**微信 Bot 云端独立运行**
- `wechat_receiver.py` 部署到腾讯云 101.43.41.96 (systemd 守护)
- iLink getUpdates 长轮询接收消息 → SiliconFlow Qwen2.5-7B 直接回复
- Mac 关机不影响微信 Bot 运行
- `wechat_bridge.py` 凭证路径修复（HOME 目录优先）
- 本地 `openclaw-gateway` 停掉消除消费者竞争

**黑五折扣搜集模块**
- `deal_scanner.py` 复用现有 SMZDM 爬取，6 大品类 30+ 关键词主动扫描
- 折扣率智能提取（降XX% / X折 / 满减），只推送 30%+ 降价
- 24h 去重 + Telegram/微信双渠道推送
- `/deals` Bot 命令 + 每 4 小时定时任务

**社媒人设资源生成**
- gpt-image-2 生成 5 张场景图（基准头像/AI工作台/健身房/咖啡馆/科技演讲）
- 人物基准描述锁定（后续换场景不换脸）
- `data/social_personas/zhou-yuheng.json` 人设配置
- 社媒 workflow 跑通验证（morning_scan + evening_produce）

**首页崩溃修复 (React Error #310)**
- loading 守卫早返回违反 hooks 规则 → 改为内联条件渲染

**Cookie 同步中心**
- CookieCloud 扩展支持 X/XHS 域名提取
- `GET /api/v1/cookies/status` + `POST /api/v1/cookies/sync-all`
- Settings 页面 Cookie 同步中心 UI

**Telegram Bot "忙" 修复**
- LLM 缓存数据库表结构损坏 (diskcache 版本不兼容)
- g4f 回复广告过滤 (`_strip_g4f_ads`)
- 后端重启后 7 Bot 全部正常回复

**后端 API 字段补全 (HI-751~756)**
- `/status` xianyu 子对象补 auto_reply_active/cookie_ok/conversations_today
- `/perf` 补 today_messages/active_users
- `/system/services` 补 uptime_seconds + 人类可读 uptime
- `/pool/stats` 补 today_cost/week_cost/month_cost/budget
- `/social/status` 超时保护

**前端 72+ UX 问题修复**
- i18n 全覆盖 (1830+ key，zh-CN/en-US 对齐)
- 10 个数据矛盾修复 (Dashboard/APIGateway/Xianyu/Bots/ControlCenter)
- 5 处错误反馈补全 (Scheduler/Logs/Evolution)
- 52 处硬编码中文接入 t()
- 新闻点击打开链接 + 中文分类标签
- 服务停止按钮竖排修复
- 闲鱼自动回复状态修复
- IBKR 登录后刷新
- Settings 网络状态真实化
- 性能内存单位 MB→GB 修复

**文件清理**
- 旧日志清理 (138MB → 21MB)
- 浏览器缓存清理 (190MB → 78MB)
- __pycache__ 清理 (~10MB)

### 未完成的工作
- 小红书 Cookie 需要手动登录（CookieCloud 需先安装插件）
- 微信消息接收偶尔有延迟（iLink 长轮询机制限制）
- Performance 页面吞吐量图表需后端新增数据采集
- 社媒自动发布需要 XHS Cookie 登录（当前已失效）

### 需要注意的坑
- `openclaw-gateway` 进程不能和 `wechat_receiver` 同时运行（同一 token 只能一个消费者）
- g4f 免费池响应慢 (30-90s)，优先用 SiliconFlow/Groq
- 构建桌面端必须走 `make tauri-build`（会自动清理旧版本）
- LLM 缓存数据库如果报 `no such column: expire`，直接删除 `data/llm_cache/` 重启

### 当前系统状态
- 后端: 运行中 (7 Bot 在线，279/282 API 源)
- 闲鱼: 在线 (CookieCloud 自动同步)
- 微信: 云端运行中 (腾讯云 101.43.41.96)
- 社交媒体: Chrome 浏览器运行中
- IBKR: 已连接
- 桌面端: `/Applications/OpenClaw.app` 最新版
- 测试: 1486 passed, 0 failed
- 闲鱼 Cookie 需要用户扫码（CookieCloud 或 App 内二维码）
- NewAPI 需要通过 http://localhost:3000 管理界面配置频道
- IBKR 需要用户启动 IB Gateway 才能显示交易数据
- WorldMonitor 三张卡（基础设施/气候/网安）暂无数据源
- gpt_free 有 1 个模型 inactive（自愈机制，重启可恢复）

### 需要注意的坑
- 双控制面问题：Dashboard 用 Python API，Sidebar 用 Tauri IPC，两套独立
- iFlow 无限 key 7天需续期
- CookieCloud 同步 11 次失败 — 需要在浏览器登录闲鱼

### 当前系统状态
- 后端：7 Bot 全在线，124/125 API 源活跃
- 前端：TypeScript 编译通过，生产构建成功
- 数据库：Redis / MongoDB / MySQL / Ollama 全在线

---


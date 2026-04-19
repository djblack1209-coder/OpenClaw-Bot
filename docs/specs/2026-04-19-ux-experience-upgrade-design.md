# 产品体验升级设计文档：从"能跑通"到"用的爽"

> 日期: 2026-04-19
> 领域: `frontend` + `backend` + `infra`
> 状态: 设计阶段

---

## 1. 背景与动机

当前系统功能完备（7 个 Telegram Bot + 闲鱼客服 + 社交自动化 + 交易系统 + macOS 桌面应用），
但用户体验存在以下痛点：

| 痛点 | 严重度 | 描述 |
|------|--------|------|
| 闲鱼 Cookie 过期骚扰 | 🔴 每日困扰 | Cookie 过期后 Telegram 疯狂发通知，需要手动扫码 |
| 无法远程开发 | 🟠 功能缺失 | 人在外面无法指挥家里电脑上的 AI 写代码 |
| 服务管理分散 | 🟠 操作复杂 | 启停机器人需要命令行，GUI 面板入口隐藏在开发者模式 |
| 数据可视化粗糙 | 🟡 体验不佳 | 图表缺乏动画、实时更新、精细设计 |
| Telegram 命令复杂 | 🟡 上手困难 | 92 个命令，没有可视化菜单 |

**目标**：让用户（非技术人员）在 macOS GUI 上一键控制所有功能，在 Telegram 上像点菜一样操作。

---

## 2. 设计原则

1. **零命令行** — 所有操作都有 GUI 按钮或 Telegram 内联键盘
2. **静默优先** — 能自动处理的不发通知，只在需要人工干预时打扰
3. **搬运优先** — 优先集成成熟开源方案，不重复造轮子
4. **渐进增强** — 每个场景独立可用，不互相依赖

---

## 3. 四大场景设计

### 3.1 P0：闲鱼 Cookie 静默续期（CookieCloud 集成）

#### 3.1.1 问题分析

当前流程：
```
Cookie 过期 → 后端检测 → Telegram 发通知 → 用户看到通知 → 打开 GUI 扫码
→ 或在 Telegram 中扫码 → Cookie 更新 → 平静 10-24 小时 → 再次过期
```

目标流程：
```
Cookie 即将过期 → CookieCloud 自动同步浏览器最新 Cookie → 后端热重载 → 用户无感
```

#### 3.1.2 技术方案

**搬运项目**：[CookieCloud](https://github.com/easychen/CookieCloud)（2958 星）

**架构**：
```
Chrome 浏览器 (CookieCloud 插件)
    ↓ 每 10 分钟自动同步
CookieCloud Server (本地 Docker/Node.js, 端口 8088)
    ↓ 端对端加密存储
ClawBot 定时任务 (每 5 分钟拉取)
    ↓ 解密 + 提取闲鱼域名 Cookie
config/.env (XIANYU_COOKIES 更新)
    ↓ SIGUSR1 信号
闲鱼 xianyu_live.py (热重载 Cookie, 无需重启)
```

**需要新增的组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| CookieCloud 集成模块 | `src/xianyu/cookie_cloud.py` | 从 CookieCloud API 拉取 + 解密 Cookie |
| 定时同步任务 | `multi_main.py` 中注册 | APScheduler 每 5 分钟执行 |
| GUI Cookie 状态面板 | `Bots/index.tsx` 中增强 | 显示 Cookie 来源、有效期、同步状态 |
| CookieCloud 配置 API | `routers/xianyu.py` 新增 | 设置 CookieCloud 服务端地址和密钥 |

**通知策略调整**：
- Cookie 自动续期成功 → 不通知（静默）
- CookieCloud 同步失败（浏览器关了） → 等待 30 分钟后发**一条**温和通知
- 连续 2 小时无法续期 → 发通知"需要扫码"（附 QR 码）
- 深夜(23:00-07:00) → 不发任何通知，攒到早上一条汇总

**GUI 面板设计**：
```
┌─ 闲鱼 Cookie 管理 ─────────────────────────────┐
│                                                  │
│  状态: 🟢 有效 (剩余 ~4.2 小时)                   │
│  来源: CookieCloud 自动同步                       │
│  上次更新: 2 分钟前                                │
│  同步模式: [☑ 自动] [☐ 手动扫码]                   │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ 🔄 立即同步   │  │ 📱 手动扫码   │              │
│  └──────────────┘  └──────────────┘              │
│                                                  │
│  同步记录:                                        │
│  09:15 ✅ 自动同步成功                             │
│  09:10 ✅ 自动同步成功                             │
│  09:05 ⚠️ 同步失败(浏览器离线), 使用缓存            │
└──────────────────────────────────────────────────┘
```

#### 3.1.3 实施步骤

1. 安装 CookieCloud Server（Docker 一行命令）
2. Chrome 安装 CookieCloud 插件并配置
3. 新建 `src/xianyu/cookie_cloud.py` — 集成 CookieCloud API
4. 修改 `cookie_refresher.py` — 增加 CookieCloud 作为主要 Cookie 来源
5. 修改通知策略 — 实现静默模式
6. GUI 增加 CookieCloud 配置入口（服务端地址 + 密钥）
7. 测试：停止手动扫码 48 小时，验证自动续期

---

### 3.2 P1：手机远程指挥 AI 写代码

#### 3.2.1 问题分析

用户场景：
- 人在外面，想到一个需求，想让家里电脑的 AI 马上开始做
- 不想等回家再操作
- 想在手机上看到 AI 正在做什么（截图/进度）

#### 3.2.2 技术方案

**搬运项目**：[claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram)（2458 星，Python）

**架构**：
```
手机 Telegram
    ↓ /dev "把首页按钮改蓝色"
ClawBot Telegram Bot (现有)
    ↓ 转发到开发会话管理器
DevSessionManager (新增)
    ↓ 启动 Claude Code CLI
claude-code --print --dangerously-skip-permissions
    ↓ 输出流
DevSessionManager (捕获输出 + 截图)
    ↓ 格式化发送
手机 Telegram (收到结果/截图/diff)
```

**核心模块**：

| 模块 | 位置 | 说明 |
|------|------|------|
| DevSessionManager | `src/dev/session_manager.py` | 管理开发会话生命周期 |
| ClaudeCodeBridge | `src/dev/claude_bridge.py` | 封装 Claude Code CLI 调用 |
| DevCommandsMixin | `src/telegram/mixins/dev_commands.py` | Telegram /dev 命令 |
| Dev 状态 API | `src/api/routers/dev.py` | GUI 面板数据源 |

**Telegram 命令设计**：
```
/dev start [项目路径]    → 开始远程开发会话
/dev "需求描述"          → 发送需求给 Claude Code
/dev screenshot          → 截图当前 IDE/终端状态
/dev diff                → 查看当前改动
/dev status              → 查看执行状态
/dev approve             → 批准 Claude Code 的操作
/dev stop                → 结束开发会话
```

**安全设计**：
- 只允许白名单 Telegram 用户 ID 使用 /dev
- 每次会话开始需要确认项目目录
- 危险操作（删文件、修改配置）需要手动审批
- 会话 30 分钟无活动自动结束

**GUI 面板设计**：
```
┌─ 远程开发控制台 ──────────────────────────────────┐
│                                                    │
│  会话状态: 🟢 活跃 (由 Telegram @your_username)     │
│  项目: /Users/.../OpenEverything                    │
│  已运行: 12 分钟                                    │
│                                                    │
│  ┌─ 实时输出 ────────────────────────────────────┐  │
│  │ > 正在修改 src/components/Home/index.tsx...   │  │
│  │ > 已更新按钮颜色从 #3B82F6 → #2563EB          │  │
│  │ > 运行 TypeScript 编译检查...                  │  │
│  │ > ✅ 编译通过，无错误                           │  │
│  └────────────────────────────────────────────────┘  │
│                                                    │
│  [⏸ 暂停] [⏹ 终止] [📸 截图] [📋 查看 Diff]        │
└────────────────────────────────────────────────────┘
```

#### 3.2.3 实施步骤

1. Fork claude-code-telegram，提取核心逻辑
2. 新建 `src/dev/` 目录，实现 DevSessionManager + ClaudeCodeBridge
3. 新增 DevCommandsMixin，注册 /dev 系列命令
4. 新增 FastAPI 路由 `/api/v1/dev/`
5. GUI 新增"远程开发控制台"页面
6. 测试：从 Telegram 发送 3 个不同类型的开发需求

---

### 3.3 P2：服务启停面板化

#### 3.3.1 问题分析

当前状态：
- GUI 的 B 端（开发者模式）已有服务管理功能
- 但需要三击版本号才能解锁
- C 端（普通模式）看不到服务控制
- Telegram 端有 /xianyu start/stop 但没有可视化菜单

#### 3.3.2 技术方案

**GUI 改造**（不引入新依赖，改造现有代码）：

**C 端首页改造** — 在 Home 页面增加"我的机器人"卡片区：
```
┌─ 我的机器人 ──────────────────────────────────────┐
│                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 🐟 闲鱼   │  │ 📱 社交   │  │ 📈 交易   │          │
│  │ 客服机器人 │  │ 自动发帖  │  │ 自动交易  │          │
│  │           │  │           │  │           │          │
│  │  🟢 运行中 │  │  🔴 已停止 │  │  🟡 待连接 │          │
│  │           │  │           │  │           │          │
│  │ [关闭 🔘] │  │ [开启 🔘] │  │ [开启 🔘] │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 🤖 AI 助手│  │ 🎫 领券   │  │ 🔔 心跳   │          │
│  │ 7 Bot 集群│  │ 自动领券  │  │ 保活监控  │          │
│  │           │  │           │  │           │          │
│  │  🟢 7/7   │  │  🔴 已停止 │  │  🟢 运行中 │          │
│  │           │  │           │  │           │          │
│  │ [管理 →]  │  │ [开启 🔘] │  │ [详情 →]  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
└────────────────────────────────────────────────────┘
```

**Telegram 内联键盘** — /menu 命令显示可视化菜单：
```
╔══════════════════════════╗
║    🦞 OpenClaw 控制台     ║
╠══════════════════════════╣
║                          ║
║  [🐟 闲鱼管理]  [📈 投资]  ║
║  [📱 社交发帖]  [🤖 AI]   ║
║  [📊 数据报表]  [⚙️ 设置]  ║
║                          ║
║  [🔧 服务状态]  [🆘 帮助]  ║
╚══════════════════════════╝
```

点击"闲鱼管理"后展开子菜单：
```
╔══════════════════════════╗
║     🐟 闲鱼管理           ║
╠══════════════════════════╣
║                          ║
║  状态: 🟢 在线 | 今日: 23 条║
║                          ║
║  [📱 扫码登录]             ║
║  [🔄 刷新 Cookie]          ║
║  [📊 今日报表]             ║
║  [⏸ 暂停服务] [▶ 继续]     ║
║                          ║
║  [← 返回主菜单]            ║
╚══════════════════════════╝
```

#### 3.3.3 实施步骤

1. Home 页面增加"我的机器人"卡片区组件
2. 实现服务开关联动 FastAPI `/api/v1/controls/` 接口
3. Telegram 新增 /menu 命令 + InlineKeyboardMarkup 菜单系统
4. 实现 CallbackQueryHandler 处理菜单点击事件
5. 测试：从 GUI 和 Telegram 分别启停各服务

---

### 3.4 P3：数据可视化升级

#### 3.4.1 技术方案

**已有基础设施**：Recharts 3.8 + framer-motion 11.18 + shadcn/ui

**参考项目**：
- [Neuberg](https://github.com/KoNananachan/Neuberg) — Bloomberg 风格交易面板
- shadcn/ui Charts — 官方图表组件

**升级内容**：

| 页面 | 当前状态 | 升级目标 |
|------|---------|---------|
| Home 首页 | 数字卡片 + 简单列表 | 实时动画仪表盘 + 趋势迷你图 |
| Portfolio 投资 | 基础持仓表格 | 交互式收益曲线 + 持仓饼图 + K 线缩略图 |
| Bots 机器人 | 文字状态 | 实时消息流 + 响应时间图表 + 日活跃图 |
| 闲鱼面板 | 基础统计 | 销售趋势图 + 会话热力图 + 收入日历 |

**实时数据推送**：
- WebSocket 连接 FastAPI `/ws/dashboard` 端点
- 每 5 秒推送核心指标更新
- framer-motion 动画实现数据过渡效果

#### 3.4.2 实施步骤

1. Home 首页增加实时统计卡片（API 调用量、今日收入、Bot 消息数）
2. Portfolio 页面用 Recharts 替换静态表格
3. Bots 页面增加实时消息流面板
4. 闲鱼面板增加销售数据图表
5. 全局增加 WebSocket 实时数据推送

---

## 4. 执行计划

### 第一期（P0 + 基础修复）— 预计 3 天

| 任务 | 预计时间 | 依赖 |
|------|---------|------|
| Rust 旧路径修复 + 桌面应用重编译 | 0.5 天 | 无 |
| CookieCloud Server 部署 + 插件配置 | 0.5 天 | 无 |
| cookie_cloud.py 集成模块开发 | 1 天 | CookieCloud 部署 |
| 通知策略改造（静默模式） | 0.5 天 | cookie_cloud.py |
| GUI Cookie 管理面板增强 | 0.5 天 | cookie_cloud.py |

### 第二期（P1）— 预计 5 天

| 任务 | 预计时间 | 依赖 |
|------|---------|------|
| claude-code-telegram Fork + 核心提取 | 1 天 | 无 |
| DevSessionManager + ClaudeCodeBridge | 2 天 | Fork |
| Telegram /dev 命令系列 | 1 天 | SessionManager |
| GUI 远程开发控制台页面 | 1 天 | API 就绪 |

### 第三期（P2 + P3 起步）— 预计 4 天

| 任务 | 预计时间 | 依赖 |
|------|---------|------|
| C 端首页"我的机器人"卡片 | 1 天 | 无 |
| Telegram /menu 内联键盘系统 | 1.5 天 | 无 |
| 首页实时数据仪表盘 | 1 天 | WebSocket |
| 投资组合图表升级 | 0.5 天 | 无 |

---

## 5. 技术风险

| 风险 | 缓解措施 |
|------|---------|
| CookieCloud 插件可能影响浏览器性能 | 设置同步间隔 ≥ 10 分钟 |
| Claude Code CLI 版本更新导致接口变化 | 抽象 Bridge 层，版本适配 |
| Tauri 重编译可能耗时较长 | 提前配置 Rust 工具链 |
| WebSocket 连接稳定性 | 自动重连 + 心跳检测（已有） |

---

## 6. 验收标准

### P0 验收
- [ ] 闲鱼 Cookie 48 小时内不发过期通知（CookieCloud 工作中）
- [ ] GUI 显示 Cookie 状态和同步记录
- [ ] CookieCloud 失效后 30 分钟内自动降级到扫码模式

### P1 验收
- [ ] 从 Telegram 发送 /dev "需求描述"，Claude Code 在电脑上执行
- [ ] 执行完成后收到结果截图和 diff
- [ ] GUI 显示远程开发会话实时状态

### P2 验收
- [ ] C 端首页可以看到所有机器人状态并启停
- [ ] Telegram /menu 显示内联键盘菜单，支持子菜单导航

### P3 验收
- [ ] 首页有实时动画数据卡片
- [ ] 投资组合有交互式图表

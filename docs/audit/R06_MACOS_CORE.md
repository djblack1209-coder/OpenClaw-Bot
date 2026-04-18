# R06 macOS 核心页面审计

> **轮次**: R6 | **状态**: 待执行 | **预估条目**: ~45
> **审计角色**: CPO + Design Lead + QA Lead
> **前置条件**: R5 完成
> **验证方式**: Playwright 截图 + 浏览器控制台零错误 + 点击每个按钮

---

## 6.1 首页仪表盘 HomeDashboard（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.01 | Mock | `components/Home/` | 是否存在硬编码假数据（对照后端 /api/v1/system/status） | 搜索硬编码数组/对象 | ⬜ |
| R6.02 | UX | `components/Home/` | 首页加载状态：skeleton/spinner 是否存在 | 截图验证 | ⬜ |
| R6.03 | UX | `components/Home/` | 后端不可达时的降级展示 | 断开后端测试 | ⬜ |
| R6.04 | UX | `components/Home/` | 所有卡片/按钮是否可点击且有响应 | 逐一点击测试 | ⬜ |
| R6.05 | 设计 | `components/Home/` | 数据刷新机制：轮询/WebSocket/手动 | 检查数据获取逻辑 | ⬜ |
| R6.06 | Mock | `components/Dashboard/AssetDistribution.tsx` | **MOCK-01**: 硬编码假资产分布数据 | 替换为 API 调用 | ⬜ |
| R6.07 | Mock | `components/Dashboard/RecentActivity.tsx` | **MOCK-02**: 全假活动列表 | 替换为 API 调用 | ⬜ |
| R6.08 | UX | `components/Dashboard/` | 图表组件(recharts)渲染是否正常 | 截图验证 | ⬜ |

## 6.2 AI 助手 Assistant（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.09 | UX | `components/Assistant/` | 4 种模式切换是否流畅 | 逐一切换测试 | ⬜ |
| R6.10 | UX | `components/Assistant/` | 消息发送→SSE 流式响应→渲染 全链路 | 发送消息测试 | ⬜ |
| R6.11 | UX | `components/Assistant/` | 会话管理：新建/切换/删除/重命名 | 逐一操作测试 | ⬜ |
| R6.12 | UX | `components/Assistant/` | 消息列表滚动：自动滚到底部/手动滚动不跳 | 交互测试 | ⬜ |
| R6.13 | UX | `components/Assistant/` | Markdown 渲染：代码块/列表/链接/图片 | 发送含 MD 的消息测试 | ⬜ |
| R6.14 | UX | `components/Assistant/` | 输入框：回车发送/Shift+Enter 换行/空消息防护 | 键盘测试 | ⬜ |
| R6.15 | 设计 | `src/services/conversationService.ts` | API 调用是否正确使用 clawbotFetch | 检查请求封装 | ⬜ |
| R6.16 | UX | `components/Assistant/` | 错误状态：API 超时/网络断开的用户提示 | 模拟错误测试 | ⬜ |

## 6.3 Bot 管理 Bots（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.17 | UX | `components/Bots/` | 7 个 Bot 卡片展示：状态/模型/命令数 | 截图验证 | ⬜ |
| R6.18 | UX | `components/Bots/` | Bot 启停控制是否可用 | 点击测试 | ⬜ |
| R6.19 | UX | `components/Bots/` | Bot 详情页：配置/日志/统计 | 点击进入详情 | ⬜ |
| R6.20 | Mock | `components/Bots/` | 是否有硬编码的 Bot 信息 | 搜索硬编码 | ⬜ |
| R6.21 | UX | `components/Bots/` | 空状态（无 Bot 时）的展示 | 检查空状态组件 | ⬜ |

## 6.4 设置 Settings（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.22 | UX | `components/Settings/` | 设置项列表：API Key/通知/显示/语言等 | 截图验证 | ⬜ |
| R6.23 | UX | `components/Settings/` | 未保存变更离开时的警告对话框 | 模拟操作测试 | ⬜ |
| R6.24 | UX | `components/Settings/` | 保存按钮状态：loading/success/error 反馈 | 点击保存测试 | ⬜ |
| R6.25 | 安全 | `components/Settings/` | API Key 输入框是否 type=password 或遮罩 | 检查输入组件 | ⬜ |
| R6.26 | 设计 | `components/Settings/` | 设置持久化到何处（Tauri store/后端/localStorage） | 跟踪存储逻辑 | ⬜ |

## 6.5 控制中心 ControlCenter（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.27 | UX | `components/ControlCenter/` | 8 个子组件是否全部渲染正常 | 截图验证 | ⬜ |
| R6.28 | UX | `components/ControlCenter/` | 交易控制开关：启停/参数调整 | 点击测试 | ⬜ |
| R6.29 | UX | `components/ControlCenter/` | 社媒控制开关：autopilot/手动 | 点击测试 | ⬜ |
| R6.30 | UX | `components/ControlCenter/` | 调度器管理：任务列表/启停 | 交互测试 | ⬜ |
| R6.31 | UX | `components/ControlCenter/` | 全局设置：系统参数展示与修改 | 交互测试 | ⬜ |

## 6.6 通用 UI 质量（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.32 | UX | `components/Layout/` | 侧边栏导航：所有菜单项是否可点击/高亮正确 | 逐一点击 | ⬜ |
| R6.33 | UX | `components/CommandPalette.tsx` | 命令面板(Cmd+K)：搜索/执行是否可用 | 键盘触发测试 | ⬜ |
| R6.34 | UX | `components/ErrorBoundary.tsx` | 错误边界是否正确捕获并展示错误 | 模拟组件错误 | ⬜ |
| R6.35 | UX | `components/Onboarding/` | 新手引导流程：步骤/跳过/完成 | 模拟首次使用 | ⬜ |
| R6.36 | 设计 | `src/styles/` | 全局样式：是否有未使用的 CSS/样式冲突 | 检查样式文件 | ⬜ |
| R6.37 | UX | 全局 | 暗色/亮色模式下所有组件是否可读 | 切换主题截图 | ⬜ |

## 6.7 Channels 频道管理（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.38 | UX | `components/Channels/` | 频道列表 CRUD：新建/编辑/删除 | 逐一操作测试 | ⬜ |
| R6.39 | UX | `components/Channels/` | 空状态展示 | 检查零频道时 UI | ⬜ |
| R6.40 | UX | `components/Channels/` | 微信渠道配置面板 | 检查配置选项 | ⬜ |
| R6.41 | 设计 | `components/Channels/` | 频道状态同步（在线/离线/错误） | 检查状态更新 | ⬜ |

## 6.8 插件系统（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R6.42 | UX | `components/Plugins/` | 已安装插件列表展示 | 截图验证 | ⬜ |
| R6.43 | Mock | `components/Store/index.tsx` | **MOCK-06**: 静默降级无提示 | 添加用户可见提示 | ⬜ |
| R6.44 | UX | `components/Store/` | 插件商店：浏览/安装/卸载流程 | 交互测试 | ⬜ |
| R6.45 | UX | `components/Plugins/` | 插件启用/禁用开关 | 点击测试 | ⬜ |

---

## 执行检查清单

- [ ] 启动 Tauri dev server（或 Vite dev server）
- [ ] 每个页面截图存档
- [ ] 每个按钮至少点击一次
- [ ] 所有 Mock 数据标记并替换
- [ ] 浏览器控制台零错误
- [ ] 更新 CHANGELOG.md

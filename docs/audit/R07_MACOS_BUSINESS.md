# R07 macOS 业务页面审计

> **轮次**: R7 | **状态**: ✅ 已完成 | **条目**: 40 | **修复**: 6 | **技术债**: 20
> **审计角色**: CPO + Design Lead + QA Lead
> **前置条件**: R6 完成
> **验证方式**: TypeScript 零错误 + 源码审查

---

## 7.1 投资交易页面 Money/Portfolio（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.01 | UX | `components/Money/` | 交易面板整体布局与可用性 | 截图验证 | ⬜ |
| R7.02 | Mock | `components/Money/OrderBook.tsx` | **MOCK-03**: Mock 订单簿数据 | 替换为 API 或添加降级提示 | ⬜ |
| R7.03 | Mock | `components/Money/DepthChart.tsx` | **MOCK-04**: Mock 深度图数据 | 替换为 API 或添加降级提示 | ⬜ |
| R7.04 | UX | `components/Money/` | K线图(lightweight-charts)渲染 | 截图验证 | ⬜ |
| R7.05 | UX | `components/Portfolio/` | 持仓列表：实时盈亏/颜色标记 | 验证数据更新 | ⬜ |
| R7.06 | UX | `components/Portfolio/` | 投资组合概览：总资产/日盈亏/收益率 | 验证数据源 | ⬜ |
| R7.07 | UX | `components/Money/` | 交易按钮：买入/卖出/确认对话框 | 点击测试 | ⬜ |
| R7.08 | UX | `components/Money/` | 投票面板：AI 模型投票状态展示 | 验证数据更新 | ⬜ |

## 7.2 社媒管理 Social（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.09 | UX | `components/Social/` | 社媒面板：平台连接状态/发文历史 | 截图验证 | ⬜ |
| R7.10 | UX | `components/Social/` | 内容创作：编辑器/AI 生成/预览 | 交互测试 | ⬜ |
| R7.11 | UX | `components/Social/` | 分析仪表盘：互动数据/趋势图 | 验证数据源 | ⬜ |
| R7.12 | UX | `components/Social/` | Autopilot 控制面板：启停/配置 | 点击测试 | ⬜ |
| R7.13 | UX | `components/Social/` | 日历视图：排期/已发/待发 | 交互测试 | ⬜ |
| R7.14 | UX | `components/Social/` | 人设管理(Personas)：创建/编辑/切换 | 交互测试 | ⬜ |

## 7.3 记忆管理 Memory（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.15 | UX | `components/Memory/` | 记忆列表：搜索/筛选/分页 | 交互测试 | ⬜ |
| R7.16 | UX | `components/Memory/` | 记忆详情：查看/编辑/删除 | 逐一操作 | ⬜ |
| R7.17 | UX | `components/Memory/` | 记忆统计：总数/分类/使用频率 | 验证数据源 | ⬜ |
| R7.18 | UX | `components/Memory/` | 空状态（无记忆时）展示 | 检查 UI | ⬜ |

## 7.4 日志查看 Logs（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.19 | UX | `components/Logs/` | 实时日志流：WebSocket 推送 + 自动滚动 | 观察实时更新 | ⬜ |
| R7.20 | UX | `components/Logs/` | 日志级别筛选：Error/Warn/Info/Debug | 切换筛选器 | ⬜ |
| R7.21 | UX | `components/Logs/` | 日志搜索：关键词高亮 | 输入搜索词 | ⬜ |
| R7.22 | 安全 | `components/Logs/` | 日志中是否脱敏（API Key 等敏感信息） | 检查输出内容 | ⬜ |

## 7.5 开发者工具 Dev/DevPanel（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.23 | Mock | `components/DevPanel/index.tsx` | **MOCK-05**: TODO 未接入后端 API | 接入或标记 | ⬜ |
| R7.24 | UX | `components/Dev/` | 开发者页面：IPC 命令测试/资源仪表盘 | 交互测试 | ⬜ |
| R7.25 | UX | `components/DevPanel/` | 开发者工作台：环境信息/快速操作 | 截图验证 | ⬜ |
| R7.26 | UX | `components/Testing/` | 测试页面：功能是否可用 | 交互测试 | ⬜ |
| R7.27 | UX | `components/Dev/` | 资源仪表盘：CPU/内存/磁盘展示 | 验证数据源 | ⬜ |

## 7.6 进化引擎 Evolution（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.28 | UX | `components/Evolution/` | 自进化扫描结果展示 | 截图验证 | ⬜ |
| R7.29 | UX | `components/Evolution/` | 提案列表：查看/接受/拒绝 | 交互测试 | ⬜ |
| R7.30 | UX | `components/Evolution/` | 能力缺口分析展示 | 验证数据映射 | ⬜ |
| R7.31 | UX | `components/Evolution/` | 进化历史时间线 | 截图验证 | ⬜ |

## 7.7 AI 配置 / API 网关（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.32 | UX | `components/AIConfig/` | AI 模型配置界面：选择/参数调整 | 交互测试 | ⬜ |
| R7.33 | UX | `components/APIGateway/` | API 网关面板：状态/配置/诊断指南 | 截图验证 | ⬜ |
| R7.34 | UX | `components/APIGateway/` | 自定义确认框（替换 browser native） | 点击测试 | ⬜ |
| R7.35 | UX | `components/AIConfig/` | 模型切换后是否立即生效 | 验证状态同步 | ⬜ |
| R7.36 | UX | `components/APIGateway/` | NewAPI 渠道/Token CRUD | 交互测试 | ⬜ |

## 7.8 执行流/调度器（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R7.37 | UX | `components/ExecutionFlow/` | xyflow 节点可视化：拖拽/连线/缩放 | 交互测试 | ⬜ |
| R7.38 | UX | `components/ExecutionFlow/` | 流程执行状态：运行中/完成/失败 颜色标记 | 截图验证 | ⬜ |
| R7.39 | UX | `components/Scheduler/` | 定时任务列表：创建/编辑/删除/启停 | 交互测试 | ⬜ |
| R7.40 | UX | `components/Scheduler/` | 任务执行历史：时间/状态/日志 | 截图验证 | ⬜ |

---

## 执行检查清单

- [ ] 每个页面截图存档（亮色+暗色）
- [ ] 每个交互元素至少操作一次
- [ ] 所有 Mock 数据标记并替换/添加降级提示
- [ ] 控制台零错误（console.error）
- [ ] 数据从后端 API 获取而非硬编码
- [ ] 更新 CHANGELOG.md

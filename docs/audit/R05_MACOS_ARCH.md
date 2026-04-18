# R05 macOS 桌面端架构审计

> **轮次**: R5 | **状态**: 待执行 | **预估条目**: ~35
> **审计角色**: CTO + Staff Engineer + Design Lead
> **前置条件**: R4 完成
> **验证基线**: `cd apps/openclaw-manager-src && npx tsc --noEmit`

---

## 5.1 Tauri 2 配置与构建（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R5.01 | 配置 | `src-tauri/tauri.conf.json` | Bundle ID / 版本号 / 窗口配置 / CSP 策略 | 对照 Tauri 2 官方文档 | ⬜ |
| R5.02 | 安全 | `src-tauri/tauri.conf.json` | CSP 策略是否正确限制 connect-src 到 127.0.0.1:18790 | 检查 CSP 头 | ⬜ |
| R5.03 | 配置 | `src-tauri/tauri.conf.json` | DevTools 是否在生产构建中禁用 | 检查 `devtools` 字段 | ⬜ |
| R5.04 | 配置 | `src-tauri/Cargo.toml` | Rust 依赖版本：tauri/serde/tokio 等是否最新稳定版 | `cargo outdated` | ⬜ |
| R5.05 | 设计 | `src-tauri/capabilities/` | Tauri 2 capability 权限模型是否正确配置 | 对照 Tauri 2 权限文档 | ⬜ |
| R5.06 | 配置 | `vite.config.ts` | Vite 构建配置：是否正确设置 Tauri 专用选项 | 对照 Tauri + Vite 官方模板 | ⬜ |
| R5.07 | 配置 | `package.json` | scripts 字段：dev/build/tauri 命令是否正确 | 实际执行验证 | ⬜ |
| R5.08 | 设计 | 构建产物 | `npm run build` 是否成功产出 dist/ | 实际构建测试 | ⬜ |

## 5.2 Rust 后端（IPC 命令）（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R5.09 | 设计 | `src-tauri/src/main.rs` | Tauri 入口：plugin 注册/command 注册/窗口创建 | 读取代码 | ⬜ |
| R5.10 | 设计 | `src-tauri/src/commands/` | IPC 命令文件清单及各命令功能 | 列出所有 #[tauri::command] | ⬜ |
| R5.11 | 设计 | `src-tauri/src/commands/` | `check_environment` 命令：检查后端服务可达性 | 跟踪实现 | ⬜ |
| R5.12 | 设计 | `src-tauri/src/commands/` | `get_service_status` 命令：3秒轮询后端状态 | 跟踪实现 | ⬜ |
| R5.13 | 安全 | `src-tauri/src/commands/` | Shell 命令执行权限：是否收窄到最小范围 | 检查 shell 权限配置 | ⬜ |
| R5.14 | 设计 | `src-tauri/src/commands/` | 错误处理：Rust panic 是否被捕获并转为 JS 错误 | 检查 Result 返回 | ⬜ |
| R5.15 | 设计 | `src-tauri/src/models/` | 数据模型定义是否与前端 TS 类型一致 | 对比 Rust struct 和 TS interface | ⬜ |
| R5.16 | 设计 | `src-tauri/src/utils/` | 工具函数：HTTP 客户端/日志/配置读取 | 检查实现质量 | ⬜ |

## 5.3 前端架构（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R5.17 | 设计 | `src/App.tsx` | 22 页面的路由/懒加载/错误边界 | 检查 React.lazy + Suspense | ⬜ |
| R5.18 | 设计 | `src/stores/` | Zustand store 文件清单及状态管理模式 | 列出所有 store | ⬜ |
| R5.19 | 设计 | `src/hooks/` | 自定义 hooks 清单及复用情况 | 列出所有 hooks | ⬜ |
| R5.20 | 设计 | `src/lib/tauri.ts` | `clawbotFetch` 封装：HTTP 请求统一处理 | 检查错误处理/超时/重试 | ⬜ |
| R5.21 | 设计 | `src/lib/logger.ts` | 前端日志系统 | 检查日志级别和输出 | ⬜ |
| R5.22 | 设计 | `src/services/` | API 服务层：是否所有后端调用都经过统一封装 | 检查服务文件 | ⬜ |
| R5.23 | 设计 | `src/components/shared/` | 共享组件库：按钮/卡片/对话框等 | 检查组件质量 | ⬜ |
| R5.24 | 设计 | `src/components/ui/` | shadcn/ui 组件：是否正确引入和使用 | 检查组件完整性 | ⬜ |

## 5.4 前后端通信（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R5.25 | 设计 | `src/lib/tauri.ts` | HTTP 请求 → 127.0.0.1:18790 → FastAPI 的完整链路 | 跟踪请求流 | ⬜ |
| R5.26 | 设计 | WebSocket | WS 连接 → ws://127.0.0.1:18790/api/v1/events | 检查连接管理 | ⬜ |
| R5.27 | 设计 | SSE | SSE 流（对话场景）→ ReadableStream 解析 | 检查流处理 | ⬜ |
| R5.28 | UX | 通信层 | 后端不可达时的用户提示 | 检查错误 UI | ⬜ |
| R5.29 | 设计 | 通信层 | 请求超时设置是否合理 | 检查 timeout 配置 | ⬜ |
| R5.30 | 设计 | 通信层 | Token 认证头是否正确附加 | 检查请求拦截器 | ⬜ |

## 5.5 macOS 特有（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R5.31 | UX | macOS | 应用图标是否存在且清晰 | 检查 `src-tauri/icons/` | ⬜ |
| R5.32 | UX | macOS | 窗口拖拽区域（drag region）是否正确 | 检查 CSS data-tauri-drag-region | ⬜ |
| R5.33 | UX | macOS | 暗色/亮色模式切换是否跟随系统 | 检查 theme 逻辑 | ⬜ |
| R5.34 | 配置 | macOS | `tauri dev` 是否能正常启动开发环境 | 实际运行验证 | ⬜ |
| R5.35 | 配置 | macOS | `tauri build` 是否能产出 .dmg / .app | 实际构建验证 | ⬜ |

---

## 执行检查清单

- [ ] TypeScript 编译零错误
- [ ] Rust cargo check 零警告
- [ ] 前端 dev server 可启动
- [ ] 所有 IPC 命令有对应的前端调用
- [ ] 回归测试
- [ ] 更新 CHANGELOG.md

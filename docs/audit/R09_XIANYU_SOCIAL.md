# R09 闲鱼+社媒+微信+工具链审计

> **轮次**: R9 | **状态**: 待执行 | **预估条目**: ~35
> **审计角色**: CPO + Staff Engineer
> **前置条件**: R8 完成
> **验证基线**: `cd packages/clawbot && pytest tests/ -k "xianyu or social or wechat" --tb=short`

---

## 9.1 闲鱼系统深度审计（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.01 | 设计 | `src/xianyu/` | 闲鱼 WebSocket 客户端：连接/心跳/重连/熔断 全链路 | 跟踪代码路径 | ⬜ |
| R9.02 | 安全 | `src/xianyu/` | Cookie 存储安全：是否加密存储、过期清理 | 检查存储机制 | ⬜ |
| R9.03 | 设计 | `src/xianyu/` | 自动回复 AI 提示词：是否防注入、是否暴露底价 | 审查 prompt 模板 | ⬜ |
| R9.04 | UX | `src/xianyu/` | 商品管理：上架/下架/价格调整 | 检查 CRUD 逻辑 | ⬜ |
| R9.05 | 设计 | `src/xianyu/` | 时段分析 + 转化漏斗 + 排行榜 数据准确性 | 检查聚合算法 | ⬜ |
| R9.06 | UX | `src/xianyu/xianyu_admin.py` | 管理面板 10 个端点逐一验证 | curl 测试 | ⬜ |
| R9.07 | 安全 | `src/xianyu/` | 频率限制(10msg/min)是否可被绕过 | 检查限速器实现 | ⬜ |
| R9.08 | 设计 | `src/xianyu/` | 后台任务异常监控：Celery/asyncio 任务是否有异常回调 | 检查任务管理 | ⬜ |

## 9.2 社媒系统深度审计（7 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.09 | 设计 | `src/social/` | browser-use 浏览器实例管理：创建/复用/销毁/资源泄漏 | 检查生命周期 | ⬜ |
| R9.10 | 设计 | `src/social/` | crawl4ai 数据采集：目标平台/频率/反爬策略 | 检查采集配置 | ⬜ |
| R9.11 | UX | `src/social/` | 内容生成质量：AI 生成文案的模板/风格控制 | 审查 prompt 模板 | ⬜ |
| R9.12 | 设计 | `src/social/` | 多平台适配器：微博/Twitter/小红书 各自的 API 差异处理 | 检查适配器模式 | ⬜ |
| R9.13 | 设计 | `src/social/` | 互动数据存储(post_engagement)：Schema 完整性 | 检查数据库表结构 | ⬜ |
| R9.14 | UX | `src/social/` | 图片/视频处理：裁剪/压缩/水印 | 检查媒体管道 | ⬜ |
| R9.15 | 设计 | `src/social/` | 排期发布：定时任务准确性 | 检查调度器精度 | ⬜ |

## 9.3 微信 Bridge 审计（7 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.16 | 设计 | `src/wechat_bridge.py` | 一向推送逻辑：iLink API 调用是否正确 | 检查 API 调用 | ⬜ |
| R9.17 | 设计 | `.openclaw/extensions/openclaw-weixin/` | 微信插件架构：42 文件的模块组织 | 审查目录结构 | ⬜ |
| R9.18 | 设计 | `openclaw-weixin/src/channel.ts` | 双向消息：getUpdates long-poll + sendMessage | 检查通信逻辑 | ⬜ |
| R9.19 | 安全 | `openclaw-weixin/src/auth/` | QR 登录 + 账号管理的安全性 | 检查凭证存储 | ⬜ |
| R9.20 | 设计 | `openclaw-weixin/src/messaging/` | 消息处理管道：接收→处理→响应 | 跟踪流程 | ⬜ |
| R9.21 | 设计 | `openclaw-weixin/src/media/` | 媒体处理：silk 转码/图片解密/CDN 上传 | 检查编解码 | ⬜ |
| R9.22 | 设计 | `openclaw-weixin/src/monitor/` | 微信连接监控：断线检测/重连 | 检查监控逻辑 | ⬜ |

## 9.4 OMEGA 工具链（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.23 | 设计 | `src/omega/` 或等效 | Jina Read/Search 集成 | 检查 API 调用 | ⬜ |
| R9.24 | 设计 | `src/omega/` | AI 图片生成(fal.ai)集成 | 检查调用和回调 | ⬜ |
| R9.25 | 设计 | `src/omega/` | AI 视频生成(Kling)集成 | 检查调用和回调 | ⬜ |
| R9.26 | 设计 | `src/omega/` | TTS/ASR 集成(Volcengine/Deepgram) | 检查音频管道 | ⬜ |
| R9.27 | 设计 | `src/omega/` | OCR 集成(GLM-OCR) | 检查图像识别 | ⬜ |
| R9.28 | 设计 | `config/omega.yaml` | OMEGA 配置文件完整性 | 对照实际使用 | ⬜ |

## 9.5 优惠券与自动化工具（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.29 | 设计 | `src/execution/wechat_coupon.py` | 微信优惠券自动领取：mitmproxy 集成 | 检查代理逻辑 | ⬜ |
| R9.30 | 安全 | `src/execution/wechat_coupon.py` | Token 存储安全(.openclaw/coupon_tokens/) | 检查文件权限 | ⬜ |
| R9.31 | 设计 | `scripts/install_mitm_cert.sh` | mitmproxy 证书安装脚本 | 读取脚本 | ⬜ |
| R9.32 | 设计 | `scripts/nightly-audit/` | 夜间审计脚本：功能和调度 | 检查脚本内容 | ⬜ |
| R9.33 | 设计 | `scripts/setup_log_rotation.sh` | 日志轮转配置 | 检查 logrotate 配置 | ⬜ |

## 9.6 NPM 插件包（2 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R9.34 | 设计 | `packages/openclaw-npm/` | 30+ 扩展插件的组织和质量 | 列出所有插件 | ⬜ |
| R9.35 | 设计 | `packages/openclaw-npm/` | Telegram/Discord/Slack/飞书等适配器 | 检查各适配器完整性 | ⬜ |

---

## 执行检查清单

- [ ] 基线快照
- [ ] 闲鱼和社媒的外部 API 调用全部有超时和重试
- [ ] 微信 Bridge 凭证安全存储
- [ ] 回归测试
- [ ] 更新 CHANGELOG.md

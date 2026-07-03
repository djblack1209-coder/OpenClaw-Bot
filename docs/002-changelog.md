# CHANGELOG

> 格式规范: 每条变更必须包含 `领域` + `影响模块` + `关联问题`。文档更新触发规则以 `AGENTS.md` 和 `docs/003-docs-index.md` 为准。
> 领域标签: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`

## 最近更新（2026-07 / 2026-06 / 2026-05）


## [2026-07-03] Frist-API 生产迁移与域名/R2 收口
> 领域: `backend` | `deploy` | `infra` | `docs`
> 影响模块: `Frist-API`, `New-API Bridge`, `Cloudflare DNS`, `R2 Backup`, `GitHub Actions`
> 关联问题: TD-006, TD-007, TD-014, TD-015, HI-856, HI-857

### 变更内容
- 按 Carven 授权执行生产 New-API 迁移：用户、余额/订单、兑换码和日志已写入生产 New-API 数据库，Frist-API 生产环境启用 New-API adapter，并保留带时间戳回滚目录。
- 对历史 `enc:v1:` 用户 Key 采取安全跳过策略：旧数据加密密钥未能在本地、VPS-Config 或服务器常规备份中找到，不能把密文伪造成可用 Key；前端/服务端会把这类 Key 标记为需重新生成。
- 复用 VPS-Config 的 Cloudflare/R2 资产：`frist-api.245334.xyz` 写入 Cloudflare proxied A，源站 Origin CA 证书和 Nginx 443 已落地，正式 HTTPS 外网冒烟 HTTP 200；R2 备份脚本、root-only env、systemd timer 已在服务器启用并完成一次手动上传验证。
- 修正生产 SMTP 边界：代码和文档只登记变量名，不写入聊天里出现过的 SMTP 密码；服务器当前未检测到 `FRIST_API_SMTP_PASSWORD`，需 Carven 用无回显终端输入一次。
- 补齐提交前门禁：根目录 `.venv312` 软链加入忽略规则，避免误把本机 Python 环境提交；Python 依赖审计改用项目 Python 3.12 环境，避免系统 Python 3.9 误判 `requests>=2.33.0` 不可解析；gitleaks 历史误报通过指纹 allowlist 收口。

### 文件变更
- `docs/002-changelog.md` — 记录生产迁移、R2、Cloudflare 和 SMTP 安全边界。
- `docs/006-registries.md` — 更新 Frist-API 网关地址、New-API 迁移入口和回滚目录状态。
- `docs/007-operations.md` — 更新生产入口、New-API 已迁移、R2 已启用、SMTP 无回显输入和 Cloudflare proxied A 方案。
- `docs/009-health.md` — 更新 TD-006 / TD-007 和当前系统状态。
- `.gitignore` — 忽略根目录 `.venv312` 虚拟环境软链。
- `.gitleaksignore` — 只忽略两个历史误报指纹，保留默认 secret 扫描规则。

### 验证
- 生产迁移：`/opt/frist-api` apply 结果为 `migrated_users=19`、`tokens=1`、`frist_topups=4`、`redemptions=2`、`logs=162`；回滚目录 `/opt/frist-api/backups/newapi-migration-20260703T005433Z`。
- 生产健康：服务器 `docker compose --env-file .env -f docker-compose.frist-api.yml ps` 显示 `frist-api-server` 与 `openclaw-newapi` 均 healthy；本机 curl `http://frist-api.101-43-41-96.nip.io/api/frist/dashboard` 返回 HTTP 200；未授权 `/v1/models` 仍返回 401。
- R2 备份：`frist-api-r2-backup.timer` 为 enabled/active，手动上传返回 `http=200`。
- DNS/HTTPS：Cloudflare API 记录 `frist-api.245334.xyz` 为 A/proxied 指向腾讯云；源站安装 Cloudflare Origin CA 证书并新增 Nginx 443 反代，Nginx 配置备份目录为服务器 `/opt/frist-api/backups/nginx-origin-ca-20260703T013937Z`；`dig @ace.ns.cloudflare.com frist-api.245334.xyz A +short` 返回 Cloudflare 代理 IP；`curl https://frist-api.245334.xyz/api/frist/dashboard` 返回 HTTP 200。
- 依赖安全：`.venv312/bin/python -m pip_audit -r packages/clawbot/requirements.txt -r packages/clawbot/requirements-dev.txt --vulnerability-service pypi --progress-spinner off --cache-dir /tmp/openclaw-pip-audit-cache --timeout 10` → `No known vulnerabilities found`；`.venv312/bin/python -m pip check` → `No broken requirements found`；可提交文件 gitleaks 与 `gitleaks git . --redact --log-level error` 均返回 0。

## [2026-07-02] OpenClaw Bot / Frist-API 全面收口
> 领域: `backend` | `frontend` | `ai-pool` | `infra` | `docs` | `social` | `xianyu`
> 影响模块: `Frist-API`, `AI Pool`, `New-API Bridge`, `ClawBot`, `WeChat Bridge`, `Social Guardrails`, `GitHub Actions`, `Docs`
> 关联问题: HI-812, HI-817, HI-818, HI-856, HI-857, HI-887, HI-890, HI-896, TD-001, TD-002, TD-003, TD-004, TD-005, TD-006, TD-007, TD-008, TD-014, TD-015, TD-016, TD-017

### 变更内容
- AI_POOL 收口：余额站/86GameStore 类渠道新增日消费限额、慢线阈值、成本敏感标记、当日消费超剩余额且慢线自动熔断、真实调用 503/401 自动降级、清理会话粘滞和一次性告警，避免面板继续展示失效渠道。
- Frist-API 模型目录收口：客户可见模型只来自健康上游 `/v1/models` 或真实探测，硬编码目录只用于后台审计排序；New-API wildcard-only token 不再膨胀成客户可见模型。
- Frist-API 生产边界按最新运营决策改为“固定 HTTPS + New-API + 管理员 2FA + 兑换码收款闭环 + 备份/SLA”，微信/支付宝/Stripe 自动支付保留为未来备用，不再作为当前上线硬门槛。
- New-API 迁移脚本新增 dry-run/package/rollback：生成 runtime 备份、幂等迁移计划和回滚脚本；`--apply` 仍阻塞在人工确认执行窗口，不直接写生产库。
- ClawBot 后端收口：`/cli` 正式注册；微信编号命令可接内部只读 API 的全部映射到真实 GET 路由，交易/发文/发货/导出等高风险入口明确转人工确认；iLink token 失效时给出重新扫码提示和一次性告警。
- Frist-API 架构收口：已把邮件发送、SMTP DNS 轮询、注册/重置/余额预警邮件模板和邮箱归一化抽到 `server/email.js`，`server.js` 从 7881 行降到 7247 行；核心网关/账号路由仍保留在主入口，避免本轮为追求拆分引入生产行为风险。
- 依赖和安全门禁收口：升级 Python 依赖安全下限，默认移出高风险/冲突可选依赖并保持 graceful degradation；CI 新增 Gitleaks、npm audit high、pip-audit 门禁，并升级 `actions/cache@v6`、`actions/setup-python@v6`、`astral-sh/setup-uv@v8.2.0`。
- 社媒边界保持克制：只做工程质量和文档收口，继续保持待审草稿、只读采集、人工最终确认；没有恢复自动发布、评论、关注、私信、点赞或推广。
- 运维文档同步：域名/Cloudflare/R2 改为复用 `/Users/blackdj/Documents/VPS-Config` 既有资产；收款主路径改为闲鱼等第三方平台售卖兑换码 + Frist-API 核销；AGPL 源码入口已在 Frist-API 页脚暴露现有 GitHub 仓库链接。

### 文件变更
- `.github/workflows/ci.yml` — 增加 secret/audit 安全门禁并升级 GitHub Actions 运行时。
- `apps/frist-api/server/server.js` / `apps/frist-api/server/email.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/catalog.js` / `apps/frist-api/server/newApiBridge.js` — AI_POOL 熔断、模型目录、New-API 桥接、邮件模块拆分和生产边界收口。
- `apps/frist-api/src/core.js` / `apps/frist-api/src/app.js` / `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` — 客户可见模型、AGPL 源码入口和前端状态文案同步。
- `scripts/frist_api_newapi_migration_dry_run.mjs` / `apps/frist-api/tests/migration.test.mjs` — New-API 迁移演练、备份和回滚包。
- `packages/clawbot/src/bot/multi_bot.py` / `packages/clawbot/src/bot/cmd_cli_mixin.py` — `/cli` 正式注册。
- `packages/clawbot/src/api/routers/wechat.py` / `packages/clawbot/src/wechat_bridge.py` — 微信编号命令真实 API 映射、危险动作转人工、iLink 失效提示和告警。
- `packages/clawbot/requirements.txt` / `packages/clawbot/pytest.ini` — 依赖安全下限和第三方 warning 隔离。
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 注册表、运维和健康状态同步。

### 验证
- Frist-API：`cd apps/frist-api && node --test tests/core.test.mjs tests/server.test.mjs tests/migration.test.mjs tests/new-api-adapter.test.mjs tests/business-flow.test.mjs` → `161 passed / 0 failed / 0 skipped`；拆分邮件模块后 `tests/server.test.mjs` 单跑 → `92 passed / 0 failed`。
- 后端：`cd packages/clawbot && .venv312/bin/python -m pytest tests/ -o addopts='' --tb=short` → `1606 passed / 2 skipped / 0 failed`。
- 质量门禁：`make lint` → `All checks passed!`；桌面端 `npx tsc --noEmit && npm run lint && npm run build` → exit 0；`npm audit --audit-level=high --omit=dev`（桌面端、Frist-API）均 `found 0 vulnerabilities`；`pip check` → `No broken requirements found`；`pip-audit` → `No known vulnerabilities found`；tracked-tree `gitleaks detect --redact --no-git` → `no leaks found`；社媒真实浏览器 smoke → X/小红书/闲鱼 `buttonClicks=0`、`auto_publish_enabled=false`、`external_actions_locked=true`；`git diff --check` → exit 0。


## [2026-07-02] 社媒运营插件排程与增长复盘收口
> 领域: `backend` | `frontend` | `social` | `docs` | `infra`
> 影响模块: `OpenClaw Manager`, `Chrome Social Pilot`, `Social API`, `Telegram Commands`, `Execution Scheduler`, `Docs`
> 关联问题: TD-016, TD-017, HI-885

### 变更内容
- 收口社媒运营三端闭环：桌面端 Social 中控、Chrome 插件 Popup/Options、Telegram 命令与后端 API 统一支持人设确认、no-code 运营打法、当前页上下文扫描、增长复盘、增长反馈反哺待审草稿、待发布排程和最终人工确认。
- 安全边界保持不变：所有新增链路只生成/编辑/审核/排程草稿，不自动发布、不自动评论、不关注/私信、不调用推广/boost；网页登录额度入口仅复制提示词并打开模型网页，不自动提交。
- 清理失效生活自动化/微信优惠券相关冗余入口和旧 MITM token 脚本，避免继续保留不可维护、依赖短有效期凭证的功能路径。
- 修复 `gptoss` 启动超时后的心跳误报，避免未真正启动的 Bot 残留在健康检查和群聊路由里。
- 文档同步更新架构、注册表、运维、健康页和功能规格，并补充本轮提交前验证结果。

### 文件变更
- `apps/openclaw-manager-src/` — Social 中控、Tauri IPC/API、i18n 与静态测试同步更新。
- `packages/openclaw-npm/assets/chrome-extension/` — 新增/更新 Popup、Background、Options、共享 social-core、页面 runner 与插件测试。
- `packages/clawbot/src/api/routers/social.py` / `packages/clawbot/src/api/rpc.py` — 社媒工作台、插件状态、草稿、排程、增长复盘和最终确认 API 收口。
- `packages/clawbot/src/bot/` / `packages/clawbot/multi_main.py` / `packages/clawbot/src/social_scheduler.py` — Telegram 命令、中文自然语言入口、Bot 启动健康注册和调度安全闸口同步。
- `packages/clawbot/src/execution/social/` — 新增社媒人设确认和 X 自动运营辅助模块。
- `packages/clawbot/scripts/mitm_token_addon.py` / `packages/clawbot/src/execution/wechat_coupon.py` — 删除失效冗余实现。
- `docs/004-architecture.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/010-feature-specs.md` — 同步本轮系统状态和操作边界。

### 验证
- CLEANUP: `git diff --check` → exit 0；`docs/` 无子目录且编号命名合法；未发现 pyc/log/tmp/DS_Store 等生成物进入未跟踪列表；敏感格式扫描 `secret_like_hits=[]`。
- BACKEND: `cd packages/clawbot && .venv312/bin/python -m py_compile <changed-python-files>` → exit 0；`cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q` → exit 0，进度日志统计 `1601 passed / 2 skipped / 0 failed`。
- FRONTEND: `cd apps/openclaw-manager-src && npm run build` → `tsc && vite build` 成功；`cd apps/openclaw-manager-src/src-tauri && cargo check` → exit 0。
- PLUGIN: `node apps/openclaw-manager-src/src/components/Social/social-growth-feedback.static.test.mjs` → `5 passed`；`node packages/openclaw-npm/assets/chrome-extension/test/*.mjs` → Popup 静态 `26 passed`、social-core `31 passed`、page-runner `10 passed`，真实浏览器 smoke 返回 `ok=true` 且 `auto_publish_enabled=false` / `external_actions_locked=true`。
- RUNTIME: 本机 `ai.openclaw.clawbot-agent` 重启后，`GET /api/v1/status` 显示 7 个 Bot 均 `alive=true`，新日志 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。

## [2026-07-02] 修复 gptoss 启动失败后的心跳误报
> 领域: `backend` | `infra` | `docs`
> 影响模块: `MultiBot`, `HealthChecker`, `ChatRouter`, `LaunchAgent`
> 关联问题: HI-885

### 变更内容
- 修复 Bot 启动流程里的注册时机：只有 Telegram polling 真正启动成功后，才把 Bot 写入健康检查和群聊路由。
- 避免 gptoss 这类 Bot 在启动超时或缺 Token 时残留成“健康检查里存在、运行注册表里不存在”的假实例，导致持续出现“Bot 心跳丢失 / 未注册重启函数”告警。
- 新增回归测试覆盖“缺 Token 启动失败不残留健康心跳或路由”的场景。
- 已重启本机 `ai.openclaw.clawbot-agent`，gptoss 重新上线，当前 7 个 Bot 均为 alive。

### 文件变更
- `packages/clawbot/src/bot/multi_bot.py` — 将健康/路由注册移动到启动成功后执行。
- `packages/clawbot/tests/test_multibot_startup_registration.py` — 新增启动失败残留注册回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮告警处置和验证结果。

### 验证
- RED: `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_multibot_startup_registration.py -q` → 新测试先失败，复现构造时提前注册的问题。
- GREEN: `cd packages/clawbot && .venv312/bin/python -m py_compile src/bot/multi_bot.py src/monitoring/health.py multi_main.py && .venv312/bin/python -m pytest tests/test_multibot_startup_registration.py tests/test_chat_router.py tests/test_monitoring_module.py -q` → `31 passed`，仅历史依赖 warning。
- FULL: `cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q` → exit 0；进度日志统计 `1601 passed / 2 skipped / 0 failed`，仅历史依赖和调度测试 coroutine warning。
- RUNTIME: `launchctl kickstart -k gui/$(id -u)/ai.openclaw.clawbot-agent` 后，`GET /api/v1/status` 显示 `qwen235b/gptoss/claude_sonnet/claude_haiku/deepseek_v3/claude_opus/free_llm` 均 `alive=true`；新日志中 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。

## [2026-07-01] 下线失效生活自动化任务
> 领域: `backend` | `docs` | `infra`
> 影响模块: `Telegram Commands`, `Execution Scheduler`, `LaunchAgent`, `Docs`
> 关联问题: TD-018

### 变更内容
- 因该生活自动化任务依赖短有效期凭证且恢复成本过高，已从项目中下线。
- 移除对应 Telegram 手动命令、中文自然语言触发、Bot 进程内定时调度、独立本机定时脚本和本机 LaunchAgent，避免继续发送相关 Telegram 通知。
- 清理示例配置、注册表、运维手册和健康页中的历史方案细节，只保留本条泛化下线记录。

### 文件变更
- Bot 命令、帮助菜单、中文自然语言入口、执行调度器、控制面板任务项、已失效实现、专用脚本、专用测试、示例配置与项目文档均已同步清理。

### 验证
- GREEN: `cd packages/clawbot && ./.venv312/bin/python -m py_compile multi_main.py src/bot/cmd_intel_mixin.py src/bot/multi_bot.py src/bot/chinese_nlp_mixin.py src/bot/cmd_basic/help_mixin.py src/bot/workflow_mixin.py src/bot/callback_mixin.py src/execution/scheduler.py src/api/routers/controls.py src/api/routers/wechat.py src/api/rpc.py src/api/schemas.py src/http_client.py src/ocr_router.py src/shopping/blackfriday_scanner.py src/shopping/crawl4ai_engine.py config/prompts.py` → exit 0。
- GREEN: `cd packages/clawbot && ./.venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_social_scheduler.py tests/test_newapi_router.py -q --tb=short` → `52 passed`，仅 requests/js2py 依赖 warning。
- INFRA: 本机 LaunchAgent 检查确认已失效任务不存在。
- CLEANUP: 已删除旧状态/日志文件和本机旧临时文件；未读取或输出任何凭证明文。



## [2026-06-22] 收口 Dependabot 依赖安全告警
> 领域: `frontend` | `backend` | `docs` | `infra`
> 影响模块: `OpenClaw Manager`, `WorldMonitor`, `Dependabot`, `openclaw-npm`, `Weixin Extension`, `ClawBot Dev Requirements`
> 关联问题: OSS review hardening

### 变更内容
- 处理打开 Dependabot 后暴露的依赖安全告警：升级 `.openclaw/extensions/openclaw-weixin` 的 Vitest 相关 lockfile，并用 overrides 固定 `glob`、`brace-expansion`、`esbuild` 安全版本。
- 桌面端 `apps/openclaw-manager-src` 移除 `react-simple-maps`，改用 `d3-geo` + `topojson-client` 直接渲染本地 `countries-110m.json`，清理旧 d3 漏洞链；同步升级 `vite`、`postcss` 和多项传递依赖 overrides。
- 升级 `packages/clawbot/requirements-dev.txt` 中 `pytest` 到 `>=9.0.3,<10.0`，并配套升级 `pytest-asyncio` 到 `>=1.4.0,<2.0`。
- 收口 `packages/openclaw-npm` 及扩展包中的 `hono`、`undici`、`markdown-it`、`tar`、`@opentelemetry/sdk-node` 等安全补丁版本，并移除源码未直接使用且上游暂无 patched version 的 `@mariozechner/pi-coding-agent` 直接依赖。
- 同步 `docs/006-registries.md` 和 `docs/009-health.md`，登记本轮依赖安全处理范围与验证结果。
- 修复 `test_api_routes_regression.py` 在全量测试中被本机 `OPENCLAW_API_TOKEN` / `.env` 污染后返回 401 的测试隔离问题，确保 API route 回归测试固定运行在无 Token 开发模式。

### 文件变更
- `.openclaw/extensions/openclaw-weixin/package.json` / `package-lock.json` — 升级测试相关依赖并收口传递漏洞。
- `apps/openclaw-manager-src/package.json` / `package-lock.json` — 替换地图依赖，升级构建依赖并添加安全 overrides。
- `apps/openclaw-manager-src/src/components/WorldMonitor/index.tsx` — 地图改为 `d3-geo` + `topojson-client` 渲染。
- `packages/clawbot/requirements-dev.txt` — 升级 `pytest` / `pytest-asyncio`。
- `packages/openclaw-npm/package.json`、`packages/openclaw-npm/extensions/*/package.json` — 收口 Node 安全依赖。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加 API 鉴权环境隔离 fixture，避免本机密钥污染回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 记录依赖安全收口。

### 验证
- `cd .openclaw/extensions/openclaw-weixin && npm audit --audit-level=moderate` → `found 0 vulnerabilities`。
- `cd apps/openclaw-manager-src && npm audit --audit-level=moderate` → `found 0 vulnerabilities`。
- `cd apps/openclaw-manager-src && npx tsc --noEmit` → 退出码 0。
- `cd apps/openclaw-manager-src && npm run build` → 退出码 0，Vite build 成功。
- `cd packages/clawbot && .venv312/bin/python -m pip check` → `No broken requirements found`。
- `cd packages/clawbot && OPENCLAW_API_TOKEN=demo .venv312/bin/python -m pytest tests/test_api_routes_regression.py -q --tb=short` → `12 passed`。
- `git diff --check` → 退出码 0。

## [2026-06-22] 补齐开源社区行为准则
> 领域: `docs` | `infra`
> 影响模块: `OSS Governance`, `README`, `Docs Index`
> 关联问题: OSS review hardening

### 变更内容
- 新增 `docs/015-code-of-conduct.md`，明确 issue、PR、Discussions 和安全报告中的友善协作、脱敏、禁止绕过平台规则和执行方式。
- 在 `README.md` 贡献入口加入行为准则链接，让外部贡献者在提交 issue / PR 前能看到社区规则。
- 更新 `docs/003-docs-index.md`，登记新增编号文档并保持 `docs/` 根目录扁平编号治理。

### 文件变更
- `docs/015-code-of-conduct.md` — 新增社区行为准则。
- `README.md` — 贡献入口增加行为准则链接。
- `docs/003-docs-index.md` — 登记新增文档。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮 OSS 治理补齐。

### 验证
- `find docs -maxdepth 2 -type d -print` → `docs` 下无子目录。
- `find docs -maxdepth 1 -type f -name '*.md' -exec basename {} \; | sort` → 新增文档为编号英文名。
- `git diff --check -- README.md docs/003-docs-index.md docs/015-code-of-conduct.md docs/002-changelog.md docs/009-health.md` → 退出码 0。

## [2026-06-22] 收口 OSS 审核前安全设置
> 领域: `docs` | `infra`
> 影响模块: `GitHub Repository`, `Security Settings`, `Local Git Refs`
> 关联问题: OSS review hardening

### 变更内容
- 开启 GitHub Dependabot security updates，让公开依赖告警后续可以自动生成安全修复 PR。
- 开启 GitHub private vulnerability reporting，让外部研究者可以通过私密入口报告漏洞，避免把敏感复现细节发到公开 issue。
- 清理本地仅存在的旧分支和 Codex 快照 ref，避免后续误推历史实验分支造成重复审核噪音。
- 二次清理本地可重建缓存、根目录临时截图和 Playwright 临时目录；运行配置、依赖环境、runtime 数据和生产备份继续保留。

### 文件变更
- `docs/002-changelog.md` — 记录本轮 OSS 审核前安全设置收口。
- `docs/009-health.md` — 更新公开仓库安全状态。

### 验证
- `gh api repos/djblack1209-coder/OpenClaw-Bot --jq '.security_and_analysis'` → `dependabot_security_updates=enabled`、`secret_scanning=enabled`、`secret_scanning_push_protection=enabled`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/private-vulnerability-reporting --jq '.'` → `{"enabled":true}`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/secret-scanning/alerts --paginate --jq '[.[] | select(.state=="open")] | length'` → `0`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/dependabot/alerts --paginate --jq '[.[] | select(.state=="open")] | length'` → `0`。
- `git for-each-ref --format='%(refname)' refs/heads refs/remotes refs/tags refs/stash refs/codex` → 仅剩 `main` 和 `origin/main` 相关 refs。
- `git fsck --full --unreachable --no-reflogs` → 无残留不可达对象输出。

## [2026-06-22] 补齐开源项目审核材料
> 领域: `docs` | `infra`
> 影响模块: `OSS Governance`, `README`, `Security Policy`
> 关联问题: Codex for OSS application readiness

### 变更内容
- 根目录新增 Apache-2.0 `LICENSE`，把项目从 README 中的私有/专有表述改为公开开源项目，提升 OpenAI Codex for OSS 等开源项目审核的一致性。
- 重写根 `README.md`：补充项目定位、可复用开源价值、技术栈、启动方式、文档入口、贡献入口和安全/合规边界。
- 新增 `docs/013-contributing.md` 和 `docs/014-security.md`：提供贡献流程、PR 验证清单、漏洞报告方式、密钥保护规则，以及赞助 API credits 只能用于 PR review、测试、文档、安全分析和重构维护的边界。
- 新增 GitHub issue/PR 模板，并用 GitHub CLI 更新仓库公开描述、topics、Discussions、secret scanning 和 push protection，提升社区资料完整度和密钥误提交防护。
- 同步 `docs/003-docs-index.md`，登记新增文档编号，继续遵守 `docs/` 扁平编号规则。

### 文件变更
- `LICENSE` — 新增 Apache License 2.0 根许可证。
- `README.md` — 改为开源友好的项目说明和安全边界。
- `docs/013-contributing.md` — 新增贡献指南。
- `docs/014-security.md` — 新增安全政策。
- `.github/ISSUE_TEMPLATE/bug_report.yml` / `.github/ISSUE_TEMPLATE/feature_request.yml` / `.github/ISSUE_TEMPLATE/config.yml` — 新增 GitHub issue 模板和安全报告入口。
- `.github/pull_request_template.md` — 新增 PR 验证与安全检查模板。
- `docs/003-docs-index.md` — 登记新增文档。
- `docs/009-health.md` — 记录 OSS 审核准备状态。

### 验证
- `find docs -maxdepth 1 -type f -name '*.md' -exec basename {} \\; | sort` → 确认新增文档均在 `docs/` 根目录且编号命名。
- `grep -n "Private / Proprietary" README.md LICENSE docs/013-contributing.md docs/014-security.md docs/003-docs-index.md docs/009-health.md` → 无旧私有许可证表述残留。
- `git diff --check -- LICENSE README.md docs/013-contributing.md docs/014-security.md docs/003-docs-index.md docs/002-changelog.md docs/009-health.md .github/ISSUE_TEMPLATE/bug_report.yml .github/ISSUE_TEMPLATE/feature_request.yml .github/ISSUE_TEMPLATE/config.yml .github/pull_request_template.md` → 退出码 0。
- `gh repo view djblack1209-coder/OpenClaw-Bot --json nameWithOwner,description,isPrivate,repositoryTopics,hasIssuesEnabled,hasDiscussionsEnabled` → 仓库公开、Issues/Discussions 已开启，topics 已包含 `ai-agents`、`telegram-bot`、`fastapi`、`tauri`、`react`、`llm-routing`、`open-source`、`automation`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot --jq '{security_and_analysis:.security_and_analysis}'` → `secret_scanning=enabled`、`secret_scanning_push_protection=enabled`。

## [2026-05-09] Frist-API 319px 移动端批注修复
> 领域: `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-901

### 变更内容
- 修复 319px 极窄屏顶栏遮挡：顶栏拆成品牌行和操作行，语言、连接状态点、登录余额按钮在第二行网格内排布，去掉 `body min-width: 320px` 造成的 319px 横向溢出。
- 修复工作台折叠菜单箭头溢出：移动端 `.rail-toggle` 改为相对定位并把箭头固定在按钮右侧安全区内，展开/收起旋转不再跑出容器。
- 优化 Dashboard 空状态：模型消耗空饼图改为带分段提示的空态环，并明确“暂无真实请求”；异常卡说明检测余额突增、失败率、慢请求和异常模型消耗；通道卡说明 60 秒巡检和登录创建 Key 后展示号池状态。
- 收口语言切换行为：按钮继续切换 `html.lang` 和偏好状态，但明确提示“仅切换语言偏好”，不再让用户误以为已完成全站中英文翻译。
- 修复 CC Switch 319px 比例和裁切：目标按钮改为两列，导入说明、用量查询、模型导出和代码片段统一 `min-width: 0` / `overflow-wrap: anywhere`，避免教程和模型列表横向撑破屏幕。
- 已用 319×718 浏览器回测 Dashboard 与 CC Switch：本地 `scrollWidth=319`，顶栏账户按钮宽度 173px，CC Switch 主内容宽 281px、用量说明宽 235px，无横向溢出。
- 已同步部署到腾讯云 `/opt/frist-api`，部署前备份为 `/opt/frist-api/backups/frist-api-mobile-319-20260509-045253-before-f2d6eda.tgz`；远端 `node --check` 和批注聚焦测试 57/57 通过，`frist-api-server` 重启后 healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401，公网 319×718 Dashboard/CC Switch 复验 `scrollWidth=319`。

### 文件变更
- `apps/frist-api/index.html` — 增加语言状态辅助文本、Dashboard 卡片说明文案，并更新资源版本。
- `apps/frist-api/src/app.js` — 丰富消耗、异常、通道空状态，语言切换改为诚实提示偏好状态。
- `apps/frist-api/src/styles.css` — 增加 319px 移动端护栏，修复顶栏、折叠菜单箭头、空饼图和 CC Switch 横向裁切。
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加 319px 顶栏、箭头、空态、语言状态和 CC Switch 宽度回归断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮移动端批注修复和登记 HI-901。

## [2026-05-09] Frist-API 工作台批注修复
> 领域: `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Tencent Cloud`, `docs`
> 关联问题: HI-900

### 变更内容
- 恢复用户端原抽象品牌 Logo：顶部不再显示单字母 `F` 占位，改回红白斜切品牌标，防止 Tabcode 皮肤覆盖 Frist-API 识别。
- 修复 Token 趋势图交互：折线图增加透明热区、键盘聚焦点位和 `data-trend-tooltip` 数据浮层，鼠标移入图表即可看到日期与 Token 数值。
- 收口工作台布局：左侧导航固定为同一个工作台栏，`API Key`、趋势、记录、模型、资料和 CC Switch 等页面都在右侧 `workspace-content` 内切换，不再像单独页面脱离导航。
- 降低当前导航项视觉噪音：首页选中态从蓝色大背景改为细线和文字提示，保留 `aria-current="page"` 给辅助技术识别。
- 补充回归护栏：测试锁定 Logo 不可退回 `F` 字母、工作台内容必须在右侧区域切换、趋势图必须具备 hover 数据钩子。
- 已同步部署到腾讯云 `/opt/frist-api`，部署前备份为 `/opt/frist-api/backups/frist-api-workbench-comments-20260509-035316-before-385bfce.tgz`；远端容器 `frist-api-server` 重启后 healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401。

### 文件变更
- `apps/frist-api/index.html` — 恢复品牌标结构，新增 `workspace-content` 右侧内容容器，并更新资源版本。
- `apps/frist-api/src/app.js` — 新增趋势图 hover/键盘聚焦数据点和浮层渲染。
- `apps/frist-api/src/styles.css` — 固定工作台左侧导航、恢复红白斜切 Logo、移除当前项大块背景、补趋势图热区与浮层样式。
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加批注回归断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮批注修复和登记 HI-900。

## [2026-05-09] Frist-API 移动端管理员入口补齐与上游 Key 自动巡检
> 领域: `frontend` | `backend` | `ai-pool` | `infra` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Gateway Monitor`, `Alerting`, `docs`
> 关联问题: HI-896, HI-899, TD-013

### 变更内容
- 补齐移动端管理员操作入口：顶栏常驻 `登录/身份码/管理` 快捷按钮，游客可直接打开登录弹窗，登录未激活管理员时一键打开身份码输入框，已激活后直达管理页，避免入口仅藏在账户弹窗底部。
- 新增后台通道巡检队列：支持按 60 秒间隔自动探测健康库存，即使无人请求也会刷新通道状态并回写连通性数据。
- 用户端首页新增 60 秒静默刷新，看板连通性与后台巡检保持同频更新，无需手动点“检测”才看到降级结果。
- 新增上游 Key 自动降级与一次性补号提醒：巡检或网关请求发现认证失败/额度耗尽时自动禁用对应 Key，支持 Telegram Bot 或 Webhook 告警，单 Key 同类问题只提醒一次，避免重复通知。
- 巡检过程会保留可用通道并更新路由字段与延迟数据，用户侧继续按健康库存自动切换，不暴露上游密钥和号商细节。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 新增移动端管理员快捷入口与交互样式。
- `apps/frist-api/server/server.js` — 新增后台 60 秒巡检、Key 异常一次性告警、运行时告警去重存储和 Telegram/Webhook 通知。
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 新增巡检降级回归与移动端快捷入口断言。
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 新增通道巡检与 Key 告警环境变量透传。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮功能、运维配置和风险状态。

## [2026-05-09] Frist-API 移动端导航和卡商通道展示修复
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Channel Monitor`, `docs`
> 关联问题: HI-898

### 变更内容
- 修复移动端顶栏批注：423px 窄屏下 Logo 收敛为紧凑品牌区，连接状态改为小状态点，不再挤占余额按钮或产生横向溢出。
- 将移动端工作台左侧导航改为默认折叠菜单：点击“工作台导航”展开，进入任一页面后自动收起，并同步当前页标题。
- 通道连通性从模型分类展示改为客户可理解的号池渠道展示：公开卡片显示 `卡商1`、`卡商2` 等渠道名和号池标签，不再展示 `.provider-models` 模型标签。
- 清理延迟 mock 口径：补号导入未显式填写或探测不到真实延迟时落为 `0`，前端展示“等待真实请求更新”，不再用 `999ms/1000ms` 伪造最低/平均延迟。
- 固定监控刷新口径为 60 秒，并在通道聚合里保留 healthy/down/slow 统计，支持同一卡商下快线、慢线、断线的自动降级状态。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` / `apps/frist-api/src/app.js` — 移动端 Logo、状态灯、折叠菜单和通道卡 UI 修复。
- `apps/frist-api/server/server.js` / `apps/frist-api/server/catalog.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/newApiClient.js` / `apps/frist-api/src/core.js` — 卡商号池聚合、60 秒刷新、无真实延迟空态和模型目录可用性保护。
- `apps/frist-api/src/admin.js` / `apps/frist-api/src/businessFlow.js` — 未提供真实延迟时不再写入默认假延迟。
- `apps/frist-api/tests/*.test.mjs` — 增加移动端折叠导航、卡商通道、无假延迟、模型目录和自动降级回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮批注修复、验证证据和剩余生产风险。

## [2026-05-09] 本地冗余清理与文档状态收口
> 领域: `infra` | `docs`
> 影响模块: `Workspace`, `Frist-API`, `ClawBot`, `docs`
> 关联问题: HI-897

### 变更内容
- 清理本地可重建冗余：移除源码树中的 `.DS_Store`、`.playwright-mcp`、`.pytest_cache`、`__pycache__`、`.ruff_cache`、Playwright/Expect 调试产物、Frist-API 历史审计截图、根目录临时截图和 ClawBot 本地旧日志。
- 明确保留边界：未删除 `.env`、`.openclaw/` 运行身份与会话、Frist-API runtime 数据、ClawBot `data/`、桌面端 `node_modules`、Python `.venv312`、腾讯云生产备份和共享服务器其他项目，避免清理动作造成运行状态丢失。
- 复核 `.gitignore` 已覆盖 `.DS_Store`、`__pycache__/`、`.pytest_cache`、`.playwright-mcp/`、`.playwright-cli/`、根目录截图、日志和密钥扫描报告；本轮不需要新增忽略规则。
- 同步文档状态：健康页新增 `HI-897`，登记本轮冗余清理范围、保留原因和验证口径；项目全景图更新时间，避免入口文档继续停留在 2026-04 的旧审计状态。
- 清理后复验：`git diff --check` 通过；`make new-api-check` 显示 GitHub 最新、本地源码和 Compose 镜像均为 `v1.0.0-rc.4`；公网首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名最终跳转到唯一 Frist-API 入口；浏览器只读复核页面标题 `Frist-API`，控制台 0 error/0 warning；复核产生的 `.playwright-mcp` 临时快照已二次清理。

### 文件变更
- `docs/002-changelog.md` — 新增本轮冗余清理和文档状态收口记录。
- `docs/009-health.md` — 更新本地日志/冗余清理状态，并登记 `HI-897`。
- `docs/001-project-map.md` — 更新时间提示，说明当前状态以健康页和变更日志为准。

## [2026-05-09] New-API 生产启动与 CC Switch 连通复核
> 领域: `infra` | `ai-pool` | `deploy` | `docs`
> 影响模块: `New-API`, `Frist-API`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-895, HI-896

### 变更内容
- 继续处理腾讯云 New-API 升级遗留项：本轮重新备份 `/opt/frist-api/data/newapi`、`.env` 和 compose 后，成功拉取 `calciumion/new-api:v1.0.0-rc.4`，解除上一轮 Docker Hub 超时阻塞。
- 定位启动失败根因并修复部署方式：共享服务器已有 `/opt/ccgame/server/src/app.js` 长期监听 `127.0.0.1:3000`，因此将 `docker-compose.newapi.yml` 的宿主机端口改为 `NEWAPI_HOST_PORT` 可配置；腾讯云设置 `NEWAPI_HOST_PORT=13000`，容器内部仍为 `3000`，不停止无关项目。
- 定位第二个启动失败根因并修复远端数据权限：`data/newapi` 来自旧 UID 501，New-API 在安全加固 `cap_drop: ALL` 下无法创建 `/data/logs`；已把远端 `data/newapi` 调整为 `root:root`、目录 `750`、数据库文件 `640`，保留安全加固而非放宽容器权限。
- 复验 New-API 运行态：`openclaw-newapi` 运行 `v1.0.0-rc.4`，`127.0.0.1:13000->3000/tcp`，健康状态 `healthy`；`/api/status` 返回 `success=true`、`version=v1.0.0-rc.4`、`setup=true`。
- 使用浏览器复核公网 `#switch`：页面标题 `Frist-API`，控制台 0 error/0 warning，Dashboard 请求 200；未登录状态下页面不生成带 Key 的 provider 导入链接，保留 21 个模型展示和独立 MCP deep link，符合“登录并创建 Key 后生成用量脚本”的边界。
- 用运行数据生成脱敏 CC Switch provider 链接样本，确认 `resource=provider`、`app=codex`、`endpoint=http://frist-api.101-43-41-96.nip.io/v1`、默认模型 `gpt-5.5`、`usageScript` 指向 `/api/frist/key-usage` 且包含 Authorization；未出现旧的大块 `config/settings_config/availableModels` 参数。
- 受控临时 Key 连通性复核：`/v1/models` 返回 200 且 21 个模型，用量接口返回 200 且 `ok=true/valid=true`；真实 `chat/completions` 返回 503，追踪到唯一 healthy 上游在测试请求后返回 401 并触发 `credential_failed upstream_http_401`，说明当前上游库存 Key 无法形成完整聊天闭环。已从测试前备份恢复 runtime，临时测试用户/Key 清零，唯一 healthy 通道状态恢复。
- 公网冒烟最终结果：首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名 301；本地 Frist-API 3180 为 200，New-API 13000 为 200。

### 文件变更
- `docker-compose.newapi.yml` — New-API 宿主机端口改为 `NEWAPI_HOST_PORT` 可配置，默认仍为 `3000`。
- `docs/006-registries.md` / `docs/007-operations.md` — 更新 New-API 固定版本、端口变量和腾讯云实际运行状态。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记本轮生产启动、CC Switch 复核证据和真实聊天连通遗留风险。

## [2026-05-08] 审计入口复核与测试命令收口
> 领域: `docs` | `infra`
> 影响模块: `AGENTS`, `docs`, `pytest`
> 关联问题: HI-894, HI-895

### 变更内容
- 本轮继续审计时发现直接运行 `pytest packages/clawbot/tests/ ...` 会命中本机 Python 3.9 的用户级 `pytest`，而项目代码和 CI 要求 Python 3.12；这会产生 `str | None` 类型语法错误，属于审计入口误用，不是业务代码回归。
- 已将 AGENTS/SOP 和快速导航里的后端测试命令收口为 `make test` 或 `.venv312/bin/python -m pytest`，确保本地审计与 GitHub Actions 的 Python 3.12 基线一致。
- 复验实际证据：`make test` 使用 `packages/clawbot/.venv312/bin/python` 执行并通过；GitHub `OpenClaw CI` run `25590993947` 两个 job 均成功；`New-API Scheduled Sync` run `25589650518` 成功；`make new-api-check` 显示本地源码和 Compose 镜像均为 `v1.0.0-rc.4`。
- 远端复核发现腾讯云 `/opt/frist-api/docker-compose.newapi.yml` 仍停留在 `calciumion/new-api:v1.0.0-rc.2`，已先备份 `data/newapi` 和旧 compose 到 `backups/newapi-runtime-20260508223247-before-rc4.tgz`，再同步 compose 到 `v1.0.0-rc.4` 并通过 `docker compose config` 校验；实际启动受 Docker Hub 访问超时阻塞，New-API 容器未启动，现有 `frist-api-server` 仍 healthy 且公网首页/看板 200。

### 文件变更
- `AGENTS.md` / `docs/001-project-map.md` / `docs/005-quickstart.md` — 统一后端测试入口，避免系统 Python 误用旧测试工具。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记本轮审计入口修复和剩余环境风险。

## [2026-05-08] 浏览器审计收尾与 CI 运行时升级
> 领域: `frontend` | `infra` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `OpenClaw CI`, `New-API`, `docs`
> 关联问题: HI-886, HI-891, HI-892, TD-015

### 变更内容
- 使用内置浏览器审计公网 `http://frist-api.101-43-41-96.nip.io/`：首页 200、标题为 `Frist-API`、控制台无 error/warn；窄屏用户端可正常进入首页和 CC Switch，CC Switch 会切成带“首页”返回按钮的详情页。
- 发现无障碍噪音：隐藏视图中的多个 `.back-home::before` 文本箭头会在浏览器快照里聚合为 `← ← ←`；已改为纯 CSS 边框箭头，保留视觉箭头但不再暴露额外文本。
- 复审发现账户弹窗密码输入框缺少真实 `form` 语义，浏览器会给出密码管理器结构提示；已按登录/注册、改密码、重置密码、身份码激活拆成独立表单，补齐 `autocomplete`，并让回车提交走原处理逻辑。
- 清理 GitHub Actions Node 20 运行时预警：`OpenClaw CI` 升级 `actions/checkout@v6`、`actions/setup-node@v6`，前端 typecheck 改用 Node.js 24。
- 合并 New-API 自动同步 PR #1：submodule 和 Compose 镜像已同步到 `v1.0.0-rc.4`；本地复验 `docker compose -f docker-compose.newapi.yml config` 通过。正式生产部署仍需先备份 `data/newapi` 并保留回滚窗口。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 返回首页按钮箭头改为非文本 CSS 图形；账户弹窗改为按动作拆分的真实表单并保留原视觉布局，消除隐藏视图可访问性噪音和密码管理器结构提示。
- `apps/frist-api/tests/business-flow.test.mjs` — 增加账户表单语义、自动填充和回车提交回归断言。
- `.github/workflows/ci.yml` — 升级 checkout/setup-node action 和 Node.js 版本，消除 Node 20 Actions 预警。
- `docker-compose.newapi.yml` / `packages/new-api-upstream` — 经 PR #1 合并同步 New-API 到 `v1.0.0-rc.4`。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录浏览器审计、CI 清理和 New-API 合并状态。

## [2026-05-08] New-API 定时同步工作流修复
> 领域: `infra` | `ai-pool` | `docs`
> 影响模块: `GitHub Actions`, `New-API Sync`, `docker-compose.newapi.yml`, `docs`
> 关联问题: HI-886, HI-891

### 变更内容
- 定位 `New-API Scheduled Sync` 最近失败 run `25576027773`：检查和同步步骤均成功，失败点为 `docker compose -f docker-compose.newapi.yml config` 在 GitHub Actions 中缺少 `NEWAPI_INITIAL_TOKEN`，导致同步 PR 步骤被跳过。
- 在工作流的 compose 配置校验步骤注入 CI 专用占位 `NEWAPI_INITIAL_TOKEN`，只用于解析配置，不触碰生产 `.env` 或真实 root token。
- 调整 New-API 检查脚本语义：退出码 `0` 表示已同步，`2` 表示需要同步，其他非零才表示真实错误；工作流据此避免把网络、GitHub API、submodule 等真失败误判成“需要同步”。
- 同步处理 GitHub 不更新的本地侧原因：本地 `main` 比 `origin/main` 多 3 个提交，本轮提交后需一并推送到 GitHub 触发工作流复验。
- 推送后复验：仓库级 Actions 权限从只读改为 write 并允许创建 PR；`New-API Scheduled Sync` run `25588894721` 已通过全部步骤，并创建 `codex/new-api-scheduled-sync` 到 `main` 的 PR #1。

### 文件变更
- `.github/workflows/new-api-sync.yml` — 为 compose 校验注入 CI 占位 token，并只把退出码 2 当作需要同步。
- `scripts/sync_new_api_upstream.sh` — `check` 模式用退出码 2 表达版本漂移。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记 GitHub Actions 根因、修复和剩余 New-API 生产升级风险。

## [2026-05-08] 严格审计复核与闲鱼管理页安全部署
> 领域: `backend` | `frontend` | `xianyu` | `deploy` | `docs`
> 影响模块: `OpenClaw Manager`, `WorldMonitor`, `NewsFeed`, `Xianyu Admin`, `APIServer`, `Tencent Cloud`
> 关联问题: HI-885, HI-886, HI-887, HI-889, HI-890

### 变更内容
- 明确复核上一轮审计边界：上一轮不是“全项目绝对完美生产级全量审计”，本轮用本地代码、live 命令、远端只读检查和公网冒烟补证据链。
- 为 `/api/v1/store/catalog` 增加专项回归，防止 Store 路由缺失再次只在全量 APIServer 初始化时暴露。
- 桌面端 `NewsFeed` 和 `WorldMonitor` 移除用 `textarea.innerHTML` 解码外部新闻文本的实现，改为共享 `decodeHtmlEntities()`，避免把外部文本交给 HTML 解析器。
- 闲鱼管理页内嵌前端补 `escapeHtml()`，对 dashboard、系统状态、最近对话、最近订单等接口返回字段写入 `innerHTML` 前统一转义，并增加页面安全回归。
- 已将闲鱼管理页同一安全修复单文件部署到腾讯云 `/home/clawbot/clawbot/src/xianyu/xianyu_admin.py`；部署前远端备份为 `/home/clawbot/clawbot/backups/xianyu_admin_20260508155652_before_escape.py`，远端 `py_compile` 通过，`clawbot.service` 重启后为 active。
- 验证证据：后端全量 pytest 退出码 0，当前 pytest nodeids 为 1495；`test_api_routes_regression.py` 12/12 通过；Frist-API `npm test` 153/153 通过且 `npm audit --audit-level=moderate` 0 漏洞；桌面端 `npx tsc --noEmit` 通过；`git diff --check` 和 Frist-API JS 语法检查通过；`gitleaks git --log-opts='HEAD~2..HEAD' --redact` 0 泄漏；公网 Frist-API 首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名 301。
- 保留真实遗留风险：New-API 本地/镜像仍为 `v1.0.0-rc.2`，GitHub live 最新为 `v1.0.0-rc.4`；用户在对话中暴露了服务器 root 密码，必须轮换；86GameStore 余额/消费/延迟风险仍需运营限额和慢线治理。

### 文件变更
- `apps/openclaw-manager-src/src/lib/html.ts` — 新增安全 HTML 实体解码工具。
- `apps/openclaw-manager-src/src/components/NewsFeed/index.tsx` / `apps/openclaw-manager-src/src/components/WorldMonitor/index.tsx` — 复用安全实体解码，不再用 `innerHTML` 解码外部文本。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 闲鱼管理页动态字段统一转义。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加 Store 路由和闲鱼管理页转义回归。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步严格审计、部署和剩余风险。

## [2026-05-08] 全量测试审计和 Store 路由恢复
> 领域: `backend` | `frontend` | `ai-pool` | `infra` | `docs`
> 影响模块: `APIServer`, `Store Router`, `Frist-API`, `New-API`, `docs`
> 关联问题: HI-885, HI-886, HI-887, HI-888

### 变更内容
- 先按用户要求提交工作区 checkpoint：`60709ea chore: checkpoint frist api recovery state`，再进行全量测试和审计。
- 后端全量测试发现 `src.api.routers.store` 缺失导致 APIServer 初始化失败；恢复 `/api/v1/store/catalog` 和 `/api/v1/store/categories` 最小兼容路由后，`pytest packages/clawbot/tests/ --tb=short -x` 通过 `1491 passed, 2 skipped`。
- 为 Frist-API 生成 `package-lock.json`，补齐 `npm audit` 可审计基线；`npm test` 通过 `153/153`，`npm audit --audit-level=moderate` 为 0 漏洞，JS 语法检查通过。
- 桌面端 `npx tsc --noEmit` 通过；公网冒烟确认 Frist-API 首页 200、Dashboard 200、未授权 `/v1/models` 401。
- 生产审计登记：New-API 本地 `v1.0.0-rc.2` 落后于上游 `v1.0.0-rc.4`；86GameStore 面板显示余额 `$35.70`、今日实际消费 `$38.1537`、平均响应 `16.11s`，不属于完美生产态。
- 调整运维文档环境变量示例写法，消除 `gitleaks` 对当前 HEAD 的 `generic-api-key` 误报。

### 文件变更
- `packages/clawbot/src/api/routers/store.py` — 恢复统一插件商店 API 路由。
- `apps/frist-api/package-lock.json` — 固定 Frist-API npm 审计基线。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步测试证据、问题清单、注册表和安全扫描记录。

## [2026-05-08] Frist-API 登录恢复和公网配置修复
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `Tencent Cloud`, `docs`
> 关联问题: HI-884

### 变更内容
- 修复登录失败反馈：前端不再把服务端 401 “邮箱或密码不正确”统一翻译成“后端暂不可用”，找回密码和重置密码也展示真实反馈。
- 新增管理员账号恢复接口 `POST /api/admin/customers/password`，用于 SMTP 未配置或用户无法收邮件时由管理员重置客户密码；响应和审计不回显明文密码。
- 新增独立 `FRIST_API_PASSWORD_HASH_SECRET` 和 `FRIST_API_LEGACY_PASSWORD_HASH_SECRETS`，避免公网修复会话密钥时让旧用户密码全部失效；旧哈希登录成功后自动迁移。
- 生产排查确认公网 `/api/frist/dashboard`、注册、登录和 Cookie 看板链路可用；腾讯云已替换默认管理令牌、开启 CSRF 并保留旧密码兼容。历史 runtime 已有 `enc:v1` 字段但缺原始加密密钥，暂不启用新的随机数据加密密钥，避免看板 500；后续需做一次性 runtime 明文迁移或找回原密钥后再启用公开模式数据加密。

### 文件变更
- `apps/frist-api/src/app.js` — 登录和找回密码反馈改为显示服务端真实错误。
- `apps/frist-api/server/server.js` / `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` — 增加管理员密码恢复接口和管理端入口。
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 透传独立密码哈希密钥和历史兼容密钥。
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖错误反馈和管理员恢复账号回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮登录恢复、接口注册、运维配置、生产兼容模式和健康记录。

## [2026-05-08] Frist-API 用户端视觉 QA 批注修复
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `CC Switch`, `Gateway Dashboard`, `docs`
> 关联问题: HI-883

### 变更内容
- 按 26 条浏览器批注重做用户端视觉细节：顶部状态灯改为带语义状态，新增中/英文切换，Logo 改为 Apple 风格的简洁 `F` 标识。
- 重新调整工作台导航间距和选中态，隐藏暂不运营的充值、邀请、独立配置教程入口；首页移除最近日志板块，日志统一到使用记录页查看。
- Token 趋势从难读日期堆叠改为 SVG 折线/面积趋势图；未登录 Dashboard 不再返回 `channelChecks`，避免把真实库存快照误认为 mock 数据。
- CC Switch 页面去掉重复 `Harmes`，顶部增加导入按钮，用量查询说明下移为教程，代码框复制改为框内图标按钮。
- Claude Code 教程改为“OpenAI 模型以 Claude 名称导入 Claude Code”的当前约束说明；用户端模型展示使用官方友好名称，不改真实内部模型 ID，避免影响路由。
- 测试台参考 OpenAI Web 端重排为模型选择侧栏、对话区和底部输入框；资料页重做为头像/昵称/邮箱可编辑布局，登录注册弹窗也同步调整。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 用户端导航、顶部、趋势图、CC Switch、测试台、资料页和登录弹窗视觉修复
- `apps/frist-api/src/core.js` / `apps/frist-api/server/server.js` / `apps/frist-api/src/serverClient.js` — 用户友好模型名、游客安静看板和导入配置展示边界
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖隐藏入口、去重目标、复制框、资料编辑、语言切换、游客 `channelChecks` 空态和登录态 SLA
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮视觉 QA 和入口注册表

## [2026-05-07] Frist-API New-API 生产边界硬门槛
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Gateway`, `New-API`, `docs`
> 关联问题: HI-882

### 变更内容
- 新增生产强制边界开关 `FRIST_API_ENFORCE_PRODUCTION_READINESS`：正式模式会检查固定 HTTPS 品牌域名、New-API 数据库、管理员 2FA、真实支付商户、备份监控和渠道 SLA 状态，缺核心项时阻止启动。
- 管理端新增 TOTP 2FA 验证入口和 `/api/admin/2fa/verify`；启用 `FRIST_API_REQUIRE_ADMIN_2FA=1` 后，管理 API 必须先通过二次验证。
- 新增 `/api/admin/production-readiness` 和 `/api/admin/backups/status`，用于登记备份/恢复演练并在管理端展示生产边界状态。
- 渠道健康从“当前库存快照”升级为可持久化 SLA 事件：成功、慢线、失败和额度耗尽会写入 `channelProbeEvents`，Dashboard 返回 7/15/30 天窗口摘要。
- 生产环境模板和 Compose 透传 `FRIST_API_REQUIRE_NEWAPI_DATABASE`、管理员 2FA、备份新鲜度、SLA 保留天数等变量。

### 文件变更
- `apps/frist-api/server/server.js` — 生产硬门槛、TOTP 管理员 2FA、备份状态、SLA 事件和 readiness API
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 管理端 2FA 输入和生产检查面板
- `apps/frist-api/tests/server.test.mjs` — 覆盖生产边界、管理员 2FA、备份状态和真实 SLA 事件
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 登记生产变量和强制边界开关
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步生产边界、环境变量和剩余外部操作

## [2026-05-07] Frist-API 用户与管理闭环实机验收
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `User Console`, `Admin`, `Gateway`, `docs`
> 关联问题: HI-881

### 变更内容
- 用户侧把 `ChatGPT / OpenAI` 展示统一收敛为 `OpenAI`，并在 CC Switch 页新增“导入后检测闭环”：供应商卡片、用量脚本、真实调用、`gpt-image-2` 流程图测试和记录页消费回写。
- 管理侧新增号池首次使用流程和渠道诊断：管理员只需要填端点、粘 Key、写入库存；页面按模型组汇总可用/断开/降级、最快延迟、失败原因和模型清单，方便判断哪个渠道断了。
- Dashboard 新增轻量异常消耗检测，覆盖今日消耗接近余额、单次调用费用突增和高延迟请求；响应只返回用户可读摘要，不泄露上游 Key、供应商原始地址或 raw usage。
- 受控实机验收使用临时 runtime 和本地 mock 上游完成：登录、创建 `fk-live-*` Key、CC Switch 导入链接含用量脚本、文本 `pong`、`gpt-image-2` 图片返回、记录页文本/图片消费、异常消耗提醒、`gpt-image-2` `1/2 可用` 降级状态。
- 修复异常消耗回归用例的阈值样本：模拟 usage 调整为真实会触发“今日消耗偏高”的大额调用，避免把业务规则放宽成假通过。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/styles.css` — 用户侧 OpenAI 命名、导入后检测闭环和异常消耗卡片
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 管理端号池小白流程、库存诊断和状态展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/newApiBridge.js` — Dashboard 和 New-API 桥接层输出轻量异常消耗摘要
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/new-api-adapter.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖导入检测、管理诊断、异常消耗和阈值回归
- `docs/006-registries.md` / `docs/009-health.md` — 登记本轮闭环能力和剩余生产边界

## [2026-05-06] Frist-API CC Switch 小白满血导入收尾
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude`, `Codex`, `OpenCode`, `OpenClaw`, `Hermes`, `docs`
> 关联问题: HI-880

### 变更内容
- 按 CC Switch 当前 `origin/main` 源码重新核对 provider/MCP deep link：供应商导入和 MCP 导入是两个 `resource`，一键供应商导入不能假装同时写入 MCP；页面改成“小白两步”：先导入供应商，再导入 MCP 增强包。
- MCP 增强包默认覆盖 CC Switch 当前支持的 `claude,codex,gemini,opencode,hermes`；页面明确说明 OpenClaw 供应商可导入，但 CC Switch 当前会忽略 OpenClaw MCP。
- 补充 CC Switch `prompt` / `skill` 资源边界：它们是独立 deep link 资源，不会随 provider 一键导入同时写入；没有公开 Skill 仓库时不生成虚假链接。
- 修复 `/api/frist/import-url` 用户显式选择模型时的导出不一致：服务端返回的默认模型、CC Switch 链接的 `model`、Codex `config.toml` 的 `model/default_model` 现在保持一致；未显式选择时仍默认最强可用模型。
- 保留 Codex 本地 `config.toml` 内联 Playwright/Superpowers/open-computer-use MCP；Claude、Gemini、OpenCode、Hermes 不再误塞 Codex TOML 段，而是使用单独的 CC Switch MCP deep link。
- 页面新增更直白的完整 Workflow：登录创建 Key、一键导入供应商、确认默认模型、测试用量查询、导入 MCP 增强包、复制终端测试命令；手动用户仍可复制 JSON/TOML、OpenCode provider 片段、用量脚本和 CLI 测试命令。

### 文件变更
- `apps/frist-api/src/core.js` — 增加服务端显式默认模型选项、全客户端 MCP deep link、Codex-only TOML MCP 内联和 CC Switch MCP 支持范围
- `apps/frist-api/server/server.js` — `/api/frist/import-url` 对服务端确认模型启用显式默认，避免导入链接和返回字段不一致
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — CC Switch 小白 Workflow、MCP 增强包、Prompt/Skill 边界和手动配置展示
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖全客户端 MCP deep link、OpenClaw MCP 边界和用户选择模型一致性
- `docs/006-registries.md` / `docs/009-health.md` — 登记 CC Switch 满血导入边界和本轮收尾状态

## [2026-05-06] Frist-API 86GameStore 号源接入与查询失败修复
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `CC Switch`, `Claude CLI`, `Codex CLI`, `docs`
> 关联问题: HI-879

### 变更内容
- 修复 CC Switch 用量查询“查询失败”：导出的 `usageScript.extractor.extra` 从对象改为字符串摘要，匹配当前 CC Switch provider 用量脚本解析契约，并增加回归断言。
- Claude 兼容入口优先走原生 Anthropic Messages `/v1/messages` 上游；如果上游不支持，再回退到 OpenAI Chat Completions 适配，避免 Claude CLI 导入后真实请求卡在适配层。
- 严格补号探测新增原生 Claude Messages 探测；对象形式补号 Key 未填 `modelGroup` 时继承补号单模型组；同一个上游 Key 作为 Claude/OpenAI 两组库存时按 `baseUrl + modelGroup + rawKey` 分开保存，避免后写覆盖先写。
- 本地 runtime 已接入 86GameStore 授权上游：Claude 组 `claude-sonnet-4-5-c`、`claude-opus-4-6-c` 为 healthy；OpenAI 组 `gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.5` 为 healthy。真实上游 Key 只在 ignored runtime 中以 `enc:v1:` AES-GCM 形式保存。
- 实测用户闭环：注册/登录、管理员入账、创建 Claude/OpenAI 用户 Key、`/v1/models`、导出 Claude/Codex CC Switch 链接、`/api/frist/key-usage`、Claude `/v1/messages`、Codex `/v1/responses` 均成功，真实请求返回 `pong` 并写入使用记录。
- 实测 CLI 闭环：Claude CLI 使用临时 settings 指向本地 Frist-API，`claude-sonnet-4-5-c` 返回 `pong`；Codex CLI 使用临时 `CODEX_HOME` provider，`gpt-5.4-mini` 返回 `pong`。测试未覆盖或改写用户原有 Claude/Codex 配置。
- 前端顶部连接状态修复为 Dashboard 成功后显示“已连接”，失败时显示“后端暂不可用”；浏览器刷新后确认不再长期停在“连接中”。

### 文件变更
- `apps/frist-api/src/core.js` — CC Switch 用量脚本字段类型修复、导出按模型组选择匹配用户 Key
- `apps/frist-api/server/server.js` — Claude 原生 Messages 路由和严格探测、同 Key 多模型组库存隔离、补号模型组继承、探测超时默认 8 秒
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/app.js` — 用户端连接状态成功/失败反馈收敛
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补 CC Switch 用量脚本、Claude 原生路由、原生探测、共享 Key 分组隔离、导出选 Key 和连接状态回归
- `apps/frist-api/deploy/production.env.example` / `docs/006-registries.md` / `docs/009-health.md` — 登记 8 秒探测超时、86GameStore 授权上游和本轮实测状态

## [2026-05-06] Frist-API 渠道状态监视器增强
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Channel Monitor`, `docs`
> 关联问题: HI-878

### 变更内容
- 参考 86GameStore `/monitor` 的用户侧监控形态，确认其公开页采用 `/channel-monitors`、7/15/30 天窗口、主模型延迟、endpoint ping、最近 60 点状态条和 30/60/120 秒自动刷新；本项目先按现有 runtime 库存能力落地“当前库存快照”，不伪造真实 7/15/30 天时间序列。
- Frist-API Dashboard 的 `channelChecks` 增加 `healthyCount`、`totalCount`、`downCount`、`slowCount`、`availability7d`、`availabilityWindow`、`successLabel`、`latencyLabel`、`averageLatencyMs`、`monitorIntervalSeconds`、`monitorStatus` 和 60 点 `history`，响应仍只暴露 `/v1`，不返回上游地址、上游 Key 或号商字段。
- 用户首页“通道”和趋势页“服务可用性”补齐状态标签、可用率、最低/平均延迟、最近检测、60 秒刷新口径和状态条；降级线路会用慢/失败状态点标记。
- 补充服务端、浏览器归一化和用户页面 wiring 回归，覆盖聚合监控字段、降级状态、当前快照口径和敏感字段不泄露。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/catalog.js` — 渠道监控聚合字段从单纯 healthy/total 扩展为可用率、降级、慢线、平均延迟和 60 点状态条
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/core.js` — 浏览器归一化和安全摘要支持新监控字段
- `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 用户侧通道摘要和服务卡增加状态标签、指标格和历史条
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/new-api-adapter.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖监控字段、降级状态、脱敏边界和页面钩子
- `docs/006-registries.md` / `docs/009-health.md` — 登记渠道监控口径和剩余真实时间序列技术债

## [2026-05-06] Frist-API CC Switch 用量查询一键导入与 CLI 实测闭环
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Bridge`, `User Console`, `docs`
> 关联问题: HI-877

### 变更内容
- 核对 CC Switch 官方 Deep Link 协议和本机 CC Switch 3.14.1 行为，确认当前 provider deep link 消费 `resource/app/name/homepage/endpoint/apiKey/model/*Model/notes/usage*` 字段；导入链接已收敛为官方短字段，不再塞旧 `config`、`availableModels` 等大块配置。
- `usageScript` 改为 Base64URL 编码，匹配 CC Switch 当前 `usage_script` 解码逻辑；语雀公开可读摘要中的“右侧用量查询、填入秘钥和 API”步骤已落到页面教程。
- CC Switch 导入链接现在同步写入自定义用量查询脚本，默认 15 分钟自动查询；脚本调用 Frist-API 自己的 `/api/frist/key-usage`，返回余额、已用额度、总额度、今日/本月消费、请求量、Token、延迟和成功率。
- 新增 `/api/frist/key-usage` 只读接口，用户 Key 通过 Bearer 或 `x-api-key` 鉴权；响应只返回脱敏统计，不返回用户完整 Key、上游 rawKey、供应商地址或号商信息。
- 修复 New-API 桥接层 `buildKeyUsage` 参数名遮蔽内部请求函数导致 500 的回归，并覆盖 New-API Token 查询、Dashboard、导入和网关代理闭环。
- DeepSeek 等模型组继续把模型请求地址导向官方兼容端点，但用量查询地址固定从 Frist-API 公开网关地址派生，避免余额脚本误打到 `api.deepseek.com`。
- 实机闭环：使用临时 Frist API 和本地受控上游生成真实 `fk-live-*` Key，CC Switch 日志确认收到并解析 `resource=provider/app=claude/name=Frist-API` deep link；因当前 CC Switch 窗口无可访问确认按钮，按官方导入结构等价写入临时 provider 后，`claude --bare --no-session-persistence --model claude-sonnet-4-5-c` 返回 `Frist API CLI OK`。测试后已恢复用户原 CC Switch/Claude 配置。

### 文件变更
- `apps/frist-api/src/core.js` — CC Switch 导入新增用量查询脚本、Base64URL 编码、短 deep link 字段和 Frist/API 上游地址解耦
- `apps/frist-api/server/server.js` / `apps/frist-api/server/newApiBridge.js` — 新增用户 Key 用量查询接口并修复 New-API 桥接回归
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — CC Switch 页面补“用量查询、启用、测试脚本、自动查询间隔”教程和状态文案
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖 deep link 用量字段、短链接契约、OpenCode 配置、New-API 用量接口和教程文案
- `docs/006-registries.md` / `docs/009-health.md` — 登记新接口、教程闭环和剩余真实客户端验收边界

## [2026-05-06] Frist-API 上线前安全闭环修复
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Runtime Store`, `Payments`, `User Console`, `docs`
> 关联问题: HI-876

### 变更内容
- 用户 API Key 新建前缀恢复为 `fk-live-*`，生成使用 `crypto.randomBytes(32).toString('base64url')`，校验统一走恒定时间比较，Dashboard 刷新后不再返回明文 Key。
- Cookie 登录态的非幂等接口增加 CSRF Token 校验；注册/登录返回 CSRF Token 并设置 `frist_csrf` Cookie，浏览器客户端自动带 `x-csrf-token`。
- 微信/支付宝回调入账前校验实付金额和订单金额；少付通知拒绝入账，重复通知仍按订单号幂等处理。
- 管理端补号 URL 增加 SSRF 防护，默认拒绝 localhost、私网、link-local 和云 metadata 地址，测试环境可显式注入解析器。
- runtime 写入改为临时文件 fsync 后 rename，写入失败发出 `FRIST_API_RUNTIME_WRITE_FAILED` warning；共享脱敏和 CORS 头同步支持 `fk-live-*` 与 `x-csrf-token`。
- 生产模板补齐 `FRIST_API_REQUIRE_CSRF`、`FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS`，公网网关示例恢复为 HTTPS 占位域名，避免生产硬门槛被 HTTP 示例误导。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/newApiBridge.js` — Key 生成和脱敏、CSRF、SSRF、金额校验、runtime 原子写和 CORS 头
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/app.js` / `apps/frist-api/src/newApiClient.js` — 浏览器 CSRF 头、创建后一次性显示 Key、刷新后不依赖明文 Key
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖 `fk-live-*`、CSRF、少付回调、SSRF 阻断和用户侧不泄露明文 Key
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 登记生产 CSRF 和 SSRF 开关，修正公网 HTTPS 示例
- `docs/006-registries.md` / `docs/009-health.md` — 同步生产变量和上线前剩余风险

## [2026-05-05] Frist-API 用户端深色体验和官方计价修复
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Gateway Billing`, `docs`
> 关联问题: HI-875

### 变更内容
- 用户首页最近日志改为 5 条内的精简事件，过滤管理认证失败等噪音；使用记录页补充客户端、费用、延迟和 Token，让广场、MacBook、PC 等来源能分开看。
- API Key 展示曾短暂改为通用 `sk-*`；2026-05-06 已按安全审计恢复为新建 `fk-live-*`、兼容旧 `sk-*`。
- 测试页减少解释文字、修复深色气泡对比度，模型连通改为 3 分钟自动检测一次；顶部和局部反馈改为短动效状态，不再显示塑料感长文案。
- 模型价目表按官方输入、缓存输入/缓存读写、输出口径统一展示；覆盖 OpenAI、Claude、DeepSeek、Gemini 和图片模型。
- 账单页前置展开兑换码，预警邮箱只遮罩展示；邀请改为“消费才返利”，返利上限为受邀方首次充值金额 5%；资料页支持修改昵称和邮箱。
- 深色控制台逐页补齐对比度护栏，修复 API 页面布局闭合标签，消费后自动刷新余额。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260505-211636-before-ux-deploy.tgz`，运行数据备份为 `backups/frist-api-runtime-20260505-211636-before-ux-deploy.tgz`；`frist-api-server` 为 healthy，公网首页和看板均返回 200，裸域名返回 301 到品牌入口，未授权 `/v1/models` 保持 401。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` — 深色控制台、兑换码前置、API 页面布局和对比度修复
- `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` — 日志降噪、测试页降噪、余额刷新、反馈动效、资料/邀请/预警展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` — Key 展示、记录字段、价目表、消费扣费和余额刷新数据
- `apps/frist-api/deploy/smoke-test.sh` — 冒烟脚本兼容中文管理工作台和可关闭验证码场景
- `apps/frist-api/tests/*.test.mjs` — 覆盖 Key 前缀、日志/记录、官方价格、深色 UI 入口和自动测试
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮修复

## [2026-05-05] Frist-API inroi 授权上游号池检测
> 领域: `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `AI Pool`, `Admin`, `docs`
> 关联问题: HI-874

### 变更内容
- 核对 `https://www.inroi.shop/v1` 是上游请求地址，不是 Frist-API 对外入口；Frist-API 公网入口仍按 `frist-api.101-43-41-96.nip.io` 收口，裸域名只做 301。
- 远端管理接口检测到同一 Key 的旧根地址记录 `https://www.inroi.shop` 已是 `exhausted/enabled=false`，不可路由；正确请求地址 `https://www.inroi.shop/v1` 已加入号池并处于 `healthy/enabled=true`。
- 已实测 inroi 上游 `/v1/models` 返回 21 个模型，`gpt-5.4-mini` Chat Completions 返回 200；真实 Key 只通过服务器管理 API 写入远端加密 runtime，不进入 Git 或文档正文。

### 文件变更
- `docs/006-registries.md` / `docs/009-health.md` — 同步 inroi 授权上游检测状态

## [2026-05-05] Frist-API 公网入口收口
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Nginx`, `Public Gateway`, `docs`
> 关联问题: HI-873

### 变更内容
- 将 Frist-API 唯一内容入口统一为 `frist-api.101-43-41-96.nip.io`，避免 `101-43-41-96.nip.io` 被误认为第二个网站。
- Nginx 配置改为品牌域名反代到 Frist-API 服务，裸域名只返回 301 到品牌域名。
- Node 服务增加应用层兜底跳转，绕过 Nginx 或未来反代配置变更时也不会直接渲染裸域名页面。
- 生产环境模板新增 `FRIST_API_CANONICAL_HOST` 和 `FRIST_API_REDIRECT_HOSTS`，导出和邮件公网地址统一到品牌域名。
- Docker Compose 透传 canonical/redirect 环境变量，确保公网容器重启后仍按唯一入口策略运行。

### 文件变更
- `apps/frist-api/server/server.js` — 增加 canonical host 和裸域名 301 兜底
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/nginx.conf` / `apps/frist-api/deploy/production.env.example` — 收口公网入口和环境变量模板
- `apps/frist-api/tests/server.test.mjs` — 覆盖裸域名 301 和品牌域名正常服务
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步唯一入口、运维步骤和健康状态

## [2026-05-05] Frist-API CC Switch 导出模型与品牌标复原
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Bridge`, `docs`
> 关联问题: HI-872

### 变更内容
- 修复用户在 `#switch` 页面看不到 `gpt-5.4`、`gpt-5.4-mini`、`gpt-image-2`、`gpt-5.3-codex` 的问题：OpenAI 家族导出清单现在会补齐官方完整模型集，不再被部分上游库存或桥接层裁掉。
- CC Switch 导出预览和 New-API 桥接层都改用同一套可见模型展开逻辑，保证 `/api/frist/import-url`、`ccswitch://` 和手动配置看到的是同一份完整模型表。
- 恢复 Frist-API 品牌标识为原黑红白 logo，Tabcode 皮肤只保留布局和对比度，不再把品牌标改成灰白抽象块。
- 给导出模型 chip 和相关回归补上测试门槛，防止以后再把核心模型藏掉。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 OpenAI 官方模型族展开和统一可见模型归一化
- `apps/frist-api/src/app.js` — CC Switch 导出清单改为强制显示完整模型集
- `apps/frist-api/server/newApiBridge.js` / `apps/frist-api/server/server.js` — 桥接层与服务端导出链路同步完整模型集
- `apps/frist-api/src/styles.css` — 恢复品牌标视觉并强化导出 chip 可读性
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补回归
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮修复

## [2026-05-05] Frist-API Tabcode 皮肤对比度修复
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `CC Switch`, `docs`
> 关联问题: HI-871

### 变更内容
- 修复 Tabcode 浅色控制台里旧深色皮肤残留导致的黑底灰字问题，重点覆盖 CC Switch 目标按钮、返回按钮、代码栏复制按钮、测试页删除按钮和分段选中态。
- 静态资源版本号切到 `20260505-contrast-fix`，避免浏览器继续命中旧 CSS 缓存。
- 增加 Tabcode 对比度护栏：主按钮/选中态统一黑底白字，普通按钮统一白底深字，深色代码栏内复制按钮使用白底深字。
- 浏览器实测用户端 6 个主路由和管理端可见交互元素低对比扫描均为 0；桌面和 390px 移动端截图已验证。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 更新 CSS/JS 资源版本号
- `apps/frist-api/src/styles.css` — 增加 Tabcode 对比度护栏和可读性颜色修复
- `apps/frist-api/tests/core.test.mjs` — 补充对比度护栏和资源版本回归断言
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮 UI 修复

## [2026-05-05] Frist-API CC Switch 导出和运行遗留项收尾
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Admin`, `Runtime Store`, `docs`
> 关联问题: HI-870

### 变更内容
- 参考本机 CC Switch 已导入的 Tabcode Claude/Codex 配置，把一键导入补齐为 New-API 基础深链字段 + Tabcode 真实 `settings_config` 落库结构。
- Claude 导出写入 `ANTHROPIC_AUTH_TOKEN` 和不带 `/v1` 的 `ANTHROPIC_BASE_URL`；Codex 导出写入 `OPENAI_API_KEY` 和 Responses `config.toml`，同时保留完整模型清单、MCP 和现有扩展字段。
- 用户点击 `ccswitch://` 导入时自动复制链接并显示短降级反馈，浏览器未弹出 CC Switch 时仍可粘贴导入。
- 管理 API 认证失败会写入脱敏审计事件；runtime 写入失败会发出 Node warning，不再静默吞掉；CLI 启动增加 SIGTERM/SIGINT 优雅关闭。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 CC Switch `settingsConfig/settings_config` 和 New-API 基础字段兼容
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 增加 CC Switch 协议降级反馈和自动复制
- `apps/frist-api/server/server.js` — 增加管理失败审计、runtime 写入告警和优雅关闭
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补齐 CC Switch 导出契约、管理失败审计和运行遗留项回归
- `docs/006-registries.md` / `docs/009-health.md` — 同步入口和健康状态

## [2026-05-05] Frist-API Plus 金额审计修复
> 领域: `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Plus Ledger`, `docs`
> 关联问题: HI-869

### 变更内容
- 全量审计时发现 Plus 账号台账的 TRY 余额/月费如果收到异常数字输入，可能把 `NaN` 带入运行数据和摘要。
- 后端新增有限数字归一化，异常金额统一落为 0，避免管理响应出现 `null` 或污染 Plus 摘要。
- 回归测试补充异常金额输入断言，确保 Plus 敏感字段仍脱敏且金额字段稳定返回数字。

### 文件变更
- `apps/frist-api/server/server.js` — Plus 台账金额改用有限数字归一化
- `apps/frist-api/tests/server.test.mjs` — 补充异常 TRY 金额回归覆盖
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮审计修复

## [2026-05-05] Frist-API Tabcode Console 设计吸收
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `docs`
> 关联问题: HI-868

### 变更内容
- 参考本地 Tabcode Dashboard 克隆，把 Frist-API 用户端和管理端切换为 `tabcode-console`：54px 白色顶栏、160px 灰色侧栏、灰色工作区、14px 白色卡片、轻阴影和黑色主按钮。
- 移除上一版设计皮肤入口和 CSS 残留，图表配色从蓝色体系改为中性黑灰加状态色，登录弹窗改为 Tabcode 两栏桌面布局并保留移动端可滚动关闭。
- 管理端仅替换视觉壳，不删管理功能；New-API/价格/入账/卡密/Plus/RT/接入/订单/库存/审计等原有入口继续保留。
- 性能优化继续保留 `content-visibility`、隐藏面板跳过渲染、搜索防抖、模型目录缓存和测试台局部渲染，避免控制台高频切换时反复重绘。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 设计系统标记和静态资源版本切到 Tabcode Console
- `apps/frist-api/src/styles.css` — 删除旧设计皮肤，新增 Tabcode Console token、布局、卡片、表格、弹窗和移动端规则
- `apps/frist-api/src/app.js` — 图表颜色切到中性控制台色系
- `apps/frist-api/tests/core.test.mjs` — 回归断言切到 Tabcode Console 视觉 token 和旧皮肤移除
- `docs/006-registries.md` / `docs/009-health.md` — 同步设计系统登记和健康状态

## [2026-05-05] Frist-API Refero Apple UI 降噪
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `docs`
> 关联问题: HI-867

### 变更内容
- 参考 Refero Styles 的 Apple 高热样式，把 Frist-API 用户端和管理端从深色 Hyperstudio 壳切到浅色 Apple 控制台：`#f5f5f7` 画布、白色面板、`#0071e3` 主操作、弱边界和短状态动效。
- 用户端以“前端入口”为准做降噪：首屏指标压到余额、Key、今日和成功率四项；导航把“仪表盘/广场/教程”等长标签改为“首页/测试/配置”，状态空态改为“无记录/未检测/离线”等短标签。
- 管理端保留价格、入账、卡密、Plus、RT、接入、订单、库存和审计等原有管理项，只压缩提示文案；New-API 管理侧能力没有减少。
- 性能上减少不必要渲染：模型目录缓存、测试台日志/图片签名复用、搜索输入防抖、面板 `content-visibility` 和克制状态动效，避免全量 DOM 反复重绘。

### 文件变更
- `apps/frist-api/index.html` — 精简用户端导航、状态、导入流程和兑换/邀请文案
- `apps/frist-api/admin.html` — 精简管理端说明文案，保留原管理区块和 RT JSON/TXT 入口
- `apps/frist-api/src/app.js` — 缩短空态/反馈文案，保留测试台和模型目录渲染缓存
- `apps/frist-api/src/admin.js` — 缩短管理端反馈和空态文案
- `apps/frist-api/src/styles.css` — 增加 Refero Apple final layer、状态微动效和 `content-visibility` 渲染优化
- `apps/frist-api/tests/core.test.mjs` — 回归断言切到 Refero Apple 视觉 token 与四指标首屏
- `docs/006-registries.md` / `docs/009-health.md` — 同步入口命名和健康状态

## [2026-05-04] Open Design 本机配置接入
> 领域: `infra` | `docs`
> 影响模块: `Codex Skills`, `Open Design`, `MCP`
> 关联问题: 无

### 变更内容
- 将 Open Design 克隆到 `/Users/blackdj/Desktop/open-design`，按官方要求启用 Node 24 和 pnpm 10.33.2，并完成依赖安装、daemon 构建和 Web 服务启动。
- 固定 Open Design 本机端口：Web 为 `http://127.0.0.1:17573`，daemon 为 `http://127.0.0.1:17456`，便于后续稳定接入 Codex。
- 在 `~/.codex/config.toml` 新增只读 `open-design` MCP server，让 Codex 后续能读取当前 Open Design 项目/文件/Artifact。
- 新增 Codex skill `~/.codex/skills/open-design`，记录启动、诊断、MCP 使用和把 Open Design 产物落地到项目 UI 的工作流。

### 文件变更
- `~/.codex/config.toml` — 新增 `mcp_servers.open-design`
- `~/.codex/skills/open-design/SKILL.md` — 新增 Open Design 使用工作流
- `~/.codex/skills/open-design/references/local-setup.md` — 记录本机路径、端口、启动命令和验证命令

## [2026-05-04] Frist-API RT JSON 批量导入管理
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `New-API`, `AI Pool`, `docs`
> 关联问题: HI-866

### 变更内容
- 参考 New-API Codex OAuth 与 Grok 给出的 RT JSON 格式，在 Frist-API 管理端新增 Refresh Token 账号池，支持 JSON 数组、单个 JSON 对象和 TXT 每行一个 RT 的导入方式。
- 管理侧是在原有 New-API/补号/价格/卡密/Plus/审计内容上增量增加，原有管理入口不减少；RT 默认只作为后台台账和刷新准备，不直接进入用户 `/v1` 路由库存。
- 后端新增 `/api/admin/rt-accounts` 和 `/api/admin/rt-accounts/import`，导入后只返回脱敏邮箱、账号 ID、RT 预览和指纹；`refreshToken` 纳入 runtime AES-GCM 加密字段。
- 回归覆盖 JSON/TXT 导入、重复 RT 更新、明文 RT/账号 ID 不出现在管理响应和落盘文件、RT 台账不污染可售上游 Key 库存。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/src/admin.js` 通过；聚焦 `node --test tests/business-flow.test.mjs tests/server.test.mjs` 为 85/85 通过；Frist-API 全量 `npm test` 为 125/125 通过；`git diff --check` 通过。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 RT 台账模型、导入解析、管理 API、脱敏展示、摘要和加密字段
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 新增管理端 RT 导入区块、摘要和脱敏列表
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖用户端隔离和 RT 导入安全边界
- `docs/006-registries.md` / `docs/009-health.md` — 同步管理入口和健康状态

## [2026-05-04] Frist-API Plus 自用账号台账入口
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `AI Pool`, `docs`
> 关联问题: HI-865

### 变更内容
- 参考 Grok 方案后收敛边界：新增“ChatGPT Plus 自用账号台账”，只管理自有 Plus 账号资产、续费日期、TRY 余额、设备/Profile 和合规状态，不做自动登录、不导出密码、不接入用户 `/v1` 路由。
- 管理端新增 Plus 账号登记/编辑表、摘要指标和账号列表，支持状态、合规、地区、到期和余额展示。
- 后端新增 `/api/admin/plus-accounts` 管理接口，返回数据统一脱敏；Plus 密码备注纳入 runtime 敏感字段加密，`/api/admin/replenishments` 可同时返回 Plus 台账摘要但不会污染上游 Key 库存。
- 回归覆盖 Plus 台账不会泄露邮箱明文/密码备注、不会生成可路由库存，避免把 Plus 账号误当作售卖 API 号源。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 Plus 账号台账模型、管理 API、脱敏展示、到期摘要和加密字段
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 新增管理端 Plus 台账入口、表单、摘要和列表样式
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖管理端入口和 Plus 台账安全边界
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步入口、运营规则和健康状态

## [2026-05-04] Frist-API 兑换码售卖主链路
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Billing`, `Redeem`, `Admin`, `docs`
> 关联问题: HI-864

### 变更内容
- 放弃个人微信/支付宝收款码自动识别路线，避免收款风险和用户上传截图的糟糕体验；用户端主路径改为“第三方平台购买兑换码，站内核销自动到账”。
- 管理端新增兑换卡批量生成、批次导出、卡密状态展示，生成内容可直接给闲鱼自动发货或客服系统使用。
- 后端新增运行数据里的 `redemptionCards` 库存，兑换码一次性核销，成功后绑定用户并标记已兑换；旧测试兑换码继续兼容。
- 用户端充值页改为购买兑换码引导，独立兑换码页突出自动到账，并预留闲鱼商品链接位置。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-152551-before-redemption-codes.tgz`，运行数据备份为 `backups/runtime-20260504-152551-before-redemption-codes.json`；公网首页 200，游客看板返回 5 个套餐和 11 个模型，未授权 `/v1/models` 为 401，容器为 healthy，远端真实生成/兑换/重复兑换拒绝闭环通过。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/src/admin.js apps/frist-api/src/app.js` 通过；Frist-API `npm test` 为 123/123 通过；聚焦 `node --test tests/core.test.mjs tests/business-flow.test.mjs tests/server.test.mjs` 为 114/114 通过；`git diff --check` 通过。

### 文件变更
- `apps/frist-api/server/server.js` — 新增兑换卡生成接口、卡密库存、一次性核销和管理端脱敏展示
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` — 新增卡密生成、复制导出和卡密状态列表
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 充值页和兑换页改为闲鱼兑换码主路径并预留购买链接
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖用户端入口、管理端钩子和卡密一次性兑换
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步兑换码售卖 SOP 和健康状态

## [2026-05-04] Frist-API 支付回调、邮箱找回和运行数据加密
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Payments`, `Auth`, `New-API Migration`, `docs`
> 关联问题: HI-850, HI-853, HI-859, HI-863

### 变更内容
- 注册流程接入 SMTP 验证码邮件，继续保留公开模式不回显验证码；新增忘记密码请求和确认接口，验证码过期后不可复用。
- 充值链路新增微信支付 Native 和支付宝当面付预创建下单；微信/支付宝异步通知完成验签、解密和按订单号幂等入账，重复回调不会重复加钱。
- 充值页补充人工确认、微信 Native、支付宝当面付三种支付方式选择；接口未配置时会明确提示，不会误导用户已经自动入账。
- Frist-API runtime JSON 增加 AES-256-GCM 字段加密，保护用户 `fk-live-*` Key 和上游 `rawKey`，兼容旧明文文件读取并在保存时迁移为密文。
- 新增 New-API 迁移 dry-run 脚本，先只输出用户、Token、订单、日志和风险提示，不默认写入生产 New-API。
- 免费域名公网实测后，将过渡入口从被腾讯 DNSPod 拦截的 `sslip.io` 切到当前可用的 `frist-api.101-43-41-96.nip.io`；Let’s Encrypt 验证被 connection reset 拦住，HTTPS 仍建议后续走自有域名或 Cloudflare Tunnel。
- Docker Compose 和生产环境模板新增邮箱找回、运行数据加密、微信支付、支付宝支付相关环境变量。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/server/payments.js apps/frist-api/src/app.js apps/frist-api/src/serverClient.js scripts/frist_api_newapi_migration_dry_run.mjs` 通过；Frist-API `npm test` 为 123/123 通过；`git diff --check` 通过；New-API 迁移 dry-run 空数据验证通过。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/payments.js` — 接入支付下单、回调验签/解密、幂等入账、邮箱验证码/找回密码和 runtime 字段加密
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/styles.css` — 补齐忘记密码入口、支付方式选择和支付反馈
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/core.test.mjs` — 覆盖邮箱、支付、幂等、加密、公开模式配置和前端入口
- `scripts/frist_api_newapi_migration_dry_run.mjs` — 新增 New-API 迁移演练报告脚本
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 登记新增生产环境变量
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步新接口、支付回调、域名方案和剩余运维风险

## [2026-05-04] Frist-API 仓库清理与离线恢复体验
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `docs`
> 关联问题: HI-862

### 变更内容
- 补齐后端不可用时的用户恢复路径：工作台显示“后端暂不可用”恢复条，说明当前为空数据模式，并提供一键重新连接按钮。
- 重新连接按钮复用现有 Dashboard 加载链路，成功后自动隐藏恢复条，失败时保留明确错误提示。
- 同步 Frist-API Web 操作注册表、快速启动文档和 HEALTH，并修正系统健康摘要接口的新版文档路径，避免文档和接口仍指向已删除的旧编号文件。

### 文件变更
- `apps/frist-api/index.html` — 增加后端恢复提示和重新连接入口
- `apps/frist-api/src/app.js` — 增加离线恢复条渲染和重试逻辑
- `apps/frist-api/src/styles.css` — 增加恢复提示的桌面/移动样式
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加离线恢复体验回归钩子
- `packages/clawbot/src/api/routers/system.py` — 健康摘要读取新版 `docs/009-health.md`
- `docs/005-quickstart.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步操作入口、文档路径和健康状态

## [2026-05-04] Frist-API DeepSeek 官方模型对齐
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `DeepSeek`, `docs`
> 关联问题: HI-858, HI-861

### 变更内容
- 用 DeepSeek 官方 live 文档重新核对 Codex DeepSeek 导入逻辑：官方 OpenAI 兼容入口继续可使用 `https://api.deepseek.com/v1`，但默认模型已不应继续锁定旧 `deepseek-chat`。
- 将 DeepSeek 新导入默认模型改为 `deepseek-v4-flash`，并把 `deepseek-v4-pro` 加入 DeepSeek 模型清单；`deepseek-chat` / `deepseek-reasoner` 继续保留为旧配置兼容，避免已有导入立刻失效。
- 同步 Workbench 模型目录、CC Switch 指引、New-API 桥接默认模型和服务端默认目录，避免前端、后端、桥接层显示不同模型。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-104527-before-deepseek-v4.tgz`；公网首页 200，游客看板 200，模型目录包含 `deepseek-v4-flash`，未授权 `/v1/models` 仍为 401，容器为 healthy。
- 验证结果: `node --check src/core.js src/app.js src/admin.js server/server.js server/shared.js server/newApiBridge.js` 通过；聚焦 `node --test tests/core.test.mjs tests/server.test.mjs` 为 90/90 通过；Frist-API `npm test` 为 118/118 通过；`make new-api-check` 确认 New-API 仍同步到 GitHub latest `v1.0.0-rc.2`。

### 文件变更
- `apps/frist-api/src/core.js` — DeepSeek 默认模型和强度排序改为 v4 优先，保留旧模型兼容
- `apps/frist-api/src/app.js` / `apps/frist-api/index.html` — 同步前端模型目录和 Codex DeepSeek 指引
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/newApiBridge.js` — 同步服务端目录、探测候选和 New-API 桥接默认模型
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖新默认模型和旧模型兼容
- `docs/009-health.md` / `docs/007-operations.md` — 同步审计结论和仍需真实 DeepSeek Key 实测的闭环项

## [2026-05-04] Frist-API 用户体验与安全审计修复
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Auth`, `Workbench UI`, `docs`
> 关联问题: HI-850, HI-851, HI-852, HI-860

### 变更内容
- 明确本轮审计范围为 `apps/frist-api` 模块、New-API 同步桥接、部署配置和用户实际路径；不将其描述为 OpenEverything 全仓所有模块审计。
- 将 Frist-API 新注册和改密密码从 SHA-256 迁移为 Node 内置 PBKDF2-SHA256 慢哈希；历史 SHA-256 用户登录成功后自动升级哈希，不新增依赖、不要求一次性数据库迁移。
- HTTPS 公网网关或反向代理 HTTPS 请求下，注册和登录 Session Cookie 自动增加 `Secure`，继续保留 `HttpOnly` 和 `SameSite=Lax`。
- 删除未使用的旧 SHA-256 密码哈希导出，减少后续维护时误用旧逻辑的风险。
- 补齐用户端和管理端动态 `innerHTML` 字段转义，覆盖管理端库存摘要/审计日志、用户端 API Key 属性、充值套餐、导入目标、进度条百分比等位置。
- 使用 GitHub live API 和 `make new-api-check` 确认 New-API 当前 latest release、本地 submodule 和 Compose 镜像均为 `v1.0.0-rc.2`。
- 验证结果: Frist-API `npm test` 116/116 通过；聚焦回归 `node --test tests/business-flow.test.mjs tests/server.test.mjs` 79/79 通过；语法检查和 `git diff --check` 通过；公网游客看板返回 11 个模型目录、9 个渠道检查并包含 DeepSeek。

### 文件变更
- `apps/frist-api/server/server.js` — 增加 PBKDF2 密码哈希、旧哈希登录迁移和 HTTPS `Secure` Cookie
- `apps/frist-api/server/shared.js` — 移除未使用的旧 SHA-256 密码哈希导出
- `apps/frist-api/src/app.js` — 补齐动态 HTML 转义和百分比钳制
- `apps/frist-api/src/admin.js` — 补齐管理端库存摘要与审计日志转义
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 增加密码哈希迁移、Cookie Secure 和 HTML 转义回归
- `docs/009-health.md` — 同步已修复问题和仍需闭环的架构缺口

## [2026-05-04] Frist-API 模型测试台按 New-API 控制台逻辑重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `Playground`, `Model Catalog`, `docs`
> 关联问题: HI-858

### 变更内容
- 参考 New-API 的 Playground、模型目录和使用记录页面组织方式，把 Frist-API 广场从单一下拉聊天框改为“模型浏览器 + 当前模型详情 + 连通诊断 + 测试台”。
- 模型选择恢复搜索、分组筛选、可用状态、供应商、端点类型和计费信息展示，避免用户误以为只剩少量模型。
- 模型广场增加搜索框和一键跳转测试台，模型卡片可直接选择测试或复制模型名。
- 保留 Refero 深色工作台视觉和 Frist-API 的 CC Switch / Codex / DeepSeek 特色，不改网关计费、路由和 New-API 桥接业务逻辑。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-090503.tgz`；公网模型测试台返回 12 行模型入口，游客看板返回 11 个模型目录和 9 个服务检查，未授权 `/v1/models` 仍为 401。
- 验证结果: `node --check apps/frist-api/src/app.js apps/frist-api/src/admin.js apps/frist-api/server/server.js` 通过；Frist-API `npm test` 114/114 通过；`git diff --check` 通过；Playwright 桌面/390px 移动端截图无横向溢出。

### 文件变更
- `apps/frist-api/index.html` — 重构广场布局，新增模型浏览器、诊断区、快捷提示和模型目录搜索
- `apps/frist-api/src/app.js` — 增加模型筛选、选择、状态摘要和测试台诊断渲染
- `apps/frist-api/src/styles.css` — 增加测试台、模型行、当前模型面板和响应式样式
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` — 覆盖 New-API 风格模型选择和测试台 UI 钩子

## [2026-05-04] Frist-API Refero 风格控制台 UI 改造
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `Workbench UI`, `docs`
> 关联问题: HI-858

### 变更内容
- 借鉴 Refero Hyperstudio 风格，把 Frist-API 用户端和管理端统一为深色控制台视觉：黑色画布、琥珀重点、绿色可用状态、8px 圆角和更克制的层级阴影。
- 保留现有前端路由和业务逻辑，仅通过 `data-design-system="refero-hyperstudio"`、CSS token 和可复用组件类调整整体 UI 壳。
- 首页模型消耗、渠道连通、最近日志、模型目录、使用记录和 API Key 列表增加生产可用空态；数据加载阶段增加骨架行和 `aria-busy`。
- 使用记录页额外增加表格外独立空态，避免小屏首次访问时只看到横向滚动表格里的截断提示。
- 静态预览或后端返回非 JSON 时，不再把 `Unexpected token` 这类技术错误直接暴露给用户，统一提示后端暂不可用并保留空数据壳。
- 工作台导航增加 `aria-current="page"`，Token 趋势条增加 `role="img"` 与描述标签，继续保留跳转主内容和可见焦点态。
- 验证结果: `node --check apps/frist-api/src/app.js` 通过；Frist-API `npm test` 114/114 通过。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 接入 Refero 风格设计系统标记、缓存版本和初始加载语义
- `apps/frist-api/src/styles.css` — 新增深色控制台设计 token、按钮/卡片/表格/图表/空态/骨架屏可复用样式
- `apps/frist-api/src/app.js` — 增加加载态、空态、当前页无障碍状态和图表可访问标签
- `apps/frist-api/tests/core.test.mjs` — 增加 Refero 风格、加载态和可访问性回归钩子
- `docs/006-registries.md` / `docs/009-health.md` — 同步 Frist-API UI 状态和入口说明

## [2026-05-03] Frist-API 登录验证码与 CC Switch 体验修正
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Playground`, `docs`
> 关联问题: HI-855, HI-858

### 变更内容
- 登录接口移除验证码校验，保留 IP 频率限制；注册继续要求验证码挑战。
- 注册验证码从简单加法改为多题型挑战，支持字符位置、倒序、数字抽取和混合算式，并限制单个挑战错误次数。
- 账户弹窗只在注册模式显示验证码，切回登录会清空验证码状态。
- 工作台左侧导航移除数字编号，只保留清晰页面名称。
- 广场输入框支持 Enter 直接发送，Shift+Enter 保留换行。
- CC Switch 页面压缩冗余文字，突出 Claude 不带 `/v1`、Codex 必须带 `/v1` 等关键点，并把流程图里的 Codex 终端配置改为可复制。
- 腾讯云 `/opt/frist-api` 已部署本轮改动，远端代码备份为 `backups/frist-api-app-20260504-073450.tgz`，运行数据备份为 `backups/runtime-20260504-073450.json`；目标测试账号总可用额度已校准为 `$1000.00`。
- 验证结果: 本地 Frist-API `npm test` 114/114 通过；语法检查和 `git diff --check` 通过；Playwright 桌面/移动检查登录验证码、注册挑战、CC Switch 页面和移动端横向溢出通过；远端本机/公网首页 200，验证码接口正常，未授权 `/v1/models` 401，容器 `healthy`。

### 文件变更
- `apps/frist-api/server/server.js` — 调整登录/注册验证码策略并增强验证码挑战
- `apps/frist-api/index.html` — 移除侧栏编号，重构 CC Switch 教程重点和可复制终端块
- `apps/frist-api/src/app.js` — 登录免验证码、注册专用验证码、广场 Enter 发送和流程图复制交互
- `apps/frist-api/src/styles.css` — 优化 CC Switch 布局密度、重点标红和导航样式
- `apps/frist-api/tests/*.mjs` — 覆盖注册验证码、登录免验证码、侧栏编号移除、广场 Enter 发送和 CC Switch 可复制终端
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 登记验证码错误次数配置
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步入口、生产配置和健康状态

## [2026-05-03] Frist-API 接入 New-API 业务桥接与定时同步
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Frist-API`, `New-API`, `CC Switch`, `Docker Compose`, `GitHub Actions`, `docs`
> 关联问题: HI-859

### 变更内容
- 新增 GitHub Actions 定时同步任务，每天检查 `QuantumNous/new-api` 最新非草稿 release；若 submodule 或 compose 镜像落后，自动执行 `make new-api-sync` 并创建同步 PR。
- 新增 Frist-API 服务端 New-API 桥接层，启用后由 New-API 承接用户看板、API Key 创建/禁用/删除、兑换码、使用日志、订阅/充值/邀请读取和可选 `/v1` 网关代理。
- 保留 Frist-API 自研账号壳、Workbench UI、CC Switch/Codex/OpenCode/OpenClaw/Hermes 导入、DeepSeek 官方 API 配置、余额预警、补号助手和本地 JSON 兜底；New-API 未启用或不可用时仍走原逻辑。
- Docker Compose 和生产环境模板新增 `FRIST_API_NEWAPI_*` 配置，真实 token、用户 ID 和服务器密钥只允许放服务器环境变量，不写入仓库。
- Codex + DeepSeek 闭环继续保持官方 OpenAI 兼容端点 `https://api.deepseek.com/v1`，测试覆盖 CC Switch 导入配置、`auth.json`、`config.toml` 和 `/v1/responses` 网关代理。
- 验证结果: Frist-API `npm test` 113/113 通过；聚焦 New-API/Codex 回归 5/5 通过；`make new-api-check` 确认当前仍为最新 `v1.0.0-rc.2`；`docker compose -f docker-compose.newapi.yml config` 通过。

### 文件变更
- `.github/workflows/new-api-sync.yml` — 新增 New-API 定时同步 PR 自动化
- `apps/frist-api/server/newApiBridge.js` — 新增 New-API 业务桥接层
- `apps/frist-api/server/server.js` — 接入桥接层，保留本地业务逻辑兜底
- `apps/frist-api/tests/server.test.mjs` — 覆盖 New-API dashboard/token/import/gateway 闭环
- `docker-compose.frist-api.yml` — 透传 `FRIST_API_NEWAPI_*` 环境变量
- `apps/frist-api/deploy/production.env.example` — 登记 New-API 生产配置模板
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步注册表、运维 SOP 和系统状态

## [2026-05-03] New-API 最新版升级与 Git 同步机制
> 领域: `backend` | `infra` | `docs`
> 影响模块: `New-API`, `Frist-API`, `ClawBot API`, `Docker Compose`, `docs`
> 关联问题: HI-859

### 变更内容
- 将 `QuantumNous/new-api` 作为 Git submodule 引入 `packages/new-api-upstream`，当前固定到最新 release `v1.0.0-rc.2`。
- `docker-compose.newapi.yml` 从 `calciumion/new-api:v0.12.6` 升级到 `calciumion/new-api:v1.0.0-rc.2`，源码指针和镜像版本保持一致。
- 新增 `scripts/sync_new_api_upstream.sh`，支持 `check` 和 `update`；`check` 会检查 GitHub 最新非草稿 release、submodule 指针和 compose 镜像 tag，发现落后时返回非 0，便于接入 CI/定时巡检。
- 新增 `make new-api-check` / `make new-api-sync` 统一入口，避免手工改镜像版本或直接复制上游代码。
- 扩展 ClawBot `newapi.py` 代理端点，新增 API Key 搜索/创建/编辑/禁用、使用日志、Token 趋势、订阅、兑换码、价格、充值配置和邀请返利接口代理；业务逻辑仍由 New-API 上游服务执行。
- New-API v1 后台接口需要 `New-Api-User` 头，代理层新增 `NEWAPI_ADMIN_USER_ID` 环境变量并同步测试，避免只配 access token 后认证失败。
- 研究结论: Frist-API 业务替换应采用“Frist-API 保留品牌壳 + New-API 内网服务承接账号/Key/渠道/计费/日志/订阅/兑换/支付”的代理与数据迁移方案，不再从旧本地 New-API 代码直接迁移。

### 文件变更
- `.gitmodules` / `packages/new-api-upstream` — 新增 New-API 上游 submodule，固定到 `v1.0.0-rc.2`
- `docker-compose.newapi.yml` — 升级 New-API 镜像并登记同步入口
- `scripts/sync_new_api_upstream.sh` — 新增上游版本检查和同步脚本
- `Makefile` — 增加 `new-api-check` / `new-api-sync`
- `packages/clawbot/src/api/routers/newapi.py` — 扩展 New-API 业务代理端点并补 `New-Api-User` 头
- `packages/clawbot/tests/test_newapi_router.py` — 覆盖新增代理路径和认证头
- `packages/clawbot/config/.env.example` — 登记 `NEWAPI_ADMIN_USER_ID`
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步注册表、升级 SOP 和当前状态

## [2026-05-03] Frist-API Workbench 腾讯云部署与 New-API 上游检查
> 领域: `frontend` | `infra` | `docs`
> 影响模块: `Frist-API`, `Docker Compose`, `New-API`, `docs`
> 关联问题: HI-858, HI-859

### 变更内容
- 已将 Frist-API Workbench UI 外壳、使用记录、美元展示、扩展 CC Switch 导入和 Codex DeepSeek 配置同步部署到腾讯云 `/opt/frist-api`。
- 部署前已备份远端应用代码，运行数据、远端 `.env` 和真实密钥未同步、未覆盖。
- `docker-compose.frist-api.yml` 补齐余额预警 SMTP 环境变量透传，避免生产容器读取不到服务器环境配置。
- 远端 `frist-api-server` 已重新创建并恢复 `healthy` 状态，公网首页、游客看板、验证码、隐藏管理页和未授权模型接口冒烟通过。
- 按用户要求暂停从旧本地 New-API 逻辑迁移，改为先检查 GitHub 上游；当前最新 New-API 为 `v1.0.0-rc.2`，本地 `docker-compose.newapi.yml` 仍固定在旧版 `calciumion/new-api:v0.12.6`，后续应先做数据备份和升级演练。

### 文件变更
- `docker-compose.frist-api.yml` — 透传 `FRIST_API_SMTP_*` 和 `FRIST_API_BALANCE_ALERT_FROM_NAME`
- `docs/002-changelog.md` — 记录部署、验证和 New-API 上游检查结果
- `docs/009-health.md` — 同步 Frist-API 服务器部署和 New-API 版本状态

## [2026-05-03] Frist-API Workbench UI 外壳与美元计价
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Adapter`, `docs`
> 关联问题: HI-858, HI-859

### 变更内容
- 用户端改成工作台式控制台外壳，保留顶部唯一 Frist-API Logo，移除侧栏重复品牌块。
- 仪表盘补齐今日请求、今日消费、今日 Token、累计 Token、累计消费、平均响应、性能指标和模型连通指标卡。
- 首页新增模型消耗圆形占比、Token 使用趋势、最近使用日志和服务可用性区块。
- API 管理新增“搜索名称或 key”、API 端点展示，以及禁用、编辑、删除、复制等图标化操作。
- 新增使用记录、我的订阅、兑换码、邀请返利和个人资料页面；使用记录展示 API 密钥、模型、推理强度、端点、类型、计费模式和 TOKEN。
- CC Switch 导入范围扩展并校验 Claude、Codex、Gemini、OpenCode、OpenClaw、Hermes、Harmes；Codex + DeepSeek 输出官方 OpenAI 兼容端点 `https://api.deepseek.com/v1`，真实 DeepSeek Key 未写入仓库。
- 用户侧余额、消费、模型价格、New-API 归一化数据和余额预警展示统一改为美元；充值仍按人民币生成美元额度。
- 已接入 New-API dashboard/token/usage/channel 的用户侧适配与脱敏归一化；完整 New-API 业务逻辑替换仍登记为架构迁移待办。
- 验证结果: Frist-API 语法检查通过；聚焦回归 3/3 通过；全量 `npm test` 112/112 通过；Playwright 已补桌面和移动截图。

### 文件变更
- `apps/frist-api/index.html` — 重做用户工作台外壳、新增页面和仪表盘区块
- `apps/frist-api/src/app.js` — 接入新路由、指标渲染、API 搜索、使用记录、CC Switch DeepSeek 流程
- `apps/frist-api/src/styles.css` — 新增工作台、指标卡、图表、记录表和新增页面响应式样式
- `apps/frist-api/src/core.js` — 扩展 CC Switch 客户端、DeepSeek 官方端点和导入配置
- `apps/frist-api/src/serverClient.js` — 归一化仪表盘、记录、日志和美元展示数据
- `apps/frist-api/src/businessFlow.js` — 同步业务流中的美元额度和导入状态
- `apps/frist-api/src/newApiClient.js` — 将 New-API 用户、Token、Usage、Channel 数据归一化到用户端美元展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` — 输出新仪表盘字段、使用记录、最近日志和 DeepSeek 模型目录
- `apps/frist-api/tests/*.test.mjs` — 覆盖新外壳、API 搜索、使用记录、美元计价、CC Switch 导入和 DeepSeek Key 不落库
- `docs/006-registries.md` — 登记新增 Frist-API Web 操作入口
- `docs/009-health.md` — 登记 UI 壳完成与 New-API 完整替换剩余架构迁移
- `docs/002-changelog.md` — 记录本次变更

## [2026-05-03] Frist-API 端到端全量审计
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`
> 关联问题: HI-850 ~ HI-857, TD-009 ~ TD-012

### 变更内容
- 对 apps/frist-api 模块执行全量端到端审计：源码审查、测试验证、安全扫描、UX 断点分析
- 测试结果：108/108 全量通过，0 失败
- 发现并登记 8 个新问题（3 安全 + 2 UX + 3 架构）和 4 个技术债
- 安全发现：runtime.json 明文存 Key、SHA-256 密码哈希过弱、Session Cookie 缺 Secure 标记、算术验证码可绕过
- UX 断点：无忘记密码流程、服务不可用时静默降级无重试
- 架构关注：单文件 4432 行、内存态状态无法水平扩展、data store 写入失败静默吞掉

### 文件变更
- `docs/009-health.md` — 新增 HI-850~857 和 TD-009~012
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Billing`, `SMTP`, `docs`
> 关联问题: HI-848

### 变更内容
- 用户账单页新增余额预警卡片，可自定义启用状态、人民币阈值和通知邮箱，并可手动发送测试邮件。
- 网关扣费后检测余额是否从阈值上方跌到阈值以下，只发送一次品牌化低余额邮件，避免重复刷屏。
- 后端新增 SMTP 发送器和 HTML/Text 双格式邮件模板，支持 Gmail/企业邮箱应用专用密码通过服务器环境变量配置。
- 腾讯云实测发现 Gmail IPv6 SMTP 可用、IPv4 465 超时；已补 Node SMTP DNS 地址轮询和 `FRIST_API_SMTP_FAMILY`，避免默认地址选择卡死自动邮件。
- 余额预警邮件模板升级为现代事务邮件样式：首屏突出当前余额/预警阈值，补齐事件摘要、CTA、暗黑模式和移动端可读性。
- 运维与注册表同步登记余额预警按钮、接口和 SMTP 环境变量；真实邮箱密码不落盘。
- 验证结果: Frist-API 本地回归测试当前 108/108 通过；本机到 Gmail SMTP 的 TLS/SMTP greeting 阶段不稳定，腾讯云服务器已通过 Gmail 587 STARTTLS 发出新版模板测试邮件，IPv4 465 超时仍保留为已知网络限制。

### 文件变更
- `apps/frist-api/server/server.js` — 新增余额预警 API、扣费触发逻辑、SMTP 发送器和邮件模板
- `apps/frist-api/index.html` — 在账单页新增余额预警设置卡片
- `apps/frist-api/src/app.js` — 接入余额预警保存、测试邮件和页面渲染
- `apps/frist-api/src/serverClient.js` — 增加余额预警接口客户端和 Dashboard 归一化
- `apps/frist-api/src/styles.css` — 增加余额预警卡片和移动端样式
- `apps/frist-api/tests/server.test.mjs` — 覆盖配置保存、跨阈值发信和重复通知抑制
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖账单页预警控件接线
- `apps/frist-api/deploy/production.env.example` — 增加 SMTP 环境变量示例
- `docs/006-registries.md` — 登记余额预警 Web 操作入口和 SMTP 环境变量
- `docs/007-operations.md` — 补充余额预警邮件配置和测试流程
- `docs/009-health.md` — 登记 HI-848/HI-849 并调整剩余 SMTP 技术债
- `docs/002-changelog.md` — 记录本次变更

## [2026-05-03] 文档压缩：43合12，核心10个
> 领域: `docs`
> 影响模块: `docs`, `AGENTS.md`
> 关联问题: HI-847

### 变更内容
- 文档合并: 43 个编号文件按类型合并为 12 个（001-010 核心 + 011-012 附录）。
  - `004-architecture.md` ← 010 + 011（OMEGA v2 + Bot Agent 指令）
  - `005-quickstart.md` ← 020 + 021 + 022 + 023 + 027 + 028
  - `006-registries.md` ← 030 + 031 + 032 + 033（API池+命令+依赖+模块）
  - `007-operations.md` ← 024 + 025 + 026 + 029
  - `008-sop.md` ← 040 + 041（文档优先协议+错误翻译）
  - `009-health.md` ← 060 + 063 + 064（健康+经验库+需求跟踪）
  - `010-feature-specs.md` ← 050-059 + 062 + 065（16个功能规格合并）
  - `011-kiro-gateway.md` ← 034-039（6个Kiro Gateway文档合并）
  - `012-handoff.md` ← 061（重编号）
- AGENTS.md 全文更新引用路径：060→009, 061→012, 030-033→006, 040-041→008, 063→009

### 文件变更
- `docs/004-010.md` — 新建 7 个合并文档
- `docs/011-kira-gateway.md` — 新建 1 个附录
- `docs/012-handoff.md` — 重编号
- `docs/` — 删除 39 个被合并的原文件
- `AGENTS.md` — 更新所有文档路径引用

## [2026-05-03] 文档治理：全项目归集 + 编号统一 + 冗余清理
> 领域: `docs`
> 影响模块: `docs`, `AGENTS.md`, `apps/openclaw/.learnings`, `apps/openclaw/usecases`, `packages/clawbot/docs`
> 关联问题: HI-846

### 变更内容
- 归集散落文档: 将 `apps/openclaw/.learnings/`、`apps/openclaw/usecases/`、`packages/clawbot/docs/` 共 27 个文档移入 `docs/` 根目录，统一编号命名
- 删除冗余: 移除 `packages/clawbot/docs/archive/`（3 个旧部署包说明）、`product-copy.txt`（闲鱼营销文案）、`final-checklist.txt`（含过期密钥的旧清单）、`architecture-ru.md`（冗余俄文翻译）、`packages/clawbot/docs/readme.md`（已过时子目录索引）
- 强化规则: 在 `AGENTS.md` 中新增「硬性规则」：docs/ 内禁止子目录、禁止非编号文件名、`docs/` 为文档唯一合法存放位置、排除范围清单、新增文档四步流程
- 编号扩展: docs/ 从 19 个扩展到 43 个，新增 011/026/028/029/034-039/050-059/062-065
- 索引同步: `docs/003-docs-index.md` 全面重写，标注编号空缺供后续使用

### 文件变更
- `docs/` — 新增 24 个编号文档，从散落位置移入
- `AGENTS.md` — §9 重写为硬性规则 + §10 新增子目录/命名禁令 + §6 新增文档变更触发索引
- `docs/003-docs-index.md` — 全文重写，增补编号空缺表
- `docs/060-health.md` — 更新文档治理状态
- `apps/openclaw/.learnings/` — 清空（内容已迁移到 docs/063-064）
- `apps/openclaw/usecases/` — 清空（内容已迁移到 docs/050-059/062/065）
- `packages/clawbot/docs/` — 清空（仅保留空目录）

## [2026-05-03] Frist-API 新余额站公网真测与图片广场优化
> 领域: `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Playground`, `Gateway`, `docs`
> 关联问题: HI-845

### 变更内容
- 上游切换: 接入新的授权余额站 `/v1` 上游，并保留 CPA JSON/chong 仅作为人工风控备用入口。
- 公网实测: 通过裸 IP 网关完成 `/v1/models`、`gpt-5.5` Chat Completions 和 `gpt-image-2` Images 真请求，图片响应返回有效 1024x1024 PNG。
- 广场优化: 用户端广场生图默认带 `quality: low`、`output_format: png` 和 `n: 1`，让低带宽服务器上的图片连通测试更稳定。
- 验证结果: Frist-API 本地回归保持 104 条通过，腾讯云容器 `frist-api-server` 处于 healthy 状态。

### 文件变更
- `apps/frist-api/src/app.js` — 广场图片请求默认使用轻量 PNG 参数
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场图片请求参数接线
- `docs/002-changelog.md` — 记录新余额站公网真测和广场优化
- `docs/025-frist-api-quickstart.md` — 同步图片广场实测口径
- `docs/060-health.md` — 登记 HI-845

## [2026-05-03] Frist-API 余额站上游与工作台首页适配
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Replenishment`, `Workbench`, `docs`
> 关联问题: HI-844

### 变更内容
- 上游策略: 适配授权余额站模式，管理员补号可以直接录入供应商根地址；当根地址返回网站 HTML 壳时，补号探测会自动尝试同域 `/v1` OpenAI 兼容路径。
- 探测校验: Chat Completions、Responses 和 Images 的 2xx 响应都要符合对应 OpenAI 兼容 JSON 结构，避免把网页、余额页或错误页误判为健康接口。
- 额度判断: 2xx HTML 文本不再参与余额不足判断，避免供应商 Dashboard 文案里的 balance 字样误触发 `quota_failed`。
- 公开部署: Docker Compose 透传 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP`，便于无域名裸 IP 阶段按显式开关完成公网验收。
- 用户界面: 首页从营销 Hero 改为控制台工作台布局，参考余额站后台的信息密度，新增紧凑左侧导航、顶部操作区和余额/API Key/消耗/模型连通四个核心状态卡。
- 验证准备: 新增根地址 HTML 自动切 `/v1` 的回归测试，保障 `gpt-5.5`、`gpt-image-2` 这类余额站模型进入广场实测前先通过真实 API 路径。

### 文件变更
- `apps/frist-api/server/server.js` — 增加根地址与 `/v1` 候选路由探测、响应结构校验和 2xx 额度判断保护
- `apps/frist-api/tests/server.test.mjs` — 覆盖供应商根地址返回 HTML 时自动路由到 `/v1`
- `apps/frist-api/index.html` — 首页改为工作台控制台布局
- `apps/frist-api/src/styles.css` — 新增工作台、左侧 rail、控制台指标卡和响应式样式
- `apps/frist-api/tests/core.test.mjs` — 更新首页布局边界测试
- `docker-compose.frist-api.yml` — 透传无域名 HTTP 验收开关
- `apps/frist-api/deploy/production.env.example` — 补充生产环境变量示例
- `docs/024-frist-api-operator-runbook.md` — 增加授权余额站接入和根地址 `/v1` 自动探测说明
- `docs/025-frist-api-quickstart.md` — 同步工作台首页、余额站探测和测试覆盖说明
- `docs/031-command-registry.md` — 登记工作台 rail 和控制台主区入口
- `docs/060-health.md` — 登记 HI-844

## [2026-05-03] Frist-API 上游失效库存落盘
> 领域: `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Inventory`, `docs`
> 关联问题: HI-843

### 变更内容
- 真实公网实测发现: 线上两枚上游 Key 已被供应商禁用，但库存仍停留在 `healthy`，导致广场继续展示 `gpt-5.5` / `gpt-image-2` 可用。
- 网关修复: 当同一模型的所有候选上游都因认证失败、网络失败或 5xx 被摘除后，返回 503 响应但保留本次库存状态变更，避免异常路径回滚。
- 库存下线: 失效上游会被持久化为 failed/exhausted，后续 `/v1/models`、广场和导入模型清单不再展示这类不可用模型。
- 验证结果: 新增所有候选上游被拒绝时的回归测试，确认 503 后库存状态会落盘且模型清单下线。

### 文件变更
- `apps/frist-api/server/server.js` — 将全候选失败路径改为可落盘的 503 网关响应
- `apps/frist-api/tests/server.test.mjs` — 覆盖所有上游被禁用时的库存持久化和模型下线行为
- `docs/002-changelog.md` — 记录公网实测暴露的问题与修复
- `docs/025-frist-api-quickstart.md` — 同步回归测试数量
- `docs/060-health.md` — 登记 HI-843

## [2026-05-03] Frist-API 备用渠道人工风控入口
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Gateway`, `Replenishment`, `docs`
> 关联问题: HI-842

### 变更内容
- 备用渠道: 管理端补号新增 `CPA JSON 备用渠道`、`chong 备用渠道` 和其他人工备用渠道类型，只作为库存登记和应急入口。
- 风险放行: 备用渠道默认写入隔离态，必须管理员选择已人工核验并勾选路由确认后，才会变成健康可路由库存。
- 路由保护: `/v1/models`、用户导入模型清单、广场和实际网关调用只使用已放行库存；隔离或禁止状态不会访问上游。
- JSON 入口: 管理端 Key 列表支持粘贴 JSON 数组，便于人工导入已合规确认的 API 兼容凭证；不实现 OAuth Token 抓取、批量刷新或绕过风控逻辑。
- 隐私边界: 用户端 Dashboard 不暴露 `cpa_json_backup`、`chong_backup`、风险备注或上游来源字段。
- 验证结果: Frist-API `npm test` 扩展到 102 条，覆盖备用渠道隔离、人工放行、图片生成和广场连通入口。

### 文件变更
- `apps/frist-api/server/server.js` — 增加渠道类型、风险状态、人工确认字段和路由过滤
- `apps/frist-api/admin.html` — 管理端新增备用渠道类型、风险状态、人工确认和风险备注入口
- `apps/frist-api/src/admin.js` — 提交/展示备用渠道风险字段，并支持 JSON 数组粘贴
- `apps/frist-api/src/businessFlow.js` — 业务流补齐备用渠道隔离/放行规则
- `apps/frist-api/tests/server.test.mjs` — 覆盖 CPA JSON 隔离和 chong 人工放行后的路由行为
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖管理端入口接线和备用渠道状态机
- `docs/024-frist-api-operator-runbook.md` — 增加备用渠道人工风控操作边界
- `docs/025-frist-api-quickstart.md` — 同步管理端备用渠道和测试覆盖说明
- `docs/031-command-registry.md` — 登记备用渠道风险字段入口
- `docs/060-health.md` — 登记 HI-842

## [2026-05-03] Frist-API 广场 5.5/image2 连通修复
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Playground`, `Replenishment`, `docs`
> 关联问题: HI-841

### 变更内容
- 方案收口: 保留 Frist-API 商业展示层 + New-API 内网路由层的解耦思路，但明确生产库存只接授权供应商、自有额度或明确可转售额度，不把批量 OAuth Session / 来路不明 JSON 号源当生产方案。
- 模型别名: 将广场和补号里常见的 `5.5`、`gpt5.5`、`gpt-55` 统一清洗为 `gpt-5.5`，将 `image2`、`gpt-image2`、`gpt_image_2` 统一清洗为 `gpt-image-2`。
- 图片探测: 补号严格探测遇到图片模型时直接请求 `/images/generations`，避免用 `/chat/completions` 或 `/responses` 误判 `image2` 库存不可用。
- 广场实测: 用户广场新增“实测连通”按钮和状态摘要，能直接展示当前模型的成功/失败、耗时和返回结果；图片模型会展示生成结果。
- 管理摘要: 管理端脱敏库存返回 `lastProbeStatus` / `lastProbeReason`，便于确认图片库存是 `image_probe_ok` 而不是信任写入。
- 验证结果: 新增回归覆盖 `5.5` / `image2` 别名、图片模型补号探测和广场实测入口；Frist-API 测试集扩展到 100 条。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 `5.5` / `image2` 等广场常用别名归一化
- `apps/frist-api/server/server.js` — 新增图片模型探测路径、图片默认候选模型和脱敏探测状态返回
- `apps/frist-api/src/app.js` — 新增广场连通实测状态、按钮逻辑和耗时摘要
- `apps/frist-api/index.html` — 新增广场连通实测按钮和状态展示位置
- `apps/frist-api/src/styles.css` — 新增广场实测状态样式
- `apps/frist-api/tests/core.test.mjs` — 覆盖广场模型别名清洗
- `apps/frist-api/tests/server.test.mjs` — 覆盖 `image2` 网关归一化和图片模型补号探测
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场连通实测入口接线
- `docs/024-frist-api-operator-runbook.md` — 明确授权库存边界和图片模型探测规则
- `docs/025-frist-api-quickstart.md` — 同步广场实测、别名和图片探测说明
- `docs/031-command-registry.md` — 登记广场连通实测入口
- `docs/060-health.md` — 登记 HI-841 修复状态

## [2026-05-03] 项目文档和冗余产物清理
> 领域: `docs` | `infra`
> 影响模块: `docs`, `Frist-API`, `workspace-cleanup`
> 关联问题: HI-840

### 变更内容
- 文档压缩: 主项目 `docs/` Markdown 从 37 个压缩到 19 个，保留核心入口、操作指南、注册表、SOP 和状态文档。
- 过时报告清理: 删除 5 月前审计/设计/归档报告、散落的 Bot 模型旧审计，以及 Frist-API 历史截图和散落测试截图。
- Frist-API 文档收口: 腾讯云部署和公网验收要点合并进 `docs/024-frist-api-operator-runbook.md` / `docs/025-frist-api-quickstart.md`，不再单独维护临时部署报告。
- 本地冗余清理: 清理可重建构建产物、缓存、浏览器模型缓存、运行日志和本地开发虚拟环境；仓库体积从约 2.4GB 降到约 196MB，保留业务数据库、测试、Bot 人设、Skill 文件和第三方包文档。
- 服务器清理: 只清腾讯云上的日志、缓存、临时文件、构建缓存和 Docker 非运行对象；系统日志从 264MB 降到 176MB，不删除共享服务器的业务项目、数据库、测试代码、运行虚拟环境、浏览器登录态或 Docker 业务卷。
- 验证结果: `apps/frist-api` 执行 `npm test`，99 passed, 0 failed；`docs/` 根目录保持 19 个 Markdown。

### 文件变更
- `docs/003-docs-index.md` — 重写为 19 个核心文档索引
- `docs/024-frist-api-operator-runbook.md` — 合并腾讯云部署和公网验收操作要点
- `docs/025-frist-api-quickstart.md` — 保留当前入口和本地/容器运行说明
- `docs/060-health.md` — 登记本次冗余清理
- `README.md` — 移除旧审计入口，指向当前 Frist-API 文档
- `apps/openclaw/BOT_MODEL_AUDIT.md` — 删除 2026-03 旧 Bot 模型审计报告

## [2026-05-02] Frist-API OpenCode 外网阻塞修复
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `OpenCode`, `Gateway`, `docs`
> 关联问题: HI-839, HI-833, HI-836

### 变更内容
- 外网复现: 用公网 Quick Tunnel 注册新用户、创建 Key、补日卡额度后复现并验证广场和 OpenCode 路由，不再只做本地冒烟。
- 一键导入入口: CC Switch 页面把“一键导入 / 复制链接 / 导出模型清单”提前到长教程流程图之前，用户不用先读完教程才能找到主操作。
- OpenCode 路由: 网关新增 `/openai/chat/completions`、`/v1/openai/chat/completions`、`/openai/responses`、`/v1/openai/responses` 和图片前缀别名，兼容 OpenCode/CC Switch 生成的 OpenAI 前缀路径。
- Chat Completions 降级: 上游 Chat Completions 返回 404 或不支持时，自动把请求转换到 Responses，再把 Responses 响应转回 Chat Completions，修复 `Route /openai/chat/completions not found`。
- 模型清单补齐: OpenCode/Codex 导入 URL、base64 配置和前端模型清单同步补 `gpt-5.4-mini`、`gpt-5.3-codex` 等兼容字段，避免外部 GUI 只显示默认 `gpt-5.5`。
- OpenCode 桌面导入: `ccswitch://` 的 OpenCode `config.models` 改为 OpenCode/CC Switch 实际读取的模型对象映射，修复桌面端导入后编辑框仍只有 `gpt-5.5` 的问题。
- 公网验证: 腾讯云 `/opt/frist-api` 已同步并重启，`frist-api-server` healthy；公网 `gpt-5.5` Chat/Responses、OpenCode 前缀 Chat、`gpt-5.4` Responses 和 OpenCode 导入模型清单均返回成功。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 OpenCode 前缀路由、Chat Completions→Responses 降级、Responses→Chat Completions 响应转换和 Codex 模型排序
- `apps/frist-api/index.html` — 将一键导入主操作和导出模型清单前置到长教程之前
- `apps/frist-api/src/styles.css` — 增加一键导入主操作区域样式
- `apps/frist-api/src/app.js` — 补齐 `gpt-5.3-codex` 前端模型强度排序
- `apps/frist-api/src/core.js` — 补齐 `gpt-5.3-codex` 导入配置模型强度排序，并按 OpenCode 真实配置格式输出完整 `models` 映射
- `apps/frist-api/tests/core.test.mjs` — 覆盖 OpenCode 桌面导入配置的完整模型映射
- `apps/frist-api/tests/server.test.mjs` — 覆盖 Chat Completions 降级、OpenCode 前缀路由和完整模型清单导出
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖一键导入主操作必须位于长教程之前
- `docs/060-health.md` — 登记 HI-839 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次外网阻塞修复和验证结果

## [2026-05-02] Frist-API 用户闭环断点修复与价格管理
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `CC Switch`, `Pricing`, `docs`
> 关联问题: HI-838, TD-006, TD-008

### 变更内容
- 登录注册反馈: 用户登录、注册、验证码和密码错误现在都会显示明确成功/失败状态，按钮进入处理中状态，避免用户不知道请求是否生效。
- API Key 创建反馈: 创建 Key 改为真实服务端链路，成功/失败均有明确提示，不再本地伪造或静默失败。
- 连通性刷新: 刷新按钮保持在首页看板，不再误跳使用教程；渠道连通性升级为供应商、模型数量、可用状态和延迟摘要。
- 模型命名清洗: 上游返回的历史 Claude Haiku 别名统一归一为官方展示名，用户页、导入链接和模型广场不再暴露 `claude-haiku-4-5-20251001` 这类非规范名称。
- Mock 数据移除: 删除用户端网页 mock 数据文件和 New-API demo fallback；服务不可用时展示真实空态，不再展示演示套餐、演示用户或伪造 Key。
- 价格管理: 新增管理端套餐与模型计价 JSON 编辑，默认套餐按用户确认的 5 档 Codex API 额度配置；模型计价按官方成本价走，优惠只体现在充值套餐。
- 实机预审: 本地浏览器完整跑通注册、登录、创建 Key、刷新连通性、模型广场、充值套餐和管理端价格保存；腾讯云容器重新部署并通过本地/公网冒烟。
- 测试额度: 测试账号已通过管理端人工入账补足 60 刀等值日卡额度，便于实测 API 聚合、模型切换、上下文粘滞和无缝降级。
- 文档治理: 主项目 `docs/` 目录统一迁移到根目录编号命名，清理子目录层级，并同步代码、测试和 SOP 中的文档路径。

### 文件变更
- `apps/frist-api/server/server.js` — 新增价格管理 API、模型名清洗、真实空态数据、登录/Key 错误反馈和渠道连通性聚合
- `apps/frist-api/src/app.js` — 接入登录/注册/Key/连通性显式反馈，移除 mock 兜底并刷新价格/模型/导入状态
- `apps/frist-api/src/core.js` — 新增官方模型名归一化和跨客户端导入模型清单清洗
- `apps/frist-api/src/serverClient.js` — 补齐价格、登录、Key 和 dashboard 请求归一化
- `apps/frist-api/src/businessFlow.js` — 业务流去除演示数据依赖并同步价格配置
- `apps/frist-api/src/admin.js` — 管理端新增套餐与模型价格读取/保存
- `apps/frist-api/src/newApiClient.js` — 移除本地 demo store fallback
- `apps/frist-api/src/data.js` — 删除网页 mock 数据源
- `apps/frist-api/index.html` — 用户端补齐反馈容器、渠道连通性区域和真实空态
- `apps/frist-api/admin.html` — 管理端新增价格管理区
- `apps/frist-api/src/styles.css` — 增加反馈状态、连通性摘要和价格管理样式
- `apps/frist-api/tests/*.mjs` — 覆盖登录反馈、Key 创建反馈、价格管理、模型清洗、mock 移除和网关计费
- `docs/024-frist-api-operator-runbook.md` — 补齐价格管理、测试额度和支付人工操作指南
- `docs/060-health.md` — 登记 HI-838 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次用户闭环和价格管理收口

## [2026-05-02] Frist-API 跨模型导入实操流程图
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude Code`, `Codex`, `Payments`
> 关联问题: HI-837, HI-836

### 变更内容
- Claude Code 实操引导: CC Switch 页新增“ChatGPT / OpenAI 模型导入 Claude Code”流程图，按真实 Claude 菜单标出左上角 `Developer`、`Configure Third-Party Inference...`、`Gateway base URL`、`Gateway API key`、`Gateway auth scheme`、`Model list` 和 `Skip login-mode chooser`。
- Codex 实操引导: 新增“Claude 模型导入 Codex”流程图，标出本站 CC Switch 目标选择、模型家族选择、一键导入、Codex `API 请求地址`、`auth.json`、`wire_api = "responses"`、默认 Claude 模型和 MCP 段。
- 动态字段: 流程图中的 Frist-API 地址、Claude/Codex 地址、默认 OpenAI 模型、默认 Claude 模型会按当前站点和用户可用模型自动刷新。
- 运营手册: 补齐个人微信/支付宝收款码试运营步骤、60 刀日卡测试额度折算说明、支付宝当面付和微信支付 Native 的小白级开通步骤，并加入对应官方接口文档入口。
- 测试额度: 已通过后台人工入账路径给测试账号加入 60 刀等值日卡额度，用于实测 API 聚合、模型切换和上下文粘滞。

### 文件变更
- `apps/frist-api/index.html` — 新增两张跨模型导入实操流程图和逐步字段说明
- `apps/frist-api/src/app.js` — 接入流程图动态字段刷新和当前场景高亮
- `apps/frist-api/src/styles.css` — 新增仿真实操窗口、菜单、设置页、Codex 配置页和响应式样式
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖流程图关键文案、字段和 MCP/Responses 配置提示
- `docs/024-frist-api-operator-runbook.md` — 扩写个人码收款、测试额度、支付宝/微信支付操作指南
- `docs/060-health.md` — 登记 HI-837 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次导入引导和支付手册改动

## [2026-05-02] Frist-API Codex MCP 默认增强
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `MCP`
> 关联问题: HI-836

### 变更内容
- Codex 最强默认配置: Codex 目标导出的 `config.toml` 现在默认写入 Playwright、Superpowers 和 open-computer-use MCP，继续保留 Responses、1M 上下文、90 万压缩阈值、xhigh 推理和工具搜索。
- CC Switch 兼容: 导入链接的隐藏配置同步携带 `mcpServers` / `mcp_servers` 元数据；如果 CC Switch 支持 MCP 字段，可以直接消费，若只写入 `config.toml` 也能保留 MCP 段。
- 用户引导: Codex 导入说明新增 MCP 和 Computer Use 权限提示，明确 CC Switch 能写配置，但首次使用桌面电脑操作能力仍需本机系统授权。
- 部署验证: 已同步到腾讯云 `/opt/frist-api`，容器 `frist-api-server` 为 healthy；公网 `/` 和 `/api/frist/dashboard` 返回 200，未授权 `/v1/models` 返回 401，普通 `/admin.html` 返回 404，冒烟脚本通过。

### 文件变更
- `apps/frist-api/src/core.js` — 为 Codex 生成默认 MCP TOML 和导入元数据
- `apps/frist-api/src/app.js` — CC Switch 页新增 Codex 最强开发配置和 MCP 权限提示
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Codex MCP TOML 和 CC Switch 元数据
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页 MCP 引导文案
- `docs/024-frist-api-operator-runbook.md` — 增加 Codex MCP 默认增强和验收项
- `docs/025-frist-api-quickstart.md` — 增加 Codex MCP 配置说明
- `docs/002-changelog.md` — 记录本次 MCP 默认增强

## [2026-05-02] Frist-API CC Switch 跨模型家族一键导入
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude Code`, `Codex`, `Payments`
> 关联问题: HI-836

### 变更内容
- Claude Code 导入: CC Switch 的 Claude 目标现在导出 `anthropic-messages` 配置，自动写入 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、默认模型、Tool Search 和团队模式字段，支持把 ChatGPT/OpenAI 模型通过 Frist-API 路由给 Claude Code 使用。
- Codex 导入: Codex 目标继续导出 Responses provider 配置，并标记 Claude 模型跨家族导入；网关在上游不支持 Responses 时自动降级到 Chat Completions，保证 Claude 模型也能被 Codex 调用。
- 网关适配: 新增 `/v1/messages` 和根路径 `/messages` 的 Anthropic Messages 入口，接收 Claude Code 请求后转换为 OpenAI 兼容上游请求，再转回 Anthropic 响应。
- 用户引导: CC Switch 页面新增“目标客户端 + 模型家族”双选择、Claude 开发者模式/第三方 API 步骤说明、Codex + Claude 导入说明和对应样式。
- 支付最后一公里: 运营手册补齐个人收款二维码人工入账、支付宝当面付、微信支付 Native、商户号、签名密钥、异步通知、验签和密钥保管操作指南。
- 回归测试: `npm test` 当前为 90/90 通过，覆盖 Claude Code Anthropic Messages、Codex Responses fallback、跨模型家族导入 UI 和支付人工操作清单。

### 文件变更
- `apps/frist-api/src/core.js` — 调整五客户端导入配置，新增 Claude Code JSON、Anthropic 格式字段和跨家族导入标记
- `apps/frist-api/server/server.js` — 新增 Anthropic Messages 网关入口、Responses 到 Chat Completions 降级和认证头兼容
- `apps/frist-api/index.html` — CC Switch 页面新增模型家族选择和跨家族导入引导
- `apps/frist-api/src/app.js` — 接入模型家族切换、跨导入文案和手动配置同步刷新
- `apps/frist-api/src/styles.css` — 增加导入家族选择和跨导入引导样式
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Claude Code 使用 ChatGPT 模型、Codex 使用 Claude 模型的导入配置
- `apps/frist-api/tests/server.test.mjs` — 覆盖 `/v1/messages` 和 Responses fallback 网关链路
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页跨家族导入引导和支付最后一公里文档
- `docs/024-frist-api-operator-runbook.md` — 补齐收款二维码、支付宝当面付、微信支付 Native 和密钥操作指南
- `docs/060-health.md` — 登记 HI-836 并更新 Frist-API 测试状态
- `docs/002-changelog.md` — 记录本次 CC Switch 跨模型家族适配

## [2026-05-02] Frist-API 首屏焦点流与品牌标识重做
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `docs`
> 关联问题: HI-835, HI-828, HI-833

### 变更内容
- 品牌回归: 顶部品牌标识改回黑底、白色斜切和红色识别点的黑白红方案，与 favicon 保持同一识别语言。
- 视觉节奏: 首页从单块大英雄卡改成“主控台 + 右侧说明 + 核心指标”双栏结构，主行动入口只保留一个，避免用户第一眼被多个等宽模块分散。
- 任务轨道: 快捷入口改成不对称任务轨道，CC Switch 作为首个主路径，其余入口保留为轻量辅助动作。
- 指标聚焦: 余额、消耗、连通三项状态继续保留，但移入右侧说明区，减少首屏横向铺满的机械感。
- 回归测试: 更新前端结构测试，覆盖新的 hero-flow 与 hero-aside 钩子以及主路径优先级。

### 文件变更
- `apps/frist-api/index.html` — 调整首屏结构、品牌文案和快捷入口排序
- `apps/frist-api/src/styles.css` — 重做品牌标识、首屏双栏布局、任务轨道和响应式断点
- `apps/frist-api/tests/core.test.mjs` — 补充首屏焦点流与品牌回归断言
- `docs/060-health.md` — 登记 HI-835 用户体验优化记录
- `docs/002-changelog.md` — 记录本次首屏视觉优化

## [2026-05-02] Frist-API 生产入口恢复与商业化审计
> 领域: `deploy` | `infra` | `docs` | `ai-pool`
> 影响模块: `Frist-API`, `Tencent Cloud`, `Nginx`, `docs`
> 关联问题: HI-834, TD-006, TD-007, TD-008

### 变更内容
- 线上恢复: 复现裸 IP 入口 `ERR_CONNECTION_REFUSED`，确认 Frist-API 容器健康但只绑定本地端口，Nginx 未监听 Frist-API 测试端口；已同步服务器代码和 Compose 文件，并在 Nginx 增加独立测试端口反代。
- 多项目保护: 保留服务器 80/443 现有默认项目，不抢占裸 IP 根路由；Frist-API 在无固定域名阶段通过独立测试端口和 Tunnel 验收。
- 商业化审计: 新增生产就绪报告，按架构、组件结构、数据流、API 设计、数据库模式、缓存策略、性能瓶颈、清洁架构拆分和人工开通清单审计当前状态。
- 运营手册: 扩写人工收款、支付平台、固定域名、SMTP、Turnstile、备份、告警、合规和模型列表规则，明确哪些事项必须由业务方在后台开通。
- 模型风险登记: 明确生产模型列表不能靠硬编码宣传，必须由上游 `/v1/models`、真实探测和官方目录校验共同决定；默认最强模型只能从用户真实可用列表中选择。
- 验证结果: 公网测试入口 `/` 和 `/api/frist/dashboard` 返回 `200 OK`；未授权 `/v1/models` 返回 `401`；公网冒烟脚本通过。

### 文件变更
- `docs/080-frist-api-production-readiness-2026-05-02.md` — 新增生产就绪审计、架构和商业化缺口报告
- `docs/024-frist-api-operator-runbook.md` — 扩写人工开通、支付、域名、邮箱、防刷、模型列表和生产验收清单
- `docs/026-frist-api-tencent-deploy.md` — 补充裸 IP 拒绝连接排查流程和多项目服务器反代边界
- `docs/060-health.md` — 登记 HI-834 和 TD-008，并更新 Frist-API 当前生产化状态
- `docs/002-changelog.md` — 记录本次线上入口恢复和商业化审计

## [2026-05-02] Frist-API 导出模型清单可见化
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `OpenCode`
> 关联问题: HI-833

### 变更内容
- 导出页新增模型清单: CC Switch 页直接展示默认模型、可用模型数量和完整模型列表，用户切换 Codex/OpenCode 时可以立即确认导出结果。
- 兼容字段补强: 导入 URL 和 base64 配置同时输出 `models`、`availableModels`、`available_models`、`modelList`、`model_list`、`supportedModels`、`defaultModel` 和 `default_model`，降低外部 GUI 只读取某个字段时只显示单模型的风险。
- 目标切换同步: 在 CC Switch 页切换 Codex/OpenCode/OpenClaw/Hermes 或模型分组后，同步刷新导入链接、手动配置和模型清单，避免链接已变但配置区域仍是旧目标。
- 官方命名排序: 补充 `gpt-5.4-nano` 的官方模型排序兜底；实际导出仍以用户库存和模型目录里的真实可用模型为准，不凭空展示未供给模型。
- 回归测试: Frist-API 当前 `make frist-api-test` 为 84/84 通过，新增覆盖 Codex/OpenCode 全模型导出、兼容字段和用户页模型清单。

### 文件变更
- `apps/frist-api/index.html` — CC Switch 页新增默认模型、可用模型数量和模型列表展示区域，并更新前端资源版本
- `apps/frist-api/src/app.js` — 增加导出模型清单渲染，目标/分组切换时同步刷新配置
- `apps/frist-api/src/styles.css` — 增加导出模型清单和默认模型标签样式
- `apps/frist-api/src/core.js` — 补齐导入 URL 与 provider 配置里的模型列表兼容字段
- `apps/frist-api/server/server.js` — 导入 URL 接口同步返回默认模型和完整可用模型列表
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Codex/OpenCode 全模型导出和兼容字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页模型清单和配置同步接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖服务端 Codex/OpenCode 导出同一份完整模型列表
- `docs/060-health.md` — 登记 HI-833
- `docs/031-command-registry.md` — 登记导出模型清单入口

## [2026-05-02] Frist-API 用户端完整度补强
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-832

### 变更内容
- 账户入口: 右上角注册/登录从简陋账户区改为模态弹窗，登录/注册按模式只显示当前动作，并补齐 `dialog`、`tab`、`aria-selected` 和 Escape 关闭语义。
- 页面返回: 广场、数据、模型、教程、API Key、充值、CC Switch 等子页面统一增加返回首页入口，避免用户进入导入或管理页后迷路。
- 广场测试: 每条测试消息支持单条删除，广场支持一键清空，图片模型和文本模型继续走同一用户 Key 与网关链路。
- API Key 管理: 用户侧支持 Key 改名、删除和单 Key 状态展示，服务端新增 `PATCH /api/frist/token/:id` 改名和 `DELETE /api/frist/token/:id` 删除。
- CC Switch 导入: 导出配置改为默认最强模型 `gpt-5.5`，同时列出用户可用模型；若库存包含 `gpt-5.5-pro` 等官方 Pro 档，会自动把 Pro 档排到默认模型；OpenCode/Codex/Hermes 走 Responses 兼容格式并默认开启流式、图片、工具搜索等能力。
- 使用教程: 教程页补齐 OpenCode、Hermes 和 Harmes 入口，手动配置同步输出默认模型、模型列表和功能开关。
- 回归测试: Frist-API 当前 `make frist-api-test` 为 83/83 通过，新增覆盖账户弹窗语义、返回按钮、广场删除/清空、API Key 改名/删除、OpenCode 模型导出和官方 Pro 模型优先级。

### 文件变更
- `apps/frist-api/index.html` — 重做账户弹窗结构，补齐返回首页、广场清空、教程目标和 API Key 操作入口
- `apps/frist-api/src/app.js` — 接入账户模式切换、消息删除/清空、Key 改名/删除、默认最强模型和教程配置刷新
- `apps/frist-api/src/styles.css` — 增加账户弹窗、返回按钮、消息删除、Key 名称输入和危险操作样式
- `apps/frist-api/src/core.js` — 导出默认模型、可用模型列表、Responses 配置、功能开关和 Hermes/Harmes 别名
- `apps/frist-api/src/businessFlow.js` — 本地 fallback 支持 Key 改名/删除并保留真实 Key 供导入配置使用
- `apps/frist-api/src/serverClient.js` — 增加用户 Key 改名和删除 HTTP 客户端
- `apps/frist-api/server/server.js` — 增加 Key 改名/删除接口，导入 URL 使用用户可用模型列表和最强默认模型
- `apps/frist-api/src/data.js` — 补齐默认模型目录
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖账户弹窗、返回入口、广场删除/清空、API Key 操作和教程目标
- `apps/frist-api/tests/core.test.mjs` — 覆盖 OpenCode 导出全模型列表并默认最强模型
- `apps/frist-api/tests/server.test.mjs` — 覆盖 API Key 改名和删除 HTTP 链路
- `docs/031-command-registry.md` — 登记本轮新增用户侧操作入口
- `docs/060-health.md` — 登记 HI-832

## [2026-05-02] Frist-API 一次性管理员身份码
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `docs`
> 关联问题: HI-831

### 变更内容
- 管理员激活: 登录后的用户可在右上角账户区域输入一次性身份码，把当前账号升级为管理员；身份码成功使用后自动作废。
- 管理入口: 账号升级后显示运营入口，可直接进入独立管理页；普通用户仍不会看到库存、补号和管理工作台。
- 管理鉴权: 管理 API 现在支持管理员登录态，也保留强随机管理员令牌作为后备方式，避免用户把账号密码交给开发者手动升级。
- 部署配置: Docker 和生产环境模板新增 `FRIST_API_ADMIN_CLAIM_CODES`，支持逗号分隔的一批一次性身份码。
- 操作说明: 补充管理员首登、人工入账、支付接口、固定域名、SMTP 和 Turnstile 的人工操作清单。
- 验证结果: 身份码链路已通过红绿回归，当前 Frist-API 测试扩展到 79 条。

### 文件变更
- `apps/frist-api/server/server.js` — 增加一次性管理员身份码校验、管理员登录态鉴权和静态管理页登录态放行
- `apps/frist-api/index.html` — 在账户区域加入身份码输入和管理员可见运营入口
- `apps/frist-api/src/app.js` — 接入身份码激活、管理员入口显示和前端状态刷新
- `apps/frist-api/src/admin.js` — 管理页支持用管理员登录态访问管理 API，管理员令牌降级为后备方式
- `apps/frist-api/src/serverClient.js` — 增加身份码激活接口和管理员字段归一化
- `apps/frist-api/src/businessFlow.js` — 同步用户状态中的管理员标记
- `apps/frist-api/src/styles.css` — 增加身份码行和运营入口样式
- `apps/frist-api/tests/server.test.mjs` — 覆盖身份码只能使用一次、管理员登录态可访问管理 API
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页身份码接线且不暴露管理令牌输入框
- `docker-compose.frist-api.yml` — 增加 `FRIST_API_ADMIN_CLAIM_CODES`
- `apps/frist-api/deploy/production.env.example` — 增加一次性管理员身份码配置
- `docs/025-frist-api-quickstart.md` — 同步管理员首登链路和测试范围
- `docs/026-frist-api-tencent-deploy.md` — 同步腾讯云部署安全边界和上线检查
- `docs/024-frist-api-operator-runbook.md` — 新增必须人工操作的支付、域名、邮箱和验证码清单
- `docs/031-command-registry.md` — 登记身份码和运营入口选择器
- `docs/060-health.md` — 登记 HI-831

## [2026-05-02] Frist-API 用户广场与数据教程页
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-830

### 变更内容
- 用户广场: 新增低密度模型测试页，用户可直接选择模型对话；`gpt-image-2` 等图片模型走图片生成窗口。
- 数据看板: 新增模型消耗分布、消耗列表和服务可用性聚合视图，把原渠道连通性收敛成客户能看懂的可用状态。
- 模型广场: 新增客户安全模型目录，展示模型家族、用途、上下文和计价，不泄露上游号商、请求地址或原始 Key。
- 使用教程: 新增 Codex、Claude、OpenClaw 的配置页，输出 JSON/TOML 配置和 macOS/Windows 一键配置命令。
- 网关链路: `/v1/images/generations` 纳入同一套用户 Key、日卡库存、上游路由和故障切换链路，方便网页广场直接测试生图模型。
- 公网入口: 已同步部署到腾讯云 Frist-API 容器，并通过 Cloudflare Quick Tunnel 提供可信 HTTPS 外网入口，当前用户端和 `/v1` 网关都走同一公开域名。
- 证书验证: 当前 HTTPS 入口证书由 Google Trust Services 签发给 `trycloudflare.com`，可满足今晚外部实测；长期生产仍需绑定自有固定域名。
- 移动端修复: 小屏下页面标题和操作控件改为纵向排布，避免“广场”等标题被按钮或选择器挤压。
- 冒烟脚本: 公网检查改为落盘再 grep，避免 `curl | grep -q` 的断管噪音污染交付日志。
- 验证结果: `npm test` 当前 78/78 通过；`node --check` 覆盖用户端、核心配置、浏览器客户端和轻量后端；`git diff --check` 无空白错误；敏感词扫描无命中。

### 文件变更
- `apps/frist-api/index.html` — 增加广场、数据看板、模型广场和使用教程四个用户页面
- `apps/frist-api/src/app.js` — 接入模型选择、对话/生图测试、数据看板、模型目录和配置教程渲染
- `apps/frist-api/src/core.js` — 生成 macOS/Windows 一键配置命令并保持 Frist-API 品牌清洗
- `apps/frist-api/server/server.js` — 增加客户安全模型目录和图片生成网关路由
- `apps/frist-api/src/styles.css` — 补齐新页面视觉层次、移动端标题布局和轻量动效
- `apps/frist-api/deploy/smoke-test.sh` — 稳定公网冒烟检查输出，覆盖用户端、验证码、隐藏管理入口和模型目录
- `apps/frist-api/tests/core.test.mjs` — 覆盖一键配置命令不泄露上游字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场、数据看板、模型广场和教程页接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖客户安全模型目录和图片生成路由
- `docs/025-frist-api-quickstart.md` — 同步用户组件、网关路由和测试覆盖
- `docs/026-frist-api-tencent-deploy.md` — 同步 Quick Tunnel HTTPS 入口、动态域名直签限制和长期域名方案
- `docs/031-command-registry.md` — 登记新增用户页面操作入口
- `docs/060-health.md` — 更新 Frist-API 测试数和 HI-830
- `docs/002-changelog.md` — 记录本次用户组件补齐

## [2026-05-02] Frist-API 公开可测链路与隐藏管理入口
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-829

### 变更内容
- 公开入口: Frist-API 已同步到腾讯云 `5566` 临时公网端口，用户端可直接进行注册、登录、创建 Key、充值申请和 CC Switch 导入实测。
- 防刷门槛: 用户注册和登录接入轻量验证码挑战与 IP 频率限制，公开模式继续关闭验证码回显和演示充值。
- 管理入口: `/admin.html` 默认返回 404，必须带独立隐藏入口码后才加载静态管理页；管理 API 仍要求管理员令牌。
- 上游清洗: 补号订单文本会归一化请求地址、卡类型、额度、到期时间、认证字段、额外请求头和模型分组；用户侧导入只暴露 Frist-API 供应商标识、官网入口、用户 Key 和公开网关地址。
- 兼容导入: CC Switch 导入继续覆盖 Claude、Codex、OpenCode、OpenClaw、Hermes，并输出 `auth.json`、`config.toml`、Responses 接口格式、上下文/压缩、`setCacheKey` 和工具搜索配置。
- 中转策略: 网关按小时卡、日卡、月卡、不限时、默认池顺序消耗库存；同一会话通过 `x-frist-session-id` 或 `metadata.frist_session_id` 粘滞到健康上游，异常时带完整请求体切换。
- 库存告警: 低库存阈值通知钩子已接入 `FRIST_API_LOW_INVENTORY_WEBHOOK`，后续可接 OpenClaw 的 Telegram/微信通知入口。
- 验证结果: `npm test` 当前 74/74 通过；公网 `challenge` 可用、游客 Dashboard 零消耗、普通 `/admin.html` 返回 404。

### 文件变更
- `apps/frist-api/server/server.js` — 增加验证码/限流、隐藏管理页入口、上游字段清洗、低库存通知、会话粘滞和库存优先级链路
- `apps/frist-api/src/core.js` — 统一生成 Frist-API 品牌 CC Switch 导入配置，避免上游供应商信息泄露到用户端
- `apps/frist-api/src/app.js` — 右上角账户菜单接入验证码挑战和用户链路低密度展示
- `apps/frist-api/src/serverClient.js` — 接入 `/api/frist/challenge` 并提交验证码字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖订单文本清洗、日卡/小时卡优先级、用户/管理端解耦和验证码接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖注册验证码、限流、隐藏管理页、模型分组、认证字段、日卡轮转、会话粘滞、流式透传和低库存通知
- `docker-compose.frist-api.yml` — 暴露隐藏管理入口码、验证码、限流和低库存 Webhook 环境变量
- `apps/frist-api/deploy/production.env.example` — 同步公开部署安全环境变量
- `apps/frist-api/deploy/smoke-test.sh` — 冒烟检查新增验证码和隐藏管理入口验证
- `docs/025-frist-api-quickstart.md` — 更新当前用户/管理/网关完整链路
- `docs/026-frist-api-tencent-deploy.md` — 更新腾讯云公开验收与隐藏管理入口说明
- `docs/081-frist-api-public-snapshot-2026-05-02.md` — 归档公网用户端浏览器快照，避免根目录散落文档
- `docs/060-health.md` — 更新 Frist-API 当前测试数和 HI-829
- `docs/061-handoff.md` — 更新当前交接状态
- `docs/002-changelog.md` — 记录本次公开可测链路收口

## [2026-05-02] Frist-API 用户端降噪与五客户端导入配置
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-828

### 变更内容
- 用户端降噪: 移除客户页左侧导航、不可点击分组文字、旧版高密度说明和管理端暗示，首页只固定保留余额、模型消耗、Claude/OpenAI 连通性和导入入口。
- 首屏默认值: 公开 HTML 初始状态改为未登录、0 元和 `FA` 标识，避免后端数据加载前闪现演示套餐或演示消耗。
- 充值页: 三个充值选项改为三列排列，去掉桌面端第四列空位，让日卡、月卡、余额更像独立购买入口。
- 游客页: 未登录状态不再用演示模型消耗填空，余额、消耗和调用统计保持 0，避免客户误以为已有历史账单。
- 导入配置: CC Switch 导入参数扩展为 Claude、Codex、OpenCode、OpenClaw、Hermes 五个客户端，导入链接带 provider、请求地址、模型、auth.json 和 config.toml。
- 解耦边界: 注册/登录收进右上角账户菜单，API 页面只保留创建 Key、开关 Key 和请求地址；补号、价格解析、号源库存继续只在 `/admin.html`。
- 回归测试: Frist-API 测试扩展到 60 条，覆盖用户端禁用词、无 sticky/无 sidebar、游客零消耗、首屏低密度、五客户端导入、日卡切换、流式透传和公开模式硬门槛。

### 文件变更
- `apps/frist-api/index.html` — 简化用户端首页、账户入口、API/充值/导入页面和公开初始状态
- `apps/frist-api/src/app.js` — 接入低密度首页渲染、右上角账户菜单、充值计划和服务端导入链接刷新
- `apps/frist-api/src/serverClient.js` — 游客 Dashboard 归一化为零余额、零消耗和零调用
- `apps/frist-api/server/server.js` — 游客 Dashboard 补齐零消耗字段
- `apps/frist-api/src/core.js` — 扩展五客户端 CC Switch 导入配置和 Codex/OpenCode 手动配置生成
- `apps/frist-api/src/data.js` — 简化充值档位和默认导入目标
- `apps/frist-api/src/styles.css` — 移除 sticky/侧栏样式，调整低密度首屏和充值三列布局
- `apps/frist-api/tests/core.test.mjs` — 增加用户端降噪、首屏默认值和五客户端导入回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 同步用户/管理端解耦和导入配置测试
- `apps/frist-api/tests/new-api-adapter.test.mjs` — 增加游客零消耗归一化回归测试
- `apps/frist-api/tests/server.test.mjs` — 增加游客 Dashboard 零消耗回归测试
- `docs/025-frist-api-quickstart.md` — 同步当前公开用户链路和低密度页面结构
- `docs/031-command-registry.md` — 同步 Frist-API 当前真实 Web 操作入口
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 更新 UI 方向和当前实现边界
- `docs/060-health.md` — 更新 Frist-API 测试数和 HI-828
- `docs/061-handoff.md` — 写入当前公网同步交接
- `docs/002-changelog.md` — 记录本次用户端降噪

## [2026-05-01] Frist-API 腾讯云公网验收部署
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `Frist-API`, `Docker`, `Tencent Cloud`
> 关联问题: HI-827

### 变更内容
- 公网验收: 将 Frist-API 部署到腾讯云小服务器，临时开放 `5566` 端口供陌生用户访问和业务链路实测。
- 安全配置: 服务器端生成强随机管理员令牌和会话密钥，生产模式关闭演示充值和验证码回显；临时公网 HTTP 仅用于无域名阶段验收。
- 健康检查: Docker 健康检查从 `localhost` 改为 `127.0.0.1`，避免 Alpine 先解析 IPv6 `::1` 导致服务可访问但容器误报 `unhealthy`。
- 验证结果: 本机外网访问用户端和管理端均返回 `200 OK`，服务器 Docker 状态为 `healthy`，Frist-API 回归测试维持 52/52 通过。

### 文件变更
- `docker-compose.frist-api.yml` — 修正容器健康检查地址为 IPv4 loopback
- `docs/025-frist-api-quickstart.md` — 同步临时公网验收和健康检查说明
- `docs/026-frist-api-tencent-deploy.md` — 同步腾讯云临时验收端口和健康检查注意事项
- `docs/060-health.md` — 更新 Frist-API 公网验收状态
- `docs/002-changelog.md` — 记录本次公网部署

## [2026-05-01] Frist-API 公开网关生产化加固
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Docker`, `docs`
> 关联问题: HI-827

### 变更内容
- 会话粘滞: 网关支持 `x-frist-session-id`、`x-conversation-id` 和请求体 `metadata.frist_session_id`，同一对话优先固定到同一枚健康上游 Key，补入更快 Key 不会打断当前上下文。
- 故障切换: 上游余额不足、5xx 或网络失败时会清掉当前会话粘滞记录，切换到备用 Key，并完整保留原始 `messages`、`tools`、`metadata` 等请求体。
- 流式透传: `stream: true` 改为边读边转发上游 SSE 数据，不再把流式响应缓冲到结束后一次性返回。
- 计费策略: 流式请求按预估消耗先扣费，非流式请求继续优先按上游 `usage` 精确扣费。
- 生产硬门槛: `NODE_ENV=production` 或 `FRIST_API_PUBLIC_MODE=1` 时，默认管理员令牌、默认会话密钥、验证码回显、演示充值或本地 HTTP 网关地址会直接拒绝启动。
- 临时公网验收: 增加 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1` 显式开关，允许无域名阶段用公网 IP 做短期验收；正式付费用户仍要求 HTTPS 域名。
- 回归测试: Frist-API 测试扩展到 52 条，覆盖会话粘滞、上下文保留、流式首包透传和公开模式安全配置。

### 文件变更
- `apps/frist-api/server/server.js` — 增加网关会话粘滞、流式透传、故障切换粘滞清理和公开模式配置校验
- `apps/frist-api/tests/server.test.mjs` — 增加公开网关生产化回归测试
- `apps/frist-api/deploy/production.env.example` — 增加生产模式和公开模式环境变量
- `docker-compose.frist-api.yml` — 暴露 `NODE_ENV` 和 `FRIST_API_PUBLIC_MODE` 配置
- `docs/025-frist-api-quickstart.md` — 同步会话粘滞、流式透传、公开模式硬门槛和测试覆盖
- `docs/026-frist-api-tencent-deploy.md` — 同步服务器上线检查项
- `docs/060-health.md` — 更新 Frist-API 当前状态和 HI-827
- `docs/002-changelog.md` — 记录本次公开网关生产化加固

## [2026-05-01] Frist-API 用户端商业化 UI 重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 用户首页: 从高密度数据控制台改成商业化客户首页，首屏只固定展示今日费用、今日剩余额度和线路状态 3 个核心指标。
- 视觉风格: 去掉左侧 Logo 黑色块，改成抽象轻量标识；页面加入深绿、珊瑚、薄荷、暖白的层次色、玻璃面板和拟物阴影。
- 导航体验: 左侧导航补充分组隔断，所有用户侧入口统一为 hash 路由和 `data-route` 钩子，避免“有的能点有的不能点”的错觉。
- 渐进披露: 首页新增状态轮播、三步快捷入口、Claude/OpenAI 快速连通性和可展开模型消耗明细，减少一屏堆满信息。
- 动效: 增加首屏进入动画、轮播切换、轻微浮动和按钮按压反馈，并保留 `prefers-reduced-motion` 降级。
- 解耦边界: 用户端继续不出现补号、号商、价格解析和管理端入口；管理端 `/admin.html` 不改动。
- 回归测试: Frist-API 测试扩展到 48 条，新增客户首页降噪结构、导航可点击契约和动效钩子测试。

### 文件变更
- `apps/frist-api/index.html` — 重构用户端首页、Logo、导航隔断、轮播、核心指标和渐进展开区
- `apps/frist-api/src/app.js` — 增加首页轮播、自动切换和明细展开交互
- `apps/frist-api/src/styles.css` — 重做用户端视觉层次、玻璃/拟物面板、动画和响应式样式
- `apps/frist-api/tests/core.test.mjs` — 增加用户端商业化 UI 边界测试
- `docs/025-frist-api-quickstart.md` — 同步新用户端结构、截图和测试覆盖
- `docs/031-command-registry.md` — 登记新增轮播和展开交互入口
- `docs/060-health.md` — 更新 Frist-API 测试数
- `docs/002-changelog.md` — 记录本次用户端 UI 重构

## [2026-05-01] Frist-API 公开能用链路打通
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 补号助手: 新增代理请求地址，补号时会对直连和代理做低成本聊天探测，自动选择成功率更高且延迟更低的路径。
- 网关路由: 上游调用优先使用补号探测得到的 `routeBaseUrl`，适配弱服务器只中转、不推理的公开试用策略。
- 模型探测: 上游不支持 `/models` 时，系统会按内置模型清单逐个低成本探测，只写入实际可用模型。
- 价格扣费: 管理端粘贴价格文本后，上游返回 `usage` 时会按输入/输出 token 和销售价扣用户套餐、加油包和上游库存。
- 日卡切换: Key 额度不足、上游余额不足、上游 5xx 或网络失败时继续自动摘除并切同池健康 Key；日卡套餐过期会清空套餐额度并切回默认套餐。
- 管理端解耦: 代理路径和库存标签只在 `/admin.html` 展示，用户端继续只保留模型消耗、Claude/OpenAI 连通性、API、充值和 CC Switch 导入。
- 回归测试: Frist-API 测试扩展到 45 条，覆盖代理/直连择优、fallback 模型探测和按真实 usage 扣费。

### 文件变更
- `apps/frist-api/server/server.js` — 增加代理路径择优、fallback 模型探测、`routeBaseUrl` 转发和按上游 usage 计费
- `apps/frist-api/admin.html` — 增加代理请求地址输入
- `apps/frist-api/src/admin.js` — 管理端提交代理地址并展示直连/代理库存标签
- `apps/frist-api/tests/server.test.mjs` — 增加代理转发、fallback 探测和 usage 扣费回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 锁定代理字段只存在于管理端
- `docs/025-frist-api-quickstart.md` — 同步公开能用链路
- `docs/026-frist-api-tencent-deploy.md` — 同步弱服务器上线检查
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 同步当前实现边界和交接提示
- `docs/031-command-registry.md` — 登记管理端代理地址入口
- `docs/060-health.md` — 更新 Frist-API 测试数和已修复技术债
- `docs/061-handoff.md` — 写入本轮交接状态
- `docs/002-changelog.md` — 记录本次公开能用链路打通

## [2026-05-01] Frist-API 公开试用业务安全加固
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 充值链路: 公开环境默认不再允许用户自助点击按钮直接增加余额；用户侧改为生成待处理充值单，管理端按邮箱人工确认入账。
- 管理端: 新增人工充值入口和 `/api/admin/customers/recharge` 接口，适配先人工收款、再后台加余额的早期运营方式。
- 兑换码: 日卡/月卡/加油包兑换码改为一次性使用，避免同一张卡被多个用户重复兑换。
- 日卡过期: 网关路由前会检查日卡/月卡到期时间，过期后清空套餐额度并切回默认套餐，防止旧卡继续走日卡池。
- 补号探测: 同一请求地址先做一次模型列表探测，再逐个 Key 做最低成本聊天健康检查，减少重复探测。
- 用户连通性: 用户侧模型连通性按模型聚合显示可用线路数量，不再把每枚上游 Key 当成一张客户状态卡。
- 部署: Docker 和生产环境模板默认关闭演示充值，避免公开部署时误开放免费额度。
- 回归测试: Frist-API 测试扩展到 42 条，覆盖待处理充值单、管理员入账、一次性兑换码、日卡过期、模型聚合连通性和补号低成本探测。

### 文件变更
- `apps/frist-api/server/server.js` — 增加待处理充值单、管理员人工入账、兑换码防复用、套餐过期、低成本探测和模型聚合健康摘要
- `apps/frist-api/index.html` — 将用户充值文案改为充值申请
- `apps/frist-api/admin.html` — 增加人工入账表单
- `apps/frist-api/src/app.js` — 用户侧充值按钮改为提交待处理充值单
- `apps/frist-api/src/admin.js` — 接入管理员人工入账接口
- `apps/frist-api/tests/server.test.mjs` — 扩展公开业务链路回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 锁定管理端人工入账入口和用户端解耦
- `apps/frist-api/deploy/production.env.example` — 增加演示充值关闭开关
- `Makefile` — 本地 Frist-API 开发启动默认回显验证码、关闭演示充值
- `docker-compose.frist-api.yml` — 生产默认关闭演示充值
- `docs/025-frist-api-quickstart.md` — 同步公开试用充值和补号规则
- `docs/026-frist-api-tencent-deploy.md` — 同步上线前检查
- `docs/031-command-registry.md` — 登记 Frist-API 管理端人工入账入口
- `docs/060-health.md` — 更新 Frist-API 当前状态
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开试用业务安全加固

## [2026-05-01] Frist-API 公开能用链路加固
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 用户链路: 新增邮箱密码登录，重复注册会被拦截，用户端不再预填演示密码。
- 计费链路: 网关成功调用后真实扣减套餐额度和加油包额度；余额不足会在访问上游前拦截。
- 日卡切换: 除额度不足外，上游 5xx 或网络失败也会自动切到同池下一枚健康 Key，并记录管理审计。
- 补号补充: 同一请求地址下重复补同一枚上游 Key 会恢复原库存记录，不再重复堆积。
- 补号探测: 管理端支持自动探测、严格探测和信任写入；未填写模型时可通过 `/models` 自动探测并过滤坏 Key。
- 管理端: 增加探测模式选择和最近操作审计列表，库存和审计继续只在管理端展示。
- 部署: 增加生产环境变量模板、冒烟脚本和腾讯云小服务器部署说明。
- 回归测试: 扩展服务端和页面链路测试，覆盖登录、真实扣费、余额拦截、坏 Key 过滤、故障切换和补货恢复。

### 文件变更
- `apps/frist-api/server/server.js` — 增加登录、真实扣费、补号探测、库存恢复、故障切换和审计事件
- `apps/frist-api/src/serverClient.js` — 增加用户端登录接口
- `apps/frist-api/index.html` — 增加登录按钮并移除演示密码预填
- `apps/frist-api/src/app.js` — 接入登录流程
- `apps/frist-api/admin.html` — 增加探测模式和审计区域
- `apps/frist-api/src/admin.js` — 发送探测模式并渲染补号审计
- `apps/frist-api/src/styles.css` — 增加管理端审计列表样式
- `apps/frist-api/tests/server.test.mjs` — 扩展公开可用后端链路测试
- `apps/frist-api/tests/business-flow.test.mjs` — 扩展用户端/管理端页面接线测试
- `apps/frist-api/deploy/production.env.example` — 新增生产环境变量模板
- `apps/frist-api/deploy/smoke-test.sh` — 新增部署冒烟检查脚本
- `docker-compose.frist-api.yml` — 补充公开网关地址和探测超时环境变量
- `docs/025-frist-api-quickstart.md` — 同步公开试用链路和部署边界
- `docs/026-frist-api-tencent-deploy.md` — 新增腾讯云小服务器部署准备说明
- `docs/113-frist-api-public-usable-user-2026-05-01.png` — 保存用户端浏览器验证截图
- `docs/112-frist-api-public-usable-admin-2026-05-01.png` — 保存管理端浏览器验证截图
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 更新当前公开试用后端边界
- `docs/060-health.md` — 更新 Frist-API 当前状态
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开可用链路加固

## [2026-05-01] Frist-API 公开试用链路后端
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Makefile`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 轻量后端: 新增 Node HTTP 服务，跑通用户注册、邮箱验证、充值、兑换码、创建 Key、Key 开关、Dashboard 和 CC Switch 导入接口。
- 中转网关: 新增 `/v1/chat/completions`，用户使用 `fk-live-*` 鉴权后按套餐池路由到上游 Key。
- 日卡切换: 日卡池 Key 额度不足会自动跳过；上游返回余额不足时自动标记当前 Key 耗尽并重试同池下一枚健康 Key。
- 管理端: 新增独立 `/admin.html` 补号工作台，支持管理员令牌、请求地址、池子、模型、Key 列表、价格文本和脱敏库存查看。
- 用户端接线: 用户页面优先调用轻量后端，失败时保留演示数据兜底；用户端继续不展示补号、号源和价格解析入口。
- 部署: `make frist-api-dev` 改为启动完整链路；Docker 原型改为 256MB Node 服务，适配弱服务器小范围试用。
- 回归测试: 新增服务端链路和管理端解耦测试，覆盖注册到导入、补号写入、上游脱敏和日卡自动切换。

### 文件变更
- `apps/frist-api/server/server.js` — 新增轻量 Frist-API HTTP 后端和 `/v1` 中转网关
- `apps/frist-api/src/serverClient.js` — 新增用户端浏览器 API 客户端和 Dashboard 归一化
- `apps/frist-api/src/app.js` — 用户端业务按钮优先调用真实后端，失败时回退演示状态
- `apps/frist-api/admin.html` — 新增独立管理端补号工作台
- `apps/frist-api/src/admin.js` — 新增管理端补号和库存查看逻辑
- `apps/frist-api/src/styles.css` — 新增管理端布局和响应式样式
- `apps/frist-api/tests/server.test.mjs` — 新增服务端完整链路测试
- `apps/frist-api/tests/business-flow.test.mjs` — 新增管理端独立页面边界测试
- `apps/frist-api/package.json` — 默认启动轻量后端，保留静态预览命令
- `.gitignore` — 忽略 Frist-API 本地运行数据，避免误提交用户 Key 或上游 Key
- `Makefile` — `frist-api-dev` 改为完整链路启动，新增 `frist-api-static`
- `docker-compose.frist-api.yml` — 改为轻量 Node 服务和 JSON 运行数据卷
- `docs/025-frist-api-quickstart.md` — 更新本地启动、管理端和公开试用边界
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 补充公开试用后端实现边界
- `docs/114-frist-api-public-user-2026-05-01.png` — 保存用户端浏览器验证截图
- `docs/111-frist-api-public-admin-2026-05-01.png` — 保存管理端浏览器验证截图
- `docs/001-project-map.md` — 更新 Frist-API 项目登记
- `docs/031-command-registry.md` — 登记 Frist-API Web 操作入口
- `docs/060-health.md` — 登记并关闭 Frist-API 首页 403 回归
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开试用链路落地

## [2026-05-01] Frist-API 完整业务链路 MVP
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 业务链路: 新增 Frist-API 用户业务状态机，跑通注册、邮箱验证、充值、兑换码、创建 Key、开启/关闭 Key 和 CC Switch 导入。
- 用户页面: 在 API 管理页加入最小账户注册与邮箱验证入口，让网页端也能串起“注册 -> 充值 -> 创建 Key -> 导入”的闭环。
- Key 管理: API Key 列表改为按每个 Key 自己的启停状态渲染，避免多个 Key 时被全局状态误导。
- 管理链路: 新增补号报告、价格草稿、号源档案写入和日卡额度不足自动切换的可测试核心逻辑，仍保持管理端内容不进入用户页。
- 回归测试: 新增业务链路测试，覆盖用户主流程、补号应用、日卡自动切换、页面业务按钮和用户/管理端解耦边界。
- 文档: 更新快速启动、MVP 设计和会话交接，明确当前为本地模拟业务状态，真实写接口下一步接入 New-API fork。

### 文件变更
- `apps/frist-api/src/businessFlow.js` — 新增 Frist-API 用户与补号业务状态机
- `apps/frist-api/src/app.js` — 接入注册、验证、充值、兑换码、创建 Key、Key 开关、连通性刷新和 CC Switch 导入
- `apps/frist-api/index.html` — 新增用户侧注册与邮箱验证入口
- `apps/frist-api/src/styles.css` — 新增账户链路表单样式
- `apps/frist-api/tests/business-flow.test.mjs` — 新增完整业务链路回归测试
- `docs/025-frist-api-quickstart.md` — 同步当前业务闭环和验证方式
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 记录当前业务链路实现边界
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次业务链路落地

## [2026-05-01] Frist-API 接入 New-API 前端适配层
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `New-API`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 数据接线: 新增 New-API 会话客户端和 Frist-API 数据仓库，用户控制台优先读取 New-API，接口不可用时回退演示数据。
- 归一化: 支持 New-API 用户余额、Token、用量日志和脱敏连通性快照转换为客户侧展示字段。
- 安全边界: 前端不发送管理员密钥，不暴露上游 Key、渠道 ID、号商地址等管理端字段。
- 页面接线: `app.js` 从硬编码演示数组改为通过数据仓库渲染，保留本地静态预览能力。
- Docker: 为 Frist-API 站点增加 Nginx 代理配置，同域 `/api/` 和 `/v1/` 转发到 New-API 容器。
- 测试: 新增 New-API 适配器测试，覆盖响应包装、缺失接口回退、Token 脱敏、用量分组和页面接线。
- 文档: 更新快速启动和 MVP 方案，明确下一步要在 New-API fork 中补齐用户安全接口。

### 文件变更
- `apps/frist-api/src/newApiClient.js` — 新增 New-API 会话客户端、数据仓库和归一化函数
- `apps/frist-api/src/app.js` — 页面改为优先读取数据仓库并保留演示数据兜底
- `apps/frist-api/deploy/nginx.conf` — 新增 Docker 站点代理配置
- `apps/frist-api/tests/new-api-adapter.test.mjs` — 新增 New-API 适配层回归测试
- `docker-compose.frist-api.yml` — 挂载 Frist-API Nginx 代理配置
- `docs/025-frist-api-quickstart.md` — 说明当前数据接入方式和下一步
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 同步当前前端适配边界
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次适配层接入

## [2026-05-01] Frist-API 参考 Tabcode 的用户控制台迭代
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- UI: 登录参考 `tabcode.cc/dashboard` 后，将 Frist-API 从单页堆叠改为分区式客户控制台，默认只展示仪表板。
- 信息架构: 借鉴客户侧分组导航，拆成控制台、API 与用量、模型与渠道、充值与订购、支持，继续保持管理端完全不暴露。
- 连通性: 将 Claude / OpenAI 状态卡升级为对话延迟、端点 Ping、官方状态、7 天可用性和历史状态条。
- 降噪: 合并重复的“使用统计”导航入口，并将慢速状态文案从“拥堵”调整为“可用较慢”。
- API/充值/导入: 增加 API Key 列表、充值金额按钮、兑换码入口、客户端下载和五目标 CC Switch 导入视图。
- 测试: 扩展用户端边界测试，锁定客户侧必要入口和连通性可观测字段。
- 文档: 更新快速启动指南，说明新的分区式用户端结构。

### 文件变更
- `apps/frist-api/index.html` — 改为分区式用户控制台
- `apps/frist-api/src/core.js` — 调整客户侧连通性状态文案
- `apps/frist-api/src/app.js` — 增加 hash 视图路由、API/充值/状态卡渲染
- `apps/frist-api/src/data.js` — 补充 API Key、充值、帮助、渠道可用性模拟数据
- `apps/frist-api/src/styles.css` — 重做分区控制台、状态卡和移动端样式
- `apps/frist-api/favicon.svg` — 更新抽象品牌图标
- `apps/frist-api/tests/core.test.mjs` — 增加分区导航和连通性字段测试
- `docs/025-frist-api-quickstart.md` — 同步当前可见能力
- `docs/002-changelog.md` — 记录本次参考站迭代

## [2026-05-01] Frist-API 用户端 UI 解耦重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- UI: 按用户反馈重构 Frist-API 为纯用户控制台，移除首屏中的管理端、补号助手、价格解析和号源归类信息。
- 信息架构: 用户端只保留模型消耗、Claude/OpenAI 渠道连通性、API 管理、充值入口和 CC Switch 导入。
- 品牌: 重做 Frist-API 抽象 Logo 和 favicon，使用黑白基础与红色识别点，降低视觉噪音。
- 测试: 新增用户端边界测试，确保管理端内容不会再次出现在用户页面。
- 文档: 更新快速启动指南，说明用户端与管理端分离。

### 文件变更
- `apps/frist-api/index.html` — 重构用户端页面结构
- `apps/frist-api/src/app.js` — 重写用户端渲染逻辑
- `apps/frist-api/src/data.js` — 调整用户端模拟数据
- `apps/frist-api/src/styles.css` — 重做用户端视觉和响应式样式
- `apps/frist-api/favicon.svg` — 更新抽象品牌图标
- `apps/frist-api/tests/core.test.mjs` — 增加用户端/管理端解耦测试
- `docs/025-frist-api-quickstart.md` — 同步用户端范围说明
- `docs/002-changelog.md` — 记录本次 UI 解耦重构

## [2026-05-01] Frist-API 网站雏形落地
> 领域: `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API`, `Makefile`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 网站: 新增 `apps/frist-api/` 独立静态网站雏形，首屏覆盖账单卡、API Key、五目标 CC Switch 导入、模型连通性、补号助手和价格解析。
- 逻辑: 新增可测试核心逻辑，覆盖请求地址归一化、CC Switch 导入链接、价格解析、直连/代理推荐、日卡 Key 自动切换和用户侧模型健康摘要。
- 部署: 新增 `docker-compose.frist-api.yml`，本地同时启动 Frist-API 网站和 New-API 核心原型。
- 命令: Makefile 增加 `frist-api-test`、`frist-api-dev`、`frist-api-up`、`frist-api-down`。
- 文档: 新增快速启动指南，并在项目地图登记 Frist-API 原型位置。

### 文件变更
- `apps/frist-api/index.html` — Frist-API 网站雏形页面
- `apps/frist-api/favicon.svg` — Frist-API 网站图标
- `apps/frist-api/src/core.js` — 核心业务逻辑
- `apps/frist-api/src/app.js` — 页面交互和模拟数据绑定
- `apps/frist-api/src/data.js` — 首屏模拟数据
- `apps/frist-api/src/styles.css` — 黑白账单控制台样式
- `apps/frist-api/tests/core.test.mjs` — 核心逻辑回归测试
- `apps/frist-api/package.json` — 本地测试和预览脚本
- `docker-compose.frist-api.yml` — Frist-API 原型 Docker 入口
- `Makefile` — 增加 Frist-API 本地命令
- `docs/025-frist-api-quickstart.md` — 新增快速启动指南
- `docs/001-project-map.md` — 登记 Frist-API 应用位置
- `docs/002-changelog.md` — 记录本次网站雏形落地

## [2026-05-01] Frist-API 盈利中转站 MVP 设计落地
> 领域: `docs` | `ai-pool`
> 影响模块: `Frist-API`, `New-API`, `docs/specs`, `handoff`
> 关联问题: Frist-API-MVP

### 变更内容
- 方案: 将公开收费 API 中转站命名为 `Frist-API`，定位为独立网站和盈利渠道，不改 OpenClaw APP 现有 New API 内部管理页面。
- 架构: 明确 Frist-API 只做中转、鉴权、计费、日志和号源管理，不使用本机硬件做模型推理，适配弱服务器部署。
- 用户端: 固化注册、充值、创建 Key、开启/关闭 Key、选择导入位置、CC Switch 导入的完整流程，导入目标覆盖 Claude、Codex、OpenCode、OpenClaw、Hermes。
- 管理端: 设计按请求地址归类的补号助手，支持模型列表缓存、Key 低成本检测、上游不支持模型列表时的降级探测。
- 价格: 设计粘贴式价格解析流程，支持币种/计费单位识别、美元/人民币换算、利润倍率、安全垫和人工确认。
- 号源: 补充上游号商模板、直连/代理测速、模型连通性缓存和用户侧可用性展示。
- 套餐: 补充日卡、月卡、默认池隔离，以及日卡 Key 额度耗尽后的自动摘除和同组切换策略。
- 交接: 写入可直接交给下一位执行者的提示词，包含实现边界、优先级和验证要求。

### 文件变更
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 新增 Frist-API MVP 设计文档和交接提示词
- `docs/061-handoff.md` — 写入本轮 Frist-API 交接摘要
- `docs/002-changelog.md` — 记录本次方案文档落地

## [2026-05-01] 质量优化: API 边界异常链路清理
> 领域: `backend` | `docs`
> 影响模块: `api/routers/cli`, `api/routers/pool`, `api/routers/shopping`, `docs`
> 关联问题: TD-005

### 变更内容
- 维护性: 为 CLI、API 池和购物比价路由的异常转换补充 `raise ... from e`，保留原始异常链，方便排查问题。
- 行为保持: 接口状态码、错误文案和日志级别不变，仅提升故障定位信息。
- 技术债: 全仓 Ruff 历史问题从 552 降到 547，B904 剩余项从 93 降到 88。

### 文件变更
- `packages/clawbot/src/api/routers/cli.py` — 3 个端点补充异常链
- `packages/clawbot/src/api/routers/pool.py` — API 池统计错误转换补充异常链
- `packages/clawbot/src/api/routers/shopping.py` — 购物比价错误转换补充异常链
- `docs/060-health.md` — 同步 TD-005 剩余技术债计数
- `docs/002-changelog.md` — 记录本次质量优化

## [2026-05-01] 质量优化: monitor 路由 lint 清理
> 领域: `backend` | `docs`
> 影响模块: `api/routers/monitor`, `docs`
> 关联问题: TD-004, TD-005

### 变更内容
- 维护性: 清理 monitor 路由中的歧义变量名和未使用循环变量，消除当前文件 Ruff 告警。
- 可靠性: 后台翻译任务保留任务引用并在结束时移除，避免异步任务被静默丢弃。
- 清理: 将后台翻译调度失败的空占位改为 debug 日志，保持接口返回行为不变。
- 技术债: 全仓 Ruff 历史问题从 555 降到 552，源码 `pass` 语句从 64 降到 63。

### 文件变更
- `packages/clawbot/src/api/routers/monitor.py` — 清理 3 项机械 lint 问题和 1 个空异常占位
- `docs/060-health.md` — 同步 TD-004/TD-005 剩余技术债计数
- `docs/002-changelog.md` — 记录本次质量优化

## [2026-05-01] 质量优化: 测试入口、RPC 去重与文档入口修正
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Makefile`, `api/rpc`, `bot mixins`, `social adapters`, `requirements-dev`, `docs`
> 关联问题: HI-821, HI-822, HI-823

### 变更内容
- 架构: 梳理后端主数据流，确认 API/Telegram 共享 `ClawBotRPC` 聚合层，优先优化共用热点。
- 维护性: `Makefile` 的 Python 探测改为优先使用项目 `.venv312`，避免系统 Python 无 pytest 时测试入口失效。
- 重复代码: 提取 yfinance 批量价格补齐 helper，统一 IBKR 价格兜底和本地持仓价格兜底。
- 重复代码: 提取社媒 Cookie 状态 helper，统一 X/Twitter 与小红书登录状态检测。
- 清理: 去掉 `CircuitOpenError` 的空 `pass`，将抽象风控校验器中的 `...` 改为明确异常。
- 清理: 去掉命令聚合类、安全异常和 SDK 降级路径中的空占位语句，抽象策略/社媒适配器改为明确 `NotImplementedError`。
- 文档: 同步 AGENTS/SOP/索引中的文档路径到当前真实文件名，修复旧归档链接和不存在的索引项。
- 文档: 用 AST 扫描真实语法占位，剩余 64 个历史 `pass` 登记为 TD-004，后续按模块分批审查。
- 工具链: `requirements-dev.txt` 补齐 `ruff`，让 `make lint` 不再依赖未声明工具。
- 工具链: 安装 Ruff 后 `make lint` 已进入真实检查阶段，暴露 555 个历史 lint 问题，登记为 TD-005 分批处理。
- 测试: 新增 API 回归测试覆盖价格 helper 去重、previous_close 兜底和 Cookie 文件格式识别。

### 文件变更
- `Makefile` — Python 探测优先项目虚拟环境
- `packages/clawbot/src/api/rpc.py` — 提取价格补齐与社媒 Cookie 检测 helper
- `packages/clawbot/src/http_client.py` — 清理异常类空占位
- `packages/clawbot/src/risk_validators.py` — 抽象方法改为明确 `NotImplementedError`
- `packages/clawbot/src/bot/cmd_basic/__init__.py` — 去掉命令聚合类空占位
- `packages/clawbot/src/bot/cmd_execution_mixin.py` — 去掉执行命令聚合类空占位
- `packages/clawbot/src/core/security.py` — 清理安全异常空占位
- `packages/clawbot/src/execution/social/platform_adapter.py` — 抽象社媒适配器改为明确未实现异常
- `packages/clawbot/src/strategy_engine.py` — 抽象策略分析改为明确未实现异常
- `packages/clawbot/src/tools/deepgram_stt.py` — SDK 缺失降级路径增加调试日志
- `packages/clawbot/src/tools/fal_client.py` — SDK 缺失降级路径增加调试日志
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加行为锁定回归测试
- `packages/clawbot/requirements-dev.txt` — 补齐 Ruff 开发依赖
- `AGENTS.md` — 同步项目导航与文档命名规范到当前文件布局
- `docs/003-docs-index.md`, `docs/001-project-map.md`, `docs/043-update-protocol.md`, `docs/040-docs-first-protocol.md`, `docs/023-disaster-recovery.md`, `docs/032-dependency-map.md` — 修正文档入口路径和依赖登记
- `docs/060-health.md` — 登记 HI-821/HI-822/HI-823 和最新测试状态
- `docs/002-changelog.md` — 记录本次质量优化

## 最近更新（2026-04）

## [2026-04-28] Git 全历史密钥扫描 + 本地风险清理
> 领域: `infra` | `docs`
> 影响模块: Git history, .gitignore, security scan, local runtime cache
> 关联问题: HI-817, HI-818, HI-819

### 变更内容
- 安全: 使用 gitleaks、trufflehog、detect-secrets 对当前工作区、本机 ignored 文件和 1217 个 Git 历史提交做密钥扫描。
- 安全: 确认公开历史曾包含 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json`、sqlite 数据库等敏感痕迹；记录为待轮换密钥 + 待历史重写。
- 安全: 从 Git 索引移除 `.openclaw/iflow_key_timestamp.json`, 并补充根 `.gitignore` 规则。
- 安全: 执行 `git-filter-repo` 全历史重写, 清除敏感配置、设备配对文件、数据库、`.env`、旧依赖、构建产物和样例凭据噪音。
- 安全: 清理后 `gitleaks` Git 全历史扫描 0 命中, `trufflehog` Git 全历史扫描 0 verified / 0 unverified。
- 清理: 删除可重建本地产物约 4.4GB，包括前端 `node_modules`、Tauri `target`、Python venv、子项目 venv、日志文件。
- 清理: 删除本机浏览器 profile 中确认含 Gemini API key 痕迹的临时 LevelDB 日志。
- Git: 运行 `git gc --prune=now`, 本地松散对象清零。
- 文档: 新增密钥扫描报告, 更新 HEALTH 安全状态。

### 文件变更
- `.gitignore` — 增加 `.openclaw/iflow_key_timestamp.json` 与本地扫描报告忽略规则
- `.openclaw/iflow_key_timestamp.json` — 从 Git 索引移除, 保留本机文件
- `.pre-commit-config.yaml` — 移除已删除 `.secrets.baseline` 的依赖
- `docs/083-secret-scan-2026-04-28.md` — 新增全量密钥扫描报告
- `docs/060-health.md` — 登记 HI-817/HI-818/HI-819
- `docs/changelog.md` — 记录本次安全扫描与清理

## [2026-04-27] Tauri 桌面端重新构建 + Makefile + iLink Session 修复
> 领域: `frontend` | `infra` | `wechat` | `docs`
> 影响模块: Makefile, wechat_receiver(云端), BUILD_GUIDE
> 关联问题: HI-812, HI-816

### 变更内容
- 构建: 创建项目 Makefile，`make tauri-build` 一键清理+编译+安装+验证
- 构建: 桌面端重新构建，OpenClaw.app 7.8MB 已安装到 /Applications
- 构建: 清理旧版 OpenClaw.app 残留，确认无 OpenEverything.app 双版本
- 云端: iLink Session 过期自动恢复 — 清空轮询游标强制重建 session
- 云端: 诊断 errcode=-14 根因 — iLink bot token 在平台侧失效，需重新扫码
- 文档: 新增 BUILD_GUIDE.md (构建铁律+快速构建+环境要求+常见问题)

### 文件变更
- `Makefile` — 新建，包含 tauri-build/dev/clean + backend-restart/test + cloud-sync
- `docs/guides/BUILD_GUIDE.md` — 新建，桌面端构建必操作指南
- `/opt/openclaw-wechat/wechat_receiver.py`(云端) — session 过期时清空 buf 游标

## [2026-04-26] 全量桌面客户端审计 — 7项Bug修复 + 性能优化 + 三端对齐
> 领域: `backend` | `frontend` | `wechat` | `infra`
> 影响模块: world_monitor, broker_bridge, monitor, log_config, wechat, multi_main
> 关联问题: HI-805~811

### 变更内容
- 后端: 金融指数全零修复(yfinance单个Ticker替代批量请求) + volume数据补全
- 后端: IBKR accountSummary event loop冲突修复(accountSummary→accountSummaryAsync)
- 后端: /monitor/extended超时修复(3个外部API改并发+缓存优先+20s超时保护)
- 后端: loguru配置修复(rotation 10s→50MB) + 清理1800+旧日志文件(168MB)
- 微信: 欢迎消息重写(完整功能速查+分区索引) + cmd_dashboard不可达修复(添加编号107)
- 微信: cmd_iorders差异化格式化 + 完整帮助消息动态生成
- 微信: cmd_status路径修复(/system/status→/status) + 12个命令新增API映射
- 微信: 热点话题(300)专用格式化 + 全球情报(407)嵌套dict展开 + 执行简报(500)映射
- 微信: 全市场扫描(205)改为需要参数 + 全球情报timeout提升至30s
- 性能: Ollama模型常驻9.1GB修复(unload + KEEP_ALIVE=5m自动卸载)
- 审计: Telegram 101命令全对齐 / 微信64命令映射完整 / 桌面端30页面覆盖
- 审计: 全量命令验证 27/27 可用(25✅ 2⚠️数据空 0❌)
- 测试: 1486 passed, 0 failed (零回归)
- 云端: 腾讯云wechat_receiver.py同步(欢迎消息+帮助+服务重启)

### 文件变更
- `src/monitoring/world_monitor.py` — yfinance单个Ticker + volume + 超时25s + warning级别
- `src/broker_bridge.py` — accountSummary→accountSummaryAsync
- `src/api/routers/monitor.py` — extended端点并发+缓存+超时保护
- `src/log_config.py` — loguru rotation改为50MB固定文件名
- `src/api/routers/wechat.py` — 新增_format_intel/_format_topics + 12个API映射 + timeout差异化

## [2026-04-25] 全量审计与优化 Sprint
> 领域: `backend` | `frontend` | `wechat`
> 影响模块: `wechat.py`, `rpc.py`, `world_monitor.py`, `social_browser_worker.py`, `multi_main.py`, 前端 8 个组件
> 关联问题: 全量审计

### 变更内容
- 后端: 修复 /trading/pnl 全零问题(IBKR 离线兜底计算), /trading/dashboard 空数据, /monitor/finance 行情全零(yfinance getattr), /social/analytics 导入错误, /trading/system unknown 状态
- 前端: 修复 Social 页 t 变量遮蔽, ControlCenter 响应检查, usePortfolioAPI 错误处理, 8 个页面轮询优化(useActivePagePolling), Settings 通知硬编码
- 微信: 实现编号命令系统(60+ 命令映射), 欢迎消息, 完整功能列表
- 性能: Chrome V8 堆 512→128MB, 渲染进程限制 3, 自动清理多余标签页, 模块懒加载(browser-use/CrewAI/进化引擎)
- Telegram: 命令全量审计(100/100 通过), 发现 2 个注册表缺失(/claude, /deals)

## [2026-04-25] 内存优化: Chrome 浏览器 + 模块懒加载
> 领域: `backend`, `infra`
> 影响模块: `social_browser_worker`, `multi_main`, `browser_use_bridge`
> 关联问题: PERF-MEM-001
### 变更内容
- Chrome 社交浏览器 V8 堆限制从 512MB 降至 128MB，新增 `--renderer-process-limit=3` 限制渲染进程数，禁用 background networking/extensions/component-update 等冗余功能。预计节省 ~800-1200MB
- 新增 `cleanup_excess_tabs()` 自动清理重复/无用标签页（blob: URL、chrome:// 内部页、重复登录页），每次状态检查时自动触发，标签页上限 4 个
- browser-use、CrewAI、进化引擎改为懒加载模式——启动时不实例化，首次使用时才初始化。预计减少启动内存 ~30-50MB
### 文件变更
- `scripts/social_browser_worker.py` — Chrome 启动参数内存优化 + 标签页清理函数
- `multi_main.py` — browser-use/CrewAI/进化引擎从启动初始化改为延迟加载
- `src/browser_use_bridge.py` — `get_browser_use()` 改为自动懒初始化

## [2026-04-17] 后端 API 新增 + 前端真实数据对接 — 从演示数据到可用系统
> 领域: `backend`, `frontend`
> 影响模块: `api/routers/system`, `api/routers/trading`, `api/server`, `api/routers/conversation`, `tauri.ts`, `Home`, `conversationService`
> 关联问题: 桌面 APP 5 个页面需要从模拟数据切换到后端真实数据
### 变更内容
- **后端新增 4 组 API 端点** — `GET /api/v1/system/daily-brief`（今日简报聚合 metrics + 模块状态）、`GET/POST /api/v1/system/notifications`（通知列表+标记已读+全部已读）、`GET /api/v1/trading/portfolio-summary`（持仓聚合摘要）、`GET /api/v1/system/services`（服务运行状态检测）
- **挂载 Conversation 路由** — `router_conversation` 之前已实现（SSE 流式对话 333 行），但未在 server.py 注册，导致 /api/v1/conversation/* 端点全部 404
- **前端 tauri.ts 新增全部 API 封装** — dailyBrief/notifications/markNotificationRead/markAllNotificationsRead/portfolioSummary/services/serviceStatus + conversation 完整封装（sessions/create/get/delete/send）
- **Home 首页对接真实数据** — 模拟通知替换为 `api.notifications()` + 首页摘要并行请求加入 `api.dailyBrief()`
- **conversationService SSE 修复** — 流式请求从裸 fetch 改为 clawbotFetch（携带 API Token），修复未授权错误
- **回归测试**: 1339 passed, 2 skipped, 0 failures ✓
### 文件变更
- `packages/clawbot/src/api/server.py` — 新增 router_conversation 导入和挂载（2处）
- `packages/clawbot/src/api/routers/system.py` — 31行→~280行，新增 daily-brief/notifications/services 三组端点
- `packages/clawbot/src/api/routers/trading.py` — 151行→~240行，新增 portfolio-summary 端点
- `apps/openclaw-manager-src/src/lib/tauri.ts` — 719行→~820行，新增所有 API 封装函数
- `apps/openclaw-manager-src/src/components/Home/index.tsx` — 模拟通知→真实 API + dailyBrief 数据对接
- `apps/openclaw-manager-src/src/services/conversationService.ts` — SSE fetch→clawbotFetch + 移除废弃 API_BASE

---


...

2026-04 以前的详细审计附件和截图已在 2026-05-03 文档清理中移除，核心变更记录保留在本文。

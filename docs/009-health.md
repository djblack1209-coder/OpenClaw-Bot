# 系统健康状态

> 合并自原 060-health.md + 063-learnings.md + 064-feature-requests.md

---


## 一、当前状态与已知问题

### 社媒运营插件排程与增长复盘 — 提交前验证通过

2026-07-02 提交前收口验证完成：桌面端 Social 中控、Chrome Social Pilot、Telegram 社媒命令、后端 Social API、排程/最终确认、增长复盘和当前页上下文扫描均保持“只生成待审草稿/只读复盘/人工最终确认”的安全边界；仍不自动发布、不自动评论、不关注/私信、不推广。已清理失效生活自动化/微信优惠券与旧 MITM token 相关冗余路径。验证结果：`git diff --check` exit 0；后端 Python 编译通过；后端全量 pytest exit 0（进度日志统计 `1601 passed / 2 skipped / 0 failed`）；桌面端 `npm run build`、Tauri `cargo check`、Social 静态测试、Chrome 插件 Popup/social-core/page-runner 测试和真实浏览器 smoke 均通过。当前需要注意的边界仍是：真实外发/评论动作必须由用户在已登录页面最终人工确认，不能恢复自动外发。

### Bot 心跳丢失误报 — gptoss 已恢复

2026-07-02 05:49 MDT 已处理 `gptoss` 心跳丢失告警。根因是 `gptoss` 在 03:01:44 启动超时后，`MultiBot.__init__` 已提前把它写入健康检查和群聊路由，但启动失败后没有进入运行注册表，也没有注册自动恢复函数，导致健康检查持续报“Bot 心跳丢失 / 未注册重启函数”。现已把 Bot 健康/路由注册移动到 Telegram polling 启动成功之后，并新增回归测试防止缺 Token 或启动失败的 Bot 残留假心跳。重启 `ai.openclaw.clawbot-agent` 后，`GET /api/v1/status` 显示 qwen235b、gptoss、claude_sonnet、claude_haiku、deepseek_v3、claude_opus、free_llm 均 `alive=true`；新日志中 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。


### 公开仓库敏感告警清理 — 已处理当前可达内容

2026-06-22 已开启 GitHub secret scanning / push protection 后，继续清理审核视角下的敏感告警：本地未推送历史、stash、旧本地实验分支和 Codex turn-diff / snapshot refs 中残留的 Google OAuth Client ID/Secret 已删除并 GC；当前 `main` 与 `origin/main` 同步，工作区干净；当前追踪树、可达 Git refs 和工作区均不包含被 GitHub Push Protection 拦截的 OAuth 值。已清理历史生活自动化敏感配置痕迹，公开仓库只保留必要占位符。GitHub 历史 secret alerts 已核对来源，涉及早期误提交的 `.openclaw` 运行配置、`node_modules`、`.venv312`、Telegram/OpenRouter/Slack/Discord/Google/微信等历史值；当前 open secret alerts 为 0，历史 alerts 已按 revoked 处理。后续仍建议在对应平台轮换/废弃这些旧凭证。

### 开源项目审核准备 — 已补齐基础治理材料

2026-06-22 为提高 OpenAI Codex for OSS 等开源项目审核通过率，根目录新增 Apache-2.0 `LICENSE`，`README.md` 已移除旧的私有/专有许可证表述并补充项目定位、可复用开源价值、安全/合规边界和贡献入口；新增 `docs/013-contributing.md`、`docs/014-security.md`、`docs/015-code-of-conduct.md`、GitHub issue/PR 模板，明确贡献流程、验证清单、漏洞报告、社区行为准则、密钥保护和 API credits 只用于 PR review、测试、文档、安全分析、重构维护，不用于真实交易、刷量、绕过平台风控、未授权抓取、商业客户工作负载或转售。已通过 GitHub CLI 更新仓库公开描述、topics、Discussions、secret scanning、push protection、Dependabot security updates 和 private vulnerability reporting。



### Dependabot 依赖安全收口 — 大部分可修项已处理

2026-06-22 打开 Dependabot security updates 后，GitHub 首次暴露 78 个历史依赖告警。本轮已升级 `.openclaw/extensions/openclaw-weixin`、`apps/openclaw-manager-src`、`packages/clawbot/requirements-dev.txt`、`packages/openclaw-npm` 及其扩展包中的可修安全版本；桌面端 `WorldMonitor` 已移除 `react-simple-maps`，改用 `d3-geo` + `topojson-client` 直接渲染本地地图，从根上去掉旧 d3 漏洞链。`@mariozechner/pi-coding-agent` 上游暂无 patched version，且当前源码未直接 import，本轮已从 `packages/openclaw-npm` 直接依赖移除。最终远端 Dependabot 告警数以推送后 GitHub 重新分析为准；本地 `.openclaw/extensions/openclaw-weixin` 和 `apps/openclaw-manager-src` 的 `npm audit --audit-level=moderate` 均为 0。全量测试中发现 `test_api_routes_regression.py` 会被本机 `OPENCLAW_API_TOKEN` 污染成 401，已在测试层固定无 Token 开发模式并用带 token 环境复验 12/12 通过。


# HEALTH — 系统健康状态

> 最后更新: 2026-05-09

---

### X 全自动运营任务 — 已切换为中英文热点追踪涨粉号

2026-06-22 已按用户新方向把 X 自动运营从 AI/视频蒸馏垂直号切换为“中文/英文热点追踪 + 抽象好玩短推”：默认排程设计为 08:30 / 10:30 / 12:30 / 15:00 / 17:30 / 20:30（America/Denver）各尝试发布 1 条。链路现在优先抓微博/百度/知乎真实热榜、B站热榜、Google News 中文/英文 RSS、Hacker News Algolia front page，并用热度、排名、可吐槽性/抽象程度、中英文覆盖和安全风险评分；YouTube RSS/字幕蒸馏保留为低优先级补位，不再作为默认账号方向。此前 2026-06-22 11:35 MDT 已通过同一 LaunchAgent 真实自动发出 1 条推文，取证链接 `https://x.com/BonoDJblack/status/2069112204343779412`。剩余边界：微博/百度/知乎接口偶发超时会自动降级到 B站/HN/Google News；B站仍以标题/热榜级语义为主，若要更准地追评论梗/小红书/微博实时梗，后续建议接入 MediaCrawler 或平台登录态评论采集；为降低 X 风控，当前不做批量关注/评论/点赞。

2026-06-23 已按用户要求切到“先确认人设/内容，再发布”模式：LaunchAgent 当前未加载，`x_auto_morning_post.py --publish-next` 未审核时只返回 `requires_review=true`，不会外发；桌面端 Social 页已能统一看到 X 自动运营草稿并执行“确认内容 / 打回 / 最终发布确认”。热点过滤已追加官方政治口号、硬新闻、核电/战争/枪击和 AI 垂直模型新闻降权/过滤，最新候选草稿保持 `review_status=pending`，等待用户确认人设与内容后再恢复外发。

2026-06-23 追加统一“浏览器运营插件”工作台：后端新增只读聚合接口 `GET /api/v1/social/ops-workspace`，一次返回 X / 小红书 / 闲鱼三平台 SaaS 卡片、审核计数、人设确认、skills 审计和闲鱼客服状态；桌面端 Social 页优先使用该接口，失败再降级旧接口。当前判断：现有 `social-autopilot` Skill 与 `social-persona.md` 仍偏 AI/程序员/效率工具号，和用户想要的“追热点、抽象好玩、最快涨粉”不完全一致，因此继续保持人工确认闸口，不能恢复自动外发。

2026-06-23 继续补齐“先确认人设内容”的产品闭环：新增 `social/persona-review` 人设确认流和 `persona_review.py` 状态文件，工作台会展示“热点抽象观察员”提案、样稿预览、确认/打回按钮。确认人设只保存方向，不会恢复自动外发；内容草稿仍必须逐条确认后才允许进入最终发布确认。

2026-06-23 人设确认卡进一步接入真实待审草稿样稿：`social/ops-workspace` 会把当前 X/小红书待审核草稿整理为 `persona_check.review_samples`，前端优先展示这些真实样稿，避免用户只看静态模板无法判断内容风格。

2026-06-23 继续收紧旧社媒自动驾驶安全边界：`SocialAutopilot` 现在固定处于审核模式，晚间生产出的 X / 小红书草稿默认是 `needs_review/pending`；午间自动回复/蹭评直接跳过；晚间发布任务即使遇到已确认草稿也不会自动外发，只提示到桌面端执行最终发布确认。统一工作台已暴露 `review_mode=true` 与 `external_actions_locked=true`，并把真实待审样稿上限扩到 6 条，平台卡片新增“下一步/样稿预览”。

2026-06-23 补齐浏览器控制插件的安全操作入口：新增 `social/browser-control` 后端 API、Tauri IPC 和桌面端卡片按钮，允许在统一工作台里执行“打开 X / 打开小红书 / 登录 / 刷新状态”等安全动作；同一入口显式拒绝 publish/reply/delete 等外部变更动作，仍必须走草稿审核和最终发布确认。

2026-06-23 追加只读审核包与开源轮子复查：新增 `GET /api/v1/social/review-pack`，一次返回“热点抽象观察员”人设提案、X/小红书真实待审样稿、guardrails、skill 审计和轮子复用判断；当前样稿 `sample_count=8`、`auto_publish_enabled=false`、`requires_owner_review=true`。已复查 `social-autopilot` Skill 和 `social-persona.md`：旧配置仍偏 AI 工具号与全自动互动，不直接启用；继续复用项目内 `sau_bridge`、`media_crawler_bridge`、`social_browser_worker.py`，并确认 GitHub 上 `NanmiCoder/MediaCrawler`（51,767⭐，覆盖小红书/B站/微博等采集）和 `dreammis/social-auto-upload`（12,811⭐，覆盖小红书/YouTube/Bilibili 等上传）可作为后续深度采集/搬运轮子。

2026-06-23 Chrome 插件第一阶段已从 Browser Relay 壳升级为 `OpenEverything Social Pilot`：`manifest.json` 默认打开 `popup.html`，Popup 能识别 X / 小红书 / 闲鱼、启动/暂停本标签页运营状态、同步到后端 `GET/POST /api/v1/social/extension/status`；`options.html` 已变成 no-code SaaS 高级设置页，支持人设标签、主内容模型、网页登录额度优先、生图模型、热点来源、自动化强度、互动强度、本地 API Base URL 和 Relay 兼容配置。当前健康判断：插件已完成“平台识别 + 设置保存 + 状态同步 + 安全闸口”的骨架闭环，但仍未实现页面自动填入、网页登录免费额度自动调用、热点深采集、生图、排程发布和互动；这些能力继续受人工审核闸口保护。

2026-06-23 Chrome 插件继续向“当前页/热点 → 待审草稿”推进：Popup 新增“根据当前页生成待审草稿”，后台只读采集当前标签页标题、选中文本、可见标题/短文本和少量正文摘要，通过 `POST /api/v1/social/extension/drafts` 写入统一社媒草稿审核队列；生成的草稿固定为 `needs_review/pending`，并继续强制 `auto_publish_enabled=false`、`external_actions_locked=true`。后续又补齐插件内审核、热点池、填入点检测、安全填入、待发布排程、插件人设与样稿确认面板、插件排程提醒面板、到点提醒和最终确认：`social-page-runner.js` 可单测验证小红书标题/正文拆分、X compose 合并填入和不点击发布按钮；`POST /api/v1/social/extension/drafts/{draft_id}/schedule` 只把已确认草稿写入 `extension_schedule`，`ops-workspace` 可见排程摘要；排程到点后转为 `awaiting_final_confirmation`，`GET /api/v1/social/extension/schedule` 会把队列和草稿预览同步到插件“看排程”面板，`final-confirm` 仅标记 `ready_for_manual_publish`，仍不调用发布器。当前仍未启用网页登录免费额度、生图、排程外发和自动互动；人设确认只代表方向确认，不等于发布授权，下一步应在真实已登录页面继续校准选择器。

2026-06-23 继续补齐真实页面校准闭环：插件 `socialPageProbe` 完成当前页只读检测后，会把平台、URL、ready、可用字段名和失败原因通过 `POST /api/v1/social/extension/page-probe` 同步到中控 `page_calibration`，并丢弃 selector 等页面细节；Popup 会明确提示“校准结果已同步”或“本地检测成功但未同步中控”。该能力只用于判断 X / 小红书 / 闲鱼页面是否已打开可填输入框，仍不点击发布、发送、评论或关注按钮。

2026-06-23 继续补强真实页面校准稳定性与冷启动闭环：`buildAutofillSelectors()` 已覆盖 X 嵌套 contenteditable / DraftEditor、小红书 Quill `.ql-editor` / aria-placeholder、闲鱼 placeholder / aria-label 聊天编辑器等常见真实页面变体；新增回归确保探测模式只读、不改写内容。App Social 的 `growth_draft_action` 在暂无增长样本时也保持可用，走 `fallback_mode=cold_start_hotspot_pool` 从热点池生成待审草稿；有高信号样本时继续复用增长反馈画像。Playwright 已用当前源码临时 API `127.0.0.1:18791` 截图验证按钮可点击且文案明确“不自动发布、不自动评论”。

2026-06-23 继续补齐产品线 1 的 Telegram 中控审核闭环：新增 `/social_review_drafts`、`/social_review_approve`、`/social_review_reject`、`/social_review_schedule`、`/social_review_schedule_queue`、`/social_review_final_confirm` 和“查看待审草稿/确认草稿/打回草稿/排程草稿明天8点/查看社媒排程/最终确认草稿”等自然语言路由。Telegram 现在可以远程查看统一草稿队列、确认、打回、加入待发布排程、查看到点排程并做最终确认；序号与插件草稿 ID 均可用，中文口语时间会规整为带时区排程时间。安全边界不变：确认只改审核状态，排程只进入 `queued_for_owner_publish`，最终确认只标记 `ready_for_manual_publish`，不自动发布、不自动评论、不关注/私信、不推广。

2026-06-23 热点池进一步升级为 MCN 选题卡：`GET /api/v1/social/extension/trends` 现在除标题/来源外，还按 X / 小红书 / 闲鱼返回目标人群、内容角度、平台打法、涨粉理由、风险等级、风险提示、执行步骤和 hook 模板；插件“抓热点”卡片会展示这些运营信号，并在生成热点草稿时把内容角度/打法/风险写入上下文。当前状态：更接近“追热点 + 平台打法 + 可执行内容”的运营产品，但仍需要真实账号数据反馈来做排序权重闭环。

2026-06-23 草稿生成继续补齐平台化内容计划与素材计划：`POST /api/v1/social/extension/drafts` 现在为 X / 小红书 / 闲鱼草稿返回 `content_plan`、`image_plan`、`platform_style`、`format_checklist`、`safety_checklist`、`cost_route`；Popup 草稿编辑器新增“素材计划”卡片，可展示内容结构、封面提示词、图片素材提示词、安全清单和模型路由提示。图片计划默认 `auto_generate=false`，只给人工确认后的生图提示词，不自动消耗 GPT Image / Gemini / Grok 等网页或 API 额度；排程提醒回填草稿时也会保留素材计划，避免到点最终确认时丢失封面和安全边界。

2026-06-23 继续补齐网页登录免费额度的安全用法：Chrome 插件新增“网页登录额度”卡片，可基于当前待审草稿生成 Gemini / Grok / ChatGPT 网页提示词，并只做“复制提示词 + 打开模型网页”。Background 白名单限制为 Gemini、Grok、ChatGPT 三个网页，且明确不自动粘贴、不自动提交、不自动生图、不自动发布；用户需要在网页手动提交后，把结果复制回插件继续审核。

2026-06-23 继续补齐运营复盘/增长反馈闭环：Chrome 插件新增“采表现”入口，可在已发布内容页只读采集点赞、评论、转发、曝光、收藏等可见指标，并通过 `POST /api/v1/social/extension/performance` 写入 `extension_performance`、草稿 `performance_snapshots` 和 `growth_feedback`。该数据只用于后续热点排序、人设复盘和 MCN 选题权重，不提供推广/boost/刷量路径，也不会触发自动发布、评论或再发布。热点池已开始读取这些增长反馈画像：历史 `high_signal` 或高赞/高评/高曝光内容会给相似标题/标签候选增加 `growth_feedback_boost`，并在插件卡片展示“历史高信号”原因。新增 `GET /api/v1/social/extension/growth-feedback` 和插件“看复盘”面板，可直接查看历史高信号内容、关键指标、标签和下一步选题建议。



2026-06-24 继续补齐产品线 1 的 Telegram 中控策略入口：新增 `/social_strategy [打法] [平台]`，并支持“切到X抽象热点打法 / 把社媒运营打法改成小红书生活攻略”等中文自然语言路由。Telegram 现在可以和 App/Chrome 共用同一个 `strategyPreset` / `strategy_summary`，远程切换财富前沿、抽象热点、小红书生活攻略、闲鱼成交客服等打法；该动作仍只改策略，不发布、不评论、不关注/私信、不推广。

2026-06-24 继续补齐 no-code 运营打法闭环：Chrome 插件高级设置新增的 `strategyPreset` 已贯通到后端 `strategy_summary` 与 App Social 中控，当前支持自动匹配、X 财富前沿、X 抽象热点、小红书生活攻略、闲鱼成交客服五种打法；App 会展示当前运营打法、目标人群、内容重点和增长闭环，平台卡也能看到对应 `strategy_preset`；App 还可通过 no-code 下拉保存打法到 `POST /api/v1/social/extension/strategy`。这解决了“插件里选了打法，但 App/Telegram 中控看不到/改不了策略”的断点；安全边界不变，打法只影响待审草稿、内容计划、素材计划和热点排序，不授权自动发布或自动评论。

2026-06-24 继续补齐三端状态一致性：Chrome Popup / Options 打开时会通过 Background 的 `socialStatusFetch` 读取 `GET /api/v1/social/extension/status`，把 App/Telegram 中控保存的合法 `strategyPreset` 自动回写到 Chrome 本地设置；同步过程继续保留本地 `automationLevel` / `interactionLevel` 安全默认值，避免任何远程状态打开自动发布或自动互动。Telegram `/social_strategy` 无参数时现在可只读查询当前打法、平台增长闭环、待审草稿、可发布未最终确认和排程数；带参数时才切换打法。

2026-06-24 真实浏览器 QA 发现并修复 Chrome 插件 Options 高级设置页的表单语义细节：Gateway token 密码框此前不在真实 form 内，Chrome 会提示 `Password field is not contained in a form`。现已用 `<form id="social-settings-form">` 包住 no-code 设置区与底部操作区，保存按钮改为 `type="submit"`，`options.js` 监听 submit 并阻止默认跳转后保存；真实 Google Chrome 复验 `hasForm=true`、`tokenInsideForm=true`、`saveType=submit`、控制台无 warning/error，截图已保存到 `output/playwright/social-pilot-options-form-fixed-20260624.png`。该修复只改善设置页浏览器 UX，不改变发布/评论安全闸口。

2026-06-24 继续把当前页热点/上下文采集收敛进共享页面执行器：`social-page-runner.js` 新增 `runSocialPageContextScanInPage()`，可只读采集 X 趋势/推文、小红书笔记标题/正文/评论、闲鱼商品/聊天/描述等信号，并返回 `selection`、`headings`、`trends`、`bodyText`。`background.js` 的当前页生成待审草稿链路已改为通过 `chrome.scripting.executeScript` 调用同一个 runner，真实 Chrome 烟测已覆盖三平台 `contextReady=true`、`contextSignals>0`、`buttonClicks=0`。这让“我打开平台页面 → 插件读当前热点/上下文 → 生成待审草稿”的入口更稳定，但仍只读采集，不点击发布/发送/评论按钮。

2026-06-24 继续把“当前页热点/上下文采集”从后台能力做成插件内可见 no-code 面板：Popup 新增“当前页热点/上下文”区域和“扫当前页”按钮，扫描结果会以卡片展示趋势、标题、正文摘要和选中文本，点击卡片才会生成待审草稿。Background 新增 `socialPageContextScan` 桥接，仍复用共享 runner 且强制 `publishIntent=false` / `auto_publish_enabled=false`。真实 Chrome 烟测已额外打开 Popup 预览页，确认 `page-context-panel` 展开、草稿编辑器出现，并保存截图 `output/playwright/social-pilot-browser-smoke-20260624/social-pilot-popup-context-20260624.png`。

2026-06-24 继续把 Chrome 插件主执行链路从单测推进到真实浏览器可重复验收：新增 `test/social-browser-smoke.mjs`，用本机 Google Chrome 模拟 X / 小红书 / 闲鱼页面，加载真实 `social-core.js` 和 `social-page-runner.js`，验证三平台都能识别 URL、探测输入框并把待审/已确认草稿安全填入页面。页面内已监听 Post / 发布 / 发送按钮点击，任何按钮点击都会让烟测失败；当前三平台结果均为 `ready=true`、`filled=true`、`buttonClicks=0`，截图位于 `output/playwright/social-pilot-browser-smoke-20260624/`。这证明 L1“自动填入页面但用户手动发布”已具备可重复 QA 证据，但仍不代表真实平台最终发布已放开。

2026-06-23 继续补齐安全互动闭环：Chrome 插件新增“扫互动”入口，能在当前 X / 小红书 / 闲鱼页面只读扫描评论、聊天或可回复信号，并点击候选卡片生成 `chrome_extension_interaction_scan` 来源的待审回复草稿。该链路只读页面文本，不点击回复/发送/评论/发布按钮；Background 只提供 `socialInteractionScan`，不提供自动评论提交路径；后端仍把草稿固定为 `needs_review/pending`，确认前不会评论或外发。

## 当前系统状态: 🟠 可运行但未达到完美生产态, 待外部密钥轮换和生产边界收口

| 指标 | 值 |
|------|------|
| 后端进程 | ✅ 运行中 (PID 自动重启) |
| 7 Bot 在线 | ✅ 7/7 |
| IBKR | ✅ 已连接 (DUP113460) |
| API 池 | ✅ 139/142 活跃源 |
| 闲鱼客服 | ✅ 自动回复活跃 |
| 社媒自动驾驶 | 🟡 草稿生成、素材计划、网页登录额度接力、只读互动扫描、增长复盘和 Telegram 审核/排程中控可运行；旧自动互动/自动发布已锁住，外部发布/评论必须走人工最终确认 |
| 测试 | ✅ 后端全量 pytest 退出码 0，当前 pytest nodeids 1495；`test_api_routes_regression.py` 12/12 通过；Frist-API 157/157 通过；2026-05-09 319px 移动端批注修复后 `node --check src/app.js`、批注聚焦测试 57/57、`npm test` 157/157 通过；桌面端 `npx tsc --noEmit` 通过；OpenClaw CI run `25592516119` 通过；2026-05-08 复审确认本地必须走 `make test` 或 `.venv312/bin/python -m pytest`，不能直接用系统 `pytest` |
| Frist-API 入口 | ✅ 唯一内容入口为 `frist-api.101-43-41-96.nip.io`；`101-43-41-96.nip.io` 只做 301 跳转，不再作为第二个网站直接展示 |
| Frist-API | ✅ HTTPS Quick Tunnel 和裸 IP 测试端口均已恢复；本地链路测试和公网冒烟通过，用户端已补齐弹窗登录注册、失败/成功反馈、API Key 创建反馈、连通性刷新不跳教程、渠道连通性聚合展示、价格管理、官方模型命名清洗、Claude Code/Codex 跨模型家族一键导入、Claude 第三方推理真实菜单流程图、Codex 导入 Claude 模型流程图、Codex 默认 Playwright/Superpowers/open-computer-use MCP、无网页 mock 数据兜底、默认最强模型导出、数据看板、模型广场、一次性管理员身份码、图片生成网关、OpenCode `/openai/chat/completions` 兼容路由、Chat Completions 到 Responses 降级、上游信息清洗、五客户端导入、日卡/小时卡轮转、会话粘滞、流式透传、公开模式硬门槛和自定义余额邮件预警；2026-05-08 复验 `npm test` 为 153/153 通过，`npm audit --audit-level=moderate` 为 0 漏洞，公网首页 200、看板 200、未授权 `/v1/models` 401；2026-05-08 内置浏览器审计公网首页标题 `Frist-API`、控制台无 error/warn，并修复返回按钮箭头无障碍噪音；2026-05-08 已部署 CSS 修复到 `/opt/frist-api/apps/frist-api/src/styles.css`，备份 `/opt/frist-api/backups/styles_20260509110117_before_browser_audit.css`，`frist-api-server` healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401；2026-05-08 复审发现账户弹窗密码字段缺少真实 form 语义，已按动作拆分表单、自动填充和回车提交回归；已部署表单修复到腾讯云，备份 `/opt/frist-api/backups/browser_form_20260508215051`，远端 `node --check src/app.js` 通过，公网内置浏览器复验 0 error/0 warning、箭头文本 0、账户表单 5 个；2026-05-09 New-API 已在腾讯云以 `calciumion/new-api:v1.0.0-rc.4` 启动并 healthy，因共享服务器 3000 端口被 `/opt/ccgame` 占用，实际绑定 `127.0.0.1:13000->3000`；公网 CC Switch 页面复验 0 error/0 warning、Dashboard 200、未登录不生成带 Key provider 链接、展示 21 个模型和独立 MCP deep link；临时 Key 验证 `/v1/models` 200 和用量接口 200，但真实聊天调用返回 503，根因是唯一 healthy 上游 Key 返回 401，需补充/轮换上游库存后才能形成完整用户调用闭环；已补后台 60 秒通道巡检和 Key 异常一次性补号提醒（Telegram/Webhook）；商业化自动运营仍需外部绑定真实品牌域名、商户平台开户、部署备份任务和执行历史数据迁移 |
| Frist-API 批注修复 | ✅ 2026-05-09 已处理 Logo、状态灯、工作台折叠菜单、通道展示批注、管理员快捷入口、固定工作台导航、趋势图 hover 数据和首页当前项背景；423×718 浏览器复验无横向溢出，Logo 105px，状态灯 18px，导航默认折叠且切页后自动收起，顶栏“登录/身份码/管理”可操作，`.provider-models` 为 0，控制台 0 error/0 warning；同日追加 319×718 极窄屏修复，Dashboard 与 CC Switch 本地浏览器复验 `scrollWidth=319`，顶栏账户按钮 173px，CC Switch 用量说明宽 235px 且无横向裁切 |
| Frist-API 腾讯云部署 | ✅ HI-875 用户端深色体验和官方计价修复已同步到 `/opt/frist-api`；部署前应用备份 `backups/frist-api-app-20260505-211636-before-ux-deploy.tgz`、运行数据备份 `backups/frist-api-runtime-20260505-211636-before-ux-deploy.tgz`；2026-05-08 复验 `frist-api-server` 容器 healthy，公网首页 200、看板 200、裸域名 301、未授权 `/v1/models` 401；2026-05-09 工作台批注修复已同步到 `/opt/frist-api`，部署备份 `/opt/frist-api/backups/frist-api-workbench-comments-20260509-035316-before-385bfce.tgz`，远端 `node --check` 和批注相关测试 57/57 通过，`frist-api-server` 重启后 healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401；同日 319px 移动端批注修复已同步到 `/opt/frist-api`，部署备份 `/opt/frist-api/backups/frist-api-mobile-319-20260509-045253-before-f2d6eda.tgz`，远端 `node --check` 和聚焦测试 57/57 通过，公网 319×718 Dashboard/CC Switch 复验 `scrollWidth=319` |
| ClawBot 腾讯云部署 | ✅ 2026-05-08 已单文件部署闲鱼管理页转义修复到 `/home/clawbot/clawbot/src/xianyu/xianyu_admin.py`；远端备份 `/home/clawbot/clawbot/backups/xianyu_admin_20260508155652_before_escape.py`；远端 `py_compile` 通过，`clawbot.service` 重启后 active |
| 微信命令 | ✅ 27/27 可用 (25✅ 2⚠️数据空) |
| Ollama 内存 | ✅ 151MB (原9.3GB) |
| 日志目录 | ✅ 2026-05-09 已清理本地 `packages/clawbot/logs/` 旧运行日志；生产日志和远端备份未清理 |
| 本地冗余 | ✅ 2026-05-09 已清理 `.DS_Store`、源码/测试 `__pycache__`、`.pytest_cache`、`.ruff_cache`、`.playwright-mcp`、Playwright/Expect 调试产物、Frist-API 历史审计截图和根目录临时截图；`.env`、`.openclaw/`、runtime 数据、`node_modules`、`.venv312` 保留 |
| 文档治理 | ✅ 主项目 docs 从散落状态统一归集到 43 个编号 Markdown，扁平化无子目录，历史截图/旧审计/散落设计报告/冗余打包文档已清理；2026-05-09 已补本轮清理日志 |
| 公开仓库安全 | 🟡 Git 历史已重写并通过本地扫描；secret alerts 当前为 0；Dependabot 可修依赖已收口，仍需等待 GitHub 重算并轮换曾暴露过的外部密钥 |

---

## 已知问题

### 🔴 阻塞 / 🟠 重要

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-872 | UX | Frist-API `#switch` 页面曾因导出模型展开逻辑被部分上游库存裁掉 `gpt-5.4`、`gpt-5.4-mini`、`gpt-image-2`、`gpt-5.3-codex`，且品牌标被 Tabcode 皮肤覆盖；已补完整 OpenAI 模型族可见逻辑、恢复原品牌标并加回归 | 2026-05-05 | ✅ 已处理 |
| HI-873 | INFRA | Frist-API 免费 nip.io 裸域名 `101-43-41-96.nip.io` 曾和品牌域名并列直接服务同一页面，用户误以为有两个网站；已收口为 `frist-api.101-43-41-96.nip.io` 唯一内容入口，裸域名只做 301 跳转 | 2026-05-05 | ✅ 已处理 |
| HI-817 | SECURITY | 公开 Git 历史曾提交 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json` 和数据库文件；已重写历史并通过本地 gitleaks/trufflehog 扫描 | 2026-04-28 | 🟠 待轮换密钥 + force-push 后复扫 |
| HI-818 | SECURITY | 本机 ignored `.env` 与浏览器 profile 日志含真实 API token；已确认未进入当前跟踪文件, 但涉及 token 应按泄露预案轮换 | 2026-04-28 | 🟠 待轮换 |
| HI-885 | BUG | 后端全量测试发现 `src.api.routers.store` 被删除但 `api/server.py` 仍挂载，导致 APIServer 初始化失败；已恢复 `/api/v1/store/catalog` 和 `/api/v1/store/categories` 最小兼容路由，并用 1491 passed 回归确认 | 2026-05-08 | ✅ 已处理 |
| HI-886 | INFRA | `make new-api-check` 显示 New-API 本地源码和 Compose 镜像曾为 `v1.0.0-rc.2`，GitHub 最新为 `v1.0.0-rc.4`；已通过自动同步 PR #1 更新 submodule 和 Compose 镜像到 `v1.0.0-rc.4`，并复验 compose 配置通过；2026-05-09 已在腾讯云完成数据备份、镜像拉取、端口冲突处理和数据目录权限修复，New-API `v1.0.0-rc.4` 当前 healthy | 2026-05-08 | ✅ 已处理 |
| HI-887 | AI_POOL/PERF | 86GameStore 实际面板显示余额 `$35.70`，今日实际消费 `$38.1537`，今日请求 `2464`，今日 Token `377.4M`，平均响应 `16.11s`；今日消耗已高于当前余额且响应偏慢，需补余额预警、限额和慢线切换策略 | 2026-05-08 | 🟠 待处理 |
| HI-890 | SECURITY | 服务器 root 密码已在对话中明文出现，视同泄露；本轮未把密码写入命令或文件，但必须尽快轮换 root 密码、审计登录记录并优先改为密钥登录/禁用密码登录 | 2026-05-08 | 🟠 待轮换 |
| HI-891 | INFRA | `New-API Scheduled Sync` 最近失败 run `25576027773` 卡在 `docker compose -f docker-compose.newapi.yml config`：CI 缺少 `NEWAPI_INITIAL_TOKEN`，导致已完成的 New-API 同步无法进入创建 PR；已给 compose 校验注入 CI 占位 token，并让检查脚本用退出码 `2` 明确表示“需要同步”、其他非零表示真实错误；复验 run `25588894721` 已成功并创建 PR #1 | 2026-05-08 | ✅ 已处理 |
| HI-892 | UX | 内置浏览器审计发现 Frist-API 隐藏视图的多个返回按钮文本箭头会在可访问性快照中聚合为 `← ← ←`，对屏幕阅读器和自动化审计产生噪音；已将 `.back-home::before` 改为纯 CSS 图形箭头，本地浏览器复验不再出现箭头文本且控制台无 error/warn | 2026-05-08 | ✅ 已处理 |
| HI-893 | UX | 内置浏览器复审发现账户弹窗密码字段不在真实 `form` 内，浏览器密码管理器会给出结构提示；已将登录/注册、改密码、重置密码和身份码激活拆成独立 `data-auth-form`，补齐 `autocomplete`，并让回车提交复用原处理逻辑 | 2026-05-08 | ✅ 已处理 |
| HI-894 | INFRA | 审计入口复核发现直接运行系统 `pytest` 会命中本机 Python 3.9 用户级脚本，导致 Python 3.12 项目代码被旧解释器误判；已将 AGENTS 和快速导航命令收口为 `make test` / `.venv312/bin/python -m pytest`，并用 `make test` 复验 | 2026-05-08 | ✅ 已处理 |
| HI-895 | INFRA | 腾讯云 New-API 远端 compose 曾仍为 `v1.0.0-rc.2`；2026-05-09 已重新备份运行数据，成功拉取 `calciumion/new-api:v1.0.0-rc.4`，并处理共享服务器 `127.0.0.1:3000` 端口冲突和 `data/newapi` UID 501 权限问题；当前 `openclaw-newapi` healthy，`/api/status` 返回 `version=v1.0.0-rc.4` | 2026-05-08 | ✅ 已处理 |
| HI-896 | AI_POOL/BUG | CC Switch 导入结构与接口边界复核通过：未登录 `#switch` 不暴露带 Key provider 链接，MCP deep link 独立展示，脱敏样本 provider 链接符合 `resource=provider/app=codex/usageScript` 契约；但受控临时 Key 实测真实聊天调用返回 503，唯一 healthy 上游返回 401 并触发 `credential_failed upstream_http_401`，说明当前上游库存 Key 需补充或轮换后才能完成端到端调用闭环 | 2026-05-09 | 🟠 待轮换上游库存 |
| HI-897 | INFRA/DOCS | 本地工作区遗留可重建缓存、调试日志和审计截图容易干扰后续审计基线；已清理 `.DS_Store`、`.playwright-mcp`、`.pytest_cache`、`__pycache__`、`.ruff_cache`、Playwright/Expect 临时产物、历史审计截图和本地旧日志，并保留运行配置、runtime 数据、依赖环境与生产备份 | 2026-05-09 | ✅ 已处理 |
| HI-898 | UX/AI_POOL | 移动端批注发现 Frist-API 顶栏状态灯和 Logo 挤压、工作台导航占屏、连通性卡按 Claude/OpenAI 模型分类且存在默认延迟疑似 mock；已改为小状态点、紧凑 Logo、默认折叠导航、卡商号池渠道展示、60 秒刷新口径和无真实延迟空态，并用 423×718 浏览器复验 | 2026-05-09 | ✅ 已处理 |
| HI-899 | UX/AI_POOL | 移动端管理员入口仅在账户弹窗底部，且无人请求时缺后台 Key 巡检，导致“看起来已连通但真实 Key 失效”不易被及时发现；已新增顶栏 `身份码/管理` 快捷入口、后台 60 秒巡检、Key 认证/额度异常自动降级和一次性补号提醒（Telegram/Webhook） | 2026-05-09 | ✅ 已处理 |
| HI-900 | UX | 浏览器批注发现 Frist-API 用户端 Logo 被退回单字母 F、趋势图鼠标移入不显示数据、首页导航当前项有大块背景且页面像脱离左侧导航；已恢复红白斜切抽象 Logo、给趋势图补整块 hover/键盘聚焦数据浮层、把工作台导航固定在左侧并让所有内容在右侧 `workspace-content` 内切换，当前项只保留细线提示 | 2026-05-09 | ✅ 已处理 |
| HI-901 | UX | 319px 移动端批注发现 Frist-API 顶栏语言/状态/登录余额遮挡、工作台折叠菜单箭头溢出、模型消耗空饼图过于单调、异常/通道空态缺说明、语言按钮像完整中英文切换、CC Switch 和用量教程比例裁切；已改为双行顶栏、固定箭头、解释型空状态、语言偏好提示和 CC Switch 两列/单列移动布局，并用 319×718 浏览器回测无横向溢出 | 2026-05-09 | ✅ 已处理 |

### 🟡 一般

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-802 | BUG | /monitor/news 首次调用可能超时 (RSS 20源+AI摘要) — 缓存热后正常 | 2026-04-26 | 🟡 已知 |
| HI-804 | BUG | G4F 服务 uptime 显示 0m — 进程检测关键词可能不匹配 | 2026-04-26 | 🟡 低优先 |
| HI-812 | BUG | 微信 iLink bot token 在平台侧失效(errcode=-14)，需在 iLink 后台重新扫码获取新 token | 2026-04-26 | 🟠 待操作 |
| HI-888 | SECURITY | `gitleaks` 扫描当前 HEAD 仍命中 `docs/007-operations.md` 中环境变量示例的 `generic-api-key` 误报；已改写为“变量名 + 取值”格式并复扫 | 2026-05-08 | ✅ 已处理 |
| HI-889 | SECURITY | 桌面端新闻/世界监控曾使用 `textarea.innerHTML` 解码外部文本，闲鱼管理页把接口返回字段拼入 `innerHTML` 前缺少统一转义；已改为安全实体解码和 `escapeHtml()` 转义，并部署远端闲鱼管理页修复 | 2026-05-08 | ✅ 已处理 |

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
| HI-821 | TECH_DEBT | Makefile 测试入口优先使用系统 Python 导致 pytest 缺失；API RPC 价格补齐和社媒 Cookie 检测存在重复实现 | 2026-05-01 |
| HI-822 | TECH_DEBT | AGENTS/SOP/索引仍指向历史大写文档路径；部分抽象类和聚合类保留空占位语句 | 2026-05-01 |
| HI-823 | INFRA | `make lint` 依赖 ruff 但开发依赖未声明；已补齐 requirements-dev 与依赖注册表 | 2026-05-01 |
| HI-824 | BUG | Frist-API 轻量后端静态首页因绝对路径归一化返回 403；已补回归测试并修复为同域 200 | 2026-05-01 |
| HI-825 | SECURITY | Frist-API 公开充值按钮会直接给用户加余额；已改为待处理充值单 + 管理端人工确认入账，生产默认关闭演示充值 | 2026-05-01 |
| HI-826 | TECH_DEBT | Frist-API 补号缺少直连/代理择优、上游不支持模型列表时的 fallback 探测和按真实 usage 扣费；已补齐轻量实现并纳入回归测试 | 2026-05-01 |
| HI-827 | ARCH_LIMIT | Frist-API 网关缺少公开可用级会话粘滞、真实流式透传和生产配置硬门槛；已补齐并纳入回归测试 | 2026-05-01 |
| HI-828 | UX | Frist-API 用户端信息密度过高、左侧导航/分组冗余、首屏存在演示数据闪现；已移除侧栏和 sticky，注册登录收进右上角，首屏只保留余额、模型消耗、连通性和导入入口，游客页不再显示演示消耗 | 2026-05-02 |
| HI-829 | SECURITY | Frist-API 公开管理页不应暴露给普通用户，注册登录需要基础防刷；已加入隐藏管理入口码、验证码挑战、认证限流和公网冒烟检查 | 2026-05-02 |
| HI-830 | UX | Frist-API 用户端缺少模型测试广场、数据看板、模型定价目录和配置教程；已补齐广场对话/生图、模型消耗分布、服务可用性、模型广场和 Codex/Claude/OpenClaw 一键配置教程 | 2026-05-02 |
| HI-831 | SECURITY | Frist-API 管理员升级不应依赖用户把账号密码交给开发者；已改为登录后输入一次性管理员身份码，成功后当前账号升级且身份码作废 | 2026-05-02 |
| HI-832 | UX | Frist-API 用户端注册登录、页面返回、广场消息管理、API Key 改名/删除、CC Switch 全模型导出、官方 Pro 模型优先级和 OpenCode/Hermes/Harmes 教程完整度不足；已补齐用户侧闭环并纳入回归测试 | 2026-05-02 |
| HI-833 | UX | Frist-API Codex/OpenCode 导出后用户无法在页面确认完整模型清单，外部 GUI 若只读单一字段可能只显示默认模型；已在 CC Switch 页可见化默认模型/全模型列表，并补齐多套模型列表兼容字段 | 2026-05-02 |
| HI-834 | INFRA | Frist-API 裸 IP 测试入口拒绝连接；根因是容器仅本地绑定且 Nginx 未监听测试端口，同时服务器代码落后于本地 open4；已同步代码、更新 Nginx 监听并通过公网冒烟 | 2026-05-02 |
| HI-835 | UX | Frist-API 首屏主卡过大、品牌标识弱化、快捷入口过于等分；已恢复黑白红品牌标识，并改为主控台、右侧说明、核心指标和不对称任务轨道 | 2026-05-02 |
| HI-836 | UX/ARCH_LIMIT | CC Switch 跨模型家族导入存在断点：ChatGPT 模型不能直接导入 Claude Code，Claude 模型导入 Codex 缺少 Responses 降级链路；已补齐 Claude Code Anthropic Messages 配置、Codex Responses fallback、开发者模式引导和支付最后一公里手册 | 2026-05-02 |
| HI-837 | UX | CC Switch 跨模型导入教程仍偏文字化，用户不知道 Claude 左上角菜单、第三方推理输入框和 Codex 配置字段在哪里；已补两张仿真实操流程图、编号步骤、字段对照和上下文切换验收提示 | 2026-05-02 |
| HI-838 | UX/BUG | Frist-API 登录、创建 Key、连通性刷新、模型命名、mock 数据和价格管理存在实测断点；已补明确反馈、刷新留在当前页、渠道聚合状态、官方模型名清洗、真实数据空态、后台价格 JSON 管理和 60 刀测试额度入账 | 2026-05-02 |
| HI-839 | UX/BUG | Frist-API 外网实测发现 CC Switch 一键导入入口藏在长教程后、广场 `gpt-5.5` Chat Completions 返回上游 `Route /openai/chat/completions not found`、OpenCode 前缀路由未接住、OpenCode 导入模型清单缺 `gpt-5.4` / `gpt-5.3-codex`，桌面端实际导入后 `config.models` 仍只写默认模型；已前置一键导入主操作、补 OpenCode `/openai/*` 兼容路由、Chat Completions 缺失时降级 Responses，并按 OpenCode/CC Switch 真实配置格式补完整模型映射 | 2026-05-02 |
| HI-840 | TECH_DEBT | 主项目文档、历史截图、旧审计报告、本地构建缓存和服务器临时产物过多；已压缩 docs 到 19 个 Markdown，本地仓库体积从约 2.4GB 降到约 196MB，并分层清理服务器日志、缓存、临时文件和 Docker 非运行对象 | 2026-05-03 |
| HI-841 | UX/BUG | Frist-API 广场和补号对 `5.5`、`image2` 这类商业别名不够稳，图片库存严格探测可能误走聊天接口；已补别名清洗、图片模型 `/images/generations` 探测、广场一键实测状态和回归测试 | 2026-05-03 |
| HI-842 | SECURITY/ARCH_LIMIT | Frist-API 需要把 CPA JSON 和 chong 作为备用渠道人工管理，但不能默认进入生产路由；已增加渠道类型、风险状态、人工确认和隔离态路由过滤 | 2026-05-03 |
| HI-843 | BUG | 腾讯云公网实测发现上游返回 `API key is disabled` 时，网关 503 路径会回滚库存状态，导致广场继续展示失效模型；已改为保留失败状态并让模型清单自动下线 | 2026-05-03 |
| HI-844 | BUG/UX | 授权余额站上游根地址会返回网站 HTML 壳，旧补号探测可能把 2xx HTML 当成健康或额度错误；已改为根地址失败后自动尝试 `/v1`、校验 OpenAI 兼容 JSON，并把首页改为控制台工作台布局 | 2026-05-03 |
| HI-845 | UX/AI_POOL | 新余额站 `gpt-image-2` 真请求耗时 40-110 秒，广场默认图片参数过重容易放大公网等待；已改为轻量 PNG 请求并完成裸 IP 公网图片真测 | 2026-05-03 |
| HI-858 | UX | Frist-API Workbench 壳不足：侧栏品牌与顶部 Logo 重复、仪表盘指标/图表/日志不足、API 管理缺搜索和端点展示、缺使用记录/订阅/兑换/邀请/资料页面、CC Switch 需覆盖 Gemini/OpenCode/OpenClaw/Hermes/Harmes 和 Codex DeepSeek；已完成 UI 外壳、美元展示和回归测试 | 2026-05-03 |
| HI-859 | ARCH_LIMIT | Frist-API 已接入服务端 New-API 业务桥接层和每日 GitHub Actions 同步 PR；New-API 可接管看板、Token、日志、兑换、订阅、充值配置、邀请返利和可选网关代理。仍保留 Frist-API 自研 UI、CC Switch/Codex/DeepSeek 配置、补号助手、余额预警和 JSON 兜底；完整切换还需要历史用户/余额/Key/订单迁移和生产 New-API 初始化 | 2026-05-03 |
| HI-848 | UX | Frist-API 用户无法按自己的心理安全线设置余额提醒；已新增账单页自定义阈值、收件邮箱、测试邮件和扣费跨阈值一次性提醒 | 2026-05-03 |
| HI-849 | INFRA | 本机到 Gmail SMTP 异常；腾讯云实测 IPv6 SMTP TLS 与真实发信可用，IPv4 465 超时；已补 Node SMTP DNS 地址轮询和 `FRIST_API_SMTP_FAMILY` 配置 | 2026-05-03 |
| HI-855 | SECURITY/UX | Frist-API 验证码原为简单算术题且登录也强制填写；已改为仅注册需要多题型挑战、单题错误次数限制，登录保留频率限制但不再要求验证码 | 2026-05-03 |
| HI-851 | SECURITY | Frist-API 密码哈希使用 SHA-256（GPU 友好）；已改为 PBKDF2-SHA256 新格式，旧 SHA-256 用户登录成功后自动升级 | 2026-05-04 |
| HI-852 | SECURITY | Frist-API Session Cookie 缺少 `Secure` 标记；已在 HTTPS 公网网关或 `x-forwarded-proto=https` 下自动加 `Secure` | 2026-05-04 |
| HI-860 | SECURITY | Frist-API 用户端和管理端部分动态 `innerHTML` 字段未统一转义；已补齐 API Key 属性、充值/导入按钮、管理端摘要/审计日志等转义并加回归 | 2026-05-04 |
| HI-861 | AI_POOL/UX | Frist-API Codex DeepSeek 导入仍默认旧 `deepseek-chat`，与 DeepSeek 官方当前 v4 模型文档不一致；已将新导入默认模型改为 `deepseek-v4-flash`，补 `deepseek-v4-pro` 并保留旧模型兼容 | 2026-05-04 |
| HI-862 | UX | Frist-API 后端不可用时用户只看到顶部错误提示，不知道如何恢复；已在工作台增加离线恢复条和一键重新连接入口 | 2026-05-04 |
| HI-850 | SECURITY | Frist-API runtime.json 明文存储用户 fk-live Key 和上游 rawKey；已新增 AES-256-GCM 字段加密，兼容旧明文读取并在保存时迁移 | 2026-05-04 |
| HI-853 | UX | Frist-API 无"忘记密码"功能，用户丢失密码后无法自助恢复；已新增 SMTP 重置验证码和确认改密接口 | 2026-05-04 |
| HI-854 | UX | Frist-API 前端服务不可用时静默降级无重试入口，用户看不到明确恢复指引 | 2026-05-03 |
| HI-856 | ARCH_LIMIT | Frist-API server.js 单文件 4432 行，账号/网关/邮件/管理全耦合在一个模块 | 2026-05-03 |
| HI-857 | ARCH_LIMIT | Frist-API 内存态 captcha/rateLimit 在进程重启或水平扩展时丢失 | 2026-05-03 |
| HI-863 | INFRA | Frist-API 长期入口仍缺固定品牌域名；免费域名已实测，`sslip.io` 在腾讯 DNSPod 侧被拦截，当前过渡入口切到 `frist-api.101-43-41-96.nip.io`；Let’s Encrypt 访问 ACME challenge 被重置，HTTPS 仍需自有域名或 Cloudflare Tunnel 闭环 | 2026-05-04 |
| HI-864 | UX/COMMERCE | Frist-API 个人阶段不再推进个人收款码自动识别；已改为管理端批量生成一次性兑换码、用户端专属兑换页核销自动到账，并预留闲鱼商品链接位置 | 2026-05-04 |
| HI-865 | AI_POOL/UX | Frist-API 需要管理自用 ChatGPT Plus 账号资产但不能把 Plus 账号变成可售 API 路由库存；已新增管理端 Plus 台账、到期摘要、敏感备注加密和用户路由隔离回归 | 2026-05-04 |
| HI-866 | AI_POOL/UX | Frist-API 需要参考 New-API Codex OAuth 和 Grok RT JSON 格式支持 Refresh Token 批量管理，同时不能减少原 New-API 管理侧能力；已新增管理端 RT JSON/TXT 导入、脱敏台账、加密落盘和路由隔离回归 | 2026-05-04 |
| HI-867 | UX/PERF | Frist-API 用户端和管理端解释性文案偏多、深色 Hyperstudio 壳与 Apple 简洁方向不一致，搜索和测试台存在不必要局部重绘；已切换 Refero Apple 浅色控制台、压缩首屏指标和导航文案、保留管理侧原功能并补局部渲染优化 | 2026-05-05 |
| HI-868 | UX/PERF | Frist-API 参考 Tabcode 控制台克隆吸收优秀设计：替换旧视觉皮肤为 `tabcode-console`，后续按用户反馈收敛为深色顶栏、深色工作区、160px 侧栏、14px 卡片和短动效反馈，管理端原有 New-API/价格/入账/卡密/Plus/RT/接入/订单/库存/审计能力不减少 | 2026-05-05 |
| HI-869 | BUG | Frist-API Plus 台账金额字段审计发现异常数字输入可能把 `NaN` 带入运行数据；已改为有限数字归一化并补回归，异常 TRY 余额/月费统一落为 0 | 2026-05-05 |
| HI-870 | UX/SECURITY/ARCH_LIMIT | Frist-API CC Switch 导出曾按本机 Tabcode Claude/Codex 真实导入结构补齐大块 `settings_config`；后续 HI-877 已按 CC Switch 当前官方 parser 收敛为短 deep link，页面仍展示完整模型清单，协议无响应时自动复制降级；管理认证失败脱敏审计、runtime 写入失败 warning 和 SIGTERM/SIGINT 优雅关闭已保留 | 2026-05-05 |
| HI-871 | UX | Frist-API Tabcode 浅色皮肤存在旧深色规则残留，黑底按钮/代码栏复制按钮/返回按钮出现灰字低对比；已更新资源版本并增加对比度护栏，用户端 6 个主路由和管理端可见交互元素扫描低对比为 0 | 2026-05-05 |
| HI-874 | AI_POOL/INFRA | 用户提供的 `https://www.inroi.shop/v1` 是授权上游请求地址，后续字符串是上游 Key，不是 Frist-API 对外入口；已按 `x-admin-token` 复查远端管理号池，同 Key 旧根地址记录为 `exhausted/enabled=false` 不可路由，正确 `/v1` 记录为 `healthy/enabled=true` 且模型 21 个，runtime 中 rawKey 为 AES-GCM 加密字段 | 2026-05-05 |
| HI-875 | UX/AI_POOL | Frist-API 用户端日志过长、测试页文字爆炸、深色对比不足、模型价格说明不完整、记录页缺客户端/费用/延迟、API Key 前缀像 fake；已改为 5 条精简日志、短动效反馈、深色控制台逐页审计、官方输入/缓存/输出价、3 分钟自动检测、消费后余额刷新、邮箱遮罩、兑换码前置、消费返利 5% 上限和资料可编辑，并已部署到腾讯云公网入口；2026-05-06 上线前安全复审已将新 Key 前缀恢复为 `fk-live-*` | 2026-05-05 |
| HI-876 | SECURITY | Frist-API 上线前安全闭环复审发现 CSRF、SSRF、支付少付入账、runtime 写入原子性、用户 Key 明文回显、共享脱敏前缀和生产模板开关存在上线风险；已补 CSRF Token、补号 URL 私网阻断、支付金额校验、临时文件 fsync+rename、Dashboard 不再持久回显明文 Key、`fk-live-*` 脱敏一致性和生产 `FRIST_API_REQUIRE_CSRF`/`FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS` 登记 | 2026-05-06 |
| HI-877 | UX/BACKEND | CC Switch 用量查询曾只能靠用户按教程手填 Key 和 API 地址，且 DeepSeek 官方端点导入时用量脚本可能误用上游域名；已核对 CC Switch 3.14.1 官方 deep link 支持 `usageScript` 等字段，导入链接自动带 Base64URL 用量脚本并移除旧 `config` / `availableModels` 大块参数，新增 `/api/frist/key-usage` 只读脱敏接口，修复 New-API 用量接口 500 回归，并将模型请求地址与 Frist 用量查询地址解耦；2026-05-06 实机验证中 CC Switch 日志确认解析 `resource=provider/app=claude/name=Frist-API`，临时等价导入后 Claude CLI 返回 `Frist API CLI OK`，测试后已恢复用户原配置 | 2026-05-06 |
| HI-878 | UX/BACKEND | Frist-API 渠道状态监视器此前只有 healthy/total 简表，用户无法判断降级、慢线、最近状态和刷新口径；已参考 86GameStore `/monitor` 补齐当前库存快照、可用率、最低/平均延迟、慢线/失败状态条和 60 秒刷新展示，响应继续脱敏；2026-05-07 已通过 HI-882 补齐持久化探测事件和 7/15/30 天 SLA 摘要 | 2026-05-06 |
| HI-879 | BUG/AI_POOL | Frist-API “Claude 兼容入口 · 查询失败”根因是 CC Switch 用量脚本返回对象型 `extra`，同时 Claude 原生 Messages 上游未优先直连；已将 `extra` 改为字符串、补 Claude `/v1/messages` 原生路由/严格探测、同 Key 多模型组隔离和导出按模型组选 Key。86GameStore Claude/OpenAI 号源已加密写入 ignored runtime，用户流程、Claude CLI、Codex CLI 和浏览器刷新均已实测闭环 | 2026-05-06 |
| HI-880 | UX/BUG | CC Switch 小白导入 Workflow 存在边界不清：供应商 deep link 和 MCP deep link 是两个 resource，页面曾把 MCP 偏向 Codex 且用户显式选择模型时服务端返回默认模型、深链模型和 TOML 默认模型可能不一致；已按 CC Switch `origin/main` 源码收敛为两步 Workflow，MCP 增强包覆盖 `claude,codex,gemini,opencode,hermes`，明确 OpenClaw MCP 会被当前 CC Switch 忽略，并补齐用户选择模型一致性回归 | 2026-05-06 |
| HI-881 | UX/BACKEND | Frist-API 用户侧缺少导入后的闭环检测和异常消费提醒，管理侧号池对小白管理员仍难以判断哪个端点/渠道断了；已将 OpenAI 命名收敛、补导入后检测闭环、`gpt-image-2` 流程图验证入口、轻量异常消费检测、管理端号池首次使用流程和渠道诊断。受控实机验证中，文本 `pong`、图片返回、用量脚本、记录页消费、异常提醒和 `gpt-image-2` 降级 `1/2 可用` 均闭环 | 2026-05-07 |
| HI-882 | SECURITY/ARCH_LIMIT | Frist-API New-API 剩余生产边界缺少统一硬门槛；已新增生产强制开关、固定品牌域名检查、New-API 数据库必备开关、管理员 TOTP 2FA、真实支付商户状态、备份/恢复登记和 7/15/30 天渠道 SLA 事件摘要。外部仍需购买/绑定真实品牌域名、在商户平台开户、部署备份任务并完成历史 JSON 到 New-API 数据迁移 | 2026-05-07 |
| HI-883 | UX/BUG | Frist-API 用户端浏览器批注发现状态灯、导航间距、趋势图、CC Switch 教程、重复 Harmes、复制按钮、模型展示名、资料页、登录弹窗和游客库存展示存在视觉 QA 问题；已按批注修复，未登录 Dashboard 不再展示 `channelChecks`，真实内部模型 ID 继续保留以免影响路由 | 2026-05-08 |
| HI-884 | BUG/SECURITY | Frist-API 登录失败曾把真实 401 账号错误统一显示为“后端暂不可用”，且公网容器仍使用默认管理令牌，SMTP 未配置时用户无法自助恢复密码；已补真实错误反馈、管理员账号恢复接口、独立密码哈希密钥、默认管理令牌替换和 CSRF。历史 runtime 已有 `enc:v1` 字段但缺原始数据加密密钥，公网暂保留兼容模式，后续需一次性迁移后再启用公开模式数据加密 | 2026-05-08 |

---

## 技术债

| ID | 分类 | 描述 | 优先级 |
|----|------|------|--------|
| TD-001 | TECH_DEBT | CookieCloud 服务器 127.0.0.1:8088 离线 | 🟡 |
| TD-002 | ARCH_LIMIT | 部分微信编号命令(~25个)无真实API,走LLM通用回复 | 🟡 |
| TD-003 | TECH_DEBT | CLICommandsMixin (/cli) 预备代码未注册 | 🔵 |
| TD-004 | TECH_DEBT | 源码仍有 63 个历史 `pass` 语句，多数位于可选依赖降级、异常兜底和测试辅助路径，需按模块分批审查后清理 | 🔵 |
| TD-005 | TECH_DEBT | `ruff` 工具链已补齐，但 `make lint` 暴露 547 个历史 lint 问题，主要为 UP031(192)、B904(88)、RUF013(62)、E402(49)；已完成 monitor 路由 3 项和 API 边界异常链路 5 项机械清理 | 🟡 |
| TD-006 | ARCH_LIMIT | Frist-API JSON runtime 已被生产强制开关挡在正式运营外；仍需把历史用户、余额、Key、订单和日志迁移到 New-API 数据库并做回滚演练 | 🟠 |
| TD-007 | INFRA | Frist-API 代码已要求生产使用固定 HTTPS 品牌域名；实际域名购买、DNS/Cloudflare Tunnel 或 ACME 证书仍需外部平台操作 | 🟡 |
| TD-008 | ARCH_LIMIT | Frist-API 模型目录和默认最强模型仍有内置排序兜底；生产应改为上游 `/v1/models`、官方模型目录校验、后台可审计排序共同决定，避免硬编码模型名误导客户 | 🟠 |
| TD-009 | TECH_DEBT | Frist-API `ccswitch://` 导入链接依赖用户已安装 CC Switch，浏览器无协议处理器时降级体验为空；已改为点击导入自动复制链接并显示短降级反馈 | ✅ 已处理 |
| TD-010 | SECURITY | Frist-API 管理 API 失败认证不生成审计事件，暴力破解无法检测；已补脱敏审计事件且不记录提交的 token | ✅ 已处理 |
| TD-011 | ARCH_LIMIT | Frist-API 无优雅关闭（SIGTERM/SIGINT），连接直接断开对网关流式请求不友好；CLI 启动已补优雅关闭和超时兜底 | ✅ 已处理 |
| TD-012 | ARCH_LIMIT | Frist-API 文件写入失败被 `catch(() => {})` 静默吞掉，store 破损后无告警；已改为 `FRIST_API_RUNTIME_WRITE_FAILED` warning | ✅ 已处理 |
| TD-013 | ARCH_LIMIT | Frist-API 已将网关成功、慢线、失败和额度耗尽写入 `channelProbeEvents` 并返回 7/15/30 天 SLA 摘要；2026-05-09 已补独立 60 秒后台探测队列覆盖无人调用时段，并支持 Key 异常一次性补号提醒 | ✅ 已处理 |
| TD-014 | TECH_DEBT | Python 测试环境存在依赖告警：`requests` 与 `urllib3/chardet/charset_normalizer` 版本组合不匹配，`jieba` 依赖 deprecated `pkg_resources`，`js2py` 使用 deprecated `co_lnotab`，部分调度测试路径有未 await coroutine warning；本轮未影响测试通过，但需后续清理 | 🟡 |
| TD-015 | INFRA | GitHub Actions Node 20 运行时即将废弃；OpenClaw CI 已升级 `checkout@v6`、`setup-node@v6` 和 Node.js 24，run `25592516119` 通过且前端 typecheck 使用 Node 24；仍有 `actions/cache@v4`、`actions/setup-python@v5`、`astral-sh/setup-uv@v5` 的平台级 Node 20 预警，需等上游 action 发布兼容版本或后续单独替换 | 🟡 部分处理 |
| TD-016 | ARCH_LIMIT | X 自动运营已从 AI/视频蒸馏垂直号切换为中英文热点追踪涨粉号，并进一步切到“草稿生成 + 人工确认后发布”：微博/百度/知乎/B站/Google News/HN 聚合、热点评分、语言配额、抽象短推模板、审核闸口、Social SaaS 驾驶舱、Chrome Social Pilot 第一阶段、当前页生成待审草稿、插件热点池选题、MCN 选题卡字段、插件草稿内容/素材计划、插件内编辑/确认/打回、已确认草稿加入待发布排程、插件人设与样稿确认面板、插件排程提醒面板、排程到点提醒与最终确认、安全填入页面但不发布、填入点检测计划、页面执行器模块化单测、真实页面选择器变体校准、页面校准结果同步中控、只读互动扫描生成待审回复草稿、只读表现复盘写入增长反馈池、增长反馈反哺热点排序、增长复盘可视化面板、App Social 中控增长复盘卡片、App/Chrome/Telegram 增长复盘反哺下一批待审热点草稿、无增长样本时冷启动热点池生成待审草稿、Telegram `/social_growth_feedback` 只读复盘命令与 `/social_growth_drafts` 待审草稿命令、Telegram `/social_review_drafts`/`approve`/`reject`/`schedule`/`schedule_queue`/`final_confirm` 审核排程中控、Chrome/App/后端 `strategyPreset` no-code 运营打法与 `strategy_summary` 已贯通，App 与 Telegram 均可保存策略但不授权外发，Chrome Popup/Options 已能从后端回拉打法避免三端长期不一致，Telegram `/social_strategy` 无参数可查询当前打法与审核状态，当前页热点/上下文采集器 `runSocialPageContextScanInPage` 已接入 Background，并升级为 Popup 可视化“扫当前页”面板且由单测/真实 Chrome 烟测覆盖，定时脚本防绕过已落地；LaunchAgent 当前未加载，需用户确认人设/内容并在真实页面校准后再恢复最终外发或评论动作 | 🟡 部分处理 |
| TD-017 | TECH_DEBT | YouTube/Bilibili 蒸馏已保留为低优先级补位；当前热点号更需要评论梗/小红书/微博实时语义，已确认 agent-reach 的 X/YouTube/B站通道可用，小红书 OpenCLI 需安装 Chrome 扩展后才能完整使用；后续可继续接入 MediaCrawler、yt-dlp、youtube_transcript_api、bilibili_api 与 sau CLI 做深度蒸馏和多平台搬运 | 🟡 部分处理 |

---

## 二、自学习经验库


记录系统运行中积累的经验、最佳实践和优化心得。

## 格式

```
## [YYYY-MM-DD] 主题

**背景**: 场景描述
**发现**: 关键洞察
**应用**: 如何应用到实际工作中
```

---

## [2026-03-18] 系统全面优化完成

**背景**: 对 OpenClaw Bot 进行全面功能完善

**完成项目**:
1. 集成优化报告到 multi_main.py（Prometheus 指标、分层上下文、策略引擎、告警系统）
2. 交易记忆自动写入机制（TradingMemoryBridge 挂载到 journal）
3. 修复类型标注问题（execution_hub 4个bug、broker_bridge TYPE_CHECKING）
4. 社交媒体浏览器发布适配器（Playwright 自动发布 X/小红书）
5. 任务可观测性增强（TaskObserver 跟踪质量/成本/检索命中率）
6. 自学习系统启用（.learnings 文件初始化）

**关键洞察**:
- 交易系统虽然在跑，但记忆为空导致"失忆"决策 → 自动桥接解决
- 社交发布链条在最后一步断了 → Playwright 补上自动化
- 可观测性不足 → TaskObserver 按任务类型跟踪成本和质量
- 类型错误大多是 decompiled 文件的副作用，修复实际 bug 即可

**应用**:
- 所有关键业务流程都应有记忆沉淀机制
- 自动化链条要端到端完整，不能在最后一步依赖人工
- 可观测性要细化到任务级别，才能优化成本和质量

---

## 三、功能需求跟踪


记录用户提出的功能需求、改进建议和待实现特性。

## 格式

```
## [YYYY-MM-DD] 功能名称

**需求**: 用户需求描述
**优先级**: High/Medium/Low
**实现思路**: 技术方案概要
**状态**: Pending/In Progress/Done
```

---

## [2026-03-18] 初始化

功能需求跟踪已启用。后续需求将记录到此文件。

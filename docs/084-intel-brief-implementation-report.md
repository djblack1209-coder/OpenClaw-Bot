# Intel Brief 实施验收报告（历史阶段汇总）

> 项目路径：`/Users/blackdj/Desktop/OpenEverything`
> 原始报告时间：2026-07-06（America/Denver）
> 证据口径：所有外部数据源连通性证据均以 `oracle-arm1` 发起的真实调用为准；Mac 本地检查只作为辅助，不作为生产可用证明。
> 当前定位：本文保留 Intel Brief Phase 0 / Phase B 的历史验收证据，不代表 2026-07-10 当前生产状态；当前结论以 `docs/009-health.md` 与 `docs/002-changelog.md` 最近条目为准。
> 安全口径：未输出任何 Key / Token / Cookie 明文；原始阶段未修改 OpenEverything 业务代码、未重启服务、未新增部署。

---

## 0. 总体结论

本轮没有进入代码实现阶段。原因是用户提示词明确要求 **Phase 0 必须先完成，并且外部数据源必须从目标 Oracle 运行环境真实调用验证**；同时提示词第 4 节规定：遇到“是否复用哪个 VPS 节点作为常驻运行环境”“是否接入 X/Reddit/Agent-Reach”“celebrity_watchlist 人物名单”等事项必须停下来问用户，不能自行决定。

我已完成一轮 **不触碰业务代码的 Phase 0 预检**：

- 已确认 `oracle-arm1` 可登录，且现有 JIYU/New-API/Apache 服务仍为 active。
- 已在 `oracle-arm1` 的临时目录创建独立验证环境 `/tmp/openclaw-intel-phase0-20260706`，安装并真实调用 `akshare` / `edgartools`；未写入项目目录，未重启服务。
- 已从 `oracle-arm1` 真实调用 GitHub、EDGAR、AKShare 部分接口、HouseStockWatcher 相关端点、OpenAI/Anthropic/DeepSeek 新闻源候选地址。
- MediaCrawler、Agent-Reach、Telegram 第 8 Bot、订阅套餐和名人白名单均被人工决策项阻塞，不能继续自动推进。

---

## 1. 各 Phase 完成情况

### Phase 0：环境与依赖验证

状态：**部分可用，有已知限制；未达到“全部通过后进入开发”的门槛。**

证据路径：本报告 `/Users/blackdj/Desktop/OpenEverything/docs/084-intel-brief-implementation-report.md`，本节为 Phase 0 验收证据摘要。

| 验证项 | 状态 | Oracle 真实调用证据 | 已验证边界 / 未验证边界 |
|---|---|---|---|
| Oracle 目标环境基础状态 | 已验证可访问 | `oracle-arm1` 返回：`host=oracle-arm1`，UTC `2026-07-06T21:32:07Z`，`Python 3.12.3`；`sub2api.service`、`openclaw-newapi.service`、`apache2` 均为 `active` | 只证明该节点可执行 Phase 0 检查；**不等于已确认它就是 Intel Brief 常驻运行环境**。 |
| Oracle Python 依赖现状 | 已验证 | 系统 Python 中：`akshare` 缺失、`edgartools` 缺失、`httpx` 缺失、`pandas` 缺失、`playwright` 缺失、`requests` 已安装 | 说明不能直接在现有系统 Python 中运行 Intel Brief 数据源；需要独立 venv 或项目环境方案。 |
| 临时依赖安装 | 已验证 | 在 `/tmp/openclaw-intel-phase0-20260706` 安装：`akshare==1.18.64`、`edgartools==5.40.1`，UTC `2026-07-06T21:35:52Z` | 只在临时目录验证安装；未安装到生产项目 venv，未改 systemd。 |
| GitHub Star / Trending 数据 | 已验证可用 | Oracle 调用 GitHub Search API，UTC `2026-07-06T21:33:49Z`，HTTP 200，样本：`sindresorhus/awesome`、`freeCodeCamp/freeCodeCamp`、`public-apis/public-apis` | GitHub Search API 可用；HTML Trending 解析需要加固，直接 HTML 样本中容易误抓 sponsors 链接。 |
| AKShare：A股龙虎榜 | 已验证可用 | Oracle 调用 `akshare.stock_lhb_detail_daily_sina(date='2026-07-03')` 成功，返回 `row_count=93`；样本含 `国华退`、`恒久退` 等龙虎榜记录 | 可作为 A 股龙虎榜接入候选；需后续封装重试和日期选择。 |
| AKShare：A股资金流 | 已验证可用但较慢 | Oracle 调用 `akshare.stock_fund_flow_individual(symbol='即时')` 成功，返回 `row_count=5194`；样本含 `概伦电子`、`鑫磊股份` 的流入/流出/净额字段；耗时约 55 秒 | 可用但慢，调度时需要超时、缓存和降级；不适合每个用户实时触发。 |
| AKShare：东方财富 A 股实时行情 | 部分失败 | Oracle 调用 `akshare.stock_zh_a_spot_em()` 失败：`ConnectionError: RemoteDisconnected('Remote end closed connection without response')` | 说明 Oracle 出口访问部分东方财富接口不稳定；不能把 AKShare 整体视为全绿。 |
| EDGAR / 13F | 已验证可用 | Oracle 调用 `edgartools.get_filings(form='13F-HR', year=2026, quarter=2)` 成功；样本：`VectorGlobal IAG, Inc.`、`Winning Points Advisors, LLC`、`BSN Capital Partners Ltd`；filing date 均为 `2026-06-30` | 13F 获取链路可用；后续还需解析 holdings 明细和缓存 SEC 速率。 |
| HouseStockWatcher API | 未可用 | Oracle 调用 `https://housestockwatcher.com/api`、`/api/trades`、`/api/transactions` 均 DNS 失败；House/Senate watcher S3 JSON 端点返回 HTTP 403 | 不能按原计划直接依赖 `housestockwatcher.com API`；需要确认新端点或改用其他公开数据源。 |
| AI 模型动态 RSS / 新闻源 | 部分可用 | Oracle 调用 `https://openai.com/blog/rss.xml` 成功，HTTP 200，样本标题：`OpenAI News`、`How ChatGPT adoption has expanded`、`Inside Genebench-Pro`；`https://www.anthropic.com/news/rss.xml` 返回 404，但 `https://www.anthropic.com/news` 页面 HTTP 200；DeepSeek 候选 RSS / news 地址返回 404 | OpenAI RSS 可直接接入；Anthropic 可抓新闻页但 RSS 地址需重新确认；DeepSeek 官方新闻源未找到可用 RSS。 |
| MediaCrawler | 未验证 | 本地存在 `packages/clawbot/docker-compose.mediacrawler.yml`，但 `packages/clawbot/vendor/MediaCrawler` 不存在；Oracle 侧未发现 MediaCrawler vendor，`docker` 不存在，`git` 存在 | 无法在不新增部署/不处理登录态的情况下跑通微博/小红书；需要用户确认是否允许在目标节点安装/运行 MediaCrawler，以及提供/确认登录态。 |
| Agent-Reach / X / Reddit | 未执行 | 未调用 | 用户提示词明确要求接入 X/Reddit 前必须确认；本轮未擅自评估或接入。 |

### Phase 1：数据源接入

状态：**未开始。**

原因：Phase 0 尚未全部通过，且 HouseStockWatcher / MediaCrawler / X/Reddit 存在明确阻塞。按照用户要求，不能在数据源未真实验证时直接写“已接入”。

### Phase 2：内容质控与摘要生成

状态：**未开始。**

原因：真实多源输入尚未稳定形成，不能用 mock 数据冒充“多源输入 → LLM 摘要”的验证闭环。

### Phase 3：订阅者与推送层

状态：**未开始。**

原因：需要 Telegram 第 8 个 Bot 的真实 Token/身份、套餐设计、名人白名单；这些都是用户提示词列出的人工决策项。

### Phase 4：闭环验证

状态：**未开始。**

原因：尚未完成 Bot 注册、订阅 DB、推送链路和一个自然日的定时任务运行；不能声称完成。

---

## 2. 遇到的技术障碍与实际解决方案

1. **目标运行环境尚未被正式确认**
   - 实际处理：只使用文档中已有 SSH alias `oracle-arm1` 做 Phase 0 预检，没有把它写成常驻运行环境，也没有部署服务。
   - 当前限制：后续是否复用该节点作为 Intel Brief 常驻节点，需要用户确认。

2. **Oracle 系统 Python 缺少 Intel Brief 依赖**
   - 实际处理：在 `/tmp/openclaw-intel-phase0-20260706` 建临时 venv，只验证 `akshare` / `edgartools` 安装和真实调用。
   - 当前限制：正式代码应使用项目 venv、专用 venv 或独立服务环境，不能把临时 venv 当生产依赖。

3. **AKShare 在 Oracle 上表现不一致**
   - 实际处理：验证了多个函数。龙虎榜和资金流可用；东方财富实时行情接口失败。
   - 当前限制：A 股模块必须按接口粒度做健康追踪，不能假设 AKShare 全量可用。

4. **HouseStockWatcher 端点不可用**
   - 实际处理：从 Oracle 真实请求多个候选端点；主域名 DNS 失败，S3 数据端点 403。
   - 当前限制：国会持仓模块需要重新确认可用公开源，不能按原 prompt 直接实现为可用数据源。

5. **MediaCrawler 没有可运行底座**
   - 实际处理：只检查现有文件和目标环境能力；发现 compose 文件存在但 vendor 缺失，Oracle 无 Docker。
   - 当前限制：微博/小红书登录态与抓取必须另行确认安装方式和账号登录方式。

6. **Anthropic / DeepSeek RSS 不可直接按候选地址接入**
   - 实际处理：OpenAI RSS 成功；Anthropic 新闻页可访问但 RSS 404；DeepSeek 候选 news/RSS 404。
   - 当前限制：AI 模型动态模块需要为 Anthropic/DeepSeek 使用页面抓取或重新确认官方 feed。

---

## 3. 需要人工决策但本轮被阻塞的事项清单

1. 是否确认使用 `oracle-arm1` 继续做 Intel Brief Phase 0/Phase 1 验证，以及未来是否作为常驻运行环境。
2. 是否允许在目标节点创建长期 Intel Brief 专用 venv，并安装 `akshare`、`edgartools`、`httpx`、`pandas`、后续可能的 MediaCrawler 依赖。
3. 是否接入 X / Reddit；如果接入，才评估 Agent-Reach 和对应网络出口。
4. MediaCrawler 的微博/小红书登录态：使用哪个账号、是否允许在目标环境维护 Cookie/Session、是否接受扫码/人工登录步骤。
5. `celebrity_watchlist` 首批公众人物白名单。
6. Telegram 第 8 个 `intel_brief_bot` 的真实 Bot Token、用户名和接收测试账号。
7. 订阅套餐、价格、有效期和默认权限范围。

---

## 4. 下一轮建议优先做什么

1. 先由用户确认：`oracle-arm1` 是否作为下一步验证/运行节点；是否允许创建长期专用 venv。
2. 在确认后继续 Phase 0：补齐国会持仓可用数据源、Anthropic/DeepSeek 新闻源、MediaCrawler 安装与登录态验证。
3. Phase 0 全部有真实样本后，再按 TDD 开始写代码：先建 `intel_brief_schema.sql` 和 DB 初始化测试，再接 GitHub / EDGAR / AKShare 三个已部分验证的数据源。
4. Telegram 第 8 Bot 与订阅菜单放到数据源最小闭环之后做，避免先做 UI 但没有真实内容可推送。

---

## 5. 本轮文件变更

- 新增报告文件：`/Users/blackdj/Desktop/OpenEverything/docs/084-intel-brief-implementation-report.md`
- Phase 0 初始清点未修改 OpenEverything 业务代码；后续 6.2/6.3 已按用户授权新增 Intel Brief 基础代码，均未部署。
- 未修改 `/Users/blackdj/Desktop/每日简报/`。
- 未重启任何本机或 Oracle 服务。
- Oracle 临时验证环境：`/tmp/openclaw-intel-phase0-20260706`，仅用于 Phase 0 依赖安装和真实调用验证。

---

## 6. 2026-07-06 补充决策执行记录

### 6.1 国会持仓数据源修复验证

状态：**Senate raw GitHub fallback 已验证可用；House S3 仍 403。**

Oracle 真实调用时间：`2026-07-06T21:50:40Z`

| 路径 | 结果 | 证据 |
|---|---|---|
| `https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json` | 失败 | HTTP `403`；响应头含 `content-type=application/xml`、`server=AmazonS3`；响应体 `AccessDenied`。 |
| `https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json` | 成功 | HTTP `200`；`content_length=2997738`；样本含 `transaction_date=11/10/2020`、`ticker=BYND`、`senator=Ron L Wyden`。 |
| `https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/main/aggregate/all_transactions.json` | 失败 | HTTP `404`，说明该仓库当前可用分支为 `master`。 |
| `timothycarambat/house-stock-watcher-data` 的 `master/main data/all_transactions.json` | 失败 | 两个候选 raw URL 均 HTTP `404`。 |

结论：国会持仓 MVP 可先接 Senate 数据，不再被 `housestockwatcher.com` 主域名 DNS 失败卡住；House 数据作为后续迭代项继续查镜像源。

### 6.2 已落地的非部署代码切片

状态：**已本地 TDD 验证；未部署到 Oracle；未触碰 Telegram Token / MediaCrawler 登录态 / 定价。**

新增文件：

- `packages/clawbot/src/intel/db/intel_brief_schema.sql`：Intel Brief 独立 SQLite schema；按补充决策使用 `tracking_targets` / `tracking_subscriptions` / `tracking_audit_log`，不再使用 `celebrity_watchlist`。
- `packages/clawbot/src/intel/db/store.py`：DB 初始化与开放姓名追踪订阅 helper；同名目标复用，并记录审计日志。
- `packages/clawbot/src/intel/quality/content_moderation.py`：推送前内容过滤入口；关键词预过滤 + 可注入 LLM/规则分类器 + 占位过滤 + `content_moderation_log`。
- `packages/clawbot/src/intel/sources/congress_trading.py`：Senate raw GitHub fallback 解析与拉取模块。
- `packages/clawbot/tests/test_intel_schema_and_tracking.py`
- `packages/clawbot/tests/test_intel_content_moderation.py`
- `packages/clawbot/tests/test_intel_congress_trading.py`

本地验证：

- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_schema_and_tracking.py tests/test_intel_content_moderation.py tests/test_intel_congress_trading.py -q` → `8 passed`。

仍未完成：

- Oracle/国内 worker 长期运行环境尚未创建或部署。
- MediaCrawler 微博/小红书登录态未处理，等待真实账号、Cookie/CDP profile 与目标节点验证。
- Telegram 第 8 Bot 未注册，等待真实 Token。
- X/Reddit/Agent-Reach 未接入，等待用户确认。
- 定价与套餐未实现，等待用户确认。



### 6.3 多服务器运行架构与微博/小红书无人值守优先策略（用户决策更新）

状态：**本地策略模块已 TDD 验证；未部署；未创建国内服务器；未保存 Cookie/Token。**

用户更新：允许按多服务器架构设计，纯国内业务可直接放国内服务器（例如炎火云），需要海外流量的数据源再走海外服务器；允许创建后续所需工程产物；微博/小红书优先设计为全自动运行。

已落地代码：

- `packages/clawbot/src/intel/runtime_policy.py`
  - 国内源：`weibo`、`xiaohongshu`、`akshare`、`zhihu`、`bilibili`、`douyin`、`baidu` 等 → `preferred_worker=domestic`、`region_hint=cn`、`requires_overseas_egress=false`。
  - 海外源：`sec_edgar`、`github_trending`、`openai_rss`、`anthropic_news`、`senate_trading` 等 → `preferred_worker=overseas`、`region_hint=global`、`requires_overseas_egress=true`。
  - 未知源：保留在 `controller`，不擅自派到国内或海外节点。
- `packages/clawbot/tests/test_intel_runtime_policy.py`
  - 覆盖国内/海外/controller 三类路由。
  - 覆盖微博、小红书登录策略：优先 `cdp_cookie` / `cookie` 等持久登录态；二维码 `fallback_only`。

微博/小红书是否可以不扫码：

- 工程设计上可以做到“**免扫码优先**”：优先复用持久浏览器态（CDP profile）、Cookie、手机号登录态/公开页抓取，定时健康检查，登录态失效时告警。
- 但不能承诺“**永不扫码**”：微博、小红书风控可能在异常 IP、设备指纹变化、Cookie 过期、账号风险命中时强制二维码或手机号二次验证。
- 因此当前可验证边界是：代码策略已把二维码降为兜底，不主动把扫码作为常规路径；真实无人值守比例需要后续在目标国内服务器 + 真实账号登录态上跑周期验证。

本地验证：

- RED：`cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_runtime_policy.py -q` → `ModuleNotFoundError: No module named 'src.intel.runtime_policy'`。
- GREEN：`cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_runtime_policy.py -q` → `4 passed`。

仍未完成 / 不能宣称完成：

- 国内服务器（炎火云或其他）尚未实际创建、连通、部署 worker。
- 微博/小红书真实账号、Cookie/CDP profile 尚未提供；未进行扫码或非扫码登录验证。
- MediaCrawler 在目标国内/海外节点上的真实抓取仍未跑通。
- 多服务器调度只完成策略模块，尚未接入 `ExecutionScheduler` 的远程派发。

### 6.4 总体方案与开源搬运规划（用户决策更新）

状态：**已完成规划文档；未部署；未创建/重启服务器；未写入任何凭证。**

用户更新：当前最重要的是先做整体方案规划；完成规划后先去 GitHub 等开源社区找可直接使用的高星轮子并形成搬运规划；开发思路理清后再推进生产变更。海外服务器优先低负载 Oracle 新加坡西，国内服务器优先炎火云；每一步需要在对应项目文件夹记录文档基线。

已落地文档：

- `docs/052-intel-brief-master-plan.md`：Intel Brief 总体方案、开源轮子搬运清单、多服务器架构、分阶段开发路线、验证门和提升建议。
- `/Users/blackdj/Documents/VPS-Config/docs/indexes/intel-brief-runtime-placement.public.md`：Oracle 新加坡西 / 炎火云 / Controller 的 runtime placement 基线，不含任何密钥明文。
- `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md`：追加 Intel Brief runtime placement baseline，避免 VPS 维护时误回撤。
- `docs/002-changelog.md` / `docs/003-docs-index.md` / `docs/009-health.md`：同步 OpenEverything 文档治理入口。

开源调研证据：

- `agent-reach doctor --json` 显示 GitHub 后端为 `gh CLI`。
- `gh search repos` / `gh repo view` 已查询 MediaCrawler、AKShare、edgartools、RSSHub、LiteLLM、APScheduler、OpenBB、Qlib、Senate watcher data、GitHub Trending API 等候选项目的星数、license、更新时间。

当前边界：

- 本轮没有创建或购买服务器。
- 本轮没有读取或输出任何凭证明文。
- 本轮没有部署 worker、重启服务、写入 Cookie/Token。
- 后续生产动作必须先按 `docs/052-intel-brief-master-plan.md` 的 Phase B 做目标节点真实验证。


### 6.5 Phase B 目标节点真实验证起步（持续目标：生产闭环）

状态：**Phase B 已起步；炎火云国内源部分验证成功；Oracle SGW 管理路径阻塞；海外源已用 Oracle Ashburn fallback 验证，不替代 SGW。**

新增证据脚手架：

- `packages/clawbot/scripts/intel_worker_probe.py`：统一 Phase B 证据 JSON 字段。
- `packages/clawbot/tests/test_intel_worker_probe.py`：覆盖国内/海外路由和 JSON 落盘。

真实调用证据：

| 运行环境 | 数据源 | 结果 | 证据路径 |
|---|---|---|---|
| 炎火云 | 微博公开页 | HTTP 200，返回 Sina Visitor System HTML | `packages/clawbot/data/intel_evidence/phaseb/20260706T224401Z-yanhuoyun-domestic-probes.jsonl` |
| 炎火云 | 小红书公开页 | HTTP 200，返回页面 HTML | `packages/clawbot/data/intel_evidence/phaseb/20260706T224401Z-yanhuoyun-domestic-probes.jsonl` |
| 炎火云 | 东方财富行情 API | HTTP 200，样本含 `000001` / `平安银行` | `packages/clawbot/data/intel_evidence/phaseb/20260706T224401Z-yanhuoyun-domestic-probes.jsonl` |
| 炎火云 | AKShare 龙虎榜 | 成功，`akshare==1.18.64`，返回 637 行，样本含 `000021` / `深科技` | `packages/clawbot/data/intel_evidence/phaseb/20260706T225123Z-yanhuoyun-akshare-call-retry.jsonl` |
| Oracle SGW | 管理 SSH | 失败，当前 Mac 直连 `149.118.53.164:22` banner 超时 | 本轮终端证据 + VPS-Config SGW readonly report |
| Oracle SGW | Beszel 状态 | 只读证明已生成，SGW 在 Yanhuo Beszel 中可见/up | `/Users/blackdj/Documents/VPS-Config/credentials/generated/server-status-panel/20260706T224751Z-status-beszel-sgw-readonly.private.md` |
| Oracle Ashburn fallback | SEC 13F | 成功，Berkshire 13F-HR 样本 `2026-05-15` / `2026-03-31` | `packages/clawbot/data/intel_evidence/phaseb/20260706T224830Z-oracle-arm1-overseas-fallback-probes.jsonl` |
| Oracle Ashburn fallback | OpenAI RSS | 成功，标题 `OpenAI News` | 同上 |
| Oracle Ashburn fallback | Anthropic News | 成功，标题 `Newsroom \ Anthropic` | 同上 |
| Oracle Ashburn fallback | Senate raw GitHub | 成功，样本 `BYND` / `Ron L Wyden` | `packages/clawbot/data/intel_evidence/phaseb/20260706T224857Z-oracle-arm1-overseas-fallback-retry.jsonl` |
| Oracle Ashburn fallback | GitHub API | 成功，样本 `codecrafters-io/build-your-own-x`，rate remaining `5` | 同上 |

边界：

- 本轮没有部署 worker，没有重启服务，没有写入生产配置。
- AKShare 只装在炎火云 `/tmp` 临时 venv，未加入长期依赖。
- 微博/小红书只是公开页连通性，不等于 MediaCrawler 登录态抓取已成功。
- Oracle Ashburn fallback 只能证明海外源可用，不能替代 SGW 首选节点验收。

下一步生产闭环切片：

1. 确认/恢复 Oracle SGW 的可执行管理路径，或明确授权以 Oracle Ashburn 暂代海外 worker。
2. 把 Phase B 证据写入 `source_health` 初始化脚本，形成“源验证 → 健康表 → 调度决策”的闭环。
3. 炎火云上验证 MediaCrawler 安装与微博/小红书 Cookie/CDP 登录态；若触发扫码，记录为人工兜底，不宣称全自动。
4. 接入 `ExecutionScheduler` 的只读派发计划，先生成 dispatch evidence，不直接启动定时生产任务。

### 6.6 Phase C/D 生产闭环支架（用户授权 Phase B 后持续推进）

状态：**已完成本地可验证支架；仍未部署、未远程执行、未注册生产调度。**

本轮目标不是停留在 Phase B，而是在已有目标节点验证基础上继续向生产闭环推进。已落地：

- `packages/clawbot/src/intel/sources/base.py`：统一 Source Adapter 契约，所有数据源后续必须返回 `IntelSourceResult`，包含 `evidence_path`，避免“内容来源不可追溯”。
- `packages/clawbot/src/intel/sources/congress_trading.py`：新增 `SenateTransactionsAdapter`，把已验证的 Senate raw GitHub fallback 纳入统一结果结构。
- `packages/clawbot/src/execution/intel_brief.py`：新增独立 Intel Brief 执行场景；当前只生成 `plan_only` 派发计划，按 `runtime_policy` 输出 domestic / overseas / controller，不触发 SSH、不跑远程命令、不推送 Telegram。
- `packages/clawbot/tests/test_intel_source_adapter_base.py`
- `packages/clawbot/tests/test_intel_scheduler_dispatch.py`

证据文件：

| 阶段 | 证据路径 | 结果 |
|---|---|---|
| Phase C | `packages/clawbot/data/intel_evidence/phasec/20260706T230209Z-controller-source-adapter-plan.json` | Source Adapter 契约已本地验证；Senate adapter 绑定 Phase B fallback evidence_path。 |
| Phase D | `packages/clawbot/data/intel_evidence/phased/20260706T230209Z-controller-dispatch-plan.json` | 默认 8 个源生成派发计划：国内 3 个、海外 5 个；`dispatch_mode=plan_only`。 |

验证命令：

```bash
cd packages/clawbot && .venv312/bin/python -m pytest \
  tests/test_intel_schema_and_tracking.py \
  tests/test_intel_content_moderation.py \
  tests/test_intel_congress_trading.py \
  tests/test_intel_runtime_policy.py \
  tests/test_intel_worker_probe.py \
  tests/test_intel_source_adapter_base.py \
  tests/test_intel_scheduler_dispatch.py -q
```

结果：`20 passed`。

仍未完成 / 不可宣称完成：

- 未恢复 Oracle SGW 管理执行路径；海外首选 worker 仍未真实跑源。
- 未把 `intel_brief.py` 注册进 `ExecutionScheduler` 生产循环。
- 未部署任何 worker service，未创建长期 venv，未重启服务。
- 未写入 Telegram 第 8 Bot Token、微博/小红书 Cookie/CDP profile 或任何密钥。
- MediaCrawler 微博/小红书登录态和无人值守能力仍需在炎火云真实验证。

### 6.7 Worker Contract / Source Health 追加推进（持续生产闭环目标）

状态：**已完成本地可验证支架；仍未远程执行、未部署、未写凭证。**

新增代码：

- `packages/clawbot/src/intel/worker_contract.py`
  - `IntelWorkerRequest`：controller → worker 的 JSON-safe 请求，只包含 `request_id`、`source`、`worker`、`region_hint`、`limit`、`metadata` 等路由/执行意图。
  - `IntelWorkerResponse`：worker → controller 的统一响应，可从 `IntelSourceResult` 包装而来。
  - metadata 对 `token` / `secret` / `cookie` / `password` / `key` 等敏感键直接拒绝。
- `packages/clawbot/src/execution/intel_brief.py`
  - `dispatch_source_job` 仍保持 `plan_only`，但现在包含可审计 `worker_request`。
- `packages/clawbot/src/intel/db/store.py`
  - 新增 `record_source_health` / `get_source_health`：支持失败累计、成功恢复清零、最近失败原因记录。

证据文件：

| 阶段 | 证据路径 | 结果 |
|---|---|---|
| Phase D | `packages/clawbot/data/intel_evidence/phased/20260706T230933Z-controller-worker-contract-plan.json` | `senate_trading` 生成 overseas worker_request；默认 run plan 仍为国内 3 / 海外 5；无密钥字段。 |
| Phase E | `packages/clawbot/data/intel_evidence/phasee/20260706T230933Z-source-health-seed.json` | 临时 SQLite DB 中验证失败计数累加与成功恢复清零；未创建/修改生产 DB。 |

SGW 只读排查：

- VPS-Config 已存在 SGW bootstrap/readiness SOP，且明确提到当前 Mac SSH banner timeout 应归类为 `management-path mismatch`，不能误判为源验证完成。
- 当前 `~/.ssh/config` 未发现可直接复用的 SGW alias。
- 本轮未修改安全组、未新增 SSH 配置、未打开 Mac /32、未读取或输出密钥明文。

仍未完成 / 不可宣称完成：

- `worker_request` 尚未被真实 worker 执行。
- SGW 仍不是已验证的生产 overseas worker。
- 炎火云 MediaCrawler 登录态仍未跑通真实无人值守抓取。
- `source_health` helper 尚未接入真实数据源执行结果，只完成本地 DB 契约验证。

### 6.8 本轮最终验证记录

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T231131Z-worker-contract-source-health-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`26 passed`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮仍然保持边界：没有目标 worker 远程执行、没有服务重启、没有生产 scheduler 注册、没有 Telegram 推送、没有写入 Token/Cookie/密钥。

### 6.9 Worker Runner / Adapter Registry / SGW Read-only Preflight

状态：**worker 本地执行闭环支架已验证；SGW 仍未达到生产 worker 执行门槛。**

新增代码：

- `packages/clawbot/src/intel/worker_runner.py`
  - `execute_worker_request`：执行一个 `IntelWorkerRequest`，调用注册 adapter，返回 `IntelWorkerResponse`。
  - `execute_worker_request_json`：接收 JSON-safe request，返回 JSON-safe response，便于后续 worker service/CLI 使用。
  - 支持可选 `db_path`，把 success/failure 写入 `source_health`。
- `packages/clawbot/src/intel/sources/registry.py`
  - `build_default_source_adapters`：默认只注册已有 Phase B 真实证据的 `senate_trading`。
- `packages/clawbot/tests/test_intel_worker_runner.py`
  - 覆盖成功执行、adapter 异常、未知 source、JSON round-trip、source_health 写入。

OpenEverything 证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasee/20260706T232159Z-worker-runner-local-contract.json` | 使用注入 adapter 验证 request JSON → response JSON → source_health；未远程执行，未触发外部调用。 |

SGW 只读证据：

| 证据路径 | 结果 |
|---|---|
| `/Users/blackdj/Documents/VPS-Config/credentials/generated/oracle-sg-west-readonly-preflight/20260706T232032Z-oracle-sg-west-readonly-preflight.private.md` | `PRODUCTION_ACTION none`；`read_only_api_run=completed-with-launch-blockers`；`status=blocked-launch-prerequisites`；OCI config/key fields 为 present/ok，但 launch prerequisites 仍有 blocker。 |

当前边界：

- SGW read-only preflight 不等于 SSH 管理路径恢复。
- Worker runner 还没有部署成服务，也没有在 SGW/炎火云上真实执行。
- 默认 registry 只包含已验证 Senate fallback；其他数据源必须先有 Phase B 目标节点证据再注册。

### 6.10 本轮最终验证记录（Worker Runner + SGW preflight）

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233012Z-worker-runner-sgw-preflight-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`31 passed`
- SGW read-only preflight：报告生成于 `/Users/blackdj/Documents/VPS-Config/credentials/generated/oracle-sg-west-readonly-preflight/20260706T232032Z-oracle-sg-west-readonly-preflight.private.md`，状态 `blocked-launch-prerequisites`，`PRODUCTION_ACTION none`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮仍然保持边界：没有目标 worker 服务部署、没有 SGW/炎火云远程执行、没有生产 scheduler 注册、没有 Telegram 推送、没有写入 Token/Cookie/密钥。

### 6.11 Worker CLI 入口与 fallback readiness

状态：**CLI 入口已本地验证；目标 worker 真实执行仍未完成。**

新增代码：

- `packages/clawbot/scripts/intel_worker_cli.py`
  - 从 stdin 或 `--input` 读取 `IntelWorkerRequest` JSON。
  - 默认使用 `build_default_source_adapters()`。
  - 可通过 `--db` 写入 `source_health`。
  - stdout 输出 `IntelWorkerResponse` JSON。
  - 返回码：成功 `0`；业务失败/未知源 `2`；JSON 解析失败 `1`。
- `packages/clawbot/tests/test_intel_worker_cli.py`
  - 覆盖 stdin、文件输入、DB 写入、未知源、坏 JSON。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasee/20260706T233517Z-worker-cli-local-execution.json` | 本地 CLI 执行 `senate_trading` 成功，样本含 `BYND` / `Ron L Wyden`，临时 DB source_health 写入成功。 |
| `packages/clawbot/data/intel_evidence/phasee/20260706T233541Z-oracle-arm1-worker-cli-readiness-readonly.json` | `oracle-arm1` SSH 成功，Python 3.12.3；常见路径未发现 OpenEverything 项目。 |

边界：

- 本地 CLI 真实调用不能替代 SGW/炎火云目标节点证据。
- `oracle-arm1` 只读 readiness 不等于已部署 fallback worker。
- 本轮未拷贝文件到远程、未创建 venv、未重启服务、未注册 scheduler、未写密钥。

### 6.12 本轮最终验证记录（Worker CLI）

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233730Z-worker-cli-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`35 passed`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮仍然保持边界：未部署 worker service，未在 SGW/炎火云/Oracle Ashburn 远程执行新 CLI，未注册生产 scheduler，未写入 Token/Cookie/密钥。

### 6.13 Worker Bundle 与 oracle-arm1 fallback 真实远程执行

状态：**海外 fallback 远程 worker CLI 最小闭环已验证；SGW preferred worker 仍未验证。**

新增代码：

- `packages/clawbot/scripts/intel_worker_bundle.py`
  - 构建最小 worker bundle：`scripts/intel_worker_cli.py`、`src/intel/*`、SQLite schema。
  - Manifest 标注 `secrets_included=false`、`production_action=none`、rollback cleanup。
- `packages/clawbot/tests/test_intel_worker_bundle.py`
  - 覆盖 bundle 文件清单、manifest、独立目录 CLI smoke。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasee/20260706T234228Z-worker-bundle-local-evidence.json` | 本地 bundle 构建与 smoke 成功；使用 unknown source 避免外部调用。 |
| `packages/clawbot/data/intel_evidence/phasee/20260706T234325Z-oracle-arm1-worker-cli-remote-execution.json` | oracle-arm1 `/tmp` 临时 staging 执行 `senate_trading` 成功，返回 BYND / Ron L Wyden 样本，source_health `failure_count=0`；cleanup 后二次验证 `remote_stage_absent`。 |

边界：

- 这是 Oracle Ashburn fallback 证据，不是 Oracle SGW preferred worker 证据。
- 未创建 systemd、cron、长期 venv、生产 DB、生产配置、Token/Cookie。
- 远程 staging 已删除；回滚命令为 `rm -rf /tmp/openclaw-intel-worker-20260706T234325Z`，且已验证目录不存在。

### 6.14 本轮最终验证记录（Worker Bundle + oracle-arm1 remote fallback）

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T234653Z-worker-bundle-remote-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`37 passed`
- oracle-arm1 fallback 远程 worker CLI：`senate_trading` 成功；cleanup_ok；二次验证 `remote_stage_absent`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：这是 Oracle Ashburn fallback 临时执行证据，不是 SGW preferred worker 证据；没有部署服务、没有 systemd/cron、没有长期 venv、没有生产配置、没有 Token/Cookie。

### 6.15 炎火云 AKShare worker CLI 真实远程执行

状态：**国内 worker 非登录数据源最小闭环已验证；仍未部署常驻服务。**

新增代码：

- `packages/clawbot/src/intel/sources/astock_flow.py`
  - `AkshareLhbAdapter`：lazy import `akshare`，调用 `stock_lhb_detail_em()`。
  - `normalize_lhb_records`：归一化中文/英文列名为 `code/name/reason/close_price`。
- `packages/clawbot/tests/test_intel_astock_flow.py`
- `packages/clawbot/tests/test_intel_python310_compat.py`
- 更新 `packages/clawbot/src/intel/sources/registry.py` 与 `packages/clawbot/scripts/intel_worker_bundle.py`，把 `akshare` 纳入默认 registry/bundle。

实际障碍与解决：

| 障碍 | 证据 | 解决 |
|---|---|---|
| 炎火云 Python 3.10 不支持 `datetime.UTC` | `packages/clawbot/data/intel_evidence/phasee/20260706T235130Z-yanhuoyun-akshare-worker-cli-remote-execution.json` | 改为 `datetime.timezone.utc`，并新增 Python 3.10 兼容静态测试。 |
| AKShare/tqdm 进度条污染取证输出 | `packages/clawbot/data/intel_evidence/phasee/20260706T235832Z-yanhuoyun-akshare-worker-cli-clean-json.json` | worker runner 捕获 adapter stdout；取证时分离 stdout/stderr，stdout 验证为纯 JSON。 |

成功证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasee/20260707T000126Z-yanhuoyun-akshare-worker-cli-clean-stdout.json` | 炎火云临时 worker CLI 执行 `akshare` 成功，样本 `000021` / `深科技`，source_health `failure_count=0`，cleanup_ok，`remote_stage_absent`。 |

边界：

- 只在 `/tmp` 临时 staging 中创建 venv 并安装 `akshare==1.18.64`，执行后删除。
- 未创建 systemd、cron、长期 venv、生产 DB、生产配置、Token/Cookie。
- 这证明 domestic 非登录源最小 worker CLI 可行，但不证明微博/小红书 MediaCrawler 无人值守已可用。

### 6.16 本轮最终验证记录（Yanhuoyun AKShare domestic worker）

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260707T000629Z-yanhuoyun-akshare-domestic-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`43 passed`
- 炎火云 domestic worker 临时 CLI：`akshare` 成功；stdout 为纯 JSON；样本 `000021` / `深科技`
- 远程临时 SQLite `source_health.failure_count=0`
- cleanup_ok；二次验证 `remote_stage_absent`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：只验证 AKShare 非登录国内源；未验证 MediaCrawler/微博/小红书登录态；未部署常驻服务、cron、systemd、生产 DB、生产配置或任何 Token/Cookie。

### 6.17 Remote Runner 固化与双 worker 复核

状态：**可重复 one-shot 远程执行原语已验证；仍未启用常驻服务或 scheduler。**

新增代码：

- `packages/clawbot/scripts/intel_worker_remote_run.py`
  - 构建最小 worker bundle。
  - 通过 SSH 临时 staging 到目标 worker `/tmp/openclaw-intel-worker-<stamp>`。
  - 执行 `scripts/intel_worker_cli.py`。
  - 查询远程临时 SQLite `source_health`。
  - 执行 cleanup 并写 evidence。
- `packages/clawbot/tests/test_intel_worker_remote_runner.py`
  - 覆盖成功/失败、cleanup、evidence、直接脚本 help。

真实复核证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasee/20260707T001230Z-remote-runner-oracle-arm1-senate.json` | oracle-arm1 fallback 执行 `senate_trading` 成功，样本 BYND / Ron L Wyden，source_health `failure_count=0`，cleanup_ok，`remote_stage_absent`。 |
| `packages/clawbot/data/intel_evidence/phasee/20260707T001324Z-remote-runner-yanhuoyun-akshare.json` | 炎火云 domestic worker 执行 `akshare` 成功，样本 `000021` / `深科技`，source_health `failure_count=0`，cleanup_ok，`remote_stage_absent`。 |

边界：

- remote runner 仍是 one-shot 临时执行，不是常驻 worker service。
- 未创建 systemd、cron、生产配置、生产 DB、Token/Cookie。
- oracle-arm1 是海外 fallback；SGW preferred worker 管理路径仍未闭合。
- 炎火云证据覆盖 AKShare 非登录源，不覆盖 MediaCrawler/微博/小红书登录态。

### 6.18 本轮最终验证记录（Remote Runner）

证据路径：`packages/clawbot/data/intel_evidence/phasee/20260707T001745Z-remote-runner-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`46 passed`
- remote runner / oracle-arm1 / `senate_trading`：成功；样本 BYND / Ron L Wyden；cleanup verified
- remote runner / 炎火云 / `akshare`：成功；样本 `000021` / `深科技`；cleanup verified
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：remote runner 仍是一键临时执行原语，不是生产 scheduler；未创建常驻服务、cron、systemd、生产配置、Token/Cookie。SGW preferred worker 和 MediaCrawler 社媒登录态仍未闭合。

### 6.19 Collect-once 多源远程采集

状态：**controller one-shot 多源采集已验证；仍未接入生产 scheduler / Telegram。**

新增代码：

- `packages/clawbot/scripts/intel_collect_once.py`
  - 按 source 映射到 worker profile。
  - 调用 `intel_worker_remote_run.py`。
  - 聚合 child evidence、response、source_health、cleanup 状态。
- `packages/clawbot/tests/test_intel_collect_once.py`
  - 覆盖默认 profile、成功聚合、未知源失败且不远程执行。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasef/20260707T002040Z-collect-once-senate-akshare.json` | `senate_trading` + `akshare` 一次性采集成功，summary `success=2 / failed=0`。 |
| `packages/clawbot/data/intel_evidence/phasef/20260707T002040Z-child-runs/20260707T002040Z-senate_trading.json` | oracle-arm1 fallback 返回 BYND / Ron L Wyden，source_health `failure_count=0`，cleanup verified。 |
| `packages/clawbot/data/intel_evidence/phasef/20260707T002040Z-child-runs/20260707T002040Z-akshare.json` | 炎火云返回 `000021` / `深科技`，source_health `failure_count=0`，cleanup verified。 |

边界：

- 这是 one-shot controller 编排，不是 scheduler 注册。
- 未创建常驻 worker service、cron、systemd、生产 DB、生产配置、Token/Cookie。
- 只覆盖已验证的非登录源：Senate + AKShare。

### 6.20 本轮最终验证记录（Collect-once）

证据路径：`packages/clawbot/data/intel_evidence/phasef/20260707T002711Z-collect-once-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`49 passed`
- collect-once：`senate_trading` + `akshare` 成功，summary `success=2 / failed=0`
- child runs：oracle-arm1 与炎火云均 cleanup verified
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：collect-once 是 one-shot controller 编排，不是生产 scheduler；未部署服务、未注册 cron/systemd、未写入 Token/Cookie。

### 6.21 Phase F Dry-run 简报生成

状态：**真实采集结果已能生成可读 dry-run 简报；仍未调用 LLM / Telegram / scheduler。**

新增代码：

- `packages/clawbot/src/intel/brief_builder.py`
  - 读取 collect-once evidence。
  - 归一化 `senate_trading` 与 `akshare` 展示字段。
  - stable-key 去重，保留首条。
  - 调用统一 `content_moderation` 入口；命中需复核内容时输出占位并清理正文细节。
  - 写出 Markdown 与 JSON dry-run evidence。
- `packages/clawbot/scripts/intel_brief_dry_run.py`
  - CLI 参数：`--collect-evidence` / `--markdown-output` / `--json-output` / `--stamp`。
  - 只转换已有 evidence，不访问外部源、不调用 LLM、不推送 Telegram。
- `packages/clawbot/tests/test_intel_brief_dry_run.py`
  - 覆盖规范化、去重、Markdown/JSON 输出、内容过滤防泄漏、CLI 输出。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.md` | 使用真实 collect-once evidence 渲染 Markdown dry-run，包含国会持仓 BYND/Ron L Wyden 与 A股龙虎榜 深科技样本。 |
| `packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.json` | JSON evidence 显示 `source_count=2`、`item_count_before_dedup=2`、`deduped_count=0`、`moderated_count=0`、`rendered_count=2`。 |

边界：

- 输入来自此前真实远程采集 evidence；本步骤本身不再访问外部数据源。
- 未调用 LLM routing，未生成付费用户最终摘要。
- 未推送 Telegram，未注册 scheduler，未创建常驻 worker service。
- 未写生产 DB；未写入 Token/Cookie/密钥。

### 6.22 本轮最终验证记录（Dry-run 简报生成）

证据路径：`packages/clawbot/data/intel_evidence/phasef/20260707T004119Z-brief-dry-run-verification.json`

验证结果：

- `ruff`：`All checks passed!`
- Intel Brief 相关 pytest：`54 passed`
- dry-run evidence：`packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.md` / `.json` 已由真实 collect-once evidence 生成
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：完成的是 one-shot 内容层 dry-run，不是生产投递闭环；未调用 LLM、未推送 Telegram、未注册 scheduler、未创建常驻服务、未写 Token/Cookie/密钥。生产闭环下一层仍需在同样证据标准下补“真实数据 → LLM routing 摘要 dry-run → 订阅者筛选 → Telegram 沙盒推送”。

### 6.23 Phase G LLM 摘要 dry-run

状态：**真实采集数据已完成 LLM routing 摘要 dry-run；仍未生产推送。**

新增代码/配置：

- `packages/clawbot/config/llm_routing.json`
  - 新增 `routing_profiles.intel_brief`：生产摘要偏好 family 为 `qwen/gemini/gpt-oss/deepseek/llama/gemma/g4f`。
  - 新增 dry-run family `intel_local`，绑定本地 Ollama `qwen2.5:1.5b`。
  - 设置 `fallback_chains.intel_local=[]`，本地取证时不自动落到外部 provider。
- `packages/clawbot/src/llm_routing_config.py`
  - 新增 `get_routing_profile()`。
- `packages/clawbot/src/intel/llm_summary.py`
  - 从 Phase F dry-run JSON 构造摘要 prompt。
  - 调用现有 LiteLLM routing；记录 model family、token usage、错误类型。
  - 支持失败后抽取式 fallback evidence。
- `packages/clawbot/scripts/intel_llm_summary_dry_run.py`
  - 支持 `--family` 与 `--max-tokens`，用于受控本地取证。
- `packages/clawbot/tests/test_intel_llm_summary.py`
  - 覆盖 routing profile、family 选择、prompt、注入式 LLM 调用、失败 fallback、CLI 输出、family override。

实际障碍与解决：

| 障碍 | 证据 | 解决 |
|---|---|---|
| `gemma` dry-run 首次调用本地 8B 模型超时，且现有 Router fallback 会继续尝试外部 provider，暴露 auth/model 不可用噪音。 | `packages/clawbot/data/intel_evidence/phaseg/20260707T005033Z-llm-summary-dry-run.json` | 新增 `intel_local` family 指向本地 `qwen2.5:1.5b`，并设置该 family 无 fallback；CLI 用 `--family intel_local --max-tokens 160` 做受控本地 LLM 证据。 |

成功证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseg/20260707T005640Z-llm-summary-dry-run-intel-local.json` | LLM routing 调用成功；family=`intel_local`；prompt_tokens=353、completion_tokens=159、total_tokens=512；输入为真实 Phase F dry-run evidence。 |
| `packages/clawbot/data/intel_evidence/phaseg/20260707T005640Z-llm-summary-dry-run-intel-local.md` | 生成可读摘要草稿，包含 BYND/Ron L Wyden 与 深科技 两条真实采集条目。 |

边界：

- 本次成功 LLM 调用是本地 Ollama dry-run，不产生外部 API 费用。
- 未验证生产优先 provider 的实际摘要质量、费用、RPM/TPM 余量。
- 未推送 Telegram，未注册 scheduler，未创建常驻服务，未写生产 DB。
- 未写入或展示任何 Token/Cookie/API Key。

### 6.24 本轮最终验证记录（LLM 摘要 dry-run）

证据路径：`packages/clawbot/data/intel_evidence/phaseg/20260707T010034Z-llm-summary-postdocs-verification.json`

验证结果：

- `llm_routing.json`：`python -m json.tool` 通过
- `ruff`：变更范围 `All checks passed!`
- pytest：Intel Brief + LLM routing 相关测试 `148 passed`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：LLM 摘要 dry-run 已用本地 `intel_local` routing family 真实跑通，但不是生产投递闭环；未推送 Telegram、未注册 scheduler/cron/systemd、未创建常驻服务、未写生产 DB、未展示或写入任何密钥。

### 6.25 Phase H 订阅者与投递层沙盒

状态：**订阅者筛选、delivery_log 与 fake Telegram outbox 已验证；仍未调用真实 Telegram。**

新增代码：

- `packages/clawbot/src/intel/delivery.py`
  - `seed_sandbox_subscriber()`：在 sandbox SQLite DB 中创建测试 subscriber、sandbox plan、active subscription、source preferences。
  - `build_delivery_message()`：从 LLM summary evidence 渲染 Telegram 长度安全的投递消息。
  - `FakeTelegramSender`：写 JSONL outbox，明确 `network=not_called`。
  - `deliver_summary_to_subscribers()`：筛选 active telegram subscriber，调用 sender，并写 `delivery_log`。
  - `build_delivery_sandbox()`：整合 sandbox DB、outbox、evidence 与 rollback 路径。
- `packages/clawbot/scripts/intel_delivery_sandbox.py`
  - CLI 参数：`--summary-evidence` / `--db` / `--outbox` / `--output` / `--stamp`。
- `packages/clawbot/tests/test_intel_delivery_sandbox.py`
  - 覆盖 sandbox 订阅者、消息渲染、fake sender、delivery_log、evidence、CLI。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseh/20260707T010624Z-delivery-sandbox.json` | 输入 Phase G LLM summary evidence；eligible=1、sent=1、failed=0、delivery_log_count=1、network_calls=0。 |
| `packages/clawbot/data/intel_evidence/phaseh/20260707T010624Z-delivery-sandbox.db` | sandbox SQLite DB；包含 1 个 subscriber、1 个 plan、1 条 active subscription、2 条 source preference、1 条 delivery_log。 |
| `packages/clawbot/data/intel_evidence/phaseh/20260707T010624Z-fake-telegram-outbox.jsonl` | fake Telegram outbox，写入 1 条消息；`network=not_called`。 |

边界：

- 该步骤没有读取或写入真实 Telegram Token。
- 没有调用 Telegram Bot API；fake sender 的 `network_calls=0`。
- 没有注册 scheduler/cron/systemd，没有创建常驻服务。
- 没有写生产 DB；sandbox run 的回滚路径已记录在 evidence 的 `rollback` 字段。

### 6.26 本轮最终验证记录（投递沙盒）

证据路径：`packages/clawbot/data/intel_evidence/phaseh/20260707T010821Z-delivery-sandbox-verification.json`

验证结果：

- `llm_routing.json`：`python -m json.tool` 通过
- `ruff`：变更范围 `All checks passed!`
- pytest：Intel Brief + LLM routing 相关测试 `154 passed`
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git -C /Users/blackdj/Documents/VPS-Config diff --check` 通过

本轮边界：投递沙盒仅使用 fake Telegram sender 与 sandbox SQLite DB；未调用真实 Telegram Bot API，未注册 scheduler/cron/systemd，未创建常驻服务，未写生产 DB，未写入或展示任何密钥。

### 6.27 Phase I Scheduled sandbox 排练

状态：**本地 scheduled controller rehearsal 已闭合；仍未注册生产调度或真实 Telegram。**

新增代码：

- `packages/clawbot/src/intel/scheduled_pipeline.py`
  - `build_schedule_decision()`：判断 enabled、计划 HH:MM、同日重复运行。
  - `run_scheduled_sandbox_pipeline()`：到点后串联 brief dry-run、LLM summary dry-run、delivery sandbox，并写统一 scheduled evidence。
- `packages/clawbot/scripts/intel_scheduled_sandbox.py`
  - CLI 参数：`--collect-evidence` / `--output-dir` / `--output` / `--now` / `--time` / `--stamp` / `--llm-mode`。
- `packages/clawbot/tests/test_intel_scheduled_pipeline.py`
  - 覆盖到点/未到点/同日去重、skipped evidence、不生成下游 artifact、成功串联 brief+LLM+delivery、CLI。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-scheduled-sandbox.json` | 输入 Phase F 真实 collect evidence；schedule reason=`due`；brief rendered=2；LLM `llm_attempted=false`；delivery `eligible=1 / sent=1 / failed=0`；`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-brief-dry-run.md` / `.json` | 从真实 Senate + AKShare collect evidence 生成 scheduled run 下的 brief dry-run artifact。 |
| `packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-llm-summary-dry-run.md` / `.json` | fallback-only 摘要 artifact；未调用外部 LLM。 |
| `packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-delivery-sandbox.json` / `.db` / `fake-telegram-outbox.jsonl` | sandbox subscriber + fake Telegram outbox；真实网络调用数为 0。 |

边界：

- 没有注册 scheduler/cron/systemd，没有创建常驻服务。
- 没有读取或写入真实 Telegram Token，没有调用 Bot API。
- 没有写生产 DB；只写 scheduled sandbox artifact 和 sandbox SQLite DB。
- 没有远程抓取新数据；本步骤只消费既有 Phase F 真实 collect evidence。

### 6.28 本轮最终验证记录（scheduled sandbox）

证据路径：`packages/clawbot/data/intel_evidence/phasei/20260707T011701Z-scheduled-sandbox-verification.json`

验证范围：scheduled pipeline 单测、Intel Brief 相关测试、LLM routing 配置 JSON、ruff、OpenEverything/VPS-Config diff check。

本轮边界：scheduled sandbox 已形成可审计的本地“定时触发排练”链路，但仍不是生产闭环；未推送真实 Telegram、未注册生产 scheduler/cron/systemd、未创建常驻 worker、未验证 SGW preferred worker、未完成自然日真实定时演练。

### 6.29 Phase J ExecutionScheduler 安全闸门接入

状态：**已接入现有 ExecutionScheduler 的 sandbox-only 安全路径；生产模式仍被硬闸门阻断。**

新增/修改代码：

- `packages/clawbot/src/execution/intel_brief.py`
  - 新增 `build_intel_brief_scheduler_gate()`：读取 `INTEL_BRIEF_ENABLED` / `INTEL_BRIEF_MODE` / token/chat/worker placement/production ack 等环境开关，输出脱敏 gate decision。
  - 生产模式当前无论如何都会带 `production_runner_not_implemented` 闸门，避免误把 sandbox 支架当成真实生产推送。
- `packages/clawbot/src/execution/scheduler.py`
  - 新增 `_last_intel_brief_date`、`intel_brief_sandbox_runner` 注入点。
  - `_loop()` 新增 `INTEL_BRIEF_TIME` 解析与 `_run_intel_brief()` 调用。
  - `_run_intel_brief()` 默认只执行 sandbox runner，并在生产硬闸门失败时标记当天已处理，避免每分钟重复撞闸。
  - 修复 async scheduler context 调用同步 scheduled pipeline 的问题：默认 runner 通过 `asyncio.to_thread()` 执行。
- `packages/clawbot/scripts/intel_scheduler_gate_probe.py`
  - 只读 gate probe CLI，写脱敏 evidence，不执行调度、不调用 Telegram、不抓外部数据源。
- `packages/clawbot/config/.env.example`
  - 新增 Intel Brief 独立调度变量，默认关闭/沙盒/fallback-only。
- `packages/clawbot/src/api/routers/controls.py`
  - 控制面板静态任务表登记 `intel_brief`，默认 disabled。
- `packages/clawbot/tests/test_intel_scheduler_gate.py`
  - 覆盖默认关闭、生产硬闸门、sandbox ready、同日去重、scheduler 注入 runner、blocked gate 不执行、gate probe CLI 脱敏、默认 runner 在 async loop 中可用。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasej/20260707T012933Z-production-hard-gate-blocked.json` | `INTEL_BRIEF_MODE=production` 被硬闸门阻断，missing gates 包含 token/chat/worker placement/production ack/production runner。证据只含布尔存在性，不含明文密钥。 |
| `packages/clawbot/data/intel_evidence/phasej/20260707T013200Z-execution-scheduler-sandbox-invocation.json` | 通过 `ExecutionScheduler._run_intel_brief()` 入口触发 sandbox-only run；brief rendered=2；LLM `attempted=false`；delivery `eligible=1 / sent=1 / failed=0`；`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasej/20260707T083100Z-scheduled-sandbox.json` | scheduler 入口触发的下游 scheduled sandbox evidence。 |

实际障碍与解决：

| 障碍 | 证据 | 解决 |
|---|---|---|
| 在 async scheduler loop 中直接调用 `run_scheduled_sandbox_pipeline()` 会触发 `RuntimeError: asyncio.run() cannot be called from a running event loop`。 | 本轮真实 scheduler sandbox 初次调用失败终端输出；新增回归测试 `test_execution_scheduler_default_sandbox_runner_works_inside_async_loop` 先复现失败。 | `_run_intel_brief()` 对默认 sandbox runner 使用 `asyncio.to_thread()`，避免嵌套 event loop；测试已通过。 |

边界：

- 仍未注册或启动真实 scheduler/cron/systemd；本轮只改代码路径并做本地显式调用。
- 没有调用真实 Telegram Bot API；fake sender `network_calls=0`。
- 没有写生产 DB；只写 Phase J evidence 和 sandbox SQLite DB。
- 没有远程抓取新数据；scheduler sandbox 使用既有 Phase F collect evidence。
- 没有输出或写入任何真实 token/cookie/API key 明文。

### 6.30 本轮最终验证记录（ExecutionScheduler 安全闸门）

证据路径：`packages/clawbot/data/intel_evidence/phasej/20260707T013304Z-scheduler-gate-verification.json`

验证结果：

- `llm_routing.json`：JSON 校验通过
- Phase J evidence：全部 JSON 可解析
- `ruff`：Intel Brief / scheduler / controls / scripts / tests 变更范围通过
- pytest：Intel Brief + LLM routing + Execution facade 相关测试通过
- fake secret 泄漏检查：通过
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git diff --check` 通过

本轮边界：ExecutionScheduler 安全闸门已接入并可 sandbox-only 本地执行，但未启用生产 scheduler/cron/systemd，未调用真实 Telegram Bot API，未创建常驻 worker，未写生产 DB，未完成自然日演练。

### 6.31 Phase K Telegram Bot API sandbox sender 合同层

状态：**真实 Telegram 发送前的合同层已落地；没有调用真实 Bot API。**

新增代码：

- `packages/clawbot/src/intel/telegram_delivery.py`
  - `build_telegram_sandbox_gate()`：读取 token/chat id/sandbox ack，只输出布尔存在性与 missing gates。
  - `TelegramBotApiSender`：封装 Telegram `sendMessage` 合同，支持注入 transport；公开结果脱敏 endpoint 与 chat id。
  - `build_telegram_sandbox_probe()`：写 gate/contract evidence；默认不允许真实网络。
- `packages/clawbot/scripts/intel_telegram_sandbox_probe.py`
  - 默认 gate-only；`--allow-real-network` 才允许在 gate ready 时调用真实 Bot API。
- `packages/clawbot/tests/test_intel_telegram_delivery.py`
  - 覆盖缺凭证阻断、token/chat 脱敏、注入 transport 合同发送、probe evidence、CLI blocked evidence。
- `packages/clawbot/config/.env.example`
  - 新增 `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK=`，默认空。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-gate-blocked.json` | 当前缺真实 token/chat/ack，Telegram sandbox gate blocked；`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-contract-injected.json` | 使用注入 transport 验证 sender 合同成功；`network=injected_transport`、`network_calls=1`、`message_id=20260707`；无真实网络调用。 |

边界：

- 没有调用真实 Telegram Bot API。
- 没有写真实 token/chat id 明文；证据只记录布尔存在性。
- 没有注册 scheduler/cron/systemd，没有写生产 DB。
- 注入 transport 证据只证明代码合同，不证明真实 Telegram token/chat id 可用。

### 6.32 本轮最终验证记录（Telegram sender 合同层）

证据路径：`packages/clawbot/data/intel_evidence/phasek/20260707T014408Z-telegram-contract-verification.json`

验证结果：

- Phase K evidence：全部 JSON 可解析
- `ruff`：Telegram 合同层代码/CLI/测试通过
- `.env.example`：`INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK` 存在
- pytest：Phase K 单测通过；Intel Brief + LLM routing 相关测试通过
- token/chat/fake secret 泄漏检查：通过
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git diff --check` 通过

本轮边界：Telegram sender 合同层已验证，但未调用真实 Telegram Bot API，未验证真实 token/chat id，未启用生产 scheduler，未创建常驻 worker，未写生产 DB。

### 6.33 Phase L-pre Telegram summary delivery 集成预演

状态：**真实 Intel Brief summary evidence 已接入 Telegram sender 合同层；没有真实联网。**

新增代码：

- `packages/clawbot/src/intel/telegram_delivery.py`
  - 新增 `build_telegram_summary_delivery_probe()`：读取 LLM summary evidence，调用 `build_delivery_message()` 生成 Telegram 消息，并走 sandbox gate/transport。
- `packages/clawbot/scripts/intel_telegram_summary_probe.py`
  - CLI 参数：`--summary-evidence` / `--output` / `--allow-real-network`。
- `packages/clawbot/tests/test_intel_telegram_delivery.py`
  - 新增 summary evidence → Telegram delivery probe 的 blocked、injected transport、CLI 测试。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-gate-blocked.json` | 输入真实 Phase I LLM summary evidence；渲染 Telegram message preview 成功；缺 token/chat/ack，gate blocked；`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-contract-injected.json` | 输入同一真实 summary evidence；注入 transport 合同成功；`network=injected_transport`、`message_id=2026070701`、`message_chars=344`；未调用真实 Telegram。 |

边界：

- 没有调用真实 Telegram Bot API。
- 没有写真实 token/chat id 明文；证据只记录布尔存在性。
- 没有注册 scheduler/cron/systemd，没有写生产 DB。
- 没有抓取新数据；输入为已有 Phase I summary evidence。

### 6.34 本轮最终验证记录（Telegram summary delivery 集成预演）

证据路径：`packages/clawbot/data/intel_evidence/phasel/20260707T015419Z-telegram-summary-delivery-verification.json`

验证结果：

- Phase L-pre evidence：全部 JSON 可解析
- `ruff`：Telegram summary delivery 相关代码/CLI/测试通过
- pytest：Phase L-pre 单测通过；Intel Brief + LLM routing 相关测试通过
- token/chat/fake secret 泄漏检查：通过
- OpenEverything：`git diff --check` 通过
- VPS-Config：`git diff --check` 通过

本轮边界：真实 Intel Brief summary evidence 已接入 Telegram sender 合同层，但未调用真实 Telegram Bot API，未验证真实 token/chat id，未启用生产 scheduler，未创建常驻 worker，未写生产 DB。


### 6.35 Phase M Production Readiness 审计

状态：**已形成只读生产就绪审计；当前生产仍被硬闸门阻断。**

新增代码：

- `packages/clawbot/src/intel/production_readiness.py`
  - 汇总 collect evidence、summary evidence、Telegram sandbox gate、scheduler production gate、worker placement gate。
- `packages/clawbot/scripts/intel_production_readiness_audit.py`
  - 写出 readiness evidence；相对路径按 OpenEverything 项目根目录解析。
- `packages/clawbot/tests/test_intel_production_readiness.py`
  - 覆盖缺外部门槛阻断、密钥存在时仍因 `production_runner_not_implemented` 阻断、缺 summary evidence、CLI 写证据、相对路径解析。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasem/20260707T020329Z-production-readiness-audit.json` | `status=blocked`，`ready=2/5`；collect 和 summary ready；Telegram sandbox、scheduler production、worker placement 未 ready；`network_calls=0`。 |

缺口：`production_ack_missing`、`production_runner_not_implemented`、`sandbox_send_ack_missing`、`telegram_bot_token_missing`、`telegram_chat_id_missing`、`worker_placement_not_confirmed`。

边界：没有调用 Telegram Bot API，没有抓取新数据，没有写生产 DB，没有注册 scheduler/cron/systemd，没有创建常驻 worker；密钥只以布尔存在性呈现。

### 6.36 Phase L-real Telegram 本机沙盒自举助手

状态：**已实现可用的本机自举路径；真实 Telegram 沙盒发送尚未执行。**

新增代码：

- `packages/clawbot/src/intel/telegram_bootstrap.py`
  - `getMe` 验证 bot、`getUpdates` 发现用户发送 `/start intel_brief_sandbox` 后的 chat id、渲染真实 summary evidence 并调用 Telegram sender。
  - evidence 永不写 token、chat id、Bot numeric id 或真实 Bot API URL。
- `packages/clawbot/scripts/intel_telegram_local_bootstrap.py`
  - 支持 `--prompt-token` 隐藏输入 token、`--open-telegram` 打开本机 Telegram deep link、`--wait-seconds` 轮询 `/start`。
- `packages/clawbot/tests/test_intel_telegram_bootstrap.py`
  - 覆盖 chat candidate 选择、缺 ack 阻断、注入 transport 成功发送、轮询等待 `/start`、CLI blocked evidence。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasel/20260707T021607Z-telegram-local-bootstrap-gate-blocked.json` | 当前 token 未安全注入运行时、ack 缺失、未允许真实网络；`status=blocked`，`network_calls=0`。 |

边界：用户已提供 bot 公开用户名和 token 材料，但我没有把 token 写入任何文件、没有在报告中回显、没有调用真实 Bot API；仍缺 chat id 或 `/start` 更新证据。真实发送前必须通过隐藏 prompt/env 注入 token，并设置 `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK=I_UNDERSTAND_TELEGRAM_SANDBOX_SEND`。


### 6.37 本轮最终验证记录（Phase M + Telegram local bootstrap）

证据路径：`packages/clawbot/data/intel_evidence/phasem/20260707T022907Z-production-readiness-bootstrap-verification.json`

验证结果：

- Phase M readiness evidence 与 Telegram local bootstrap blocked evidence：JSON 可解析。
- `ruff`：production readiness、Telegram delivery、Telegram local bootstrap 相关源码/CLI/测试通过。
- pytest：`tests/test_intel_production_readiness.py`、`tests/test_intel_telegram_delivery.py`、`tests/test_intel_telegram_bootstrap.py`、Intel Brief/LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- token 泄漏检查：本轮相关代码、文档和 evidence 未发现用户提供的真实 token 片段或 bot numeric id。

本轮边界：真实 Telegram Bot API 仍未调用成功；未写真实 token/chat id；未启用 production scheduler/cron/systemd；未创建常驻 worker；未写生产 DB。下一步需要用户先在本机 Telegram 给 `@carven_Jianbao_bot` 发送 `/start intel_brief_sandbox`，再通过隐藏 prompt/env 注入 token 与 sandbox ack，执行真实 sandbox send。


### 6.38 Phase N Production runner 合同闭合

状态：**生产 runner 技术阻断已移除；真实生产仍被外部门槛阻断。**

代码变更：

- `packages/clawbot/src/execution/intel_brief.py`
  - Production gate 新增 `INTEL_BRIEF_SUMMARY_EVIDENCE` 校验和 `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK` 校验。
  - 不再无条件追加 `production_runner_not_implemented`。
- `packages/clawbot/src/execution/scheduler.py`
  - `ExecutionScheduler._run_intel_brief()` 新增 production branch：gate ready 后调用注入的 `intel_brief_production_runner`，默认使用 `build_telegram_summary_delivery_probe(..., allow_real_network=True)`。
- `packages/clawbot/tests/test_intel_scheduler_gate.py` / `tests/test_intel_production_readiness.py`
  - 覆盖 production gate ready、缺 summary、缺 sandbox ack、注入 production runner、readiness all-gates-ready 等场景。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasem/20260707T024108Z-production-readiness-runner-contract-audit.json` | `status=blocked`，`ready=2/5`，缺 `telegram_bot_token_missing` / `telegram_chat_id_missing` / `sandbox_send_ack_missing` / `worker_placement_not_confirmed` / `production_ack_missing`；不再含 `production_runner_not_implemented`；`network_calls=0`。 |

边界：这不是生产启用；没有真实 Telegram Bot API 调用，没有 token/chat id 落盘，没有 scheduler/cron/systemd 注册，没有常驻 worker，没有生产 DB 写入。


### 6.39 本轮最终验证记录（Phase N production runner 合同）

证据路径：`packages/clawbot/data/intel_evidence/phasem/20260707T024229Z-production-runner-contract-verification.json`

验证结果：

- 新 readiness evidence：JSON 可解析，且缺口不再包含 `production_runner_not_implemented`。
- `ruff`：scheduler gate、ExecutionScheduler production branch、readiness、Telegram delivery/bootstrap 相关代码/CLI/测试通过。
- pytest：Intel Brief/LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- token 泄漏检查：本轮相关文件未发现用户提供的真实 token 片段或 bot numeric id。

边界：真实 Telegram Bot API 仍未成功调用；真实 chat id 未验证；production scheduler/cron/systemd 未启用；常驻 worker 未创建；生产 DB 未写入。


### 6.40 Phase O 真实 Telegram sandbox + SGW preferred worker

状态：**真实 Telegram sandbox 已成功；SGW preferred overseas worker 已成功；readiness 提升到 3/5。**

代码变更：

- `packages/clawbot/scripts/intel_worker_remote_run.py`
  - 无 pip 依赖时不再强制 `python3 -m venv`，直接使用系统 Python 执行临时 worker bundle，解决 SGW 缺 `ensurepip/python3.12-venv` 时的非必要失败。
- `packages/clawbot/scripts/intel_collect_once.py`
  - `senate_trading` 默认 profile 改为 `ssh_target=oracle-sg-west`、`worker_label=oracle-sg-west-preferred-overseas`。
- `packages/clawbot/tests/test_intel_worker_remote_runner.py` / `tests/test_intel_collect_once.py`
  - 覆盖无依赖 system-python remote runner 和 SGW preferred profile。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasel/20260707T024537Z-telegram-local-bootstrap-real-sandbox.json` | 真实 Bot API sandbox delivery 成功；`getMe/getUpdates/sendMessage`，`network_calls=3`，chat candidate private 且匹配 `/start intel_brief_sandbox`；token/chat id 脱敏。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T024457Z-sgw-ssh-python-smoke.json` | SGW SSH/Python smoke 成功，hostname=`sgw-a1`，python=`3.12.3`。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T024555Z-sgw-senate-worker-remote-run.json` | 首次 SGW worker 失败，原因为 venv/ensurepip 不可用；cleanup 成功，`remote_stage_absent`。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T024852Z-sgw-senate-worker-remote-run-system-python.json` | 修复 runner 后 SGW `senate_trading` 成功，raw_count=2，cleanup 成功，`remote_stage_absent`。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T025103Z-collect-once-sgw-senate-yanhuoyun-akshare.json` | SGW Senate + Yanhuoyun AKShare collect-once 成功，`success=2/failed=0`。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T025315Z-scheduled-sgw-sandbox.json` | 使用 SGW collect evidence 完成 scheduled sandbox；fake Telegram delivery 成功。 |
| `packages/clawbot/data/intel_evidence/phasen/20260707T025328Z-production-readiness-sgw-placement-confirmed.json` | readiness `ready=3/5`；剩余缺口为 token/chat/sandbox ack/production ack。 |

边界：没有把 token/chat id 写入文件或报告；没有创建常驻 worker；没有启用 production scheduler/cron/systemd；没有写生产 DB；没有更改 VPS 防火墙/DNS/Cloudflare/OCI 配置。


### 6.41 本轮最终验证记录（Phase O Telegram + SGW）

证据路径：`packages/clawbot/data/intel_evidence/phasen/20260707T025535Z-phase-o-telegram-sgw-verification.json`

验证结果：

- 真实 Telegram sandbox：success，Bot API `network_calls=3`。
- SGW preferred worker：SSH/Python smoke 成功；首次 venv 失败清理成功；system-python runner 成功抓取 Senate 数据并清理。
- Collect/scheduled：SGW Senate + Yanhuoyun AKShare collect-once `success=2/failed=0`；基于该输入的 scheduled sandbox 成功。
- Readiness：worker placement confirmed 后 `ready=3/5`，剩余 token/chat/sandbox ack/production ack。
- `ruff`、Intel Brief/LLM routing 相关 pytest、OpenEverything/VPS-Config diff check、真实 token 片段扫描均通过。

边界：未启用 production scheduler/cron/systemd；未创建常驻 worker；未把 token/chat id 持久写入 env/文件；未写生产 DB。


### 6.42 Phase P 私有 env 与 launch package dry-run

状态：**私有 env/launch package 机制已完成；真实私有 env 尚未写入，因为剪贴板没有可识别 token。**

代码变更：

- `packages/clawbot/src/intel/private_env.py` / `scripts/intel_private_env.py`
  - 写入 `.openclaw/intel-brief.production.env`，权限 0600；证据只记录 key presence。
- `packages/clawbot/src/intel/launch_package.py` / `scripts/intel_launch_package.py`
  - 生成 launchd dry-run package，`production_action=none`，不安装、不加载。
- `packages/clawbot/src/execution/intel_brief.py`
  - scheduler gate 支持 `INTEL_BRIEF_PRIVATE_ENV`，从私有 env 合并 token/chat/ack/worker placement 后再脱敏判断。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasep/20260707T030509Z-private-env-audit-redacted.json` | 私有 env audit blocked；缺 token/chat/ack/worker placement。 |
| `packages/clawbot/data/intel_evidence/phasep/20260707T030509Z-launchd-dry-run-package.json` | launchd package generated；`production_action=none`、`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasep/20260707T030727Z-readiness-private-env-path-blocked.json` | gate 已接受 private env path，但文件未就绪；readiness `ready=3/5`。 |

边界：未写真实 token/chat id；未安装 launchd plist；未启用 scheduler/cron/systemd；production ack 未写入任何文件。


### 6.43 本轮最终验证记录（Phase P private env / launch package）

证据路径：`packages/clawbot/data/intel_evidence/phasep/20260707T030858Z-phase-p-private-env-launch-verification.json`

验证结果：private env audit blocked 且脱敏；launch package `production_action=none`；readiness private env path `ready=3/5`；ruff/pytest/diff check/token 片段扫描均通过。

边界：真实 token/chat id 未写入私有 env；production ack 未写入；launchd plist 未安装/加载；没有生产 scheduler 或自然日演练。


### 6.44 Phase Q Production-once 入口与 launch package 升级

状态：**一次性 production runner 已实现；当前被 gate 阻断且不联网。**

代码变更：

- `packages/clawbot/src/intel/production_once.py` / `scripts/intel_production_once.py`
  - 统一入口：评估 production gate → gate ready 才调用 Telegram summary delivery → 写 evidence。
- `packages/clawbot/src/intel/launch_package.py` / `scripts/intel_launch_package.py`
  - launchd dry-run plist 改为调用 `intel_production_once.py`，带 summary evidence 与 run evidence 路径。
- `packages/clawbot/tests/test_intel_production_once.py` / `tests/test_intel_launch_package.py`
  - 覆盖缺 gate 不联网、注入 runner 成功、CLI blocked、launch plist 指向 production_once。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-production-once-private-env-blocked.json` | `status=blocked`，缺 token/chat/ack/worker placement/production ack，`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-launchd-production-once-dry-run-package.json` | launch package generated，指向 production_once，`production_action=none`。 |

边界：未安装/加载 launchd；未写 production ack；未联网发送 Telegram；未创建常驻 worker。

### 6.45 Phase R 私有 env ready、production-once 修复与真实 Telegram 投递

状态：**Telegram Bot API 真实 production-once 投递已成功；生产 scheduler 仍未启用。**

代码变更：

- `packages/clawbot/src/intel/production_once.py`
  - 修复 production-once runner：在调用真实 delivery runner 前合并 `INTEL_BRIEF_PRIVATE_ENV`，避免 gate 已 ready 但 Telegram sender 收不到 token/chat 的问题。
- `packages/clawbot/tests/test_intel_production_once.py`
  - 新增回归测试 `test_production_once_loads_private_env_for_real_delivery_runner`，先复现再修复该问题。
- `packages/clawbot/src/intel/production_readiness.py`
  - 此前已修复所有 readiness gate 统一合并 private env，避免误报 token/chat 缺失。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseq/20260707T031755Z-private-env-write-ready-redacted.json` | 私有 env 写入 ready；权限 `0600`；必要键 presence 全部为 true；不含明文密钥。 |
| `packages/clawbot/data/intel_evidence/phaseq/20260707T031828Z-private-env-audit-ready-redacted.json` | 私有 env audit ready；不输出 env 值。 |
| `packages/clawbot/data/intel_evidence/phaseq/20260707T032005Z-readiness-private-env-ready-only-production-ack-missing.json` | readiness `ready=4/5`；仅剩 `production_ack_missing`。 |
| `packages/clawbot/data/intel_evidence/phaseq/20260707T032020Z-production-once-private-env-ready-ack-missing.json` | 不带 production ack 时 production-once blocked，`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phaser/20260707T032745Z-readiness-temporary-ack-ready.json` | 临时 ack 下 readiness `ready=5/5`，`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phaser/20260707T032645Z-production-once-real-delivery.json` | production gate `production_ready`；真实 Telegram `sendMessage` 成功，`network_calls=1`，message_id 存在且脱敏。 |

边界：production ack 未持久写入；未安装/加载 launchd；未注册 cron/systemd；未创建常驻 worker；未完成自然日生产运行观察；未写生产 DB；未输出 token/chat id 明文。

### 6.46 本轮最终验证记录（Phase R production-once）

证据路径：`packages/clawbot/data/intel_evidence/phaser/20260707T033355Z-phase-r-production-once-final-verification.json`

验证结果：

- Phase Q/R evidence JSON 均可解析。
- `.openclaw/intel-brief.production.env` 经 `git check-ignore` 确认被忽略；`.gitignore` 已补 `.openclaw/*.env`。
- `ruff`：private env、launch package、production-once、readiness、scheduler gate 相关文件通过。
- pytest：Intel Brief / LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- 真实 token 片段扫描：变更文件 0 命中（不扫描/不输出私有 env 内容）。

边界：一次性 production-once 已真实发送；production scheduler/launchd 尚未安装或加载；自然日生产运行尚未观察完成。

### 6.47 Phase S fresh production cycle 与 launchd package 升级

状态：**fresh one-shot production cycle 已真实闭合；production scheduler 尚未安装/加载。**

代码变更：

- `packages/clawbot/src/intel/production_cycle.py` / `packages/clawbot/scripts/intel_production_cycle.py`
  - 新增 production cycle：production preflight → fresh collect-once → brief dry-run → LLM summary fallback/real → gated production-once Telegram delivery。
  - 无 production ack 时在远程采集前阻断，`network_calls=0`。
- `packages/clawbot/src/intel/launch_package.py` / `scripts/intel_launch_package.py`
  - launchd dry-run plist 改为调用 `intel_production_cycle.py`，不再固定 `--summary-evidence`，避免未来调度重复发送旧摘要。
- `packages/clawbot/tests/test_intel_production_cycle.py` / `tests/test_intel_launch_package.py`
  - 覆盖无 ack 不采集、fresh cycle 注入 runner、CLI blocked、launch package 不要求固定 summary。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phases/20260707T034607Z-launchd-production-cycle-dry-run-package.json` | launch package generated，plist 指向 `intel_production_cycle.py`，`production_action=none`，未 install/load。 |
| `packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-real-delivery.json` | fresh cycle `status=success`；preflight `production_ready`；collect `success=2/failed=0`；Telegram `network_calls=1`。 |
| `packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-artifacts/20260707T034621Z-collect-once.json` | SGW Senate + 炎火云 AKShare 新采集成功，两个 child run 均 `remote_stage_absent`。 |
| `packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-artifacts/20260707T034621Z-llm-summary-dry-run.json` | fallback-only summary，`llm_attempted=false`，未调用外部 LLM。 |
| `packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-artifacts/20260707T034621Z-production-once-delivery.json` | Telegram Bot API `sendMessage` 成功，endpoint/token/chat 脱敏，message_id 存在。 |

边界：production ack 仍为临时命令环境变量；未安装或加载 launchd；未注册 cron/systemd；未创建常驻 worker；未完成自然日定时观察；未输出 token/chat id 明文。

### 6.48 本轮最终验证记录（Phase S fresh production cycle）

证据路径：`packages/clawbot/data/intel_evidence/phases/20260707T035130Z-phase-s-production-cycle-final-verification.json`

验证结果：

- Phase S launch/cycle/artifacts evidence JSON 均可解析。
- `ruff`：private env、launch package、production-once、production-cycle、readiness、scheduler gate 相关文件通过。
- pytest：Intel Brief / LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- `.openclaw/intel-brief.production.env` 仍被 gitignore 覆盖。
- 真实 token 片段扫描：变更文件 0 命中（不扫描/不输出私有 env 内容）。

边界：fresh one-shot production cycle 已真实发送；production scheduler/launchd 尚未安装或加载；自然日生产运行尚未观察完成。

### 6.49 Phase T LaunchAgent 安装/加载

状态：**本机 LaunchAgent 已安装并加载；未 kickstart；自然日自动运行仍待观察。**

代码变更：

- `packages/clawbot/src/intel/launch_package.py` / `scripts/intel_launch_package.py`
  - 支持 `--include-production-ack`，用于真实定时任务环境。
  - plist 增加 stdout/stderr log path。
  - 相对 output/env 路径按 project_root 解析为绝对路径，避免 launchd 执行时路径漂移。
- `packages/clawbot/tests/test_intel_launch_package.py`
  - 覆盖 production ack/log path、CLI 不要求固定 summary、绝对路径解析。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaset/20260707T035646Z-launchd-production-cycle-install-package.json` | 首个带 ack package 生成；随后发现相对路径可观测性问题。 |
| `packages/clawbot/data/intel_evidence/phaset/20260707T035735Z-launchd-production-cycle-install-load.json` | 首次安装/加载成功，未 kickstart，`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute.json` | 绝对路径 package 生成，production ack embedded，plist 指向 `intel_production_cycle.py`。 |
| `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-reinstall-load-absolute.json` | 重新安装/加载成功，`launchctl print` 有 label，uses_absolute_run_paths=true，`network_calls=0`。 |

边界：没有执行 `launchctl kickstart`；安装/加载步骤没有 Telegram 网络调用；下一次自动运行尚未观察；如需回滚，按 evidence 中 rollback 命令 bootout 并删除 plist。

### 6.50 本轮最终验证记录（Phase T LaunchAgent）

证据路径：`packages/clawbot/data/intel_evidence/phaset/20260707T041245Z-phase-t-launchagent-final-verification.json`

验证结果：

- Phase S/T evidence JSON 均可解析。
- `launchctl print gui/$(id -u)/ai.openclaw.intel-brief.scheduler` 状态审计为 loaded，目标程序为 `intel_production_cycle.py`，使用绝对 runs/logs 路径。
- `ruff`：private env、launch package、production-once、production-cycle、readiness、scheduler gate 相关文件通过。
- pytest：Intel Brief / LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- `.openclaw/intel-brief.production.env` 仍被 gitignore 覆盖。
- 真实 token 片段扫描：变更文件 0 命中。

边界：LaunchAgent 已加载，但未 kickstart；下一次 calendar-triggered 生产运行仍待观察。

### 6.51 Phase U LaunchAgent post-run 审计工具

状态：**post-run 审计工具已就绪；当前真实状态为 pending_calendar_trigger。**

代码变更：

- `packages/clawbot/src/intel/launchagent_audit.py`
  - 读取 launchctl 状态文本、run evidence 和 stdout/stderr，判断 LaunchAgent 是否完成自然触发生产运行。
- `packages/clawbot/scripts/intel_launchagent_audit.py`
  - CLI 输出审计 evidence；`verified_success` 返回 0，其余状态返回 2。
- `packages/clawbot/tests/test_intel_launchagent_audit.py`
  - 覆盖未触发、成功触发和 CLI 写 evidence。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseu/20260707T041950Z-launchagent-post-run-audit-pending.json` | `status=pending_calendar_trigger`；`runs=0`；`last_exit_code=(never exited)`；run evidence 不存在；`network_calls=0`。 |

边界：本节没有 kickstart，没有 Telegram 发送，没有远程采集；只是为下一次自然日运行提供可重复验收入口。

### 6.52 本轮最终验证记录（Phase U LaunchAgent audit）

证据路径：`packages/clawbot/data/intel_evidence/phaseu/20260707T042640Z-phase-u-launchagent-audit-final-verification.json`

验证结果：

- Phase U/T evidence JSON 均可解析。
- `ruff`：launchagent audit、launch package、production-cycle 相关文件通过。
- pytest：Intel Brief / LLM routing 相关测试通过。
- diff check：OpenEverything 与 VPS-Config 均通过。
- `.openclaw/intel-brief.production.env` 仍被 gitignore 覆盖。
- 真实 token 片段扫描：变更文件 0 命中。

边界：当前状态是 `pending_calendar_trigger`，自然日自动运行仍未完成；下一次 08:30 后需要重新运行 audit CLI。

### 6.53 Telegram Bot API 状态复核（无需接管本机 Telegram）

状态：**已解决并复核通过。**

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123333Z-telegram-private-env-audit.json` | 私有 env 存在且 mode=`0600`；Bot Token、chat id、sandbox ack、worker placement 均为存在态；证据不含明文密钥。 |
| `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123350Z-telegram-bot-api-real-send-probe.json` | 真实调用 Telegram Bot API `sendMessage` 成功；`network_calls=1`；message_id 存在；endpoint/token/chat id 均已脱敏。 |
| `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123424Z-telegram-bot-api-getme-probe.json` | 真实调用 Telegram Bot API `getMe` 成功；返回 bot username=`carven_Jianbao_bot`；bot id 仅记录存在性。 |

结论：当前不是 Bot API 卡点，不需要再接管本机 Telegram 点击 Copy。仍未闭合的是自然日 08:30 LaunchAgent 生产调度观察，以及 SGW 间歇 SSH timeout 的容错处理。

边界：本次复核只验证 Telegram Bot API、私有 env 和真实发送能力；没有修改 BotFather 设置，没有输出或记录 Token/chat id 明文，没有新增/删除 Telegram bot。

### 6.54 Phase W SGW 超时容错与 LaunchAgent canary 验证

状态：**已完成代码容错、真实 fallback 验证、真实日历触发 canary 验证；自然日 08:30 正式 LaunchAgent 仍待下一次到点观察。**

代码变更：

- `packages/clawbot/scripts/intel_collect_once.py`
  - `senate_trading` 默认仍优先走 `oracle-sg-west` / `oracle-sg-west-preferred-overseas`。
  - 新增 `oracle-arm1` / `oracle-arm1-overseas-fallback` 作为 Senate 海外 fallback。
  - SGW SSH 增加 `BatchMode=yes` 与 `ConnectTimeout=12`，避免单次管理路径异常拖垮整个生产周期。
  - collect evidence 新增 `attempts[]` 与 `fallback` 字段，明确 primary/fallback 每次尝试、worker、return code、stderr 摘要、cleanup 状态。
- `packages/clawbot/scripts/intel_worker_remote_run.py`
  - 初始 SSH staging/mkdir 失败时 fail-fast，写入失败 evidence 后返回，不再继续执行 worker/health/cleanup/verify 等多次 SSH 超时动作。
- `packages/clawbot/tests/test_intel_collect_once.py`
  - 覆盖 SGW primary failed 后自动切到 oracle-arm1 fallback，且 collect summary 仍为成功。
- `packages/clawbot/tests/test_intel_worker_remote_runner.py`
  - 覆盖初始 SSH staging 失败时 fail-fast，不重复触发后续 SSH 命令。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasev/20260707T122900Z-launchd-calendar-canary-due-failure-rollback.json` | 上一轮 canary 真实触发但 SGW SSH `Operation timed out`；临时 canary 已移除，SGW cleanup 尝试记录。 |
| `packages/clawbot/data/intel_evidence/phasew/20260707T124408Z-forced-senate-fallback/collect-once.json` | 受控强制 primary SSH 失败后，`senate_trading` 自动切到 `oracle-arm1-overseas-fallback` 并真实抓取成功；fallback child cleanup=`remote_stage_absent`。 |
| `packages/clawbot/data/intel_evidence/phasew/20260707T124152Z-production-cycle-with-sgw-fallback/latest-production-cycle.json` | 真实 one-shot fresh production cycle 成功；本次 SGW primary 恢复可用，fallback 未触发；Yanhuoyun AKShare 成功；Telegram `sendMessage` 成功。 |
| `packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/post-run-audit.json` | 临时 canary LaunchAgent 日历触发完成；audit=`verified_success`，`launchctl.runs=1`，`last_exit_code=0`，run evidence `status=success`，Telegram message_id 存在。 |
| `packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/rollback-evidence.json` | 临时 canary 已 bootout 并删除 plist；正式 daily LaunchAgent 未被卸载。 |

验证命令：

- `packages/clawbot/.venv312/bin/python -m ruff check scripts/intel_worker_remote_run.py scripts/intel_collect_once.py tests/test_intel_worker_remote_runner.py tests/test_intel_collect_once.py`
- `packages/clawbot/.venv312/bin/python -m pytest tests/test_intel_worker_remote_runner.py tests/test_intel_collect_once.py tests/test_intel_production_cycle.py -q`
- Phase W evidence `python3 -m json.tool` 校验通过。
- canary rollback 后检查：`ai.openclaw.intel-brief.scheduler-canary` 不存在，`~/Library/LaunchAgents/ai.openclaw.intel-brief.scheduler-canary.plist` 不存在；正式 `ai.openclaw.intel-brief.scheduler` 仍 loaded 且 `runs=0`。

边界：

- `20260707T124408Z-forced-senate-fallback` 是受控强制 primary 失败，用来证明 fallback 代码路径与 oracle-arm1 真实 worker 可用；不是说当时 SGW 生产端口一定故障。
- `20260707T125003Z-launchd-calendar-canary-verified` 证明 macOS LaunchAgent 的 calendar trigger + fresh collect + Telegram delivery 能闭合；它是临时 canary，不等同于正式 daily label 的自然日 08:30 已经跑过。
- 仍未创建 VPS 常驻 worker/systemd/cron；远端仍是 `/tmp` 临时 staging，执行后 cleanup。
- 证据不包含 Telegram Token/chat id 明文。

### 6.55 Phase W 最终验证记录

证据路径：`packages/clawbot/data/intel_evidence/phasew/20260707T125656Z-phase-w-final-verification.json`

验证结果：

- Phase V/W 关键 evidence JSON 均可解析。
- `ruff`：remote runner、collect once、production cycle、LaunchAgent audit 相关文件通过。
- `pytest`：`test_intel_worker_remote_runner.py`、`test_intel_collect_once.py`、`test_intel_production_cycle.py`、`test_intel_launchagent_audit.py` 共 15 项通过。
- `git diff --check`：OpenEverything 与 VPS-Config 均通过。
- Token 片段扫描：本轮变更代码/文档/evidence 0 命中。
- 临时 canary 已移除；正式 daily LaunchAgent 仍 loaded，且 `runs=0`，等待自然日 08:30。

边界：最终验证本身没有再次调用 Telegram 或远程 worker；完整目标仍不能标记完成，因为正式 daily LaunchAgent 的自然日 08:30 运行尚未发生。

### 6.56 Phase X 正式 daily LaunchAgent 预触发审计

状态：**正式 daily LaunchAgent 已加载，但当前尚未到本地 08:30 触发时间；保持等待自然触发，不用 canary 代替正式验收。**

真实审计时间：本地 `2026-07-07T06:58:45-0600 MDT` / UTC `2026-07-07T12:58:45Z`。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasex/20260707T125904Z-daily-launchagent-pre-trigger-pending-audit.json` | `status=pending_calendar_trigger`；正式 label `ai.openclaw.intel-brief.scheduler` 已加载，目标为 `intel_production_cycle.py`；`runs=0`；`last_exit_code=(never exited)`；run evidence 尚不存在；`network_calls=0`。 |

操作记录：已创建一次性线程 heartbeat，在本地 08:40 左右回到当前线程执行正式 daily 08:30 后审计。该 heartbeat 只负责恢复审计工作，不会替代 launchd 触发，也不会读取或输出 Telegram Token/chat id。

边界：本节只读审计，没有 kickstart，没有 Telegram 调用，没有远程采集，没有修改正式 LaunchAgent；正式 daily 自然触发仍待观察。

### 6.57 Phase X 预触发等待阶段最终验证

证据路径：`packages/clawbot/data/intel_evidence/phasex/20260707T130040Z-phase-x-pretrigger-final-verification.json`

验证结果：

- pending audit evidence JSON 可解析。
- heartbeat creation evidence JSON 可解析：`packages/clawbot/data/intel_evidence/phasex/20260707T130014Z-daily-audit-heartbeat-created.json`。
- OpenEverything 与 VPS-Config `git diff --check` 通过。
- Token 片段扫描 0 命中。
- 正式 daily LaunchAgent 仍 loaded，且 `runs=0`，符合 08:30 前状态。

边界：本轮验证只读；没有触发 launchd，没有 Telegram 调用，没有远程 worker 调用。目标保持 active，等待本地 08:40 heartbeat 继续正式 post-run audit。

### 6.58 Phase X 重复预触发审计（仍早于 08:30）

状态：**仍处于等待正式 daily 08:30 自然触发阶段。**

真实审计时间：本地 `2026-07-07T07:02:10-0600 MDT` / UTC `2026-07-07T13:02:10Z`。

证据路径：`packages/clawbot/data/intel_evidence/phasex/20260707T130243Z-daily-launchagent-repeat-pre-trigger-audit.json`

结果：正式 label `ai.openclaw.intel-brief.scheduler` 仍 loaded，目标为 `intel_production_cycle.py`，`runs=0`，`last_exit_code=(never exited)`，run evidence 尚不存在。已复核一次性 heartbeat 配置存在且为 active，计划在 UTC `2026-07-07T14:40:00Z` / 本地 `08:40 MDT` 继续 post-run audit。

边界：本节只读审计；未 kickstart、未 Telegram 调用、未远程采集、未修改 LaunchAgent/VPS。

### 6.59 Phase X 正式 daily LaunchAgent 自然触发闭环

状态：**正式 daily LaunchAgent 自然触发已验证成功。**

真实触发/审计：

- 本地审计时间：`2026-07-07T08:40:50-0600 MDT` / UTC `2026-07-07T14:40:50Z`。
- 正式 label：`ai.openclaw.intel-brief.scheduler`。
- launchd 状态：`runs=1`，`last_exit_code=0`，目标程序为 `intel_production_cycle.py`。
- run evidence 写入时间：`2026-07-07T14:30:05Z`，对应本地 08:30 自然触发。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs/latest-production-cycle.json` | 正式 daily run `status=success`；collect `success=2/failed=0`；SGW `senate_trading` 成功；炎火云 `akshare` 成功；Telegram production delivery `network_calls=1`，`message_id` 存在，token/chat 已脱敏。 |
| `packages/clawbot/data/intel_evidence/phasex/20260707T144102Z-daily-launchagent-post-run-audit.json` | post-run audit `verified_success`；launchctl `runs=1`、`last_exit_code=0`；run evidence OK；Telegram send success。 |
| `packages/clawbot/data/intel_evidence/phasex/20260707T145534Z-heartbeat-cleanup-after-daily-success.json` | 一次性 follow-up heartbeat 已清理；正式 LaunchAgent 未被修改。 |

边界：正式 daily LaunchAgent 仍保留加载状态，供后续每天 08:30 运行；本节未创建 VPS 常驻 worker/systemd/cron，远端仍为 `/tmp` 临时 staging 并 cleanup；未输出 Telegram Token/chat id 明文。

### 6.60 Phase X 最终验证与生产闭环结论

最终验证证据：`packages/clawbot/data/intel_evidence/phasex/20260707T145702Z-daily-launchagent-closure-final-verification.json`

验证结果：

- 关键 evidence JSON 均可解析。
- `ruff`：remote runner、collect once、LaunchAgent audit、production cycle 相关文件通过。
- `pytest`：remote runner、collect once、production cycle、LaunchAgent audit、production once、Telegram delivery 相关 28 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 片段扫描 0 命中。
- launchctl 当前确认 `runs=1`、`last_exit_code=0`。
- 正式 run evidence `status=success`；collect `success=2/failed=0`；Telegram send success；message_id present。
- post-run audit `verified_success`。

当前结论：Intel Brief 从 Phase B 目标节点真实验证到正式 daily 生产闭环已经完成最小闭环：目标节点真实采集、内容生成、Telegram 真实投递、正式 LaunchAgent 08:30 自然触发、post-run audit 与文档基线均已闭合。后续扩展数据源/社媒登录态/常驻 worker 属于下一阶段能力增强，不阻塞当前闭环。

### 7.1 Phase Y 商业订阅 MVP 数据层与 Telegram 菜单合同

状态：**完成第一块商业化 MVP 基础能力：订阅授权、到期判断、分类偏好、推送频率/时间、Telegram 菜单合同。**

代码变更：

- `packages/clawbot/src/intel/db/intel_brief_schema.sql`
  - 新增 `delivery_preferences`：记录用户推送频率、推送时间、时区。
  - 新增 `subscription_audit_log`：记录人工/闲鱼等来源的订阅授权事件，便于后续追溯。
- `packages/clawbot/src/intel/subscriptions.py`
  - 新增商业 MVP 订阅服务：plan upsert、Telegram subscriber upsert、grant subscription、source preferences、delivery preferences、profile 查询、按分类筛选 eligible recipients、Telegram menu contract。
- `packages/clawbot/tests/test_intel_commercial_mvp.py`
  - 覆盖 schema、订阅授权与到期、偏好筛选、Telegram 菜单命令合同。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasey/20260707T152655Z-commercial-mvp-subscription-contract/evidence.json` | sandbox DB 写入 2 个订阅者、1 个套餐、2 条订阅、4 条 enabled preferences、1 条 delivery preference、2 条 subscription audit；到期用户被排除，eligible_count=1；Telegram menu contract 生成；`network_calls=0`。 |

边界：本节只写 sandbox SQLite 和 evidence；没有调用 Telegram Bot API，没有调用支付/闲鱼接口，没有修改正式 daily LaunchAgent，没有触碰生产 `.openclaw` 私有 env。chat id 仅记录存在性，不写明文到 evidence。

### 7.2 Phase Y 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phasey/20260707T153329Z-commercial-mvp-subscription-final-verification.json`

验证结果：

- Phase Y contract evidence JSON 可解析。
- `ruff`：订阅服务、DB store、商业 MVP/Schema/Delivery 相关测试文件通过。
- `pytest`：`test_intel_commercial_mvp.py`、`test_intel_schema_and_tracking.py`、`test_intel_delivery_sandbox.py` 共 14 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 片段扫描 0 命中。
- sandbox evidence `status=success`、eligible_count=1、`network_calls=0`。

边界：商业化订阅 MVP 目标仍未完成；本轮只闭合数据层与 Telegram 菜单合同。下一步需要把真实 Telegram handler 接入这些合同，并让 daily production delivery 从固定 chat 转为按订阅/偏好筛选用户。

### 7.3 Phase Z Telegram 用户菜单 Handler 合同

状态：**已完成本地 handler contract 与 sandbox evidence；尚未接入真实 Telegram SDK long-polling/webhook。**

代码变更：

- `packages/clawbot/src/intel/telegram_menu.py`
  - 新增 `TelegramUserContext` 与 `handle_intel_telegram_command()`。
  - 支持 `/start`、`/status`、`/sources`、`/schedule`、`/custom`、`/help`。
  - 只返回 reply contract，不调用 Telegram Bot API。
  - `/custom` 只写入 `tracking_targets` / `tracking_subscriptions` / `tracking_audit_log`，不触发社媒抓取，避免用户输入立即放大为高频盯梢。
- `packages/clawbot/scripts/intel_telegram_menu_sandbox.py`
  - 用 sandbox SQLite 演练 `/start → 人工授权 → /sources → /schedule → /custom → /status`。
  - evidence 中 chat id 仅记录存在性，不写明文。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`
  - 覆盖 start 创建 subscriber、active subscription 状态、分类偏好、推送计划、自定义人物追踪 audit、sandbox evidence builder。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasez/20260707T155448Z-telegram-menu-handler-contract/evidence.json` | sandbox flow `status=success`；步骤为 `start/grant/sources/schedule/custom/status`；final profile `active`；enabled categories=`akshare, senate_trading`；delivery=`daily 08:30 America/Denver`；tracking target=`周杰伦`，active_subscription_count=1；`network_calls=0`。 |

边界：本节没有调用 Telegram Bot API、没有注册真实 bot handler/setMyCommands、没有触发社媒抓取、没有调用支付/闲鱼接口、没有修改正式 `intel_brief.db`、没有修改正式 daily LaunchAgent。rollback 边界为删除本节新增的 handler/测试/脚本与 sandbox evidence：`packages/clawbot/src/intel/telegram_menu.py`、`packages/clawbot/tests/test_intel_telegram_menu_handlers.py`、`packages/clawbot/scripts/intel_telegram_menu_sandbox.py`、`packages/clawbot/data/intel_evidence/phasez/20260707T155448Z-telegram-menu-handler-contract/`。

### 7.4 Phase Z 当前未完成边界

商业化订阅 MVP 闭环仍未完成，剩余硬门槛：

- 将 handler contract 接入真实 `intel_brief_bot` Telegram runtime（long polling 或 webhook），并设置 bot commands。
- 真实 Telegram 用户执行 `/start`、配置 `/sources`、`/schedule`、`/custom` 后，生产 DB 能保存对应偏好。
- daily production delivery 从固定 chat 迁移为按 `eligible_subscribers_for_categories()` 和用户偏好筛选。
- 至少一次真实端到端：订阅授权 → 用户配置 → 到点收到按偏好生成的每日简报。

### 7.5 Phase Z 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phasez/20260707T155805Z-telegram-menu-handler-final-verification.json`

验证结果：

- Phase Z sandbox evidence JSON 可解析，`status=success`，`network_calls=0`。
- `ruff`：`telegram_menu.py`、sandbox 脚本、Telegram handler 测试、订阅相关文件通过。
- `pytest`：`test_intel_telegram_menu_handlers.py`、`test_intel_commercial_mvp.py`、`test_intel_schema_and_tracking.py` 共 12 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Telegram token 形态扫描通过，未在本轮变更文件/evidence/docs 中发现 token 形态泄漏。

边界：该验证未调用 Telegram Bot API、支付/闲鱼、社媒抓取、远程 worker 或 LLM；商业订阅 MVP 闭环仍未完成，下一步必须接入真实 `intel_brief_bot` runtime，并让 production delivery 按订阅/偏好筛选。

### 7.6 Phase AA Telegram Runtime Adapter 沙盒闭环

状态：**已完成 Telegram update → Intel handler → reply sender 的运行适配层；仍未启动真实 Telegram long-polling/webhook。**

代码变更：

- `packages/clawbot/src/intel/telegram_runtime.py`
  - 新增 `parse_telegram_command_update()`：从 Telegram update 中解析 command、args、user context。
  - 新增 `process_intel_telegram_updates()`：把 Telegram update 批量送入 Phase Z handler，并调用注入式 reply sender。
  - 返回 redacted runtime evidence，不包含 raw chat id 或 token。
- `packages/clawbot/scripts/intel_telegram_runtime_sandbox.py`
  - 使用 fake sender 和 sandbox SQLite 演练真实 Telegram update 形状：`/start`、人工授权、`/sources`、`/schedule`、`/custom`、`/status`。
- `packages/clawbot/tests/test_intel_telegram_runtime.py`
  - 覆盖 update 解析、reply sender 注入、chat id 脱敏、active 用户配置、sandbox evidence builder。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaa/20260707T160334Z-telegram-runtime-adapter-sandbox/evidence.json` | `status=success`；Telegram-shaped updates `seen=5/handled=5`；reply `send_success=5`；final profile `active`；enabled categories=`akshare, senate_trading`；delivery=`daily 08:30 America/Denver`；tracking target=`周杰伦`；`network_calls=0`。 |

边界：本节没有调用 Telegram Bot API，没有启动 long-polling/webhook，没有设置真实 bot commands，没有修改正式 `intel_brief.db`，没有修改正式 daily LaunchAgent，没有触发社媒抓取，没有调用支付/闲鱼。rollback 边界为删除 `telegram_runtime.py`、runtime 测试/脚本与 `phaseaa/20260707T160334Z-telegram-runtime-adapter-sandbox/` evidence。

### 7.7 Phase AA 当前未完成边界

Telegram 商业 MVP 仍缺：

- 用真实 `TelegramBotApiSender` 或专用 Bot API client 接入 `getUpdates`/webhook 与 `sendMessage`。
- 为 `intel_brief_bot` 设置真实 commands，并产出 Bot API `setMyCommands` 证据。
- 将真实用户命令写入正式 `packages/clawbot/data/intel_brief.db`。
- production delivery 按订阅状态、到期时间、分类偏好和推送时间筛选收件人。

### 7.8 Phase AA 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseaa/20260707T160655Z-telegram-runtime-adapter-final-verification.json`

验证结果：

- Phase AA sandbox evidence JSON 可解析，`status=success`，`network_calls=0`。
- `ruff`：runtime adapter、runtime sandbox、Phase Z handler/脚本/测试通过。
- `pytest`：`test_intel_telegram_runtime.py`、`test_intel_telegram_menu_handlers.py`、`test_intel_commercial_mvp.py`、`test_intel_schema_and_tracking.py` 共 15 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Telegram token 形态扫描通过，Phase AA evidence 未写 raw chat id。

边界：该验证未调用 Telegram Bot API、支付/闲鱼、社媒抓取、远程 worker 或 LLM；商业订阅 MVP 闭环仍未完成，下一步必须接入真实 `intel_brief_bot` Bot API runtime，并让 production delivery 按订阅/偏好筛选。

### 7.9 Phase AB Telegram Bot API Runtime Gate 与命令注册

状态：**已完成真实 Bot API `setMyCommands` / `getUpdates` 低风险 probe；尚未把真实 updates 写入生产 DB 或自动回复。**

代码变更：

- `packages/clawbot/src/intel/telegram_bot_runtime.py`
  - 新增 `build_bot_runtime_gate()`：检查 Bot token 存在、runtime ack 存在、是否显式允许 real network。
  - 新增 `TelegramBotApiRuntimeClient`：支持 `setMyCommands` 与 `getUpdates`，transport 可注入，返回值脱敏。
  - 新增 `build_telegram_bot_runtime_probe()`：写入 redacted evidence；不持久化 raw updates、chat id、user id 或消息文本。
- `packages/clawbot/scripts/intel_telegram_bot_runtime_probe.py`
  - 从 `.openclaw/intel-brief.production.env` 读取私有 env，执行受控 runtime probe。
- `packages/clawbot/tests/test_intel_telegram_bot_runtime.py`
  - 覆盖 gate blocked、命令注册 payload、getUpdates 脱敏、probe evidence、CLI blocked。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseab/20260707T161200Z-telegram-bot-runtime-injected-contract/evidence.json` | 注入式 transport 合同验证；`setMyCommands` success；`getUpdates` success；`network_calls=2`；raw updates 未持久化。 |
| `packages/clawbot/data/intel_evidence/phaseab/20260707T161129Z-telegram-bot-runtime-real-probe.json` | 真实 Telegram Bot API 调用成功；gate ready；`setMyCommands.success=true`；`getUpdates.success=true`；真实 `network_calls=2`；读取到 4 条 command updates / 4 条 private chat updates（仅计数，未写 raw chat id/user id/message text）。 |

边界：本节没有调用 `sendMessage`，没有启动 long-polling/webhook，没有写正式 `intel_brief.db`，没有修改 daily LaunchAgent，没有触发社媒抓取，没有调用支付/闲鱼，没有创建 VPS 常驻 runtime。rollback 边界：代码层删除 `telegram_bot_runtime.py`、probe 脚本和测试；Telegram Bot API `setMyCommands` 若需回滚，可后续调用 `deleteMyCommands` 或重新设置旧命令，但本节未自动执行回滚以免破坏已注册的 Intel Brief 菜单。

### 7.10 Phase AB 当前未完成边界

商业 MVP 的 Telegram 层仍缺：

- 从真实 `getUpdates` 拉取后调用 Phase AA runtime adapter 并用真实 `sendMessage` 回复。
- 为 update offset 建立持久状态，避免重复回复历史 commands。
- 将真实用户 `/start`、`/sources`、`/schedule`、`/custom` 写入正式 `packages/clawbot/data/intel_brief.db`。
- daily production delivery 按订阅/偏好筛选真实用户。

### 7.11 Phase AB 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseab/20260707T161357Z-telegram-bot-runtime-final-verification.json`

验证结果：

- 注入式与真实 Bot API evidence JSON 均可解析，状态均为 `success`。
- 真实 Bot API `setMyCommands` 成功，`getUpdates` 成功；本阶段真实 `network_calls=2`。
- `ruff`：Bot runtime、runtime adapter、相关脚本/测试通过。
- `pytest`：Bot runtime、runtime adapter、菜单 handler、商业订阅、schema/tracking 共 19 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态与 raw update/chat id 扫描通过；real evidence 未持久化 raw updates。

边界：该验证只调用 `setMyCommands` 与 `getUpdates`，没有调用 `sendMessage`；没有写生产 DB；没有启动 long-polling/webhook；没有调用支付/闲鱼、社媒抓取、远程 worker 或 LLM。下一步需要 offset 持久化与真实 update → handler → sendMessage → DB 写入闭环。

### 7.12 Phase AC Telegram Update Offset 与防重复处理沙盒

状态：**已完成 Telegram update offset 持久化与防重复处理；仍未对真实 Telegram updates 自动 `sendMessage`。**

代码变更：

- `packages/clawbot/src/intel/db/intel_brief_schema.sql`
  - 新增 `telegram_runtime_state`：按 bot profile 持久化 `last_update_id`，用于 `getUpdates` offset 和防重复回复。
- `packages/clawbot/src/intel/telegram_update_processor.py`
  - 新增 `get_telegram_offset()` / `set_telegram_offset()`。
  - 新增 `process_telegram_updates_once()`：读取 offset → 调用 Bot API client 的 `getUpdates` → 过滤重复 update → 调用 Phase AA runtime adapter → 全部发送成功后推进 offset。
- `packages/clawbot/scripts/intel_telegram_update_processor_sandbox.py`
  - fake client + fake sender + sandbox SQLite 演练 `/start`、人工授权、配置命令、重复 replay。
- `packages/clawbot/tests/test_intel_telegram_update_processor.py`
  - 覆盖 schema、offset 持久化、重复 update 跳过、active 用户配置、sandbox evidence。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseac/20260707T161820Z-telegram-update-processor-offset-sandbox/evidence.json` | sandbox `status=success`；第一轮 offset `0 → 100`；第二轮 request offset `101`，offset `100 → 103`；重复 replay request offset `104`，`handled_count=0`；final profile `active`，分类 `akshare/senate_trading`，推送 `daily 08:30 America/Denver`，tracking target `周杰伦`；`network_calls=0`。 |

边界：本节只用 fake client/fake sender 和 sandbox DB；没有调用 Telegram Bot API，没有 `sendMessage`，没有写正式 `intel_brief.db`，没有修改 daily LaunchAgent，没有调用支付/闲鱼/社媒抓取/远程 worker。rollback 边界为删除 `telegram_runtime_state` schema 追加、`telegram_update_processor.py`、sandbox 脚本/测试和 `phaseac/20260707T161820Z-telegram-update-processor-offset-sandbox/` evidence。

### 7.13 Phase AC 当前未完成边界

真实 Telegram 自动回复仍缺：

- 明确真实处理 ack：避免把历史 `getUpdates` 中的旧命令批量回复。
- 首次生产运行应先将 offset baseline 设置到当前最新 update，或只处理用户新发命令。
- 使用真实 `TelegramBotApiRuntimeClient` + `TelegramBotApiSender` 连接 `process_telegram_updates_once()`，并写正式 `intel_brief.db`。
- 产出真实用户 `/start` → `/sources` → `/schedule` → `/custom` → `/status` 的 sendMessage evidence。

### 7.14 Phase AC 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseac/20260707T162038Z-telegram-update-processor-final-verification.json`

验证结果：

- Phase AC sandbox evidence JSON 可解析，状态 `success`，`network_calls=0`，final offset `103`，重复 replay `handled_count=0`。
- `ruff`：update processor、sandbox 脚本、runtime/Bot runtime 相关文件通过。
- `pytest`：update processor、Bot runtime、runtime adapter、菜单 handler、商业订阅、schema/tracking 共 23 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态与 raw chat 扫描通过；sandbox evidence 未写 raw chat id。

边界：该验证未调用 Telegram Bot API 或 `sendMessage`；没有写生产 DB；没有启动 long-polling/webhook；没有调用支付/闲鱼、社媒抓取、远程 worker 或 LLM。下一步需要真实处理前的 baseline offset/ack，然后把真实新 updates 送入 processor 并真实回复。

### 7.15 Phase AD Telegram Baseline Offset 安全门

状态：**已完成真实 Bot API `getUpdates` baseline offset 写入；历史 updates 已标记为已读，未自动回复。**

代码变更：

- `packages/clawbot/src/intel/telegram_baseline_offset.py`
  - 新增 `seed_telegram_baseline_offset()`：读取当前可见 updates 的最大 `update_id`，只写 `telegram_runtime_state.last_update_id`，不回复。
  - 新增 `build_telegram_baseline_offset_evidence()`：写入脱敏 evidence，不持久化 raw updates/chat id/user id/message text。
- `packages/clawbot/scripts/intel_telegram_baseline_offset.py`
  - 从 `.openclaw/intel-brief.production.env` 读取私有 env，经 Bot runtime gate 后执行真实 baseline。
- `packages/clawbot/tests/test_intel_telegram_baseline_offset.py`
  - 覆盖 baseline offset 推进、不降低已有 offset、evidence 脱敏、CLI blocked。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasead/20260707T162500Z-telegram-baseline-offset-sandbox/evidence.json` | sandbox baseline：fake `getUpdates` 2 条，baseline `0 → 305`，`reply_sent=false`，`network_calls=0`。 |
| `packages/clawbot/data/intel_evidence/phasead/20260707T162505Z-telegram-baseline-offset-real.json` | 真实 Bot API `getUpdates` 一次成功；读取到 4 条 command/private updates（仅计数）；正式 `packages/clawbot/data/intel_brief.db` 的 `intel_brief_bot` offset 写为 `684746897`；`reply_sent=false`，`raw_updates_persisted=false`，`network_calls=1`。 |

回滚边界：如误设 baseline 且确需重放历史命令，可将 `packages/clawbot/data/intel_brief.db` 中 `telegram_runtime_state` 的 `intel_brief_bot.last_update_id` 恢复为 evidence 记录的 `previous_offset=0`；正常情况下不建议回滚，以免后续自动回复旧命令。

边界：本节只调用真实 `getUpdates`，没有调用 `sendMessage`；没有启动 long-polling/webhook；没有触发社媒抓取、支付/闲鱼、远程 worker 或 LLM；没有修改 daily LaunchAgent。生产 DB 只写入 Telegram offset，不写订阅者或偏好。

### 7.16 Phase AD 当前未完成边界

下一步可以进入受控真实自动回复：

- 用 `TelegramBotApiRuntimeClient` 从 offset `684746898` 起拉取新命令。
- 用 `TelegramBotApiSender` 真实 `sendMessage` 回复。
- 写正式 `intel_brief.db` 的 subscriber/source_preferences/delivery_preferences/tracking audit。
- 产出真实用户新命令的端到端 evidence。

### 7.17 Phase AD 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phasead/20260707T162726Z-telegram-baseline-offset-final-verification.json`

验证结果：

- Phase AD sandbox/real evidence JSON 均可解析，状态 `success`，`reply_sent=false`，`raw_updates_persisted=false`。
- 正式 `packages/clawbot/data/intel_brief.db` 中 `intel_brief_bot.last_update_id=684746897`。
- `ruff`：baseline offset、update processor、相关脚本/测试通过。
- `pytest`：baseline offset、update processor、Bot runtime、runtime adapter、菜单 handler、商业订阅、schema/tracking 共 27 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态与 raw update/chat 扫描通过。

边界：真实验证只调用 `getUpdates`，没有调用 `sendMessage`；生产 DB 写入仅限 `telegram_runtime_state.last_update_id`；商业订阅 MVP 闭环仍未完成，下一步需要处理真实新 update 并回复。

### 7.18 Phase AE 真实 Telegram Update Runner One-shot

状态：**真实 runner 已实现并执行；本次 baseline 后没有新 Telegram 命令，因此未触发 `sendMessage`，不能算真实用户交互闭环完成。**

代码变更：

- `packages/clawbot/src/intel/telegram_real_update_runner.py`
  - 新增 `build_real_update_runner_gate()`：要求 token、runtime ack、`allow_real_network`、`allow_send_message` 四项同时满足。
  - 新增 `run_real_update_processor_once()`：连接真实 Bot API `getUpdates` client 与 `TelegramBotApiSender`，复用 Phase AC offset-safe processor。
  - 新增 `build_real_update_runner_evidence()`：输出脱敏 evidence，不写 raw updates/chat id/user id/message text。
- `packages/clawbot/scripts/intel_telegram_real_update_runner.py`
  - 一次性真实 runner CLI，默认 blocked，必须显式加 `--allow-real-network --allow-send-message`。
- `packages/clawbot/tests/test_intel_telegram_real_update_runner.py`
  - 覆盖 gate、注入式新 update send、无新 update 不发送、evidence blocked、CLI blocked。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseae/20260707T163143Z-telegram-real-update-runner-one-shot.json` | gate ready；请求 offset `684746898`；真实 `getUpdates` 返回 0 条新 update；`status=no_new_updates`；`network_calls=1`；`send_message_attempted=false`；正式 DB offset 保持 `684746897`。 |

边界：本节真实调用只有 `getUpdates`；由于没有新 update，没有调用 `sendMessage`，没有写 subscriber/source_preferences/delivery_preferences/tracking audit。真实用户交互闭环仍未完成。下一步需要用户在 Telegram 发送一个新命令（如 `/start` 或 `/status`），再重跑该 runner 才能获得真实自动回复和 DB 写入证据。

### 7.19 Phase AE 当前未完成边界

- 缺少 baseline 后的新 Telegram 用户命令，因此没有真实 `sendMessage` 回复证据。
- 正式 `intel_brief.db` 尚未通过真实 Telegram command 写入用户偏好。
- daily production delivery 尚未按正式订阅/偏好筛选真实用户。

### 7.20 Phase AE 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseae/20260707T163352Z-telegram-real-update-runner-final-verification.json`

验证结果：

- Phase AE real runner evidence JSON 可解析，状态 `no_new_updates`。
- 正式 DB offset 仍为 `684746897`，请求 offset 为 `684746898`。
- `ruff`：real update runner、baseline/update processor 相关文件通过。
- `pytest`：real runner、baseline、update processor、Bot runtime、runtime adapter、菜单 handler、商业订阅、schema/tracking 共 32 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态与 raw update/chat 扫描通过。

边界：真实 runner 已 ready，但本次没有 baseline 后新 update；因此未 `sendMessage`、未写 subscriber/preferences/tracking audit。商业 MVP 仍需真实用户新命令来完成 Telegram 交互验收。


### 7.21 Phase AF 订阅偏好过滤投递 sandbox

状态：**已完成 sandbox 级别的订阅/到期/偏好过滤投递；尚未接入正式 daily production delivery。**

代码变更：

- `packages/clawbot/src/intel/subscription_delivery.py`
  - 新增 `deliver_summary_to_eligible_subscribers()`：从 summary evidence 提取来源分类，只投递给 active、未过期、Telegram 渠道且 source preference 命中的订阅者。
  - 投递结果写 `delivery_log`，对外 evidence 只保留 `channel_user_id_present`、message id presence、endpoint/network 摘要，不输出 raw chat id。
  - 新增 `build_subscription_delivery_sandbox()`：使用 sandbox SQLite 和 fake sender 生成可审计证据。
- `packages/clawbot/scripts/intel_subscription_delivery_sandbox.py`
  - 本地 sandbox CLI，不调用 Telegram API。
- `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py`
  - 覆盖 active/expired、偏好匹配/排除、delivery_log 写入、evidence 脱敏。

真实/验证证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaf/20260707T164449Z-subscription-filtered-delivery-sandbox/evidence.json` | sandbox `status=success`；summary 来源分类 `akshare/senate_trading`；eligible=2、sent=2、failed=0；排除未命中 `ai_model_updates` 与 expired subscriber；`network_calls=0`；evidence 未写 raw chat id。 |

边界：本节只使用 sandbox DB 与 fake sender；没有调用 Telegram Bot API，没有修改正式 `packages/clawbot/data/intel_brief.db`，没有修改 daily LaunchAgent，没有调用支付/闲鱼/社媒抓取/远程 worker。rollback 边界为删除 `subscription_delivery.py`、sandbox 脚本、测试及 `phaseaf/` evidence。

### 7.22 Phase AF 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseaf/20260707T165346Z-subscription-filtered-delivery-final-verification.json`

验证结果：

- Phase AF sandbox evidence JSON 可解析，状态 `success`，投递摘要 `eligible=2/sent=2/failed=0`，来源分类 `akshare/senate_trading`，`network_calls=0`。
- `ruff`：subscription delivery、sandbox 脚本、测试、subscriptions/delivery 相关文件通过。
- `pytest`：subscription filtered delivery、commercial MVP、delivery sandbox、schema/tracking 共 16 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态扫描通过；sandbox evidence 未写 raw fake chat id。测试文件中保留 fake chat id 字符串用于断言脱敏，不属于生产密钥或真实 chat id。

边界：production daily cycle 仍未切换到订阅/偏好过滤投递；真实 Telegram 用户命令仍需 baseline 后新 update 才能验证真实自动回复和正式 DB 写入。


### 7.23 Phase AG Production-once 订阅过滤投递开关

状态：**已完成生产入口的 feature-flag 接线；默认 fixed-chat 路径保持不变，正式 daily LaunchAgent 尚未切换。**

代码变更：

- `packages/clawbot/src/intel/production_once.py`
  - 新增 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED` 分支。
  - 默认不开关时继续走原 `build_telegram_summary_delivery_probe` fixed-chat 投递路径，保护已验证的 daily LaunchAgent 行为。
  - 开关打开时要求 `INTEL_BRIEF_DB_PATH`，然后走 `deliver_summary_to_eligible_subscribers()` 或注入式 `subscription_delivery_runner`。
  - 输出 `delivery_mode` 与 `subscription_delivery_gate`，只记录 DB path 是否存在/token 是否存在等布尔信息，不输出 token/chat id。
- `packages/clawbot/tests/test_intel_production_once.py`
  - 新增 RED/GREEN 覆盖：默认 fixed-chat、开关开启走 subscription-filtered、缺 DB path 阻断。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseag/20260707T165951Z-production-once-subscription-delivery-switch-sandbox/evidence.json` | sandbox 注入式 runner 证明默认 `delivery_mode=fixed_chat` 且 fixed runner 调用 1 次；开关开启时 `delivery_mode=subscription_filtered` 且 subscription runner 调用 1 次；缺 `INTEL_BRIEF_DB_PATH` 时 blocked 且 `network_calls=0`。 |

边界：本节没有修改正式 private env 或 daily LaunchAgent；没有真实 Telegram API 调用；没有写正式 `intel_brief.db`。它只是把 production_once 做成可安全切换的接线点。

### 7.24 Phase AG 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseag/20260707T170034Z-production-once-subscription-switch-final-verification.json`

验证结果：

- Phase AG sandbox evidence JSON 可解析，状态 `success`。
- `ruff`：production_once、Phase AG 测试、subscription_delivery、telegram_delivery 通过。
- `pytest`：production_once、production_cycle、subscription filtered delivery、commercial MVP、delivery sandbox 共 22 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- Token 形态与 sandbox evidence 泄漏扫描通过；测试内 dummy secret/chat 仅用于断言 evidence 不泄漏。

边界：production daily cycle 仍默认 fixed-chat；商业订阅闭环仍需真实 Telegram 用户新命令写入正式 DB，并在后续显式打开订阅过滤开关完成真实订阅投递。


### 7.25 Phase AI Telegram 截图式 Inline Keyboard 菜单

状态：**已按用户截图要求完成：`/start` 不再只发送文本菜单或底部 reply keyboard，而是发送消息内 `inline_keyboard` 按钮矩阵。**

代码变更：

- `packages/clawbot/src/intel/subscriptions.py`
  - `build_telegram_menu_contract()` 输出 `reply_markup.inline_keyboard`，5 行 22 个按钮，按钮文本与用户给的菜单结构一致。
  - 标记 `menu_style=inline_keyboard_card`，避免后续误回退到底部键盘。
- `packages/clawbot/src/intel/telegram_runtime.py`
  - 支持 `callback_query` update，把 inline 按钮 `callback_data` 接回现有菜单 handler。
  - 点击按钮后通过 `answerCallbackQuery` 进行确认，防止 Telegram 客户端一直 loading。
- `packages/clawbot/src/intel/telegram_bot_runtime.py`
  - `getUpdates.allowed_updates` 扩展为 `message + callback_query`。
- `packages/clawbot/src/intel/telegram_delivery.py`
  - `TelegramBotApiSender` 支持 `reply_markup.inline_keyboard` 与 `answer_callback_query()`。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseai/20260707T172324Z-real-telegram-inline-keyboard-menu-send/evidence.json` | 真实 Bot API `sendMessage` 成功；`reply_markup_type=inline_keyboard`；5 行 22 个按钮；`has_bottom_reply_keyboard=false`；`callback_data_present=true`；`message_id_present=true`；证据不含 token/chat id/user id。 |

边界：本节只修正 Telegram 菜单交互体验；没有授予付费订阅、没有修改正式订阅偏好、没有触发支付/闲鱼/爬虫/远程 worker，也没有修改 daily LaunchAgent。真实用户点击 inline 按钮后的生产回调尚需下一次用户实际点击后由 runner 记录。

### 7.26 Phase AI 最终验证记录

最终验证证据：`packages/clawbot/data/intel_evidence/phaseai/20260707T172410Z-inline-keyboard-menu-final-verification.json`

验证结果：

- `ruff`：Telegram menu/runtime/bot runtime/delivery/real runner 相关文件通过。
- `pytest`：Telegram 菜单、runtime、update processor、delivery、bot runtime、real update runner 共 36 项通过。
- OpenEverything 与 VPS-Config `git diff --check` 均通过。
- 脱敏扫描通过：真实证据只保留 presence/count，不持久化 Bot token、chat id、Telegram user id、callback id 或原始消息文本。

用户可见结果：Telegram 中应出现类似截图的消息内灰色按钮矩阵，而不是底部普通键盘或纯文本菜单。

### 7.27 Phase AK Telegram 菜单按截图重排为 4 列按钮矩阵

状态：**已完成并真实发送**。用户指出上一版仍像“文本菜单/命令说明”，本阶段将 `/start` 菜单进一步改为截图式短文案 + 消息内灰色 inline 按钮矩阵。

代码变更：

- `packages/clawbot/src/intel/subscriptions.py`
  - 菜单正文改为短标题与短说明，移除旧的 `命令：/sources...` 文本说明。
  - inline keyboard 从长短不一的行宽调整为截图式 4 列优先矩阵：6 行、22 个按钮，最大行宽 4，最后一行 2 个宽按钮。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`
  - 固化 4 列矩阵结构，断言不再出现旧命令说明。
- `packages/clawbot/tests/test_intel_commercial_mvp.py`
  - 菜单分类按钮从 `reply_markup.inline_keyboard` 检查，而不是从正文里检查，防止后续误把按钮重新塞回正文。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseak/20260707T174008Z-reference-style-telegram-menu-send/evidence.json` | 真实 Telegram `sendMessage` 成功；`reply_markup_type=inline_keyboard`；6 行 22 个按钮；`row_lengths=[4,4,4,4,4,2]`；`max_row_length=4`；`screenshot_like_grid=true`；旧命令说明已移除；证据不含 token/chat id/user id。 |

边界：本节只修正 Telegram 菜单 UI；没有授予订阅、没有修改正式订阅偏好、没有修改 LaunchAgent/private env/VPS、没有触发支付/闲鱼/爬虫/远程 worker。

### 7.28 Phase AJ 真实订阅过滤投递

状态：**已完成真实 Telegram 投递**。正式 `intel_brief.db` 中 1 个 Telegram subscriber 已具备内部测试订阅授权、`akshare/senate_trading` 偏好与每日 08:30 推送偏好。本阶段使用最新真实 daily summary evidence 执行 subscription-filtered delivery，只投递给 active、未过期、偏好命中的订阅者。

代码/安全修正：

- `packages/clawbot/src/intel/subscription_delivery.py`
  - 投递 evidence 不再返回 `user_id=tg:<Telegram user id>`，改为 `user_id_present`，避免持久化真实 Telegram user id。
- `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py`
  - 增加断言：delivery/evidence 不包含 raw chat id，也不包含 `tg:<user>` 形式内部用户标识。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaj/20260707T172805Z-production-subscriber-internal-test-entitlement/evidence.json` | 正式 DB 内部测试订阅授权成功；subscriber eligible；默认偏好 `akshare/senate_trading`；推送偏好 daily 08:30 America/Denver。 |
| `packages/clawbot/data/intel_evidence/phaseaj/20260707T174622Z-real-subscription-filtered-delivery/evidence.json` | 真实 Telegram `sendMessage` 成功；`eligible=1/sent=1/failed=0`；source categories 为 `akshare/senate_trading`；`delivery_log_delta=1`；证据不含 token/chat id/user id。 |

正式 DB 结果：`delivery_log` 从 0 增至 1，最近记录 `channel_type=telegram`、`success=1`、`content_len=344`、无 error。

边界：这一步证明真实订阅者可按订阅/偏好/到期过滤收到真实简报，但正式 daily LaunchAgent 的自然 08:30 路径在本节完成时尚未切换为 subscription-filtered；支付/闲鱼订单授权自动化也尚未完成。

### 7.29 Phase AL daily 生产路径切换为订阅过滤投递

状态：**已完成可回滚切换，并通过受控 `production_once` 真实验证**。正式 LaunchAgent plist 未重装、不改 label；它已经通过 `INTEL_BRIEF_PRIVATE_ENV` 读取私有 env。本阶段只在私有 env 中新增/启用订阅投递开关和正式 DB path，让下一次自然 08:30 daily cycle 进入 subscription-filtered delivery。

变更内容：

- 私有 env：`.openclaw/intel-brief.production.env`（不提交、不打印明文）
  - 新增/启用 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED=true`
  - 新增 `INTEL_BRIEF_DB_PATH=/Users/blackdj/Desktop/OpenEverything/packages/clawbot/data/intel_brief.db`
- `packages/clawbot/src/intel/production_once.py`
  - 加固订阅投递 gate：开启订阅投递时必须同时满足 token present、DB path present、DB path exists。
  - 避免误配时创建空 DB 或静默跳过 subscriber。
- `packages/clawbot/tests/test_intel_production_once.py`
  - 增加 DB path 不存在时必须 blocked 的回归测试。

真实证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/private-env-subscription-switch.json` | 私有 env 已启用订阅投递；DB path 存在；token/chat id 只记录 presence。 |
| `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/production-once-subscription-delivery.json` | 受控 `production_once` 进入 `delivery_mode=subscription_filtered` 并真实发送成功。 |
| `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/evidence.json` | wrapper 证据：`status=success`，`eligible=1/sent=1/failed=0`，`network_calls=1`，`delivery_log_delta=1`。 |

回滚边界：无需重装 LaunchAgent。将 `.openclaw/intel-brief.production.env` 中 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED=false` 或删除该键，即可回到 fixed-chat delivery。保留 `INTEL_BRIEF_DB_PATH` 不会在开关关闭时生效。

当前边界：正式 daily LaunchAgent 已会在下一次自然 08:30 读取新私有 env 并走订阅过滤路径；但“自然 08:30 触发 + subscription-filtered delivery”的证据仍需等下一次定时触发后审计。支付/闲鱼订单授权自动化仍未完成。

### 7.30 Phase AM 受控 production_cycle 全链路订阅投递验证

状态：**已完成受控全链路验证**。本阶段不等待自然 08:30，而是使用 LaunchAgent 实际调用的同一脚本 `packages/clawbot/scripts/intel_production_cycle.py`，在当前 private env 订阅投递模式下跑完整链路：采集 → brief → summary → production_once → subscription-filtered Telegram delivery。

受控运行结果：

- Evidence 根目录：`packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/`
- 主 evidence：`latest-production-cycle.json`
- collect：`success=2/failed=0`
  - `senate_trading`
  - `akshare`
- summary：`partial_fallback`，2 个 item（fallback-only 模式，未额外调用 LLM 付费接口）
- production_once：`status=success`
- delivery mode：`subscription_filtered`
- subscription gate：ready，missing gates 为空，DB path exists，token present（presence only）
- delivery：`eligible=1/sent=1/failed=0`
- Telegram network calls：1
- `delivery_log`：增至 3 条 success 记录

关键证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/latest-production-cycle.json` | 全链路 status=success，network_calls=1。 |
| `packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/runs/20260707T180242Z-production-once-delivery.json` | `delivery_mode=subscription_filtered`，`eligible=1/sent=1/failed=0`。 |
| `packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/runs/20260707T180242Z-collect-once.json` | 真实采集 `success=2/failed=0`。 |

当前边界：这是受控运行，不是自然 LaunchAgent 08:30 触发；因此下一门槛仍是等待正式 `ai.openclaw.intel-brief.scheduler` 自然触发后审计 `latest-production-cycle.json`，确认自然定时上下文也进入 `delivery_mode=subscription_filtered`。支付/闲鱼订单授权自动化仍未完成。

### 7.31 Phase AN 订阅到期管理与提醒审计

状态：**已完成商业 MVP 所需的订阅生命周期最小闭环**。此前系统已有订阅表、到期字段和 delivery 过滤，但缺少可审计的“即将到期提醒 / 已过期标记 / 去重提醒”执行层。本阶段新增 lifecycle 模块，默认只读审计；只有显式开启 `apply_expiry=True` 才标记 expired，显式开启 `send_reminders=True` 且传入 sender 才发送提醒。

代码变更：

- `packages/clawbot/src/intel/subscription_lifecycle.py`
  - 新增 `audit_subscription_lifecycle()`：识别 active 订阅中的已过期与 N 天内到期订阅。
  - 支持 `apply_expiry=True` 标记过期订阅为 `expired`，并写 `subscription_audit_log(event_type='expired')`。
  - 支持 `send_reminders=True` 发送到期提醒，提醒 audit 事件按 subscriber/plan/day 去重。
  - 证据只记录 `user_id_present` / `channel_user_id_present`，不持久化 raw Telegram user id/chat id。
- `packages/clawbot/scripts/intel_subscription_lifecycle_sandbox.py`
  - 生成 sandbox evidence，不调用真实 Telegram。
- `packages/clawbot/tests/test_intel_subscription_lifecycle.py`
  - 覆盖默认只读、不泄漏 raw id、过期标记、提醒发送、同日提醒去重、sandbox evidence 脱敏。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasean/20260707T181146Z-subscription-lifecycle-sandbox/evidence.json` | sandbox：发现 1 个已过期 active、1 个 7 天内到期；标记 expired=1；发送 fake reminder=1；写 audit=2；replay 同日 reminders_sent=0，证明去重。 |
| `packages/clawbot/data/intel_evidence/phasean/20260707T181219Z-production-db-subscription-lifecycle-readonly-audit/evidence.json` | 正式 DB 只读审计：当前 expired_active=0、expiring_active=0、counts_unchanged=true、network_calls=0。 |

边界：本阶段没有真实发送到期提醒，也没有改正式订阅状态；正式 DB 审计是只读。后续若要上线自动提醒，可在 daily cycle 或独立 LaunchAgent 中显式启用 `send_reminders=True`；若要自动停权，显式启用 `apply_expiry=True`。

### 7.32 Phase AO production_cycle 集成订阅生命周期只读审计

状态：**已完成并通过受控验证**。Phase AN 提供了订阅生命周期能力；Phase AO 将其接入 daily `production_cycle` evidence。下一次正式 LaunchAgent 自然 08:30 触发时，`latest-production-cycle.json` 将包含 `subscription_lifecycle` 字段，用于记录订阅到期状态。

代码变更：

- `packages/clawbot/src/intel/production_cycle.py`
  - 新增 `_subscription_lifecycle_readonly_audit()`。
  - 从 private env 合并读取 `INTEL_BRIEF_DB_PATH`。
  - 若 DB path 缺失或文件不存在，记录 `skipped`，不影响 collect/delivery 主链路。
  - 若 DB path 存在，调用 `audit_subscription_lifecycle(... apply_expiry=False, send_reminders=False)`。
  - evidence 增加顶层 `subscription_lifecycle` 字段。
- `packages/clawbot/tests/test_intel_production_cycle.py`
  - 覆盖 DB path 存在时 lifecycle 只读审计成功。
  - 覆盖 DB path 缺失时 lifecycle skipped 且主 production cycle 仍可继续。

受控证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseao/20260707T182041Z-production-cycle-lifecycle-readonly-integration/evidence.json` | production_cycle status=success，包含 `subscription_lifecycle.status=success`，`reason=readonly_audit_complete`。 |
| `packages/clawbot/data/intel_evidence/phaseao/20260707T182041Z-production-cycle-lifecycle-readonly-integration/wrapper.json` | 正式 DB 计数 unchanged；lifecycle summary 全 0；network_calls=0；无 Telegram 发送。 |

边界：Phase AO 使用 injected production_once runner 避免再次真实发送 Telegram；真实订阅投递已在 Phase AM 验证。生命周期审计默认只读，不标记 expired、不发送提醒。下一次自然 08:30 审计时应确认 `latest-production-cycle.json.subscription_lifecycle` 存在。

### 7.33 Phase AP 人工订单/续费授权入口

状态：**已完成支付/闲鱼自动化之前的最小运营入口**。本阶段不接入闲鱼自动上架、不接支付回调；只提供人工核单后的安全授权工具，避免运营者直接手改 SQLite。

代码变更：

- `packages/clawbot/src/intel/manual_entitlement.py`
  - 新增 `grant_manual_entitlement()`：把已核验的外部订单映射为 Telegram subscriber 订阅授权。
  - 默认 `apply=False`，只输出 dry-run 计划，不写 subscriber/subscription/preference/audit。
  - `apply=True` 时才 upsert plan/subscriber、grant subscription、设置 source preferences 与 daily delivery preferences。
  - 支持续费：如果已有 active subscription，则从现有 `expires_at` 顺延，而不是从当前时间覆盖。
  - 订单号不以明文写 evidence；写入 audit source 时只保留 `order_ref_sha256:<短哈希>`。
- `packages/clawbot/scripts/intel_manual_entitlement.py`
  - CLI：默认 dry-run，必须显式 `--apply` 才写 DB。
- `packages/clawbot/scripts/intel_manual_entitlement_sandbox.py`
  - 生成 sandbox evidence：dry-run、首次授权、续费。
- `packages/clawbot/tests/test_intel_manual_entitlement.py`
  - 覆盖 dry-run 不写业务行、apply 写授权、续费顺延、CLI evidence、sandbox 脱敏。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseap/20260707T182938Z-manual-entitlement-sandbox/evidence.json` | sandbox：dry-run 成功；首次授权成功；续费到 `2026-09-05T00:00:00+00:00`；network_calls=0；不含 raw Telegram/chat/order。 |
| `packages/clawbot/data/intel_evidence/phaseap/20260707T183007Z-production-db-manual-entitlement-dry-run/evidence.json` | 正式 DB dry-run：基于当前真实 subscriber 预演 30 天续费，planned expiry `2026-09-06T00:00:00+00:00`；counts_unchanged=true；network_calls=0。 |

边界：本阶段没有修改正式 DB 订阅、没有调用支付/闲鱼/Telegram/远程 worker，也没有决定商品上架或售卖方式。后续如果用户人工核单，只需用 CLI 带 `--apply` 写入授权；真正的闲鱼/支付自动化仍是后续显式生产决策。

### 7.34 Phase AR Telegram 菜单按最新参考图改成热搜按钮矩阵

状态：**已完成并真实发送验证**。用户提供的参考图要求主菜单像 Telegram 热搜 Bot：短标题 + 大量灰色按钮，而不是把订阅状态、分类状态和 `/sources` 命令说明直接显示在首屏。本阶段将 `/start` 首屏改为：

```text
🔥 热搜排行
🔥 近期高价值情报入口
发送关键词🔍搜索你感兴趣的内容
```

按钮矩阵当前为 6 行 23 个按钮，最大 4 列：Github/OpenAI/Claude/Deepseek，微博/小红书/抖音/知乎，B站/天气/空气/降雨，温度/湿度/灾害/投行，科技/股市/加密/订阅，最后一行是 `⚙️ 设置 / 🔎 自定义 / ⏰ 定时`。订阅状态仍可通过 `订阅` 或 `⚙️ 设置` 进入 `/status`，但不再污染主菜单首屏。

代码变更：

- `packages/clawbot/src/intel/subscriptions.py`
  - 新增 `TELEGRAM_INLINE_MENU_BUTTONS`，将按钮展示文本与 `callback_data` 分离。
  - `build_telegram_menu_contract()` 输出参考图式短正文和 6 行 inline keyboard。
- `packages/clawbot/src/intel/telegram_menu.py`
  - 增加稳定 callback 值映射：`settings/status/custom/schedule` 等。
  - 保留原中文按钮文本映射，兼容用户直接发送按钮文本的场景。
- `packages/clawbot/scripts/intel_telegram_menu_sandbox.py`
  - evidence 增加 `menu_style`、`inline_keyboard`、`reply_markup_kind`，方便后续审计 UI 基线。
- 相关测试更新：`test_intel_telegram_menu_handlers.py`、`test_intel_commercial_mvp.py`、`test_intel_telegram_runtime.py`、`test_intel_telegram_real_update_runner.py`。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasear/20260707T185209Z-reference-screenshot-style-menu-contract-v2/evidence.json` | sandbox contract 成功，`network_calls=0`，菜单行宽 `[4,4,4,4,4,3]`。 |
| `packages/clawbot/data/intel_evidence/phasear/20260707T185237Z-reference-screenshot-style-menu-real-send/evidence.json` | 真实 Telegram `sendMessage` 成功，`network_calls=1`，证据不含 token/chat id/user id。 |
| `packages/clawbot/data/intel_evidence/phasear/20260707T185522Z-reference-screenshot-menu-final-verification/evidence.json` | ruff/pytest/diff check/JSON parse/token scan 均通过。 |

边界：只发送 1 条菜单视觉验收消息；没有修改 production DB、订阅授权、LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。真实用户点击 callback 的生产 evidence 仍待下一次点击后由 update runner 记录。

### 7.35 Phase AQ GitHub Trending 数据源与三源生产链路验证

状态：**已验证可用**。本阶段补齐一个核心高价值公开信息源：GitHub Trending daily。该源满足原始商业设想中“每天 GitHub star 增长排行榜前三项目与项目地址”的 MVP 需求，不依赖 GitHub API token。

代码变更：

- `packages/clawbot/src/intel/sources/github_trending.py`
  - 新增 `parse_github_trending_html()`、`fetch_github_trending()`、`GitHubTrendingAdapter`。
  - 输出字段：`repo`、`url`、`description`、`language`、`stars_today`。
  - 修复真实页面 sponsor link 干扰：仓库链接只从 article repo heading 提取。
- `packages/clawbot/src/intel/sources/registry.py`
  - 默认 adapter registry 注册 `github_trending`，evidence path 指向 Oracle SG West 真实调用结果。
- `packages/clawbot/scripts/intel_collect_once.py`
  - `github_trending` primary worker=`oracle-sg-west`，fallback=`oracle-arm1`。
  - 修复 fallback profile source 从误标的 `senate_trading` 改为 `github_trending`。
- `packages/clawbot/scripts/intel_worker_bundle.py`
  - worker bundle 包含 `github_trending.py`。
- `packages/clawbot/src/intel/production_cycle.py`
  - 默认 production cycle sources 包含 `github_trending`。
- 测试：`test_intel_github_trending.py`、`test_intel_collect_once.py`、`test_intel_source_adapter_base.py`、`test_intel_worker_bundle.py` 等。

真实调用证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaq/20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json` | Oracle SG West real worker success；`raw_count=3`；返回 `Zackriya-Solutions/meetily`、`addyosmani/agent-skills`、`ruvnet/RuView`；cleanup 成功。 |
| `packages/clawbot/data/intel_evidence/phaseaq/20260707T190718Z-controlled-production-cycle-three-sources/latest-production-cycle.json` | 受控 production cycle 三源采集 success=3/failed=0；`delivery_mode=subscription_filtered`；Telegram delivery success。 |
| `packages/clawbot/data/intel_evidence/phaseaq/20260707T191656Z-github-trending-final-verification/evidence.json` | ruff/pytest 23 项/JSON parse/token scan/文档同步均通过；自然 LaunchAgent 下一次 08:30 仍待审计。 |

已知边界：

- 这是 GitHub Trending HTML 抓取，若 GitHub 页面结构大改，需要 parser 回归验证。
- 本轮真实 subscriber 当前偏好命中 `akshare/senate_trading`；`github_trending` 已进入采集与 summary，但是否推送给某用户仍由其 source preferences 决定。
- 本阶段没有重装 LaunchAgent、没有创建常驻 worker、没有新增密钥或支付/闲鱼逻辑。

### 7.36 Phase AU AI 模型动态源接入

状态：**已验证可用**。本阶段补齐 OpenAI/Claude/DeepSeek 前沿 AI 模型动态源，作为商业化简报的高价值信息类目之一。实现不依赖付费 API，不使用第三方新闻聚合，优先官方入口。

代码变更：

- `packages/clawbot/src/intel/sources/ai_model_updates.py`
  - 新增 `AIModelUpdatesAdapter`、`FeedSpec`、RSS/HTML parser。
  - OpenAI：`https://openai.com/news/rss.xml`。
  - Anthropic：`https://www.anthropic.com/news`。
  - DeepSeek：`https://www.deepseek.com/`。选择根页是因为 Oracle SG West 对 `/news` 返回 404，但根页可访问并含官方公告。
  - 合并策略按 feed 轮询，避免 OpenAI RSS 过多挤掉 Anthropic/DeepSeek。
- `packages/clawbot/scripts/intel_collect_once.py`
  - 新增 `ai_model_updates` worker profile：primary `oracle-sg-west`，fallback `oracle-arm1`，limit=6。
  - `github_trending` limit=3，符合 GitHub Star 增长榜前三口径。
- `packages/clawbot/src/intel/production_cycle.py`
  - 默认 sources 增至四源：`senate_trading/akshare/github_trending/ai_model_updates`。
- `packages/clawbot/src/intel/telegram_menu.py`
  - `OpenAI/Claude/Deepseek` 按钮映射为 `ai_model_updates` 偏好。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseau/20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json` | Oracle SG West real worker success；providers 包含 `openai/anthropic/deepseek`；`raw_count=6`；cleanup 成功。 |
| `packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json` | 四源 collect success=4/failed=0；GitHub raw_count=3；AI raw_count=6；subscription-filtered Telegram delivery success。 |
| `packages/clawbot/data/intel_evidence/phaseau/20260707T195140Z-ai-model-and-recipient-filter-final-verification/evidence.json` | ruff/pytest 37 项/diff/JSON parse/token scan/文档同步均通过。 |

边界：本阶段没有安装服务、没有重装 LaunchAgent、没有创建常驻 worker、没有新增或输出密钥。自然 LaunchAgent 下一次 08:30 仍需审计新版四源默认链路。

### 7.37 Phase AV 按用户偏好裁剪订阅消息正文

状态：**已完成并通过 sandbox + 真实受控投递验证**。四源上线后发现一个商业化订阅核心问题：旧逻辑只用 source preferences 筛收件人，但正文仍是全量 summary，可能让用户收到未订阅分类。Phase AV 将 delivery 改为 per-recipient filtered payload。

代码变更：

- `packages/clawbot/src/intel/subscription_delivery.py`
  - 新增 `_filter_summary_payload_for_categories()`。
  - 每个 recipient 发送前按 `matched_categories` 裁剪 `items`。
  - 重写 `llm.summary_text` 为“已按你的订阅偏好筛选 N 条情报”，避免全局摘要泄漏未订阅分类。
  - `delivery_log.content_summary` 写入过滤后的消息。
  - evidence 中每个 delivery 增加 `filtered_item_count`。
- `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py`
  - 覆盖 A股/国会/AI 三个用户只收到自己分类，且 delivery_log 不含未订阅条目。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseav/20260707T194902Z-subscription-delivery-per-recipient-filter-sandbox/evidence.json` | sandbox 三个用户各自 filtered_item_count=1，network_calls=0。 |
| `packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json` | 真实 Telegram delivery success；当前真实 subscriber matched `akshare/senate_trading`，filtered_item_count=2。 |

边界：当前是“按偏好裁剪全局 fallback 摘要”的 MVP；后续可升级为按用户偏好单独生成 LLM 摘要，但这会增加 token 消耗。

### 7.38 Phase AR 补充：Telegram 菜单增加截图式底部宽按钮

状态：**已完成并真实发送验证**。在此前“短标题 + 灰色按钮矩阵”基础上，为更接近用户参考图，`/start` inline keyboard 新增最后一行两个宽入口：`🔍 备用搜索` 与 `👥 设置导航`。当前菜单首屏仍不显示 `inactive_or_expired`、分类状态或 `/sources` 命令说明。

当前菜单基线：7 行 25 个按钮：

1. `Github / OpenAI / Claude / Deepseek`
2. `微博 / 小红书 / 抖音 / 知乎`
3. `B站 / 天气 / 空气 / 降雨`
4. `温度 / 湿度 / 灾害 / 投行`
5. `科技 / 股市 / 加密 / 订阅`
6. `⚙️ 设置 / 🔎 自定义 / ⏰ 定时`
7. `🔍 备用搜索 / 👥 设置导航`

代码变更：

- `packages/clawbot/src/intel/subscriptions.py`：增加最后一行两列宽按钮。
- `packages/clawbot/src/intel/telegram_menu.py`：新增 `search` callback prompt；`设置导航` 复用 settings/status 路由。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`：更新菜单基线和 search callback 覆盖。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasear/20260707T200639Z-reference-screenshot-style-menu-with-wide-row-sandbox/evidence.json` | sandbox contract 成功，`network_calls=0`，inline keyboard 为 7 行。 |
| `packages/clawbot/data/intel_evidence/phasear/20260707T200700Z-reference-screenshot-style-menu-with-wide-row-real-send/evidence.json` | 真实 Telegram `sendMessage` 成功，`network_calls=1`，`reply_markup_present=true`，证据不含 token/chat id。 |

验证：ruff 通过；`test_intel_telegram_menu_handlers.py`、`test_intel_telegram_runtime.py`、`test_intel_telegram_real_update_runner.py` 共 16 项通过；JSON parse、token-shape scan、diff check 通过。

边界：只修改菜单展示/回调合同和测试；没有修改 production DB、订阅授权、LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

### 7.39 Phase AW SEC 13F 机构持仓源聚合修复与五源生产链路

状态：**已验证可用**。本阶段完成机构/顶级基金持仓变化的 MVP 数据源：官方 SEC EDGAR 13F。当前先以 Berkshire Hathaway (`CIK0001067983`) 作为第一个顶级机构样本，后续可扩展多机构 CIK 列表。

代码变更：

- `packages/clawbot/src/intel/sources/institutional_13f.py`
  - 从 SEC submissions JSON 找最新 `13F-HR`。
  - 读取 archive `index.json`，定位 information table XML。
  - 解析持仓字段：issuer/class/cusip/value/shares/share_type/investment_discretion。
  - 修复真实数据质量问题：按 `(issuer, class, cusip)` 聚合重复行，整数 value/shares 求和，按 value 降序输出后再 limit。
- `packages/clawbot/src/intel/sources/registry.py`
  - `institutional_13f` evidence path 更新为真实 Oracle SG West 聚合验证证据。
- `packages/clawbot/tests/test_intel_institutional_13f.py`
  - 增加重复 issuer/CUSIP 聚合回归。

真实调用证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaw/20260707T201214Z-institutional-13f-oracle-sg-worker-aggregated.json` | Oracle SG West real worker success；`raw_count=10`；样本包含 Apple、American Express、Coca Cola、Bank of America、Chevron；cleanup 成功。 |
| `packages/clawbot/data/intel_evidence/phaseaw/20260707T201455Z-controlled-production-cycle-five-sources-13f-aggregated/latest-production-cycle.json` | 五源 collect `success=5/failed=0`；summary 21 items；subscription-filtered Telegram delivery `eligible=1/sent=1/failed=0`。 |

验证：

- 已先看到聚合测试失败：旧实现返回 2 行重复 `ALLY FINL INC`。
- 修复后 `test_intel_institutional_13f.py` 通过。
- 目标环境 Oracle SG West 真实调用通过。
- 五源受控 production cycle 通过并真实投递。

边界：本阶段没有安装/重装 LaunchAgent，没有创建常驻 worker，没有新增或输出密钥。远端 worker 仍是 `/tmp` 临时 staging 并 cleanup。当前真实用户偏好只启用 `akshare/senate_trading`，所以虽然五源全部进入采集和 summary，本次推送正文仍按偏好过滤为 2 条。

### 7.40 LaunchAgent 08:30 自然触发只读审计边界

状态：**有成功运行产物，但审计未判定 verified_success**。按只读边界运行 `intel_launchagent_audit.py` 检查正式 daily LaunchAgent `ai.openclaw.intel-brief.scheduler`，没有执行 kickstart/bootstrap/bootout。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaset/20260707T202022Z-launchagent-natural-0830-post-run-audit/evidence.json` | audit `status=pending_calendar_trigger`；原因是 `launchctl print` 当前显示 `runs=0`、`last exit code=(never exited)`。 |
| `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs/latest-production-cycle.json` | 存在 2026-07-07 14:30:05Z 运行产物，production cycle `status=success`，collect `success=2/failed=0`，Telegram send success。 |

边界说明：该自然 08:30 产物证明已安装的两源 LaunchAgent 包在当时产生了成功运行结果；但由于当前 `launchctl print` 计数不支持 verified_success 判定，审计结果按工具规则保留为 `pending_calendar_trigger`。本阶段没有重装、重启或触发 LaunchAgent。后续若要证明“五源新版默认链路”的自然定时，还需要下一次自然 08:30 后再次审计。

### 7.41 Phase AX Telegram 分类按钮不再覆盖用户偏好

状态：**已完成，sandbox 验证 + 真实 `/start` update 回发验证**。此前按钮点击复用 `/sources` 替换语义，导致用户在菜单里追加分类时会误清空已选分类。商业化订阅场景下这会直接破坏用户自定义偏好，因此本阶段将菜单分类按钮改为开关式交互。

新语义：

- 菜单分类按钮：未全选则追加该按钮对应分类；已全选再点则取消该按钮对应分类。
- `/sources ...` 命令：继续保留显式替换语义。
- 示例：`股市` → `Github` → `Github` 的偏好变化为：
  1. `akshare / institutional_13f / senate_trading`
  2. `akshare / github_trending / institutional_13f / senate_trading`
  3. `akshare / institutional_13f / senate_trading`

代码变更：

- `packages/clawbot/src/intel/telegram_menu.py`
  - 区分菜单按钮来源与 `/sources` 命令来源。
  - 按钮来源读取当前 profile 后做 union/remove。
- `packages/clawbot/scripts/intel_telegram_menu_sandbox.py`
  - evidence 增加 `button_preference_flow`，记录按钮偏好流。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`
  - 新增按钮不覆盖偏好的回归测试。
  - 更新旧按钮映射测试，避免把同一用户连续点击误当成空状态映射。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseax/20260707T202835Z-telegram-menu-button-preference-toggle-sandbox/evidence.json` | `network_calls=0`；按钮偏好流符合预期。 |
| `packages/clawbot/data/intel_evidence/phaseax/20260707T202846Z-telegram-real-update-runner-button-preference-cycle.json` | 真实 Telegram update runner 处理 1 条 `/start`，成功回发新版 inline keyboard；raw update/chat id 未持久化。 |

边界：本阶段没有修改套餐/授权、支付/闲鱼、LaunchAgent、VPS 或采集 worker。正式 DB 只因真实 `/start` update 做了 subscriber/chat upsert，当前真实 subscriber 偏好仍为 `akshare/senate_trading`。

### 7.42 Phase AY Telegram 偏好回包改为用户可读中文分类名

状态：**已完成并通过 sandbox 验证**。真实订阅用户不应看到 `akshare`、`senate_trading`、`github_trending` 这类内部 id。Phase AY 将 Telegram `/sources`、分类按钮回包和 `/status` 的分类展示改为产品化中文名，同时保留内部 id 用于投递过滤和审计。

示例：

- `akshare` → `A股资金流向`
- `senate_trading` → `国会持仓`
- `github_trending` → `GitHub趋势`
- `institutional_13f` → `机构13F持仓`
- `ai_model_updates` → `AI模型动态`

代码变更：

- `packages/clawbot/src/intel/telegram_menu.py`
  - 新增 `CATEGORY_DISPLAY_NAMES`。
  - `/status` 和 sources 回包使用中文展示名。
  - handler result 增加 `enabled_category_labels`，保留 `enabled_categories` 内部 id。
- `packages/clawbot/scripts/intel_telegram_menu_sandbox.py`
  - evidence 增加 `button_preference_flow_display`。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`
  - 增加回归：用户回包不包含内部 id，包含中文分类名。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseay/20260707T203616Z-telegram-menu-user-facing-category-labels-sandbox/evidence.json` | `network_calls=0`；同时记录内部分类 flow 与中文展示 flow。 |

边界：没有修改 DB schema、订阅授权、支付/闲鱼、LaunchAgent、VPS 或采集 worker。subscription-filtered delivery 仍按内部 category id 工作。

### 7.43 Phase AZ 天气/空气/降雨/温度/湿度/灾害源接入

状态：**已验证可用**。本阶段补齐菜单中已有但此前没有数据源支撑的天气相关分类。`weather` 聚合源当前以 Denver, CO 作为 MVP 默认位置，后续可扩展为用户级 location preferences。

代码变更：

- `packages/clawbot/src/intel/sources/weather_monitor.py`
  - 新增 `WeatherMonitorAdapter` 与 `fetch_weather_monitor()`。
  - NWS `api.weather.gov`：天气、温度、降雨概率、湿度、active alerts。
  - Open-Meteo Air Quality：US AQI、PM2.5、PM10。
- `packages/clawbot/src/intel/subscription_delivery.py`
  - 支持 `category_aliases` 匹配。订阅 `weather` 可收到所有天气子类；订阅 `temperature` 只收到温度 item。
- `packages/clawbot/src/intel/brief_builder.py`
  - generic item 保留 `category` / `category_aliases`。
- `packages/clawbot/src/intel/subscriptions.py`
  - `DEFAULT_MVP_CATEGORIES` 加入 `weather/air_quality/rainfall/temperature/humidity/disaster_alerts`。
- `packages/clawbot/src/intel/production_cycle.py`
  - 默认 production sources 增加 `weather`。
- `packages/clawbot/scripts/intel_collect_once.py` / `intel_worker_bundle.py`
  - weather 使用 Oracle SG West primary、Oracle ARM1 fallback，limit=6，并进入临时 worker bundle。

真实调用证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseaz/20260707T204803Z-weather-oracle-sg-worker.json` | Oracle SG West real worker success；`raw_count=6`；包含天气、温度、降雨、湿度、灾害预警、空气质量；cleanup 成功。 |
| `packages/clawbot/data/intel_evidence/phaseaz/20260707T205021Z-controlled-production-cycle-six-sources-weather/latest-production-cycle.json` | 六源 collect `success=6/failed=0`；summary 27 items；subscription-filtered Telegram delivery `eligible=1/sent=1/failed=0`。 |

商业边界：NWS 官方 API 要求 User-Agent；Open-Meteo Air Quality 无 Key endpoint 适合 MVP 验证，但公开文档区分非商业与商业使用。正式面向付费用户公开销售前，需要确认/购买商业使用权限或替换为空气质量合规来源。

边界：未安装或重装 LaunchAgent，未创建常驻 worker，未新增或输出密钥。远端 worker 仍是 `/tmp` 临时 staging 并 cleanup。

### 7.44 Phase BA Telegram 菜单按用户截图 v3 对齐

状态：**已完成并通过 sandbox 验证**。本阶段针对用户截图继续收敛 Telegram `/start` 首屏：菜单不再是正文命令说明，而是三行热搜入口文案 + Telegram inline keyboard 多列按钮矩阵。

当前首屏文案：

```text
🔥 热搜排行
🔥 近期高价值情报排行榜
发送关键词🔍搜索你感兴趣的内容
```

当前按钮矩阵：

1. `Github / OpenAI / Claude / Deepseek`
2. `微博 / 小红书 / 抖音 / 知乎`
3. `B站 / 天气 / 空气 / 降雨`
4. `温度 / 湿度 / 灾害 / 投行`
5. `科技 / 股市 / 加密 / 订阅`
6. `设置 / 自定义 / 定时`
7. `🔍 情报搜索 / 👥 功能导航`

代码变更：

- `packages/clawbot/src/intel/subscriptions.py`
  - 更新 `/start` 文案和 inline keyboard 展示文本。
- `packages/clawbot/src/intel/telegram_menu.py`
  - 新增 `🔍 情报搜索/情报搜索`、`👥 功能导航/功能导航` callback 文案兼容。
  - 保留旧 `备用搜索/设置导航` callback 兼容，避免历史消息按钮失效。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py`
  - 更新 screenshot-style keyboard 合同断言。
- `packages/clawbot/tests/test_intel_commercial_mvp.py`
  - 更新商业 MVP 菜单标签断言。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaseba/20260707T210354Z-screenshot-style-telegram-menu-v3/evidence.json` | `network_calls=0`；菜单 contract 显示 7 行 25 个按钮；无 token/chat id 明文。 |
| `packages/clawbot/data/intel_evidence/phaseba/20260707T210719Z-screenshot-style-menu-v3-real-send/evidence.json` | 真实 Telegram `sendMessage` success；`token_present=true/chat_id_present=true/message_id_present=true`，未写 token/chat id 明文。 |

边界：未修改 production DB、LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

### 7.45 Phase BB LaunchAgent 自然 08:30 审计 verified_success

状态：**已验证可用（有边界）**。正式 daily LaunchAgent `ai.openclaw.intel-brief.scheduler` 的自然 08:30 触发已经由 run artifact 与 stdout 证明：`latest-production-cycle.json` 时间戳为 `2026-07-07T14:30:05Z`，collect `success=2/failed=0`，production_once success，真实 Telegram send success，message_id present。

修复点：

- `packages/clawbot/src/intel/launchagent_audit.py`
  - 增加 stdout 成功检查。
  - 当 `launchctl runs` 计数滞后但 LaunchAgent 仍加载、日历配置存在、stdout 与 run artifact 均成功时，允许 `verified_success`。
  - 保留 `launchctl.counter_mismatch=true` 与 `verification.basis=artifact_and_standard_output`，不掩盖 macOS counter 异常。
- `packages/clawbot/tests/test_intel_launchagent_audit.py`
  - 增加 counter stale 回归测试。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json` | `status=verified_success`；`artifact_success=true`；`stdout_success=true`；`telegram_send_success=true`；`launchctl.counter_mismatch=true`。 |

边界：没有执行 `launchctl kickstart/bootstrap/bootout`，没有重装 plist，没有改 private env、VPS、远程 worker、生产 DB、支付/闲鱼或爬虫。该自然触发发生在 GitHub/AI/13F/weather 接入前，因此它证明“正式 LaunchAgent 自然 08:30 能触发并真实投递”，但不证明“当前六源默认链路已经自然触发”。六源链路仍以后续 controlled production cycle 为证据，下一次自然 08:30 后需要继续审计。

### 7.46 Phase BC 订阅生命周期生产安全维护入口

状态：**已完成并通过 sandbox + production readonly 验证**。此前订阅生命周期能力已经存在，但缺少一个可控生产入口。Phase BC 新增 `intel_subscription_lifecycle.py`，让运营者可以安全审计订阅到期状态，并在显式 gate 下执行过期标记或到期提醒。

代码变更：

- `packages/clawbot/src/intel/subscription_lifecycle.py`
  - 新增 `LIFECYCLE_APPLY_ACK_VALUE`。
  - 新增 `run_subscription_lifecycle_maintenance()`：默认只读；apply/reminder 走 gate；返回脱敏 evidence。
- `packages/clawbot/scripts/intel_subscription_lifecycle.py`
  - 新增生产安全 CLI。
  - 默认读取 private env（如存在）但只输出 presence booleans。
  - `--apply-expiry` 需要 lifecycle apply ack。
  - `--send-reminders` 需要 Telegram token、runtime ack 和 `--allow-real-network`。
- `packages/clawbot/tests/test_intel_subscription_lifecycle.py`
  - 新增 default readonly、blocked apply、apply with ack、injected reminder transport、CLI evidence 回归。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasebc/20260707T212320Z-subscription-lifecycle-maintenance-sandbox/evidence.json` | sandbox 覆盖 readonly、缺 ack 阻断、apply expired、injected reminder；无 token/chat/user 明文。 |
| `packages/clawbot/data/intel_evidence/phasebc/20260707T212337Z-subscription-lifecycle-production-readonly/evidence.json` | 正式 DB 只读审计 success；`expired_active_found=0`、`expiring_active_found=0`、`network_calls=0`。 |

边界：没有对正式 DB 执行 apply，没有真实发送 reminder，没有修改 LaunchAgent/private env/VPS/远程 worker/支付/闲鱼/爬虫。daily `production_cycle` 仍只做 lifecycle readonly audit；是否把 maintenance CLI 纳入独立日常运维，需要后续运营决策。

### 7.47 Phase BD LaunchAgent 下一次六源自然触发 readiness

状态：**已验证 ready，但不是自然触发本身**。Phase BB 证明了正式 LaunchAgent 可以自然 08:30 触发并真实投递；Phase BD 进一步证明已安装 plist 下一次自然触发将读取当前六源默认配置，而不是固定旧两源。

代码变更：

- `packages/clawbot/src/intel/launchagent_readiness.py`
  - 只读解析 installed plist。
  - 检查是否指向 `intel_production_cycle.py`、是否没有旧 `--source` 固定参数、是否含 08:30 calendar、private env、production ack。
  - 读取 controlled six-source cycle evidence，确认 sources 与当前 defaults 一致且 collect 全成功。
- `packages/clawbot/scripts/intel_launchagent_next_run_readiness.py`
  - 输出 next-run readiness evidence。
- `packages/clawbot/tests/test_intel_launchagent_readiness.py`
  - 覆盖 default source ready、显式旧 source mismatch、CLI evidence。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasebd/20260707T213012Z-launchagent-next-run-six-source-readiness/evidence.json` | `status=ready`；`missing=[]`；plist uses default sources；expected six sources match；controlled cycle collect `success=6/failed=0`。 |

边界：没有执行 `launchctl kickstart/bootstrap/bootout`，没有重装 plist，没有修改 private env、VPS、远程 worker、生产 DB、支付/闲鱼或爬虫，也没有调用 Telegram。该 evidence 不能替代下一次自然 08:30 后的真实 post-run audit。

### 7.48 Phase BE 投递文案产品化与 E2E 状态审计

状态：**当前 E2E 状态已 verified（仍需下一次自然 08:30 六源 post-run audit）**。本阶段修复真实 Telegram 投递仍显示 sandbox/fake 文案的问题，并新增只读 E2E 状态审计。

代码变更：

- `packages/clawbot/src/intel/delivery.py`
  - `build_delivery_message()` 新增 `delivery_context`。
  - 默认生产文案标题为 `🧭 情报简报`。
  - 生产文案末尾显示“内容来自公开来源自动汇总，不构成投资建议”。
  - sandbox 调用显式 `delivery_context="sandbox"`，保留 fake sender 边界。
- `packages/clawbot/src/intel/subscription_delivery.py`
  - subscription-filtered delivery 显式使用 production 文案。
- `packages/clawbot/src/intel/e2e_status_audit.py`
  - 新增只读商业 MVP E2E 状态审计。
- `packages/clawbot/scripts/intel_e2e_status_audit.py`
  - 新增 CLI evidence 输出。
- `packages/clawbot/tests/test_intel_e2e_status_audit.py`
  - 覆盖 verified、sandbox 文案拦截、CLI evidence。

证据：

| 证据路径 | 结果 |
|---|---|
| `packages/clawbot/data/intel_evidence/phasebe/20260707T213634Z-production-once-user-facing-delivery-copy/evidence.json` | 真实 Telegram send success；subscription-filtered；eligible=1/sent=1/failed=0；filtered item count=2。 |
| `packages/clawbot/data/intel_evidence/phasebe/20260707T213933Z-commercial-mvp-e2e-status-audit/evidence.json` | `status=verified`；active eligible subscriber=1；latest delivery success；无 sandbox/fake 文案；按偏好过滤；next-run readiness=ready。 |

边界：真实发送 1 条 Telegram 验收消息；未修改 LaunchAgent/private env/VPS/远程 worker/支付/闲鱼/爬虫。E2E audit 只读且不写 raw chat id、user id、token 或完整消息正文。

## 2026-07-07 Phase BF — Telegram 菜单 v4 截图式交互修复

- 状态：已验证可用。
- 变更：`/start` 菜单改为截图式热搜排行卡片；新增 persistent bottom shortcut keyboard `👥 功能导航 / 🔥 热搜排行`；`👥 功能导航` 从 status/settings 改为返回菜单卡片；普通关键词文本进入搜索提示。
- 真实调用证据：`packages/clawbot/data/intel_evidence/phasebf/20260707T215317Z-screenshot-like-menu-v4-real-send/evidence.json`，Telegram send `status=success`，发送 2 条消息（安装底部快捷键盘 + inline 菜单卡片）。
- 命令注册证据：`packages/clawbot/data/intel_evidence/phasebf/20260707T215248Z-telegram-command-menu-registration-v4.json`，`setMyCommands` 成功。
- Sandbox 合同证据：`packages/clawbot/data/intel_evidence/phasebf/20260707T215214Z-screenshot-like-telegram-menu-v4/evidence.json`。
- 已验证边界：证据只记录 token/chat id 是否存在与脱敏发送结果；未输出或写入 Telegram token、chat id、user id 或 raw update payload。
- 未改变：LaunchAgent、VPS、private env、远程 worker、生产订阅授权、支付/闲鱼、爬虫。

## 2026-07-07 Phase BG — LaunchAgent 六源 expected-source 审计强约束

- 状态：已验证可用。
- 变更：`intel_launchagent_audit.py` 新增 `--expected-source` 可重复参数；审计结果必须证明期望源全部出现且 collect 成功，才可在 expected-source 模式下返回 `verified_success`。
- 回归证据：`packages/clawbot/data/intel_evidence/phasebg/20260707T220027Z-launchagent-six-source-expected-regression/evidence.json`。
- 真实边界：旧自然 08:30 artifact 只有 `senate_trading/akshare` 两源；在六源 expected audit 下现在返回 `failed_or_incomplete`，缺失 `github_trending/ai_model_updates/institutional_13f/weather`。
- 验收边界：该阶段证明审计不会误判；还没有证明下一次自然 08:30 已真实跑满六源。下一轮自然触发后必须用同样的 `--expected-source` 六源参数复审。
- 未改变：LaunchAgent plist、private env、VPS、远程 worker、生产 DB、订阅授权、支付/闲鱼、爬虫；本阶段无 Telegram 或外部数据源网络调用。

## 2026-07-07 Phase BH — 商业 MVP E2E 审计接入自然六源 LaunchAgent 门禁

- 状态：已验证可用，当前生产状态为 `needs_attention`。
- 变更：`intel_e2e_status_audit.py` 新增 `--launchagent-audit-evidence`；E2E `verified` 必须包含自然 08:30 LaunchAgent 六源 expected-source audit 的 `verified_success` 证据。
- 当前证据：`packages/clawbot/data/intel_evidence/phasebh/20260707T220524Z-commercial-mvp-e2e-requires-natural-six-source/evidence.json`。
- 当前结果：真实 subscriber、偏好、最新投递、文案、偏好过滤、next-run readiness、latest production delivery evidence 均为通过；但 `natural_six_source_launchagent_verified=false`，因为旧自然运行只含两源，缺失 `github_trending/ai_model_updates/institutional_13f/weather`。
- 验收边界：该阶段证明商业 MVP 总审计不会提前标记完成；下一次自然 08:30 后仍需重新跑六源 expected-source post-run audit 与 E2E audit。
- 未改变：LaunchAgent plist、private env、VPS、远程 worker、生产 DB、订阅授权、支付/闲鱼、爬虫；本阶段无 Telegram 或外部数据源网络调用。

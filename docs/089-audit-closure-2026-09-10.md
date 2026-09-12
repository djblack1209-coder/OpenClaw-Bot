# OpenEverything 审计修复闭环跟踪

目标：以 088 审计报告为基线，修复并验证可独立执行的工作；外部阻塞保留证据、前置条件和验收步骤。开始基线为 e414e959，工作分支 codex/audit-closure-20260910。

2026-09-12 更新：用户要求将保留的全部改动随新闻归并提交并合入 main。下文 2026-09-10 的测试数量和“未提交、未推送”属于当时检查点；本次新验证、提交与运行边界见 [新闻归并记录](090-news-consolidation-2026-09-12.md)。C03 的旧科技早报路径已退役，可靠投递机制继续服务运营日报与周报；历史记录保留。

状态说明：待处理 / 进行中 / 本地验证通过 / 运行验收通过 / 外部阻塞。不能用“本地测试通过”代替上线和商业验收。

| 编号 | 工作 | 状态 | 闭环条件 |
|---|---|---|---|
| C00 | GPT 连接器恢复与读取验收 | 运行验收通过（网页）；旧任务工具引用待刷新复核 | GPT 实际工作区/Git/文件读取匹配，绑定保存回读与同一会话重开通过 |
| C01 | 模型精确估价、调用账本、预算预留/结算 | 本地实现经独立复审通过；运行启用待确认 | 并发、重启、缓存、正常/中断流式与未知成本均有回归 |
| C02 | 依赖漏洞、干净构建、CI 门禁 | 已验证范围经独立复审接受；微信/Linux 桌面/Rust 警告仍未闭环 | 各生态独立结果，干净安装与相关测试通过 |
| C03 | 普通早报/日报/周报可靠投递 | 本地实现经独立复审通过；运行验收待完成 | 持久状态、异常重试、未知结果与重启去重 |
| C04 | 文档结构、死链、安装说明 | 本地实现经独立复审通过 | 文档门禁通过，当前基线与归档区分 |
| C05 | 首次引导保存/验证与准确文案 | 本地实现经独立复审通过 | 保存失败不误报完成，可重试或显式跳过 |
| C06 | Docker 监听/鉴权/配置 | 本地实现经独立复审通过；dotenv 补充验证完成 | 宿主访问合同与容器配置验证 |
| C07 | 统一观测内容脱敏 | macOS 组合验证通过；Linux 整合与独立复审待做 | 真实出口路径中测试秘密与选定 PII 不外传 |
| C08 | 交易确认与请求幂等 | macOS 组合及浏览器验证通过；Linux 整合与独立复审待做 | 请求重放、过期确认、参数更改和未知券商结果回归 |
| C09 | 隔离恢复、安装/手机体验与运行验收 | 待处理 | 可执行部分实际验证；外部依赖另记 |
| C10 | 商业材料与权限边界 | 待处理 | 数据流/许可证/单所有者边界/支持手册/计量验收准备 |

## 外部依赖

- JIYU 正常 MFA 下的登录后业务；不绕过 MFA，不虚构已支付/到账。
- 经营主体、上游/数据来源授权、支付批准、证书账号与实际经营数据。
- 真实客户访谈、持续使用与付费意愿；本轮只可准备材料，不代替客户反馈。
- 需要时间窗口的自然投递/长期可用性与异地完整恢复；记录实测范围，不提前宣称 7 天或 30 天目标达成。

## 执行记录

- 已建立目标并保留审计报告。当前未部署新产品版本、未发送外部消息、未发起交易或支付。

- 用户要求优先修复 GPT 连接器：已完成只读配对与最高能力实际读取测试，保留新会话绑定；未更改其他项目的连接。旧任务预加载工具引用失效单列，未通过重复创建连接掩盖。

- 重开验证通过：离开会话后按保存地址恢复，同一连接验收回复、当前修复分支与 6 Pro 控件均可见。

- C04：新增 8 项门禁回归，修复前 6 失败/2 通过；修复后 8 通过，仓库 make docs-check、ShellCheck 与 git diff --check 通过。当前入口改为 README/地图/快速开始/当前基线；跨工作区路径带前缀，移除不存在的根 AGENTS 入口；仍拦截缺基线、死链、重复编号与可变运行包规格。CI 改用同一 make 入口。
- C01：GPT 计划已实际读取并核验调用旁路；决定采用 SQLite 唯一账本、按实际发送尝试预留与结算、明确未知费用，保留现有路由/循环隔离。旧版本成本与路由 62 项测试通过，但不覆盖已确认缺陷；新增回归中。

## C01 实现合同与启用准备

本轮新增 `src/core/cost_ledger.py`、`cost_policy.py`、`accounted_completion.py`、`accounted_router.py` 与 `cost_ledger_cli.py`（均位于 `packages/clawbot/`），CostController 改为唯一 SQLite 账本的门面。旧 `daily_costs.jsonl` 保留，启动时不自动导入或确认期初余额。

- 准入：同一事务检查已结算金额、所有未决预留与本次上界。金额以纳美元向上取整，预算归属日为 America/New_York。跨午夜、重启、多线程、多事件循环和多进程不释放未决预留。
- 发送：每个 Router 重试、跨 deployment 回退、原生 Claude HTTP 重试和单 Key 探针使用独立尝试 ID。Router 的选择、每个事件循环独立实例、并发信号量和调用前限流保留；禁止隐藏流式重放和模型镜像请求。预算/账本异常穿透 SDK 重试、instructor 回退与 Bot 通用回退。
- 终态：供应商实际提供的完整最终 usage 按明确费率结算为估价；SDK 推算或补默认值不构成供应商计量。缺 usage、未知额外计费、超时、取消和断流保留预留待核对。已发送后结算写入失败不会重新请求。超过预留上界照实记账并阻止进一步准入，不能截断费用。
- 价格：完整 deployment、provider、模型 ID 与价格快照绑定。参考模型表改为精确匹配，未知模型返回空值；“免费”名称、统一 tier 和历史注释不构成零费率依据。多模态、额外收费维度、冲突的输出上限与覆盖供应商身份的请求目前明确拒绝。
- 展示：费用 API、首页、AI 配置页与 Telegram 费用查询读取同一账本。每次统计使用一致的 SQLite 读快照。累计费用与日费用分开；未初始化显示未知，未决费用显示不完整。金额为 USD 配置估价，不能当成供应商已对账账单。7/30 日完整费用在覆盖不足时为空，已知小计另列 `known_week_cost` / `known_month_cost`；周报和累计费用同样提供明确的已知小计字段。
- 缓存：采用新键版本，包含完整消息、输出上限和其他响应参数；兼容入口直接传递 cache_ttl/no_cache/stream。命中缓存不新增调用、usage 或费用，缓存故障不重发请求。

### 价格配置与启用步骤（尚未操作运行数据）

每个 `config/llm_routing.json` 的模型项可添加 `accounting` 对象。下例仅是合成测试配置，**不是任何供应商现价**：

```json
{
  "accounting": {
    "provider": "fixture",
    "snapshot": "fixture-v1",
    "currency": "USD",
    "source": "synthetic-test-only",
    "input_per_million": "1",
    "output_per_million": "1",
    "max_input_tokens": 100,
    "max_output_tokens": 100
  }
}
```

实际配置应根据该渠道/账户的收费规则填写费率、来源、快照标识与供应商实际执行的输入/输出上限；不能把期望的提示长度当成服务端上下文上限。请求按配置的完整输入上限预留，以涵盖 SDK 注入的 schema/system/tool 开销，因此比按提示词估算更保守。无可核验费率的部署保持拒绝状态；明确零新增 API 费用也必须配置零费率，不能继承模型的宣传名称。可识别的 cache_control、服务端搜索/代码执行工具等额外收费请求在发送前拒绝；响应出现额外计量时，保留已知 token/额外数量并进入未知状态。

价格表持久保存 provider、deployment、完整模型、来源、USD 费率和输入/输出上限的白名单快照及内容摘要。同一 deployment 的快照标签不能改写为不同内容；不同部署不能串用身份。数据库升级到 schema 2 时保留原有尝试。旧 JSONL、手工补记和 schema 1 中未保存过的费率无法凭空重建；真实模型新调用均在准入事务内绑定完整快照。

原生 Claude 单独使用 `native_claude_deployments` 数组，项包含 `id`、`api_base`、`model`、`accounting`；base 与模型必须精确匹配，不把某个中转渠道的价格套到其他入口。配置内容不得含密钥。现有显式启用和 `/claude` 授权要求仍然有效。

在 `packages/clawbot` 工作目录中，使用既有 Python 3.12 环境运行以下 CLI。应先对隔离副本操作，`--db` 必须明确指定目标：

```text
python -m src.core.cost_ledger_cli --db <副本数据库> stats
python -m src.core.cost_ledger_cli --db <副本数据库> import-legacy <不可变JSONL快照>
python -m src.core.cost_ledger_cli --db <副本数据库> import-legacy <不可变JSONL快照> --apply
python -m src.core.cost_ledger_cli --db <副本数据库> activate --opening-spend-usd <已核实的切换日总费用>
python -m src.core.cost_ledger_cli --db <副本数据库> reconcile <attempt_id> --actual-usd <供应商已核实费用> --reconciliation-id <唯一核对ID> --evidence <非秘密账单引用>
python -m src.core.cost_ledger_cli --db <副本数据库> release-reserved <确定未发送的attempt_id>
python -m src.core.cost_ledger_cli --db <副本数据库> recover-bounds --recovery-id <唯一恢复ID> --evidence <价格核验引用> --replacements <更正价格快照JSON>
```

导入默认 dry-run；按文件内容快照与行位置生成身份，既保留同文不同记录，又避免重复导入同一快照。损坏、非法日期和负金额阻止整批导入，原文件不修改。需先导入再启用，期初总费用不能低于当天已导入费用。旧主链曾漏记，因此导入不能重建完整历史；空数据库也不等于零支出。

运行切换前仍需：核实价格配置与期初金额、保留旧日志和数据库备份、确认新账本覆盖起点。当前未部署、未更改实际费率、未启动生产迁移。回滚不能清空预留、删账，或恢复旧付费路径后宣称预算仍受保护。`bound_exceeded` 表示估价上界失效，需先核对实际费用与价格/上限配置，不能直接忽略状态继续收费。

`reconcile` 追加不可覆盖的核对/调整记录，保留原始估价、usage、历次金额与账单引用。同 ID 相同内容幂等，不同内容冲突；账单更正使用新的核对 ID。`release-reserved` 只释放尚未进入 dispatched 的预留，与发送状态转换使用同一事务竞争。`recover-bounds` 要求全部上界异常已按实际费用核对、没有未决尝试、逐项提供同 provider/deployment/model 的新价格快照，新完整上界必须提高且覆盖异常费用。恢复会停用旧快照，旧运行配置不能借清除标记重新放行。更正 JSON 为 attempt ID 到完整白名单快照的映射，包含 deployment_id、model 以及上述 accounting 字段；不包含密钥或完整路由配置。

### C01 本地验证记录（按轮次区分）

- 首轮账本测试 17 项通过；随后组合回归 219 项通过，包含 32 线程/独立事件循环竞争、两个进程共享账本、ET 日切与夏令时、不可写数据库、迁移预览等。
- 真实锁定 LiteLLM Router 的 fallback 和 RateLimit retry 经过合成传输；真实 LiteLLM + OpenAI SDK + httpx MockTransport 验证单次 HTTP 尝试没有 SDK 隐藏重试；原生 ResilientHTTPClient 的 503 重试按两次尝试记账。
- SDK 1.90.2 的重试策略函数未实现 `InternalServerErrorRetries` 字段分支；回归使用其真实支持的 RateLimit 策略，未修改锁定版本或扩大 SDK 升级范围。
- 首页合成状态渲染 4 项通过：已知零、未知、待核对、正常日费用；TypeScript 检查通过。补充费用 API、群聊调用控制、限流、鉴权与安全回归后的组合结果为 381 项通过；随后真实 instructor 验证重试/预算拒绝专项在内的 27 项通过（与组合回归有重叠，不相加）。文档与费用渲染合计 12 项通过，文档门禁、TypeScript、修改文件 Ruff 与 diff 检查通过。GPT 独立评审待完成。
- 首轮使用隔离源码副本、环境白名单与 socket guard，但没有隔离用户 home，不能据此断言所有导入均未读取真实环境文件；这项证据限制已在第二轮整改。模型/Telegram/观测出口使用假对象或假传输，未发起真实模型、Telegram 或交易请求。

首轮组合为 **383 passed**。第二轮使用加强后的 `scripts/run_clawbot_offline_tests.py` 重新验收，不沿用首轮的隔离保证。命令为：

```text
python3 scripts/run_clawbot_offline_tests.py tests/test_cost_control.py tests/test_cost_ledger.py tests/test_litellm_accounting.py tests/test_cost_api.py tests/test_llm_cache.py tests/test_litellm_router.py tests/test_llm_routing_config.py tests/test_http_client.py tests/test_api_mixin.py tests/test_structured_llm_router_isolation.py tests/test_chat_router_cost_controls.py tests/test_rate_limiter.py tests/test_api_security_middleware.py tests/test_security.py tests/test_api_routes_regression.py tests/test_offline_isolation.py
python3 scripts/test_offline_test_runner.py
node --test scripts/docs_layout.test.mjs scripts/cost_telemetry.test.mjs
```

上述脚本不安装依赖，使用现有 `.venv312`；生产 `data/`、私有环境文件和凭据环境不会复制。当前价格配置仍未激活，新增费用控制尚不能作为生产运行预算已受保护的证据。

第二轮隔离使用临时源码、配置文件白名单、临时用户状态路径与缓存目录、禁用 dotenv 自动加载、Python DNS/socket 阻断，以及 macOS 文件/网络沙箱。遵循本地执行约束，不重设 `HOME` / `CODEX_HOME`；通过独立 `OE_TEST_HOME` 映射 `Path.home()`、`expanduser("~")` 和当前用户目录查询，并由系统阻止访问真实用户目录数据（仅允许只读既有依赖环境）。合成复制测试覆盖未列入白名单的配置与符号链接；子进程和代表性 iflow/草稿/发布锁路径均有断言。当前运行器只支持已验证的 macOS 本地验收环境。

真实 HTTP/SSE 回归先复现“无供应商 usage 却被 SDK 合成用量结算”（1 失败、5 通过），修复后 6 项通过，再扩充部分 usage 覆盖。系统文件隔离另实际拦截了 SDK 导入时对项目 `.env` 的自动查找；禁用该自动加载后 33 项 SDK 测试通过。R1 至 R6 第一组修复回归为 109 项通过；包含多进程对账/释放竞争、一致读快照、不可变价格重放与受控恢复。

第二轮最终组合：**418 项 Python 通过**，另有 **1 项合成复制边界测试、12 项 Node 测试通过**；TypeScript、Ruff、22 文档门禁与 diff 检查通过。真实 SSE 测试经过模型池/Router/SDK/假 HTTP 全链路，包含完整计量、无计量、缺部分计量、断流、取消、提前关闭和未消费即关闭；完整供应商 token 同时进入运行统计。账本 `usage_source` 明确保存计量来源，费用估价与供应商实际账单通过独立核对记录区分。最终隔离源码摘要为 `f9282f6e150b9277bd3d5904dd3c99dba5365e5219d51a28cd4904ae4aac5ced`，由运行器在导入前计算。第二轮 GPT 独立复审接受 R3 至 R6 和流式修复，指出非流式 SDK 默认用量及嵌套计费维度仍需修复。


### C01 第三轮：普通响应计量来源与嵌套费用

普通 Router 调用和单 Key 探针现使用逐尝试的 SDK 原始响应观察器，在 LiteLLM 构造带默认零值的 `Usage` 之前提取 usage。沿用 SDK 自身的请求初始化和既有回调，观察器只绑定该次调用，结束后恢复；不会覆盖全局观测回调，也不会把完整响应正文加入账本。没有原始计量入口的渠道保守保持未知。流式原有转换前观察与底层关闭逻辑不变。

策略对 details 字段作明确分类：普通文本细分和输出推理 token 包含在已计价总量中；搜索、缓存、音频和其他尚未建模的有效数量保持未知。嵌套搜索次数、缓存创建总量及 5 分钟/1 小时缓存明细中的安全数字会保留。零 token 费率不代表额外服务零费用。

失败证据包括上一轮末的真实非流式测试（2 失败、1 通过：缺整个 usage 与缺输入均错误结算），以及本轮 28 个嵌套字段反例。最初扩展六种普通响应时，有五例受测试共享缓存影响而没有实际发出 HTTP；现已显式禁止缓存，每例都断言一次 HTTP 调用，未将这五个夹具失败计为产品缺陷。

第三轮完整计费专项 **83 项通过**，源码复制摘要 `c0642ef26dd058a5ef34a9a5a588fbf9580a9d24ac22a755d1bbb08e06968bf6`。六种普通响应均经过真实模型池 → Router → LiteLLM → OpenAI SDK → 假 HTTP；28 项嵌套用量覆盖字典/真实 SDK 对象与正/零费率。此前真实 SSE、重试、缓存、探针和 instructor 回归同时通过。完整 C01 组合 **452 项 Python 通过**，复制源码摘要与上述专项一致。Ruff、文档门禁（8 项测试与 22 文档）和 diff 检查通过。第三轮未更改桌面代码，第二轮 TypeScript 与 4 项费用渲染证据继续适用；第三轮 GPT 已读取六份独立执行记录并验收 C01 本地阶段；不构成运行启用或整个审计闭环。

## C02 依赖与干净构建

审计改为逐锁独立执行、保留原始 JSON 和错误输出、最后汇总退出码。`make dependency-audit` 默认包含三组 npm 的全部/生产范围、两份 Python 锁和 Cargo，共九次扫描；CI 的 RustSec 保留在独立桌面任务，因此安全任务显式使用 `--without-rust`。缺工具、超时、损坏报告与异常退出均记为未完成，不能产生通过结果。npm high 阈值、Python/Cargo 漏洞失败、Action SHA 与哈希锁要求保留。

本轮重新取得的基线如下，npm 数量是各范围报告中的受影响条目，包含传递影响，不是独立公告数量；同一锁的不同范围不能相加。原始记录中的第一次 Python 审计因临时解释器路径处理失败，只作为历史失败，不作为完整基线。

| 锁与范围 | 修复前 | 候选修复后 |
|---|---|---|
| 桌面 npm 全部 / 生产 | 8（3 high、4 moderate、1 low）/ 1 low | 0 / 0 |
| 受管 runtime npm 全部 / 生产 | 6（1 high、5 moderate）/ 14（2 high、12 moderate） | 0 / 0 |
| 微信 npm 全部 / 生产 | 3 moderate / 0 | 0 / 0 |
| Linux Python，261 包 | 7 项公告，3 个包 | 0 |
| macOS Python，260 包 | 7 项公告，3 个包 | 0 |
| Cargo | 0 漏洞、7 警告 | 0 漏洞、7 警告 |

桌面定向修复 `fast-uri 4.1.3`、`hono 4.13.5`、`js-yaml 4.3.2`、`qs 6.16.0`，并更新同一兼容范围内的 humanfs、浏览器兼容数据库与 PostCSS selector parser 依赖链。runtime 单独使用 `fast-uri 3.1.6`、`hono 4.13.5`、`qs 6.16.0`，没有把桌面的 fast-uri 主版本套入 runtime。对应公告包括 GHSA-5jgf-p345-68v8、GHSA-f65p-4m7j-42xc、GHSA-fph4-wmhf-6fwf、GHSA-jqff-g426-hqxp（fast-uri），GHSA-2883-xcg3-v3hh（js-yaml），GHSA-gqvv-2mrq-wpjv/GHSA-g6gw-c38x-mqfc/GHSA-crvj-82cr-hjcx（hono），以及 GHSA-x5fp-wj9c-mxmx/GHSA-4mjr-xmp4-gh2g（qs）。各锁的实际依赖链、完整公告、工具版本、时间、摘要与报告位置保存在独立审计 JSON 中。

微信开发工具 `vitest` 和 `@vitest/coverage-v8` 同步固定到修复 GHSA-82fw-gwwq-j7x9 的 `4.1.11`，保留原 `vite 7.3.5`。曾遇 npm 解析器 `edgesOut` 异常；固定原 Vite 版本后锁生成及干净安装成功，未使用 force 或 legacy-peer-deps。运行依赖 qrcode-terminal、zod 和 TypeScript 原锁版本不变。Vitest 4 删除旧 glob/minimatch/brace-expansion 链，因此供应链规则允许 brace-expansion 缺席；如果再次出现，仍必须符合原固定安全版本，其他完整性约束保留。

两份 Python 锁都只改动三个实际包版本和对应哈希：`pypdf 6.15.0 → 6.16.1`（CVE-2026-84309/84310/84311），`RestrictedPython 8.2 → 8.3`（CVE-2026-55830），`tornado 6.5.7 → 6.5.8`（GHSA-wwv5-g3v4-889x、GHSA-8423-8fgw-73vq、CVE-2026-82397）。其余包版本逐项比较相同；LiteLLM、instructor、OpenAI、httpx、tenacity、tiktoken 六个冻结版本保留，`make python-lock-check` 已通过。

干净验证入口改为 `scripts/check_clean_install.py`，Shell 仅转发参数。它在临时目录复制公开源码白名单，安装三组 npm 及本机 Python 哈希锁；安装不复用活动 node_modules/.venv。npm 生命周期脚本全部禁用。公开制品获取与离线构建分阶段，真实用户目录读写由 macOS 沙箱阻断，仅放行必要工具的只读代码；构建和测试禁止出网。Python 六个仅有源码分发的包，固定归档哈希并检查构建入口后，才在无网络环境中构建。`--python` 仅接受临时虚拟环境，并保留其解释器符号链接语义；原 C01 隔离保护没有放宽。默认清理临时产物，`--keep` 可保留完整证据。

原桌面锁在全新环境下的安装、类型检查、lint、生产构建及 22 项安全测试均通过，未复现旧 lucide-react 缺文件；据此归为旧安装状态问题，没有为它改产品源码。候选锁重复完成上述验证并通过。受管 runtime 的全新安装、固定直接版本和登记 bin 文件检查通过，没有启动任何运行服务。

微信发布包没有 tsconfig 或上游测试；本轮完成全新安装、Vitest CLI 和 33 个源码文件语法转译。额外的入口类型编译失败：当前冻结的 OpenClaw 包不导出插件使用的 `openclaw/plugin-sdk` 根入口，且缺少 `silk-wasm` 类型依赖。因此微信完整类型编译、上游测试和通道运行仍未通过，不能以语法检查代替。这是既有源码/运行 SDK 的兼容性缺口，后续 C09 需单独处理，不通过升级整个运行框架绕过本轮冻结范围。

Cargo 的 7 条警告仍未关闭：proc-macro-error 与五个 unic 包为 unmaintained；glib 0.18.5 为 RUSTSEC-2024-0429 unsound。它们属于现有 Tauri/GTK 依赖链，未使用忽略规则或无兼容依据的主版本覆盖。候选审计使用的 RustSec 数据库提交为 `b50980aad8b8f14f77e25a97b32dd94bf008b0af`。macOS 编译不能替代 Linux GTK 路径的验证。

C02 本轮最终本地结果：新 macOS Python 3.12 环境哈希安装和 `uv pip check` 通过；使用该环境运行完整 C01 组合 **452 项通过**，源码快照仍为 `c0642ef26dd058a5ef34a9a5a588fbf9580a9d24ac22a755d1bbb08e06968bf6`。先行的 202 项子集已通过，包含在 452 项中，不相加。启动阶段比已有环境慢，但测试正常完成，最终组合测试耗时 66.16 秒。Cargo 在独立 CARGO_HOME 和 target 下完成 `fetch --locked`、禁止出网的 `check --locked --offline`，以及三个 `npm_runtime::tests`；44 个其他 Rust 测试未在本轮运行。这里的 Cargo 编译会调用仓库现有 `build.rs` 中的 tauri-build 库，不涉及桌面打包、安装或服务启停。

最终 `make dependency-audit` 九次扫描退出 0；随后加强了 Python/Rust 损坏报告字段校验，以保存的九份原始报告重验仍通过。审计汇总器现有 9 项回归，包含历史失败、后续组继续执行、异常报告和生态失败策略。新临时解释器/公开源码边界 2 项及原复制边界 1 项通过。运行器增加的文件/网络探针实际通过；源码转译探针与完整 452 项在先行验证脚本启动后加入，已分别执行并单独记录，不能假称它们包含在先行脚本的旧 results.json 中。

证据保存在临时目录及分开的协作执行记录中：审计基线 `c02-audit-before-verified`、最终 `c02-audit-final`，干净安装 `oe-clean-install-u3u8s1bk`，独立 Rust `oe-c02-cargo-377kq51m`。本地成功不构成 Linux 哈希锁安装、Linux GTK 编译、微信通道兼容、生产预算启用或部署验收。C02 独立复审结果见下一段；C03–C10 继续保留在原目标内。

C02 独立复审已完成：ChatGPT 实际读取第四轮输出 15–26，接受已验证的依赖整改、门禁及 macOS 构建范围，明确 C02 整体仍未关闭，允许进入独立的 C03。复审后补充说明：输出 27 为临时添加的 7 项 AES 用例，实际运行 Vitest 4.1.11 与 coverage-v8 通过，仅验证开发工具和该模块，不代表缺失的上游测试。输出 28 记录可选的整个临时依赖目录预编译失败：CCXT 4.5.56 内 7 个 BIP 钱包文件存在语法错误；核心 CCXT 导入及本项目行情路径使用的 Binance 对象离线构造另行通过，未执行 HTTP。这两份补充输出不属于上述十二份已复核证据；钱包工件限制保留至 C09，未据此升级其他依赖。

## C03 调度与普通报告投递

已确认三个额外入口问题：`_run_deal_scan` 嵌套在数据库备份函数内部，却被循环作为实例方法调用；循环崩溃后仅靠 `_running` 可能误报运行；早报从没有导出实例的模块导入 `news_fetcher`，而实际实例已由 ExecutionHub 接收。恢复折扣扫描方法归属会使该扫描重新可达，运行启用前需明确这一行为变化。本轮仅调用假扫描函数，不抓取或推送。

现有调度/Intel 相关五个测试文件在隔离环境先得到 50 通过、2 失败，失败原因为没有复制测试依赖的两个公开 CLI。临时精确加入这两个文件后，52 项全部通过。该基线未覆盖普通报告的持久投递和已确认的循环入口问题，后续新增回归需覆盖它们。


C03 本地实现保留原循环和 Intel 流程，增加独立 `data/report_delivery.sqlite3`。该文件只在实际组装报告服务时创建；API/CLI 状态读取使用只读模式，不会用“查状态”悄悄启用新覆盖期。首次创建记录不可变 `coverage_start`，早于覆盖开始的计划实例为 `expired/before_coverage`，不会根据空表推断过去未发。未在现有运行环境创建该数据库、重启服务或启用真实发送。

三个普通报告统一使用 America/New_York 的完整计划日期与 UTC 秒级时间。默认允许计划后两小时补发，服务参数最多六小时；越过午夜时仍引用原计划日，跨年周报使用完整周日日期。夏令时缺失时间向前规范化，重复时间选择第一次出现。生成器收到计划时间仅修正文案日期；原数据源内部降级与当前数据读取行为未改成历史快照。旧字符串结果的生成质量为 `unverified`，不能因发送成功宣称全部来源健康。

每个“报告种类、计划时刻、通道、目标”只有一个作业。生成内容、摘要及 UTF-16 不超过 4000 单位的稳定分段先原子保存，再取得发送租约。单段发送前记录 `sending`，成功回执必须包含正整数 Telegram message_id；此处 `sent` 仅代表 Telegram API 接受，不代表用户阅读。多段报告保留每段回执，后续明确限流重试只发送剩余段落；遵守完整 RetryAfter、不缩短服务端等待时间，每段最多三次，越过补发窗口后过期。生成失败也最多三次，不生成替代“成功”文案。

超时、网络错误、取消、崩溃、发送租约过期、API 已接受但本地回执未保存均进入 `unknown`，不自动重放。SQLite 原子声明和租约令牌隔离并发所有者，旧生成者或发送者不能覆盖新状态。循环逐项隔离异常；重复 start 保留现有任务，stop 等待取消完成，状态以实际任务存活情况为准。原本错误嵌套的折扣扫描已恢复为实例方法；其运行可达性变化需随实际启用一起验证。

普通报告使用新的专用发送适配器，交易通知、批处理和 EventBus 回调保持原有路径。目标沿用现有公开/私有收件人解析；缺少私有目标时不会改用公开目标。实际 Bot 必须已初始化。每次生成前和每段发送前重新检查总开关、维护模式、报告开关、环境开关与对应收件人的 daily_report 偏好；配置读取失败阻止发送。控制面板展示持久结果与生成质量，不再把内存日期或持久配置里的任意 last_run 当作发送回执。

微信镜像单独存储，复用同一内容，不改变 Telegram 成功状态。新增仅供普通报告使用的 `single_attempt` 参数，关闭发送请求的网络层和外层自动重试；现有其他调用保留默认行为。使用真实 HTTPX 的假响应验证成功、403、500 和超时都只有一个发送请求。现有 iLink 布尔返回仍没有可验证消息回执，因此镜像只记录 `unknown/legacy_mirror_receipt_unverified`，长消息第一段未知后停止，不能宣称完整微信投递或 C02/C09 兼容问题已关闭。读取 context token 的请求不属于发送效果，仍保留原读取逻辑。

本地查询命令（本次只对临时合成数据库测试）：

```sh
python -m src.execution.report_delivery_cli --db /path/to/report_delivery.sqlite3 status
python -m src.execution.report_delivery_cli --db /path/to/report_delivery.sqlite3 resolve REPORT_ID --part 0 --action confirmed_sent --expected-state unknown --operation-id UNIQUE_CHECK_ID --evidence ticket:MANUAL_CHECK --message-id VERIFIED_MESSAGE_ID
```

仅在人工核实后使用 `confirmed_sent` 或 `not_sent`；需要唯一操作 ID、预期 unknown 状态和无秘密的证据引用。重复同一操作幂等，冲突操作被拒绝；不会重置尝试次数或已确认分段。确认未发送也仍受原截止时间限制，没有批量重置接口，CLI 不产生网络发送或报告生成。

验证过程保留失败证据：循环四项和持久层十项分别先失败后通过；真实 SDK 发送组先缺少模块失败，随后 12 项通过。扩展组合首轮 98 通过、3 个测试复制依赖缺失；精确加入公开 `multi_main.py` 与两个 Telegram 闸门 CLI 后 112 项通过，未放开整个 scripts 目录。复制边界回归覆盖四个明确 CLI、主入口及任意文件排除。微信单次请求新增四项先失败，完成后相关 23 项通过。最终检查又发现：配置暂不可读会消耗未实际开始的生成次数。新增失败回归后，将次数记录移到偏好/目标检查之后、生成开始之前。修复后 C03 与相关旧功能组合 **118 项通过**；完整组合 **570 项通过**（包含原 C01 的 452 项，不另行相加），两次源码快照均为 `ff8a193b8a0e0cea41e2f9f99d94725334aed1e6ef5c6b21e6bcafc777159138`。此前 117/569 项属于修正前成功证据，不能替代最终结果。


最终相关 Python/Ruff、复制边界 1 项、文档 8 项/22 文档、gitleaks 和 diff 检查通过。主入口全文件 Ruff 本来有 32 项历史诊断；对比 HEAD 后没有新增诊断，不能写成主入口完整 lint 零告警。测试日志保留临时源码摘要和文件/网络隔离探针结果，未运行真实 multi_main 启动流程。第五轮独立复审已读取输出 29–35 并要求补修，详见下一节；自然调度、Telegram 真正回执、微信完整通道及长期观察均未作为本轮实测通过项。


### C03 第二轮：受检偏好、维护恢复与账本费用

第五轮独立复审确认持久投递和未知结果处理可以保留，指出实际用户偏好管理器吞掉读取错误、维护暂停被当作终态关闭，以及日报/周报仍读取旧费用分析器。复审也已补读 C02 输出 27、28；其 AES 局部通过与 CCXT 附带钱包语法失败边界继续保留。

报告路径新增实际 UserPreferencesManager 的受检读取方法。每次预检重新读取合成或运行配置的当前持久值，不改变其他设置路径的旧接口；正常首次缺省允许接收，明确 false 关闭，损坏 JSON、不可读文件、非法结构和非布尔报告值均阻止生成和发送。已经存在或保存过的偏好文件消失，也不能重新当作首次缺省。恢复有效配置后可在原窗口内重试，不消耗未开始的生成次数。回归通过执行源码中的完整实际管理器类，避免导入 globals 时构造无关机器人；没有以假 allowed 抛错替代底层读取测试。

维护模式和调度总开关是可恢复的 blocked；窗口内恢复会继续同一作业，超时后过期。单项报告开关、渠道环境开关及收件人明确关闭使用终态 disabled。目标暂缺为 blocked/target_unavailable，缺私聊目标不改投公开目标。发送每段前重新检查；维护发生在第一段确认之后时，只续发未发送段。没有迁移或批量重分类旧 disabled 记录，旧记录不足以区分用户关闭与维护暂停。

未来生成的日报费用段、日报摘要指标和综合周报改为读取现有 CostController 的单一账本快照，不再使用 cost_analytics.db 或其预测字段。每日费用采用计划所在 ET 日，周报为计划日期及前六天；跨午夜补发仍选原计划日。金额读取发生在实际生成时，明确展示统计日期、统计截至时间、已知小计、完整费用是否未知、未决请求、覆盖起点和历史完整性。未初始化、未决请求、上界失效、覆盖不足或读取失败不会显示成完整零费用；账本明确记录的零值仍展示。日报费用段和摘要使用同一份快照，避免在中途模型调用后读到另一份金额。当前读取不是计划时刻的历史快照，其他数据源的历史恢复仍未实现；已经缓存的报告内容和摘要保持不变。

另用屏障复现 stop 等待旧任务取消期间并发 start 导致新任务丢失引用的缺陷；局部生命周期锁串行化启停，等待所属旧任务结束后才允许新任务启动。stop 的调用者被取消时仍等待旧任务清理，并向调用者传播取消。没有新增调度框架。

补跑 Intel 富媒体及更新处理器回归时，先出现两个隔离夹具缺项：明确的更新处理器沙盒 CLI 未复制，以及仓库自带封面未复制。仅补入一个已检查的合成 CLI 与单一公开封面文件，不放开整个 scripts/assets 目录；原 Intel 投递、渲染模块和测试均无源码改动。临时验证补齐资源后 18 项通过；此前失败日志与三文件相对 HEAD 零差异均保留。

第二轮新增反例初次为 17 失败、2 通过，涵盖实际偏好读取、维护恢复、缺目标分类、费用消费者与启停交错；局部修复后的首次组合 71 项通过。额外补充偏好文件消失、调用者取消 stop 和账本不可读回归。随后新增 UTC 输入跨午夜的周报标题反例（1 失败、21 未选），将日报和周报标题也统一为 ET，避免标题与费用统计日不一致。最终专项与相关保障 **158 项通过**，最终完整组合 **610 项通过**（包括 C01 的 452 项、C03/相关 118 项、本轮 22 项与 Intel 补充 18 项；不重复相加）。两次最终源码摘要均为 `1e4da2e1fd8ba743ae9a7cd16b7a3838ac8f46b112620161d809126ed68c9868`。此前同数量的 `d7c361...` 快照早于标题修正，保留为历史证据，不替代最终结果。

相关 Ruff、复制边界 1 项、文档 8 项/22 文档、gitleaks 与 diff 检查通过；主入口重新比对 HEAD 仍为 32 项既有诊断、零新增。第二轮修正尚待独立复核，不提前标为 C03 DONE；本阶段不启动生产服务、不发送真实消息、不激活运行账本。

C03 第二次独立复审接受本地阶段：第六轮输出 36–42 共七份均已读取，当前 74 路径与专项、组合源码摘要匹配；R1/R2/R3、并发启停及 ET 日期补修通过。158 项包含在 610 项组合中。真实自然投递、覆盖切换和长期运行仍未验收。随后进入第七轮 C06 实际绑定鉴权、C05 引导和 C04 安装说明。


## C04–C06 本地实施与验收（第七轮，独立复审通过）

### C06：实例认证与容器边界

API 以实例级不可变上下文保存规范化地址、环境和 token，优先级为显式参数、环境、受限默认。实际 Uvicorn 地址、诊断、HTTP 与 WebSocket 共用此上下文，主入口允许 `API_HOST` 生效。公开地址、production、未知模式及缺上下文拒绝无 token 请求；显式 loopback 开发仍可保留无 token。`localhost` 固定为 `127.0.0.1`，只接受具体 IP 或 localhost，不通过 DNS/Host/代理头判断是否免认证。两个实例创建后环境改变不会污染彼此。

新增实际 ASGI/WS、启动参数与主入口假启动器矩阵：初始 19 项中 16 失败/3 通过；修复后的相关组合 130 项通过，全部包含于最终 709 项。旧测试对已删除全局标记的引用按实例合同更新，未放宽认证规则。

Compose 保持宿主 loopback 发布，容器内绑定 `0.0.0.0`，明确 production，要求 API token 和 Redis 密码，配置只读。现有 data/logs 绑定目录不变；审计只用独立测试卷。镜像继续固定原 Python 摘要，Linux 哈希锁安装，六个源码包使用锁内 setuptools 且关闭构建隔离，防止构建工具绕过哈希锁下载。LLM 六个冻结版本、OpenClaw 固定版本与其他锁不变。

真实 BuildKit 上下文导出曾发现目录例外与嵌套 node_modules 泄入合成秘密；修正默认拒绝白名单及递归排除后，四项容器合同测试通过。实际 Linux 冷启动又暴露 tiktoken 词表首次下载、图片目录不可写和社媒状态接口固定父目录深度问题。现从哈希锁定的 LiteLLM wheel 提取 cl100k 词表，校验 SDK 固定 SHA256 后预置缓存；图片写入 `/app/data/images`，社媒可选技能检查兼容独立 `/app` 布局，缺文件仍报告不存在。macOS 离线运行器也复制并校验同一公开词表到当次临时缓存，避免依赖共享 `/tmp` 的旧缓存。四进程投递 claim 测试保留原互斥断言，冷启动共享上限调整为 60 秒，失败后回收所属子进程。

临时 Colima 0.10.3 / Lima 2.2.0 的官方发布工件经 SHA256 验证；独立 profile、工具目录、配置、socket，无宿主用户目录挂载、无 SSH agent/凭据转发、无默认 Docker context 切换。Docker Desktop 原 daemon 未启动。来宾 Ubuntu 24.04.4 aarch64 使用现有 Rosetta 执行 `linux/amd64` 镜像；实际 Python 为 x86_64 3.12.13，261 个包逐项匹配 Linux 锁，`pip check` 和冷启动实际 API 导入通过。

Linux 最终完整组合 **709 项通过**；保留一条只读 `/app` 无法写 pytest 缓存的警告。先前 15 失败/683 通过/11 错误的运行和导入探针错误均保留。两次导入探针错误包含误列未安装的可选 SDK，不计为产品依赖缺失。最终完整组合早于仅清空示例凭据占位值的镜像更新；最终镜像另行复验源码摘要、冷导入和 API 合同，不把历史镜像 ID 当作最终镜像。

实际 API 探针未运行 multi_main、Gateway、Bot 或调度器。来宾宿主 loopback 请求结果为无 token 401、错误 token 401、正确 token 200；Dockerfile 真实健康命令成功；配置写入以只读文件系统错误拒绝，非 root 可写测试 data/logs。初次探针错误地把仅 internal 的网络用于宿主映射，未就绪结果保留；最终使用任务专用 bridge 并在来宾防火墙拒绝该接口的新出站连接，不更改生产网络。内部网络和端口映射的区别参考 [Docker Compose 网络文档](https://docs.docker.com/compose/how-tos/networking/)。这是 VM 宿主到容器的合同，不是生产服务或 macOS 外部客户端验收。

### C05：首次设置的真实保存与状态

向导现在调用已有 `get_ai_config` / `save_provider` 保存明确的 Gateway Provider、模型、URL、协议和可选密钥，再脱敏回读核对身份。Agent 管理的回退配置保持只读。Rust 在原跨进程锁和原子事务内合并最新内容，保留未提及模型、扩展、费率、别名及 SecretRef，不默认写零费率、不切换主模型。空密钥保留原值，掩码拒绝作为新密钥；Unicode 掩码按字符处理，避免错误切片。只新增配置来源标记，不回传原始秘密。

Zustand 同一存储键成为唯一完成来源；写入及回读成功后才更新内存和导航，失败保留表单。旧标记只兼容读取为未验证。状态区分未完成、保存中/失败、已保存但运行未验证和跳过；跳过不保存未确认密钥，首页保留重新进入入口。功能选择只是界面偏好。同步防重入和卸载检查阻止重复保存及迟到完成。

真实 React 组件浏览器基线复现“保存失败仍完成”（1 失败），修复后 **13 项交互检查通过**，覆盖保存/回读/持久失败、重试、渲染、双击、返回/跳过、卸载、旧密钥和 Agent 回退。另有 **23 项实际 store/helper 测试通过**；Rust 使用临时合成文件运行 **26 项配置事务相关测试通过**，另外 25 项过滤。首次 Rust 编译的命名空间错误以及一次错误筛选导致零测试的输出均保留，不算通过证据。前端类型、lint、生产构建和既有 22 项安全相关测试通过；测试页样式路径修正后再核对真实布局。未安装或启动桌面 App，未调用模型或保存真实配置。

### C04：锁定安装说明与实际重放

README 与 005 改为临时干净验证入口，列出 Python 3.12.x / macOS arm64 与 Linux amd64、Node 22.19+（22.x）或 24.x、npm 10/11；本机实测 Node 22.22.3、npm 10.9.8、Python 3.12.12、Rust 1.93.1，CI 使用 Node 24。验证器在开始安装前拒绝未支持的版本/架构。`make tauri-build` 明确为安装部署动作，与前端构建分开。Compose 命令明确传入部署 env 文件，不假定服务级 env_file 能完成 Compose 插值。

文档中的完整 `--component all --python ... --keep` 已在新的临时目录实际重放：桌面安装/类型/lint/构建/45 项组合测试、runtime 固定版本和 bin 检查、Weixin CLI/语法、macOS Python 哈希安装和一致性检查、C01 的 452 项均通过。随后在该新 Python 环境执行最终 **709 项通过**，7 条 jieba SyntaxWarning 保留。最终 Python 源码摘要为 `2634bd1408a42e0a70877c8807914bc63d171bc7330ba6dad3c2f9d65fe41e43`。已有环境下的 709、专项 130、C03 610 和 C01 452 都是覆盖关系，不重复相加。

环境模板中的凭据占位保持空白。部署准备示例在本地生成认证随机值，以 0600 和排他创建写入新文件，不打印值、不覆盖已有文件；这段文档代码已仅在临时目录实际执行并验证重跑拒绝覆盖。三项安装边界、两项复制/词表边界、一项文档配置生成、八项文档门禁通过。源码 lint、哈希锁校验、gitleaks 和 diff 检查保留各自结果。

C04–C06 的本地证据已通过第七轮独立复审，输出 43–55 共 13 份及当前 99 个路径已核对。Linux Python 安装缺口已补齐，Linux GTK/Rust 七条警告、Weixin 语义及上游测试、CCXT 附带钱包源码问题仍保留；C07–C10 仍在原目标内。费用费率/期初值、投递覆盖起点和真实业务运行没有因安装或 API 探针成功而自动完成。

### C06 配置加载补充

Compose 已注入 `PYTHON_DOTENV_DISABLED=1`：Compose 由宿主读取 0600 配置并注入环境，非 root 容器不必再次读取 root 所有的私有文件。本地启动仍按原路径加载 dotenv，显式环境变量优先。实际 Linux 临时卷复现 PermissionError，修复后通过真实主入口的配置加载语句、Bot 配置导入与 HTTP 401/401/200 探针；6 项配置单测通过。未放宽配置权限。

## C07：观测副本与实际出口

`observability_policy.py` 统一清洗策略，默认仅导出允许的模型/操作标签、计数、延迟和状态。`OPENCLAW_OBSERVABILITY_CONTENT=redacted` 才允许清洗后的正文；非法值退回 metadata 并在状态中标记配置无效。这是指定秘密及 PII 模式过滤，不代表能够匿名化任意自然语言。默认不导出用户/会话标识，也不使用低熵普通哈希代替它们。

清洗以副本执行，限制深度、节点、字符串及压缩正文大小；处理结构化敏感键、Header/Cookie、URL 用户信息/查询参数、私钥、Telegram Token、选定邮箱/电话/银行卡/账户模式。未知对象不调用 repr/str，异常不保留原始消息、堆栈和链。业务输入、输出、历史和异常语义保持原样。

- Langfuse 2.60.10：手工调用、装饰器和 LiteLLM 回调统一进入适配器，在实际 SDK 入队前及最终 HTTP 批次序列化时再次过滤。导出服务器错误回显也先清洗再返回 SDK。替换已知 Langfuse/Langfuse OTEL 回调入口，保留其他回调身份与顺序。已知不支持的写入出口直接拒绝。
- Phoenix/OpenTelemetry：使用私有 Provider 和明确注册的 instrumentor，不自动发现其他出口。在真实 BatchSpanProcessor 入队前和最终 exporter 前重建安全 Span，覆盖资源、事件、链接、状态与 scope。已有未托管 instrumentor 不擅自替换，状态单列实际拥有的入口。
- 实测发现 OpenInference 0.1.34 的流包装会隐藏 SDK 原始流，令缺供应商 usage 的响应错误结算。回归已复现并修正：异步流只记录打开事件并原样返回 SDK 流，最终内容由安全 Langfuse 完成回调处理；不把打开延迟当作完整流时长。完整、缺失/部分 usage、断流、取消、提前关闭及未消费关闭的 12 项联动测试通过。
- 日志：Loguru 文本、JSON、bind/extra、线程名和 stdlib 降级均使用过滤；脱敏器失败输出固定占位符。原有目录 0700、文件与压缩日志 0600 保持。
- 导出 SDK 给出的 token 仅标为 `sdk_reported_unverified`，不自动写成确认费用；OTEL 自动成本字段不导出。只有显式供应商计量来源可作为 Langfuse usage；C01 账本仍独立验证原始计量。

旧实际 Langfuse/OTEL 和 Loguru JSON 出口均复现测试秘密外泄。后续 234 项组合回归通过，包含真实锁定 LiteLLM/OpenAI/httpx、OTLP protobuf 和成本账本；扩展后 C07/C08 边界组合 81 项通过。最终 macOS 组合 894 项通过，但仍观察到 LiteLLM 后台日志清理的一条未 await 警告，未关闭该问题。当前尚未宣称远程观测平台真实运行验收完成。

## C08：手动股票卖出确认与持久状态

接口为 `POST /api/v1/trading/sell/prepare`、`POST /api/v1/trading/sell`、`GET /api/v1/trading/sell/requests/{request_id}`。协议为 `manual-sell-v1`，客户端先生成 UUIDv4；prepare 绑定规范化订单、明确的券商账户、paper/live 环境、TWS 协议版本和已核实股票 conId。数量/价格必须有限且符合订单类型。旧客户端缺少确认合同会被拒绝。

prepare 与 submit 必须有配置好的 API Token（本地开发亦同），并且 `OPENCLAW_MANUAL_TRADING_ENABLED=true`。`IBKR_ACCOUNT` 必须明确且在当前已认证连接的 managed accounts 中；`OPENCLAW_MANUAL_TRADING_ENVIRONMENT` 必须明确匹配。当前仅支持标准 U/DU 股票账户，其他账户类型保持拒绝。端口、桥接类的 Paper 注释和 default-account 均不构成环境证明。[IBKR managed accounts](https://interactivebrokers.github.io/tws-api/managed_accounts.html) 与 [IBKR 纸面账户标识说明](https://www.interactivebrokers.co.jp/en/support/customer-service.php?p=email) 为该验证边界提供依据。

独立 SQLite 默认位于 `packages/clawbot/data/manual-trades/requests.sqlite3`，目录 0700、文件 0600，拒绝符号链接；不混用费用或投递数据库。确认凭据只保存哈希，最长 120 秒；消费确认与取得唯一执行权在同一事务。相同 ID/参数返回已有状态，不同参数冲突，过期与终态保留。已进入 dispatch 的请求不因超时、重启或执行租约到期重发，同账户/合约的未决请求也阻止换新 ID 再卖。

真实券商所有者循环在 placeOrder 前检查权限、作用域与精确参数，持久记录 dispatch 后再次检查，事务不跨网络。锁定 ib_async 会先向客户端发送、再构造 Trade，所以其内部抛错也按可能已生效处理。订单携带稳定 orderRef；查询匹配账户、conId、参数及引用，并保留永久订单身份与成交量。空/失败/冲突快照、单独的数字订单号不能清除未知状态；对账只追加证据，不重新下单。[IBKR Order 字段](https://www.interactivebrokers.com/docs/tws-api/ref/order) 支持引用合同。

前端显示服务器摘要和有效期，提交前只持久保存请求编号。超时/无效响应后查询原请求，重载不恢复凭据或重新提交；submitted、部分成交、全部成交、拒绝、取消和未知分别显示。通知失败与重复请求不会再次调用券商。已有自动交易、持仓数量预留与预算逻辑保留，本轮未启用手动交易开关、未发起真实订单。

旧入口在隔离回归中实际调用了一次假 placeOrder，证明未确认订单可达券商。新实现的 141 项 API/桥接/状态机组合通过；真实 Portfolio/API 包装器的 8 项浏览器交互通过，包含过期、存储失败、超时后重载、部分成交、卸载后返回与双击。TypeScript、状态测试、现有安全回归、lint 和构建通过。最终 macOS 组合验证已完成；Linux 整合证据与独立复审尚待完成。

## 本轮快速收尾与续做入口

2026-09-10 用户因额度将尽要求快速收尾，本轮停止扩展修复和新的 GPT 长评审。原 C01–C10 总目标尚未全部完成。

- 最终 macOS 隔离组合：894 passed / 8 warnings / 75.03 秒；源码摘要 `f1b5a2183d5f32f74830f4a8304f41f081a62136acaa7d5794cd6706a09816c3`。警告为 jieba 的 7 条 SyntaxWarning 和 LiteLLM 的 1 条后台协程未 await 警告。日志：`/tmp/openeverything-audit-20260910/c78-macos-full-first.txt`。
- 前端类型检查、状态测试、lint、构建与现有安全回归均 exit 0；日志：`/tmp/openeverything-audit-20260910/c08-frontend-first.txt`。收尾文档门禁、配置模板检查及 diff 空白检查通过。
- C07/C08 的 Linux 镜像构建成功，但未执行最终 Linux 组合测试；不得把构建成功写成 Linux 验收通过。两项尚未提交第八轮 GPT 独立复审。
- 续做顺序：复核 C07/C08 当前变更及 LiteLLM 警告，完成 Linux 组合与第八轮独立复审；再完成 C02 的 Weixin 语义/上游回归、Linux GTK/Rust 警告及 CCXT 钱包问题；最后推进 C09 隔离恢复/体验/运行验收和 C10 商业及权限材料。
- C01 真实费率、期初状态和运行启用，C03 自然投递与长期覆盖，以及外部依赖均保持未验收。当前更改保存在工作分支中，尚未提交、推送或部署。

临时 API/测试容器与测试网络已移除，来宾防火墙临时规则已删除，浏览器测试服务已停止。本任务 VM 已停止以释放资源；仅保留其任务专用磁盘和可复核日志，供后续 Linux 未闭环项复用，未执行全局清理。

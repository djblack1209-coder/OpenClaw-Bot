# OpenEverything 工程导览

[返回首页](../README.md) · [架构说明](004-architecture.md) · [开发环境](005-quickstart.md)

这份导览面向想快速评审项目的 AI 应用与全栈工程师。建议先体验首页的离线演示，再选择一个主题看代码。演示金额与执行记录均为合成数据；真实行为由实现与测试共同解释。

## 30 秒认识项目

OpenEverything 将 Telegram 入口、Tauri 桌面控制台、Python/FastAPI 业务层和情报调度组合成个人 AI 自动化系统。它关注模型调用之后的工程问题：费用如何约束、重试如何记录、调度如何去重、配置是否真的生效，以及谁能控制服务。

上游 OpenClaw、LiteLLM、FastAPI、Tauri 等提供运行时和框架。本仓库的重点是把它们接成有状态、有边界、可恢复的业务路径。个人贡献范围应结合具体提交说明，不把依赖库、vendor 目录或第三方子模块说成独立开发成果。

## 五分钟阅读路线

| 时间 | 看什么 | 要回答的问题 |
|---|---|---|
| 第 1 分钟 | [交互入口](../apps/openclaw-manager-src/src/App.tsx)与[架构](004-architecture.md) | 桌面、Bot、Gateway 为什么是不同组件？ |
| 第 2 分钟 | [CostLedger](../packages/clawbot/src/core/cost_ledger.py) | 并发请求如何避免同时花掉最后一笔预算？ |
| 第 3 分钟 | [AccountedRouter](../packages/clawbot/src/core/accounted_router.py)与[价格策略](../packages/clawbot/src/core/cost_policy.py) | 调用超时、费用未知、路由重试分别如何记账？ |
| 第 4 分钟 | [调度认领](../packages/clawbot/src/intel/scheduled_cycle.py) | 主机重启后为什么不会直接重发当天简报？ |
| 第 5 分钟 | [回归测试](../packages/clawbot/tests/test_intel_scheduled_cycle.py)与[CI](../.github/workflows/ci.yml) | 哪些失败模式被验证？哪些还需要真实业务验收？ |

## 案例一：一个超时请求，可能仍然产生费用

**问题。** 如果模型请求超时后立即释放预算，下一次重试就可能花掉同一笔钱，而第一次请求已经在供应商处执行。

**实现。** 账本先在 SQLite 写事务中预留金额，记录每次尝试的独立标识；发送后进入 `dispatched`。可计价用量进入 `settled`，未知结果保留 `unknown` 与预算敞口。网络调用不占用数据库事务。

**取舍。** 保守处理未知状态会暂时降低预算可用性，换来不把不确定性隐藏为零成本。SQLite 适合本地部署；当前设计不能直接当作跨机器共享账本。

**代码追问。** [账本测试](../packages/clawbot/tests/test_cost_ledger.py)覆盖跨进程预算竞争、重复结算、幂等冲突和 DST；[路由](../packages/clawbot/src/core/accounted_router.py)说明一次逻辑请求如何产生多次尝试。真实供应商账单核对需要独立证据。

## 案例二：一份早报，两个时区

**问题。** 本机在纽约运行，用户希望新加坡早晨收到简报。直接按主机 08:30 启动，会遇到日期、夏令时和业务窗口不一致；进程重启还可能重复执行。

**实现。** 使用带时区的时钟计算业务日期；在窗口内先获取进程锁，以排他创建方式持久化当日认领，写入并同步后才进入管线。相同日期再次触发直接跳过。

**取舍。** 认领后失败不会自动重放，避免不确定投递导致重复发送。恢复需要检查实际状态。文件锁与认领文件属于本机持久化方案，不是分布式 exactly-once 消息系统。

**代码追问。** [调度测试](../packages/clawbot/tests/test_intel_scheduled_cycle.py)包含夏冬时切换、窗口外跳过、进程退出、并发运行、符号链接防护和跨日投递阻止。

## 案例三：保存成功，为什么不能显示“已经可用”

**问题。** 设置表单写入了配置，但 Provider 可能不可达，运行中的服务也可能仍使用旧状态。把“保存成功”直接显示为“接入完成”会误导用户。

**实现。** 首次引导区分未配置、保存但未验证和已完成状态；桌面通过原生命令控制受管服务，业务 API 保留鉴权。参考 [Onboarding](../apps/openclaw-manager-src/src/components/Onboarding)、[引导测试](../scripts/onboarding.test.mjs)和 [API auth](../packages/clawbot/src/api/auth.py)。

**取舍。** 状态提示更保守，但用户可以明确知道下一步是保存、启动还是实际请求验证。桌面原生流程需要在目标平台继续验收，静态构建不能代替安装后的真实运行。

## 在本地复验

先按[快速开始](005-quickstart.md)准备锁定环境。下列命令选择本导览引用的现有回归测试，不启动真实 Bot 或发送消息：

```bash
# 从仓库根目录执行
node --test scripts/onboarding.test.mjs scripts/news-entrypoints.test.mjs
cd packages/clawbot
.venv312/bin/python -m pytest tests/test_cost_ledger.py tests/test_intel_scheduled_cycle.py -q
```

CI 按对应提交查看。涉及桌面修改时另行运行 lint、build 和相关 Rust 检查。独立远端服务、自然调度回执、真实 Provider 计费与跨平台安装不包含在上述测试结论中。

## 展示时如何准确表达

可以围绕“问题 → 设计选择 → 失败场景 → 验证证据 → 尚存限制”讲解其中一个案例。比罗列集成库更能体现 AI 应用与全栈工程能力。

简历表述可参考下面的结构，但必须按实际个人贡献调整：

> 基于 Python/FastAPI 与 Tauri/React 构建个人 AI 自动化项目，集成 Telegram、模型路由和情报管线；参与费用预留与未知状态处理、按业务日的持久化调度认领及相关回归验证。

不要加入没有测量依据的提效比例、真实用户数、交易收益或可用性承诺。能够现场解释并复现一个失败路径，比未经验证的规模数字更有说服力。

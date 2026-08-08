# 开源轮子调研：闲鱼、社媒、财经与爬虫

> 调研时间: 2026-07-08；闲鱼候选复核: 2026-08-08
> 调研方式: agent-reach GitHub/gh CLI 拉取仓库元数据、README、目录结构和 LICENSE 片段
> 目的: 找出 OpenEverything 可以直接复用的轮子、只适合借鉴的思路、以及暂不建议接入的项目。

## 老板版一句话结论

这些仓库里，**真正能“直接搬进来省开发成本”的不多**。最稳的是：

1. **`mootdx/mootdx`**：通达信行情数据，MIT，适合直接做 A 股数据补充源。
2. **`d60/twikit`**：X/Twitter 内部接口客户端，MIT，适合做只读热点/搜索补充，但不能乱自动互动。
3. **`Evil0ctal/Douyin_TikTok_Download_API`**：Apache-2.0、FastAPI/Docker 化，适合独立跑成“抖音/TikTok/B站解析服务”。

**闲鱼方向已允许采用更重但更好用的助手**：当前选定 [`zhinianboke/xianyu-auto-reply`](https://github.com/zhinianboke/xianyu-auto-reply) 作为独立 AGPL 服务候选，不复制或合并其源码到 OpenEverything。它的产品闭环比继续扩张现有自研模块更完整，但部署必须先满足资源、私网暴露和闲鱼出口风控边界。

**MediaCrawler 很强，但许可证写明非商业学习**，不能直接作为商业功能代码搬进来；可以拿它当“平台适配层设计参考”。

---

## 分级规则

| 等级 | 含义 | 处理方式 |
|---|---|---|
| A 直接可用 | 许可证清晰、维护较活跃、可作为独立依赖/服务接入 | 可以进入短期开发计划 |
| B 借鉴思路 | 功能很有价值，但许可证、风控、维护或架构不适合直接复制 | 只读源码/README，自己实现最小安全版 |
| C 暂不建议 | 已失效、归档、过旧、商业/灰产味重、与当前目标不匹配 | 不接入，只记录风险 |

---

## 闲鱼

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`cv-cat/XianYuApis`](https://github.com/cv-cat/XianYuApis) | **B：重点借鉴** | 闲鱼 WebSocket、HTTP API、签名、消息收发，是我们自动发货/AI 客服最相关的参考。 | README 写 MIT 徽章，但 GitHub 未识别 LICENSE 文件；不要直接复制代码。重点对照我们现有 `xianyu_apis.py`、`xianyu_live.py`，补齐 mtop 发货/状态接口。 |
| [`zhinianboke/xianyu-auto-reply`](https://github.com/zhinianboke/xianyu-auto-reply) | **A/B：独立服务候选** | 截至 2026-08-08 为 6,337 stars，最近 pushed 2026-08-01；FastAPI + React + MySQL + Redis + Playwright，覆盖多账号、自动回复、自动发货和商品发布。最低 2c4G，推荐 4c8G。 | AGPL-3.0，只能作为边界清晰的独立服务部署并履行许可证义务，不能复制合并源码。默认部署安全边界不足，必须先完成下方加固。 |
| [`shaxiu/XianyuAutoAgent`](https://github.com/shaxiu/XianyuAutoAgent) | **B：AI 客服思路借鉴** | 多专家协同、议价、上下文记忆、客服 prompt，很适合后续 AI 智能客服。 | LICENSE 为 GPL-3.0；不直接复制代码。我们只借鉴“客服 Agent 分工”和“议价/售后意图分类”。 |
| [`chinamonarchs/xyxyxy`](https://github.com/chinamonarchs/xyxyxy) | **C：不建议接入** | 有商品监控、过滤、钉钉推送等思路。 | 最后 push 很早，偏抢拍/秒拍/强聊，风控和合规风险高；不适合我们的“稳定售卖 + 售后”路线。 |

### 闲鱼落地建议

当前落地决定：

1. **独立服务，不合并源码**：固定审阅后的 commit，自行构建镜像；禁止 `curl | bash`，也不直接信任可变 latest 镜像。
2. **部署前强制加固**：不使用默认 `admin/admin123`；9000/8089/8090/8091 不得暴露公网，只绑定私网或 loopback，经带认证的反向代理访问；关闭默认远程广告、远程公告和卡片远程基址，使用强随机管理凭据。
3. **资源与出口阻塞**：当前国内 VPS 只有约 13GB 空闲磁盘，源码构建可能突破安全余量；Oracle SGW 约有 88GB 空闲，但海外出口对闲鱼登录与风控不利。因此本轮不真实部署，状态是“候选已选定、部署客观阻塞”，不是完成。
4. **业务安全边界**：即使后续部署，也只处理授权店铺的客服、商品和真实订单；不做抢拍、强聊、批量骚扰，不绕过 CAPTCHA、短信、实体手机号或平台风控。

---

## 微博

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`dataabc/weiboSpider`](https://github.com/dataabc/weiboSpider) | **B：数据源思路可用** | 成熟微博用户数据爬取，支持文件/数据库输出，适合做 Intel Brief 的“指定账号跟踪”。 | 需要 Cookie；未看到清晰 LICENSE 文件，不直接复制代码。 |
| [`dataabc/weibo-crawler`](https://github.com/dataabc/weibo-crawler) | **B：更适合做外部采集脚本参考** | 支持 Docker/API 服务，免 Cookie 版本思路适合做低风险微博公开数据采集。 | 未看到清晰 LICENSE 文件；建议只借鉴输出 schema 和定时采集设计。 |

### 微博落地建议

先接“公开热榜/RSS/搜索结果”这类低风险源；需要登录 Cookie 的用户主页跟踪放到 P2，并在 Dashboard 标注“登录态需要维护”。

---

## 小红书

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`cv-cat/Spider_XHS`](https://github.com/cv-cat/Spider_XHS) | **B：重点借鉴** | 小红书全域运营、API/签名/采集结构，对后续小红书内容池有参考价值。 | README 有 MIT 徽章但未看到 LICENSE 文件；平台风控高，不直接复制。 |
| [`JoeanAmier/XHS-Downloader`](https://github.com/JoeanAmier/XHS-Downloader) | **B：下载/解析思路可借鉴** | 链接提取、作品采集、下载能力成熟。 | LICENSE 为 GPL-3.0；不能直接并入商业闭源代码。可借鉴 CLI/任务结构。 |
| [`submato/xhscrawl`](https://github.com/submato/xhscrawl) | **B/C：只作参考** | 小红书 xs 逆向、API 服务思路。 | 目录含 `node_modules`，许可证不清，维护和合规风险较高。 |

### 小红书落地建议

不要先做自动发布/自动评论。先做“热点采集 → 生成待审草稿 → 老板确认”的只读闭环。

---

## 抖音 / TikTok

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`Evil0ctal/Douyin_TikTok_Download_API`](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | **A：可独立接入** | Apache-2.0，FastAPI/Docker，支持抖音/TikTok/B站解析下载；适合跑成独立服务，给 Intel Brief 和内容素材池用。 | 不建议把代码复制进主项目；用 Docker/HTTP 调用隔离风险。 |
| [`cv-cat/DouYin_Spider`](https://github.com/cv-cat/DouYin_Spider) | **B：协议/直播监听思路借鉴** | 抖音 API、私信、直播间监听，适合了解能力边界。 | 许可证不清，平台风控高，不直接接入生产。 |
| [`VideoData/DY-Data`](https://github.com/VideoData/DY-Data) | **C：不建议接入** | 有很多抖音 API 方向描述。 | 最后代码很旧，偏资料/联系导向，不适合当前工程直接复用。 |

---

## 知乎

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`LiuRoy/zhihu_spider`](https://github.com/LiuRoy/zhihu_spider) | **C：暂不接入** | Scrapy/Mongo/RabbitMQ 的老式爬虫结构可作历史参考。 | 最后 push 2016，知乎页面和登录机制已变化，维护成本大。 |
| [`atonasting/zhihuspider`](https://github.com/atonasting/zhihuspider) | **C：不接入** | 无。 | 仓库已归档，README 明确代码已失效。 |

### 知乎落地建议

不要搬这些老爬虫。用公开热榜/搜索页/API 或 MediaCrawler 的结构思路自己做轻量只读适配。

---

## 财经数据：同花顺 / 通达信 / 雪球

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`mootdx/mootdx`](https://github.com/mootdx/mootdx) | **A：可直接接入** | MIT，PyPI、文档、测试都比较完整；可作为通达信行情读取补充源。 | 适合 P1 接入 Intel Brief/A 股数据源。 |
| [`panghu11033/thsdk`](https://github.com/panghu11033/thsdk) | **B：先试用验证** | 同花顺 Python SDK，支持行情/K线/板块等，接口形式适合接入。 | 未看到清晰 LICENSE；先本地 PoC，不直接复制。 |
| [`decaywood/XueQiuSuperSpider`](https://github.com/decaywood/XueQiuSuperSpider) | **C：不建议直接接入** | 老雪球抓取思路。 | Java 项目、较老、README 提到反爬问题；当前可用性和维护成本不划算。 |

---

## X / Instagram / 微信公众号

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`d60/twikit`](https://github.com/d60/twikit) | **A：可谨慎接入** | MIT，PyPI，适合做 X/Twitter 搜索、只读热点、账号内容读取。 | 登录态/风控仍需小心；禁止自动关注、批量评论、骚扰式互动。 |
| [`sc1341/InstagramOSINT`](https://github.com/sc1341/InstagramOSINT) | **C：不接入** | 只适合 OSINT 查询。 | 已归档；隐私/合规风险较高，和当前业务目标弱相关。 |
| [`bowenpay/wechat-spider`](https://github.com/bowenpay/wechat-spider) | **C：不接入** | 历史微信公众号爬虫。 | README 明确搜狗微信能力下线后项目废弃；Python2 时代项目。 |

---

## 综合爬虫框架

| 项目 | 判断 | 可用价值 | 风险/备注 |
|---|---|---|---|
| [`NanmiCoder/MediaCrawler`](https://github.com/NanmiCoder/MediaCrawler) | **B：强烈借鉴，不直接商用复制** | 覆盖小红书、抖音、快手、B站、微博、贴吧、知乎等，平台适配结构非常值得参考。 | LICENSE 是非商业学习许可；不能直接作为商业功能搬进 OpenEverything。可以学习目录结构、登录态管理、平台抽象和存储层。 |

---

## 推荐接入路线

### P0：服务当前“闲鱼售卖闭环”

1. 对照 `XianYuApis` / `xianyu-auto-reply`，补一个**真实数字订单号 mtop 虚拟发货实验**。
2. 自动发货策略保持：**接口确认发货优先，页面按钮兜底**。
3. AI 客服先做“只回答常见问题 + 不承诺退款/效果 + 敏感问题交给老板”。

### P1：增强每日简报数据源

1. `mootdx` 接入 A 股行情/板块补充。
2. `twikit` 接入 X/Twitter 只读热点补充。
3. `Douyin_TikTok_Download_API` 作为独立 Docker 服务接入抖音/TikTok/B站素材解析。
4. 微博、小红书先做只读采集，不做自动互动。

### P2：统一采集适配层

参考 MediaCrawler 设计一个自己的轻量接口：

```text
平台适配器 → 标准化文章/视频/评论/热榜对象 → 风险过滤 → Intel Brief/社媒草稿/运营看板
```

这样以后换源不会改业务代码，只换适配器。

---

## 明确不做的事

- 不做抢拍、秒拍、强聊、批量私信、批量评论。
- 不把 GPL/AGPL/非商业许可证代码直接复制进生产项目。
- 不绕过验证码或平台风控。
- 不把登录 Cookie、API Key、卡密写入日志或报告。

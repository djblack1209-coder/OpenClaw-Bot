# 微信笔笔省领券 + Worldmonitor 情报集成 — 设计规格

> 日期: 2026-04-06 | 状态: 已确认

---

## 一、微信笔笔省每日领券

### 目标
每天自动领取"微信支付提现笔笔省"小程序中的免费提现券(365天有效期)，免除微信提现手续费。

### 技术方案: mitmproxy 抓包 + API 直调

#### 核心发现
GitHub 项目 `whether1/txbbs-WxMiniProgramScript` 已验证：领券本质上是一个 HTTP POST 请求，不需要操作界面。

#### API 规格
- **URL**: `https://discount.wxpapp.wechatpay.cn/txbbs-mall/coupon/deliveryfreewithdrawalcoupon`
- **Method**: POST
- **Body**: `{}`
- **认证**: `session-token` 请求头 (从微信客户端流量中嗅探)

#### 完整请求头
```
session-token: <从mitmproxy截获>
X-Track-Id: T<32位大写UUID>
X-Appid: wxdb3c0e388702f785
X-Page: pages/gift/index
X-Module-Name: mmpaytxbbsmp
xweb_xhr: 1
Content-Type: application/json
Referer: https://servicewechat.com/wxdb3c0e388702f785/92/page-frame.html
```

#### 工作流程
```
每天 08:30 定时触发
  1. networksetup 设置 Mac 系统代理 → 127.0.0.1:8080
  2. 启动 mitmdump 监听, addon 截获 session-token
  3. open "weixin://launchapplet/?app_id=wxdb3c0e388702f785" 打开小程序
  4. 等待 5-10 秒, addon 从流量中提取 token
  5. httpx POST 领券 API
  6. 恢复系统代理, 关闭 mitmdump
  7. 通知 Telegram 结果
```

#### 成功判断
```python
if "face_value" in resp_text:  # 领券成功
if "已在其它微信领取" in resp_text:  # 已领过
if errcode != 0:  # 失败, 需重试
```

#### 重试策略
- 最多重试 3 次, 每次重新打开小程序获取新 token
- 每次重试间隔 5 秒

### 新增文件
- `src/execution/wechat_coupon.py` — 领券自动化核心模块
- `scripts/mitm_token_addon.py` — mitmproxy addon 脚本

### 命令入口
- `/coupon` — 手动触发领券
- 中文触发词: "领券"、"笔笔省"、"领优惠券"、"提现券"

### 前置条件
- mitmproxy 已安装 (`pip install mitmproxy`)
- mitmproxy CA 证书已安装到 macOS 钥匙串
- macOS 微信已登录

---

## 二、Worldmonitor 情报系统集成

### 目标
集成 Worldmonitor (koala73/worldmonitor) 的全球情报数据到现有新闻系统，通过 Telegram Bot 交互式菜单查看行业/地区新闻速递。

### 技术方案: API 对接

#### 数据源
Worldmonitor 公开 API (worldmonitor.app)，435+ 新闻源，15 个分类。

#### 分类映射

| 我们的分类 | Worldmonitor API | 中文名 |
|-----------|-----------------|--------|
| finance | /api/market/, /api/economic/ | 金融经济 |
| military | /api/military/, /api/conflict/ | 军事安全 |
| tech | /api/news/ (tech filter) | 科技网络 |
| energy | /api/eia/ | 能源气候 |
| cyber | /api/cyber/ | 网络安全 |
| natural | /api/natural/, /api/climate/ | 自然灾害 |
| geopolitics | /api/intelligence/ | 地缘政治 |

#### 地区映射

| 地区代码 | 显示名 | 涵盖国家/地区 |
|---------|--------|-------------|
| north_america | 北美 | US, CA |
| europe | 欧洲 | EU, UK, DE, FR |
| asia_pacific | 亚太 | CN, JP, KR, AU, IN |
| middle_east | 中东 | IL, IR, SA, SY |
| global | 全球 | 不过滤地区 |

### 新增文件
- `src/tools/worldmonitor_client.py` — API 客户端 (httpx + 缓存 + 降级)
- `src/bot/cmd_intel_mixin.py` — 情报命令 Mixin

### 命令入口
- `/intel` — 情报主菜单 (按钮式交互)
- `/intel <分类>` — 直接查看某类情报 (如 `/intel 金融`)
- 中文触发词: "情报"、"世界新闻"、"全球新闻"、"行业新闻"、"地缘政治"、"军事动态"、"网络安全新闻"
- 现有 `/news` 增加 Worldmonitor 全球情报板块

### 菜单交互设计
```
/intel → 显示按钮菜单:
  行业: [金融经济] [军事安全] [科技网络] [能源气候] [网络安全] [自然灾害] [地缘政治]
  地区: [北美] [欧洲] [亚太] [中东] [全球]
  [每日情报简报]

点击按钮 → 拉取对应新闻 → LLM 生成中文摘要 → 发送
```

### 缓存策略
- 10 分钟内存缓存 (避免重复 API 调用)
- API 不可用时降级到现有 RSS 源

### 降级链
```
Worldmonitor API → 现有 news_fetcher RSS → Google News RSS → Bing 搜索
```

---

## 三、共享改动

| 文件 | 改动内容 |
|------|---------|
| `src/bot/multi_bot.py` | 新增 IntelCommandsMixin + 注册 /coupon, /intel 命令 |
| `src/bot/chinese_nlp_mixin.py` | 新增领券+情报中文触发词 |
| `src/execution/scheduler.py` | 新增领券定时任务 (08:30) |
| `src/news_fetcher.py` | generate_morning_report() 增加 Worldmonitor 全球情报板块 |
| `requirements.txt` | 新增 mitmproxy 依赖 |

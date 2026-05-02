# 错误翻译 + 用户沟通参考表

> 最后更新: 2026-04-01
> 本文件从 AGENTS.md §15 外移，AI 按需查阅

---

## 错误翻译三步法

```
第一步：一句话说清楚（什么坏了）— 用功能名，不用技术术语
第二步：一句话说原因（为什么坏了）— 用类比解释
第三步：一句话说方案（怎么修）— 告知处理方式，不需用户操作
```

## 常见错误标准翻译

| 技术错误 | 用户听到的应该是 |
|----------|-----------------|
| `ModuleNotFoundError` | 「缺少一个工具包，我装一下就好」 |
| `ConnectionRefusedError` / `ConnectionTimeout` | 「连不上某个服务，可能是网络问题，我重试一下」 |
| `FileNotFoundError` | 「有个文件找不到了，我检查一下路径」 |
| `PermissionError` | 「系统不让我动这个文件，需要调整一下权限」 |
| `KeyError` / `AttributeError` | 「程序内部取数据的时候找错了位置，我修一下」 |
| `TypeError` / `ValueError` | 「有个数据的格式不对，相当于把身份证号填到了手机号的格子里」 |
| `JSONDecodeError` | 「收到了一段看不懂的数据，格式乱了，我处理一下」 |
| `HTTPError 401/403` | 「登录凭证过期或无权限，相当于门卡刷不开了」 |
| `HTTPError 429` | 「请求太频繁被限速了，相当于高速公路堵车，我等一会儿再试」 |
| `HTTPError 500/502/503` | 「对方的服务器出了问题（不是咱们的问题），等一会儿应该就好」 |
| `MemoryError` / `OOM` | 「程序占用的内存太多了，相当于桌子太小放不下这么多文件」 |
| `TimeoutError` | 「等了太久没等到回应，相当于打电话一直没人接，我重试一下」 |
| `sqlite3.OperationalError: database is locked` | 「数据库正忙，相当于有人在用这个文件，我等一下再试」 |
| `telegram.error.BadRequest` | 「发消息时格式不对，Telegram 拒收了，我调整一下」 |
| `telegram.error.NetworkError` | 「连不上 Telegram 服务器，可能需要检查网络」 |
| `openai.RateLimitError` / `litellm.RateLimitError` | 「AI 接口调用太频繁了，需要等一会儿或者换一个」 |
| `openai.AuthenticationError` | 「AI 接口的密钥失效了，需要换一个新的」 |
| `AssertionError` (测试失败) | 「有个自动检查没通过，我看看是什么问题」 |

## 禁止术语清单

以下术语**禁止直接对用户使用**，必须替换为括号内的说法：

| 禁用术语 | 替换为 |
|----------|--------|
| Traceback / Stack trace | 「错误详情」或不提 |
| Exception / 异常 | 「出了个问题」 |
| Debug / 调试 | 「排查问题」 |
| Compile / 编译 | 「把代码转换成能运行的程序」 |
| Dependency / 依赖 | 「需要用到的工具包」 |
| Runtime / 运行时 | 「程序运行的时候」 |
| Middleware / 中间件 | 「中间处理环节」 |
| API | 「接口」或「服务的入口」 |
| Token (认证) | 「登录凭证」或「密钥」 |
| Token (LLM) | 「字数」或「用量」 |
| Callback / 回调 | 「自动触发的后续操作」 |
| Async / 异步 | 「后台同时处理」 |
| Cache / 缓存 | 「临时记忆」或「暂存」 |
| Refactor / 重构 | 「内部整理优化」 |
| Deploy / 部署 | 「把程序装到服务器上运行」 |
| Endpoint | 「接口地址」 |
| Webhook | 「自动通知地址」 |
| Environment Variable | 「配置项」 |
| Container / Docker | 「独立运行的小环境」 |
| ORM | 「数据库操作工具」 |
| Schema | 「数据格式定义」 |
| CI/CD | 「自动测试和上线流程」 |

## 区分原则

- **对用户说话** → 必须遵守本表，翻译所有术语
- **AI 内部文档** (CHANGELOG, HEALTH.md, 代码注释) → 可以使用技术术语

# JIYU AI 生图与 MCP 小白教程

> 日期: 2026-08-08
> 适用对象: 不会写代码，但会使用 JIYU AI、CC Switch 和 AI 编程助手的用户
> 当前状态: 教程已就绪；站内两个生图分组上线前不要创建或购买生图 Key

## 先说结论

文本模型和生图模型不是同一个接口。Claude 端点用于 Messages，ChatGPT 端点用于 OpenAI 兼容文本接口；生图要调用：

```text
https://jiyu.245334.xyz/v1/images/generations
```

CC Switch 的本地路由能在常见文本协议之间转换，但不会自动把一句普通聊天变成“调用生图接口”。最稳妥的做法是另建一个生图专用 Key，再用一个本地 MCP 把生图接口包装成 AI 能调用的 `generate_image` 工具。

## 你需要准备什么

1. 已安装 CC Switch。
2. 站内“API 密钥”页面已经出现 `JIYU 生图 · 渠道A` 或 `JIYU 生图 · 渠道B`。
3. 单独创建一个生图 Key。不要复用日常文本 Key，也不要把 Key 发到聊天、截图或代码仓库。
4. 电脑已安装 Python 3.10 以上和 `uv`，或者让 AI 编程助手代为检查安装。

如果站内还没有两个生图分组，到这里就停止。不要选择文本分组假装生图，也不要在旧的失效 MCP 配置里粘贴新 Key。

## MCP 应该做什么

一个合格的 JIYU 生图 MCP 只需要暴露一个工具：

```text
generate_image(prompt, model, size, quality, output_format)
```

它收到 AI 的工具调用后：

1. 从本机安全存储读取生图 Key。
2. 向 JIYU 的 `/v1/images/generations` 发送请求。
3. 检查 HTTP 状态、响应类型和图片大小。
4. 把返回的图片作为 MCP 图片内容交回 AI。

MCP 不应输出 Key，不应把完整 base64 图片写日志，也不应允许用户临时改成任意外部网址。

## 在 CC Switch 中连接

MCP 安装好后，在 CC Switch 顶部进入“MCP”并新增自定义服务器：

| 字段 | 填写内容 |
|---|---|
| 类型 | `stdio` |
| 名称 | `JIYU AI 生图` |
| 命令 | AI 为你安装后给出的绝对命令路径 |
| 参数 | 使用安装器给出的固定参数，不要追加 Key |
| 环境变量 | 由安装器从系统钥匙串或本机安全环境读取 |

然后按需开启 Claude、Codex、Gemini、OpenCode 或 Hermes。重新启动对应客户端后，问 AI“列出你可用的 MCP 工具”，应该能看到 `generate_image`。

## 可直接复制给 AI 的提示词

把下面整段交给 Codex、Claude Code 或其他能操作你电脑的 AI。不要把真实 Key 填进提示词；让 AI 在执行到凭据步骤时使用系统安全输入框或钥匙串。

```text
请在我的电脑上安装一个名为 JIYU AI 生图的本地 stdio MCP，并接入 CC Switch。要求：

1. 使用官方 Model Context Protocol Python SDK 2.x 和 Python 3.10+，使用 uv 创建隔离环境并固定依赖版本。
2. MCP 只提供 generate_image 工具，参数为 prompt、model、size、quality、output_format。
3. API 根地址固定为 https://jiyu.245334.xyz/v1，请求路径固定为 /images/generations，不允许调用者覆盖主机名或关闭 HTTPS 校验。
4. 生图 API Key 必须单独使用。执行到这里时让我通过隐藏输入或 macOS 钥匙串提供，禁止在聊天、终端历史、源码、配置文件、日志、截图或测试夹具中输出明文。
5. stdio 的 stdout 只能写 MCP JSON-RPC；普通日志写 stderr，并对 Authorization、Key、Token、Cookie 和图片 base64 脱敏。
6. 设置 120 秒总超时、20 MiB 最大响应、一次有限重试；拒绝重定向到非 JIYU 域名、私网地址和非图片响应。
7. 返回 MCP ImageContent；失败时返回小白能读懂的错误，不泄露内部上游品牌、域名或凭据。
8. 在 CC Switch 新增自定义 stdio MCP“JIYU AI 生图”，同步到已安装的 Claude、Codex、OpenCode；不要修改其他 Provider 或 MCP。
9. 删除或停用指向不存在脚本的旧生图 MCP 条目，但先备份其不含 env 的结构，禁止输出旧环境变量值。
10. 只做三项验证：MCP tools/list、一次不带 Key 的失败关闭测试、一次由我确认费用后的真实单图测试。不要跑大批量测试，不要连续生图。
11. 完成后告诉我：安装路径、CC Switch 中的显示名称、如何停用、三项验证结果。不要显示任何 Key。
```

## 怎么确认真的成功

- CC Switch 的 MCP 列表中显示 `JIYU AI 生图`，开启的客户端同步成功。
- AI 能列出 `generate_image`，缺少 Key 时明确失败，不会偷偷使用文本 Key。
- 经你确认费用后只生成一张测试图；站内使用记录能看到图片模型、尺寸、渠道和费用。
- 关闭 MCP 后，AI 不再看到该工具；日常 Claude/ChatGPT 文本调用不受影响。

## 常见问题

**为什么要单独 Key？** 生图通常单次费用高于文本请求。独立 Key 可以单独限额、停用和审计，泄漏时不会连带日常文本调用。

**为什么不直接依赖旧生图 MCP？** 当前本机旧条目指向的启动脚本已经不存在，继续填 Key 也无法启动，而且无法审计其历史实现。

**为什么不直接安装网上的任意生图 MCP？** 调研到的多供应商项目可以作为实现参考，但活跃度和审计证据不足。生产配置优先使用官方 MCP SDK，固定 JIYU 域名，并让 Key 留在本机安全存储。

## 参考资料

- [CC Switch 本地路由服务](https://ccswitch.co/docs/proxy-service.html)
- [CC Switch MCP 管理](https://ccswitch.co/docs/extensions-mcp.html)
- [MCP 官方：构建服务器](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP 官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenAI 兼容 Images API 参考](https://platform.openai.com/docs/api-reference/images/create)


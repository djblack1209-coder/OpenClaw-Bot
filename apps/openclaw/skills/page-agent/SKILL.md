---
name: page-agent
description: Alibaba 开源的网页 GUI Agent，用自然语言直接控制浏览器界面，一行代码集成。替代复杂的 Playwright 脚本。
metadata: {"openclaw":{"emoji":"🌐"}}
---

# Page-Agent 浏览器 GUI 代理

阿里巴巴开源的网页内 GUI 代理，用自然语言控制浏览器界面。

## 核心优势

- 自然语言指令替代 CSS 选择器和 XPath
- 一行代码集成到现有项目
- 理解页面语义，不依赖 DOM 结构
- 比 Playwright 脚本更鲁棒（页面改版不会轻易失效）

## 安装

```bash
pip install page-agent
```

## 与 OpenClaw Bot 集成

### 替代当前 Playwright 社交发布

当前方式（Playwright 脚本，易碎）:
```javascript
await page.click('#post-button');
await page.fill('textarea.content', text);
await page.click('button[type="submit"]');
```

Page-Agent 方式（自然语言，鲁棒）:
```python
from page_agent import PageAgent

agent = PageAgent(page)
await agent.act("点击发布按钮")
await agent.act("在内容框中输入: " + text)
await agent.act("点击提交")
```

### 集成到社交发布流程

```python
# tools/social-browser-adapter 升级
from page_agent import PageAgent

async def publish_to_x(content):
    agent = PageAgent(browser_page)
    await agent.act("点击撰写推文按钮")
    await agent.act(f"输入推文内容: {content}")
    await agent.act("点击发布按钮")
    return await agent.act("确认推文已发布成功")

async def publish_to_xhs(content, images):
    agent = PageAgent(browser_page)
    await agent.act("点击发布笔记")
    for img in images:
        await agent.act(f"上传图片: {img}")
    await agent.act(f"输入笔记内容: {content}")
    await agent.act("点击发布")
```

### 集成到闲鱼自动化

```python
async def reply_xianyu_customer(message):
    agent = PageAgent(browser_page)
    await agent.act(f"在聊天输入框中输入: {message}")
    await agent.act("点击发送按钮")
```

## 使用场景

1. **社交媒体发布** — 替代 `social-browser-adapter.mjs` 中的 Playwright 硬编码
2. **闲鱼操作** — 替代 WebSocket 方式的备用方案
3. **网页数据采集** — 替代 `crawl4ai` 的部分场景
4. **任意网页交互** — Boss 说"帮我在 xxx 网站上做 yyy"

## 触发条件

- Boss 说 "page-agent"、"自然语言控制浏览器"、"网页操作"
- 需要浏览器自动化但 Playwright 脚本太脆弱时
- 社交发布流程中 DOM 选择器失效时自动降级

## 与现有工具的关系

| 工具 | 适用场景 | 优势 |
|------|---------|------|
| Playwright (当前) | 结构稳定的页面 | 速度快、精确 |
| Page-Agent (新增) | 页面结构不稳定 | 鲁棒、自然语言 |
| crawl4ai | 数据采集 | 专注提取 |

建议: Playwright 作为主路径，Page-Agent 作为降级方案和新页面的快速原型。

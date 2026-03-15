---
name: crawl4ai
description: "AI-friendly web crawling and content extraction via Crawl4AI. Use when: (1) need to scrape web pages for AI consumption, (2) extract structured data from websites, (3) convert web content to clean Markdown, (4) build RAG knowledge bases from web sources. Preferred over basic fetch when pages have JS rendering or complex layouts."
---

# Crawl4AI — AI 智能网页爬取

开源 AI 友好爬虫，将网页内容转换为干净的 Markdown/JSON，适合 RAG 和 AI 消费。

## Requirements

```bash
pip install crawl4ai
crawl4ai-setup  # 安装浏览器（首次）
```

## Quick Usage

### 基础爬取（转 Markdown）

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

async def crawl(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=CrawlerRunConfig())
        return result.markdown

# asyncio.run(crawl("https://example.com"))
```

### 命令行快速爬取

```bash
python -c "
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
async def main():
    async with AsyncWebCrawler() as c:
        r = await c.arun(url='$URL', config=CrawlerRunConfig())
        print(r.markdown[:3000])
asyncio.run(main())
"
```

### 结构化数据提取

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
import json

schema = {
    "name": "Products",
    "baseSelector": ".product-card",
    "fields": [
        {"name": "title", "selector": "h2", "type": "text"},
        {"name": "price", "selector": ".price", "type": "text"},
        {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
    ]
}

async def extract(url):
    strategy = JsonCssExtractionStrategy(schema)
    config = CrawlerRunConfig(extraction_strategy=strategy)
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        return json.loads(result.extracted_content)
```

## Use Cases

| 场景 | 方法 |
|------|------|
| 网页转 Markdown | 基础爬取，直接用 `result.markdown` |
| 提取商品/文章列表 | JsonCssExtractionStrategy + CSS 选择器 |
| JS 渲染页面 | 默认支持，自动等待页面加载 |
| 批量爬取 | 循环 URL 列表，注意限速 |
| RAG 数据源 | 爬取后切分存入向量数据库 |

## Notes

- 默认使用 headless 浏览器，支持 JS 渲染
- 自动转换为 AI 友好的 Markdown 格式
- 比 requests + BeautifulSoup 更适合现代网页
- 注意遵守目标网站的 robots.txt 和使用条款

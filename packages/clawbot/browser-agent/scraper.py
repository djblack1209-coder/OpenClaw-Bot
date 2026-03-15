"""
直接Playwright脚本 - 不依赖AI判断，直接抓取已知平台的免费额度信息
比AI驱动的browser-use更快更稳定
"""

import asyncio
import json
import logging
from datetime import datetime
from playwright.async_api import async_playwright

logger = logging.getLogger('scraper')


async def scrape_groq() -> dict:
    """直接抓取Groq免费额度信息"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://console.groq.com/docs/rate-limits", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            content = await page.content()
            # 提取表格文本
            tables = await page.query_selector_all("table")
            result_parts = []
            for table in tables:
                text = await table.inner_text()
                result_parts.append(text)
            text_content = await page.inner_text("main") if await page.query_selector("main") else await page.inner_text("body")
            return {
                "success": True,
                "platform": "Groq",
                "url": "https://console.groq.com/docs/rate-limits",
                "result": text_content[:3000],
                "tables": result_parts[:5],
            }
        except Exception as e:
            return {"success": False, "platform": "Groq", "result": str(e)}
        finally:
            await browser.close()


async def scrape_siliconflow() -> dict:
    """抓取硅基流动定价和免费模型信息"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://cloud.siliconflow.cn/pricing", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            text = await page.inner_text("body")
            return {
                "success": True,
                "platform": "硅基流动",
                "url": "https://cloud.siliconflow.cn/pricing",
                "result": text[:3000],
            }
        except Exception as e:
            return {"success": False, "platform": "硅基流动", "result": str(e)}
        finally:
            await browser.close()


async def scrape_google_ai_studio() -> dict:
    """抓取Google AI Studio免费额度"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://ai.google.dev/pricing", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            text = await page.inner_text("body")
            return {
                "success": True,
                "platform": "Google AI Studio",
                "url": "https://ai.google.dev/pricing",
                "result": text[:3000],
            }
        except Exception as e:
            return {"success": False, "platform": "Google AI Studio", "result": str(e)}
        finally:
            await browser.close()


async def scrape_together_ai() -> dict:
    """抓取Together AI定价"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://www.together.ai/pricing", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            text = await page.inner_text("body")
            return {
                "success": True,
                "platform": "Together AI",
                "url": "https://www.together.ai/pricing",
                "result": text[:3000],
            }
        except Exception as e:
            return {"success": False, "platform": "Together AI", "result": str(e)}
        finally:
            await browser.close()


async def scrape_cloudflare_ai() -> dict:
    """抓取Cloudflare Workers AI免费额度"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://developers.cloudflare.com/workers-ai/platform/pricing/", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            text = await page.inner_text("main") if await page.query_selector("main") else await page.inner_text("body")
            return {
                "success": True,
                "platform": "Cloudflare Workers AI",
                "url": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
                "result": text[:3000],
            }
        except Exception as e:
            return {"success": False, "platform": "Cloudflare Workers AI", "result": str(e)}
        finally:
            await browser.close()


async def scrape_huggingface() -> dict:
    """抓取HuggingFace Inference API信息"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://huggingface.co/pricing", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            text = await page.inner_text("body")
            return {
                "success": True,
                "platform": "Hugging Face",
                "url": "https://huggingface.co/pricing",
                "result": text[:3000],
            }
        except Exception as e:
            return {"success": False, "platform": "Hugging Face", "result": str(e)}
        finally:
            await browser.close()


async def scrape_any_url(url: str) -> dict:
    """通用：抓取任意URL的文本内容"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            title = await page.title()
            text = await page.inner_text("main") if await page.query_selector("main") else await page.inner_text("body")
            return {
                "success": True,
                "url": url,
                "title": title,
                "result": text[:5000],
            }
        except Exception as e:
            return {"success": False, "url": url, "result": str(e)}
        finally:
            await browser.close()


# 平台名 -> 抓取函数的映射
SCRAPERS = {
    "groq": scrape_groq,
    "siliconflow": scrape_siliconflow,
    "google_ai_studio": scrape_google_ai_studio,
    "together_ai": scrape_together_ai,
    "cloudflare_ai": scrape_cloudflare_ai,
    "huggingface": scrape_huggingface,
}


async def scrape_platform(platform: str) -> dict:
    """按平台名调用对应的抓取函数"""
    scraper = SCRAPERS.get(platform)
    if not scraper:
        return {"success": False, "result": f"未知平台: {platform}，可用: {list(SCRAPERS.keys())}"}
    return await asyncio.wait_for(scraper(), timeout=60)


async def scrape_all_platforms() -> list:
    """并发抓取所有平台"""
    tasks = [scrape_platform(p) for p in SCRAPERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for r in results:
        if isinstance(r, Exception):
            out.append({"success": False, "result": str(r)})
        else:
            out.append(r)
    return out

"""
ClawBot AI 浏览器代理 v1.0（对标 browser-use 59k⭐）

用 LLM 驱动 Playwright 浏览器，支持：
- 自然语言指令 → 浏览器操作
- 截图 + 视觉理解（通过 vision API）
- 自适应选择器（LLM 分析 DOM 结构）
- 多步骤任务编排
- 反检测 stealth 模式
- 操作历史 + 错误自愈
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ai_browser")

# 截图保存目录
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


class BrowserAction:
    """浏览器操作指令"""
    GOTO = "goto"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    BACK = "back"
    DONE = "done"
    FAIL = "fail"


# 对标 browser-use: LLM 决策的系统提示
BROWSER_SYSTEM_PROMPT = """You are a browser automation agent. You control a real browser via Playwright.

Given the user's goal and the current page state (URL, title, visible text, screenshot), decide the next action.

Available actions (respond with EXACTLY ONE JSON object):
- {"action": "goto", "url": "https://..."}
- {"action": "click", "selector": "css_selector_or_text"}
- {"action": "type", "selector": "css_selector", "text": "content to type"}
- {"action": "scroll", "direction": "down"|"up", "amount": 500}
- {"action": "wait", "seconds": 2}
- {"action": "screenshot"}
- {"action": "extract", "selector": "css_selector", "description": "what to extract"}
- {"action": "back"}
- {"action": "done", "result": "summary of what was accomplished"}
- {"action": "fail", "reason": "why the task cannot be completed"}

Rules:
- Always respond with a single JSON object, no markdown or explanation.
- If you see a cookie banner or popup, dismiss it first.
- If a selector doesn't work, try alternative selectors or text-based matching.
- Maximum 15 steps per task. If stuck, return "fail".
"""


class AIBrowser:
    """AI 驱动的浏览器代理（对标 browser-use）"""

    def __init__(
        self,
        llm_call: Callable,
        headless: bool = True,
        stealth: bool = True,
        max_steps: int = 15,
        screenshot_on_each_step: bool = False,
        viewport: Dict[str, int] = None,
    ):
        """
        Args:
            llm_call: async callable(messages) -> str，调用 LLM 的函数
            headless: 是否无头模式
            stealth: 是否启用反检测
            max_steps: 单任务最大步数
            screenshot_on_each_step: 是否每步截图
            viewport: 浏览器视口大小
        """
        self.llm_call = llm_call
        self.headless = headless
        self.stealth = stealth
        self.max_steps = max_steps
        self.screenshot_on_each_step = screenshot_on_each_step
        self.viewport = viewport or {"width": 1280, "height": 720}
        self._browser = None
        self._page = None
        self._history: List[Dict] = []

    async def _ensure_browser(self):
        """懒初始化浏览器"""
        if self._page:
            return
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"] if self.stealth else []
        self._browser = await self._pw.chromium.launch(
            headless=self.headless, args=launch_args,
        )
        context_opts = {
            "viewport": self.viewport,
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        }
        if self.stealth:
            context_opts["java_script_enabled"] = True
        ctx = await self._browser.new_context(**context_opts)
        # 对标 browser-use: stealth 脚本注入
        if self.stealth:
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)
        self._page = await ctx.new_page()
        self._page.set_default_timeout(15000)

    async def _get_page_state(self, include_screenshot: bool = False) -> Dict[str, Any]:
        """获取当前页面状态（对标 browser-use 的 DOM 观察）"""
        page = self._page
        state = {
            "url": page.url,
            "title": await page.title(),
        }
        # 提取可见文本（截断到 3000 字符）
        try:
            text = await page.evaluate("""() => {
                const sel = document.querySelector('main') || document.querySelector('article') || document.body;
                return sel ? sel.innerText.substring(0, 3000) : '';
            }""")
            state["visible_text"] = text
        except Exception:
            state["visible_text"] = ""

        # 提取可交互元素（对标 browser-use 的元素标注）
        try:
            elements = await page.evaluate("""() => {
                const items = [];
                const els = document.querySelectorAll('a, button, input, select, textarea, [role="button"], [onclick]');
                for (let i = 0; i < Math.min(els.length, 30); i++) {
                    const el = els[i];
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    items.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').substring(0, 80),
                        type: el.type || '',
                        href: el.href || '',
                        id: el.id || '',
                        class: el.className ? el.className.substring(0, 60) : '',
                    });
                }
                return items;
            }""")
            state["interactive_elements"] = elements
        except Exception:
            state["interactive_elements"] = []

        if include_screenshot:
            try:
                screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
                state["screenshot_b64"] = base64.b64encode(screenshot_bytes).decode()
            except Exception:
                pass

        return state

    async def _execute_action(self, action: Dict) -> str:
        """执行单个浏览器操作"""
        page = self._page
        act = action.get("action", "")
        try:
            if act == BrowserAction.GOTO:
                url = action["url"]
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                return f"Navigated to {url}"

            elif act == BrowserAction.CLICK:
                selector = action["selector"]
                # 对标 browser-use: 先尝试 CSS，再尝试文本匹配
                try:
                    await page.click(selector, timeout=5000)
                except Exception:
                    await page.get_by_text(selector, exact=False).first.click(timeout=5000)
                return f"Clicked: {selector}"

            elif act == BrowserAction.TYPE:
                selector = action["selector"]
                text = action["text"]
                try:
                    await page.fill(selector, text)
                except Exception:
                    el = page.get_by_role("textbox").first
                    await el.fill(text)
                return f"Typed '{text[:30]}...' into {selector}"

            elif act == BrowserAction.SCROLL:
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                delta = amount if direction == "down" else -amount
                await page.mouse.wheel(0, delta)
                await asyncio.sleep(0.5)
                return f"Scrolled {direction} {amount}px"

            elif act == BrowserAction.WAIT:
                secs = min(action.get("seconds", 2), 10)
                await asyncio.sleep(secs)
                return f"Waited {secs}s"

            elif act == BrowserAction.SCREENSHOT:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = SCREENSHOTS_DIR / f"step_{ts}.jpg"
                await page.screenshot(path=str(path), type="jpeg", quality=70)
                return f"Screenshot saved: {path.name}"

            elif act == BrowserAction.EXTRACT:
                selector = action.get("selector", "body")
                try:
                    text = await page.inner_text(selector)
                except Exception:
                    text = await page.inner_text("body")
                return text[:3000]

            elif act == BrowserAction.BACK:
                await page.go_back()
                return "Navigated back"

            elif act == BrowserAction.DONE:
                return action.get("result", "Task completed")

            elif act == BrowserAction.FAIL:
                return f"FAIL: {action.get('reason', 'Unknown')}"

            else:
                return f"Unknown action: {act}"

        except Exception as e:
            return f"Action error ({act}): {str(e)[:200]}"

    def _parse_llm_response(self, text: str) -> Dict:
        """从 LLM 响应中提取 JSON 操作（使用 json_repair 容错）"""
        from json_repair import loads as jloads
        text = text.strip()
        # 尝试直接解析
        try:
            return jloads(text)
        except Exception:
            pass
        # 尝试从 markdown 代码块提取
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return jloads(match.group(1))
            except Exception:
                pass
        # 尝试找第一个 JSON 对象
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            try:
                return jloads(match.group())
            except Exception:
                pass
        return {"action": "fail", "reason": f"Cannot parse LLM response: {text[:100]}"}

    async def run(self, task: str) -> Dict[str, Any]:
        """执行自然语言浏览器任务（对标 browser-use 的 agent.run()）
        
        Args:
            task: 自然语言任务描述，如 "去 Google 搜索 Python 教程"
            
        Returns:
            {"success": bool, "result": str, "steps": int, "history": [...]}
        """
        await self._ensure_browser()
        self._history = []
        start_time = time.time()

        messages = [
            {"role": "system", "content": BROWSER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task}"},
        ]

        for step in range(self.max_steps):
            # 获取页面状态
            include_ss = self.screenshot_on_each_step or step == 0
            state = await self._get_page_state(include_screenshot=include_ss)

            # 构建状态消息
            state_msg = (
                f"Step {step + 1}/{self.max_steps}\n"
                f"URL: {state['url']}\n"
                f"Title: {state['title']}\n"
                f"Visible text (truncated): {state['visible_text'][:1500]}\n"
                f"Interactive elements: {json.dumps(state.get('interactive_elements', [])[:15], ensure_ascii=False)}"
            )
            messages.append({"role": "user", "content": state_msg})

            # 调用 LLM 决策
            try:
                llm_response = await self.llm_call(messages)
            except Exception as e:
                logger.error(f"[AIBrowser] LLM 调用失败: {e}")
                return {"success": False, "result": f"LLM error: {e}",
                        "steps": step + 1, "history": self._history}

            action = self._parse_llm_response(llm_response)
            messages.append({"role": "assistant", "content": json.dumps(action)})

            # 执行操作
            result = await self._execute_action(action)
            self._history.append({
                "step": step + 1, "action": action,
                "result": result[:500], "url": self._page.url,
            })

            logger.info(f"[AIBrowser] Step {step+1}: {action.get('action')} -> {result[:100]}")

            # 检查终止条件
            if action.get("action") == BrowserAction.DONE:
                return {
                    "success": True, "result": result,
                    "steps": step + 1, "history": self._history,
                    "elapsed_s": round(time.time() - start_time, 1),
                }
            if action.get("action") == BrowserAction.FAIL:
                return {
                    "success": False, "result": result,
                    "steps": step + 1, "history": self._history,
                    "elapsed_s": round(time.time() - start_time, 1),
                }

            messages.append({"role": "user", "content": f"Result: {result[:500]}"})

        return {
            "success": False, "result": "Max steps reached",
            "steps": self.max_steps, "history": self._history,
            "elapsed_s": round(time.time() - start_time, 1),
        }

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
        if hasattr(self, '_pw') and self._pw:
            await self._pw.stop()
            self._pw = None


# ---- 便捷函数 ----

async def quick_browse(task: str, llm_call: Callable, headless: bool = True) -> Dict:
    """一行代码执行 AI 浏览器任务"""
    agent = AIBrowser(llm_call=llm_call, headless=headless)
    try:
        return await agent.run(task)
    finally:
        await agent.close()

#!/usr/bin/env python3
"""Gemini Web 图片生成工具 — 通过浏览器自动化访问 gemini.google.com 生成图片"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "images" / "anime"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BROWSER_PROFILE = ROOT / "data" / "browser_profiles" / "openclaw_social"
GEMINI_URL = "https://gemini.google.com/app"


def generate_image(prompt: str, name: str, timeout_ms: int = 120000) -> dict:
    """通过 Gemini Web 生成图片"""
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.new_page()
        try:
            page.goto(GEMINI_URL, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # 找到输入框并输入 prompt
            # Gemini 的输入框可能是 contenteditable div 或 textarea
            input_sel = 'div[contenteditable="true"], textarea[aria-label], .ql-editor, rich-textarea'
            page.wait_for_selector(input_sel, timeout=15000)
            input_el = page.query_selector(input_sel)
            if not input_el:
                return {"success": False, "error": "找不到输入框"}

            # 清空并输入
            input_el.click()
            time.sleep(0.5)
            full_prompt = f"Generate an image: {prompt}"
            input_el.fill(full_prompt)
            time.sleep(0.5)

            # 点击发送按钮
            send_btn = page.query_selector('button[aria-label="Send message"], button[aria-label="发送"], button.send-button, mat-icon[data-mat-icon-name="send"]')
            if send_btn:
                send_btn.click()
            else:
                input_el.press("Enter")

            # 等待图片生成（最多 2 分钟）
            print(f"  等待 Gemini 生成图片...", flush=True)
            img_sel = 'img[src*="blob:"], img[src*="lh3.googleusercontent"], img.generated-image, div.image-container img'
            page.wait_for_selector(img_sel, timeout=timeout_ms)
            time.sleep(5)  # 等待所有图片加载完

            # 收集生成的图片
            images = page.query_selector_all(img_sel)
            saved = []
            for i, img in enumerate(images[:4]):
                src = img.get_attribute("src") or ""
                if not src or "avatar" in src.lower() or "profile" in src.lower():
                    continue
                # 截图方式保存
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = OUTPUT_DIR / f"gemini_{name}_{ts}_{i}.png"
                try:
                    img.screenshot(path=str(filepath))
                    saved.append(str(filepath))
                    print(f"  ✅ 保存: {filepath.name}", flush=True)
                except Exception as e:
                    print(f"  ⚠️ 截图失败: {e}", flush=True)

            if not saved:
                # 尝试下载方式
                for i, img in enumerate(images[:4]):
                    src = img.get_attribute("src") or ""
                    if src.startswith("http"):
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filepath = OUTPUT_DIR / f"gemini_{name}_{ts}_{i}.png"
                        try:
                            resp = page.request.get(src)
                            filepath.write_bytes(resp.body())
                            saved.append(str(filepath))
                            print(f"  ✅ 下载: {filepath.name}", flush=True)
                        except Exception as e:
                            print(f"  ⚠️ 下载失败: {e}", flush=True)

            return {"success": len(saved) > 0, "paths": saved, "count": len(saved)}

        except Exception as e:
            # 保存截图用于调试
            debug_path = OUTPUT_DIR / f"gemini_debug_{name}.png"
            try:
                page.screenshot(path=str(debug_path))
            except:
                pass
            return {"success": False, "error": str(e), "debug_screenshot": str(debug_path)}
        finally:
            page.close()
            browser.close()


def main():
    prompts = {
        "avatar": "anime style portrait of a 21-year-old handsome East Asian male college student, bright eyes, neat black hair, warm smile, white t-shirt gray hoodie, golden hour lighting, Makoto Shinkai anime style, high quality illustration, vibrant colors, upper body",
        "gym": "anime illustration of a fit handsome East Asian male college student in gym, sleeveless top, lean athletic arms, dumbbell, confident smile, modern gym background, warm lighting, clean anime art style",
        "campus": "anime illustration of handsome East Asian male college student on sunny university campus, casual outfit backpack, cherry blossom trees, warm afternoon light, slice of life anime, vibrant colors",
        "night": "anime portrait of cool East Asian male college student at night, black jacket, city lights bokeh, sharp eyes, urban anime aesthetic, cinematic lighting",
        "coding": "anime illustration of East Asian male student coding at desk with laptop, headphones, cozy dorm room, warm lamp, books and coffee, night city window view, lofi anime aesthetic",
    }

    if len(sys.argv) > 1:
        # 只生成指定的
        keys = sys.argv[1:]
    else:
        keys = list(prompts.keys())

    for name in keys:
        if name not in prompts:
            print(f"❌ Unknown: {name}, available: {list(prompts.keys())}")
            continue
        print(f"\n🎨 Generating {name}...", flush=True)
        result = generate_image(prompts[name], name)
        if result["success"]:
            print(f"  ✅ Done: {result['count']} images saved")
        else:
            print(f"  ❌ Failed: {result.get('error', 'unknown')}")


if __name__ == "__main__":
    main()

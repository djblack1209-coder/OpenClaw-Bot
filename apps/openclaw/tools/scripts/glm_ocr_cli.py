#!/usr/bin/env python3
"""
GLM-OCR CLI — Extract text from images/PDFs via Zhipu GLM-OCR API.

Usage:
    python glm_ocr_cli.py --file image.png
    python glm_ocr_cli.py --file-url "https://example.com/doc.png"
    python glm_ocr_cli.py --file doc.pdf --output result.json --pretty

Environment:
    ZHIPU_API_KEY  — Required. Get from https://open.bigmodel.cn
    GLM_OCR_TIMEOUT — Optional. Request timeout in seconds (default: 300)
"""

import argparse
import base64
import json
import mimetypes
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import httpx  # type: ignore[import-untyped]
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    HTTPX_AVAILABLE = False

API_URL = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
MODEL = "glm-ocr"
DEFAULT_TIMEOUT = 300
MAX_RETRIES = 2
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def get_api_key() -> str:
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not key:
        # Try .env file
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("ZHIPU_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        print(
            "Error: ZHIPU_API_KEY not configured.\n"
            "Get your API key at: https://www.bigmodel.cn/usercenter/proj-mgmt/apikeys\n\n"
            "Setup:\n"
            "  export ZHIPU_API_KEY=\"your-key\"\n"
            "  # or add to .env file in working directory",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def get_timeout() -> int:
    t = os.environ.get("GLM_OCR_TIMEOUT", "").strip()
    if t:
        try:
            return int(t)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT


def file_to_data_uri(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        mime = mime_map.get(suffix, "application/octet-stream")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def call_api_httpx(api_key: str, file_input: str, timeout: int) -> dict:
    if not HTTPX_AVAILABLE or httpx is None:
        return {"error": "httpx not available"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "file": file_input,
    }
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout, verify=True) as client:  # type: ignore[union-attr]
                resp = client.post(API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = min(0.5 * (2 ** attempt), 8.0)
                    time.sleep(wait)
                    continue
                last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                if resp.status_code in (401, 403):
                    return {"error": f"Authentication failed ({resp.status_code}). Check your ZHIPU_API_KEY."}
                if resp.status_code == 429:
                    return {"error": "Rate limit exceeded (429). Please wait and try again."}
                return {"error": last_error}
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * (2 ** attempt))
                continue
    return {"error": f"Request failed after {MAX_RETRIES + 1} attempts: {last_error}"}


def call_api_urllib(api_key: str, file_input: str, timeout: int) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"model": MODEL, "file": file_input}).encode("utf-8")
    ctx = ssl.create_default_context()
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            code = e.code
            body = e.read().decode("utf-8", errors="replace")[:500]
            if code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                time.sleep(0.5 * (2 ** attempt))
                continue
            if code in (401, 403):
                return {"error": f"Authentication failed ({code}). Check your ZHIPU_API_KEY."}
            if code == 429:
                return {"error": "Rate limit exceeded (429). Please wait and try again."}
            last_error = f"HTTP {code}: {body}"
            return {"error": last_error}
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * (2 ** attempt))
                continue
    return {"error": f"Request failed after {MAX_RETRIES + 1} attempts: {last_error}"}


def call_api(api_key: str, file_input: str, timeout: int) -> dict:
    if HTTPX_AVAILABLE:
        return call_api_httpx(api_key, file_input, timeout)
    return call_api_urllib(api_key, file_input, timeout)


def parse_response(resp: dict, source: str, source_type: str) -> dict:
    if "error" in resp:
        return {
            "ok": False,
            "text": None,
            "layout_details": None,
            "result": None,
            "error": resp["error"],
            "source": source,
            "source_type": source_type,
        }

    # Extract content from API response
    # The Zhipu layout_parsing API returns md_results + layout_details at top level
    text = (
        resp.get("md_results")
        or resp.get("content")
        or resp.get("output", {}).get("content", "")
        or ""
    )
    layout = (
        resp.get("layout_details")
        or resp.get("document_info")
        or resp.get("output", {}).get("layout_details", [])
        or []
    )

    return {
        "ok": True,
        "text": text,
        "layout_details": layout,
        "result": {"raw_api_response": resp},
        "error": None,
        "source": source,
        "source_type": source_type,
    }


def main():
    parser = argparse.ArgumentParser(
        description="GLM-OCR: Extract text from images/PDFs via Zhipu API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python glm_ocr_cli.py --file image.png\n"
               "  python glm_ocr_cli.py --file-url https://example.com/doc.png\n"
               "  python glm_ocr_cli.py --file doc.pdf --output result.json --pretty",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file-url", help="URL to image/PDF")
    group.add_argument("--file", help="Local file path to image/PDF")
    parser.add_argument("--output", "-o", help="Save result JSON to file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    api_key = get_api_key()
    timeout = get_timeout()

    if args.file:
        file_input = file_to_data_uri(args.file)
        source = str(Path(args.file).resolve())
        source_type = "file"
    else:
        file_input = args.file_url
        source = args.file_url
        source_type = "url"

    result = call_api(api_key, file_input, timeout)
    output = parse_response(result, source, source_type)

    indent = 2 if args.pretty else None
    json_str = json.dumps(output, ensure_ascii=False, indent=indent)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str, encoding="utf-8")
        print(f"Result saved to: {out_path}", file=sys.stderr)

    print(json_str)

    if not output["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

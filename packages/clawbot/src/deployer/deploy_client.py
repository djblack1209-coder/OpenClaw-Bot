#!/usr/bin/env python3
"""OpenClaw 一键部署客户端 — 跨平台 (Win/Mac/Linux)"""
import hashlib
import json
import logging
import os
import platform
import shlex
import subprocess
import sys
import uuid
from getpass import getpass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SERVER_URL = os.getenv("OPENCLAW_DEPLOY_SERVER", "https://deploy.openclaw.ai")
OPENCLAW_HOME = os.path.expanduser("~/.openclaw")
CONFIG_PATH = os.path.join(OPENCLAW_HOME, "openclaw.json")
LICENSE_PATH = os.path.join(OPENCLAW_HOME, ".license")


def machine_id() -> str:
    raw = f"{uuid.getnode()}:{platform.node()}:{platform.system()}:{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def detect_os() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


def print_banner():
    print("""
╔══════════════════════════════════════════╗
║     🦞 OpenClaw 一键部署工具 v1.0       ║
║     支持 Windows / macOS / Linux         ║
╚══════════════════════════════════════════╝
""")


# ---- 1. 登录验证 ----

def login() -> Optional[dict]:
    print("[1/5] 账号验证")
    print("  [1] License Key 激活（推荐）")
    print("  [2] 用户名 + 密码登录")
    auth_mode = input("  选择方式 [1]: ").strip() or "1"

    mid = machine_id()

    if auth_mode == "1":
        license_key = input("  License Key: ").strip()
        if not license_key:
            print("  ❌ License Key 不能为空")
            return None
        try:
            resp = requests.post(f"{SERVER_URL}/api/deploy/auth", json={
                "license_key": license_key, "machine_id": mid,
            }, timeout=15)
            result = resp.json()
        except Exception as e:
            print(f"  ❌ 连接服务器失败: {e}")
            return None
    else:
        username = input("  用户名: ").strip()
        password = getpass("  密码: ").strip()
        if not username or not password:
            print("  ❌ 用户名和密码不能为空")
            return None
        try:
            resp = requests.post(f"{SERVER_URL}/api/deploy/auth", json={
                "username": username, "password": password, "machine_id": mid,
            }, timeout=15)
            result = resp.json()
        except Exception as e:
            print(f"  ❌ 连接服务器失败: {e}")
            return None

    if not result.get("ok"):
        print(f"  ❌ {result.get('message', '验证失败')}")
        return None

    print(f"  ✅ 验证通过 (License: {result['license_key'][:12]}...)")
    # 保存 license 到本地
    os.makedirs(OPENCLAW_HOME, exist_ok=True)
    with open(LICENSE_PATH, "w") as f:
        json.dump({"key": result["license_key"], "machine_id": mid}, f)
    return result


# ---- 2. 环境检测 ----

def check_env() -> dict:
    print("\n[2/5] 环境检测")
    os_type = detect_os()
    print(f"  系统: {platform.system()} {platform.release()} ({platform.machine()})")

    checks = {"os": os_type, "node": False, "npm": False, "python": False, "git": False}

    for cmd, key in [("node --version", "node"), ("npm --version", "npm"),
                     ("python3 --version", "python"), ("git --version", "git")]:
        try:
            r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                checks[key] = True
                ver = r.stdout.strip() or r.stderr.strip()
                print(f"  ✅ {key}: {ver}")
            else:
                print(f"  ❌ {key}: 未安装")
        except FileNotFoundError as e:
            print(f"  ❌ {key}: 未安装")
        except Exception as e:
            logger.debug("[DeployClient] 异常: %s", e)
            print(f"  ❌ {key}: 检测失败")

    return checks


def install_deps(checks: dict):
    """自动安装缺失依赖"""
    os_type = checks["os"]
    missing = [k for k in ("node", "npm", "git") if not checks[k]]
    if not missing:
        print("  所有依赖已就绪")
        return

    print(f"\n  需要安装: {', '.join(missing)}")
    confirm = input("  是否自动安装? (y/n): ").strip().lower()
    if confirm != "y":
        print("  跳过自动安装，请手动安装后重试")
        sys.exit(1)

    if os_type == "macos":
        if "node" in missing or "npm" in missing:
            _run("brew install node")
        if "git" in missing:
            _run("xcode-select --install")
    elif os_type == "linux":
        _run("sudo apt-get update -y")
        if "node" in missing or "npm" in missing:
            _run("curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -")
            _run("sudo apt-get install -y nodejs")
        if "git" in missing:
            _run("sudo apt-get install -y git")
    elif os_type == "windows":
        print("  Windows 请手动安装:")
        if "node" in missing:
            print("    Node.js: https://nodejs.org/")
        if "git" in missing:
            print("    Git: https://git-scm.com/")
        sys.exit(1)


# ---- 3. 配置向导 ----

def config_wizard(license_key: str) -> dict:
    print("\n[3/5] 配置向导")

    print("\n  --- AI 模型方案 ---")
    print("  [1] 自有 API Key（OpenAI/中转 API/DeepSeek 等）")
    print("  [2] 免费模型（OpenRouter 免费额度，无需付费）")
    print("  [3] 本地模型（Phi-4/BitNet，纯 CPU 运行，完全离线）")
    print("  [4] 混合模式（付费 API + 免费 fallback）")
    mode = input("  选择方案 [1]: ").strip() or "1"

    api_base = ""
    api_key = ""
    model_id = ""
    model_name = ""
    openrouter_key = ""
    local_model = ""

    if mode in ("1", "4"):
        print("\n  --- 付费 API 配置 ---")
        print("  支持中转地址（one-api、new-api、硅基流动等）")
        api_base = input("  API Base URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
        api_key = getpass("  API Key: ").strip()
        model_id = input("  模型 ID [gpt-4o]: ").strip() or "gpt-4o"
        model_name = input("  模型显示名 [GPT-4o]: ").strip() or "GPT-4o"

    if mode in ("2", "4"):
        print("\n  --- 免费模型配置 (OpenRouter) ---")
        print("  注册 https://openrouter.ai 获取免费 Key")
        openrouter_key = getpass("  OpenRouter API Key: ").strip()
        if mode == "2":
            api_base = "https://openrouter.ai/api/v1"
            api_key = openrouter_key
            model_id = "deepseek/deepseek-chat:free"
            model_name = "DeepSeek Chat (Free)"

    if mode == "3":
        print("\n  --- 本地模型配置 ---")
        print("  [a] Phi-4-mini（3.8B，推荐，需 4GB 内存）")
        print("  [b] BitNet-b1.58（2B，极轻量，需 2GB 内存）")
        local_choice = input("  选择 [a]: ").strip().lower() or "a"
        if local_choice == "b":
            local_model = "bitnet-b1.58-2B-4T"
            model_name = "BitNet 2B (Local)"
        else:
            local_model = "phi-4-mini"
            model_name = "Phi-4 Mini (Local)"
        api_base = "http://localhost:11434/v1"
        api_key = "local"
        model_id = local_model

    print("\n  --- 聊天渠道 ---")
    tg_token = input("  Telegram Bot Token (留空跳过): ").strip()

    # 构建 providers
    providers = {}
    if mode in ("1", "4") and api_key and api_key != "local":
        providers["custom"] = {
            "baseUrl": api_base, "apiKey": api_key, "api": "openai-completions",
            "models": [{"id": model_id, "name": model_name, "contextWindow": 128000, "maxTokens": 4096}],
        }
    if mode in ("2", "4") and openrouter_key:
        providers["openrouter_free"] = {
            "baseUrl": "https://openrouter.ai/api/v1", "apiKey": openrouter_key, "api": "openai-completions",
            "models": [
                {"id": "deepseek/deepseek-chat:free", "name": "DeepSeek Chat (Free)", "contextWindow": 131072, "maxTokens": 8192},
                {"id": "google/gemma-3-27b-it:free", "name": "Gemma-3 27B (Free)", "contextWindow": 96000, "maxTokens": 8192},
                {"id": "qwen/qwen3-32b:free", "name": "Qwen3 32B (Free)", "contextWindow": 40960, "maxTokens": 8192},
            ],
        }
    if mode == "3":
        providers["local"] = {
            "baseUrl": api_base, "apiKey": "local", "api": "openai-completions",
            "models": [{"id": model_id, "name": model_name, "contextWindow": 8192, "maxTokens": 2048}],
        }

    mid = machine_id()
    try:
        resp = requests.post(f"{SERVER_URL}/api/deploy/config", json={
            "license_key": license_key, "machine_id": mid,
            "api_base_url": api_base, "api_key": api_key,
            "model_id": model_id, "model_name": model_name,
            "telegram_token": tg_token,
            "openrouter_key": openrouter_key,
            "local_model": local_model,
            "mode": mode,
        }, timeout=15)
        result = resp.json()
        if result.get("ok"):
            return result["config"]
    except Exception as e:
        print(f"  ⚠️ 无法从服务器获取配置模板: {e}")

    # Fallback: 本地生成
    config = {
        "version": "2026.3",
        "gateway": {"port": int(os.environ.get("GATEWAY_PORT", "18789"))},
        "models": {"providers": providers},
        "channels": {"telegram": {"enabled": bool(tg_token), "token": tg_token}},
        "skills_bundle": ["self-improving-agent", "openclaw-backup", "find-skills", "crawl4ai"],
    }
    if local_model:
        config["local_model"] = {"engine": "ollama", "model": local_model}
    return config


# ---- 4. 安装 OpenClaw ----

def install_openclaw(config: dict):
    print("\n[4/5] 安装 OpenClaw")

    # 安装 openclaw npm 包
    print("  安装 OpenClaw CLI...")
    _run("npm install -g openclaw@latest")

    # 写入配置
    os.makedirs(OPENCLAW_HOME, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"  ✅ 配置已写入: {CONFIG_PATH}")

    # 本地模型安装（如果选择了本地模型方案）
    local_cfg = config.get("local_model")
    if local_cfg:
        model = local_cfg.get("model", "")
        print(f"\n  --- 安装本地模型: {model} ---")
        # 检查 ollama 是否已安装
        try:
            r = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print(f"  ✅ Ollama: {r.stdout.strip()}")
            else:
                raise FileNotFoundError
        except FileNotFoundError as e:
            print("  安装 Ollama（本地模型运行引擎）...")
            os_type = detect_os()
            if os_type == "macos":
                _run("brew install ollama")
            elif os_type == "linux":
                _run("curl -fsSL https://ollama.com/install.sh | sh")
            else:
                print("  Windows 请手动安装: https://ollama.com/download")

        print(f"  拉取模型 {model}（首次需要下载，请耐心等待）...")
        _run(f"ollama pull {model}")
        print(f"  ✅ 本地模型 {model} 就绪")

    # 安装推荐 Skills
    skills = config.get("skills_bundle", [])
    if skills:
        print(f"\n  安装推荐 Skills ({len(skills)} 个)...")
        for skill in skills:
            print(f"    安装 {skill}...", end=" ")
            try:
                r = subprocess.run(["npx", "clawhub", "install", skill],
                                   capture_output=True, text=True, timeout=60)
                print("✅" if r.returncode == 0 else f"⚠️ {r.stderr[:50]}")
            except Exception as e:
                print(f"⚠️ {e}")


# ---- 5. 启动验证 ----

def verify_install():
    print("\n[5/5] 验证安装 & 生成健康报告")
    report = []
    report.append(f"系统: {platform.system()} {platform.release()} ({platform.machine()})")
    report.append(f"时间: {__import__('datetime').now_et().strftime('%Y-%m-%d %H:%M:%S')}")

    # OpenClaw CLI
    try:
        r = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            ver = r.stdout.strip()
            print(f"  ✅ OpenClaw {ver}")
            report.append(f"OpenClaw: {ver}")
        else:
            print("  ⚠️ openclaw 命令未找到")
            report.append("OpenClaw: 未找到")
    except FileNotFoundError as e:
        print("  ⚠️ openclaw 命令未找到")
        report.append("OpenClaw: 未找到")

    # 配置文件
    if os.path.exists(CONFIG_PATH):
        print(f"  ✅ 配置文件: {CONFIG_PATH}")
        report.append("配置文件: OK")
    else:
        print(f"  ❌ 配置文件不存在")
        report.append("配置文件: 缺失")

    # 模型连通性
    try:
        import json as _json
        with open(CONFIG_PATH) as f:
            cfg = _json.load(f)
        providers = cfg.get("models", {}).get("providers", {})
        for name, prov in providers.items():
            base_url = prov.get("baseUrl", "")
            api_key = prov.get("apiKey", "")
            if not base_url or not api_key:
                continue
            try:
                import requests as _req
                resp = _req.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
                ok = resp.status_code == 200
                status = "连通" if ok else f"HTTP {resp.status_code}"
            except Exception as e:
                status = f"失败: {e}"
            icon = "✅" if "连通" in status else "❌"
            print(f"  {icon} 模型 [{name}]: {status}")
            report.append(f"模型 [{name}]: {status}")
    except Exception as e:
        logger.debug("[DeployClient] 异常: %s", e)

    # Skills
    skills_dir = os.path.join(OPENCLAW_HOME, "skills") if os.path.exists(os.path.join(OPENCLAW_HOME, "skills")) else ""
    if skills_dir:
        skills = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]
        print(f"  ✅ Skills: {len(skills)} 个已安装")
        report.append(f"Skills: {len(skills)} 个 ({', '.join(skills[:5])}{'...' if len(skills) > 5 else ''})")
    else:
        report.append("Skills: 0")

    # 生成报告文件
    report_path = os.path.join(OPENCLAW_HOME, "deploy_report.txt")
    report_text = "═══ OpenClaw 部署健康报告 ═══\n\n" + "\n".join(report) + "\n\n═══ 部署完成 ═══"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n  📋 健康报告已保存: {report_path}")

    print("""
╔══════════════════════════════════════════╗
║  部署完成                                ║
║                                          ║
║  启动: openclaw                          ║
║  配置: openclaw configure                ║
║  状态: openclaw config validate          ║
║  报告: ~/.openclaw/deploy_report.txt     ║
║                                          ║
║  7天内有问题随时联系卖家                   ║
╚══════════════════════════════════════════╝
""")


# ---- 工具 ----

def _run(cmd: str):
    print(f"  $ {cmd}")
    subprocess.run(shlex.split(cmd), check=False)


# ---- 入口 ----

def main():
    print_banner()

    # 1. 登录
    auth = login()
    if not auth:
        sys.exit(1)

    # 2. 环境检测
    checks = check_env()
    install_deps(checks)

    # 3. 配置
    config = config_wizard(auth["license_key"])

    # 4. 安装
    install_openclaw(config)

    # 5. 验证
    verify_install()


if __name__ == "__main__":
    main()

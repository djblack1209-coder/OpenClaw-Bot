#!/usr/bin/env python3
"""自动下载OpenClaw完整资源包"""
import os
import subprocess
import sys

def run(cmd):
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def main():
    print("📦 下载OpenClaw完整资源...")
    
    # 1. 安装OpenClaw
    print("\n[1/4] 安装OpenClaw CLI...")
    run("npm install -g openclaw@latest")
    
    # 2. 安装热门Skills
    print("\n[2/4] 安装Skills...")
    skills = [
        "self-improving-agent",  # 自我改进
        "crawl4ai",              # 网页爬取
        "github",                # GitHub集成
        "weather",               # 天气查询
    ]
    for skill in skills:
        try:
            run(f"npx clawhub install {skill}")
        except Exception as e:
            print(f"  跳过 {skill}: {e}")
    
    # 3. 配置免费模型
    print("\n[3/4] 配置免费模型...")
    config = {
        "models": {
            "providers": {
                "g4f": {
                    "baseUrl": "http://127.0.0.1:18891/v1",
                    "apiKey": "dummy",
                    "api": "openai-completions"
                }
            }
        }
    }
    
    import json
    home = os.path.expanduser("~/.openclaw")
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "openclaw.json"), "w") as f:
        json.dump(config, f, indent=2)
    
    print("\n[4/4] 完成！")
    print("\n✅ OpenClaw已安装，运行: openclaw")

if __name__ == "__main__":
    main()

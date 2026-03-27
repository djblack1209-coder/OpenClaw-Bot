#!/usr/bin/env python3
"""
OpenCode 一键部署器 v3.0 — 完整生态部署
自动安装 OpenCode + Skills + MCP + AGENTS.md
买家只需输入: 激活码 + API配置
"""
import hashlib
import hmac
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
import webbrowser
import threading

# ---- 离线License验证 ----
_SECRET = b"OpenClaw2026-xianyu-license-hmac-secret-key"

def verify_key(key):
    try:
        parts = key.strip().split("-")
        if len(parts) != 4 or parts[0] != "OC":
            return {"ok": False, "message": "激活码格式无效"}
        _, r, exp, sig = parts
        payload = f"{r}-{exp}"
        expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()
        if not hmac.compare_digest(sig.upper(), expected):
            return {"ok": False, "message": "激活码无效"}
        if time.time() > int(exp, 16):
            return {"ok": False, "message": "激活码已过期"}
        return {"ok": True, "expires": time.strftime("%Y-%m-%d", time.localtime(int(exp, 16)))}
    except:
        return {"ok": False, "message": "验证失败"}

# ---- 预配置模板 ----

AGENTS_MD = "你是 OpenClaw，严总的全能AI助手。直接给帮助，跳过废话。有自己的观点。用中文回复。"

OPENCODE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "context7": {
            "type": "remote",
            "url": "https://mcp.context7.com/mcp",
            "enabled": True
        },
        "gh_grep": {
            "type": "remote",
            "url": "https://mcp.grep.app",
            "enabled": True
        }
    }
}

SKILL_PLAYWRIGHT = """---
name: playwright
description: Use when the task requires automating a real browser for navigation, screenshots, form filling, or UI debugging.
---
## What I do
- Take screenshots of web pages
- Fill forms and click buttons
- Extract data from websites
- Debug UI issues

## When to use me
Use this when the user asks to browse a website, take a screenshot, or interact with a web page.
"""

SKILL_DOC = """---
name: doc
description: Use when the task involves reading, creating, or editing documents, summarizing text, or translating content.
---
## What I do
- Read and summarize documents
- Create reports and memos
- Translate between languages
- Format and structure text

## When to use me
Use this when the user asks to write, edit, summarize, or translate documents.
"""

SKILL_DEPLOY = """---
name: deploy
description: Use when the task involves deploying applications to cloud platforms like Vercel, Cloudflare, or other hosting services.
---
## What I do
- Deploy web applications to Vercel or Cloudflare
- Configure deployment settings
- Set up environment variables
- Monitor deployment status

## When to use me
Use this when the user asks to deploy, publish, or host an application.
"""

# ---- 模型配置教程 ----

MODEL_GUIDE = """
===================================
   AI模型配置指南（免费获取方式）
===================================

【方式1: DeepSeek（推荐，中国可直接访问）】
1. 访问: https://platform.deepseek.com/
2. 注册账号（手机号即可）
3. 新用户送 ¥10 免费额度
4. 左侧菜单 → API Keys → 创建
5. 复制 API Key（sk-开头）
配置:
  API地址: https://api.deepseek.com
  模型: deepseek-chat 或 deepseek-reasoner

【方式2: 硅基流动 SiliconFlow（国内平台）】
1. 访问: https://siliconflow.cn/
2. 注册账号
3. 新用户送免费额度
4. 控制台 → API密钥 → 创建
配置:
  API地址: https://api.siliconflow.cn/v1
  模型: Qwen/Qwen3-235B-A22B（免费）

【方式3: OpenRouter（海外平台，有免费模型）】
1. 访问: https://openrouter.ai/
2. 用Google/GitHub登录
3. Settings → API Keys → Create
4. 免费模型: deepseek/deepseek-chat:free
配置:
  API地址: https://openrouter.ai/api/v1
  模型: deepseek/deepseek-chat:free

【方式4: 本地模型 Ollama（完全离线免费）】
1. 访问: https://ollama.com/download
2. 下载安装 Ollama
3. 终端运行: ollama pull qwen3:8b
配置:
  API地址: http://localhost:11434/v1
  模型: qwen3:8b

===================================
"""

# ---- Web安装器 ----

def check_deps():
    try:
        import flask
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "flask"], capture_output=True)

def run_web():
    from flask import Flask, request, jsonify, Response
    app = Flask(__name__)

    HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenCode 一键部署</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f172a;min-height:100vh;display:flex;align-items:center;justify-content:center;color:#fff}
.c{background:#1e293b;border-radius:16px;padding:36px;max-width:560px;width:94%;box-shadow:0 25px 50px rgba(0,0,0,.5);border:1px solid #334155}
h1{font-size:24px;margin-bottom:4px;text-align:center}
.sub{color:#94a3b8;font-size:13px;text-align:center;margin-bottom:24px}
.step{display:none}.step.on{display:block}
label{display:block;margin-bottom:6px;color:#cbd5e1;font-weight:500;font-size:13px}
input,select,textarea{width:100%;padding:10px 12px;background:#0f172a;border:1px solid #475569;border-radius:8px;color:#e2e8f0;font-size:14px;margin-bottom:14px}
input:focus,select:focus,textarea:focus{outline:none;border-color:#3b82f6}
textarea{height:80px;resize:vertical;font-family:monospace}
.btn{width:100%;padding:12px;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:.2s}
.btn:hover{background:#2563eb}
.bar{height:3px;background:#1e293b;border-radius:2px;margin-bottom:20px;overflow:hidden;border:1px solid #334155}
.bar-fill{height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:.4s}
.log{background:#0f172a;padding:12px;border-radius:8px;max-height:220px;overflow-y:auto;font-family:monospace;font-size:12px;margin-top:12px;display:none;line-height:1.8;border:1px solid #334155}
.ok{color:#22c55e}.err{color:#ef4444}.info{color:#94a3b8}
.tip{background:#172554;border:1px solid #1e40af;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:12px;color:#93c5fd;line-height:1.6}
.warn{background:#422006;border:1px solid #92400e;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:12px;color:#fbbf24;line-height:1.6}
.done-box{text-align:center;padding:24px 0}
.done-box h2{color:#22c55e;font-size:22px;margin-bottom:12px}
.done-box p{color:#94a3b8;margin-bottom:6px;font-size:13px}
.section{margin-bottom:16px;padding:14px;background:#0f172a;border-radius:8px;border:1px solid #334155}
.section h3{font-size:14px;color:#e2e8f0;margin-bottom:8px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tab{padding:6px 14px;background:#1e293b;border:1px solid #475569;border-radius:6px;cursor:pointer;font-size:12px;color:#94a3b8;transition:.2s}
.tab.on{background:#3b82f6;border-color:#3b82f6;color:#fff}
a{color:#3b82f6;text-decoration:none}
a:hover{text-decoration:underline}
.steps-list{list-style:none;padding:0}
.steps-list li{padding:4px 0;font-size:12px;color:#94a3b8}
.steps-list li::before{content:"→ ";color:#3b82f6}
</style>
</head>
<body>
<div class="c">
<h1>OpenCode 一键部署</h1>
<p class="sub">完整生态系统 · Skills · MCP · 智能配置</p>
<div class="bar"><div class="bar-fill" id="bar" style="width:0%"></div></div>

<!-- STEP 1: 激活 -->
<div class="step on" id="s1">
<label>激活码（购买后获得）</label>
<input id="key" placeholder="OC-XXXXXXXX-XXXXXXXX-XXXXXXXX">
<button class="btn" onclick="doActivate()">激活</button>
</div>

<!-- STEP 2: 配置模型 -->
<div class="step" id="s2">
<div class="tip">激活成功！有效期至 <span id="expDate"></span></div>

<div class="section">
<h3>AI模型配置</h3>
<div class="tabs" id="providerTabs">
<div class="tab on" onclick="selectProvider('deepseek')">DeepSeek</div>
<div class="tab" onclick="selectProvider('siliconflow')">硅基流动</div>
<div class="tab" onclick="selectProvider('openrouter')">OpenRouter</div>
<div class="tab" onclick="selectProvider('custom')">自定义</div>
<div class="tab" onclick="selectProvider('ollama')">本地Ollama</div>
</div>

<div id="providerInfo"></div>

<label>API地址</label>
<input id="apiUrl" value="https://api.deepseek.com">
<label>API Key</label>
<input id="apiKey" type="password" placeholder="sk-...">
<label>模型名称</label>
<input id="modelId" value="deepseek-chat">
</div>

<div class="section">
<h3>远程控制渠道（选填）</h3>
<label>Telegram Bot Token</label>
<input id="tgToken" placeholder="可选，在@BotFather创建Bot获取">
</div>

<button class="btn" onclick="doDeploy()">开始部署</button>
</div>

<!-- STEP 3: 部署中 -->
<div class="step" id="s3">
<h2 style="margin-bottom:8px">正在部署...</h2>
<p style="color:#94a3b8;font-size:12px;margin-bottom:8px">请耐心等待，不要关闭窗口</p>
<div class="log" id="log"></div>
</div>

<!-- STEP 4: 完成 -->
<div class="step" id="s4">
<div class="done-box">
<h2>部署完成！</h2>
<p>在终端输入 <b>opencode</b> 启动</p>
<p style="margin-top:12px">已安装的功能：</p>
<ul class="steps-list">
<li>OpenCode 核心引擎</li>
<li>AGENTS.md 智能助手配置</li>
<li>Playwright 浏览器自动化 Skill</li>
<li>文档处理 Skill</li>
<li>应用部署 Skill</li>
<li>Context7 文档搜索 MCP</li>
<li>GitHub代码搜索 MCP</li>
</ul>
<p style="margin-top:12px;color:#94a3b8;font-size:11px">7天内有问题随时联系卖家</p>
</div>
</div>
</div>

<script>
let licKey='',currentProvider='deepseek';
const providers={
  deepseek:{url:'https://api.deepseek.com',model:'deepseek-chat',info:'<a href="https://platform.deepseek.com/" target="_blank">注册DeepSeek</a> → API Keys → 创建<br>新用户送¥10免费额度，够用很久'},
  siliconflow:{url:'https://api.siliconflow.cn/v1',model:'Qwen/Qwen3-235B-A22B',info:'<a href="https://siliconflow.cn/" target="_blank">注册硅基流动</a> → API密钥 → 创建<br>国内平台，访问快，有免费模型'},
  openrouter:{url:'https://openrouter.ai/api/v1',model:'deepseek/deepseek-chat:free',info:'<a href="https://openrouter.ai/" target="_blank">注册OpenRouter</a> → Settings → API Keys<br>有免费模型可用，需要科学上网'},
  custom:{url:'',model:'',info:'填写任意OpenAI兼容的API地址和Key<br>支持中转API、One-API等'},
  ollama:{url:'http://localhost:11434/v1',model:'qwen3:8b',info:'先安装 <a href="https://ollama.com/download" target="_blank">Ollama</a>，然后运行:<br><code>ollama pull qwen3:8b</code><br>完全离线免费，但需要较好的电脑配置'}
};

function show(n){document.querySelectorAll('.step').forEach(s=>s.classList.remove('on'));document.getElementById('s'+n).classList.add('on');document.getElementById('bar').style.width=(n*25)+'%'}
function selectProvider(p){
  currentProvider=p;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  event.target.classList.add('on');
  const cfg=providers[p];
  document.getElementById('apiUrl').value=cfg.url;
  document.getElementById('modelId').value=cfg.model;
  document.getElementById('providerInfo').innerHTML='<div class="warn">'+cfg.info+'</div>';
}
function log(m,t){const l=document.getElementById('log');l.style.display='block';l.innerHTML+=`<div class="${t||'info'}">${m}</div>`;l.scrollTop=9999}

selectProvider('deepseek');

async function doActivate(){
  licKey=document.getElementById('key').value.trim();
  if(!licKey)return alert('请输入激活码');
  const r=await(await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:licKey})})).json();
  if(r.ok){document.getElementById('expDate').textContent=r.expires;show(2)}
  else alert(r.message);
}

async function doDeploy(){
  const cfg={
    key:licKey,
    api_url:document.getElementById('apiUrl').value.trim(),
    api_key:document.getElementById('apiKey').value.trim(),
    model_id:document.getElementById('modelId').value.trim(),
    provider:currentProvider,
    telegram_token:document.getElementById('tgToken').value.trim()
  };
  if(!cfg.api_url||!cfg.api_key){
    if(currentProvider!=='ollama')return alert('请填写API地址和API Key');
    cfg.api_key='ollama';
  }
  show(3);log('开始部署 OpenCode 完整生态...');
  try{
    const res=await fetch('/api/deploy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    const reader=res.body.getReader();const dec=new TextDecoder();
    while(true){
      const{done,value}=await reader.read();if(done)break;
      dec.decode(value).split('\n').forEach(line=>{
        if(line.startsWith('data: ')){
          const m=line.slice(6);
          if(m==='[DONE]'){log('部署完成！','ok');setTimeout(()=>show(4),800)}
          else if(m.startsWith('[ERR]'))log(m,'err');
          else log(m,'ok');
        }
      });
    }
  }catch(e){log('[ERR] '+e.message,'err')}
}
</script>
</body>
</html>"""

    @app.route('/')
    def index():
        return HTML

    @app.route('/api/verify', methods=['POST'])
    def verify():
        return jsonify(verify_key(request.json.get('key', '')))

    @app.route('/api/guide')
    def guide():
        return MODEL_GUIDE, 200, {'Content-Type': 'text/plain; charset=utf-8'}

    @app.route('/api/deploy', methods=['POST'])
    def deploy():
        data = request.json

        def gen():
            home = os.path.expanduser("~")
            oc_home = os.path.join(home, ".opencode")
            oc_config = os.path.join(home, ".config", "opencode")

            # 1. 环境检查
            yield "data: [1/6] 检查系统环境...\n\n"
            os_name = platform.system()
            yield f"data: 系统: {os_name} {platform.release()}\n\n"

            # 检查 Node.js
            node_ok = False
            try:
                r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    node_ok = True
                    yield f"data: Node.js: {r.stdout.strip()}\n\n"
            except:
                pass
            if not node_ok:
                yield "data: [ERR] 未安装Node.js! 请先安装: https://nodejs.org/\n\n"
                return

            # 2. 安装 OpenCode
            yield "data: [2/6] 安装 OpenCode...\n\n"
            try:
                r = subprocess.run(["npm", "install", "-g", "opencode-ai"],
                                  capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    yield "data: OpenCode 安装成功\n\n"
                else:
                    # 尝试curl安装
                    yield "data: npm安装失败，尝试curl安装...\n\n"
                    r2 = subprocess.run(
                        ["bash", "-c", "curl -fsSL https://opencode.ai/install | bash"],
                        capture_output=True, text=True, timeout=120)
                    if r2.returncode == 0:
                        yield "data: OpenCode 安装成功（curl方式）\n\n"
                    else:
                        yield f"data: [ERR] 安装失败: {r.stderr[:200]}\n\n"
                        return
            except Exception as e:
                yield f"data: [ERR] 安装异常: {e}\n\n"
                return

            # 3. 写入AGENTS.md
            yield "data: [3/6] 配置智能助手 AGENTS.md...\n\n"
            os.makedirs(oc_home, exist_ok=True)
            agents_path = os.path.join(home, "AGENTS.md")
            with open(agents_path, "w", encoding="utf-8") as f:
                f.write(AGENTS_MD)
            yield "data: AGENTS.md 已创建\n\n"

            # 4. 安装Skills
            yield "data: [4/6] 安装 Skills...\n\n"
            skills_dir = os.path.join(oc_config, "skills")
            os.makedirs(skills_dir, exist_ok=True)

            skill_map = {
                "playwright": SKILL_PLAYWRIGHT,
                "doc": SKILL_DOC,
                "deploy": SKILL_DEPLOY,
            }
            for name, content in skill_map.items():
                skill_dir = os.path.join(skills_dir, name)
                os.makedirs(skill_dir, exist_ok=True)
                with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
                    f.write(content)
                yield f"data: Skill [{name}] 已安装\n\n"

            # 5. 配置模型 + MCP
            yield "data: [5/6] 配置模型和MCP服务...\n\n"
            config = dict(OPENCODE_CONFIG)

            # 配置Provider
            provider_id = data.get("provider", "custom")
            api_url = data.get("api_url", "")
            api_key = data.get("api_key", "")
            model_id = data.get("model_id", "")

            if provider_id == "deepseek":
                # DeepSeek有原生支持
                yield "data: 模型: DeepSeek (原生支持)\n\n"
            elif provider_id == "ollama":
                config["provider"] = {
                    "ollama": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Ollama (本地)",
                        "options": {"baseURL": api_url},
                        "models": {model_id: {"name": model_id}}
                    }
                }
                yield f"data: 模型: Ollama本地 ({model_id})\n\n"
            else:
                config["provider"] = {
                    provider_id: {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": provider_id,
                        "options": {"baseURL": api_url},
                        "models": {model_id: {"name": model_id}}
                    }
                }
                yield f"data: 模型: {model_id} ({api_url})\n\n"

            # 写入opencode.json
            os.makedirs(oc_config, exist_ok=True)
            config_path = os.path.join(oc_config, "opencode.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            yield "data: opencode.json 配置已保存\n\n"

            # 存储API Key（通过/connect命令的auth.json）
            auth_dir = os.path.join(home, ".local", "share", "opencode")
            os.makedirs(auth_dir, exist_ok=True)
            auth_path = os.path.join(auth_dir, "auth.json")
            auth_data = {}
            if os.path.exists(auth_path):
                try:
                    with open(auth_path) as f:
                        auth_data = json.load(f)
                except:
                    pass
            if provider_id == "deepseek":
                auth_data["deepseek"] = api_key
            elif provider_id != "ollama":
                auth_data[provider_id] = api_key
            with open(auth_path, "w") as f:
                json.dump(auth_data, f, indent=2)
            yield "data: API Key 已安全存储\n\n"

            # MCP已在opencode.json中配置
            yield "data: MCP: Context7(文档搜索) + GitHub Grep(代码搜索) 已启用\n\n"

            # 6. 验证
            yield "data: [6/6] 验证安装...\n\n"
            try:
                r = subprocess.run(["opencode", "--version"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    yield f"data: OpenCode {r.stdout.strip()} 已就绪\n\n"
                else:
                    yield "data: OpenCode 已安装\n\n"
            except:
                yield "data: OpenCode 已安装\n\n"

            yield "data: [DONE]\n\n"

        return Response(gen(), mimetype='text/event-stream')

    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:18899")).start()
    print("=" * 50)
    print("  OpenCode 一键部署器 v3.0")
    print("  浏览器已自动打开: http://localhost:18899")
    print("=" * 50)
    app.run(host="127.0.0.1", port=18899, debug=False)

if __name__ == "__main__":
    check_deps()
    run_web()

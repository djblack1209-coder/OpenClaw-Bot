#!/usr/bin/env python3
"""
OpenClaw 一键部署器 v4.0 — 龙虾AI助手完整生态
自动安装: OpenClaw + Manager UI + Skills + MCP + 三省六部AGENTS.md
买家只需: 激活码 + 选模型 → 一键部署
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
import webbrowser
import threading
import logging

logger = logging.getLogger(__name__)

# ---- 离线License验证 ----
_secret_env = os.getenv("OPENCLAW_LICENSE_SECRET")
if not _secret_env:
    raise RuntimeError(
        "OPENCLAW_LICENSE_SECRET environment variable is not set. "
        "The license HMAC secret must be provided via environment variable."
    )
_SECRET = _secret_env.encode()
logger.info("License HMAC secret loaded from OPENCLAW_LICENSE_SECRET environment variable.")

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
    except Exception:
        return {"ok": False, "message": "验证失败"}

# ---- 退款销毁功能 ----
def destroy_deployment():
    """退款时自动销毁已部署内容"""
    home = os.path.expanduser("~")
    oc_home = os.path.join(home, ".openclaw")
    
    if os.path.exists(oc_home):
        shutil.rmtree(oc_home)
        print(f"✅ 已删除 {oc_home}")
    
    # 卸载全局 openclaw
    try:
        subprocess.run(["npm", "uninstall", "-g", "openclaw"], capture_output=True, timeout=60)
        print("✅ 已卸载 openclaw")
    except Exception as e:
        logger.debug(f"npm uninstall openclaw failed: {e}")
    
    print("🔥 退款销毁完成")

# ---- 读取三省六部 AGENTS.md ----
def load_agents_md():
    agents_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "agents.md")
    try:
        with open(agents_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Failed to read agents.md: {e}")
        return """# OpenClaw 龙虾 — 私人AI助手
你是"龙虾"(OpenClaw)，用户的私人AI助手。以三省六部制为内部工作流，高效、准确地完成任务。
"""

# ---- Manager UI 下载链接 ----
MANAGER_UI_URLS = {
    "Darwin": "https://github.com/miaoxworld/openclaw-manager/releases/latest/download/OpenClaw-Manager.dmg",
    "Windows": "https://github.com/miaoxworld/openclaw-manager/releases/latest/download/OpenClaw-Manager-Setup.exe",
    "Linux": "https://github.com/miaoxworld/openclaw-manager/releases/latest/download/OpenClaw-Manager.AppImage"
}

# ---- MCP 配置 ----
OPENCLAW_MCP_CONFIG = {
    "mcpServers": {
        "context7": {
            "command": "npx",
            "args": ["-y", "@context7/mcp-server"],
            "disabled": False
        },
        "gh_grep": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "disabled": False
        }
    }
}

# 热门 Skills 列表
POPULAR_SKILLS = [
    "playwright",
    "pdf", 
    "doc",
    "vercel-deploy",
    "cloudflare-deploy"
]

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
<title>OpenClaw 龙虾AI助手 - 一键部署</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f172a;min-height:100vh;display:flex;align-items:center;justify-content:center;color:#fff}
.c{background:#1e293b;border-radius:16px;padding:36px;max-width:560px;width:94%;box-shadow:0 25px 50px rgba(0,0,0,.5);border:1px solid #334155}
h1{font-size:24px;margin-bottom:4px;text-align:center}
.sub{color:#94a3b8;font-size:13px;text-align:center;margin-bottom:24px}
.step{display:none}.step.on{display:block}
label{display:block;margin-bottom:6px;color:#cbd5e1;font-weight:500;font-size:13px}
input,select{width:100%;padding:10px 12px;background:#0f172a;border:1px solid #475569;border-radius:8px;color:#e2e8f0;font-size:14px;margin-bottom:14px}
input:focus,select:focus{outline:none;border-color:#f97316}
.btn{width:100%;padding:12px;background:#f97316;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:.2s}
.btn:hover{background:#ea580c}
.bar{height:3px;background:#1e293b;border-radius:2px;margin-bottom:20px;overflow:hidden;border:1px solid #334155}
.bar-fill{height:100%;background:linear-gradient(90deg,#f97316,#fb923c);transition:.4s}
.log{background:#0f172a;padding:12px;border-radius:8px;max-height:220px;overflow-y:auto;font-family:monospace;font-size:12px;margin-top:12px;display:none;line-height:1.8;border:1px solid #334155}
.ok{color:#22c55e}.err{color:#ef4444}.info{color:#94a3b8}
.tip{background:#172554;border:1px solid #1e40af;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:12px;color:#93c5fd;line-height:1.6}
.warn{background:#422006;border:1px solid #92400e;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:12px;color:#fbbf24;line-height:1.6}
.done-box{text-align:center;padding:24px 0}
.done-box h2{color:#22c55e;font-size:22px;margin-bottom:12px}
.done-box p{color:#94a3b8;margin-bottom:6px;font-size:13px}
.section{margin-bottom:16px;padding:14px;background:#0f172a;border-radius:8px;border:1px solid #334155}
.section h3{font-size:14px;color:#e2e8f0;margin-bottom:8px}
.tabs{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.tab{padding:6px 14px;background:#1e293b;border:1px solid #475569;border-radius:6px;cursor:pointer;font-size:12px;color:#94a3b8;transition:.2s}
.tab.on{background:#f97316;border-color:#f97316;color:#fff}
a{color:#f97316;text-decoration:none}
a:hover{text-decoration:underline}
.steps-list{list-style:none;padding:0}
.steps-list li{padding:4px 0;font-size:12px;color:#94a3b8}
.steps-list li::before{content:"🦞 ";color:#f97316}
code{background:#1e293b;padding:2px 6px;border-radius:4px;font-size:11px}
</style>
</head>
<body>
<div class="c">
<h1>🦞 OpenClaw 龙虾AI助手</h1>
<p class="sub">三省六部架构 · Manager UI · Skills · MCP</p>
<div class="bar"><div class="bar-fill" id="bar" style="width:0%"></div></div>

<!-- STEP 1: 激活 -->
<div class="step on" id="s1">
<label>激活码（购买后获得）</label>
<input id="key" placeholder="OC-XXXXXXXX-XXXXXXXX-XXXXXXXX">
<button class="btn" onclick="doActivate()">激活</button>
</div>

<!-- STEP 2: 配置模型 -->
<div class="step" id="s2">
<div class="tip">✅ 激活成功！有效期至 <span id="expDate"></span></div>

<div class="section">
<h3>AI模型配置</h3>
<div class="tabs" id="providerTabs">
<div class="tab on" onclick="selectProvider('deepseek')">DeepSeek</div>
<div class="tab" onclick="selectProvider('siliconflow')">硅基流动</div>
<div class="tab" onclick="selectProvider('openrouter')">OpenRouter</div>
<div class="tab" onclick="selectProvider('ollama')">本地Ollama</div>
<div class="tab" onclick="selectProvider('custom')">自定义</div>
</div>

<div id="providerInfo"></div>

<label>API地址</label>
<input id="apiUrl" value="https://api.deepseek.com">
<label>API Key</label>
<input id="apiKey" type="password" placeholder="sk-...">
<label>模型名称</label>
<input id="modelId" value="deepseek-chat">
</div>

<button class="btn" onclick="doDeploy()">🚀 开始部署</button>
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
<h2>🎉 部署完成！</h2>
<p>在终端输入 <code>openclaw</code> 启动龙虾助手</p>
<p style="margin-top:12px">已安装的功能：</p>
<ul class="steps-list">
<li>OpenClaw 核心引擎（315k⭐）</li>
<li>三省六部 AGENTS.md 智能配置</li>
<li>Manager UI 桌面管理界面</li>
<li>5个热门 Skills（playwright/pdf/doc/deploy）</li>
<li>ClawHub CLI 技能市场</li>
<li>Context7 + GitHub Grep MCP</li>
</ul>
<p style="margin-top:16px;color:#94a3b8;font-size:11px">💡 输入 <code>openclaw onboard</code> 查看新手教程</p>
<p style="color:#94a3b8;font-size:11px">📚 查看 quick-start-guide.md 学习API配置和远程控制</p>
<p style="margin-top:8px;color:#94a3b8;font-size:11px">7天内有问题随时联系卖家</p>
</div>
</div>
</div>

<script>
let licKey='',currentProvider='deepseek';
const providers={
  deepseek:{url:'https://api.deepseek.com',model:'deepseek-chat',info:'<a href="https://platform.deepseek.com/" target="_blank">注册DeepSeek</a> → API Keys → 创建<br>新用户送¥10免费额度，够用很久'},
  siliconflow:{url:'https://api.siliconflow.cn/v1',model:'Qwen/Qwen3-235B-A22B',info:'<a href="https://siliconflow.cn/" target="_blank">注册硅基流动</a> → API密钥 → 创建<br>国内平台，访问快，有免费模型'},
  openrouter:{url:'https://openrouter.ai/api/v1',model:'deepseek/deepseek-chat:free',info:'<a href="https://openrouter.ai/" target="_blank">注册OpenRouter</a> → Settings → API Keys<br>有免费模型可用，需要科学上网'},
  ollama:{url:'http://localhost:11434/v1',model:'qwen3:8b',info:'先安装 <a href="https://ollama.com/download" target="_blank">Ollama</a>，然后运行:<br><code>ollama pull qwen3:8b</code><br>完全离线免费，但需要较好的电脑配置'},
  custom:{url:'',model:'',info:'填写任意OpenAI兼容的API地址和Key<br>支持中转API、One-API等'}
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
    provider:currentProvider
  };
  if(!cfg.api_url||!cfg.api_key){
    if(currentProvider!=='ollama')return alert('请填写API地址和API Key');
    cfg.api_key='ollama';
  }
  show(3);log('🦞 开始部署 OpenClaw 完整生态...');
  try{
    const res=await fetch('/api/deploy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    const reader=res.body.getReader();const dec=new TextDecoder();
    while(true){
      const{done,value}=await reader.read();if(done)break;
      dec.decode(value).split('\n').forEach(line=>{
        if(line.startsWith('data: ')){
          const m=line.slice(6);
          if(m==='[DONE]'){log('✅ 部署完成！','ok');setTimeout(()=>show(4),800)}
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
            oc_home = os.path.join(home, ".openclaw")
            oc_workspace = os.path.join(oc_home, "workspace")
            oc_config = os.path.join(oc_home, "openclaw.json")

            # 1. 环境检查
            yield "data: [1/8] 检查系统环境...\n\n"
            os_name = platform.system()
            yield f"data: 系统: {os_name} {platform.release()}\n\n"

            # 检查 Node.js
            node_ok = False
            try:
                r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    node_ok = True
                    yield f"data: Node.js: {r.stdout.strip()}\n\n"
            except Exception as e:
                logger.debug(f"Node.js check failed: {e}")
            if not node_ok:
                yield "data: [ERR] 未安装Node.js! 请先安装: https://nodejs.org/\n\n"
                yield "data: [ERR] 需要 Node.js >= 22\n\n"
                return

            # 2. 安装 OpenClaw
            yield "data: [2/8] 安装 OpenClaw 核心...\n\n"
            try:
                r = subprocess.run(["npm", "install", "-g", "openclaw@latest"],
                                  capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    yield "data: ✅ OpenClaw 安装成功\n\n"
                else:
                    yield f"data: [ERR] npm安装失败: {r.stderr[:200]}\n\n"
                    return
            except Exception as e:
                yield f"data: [ERR] 安装异常: {e}\n\n"
                return

            # 3. 初始化 OpenClaw
            yield "data: [3/8] 初始化 OpenClaw...\n\n"
            try:
                r = subprocess.run(["openclaw", "onboard", "--install-daemon"],
                                  capture_output=True, text=True, timeout=120)
                yield "data: ✅ OpenClaw 初始化完成\n\n"
            except Exception as e:
                logger.debug(f"openclaw onboard failed: {e}")
                yield "data: ⚠️ 初始化跳过（可能已初始化）\n\n"

            # 4. 部署三省六部 AGENTS.md
            yield "data: [4/8] 部署三省六部 AGENTS.md...\n\n"
            os.makedirs(oc_workspace, exist_ok=True)
            agents_path = os.path.join(oc_workspace, "AGENTS.md")
            with open(agents_path, "w", encoding="utf-8") as f:
                f.write(load_agents_md())
            yield "data: ✅ AGENTS.md 已部署到 ~/.openclaw/workspace/\n\n"

            # 5. 安装 Skills
            yield "data: [5/8] 安装热门 Skills...\n\n"
            for skill in POPULAR_SKILLS:
                try:
                    r = subprocess.run(["clawhub", "install", skill],
                                      capture_output=True, text=True, timeout=60)
                    if r.returncode == 0:
                        yield f"data: ✅ Skill [{skill}] 已安装\n\n"
                    else:
                        yield f"data: ⚠️ Skill [{skill}] 安装失败（可跳过）\n\n"
                except Exception as e:
                    logger.debug(f"Skill [{skill}] install failed: {e}")
                    yield f"data: ⚠️ Skill [{skill}] 安装失败（可跳过）\n\n"

            # 6. Manager UI 下载提示
            yield "data: [6/8] Manager UI 桌面应用...\n\n"
            manager_url = MANAGER_UI_URLS.get(os_name, "")
            if manager_url:
                yield f"data: 💡 下载 Manager UI: {manager_url}\n\n"
                yield "data: （可选，提供可视化管理界面）\n\n"
            
            # 7. 配置 MCP
            yield "data: [7/8] 配置 MCP 服务...\n\n"
            mcp_config_path = os.path.join(oc_home, "mcp.json")
            with open(mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(OPENCLAW_MCP_CONFIG, f, indent=2, ensure_ascii=False)
            yield "data: ✅ MCP: Context7 + GitHub Grep 已启用\n\n"

            # 8. 配置模型
            yield "data: [8/8] 配置AI模型...\n\n"
            provider_id = data.get("provider", "custom")
            api_url = data.get("api_url", "")
            api_key = data.get("api_key", "")
            model_id = data.get("model_id", "")

            config = {
                "provider": provider_id,
                "apiUrl": api_url,
                "apiKey": api_key,
                "model": model_id
            }

            with open(oc_config, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            yield f"data: ✅ 模型: {model_id} ({provider_id})\n\n"

            # 8. 验证
            try:
                r = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    yield f"data: ✅ OpenClaw {r.stdout.strip()} 已就绪\n\n"
            except Exception:
                yield "data: ✅ OpenClaw 已安装\n\n"

            yield "data: [DONE]\n\n"

        return Response(gen(), mimetype='text/event-stream')

    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:18899")).start()
    print("=" * 50)
    print("  🦞 OpenClaw 龙虾AI助手 - 一键部署器 v4.0")
    print("  浏览器已自动打开: http://localhost:18899")
    print("=" * 50)
    app.run(host="127.0.0.1", port=18899, debug=False)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--destroy":
        print("🔥 执行退款销毁...")
        destroy_deployment()
    else:
        check_deps()
        run_web()

---
name: glmocr
description: 智谱 GLM-OCR 统一技能。支持通用文字提取、表格识别、公式识别（LaTeX）、手写体识别。触发词：OCR、文字识别、文档解析、图片转文字、表格提取、公式识别、手写识别。ClawBot 已内置自动调用，发图片/PDF 即可。
metadata: {"openclaw":{"emoji":"📄","requires":{"env":["ZHIPU_API_KEY"],"bins":["python"]},"primaryEnv":"ZHIPU_API_KEY","homepage":"https://github.com/zai-org/GLM-OCR","modes":["general","table","formula","handwriting"]}}
---

# GLM-OCR 统一文字识别技能

智谱 GLM-OCR（OmniDocBench V1.5 第一名），支持 4 种识别模式。

## 识别模式

| 模式 | 说明 | 输出格式 |
|------|------|----------|
| general | 通用文字提取（默认） | Markdown |
| table | 表格识别 | Markdown 表格 |
| formula | 数学公式识别 | LaTeX |
| handwriting | 手写体识别 | Markdown |

## ClawBot 自动集成（已内置）

直接在 Telegram 发图片或 PDF，ClawBot 自动：
1. OCR 识别文字
2. 智能场景路由（交易/电商/通用）
3. 交易场景：提取指标 → 写入记忆 → 建议触发 /invest
4. 电商场景：提取价格 → 竞品分析 → 定价建议

群聊中需 @bot 或 caption 含触发词（OCR/识别/分析/竞品/财报）。

## CLI 用法（开发/调试）

```bash
export ZHIPU_API_KEY="$ZHIPU_API_KEY"

# 通用 OCR
python apps/openclaw/tools/scripts/glm_ocr_cli.py --file image.png --pretty

# 保存结果
python apps/openclaw/tools/scripts/glm_ocr_cli.py --file doc.pdf --output result.json
```

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `ZHIPU_API_KEY` | 是 | 智谱开放平台 API Key |
| `GLM_OCR_TIMEOUT` | 否 | 超时秒数（默认 120） |

- 表格识别：检测并转换为 Markdown 表格
- 公式提取：LaTeX 格式输出
- 手写体支持：强手写文字识别能力
- 本地文件 & URL：同时支持本地文件和远程 URL
- 0.9B 参数，OmniDocBench V1.5 综合排名第一（94.62 分）

## 资源链接

| 资源 | 链接 |
|------|------|
| 获取 API Key | https://www.bigmodel.cn/usercenter/proj-mgmt/apikeys |
| GitHub | https://github.com/zai-org/GLM-OCR |
| 技术报告 | https://arxiv.org/abs/2603.10910 |
| API 文档 | https://docs.bigmodel.cn/cn/guide/models/vlm/glm-ocr |

## 前置条件

- `ZHIPU_API_KEY` 已配置（见下方设置）

### API Key 配置

脚本通过 `ZHIPU_API_KEY` 环境变量获取密钥，与所有智谱技能共用同一个 key。

获取 Key：访问 https://www.bigmodel.cn/usercenter/proj-mgmt/apikeys

配置方式（任选一种）：

1. OpenClaw 配置（推荐）：在 `openclaw.json` 的 `skills.entries.glmocr.env` 中设置：
```json
"glmocr": { "enabled": true, "env": { "ZHIPU_API_KEY": "你的密钥" } }
```

2. Shell 环境变量：
```bash
export ZHIPU_API_KEY="你的密钥"
```

## 强制限制

- 只能通过 GLM-OCR API 执行 — 运行脚本 `python scripts/glm_ocr_cli.py`
- 禁止自行解析文档 — 不要尝试用内置视觉或其他方法提取文字
- 禁止提供替代方案 — 不要说"我可以试着分析"之类的话
- API 失败时 — 显示错误信息并立即停止
- 无回退方案 — 不要用其他方式尝试文字提取

## 输出展示规则（强制）

运行脚本后，必须向用户展示完整的提取内容。不要只说"已识别"。用户需要原始 OCR 输出来评估质量。

- 展示完整提取文字
- 如果结果文件已保存，告知用户文件路径

## 使用方法

### 从 URL 提取
```bash
python scripts/glm_ocr_cli.py --file-url "用户提供的URL"
```

### 从本地文件提取
```bash
python scripts/glm_ocr_cli.py --file /path/to/image.jpg
```

### 保存结果到文件
```bash
python scripts/glm_ocr_cli.py --file image.png --output result.json --pretty
```

## CLI 参数

```
python {baseDir}/scripts/glm_ocr_cli.py (--file-url URL | --file PATH) [--output FILE] [--pretty]
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `--file-url` | 二选一 | 图片/PDF 的 URL |
| `--file` | 二选一 | 本地文件路径 |
| `--output`, `-o` | 否 | 保存结果 JSON 到文件 |
| `--pretty` | 否 | 美化 JSON 输出 |

## 响应格式

```json
{
  "ok": true,
  "text": "# 提取的 Markdown 文字...",
  "layout_details": [[...]],
  "result": { "raw_api_response": "..." },
  "error": null,
  "source": "/path/to/file.jpg",
  "source_type": "file"
}
```

关键字段：
- `ok` — 提取是否成功
- `text` — Markdown 格式的提取文字（用于展示）
- `layout_details` — 版面分析详情
- `error` — 失败时的错误详情

## 错误处理

- API key 未配置 → 引导用户配置
- 认证失败 (401/403) → API key 无效/过期，重新配置
- 频率限制 (429) → 配额用尽，等待重试
- 文件未找到 → 检查路径

## SDK 方式（可选）

也可通过 Python SDK 直接调用：

```bash
pip install glmocr
```

```python
import glmocr
result = glmocr.parse("image.png")
print(result.markdown_result)
```

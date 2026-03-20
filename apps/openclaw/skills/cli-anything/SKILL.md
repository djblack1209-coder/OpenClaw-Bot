---
name: cli-anything
description: 一键为任意 GUI 软件生成 CLI 接口，让 AI Agent 能控制传统桌面应用。基于 HKUDS/CLI-Anything 项目。
metadata: {"openclaw":{"emoji":"🔧"}}
---

# CLI-Anything 集成

让任意 GUI 软件变成 Agent 可控的 CLI 工具。

## 核心能力

- 分析软件源码/API，自动生成完整 CLI 接口
- 7 阶段自动化流水线: 分析→设计→实现→测试计划→写测试→文档→发布
- 生成的 CLI 支持 JSON 输出（Agent 友好）+ 人类可读格式
- 内置 REPL 交互模式
- 已验证 13 个应用: GIMP、Blender、LibreOffice、OBS、Audacity 等

## 安装

```bash
git clone https://github.com/HKUDS/CLI-Anything.git
mkdir -p ~/.openclaw/skills/cli-anything
cp CLI-Anything/openclaw-skill/SKILL.md ~/.openclaw/skills/cli-anything/SKILL.md
```

## 使用方式

### 为软件生成 CLI

```
@cli-anything build a CLI for ./gimp
@cli-anything build a CLI for https://github.com/some/app
```

### 细化已有 CLI

```
@cli-anything refine ./gimp "批量处理和滤镜"
```

### 验证 CLI 质量

```
@cli-anything validate ./gimp
```

## 7 阶段流水线

1. 🔍 分析 — 扫描源码，映射 GUI 操作到 API
2. 📐 设计 — 架构命令组、状态模型、输出格式
3. 🔨 实现 — 构建 Click CLI + REPL + JSON 输出 + 撤销/重做
4. 📋 测试计划 — 创建 TEST.md（单元 + E2E）
5. 🧪 写测试 — 实现完整测试套件
6. 📝 文档 — 更新 TEST.md 和结果
7. 📦 发布 — 创建 setup.py，安装到 PATH

## OpenClaw Bot 集成场景

### 控制闲鱼客户端
```bash
# 为闲鱼 Web 版生成 CLI
@cli-anything build a CLI for xianyu web interface

# Agent 可以直接操作
cli-anything-xianyu listing create --title "..." --price 19.9
cli-anything-xianyu order list --status pending --json
```

### 控制浏览器自动化
```bash
# 为 Chrome DevTools Protocol 生成 CLI
@cli-anything build a CLI for chrome-devtools

# 替代 Playwright 脚本
cli-anything-chrome tab new --url "https://x.com"
cli-anything-chrome element click --selector "#post-button"
```

### 控制本地开发工具
```bash
# 为 VS Code 生成 CLI
cli-anything-vscode file open --path ./src/index.ts
cli-anything-vscode terminal run --command "npm test"
```

## 触发条件

- Boss 说 "cli-anything"、"生成 CLI"、"让 Agent 控制 xxx"
- 需要自动化操作某个 GUI 软件时
- `/coding_agent` 任务涉及 GUI 软件交互时

## 注意

- 需要 Python 3.10+
- 目标软件需要已安装在本机
- 生成的 CLI 通过 `pip install -e .` 安装到 PATH
- 每个 CLI 命名为 `cli-anything-<软件名>`

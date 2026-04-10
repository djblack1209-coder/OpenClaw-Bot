# OpenCode 与 CC Switch 模型命名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 OpenCode 与 CC Switch 的配置名和模型显示名，并给 Claude 补齐缺失的官转 MAX 分组。

**Architecture:** 直接修改 OpenCode 的本地 JSON 配置与 CC Switch 的 SQLite 数据库。命名只影响显示层，不改底层模型 ID、baseURL 与密钥，避免破坏已有调用链路。

**Tech Stack:** JSON, SQLite, 本地桌面配置

---

### Task 1: 备份外部配置

**Files:**
- Modify: `~/.config/opencode/opencode.json`
- Modify: `~/.cc-switch/cc-switch.db`

- [ ] **Step 1: 复制 OpenCode 配置备份**

Run: `cp ~/.config/opencode/opencode.json ~/.config/opencode/opencode.json.bak-20260410-rename-models`

- [ ] **Step 2: 复制 CC Switch 数据库备份**

Run: `cp ~/.cc-switch/cc-switch.db ~/.cc-switch/cc-switch.db.bak-20260410-rename-models`

### Task 2: 修改 OpenCode 命名

**Files:**
- Modify: `~/.config/opencode/opencode.json`

- [ ] **Step 1: 更新 provider 显示名称**
- [ ] **Step 2: 更新 provider 内部模型显示名称**
- [ ] **Step 3: 为缺失分组补齐 Claude 对应 provider 配置**
- [ ] **Step 4: 重新读取 JSON 确认结果**

### Task 3: 修改 CC Switch 命名

**Files:**
- Modify: `~/.cc-switch/cc-switch.db`

- [ ] **Step 1: 更新 `providers.name` 中的配置名称**
- [ ] **Step 2: 更新 `providers.settings_config` 中的模型显示名称**
- [ ] **Step 3: 新增 Claude 官转 MAX provider 记录**
- [ ] **Step 4: 新增对应 endpoint 记录**
- [ ] **Step 5: 重新查询数据库确认结果**

### Task 4: 最终核对

**Files:**
- Modify: `~/.config/opencode/opencode.json`
- Modify: `~/.cc-switch/cc-switch.db`

- [ ] **Step 1: 核对 OpenCode provider 列表**
- [ ] **Step 2: 核对 CC Switch Claude 与 OpenCode 列表**
- [ ] **Step 3: 核对新增 Claude 官转 MAX 配置结构**

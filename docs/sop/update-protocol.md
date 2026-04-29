# UPDATE_PROTOCOL — 文档更新触发规则

> 最后更新: 2026-03-22
> 本文件定义：什么变更触发什么文档更新。AI 完成工作后必须按此协议执行。

---

## 触发规则表

| 代码变更类型 | 必须更新的文档 | 说明 |
|-------------|---------------|------|
| 新增/删除 Python 模块 | `docs/registries/MODULE_REGISTRY.md` | 新增条目或标记删除 |
| 新增/修改 Telegram 命令 | `docs/registries/COMMAND_REGISTRY.md` | 更新命令表 |
| 新增/修改回调按钮 | `docs/registries/COMMAND_REGISTRY.md` | 更新回调模式表 |
| 新增中文触发词 | `docs/registries/COMMAND_REGISTRY.md` | 更新触发器表 |
| 新增 pip 依赖 | `docs/registries/DEPENDENCY_MAP.md` | 新增依赖条目 |
| 新增/修改 API Key | `docs/registries/API_POOL_REGISTRY.md` | 更新号池表 |
| 新增/修改 LLM 提供商 | `docs/registries/API_POOL_REGISTRY.md` | 更新限制详情 |
| 架构级改动 | `docs/PROJECT_MAP.md` | 更新相关章节 |
| 发现 Bug | `docs/status/HEALTH.md` | 登记到「活跃问题」 |
| 修复 Bug | `docs/status/HEALTH.md` + `docs/CHANGELOG.md` | 移至「已解决」+ 追加变更日志 |
| 识别技术债 | `docs/status/HEALTH.md` | 记入「技术债务」 |
| **任何代码变更** | `docs/CHANGELOG.md` | **无例外** — 追加结构化条目 |

---

## CHANGELOG 条目格式

```markdown
## [YYYY-MM-DD] 标题

> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`
> 影响模块: `模块A`, `模块B`
> 关联问题: HI-xxx (来自 HEALTH.md)

### 变更内容
- 描述

### 文件变更
- `path/to/file.py` — 说明
```

### 领域标签说明

| 标签 | 含义 | 示例 |
|------|------|------|
| `backend` | Python 后端代码 | bot/, core/, tools/ |
| `frontend` | Tauri/React 桌面端 | openclaw-manager-src/ |
| `ai-pool` | LLM API/模型/Key | litellm_router.py, config/.env |
| `deploy` | 部署/基础设施 | docker-compose, LaunchAgent, systemd |
| `docs` | 文档变更 | docs/ 任何文件 |
| `infra` | 监控/日志/缓存 | monitoring.py, log_config.py |
| `trading` | 交易/投资系统 | auto_trader.py, risk_manager.py |
| `social` | 社媒/闲鱼 | social_*, xianyu/ |
| `xianyu` | 闲鱼专项 | xianyu/ 目录 |

---

## HEALTH.md 条目格式

### 活跃问题

```markdown
| HI-NNN | `领域` | `模块路径` | 一句话描述 | YYYY-MM-DD |
```

- ID: `HI-NNN` 自增编号
- 严重度分区: 🔴 阻塞 → 🟠 重要 → 🟡 一般 → 🔵 低优先
- 领域: 使用 CHANGELOG 相同的领域标签

### 已解决

```markdown
| HI-NNN | `领域` | `模块路径` | 描述 | 解决方案 | YYYY-MM-DD | CHANGELOG引用 |
```

### 技术债务

```markdown
| `领域` | 债务描述 | 根因 | 建议 | 关联 HI-ID |
```

---

## 自检清单 (完工前执行)

- [ ] CHANGELOG.md 已追加条目，格式包含 `领域` + `影响模块` + `关联问题`
- [ ] 受影响的注册表文档已同步更新
- [ ] 发现的 Bug/技术债已登记到 HEALTH.md
- [ ] 修复的 Bug 已从「活跃问题」移至「已解决」
- [ ] 代码通过语法检查

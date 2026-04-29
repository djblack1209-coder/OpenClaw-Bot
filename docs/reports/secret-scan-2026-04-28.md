# Git 密钥泄露全量扫描报告

> 日期: 2026-04-28
> 范围: 当前工作区、本机 ignored 文件、Git 全历史、历史文件名
> 脱敏摘要: `/tmp/openclaw-secret-scan-20260428/SUMMARY.txt`
> 说明: 扫描器原始 JSON/JSONL 可能包含 Raw 字段, 已在汇总结论后删除, 避免形成二次泄露。

## 结论

本次扫描确认: 当前 HEAD 没有新提交的明文密钥, 但公开仓库的 Git 历史中曾提交过敏感配置、设备 token 和数据库文件。已执行 Git 全历史重写, 移除敏感配置、数据库、依赖缓存、构建产物和扫描器噪音样例值；清理后 `gitleaks` 与 `trufflehog` 对 Git 历史均为 0 条命中。

注意: 历史清理只能移除仓库里的痕迹, 不能让已经暴露过的 token 自动失效。历史中出现过或可能同源的密钥仍必须在对应平台轮换。

## 扫描证据

| 工具 | 范围 | 结果 |
|---|---|---|
| `gitleaks 8.30.1` | `git log --all`, 1217 个提交 | 2876 条命中; 排除 `.secrets.baseline` 和翻译记忆库噪声后仍有 73 条需要复核 |
| `trufflehog 3.95.2` | Git 历史 | 11 条未验证命中, 无 verified 命中 |
| `trufflehog 3.95.2` | 当前文件系统, 排除依赖/构建目录 | 123 条未验证命中, 主要集中在本机 `.env` 和浏览器 profile 日志 |
| `detect-secrets 1.5.0` | 本机敏感文件定向扫描 | 命中 `.env`, `packages/clawbot/config/.env`, `packages/clawbot/kiro-gateway/.env`, `.openclaw/devices/paired.json` 等 |
| Git 文件名审计 | `git log --all --name-only` | 历史中出现过 `.openclaw/openclaw.json*`, `.openclaw/memory/*.sqlite`, `clawbot/data/*.db` |
| `gitleaks 8.30.1` | 清理后 Git 全历史 | 0 条命中 |
| `trufflehog 3.95.2` | 清理后 Git 全历史 | 0 verified, 0 unverified |

## 高风险发现

### S-001: Git 历史泄露 OpenClaw 主配置

- 路径: `.openclaw/openclaw.json`, `.openclaw/openclaw.json.bak`, `.openclaw/openclaw.json.bak.1`, `.openclaw/openclaw.json.bak.2`
- 证据: `gitleaks` 在历史提交中命中 `generic-api-key`
- 涉及提交: `6162a73c185446e7ba28f38aa4a86b47487fef94`, `ecbd9b0221ca2f45a2c6b720792bd9e896485968`, `3a376fd1544cff735d764f656e1b4ccc48dfd94a`
- 影响: 配置文件历史中可能含 LLM 中转、模型服务或本地代理密钥。公开仓库场景下必须当作已泄露。

### S-002: Git 历史泄露 OpenClaw 设备配对 token

- 路径: `.openclaw/devices/paired.json`
- 证据: `gitleaks` 命中 2 条 `generic-api-key`
- 涉及提交: `6162a73c185446e7ba28f38aa4a86b47487fef94`
- 影响: 设备/操作者 token 可能被复用, 需要撤销旧设备授权并重新配对。

### S-003: Git 历史曾提交本地数据库

- 路径: `.openclaw/memory/main.sqlite`, `.openclaw/memory/group_free_main.sqlite`, `clawbot/data/history.db`, `clawbot/data/shared_memory.db`
- 证据: Git 历史文件名审计命中, 后续提交仅删除了当前 HEAD 文件
- 影响: 数据库可能包含聊天、记忆、账户、任务或业务记录。即使扫描器未验证出密钥, 公开历史仍有隐私和业务数据风险。

### S-004: 本机 ignored `.env` 含真实 token

- 路径: `.env`, `packages/clawbot/config/.env`, `packages/clawbot/kiro-gateway/.env`
- 证据: `trufflehog filesystem` 命中 Gemini、GitHub、Groq、NVIDIA、HuggingFace、Deepgram、CloudConvert/JWT、Telegram Bot Token 等类型
- 当前 Git 状态: 已被 `.gitignore` 保护, 未进入当前跟踪文件
- 影响: 本机文件风险仍存在; 如果这些 token 曾随历史配置同步到公开仓库, 必须轮换。

### S-005: 本机浏览器 profile 日志残留 Gemini API key

- 路径: `packages/clawbot/data/browser_profiles/openclaw_social/Default/shared_proto_db/000003.log`
- 证据: `trufflehog filesystem` 多次命中 `GoogleGeminiAPIKey`
- 处理: 已删除该本地日志文件
- 影响: 建议轮换对应 Gemini API key, 因为浏览器缓存/日志曾保存过它。

## 已执行清理

- 从 Git 索引移除 `.openclaw/iflow_key_timestamp.json`, 文件保留在本机但不再跟踪。
- 更新 `.gitignore`, 增加 `.openclaw/iflow_key_timestamp.json` 和本地密钥扫描报告目录。
- 删除可重建本地产物约 4.4GB:
  - `apps/openclaw-manager-src/node_modules`
  - `apps/openclaw-manager-src/src-tauri/target`
  - `.openclaw/extensions/openclaw-weixin/node_modules`
  - `packages/clawbot/.venv312`
  - `packages/clawbot/browser-agent/.venv`
  - `packages/clawbot/kiro-gateway/.venv`
  - `packages/clawbot/logs/*.log`
- 删除已确认含密钥痕迹的浏览器本地日志: `packages/clawbot/data/browser_profiles/openclaw_social/Default/shared_proto_db/000003.log`
- 运行 `git gc --prune=now`, 本地 Git 松散对象清零。
- 执行 `git-filter-repo` 全历史重写, 清除历史敏感路径和大体积冗余产物。
- 对文档/测试中的样例 token、样例 Basic Auth URL、样例 PostgreSQL URL 做脱敏, 避免扫描器误判和二次风险。

## 历史重写结果

用户已确认执行破坏性历史清理。已从 Git 历史清除:

- `.openclaw/openclaw.json*`
- `.openclaw/devices/`, `.openclaw/agents/`, `.openclaw/identity/`, `.openclaw/credentials/`, `.openclaw/memory/`
- `.openclaw/iflow_key_timestamp.json`
- `.opencode-state/`
- `.secrets.baseline`
- `.env` / `.env.*`
- sqlite/db 运行数据
- `tools/repair-backup/`
- 旧依赖和构建产物: `node_modules`, `.venv*`, `target`, `dist`
- 历史中命中过真实或疑似密钥的源码路径已移除旧历史, 并在新提交中恢复当前干净版本
- 文档/测试中的固定样例 key、样例 bearer token、样例 Basic Auth URL、样例 PostgreSQL URL

## 必须下一步

1. 立即轮换所有历史配置可能涉及的 token: LLM 中转、Gemini、GitHub Models、Groq、NVIDIA NIM、HuggingFace、Deepgram、CloudConvert/JWT、Telegram Bot、Kiro Gateway、NewAPI 初始 token。
2. 撤销 `.openclaw/devices/paired.json` 里的旧设备/操作者授权, 重新配对。
3. force-push 后让 GitHub 重新跑 secret scanning, 并开启 Push Protection。

# 灾难恢复指南 (Disaster Recovery)

> 最后更新: 2026-04-18

---

## 数据资产清单

### SQLite 数据库（11 个）

| 数据库 | 用途 | 重要性 | 数据量级 |
|--------|------|--------|----------|
| trading.db | 交易日志/持仓/盈亏 | 🔴 关键 | 中 |
| portfolio.db | 投资组合/现金管理 | 🔴 关键 | 小 |
| shared_memory.db | AI 记忆/用户偏好 | 🟠 重要 | 中 |
| history.db | 对话历史 | 🟡 一般 | 大 |
| execution_hub.db | 任务执行记录/提醒/记账 | 🟠 重要 | 中 |
| xianyu_chat.db | 闲鱼客服对话 | 🟠 重要 | 大 |
| feedback.db | 用户反馈 | 🟡 一般 | 小 |
| cost_analytics.db | LLM 成本分析 | 🟡 一般 | 中 |
| deploy_licenses.db | License 发放记录 | 🟠 重要 | 小 |
| novels.db | AI 小说创作 | 🟡 一般 | 小 |
| auto_shipper.db | 闲鱼自动发货规则 | 🟠 重要 | 小 |

### 其他关键数据

| 数据 | 位置 | 重要性 |
|------|------|--------|
| Redis | localhost:6379 | 🟡 会话缓存（可重建） |
| LLM 缓存 | data/llm_cache/ | 🔵 可再生 |
| 配置文件 | config/.env | 🔴 关键（含 API 密钥） |
| 草稿 | ~/.openclaw/drafts.json | 🟡 一般 |
| Cookie | config/.env 中 XIANYU_COOKIES | 🟠 重要 |

---

## 自动备份机制

### 定时任务
- **每日 03:00**: 数据清理（trading 365天/feedback 90天/cost 30天/降价监控 30+90天）
- **每日 04:00**: 全量数据库备份（11 个 SQLite 文件）

### 备份位置
```
packages/clawbot/data/backups/
├── trading_2026-04-18.db
├── portfolio_2026-04-18.db
├── shared_memory_2026-04-18.db
└── ...
```

### 保留策略
- 每日备份：保留 **7 天**
- 每周备份（周日）：保留 **4 周**

### 手动备份
```bash
cd packages/clawbot
.venv312/bin/python scripts/backup_databases.py
```

---

## 恢复步骤

### 场景 1：单个数据库损坏

```bash
# 1. 停止 ClawBot
kill $(pgrep -f multi_main.py)

# 2. 找到最近的备份
ls -la data/backups/ | grep trading

# 3. 替换损坏的数据库
cp data/backups/trading_2026-04-18.db data/trading.db

# 4. 验证完整性
sqlite3 data/trading.db "PRAGMA integrity_check;"

# 5. 重启 ClawBot
.venv312/bin/python multi_main.py &
```

### 场景 2：全部数据库恢复

```bash
# 1. 停止 ClawBot
kill $(pgrep -f multi_main.py)

# 2. 备份当前损坏的数据库（以防万一）
mkdir data/corrupted_$(date +%Y%m%d)
mv data/*.db data/corrupted_$(date +%Y%m%d)/

# 3. 找到最近日期的备份
LATEST=$(ls data/backups/trading_*.db | sort | tail -1 | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}')

# 4. 恢复所有数据库
for db in trading portfolio history shared_memory execution_hub xianyu_chat feedback cost_analytics deploy_licenses novels auto_shipper; do
  if [ -f "data/backups/${db}_${LATEST}.db" ]; then
    cp "data/backups/${db}_${LATEST}.db" "data/${db}.db"
    echo "✅ 已恢复 ${db}.db"
  fi
done

# 5. 重启
.venv312/bin/python multi_main.py &
```

### 场景 3：Mac 主机硬盘损坏 → VPS 接管

1. 确认 VPS failover 已自动接管（heartbeat 超时 120s × 3 次 = 6 分钟后）
2. SSH 登录 VPS 检查 `systemctl status clawbot`
3. VPS 上的数据可能不是最新的 — 最后一次 rsync 的数据
4. 修复 Mac 后，从 VPS 拉回数据：
```bash
rsync -avz user@vps:/path/to/clawbot/data/ packages/clawbot/data/
```
5. 在 Mac 重启 ClawBot，VPS 会自动退让

### 场景 4：config/.env 丢失

1. 从密码管理器/笔记中恢复 API 密钥
2. 必须恢复的密钥清单：
   - `TELEGRAM_BOT_TOKEN` — Telegram @BotFather
   - `MEM0_API_KEY` — mem0 Cloud 控制台
   - `SILICONFLOW_API_KEY` — SiliconFlow 控制台
   - `IBKR_*` — IBKR 交易网关配置
   - `XIANYU_COOKIES` — 需要重新扫码登录
3. 其余密钥参见 `docs/registries/API_POOL_REGISTRY.md`

---

## 预防措施

1. **Git 推送**：所有代码变更及时 push 到 GitHub
2. **密钥管理**：config/.env 不进 Git，建议同步到加密密码管理器
3. **VPS 同步**：rsync 排除 data/ 目录（数据库太大），仅同步代码
4. **监控**：heartbeat 每 60s 一次，3 次失败自动切换到 VPS
5. **定期验证**：每月检查 `data/backups/` 目录确认备份正在运行

---

## 联系方式

遇到无法恢复的问题，检查：
- `docs/status/HEALTH.md` — 已知问题
- `docs/status/HANDOFF.md` — 最近的工作状态
- GitHub Issues — 记录和追踪

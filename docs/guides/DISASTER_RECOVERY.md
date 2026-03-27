# DISASTER_RECOVERY.md — 灾难恢复指南

> 最后更新: 2026-03-24

---

## 恢复目标

| 指标 | 目标 | 说明 |
|------|------|------|
| RPO (Recovery Point Objective) | 24 小时 | 每日 04:00 ET 自动备份 |
| RTO (Recovery Time Objective) | ~30 分钟 | 重启服务 + 恢复数据库 |

---

## 数据库清单

### 关键数据 (丢失不可恢复)

| 数据库 | 路径 | 内容 | 大小估算 |
|--------|------|------|----------|
| `trading.db` | `data/trading.db` | 交易日志 — 全部历史交易记录、盈亏 | ~5-50 MB |
| `portfolio.db` | `data/portfolio.db` | 投资组合 — 持仓、配置、回测结果 | ~1-10 MB |
| `history.db` | `data/history.db` | 对话历史 — 所有 Bot 用户的消息记录 | ~10-100 MB |
| `shared_memory.db` | `data/shared_memory.db` | 共享记忆 — Mem0 向量嵌入 + 语义索引 | ~5-50 MB |

### 重要数据 (丢失影响功能)

| 数据库 | 路径 | 内容 | 大小估算 |
|--------|------|------|----------|
| `execution_hub.db` | `data/execution_hub.db` | 执行记录 — 任务执行历史、状态 | ~1-10 MB |
| `xianyu_chat.db` | `data/xianyu_chat.db` | 闲鱼聊天 — 买家对话上下文 | ~1-5 MB |
| `deploy_licenses.db` | `data/deploy_licenses.db` | 部署许可证 — 授权信息 | <1 MB |

### 可重建数据 (丢失可恢复)

| 数据库 | 路径 | 内容 | 重建方式 |
|--------|------|------|----------|
| `feedback.db` | `data/feedback.db` | 用户反馈 — 评分和改进建议 | 用户重新提交 |
| `cost_analytics.db` | `data/cost_analytics.db` | 成本分析 — LLM API 调用成本追踪 | 自动重新积累 (30 天保留) |

---

## 备份机制

### 自动备份 (默认启用)

- **脚本**: `scripts/backup_databases.py`
- **触发**: ExecutionScheduler 每日 04:00 ET 自动执行
- **方式**: SQLite 在线备份 API (`sqlite3.Connection.backup()`) — 不影响运行中的服务
- **目标**: `data/backups/` 目录

### 备份保留策略

| 类型 | 保留期 | 频率 | 命名格式 |
|------|--------|------|----------|
| 每日备份 | 7 天 | 每天 04:00 ET | `{db_name}_{YYYY-MM-DD}.db` |
| 每周备份 | 4 周 | 周日的每日备份 | 同上 (周日的备份自动保留更久) |

### 手动备份

```bash
cd packages/clawbot
python3 scripts/backup_databases.py
```

---

## 恢复流程

### 场景 1: 单个数据库损坏

```bash
# 1. 停止服务
sudo systemctl stop clawbot  # VPS
# 或: launchctl unload ~/Library/LaunchAgents/com.clawbot.agent.plist  # macOS

# 2. 查看可用备份
ls -la data/backups/ | grep trading  # 示例: 恢复 trading.db

# 3. 恢复 (替换损坏文件)
cp data/backups/trading_2026-03-23.db data/trading.db

# 4. 清理 WAL 文件 (如有)
rm -f data/trading.db-wal data/trading.db-shm

# 5. 验证完整性
sqlite3 data/trading.db "PRAGMA integrity_check;"

# 6. 重启服务
sudo systemctl start clawbot  # VPS
```

### 场景 2: 全量恢复 (新机器/全部数据丢失)

```bash
# 1. 部署代码 (不含数据库)
./scripts/deploy_vps.sh

# 2. 从备份恢复所有数据库
scp -P 29222 /path/to/backups/*.db clawbot@VPS_IP:/home/clawbot/clawbot/data/

# 3. 清理 WAL 文件
ssh -p 29222 root@VPS_IP 'rm -f /home/clawbot/clawbot/data/*.db-wal /home/clawbot/clawbot/data/*.db-shm'

# 4. 修复权限
ssh -p 29222 root@VPS_IP 'chown -R clawbot:clawbot /home/clawbot/clawbot/data/'

# 5. 验证
ssh -p 29222 root@VPS_IP 'for db in /home/clawbot/clawbot/data/*.db; do echo "$db:"; sqlite3 "$db" "PRAGMA integrity_check;"; done'

# 6. 重启
ssh -p 29222 root@VPS_IP 'systemctl restart clawbot'
```

### 场景 3: macOS 主节点迁移到新 Mac

```bash
# 1. 在旧 Mac 上手动备份
cd packages/clawbot
python3 scripts/backup_databases.py
tar czf ~/Desktop/clawbot-data-backup.tar.gz data/

# 2. 传输到新 Mac
scp ~/Desktop/clawbot-data-backup.tar.gz newmac:~/Desktop/

# 3. 在新 Mac 上恢复
cd ~/Desktop/OpenClaw\ Bot/packages/clawbot
tar xzf ~/Desktop/clawbot-data-backup.tar.gz

# 4. 恢复 .env (手动复制，不在备份中)
cp /path/to/secure/.env config/.env

# 5. 安装依赖 + 启动
pip install -r requirements.txt
python3 multi_main.py
```

---

## VPS 迁移检查清单

| # | 步骤 | 命令/操作 | 验证 |
|---|------|-----------|------|
| 1 | 备份当前 VPS 数据库 | `ssh VPS 'cd /home/clawbot/clawbot && python3 scripts/backup_databases.py'` | 检查 `data/backups/` |
| 2 | 下载备份到本地 | `scp -P 29222 -r root@OLD_VPS:/home/clawbot/clawbot/data/backups/ ./` | 文件大小正确 |
| 3 | 部署代码到新 VPS | `VPS_IP=NEW_IP ./scripts/deploy_vps.sh` | systemctl status ok |
| 4 | 上传数据库 | `scp -P 29222 backups/*.db root@NEW_VPS:/home/clawbot/clawbot/data/` | 文件存在 |
| 5 | 上传 .env | `scp -P 29222 config/.env root@NEW_VPS:/home/clawbot/clawbot/config/` | env 变量正确 |
| 6 | 修复权限 | `chown -R clawbot:clawbot /home/clawbot/clawbot/` | 无权限错误 |
| 7 | 重启服务 | `systemctl restart clawbot` | Bot 在线响应 |
| 8 | 验证功能 | Telegram 发送 `/status` | 收到正常状态回复 |
| 9 | 更新 DNS/IP | 更新 deploy_vps.sh 默认 IP | — |
| 10 | 停止旧 VPS | `systemctl stop clawbot && systemctl disable clawbot` | — |

---

## 关键文件 (非数据库)

除数据库外，以下文件也需要保护:

| 文件 | 说明 | 备份方式 |
|------|------|----------|
| `config/.env` | API Keys (30+ 个) | 手动管理，不进入 rsync/git |
| `data/api_keys.json` | API Key 池配置 | 随代码同步 |
| `data/free_api_pool.json` | 免费 API 池 | 随代码同步 |
| `data/broker_budget_state.json` | 交易预算状态 | 每日自动生成 |
| `data/social_state/` | 社媒运营状态 | 可重建 |
| `data/qdrant_data/` | 向量数据库 | 可从 shared_memory.db 重建 |

---

## 紧急联系

| 角色 | 操作 |
|------|------|
| 服务宕机 | 检查 `systemctl status clawbot` → 查看日志 `journalctl -u clawbot -n 100` |
| 数据库锁死 | 删除 WAL 文件: `rm data/*.db-wal data/*.db-shm` → 重启 |
| API Key 泄露 | 立即轮换所有 Key → 更新 `config/.env` → 重启 |
| VPS 被攻破 | 停止服务 → 更换 VPS → 从本地备份恢复 |

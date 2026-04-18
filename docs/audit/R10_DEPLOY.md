# R10 生产部署与运维审计

> **轮次**: R10 | **状态**: 待执行 | **预估条目**: ~30
> **审计角色**: DevOps Lead + VP Security + CTO
> **前置条件**: R9 完成
> **验证方式**: SSH 登录服务器实测 + 本地 Docker 构建测试

---

## 10.1 VPS 服务器审计（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.01 | 安全 | VPS | SSH 安全：密钥登录/密码强度/端口(22) | `ssh root@101.43.41.96` 检查 | ⬜ |
| R10.02 | 安全 | VPS | 防火墙(ufw/iptables)规则：仅开放必要端口 | `ufw status` | ⬜ |
| R10.03 | 配置 | VPS | 系统资源：2C2G 是否足够运行所有服务 | `free -h && df -h && top` | ⬜ |
| R10.04 | 配置 | VPS | 磁盘使用：40GB SSD 空间分布 | `du -sh /*` | ⬜ |
| R10.05 | 安全 | VPS | 系统更新：Ubuntu 22.04 安全补丁 | `apt list --upgradable` | ⬜ |
| R10.06 | 配置 | VPS | 时区设置：是否为 Asia/Shanghai | `timedatectl` | ⬜ |
| R10.07 | 配置 | VPS | swap 配置：2GB 内存是否需要 swap | `swapon --show` | ⬜ |
| R10.08 | 安全 | VPS | 运行中的服务：是否有不必要的服务 | `systemctl list-units` | ⬜ |

## 10.2 Docker 部署实测（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.09 | 配置 | VPS | Docker 版本和配置 | `docker version && docker info` | ⬜ |
| R10.10 | 配置 | VPS | `docker-compose up -d` 是否成功启动所有服务 | 实际执行 | ⬜ |
| R10.11 | 配置 | VPS | Redis 连接测试 | `docker exec redis redis-cli ping` | ⬜ |
| R10.12 | 配置 | VPS | OpenClaw 服务健康检查 | `curl localhost:18790/api/v1/system/ping` | ⬜ |
| R10.13 | 配置 | VPS | 容器资源限制是否生效（Redis 128M / OpenClaw 1G） | `docker stats` | ⬜ |
| R10.14 | 配置 | VPS | 容器日志管理：是否配置了 log rotation | 检查 Docker log 配置 | ⬜ |

## 10.3 systemd 服务管理（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.15 | 安全 | VPS | clawbot.service：non-root 运行/沙箱配置 | 读取 service 文件 | ⬜ |
| R10.16 | 配置 | VPS | 服务自启动：是否 enable 了 | `systemctl is-enabled clawbot` | ⬜ |
| R10.17 | 配置 | VPS | 服务重启策略：Restart=on-failure + 延迟 | 检查 Restart 配置 | ⬜ |
| R10.18 | 配置 | VPS | 服务日志：journalctl 输出是否正常 | `journalctl -u clawbot -n 50` | ⬜ |

## 10.4 心跳与故障转移（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.19 | 设计 | VPS | 心跳检测：macOS 主节点 → VPS 备用 | 检查心跳间隔和超时(120s) | ⬜ |
| R10.20 | 设计 | VPS | failover.timer：3次失败自动接管 | 检查定时器配置 | ⬜ |
| R10.21 | 设计 | VPS | Mac 恢复后自动退让 | 检查退让逻辑 | ⬜ |
| R10.22 | UX | VPS | 故障转移时的用户通知 | 检查告警触发 | ⬜ |

## 10.5 macOS LaunchAgent（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.23 | 配置 | `tools/launchagents/` | LaunchAgent plist 配置正确性 | 对照 Apple 文档 | ⬜ |
| R10.24 | 配置 | `tools/launchagents/` | 开机自启动是否生效 | `launchctl list` 检查 | ⬜ |
| R10.25 | 配置 | `tools/newsyslog.d/` | 日志轮转配置 | 检查 newsyslog 规则 | ⬜ |
| R10.26 | 设计 | macOS | Python 进程 Dock 隐藏是否正常工作 | 检查 multi_main.py 前几行 | ⬜ |

## 10.6 备份与灾难恢复（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R10.27 | 设计 | VPS/macOS | 自动备份(7日/4周保留)是否正常执行 | 检查备份目录 | ⬜ |
| R10.28 | 设计 | VPS | rsync 排除数据库的配置 | 检查 rsync 参数 | ⬜ |
| R10.29 | 设计 | 全局 | 灾难恢复指南(DR)是否可执行 | 模拟恢复步骤 | ⬜ |
| R10.30 | 安全 | VPS | .env 文件权限(600) | `ls -la config/.env` | ⬜ |

---

## 执行检查清单

- [ ] SSH 连接 VPS 成功
- [ ] Docker 服务全部运行正常
- [ ] 心跳检测正常
- [ ] 备份文件存在且最近
- [ ] 防火墙规则最小权限
- [ ] 更新 CHANGELOG.md

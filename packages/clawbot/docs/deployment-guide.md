# OpenClaw 闲鱼商业部署系统 - 使用指南

## 系统概览

已完成的商业化部署系统，包含：
- **6个免费AI Bot** (Telegram) - 基于 g4f 免费模型
- **闲鱼AI客服** - 自动回复、议价、订单处理
- **自动交付系统** - 付款检测 → License生成 → 百度网盘发货
- **防退款保护** - 检测退款自动吊销License
- **部署授权服务** - License验证 + 设备绑定

## 快速启动

### 一键启动所有服务
```bash
cd /Users/blackdj/Desktop/OpenClaw\ Bot/packages/clawbot
bash scripts/start_all.sh
```

启动内容：
- g4f API (端口 18891) - 免费AI模型
- 部署授权服务 (端口 18800) - License验证
- 闲鱼AI客服 - WebSocket实时监控
- 6个Telegram Bot - 全能助手

### 停止所有服务
```bash
bash scripts/stop_all.sh
```

## 核心配置

### 1. 百度网盘交付链接
编辑 `config/.env`，设置：
```bash
BAIDU_PAN_LINK=https://pan.baidu.com/s/你的分享链接
BAIDU_PAN_CODE=提取码
```

### 2. 打包部署客户端
```bash
bash scripts/pack_deploy_bundle.sh
```
生成 `OpenClaw_Deploy_v2026.3.zip`，上传到百度网盘

### 3. 闲鱼Cookie更新
当Cookie失效时：
1. Chrome打开闲鱼，F12复制Cookie
2. 更新 `.env` 中的 `XIANYU_COOKIES`
3. 热更新：`kill -USR1 $(cat /tmp/xianyu.pid)`

## 商业流程

### 买家购买流程
1. 买家在闲鱼咨询 → AI自动回复
2. 买家议价 → AI根据底价策略应对
3. 买家付款 → 系统检测到"等待卖家发货"
4. 自动创建License (用户名/密码/Key)
5. 通过闲鱼消息发送：百度网盘链接 + License
6. 同时Telegram通知你接手远程部署

### 买家部署流程
1. 下载百度网盘的部署包
2. 双击运行"一键部署"
3. 输入License Key
4. 选择AI模型方案（付费API/免费/本地）
5. 配置Telegram Bot Token
6. 自动安装OpenClaw + Skills
7. 生成健康报告

### 退款保护
- 检测到"退款成功" → 自动吊销License
- 买家无法继续使用
- Telegram通知你

## 定价策略

当前AI客服底价设置（`src/xianyu/xianyu_agent.py`）：
- 部署服务：¥89（可议价到¥79）
- API Token包：¥15

建议闲鱼标价：
- 产品A：OpenClaw一键部署包 - ¥19.9
- 产品B：云托管版 - ¥49.9/月（未实现）

## 服务监控

### 查看日志
```bash
tail -f logs/xianyu.log        # 闲鱼客服
tail -f logs/multi_bot.log     # Telegram Bot
tail -f logs/g4f.log           # g4f API
tail -f logs/deploy_server.log # 部署服务
```

### 检查服务状态
```bash
lsof -ti:18891  # g4f
lsof -ti:18800  # 部署服务
ps aux | grep xianyu
ps aux | grep multi_main
```

### License管理
```bash
# 查看所有License
curl -H "X-Admin-Token: $(grep DEPLOY_ADMIN_TOKEN config/.env | cut -d= -f2)" \
  http://localhost:18800/api/admin/licenses

# 手动吊销License
curl -X POST -H "X-Admin-Token: $(grep DEPLOY_ADMIN_TOKEN config/.env | cut -d= -f2)" \
  http://localhost:18800/api/admin/licenses/OC-XXXX-XXXX/revoke
```

## 成本控制

### 完全免费的部分
- 6个Telegram Bot：使用g4f免费模型
- 闲鱼AI客服：使用g4f的qwen-3-235b
- 部署授权服务：自建Flask API
- 所有基础设施：本地运行

### 可选付费部分
- Claude代理API：0.01元/次（仅作备用，已配置但未启用）
- 服务器托管：如需7x24运行可用VPS（约¥30/月）

## 故障排查

### g4f无响应
```bash
kill $(lsof -ti:18891)
python3 -m g4f.api --port 18891 --g4f-api-key dummy
```

### 闲鱼客服掉线
检查Cookie是否过期，查看 `logs/xianyu.log`

### Telegram Bot无响应
检查Token是否正确，查看 `logs/multi_bot.log`

## 下一步优化

1. **百度网盘自动上传** - 目前需手动上传部署包
2. **自动定价策略** - 根据市场竞争动态调价
3. **客户CRM** - 记录客户购买历史和满意度
4. **A/B测试** - 测试不同话术的转化率

## 技术架构

```
闲鱼买家
  ↓ WebSocket
闲鱼AI客服 (xianyu_live.py)
  ↓ 检测付款
License Manager (license_manager.py)
  ↓ 生成凭证
闲鱼消息 (百度网盘链接 + License)
  ↓
买家下载部署包
  ↓
部署客户端 (deploy_client.py)
  ↓ License验证
部署授权服务 (deploy_server.py)
  ↓ 设备绑定
OpenClaw安装完成
```

---

**所有核心功能已实现并测试通过。**

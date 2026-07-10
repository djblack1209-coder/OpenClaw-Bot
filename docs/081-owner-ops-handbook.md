# OpenEverything 使用手册（给老板）

> 最后更新：2026-07-07
> 目标：老板只看绿灯/黄灯/红灯，不记技术命令。

## 每天早上第一件事

1. 打开：`http://127.0.0.1:18800/dashboard`
2. 看首屏颜色：
   - 🟢 绿灯：不用管，系统在自动看守。
   - 🟡 黄灯：按页面里的“下一步”做。
   - 🔴 红灯：点右上角“导出状态报告”，发给技术支持。
3. 如果页面打不开，再运行：

```bash
cd ~/Desktop/OpenEverything && scripts/auto_recovery.sh --dry-run
```

先看 dry-run 提示，确认没问题后再去掉 `--dry-run`。

## 闲鱼有新订单怎么办

正常情况：你什么都不用做。

- 买家付款后，系统自动发卡密。
- 浏览器助手看到“已付款/待发货”后，才会点发货。
- 买家兑换后，系统会继续观察是否创建 API、导入 CC Switch、调用模型。

如果看到“补救队列不为空”：

1. 打开 `http://127.0.0.1:18800/dashboard`
2. 展开“补救队列”
3. 按页面提示复制话术或让浏览器助手重试

## 当前买家号不能测试时怎么办

用“替换模式模拟验收”：

1. 打开 `http://127.0.0.1:18800/dashboard`
2. 展开“替换模式模拟验收”
3. 看“严格模拟门”逐步状态，按页面提示补齐：发卡 → 商品模板/重新上架 → 注册 → 兑换 → 创建 API → 导入 CC Switch → 终端调用 → 渠道/服务器状态
4. 页面显示“严格模拟门已跑通”后，也只能说明演练通过，不能正式放量

注意：替换模式只证明流程能演练，不能解锁正式售卖。正式售卖仍必须等新的 `xy_oid_*` 真实小额订单；“买家真实下单付款”和“最终点击闲鱼发货按钮”不在模拟门里伪造。

## 系统红灯怎么办

### 1. 先导出状态报告

打开：`http://127.0.0.1:18800/export-status`

把页面里的 JSON 发给技术支持。报告已经去掉卡密、Token、买家昵称和 API Key。

### 2. 再跑一键健康检查

```bash
cd ~/Desktop/OpenEverything && scripts/auto_health_check.sh
```

看每一行后面的“怎么办”。

### 3. 仍然红灯，再跑一键恢复预演

```bash
cd ~/Desktop/OpenEverything && scripts/auto_recovery.sh --dry-run
```

确认要执行，再运行：

```bash
cd ~/Desktop/OpenEverything && scripts/auto_recovery.sh
```

## 备份和恢复

### 手动备份一次

```bash
cd ~/Desktop/OpenEverything && scripts/local_backup.sh
```

默认备份到 iCloud（如果可用）或桌面 `OpenEverything-backups`，保留 30 天。

### 恢复前先预演

```bash
cd ~/Desktop/OpenEverything && scripts/disaster_recovery.sh --dry-run
```

真正恢复必须加 `--confirm`，避免误覆盖。

## 老板只需要记住一句话

平时只打开：`http://127.0.0.1:18800/dashboard`

看不懂就点：`导出状态报告`。

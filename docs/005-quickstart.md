# OpenEverything 快速开始

> 生产运行时是唯一事实。首次操作先读 `docs/current/current-baseline.md`，不要从旧截图、历史报告或本地测试推断生产状态。

## 本机只读检查

```bash
bash scripts/auto_health_check.sh --json --strict
openclaw health --json --timeout 5000
openclaw status --json --timeout 5000
```

正常基线至少包括 Gateway 与 ClawBot Agent 可达、每日备份新鲜、核心 LaunchAgent 运行。G4F、Kiro 和 IBKR 是显式可选能力，未配置时应显示 disabled，而不是伪装成故障。

## 开发环境：先验证，再配置运行

支持矩阵为 Python 3.12.x 的 macOS arm64 与 Linux amd64 后端；Node 22.19+（22.x）或 24.x / npm 10.x 或 11.x。Rust 桌面编译需要 Xcode Command Line Tools（macOS）或 GTK/WebKit 开发库（Linux）。其他 Python 小版本或架构不能从当前锁安装结果推断为支持。

macOS 从仓库根目录运行：

```bash
python3.12 --version
node --version
npm --version
uv --version
bash scripts/check_clean_install.sh --component all --python "$(command -v python3.12)" --keep
```

此入口创建全新临时源副本和依赖目录，不复用或覆盖项目 `.venv312`、`node_modules`、真实配置。npm 使用 `ci --ignore-scripts`；Python 先按哈希下载，再断网安装 macOS 锁，六个已审查的纯 Python 源码包使用锁内构建工具。日志及逐项退出码保存在输出的 `WORK_DIR` 下。可用 `--component desktop`、`runtime`、`weixin`、`python` 分别复验。Weixin CLI/语法通过不能替代 SDK 语义或上游测试通过。

完成验证后，若要在专用的新开发副本构建前端：

```bash
cd apps/openclaw-manager-src
npm ci --ignore-scripts --no-audit --no-fund
npm run lint
npm run build
cd src-tauri
cargo check --locked
```

`npm ci` 会替换当前目录的依赖，因此只在新副本使用；Rust 构建本身需要执行受审查的构建脚本。审计使用了隔离的临时 Cargo 目录；以上简短开发命令不承诺同等沙箱隔离。首次设置只保存 Gateway Provider/模型并回读，显示“配置已保存、运行未验证”；保存失败会保留表单，跳过保留待配置状态。已有模型、费率、扩展和 SecretRef 保留，ClawBot 模型池需另行配置。

不要把 `.env`、浏览器 Profile、数据库、备份或构建产物提交 Git。运行配置只在部署阶段创建；复制模板前先确认目标不存在，不覆盖现有 `config/.env`。配置中的必填 token 不写入命令历史或文档。

## 容器部署

这部分会启动实际业务。先在专用部署副本准备 `packages/clawbot/config/.env`、`data`、`logs`，保留已有文件；配置 `OPENCLAW_API_TOKEN` 与 `REDIS_PASSWORD`，并确认数据和日志目录可由镜像中的 `clawbot` 用户写入；图片产物位于数据目录内的 `images`。Compose 保留现有绑定目录，不会自动把已有数据切换到空卷。

在新部署副本的仓库根目录生成本地认证值，代码不会打印值，也不会覆盖已经存在的配置。其余供应商和 Bot 凭据仍保持空白，随后按所需功能在本地填写：

```bash
python3 - <<'PYCONFIG'
import os, re, secrets
from pathlib import Path
folder = Path('packages/clawbot/config')
content = (folder / '.env.example').read_text()
for key in ('OPENCLAW_API_TOKEN', 'REDIS_PASSWORD'):
    content = re.sub(rf'^{key}=.*$', f'{key}={secrets.token_hex(32)}', content, flags=re.M)
fd = os.open(folder / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(content)
PYCONFIG
```

此配置生成属于部署准备，不进入前面的安装验证流程。已有配置时会明确失败；保留原文件并在本地检查，而不是删除后重建。

```bash
docker compose --env-file packages/clawbot/config/.env config --quiet
docker compose --env-file packages/clawbot/config/.env build openclaw
docker compose --env-file packages/clawbot/config/.env up -d
```

不要输出完整展开后的 Compose 配置，它可能包含密钥。Compose 从宿主读取 `.env` 并注入环境变量；显式设置 `PYTHON_DOTENV_DISABLED=1`，避免非 root 应用再次读取属于宿主用户的 0600 文件。保留该文件权限，不通过放宽权限或改为 root 运行解决配置加载。普通本机入口仍支持读取自己的 `.env`，已有环境变量优先。

容器内 API 监听 `0.0.0.0:18790`，宿主仅发布至 `127.0.0.1:18790`，配置目录只读。健康检查自动带 `X-API-Token`；无 token 的公网或 production 实例拒绝请求。仅显式本地开发、测试环境的 loopback 实例可无 token。HTTP 与 WebSocket 使用同一个实例认证上下文，修改环境变量后需重启实例才生效。

构建镜像不等于业务上线验收。审计容器仅启动实际 API 类的独立探针，验证认证、端口及卷权限；完整业务仍须通过受管入口启动，再验证对应功能。

## 桌面 App

```bash
make tauri-build
```

这是部署入口，会更改已安装 App；不用于只读检查或干净安装验证。该入口会先保存已安装 App，构建并验证签名，再原子安装；失败自动恢复上一版。App 的“智能体”页是本机服务唯一写控制面。

## 浏览器扩展

扩展当前仅支持 X 和小红书的页面识别、只读上下文采集、待审草稿、安全填入和表现回读。默认不点击发布、评论、关注或私信。

聚焦回归：

```bash
node --test \
  packages/openclaw-npm/assets/chrome-extension/test/social-core.test.mjs \
  packages/openclaw-npm/assets/chrome-extension/test/social-page-runner.test.mjs \
  packages/openclaw-npm/assets/chrome-extension/test/popup-static.test.mjs
```

## Global Intelligence 新闻入口

新闻产品使用 `packages/clawbot/src/intel/` 的独立采集、订阅和投递管线。专用凭据为 `INTEL_BRIEF_TELEGRAM_BOT_TOKEN`，禁止回退到通用 ClawBot token。固定投递使用专用 chat 配置；订阅投递使用 Intel 数据库中的订阅目标。

通用 ClawBot 的 `/news`、中文“早报”和微信 `104` 只返回入口说明，不再生成旧科技早报。在 `packages/clawbot/config/.env` 中配置经专用 Bot `getMe` 核实的 `INTEL_BRIEF_TELEGRAM_BOT_USERNAME`，重载 ClawBot 后生效；缺失或非法用户名只显示文字，不猜测地址。专用 Bot 内使用 `/today`、`/ai`、`/market`。

旧 `morning_news` 任务永久退役，`MORNING_NEWS_ENABLED` 或控制面历史 `enabled=true` 不会恢复它。升级运行实例前，先将控制面该任务设为禁用，保存本地前态备份；历史投递记录保留。调度时区、回滚与验收边界见 [新闻归并记录](090-news-consolidation-2026-09-12.md)。

## 本机备份与恢复

```bash
make backup-run
make backup-schedule-status
make backup-restore-drill
```

恢复默认只预览或演练。真正覆盖现有状态前必须有最新 prestate、校验通过的归档、明确范围和失败回滚。

## Oracle JIYU

只读检查：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager status'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager check'
```

一致性备份：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager backup'
```

任何更新、品牌、Apache、Cloudflare 源站或地域配置写入都必须使用管理器的现有命令。不得直接替换二进制、改数据库或编辑生产环境文件。

## 聚焦验证

```bash
make docs-check
make sub2api-check
npm run build --prefix apps/openclaw-manager-src
```

只有改动跨越多个共享边界时才运行 `make ci-local`。本地环境失败单独记录，不阻塞安全的生产只读诊断。

## 恢复原则

- Mac：先运行现有备份恢复演练，再使用已签名上一版 App 或受管 LaunchAgent 定义。
- Oracle：使用管理器生成的一致性备份和变更自己的回滚目录。
- 闲鱼、Frist-API 和中央生图 MCP 已退役，不属于恢复目标。
- 支付、订单、数据库迁移、备份恢复和安全数据不得因减负而删除。

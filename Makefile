# OpenClaw Bot — Monorepo 任务入口
# 使用: make test / make lint / make format / make typecheck / make docker

# Python 路径自动探测: 优先用项目虚拟环境，避免系统 python3 缺少 pytest 或依赖
CLAWBOT := packages/clawbot
PYTHON ?= $(shell \
	if [ -x "$(CURDIR)/$(CLAWBOT)/.venv312/bin/python" ]; then \
		echo "$(CURDIR)/$(CLAWBOT)/.venv312/bin/python"; \
	elif command -v python3.12 >/dev/null 2>&1; then \
		command -v python3.12; \
	elif command -v python3 >/dev/null 2>&1; then \
		command -v python3; \
	else \
		echo python3; \
	fi)
FRONTEND := apps/openclaw-manager-src
FRIST_API := apps/frist-api
CHROME_EXTENSION := packages/openclaw-npm/assets/chrome-extension

.PHONY: test test-ci lint format format-check typecheck frontend-lint frontend-static-test frontend-build chrome-extension-test backup-databases backup-restore-drill source-backup-restore-test backup-restore-test runtime-permissions-check runtime-permissions-fix runtime-permissions-test renewals-check renewals-test docker clean deep-clean help ci-python ci-frontend ci-frist-api ci-docs ci-local final-audit syntax-check docs-check frist-api-test frist-api-dev frist-api-static frist-api-up frist-api-down frist-api-newapi-setup new-api-up new-api-down new-api-check new-api-sync new-api-brand-patch cc-seller-chrome cc-seller-bridge cc-seller-auto

## ─── 帮助 ───
help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

## ─── 测试 ───
test: ## 运行 Python 全量测试
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q

test-ci: ## 运行 CI 使用的完整 Python 测试（不在首个失败处提前停止）
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q --timeout=120 -o "addopts="

test-v: ## 运行 Python 测试 (详细模式)
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -v

test-cov: ## 运行测试 + 覆盖率报告
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q --cov=src --cov-report=term-missing

## ─── 代码检查 ───
lint: ## Ruff 静态检查
	cd $(CLAWBOT) && $(PYTHON) -m ruff check src/

typecheck: ## 前端 TypeScript 类型检查
	cd $(FRONTEND) && npx tsc --noEmit

frontend-lint: ## 前端 ESLint 检查
	cd $(FRONTEND) && npm run lint

frontend-static-test: ## 桌面端高风险动作与运行端点静态合同
	node $(FRONTEND)/src/components/Social/social-growth-feedback.static.test.mjs
	node $(FRONTEND)/src/components/Layout/layout-responsive.static.test.mjs

frontend-build: ## 前端生产构建
	cd $(FRONTEND) && npm run build

chrome-extension-test: ## Chrome 扩展语法与高风险动作安全合同
	node --check $(CHROME_EXTENSION)/background.js
	node --check $(CHROME_EXTENSION)/popup.js
	node --check $(CHROME_EXTENSION)/social-page-runner.js
	cd $(CHROME_EXTENSION) && node --test test/social-core.test.mjs test/social-page-runner.test.mjs test/popup-static.test.mjs

backup-databases: ## 锁定、校验并原子备份本机 SQLite 数据
	cd $(CLAWBOT) && $(PYTHON) scripts/backup_databases.py

backup-restore-drill: ## 把最新 SQLite 备份恢复到可丢弃临时目录并校验
	cd $(CLAWBOT) && $(PYTHON) scripts/backup_databases.py --restore-drill

source-backup-restore-test: ## 运行源码快照、校验和与可丢弃恢复安全合同
	$(PYTHON) -m pytest $(CLAWBOT)/tests/test_local_backup_restore.py --tb=short -q

backup-restore-test: ## 运行不接触生产数据的数据库和源码备份/恢复合同
	$(PYTHON) -m pytest $(CLAWBOT)/tests/test_backup_databases.py $(CLAWBOT)/tests/test_local_backup_restore.py --tb=short -q

runtime-permissions-check: ## 只检查本机敏感运行文件权限，不读取内容
	OPENCLAW_PROJECT_ROOT=$(CURDIR) $(PYTHON) scripts/harden_runtime_permissions.py --check

runtime-permissions-fix: ## 把已知敏感运行文件和目录收紧为仅所有者可访问
	OPENCLAW_PROJECT_ROOT=$(CURDIR) $(PYTHON) scripts/harden_runtime_permissions.py --apply

runtime-permissions-test: ## 在临时目录验证权限检查和修复合同
	$(PYTHON) -m pytest $(CLAWBOT)/tests/test_runtime_permissions.py --tb=short -q

renewals-check: ## 校验无凭据续费模板和 30/14/7/3/1 天提醒规则
	$(PYTHON) scripts/check_renewals.py --config $(CLAWBOT)/config/renewals.example.json --validate-template --json

renewals-test: ## 在临时数据上验证续费提醒和凭据拒绝合同
	$(PYTHON) -m pytest $(CLAWBOT)/tests/test_check_renewals.py --tb=short -q

frist-api-test: ## 运行 Frist-API 原型测试
	cd $(FRIST_API) && npm test

docs-check: ## 检查 docs 扁平目录、编号命名和索引完整性
	bash scripts/check_docs_layout.sh

frist-api-dev: ## 启动 Frist-API 本地完整链路 (http://127.0.0.1:3180)
	cd $(FRIST_API) && FRIST_API_EXPOSE_VERIFICATION_CODE=1 FRIST_API_ALLOW_DEMO_RECHARGE=0 npm start

frist-api-static: ## 仅启动 Frist-API 静态网站预览 (无后端链路)
	cd $(FRIST_API) && npm run static

frist-api-newapi-setup: ## 从本机 New-API SQLite 写入 Frist-API 桥接 .env（不打印密钥）
	node scripts/setup_local_newapi_bridge.mjs

new-api-up: ## Docker 启动 QuantumNous/new-api（启动前自动备份 data/newapi）
	@mkdir -p data/backups
	@if [ -d data/newapi ]; then tar -czf "data/backups/newapi-$$(date +%Y%m%d-%H%M%S).tgz" data/newapi; fi
	docker compose -f docker-compose.newapi.yml up -d

new-api-down: ## Docker 停止 QuantumNous/new-api
	docker compose -f docker-compose.newapi.yml down

frist-api-up: frist-api-newapi-setup ## Docker 启动 Frist-API + QuantumNous/new-api 全链路
	docker compose -f docker-compose.newapi.yml -f docker-compose.frist-api.yml up -d

frist-api-down: ## Docker 停止 Frist-API + New-API 全链路
	docker compose -f docker-compose.newapi.yml -f docker-compose.frist-api.yml down

new-api-check: ## 检查 New-API 上游源码和镜像是否同步到最新版
	scripts/sync_new_api_upstream.sh check

new-api-sync: ## 同步 New-API submodule 指针和 docker-compose 镜像 tag 到最新版
	scripts/sync_new_api_upstream.sh update

new-api-brand-patch: ## 在干净 New-API submodule 上应用 CC中转品牌补丁
	scripts/apply_new_api_brand_patch.sh

cc-seller-chrome: ## 启动 CC中转闲鱼卖家专用 Chrome，并打开插件加载目录
	node scripts/cc_zhongzhuan_launch_seller_chrome.mjs --copy-token

cc-seller-bridge: ## 启动 CC中转闲鱼卖家本机桥接器，只读巡检页面；发卡需 18800 人工单次确认
	node scripts/cc_zhongzhuan_seller_bridge.mjs

cc-seller-auto: cc-seller-chrome ## 启动卖家专用浏览器后，运行一次只读桥接巡检
	node scripts/cc_zhongzhuan_seller_bridge.mjs --once

## ─── 格式化 ───
format: ## Ruff 自动格式化
	cd $(CLAWBOT) && $(PYTHON) -m ruff format src/

format-check: ## 检查格式 (不修改)
	cd $(CLAWBOT) && $(PYTHON) -m ruff format --check src/

## ─── Docker ───
docker: ## 构建 Docker 镜像
	docker compose build

docker-up: ## 启动 Docker 容器
	docker compose up -d

docker-down: ## 停止 Docker 容器
	docker compose down

## ─── Tauri 桌面端构建 ───
tauri-clean: ## 构建前清理所有历史残留应用 (防止 Launchpad 出现重复图标)
	@echo "══════ 清理历史残留应用 ══════"
	@# /Applications 下的旧版本
	rm -rf /Applications/OpenEverything.app 2>/dev/null || true
	rm -rf /Applications/OpenClaw.app 2>/dev/null || true
	rm -rf /Applications/OpenClaw-Gateway.app 2>/dev/null || true
	@# 主分支构建目录里的旧 .app (Spotlight 会索引导致 Launchpad 重复)
	rm -rf apps/openclaw-manager-src/src-tauri/target/release/bundle/macos/OpenEverything.app 2>/dev/null || true
	rm -rf apps/openclaw-manager-src/src-tauri/target/release/bundle/macos/OpenClaw.app 2>/dev/null || true
	@# worktree 分支构建目录里的旧 .app
	find .worktrees -path "*/bundle/macos/*.app" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 历史残留已清理"

tauri-build: tauri-clean ## 构建 Tauri 桌面端 (含自动清理历史残留)
	@echo "══════ 构建 Tauri 桌面端 ══════"
	cd $(FRONTEND) && npm run tauri:build
	@echo "✅ Tauri 构建完成"
	@echo "══════ 安装到 /Applications ══════"
	cp -R apps/openclaw-manager-src/src-tauri/target/release/bundle/macos/OpenClaw.app /Applications/
	@# 安装完毕后删除构建目录的 .app 副本，防止 Spotlight 索引出重复
	rm -rf apps/openclaw-manager-src/src-tauri/target/release/bundle/macos/OpenClaw.app
	@# 刷新 Launchpad 缓存
	defaults write com.apple.dock ResetLaunchPad -bool true && killall Dock 2>/dev/null || true
	@echo "✅ OpenClaw.app 已安装到 /Applications (构建副本已清理, Launchpad 已刷新)"

## ─── 清理 ───
clean: ## 清理缓存和临时文件
	find $(CLAWBOT) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type f -name "*.pyc" -delete 2>/dev/null || true

deep-clean: clean ## 深度清理（释放 GB 级空间，不影响代码）
	@echo "══════ 深度清理开始 ══════"
	@echo "[1/5] 清理 Tauri 编译缓存..."
	rm -rf $(FRONTEND)/src-tauri/target/ 2>/dev/null || true
	@echo "[2/5] 修剪失效 worktree 记录（保留所有有效 worktree 和未提交工作）..."
	git worktree prune
	@echo "[3/5] 压缩 git 历史..."
	git gc --prune=now 2>/dev/null || true
	@echo "[4/5] 清理 Python 构建缓存..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "[5/5] 清理 Playwright 临时文件..."
	rm -rf .playwright-cli/ .playwright-mcp/ 2>/dev/null || true
	@echo ""
	@echo "✅ 深度清理完成。项目当前大小:"
	@du -sh . 2>/dev/null
	@echo "提示: 如果 OpenCode 仍然卡顿，请重启 OpenCode 应用"

## ─── CI 本地验证（GitHub Actions 直接复用这些目标） ───
ci-python: ## Python Ruff、全量测试和语法检查
	@echo "══════ Python: Ruff ══════"
	$(MAKE) lint
	@echo "══════ Python: Tests ══════"
	$(MAKE) test-ci
	@echo "══════ Python: Syntax ══════"
	$(MAKE) syntax-check

ci-frontend: ## 前端 ESLint、TypeScript、生产构建和 Chrome 扩展安全合同
	@echo "══════ Frontend: ESLint ══════"
	$(MAKE) frontend-lint
	@echo "══════ Frontend: TypeScript ══════"
	$(MAKE) typecheck
	@echo "══════ Frontend: Safety Contracts ══════"
	$(MAKE) frontend-static-test
	@echo "══════ Frontend: Build ══════"
	$(MAKE) frontend-build
	@echo "══════ Chrome Extension: Safety Contracts ══════"
	$(MAKE) chrome-extension-test

ci-frist-api: ## Frist-API 确定性测试
	@echo "══════ Frist-API: Tests ══════"
	$(MAKE) frist-api-test

ci-docs: ## 文档治理检查
	@echo "══════ Docs: Governance ══════"
	$(MAKE) docs-check

ci-local: ci-python ci-frontend ci-frist-api ci-docs ## 一键运行与 GitHub Actions 相同的确定性质量门
	@echo ""
	@echo "✅ 本地 CI 全部通过"

final-audit: ## 运行完整离线质量、安全与供应链审计，输出脱敏 JSON/摘要
	$(PYTHON) scripts/final_audit.py --python $(PYTHON)

syntax-check: ## 仅检查 Python 语法
	cd $(CLAWBOT) && $(PYTHON) -m py_compile multi_main.py
	cd $(CLAWBOT) && find src/ -name "*.py" -exec $(PYTHON) -m py_compile {} +

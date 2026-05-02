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

.PHONY: test lint format typecheck docker clean help ci-local syntax-check frist-api-test frist-api-dev frist-api-static frist-api-up frist-api-down

## ─── 帮助 ───
help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

## ─── 测试 ───
test: ## 运行 Python 全量测试
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q

test-v: ## 运行 Python 测试 (详细模式)
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -v

test-cov: ## 运行测试 + 覆盖率报告
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q --cov=src --cov-report=term-missing

## ─── 代码检查 ───
lint: ## Ruff 静态检查
	cd $(CLAWBOT) && $(PYTHON) -m ruff check src/

typecheck: ## 前端 TypeScript 类型检查
	cd $(FRONTEND) && npx tsc --noEmit

frist-api-test: ## 运行 Frist-API 原型测试
	cd $(FRIST_API) && npm test

frist-api-dev: ## 启动 Frist-API 本地完整链路 (http://127.0.0.1:3180)
	cd $(FRIST_API) && FRIST_API_EXPOSE_VERIFICATION_CODE=1 FRIST_API_ALLOW_DEMO_RECHARGE=0 npm start

frist-api-static: ## 仅启动 Frist-API 静态网站预览 (无后端链路)
	cd $(FRIST_API) && npm run static

frist-api-up: ## Docker 启动 Frist-API 网站 + New-API 核心原型
	docker compose -f docker-compose.frist-api.yml up -d

frist-api-down: ## Docker 停止 Frist-API 原型
	docker compose -f docker-compose.frist-api.yml down

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
	@echo "[2/5] 清理 worktrees..."
	@# 先正确注销 git worktree，再删目录
	@for wt in $$(git worktree list --porcelain 2>/dev/null | grep '^worktree ' | grep '.worktrees/' | sed 's/^worktree //'); do \
		git worktree remove "$$wt" --force 2>/dev/null || true; \
	done
	rm -rf .worktrees/ 2>/dev/null || true
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

## ─── CI 本地验证（和 GitHub Actions 一致） ───
ci-local: ## 一键本地 CI 验证 (等同 GitHub Actions 全部检查)
	@echo "══════ [1/4] Python Lint (ruff) ══════"
	cd $(CLAWBOT) && $(PYTHON) -m ruff check src/ --config ruff.toml
	@echo ""
	@echo "══════ [2/4] Python Tests (pytest) ══════"
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q \
		-x --timeout=120
	@echo ""
	@echo "══════ [3/4] Python Syntax Check ══════"
	cd $(CLAWBOT) && $(PYTHON) -m py_compile multi_main.py
	cd $(CLAWBOT) && find src/ -name "*.py" -exec $(PYTHON) -m py_compile {} +
	@echo ""
	@echo "══════ [4/4] Frontend TypeScript Check ══════"
	cd $(FRONTEND) && npx tsc --noEmit
	@echo ""
	@echo "✅ 本地 CI 全部通过"

syntax-check: ## 仅检查 Python 语法
	cd $(CLAWBOT) && $(PYTHON) -m py_compile multi_main.py
	cd $(CLAWBOT) && find src/ -name "*.py" -exec $(PYTHON) -m py_compile {} +

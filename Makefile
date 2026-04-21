# OpenClaw Bot — Monorepo 任务入口
# 使用: make test / make lint / make format / make typecheck / make docker

# Python 路径自动探测: 优先用系统 python3，找不到则回退到项目虚拟环境
CLAWBOT := packages/clawbot
PYTHON ?= $(shell command -v python3 || echo $(CLAWBOT)/.venv312/bin/python)
FRONTEND := apps/openclaw-manager-src

.PHONY: test lint format typecheck docker clean help ci-local syntax-check

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
tauri-clean: ## 构建前清理 /Applications 下的历史残留应用 (防止双版本共存)
	@echo "══════ 清理历史残留应用 ══════"
	rm -rf /Applications/OpenEverything.app 2>/dev/null || true
	rm -rf /Applications/OpenClaw.app 2>/dev/null || true
	@echo "✅ 历史残留已清理"

tauri-build: tauri-clean ## 构建 Tauri 桌面端 (含自动清理历史残留)
	@echo "══════ 构建 Tauri 桌面端 ══════"
	cd $(FRONTEND) && npm run tauri:build
	@echo "✅ Tauri 构建完成"
	@echo "══════ 安装到 /Applications ══════"
	cp -R apps/openclaw-manager-src/src-tauri/target/release/bundle/macos/OpenClaw.app /Applications/
	@echo "✅ OpenClaw.app 已安装到 /Applications"

## ─── 清理 ───
clean: ## 清理缓存和临时文件
	find $(CLAWBOT) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type f -name "*.pyc" -delete 2>/dev/null || true

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

# OpenClaw Bot — Monorepo 任务入口
# 使用: make test / make lint / make format / make typecheck / make docker

PYTHON := packages/clawbot/.venv312/bin/python
CLAWBOT := packages/clawbot
FRONTEND := apps/openclaw-manager-src

.PHONY: test lint format typecheck docker clean help

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

## ─── 清理 ───
clean: ## 清理缓存和临时文件
	find $(CLAWBOT) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find $(CLAWBOT) -type f -name "*.pyc" -delete 2>/dev/null || true

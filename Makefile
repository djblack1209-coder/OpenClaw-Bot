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
SHELLCHECK_FILES := $(filter-out \
	packages/clawbot/scripts/start_xianyu.sh, \
	$(wildcard scripts/*.sh packages/clawbot/scripts/*.sh tools/launchagents/*.sh apps/frist-api/deploy/*.sh))

.PHONY: test lint format typecheck docker clean help ci-local syntax-check docs-check shellcheck gitleaks-check dependency-audit rust-audit security-check clean-install-check supply-chain-check python-lock python-lock-check critical-coverage-check frist-api-test frist-api-dev frist-api-static frist-api-up frist-api-down frist-api-newapi-setup new-api-up new-api-down new-api-check new-api-sync new-api-brand-patch sub2api-check jiyu-sub2-replenish jiyu-sub2-replenish-dry-run cc-seller-chrome cc-seller-bridge cc-seller-auto backup-run backup-schedule-install backup-schedule-status backup-schedule-uninstall backup-restore-drill tauri-rollback-check tauri-rollback

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
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q --cov=src --cov-report=term-missing --cov-fail-under=40
	$(MAKE) critical-coverage-check

critical-coverage-check: ## 要求高风险业务模块聚合覆盖率不低于 80%
	cd $(CLAWBOT) && $(PYTHON) -m coverage report \
		--include='src/api/auth.py,src/core/loop_owner.py,src/xianyu/cc_operator_state.py,src/execution/social/publish_gate.py,src/intel/scheduled_pipeline.py,src/risk_validators.py' \
		--fail-under=80
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/api/auth.py' --fail-under=70
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/core/loop_owner.py' --fail-under=70
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/xianyu/cc_operator_state.py' --fail-under=90
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/execution/social/publish_gate.py' --fail-under=75
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/intel/scheduled_pipeline.py' --fail-under=90
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/risk_validators.py' --fail-under=90
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/broker_bridge.py' --fail-under=35
	cd $(CLAWBOT) && $(PYTHON) -m coverage report --include='src/xianyu/xianyu_live.py' --fail-under=35

## ─── 代码检查 ───
lint: ## Ruff 静态检查
	cd $(CLAWBOT) && $(PYTHON) -m ruff check src/

typecheck: ## 前端 TypeScript 类型检查
	cd $(FRONTEND) && npx tsc --noEmit

frist-api-test: ## 运行 Frist-API 原型测试
	cd $(FRIST_API) && npm test

docs-check: ## 检查 docs 扁平目录、编号命名和索引完整性
	bash scripts/check_docs_layout.sh

shellcheck: ## 检查仓库自有 Shell 脚本（仅排除依赖特殊运行环境的闲鱼启动脚本）
	@command -v shellcheck >/dev/null 2>&1 || { echo '缺少 shellcheck，请先安装后重试'; exit 127; }
	shellcheck -x $(SHELLCHECK_FILES)

gitleaks-check: ## 扫描最新提交、受跟踪改动和未跟踪文件中的密钥
	@command -v gitleaks >/dev/null 2>&1 || { echo '缺少 gitleaks，请先安装后重试'; exit 127; }
	gitleaks detect --source . --log-opts='--max-count=1' --redact --no-banner --no-color
	@git diff --binary --no-ext-diff HEAD | gitleaks detect --pipe --redact --no-banner --no-color
	@git ls-files --others --exclude-standard | while IFS= read -r file; do \
		[ -f "$$file" ] || continue; \
		printf '\nFILE:%s\n' "$$file"; \
		cat "$$file"; \
	done | gitleaks detect --pipe --redact --no-banner --no-color

dependency-audit: ## 审计前端、服务端和 Python 锁定依赖的高危漏洞
	$(PYTHON) -m pip_audit --version >/dev/null
	npm audit --prefix $(FRONTEND) --audit-level=high
	npm audit --prefix $(FRIST_API) --audit-level=high
	npm audit --prefix $(FRONTEND)/src-tauri/npm-runtime-lock --audit-level=high --omit=dev
	npm audit --prefix .openclaw/extensions/openclaw-weixin --audit-level=high
	$(PYTHON) -m pip_audit --disable-pip --no-deps -r $(CLAWBOT)/requirements-lock.txt --vulnerability-service pypi --progress-spinner off --cache-dir /tmp/openclaw-pip-audit-cache --timeout 10
	$(PYTHON) -m pip_audit --disable-pip --no-deps -r $(CLAWBOT)/requirements-lock-macos.txt --vulnerability-service pypi --progress-spinner off --cache-dir /tmp/openclaw-pip-audit-cache --timeout 10

rust-audit: ## 使用 RustSec 审计桌面端锁定依赖
	@command -v cargo-audit >/dev/null 2>&1 || { echo '缺少 cargo-audit，请先运行 cargo install cargo-audit --locked'; exit 127; }
	cd $(FRONTEND)/src-tauri && cargo audit --file Cargo.lock

security-check: shellcheck gitleaks-check dependency-audit rust-audit supply-chain-check ## 运行本地安全与供应链门禁

clean-install-check: ## 在临时目录实际安装前端与 Python 哈希锁
	bash scripts/check_clean_install.sh

supply-chain-check: ## 验证 GitHub Action SHA 与桌面 npm 完整性锁
	node scripts/check_supply_chain.mjs
	npm ci --prefix $(FRONTEND)/src-tauri/npm-runtime-lock --omit=dev --ignore-scripts --no-audit --no-fund
	npm audit --prefix $(FRONTEND)/src-tauri/npm-runtime-lock --omit=dev --audit-level=high

python-lock: ## 重新生成 Linux CI 与 macOS Python 3.12 哈希锁
	cd $(CLAWBOT) && uv pip compile requirements-dev.txt --python-platform x86_64-manylinux_2_28 --python-version 3.12 --generate-hashes --no-annotate --custom-compile-command 'make python-lock' --output-file requirements-lock.txt
	cd $(CLAWBOT) && uv pip compile requirements-dev.txt --python-platform aarch64-apple-darwin --python-version 3.12 --generate-hashes --no-annotate --custom-compile-command 'make python-lock' --output-file requirements-lock-macos.txt

python-lock-check: ## 验证 requirements 与已提交哈希锁没有漂移
	@cd $(CLAWBOT) && \
		tmp_linux=$$(mktemp) && tmp_macos=$$(mktemp) && \
		trap 'rm -f "$$tmp_linux" "$$tmp_macos"' EXIT && \
		uv pip compile requirements-dev.txt --constraints requirements-lock.txt --python-platform x86_64-manylinux_2_28 --python-version 3.12 --generate-hashes --no-annotate --custom-compile-command 'make python-lock' --output-file "$$tmp_linux" >/dev/null && \
		uv pip compile requirements-dev.txt --constraints requirements-lock-macos.txt --python-platform aarch64-apple-darwin --python-version 3.12 --generate-hashes --no-annotate --custom-compile-command 'make python-lock' --output-file "$$tmp_macos" >/dev/null && \
		cmp -s requirements-lock.txt "$$tmp_linux" && \
		cmp -s requirements-lock-macos.txt "$$tmp_macos" || \
		{ echo 'Python 依赖锁已漂移，请运行 make python-lock 并重新验证'; exit 1; }

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

sub2api-check: ## 检查 Sub2API Oracle 部署脚本的语法与安全合同
	bash -n scripts/sub2api_oracle_manage.sh
	node --test scripts/sub2api_ops_scripts.test.mjs

jiyu-sub2-replenish: ## 启动 JIYU Sub2 本地补号助手（http://127.0.0.1:18796）
	cd $(CLAWBOT) && $(PYTHON) -m src.sub2_replenish

jiyu-sub2-replenish-dry-run: ## 演练补号助手，只验证解析和页面，不登录或建号
	cd $(CLAWBOT) && $(PYTHON) -m src.sub2_replenish --dry-run

cc-seller-chrome: ## 启动 CC中转闲鱼卖家专用 Chrome，并打开插件加载目录
	node scripts/cc_zhongzhuan_launch_seller_chrome.mjs --copy-token

cc-seller-bridge: ## 启动 CC中转闲鱼卖家本机桥接器，负责自动发卡/确认发货/恢复可售
	node scripts/cc_zhongzhuan_seller_bridge.mjs

cc-seller-auto: cc-seller-chrome ## 启动卖家专用浏览器后，运行一次本机桥接巡检
	node scripts/cc_zhongzhuan_seller_bridge.mjs --once

backup-run: ## 立即生成本机备份并完成一次只读恢复演练
	bash scripts/manage_backup_launchagent.sh run

backup-schedule-install: ## 安装每天 03:30 自动备份和恢复演练
	bash scripts/manage_backup_launchagent.sh install

backup-schedule-status: ## 查看每日备份任务是否已安装和加载
	bash scripts/manage_backup_launchagent.sh status

backup-schedule-uninstall: ## 卸载每日备份任务（不删除已有备份）
	bash scripts/manage_backup_launchagent.sh uninstall

backup-restore-drill: ## 校验最近备份可恢复，但不覆盖现有文件
	bash scripts/disaster_recovery.sh --drill

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

tauri-build: ## 构建并事务式安装 Tauri 桌面端（失败自动恢复旧版）
	bash scripts/tauri_build_install.sh

tauri-rollback-check: ## 只读验证上一版桌面回滚副本
	bash scripts/tauri_rollback.sh --check

tauri-rollback: ## 显式回滚到上一版桌面应用
	bash scripts/tauri_rollback.sh --confirm

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
ci-local: ## 一键本地 CI 验证（含临时目录干净安装）
	@echo "══════ [1/11] Security + Dependency Gates ══════"
	$(MAKE) python-lock-check
	$(MAKE) security-check
	@echo ""
	@echo "══════ [2/11] Clean Install ══════"
	$(MAKE) clean-install-check
	@echo ""
	@echo "══════ [3/11] Python Lint (ruff) ══════"
	cd $(CLAWBOT) && $(PYTHON) -m ruff check src/ --config ruff.toml
	@echo ""
	@echo "══════ [4/11] Python Tests (pytest) ══════"
	cd $(CLAWBOT) && $(PYTHON) -m pytest tests/ --tb=short -q \
		-x --timeout=120 --cov=src --cov-report=term --cov-fail-under=40
	$(MAKE) critical-coverage-check
	@echo ""
	@echo "══════ [5/11] Python Syntax Check ══════"
	cd $(CLAWBOT) && $(PYTHON) -m py_compile multi_main.py
	cd $(CLAWBOT) && find src/ -name "*.py" -exec $(PYTHON) -m py_compile {} +
	@echo ""
	@echo "══════ [6/11] Frist-API Tests ══════"
	cd $(FRIST_API) && npm test
	@echo ""
	@echo "══════ [7/11] Desktop Security Boundary Tests ══════"
	node --test \
		$(FRONTEND)/src/lib/security-hardening.static.test.mjs \
		$(FRONTEND)/src/components/Social/social-growth-feedback.static.test.mjs \
		scripts/auto_ops_scripts.test.mjs
	@echo ""
	@echo "══════ [8/11] Frontend TypeScript Check ══════"
	cd $(FRONTEND) && npx tsc --noEmit
	@echo ""
	@echo "══════ [9/11] Frontend Lint + Production Build ══════"
	cd $(FRONTEND) && npm run lint && npm run build
	@echo ""
	@echo "══════ [10/11] Desktop Rust Tests + Compile Check ══════"
	cd $(FRONTEND)/src-tauri && cargo test --locked && cargo check --locked
	@echo ""
	@echo "══════ [11/11] Docs Governance Check ══════"
	bash scripts/check_docs_layout.sh
	@echo ""
	@echo "✅ 本地 CI 全部通过"

syntax-check: ## 仅检查 Python 语法
	cd $(CLAWBOT) && $(PYTHON) -m py_compile multi_main.py
	cd $(CLAWBOT) && find src/ -name "*.py" -exec $(PYTHON) -m py_compile {} +

# R01 基础设施与文件治理审计

> **轮次**: R1 | **状态**: 待执行 | **预估条目**: ~40
> **审计角色**: CTO + VP Engineering + DevOps Lead
> **前置条件**: 无
> **验证基线**: `cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5`

---

## 1.1 Git 仓库治理（7 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.01 | 冗余 | `.gitignore` | 检查是否覆盖所有应忽略目录（.venv/node_modules/__pycache__/.env/dist/build等），对比 GitHub Python+Node 官方 gitignore 模板 | `git status --porcelain` 无脏文件 | ⬜ |
| R1.02 | 冗余 | 根目录 | 检查 `cleanup-redundant.sh` 是否仍需保留，内容是否过时 | 读取脚本内容，判断是否可删除 | ⬜ |
| R1.03 | 配置 | `.editorconfig` | 验证 indent_style/size/charset/end_of_line 与项目实际一致 | 对比 Python(4空格) + TS(2空格) + Rust(4空格) 实际缩进 | ⬜ |
| R1.04 | 冗余 | `.clinerules` / `.cursorrules` | 检查是否与 AGENTS.md 重复，内容是否过时 | 读取对比，如过时则删除 | ⬜ |
| R1.05 | 配置 | `.pre-commit-config.yaml` | 验证 hooks 配置是否匹配当前 Python/ruff/pytest 版本 | `pre-commit run --all-files` | ⬜ |
| R1.06 | 冗余 | 根目录 | 搜索根目录下所有非必要文件（临时文件、截图、旧审计产物等） | `ls -la` 逐一审查 | ⬜ |
| R1.07 | 文档 | `README.md` | 检查 README 是否反映当前项目状态，安装/运行说明是否可用 | 按 README 步骤模拟执行 | ⬜ |

## 1.2 CI/CD 流水线（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.08 | 配置 | `.github/workflows/ci.yml` | 验证 Python 版本(3.12)、依赖安装命令、pytest 参数、覆盖率上传 | 对照 GitHub Actions 官方文档 | ⬜ |
| R1.09 | 配置 | `.github/workflows/ci.yml` | 验证前端 typecheck job：Node 版本(20)、npm ci、tsc --noEmit | 对照实际 package.json engines 字段 | ⬜ |
| R1.10 | 冗余 | `packages/clawbot/.github/workflows/ci.yml` | 子包内嵌套的 CI 配置是否与根目录重复 | 对比两个 ci.yml 内容 | ⬜ |
| R1.11 | 配置 | `packages/clawbot/kiro-gateway/.github/workflows/docker.yml` | Kiro Gateway Docker 构建 CI 是否有效 | 读取配置验证 | ⬜ |
| R1.12 | 设计 | CI 全局 | 是否缺少 lint(ruff)、安全扫描(safety/bandit)、Docker 构建测试 | 对照业界最佳实践 | ⬜ |
| R1.13 | 设计 | CI 全局 | PR 合并保护规则：是否要求 CI 通过才能合并 | 检查 GitHub 分支保护设置 | ⬜ |

## 1.3 Docker 容器化（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.14 | 安全 | `packages/clawbot/Dockerfile` | 基础镜像版本是否最新、是否使用 non-root 用户、多阶段构建是否合理 | 对照 Docker 官方最佳实践 | ⬜ |
| R1.15 | 配置 | `docker-compose.yml` | Redis 7.2 配置：内存限制(128M)、持久化策略、密码保护 | 对照 Redis 官方文档 | ⬜ |
| R1.16 | 配置 | `docker-compose.yml` | OpenClaw 主服务：端口映射、卷挂载、环境变量传递、资源限制(1G) | 验证本地 docker-compose config | ⬜ |
| R1.17 | 安全 | `docker-compose.yml` | 网络架构：公网+内网隔离是否正确，不必要的端口是否暴露 | 检查 networks 定义 | ⬜ |
| R1.18 | 配置 | `docker-compose.newapi.yml` | New-API LLM 网关配置是否正确(v0.12.6) | 检查端口/环境变量/资源限制 | ⬜ |
| R1.19 | 配置 | `packages/clawbot/docker-compose.goofish.yml` | 闲鱼服务 Docker 配置 | 读取验证 | ⬜ |
| R1.20 | 配置 | `packages/clawbot/docker-compose.mediacrawler.yml` | MediaCrawler 服务配置 | 读取验证 | ⬜ |
| R1.21 | 配置 | `packages/clawbot/kiro-gateway/Dockerfile` | Kiro Gateway 镜像配置 | 对照最佳实践 | ⬜ |

## 1.4 依赖管理（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.22 | 安全 | `packages/clawbot/requirements.txt` | 扫描已知 CVE（重点 diskcache HI-388） | `pip audit` 或 `safety check` | ⬜ |
| R1.23 | 依赖 | `packages/clawbot/requirements.txt` | 检查版本锁定：是否所有依赖都 pin 了精确版本 | 逐行检查 `==` vs `>=` | ⬜ |
| R1.24 | 冗余 | `packages/clawbot/requirements.txt` | 检查是否有未使用的依赖（对照 import 实际使用情况） | `pip-autoremove` 或手动扫描 | ⬜ |
| R1.25 | 依赖 | `apps/openclaw-manager-src/package.json` | 前端依赖版本检查，是否有已知漏洞 | `npm audit` | ⬜ |
| R1.26 | 依赖 | `apps/openclaw-manager-src/src-tauri/Cargo.toml` | Rust 依赖版本检查 | `cargo audit` | ⬜ |
| R1.27 | 文档 | `docs/registries/DEPENDENCY_MAP.md` | 依赖注册表是否与实际 requirements.txt/package.json 一致 | 对比文件 | ⬜ |

## 1.5 文档体系治理（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.28 | 文档 | `docs/PROJECT_MAP.md` | 是否反映当前真实架构（文件数、模块数、命令数等） | 对比实际 `find` 结果 | ⬜ |
| R1.29 | 文档 | `docs/registries/MODULE_REGISTRY.md` | 模块注册表是否与 `src/` 下实际模块对齐 | 对比 `ls src/` 结果 | ⬜ |
| R1.30 | 文档 | `docs/registries/COMMAND_REGISTRY.md` | 命令注册表是否与代码中注册的命令一致 | 对比 `multi_main.py` 命令列表 | ⬜ |
| R1.31 | 文档 | `docs/registries/API_POOL_REGISTRY.md` | API 池注册表是否反映当前 LLM 路由配置 | 对比 `llm_routing.json` | ⬜ |
| R1.32 | 文档 | `docs/status/HEALTH.md` | 健康文档是否有过时条目（已修复但未标记） | 逐条验证 | ⬜ |
| R1.33 | 冗余 | `docs/` 全目录 | 是否存在过时/重复/废弃的文档文件 | 列出所有 .md 文件，逐一判断 | ⬜ |
| R1.34 | 文档 | `docs/CHANGELOG.md` / `docs/CHANGELOG/` | CHANGELOG 格式是否统一，是否有缺失条目 | 检查格式一致性 | ⬜ |
| R1.35 | 文档 | `AGENTS.md` | 主入口文档是否与当前项目状态一致 | 对比实际目录结构 | ⬜ |

## 1.6 环境与配置（5 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R1.36 | 配置 | `packages/clawbot/config/.env.example` | 模板是否完整，每个变量是否有注释说明 | 对比实际 .env 使用的变量 | ⬜ |
| R1.37 | 安全 | 根目录 + 子目录 | 确认无 .env 文件被 git 跟踪 | `git ls-files | grep -i env` | ⬜ |
| R1.38 | 配置 | `Makefile` | Make 目标是否可用，帮助文档是否准确 | `make help` 或读取 Makefile | ⬜ |
| R1.39 | 配置 | `opencode.json` | OpenCode 编辑器配置是否正确 | 读取验证 | ⬜ |
| R1.40 | 配置 | `packages/clawbot/ruff.toml` + `pytest.ini` | Linter 和测试配置是否与项目规范匹配 | 对照代码规范 | ⬜ |

---

## 执行检查清单

- [ ] 基线快照：记录审计前的测试通过数
- [ ] 每个条目完成后标记 ✅ 并记录置信度
- [ ] 每次修复后运行回归测试
- [ ] 审计完成后更新 HEALTH.md + CHANGELOG.md
- [ ] 清理所有发现的冗余文件并提交

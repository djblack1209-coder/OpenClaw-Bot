# Kiro Gateway — 生产 Dockerfile
# 多阶段构建: builder 安装依赖 → runtime 最小镜像
# 使用: docker compose build kiro-gateway

# ── Stage 1: 构建依赖 ────────────────────────────────
FROM python:3.10-slim AS builder

WORKDIR /build

# 系统依赖 (编译某些 pip 包可能需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: 运行时镜像 ──────────────────────────────
FROM python:3.10-slim AS runtime

# 非 root 用户
RUN groupadd -r kiro && useradd -r -g kiro -d /app -s /sbin/nologin kiro

WORKDIR /app

# 从 builder 阶段复制已安装的依赖（不携带编译工具链）
COPY --from=builder /install /usr/local

# 复制应用代码
COPY --chown=kiro:kiro . .

# 创建运行时目录并设置权限
RUN mkdir -p /app/debug_logs && \
    chown -R kiro:kiro /app/debug_logs

# 切换到非 root 用户
USER kiro

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# 健康检查 (使用标准库，不依赖第三方包)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-u", "main.py"]

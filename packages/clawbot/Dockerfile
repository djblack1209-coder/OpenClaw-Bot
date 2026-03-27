# OpenClaw Bot — 生产 Dockerfile
# 多阶段构建: builder 安装依赖 → runtime 最小镜像
# 使用: docker compose build openclaw

# ── Stage 1: 构建依赖 ────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# 系统依赖 (编译某些 pip 包需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: 运行时镜像 ──────────────────────────────
FROM python:3.12-slim AS runtime

# 非 root 用户
RUN groupadd -r clawbot && useradd -r -g clawbot -d /app -s /sbin/nologin clawbot

WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /install /usr/local

# 复制应用代码 (排除通过 .dockerignore 控制)
COPY --chown=clawbot:clawbot . .

# 创建运行时目录
RUN mkdir -p /app/data /app/logs && \
    chown -R clawbot:clawbot /app/data /app/logs

# 切换到非 root 用户
USER clawbot

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18790/api/v1/ping')" || exit 1

# 暴露端口
EXPOSE 18790 9090

# 启动命令
CMD ["python", "-u", "multi_main.py"]

# OpenClaw Bot — 生产 Dockerfile
# 多阶段构建: builder 安装依赖 → runtime 最小镜像
# 使用: docker compose build openclaw

# ── Stage 1: 构建依赖 ────────────────────────────────
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

WORKDIR /build

# 只接受 Linux 哈希锁；仅对没有 Python 3.12/Linux wheel 的六个纯 Python 包放开已哈希源码包。
COPY requirements-lock.txt .
RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes --only-binary=:all: --no-binary=jieba,jsonpath,pyjsparser,sgmllib3k,snownlp,ta --prefix=/install -r requirements-lock.txt

# ── Stage 2: 运行时镜像 ──────────────────────────────
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

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
    CMD python -c "import os, urllib.request; request = urllib.request.Request('http://localhost:18790/api/v1/ping', headers={'X-API-Token': os.environ.get('OPENCLAW_API_TOKEN', '')}); urllib.request.urlopen(request, timeout=8)" || exit 1

# 暴露端口
EXPOSE 18790 9090

# 启动命令
CMD ["python", "-u", "multi_main.py"]

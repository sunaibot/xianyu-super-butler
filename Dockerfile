# ============================================
# 闲鱼自动回复系统 - Dockerfile
# 多阶段构建：前端构建 → Python构建 → 运行时
# 自动检测国内环境并启用镜像加速
# ============================================

FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    DOCKER_ENV=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# ---------- 阶段1: 前端构建 ----------
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

# 国内源加速（可通过 build-arg 控制）
ARG USE_CN_MIRROR=true
RUN if [ "$USE_CN_MIRROR" = "true" ]; then \
        npm config set registry https://registry.npmmirror.com; \
    fi

COPY frontend/package.json frontend/pnpm-lock.yaml ./
# 使用 pnpm 9（无 ERR_PNPM_IGNORED_BUILDS 严格策略），兼容 v9 lockfile 格式
RUN npm install -g pnpm@9 && pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

# ---------- 共享阶段: 国内镜像配置（builder 与 runtime 共用，消除重复 sed 命令）----------
FROM base AS cn-mirror

ARG USE_CN_MIRROR=true
RUN if [ "$USE_CN_MIRROR" = "true" ]; then \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources; \
        fi && \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list; \
        fi; \
    fi

# apt 超时与重试配置（应对国内访问 deb.debian.org 偶发 502 Bad Gateway）
RUN echo 'Acquire::http::Timeout "120";' > /etc/apt/apt.conf.d/99timeout && \
    echo 'Acquire::https::Timeout "120";' >> /etc/apt/apt.conf.d/99timeout && \
    echo 'Acquire::Retries "3";' >> /etc/apt/apt.conf.d/99timeout

# ---------- 阶段2: Python 依赖构建 ----------
FROM cn-mirror AS builder

ARG USE_CN_MIRROR=true

# pip 国内源
RUN if [ "$USE_CN_MIRROR" = "true" ]; then \
        echo '[global]' > /etc/pip.conf && \
        echo 'index-url = https://pypi.tuna.tsinghua.edu.cn/simple' >> /etc/pip.conf; \
    fi

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 复制前端构建产物
COPY --from=frontend-builder /static/ ./static/

# 确保运行时 JS 文件存在（防止被前端构建覆盖）
COPY static/xianyu_js_version_2.js ./static/

# ---------- 阶段3: 运行时 ----------
FROM cn-mirror AS runtime

LABEL maintainer="zhinianboke" \
      version="3.0.0" \
      description="闲鱼自动回复系统" \
      repository="https://github.com/zhinianboke/xianyu-auto-reply"

# 安装运行时依赖
# - nodejs: PyExecJS 执行 JS 所需
# - gosu: 以 root 启动→chown 挂载卷→降权到非 root 用户运行应用（最小权限）
# - Playwright 依赖: 浏览器自动化
# - 图像处理: Pillow 所需
# - OpenCV 运行时
RUN apt-get update && \
    apt-get install -y --no-install-recommends --fix-missing \
        nodejs \
        npm \
        tzdata \
        curl \
        ca-certificates \
        gosu \
        libjpeg-dev \
        libpng-dev \
        libfreetype6-dev \
        fonts-dejavu-core \
        fonts-liberation \
        libnss3 \
        libnspr4 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libatspi2.0-0 \
        libgtk-3-0 \
        libgdk-pixbuf2.0-0 \
        libxcursor1 \
        libxi6 \
        libxrender1 \
        libxext6 \
        libx11-6 \
        libxft2 \
        libxinerama1 \
        libxtst6 \
        libappindicator3-1 \
        libx11-xcb1 \
        libxfixes3 \
        xdg-utils \
        libgl1 \
        libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 验证安装
RUN node --version && npm --version

# 从构建阶段复制 Python 虚拟环境（不常变化，放前面利用缓存）
COPY --from=builder /opt/venv /opt/venv

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"

# 安装 Playwright Chromium（在 COPY /app 之前，避免代码修改触发重新下载）
RUN playwright install chromium

# 从构建阶段复制应用代码（经常变化，放后面）
COPY --from=builder /app /app

# 创建非 root 运行用户（UID/GID 1000，与常见宿主用户对齐，便于 bind-mount 权限）
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# 创建运行时目录并收敛权限（不再使用 777）
RUN mkdir -p /app/logs /app/data /app/backups /app/static/uploads/images && \
    chown -R appuser:appgroup /app /ms-playwright && \
    chmod -R u+rwX,g+rwX,o-rwx /app/logs /app/data /app/backups /app/static/uploads

# 安全配置
RUN echo "ulimit -c 0" >> /etc/profile

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 启动：entrypoint 以 root 启动（用于 chown 挂载卷），随后降权到 appuser
# 修正 Windows CRLF 行尾（避免 exec format error）
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]

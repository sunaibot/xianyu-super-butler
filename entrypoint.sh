#!/bin/bash
set -e

echo "=========================================="
echo "闲鱼自动回复系统 - Docker 启动脚本"
echo "=========================================="

# 确保必要的目录存在
mkdir -p /app/logs /app/data /app/backups /app/static/uploads/images

# 设置权限
chmod -R 777 /app/logs /app/data /app/backups 2>/dev/null || true
chmod -R 777 /app/static/uploads 2>/dev/null || true

echo "[1/3] 检查环境..."
echo "Python版本: $(python --version)"
echo "Node.js版本: $(node --version)"
echo "当前工作目录: $(pwd)"

# 检查必要的文件
if [ ! -f "/app/Start.py" ]; then
    echo "错误: Start.py 不存在"
    exit 1
fi

# 检查虚拟环境
if [ -d "/opt/venv" ]; then
    echo "[2/3] 激活虚拟环境..."
    source /opt/venv/bin/activate
else
    echo "[2/3] 警告: 虚拟环境不存在，使用系统Python"
fi

# 确保静态文件目录存在
if [ ! -f "/app/static/index.html" ]; then
    echo "警告: static/index.html 不存在，前端可能未正确构建"
fi

echo "[3/3] 启动应用..."
echo "=========================================="

# 使用 exec 启动，使进程成为 PID 1
exec python /app/Start.py

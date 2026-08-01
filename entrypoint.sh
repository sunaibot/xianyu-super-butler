#!/bin/bash
set -e

echo "=========================================="
echo "闲鱼自动回复系统 - Docker 启动脚本"
echo "=========================================="

# 以 root 身份创建/修正挂载卷目录权限，随后降权到非 root 用户运行应用
mkdir -p /app/logs /app/data /app/backups /app/static/uploads/images
# 仅将应用自身目录与挂载卷归属调整为 appuser，最小权限原则
chown -R appuser:appgroup /app/logs /app/data /app/backups /app/static/uploads 2>/dev/null || true
chmod -R u+rwX,g+rwX /app/logs /app/data /app/backups /app/static/uploads 2>/dev/null || true

echo "[1/4] 检查环境..."
echo "Python: $(python --version)"
echo "Node.js: $(node --version)"
echo "工作目录: $(pwd)"

if [ ! -f "/app/Start.py" ]; then
    echo "错误: Start.py 不存在"
    exit 1
fi

if [ -d "/opt/venv" ]; then
    echo "[2/4] 激活虚拟环境..."
    source /opt/venv/bin/activate
else
    echo "[2/4] 警告: 虚拟环境不存在"
fi

if [ ! -f "/app/static/index.html" ]; then
    echo "警告: static/index.html 不存在，前端可能未正确构建"
fi

echo "[3/4] 初始化管理员..."
if [ -f "/app/init_admin_noninteractive.py" ]; then
    gosu appuser python /app/init_admin_noninteractive.py || echo "[WARN] 管理员初始化脚本执行失败"
else
    echo "[WARN] init_admin_noninteractive.py 不存在，跳过"
fi

echo "[4/4] 启动应用（非 root 用户 appuser）..."
echo "=========================================="

# 降权到 appuser 运行主进程，实现最小权限
exec gosu appuser python /app/Start.py

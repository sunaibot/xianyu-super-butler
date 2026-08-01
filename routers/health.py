"""
routers/health.py
=================
健康检查路由（从 reply_server.py 迁移）。

路由清单：
- GET /health  健康检查端点，用于 Docker 健康检查和负载均衡器

设计要点：
- 无需认证（公开端点）
- 检查 CookieManager 状态、数据库连接、系统资源（CPU/内存）
- 不健康时返回 503
"""
import time

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["system"])


@router.get('/health')
async def health_check():
    """健康检查端点，用于Docker健康检查和负载均衡器"""
    try:
        import cookie_manager

        # 检查Cookie管理器状态
        manager_status = "ok" if cookie_manager.manager is not None else "error"

        # 检查数据库连接（轻量 SELECT 1，不拉全表）
        from db_manager import db_manager
        try:
            import sqlite3
            conn = sqlite3.connect(db_manager.db_path, check_same_thread=False)
            conn.execute("SELECT 1")
            conn.close()
            db_status = "ok"
        except Exception:
            db_status = "error"

        # 获取系统状态（interval=None 非阻塞，返回上次调用以来的 CPU 使用率）
        import psutil
        cpu_percent = psutil.cpu_percent(interval=None)
        memory_info = psutil.virtual_memory()

        status = {
            "status": "healthy" if manager_status == "ok" and db_status == "ok" else "unhealthy",
            "timestamp": time.time(),
            "services": {
                "cookie_manager": manager_status,
                "database": db_status,
            },
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_info.percent,
                "memory_available": memory_info.available,
            },
        }

        if status["status"] == "unhealthy":
            raise HTTPException(status_code=503, detail=status)

        return status

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": time.time(),
            "error": str(e),
        }

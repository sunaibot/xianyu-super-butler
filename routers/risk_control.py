"""
routers/risk_control.py
=======================
风控日志路由（从 reply_server.py 迁移）。

路由清单（全部管理员专用）：
- GET    /risk-control-logs          获取风控日志列表（支持 cookie_id 过滤 + 分页）
- DELETE /risk-control-logs/{log_id} 删除单条风控日志
- GET    /admin/risk-control-logs    获取风控日志列表（与 /risk-control-logs 实现一致，管理员路径别名）

设计要点：
- 权限：全部 require_admin
- DBManager 已委托 risk_control_repo，路由层仅调用 db_manager.* 即可
- /risk-control-logs 与 /admin/risk-control-logs 实现完全一致（保留两个路径以兼容前端）
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from loguru import logger

from .deps import require_admin, safe_client_msg, log_with_user

router = APIRouter(tags=["risk-control"])


def _db():
    from db_manager import db_manager
    return db_manager


# ==================== 风控日志查询/删除 ====================

@router.get("/risk-control-logs")
async def get_risk_control_logs(
    cookie_id: str = None,
    limit: int = 100,
    offset: int = 0,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    """获取风控日志（管理员专用）"""
    try:
        log_with_user('info', f"查询风控日志: cookie_id={cookie_id}, limit={limit}, offset={offset}", admin_user)

        db = _db()
        logs = db.get_risk_control_logs(cookie_id=cookie_id, limit=limit, offset=offset)
        total_count = db.get_risk_control_logs_count(cookie_id=cookie_id)

        log_with_user('info', f"风控日志查询成功，共 {len(logs)} 条记录，总计 {total_count} 条", admin_user)

        return {
            "success": True,
            "data": logs,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        log_with_user('error', f"获取风控日志失败: {str(e)}", admin_user)
        return {
            "success": False,
            "message": safe_client_msg(e, "获取风控日志失败"),
            "data": [],
            "total": 0,
        }


@router.delete("/risk-control-logs/{log_id}")
async def delete_risk_controllog_with_user(
    log_id: int,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    """删除风控日志记录（管理员专用）"""
    try:
        log_with_user('info', f"删除风控日志记录: {log_id}", admin_user)

        success = _db().delete_risk_controllog_with_user(log_id)

        if success:
            log_with_user('info', f"风控日志删除成功: {log_id}", admin_user)
            return {"success": True, "message": "删除成功"}
        log_with_user('warning', f"风控日志删除失败: {log_id}", admin_user)
        return {"success": False, "message": "删除失败，记录可能不存在"}

    except Exception as e:
        log_with_user('error', f"删除风控日志失败: {log_id} - {str(e)}", admin_user)
        return {"success": False, "message": safe_client_msg(e, "删除失败")}


# ==================== 管理员路径别名 ====================

@router.get("/admin/risk-control-logs")
async def get_admin_risk_control_logs(
    cookie_id: str = None,
    limit: int = 100,
    offset: int = 0,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    """获取风控日志（管理员专用，/admin 路径别名）"""
    try:
        log_with_user('info', f"查询风控日志: cookie_id={cookie_id}, limit={limit}, offset={offset}", admin_user)

        db = _db()
        logs = db.get_risk_control_logs(cookie_id=cookie_id, limit=limit, offset=offset)
        total_count = db.get_risk_control_logs_count(cookie_id=cookie_id)

        log_with_user('info', f"风控日志查询成功，共 {len(logs)} 条记录，总计 {total_count} 条", admin_user)

        return {
            "success": True,
            "data": logs,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        log_with_user('error', f"查询风控日志失败: {str(e)}", admin_user)
        return {
            "success": False,
            "message": safe_client_msg(e, "查询失败"),
            "data": [],
            "total": 0,
        }

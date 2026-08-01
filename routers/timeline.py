"""
routers/timeline.py
==================
订单状态变更时间线 router。

GET /api/orders/{order_id}/timeline
  return: [{ status, timestamp, note }]

委托 order_repo.get_order_by_id + get_order_status_logs，
无 order_status_logs 表时降级为单条记录。
"""
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .deps import require_auth, server_error
from db_manager import db_manager

router = APIRouter(prefix="/api/orders", tags=["订单时间线"])


class TimelineEntry(BaseModel):
    status: str
    timestamp: str
    note: str = ""


@router.get("/{order_id}/timeline")
async def get_order_timeline(order_id: str, _: dict = Depends(require_auth)):
    """获取订单状态变更时间线"""
    try:
        order = db_manager.get_order_by_id(order_id)
        if not order:
            return {"success": False, "message": "订单不存在"}

        current_status = order.get("status") or order.get("order_status") or ""
        created_at = order.get("created_at") or ""
        updated_at = order.get("updated_at") or created_at

        # 优先查询 order_status_logs 表（表不存在时 repo 降级返回空列表）
        timeline: List[dict] = db_manager.get_order_status_logs(order_id)

        # 降级：至少返回创建与当前状态
        if not timeline:
            timeline = [
                {"status": "created", "timestamp": str(created_at), "note": "订单创建"},
            ]
            if current_status:
                timeline.append({
                    "status": current_status,
                    "timestamp": str(updated_at or created_at),
                    "note": "最近状态",
                })

        return {"success": True, "data": timeline}
    except Exception as e:
        raise server_error(e, "查询订单时间线")

"""
routers/batch.py
================
通用批量操作 router。

POST /api/batch
  body: { entity: 'order'|'item'|'card', action: 'delete'|'enable'|'disable', ids: [...], payload: {} }
  return: { success_count, failed_count, failures: [] }

内部委托给 db_manager（→ 各 repository），统一批量入口。
"""
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from loguru import logger

from .deps import require_auth, server_error, client_error
from db_manager import db_manager

router = APIRouter(prefix="/api/batch", tags=["批量操作"])


class BatchRequest(BaseModel):
    entity: str = Field(..., description="操作实体：order/item/card/account")
    action: str = Field(..., description="操作动作：delete/enable/disable/refresh")
    ids: List[str] = Field(..., min_length=1, max_length=100, description="目标 ID 列表")
    payload: Optional[dict] = Field(default=None, description="附加参数")


# 处理器签名: (id: str, payload: dict) -> bool
def _delete_item(item_id: str, payload: dict) -> bool:
    """商品删除：委托 item_repo，自动回查 cookie_id"""
    cookie_id = (payload or {}).get("cookie_id")
    if not cookie_id:
        # 回查商品的 cookie_id
        item = db_manager.get_item_by_id(item_id)
        if item:
            cookie_id = item.get("cookie_id")
    if not cookie_id:
        logger.warning(f"[batch] 删除商品 {item_id} 失败：未提供且无法回查 cookie_id")
        return False
    return bool(db_manager.delete_item_info(cookie_id, item_id))


def _delete_order(order_id: str, payload: dict) -> bool:
    """订单删除：委托 order_repo"""
    return bool(db_manager.delete_order(order_id))


def _delete_card(card_id: str, payload: dict) -> bool:
    """卡密删除：委托 card_repo"""
    try:
        return bool(db_manager.delete_card(int(card_id)))
    except (TypeError, ValueError) as e:
        logger.warning(f"[batch] 删除卡密 {card_id} 失败：{e}")
        return False


def _enable_account(cookie_id: str, payload: dict) -> bool:
    """账号启用/禁用切换"""
    enabled = bool((payload or {}).get("enabled", True))
    try:
        if hasattr(db_manager, "update_account_status"):
            return bool(db_manager.update_account_status(cookie_id, enabled))
        return bool(db_manager.save_cookie_status(cookie_id, enabled))
    except Exception as e:
        logger.warning(f"[batch] 切换账号 {cookie_id} 状态失败: {e}")
        return False


# 处理器注册表（插件化：后续可扩展）
HANDLERS = {
    ("item", "delete"): _delete_item,
    ("order", "delete"): _delete_order,
    ("card", "delete"): _delete_card,
    ("account", "enable"): _enable_account,
    ("account", "disable"): lambda id, p: _enable_account(id, {**(p or {}), "enabled": False}),
}


@router.post("")
async def batch_operate(req: BatchRequest, user: dict = Depends(require_auth)):
    """通用批量操作入口"""
    key = (req.entity, req.action)
    handler = HANDLERS.get(key)
    if not handler:
        raise client_error(
            ValueError(f"不支持的批量操作：{req.entity}/{req.action}"),
            "批量操作"
        )

    success_count = 0
    failures = []
    for target_id in req.ids:
        try:
            ok = handler(target_id, req.payload or {})
            if ok:
                success_count += 1
            else:
                failures.append({"id": target_id, "reason": "操作未生效"})
        except Exception as e:
            failures.append({"id": target_id, "reason": str(e)[:100]})

    logger.info(
        f"[batch] 用户 {user.get('username')} 批量{req.action} {req.entity}: "
        f"成功 {success_count}/{len(req.ids)}"
    )
    return {
        "success": True,
        "success_count": success_count,
        "failed_count": len(failures),
        "failures": failures,
    }

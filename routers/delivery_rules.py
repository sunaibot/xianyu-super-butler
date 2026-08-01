"""
routers/delivery_rules.py
========================
发货规则路由（从 reply_server.py 迁移）。

路由清单：
- GET    /delivery-rules             获取发货规则列表（含卡券名称/类型）
- POST   /delivery-rules             创建发货规则
- GET    /delivery-rules/{rule_id}   获取单个发货规则详情
- PUT    /delivery-rules/{rule_id}   更新发货规则
- DELETE /delivery-rules/{rule_id}   删除发货规则

设计要点：
- 用户隔离：列表/详情/更新/删除按 user_id 过滤
- 权限：全部需要登录（require_auth）
- 关键字匹配查询（get_delivery_rules_by_keyword / by_keyword_and_spec）
  仍由 DBManager → DeliveryRuleRepo 提供，供回复流程内部调用，不暴露为路由
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, server_error, client_error, log_with_user

router = APIRouter(tags=["delivery-rules"])


def _db():
    from db_manager import db_manager
    return db_manager


# ------------------------- 列表 / 详情 -------------------------

@router.get("/delivery-rules")
def get_delivery_rules(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取发货规则列表"""
    try:
        user_id = current_user['user_id']
        return _db().get_all_delivery_rules(user_id)
    except Exception as e:
        log_with_user('error', f"获取发货规则列表失败: {e}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/delivery-rules/{rule_id}")
def get_delivery_rule(rule_id: int, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取单个发货规则详情"""
    try:
        user_id = current_user['user_id']
        rule = _db().get_delivery_rule_by_id(rule_id, user_id)
        if rule:
            return rule
        raise HTTPException(status_code=404, detail="发货规则不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"获取发货规则失败: {rule_id} - {e}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ------------------------- 创建 / 更新 / 删除 -------------------------

@router.post("/delivery-rules")
def create_delivery_rule(rule_data: dict, current_user: Dict[str, Any] = Depends(require_auth)):
    """创建发货规则"""
    try:
        user_id = current_user['user_id']
        rule_id = _db().create_delivery_rule(
            keyword=rule_data.get('keyword'),
            card_id=rule_data.get('card_id'),
            delivery_count=rule_data.get('delivery_count', 1),
            enabled=rule_data.get('enabled', True),
            description=rule_data.get('description'),
            user_id=user_id,
        )
        log_with_user('info', f"发货规则创建成功: ID {rule_id}", current_user)
        return {"id": rule_id, "message": "发货规则创建成功"}
    except Exception as e:
        log_with_user('error', f"创建发货规则失败: {e}", current_user)
        raise client_error(e, "创建发货规则")


@router.put("/delivery-rules/{rule_id}")
def update_delivery_rule(rule_id: int, rule_data: dict, current_user: Dict[str, Any] = Depends(require_auth)):
    """更新发货规则"""
    try:
        user_id = current_user['user_id']
        success = _db().update_delivery_rule(
            rule_id=rule_id,
            keyword=rule_data.get('keyword'),
            card_id=rule_data.get('card_id'),
            delivery_count=rule_data.get('delivery_count', 1),
            enabled=rule_data.get('enabled', True),
            description=rule_data.get('description'),
            user_id=user_id,
        )
        if success:
            return {"message": "发货规则更新成功"}
        raise HTTPException(status_code=404, detail="发货规则不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"更新发货规则失败: {rule_id} - {e}", current_user)
        raise server_error(e, "更新发货规则")


@router.delete("/delivery-rules/{rule_id}")
def delete_delivery_rule(rule_id: int, current_user: Dict[str, Any] = Depends(require_auth)):
    """删除发货规则"""
    try:
        user_id = current_user['user_id']
        success = _db().delete_delivery_rule(rule_id, user_id)
        if success:
            log_with_user('info', f"发货规则删除成功: ID {rule_id}", current_user)
            return {"message": "发货规则删除成功"}
        raise HTTPException(status_code=404, detail="发货规则不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除发货规则失败: {rule_id} - {e}", current_user)
        raise server_error(e, "删除发货规则")

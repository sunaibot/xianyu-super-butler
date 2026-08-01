"""
routers/analytics.py
====================
统计分析路由（从 reply_server.py 迁移）。

路由清单：
- GET /api/stats                获取当前用户的统计信息（管理员返回全量，普通用户返回自己的数据）
- GET /analytics/orders         获取订单分析数据（BI报表，支持日期范围筛选）
- GET /analytics/orders/valid   获取有效订单详情列表（用于统计中的订单明细）

设计要点：
- 全部 require_auth（普通登录用户即可访问）
- 管理员返回全量数据，普通用户仅返回自己的数据
- 有效订单状态白名单：pending_ship / shipped / completed
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, log_with_user

router = APIRouter(tags=["analytics"])


def _db():
    from db_manager import db_manager
    return db_manager


# 有效订单状态白名单（只统计这几种状态）
_VALID_STATUSES = ['pending_ship', 'shipped', 'completed']


# ==================== 用户统计 ====================

@router.get('/api/stats')
def get_user_stats(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户的统计信息（管理员返回全量，普通用户返回自己的数据）"""
    try:
        db = _db()
        is_admin = current_user.get('is_admin', False)
        user_id = current_user['user_id']

        if is_admin:
            all_users = db.get_all_users()
            total_users = len(all_users)
        else:
            total_users = 0

        all_cookies = db.get_all_cookies(None if is_admin else user_id)
        total_cookies = len(all_cookies)

        active_cookies = 0
        for cookie_id in all_cookies.keys():
            status = db.get_cookie_status(cookie_id)
            if status:
                active_cookies += 1

        all_cards = db.get_all_cards(None if is_admin else user_id)
        total_cards = len(all_cards) if all_cards else 0

        all_keywords = db.get_all_keywords(None if is_admin else user_id)
        total_keywords = sum(len(kw_list) for kw_list in all_keywords.values())

        total_orders = 0
        try:
            if is_admin:
                orders = db.get_all_orders()
                total_orders = len(orders) if orders else 0
            else:
                user_cookie_ids = list(all_cookies.keys())
                if user_cookie_ids:
                    orders = db.get_orders_for_analytics(
                        user_id=user_id,
                        include_statuses=None,
                    )
                    total_orders = len(orders)
        except Exception:
            pass

        stats = {
            "total_users": total_users,
            "total_cookies": total_cookies,
            "active_cookies": active_cookies,
            "total_cards": total_cards,
            "total_keywords": total_keywords,
            "total_orders": total_orders,
            "is_admin": is_admin,
        }

        return stats

    except Exception as e:
        log_with_user('error', f"获取统计信息失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ==================== BI 报表分析 ====================

@router.get('/analytics/orders')
def get_order_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """
    获取订单分析数据（BI报表）

    Args:
        start_date: 开始日期 (格式: YYYY-MM-DD)
        end_date: 结束日期 (格式: YYYY-MM-DD)
    """
    try:
        db = _db()
        log_with_user('info', f"查询订单分析数据: {start_date} - {end_date}", current_user)

        user_id = current_user['user_id']

        analytics_data = db.get_order_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            include_statuses=_VALID_STATUSES,
        )

        if 'error' in analytics_data:
            log_with_user('error', f"获取订单分析数据失败: {analytics_data['error']}", current_user)
            raise HTTPException(status_code=500, detail=analytics_data['error'])

        log_with_user('info', "订单分析数据查询成功", current_user)
        return analytics_data

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"获取订单分析数据失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get('/analytics/orders/valid')
def get_valid_orders(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """
    获取有效订单详情列表（用于统计中的订单明细）

    Args:
        start_date: 开始日期 (格式: YYYY-MM-DD)
        end_date: 结束日期 (格式: YYYY-MM-DD)
    """
    try:
        db = _db()
        log_with_user('info', f"查询有效订单列表: {start_date} - {end_date}", current_user)

        user_id = current_user['user_id']

        orders = db.get_orders_for_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            include_statuses=_VALID_STATUSES,
        )

        log_with_user('info', f"查询到 {len(orders)} 个有效订单", current_user)
        return {"orders": orders}

    except Exception as e:
        log_with_user('error', f"获取有效订单列表失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")

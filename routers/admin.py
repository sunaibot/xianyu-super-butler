"""
routers/admin.py
================
管理员路由（从 reply_server.py 迁移）。

路由清单：
用户管理：
- GET    /admin/users                获取所有用户信息（含 cookie/card 统计）
- DELETE /admin/users/{user_id}      删除用户（含级联数据清理，不能删自己）

系统统计：
- GET    /admin/stats                获取系统统计信息（用户/cookie/卡券/关键词/订单）

数据表管理：
- GET    /admin/data/{table_name}        获取指定表的所有数据（白名单校验）
- DELETE /admin/data/{table_name}/{record_id}  删除指定表的指定记录（含管理员保护）
- DELETE /admin/data/{table_name}        清空指定表的所有数据（不允许清空 users 表）

设计要点：
- 全部 require_admin（管理员专用）
- 表名白名单校验，防止任意表访问
- 删除用户时不能删除管理员自己
- 清空表时不允许清空 users 表
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_admin, log_with_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _db():
    from db_manager import db_manager
    return db_manager


# 允许查询的表白名单（GET /admin/data/{table_name}）
_ALLOWED_TABLES_READ = [
    'users', 'cookies', 'cookie_status', 'keywords', 'default_replies', 'default_reply_records',
    'ai_reply_settings', 'ai_conversations', 'ai_item_cache', 'item_info',
    'message_notifications', 'cards', 'delivery_rules', 'notification_channels',
    'user_settings', 'system_settings', 'email_verifications', 'captcha_codes', 'orders',
    'item_replay', 'risk_control_logs', 'knowledge_base_scripts',
]

# 允许删除单条记录的表白名单（DELETE /admin/data/{table_name}/{record_id}）
_ALLOWED_TABLES_DELETE_RECORD = [
    'users', 'cookies', 'cookie_status', 'keywords', 'default_replies', 'default_reply_records',
    'ai_reply_settings', 'ai_conversations', 'ai_item_cache', 'item_info',
    'message_notifications', 'cards', 'delivery_rules', 'notification_channels',
    'user_settings', 'system_settings', 'email_verifications', 'captcha_codes', 'orders',
    'item_replay',
]

# 允许清空的表白名单（DELETE /admin/data/{table_name}）
_ALLOWED_TABLES_CLEAR = [
    'cookies', 'cookie_status', 'keywords', 'default_replies', 'default_reply_records',
    'ai_reply_settings', 'ai_conversations', 'ai_item_cache', 'item_info',
    'message_notifications', 'cards', 'delivery_rules', 'notification_channels',
    'user_settings', 'system_settings', 'email_verifications', 'captcha_codes', 'orders',
    'item_replay', 'risk_control_logs',
]


# ==================== 用户管理 ====================

@router.get("/users")
def get_all_users(admin_user: Dict[str, Any] = Depends(require_admin)):
    """获取所有用户信息（管理员专用，含 cookie/card 统计，隐藏密码字段）"""
    try:
        log_with_user('info', "查询所有用户信息", admin_user)
        db = _db()
        users = db.get_all_users()

        # 为每个用户添加统计信息
        for user in users:
            user_id = user['id']
            # 统计用户的Cookie数量
            user_cookies = db.get_all_cookies(user_id)
            user['cookie_count'] = len(user_cookies)

            # 统计用户的卡券数量
            user_cards = db.get_all_cards(user_id)
            user['card_count'] = len(user_cards) if user_cards else 0

            # 隐藏密码字段
            if 'password_hash' in user:
                del user['password_hash']

        log_with_user('info', f"返回用户信息，共 {len(users)} 个用户", admin_user)
        return {"users": users}
    except Exception as e:
        log_with_user('error', f"获取用户信息失败: {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin_user: Dict[str, Any] = Depends(require_admin)):
    """删除用户（管理员专用，含级联数据清理，不能删除管理员自己）"""
    try:
        db = _db()
        # 不能删除管理员自己
        if user_id == admin_user['user_id']:
            log_with_user('warning', "尝试删除管理员自己", admin_user)
            raise HTTPException(status_code=400, detail="不能删除管理员自己")

        # 获取要删除的用户信息
        user_to_delete = db.get_user_by_id(user_id)
        if not user_to_delete:
            raise HTTPException(status_code=404, detail="用户不存在")

        log_with_user('info', f"准备删除用户: {user_to_delete['username']} (ID: {user_id})", admin_user)

        # 删除用户及其相关数据
        success = db.delete_user_and_data(user_id)

        if success:
            log_with_user('info', f"用户删除成功: {user_to_delete['username']} (ID: {user_id})", admin_user)
            return {"message": f"用户 {user_to_delete['username']} 删除成功"}
        log_with_user('error', f"用户删除失败: {user_to_delete['username']} (ID: {user_id})", admin_user)
        raise HTTPException(status_code=400, detail="删除失败")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除用户异常: {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ==================== 系统统计 ====================

@router.get("/stats")
def get_system_stats(admin_user: Dict[str, Any] = Depends(require_admin)):
    """获取系统统计信息（管理员专用）"""
    try:
        log_with_user('info', "查询系统统计信息", admin_user)
        db = _db()

        # 用户统计
        all_users = db.get_all_users()
        total_users = len(all_users)

        # Cookie统计
        all_cookies = db.get_all_cookies()
        total_cookies = len(all_cookies)

        # 活跃账号统计（启用状态的账号）
        active_cookies = 0
        for cookie_id in all_cookies.keys():
            status = db.get_cookie_status(cookie_id)
            if status:
                active_cookies += 1

        # 卡券统计
        all_cards = db.get_all_cards()
        total_cards = len(all_cards) if all_cards else 0

        # 关键词统计
        all_keywords = db.get_all_keywords()
        total_keywords = sum(len(kw_list) for kw_list in all_keywords.values())

        # 订单统计
        total_orders = 0
        try:
            orders = db.get_all_orders()
            total_orders = len(orders) if orders else 0
        except Exception:
            pass

        stats = {
            "total_users": total_users,
            "total_cookies": total_cookies,
            "active_cookies": active_cookies,
            "total_cards": total_cards,
            "total_keywords": total_keywords,
            "total_orders": total_orders,
        }

        log_with_user('info', f"系统统计信息查询完成: {stats}", admin_user)
        return stats

    except Exception as e:
        log_with_user('error', f"获取系统统计信息失败: {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ==================== 数据表管理 ====================

@router.get("/data/{table_name}")
def get_table_data(table_name: str, admin_user: Dict[str, Any] = Depends(require_admin)):
    """获取指定表的所有数据（管理员专用，白名单校验）"""
    try:
        log_with_user('info', f"查询表数据: {table_name}", admin_user)

        # 验证表名安全性
        if table_name not in _ALLOWED_TABLES_READ:
            log_with_user('warning', f"尝试访问不允许的表: {table_name}", admin_user)
            raise HTTPException(status_code=400, detail="不允许访问该表")

        # 获取表数据
        data, columns = _db().get_table_data(table_name)

        log_with_user('info', f"表 {table_name} 查询成功，共 {len(data)} 条记录", admin_user)

        return {
            "success": True,
            "data": data,
            "columns": columns,
            "count": len(data),
        }

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"查询表数据失败: {table_name} - {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/data/{table_name}/{record_id}")
def delete_table_record(
    table_name: str,
    record_id: str,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    """删除指定表的指定记录（管理员专用，含管理员保护）"""
    try:
        log_with_user('info', f"删除表记录: {table_name}.{record_id}", admin_user)

        # 验证表名安全性
        if table_name not in _ALLOWED_TABLES_DELETE_RECORD:
            log_with_user('warning', f"尝试删除不允许的表记录: {table_name}", admin_user)
            raise HTTPException(status_code=400, detail="不允许操作该表")

        # 特殊保护：不能删除管理员用户
        if table_name == 'users' and record_id == str(admin_user['user_id']):
            log_with_user('warning', "尝试删除管理员自己", admin_user)
            raise HTTPException(status_code=400, detail="不能删除管理员自己")

        # 删除记录
        success = _db().delete_table_record(table_name, record_id)

        if success:
            log_with_user('info', f"表记录删除成功: {table_name}.{record_id}", admin_user)
            return {"success": True, "message": "删除成功"}
        log_with_user('warning', f"表记录删除失败: {table_name}.{record_id}", admin_user)
        raise HTTPException(status_code=400, detail="删除失败，记录可能不存在")

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除表记录异常: {table_name}.{record_id} - {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/data/{table_name}")
def clear_table_data(table_name: str, admin_user: Dict[str, Any] = Depends(require_admin)):
    """清空指定表的所有数据（管理员专用，不允许清空 users 表）"""
    try:
        log_with_user('info', f"清空表数据: {table_name}", admin_user)

        # 不允许清空用户表
        if table_name == 'users':
            log_with_user('warning', "尝试清空用户表", admin_user)
            raise HTTPException(status_code=400, detail="不允许清空用户表")

        if table_name not in _ALLOWED_TABLES_CLEAR:
            log_with_user('warning', f"尝试清空不允许的表: {table_name}", admin_user)
            raise HTTPException(status_code=400, detail="不允许清空该表")

        # 清空表数据
        success = _db().clear_table_data(table_name)

        if success:
            log_with_user('info', f"表数据清空成功: {table_name}", admin_user)
            return {"success": True, "message": "清空成功"}
        log_with_user('warning', f"表数据清空失败: {table_name}", admin_user)
        raise HTTPException(status_code=400, detail="清空失败")

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"清空表数据异常: {table_name} - {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")

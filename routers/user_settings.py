"""
routers/user_settings.py
========================
用户设置路由（从 reply_server.py 迁移）。

路由清单：
- GET /user-settings         获取当前用户的所有设置
- PUT /user-settings/{key}   更新用户设置
- GET /user-settings/{key}    获取用户特定设置

设计要点：
- 权限：要求登录（require_auth）
- DBManager 已委托 user_settings_repo，路由层仅调用 db_manager.* 即可
- 路由顺序：/user-settings 在前，/user-settings/{key} 在后（FastAPI 顺序匹配）
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, server_error
from .models import UserSettingUpdate

router = APIRouter(tags=["user-settings"])


def _db():
    from db_manager import db_manager
    return db_manager


# ------------------------- 全部设置 -------------------------

@router.get('/user-settings')
def get_user_settings(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户的所有设置"""
    try:
        user_id = current_user['user_id']
        return _db().get_user_settings(user_id)
    except Exception as e:
        logger.error(f"获取用户设置异常: {e}")
        raise server_error(e, "获取用户设置")


# ------------------------- 单个设置 -------------------------

@router.put('/user-settings/{key}')
def update_user_setting(
    key: str,
    setting_data: UserSettingUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新用户设置"""
    try:
        user_id = current_user['user_id']
        logger.info(
            f"【{current_user.get('username', 'unknown')}#{user_id}】 更新用户设置: {key}"
        )

        success = _db().set_user_setting(
            user_id=user_id,
            key=key,
            value=setting_data.value,
            description=setting_data.description,
        )
        if not success:
            raise HTTPException(status_code=400, detail='更新失败')
        return {'msg': 'setting updated', 'key': key, 'value': setting_data.value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新用户设置异常: {e}")
        raise server_error(e, "更新用户设置")


@router.get('/user-settings/{key}')
def get_user_setting(
    key: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取用户特定设置"""
    try:
        user_id = current_user['user_id']
        setting = _db().get_user_setting(user_id, key)
        if setting:
            return setting
        raise HTTPException(status_code=404, detail='设置不存在')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户设置异常: {e}")
        raise server_error(e, "获取用户设置")

"""
routers/system_settings.py
===========================
系统设置路由。

从 reply_server.py 渐进迁移而来：
- GET /system-settings/public  （无需认证，仅返回公开配置项）
- GET /system-settings          （需认证，排除敏感信息）
- PUT /system-settings/{key}    （需认证，更新单项）

设计原则：
- updateSystemSettings API 使用顺序更新（已由 db_manager 保证）
- webhook 配置变更后失效事件总线缓存
- admin_password_hash 禁止通过本接口修改
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from .deps import require_auth, server_error, client_error
from .models import SystemSettingIn

router = APIRouter(tags=["system-settings"])


def _db():
    from db_manager import db_manager
    return db_manager


# 公开配置项白名单（无需认证即可读取）
_PUBLIC_KEYS = {"registration_enabled", "show_default_login_info", "login_captcha_enabled"}

# webhook 相关配置键，变更后需失效缓存
_WEBHOOK_KEYS = {'webhook_enabled', 'webhook_url', 'webhook_secret', 'webhook_events'}


@router.get('/system-settings/public')
def get_public_system_settings():
    """获取公开的系统设置（无需认证）"""
    try:
        all_settings = _db().get_all_system_settings()
        return {k: v for k, v in all_settings.items() if k in _PUBLIC_KEYS}
    except Exception as e:
        # 出错时返回安全默认值，不向客户端暴露异常详情
        from loguru import logger
        logger.error(f"获取公开系统设置失败: {e}")
        return {
            "registration_enabled": "true",
            "show_default_login_info": "true",
            "login_captcha_enabled": "true",
        }


@router.get('/system-settings')
def get_system_settings(_: Dict[str, Any] = Depends(require_auth)):
    """获取系统设置（排除敏感信息）"""
    try:
        settings = _db().get_all_system_settings()
        # 移除敏感信息
        settings.pop('admin_password_hash', None)
        return settings
    except Exception as e:
        raise server_error(e, "获取系统设置")


@router.put('/system-settings/{key}')
def update_system_setting(
    key: str,
    setting_data: SystemSettingIn,
    _: Dict[str, Any] = Depends(require_auth),
):
    """更新系统设置"""
    try:
        if key == 'admin_password_hash':
            raise HTTPException(status_code=400, detail='请使用密码修改接口')

        success = _db().set_system_setting(key, setting_data.value, setting_data.description)
        if not success:
            raise HTTPException(status_code=400, detail='更新失败')

        # webhook 配置变更后失效缓存
        if key in _WEBHOOK_KEYS:
            try:
                from event_bus import event_bus
                event_bus.invalidate_webhook_cache()
            except Exception:
                pass

        return {'msg': 'system setting updated'}
    except HTTPException:
        raise
    except Exception as e:
        raise client_error(e, "更新系统设置")

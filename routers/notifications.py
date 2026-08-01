"""
routers/notifications.py
=========================
通知域路由：通知渠道 + 消息通知配置。

从 reply_server.py 渐进迁移而来：
- GET    /notification-channels
- POST   /notification-channels
- GET    /notification-channels/{channel_id}
- PUT    /notification-channels/{channel_id}
- DELETE /notification-channels/{channel_id}
- GET    /message-notifications
- GET    /message-notifications/{cid}
- POST   /message-notifications/{cid}
- DELETE /message-notifications/account/{cid}
- DELETE /message-notifications/{notification_id}

设计原则：
- 鉴权统一走 routers.deps.require_auth（与 reply_server.py 等价）
- 数据访问通过 db_manager 单例（保持与现有实现一致，避免连接管理分歧）
- 错误响应统一走 routers.deps.server_error / client_error
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from .deps import require_auth, server_error, client_error
from .models import (
    NotificationChannelIn,
    NotificationChannelUpdate,
    MessageNotificationIn,
)

router = APIRouter(tags=["notifications"])


def _db():
    """延迟导入 db_manager 单例，避免模块加载期耦合"""
    from db_manager import db_manager
    return db_manager


def _user_cookies(user_id: int) -> Dict[str, str]:
    """获取当前用户的所有 cookie（用于权限校验）"""
    return _db().get_all_cookies(user_id)


def _ensure_cookie_owned(cid: str, user_id: int) -> None:
    """校验 cid 属于当前用户，否则 403"""
    if cid not in _user_cookies(user_id):
        raise HTTPException(status_code=403, detail="无权限访问该Cookie")


# ------------------------- 通知渠道管理 -------------------------

@router.get('/notification-channels')
def get_notification_channels(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取所有通知渠道"""
    try:
        return _db().get_notification_channels(current_user['user_id'])
    except Exception as e:
        raise server_error(e, "获取通知渠道")


@router.post('/notification-channels')
def create_notification_channel(
    channel_data: NotificationChannelIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """创建通知渠道"""
    try:
        channel_id = _db().create_notification_channel(
            channel_data.name,
            channel_data.type,
            channel_data.config,
            current_user['user_id'],
        )
        return {'msg': 'notification channel created', 'id': channel_id}
    except Exception as e:
        raise client_error(e, "创建通知渠道")


@router.get('/notification-channels/{channel_id}')
def get_notification_channel(channel_id: int, _: Dict[str, Any] = Depends(require_auth)):
    """获取指定通知渠道"""
    try:
        channel = _db().get_notification_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail='通知渠道不存在')
        return channel
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取通知渠道")


@router.put('/notification-channels/{channel_id}')
def update_notification_channel(
    channel_id: int,
    channel_data: NotificationChannelUpdate,
    _: Dict[str, Any] = Depends(require_auth),
):
    """更新通知渠道"""
    try:
        success = _db().update_notification_channel(
            channel_id,
            channel_data.name,
            channel_data.config,
            channel_data.enabled,
        )
        if not success:
            raise HTTPException(status_code=404, detail='通知渠道不存在')
        return {'msg': 'notification channel updated'}
    except HTTPException:
        raise
    except Exception as e:
        raise client_error(e, "更新通知渠道")


@router.delete('/notification-channels/{channel_id}')
def delete_notification_channel(channel_id: int, _: Dict[str, Any] = Depends(require_auth)):
    """删除通知渠道"""
    try:
        success = _db().delete_notification_channel(channel_id)
        if not success:
            raise HTTPException(status_code=404, detail='通知渠道不存在')
        return {'msg': 'notification channel deleted'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "删除通知渠道")


# ------------------------- 消息通知配置 -------------------------

@router.get('/message-notifications')
def get_all_message_notifications(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户所有账号的消息通知配置"""
    try:
        user_id = current_user['user_id']
        user_cookies = _user_cookies(user_id)
        all_notifications = _db().get_all_message_notifications()
        return {cid: n for cid, n in all_notifications.items() if cid in user_cookies}
    except Exception as e:
        raise server_error(e, "获取消息通知")


@router.get('/message-notifications/{cid}')
def get_account_notifications(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取指定账号的消息通知配置"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        return _db().get_account_notifications(cid)
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取账号消息通知")


@router.post('/message-notifications/{cid}')
def set_message_notification(
    cid: str,
    notification_data: MessageNotificationIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """设置账号的消息通知"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        channel = _db().get_notification_channel(notification_data.channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail='通知渠道不存在')
        success = _db().set_message_notification(cid, notification_data.channel_id, notification_data.enabled)
        if not success:
            raise HTTPException(status_code=400, detail='设置失败')
        return {'msg': 'message notification set'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "设置消息通知")


@router.delete('/message-notifications/account/{cid}')
def delete_account_notifications(cid: str, _: Dict[str, Any] = Depends(require_auth)):
    """删除账号的所有消息通知配置"""
    try:
        success = _db().delete_account_notifications(cid)
        if not success:
            raise HTTPException(status_code=404, detail='账号通知配置不存在')
        return {'msg': 'account notifications deleted'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "删除账号通知")


@router.delete('/message-notifications/{notification_id}')
def delete_message_notification(notification_id: int, _: Dict[str, Any] = Depends(require_auth)):
    """删除消息通知配置"""
    try:
        success = _db().delete_message_notification(notification_id)
        if not success:
            raise HTTPException(status_code=404, detail='通知配置不存在')
        return {'msg': 'message notification deleted'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "删除消息通知")

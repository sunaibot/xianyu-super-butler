"""
routers/default_replies.py
============================
默认回复路由。

从 reply_server.py 渐进迁移而来：
- GET    /default-replies/{cid}
- PUT    /default-replies/{cid}
- GET    /default-replies
- DELETE /default-replies/{cid}
- POST   /default-replies/{cid}/clear-records
- GET    /api/default-replies            （兼容路由）
- GET    /api/default-reply/{cid}        （兼容路由）
- PUT    /api/default-reply/{cid}        （兼容路由）
- DELETE /api/default-reply/{cid}        （兼容路由）
- POST   /api/default-reply/{cid}/clear-records （兼容路由）

设计原则：
- 兼容路由直接委托到主路由函数，避免重复实现
- 权限校验统一：cid 必须属于当前用户
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from .deps import require_auth, server_error, client_error
from .models import DefaultReplyIn

router = APIRouter(tags=["default-replies"])


def _db():
    from db_manager import db_manager
    return db_manager


def _ensure_cookie_owned(cid: str, user_id: int) -> None:
    """校验 cid 属于当前用户，否则 403"""
    if cid not in _db().get_all_cookies(user_id):
        raise HTTPException(status_code=403, detail="无权限操作该Cookie")


# ------------------------- 主路由 -------------------------

@router.get('/default-replies/{cid}')
def get_default_reply(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取指定账号的默认回复设置"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        result = _db().get_default_reply(cid)
        if result is None:
            return {'enabled': False, 'reply_content': '', 'reply_once': False}
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取默认回复")


@router.put('/default-replies/{cid}')
def update_default_reply(
    cid: str,
    reply_data: DefaultReplyIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新指定账号的默认回复设置"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        _db().save_default_reply(
            cid,
            reply_data.enabled,
            reply_data.reply_content,
            reply_data.reply_once,
            reply_data.reply_image_url,
        )
        return {
            'msg': 'default reply updated',
            'enabled': reply_data.enabled,
            'reply_once': reply_data.reply_once,
            'reply_image_url': reply_data.reply_image_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "更新默认回复")


@router.get('/default-replies')
def get_all_default_replies(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户所有账号的默认回复设置"""
    try:
        user_id = current_user['user_id']
        user_cookies = _db().get_all_cookies(user_id)
        all_replies = _db().get_all_default_replies()
        return {cid: r for cid, r in all_replies.items() if cid in user_cookies}
    except Exception as e:
        raise server_error(e, "获取默认回复列表")


@router.delete('/default-replies/{cid}')
def delete_default_reply(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """删除指定账号的默认回复设置"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        success = _db().delete_default_reply(cid)
        if not success:
            raise HTTPException(status_code=400, detail='删除失败')
        return {'msg': 'default reply deleted'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "删除默认回复")


@router.post('/default-replies/{cid}/clear-records')
def clear_default_reply_records(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """清空指定账号的默认回复记录"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        _db().clear_default_reply_records(cid)
        return {'msg': 'default reply records cleared'}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "清空默认回复记录")


# ------------------------- 兼容路由（/api/default-reply/*） -------------------------
# 前端历史使用单数形式，此处委托到主路由函数保持行为一致

@router.get('/api/default-replies')
def get_all_default_replies_compat(current_user: Dict[str, Any] = Depends(require_auth)):
    return get_all_default_replies(current_user)


@router.get('/api/default-reply/{cid}')
def get_default_reply_compat(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    return get_default_reply(cid, current_user)


@router.put('/api/default-reply/{cid}')
def update_default_reply_compat(
    cid: str,
    reply_data: DefaultReplyIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    return update_default_reply(cid, reply_data, current_user)


@router.delete('/api/default-reply/{cid}')
def delete_default_reply_compat(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    return delete_default_reply(cid, current_user)


@router.post('/api/default-reply/{cid}/clear-records')
def clear_default_reply_records_compat(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    return clear_default_reply_records(cid, current_user)

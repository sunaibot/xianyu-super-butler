"""
routers/cookies.py
============================
Cookie / 账号基础 CRUD 路由。

从 reply_server.py 渐进迁移而来：
- GET    /cookies                          列出当前用户的 Cookie ID
- GET    /cookies/details                  批量详情（消除 N+1，不返回敏感字段）
- POST   /cookies                          新增 Cookie（含跨用户冲突检查）
- PUT    /cookies/{cid}/login-info         更新账号登录信息（用户名/密码/show_browser）
- PUT    /cookies/{cid}                    更新 Cookie 值（变化时重启任务）
- PUT    /cookies/{cid}/status             更新启用/禁用状态
- DELETE /cookies/{cid}                    删除 Cookie（同步移除运行任务）
- PUT    /cookies/{cid}/auto-confirm       更新自动确认发货
- GET    /cookies/{cid}/auto-confirm       获取自动确认发货
- PUT    /cookies/{cid}/remark             更新备注
- GET    /cookies/{cid}/remark             获取备注
- PUT    /cookies/{cid}/pause-duration     更新自动回复暂停时间（0-120 分钟）
- GET    /cookies/{cid}/pause-duration     获取自动回复暂停时间
- GET    /cookies/check                    检查有效账号（公开接口）
- GET    /cookie/{cid}/details             获取账号详情（include_value=true 时返回 Cookie 明文，编辑场景）
- GET    /admin/cookies                     管理员查看所有 Cookie

设计原则：
- 权限校验：cid 必须属于当前用户（管理员路由走 require_admin）
- CookieManager 仍是账号运行时管理器，路由通过 cookie_manager.manager 访问
- 敏感字段（value/username/password）仅在内部使用，绝不返回给前端
- 不含 QR 登录、密码登录、风控截图等复杂流程，这些仍保留在 reply_server.py
- 原 cookie_account.py 的 POST /cookie/{cid}/account-info 已移除（与 PUT /cookies/{cid}
  + PUT /cookies/{cid}/login-info 功能重复，前端未使用）
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, require_admin, optional_auth, server_error, client_error, log_with_user
from .models import (
    CookieIn, CookieStatusIn, AccountLoginInfoUpdate,
    AutoConfirmUpdate, RemarkUpdate, PauseDurationUpdate,
)

router = APIRouter(tags=["cookies"])


def _db():
    from db_manager import db_manager
    return db_manager


def _mgr():
    """获取 CookieManager 单例；如未就绪抛 500"""
    import cookie_manager
    if cookie_manager.manager is None:
        raise HTTPException(status_code=500, detail="CookieManager 未就绪")
    return cookie_manager.manager


def _ensure_cookie_owned(cid: str, user_id: int) -> None:
    """校验 cid 属于当前用户，否则 403"""
    if cid not in _db().get_all_cookies(user_id):
        raise HTTPException(status_code=403, detail="无权限操作该Cookie")


# ------------------------- 列表 / 详情 -------------------------

@router.get("/cookies")
def list_cookies(current_user: Dict[str, Any] = Depends(require_auth)):
    """列出当前用户的所有 Cookie ID"""
    if not _is_mgr_ready():
        return []
    user_cookies = _db().get_all_cookies(current_user['user_id'])
    return list(user_cookies.keys())


def _is_mgr_ready() -> bool:
    import cookie_manager
    return cookie_manager.manager is not None


@router.get("/cookies/details")
def get_cookies_details(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取所有账号的非敏感信息（批量查询，消除 N+1）"""
    import cookie_manager
    if cookie_manager.manager is None:
        return []

    db = _db()
    user_id = current_user['user_id']

    # 批量查询：一次取回该用户所有 cookie 的 id 与详情
    user_cookies = db.get_all_cookies(user_id)
    all_details = db.get_all_cookie_details(user_id)
    # 启用状态走 CookieManager 内存态
    mgr = cookie_manager.manager

    result = []
    for cookie_id in user_cookies.keys():
        details = all_details.get(cookie_id, {})
        result.append({
            'id': cookie_id,
            'has_cookie': True,
            'enabled': mgr.get_cookie_status(cookie_id),
            'auto_confirm': details.get('auto_confirm', False),
            'remark': details.get('remark', ''),
            'pause_duration': details.get('pause_duration', 10),
        })
    return result


@router.post("/cookies")
def add_cookie(item: CookieIn, current_user: Dict[str, Any] = Depends(require_auth)):
    """新增 Cookie（绑定到当前用户）"""
    import cookie_manager
    if cookie_manager.manager is None:
        raise HTTPException(status_code=500, detail="CookieManager 未就绪")
    try:
        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"尝试添加Cookie: {item.id}, 当前用户ID: {user_id}", current_user)

        # 检查 cookie 是否已存在且属于其他用户
        existing_cookies = db.get_all_cookies()
        if item.id in existing_cookies:
            user_cookies = db.get_all_cookies(user_id)
            if item.id not in user_cookies:
                log_with_user('warning', f"Cookie ID冲突: {item.id} 已被其他用户使用", current_user)
                raise HTTPException(status_code=400, detail="该Cookie ID已被其他用户使用")

        db.save_cookie(item.id, item.value, user_id)
        cookie_manager.manager.add_cookie(item.id, item.value, user_id=user_id)
        log_with_user('info', f"Cookie添加成功: {item.id}", current_user)
        return {"msg": "success"}
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"添加Cookie失败: {item.id} - {e}", current_user)
        raise client_error(e, "操作")


# ------------------------- /cookies/{cid}/xxx 子路径（须先于 /cookies/{cid} 注册） -------------------------

@router.put("/cookies/{cid}/login-info")
def update_cookie_login_info(
    cid: str,
    update_data: AccountLoginInfoUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新账号登录信息（用户名、密码、是否显示浏览器）"""
    try:
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        success = db.update_cookie_account_info(
            cid,
            username=update_data.username,
            password=update_data.login_password,
            show_browser=update_data.show_browser,
        )
        if success:
            return {"success": True, "message": "登录信息已更新"}
        raise HTTPException(status_code=500, detail="更新登录信息失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put('/cookies/{cid}')
def update_cookie(cid: str, item: CookieIn, current_user: Dict[str, Any] = Depends(require_auth)):
    """更新 Cookie 值；变化时重启任务"""
    try:
        db = _db()
        mgr = _mgr()
        _ensure_cookie_owned(cid, current_user['user_id'])

        # 获取旧值，判断是否需要重启任务
        old_cookie_details = db.get_cookie_details(cid)
        old_cookie_value = old_cookie_details.get('value') if old_cookie_details else None

        success = db.update_cookie_account_info(cid, cookie_value=item.value)
        if not success:
            raise HTTPException(status_code=400, detail="更新Cookie失败")

        if item.value != old_cookie_value:
            logger.info(f"Cookie值已变化，重启任务: {cid}")
            mgr.update_cookie(cid, item.value, save_to_db=False)
        else:
            logger.info(f"Cookie值未变化，无需重启任务: {cid}")
        return {'msg': 'updated'}
    except HTTPException:
        raise
    except Exception as e:
        raise client_error(e, "操作")


@router.put('/cookies/{cid}/status')
def update_cookie_status(
    cid: str,
    status_data: CookieStatusIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新账号的启用/禁用状态"""
    try:
        mgr = _mgr()
        _ensure_cookie_owned(cid, current_user['user_id'])
        mgr.update_cookie_status(cid, status_data.enabled)
        return {'msg': 'status updated', 'enabled': status_data.enabled}
    except HTTPException:
        raise
    except Exception as e:
        raise client_error(e, "操作")


@router.delete("/cookies/{cid}")
def remove_cookie(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """删除 Cookie（同步移除运行任务）"""
    try:
        mgr = _mgr()
        _ensure_cookie_owned(cid, current_user['user_id'])
        mgr.remove_cookie(cid)
        return {"msg": "removed"}
    except HTTPException:
        raise
    except Exception as e:
        raise client_error(e, "操作")


@router.put("/cookies/{cid}/auto-confirm")
def update_auto_confirm(
    cid: str,
    update_data: AutoConfirmUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新账号的自动确认发货设置"""
    try:
        mgr = _mgr()
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        success = db.update_auto_confirm(cid, update_data.auto_confirm)
        if not success:
            raise HTTPException(status_code=500, detail="更新自动确认发货设置失败")

        # 通知 CookieManager 更新设置（如果账号正在运行）
        if hasattr(mgr, 'update_auto_confirm_setting'):
            mgr.update_auto_confirm_setting(cid, update_data.auto_confirm)

        return {
            "msg": "success",
            "auto_confirm": update_data.auto_confirm,
            "message": f"自动确认发货已{'开启' if update_data.auto_confirm else '关闭'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/cookies/{cid}/auto-confirm")
def get_auto_confirm(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取账号的自动确认发货设置"""
    try:
        _mgr()  # 仅校验 CookieManager 就绪
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        auto_confirm = db.get_auto_confirm(cid)
        return {
            "auto_confirm": auto_confirm,
            "message": f"自动确认发货当前{'开启' if auto_confirm else '关闭'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/cookies/{cid}/remark")
def update_cookie_remark(
    cid: str,
    update_data: RemarkUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新账号备注"""
    try:
        _mgr()
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        success = db.update_cookie_remark(cid, update_data.remark)
        if success:
            log_with_user('info', f"更新账号备注: {cid} -> {update_data.remark}", current_user)
            return {
                "message": "备注更新成功",
                "remark": update_data.remark,
            }
        raise HTTPException(status_code=500, detail="备注更新失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/cookies/{cid}/remark")
def get_cookie_remark(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取账号备注"""
    try:
        _mgr()
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        cookie_details = db.get_cookie_details(cid)
        if cookie_details:
            return {
                "remark": cookie_details.get('remark', ''),
                "message": "获取备注成功",
            }
        raise HTTPException(status_code=404, detail="账号不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/cookies/{cid}/pause-duration")
def update_cookie_pause_duration(
    cid: str,
    update_data: PauseDurationUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新账号自动回复暂停时间"""
    try:
        _mgr()
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        # 验证暂停时间范围（0-120 分钟，0 表示不暂停）
        if not (0 <= update_data.pause_duration <= 120):
            raise HTTPException(status_code=400, detail="暂停时间必须在0-120分钟之间（0表示不暂停）")

        success = db.update_cookie_pause_duration(cid, update_data.pause_duration)
        if success:
            log_with_user('info', f"更新账号自动回复暂停时间: {cid} -> {update_data.pause_duration}分钟", current_user)
            return {
                "message": "暂停时间更新成功",
                "pause_duration": update_data.pause_duration,
            }
        raise HTTPException(status_code=500, detail="暂停时间更新失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/cookies/{cid}/pause-duration")
def get_cookie_pause_duration(cid: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取账号自动回复暂停时间"""
    try:
        _mgr()
        db = _db()
        _ensure_cookie_owned(cid, current_user['user_id'])

        pause_duration = db.get_cookie_pause_duration(cid)
        return {
            "pause_duration": pause_duration,
            "message": "获取暂停时间成功",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ------------------------- 公共 / 管理员路由 -------------------------

@router.get("/cookie/{cid}/details")
def get_cookie_account_details(
    cid: str,
    include_value: bool = False,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取账号详情（include_value=True 时返回Cookie明文，仅用于编辑场景）

    原 cookie_account.py 迁入；保留 /cookie/{cid}/details URL 以兼容前端 getAccountForEdit。
    """
    import cookie_manager
    from db_manager import db_manager

    try:
        user_id = current_user['user_id']
        user_cookies = db_manager.get_all_cookies(user_id)
        if cid not in user_cookies:
            raise HTTPException(status_code=403, detail="无权限操作该Cookie")

        details = db_manager.get_cookie_details(cid)
        if not details:
            raise HTTPException(status_code=404, detail="账号不存在")

        result = {
            'id': details.get('id'),
            'enabled': cookie_manager.manager.get_cookie_status(cid) if cookie_manager.manager else True,
            'auto_confirm': details.get('auto_confirm', True),
            'remark': details.get('remark', ''),
            'pause_duration': details.get('pause_duration', 10),
            'show_browser': details.get('show_browser', False),
            'username': details.get('username', ''),
            'has_cookie': True,
        }

        if include_value:
            cookie_value = db_manager.get_cookie(cid)
            result['cookie'] = cookie_value or ''
            result['value'] = cookie_value or ''

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取账号详情失败: {e}")
        raise client_error(e, "操作")


@router.get("/cookies/check")
async def check_valid_cookies(
    current_user: Optional[Dict[str, Any]] = Depends(optional_auth),
):
    """检查是否有有效的 cookies 账户（必须是启用状态）。

    公开接口，未登录也允许；current_user 当前未使用，但保留参数以便未来按用户隔离。
    """
    import cookie_manager
    try:
        if cookie_manager.manager is None:
            return {
                "success": True,
                "hasValidCookies": False,
                "validCount": 0,
                "enabledCount": 0,
                "totalCount": 0,
            }

        db = _db()
        all_cookies = db.get_all_cookies()

        valid_cookies = []
        enabled_cookies = []
        for cookie_id, cookie_value in all_cookies.items():
            is_enabled = cookie_manager.manager.get_cookie_status(cookie_id)
            if is_enabled:
                enabled_cookies.append(cookie_id)
                # 检查是否有效（长度大于 50）
                if len(cookie_value) > 50:
                    valid_cookies.append(cookie_id)

        return {
            "success": True,
            "hasValidCookies": len(valid_cookies) > 0,
            "validCount": len(valid_cookies),
            "enabledCount": len(enabled_cookies),
            "totalCount": len(all_cookies),
        }
    except Exception as e:
        logger.error(f"检查cookies失败: {e}")
        return {
            "success": False,
            "hasValidCookies": False,
            "error": str(e),
        }


@router.get('/admin/cookies')
def get_admin_cookies(admin_user: Dict[str, Any] = Depends(require_admin)):
    """获取所有 Cookie 信息（管理员专用）"""
    try:
        import cookie_manager
        log_with_user('info', "查询所有Cookie信息", admin_user)

        if cookie_manager.manager is None:
            return {
                "success": True,
                "cookies": [],
                "message": "CookieManager 未就绪",
            }

        db = _db()
        all_users = db.get_all_users()
        all_cookies = []
        for user in all_users:
            user_id = user['id']
            user_cookies = db.get_all_cookies(user_id)
            for cookie_id, _cookie_value in user_cookies.items():
                cookie_details = db.get_cookie_details(cookie_id)
                all_cookies.append({
                    'cookie_id': cookie_id,
                    'user_id': user_id,
                    'username': user['username'],
                    'nickname': cookie_details.get('remark', '') if cookie_details else '',
                    'enabled': cookie_manager.manager.get_cookie_status(cookie_id),
                })

        log_with_user('info', f"获取到 {len(all_cookies)} 个Cookie", admin_user)
        return {
            "success": True,
            "cookies": all_cookies,
            "total": len(all_cookies),
        }
    except Exception as e:
        log_with_user('error', f"获取Cookie信息失败: {e}", admin_user)
        return {
            "success": False,
            "cookies": [],
            "message": "获取失败",
        }

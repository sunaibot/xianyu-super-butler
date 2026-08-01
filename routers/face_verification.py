"""
routers/face_verification.py
============================
人脸验证截图路由（从 reply_server.py 迁移）。

路由清单：
- GET    /face-verification/screenshot/{account_id}   获取指定账号的最新验证截图
- DELETE /face-verification/screenshot/{account_id}   删除指定账号的所有验证截图

设计要点：
- 权限校验：非管理员只能操作自己的账号
- 截图文件存放在 static/uploads/images/ 目录，文件名匹配 face_verify_{account_id}_*.jpg
"""
import os
import glob
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends
from loguru import logger

from .deps import require_auth, safe_client_msg, log_with_user

router = APIRouter(tags=["face-verification"])


_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


@router.get("/face-verification/screenshot/{account_id}")
async def get_account_face_verification_screenshot(
    account_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定账号的人脸验证截图"""
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        is_admin = bool(current_user.get('is_admin', False))

        if not is_admin:
            cookie_info = db_manager.get_cookie_details(account_id)
            if not cookie_info:
                log_with_user('warning', f"账号 {account_id} 不存在", current_user)
                return {'success': False, 'message': '账号不存在'}
            if cookie_info.get('user_id') != user_id:
                log_with_user('warning', f"用户 {user_id} 尝试访问账号 {account_id}（归属用户: {cookie_info.get('user_id')}）", current_user)
                return {'success': False, 'message': '无权访问该账号'}

        screenshots_dir = os.path.join(_STATIC_DIR, 'uploads', 'images')
        pattern = os.path.join(screenshots_dir, f'face_verify_{account_id}_*.jpg')
        screenshot_files = glob.glob(pattern)

        log_with_user('debug', f"查找截图: {pattern}, 找到 {len(screenshot_files)} 个文件", current_user)

        if not screenshot_files:
            log_with_user('warning', f"账号 {account_id} 没有找到验证截图", current_user)
            return {'success': False, 'message': '未找到验证截图'}

        latest_file = max(screenshot_files, key=os.path.getmtime)
        filename = os.path.basename(latest_file)
        stat = os.stat(latest_file)

        screenshot_info = {
            'filename': filename,
            'account_id': account_id,
            'path': f'/static/uploads/images/{filename}',
            'size': stat.st_size,
            'created_time': stat.st_ctime,
            'created_time_str': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
        }
        log_with_user('info', f"获取账号 {account_id} 的验证截图", current_user)
        return {'success': True, 'screenshot': screenshot_info}

    except Exception as e:
        log_with_user('error', f"获取验证截图失败: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "操作失败")}


@router.delete("/face-verification/screenshot/{account_id}")
async def delete_account_face_verification_screenshot(
    account_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """删除指定账号的人脸验证截图"""
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        cookie_info = db_manager.get_cookie_details(account_id)
        if not cookie_info or cookie_info.get('user_id') != user_id:
            return {'success': False, 'message': '无权访问该账号'}

        screenshots_dir = os.path.join(_STATIC_DIR, 'uploads', 'images')
        pattern = os.path.join(screenshots_dir, f'face_verify_{account_id}_*.jpg')
        screenshot_files = glob.glob(pattern)

        deleted_count = 0
        for file_path in screenshot_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_count += 1
                    log_with_user('info', f"删除账号 {account_id} 的验证截图: {os.path.basename(file_path)}", current_user)
            except Exception as e:
                log_with_user('error', f"删除截图失败 {file_path}: {str(e)}", current_user)

        return {'success': True, 'message': f'已删除 {deleted_count} 个验证截图', 'deleted_count': deleted_count}

    except Exception as e:
        log_with_user('error', f"删除验证截图失败: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "操作失败")}

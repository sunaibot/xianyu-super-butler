"""
routers/qr_login.py
===================
扫码登录路由（从 reply_server.py 迁移）。

路由清单：
- POST /qr-login/generate                生成扫码登录二维码
- GET  /qr-login/check/{session_id}       检查扫码登录状态
- POST /qr-login/refresh-cookies          使用扫码cookie刷新真实cookie
- POST /qr-login/reset-cooldown/{cookie_id}   重置Cookie刷新冷却时间
- GET  /qr-login/cooldown-status/{cookie_id}  获取Cookie刷新冷却状态

设计要点：
- qr_check_processed / qr_check_locks / cleanup_qr_check_records /
  process_qr_login_cookies / _fallback_save_qr_cookie 已迁移至本模块
- 会话锁防止并发重复处理
"""
import asyncio
import time
from collections import defaultdict
from typing import Any, Dict

from fastapi import APIRouter, Depends
from loguru import logger

from .deps import log_with_user, require_auth, safe_client_msg

# 扫码登录检查锁 - 防止并发处理同一个session
qr_check_locks = defaultdict(lambda: asyncio.Lock())
qr_check_processed = {}  # 记录已处理的session: {session_id: {'processed': bool, 'timestamp': float}}


def cleanup_qr_check_records():
    """清理过期的扫码检查记录"""
    current_time = time.time()
    expired_sessions = []

    for session_id, record in qr_check_processed.items():
        # 清理超过1小时的记录
        if current_time - record['timestamp'] > 3600:
            expired_sessions.append(session_id)

    for session_id in expired_sessions:
        if session_id in qr_check_processed:
            del qr_check_processed[session_id]
        if session_id in qr_check_locks:
            del qr_check_locks[session_id]


async def process_qr_login_cookies(cookies: str, unb: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """处理扫码登录获取的Cookie - 先获取真实cookie再保存到数据库"""
    try:
        from db_manager import db_manager
        from utils.xianyu_utils import trans_cookies

        import cookie_manager

        user_id = current_user['user_id']

        # 检查是否已存在相同unb的账号
        existing_cookies = db_manager.get_all_cookies(user_id)
        existing_account_id = None

        for account_id, cookie_value in existing_cookies.items():
            try:
                # 解析现有Cookie中的unb
                existing_cookie_dict = trans_cookies(cookie_value)
                if existing_cookie_dict.get('unb') == unb:
                    existing_account_id = account_id
                    break
            except Exception:
                continue

        # 确定账号ID
        if existing_account_id:
            account_id = existing_account_id
            is_new_account = False
            log_with_user('info', f"扫码登录找到现有账号: {account_id}, UNB: {unb}", current_user)
        else:
            # 创建新账号，使用unb作为账号ID
            account_id = unb

            # 确保账号ID唯一
            counter = 1
            original_account_id = account_id
            while account_id in existing_cookies:
                account_id = f"{original_account_id}_{counter}"
                counter += 1

            is_new_account = True
            log_with_user('info', f"扫码登录准备创建新账号: {account_id}, UNB: {unb}", current_user)

        # 第一步：使用扫码cookie获取真实cookie
        log_with_user('info', f"开始使用扫码cookie获取真实cookie: {account_id}", current_user)

        try:
            # 创建一个临时的XianyuLive实例来执行cookie刷新
            from XianyuAutoAsync import XianyuLive

            # 使用扫码登录的cookie创建临时实例
            temp_instance = XianyuLive(
                cookies_str=cookies,
                cookie_id=account_id,
                user_id=user_id
            )

            # 执行cookie刷新获取真实cookie
            refresh_success = await temp_instance.refresh_cookies_from_qr_login(
                qr_cookies_str=cookies,
                cookie_id=account_id,
                user_id=user_id
            )

            if refresh_success:
                log_with_user('info', f"扫码登录真实cookie获取成功: {account_id}", current_user)

                # 从数据库获取刚刚保存的真实cookie
                updated_cookie_info = db_manager.get_cookie_by_id(account_id)
                if updated_cookie_info:
                    real_cookies = updated_cookie_info['cookies_str']
                    log_with_user('info', f"已获取真实cookie，长度: {len(real_cookies)}", current_user)

                    # 第二步：将真实cookie添加到cookie_manager（如果是新账号）或更新现有账号
                    if cookie_manager.manager:
                        if is_new_account:
                            cookie_manager.manager.add_cookie(account_id, real_cookies)
                            log_with_user('info', f"已将真实cookie添加到cookie_manager: {account_id}", current_user)
                        else:
                            # refresh_cookies_from_qr_login 已经保存到数据库了，这里不需要再保存
                            cookie_manager.manager.update_cookie(account_id, real_cookies, save_to_db=False)
                            log_with_user('info', f"已更新cookie_manager中的真实cookie: {account_id}", current_user)

                    return {
                        'account_id': account_id,
                        'is_new_account': is_new_account,
                        'real_cookie_refreshed': True,
                        'cookie_length': len(real_cookies)
                    }
                else:
                    log_with_user('error', f"无法从数据库获取真实cookie: {account_id}", current_user)
                    # 降级处理：使用原始扫码cookie
                    return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, "无法从数据库获取真实cookie")
            else:
                log_with_user('warning', f"扫码登录真实cookie获取失败: {account_id}", current_user)
                # 降级处理：使用原始扫码cookie
                return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, "真实cookie获取失败")

        except Exception as refresh_e:
            log_with_user('error', f"扫码登录真实cookie获取异常: {str(refresh_e)}", current_user)
            # 降级处理：使用原始扫码cookie
            return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, f"获取真实cookie异常: {str(refresh_e)}")

    except Exception as e:
        log_with_user('error', f"处理扫码登录Cookie失败: {str(e)}", current_user)
        raise e


async def _fallback_save_qr_cookie(account_id: str, cookies: str, user_id: int, is_new_account: bool, current_user: Dict[str, Any], error_reason: str) -> Dict[str, Any]:
    """降级处理：当无法获取真实cookie时，保存原始扫码cookie"""
    try:
        from db_manager import db_manager

        import cookie_manager

        log_with_user('warning', f"降级处理 - 保存原始扫码cookie: {account_id}, 原因: {error_reason}", current_user)

        # 保存原始扫码cookie到数据库
        if is_new_account:
            db_manager.save_cookie(account_id, cookies, user_id)
            log_with_user('info', f"降级处理 - 新账号原始cookie已保存: {account_id}", current_user)
        else:
            # 现有账号使用 update_cookie_account_info 避免覆盖其他字段
            db_manager.update_cookie_account_info(account_id, cookie_value=cookies)
            log_with_user('info', f"降级处理 - 现有账号原始cookie已更新: {account_id}", current_user)

        # 添加到或更新cookie_manager
        if cookie_manager.manager:
            if is_new_account:
                cookie_manager.manager.add_cookie(account_id, cookies)
                log_with_user('info', f"降级处理 - 已将原始cookie添加到cookie_manager: {account_id}", current_user)
            else:
                # update_cookie_account_info 已经保存到数据库了，这里不需要再保存
                cookie_manager.manager.update_cookie(account_id, cookies, save_to_db=False)
                log_with_user('info', f"降级处理 - 已更新cookie_manager中的原始cookie: {account_id}", current_user)

        return {
            'account_id': account_id,
            'is_new_account': is_new_account,
            'real_cookie_refreshed': False,
            'fallback_reason': error_reason,
            'cookie_length': len(cookies)
        }

    except Exception as fallback_e:
        log_with_user('error', f"降级处理失败: {str(fallback_e)}", current_user)
        raise fallback_e


router = APIRouter(tags=["qr-login"])


@router.post("/qr-login/generate")
async def generate_qr_code(current_user: Dict[str, Any] = Depends(require_auth)):
    """生成扫码登录二维码"""
    try:
        from utils.qr_login import qr_login_manager

        log_with_user('info', "请求生成扫码登录二维码", current_user)
        result = await qr_login_manager.generate_qr_code()
        if result['success']:
            log_with_user('info', f"扫码登录二维码生成成功: {result['session_id']}", current_user)
        else:
            log_with_user('warning', f"扫码登录二维码生成失败: {result.get('message', '未知错误')}", current_user)
        return result
    except Exception as e:
        log_with_user('error', f"生成扫码登录二维码异常: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "生成二维码失败")}


@router.get("/qr-login/check/{session_id}")
async def check_qr_code_status(session_id: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """检查扫码登录状态"""
    try:
        from utils.qr_login import qr_login_manager

        cleanup_qr_check_records()

        # 检查是否已处理过
        if session_id in qr_check_processed:
            record = qr_check_processed[session_id]
            if record['processed']:
                log_with_user('debug', f"扫码登录session {session_id} 已处理过，直接返回", current_user)
                return {'status': 'already_processed', 'message': '该会话已处理完成'}

        session_lock = qr_check_locks[session_id]
        if session_lock.locked():
            log_with_user('debug', f"扫码登录session {session_id} 正在被其他请求处理，跳过", current_user)
            return {'status': 'processing', 'message': '正在处理中，请稍候...'}

        async with session_lock:
            if session_id in qr_check_processed and qr_check_processed[session_id]['processed']:
                log_with_user('debug', f"扫码登录session {session_id} 在获取锁后发现已处理，直接返回", current_user)
                return {'status': 'already_processed', 'message': '该会话已处理完成'}

            qr_login_manager.cleanup_expired_sessions()
            status_info = qr_login_manager.get_session_status(session_id)
            log_with_user('info', f"获取会话状态: {status_info}", current_user)

            if status_info['status'] == 'success':
                cookies_info = qr_login_manager.get_session_cookies(session_id)
                log_with_user('info', f"获取会话Cookie: {cookies_info}", current_user)
                if cookies_info:
                    account_info = await process_qr_login_cookies(
                        cookies_info['cookies'],
                        cookies_info['unb'],
                        current_user,
                    )
                    status_info['account_info'] = account_info
                    log_with_user('info', f"扫码登录处理完成: {session_id}, 账号: {account_info.get('account_id', 'unknown')}", current_user)
                    qr_check_processed[session_id] = {'processed': True, 'timestamp': time.time()}

            return status_info
    except Exception as e:
        log_with_user('error', f"检查扫码登录状态异常: {str(e)}", current_user)
        return {'status': 'error', 'message': safe_client_msg(e, "操作失败")}


@router.post("/qr-login/refresh-cookies")
async def refresh_cookies_from_qr_login(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """使用扫码登录获取的cookie访问指定界面获取真实cookie并存入数据库"""
    try:
        import cookie_manager
        from db_manager import db_manager
        from XianyuAutoAsync import XianyuLive

        qr_cookies = request.get('qr_cookies')
        cookie_id = request.get('cookie_id')

        if not qr_cookies:
            return {'success': False, 'message': '缺少扫码登录cookie'}
        if not cookie_id:
            return {'success': False, 'message': '缺少cookie_id'}

        log_with_user('info', f"开始使用扫码cookie刷新真实cookie: {cookie_id}", current_user)

        temp_instance = XianyuLive(
            cookies_str=qr_cookies,
            cookie_id=cookie_id,
            user_id=current_user['user_id'],
        )
        success = await temp_instance.refresh_cookies_from_qr_login(
            qr_cookies_str=qr_cookies,
            cookie_id=cookie_id,
            user_id=current_user['user_id'],
        )

        if success:
            log_with_user('info', f"扫码cookie刷新成功: {cookie_id}", current_user)
            if cookie_manager.manager:
                updated_cookie_info = db_manager.get_cookie_by_id(cookie_id)
                if updated_cookie_info:
                    cookie_manager.manager.update_cookie(cookie_id, updated_cookie_info['cookies_str'], save_to_db=False)
                    log_with_user('info', f"已更新cookie_manager中的cookie: {cookie_id}", current_user)
            return {'success': True, 'message': '真实cookie获取并保存成功', 'cookie_id': cookie_id}
        else:
            log_with_user('error', f"扫码cookie刷新失败: {cookie_id}", current_user)
            return {'success': False, 'message': '获取真实cookie失败'}
    except Exception as e:
        log_with_user('error', f"扫码cookie刷新异常: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "刷新cookie失败")}


@router.post("/qr-login/reset-cooldown/{cookie_id}")
async def reset_qr_cookie_refresh_cooldown(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """重置指定账号的扫码登录Cookie刷新冷却时间"""
    try:
        import cookie_manager
        from db_manager import db_manager

        log_with_user('info', f"重置扫码登录Cookie刷新冷却时间: {cookie_id}", current_user)

        cookie_info = db_manager.get_cookie_by_id(cookie_id)
        if not cookie_info:
            return {'success': False, 'message': '账号不存在'}

        if cookie_manager.manager and cookie_id in cookie_manager.manager.instances:
            instance = cookie_manager.manager.instances[cookie_id]
            remaining_time_before = instance.get_qr_cookie_refresh_remaining_time()
            instance.reset_qr_cookie_refresh_flag()
            log_with_user('info', f"已重置账号 {cookie_id} 的扫码登录冷却时间，原剩余时间: {remaining_time_before}秒", current_user)
            return {
                'success': True,
                'message': '扫码登录Cookie刷新冷却时间已重置',
                'cookie_id': cookie_id,
                'previous_remaining_time': remaining_time_before,
            }
        else:
            log_with_user('info', f"账号 {cookie_id} 没有活跃实例，无需重置冷却时间", current_user)
            return {
                'success': True,
                'message': '账号没有活跃实例，无需重置冷却时间',
                'cookie_id': cookie_id,
            }
    except Exception as e:
        log_with_user('error', f"重置扫码登录冷却时间异常: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "重置冷却时间失败")}


@router.get("/qr-login/cooldown-status/{cookie_id}")
async def get_qr_cookie_refresh_cooldown_status(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定账号的扫码登录Cookie刷新冷却状态"""
    try:
        import cookie_manager
        from db_manager import db_manager

        cookie_info = db_manager.get_cookie_by_id(cookie_id)
        if not cookie_info:
            return {'success': False, 'message': '账号不存在'}

        if cookie_manager.manager and cookie_id in cookie_manager.manager.instances:
            instance = cookie_manager.manager.instances[cookie_id]
            remaining_time = instance.get_qr_cookie_refresh_remaining_time()
            cooldown_duration = instance.qr_cookie_refresh_cooldown
            last_refresh_time = instance.last_qr_cookie_refresh_time
            return {
                'success': True,
                'cookie_id': cookie_id,
                'remaining_time': remaining_time,
                'cooldown_duration': cooldown_duration,
                'last_refresh_time': last_refresh_time,
                'is_in_cooldown': remaining_time > 0,
                'remaining_minutes': remaining_time // 60,
                'remaining_seconds': remaining_time % 60,
            }
        else:
            return {
                'success': True,
                'cookie_id': cookie_id,
                'remaining_time': 0,
                'cooldown_duration': 600,
                'last_refresh_time': 0,
                'is_in_cooldown': False,
                'message': '账号没有活跃实例',
            }
    except Exception as e:
        log_with_user('error', f"获取扫码登录冷却状态异常: {str(e)}", current_user)
        return {'success': False, 'message': safe_client_msg(e, "获取冷却状态失败")}

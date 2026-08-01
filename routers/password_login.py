"""
routers/password_login.py
=========================
账号密码登录路由（从 reply_server.py 迁移）。

路由清单：
- POST /password-login                  发起账号密码登录（异步，支持人脸认证）
- GET  /password-login/check/{session_id}  检查登录状态

设计要点：
- password_login_sessions 和 _execute_password_login 已迁移至本模块
- 会话超过 1 小时自动清理
"""
import time
import asyncio
import traceback
import os
import threading
import base64
import io
import secrets
from collections import defaultdict
from typing import Any, Dict

from fastapi import APIRouter, Depends
from loguru import logger

import cookie_manager
from db_manager import db_manager

from .deps import require_auth, safe_client_msg, log_with_user

# 兼容 reply_server 中的命名
_safe_client_msg = safe_client_msg

# 账号密码登录会话管理
password_login_sessions = {}  # {session_id: {'account_id': str, 'account': str, 'password': str, 'show_browser': bool, 'status': str, 'verification_url': str, 'qr_code_url': str, 'slider_instance': object, 'task': asyncio.Task, 'timestamp': float}}
password_login_locks = defaultdict(lambda: asyncio.Lock())

router = APIRouter(tags=["password-login"])


async def _execute_password_login(session_id: str, account_id: str, account: str, password: str, show_browser: bool, user_id: int, current_user: Dict[str, Any]):
    """后台执行账号密码登录任务"""
    try:
        log_with_user('info', f"开始执行账号密码登录任务: {session_id}, 账号: {account_id}", current_user)

        # 导入 XianyuSliderStealth
        from utils.xianyu_slider_stealth import XianyuSliderStealth
        import base64
        import io

        # 创建 XianyuSliderStealth 实例
        slider_instance = XianyuSliderStealth(
            user_id=account_id,
            enable_learning=True,
            headless=not show_browser
        )

        # 更新会话信息
        password_login_sessions[session_id]['slider_instance'] = slider_instance

        # 定义通知回调函数，用于检测到人脸认证时返回验证链接或截图（同步函数）
        def notification_callback(message: str, screenshot_path: str = None, verification_url: str = None, screenshot_path_new: str = None):
            """人脸认证通知回调（同步）

            Args:
                message: 通知消息
                screenshot_path: 旧版截图路径（兼容参数）
                verification_url: 验证链接
                screenshot_path_new: 新版截图路径（新参数，优先使用）
            """
            try:
                # 优先使用新的截图路径参数
                actual_screenshot_path = screenshot_path_new if screenshot_path_new else screenshot_path

                # 优先使用截图路径，如果没有截图则使用验证链接
                if actual_screenshot_path and os.path.exists(actual_screenshot_path):
                    # 更新会话状态，保存截图路径
                    password_login_sessions[session_id]['status'] = 'verification_required'
                    password_login_sessions[session_id]['screenshot_path'] = actual_screenshot_path
                    password_login_sessions[session_id]['verification_url'] = None
                    password_login_sessions[session_id]['qr_code_url'] = None
                    log_with_user('info', f"人脸认证截图已保存: {session_id}, 路径: {actual_screenshot_path}", current_user)

                    # 发送通知到用户配置的渠道
                    def send_face_verification_notification():
                        """在后台线程中发送人脸验证通知"""
                        try:
                            from XianyuAutoAsync import XianyuLive
                            log_with_user('info', f"开始尝试发送人脸验证通知: {account_id}", current_user)

                            # 尝试获取XianyuLive实例（如果账号已经存在）
                            live_instance = XianyuLive.get_instance(account_id)

                            if live_instance:
                                log_with_user('info', f"找到账号实例，准备发送通知: {account_id}", current_user)
                                # 创建新的事件循环来运行异步通知
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                                try:
                                    new_loop.run_until_complete(
                                        live_instance.send_token_refresh_notification(
                                            error_message=message,
                                            notification_type="face_verification",
                                            verification_url=None,
                                            attachment_path=actual_screenshot_path
                                        )
                                    )
                                    log_with_user('info', f"✅ 已发送人脸验证通知: {account_id}", current_user)
                                except Exception as notify_err:
                                    log_with_user('error', f"发送人脸验证通知失败: {str(notify_err)}", current_user)
                                    import traceback
                                    log_with_user('error', f"通知错误详情: {traceback.format_exc()}", current_user)
                                finally:
                                    new_loop.close()
                            else:
                                # 如果账号实例不存在，记录警告并尝试从数据库获取通知配置
                                log_with_user('warning', f"账号实例不存在: {account_id}，尝试从数据库获取通知配置", current_user)
                                try:
                                    # 尝试从数据库获取通知配置
                                    notifications = db_manager.get_account_notifications(account_id)
                                    if notifications:
                                        log_with_user('info', f"找到 {len(notifications)} 个通知配置，但需要账号实例才能发送", current_user)
                                        log_with_user('warning', f"账号实例不存在，无法发送通知: {account_id}。请确保账号已登录并运行中。", current_user)
                                    else:
                                        log_with_user('warning', f"账号 {account_id} 未配置通知渠道", current_user)
                                except Exception as db_err:
                                    log_with_user('error', f"获取通知配置失败: {str(db_err)}", current_user)
                        except Exception as notify_err:
                            log_with_user('error', f"发送人脸验证通知时出错: {str(notify_err)}", current_user)
                            import traceback
                            log_with_user('error', f"通知错误详情: {traceback.format_exc()}", current_user)

                    # 在后台线程中发送通知，避免阻塞登录流程
                    import threading
                    notification_thread = threading.Thread(target=send_face_verification_notification)
                    notification_thread.daemon = True
                    notification_thread.start()
                    log_with_user('info', f"已启动人脸验证通知发送线程: {account_id}", current_user)
                elif verification_url:
                    # 如果没有截图，使用验证链接（兼容旧版本）
                    password_login_sessions[session_id]['status'] = 'verification_required'
                    password_login_sessions[session_id]['verification_url'] = verification_url
                    password_login_sessions[session_id]['screenshot_path'] = None
                    password_login_sessions[session_id]['qr_code_url'] = None
                    log_with_user('info', f"人脸认证验证链接已保存: {session_id}, URL: {verification_url}", current_user)

                    # 发送通知到用户配置的渠道
                    def send_face_verification_notification():
                        """在后台线程中发送人脸验证通知"""
                        try:
                            from XianyuAutoAsync import XianyuLive
                            log_with_user('info', f"开始尝试发送人脸验证通知: {account_id}", current_user)

                            # 尝试获取XianyuLive实例（如果账号已经存在）
                            live_instance = XianyuLive.get_instance(account_id)

                            if live_instance:
                                log_with_user('info', f"找到账号实例，准备发送通知: {account_id}", current_user)
                                # 创建新的事件循环来运行异步通知
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                                try:
                                    new_loop.run_until_complete(
                                        live_instance.send_token_refresh_notification(
                                            error_message=message,
                                            notification_type="face_verification",
                                            verification_url=verification_url
                                        )
                                    )
                                    log_with_user('info', f"✅ 已发送人脸验证通知: {account_id}", current_user)
                                except Exception as notify_err:
                                    log_with_user('error', f"发送人脸验证通知失败: {str(notify_err)}", current_user)
                                    import traceback
                                    log_with_user('error', f"通知错误详情: {traceback.format_exc()}", current_user)
                                finally:
                                    new_loop.close()
                            else:
                                # 如果账号实例不存在，记录警告并尝试从数据库获取通知配置
                                log_with_user('warning', f"账号实例不存在: {account_id}，尝试从数据库获取通知配置", current_user)
                                try:
                                    # 尝试从数据库获取通知配置
                                    notifications = db_manager.get_account_notifications(account_id)
                                    if notifications:
                                        log_with_user('info', f"找到 {len(notifications)} 个通知配置，但需要账号实例才能发送", current_user)
                                        log_with_user('warning', f"账号实例不存在，无法发送通知: {account_id}。请确保账号已登录并运行中。", current_user)
                                    else:
                                        log_with_user('warning', f"账号 {account_id} 未配置通知渠道", current_user)
                                except Exception as db_err:
                                    log_with_user('error', f"获取通知配置失败: {str(db_err)}", current_user)
                        except Exception as notify_err:
                            log_with_user('error', f"发送人脸验证通知时出错: {str(notify_err)}", current_user)
                            import traceback
                            log_with_user('error', f"通知错误详情: {traceback.format_exc()}", current_user)

                    # 在后台线程中发送通知，避免阻塞登录流程
                    import threading
                    notification_thread = threading.Thread(target=send_face_verification_notification)
                    notification_thread.daemon = True
                    notification_thread.start()
                    log_with_user('info', f"已启动人脸验证通知发送线程: {account_id}", current_user)
            except Exception as e:
                log_with_user('error', f"处理人脸认证通知失败: {str(e)}", current_user)

        # 调用登录方法（同步方法，需要在后台线程中执行）
        import threading

        def run_login():
            try:
                cookies_dict = slider_instance.login_with_password_playwright(
                    account=account,
                    password=password,
                    show_browser=show_browser,
                    notification_callback=notification_callback
                )

                if cookies_dict is None:
                    password_login_sessions[session_id]['status'] = 'failed'
                    password_login_sessions[session_id]['error'] = '登录失败，请检查账号密码是否正确'
                    log_with_user('error', f"账号密码登录失败: {account_id}", current_user)
                    return

                # 将cookie字典转换为字符串格式
                cookies_str = '; '.join([f"{k}={v}" for k, v in cookies_dict.items()])

                log_with_user('info', f"账号密码登录成功，获取到 {len(cookies_dict)} 个Cookie字段: {account_id}", current_user)

                # 检查是否已存在相同账号ID的Cookie
                existing_cookies = db_manager.get_all_cookies(user_id)
                is_new_account = account_id not in existing_cookies

                # 保存账号密码和Cookie到数据库
                # 使用 update_cookie_account_info 来保存，它会自动处理新账号和现有账号的情况
                update_success = db_manager.update_cookie_account_info(
                    account_id,
                    cookie_value=cookies_str,
                    username=account,
                    password=password,
                    show_browser=show_browser,
                    user_id=user_id  # 新账号时需要提供user_id
                )

                if update_success:
                    if is_new_account:
                        log_with_user('info', f"新账号Cookie和账号密码已保存: {account_id}", current_user)
                    else:
                        log_with_user('info', f"现有账号Cookie和账号密码已更新: {account_id}", current_user)
                else:
                    log_with_user('error', f"保存账号信息失败: {account_id}", current_user)

                # 添加到或更新cookie_manager（注意：不要在这里调用add_cookie或update_cookie，因为它们会覆盖账号密码）
                # 账号密码已经在上面通过update_cookie_account_info保存了
                # 这里只需要更新内存中的cookie值，不保存到数据库（避免覆盖账号密码）
                if cookie_manager.manager:
                    # 更新内存中的cookie值
                    cookie_manager.manager.cookies[account_id] = cookies_str
                    log_with_user('info', f"已更新cookie_manager中的Cookie（内存）: {account_id}", current_user)

                    # 如果是新账号，需要启动任务
                    if is_new_account:
                        # 使用异步方式启动任务，但不保存到数据库（避免覆盖账号密码）
                        try:
                            import asyncio
                            loop = cookie_manager.manager.loop
                            if loop:
                                # 确保关键词列表存在
                                if account_id not in cookie_manager.manager.keywords:
                                    cookie_manager.manager.keywords[account_id] = []

                                # 在后台启动任务（使用线程安全的方式，因为run_login是在后台线程中运行的）
                                try:
                                    # 尝试使用run_coroutine_threadsafe，这是线程安全的方式
                                    fut = asyncio.run_coroutine_threadsafe(
                                        cookie_manager.manager._run_xianyu(account_id, cookies_str, user_id),
                                        loop
                                    )
                                    # 不等待结果，让它在后台运行
                                    log_with_user('info', f"已启动新账号任务: {account_id}", current_user)
                                except RuntimeError as e:
                                    # 如果事件循环未运行，记录警告但不影响登录成功
                                    log_with_user('warning', f"事件循环未运行，无法启动新账号任务: {account_id}, 错误: {str(e)}", current_user)
                                    log_with_user('info', f"账号已保存，将在系统重启后自动启动任务: {account_id}", current_user)
                        except Exception as task_err:
                            log_with_user('warning', f"启动新账号任务失败: {account_id}, 错误: {str(task_err)}", current_user)
                            import traceback
                            logger.error(traceback.format_exc())

                # 登录成功后，调用_refresh_cookies_via_browser刷新Cookie
                try:
                    log_with_user('info', f"开始调用_refresh_cookies_via_browser刷新Cookie: {account_id}", current_user)
                    from XianyuAutoAsync import XianyuLive

                    # 创建临时的XianyuLive实例来刷新Cookie
                    temp_xianyu = XianyuLive(
                        cookies_str=cookies_str,
                        cookie_id=account_id,
                        user_id=user_id
                    )

                    # 重置扫码登录Cookie刷新标志，确保账号密码登录后能立即刷新
                    try:
                        temp_xianyu.reset_qr_cookie_refresh_flag()
                        log_with_user('info', f"已重置扫码登录Cookie刷新标志: {account_id}", current_user)
                    except Exception as reset_err:
                        log_with_user('debug', f"重置扫码登录Cookie刷新标志失败（不影响刷新）: {str(reset_err)}", current_user)

                    # 在后台异步执行刷新（不阻塞主流程）
                    async def refresh_cookies_task():
                        try:
                            refresh_success = await temp_xianyu._refresh_cookies_via_browser(triggered_by_refresh_token=False)
                            if refresh_success:
                                log_with_user('info', f"Cookie刷新成功: {account_id}", current_user)
                                # 刷新成功后，从数据库获取更新后的Cookie
                                updated_cookie_info = db_manager.get_cookie_details(account_id)
                                if updated_cookie_info:
                                    refreshed_cookies = updated_cookie_info.get('value', '')
                                    if refreshed_cookies:
                                        # 更新cookie_manager中的Cookie
                                        if cookie_manager.manager:
                                            cookie_manager.manager.update_cookie(account_id, refreshed_cookies, save_to_db=False)
                                        log_with_user('info', f"已更新刷新后的Cookie到cookie_manager: {account_id}", current_user)
                            else:
                                log_with_user('warning', f"Cookie刷新失败或跳过: {account_id}", current_user)
                        except Exception as refresh_e:
                            log_with_user('error', f"刷新Cookie时出错: {account_id}, 错误: {str(refresh_e)}", current_user)
                            import traceback
                            logger.error(traceback.format_exc())

                    # 在后台线程中运行异步任务
                    # 由于run_login是在线程中运行的，需要创建新的事件循环
                    def run_async_refresh():
                        try:
                            import asyncio
                            # 创建新的事件循环
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(refresh_cookies_task())
                            finally:
                                new_loop.close()
                        except Exception as e:
                            log_with_user('error', f"运行异步刷新任务失败: {account_id}, 错误: {str(e)}", current_user)

                    # 在后台线程中执行刷新任务
                    refresh_thread = threading.Thread(target=run_async_refresh, daemon=True)
                    refresh_thread.start()

                except Exception as refresh_err:
                    log_with_user('warning', f"调用_refresh_cookies_via_browser失败: {account_id}, 错误: {str(refresh_err)}", current_user)
                    # 刷新失败不影响登录成功

                # 更新会话状态
                password_login_sessions[session_id]['status'] = 'success'
                password_login_sessions[session_id]['account_id'] = account_id
                password_login_sessions[session_id]['is_new_account'] = is_new_account
                password_login_sessions[session_id]['cookie_count'] = len(cookies_dict)

            except Exception as e:
                error_msg = str(e)
                password_login_sessions[session_id]['status'] = 'failed'
                # 安全：存入会话的 error 仅保留脱敏后的客户端消息，原始异常只入日志
                password_login_sessions[session_id]['error'] = _safe_client_msg(e, "账号密码登录失败")
                log_with_user('error', f"账号密码登录失败: {account_id}, 错误: {error_msg}", current_user)
                logger.info(f"会话 {session_id} 状态已更新为 failed")  # 添加日志确认状态更新
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # 清理实例（释放并发槽位）
                try:
                    from utils.xianyu_slider_stealth import concurrency_manager
                    concurrency_manager.unregister_instance(account_id)
                    log_with_user('debug', f"已释放并发槽位: {account_id}", current_user)
                except Exception as cleanup_e:
                    log_with_user('warning', f"清理实例时出错: {str(cleanup_e)}", current_user)

        # 在后台线程中执行登录
        login_thread = threading.Thread(target=run_login, daemon=True)
        login_thread.start()

    except Exception as e:
        password_login_sessions[session_id]['status'] = 'failed'
        password_login_sessions[session_id]['error'] = _safe_client_msg(e, "账号密码登录失败")
        log_with_user('error', f"执行账号密码登录任务异常: {str(e)}", current_user)
        import traceback
        logger.error(traceback.format_exc())


@router.post("/password-login")
async def password_login(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """账号密码登录接口（异步，支持人脸认证）"""
    try:
        account_id = request.get('account_id')
        account = request.get('account')
        password = request.get('password')
        show_browser = request.get('show_browser', False)

        if not account_id or not account or not password:
            return {'success': False, 'message': '账号ID、登录账号和密码不能为空'}

        log_with_user('info', f"开始账号密码登录: {account_id}, 账号: {account}", current_user)

        import secrets
        session_id = secrets.token_urlsafe(16)
        user_id = current_user['user_id']

        sessions = password_login_sessions
        sessions[session_id] = {
            'account_id': account_id,
            'account': account,
            'password': password,
            'show_browser': show_browser,
            'status': 'processing',
            'verification_url': None,
            'screenshot_path': None,
            'qr_code_url': None,
            'slider_instance': None,
            'task': None,
            'timestamp': time.time(),
            'user_id': user_id,
        }

        task = asyncio.create_task(_execute_password_login(
            session_id, account_id, account, password, show_browser, user_id, current_user,
        ))
        sessions[session_id]['task'] = task

        return {
            'success': True,
            'session_id': session_id,
            'status': 'processing',
            'message': '登录任务已启动，请等待...',
        }
    except Exception as e:
        log_with_user('error', f"账号密码登录异常: {str(e)}", current_user)
        logger.error(traceback.format_exc())
        return {'success': False, 'message': safe_client_msg(e, "登录失败")}


@router.get("/password-login/check/{session_id}")
async def check_password_login_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """检查账号密码登录状态"""
    try:
        sessions = password_login_sessions

        # 清理过期会话（超过1小时）
        current_time = time.time()
        expired = [sid for sid, s in sessions.items() if current_time - s['timestamp'] > 3600]
        for sid in expired:
            sessions.pop(sid, None)

        if session_id not in sessions:
            return {'status': 'not_found', 'message': '会话不存在或已过期'}

        session = sessions[session_id]
        if session['user_id'] != current_user['user_id']:
            return {'status': 'forbidden', 'message': '无权限访问该会话'}

        status = session['status']

        if status == 'verification_required':
            return {
                'status': 'verification_required',
                'verification_url': session.get('verification_url'),
                'screenshot_path': session.get('screenshot_path'),
                'qr_code_url': session.get('qr_code_url'),
                'message': '需要人脸验证，请查看验证截图' if session.get('screenshot_path') else '需要人脸验证，请点击验证链接',
            }
        elif status == 'success':
            screenshot_path = session.get('screenshot_path')
            if screenshot_path:
                try:
                    from utils.image_utils import image_manager
                    if image_manager.delete_image(screenshot_path):
                        log_with_user('info', f"验证成功后已删除截图: {screenshot_path}", current_user)
                    else:
                        log_with_user('warning', f"删除截图失败: {screenshot_path}", current_user)
                except Exception as e:
                    log_with_user('error', f"删除截图时出错: {str(e)}", current_user)

            result = {
                'status': 'success',
                'message': f'账号 {session["account_id"]} 登录成功',
                'account_id': session['account_id'],
                'is_new_account': session.get('is_new_account', False),
                'cookie_count': session.get('cookie_count', 0),
            }
            sessions.pop(session_id, None)
            return result
        elif status == 'failed':
            screenshot_path = session.get('screenshot_path')
            if screenshot_path:
                try:
                    from utils.image_utils import image_manager
                    if image_manager.delete_image(screenshot_path):
                        log_with_user('info', f"验证失败后已删除截图: {screenshot_path}", current_user)
                    else:
                        log_with_user('warning', f"删除截图失败: {screenshot_path}", current_user)
                except Exception as e:
                    log_with_user('error', f"删除截图时出错: {str(e)}", current_user)

            error_msg = session.get('error', '登录失败')
            log_with_user('info', f"返回登录失败状态: {session_id}, 错误消息: {error_msg}", current_user)
            result = {'status': 'failed', 'message': error_msg, 'error': error_msg}
            sessions.pop(session_id, None)
            return result
        else:
            return {'status': 'processing', 'message': '登录处理中，请稍候...'}

    except Exception as e:
        log_with_user('error', f"检查账号密码登录状态异常: {str(e)}", current_user)
        return {'status': 'error', 'message': safe_client_msg(e, "操作失败")}

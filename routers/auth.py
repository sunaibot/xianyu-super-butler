"""
routers/auth.py
================
认证流程路由（从 reply_server.py 迁移）。

路由清单：
登录/登出/验证：
- POST /login                       用户名/邮箱/验证码登录（含限流）
- GET  /verify                      验证当前 session 是否有效
- POST /logout                      登出并清除 Cookie

密码管理：
- POST /change-admin-password       管理员修改密码
- POST /change-password             普通用户修改密码（含限流）
- GET  /api/check-default-password  已废弃，返回 404

图形验证码：
- POST /generate-captcha            生成图形验证码（含限流）
- POST /verify-captcha              验证图形验证码（含限流）

极验滑动验证：
- GET  /geetest/register            极验初始化
- POST /geetest/validate             极验二次验证

邮箱验证码 / 注册 / 发消息：
- POST /send-verification-code      发送邮箱验证码（含限流）
- POST /register                    用户注册（含限流）
- POST /send-message                API 秘钥发消息

注册/登录信息设置：
- GET  /registration-status         获取注册开关（公开）
- GET  /login-info-status           获取登录信息显示状态（公开）
- PUT  /registration-settings       更新注册开关（管理员）
- PUT  /login-info-settings         更新登录信息显示（管理员）

设计要点：
- session 管理（_create_session / _set_auth_cookies / _delete_session）通过懒加载从 reply_server 导入
- 速率限制器通过 make_rate_limiter 本地创建（与 reply_server 独立计数，功能等价）
- 极验状态存储在本模块内（进程内字典，与原实现一致）
"""
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from loguru import logger

from .deps import require_auth, require_admin, optional_auth, safe_client_msg
from .rate_limit import make_rate_limiter

router = APIRouter(tags=["auth"])


# ==================== 常量 ====================

RESERVED_USERNAMES = {'admin', 'administrator', 'root', 'system', 'superuser'}

SESSION_COOKIE_NAME = "session"
WS_TOKEN_COOKIE_NAME = "ws_token"


# ==================== 速率限制器 ====================

login_rate_limit = make_rate_limiter(max_requests=5, window_seconds=60, key_prefix='login')
register_rate_limit = make_rate_limiter(max_requests=3, window_seconds=300, key_prefix='register')
verification_code_rate_limit = make_rate_limiter(max_requests=3, window_seconds=300, key_prefix='verify_code')
captcha_rate_limit = make_rate_limiter(max_requests=10, window_seconds=60, key_prefix='captcha')
change_password_rate_limit = make_rate_limiter(max_requests=3, window_seconds=300, key_prefix='change_pwd')


# ==================== Pydantic 模型 ====================

class LoginRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    verification_code: Optional[str] = None


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    is_admin: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CaptchaRequest(BaseModel):
    session_id: str


class CaptchaResponse(BaseModel):
    success: bool
    captcha_image: str
    session_id: str
    message: str


class VerifyCaptchaRequest(BaseModel):
    session_id: str
    captcha_code: str


class VerifyCaptchaResponse(BaseModel):
    success: bool
    message: str


class SendCodeRequest(BaseModel):
    email: str
    type: str = 'register'  # register | login


class SendCodeResponse(BaseModel):
    success: bool
    message: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    verification_code: str


class RegisterResponse(BaseModel):
    success: bool
    message: str


class SendMessageRequest(BaseModel):
    api_key: str
    cookie_id: str
    chat_id: str
    to_user_id: str
    message: str


class SendMessageResponse(BaseModel):
    success: bool
    message: str


class RegistrationSettingUpdate(BaseModel):
    enabled: bool


class LoginInfoSettingUpdate(BaseModel):
    enabled: bool


# ==================== 极验状态存储 ====================

geetest_status_store: dict = {}


def _cleanup_expired_geetest_status():
    current_time = time.time()
    expired_keys = [k for k, v in geetest_status_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del geetest_status_store[k]


def _set_geetest_status(challenge: str, status: int):
    _cleanup_expired_geetest_status()
    geetest_status_store[challenge] = {
        "status": status,
        "expires_at": time.time() + 300,
    }


def _get_geetest_status(challenge: str) -> int:
    _cleanup_expired_geetest_status()
    stored = geetest_status_store.get(challenge)
    if stored and stored["expires_at"] > time.time():
        return stored["status"]
    return 0


class GeetestRegisterResponse(BaseModel):
    success: bool
    code: int = 200
    message: str = ""
    data: Optional[dict] = None


class GeetestValidateRequest(BaseModel):
    challenge: str
    validate_str: str = Field(..., alias='validate')
    seccode: str
    model_config = {'populate_by_name': True}


class GeetestValidateResponse(BaseModel):
    success: bool
    code: int = 200
    message: str = ""


# ==================== 懒加载导入 ====================

def _session_funcs():
    """从 deps 懒加载 session 管理函数"""
    from .deps import _create_session, _set_auth_cookies, _delete_session
    return _create_session, _set_auth_cookies, _delete_session


def _verify_api_key(api_key: str) -> bool:
    """验证API秘钥（必须显式配置，不再硬编码）"""
    try:
        from db_manager import db_manager
        qq_secret_key = db_manager.get_system_setting('qq_reply_secret_key')
        if not qq_secret_key:
            logger.error("qq_reply_secret_key 未配置，拒绝请求")
            return False
        return api_key == qq_secret_key
    except Exception as e:
        logger.error(f"验证API秘钥时发生异常: {e}")
        return False


# ==================== 登录 / 登出 / 验证 ====================

@router.post('/login')
async def login(request: LoginRequest, _: bool = Depends(login_rate_limit)):
    """登录接口（用户名/密码、邮箱/密码、邮箱/验证码三种方式）"""
    from db_manager import db_manager
    _create_session, _set_auth_cookies, _ = _session_funcs()

    if request.username and request.password:
        logger.info(f"【{request.username}】尝试用户名登录")
        if db_manager.verify_user_password(request.username, request.password):
            user = db_manager.get_user_by_username(request.username)
            if user:
                is_admin = bool(user.get('is_admin', False))
                session_id = _create_session({
                    'id': user['id'],
                    'username': user['username'],
                    'is_admin': is_admin,
                })
                if is_admin:
                    logger.info(f"【{user['username']}#{user['id']}】登录成功（管理员）")
                else:
                    logger.info(f"【{user['username']}#{user['id']}】登录成功")
                resp = JSONResponse(content=LoginResponse(
                    success=True, token=None, message="登录成功",
                    user_id=user['id'], username=user['username'], is_admin=is_admin,
                ).model_dump())
                _set_auth_cookies(resp, session_id)
                return resp
        logger.warning(f"【{request.username}】登录失败：用户名或密码错误")
        return LoginResponse(success=False, message="用户名或密码错误")

    elif request.email and request.password:
        logger.info(f"【{request.email}】尝试邮箱密码登录")
        user = db_manager.get_user_by_email(request.email)
        if user and db_manager.verify_user_password(user['username'], request.password):
            is_admin = bool(user.get('is_admin', False))
            session_id = _create_session({
                'id': user['id'], 'username': user['username'], 'is_admin': is_admin,
            })
            logger.info(f"【{user['username']}#{user['id']}】邮箱登录成功")
            resp = JSONResponse(content=LoginResponse(
                success=True, token=None, message="登录成功",
                user_id=user['id'], username=user['username'], is_admin=is_admin,
            ).model_dump())
            _set_auth_cookies(resp, session_id)
            return resp
        logger.warning(f"【{request.email}】邮箱登录失败：邮箱或密码错误")
        return LoginResponse(success=False, message="邮箱或密码错误")

    elif request.email and request.verification_code:
        logger.info(f"【{request.email}】尝试邮箱验证码登录")
        if not db_manager.verify_email_code(request.email, request.verification_code, 'login'):
            logger.warning(f"【{request.email}】验证码登录失败：验证码错误或已过期")
            return LoginResponse(success=False, message="验证码错误或已过期")
        user = db_manager.get_user_by_email(request.email)
        if not user:
            logger.warning(f"【{request.email}】验证码登录失败：用户不存在")
            return LoginResponse(success=False, message="用户不存在")
        is_admin = bool(user.get('is_admin', False))
        session_id = _create_session({
            'id': user['id'], 'username': user['username'], 'is_admin': is_admin,
        })
        logger.info(f"【{user['username']}#{user['id']}】验证码登录成功")
        resp = JSONResponse(content=LoginResponse(
            success=True, token=None, message="登录成功",
            user_id=user['id'], username=user['username'], is_admin=is_admin,
        ).model_dump())
        _set_auth_cookies(resp, session_id)
        return resp
    else:
        return LoginResponse(success=False, message="请提供有效的登录信息")


@router.get('/verify')
async def verify(user_info: Optional[Dict[str, Any]] = Depends(optional_auth)):
    """验证当前 session 是否有效"""
    from db_manager import db_manager
    initialized = db_manager.is_system_initialized()

    if user_info:
        return {
            "authenticated": True,
            "user_id": user_info['user_id'],
            "username": user_info['username'],
            "is_admin": bool(user_info.get('is_admin', False)),
            "initialized": initialized,
        }
    return {"authenticated": False, "initialized": initialized}


@router.post('/logout')
async def logout(response: Response, session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    """登出并清除 Cookie"""
    _, _, _delete_session = _session_funcs()
    if session:
        _delete_session(session)
    resp = JSONResponse(content={"message": "已登出"})
    resp.delete_cookie(key=SESSION_COOKIE_NAME, path='/')
    resp.delete_cookie(key=WS_TOKEN_COOKIE_NAME, path='/')
    return resp


# ==================== 密码管理 ====================

@router.post('/change-admin-password')
async def change_admin_password(request: ChangePasswordRequest, admin_user: Dict[str, Any] = Depends(require_admin)):
    """管理员修改密码"""
    from db_manager import db_manager
    try:
        current_username = admin_user.get('username', '')
        if not current_username:
            return {"success": False, "message": "无法识别当前用户"}
        if not db_manager.verify_user_password(current_username, request.current_password):
            return {"success": False, "message": "当前密码错误"}
        success = db_manager.update_user_password(current_username, request.new_password)
        if success:
            logger.info(f"【{current_username}#{admin_user['user_id']}】管理员密码修改成功")
            return {"success": True, "message": "密码修改成功"}
        return {"success": False, "message": "密码修改失败"}
    except Exception as e:
        logger.error(f"修改管理员密码异常: {e}")
        return {"success": False, "message": "系统错误"}


@router.post('/change-password')
async def change_user_password(
    request: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(require_auth),
    _: bool = Depends(change_password_rate_limit),
):
    """普通用户修改密码"""
    from db_manager import db_manager
    try:
        username = current_user.get('username')
        user_id = current_user.get('user_id')
        if not username:
            return {"success": False, "message": "无法获取用户信息"}
        if not db_manager.verify_user_password(username, request.current_password):
            return {"success": False, "message": "当前密码错误"}
        success = db_manager.update_user_password(username, request.new_password)
        if success:
            logger.info(f"【{username}#{user_id}】用户密码修改成功")
            return {"success": True, "message": "密码修改成功"}
        return {"success": False, "message": "密码修改失败"}
    except Exception as e:
        logger.error(f"修改用户密码异常: {e}")
        return {"success": False, "message": "系统错误"}


@router.get('/api/check-default-password')
async def check_default_password(current_user: Dict[str, Any] = Depends(require_auth)):
    """已废弃：不再支持默认口令检查（安全原因）"""
    raise HTTPException(status_code=404, detail="接口已移除")


# ==================== 图形验证码 ====================

@router.post('/generate-captcha')
async def generate_captcha(request: CaptchaRequest, _: bool = Depends(captcha_rate_limit)):
    """生成图形验证码"""
    from db_manager import db_manager
    try:
        captcha_text, captcha_image = db_manager.generate_captcha()
        if not captcha_image:
            return CaptchaResponse(success=False, captcha_image="", session_id=request.session_id, message="图形验证码生成失败")
        if db_manager.save_captcha(request.session_id, captcha_text):
            return CaptchaResponse(success=True, captcha_image=captcha_image, session_id=request.session_id, message="图形验证码生成成功")
        return CaptchaResponse(success=False, captcha_image="", session_id=request.session_id, message="图形验证码保存失败")
    except Exception as e:
        logger.error(f"生成图形验证码失败: {e}")
        return CaptchaResponse(success=False, captcha_image="", session_id=request.session_id, message="图形验证码生成失败")


@router.post('/verify-captcha')
async def verify_captcha(request: VerifyCaptchaRequest, _: bool = Depends(captcha_rate_limit)):
    """验证图形验证码"""
    from db_manager import db_manager
    try:
        if db_manager.verify_captcha(request.session_id, request.captcha_code):
            return VerifyCaptchaResponse(success=True, message="图形验证码验证成功")
        return VerifyCaptchaResponse(success=False, message="图形验证码错误或已过期")
    except Exception as e:
        logger.error(f"验证图形验证码失败: {e}")
        return VerifyCaptchaResponse(success=False, message="图形验证码验证失败")


# ==================== 极验滑动验证码 ====================

@router.get('/geetest/register', response_model=GeetestRegisterResponse)
async def geetest_register():
    """获取极验验证码初始化参数"""
    try:
        from utils.geetest import GeetestLib
        gt_lib = GeetestLib()
        result = await gt_lib.register()
        data = result.to_dict()
        logger.info(f"极验初始化结果: status={result.status}, data={data}")
        challenge = data.get("challenge", "")
        if challenge:
            _set_geetest_status(challenge, 0)
        return GeetestRegisterResponse(
            success=True, code=200,
            message="获取成功" if result.status == 1 else "宕机模式",
            data=data,
        )
    except Exception as e:
        logger.error(f"极验初始化失败: {e}")
        try:
            from utils.geetest import GeetestLib
            gt_lib = GeetestLib()
            result = gt_lib.local_init()
            data = result.to_dict()
            challenge = data.get("challenge", "")
            if challenge:
                _set_geetest_status(challenge, 0)
            return GeetestRegisterResponse(success=True, code=200, message="本地初始化", data=data)
        except Exception as e2:
            logger.error(f"极验本地初始化也失败: {e2}")
            return GeetestRegisterResponse(success=False, code=500, message="验证码服务异常")


@router.post('/geetest/validate', response_model=GeetestValidateResponse)
async def geetest_validate(request: GeetestValidateRequest):
    """极验二次验证"""
    try:
        if _get_geetest_status(request.challenge) == 1:
            return GeetestValidateResponse(success=True, code=200, message="验证通过")
        from utils.geetest import GeetestLib
        gt_lib = GeetestLib()
        is_normal_mode = len(request.challenge) == 32
        if is_normal_mode:
            result = await gt_lib.success_validate(request.challenge, request.validate_str, request.seccode)
        else:
            result = gt_lib.fail_validate(request.challenge, request.validate_str, request.seccode)
        if result.status == 1:
            _set_geetest_status(request.challenge, 1)
            return GeetestValidateResponse(success=True, code=200, message="验证通过")
        return GeetestValidateResponse(success=False, code=400, message=result.msg or "验证失败")
    except Exception as e:
        logger.error(f"极验二次验证失败: {e}")
        return GeetestValidateResponse(success=False, code=500, message="验证服务异常")


# ==================== 邮箱验证码 / 注册 / 发消息 ====================

@router.post('/send-verification-code')
async def send_verification_code(request: SendCodeRequest, _: bool = Depends(verification_code_rate_limit)):
    """发送邮箱验证码"""
    from db_manager import db_manager
    try:
        if request.type == 'register':
            existing_user = db_manager.get_user_by_email(request.email)
            if existing_user:
                return SendCodeResponse(success=False, message="该邮箱已被注册")
        elif request.type == 'login':
            existing_user = db_manager.get_user_by_email(request.email)
            if not existing_user:
                return SendCodeResponse(success=False, message="该邮箱未注册")

        code = db_manager.generate_verification_code()
        if not db_manager.save_verification_code(request.email, code, request.type):
            return SendCodeResponse(success=False, message="验证码保存失败，请稍后重试")
        if await db_manager.send_verification_email(request.email, code):
            return SendCodeResponse(success=True, message="验证码已发送到您的邮箱，请查收")
        return SendCodeResponse(success=False, message="验证码发送失败，请检查邮箱地址或稍后重试")
    except Exception as e:
        logger.error(f"发送验证码失败: {e}")
        return SendCodeResponse(success=False, message="发送验证码失败，请稍后重试")


@router.post('/register')
async def register(request: RegisterRequest, _: bool = Depends(register_rate_limit)):
    """用户注册"""
    from db_manager import db_manager
    registration_enabled = db_manager.get_system_setting('registration_enabled')
    if registration_enabled != 'true':
        logger.warning(f"【{request.username}】注册失败: 注册功能已关闭")
        return RegisterResponse(success=False, message="注册功能已关闭，请联系管理员")

    try:
        logger.info(f"【{request.username}】尝试注册，邮箱: {request.email}")
        if request.username.lower() in RESERVED_USERNAMES:
            return RegisterResponse(success=False, message="该用户名为系统保留名称，请更换")
        if not db_manager.verify_email_code(request.email, request.verification_code):
            return RegisterResponse(success=False, message="验证码错误或已过期")
        if db_manager.get_user_by_username(request.username):
            return RegisterResponse(success=False, message="用户名已存在")
        if db_manager.get_user_by_email(request.email):
            return RegisterResponse(success=False, message="该邮箱已被注册")
        if db_manager.create_user(request.username, request.email, request.password):
            logger.info(f"【{request.username}】注册成功")
            return RegisterResponse(success=True, message="注册成功，请登录")
        return RegisterResponse(success=False, message="注册失败，请稍后重试")
    except Exception as e:
        logger.error(f"【{request.username}】注册异常: {e}")
        return RegisterResponse(success=False, message="注册失败，请稍后重试")


@router.post('/send-message', response_model=SendMessageResponse)
async def send_message_api(request: SendMessageRequest):
    """发送消息API接口（使用秘钥验证）"""
    try:
        def clean_param(p):
            if isinstance(p, str):
                return p.replace('\\n', '').replace('\n', '')
            return p

        cleaned_api_key = clean_param(request.api_key)
        cleaned_cookie_id = clean_param(request.cookie_id)
        cleaned_chat_id = clean_param(request.chat_id)
        cleaned_to_user_id = clean_param(request.to_user_id)
        cleaned_message = clean_param(request.message)

        if not cleaned_api_key:
            return SendMessageResponse(success=False, message="API秘钥不能为空")
        if not _verify_api_key(cleaned_api_key):
            logger.warning(f"API秘钥验证失败: {cleaned_api_key}")
            return SendMessageResponse(success=False, message="API秘钥验证失败")

        for name, val in {'cookie_id': cleaned_cookie_id, 'chat_id': cleaned_chat_id,
                          'to_user_id': cleaned_to_user_id, 'message': cleaned_message}.items():
            if not val:
                return SendMessageResponse(success=False, message=f"参数 {name} 不能为空")

        from XianyuAutoAsync import XianyuLive
        live_instance = XianyuLive.get_instance(cleaned_cookie_id)
        if not live_instance:
            return SendMessageResponse(success=False, message="账号实例不存在或未连接，请检查账号状态")
        if not live_instance.ws or live_instance.ws.closed:
            return SendMessageResponse(success=False, message="账号WebSocket连接已断开，请等待重连")

        await live_instance.send_msg(live_instance.ws, cleaned_chat_id, cleaned_to_user_id, cleaned_message)
        logger.info(f"API成功发送消息: {cleaned_cookie_id} -> {cleaned_to_user_id}, 内容: {cleaned_message[:50]}{'...' if len(cleaned_message) > 50 else ''}")
        return SendMessageResponse(success=True, message="消息发送成功")
    except Exception as e:
        logger.error(f"API发送消息异常: {clean_param(request.cookie_id) if 'clean_param' in locals() else request.cookie_id} -> {clean_param(request.to_user_id) if 'clean_param' in locals() else request.to_user_id}, 错误: {str(e)}")
        return SendMessageResponse(success=False, message=f"发送消息失败: {str(e)}")


# ==================== 注册/登录信息设置 ====================

@router.get('/registration-status')
def get_registration_status():
    """获取注册开关状态（公开接口）"""
    from db_manager import db_manager
    try:
        enabled_str = db_manager.get_system_setting('registration_enabled')
        if enabled_str is None:
            return {'enabled': True, 'message': '注册功能已开启'}
        enabled_bool = enabled_str == 'true'
        return {'enabled': enabled_bool, 'message': '注册功能已开启' if enabled_bool else '注册功能已关闭'}
    except Exception as e:
        logger.error(f"获取注册状态失败: {e}")
        return {'enabled': True, 'message': '注册功能已开启'}


@router.get('/login-info-status')
def get_login_info_status():
    """获取默认登录信息显示状态（公开接口）"""
    from db_manager import db_manager
    try:
        enabled_str = db_manager.get_system_setting('show_default_login_info')
        if enabled_str is None:
            return {"enabled": True}
        return {"enabled": enabled_str == 'true'}
    except Exception as e:
        logger.error(f"获取登录信息显示状态失败: {e}")
        return {"enabled": True}


@router.put('/registration-settings')
def update_registration_settings(setting_data: RegistrationSettingUpdate, admin_user: Dict[str, Any] = Depends(require_admin)):
    """更新注册开关设置（仅管理员）"""
    from db_manager import db_manager
    try:
        enabled = setting_data.enabled
        success = db_manager.set_system_setting('registration_enabled', 'true' if enabled else 'false', '是否开启用户注册')
        if success:
            logger.info(f"【{admin_user.get('username')}#{admin_user['user_id']}】更新注册设置: {'开启' if enabled else '关闭'}")
            return {'success': True, 'enabled': enabled, 'message': f"注册功能已{'开启' if enabled else '关闭'}"}
        raise HTTPException(status_code=500, detail='更新注册设置失败')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新注册设置失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put('/login-info-settings')
def update_login_info_settings(setting_data: LoginInfoSettingUpdate, admin_user: Dict[str, Any] = Depends(require_admin)):
    """更新默认登录信息显示设置（仅管理员）"""
    from db_manager import db_manager
    try:
        enabled = setting_data.enabled
        success = db_manager.set_system_setting('show_default_login_info', 'true' if enabled else 'false', '是否显示默认登录信息')
        if success:
            logger.info(f"【{admin_user.get('username')}#{admin_user['user_id']}】更新登录信息显示设置: {'开启' if enabled else '关闭'}")
            return {'success': True, 'enabled': enabled, 'message': f"默认登录信息显示已{'开启' if enabled else '关闭'}"}
        raise HTTPException(status_code=500, detail='更新设置失败')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新登录信息显示设置失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

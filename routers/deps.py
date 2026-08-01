"""
routers/deps.py
================
FastAPI 路由共享依赖与工具函数。

设计原则：
- 独立实现鉴权逻辑，不依赖 reply_server.py 内部函数，避免循环导入
- 新 router 通过 `from .deps import require_auth, require_admin, safe_error` 使用
- 与 reply_server.py 现有鉴权逻辑等价（均解析 session cookie → 查 sessions 表）
"""
import time
import sqlite3
import secrets
import re
from typing import Optional, Dict, Any
from fastapi import Cookie, Depends, HTTPException, status, Response

from loguru import logger
from config import DB_PATH as _DEFAULT_DB_PATH

# Session Cookie 配置
SESSION_COOKIE_NAME = "session"
WS_TOKEN_COOKIE_NAME = "ws_token"
SESSION_EXPIRE_SECONDS = 24 * 60 * 60

# 敏感信息过滤正则
_SENSITIVE_DETAIL_PATTERNS = re.compile(
    r'(?i)(password|passwd|secret|token|api[_-]?key|cookie|authorization|/data/|\\data\\|\.db|sqlite)'
)

# 可安全透传给客户端的异常类型
_SAFE_CLIENT_EXCEPTIONS = (ValueError, KeyError, AttributeError, TypeError)


def _get_db_path() -> str:
    return _DEFAULT_DB_PATH


# ==================== Session 管理 ====================

def _init_sessions_table_if_needed():
    """确保 sessions 表存在"""
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        ''')
        conn.commit()
    finally:
        conn.close()


def _create_session(user: Dict[str, Any]) -> str:
    """创建会话，返回 session_id"""
    _init_sessions_table_if_needed()
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + SESSION_EXPIRE_SECONDS

    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (session_id, user_id, username, is_admin, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                int(user['id']),
                str(user['username']),
                1 if user.get('is_admin') else 0,
                int(expires_at),
                int(now),
            ),
        )
        conn.commit()
        return session_id
    finally:
        conn.close()


def _set_auth_cookies(resp: Response, session_id: str):
    """设置认证Cookie（httponly 的 session + js 可读的 ws_token）"""
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite='lax',
        secure=False,
        max_age=SESSION_EXPIRE_SECONDS,
        path='/',
    )
    resp.set_cookie(
        key=WS_TOKEN_COOKIE_NAME,
        value=session_id,
        httponly=False,
        samesite='lax',
        secure=False,
        max_age=SESSION_EXPIRE_SECONDS,
        path='/',
    )


def _delete_session(session_id: str) -> None:
    """删除会话"""
    _init_sessions_table_if_needed()
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """根据 session_id 查询会话，返回用户信息或 None"""
    if not session_id:
        return None
    try:
        _init_sessions_table_if_needed()
        conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id, user_id, username, is_admin, expires_at FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            now = int(time.time())
            expires_at = int(row[4])
            if expires_at <= now:
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return None

            return {
                'session_id': row[0],
                'user_id': int(row[1]),
                'username': row[2],
                'is_admin': bool(row[3]),
                'timestamp': float(now),
            }
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error(f"[deps] 查询 session 失败: {e}")
        return None


# ==================== 用户日志工具 ====================

def get_user_log_prefix(user_info: Dict[str, Any] = None) -> str:
    """获取用户日志前缀"""
    if user_info:
        return f"【{user_info['username']}#{user_info['user_id']}】"
    return "【系统】"


def log_with_user(level: str, message: str, user_info: Dict[str, Any] = None):
    """带用户信息的日志记录"""
    prefix = get_user_log_prefix(user_info)
    full_message = f"{prefix} {message}"

    if level.lower() == 'info':
        logger.info(full_message)
    elif level.lower() == 'error':
        logger.error(full_message)
    elif level.lower() == 'warning':
        logger.warning(full_message)
    elif level.lower() == 'debug':
        logger.debug(full_message)
    else:
        logger.info(full_message)


def get_current_user_from_session_cookie(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)
) -> Optional[Dict[str, Any]]:
    """解析 session cookie → 返回用户信息（FastAPI 依赖）"""
    return _get_session(session) if session else None


def require_auth(
    user_info: Optional[Dict[str, Any]] = Depends(get_current_user_from_session_cookie)
) -> Dict[str, Any]:
    """要求登录，否则 401"""
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return user_info


def optional_auth(
    user_info: Optional[Dict[str, Any]] = Depends(get_current_user_from_session_cookie)
) -> Optional[Dict[str, Any]]:
    """可选认证：未登录也放行，user_info 可能为 None"""
    return user_info


def require_admin(
    current_user: Dict[str, Any] = Depends(require_auth)
) -> Dict[str, Any]:
    """要求管理员，否则 403"""
    if not current_user.get('is_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def get_user_id(user_info: Dict[str, Any] = Depends(require_auth)) -> int:
    """便捷依赖：返回当前用户 ID"""
    return int(user_info.get('user_id', 0))


def safe_client_msg(e: Exception, default: str = "操作失败") -> str:
    """构造可安全回传给客户端的错误消息（敏感片段脱敏）"""
    if isinstance(e, _SAFE_CLIENT_EXCEPTIONS):
        msg = str(e).strip()
        if not msg:
            return default
        return _SENSITIVE_DETAIL_PATTERNS.sub('***', msg)
    return default


def server_error(e: Exception, action: str = "操作"):
    """统一 500 响应：日志记录完整异常，客户端返回通用消息"""
    logger.error(f"[{action}] 服务端异常: {e}", exc_info=True)
    return HTTPException(status_code=500, detail=f"{action}失败，请稍后重试")


def client_error(e: Exception, action: str = "操作"):
    """统一 4xx 响应：业务校验异常可透传"""
    return HTTPException(status_code=400, detail=safe_client_msg(e, f"{action}失败"))

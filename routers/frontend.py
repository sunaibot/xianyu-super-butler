"""
routers/frontend.py
===================
前端 SPA 页面路由 + catch-all（从 reply_server.py 迁移）。

路由清单：
- GET /               首页 → index.html
- GET /login.html      登录页 → index.html
- GET /login           登录页 → index.html
- GET /init            初始化页 → index.html
- GET /register.html   注册页 → 检查注册开关后 → index.html
- GET /{path:path}     catch-all：非 API 路径返回 index.html，API 路径返回 404

设计要点：
- 无需认证（公开页面）
- catch-all 必须在所有 API 路由之后注册（本 router 在 __init__.py 中排在最后）
- API_PREFIXES 列表用于区分 API 请求（返回 404）和前端路由（返回 index.html）
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["frontend"])


# 前端静态文件目录（与 reply_server.py 中的 static_dir 指向同一位置）
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

# 不需要返回前端页面的路径前缀（API 路径）
# catch-all 遇到这些前缀时返回 404，而不是 index.html
# 注意：仅列出实际存在的 API 路径前缀，避免误拦截前端路由
_API_PREFIXES = [
    '/api/', '/static/', '/assets', '/health', '/login', '/logout',
    '/verify', '/change-password', '/change-admin-password',
    '/cookie/', '/password-login', '/face-verification', '/qr-login',
    '/register', '/send-message', '/send-verification-code',
    '/generate-captcha', '/verify-captcha', '/geetest',
    '/registration-status', '/registration-settings',
    '/login-info-status', '/login-info-settings',
    '/xianyu/reply', '/webhook', '/kb', '/admin', '/analytics',
    '/backup', '/system', '/risk-control', '/logs', '/items',
    '/item-reply', '/itemReplays',
    '/cookies', '/cards', '/delivery-rules', '/keywords',
    '/ai-reply', '/user-settings', '/default-replies', '/notification',
    '/message-notifications', '/upload-image', '/debug',
]


async def _serve_frontend() -> HTMLResponse:
    """服务 React 前端 SPA"""
    index_path = os.path.join(_STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(f.read())
    return HTMLResponse('<h3>Frontend not found. Please build the frontend first.</h3>')


# ==================== 页面路由 ====================

@router.get('/', response_class=HTMLResponse)
async def root():
    """首页"""
    return await _serve_frontend()


@router.get('/login.html', response_class=HTMLResponse)
async def login_page():
    """登录页"""
    return await _serve_frontend()


@router.get('/login', response_class=HTMLResponse)
async def login_route():
    """登录页（GET，与 POST /login 认证接口不同方法，无冲突）"""
    return await _serve_frontend()


@router.get('/init', response_class=HTMLResponse)
async def init_route():
    """初始化页"""
    return await _serve_frontend()


@router.get('/register.html', response_class=HTMLResponse)
async def register_page():
    """注册页（检查注册开关）"""
    from db_manager import db_manager
    registration_enabled = db_manager.get_system_setting('registration_enabled')
    if registration_enabled != 'true':
        return HTMLResponse('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>注册已关闭</title>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .message { color: #666; font-size: 18px; }
                .back-link { margin-top: 20px; }
                .back-link a { color: #007bff; text-decoration: none; }
            </style>
        </head>
        <body>
            <h2>🚫 注册功能已关闭</h2>
            <p class="message">系统管理员已关闭用户注册功能</p>
            <div class="back-link">
                <a href="/">← 返回首页</a>
            </div>
        </body>
        </html>
        ''', status_code=403)

    return await _serve_frontend()


# ==================== Catch-All（必须最后注册） ====================

@router.get('/{path:path}', response_class=HTMLResponse)
async def catch_all_route(path: str):
    """
    Catch-all 路由：处理所有未匹配的 GET 请求
    如果是 API 请求，返回 404；否则返回前端 index.html
    """
    full_path = f'/{path}'
    for prefix in _API_PREFIXES:
        if full_path.startswith(prefix):
            raise HTTPException(status_code=404, detail="Not Found")

    return await _serve_frontend()



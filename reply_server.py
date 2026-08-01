"""
reply_server.py
================
FastAPI 应用入口（骨架）。

所有业务路由已迁移至 routers/ 目录，按域拆分：
- auth, cookies, orders, items, keywords, ai_reply, user_settings
- logs, backup, risk_control, analytics, services, admin, kb
- qr_login, password_login, face_verification
- xianyu_reply, system_settings, health, frontend, plugins

本文件仅保留：
1. app 实例创建
2. CORS 中间件 + 请求日志中间件 + 全局异常处理器
3. 静态文件挂载（必须在 register_routers 之前）
4. WebSocket 实时推送端点
5. 事件推送辅助函数
6. register_routers() 调用
"""
import os
import time
import asyncio
from typing import Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

import cookie_manager
from file_log_collector import setup_file_logging
from event_bus import event_bus
from config import parse_cors_origins

# 刮刮乐远程控制路由
try:
    from api_captcha_remote import router as captcha_router
    CAPTCHA_ROUTER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ api_captcha_remote 未找到，刮刮乐远程控制功能不可用")
    CAPTCHA_ROUTER_AVAILABLE = False


# ==================== App 实例 ====================

app = FastAPI(
    title="Xianyu Auto Reply API",
    version="1.0.0",
    description="闲鱼自动回复系统API",
    docs_url="/docs",
    redoc_url="/redoc"
)


# ==================== CORS ====================

# CORS 配置由 config.parse_cors_origins() 集中解析（读取 CORS_ORIGINS 环境变量）
cors_origins, cors_credentials = parse_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Cookie", "X-Requested-With"],
)
logger.info(f"CORS配置: origins={cors_origins}, credentials={cors_credentials}")


# ==================== 刮刮乐路由 ====================

if CAPTCHA_ROUTER_AVAILABLE:
    app.include_router(captcha_router)
    logger.info("✅ 已注册刮刮乐远程控制路由: /api/captcha")
else:
    logger.warning("⚠️ 刮刮乐远程控制路由未注册")


# ==================== 静态文件挂载（必须在 register_routers 之前）=================
# 原因：register_routers 包含 frontend.py 的 catch-all /{path:path}，
# 若 mount 在其后，catch-all 会先命中 /static/xxx 并返回 404，StaticFiles 无法处理。

static_dir = os.path.join(os.path.dirname(__file__), 'static')
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount('/static', StaticFiles(directory=static_dir), name='static')

# /assets 挂载（指向 static/assets），仅在构建产物存在时挂载
assets_dir = os.path.join(static_dir, 'assets')
if os.path.exists(assets_dir):
    app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

# 确保图片上传目录存在
uploads_dir = os.path.join(static_dir, 'uploads', 'images')
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir, exist_ok=True)
    logger.info(f"创建图片上传目录: {uploads_dir}")


# ==================== 模块化业务路由注册 ====================

try:
    from routers import register_routers
    register_routers(app)
    logger.info("✅ 已注册模块化业务路由")
except ImportError as e:
    logger.warning(f"⚠️ 模块化业务路由注册失败: {e}")


# ==================== 服务插件生命周期 ====================

try:
    from services import startup_all, shutdown_all

    @app.on_event("startup")
    async def _on_app_startup():
        """应用启动时统一启动所有已注册服务插件"""
        startup_all()

    @app.on_event("shutdown")
    async def _on_app_shutdown():
        """应用关闭时统一关闭所有已注册服务插件"""
        shutdown_all()

    logger.info("✅ 已注册服务插件生命周期钩子")
except ImportError as e:
    logger.warning(f"⚠️ 服务插件生命周期未接入: {e}")


# ==================== 文件日志收集器 ====================

setup_file_logging()
logger.info("Web服务器启动，文件日志收集器已初始化")


# ==================== WebSocket 实时推送 ====================

@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """前端事件推送 WebSocket 端点"""
    await websocket.accept()

    user_id = None

    try:
        init_data = await websocket.receive_json()
        if init_data.get('type') == 'init':
            token = init_data.get('token', '')
            user_id = _validate_ws_token(token)
            if not user_id:
                await websocket.send_json({'type': 'error', 'message': '认证失败'})
                await websocket.close(code=4001, reason='Auth failed')
                return
            await websocket.send_json({'type': 'connected', 'message': '连接成功'})
        else:
            await websocket.send_json({'type': 'error', 'message': '需要认证'})
            await websocket.close(code=4001, reason='No auth')
            return
    except Exception:
        await websocket.close(code=4000, reason='Invalid init')
        return

    await event_bus.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket连接异常: {e}")
    finally:
        await event_bus.disconnect(user_id, websocket)


def _validate_ws_token(token: str) -> Optional[str]:
    """验证 WebSocket 连接 token（使用 session cookie 值），返回 user_id"""
    if not token:
        return None
    from routers.deps import _get_session
    session = _get_session(token)
    if session and session.get('user_id'):
        return str(session['user_id'])
    return None


# ==================== 事件推送辅助函数 ====================

def broadcast_event(event_type: str, data: Any = None, user_id: Optional[str] = None):
    """同步方式广播事件（供非async上下文调用）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(event_bus.broadcast(event_type, data, user_id))
        else:
            asyncio.run(event_bus.broadcast(event_type, data, user_id))
    except RuntimeError:
        asyncio.run(event_bus.broadcast(event_type, data, user_id))


def notify_new_order(order_data: Dict[str, Any]):
    """通知新订单创建"""
    broadcast_event('new_order', {
        'order_id': order_data.get('order_id'),
        'item_title': order_data.get('item_title', ''),
        'status': order_data.get('status', 'pending_ship'),
        'created_at': order_data.get('created_at', '')
    })


def notify_order_status_changed(order_id: str, old_status: str, new_status: str):
    """通知订单状态变更"""
    broadcast_event('order_updated', {
        'order_id': order_id,
        'old_status': old_status,
        'new_status': new_status
    })


def notify_message_received(cookie_id: str, sender_id: str, content: str):
    """通知收到新消息"""
    broadcast_event('message_received', {
        'cookie_id': cookie_id,
        'sender_id': sender_id,
        'content_preview': content[:100] if content else '',
        'received_at': int(time.time() * 1000)
    })


def notify_account_status(cookie_id: str, status: str, message: str = ''):
    """通知账号状态变更"""
    broadcast_event('account_status', {
        'cookie_id': cookie_id,
        'status': status,
        'message': message
    })


def notify_delivery_completed(order_id: str, delivery_type: str, content: str):
    """通知发货完成"""
    broadcast_event('delivery_completed', {
        'order_id': order_id,
        'delivery_type': delivery_type,
        'content_preview': content[:100] if content else ''
    })


def notify_system_log(level: str, message: str, source: str = ''):
    """通知系统日志事件"""
    broadcast_event('system_log', {
        'level': level,
        'message': message[:200],
        'source': source
    })


# ==================== 请求日志中间件 ====================

@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()

    # 敏感路径不记录详细参数（避免泄露 token、密码等）
    path = request.url.path
    is_sensitive_path = any(p in path for p in ['/login', '/change-password', '/verify-captcha', '/send-verification-code'])
    if is_sensitive_path:
        logger.info(f"🌐 API请求: {request.method} {path} (敏感路径，参数已隐藏)")
    else:
        logger.info(f"🌐 API请求: {request.method} {path}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"❌ 未处理异常: {request.method} {path} - {type(e).__name__}: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请稍后重试"}
        )

    process_time = time.time() - start_time
    logger.info(f"✅ API响应: {request.method} {path} - {response.status_code} ({process_time:.3f}s)")

    return response


# ==================== 全局异常处理器 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """捕获所有未处理异常，返回通用错误信息"""
    logger.error(f"未处理异常: {request.method} {request.url.path} - {type(exc).__name__}: {exc}", exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )

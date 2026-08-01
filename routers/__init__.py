"""
routers package
================
聚合注册所有业务 router。

新增 router 流程：
1. 在 routers/ 下新建 xxx.py，定义 `router = APIRouter(prefix=..., tags=[...])`
2. 在下方 import 并加入 `routers` 列表
3. reply_server.py 调用 `register_routers(app)` 即可挂载全部

现有 reply_server.py 中的路由保持原样（向后兼容），
新增功能（搜索/批量/时间线/插件）走本目录的 router 模块。
"""
from fastapi import FastAPI

from . import search
from . import batch
from . import timeline
from . import plugins
from . import notifications
from . import system_settings
from . import default_replies
from . import orders
from . import webhook
from . import cookies
from . import cards
from . import delivery_rules
from . import keywords
from . import ai_reply
from . import user_settings
from . import items
from . import logs
from . import risk_control
from . import backup
from . import kb
from . import admin
from . import analytics
from . import services
from . import health
from . import xianyu_reply
from . import auth
from . import password_login
from . import face_verification
from . import qr_login
from . import frontend

# 聚合所有 router（顺序即注册顺序）
# 注意：带子路径的 /cookies/{cid}/xxx 必须在 /cookies/{cid} 之前注册，
# FastAPI 按声明顺序匹配路由，子路径在前可避免被通用路由吞掉。
# frontend.router 必须最后注册：其 catch-all /{path:path} 会吞掉所有未匹配的 GET 请求
routers = [
    search.router,
    batch.router,
    timeline.router,
    plugins.router,       # /api/plugins/* 服务插件
    notifications.router,
    system_settings.router,
    default_replies.router,
    cookies.router,        # /cookies/{cid}/xxx 子路径在前，/cookies/{cid} 在后；含 /cookie/{cid}/details
    cards.router,
    delivery_rules.router,
    keywords.router,       # /keywords-export|/keywords-with-* 与 /keywords/{cid} 首段不同，无冲突
    orders.router,         # /api/orders/{refresh|manual-ship|import} 静态路径在前，/api/orders/{order_id} 在后
    webhook.router,
    ai_reply.router,       # /ai-reply-settings 在前，/ai-reply-settings/{cookie_id} 在后
    user_settings.router,  # /user-settings 在前，/user-settings/{key} 在后
    items.router,          # /items/{search|get-all-from-account|batch} 等静态路径在前，/items/{cid} 在后
    logs.router,           # /logs/stats|/logs/clear 在前，/logs 在后；/admin/logs/export|/admin/log-files 在前
    risk_control.router,   # /risk-control-logs/{log_id} 在 /risk-control-logs 之后（不同方法不冲突）
    backup.router,         # /backup/export|/backup/import 静态路径；/admin/backup/{download|upload|list} 静态路径
    kb.router,             # /kb/scripts 在前，/kb/scripts/{script_id} 在后
    admin.router,          # /admin/users|/admin/stats|/admin/data/* 静态路径
    analytics.router,      # /api/stats|/analytics/orders|/analytics/orders/valid
    services.router,       # /api/services/{forbidden-check|product-dedup|extract-product|...}
    health.router,         # /health
    xianyu_reply.router,   # /xianyu/reply
    auth.router,           # /login|/verify|/logout|/change-*|/captcha|/geetest|/register|/send-*|/*-settings
    password_login.router, # /password-login|/password-login/check/{session_id}
    face_verification.router,  # /face-verification/screenshot/{account_id}
    qr_login.router,       # /qr-login/{generate|check/{sid}|refresh-cookies|reset-cooldown/{cid}|cooldown-status/{cid}}
    frontend.router,       # / + /login.html + /login + /init + /register.html + catch-all /{path:path}  ← 必须最后注册
]




def register_routers(app: FastAPI) -> None:
    """将所有业务 router 注册到 FastAPI app"""
    for r in routers:
        app.include_router(r)


__all__ = ["register_routers", "routers"]

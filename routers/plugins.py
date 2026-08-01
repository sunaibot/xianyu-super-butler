"""
routers/plugins.py
==================
服务插件 API router。

GET  /api/plugins          列出所有已注册插件及健康状态
GET  /api/plugins/{name}    获取单个插件详情
POST /api/plugins/{name}/call  调用插件动作

通过 services.registry 动态发现，无需为每个插件写独立路由。
"""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from loguru import logger

from .deps import require_auth, require_admin, client_error, server_error
from services.registry import list_service_info, get_service

router = APIRouter(prefix="/api/plugins", tags=["服务插件"])


class PluginCallRequest(BaseModel):
    action: str = Field(..., description="动作名")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="动作参数")


@router.get("")
async def list_plugins(_: dict = Depends(require_auth)):
    """列出所有已注册服务插件"""
    return {"success": True, "data": list_service_info()}


@router.get("/{name}")
async def get_plugin(name: str, _: dict = Depends(require_auth)):
    """获取单个插件详情"""
    svc = get_service(name)
    if not svc:
        return {"success": False, "message": f"插件 {name} 不存在"}
    return {"success": True, "data": svc.health()}


@router.post("/{name}/call")
async def call_plugin(name: str, req: PluginCallRequest, user: dict = Depends(require_auth)):
    """调用插件动作（统一入口）"""
    svc = get_service(name)
    if not svc:
        return {"success": False, "message": f"插件 {name} 不存在"}
    try:
        result = svc.call(req.action, req.payload)
        logger.info(f"[plugin] 用户 {user.get('username')} 调用 {name}.{req.action}")
        return {"success": True, "data": result}
    except NotImplementedError as e:
        raise client_error(e, "插件调用")
    except Exception as e:
        raise server_error(e, "插件调用")

"""
services/registry.py
====================
服务插件注册表。

启动时统一注册所有 ServiceBase 子类实例，
供 /api/plugins 路由动态发现与调用。

使用方式：
    from services.registry import register_service, get_service, list_services
    from services.xxx import XxxService

    register_service(XxxService())

    svc = get_service('xxx')
    svc.call('check', {...})
"""
from typing import Dict, List, Optional, Any
from loguru import logger

from .base import ServiceBase

# 全局注册表：name → 实例
_registry: Dict[str, ServiceBase] = {}


def register_service(service: ServiceBase) -> None:
    """注册服务插件实例"""
    if not isinstance(service, ServiceBase):
        logger.warning(f"[registry] {service} 不是 ServiceBase 子类，跳过注册")
        return
    if service.name in _registry:
        logger.debug(f"[registry] 服务 {service.name} 已存在，覆盖注册")
    _registry[service.name] = service
    logger.info(f"[registry] 已注册服务: {service.name} ({service.display_name})")


def get_service(name: str) -> Optional[ServiceBase]:
    """按名称获取服务实例"""
    return _registry.get(name)


def list_services() -> List[ServiceBase]:
    """获取所有已注册服务"""
    return list(_registry.values())


def list_service_info() -> List[Dict[str, Any]]:
    """获取所有服务的健康信息"""
    infos = []
    for svc in _registry.values():
        try:
            infos.append(svc.health())
        except Exception as e:
            logger.warning(f"[registry] 服务 {svc.name} 健康检查失败: {e}")
            infos.append({
                "name": svc.name,
                "display_name": getattr(svc, "display_name", svc.name),
                "healthy": False,
                "error": str(e)[:100],
            })
    return infos


def startup_all() -> None:
    """启动所有已注册服务（统一调用）"""
    for svc in _registry.values():
        try:
            svc.startup()
            logger.info(f"[registry] 服务 {svc.name} 启动成功")
        except Exception as e:
            logger.error(f"[registry] 服务 {svc.name} 启动失败: {e}", exc_info=True)


def shutdown_all() -> None:
    """关闭所有已注册服务（统一调用）"""
    for svc in _registry.values():
        try:
            svc.shutdown()
        except Exception as e:
            logger.warning(f"[registry] 服务 {svc.name} 关闭失败: {e}")

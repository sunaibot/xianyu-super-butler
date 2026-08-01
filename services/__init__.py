"""
services 包
================
从 XY-Agent 迁移的实用服务模块。

所有服务插件继承 ServiceBase 并通过 registry 注册，
供 /api/plugins 路由动态发现与调用。
"""
from .registry import (
    register_service,
    get_service,
    list_services,
    list_service_info,
    startup_all,
    shutdown_all,
)

# 导入各服务模块（触发模块级单例创建），并注册到 registry。
# 顺序：browser_service 必须在 product_extractor / product_publisher 之前导入。
from .forbidden_words import forbidden_checker
from .product_dedup import product_dedup
from .browser_service import browser_service
from .product_extractor import product_extractor
from .product_publisher import product_publisher
from .performance_monitor import performance_monitor

register_service(forbidden_checker)
register_service(product_dedup)
register_service(browser_service)
register_service(product_extractor)
register_service(product_publisher)
register_service(performance_monitor)

__all__ = [
    "register_service",
    "get_service",
    "list_services",
    "list_service_info",
    "startup_all",
    "shutdown_all",
]

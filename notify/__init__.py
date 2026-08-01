"""通知模块：7 个渠道 + 入口分发。

对外暴露 Notifier，负责按账号加载渠道配置并多渠道分发。
防重复/冷却逻辑由调用方管理（如 XianyuLive.send_notification）。
"""
from .dispatcher import Notifier

__all__ = ["Notifier"]

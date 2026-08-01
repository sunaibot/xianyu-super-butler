"""
通知分发器

按账号加载通知渠道配置，实例化对应 Channel 并调用 send。

设计要点：
- Notifier 不持有防重复/冷却逻辑（由调用方管理，如 XianyuLive.send_notification）
- Notifier 只负责"按 channel_type 实例化 Channel + 调用 send + 异常隔离"
- channel_type → Channel 类的注册表支持扩展新渠道
- 单条渠道失败不影响其他渠道
"""
import json
from typing import Dict, List, Optional, Type

from loguru import logger

from .channels import (
    NotificationChannel,
    DingTalkChannel,
    FeishuChannel,
    BarkChannel,
    EmailChannel,
    WebhookChannel,
    WechatChannel,
    TelegramChannel,
)


# channel_type 字符串 → Channel 类的注册表
# 支持多种别名（如 ding_talk / dingtalk）
_CHANNEL_REGISTRY: Dict[str, Type[NotificationChannel]] = {
    "ding_talk": DingTalkChannel,
    "dingtalk": DingTalkChannel,
    "feishu": FeishuChannel,
    "lark": FeishuChannel,
    "bark": BarkChannel,
    "email": EmailChannel,
    "webhook": WebhookChannel,
    "wechat": WechatChannel,
    "telegram": TelegramChannel,
}


def register_channel(channel_type: str, channel_cls: Type[NotificationChannel]) -> None:
    """注册新的通知渠道类型（插件化扩展点）"""
    _CHANNEL_REGISTRY[channel_type.lower()] = channel_cls


def get_channel_class(channel_type: str) -> Optional[Type[NotificationChannel]]:
    """按类型获取 Channel 类"""
    return _CHANNEL_REGISTRY.get((channel_type or "").lower())


def list_supported_channel_types() -> List[str]:
    """列出所有支持的渠道类型"""
    return sorted(_CHANNEL_REGISTRY.keys())


def _parse_channel_config(config) -> dict:
    """解析渠道配置（接受 JSON 字符串或 dict）"""
    if not config:
        return {}
    if isinstance(config, dict):
        return config
    if isinstance(config, str):
        try:
            return json.loads(config)
        except Exception as e:
            logger.warning(f"通知渠道配置 JSON 解析失败: {e}")
            return {}
    return {}


class Notifier:
    """
    通知分发器

    使用方式：
        notifier = Notifier()
        ok = await notifier.dispatch(notifications_config_list, message)
    """

    def __init__(self):
        # Channel 实例缓存（channel_type → 实例），无状态可复用
        self._channel_cache: Dict[str, NotificationChannel] = {}

    def _get_channel(self, channel_type: str) -> Optional[NotificationChannel]:
        """按类型获取 Channel 实例（缓存复用）"""
        key = (channel_type or "").lower()
        if key in self._channel_cache:
            return self._channel_cache[key]
        cls = get_channel_class(key)
        if cls is None:
            return None
        instance = cls()
        self._channel_cache[key] = instance
        return instance

    async def dispatch(self, notifications: List[dict], message: str, **kwargs) -> Dict[str, bool]:
        """
        分发通知到多个渠道配置

        Args:
            notifications: 账号的通知配置列表，每项含
                channel_type / channel_config / channel_name / enabled
            message: 通知正文
            **kwargs: 透传给 Channel.send 的额外参数

        Returns:
            { channel_name: success_bool } 各渠道发送结果
        """
        results: Dict[str, bool] = {}

        if not notifications:
            return results

        for notification in notifications:
            channel_name = notification.get("channel_name", "Unknown")
            if not notification.get("enabled", True):
                logger.info(f"📱 通知渠道 {channel_name} 已禁用，跳过")
                results[channel_name] = False
                continue

            channel_type = notification.get("channel_type")
            channel_config = notification.get("channel_config")

            try:
                config_data = _parse_channel_config(channel_config)
                channel = self._get_channel(channel_type)
                if channel is None:
                    logger.warning(f"📱 不支持的通知渠道类型: {channel_type} (渠道: {channel_name})")
                    results[channel_name] = False
                    continue

                logger.info(f"📱 开始发送 {channel_type} 通知 (渠道: {channel_name})")
                ok = await channel.send(config_data, message, **kwargs)
                results[channel_name] = bool(ok)
                if ok:
                    logger.info(f"📱 ✅ {channel_name} 通知发送成功")
                else:
                    logger.warning(f"📱 ❌ {channel_name} 通知发送失败")
            except Exception as e:
                logger.error(f"📱 发送通知失败 (渠道 {channel_name}): {e}")
                results[channel_name] = False

        return results

    async def dispatch_for_account(self, cookie_id: str, message: str, **kwargs) -> Dict[str, bool]:
        """
        按账号 ID 加载通知配置并分发（便捷方法）

        Args:
            cookie_id: 账号 Cookie ID
            message: 通知正文
        """
        try:
            from db_manager import db_manager
            notifications = db_manager.get_account_notifications(cookie_id)
        except Exception as e:
            logger.error(f"📱 加载账号 {cookie_id} 通知配置失败: {e}")
            return {}

        if not notifications:
            logger.info(f"📱 账号 {cookie_id} 未配置消息通知")
            return {}

        return await self.dispatch(notifications, message, **kwargs)

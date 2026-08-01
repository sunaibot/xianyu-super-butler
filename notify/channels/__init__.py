"""通知渠道包：每个渠道一个类，继承 NotificationChannel。"""
from .base import NotificationChannel, safe_str
from .dingtalk import DingTalkChannel
from .feishu import FeishuChannel
from .bark import BarkChannel
from .email_channel import EmailChannel
from .webhook import WebhookChannel
from .wechat import WechatChannel
from .telegram import TelegramChannel

__all__ = [
    "NotificationChannel",
    "safe_str",
    "DingTalkChannel",
    "FeishuChannel",
    "BarkChannel",
    "EmailChannel",
    "WebhookChannel",
    "WechatChannel",
    "TelegramChannel",
]

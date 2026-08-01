"""微信通知渠道"""
import aiohttp
from loguru import logger
from .base import NotificationChannel, safe_str


class WechatChannel(NotificationChannel):
    channel_type = "wechat"

    async def send(self, config_data: dict, message: str, **kwargs) -> bool:
        """发送微信通知"""
        try:
            # 解析配置
            webhook_url = config_data.get('webhook_url', '')

            if not webhook_url:
                logger.warning("微信通知配置为空")
                return False

            data = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"微信通知发送成功")
                    else:
                        logger.warning(f"微信通知发送失败: {response.status}")
            return True

        except Exception as e:
            logger.error(f"发送微信通知异常: {safe_str(e)}")
            return False

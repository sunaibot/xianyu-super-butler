"""Telegram通知渠道"""
import aiohttp
from loguru import logger
from .base import NotificationChannel, safe_str


class TelegramChannel(NotificationChannel):
    channel_type = "telegram"

    async def send(self, config_data: dict, message: str, **kwargs) -> bool:
        """发送Telegram通知"""
        try:
            # 解析配置
            bot_token = config_data.get('bot_token', '')
            chat_id = config_data.get('chat_id', '')

            if not all([bot_token, chat_id]):
                logger.warning("Telegram通知配置不完整")
                return False

            # 构建API URL
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Telegram通知发送成功")
                    else:
                        logger.warning(f"Telegram通知发送失败: {response.status}")
            return True

        except Exception as e:
            logger.error(f"发送Telegram通知异常: {safe_str(e)}")
            return False

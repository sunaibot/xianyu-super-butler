"""飞书通知渠道"""
import time
import hmac
import hashlib
import base64
import json
import aiohttp
from loguru import logger
from .base import NotificationChannel, safe_str


class FeishuChannel(NotificationChannel):
    channel_type = "feishu"

    async def send(self, config_data: dict, message: str, **kwargs) -> bool:
        """发送飞书通知"""
        try:
            logger.info(f"📱 飞书通知 - 开始处理配置数据: {config_data}")

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')
            secret = config_data.get('secret', '')

            logger.info(f"📱 飞书通知 - Webhook URL: {webhook_url[:50]}...")
            logger.info(f"📱 飞书通知 - 是否有签名密钥: {'是' if secret else '否'}")

            if not webhook_url:
                logger.warning("📱 飞书通知 - Webhook URL配置为空，无法发送通知")
                return False

            # 如果有加签密钥，生成签名
            timestamp = str(int(time.time()))
            sign = ""

            if secret:
                string_to_sign = f'{timestamp}\n{secret}'
                hmac_code = hmac.new(
                    string_to_sign.encode('utf-8'),
                    ''.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                sign = base64.b64encode(hmac_code).decode('utf-8')
                logger.info(f"📱 飞书通知 - 已生成签名")

            # 构建请求数据
            data = {
                "msg_type": "text",
                "content": {
                    "text": message
                },
                "timestamp": timestamp
            }

            # 如果有签名，添加到请求数据中
            if sign:
                data["sign"] = sign

            logger.info(f"📱 飞书通知 - 请求数据构建完成")

            # 发送POST请求
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    logger.info(f"📱 飞书通知 - 响应状态: {response.status}")
                    logger.info(f"📱 飞书通知 - 响应内容: {response_text}")

                    if response.status == 200:
                        try:
                            response_json = json.loads(response_text)
                            if response_json.get('code') == 0:
                                logger.info(f"📱 飞书通知发送成功")
                            else:
                                logger.warning(f"📱 飞书通知发送失败: {response_json.get('msg', '未知错误')}")
                        except json.JSONDecodeError:
                            logger.info(f"📱 飞书通知发送成功（响应格式异常）")
                    else:
                        logger.warning(f"📱 飞书通知发送失败: HTTP {response.status}, 响应: {response_text}")
            return True

        except Exception as e:
            logger.error(f"📱 发送飞书通知异常: {safe_str(e)}")
            import traceback
            logger.error(f"📱 飞书通知异常详情: {traceback.format_exc()}")
            return False

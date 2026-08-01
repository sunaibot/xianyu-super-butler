"""Bark通知渠道"""
import json
import aiohttp
from loguru import logger
from .base import NotificationChannel, safe_str


class BarkChannel(NotificationChannel):
    channel_type = "bark"

    async def send(self, config_data: dict, message: str, **kwargs) -> bool:
        """发送Bark通知"""
        try:
            logger.info(f"📱 Bark通知 - 开始处理配置数据: {config_data}")

            # 解析配置
            server_url = config_data.get('server_url', 'https://api.day.app').rstrip('/')
            device_key = config_data.get('device_key', '')
            title = config_data.get('title', '闲鱼自动回复通知')
            sound = config_data.get('sound', 'default')
            icon = config_data.get('icon', '')
            group = config_data.get('group', 'xianyu')
            url = config_data.get('url', '')

            logger.info(f"📱 Bark通知 - 服务器: {server_url}")
            logger.info(f"📱 Bark通知 - 设备密钥: {device_key[:10]}..." if device_key else "📱 Bark通知 - 设备密钥: 未设置")
            logger.info(f"📱 Bark通知 - 标题: {title}")

            if not device_key:
                logger.warning("📱 Bark通知 - 设备密钥配置为空，无法发送通知")
                return False

            # 构建请求URL和数据
            # Bark支持两种方式：URL路径方式和POST JSON方式
            # 这里使用POST JSON方式，更灵活且支持更多参数

            api_url = f"{server_url}/push"

            # 构建请求数据
            data = {
                "device_key": device_key,
                "title": title,
                "body": message,
                "sound": sound,
                "group": group
            }

            # 可选参数
            if icon:
                data["icon"] = icon
            if url:
                data["url"] = url

            logger.info(f"📱 Bark通知 - API地址: {api_url}")
            logger.info(f"📱 Bark通知 - 请求数据构建完成")

            # 发送POST请求
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    logger.info(f"📱 Bark通知 - 响应状态: {response.status}")
                    logger.info(f"📱 Bark通知 - 响应内容: {response_text}")

                    if response.status == 200:
                        try:
                            response_json = json.loads(response_text)
                            if response_json.get('code') == 200:
                                logger.info(f"📱 Bark通知发送成功")
                            else:
                                logger.warning(f"📱 Bark通知发送失败: {response_json.get('message', '未知错误')}")
                        except json.JSONDecodeError:
                            # 某些Bark服务器可能返回纯文本
                            if 'success' in response_text.lower() or 'ok' in response_text.lower():
                                logger.info(f"📱 Bark通知发送成功")
                            else:
                                logger.warning(f"📱 Bark通知响应格式异常: {response_text}")
                    else:
                        logger.warning(f"📱 Bark通知发送失败: HTTP {response.status}, 响应: {response_text}")
            return True

        except Exception as e:
            logger.error(f"📱 发送Bark通知异常: {safe_str(e)}")
            import traceback
            logger.error(f"📱 Bark通知异常详情: {traceback.format_exc()}")
            return False

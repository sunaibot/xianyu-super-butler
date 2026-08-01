"""通知渠道基类"""


def safe_str(e) -> str:
    """安全地将异常转换为字符串"""
    try:
        return str(e)
    except Exception:
        try:
            return repr(e)
        except Exception:
            return "未知错误"


class NotificationChannel:
    """通知渠道基类"""
    channel_type: str = ""

    async def send(self, config: dict, message: str, **kwargs) -> bool:
        """发送通知，返回是否成功"""
        raise NotImplementedError

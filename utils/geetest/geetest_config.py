"""
极验验证码配置

说明：
- captcha_id 和 private_key 需要从极验官网申请
- 当前使用的是示例配置，生产环境请替换为自己的密钥
- 环境变量统一由 config.py 管理，此处仅做聚合
"""
from config import GEETEST_CAPTCHA_ID, GEETEST_PRIVATE_KEY, GEETEST_USER_ID


class GeetestConfig:
    """极验验证码配置类"""

    # 极验分配的captcha_id（来自 config.py 集中管理）
    CAPTCHA_ID = GEETEST_CAPTCHA_ID

    # 极验分配的私钥（来自 config.py 集中管理）
    PRIVATE_KEY = GEETEST_PRIVATE_KEY

    # 用户标识（可选）
    USER_ID = GEETEST_USER_ID

    # 客户端类型：web, h5, native, unknown
    CLIENT_TYPE = "web"

    # API地址
    API_URL = "http://api.geetest.com"
    REGISTER_URL = "/register.php"
    VALIDATE_URL = "/validate.php"

    # 请求超时时间（秒）
    TIMEOUT = 5

    # SDK版本
    VERSION = "python-fastapi:1.0.0"

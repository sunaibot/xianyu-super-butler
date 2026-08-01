"""
加密 API 调用基类

抽取 secure_confirm_decrypted.py 与 secure_freeshipping_decrypted.py 的公共逻辑：
- _safe_str / token 提取 / sign 生成 / set-cookie 解析与回写数据库 / 重试骨架

子类只需提供：
- API_NAME（mtop 接口名）
- API_URL（完整 URL）
- build_data_val(*args, **kwargs) 构造 data_val 字符串
- 日志动作名（用于日志可读性）
"""

import asyncio
import time
from loguru import logger
from utils.xianyu_utils import trans_cookies, generate_sign


class BaseSecureApi:
    """加密 API 调用基类，封装 token/sign/cookie/重试骨架"""

    # 子类必须覆盖
    API_NAME: str = ""
    API_URL: str = ""
    ACTION_LABEL: str = "加密API"  # 日志中显示的动作名，如"自动确认发货"/"自动免拼发货"

    def __init__(self, session, cookies_str, cookie_id, main_instance=None):
        self.session = session
        self.cookies_str = cookies_str
        self.cookie_id = cookie_id
        self.main_instance = main_instance
        self.cookies = trans_cookies(cookies_str) if cookies_str else {}

        # Token 相关属性
        self.current_token = None
        self.last_token_refresh_time = 0
        self.token_refresh_interval = 3600

    # -------- 公共方法 --------

    def _safe_str(self, obj) -> str:
        """安全转换为字符串"""
        try:
            return str(obj)
        except Exception:
            return "无法转换的对象"

    async def _update_config_cookies(self) -> None:
        """更新数据库中的 Cookie（统一走 update_cookie_account_info）"""
        try:
            from db_manager import db_manager
            db_manager.update_cookie_account_info(self.cookie_id, cookie_value=self.cookies_str)
            logger.debug(f"【{self.cookie_id}】已更新数据库中的Cookie")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】更新数据库Cookie失败: {self._safe_str(e)}")

    def _build_params(self, data_val: str) -> dict:
        """构造请求参数并生成 sign"""
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': self.API_NAME,
            'sessionOption': 'AutoLoginOnly',
        }

        token = (trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0]
                 if trans_cookies(self.cookies_str).get('_m_h5_tk') else '')
        if token:
            logger.info(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        params['sign'] = generate_sign(params['t'], token, data_val)
        return params

    def _extract_set_cookies(self, response) -> dict:
        """从响应头解析 set-cookie 为 dict"""
        new_cookies = {}
        for cookie in response.headers.getall('set-cookie', []):
            if '=' in cookie:
                name, value = cookie.split(';')[0].split('=', 1)
                new_cookies[name.strip()] = value.strip()
        return new_cookies

    async def _apply_set_cookies(self, response) -> None:
        """若响应含 set-cookie，更新本地 cookies 并回写数据库"""
        if 'set-cookie' not in response.headers:
            return
        new_cookies = self._extract_set_cookies(response)
        if not new_cookies:
            return
        self.cookies.update(new_cookies)
        self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
        await self._update_config_cookies()
        logger.debug("已更新Cookie到数据库")

    # -------- 子类覆盖 --------

    def build_data_val(self, *args, **kwargs) -> str:
        """子类构造 data_val 字符串"""
        raise NotImplementedError

    def describe(self, *args, **kwargs) -> str:
        """子类返回用于日志的参数描述"""
        return ""

    # -------- 主流程骨架 --------

    async def execute(self, *args, retry_count: int = 0, **kwargs):
        """执行加密 API 调用（重试骨架）"""
        action = self.ACTION_LABEL
        if retry_count >= 4:
            logger.error(f"{action}失败，重试次数过多")
            return {"error": f"{action}失败，重试次数过多"}

        if not self.session:
            raise Exception("Session未创建")

        data_val = self.build_data_val(*args, **kwargs)
        params = self._build_params(data_val)
        data = {'data': data_val}

        desc = self.describe(*args, **kwargs)
        if desc:
            logger.info(f"【{self.cookie_id}】{action}请求参数: {desc}")

        order_id = kwargs.get('order_id') or (args[0] if args else '')
        try:
            logger.info(f"【{self.cookie_id}】开始{action}，订单ID: {order_id}")
            async with self.session.post(self.API_URL, params=params, data=data) as response:
                res_json = await response.json()
                await self._apply_set_cookies(response)

                logger.info(f"【{self.cookie_id}】{action}响应: {res_json}")

                if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                    logger.info(f"【{self.cookie_id}】✅ {action}成功，订单ID: {order_id}")
                    return {"success": True, "order_id": order_id}

                error_msg = res_json.get('ret', ['未知错误'])[0] if res_json.get('ret') else '未知错误'
                logger.warning(f"【{self.cookie_id}】❌ {action}失败: {error_msg}")
                return await self.execute(*args, retry_count=retry_count + 1, **kwargs)

        except Exception as e:
            logger.error(f"【{self.cookie_id}】{action}API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)
            if retry_count < 2:
                logger.info(f"【{self.cookie_id}】网络异常，准备重试...")
                return await self.execute(*args, retry_count=retry_count + 1, **kwargs)
            return {"error": f"网络异常: {self._safe_str(e)}", "order_id": order_id}

"""自动确认发货 - 加密版本（基于 BaseSecureApi）"""

from secure_base_api import BaseSecureApi
from loguru import logger


class SecureConfirm(BaseSecureApi):
    API_NAME = 'mtop.taobao.idle.logistic.consign.dummy'
    API_URL = 'https://h5api.m.goofish.com/h5/mtop.taobao.idle.logistic.consign.dummy/1.0/'
    ACTION_LABEL = '自动确认发货'

    def __init__(self, session, cookies_str, cookie_id, main_instance=None):
        super().__init__(session, cookies_str, cookie_id, main_instance)
        self._current_item_id = None

    async def _get_real_item_id(self):
        """从数据库中获取一个真实的商品ID"""
        try:
            from db_manager import db_manager
            items = db_manager.get_items_by_cookie(self.cookie_id)
            if items:
                item_id = items[0].get('item_id')
                if item_id:
                    logger.debug(f"【{self.cookie_id}】获取到真实商品ID: {item_id}")
                    return item_id
            all_items = db_manager.get_all_items()
            if all_items:
                item_id = all_items[0].get('item_id')
                if item_id:
                    logger.debug(f"【{self.cookie_id}】使用其他账号的商品ID: {item_id}")
                    return item_id
            logger.warning(f"【{self.cookie_id}】数据库中没有找到任何商品ID")
            return None
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取真实商品ID失败: {self._safe_str(e)}")
            return None

    def build_data_val(self, order_id, item_id=None, **kwargs) -> str:
        return '{"orderId":"' + order_id + '", "tradeText":"","picList":[],"newUnconsign":true}'

    def describe(self, order_id, item_id=None, **kwargs) -> str:
        return f"order_id: {order_id}, item_id: {item_id}"

    # 对外兼容旧接口
    async def auto_confirm(self, order_id, item_id=None, retry_count=0):
        if item_id:
            self._current_item_id = item_id
            logger.debug(f"【{self.cookie_id}】设置当前商品ID: {item_id}")
        return await self.execute(order_id, item_id, retry_count=retry_count)

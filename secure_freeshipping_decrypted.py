"""自动免拼发货 - 加密版本（基于 BaseSecureApi）"""

from secure_base_api import BaseSecureApi


class SecureFreeshipping(BaseSecureApi):
    API_NAME = 'mtop.idle.groupon.activity.seller.freeshipping'
    API_URL = 'https://h5api.m.goofish.com/h5/mtop.idle.groupon.activity.seller.freeshipping/1.0/'
    ACTION_LABEL = '自动免拼发货'

    def build_data_val(self, order_id, item_id, buyer_id, **kwargs) -> str:
        return '{"bizOrderId":"' + order_id + '", "itemId":' + item_id + ',"buyerId":' + buyer_id + '}'

    def describe(self, order_id, item_id, buyer_id, **kwargs) -> str:
        return f"data_val = {self.build_data_val(order_id, item_id, buyer_id)}, 参数详情 - order_id: {order_id}, item_id: {item_id}, buyer_id: {buyer_id}"

    # 对外兼容旧接口
    async def auto_freeshipping(self, order_id, item_id, buyer_id, retry_count=0):
        return await self.execute(order_id, item_id, buyer_id, retry_count=retry_count)

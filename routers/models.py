"""
routers/models.py
=================
跨 router 共享的 Pydantic 模型。

从 reply_server.py 抽取，供 reply_server.py 与各 router 模块复用，
避免循环导入（router 不再 import reply_server.py）。

设计原则：纯数据契约，无业务逻辑，无 FastAPI 依赖。
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ---------- 默认回复 ----------
class DefaultReplyIn(BaseModel):
    enabled: bool
    reply_content: Optional[str] = None
    reply_image_url: Optional[str] = None
    reply_once: bool = False


# ---------- 通知渠道 ----------
class NotificationChannelIn(BaseModel):
    name: str
    type: str = "qq"
    config: str


class NotificationChannelUpdate(BaseModel):
    name: str
    config: str
    enabled: bool = True


# ---------- 消息通知 ----------
class MessageNotificationIn(BaseModel):
    channel_id: int
    enabled: bool = True


# ---------- 系统设置 ----------
class SystemSettingIn(BaseModel):
    value: str
    description: Optional[str] = None


class SystemSettingCreateIn(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


# ---------- Cookie / 账号管理 ----------
class CookieIn(BaseModel):
    id: str
    value: str


class CookieStatusIn(BaseModel):
    enabled: bool


class AccountLoginInfoUpdate(BaseModel):
    """账号登录信息更新模型"""
    username: Optional[str] = None
    login_password: Optional[str] = None
    show_browser: Optional[bool] = None


class AutoConfirmUpdate(BaseModel):
    auto_confirm: bool


class RemarkUpdate(BaseModel):
    remark: str


class PauseDurationUpdate(BaseModel):
    pause_duration: int


# ---------- 关键字 ----------
class KeywordIn(BaseModel):
    keywords: Dict[str, str]  # key -> reply


class KeywordWithItemIdIn(BaseModel):
    keywords: List[Dict[str, Any]]  # [{"keyword": str, "reply": str, "item_id": str}]


# ---------- AI 回复设置 ----------
class AIReplySettings(BaseModel):
    ai_enabled: bool
    model_name: str = "qwen-plus"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_discount_percent: int = 10
    max_discount_amount: int = 100
    max_bargain_rounds: int = 3
    custom_prompts: str = ""


class AIReplyTestIn(BaseModel):
    """AI 回复测试请求体"""
    message: str = "你好"
    item_title: str = "测试商品"
    item_price: float = 100
    item_desc: str = "这是一个测试商品"


# ---------- 用户设置 ----------
class UserSettingUpdate(BaseModel):
    """用户设置更新模型"""
    value: str
    description: str = ""


# ---------- 商品管理 ----------
class CreateItem(BaseModel):
    item_id: str
    item_title: str = ''
    item_price: str = ''
    item_image: str = ''
    is_multi_spec: bool = False
    is_multi_qty_ship: bool = False


class ItemDetailUpdate(BaseModel):
    item_detail: str


class ItemSearchRequest(BaseModel):
    keyword: str
    page: int = 1
    page_size: int = 20


class ItemSearchMultipleRequest(BaseModel):
    keyword: str
    total_pages: int = 1


class ItemToDelete(BaseModel):
    cookie_id: str
    item_id: str


class BatchDeleteItemsRequest(BaseModel):
    """批量删除商品请求（/items/batch）"""
    items: List[ItemToDelete]


class BatchDeleteItemRepliesRequest(BaseModel):
    """批量删除商品回复请求（/item-reply/batch）"""
    items: List[ItemToDelete]


class ItemReplyUpdate(BaseModel):
    reply_content: str


class MultiSpecUpdate(BaseModel):
    is_multi_spec: bool


class MultiQuantityDeliveryUpdate(BaseModel):
    multi_quantity_delivery: bool


class GetAllFromAccountRequest(BaseModel):
    cookie_id: str


class GetByPageRequest(BaseModel):
    cookie_id: str
    page_number: int = 1
    page_size: int = 20


# ---------- 知识库 ----------
class KBScriptCreate(BaseModel):
    user_question: str
    answer: str
    intent_l1: str = ""
    intent_l2: str = ""


class KBScriptUpdate(BaseModel):
    user_question: str
    answer: str
    intent_l1: str = ""
    intent_l2: str = ""


class KBSearchIn(BaseModel):
    query: str = ""
    n_results: int = 3


class KBImportIn(BaseModel):
    csv_content: str = ""


__all__ = [
    "DefaultReplyIn",
    "NotificationChannelIn",
    "NotificationChannelUpdate",
    "MessageNotificationIn",
    "SystemSettingIn",
    "SystemSettingCreateIn",
    "CookieIn",
    "CookieStatusIn",
    "AccountLoginInfoUpdate",
    "AutoConfirmUpdate",
    "RemarkUpdate",
    "PauseDurationUpdate",
    "KeywordIn",
    "KeywordWithItemIdIn",
    "AIReplySettings",
    "AIReplyTestIn",
    "UserSettingUpdate",
    "CreateItem",
    "ItemDetailUpdate",
    "ItemSearchRequest",
    "ItemSearchMultipleRequest",
    "ItemToDelete",
    "BatchDeleteItemsRequest",
    "BatchDeleteItemRepliesRequest",
    "ItemReplyUpdate",
    "MultiSpecUpdate",
    "MultiQuantityDeliveryUpdate",
    "GetAllFromAccountRequest",
    "GetByPageRequest",
    "KBScriptCreate",
    "KBScriptUpdate",
    "KBSearchIn",
    "KBImportIn",
]

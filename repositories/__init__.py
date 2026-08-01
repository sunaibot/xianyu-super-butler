"""
repositories package
====================
数据库仓储层。

DBManager 方法渐进迁移到此：各 repo 继承 BaseRepo，按表组织方法。
DBManager 对应方法改为委托：return self.cookie_repo.save_cookie(...)
最终 DBManager 仅作聚合入口，保持向后兼容。

已迁移：
- cookie_repo.py：Cookie 域（save/delete/get/details/update_* + cookie_status）
- order_repo.py：订单域（insert_or_update_order / get / delete / 批量查询 + update_order_address + 分析统计 + item_title 映射）
- user_repo.py：用户域（create/get/verify_password/update_password/delete_user_and_data）
- card_repo.py：卡券域（create/get_all/get_by_id/update/update_image_url/delete + consume_batch_data）
- delivery_rule_repo.py：发货规则域（CRUD + 关键字匹配 + 多规格优先匹配 + 发货次数自增）
- keyword_repo.py：关键字域（save/get/check_duplicate/save_image/delete_by_index + Excel 导入导出支撑）
- ai_reply_repo.py：AI 回复设置域（save/get/get_all + system_settings 兜底）
- user_settings_repo.py：用户设置域（get_all/get_one/set）
- item_repo.py：商品域（item_info + item_replay，含 get_all_item_titles 从 order_repo 迁入）
- risk_control_repo.py：风控日志域（add/update + get_risk_control_logs / count / delete）
- default_reply_repo.py：默认回复域（default_replies / default_reply_records + find_chat_id_by_buyer）
- notification_repo.py：通知渠道与消息通知域（notification_channels / message_notifications）
- system_settings_repo.py：系统设置域（system_settings 表）
- verification_repo.py：验证码域（captcha_codes / email_verifications）
- admin_repo.py：管理员通用表操作（get_table_data / delete_table_record / clear_table_data，PRAGMA 主键探测）
"""
from .base import BaseRepo
from .cookie_repo import CookieRepo, cookie_repo
from .order_repo import OrderRepo, order_repo
from .user_repo import UserRepo, user_repo
from .card_repo import CardRepo, card_repo
from .delivery_rule_repo import DeliveryRuleRepo, delivery_rule_repo
from .keyword_repo import KeywordRepo, keyword_repo
from .ai_reply_repo import AIReplyRepo, ai_reply_repo
from .user_settings_repo import UserSettingsRepo, user_settings_repo
from .item_repo import ItemRepo, item_repo
from .risk_control_repo import RiskControlRepo, risk_control_repo
from .default_reply_repo import DefaultReplyRepo, default_reply_repo
from .notification_repo import NotificationRepo, notification_repo
from .system_settings_repo import SystemSettingsRepo, system_settings_repo
from .verification_repo import VerificationRepo, verification_repo
from .admin_repo import AdminRepo, admin_repo

__all__ = [
    "BaseRepo",
    "CookieRepo", "cookie_repo",
    "OrderRepo", "order_repo",
    "UserRepo", "user_repo",
    "CardRepo", "card_repo",
    "DeliveryRuleRepo", "delivery_rule_repo",
    "KeywordRepo", "keyword_repo",
    "AIReplyRepo", "ai_reply_repo",
    "UserSettingsRepo", "user_settings_repo",
    "ItemRepo", "item_repo",
    "RiskControlRepo", "risk_control_repo",
    "DefaultReplyRepo", "default_reply_repo",
    "NotificationRepo", "notification_repo",
    "SystemSettingsRepo", "system_settings_repo",
    "VerificationRepo", "verification_repo",
    "AdminRepo", "admin_repo",
]

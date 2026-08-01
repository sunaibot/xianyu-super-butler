"""
repositories/default_reply_repo.py
==================================
默认回复数据访问层（default_replies / default_reply_records 表）。

从 db_manager.DBManager 迁移而来：
- save_default_reply / get_default_reply / get_all_default_replies
- add_default_reply_record / has_default_reply_record / clear_default_reply_records
- find_chat_id_by_buyer（依赖 ai_conversations 表）
- delete_default_reply / update_default_reply_image_url

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, Optional

from loguru import logger

from .base import BaseRepo


class DefaultReplyRepo(BaseRepo):
    """默认回复仓储"""

    table_name = "default_replies"

    # ------------------------- default_replies 表 -------------------------

    def save_default_reply(self, cookie_id: str, enabled: bool, reply_content: str = None, reply_once: bool = False, reply_image_url: str = None):
        """保存默认回复设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT OR REPLACE INTO default_replies (cookie_id, enabled, reply_content, reply_image_url, reply_once, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''',
                    (cookie_id, enabled, reply_content, reply_image_url, reply_once),
                )
                logger.debug(f"保存默认回复设置: {cookie_id} -> {'启用' if enabled else '禁用'}, 只回复一次: {'是' if reply_once else '否'}, 图片: {reply_image_url}")
        except Exception as e:
            logger.error(f"保存默认回复设置失败: {e}")
            raise

    def get_default_reply(self, cookie_id: str) -> Optional[Dict[str, any]]:
        """获取指定账号的默认回复设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT enabled, reply_content, reply_once, reply_image_url FROM default_replies WHERE cookie_id = ?
                    ''',
                    (cookie_id,),
                )
                result = cur.fetchone()
                if result:
                    enabled, reply_content, reply_once, reply_image_url = result
                    return {
                        'enabled': bool(enabled),
                        'reply_content': reply_content or '',
                        'reply_once': bool(reply_once) if reply_once is not None else False,
                        'reply_image_url': reply_image_url or ''
                    }
                return None
        except Exception as e:
            logger.error(f"获取默认回复设置失败: {e}")
            return None

    def get_all_default_replies(self) -> Dict[str, Dict[str, any]]:
        """获取所有账号的默认回复设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    'SELECT cookie_id, enabled, reply_content, reply_once, reply_image_url FROM default_replies',
                )

                result = {}
                for row in cur.fetchall():
                    cookie_id, enabled, reply_content, reply_once, reply_image_url = row
                    result[cookie_id] = {
                        'enabled': bool(enabled),
                        'reply_content': reply_content or '',
                        'reply_once': bool(reply_once) if reply_once is not None else False,
                        'reply_image_url': reply_image_url or ''
                    }

                return result
        except Exception as e:
            logger.error(f"获取所有默认回复设置失败: {e}")
            return {}

    def delete_default_reply(self, cookie_id: str) -> bool:
        """删除指定账号的默认回复设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM default_replies WHERE cookie_id = ?", (cookie_id,))
                logger.debug(f"删除默认回复设置: {cookie_id}")
                return True
        except Exception as e:
            logger.error(f"删除默认回复设置失败: {e}")
            return False

    def update_default_reply_image_url(self, cookie_id: str, new_image_url: str) -> bool:
        """更新默认回复的图片URL（用于将本地图片URL更新为CDN URL）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    UPDATE default_replies SET reply_image_url = ? WHERE cookie_id = ?
                    ''',
                    (new_image_url, cookie_id),
                )
                logger.debug(f"更新默认回复图片URL: {cookie_id} -> {new_image_url}")
                return True
        except Exception as e:
            logger.error(f"更新默认回复图片URL失败: {e}")
            return False

    # ------------------------- default_reply_records 表 -------------------------

    def add_default_reply_record(self, cookie_id: str, chat_id: str):
        """记录已回复的chat_id"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT OR IGNORE INTO default_reply_records (cookie_id, chat_id)
                    VALUES (?, ?)
                    ''',
                    (cookie_id, chat_id),
                )
                logger.debug(f"记录默认回复: {cookie_id} -> {chat_id}")
        except Exception as e:
            logger.error(f"记录默认回复失败: {e}")

    def has_default_reply_record(self, cookie_id: str, chat_id: str) -> bool:
        """检查是否已经回复过该chat_id"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT 1 FROM default_reply_records WHERE cookie_id = ? AND chat_id = ?
                    ''',
                    (cookie_id, chat_id),
                )
                result = cur.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"检查默认回复记录失败: {e}")
            return False

    def clear_default_reply_records(self, cookie_id: str):
        """清空指定账号的默认回复记录"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    'DELETE FROM default_reply_records WHERE cookie_id = ?',
                    (cookie_id,),
                )
                logger.debug(f"清空默认回复记录: {cookie_id}")
        except Exception as e:
            logger.error(f"清空默认回复记录失败: {e}")

    # ------------------------- ai_conversations 辅助 -------------------------

    def find_chat_id_by_buyer(self, cookie_id: str, buyer_id: str) -> str:
        """根据买家ID查找最近的chat_id（从AI对话记录中查找）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT chat_id FROM ai_conversations
                    WHERE cookie_id = ? AND user_id = ?
                    AND chat_id IS NOT NULL AND chat_id != ''
                    ORDER BY id DESC LIMIT 1
                    ''',
                    (cookie_id, buyer_id),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
                return None
        except Exception as e:
            logger.error(f"查找chat_id失败: {e}")
            return None


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
default_reply_repo = DefaultReplyRepo()


__all__ = ["DefaultReplyRepo", "default_reply_repo"]

"""
repositories/notification_repo.py
=================================
通知渠道与消息通知数据访问层（notification_channels / message_notifications 表）。

从 db_manager.DBManager 迁移而来：
- create_notification_channel / get_notification_channels / get_notification_channel
- update_notification_channel / delete_notification_channel
- set_message_notification / get_account_notifications
- get_all_message_notifications / delete_message_notification / delete_account_notifications

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, List, Optional

from loguru import logger

from .base import BaseRepo


class NotificationRepo(BaseRepo):
    """通知渠道与消息通知仓储"""

    table_name = "notification_channels"

    # ------------------------- 通知渠道操作 -------------------------

    def create_notification_channel(self, name: str, channel_type: str, config: str, user_id: int = None) -> int:
        """创建通知渠道"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT INTO notification_channels (name, type, config, user_id)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (name, channel_type, config, user_id),
                )
                channel_id = cur.lastrowid
                logger.debug(f"创建通知渠道: {name} (ID: {channel_id})")
                return channel_id
        except Exception as e:
            logger.error(f"创建通知渠道失败: {e}")
            raise

    def get_notification_channels(self, user_id: int = None) -> List[Dict[str, any]]:
        """获取所有通知渠道"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        '''
                        SELECT id, name, type, config, enabled, created_at, updated_at
                        FROM notification_channels
                        WHERE user_id = ?
                        ORDER BY created_at DESC
                        ''',
                        (user_id,),
                    )
                else:
                    self._execute_sql(
                        cur,
                        '''
                        SELECT id, name, type, config, enabled, created_at, updated_at
                        FROM notification_channels
                        ORDER BY created_at DESC
                        ''',
                    )

                channels = []
                for row in cur.fetchall():
                    channels.append({
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'config': row[3],
                        'enabled': bool(row[4]),
                        'created_at': row[5],
                        'updated_at': row[6]
                    })

                return channels
        except Exception as e:
            logger.error(f"获取通知渠道失败: {e}")
            return []

    def get_notification_channel(self, channel_id: int) -> Optional[Dict[str, any]]:
        """获取指定通知渠道"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT id, name, type, config, enabled, created_at, updated_at
                    FROM notification_channels WHERE id = ?
                    ''',
                    (channel_id,),
                )

                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'config': row[3],
                        'enabled': bool(row[4]),
                        'created_at': row[5],
                        'updated_at': row[6]
                    }
                return None
        except Exception as e:
            logger.error(f"获取通知渠道失败: {e}")
            return None

    def update_notification_channel(self, channel_id: int, name: str, config: str, enabled: bool = True) -> bool:
        """更新通知渠道"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    UPDATE notification_channels
                    SET name = ?, config = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''',
                    (name, config, enabled, channel_id),
                )
                logger.debug(f"更新通知渠道: {channel_id}")
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"更新通知渠道失败: {e}")
            return False

    def delete_notification_channel(self, channel_id: int) -> bool:
        """删除通知渠道"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM notification_channels WHERE id = ?", (channel_id,))
                logger.debug(f"删除通知渠道: {channel_id}")
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除通知渠道失败: {e}")
            return False

    # ------------------------- 消息通知配置操作 -------------------------

    def set_message_notification(self, cookie_id: str, channel_id: int, enabled: bool = True) -> bool:
        """设置账号的消息通知"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT OR REPLACE INTO message_notifications (cookie_id, channel_id, enabled)
                    VALUES (?, ?, ?)
                    ''',
                    (cookie_id, channel_id, enabled),
                )
                logger.debug(f"设置消息通知: {cookie_id} -> {channel_id}")
                return True
        except Exception as e:
            logger.error(f"设置消息通知失败: {e}")
            return False

    def get_account_notifications(self, cookie_id: str) -> List[Dict[str, any]]:
        """获取账号的通知配置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT mn.id, mn.channel_id, mn.enabled, nc.name, nc.type, nc.config
                    FROM message_notifications mn
                    JOIN notification_channels nc ON mn.channel_id = nc.id
                    WHERE mn.cookie_id = ? AND nc.enabled = 1
                    ORDER BY mn.id
                    ''',
                    (cookie_id,),
                )

                notifications = []
                for row in cur.fetchall():
                    notifications.append({
                        'id': row[0],
                        'channel_id': row[1],
                        'enabled': bool(row[2]),
                        'channel_name': row[3],
                        'channel_type': row[4],
                        'channel_config': row[5]
                    })

                return notifications
        except Exception as e:
            logger.error(f"获取账号通知配置失败: {e}")
            return []

    def get_all_message_notifications(self) -> Dict[str, List[Dict[str, any]]]:
        """获取所有账号的通知配置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    SELECT mn.cookie_id, mn.id, mn.channel_id, mn.enabled, nc.name, nc.type, nc.config
                    FROM message_notifications mn
                    JOIN notification_channels nc ON mn.channel_id = nc.id
                    WHERE nc.enabled = 1
                    ORDER BY mn.cookie_id, mn.id
                    ''',
                )

                result = {}
                for row in cur.fetchall():
                    cookie_id = row[0]
                    if cookie_id not in result:
                        result[cookie_id] = []

                    result[cookie_id].append({
                        'id': row[1],
                        'channel_id': row[2],
                        'enabled': bool(row[3]),
                        'channel_name': row[4],
                        'channel_type': row[5],
                        'channel_config': row[6]
                    })

                return result
        except Exception as e:
            logger.error(f"获取所有消息通知配置失败: {e}")
            return {}

    def delete_message_notification(self, notification_id: int) -> bool:
        """删除消息通知配置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM message_notifications WHERE id = ?", (notification_id,))
                logger.debug(f"删除消息通知配置: {notification_id}")
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除消息通知配置失败: {e}")
            return False

    def delete_account_notifications(self, cookie_id: str) -> bool:
        """删除账号的所有消息通知配置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM message_notifications WHERE cookie_id = ?", (cookie_id,))
                logger.debug(f"删除账号通知配置: {cookie_id}")
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除账号通知配置失败: {e}")
            return False


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
notification_repo = NotificationRepo()


__all__ = ["NotificationRepo", "notification_repo"]

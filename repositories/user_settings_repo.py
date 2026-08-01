"""
repositories/user_settings_repo.py
==================================
用户设置数据访问层（user_settings 表）。

从 db_manager.DBManager 迁移而来：
- get_user_settings(user_id)：获取用户的所有设置
- get_user_setting(user_id, key)：获取用户的特定设置
- set_user_setting(user_id, key, value, description)：设置用户配置（INSERT OR REPLACE）

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, Optional

from loguru import logger

from .base import BaseRepo


class UserSettingsRepo(BaseRepo):
    """用户设置仓储"""

    table_name = "user_settings"

    def get_user_settings(self, user_id: int) -> Dict[str, dict]:
        """获取用户的所有设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    SELECT key, value, description, updated_at
                    FROM user_settings
                    WHERE user_id = ?
                    ORDER BY key
                    """,
                    (user_id,),
                )
                settings = {}
                for row in cur.fetchall():
                    settings[row[0]] = {
                        'value': row[1],
                        'description': row[2],
                        'updated_at': row[3],
                    }
                return settings
        except Exception as e:
            logger.error(f"获取用户设置失败: {e}")
            return {}

    def get_user_setting(self, user_id: int, key: str) -> Optional[dict]:
        """获取用户的特定设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    SELECT value, description, updated_at
                    FROM user_settings
                    WHERE user_id = ? AND key = ?
                    """,
                    (user_id, key),
                )
                row = cur.fetchone()
                if row:
                    return {
                        'key': key,
                        'value': row[0],
                        'description': row[1],
                        'updated_at': row[2],
                    }
                return None
        except Exception as e:
            logger.error(f"获取用户设置失败: {e}")
            return None

    def set_user_setting(
        self,
        user_id: int,
        key: str,
        value: str,
        description: str = None,
    ) -> bool:
        """设置用户配置（INSERT OR REPLACE）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    INSERT OR REPLACE INTO user_settings (user_id, key, value, description, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (user_id, key, value, description),
                )
                conn.commit()
                logger.info(f"用户设置更新成功: user_id={user_id}, key={key}")
                return True
        except Exception as e:
            logger.error(f"设置用户配置失败: {e}")
            return False


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
user_settings_repo = UserSettingsRepo()

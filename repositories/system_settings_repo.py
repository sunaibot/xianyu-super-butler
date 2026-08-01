"""
repositories/system_settings_repo.py
=====================================
系统设置数据访问层（system_settings 表）。

从 db_manager.DBManager 迁移而来：
- get_system_setting / set_system_setting / get_all_system_settings

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, Optional

from loguru import logger

from .base import BaseRepo


class SystemSettingsRepo(BaseRepo):
    """系统设置仓储"""

    table_name = "system_settings"

    def get_system_setting(self, key: str) -> Optional[str]:
        """获取系统设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT value FROM system_settings WHERE key = ?", (key,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"获取系统设置失败: {e}")
            return None

    def set_system_setting(self, key: str, value: str, description: str = None) -> bool:
        """设置系统设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT OR REPLACE INTO system_settings (key, value, description, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''',
                    (key, value, description),
                )
                logger.debug(f"设置系统设置: {key}")
                return True
        except Exception as e:
            logger.error(f"设置系统设置失败: {e}")
            return False

    def get_all_system_settings(self) -> Dict[str, str]:
        """获取所有系统设置"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT key, value FROM system_settings")

                settings = {}
                for row in cur.fetchall():
                    settings[row[0]] = row[1]

                return settings
        except Exception as e:
            logger.error(f"获取所有系统设置失败: {e}")
            return {}


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
system_settings_repo = SystemSettingsRepo()


__all__ = ["SystemSettingsRepo", "system_settings_repo"]

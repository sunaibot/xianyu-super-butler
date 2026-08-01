"""
repositories/user_repo.py
============================
User 仓储：从 DBManager 迁移而来的 User 域数据访问。

迁移范围：
- create_user（含 hash_password）
- get_user_by_username / get_user_by_email / get_user_by_id / get_all_users
- verify_user_password（含 bcrypt 自动迁移旧 SHA-256 哈希）
- update_user_password
- delete_user_and_data（事务性级联删除）

设计原则：
- 继承 BaseRepo，使用独立连接（每次新建 + with 语句自动事务）
- delete_user_and_data 使用 BEGIN/COMMIT/ROLLBACK 显式事务，保证级联删除原子性
- DBManager 对应方法将逐步委托到此处（向后兼容）
- 密码哈希逻辑委托给 password_utils 模块
"""
from typing import Optional, Dict, Any, List
from loguru import logger

from .base import BaseRepo


class UserRepo(BaseRepo):
    """User 仓储（users 表 + 级联删除）"""

    table_name = "users"

    # ------------------------- 写操作 -------------------------

    def create_user(self, username: str, email: str, password: str) -> bool:
        """创建新用户"""
        try:
            from password_utils import hash_password
            with self.get_connection() as conn:
                cur = conn.cursor()
                password_hash = hash_password(password)
                self._execute_sql(
                    cur,
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, password_hash),
                )
                logger.info(f"创建用户成功: {username} ({email})")
                return True
        except Exception as e:
            # sqlite3.IntegrityError 在 with 语句中由 conn 处理回滚
            logger.error(f"创建用户失败，用户名或邮箱已存在: {e}")
            return False

    def update_user_password(self, username: str, new_password: str) -> bool:
        """更新用户密码"""
        try:
            from password_utils import hash_password
            with self.get_connection() as conn:
                cur = conn.cursor()
                password_hash = hash_password(new_password)
                self._execute_sql(
                    cur,
                    "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
                    (password_hash, username),
                )
                if cur.rowcount > 0:
                    logger.info(f"用户 {username} 密码更新成功")
                    return True
                logger.warning(f"用户 {username} 不存在，密码更新失败")
                return False
        except Exception as e:
            logger.error(f"更新用户密码失败: {e}")
            return False

    def delete_user_and_data(self, user_id: int) -> bool:
        """删除用户及其所有相关数据（事务性级联删除）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                # 显式事务：BEGIN/COMMIT/ROLLBACK，与原实现保持一致
                self._execute_sql(cur, "BEGIN TRANSACTION")

                # 1. 删除用户设置
                self._execute_sql(cur, "DELETE FROM user_settings WHERE user_id = ?", (user_id,))
                # 2. 删除用户的卡券
                self._execute_sql(cur, "DELETE FROM cards WHERE user_id = ?", (user_id,))
                # 3. 删除用户的发货规则
                self._execute_sql(cur, "DELETE FROM delivery_rules WHERE user_id = ?", (user_id,))
                # 4. 删除用户的通知渠道
                self._execute_sql(cur, "DELETE FROM notification_channels WHERE user_id = ?", (user_id,))
                # 5. 删除用户的Cookie
                self._execute_sql(cur, "DELETE FROM cookies WHERE user_id = ?", (user_id,))
                # 6. 删除用户的关键字（cookie 已删，子查询理论上不会命中，保留兜底）
                self._execute_sql(
                    cur,
                    "DELETE FROM keywords WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)",
                    (user_id,),
                )
                # 7. 删除用户的默认回复
                self._execute_sql(
                    cur,
                    "DELETE FROM default_replies WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)",
                    (user_id,),
                )
                # 8. 删除用户的AI回复设置
                self._execute_sql(
                    cur,
                    "DELETE FROM ai_reply_settings WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)",
                    (user_id,),
                )
                # 9. 删除用户的消息通知
                self._execute_sql(
                    cur,
                    "DELETE FROM message_notifications WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)",
                    (user_id,),
                )
                # 10. 最后删除用户本身
                self._execute_sql(cur, "DELETE FROM users WHERE id = ?", (user_id,))

                self._execute_sql(cur, "COMMIT")
                logger.info(f"用户及相关数据删除成功: user_id={user_id}")
                return True
        except Exception as e:
            try:
                with self.get_connection() as conn:
                    cur = conn.cursor()
                    self._execute_sql(cur, "ROLLBACK")
            except Exception:
                pass
            logger.error(f"删除用户及相关数据失败: {e}")
            return False

    # ------------------------- 读操作 -------------------------

    def _row_to_user_full(self, row) -> Dict[str, Any]:
        """行数据 → 用户完整字段（含 password_hash，供验证用）"""
        return {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'password_hash': row[3],
            'is_active': row[4],
            'is_admin': bool(row[5]),
            'created_at': row[6],
            'updated_at': row[7],
        }

    def _row_to_user_public(self, row) -> Dict[str, Any]:
        """行数据 → 用户公开字段（不含 password_hash）"""
        return {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'created_at': row[3],
            'updated_at': row[4],
        }

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户信息（含 password_hash）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, username, email, password_hash, is_active, is_admin, created_at, updated_at "
                    "FROM users WHERE username = ?",
                    (username,),
                )
                row = cur.fetchone()
                return self._row_to_user_full(row) if row else None
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱获取用户信息（含 password_hash）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, username, email, password_hash, is_active, is_admin, created_at, updated_at "
                    "FROM users WHERE email = ?",
                    (email,),
                )
                row = cur.fetchone()
                return self._row_to_user_full(row) if row else None
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取用户信息（公开字段）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, username, email, created_at, updated_at FROM users WHERE id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
                return self._row_to_user_public(row) if row else None
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """获取所有用户信息（管理员专用，公开字段）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, username, email, created_at, updated_at "
                    "FROM users ORDER BY created_at DESC",
                )
                return [self._row_to_user_public(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取所有用户失败: {e}")
            return []

    # ------------------------- 密码验证 -------------------------

    def verify_user_password(self, username: str, password: str) -> bool:
        """验证用户密码（支持 bcrypt 自动迁移旧 SHA-256 哈希）"""
        try:
            from password_utils import verify_password, needs_migration, migrate_password
        except ImportError as e:
            logger.error(f"password_utils 模块不可用: {e}")
            return False

        user = self.get_user_by_username(username)
        if not user:
            return False
        if not user.get('is_active'):
            return False

        stored_hash = user.get('password_hash', '')
        if not stored_hash:
            return False

        if not verify_password(password, stored_hash):
            return False

        # 验证成功，按需迁移到 bcrypt
        if needs_migration(stored_hash):
            new_hash = migrate_password(password)
            if new_hash:
                try:
                    with self.get_connection() as conn:
                        cur = conn.cursor()
                        self._execute_sql(
                            cur,
                            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
                            (new_hash, username),
                        )
                        logger.info(f"用户 {username} 密码已自动迁移到 bcrypt")
                except Exception as e:
                    logger.warning(f"密码迁移失败（不影响本次登录）: {e}")
        return True


# 模块级单例（与 db_manager 单例等价的访问方式）
user_repo = UserRepo()


__all__ = ["UserRepo", "user_repo"]

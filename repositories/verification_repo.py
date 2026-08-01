"""
repositories/verification_repo.py
==================================
验证码数据访问层（captcha_codes / email_verifications 表）。

从 db_manager.DBManager 迁移而来（仅 DB 方法，纯逻辑的
generate_verification_code / generate_captcha 保留在 DBManager 中）：
- save_captcha / verify_captcha（图形验证码）
- save_verification_code / verify_email_code（邮箱验证码）

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
import time

from loguru import logger

from .base import BaseRepo


class VerificationRepo(BaseRepo):
    """验证码仓储"""

    table_name = "captcha_codes"

    # ------------------------- 图形验证码（captcha_codes 表） -------------------------

    def save_captcha(self, session_id: str, captcha_text: str, expires_minutes: int = 5) -> bool:
        """保存图形验证码"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                expires_at = time.time() + (expires_minutes * 60)

                # 删除该session的旧验证码
                self._execute_sql(cur, 'DELETE FROM captcha_codes WHERE session_id = ?', (session_id,))

                self._execute_sql(
                    cur,
                    '''
                    INSERT INTO captcha_codes (session_id, code, expires_at)
                    VALUES (?, ?, ?)
                    ''',
                    (session_id, captcha_text.upper(), expires_at),
                )

                logger.debug(f"保存图形验证码成功: {session_id}")
                return True
        except Exception as e:
            logger.error(f"保存图形验证码失败: {e}")
            return False

    def verify_captcha(self, session_id: str, user_input: str) -> bool:
        """验证图形验证码"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                current_time = time.time()

                # 查找有效的验证码
                self._execute_sql(
                    cur,
                    '''
                    SELECT id FROM captcha_codes
                    WHERE session_id = ? AND code = ? AND expires_at > ?
                    ORDER BY created_at DESC LIMIT 1
                    ''',
                    (session_id, user_input.upper(), current_time),
                )

                row = cur.fetchone()
                if row:
                    # 删除已使用的验证码
                    self._execute_sql(cur, 'DELETE FROM captcha_codes WHERE id = ?', (row[0],))
                    logger.debug(f"图形验证码验证成功: {session_id}")
                    return True
                else:
                    logger.warning(f"图形验证码验证失败: {session_id} - {user_input}")
                    return False
        except Exception as e:
            logger.error(f"验证图形验证码失败: {e}")
            return False

    # ------------------------- 邮箱验证码（email_verifications 表） -------------------------

    def save_verification_code(self, email: str, code: str, code_type: str = 'register', expires_minutes: int = 10) -> bool:
        """保存邮箱验证码"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                expires_at = time.time() + (expires_minutes * 60)

                self._execute_sql(
                    cur,
                    '''
                    INSERT INTO email_verifications (email, code, type, expires_at)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (email, code, code_type, expires_at),
                )

                logger.info(f"保存验证码成功: {email} ({code_type})")
                return True
        except Exception as e:
            logger.error(f"保存验证码失败: {e}")
            return False

    def verify_email_code(self, email: str, code: str, code_type: str = 'register') -> bool:
        """验证邮箱验证码"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                current_time = time.time()

                # 查找有效的验证码
                self._execute_sql(
                    cur,
                    '''
                    SELECT id FROM email_verifications
                    WHERE email = ? AND code = ? AND type = ? AND expires_at > ? AND used = FALSE
                    ORDER BY created_at DESC LIMIT 1
                    ''',
                    (email, code, code_type, current_time),
                )

                row = cur.fetchone()
                if row:
                    # 标记验证码为已使用
                    self._execute_sql(
                        cur,
                        '''
                        UPDATE email_verifications SET used = TRUE WHERE id = ?
                        ''',
                        (row[0],),
                    )
                    logger.info(f"验证码验证成功: {email} ({code_type})")
                    return True
                else:
                    logger.warning(f"验证码验证失败: {email} - {code} ({code_type})")
                    return False
        except Exception as e:
            logger.error(f"验证邮箱验证码失败: {e}")
            return False


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
verification_repo = VerificationRepo()


__all__ = ["VerificationRepo", "verification_repo"]

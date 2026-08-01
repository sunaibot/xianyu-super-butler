"""
repositories/cookie_repo.py
============================
Cookie 仓储：从 DBManager 迁移而来的 Cookie 域数据访问。

迁移范围：
- save_cookie / delete_cookie
- get_cookie / get_all_cookies / get_cookie_by_id
- get_cookie_details / get_all_cookie_details（批量，消除 N+1）
- update_auto_confirm / get_auto_confirm
- update_cookie_remark
- update_cookie_pause_duration / get_cookie_pause_duration
- update_cookie_account_info
- save_cookie_status / get_cookie_status / get_all_cookie_status（cookie_status 表）

设计原则：
- 继承 BaseRepo，使用独立连接（每次新建 + with 语句自动事务）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
- 高内聚：所有 cookies 表操作聚集于此
"""
from typing import Optional, Dict, List, Any
from loguru import logger

from .base import BaseRepo


class CookieRepo(BaseRepo):
    """Cookie 仓储（cookies 表）"""

    table_name = "cookies"

    # ------------------------- 写操作 -------------------------

    def save_cookie(self, cookie_id: str, cookie_value: str, user_id: Optional[int] = None) -> bool:
        """保存 Cookie（存在则更新）。user_id 缺省时尝试沿用既有记录，否则回退到 admin 用户。"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # user_id 缺省：沿用既有记录或回退到 admin
                if user_id is None:
                    self._execute_sql(cur, "SELECT user_id FROM cookies WHERE id = ?", (cookie_id,))
                    existing = cur.fetchone()
                    if existing:
                        user_id = existing[0]
                    else:
                        self._execute_sql(cur, "SELECT id FROM users WHERE username = 'admin'")
                        admin_user = cur.fetchone()
                        if not admin_user:
                            raise RuntimeError('系统未初始化：admin 用户不存在，请先执行 init_admin.py 初始化管理员')
                        user_id = admin_user[0]

                self._execute_sql(
                    cur,
                    "INSERT OR REPLACE INTO cookies (id, value, user_id) VALUES (?, ?, ?)",
                    (cookie_id, cookie_value, user_id),
                )
                # with 语句退出时自动 commit
                logger.info(f"Cookie保存成功: {cookie_id} (用户ID: {user_id})")
                return True
        except Exception as e:
            logger.error(f"Cookie保存失败: {e}")
            return False

    def delete_cookie(self, cookie_id: str) -> bool:
        """删除 Cookie 及其关联关键字"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM keywords WHERE cookie_id = ?", (cookie_id,))
                self._execute_sql(cur, "DELETE FROM cookies WHERE id = ?", (cookie_id,))
                logger.debug(f"Cookie删除成功: {cookie_id}")
                return True
        except Exception as e:
            logger.error(f"Cookie删除失败: {e}")
            return False

    def update_auto_confirm(self, cookie_id: str, auto_confirm: bool) -> bool:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE cookies SET auto_confirm = ? WHERE id = ?",
                    (int(auto_confirm), cookie_id),
                )
                logger.info(f"更新账号 {cookie_id} 自动确认发货设置: {'开启' if auto_confirm else '关闭'}")
                return True
        except Exception as e:
            logger.error(f"更新自动确认发货设置失败: {e}")
            return False

    def update_cookie_remark(self, cookie_id: str, remark: str) -> bool:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "UPDATE cookies SET remark = ? WHERE id = ?", (remark, cookie_id))
                logger.info(f"更新账号 {cookie_id} 备注: {remark}")
                return True
        except Exception as e:
            logger.error(f"更新账号备注失败: {e}")
            return False

    def update_cookie_pause_duration(self, cookie_id: str, pause_duration: int) -> bool:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE cookies SET pause_duration = ? WHERE id = ?",
                    (pause_duration, cookie_id),
                )
                logger.info(f"更新账号 {cookie_id} 自动回复暂停时间: {pause_duration}分钟")
                return True
        except Exception as e:
            logger.error(f"更新账号自动回复暂停时间失败: {e}")
            return False

    def update_cookie_account_info(
        self,
        cookie_id: str,
        cookie_value: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        show_browser: Optional[bool] = None,
        user_id: Optional[int] = None,
    ) -> bool:
        """更新账号信息；记录不存在时按需创建"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                self._execute_sql(cur, "SELECT id FROM cookies WHERE id = ?", (cookie_id,))
                exists = cur.fetchone() is not None

                if not exists:
                    # 新建记录
                    if cookie_value is None:
                        logger.warning(f"账号 {cookie_id} 不存在，且未提供cookie_value，无法创建")
                        return False
                    if user_id is None:
                        self._execute_sql(cur, "SELECT id FROM users WHERE username = 'admin'")
                        admin_user = cur.fetchone()
                        if not admin_user:
                            raise RuntimeError('系统未初始化：admin 用户不存在')
                        user_id = admin_user[0]

                    fields, values = ['id', 'value', 'user_id'], [cookie_id, cookie_value, user_id]
                    if username is not None:
                        fields.append('username'); values.append(username)
                    if password is not None:
                        fields.append('password'); values.append(password)
                    if show_browser is not None:
                        fields.append('show_browser'); values.append(1 if show_browser else 0)

                    placeholders = ','.join('?' * len(fields))
                    sql = f"INSERT INTO cookies ({','.join(fields)}) VALUES ({placeholders})"
                    self._execute_sql(cur, sql, tuple(values))
                    logger.info(f"创建新账号 {cookie_id} 并保存信息成功: {fields}")
                    return True
                else:
                    # 更新既有记录
                    set_clauses, params = [], []
                    if cookie_value is not None:
                        set_clauses.append("value = ?"); params.append(cookie_value)
                    if username is not None:
                        set_clauses.append("username = ?"); params.append(username)
                    if password is not None:
                        set_clauses.append("password = ?"); params.append(password)
                    if show_browser is not None:
                        set_clauses.append("show_browser = ?"); params.append(1 if show_browser else 0)

                    if not set_clauses:
                        logger.warning(f"更新账号 {cookie_id} 信息时没有提供任何更新字段")
                        return False

                    params.append(cookie_id)
                    sql = f"UPDATE cookies SET {', '.join(set_clauses)} WHERE id = ?"
                    self._execute_sql(cur, sql, tuple(params))
                    logger.info(f"更新账号 {cookie_id} 信息成功: {set_clauses}")
                    return True
        except Exception as e:
            logger.error(f"更新账号信息失败: {e}")
            return False

    # ------------------------- 读操作 -------------------------

    def get_cookie(self, cookie_id: str) -> Optional[str]:
        """获取 Cookie 值"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT value FROM cookies WHERE id = ?", (cookie_id,))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"获取Cookie失败: {e}")
            return None

    def get_all_cookies(self, user_id: Optional[int] = None) -> Dict[str, str]:
        """获取所有 Cookie（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(cur, "SELECT id, value FROM cookies WHERE user_id = ?", (user_id,))
                else:
                    self._execute_sql(cur, "SELECT id, value FROM cookies")
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"获取所有Cookie失败: {e}")
            return {}

    def get_cookie_by_id(self, cookie_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 Cookie 信息（含 cookies_str 别名以匹配调用方期望）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, value, created_at FROM cookies WHERE id = ?",
                    (cookie_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0],
                    'cookies_str': row[1],  # 调用方期望字段名
                    'value': row[1],        # 向后兼容
                    'created_at': row[2],
                }
        except Exception as e:
            logger.error(f"根据ID获取Cookie失败: {e}")
            return None

    def get_cookie_details(self, cookie_id: str) -> Optional[Dict[str, Any]]:
        """获取 Cookie 详情（含敏感字段，供编辑场景使用）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, value, user_id, auto_confirm, remark, pause_duration, "
                    "username, password, show_browser, created_at FROM cookies WHERE id = ?",
                    (cookie_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0],
                    'value': row[1],
                    'user_id': row[2],
                    'auto_confirm': bool(row[3]),
                    'remark': row[4] or '',
                    'pause_duration': row[5] if row[5] is not None else 10,
                    'username': row[6] or '',
                    'password': row[7] or '',
                    'show_browser': bool(row[8]) if row[8] is not None else False,
                    'created_at': row[9],
                }
        except Exception as e:
            logger.error(f"获取Cookie详细信息失败: {e}")
            return None

    def get_all_cookie_details(self, user_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """批量获取多个 Cookie 的详情（消除列表接口的 N+1 查询）。
        不返回 value/username/password 等敏感字段。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        "SELECT id, user_id, auto_confirm, remark, pause_duration, show_browser, created_at "
                        "FROM cookies WHERE user_id = ?",
                        (user_id,),
                    )
                else:
                    self._execute_sql(
                        cur,
                        "SELECT id, user_id, auto_confirm, remark, pause_duration, show_browser, created_at FROM cookies",
                    )
                result = {}
                for row in cur.fetchall():
                    cid = row[0]
                    result[cid] = {
                        'id': cid,
                        'user_id': row[1],
                        'auto_confirm': bool(row[2]) if row[2] is not None else False,
                        'remark': row[3] or '',
                        'pause_duration': row[4] if row[4] is not None else 10,
                        'show_browser': bool(row[5]) if row[5] is not None else False,
                        'created_at': row[6],
                    }
                return result
        except Exception as e:
            logger.error(f"批量获取Cookie详细信息失败: {e}")
            return {}

    def get_auto_confirm(self, cookie_id: str) -> bool:
        """获取自动确认发货设置（默认 True）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT auto_confirm FROM cookies WHERE id = ?", (cookie_id,))
                row = cur.fetchone()
                if row:
                    return bool(row[0])
                return True
        except Exception as e:
            logger.error(f"获取自动确认发货设置失败: {e}")
            return True

    def get_cookie_pause_duration(self, cookie_id: str) -> int:
        """获取自动回复暂停时间（NULL 修复为 10 分钟）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT pause_duration FROM cookies WHERE id = ?", (cookie_id,))
                row = cur.fetchone()
                if not row:
                    logger.warning(f"账号 {cookie_id} 未找到记录，使用默认值10分钟")
                    return 10
                if row[0] is None:
                    logger.warning(f"账号 {cookie_id} 的pause_duration为NULL，使用默认值10分钟并修复数据库")
                    self._execute_sql(cur, "UPDATE cookies SET pause_duration = 10 WHERE id = ?", (cookie_id,))
                    return 10
                return row[0]
        except Exception as e:
            logger.error(f"获取账号自动回复暂停时间失败: {e}")
            return 10

    # ------------------------- cookie_status 表 -------------------------

    def save_cookie_status(self, cookie_id: str, enabled: bool) -> None:
        """保存 Cookie 的启用状态（cookie_status 表）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "INSERT OR REPLACE INTO cookie_status (cookie_id, enabled, updated_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (cookie_id, 1 if enabled else 0),
                )
                logger.debug(f"保存Cookie状态: {cookie_id} -> {'启用' if enabled else '禁用'}")
        except Exception as e:
            logger.error(f"保存Cookie状态失败: {e}")
            raise

    def get_cookie_status(self, cookie_id: str) -> bool:
        """获取 Cookie 的启用状态（默认启用）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT enabled FROM cookie_status WHERE cookie_id = ?",
                    (cookie_id,),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else True
        except Exception as e:
            logger.error(f"获取Cookie状态失败: {e}")
            return True

    def get_all_cookie_status(self) -> Dict[str, bool]:
        """获取所有 Cookie 的启用状态"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT cookie_id, enabled FROM cookie_status")
                return {row[0]: bool(row[1]) for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"获取所有Cookie状态失败: {e}")
            return {}

    def search_cookies(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """跨字段 LIKE 搜索账号（用于全局搜索，不返回敏感字段）"""
        try:
            like = f"%{keyword}%"
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT cookie_id, remark, username FROM cookies "
                    "WHERE cookie_id LIKE ? OR remark LIKE ? OR username LIKE ? LIMIT ?",
                    (like, like, like, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"搜索账号失败: {e}")
            return []


# 模块级单例（与 db_manager 单例等价的访问方式）
cookie_repo = CookieRepo()


__all__ = ["CookieRepo", "cookie_repo"]

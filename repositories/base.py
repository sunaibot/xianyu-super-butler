"""
repositories/base.py
====================
通用仓储基类。

为 db_manager.py 的拆分提供基础：
- BaseRepo 封装连接管理与通用 SQL 工具
- 子类按业务域（CookieRepo / OrderRepo 等）继承并实现具体方法
- DBManager 保持向后兼容，未来逐步委托给各 repo

迁移示例（cookie_repo.py）：
    class CookieRepo(BaseRepo):
        def save_cookie(self, cookie_id, cookie_value, user_id=None):
            # 从 db_manager.DBManager.save_cookie 迁移而来
            ...

设计原则：高内聚（同表方法聚集）、低耦合（repo 间无依赖）、原子化（单一职责）。
"""
import sqlite3
import re
from typing import Any, Optional, List, Tuple
from loguru import logger
from config import DB_PATH as _DEFAULT_DB_PATH, SQL_LOG_ENABLED, SQL_LOG_LEVEL

# 敏感字段脱敏正则（与 db_manager / log_sanitizer 一致）
_SENSITIVE_FIELDS = re.compile(r'(?i)(password|passwd|secret|token|api[_-]?key|cookie|authorization)')
_SANITIZE_REPLACE = '***敏感信息已脱敏***'


def _get_db_path() -> str:
    return _DEFAULT_DB_PATH


class BaseRepo:
    """通用仓储基类"""

    # 子类可覆盖表名
    table_name: str = ""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or _get_db_path()

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（调用方负责关闭）"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------- 通用 SQL 工具 ----------

    def _sanitize_param(self, param: Any, field_name: str = '') -> Any:
        """敏感字段日志脱敏"""
        if not field_name:
            return param
        if _SENSITIVE_FIELDS.search(field_name) and isinstance(param, str):
            return _SANITIZE_REPLACE
        return param

    def _log_sql(self, sql: str, params: tuple = None, operation: str = "EXECUTE") -> None:
        """SQL 日志（受 SQL_LOG_ENABLED 控制，默认启用，与 db_manager 保持一致）"""
        if not SQL_LOG_ENABLED:
            return
        level = SQL_LOG_LEVEL
        # 脱敏参数
        safe_params = None
        if params:
            safe_params = tuple(self._sanitize_param(p, '') for p in params)
        logger.log(
            getattr(logger, level, logger.INFO),
            f"[SQL:{operation}] {sql} | params={safe_params}"
        )

    def _execute_sql(self, cursor: sqlite3.Cursor, sql: str, params: tuple = None) -> sqlite3.Cursor:
        """执行 SQL（带日志）"""
        self._log_sql(sql, params)
        if params:
            return cursor.execute(sql, params)
        return cursor.execute(sql)

    def _executemany_sql(self, cursor: sqlite3.Cursor, sql: str, params_list: List[tuple]) -> sqlite3.Cursor:
        """批量执行 SQL"""
        self._log_sql(sql, None, "EXECUTEMANY")
        return cursor.executemany(sql, params_list)

    # ---------- 通用 CRUD ----------

    def find_by_id(self, id_value: Any, id_col: str = "id") -> Optional[dict]:
        """按主键查询"""
        if not self.table_name:
            raise ValueError("子类未设置 table_name")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute_sql(cursor, f"SELECT * FROM {self.table_name} WHERE {id_col} = ?", (id_value,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def find_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """查询全部（分页）"""
        if not self.table_name:
            raise ValueError("子类未设置 table_name")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute_sql(cursor, f"SELECT * FROM {self.table_name} LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def count(self) -> int:
        """总数"""
        if not self.table_name:
            raise ValueError("子类未设置 table_name")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute_sql(cursor, f"SELECT COUNT(*) FROM {self.table_name}")
            return cursor.fetchone()[0]

    def delete_by_id(self, id_value: Any, id_col: str = "id") -> bool:
        """按主键删除"""
        if not self.table_name:
            raise ValueError("子类未设置 table_name")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute_sql(cursor, f"DELETE FROM {self.table_name} WHERE {id_col} = ?", (id_value,))
            conn.commit()
            return cursor.rowcount > 0

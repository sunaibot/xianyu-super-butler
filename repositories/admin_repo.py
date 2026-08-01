"""
repositories/admin_repo.py
==========================
管理员通用表操作仓储。

为 db_manager.py 中残留的通用表管理方法提供下沉位置：
- get_table_data(table_name)         获取整表数据 + 列名
- delete_table_record(table, id)     按主键删除单条记录
- clear_table_data(table)            清空整表（含 sqlite_sequence 重置）

设计原则：
- 主键探测使用 PRAGMA table_info，不再维护硬编码 primary_key_map
- 表名白名单由 routers/admin.py 维护，本 repo 信任调用方已校验
- 使用 BaseRepo.get_connection 独立连接，与 DBManager.conn 解耦
"""
import sqlite3
from typing import List, Tuple, Dict, Any

from loguru import logger

from .base import BaseRepo


class AdminRepo(BaseRepo):
    """管理员通用表操作仓储（无固定 table_name，方法接收 table_name 参数）"""

    table_name: str = ""  # 不使用基类的固定表名

    # ---------- 主键探测 ----------

    def _detect_primary_key(self, conn: sqlite3.Connection, table_name: str) -> str:
        """通过 PRAGMA table_info 探测表的主键列名

        - 优先返回 pk=1 的列
        - 无显式主键时回退为 'id'（兼容老表）
        - orders 表特殊处理：主键为 order_id
        """
        # 特殊兜底：orders 表在 schema 中主键为 order_id，PRAGMA 应能识别
        cursor = conn.cursor()
        self._execute_sql(cursor, f"PRAGMA table_info({table_name})")
        for col in cursor.fetchall():
            # col: (cid, name, type, notnull, dflt_value, pk)
            if col[5] == 1:  # pk 标记
                return col[1]
        # 兜底：无主键时返回 id
        return "id"

    # ---------- 通用表查询 ----------

    def get_table_data(self, table_name: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """获取指定表的所有数据 + 列名列表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 表结构
                self._execute_sql(cursor, f"PRAGMA table_info({table_name})")
                columns_info = cursor.fetchall()
                columns = [col[1] for col in columns_info]

                # 全表数据
                self._execute_sql(cursor, f"SELECT * FROM {table_name}")
                rows = cursor.fetchall()

                data = [dict(row) for row in rows]
                return data, columns
        except Exception as e:
            logger.error(f"获取表数据失败: {table_name} - {e}")
            return [], []

    def delete_table_record(self, table_name: str, record_id: str) -> bool:
        """按主键删除指定表的指定记录

        主键列通过 PRAGMA table_info 自动探测，无需硬编码。
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                primary_key = self._detect_primary_key(conn, table_name)

                self._execute_sql(
                    cursor,
                    f"DELETE FROM {table_name} WHERE {primary_key} = ?",
                    (record_id,),
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除表记录成功: {table_name}.{record_id} (pk={primary_key})")
                    return True
                logger.warning(f"删除表记录失败，记录不存在: {table_name}.{record_id}")
                return False
        except Exception as e:
            logger.error(f"删除表记录失败: {table_name}.{record_id} - {e}")
            return False

    def clear_table_data(self, table_name: str) -> bool:
        """清空指定表的所有数据，并重置 sqlite_sequence"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                self._execute_sql(cursor, f"DELETE FROM {table_name}")
                # 重置自增 ID（若表无 AUTOINCREMENT 则无 sqlite_sequence 记录，忽略错误）
                try:
                    self._execute_sql(
                        cursor,
                        "DELETE FROM sqlite_sequence WHERE name = ?",
                        (table_name,),
                    )
                except Exception:
                    pass
                conn.commit()
                logger.info(f"清空表数据成功: {table_name}")
                return True
        except Exception as e:
            logger.error(f"清空表数据失败: {table_name} - {e}")
            return False


# 模块级单例
admin_repo = AdminRepo()

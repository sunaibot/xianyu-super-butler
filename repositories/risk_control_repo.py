"""
repositories/risk_control_repo.py
=================================
风控日志数据访问层（risk_control_logs 表）。

从 db_manager.DBManager 迁移而来：
- add_risk_control_log：新增风控日志记录
- update_risk_control_log：更新风控日志记录
- get_risk_control_logs(cookie_id, limit, offset)：获取风控日志列表（含 cookie_name 关联）
- get_risk_control_logs_count(cookie_id)：获取风控日志总数
- delete_risk_control_log(log_id)：删除单条风控日志

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, List, Optional

from loguru import logger

from .base import BaseRepo


class RiskControlRepo(BaseRepo):
    """风控日志仓储"""

    table_name = "risk_control_logs"

    # ------------------------- 写操作 -------------------------

    def add_risk_control_log(self, cookie_id: str, event_type: str = 'slider_captcha',
                           event_description: str = None, processing_result: str = None,
                           processing_status: str = 'processing', error_message: str = None) -> bool:
        """
        添加风控日志记录

        Args:
            cookie_id: Cookie ID
            event_type: 事件类型，默认为'slider_captcha'
            event_description: 事件描述
            processing_result: 处理结果
            processing_status: 处理状态 ('processing', 'success', 'failed')
            error_message: 错误信息

        Returns:
            bool: 添加成功返回True，失败返回False
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    '''
                    INSERT INTO risk_control_logs
                    (cookie_id, event_type, event_description, processing_result, processing_status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (cookie_id, event_type, event_description, processing_result, processing_status, error_message),
                )
                return True
        except Exception as e:
            logger.error(f"添加风控日志失败: {e}")
            return False

    def update_risk_control_log(self, log_id: int, processing_result: str = None,
                              processing_status: str = None, error_message: str = None) -> bool:
        """
        更新风控日志记录

        Args:
            log_id: 日志ID
            processing_result: 处理结果
            processing_status: 处理状态
            error_message: 错误信息

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                if processing_result is not None:
                    update_fields.append("processing_result = ?")
                    params.append(processing_result)

                if processing_status is not None:
                    update_fields.append("processing_status = ?")
                    params.append(processing_status)

                if error_message is not None:
                    update_fields.append("error_message = ?")
                    params.append(error_message)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(log_id)

                    sql = f"UPDATE risk_control_logs SET {', '.join(update_fields)} WHERE id = ?"
                    self._execute_sql(cur, sql, params)
                    return cur.rowcount > 0

                return False
        except Exception as e:
            logger.error(f"更新风控日志失败: {e}")
            return False

    # ------------------------- 读操作 -------------------------

    def get_risk_control_logs(
        self,
        cookie_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """获取风控日志列表（按 created_at 倒序，关联 cookies 表取 cookie_name）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                if cookie_id:
                    self._execute_sql(
                        cur,
                        """
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        WHERE r.cookie_id = ?
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (cookie_id, limit, offset),
                    )
                else:
                    self._execute_sql(
                        cur,
                        """
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (limit, offset),
                    )

                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取风控日志失败: {e}")
            return []

    def get_risk_control_logs_count(self, cookie_id: str = None) -> int:
        """获取风控日志总数"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if cookie_id:
                    self._execute_sql(
                        cur,
                        "SELECT COUNT(*) FROM risk_control_logs WHERE cookie_id = ?",
                        (cookie_id,),
                    )
                else:
                    self._execute_sql(cur, "SELECT COUNT(*) FROM risk_control_logs")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"获取风控日志数量失败: {e}")
            return 0

    def delete_risk_control_log(self, log_id: int) -> bool:
        """删除单条风控日志"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "DELETE FROM risk_control_logs WHERE id = ?",
                    (log_id,),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除风控日志失败: {e}")
            return False


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
risk_control_repo = RiskControlRepo()

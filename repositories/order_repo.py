"""
repositories/order_repo.py
============================
Order 仓储：从 DBManager 迁移而来的 Order 域数据访问。

迁移范围（首批）：
- insert_or_update_order（含 event_bus 广播）
- get_order_by_id
- delete_order
- get_recent_order_by_item_and_buyer
- get_orders_by_cookie / get_orders_by_cookies（批量，消除列表 N+1）
- get_all_orders
- update_order_address
- get_order_analytics / get_orders_for_analytics
- get_all_item_titles（item_info 表辅助方法，替代 GET /api/orders 中的内联全表扫描）

设计原则：
- 继承 BaseRepo，使用独立连接（每次新建 + with 语句自动事务）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- DBManager 对应方法将逐步委托到此处（向后兼容）
- event_bus 广播保持原行为：异步 loop 运行时 create_task，否则丢弃
"""
import asyncio
from typing import Optional, Dict, List, Any
from loguru import logger

from .base import BaseRepo


class OrderRepo(BaseRepo):
    """Order 仓储（orders 表 + item_info 辅助查询）"""

    table_name = "orders"

    # ------------------------- 写操作 -------------------------

    def insert_or_update_order(
        self,
        order_id: str,
        item_id: str = None,
        buyer_id: str = None,
        spec_name: str = None,
        spec_value: str = None,
        quantity: str = None,
        amount: str = None,
        order_status: str = None,
        cookie_id: str = None,
        is_bargain: bool = None,
        created_at: str = None,
        receiver_name: str = None,
        receiver_phone: str = None,
        receiver_address: str = None,
        system_shipped: bool = None,
        expected_version: int = None,
        chat_id: str = None,
    ) -> bool:
        """插入或更新订单信息（保留乐观锁与 event_bus 广播语义）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 校验 cookie_id 是否存在于 cookies 表
                if cookie_id:
                    self._execute_sql(cur, "SELECT id FROM cookies WHERE id = ?", (cookie_id,))
                    if not cur.fetchone():
                        logger.warning(f"Cookie ID {cookie_id} 不存在于cookies表中，拒绝插入订单 {order_id}")
                        return False

                # 检查订单是否已存在
                self._execute_sql(cur, "SELECT order_id FROM orders WHERE order_id = ?", (order_id,))
                existing = cur.fetchone()
                is_new = not existing

                if existing:
                    # 更新现有订单（按非空字段动态拼接）
                    set_clauses, params = [], []
                    field_map = [
                        (item_id, "item_id"), (buyer_id, "buyer_id"),
                        (spec_name, "spec_name"), (spec_value, "spec_value"),
                        (quantity, "quantity"), (amount, "amount"),
                        (order_status, "order_status"), (cookie_id, "cookie_id"),
                        (created_at, "created_at"),
                        (receiver_name, "receiver_name"), (receiver_phone, "receiver_phone"),
                        (receiver_address, "receiver_address"),
                    ]
                    for value, col in field_map:
                        if value is not None:
                            set_clauses.append(f"{col} = ?")
                            params.append(value)
                    if is_bargain is not None:
                        set_clauses.append("is_bargain = ?")
                        params.append(1 if is_bargain else 0)
                    if system_shipped is not None:
                        set_clauses.append("system_shipped = ?")
                        params.append(1 if system_shipped else 0)
                    if chat_id is not None:
                        set_clauses.append("chat_id = ?")
                        params.append(chat_id)

                    if set_clauses:
                        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                        set_clauses.append("version = version + 1")

                        if expected_version is not None:
                            where_clause = "order_id = ? AND version = ?"
                            params.extend([order_id, expected_version])
                        else:
                            where_clause = "order_id = ?"
                            params.append(order_id)

                        sql = f"UPDATE orders SET {', '.join(set_clauses)} WHERE {where_clause}"
                        self._execute_sql(cur, sql, tuple(params))

                        if expected_version is not None and cur.rowcount == 0:
                            logger.warning(f"订单更新失败（版本冲突）: {order_id}, expected_version={expected_version}")
                            return False

                        logger.info(f"更新订单信息: {order_id}")
                else:
                    # 插入新订单
                    if created_at:
                        self._execute_sql(
                            cur,
                            "INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value, "
                            "quantity, amount, order_status, cookie_id, is_bargain, created_at, "
                            "receiver_name, receiver_phone, receiver_address, system_shipped, chat_id) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                order_id, item_id, buyer_id, spec_name, spec_value,
                                quantity, amount, order_status or 'unknown', cookie_id,
                                1 if is_bargain else 0, created_at,
                                receiver_name, receiver_phone, receiver_address,
                                1 if system_shipped else 0, chat_id or '',
                            ),
                        )
                    else:
                        self._execute_sql(
                            cur,
                            "INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value, "
                            "quantity, amount, order_status, cookie_id, is_bargain, "
                            "receiver_name, receiver_phone, receiver_address, system_shipped, chat_id) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                order_id, item_id, buyer_id, spec_name, spec_value,
                                quantity, amount, order_status or 'unknown', cookie_id,
                                1 if is_bargain else 0,
                                receiver_name, receiver_phone, receiver_address,
                                1 if system_shipped else 0, chat_id or '',
                            ),
                        )
                    logger.info(f"插入新订单: {order_id}")

                # with 语句退出时自动 commit

                # 异步广播事件（不阻塞调用方）
                try:
                    from event_bus import event_bus
                    loop = None
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        pass
                    if is_new:
                        task = event_bus.broadcast('new_order', {
                            'order_id': order_id,
                            'item_id': item_id,
                            'buyer_id': buyer_id,
                            'status': order_status or 'pending_ship',
                            'cookie_id': cookie_id,
                        })
                        if loop and loop.is_running():
                            loop.create_task(task)
                    elif order_status:
                        task = event_bus.broadcast('order_updated', {
                            'order_id': order_id,
                            'status': order_status,
                            'cookie_id': cookie_id,
                        })
                        if loop and loop.is_running():
                            loop.create_task(task)
                except Exception:
                    pass

                return True
        except Exception as e:
            logger.error(f"插入或更新订单失败: {order_id} - {e}")
            return False

    def delete_order(self, order_id: str) -> bool:
        """删除订单"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM orders WHERE order_id = ?", (order_id,))
                if cur.rowcount > 0:
                    logger.info(f"删除订单成功: {order_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"删除订单失败: {order_id} - {e}")
            return False

    def update_order_address(self, order_id: str, receiver_address: str = None, receiver_city: str = None):
        """
        更新订单的收货地址信息

        Args:
            order_id: 订单ID
            receiver_address: 收货地址
            receiver_city: 收货城市

        Returns:
            bool: 更新是否成功
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                update_fields = []
                update_values = []

                if receiver_address is not None:
                    update_fields.append("receiver_address = ?")
                    update_values.append(receiver_address)

                if receiver_city is not None:
                    update_fields.append("receiver_city = ?")
                    update_values.append(receiver_city)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    update_values.append(order_id)

                    sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE order_id = ?"
                    self._execute_sql(cur, sql, update_values)

                    return cur.rowcount > 0

                return False

        except Exception as e:
            logger.error(f"更新订单地址失败: {order_id} - {e}")
            return False

    # ------------------------- 读操作 -------------------------

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """根据订单 ID 获取订单信息"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT order_id, item_id, buyer_id, spec_name, spec_value, "
                    "quantity, amount, order_status, cookie_id, is_bargain, "
                    "created_at, updated_at, version, chat_id "
                    "FROM orders WHERE order_id = ?",
                    (order_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0],
                    'order_id': row[0],
                    'item_id': row[1],
                    'buyer_id': row[2],
                    'spec_name': row[3],
                    'spec_value': row[4],
                    'quantity': row[5],
                    'amount': row[6],
                    'order_status': row[7],
                    'status': row[7],  # 兼容旧代码
                    'cookie_id': row[8],
                    'is_bargain': bool(row[9]) if row[9] is not None else False,
                    'created_at': row[10],
                    'updated_at': row[11],
                    'version': row[12] if len(row) > 12 else 1,
                    'chat_id': row[13] if len(row) > 13 else '',
                }
        except Exception as e:
            logger.error(f"获取订单信息失败: {order_id} - {e}")
            return None

    def get_order_status_logs(self, order_id: str) -> List[Dict[str, Any]]:
        """查询订单状态变更日志（order_status_logs 表，若表不存在返回空列表）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT status, timestamp, note FROM order_status_logs "
                    "WHERE order_id = ? ORDER BY timestamp",
                    (order_id,),
                )
                rows = cur.fetchall()
                return [
                    {"status": r[0], "timestamp": str(r[1]), "note": r[2] or ""}
                    for r in rows
                ]
        except Exception as e:
            # 表不存在等异常降级为空列表
            logger.debug(f"获取订单状态日志失败（可能表不存在）: {order_id} - {e}")
            return []

    def search_orders(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """跨字段 LIKE 搜索订单（用于全局搜索）"""
        try:
            like = f"%{keyword}%"
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT order_id, item_id, buyer_id, receiver_name, receiver_phone "
                    "FROM orders WHERE order_id LIKE ? OR item_id LIKE ? "
                    "OR buyer_id LIKE ? OR receiver_name LIKE ? OR receiver_phone LIKE ? "
                    "LIMIT ?",
                    (like, like, like, like, like, limit),
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"搜索订单失败: {e}")
            return []

    def get_recent_order_by_item_and_buyer(self, item_id: str, buyer_id: str) -> Optional[Dict[str, Any]]:
        """根据商品ID和买家ID获取最近的订单"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT order_id, item_id, buyer_id, spec_name, spec_value, "
                    "quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at "
                    "FROM orders WHERE item_id = ? AND buyer_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (item_id, buyer_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0],
                    'order_id': row[0],
                    'item_id': row[1],
                    'buyer_id': row[2],
                    'spec_name': row[3],
                    'spec_value': row[4],
                    'quantity': row[5],
                    'amount': row[6],
                    'order_status': row[7],
                    'cookie_id': row[8],
                    'is_bargain': bool(row[9]) if row[9] is not None else False,
                    'created_at': row[10],
                    'updated_at': row[11],
                }
        except Exception as e:
            logger.error(f"获取订单信息失败: item_id={item_id}, buyer_id={buyer_id} - {e}")
            return None

    def get_orders_by_cookie(self, cookie_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """根据 Cookie ID 获取订单列表"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT order_id, item_id, buyer_id, spec_name, spec_value, "
                    "quantity, amount, order_status, is_bargain, created_at, updated_at, "
                    "receiver_name, receiver_phone, receiver_address "
                    "FROM orders WHERE cookie_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (cookie_id, limit),
                )
                return [
                    {
                        'id': row[0],
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'status': row[7],
                        'is_bargain': bool(row[8]) if row[8] is not None else False,
                        'created_at': row[9],
                        'updated_at': row[10],
                        'receiver_name': row[11],
                        'receiver_phone': row[12],
                        'receiver_address': row[13],
                    }
                    for row in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"获取Cookie订单列表失败: {cookie_id} - {e}")
            return []

    def get_orders_by_cookies(self, cookie_ids, limit_per_cookie: int = 1000) -> List[Dict[str, Any]]:
        """批量获取多个 Cookie 的订单（一次 IN 查询，消除列表接口 N+1）。

        Args:
            cookie_ids: 可迭代的 cookie_id 集合
            limit_per_cookie: 每个 cookie 最多返回的订单数

        Returns:
            list[dict]，每个订单附带 cookie_id 字段。
        """
        cookie_ids = list(cookie_ids)
        if not cookie_ids:
            return []
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                placeholders = ','.join('?' * len(cookie_ids))
                self._execute_sql(
                    cur,
                    f"SELECT order_id, item_id, buyer_id, spec_name, spec_value, "
                    f"quantity, amount, order_status, is_bargain, created_at, updated_at, "
                    f"receiver_name, receiver_phone, receiver_address, cookie_id "
                    f"FROM orders WHERE cookie_id IN ({placeholders}) "
                    f"ORDER BY created_at DESC",
                    cookie_ids,
                )
                orders = []
                per_cookie_count: Dict[str, int] = {}
                for row in cur.fetchall():
                    cid = row[14]
                    if per_cookie_count.get(cid, 0) >= limit_per_cookie:
                        continue
                    per_cookie_count[cid] = per_cookie_count.get(cid, 0) + 1
                    orders.append({
                        'id': row[0],
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'status': row[7],
                        'is_bargain': bool(row[8]) if row[8] is not None else False,
                        'created_at': row[9],
                        'updated_at': row[10],
                        'receiver_name': row[11],
                        'receiver_phone': row[12],
                        'receiver_address': row[13],
                        'cookie_id': cid,
                    })
                return orders
        except Exception as e:
            logger.error(f"批量获取订单失败: {e}")
            return []

    def get_all_orders(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取所有订单列表（按创建时间倒序）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT order_id, item_id, buyer_id, spec_name, spec_value, "
                    "quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at "
                    "FROM orders ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                return [
                    {
                        'id': row[0],
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'status': row[7],
                        'cookie_id': row[8],
                        'is_bargain': bool(row[9]) if row[9] is not None else False,
                        'created_at': row[10],
                        'updated_at': row[11],
                    }
                    for row in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"获取所有订单列表失败: {e}")
            return []

    # ------------------------- 分析统计 -------------------------

    def get_order_analytics(self, start_date: str = None, end_date: str = None, user_id: int = None, include_statuses: list = None):
        """
        获取订单分析数据

        Args:
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            user_id: 用户ID (可选)
            include_statuses: 要包含的订单状态列表 (可选，如果指定则只统计这些状态)

        Returns:
            包含订单分析数据的字典
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 构建WHERE条件
                where_conditions = []
                params = []

                if start_date:
                    where_conditions.append("DATE(created_at) >= ?")
                    params.append(start_date)

                if end_date:
                    where_conditions.append("DATE(created_at) <= ?")
                    params.append(end_date)

                # 关联cookies表以过滤user_id
                if user_id is not None:
                    where_conditions.append("EXISTS (SELECT 1 FROM cookies WHERE cookies.id = orders.cookie_id AND cookies.user_id = ?)")
                    params.append(user_id)

                # 只包含指定状态（小写形式）
                if include_statuses:
                    placeholders = ','.join(['?' for _ in include_statuses])
                    where_conditions.append(f"order_status IN ({placeholders})")
                    params.extend(include_statuses)

                where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

                # 1. 总收益统计（估值，实际会扣税等）
                self._execute_sql(cur, f"""
                    SELECT
                        COUNT(DISTINCT order_id) as total_orders,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount,
                        AVG(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as avg_amount,
                        COUNT(DISTINCT buyer_id) as unique_buyers,
                        COUNT(DISTINCT item_id) as unique_items
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                """, params)

                row = cur.fetchone()
                revenue_stats = {
                    'total_orders': row[0] or 0,
                    'total_amount': round(row[1] or 0, 2),
                    'avg_amount': round(row[2] or 0, 2),
                    'unique_buyers': row[3] or 0,
                    'unique_items': row[4] or 0
                } if row else {}

                # 2. 按日期统计订单量和收益
                self._execute_sql(cur, f"""
                    SELECT
                        DATE(created_at) as date,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as daily_amount
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    LIMIT 30
                """, params)

                daily_stats = []
                for row in cur.fetchall():
                    daily_stats.append({
                        'date': row[0],
                        'order_count': row[1],
                        'amount': round(row[2] or 0, 2)
                    })

                # 3. 按状态统计订单
                self._execute_sql(cur, f"""
                    SELECT
                        order_status,
                        COUNT(DISTINCT order_id) as count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as amount
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY order_status
                    ORDER BY count DESC
                """, params)

                status_stats = []
                for row in cur.fetchall():
                    status_stats.append({
                        'status': row[0] or 'unknown',
                        'count': row[1],
                        'amount': round(row[2] or 0, 2)
                    })

                # 4. 按城市统计地区分布（如果有收货城市数据）
                self._execute_sql(cur, f"""
                    SELECT
                        receiver_city,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount
                    FROM orders
                    {where_clause}
                    AND receiver_city IS NOT NULL AND receiver_city != ''
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY receiver_city
                    ORDER BY order_count DESC
                    LIMIT 50
                """, params)

                city_stats = []
                for row in cur.fetchall():
                    city_stats.append({
                        'city': row[0],
                        'order_count': row[1],
                        'total_amount': round(row[2] or 0, 2)
                    })

                # 5. 商品排行（按订单量）
                self._execute_sql(cur, f"""
                    SELECT
                        item_id,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount,
                        AVG(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as avg_amount
                    FROM orders
                    {where_clause}
                    AND item_id IS NOT NULL AND item_id != ''
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY item_id
                    ORDER BY order_count DESC
                    LIMIT 20
                """, params)

                item_stats = []
                for row in cur.fetchall():
                    item_stats.append({
                        'item_id': row[0],
                        'order_count': row[1],
                        'total_amount': round(row[2] or 0, 2),
                        'avg_amount': round(row[3] or 0, 2)
                    })

                return {
                    'revenue_stats': revenue_stats,
                    'daily_stats': daily_stats,
                    'status_stats': status_stats,
                    'city_stats': city_stats,
                    'item_stats': item_stats
                }

        except Exception as e:
            logger.error(f"获取订单分析数据失败: {e}")
            return {'error': str(e)}

    def get_orders_for_analytics(self, start_date: str = None, end_date: str = None,
                                  user_id: int = None, include_statuses: list = None):
        """
        获取用于分析的订单列表

        Args:
            start_date: 开始日期
            end_date: 结束日期
            user_id: 用户ID
            include_statuses: 要包含的订单状态列表（如果指定则只返回这些状态的订单）

        Returns:
            订单列表
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 构建WHERE条件
                where_conditions = []
                params = []

                if start_date:
                    where_conditions.append("DATE(created_at) >= ?")
                    params.append(start_date)

                if end_date:
                    where_conditions.append("DATE(created_at) <= ?")
                    params.append(end_date)

                # 关联cookies表以过滤user_id
                if user_id is not None:
                    where_conditions.append("EXISTS (SELECT 1 FROM cookies WHERE cookies.id = orders.cookie_id AND cookies.user_id = ?)")
                    params.append(user_id)

                # 只包含指定状态
                if include_statuses:
                    placeholders = ','.join(['?' for _ in include_statuses])
                    where_conditions.append(f"order_status IN ({placeholders})")
                    params.extend(include_statuses)

                where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

                self._execute_sql(cur, f"""
                    SELECT
                        order_id,
                        item_id,
                        buyer_id,
                        amount,
                        order_status,
                        spec_name,
                        spec_value,
                        quantity,
                        created_at,
                        receiver_city
                    FROM orders
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT 1000
                """, params)

                orders = []
                for row in cur.fetchall():
                    orders.append({
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'amount': row[3],
                        'order_status': row[4],
                        'spec_name': row[5],
                        'spec_value': row[6],
                        'quantity': row[7],
                        'created_at': row[8],
                        'receiver_city': row[9]
                    })

                return orders

        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            return []

    # ------------------------- item_info 辅助 -------------------------

    def get_all_item_titles(self) -> Dict[str, str]:
        """获取所有 item_id → item_title 的映射（一次全表读取，消除逐订单 N+1）。

        注意：item_info 表本应归属 ItemRepo，但当前订单列表接口强依赖此映射，
        暂置于 OrderRepo。后续 ItemRepo 建立后再行迁移。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT item_id, item_title FROM item_info")
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"获取商品标题映射失败: {e}")
            return {}


# 模块级单例（与 db_manager 单例等价的访问方式）
order_repo = OrderRepo()


__all__ = ["OrderRepo", "order_repo"]

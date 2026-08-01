"""
repositories/item_repo.py
=========================
商品（item_info 表）+ 商品回复（item_replay 表）数据访问层。

从 db_manager.DBManager 迁移而来：
- item_info 表：save_item_basic_info / save_item_info / get_item_info /
  update_item_detail / update_item_title_only / update_item_multi_spec_status /
  update_item_multi_quantity_delivery_status / batch_save_item_basic_info /
  delete_item_info / batch_delete_item_info / get_items_by_cookie / get_all_items /
  get_item_multi_spec_status / get_item_multi_quantity_delivery_status /
  get_all_item_titles（从 order_repo 迁入，item_info 表辅助查询）
- item_replay 表：get_item_replay / get_item_reply / update_item_reply /
  get_itemReplays_by_cookie / delete_item_reply / batch_delete_item_replies

新增方法（从 reply_server.py 路由内联 SQL 抽取）：
- get_item_list_by_cookie：商品摘要列表（原 GET /items/{cid} 内联 SQL）
- create_item：新增商品 INSERT OR IGNORE（原 POST /items/{cookie_id} 内联 SQL）

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- item_detail 字段在 DB 中为 JSON 字符串，读取时附加 item_detail_parsed 字段
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
import json
from typing import Any, Dict, List, Optional

from loguru import logger

from .base import BaseRepo


class ItemRepo(BaseRepo):
    """商品仓储（item_info + item_replay）"""

    table_name = "item_info"

    # ------------------------- 内部工具 -------------------------

    @staticmethod
    def _parse_item_detail(item_info: dict) -> dict:
        """解析 item_detail JSON 字段，附加 item_detail_parsed 键"""
        if item_info.get('item_detail'):
            try:
                item_info['item_detail_parsed'] = json.loads(item_info['item_detail'])
            except Exception:
                item_info['item_detail_parsed'] = {}
        return item_info

    # ==================== item_info 表 ====================
    # ------------------------- 写操作 -------------------------

    def save_item_basic_info(self, cookie_id: str, item_id: str, item_title: str = None,
                            item_description: str = None, item_category: str = None,
                            item_price: str = None, item_detail: str = None,
                            item_image: str = None) -> bool:
        """保存或更新商品基本信息，使用原子操作避免并发问题

        采用 INSERT OR IGNORE + 条件 UPDATE 模式：仅当现有字段为空时才填充新值，
        避免覆盖已有数据。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 首先尝试插入，如果已存在则忽略
                self._execute_sql(
                    cur,
                    "INSERT OR IGNORE INTO item_info (cookie_id, item_id, item_title, item_description, "
                    "item_category, item_price, item_detail, item_image, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (cookie_id, item_id, item_title or '', item_description or '',
                     item_category or '', item_price or '', item_detail or '', item_image or ''),
                )

                # 如果是新插入的记录，直接返回成功
                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"新增商品基本信息: {item_id} - {item_title}")
                    return True

                # 记录已存在，使用原子UPDATE操作，只更新非空字段且不覆盖现有非空值
                update_parts = []
                params: list = []

                if item_title:
                    update_parts.append("item_title = CASE WHEN (item_title IS NULL OR item_title = '') THEN ? ELSE item_title END")
                    params.append(item_title)

                if item_description:
                    update_parts.append("item_description = CASE WHEN (item_description IS NULL OR item_description = '') THEN ? ELSE item_description END")
                    params.append(item_description)

                if item_category:
                    update_parts.append("item_category = CASE WHEN (item_category IS NULL OR item_category = '') THEN ? ELSE item_category END")
                    params.append(item_category)

                if item_price:
                    update_parts.append("item_price = CASE WHEN (item_price IS NULL OR item_price = '') THEN ? ELSE item_price END")
                    params.append(item_price)

                # 对于item_detail，只有在现有值为空时才更新
                if item_detail:
                    update_parts.append("item_detail = CASE WHEN (item_detail IS NULL OR item_detail = '' OR TRIM(item_detail) = '') THEN ? ELSE item_detail END")
                    params.append(item_detail)

                # 对于item_image，只有在现有值为空时才更新
                if item_image:
                    update_parts.append("item_image = CASE WHEN (item_image IS NULL OR item_image = '') THEN ? ELSE item_image END")
                    params.append(item_image)

                if update_parts:
                    update_parts.append("updated_at = CURRENT_TIMESTAMP")
                    params.extend([cookie_id, item_id])

                    sql = f"UPDATE item_info SET {', '.join(update_parts)} WHERE cookie_id = ? AND item_id = ?"
                    self._execute_sql(cur, sql, params)

                    if cur.rowcount > 0:
                        logger.info(f"更新商品基本信息: {item_id} - {item_title}")
                    else:
                        logger.debug(f"商品信息无需更新: {item_id}")

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"保存商品基本信息失败: {e}")
            return False

    def save_item_info(self, cookie_id: str, item_id: str, item_data: Any = None) -> bool:
        """保存或更新商品信息

        item_data 可以是字符串或字典；为空或字典无标题时跳过保存。
        已存在记录时覆盖 item_detail（及字典模式下的标题等字段）。
        """
        try:
            # 验证：如果只有商品ID，没有商品详情数据，则不插入数据库
            if not item_data:
                logger.debug(f"跳过保存商品信息：缺少商品详情数据 - {item_id}")
                return False

            # 如果是字典类型，检查是否有标题信息
            if isinstance(item_data, dict):
                title = item_data.get('title', '').strip()
                if not title:
                    logger.debug(f"跳过保存商品信息：缺少商品标题 - {item_id}")
                    return False

            # 如果是字符串类型，检查是否为空
            if isinstance(item_data, str) and not item_data.strip():
                logger.debug(f"跳过保存商品信息：商品详情为空 - {item_id}")
                return False

            with self.get_connection() as conn:
                cur = conn.cursor()

                # 检查商品是否已存在
                self._execute_sql(
                    cur,
                    "SELECT id, item_detail FROM item_info WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )
                existing = cur.fetchone()

                if existing:
                    # 如果传入的商品详情有值，则用最新数据覆盖
                    if item_data is not None and item_data:
                        if isinstance(item_data, str):
                            self._execute_sql(
                                cur,
                                "UPDATE item_info SET item_detail = ?, updated_at = CURRENT_TIMESTAMP "
                                "WHERE cookie_id = ? AND item_id = ?",
                                (item_data, cookie_id, item_id),
                            )
                        else:
                            self._execute_sql(
                                cur,
                                "UPDATE item_info SET item_title = ?, item_description = ?, item_category = ?, "
                                "item_price = ?, item_detail = ?, updated_at = CURRENT_TIMESTAMP "
                                "WHERE cookie_id = ? AND item_id = ?",
                                (
                                    item_data.get('title', ''),
                                    item_data.get('description', ''),
                                    item_data.get('category', ''),
                                    item_data.get('price', ''),
                                    json.dumps(item_data, ensure_ascii=False),
                                    cookie_id, item_id,
                                ),
                            )
                        logger.info(f"更新商品信息（覆盖）: {item_id}")
                    else:
                        # 如果商品详情没有数据，则不更新，只记录存在
                        logger.debug(f"商品信息已存在，无新数据，跳过更新: {item_id}")
                        return True
                else:
                    # 新增商品信息
                    if isinstance(item_data, str):
                        self._execute_sql(
                            cur,
                            "INSERT INTO item_info (cookie_id, item_id, item_detail) VALUES (?, ?, ?)",
                            (cookie_id, item_id, item_data),
                        )
                    else:
                        self._execute_sql(
                            cur,
                            "INSERT INTO item_info (cookie_id, item_id, item_title, item_description, "
                            "item_category, item_price, item_detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                cookie_id, item_id,
                                item_data.get('title', '') if item_data else '',
                                item_data.get('description', '') if item_data else '',
                                item_data.get('category', '') if item_data else '',
                                item_data.get('price', '') if item_data else '',
                                json.dumps(item_data, ensure_ascii=False) if item_data else '',
                            ),
                        )
                    logger.info(f"新增商品信息: {item_id}")

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"保存商品信息失败: {e}")
            return False

    def update_item_detail(self, cookie_id: str, item_id: str, item_detail: str) -> bool:
        """更新商品详情（不覆盖商品标题等基本信息）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE item_info SET item_detail = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE cookie_id = ? AND item_id = ?",
                    (item_detail, cookie_id, item_id),
                )

                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新商品详情成功: {item_id}")
                    return True
                else:
                    logger.warning(f"未找到要更新的商品: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品详情失败: {e}")
            return False

    def update_item_title_only(self, cookie_id: str, item_id: str, item_title: str) -> bool:
        """仅更新商品标题（并发安全）

        使用 INSERT ... ON CONFLICT DO UPDATE 确保记录存在，但只更新标题字段。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "INSERT INTO item_info (cookie_id, item_id, item_title, item_description, "
                    "item_category, item_price, item_detail, created_at, updated_at) "
                    "VALUES (?, ?, ?, "
                    "COALESCE((SELECT item_description FROM item_info WHERE cookie_id = ? AND item_id = ?), ''), "
                    "COALESCE((SELECT item_category FROM item_info WHERE cookie_id = ? AND item_id = ?), ''), "
                    "COALESCE((SELECT item_price FROM item_info WHERE cookie_id = ? AND item_id = ?), ''), "
                    "COALESCE((SELECT item_detail FROM item_info WHERE cookie_id = ? AND item_id = ?), ''), "
                    "COALESCE((SELECT created_at FROM item_info WHERE cookie_id = ? AND item_id = ?), CURRENT_TIMESTAMP), "
                    "CURRENT_TIMESTAMP) "
                    "ON CONFLICT(cookie_id, item_id) DO UPDATE SET "
                    "item_title = excluded.item_title, updated_at = CURRENT_TIMESTAMP",
                    (cookie_id, item_id, item_title,
                     cookie_id, item_id, cookie_id, item_id, cookie_id, item_id,
                     cookie_id, item_id, cookie_id, item_id),
                )

                conn.commit()
                logger.info(f"更新商品标题成功: {item_id} - {item_title}")
                return True

        except Exception as e:
            logger.error(f"更新商品标题失败: {e}")
            return False

    def update_item_multi_spec_status(self, cookie_id: str, item_id: str, is_multi_spec: bool) -> bool:
        """更新商品的多规格状态"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE item_info SET is_multi_spec = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE cookie_id = ? AND item_id = ?",
                    (is_multi_spec, cookie_id, item_id),
                )

                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新商品多规格状态成功: {item_id} -> {is_multi_spec}")
                    return True
                else:
                    logger.warning(f"商品不存在，无法更新多规格状态: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品多规格状态失败: {e}")
            return False

    def update_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str,
                                                    multi_quantity_delivery: bool) -> bool:
        """更新商品的多数量发货状态"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE item_info SET multi_quantity_delivery = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE cookie_id = ? AND item_id = ?",
                    (multi_quantity_delivery, cookie_id, item_id),
                )

                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新商品多数量发货状态成功: {item_id} -> {multi_quantity_delivery}")
                    return True
                else:
                    logger.warning(f"未找到要更新的商品: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品多数量发货状态失败: {e}")
            return False

    def batch_save_item_basic_info(self, items_data: list) -> int:
        """批量保存商品基本信息（并发安全）

        使用 INSERT OR IGNORE + 条件 UPDATE 模式，逐条处理但共享同一事务。
        返回成功保存的商品数量。
        """
        if not items_data:
            return 0

        success_count = 0
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                for item_data in items_data:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')
                        item_title = item_data.get('item_title', '')
                        item_description = item_data.get('item_description', '')
                        item_category = item_data.get('item_category', '')
                        item_price = item_data.get('item_price', '')
                        item_detail = item_data.get('item_detail', '')
                        item_image = item_data.get('item_image', '')

                        if not cookie_id or not item_id:
                            continue

                        # 验证：如果没有商品标题，则跳过保存
                        if not item_title or not item_title.strip():
                            logger.debug(f"跳过批量保存商品信息：缺少商品标题 - {item_id}")
                            continue

                        # 使用 INSERT OR IGNORE + UPDATE 模式
                        self._execute_sql(
                            cur,
                            "INSERT OR IGNORE INTO item_info (cookie_id, item_id, item_title, item_description, "
                            "item_category, item_price, item_detail, item_image, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                            (cookie_id, item_id, item_title, item_description,
                             item_category, item_price, item_detail, item_image),
                        )

                        if cur.rowcount == 0:
                            # 记录已存在，进行条件更新
                            self._execute_sql(
                                cur,
                                "UPDATE item_info SET "
                                "item_title = CASE WHEN (item_title IS NULL OR item_title = '') AND ? != '' THEN ? ELSE item_title END, "
                                "item_description = CASE WHEN (item_description IS NULL OR item_description = '') AND ? != '' THEN ? ELSE item_description END, "
                                "item_category = CASE WHEN (item_category IS NULL OR item_category = '') AND ? != '' THEN ? ELSE item_category END, "
                                "item_price = CASE WHEN (item_price IS NULL OR item_price = '') AND ? != '' THEN ? ELSE item_price END, "
                                "item_detail = CASE WHEN (item_detail IS NULL OR item_detail = '' OR TRIM(item_detail) = '') AND ? != '' THEN ? ELSE item_detail END, "
                                "item_image = CASE WHEN (item_image IS NULL OR item_image = '') AND ? != '' THEN ? ELSE item_image END, "
                                "updated_at = CURRENT_TIMESTAMP "
                                "WHERE cookie_id = ? AND item_id = ?",
                                (
                                    item_title, item_title,
                                    item_description, item_description,
                                    item_category, item_category,
                                    item_price, item_price,
                                    item_detail, item_detail,
                                    item_image, item_image,
                                    cookie_id, item_id,
                                ),
                            )

                        success_count += 1

                    except Exception as item_e:
                        logger.warning(f"批量保存单个商品失败 {item_data.get('item_id', 'unknown')}: {item_e}")
                        continue

                conn.commit()
                logger.info(f"批量保存商品信息完成: {success_count}/{len(items_data)} 个商品")
                return success_count

        except Exception as e:
            logger.error(f"批量保存商品信息失败: {e}")
            return success_count

    def get_item_by_id(self, item_id: str) -> Optional[Dict]:
        """按 item_id 查询商品（不限 cookie_id）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT * FROM item_info WHERE item_id = ? LIMIT 1",
                    (item_id,),
                )
                row = cur.fetchone()
                if row:
                    return self._parse_item_detail(dict(row))
                return None
        except Exception as e:
            logger.error(f"按 item_id 查询商品失败: {e}")
            return None

    def delete_item_info(self, cookie_id: str, item_id: str) -> bool:
        """删除商品信息"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "DELETE FROM item_info WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )

                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除商品信息成功: {cookie_id} - {item_id}")
                    return True
                else:
                    logger.warning(f"未找到要删除的商品信息: {cookie_id} - {item_id}")
                    return False

        except Exception as e:
            logger.error(f"删除商品信息失败: {e}")
            return False

    def batch_delete_item_info(self, items_to_delete: list) -> int:
        """批量删除商品信息

        每个元素包含 cookie_id 和 item_id；返回成功删除的数量。
        """
        if not items_to_delete:
            return 0

        success_count = 0
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                for item_data in items_to_delete:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')

                        if not cookie_id or not item_id:
                            continue

                        self._execute_sql(
                            cur,
                            "DELETE FROM item_info WHERE cookie_id = ? AND item_id = ?",
                            (cookie_id, item_id),
                        )

                        if cur.rowcount > 0:
                            success_count += 1
                            logger.debug(f"删除商品信息: {cookie_id} - {item_id}")

                    except Exception as item_e:
                        logger.warning(f"删除单个商品失败 {item_data.get('item_id', 'unknown')}: {item_e}")
                        continue

                conn.commit()
                logger.info(f"批量删除商品信息完成: {success_count}/{len(items_to_delete)} 个商品")
                return success_count

        except Exception as e:
            logger.error(f"批量删除商品信息失败: {e}")
            return success_count

    def create_item(self, cookie_id: str, item_id: str, item_title: str = '',
                    item_price: str = '', item_image: str = '',
                    is_multi_spec: bool = False, multi_quantity_delivery: bool = False) -> bool:
        """新增商品（INSERT OR IGNORE）；返回是否新增成功（已存在返回 False）

        从 reply_server.py 的 POST /items/{cookie_id} 路由内联 SQL 抽取。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "INSERT OR IGNORE INTO item_info "
                    "(cookie_id, item_id, item_title, item_price, item_image, is_multi_spec, multi_quantity_delivery) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cookie_id, item_id, item_title, item_price, item_image,
                     1 if is_multi_spec else 0, 1 if multi_quantity_delivery else 0),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"新增商品失败: {e}")
            raise

    # ------------------------- 读操作 -------------------------

    def get_item_info(self, cookie_id: str, item_id: str) -> Optional[Dict]:
        """获取商品信息（含 item_detail_parsed 解析字段）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT * FROM item_info WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )

                row = cur.fetchone()
                if row:
                    item_info = dict(row)
                    self._parse_item_detail(item_info)
                    logger.info(f"item_info: {item_info}")
                    return item_info
                return None

        except Exception as e:
            logger.error(f"获取商品信息失败: {e}")
            return None

    def get_items_by_cookie(self, cookie_id: str) -> List[Dict]:
        """获取指定 Cookie 的所有商品信息（按 updated_at 倒序，含 item_detail_parsed）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT * FROM item_info WHERE cookie_id = ? ORDER BY updated_at DESC",
                    (cookie_id,),
                )

                items = []
                for row in cur.fetchall():
                    item_info = dict(row)
                    self._parse_item_detail(item_info)
                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取Cookie商品信息失败: {e}")
            return []

    def get_all_items(self) -> List[Dict]:
        """获取所有商品信息（按 updated_at 倒序，含 item_detail_parsed）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT * FROM item_info ORDER BY updated_at DESC")

                items = []
                for row in cur.fetchall():
                    item_info = dict(row)
                    self._parse_item_detail(item_info)
                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取所有商品信息失败: {e}")
            return []

    def get_item_multi_spec_status(self, cookie_id: str, item_id: str) -> bool:
        """获取商品的多规格状态"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT is_multi_spec FROM item_info WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )

                row = cur.fetchone()
                if row:
                    return bool(row[0]) if row[0] is not None else False
                return False

        except Exception as e:
            logger.error(f"获取商品多规格状态失败: {e}")
            return False

    def get_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str) -> bool:
        """获取商品的多数量发货状态"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT multi_quantity_delivery FROM item_info WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )

                row = cur.fetchone()
                if row:
                    return bool(row[0]) if row[0] is not None else False
                return False

        except Exception as e:
            logger.error(f"获取商品多数量发货状态失败: {e}")
            return False

    def get_all_item_titles(self) -> Dict[str, str]:
        """获取所有 item_id → item_title 的映射（一次全表读取）

        注意：此方法原置于 order_repo，因 item_info 表归属 ItemRepo，现迁入此处。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT item_id, item_title FROM item_info")
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"获取商品标题映射失败: {e}")
            return {}

    def get_item_list_by_cookie(self, cookie_id: str) -> List[Dict]:
        """获取指定 Cookie 的商品摘要列表（item_id / item_title / item_price / created_at）

        从 reply_server.py 的 GET /items/{cid} 路由内联 SQL 抽取。
        按 created_at 倒序排列；空标题/价格附加展示兜底值。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT item_id, item_title, item_price, created_at "
                    "FROM item_info WHERE cookie_id = ? ORDER BY created_at DESC",
                    (cookie_id,),
                )
                return [
                    {
                        'item_id': row[0],
                        'item_title': row[1] or '未知商品',
                        'item_price': row[2] or '价格未知',
                        'created_at': row[3],
                    }
                    for row in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"获取商品列表失败: {e}")
            return []

    def search_items(self, keyword: str, limit: int = 10) -> List[Dict]:
        """跨字段 LIKE 搜索商品（用于全局搜索）"""
        try:
            like = f"%{keyword}%"
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT item_id, title FROM item_info "
                    "WHERE item_id LIKE ? OR title LIKE ? LIMIT ?",
                    (like, like, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"搜索商品失败: {e}")
            return []

    # ==================== item_replay 表 ====================

    def get_item_replay(self, item_id: str) -> Optional[Dict[str, Any]]:
        """根据商品ID获取商品回复信息（仅按 item_id 查询，返回统一格式）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT reply_content FROM item_replay WHERE item_id = ?",
                    (item_id,),
                )

                row = cur.fetchone()
                if row:
                    (reply_content,) = row
                    return {
                        'reply_content': reply_content or ''
                    }
                return None
        except Exception as e:
            logger.error(f"获取商品回复失败: {e}")
            return None

    def get_item_reply(self, cookie_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """获取指定账号和商品的回复内容（含创建/更新时间）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT reply_content, created_at, updated_at "
                    "FROM item_replay WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )

                row = cur.fetchone()
                if row:
                    return {
                        'reply_content': row[0] or '',
                        'created_at': row[1],
                        'updated_at': row[2]
                    }
                return None
        except Exception as e:
            logger.error(f"获取指定商品回复失败: {e}")
            return None

    def update_item_reply(self, cookie_id: str, item_id: str, reply_content: str) -> bool:
        """更新指定 cookie 和 item 的回复内容（upsert：不存在则插入）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE item_replay SET reply_content = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE cookie_id = ? AND item_id = ?",
                    (reply_content, cookie_id, item_id),
                )

                if cur.rowcount == 0:
                    # 如果没更新到，说明该条记录不存在，插入新记录
                    self._execute_sql(
                        cur,
                        "INSERT INTO item_replay (item_id, cookie_id, reply_content, created_at, updated_at) "
                        "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (item_id, cookie_id, reply_content),
                    )

                conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新商品回复失败: {e}")
            return False

    def get_itemReplays_by_cookie(self, cookie_id: str) -> List[Dict]:
        """获取指定 Cookie 的所有商品回复（LEFT JOIN item_info 获取标题/详情）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT r.item_id, r.cookie_id, r.reply_content, r.created_at, r.updated_at, "
                    "i.item_title, i.item_detail "
                    "FROM item_replay r "
                    "LEFT JOIN item_info i ON i.item_id = r.item_id "
                    "WHERE r.cookie_id = ? "
                    "ORDER BY r.updated_at DESC",
                    (cookie_id,),
                )

                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"获取Cookie商品信息失败: {e}")
            return []

    def delete_item_reply(self, cookie_id: str, item_id: str) -> bool:
        """删除指定 cookie_id 和 item_id 的商品回复"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "DELETE FROM item_replay WHERE cookie_id = ? AND item_id = ?",
                    (cookie_id, item_id),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除商品回复失败: {e}")
            return False

    def batch_delete_item_replies(self, items: List[Dict[str, str]]) -> Dict[str, int]:
        """批量删除商品回复

        Args:
            items: List[Dict]，每个字典包含 cookie_id 和 item_id

        Returns:
            Dict[str, int]：{"success_count": N, "failed_count": M}
        """
        success_count = 0
        failed_count = 0

        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                for item in items:
                    cookie_id = item.get('cookie_id')
                    item_id = item.get('item_id')
                    if not cookie_id or not item_id:
                        failed_count += 1
                        continue
                    self._execute_sql(
                        cur,
                        "DELETE FROM item_replay WHERE cookie_id = ? AND item_id = ?",
                        (cookie_id, item_id),
                    )
                    if cur.rowcount > 0:
                        success_count += 1
                    else:
                        failed_count += 1
                conn.commit()
        except Exception as e:
            logger.error(f"批量删除商品回复失败: {e}")
            # 整体失败则视为全部失败
            return {"success_count": 0, "failed_count": len(items)}

        return {"success_count": success_count, "failed_count": failed_count}


# 模块级单例（与 cookie_repo / order_repo / card_repo 一致）
item_repo = ItemRepo()

"""
repositories/delivery_rule_repo.py
==================================
发货规则（delivery_rules 表）数据访问层。

从 db_manager.DBManager 迁移而来：
- create / get_all / get_by_id / update / delete
- get_delivery_rules_by_keyword            关键字模糊匹配（核心匹配逻辑）
- get_delivery_rules_by_keyword_and_spec   多规格优先匹配 + 兜底
- increment_delivery_times                 发货次数自增

设计要点：
- delivery_rules 与 cards 通过 card_id 关联，查询时 LEFT JOIN 获取卡券信息
- 支持用户隔离（user_id 过滤）
- 关键字匹配采用双向 LIKE：商品内容包含关键字 OR 关键字包含商品内容
- 多规格匹配优先（is_multi_spec=1 且 spec 完全匹配），无则回退普通匹配
"""
import json
from typing import Any, List, Optional

from loguru import logger

from .base import BaseRepo


def _parse_api_config(raw: Any) -> Any:
    if not raw:
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


class DeliveryRuleRepo(BaseRepo):
    """发货规则仓储"""

    table_name = "delivery_rules"

    # 列表查询字段（含 JOIN cards 的卡券信息）
    _LIST_COLUMNS = (
        "dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled, "
        "dr.description, dr.delivery_times, dr.created_at, dr.updated_at, "
        "c.name as card_name, c.type as card_type, c.is_multi_spec, c.spec_name, c.spec_value"
    )

    # 关键字匹配查询字段（含完整卡券内容，用于发货时构造响应）
    _MATCH_COLUMNS = (
        "dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled, "
        "dr.description, dr.delivery_times, "
        "c.name as card_name, c.type as card_type, c.api_config, "
        "c.text_content, c.data_content, c.image_url, c.enabled as card_enabled, "
        "c.description as card_description, c.delay_seconds as card_delay_seconds, "
        "c.is_multi_spec, c.spec_name, c.spec_value"
    )

    @staticmethod
    def _list_row_to_dict(row) -> dict:
        return {
            'id': row[0],
            'keyword': row[1],
            'card_id': row[2],
            'delivery_count': row[3],
            'enabled': bool(row[4]),
            'description': row[5],
            'delivery_times': row[6],
            'created_at': row[7],
            'updated_at': row[8],
            'card_name': row[9],
            'card_type': row[10],
            'is_multi_spec': bool(row[11]) if row[11] is not None else False,
            'spec_name': row[12],
            'spec_value': row[13],
        }

    @staticmethod
    def _match_row_to_dict(row) -> dict:
        return {
            'id': row[0],
            'keyword': row[1],
            'card_id': row[2],
            'delivery_count': row[3],
            'enabled': bool(row[4]),
            'description': row[5],
            'delivery_times': row[6] or 0,
            'card_name': row[7],
            'card_type': row[8],
            'api_config': _parse_api_config(row[9]),
            'text_content': row[10],
            'data_content': row[11],
            'image_url': row[12],
            'card_enabled': bool(row[13]),
            'card_description': row[14],
            'card_delay_seconds': row[15] or 0,
            'is_multi_spec': bool(row[16]) if row[16] is not None else False,
            'spec_name': row[17],
            'spec_value': row[18],
        }

    # ------------------------- 写操作 -------------------------

    def create_delivery_rule(self, keyword: str, card_id: int, delivery_count: int = 1,
                             enabled: bool = True, description: str = None, user_id: int = None) -> int:
        """创建发货规则；返回新规则 ID"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "INSERT INTO delivery_rules (keyword, card_id, delivery_count, enabled, description, user_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (keyword, card_id, delivery_count, enabled, description, user_id),
                )
                conn.commit()
                rule_id = cur.lastrowid
                logger.info(f"创建发货规则成功: {keyword} -> 卡券ID {card_id} (规则ID: {rule_id})")
                return rule_id
        except Exception as e:
            logger.error(f"创建发货规则失败: {e}")
            raise

    def update_delivery_rule(self, rule_id: int, keyword: str = None, card_id: int = None,
                             delivery_count: int = None, enabled: bool = None,
                             description: str = None, user_id: int = None) -> bool:
        """按字段更新发货规则（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                update_fields = []
                params: list = []
                for col, val in [
                    ("keyword", keyword), ("card_id", card_id),
                    ("delivery_count", delivery_count), ("enabled", enabled),
                    ("description", description),
                ]:
                    if val is not None:
                        update_fields.append(f"{col} = ?")
                        params.append(val)
                if not update_fields:
                    return True

                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(rule_id)
                if user_id is not None:
                    params.append(user_id)
                    sql = f"UPDATE delivery_rules SET {', '.join(update_fields)} WHERE id = ? AND user_id = ?"
                else:
                    sql = f"UPDATE delivery_rules SET {', '.join(update_fields)} WHERE id = ?"
                self._execute_sql(cur, sql, params)
                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新发货规则成功: ID {rule_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"更新发货规则失败: {e}")
            raise

    def delete_delivery_rule(self, rule_id: int, user_id: int = None) -> bool:
        """删除发货规则（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(cur, "DELETE FROM delivery_rules WHERE id = ? AND user_id = ?", (rule_id, user_id))
                else:
                    self._execute_sql(cur, "DELETE FROM delivery_rules WHERE id = ?", (rule_id,))
                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除发货规则成功: ID {rule_id} (用户ID: {user_id})")
                    return True
                return False
        except Exception as e:
            logger.error(f"删除发货规则失败: {e}")
            raise

    def increment_delivery_times(self, rule_id: int) -> None:
        """发货次数 +1"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE delivery_rules SET delivery_times = delivery_times + 1, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (rule_id,),
                )
                conn.commit()
                logger.debug(f"发货规则 {rule_id} 发货次数已增加")
        except Exception as e:
            logger.error(f"更新发货次数失败: {e}")

    # ------------------------- 读操作 -------------------------

    def get_all_delivery_rules(self, user_id: int = None) -> List[dict]:
        """获取所有发货规则（含卡券名称/类型）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._LIST_COLUMNS} FROM delivery_rules dr "
                        f"LEFT JOIN cards c ON dr.card_id = c.id "
                        f"WHERE dr.user_id = ? ORDER BY dr.created_at DESC",
                        (user_id,),
                    )
                else:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._LIST_COLUMNS} FROM delivery_rules dr "
                        f"LEFT JOIN cards c ON dr.card_id = c.id "
                        f"ORDER BY dr.created_at DESC",
                    )
                return [self._list_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取发货规则列表失败: {e}")
            return []

    def get_delivery_rule_by_id(self, rule_id: int, user_id: int = None) -> Optional[dict]:
        """根据 ID 获取发货规则（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        f"SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled, "
                        f"dr.description, dr.delivery_times, dr.created_at, dr.updated_at, "
                        f"c.name as card_name, c.type as card_type "
                        f"FROM delivery_rules dr LEFT JOIN cards c ON dr.card_id = c.id "
                        f"WHERE dr.id = ? AND dr.user_id = ?",
                        (rule_id, user_id),
                    )
                else:
                    self._execute_sql(
                        cur,
                        f"SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled, "
                        f"dr.description, dr.delivery_times, dr.created_at, dr.updated_at, "
                        f"c.name as card_name, c.type as card_type "
                        f"FROM delivery_rules dr LEFT JOIN cards c ON dr.card_id = c.id "
                        f"WHERE dr.id = ?",
                        (rule_id,),
                    )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0], 'keyword': row[1], 'card_id': row[2],
                    'delivery_count': row[3], 'enabled': bool(row[4]), 'description': row[5],
                    'delivery_times': row[6], 'created_at': row[7], 'updated_at': row[8],
                    'card_name': row[9], 'card_type': row[10],
                }
        except Exception as e:
            logger.error(f"获取发货规则失败: {e}")
            return None

    # ------------------------- 关键字匹配（发货核心）-------------------------

    def get_delivery_rules_by_keyword(self, keyword: str) -> List[dict]:
        """根据关键字获取匹配的发货规则（双向 LIKE 模糊匹配）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    f"SELECT {self._MATCH_COLUMNS} FROM delivery_rules dr "
                    f"LEFT JOIN cards c ON dr.card_id = c.id "
                    f"WHERE dr.enabled = 1 AND c.enabled = 1 "
                    f"AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%') "
                    f"ORDER BY CASE WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword) "
                    f"ELSE LENGTH(dr.keyword) / 2 END DESC, dr.id ASC",
                    (keyword, keyword, keyword),
                )
                return [self._match_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"根据关键字获取发货规则失败: {e}")
            return []

    def get_delivery_rules_by_keyword_and_spec(self, keyword: str, spec_name: str = None,
                                               spec_value: str = None) -> List[dict]:
        """根据关键字和规格信息获取匹配的发货规则（多规格优先 + 兜底）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 1) 优先：多规格完全匹配
                if spec_name and spec_value:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._MATCH_COLUMNS} FROM delivery_rules dr "
                        f"LEFT JOIN cards c ON dr.card_id = c.id "
                        f"WHERE dr.enabled = 1 AND c.enabled = 1 "
                        f"AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%') "
                        f"AND c.is_multi_spec = 1 AND c.spec_name = ? AND c.spec_value = ? "
                        f"ORDER BY CASE WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword) "
                        f"ELSE LENGTH(dr.keyword) / 2 END DESC, dr.delivery_times ASC",
                        (keyword, keyword, spec_name, spec_value, keyword),
                    )
                    rules = [self._match_row_to_dict(r) for r in cur.fetchall()]
                    if rules:
                        logger.info(f"找到多规格匹配规则: {keyword} - {spec_name}:{spec_value}")
                        return rules

                # 2) 兜底：普通卡券（非多规格）
                self._execute_sql(
                    cur,
                    f"SELECT {self._MATCH_COLUMNS} FROM delivery_rules dr "
                    f"LEFT JOIN cards c ON dr.card_id = c.id "
                    f"WHERE dr.enabled = 1 AND c.enabled = 1 "
                    f"AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%') "
                    f"AND (c.is_multi_spec = 0 OR c.is_multi_spec IS NULL) "
                    f"ORDER BY CASE WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword) "
                    f"ELSE LENGTH(dr.keyword) / 2 END DESC, dr.delivery_times ASC",
                    (keyword, keyword, keyword),
                )
                rules = [self._match_row_to_dict(r) for r in cur.fetchall()]
                if rules:
                    logger.info(f"找到兜底匹配规则: {keyword}")
                else:
                    logger.info(f"未找到匹配规则: {keyword}")
                return rules
        except Exception as e:
            logger.error(f"获取发货规则失败: {e}")
            return []


# 模块级单例
delivery_rule_repo = DeliveryRuleRepo()

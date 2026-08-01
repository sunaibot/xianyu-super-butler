"""
repositories/card_repo.py
=========================
卡券（cards 表）数据访问层。

从 db_manager.DBManager 迁移而来：
- create_card / get_all_cards / get_card_by_id
- update_card / update_card_image_url / delete_card
- consume_batch_data（消费批量数据的第一条记录）

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 支持多规格卡券（is_multi_spec / spec_name / spec_value）
- 支持用户隔离（user_id 过滤）
- api_config 字段在 DB 中为 JSON 字符串，读取时反序列化为 dict
"""
import json
from typing import Any, List, Optional

from loguru import logger

from .base import BaseRepo


def _parse_api_config(raw: Any) -> Any:
    """将 api_config 字段从 JSON 字符串解析为 dict；失败则保持原值"""
    if not raw:
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


class CardRepo(BaseRepo):
    """卡券仓储"""

    table_name = "cards"

    # ------------------------- 字段映射 -------------------------
    _SELECT_COLUMNS = (
        "id, name, type, api_config, text_content, data_content, image_url, "
        "description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value, "
        "created_at, updated_at"
    )

    @staticmethod
    def _row_to_dict(row) -> Optional[dict]:
        """sqlite3.Row / tuple → dict"""
        if row is None:
            return None
        return {
            'id': row[0],
            'name': row[1],
            'type': row[2],
            'api_config': _parse_api_config(row[3]),
            'text_content': row[4],
            'data_content': row[5],
            'image_url': row[6],
            'description': row[7],
            'enabled': bool(row[8]),
            'delay_seconds': row[9] or 0,
            'is_multi_spec': bool(row[10]) if row[10] is not None else False,
            'spec_name': row[11],
            'spec_value': row[12],
            'created_at': row[13],
            'updated_at': row[14],
        }

    # ------------------------- 写操作 -------------------------

    def create_card(self, name: str, card_type: str, api_config=None,
                    text_content: str = None, data_content: str = None, image_url: str = None,
                    description: str = None, enabled: bool = True, delay_seconds: int = 0,
                    is_multi_spec: bool = False, spec_name: str = None, spec_value: str = None,
                    user_id: int = None) -> int:
        """创建新卡券（支持多规格）；返回新卡券 ID"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 唯一性校验
                if is_multi_spec:
                    if not spec_name or not spec_value:
                        raise ValueError("多规格卡券必须提供规格名称和规格值")
                    self._execute_sql(
                        cur,
                        "SELECT COUNT(*) FROM cards WHERE name = ? AND spec_name = ? AND spec_value = ? AND user_id = ?",
                        (name, spec_name, spec_value, user_id),
                    )
                    if cur.fetchone()[0] > 0:
                        raise ValueError(f"卡券已存在：{name} - {spec_name}:{spec_value}")
                else:
                    self._execute_sql(
                        cur,
                        "SELECT COUNT(*) FROM cards WHERE name = ? AND (is_multi_spec = 0 OR is_multi_spec IS NULL) AND user_id = ?",
                        (name, user_id),
                    )
                    if cur.fetchone()[0] > 0:
                        raise ValueError(f"卡券名称已存在：{name}")

                # api_config 序列化
                api_config_str = None
                if api_config is not None:
                    api_config_str = json.dumps(api_config) if isinstance(api_config, dict) else str(api_config)

                self._execute_sql(
                    cur,
                    f"INSERT INTO cards (name, type, api_config, text_content, data_content, image_url, "
                    f"description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value, user_id) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, card_type, api_config_str, text_content, data_content, image_url,
                     description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value, user_id),
                )
                conn.commit()
                card_id = cur.lastrowid
                logger.info(f"创建卡券成功: {name} (ID: {card_id})")
                return card_id
        except Exception as e:
            logger.error(f"创建卡券失败: {e}")
            raise

    def update_card(self, card_id: int, name: str = None, card_type: str = None,
                    api_config=None, text_content: str = None, data_content: str = None,
                    image_url: str = None, description: str = None, enabled: bool = None,
                    delay_seconds: int = None, is_multi_spec: bool = None, spec_name: str = None,
                    spec_value: str = None) -> bool:
        """按字段更新卡券；返回是否成功"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                api_config_str = None
                if api_config is not None:
                    api_config_str = json.dumps(api_config) if isinstance(api_config, dict) else str(api_config)

                update_fields = []
                params: list = []
                for col, val in [
                    ("name", name), ("type", card_type), ("api_config", api_config_str),
                    ("text_content", text_content), ("data_content", data_content),
                    ("image_url", image_url), ("description", description),
                    ("enabled", enabled), ("delay_seconds", delay_seconds),
                    ("is_multi_spec", is_multi_spec), ("spec_name", spec_name), ("spec_value", spec_value),
                ]:
                    if val is not None:
                        update_fields.append(f"{col} = ?")
                        params.append(val)

                if not update_fields:
                    return True  # 无需更新

                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(card_id)

                self._execute_sql(
                    cur,
                    f"UPDATE cards SET {', '.join(update_fields)} WHERE id = ?",
                    params,
                )
                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新卡券成功: ID {card_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"更新卡券失败: {e}")
            raise

    def update_card_image_url(self, card_id: int, new_image_url: str) -> bool:
        """更新图片卡券的图片 URL"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE cards SET image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND type = 'image'",
                    (new_image_url, card_id),
                )
                conn.commit()
                if cur.rowcount > 0:
                    logger.info(f"卡券图片URL更新成功: 卡券ID: {card_id}")
                    return True
                logger.warning(f"未找到匹配的图片卡券: 卡券ID: {card_id}")
                return False
        except Exception as e:
            logger.error(f"更新卡券图片URL失败: {e}")
            return False

    def delete_card(self, card_id: int) -> bool:
        """删除卡券"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM cards WHERE id = ?", (card_id,))
                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除卡券成功: ID {card_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"删除卡券失败: {e}")
            raise

    def consume_batch_data(self, card_id: int):
        """消费批量数据的第一条记录（线程安全）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 获取卡券的批量数据
                self._execute_sql(cur, "SELECT data_content FROM cards WHERE id = ? AND type = 'data'", (card_id,))
                result = cur.fetchone()

                if not result or not result[0]:
                    logger.warning(f"卡券 {card_id} 没有批量数据")
                    return None

                data_content = result[0]
                lines = [line.strip() for line in data_content.split('\n') if line.strip()]

                if not lines:
                    logger.warning(f"卡券 {card_id} 批量数据为空")
                    return None

                # 获取第一条数据
                first_line = lines[0]

                # 移除第一条数据，更新数据库
                remaining_lines = lines[1:]
                new_data_content = '\n'.join(remaining_lines)

                self._execute_sql(
                    cur,
                    '''
                    UPDATE cards
                    SET data_content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''',
                    (new_data_content, card_id),
                )

                logger.info(f"消费批量数据成功: 卡券ID={card_id}, 剩余={len(remaining_lines)}条")
                return first_line

        except Exception as e:
            logger.error(f"消费批量数据失败: {e}")
            return None

    # ------------------------- 读操作 -------------------------

    def get_all_cards(self, user_id: int = None) -> List[dict]:
        """获取所有卡券（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._SELECT_COLUMNS} FROM cards WHERE user_id = ? ORDER BY created_at DESC",
                        (user_id,),
                    )
                else:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._SELECT_COLUMNS} FROM cards ORDER BY created_at DESC",
                    )
                return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取卡券列表失败: {e}")
            return []

    def get_card_by_id(self, card_id: int, user_id: int = None) -> Optional[dict]:
        """根据 ID 获取卡券（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._SELECT_COLUMNS} FROM cards WHERE id = ? AND user_id = ?",
                        (card_id, user_id),
                    )
                else:
                    self._execute_sql(
                        cur,
                        f"SELECT {self._SELECT_COLUMNS} FROM cards WHERE id = ?",
                        (card_id,),
                    )
                return self._row_to_dict(cur.fetchone())
        except Exception as e:
            logger.error(f"获取卡券失败: {e}")
            return None

    def search_cards(self, keyword: str, limit: int = 10) -> List[dict]:
        """跨字段 LIKE 搜索卡券（用于全局搜索，不返回 card_content 全文）"""
        try:
            like = f"%{keyword}%"
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT id, remark FROM cards "
                    "WHERE card_content LIKE ? OR remark LIKE ? LIMIT ?",
                    (like, like, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"搜索卡券失败: {e}")
            return []


# 模块级单例（与 cookie_repo / order_repo 一致）
card_repo = CardRepo()

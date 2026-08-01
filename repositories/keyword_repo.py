"""
repositories/keyword_repo.py
============================
关键字（keywords 表）数据访问层。

从 db_manager.DBManager 迁移而来：
- save_keywords / save_keywords_with_item_id / save_text_keywords_only
- get_keywords / get_keywords_with_item_id / get_keywords_with_type / get_all_keywords
- check_keyword_duplicate / save_image_keyword / update_keyword_image_url
- delete_keyword_by_index

设计要点：
- 关键字支持文本/图片两种类型（type 字段）
- 文本关键字保存时保留图片关键字（save_text_keywords_only）
- item_id 标准化：空字符串 → None
- 关键字查重支持通用（item_id 为空）和商品级别（item_id 非空）
- 表结构迁移方法（_migrate_keywords_table_constraints / upgrade_keywords_table_for_image_support）
  属于 schema 管理范畴，仍保留在 DBManager
"""
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .base import BaseRepo


class KeywordRepo(BaseRepo):
    """关键字仓储"""

    table_name = "keywords"

    # ------------------------- 保存 -------------------------

    def save_keywords(self, cookie_id: str, keywords: List[Tuple[str, str]]) -> bool:
        """保存关键字列表（向后兼容方法，不含 item_id）"""
        keywords_with_item_id = [(keyword, reply, None) for keyword, reply in keywords]
        return self.save_keywords_with_item_id(cookie_id, keywords_with_item_id)

    def save_keywords_with_item_id(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """保存关键字列表（含 item_id），先删除旧数据再插入"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "DELETE FROM keywords WHERE cookie_id = ?", (cookie_id,))

                for keyword, reply, item_id in keywords:
                    normalized_item_id = item_id if item_id and item_id.strip() else None
                    try:
                        self._execute_sql(
                            cur,
                            "INSERT INTO keywords (cookie_id, keyword, reply, item_id) VALUES (?, ?, ?, ?)",
                            (cookie_id, keyword, reply, normalized_item_id),
                        )
                    except sqlite3.IntegrityError as ie:
                        item_desc = f"商品ID: {normalized_item_id}" if normalized_item_id else "通用关键词"
                        logger.error(f"关键词唯一约束冲突: Cookie={cookie_id}, 关键词='{keyword}', {item_desc}")
                        raise ie

                conn.commit()
                logger.info(f"关键字保存成功: {cookie_id}, {len(keywords)}条")
                return True
        except Exception as e:
            logger.error(f"关键字保存失败: {e}")
            return False

    def save_text_keywords_only(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """保存文本关键字，只删除文本类型，保留图片关键词"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 检查与现有图片关键词的冲突
                for keyword, reply, item_id in keywords:
                    normalized_item_id = item_id if item_id and item_id.strip() else None
                    if normalized_item_id:
                        self._execute_sql(
                            cur,
                            "SELECT type FROM keywords WHERE cookie_id = ? AND keyword = ? AND item_id = ? AND type = 'image'",
                            (cookie_id, keyword, normalized_item_id),
                        )
                    else:
                        self._execute_sql(
                            cur,
                            "SELECT type FROM keywords WHERE cookie_id = ? AND keyword = ? AND (item_id IS NULL OR item_id = '') AND type = 'image'",
                            (cookie_id, keyword),
                        )

                    if cur.fetchone():
                        item_desc = f"商品ID: {normalized_item_id}" if normalized_item_id else "通用关键词"
                        error_msg = f"关键词 '{keyword}' （{item_desc}） 已存在（图片关键词），无法保存为文本关键词"
                        logger.warning(f"文本关键词与图片关键词冲突: Cookie={cookie_id}, 关键词='{keyword}', {item_desc}")
                        raise ValueError(error_msg)

                # 只删除文本类型
                self._execute_sql(
                    cur,
                    "DELETE FROM keywords WHERE cookie_id = ? AND (type IS NULL OR type = 'text')",
                    (cookie_id,),
                )

                # 插入新文本关键字
                for keyword, reply, item_id in keywords:
                    normalized_item_id = item_id if item_id and item_id.strip() else None
                    self._execute_sql(
                        cur,
                        "INSERT INTO keywords (cookie_id, keyword, reply, item_id, type) VALUES (?, ?, ?, ?, 'text')",
                        (cookie_id, keyword, reply, normalized_item_id),
                    )

                conn.commit()
                logger.info(f"文本关键字保存成功: {cookie_id}, {len(keywords)}条，图片关键词已保留")
                return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"文本关键字保存失败: {e}")
            return False

    def save_image_keyword(self, cookie_id: str, keyword: str, image_url: str, item_id: str = None) -> bool:
        """保存图片关键词（调用前应先检查重复）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                normalized_item_id = item_id if item_id and item_id.strip() else None
                self._execute_sql(
                    cur,
                    "INSERT INTO keywords (cookie_id, keyword, reply, item_id, type, image_url) "
                    "VALUES (?, ?, ?, ?, 'image', ?)",
                    (cookie_id, keyword, '', normalized_item_id, 'image', image_url),
                )
                conn.commit()
                logger.info(f"图片关键词保存成功: {cookie_id}, 关键词: {keyword}, 图片: {image_url}")
                return True
        except Exception as e:
            logger.error(f"图片关键词保存失败: {e}")
            return False

    # ------------------------- 查询 -------------------------

    def get_keywords(self, cookie_id: str) -> List[Tuple[str, str]]:
        """获取指定 Cookie 的关键字列表（不含 item_id）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(cur, "SELECT keyword, reply FROM keywords WHERE cookie_id = ?", (cookie_id,))
                return [(row[0], row[1]) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取关键字失败: {e}")
            return []

    def get_keywords_with_item_id(self, cookie_id: str) -> List[Tuple[str, str, str]]:
        """获取指定 Cookie 的关键字列表（含 item_id）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT keyword, reply, item_id FROM keywords WHERE cookie_id = ?",
                    (cookie_id,),
                )
                return [(row[0], row[1], row[2]) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"获取关键字失败: {e}")
            return []

    def get_keywords_with_type(self, cookie_id: str) -> List[Dict[str, Any]]:
        """获取指定 Cookie 的关键字列表（含类型信息）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT keyword, reply, item_id, type, image_url FROM keywords WHERE cookie_id = ?",
                    (cookie_id,),
                )
                return [
                    {
                        'keyword': row[0],
                        'reply': row[1],
                        'item_id': row[2],
                        'type': row[3] or 'text',
                        'image_url': row[4],
                    }
                    for row in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"获取关键字失败: {e}")
            return []

    def get_all_keywords(self, user_id: int = None) -> Dict[str, List[Tuple[str, str]]]:
        """获取所有 Cookie 的关键字（支持用户隔离）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if user_id is not None:
                    self._execute_sql(
                        cur,
                        "SELECT k.cookie_id, k.keyword, k.reply FROM keywords k "
                        "JOIN cookies c ON k.cookie_id = c.id WHERE c.user_id = ?",
                        (user_id,),
                    )
                else:
                    self._execute_sql(cur, "SELECT cookie_id, keyword, reply FROM keywords")
                result: Dict[str, List[Tuple[str, str]]] = {}
                for row in cur.fetchall():
                    cookie_id, keyword, reply = row
                    result.setdefault(cookie_id, []).append((keyword, reply))
                return result
        except Exception as e:
            logger.error(f"获取所有关键字失败: {e}")
            return {}

    def check_keyword_duplicate(self, cookie_id: str, keyword: str, item_id: str = None) -> bool:
        """检查关键词是否重复"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                if item_id:
                    self._execute_sql(
                        cur,
                        "SELECT COUNT(*) FROM keywords WHERE cookie_id = ? AND keyword = ? AND item_id = ?",
                        (cookie_id, keyword, item_id),
                    )
                else:
                    self._execute_sql(
                        cur,
                        "SELECT COUNT(*) FROM keywords WHERE cookie_id = ? AND keyword = ? AND (item_id IS NULL OR item_id = '')",
                        (cookie_id, keyword),
                    )
                return cur.fetchone()[0] > 0
        except Exception as e:
            logger.error(f"检查关键词重复失败: {e}")
            return False

    # ------------------------- 更新 / 删除 -------------------------

    def update_keyword_image_url(self, cookie_id: str, keyword: str, new_image_url: str) -> bool:
        """更新关键词的图片 URL"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "UPDATE keywords SET image_url = ? WHERE cookie_id = ? AND keyword = ? AND type = 'image'",
                    (new_image_url, cookie_id, keyword),
                )
                conn.commit()
                if cur.rowcount > 0:
                    logger.info(f"关键词图片URL更新成功: {cookie_id}, 关键词: {keyword}")
                    return True
                logger.warning(f"未找到匹配的图片关键词: {cookie_id}, 关键词: {keyword}")
                return False
        except Exception as e:
            logger.error(f"更新关键词图片URL失败: {e}")
            return False

    def delete_keyword_by_index(self, cookie_id: str, index: int) -> bool:
        """根据索引删除关键词（按 rowid 排序）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    "SELECT rowid FROM keywords WHERE cookie_id = ? ORDER BY rowid",
                    (cookie_id,),
                )
                rows = cur.fetchall()
                if 0 <= index < len(rows):
                    rowid = rows[index][0]
                    self._execute_sql(cur, "DELETE FROM keywords WHERE rowid = ?", (rowid,))
                    conn.commit()
                    logger.info(f"删除关键词成功: {cookie_id}, 索引: {index}")
                    return True
                logger.warning(f"关键词索引超出范围: {index}")
                return False
        except Exception as e:
            logger.error(f"删除关键词失败: {e}")
            return False


# 模块级单例
keyword_repo = KeywordRepo()

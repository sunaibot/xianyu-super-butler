#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库服务模块
轻量话术管理 + 关键词匹配检索
所有 AI 回复通过外部 API 接口，本模块仅做话术存储和快速匹配

数据访问统一通过 db_manager.get_connection()，不再自管 sqlite3.connect。
"""

import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

_kb_instance = None


class KeywordMatcher:
    """关键词匹配器 - 基于 TF-IDF 思想的轻量匹配"""

    def __init__(self):
        self.scripts: List[Dict] = []

    def load_scripts(self, scripts: List[Dict]):
        self.scripts = scripts

    def search(self, query: str, n_results: int = 3) -> List[Dict]:
        if not self.scripts:
            return []

        query_lower = query.lower().strip()
        if not query_lower:
            return []

        scored = []
        for script in self.scripts:
            question = script.get("user_question", "").lower()
            answer = script.get("answer", "")
            score = self._compute_similarity(query_lower, question)

            scored.append({
                "id": script.get("id", 0),
                "document": question,
                "metadata": {
                    "answer": answer,
                    "intent_l1": script.get("intent_l1", ""),
                    "intent_l2": script.get("intent_l2", ""),
                },
                "similarity": round(score * 100, 2),
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return [r for r in scored if r["similarity"] > 0][:n_results]

    @staticmethod
    def _compute_similarity(query: str, question: str) -> float:
        if not query or not question:
            return 0.0

        if query == question:
            return 1.0

        if query in question or question in query:
            return 0.9

        q_chars = set(query)
        q_chars.discard(" ")
        q_chars.discard(",")
        q_chars.discard("，")
        q_chars.discard("。")
        q_chars.discard("？")
        q_chars.discard("?")

        q_len = max(len(q_chars), 1)

        q_bigrams = set(query[i:i+2] for i in range(len(query) - 1))
        q_bigrams.discard(" ")

        score = 0.0

        for bg in q_bigrams:
            if bg and bg in question:
                score += 0.15

        score = min(score, 0.85)

        common_chars = q_chars & set(question)
        char_score = len(common_chars) / q_len * 0.3
        score += min(char_score, 0.3)

        return min(score, 1.0)


class KnowledgeBaseService:
    """知识库服务 - SQLite 持久化 + 关键词匹配

    通过 db_manager.get_connection() 访问数据库，统一连接管理。
    """

    def __init__(self):
        self.matcher = KeywordMatcher()
        self._load_scripts()

    def _get_conn(self):
        """从 db_manager 获取共享连接，并设置 row_factory"""
        from db_manager import db_manager
        import sqlite3
        conn = db_manager.get_connection()
        # 临时切到 Row factory（仅影响本连接后续查询）
        conn.row_factory = sqlite3.Row
        return conn

    def _load_scripts(self):
        try:
            scripts = self._get_all_scripts_from_db()
            self.matcher.load_scripts(scripts)
            logger.info(f"📚 话术库已加载 {len(scripts)} 条话术（关键词匹配模式）")
        except Exception as e:
            logger.error(f"加载话术失败: {e}")

    def _get_all_scripts_from_db(self) -> List[Dict]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id, user_question, answer, intent_l1, intent_l2, created_at "
                "FROM knowledge_base_scripts WHERE enabled = 1 ORDER BY id"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取所有话术失败: {e}")
            return []

    def rebuild_index(self) -> int:
        try:
            self._load_scripts()
            scripts = self._get_all_scripts_from_db()
            logger.info(f"✅ 话术库重建完成，共 {len(scripts)} 条")
            return len(scripts)
        except Exception as e:
            logger.error(f"❌ 重建索引失败: {e}")
            raise

    def search(self, query: str, n_results: int = 3) -> List[Dict]:
        return self.matcher.search(query, n_results)

    def add_script(self, question: str, answer: str, intent_l1: str = "", intent_l2: str = "") -> int:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "INSERT INTO knowledge_base_scripts (user_question, answer, intent_l1, intent_l2, enabled) "
                "VALUES (?, ?, ?, ?, 1)",
                (question, answer, intent_l1, intent_l2),
            )
            script_id = cursor.lastrowid
            conn.commit()
            self._load_scripts()
            return script_id
        except Exception as e:
            logger.error(f"添加话术失败: {e}")
            raise

    def update_script(self, script_id: int, question: str, answer: str, intent_l1: str = "", intent_l2: str = ""):
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE knowledge_base_scripts SET user_question=?, answer=?, intent_l1=?, intent_l2=? WHERE id=?",
                (question, answer, intent_l1, intent_l2, script_id),
            )
            conn.commit()
            self._load_scripts()
        except Exception as e:
            logger.error(f"更新话术失败: {e}")
            raise

    def delete_script(self, script_id: int):
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM knowledge_base_scripts WHERE id=?", (script_id,))
            conn.commit()
            self._load_scripts()
        except Exception as e:
            logger.error(f"删除话术失败: {e}")
            raise

    def list_scripts(self, page: int = 1, page_size: int = 20, search: str = "") -> Tuple[List[Dict], int]:
        try:
            conn = self._get_conn()

            count_sql = "SELECT COUNT(*) FROM knowledge_base_scripts WHERE 1=1"
            data_sql = "SELECT * FROM knowledge_base_scripts WHERE 1=1"
            params = []

            if search:
                count_sql += " AND (user_question LIKE ? OR answer LIKE ?)"
                data_sql += " AND (user_question LIKE ? OR answer LIKE ?)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])

            total = conn.execute(count_sql, params).fetchone()[0]

            data_sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            offset = (page - 1) * page_size
            rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

            return [dict(row) for row in rows], total
        except Exception as e:
            logger.error(f"获取话术列表失败: {e}")
            return [], 0

    def import_from_text(self, text: str) -> int:
        """从文本导入，格式：question,answer,intent_l1,intent_l2（每行一条）"""
        count = 0
        try:
            lines = text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",", 3)
                if len(parts) < 2:
                    continue
                question = parts[0].strip()
                answer = parts[1].strip()
                intent_l1 = parts[2].strip() if len(parts) > 2 else ""
                intent_l2 = parts[3].strip() if len(parts) > 3 else ""
                if question and answer:
                    self.add_script(question, answer, intent_l1, intent_l2)
                    count += 1
            logger.info(f"✅ 导入了 {count} 条话术")
            return count
        except Exception as e:
            logger.error(f"❌ 导入失败: {e}")
            raise

    def get_status(self) -> Dict:
        scripts = self._get_all_scripts_from_db()
        return {
            "total_scripts": len(scripts),
            "search_mode": "keyword_match",
        }


def get_kb_service() -> KnowledgeBaseService:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBaseService()
    return _kb_instance

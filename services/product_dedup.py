"""
商品去重模块

提供 URL 级别去重和文案语义去重（bigram Jaccard 相似度），
不依赖外部 embedding 模型。
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ServiceBase

logger = logging.getLogger(__name__)

DEFAULT_RECORDS_PATH = "data/published_records.json"


class ProductDedup(ServiceBase):
    """商品去重检测器"""

    name: str = "product_dedup"
    display_name: str = "商品去重"
    description: str = "URL 级别去重与文案语义去重（bigram Jaccard 相似度）"
    version: str = "1.0.0"

    def __init__(self, records_path: Optional[str] = None):
        self._records_path = Path(records_path or DEFAULT_RECORDS_PATH)
        self._lock = threading.Lock()
        self._records: List[Dict] = self._load_records()

    def startup(self) -> None:
        """初始化已在 __init__ 完成，启动无需额外操作"""
        pass

    def health(self) -> Dict[str, Any]:
        return {
            **super().health(),
            "records_count": len(self._records),
            "records_path": str(self._records_path),
        }

    def call(self, action: str, payload: Dict[str, Any] = None) -> Any:
        payload = payload or {}
        if action == "dedup":
            return self.dedup_items(
                item_urls=payload.get("item_urls"),
                item_titles=payload.get("item_titles"),
                item_descriptions=payload.get("item_descriptions"),
                url_threshold=payload.get("url_threshold", 0.9),
                text_threshold=payload.get("text_threshold", 0.7),
            )
        if action == "is_url_published":
            return self.is_url_published(payload.get("url", ""))
        if action == "is_text_similar":
            return self.is_text_similar(
                payload.get("text", ""),
                payload.get("threshold", 0.85),
            )
        if action == "save_published":
            return self.save_published(
                payload.get("url", ""),
                payload.get("title", ""),
                payload.get("description", ""),
            )
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")


    def _load_records(self) -> List[Dict]:
        try:
            if self._records_path.exists():
                with open(self._records_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                logger.info(f"已加载 {len(records)} 条发布记录 ({self._records_path})")
                return records
            else:
                self._records_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._records_path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                logger.info(f"已初始化空发布记录文件: {self._records_path}")
                return []
        except Exception as e:
            logger.warning(f"加载发布记录失败，将使用空记录: {e}")
            return []

    def _persist_records(self) -> None:
        try:
            with open(self._records_path, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存发布记录失败: {e}")
            raise

    def is_url_published(self, url: str) -> bool:
        with self._lock:
            for record in self._records:
                if record.get("url") == url:
                    logger.debug(f"URL 已发布过: {url}")
                    return True
            return False

    def is_text_similar(
        self, new_text: str, threshold: float = 0.85
    ) -> Dict:
        with self._lock:
            best_score = 0.0
            best_text = ""

            for record in self._records:
                existing_text = (
                    record.get("title", "") + " " + record.get("description", "")
                ).strip()
                if not existing_text:
                    continue

                score = self._jaccard_similarity(new_text, existing_text)
                if score > best_score:
                    best_score = score
                    best_text = existing_text

            is_similar = best_score >= threshold
            if is_similar:
                logger.info(
                    f"文案相似度过高 ({best_score:.3f} >= {threshold}): {new_text[:30]}..."
                )

            return {
                "is_similar": is_similar,
                "most_similar_text": best_text,
                "similarity": best_score,
            }

    def save_published(
        self, url: str, title: str, description: str = ""
    ) -> None:
        record: Dict = {
            "url": url,
            "title": title,
            "description": description,
            "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with self._lock:
            self._records.append(record)
            self._persist_records()

        logger.info(f"已保存发布记录: {title} ({url})")

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        def bigrams(text: str):
            return {text[i: i + 2] for i in range(len(text) - 1)}

        set1 = bigrams(text1)
        set2 = bigrams(text2)

        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union)

    def dedup_items(
        self,
        item_urls: List[str] = None,
        item_titles: List[str] = None,
        item_descriptions: List[str] = None,
        url_threshold: float = 0.9,
        text_threshold: float = 0.7,
    ) -> Dict:
        """
        批量商品去重

        Args:
            item_urls: 商品URL列表
            item_titles: 商品标题列表（与urls对应）
            item_descriptions: 商品描述列表（与urls对应）
            url_threshold: URL相似度阈值
            text_threshold: 文案相似度阈值

        Returns:
            {"duplicates": [(index, reason, similar_to)], "unique_indices": [...]}
        """
        item_urls = item_urls or []
        item_titles = item_titles or []
        item_descriptions = item_descriptions or []

        count = max(len(item_urls), len(item_titles), len(item_descriptions))
        if count == 0:
            return {"duplicates": [], "unique_indices": []}

        duplicates = []
        unique_indices = list(range(count))

        seen_urls = {}
        seen_texts = []

        for i in range(count):
            url = item_urls[i] if i < len(item_urls) else ""
            title = item_titles[i] if i < len(item_titles) else ""
            desc = item_descriptions[i] if i < len(item_descriptions) else ""

            is_dup = False

            if url:
                if url in seen_urls:
                    duplicates.append({
                        "index": i,
                        "reason": "URL重复",
                        "similar_to": seen_urls[url]
                    })
                    is_dup = True
                else:
                    seen_urls[url] = i

            if not is_dup and (title or desc):
                combined = f"{title} {desc}".strip()
                if combined:
                    for prev_idx, prev_text in seen_texts:
                        sim = self._jaccard_similarity(combined, prev_text)
                        if sim >= text_threshold:
                            duplicates.append({
                                "index": i,
                                "reason": f"文案重复 (相似度={sim:.2f})",
                                "similar_to": prev_idx
                            })
                            is_dup = True
                            break

            if not is_dup:
                seen_texts.append((i, combined))

        dup_indices = {d["index"] for d in duplicates}
        unique_indices = [i for i in range(count) if i not in dup_indices]

        return {
            "total_input": count,
            "duplicate_count": len(duplicates),
            "unique_count": len(unique_indices),
            "duplicates": duplicates,
            "unique_indices": unique_indices
        }


# 模块级单例，供 registry 注册及外部复用
product_dedup = ProductDedup()

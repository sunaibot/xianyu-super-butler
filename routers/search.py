"""
routers/search.py
=================
全局跨实体搜索 router。

POST /api/search
  body: { query, entities: ['order','item','account','card'], limit }
  return: { orders, items, accounts, cards }

委托各 repo 的 search_xxx 方法，本路由只做聚合与字段统一。
"""
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .deps import require_auth, server_error
from db_manager import db_manager

router = APIRouter(prefix="/api", tags=["搜索"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=100, description="搜索关键词")
    entities: Optional[List[str]] = Field(
        default=None, description="限定搜索实体，默认全部"
    )
    limit: int = Field(default=10, ge=1, le=50, description="每组返回上限")


# 支持的实体集合
SUPPORTED_ENTITIES = {"order", "item", "account", "card"}


def _normalize_order(row: dict) -> dict:
    return {
        "id": str(row.get("order_id") or ""),
        "label": str(row.get("order_id") or "")[:80],
        "sub": str(row.get("item_id") or "")[:80],
    }


def _normalize_item(row: dict) -> dict:
    return {
        "id": str(row.get("item_id") or ""),
        "label": str(row.get("title") or row.get("item_id") or "")[:80],
        "sub": str(row.get("item_id") or "")[:80],
    }


def _normalize_account(row: dict) -> dict:
    return {
        "id": str(row.get("cookie_id") or ""),
        "label": str(row.get("remark") or row.get("cookie_id") or "")[:80],
        "sub": str(row.get("cookie_id") or "")[:80],
    }


def _normalize_card(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "label": str(row.get("remark") or row.get("id") or "")[:80],
        "sub": str(row.get("id") or "")[:80],
    }


@router.post("/search")
async def global_search(req: SearchRequest, _: dict = Depends(require_auth)):
    """全局跨实体搜索"""
    try:
        entities = req.entities or list(SUPPORTED_ENTITIES)
        result = {}

        for entity in entities:
            if entity == "order":
                rows = db_manager.search_orders(req.query, req.limit)
                result["orders"] = [_normalize_order(r) for r in rows]
            elif entity == "item":
                rows = db_manager.search_items(req.query, req.limit)
                result["items"] = [_normalize_item(r) for r in rows]
            elif entity == "account":
                rows = db_manager.search_cookies(req.query, req.limit)
                result["accounts"] = [_normalize_account(r) for r in rows]
            elif entity == "card":
                rows = db_manager.search_cards(req.query, req.limit)
                result["cards"] = [_normalize_card(r) for r in rows]

        return {"success": True, "data": result, "query": req.query}
    except Exception as e:
        raise server_error(e, "全局搜索")

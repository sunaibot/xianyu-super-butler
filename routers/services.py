"""
routers/services.py
==================
服务模块接口路由（从 reply_server.py 迁移）。

路由清单：
违禁词 / 去重 / 监控：
- POST /api/services/forbidden-check    违禁词检测
- POST /api/services/forbidden-clean     违禁词检测+替换
- POST /api/services/product-dedup       商品去重（URL+文案相似度）
- GET  /api/services/performance-stats   获取性能监控统计
- POST /api/services/performance-reset    重置性能监控

商品抓取与发布：
- POST /api/services/extract-product     从闲鱼商品页抓取商品信息
- POST /api/services/publish-product      发布商品到闲鱼
- POST /api/services/download-images      下载商品图片

设计要点：
- 契约说明：请求/响应结构必须与前端 frontend/services/api.ts 及 frontend/types.ts 保持一致
- 这些接口在原实现中无需认证（公开 API），保持向后兼容
- 服务实例统一通过 services.registry.get_service 获取，避免双份实例
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from loguru import logger

from services.registry import get_service

router = APIRouter(prefix="/api/services", tags=["services"])


# ==================== Pydantic 模型 ====================

class ForbiddenCheckRequest(BaseModel):
    text: str


class DedupRequest(BaseModel):
    item_urls: List[str] = []
    item_titles: List[str] = []
    item_descriptions: List[str] = []


class CleanTextRequest(BaseModel):
    text: str


class ExtractProductRequest(BaseModel):
    product_url: str
    cookie_id: Optional[str] = None


class PublishProductRequest(BaseModel):
    title: str
    description: str = ""
    price: str = ""  # 前端传入字符串，后端转换为 float
    original_price: float = 0
    images: List[str] = []
    category: str = ""  # 前端会传，后端忽略（ProductPublisher 不使用）
    shipping: str = "包邮"
    cookie_id: Optional[str] = None
    dry_run: bool = False  # 默认真正发布（前端显式传 true 才模拟）


def _safe_client_msg(e: Exception, default: str = "操作失败") -> str:
    """构造可安全回传给客户端的错误消息（与 deps.safe_client_msg 一致）"""
    import re
    _SENSITIVE = re.compile(
        r'(?i)(password|passwd|secret|token|api[_-]?key|cookie|authorization|/data/|\\data\\|\.db|sqlite)'
    )
    if isinstance(e, (ValueError, KeyError, AttributeError, TypeError)):
        msg = str(e).strip()
        if not msg:
            return default
        return _SENSITIVE.sub('***', msg)
    return default


# ==================== 违禁词 / 去重 / 监控 ====================

@router.post("/forbidden-check")
def api_forbidden_check(req: ForbiddenCheckRequest):
    """违禁词检测
    返回: {has_forbidden, found_words, suggestions, original_text, cleaned_text}
    """
    svc = get_service("forbidden_words")
    if not svc:
        return {"has_forbidden": False, "found_words": [], "suggestions": [], "original_text": req.text, "cleaned_text": req.text}
    return svc.call("check", {"text": req.text})


@router.post("/forbidden-clean")
def api_forbidden_clean(req: CleanTextRequest):
    """违禁词检测+替换（返回清理后的文本，前端可直接使用）
    返回: {has_forbidden, found_words, suggestions, original_text, cleaned_text}
    """
    svc = get_service("forbidden_words")
    if not svc:
        return {"has_forbidden": False, "found_words": [], "suggestions": [], "original_text": req.text, "cleaned_text": req.text}
    return svc.call("check", {"text": req.text})


@router.post("/product-dedup")
def api_product_dedup(req: DedupRequest):
    """商品去重（URL+文案相似度）
    返回: {total_input, duplicate_count, unique_count, duplicates, unique_indices}
    duplicates 元素: {index1, index2, similarity, reason}
    """
    urls = req.item_urls or []
    titles = req.item_titles or []
    descriptions = req.item_descriptions or []

    if not urls and not titles:
        return {
            "total_input": 0,
            "duplicate_count": 0,
            "unique_count": 0,
            "duplicates": [],
            "unique_indices": [],
        }

    svc = get_service("product_dedup")
    if not svc:
        return {"total_input": len(urls), "duplicate_count": 0, "unique_count": len(urls), "duplicates": [], "unique_indices": list(range(len(urls)))}

    raw_result = svc.call("dedup", {
        "item_urls": urls,
        "item_titles": titles,
        "item_descriptions": descriptions,
    })

    # 适配前端期望的字段结构：{index1, index2, similarity, reason}
    adapted_duplicates = []
    for dup in raw_result.get("duplicates", []):
        reason_str = dup.get("reason", "")
        similarity = 0.0
        if "相似度=" in reason_str:
            try:
                similarity = float(reason_str.split("相似度=")[1].rstrip(")"))
            except (ValueError, IndexError):
                similarity = 1.0 if "URL重复" in reason_str else 0.0
        elif "URL重复" in reason_str:
            similarity = 1.0

        adapted_duplicates.append({
            "index1": dup.get("index", 0),
            "index2": dup.get("similar_to", 0),
            "similarity": similarity,
            "reason": reason_str,
        })

    return {
        "total_input": raw_result.get("total_input", 0),
        "duplicate_count": raw_result.get("duplicate_count", 0),
        "unique_count": raw_result.get("unique_count", 0),
        "duplicates": adapted_duplicates,
        "unique_indices": raw_result.get("unique_indices", []),
    }


@router.get("/performance-stats")
def api_performance_stats():
    """获取性能监控统计
    返回: {today: {...}, summary: {...}, recent: [...], provider_comparison: {...}}
    """
    perf = get_service("performance_monitor")
    if not perf:
        return {"today": {}, "summary": {}, "recent": [], "provider_comparison": {}}
    return perf.call("stats", {})


@router.post("/performance-reset")
def api_performance_reset():
    """重置性能监控（清空所有历史数据）"""
    perf = get_service("performance_monitor")
    if not perf:
        return {"success": False, "message": "性能监控不可用"}
    ok = perf.call("reset", {})
    return {"success": bool(ok), "message": "性能监控已重置" if ok else "重置失败"}


# ==================== 商品抓取与发布 ====================

@router.post("/extract-product")
def api_extract_product(req: ExtractProductRequest):
    """从闲鱼商品页抓取商品信息
    返回: {success, product: {title, price, images, description, category}, message?}
    """
    try:
        from services.browser_service import get_browser_service
        from services.product_extractor import ProductExtractor

        bs = get_browser_service()
        extractor = ProductExtractor(bs, config={})
        product = extractor.extract_product_info(req.product_url)
        if product:
            return {
                "success": True,
                "product": {
                    "title": product.title,
                    "price": str(product.current_price or product.original_price or ""),
                    "images": list(product.image_urls or []),
                    "description": product.description or "",
                    "category": product.category or "其他技能服务",
                },
            }
        else:
            return {"success": False, "message": "商品信息提取失败"}
    except ImportError as e:
        return {"success": False, "message": _safe_client_msg(e, "依赖缺失失败")}
    except Exception as e:
        logger.error(f"商品提取失败: {e}")
        return {"success": False, "message": "商品提取失败，请稍后重试"}


@router.post("/publish-product")
def api_publish_product(req: PublishProductRequest):
    """发布商品到闲鱼
    返回: {success, message, dry_run?}
    """
    try:
        from services.browser_service import get_browser_service
        from services.product_models import ProductInfo
        from services.product_publisher import ProductPublisher

        # 转换 price 字符串为 float
        try:
            price_float = float(req.price) if req.price else 0.0
        except ValueError:
            return {"success": False, "message": f"价格格式无效: {req.price}"}

        bs = get_browser_service()
        publisher = ProductPublisher(bs, config={})

        product = ProductInfo(
            source_url="",
            title=req.title,
            description=req.description,
            current_price=price_float,
            original_price=req.original_price or price_float,
            image_urls=req.images,
            local_images=req.images,
            shipping=req.shipping,
        )

        result = publisher.publish_product(product, dry_run=req.dry_run)
        return {
            "success": result,
            "message": "商品发布成功" if result else "商品发布失败",
            "dry_run": req.dry_run,
        }
    except ImportError as e:
        return {"success": False, "message": _safe_client_msg(e, "依赖缺失失败")}
    except Exception as e:
        logger.error(f"商品发布失败: {e}")
        return {"success": False, "message": "商品发布失败，请稍后重试"}


@router.post("/download-images")
def api_download_images(req: dict):
    """下载商品图片"""
    try:
        from services.product_extractor import ProductExtractor

        urls = req.get("image_urls", [])
        save_dir = req.get("save_dir", "temp_images")
        config = {"image_save_dir": save_dir}

        class _FakeBrowser:
            pass

        extractor = ProductExtractor(_FakeBrowser(), config)
        local_paths = extractor.download_images(urls, save_dir)
        return {
            "success": True,
            "downloaded_count": len(local_paths),
            "local_paths": local_paths,
        }
    except Exception as e:
        logger.error(f"图片下载失败: {e}")
        return {"success": False, "message": "图片下载失败，请稍后重试"}

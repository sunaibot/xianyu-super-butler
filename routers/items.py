"""
routers/items.py
================
商品管理路由（从 reply_server.py 迁移）。

路由清单（按声明顺序，FastAPI 按顺序匹配）：
- 静态路径优先（避免被动态路径 /items/{cid} 吞掉）

商品信息（item_info 表）：
- GET    /items                                       获取当前用户的所有商品信息
- POST   /items/search                                 搜索闲鱼商品
- POST   /items/search_multiple                        搜索多页闲鱼商品
- POST   /items/get-all-from-account                   从指定账号获取所有商品信息
- POST   /items/get-by-page                            从指定账号按页获取商品信息
- DELETE /items/batch                                   批量删除商品信息
- GET    /items/cookie/{cookie_id}                     获取指定Cookie的商品信息（完整字段）
- GET    /items/{cid}                                  获取指定账号的商品列表（摘要）
- POST   /items/{cookie_id}                            添加新商品
- GET    /items/{cookie_id}/{item_id}                  获取商品详情
- PUT    /items/{cookie_id}/{item_id}                  更新商品详情
- DELETE /items/{cookie_id}/{item_id}                  删除商品信息
- PUT    /items/{cookie_id}/{item_id}/multi-spec        更新商品多规格状态
- PUT    /items/{cookie_id}/{item_id}/multi-quantity-delivery  更新商品多数量发货状态

商品回复（item_replay 表）：
- GET    /itemReplays                                  获取当前用户的所有商品回复信息
- GET    /itemReplays/cookie/{cookie_id}               获取指定Cookie的商品回复
- DELETE /item-reply/batch                             批量删除商品回复
- GET    /item-reply/{cookie_id}/{item_id}             获取商品回复
- PUT    /item-reply/{cookie_id}/{item_id}             更新商品回复
- DELETE /item-reply/{cookie_id}/{item_id}             删除商品回复

设计要点：
- 权限校验：cookie_id 必须属于当前用户（get_all_cookies 校验）
- 违禁词检查：create/update 时调用 forbidden_checker.check_text
- 商品搜索：调用 utils.item_search 异步函数
- 从账号拉取商品：调用 XianyuAutoAsync.XianyuLive 异步实例
- DBManager 已委托 item_repo，路由层仅调用 db_manager.* 即可
"""
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, optional_auth, server_error
from .models import (
    CreateItem,
    ItemDetailUpdate,
    ItemSearchRequest,
    ItemSearchMultipleRequest,
    BatchDeleteItemsRequest,
    BatchDeleteItemRepliesRequest,
    ItemReplyUpdate,
    MultiSpecUpdate,
    MultiQuantityDeliveryUpdate,
    GetAllFromAccountRequest,
    GetByPageRequest,
)

router = APIRouter(tags=["items"])


def _db():
    from db_manager import db_manager
    return db_manager


def _ensure_cookie_owned(cookie_id: str, user_id: int) -> None:
    """校验 cookie_id 属于当前用户，否则 403"""
    if cookie_id not in _db().get_all_cookies(user_id):
        raise HTTPException(status_code=403, detail="无权限操作该Cookie")


def _log_prefix(user_info: Optional[Dict[str, Any]]) -> str:
    if not user_info:
        return "【未登录】"
    return f"【{user_info.get('username', 'unknown')}#{user_info.get('user_id', 'unknown')}】"


# ==================== 商品信息（静态路径优先） ====================

@router.get("/items")
def get_all_items(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户的所有商品信息"""
    try:
        user_id = current_user['user_id']
        user_cookies = _db().get_all_cookies(user_id)

        all_items = []
        for cookie_id in user_cookies.keys():
            items = _db().get_items_by_cookie(cookie_id)
            for item in items:
                # 优先使用独立的 item_image 列；为空时尝试从 item_detail JSON 中提取 picUrl
                item_image = item.get('item_image', '') or ''
                if not item_image and item.get('item_detail'):
                    try:
                        detail = json.loads(item['item_detail'])
                        pic_url = (detail.get('pic_info') or {}).get('picUrl', '')
                        if pic_url:
                            item_image = pic_url
                    except (ValueError, TypeError):
                        pass
                # alicdn 支持 https，统一升级避免混合内容拦截
                if item_image and item_image.startswith('http://'):
                    item_image = 'https://' + item_image[len('http://'):]
                item['item_image'] = item_image
                item['is_multi_qty_ship'] = bool(item.get('multi_quantity_delivery', False))
                item['is_multi_spec'] = bool(item.get('is_multi_spec', False))
                all_items.append(item)

        return {"items": all_items}
    except Exception as e:
        raise server_error(e, "获取商品信息")


@router.post("/items/search")
async def search_items(
    search_request: ItemSearchRequest,
    current_user: Optional[Dict[str, Any]] = Depends(optional_auth),
):
    """搜索闲鱼商品"""
    user_info = _log_prefix(current_user)
    try:
        logger.info(
            f"{user_info} 开始单页搜索: 关键词='{search_request.keyword}', "
            f"页码={search_request.page}, 每页={search_request.page_size}"
        )

        from utils.item_search import search_xianyu_items

        result = await search_xianyu_items(
            keyword=search_request.keyword,
            page=search_request.page,
            page_size=search_request.page_size,
        )

        has_error = result.get("error")
        items_count = len(result.get("items", []))

        logger.info(
            f"{user_info} 单页搜索完成: 获取到 {items_count} 条数据"
            + (f", 错误: {has_error}" if has_error else "")
        )

        response_data = {
            "success": True,
            "data": result.get("items", []),
            "total": result.get("total", 0),
            "page": search_request.page,
            "page_size": search_request.page_size,
            "keyword": search_request.keyword,
            "is_real_data": result.get("is_real_data", False),
            "source": result.get("source", "unknown"),
        }
        if has_error:
            response_data["error"] = has_error
        return response_data
    except Exception as e:
        logger.error(f"{user_info} 商品搜索失败: {e}", exc_info=True)
        raise server_error(e, "商品搜索")


@router.post("/items/search_multiple")
async def search_multiple_pages(
    search_request: ItemSearchMultipleRequest,
    current_user: Optional[Dict[str, Any]] = Depends(optional_auth),
):
    """搜索多页闲鱼商品"""
    user_info = _log_prefix(current_user)
    try:
        logger.info(
            f"{user_info} 开始多页搜索: 关键词='{search_request.keyword}', "
            f"页数={search_request.total_pages}"
        )

        from utils.item_search import search_multiple_pages_xianyu

        result = await search_multiple_pages_xianyu(
            keyword=search_request.keyword,
            total_pages=search_request.total_pages,
        )

        has_error = result.get("error")
        items_count = len(result.get("items", []))

        logger.info(
            f"{user_info} 多页搜索完成: 获取到 {items_count} 条数据"
            + (f", 错误: {has_error}" if has_error else "")
        )

        response_data = {
            "success": True,
            "data": result.get("items", []),
            "total": result.get("total", 0),
            "total_pages": search_request.total_pages,
            "keyword": search_request.keyword,
            "is_real_data": result.get("is_real_data", False),
            "is_fallback": result.get("is_fallback", False),
            "source": result.get("source", "unknown"),
        }
        if has_error:
            response_data["error"] = has_error
        return response_data
    except Exception as e:
        logger.error(f"{user_info} 多页商品搜索失败: {str(e)}")
        raise server_error(e, "多页商品搜索")


@router.post("/items/get-all-from-account")
async def get_all_items_from_account(
    request: GetAllFromAccountRequest,
    _: None = Depends(require_auth),
):
    """从指定账号获取所有商品信息"""
    try:
        cookie_id = request.cookie_id
        if not cookie_id:
            return {"success": False, "message": "缺少cookie_id参数"}

        cookie_info = _db().get_cookie_by_id(cookie_id)
        if not cookie_info:
            return {"success": False, "message": "未找到指定的账号信息"}

        cookies_str = cookie_info.get('cookies_str', '')
        if not cookies_str:
            return {"success": False, "message": "账号cookie信息为空"}

        from XianyuAutoAsync import XianyuLive
        xianyu_instance = XianyuLive(cookies_str, cookie_id)

        logger.info(f"开始获取账号 {cookie_id} 的所有商品信息")
        result = await xianyu_instance.get_all_items()
        await xianyu_instance.close_session()

        if result.get('error'):
            logger.error(f"获取商品信息失败: {result['error']}")
            return {"success": False, "message": result['error']}

        total_count = result.get('total_count', 0)
        total_pages = result.get('total_pages', 1)
        saved_count = result.get('total_saved', 0)
        logger.info(
            f"成功获取账号 {cookie_id} 的 {total_count} 个商品（共{total_pages}页），保存 {saved_count} 个"
        )
        return {
            "success": True,
            "message": f"成功获取商品，共 {total_count} 件，保存 {saved_count} 件",
            "total_count": total_count,
            "total_pages": total_pages,
            "saved_count": saved_count,
        }
    except Exception as e:
        logger.error(f"获取账号商品信息异常: {str(e)}")
        from .deps import safe_client_msg
        return {"success": False, "message": safe_client_msg(e, "获取商品信息失败")}


@router.post("/items/get-by-page")
async def get_items_by_page(
    request: GetByPageRequest,
    _: None = Depends(require_auth),
):
    """从指定账号按页获取商品信息"""
    try:
        cookie_id = request.cookie_id
        page_number = request.page_number
        page_size = request.page_size

        if not cookie_id:
            return {"success": False, "message": "缺少cookie_id参数"}

        if page_number < 1:
            return {"success": False, "message": "页码必须大于0"}

        if page_size < 1 or page_size > 100:
            return {"success": False, "message": "每页数量必须在1-100之间"}

        account = _db().get_cookie_by_id(cookie_id)
        if not account:
            return {"success": False, "message": "账号不存在"}

        cookies_str = account['cookies_str']
        if not cookies_str:
            return {"success": False, "message": "账号cookies为空"}

        from XianyuAutoAsync import XianyuLive
        xianyu_instance = XianyuLive(cookies_str, cookie_id)

        logger.info(f"开始获取账号 {cookie_id} 第{page_number}页商品信息（每页{page_size}条）")
        result = await xianyu_instance.get_item_list_info(page_number, page_size)
        await xianyu_instance.close_session()

        if result.get('error'):
            logger.error(f"获取商品信息失败: {result['error']}")
            return {"success": False, "message": result['error']}

        current_count = result.get('current_count', 0)
        logger.info(f"成功获取账号 {cookie_id} 第{page_number}页 {current_count} 个商品")
        return {
            "success": True,
            "message": f"成功获取第{page_number}页 {current_count} 个商品，详细信息已打印到控制台",
            "page_number": page_number,
            "page_size": page_size,
            "current_count": current_count,
        }
    except Exception as e:
        logger.error(f"获取账号商品信息异常: {str(e)}")
        from .deps import safe_client_msg
        return {"success": False, "message": safe_client_msg(e, "获取商品信息失败")}


@router.delete("/items/batch")
def batch_delete_items(
    request: BatchDeleteItemsRequest,
    _: None = Depends(require_auth),
):
    """批量删除商品信息"""
    try:
        if not request.items:
            raise HTTPException(status_code=400, detail="删除列表不能为空")

        # 转为 dict 列表传给 db_manager（保持与原实现兼容）
        items_as_dicts = [item.dict() for item in request.items]
        success_count = _db().batch_delete_item_info(items_as_dicts)
        total_count = len(request.items)

        return {
            "message": "批量删除完成",
            "success_count": success_count,
            "total_count": total_count,
            "failed_count": total_count - success_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除商品信息异常: {e}")
        raise server_error(e, "批量删除商品")


@router.get("/items/cookie/{cookie_id}")
def get_items_by_cookie(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定 Cookie 的商品信息（完整字段）"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        items = _db().get_items_by_cookie(cookie_id)
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取商品信息")


# ==================== 商品信息（动态路径） ====================

@router.get("/items/{cid}")
def get_items_list(
    cid: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定账号的商品列表（摘要：item_id / item_title / item_price / created_at）"""
    try:
        _ensure_cookie_owned(cid, current_user['user_id'])
        items = _db().item_repo.get_item_list_by_cookie(cid)
        return {"items": items, "count": len(items)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取商品列表失败: {e}")
        raise server_error(e, "获取商品列表")


@router.post("/items/{cookie_id}")
def create_item(
    cookie_id: str,
    item_data: CreateItem,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """添加新商品"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        if not item_data.item_id or not item_data.item_id.strip():
            raise HTTPException(status_code=400, detail="商品ID不能为空")

        # 违禁词检查
        if item_data.item_title:
            from services.forbidden_words import ForbiddenWordChecker
            forbidden_checker = ForbiddenWordChecker()
            fw_result = forbidden_checker.check_text(item_data.item_title)
            if fw_result['has_forbidden']:
                logger.warning(f"商品 {item_data.item_id} 标题含违禁词: {fw_result['found_words']}")

        success = _db().item_repo.create_item(
            cookie_id=cookie_id,
            item_id=item_data.item_id.strip(),
            item_title=item_data.item_title or '',
            item_price=item_data.item_price or '',
            item_image=item_data.item_image or '',
            is_multi_spec=item_data.is_multi_spec,
            multi_quantity_delivery=item_data.is_multi_qty_ship,
        )
        if not success:
            raise HTTPException(status_code=400, detail=f"商品 {item_data.item_id} 已存在")

        return {"message": "商品添加成功", "item_id": item_data.item_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加商品失败: {str(e)}")
        raise server_error(e, "添加商品")


@router.get("/items/{cookie_id}/{item_id}")
def get_item_detail(
    cookie_id: str,
    item_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取商品详情"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        item = _db().get_item_info(cookie_id, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="商品不存在")
        return {"item": item}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取商品详情")


@router.put("/items/{cookie_id}/{item_id}")
def update_item_detail(
    cookie_id: str,
    item_id: str,
    update_data: ItemDetailUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新商品详情"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        item_detail = update_data.item_detail
        if item_detail:
            from services.forbidden_words import ForbiddenWordChecker
            forbidden_checker = ForbiddenWordChecker()
            fw_result = forbidden_checker.check_text(item_detail)
            if fw_result['has_forbidden']:
                logger.warning(f"商品 {item_id} 详情含违禁词: {fw_result['found_words']}")
                item_detail = fw_result['cleaned_text']

        success = _db().update_item_detail(cookie_id, item_id, item_detail)
        if success:
            return {"message": "商品详情更新成功"}
        raise HTTPException(status_code=400, detail="更新失败")
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "更新商品详情")


@router.delete("/items/{cookie_id}/{item_id}")
def delete_item_info(
    cookie_id: str,
    item_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """删除商品信息"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        success = _db().delete_item_info(cookie_id, item_id)
        if success:
            return {"message": "商品信息删除成功"}
        raise HTTPException(status_code=404, detail="商品信息不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除商品信息异常: {e}")
        raise server_error(e, "删除商品信息")


@router.put("/items/{cookie_id}/{item_id}/multi-spec")
def update_item_multi_spec(
    cookie_id: str,
    item_id: str,
    spec_data: MultiSpecUpdate,
    _: None = Depends(require_auth),
):
    """更新商品的多规格状态"""
    try:
        is_multi_spec = spec_data.is_multi_spec
        success = _db().update_item_multi_spec_status(cookie_id, item_id, is_multi_spec)
        if success:
            return {"message": f"商品多规格状态已{'开启' if is_multi_spec else '关闭'}"}
        raise HTTPException(status_code=404, detail="商品不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "更新商品多规格状态")


@router.put("/items/{cookie_id}/{item_id}/multi-quantity-delivery")
def update_item_multi_quantity_delivery(
    cookie_id: str,
    item_id: str,
    delivery_data: MultiQuantityDeliveryUpdate,
    _: None = Depends(require_auth),
):
    """更新商品的多数量发货状态"""
    try:
        multi_quantity_delivery = delivery_data.multi_quantity_delivery
        success = _db().update_item_multi_quantity_delivery_status(
            cookie_id, item_id, multi_quantity_delivery
        )
        if success:
            return {"message": f"商品多数量发货状态已{'开启' if multi_quantity_delivery else '关闭'}"}
        raise HTTPException(status_code=404, detail="商品不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "更新商品多数量发货状态")


# ==================== 商品回复（item_replay 表） ====================

@router.get("/itemReplays")
def get_all_item_replays(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户的所有商品回复信息"""
    try:
        user_id = current_user['user_id']
        user_cookies = _db().get_all_cookies(user_id)

        all_items = []
        for cookie_id in user_cookies.keys():
            items = _db().get_itemReplays_by_cookie(cookie_id)
            all_items.extend(items)
        return {"items": all_items}
    except Exception as e:
        raise server_error(e, "获取商品回复信息")


@router.get("/itemReplays/cookie/{cookie_id}")
def get_item_replays_by_cookie(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定 Cookie 的商品回复"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        items = _db().get_itemReplays_by_cookie(cookie_id)
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取商品回复")


@router.delete("/item-reply/batch")
def batch_delete_item_reply(
    req: BatchDeleteItemRepliesRequest,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """批量删除商品回复"""
    user_id = current_user['user_id']

    # 校验当前用户是否有权限删除每个 cookie 对应的回复
    user_cookies = _db().get_all_cookies(user_id)
    for item in req.items:
        if item.cookie_id not in user_cookies:
            raise HTTPException(status_code=403, detail=f"无权限访问Cookie {item.cookie_id}")

    result = _db().batch_delete_item_replies([item.dict() for item in req.items])
    return {
        "success_count": result["success_count"],
        "failed_count": result["failed_count"],
    }


@router.get("/item-reply/{cookie_id}/{item_id}")
def get_item_reply(
    cookie_id: str,
    item_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定账号和商品的回复内容"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        item_replies = _db().get_itemReplays_by_cookie(cookie_id)
        item_reply = next((r for r in item_replies if r['item_id'] == item_id), None)

        if item_reply is None:
            raise HTTPException(status_code=404, detail="商品回复不存在")
        return item_reply
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "获取商品回复")


@router.put("/item-reply/{cookie_id}/{item_id}")
def update_item_reply(
    cookie_id: str,
    item_id: str,
    data: ItemReplyUpdate,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新指定账号和商品的回复内容"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        reply_content = (data.reply_content or "").strip()
        if not reply_content:
            raise HTTPException(status_code=400, detail="回复内容不能为空")

        _db().update_item_reply(cookie_id=cookie_id, item_id=item_id, reply_content=reply_content)
        return {"message": "商品回复更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "更新商品回复")


@router.delete("/item-reply/{cookie_id}/{item_id}")
def delete_item_reply(
    cookie_id: str,
    item_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """删除指定账号和商品的回复"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        success = _db().delete_item_reply(cookie_id, item_id)
        if not success:
            raise HTTPException(status_code=404, detail="商品回复不存在")
        return {"message": "商品回复删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e, "删除商品回复")

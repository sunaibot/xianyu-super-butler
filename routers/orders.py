"""
routers/orders.py
============================
订单查询与管理路由。

从 reply_server.py 渐进迁移而来：
- GET    /api/orders                       订单列表（分页 + 筛选 + 搜索，复用 OrderRepo.get_all_item_titles 消除内联 N+1）
- GET    /api/orders/{order_id}            订单详情
- DELETE /api/orders/{order_id}            删除订单
- PUT    /api/orders/{order_id}            更新订单（数据不完整时通过 Playwright 自动补全）
- POST   /api/orders/refresh               智能刷新订单状态（并发处理）
- POST   /api/orders/manual-ship           手动发货（status_only / full_delivery）
- POST   /api/orders/import               批量导入订单
- POST   /api/orders/{order_id}/refresh    刷新单条订单状态

设计原则：
- 权限校验统一走 routers/deps.require_auth
- 订单归属校验：cookie_id 必须属于当前用户
- 错误响应统一走 routers/deps.server_error / client_error
- 路由顺序：静态路径（/refresh, /manual-ship, /import）在 /api/orders/{order_id} 之前
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger

from .deps import require_auth, server_error, safe_client_msg, log_with_user

router = APIRouter(tags=["orders"])


def _db():
    from db_manager import db_manager
    return db_manager


# ------------------------- 列表 / 详情 / 删除 -------------------------

@router.get('/api/orders')
def get_user_orders(
    current_user: Dict[str, Any] = Depends(require_auth),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    cookie_id: str = None,
    status: str = None,
    search: str = None,
):
    """获取当前用户的订单信息（支持分页和搜索）"""
    try:
        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"查询用户订单信息 (page={page}, page_size={page_size}, search={search})", current_user)

        # 获取用户的所有Cookie
        user_cookies = db.get_all_cookies(user_id)

        # 指定 cookie_id 筛选时只保留该账号
        if cookie_id and cookie_id in user_cookies:
            user_cookies = {cookie_id: user_cookies[cookie_id]}

        # 一次性获取所有 item_id → item_title 映射（替代原先内联全表扫描）
        item_titles = db.get_all_item_titles()

        search_lower = search.lower().strip() if search else None

        # 批量获取所有 cookie 的订单（单条 IN 查询），消除逐 cookie N+1
        all_orders = db.get_orders_by_cookies(user_cookies.keys(), limit_per_cookie=1000)

        # 内存中补充 item_title 与筛选
        filtered = []
        for order in all_orders:
            order['item_title'] = item_titles.get(order.get('item_id'), '')
            if status and order.get('status') != status:
                continue
            if search_lower:
                match = False
                for field in ['order_id', 'item_id', 'buyer_id', 'item_title', 'receiver_name', 'receiver_phone']:
                    val = str(order.get(field, '') or '').lower()
                    if search_lower in val:
                        match = True
                        break
                if not match:
                    continue
            filtered.append(order)
        all_orders = filtered

        # 按创建时间倒序
        all_orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # 分页
        total = len(all_orders)
        total_pages = (total + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_orders = all_orders[start_idx:end_idx]

        log_with_user('info', f"用户订单查询成功，共 {total} 条记录，第 {page}/{total_pages} 页", current_user)
        return {
            "success": True,
            "data": paginated_orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        log_with_user('error', f"查询用户订单失败: {e}", current_user)
        raise server_error(e, "查询订单")


@router.get('/api/orders/{order_id}')
def get_order_detail(order_id: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取订单详情"""
    try:
        db = _db()
        log_with_user('info', f"查询订单详情: {order_id}", current_user)

        user_cookies = db.get_all_cookies(current_user['user_id'])

        # 在用户的订单中查找（保留原实现的单次查询行为）
        order = db.get_order_by_id(order_id)
        if order and order.get('cookie_id') in user_cookies:
            log_with_user('info', f"订单详情查询成功: {order_id}", current_user)
            return {"success": True, "data": order}

        log_with_user('warning', f"订单不存在或无权访问: {order_id}", current_user)
        raise HTTPException(status_code=404, detail="订单不存在或无权访问")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"查询订单详情失败: {e}", current_user)
        raise server_error(e, "查询订单详情")


@router.delete('/api/orders/{order_id}')
def delete_order(order_id: str, current_user: Dict[str, Any] = Depends(require_auth)):
    """删除订单"""
    try:
        db = _db()
        log_with_user('info', f"删除订单: {order_id}", current_user)

        user_cookies = db.get_all_cookies(current_user['user_id'])

        order = db.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.get('cookie_id') not in user_cookies:
            raise HTTPException(status_code=403, detail="无权删除此订单")

        success = db.delete_order(order_id)
        if success:
            log_with_user('info', f"订单删除成功: {order_id}", current_user)
            return {"success": True, "message": "删除成功"}
        raise HTTPException(status_code=500, detail="删除失败")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除订单失败: {e}", current_user)
        raise server_error(e, "删除订单")


# ------------------------- 更新（含 Playwright 自动补全） -------------------------

def _check_order_data_completeness(order: Dict[str, Any]) -> bool:
    """检查订单数据是否完整（缺失关键字段时需触发刷新）"""
    incomplete_conditions = [
        not order.get('receiver_name') or order.get('receiver_name') == 'unknown',
        not order.get('receiver_phone') or order.get('receiver_phone') == 'unknown',
        not order.get('receiver_address') or order.get('receiver_address') == 'unknown',
        order.get('order_status') == 'unknown',
        not order.get('buyer_id') or order.get('buyer_id') == 'unknown',
    ]
    return not any(incomplete_conditions)


def _map_order_status(order_status):
    """数字状态码 → 文本状态"""
    if order_status and str(order_status).isdigit():
        status_mapping = {
            '1': 'processing', '2': 'pending_ship', '3': 'shipped', '4': 'completed',
            '5': 'refunding', '6': 'cancelled', '7': 'refunding', '8': 'cancelled',
            '9': 'refunding', '10': 'cancelled', '11': 'completed', '12': 'cancelled',
        }
        return status_mapping.get(str(order_status), order_status)
    return order_status


@router.put('/api/orders/{order_id}')
async def update_order(
    order_id: str,
    update_data: dict,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新订单信息；数据不完整时通过 Playwright 自动补全。

    自动补全依赖 utils.order_fetcher_optimized.fetch_order_complete，
    如该模块缺失则降级为仅写入用户提交的字段。
    """
    try:
        db = _db()
        update_fields = dict(update_data)
        log_with_user('info', f"更新订单: {order_id}, 数据: {update_fields}", current_user)

        user_cookies = db.get_all_cookies(current_user['user_id'])

        order = db.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.get('cookie_id') not in user_cookies:
            raise HTTPException(status_code=403, detail="无权修改此订单")

        is_complete = _check_order_data_completeness(order)

        if not is_complete:
            log_with_user('info', f"订单 {order_id} 数据不完整，尝试使用 Playwright 获取完整数据", current_user)
            cookie_id = order.get('cookie_id')
            cookie_string = user_cookies.get(cookie_id)

            if cookie_string:
                try:
                    from utils.order_fetcher_optimized import fetch_order_complete
                    complete_result = await fetch_order_complete(
                        order_id=order_id,
                        cookie_id=cookie_id,
                        cookie_string=cookie_string,
                        timeout=30,
                        headless=True,
                        use_pool=True,
                    )

                    if complete_result:
                        log_with_user('info', f"成功获取订单 {order_id} 的完整数据", current_user)
                        order_status = _map_order_status(complete_result.get('order_status', 'unknown'))
                        refresh_data = {
                            'order_id': order_id,
                            'item_id': complete_result.get('item_id') or order.get('item_id'),
                            'buyer_id': complete_result.get('buyer_id') or order.get('buyer_id'),
                            'order_status': order_status or order.get('order_status'),
                            'spec_name': complete_result.get('spec_name') or None,
                            'spec_value': complete_result.get('spec_value') or None,
                            'quantity': complete_result.get('quantity') or None,
                            'amount': complete_result.get('amount') or None,
                            'created_at': complete_result.get('order_time') or None,
                            'receiver_name': complete_result.get('receiver_name') or None,
                            'receiver_phone': complete_result.get('receiver_phone') or None,
                            'receiver_address': complete_result.get('receiver_address') or None,
                        }
                        db.insert_or_update_order(**refresh_data)
                        log_with_user('info', f"订单 {order_id} 完整数据已更新到数据库", current_user)
                    else:
                        log_with_user('warning', f"订单 {order_id} 详情获取失败，继续使用现有数据", current_user)
                except ImportError:
                    log_with_user('warning', f"utils.order_fetcher_optimized 不可用，跳过 Playwright 补全", current_user)
                except Exception as e:
                    log_with_user('error', f"获取订单 {order_id} 详情时出错: {e}", current_user)
            else:
                log_with_user('warning', f"订单 {order_id} 的Cookie信息不完整，无法刷新", current_user)

        # 仅允许更新的字段白名单
        allowed_fields = {
            'item_id', 'buyer_id', 'spec_name', 'spec_value',
            'quantity', 'amount', 'order_status',
            'receiver_name', 'receiver_phone', 'receiver_address',
            'system_shipped', 'created_at',
        }
        filtered_data = {k: v for k, v in update_fields.items() if k in allowed_fields}

        if not filtered_data:
            updated_order = db.get_order_by_id(order_id)
            if not is_complete:
                return {
                    "success": True,
                    "message": "订单数据已自动刷新",
                    "data": updated_order,
                    "refreshed": True,
                }
            return {
                "success": True,
                "message": "订单数据已是最新",
                "data": updated_order,
                "refreshed": False,
            }

        success = db.insert_or_update_order(order_id=order_id, **filtered_data)
        if success:
            log_with_user('info', f"订单更新成功: {order_id}", current_user)
            updated_order = db.get_order_by_id(order_id)
            return {
                "success": True,
                "message": "更新成功",
                "data": updated_order,
                "refreshed": not is_complete,
            }
        raise HTTPException(status_code=500, detail="更新失败")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"更新订单失败: {e}", current_user)
        raise server_error(e, "更新订单")


# ------------------------- 智能刷新 -------------------------

# 稳定状态（无需刷新）
_STABLE_STATUSES = {'shipped', 'completed', 'cancelled'}


@router.post('/api/orders/refresh')
async def refresh_orders_status(
    cookie_id: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """
    智能刷新订单状态
    1. 从数据库获取订单列表（支持筛选）
    2. 对非'已发货'状态的订单，使用Playwright查询最新状态
    3. 更新数据库中有变化的订单
    """
    try:
        from utils.order_fetcher_optimized import process_orders_batch

        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"开始智能刷新订单状态（优化版：并发处理） (cookie_id={cookie_id}, status={status})", current_user)

        # 获取用户的所有Cookie
        user_cookies = db.get_all_cookies(user_id)

        # 如果指定了cookie_id，只使用该Cookie
        if cookie_id:
            if cookie_id not in user_cookies:
                raise HTTPException(status_code=404, detail="Cookie不存在或无权访问")
            user_cookies = {cookie_id: user_cookies[cookie_id]}

        # 获取需要刷新的订单
        orders_to_refresh = []
        for cid in user_cookies.keys():
            orders = db.get_orders_by_cookie(cid, limit=1000)
            for order in orders:
                if status and order.get('status') != status:
                    continue
                order_status = order.get('status', 'unknown')
                needs_refresh = order_status not in _STABLE_STATUSES
                if needs_refresh:
                    orders_to_refresh.append({
                        'order_id': order['order_id'],
                        'cookie_id': cid,
                        'current_status': order_status,
                    })

        log_with_user('info', f"找到 {len(orders_to_refresh)} 个需要刷新的订单", current_user)

        if not orders_to_refresh:
            return JSONResponse({
                "success": True,
                "message": "没有需要刷新的订单",
                "summary": {"total": 0, "updated": 0, "no_change": 0, "failed": 0},
                "results": [],
            })

        updated_count = 0
        failed_count = 0
        no_change_count = 0
        refresh_results = []

        # 按cookie_id分组订单
        orders_by_cookie: Dict[str, list] = {}
        for order_info in orders_to_refresh:
            cid = order_info['cookie_id']
            orders_by_cookie.setdefault(cid, []).append(order_info)

        # 对每个cookie的订单进行并发批量处理
        for cid, cookie_orders in orders_by_cookie.items():
            cookies_str = user_cookies[cid]
            if not cookies_str:
                log_with_user('warning', f"Cookie {cid} 的值为空，跳过", current_user)
                failed_count += len(cookie_orders)
                continue

            order_ids = [o['order_id'] for o in cookie_orders]
            log_with_user('info', f"使用并发处理Cookie {cid} 的 {len(order_ids)} 个订单", current_user)

            batch_results = await process_orders_batch(
                order_ids=order_ids,
                cookie_id=cid,
                cookie_string=cookies_str,
                max_concurrent=5,
                timeout=30,
                headless=True,
                use_pool=True,
                force_refresh=True,
            )

            for i, result in enumerate(batch_results):
                order_info = cookie_orders[i]
                order_id = order_info['order_id']
                current_status = order_info['current_status']

                if result and not result.get('error'):
                    api_status = result.get('api_status', 'N/A')
                    dom_status = result.get('dom_status', 'N/A')
                    log_with_user('debug', f"订单 {order_id} - API状态: {api_status}, DOM状态: {dom_status}", current_user)

                    order_status = _map_order_status(result.get('order_status', 'unknown'))

                    success = db.insert_or_update_order(
                        order_id=order_id,
                        item_id=result.get('item_id') or None,
                        buyer_id=result.get('buyer_id') or None,
                        spec_name=result.get('spec_name') or None,
                        spec_value=result.get('spec_value') or None,
                        quantity=result.get('quantity') or None,
                        amount=result.get('amount') or None,
                        order_status=order_status if order_status != current_status else None,
                        cookie_id=cid,
                        created_at=result.get('order_time') or None,
                        receiver_name=result.get('receiver_name') or None,
                        receiver_phone=result.get('receiver_phone') or None,
                        receiver_address=result.get('receiver_address') or None,
                    )

                    if success:
                        has_changes = (
                            order_status != current_status
                            or result.get('buyer_id')
                            or result.get('amount')
                        )
                        if has_changes:
                            updated_count += 1
                            refresh_results.append({
                                'order_id': order_id,
                                'old_status': current_status,
                                'new_status': order_status,
                                'status_text': result.get('status_text', ''),
                            })
                            log_with_user('info', f"订单 {order_id} 已更新 | {current_status} -> {order_status}", current_user)
                        else:
                            no_change_count += 1
                    else:
                        failed_count += 1
                        log_with_user('error', f"订单 {order_id} 更新失败", current_user)
                else:
                    failed_count += 1
                    error_msg = result.get('error', '未知错误') if result else '未知错误'
                    log_with_user('warning', f"订单 {order_id} 获取失败: {error_msg}", current_user)

        log_with_user('info', f"订单刷新完成: 更新{updated_count}个, 无变化{no_change_count}个, 失败{failed_count}个", current_user)

        return JSONResponse({
            "success": True,
            "message": f"刷新完成: 更新{updated_count}个, 无变化{no_change_count}个, 失败{failed_count}个",
            "summary": {
                "total": len(orders_to_refresh),
                "updated": updated_count,
                "no_change": no_change_count,
                "failed": failed_count,
            },
            "updated_orders": refresh_results,
        })

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"刷新订单状态失败: {str(e)}", current_user)
        raise server_error(e, "刷新订单状态")


@router.post('/api/orders/{order_id}/refresh')
async def refresh_single_order(
    order_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """刷新单条订单状态"""
    try:
        from utils.order_fetcher_optimized import process_orders_batch

        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"刷新单条订单: {order_id}", current_user)

        user_cookies = db.get_all_cookies(user_id)

        order = db.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        cookie_id = order.get('cookie_id')
        if not cookie_id or cookie_id not in user_cookies:
            raise HTTPException(status_code=403, detail="无权刷新此订单")

        cookies_str = user_cookies[cookie_id]
        if not cookies_str:
            raise HTTPException(status_code=400, detail="Cookie无效")

        batch_results = await process_orders_batch(
            order_ids=[order_id],
            cookie_id=cookie_id,
            cookie_string=cookies_str,
            max_concurrent=1,
            timeout=30,
            headless=True,
            use_pool=True,
            force_refresh=True,
        )

        if not batch_results or len(batch_results) == 0:
            raise HTTPException(status_code=500, detail="刷新失败")

        result = batch_results[0]
        if result.get('error'):
            raise HTTPException(status_code=500, detail=f"刷新失败: {result.get('error')}")

        order_status = _map_order_status(result.get('order_status', 'unknown'))

        db.insert_or_update_order(
            order_id=order_id,
            item_id=result.get('item_id') or None,
            buyer_id=result.get('buyer_id') or None,
            spec_name=result.get('spec_name') or None,
            spec_value=result.get('spec_value') or None,
            quantity=result.get('quantity') or None,
            amount=result.get('amount') or None,
            order_status=order_status,
            cookie_id=cookie_id,
            receiver_name=result.get('receiver_name') or None,
            receiver_phone=result.get('receiver_phone') or None,
            receiver_address=result.get('receiver_address') or None,
        )

        log_with_user('info', f"订单刷新成功: {order_id}, 新状态: {order_status}", current_user)
        return JSONResponse({
            "success": True,
            "message": "订单刷新成功",
            "data": {
                "order_id": order_id,
                "order_status": order_status,
            },
        })

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"刷新订单失败: {str(e)}", current_user)
        raise server_error(e, "刷新订单")


# ------------------------- 手动发货 -------------------------

@router.post('/api/orders/manual-ship')
async def manual_ship_orders(
    order_ids: List[str] = Body(..., description="订单ID列表"),
    ship_mode: str = Body(..., description="发货模式: status_only 或 full_delivery"),
    custom_content: Optional[str] = Body(None, description="自定义发货内容（保留兼容）"),
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """
    手动发货

    发货模式：
    - status_only: 仅在闲鱼标记为已发货（不发送卡券给买家）
    - full_delivery: 完整发货流程（匹配卡券、发送卡券给买家、标记发货状态）
    """
    try:
        import asyncio
        from XianyuAutoAsync import XianyuLive

        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"开始手动发货: 订单数量={len(order_ids)}, 模式={ship_mode}", current_user)

        if ship_mode not in ['status_only', 'full_delivery']:
            raise HTTPException(status_code=400, detail="发货模式必须是 status_only 或 full_delivery")

        user_cookies = db.get_all_cookies(user_id)

        success_count = 0
        failed_count = 0
        results = []

        for order_id in order_ids:
            try:
                order = db.get_order_by_id(order_id)
                if not order:
                    results.append({'order_id': order_id, 'success': False, 'message': '订单不存在'})
                    failed_count += 1
                    continue

                cookie_id = order.get('cookie_id')
                if cookie_id not in user_cookies:
                    results.append({'order_id': order_id, 'success': False, 'message': '无权操作此订单'})
                    failed_count += 1
                    continue

                item_id = order.get('item_id')
                buyer_id = order.get('buyer_id')

                if ship_mode == 'status_only':
                    if not item_id:
                        results.append({'order_id': order_id, 'success': False, 'message': '订单缺少商品ID'})
                        failed_count += 1
                        continue

                    cookies_str = user_cookies.get(cookie_id)
                    if not cookies_str:
                        results.append({'order_id': order_id, 'success': False, 'message': '无法获取账号Cookie信息'})
                        failed_count += 1
                        continue

                    import aiohttp
                    from secure_confirm_decrypted import SecureConfirm

                    try:
                        async with aiohttp.ClientSession(
                            headers={'cookie': cookies_str},
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as session:
                            confirm = SecureConfirm(session, cookies_str, cookie_id, None)
                            confirm_result = await confirm.auto_confirm(order_id, item_id)

                        if confirm_result and confirm_result.get('success'):
                            db.insert_or_update_order(order_id=order_id, order_status='shipped', system_shipped=True)
                            results.append({'order_id': order_id, 'success': True, 'message': '已成功修改闲鱼发货状态'})
                            success_count += 1
                        else:
                            error_msg = confirm_result.get('error', '未知错误') if confirm_result else '确认发货返回空结果'
                            results.append({'order_id': order_id, 'success': False, 'message': f'修改发货状态失败: {error_msg}'})
                            failed_count += 1
                    except Exception as e:
                        log_with_user('error', f"确认发货异常: {str(e)}", current_user)
                        results.append({'order_id': order_id, 'success': False, 'message': safe_client_msg(e, "确认发货失败")})
                        failed_count += 1

                elif ship_mode == 'full_delivery':
                    if not item_id:
                        results.append({'order_id': order_id, 'success': False, 'message': '订单缺少商品ID，无法匹配发货规则'})
                        failed_count += 1
                        continue
                    if not buyer_id:
                        results.append({'order_id': order_id, 'success': False, 'message': '订单缺少买家ID，无法发送卡券'})
                        failed_count += 1
                        continue

                    live_instance = XianyuLive.get_instance(cookie_id)
                    if not live_instance:
                        results.append({'order_id': order_id, 'success': False, 'message': '该账号未在线运行，无法执行完整发货。请先启动账号。'})
                        failed_count += 1
                        continue
                    if not live_instance.ws or live_instance.ws.closed:
                        results.append({'order_id': order_id, 'success': False, 'message': '该账号WebSocket连接已断开，无法发送消息。请等待重连后重试。'})
                        failed_count += 1
                        continue

                    chat_id = order.get('chat_id') or ''
                    if not chat_id:
                        chat_id = db.find_chat_id_by_buyer(cookie_id, buyer_id)
                    if not chat_id:
                        results.append({'order_id': order_id, 'success': False, 'message': '未找到与该买家的聊天记录，无法发送卡券消息。请等待买家发送消息后重试。'})
                        failed_count += 1
                        continue

                    # 检查多数量发货
                    quantity_to_send = 1
                    multi_quantity_delivery = db.get_item_multi_quantity_delivery_status(cookie_id, item_id)
                    if multi_quantity_delivery:
                        try:
                            order_detail = await live_instance.fetch_order_detail_info(order_id, item_id, buyer_id)
                            if order_detail and isinstance(order_detail, dict):
                                qty = order_detail.get('quantity', 1)
                                if isinstance(qty, int) and qty > 1:
                                    quantity_to_send = qty
                        except Exception as e:
                            log_with_user('warning', f"获取订单数量失败，使用默认数量1: {str(e)}", current_user)

                    delivery_contents = []
                    for i in range(quantity_to_send):
                        try:
                            delivery_content = await live_instance._auto_delivery(item_id, '', order_id, buyer_id)
                            if delivery_content:
                                delivery_contents.append(delivery_content)
                        except Exception as e:
                            log_with_user('error', f"获取第{i+1}个卡券失败: {str(e)}", current_user)

                    if not delivery_contents:
                        results.append({'order_id': order_id, 'success': False, 'message': '未匹配到发货规则或卡券获取失败'})
                        failed_count += 1
                        continue

                    send_success = True
                    for idx, content in enumerate(delivery_contents):
                        try:
                            if content.startswith("__IMAGE_SEND__"):
                                image_data = content.replace("__IMAGE_SEND__", "")
                                card_id = None
                                if "|" in image_data:
                                    card_id_str, image_url = image_data.split("|", 1)
                                    try:
                                        card_id = int(card_id_str)
                                    except ValueError:
                                        card_id = None
                                else:
                                    image_url = image_data
                                await live_instance.send_image_msg(
                                    live_instance.ws, chat_id, buyer_id, image_url, card_id=card_id,
                                )
                            else:
                                await live_instance.send_msg(live_instance.ws, chat_id, buyer_id, content)

                            if len(delivery_contents) > 1 and idx < len(delivery_contents) - 1:
                                await asyncio.sleep(1)
                        except Exception as e:
                            log_with_user('error', f"发送第{idx+1}条卡券消息失败: {str(e)}", current_user)
                            send_success = False

                    db.insert_or_update_order(order_id=order_id, order_status='shipped', system_shipped=True)

                    if send_success:
                        results.append({'order_id': order_id, 'success': True, 'message': f'完整发货成功，已发送{len(delivery_contents)}条卡券信息给买家'})
                        success_count += 1
                    else:
                        results.append({'order_id': order_id, 'success': True, 'message': f'发货状态已更新，但部分卡券消息发送失败（共{len(delivery_contents)}条）'})
                        success_count += 1

            except Exception as e:
                results.append({'order_id': order_id, 'success': False, 'message': safe_client_msg(e, "操作失败")})
                failed_count += 1
                log_with_user('error', f"发货订单 {order_id} 时发生异常: {str(e)}", current_user)

        log_with_user('info', f"手动发货完成: 成功{success_count}个, 失败{failed_count}个", current_user)

        return {
            "success": True,
            "message": f"发货完成: 成功{success_count}个, 失败{failed_count}个",
            "total": len(order_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"手动发货失败: {str(e)}", current_user)
        raise server_error(e, "手动发货")


# ------------------------- 批量导入 -------------------------

@router.post('/api/orders/import')
async def import_orders(
    orders: List[Dict[str, Any]] = Body(..., description="订单列表"),
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """
    导入订单
    支持批量导入自定义订单数据
    """
    try:
        db = _db()
        user_id = current_user['user_id']
        log_with_user('info', f"开始导入订单: 订单数量={len(orders)}", current_user)

        user_cookies = db.get_all_cookies(user_id)

        success_count = 0
        failed_count = 0
        results = []

        required_fields = ['order_id', 'cookie_id']
        param_mapping = {
            'item_id': 'item_id',
            'buyer_id': 'buyer_id',
            'receiver_name': 'receiver_name',
            'receiver_phone': 'receiver_phone',
            'receiver_address': 'receiver_address',
            'receiver_city': 'receiver_city',
            'status': 'order_status',  # 前端用 status，后端用 order_status
            'status_text': 'status_text',
            'order_time': 'order_time',
            'pay_time': 'pay_time',
            'quantity': 'quantity',
            'amount': 'amount',
            'item_title': 'item_title',
            'item_price': 'item_price',
            'item_image': 'item_image',
        }

        for order_data in orders:
            try:
                missing_fields = [f for f in required_fields if not order_data.get(f)]
                if missing_fields:
                    results.append({
                        'order_id': order_data.get('order_id', 'unknown'),
                        'success': False,
                        'message': f'缺少必需字段: {", ".join(missing_fields)}',
                    })
                    failed_count += 1
                    continue

                order_id = str(order_data['order_id'])
                cookie_id = str(order_data['cookie_id'])

                if cookie_id not in user_cookies:
                    results.append({'order_id': order_id, 'success': False, 'message': '无权操作此账号的订单'})
                    failed_count += 1
                    continue

                existing_order = db.get_order_by_id(order_id)

                insert_params = {'order_id': order_id, 'cookie_id': cookie_id}
                for field, value in order_data.items():
                    if value is not None and field in param_mapping:
                        insert_params[param_mapping[field]] = value

                db.insert_or_update_order(**insert_params)

                results.append({
                    'order_id': order_id,
                    'success': True,
                    'message': '订单已更新' if existing_order else '订单已导入',
                })
                success_count += 1

            except Exception as e:
                results.append({
                    'order_id': order_data.get('order_id', 'unknown'),
                    'success': False,
                    'message': safe_client_msg(e, "操作失败"),
                })
                failed_count += 1
                log_with_user('error', f"导入订单时发生异常: {str(e)}", current_user)

        log_with_user('info', f"导入订单完成: 成功{success_count}个, 失败{failed_count}个", current_user)

        return {
            "success": True,
            "message": f"导入完成: 成功{success_count}个, 失败{failed_count}个",
            "total": len(orders),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"导入订单失败: {str(e)}", current_user)
        raise server_error(e, "导入订单")

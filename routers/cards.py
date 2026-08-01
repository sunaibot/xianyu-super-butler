"""
routers/cards.py
================
卡券管理路由（从 reply_server.py 迁移）。

路由清单：
- GET    /cards                获取当前用户的卡券列表
- POST   /cards                创建新卡券（支持多规格）
- GET    /cards/{card_id}      获取单个卡券详情
- PUT    /cards/{card_id}      更新卡券
- PUT    /cards/{card_id}/image 更新带图片的卡券（multipart/form-data）
- DELETE /cards/{card_id}      删除卡券

设计要点：
- 用户隔离：列表/详情/创建按 user_id 过滤；更新/删除暂不校验归属（与原实现一致）
- 多规格：is_multi_spec=true 时必须提供 spec_name + spec_value
- 图片上传：复用 image_manager 单例，保存失败时回滚已存图片
- 权限：全部需要登录（require_auth）
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from loguru import logger

from .deps import require_auth, server_error, client_error, log_with_user

router = APIRouter(tags=["cards"])


def _db():
    from db_manager import db_manager
    return db_manager


# ------------------------- 列表 / 详情 -------------------------

@router.get("/cards")
def get_cards(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户的卡券列表"""
    try:
        user_id = current_user['user_id']
        return _db().get_all_cards(user_id)
    except Exception as e:
        log_with_user('error', f"获取卡券列表失败: {e}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/cards/{card_id}")
def get_card(card_id: int, current_user: Dict[str, Any] = Depends(require_auth)):
    """获取单个卡券详情"""
    try:
        user_id = current_user['user_id']
        card = _db().get_card_by_id(card_id, user_id)
        if card:
            return card
        raise HTTPException(status_code=404, detail="卡券不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"获取卡券失败: {card_id} - {e}", current_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ------------------------- 创建 / 更新 / 删除 -------------------------

@router.post("/cards")
def create_card(card_data: dict, current_user: Dict[str, Any] = Depends(require_auth)):
    """创建新卡券（支持多规格）"""
    try:
        user_id = current_user['user_id']
        card_name = card_data.get('name', '未命名卡券')
        log_with_user('info', f"创建卡券: {card_name}", current_user)

        is_multi_spec = card_data.get('is_multi_spec', False)
        if is_multi_spec:
            if not card_data.get('spec_name') or not card_data.get('spec_value'):
                raise HTTPException(status_code=400, detail="多规格卡券必须提供规格名称和规格值")

        card_id = _db().create_card(
            name=card_data.get('name'),
            card_type=card_data.get('type'),
            api_config=card_data.get('api_config'),
            text_content=card_data.get('text_content'),
            data_content=card_data.get('data_content'),
            image_url=card_data.get('image_url'),
            description=card_data.get('description'),
            enabled=card_data.get('enabled', True),
            delay_seconds=card_data.get('delay_seconds', 0),
            is_multi_spec=is_multi_spec,
            spec_name=card_data.get('spec_name') if is_multi_spec else None,
            spec_value=card_data.get('spec_value') if is_multi_spec else None,
            user_id=user_id,
        )

        log_with_user('info', f"卡券创建成功: {card_name} (ID: {card_id})", current_user)
        return {"id": card_id, "message": "卡券创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"创建卡券失败: {card_data.get('name', '未知')} - {e}", current_user)
        raise client_error(e, "创建卡券")


@router.put("/cards/{card_id}")
def update_card(card_id: int, card_data: dict, current_user: Dict[str, Any] = Depends(require_auth)):
    """更新卡券"""
    try:
        is_multi_spec = card_data.get('is_multi_spec')
        if is_multi_spec:
            if not card_data.get('spec_name') or not card_data.get('spec_value'):
                raise HTTPException(status_code=400, detail="多规格卡券必须提供规格名称和规格值")

        success = _db().update_card(
            card_id=card_id,
            name=card_data.get('name'),
            card_type=card_data.get('type'),
            api_config=card_data.get('api_config'),
            text_content=card_data.get('text_content'),
            data_content=card_data.get('data_content'),
            image_url=card_data.get('image_url'),
            description=card_data.get('description'),
            enabled=card_data.get('enabled', True),
            delay_seconds=card_data.get('delay_seconds'),
            is_multi_spec=is_multi_spec,
            spec_name=card_data.get('spec_name'),
            spec_value=card_data.get('spec_value'),
        )
        if success:
            return {"message": "卡券更新成功"}
        raise HTTPException(status_code=404, detail="卡券不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"更新卡券失败: {card_id} - {e}", current_user)
        raise server_error(e, "更新卡券")


@router.put("/cards/{card_id}/image")
async def update_card_with_image(
    card_id: int,
    image: UploadFile = File(...),
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(default=""),
    delay_seconds: int = Form(default=0),
    enabled: bool = Form(default=True),
    is_multi_spec: bool = Form(default=False),
    spec_name: str = Form(default=""),
    spec_value: str = Form(default=""),
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新带图片的卡券（multipart/form-data）"""
    try:
        logger.info(f"接收到带图片的卡券更新请求: card_id={card_id}, name={name}, type={type}")

        if not image.content_type or not image.content_type.startswith('image/'):
            logger.warning(f"无效的图片文件类型: {image.content_type}")
            raise HTTPException(status_code=400, detail="请上传图片文件")

        if is_multi_spec:
            if not spec_name or not spec_value:
                raise HTTPException(status_code=400, detail="多规格卡券必须提供规格名称和规格值")

        image_data = await image.read()
        logger.info(f"读取图片数据成功，大小: {len(image_data)} bytes")

        # 延迟导入 image_manager 单例
        import image_manager
        image_url = image_manager.save_image(image_data, image.filename)
        if not image_url:
            logger.error("图片保存失败")
            raise HTTPException(status_code=400, detail="图片保存失败")
        logger.info(f"图片保存成功: {image_url}")

        success = _db().update_card(
            card_id=card_id,
            name=name,
            card_type=type,
            image_url=image_url,
            description=description,
            enabled=enabled,
            delay_seconds=delay_seconds,
            is_multi_spec=is_multi_spec,
            spec_name=spec_name if is_multi_spec else None,
            spec_value=spec_value if is_multi_spec else None,
        )

        if success:
            logger.info(f"卡券更新成功: {name} (ID: {card_id})")
            return {"message": "卡券更新成功", "image_url": image_url}

        # 数据库更新失败 → 删除已保存的图片
        image_manager.delete_image(image_url)
        raise HTTPException(status_code=404, detail="卡券不存在")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新带图片的卡券失败: {e}")
        raise server_error(e, "更新卡券图片")


@router.delete("/cards/{card_id}")
def delete_card(card_id: int, current_user: Dict[str, Any] = Depends(require_auth)):
    """删除卡券"""
    try:
        success = _db().delete_card(card_id)
        if success:
            log_with_user('info', f"卡券删除成功: ID {card_id}", current_user)
            return {"message": "卡券删除成功"}
        raise HTTPException(status_code=404, detail="卡券不存在")
    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除卡券失败: {card_id} - {e}", current_user)
        raise server_error(e, "删除卡券")

"""
routers/ai_reply.py
===================
AI 回复管理路由（从 reply_server.py 迁移）。

路由清单：
- GET  /ai-reply-settings/{cookie_id}  获取指定账号的 AI 回复设置
- PUT  /ai-reply-settings/{cookie_id}  更新指定账号的 AI 回复设置
- GET  /ai-reply-settings              获取当前用户所有账号的 AI 回复设置
- POST /ai-reply-test/{cookie_id}      测试 AI 回复功能（调用 ai_reply_engine 生成回复）

设计要点：
- 权限：cookie_id 必须属于当前用户（get_all_cookies 校验）
- DBManager 已委托 ai_reply_repo，路由层仅调用 db_manager.* 即可
- ai_reply_engine 为全局单例，直接 import 使用
- 系统级 AI 配置兜底逻辑封装在 ai_reply_repo.get_ai_reply_settings 内
"""
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, server_error
from .models import AIReplySettings, AIReplyTestIn

router = APIRouter(tags=["ai-reply"])


def _db():
    from db_manager import db_manager
    return db_manager


def _ensure_cookie_owned(cookie_id: str, user_id: int) -> None:
    """校验 cookie_id 属于当前用户，否则 403"""
    if cookie_id not in _db().get_all_cookies(user_id):
        raise HTTPException(status_code=403, detail="无权限操作该Cookie")


# ------------------------- 单账号设置 -------------------------

@router.get("/ai-reply-settings/{cookie_id}")
def get_ai_reply_settings(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """获取指定账号的 AI 回复设置"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])
        return _db().get_ai_reply_settings(cookie_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取AI回复设置异常: {e}")
        raise server_error(e, "获取AI回复设置")


@router.put("/ai-reply-settings/{cookie_id}")
def update_ai_reply_settings(
    cookie_id: str,
    settings: AIReplySettings,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """更新指定账号的 AI 回复设置"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        import cookie_manager
        if cookie_manager.manager is None:
            raise HTTPException(status_code=500, detail='CookieManager 未就绪')

        settings_dict = settings.dict()
        success = _db().save_ai_reply_settings(cookie_id, settings_dict)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")

        if settings.ai_enabled:
            logger.info(f"账号 {cookie_id} 启用AI回复")
        else:
            logger.info(f"账号 {cookie_id} 禁用AI回复")
        return {"message": "AI回复设置更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新AI回复设置异常: {e}")
        raise server_error(e, "更新AI回复设置")


# ------------------------- 全部账号设置 -------------------------

@router.get("/ai-reply-settings")
def get_all_ai_reply_settings(current_user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户所有账号的 AI 回复设置（按用户过滤）"""
    try:
        user_id = current_user['user_id']
        user_cookies = _db().get_all_cookies(user_id)

        all_settings = _db().get_all_ai_reply_settings()
        # 过滤只属于当前用户的设置
        return {cid: s for cid, s in all_settings.items() if cid in user_cookies}
    except Exception as e:
        logger.error(f"获取所有AI回复设置异常: {e}")
        raise server_error(e, "获取所有AI回复设置")


# ------------------------- AI 回复测试 -------------------------

@router.post("/ai-reply-test/{cookie_id}")
def test_ai_reply(
    cookie_id: str,
    test_data: AIReplyTestIn,
    current_user: Dict[str, Any] = Depends(require_auth),
):
    """测试 AI 回复功能（调用 ai_reply_engine 生成回复）"""
    try:
        _ensure_cookie_owned(cookie_id, current_user['user_id'])

        import cookie_manager
        if cookie_manager.manager is None:
            raise HTTPException(status_code=500, detail='CookieManager 未就绪')
        if cookie_id not in cookie_manager.manager.cookies:
            raise HTTPException(status_code=404, detail='账号不存在')

        # 延迟导入 ai_reply_engine 单例（避免模块级循环依赖）
        from ai_reply_engine import ai_reply_engine

        if not ai_reply_engine.is_ai_enabled(cookie_id):
            raise HTTPException(status_code=400, detail='该账号未启用AI回复')

        settings = _db().get_ai_reply_settings(cookie_id)
        if not settings.get('api_key'):
            raise HTTPException(status_code=400, detail='未配置API Key，请先在AI设置中配置API Key')
        if not settings.get('base_url'):
            raise HTTPException(status_code=400, detail='未配置API地址，请先在AI设置中配置API地址')

        test_item_info = {
            'title': test_data.item_title,
            'price': test_data.item_price,
            'desc': test_data.item_desc,
        }

        reply = ai_reply_engine.generate_reply(
            message=test_data.message,
            item_info=test_item_info,
            chat_id=f"test_{int(time.time())}",
            cookie_id=cookie_id,
            user_id="test_user",
            item_id="test_item",
            skip_wait=True,  # 测试时跳过10秒等待
        )

        if reply:
            return {"message": "测试成功", "reply": reply}
        raise HTTPException(
            status_code=400,
            detail="AI回复生成失败，请检查API Key是否正确、API地址是否可访问",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试AI回复异常: {e}", exc_info=True)
        raise server_error(e, "测试AI回复")

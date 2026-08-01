"""
routers/kb.py
=============
知识库管理路由（从 reply_server.py 迁移）。

路由清单：
- GET    /kb/scripts/{script_id}  获取话术列表（分页 + 搜索）
- POST   /kb/scripts              创建话术
- PUT    /kb/scripts/{script_id}  更新话术
- DELETE /kb/scripts/{script_id}  删除话术
- POST   /kb/rebuild               重建索引
- GET    /kb/status                获取知识库状态
- POST   /kb/search                搜索知识库
- POST   /kb/import                从 CSV 文本导入话术

设计要点：
- 全部 require_auth（普通登录用户即可访问）
- 使用 knowledge_base_service.get_kb_service() 单例
- 路由顺序：/kb/scripts 在前，/kb/scripts/{script_id} 在后（不同方法不冲突）
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth, server_error
from .models import KBScriptCreate, KBScriptUpdate, KBSearchIn, KBImportIn

router = APIRouter(prefix="/kb", tags=["kb"])


def _kb():
    """获取知识库服务单例"""
    from knowledge_base_service import get_kb_service
    return get_kb_service()


# ==================== 话术 CRUD ====================

@router.get("/scripts")
def list_kb_scripts(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    _: None = Depends(require_auth),
):
    """获取话术列表（分页 + 搜索）"""
    kb = _kb()
    scripts, total = kb.list_scripts(page=page, page_size=page_size, search=search)
    return {"scripts": scripts, "total": total, "page": page, "page_size": page_size}


@router.post("/scripts")
def create_kb_script(data: KBScriptCreate, _: None = Depends(require_auth)):
    """创建话术"""
    kb = _kb()
    script_id = kb.add_script(
        question=data.user_question,
        answer=data.answer,
        intent_l1=data.intent_l1,
        intent_l2=data.intent_l2,
    )
    return {"id": script_id, "message": "添加成功"}


@router.put("/scripts/{script_id}")
def update_kb_script(script_id: int, data: KBScriptUpdate, _: None = Depends(require_auth)):
    """更新话术"""
    kb = _kb()
    kb.update_script(
        script_id=script_id,
        question=data.user_question,
        answer=data.answer,
        intent_l1=data.intent_l1,
        intent_l2=data.intent_l2,
    )
    return {"message": "更新成功"}


@router.delete("/scripts/{script_id}")
def delete_kb_script(script_id: int, _: None = Depends(require_auth)):
    """删除话术"""
    kb = _kb()
    kb.delete_script(script_id)
    return {"message": "删除成功"}


# ==================== 索引 / 状态 / 搜索 / 导入 ====================

@router.post("/rebuild")
def rebuild_kb_index(_: None = Depends(require_auth)):
    """重建知识库索引"""
    kb = _kb()
    count = kb.rebuild_index()
    return {"message": f"索引重建成功，共 {count} 条话术", "count": count}


@router.get("/status")
def get_kb_status(_: None = Depends(require_auth)):
    """获取知识库状态"""
    kb = _kb()
    return kb.get_status()


@router.post("/search")
def search_kb(query_data: KBSearchIn, _: None = Depends(require_auth)):
    """搜索知识库"""
    kb = _kb()
    results = kb.search(query_data.query, query_data.n_results)
    return {"results": results}


@router.post("/import")
def import_kb_csv(import_data: KBImportIn, _: None = Depends(require_auth)):
    """从 CSV 文本导入话术"""
    kb = _kb()
    if not import_data.csv_content:
        raise HTTPException(status_code=400, detail="CSV内容不能为空")
    try:
        count = kb.import_from_text(import_data.csv_content)
        return {"message": f"导入成功，共导入 {count} 条话术", "count": count}
    except Exception as e:
        raise server_error(e, "导入")

"""
routers/logs.py
===============
日志管理路由（从 reply_server.py 迁移）。

路由清单：
普通用户：
- GET  /logs              获取实时系统日志（来自 file_log_collector）
- GET  /logs/stats        获取日志统计信息
- POST /logs/clear        清空日志

管理员：
- GET  /admin/logs        获取系统日志文件内容（按级别过滤，取最后 N 行）
- GET  /admin/log-files   列出所有可用的系统日志文件
- GET  /admin/logs/export 导出指定的日志文件（流式响应，防目录遍历）

设计要点：
- 普通用户日志走 file_log_collector 单例（内存环形缓冲）
- 管理员日志直接读取 logs/xianyu_*.log 文件
- 导出日志时严格防目录遍历：os.path.basename + startswith 校验
- 权限：普通路由 require_auth，管理员路由 require_admin
"""
import os
import glob
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from .deps import require_auth, require_admin, safe_client_msg, log_with_user

router = APIRouter(tags=["logs"])


def _get_collector():
    """获取文件日志收集器单例"""
    from file_log_collector import get_file_log_collector
    return get_file_log_collector()


# ==================== 普通用户日志 ====================

@router.get("/logs")
async def get_logs(
    lines: int = 200,
    level: str = None,
    source: str = None,
    _: None = Depends(require_auth),
):
    """获取实时系统日志"""
    try:
        collector = _get_collector()
        logs = collector.get_logs(lines=lines, level_filter=level, source_filter=source)
        return {"success": True, "logs": logs}
    except Exception as e:
        return {
            "success": False,
            "message": safe_client_msg(e, "获取日志失败"),
            "logs": [],
        }


@router.get("/logs/stats")
async def get_log_stats(_: None = Depends(require_auth)):
    """获取日志统计信息"""
    try:
        collector = _get_collector()
        stats = collector.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        return {
            "success": False,
            "message": safe_client_msg(e, "获取日志统计失败"),
            "stats": {},
        }


@router.post("/logs/clear")
async def clear_logs(_: None = Depends(require_auth)):
    """清空日志"""
    try:
        collector = _get_collector()
        collector.clear_logs()
        return {"success": True, "message": "日志已清空"}
    except Exception as e:
        return {
            "success": False,
            "message": safe_client_msg(e, "清空日志失败"),
        }


# ==================== 管理员系统日志（文件） ====================

@router.get("/admin/logs")
def get_system_logs(
    admin_user: Dict[str, Any] = Depends(require_admin),
    lines: int = 100,
    level: str = None,
):
    """获取系统日志文件内容（按级别过滤，取最后 N 行）"""
    try:
        log_with_user('info', f"查询系统日志，行数: {lines}, 级别: {level}", admin_user)

        # 查找日志文件
        log_files = glob.glob("logs/xianyu_*.log")
        logger.info(f"找到日志文件: {log_files}")

        if not log_files:
            logger.warning("未找到日志文件")
            return {"logs": [], "message": "未找到日志文件", "success": False}

        # 获取最新的日志文件
        latest_log_file = max(log_files, key=os.path.getctime)
        logger.info(f"使用最新日志文件: {latest_log_file}")

        logs = []
        try:
            with open(latest_log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                logger.info(f"读取到 {len(all_lines)} 行日志")

                # 如果指定了日志级别，进行过滤
                if level:
                    filtered_lines = [line for line in all_lines if f"| {level.upper()} |" in line]
                    logger.info(f"按级别 {level} 过滤后剩余 {len(filtered_lines)} 行")
                else:
                    filtered_lines = all_lines

                # 获取最后N行
                recent_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
                logger.info(f"取最后 {len(recent_lines)} 行日志")

                for line in recent_lines:
                    logs.append(line.strip())

        except Exception as e:
            logger.error(f"读取日志文件失败: {str(e)}")
            log_with_user('error', f"读取日志文件失败: {str(e)}", admin_user)
            return {
                "logs": [],
                "message": safe_client_msg(e, "读取日志文件失败"),
                "success": False,
            }

        log_with_user('info', f"返回日志记录 {len(logs)} 条", admin_user)
        logger.info(f"成功返回 {len(logs)} 条日志记录")

        return {
            "logs": logs,
            "log_file": latest_log_file,
            "total_lines": len(logs),
            "success": True,
        }

    except Exception as e:
        logger.error(f"获取系统日志失败: {str(e)}")
        log_with_user('error', f"获取系统日志失败: {str(e)}", admin_user)
        return {
            "logs": [],
            "message": safe_client_msg(e, "获取系统日志失败"),
            "success": False,
        }


@router.get("/admin/log-files")
def list_log_files(admin_user: Dict[str, Any] = Depends(require_admin)):
    """列出所有可用的系统日志文件"""
    try:
        log_with_user('info', "查询日志文件列表", admin_user)

        log_dir = "logs"
        if not os.path.exists(log_dir):
            logger.warning("日志目录不存在")
            return {"success": True, "files": []}

        log_pattern = os.path.join(log_dir, "xianyu_*.log")
        log_files = glob.glob(log_pattern)

        files_info = []
        for file_path in log_files:
            try:
                stat_info = os.stat(file_path)
                files_info.append({
                    "name": os.path.basename(file_path),
                    "size": stat_info.st_size,
                    "modified_at": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                    "modified_ts": stat_info.st_mtime,
                })
            except OSError as e:
                logger.warning(f"读取日志文件信息失败 {file_path}: {e}")

        # 按修改时间倒序排序
        files_info.sort(key=lambda item: item.get("modified_ts", 0), reverse=True)

        logger.info(f"返回日志文件列表，共 {len(files_info)} 个文件")
        return {"success": True, "files": files_info}

    except Exception as e:
        logger.error(f"获取日志文件列表失败: {str(e)}")
        log_with_user('error', f"获取日志文件列表失败: {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/admin/logs/export")
def export_log_file(file: str, admin_user: Dict[str, Any] = Depends(require_admin)):
    """导出指定的日志文件（流式响应，防目录遍历）"""
    try:
        if not file:
            raise HTTPException(status_code=400, detail="缺少文件参数")

        safe_name = os.path.basename(file)
        log_dir = os.path.abspath("logs")
        target_path = os.path.abspath(os.path.join(log_dir, safe_name))

        # 防止目录遍历
        if not target_path.startswith(log_dir):
            log_with_user('warning', f"尝试访问非法日志文件: {file}", admin_user)
            raise HTTPException(status_code=400, detail="非法的日志文件路径")

        if not os.path.exists(target_path):
            log_with_user('warning', f"日志文件不存在: {file}", admin_user)
            raise HTTPException(status_code=404, detail="日志文件不存在")

        log_with_user('info', f"导出日志文件: {safe_name}", admin_user)

        def iter_file(path: str):
            file_handle = open(path, 'rb')
            try:
                while True:
                    chunk = file_handle.read(8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                file_handle.close()

        headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
        return StreamingResponse(
            iter_file(target_path),
            media_type='text/plain; charset=utf-8',
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出日志文件失败: {str(e)}")
        log_with_user('error', f"导出日志文件失败: {str(e)}", admin_user)
        raise HTTPException(status_code=500, detail="服务器内部错误")

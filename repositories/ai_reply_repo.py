"""
repositories/ai_reply_repo.py
=============================
AI 回复设置数据访问层（ai_reply_settings 表 + system_settings 兜底）。

从 db_manager.DBManager 迁移而来：
- save_ai_reply_settings：保存账号级 AI 回复配置
- get_ai_reply_settings：读取账号级配置，缺失时回退到系统级 AI 配置
- get_all_ai_reply_settings：读取全部账号配置

设计要点：
- 继承 BaseRepo，使用独立连接（get_connection 上下文管理器）
- 不持有 DBManager 的 self.conn / self.lock，消除单连接瓶颈
- 账号级 api_key / base_url / model_name 为空或等于硬编码默认值时，
  自动回退到 system_settings 表中的 ai_api_key / ai_api_url / ai_model
- DBManager 对应方法将逐步委托到此处（向后兼容）
"""
from typing import Dict, Optional

from loguru import logger

from .base import BaseRepo

# 默认值常量（与 db_manager 原实现保持一致）
_DEFAULT_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
_DEFAULT_MODEL = 'qwen-plus'

# 默认返回结构（异常或无配置时）
_DEFAULT_SETTINGS = {
    'ai_enabled': False,
    'model_name': _DEFAULT_MODEL,
    'api_key': '',
    'base_url': _DEFAULT_BASE_URL,
    'max_discount_percent': 10,
    'max_discount_amount': 100,
    'max_bargain_rounds': 3,
    'custom_prompts': '',
}


class AIReplyRepo(BaseRepo):
    """AI 回复设置仓储"""

    table_name = "ai_reply_settings"

    # ------------------------- 内部工具 -------------------------

    def _get_system_setting(self, conn, key: str) -> Optional[str]:
        """从 system_settings 表读取指定 key（同连接复用 cursor）"""
        try:
            cur = conn.cursor()
            self._execute_sql(
                cur,
                "SELECT value FROM system_settings WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"读取系统设置失败: key={key}, err={e}")
            return None

    # ------------------------- 写入 -------------------------

    def save_ai_reply_settings(self, cookie_id: str, settings: dict) -> bool:
        """保存 AI 回复设置（INSERT OR REPLACE）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    INSERT OR REPLACE INTO ai_reply_settings
                    (cookie_id, ai_enabled, model_name, api_key, base_url,
                     max_discount_percent, max_discount_amount, max_bargain_rounds,
                     custom_prompts, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        cookie_id,
                        bool(settings.get('ai_enabled', False)),
                        settings.get('model_name', _DEFAULT_MODEL),
                        settings.get('api_key', ''),
                        settings.get('base_url', _DEFAULT_BASE_URL),
                        int(settings.get('max_discount_percent', 10)),
                        int(settings.get('max_discount_amount', 100)),
                        int(settings.get('max_bargain_rounds', 3)),
                        settings.get('custom_prompts', ''),
                    ),
                )
                conn.commit()
                logger.debug(f"AI回复设置保存成功: {cookie_id}")
                return True
        except Exception as e:
            logger.error(f"保存AI回复设置失败: {e}")
            return False

    # ------------------------- 读取 -------------------------

    def get_ai_reply_settings(self, cookie_id: str) -> dict:
        """获取 AI 回复设置。

        优先使用账号级配置；如果账号 api_key/base_url/model_name 为空或等于硬编码默认值，
        则回退到 system_settings 表中的全局 AI 配置。
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    SELECT ai_enabled, model_name, api_key, base_url,
                           max_discount_percent, max_discount_amount, max_bargain_rounds,
                           custom_prompts
                    FROM ai_reply_settings WHERE cookie_id = ?
                    """,
                    (cookie_id,),
                )
                result = cur.fetchone()

                # 读取系统级 AI 配置作为兜底
                system_api_key = self._get_system_setting(conn, 'ai_api_key') or ''
                system_base_url = self._get_system_setting(conn, 'ai_api_url') or _DEFAULT_BASE_URL
                system_model = self._get_system_setting(conn, 'ai_model') or _DEFAULT_MODEL

                if result:
                    account_model = result[1]
                    account_api_key = result[2]
                    account_base_url = result[3]

                    # 账号值为空或等于硬编码默认值 → 使用系统设置
                    use_model = account_model if (account_model and account_model != _DEFAULT_MODEL) else system_model
                    use_api_key = account_api_key if account_api_key else system_api_key
                    use_base_url = account_base_url if (account_base_url and account_base_url != _DEFAULT_BASE_URL) else system_base_url

                    return {
                        'ai_enabled': bool(result[0]),
                        'model_name': use_model,
                        'api_key': use_api_key,
                        'base_url': use_base_url,
                        'max_discount_percent': result[4],
                        'max_discount_amount': result[5],
                        'max_bargain_rounds': result[6],
                        'custom_prompts': result[7],
                    }
                # 账号无配置 → 返回系统级默认
                return {
                    'ai_enabled': False,
                    'model_name': system_model,
                    'api_key': system_api_key,
                    'base_url': system_base_url,
                    'max_discount_percent': 10,
                    'max_discount_amount': 100,
                    'max_bargain_rounds': 3,
                    'custom_prompts': '',
                }
        except Exception as e:
            logger.error(f"获取AI回复设置失败: {e}")
            return dict(_DEFAULT_SETTINGS)

    def get_all_ai_reply_settings(self) -> Dict[str, dict]:
        """获取所有账号的 AI 回复设置（不含系统级回退逻辑，原样返回）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                self._execute_sql(
                    cur,
                    """
                    SELECT cookie_id, ai_enabled, model_name, api_key, base_url,
                           max_discount_percent, max_discount_amount, max_bargain_rounds,
                           custom_prompts
                    FROM ai_reply_settings
                    """,
                )
                result = {}
                for row in cur.fetchall():
                    cookie_id = row[0]
                    result[cookie_id] = {
                        'ai_enabled': bool(row[1]),
                        'model_name': row[2],
                        'api_key': row[3],
                        'base_url': row[4],
                        'max_discount_percent': row[5],
                        'max_discount_amount': row[6],
                        'max_bargain_rounds': row[7],
                        'custom_prompts': row[8],
                    }
                return result
        except Exception as e:
            logger.error(f"获取所有AI回复设置失败: {e}")
            return {}


# 模块级单例（与 cookie_repo / order_repo 等保持一致）
ai_reply_repo = AIReplyRepo()

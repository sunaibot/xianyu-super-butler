"""
forbidden_words.py — 闲鱼商品上架违禁词检测模块

提供 ForbiddenWordChecker 类，支持：
- 纯文本违禁词检测与替换
- 返回建议替换词映射（suggestions）
- 保留原文（original_text）供前端展示对比

设计原则：
- 纯函数式检测，无状态
- 返回结构稳定，便于前端契约对齐
"""

import logging
from typing import Any, Dict, List

from .base import ServiceBase

logger = logging.getLogger(__name__)


class ForbiddenWordChecker(ServiceBase):
    """违禁词检测器"""

    name: str = "forbidden_words"
    display_name: str = "违禁词检测"
    description: str = "闲鱼商品上架违禁词检测与替换"
    version: str = "1.0.0"

    FORBIDDEN_WORDS: List[str] = [
        "最低价", "全网最低", "第一", "最好", "100%", "假一赔十",
        "加微信", "加QQ", "私聊", "走咸鱼", "线下交易", "微信", "QQ",
        "发票", "刷单", "好评返现",
    ]

    REPLACEMENT_MAP: Dict[str, str] = {
        "加微信": "详聊",
        "加QQ": "详聊",
        "微信": "v",
        "QQ": "q",
        "私聊": "详聊",
        "全网最低": "优惠价",
        "最低价": "优惠价",
        "第一": "领先",
        "最好": "优质",
        "100%": "高",
        "假一赔十": "正品保障",
        "走咸鱼": "平台交易",
        "线下交易": "平台交易",
        "发票": "凭证",
        "刷单": "推广",
        "好评返现": "优惠活动",
    }

    def startup(self) -> None:
        """违禁词检测器无外部资源，启动无需操作"""
        pass

    def health(self) -> Dict[str, Any]:
        return {
            **super().health(),
            "forbidden_words_count": len(self.FORBIDDEN_WORDS),
        }

    def call(self, action: str, payload: Dict[str, Any] = None) -> Any:
        if action == "check":
            return self.check_text((payload or {}).get("text", ""))
        if action == "clean":
            return self.clean_text((payload or {}).get("text", ""))
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

    def check_text(self, text: str) -> Dict[str, Any]:
        """
        检测文案中的违禁词，返回统一结构：
        {
            "has_forbidden": bool,
            "found_words": List[str],
            "suggestions": Dict[str, str],  # 违禁词 → 建议替换词
            "original_text": str,          # 原文
            "cleaned_text": str,            # 清理后文本
        }
        """
        if not text:
            logger.debug("check_text: 收到空文本，跳过检测")
            return {
                "has_forbidden": False,
                "found_words": [],
                "suggestions": {},
                "original_text": text,
                "cleaned_text": text,
            }

        text_lower = text.lower()
        found_words = [
            word for word in self.FORBIDDEN_WORDS
            if word.lower() in text_lower
        ]

        has_forbidden = bool(found_words)
        if has_forbidden:
            logger.info("check_text: 检测到违禁词 %s", found_words)

        # 构建建议替换映射
        suggestions: Dict[str, str] = {}
        for word in found_words:
            if word in self.REPLACEMENT_MAP:
                suggestions[word] = self.REPLACEMENT_MAP[word]
            else:
                suggestions[word] = "***（无建议替换词，建议手动修改）"

        return {
            "has_forbidden": has_forbidden,
            "found_words": found_words,
            "suggestions": suggestions,
            "original_text": text,
            "cleaned_text": self.clean_text(text),
        }

    def clean_text(self, text: str) -> str:
        """替换文案中的违禁词为安全词"""
        if not text:
            return text

        result = text
        for forbidden, safe in self.REPLACEMENT_MAP.items():
            if forbidden in result:
                result = result.replace(forbidden, safe)
                logger.debug("clean_text: 替换 '%s' → '%s'", forbidden, safe)

        return result


# 模块级单例，供 registry 注册及外部复用
forbidden_checker = ForbiddenWordChecker()

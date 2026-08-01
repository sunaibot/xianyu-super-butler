"""
log_sanitizer.py — 日志脱敏工具

提供统一的敏感信息脱敏函数，避免 Cookie、token、密码等泄露到日志。

设计原则：
- 纯函数，无副作用
- 可被任意模块导入使用
- 保守脱敏：宁可多脱敏也不泄露
"""

import re
from typing import Any, Optional


# 需要脱敏的 Cookie 字段名（小写匹配）
SENSITIVE_COOKIE_KEYS = {
    '_m_h5_tk', 'unb', 'cookie2', 'sgcookie', '_tb_token_',
    'csg', 'mt', 'cna', 'wua', 'bx_v', 'bx_vda',
    'session', 'token', 'password', 'secret', 'api_key',
}

# 敏感字段正则（用于键值对脱敏）
_SENSITIVE_KEY_PATTERN = re.compile(
    r'(password|passwd|pwd|secret|token|api_key|apikey|private_key|access_token|refresh_token|session_id|jwt)',
    re.IGNORECASE
)

# 敏感值正则（用于检测日志中的裸敏感串）
_SENSITIVE_VALUE_PATTERNS = [
    # Bearer token
    re.compile(r'(Bearer\s+)[A-Za-z0-9\-_\.]+', re.IGNORECASE),
    # 长十六进制串（32+ 位，可能是 token/hash）
    re.compile(r'\b[0-9a-f]{32,}\b', re.IGNORECASE),
    # JWT 格式
    re.compile(r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]*'),
]


def sanitize_cookie_string(cookie_str: str, show_length: bool = True) -> str:
    """
    脱敏 Cookie 字符串，保留结构便于调试。
    例: "key1=value1; _m_h5_tk=abc123; unb=12345"
        → "key1=value1; _m_h5_tk=***; unb=***"
    """
    if not cookie_str:
        return ""

    parts = cookie_str.split(';')
    sanitized_parts = []
    for part in parts:
        part = part.strip()
        if '=' not in part:
            sanitized_parts.append(part)
            continue

        key, _, value = part.partition('=')
        key_lower = key.strip().lower()
        if key_lower in SENSITIVE_COOKIE_KEYS or _SENSITIVE_KEY_PATTERN.search(key_lower):
            sanitized_parts.append(f"{key.strip()}=***")
        else:
            # 非敏感字段也只保留前缀，避免泄露
            if len(value) > 20:
                sanitized_parts.append(f"{key.strip()}={value[:8]}***")
            else:
                sanitized_parts.append(part)

    result = '; '.join(sanitized_parts)
    if show_length:
        result += f" (长度:{len(cookie_str)})"
    return result


def sanitize_dict(data: dict, sensitive_keys: Optional[set] = None) -> dict:
    """
    脱敏字典中的敏感字段值。
    用于记录请求参数、配置等结构化数据。
    """
    if not isinstance(data, dict):
        return data

    keys_to_mask = sensitive_keys or SENSITIVE_COOKIE_KEYS
    result = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if k_lower in keys_to_mask or _SENSITIVE_KEY_PATTERN.search(k_lower):
            result[k] = "***敏感信息已脱敏***"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, keys_to_mask)
        elif isinstance(v, str) and len(v) > 100:
            # 超长字符串可能是 cookie/token
            result[k] = f"{v[:10]}...(长度:{len(v)})"
        else:
            result[k] = v
    return result


def sanitize_text(text: str) -> str:
    """
    脱敏文本中的敏感模式（用于通用日志消息）。
    """
    if not text:
        return text

    result = text
    # 脱敏 Bearer token
    result = re.sub(r'(Bearer\s+)[A-Za-z0-9\-_\.]+', r'\1***', result, flags=re.IGNORECASE)
    # 脱敏 JWT
    result = re.sub(r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]*', '***JWT***', result)

    return result


def safe_log(message: str, **kwargs) -> str:
    """
    构建安全的日志消息，自动脱敏 kwargs 中的敏感字段。
    用于 logger.info(safe_log("xxx", cookie=cookie_str, token=token))
    """
    parts = [message]
    for k, v in kwargs.items():
        k_lower = k.lower()
        if k_lower in SENSITIVE_COOKIE_KEYS or _SENSITIVE_KEY_PATTERN.search(k_lower):
            parts.append(f"{k}=***")
        elif isinstance(v, str) and len(v) > 100:
            parts.append(f"{k}={v[:8]}...(长度:{len(v)})")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)

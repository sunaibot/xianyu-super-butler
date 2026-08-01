"""
password_utils.py — 密码安全工具

提供 bcrypt 哈希与验证，兼容历史 SHA-256 哈希的平滑迁移。

设计原则：
- 新密码一律使用 bcrypt（自带 salt，抗彩虹表）
- 旧 SHA-256 哈希在用户首次登录时自动迁移为 bcrypt
- 直接使用 bcrypt 库（不依赖 passlib，避免与 bcrypt 4.x 的 __about__ 兼容性问题）
- 模块化，可被 db_manager / reply_server / init_admin 复用
"""

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 旧哈希前缀标识，用于识别和迁移
_LEGACY_SHA256_PREFIX = "sha256$"

# bcrypt 密码最大长度（字节），超出需截断（bcrypt 硬性限制）
_BCRYPT_MAX_BYTES = 72

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning(
        "bcrypt 未安装，密码安全降级为 SHA-256（不安全，请 pip install bcrypt"
    )


def _truncate_for_bcrypt(password: str) -> bytes:
    """将密码编码为 UTF-8 并截断到 bcrypt 允许的 72 字节，避免超长异常"""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码（如果 bcrypt 可用），否则降级为带前缀的 SHA-256"""
    if not password:
        raise ValueError("密码不能为空")

    if BCRYPT_AVAILABLE:
        pwd_bytes = _truncate_for_bcrypt(password)
        return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")
    else:
        # 降级方案：带前缀的 SHA-256（仍不如 bcrypt 安全，但标识了算法版本）
        return _LEGACY_SHA256_PREFIX + hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证密码
    - bcrypt 哈希：使用 bcrypt.checkpw 验证
    - 旧 SHA-256 哈希（无前缀或带前缀）：直接比对
    - 返回是否验证成功
    """
    if not password or not password_hash:
        return False

    # 检查是否是 bcrypt 哈希（bcrypt 哈希以 $2b$ / $2a$ / $2y$ 开头）
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$") or password_hash.startswith("$2y$"):
        if not BCRYPT_AVAILABLE:
            logger.error("数据库中存在 bcrypt 哈希但 bcrypt 未安装，无法验证")
            return False
        pwd_bytes = _truncate_for_bcrypt(password)
        try:
            return bcrypt.checkpw(pwd_bytes, password_hash.encode("utf-8"))
        except Exception as e:
            logger.error(f"bcrypt 验证异常: {e}")
            return False

    # 兼容旧 SHA-256 哈希（带前缀）
    if password_hash.startswith(_LEGACY_SHA256_PREFIX):
        legacy_hash = password_hash[len(_LEGACY_SHA256_PREFIX):]
        return hashlib.sha256(password.encode()).hexdigest() == legacy_hash

    # 最旧的格式：纯 SHA-256 哈希（无前缀）
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    return password_hash == legacy_hash


def needs_migration(password_hash: str) -> bool:
    """检查密码哈希是否需要迁移到 bcrypt"""
    if not BCRYPT_AVAILABLE:
        return False
    # 非 bcrypt 哈希都需要迁移
    return not (password_hash.startswith("$2b$") or password_hash.startswith("$2a$") or password_hash.startswith("$2y$"))


def migrate_password(password: str) -> Optional[str]:
    """
    如果密码验证成功且需要迁移，返回新的 bcrypt 哈希
    否则返回 None
    """
    if not BCRYPT_AVAILABLE:
        return None
    return hash_password(password)

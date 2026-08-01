#!/usr/bin/env python3
"""管理员账号初始化（非交互式，从环境变量读取凭据）。

公共函数 ensure_admin_account 供本脚本、init_admin.py（交互式）、reset_password.py 复用，
消除三处重复的「检查存在 → 创建/重置 → 设为管理员」逻辑。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import db_manager
from config import ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD


def ensure_admin_account(
    username: str,
    email: str,
    password: str,
    reset_if_exists: bool = True,
) -> bool:
    """确保管理员账号存在且为管理员角色。

    - 不存在 → 创建用户 + 设为管理员
    - 已存在 + reset_if_exists=True → 重置密码 + 设为管理员
    - 已存在 + reset_if_exists=False → 仅确保 is_admin=1，不改密码

    Args:
        username: 管理员用户名
        email: 管理员邮箱
        password: 明文密码（将经 bcrypt 哈希后存储）
        reset_if_exists: 用户已存在时是否重置密码

    Returns:
        True 表示成功（创建或重置或已存在）；False 表示创建/重置失败
    """
    existing = db_manager.get_user_by_username(username)
    if existing:
        if reset_if_exists:
            if not db_manager.update_user_password(username, password):
                return False
            print(f'[INFO] 已重置 {username} 的密码')
        else:
            print(f'[INFO] 用户 {username} 已存在，跳过密码重置')
        _set_admin_role(username)
        return True

    # 不存在 → 创建
    if not db_manager.create_user(username, email, password):
        return False
    _set_admin_role(username)
    print(f'[INFO] 已创建管理员 {username}')
    return True


def _set_admin_role(username: str) -> None:
    """将指定用户标记为管理员（is_admin=1）。"""
    with db_manager.lock:
        cursor = db_manager.conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
        db_manager.conn.commit()


def main():
    username = ADMIN_USERNAME or 'admin'
    email = ADMIN_EMAIL or 'admin@example.com'
    password = ADMIN_PASSWORD

    default_password_used = False
    if not password:
        password = 'admin123'
        default_password_used = True
        print('[WARN] 未设置 ADMIN_PASSWORD 环境变量，使用默认密码 admin123（生产环境请尽快修改！）')

    print(f'[INFO] 管理员用户名: {username}')
    print(f'[INFO] 管理员邮箱: {email}')
    if default_password_used:
        print('[WARN] 使用的是默认密码，请务必在首次登录后立即修改！')

    # 未显式设置密码时不覆盖已有密码（避免覆盖用户自定义密码）
    reset_if_exists = not default_password_used

    ok = ensure_admin_account(username, email, password, reset_if_exists=reset_if_exists)
    if not ok:
        print('[ERROR] 管理员初始化失败')
        sys.exit(1)

    print(f'[SUCCESS] 管理员 {username} 初始化完成')
    if default_password_used:
        print('[WARN] 请尽快登录并修改默认密码！')


if __name__ == '__main__':
    main()

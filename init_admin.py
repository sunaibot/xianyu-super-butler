#!/usr/bin/env python3
"""交互式管理员账号初始化（CLI）。

复用 init_admin_noninteractive.ensure_admin_account 公共函数，
仅保留交互式输入逻辑（密码二次确认、邮箱提示）。
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import db_manager
from init_admin_noninteractive import ensure_admin_account


def _prompt_non_empty(prompt: str) -> str:
    while True:
        val = input(prompt).strip()
        if val:
            return val


def _prompt_password_twice() -> str:
    while True:
        p1 = getpass.getpass('请输入管理员密码（不回显）: ').strip()
        p2 = getpass.getpass('请再次输入管理员密码（不回显）: ').strip()
        if not p1:
            print('密码不能为空')
            continue
        if p1 != p2:
            print('两次输入不一致，请重试')
            continue
        return p1


def main():
    existing = db_manager.get_user_by_username('admin')
    if existing:
        print('admin 用户已存在')
        ans = input('是否重置 admin 密码？(y/N): ').strip().lower()
        if ans not in ('y', 'yes'):
            print('跳过初始化')
            return

        password = _prompt_password_twice()
        # 已存在且用户确认重置 → reset_if_exists=True
        if not ensure_admin_account('admin', existing.get('email', ''), password, reset_if_exists=True):
            raise SystemExit('重置 admin 密码失败')
        print('重置完成：已更新 admin 密码')
        return

    print('=== 初始化管理员账号（CLI）===')
    email = _prompt_non_empty('请输入管理员邮箱: ')
    password = _prompt_password_twice()

    # 不存在 → 创建（ensure_admin_account 自动创建并设为管理员）
    if not ensure_admin_account('admin', email, password, reset_if_exists=True):
        raise SystemExit('创建 admin 用户失败：用户名或邮箱可能已存在')
    print('初始化完成：已创建 admin 用户')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import db_manager

def main():
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    existing = db_manager.get_user_by_username(username)
    if existing:
        print(f'[INFO] 用户 {username} 已存在')
        print(f'[INFO] 正在重置密码...')
        ok = db_manager.update_user_password(username, password)
        if ok:
            with db_manager.lock:
                cursor = db_manager.conn.cursor()
                cursor.execute(f"UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
                db_manager.conn.commit()
            print(f'[SUCCESS] 管理员 {username} 密码重置完成')
        else:
            print('[ERROR] 重置密码失败')
            sys.exit(1)
        return
    
    print(f'[INFO] 正在创建管理员用户 {username}...')
    ok = db_manager.create_user(username, email, password)
    if not ok:
        print('[ERROR] 创建用户失败')
        sys.exit(1)
    
    with db_manager.lock:
        cursor = db_manager.conn.cursor()
        cursor.execute(f"UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
        db_manager.conn.commit()
    
    print(f'[SUCCESS] 管理员 {username} 创建完成')

if __name__ == '__main__':
    main()

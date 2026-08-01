#!/usr/bin/env python3
"""
check_db.py
===========
数据库诊断脚本（CLI）。

复用项目内 db_manager / user_repo 进行诊断，避免直接 SQL 重复逻辑：
- 列出用户（含是否管理员）
- 显示数据库路径与连接状态
- 输出各业务表行数概览

使用方式：
    python check_db.py
    DB_PATH=data/xianyu_data.db python check_db.py
"""
import os
import sys


def _resolve_db_path() -> str:
    """优先使用环境变量，其次回退到 local_data 与项目根 data 目录"""
    # 复用 config.py 集中管理的 DB_PATH 默认值，避免重复
    from config import DB_PATH as _cfg_db_path
    env_path = _cfg_db_path
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        "local_data/data/xianyu_data.db",
        "data/xianyu_data.db",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # 兜底：返回默认值，让 db_manager 报错
    return env_path or candidates[0]


def main() -> int:
    db_path = _resolve_db_path()
    if not os.path.exists(db_path):
        print(f"[FAIL] 数据库文件不存在: {db_path}")
        # 扫描可能的 .db 文件，便于排查
        for scan_root in ("local_data", "data", "."):
            if not os.path.isdir(scan_root):
                continue
            for root, _dirs, files in os.walk(scan_root):
                for f in files:
                    if f.endswith('.db'):
                        print(f"  发现候选: {os.path.join(root, f)}")
        return 1

    print(f"[OK] 数据库路径: {db_path}")
    # check_db 作为 CLI 诊断脚本，允许通过环境变量覆盖 DB_PATH
    os.environ.setdefault('DB_PATH', db_path)

    # 延迟导入，确保 DB_PATH 已设置
    from db_manager import db_manager
    from repositories import user_repo

    # 1) 用户列表（不含密码哈希）
    try:
        users = user_repo.get_all_users() if hasattr(user_repo, 'get_all_users') else None
        if users is None:
            # 回退到 db_manager
            users = db_manager.get_all_users()
        print("\n=== 用户列表 ===")
        for u in users:
            print(f"  ID={u.get('id')}  用户名={u.get('username')}  邮箱={u.get('email')}  管理员={u.get('is_admin')}")
        print(f"共 {len(users)} 个用户")

        # 2) admin 密码哈希长度（不输出明文，避免泄露）
        admin = next((u for u in users if u.get('username') == 'admin'), None)
        if admin and admin.get('password_hash'):
            print(f"\nadmin 密码哈希长度: {len(admin['password_hash'])} 字符 (前缀: {admin['password_hash'][:8]}...)")
        elif admin:
            print("\nadmin 用户存在但无密码哈希")
        else:
            print("\n未找到 admin 用户")
    except Exception as e:
        print(f"[FAIL] 读取用户列表失败: {e}")
        return 2

    # 3) 各表行数概览（轻量诊断，使用 PRAGMA + COUNT）
    print("\n=== 表行数概览 ===")
    tables = [
        'users', 'cookies', 'cookie_status', 'keywords', 'orders', 'cards',
        'delivery_rules', 'ai_reply_settings', 'ai_conversations', 'item_info',
        'item_replay', 'default_replies', 'notification_channels', 'message_notifications',
        'user_settings', 'system_settings', 'risk_control_logs',
    ]
    try:
        with db_manager.get_connection() as conn:
            cur = conn.cursor()
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    count = cur.fetchone()[0]
                    print(f"  {t}: {count}")
                except Exception as e:
                    print(f"  {t}: 表不存在或查询失败 ({e})")
    except Exception as e:
        print(f"[FAIL] 表行数诊断失败: {e}")
        return 3

    print("\n[OK] 诊断完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

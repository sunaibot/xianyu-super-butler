import sqlite3
import os

db_path = "local_data/data/xianyu_data.db"

if not os.path.exists(db_path):
    print(f"数据库文件不存在: {db_path}")
    # 查找可能的数据库位置
    for root, dirs, files in os.walk("local_data"):
        for f in files:
            if f.endswith('.db'):
                print(f"找到数据库: {os.path.join(root, f)}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查用户表
cursor.execute("SELECT id, username, email, is_admin FROM users")
users = cursor.fetchall()
print("\n用户列表:")
for user in users:
    print(f"  ID: {user[0]}, 用户名: {user[1]}, 邮箱: {user[2]}, 管理员: {user[3]}")

# 检查密码哈希
cursor.execute("SELECT username, password_hash FROM users WHERE username='admin'")
user = cursor.fetchone()
if user:
    print(f"\nadmin 用户密码哈希: {user[1][:50]}...")

conn.close()

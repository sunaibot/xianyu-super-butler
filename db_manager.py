import sqlite3
import os
import threading
import hashlib
import time
import json
import random
import string
import aiohttp
import io
import base64
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple, Dict, Optional, Any
from loguru import logger
from password_utils import hash_password, verify_password, needs_migration, migrate_password
from config import DB_PATH as _DEFAULT_DB_PATH, SQL_LOG_ENABLED, SQL_LOG_LEVEL

class DBManager:
    """SQLite数据库管理，持久化存储Cookie和关键字"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接和表结构"""
        # 使用 config.py 集中管理的 DB_PATH 默认值
        if db_path is None:
            db_path = _DEFAULT_DB_PATH

        # 确保数据目录存在并有正确权限
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, mode=0o755, exist_ok=True)
                logger.info(f"创建数据目录: {db_dir}")
            except PermissionError as e:
                logger.error(f"创建数据目录失败，权限不足: {e}")
                # 尝试使用当前目录
                db_path = os.path.basename(db_path)
                logger.warning(f"使用当前目录作为数据库路径: {db_path}")
            except Exception as e:
                logger.error(f"创建数据目录失败: {e}")
                raise

        # 检查目录权限
        if db_dir and os.path.exists(db_dir):
            if not os.access(db_dir, os.W_OK):
                logger.error(f"数据目录没有写权限: {db_dir}")
                # 尝试使用当前目录
                db_path = os.path.basename(db_path)
                logger.warning(f"使用当前目录作为数据库路径: {db_path}")

        self.db_path = db_path
        logger.info(f"数据库路径: {self.db_path}")
        self.conn = None
        self.lock = threading.RLock()  # 使用可重入锁保护数据库操作

        # SQL日志配置（由 config.py 集中读取环境变量）
        self.sql_log_enabled = SQL_LOG_ENABLED
        self.sql_log_level = SQL_LOG_LEVEL

        logger.info(f"SQL日志已启用，日志级别: {self.sql_log_level}")

        # 仓储层委托（渐进迁移）：各域已委托给对应 Repo
        # 各 Repo 使用独立连接（get_connection 上下文管理器），与 self.conn/self.lock 解耦
        # 注意：必须在 init_db() 之前初始化，因为 check_and_upgrade_db() 会调用 get_system_setting()
        from repositories import cookie_repo as _cookie_repo
        from repositories import order_repo as _order_repo
        from repositories import user_repo as _user_repo
        from repositories import card_repo as _card_repo
        from repositories import delivery_rule_repo as _delivery_rule_repo
        from repositories import keyword_repo as _keyword_repo
        from repositories import ai_reply_repo as _ai_reply_repo
        from repositories import user_settings_repo as _user_settings_repo
        from repositories import item_repo as _item_repo
        from repositories import risk_control_repo as _risk_control_repo
        from repositories import default_reply_repo as _default_reply_repo
        from repositories import notification_repo as _notification_repo
        from repositories import system_settings_repo as _system_settings_repo
        from repositories import verification_repo as _verification_repo
        from repositories import admin_repo as _admin_repo
        self.cookie_repo = _cookie_repo
        self.order_repo = _order_repo
        self.user_repo = _user_repo
        self.card_repo = _card_repo
        self.delivery_rule_repo = _delivery_rule_repo
        self.keyword_repo = _keyword_repo
        self.ai_reply_repo = _ai_reply_repo
        self.user_settings_repo = _user_settings_repo
        self.item_repo = _item_repo
        self.risk_control_repo = _risk_control_repo
        self.default_reply_repo = _default_reply_repo
        self.notification_repo = _notification_repo
        self.system_settings_repo = _system_settings_repo
        self.verification_repo = _verification_repo
        self.admin_repo = _admin_repo

        self.init_db()
    
    def init_db(self):
        """初始化数据库表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()
            
            # 创建用户表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建邮箱验证码表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建图形验证码表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS captcha_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建cookies表（添加user_id字段和auto_confirm字段）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                id TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                auto_confirm INTEGER DEFAULT 1,
                remark TEXT DEFAULT '',
                pause_duration INTEGER DEFAULT 10,
                username TEXT DEFAULT '',
                password TEXT DEFAULT '',
                show_browser INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            ''')

            
            # 创建keywords表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS keywords (
                cookie_id TEXT,
                keyword TEXT,
                reply TEXT,
                item_id TEXT,
                type TEXT DEFAULT 'text',
                image_url TEXT,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建cookie_status表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookie_status (
                cookie_id TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建AI回复配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_reply_settings (
                cookie_id TEXT PRIMARY KEY,
                ai_enabled BOOLEAN DEFAULT FALSE,
                model_name TEXT DEFAULT 'qwen-plus',
                api_key TEXT,
                base_url TEXT DEFAULT 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                max_discount_percent INTEGER DEFAULT 10,
                max_discount_amount INTEGER DEFAULT 100,
                max_bargain_rounds INTEGER DEFAULT 3,
                custom_prompts TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建AI对话历史表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                bargain_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies (id) ON DELETE CASCADE
            )
            ''')

            # 创建AI商品信息缓存表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_item_cache (
                item_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                price REAL,
                description TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建卡券表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('api', 'text', 'data', 'image')),
                api_config TEXT,
                text_content TEXT,
                data_content TEXT,
                image_url TEXT,
                description TEXT,
                enabled BOOLEAN DEFAULT TRUE,
                delay_seconds INTEGER DEFAULT 0,
                is_multi_spec BOOLEAN DEFAULT FALSE,
                spec_name TEXT,
                spec_value TEXT,
                user_id INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            ''')

            # 创建订单表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                item_id TEXT,
                buyer_id TEXT,
                spec_name TEXT,
                spec_value TEXT,
                quantity TEXT,
                amount TEXT,
                order_status TEXT DEFAULT 'unknown',
                cookie_id TEXT,
                is_bargain INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 检查并添加 is_bargain 列（用于标记小刀订单）
            try:
                self._execute_sql(cursor, "SELECT is_bargain FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                # is_bargain 列不存在，需要添加
                logger.info("正在为 orders 表添加 is_bargain 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN is_bargain INTEGER DEFAULT 0")
                logger.info("orders 表 is_bargain 列添加完成")

            # 检查并添加收货人信息列（旧库可能只补齐了部分列，需要逐列检查）
            try:
                cursor.execute("PRAGMA table_info(orders)")
                order_columns = [column[1] for column in cursor.fetchall()]

                receiver_cols = {
                    'receiver_name': "ALTER TABLE orders ADD COLUMN receiver_name TEXT DEFAULT ''",
                    'receiver_phone': "ALTER TABLE orders ADD COLUMN receiver_phone TEXT DEFAULT ''",
                    'receiver_address': "ALTER TABLE orders ADD COLUMN receiver_address TEXT DEFAULT ''",
                    'receiver_city': "ALTER TABLE orders ADD COLUMN receiver_city TEXT DEFAULT ''",
                }

                missing = [c for c in receiver_cols.keys() if c not in order_columns]
                if missing:
                    logger.info(f"正在为 orders 表添加收货信息列: {missing}...")
                    for col in missing:
                        self._execute_sql(cursor, receiver_cols[col])
                    logger.info("orders 表收货信息列补齐完成")

            except Exception as e:
                logger.error(f"检查/补齐 orders 收货信息列失败: {e}")

            # 检查并添加 version 列（用于乐观锁）
            try:
                self._execute_sql(cursor, "SELECT version FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                # version 列不存在，需要添加
                logger.info("正在为 orders 表添加 version 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN version INTEGER DEFAULT 1")
                logger.info("orders 表 version 列添加完成")

            # 检查并添加 chat_id 列到 orders 表（用于手动发货时发送消息）
            try:
                self._execute_sql(cursor, "SELECT chat_id FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 orders 表添加 chat_id 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN chat_id TEXT DEFAULT ''")
                logger.info("orders 表 chat_id 列添加完成")

            # 检查并添加 user_id 列（用于数据库迁移）
            try:
                self._execute_sql(cursor, "SELECT user_id FROM cards LIMIT 1")
            except sqlite3.OperationalError:
                # user_id 列不存在，需要添加
                logger.info("正在为 cards 表添加 user_id 列...")
                self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
                self._execute_sql(cursor, "CREATE INDEX IF NOT EXISTS idx_cards_user_id ON cards(user_id)")
                logger.info("cards 表 user_id 列添加完成")

            # 检查并添加 delay_seconds 列（用于自动发货延时功能）
            try:
                self._execute_sql(cursor, "SELECT delay_seconds FROM cards LIMIT 1")
            except sqlite3.OperationalError:
                # delay_seconds 列不存在，需要添加
                logger.info("正在为 cards 表添加 delay_seconds 列...")
                self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN delay_seconds INTEGER DEFAULT 0")
                logger.info("cards 表 delay_seconds 列添加完成")

            # 检查并添加 item_id 列（用于自动回复商品ID功能）
            try:
                self._execute_sql(cursor, "SELECT item_id FROM keywords LIMIT 1")
            except sqlite3.OperationalError:
                # item_id 列不存在，需要添加
                logger.info("正在为 keywords 表添加 item_id 列...")
                self._execute_sql(cursor, "ALTER TABLE keywords ADD COLUMN item_id TEXT")
                logger.info("keywords 表 item_id 列添加完成")

            # 创建商品信息表（建表语句包含所有已知列，避免旧库迁移）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS item_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_title TEXT,
                item_description TEXT,
                item_category TEXT,
                item_price TEXT,
                item_detail TEXT,
                item_image TEXT,
                is_multi_spec BOOLEAN DEFAULT FALSE,
                multi_quantity_delivery BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE,
                UNIQUE(cookie_id, item_id)
            )
            ''')

            # 旧库迁移：检查并添加 multi_quantity_delivery 列
            try:
                self._execute_sql(cursor, "SELECT multi_quantity_delivery FROM item_info LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 item_info 表添加 multi_quantity_delivery 列...")
                self._execute_sql(cursor, "ALTER TABLE item_info ADD COLUMN multi_quantity_delivery BOOLEAN DEFAULT FALSE")
                logger.info("item_info 表 multi_quantity_delivery 列添加完成")

            # 旧库迁移：检查并添加 item_image 列
            try:
                self._execute_sql(cursor, "SELECT item_image FROM item_info LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 item_info 表添加 item_image 列...")
                self._execute_sql(cursor, "ALTER TABLE item_info ADD COLUMN item_image TEXT")
                logger.info("item_info 表 item_image 列添加完成")

            # 创建自动发货规则表（建表语句包含 user_id 列，避免旧库迁移）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS delivery_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                card_id INTEGER NOT NULL,
                delivery_count INTEGER DEFAULT 1,
                enabled BOOLEAN DEFAULT TRUE,
                description TEXT,
                delivery_times INTEGER DEFAULT 0,
                user_id INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
            )
            ''')

            # 旧库迁移：检查并添加 delivery_rules 表的 user_id 列（必须在建表之后）
            try:
                self._execute_sql(cursor, "SELECT user_id FROM delivery_rules LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 delivery_rules 表添加 user_id 列...")
                self._execute_sql(cursor, "ALTER TABLE delivery_rules ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
                logger.info("delivery_rules 表 user_id 列添加完成")
            try:
                self._execute_sql(cursor, "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_delivery_rules_user_id'")
                if cursor.fetchone() is None:
                    self._execute_sql(cursor, "CREATE INDEX IF NOT EXISTS idx_delivery_rules_user_id ON delivery_rules(user_id)")
            except sqlite3.OperationalError:
                pass

            # 创建默认回复表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS default_replies (
                cookie_id TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                reply_content TEXT,
                reply_image_url TEXT,
                reply_once BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 添加 reply_once 字段（如果不存在）
            try:
                cursor.execute('ALTER TABLE default_replies ADD COLUMN reply_once BOOLEAN DEFAULT FALSE')
                self.conn.commit()
                logger.info("已添加 reply_once 字段到 default_replies 表")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.warning(f"添加 reply_once 字段失败: {e}")

            # 添加 reply_image_url 字段（如果不存在）
            try:
                cursor.execute('ALTER TABLE default_replies ADD COLUMN reply_image_url TEXT')
                self.conn.commit()
                logger.info("已添加 reply_image_url 字段到 default_replies 表")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.warning(f"添加 reply_image_url 字段失败: {e}")

            # 创建指定商品回复表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS item_replay (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    cookie_id TEXT NOT NULL,
                    reply_content TEXT NOT NULL ,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建默认回复记录表（记录已回复的chat_id）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS default_reply_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                replied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cookie_id, chat_id),
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建通知渠道表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk','dingtalk','feishu','lark','bark','email','webhook','wechat','telegram')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建系统设置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建消息通知配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES notification_channels(id) ON DELETE CASCADE,
                UNIQUE(cookie_id, channel_id)
            )
            ''')

            # 创建用户设置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, key)
            )
            ''')

            # 创建风控日志表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_control_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'slider_captcha',
                event_description TEXT,
                processing_result TEXT,
                processing_status TEXT DEFAULT 'processing',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建知识库话术表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base_scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_question TEXT NOT NULL,
                answer TEXT NOT NULL,
                intent_l1 TEXT DEFAULT '',
                intent_l2 TEXT DEFAULT '',
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 检查并添加 is_admin 列
            try:
                self._execute_sql(cursor, "SELECT is_admin FROM users LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 users 表添加 is_admin 列...")
                self._execute_sql(cursor, "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
                logger.info("users 表 is_admin 列添加完成")

            # 插入默认系统设置（不包括管理员密码，由CLI初始化）
            cursor.execute('''
            INSERT OR IGNORE INTO system_settings (key, value, description) VALUES
            ('theme_color', 'blue', '主题颜色'),
            ('registration_enabled', 'true', '是否开启用户注册'),
            ('show_default_login_info', 'true', '是否显示默认登录信息'),
            ('login_captcha_enabled', 'true', '登录滑动验证码开关'),
            ('smtp_server', '', 'SMTP服务器地址'),
            ('smtp_port', '587', 'SMTP端口'),
            ('smtp_user', '', 'SMTP登录用户名（发件邮箱）'),
            ('smtp_password', '', 'SMTP登录密码/授权码'),
            ('smtp_from', '', '发件人显示名（留空则使用用户名）'),
            ('smtp_use_tls', 'true', '是否启用TLS'),
            ('smtp_use_ssl', 'false', '是否启用SSL'),
            ('qq_reply_secret_key', 'xianyu_qq_reply_2024', 'QQ回复消息API秘钥'),
            ('item_sync_enabled', 'true', '是否启用定时自动同步商品'),
            ('item_sync_interval', '600', '商品同步间隔时间（秒）'),
            ('item_sync_max_pages', '5', '每次最多同步的页数')
            ''')

            # 检查并升级数据库
            self.check_and_upgrade_db(cursor)

            # 执行数据库迁移
            self._migrate_database(cursor)

            self.conn.commit()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            self.conn.rollback()
            raise

    def _migrate_database(self, cursor):
        """执行数据库迁移"""
        try:
            # 检查cards表是否存在image_url列
            cursor.execute("PRAGMA table_info(cards)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'image_url' not in columns:
                logger.info("添加cards表的image_url列...")
                cursor.execute("ALTER TABLE cards ADD COLUMN image_url TEXT")
                logger.info("数据库迁移完成：添加image_url列")

            # 检查并更新CHECK约束（重建表以支持image类型）
            self._update_cards_table_constraints(cursor)

            # 检查cookies表是否存在remark列
            cursor.execute("PRAGMA table_info(cookies)")
            cookie_columns = [column[1] for column in cursor.fetchall()]

            if 'remark' not in cookie_columns:
                logger.info("添加cookies表的remark列...")
                cursor.execute("ALTER TABLE cookies ADD COLUMN remark TEXT DEFAULT ''")
                logger.info("数据库迁移完成：添加remark列")

            # 检查cookies表是否存在pause_duration列
            if 'pause_duration' not in cookie_columns:
                logger.info("添加cookies表的pause_duration列...")
                cursor.execute("ALTER TABLE cookies ADD COLUMN pause_duration INTEGER DEFAULT 10")
                logger.info("数据库迁移完成：添加pause_duration列")

            # 确保商品同步配置存在
            cursor.execute("SELECT key FROM system_settings WHERE key IN ('item_sync_enabled', 'item_sync_interval', 'item_sync_max_pages')")
            existing_keys = [row[0] for row in cursor.fetchall()]

            if 'item_sync_enabled' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_enabled...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_enabled', 'true', '是否启用定时自动同步商品')")
            if 'item_sync_interval' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_interval...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_interval', '600', '商品同步间隔时间（秒）')")
            if 'item_sync_max_pages' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_max_pages...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_max_pages', '5', '每次最多同步的页数')")

        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            # 迁移失败不应该阻止程序启动
            pass

    def _update_cards_table_constraints(self, cursor):
        """更新cards表的CHECK约束以支持image类型"""
        try:
            # 尝试插入一个测试的image类型记录来检查约束
            cursor.execute('''
                INSERT INTO cards (name, type, user_id)
                VALUES ('__test_image_constraint__', 'image', 1)
            ''')
            # 如果插入成功，立即删除测试记录
            cursor.execute("DELETE FROM cards WHERE name = '__test_image_constraint__'")
            logger.info("cards表约束检查通过，支持image类型")
        except Exception as e:
            if "CHECK constraint failed" in str(e) or "constraint" in str(e).lower():
                logger.info("检测到旧的CHECK约束，开始更新cards表...")

                # 重建表以更新约束
                try:
                    # 1. 创建新表
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cards_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        type TEXT NOT NULL CHECK (type IN ('api', 'text', 'data', 'image')),
                        api_config TEXT,
                        text_content TEXT,
                        data_content TEXT,
                        image_url TEXT,
                        description TEXT,
                        enabled BOOLEAN DEFAULT TRUE,
                        delay_seconds INTEGER DEFAULT 0,
                        is_multi_spec BOOLEAN DEFAULT FALSE,
                        spec_name TEXT,
                        spec_value TEXT,
                        user_id INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    ''')

                    # 2. 复制数据
                    cursor.execute('''
                    INSERT INTO cards_new (id, name, type, api_config, text_content, data_content, image_url,
                                          description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value,
                                          user_id, created_at, updated_at)
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value,
                           user_id, created_at, updated_at
                    FROM cards
                    ''')

                    # 3. 删除旧表
                    cursor.execute("DROP TABLE cards")

                    # 4. 重命名新表
                    cursor.execute("ALTER TABLE cards_new RENAME TO cards")

                    logger.info("cards表约束更新完成，现在支持image类型")

                except Exception as rebuild_error:
                    logger.error(f"重建cards表失败: {rebuild_error}")
                    # 如果重建失败，尝试回滚
                    try:
                        cursor.execute("DROP TABLE IF EXISTS cards_new")
                    except Exception:
                        pass
            else:
                logger.error(f"检查cards表约束时出现未知错误: {e}")
            
    def check_and_upgrade_db(self, cursor):
        """检查数据库版本并执行必要的升级"""
        try:
            # 获取当前数据库版本
            current_version = self.get_system_setting("db_version") or "1.0"
            logger.info(f"当前数据库版本: {current_version}")

            if current_version == "1.0":
                logger.info("开始升级数据库到版本1.0...")
                # 安全基线：不再在数据库初始化/升级时自动创建默认管理员账号
                self.set_system_setting("db_version", "1.0", "数据库版本号")
                logger.info("数据库升级到版本1.0完成")
            
            # 如果版本低于需要升级的版本，执行升级
            if current_version < "1.1":
                logger.info("开始升级数据库到版本1.1...")
                self.upgrade_notification_channels_table(cursor)
                self.set_system_setting("db_version", "1.1", "数据库版本号")
                logger.info("数据库升级到版本1.1完成")

            # 升级到版本1.2 - 支持更多通知渠道类型
            if current_version < "1.2":
                logger.info("开始升级数据库到版本1.2...")
                self.upgrade_notification_channels_types(cursor)
                self.set_system_setting("db_version", "1.2", "数据库版本号")
                logger.info("数据库升级到版本1.2完成")

            # 升级到版本1.3 - 添加关键词类型和图片URL字段
            if current_version < "1.3":
                logger.info("开始升级数据库到版本1.3...")
                self.upgrade_keywords_table_for_image_support(cursor)
                self.set_system_setting("db_version", "1.3", "数据库版本号")
                logger.info("数据库升级到版本1.3完成")
            
            
            # 升级到版本1.4 - 添加关键词类型和图片URL字段
            if current_version < "1.4":
                logger.info("开始升级数据库到版本1.4...")
                self.upgrade_notification_channels_types(cursor)
                self.set_system_setting("db_version", "1.4", "数据库版本号")
                logger.info("数据库升级到版本1.4完成")

            # 升级到版本1.5 - 为cookies表添加账号登录字段
            if current_version < "1.5":
                logger.info("开始升级数据库到版本1.5...")
                self.upgrade_cookies_table_for_account_login(cursor)
                self.set_system_setting("db_version", "1.5", "数据库版本号")
                logger.info("数据库升级到版本1.5完成")

            # 迁移遗留数据（在所有版本升级完成后执行）
            self.migrate_legacy_data(cursor)

        except Exception as e:
            logger.error(f"数据库版本检查或升级失败: {e}")
            raise

    def is_system_initialized(self) -> bool:
        """判断系统是否已完成初始化（至少存在 admin 用户）"""
        try:
            admin_user = self.get_user_by_username('admin')
            return bool(admin_user)
        except Exception:
            return False
            self.conn.commit()
            logger.info(f"admin用户ID更新完成")
        except Exception as e:
            logger.error(f"更新admin用户ID失败: {e}")
            raise
            
    def upgrade_notification_channels_table(self, cursor):
        """升级notification_channels表的type字段约束"""
        try:
            logger.info("开始升级notification_channels表...")
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True
                
            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 删除可能存在的临时表
            cursor.execute("DROP TABLE IF EXISTS notification_channels_new")

            # 创建临时表
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 复制数据，并转换不兼容的类型
            if count > 0:
                logger.info(f"复制 {count} 条通知渠道数据到新表")
                # 先查看现有数据的类型
                cursor.execute("SELECT DISTINCT type FROM notification_channels")
                existing_types = [row[0] for row in cursor.fetchall()]
                logger.info(f"现有通知渠道类型: {existing_types}")

                # 获取所有现有数据进行逐行处理
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()

                # 逐行转移数据，确保类型映射正确
                for row in existing_data:
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段，默认为qq

                    # 类型映射规则
                    type_mapping = {
                        'dingtalk': 'ding_talk',
                        'ding_talk': 'ding_talk',
                        'qq': 'qq',
                        'email': 'qq',  # 暂时映射为qq，后续版本会支持
                        'webhook': 'qq',  # 暂时映射为qq，后续版本会支持
                        'wechat': 'qq',  # 暂时映射为qq，后续版本会支持
                        'telegram': 'qq'  # 暂时映射为qq，后续版本会支持
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认转换为qq类型

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))
            
            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")
            
            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")
            
            logger.info("notification_channels表升级完成")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表失败: {e}")
            raise

    def upgrade_notification_channels_types(self, cursor):
        """升级notification_channels表支持更多渠道类型"""
        try:
            logger.info("开始升级notification_channels表支持更多渠道类型...")

            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True

            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 获取现有数据
            existing_data = []
            if count > 0:
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()
                logger.info(f"备份 {count} 条通知渠道数据")

            # 创建新表，支持所有通知渠道类型
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk','dingtalk','feishu','lark','bark','email','webhook','wechat','telegram')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 复制数据，同时处理类型映射
            if existing_data:
                logger.info(f"迁移 {len(existing_data)} 条通知渠道数据到新表")
                for row in existing_data:
                    # 处理类型映射，支持更多渠道类型
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段

                    # 完整的类型映射规则，支持所有通知渠道
                    type_mapping = {
                        'ding_talk': 'dingtalk',  # 统一为dingtalk
                        'dingtalk': 'dingtalk',
                        'qq': 'qq',
                        'feishu': 'feishu',      # 飞书通知
                        'lark': 'lark',          # 飞书通知（英文名）
                        'bark': 'bark',          # Bark通知
                        'email': 'email',        # 邮件通知
                        'webhook': 'webhook',    # Webhook通知
                        'wechat': 'wechat',      # 微信通知
                        'telegram': 'telegram'   # Telegram通知
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认为qq

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表，确保字段完整性
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))

            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")

            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")

            logger.info("notification_channels表类型升级完成")
            logger.info("✅ 现在支持以下所有通知渠道类型:")
            logger.info("   - qq (QQ通知)")
            logger.info("   - ding_talk/dingtalk (钉钉通知)")
            logger.info("   - feishu/lark (飞书通知)")
            logger.info("   - bark (Bark通知)")
            logger.info("   - email (邮件通知)")
            logger.info("   - webhook (Webhook通知)")
            logger.info("   - wechat (微信通知)")
            logger.info("   - telegram (Telegram通知)")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表类型失败: {e}")
            raise

    def upgrade_cookies_table_for_account_login(self, cursor):
        """升级cookies表支持账号密码登录功能"""
        try:
            logger.info("开始为cookies表添加账号登录相关字段...")

            # 为cookies表添加username字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT username FROM cookies LIMIT 1")
                logger.info("cookies表username字段已存在")
            except sqlite3.OperationalError:
                # username字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN username TEXT DEFAULT ''")
                logger.info("为cookies表添加username字段")

            # 为cookies表添加password字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT password FROM cookies LIMIT 1")
                logger.info("cookies表password字段已存在")
            except sqlite3.OperationalError:
                # password字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN password TEXT DEFAULT ''")
                logger.info("为cookies表添加password字段")

            # 为cookies表添加show_browser字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT show_browser FROM cookies LIMIT 1")
                logger.info("cookies表show_browser字段已存在")
            except sqlite3.OperationalError:
                # show_browser字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN show_browser INTEGER DEFAULT 0")
                logger.info("为cookies表添加show_browser字段")

            logger.info("✅ cookies表账号登录字段升级完成")
            logger.info("   - username: 用于密码登录的用户名")
            logger.info("   - password: 用于密码登录的密码")
            logger.info("   - show_browser: 登录时是否显示浏览器（0=隐藏，1=显示）")
            return True
        except Exception as e:
            logger.error(f"升级cookies表账号登录字段失败: {e}")
            raise

    def migrate_legacy_data(self, cursor):
        """迁移遗留数据到新表结构"""
        try:
            logger.info("开始检查和迁移遗留数据...")

            # 检查是否有需要迁移的老表
            legacy_tables = [
                'old_notification_channels',
                'legacy_delivery_rules',
                'old_keywords',
                'backup_cookies'
            ]

            for table_name in legacy_tables:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if cursor.fetchone():
                    logger.info(f"发现遗留表: {table_name}，开始迁移数据...")
                    self._migrate_table_data(cursor, table_name)

            logger.info("遗留数据迁移完成")
            return True
        except Exception as e:
            logger.error(f"迁移遗留数据失败: {e}")
            return False

    def _migrate_table_data(self, cursor, table_name: str):
        """迁移指定表的数据"""
        try:
            if table_name == 'old_notification_channels':
                # 迁移通知渠道数据
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                if count > 0:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    old_data = cursor.fetchall()

                    for row in old_data:
                        # 处理数据格式转换
                        cursor.execute('''
                        INSERT OR IGNORE INTO notification_channels
                        (name, user_id, type, config, enabled)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (
                            row[1] if len(row) > 1 else f"迁移渠道_{row[0]}",
                            row[2] if len(row) > 2 else 1,  # 默认admin用户
                            self._normalize_channel_type(row[3] if len(row) > 3 else 'qq'),
                            row[4] if len(row) > 4 else '{}',
                            row[5] if len(row) > 5 else True
                        ))

                    logger.info(f"成功迁移 {count} 条通知渠道数据")

                    # 迁移完成后删除老表
                    cursor.execute(f"DROP TABLE {table_name}")
                    logger.info(f"已删除遗留表: {table_name}")

        except Exception as e:
            logger.error(f"迁移表 {table_name} 数据失败: {e}")

    def _normalize_channel_type(self, old_type: str) -> str:
        """标准化通知渠道类型"""
        type_mapping = {
            'ding_talk': 'dingtalk',
            'dingtalk': 'dingtalk',
            'qq': 'qq',
            'email': 'email',
            'webhook': 'webhook',
            'wechat': 'wechat',
            'telegram': 'telegram',
            # 处理一些可能的变体
            'dingding': 'dingtalk',
            'weixin': 'wechat',
            'tg': 'telegram'
        }
        return type_mapping.get(old_type.lower(), 'qq')
    
    def _migrate_keywords_table_constraints(self, cursor):
        """迁移keywords表的约束，支持基于商品ID的唯一性校验"""
        try:
            # 检查是否已经迁移过（通过检查是否存在新的唯一索引）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_keywords_unique_with_item'")
            if cursor.fetchone():
                logger.info("keywords表约束已经迁移过，跳过")
                return

            logger.info("开始迁移keywords表约束...")

            # 1. 创建临时表，不设置主键约束
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS keywords_temp (
                cookie_id TEXT,
                keyword TEXT,
                reply TEXT,
                item_id TEXT,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 2. 复制现有数据到临时表
            cursor.execute('''
            INSERT INTO keywords_temp (cookie_id, keyword, reply, item_id)
            SELECT cookie_id, keyword, reply, item_id FROM keywords
            ''')

            # 3. 删除原表
            cursor.execute('DROP TABLE keywords')

            # 4. 重命名临时表
            cursor.execute('ALTER TABLE keywords_temp RENAME TO keywords')

            # 5. 创建复合唯一索引来实现我们需要的约束逻辑
            # 对于item_id为空的情况：(cookie_id, keyword)必须唯一
            cursor.execute('''
            CREATE UNIQUE INDEX idx_keywords_unique_no_item
            ON keywords(cookie_id, keyword)
            WHERE item_id IS NULL OR item_id = ''
            ''')

            # 对于item_id不为空的情况：(cookie_id, keyword, item_id)必须唯一
            cursor.execute('''
            CREATE UNIQUE INDEX idx_keywords_unique_with_item
            ON keywords(cookie_id, keyword, item_id)
            WHERE item_id IS NOT NULL AND item_id != ''
            ''')

            logger.info("keywords表约束迁移完成")

        except Exception as e:
            logger.error(f"迁移keywords表约束失败: {e}")
            # 如果迁移失败，尝试回滚
            try:
                cursor.execute('DROP TABLE IF EXISTS keywords_temp')
            except Exception:
                pass
            raise

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_connection(self):
        """获取数据库连接，如果已关闭则重新连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.conn

    # 敏感字段列表（日志中需要脱敏的字段）
    _SENSITIVE_FIELDS = {'password', 'password_hash', 'token', 'secret', 'secret_key', 
                         'api_key', 'cookie', 'cookies', 'session', 'session_id',
                         'authorization', 'access_token', 'refresh_token'}

    def _sanitize_param(self, param, field_name: str = ''):
        """对敏感参数进行脱敏处理"""
        if field_name and field_name.lower() in self._SENSITIVE_FIELDS:
            return "'***敏感信息已脱敏***'"
        if isinstance(param, str) and len(param) > 100:
            return f"'{param[:50]}...(已截断，总长度{len(param)})'"
        return repr(param)

    def _log_sql(self, sql: str, params: tuple = None, operation: str = "EXECUTE"):
        """记录SQL执行日志（敏感参数自动脱敏）"""
        if not self.sql_log_enabled:
            return

        # 格式化参数
        params_str = ""
        if params:
            if isinstance(params, (list, tuple)):
                if len(params) > 0:
                    # 从 SQL 语句中提取列名（用于识别敏感字段）
                    column_names = []
                    sql_upper = sql.upper()
                    if 'INSERT' in sql_upper:
                        try:
                            import re
                            cols_match = re.search(r'\(([^)]+)\)\s*VALUES', sql, re.IGNORECASE)
                            if cols_match:
                                column_names = [c.strip() for c in cols_match.group(1).split(',')]
                        except Exception:
                            pass
                    elif 'UPDATE' in sql_upper:
                        try:
                            import re
                            set_match = re.search(r'SET\s+([^WHERE]+)', sql, re.IGNORECASE)
                            if set_match:
                                set_clause = set_match.group(1)
                                column_names = [c.split('=')[0].strip() for c in set_clause.split(',') if '=' in c]
                        except Exception:
                            pass

                    # 格式化参数，对敏感字段脱敏
                    formatted_params = []
                    for i, param in enumerate(params):
                        # 确定当前参数对应的列名
                        field_name = column_names[i] if i < len(column_names) else ''
                        formatted_params.append(self._sanitize_param(param, field_name))
                    params_str = f" | 参数: [{', '.join(formatted_params)}]"

        # 格式化SQL（移除多余空白）
        formatted_sql = ' '.join(sql.split())

        # 根据配置的日志级别输出
        log_message = f"🗄️ SQL {operation}: {formatted_sql}{params_str}"

        if self.sql_log_level == 'DEBUG':
            logger.debug(log_message)
        elif self.sql_log_level == 'INFO':
            logger.info(log_message)
        elif self.sql_log_level == 'WARNING':
            logger.warning(log_message)
        else:
            logger.debug(log_message)

    def _execute_sql(self, cursor, sql: str, params: tuple = None):
        """执行SQL并记录日志"""
        self._log_sql(sql, params, "EXECUTE")
        if params:
            return cursor.execute(sql, params)
        else:
            return cursor.execute(sql)

    def _executemany_sql(self, cursor, sql: str, params_list):
        """批量执行SQL并记录日志"""
        self._log_sql(sql, f"批量执行 {len(params_list)} 条记录", "EXECUTEMANY")
        return cursor.executemany(sql, params_list)
    
    # -------------------- Cookie操作 --------------------
    def save_cookie(self, cookie_id: str, cookie_value: str, user_id: int = None) -> bool:
        """保存Cookie到数据库（已委托给 CookieRepo）"""
        return self.cookie_repo.save_cookie(cookie_id, cookie_value, user_id)

    def delete_cookie(self, cookie_id: str) -> bool:
        """从数据库删除Cookie及其关键字（已委托给 CookieRepo）"""
        return self.cookie_repo.delete_cookie(cookie_id)

    def get_cookie(self, cookie_id: str) -> Optional[str]:
        """获取指定Cookie值（已委托给 CookieRepo）"""
        return self.cookie_repo.get_cookie(cookie_id)

    def get_all_cookies(self, user_id: int = None) -> Dict[str, str]:
        """获取所有Cookie（支持用户隔离，已委托给 CookieRepo）"""
        return self.cookie_repo.get_all_cookies(user_id)

    def search_cookies(self, keyword: str, limit: int = 10):
        """search_cookies（已委托给 cookie_repo）"""
        return self.cookie_repo.search_cookies(keyword=keyword, limit=limit)

    def get_cookie_by_id(self, cookie_id: str) -> Optional[Dict[str, str]]:
        """根据ID获取Cookie信息（已委托给 CookieRepo）"""
        return self.cookie_repo.get_cookie_by_id(cookie_id)

    def get_cookie_details(self, cookie_id: str) -> Optional[Dict[str, any]]:
        """获取Cookie的详细信息（已委托给 CookieRepo）"""
        return self.cookie_repo.get_cookie_details(cookie_id)

    def get_all_cookie_details(self, user_id: int = None) -> Dict[str, Dict[str, any]]:
        """批量获取多个 Cookie 的详细信息（消除 N+1 查询，已委托给 CookieRepo）"""
        return self.cookie_repo.get_all_cookie_details(user_id)

    def update_auto_confirm(self, cookie_id: str, auto_confirm: bool) -> bool:
        """更新Cookie的自动确认发货设置（已委托给 CookieRepo）"""
        return self.cookie_repo.update_auto_confirm(cookie_id, auto_confirm)

    def update_cookie_remark(self, cookie_id: str, remark: str) -> bool:
        """更新Cookie的备注（已委托给 CookieRepo）"""
        return self.cookie_repo.update_cookie_remark(cookie_id, remark)

    def update_cookie_pause_duration(self, cookie_id: str, pause_duration: int) -> bool:
        """更新Cookie的自动回复暂停时间（已委托给 CookieRepo）"""
        return self.cookie_repo.update_cookie_pause_duration(cookie_id, pause_duration)

    def get_cookie_pause_duration(self, cookie_id: str) -> int:
        """获取Cookie的自动回复暂停时间（已委托给 CookieRepo）"""
        return self.cookie_repo.get_cookie_pause_duration(cookie_id)

    def update_cookie_account_info(self, cookie_id: str, cookie_value: str = None, username: str = None, password: str = None, show_browser: bool = None, user_id: int = None) -> bool:
        """更新Cookie的账号信息（已委托给 CookieRepo）"""
        return self.cookie_repo.update_cookie_account_info(
            cookie_id, cookie_value, username, password, show_browser, user_id
        )

    def get_auto_confirm(self, cookie_id: str) -> bool:
        """获取Cookie的自动确认发货设置（已委托给 CookieRepo）"""
        return self.cookie_repo.get_auto_confirm(cookie_id)
    
    # -------------------- 关键字操作 --------------------
    def save_keywords(self, cookie_id: str, keywords: List[Tuple[str, str]]) -> bool:
        """save_keywords（已委托给 keyword_repo）"""
        return self.keyword_repo.save_keywords(cookie_id=cookie_id, keywords=keywords)

    def save_keywords_with_item_id(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """save_keywords_with_item_id（已委托给 keyword_repo）"""
        return self.keyword_repo.save_keywords_with_item_id(cookie_id=cookie_id, keywords=keywords)

    def save_text_keywords_only(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """save_text_keywords_only（已委托给 keyword_repo）"""
        return self.keyword_repo.save_text_keywords_only(cookie_id=cookie_id, keywords=keywords)
    
    def get_keywords(self, cookie_id: str) -> List[Tuple[str, str]]:
        """get_keywords（已委托给 keyword_repo）"""
        return self.keyword_repo.get_keywords(cookie_id=cookie_id)

    def get_keywords_with_item_id(self, cookie_id: str) -> List[Tuple[str, str, str]]:
        """get_keywords_with_item_id（已委托给 keyword_repo）"""
        return self.keyword_repo.get_keywords_with_item_id(cookie_id=cookie_id)

    def check_keyword_duplicate(self, cookie_id: str, keyword: str, item_id: str = None) -> bool:
        """check_keyword_duplicate（已委托给 keyword_repo）"""
        return self.keyword_repo.check_keyword_duplicate(cookie_id=cookie_id, keyword=keyword, item_id=item_id)

    def save_image_keyword(self, cookie_id: str, keyword: str, image_url: str, item_id: str = None) -> bool:
        """save_image_keyword（已委托给 keyword_repo）"""
        return self.keyword_repo.save_image_keyword(cookie_id=cookie_id, keyword=keyword, image_url=image_url, item_id=item_id)

    def get_keywords_with_type(self, cookie_id: str) -> List[Dict[str, any]]:
        """get_keywords_with_type（已委托给 keyword_repo）"""
        return self.keyword_repo.get_keywords_with_type(cookie_id=cookie_id)

    def update_keyword_image_url(self, cookie_id: str, keyword: str, new_image_url: str) -> bool:
        """update_keyword_image_url（已委托给 keyword_repo）"""
        return self.keyword_repo.update_keyword_image_url(cookie_id=cookie_id, keyword=keyword, new_image_url=new_image_url)

    def delete_keyword_by_index(self, cookie_id: str, index: int) -> bool:
        """delete_keyword_by_index（已委托给 keyword_repo）"""
        return self.keyword_repo.delete_keyword_by_index(cookie_id=cookie_id, index=index)


    def get_all_keywords(self, user_id: int = None) -> Dict[str, List[Tuple[str, str]]]:
        """get_all_keywords（已委托给 keyword_repo）"""
        return self.keyword_repo.get_all_keywords(user_id=user_id)

    def save_cookie_status(self, cookie_id: str, enabled: bool):
        """保存Cookie的启用状态（已委托给 CookieRepo）"""
        self.cookie_repo.save_cookie_status(cookie_id, enabled)

    def get_cookie_status(self, cookie_id: str) -> bool:
        """获取Cookie的启用状态（已委托给 CookieRepo）"""
        return self.cookie_repo.get_cookie_status(cookie_id)

    def get_all_cookie_status(self) -> Dict[str, bool]:
        """获取所有Cookie的启用状态（已委托给 CookieRepo）"""
        return self.cookie_repo.get_all_cookie_status()

    # -------------------- AI回复设置操作 --------------------
    def save_ai_reply_settings(self, cookie_id: str, settings: dict) -> bool:
        """save_ai_reply_settings（已委托给 ai_reply_repo）"""
        return self.ai_reply_repo.save_ai_reply_settings(cookie_id=cookie_id, settings=settings)

    def get_ai_reply_settings(self, cookie_id: str) -> dict:
        """get_ai_reply_settings（已委托给 ai_reply_repo）"""
        return self.ai_reply_repo.get_ai_reply_settings(cookie_id=cookie_id)

    def get_all_ai_reply_settings(self) -> Dict[str, dict]:
        """get_all_ai_reply_settings（已委托给 ai_reply_repo）"""
        return self.ai_reply_repo.get_all_ai_reply_settings()

    # -------------------- 默认回复操作 --------------------
    def save_default_reply(self, cookie_id: str, enabled: bool, reply_content: str = None, reply_once: bool = False, reply_image_url: str = None):
        """save_default_reply（已委托给 default_reply_repo）"""
        return self.default_reply_repo.save_default_reply(
            cookie_id=cookie_id, enabled=enabled, reply_content=reply_content,
            reply_once=reply_once, reply_image_url=reply_image_url,
        )

    def get_default_reply(self, cookie_id: str) -> Optional[Dict[str, any]]:
        """get_default_reply（已委托给 default_reply_repo）"""
        return self.default_reply_repo.get_default_reply(cookie_id=cookie_id)

    def get_all_default_replies(self) -> Dict[str, Dict[str, any]]:
        """get_all_default_replies（已委托给 default_reply_repo）"""
        return self.default_reply_repo.get_all_default_replies()

    def add_default_reply_record(self, cookie_id: str, chat_id: str):
        """add_default_reply_record（已委托给 default_reply_repo）"""
        return self.default_reply_repo.add_default_reply_record(cookie_id=cookie_id, chat_id=chat_id)

    def has_default_reply_record(self, cookie_id: str, chat_id: str) -> bool:
        """has_default_reply_record（已委托给 default_reply_repo）"""
        return self.default_reply_repo.has_default_reply_record(cookie_id=cookie_id, chat_id=chat_id)

    def clear_default_reply_records(self, cookie_id: str):
        """clear_default_reply_records（已委托给 default_reply_repo）"""
        return self.default_reply_repo.clear_default_reply_records(cookie_id=cookie_id)

    def find_chat_id_by_buyer(self, cookie_id: str, buyer_id: str) -> str:
        """find_chat_id_by_buyer（已委托给 default_reply_repo）"""
        return self.default_reply_repo.find_chat_id_by_buyer(cookie_id=cookie_id, buyer_id=buyer_id)

    def delete_default_reply(self, cookie_id: str) -> bool:
        """delete_default_reply（已委托给 default_reply_repo）"""
        return self.default_reply_repo.delete_default_reply(cookie_id=cookie_id)

    def update_default_reply_image_url(self, cookie_id: str, new_image_url: str) -> bool:
        """update_default_reply_image_url（已委托给 default_reply_repo）"""
        return self.default_reply_repo.update_default_reply_image_url(cookie_id=cookie_id, new_image_url=new_image_url)

    # -------------------- 通知渠道操作 --------------------
    def create_notification_channel(self, name: str, channel_type: str, config: str, user_id: int = None) -> int:
        """create_notification_channel（已委托给 notification_repo）"""
        return self.notification_repo.create_notification_channel(
            name=name, channel_type=channel_type, config=config, user_id=user_id,
        )

    def get_notification_channels(self, user_id: int = None) -> List[Dict[str, any]]:
        """get_notification_channels（已委托给 notification_repo）"""
        return self.notification_repo.get_notification_channels(user_id=user_id)

    def get_notification_channel(self, channel_id: int) -> Optional[Dict[str, any]]:
        """get_notification_channel（已委托给 notification_repo）"""
        return self.notification_repo.get_notification_channel(channel_id=channel_id)

    def update_notification_channel(self, channel_id: int, name: str, config: str, enabled: bool = True) -> bool:
        """update_notification_channel（已委托给 notification_repo）"""
        return self.notification_repo.update_notification_channel(
            channel_id=channel_id, name=name, config=config, enabled=enabled,
        )

    def delete_notification_channel(self, channel_id: int) -> bool:
        """delete_notification_channel（已委托给 notification_repo）"""
        return self.notification_repo.delete_notification_channel(channel_id=channel_id)

    # -------------------- 消息通知配置操作 --------------------
    def set_message_notification(self, cookie_id: str, channel_id: int, enabled: bool = True) -> bool:
        """set_message_notification（已委托给 notification_repo）"""
        return self.notification_repo.set_message_notification(
            cookie_id=cookie_id, channel_id=channel_id, enabled=enabled,
        )

    def get_account_notifications(self, cookie_id: str) -> List[Dict[str, any]]:
        """get_account_notifications（已委托给 notification_repo）"""
        return self.notification_repo.get_account_notifications(cookie_id=cookie_id)

    def get_all_message_notifications(self) -> Dict[str, List[Dict[str, any]]]:
        """get_all_message_notifications（已委托给 notification_repo）"""
        return self.notification_repo.get_all_message_notifications()

    def delete_message_notification(self, notification_id: int) -> bool:
        """delete_message_notification（已委托给 notification_repo）"""
        return self.notification_repo.delete_message_notification(notification_id=notification_id)

    def delete_account_notifications(self, cookie_id: str) -> bool:
        """delete_account_notifications（已委托给 notification_repo）"""
        return self.notification_repo.delete_account_notifications(cookie_id=cookie_id)

    # -------------------- 备份和恢复操作 --------------------
    def export_backup(self, user_id: int = None) -> Dict[str, any]:
        """导出系统备份数据（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                backup_data = {
                    'version': '1.0',
                    'timestamp': time.time(),
                    'user_id': user_id,
                    'data': {}
                }

                if user_id is not None:
                    # 用户级备份：只备份该用户的数据
                    # 备份用户的cookies
                    self._execute_sql(cursor, "SELECT * FROM cookies WHERE user_id = ?", (user_id,))
                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()
                    backup_data['data']['cookies'] = {
                        'columns': columns,
                        'rows': [list(row) for row in rows]
                    }

                    # 备份用户cookies相关的其他数据
                    user_cookie_ids = [row[0] for row in rows]  # 获取用户的cookie_id列表

                    if user_cookie_ids:
                        placeholders = ','.join(['?' for _ in user_cookie_ids])

                        # 备份关键字
                        cursor.execute(f"SELECT * FROM keywords WHERE cookie_id IN ({placeholders})", user_cookie_ids)
                        columns = [description[0] for description in cursor.description]
                        rows = cursor.fetchall()
                        backup_data['data']['keywords'] = {
                            'columns': columns,
                            'rows': [list(row) for row in rows]
                        }

                        # 备份其他相关表
                        related_tables = ['cookie_status', 'default_replies', 'message_notifications',
                                        'item_info', 'ai_reply_settings', 'ai_conversations']

                        for table in related_tables:
                            cursor.execute(f"SELECT * FROM {table} WHERE cookie_id IN ({placeholders})", user_cookie_ids)
                            columns = [description[0] for description in cursor.description]
                            rows = cursor.fetchall()
                            backup_data['data'][table] = {
                                'columns': columns,
                                'rows': [list(row) for row in rows]
                            }
                else:
                    # 系统级备份：备份所有数据
                    tables = [
                        'cookies', 'keywords', 'cookie_status', 'cards',
                        'delivery_rules', 'default_replies', 'notification_channels',
                        'message_notifications', 'system_settings', 'item_info',
                        'ai_reply_settings', 'ai_conversations', 'ai_item_cache'
                    ]

                    for table in tables:
                        cursor.execute(f"SELECT * FROM {table}")
                        columns = [description[0] for description in cursor.description]
                        rows = cursor.fetchall()

                        backup_data['data'][table] = {
                            'columns': columns,
                            'rows': [list(row) for row in rows]
                        }

                logger.info(f"导出备份成功，用户ID: {user_id}")
                return backup_data

            except Exception as e:
                logger.error(f"导出备份失败: {e}")
                raise

    def import_backup(self, backup_data: Dict[str, any], user_id: int = None) -> bool:
        """导入系统备份数据（支持用户隔离）"""
        with self.lock:
            try:
                # 验证备份数据格式
                if not isinstance(backup_data, dict) or 'data' not in backup_data:
                    raise ValueError("备份数据格式无效")

                # 开始事务
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "BEGIN TRANSACTION")

                if user_id is not None:
                    # 用户级导入：只清空该用户的数据
                    # 获取用户的cookie_id列表
                    self._execute_sql(cursor, "SELECT id FROM cookies WHERE user_id = ?", (user_id,))
                    user_cookie_ids = [row[0] for row in cursor.fetchall()]

                    if user_cookie_ids:
                        placeholders = ','.join(['?' for _ in user_cookie_ids])

                        # 删除用户相关数据
                        related_tables = ['message_notifications', 'default_replies', 'item_info',
                                        'cookie_status', 'keywords', 'ai_conversations', 'ai_reply_settings']

                        for table in related_tables:
                            cursor.execute(f"DELETE FROM {table} WHERE cookie_id IN ({placeholders})", user_cookie_ids)

                        # 删除用户的cookies
                        self._execute_sql(cursor, "DELETE FROM cookies WHERE user_id = ?", (user_id,))
                else:
                    # 系统级导入：清空所有数据（除了用户和管理员密码）
                    tables = [
                        'message_notifications', 'notification_channels', 'default_replies',
                        'delivery_rules', 'cards', 'item_info', 'cookie_status', 'keywords',
                        'ai_conversations', 'ai_reply_settings', 'ai_item_cache', 'cookies'
                    ]

                    for table in tables:
                        cursor.execute(f"DELETE FROM {table}")

                    # 清空系统设置（保留管理员密码）
                    self._execute_sql(cursor, "DELETE FROM system_settings WHERE key != 'admin_password_hash'")

                # 导入数据
                data = backup_data['data']
                for table_name, table_data in data.items():
                    if table_name not in ['cookies', 'keywords', 'cookie_status', 'cards',
                                        'delivery_rules', 'default_replies', 'notification_channels',
                                        'message_notifications', 'system_settings', 'item_info',
                                        'ai_reply_settings', 'ai_conversations', 'ai_item_cache']:
                        continue

                    columns = table_data['columns']
                    rows = table_data['rows']

                    if not rows:
                        continue

                    # 如果是用户级导入，需要确保cookies表的user_id正确
                    if user_id is not None and table_name == 'cookies':
                        # 更新所有导入的cookies的user_id
                        updated_rows = []
                        for row in rows:
                            row_dict = dict(zip(columns, row))
                            row_dict['user_id'] = user_id
                            updated_rows.append([row_dict[col] for col in columns])
                        rows = updated_rows

                    # 构建插入语句
                    placeholders = ','.join(['?' for _ in columns])

                    if table_name == 'system_settings':
                        # 系统设置需要特殊处理，避免覆盖管理员密码
                        for row in rows:
                            if len(row) >= 1 and row[0] != 'admin_password_hash':
                                cursor.execute(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", row)
                    else:
                        cursor.executemany(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", rows)

                # 提交事务
                self.conn.commit()
                logger.info("导入备份成功")
                return True

            except Exception as e:
                logger.error(f"导入备份失败: {e}")
                self.conn.rollback()
                return False

    # -------------------- 系统设置操作 --------------------
    def get_system_setting(self, key: str) -> Optional[str]:
        """get_system_setting（已委托给 system_settings_repo）"""
        return self.system_settings_repo.get_system_setting(key=key)

    def set_system_setting(self, key: str, value: str, description: str = None) -> bool:
        """set_system_setting（已委托给 system_settings_repo）"""
        return self.system_settings_repo.set_system_setting(key=key, value=value, description=description)

    def get_all_system_settings(self) -> Dict[str, str]:
        """get_all_system_settings（已委托给 system_settings_repo）"""
        return self.system_settings_repo.get_all_system_settings()

    # 管理员密码现在统一使用用户表管理，不再需要单独的方法

    # ==================== 用户管理方法 ====================

    def create_user(self, username: str, email: str, password: str) -> bool:
        """创建新用户（已委托给 UserRepo）"""
        return self.user_repo.create_user(username, email, password)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户信息（已委托给 UserRepo）"""
        return self.user_repo.get_user_by_username(username)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱获取用户信息（已委托给 UserRepo）"""
        return self.user_repo.get_user_by_email(email)

    def verify_user_password(self, username: str, password: str) -> bool:
        """验证用户密码（已委托给 UserRepo）"""
        return self.user_repo.verify_user_password(username, password)

    def update_user_password(self, username: str, new_password: str) -> bool:
        """更新用户密码（已委托给 UserRepo）"""
        return self.user_repo.update_user_password(username, new_password)

    def generate_verification_code(self) -> str:
        """生成6位数字验证码（已委托给 utils.captcha_generator）"""
        from utils.captcha_generator import generate_verification_code as _gen
        return _gen()

    def generate_captcha(self) -> Tuple[str, str]:
        """生成图形验证码（已委托给 utils.captcha_generator）

        返回: (验证码文本, base64编码的图片)
        """
        from utils.captcha_generator import generate_captcha as _gen
        return _gen()

    def save_captcha(self, session_id: str, captcha_text: str, expires_minutes: int = 5) -> bool:
        """save_captcha（已委托给 verification_repo）"""
        return self.verification_repo.save_captcha(
            session_id=session_id, captcha_text=captcha_text, expires_minutes=expires_minutes,
        )

    def verify_captcha(self, session_id: str, user_input: str) -> bool:
        """verify_captcha（已委托给 verification_repo）"""
        return self.verification_repo.verify_captcha(session_id=session_id, user_input=user_input)

    def save_verification_code(self, email: str, code: str, code_type: str = 'register', expires_minutes: int = 10) -> bool:
        """save_verification_code（已委托给 verification_repo）"""
        return self.verification_repo.save_verification_code(
            email=email, code=code, code_type=code_type, expires_minutes=expires_minutes,
        )

    def verify_email_code(self, email: str, code: str, code_type: str = 'register') -> bool:
        """verify_email_code（已委托给 verification_repo）"""
        return self.verification_repo.verify_email_code(email=email, code=code, code_type=code_type)

    async def send_verification_email(self, email: str, code: str) -> bool:
        """发送验证码邮件（支持SMTP和API两种方式）"""
        try:
            subject = "闲鱼自动回复系统 - 邮箱验证码"
            # 使用简单的纯文本邮件内容
            text_content = f"""【闲鱼自动回复系统】邮箱验证码

您好！

感谢您使用闲鱼自动回复系统。为了确保账户安全，请使用以下验证码完成邮箱验证：

验证码：{code}

重要提醒：
• 验证码有效期为 10 分钟，请及时使用
• 请勿将验证码分享给任何人
• 如非本人操作，请忽略此邮件
• 系统不会主动索要您的验证码

如果您在使用过程中遇到任何问题，请联系我们的技术支持团队。
感谢您选择闲鱼自动回复系统！

---
此邮件由系统自动发送，请勿直接回复
© 2025 闲鱼自动回复系统"""

            # 从系统设置读取SMTP配置
            try:
                smtp_server = self.get_system_setting('smtp_server') or ''
                smtp_port = int(self.get_system_setting('smtp_port') or 0)
                smtp_user = self.get_system_setting('smtp_user') or ''
                smtp_password = self.get_system_setting('smtp_password') or ''
                smtp_from = (self.get_system_setting('smtp_from') or '').strip() or smtp_user
                smtp_use_tls = (self.get_system_setting('smtp_use_tls') or 'true').lower() == 'true'
                smtp_use_ssl = (self.get_system_setting('smtp_use_ssl') or 'false').lower() == 'true'
            except Exception as e:
                logger.error(f"读取SMTP系统设置失败: {e}")
                # 如果读取配置失败，使用API方式
                return await self._send_email_via_api(email, subject, text_content)

            # 检查SMTP配置是否完整
            if smtp_server and smtp_port and smtp_user and smtp_password:
                # 配置完整，使用SMTP方式发送
                logger.info(f"使用SMTP方式发送验证码邮件: {email}")
                return await self._send_email_via_smtp(email, subject, text_content,
                                                     smtp_server, smtp_port, smtp_user,
                                                     smtp_password, smtp_from, smtp_use_tls, smtp_use_ssl)
            else:
                # 配置不完整，使用API方式发送
                logger.info(f"SMTP配置不完整，使用API方式发送验证码邮件: {email}")
                return await self._send_email_via_api(email, subject, text_content)

        except Exception as e:
            logger.error(f"发送验证码邮件异常: {e}")
            return False

    async def _send_email_via_smtp(self, email: str, subject: str, text_content: str,
                                 smtp_server: str, smtp_port: int, smtp_user: str,
                                 smtp_password: str, smtp_from: str, smtp_use_tls: bool, smtp_use_ssl: bool) -> bool:
        """使用SMTP方式发送邮件"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = smtp_from
            msg['To'] = email

            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))

            if smtp_use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)

            server.ehlo()
            if smtp_use_tls and not smtp_use_ssl:
                server.starttls()
                server.ehlo()

            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [email], msg.as_string())
            server.quit()

            logger.info(f"验证码邮件发送成功(SMTP): {email}")
            return True
        except Exception as e:
            logger.error(f"SMTP发送验证码邮件失败: {e}")
            # SMTP发送失败，尝试使用API方式
            logger.info(f"SMTP发送失败，尝试使用API方式发送: {email}")
            return await self._send_email_via_api(email, subject, text_content)

    async def _send_email_via_api(self, email: str, subject: str, text_content: str) -> bool:
        """使用API方式发送邮件"""
        try:
            import aiohttp

            # 使用GET请求发送邮件
            api_url = "https://dy.zhinianboke.com/api/emailSend"
            params = {
                'subject': subject,
                'receiveUser': email,
                'sendHtml': text_content
            }

            async with aiohttp.ClientSession() as session:
                try:
                    logger.info(f"使用API发送验证码邮件: {email}")
                    async with session.get(api_url, params=params, timeout=15) as response:
                        response_text = await response.text()
                        logger.info(f"邮件API响应: {response.status}")

                        if response.status == 200:
                            logger.info(f"验证码邮件发送成功(API): {email}")
                            return True
                        else:
                            logger.error(f"API发送验证码邮件失败: {email}, 状态码: {response.status}, 响应: {response_text[:200]}")
                            return False
                except Exception as e:
                    logger.error(f"API邮件发送异常: {email}, 错误: {e}")
                    return False
        except Exception as e:
            logger.error(f"API邮件发送方法异常: {e}")
            return False

    # ==================== 卡券管理方法 ====================

    def create_card(self, name: str, card_type: str, api_config=None,
                   text_content: str = None, data_content: str = None, image_url: str = None,
                   description: str = None, enabled: bool = True, delay_seconds: int = 0,
                   is_multi_spec: bool = False, spec_name: str = None, spec_value: str = None,
                   user_id: int = None):
        """create_card（已委托给 card_repo）"""
        return self.card_repo.create_card(name=name, card_type=card_type, api_config=api_config, text_content=text_content, data_content=data_content, image_url=image_url, description=description, enabled=enabled, delay_seconds=delay_seconds, is_multi_spec=is_multi_spec, spec_name=spec_name, spec_value=spec_value, user_id=user_id)

    def get_all_cards(self, user_id: int = None):
        """get_all_cards（已委托给 card_repo）"""
        return self.card_repo.get_all_cards(user_id=user_id)

    def search_cards(self, keyword: str, limit: int = 10):
        """search_cards（已委托给 card_repo）"""
        return self.card_repo.search_cards(keyword=keyword, limit=limit)

    def get_card_by_id(self, card_id: int, user_id: int = None):
        """get_card_by_id（已委托给 card_repo）"""
        return self.card_repo.get_card_by_id(card_id=card_id, user_id=user_id)

    def update_card(self, card_id: int, name: str = None, card_type: str = None,
                   api_config=None, text_content: str = None, data_content: str = None,
                   image_url: str = None, description: str = None, enabled: bool = None,
                   delay_seconds: int = None, is_multi_spec: bool = None, spec_name: str = None,
                   spec_value: str = None):
        """update_card（已委托给 card_repo）"""
        return self.card_repo.update_card(card_id=card_id, name=name, card_type=card_type, api_config=api_config, text_content=text_content, data_content=data_content, image_url=image_url, description=description, enabled=enabled, delay_seconds=delay_seconds, is_multi_spec=is_multi_spec, spec_name=spec_name, spec_value=spec_value)

    def update_card_image_url(self, card_id: int, new_image_url: str) -> bool:
        """update_card_image_url（已委托给 card_repo）"""
        return self.card_repo.update_card_image_url(card_id=card_id, new_image_url=new_image_url)

    def create_delivery_rule(self, keyword: str, card_id: int, delivery_count: int = 1,
                           enabled: bool = True, description: str = None, user_id: int = None):
        """create_delivery_rule（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.create_delivery_rule(keyword=keyword, card_id=card_id, delivery_count=delivery_count, enabled=enabled, description=description, user_id=user_id)

    def get_all_delivery_rules(self, user_id: int = None):
        """get_all_delivery_rules（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.get_all_delivery_rules(user_id=user_id)

    def get_delivery_rules_by_keyword(self, keyword: str):
        """get_delivery_rules_by_keyword（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.get_delivery_rules_by_keyword(keyword=keyword)

    def get_delivery_rule_by_id(self, rule_id: int, user_id: int = None):
        """get_delivery_rule_by_id（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.get_delivery_rule_by_id(rule_id=rule_id, user_id=user_id)

    def update_delivery_rule(self, rule_id: int, keyword: str = None, card_id: int = None,
                           delivery_count: int = None, enabled: bool = None,
                           description: str = None, user_id: int = None):
        """update_delivery_rule（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.update_delivery_rule(rule_id=rule_id, keyword=keyword, card_id=card_id, delivery_count=delivery_count, enabled=enabled, description=description, user_id=user_id)

    def increment_delivery_times(self, rule_id: int):
        """increment_delivery_times（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.increment_delivery_times(rule_id=rule_id)

    def get_delivery_rules_by_keyword_and_spec(self, keyword: str, spec_name: str = None, spec_value: str = None):
        """get_delivery_rules_by_keyword_and_spec（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.get_delivery_rules_by_keyword_and_spec(keyword=keyword, spec_name=spec_name, spec_value=spec_value)

    def delete_card(self, card_id: int):
        """delete_card（已委托给 card_repo）"""
        return self.card_repo.delete_card(card_id=card_id)

    def delete_delivery_rule(self, rule_id: int, user_id: int = None):
        """delete_delivery_rule（已委托给 delivery_rule_repo）"""
        return self.delivery_rule_repo.delete_delivery_rule(rule_id=rule_id, user_id=user_id)

    def consume_batch_data(self, card_id: int):
        """consume_batch_data（已委托给 card_repo）"""
        return self.card_repo.consume_batch_data(card_id=card_id)

    # ==================== 商品信息管理 ====================

    def save_item_basic_info(self, cookie_id: str, item_id: str, item_title: str = None,
                            item_description: str = None, item_category: str = None,
                            item_price: str = None, item_detail: str = None,
                            item_image: str = None) -> bool:
        """save_item_basic_info（已委托给 item_repo）"""
        return self.item_repo.save_item_basic_info(
            cookie_id=cookie_id, item_id=item_id, item_title=item_title,
            item_description=item_description, item_category=item_category,
            item_price=item_price, item_detail=item_detail, item_image=item_image,
        )

    def save_item_info(self, cookie_id: str, item_id: str, item_data = None) -> bool:
        """save_item_info（已委托给 item_repo）"""
        return self.item_repo.save_item_info(
            cookie_id=cookie_id, item_id=item_id, item_data=item_data
        )

    def get_item_info(self, cookie_id: str, item_id: str) -> Optional[Dict]:
        """get_item_info（已委托给 item_repo）"""
        return self.item_repo.get_item_info(cookie_id=cookie_id, item_id=item_id)

    def update_item_multi_spec_status(self, cookie_id: str, item_id: str, is_multi_spec: bool) -> bool:
        """update_item_multi_spec_status（已委托给 item_repo）"""
        return self.item_repo.update_item_multi_spec_status(
            cookie_id=cookie_id, item_id=item_id, is_multi_spec=is_multi_spec
        )

    def get_item_multi_spec_status(self, cookie_id: str, item_id: str) -> bool:
        """get_item_multi_spec_status（已委托给 item_repo）"""
        return self.item_repo.get_item_multi_spec_status(cookie_id=cookie_id, item_id=item_id)

    def update_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str, multi_quantity_delivery: bool) -> bool:
        """update_item_multi_quantity_delivery_status（已委托给 item_repo）"""
        return self.item_repo.update_item_multi_quantity_delivery_status(
            cookie_id=cookie_id, item_id=item_id, multi_quantity_delivery=multi_quantity_delivery
        )

    def get_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str) -> bool:
        """get_item_multi_quantity_delivery_status（已委托给 item_repo）"""
        return self.item_repo.get_item_multi_quantity_delivery_status(cookie_id=cookie_id, item_id=item_id)

    def get_items_by_cookie(self, cookie_id: str) -> List[Dict]:
        """get_items_by_cookie（已委托给 item_repo）"""
        return self.item_repo.get_items_by_cookie(cookie_id=cookie_id)

    def get_all_items(self) -> List[Dict]:
        """get_all_items（已委托给 item_repo）"""
        return self.item_repo.get_all_items()

    def search_items(self, keyword: str, limit: int = 10):
        """search_items（已委托给 item_repo）"""
        return self.item_repo.search_items(keyword=keyword, limit=limit)

    def update_item_detail(self, cookie_id: str, item_id: str, item_detail: str) -> bool:
        """update_item_detail（已委托给 item_repo）"""
        return self.item_repo.update_item_detail(
            cookie_id=cookie_id, item_id=item_id, item_detail=item_detail
        )

    def update_item_title_only(self, cookie_id: str, item_id: str, item_title: str) -> bool:
        """update_item_title_only（已委托给 item_repo）"""
        return self.item_repo.update_item_title_only(
            cookie_id=cookie_id, item_id=item_id, item_title=item_title
        )

    def batch_save_item_basic_info(self, items_data: list) -> int:
        """batch_save_item_basic_info（已委托给 item_repo）"""
        return self.item_repo.batch_save_item_basic_info(items_data=items_data)

    def get_item_by_id(self, item_id: str):
        """get_item_by_id（已委托给 item_repo）"""
        return self.item_repo.get_item_by_id(item_id=item_id)

    def delete_item_info(self, cookie_id: str, item_id: str) -> bool:
        """delete_item_info（已委托给 item_repo）"""
        return self.item_repo.delete_item_info(cookie_id=cookie_id, item_id=item_id)

    def batch_delete_item_info(self, items_to_delete: list) -> int:
        """batch_delete_item_info（已委托给 item_repo）"""
        return self.item_repo.batch_delete_item_info(items_to_delete=items_to_delete)

    # ==================== 用户设置管理方法 ====================

    def get_user_settings(self, user_id: int):
        """get_user_settings（已委托给 user_settings_repo）"""
        return self.user_settings_repo.get_user_settings(user_id=user_id)

    def get_user_setting(self, user_id: int, key: str):
        """get_user_setting（已委托给 user_settings_repo）"""
        return self.user_settings_repo.get_user_setting(user_id=user_id, key=key)

    def set_user_setting(self, user_id: int, key: str, value: str, description: str = None):
        """set_user_setting（已委托给 user_settings_repo）"""
        return self.user_settings_repo.set_user_setting(
            user_id=user_id, key=key, value=value, description=description
        )

    # ==================== 管理员专用方法 ====================

    def get_all_users(self):
        """获取所有用户信息（管理员专用，已委托给 UserRepo）"""
        return self.user_repo.get_all_users()

    def get_user_by_id(self, user_id: int):
        """根据ID获取用户信息（已委托给 UserRepo）"""
        return self.user_repo.get_user_by_id(user_id)

    def delete_user_and_data(self, user_id: int):
        """删除用户及其所有相关数据（已委托给 UserRepo）"""
        return self.user_repo.delete_user_and_data(user_id)

    def get_table_data(self, table_name: str):
        """获取指定表的所有数据（已委托给 admin_repo）"""
        return self.admin_repo.get_table_data(table_name)

    def insert_or_update_order(self, order_id: str, item_id: str = None, buyer_id: str = None,
                              spec_name: str = None, spec_value: str = None, quantity: str = None,
                              amount: str = None, order_status: str = None, cookie_id: str = None,
                              is_bargain: bool = None, created_at: str = None, receiver_name: str = None,
                              receiver_phone: str = None, receiver_address: str = None,
                              system_shipped: bool = None, expected_version: int = None,
                              chat_id: str = None):
        """插入或更新订单信息（已委托给 OrderRepo）"""
        return self.order_repo.insert_or_update_order(
            order_id=order_id, item_id=item_id, buyer_id=buyer_id,
            spec_name=spec_name, spec_value=spec_value, quantity=quantity,
            amount=amount, order_status=order_status, cookie_id=cookie_id,
            is_bargain=is_bargain, created_at=created_at,
            receiver_name=receiver_name, receiver_phone=receiver_phone,
            receiver_address=receiver_address, system_shipped=system_shipped,
            expected_version=expected_version, chat_id=chat_id,
        )

    def get_order_by_id(self, order_id: str):
        """根据订单ID获取订单信息（已委托给 OrderRepo）"""
        return self.order_repo.get_order_by_id(order_id)

    def get_order_status_logs(self, order_id: str):
        """查询订单状态变更日志（已委托给 OrderRepo）"""
        return self.order_repo.get_order_status_logs(order_id)

    def search_orders(self, keyword: str, limit: int = 10):
        """跨字段搜索订单（已委托给 OrderRepo）"""
        return self.order_repo.search_orders(keyword=keyword, limit=limit)

    def delete_order(self, order_id: str):
        """删除订单（已委托给 OrderRepo）"""
        return self.order_repo.delete_order(order_id)

    def get_recent_order_by_item_and_buyer(self, item_id: str, buyer_id: str):
        """根据商品ID和买家ID获取最近的订单（已委托给 OrderRepo）"""
        return self.order_repo.get_recent_order_by_item_and_buyer(item_id, buyer_id)

    def get_orders_by_cookie(self, cookie_id: str, limit: int = 100):
        """根据Cookie ID获取订单列表（已委托给 OrderRepo）"""
        return self.order_repo.get_orders_by_cookie(cookie_id, limit)

    def get_orders_by_cookies(self, cookie_ids, limit_per_cookie: int = 1000):
        """批量获取多个 Cookie 的订单（已委托给 OrderRepo）"""
        return self.order_repo.get_orders_by_cookies(cookie_ids, limit_per_cookie)

    def get_all_orders(self, limit: int = 1000):
        """获取所有订单列表（已委托给 OrderRepo）"""
        return self.order_repo.get_all_orders(limit)

    def get_all_item_titles(self):
        """get_all_item_titles（已委托给 item_repo）"""
        return self.item_repo.get_all_item_titles()

    def delete_table_record(self, table_name: str, record_id: str):
        """删除指定表的指定记录（已委托给 admin_repo，PRAGMA 自动探测主键）"""
        return self.admin_repo.delete_table_record(table_name, record_id)

    def clear_table_data(self, table_name: str):
        """清空指定表的所有数据（已委托给 admin_repo）"""
        return self.admin_repo.clear_table_data(table_name)

    def upgrade_keywords_table_for_image_support(self, cursor):
        """升级keywords表以支持图片关键词"""
        try:
            logger.info("开始升级keywords表以支持图片关键词...")

            # 检查是否已经有type字段
            cursor.execute("PRAGMA table_info(keywords)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'type' not in columns:
                logger.info("添加type字段到keywords表...")
                cursor.execute("ALTER TABLE keywords ADD COLUMN type TEXT DEFAULT 'text'")

            if 'image_url' not in columns:
                logger.info("添加image_url字段到keywords表...")
                cursor.execute("ALTER TABLE keywords ADD COLUMN image_url TEXT")

            # 为现有记录设置默认类型
            cursor.execute("UPDATE keywords SET type = 'text' WHERE type IS NULL")

            logger.info("keywords表升级完成")
            return True

        except Exception as e:
            logger.error(f"升级keywords表失败: {e}")
            raise
    def get_item_replay(self, item_id: str) -> Optional[Dict[str, Any]]:
        """get_item_replay（已委托给 item_repo）"""
        return self.item_repo.get_item_replay(item_id=item_id)

    def get_item_reply(self, cookie_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """get_item_reply（已委托给 item_repo）"""
        return self.item_repo.get_item_reply(cookie_id=cookie_id, item_id=item_id)

    def update_item_reply(self, cookie_id: str, item_id: str, reply_content: str) -> bool:
        """update_item_reply（已委托给 item_repo）"""
        return self.item_repo.update_item_reply(
            cookie_id=cookie_id, item_id=item_id, reply_content=reply_content
        )

    def get_itemReplays_by_cookie(self, cookie_id: str) -> List[Dict]:
        """get_itemReplays_by_cookie（已委托给 item_repo）"""
        return self.item_repo.get_itemReplays_by_cookie(cookie_id=cookie_id)

    def delete_item_reply(self, cookie_id: str, item_id: str) -> bool:
        """delete_item_reply（已委托给 item_repo）"""
        return self.item_repo.delete_item_reply(cookie_id=cookie_id, item_id=item_id)

    def batch_delete_item_replies(self, items: List[Dict[str, str]]) -> Dict[str, int]:
        """batch_delete_item_replies（已委托给 item_repo）"""
        return self.item_repo.batch_delete_item_replies(items=items)

    # ==================== 风控日志管理 ====================

    def add_risk_control_log(self, cookie_id: str, event_type: str = 'slider_captcha',
                           event_description: str = None, processing_result: str = None,
                           processing_status: str = 'processing', error_message: str = None) -> bool:
        """add_risk_control_log（已委托给 risk_control_repo）"""
        return self.risk_control_repo.add_risk_control_log(
            cookie_id=cookie_id, event_type=event_type, event_description=event_description,
            processing_result=processing_result, processing_status=processing_status,
            error_message=error_message,
        )

    def update_risk_control_log(self, log_id: int, processing_result: str = None,
                              processing_status: str = None, error_message: str = None) -> bool:
        """update_risk_control_log（已委托给 risk_control_repo）"""
        return self.risk_control_repo.update_risk_control_log(
            log_id=log_id, processing_result=processing_result,
            processing_status=processing_status, error_message=error_message,
        )

    def get_risk_control_logs(self, cookie_id: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """get_risk_control_logs（已委托给 risk_control_repo）"""
        return self.risk_control_repo.get_risk_control_logs(
            cookie_id=cookie_id, limit=limit, offset=offset
        )

    def get_risk_control_logs_count(self, cookie_id: str = None) -> int:
        """get_risk_control_logs_count（已委托给 risk_control_repo）"""
        return self.risk_control_repo.get_risk_control_logs_count(cookie_id=cookie_id)

    def delete_risk_control_log(self, log_id: int) -> bool:
        """delete_risk_control_log（已委托给 risk_control_repo）"""
        return self.risk_control_repo.delete_risk_control_log(log_id=log_id)
    
    def cleanup_old_data(self, days: int = 90) -> dict:
        """清理过期的历史数据，防止数据库无限增长
        
        Args:
            days: 保留最近N天的数据，默认90天
            
        Returns:
            清理统计信息
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                stats = {}
                
                # 清理AI对话历史（保留最近90天）
                try:
                    cursor.execute(
                        "DELETE FROM ai_conversations WHERE created_at < datetime('now', '-' || ? || ' days')",
                        (days,)
                    )
                    stats['ai_conversations'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的AI对话记录（{days}天前）")
                except Exception as e:
                    logger.warning(f"清理AI对话历史失败: {e}")
                    stats['ai_conversations'] = 0
                
                # 清理风控日志（保留最近90天）
                try:
                    cursor.execute(
                        "DELETE FROM risk_control_logs WHERE created_at < datetime('now', '-' || ? || ' days')",
                        (days,)
                    )
                    stats['risk_control_logs'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的风控日志（{days}天前）")
                except Exception as e:
                    logger.warning(f"清理风控日志失败: {e}")
                    stats['risk_control_logs'] = 0
                
                # 清理AI商品缓存（保留最近30天）
                cache_days = min(days, 30)  # AI商品缓存最多保留30天
                try:
                    cursor.execute(
                        "DELETE FROM ai_item_cache WHERE last_updated < datetime('now', '-' || ? || ' days')",
                        (cache_days,)
                    )
                    stats['ai_item_cache'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的AI商品缓存（{cache_days}天前）")
                except Exception as e:
                    logger.warning(f"清理AI商品缓存失败: {e}")
                    stats['ai_item_cache'] = 0
                
                # 清理验证码记录（保留最近1天）
                try:
                    cursor.execute(
                        "DELETE FROM captcha_codes WHERE created_at < datetime('now', '-1 day')"
                    )
                    stats['captcha_codes'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的验证码记录")
                except Exception as e:
                    logger.warning(f"清理验证码记录失败: {e}")
                    stats['captcha_codes'] = 0
                
                # 清理邮箱验证记录（保留最近7天）
                try:
                    cursor.execute(
                        "DELETE FROM email_verifications WHERE created_at < datetime('now', '-7 days')"
                    )
                    stats['email_verifications'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的邮箱验证记录")
                except Exception as e:
                    logger.warning(f"清理邮箱验证记录失败: {e}")
                    stats['email_verifications'] = 0
                
                # 提交更改
                self.conn.commit()
                
                # 执行VACUUM以释放磁盘空间（仅当清理了大量数据时）
                total_cleaned = sum(stats.values())
                if total_cleaned > 100:
                    logger.info(f"共清理了 {total_cleaned} 条记录，执行VACUUM以释放磁盘空间...")
                    cursor.execute("VACUUM")
                    logger.info("VACUUM执行完成")
                    stats['vacuum_executed'] = True
                else:
                    stats['vacuum_executed'] = False
                
                stats['total_cleaned'] = total_cleaned
                return stats
                
        except Exception as e:
            logger.error(f"清理历史数据时出错: {e}")
            return {'error': str(e)}

    # ==================== BI报表统计函数 ====================

    def get_order_analytics(self, start_date: str = None, end_date: str = None, user_id: int = None, include_statuses: list = None):
        """get_order_analytics（已委托给 order_repo）"""
        return self.order_repo.get_order_analytics(
            start_date=start_date, end_date=end_date,
            user_id=user_id, include_statuses=include_statuses,
        )

    def update_order_address(self, order_id: str, receiver_address: str = None, receiver_city: str = None):
        """update_order_address（已委托给 order_repo）"""
        return self.order_repo.update_order_address(
            order_id=order_id, receiver_address=receiver_address, receiver_city=receiver_city,
        )

    def get_orders_for_analytics(self, start_date: str = None, end_date: str = None,
                                  user_id: int = None, include_statuses: list = None):
        """get_orders_for_analytics（已委托给 order_repo）"""
        return self.order_repo.get_orders_for_analytics(
            start_date=start_date, end_date=end_date,
            user_id=user_id, include_statuses=include_statuses,
        )


# 全局单例
db_manager = DBManager()

# 确保进程结束时关闭数据库连接
import atexit
atexit.register(db_manager.close)

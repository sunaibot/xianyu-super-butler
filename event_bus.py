"""
WebSocket 事件总线 - 实时向前端推送系统事件
支持：新订单、订单状态变更、消息接收、账号状态变更、发货完成等
支持：Webhook 外部转发（对接 n8n、企业微信、钉钉等）
"""
import asyncio
import json
import time
import hmac
import hashlib
from typing import Dict, Set, Any, Optional
from loguru import logger


class EventBus:
    """WebSocket 事件管理器 + Webhook 转发"""

    def __init__(self):
        self._connections: Dict[str, Set] = {}
        self._lock = asyncio.Lock()
        self._event_history: list = []
        self._max_history = 200
        self._webhook_cache: Optional[Dict[str, Any]] = None
        self._webhook_cache_time: float = 0
        self._http_session = None

    def _get_webhook_config(self) -> Optional[Dict[str, Any]]:
        """获取 Webhook 配置（带缓存，避免每次查库）"""
        now = time.time()
        if self._webhook_cache and (now - self._webhook_cache_time) < 5:
            return self._webhook_cache

        try:
            from db_manager import db_manager
            enabled = db_manager.get_system_setting('webhook_enabled')
            url = db_manager.get_system_setting('webhook_url')
            secret = db_manager.get_system_setting('webhook_secret')
            events_str = db_manager.get_system_setting('webhook_events') or ''

            config = {
                'enabled': enabled == 'true',
                'url': url or '',
                'secret': secret or '',
                'events': [e.strip() for e in events_str.split(',') if e.strip()] if events_str else []
            }
            self._webhook_cache = config
            self._webhook_cache_time = now
            return config
        except Exception as e:
            logger.warning(f"[EventBus] 获取 Webhook 配置失败: {e}")
            return None

    def invalidate_webhook_cache(self):
        """强制刷新 Webhook 缓存（配置更新时调用）"""
        self._webhook_cache = None
        self._webhook_cache_time = 0

    async def _forward_webhook(self, event_type: str, data: Any):
        """将事件转发到配置的 Webhook URL（带重试）"""
        config = self._get_webhook_config()
        if not config or not config.get('enabled'):
            return
        if not config.get('url'):
            return
        if config['events'] and event_type not in config['events']:
            return

        # 异步调度带重试的发送任务，不阻塞当前事件循环
        try:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(
                None,
                self._send_webhook_with_retry,
                event_type, data, config
            )
        except Exception as e:
            logger.error(f"[Webhook] 调度推送任务失败: {e}")

    def _send_webhook_with_retry(self, event_type: str, data: Any, config: Dict[str, Any]):
        """带重试的 Webhook 发送（在 executor 中执行）"""
        import urllib.request
        import urllib.error
        import hashlib
        import hmac as hmac_mod
        import time as time_mod

        max_retries = 3
        base_delay = 2  # 基础重试延迟（秒）

        payload = {
            'event_type': event_type,
            'data': data,
            'timestamp': int(time_mod.time() * 1000),
            'source': 'xianyu-auto'
        }

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'XianyuAuto-Webhook/1.0',
            'X-Event-Type': event_type,
            'X-Delivery-Timestamp': str(payload['timestamp'])
        }

        if config.get('secret'):
            secret = config['secret'].encode('utf-8')
            signature = hmac_mod.new(secret, body, hashlib.sha256).hexdigest()
            headers['X-Signature'] = f'sha256={signature}'

        url = config['url']
        timeout = 10

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = resp.status
                    if 200 <= status < 300:
                        logger.info(f"[Webhook] 事件 {event_type} 推送成功 -> {url} (尝试 {attempt}/{max_retries})")
                        return
                    else:
                        logger.warning(f"[Webhook] 事件 {event_type} 返回非2xx状态: {status} (尝试 {attempt}/{max_retries})")
            except urllib.error.HTTPError as e:
                # 4xx 客户端错误不重试（除了 429 限流）
                if 400 <= e.code < 500 and e.code != 429:
                    logger.error(f"[Webhook] 事件 {event_type} 推送失败: HTTP {e.code} (客户端错误，不重试) - {url}")
                    return
                logger.error(f"[Webhook] 事件 {event_type} 推送失败: HTTP {e.code} (尝试 {attempt}/{max_retries}) - {url}")
            except urllib.error.URLError as e:
                logger.error(f"[Webhook] 事件 {event_type} 网络错误: {e.reason} (尝试 {attempt}/{max_retries}) - {url}")
            except Exception as e:
                logger.error(f"[Webhook] 事件 {event_type} 推送异常: {e} (尝试 {attempt}/{max_retries})")

            # 还有重试机会，则等待后重试
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))  # 2, 4, 8 秒指数退避
                logger.info(f"[Webhook] {delay}秒后重试 ({attempt + 1}/{max_retries})...")
                time_mod.sleep(delay)

        logger.error(f"[Webhook] 事件 {event_type} 推送最终失败，已重试 {max_retries} 次 - {url}")

    async def connect(self, user_id: str, websocket):
        """注册新的 WebSocket 连接"""
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        logger.info(f"[EventBus] 用户 {user_id} 已连接，当前连接数: {self._get_total_connections()}")

        await self._send_snapshot(websocket)

    async def disconnect(self, user_id: str, websocket):
        """断开 WebSocket 连接"""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.info(f"[EventBus] 用户 {user_id} 已断开，当前连接数: {self._get_total_connections()}")

    def _get_total_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())

    async def broadcast(self, event_type: str, data: Any = None, user_id: Optional[str] = None):
        """
        广播事件到前端 + 转发到 Webhook

        Args:
            event_type: 事件类型 (如 'new_order', 'order_updated', 'message_received')
            data: 事件数据
            user_id: 如果指定，只推送给该用户；否则推送给所有用户
        """
        event = {
            'type': event_type,
            'data': data,
            'timestamp': int(time.time() * 1000)
        }

        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        async with self._lock:
            if user_id:
                targets = {user_id: self._connections.get(user_id, set())}
            else:
                targets = dict(self._connections)

        disconnected = []
        for uid, connections in targets.items():
            for ws in connections:
                try:
                    await ws.send_json(event)
                except Exception:
                    disconnected.append((uid, ws))

        for uid, ws in disconnected:
            await self.disconnect(uid, ws)

        if disconnected:
            logger.debug(f"[EventBus] 清理了 {len(disconnected)} 个失效连接")

        await self._forward_webhook(event_type, data)

    async def _send_snapshot(self, websocket):
        """发送最近事件历史给新连接的客户端"""
        if self._event_history:
            try:
                await websocket.send_json({
                    'type': 'snapshot',
                    'data': self._event_history[-50:],
                    'timestamp': int(time.time() * 1000)
                })
            except Exception:
                pass

    async def broadcast_to_user(self, user_id: str, event_type: str, data: Any = None):
        """向特定用户推送事件"""
        await self.broadcast(event_type, data, user_id)

    def get_connection_count(self) -> int:
        return self._get_total_connections()


# 全局事件总线实例
event_bus = EventBus()

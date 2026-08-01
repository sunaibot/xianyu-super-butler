"""
routers/rate_limit.py
=====================
共享速率限制器。

从 reply_server.py 抽取，供 reply_server.py 与 routers/* 共用，
避免循环导入。

设计：
- RateLimiter：每 IP 滑动窗口实现，进程内单例
- rate_limiter：模块级单例，全应用共享
- make_rate_limiter(...)：FastAPI 依赖工厂，参数化限流配置

约束（项目硬性要求）：
- 关键接口（登录、注册、验证码、Webhook 测试、改密）必须实现限流
- 默认拒绝时返回 429
"""
import time
import threading
from collections import defaultdict, deque
from typing import Dict

from fastapi import HTTPException, Request
from loguru import logger


class RateLimiter:
    """每 IP 滑动窗口速率限制器"""

    def __init__(self):
        self._windows: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """检查是否允许请求；返回 True 表示允许，False 表示被限流"""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            window = self._windows[key]
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= max_requests:
                return False
            window.append(now)
            return True

    def cleanup(self):
        """清理过期的窗口数据，防止内存泄露"""
        now = time.time()
        with self._lock:
            expired_keys = [k for k, w in self._windows.items() if not w or w[-1] < now - 3600]
            for k in expired_keys:
                del self._windows[k]


# 全应用共享的速率限制单例
rate_limiter = RateLimiter()


def make_rate_limiter(max_requests: int, window_seconds: int, key_prefix: str):
    """生成速率限制依赖工厂"""
    def dependency(request: Request) -> bool:
        client_ip = 'unknown'
        if request.client:
            client_ip = request.client.host
        # 代理后取真实 IP
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            client_ip = forwarded.split(',')[0].strip()

        limit_key = f"{key_prefix}:{client_ip}"
        if not rate_limiter.check(limit_key, max_requests, window_seconds):
            logger.warning(f"速率限制触发: {client_ip} - {key_prefix} (限流: {max_requests}/{window_seconds}s)")
            raise HTTPException(status_code=429, detail=f'请求过于频繁，请{window_seconds}秒后重试')
        return True
    return dependency


__all__ = ["RateLimiter", "rate_limiter", "make_rate_limiter"]

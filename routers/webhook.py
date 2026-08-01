"""
routers/webhook.py
============================
Webhook 测试路由。

从 reply_server.py 迁移而来：
- POST /webhook/test   测试 Webhook 连接（含 SSRF 防护 + HMAC-SHA256 签名 + 限流）

设计原则：
- SSRF 防护：禁止内网 IP、保留地址、裸 IP、本地/内网域名、云元数据端点
- 签名：secret 非空时附 X-Signature: sha256=... 头
- 限流：每 IP 60s 内最多 5 次测试（复用 routers/rate_limit 共享单例）
- 标准化请求体：event_type / data / timestamp / source / test
"""
import hashlib
import hmac as hmac_mod
import ipaddress
import json
import socket
import time as time_mod
import urllib.error
import urllib.request
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from .deps import require_auth
from .rate_limit import make_rate_limiter

router = APIRouter(tags=["webhook"])

# 每 IP 60s 内最多 5 次（与 reply_server.py 原配置一致）
_webhook_test_rate_limit = make_rate_limiter(
    max_requests=5, window_seconds=60, key_prefix='webhook_test'
)

# 禁止的本地/内网域名（与 reply_server.py 原实现一致）
_BLOCKED_HOSTS = {
    'localhost', 'ip6-localhost', 'ip6-loopback', 'metadata.google.internal',
}
_BLOCKED_SUFFIXES = ('.local', '.internal', '.localhost', '.cluster.local', '.svc')


def _validate_webhook_url(url: str) -> None:
    """校验 Webhook URL，防止 SSRF 攻击"""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail='无效的 URL 格式')

    if parsed.scheme not in ('http', 'https'):
        raise HTTPException(status_code=400, detail='仅支持 http/https 协议')
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail='URL 缺少主机名')

    hostname = parsed.hostname.lower()

    # 禁止裸 IP 访问（防止直接访问内网 IP）
    try:
        ipaddress.ip_address(hostname)
        raise HTTPException(status_code=400, detail='禁止使用 IP 地址访问')
    except ValueError:
        pass

    # 禁止 localhost / 内网域名
    if hostname in _BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail='禁止访问本地/内网地址')

    # 禁止常见内网域名后缀
    for suffix in _BLOCKED_SUFFIXES:
        if hostname.endswith(suffix):
            raise HTTPException(status_code=400, detail='禁止访问内网域名')

    # 解析 DNS 并检查 IP 是否为内网地址
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    raise HTTPException(status_code=400, detail='禁止访问内网/保留地址')
            except ValueError:
                continue
    except socket.gaierror:
        raise HTTPException(status_code=400, detail='域名解析失败')


@router.post('/webhook/test')
async def test_webhook(
    test_data: Dict[str, Any],
    _: Dict[str, Any] = Depends(require_auth),
    __: bool = Depends(_webhook_test_rate_limit),
):
    """测试 Webhook 连接（含 SSRF 防护、HMAC-SHA256 签名、限流）"""
    url = test_data.get('url', '')
    secret = test_data.get('secret', '')
    event_type = test_data.get('event_type', 'test_event')

    if not url:
        raise HTTPException(status_code=400, detail='Webhook URL 不能为空')

    # SSRF 防护：校验目标 URL
    _validate_webhook_url(url)

    payload = {
        'event_type': event_type,
        'data': test_data.get('data', {'message': 'Webhook 测试消息', 'test': True}),
        'timestamp': int(time_mod.time() * 1000),
        'source': 'xianyu-auto',
        'test': True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'XianyuAuto-Webhook-Test/1.0',
        'X-Event-Type': event_type,
        'X-Delivery-Timestamp': str(payload['timestamp']),
    }
    if secret:
        secret_bytes = secret.encode('utf-8')
        signature = hmac_mod.new(secret_bytes, body, hashlib.sha256).hexdigest()
        headers['X-Signature'] = f'sha256={signature}'

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            resp_body = resp.read().decode('utf-8', errors='replace')[:500]
            return {
                'success': 200 <= status < 300,
                'status_code': status,
                'response': resp_body,
            }
    except urllib.error.HTTPError as e:
        body_text = ''
        try:
            body_text = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            pass
        return {
            'success': False,
            'status_code': e.code,
            'response': body_text or f'HTTP {e.code}',
        }
    except urllib.error.URLError:
        raise HTTPException(status_code=400, detail='连接失败，请检查 URL 或网络')
    except Exception as e:
        logger.error(f"Webhook 测试失败: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail='测试失败，请稍后重试')

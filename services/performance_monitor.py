#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控服务 - 记录统计回复耗时

设计原则：
- 线程安全（所有读写加锁）
- 原子写（tmp + rename 防止断电损坏）
- 单实例模式（模块级单例，避免双实例问题）
- 统一返回结构（get_today_stats / get_summary / get_recent 返回 dict）
"""

import json
import logging
import os
import tempfile
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ServiceBase

logger = logging.getLogger(__name__)


def _get_default_data_dir() -> Path:
    """获取默认数据目录（基于项目根目录，避免相对路径问题）"""
    # reply_server.py / ai_reply_engine.py 都在项目根目录
    # services/ 是子目录，所以向上两层是项目根
    return Path(__file__).resolve().parent.parent / "data"


class PerformanceMonitor(ServiceBase):
    """性能监控服务（线程安全单例）"""

    name: str = "performance_monitor"
    display_name: str = "性能监控"
    description: str = "记录与统计回复耗时，支持按日聚合与 provider 对比"
    version: str = "1.0.0"

    _instance: Optional["PerformanceMonitor"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式：确保全局只有一个实例，避免双实例数据不一致"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, data_dir: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.data_dir = Path(data_dir) if data_dir else _get_default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.data_dir / "performance_metrics.json"

        # 线程锁：保护所有内存数据读写
        self._lock = threading.RLock()

        # 当前进行中的计时
        self._current_operation: Optional[Dict] = None

        # 历史记录（最多保留 1000 条）
        self._metrics: List[Dict] = []

        # 按日聚合统计
        self._daily_stats: Dict[str, Dict] = defaultdict(lambda: {
            'total_replies': 0,
            'ai_replies': 0,
            'kb_matches': 0,
            'total_time': 0.0,
            'total_ai_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
        })

        self._load_metrics()
        logger.info(f"PerformanceMonitor 初始化完成，加载 {len(self._metrics)} 条历史记录")

    # ===== ServiceBase 接口 =====

    def startup(self) -> None:
        """初始化已在 __init__ 完成，启动无需额外操作"""
        pass

    def health(self) -> Dict[str, Any]:
        return {
            **super().health(),
            "metrics_count": len(self._metrics),
            "metrics_file": str(self.metrics_file),
        }

    def call(self, action: str, payload: Dict[str, Any] = None) -> Any:
        payload = payload or {}
        if action == "get_today_stats":
            return self.get_today_stats()
        if action == "get_summary":
            return self.get_summary()
        if action == "get_recent":
            return self.get_recent(payload.get("limit", 10))
        if action == "get_provider_comparison":
            return self.get_provider_comparison()
        if action == "stats":
            # 聚合返回性能监控全量统计（供 /api/services/performance-stats 使用）
            return {
                "today": self.get_today_stats(),
                "summary": self.get_summary(),
                "recent": self.get_recent(payload.get("limit", 10)),
                "provider_comparison": self.get_provider_comparison(),
            }
        if action == "reset":
            return self.reset()
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

    # ===== 持久化 =====

    def _load_metrics(self):
        """从文件加载历史指标"""
        with self._lock:
            if not self.metrics_file.exists():
                return
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._metrics = data.get('metrics', [])[-1000:]
                self._rebuild_daily_stats()
            except Exception as e:
                logger.warning(f"加载性能指标失败: {e}，将备份原文件后重建")
                # 备份损坏的文件，避免后续覆盖丢失
                backup = self.metrics_file.with_suffix('.json.bak')
                try:
                    self.metrics_file.rename(backup)
                    logger.warning(f"已备份损坏的指标文件到: {backup}")
                except Exception:
                    pass
                self._metrics = []
                self._daily_stats.clear()

    def _save_metrics(self):
        """原子写入指标文件（tmp + rename，防断电损坏）"""
        with self._lock:
            try:
                data = {
                    'metrics': self._metrics[-1000:],
                    'updated_at': datetime.now().isoformat()
                }
                # 先写到临时文件，再原子重命名
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(self.data_dir),
                    prefix='.perf_',
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    # Windows 下 rename 会失败如果目标存在，用 replace
                    os.replace(tmp_path, self.metrics_file)
                except Exception:
                    # 清理临时文件
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            except Exception as e:
                logger.error(f"保存性能指标失败: {e}")

    def _rebuild_daily_stats(self):
        """从历史记录重建日统计"""
        self._daily_stats.clear()
        for metric in self._metrics:
            day = metric.get('timestamp', '')[:10]
            if not day:
                continue
            self._update_daily_stats(
                day,
                metric.get('total_reply_time', 0),
                metric.get('ai_generation_time', 0),
                metric.get('intent'),
                metric.get('provider'),
            )

    def _update_daily_stats(self, day: str, total_time: float, ai_time: float,
                            intent: Optional[str] = None,
                            provider: Optional[str] = None):
        """更新单日统计"""
        stats = self._daily_stats[day]
        stats['total_replies'] += 1
        stats['total_time'] += total_time
        stats['total_ai_time'] += ai_time
        stats['min_time'] = min(stats['min_time'], total_time)
        stats['max_time'] = max(stats['max_time'], total_time)

        # 按来源分类统计
        if provider and provider not in ('knowledge_base', 'bargain_limit', 'error', ''):
            stats['ai_replies'] += 1
        if provider == 'knowledge_base':
            stats['kb_matches'] += 1

    # ===== 计时接口（由 ai_reply_engine 调用）=====

    def start_reply_timer(self, contact_name: str, message: str):
        """开始回复计时"""
        with self._lock:
            self._current_operation = {
                'start_time': time.time(),
                'contact_name': contact_name,
                'message': message,
                'message_length': len(message),
                'ai_start_time': None,
                'ai_end_time': None,
            }

    def mark_ai_start(self):
        """标记 AI 调用开始"""
        with self._lock:
            if self._current_operation:
                self._current_operation['ai_start_time'] = time.time()

    def mark_ai_end(self):
        """标记 AI 调用结束"""
        with self._lock:
            if self._current_operation:
                self._current_operation['ai_end_time'] = time.time()

    def end_reply_timer(self, reply: str, intent: Optional[str] = None,
                        provider: Optional[str] = None) -> Optional[Dict]:
        """结束回复计时并记录指标"""
        with self._lock:
            if not self._current_operation:
                return None

            end_time = time.time()
            op = self._current_operation

            total_time = end_time - op['start_time']
            ai_time = 0.0
            if op.get('ai_start_time') and op.get('ai_end_time'):
                ai_time = op['ai_end_time'] - op['ai_start_time']

            metric = {
                'timestamp': datetime.now().isoformat(),
                'contact_name': op['contact_name'],
                'message_length': op['message_length'],
                'reply_length': len(reply) if reply else 0,
                'ai_generation_time': round(ai_time, 3),
                'total_reply_time': round(total_time, 3),
                'intent': intent,
                'provider': provider,
            }

            self._metrics.append(metric)
            # 仅保留最近 1000 条
            if len(self._metrics) > 1000:
                self._metrics = self._metrics[-1000:]

            self._update_daily_stats(
                date.today().isoformat(), total_time, ai_time, intent, provider
            )
            self._current_operation = None

            # 释放锁后再保存（保存内部会重新获取锁）
            save_needed = True

        if save_needed:
            self._save_metrics()
            logger.info(f"回复耗时: {total_time:.2f}s (AI: {ai_time:.2f}s) intent={intent}")

        return metric

    # ===== 查询接口（由 API 路由调用）=====

    def get_today_stats(self) -> Dict:
        """获取今日统计（统一返回结构）"""
        with self._lock:
            today = date.today().isoformat()
            stats = self._daily_stats.get(today, {})

            if not stats or stats.get('total_replies', 0) == 0:
                return {
                    'total_replies': 0,
                    'ai_replies': 0,
                    'kb_matches': 0,
                    'avg_response_time': 0.0,
                    'avg_ai_time': 0.0,
                    'min_response_time': 0.0,
                    'max_response_time': 0.0,
                }

            total = stats['total_replies']
            return {
                'total_replies': total,
                'ai_replies': stats.get('ai_replies', 0),
                'kb_matches': stats.get('kb_matches', 0),
                'avg_response_time': round(stats['total_time'] / total, 2),
                'avg_ai_time': round(stats.get('total_ai_time', 0) / total, 2),
                'min_response_time': round(stats['min_time'], 2) if stats['min_time'] != float('inf') else 0.0,
                'max_response_time': round(stats['max_time'], 2),
            }

    def get_summary(self) -> Dict:
        """获取历史汇总（统一返回 dict 而非字符串）"""
        with self._lock:
            if not self._metrics:
                return {
                    'total_replies': 0,
                    'ai_replies': 0,
                    'kb_matches': 0,
                    'avg_response_time': 0.0,
                    'min_response_time': 0.0,
                    'max_response_time': 0.0,
                }

            total = len(self._metrics)
            total_time = sum(m.get('total_reply_time', 0) for m in self._metrics)
            ai_count = sum(
                1 for m in self._metrics
                if m.get('provider') and m['provider'] not in ('knowledge_base', 'bargain_limit', 'error', '')
            )
            kb_count = sum(1 for m in self._metrics if m.get('provider') == 'knowledge_base')
            times = [m.get('total_reply_time', 0) for m in self._metrics]

            return {
                'total_replies': total,
                'ai_replies': ai_count,
                'kb_matches': kb_count,
                'avg_response_time': round(total_time / total, 2) if total > 0 else 0.0,
                'min_response_time': round(min(times), 2) if times else 0.0,
                'max_response_time': round(max(times), 2) if times else 0.0,
            }

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """获取最近的回复记录（倒序，最新在前）"""
        with self._lock:
            recent = self._metrics[-limit:][::-1]
            return [
                {
                    'timestamp': m.get('timestamp', ''),
                    'intent': m.get('intent') or '-',
                    'source': self._classify_source(m.get('provider')),
                    'response_time': m.get('total_reply_time', 0),
                }
                for m in recent
            ]

    @staticmethod
    def _classify_source(provider: Optional[str]) -> str:
        """将 provider 分类为前端可读的来源标签"""
        if not provider:
            return 'system'
        if provider == 'knowledge_base':
            return 'kb'
        if provider in ('bargain_limit', 'error', ''):
            return 'system'
        return 'ai'

    def get_provider_comparison(self) -> Dict[str, Dict]:
        """获取各 provider 的对比数据"""
        with self._lock:
            provider_stats = defaultdict(lambda: {'count': 0, 'total_time': 0.0})
            for metric in self._metrics:
                p = metric.get('provider')
                if p:
                    provider_stats[p]['count'] += 1
                    provider_stats[p]['total_time'] += metric.get('ai_generation_time', 0)

            return {
                p: {
                    'count': s['count'],
                    'avg_time': round(s['total_time'] / s['count'], 3) if s['count'] > 0 else 0
                }
                for p, s in provider_stats.items()
            }

    def reset(self) -> bool:
        """清空所有历史数据（用于 API reset）"""
        with self._lock:
            self._metrics.clear()
            self._daily_stats.clear()
            self._current_operation = None

        # 删除数据文件
        try:
            if self.metrics_file.exists():
                self.metrics_file.unlink()
            logger.info("性能监控数据已重置")
            return True
        except Exception as e:
            logger.error(f"重置性能监控数据失败: {e}")
            return False


# ===== 模块级单例工厂 =====

def get_performance_monitor() -> PerformanceMonitor:
    """获取全局唯一的 PerformanceMonitor 实例"""
    return PerformanceMonitor()


# 模块级单例，供 registry 注册及外部复用
performance_monitor = get_performance_monitor()

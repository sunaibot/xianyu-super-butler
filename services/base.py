"""
services/base.py
================
服务插件抽象基类。

所有 services/ 下的服务插件应继承 ServiceBase，并通过 registry 注册。
启动时统一调用 startup()，关闭时 shutdown()，
/api/plugins 路由通过 registry 动态发现。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ServiceBase(ABC):
    """服务插件抽象基类"""

    # 插件元信息（子类覆盖）
    name: str = "base"
    display_name: str = "基础服务"
    description: str = ""
    version: str = "1.0.0"

    @abstractmethod
    def startup(self) -> None:
        """服务启动时调用（初始化资源、连接等）"""
        ...

    def shutdown(self) -> None:
        """服务关闭时调用（释放资源），默认空实现"""
        pass

    def health(self) -> Dict[str, Any]:
        """健康检查，返回状态信息"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "healthy": True,
        }

    def call(self, action: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        """通用动作调用入口（子类按需覆盖）

        Args:
            action: 动作名（如 'check'、'reset'、'extract'）
            payload: 动作参数
        Returns:
            动作执行结果
        """
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

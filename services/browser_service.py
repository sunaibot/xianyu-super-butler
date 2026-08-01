"""
浏览器服务适配器
为 product_extractor / product_publisher 提供统一的浏览器实例

DrissionPage 需要独立的 Chrome/Chromium 可执行文件。
在 Docker 中仅安装了 Playwright 的 Chromium（/ms-playwright/），
此处自动检测并复用，避免商品提取功能因找不到浏览器而瘫痪。
"""
import glob
import logging
import os
from typing import Any, Dict, Optional

from .base import ServiceBase

logger = logging.getLogger(__name__)


def _find_chromium_executable() -> Optional[str]:
    """自动检测 Chromium/Chrome 可执行文件路径。

    检测顺序：
    1. 环境变量 CHROME_PATH / CHROMIUM_PATH（用户显式指定）
    2. Docker 环境：PLAYWRIGHT_BROWSERS_PATH 下的 chromium
    3. 常见系统默认安装路径（Windows/macOS/Linux）
    4. 返回 None，交由 DrissionPage 自行探测
    """
    # 1. 用户显式指定
    for env_key in ("CHROME_PATH", "CHROMIUM_PATH"):
        path = os.environ.get(env_key)
        if path and os.path.isfile(path):
            logger.info(f"使用环境变量 {env_key} 指定的浏览器: {path}")
            return path

    # 2. Docker 环境：复用 Playwright 安装的 Chromium
    playwright_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")
    if os.path.isdir(playwright_path):
        # Playwright 不同版本可能使用 chrome-linux 或 chrome-linux64 目录
        candidates = sorted(
            glob.glob(os.path.join(playwright_path, "chromium-*", "chrome-linux", "chrome"))
            + glob.glob(os.path.join(playwright_path, "chromium-*", "chrome-linux64", "chrome"))
        )
        if candidates:
            logger.info(f"检测到 Playwright Chromium: {candidates[-1]}")
            return candidates[-1]

    # 3. 常见系统默认路径
    default_paths = []
    if os.name == "nt":  # Windows
        default_paths.extend([
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ])
    elif os.uname().sysname == "Darwin":  # macOS
        default_paths.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:  # Linux
        default_paths.extend([
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ])

    for path in default_paths:
        if path and os.path.isfile(path):
            logger.info(f"检测到系统 Chrome: {path}")
            return path

    logger.warning("未找到 Chrome/Chromium 可执行文件，交由 DrissionPage 自行探测")
    return None


class SimpleBrowserService(ServiceBase):
    """轻量浏览器服务 - 按需创建 DrissionPage 浏览器"""

    name: str = "browser_service"
    display_name: str = "浏览器服务"
    description: str = "为商品提取/发布提供统一的 DrissionPage 浏览器实例"
    version: str = "1.0.0"

    def __init__(self):
        self._browser = None
        self._page = None

    def startup(self) -> None:
        """浏览器按需初始化（首次 get_page 时创建），启动无需操作"""
        pass

    def shutdown(self) -> None:
        """关闭时释放浏览器实例"""
        self.close()

    def health(self) -> Dict[str, Any]:
        return {
            **super().health(),
            "browser_initialized": self._page is not None,
        }

    def call(self, action: str, payload: Dict[str, Any] = None) -> Any:
        if action == "get_page":
            return self.get_page()
        if action == "close":
            self.close()
            return {"closed": True}
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

    def get_page(self):
        if self._page is None:
            self._init_browser()
        return self._page

    def _init_browser(self):
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions

            browser_path = _find_chromium_executable()
            co = ChromiumOptions()
            if browser_path:
                co.set_browser_path(browser_path)
            # 无头模式（Docker 无显示环境）
            if os.environ.get("DOCKER_ENV") == "true" or not os.environ.get("DISPLAY"):
                co.headless(True)
            # 自动适配 Docker 内的 --no-sandbox（非 root 运行无需 sandbox）
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-dev-shm-usage")

            self._page = ChromiumPage(co)
            logger.info("DrissionPage 浏览器初始化成功")
        except ImportError:
            logger.error("DrissionPage 未安装，请执行 pip install DrissionPage")
            raise
        except Exception as e:
            logger.error(f"DrissionPage 浏览器初始化失败: {e}")
            raise

    def close(self):
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass
            self._page = None
            self._browser = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


_browser_service: Optional[SimpleBrowserService] = None


def get_browser_service() -> SimpleBrowserService:
    global _browser_service
    if _browser_service is None:
        _browser_service = SimpleBrowserService()
    return _browser_service


# 模块级单例，供 registry 注册及外部复用
browser_service = get_browser_service()

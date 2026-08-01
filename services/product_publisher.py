#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品发布服务
使用 DrissionPage 的 tag/css/text 选择器将 ProductInfo 发布到闲鱼。
"""

import time
import random
import logging
import os
from typing import Any, Dict, List, Optional

from services.product_models import ProductInfo
from services.browser_service import get_browser_service
from .base import ServiceBase

logger = logging.getLogger(__name__)


class ProductPublisher(ServiceBase):
    name: str = "product_publisher"
    display_name: str = "商品发布"
    description: str = "使用 DrissionPage 将商品信息发布到闲鱼"
    version: str = "1.0.0"

    PUBLISH_URL = "https://www.goofish.com/publish"

    ALLOWED_CATEGORIES = [
        "其他技能服务",
        "市场调研服务",
        "软件/程序/网站开发",
        "其它互联网/软硬件相关服务",
        "其他服务",
    ]

    def __init__(self, browser_service, config: dict):
        self.browser = browser_service
        self.config = config

    def startup(self) -> None:
        """浏览器按需初始化，启动无需额外操作"""
        pass

    def health(self) -> Dict[str, Any]:
        return {
            **super().health(),
            "has_browser": self.browser is not None,
        }

    def call(self, action: str, payload: Dict[str, Any] = None) -> Any:
        payload = payload or {}
        if action == "publish":
            from services.product_models import ProductInfo
            product = payload.get("product")
            if isinstance(product, ProductInfo):
                return self.publish_product(product, payload.get("dry_run", False))
            raise ValueError("payload.product 必须是 ProductInfo 实例")
        if action == "navigate":
            return self.navigate_to_publish()
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

    def _get_page(self):
        return self.browser.get_page()

    def _random_delay(self, min_s: float = 0.5, max_s: float = 1.5) -> None:
        delay = random.uniform(min_s, max_s)
        time.sleep(delay)

    def navigate_to_publish(self) -> bool:
        page = self._get_page()
        logger.info(f"导航到发布页: {self.PUBLISH_URL}")
        page.get(self.PUBLISH_URL)
        time.sleep(3)
        success = "publish" in page.url
        if success:
            logger.info("发布页加载成功")
        else:
            logger.warning(f"发布页跳转异常，当前 URL: {page.url}")
        return success

    def upload_images(self, image_paths: List[str]) -> bool:
        page = self._get_page()
        logger.info(f"尝试上传 {len(image_paths)} 张图片")

        file_input = page.ele('css:input[type="file"]', timeout=5)
        if not file_input:
            logger.debug('未找到 file input，尝试点击"添加首图"按钮')
            add_btn = page.ele("text:添加首图", timeout=3)
            if add_btn:
                add_btn.click()
                time.sleep(1)
                file_input = page.ele('css:input[type="file"]', timeout=3)

        if not file_input:
            logger.error("找不到文件上传 input 元素")
            return False

        valid = [p for p in image_paths if p and os.path.isfile(p)][:9]
        if not valid:
            logger.error(f"没有有效的本地图片文件，原始路径列表: {image_paths}")
            return False

        logger.info(f"上传有效图片 {len(valid)} 张: {valid}")
        file_input.input(valid)
        time.sleep(3)
        logger.info("图片上传完成，等待渲染")
        return True

    def fill_description(self, description: str) -> bool:
        page = self._get_page()
        logger.info(f"填写描述，长度 {len(description)} 字符")

        desc_input = page.ele('css:div[contenteditable="true"]', timeout=3)
        if not desc_input:
            logger.debug("未找到 contenteditable div，尝试 textarea")
            desc_input = page.ele("tag:textarea", timeout=2)

        if not desc_input:
            logger.debug('尝试通过"宝贝描述"标签定位描述框')
            label = page.ele("text:宝贝描述", timeout=2)
            if label:
                parent = label.parent()
                if parent:
                    desc_input = parent.ele("css:div[contenteditable]", timeout=1)
                    if not desc_input:
                        next_sibling = parent.next()
                        if next_sibling:
                            desc_input = next_sibling.ele(
                                "css:div[contenteditable]", timeout=1
                            )

        if not desc_input:
            logger.error("找不到描述输入区域")
            return False

        desc_input.clear()
        desc_input.input(description)
        logger.info("描述填写完成")
        return True

    def fill_price(self, price: float, original_price: float = 0) -> bool:
        page = self._get_page()
        logger.info(f"填写价格: {price}，原价: {original_price}")

        price_label = page.ele("text:价格", timeout=2)
        if price_label:
            for level in range(1, 5):
                parent = price_label.parent(level)
                if not parent:
                    continue
                inputs = parent.eles("tag:input", timeout=1)
                if inputs:
                    inputs[0].clear()
                    inputs[0].input(str(price))
                    logger.info(f"价格已填写: {price}")
                    if len(inputs) > 1 and original_price > 0:
                        inputs[1].clear()
                        inputs[1].input(str(original_price))
                        logger.info(f"原价已填写: {original_price}")
                    return True

        if original_price > 0:
            orig_label = page.ele("text:原价", timeout=2)
            if orig_label:
                for level in range(1, 5):
                    parent = orig_label.parent(level)
                    if not parent:
                        continue
                    inputs = parent.eles("tag:input", timeout=1)
                    if inputs:
                        inputs[0].clear()
                        inputs[0].input(str(original_price))
                        logger.info(f"原价（回退路径）已填写: {original_price}")
                        break

        logger.warning("通过标签未找到价格 input，价格可能未填写")
        return False

    def select_shipping(self, method: str = "包邮") -> bool:
        page = self._get_page()
        logger.info(f"选择发货方式: {method}")
        ship_option = page.ele(f"text:{method}", timeout=2)
        if ship_option:
            ship_option.click()
            logger.info(f"已选择发货方式: {method}")
            return True
        logger.warning(f"未找到发货方式选项: {method}")
        return False

    def submit_publish(self, dry_run: bool = False) -> bool:
        page = self._get_page()
        logger.info("查找发布按钮")
        btn = page.ele("text:发布", timeout=3)
        if not btn:
            logger.error('找不到"发布"按钮')
            return False
        if dry_run:
            logger.info("[DRY RUN] 跳过点击发布按钮")
            return True
        logger.info("点击发布按钮")
        btn.click()
        time.sleep(3)
        logger.info("发布请求已提交")
        return True

    def publish_product(self, product: ProductInfo, dry_run: bool = False) -> bool:
        logger.info(f"开始发布商品，标题: {product.title!r}，dry_run={dry_run}")
        try:
            if not self.navigate_to_publish():
                logger.error("无法打开发布页，终止")
                return False
            self._random_delay(1, 2)

            if product.local_images:
                if not self.upload_images(product.local_images):
                    logger.error("图片上传失败，终止发布")
                    return False
                self._random_delay(2, 3)
            else:
                logger.warning("商品没有本地图片，跳过上传步骤")

            if product.description:
                if not self.fill_description(product.description):
                    logger.warning("描述填写失败，继续后续步骤")
                self._random_delay(1, 2)

            price = product.current_price or product.price
            if price > 0:
                if not self.fill_price(price, product.original_price):
                    logger.warning("价格填写失败，继续后续步骤")
                self._random_delay(0.5, 1)

            shipping = product.shipping or "包邮"
            self.select_shipping(shipping)
            self._random_delay(0.5, 1)

            result = self.submit_publish(dry_run=dry_run)
            if result:
                logger.info(f"商品发布成功: {product.title!r}")
            else:
                logger.error(f"商品发布失败: {product.title!r}")
            return result

        except Exception as e:
            logger.error(f"发布过程中出现异常: {e}", exc_info=True)
            return False


# 模块级单例，供 registry 注册及外部复用
product_publisher = ProductPublisher(get_browser_service(), config={})

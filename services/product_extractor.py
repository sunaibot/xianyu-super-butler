#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞品信息提取模块 (DrissionPage)

使用 2026-03-30 验证过的 DOM 选择器。
"""

import logging
import os
import re
import time
import random
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from services.product_models import ProductInfo
from services.browser_service import get_browser_service
from .base import ServiceBase

logger = logging.getLogger(__name__)


class ProductExtractor(ServiceBase):
    """竞品信息提取器 (DrissionPage)"""

    name: str = "product_extractor"
    display_name: str = "商品信息提取"
    description: str = "从闲鱼商品页提取标题/价格/描述/图片等结构化信息"
    version: str = "1.0.0"

    DEFAULT_IMAGE_DIR = "temp_images"
    REQUEST_TIMEOUT = 10

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
        if action == "search":
            return self.search_products(
                payload.get("keyword", ""),
                payload.get("max_results", 30),
            )
        if action == "extract":
            return self.extract_product_info(payload.get("product_url", ""))
        if action == "download_images":
            return self.download_images(
                payload.get("image_urls", []),
                payload.get("save_dir"),
            )
        raise NotImplementedError(f"服务 {self.name} 不支持动作: {action}")

    def _get_page(self):
        return self.browser.get_page()

    @staticmethod
    def _random_delay(min_s: float = 1.0, max_s: float = 2.5) -> None:
        time.sleep(random.uniform(min_s, max_s))

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        match = re.search(r'[¥￥]\s*(\d+\.?\d*)', text)
        if match:
            return float(match.group(1))
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            return float(match.group(1))
        return None

    def search_products(self, keyword: str, max_results: int = 30) -> List[str]:
        page = self._get_page()
        product_urls: List[str] = []

        try:
            encoded = urllib.parse.quote(keyword)
            search_url = f"https://www.goofish.com/search?q={encoded}"
            logger.info(f"搜索关键词: {keyword}，URL: {search_url}")

            page.get(search_url)
            self._random_delay(2.5, 4.0)

            links = page.eles('tag:a', timeout=5)
            seen_ids: set = set()

            for link in links:
                href = link.attr('href') or ''
                if '/item?' not in href:
                    continue

                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = 'https://www.goofish.com' + href

                id_match = re.search(r'[?&]id=(\d+)', href)
                if not id_match:
                    continue
                item_id = id_match.group(1)
                if item_id in seen_ids:
                    continue

                seen_ids.add(item_id)
                canonical_url = f"https://www.goofish.com/item?id={item_id}"
                product_urls.append(canonical_url)

                if len(product_urls) >= max_results:
                    break

            logger.info(f"共提取 {len(product_urls)} 个有效商品 URL")
            return product_urls

        except Exception as exc:
            logger.error(f"搜索商品失败: {exc}")
            return []

    def extract_product_info(self, product_url: str) -> Optional[ProductInfo]:
        page = self._get_page()

        try:
            logger.info(f"访问商品页: {product_url}")
            page.get(product_url)
            self._random_delay(2.0, 3.5)

            product = ProductInfo(source_url=product_url)

            product.title = self._extract_title(page)
            logger.info(f"标题: {product.title!r}")

            self._extract_price(page, product)
            logger.info(
                f"价格: current={product.current_price}, original={product.original_price}, "
                f"has_xiaodao={product.has_xiaodao}"
            )

            product.description = self._extract_description(page)
            logger.info(f"描述长度: {len(product.description)} 字符")

            product.image_urls = self._extract_images(page)
            logger.info(f"图片数: {len(product.image_urls)}")

            self._extract_metrics(page, product)
            logger.info(
                f"想要数: {product.want_count}，浏览量: {product.browse_count}"
            )

            product.source_shipping = self._extract_shipping(page)
            logger.info(f"发货: {product.source_shipping!r}")

            self._extract_attributes(page, product)
            logger.info(
                f"工期: {product.duration!r}，售后: {product.after_sales!r}"
            )

            product.price = product.current_price or product.original_price
            return product

        except Exception as exc:
            logger.error(f"提取商品信息失败 ({product_url}): {exc}", exc_info=True)
            return None

    def _extract_title(self, page) -> str:
        try:
            raw_title: str = page.run_js('return document.title') or ''
            title = re.sub(r'[_\-－–—]\s*闲鱼.*$', '', raw_title).strip()
            if title:
                return title
        except Exception as exc:
            logger.warning(f"JS 获取标题失败: {exc}")

        try:
            h1 = page.ele('tag:h1', timeout=2)
            if h1:
                return h1.text.strip()
        except Exception:
            pass

        return ''

    def _extract_price(self, page, product: ProductInfo) -> None:
        try:
            xiaodao_text: str = page.run_js(
                """
                var els = document.querySelectorAll('*');
                for (var i = 0; i < els.length; i++) {
                    var t = els[i].textContent || '';
                    if (t.indexOf('小刀价') !== -1 && /[¥￥]/.test(t)) {
                        return t;
                    }
                }
                return null;
                """
            )
        except Exception:
            xiaodao_text = None

        if xiaodao_text:
            price = self._parse_price(xiaodao_text)
            if price is not None:
                product.current_price = price
                product.has_xiaodao = True

                try:
                    direct_text: str = page.run_js(
                        """
                        var els = document.querySelectorAll('*');
                        for (var i = 0; i < els.length; i++) {
                            var t = (els[i].textContent || '').trim();
                            if (t.indexOf('直接买') !== -1 && /[¥￥]/.test(t)
                                && els[i].children.length === 0 && t.length < 30) {
                                return t;
                            }
                        }
                        return null;
                        """
                    )
                except Exception:
                    direct_text = None

                if direct_text:
                    orig = self._parse_price(direct_text)
                    if orig is not None:
                        product.original_price = orig
                return

        try:
            price_wrap = page.ele('css:[class*="price-wrap"]', timeout=3)
            if price_wrap:
                price_text = price_wrap.text.strip()
                price = self._parse_price(price_text)
                if price is not None:
                    product.current_price = price
                    return
        except Exception as exc:
            logger.warning(f"price-wrap 提取失败: {exc}")

        try:
            fallback_text: str = page.run_js(
                "var els = document.querySelectorAll('*');"
                "for (var i = 0; i < els.length; i++) {"
                "    var t = (els[i].textContent || '').trim();"
                "    if (/^[¥￥]\\s*\\d+/.test(t)) {"
                "        return t;"
                "    }"
                "}"
                "return null;"
            )
            if fallback_text:
                price = self._parse_price(fallback_text)
                if price is not None:
                    product.current_price = price
        except Exception as exc:
            logger.warning(f"JS 兜底价格提取失败: {exc}")

    def _extract_description(self, page) -> str:
        try:
            expand_btn = page.ele('text:展开', timeout=2)
            if expand_btn:
                expand_btn.click()
                self._random_delay(0.5, 1.0)
        except Exception:
            pass

        try:
            desc_elem = page.ele('css:[class*="desc"]', timeout=3)
            if desc_elem:
                text = desc_elem.text.strip()
                if text:
                    return text
        except Exception as exc:
            logger.warning(f"desc 选择器提取失败: {exc}")

        try:
            desc_elems = page.eles('css:[class*="desc"]', timeout=3)
            if desc_elems:
                texts = [e.text.strip() for e in desc_elems if e.text.strip()]
                if texts:
                    return max(texts, key=len)
        except Exception as exc:
            logger.warning(f"多 desc 元素提取失败: {exc}")

        return ''

    def _extract_images(self, page) -> List[str]:
        image_urls: List[str] = []

        try:
            page.run_js('window.scrollBy(0, 400)')
            self._random_delay(0.8, 1.5)

            slider_imgs = page.eles('css:[class*="slider"] img', timeout=4)

            seen: set = set()
            for img in slider_imgs:
                src = img.attr('src') or img.attr('data-src') or ''
                if not src:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                if 'alicdn.com' not in src:
                    continue
                if src in seen:
                    continue
                seen.add(src)
                image_urls.append(src)

        except Exception as exc:
            logger.warning(f"slider 图片提取失败: {exc}")

        if not image_urls:
            try:
                js_urls: list = page.run_js(
                    """
                    var imgs = document.querySelectorAll('img');
                    var result = [];
                    var seen = {};
                    for (var i = 0; i < imgs.length; i++) {
                        var src = imgs[i].src || imgs[i].getAttribute('data-src') || '';
                        if (src.indexOf('alicdn.com') === -1) continue;
                        if (imgs[i].naturalWidth <= 200) continue;
                        if (seen[src]) continue;
                        seen[src] = true;
                        result.push(src);
                    }
                    return result;
                    """
                ) or []
                for url in js_urls:
                    if isinstance(url, str) and url not in image_urls:
                        image_urls.append(url)
            except Exception as exc:
                logger.warning(f"JS 兜底图片提取失败: {exc}")

        return image_urls

    def _extract_metrics(self, page, product: ProductInfo) -> None:
        try:
            metrics_text: str = page.run_js(
                """
                var want = 0, browse = 0;
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].children.length > 0) continue;
                    var t = all[i].textContent.trim();
                    if (!t) continue;
                    var m1 = t.match(/^(\\d+)人想要$/);
                    if (m1) want = parseInt(m1[1]);
                    var m2 = t.match(/^(\\d+)浏览$/);
                    if (m2) browse = parseInt(m2[1]);
                }
                return JSON.stringify({want: want, browse: browse});
                """
            ) or '{}'
            import json
            data = json.loads(metrics_text)
            product.want_count = int(data.get('want', 0))
            product.browse_count = int(data.get('browse', 0))

            if product.want_count or product.browse_count:
                return

        except Exception as exc:
            logger.warning(f"JS 提取指标失败: {exc}")

        try:
            body_text: str = page.run_js('return document.body.innerText') or ''
            want_match = re.search(r'(\d+)\s*人想要', body_text)
            if want_match:
                product.want_count = int(want_match.group(1))
            browse_match = re.search(r'(\d+)\s*浏览', body_text)
            if browse_match:
                product.browse_count = int(browse_match.group(1))
        except Exception as exc:
            logger.warning(f"正则兜底指标提取失败: {exc}")

    def _extract_shipping(self, page) -> str:
        try:
            elem = page.ele('text:包邮', timeout=2)
            if elem:
                return '包邮'
        except Exception:
            pass
        return ''

    def _extract_attributes(self, page, product: ProductInfo) -> None:
        attr_map = {
            '预计工期：': 'duration',
            '售后服务：': 'after_sales',
            '计价方式：': 'pricing_method',
        }

        try:
            attrs_json: str = page.run_js(
                r"""
                var prefixes = ['预计工期：', '售后服务：', '计价方式：', '数据库系统：'];
                var result = {};
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].children.length > 0) continue;
                    var t = (all[i].textContent || '').trim();
                    for (var j = 0; j < prefixes.length; j++) {
                        if (t.startsWith(prefixes[j]) && t.length < 60) {
                            if (!result[prefixes[j]]) {
                                result[prefixes[j]] = t.replace(prefixes[j], '').trim();
                            }
                        }
                    }
                }
                return JSON.stringify(result);
                """
            ) or '{}'
            import json
            attrs = json.loads(attrs_json)
        except Exception as exc:
            logger.warning(f"属性提取失败: {exc}")
            return

        for prefix, field_name in attr_map.items():
            value = attrs.get(prefix, '')
            if value:
                setattr(product, field_name, value)

    def download_images(
        self, image_urls: List[str], save_dir: str = None
    ) -> List[str]:
        if not save_dir:
            save_dir = self.config.get('image_save_dir', self.DEFAULT_IMAGE_DIR)

        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"图片保存目录: {save_path.resolve()}")

        local_paths: List[str] = []

        for idx, url in enumerate(image_urls):
            try:
                local_path = self._download_single_image(url, save_path, idx)
                if local_path:
                    local_paths.append(local_path)
            except Exception as exc:
                logger.warning(f"下载图片失败 ({url[:60]}...): {exc}")

        logger.info(f"成功下载 {len(local_paths)}/{len(image_urls)} 张图片")
        return local_paths

    def _download_single_image(
        self, url: str, save_dir: Path, index: int
    ) -> Optional[str]:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://www.goofish.com/',
        }

        resp = requests.get(url, headers=headers, timeout=self.REQUEST_TIMEOUT)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        raw_ext = self._guess_extension(url, content_type)

        if raw_ext in ('.avif', '.webp'):
            local_path = self._save_as_jpg(resp.content, save_dir, index, raw_ext)
        else:
            ext = raw_ext or '.jpg'
            filename = f"img_{index:03d}{ext}"
            local_path = str(save_dir / filename)
            with open(local_path, 'wb') as fp:
                fp.write(resp.content)

        logger.debug(f"已下载: {local_path}")
        return local_path

    @staticmethod
    def _guess_extension(url: str, content_type: str) -> str:
        ext_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/avif': '.avif',
        }
        for mime, ext in ext_map.items():
            if mime in content_type.lower():
                return ext
        path = urllib.parse.urlparse(url).path
        _, suffix = os.path.splitext(path)
        return suffix.lower() if suffix else '.jpg'

    @staticmethod
    def _save_as_jpg(
        raw_bytes: bytes, save_dir: Path, index: int, original_ext: str
    ) -> str:
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
            filename = f"img_{index:03d}.jpg"
            local_path = str(save_dir / filename)
            img.save(local_path, 'JPEG', quality=90)
            logger.debug(f"已转换 {original_ext} → jpg: {local_path}")
            return local_path

        except ImportError:
            logger.warning("Pillow 未安装，无法转换 avif/webp，以原格式保存。")
        except Exception as exc:
            logger.warning(f"avif/webp 转换失败: {exc}")

        filename = f"img_{index:03d}{original_ext}"
        local_path = str(save_dir / filename)
        with open(local_path, 'wb') as fp:
            fp.write(raw_bytes)
        return local_path


# 模块级单例，供 registry 注册及外部复用
product_extractor = ProductExtractor(get_browser_service(), config={})

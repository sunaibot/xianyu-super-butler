"""
商品数据模型
从 XY-Agent 提取，扩充了价格区分和更多业务字段。
"""

from dataclasses import dataclass, asdict, field
from typing import List


@dataclass
class ProductInfo:
    """商品信息数据类"""
    source_url: str = ""
    title: str = ""
    description: str = ""
    price: float = 0.0
    current_price: float = 0.0
    original_price: float = 0.0
    has_xiaodao: bool = False
    image_urls: List[str] = field(default_factory=list)
    local_images: List[str] = field(default_factory=list)
    category: str = "其他技能服务"
    pricing_method: str = "元/次"
    location: str = ""
    shipping: str = "包邮"
    source_shipping: str = ""
    source_category: str = ""
    want_count: int = 0
    exposure_count: int = 0
    want_exposure_ratio: float = 0.0
    browse_count: int = 0
    duration: str = ""
    after_sales: str = ""
    forbidden_words_found: List[str] = field(default_factory=list)
    is_dedup: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompetitorProductData:
    """对标商品完整数据"""
    url: str = ""
    title: str = ""
    description: str = ""
    image_urls: List[str] = field(default_factory=list)
    category: str = ""
    estimated_duration: str = ""
    pricing_method: str = ""
    price: float = 0.0
    current_price: float = 0.0
    original_price: float = 0.0
    has_xiaodao: bool = False
    location: str = ""
    want_count: int = 0
    exposure_count: int = 0
    browse_count: int = 0
    duration: str = ""
    after_sales: str = ""
    forbidden_words_found: List[str] = field(default_factory=list)
    is_dedup: bool = False
    extracted_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

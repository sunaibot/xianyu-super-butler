"""
图形验证码生成器

从 db_manager.generate_captcha 迁出，DBManager 不应承担 PIL 绘图职责。
"""
import base64
import io
import random
import string

from loguru import logger

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def generate_verification_code() -> str:
    """生成 6 位数字验证码"""
    return ''.join(random.choices(string.digits, k=6))


def generate_captcha() -> tuple:
    """生成图形验证码

    返回: (验证码文本, base64编码的图片 data URI)
    若 PIL 不可用则降级为纯数字验证码（图片为空字符串）。
    """
    if not _PIL_AVAILABLE:
        # 无 PIL 环境降级
        simple_code = ''.join(random.choices(string.digits, k=4))
        return simple_code, ""

    try:
        # 生成 4 位随机验证码（数字+字母）
        chars = string.ascii_uppercase + string.digits
        captcha_text = ''.join(random.choices(chars, k=4))

        # 创建图片
        width, height = 120, 40
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        # 尝试使用系统字体，失败则用默认字体
        font = None
        for font_path in ("arial.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                font = ImageFont.truetype(font_path, 20)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        # 绘制验证码文本
        for i, char in enumerate(captcha_text):
            color = (
                random.randint(0, 100),
                random.randint(0, 100),
                random.randint(0, 100),
            )
            x = 20 + i * 20 + random.randint(-3, 3)
            y = 8 + random.randint(-3, 3)
            draw.text((x, y), char, font=font, fill=color)

        # 干扰线
        for _ in range(3):
            start = (random.randint(0, width), random.randint(0, height))
            end = (random.randint(0, width), random.randint(0, height))
            draw.line(
                [start, end],
                fill=(
                    random.randint(100, 200),
                    random.randint(100, 200),
                    random.randint(100, 200),
                ),
                width=1,
            )

        # 干扰点
        for _ in range(20):
            x = random.randint(0, width)
            y = random.randint(0, height)
            draw.point(
                (x, y),
                fill=(
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                ),
            )

        # 转 base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        return captcha_text, f"data:image/png;base64,{img_base64}"

    except Exception as e:
        logger.error(f"生成图形验证码失败: {e}")
        simple_code = ''.join(random.choices(string.digits, k=4))
        return simple_code, ""

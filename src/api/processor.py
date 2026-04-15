"""
이미지 처리 — 카페24 상품 이미지 규격 변환

카페24 권장 사이즈 (정방형):
  detail_image : 1000x1000  (상품 상세 대표 이미지)
  list_image   :  400x400   (상품 목록 이미지)
  small_image  :  200x200   (장바구니/소형 이미지)
  tiny_image   :   80x80    (미니 섬네일)

처리 방식:
  1. 중앙 기준 정방형 크롭 (긴 변 기준으로 단변 중앙에서 자름)
  2. 각 타입별 목표 사이즈로 LANCZOS 리샘플링
  3. JPEG base64 인코딩 (quality=90)
"""

import base64
import io
from pathlib import Path

from PIL import Image

# 카페24 이미지 타입별 목표 사이즈 (px)
IMAGE_SIZES: dict[str, tuple[int, int]] = {
    "detail_image": (1000, 1000),
    "list_image": (400, 400),
    "small_image": (200, 200),
    "tiny_image": (80, 80),
}


def _center_crop_square(img: Image.Image) -> Image.Image:
    """이미지를 중앙 기준 정방형으로 크롭."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _to_base64_jpeg(img: Image.Image, quality: int = 90) -> str:
    """PIL Image → data:image/jpeg;base64,... 문자열 반환."""
    buf = io.BytesIO()
    # RGBA/P 모드는 JPEG 저장 불가 → RGB 변환
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    encoded = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def process_body_image(image_path: Path, width: int = 860) -> str:
    """
    본문용 이미지를 860px 고정 폭으로 리사이징 (비율 유지, 크롭 없음).

    Returns:
        "data:image/jpeg;base64,..." 문자열
    """
    with Image.open(image_path) as img:
        img.load()
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        orig_w, orig_h = img.size
        if orig_w > width:
            new_h = int(orig_h * width / orig_w)
            img = img.resize((width, new_h), Image.LANCZOS)
        return _to_base64_jpeg(img, quality=85)


def process_product_images(image_path: Path) -> dict[str, str]:
    """
    원본 이미지를 카페24 4종 규격으로 변환하여 반환.

    Returns:
        {
            "detail_image": "data:image/jpeg;base64,...",
            "list_image":   "data:image/jpeg;base64,...",
            "small_image":  "data:image/jpeg;base64,...",
            "tiny_image":   "data:image/jpeg;base64,...",
        }
    """
    with Image.open(image_path) as img:
        img.load()  # 지연 로딩 강제 해제 (파일 핸들 안전 종료용)
        cropped = _center_crop_square(img.copy())

    result: dict[str, str] = {}
    for image_type, (w, h) in IMAGE_SIZES.items():
        resized = cropped.resize((w, h), Image.LANCZOS)
        result[image_type] = _to_base64_jpeg(resized)

    return result

"""
Claude Vision으로 상품 이미지 분석

이미지를 받아 카페24 상품 등록에 필요한 정보를 자동 생성합니다.
"""

import base64
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """당신은 패션 쇼핑몰 상품 등록 전문가입니다.
상품 이미지를 보고 카페24 쇼핑몰에 등록할 정보를 JSON으로 반환하세요.

반드시 아래 JSON 형식만 반환하세요 (다른 텍스트 없이):
{
  "product_name": "상품명 (예: [큐빅세트] 펄 비즈 슬림 투피스)",
  "supply_product_name": "공급사 상품명 (product_name과 동일하게)",
  "simple_description": "한 줄 요약 (30자 이내)",
  "description": "상세 설명 HTML (소재, 핏, 스타일링 팁 포함, 200자 이상)",
  "price": "판매가 (숫자만, 원화 기준 예: 89000)",
  "supply_price": "공급가 (판매가의 50% 수준)",
  "product_tag": "검색 태그 (쉼표 구분, 예: 투피스,세트,여름,데일리)",
  "sizes": ["FREE", "S", "M", "L"] 중 해당하는 것만 배열로
}"""


def analyze_image(image_path: Path) -> dict:
    """이미지 파일을 분석해 상품 정보 dict 반환"""
    img_bytes = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    media_type = media_type_map.get(suffix, "image/jpeg")

    b64 = base64.standard_b64encode(img_bytes).decode()

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": "이 상품 이미지를 분석해서 카페24 상품 정보를 생성해주세요."},
                ],
            }
        ],
    )

    import json, re
    raw = message.content[0].text.strip()
    # 마크다운 코드블록 제거
    raw = re.sub(r"```(?:json)?\n?", "", raw).strip().rstrip("`").strip()
    # JSON 블록만 추출 (앞뒤 텍스트 있을 경우 대비)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"Claude 응답에서 JSON을 찾을 수 없습니다.\n응답 내용: {raw[:200]}")
    return json.loads(match.group(0))

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


BODY_SYSTEM_PROMPT = """당신은 여성 패션 쇼핑몰의 카피라이터입니다.
상품 본문 이미지들을 보고, 각 이미지에 어울리는 한국어 패션 카피 텍스트를 작성하세요.

아래 형식과 톤앤매너를 반드시 따르세요:

[이미지 1 텍스트 스타일]
- 상품 전체를 소개하는 오프너 문장으로 시작 (1~2줄)
- 이어서 핵심 특징 3가지를 짧은 문단으로 (각 1~2줄)
- 이모지 적극 활용 (✨ 🌙 😊 💫 🤍 등)
- 예시:
  "✨ 이번 시즌 가장 사랑받을 아이템을 소개해요.

  🌙 부드러운 소재감이 피부에 닿는 느낌까지 고려했어요.
  하루종일 입어도 편안한 착용감을 자랑합니다.

  😊 어떤 하의와도 자연스럽게 어울리는 실루엣.
  데일리부터 특별한 날까지, 어디서든 빛나는 아이템이에요."

[이미지 2 텍스트 스타일]
- 실루엣과 핏에 집중하는 2~3줄 텍스트
- 착용했을 때의 느낌과 보여지는 모습 묘사
- 예시:
  "적당한 루즈핏으로 체형에 상관없이 누구나 잘 어울려요.
  떨어지는 라인이 자연스럽게 날씬해 보이는 효과까지."

[이미지 3 텍스트 스타일]
- 디테일, 소재, 봉제 등 제품 퀄리티 부각 (3줄)
- 소재감이나 마감 처리 언급
- 이모지 1~2개 포함
- 예시:
  "✨ 세심하게 마감된 솔기 처리로 오래 입어도 변형 없어요.
  부드러운 텍스처가 고급스러운 느낌을 더해줍니다.
  🤍 세탁 후에도 형태가 유지되는 고품질 원단을 사용했어요."

[이미지 4 텍스트 스타일]
- 스타일링 활용도와 착용 상황 제안 (2~3줄)
- 다양한 코디법이나 계절 활용법 언급
- 마무리 이모지 1개
- 예시:
  "캐주얼 스니커즈부터 힐까지, 어떤 신발과도 잘 어울려요.
  출근룩은 물론 주말 나들이까지 폭넓게 활용 가능한 아이템 💫"

반드시 아래 JSON 형식만 반환하세요 (다른 텍스트 없이):
{
  "texts": [
    "이미지1 카피 텍스트 (\\n으로 줄바꿈)",
    "이미지2 카피 텍스트",
    "이미지3 카피 텍스트",
    "이미지4 카피 텍스트"
  ]
}

이미지가 4장 미만이면 해당 개수만큼만 texts 배열에 포함하세요."""


def analyze_body_images(image_paths: list[Path]) -> list[str]:
    """본문 이미지 1~4장을 분석해 각각에 대한 한국어 패션 카피 텍스트 반환"""
    import json, re

    content = []
    for i, path in enumerate(image_paths[:4], 1):
        img_bytes = path.read_bytes()
        suffix = path.suffix.lower()
        media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        media_type = media_type_map.get(suffix, "image/jpeg")
        b64 = base64.standard_b64encode(img_bytes).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })
        content.append({"type": "text", "text": f"[이미지 {i}]"})

    content.append({"type": "text", "text": "위 이미지들에 대한 본문 카피 텍스트를 작성해주세요."})

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=BODY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"```(?:json)?\n?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"Claude 응답에서 JSON을 찾을 수 없습니다.\n응답: {raw[:200]}")
    result = json.loads(match.group(0))
    return result.get("texts", [])


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

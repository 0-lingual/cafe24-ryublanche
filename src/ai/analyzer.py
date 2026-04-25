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

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Anthropic 클라이언트 지연 초기화 (환경변수 설정 후 최초 호출 시 생성)"""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client

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

## STEP 1 — 이미지별 디자인 포인트 추출 (내부 분석, 출력하지 않음)
전체 이미지를 통합 분석하여, 각 이미지에서 가장 눈에 띄는 시각적 특징을 1개씩 먼저 찾아라.
예: 단추 디테일 / 밑단 커팅 / 원단 비침 / 레이어드 구성 / 다른 의류와의 조합 / 착용 실루엣 / 소재 텍스처 등
이미지 번호별 역할(소개·핏·소재·스타일링)을 미리 고정하지 말고, 해당 이미지에서 실제로 보이는 것을 기반으로 판단하라.

## STEP 2 — 텍스트 작성 규칙
각 이미지에 대해 STEP 1에서 찾은 시각적 특징을 반드시 1개 이상 구체적으로 언급하며 텍스트를 작성하라.

**톤앤매너**
- 친근한 존댓말: `~에요`, `~이에요`, `~드려요` 어미 사용
- 한 문장은 2~4어절로 짧게 끊기
- 이모지는 줄 끝에만, 블록당 1~2개 이하로 절제

**분량**
- 블록당 짧은 문장 2~4쌍 (총 4~8줄)
- 문장 사이 빈 줄로 리듬감 부여

**예시 (톤앤매너 참고용)**
  "이거 하나로 분위기 완성되는\n레이어드 무드 티셔츠에요 ✨\n\n이너 + 랩 디자인이 합쳐진 느낌으로\n꾸민 듯 안 꾸민 듯 감성 제대로 🪐\n\n쇄골라인 자연스럽게 드러나서\n여리여리한 실루엣 완성 🤍"

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

    message = _get_client().messages.create(
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

    message = _get_client().messages.create(
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

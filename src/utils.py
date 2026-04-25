"""
공용 유틸리티 — FastAPI / Streamlit 양쪽에서 사용
"""

from pathlib import Path

from src.api.processor import process_body_image


def build_description_html(
    body_paths: list[Path],
    body_texts: list[str],
) -> str:
    """
    본문 HTML 생성.

    구조: 이미지1→텍스트1 → 이미지2→텍스트2 → ... → 이미지4→텍스트4
          → 이미지5 → 이미지6 → ... → 이미지N (텍스트 없음)
    이미지는 base64 data URI로 인라인 삽입.

    Args:
        body_paths: 본문 이미지 Path 목록 (최대 15장)
        body_texts: 이미지 1~4에 대응하는 텍스트 목록
    """
    parts = ['<div style="max-width:860px;margin:0 auto;text-align:center;font-family:sans-serif;">']

    for i, img_path in enumerate(body_paths):
        if not img_path.exists():
            continue

        b64 = process_body_image(img_path)
        parts.append(f'<img src="{b64}" style="width:100%;display:block;" alt="">')

        # 이미지 1~4에만 텍스트 삽입
        if i < 4 and i < len(body_texts) and body_texts[i]:
            text_html = body_texts[i].replace("\n", "<br>")
            parts.append(
                f'<div style="padding:28px 24px 32px;border-bottom:1px solid #e8e8e8;text-align:left;">'
                f'<p style="font-size:15px;line-height:1.9;color:#333;white-space:pre-line;">{text_html}</p>'
                f'</div>'
            )

    parts.append('</div>')
    return "\n".join(parts)

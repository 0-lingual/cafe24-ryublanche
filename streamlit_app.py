"""
ryublanche-ax Streamlit 어드민
Streamlit Cloud 배포용 진입점
"""

import os
import tempfile
import uuid
from pathlib import Path

import streamlit as st

# ── Secrets → os.environ (src.* 모듈 import 전에 반드시 실행) ──────────────
# 로컬: .env 파일 사용 / Streamlit Cloud: st.secrets 사용
_SECRET_KEYS = [
    "ANTHROPIC_API_KEY",
    "CAFE24_MALL_ID",
    "CAFE24_CLIENT_ID",
    "CAFE24_CLIENT_SECRET",
    "CAFE24_API_VERSION",
    "CAFE24_REDIRECT_URI",
]

try:
    for _k in _SECRET_KEYS:
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # 로컬 개발 시 .env가 처리함

# ── 모듈 import (환경변수 설정 완료 후) ──────────────────────────────────────
from src.ai.analyzer import analyze_body_images, analyze_image
from src.api.processor import process_product_images
from src.cafe24.auth import refresh_access_token
from src.cafe24.client import Cafe24Client
from src.utils import build_description_html

# ── 임시 파일 디렉토리 ─────────────────────────────────────────────────────────
UPLOAD_DIR = Path(tempfile.gettempdir()) / "ryublanche_ax"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── 토큰 관리 ──────────────────────────────────────────────────────────────────
def _get_access_token() -> str:
    """
    유효한 access_token 반환.
    - 세션에 유효한 토큰 있으면 바로 반환
    - 없으면 st.secrets에서 로드 → 만료 시 refresh_token으로 갱신
    """
    from datetime import datetime, timedelta

    # 세션에 캐싱된 토큰 확인
    if "access_token" in st.session_state and "token_expires_at" in st.session_state:
        try:
            expiry = datetime.fromisoformat(st.session_state["token_expires_at"])
            if datetime.now() < expiry - timedelta(minutes=10):
                return st.session_state["access_token"]
        except ValueError:
            pass

    # st.secrets에서 토큰 로드
    try:
        access_token = str(st.secrets["CAFE24_ACCESS_TOKEN"])
        refresh_token = str(st.secrets["CAFE24_REFRESH_TOKEN"])
        expires_at_str = str(st.secrets.get("CAFE24_TOKEN_EXPIRES_AT", ""))
    except KeyError as e:
        st.error(
            f"**토큰 설정 누락: {e}**\n\n"
            "Streamlit Cloud → App settings → Secrets에 아래 키를 추가하세요:\n"
            "- `CAFE24_ACCESS_TOKEN`\n"
            "- `CAFE24_REFRESH_TOKEN`\n"
            "- `CAFE24_TOKEN_EXPIRES_AT` (선택)"
        )
        st.stop()

    # 만료 시간 확인
    if expires_at_str:
        try:
            expiry = datetime.fromisoformat(expires_at_str)
            if datetime.now() < expiry - timedelta(minutes=10):
                st.session_state["access_token"] = access_token
                st.session_state["token_expires_at"] = expires_at_str
                return access_token
        except ValueError:
            pass

    # 토큰 갱신
    try:
        new_data = refresh_access_token(refresh_token)
        st.session_state["access_token"] = new_data["access_token"]
        st.session_state["token_expires_at"] = new_data.get("expires_at", "")
        return new_data["access_token"]
    except Exception as e:
        st.error(
            f"**토큰 갱신 실패: {e}**\n\n"
            "카페24 재인증 후 Secrets의 `CAFE24_ACCESS_TOKEN`, `CAFE24_REFRESH_TOKEN`을 업데이트하세요."
        )
        st.stop()


def get_client() -> Cafe24Client:
    return Cafe24Client(_get_access_token())


# ── 임시 파일 저장 ─────────────────────────────────────────────────────────────
def save_upload(img_bytes: bytes, original_name: str) -> Path:
    """업로드 바이트를 임시 파일로 저장 후 Path 반환"""
    suffix = Path(original_name).suffix.lower() or ".jpg"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(img_bytes)
    return path


# ── 세션 상태 초기화 ───────────────────────────────────────────────────────────
def _init():
    defaults = {
        "main_file_id": None,      # 분석한 파일의 고유 ID (재분석 방지)
        "main_img_bytes": None,    # 대표 이미지 바이트
        "main_img_name": None,     # 대표 이미지 원본 파일명
        "product_info": {},        # AI 분석 결과
        # body_slots[i]: {"bytes": bytes, "name": str, "text": str} or None
        "body_slots": [None, None, None, None],
        # body_extras[i]: {"bytes": bytes, "name": str}
        "body_extras": [],
        "categories": None,        # 카테고리 목록 캐시
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── 카테고리 로드 ──────────────────────────────────────────────────────────────
def load_categories() -> list[dict]:
    if st.session_state.categories is not None:
        return st.session_state.categories
    try:
        client = get_client()
        result = client.get("/categories", params={"display_group": 1, "limit": 100})
        cats = [c for c in result.get("categories", []) if c.get("use_display") == "T"]
        st.session_state.categories = cats
        return cats
    except Exception as e:
        st.warning(f"카테고리 로드 실패: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 앱 시작
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Ryublanche AX", page_icon="👗", layout="wide")
_init()

st.title("👗 Ryublanche AX")
st.caption("카페24 AI 상품 자동 등록 어드민")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Section 1+2: 대표 이미지 & 상품 정보
# ══════════════════════════════════════════════════════════════════════════════
col_img, col_form = st.columns([1, 1], gap="large")

with col_img:
    st.subheader("1. 대표 이미지 업로드")
    main_file = st.file_uploader(
        "이미지를 업로드하세요",
        type=["jpg", "jpeg", "png", "gif", "webp"],
        key="main_uploader",
        label_visibility="collapsed",
    )

    if main_file is not None:
        # 새 파일 업로드 시 AI 자동 분석
        if main_file.file_id != st.session_state.main_file_id:
            img_bytes = main_file.read()
            st.session_state.main_img_bytes = img_bytes
            st.session_state.main_img_name = main_file.name
            st.session_state.main_file_id = main_file.file_id

            with st.spinner("Claude가 이미지를 분석하는 중..."):
                try:
                    tmp_path = save_upload(img_bytes, main_file.name)
                    result = analyze_image(tmp_path)
                    st.session_state.product_info = result
                    # 분석 결과를 폼 키에 미리 기록 (widget 렌더 전 설정)
                    st.session_state["f_product_name"] = result.get("product_name", "")
                    st.session_state["f_simple_desc"] = result.get("simple_description", "")
                    st.session_state["f_price"] = str(result.get("price", ""))
                    st.session_state["f_supply_price"] = str(result.get("supply_price", ""))
                    st.session_state["f_tags"] = result.get("product_tag", "")
                    st.session_state["f_sizes"] = result.get("sizes", [])
                    st.success("분석 완료! 상품 정보를 확인하고 수정 후 등록하세요.")
                except Exception as e:
                    st.error(f"분석 실패: {e}")

        # 이미지 미리보기
        if st.session_state.main_img_bytes:
            st.image(st.session_state.main_img_bytes, use_container_width=True)

    if st.button("초기화", key="reset_btn"):
        for k in ["main_file_id", "main_img_bytes", "main_img_name", "product_info",
                  "f_product_name", "f_simple_desc", "f_price", "f_supply_price",
                  "f_tags", "f_sizes"]:
            st.session_state[k] = None if "bytes" in k or k == "main_file_id" else ([] if k == "f_sizes" else "")
        st.session_state.product_info = {}
        st.rerun()

with col_form:
    st.subheader("2. 상품 정보 확인 & 수정")

    product_name = st.text_input(
        "상품명",
        placeholder="AI 분석 후 자동 입력됩니다",
        key="f_product_name",
    )
    simple_desc = st.text_input(
        "한 줄 소개",
        placeholder="간단한 상품 소개",
        key="f_simple_desc",
    )

    price_col, supply_col = st.columns(2)
    with price_col:
        price = st.text_input("판매가 (원)", placeholder="89000", key="f_price")
    with supply_col:
        supply_price = st.text_input("공급가 (원)", placeholder="45000", key="f_supply_price")

    # 카테고리
    cats = load_categories()
    cat_options = {f"{'　' * ((c.get('category_depth', 1) - 1))} {c['category_name']}": c["category_no"] for c in cats}
    cat_labels = ["(카테고리 없음)"] + list(cat_options.keys())
    selected_cat_label = st.selectbox("카테고리", cat_labels, key="f_category")
    category_no = cat_options.get(selected_cat_label.strip(), 0)

    tags = st.text_input("태그 (쉼표 구분)", placeholder="투피스,세트,여름,데일리", key="f_tags")

    # 사이즈 멀티셀렉트
    size_options = ["FREE", "XS", "S", "M", "L", "XL"]
    default_sizes = st.session_state.get("f_sizes", []) or []
    valid_defaults = [s for s in default_sizes if s in size_options]
    sizes = st.multiselect("사이즈", size_options, default=valid_defaults, key="f_sizes_select")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Section 3: 본문 구성
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("3. 본문 구성")
st.caption("이미지 1~4에는 텍스트가 함께 표시됩니다. 이미지 5번부터는 이미지만 표시됩니다.")

# ── 이미지+텍스트 슬롯 (1~4) ──────────────────────────────────────────────────
for i in range(4):
    slot = st.session_state.body_slots[i]
    c_img, c_text = st.columns([1, 2], gap="medium")

    with c_img:
        body_file = st.file_uploader(
            f"이미지 {i + 1}",
            type=["jpg", "jpeg", "png", "gif", "webp"],
            key=f"body_slot_uploader_{i}",
        )
        if body_file is not None:
            b_bytes = body_file.read()
            existing = st.session_state.body_slots[i] or {}
            st.session_state.body_slots[i] = {
                "bytes": b_bytes,
                "name": body_file.name,
                "text": existing.get("text", ""),
            }
            slot = st.session_state.body_slots[i]

        if slot and slot.get("bytes"):
            st.image(slot["bytes"], use_container_width=True)

    with c_text:
        default_text = slot["text"] if slot else ""
        body_text = st.text_area(
            f"본문 텍스트 {i + 1}",
            value=default_text,
            height=180,
            placeholder="이미지 업로드 후 자동 생성됩니다. 직접 수정도 가능해요.",
            key=f"body_text_area_{i}",
        )
        # 텍스트 변경 시 세션에 반영
        if st.session_state.body_slots[i] is not None:
            st.session_state.body_slots[i]["text"] = body_text

# ── 텍스트 자동 생성 버튼 ─────────────────────────────────────────────────────
filled_slots = [s for s in st.session_state.body_slots if s and s.get("bytes")]
gen_disabled = len(filled_slots) == 0

if st.button(
    "✨ 본문 텍스트 자동 생성",
    disabled=gen_disabled,
    help="이미지 1~4를 모두 업로드하면 활성화됩니다" if gen_disabled else None,
):
    with st.spinner("Claude가 본문 텍스트를 생성하는 중... (30초 정도 소요될 수 있어요)"):
        try:
            tmp_paths = []
            for slot in filled_slots:
                tmp_paths.append(save_upload(slot["bytes"], slot["name"]))

            texts = analyze_body_images(tmp_paths)

            # 생성된 텍스트를 슬롯에 반영
            for i, text in enumerate(texts):
                if st.session_state.body_slots[i] is not None:
                    st.session_state.body_slots[i]["text"] = text

            st.success("본문 텍스트 자동 생성 완료! 내용을 확인하고 수정하세요.")
            st.rerun()
        except Exception as e:
            st.error(f"텍스트 생성 실패: {e}")

# ── 이미지 전용 슬롯 (5번~) ───────────────────────────────────────────────────
st.markdown("**이미지 전용 슬롯 (5번~)**")
extra_files = st.file_uploader(
    "추가 이미지 업로드 (최대 11장)",
    type=["jpg", "jpeg", "png", "gif", "webp"],
    accept_multiple_files=True,
    key="body_extra_uploader",
)
if extra_files:
    new_extras = [{"bytes": f.read(), "name": f.name} for f in extra_files[:11]]
    st.session_state.body_extras = new_extras

if st.session_state.body_extras:
    preview_cols = st.columns(min(len(st.session_state.body_extras), 5))
    for idx, extra in enumerate(st.session_state.body_extras):
        with preview_cols[idx % 5]:
            st.image(extra["bytes"], caption=f"이미지 {idx + 5}", use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 등록 버튼
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("4. 카페24에 등록")

register_ready = bool(
    st.session_state.main_img_bytes
    and st.session_state.get("f_product_name")
    and st.session_state.get("f_price")
)

if not register_ready:
    st.info("대표 이미지를 업로드하고 상품명·판매가를 입력하면 등록 버튼이 활성화됩니다.")

if st.button("✅ 카페24에 등록", type="primary", disabled=not register_ready):
    with st.spinner("카페24에 등록 중..."):
        try:
            client = get_client()

            # 본문 HTML 빌드
            description_html = ""
            all_body_paths: list[Path] = []
            all_body_texts: list[str] = []

            for slot in st.session_state.body_slots:
                if slot and slot.get("bytes"):
                    all_body_paths.append(save_upload(slot["bytes"], slot["name"]))
                    all_body_texts.append(slot.get("text", ""))

            for extra in st.session_state.body_extras:
                if extra.get("bytes"):
                    all_body_paths.append(save_upload(extra["bytes"], extra["name"]))

            if all_body_paths:
                description_html = build_description_html(all_body_paths, all_body_texts)

            # 상품 등록 payload
            payload: dict = {
                "product_name": st.session_state.f_product_name,
                "supply_product_name": st.session_state.f_product_name,
                "price": st.session_state.f_price,
                "supply_price": st.session_state.f_supply_price or st.session_state.f_price,
                "display": "T",
                "selling": "T",
            }
            if st.session_state.f_simple_desc:
                payload["simple_description"] = st.session_state.f_simple_desc
            if description_html:
                payload["description"] = description_html
            if tags:
                payload["product_tag"] = [t.strip() for t in tags.split(",") if t.strip()]
            if sizes:
                payload["has_option"] = "T"
                payload["option_type"] = "S"
                payload["option_list_type"] = "S"
                payload["options"] = [{"name": "사이즈", "value": sizes}]

            result = client.create_product(payload)
            product = result.get("product", {})
            product_no = product.get("product_no")

            # 카테고리 할당
            if category_no and product_no:
                try:
                    client.post(f"/categories/{category_no}/products", {
                        "request": {"product_no": [product_no]}
                    })
                except Exception as ce:
                    st.warning(f"카테고리 할당 실패: {ce}")

            # 대표 이미지 업로드
            image_uploaded = False
            if st.session_state.main_img_bytes and product_no:
                try:
                    tmp_main = save_upload(
                        st.session_state.main_img_bytes,
                        st.session_state.main_img_name or "main.jpg"
                    )
                    images = process_product_images(tmp_main)
                    img_result = client.post(f"/products/{product_no}/images", {
                        "request": {"image_upload_type": "B", **images}
                    })
                    image_uploaded = any(
                        img_result.get("image", {}).get(k)
                        for k in ("detail_image", "list_image", "tiny_image", "small_image")
                    )
                except Exception as ie:
                    st.warning(f"이미지 업로드 실패: {ie}")

            mall_id = os.getenv("CAFE24_MALL_ID", "ryublanche")
            shop_url = f"https://{mall_id}.cafe24.com/product/detail.html?product_no={product_no}"

            st.success(
                f"**상품 등록 완료!** No.{product_no} — 코드: {product.get('product_code')}\n\n"
                f"{'✅ 이미지 자동 등록 완료' if image_uploaded else '⚠️ 이미지 자동 등록 실패'}"
            )
            st.link_button("쇼핑몰에서 보기 →", shop_url)

            # 카테고리 캐시 무효화하여 상품목록 새로고침
            if "categories" in st.session_state:
                del st.session_state["categories"]

        except Exception as e:
            st.error(f"등록 실패: {e}")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 등록된 상품 목록
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("📦 등록된 상품 목록", expanded=False):
    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("새로고침", key="refresh_products"):
            st.session_state["product_list_cache"] = None

    try:
        if "product_list_cache" not in st.session_state or st.session_state.product_list_cache is None:
            client = get_client()
            result = client.get_products(limit=12)
            st.session_state.product_list_cache = result.get("products", [])

        products = st.session_state.product_list_cache or []

        if not products:
            st.info("등록된 상품이 없습니다.")
        else:
            cols = st.columns(4)
            for idx, p in enumerate(products):
                with cols[idx % 4]:
                    if p.get("detail_image"):
                        st.image(p["detail_image"], use_container_width=True)
                    st.caption(f"**{p.get('product_name', '-')}**")
                    st.caption(f"{int(p.get('price', 0)):,}원 · No.{p.get('product_no')}")
    except Exception as e:
        st.error(f"상품 목록 로드 실패: {e}")

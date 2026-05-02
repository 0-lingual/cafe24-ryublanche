"""
ryublanche-ax Streamlit 어드민
Streamlit Cloud 배포용 진입점
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

import requests as _http
import streamlit as st

# ── 페이지 설정 (반드시 최상단) ────────────────────────────────────────────────
st.set_page_config(page_title="Ryublanche AX", page_icon="👗", layout="wide")

# ── Secrets → os.environ (src.* 모듈 import 전에 반드시 실행) ──────────────
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


# ── Secrets 사전 검사 (UI 렌더 전) ────────────────────────────────────────────
def _check_secrets() -> bool:
    """필수 Secrets 확인. 누락 시 설정 안내 화면 표시 후 False 반환."""
    required = [
        "CAFE24_ACCESS_TOKEN",
        "CAFE24_REFRESH_TOKEN",
        "ANTHROPIC_API_KEY",
        "CAFE24_MALL_ID",
        "CAFE24_CLIENT_ID",
        "CAFE24_CLIENT_SECRET",
    ]
    missing = []
    try:
        for k in required:
            if k not in st.secrets:
                missing.append(k)
    except Exception:
        missing = required

    if missing:
        st.title("👗 Ryublanche AX")
        st.error("**⚙️ Streamlit Secrets 설정이 필요합니다**")
        st.markdown(
            "Streamlit Cloud 상단 메뉴 **Manage app → Settings → Secrets** 에 아래 내용을 붙여넣으세요."
        )
        st.code(
            "\n".join(f'{k} = "..."' for k in missing),
            language="toml",
        )
        st.info(
            "`.streamlit/secrets.toml.example` 파일을 참고하거나, "
            "로컬의 `.streamlit/secrets.toml` 내용을 그대로 붙여넣으면 됩니다."
        )
        return False
    return True


if not _check_secrets():
    st.stop()  # ← 최상단에서만 stop (컬럼 내부에서 호출 안 함)

# ── 모듈 import (Secrets 검증 + 환경변수 설정 완료 후) ───────────────────────
from src.ai.analyzer import analyze_body_images, analyze_image  # noqa: E402
from src.api.processor import process_extra_image, process_product_images  # noqa: E402
from src.cafe24.auth import refresh_access_token  # noqa: E402
from src.cafe24.client import Cafe24Client  # noqa: E402
from src.utils import build_description_html  # noqa: E402

# ── 임시 파일 디렉토리 ─────────────────────────────────────────────────────────
UPLOAD_DIR = Path(tempfile.gettempdir()) / "ryublanche_ax"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── 토큰 관리 ──────────────────────────────────────────────────────────────────
# Gist 영구 저장: 앱 재시작 후에도 rotate된 최신 refresh_token 유지
# GITHUB_TOKEN + GITHUB_GIST_ID가 secrets에 있을 때만 활성화 (없으면 기존 secrets 방식)

def _load_from_gist() -> dict | None:
    try:
        gist_id = str(st.secrets.get("GITHUB_GIST_ID", ""))
        gh_token = str(st.secrets.get("GITHUB_TOKEN", ""))
        if not gist_id or not gh_token:
            return None
        resp = _http.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {gh_token}",
                     "Accept": "application/vnd.github.v3+json"},
            timeout=5,
        )
        if resp.ok:
            content = resp.json().get("files", {}).get("cafe24_tokens.json", {}).get("content", "")
            if content and content.strip() != "{}":
                return json.loads(content)
    except Exception:
        pass
    return None


def _save_to_gist(data: dict) -> None:
    try:
        gist_id = str(st.secrets.get("GITHUB_GIST_ID", ""))
        gh_token = str(st.secrets.get("GITHUB_TOKEN", ""))
        if not gist_id or not gh_token:
            return
        _http.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {gh_token}",
                     "Accept": "application/vnd.github.v3+json"},
            json={"files": {"cafe24_tokens.json": {"content": json.dumps(data)}}},
            timeout=5,
        )
    except Exception:
        pass


@st.cache_resource
def _token_store() -> dict:
    """앱 인스턴스 전역 토큰 저장소. 재시작 시 Gist에서 최신 토큰 복원."""
    store = {"access_token": None, "refresh_token": None, "expires_at": None}
    gist_data = _load_from_gist()
    if gist_data:
        store.update(gist_data)
    return store


def _do_refresh() -> str:
    """
    refresh_token으로 access_token 갱신.
    Cafe24 rotate 정책: 매 refresh마다 새 refresh_token 발급.
    → 전역 캐시(_token_store)에 저장해 secrets 구버전 문제 방지.
    """
    store = _token_store()
    # 전역 캐시 → session_state → secrets 순으로 최신 refresh_token 우선 사용
    rt = (
        store.get("refresh_token")
        or st.session_state.get("refresh_token")
        or str(st.secrets["CAFE24_REFRESH_TOKEN"])
    )
    new_data = refresh_access_token(rt)
    # 전역 캐시 업데이트 (다음 세션도 최신 토큰 사용 가능)
    store["access_token"] = new_data["access_token"]
    store["expires_at"] = new_data.get("expires_at", "")
    store["refresh_token"] = new_data.get("refresh_token") or rt
    # session_state에도 동기화
    st.session_state["access_token"] = store["access_token"]
    st.session_state["token_expires_at"] = store["expires_at"]
    st.session_state["refresh_token"] = store["refresh_token"]
    # Gist에 저장 (앱 재시작 후에도 최신 rotate 토큰 사용 가능)
    _save_to_gist({
        "access_token": store["access_token"],
        "refresh_token": store["refresh_token"],
        "expires_at": store["expires_at"],
    })
    return store["access_token"]


def _get_access_token() -> str:
    """유효한 access_token 반환. 만료 시 자동 갱신."""
    from datetime import datetime, timedelta

    def _not_expired(expires_at_str: str) -> bool:
        try:
            return datetime.now() < datetime.fromisoformat(expires_at_str) - timedelta(minutes=10)
        except (ValueError, TypeError):
            return False

    # 1순위: 전역 캐시 (다른 세션이 갱신한 최신 토큰)
    store = _token_store()
    if store.get("access_token") and _not_expired(store.get("expires_at", "")):
        return store["access_token"]

    # 2순위: session_state 캐시
    if _not_expired(st.session_state.get("token_expires_at", "")):
        return st.session_state["access_token"]

    # 3순위: secrets의 access_token (만료 안됐을 때만)
    expires_at_str = str(st.secrets.get("CAFE24_TOKEN_EXPIRES_AT", ""))
    if _not_expired(expires_at_str):
        token = str(st.secrets["CAFE24_ACCESS_TOKEN"])
        store["access_token"] = token
        store["expires_at"] = expires_at_str
        # secrets의 refresh_token도 캐시 (아직 store에 없을 경우)
        if not store.get("refresh_token"):
            store["refresh_token"] = str(st.secrets.get("CAFE24_REFRESH_TOKEN", ""))
        return token

    # 모두 만료 → 갱신
    return _do_refresh()


def get_client() -> Cafe24Client:
    return Cafe24Client(_get_access_token())


def _with_retry(fn):
    """
    fn(client) → result.
    401 발생 시 전역·세션 캐시 비우고 강제 갱신 후 1회 재시도.
    """
    try:
        return fn(get_client())
    except Exception as e:
        is_401 = "401" in str(e) or (
            hasattr(e, "response") and e.response is not None and e.response.status_code == 401
        )
        if not is_401:
            raise
        # 전역 캐시 + session_state 비우고 강제 갱신
        store = _token_store()
        store["access_token"] = None
        store["expires_at"] = None
        st.session_state.pop("access_token", None)
        st.session_state.pop("token_expires_at", None)
        new_token = _do_refresh()
        return fn(Cafe24Client(new_token))


# ── 임시 파일 저장 ─────────────────────────────────────────────────────────────
def save_upload(img_bytes: bytes, original_name: str) -> Path:
    suffix = Path(original_name).suffix.lower() or ".jpg"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(img_bytes)
    return path


# ── 세션 상태 초기화 ───────────────────────────────────────────────────────────
def _init():
    defaults = {
        "main_imgs": [],           # [{bytes, name}, ...]
        "main_file_ids": [],       # 파일 ID 리스트 (변경 감지용)
        "product_info": {},
        "body_slots": [None, None, None, None],
        "body_extras": [],
        "categories": None,
        "product_list_cache": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── 카테고리 로드 ──────────────────────────────────────────────────────────────
def load_categories() -> list[dict]:
    if st.session_state.categories is not None:
        return st.session_state.categories
    try:
        result = _with_retry(
            lambda c: c.get("/categories", params={"limit": 100})  # Cafe24 max: 100
        )
        # use_display 필터 없이 전체 반환 (쇼핑몰 설정마다 값이 다름)
        cats = result.get("categories", [])
        st.session_state.categories = cats
        return cats
    except Exception as e:
        st.warning(f"카테고리 로드 실패: {e}")
        st.exception(e)
        st.session_state.categories = []
        return []


# ── 상품 수정 다이얼로그 ───────────────────────────────────────────────────────
@st.dialog("상품 수정")
def _edit_dialog(product: dict):
    product_no = product.get("product_no")
    st.caption(f"No.{product_no}")

    new_name = st.text_input("상품명", value=product.get("product_name", ""))

    try:
        cur_price = int(float(str(product.get("price") or 0)))
    except (ValueError, TypeError):
        cur_price = 0
    new_price = st.number_input("판매가 (원)", value=cur_price, step=1000, min_value=0)

    try:
        cur_supply = int(float(str(product.get("supply_price") or 0)))
    except (ValueError, TypeError):
        cur_supply = 0
    new_supply = st.number_input("공급가 (원)", value=cur_supply, step=1000, min_value=0)

    col_d, col_s = st.columns(2)
    with col_d:
        new_display = st.checkbox("진열", value=(product.get("display", "T") == "T"))
    with col_s:
        new_selling = st.checkbox("판매", value=(product.get("selling", "T") == "T"))

    if st.button("저장", type="primary"):
        try:
            _with_retry(lambda c: c.update_product(int(product_no), {
                "product_name": new_name,
                "price": str(new_price),
                "supply_price": str(new_supply),
                "display": "T" if new_display else "F",
                "selling": "T" if new_selling else "F",
            }))
            st.session_state.product_list_cache = None
            st.success("수정 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"수정 실패: {e}")
            st.exception(e)


# ── 상품 삭제 다이얼로그 ───────────────────────────────────────────────────────
@st.dialog("상품 삭제 확인")
def _delete_dialog(product: dict):
    product_no = product.get("product_no")
    st.warning(
        f"**{product.get('product_name', '')}** (No.{product_no})를 삭제하시겠습니까?\n\n"
        "삭제 후 복구가 어렵습니다."
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("삭제", type="primary"):
            try:
                _with_retry(lambda c: c.delete(f"/products/{int(product_no)}"))
                st.session_state.product_list_cache = None
                st.success("삭제 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"삭제 실패: {e}")
                st.exception(e)
    with col2:
        if st.button("취소"):
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# 앱 UI
# ══════════════════════════════════════════════════════════════════════════════
_init()

st.title("👗 Ryublanche AX")
st.caption("카페24 AI 상품 자동 등록 어드민")
st.divider()

# ── Section 1 + 2: 대표 이미지 & 상품 정보 ───────────────────────────────────
col_img, col_form = st.columns([1, 1], gap="large")

with col_img:
    st.subheader("1. 대표 이미지 업로드")
    st.caption("여러 장 선택 가능. 첫 번째가 대표 이미지, 나머지는 추가 이미지로 등록됩니다.")
    main_files = st.file_uploader(
        "이미지 업로드",
        type=["jpg", "jpeg", "png", "gif", "webp"],
        accept_multiple_files=True,
        key="main_uploader",
        label_visibility="collapsed",
    )

    if main_files:
        new_ids = [f.file_id for f in main_files]
        if new_ids != st.session_state.main_file_ids:
            st.session_state.main_file_ids = new_ids
            st.session_state.main_imgs = [{"bytes": f.read(), "name": f.name} for f in main_files]

            # AI 분석: 첫 번째 이미지만
            first = st.session_state.main_imgs[0]
            with st.spinner("Claude가 이미지를 분석하는 중..."):
                try:
                    tmp_path = save_upload(first["bytes"], first["name"])
                    result = analyze_image(tmp_path)
                    st.session_state.product_info = result
                    st.session_state["f_product_name"] = result.get("product_name", "")
                    st.session_state["f_simple_desc"] = result.get("simple_description", "")
                    st.session_state["f_price"] = str(result.get("price", ""))
                    st.session_state["f_supply_price"] = str(result.get("supply_price", ""))
                    st.session_state["f_tags"] = result.get("product_tag", "")
                    ai_sizes = [s for s in result.get("sizes", []) if s in ["FREE", "XS", "S", "M", "L", "XL"]]
                    st.session_state["f_sizes"] = ai_sizes
                    st.session_state["f_sizes_select"] = ai_sizes
                    st.success("분석 완료! 상품 정보를 확인하고 수정 후 등록하세요.")
                except Exception as e:
                    st.error(f"분석 실패: {e}")

    if st.session_state.main_imgs:
        n = min(len(st.session_state.main_imgs), 4)
        preview_cols = st.columns(n)
        for idx, img_data in enumerate(st.session_state.main_imgs):
            with preview_cols[idx % n]:
                st.image(img_data["bytes"], width="stretch")
                st.caption("대표" if idx == 0 else f"추가 {idx}")

    if st.button("초기화", key="reset_btn"):
        for k in ["main_file_ids", "main_imgs", "product_info",
                  "f_product_name", "f_simple_desc", "f_price", "f_supply_price",
                  "f_tags"]:
            if k in ("main_file_ids", "main_imgs"):
                st.session_state[k] = []
            elif k == "product_info":
                st.session_state[k] = {}
            else:
                st.session_state[k] = ""
        st.session_state["f_sizes"] = []
        st.session_state["f_sizes_select"] = []
        st.rerun()

with col_form:
    st.subheader("2. 상품 정보 확인 & 수정")

    product_name = st.text_input(
        "상품명", placeholder="AI 분석 후 자동 입력됩니다", key="f_product_name"
    )
    simple_desc = st.text_input(
        "한 줄 소개", placeholder="간단한 상품 소개", key="f_simple_desc"
    )

    pc, sc = st.columns(2)
    with pc:
        price = st.text_input("판매가 (원)", placeholder="89000", key="f_price")
    with sc:
        supply_price = st.text_input("공급가 (원)", placeholder="45000", key="f_supply_price")

    # 카테고리 — try/except 내부, 실패해도 나머지 렌더 계속
    cats = load_categories()
    cat_options = {
        f"{'　' * max(c.get('category_depth', 1) - 1, 0)} {c['category_name']}": c["category_no"]
        for c in cats
    }
    cat_labels = ["(카테고리 없음)"] + list(cat_options.keys())
    selected_cat_label = st.selectbox("카테고리", cat_labels, key="f_category")
    category_no = cat_options.get(selected_cat_label.strip(), 0)

    tags = st.text_input("태그 (쉼표 구분)", placeholder="투피스,세트,여름,데일리", key="f_tags")

    size_options = ["FREE", "XS", "S", "M", "L", "XL"]
    default_sizes = [s for s in (st.session_state.get("f_sizes") or []) if s in size_options]
    sizes = st.multiselect("사이즈", size_options, default=default_sizes, key="f_sizes_select")

st.divider()

# ── Section 3: 본문 구성 ───────────────────────────────────────────────────────
st.subheader("3. 본문 구성")
st.caption("이미지 1~4에는 텍스트가 함께 표시됩니다. 이미지 5번부터는 이미지만 표시됩니다.")

# 위젯 렌더 전에 pending 텍스트를 위젯 키로 이전
# (버튼 핸들러에서 이미 렌더된 위젯 키를 직접 수정하면 StreamlitAPIException 발생)
for _i in range(4):
    _pk = f"body_text_pending_{_i}"
    if _pk in st.session_state:
        st.session_state[f"body_text_area_{_i}"] = st.session_state.pop(_pk)

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
            st.image(slot["bytes"], width="stretch")

    with c_text:
        default_text = slot["text"] if slot else ""
        body_text = st.text_area(
            f"본문 텍스트 {i + 1}",
            value=default_text,
            height=180,
            placeholder="이미지 업로드 후 자동 생성됩니다. 직접 수정도 가능해요.",
            key=f"body_text_area_{i}",
        )
        if st.session_state.body_slots[i] is not None:
            st.session_state.body_slots[i]["text"] = body_text

# (슬롯 인덱스 보존) 채워진 슬롯의 (인덱스, 슬롯) 쌍
filled_indexed = [(i, s) for i, s in enumerate(st.session_state.body_slots) if s and s.get("bytes")]
gen_disabled = len(filled_indexed) == 0

if st.button(
    "✨ 본문 텍스트 자동 생성",
    disabled=gen_disabled,
    help="이미지를 1장 이상 업로드하면 활성화됩니다" if gen_disabled else None,
):
    with st.spinner("Claude가 본문 텍스트를 생성하는 중... (30초 정도 소요될 수 있어요)"):
        try:
            tmp_paths = [save_upload(s["bytes"], s["name"]) for _, s in filled_indexed]
            texts = analyze_body_images(tmp_paths)
            for (slot_idx, _), text in zip(filled_indexed, texts):
                st.session_state.body_slots[slot_idx]["text"] = text
                # pending 키에 저장 → rerun 후 위젯 렌더 전에 위젯 키로 이전됨
                st.session_state[f"body_text_pending_{slot_idx}"] = text
            st.success("본문 텍스트 자동 생성 완료! 내용을 확인하고 수정하세요.")
            st.rerun()
        except Exception as e:
            st.error(f"텍스트 생성 실패: {e}")
            st.exception(e)  # Streamlit Cloud가 메시지를 리댁트해도 traceback은 표시됨

st.markdown("**이미지 전용 슬롯 (5번~)**")
extra_files = st.file_uploader(
    "추가 이미지 업로드 (최대 11장)",
    type=["jpg", "jpeg", "png", "gif", "webp"],
    accept_multiple_files=True,
    key="body_extra_uploader",
)
if extra_files:
    st.session_state.body_extras = [{"bytes": f.read(), "name": f.name} for f in extra_files[:11]]

if st.session_state.body_extras:
    n = min(len(st.session_state.body_extras), 5)
    preview_cols = st.columns(n)
    for idx, extra in enumerate(st.session_state.body_extras):
        with preview_cols[idx % n]:
            st.image(extra["bytes"], caption=f"이미지 {idx + 5}", width="stretch")

st.divider()

# ── Section 4: 카페24 등록 ────────────────────────────────────────────────────
st.subheader("4. 카페24에 등록")

register_ready = bool(
    st.session_state.main_imgs
    and st.session_state.get("f_product_name")
    and st.session_state.get("f_price")
)

if not register_ready:
    st.info("대표 이미지를 업로드하고 상품명·판매가를 입력하면 등록 버튼이 활성화됩니다.")

if st.button("✅ 카페24에 등록", type="primary", disabled=not register_ready):
    with st.spinner("카페24에 등록 중..."):
        try:
            all_body_paths: list[Path] = []
            all_body_texts: list[str] = []
            for slot in st.session_state.body_slots:
                if slot and slot.get("bytes"):
                    all_body_paths.append(save_upload(slot["bytes"], slot["name"]))
                    all_body_texts.append(slot.get("text", ""))
            for extra in st.session_state.body_extras:
                if extra.get("bytes"):
                    all_body_paths.append(save_upload(extra["bytes"], extra["name"]))

            description_html = build_description_html(all_body_paths, all_body_texts) if all_body_paths else ""

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

            # 상품 등록 (401 시 자동 갱신 재시도)
            result = _with_retry(lambda c: c.create_product(payload))
            product = result.get("product", {})
            product_no = product.get("product_no")

            # 카테고리 할당
            if category_no and product_no:
                try:
                    _with_retry(lambda c: c.post(f"/categories/{category_no}/products", {
                        "request": {"product_no": [product_no]}
                    }))
                except Exception as ce:
                    st.warning(f"카테고리 할당 실패: {ce}")

            # 대표 이미지 업로드 (첫 번째 이미지)
            image_uploaded = False
            extra_uploaded = 0
            if st.session_state.main_imgs and product_no:
                first_img = st.session_state.main_imgs[0]
                try:
                    tmp_main = save_upload(first_img["bytes"], first_img["name"])
                    images = process_product_images(tmp_main)
                    img_result = _with_retry(lambda c: c.post(f"/products/{product_no}/images", {
                        "request": {"image_upload_type": "B", **images}
                    }))
                    image_uploaded = any(
                        img_result.get("image", {}).get(k)
                        for k in ("detail_image", "list_image", "tiny_image", "small_image")
                    )
                except Exception as ie:
                    st.warning(f"대표 이미지 업로드 실패: {ie}")

                # 추가 대표 이미지 (2번째 이미지부터 → additionalimages)
                for extra_img in st.session_state.main_imgs[1:]:
                    try:
                        tmp_extra = save_upload(extra_img["bytes"], extra_img["name"])
                        extra_b64 = process_extra_image(tmp_extra)
                        _with_retry(lambda c: c.post(f"/products/{product_no}/additionalimages", {
                            "request": {"image": extra_b64}
                        }))
                        extra_uploaded += 1
                    except Exception as ae:
                        st.warning(f"추가 이미지 업로드 실패: {ae}")

            mall_id = os.getenv("CAFE24_MALL_ID", "ryublanche")
            shop_url = f"https://{mall_id}.cafe24.com/product/detail.html?product_no={product_no}"

            extra_msg = f" · 추가 이미지 {extra_uploaded}장" if extra_uploaded else ""
            st.success(
                f"**상품 등록 완료!** No.{product_no} — 코드: {product.get('product_code')}\n\n"
                f"{'✅ 이미지 자동 등록 완료' if image_uploaded else '⚠️ 이미지 자동 등록 실패'}{extra_msg}"
            )
            st.link_button("쇼핑몰에서 보기 →", shop_url)
            st.session_state.product_list_cache = None  # 목록 캐시 초기화

        except Exception as e:
            st.error(f"등록 실패: {e}")
            st.exception(e)

st.divider()

# ── 등록된 상품 목록 ───────────────────────────────────────────────────────────
with st.expander("📦 등록된 상품 목록", expanded=False):
    if st.button("새로고침", key="refresh_products"):
        st.session_state.product_list_cache = None

    if st.session_state.product_list_cache is None:
        try:
            result = _with_retry(lambda c: c.get_products(limit=12))
            st.session_state.product_list_cache = result.get("products", [])
        except Exception as e:
            st.error(f"상품 목록 로드 실패: {e}")
            st.session_state.product_list_cache = []

    products = st.session_state.product_list_cache or []
    if not products:
        st.info("등록된 상품이 없습니다.")
    else:
        cols = st.columns(4)
        for idx, p in enumerate(products):
            with cols[idx % 4]:
                if p.get("detail_image"):
                    st.image(p["detail_image"], width="stretch")
                st.caption(f"**{p.get('product_name', '-')}**")
                try:
                    price_int = int(float(str(p.get("price") or 0)))
                except (ValueError, TypeError):
                    price_int = 0
                st.caption(f"{price_int:,}원 · No.{p.get('product_no')}")

                # 수정 / 삭제 버튼
                btn1, btn2 = st.columns(2)
                with btn1:
                    if st.button("✏️ 수정", key=f"edit_{p.get('product_no')}_{idx}"):
                        _edit_dialog(p)
                with btn2:
                    if st.button("🗑️ 삭제", key=f"del_{p.get('product_no')}_{idx}"):
                        _delete_dialog(p)

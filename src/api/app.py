"""
ryublanche-ax 어드민 웹 서버

이미지 업로드 → AI 분석 → 카페24 상품 등록
"""

import os
import re
import subprocess
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from src.ai.analyzer import analyze_image
from src.cafe24.client import Cafe24Client
from src.cafe24.token_manager import TokenManager

app = FastAPI(title="ryublanche-ax")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")  # 터널 시작 후 자동 설정

token_manager = TokenManager()


def get_client() -> Cafe24Client:
    return Cafe24Client(token_manager.get_token())


# ── Cloudflare Tunnel ─────────────────────────────────────────────────────────

def _start_tunnel(port: int):
    """cloudflared quick tunnel 시작 → PUBLIC_BASE_URL 자동 설정"""
    global PUBLIC_BASE_URL
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
            if match:
                PUBLIC_BASE_URL = match.group(0)
                print(f"\n[Tunnel] 공개 URL: {PUBLIC_BASE_URL}\n")
                break
    except FileNotFoundError:
        print("[Tunnel] cloudflared 미설치 — 이미지 자동 업로드 비활성화")


@app.on_event("startup")
async def startup():
    threading.Thread(target=_start_tunnel, args=(8000,), daemon=True).start()


# ── 라우트 ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    """이미지 업로드 → Claude 분석 → 상품 정보 반환"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(400, "jpg/png/gif/webp 파일만 가능합니다.")

    filename = f"{uuid.uuid4().hex}{suffix}"
    save_path = UPLOAD_DIR / filename
    save_path.write_bytes(await file.read())

    product_info = analyze_image(save_path)
    product_info["_image_filename"] = filename

    # 터널 URL이 준비됐으면 이미지 공개 URL 포함
    if PUBLIC_BASE_URL:
        product_info["_image_url"] = f"{PUBLIC_BASE_URL}/uploads/{filename}"
    return product_info


@app.get("/api/categories")
async def list_categories():
    """카페24 카테고리 목록 (쇼핑몰 노출 카테고리만)"""
    client = get_client()
    result = client.get("/categories", params={"display_group": 1, "limit": 100})
    # use_display=T 인 카테고리만 반환
    visible = [c for c in result.get("categories", []) if c.get("use_display") == "T"]
    return {"categories": visible}


class CreateProductRequest(BaseModel):
    product_name: str
    supply_product_name: str
    price: str
    supply_price: str
    simple_description: str = ""
    description: str = ""
    product_tag: str = ""
    image_filename: str = ""
    sizes: list[str] = []
    category_no: int = 0


def _upload_product_image(client: Cafe24Client, product_no: int, filename: str) -> bool:
    """상품 이미지를 base64로 직접 Cafe24에 업로드"""
    import base64
    img_path = UPLOAD_DIR / filename
    if not img_path.exists():
        return False
    ext_map = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".gif": "gif", ".webp": "webp"}
    ext = ext_map.get(img_path.suffix.lower(), "jpg")
    b64 = base64.standard_b64encode(img_path.read_bytes()).decode()
    image_data = f"data:image/{ext};base64,{b64}"
    try:
        for image_type in ("detail", "list", "tiny", "small"):
            client.post(f"/products/{product_no}/images", {
                "request": {
                    "image_upload_type": "B",
                    "image_type": image_type,
                    "image": image_data,
                }
            })
        return True
    except Exception as e:
        print(f"[경고] 이미지 업로드 실패: {e}")
        return False


@app.post("/api/products")
async def create_product(req: CreateProductRequest):
    """카페24에 상품 등록 (이미지 + 옵션 포함)"""
    client = get_client()

    payload: dict = {
        "product_name": req.product_name,
        "supply_product_name": req.supply_product_name,
        "price": req.price,
        "supply_price": req.supply_price,
        "display": "T",
        "selling": "T",
    }

    if req.simple_description:
        payload["simple_description"] = req.simple_description
    if req.description:
        payload["description"] = req.description
    if req.product_tag:
        payload["product_tag"] = [t.strip() for t in req.product_tag.split(",") if t.strip()]

    # 사이즈 옵션 — 상품 생성 시 함께 전달
    if req.sizes:
        payload["has_option"] = "T"
        payload["option_type"] = "S"
        payload["option_list_type"] = "S"
        payload["options"] = [{"name": "사이즈", "value": req.sizes}]

    result = client.create_product(payload)
    product = result.get("product", {})
    product_no = product.get("product_no")

    # 카테고리 할당 (상품 생성 후 별도 API 호출 — product_no는 배열로 전달)
    if req.category_no and product_no:
        try:
            client.post(f"/categories/{req.category_no}/products", {
                "request": {"product_no": [product_no]}
            })
        except Exception as e:
            print(f"[경고] 카테고리 할당 실패: {e}")

    # 이미지 업로드 (상품 생성 후 별도 업로드)
    image_uploaded = False
    if req.image_filename and product_no:
        image_uploaded = _upload_product_image(client, product_no, req.image_filename)

    mall_id = os.getenv("CAFE24_MALL_ID", "ryublanche")
    shop_url = f"https://{mall_id}.cafe24.com/product/detail.html?product_no={product_no}"

    return {
        "product_no": product_no,
        "product_code": product.get("product_code"),
        "message": f"상품 등록 완료 (No.{product_no})",
        "shop_url": shop_url,
        "image_uploaded": image_uploaded,
    }


@app.get("/api/products")
async def list_products(limit: int = 10, offset: int = 0):
    """등록된 상품 목록"""
    client = get_client()
    result = client.get_products(limit=limit, offset=offset)
    return result

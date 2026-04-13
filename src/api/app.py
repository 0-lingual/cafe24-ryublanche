"""
ryublanche-ax 어드민 웹 서버

이미지 업로드 → AI 분석 → 카페24 상품 등록
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from src.ai.analyzer import analyze_image
from src.cafe24.client import Cafe24Client
from src.cafe24.token_manager import TokenManager

app = FastAPI(title="ryublanche-ax")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

token_manager = TokenManager()


def get_client() -> Cafe24Client:
    return Cafe24Client(token_manager.get_token())


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
    product_info["_image_url"] = f"{PUBLIC_BASE_URL}/uploads/{filename}"
    return product_info


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


@app.post("/api/products")
async def create_product(req: CreateProductRequest):
    """카페24에 상품 등록"""
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

    result = client.create_product(payload)
    product = result.get("product", {})
    product_no = product.get("product_no")

    # 사이즈 옵션 등록
    if req.sizes and product_no:
        _add_size_options(client, product_no, req.sizes)

    mall_id = os.getenv("CAFE24_MALL_ID", "ryublanche")
    admin_url = f"https://{mall_id}.cafe24.com/disp/admin/shop1/product/ProductModify?product_no={product_no}"

    return {
        "product_no": product_no,
        "product_code": product.get("product_code"),
        "message": f"상품 등록 완료 (No.{product_no})",
        "admin_url": admin_url,
    }


def _add_size_options(client: Cafe24Client, product_no: int, sizes: list[str]):
    try:
        client.post(f"/products/{product_no}/options", {
            "request": {
                "has_option": "T",
                "option_type": "S",
                "options": [{"name": "사이즈", "value": sizes}],
            }
        })
    except Exception as e:
        print(f"[경고] 사이즈 옵션 등록 실패: {e}")


@app.get("/api/products")
async def list_products(limit: int = 10, offset: int = 0):
    """등록된 상품 목록"""
    client = get_client()
    result = client.get_products(limit=limit, offset=offset)
    return result

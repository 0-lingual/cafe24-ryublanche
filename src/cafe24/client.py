"""
Cafe24 API 클라이언트

모든 API 호출은 이 클라이언트를 통해 수행합니다.
access_token을 주입받아 인증 헤더를 자동으로 처리합니다.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

MALL_ID = os.getenv("CAFE24_MALL_ID")
API_VERSION = os.getenv("CAFE24_API_VERSION", "2024-09-01")
BASE_URL = f"https://{MALL_ID}.cafe24api.com/api/v2/admin"


class Cafe24Client:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Cafe24-Api-Version": API_VERSION,
            }
        )

    def get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: dict) -> dict:
        resp = self.session.post(f"{BASE_URL}{path}", json=body)
        if not resp.ok:
            raise ValueError(f"[{resp.status_code}] {path}\n{resp.text}")
        return resp.json()

    def put(self, path: str, body: dict) -> dict:
        resp = self.session.put(f"{BASE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json()

    def delete(self, path: str) -> dict:
        resp = self.session.delete(f"{BASE_URL}{path}")
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {}

    # ── 상품 API ──────────────────────────────────────────────────────────────

    def get_products(self, limit: int = 10, offset: int = 0) -> dict:
        """상품 목록 조회"""
        return self.get("/products", params={"limit": limit, "offset": offset})

    def create_product(self, product_data: dict) -> dict:
        """상품 등록"""
        return self.post("/products", body={"request": product_data})

    def update_product(self, product_no: int, product_data: dict) -> dict:
        """상품 수정"""
        return self.put(f"/products/{product_no}", body={"request": product_data})

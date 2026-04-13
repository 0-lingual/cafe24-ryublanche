"""
Cafe24 OAuth 2.0 인증 모듈

인증 흐름:
  1. get_authorization_url() → 브라우저에서 접속해 쇼핑몰 관리자 로그인
  2. 콜백으로 code 수신
  3. exchange_code_for_token(code) → access_token, refresh_token 획득
  4. refresh_access_token() → access_token 만료(2시간) 시 갱신
"""

import base64
import os
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

MALL_ID = os.getenv("CAFE24_MALL_ID")
CLIENT_ID = os.getenv("CAFE24_CLIENT_ID")
CLIENT_SECRET = os.getenv("CAFE24_CLIENT_SECRET")
REDIRECT_URI = os.getenv("CAFE24_REDIRECT_URI")
API_VERSION = os.getenv("CAFE24_API_VERSION", "2024-09-01")

BASE_URL = f"https://{MALL_ID}.cafe24api.com"


def get_authorization_url(scopes: list[str]) -> str:
    """OAuth 인증 URL 생성. 브라우저에서 열어 관리자 로그인 후 code를 받습니다."""
    params = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": ",".join(scopes),
    })
    return f"{BASE_URL}/api/v2/oauth/authorize?{params}"


def _basic_auth_header() -> str:
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _attach_expires_at(token_data: dict) -> dict:
    """expires_in(초) → expires_at(ISO 문자열) 계산 후 dict에 추가."""
    from datetime import datetime, timedelta
    expires_in = int(token_data.get("expires_in", 7200))
    token_data["expires_at"] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    return token_data


def exchange_code_for_token(code: str) -> dict:
    """Authorization code를 access_token / refresh_token으로 교환합니다."""
    resp = requests.post(
        f"{BASE_URL}/api/v2/oauth/token",
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    return _attach_expires_at(resp.json())


def refresh_access_token(refresh_token: str) -> dict:
    """만료된 access_token을 refresh_token으로 갱신합니다."""
    resp = requests.post(
        f"{BASE_URL}/api/v2/oauth/token",
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    resp.raise_for_status()
    return _attach_expires_at(resp.json())

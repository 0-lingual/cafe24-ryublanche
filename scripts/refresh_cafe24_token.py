"""
Cafe24 토큰 자동 갱신 스크립트 (GitHub Actions용)

GitHub Actions에서 매주 실행되어 refresh_token을 갱신하고 Gist에 저장합니다.

필요한 환경변수 (GitHub Actions secrets에 설정):
  CAFE24_MALL_ID, CAFE24_CLIENT_ID, CAFE24_CLIENT_SECRET
  CAFE24_API_VERSION (optional, default: 2024-09-01)
  GH_TOKEN         — GitHub PAT (gist scope)
  GITHUB_GIST_ID   — Private Gist ID (cafe24_tokens.json 포함)
"""

import base64
import json
import os
import sys

import requests

MALL_ID = os.environ["CAFE24_MALL_ID"]
CLIENT_ID = os.environ["CAFE24_CLIENT_ID"]
CLIENT_SECRET = os.environ["CAFE24_CLIENT_SECRET"]
API_VERSION = os.environ.get("CAFE24_API_VERSION", "2024-09-01")
GH_TOKEN = os.environ["GH_TOKEN"]
GIST_ID = os.environ["GITHUB_GIST_ID"]

GIST_FILENAME = "cafe24_tokens.json"
CAFE24_TOKEN_URL = f"https://{MALL_ID}.cafe24api.com/api/v2/oauth/token"


def gist_load() -> dict:
    resp = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GH_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    resp.raise_for_status()
    content = resp.json()["files"][GIST_FILENAME]["content"]
    return json.loads(content)


def gist_save(data: dict) -> None:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GH_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {GIST_FILENAME: {"content": json.dumps(data, indent=2)}}},
        timeout=10,
    )
    resp.raise_for_status()


def cafe24_refresh(refresh_token: str) -> dict:
    from datetime import datetime, timedelta
    credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        CAFE24_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Cafe24-Api-Version": API_VERSION,
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    expires_in = int(data.get("expires_in", 7200))
    data["expires_at"] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    return data


def main():
    print("Gist에서 현재 토큰 로드...")
    current = gist_load()
    refresh_token = current.get("refresh_token")
    if not refresh_token:
        print("ERROR: Gist에 refresh_token이 없습니다.")
        sys.exit(1)

    print("Cafe24 토큰 갱신 중...")
    new_data = cafe24_refresh(refresh_token)

    new_tokens = {
        "access_token": new_data["access_token"],
        "refresh_token": new_data.get("refresh_token", refresh_token),
        "expires_at": new_data["expires_at"],
    }
    print(f"  access_token: {new_tokens['access_token'][:10]}...")
    print(f"  refresh_token: {new_tokens['refresh_token'][:10]}...")
    print(f"  expires_at: {new_tokens['expires_at']}")

    print("Gist 업데이트 중...")
    gist_save(new_tokens)
    print("완료!")


if __name__ == "__main__":
    main()

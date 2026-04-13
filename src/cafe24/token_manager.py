"""
토큰 자동 관리 — 만료 전 자동 갱신

사용법:
    tm = TokenManager()
    client = Cafe24Client(tm.get_token())
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.cafe24.auth import refresh_access_token

TOKEN_FILE = Path(".token.json")
REFRESH_BUFFER_MINUTES = 10  # 만료 10분 전에 미리 갱신


class TokenManager:
    def __init__(self, token_file: Path = TOKEN_FILE):
        self.token_file = token_file

    def _load(self) -> dict:
        if not self.token_file.exists():
            raise FileNotFoundError(".token.json 없음. 'uv run main.py login' 먼저 실행하세요.")
        return json.loads(self.token_file.read_text())

    def _save(self, data: dict):
        self.token_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _is_expired(self, data: dict) -> bool:
        expires_at = data.get("expires_at")
        if not expires_at:
            return True
        expiry = datetime.fromisoformat(expires_at)
        return datetime.now() >= expiry - timedelta(minutes=REFRESH_BUFFER_MINUTES)

    def get_token(self) -> str:
        data = self._load()
        if self._is_expired(data):
            print("[토큰] 만료 임박 — refresh_token으로 갱신 중...")
            new_data = refresh_access_token(data["refresh_token"])
            self._save(new_data)
            data = new_data
            print("[토큰] 갱신 완료")
        return data["access_token"]

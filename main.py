"""
ryublanche-ax 진입점

사용법:
  uv run main.py login           # 인증 URL 출력 + 콜백 서버 자동 시작 (권장)
  uv run main.py auth            # 인증 URL만 출력
  uv run main.py token <code>    # code → 토큰 교환
  uv run main.py products        # 상품 목록 조회 (.token.json 사용)
  uv run main.py server          # 어드민 웹 서버 시작 (포트 8000)
"""

import json
import sys
import webbrowser
from pathlib import Path

from src.cafe24.auth import exchange_code_for_token, get_authorization_url
from src.cafe24.client import Cafe24Client

TOKEN_FILE = Path(".token.json")

# 카페24 앱 권한 범위 (개발자센터 앱 설정과 동일하게 유지)
SCOPES = [
    "mall.read_application",
    "mall.write_application",
    "mall.read_category",
    "mall.write_category",
    "mall.read_product",
    "mall.write_product",
    "mall.read_collection",
    "mall.write_collection",
]


def load_token() -> str:
    if not TOKEN_FILE.exists():
        print("[오류] .token.json 파일이 없습니다. 먼저 'uv run main.py login'을 실행하세요.")
        sys.exit(1)
    data = json.loads(TOKEN_FILE.read_text())
    token = data.get("access_token")
    if not token:
        print("[오류] .token.json에 access_token이 없습니다.")
        sys.exit(1)
    return token


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    # ── login: 서버 시작 + 브라우저 오픈 ──────────────────────────────────────
    if cmd == "login":
        from src.cafe24.callback_server import run as run_server
        url = get_authorization_url(SCOPES)
        print(f"\n인증 URL:\n{url}\n")
        print("브라우저를 자동으로 엽니다. 팝업이 안 뜨면 위 URL을 직접 복사해 붙여넣으세요.")
        webbrowser.open(url)
        run_server()

    # ── auth: URL만 출력 ───────────────────────────────────────────────────────
    elif cmd == "auth":
        url = get_authorization_url(SCOPES)
        print("\n아래 URL을 브라우저에서 열어 쇼핑몰 관리자로 로그인하세요:\n")
        print(url)

    # ── token: code → 토큰 교환 ───────────────────────────────────────────────
    elif cmd == "token":
        if len(sys.argv) < 3:
            print("사용법: uv run main.py token <authorization_code>")
            return
        code = sys.argv[2]
        token_data = exchange_code_for_token(code)
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
        print("\n토큰 발급 성공:")
        print(f"  access_token  : {token_data.get('access_token', '')[:16]}...")
        print(f"  refresh_token : {token_data.get('refresh_token', '')[:16]}...")
        print(f"  expires_in    : {token_data.get('expires_in')}초")
        print(f"  저장 위치      : {TOKEN_FILE}")

    # ── products: 상품 목록 조회 ───────────────────────────────────────────────
    elif cmd == "products":
        client = Cafe24Client(load_token())
        result = client.get_products(limit=5)
        products = result.get("products", [])
        print(f"\n상품 {len(products)}개 조회:")
        for p in products:
            print(f"  [{p.get('product_no')}] {p.get('product_name')} — {p.get('price')}원")

    # ── server: 어드민 웹 서버 시작 ──────────────────────────────────────────
    elif cmd == "server":
        import uvicorn
        print("\n어드민 서버 시작: http://localhost:8000\n")
        uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)

    else:
        print(f"알 수 없는 명령어: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()

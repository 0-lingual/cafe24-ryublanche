"""
로컬 OAuth 콜백 서버 (HTTP — cloudflare tunnel이 HTTPS 담당)

카페24가 인증 후 code를 이 서버로 전달합니다.
code를 받으면 자동으로 access_token으로 교환하고 .token.json에 저장합니다.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cafe24.auth import exchange_code_for_token  # noqa: E402

load_dotenv()

PORT = 8080
TOKEN_FILE = Path(".token.json")


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        params = parse_qs(urlparse(self.path).query)

        if "error" in params:
            error = params["error"][0]
            desc = params.get("error_description", [""])[0]
            self._respond(400, f"<h2>인증 실패</h2><p>{error}: {desc}</p>")
            print(f"\n[오류] {error}: {desc}")
            _shutdown_after(self.server)
            return

        if "code" not in params:
            # App URL로 진입 시 (테스트설치 흐름) → OAuth 인증 URL로 리다이렉트
            from src.cafe24.auth import get_authorization_url
            SCOPES = [
                "mall.read_application", "mall.write_application",
                "mall.read_category", "mall.write_category",
                "mall.read_product", "mall.write_product",
                "mall.read_collection", "mall.write_collection",
            ]
            auth_url = get_authorization_url(SCOPES)
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            print(f"[→] OAuth 리다이렉트: {auth_url[:60]}...")
            return

        code = params["code"][0]
        print(f"\n[✓] code 수신: {code[:10]}...")

        try:
            token_data = exchange_code_for_token(code)
            TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")

            print(f"[✓] access_token  : {access_token[:20]}...")
            print(f"[✓] refresh_token : {refresh_token[:20]}...")
            print(f"[✓] 저장 완료: {TOKEN_FILE}")

            self._respond(200,
                "<h2>✅ 인증 성공!</h2>"
                "<p>토큰이 저장되었습니다. 이 창을 닫아도 됩니다.</p>")
        except Exception as e:
            self._respond(500, f"<h2>토큰 교환 실패</h2><pre>{e}</pre>")
            print(f"\n[오류] 토큰 교환 실패: {e}")

        _shutdown_after(self.server)

    def _respond(self, status: int, body: str):
        content = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def _shutdown_after(server: HTTPServer):
    import threading
    threading.Thread(target=server.shutdown, daemon=True).start()


def run(port: int = PORT):
    server = HTTPServer(("0.0.0.0", port), CallbackHandler)
    print(f"[콜백 서버] http://localhost:{port} 대기 중...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()

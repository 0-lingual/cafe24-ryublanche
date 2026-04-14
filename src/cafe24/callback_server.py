"""
로컬 OAuth 콜백 서버

인증 흐름:
  1. http://localhost:8080 접속 → 카페24 인증 링크 + URL 붙여넣기 폼 표시
  2. 사용자가 카페24에서 인증 → 브라우저가 만료된 터널 URL로 리다이렉트됨 (연결 오류)
  3. 주소창 URL 복사 → 폼에 붙여넣기 → 토큰 자동 저장
"""

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.cafe24.auth import exchange_code_for_token  # noqa: E402

load_dotenv()

PORT = 8080
TOKEN_FILE = Path(".token.json")

_FORM_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>카페24 인증</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;min-height:100vh}}
  .card{{background:#fff;border-radius:14px;padding:36px 40px;width:100%;max-width:560px;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
  h2{{font-size:20px;margin-bottom:24px;color:#222}}
  .step{{background:#fafafa;border:1px solid #e8e8e8;border-radius:10px;padding:20px;margin-bottom:16px}}
  .step-num{{display:inline-block;background:#6366f1;color:#fff;border-radius:50%;width:24px;height:24px;font-size:12px;font-weight:700;line-height:24px;text-align:center;margin-right:8px}}
  .step h3{{display:inline;font-size:14px;color:#444}}
  .step p{{font-size:13px;color:#666;margin:10px 0 12px}}
  a.btn{{display:inline-flex;align-items:center;gap:6px;background:#6366f1;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:500}}
  a.btn:hover{{background:#4f46e5}}
  input[type=text]{{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:13px;margin:8px 0;font-family:monospace}}
  input[type=text]:focus{{outline:none;border-color:#6366f1}}
  button{{background:#10b981;color:#fff;padding:10px 22px;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;margin-top:4px}}
  button:hover{{background:#059669}}
  .note{{font-size:12px;color:#aaa;margin-top:8px;word-break:break-all}}
  .error{{background:#fee2e2;color:#991b1b;border-radius:8px;padding:12px 16px;font-size:13px;margin-top:12px}}
</style>
</head>
<body>
<div class="card">
  <h2>카페24 OAuth 인증</h2>

  <div class="step">
    <span class="step-num">1</span><h3>카페24에서 인증하기</h3>
    <p>아래 버튼을 클릭해 카페24 관리자 계정으로 로그인 후 앱을 승인하세요.</p>
    <a class="btn" href="{auth_url}" target="_blank">카페24 인증 페이지 열기 →</a>
  </div>

  <div class="step">
    <span class="step-num">2</span><h3>리다이렉트 URL 붙여넣기</h3>
    <p>인증 후 브라우저가 <b>연결 오류</b> 페이지로 이동합니다.<br>
    주소창의 URL 전체를 복사해 아래에 붙여넣으세요.</p>
    <form method="POST" action="/submit">
      <input type="text" name="redirect_url"
        placeholder="https://zealand-travis-relations-donna.trycloudflare.com?code=...">
      <button type="submit">토큰 저장하기</button>
    </form>
    {error_block}
    <p class="note">예시: https://zealand-travis-relations-donna.trycloudflare.com?code=AbCdEfGh&amp;state=...</p>
  </div>
</div>
</body>
</html>
"""

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>인증 완료</title>
<style>body{{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f5}}
.card{{background:#fff;border-radius:14px;padding:40px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
h2{{color:#059669;margin-bottom:12px}}p{{color:#555;font-size:14px}}</style>
</head>
<body><div class="card"><h2>✅ 인증 완료</h2><p>토큰이 저장되었습니다.<br>이 창을 닫아도 됩니다.</p></div></body>
</html>
"""


class CallbackHandler(BaseHTTPRequestHandler):
    auth_url: str = ""

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        params = parse_qs(urlparse(self.path).query)

        if "error" in params:
            error = params["error"][0]
            desc = params.get("error_description", [""])[0]
            self._send(400, f"<h2>인증 실패</h2><p>{error}: {desc}</p>".encode())
            print(f"\n[오류] {error}: {desc}")
            _shutdown_after(self.server)
            return

        if "code" in params:
            # 터널을 통해 직접 code 수신
            code = params["code"][0]
            print(f"\n[✓] code 수신: {code[:10]}...")
            try:
                token_data = exchange_code_for_token(code)
                TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
                print(f"[✓] access_token: {token_data.get('access_token','')[:20]}...")
                print(f"[✓] 토큰 저장 완료: {TOKEN_FILE}")
                self._send(200, _SUCCESS_HTML.encode("utf-8"))
            except Exception as e:
                self._send(500, f"<h2>토큰 교환 실패</h2><pre>{e}</pre>".encode())
                print(f"\n[오류] 토큰 교환 실패: {e}")
                return
            _shutdown_after(self.server)
            return

        # code 없으면 수동 입력 폼 표시
        content = _FORM_HTML.format(
            auth_url=self.__class__.auth_url,
            error_block="",
        ).encode("utf-8")
        self._send(200, content)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        redirect_url = params.get("redirect_url", [""])[0].strip()

        parsed = urlparse(redirect_url)
        url_params = parse_qs(parsed.query)

        if "code" not in url_params:
            error = '<div class="error">⚠️ URL에서 code를 찾을 수 없습니다. 주소창의 URL 전체를 복사해 다시 붙여넣어 주세요.</div>'
            content = _FORM_HTML.format(
                auth_url=self.__class__.auth_url,
                error_block=error,
            ).encode("utf-8")
            self._send(400, content)
            return

        code = url_params["code"][0]
        try:
            token_data = exchange_code_for_token(code)
            TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False))
            access_token = token_data.get("access_token", "")
            print(f"\n[✓] 토큰 저장 완료: {TOKEN_FILE}")
            print(f"[✓] access_token: {access_token[:20]}...")
            self._send(200, _SUCCESS_HTML.encode("utf-8"))
        except Exception as e:
            error = f'<div class="error">⚠️ 토큰 교환 실패: {e}</div>'
            content = _FORM_HTML.format(
                auth_url=self.__class__.auth_url,
                error_block=error,
            ).encode("utf-8")
            self._send(500, content)
            print(f"\n[오류] 토큰 교환 실패: {e}")
            return

        _shutdown_after(self.server)

    def _send(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _shutdown_after(server: HTTPServer):
    import threading
    threading.Thread(target=server.shutdown, daemon=True).start()


def run(port: int = PORT, auth_url: str = ""):
    CallbackHandler.auth_url = auth_url
    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    print(f"[콜백 서버] http://localhost:{port} 에서 대기 중...")
    webbrowser.open(f"http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()

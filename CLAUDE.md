# ryublanche-ax — 카페24 AI 상품 자동 등록 어드민

## 세션 시작 시 필수

**반드시 최신 랩업 파일을 먼저 읽어라:**
```
.claude/wrap-up/YYYY-MM-DD.md  (가장 최근 날짜 파일)
```
파일 목록: `ls .claude/wrap-up/` 로 확인 후 최신 파일 Read

---

## 서버 실행

```bash
uv run main.py server
# → http://localhost:8000
```

- `.token.json` 있으면 자동 갱신됨 — OAuth 로그인 불필요
- refresh_token 만료 후: `uv run main.py login`

---

## 프로젝트 구조

```
main.py                  # 진입점
src/api/app.py           # FastAPI 라우트
src/api/static/index.html# 어드민 UI
src/ai/analyzer.py       # Claude Vision 이미지 분석
src/cafe24/client.py     # 카페24 API 클라이언트
src/cafe24/token_manager.py  # 토큰 자동 갱신
.token.json              # 액세스/리프레시 토큰
.env                     # 환경변수
uploads/                 # 업로드 이미지
.claude/wrap-up/         # 세션별 랩업 기록
```

## 세션 종료 시

`/wrap-up` 실행하여 `.claude/wrap-up/YYYY-MM-DD.md` 갱신

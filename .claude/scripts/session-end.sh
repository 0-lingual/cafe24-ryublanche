#!/bin/bash
# 세션 종료 시 자동 실행 — 랩업 파일에 종료 시각 기록

PROJECT_DIR="/Users/jhhyun/Documents/claude-starter-main/projects/ryublanche-ax"
WRAPUP_DIR="$PROJECT_DIR/.claude/wrap-up"
TODAY=$(date +%Y-%m-%d)
WRAPUP_FILE="$WRAPUP_DIR/$TODAY.md"
NOW=$(date "+%Y-%m-%d %H:%M:%S")

# 오늘 랩업 파일이 없으면 기본 템플릿 생성
if [ ! -f "$WRAPUP_FILE" ]; then
  cat > "$WRAPUP_FILE" << EOF
# 세션 랩업 — $TODAY

## 작업 요약
(이 세션에서 작성된 랩업 없음)

## 서버 시작 방법
\`\`\`bash
cd $PROJECT_DIR
uv run main.py server
\`\`\`

브라우저에서 **http://localhost:8000** 접속
EOF
fi

# 세션 종료 시각 기록
echo "" >> "$WRAPUP_FILE"
echo "---" >> "$WRAPUP_FILE"
echo "**세션 종료**: $NOW" >> "$WRAPUP_FILE"
echo "**git HEAD**: $(cd "$PROJECT_DIR" && git log -1 --oneline 2>/dev/null || echo 'N/A')" >> "$WRAPUP_FILE"

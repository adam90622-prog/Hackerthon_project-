#!/usr/bin/env bash
# 새 seeds CSV 하나로 "정제 → 3종 콘텐츠 생성 → 형식 검증 → 캐던스 점검 → KPI 측정 →
# HTML 리포트"까지 전 과정을 한 번에 실행합니다.
#
# 사용법:
#   bash scripts/full_pipeline.sh data/새파일.csv
#
# 전제조건:
#   - 이 저장소 루트에서 실행해야 합니다 (scripts/, data/, output/, context/ 폴더가 보이는 위치)
#   - Claude Code CLI(claude 명령)가 설치·로그인되어 있어야 합니다 (3종 콘텐츠 생성 단계에서 사용)
#
# 이 스크립트 하나가 하는 일:
#   1) 결측·중복 등 데이터 정제           (scripts/clean_seeds.py)
#   2) 타깃별 발행 주기 가능 여부 점검      (scripts/check_cadence.py)
#   3) 카드뉴스·카카오·뉴스레터 3종 생성    (Claude Code 헤드리스 호출, claude -p)
#   4) 생성물 글자수·용어 반영 자동 검증    (scripts/validate_content.py)
#   5) KPI 4종 실측                       (scripts/measure_kpi.py)
#   6) 콘텐츠+KPI를 담은 HTML 리포트 생성  (scripts/build_report.py)

set -e

if [ -z "$1" ]; then
  echo "사용법: bash scripts/full_pipeline.sh <seeds_csv 경로>"
  echo "예시:   bash scripts/full_pipeline.sh data/nursevillage_content_seeds.csv"
  exit 1
fi

SEEDS_CSV="$1"
BASENAME=$(basename "$SEEDS_CSV" .csv)
CLEANED_CSV="data/${BASENAME}_cleaned.csv"
CONTENT_MD="output/output_content_set.md"

if [ ! -f "$SEEDS_CSV" ]; then
  echo "❌ 파일을 찾을 수 없습니다: $SEEDS_CSV"
  exit 1
fi

if ! command -v claude &> /dev/null; then
  echo "❌ 'claude' 명령을 찾을 수 없습니다. Claude Code CLI가 설치·로그인되어 있는지 확인하세요."
  echo "   (설치되어 있다면, 3단계만 Claude Code 채팅창에서 직접 '새 시드로 3종 콘텐츠 만들어줘'라고"
  echo "   요청한 뒤, 이 스크립트를 다시 실행하면 4~6단계는 자동으로 이어집니다.)"
  exit 1
fi

echo "========================================"
echo "[1/6] 데이터 정제 (clean_seeds.py)"
echo "========================================"
python scripts/clean_seeds.py "$SEEDS_CSV" "$CLEANED_CSV"

echo ""
echo "========================================"
echo "[2/6] 캐던스 점검 (check_cadence.py)"
echo "========================================"
python scripts/check_cadence.py "$CLEANED_CSV" || echo "  (FAIL이 있어도 파이프라인은 계속 진행합니다 — 발행 캘린더/전략안에서 다룰 문제입니다)"

echo ""
echo "========================================"
echo "[3/6] 3종 콘텐츠 생성 (Claude Code 호출 중... 데이터 양에 따라 수 분 소요될 수 있습니다)"
echo "========================================"
claude -p "다음 정제된 시드 CSV 파일(${CLEANED_CSV})의 모든 행을 읽고, .claude/skills/analyze.md → insight.md → generate.md → review.md 절차를 그대로 따라 각 행마다 카드뉴스(3~5장, 장별 헤드라인+본문 2~3문장, 마지막 장 CTA) · 카카오메시지(200자 이내) · 뉴스레터(550~650자, 도입-본문-CTA 3단) 3종 콘텐츠를 생성해줘. context/nursevillage-brand-voice.md의 호칭·이모지·인용 화법 규칙을 반드시 반영하고, 각 행에서 사용한 현장 용어를 태그로 정리해줘. 결과는 기존 output_content_set.md와 동일한 마크다운 형식으로 ${CONTENT_MD} 에 덮어써줘."

echo ""
echo "========================================"
echo "[4/6] 생성물 형식 검증 (validate_content.py)"
echo "========================================"
python scripts/validate_content.py

echo ""
echo "========================================"
echo "[5/6] KPI 측정 (measure_kpi.py)"
echo "========================================"
python scripts/measure_kpi.py "$CLEANED_CSV"

echo ""
echo "========================================"
echo "[6/6] HTML 리포트 생성 (build_report.py)"
echo "========================================"
python scripts/build_report.py

echo ""
echo "✅ 전 과정 완료"
echo "   - 콘텐츠 3종:   $CONTENT_MD"
echo "   - KPI 결과:     output/kpi-results.json"
echo "   - HTML 리포트:  output/dashboard.html"

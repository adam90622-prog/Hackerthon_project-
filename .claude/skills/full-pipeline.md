# /full-pipeline — 새 시드로 전 과정 한 번에 실행

## 목적
새 seeds CSV 하나로 "정제 → 3종 콘텐츠 생성 → 형식 검증 → 캐던스 점검 → KPI 측정 →
HTML 리포트"까지 전 과정을 이 대화 안에서 이어서 실행합니다. 터미널을 쓸 수 있다면
`bash scripts/full_pipeline.sh <csv>` 한 줄로도 동일하게 실행되지만, 이 스킬은 Claude
Code 채팅창에 "새 시드 파일로 전체 파이프라인 실행해줘"라고 말 한마디만 해도 되도록
만든 버전입니다.

## 트리거 예시
- "새 시드 파일로 전체 파이프라인 실행해줘"
- "이 CSV로 3종 콘텐츠부터 리포트까지 한 번에 만들어줘"

## 절차 (아래 순서대로 bash 도구를 사용해 직접 실행할 것)

1. **정제**: `python scripts/clean_seeds.py <새파일>.csv data/<새파일>_cleaned.csv`
   콘솔에 나오는 범주값 정규화·중복 제거·keywords 보완 로그를 확인하고, 애매한 케이스가
   있으면 decisions.md에 기록된 근거를 사용자에게 보여준다.

2. **캐던스 점검**: `python scripts/check_cadence.py data/<새파일>_cleaned.csv`
   FAIL이 나와도 파이프라인은 계속 진행한다(발행 캘린더·전략안에서 다룰 문제이기 때문).

3. **3종 콘텐츠 생성**: `.claude/skills/analyze.md → insight.md → generate.md → review.md`
   절차를 그대로 따라, 정제된 CSV의 모든 행에 대해 카드뉴스(3~5장)·카카오메시지(200자
   이내)·뉴스레터(550~650자) 3종을 생성한다. `context/nursevillage-brand-voice.md` 규칙을
   반드시 반영하고, 결과를 `output/output_content_set.md`에 기존과 동일한 마크다운
   형식으로 저장한다.

4. **형식 검증**: `python scripts/validate_content.py`
   실패 항목이 있으면 3번으로 돌아가 해당 행만 다시 생성한다.

5. **KPI 측정**: `python scripts/measure_kpi.py data/<새파일>_cleaned.csv`
   (CSV 경로를 반드시 새 파일로 넘겨야 새 데이터 기준으로 keywords_required 반영률 등이
   정확히 계산된다.)

6. **HTML 리포트 생성**: `python scripts/build_report.py`
   `output/dashboard.html`이 새 콘텐츠·새 KPI로 갱신된다.

## 완료 조건
- `output/output_content_set.md`, `output/kpi-results.json`, `output/dashboard.html`
  세 파일이 모두 갱신됨
- 4번 검증에서 전 행 통과
- 사용자에게 6단계 각각의 결과 요약(성공/실패 건수, KPI 수치)을 보고

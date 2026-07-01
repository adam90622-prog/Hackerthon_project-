## 신규 담당자용 3줄 요약

1. 새 시드 CSV 파일을 data/ 폴더에 넣으세요
2. Claude Code를 열고 "새 시드 파일 정제하고 3종 콘텐츠 만들어줘"라고 입력하세요
3. output 폴더에서 결과 파일을 확인하세요

# 파이프라인 사용법 — 정제 + 캐던스 검증 (Standard: 재사용 파이프라인)

## 한 번에 실행

```bash
python scripts/run_pipeline.py <seeds_csv> [cleaned_csv] [--target-days 14] [--reuse-days 70]
```

예시 (제공된 원본 데이터로 재현):

```bash
python scripts/run_pipeline.py data/nursevillage_content_seeds.csv data/nursevillage_content_seeds_cleaned.csv
```

- `seeds_csv`만 넘기면 `<이름>_cleaned.csv`로 자동 저장됩니다.
- 인자를 전부 생략하면 `data/nursevillage_content_seeds.csv`를 기본값으로 사용합니다.
- 내부적으로 1단계 `clean_seeds.py` → 2단계 `check_cadence.py` 순서로 호출만 하는
  얇은 래퍼입니다. 각 단계는 아래처럼 단독 실행도 가능합니다.

## 단계별 단독 실행

```bash
# 1단계: 정제만
python scripts/clean_seeds.py data/nursevillage_content_seeds.csv data/nursevillage_content_seeds_cleaned.csv

# 2단계: 캐던스 검증만 (이미 정제된 CSV 대상)
python scripts/check_cadence.py data/nursevillage_content_seeds_cleaned.csv
```

## clean_seeds.py가 처리하는 정제 항목

- 범주값 오타·공백 정규화 (tone, target_audience)
- keywords_required 구분자 정규화, 결측 보완(규칙 1~3, 근거는 decisions.md에 자동 기록)
- 완전 중복 행 제거, topic 결측 플래그
- 중복 topic(타깃이 다른 경우)은 dup_group으로 표시해 이후 생성 단계에서 관점을
  차별화하도록 유도

## check_cadence.py 판정 방식

- k = 정제된 CSV에서 타깃(target_audience)별 상시(ref_event 없는) 콘텐츠 개수
- 같은 콘텐츠를 `--reuse-days`(기본 70일) 안에 재사용하지 않는다는 전제에서, 지속
  가능한 평균 발행 주기 하한은 `reuse-days ÷ k`일
- 이 값이 `--target-days`(기본 14일) 이하면 PASS, 초과하면 FAIL
- 종료 코드: 전체 타깃 PASS면 0, 하나라도 FAIL이면 1 (CI 연동 가능)

## 검증된 결과 (제공된 18행 데이터 기준)

| 타깃 | k(상시 콘텐츠 수) | 70÷k | 판정 |
|---|---|---|---|
| 신규RN | 3 | 23.3일 | ❌ FAIL |
| 간호학생 | 3 | 23.3일 | ❌ FAIL |
| 경력RN | 4 | 17.5일 | ❌ FAIL |

18행 데이터는 상시 콘텐츠 수가 적어(k<5) 구조적으로 14일 캐던스를 바로 충족하기
어렵습니다. 이 인사이트를 근거로 삼은 개선 전략은 `challenge-strategy.md`
전략안 1에서 다룹니다.

## 새 seeds를 넣을 때 체크리스트

1. `python scripts/run_pipeline.py data/<새파일>.csv` 실행
2. 콘솔에 출력되는 "범주값 정규화 / 중복 제거 / topic 결측 / keywords 보완" 내역을
   확인 — 애매한 케이스가 있으면 decisions.md에 근거·후보가 자동 기록되니 그걸 보고
   `scripts/clean_seeds.py`의 `MANUAL_OVERRIDES`를 채운다
3. 캐던스 결과가 FAIL이면 어느 타깃의 k가 부족한지 확인하고, 해당 타깃의 상시
   (ref_event 없는) 소재를 필요한 만큼 늘린다

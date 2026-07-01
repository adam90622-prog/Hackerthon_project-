## 신규 담당자용 3줄 요약

1. 새 시드 CSV 파일을 data/ 폴더에 넣으세요
2. Claude Code를 열고 "새 시드 파일 정제하고 3종 콘텐츠 만들어줘"라고 입력하세요
3. output 폴더에서 결과 파일을 확인하세요

# 파이프라인 사용법 — 정제 + 캐던스 검증 (Standard 8: 재사용 파이프라인)

새 seeds CSV 하나만 있으면 "결측·오타·중복 정제 → 타깃별 14일 캐던스
PASS/FAIL 판정"까지 명령 한 번으로 실행됩니다.

## 한 번에 실행

```bash
python scripts/run_pipeline.py <seeds_csv> [cleaned_csv] [--target-days 14] [--reuse-days 70]
```

예시:

```bash
python scripts/run_pipeline.py data/dummy_seeds_50.csv data/dummy_seeds_50_cleaned.csv
```

- `seeds_csv`만 넘기면 `<이름>_cleaned.csv`로 자동 저장됩니다.
- 인자를 전부 생략하면 기존 `data/nursevillage_content_seeds.csv`를 기본값으로
  사용합니다(하위 호환).
- 내부적으로 1단계 `scripts/clean_seeds.py` → 2단계 `scripts/check_cadence.py`
  순서로 호출만 하는 얇은 래퍼입니다. 각 단계는 아래처럼 단독 실행도 가능합니다.

## 단계별 단독 실행

```bash
# 1단계: 정제만
python scripts/clean_seeds.py data/dummy_seeds_50.csv data/dummy_seeds_50_cleaned.csv

# 2단계: 캐던스 검증만 (이미 정제된 CSV 대상)
python scripts/check_cadence.py data/dummy_seeds_50_cleaned.csv
```

## 캐던스 검증(check_cadence.py) 판정 방식

- k = 정제된 CSV에서 타깃(target_audience)별로 "생성 대상이고(topic 존재,
  topic 결측 플래그 없음) ref_event가 비어 있는" 상시(evergreen) 콘텐츠 개수.
- 같은 콘텐츠를 최소 `--reuse-days`(기본 70일) 텀 없이 재사용하지 않는다는
  전제에서, 지속 가능한 평균 발행 주기 하한은 `reuse-days ÷ k`일입니다.
- 이 값이 `--target-days`(기본 14일) 이하면 PASS, 초과하면 FAIL이고, 항상
  `min k needed = ceil(reuse-days / target-days)`(기본 설정에서는 5)도 함께
  출력합니다.
- 종료 코드: 전체 타깃 PASS면 0, 하나라도 FAIL이면 1 (CI/스크립트 체이닝에
  바로 활용 가능).

## 검증된 결과 (2026-07-01)

| 데이터셋 | 신규RN k | 간호학생 k | 경력RN k | 결과 |
|---|---|---|---|---|
| data/nursevillage_content_seeds_cleaned.csv (18행) | 3 | 3 | 4 | ❌ FAIL (전 타깃) |
| data/dummy_seeds_50_cleaned.csv (50행 더미) | 13 | 11 | 10 | ✅ PASS (전 타깃) |

18행 데이터는 구조적으로 14일 캐던스가 불가능하고, 50행 더미로는 가능함을
확인했습니다 — 원인은 로직 결함이 아니라 데이터 볼륨(타깃당 상시 콘텐츠
개수 k) 부족이었습니다. 근거: [decisions.md](../decisions.md) 최신 항목,
[standard-guide.md](standard-guide.md) "타깃별 최대 공백일 검증표".

## 재사용성(reusability) 검증 내역

`data/dummy_seeds_50.csv`(원본 더미, 오타·결측·중복 포함)를 `clean_seeds.py`
로 다시 정제한 결과가 기존 `data/dummy_seeds_50_cleaned.csv`와 바이트 단위로
100% 동일함을 확인했습니다 — 정제 로직이 18행 원본 데이터뿐 아니라 새로운
50행 데이터에도 동일하게, 결정론적으로 적용됨을 의미합니다(같은 입력이면
항상 같은 출력·같은 decisions.md 근거가 나옴).

## 발행 이력 반영 재스케줄링 (scripts/reschedule.py)

정제·캐던스 검증 다음 단계로, 실제 발행 이력(`data/published_log.csv`)을
반영해 "오늘 이후 구간만" 다시 스케줄링하는 확장 스크립트입니다.

```bash
python scripts/reschedule.py [--today 2026-07-01] [--horizon-end 2026-12-17] [--reuse-days 70] [--target-days 14]
```

- 오늘 이전 발행 건은 `data/published_log.csv`의 source of truth로 두고 그대로
  고정, 오늘 이후 구간만 18건 원본 + `data/classified_new_articles.csv`를 합친
  확장 풀로 재계산합니다.
- 내부적으로 `check_cadence.py`의 `count_evergreen_by_target`/`evaluate_cadence`/
  `DEFAULT_REUSE_DAYS`/`DEFAULT_TARGET_DAYS`를 그대로 import해서 씁니다 — 별도
  로직을 새로 만들지 않고 기존 파이프라인 함수를 합성만 합니다.
- 결과는 `output/rescheduled-calendar.md`에 저장되며, `output/standard-guide.md`
  (원본 41건 스냅샷)는 대체하지 않고 그대로 둡니다.
- 자세한 설계 근거는 [decisions.md](../decisions.md)의 "Standard 파이프라인
  확장" 항목 참고.

## 새 seeds를 넣을 때 체크리스트

1. `python scripts/run_pipeline.py data/<새파일>.csv` 실행
2. 콘솔에 출력되는 "범주값 정규화 / 중복 제거 / topic 결측 / keywords 보완"
   내역을 확인 — `MANUAL_OVERRIDES`가 필요한 애매한 규칙 2(ref_event 연결)
   케이스가 있으면 `decisions.md`에 근거·후보가 자동 기록되니 그걸 보고
   `scripts/clean_seeds.py`의 `MANUAL_OVERRIDES`를 채운다.
3. 캐던스 결과가 FAIL이면 어느 타깃의 k가 부족한지 표에서 확인하고, 해당
   타깃의 상시(ref_event 없는) 소재를 `min k needed`만큼 늘린다.

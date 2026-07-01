"""캐던스(발행 주기) 검증 스크립트 — 정제된 seeds CSV에서 타깃별 상시
(ref_event 없는) 콘텐츠 개수(k)를 세어 70÷k 공식으로 목표 캐던스(기본 14일)
충족 여부를 판정한다.

공식 근거
---------
같은 콘텐츠를 최소 reuse_days(기본 70일, 2~3개월) 텀 없이 재사용하지 않는다는
안전장치 하에, 타깃당 상시 콘텐츠 k개를 균등 순환 재발행하면 지속 가능한
평균 발행 주기의 하한은 reuse_days÷k일이다. 이 값이 목표 캐던스(target_days)
이하이면 이론상 목표 캐던스를 달성 가능(PASS), 아니면 구조적으로 불가능(FAIL).
유도 과정과 18행 데이터 사례(k=3,3,4로 전부 FAIL)는 output/standard-guide.md
"타깃별 최대 공백일 검증표" 참고.

k 집계 규칙
-----------
- topic이 비어 있는 행(review_flag에 "topic 결측"이 찍힌 행)은 애초에 콘텐츠
  생성 대상에서 제외되므로(decisions.md 참고) k에 포함하지 않는다.
- ref_event가 있는 행은 특정 이벤트 앞에 1회성으로 배치되는 시의성 콘텐츠라
  순환 재발행 풀에 넣지 않는다(원칙 1: 이벤트는 발생 전 1회만 노출).
- dup_group(같은 topic, 다른 target_audience)은 타깃별로 별도 콘텐츠이므로
  각자의 target_audience 쪽 k에 정상적으로 포함한다.

사용법
------
python scripts/check_cadence.py [cleaned_csv] [--target-days 14] [--reuse-days 70]
인자를 생략하면 nursevillage_content_seeds_cleaned.csv를 기본값으로 쓴다
(clean_seeds.py와 동일한 하위 호환 규칙).
"""
import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLEANED_CSV = ROOT / "data" / "nursevillage_content_seeds_cleaned.csv"

# 70일 재사용 텀 / 14일 목표 캐던스 — 이 두 숫자가 이 파이프라인의 유일한 정의처.
# 다른 스크립트(reschedule.py)는 이 상수를 import해서 쓴다(값을 다시 적지 않는다).
DEFAULT_REUSE_DAYS = 70
DEFAULT_TARGET_DAYS = 14


def ensure_utf8_stdout():
    """콘솔 인코딩이 utf-8이 아닌 환경(예: 한글 Windows cp949)에서도 한글 출력이
    깨지지 않게 한다. reschedule.py도 이 함수를 그대로 가져다 쓴다."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def load_rows(csv_path):
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def is_generatable(row):
    if not row.get("topic", "").strip():
        return False
    if "topic 결측" in row.get("review_flag", ""):
        return False
    return True


def count_evergreen_by_target(rows):
    counts = {}
    for r in rows:
        if not is_generatable(r):
            continue
        if r.get("ref_event", "").strip():
            continue
        target = r["target_audience"].strip()
        if target:
            counts[target] = counts.get(target, 0) + 1
    return counts


def evaluate_cadence(counts, target_days=DEFAULT_TARGET_DAYS, reuse_days=DEFAULT_REUSE_DAYS):
    results = {}
    min_k_needed = math.ceil(reuse_days / target_days)
    for target, k in counts.items():
        min_cycle_days = reuse_days / k
        results[target] = {
            "k": k,
            "min_cycle_days": min_cycle_days,
            "pass": min_cycle_days <= target_days,
            "min_k_needed": min_k_needed,
        }
    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CLEANED_CSV))
    parser.add_argument("--target-days", type=int, default=DEFAULT_TARGET_DAYS)
    parser.add_argument("--reuse-days", type=int, default=DEFAULT_REUSE_DAYS)
    ns = parser.parse_args(argv)
    return Path(ns.csv_path), ns.target_days, ns.reuse_days


def main(argv=None):
    ensure_utf8_stdout()

    csv_path, target_days, reuse_days = parse_args(sys.argv[1:] if argv is None else argv)
    rows = load_rows(csv_path)
    counts = count_evergreen_by_target(rows)
    results = evaluate_cadence(counts, target_days, reuse_days)

    print(f"[input] {csv_path.name} (target_days={target_days}, reuse_days={reuse_days})")
    print(f"{'target':<10}{'k':<5}{f'{reuse_days}/k(일)':<12}{'result':<8}min k needed")
    all_pass = True
    for target in sorted(results):
        r = results[target]
        if not r["pass"]:
            all_pass = False
        print(f"{target:<10}{r['k']:<5}{r['min_cycle_days']:<12.1f}"
              f"{'PASS' if r['pass'] else 'FAIL':<8}{r['min_k_needed']}")
    print()
    print("PASS" if all_pass else "FAIL", "— 전체 타깃 기준")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

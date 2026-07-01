"""정제(clean_seeds) + 캐던스 검증(check_cadence)을 한 번에 실행하는 파이프라인 래퍼.

새 seeds CSV 하나로 "정제 -> 결측/오타/중복 처리 -> 타깃별 14일 캐던스
PASS/FAIL"까지 한 번에 확인하기 위한 진입점. 두 스크립트는 각각 단독 실행도
가능하다(clean_seeds.py, check_cadence.py 참고) — 이 스크립트는 순서대로
호출만 한다.

사용법
------
python scripts/run_pipeline.py <seeds_csv> [cleaned_csv] [--target-days 14] [--reuse-days 70]

인자를 모두 생략하면 clean_seeds.py의 기본 경로(nursevillage 파일)를 그대로
쓴다(하위 호환). cleaned_csv를 생략하면 <seeds_csv 이름>_cleaned.csv 로 저장한다.

예시
----
python scripts/run_pipeline.py data/dummy_seeds_50.csv data/dummy_seeds_50_cleaned.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_seeds
import check_cadence


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("seeds_csv", nargs="?", default=None)
    parser.add_argument("cleaned_csv", nargs="?", default=None)
    parser.add_argument("--target-days", type=int, default=check_cadence.DEFAULT_TARGET_DAYS)
    parser.add_argument("--reuse-days", type=int, default=check_cadence.DEFAULT_REUSE_DAYS)
    return parser.parse_args(argv)


def main(argv=None):
    ns = parse_args(sys.argv[1:] if argv is None else argv)

    seeds_csv = Path(ns.seeds_csv) if ns.seeds_csv else clean_seeds.DEFAULT_SEEDS_CSV
    if ns.cleaned_csv:
        cleaned_csv = Path(ns.cleaned_csv)
    elif ns.seeds_csv:
        cleaned_csv = seeds_csv.with_name(seeds_csv.stem + "_cleaned.csv")
    else:
        cleaned_csv = clean_seeds.DEFAULT_CLEANED_CSV

    print("=== 1단계: 정제 (clean_seeds) ===")
    clean_seeds.main([str(seeds_csv), str(cleaned_csv)])

    print()
    print("=== 2단계: 캐던스 검증 (check_cadence) ===")
    check_cadence.main([str(cleaned_csv), "--target-days", str(ns.target_days),
                        "--reuse-days", str(ns.reuse_days)])  # 캐던스 FAIL 시 여기서 exit code 1로 종료됨


if __name__ == "__main__":
    main()

"""KPI 측정 스크립트 — Problem 04 다이버즈
4개 지표를 output/output_content_set.md의 콘텐츠에 대해 측정합니다:
1. 생성 성공률 (채널별 포맷 조건 충족 여부)
2. 브랜드보이스 유지도 (호칭 병기·이모지 팔레트 준수, 카카오 이모지 미사용 준수)
3. 전문용어 사용도 (keywords_required 반영률)
4. 속도 단축률 (가정 기반 추정치 — 아래 상수 주석에 근거 명시)

결과는 output/kpi-results.json 과 콘솔 표로 출력됩니다.

사용법:
    python scripts/measure_kpi.py                          # 기본 CSV(nursevillage_content_seeds_cleaned.csv) 기준
    python scripts/measure_kpi.py data/새파일_cleaned.csv    # 새 seeds로 재현할 때
"""
import re
import csv
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONTENT_MD = BASE / "output" / "output_content_set.md"
DEFAULT_CSV = BASE / "data" / "nursevillage_content_seeds_cleaned.csv"
CSV_PATH = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CSV

EMOJI_PALETTE = set("🤍😊🥲💪🌱😆🙈😅🎉")
HONOR_MAP = {"신규RN": "신규 RN 선생님", "간호학생": "간호학생 선생님", "경력RN": "경력RN 선생님"}

MANUAL_MINUTES_PER_SET = 150
AI_MINUTES_PER_SET = 5


def load_seeds():
    with open(CSV_PATH, encoding="utf-8") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def load_blocks():
    content = CONTENT_MD.read_text(encoding="utf-8")
    parts = re.split(r"\n## 시드 #(\d+):", content)[1:]
    return {parts[i].strip(): parts[i + 1] for i in range(0, len(parts), 2)}


def measure():
    seeds = load_seeds()
    blocks = load_blocks()

    channel_success = {"card": 0, "kakao": 0, "newsletter": 0}
    honor_ok, emoji_ok, kakao_noemoji_ok = 0, 0, 0
    kw_total, kw_hit = 0, 0

    for sid, body in blocks.items():
        seed = seeds.get(sid, {})
        target = seed.get("target_audience", "")

        m = re.search(r"### 🎴 카드뉴스 \((\d+)장\)", body)
        n_slides = int(m.group(1)) if m else 0
        headers = re.findall(r"\*\*(\d+)장(?:\(CTA\))?\.\s", body)
        if 3 <= n_slides <= 5 and len(headers) == n_slides and f"{n_slides}장(CTA)" in body:
            channel_success["card"] += 1

        km = re.search(r"### 💬 카카오메시지 \((\d+)자\)\n(.+?)(?=\n###|\n---|\Z)", body, re.S)
        kakao_text = km.group(2).strip() if km else ""
        kakao_len = len(kakao_text)
        if km and int(km.group(1)) == kakao_len and kakao_len <= 200:
            channel_success["kakao"] += 1
        if not any(c in EMOJI_PALETTE for c in kakao_text):
            kakao_noemoji_ok += 1

        nm = re.search(r"### 📰 뉴스레터 \((\d+)자\)\n(.+?)(?=\n###|\n---|\Z)", body, re.S)
        news_text = nm.group(2).strip() if nm else ""
        news_len = len(news_text)
        if nm and int(nm.group(1)) == news_len and 550 <= news_len <= 650:
            channel_success["newsletter"] += 1

        honor = HONOR_MAP.get(target)
        if honor and honor in body:
            honor_ok += 1
        if any(c in EMOJI_PALETTE for c in body):
            emoji_ok += 1

        required = [k.strip() for k in seed.get("keywords_required", "").split(",") if k.strip()]
        kw_total += len(required)
        kw_hit += sum(1 for k in required if k in body)

    n = len(blocks)
    results = {
        "basic_format": {
            "총 시드 수": n,
            "카드뉴스 성공": f"{channel_success['card']}/{n}",
            "카카오메시지 성공": f"{channel_success['kakao']}/{n}",
            "뉴스레터 성공": f"{channel_success['newsletter']}/{n}",
            "생성 성공률(채널 평균, %)": round(sum(channel_success.values()) / (n * 3) * 100, 1),
        },
        "brand_voice": {
            "호칭 병기 준수": f"{honor_ok}/{n}",
            "감성 이모지 포함(카드+뉴스레터)": f"{emoji_ok}/{n}",
            "카카오 이모지 미사용 준수": f"{kakao_noemoji_ok}/{n}",
            "브랜드보이스 유지도(3개 규칙 평균, %)": round((honor_ok + emoji_ok + kakao_noemoji_ok) / (n * 3) * 100, 1),
        },
        "keywords": {
            "요구 키워드 총합": kw_total,
            "반영된 키워드 수": kw_hit,
            "전문용어 사용도(%)": round(kw_hit / kw_total * 100, 1) if kw_total else None,
        },
        "speed": {
            "수작업 기준(1건, 분)": MANUAL_MINUTES_PER_SET,
            "AI 파이프라인 기준(1건, 분)": AI_MINUTES_PER_SET,
            "속도 단축률(%)": round((MANUAL_MINUTES_PER_SET - AI_MINUTES_PER_SET) / MANUAL_MINUTES_PER_SET * 100, 1),
            "18건 총 소요-수작업(시간)": round(MANUAL_MINUTES_PER_SET * n / 60, 1),
            "18건 총 소요-AI(시간)": round(AI_MINUTES_PER_SET * n / 60, 2),
            "가정 근거": "problem.md '1건 2~3시간'(중간값 150분) vs company-info.md '5분 내 초안' 목표치 비교. 실측 스톱워치 값이 아닌 문제 정의서 상 목표 비교치임.",
        },
    }
    return results


if __name__ == "__main__":
    r = measure()
    out_path = BASE / "output" / "kpi-results.json"
    out_path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    for section, data in r.items():
        print(f"\n=== {section} ===")
        for k, v in data.items():
            print(f"{k}: {v}")
    try:
        csv_display = CSV_PATH.relative_to(BASE)
    except ValueError:
        csv_display = CSV_PATH
    print(f"\n저장됨: {out_path} (기준 CSV: {csv_display})")

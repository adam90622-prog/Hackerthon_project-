"""
콘텐츠 3종 세트 검증 스크립트 (글자수·키워드 반영 검증용 — 콘텐츠 자체는 생성하지 않음)

사용법:
    python scripts/validate_content.py            # 전체 18행 검증
    python scripts/validate_content.py 01 05 12   # 특정 id만 검증
"""

import re
import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONTENT_MD = BASE / "output" / "output_content_set.md"
CSV_PATH = BASE / "data" / "nursevillage_content_seeds_cleaned.csv"

KAKAO_MAX = 200
NEWSLETTER_MIN = 550
NEWSLETTER_MAX = 650


def load_keywords():
    keywords = {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row["keywords_required"].strip()
            # 결측 보완 표기 "[추론: a,b,c]" 형태 처리
            m = re.match(r"^\[추론:\s*(.*)\]$", raw)
            if m:
                raw = m.group(1)
            terms = [t.strip() for t in raw.split(",") if t.strip()]
            # "국시(국가시험)" 같은 대체 표기는 (A/B 중 하나만 등장해도 통과)로 처리
            parsed_terms = []
            for t in terms:
                alt_m = re.match(r"^(.+?)\((.+?)\)$", t)
                if alt_m:
                    parsed_terms.append([alt_m.group(1).strip(), alt_m.group(2).strip()])
                else:
                    parsed_terms.append([t])
            keywords[row["id"].strip()] = parsed_terms
    return keywords


def parse_blocks(text):
    chunks = re.split(r"\n(?=## 시드 #)", text)
    blocks = {}
    for chunk in chunks:
        m = re.match(r"## 시드 #(\d+)", chunk)
        if not m:
            continue
        seed_id = m.group(1)
        sections = re.split(r"\n### ", chunk)
        data = {"card": "", "kakao": "", "newsletter": "", "tags": ""}
        for sec in sections[1:]:
            parts = sec.split("\n", 1)
            header = parts[0]
            body = parts[1] if len(parts) > 1 else ""
            body = body.split("\n---")[0].strip()
            if "카드뉴스" in header:
                data["card"] = body
            elif "카카오메시지" in header:
                data["kakao"] = body
            elif "뉴스레터" in header:
                data["newsletter"] = body
            elif "현장 용어" in header:
                data["tags"] = body
        blocks[seed_id] = data
    return blocks


def validate(target_ids=None):
    if not CONTENT_MD.exists():
        print(f"파일 없음: {CONTENT_MD}")
        sys.exit(1)
    text = CONTENT_MD.read_text(encoding="utf-8")
    keywords_map = load_keywords()
    blocks = parse_blocks(text)

    ids = target_ids or sorted(keywords_map.keys(), key=int)
    results = []
    for seed_id in ids:
        kws = keywords_map.get(seed_id, [])
        block = blocks.get(seed_id)
        if not block:
            results.append({"id": seed_id, "kakao_len": None, "news_len": None,
                             "missing": kws, "pass": False, "note": "BLOCK MISSING"})
            continue
        kakao_len = len(block["kakao"])
        news_len = len(block["newsletter"])
        combined = " ".join([block["card"], block["kakao"], block["newsletter"]])
        missing = ["/".join(alts) for alts in kws if not any(a in combined for a in alts)]
        kakao_ok = kakao_len <= KAKAO_MAX
        news_ok = NEWSLETTER_MIN <= news_len <= NEWSLETTER_MAX
        passed = kakao_ok and news_ok and not missing
        note = []
        if not kakao_ok:
            note.append(f"카카오 {kakao_len}자 초과")
        if not news_ok:
            note.append(f"뉴스레터 {news_len}자 범위 밖")
        if missing:
            note.append(f"누락 키워드: {missing}")
        results.append({"id": seed_id, "kakao_len": kakao_len, "news_len": news_len,
                         "missing": missing, "pass": passed, "note": "; ".join(note) or "OK"})
    return results


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    target_ids = sys.argv[1:] or None
    results = validate(target_ids)
    print(f"{'id':<4}{'kakao':<8}{'news':<8}{'pass':<7}note")
    all_pass = True
    for r in results:
        if not r["pass"]:
            all_pass = False
        print(f"{r['id']:<4}{str(r['kakao_len']):<8}{str(r['news_len']):<8}{str(r['pass']):<7}{r['note']}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

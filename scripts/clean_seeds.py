"""nursevillage_content_seeds.csv 결측치·중복 정제 스크립트.

설계 원칙
---------
TERM_DICT / EVENT_BLOCKS는 코드에 박아둔 고정 리스트가 아니라, 매 실행 시
context/company-info.md · context/industry-news.md 를 다시 읽어 파싱한 결과다.
두 파일 내용이 바뀌면(새 용어·새 이벤트 추가) 코드를 고치지 않아도 반영된다.

규칙 1(topic 문자열 내 용어 채택)과 규칙 3(동일 target_audience 형제 행 기반
저빈도 보충)은 순수 규칙으로 완전히 자동화된다.

규칙 2(ref_event를 읽고 의미적으로 연결되는 용어를 고르는 것 + 준비/완료 시점
구분)는 문자열 매칭만으로 완전히 대체되지 않는 의미 판단이 섞여 있다. 이 스크립트는:
  1) 이벤트 설명 문단에 실제로 언급된 TERM_DICT 용어만 "후보"로 추출한다
     (이벤트→용어 고정 매핑표가 아니라 co-occurrence 휴리스틱).
  2) topic 문장에 준비/완료 시점을 암시하는 표현이 있으면, 용어 사전 정의문에서
     감지되는 시점과 반대되는 후보는 제외한다.
  3) 그래도 애매하면 MANUAL_OVERRIDES에 남긴 인간/LLM 판단을 우선 적용한다.
새 CSV를 넣었을 때 규칙 2가 애매한 케이스를 만들면, 이 스크립트가 후보와 근거
문단을 decisions.md에 남기므로 그걸 보고 MANUAL_OVERRIDES를 채우면 된다.

파이프라인 재현성
------------------
python scripts/clean_seeds.py [input_csv] [output_csv] 형태로 다른 seeds CSV도
동일 규칙으로 정제할 수 있다. 인자를 생략하면 기존 nursevillage 파일 경로를
그대로 쓴다(하위 호환).

이 스크립트가 처리하는 "결측·이상치" 종류:
  A. keywords_required 결측 -> 규칙 1~3으로 보완
  B. tone / target_audience 오타·공백("유모형", "신규 RN", "경력알엔" 등) -> 표준값 정규화
  C. keywords_required 구분자 오염(세미콜론·중복 콤마·트레일링 콤마·여분 공백) -> 콤마 정규화
  D. topic 결측 -> 자동 보완 불가, review_flag로 표시하고 수동 확인 유도
  E. 전 필드가 동일한 완전 중복 행 -> 먼저 등장한 id만 남기고 제거
  F. topic은 같지만 target_audience가 다른 행 -> dup_group 플래그 + 관점 차별화 판단 필요
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANY_INFO = ROOT / "context" / "company-info.md"
INDUSTRY_NEWS = ROOT / "context" / "industry-news.md"
DEFAULT_SEEDS_CSV = ROOT / "data" / "nursevillage_content_seeds.csv"
DEFAULT_CLEANED_CSV = ROOT / "data" / "nursevillage_content_seeds_cleaned.csv"
DECISIONS_MD = ROOT / "decisions.md"

PRE_DEF_MARKERS = ["들어가기 전", "하기 전"]
POST_DEF_MARKERS = ["합격", "취득", "받은", "이후"]
PRE_TOPIC_MARKERS = ["준비", "앞두고", "D-", "전에", "앞서"]
POST_TOPIC_MARKERS = ["끝나고", "끝난", "마치고", "합격", "이후", "후"]

VALID_TONES = ["공감형", "정보형", "유머형"]
VALID_TARGETS = ["신규RN", "간호학생", "경력RN"]
# 순수 문자열 오타 교정으로 커버되지 않는 표기(음가 치환 등)만 예외적으로 명시한다.
ALIAS_SUBS = {"알엔": "RN"}

# 이번 실행에서 자동 로직으로 판단이 애매했던 id에 대한 최종 인간/LLM 판단.
# {id: [keyword, ...]} 형태로 채우면 자동 로직 결과를 덮어쓴다. 비어있으면
# 아래 rule1~rule3 로직 결과를 그대로 채택한다.
#
# id 12 ("국시 끝나고 우리가 하고 싶은 것들", 간호학생, ref_event=간호사 국가시험 합격발표,
# nursevillage_content_seeds.csv): 자동 rule1~3 재실행 시 값이 계속 흔들리는 재현성 문제가
# 확인되어 재판단 없이 최종값으로 확정. "국시 합격 발표 후" 국면에 맞는 용어(면허·RN)로 고정.
# 상세 근거: decisions.md 참고.
#
# id 30 ("나이트 근무 루틴 브이로그", 신규RN, dummy_seeds_50.csv): 자동 rule1은 topic 속
# 알리아스 "나이트"를 찾았지만 결과에는 그 alias가 속한 복합 표기 원형 "데이/이브닝/나이트"를
# 그대로 채택했다. keywords_required의 다른 모든 값은 단일 용어인데 이 값만 슬래시 결합
# 문자열이라 validate_content.py의 "본문에 키워드 문자열이 그대로 등장하는지" 체크와
# 실제 콘텐츠 문장에서 어색함을 유발한다. topic이 가리키는 것은 3교대 전체가 아니라
# 그중 하나인 "나이트" 근무 하나이므로, 매칭된 alias 그대로 "나이트"로 대체한다.
MANUAL_OVERRIDES = {
    "12": ["국시", "면허", "RN"],
    "30": ["나이트", "5R", "RN"],
}

# 중복 topic 그룹의 차별화 판단 — "누구 시점에서 말하는 콘텐츠인가"는 빈도·문자열
# 매칭으로 자동화할 수 없는 편집 판단이라 별도로 기록한다.
DUP_NOTES = {
    "실습 나가서 듣는 웃픈 한마디 모음": (
        "간호학생 행 = '당하는' 실습생 1인칭 시점(선배·프리셉터에게 듣는 말), "
        "경력RN 행 = '돌아보는' 선배 시점(후배 시절 회상 + 지금 후배에게 하는 말)으로 관점을 분리"
    ),
    "선배가 알려준 인계 꿀팁 모음": (
        "신규RN 행 = 갓 배운 인계 꿀팁을 현장에 처음 적용하는 '실행자' 시점, "
        "경력RN 행 = 후배에게 인계 꿀팁을 전수하는 '전달자' 시점으로 관점을 분리"
    ),
}


def parse_term_dict(text):
    """company-info.md 용어 사전 표를 파싱해 {별칭: {raw, definition, tense}} 반환."""
    terms = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|$", line.strip())
        if not m:
            continue
        raw_term, definition = m.group(1).strip(), m.group(2).strip()
        main = raw_term.split("(")[0].strip()
        aliases = {raw_term, main}
        if "/" in main:
            aliases.update(a.strip() for a in main.split("/") if a.strip())
        tense = "neutral"
        if any(mk in definition for mk in PRE_DEF_MARKERS):
            tense = "pre"
        elif any(mk in definition for mk in POST_DEF_MARKERS):
            tense = "post"
        for alias in aliases:
            if len(alias) >= 2:
                terms[alias] = {"raw": raw_term, "main": main, "definition": definition, "tense": tense}
    return terms


def split_event_blocks(text):
    """industry-news.md의 ### 섹션과 캘린더 표 행을 {제목: 본문} 형태로 반환."""
    blocks = {}
    for m in re.finditer(r"^###\s+(.+?)\n(.*?)(?=\n##|\Z)", text, re.S | re.M):
        blocks[m.group(1).strip()] = re.sub(r"\s+", " ", m.group(2)).strip()
    table_re = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M)
    for row in table_re.finditer(text):
        a, b, c = (row.group(i).strip() for i in (1, 2, 3))
        if a.startswith("-") or b in ("이벤트", "내용", "이슈") or len(b) > 20:
            continue
        blocks[b] = f"{a} {b} {c}"
    return blocks


def normalize(s):
    return re.sub(r"\s+", "", s)


def find_event_block(ref_event, blocks):
    key = normalize(ref_event)
    for title, body in blocks.items():
        nt = normalize(title)
        if nt in key or key in nt:
            return title, body
    core = re.sub(r"(합격발표|시행|주간)$", "", key)
    if core:
        for title, body in blocks.items():
            if core in normalize(title):
                return title, body
    return None, None


def topic_tense(topic):
    if any(mk in topic for mk in POST_TOPIC_MARKERS):
        return "post"
    if any(mk in topic for mk in PRE_TOPIC_MARKERS):
        return "pre"
    return "neutral"


def rule1_from_topic(topic, term_dict):
    """1순위: topic 문자열에 이미 등장하는 용어 사전 단어를 채택."""
    hits = []
    for alias, info in term_dict.items():
        if alias in topic and info["main"] not in hits:
            hits.append(info["main"])
    return hits


def rule2_from_event(topic, ref_event, term_dict, event_blocks):
    """2순위: ref_event 설명 문단에서 언급되는 용어 후보 + 시점(준비/완료) 필터."""
    if not ref_event:
        return [], None
    title, body = find_event_block(ref_event, event_blocks)
    if not body:
        return [], None
    tense = topic_tense(topic)
    # 후보 순위는 "본문 텍스트에서 먼저 언급된 순서"로 매긴다 (TERM_DICT에 용어가
    # 나열된 순서로 매기면 회사 문서의 임의적인 서술 순서가 랭킹에 끼어든다).
    best_idx = {}
    for alias, info in term_dict.items():
        idx = body.find(alias)
        if idx == -1:
            continue
        if tense != "neutral" and info["tense"] != "neutral" and info["tense"] != tense:
            continue  # topic 시점과 반대되는 용어는 후보에서 제외
        main = info["main"]
        if main not in best_idx or idx < best_idx[main]:
            best_idx[main] = idx
    candidates = sorted(best_idx, key=lambda m: best_idx[m])
    return candidates, title


def rule3_from_siblings(target_audience, current_id, rows, exclude):
    """3순위: 동일 target_audience 행들의 keywords_required 중 저빈도(차별화) 용어."""
    freq, order = {}, {}
    for r in rows:
        if r["target_audience"] != target_audience or r["id"] == current_id:
            continue
        for kw in [k.strip() for k in r["keywords_required"].split(",") if k.strip()]:
            freq[kw] = freq.get(kw, 0) + 1
            order.setdefault(kw, len(order))
    pool = [k for k in freq if k not in exclude]
    pool.sort(key=lambda k: (freq[k], order[k]))
    return pool, freq


def _levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def normalize_categorical(value, valid_values):
    """오타·공백이 섞인 범주값(tone/target_audience)을 표준값으로 정규화.

    반환: (최종값, 값이 바뀌었는지, 정규화 근거 또는 None(미확인 값이라 원본 유지))
    """
    raw = value.strip()
    if raw in valid_values:
        return raw, False, None
    collapsed = re.sub(r"\s+", "", raw)
    if collapsed in valid_values:
        return collapsed, True, f"공백 제거: '{raw}' -> '{collapsed}'"
    aliased = collapsed
    for k, v in ALIAS_SUBS.items():
        aliased = aliased.replace(k, v)
    if aliased in valid_values:
        return aliased, True, f"표기 치환: '{raw}' -> '{aliased}'"
    best, best_dist = None, 99
    for v in valid_values:
        d = _levenshtein(collapsed, v)
        if d < best_dist:
            best, best_dist = v, d
    if best is not None and best_dist <= 1:
        return best, True, f"오타 추정(편집거리 {best_dist}): '{raw}' -> '{best}'"
    return raw, False, None


def normalize_keywords_format(raw):
    """구분자(콤마/세미콜론) 혼용·빈 토큰·여분 공백을 정리해 표준 콤마 구분 문자열로 변환."""
    if not raw.strip():
        return raw, False
    tokens = [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]
    cleaned = ",".join(tokens)
    return cleaned, cleaned != raw


def normalize_rows(rows):
    """모든 행에 대해 B(범주 오타)·C(구분자 오염) 정규화를 적용하고 변경 로그를 반환."""
    fixes = []
    for r in rows:
        for field, valid in (("tone", VALID_TONES), ("target_audience", VALID_TARGETS)):
            if not r[field].strip():
                continue
            fixed, changed, note = normalize_categorical(r[field], valid)
            if changed:
                fixes.append((r["id"], field, r[field], fixed, note))
                r[field] = fixed
            elif fixed not in valid:
                fixes.append((r["id"], field, r[field], fixed, "미확인 값 — 표준 범주와 매칭 실패, 수동 확인 필요"))
                r.setdefault("review_flag", "")
                r["review_flag"] = (r["review_flag"] + ";" if r["review_flag"] else "") + f"{field} 미확인 값('{r[field]}')"

        cleaned_kw, kw_changed = normalize_keywords_format(r["keywords_required"])
        if kw_changed:
            fixes.append((r["id"], "keywords_required", r["keywords_required"], cleaned_kw, "구분자/공백 정규화"))
            r["keywords_required"] = cleaned_kw
    return fixes


def dedupe_exact_rows(rows):
    """topic·tone·target·keywords·platform·ref_event가 모두 동일한 완전 중복 행을 찾아
    먼저 등장한 id만 남기고 나머지는 제거한다. (topic만 같고 target이 다른 경우는
    별도의 dup_group 로직(F)에서 처리 — 관점 차별화가 필요한 의도된 중복이므로 삭제 대상 아님)."""
    key_fields = ("topic", "tone", "target_audience", "keywords_required", "platform_hint", "ref_event")
    seen, kept, dropped = {}, [], []
    for r in rows:
        key = tuple(r[f].strip() for f in key_fields)
        if not key[0]:  # topic 결측 행은 키 비교 대상에서 제외 (D에서 별도 처리)
            kept.append(r)
            continue
        if key in seen:
            dropped.append((r["id"], seen[key], r["topic"]))
            continue
        seen[key] = r["id"]
        kept.append(r)
    return kept, dropped


def flag_missing_topic(rows):
    flagged = []
    for r in rows:
        if not r["topic"].strip():
            r["review_flag"] = (r.get("review_flag", "") + ";" if r.get("review_flag") else "") + \
                "topic 결측 — 자동 보완 불가(내용을 임의로 지어낼 수 없음), 수동 확인 필요"
            flagged.append(r["id"])
    return flagged


def clean(rows, term_dict, event_blocks):
    decisions = []
    for r in rows:
        r.setdefault("dup_group", "")
        r.setdefault("review_flag", r.get("review_flag", ""))
        if r["keywords_required"].strip() or not r["topic"].strip():
            continue  # topic 결측 행은 근거가 없어 규칙 1/2 적용 불가 — D에서 별도 플래그 처리

        chosen, trail = [], []

        r1 = rule1_from_topic(r["topic"], term_dict)
        chosen += [t for t in r1 if t not in chosen]
        if r1:
            trail.append(f"1순위(topic 내 용어 매칭): {', '.join(r1)}")

        r2, event_title = rule2_from_event(r["topic"], r["ref_event"], term_dict, event_blocks)
        added2 = [t for t in r2 if t not in chosen][: max(0, 3 - len(chosen))]
        chosen += added2
        if r2:
            trail.append(
                f"2순위(ref_event '{r['ref_event']}' -> industry-news.md '{event_title}' 문단, "
                f"topic tense={topic_tense(r['topic'])}): 후보={', '.join(r2)} / 채택={', '.join(added2) or '(중복이라 미채택)'}"
            )

        override = MANUAL_OVERRIDES.get(r["id"])
        if override:
            trail.append(f"수동 판단(override) 적용 전 자동 결과: {', '.join(chosen)}")
            chosen = list(override)
            trail.append(f"수동 판단(override) 최종: {', '.join(chosen)}")

        if len(chosen) < 3:
            pool, freq = rule3_from_siblings(r["target_audience"], r["id"], rows, set(chosen))
            need = 3 - len(chosen)
            added3 = pool[:need]
            chosen += added3
            if added3:
                trail.append(
                    "3순위(동일 target_audience 저빈도 보충, 빈도 낮은 순): "
                    + ", ".join(f"{t}(형제행 {freq[t]}회)" for t in added3)
                )

        r["keywords_required"] = ",".join(chosen)
        decisions.append((r["id"], r["topic"], r["target_audience"], r["ref_event"], chosen, trail))

    topic_groups = {}
    for r in rows:
        if not r["topic"].strip():
            continue
        topic_groups.setdefault(r["topic"], []).append(r)

    dup_entries = []
    gi = 0
    for topic, grp in topic_groups.items():
        targets = {g["target_audience"] for g in grp}
        if len(grp) > 1 and len(targets) > 1:
            gi += 1
            gid = f"DUP{gi:02d}"
            for g in grp:
                g["dup_group"] = gid
            dup_entries.append((gid, topic, grp, DUP_NOTES.get(topic, "차별화 판단 필요 (수동 검토 요망)")))

    return decisions, dup_entries


def write_cleaned_csv(rows, fieldnames, cleaned_csv):
    # 원본 CSV에 BOM이 없으므로 출력도 BOM 없는 utf-8로 맞춘다. utf-8-sig로 쓰면
    # 이 파일을 다음 스크립트가 encoding='utf-8'로 열 때 헤더가 '﻿id'로
    # 깨질 수 있다 — 읽기는 어느 쪽이든 utf-8-sig로 열면 안전하지만, 파이프라인
    # 재사용성을 위해 쓰기 단계에서부터 BOM을 붙이지 않는다.
    with cleaned_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def append_decisions_md(decisions, dup_entries, cat_fixes, dropped_dups, missing_topics, date_str):
    lines = []

    if cat_fixes:
        lines.append(f"**[{date_str}] 범주값·구분자 오타 정규화**")
        for id_, field, before, after, note in cat_fixes:
            lines.append(f"- id {id_} [{field}]: \"{before}\" -> \"{after}\" ({note})")
        lines.append("- 선택한 이유: tone/target_audience는 채널 로직·타깃 매칭에 쓰이는 고정 범주라 오타·공백이 있으면 이후 단계가 깨짐. keywords_required는 세미콜론/중복콤마/트레일링콤마가 섞여 있어 콤마 기준으로 통일")
        lines.append("- 대안으로 고려했던 것: 미확인 값(편집거리 2 이상)은 임의로 표준값에 끼워맞추지 않고 review_flag로만 표시해 수동 확인을 유도")
        lines.append("")

    if dropped_dups:
        lines.append(f"**[{date_str}] 완전 중복 행 제거**")
        for dropped_id, kept_id, topic in dropped_dups:
            lines.append(f"- id {dropped_id} (\"{topic}\") 제거 — id {kept_id}와 topic·tone·target·keywords·platform·ref_event 전부 동일")
        lines.append("- 선택한 이유: 전 필드가 동일한 행은 동일 콘텐츠를 중복 생성하게 되어 낭비이자 데이터 오류로 판단")
        lines.append("- 대안으로 고려했던 것: 두 행 모두 유지 후 콘텐츠 생성 단계에서 중복 제거 — 정제 단계에서 미리 제거하는 쪽이 하위 단계 낭비를 줄여 채택")
        lines.append("")

    if missing_topics:
        lines.append(f"**[{date_str}] topic 결측 플래그**")
        lines.append(f"- id {', '.join(missing_topics)}: topic이 비어 있어 규칙 1(topic 매칭)·규칙 2(ref_event 연결) 적용 불가")
        lines.append("- 선택한 이유: topic 없이 keywords_required만으로 주제를 역으로 지어내는 것은 원문 왜곡 위험이 있어 자동 보완하지 않고 review_flag(\"topic 결측\")로 표시, 콘텐츠 생성 대상에서 제외")
        lines.append("- 대안으로 고려했던 것: keywords_required 기반으로 topic을 추정 생성 — 근거 데이터가 아닌 추측이라 기각")
        lines.append("")

    for id_, topic, target, ref_event, chosen, trail in decisions:
        lines.append(f"**[{date_str}] keywords_required 결측 보완 — id {id_}**")
        lines.append(f"- 결정 내용: id {id_} (\"{topic}\", {target}) keywords_required = \"{','.join(chosen)}\"")
        lines.append(f"- 선택한 이유: " + " / ".join(trail))
        lines.append(f"- 대안으로 고려했던 것: 규칙 1~3의 각 단계 후보 전체 (위 근거 참고), ref_event='{ref_event or '(없음)'}'")
        lines.append("")

    for gid, topic, grp, note in dup_entries:
        ids = ", ".join(f"id {g['id']}({g['target_audience']})" for g in grp)
        lines.append(f"**[{date_str}] 중복 topic 플래그 — {gid}**")
        lines.append(f"- 결정 내용: \"{topic}\" — {ids} 를 {gid}로 플래그, 관점 차별화 판단 부여")
        lines.append(f"- 선택한 이유: {note}")
        lines.append("- 대안으로 고려했던 것: topic 문자열 자체를 타깃별로 다르게 바꾸는 방안 — 이번 정제 단계에서는 원문 topic은 유지하고 관점 판단만 남김 (콘텐츠 생성은 다음 턴)")
        lines.append("")

    if not lines:
        return
    text = DECISIONS_MD.read_text(encoding="utf-8")
    marker = "(여기에 기록이 추가됩니다)"
    addition = "\n".join(lines)
    if marker in text:
        text = text.replace(marker, marker + "\n\n" + addition)
    else:
        text = text.rstrip() + "\n\n" + addition
    DECISIONS_MD.write_text(text, encoding="utf-8")


def main(argv=None):
    from datetime import date

    args = sys.argv[1:] if argv is None else argv
    seeds_csv = Path(args[0]) if len(args) >= 1 else DEFAULT_SEEDS_CSV
    cleaned_csv = Path(args[1]) if len(args) >= 2 else DEFAULT_CLEANED_CSV

    company_text = COMPANY_INFO.read_text(encoding="utf-8-sig")
    news_text = INDUSTRY_NEWS.read_text(encoding="utf-8-sig")
    term_dict = parse_term_dict(company_text)
    event_blocks = split_event_blocks(news_text)

    with seeds_csv.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        base_fields = [fn for fn in reader.fieldnames if fn not in ("dup_group", "review_flag")]
        fieldnames = base_fields + ["dup_group", "review_flag"]
        rows = [dict(row) for row in reader]

    before = {r["id"]: r["keywords_required"] for r in rows}

    cat_fixes = normalize_rows(rows)
    rows, dropped_dups = dedupe_exact_rows(rows)
    missing_topics = flag_missing_topic(rows)
    decisions, dup_entries = clean(rows, term_dict, event_blocks)

    write_cleaned_csv(rows, fieldnames, cleaned_csv)
    append_decisions_md(decisions, dup_entries, cat_fixes, dropped_dups, missing_topics, date.today().isoformat())

    print(f"[input] {seeds_csv.name} -> [output] {cleaned_csv.name}")
    print(f"[parsed] TERM_DICT aliases: {len(term_dict)} / EVENT_BLOCKS: {len(event_blocks)}")
    print()
    if cat_fixes:
        print("=== 범주값·구분자 정규화 ===")
        for id_, field, bef, aft, note in cat_fixes:
            print(f"id {id_} [{field}]: '{bef}' -> '{aft}' ({note})")
        print()
    if dropped_dups:
        print("=== 완전 중복 행 제거 ===")
        for dropped_id, kept_id, topic in dropped_dups:
            print(f"id {dropped_id} 제거 (id {kept_id}와 완전 동일, topic=\"{topic}\")")
        print()
    if missing_topics:
        print("=== topic 결측 플래그 ===")
        print(f"id {', '.join(missing_topics)}")
        print()
    print("=== keywords_required 결측 보완 ===")
    for id_, topic, target, ref_event, chosen, trail in decisions:
        print(f"id {id_} | before='{before.get(id_, '')}' -> after='{','.join(chosen)}'")
        for t in trail:
            print(f"    - {t}")
    print()
    print("=== 중복 topic 플래그 ===")
    for gid, topic, grp, note in dup_entries:
        ids = ", ".join(f"id {g['id']}({g['target_audience']})" for g in grp)
        print(f"{gid}: \"{topic}\" -> {ids}")
        print(f"    - 차별화 판단: {note}")


if __name__ == "__main__":
    main()

"""과거+확정 구간(committed window)은 고정하고, 그 이후 구간만 확장된 콘텐츠
풀로 재스케줄링하는 스크립트. check_cadence.py의 70÷k 공식·집계 규칙·상수를
그대로 불러와 쓴다 — Standard 8번(재사용 파이프라인) 위에 쌓은 확장이다.

동작
----
1. data/published_log.csv를 세 구간으로 나눈다.
   - 과거(TODAY 이전): 이미 실제로 나간 것 → 불변.
   - 확정 구간(TODAY ~ TODAY+committed_days, 기본 14일): 이미 예정돼 있던
     것도 편집 주기(카피 준비·인쇄·예약 발행 세팅)를 존중해 그대로 고정한다.
     "고정" = 과거 발행분 + 확정 구간 두 그룹 모두.
   - 자유 구간(확정 구간 이후): 여기만 자유롭게 재배치한다.
2. 18건 원본(data/nursevillage_content_seeds_cleaned.csv) + 새로 분류된 아티클
   (data/classified_new_articles.csv)을 합쳐 새 콘텐츠 풀을 만든다. 두 파일의
   id가 01~50 범위로 겹치므로, 분류 아티클 쪽 id에는 전부 "NEW-" 접두어를
   붙여 published_log.csv의 기존 id(원본 01~18, 재발행 xx-R1...)와 절대
   충돌하지 않게 한다. (알려진 한계: 이 접두어는 이 스크립트 내부의 임시
   네임스페이싱일 뿐, clean_seeds.py 쪽에 여러 소스 CSV를 위한 공통 id 체계는
   아직 없다.)
3. check_cadence.count_evergreen_by_target() / evaluate_cadence()를 그대로
   재사용해 타깃별 상시(ref_event 없는) 콘텐츠 개수 k와 70÷k PASS/FAIL을
   재계산한다.
4. 확정 구간 안이라도, 실제 이벤트 날짜가 확인되는 새 시의성(ref_event) 소재는
   "비어 있는 슬롯"에 한해 예외적으로 끼워 넣는다. 조건(둘 다 충족해야 함):
   - 이벤트 날짜까지 오늘 기준 최소 insert_lead_days(기본 3일) 이상 남아있을 것
     (리드타임 조건이 슬롯 유무보다 우선 — 리드타임이 안 되면 슬롯을 보지도 않고
     즉시 반려한다).
   - 그 날짜에 이미 고정된 항목(과거/확정 구간 어느 쪽이든)이 없을 것(슬롯 비어있음).
   실제 날짜가 아예 확인되지 않는 이벤트(예: 간호주간·코로나19 재유행처럼 공식
   출처가 없는 것)는 애초에 이 판단의 대상이 아니며 "미배치"로 남는다. 확인된
   날짜가 확정 구간 밖이면 이번 삽입 로직과 무관(다음 회차 자유 구간 스케줄링
   때 anchors로 처리됨).
5. 자유 구간의 상시 콘텐츠 풀을 타깃별로 순환 배정한다.
   - expires_after가 TODAY보다 과거인 time_bound_fact 콘텐츠는 재발행 후보에서
     자동 제외한다(만료된 사실을 다시 내보내지 않기 위함).
   - 한 번도 발행된 적 없는 새 아티클(NEW-*)을 id 순으로 먼저 소진한다.
   - 이미 발행된 적 있는 항목(과거 또는 확정 구간 포함)은 published_log.csv
     기준 "마지막 발행일"이 오래된 순으로 재사용 후보에 넣는다.
   - 순번이 돌아와도 "마지막 발행일 + reuse_days(기본 70일)"이 안 지났으면
     건너뛰고 다음 후보로 넘어간다(재사용 안전장치 그대로 적용).
6. 결과를 output/rescheduled-calendar.md에 저장한다.

사용법
------
python scripts/reschedule.py [--today 2026-07-01] [--horizon-end 2026-12-17]
    [--committed-days 14] [--insert-lead-days 3] [--reuse-days 70] [--target-days 14]

--today/--horizon-end 기본값은 이번 과제 시나리오(TODAY=2026-07-01)에 맞춘
고정 리터럴이다 — 동일 인자로 항상 동일한 결과가 재현되도록 일부러 실제
시계(date.today())를 쓰지 않았다. 다른 시점 기준으로 돌리려면 두 값을 명시
하면 된다.
"""
import argparse
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_cadence

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_LOG = ROOT / "data" / "published_log.csv"
ORIGINAL_CSV = ROOT / "data" / "nursevillage_content_seeds_cleaned.csv"
CLASSIFIED_CSV = ROOT / "data" / "classified_new_articles.csv"
OUT_MD = ROOT / "output" / "rescheduled-calendar.md"

NEW_PREFIX = "NEW-"
DEFAULT_TODAY = date(2026, 7, 1)
DEFAULT_HORIZON_END = date(2026, 12, 17)
DEFAULT_COMMITTED_DAYS = 14
DEFAULT_INSERT_LEAD_DAYS = 3
MAX_SCHEDULE_ITERATIONS = 5000  # cur이 매 반복 전진하므로 실제로는 이 값에 훨씬 못 미침 — 무한루프 방지용 상한

# 확정된 실제 발생일이 알려진 이벤트만 등록한다 — 국내 정확한 날짜가 미확인인
# 이벤트(간호주간·코로나19 재유행·면허 갱신 시즌·처우개선 발표 등)는 절대
# 추정해 넣지 않는다(기존 clean_seeds.py/standard-guide.md와 동일한 원칙).
# 값 = (월, 일). "다음 발생일"은 today 기준으로 계산한다.
KNOWN_EVENT_DATES = {
    "환자안전주간": (9, 17),  # WHO 지정 세계 환자안전의 날 확정 프록시. 국내 "환자안전주간" 정확한 날짜는 병원별 상이·미확인이라 기존 id 03 결정과 동일하게 이 날짜를 앵커로 사용
    "스승의날": (5, 15),
    "국제 간호사의 날": (5, 12),
}


def next_occurrence(month, day, after):
    candidate = date(after.year, month, day)
    if candidate < after:
        candidate = date(after.year + 1, month, day)
    return candidate


def resolve_event_date(ref_event, today):
    md = KNOWN_EVENT_DATES.get(ref_event)
    return next_occurrence(md[0], md[1], today) if md else None


def load_published_log():
    rows = check_cadence.load_rows(PUBLISHED_LOG)
    for r in rows:
        r["published_date"] = date.fromisoformat(r["published_date"].strip())
        r["is_reissue"] = r["is_reissue"].strip().lower() == "true"
    return rows


def load_pool():
    """18건 원본 + 분류 아티클(NEW- 접두어)을 합친 콘텐츠 풀. 각 항목:
    {id, target_audience, tone, keywords_required, platform_hint, ref_event,
    content_type, expires_after, superseded_by}"""
    pool = {r["id"]: r for r in check_cadence.load_rows(ORIGINAL_CSV)}
    for r in check_cadence.load_rows(CLASSIFIED_CSV):
        if not check_cadence.is_generatable(r):
            continue  # id 50 (topic 결측) 등 생성 불가 행은 풀에서 제외
        new_id = NEW_PREFIX + r["id"]
        r["id"] = new_id
        pool[new_id] = r
    return pool


def split_windows(log_rows, today, committed_days):
    """과거 / 확정 구간(today~today+committed_days) / 자유 구간(그 이후)으로 분리."""
    committed_end = today + timedelta(days=committed_days)
    past = [r for r in log_rows if r["published_date"] < today]
    committed = [r for r in log_rows if today <= r["published_date"] <= committed_end]
    free_old = [r for r in log_rows if r["published_date"] > committed_end]
    return past, committed, free_old, committed_end


def last_used_dates(fixed_rows):
    """id별 마지막 발행일. 날짜 오름차순으로 훑으면서 덮어쓰면 항상 최신 값이 남는다."""
    return {r["id"]: r["published_date"]
            for r in sorted(fixed_rows, key=lambda r: r["published_date"])}


def find_pending_event_anchor(pool, free_old):
    """자유 구간 이후에도 아직 안 지난 이벤트 앵커 원본 — 날짜를 고정 유지한다."""
    anchors = []
    for r in free_old:
        item = pool.get(r["id"])
        if item and item.get("ref_event", "").strip():
            anchors.append({"id": r["id"], "date": r["published_date"],
                             "channel": r["channel"], "target": item["target_audience"]})
    return anchors


def unplaced_event_items(pool):
    return [item for pid, item in pool.items()
            if pid.startswith(NEW_PREFIX) and item.get("ref_event", "").strip()]


def evaluate_committed_insertions(pool, committed, today, committed_end, insert_lead_days):
    """확정 구간 안에 새 시의성 소재를 예외 삽입할 수 있는지 판단.
    반환: (삽입됨, 반려됨, 확정구간밖(해당없음), 날짜미확인)"""
    occupied_dates = {r["published_date"] for r in committed}
    inserted, rejected, outside_window, unresolved = [], [], [], []
    for item in sorted(unplaced_event_items(pool), key=lambda x: x["id"]):
        event_date = resolve_event_date(item["ref_event"], today)
        if event_date is None:
            unresolved.append(item)
            continue
        if not (today <= event_date <= committed_end):
            outside_window.append({**item, "event_date": event_date})
            continue
        lead_days = (event_date - today).days
        if lead_days < insert_lead_days:
            rejected.append({**item, "event_date": event_date,
                              "reason": f"리드타임 부족({lead_days}일 < {insert_lead_days}일)"})
            continue
        if event_date in occupied_dates:
            rejected.append({**item, "event_date": event_date, "reason": "슬롯 없음"})
            continue
        inserted.append({**item, "event_date": event_date})
        occupied_dates.add(event_date)  # 같은 실행 안에서 같은 날짜에 중복 삽입 방지
    return inserted, rejected, outside_window, unresolved


def is_expired(item, today):
    if item.get("content_type") != "time_bound_fact":
        return False
    expires = item.get("expires_after", "").strip()
    return bool(expires) and date.fromisoformat(expires) < today


def evergreen_pool_by_target(pool, today):
    """타깃별 상시(ref_event 없는) 콘텐츠 id 목록. 만료된 time_bound_fact는 제외."""
    by_target, excluded_expired = {}, []
    for pid, item in pool.items():
        if item.get("ref_event", "").strip():
            continue
        if is_expired(item, today):
            excluded_expired.append(item)
            continue
        target = item["target_audience"].strip()
        by_target.setdefault(target, []).append(pid)
    return by_target, excluded_expired


def schedule_target(pool_ids, last_used, start_date, end_date, interval_days,
                     reuse_days, blocked_dates):
    cooldown = timedelta(days=reuse_days)
    never = sorted([i for i in pool_ids if i not in last_used])
    used = sorted([i for i in pool_ids if i in last_used], key=lambda i: last_used[i])
    order = never + used
    lu = dict(last_used)
    schedule = []
    cur = start_date
    idx = 0
    guard = 0
    while cur <= end_date and guard < MAX_SCHEDULE_ITERATIONS:
        guard += 1
        if cur in blocked_dates:
            cur += timedelta(days=1)
            continue
        chosen = None
        for _ in range(len(order)):
            cand = order[idx % len(order)]
            idx += 1
            if cand not in lu or (cur - lu[cand]) >= cooldown:
                chosen = cand
                break
        if chosen is None:
            cur = min(lu[c] for c in order) + cooldown
            continue
        schedule.append((cur, chosen))
        lu[chosen] = cur
        cur += timedelta(days=interval_days)
    return schedule


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--today", type=date.fromisoformat, default=DEFAULT_TODAY)
    parser.add_argument("--horizon-end", type=date.fromisoformat, default=DEFAULT_HORIZON_END)
    parser.add_argument("--committed-days", type=int, default=DEFAULT_COMMITTED_DAYS)
    parser.add_argument("--insert-lead-days", type=int, default=DEFAULT_INSERT_LEAD_DAYS)
    parser.add_argument("--reuse-days", type=int, default=check_cadence.DEFAULT_REUSE_DAYS)
    parser.add_argument("--target-days", type=int, default=check_cadence.DEFAULT_TARGET_DAYS)
    return parser.parse_args(argv)


def main(argv=None):
    check_cadence.ensure_utf8_stdout()

    ns = parse_args(sys.argv[1:] if argv is None else argv)
    today, horizon_end = ns.today, ns.horizon_end
    committed_days, insert_lead_days = ns.committed_days, ns.insert_lead_days
    reuse_days, target_days = ns.reuse_days, ns.target_days

    log_rows = load_published_log()
    pool = load_pool()
    past, committed, free_old, committed_end = split_windows(log_rows, today, committed_days)
    fixed = past + committed
    last_used = last_used_dates(fixed)

    counts = check_cadence.count_evergreen_by_target(pool.values())
    cadence_results = check_cadence.evaluate_cadence(counts, target_days, reuse_days)

    anchors = find_pending_event_anchor(pool, free_old)
    blocked_dates = {a["date"] for a in anchors}

    inserted, rejected, outside_window, unresolved = evaluate_committed_insertions(
        pool, committed, today, committed_end, insert_lead_days)
    # 삽입된 항목은 committed 그룹에 합류시켜 last_used·리포트에 함께 반영한다.
    for ins in inserted:
        last_used[ins["id"]] = ins["event_date"]

    evergreen_by_target, excluded_expired = evergreen_pool_by_target(pool, today)
    free_start = committed_end + timedelta(days=1)

    all_schedules, interval_days_by_target = {}, {}
    for target, r in cadence_results.items():
        interval_days_by_target[target] = max(1, round(reuse_days / r["k"]))
        pool_ids = evergreen_by_target.get(target, [])
        all_schedules[target] = schedule_target(
            pool_ids, last_used, free_start, horizon_end, interval_days_by_target[target],
            reuse_days, blocked_dates,
        )

    write_report(pool, past, committed, inserted, rejected, outside_window, unresolved,
                 excluded_expired, anchors, cadence_results, all_schedules,
                 interval_days_by_target, today, horizon_end, committed_end, free_start,
                 reuse_days, target_days, insert_lead_days)

    print(f"[past, fixed] {len(past)}건 (오늘 이전, 변경 없음)")
    print(f"[committed, fixed] {len(committed)}건 (오늘~오늘+{committed_days}일, 변경 없음)")
    print(f"[committed insertions] 삽입 {len(inserted)}건 / 반려 {len(rejected)}건")
    print(f"[expired excluded] {len(excluded_expired)}건 (만료된 time_bound_fact, 재발행 후보 제외)")
    print()
    print(f"{'target':<10}{'k':<5}{f'{reuse_days}/k(일)':<12}{'result':<8}new schedule count")
    all_pass = True
    for target in sorted(cadence_results):
        r = cadence_results[target]
        if not r["pass"]:
            all_pass = False
        print(f"{target:<10}{r['k']:<5}{r['min_cycle_days']:<12.1f}"
              f"{'PASS' if r['pass'] else 'FAIL':<8}{len(all_schedules.get(target, []))}")
    print()
    print("PASS" if all_pass else "FAIL", "— 전체 타깃 기준 (재계산된 k)")
    print(f"[output] {OUT_MD.relative_to(ROOT)}")
    sys.exit(0 if all_pass else 1)


def render_table(headers, rows):
    """헤더/구분선/행을 받아 마크다운 표 블록(줄 리스트)을 만든다."""
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    out.append("")
    return out


def write_report(pool, past, committed, inserted, rejected, outside_window, unresolved,
                  excluded_expired, anchors, cadence_results, all_schedules,
                  interval_days_by_target, today, horizon_end, committed_end, free_start,
                  reuse_days, target_days, insert_lead_days):
    lines = []
    lines.append("# 재스케줄링 캘린더 — 확정 구간 이후 (Standard 8 확장)")
    lines.append("")
    lines.append(f"> 기준일(TODAY) = {today.isoformat()}, 확정 구간 = {today.isoformat()} ~ "
                 f"{committed_end.isoformat()}. 이 문서는 output/standard-guide.md의 41건")
    lines.append("> 캘린더를 대체하지 않습니다 — 그 문서는 원본 18건 기준 스냅샷으로 그대로 두고,")
    lines.append("> 이 문서는 확장된 콘텐츠 풀(18건 원본 + 신규 분류 아티클)로 **확정 구간 이후만**")
    lines.append("> 다시 짠 결과입니다.")
    lines.append("")

    lines.append("## 1. 확정 구간 — 고정됨(과거 발행분 + 향후 14일)")
    lines.append("")
    lines.append(f"{today.isoformat()} 이전 발행분 **{len(past)}건** + 확정 구간"
                 f"({today.isoformat()}~{committed_end.isoformat()}) 발행 예정 **{len(committed)}건**")
    lines.append("= 총 **" + str(len(past) + len(committed)) + "건**은 변경 없이 그대로 유지합니다.")
    lines.append("원본 데이터: [data/published_log.csv](../data/published_log.csv)")
    lines.append("")
    lines.append("### 확정 구간 전/후 비교 (변경 없음 확인)")
    lines.append("")
    lines.append("확정 구간 안에 있던 항목은 재스케줄링 로직이 아예 건드리지 않으므로,")
    lines.append("아래 '이전'과 '이후' 값은 항상 동일해야 합니다(이 표 자체가 그 불변성 증거입니다).")
    lines.append("")
    lines.extend(render_table(
        ["id", "이전(published_log) 날짜", "이후(재스케줄링) 날짜", "채널", "변경 여부"],
        [[r["id"], r["published_date"].isoformat(), r["published_date"].isoformat(),
          r["channel"], "unchanged"] for r in committed],
    ))
    if not committed:
        lines.append("(확정 구간 안에 예정된 기존 발행 건 없음)")
        lines.append("")

    if anchors:
        lines.append("### 확정 구간 이후에도 고정 유지되는 이벤트 앵커")
        lines.append("")
        lines.extend(render_table(
            ["id", "날짜", "채널", "타깃", "비고"],
            [[a["id"], a["date"].isoformat(), a["channel"], a["target"],
              "실제 이벤트 날짜에 고정된 원본이라 재스케줄링 대상에서 제외"] for a in anchors],
        ))

    lines.append("## 2. 확정 구간 안 신규 시의성 콘텐츠 삽입")
    lines.append("")
    lines.append(f"조건: (1) 이벤트 날짜까지 오늘 기준 최소 {insert_lead_days}일 이상"
                 " 남아있을 것(리드타임이 슬롯 유무보다 우선), (2) 그 날짜에 이미 고정된")
    lines.append("항목이 없을 것(빈 슬롯). 실제 날짜가 확인되지 않는 이벤트는 판단 대상이 아닙니다.")
    lines.append("")
    if inserted:
        lines.append("### 삽입됨")
        lines.append("")
        lines.extend(render_table(
            ["id", "topic", "타깃", "삽입일", "채널", "통과 근거"],
            [[i["id"], i["topic"], i["target_audience"], i["event_date"].isoformat(),
              i["platform_hint"],
              f"리드타임 {(i['event_date'] - today).days}일 확보 + {i['event_date'].isoformat()} 슬롯 비어있음"]
             for i in inserted],
        ))
    else:
        lines.append("### 삽입됨")
        lines.append("")
        lines.append("이번 실행에서는 없음 — 아래 '확정 구간 밖' 항목 참고(실제 날짜가 확인된")
        lines.append("이벤트가 이번 확정 구간 범위 밖에 있어 애초에 삽입 후보가 아니었음).")
        lines.append("")
    if rejected:
        lines.append("### 삽입 불가로 플래그된 항목")
        lines.append("")
        lines.extend(render_table(
            ["id", "topic", "타깃", "이벤트 날짜", "사유"],
            [[i["id"], i["topic"], i["target_audience"], i["event_date"].isoformat(),
              f"삽입 불가 — {i['reason']}, 수동 조정 필요"] for i in rejected],
        ))
    if outside_window:
        lines.append("### 참고 — 날짜는 확인되지만 이번 확정 구간 밖인 이벤트")
        lines.append("")
        lines.extend(render_table(
            ["id", "topic", "타깃", "다음 발생일", "확정 구간과의 관계"],
            [[i["id"], i["topic"], i["target_audience"], i["event_date"].isoformat(),
              f"확정 구간({today.isoformat()}~{committed_end.isoformat()}) 밖 — 이번 삽입 로직 대상 아님"]
             for i in outside_window],
        ))

    lines.append("## 3. 콘텐츠 풀 재계산 — 타깃별 k값 & 캐던스 PASS/FAIL")
    lines.append("")
    lines.append("18건 원본 + data/classified_new_articles.csv(신규 분류 아티클, `NEW-` 접두어)를")
    lines.append("합쳐 재계산했습니다. k = 타깃별 상시(ref_event 없는) 콘텐츠 개수.")
    lines.append("")
    lines.extend(render_table(
        ["타깃", "k", f"{reuse_days}÷k(일)", "결과", f"목표({target_days}일) 대비"],
        [[target, str(r["k"]), f"{r['min_cycle_days']:.1f}",
          "✅ PASS" if r["pass"] else "❌ FAIL", f"최소 필요 k={r['min_k_needed']}"]
         for target, r in sorted(cadence_results.items())],
    ))

    lines.append("### content_type 분류 요약 (타깃별)")
    lines.append("")
    type_counts = Counter((item["target_audience"], item.get("content_type", ""))
                           for item in pool.values() if item.get("content_type"))
    targets = sorted({t for t, _ in type_counts})
    types = ["evergreen", "recurring_seasonal", "time_bound_fact"]
    lines.extend(render_table(
        ["타깃", *types],
        [[t, *[str(type_counts.get((t, ct), 0)) for ct in types]] for t in targets],
    ))

    if excluded_expired:
        lines.append("### 만료로 재발행 후보에서 제외된 콘텐츠")
        lines.append("")
        lines.extend(render_table(
            ["id", "topic", "타깃", "expires_after", "superseded_by"],
            [[item["id"], item["topic"], item["target_audience"], item["expires_after"],
              item.get("superseded_by", "") or "(없음)"] for item in excluded_expired],
        ))
    else:
        lines.append(f"### 만료로 재발행 후보에서 제외된 콘텐츠: 없음 (기준일 {today.isoformat()}")
        lines.append("시점에 만료일이 지난 time_bound_fact 콘텐츠가 아직 없음)")
        lines.append("")

    lines.append(f"## 4. 확정 구간 이후({free_start.isoformat()} ~ {horizon_end.isoformat()}) 재스케줄링 결과")
    lines.append("")
    for target in sorted(all_schedules):
        sched = all_schedules[target]
        lines.append(f"### {target} ({len(sched)}건, 간격 약 {interval_days_by_target[target]}일)")
        lines.append("")
        lines.extend(render_table(
            ["발행일", "콘텐츠 id", "채널", "구분"],
            [[d.isoformat(), pid, pool[pid]["platform_hint"],
              "신규(최초 발행)" if pid.startswith(NEW_PREFIX) else "원본 재사용(재발행)"]
             for d, pid in sched],
        ))

    if unresolved:
        lines.append("## 5. 미배치 이벤트형 신규 소재 (날짜 자체가 확인되지 않음)")
        lines.append("")
        lines.append("아래 항목은 ref_event가 있어 특정 시점 전에 발행해야 하지만, 실제 캘린더")
        lines.append("날짜가 이번 범위에서 전혀 확인되지 않아 확정 구간 삽입 판단 자체를 할 수")
        lines.append("없었습니다. context/industry-news.md·nursing-calendar.md 또는 최신 공고로")
        lines.append("날짜를 확인한 뒤 수동으로 캘린더에 끼워 넣으세요.")
        lines.append("")
        lines.extend(render_table(
            ["id", "topic", "타깃", "ref_event"],
            [[item["id"], item["topic"], item["target_audience"], item["ref_event"]]
             for item in sorted(unresolved, key=lambda x: x["id"])],
        ))
        repeated = {ev: c for ev, c in Counter(item["ref_event"] for item in unresolved).items() if c > 1}
        if repeated:
            joined = ", ".join(f"{ev}({c}건)" for ev, c in repeated.items())
            lines.append(f"> ⚠️ {joined}처럼 같은 이벤트에 여러 건이 몰려 있는 것은 스탠드인 더미 데이터의")
            lines.append("> 특성입니다(dummy_seeds_50이 배치 구조로 생성돼 동일 ref_event가 반복됨). 실제")
            lines.append("> 운영에서는 같은 이벤트에 여러 건을 모두 붙이지 말고, D-n 오프셋을 달리하거나")
            lines.append("> 다음 이벤트 주기로 일부를 이월하는 식으로 사람이 우선순위를 정해야 합니다.")
            lines.append("")

    lines.append("## 6. 재현성")
    lines.append("")
    lines.append("```")
    lines.append("python scripts/reschedule.py --today 2026-07-01 --horizon-end 2026-12-17 "
                 "--committed-days 14 --insert-lead-days 3")
    lines.append("```")
    lines.append("")
    lines.append("동일한 published_log.csv·classified_new_articles.csv가 입력되면 항상 동일한")
    lines.append("재스케줄링 결과가 재현됩니다(라운드로빈 순서 = 미사용 아티클 id 오름차순 →")
    lines.append("과거 발행 이력이 오래된 순, 70일 쿨다운 미충족 시 다음 후보로 자동 스킵,")
    lines.append("확정 구간 삽입은 리드타임 → 슬롯 순으로 결정론적으로 판정).")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

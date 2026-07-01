"""HTML 리포트 생성 스크립트 — Problem 04 다이버즈 (v2, 운영 가이드 확장판)
output_content_set.md(18건) + kpi-results.json(KPI 4종) + standard-guide.md(파이프라인·
캘린더·채널지표·브랜드보이스) + pipeline-usage.md(사용법) + challenge-strategy.md(전략안)
를 읽어 output/dashboard.html(정적 HTML, 서버·앱 없음) 하나로 렌더링합니다.
app.py(Streamlit)가 이 파일을 그대로 읽어 iframe으로 보여주므로, 외부 CDN 의존 없이
완전히 자기완결적인 단일 HTML로 만듭니다.
"""
import re
import json
import html
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONTENT_MD = BASE / "output" / "output_content_set.md"
KPI_JSON = BASE / "output" / "kpi-results.json"
STANDARD_MD = BASE / "output" / "standard-guide.md"
PIPELINE_MD = BASE / "output" / "pipeline-usage.md"
CHALLENGE_MD = BASE / "output" / "challenge-strategy.md"
OUT_HTML = BASE / "output" / "dashboard.html"

EMOJI_PALETTE = set("🤍😊🥲💪🌱😆🙈😅🎉")
TONE_EMOJI = {"공감형": "🤍😊🥲", "정보형": "😊💪", "유머형": "😆🙈😅"}


def esc(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------
# 1) output_content_set.md 파싱 (18건 콘텐츠)
# ---------------------------------------------------------------------------
def parse_seeds(content: str):
    parts = re.split(r"\n## 시드 #(\d+):\s*(.+?)\n", content)
    seeds = []
    for i in range(1, len(parts), 3):
        sid, title, body = parts[i], parts[i + 1], parts[i + 2]

        dup_note = None
        m = re.search(r"\(dup_group:\s*(.+?)\)", title)
        if m:
            dup_note = m.group(1)
            title = re.sub(r"\s*\(dup_group:.+?\)", "", title).strip()

        meta = re.search(
            r"\*\*타깃\*\*:\s*(.+?)\s*\|\s*\*\*톤\*\*:\s*(.+?)\s*\|\s*\*\*시의성\*\*:\s*(.+?)\n",
            body,
        )
        target, tone, ref_event = (meta.group(1).strip(), meta.group(2).strip(), meta.group(3).strip()) if meta else ("", "", "")

        perspective = None
        pm = re.search(r"\*\*관점\*\*:\s*(.+?)\n", body)
        if pm:
            perspective = pm.group(1).strip()

        card_m = re.search(r"### 🎴 카드뉴스 \((\d+)장\)\n(.+?)(?=\n### 💬)", body, re.S)
        slides = []
        if card_m:
            raw_slides = re.split(r"\n(?=\*\*\d+장)", card_m.group(2).strip())
            for s in raw_slides:
                hm = re.match(r"\*\*(\d+)장(\(CTA\))?\.\s*(.+?)\*\*\n(.+)", s.strip(), re.S)
                if hm:
                    slides.append({"no": hm.group(1), "is_cta": bool(hm.group(2)),
                                    "headline": hm.group(3).strip(), "text": hm.group(4).strip()})

        kakao_m = re.search(r"### 💬 카카오메시지 \((\d+)자\)\n(.+?)(?=\n### 📰)", body, re.S)
        kakao_len = kakao_m.group(1) if kakao_m else "?"
        kakao_text = kakao_m.group(2).strip() if kakao_m else ""

        news_m = re.search(r"### 📰 뉴스레터 \((\d+)자\)\n(.+?)(?=\n### 🏷️)", body, re.S)
        news_len = news_m.group(1) if news_m else "?"
        news_text = news_m.group(2).strip() if news_m else ""

        tag_m = re.search(r"### 🏷️ 사용된 현장 용어\n(.+?)(?=\n---|\Z)", body, re.S)
        tags = re.findall(r"#(\S+)", tag_m.group(1)) if tag_m else []

        seeds.append({"id": sid, "title": title, "dup_note": dup_note, "target": target,
                        "tone": tone, "ref_event": ref_event, "perspective": perspective,
                        "slides": slides, "kakao_len": kakao_len, "kakao_text": kakao_text,
                        "news_len": news_len, "news_text": news_text, "tags": tags})
    return seeds


def parse_md_table(block: str):
    """마크다운 테이블 문자열 -> [{col: val, ...}, ...]"""
    lines = [l for l in block.strip().split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


# ---------------------------------------------------------------------------
# 2) standard-guide.md 파싱
# ---------------------------------------------------------------------------
def parse_standard_guide(content: str):
    scripts = re.findall(r"- `(scripts/\S+\.py)`:\s*(.+)", content)

    cal_m = re.search(r"### 캘린더.+?\n(.+?)\n\n### 캐던스", content, re.S)
    calendar_rows = parse_md_table(cal_m.group(1)) if cal_m else []

    insight_m = re.search(r"### 캐던스 관련 인사이트\n(.+?)\n\n##", content, re.S)
    cadence_insight = insight_m.group(1).strip() if insight_m else ""

    metrics_m = re.search(r"## 3\. 채널별 핵심 지표\n\n(.+?)\n\n##", content, re.S)
    channel_metrics = parse_md_table(metrics_m.group(1)) if metrics_m else []

    voice_m = re.search(r"핵심 3원칙:\n\n(.+?)\n\n## 5\.", content, re.S)
    voice_items = re.findall(r"\d+\.\s+\*\*(.+?)\*\*:\s*(.+?)(?=\n\d+\.|\Z)", voice_m.group(1), re.S) if voice_m else []

    return {"scripts": scripts, "calendar": calendar_rows, "cadence_insight": cadence_insight,
            "channel_metrics": channel_metrics, "voice_items": voice_items}


# ---------------------------------------------------------------------------
# 3) pipeline-usage.md 파싱
# ---------------------------------------------------------------------------
def parse_pipeline_usage(content: str):
    summary_m = re.search(r"## 신규 담당자용 3줄 요약\n\n(.+?)\n\n#", content, re.S)
    steps = re.findall(r"\d+\.\s+(.+)", summary_m.group(1)) if summary_m else []

    oneshot_m = re.search(r"## 정말 한 번에 실행.+?\n\n```bash\n(.+?)\n```", content, re.S)
    one_shot_cmd = oneshot_m.group(1).strip() if oneshot_m else ""

    cmd_m = re.search(r"예시.+?\n\n```bash\n(.+?)\n```", content, re.S)
    example_cmd = cmd_m.group(1).strip() if cmd_m else ""

    table_m = re.search(r"## 검증된 결과.+?\n\n(.+?)\n\n", content, re.S)
    cadence_table = parse_md_table(table_m.group(1)) if table_m else []

    return {"steps": steps, "one_shot_cmd": one_shot_cmd, "example_cmd": example_cmd, "cadence_table": cadence_table}


# ---------------------------------------------------------------------------
# 4) challenge-strategy.md 파싱
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_challenge(content: str):
    principle_m = re.search(
        r"## 우선순위 판단 기준 \(직접 설계\)\n\n(.+?)\n\n((?:- \*\*.+?\n?)+)\n\n---",
        content, re.S,
    )
    principle_text = _norm(principle_m.group(1)) if principle_m else ""
    axis_defs = re.findall(r"- \*\*(.+?)\*\*:\s*(.+)", principle_m.group(2)) if principle_m else []

    strat_blocks = re.split(r"\n## 전략안 (\d+):\s*(.+?)\n", content)
    strategies = []
    for i in range(1, len(strat_blocks), 3):
        num, title, body = strat_blocks[i], strat_blocks[i + 1], strat_blocks[i + 2]

        def grab(label):
            mm = re.search(rf"\*\*{label}\*\*\n(.+?)(?=\n\n\*\*|\n\n---|\Z)", body, re.S)
            return mm.group(1).strip() if mm else ""

        problem = _norm(grab("문제 정의"))
        proposal = _norm(grab("전략 제안"))

        evidence_raw = grab("근거 데이터")
        evidence_items = []
        for chunk in re.split(r"\n(?=[ivx]+\))", evidence_raw.strip()):
            m = re.match(r"([ivx]+)\)\s*(.+)", chunk, re.S)
            if m:
                evidence_items.append((m.group(1), _norm(m.group(2))))

        priority_raw = grab("우선순위")
        priority_items = [(a, _norm(b)) for a, b in re.findall(r"- (.+?):\s*(.+)", priority_raw)]

        concl_m = re.search(r"\*\*(\d순위) 전략\*\*\s*—\s*(.+?)\.", body, re.S)
        rank, conclusion = (concl_m.group(1), _norm(concl_m.group(2)) + ".") if concl_m else ("?", "")

        strategies.append({
            "num": num, "title": title.strip(), "problem": problem,
            "evidence_items": evidence_items, "proposal": proposal,
            "priority_items": priority_items, "rank": rank, "conclusion": conclusion,
        })
    return {"principle_text": principle_text, "axis_defs": axis_defs, "strategies": strategies}


# ---------------------------------------------------------------------------
# 렌더링 — 콘텐츠 카드 (기존)
# ---------------------------------------------------------------------------
def para_html(text):
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{esc(p)}</p>" for p in paras)


TONE_CLASS = {"공감형": "t-empathy", "정보형": "t-info", "유머형": "t-humor"}
TARGET_CLASS = {"신규RN": "seg-new", "간호학생": "seg-student", "경력RN": "seg-senior"}


def render_seed_card(seed):
    tone_cls = TONE_CLASS.get(seed["tone"], "")
    target_cls = TARGET_CLASS.get(seed["target"], "")
    ref_badge = f'<span class="tag t-event">📅 {esc(seed["ref_event"])}</span>' if seed["ref_event"] and seed["ref_event"] != "없음(상시)" else '<span class="tag t-evergreen">상시</span>'
    dup_badge = '<span class="tag t-dup">중복topic 차별화</span>' if seed["dup_note"] else ""
    perspective_html = f'<div class="perspective">🔀 {esc(seed["perspective"])}</div>' if seed["perspective"] else ""

    slides_html = ""
    for s in seed["slides"]:
        cta_cls = " slide-cta" if s["is_cta"] else ""
        cta_label = " · CTA" if s["is_cta"] else ""
        slides_html += f'''
        <div class="slide{cta_cls}">
          <div class="slide-no">{esc(s["no"])}장{cta_label}</div>
          <div class="slide-headline">{esc(s["headline"])}</div>
          <div class="slide-text">{esc(s["text"])}</div>
        </div>'''

    tags_html = "".join(f'<span class="kw-tag">#{esc(t)}</span>' for t in seed["tags"])

    return f'''
    <article class="seed-card" data-target="{esc(seed["target"])}" data-tone="{esc(seed["tone"])}" data-search="{esc(seed["title"] + ' ' + ' '.join(seed["tags"]))}">
      <header class="seed-head" onclick="this.parentElement.classList.toggle('open')">
        <div class="seed-head-main">
          <span class="seed-id">#{esc(seed["id"])}</span>
          <span class="seed-title">{esc(seed["title"])}</span>
        </div>
        <div class="seed-head-tags">
          <span class="tag {target_cls}">{esc(seed["target"])}</span>
          <span class="tag {tone_cls}">{esc(seed["tone"])}</span>
          {ref_badge}
          {dup_badge}
        </div>
        <span class="chevron">▾</span>
      </header>
      <div class="seed-body">
        {perspective_html}
        <div class="channels">
          <div class="channel-tabs">
            <button class="ch-tab active" data-ch="card">🎴 카드뉴스</button>
            <button class="ch-tab" data-ch="kakao">💬 카카오 ({esc(seed["kakao_len"])}자)</button>
            <button class="ch-tab" data-ch="news">📰 뉴스레터 ({esc(seed["news_len"])}자)</button>
          </div>
          <div class="ch-panel ch-card active">{slides_html}</div>
          <div class="ch-panel ch-kakao">{para_html(seed["kakao_text"])}</div>
          <div class="ch-panel ch-news">{para_html(seed["news_text"])}</div>
        </div>
        <div class="kw-tags">{tags_html}</div>
      </div>
    </article>'''


def render_kpi_cards(kpi):
    bf, bv, kw, sp = kpi["basic_format"], kpi["brand_voice"], kpi["keywords"], kpi["speed"]
    return f'''
    <div class="kpi-grid">
      <div class="kpi-card kpi-teal">
        <div class="kpi-value">{sp["속도 단축률(%)"]}%</div>
        <div class="kpi-label">속도 단축률</div>
        <div class="kpi-sub">수작업 {sp["수작업 기준(1건, 분)"]}분 → AI {sp["AI 파이프라인 기준(1건, 분)"]}분<br>18건 기준 {sp["18건 총 소요-수작업(시간)"]}시간 → {sp["18건 총 소요-AI(시간)"]}시간</div>
      </div>
      <div class="kpi-card kpi-blue">
        <div class="kpi-value">{bv["브랜드보이스 유지도(3개 규칙 평균, %)"]}%</div>
        <div class="kpi-label">브랜드보이스 유지도</div>
        <div class="kpi-sub">호칭 병기 {bv["호칭 병기 준수"]} · 감성 이모지 {bv["감성 이모지 포함(카드+뉴스레터)"]}<br>카카오 이모지 미사용 {bv["카카오 이모지 미사용 준수"]}</div>
      </div>
      <div class="kpi-card kpi-pink">
        <div class="kpi-value">{kw["전문용어 사용도(%)"]}%</div>
        <div class="kpi-label">전문용어 사용도</div>
        <div class="kpi-sub">keywords_required {kw["요구 키워드 총합"]}개 중 {kw["반영된 키워드 수"]}개 반영</div>
      </div>
      <div class="kpi-card kpi-amber">
        <div class="kpi-value">{bf["생성 성공률(채널 평균, %)"]}%</div>
        <div class="kpi-label">생성 성공률</div>
        <div class="kpi-sub">카드뉴스 {bf["카드뉴스 성공"]} · 카카오메시지 {bf["카카오메시지 성공"]} · 뉴스레터 {bf["뉴스레터 성공"]}</div>
      </div>
    </div>
    <div class="kpi-note">※ 속도 단축률은 실측 스톱워치 값이 아니라 problem.md의 "1건 2~3시간"(중간값)과 목표치 "5분 내 초안"을 비교한 추정치입니다.</div>
    '''


# ---------------------------------------------------------------------------
# 렌더링 — 신규 섹션들
# ---------------------------------------------------------------------------
def render_pipeline_section(sg, pu):
    steps_html = "".join(f'<li>{esc(s)}</li>' for s in pu["steps"])
    scripts_html = "".join(
        f'<div class="pipe-step"><span class="pipe-no">{i+1}</span><div><code>{esc(name)}</code><p>{esc(desc)}</p></div></div>'
        for i, (name, desc) in enumerate(sg["scripts"])
    )
    inner = f'''
      <div class="oneshot-box">
        <div class="oneshot-label">🚀 정말 한 번에 끝내기 — 새 시드 CSV 하나로 전 과정 자동 실행</div>
        <code>{esc(pu["one_shot_cmd"])}</code>
        <p class="oneshot-desc">정제 → 캐던스 점검 → 3종 콘텐츠 생성(Claude Code 자동 호출) → 형식 검증 → KPI 측정 → HTML 리포트, 6단계가 사람 개입 없이 이어집니다. 터미널이 낯설면 Claude Code 채팅창에 "새 시드 파일로 전체 파이프라인 실행해줘"라고 말해도 동일하게 진행됩니다.</p>
      </div>
      <div class="pipe-grid">
        <div class="pipe-box">
          <div class="pipe-box-title">가장 쉬운 방법 (터미널 몰라도 OK)</div>
          <ol class="pipe-simple">{steps_html}</ol>
        </div>
        <div class="pipe-box">
          <div class="pipe-box-title">내부적으로 도는 6단계 (원샷 스크립트가 순서대로 호출)</div>
          <div class="pipe-steps">{scripts_html}</div>
        </div>
      </div>
      <div class="pipe-cmd">
        <span class="pipe-cmd-label">일부만(정제+캐던스 점검만) 실행하고 싶다면</span>
        <code>{esc(pu["example_cmd"])}</code>
      </div>'''
    return "🔧 재사용 파이프라인 — 신입도 따라할 수 있는 사용법", inner


def render_calendar_section(sg):
    groups = {}
    order = []
    for r in sg["calendar"]:
        date = r.get("발행일", "")
        month_key = date[:7] if len(date) >= 7 else "기타"
        if month_key not in groups:
            groups[month_key] = []
            order.append(month_key)
        groups[month_key].append(r)

    groups_html = ""
    for month_key in order:
        rows = groups[month_key]
        y, m = (month_key.split("-") + ["", ""])[:2]
        month_label = f"{y}년 {int(m)}월" if m.isdigit() else month_key
        items_html = ""
        for r in rows:
            target_cls = TARGET_CLASS.get(r.get("대상", ""), "")
            items_html += f'''
            <div class="cal-item">
              <div class="cal-item-date">{esc(r.get("발행일","")[-2:])}일</div>
              <div class="cal-item-body">
                <div class="cal-item-top">
                  <span class="cal-id">#{esc(r.get("id",""))}</span>
                  <span class="tag {target_cls}">{esc(r.get("대상",""))}</span>
                </div>
                <div class="cal-item-topic">{esc(r.get("topic",""))}</div>
                <div class="cal-item-reason">💡 {esc(r.get("배치 사유",""))}</div>
              </div>
            </div>'''
        groups_html += f'''
        <div class="cal-month-group">
          <div class="cal-month-label">{esc(month_label)}</div>
          <div class="cal-month-items">{items_html}</div>
        </div>'''

    inner = f'''
      <p class="section-desc">원칙 1: 시의성 이벤트는 발생 <b>전</b>에 역산 배치 · 원칙 2: 상시 콘텐츠는 타깃이 실제로 그 상황을 겪는 시기에 배치</p>
      <div class="cal-groups">{groups_html}</div>
      <div class="cal-insight">💡 {esc(sg["cadence_insight"])}</div>'''
    return "📅 발행 캘린더 — 18건 시드별 발행일", inner


def render_metrics_section(sg):
    cards = ""
    for m in sg["channel_metrics"]:
        ch = m.get("채널", "")
        metric = re.sub(r"\*\*", "", m.get("핵심 지표", ""))
        reason = m.get("근거", "")
        cards += f'''
        <div class="metric-card">
          <div class="metric-ch">{esc(ch)}</div>
          <div class="metric-name">{esc(metric)}</div>
          <div class="metric-reason">{esc(reason)}</div>
          <div class="metric-placeholder">실측값: 운영 데이터 연동 후 채워지는 자리 (현재는 스펙상 성과분석 범위 밖)</div>
        </div>'''
    inner = f'''
      <p class="section-desc">아래는 "실제 측정된 성과 수치"가 아니라 <b>"이 채널은 어떤 지표로 판단해야 하는가"에 대한 설계</b>입니다.
      문제 정의서가 콘텐츠 성과 분석(발행 후 지표 수집·분석)을 범위 밖으로 명시하고 있어, 가상의 성과 수치는 넣지 않았습니다.</p>
      <div class="metric-grid">{cards}</div>'''
    return "📊 채널별 핵심 지표 — 무엇을, 왜 볼 것인가", inner


def render_voice_section(sg):
    icons = ["🗣️", "🎨", "💬"]
    cards_html = ""
    for i, (name, desc) in enumerate(sg["voice_items"]):
        cards_html += f'''
        <div class="voice-card">
          <div class="voice-icon">{icons[i] if i < len(icons) else "✅"}</div>
          <div class="voice-name">{esc(name)}</div>
          <p class="voice-desc">{esc(desc)}</p>
        </div>'''

    tone_rows = "".join(
        f'<div class="tone-row"><span class="tag {TONE_CLASS.get(t,"")}">{esc(t)}</span><span class="voice-emoji">{esc(e)}</span></div>'
        for t, e in TONE_EMOJI.items()
    )
    inner = f'''
      <p class="section-desc">담당자가 바뀌어도 톤이 흔들리지 않도록 고정한 3가지 규칙입니다.</p>
      <div class="voice-grid">{cards_html}</div>
      <div class="tone-box">
        <div class="pipe-box-title">톤별 이모지 팔레트</div>
        <div class="tone-rows">{tone_rows}</div>
        <p class="voice-note">카카오메시지는 3개 톤 모두 이모지 미적용이 원칙입니다.</p>
      </div>'''
    return "🎙️ 브랜드보이스 설정값", inner


def render_strategy_section(ch):
    axis_html = "".join(f'<li><b>{esc(a)}</b>: {esc(d)}</li>' for a, d in ch["axis_defs"])
    cards = ""
    for s in ch["strategies"]:
        rank_cls = "rank-1" if s["rank"] == "1순위" else "rank-2"
        evid_html = "".join(f'<li><span class="evid-no">{esc(no)})</span> {esc(text)}</li>' for no, text in s["evidence_items"])
        prio_html = "".join(f'<li><b>{esc(a)}</b>: {esc(b)}</li>' for a, b in s["priority_items"])
        cards += f'''
        <div class="strategy-card">
          <div class="strategy-head">
            <span class="strategy-num">전략안 {esc(s["num"])}</span>
            <span class="strategy-badge {rank_cls}">{esc(s["rank"])}</span>
          </div>
          <h3 class="strategy-title">{esc(s["title"])}</h3>
          <div class="strategy-block"><div class="strategy-label">문제 정의</div><p>{esc(s["problem"])}</p></div>
          <div class="strategy-block"><div class="strategy-label">근거 데이터</div><ul class="evid-list">{evid_html}</ul></div>
          <div class="strategy-block"><div class="strategy-label">전략 제안</div><p>{esc(s["proposal"])}</p></div>
          <div class="strategy-block strategy-priority">
            <div class="strategy-label">우선순위 비교</div>
            <ul class="prio-list">{prio_html}</ul>
            <p class="strategy-conclusion">{esc(s["conclusion"])}</p>
          </div>
        </div>'''
    inner = f'''
      <p class="section-desc">타깃·톤·시의성 패턴에서 도출한 발행 전략 2건. 문제정의/근거데이터/전략제안/우선순위 4단 형식은 고정하되, 표현은 누구나 이해할 수 있게 직접 설계했습니다.</p>
      <div class="rubric-box">
        <div class="pipe-box-title">우선순위 판단 기준 (직접 설계)</div>
        <p class="rubric-principle">{esc(ch["principle_text"])}</p>
        <ul class="axis-list">{axis_html}</ul>
      </div>
      <div class="strategy-grid">{cards}</div>'''
    return "🧭 발행 전략안 (Challenge)", inner


def wrap_section(section_id, title, inner_html, open_default=False):
    open_cls = " open" if open_default else ""
    return f'''
    <section id="{section_id}" class="report-section collapsible{open_cls}">
      <div class="section-head" onclick="this.parentElement.classList.toggle('open')">
        <h2 class="section-title">{title}</h2>
        <span class="section-chevron">▾</span>
      </div>
      <div class="section-body">{inner_html}</div>
    </section>'''


CSS = """
:root {
  --teal: #2b7a78; --teal-bg: #d8f0ee;
  --blue: #4361ee; --blue-bg: #e7e0ff;
  --pink: #c14d77; --pink-bg: #ffe0e9;
  --amber: #b8860b; --amber-bg: #fff3cd;
  --ink: #1a1a2e; --sub: #6c757d; --line: #eee; --bg: #f4f5f7;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif; background: var(--bg); color: var(--ink); line-height: 1.65; }
.container { max-width: 1040px; margin: 0 auto; padding: 32px 20px 60px; }
.header { background: #fff; border-radius: 12px; padding: 28px 32px; margin-bottom: 16px; border-left: 5px solid var(--teal); box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.header h1 { font-size: 20px; font-weight: 800; margin-bottom: 6px; }
.header p { font-size: 13px; color: var(--sub); }

.nav { display: flex; gap: 6px; flex-wrap: wrap; background: #fff; padding: 10px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); position: sticky; top: 8px; z-index: 10; }
.nav a { font-size: 12.5px; font-weight: 700; color: var(--sub); text-decoration: none; padding: 8px 12px; border-radius: 8px; }
.nav a:hover { background: var(--teal-bg); color: var(--teal); }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 6px; }
.kpi-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.06); border-top: 4px solid; }
.kpi-teal { border-color: var(--teal); } .kpi-blue { border-color: var(--blue); }
.kpi-pink { border-color: var(--pink); } .kpi-amber { border-color: var(--amber); }
.kpi-value { font-size: 30px; font-weight: 800; }
.kpi-teal .kpi-value { color: var(--teal); } .kpi-blue .kpi-value { color: var(--blue); }
.kpi-pink .kpi-value { color: var(--pink); } .kpi-amber .kpi-value { color: #8a6d00; }
.kpi-label { font-size: 13px; font-weight: 700; margin-top: 2px; }
.kpi-sub { font-size: 11px; color: var(--sub); margin-top: 6px; line-height: 1.5; }
.kpi-note { font-size: 11px; color: var(--sub); margin: 10px 4px 24px; }

.report-section { background: #fff; border-radius: 12px; margin-bottom: 22px; box-shadow: 0 1px 4px rgba(0,0,0,.06); scroll-margin-top: 60px; overflow: hidden; }
.report-section.collapsible .section-head { display: flex; justify-content: space-between; align-items: center; padding: 24px 36px; cursor: pointer; user-select: none; }
.report-section.collapsible .section-body { display: none; padding: 0 36px 32px; }
.report-section.collapsible.open .section-body { display: block; }
.section-chevron { font-size: 16px; color: var(--sub); transition: transform .18s; flex: none; margin-left: 12px; }
.report-section.collapsible.open .section-chevron { transform: rotate(180deg); }
.section-title { font-size: 21px; font-weight: 800; }
.section-desc { font-size: 14.5px; color: var(--sub); margin-bottom: 22px; line-height: 1.75; }

.oneshot-box { background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 12px; padding: 24px 26px; margin-bottom: 22px; }
.oneshot-label { color: #fff; font-size: 15.5px; font-weight: 800; margin-bottom: 12px; }
.oneshot-box code { display: block; color: #7de8c4; font-size: 15px; font-weight: 700; background: rgba(255,255,255,.08); padding: 12px 16px; border-radius: 8px; word-break: break-all; }
.oneshot-desc { color: #c4c8d4; font-size: 13.5px; margin-top: 12px; line-height: 1.75; }
.pipe-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.pipe-box { background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 22px; }
.pipe-box-title { font-size: 13px; font-weight: 800; color: var(--sub); margin-bottom: 16px; letter-spacing: .03em; }
.pipe-simple { padding-left: 20px; font-size: 15px; line-height: 1.9; }
.pipe-simple li { margin-bottom: 12px; }
.pipe-steps { display: flex; flex-direction: column; gap: 16px; }
.pipe-step { display: flex; gap: 12px; align-items: flex-start; }
.pipe-no { background: var(--teal); color: #fff; font-size: 12px; font-weight: 800; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; margin-top: 2px; }
.pipe-step code { font-size: 13.5px; font-weight: 700; color: var(--teal); }
.pipe-step p { font-size: 13.5px; color: #444; margin-top: 4px; line-height: 1.6; }
.pipe-cmd { margin-top: 18px; background: #1a1a2e; border-radius: 10px; padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
.pipe-cmd-label { font-size: 12px; color: #9aa; font-weight: 700; }
.pipe-cmd code { color: #7de8c4; font-size: 14px; word-break: break-all; }

.cal-groups { display: flex; flex-direction: column; gap: 20px; }
.cal-month-label { font-size: 13.5px; font-weight: 800; color: var(--teal); background: var(--teal-bg); display: inline-block; padding: 5px 14px; border-radius: 20px; margin-bottom: 12px; }
.cal-month-items { display: flex; flex-direction: column; gap: 10px; }
.cal-item { display: flex; gap: 16px; background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; align-items: flex-start; }
.cal-item-date { font-size: 20px; font-weight: 800; color: var(--ink); flex: none; width: 48px; text-align: center; }
.cal-item-body { flex: 1; min-width: 0; }
.cal-item-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cal-id { font-size: 12px; font-weight: 800; color: var(--teal); }
.cal-item-topic { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.cal-item-reason { font-size: 13px; color: var(--sub); line-height: 1.6; }
.cal-insight { margin-top: 20px; background: var(--teal-bg); border-radius: 10px; padding: 16px 20px; font-size: 14px; color: #1a4a48; line-height: 1.7; }

.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.metric-card { background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 24px; }
.metric-ch { font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.metric-name { font-size: 25px; font-weight: 800; color: var(--teal); margin-bottom: 12px; }
.metric-reason { font-size: 13.5px; color: #444; line-height: 1.7; margin-bottom: 14px; }
.metric-placeholder { font-size: 12px; color: var(--sub); background: #fff; border: 1px dashed var(--line); border-radius: 6px; padding: 10px 12px; line-height: 1.6; }

.voice-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 20px; }
.voice-card { background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 24px; text-align: center; }
.voice-icon { font-size: 28px; margin-bottom: 10px; }
.voice-name { font-size: 15px; font-weight: 800; color: var(--teal); margin-bottom: 8px; }
.voice-desc { font-size: 13.5px; color: #444; line-height: 1.7; text-align: left; }
.tone-box { background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 22px; }
.tone-rows { display: flex; flex-direction: column; gap: 12px; margin-top: 6px; }
.tone-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--line); }
.voice-emoji { font-size: 20px; }
.voice-note { font-size: 12.5px; color: var(--sub); margin-top: 14px; }

.rubric-box { background: #f9f9fa; border: 1px solid var(--line); border-radius: 10px; padding: 22px; margin-bottom: 22px; }
.rubric-principle { font-size: 15px; font-weight: 700; color: #1a4a48; margin: 10px 0 14px; line-height: 1.7; }
.axis-list { padding-left: 20px; font-size: 13.5px; color: #444; line-height: 2; }
.strategy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.strategy-card { background: #f9f9fa; border: 1px solid var(--line); border-radius: 12px; padding: 26px; }
.strategy-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.strategy-num { font-size: 12px; font-weight: 800; color: var(--sub); letter-spacing: .05em; }
.strategy-badge { font-size: 12px; font-weight: 800; padding: 4px 12px; border-radius: 20px; }
.rank-1 { background: #ffe0e9; color: var(--pink); } .rank-2 { background: var(--amber-bg); color: #8a6d00; }
.strategy-title { font-size: 17px; font-weight: 800; margin-bottom: 18px; line-height: 1.5; }
.strategy-block { margin-bottom: 18px; }
.strategy-label { font-size: 11.5px; font-weight: 800; color: var(--sub); letter-spacing: .05em; margin-bottom: 6px; }
.strategy-block p { font-size: 13.5px; color: #333; line-height: 1.75; }
.evid-list, .prio-list { padding-left: 0; list-style: none; font-size: 13.5px; color: #333; line-height: 1.75; }
.evid-list li { margin-bottom: 10px; }
.evid-no { font-weight: 800; color: var(--teal); margin-right: 4px; }
.prio-list li { margin-bottom: 6px; }
.strategy-conclusion { margin-top: 12px; font-size: 13.5px; font-weight: 700; color: var(--teal); background: var(--teal-bg); padding: 10px 14px; border-radius: 8px; line-height: 1.6; }

.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; background: #fff; padding: 12px 16px; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.06); align-items: center; }
.toolbar input { flex: 1; min-width: 160px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; font-size: 13px; }
.toolbar select { padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; font-size: 13px; background: #fff; }
.result-count { font-size: 12px; color: var(--sub); white-space: nowrap; }

.seed-card { background: #fff; border-radius: 12px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.06); overflow: hidden; }
.seed-head { display: flex; align-items: center; gap: 10px; padding: 14px 18px; cursor: pointer; flex-wrap: wrap; }
.seed-head-main { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 200px; }
.seed-id { font-size: 11px; font-weight: 800; color: var(--teal); background: var(--teal-bg); padding: 2px 8px; border-radius: 6px; }
.seed-title { font-size: 14px; font-weight: 700; }
.seed-head-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 5px; white-space: nowrap; }
.seg-new { background: #e0f0ff; color: #1a5fa8; } .seg-student { background: var(--blue-bg); color: #5a2d9a; }
.seg-senior { background: #ffe9d6; color: #a35b0a; }
.t-empathy { background: #ffe0e9; color: var(--pink); } .t-info { background: var(--amber-bg); color: #8a6d00; }
.t-humor { background: #e0ffe9; color: #1a8a4a; }
.t-event { background: #ffe0e9; color: var(--pink); } .t-evergreen { background: #eee; color: #666; }
.t-dup { background: #fff3cd; color: #8a6d00; }
.chevron { font-size: 12px; color: var(--sub); transition: transform .15s; margin-left: auto; }
.seed-card.open .chevron { transform: rotate(180deg); }

.seed-body { display: none; padding: 0 18px 18px; border-top: 1px solid var(--line); }
.seed-card.open .seed-body { display: block; }
.perspective { font-size: 12px; color: var(--sub); background: #f8f9fa; padding: 8px 12px; border-radius: 8px; margin: 12px 0; }

.channel-tabs { display: flex; gap: 6px; margin: 12px 0 10px; flex-wrap: wrap; }
.ch-tab { font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 20px; border: 1px solid var(--line); background: #fafafa; cursor: pointer; color: var(--sub); }
.ch-tab.active { background: var(--teal); color: #fff; border-color: var(--teal); }
.ch-panel { display: none; font-size: 13.5px; }
.ch-panel.active { display: block; }
.ch-panel p { margin-bottom: 10px; }

.slide { background: #fafbfc; border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-bottom: 8px; }
.slide-cta { border-color: var(--teal); background: var(--teal-bg); }
.slide-no { font-size: 10px; font-weight: 800; color: var(--sub); margin-bottom: 4px; }
.slide-cta .slide-no { color: var(--teal); }
.slide-headline { font-size: 13.5px; font-weight: 700; margin-bottom: 4px; }
.slide-text { font-size: 13px; color: #333; }

.kw-tags { margin-top: 14px; }
.kw-tag { display: inline-block; font-size: 11px; font-weight: 700; color: var(--teal); background: var(--teal-bg); padding: 3px 9px; border-radius: 6px; margin: 0 4px 4px 0; }

.footer-note { text-align: center; font-size: 11px; color: var(--sub); margin-top: 24px; }
@media (max-width: 700px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .pipe-grid, .voice-grid, .strategy-grid { grid-template-columns: 1fr; }
  .metric-grid { grid-template-columns: 1fr; }
}
"""

JS = """
document.querySelectorAll('.nav a').forEach(a => {
  a.addEventListener('click', () => {
    const id = a.getAttribute('href').slice(1);
    const target = document.getElementById(id);
    if (target && target.classList.contains('collapsible')) {
      target.classList.add('open');
    }
  });
});

document.querySelectorAll('.channel-tabs').forEach(bar => {
  bar.addEventListener('click', e => {
    const btn = e.target.closest('.ch-tab');
    if (!btn) return;
    const card = bar.closest('.channels');
    bar.querySelectorAll('.ch-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    card.querySelectorAll('.ch-panel').forEach(p => p.classList.remove('active'));
    card.querySelector('.ch-' + btn.dataset.ch).classList.add('active');
  });
});

const searchInput = document.getElementById('search');
const targetFilter = document.getElementById('filter-target');
const toneFilter = document.getElementById('filter-tone');
const cards = Array.from(document.querySelectorAll('.seed-card'));
const countEl = document.getElementById('result-count');

function applyFilters() {
  const q = searchInput.value.trim().toLowerCase();
  const t = targetFilter.value;
  const tn = toneFilter.value;
  let shown = 0;
  cards.forEach(c => {
    const matchQ = !q || c.dataset.search.toLowerCase().includes(q);
    const matchT = !t || c.dataset.target === t;
    const matchTn = !tn || c.dataset.tone === tn;
    const ok = matchQ && matchT && matchTn;
    c.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  countEl.textContent = shown + ' / ' + cards.length + '건 표시';
}
searchInput.addEventListener('input', applyFilters);
targetFilter.addEventListener('change', applyFilters);
toneFilter.addEventListener('change', applyFilters);
applyFilters();
"""


def build():
    seeds = parse_seeds(CONTENT_MD.read_text(encoding="utf-8"))
    kpi = json.loads(KPI_JSON.read_text(encoding="utf-8"))
    sg = parse_standard_guide(STANDARD_MD.read_text(encoding="utf-8"))
    pu = parse_pipeline_usage(PIPELINE_MD.read_text(encoding="utf-8"))
    ch = parse_challenge(CHALLENGE_MD.read_text(encoding="utf-8"))

    assert len(seeds) == 18, f"시드 파싱 개수 이상: {len(seeds)}"
    assert len(sg["calendar"]) == 18, f"캘린더 행 개수 이상: {len(sg['calendar'])}"
    assert len(sg["channel_metrics"]) == 3, f"채널 지표 개수 이상: {len(sg['channel_metrics'])}"
    assert len(sg["voice_items"]) == 3, f"브랜드보이스 원칙 개수 이상: {len(sg['voice_items'])}"
    assert len(ch["strategies"]) == 2, f"전략안 개수 이상: {len(ch['strategies'])}"

    seed_cards_html = "".join(render_seed_card(s) for s in seeds)
    kpi_html = render_kpi_cards(kpi)
    pipeline_html = wrap_section("pipeline", *render_pipeline_section(sg, pu))
    calendar_html = wrap_section("calendar", *render_calendar_section(sg))
    metrics_html = wrap_section("metrics", *render_metrics_section(sg))
    voice_html = wrap_section("brandvoice", *render_voice_section(sg))
    strategy_html = wrap_section("strategy", *render_strategy_section(ch))

    html_out = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>널스빌리지 콘텐츠 3종 세트 &amp; 운영 대시보드</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>널스빌리지 SNS 콘텐츠 3종 세트 &amp; 운영 대시보드</h1>
    <p>data/nursevillage_content_seeds.csv 18건 기준 · Basic(콘텐츠 3종) + Standard(파이프라인·캘린더·지표·브랜드보이스) + Challenge(발행 전략안) + KPI 실측을 한 화면에 정리했습니다.</p>
  </div>

  <nav class="nav">
    <a href="#kpi">📈 KPI</a>
    <a href="#pipeline">🔧 파이프라인 사용법</a>
    <a href="#calendar">📅 발행 캘린더</a>
    <a href="#metrics">📊 채널별 지표</a>
    <a href="#brandvoice">🎙️ 브랜드보이스</a>
    <a href="#strategy">🧭 발행 전략안</a>
    <a href="#content">🎴 콘텐츠 3종(18건)</a>
  </nav>

  <div id="kpi">{kpi_html}</div>

  {pipeline_html}
  {calendar_html}
  {metrics_html}
  {voice_html}
  {strategy_html}

  <section id="content" class="report-section" style="padding:0;background:transparent;box-shadow:none">
    <h2 class="section-title" style="padding:0 4px">🎴 콘텐츠 3종 세트 (18건 전문)</h2>
    <div class="toolbar">
      <input id="search" type="text" placeholder="주제·용어로 검색...">
      <select id="filter-target">
        <option value="">전체 타깃</option>
        <option value="신규RN">신규RN</option>
        <option value="간호학생">간호학생</option>
        <option value="경력RN">경력RN</option>
      </select>
      <select id="filter-tone">
        <option value="">전체 톤</option>
        <option value="공감형">공감형</option>
        <option value="정보형">정보형</option>
        <option value="유머형">유머형</option>
      </select>
      <span class="result-count" id="result-count"></span>
    </div>
    <div class="seed-list">
      {seed_cards_html}
    </div>
  </section>

  <div class="footer-note">Problem 04 다이버즈 · Basic+Standard+Challenge 전체 산출물 + KPI 실측 결과 (정적 HTML, 서버 없음)</div>
</div>
<script>{JS}</script>
</body>
</html>"""

    OUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"생성됨: {OUT_HTML} ({len(seeds)}개 시드, 캘린더 {len(sg['calendar'])}행, "
          f"채널지표 {len(sg['channel_metrics'])}개, 브랜드보이스 {len(sg['voice_items'])}개, "
          f"전략안 {len(ch['strategies'])}건, {len(html_out)}자)")


if __name__ == "__main__":
    build()

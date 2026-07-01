"""HTML 리포트 생성 스크립트 — Problem 04 다이버즈
output/output_content_set.md(18건 3종 콘텐츠)와 output/kpi-results.json(KPI 4종)을
읽어 output/dashboard.html(정적 HTML, 서버·앱 없음)을 생성합니다.
app.py(Streamlit)가 이 파일을 그대로 읽어 iframe으로 보여주므로, 외부 CDN 의존 없이
완전히 자기완결적인(self-contained) 단일 HTML로 만듭니다.
"""
import re
import json
import html
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONTENT_MD = BASE / "output" / "output_content_set.md"
KPI_JSON = BASE / "output" / "kpi-results.json"
OUT_HTML = BASE / "output" / "dashboard.html"

EMOJI_PALETTE = set("🤍😊🥲💪🌱😆🙈😅🎉")


def parse_seeds(content: str):
    """output_content_set.md의 시드별 블록을 구조화해 파싱한다."""
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
            slide_text = card_m.group(2)
            raw_slides = re.split(r"\n(?=\*\*\d+장)", slide_text.strip())
            for s in raw_slides:
                hm = re.match(r"\*\*(\d+)장(\(CTA\))?\.\s*(.+?)\*\*\n(.+)", s.strip(), re.S)
                if hm:
                    slides.append({
                        "no": hm.group(1),
                        "is_cta": bool(hm.group(2)),
                        "headline": hm.group(3).strip(),
                        "text": hm.group(4).strip(),
                    })

        kakao_m = re.search(r"### 💬 카카오메시지 \((\d+)자\)\n(.+?)(?=\n### 📰)", body, re.S)
        kakao_len = kakao_m.group(1) if kakao_m else "?"
        kakao_text = kakao_m.group(2).strip() if kakao_m else ""

        news_m = re.search(r"### 📰 뉴스레터 \((\d+)자\)\n(.+?)(?=\n### 🏷️)", body, re.S)
        news_len = news_m.group(1) if news_m else "?"
        news_text = news_m.group(2).strip() if news_m else ""

        tag_m = re.search(r"### 🏷️ 사용된 현장 용어\n(.+?)(?=\n---|\Z)", body, re.S)
        tags = re.findall(r"#(\S+)", tag_m.group(1)) if tag_m else []

        seeds.append({
            "id": sid, "title": title, "dup_note": dup_note,
            "target": target, "tone": tone, "ref_event": ref_event,
            "perspective": perspective, "slides": slides,
            "kakao_len": kakao_len, "kakao_text": kakao_text,
            "news_len": news_len, "news_text": news_text,
            "tags": tags,
        })
    return seeds


def esc(s):
    return html.escape(s, quote=True)


def para_html(text):
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{esc(p)}</p>" for p in paras)


TONE_CLASS = {"공감형": "t-empathy", "정보형": "t-info", "유머형": "t-humor"}
TARGET_CLASS = {"신규RN": "seg-new", "간호학생": "seg-student", "경력RN": "seg-senior"}


def render_seed_card(seed):
    tone_cls = TONE_CLASS.get(seed["tone"], "")
    target_cls = TARGET_CLASS.get(seed["target"], "")
    ref_badge = f'<span class="tag t-event">📅 {esc(seed["ref_event"])}</span>' if seed["ref_event"] and seed["ref_event"] != "없음(상시)" else '<span class="tag t-evergreen">상시</span>'
    dup_badge = f'<span class="tag t-dup">중복topic 차별화</span>' if seed["dup_note"] else ""
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
    bf = kpi["basic_format"]
    bv = kpi["brand_voice"]
    kw = kpi["keywords"]
    sp = kpi["speed"]
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
.container { max-width: 980px; margin: 0 auto; padding: 32px 20px 60px; }
.header { background: #fff; border-radius: 12px; padding: 28px 32px; margin-bottom: 20px; border-left: 5px solid var(--teal); box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.header h1 { font-size: 20px; font-weight: 800; margin-bottom: 6px; }
.header p { font-size: 13px; color: var(--sub); }

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
@media (max-width: 700px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
"""

JS = """
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
    content = CONTENT_MD.read_text(encoding="utf-8")
    kpi = json.loads(KPI_JSON.read_text(encoding="utf-8"))
    seeds = parse_seeds(content)

    seed_cards_html = "".join(render_seed_card(s) for s in seeds)
    kpi_html = render_kpi_cards(kpi)

    html_out = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>널스빌리지 콘텐츠 3종 세트 &amp; KPI 리포트</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>널스빌리지 SNS 콘텐츠 3종 세트 &amp; KPI 리포트</h1>
    <p>data/nursevillage_content_seeds.csv 18건 기준 · 카드뉴스·카카오메시지·뉴스레터 자동 생성 결과와, 문제 정의(속도·브랜드보이스 일관성·전문용어 반영·포맷 정확도) 대비 해결 정도를 측정한 KPI입니다.</p>
  </div>

  {kpi_html}

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

  <div class="footer-note">Problem 04 다이버즈 · Basic 콘텐츠 18건 전문 + KPI 실측 결과 (정적 HTML, 서버 없음)</div>
</div>
<script>{JS}</script>
</body>
</html>"""

    OUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"생성됨: {OUT_HTML} ({len(seeds)}개 시드, {len(html_out)}자)")


if __name__ == "__main__":
    build()

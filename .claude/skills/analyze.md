# /analyze — 콘텐츠 시드 데이터 파악

## 목적

data/nursevillage_content_seeds.csv를 읽고 콘텐츠 생성 전 데이터 현황을 파악합니다.
결측치·중복·이벤트 분포를 확인하고, 간호 현장 용어 사전을 숙지해 generate 단계의 예외 처리 방향을 결정합니다.

---

## 실행 절차

### 1단계: 파일 읽기
`data/nursevillage_content_seeds.csv`를 Read 툴로 읽으세요. (18행 + 헤더)

### 2단계: 컬럼 구조 확인
아래 컬럼이 모두 존재하는지 확인하세요:
- id, topic, tone, target_audience, keywords_required, platform_hint, ref_event

### 3단계: 결측·중복 탐지
- **keywords_required 결측**: 빈 값인 행의 id를 나열하세요 (예상: 1건)
- **ref_event 빈칸**: 빈 값인 행의 id를 나열하세요 (상시 콘텐츠 — 시즌 언급 없이 작성)
- **중복 topic**: topic 문자열이 동일한 행 쌍을 찾으세요 (예상: 1쌍, target_audience는 상이)

### 4단계: 분포 집계
- target_audience별 건수: 신규RN __ / 간호학생 __ / 경력RN __
- tone별 건수: 공감형 __ / 정보형 __ / 유머형 __
- platform_hint별 건수: card __ / kakao __ / newsletter __
- ref_event(시의성)별 건수

### 5단계: 채널 요구사항 정리
| 채널 | 분량 | 구성 |
|---|---|---|
| 카드뉴스 | 3~5장 | 장별 헤드라인 + 본문 2~3문장, 마지막 장 CTA |
| 카카오메시지 | 200자 이내 | 핵심 + 링크 유도 |
| 뉴스레터 | 600자 내외 | 도입–본문–CTA 3단 |

### 6단계: 용어 사전 숙지
`context/company-info.md`의 간호 현장 용어 사전(나이팅게일 선서·태움·RN/LPN·프리셉터·SBAR·5R·OCS·EMR·듀티표 등)을 읽고, keywords_required에 등장하는 용어의 정의를 확인하세요.

---

## 출력 형식
```
## 데이터 분석 결과

### 전체 건수
- 총 18건 (target 3종 × tone 3종 × 2)

### 결측·중복 현황
- keywords_required 결측: id [번호] (__건)
- ref_event 빈칸: id [번호] (__건)
- 중복 topic: id [번호] = id [번호] — "[topic]" (target 상이)

### 분포
- target: 신규RN __ / 간호학생 __ / 경력RN __
- tone: 공감형 __ / 정보형 __ / 유머형 __

### 처리 방향 제안
- 결측 keywords: [보완 방법]
- 중복 topic: [타깃별 차별화 방향]
```

---

## 완료 조건
- 결측·중복 행이 모두 식별됨
- target·tone·platform 분포가 집계됨
- 처리 방향이 제안됨
- 주요 결정은 decisions.md에 기록됨

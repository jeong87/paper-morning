# Paper Morning Scoring Policy

이 문서는 Paper Morning이 어떤 기준으로 논문을 올릴지 결정하는지 설명합니다.

모든 프롬프트 전문을 그대로 공개하는 문서는 아니고, `점수 체계와 선택 기준`을 설명하는 문서입니다.

## 1) 먼저 검색하고, 그 다음 점수화
Paper Morning은 전체 논문 우주를 바로 LLM에게 맡기지 않습니다.

파이프라인:
1. 연구 컨텍스트에서 검색식 생성
2. arXiv, PubMed 같은 소스에서 후보 수집
3. shortlist 생성
4. shortlist에 대해 listwise LLM rerank 수행

현재 shortlist 제어값:
- `LLM_MAX_CANDIDATES`
- 기본값은 `30`

## 2) Search intent 층
검색 intent는 retrieval과 ranking 기대치를 함께 바꿉니다.

### `whats_new`
- 최신 논문 우선
- 요청한 horizon 안에서 단계적으로 기간 확장
- 그래도 직접적인 usefulness는 요구

### `best_match`
- 선택한 기간 안에서 가장 잘 맞는 논문 우선
- 직접적인 overlap과 실용적 재사용 가능성을 중시

### `discovery`
- 인접하지만 전이 가능한 작업까지 더 넓게 포함
- 가까운 분야의 방법론 이전 가능성을 허용

## 3) Topic relevance mode
각 topic은 relevance mode를 가질 수 있습니다.

### `strict`
- threshold: `7.5`
- precision 우선
- 인접 논문도 통과할 수는 있지만 reuse path가 매우 강해야 함

### `balanced`
- threshold: `6.0`
- 기본 모드
- exact match만이 아니라 재사용 가능한 방법론 논문도 허용

### `discovery`
- threshold: `5.0`
- high-upside 인접 논문을 더 넓게 허용
- generic buzzword overlap은 여전히 낮게 평가

코드 기준 파일:
- `app/scoring_policy.py`

## 4) LLM이 반환하는 것
각 shortlist 논문에 대해 LLM은 다음을 반환합니다.
- `relevance_score`
- `relevance_reason`
- `core_point`
- `usefulness`
- `evidence_spans`

`evidence_spans`는 제목 또는 초록에서 가져온 짧은 근거 구문이어야 합니다.

## 5) Evidence-aware gating
추가 안전 규칙이 있습니다.
- 점수가 `7.0 이상`인데 evidence spans가 없으면 강등합니다

목적:
- 근거 없는 고득점 inflation 억제
- 나중에 사용자가 high score를 점검하기 쉽게 만들기

## 6) 현재의 tradeoff
Paper Morning은 지금 `작은 배치 여러 번`보다 `capped shortlist listwise rerank`를 사용합니다.

이유:
- 논문 간 상대 비교가 더 쉬움
- 하나의 공통 스케일 유지에 유리함

알려진 tradeoff:
- shortlist가 너무 길어지면 일관성이 떨어질 수 있음
- 현재는 token-aware chunk orchestration 대신 shortlist cap으로 제어하고 있음

이건 아직 해결 안 된 결함이라기보다, 현재의 명시적 설계 선택입니다.

## 7) 이 점수가 의미하지 않는 것
이 점수는 논문의 절대적 질을 말하는 점수가 아닙니다.

이 점수는 다음을 위한 ranking signal입니다.
- 실용적 usefulness
- 방법론 재사용 가능성
- 입력된 연구 컨텍스트와의 관련성

즉, `선별용 점수`이지 `논문 품질 자체의 절대평가`는 아닙니다.

# Paper Morning

[![Paper Morning Logo](../../assets/papermorning2.png)](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html)

**[EN](../../README.md) | [KR](README_KR.md)**

Paper Morning은 의료/헬스케어 AI 연구자를 위한 연구 맥락 기반 논문 검색 도구입니다.  
프로젝트 설명을 넣으면 검색식을 만들고, 실제 논문 후보를 가져온 뒤, 어떤 논문이 왜 맞는지까지 정리해줍니다.  
로컬 인박스, 아침 팝업, 이메일 발송은 모두 선택 기능으로 남아 있습니다.

- 최신 버전: **[v0.7.0](../../VERSION)**
- 라이선스: `GNU AGPLv3` ([LICENSE](../../LICENSE))
- 개인정보/외부 전송 정책: [PRIVACY.md](../../PRIVACY.md)

## 라이브 웹 프리뷰
GitHub에서 제품이 무엇을 하는지 먼저 확인하고 싶다면:

- <a href="https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html">한글 라이브 웹 프리뷰 열기</a>

이 페이지에서 일어나는 일:
- 연구 컨텍스트와 Gemini API key를 입력합니다.
- Paper Morning이 컨텍스트에서 검색식을 생성합니다.
- arXiv와 PubMed에서 실제 후보 논문을 가져옵니다.
- Gemini가 후보를 같은 기준으로 다시 평가하고 요약합니다.
- 결과를 새 브라우저 탭 HTML로 보여줍니다.

참고:
- 브라우저 안에서만 동작합니다.
- 이 페이지에서는 실제 이메일을 보내지 않습니다.
- 설치 전에 제품 가치를 확인하기 위한 첫 인상용 진입점입니다.

## 이 도구가 하는 일
1. 프로젝트 맥락에서 검색 의도를 파악합니다.
2. arXiv, PubMed, Semantic Scholar, 선택적으로 Google Scholar(SerpAPI)에서 논문을 수집합니다.
3. LLM이 실사용 관점에서 관련성을 다시 평가합니다.
4. 사용자는 필요할 때 결과를 보고, 원하면 나중에 자동화나 이메일까지 켤 수 있습니다.

## 주요 기능
- `최신 동향 / 정확도 우선 / 탐색 확장` 검색 모드
- `7일 ~ 5년` 기간 선택
- 프로젝트 맥락 기반 LLM relevance ranking
- 로컬 인박스 기본 경로
- 실행 중인 PC에서 아침 팝업 자동 열기
- 이메일 발송은 선택 기능
- Gemini 자동 폴백
  - `3.1-pro -> 3.1-flash -> 3.0-pro -> 3.0-flash -> 2.5-pro -> 2.5-flash`
- `OUTPUT_LANGUAGE=en|ko|ja|es|...` 지원

## 추천 시작 경로
가장 먼저 확인할 것은 “내 연구 주제에 맞는 논문이 잘 잡히는가”입니다.

1. 의존성 설치

```bash
pip install -r deps/requirements.txt
```

2. 로컬 런처 실행

```bash
python app/local_ui_launcher.py
```

3. 첫 실행이면 브라우저에서 setup 화면이 자동으로 열립니다.
4. 프로젝트 설명과 Gemini key를 입력한 뒤 `Save and Search Now`를 누릅니다.
5. 이후부터는 홈에서 버튼 한 번으로 최신 검색 결과를 열 수 있습니다.

`로컬 인박스`는 메일 대신 검색 결과 HTML/JSON을 내 PC에 저장하고 브라우저에서 다시 여는 방식입니다.

## 자동화와 발송은 나중에
검색 품질이 만족스러운지 먼저 확인한 뒤에만 아래 옵션을 켜는 편이 좋습니다.

- 로컬 아침 팝업
- Gmail OAuth
- Gmail 앱 비밀번호
- GitHub Actions 자동화

## 인증 옵션 우선순위
1. `로컬 인박스`
2. `Gmail OAuth`
3. `Gmail 앱 비밀번호`

설명:
- 로컬 인박스는 이메일 자격증명이 전혀 필요 없습니다.
- Gmail OAuth는 옵션 기능이며, 공개 사용자 대상으로 안정적으로 운영하려면 Google 쪽 설정과 검증 이슈를 확인해야 합니다.
- Gmail 앱 비밀번호는 가장 단순한 fallback 경로입니다.

## 빠른 링크
- 초보자 가이드: [MANUAL_FIRSTTIME_KR.md](./MANUAL_FIRSTTIME_KR.md)
- 고급 운영/자동화: [MANUAL_KR.md](./MANUAL_KR.md)
- 에이전트/툴 연동: [MANUAL_AGENT_KR.md](./MANUAL_AGENT_KR.md)
- English README: [../../README.md](../../README.md)

## 문의
- `nineclas@gmail.com`

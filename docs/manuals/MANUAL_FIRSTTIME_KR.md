# Paper Morning 초보자 매뉴얼

이 문서는 처음 사용하는 분을 위한 빠른 시작 가이드입니다.  
핵심 목표는 자동화보다 먼저, **내 연구 맥락에 맞는 논문이 실제로 잘 잡히는지 확인하는 것**입니다.

## 0. 준비물
1. Python 3.11+
2. 이 저장소 코드
3. Gemini API key 1개
4. 이메일 설정은 당장은 필요 없음

Gemini API key 발급:
- https://aistudio.google.com/app/apikey

## 1. 가장 먼저 확인할 것
먼저 할 일:
- 프로젝트 설명 입력
- 검색 모드 선택
- 논문 검색 결과 1회 생성

나중에 할 일:
- 아침 팝업 자동화
- Gmail 연동
- GitHub Actions 자동화

## 2. 설치 없이 먼저 체험하기
GitHub에서 바로 확인하려면:

- 한글 라이브 프리뷰: https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html

이 경로는 설치 없이 브라우저에서 바로 동작합니다.  
결과는 새 탭 HTML로 열리며, 실제 이메일은 보내지 않습니다.

## 3. 로컬 설치 후 첫 실행
1. 의존성 설치

```bash
pip install -r deps/requirements.txt
```

2. 로컬 런처 실행

```bash
python app/local_ui_launcher.py
```

3. 브라우저가 자동으로 열리지 않으면 아래 주소로 접속

```text
http://127.0.0.1:5050
```

4. 첫 실행이면 setup 화면으로 자동 이동합니다.

## 4. setup에서 입력할 것
- Onboarding mode: `preview`
- 프로젝트 이름
- 프로젝트 컨텍스트
- 추가 키워드(선택)
- Gemini API key
- 기본 검색 모드
  - `best_match`
  - `whats_new`
  - `discovery`
- 기본 검색 기간
  - `7d`, `30d`, `180d`, `1y`, `3y`, `5y`

추천:
- 처음에는 `best_match + 1y`
- 최신성 확인이 중요하면 `whats_new + 30d`
- 인접 방법론까지 보고 싶으면 `discovery + 3y`

## 5. 첫 검색 실행
1. `Save and Search Now` 클릭
2. 새 탭 또는 결과 화면에서 아래를 확인
   - 어떤 기간으로 검색했는지
   - 몇 편을 검토했고 몇 편을 선정했는지
   - 왜 내 연구와 맞는지
   - 핵심 포인트
   - 어떻게 활용할 수 있는지

검색 결과가 괜찮다면 그 다음부터는 홈 화면에서 버튼 한 번으로 다시 검색할 수 있습니다.

## 6. 로컬 인박스란?
`로컬 인박스`는 메일 대신 검색 결과를 로컬 파일로 저장하고 브라우저에서 다시 여는 방식입니다.

장점:
- Gmail 설정이 필요 없음
- 다른 사람 메일을 거치지 않음
- 가장 설치 허들이 낮음

즉, Paper Morning의 기본 경로는 이제  
`연구 컨텍스트 입력 -> 검색 -> 로컬에서 결과 확인` 입니다.

## 7. 자동화는 필요할 때만
원하면 나중에 아래를 켤 수 있습니다.

- 아침 9시 팝업 자동 실행
- Gmail OAuth
- Gmail 앱 비밀번호
- GitHub Actions 스케줄 실행

권장 우선순위:
1. 로컬 인박스로 먼저 검증
2. 필요하면 아침 팝업
3. 그 다음 이메일

## 8. 자주 생기는 문제
`Gemini API key is required`
- setup 또는 라이브 프리뷰에 Gemini key가 비어 있습니다.

`No papers found`
- 컨텍스트가 너무 좁거나 키워드가 과하게 제한적일 수 있습니다.
- `1y -> 3y -> 5y`로 기간을 넓혀보세요.
- `best_match` 대신 `discovery`를 시도해보세요.

`Quota exhausted`
- 선택한 Gemini 모델 quota가 부족할 수 있습니다.
- 앱은 여러 Gemini 모델을 자동 폴백 시도한 뒤 최종 실패 시에만 quota 메시지를 보여줍니다.

`Popup blocked`
- 브라우저가 새 탭을 막고 있습니다.
- `127.0.0.1:5050` 또는 raw.githack 페이지의 팝업을 허용하세요.

## 9. 다음 문서
- 한글 README: [README_KR.md](./README_KR.md)
- 고급 자동화/운영: [MANUAL_KR.md](./MANUAL_KR.md)

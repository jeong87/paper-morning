# Linux 빌드 빠른 가이드

이 폴더를 Linux 서버/PC로 그대로 옮긴 뒤, 아래 순서대로 실행하면 Linux 배포판이 생성됩니다.

## 1) 준비 패키지

Ubuntu/Debian 예시:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv build-essential
```

## 2) 빌드

```bash
cd linux_bundle_20260226
python3 -m venv .venv
source .venv/bin/activate

# (Windows에서 옮긴 파일이라 줄바꿈 이슈가 있으면 1회 실행)
sed -i 's/\r$//' build_linux.sh start_web_console.sh

chmod +x build_linux.sh start_web_console.sh
./build_linux.sh
```

## 3) 결과물

빌드 완료 후 `dist/` 폴더:

- `PaperDigestLocalUI` (웹 UI 런처)
- `PaperDigestSetup` (초기 설정 마법사)
- `PaperDigest` (CLI 실행)
- `.env.example`, `user_topics.template.json`, `MANUAL_KR.md`, `README.md`

## 4) 실행 테스트

```bash
./dist/PaperDigestLocalUI
```

브라우저에서 `http://127.0.0.1:5050` (또는 로그에 표시된 포트) 접속.

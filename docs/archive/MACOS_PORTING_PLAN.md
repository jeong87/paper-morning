# Paper-Morning macOS 포팅 계획 (v0.2.4 기준)

> **결론**: 현재 코드베이스는 **90% 이상 macOS와 호환**됩니다. Python 자체의 크로스 플랫폼 지원 덕분입니다. 남은 10%는 **빌드 스크립트**와 **OS Native 스케줄러(launchd) 연동**입니다.

---

## 1. 현재 macOS 호환성 현황 (Passed)

코드베이스 분석 결과, 이미 많은 부분이 macOS를 고려하여 작성되어 있습니다.

*   ✅ **파일 경로 처리**: `pathlib`를 사용하여 OS 상관없이 안전하게 경로를 조작하고 있습니다.
*   ✅ **사용자 데이터 폴더**: `get_default_data_dir()` 함수에 `sys.platform == "darwin"` 조건이 이미 구현되어 있어, macOS에서는 `~/Library/Application Support/paper-morning` 경로를 정상적으로 사용합니다.
*   ✅ **로컬 UI 브라우저 실행**: `webbrowser.open()`은 macOS의 기본 브라우저(Safari, Chrome 등)를 정상적으로 호출합니다.
*   ✅ **파일 권한 관리**: `enforce_private_file_permissions()` 함수에서 `os.name == "nt"`가 아닌 경우 (macOS 포함 POSIX계열) `chmod 600`(`stat.S_IRUSR | stat.S_IWUSR`)을 정상 적용합니다.
*   ✅ **의존성 패키지**: `requirements.txt`에 명시된 패키지(Flask, feedparser, requests 등)는 모두 macOS 환경(Intel/Apple Silicon)에서 네이티브하게 잘 돌아갑니다.

---

## 2. 향후 보완이 필요한 부분 (Todo)

macOS 사용자에게 Windows와 동일한 수준의 `One-click` 경험과 자동화 기능을 제공하려면 다음 두 가지 작업이 필요합니다.

### A. macOS 전용 스케줄러 등록 (launchd)

Windows의 "작업 스케줄러" 역할을 macOS에서는 `launchd`가 담당합니다. 현재 `register_task.ps1` (PowerShell 스크립트)만 존재하며, 웹 UI의 "Register Windows Scheduled Task" 버튼은 Windows에서만 동작합니다.

**구현 계획:**
1.  **`register_task_mac.sh` 또는 파이썬 함수 생성**: 사용자 홈 디렉토리의 `~/Library/LaunchAgents/com.paper-morning.daily.plist` 파일을 동적으로 생성하는 스크립트 작성.
2.  **plist 설정 내용**:
    *   `ProgramArguments`: `PaperDigest` 실행 파일 경로와 `--task=send_now` (또는 해당 역할의 인자)
    *   `StartCalendarInterval`: 사용자가 설정한 `SEND_HOUR`, `SEND_MINUTE` 적용
    *   `StandardOutPath`, `StandardErrorPath`: 로그 파일 경로 지정
3.  **UI 연동**: `web_app.py`에 `register_mac_launchd_task()` 함수를 추가하고, OS가 `darwin`일 때 Settings/Home 화면에 "Register macOS Launchd Task" 버튼 표시.

### B. macOS 빌드 자동화 스크립트 (`build_mac.sh`)

현재 `build_windows.ps1`과 `build_linux.sh`만 존재합니다. PyInstaller를 사용하여 macOS용 독립 실행형(Standalone) 바이너리를 만드는 스크립트가 필요합니다.

**구현 계획 (`build_mac.sh` 초안):**
```bash
#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"

echo "Installing runtime dependencies..."
"$PYTHON_EXE" -m pip install -r requirements.txt

echo "Installing build dependency (PyInstaller)..."
"$PYTHON_EXE" -m pip install pyinstaller

# macOS에서는 앱 번들(.app)보다는 CLI 도구 형태로 배포하는 것이
# launchd 스케줄러와의 연동 및 터미널 사용에 더 유리할 수 있습니다.
echo "Building PaperDigest ..."
"$PYTHON_EXE" -m PyInstaller --name PaperDigest --clean --noconfirm --onefile paper_digest_app.py

echo "Building PaperDigestSetup ..."
"$PYTHON_EXE" -m PyInstaller --name PaperDigestSetup --clean --noconfirm --onefile onboarding_wizard.py

echo "Building PaperDigestLocalUI ..."
"$PYTHON_EXE" -m PyInstaller --name PaperDigestLocalUI --clean --noconfirm --onefile local_ui_launcher.py

# ... (Linux 빌드 스크립트와 동일한 파일 복사 로직)
```

**추가 고려사항 (Apple Silicon vs Intel):**
*   macOS는 아키텍처(M1/M2 vs Intel) 파편화가 있습니다.
*   빌드하는 Mac의 아키텍처에 맞춰 바이너리가 생성되므로, 배포 시 `macOS_arm64.zip`과 `macOS_x86_64.zip` 두 가지 버전을 제공하거나, GitHub Actions를 통해 Universal Binary로 컴파일하는 설정이 필요합니다.

---

## 3. 요약 로드맵

1.  **(즉시 가능)** 제공된 Python 소스코드를 macOS 터미널에서 `python start_web_console.py` 형태로 직접 실행하여 바로 사용 시작.
2.  **(단기 포팅)** `build_mac.sh` 스크립트를 추가하여 macOS용 독립 실행파일(`.zip`) 배포 파이프라인 구축.
3.  **(중기 포팅)** macOS `launchd` plist 자동 생성 기능을 웹 UI에 탑재하여 "매일 자동 발송" 설정의 편의성 창출.

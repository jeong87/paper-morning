#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"

echo "Installing runtime dependencies..."
"$PYTHON_EXE" -m pip install -r requirements.txt

echo "Installing build dependency (PyInstaller)..."
"$PYTHON_EXE" -m pip install pyinstaller

echo "Building PaperDigest ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigest \
  --clean \
  --noconfirm \
  --onefile \
  paper_digest_app.py

echo "Building PaperDigestSetup ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigestSetup \
  --clean \
  --noconfirm \
  --onefile \
  onboarding_wizard.py

echo "Building PaperDigestLocalUI ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigestLocalUI \
  --clean \
  --noconfirm \
  --onefile \
  local_ui_launcher.py

echo "Cleaning generated local config files from dist ..."
rm -f dist/.env dist/user_topics.json

echo "Copying support files to dist ..."
cp -f .env.example dist/.env.example
cp -f google_oauth_bundle.template.json dist/google_oauth_bundle.template.json
if [ -f "google_oauth_bundle.json" ]; then
  cp -f google_oauth_bundle.json dist/google_oauth_bundle.json
fi
cp -f user_topics.template.json dist/user_topics.template.json
cp -f MANUAL_KR.md dist/MANUAL_KR.md
cp -f README.md dist/README.md
cp -f LICENSE dist/LICENSE
cp -f PRIVACY.md dist/PRIVACY.md
cp -f VERSION dist/VERSION
cp -f CHANGELOG.md dist/CHANGELOG.md
cp -f register_task.ps1 dist/register_task.ps1
if [ -f "paper-morning-logo.png" ]; then
  cp -f paper-morning-logo.png dist/paper-morning-logo.png
fi

echo "Build complete."
echo "App executable: dist/PaperDigest"
echo "Setup executable: dist/PaperDigestSetup"
echo "One-click local UI executable: dist/PaperDigestLocalUI"
echo "Support files: dist/.env.example, dist/google_oauth_bundle.template.json, dist/user_topics.template.json, dist/paper-morning-logo.png, dist/MANUAL_KR.md, dist/README.md, dist/LICENSE, dist/PRIVACY.md, dist/VERSION, dist/CHANGELOG.md, dist/register_task.ps1"

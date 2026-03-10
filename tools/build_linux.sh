#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
cd "$REPO_ROOT"

echo "Installing runtime dependencies..."
"$PYTHON_EXE" -m pip install -r "$REPO_ROOT/deps/requirements.txt"

echo "Installing build dependency (PyInstaller)..."
"$PYTHON_EXE" -m pip install pyinstaller

echo "Building PaperDigest ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigest \
  --clean \
  --noconfirm \
  --onefile \
  "$REPO_ROOT/app/paper_digest_app.py"

echo "Building PaperDigestSetup ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigestSetup \
  --clean \
  --noconfirm \
  --onefile \
  "$REPO_ROOT/app/onboarding_wizard.py"

echo "Building PaperDigestLocalUI ..."
"$PYTHON_EXE" -m PyInstaller \
  --name PaperDigestLocalUI \
  --clean \
  --noconfirm \
  --onefile \
  "$REPO_ROOT/app/local_ui_launcher.py"

echo "Cleaning generated local config files from dist ..."
rm -f "$DIST_DIR/.env" "$DIST_DIR/user_topics.json"

echo "Copying support files to dist ..."
cp -f "$REPO_ROOT/config/.env.example" "$DIST_DIR/.env.example"
cp -f "$REPO_ROOT/templates/google_oauth_bundle.template.json" "$DIST_DIR/google_oauth_bundle.template.json"
if [ -f "$REPO_ROOT/google_oauth_bundle.json" ]; then
  cp -f "$REPO_ROOT/google_oauth_bundle.json" "$DIST_DIR/google_oauth_bundle.json"
fi
cp -f "$REPO_ROOT/config/user_topics.template.json" "$DIST_DIR/user_topics.template.json"
cp -f "$REPO_ROOT/docs/manuals/MANUAL_KR.md" "$DIST_DIR/MANUAL_KR.md"
cp -f "$REPO_ROOT/docs/manuals/MANUAL_FIRSTTIME_KR.md" "$DIST_DIR/MANUAL_FIRSTTIME_KR.md"
cp -f "$REPO_ROOT/README.md" "$DIST_DIR/README.md"
if [ -f "$REPO_ROOT/docs/manuals/README_KR.md" ]; then
  cp -f "$REPO_ROOT/docs/manuals/README_KR.md" "$DIST_DIR/README_KR.md"
fi
cp -f "$REPO_ROOT/LICENSE" "$DIST_DIR/LICENSE"
cp -f "$REPO_ROOT/PRIVACY.md" "$DIST_DIR/PRIVACY.md"
cp -f "$REPO_ROOT/VERSION" "$DIST_DIR/VERSION"
cp -f "$REPO_ROOT/CHANGELOG.md" "$DIST_DIR/CHANGELOG.md"
cp -f "$REPO_ROOT/tools/register_task.ps1" "$DIST_DIR/register_task.ps1"
if [ -f "$REPO_ROOT/assets/paper-morning-logo.png" ]; then
  cp -f "$REPO_ROOT/assets/paper-morning-logo.png" "$DIST_DIR/paper-morning-logo.png"
fi

echo "Build complete."
echo "App executable: dist/PaperDigest"
echo "Setup executable: dist/PaperDigestSetup"
echo "One-click local UI executable: dist/PaperDigestLocalUI"
echo "Support files: dist/.env.example, dist/google_oauth_bundle.template.json, dist/user_topics.template.json, dist/paper-morning-logo.png, dist/MANUAL_KR.md, dist/MANUAL_FIRSTTIME_KR.md, dist/README.md, dist/README_KR.md, dist/LICENSE, dist/PRIVACY.md, dist/VERSION, dist/CHANGELOG.md, dist/register_task.ps1"

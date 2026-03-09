param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing runtime dependencies..."
& $PythonExe -m pip install -r requirements.txt

Write-Host "Installing build dependency (PyInstaller)..."
& $PythonExe -m pip install pyinstaller

Write-Host "Building PaperDigest.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigest `
    --clean `
    --noconfirm `
    --onefile `
    paper_digest_app.py

Write-Host "Building PaperDigestSetup.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigestSetup `
    --clean `
    --noconfirm `
    --onefile `
    onboarding_wizard.py

Write-Host "Building PaperDigestLocalUI.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigestLocalUI `
    --clean `
    --noconfirm `
    --onefile `
    local_ui_launcher.py

Write-Host "Cleaning generated local config files from dist ..."
$cleanupFiles = @(
    "dist\.env",
    "dist\user_topics.json"
)
foreach ($path in $cleanupFiles) {
    if (Test-Path $path) {
        Remove-Item -Force $path
    }
}

Write-Host "Copying support files to dist ..."
Copy-Item -Force .env.example dist\.env.example
Copy-Item -Force google_oauth_bundle.template.json dist\google_oauth_bundle.template.json
if (Test-Path "google_oauth_bundle.json") {
    Copy-Item -Force google_oauth_bundle.json dist\google_oauth_bundle.json
}
Copy-Item -Force user_topics.template.json dist\user_topics.template.json
Copy-Item -Force MANUAL_KR.md dist\MANUAL_KR.md
Copy-Item -Force MANUAL_FIRSTTIME_KR.md dist\MANUAL_FIRSTTIME_KR.md
Copy-Item -Force README.md dist\README.md
if (Test-Path "README_KR.md") {
    Copy-Item -Force README_KR.md dist\README_KR.md
}
Copy-Item -Force LICENSE dist\LICENSE
Copy-Item -Force PRIVACY.md dist\PRIVACY.md
Copy-Item -Force VERSION dist\VERSION
Copy-Item -Force CHANGELOG.md dist\CHANGELOG.md
Copy-Item -Force register_task.ps1 dist\register_task.ps1
if (Test-Path "paper-morning-logo.png") {
    Copy-Item -Force paper-morning-logo.png dist\paper-morning-logo.png
}

Write-Host "Build complete."
Write-Host "App executable: dist\PaperDigest.exe"
Write-Host "Setup executable: dist\PaperDigestSetup.exe"
Write-Host "One-click local UI executable: dist\PaperDigestLocalUI.exe"
Write-Host "Support files: dist\.env.example, dist\google_oauth_bundle.template.json, dist\user_topics.template.json, dist\paper-morning-logo.png, dist\MANUAL_KR.md, dist\MANUAL_FIRSTTIME_KR.md, dist\README.md, dist\README_KR.md, dist\LICENSE, dist\PRIVACY.md, dist\VERSION, dist\CHANGELOG.md, dist\register_task.ps1"

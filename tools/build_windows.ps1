param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $RepoRoot

Write-Host "Installing runtime dependencies..."
& $PythonExe -m pip install -r (Join-Path $RepoRoot "deps\requirements.txt")

Write-Host "Installing build dependency (PyInstaller)..."
& $PythonExe -m pip install pyinstaller

Write-Host "Building PaperDigest.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigest `
    --clean `
    --noconfirm `
    --onefile `
    (Join-Path $RepoRoot "app\paper_digest_app.py")

Write-Host "Building PaperDigestSetup.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigestSetup `
    --clean `
    --noconfirm `
    --onefile `
    (Join-Path $RepoRoot "app\onboarding_wizard.py")

Write-Host "Building PaperDigestLocalUI.exe ..."
& $PythonExe -m PyInstaller `
    --name PaperDigestLocalUI `
    --clean `
    --noconfirm `
    --onefile `
    (Join-Path $RepoRoot "app\local_ui_launcher.py")

Write-Host "Cleaning generated local config files from dist ..."
$cleanupFiles = @(
    (Join-Path $RepoRoot "dist\.env"),
    (Join-Path $RepoRoot "dist\user_topics.json")
)
foreach ($path in $cleanupFiles) {
    if (Test-Path $path) {
        Remove-Item -Force $path
    }
}

Write-Host "Copying support files to dist ..."
$distDir = Join-Path $RepoRoot "dist"
Copy-Item -Force (Join-Path $RepoRoot "config\.env.example") (Join-Path $distDir ".env.example")
Copy-Item -Force (Join-Path $RepoRoot "templates\google_oauth_bundle.template.json") (Join-Path $distDir "google_oauth_bundle.template.json")
if (Test-Path (Join-Path $RepoRoot "google_oauth_bundle.json")) {
    Copy-Item -Force (Join-Path $RepoRoot "google_oauth_bundle.json") (Join-Path $distDir "google_oauth_bundle.json")
}
Copy-Item -Force (Join-Path $RepoRoot "config\user_topics.template.json") (Join-Path $distDir "user_topics.template.json")
Copy-Item -Force (Join-Path $RepoRoot "docs\manuals\MANUAL_KR.md") (Join-Path $distDir "MANUAL_KR.md")
Copy-Item -Force (Join-Path $RepoRoot "docs\manuals\MANUAL_FIRSTTIME_KR.md") (Join-Path $distDir "MANUAL_FIRSTTIME_KR.md")
Copy-Item -Force (Join-Path $RepoRoot "README.md") (Join-Path $distDir "README.md")
if (Test-Path (Join-Path $RepoRoot "docs\manuals\README_KR.md")) {
    Copy-Item -Force (Join-Path $RepoRoot "docs\manuals\README_KR.md") (Join-Path $distDir "README_KR.md")
}
Copy-Item -Force (Join-Path $RepoRoot "LICENSE") (Join-Path $distDir "LICENSE")
Copy-Item -Force (Join-Path $RepoRoot "PRIVACY.md") (Join-Path $distDir "PRIVACY.md")
Copy-Item -Force (Join-Path $RepoRoot "VERSION") (Join-Path $distDir "VERSION")
Copy-Item -Force (Join-Path $RepoRoot "CHANGELOG.md") (Join-Path $distDir "CHANGELOG.md")
Copy-Item -Force (Join-Path $RepoRoot "tools\register_task.ps1") (Join-Path $distDir "register_task.ps1")
if (Test-Path (Join-Path $RepoRoot "assets\paper-morning-logo.png")) {
    Copy-Item -Force (Join-Path $RepoRoot "assets\paper-morning-logo.png") (Join-Path $distDir "paper-morning-logo.png")
}

Write-Host "Build complete."
Write-Host "App executable: dist\PaperDigest.exe"
Write-Host "Setup executable: dist\PaperDigestSetup.exe"
Write-Host "One-click local UI executable: dist\PaperDigestLocalUI.exe"
Write-Host "Support files: dist\.env.example, dist\google_oauth_bundle.template.json, dist\user_topics.template.json, dist\paper-morning-logo.png, dist\MANUAL_KR.md, dist\MANUAL_FIRSTTIME_KR.md, dist\README.md, dist\README_KR.md, dist\LICENSE, dist\PRIVACY.md, dist\VERSION, dist\CHANGELOG.md, dist\register_task.ps1"
Pop-Location

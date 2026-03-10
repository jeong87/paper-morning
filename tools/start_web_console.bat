@echo off
set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
python "%REPO_ROOT%\app\local_ui_launcher.py" --host 127.0.0.1 --port 5050

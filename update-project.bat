@echo off
setlocal EnableExtensions
chcp 936 >nul
set "PROJECT_DIR=%~dp0"
if not exist "%PROJECT_DIR%.venv\Scripts\python.exe" (
    echo [ERROR] Missing .venv. Follow docs/WINDOWS_MIGRATION_SETUP.md first.
    pause
    exit /b 1
)
"%PROJECT_DIR%.venv\Scripts\python.exe" "%PROJECT_DIR%backend\scripts\update_project.py" %*
set "UPDATE_EXIT_CODE=%ERRORLEVEL%"
if not "%BS_HFN_UPDATE_NO_PAUSE%"=="1" pause
exit /b %UPDATE_EXIT_CODE%

@echo off
setlocal EnableExtensions
chcp 936 >nul

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "CELERY_EXE=%PROJECT_ROOT%.venv\Scripts\celery.exe"
set "FFMPEG_EXE=%PROJECT_ROOT%tools\ffmpeg\bin\ffmpeg.exe"
set "FFPROBE_EXE=%PROJECT_ROOT%tools\ffmpeg\bin\ffprobe.exe"

echo.
echo [BS_HFN] 正在检查开发环境...

if not exist "%BACKEND_DIR%\.env" (
    echo [错误] 缺少 backend\.env。
    goto :failed
)

if not exist "%PYTHON_EXE%" (
    echo [错误] 缺少项目 Python 环境：.venv\Scripts\python.exe
    goto :failed
)

if not exist "%CELERY_EXE%" (
    echo [错误] 缺少 Celery：.venv\Scripts\celery.exe
    goto :failed
)

if not exist "%FFMPEG_EXE%" (
    echo [错误] 缺少项目 FFmpeg：tools\ffmpeg\bin\ffmpeg.exe
    goto :failed
)

if not exist "%FFPROBE_EXE%" (
    echo [错误] 缺少项目 ffprobe：tools\ffmpeg\bin\ffprobe.exe
    goto :failed
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 npm，请先安装 Node.js 并将 npm 加入 PATH。
    goto :failed
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [错误] 前端依赖尚未安装，请先在 frontend 目录运行 npm install。
    goto :failed
)

echo [通过] Python、Celery、npm、前端依赖与项目 FFmpeg 均已就绪。
findstr /B /I /C:"VIDEO_PROCESSING_ASYNC=true" "%BACKEND_DIR%\.env" >nul
if errorlevel 1 echo [提示] 当前未启用异步视频处理，Celery 终端仍会启动并等待任务。

if /I "%~1"=="--check" (
    echo [完成] 检查模式不会启动任何任务终端。
    exit /b 0
)

echo.
echo [BS_HFN] 正在分别启动三个任务终端...
start "BS_HFN - Flask API" /D "%BACKEND_DIR%" "%ComSpec%" /k ""%PYTHON_EXE%" run.py"
start "BS_HFN - Celery Worker" /D "%BACKEND_DIR%" "%ComSpec%" /k ""%CELERY_EXE%" -A celery_worker.celery_app worker --pool=solo --loglevel=INFO"
start "BS_HFN - Vue Frontend" /D "%FRONTEND_DIR%" "%ComSpec%" /k "call npm run dev"

echo [完成] 已打开 Flask、Celery 和 Vue/Vite 三个独立终端。
echo [地址] 前端请查看 Vue/Vite 终端输出，API 默认为 http://127.0.0.1:5000
exit /b 0

:failed
echo.
echo [失败] 环境检查未通过，未启动任何任务。
pause
exit /b 1

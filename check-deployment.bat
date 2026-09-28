@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "CELERY_EXE=%PROJECT_ROOT%.venv\Scripts\celery.exe"
set "ENV_FILE=%BACKEND_DIR%\.env"
set "FFMPEG_EXE=%PROJECT_ROOT%tools\ffmpeg\bin\ffmpeg.exe"
set "FFPROBE_EXE=%PROJECT_ROOT%tools\ffmpeg\bin\ffprobe.exe"
set "EXPECTED_REVISION=a7d9e2c4f6b8"
set "EXPECTED_TABLES=26"
set /a PASS_COUNT=0
set /a WARN_COUNT=0
set /a FAIL_COUNT=0
set "NO_PAUSE=0"
set "QUICK_MODE=0"

for %%A in (%*) do (
    if /I "%%~A"=="--no-pause" set "NO_PAUSE=1"
    if /I "%%~A"=="--quick" set "QUICK_MODE=1"
)

echo.
echo ============================================================
echo BS_HFN 部署电脑环境检测
echo 项目目录：%PROJECT_ROOT%
echo 本脚本只读取配置和服务状态，不修改数据库业务数据。
echo ============================================================
echo.

echo [1/9] 检查操作系统和项目目录
ver
if /I "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    call :pass "64 位 Windows 环境"
) else if /I "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
    call :pass "64 位 Windows 环境"
) else (
    call :fail "需要 64 位 Windows 环境"
)
call :require_file "%BACKEND_DIR%\run.py" "后端入口 backend\run.py"
call :require_file "%BACKEND_DIR%\requirements.txt" "后端依赖清单"
call :require_file "%FRONTEND_DIR%\package.json" "前端依赖清单"
call :require_file "%PROJECT_ROOT%start-dev.bat" "项目启动脚本"
call :require_dir "%BACKEND_DIR%\media" "媒体目录"
echo.

echo [2/9] 检查 Python 虚拟环境和后端依赖
set "PYTHON_OK=0"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] >= (3,10) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
    if errorlevel 1 (
        call :fail "项目虚拟环境必须使用 64 位 Python 3.10 或更高版本"
    ) else (
        for /f "delims=" %%V in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PYTHON_VERSION=%%V"
        call :pass "项目 Python 可用：!PYTHON_VERSION!"
        set "PYTHON_OK=1"
    )
) else (
    call :fail "缺少 .venv\Scripts\python.exe；请在新电脑重建虚拟环境"
)

if "!PYTHON_OK!"=="1" (
    "%PYTHON_EXE%" -c "import flask,flask_sqlalchemy,flask_migrate,flask_jwt_extended,pymysql,redis,celery,dotenv" >nul 2>&1
    if errorlevel 1 (
        call :fail "后端依赖不完整；请执行 python -m pip install -r backend\requirements.txt"
    ) else (
        call :pass "Flask、SQLAlchemy、MySQL、Redis、Celery 依赖可导入"
    )
    if "!QUICK_MODE!"=="0" (
        "%PYTHON_EXE%" -m pip check >nul 2>&1
        if errorlevel 1 (
            call :fail "Python 依赖存在版本冲突；请手动运行 python -m pip check"
        ) else (
            call :pass "Python 依赖一致性检查"
        )
    ) else (
        call :warn "快速模式已跳过 pip check"
    )
)
echo.

echo [3/9] 检查 backend\.env 配置
set "ENV_OK=0"
if not exist "%ENV_FILE%" (
    call :fail "缺少 backend\.env；不能只保留 .env.example"
) else if "!PYTHON_OK!"=="0" (
    call :fail "Python 不可用，无法安全解析 backend\.env"
) else (
    "%PYTHON_EXE%" -c "from dotenv import dotenv_values; c=dotenv_values(r'%ENV_FILE%'); required=('FLASK_ENV','SECRET_KEY','JWT_SECRET_KEY','DB_HOST','DB_PORT','DB_USER','DB_PASSWORD','DB_NAME','REDIS_URL','FFMPEG_BIN','FFPROBE_BIN'); missing=[k for k in required if not str(c.get(k) or '').strip()]; markers=('replace-with','change-me','set-a-strong'); weak=[k for k,v in c.items() if any(m in str(v).lower() for m in markers)]; short=[k for k in ('SECRET_KEY','JWT_SECRET_KEY') if len(str(c.get(k) or '')) < 32]; print('MISSING='+','.join(missing) if missing else ''); print('PLACEHOLDER='+','.join(weak) if weak else ''); print('SHORT_SECRET='+','.join(short) if short else ''); raise SystemExit(1 if missing or weak or short else 0)"
    if errorlevel 1 (
        call :fail "backend\.env 存在缺项、模板值或长度不足 32 位的密钥"
    ) else (
        call :pass "backend\.env 必填项、模板值和密钥长度检查"
        set "ENV_OK=1"
    )
)
echo.

echo [4/9] 检查 Node.js、npm 和前端依赖
set "NODE_OK=0"
where node >nul 2>&1
if errorlevel 1 (
    call :fail "未找到 Node.js；请安装 64 位 Node.js 18 或更高版本"
) else (
    node -e "const major=Number(process.versions.node.split('.')[0]); process.exit(major>=18?0:1)" >nul 2>&1
    if errorlevel 1 (
        call :fail "Node.js 版本过低，需要 18 或更高版本"
    ) else (
        for /f "delims=" %%V in ('node --version') do set "NODE_VERSION=%%V"
        call :pass "Node.js 可用：!NODE_VERSION!"
        set "NODE_OK=1"
    )
)
where npm >nul 2>&1
if errorlevel 1 (
    call :fail "未找到 npm，或 npm 未加入 PATH"
) else (
    for /f "delims=" %%V in ('call npm --version 2^>nul') do set "NPM_VERSION=%%V"
    call :pass "npm 可用：!NPM_VERSION!"
)
if not exist "%FRONTEND_DIR%\node_modules" (
    call :fail "前端依赖未安装；请在 frontend 目录执行 npm ci"
) else (
    call :pass "frontend\node_modules 已存在"
    if "!QUICK_MODE!"=="0" (
        pushd "%FRONTEND_DIR%"
        call npm ls --depth=0 >nul 2>&1
        if errorlevel 1 (
            popd
            call :fail "前端依赖树异常；请执行 npm ci 后重试"
        ) else (
            popd
            call :pass "前端依赖树检查"
        )
    ) else (
        call :warn "快速模式已跳过 npm 依赖树检查"
    )
)
echo.

echo [5/9] 检查项目内 FFmpeg 和 ffprobe
if exist "%FFMPEG_EXE%" (
    "%FFMPEG_EXE%" -version >nul 2>&1
    if errorlevel 1 (call :fail "项目内 FFmpeg 无法执行") else (call :pass "项目内 FFmpeg 可执行")
) else (
    call :fail "缺少 tools\ffmpeg\bin\ffmpeg.exe"
)
if exist "%FFPROBE_EXE%" (
    "%FFPROBE_EXE%" -version >nul 2>&1
    if errorlevel 1 (call :fail "项目内 ffprobe 无法执行") else (call :pass "项目内 ffprobe 可执行")
) else (
    call :fail "缺少 tools\ffmpeg\bin\ffprobe.exe"
)
echo.

echo [6/9] 检查 MySQL、数据库结构和 Redis
where mysql >nul 2>&1
if errorlevel 1 (call :warn "mysql.exe 未加入 PATH；应用仍可连接，但命令行维护不方便") else (call :pass "mysql.exe 已加入 PATH")
where mysqldump >nul 2>&1
if errorlevel 1 (call :fail "mysqldump.exe 未加入 PATH，无法执行安全备份和迁移") else (call :pass "mysqldump.exe 已加入 PATH")

if "!PYTHON_OK!"=="1" if "!ENV_OK!"=="1" (
    pushd "%BACKEND_DIR%"
    "%PYTHON_EXE%" -c "from app import create_app; from app.extensions import db; from sqlalchemy import inspect,text; a=create_app(); c=a.app_context(); c.push(); revision=db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one(); tables=len([n for n in inspect(db.engine).get_table_names() if n not in ('alembic_version',)]); print('DATABASE_REVISION='+revision); print('BUSINESS_TABLES='+str(tables)); raise SystemExit(0 if revision=='%EXPECTED_REVISION%' and tables==%EXPECTED_TABLES% else 1)"
    if errorlevel 1 (
        call :fail "MySQL 连接失败，或数据库迁移版本/业务表数量不匹配"
    ) else (
        call :pass "MySQL 连接、迁移版本和 26 张业务表检查"
    )
    "%PYTHON_EXE%" -c "from app import create_app; a=create_app(); raise SystemExit(0 if a.extensions['redis'].ping() else 1)" >nul 2>&1
    if errorlevel 1 (
        call :fail "Redis 无法连接；登录认证和异步任务将不能正常工作"
    ) else (
        call :pass "Redis 连接和 PING 检查"
    )
    popd
) else (
    call :fail "配置或 Python 未通过，已跳过 MySQL 与 Redis 实际连接检查"
)
echo.

echo [7/9] 检查 Celery 和演示数据完整性
findstr /B /I /C:"VIDEO_PROCESSING_ASYNC=true" "%ENV_FILE%" >nul 2>&1
if errorlevel 1 (
    call :pass "当前为同步视频处理，不强制检查 Celery 启动入口"
) else if exist "%CELERY_EXE%" (
    "%CELERY_EXE%" --version >nul 2>&1
    if errorlevel 1 (call :fail "Celery 入口存在但无法执行") else (call :pass "异步视频模式所需 Celery 可执行")
) else (
    call :fail "已启用异步视频处理，但缺少 .venv\Scripts\celery.exe"
)

if "!PYTHON_OK!"=="1" if "!ENV_OK!"=="1" (
    pushd "%BACKEND_DIR%"
    "%PYTHON_EXE%" -X utf8 -m scripts.seed_demo --check >nul 2>&1
    if errorlevel 1 (
        call :fail "演示数据或演示媒体基线检查失败；请运行对应命令查看详情"
    ) else (
        call :pass "演示数据、课程班级和演示媒体检查"
    )
    popd
)
echo.

echo [8/9] 检查备份和私有交付文件
set "LATEST_BACKUP="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%BACKEND_DIR%\backups\*.sql" 2^>nul') do if not defined LATEST_BACKUP set "LATEST_BACKUP=%%F"
if defined LATEST_BACKUP (
    call :pass "已找到数据库备份：!LATEST_BACKUP!"
) else (
    call :fail "backend\backups 中没有 SQL 备份"
)
if exist "%BACKEND_DIR%\demo-data-report.json" (call :pass "演示数据 ID 报告存在") else (call :fail "缺少 backend\demo-data-report.json")
if exist "%PROJECT_ROOT%账号密码.txt" (call :pass "本地答辩账号说明存在") else (call :warn "未找到账号密码.txt；不影响启动，但会影响现场切换账号")
if exist "%PROJECT_ROOT%docs\WINDOWS_MIGRATION_SETUP.md" (call :pass "换电脑迁移手册存在") else (call :warn "缺少换电脑迁移手册")
echo.

echo [9/9] 检查前端生产构建
if "!QUICK_MODE!"=="1" (
    call :warn "快速模式已跳过前端生产构建"
) else if "!NODE_OK!"=="1" if exist "%FRONTEND_DIR%\node_modules" (
    pushd "%FRONTEND_DIR%"
    call npm run build >nul 2>&1
    if errorlevel 1 (
        popd
        call :fail "前端生产构建失败；请在 frontend 目录运行 npm run build 查看详情"
    ) else (
        popd
        call :pass "前端生产构建"
    )
) else (
    call :fail "Node.js 或前端依赖不可用，无法执行生产构建"
)

echo.
echo ============================================================
echo 检测完成：通过 !PASS_COUNT! 项，警告 !WARN_COUNT! 项，失败 !FAIL_COUNT! 项。
if !FAIL_COUNT! EQU 0 (
    echo [结论] 部署环境检查通过，可以继续运行 start-dev.bat。
    set "FINAL_CODE=0"
) else (
    echo [结论] 部署环境检查未通过，请先处理所有 [失败] 项。
    set "FINAL_CODE=1"
)
if !WARN_COUNT! GTR 0 echo [提示] [警告] 不一定阻止启动，但建议在答辩前处理。
echo ============================================================
echo.

if "!NO_PAUSE!"=="0" pause
exit /b !FINAL_CODE!

:require_file
if exist "%~1" (call :pass "%~2") else (call :fail "缺少 %~2")
exit /b 0

:require_dir
if exist "%~1\" (call :pass "%~2") else (call :fail "缺少 %~2")
exit /b 0

:pass
set /a PASS_COUNT+=1
echo [通过] %~1
exit /b 0

:warn
set /a WARN_COUNT+=1
echo [警告] %~1
exit /b 0

:fail
set /a FAIL_COUNT+=1
echo [失败] %~1
exit /b 0

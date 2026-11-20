"""更新已有 Windows 部署；保留配置和业务数据，不自动停止服务或覆盖本地改动。"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'


def run(command, *, cwd=ROOT, capture=False):
    result = subprocess.run([str(x) for x in command], cwd=str(cwd), check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            text=True, encoding='utf-8', errors='replace')
    return result.stdout.strip() if capture else ''


def require_clean_checkout():
    if run(['git', 'rev-parse', '--is-inside-work-tree'], capture=True) != 'true':
        raise RuntimeError('当前目录不是 Git 工作区，请按迁移手册先取得仓库')
    if run(['git', 'branch', '--show-current'], capture=True) != 'main':
        raise RuntimeError('仅支持 main 分支更新，请先核对并切换分支')
    if run(['git', 'status', '--porcelain', '--untracked-files=all'], capture=True):
        raise RuntimeError('发现未提交或未跟踪文件，请先备份并提交/移出；脚本不会 reset、clean 或自动 stash')
    remote = run(['git', 'remote', 'get-url', 'origin'], capture=True).rstrip('/')
    if remote not in {'git@github.com:3198073725/BS_HFN.git', 'https://github.com/3198073725/BS_HFN.git', 'https://github.com/3198073725/BS_HFN'}:
        raise RuntimeError('origin 不是预期的 BS_HFN 仓库，请先人工核对远程地址')


def require_stopped_services():
    for port in (5000, 5173, 4173):
        with socket.socket() as connection:
            connection.settimeout(0.3)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'本地 {port} 端口仍在运行，请先关闭 Flask、Vite/preview 后重试')
    if os.name == 'nt':
        workers = run(['powershell.exe', '-NoProfile', '-Command',
                       "@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*celery_worker.celery_app*' } | Select-Object -ExpandProperty ProcessId) | ConvertTo-Json -Compress"], capture=True)
        if workers and json.loads(workers):
            raise RuntimeError('Celery 仍在运行，请先停止工作进程，避免更新期间继续写入数据库')


def preflight():
    if not PYTHON.is_file() or sys.version_info < (3, 10):
        raise RuntimeError('需要本机创建的 Python 3.10+ .venv，不能复制其他电脑的虚拟环境')
    if not (BACKEND / '.env').is_file():
        raise RuntimeError('缺少 backend/.env；本脚本只更新已有部署，不创建或覆盖数据库连接配置')
    for command in ('git', 'mysqldump'):
        if not shutil.which(command):
            raise RuntimeError(f'缺少 {command}，请先加入 PATH')
    npm = (shutil.which('npm.cmd') or shutil.which('npm.exe') or shutil.which('npm')) if os.name == 'nt' else shutil.which('npm')
    if not npm:
        raise RuntimeError('缺少 npm，请先安装 Node.js 并激活 NVM 版本')
    # 通过实际执行检测 NVM shim，而非只判断文件存在。
    run([npm, '--version'])
    run(['node', '--version'])
    run([PYTHON, '-c', 'import flask,flask_migrate,pymysql,dotenv'], cwd=BACKEND)
    for name in ('ffmpeg.exe', 'ffprobe.exe'):
        if not (ROOT / 'tools' / 'ffmpeg' / 'bin' / name).is_file():
            raise RuntimeError(f'缺少 tools/ffmpeg/bin/{name}，请从原电脑复制便携 FFmpeg')
    require_clean_checkout()
    require_stopped_services()
    return npm


def merge_ai_environment(path):
    text = path.read_text(encoding='utf-8-sig')
    keys = set(re.findall(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', text, flags=re.MULTILINE))
    defaults = {
        'DEEPSEEK_API_KEY': '',
        'DEEPSEEK_BASE_URL': 'https://api.deepseek.com',
        'DEEPSEEK_MODEL': 'deepseek-chat',
        'WHISPER_MODEL': '../tools/whisper-small',
        'WHISPER_DEVICE': 'cpu',
        'WHISPER_COMPUTE_TYPE': 'int8',
    }
    missing = [f'{key}={value}' for key, value in defaults.items() if key not in keys]
    if missing:
        with path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write('\n\n# 视频字幕与 DeepSeek 总结（补充缺失项，保留原配置）\n' + '\n'.join(missing) + '\n')
    print('AI 配置检查完成；已有值未覆盖，密钥不会输出到终端。')


SNAPSHOT_CODE = """
import json,sys
from pathlib import Path
from sqlalchemy import inspect,text
from app import create_app
from app.extensions import db
from scripts.seed_demo import backup_mysql
app=create_app()
with app.app_context():
    backup=backup_mysql(app)
    print('数据库备份：',backup)
    names=[n for n in inspect(db.engine).get_table_names() if n!='alembic_version']
    quote=db.engine.dialect.identifier_preparer.quote
    counts={n:db.session.execute(text('SELECT COUNT(*) FROM '+quote(n))).scalar_one() for n in names}
    progress=list(db.session.execute(text('SELECT COALESCE(SUM(watch_duration),0),COALESCE(SUM(progress),0) FROM learning_record')).one())
    Path(sys.argv[1]).write_text(json.dumps({'counts':counts,'learning_totals':[str(x) for x in progress]}),encoding='utf-8')
"""

VERIFY_CODE = """
import json,sys
from pathlib import Path
from sqlalchemy import inspect,text
from app import create_app
from app.extensions import db
app=create_app()
with app.app_context():
    before=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    quote=db.engine.dialect.identifier_preparer.quote
    after={n:db.session.execute(text('SELECT COUNT(*) FROM '+quote(n))).scalar_one() for n in before['counts']}
    progress=[str(x) for x in db.session.execute(text('SELECT COALESCE(SUM(watch_duration),0),COALESCE(SUM(progress),0) FROM learning_record')).one()]
    if after!=before['counts'] or progress!=before['learning_totals']:
        raise RuntimeError('迁移后原有表行数或学习累计值不一致；请保留备份，不要启动应用')
    print('原有业务表行数、学习时长与学习进度累计值校验通过。')
"""

COURSE_POLICY_CODE = """
from app import create_app
from app.extensions import db
from app.models import Course,CourseAISummary
app=create_app()
with app.app_context():
    courses=db.session.scalars(db.select(Course).where(Course.name=='C语言学习')).all()
    if len(courses)==1:
        course=courses[0]
        row=db.session.scalar(db.select(CourseAISummary).where(CourseAISummary.course_id==course.id))
        row=row or CourseAISummary(course_id=course.id,status='DRAFT')
        row.open_to_students=True
        db.session.add(row);db.session.commit()
        print('已为 C语言学习 配置所有学生查看已发布视频总结，课程 ID：',course.id)
    else:
        print('未找到唯一的 C语言学习，跳过开放设置；请按实际课程人工核对。')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只检查更新条件，不拉取、不安装、不迁移')
    parser.add_argument('--skip-model-download', action='store_true', help='模型已复制或使用自定义模型时跳过下载')
    args = parser.parse_args()
    print('项目位置：', ROOT)
    npm = preflight()
    if args.check:
        print('更新条件检查通过。此模式没有修改代码、配置或数据库。')
        return
    before_revision = run(['git', 'rev-parse', 'HEAD'], capture=True)
    print('正在核对远程 main 分支……')
    run(['git', 'fetch', 'origin'])
    try:
        run(['git', 'merge-base', '--is-ancestor', 'HEAD', 'origin/main'], capture=True)
    except subprocess.CalledProcessError:
        raise RuntimeError('本地提交与远程不兼容，请人工处理；脚本不会强制覆盖分支') from None
    backup_dir = BACKEND / 'backups' / ('update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(BACKEND / '.env', backup_dir / 'backend.env')
    (backup_dir / 'previous-commit.txt').write_text(before_revision + '\n', encoding='ascii')
    snapshot = backup_dir / 'row-counts.json'
    # 备份失败即退出，在此之前没有拉取代码、安装依赖或执行迁移。
    run([PYTHON, '-c', SNAPSHOT_CODE, snapshot], cwd=BACKEND)
    print('配置与版本备份目录：', backup_dir)
    run(['git', 'pull', '--ff-only', 'origin', 'main'])
    print('正在安装后端依赖……')
    run([PYTHON, '-m', 'pip', 'install', '-r', BACKEND / 'requirements-ai.txt'])
    merge_ai_environment(BACKEND / '.env')
    if not args.skip_model_download:
        # local_files_only 先验证已经复制的模型；缺失时才调用下载脚本。
        model_check = subprocess.run([str(PYTHON), '-c',
            "from pathlib import Path;from app import create_app;a=create_app();p=Path(a.config['WHISPER_MODEL']);raise SystemExit(0 if p.is_dir() and (p/'model.bin').is_file() and (p/'config.json').is_file() else 1)"], cwd=BACKEND)
        if model_check.returncode:
            from dotenv import dotenv_values
            model = dotenv_values(BACKEND / '.env').get('WHISPER_MODEL', '')
            if model not in {'small', '../tools/whisper-small'}:
                raise RuntimeError('自定义 WHISPER_MODEL 不存在，请复制该模型或修正 .env 后重试')
            if model == 'small':
                # 保留已有模型名配置，同时下载到 WhisperModel('small') 实际使用的缓存。
                run([PYTHON, '-c', "from faster_whisper.utils import download_model; download_model('small'); print('small 模型缓存已准备')"])
            else:
                run([PYTHON, BACKEND / 'scripts' / 'prepare_subtitle_model.py'])
    print('正在迁移并验证数据库……')
    run([PYTHON, '-m', 'flask', '--app', 'run:app', 'db', 'upgrade'], cwd=BACKEND)
    run([PYTHON, '-c', VERIFY_CODE, snapshot], cwd=BACKEND)
    run([PYTHON, '-m', 'flask', '--app', 'run:app', 'db', 'check'], cwd=BACKEND)
    # 先验证旧数据保留，再应用用户指定的课程开放设置，不覆盖正文或发布状态。
    run([PYTHON, '-c', COURSE_POLICY_CODE], cwd=BACKEND)
    print('正在安装并构建前端……')
    run([npm, 'ci'], cwd=ROOT / 'frontend')
    run([npm, 'run', 'build'], cwd=ROOT / 'frontend')
    run([PYTHON, '-m', 'pip', 'check'])
    run(['node', 'scripts/verify-summary-markdown.mjs'], cwd=ROOT / 'frontend')
    print('更新成功，当前版本：', run(['git', 'rev-parse', '--short', 'HEAD'], capture=True))
    print('请填写本机 backend/.env 的 DEEPSEEK_API_KEY，再双击 start-dev.bat。')
    print('已有密钥无需重填。脚本未自动启动服务、生成字幕或调用付费 AI。')
    print('SQL 备份位于 backend/backups；配置快照可能含密钥，请勿上传。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print('更新已停止：', str(exc), file=sys.stderr)
        print('请检查上一条失败命令及 backend/backups；脚本不会自动回滚或覆盖数据库。', file=sys.stderr)
        raise SystemExit(1)

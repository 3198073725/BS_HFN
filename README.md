# 基于 Web 技术与 FFmpeg 的学生课后辅导系统

本仓库是根据 `docs/BS_HFN.md` 与 `docs/BS_HFN数据库文档.md` 重建的课后辅导系统。目前已完成认证权限、课程视频、FFmpeg/HLS、学习进度与答疑、作业、在线测验、公告、实时统计和管理员后台的完整第一版闭环。

## 技术栈

- 前端：Vue 3、Vite、Vue Router、Pinia、Axios、Element Plus、hls.js、Playwright
- 后端：Python、Flask、Flask-SQLAlchemy、Flask-Migrate、Flask-JWT-Extended
- 数据与任务：MySQL 8、Redis、Celery
- 视频处理：FFmpeg、ffprobe、HLS

## 项目内 FFmpeg

FFmpeg 已放在项目目录 `tools/ffmpeg` 中：

```text
tools/ffmpeg/bin/ffmpeg.exe
tools/ffmpeg/bin/ffprobe.exe
tools/ffmpeg/bin/ffplay.exe
```

`backend/.env` 使用相对于后端目录的路径，应用启动时会解析为绝对路径，因此整个 `BS_HFN` 项目移动到其他位置后仍可使用。FFmpeg 二进制文件约 300 MB，已通过 `.gitignore` 排除，不会误提交到普通 Git 仓库；复制或打包项目时请保留 `tools/ffmpeg` 目录。

## 目录

```text
backend/   Flask API、数据库模型、Celery 与视频服务
frontend/  Vue 3 单页应用
docs/      当前需求与数据库设计基线
```

## 本地启动

当前机器的 Python、前端依赖、MySQL 数据库、迁移、Redis 和便携版 FFmpeg 已配置好。

推荐直接双击项目根目录的 `start-dev.bat`。脚本使用 Windows ANSI（CP936）编码，会先检查依赖，再为 Flask API、Celery worker 和 Vue/Vite 前端分别打开一个独立终端。

只检查环境而不启动任务：

```powershell
cmd /c start-dev.bat --check
```

后端：

```powershell
cd E:\BS_HFN\backend
..\.venv\Scripts\python.exe run.py
```

前端（另开终端）：

```powershell
cd E:\BS_HFN\frontend
npm run dev
```

浏览器访问 Vite 输出的本地地址。API 默认地址为 `http://127.0.0.1:5000`，健康检查为 `GET /api/health`。

学生登录后可在“我的学习”恢复视频进度并记录时间点笔记或提问，也可提交课程作业、参加自动评分测验并查看个人数据。教师可管理课程与视频、处理答疑、发布和批改作业、组织测验并查看课程统计。管理员可在“系统后台”管理账号和公告。

管理员用户名和首次密码保存在被 Git 忽略的 `backend/.env` 中。不要提交该文件，也不要把其中的密码复制到文档或聊天记录。

## 视频处理模式

默认 `VIDEO_PROCESSING_ASYNC=false`，上传请求内同步完成转码，适合当前开发调试。要启用后台处理：

1. 把 `backend/.env` 中的 `VIDEO_PROCESSING_ASYNC` 改为 `true`。
2. 保持 Redis 运行。
3. 在 `backend` 目录启动 worker：

```powershell
..\.venv\Scripts\celery.exe -A celery_worker.celery_app worker --pool=solo --loglevel=info
```

## 验证

```powershell
cd E:\BS_HFN\backend
$env:RUN_FFMPEG_TEST='1'
..\.venv\Scripts\python.exe -m pytest -q

cd E:\BS_HFN\frontend
npm run build
npm run test:e2e
```

`test:e2e` 会自动启动独立端口的前后端，并使用内存 SQLite 和专用临时账号执行测试，不会读取或修改开发用 MySQL 数据。

异步模式下可执行一次会自动清理数据的真实链路验收：

```powershell
cd E:\BS_HFN\backend
..\.venv\Scripts\python.exe -m scripts.verify_async_video
```

统计页面使用轻量卡片和表格直接呈现聚合结果，当前不依赖图表库，避免为基础数据展示引入不必要的体积与安全维护成本。

接口清单见 `docs/API.md`，后续顺序见 `docs/DEVELOPMENT_PLAN.md`。

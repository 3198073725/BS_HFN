# Windows 换电脑迁移与完整配置手册

> 2026-11-19 补充：已部署电脑更新本次字幕、DeepSeek 和 Markdown 功能，请优先使用 [本次更新指南](UPDATE_2026-11-19.md) 与根目录 update-project.bat。最新数据库为 29 张业务表、迁移 30cc40dd50ee。需要额外安装 backend/requirements-ai.txt，并复制或下载 tools/whisper-small；其余初次迁移步骤仍按本文执行。

更新时间：2026-09-26。适用项目：BS_HFN 本地毕业答辩版。

本文按当前代码、启动脚本与数据库迁移核对编写，不要求公网部署。主流程是把旧电脑的现有账号、课程、班级、视频、附件和演示记录完整搬到新电脑，而不是重新生成一套数据。

本文示例旧目录为 `E:\BS_HFN`，新目录为 `D:\BS_HFN`，数据库为 `student_tutoring`。如果你的实际位置、账号、端口、数据库名不同，必须替换示例。命令中没有提供你的实际密码，不能把“示例密码”当成已配置密码。

## 目录

1. [先读：必须遵守的迁移规则](#1-先读必须遵守的迁移规则)
2. [环境、目录与运行关系](#2-环境目录与运行关系)
3. [旧电脑：冻结操作、备份与复制](#3-旧电脑冻结操作备份与复制)
4. [新电脑：安装 Python、Node.js 和 MySQL](#4-新电脑安装-pythonnodejs-和-mysql)
5. [新电脑：配置 Redis](#5-新电脑配置-redis)
6. [新电脑：重建项目依赖](#6-新电脑重建项目依赖)
7. [新电脑：完整配置 .env](#7-新电脑完整配置-env)
8. [主流程 A：恢复旧电脑的完整数据库](#8-主流程-a恢复旧电脑的完整数据库)
9. [独立流程 B：确实需要从空库重新建立项目](#9-独立流程-b确实需要从空库重新建立项目)
10. [首次启动与日常启动](#10-首次启动与日常启动)
11. [迁移后的完整验收](#11-迁移后的完整验收)
12. [常见故障与排查](#12-常见故障与排查)
13. [离线答辩、备份与回退](#13-离线答辩备份与回退)
14. [最后的勾选清单](#14-最后的勾选清单)
15. [核对依据与官方参考](#15-核对依据与官方参考)

## 1. 先读：必须遵守的迁移规则

### 1.1 不能只复制代码

项目数据分布在不同位置：

| 内容 | 实际位置 | 是否随普通 Git 克隆完整带走 |
| --- | --- | --- |
| 前后端代码、迁移脚本、文档、启动脚本 | 项目目录 | 已提交内容可以；本机未提交修改不可以 |
| 账号、课程、班级、进度、成绩、通知 | MySQL 数据库 | 不可以，必须导出 SQL |
| 视频原文件、处理后文件、HLS、封面、头像、教学附件 | `backend/media` 或实际 `MEDIA_ROOT` | 不可以，多数已被忽略 |
| 实际运行参数和密钥 | `backend/.env` | 不可以，已被忽略 |
| FFmpeg 二进制 | `tools/ffmpeg` | 不可以，已被忽略 |
| 演示数据 ID 报告 | `backend/demo-data-report.json` | 不可以，已被忽略 |
| Redis 队列与令牌撤销记录 | Redis 存储 | 不可以，通常不复制旧队列 |
| 未交卷草稿、未补传进度、登录状态 | 旧浏览器的站点存储 | 不可以，不属于项目文件或 SQL |

因此，完整迁移需要“当前代码 + 最新 SQL + 完整媒体 + 实际配置 + FFmpeg”，不能仅下载 Git 仓库压缩包。

### 1.2 不要直接使用旧电脑的虚拟环境

旧 `.venv` 的配置引用旧 Python 安装路径，Celery 等可执行入口也与旧环境绑定。Python 虚拟环境不能作为跨电脑便携运行时，必须在新电脑重建。[Python 官方说明](https://docs.python.org/3.12/library/venv.html)

`frontend/node_modules` 也建议重新安装。代码目录移动后如果沿用旧 `.venv`，即使 `start-dev.bat --check` 看起来通过，也可能在真正执行时失败。

### 1.3 Redis 是必需服务，不只是异步转码的可选项

当前代码使用 Redis 保存 JWT 撤销记录，并在受保护请求中检查令牌。Redis 不可用时按安全策略拒绝请求，可能出现“能打开页面、登录后马上失效或退出失败”。

**即使 `VIDEO_PROCESSING_ASYNC=false`，仍然需要 Redis。** 关闭异步模式只是让转码在上传请求中同步执行，不会关闭认证对 Redis 的依赖。

### 1.4 恢复完整 SQL 与从空库迁移是两条不同路线

- 主流程 A：保留现在全部数据。先建立一个空数据库，再导入最新完整 SQL；不要提前运行业务表迁移或初始化脚本。导入后核对版本。
- 独立流程 B：不要旧数据，从零开始。空数据库运行 Alembic 迁移，然后初始化基础管理员与分类；需要演示数据时再单独生成。

不能把两条路线顺序混用。本文恢复命令仅用于新电脑的空目标库，不授权覆盖任何已有数据库。

### 1.5 保密和回退

SQL 中有个人资料、成绩和密码哈希；`.env` 中有数据库密码、密钥。请使用自己的 U 盘或加密传输，不要发到公开仓库、群聊或公开网盘。私人账号记录如需携带，也单独保管，不作为公开项目附件。

旧电脑保持原样，直到新电脑完成第 11 节验收。不要删除旧数据库、旧媒体、备份或 Redis 数据，也不要为了迁移执行清库、重置密码、删除课程等操作。

## 2. 环境、目录与运行关系

### 2.1 本地运行所需环境

| 项目 | 本次迁移建议 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10/11，64 位 | 本手册、启动脚本和端到端测试路径按 Windows 编写 |
| Python | 3.12，64 位 | 当前旧机器实际为 3.12.0；选择官方提供的 3.12 系列 Windows 安装包，不要求升级到其他大版本 |
| Node.js | 22 LTS，64 位 | 当前旧机器为 18.20.8；本项目 Vite 6 配置允许 22，换机后需执行构建与验收，不能把旧机器结果当新机器结果 |
| npm | 随 Node.js 安装 | 必须使用现有 `package-lock.json` 执行 `npm ci` |
| MySQL Server | 8.0，同系列优先 | 另需 `mysql.exe`、`mysqldump.exe`；Workbench 不是替代数据库服务器的程序 |
| Redis | 现有可信本地安装，或 Docker 中的 Redis | 认证必需，异步队列也依赖它 |
| FFmpeg / ffprobe | 搬迁项目自带 Windows 二进制 | `tools/ffmpeg/bin`，不需要重复下载 |
| 浏览器 | 当前 Chrome 或 Edge | 支持 HLS.js、本地缓存和图表渲染 |
| Git | 可选 | 正常启动不要求 Git，不要求配置 Git 用户名或密码 |
| Playwright Chromium | 仅自动化验收需要 | 普通浏览器访问不需要安装 Playwright 浏览器 |

Node.js 下载来源：[Node.js 22 官方下载](https://nodejs.org/en/download/archive/v22)。Python 下载来源：[Python 官方 Windows 下载](https://www.python.org/downloads/windows/)。

磁盘空间应根据旧目录实际大小准备，而不是只看代码体积；媒体通常占主要空间，迁移包、解压目录和临时转码文件都需要额外空间。建议把项目放在本地可写磁盘的短路径，如 `D:\BS_HFN`，不要放在 `Program Files`、只读 U 盘或会自动同步的云盘目录。

### 2.2 新目录应该长什么样

```text
D:\BS_HFN\
  .venv\                       新电脑创建，不能沿用旧环境
  backend\
    .env                       实际运行配置，不是 .env.example
    .env.example               配置模板
    run.py
    celery_worker.py
    requirements.txt
    app\
    migrations\
    scripts\
    media\                     完整复制旧媒体
      avatars\
      course_covers\
      videos\
        original\
        processed\
        hls\                   不仅有 m3u8，还有其引用的切片
        covers\
      homework\
      exams\
      defense_assets\          演示素材，若原项目有则携带
    backups\
      move-latest.sql          本次新导出的完整备份
    demo-data-report.json      已有演示数据的报告，若有则携带
  frontend\
    package.json
    package-lock.json
    node_modules\              新电脑 npm ci 安装
    src\
    vite.config.js
  tools\
    ffmpeg\bin\
      ffmpeg.exe
      ffprobe.exe
      ffplay.exe
  docs\
  start-dev.bat
  README.md
```

### 2.3 默认端口与进程

| 进程 | 默认地址 | 启动来源 |
| --- | --- | --- |
| MySQL | `127.0.0.1:3306` | Windows 数据库服务 |
| Redis | `127.0.0.1:6379` | 单独启动；项目脚本不启动它 |
| Flask API | `http://127.0.0.1:5000` | `backend/run.py` |
| Celery | 无网页地址 | 独立 worker 终端；Windows 用 `solo` 进程池 |
| Vue / Vite | `http://127.0.0.1:5173` | 前端终端 |
| 隔离自动化测试 | API 5100、前端 4173 | 仅 `npm run test:e2e` 时使用 |

浏览器访问的是 5173，不是 5000。前端通过 Vite 把 `/api` 和 `/media` 代理到 5000。ECharts 依赖在本机 npm 包中，不需要访问外网 CDN。

MySQL、Redis先准备好，再启动后端、Celery、前端。每个任务独立终端是当前脚本行为；Redis 若以 Docker 或 Windows 服务运行，不需要额外可见终端。

## 3. 旧电脑：冻结操作、备份与复制

### 3.1 冻结操作

1. 通知自己或其他正在使用系统的人暂停提交、审批、上传、批改和管理操作。
2. 旧浏览器恢复网络，让未补传学习进度完成补传；处理需要保留的作业/测验草稿。草稿不会随 SQL 自动迁移。
3. 等待真实视频任务完成，不要在转码写入文件时打包媒体。
4. 检查管理员视频处理中心是否还有需要保留的真实等待/处理中任务。虚构演示异常样例可能故意保持这些状态，需要与真实任务区分。
5. 关闭前端、Celery、后端终端。导出 SQL 时保持 MySQL 服务运行。

迁移不需要搬旧 Redis 消息队列。若真实待处理任务仍存在，先让旧机器处理完或保留旧机器供后续恢复，不能假设新 Redis 会自动执行旧任务。

### 3.2 核对数据库信息，不展示密码

在编辑器里自行打开 `E:\BS_HFN\backend\.env`，记下 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_NAME`。密码自行保管，不截图公开，也不要把整个 `.env` 打印到聊天记录。

PowerShell 中检查工具是否存在：

```powershell
Get-Command mysql,mysqldump -ErrorAction SilentlyContinue
```

旧机器当前 MySQL 工具位置是 `C:\Program Files\MySQL\MySQL Server 8.0\bin`。如果 PATH 未配置，可以使用带空格的完整路径：

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' --version
```

### 3.3 导出最新完整 SQL

下列例子连接旧电脑本地 MySQL，使用 root，数据库是 `student_tutoring`。有任意一项不一致就先替换。备份文件名应是本次专用的新名称；若同名文件已经存在，改名，避免覆盖旧备份。

```powershell
cd E:\BS_HFN
New-Item -ItemType Directory -Path .\backend\backups -Force

mysqldump -h 127.0.0.1 -P 3306 -u root -p --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF --hex-blob --default-character-set=utf8mb4 --result-file=E:/BS_HFN/backend/backups/move-latest.sql student_tutoring

if ($LASTEXITCODE -ne 0) { throw 'SQL 导出失败：停止迁移，保留原库并检查报错' }
Get-Item .\backend\backups\move-latest.sql | Select-Object Name,Length,LastWriteTime
Get-FileHash .\backend\backups\move-latest.sql -Algorithm SHA256
```

执行 `-p` 后按提示输入密码，终端不显示密码字符是正常的。不要改成 `-p真实密码`，避免密码进入命令历史。

参数含义：`--single-transaction` 为事务表取得一致性快照；冻结操作还用于保持数据库和文件配套。`--no-tablespaces` 避免不必要的表空间备份权限；`--set-gtid-purged=OFF` 不携带源库 GTID 状态；`--hex-blob` 保留二进制字段；`utf8mb4` 支持中文；`--result-file` 直接由工具写文件，避免 PowerShell `>` 的编码陷阱。[MySQL 官方 mysqldump 文档](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)

必须确认退出码为 0、文件非空，并记录 SHA256。文件非空不等于一定成功，错误退出产生的半截文件不能用于恢复。若失败，保留报错和原库，改用新的文件名重新导出，不要把错误 SQL 当有效备份。

当前 `pre-defense-*.sql` 是历史操作前备份，不能代替这次导出的最新 SQL。

### 3.4 记录原数据库的核对基线

```powershell
mysql -h 127.0.0.1 -P 3306 -u root -p --default-character-set=utf8mb4
```

进入提示符 `mysql>` 后执行以下 SQL。不要连同 `mysql>` 字样一起复制：

```sql
USE student_tutoring;
SELECT DATABASE(), VERSION();
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS total_tables
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';

SELECT 'sys_user' AS table_name, COUNT(*) AS row_count FROM sys_user
UNION ALL SELECT 'course', COUNT(*) FROM course
UNION ALL SELECT 'chapter', COUNT(*) FROM chapter
UNION ALL SELECT 'video', COUNT(*) FROM video
UNION ALL SELECT 'teaching_class', COUNT(*) FROM teaching_class
UNION ALL SELECT 'homework', COUNT(*) FROM homework
UNION ALL SELECT 'homework_submission', COUNT(*) FROM homework_submission
UNION ALL SELECT 'exam', COUNT(*) FROM exam
UNION ALL SELECT 'exam_record', COUNT(*) FROM exam_record
UNION ALL SELECT 'learning_record', COUNT(*) FROM learning_record
UNION ALL SELECT 'learning_progress_receipt', COUNT(*) FROM learning_progress_receipt;
EXIT;
```

当前迁移版本应为 `f6a7b8c9d0e1`，完整当前库应有 27 张表，其中 26 张业务表、1 张 `alembic_version`。记录各表行数供新电脑对照；这些查询不显示个人信息和密码。

### 3.5 复制项目

用资源管理器复制完整项目，或压缩后转移。开启“查看 → 显示 → 隐藏的项目”和“文件扩展名”，核对 `.env` 以及代码中的隐藏配置文件确实带走。

可不携带：`.venv`、`frontend/node_modules`、`frontend/dist`、`frontend/test-results`、`frontend/playwright-report`、`backend/.e2e-media`、缓存目录、`output` 和 `tmp`。这些不是现有业务数据。可以保留它们作记录，但不能依靠旧环境启动。

必须携带第 1 节所列业务文件。若实际配置了自定义 `MEDIA_ROOT`，它可能在项目外，必须另外复制全部文件，不能只复制空的 `backend/media`。

旧电脑当前还有 `E:\Redis`，它不在 `E:\BS_HFN` 中。若使用第 5.1 节可信旧便携安装路线，要另外携带 Redis 可执行程序与配置。不要把旧队列或旧 Redis 持久化文件随意装进新实例。

解压后不要出现 `D:\BS_HFN\BS_HFN\backend` 这样的额外套层。根目录应直接包含 `backend`、`frontend`、`tools` 和 `start-dev.bat`。

### 3.6 核对媒体复制结果

旧电脑执行一次以下查询，把结果自行记录；新电脑在对应目录执行同一查询，文件数量与总字节数应一致。检查期间不要运行上传或转码。

```powershell
cd E:\BS_HFN
$migrationMediaFiles = Get-ChildItem -LiteralPath .\backend\media -File -Recurse
$migrationMediaFiles | Measure-Object -Property Length -Sum | Select-Object Count,Sum
```

这个核验只证明数量和大小一致，不是逐文件内容校验。重要原视频可在两台机器对相同文件分别执行 `Get-FileHash -Algorithm SHA256`，或对整个传输压缩包核对 SHA256。不要仅凭文件夹可打开就认定媒体完整。

## 4. 新电脑：安装 Python、Node.js 和 MySQL

### 4.1 安装 Python

1. 从官方来源取得 Python 3.12 系列的 64 位 Windows 安装包；并非每个后续安全修订版都提供 Windows 安装器，选择页面明确列有 Windows installer 的版本。
2. 安装时勾选 `Add python.exe to PATH`，保留 pip 和 Python Launcher。
3. 安装完成后关闭并重新打开 PowerShell，旧终端不会自动更新 PATH。
4. 检查：

```powershell
py -3.12 --version
py -3.12 -m pip --version
```

若没有 `py` 启动器，使用实际 Python 3.12 的 `python.exe` 完整路径。不要在版本不明的情况下直接用系统 `python` 建环境；部分 Windows 电脑会把它指向应用商店别名或其他版本。

### 4.2 安装 Node.js

安装 Node.js 22 LTS 的 Windows x64 安装包，保留 npm 和 PATH 选项。重开终端：

```powershell
node --version
npm.cmd --version
```

本手册采用 `npm.cmd`，避免 PowerShell 将 `npm` 解析为受执行策略限制的 `npm.ps1`。不需要为启动项目修改整台电脑的执行策略。

### 4.3 安装 MySQL Server

从 MySQL 官方安装来源安装 MySQL Server 8.0。配置向导中：

1. 安装数据库服务器及客户端工具，Workbench 按需安装。
2. 本地答辩使用开发机器配置即可。
3. TCP/IP 端口使用 3306；若已被其他 MySQL 占用，先识别已有服务，或者明确使用其他端口并同步 `.env`。
4. 保留服务器默认支持的认证机制，不要为解决客户端报错随意降级认证。
5. 设置自己的 MySQL root 密码，妥善保存。这是数据库密码，不是平台管理员登录密码。
6. 配置 Windows 服务并启动。服务名常见 `MySQL80`，但以安装时实际名称为准。
7. 仅本机答辩不需要为了运行项目主动开放数据库端口到公网。

Windows 安装要求及向导说明见 [MySQL 官方 Windows 安装文档](https://dev.mysql.com/doc/refman/8.0/en/windows-installation.html)。缺少运行库时按安装器提示从官方来源补装，不要从未知网站下载 DLL。

### 4.4 配置 MySQL 工具 PATH

在 Windows“编辑系统环境变量 → 环境变量 → Path”中添加实际 MySQL `bin` 目录，例如：

```text
C:\Program Files\MySQL\MySQL Server 8.0\bin
```

不要删除已有 PATH 项，也不要把整个 PATH 替换为这一行。重开 PowerShell：

```powershell
mysql --version
mysqldump --version
Get-Service | Where-Object { $_.Name -like '*mysql*' } | Select-Object Name,Status
Test-NetConnection 127.0.0.1 -Port 3306
```

`TcpTestSucceeded=True` 只表示端口可连接，还要用 `mysql -h 127.0.0.1 -P 3306 -u root -p` 确认密码和目标实例正确。

如果客户端不在 PATH，可像旧电脑一样用 `& '完整路径\mysql.exe'` 运行。初始化演示数据和安全升级脚本会查找 `mysqldump`，使用这些脚本前仍要将它加入 PATH。

## 5. 新电脑：配置 Redis

三种方式选择一种，不要让多个实例争用同一 6379 端口。当前只需要本地 Redis，不需要集群或云 Redis。

### 5.1 路线一：复用旧电脑可信便携安装

适合短期本地答辩，前提是旧电脑的程序来源可信，并且在新系统上实际运行成功。旧机器当前 `redis-server.exe` 在 `E:\Redis`。Windows 原生旧版本不等同于官方当前支持的生产方案；如果程序不兼容，转用 Docker 或 WSL，不要从陌生下载站补程序。

把程序和配置复制到例如 `D:\Redis`。如果配置里有旧电脑的 `dir`、日志路径、持久化路径或地址，先在编辑器核对。不要把旧 Redis 直接指定到新项目的媒体目录。

在独立 PowerShell 终端前台运行：

```powershell
cd D:\Redis
.\redis-server.exe --bind 127.0.0.1 --port 6379
```

若该构建不支持这些命令参数，用其可信配置文件设置 `bind 127.0.0.1`、`port 6379`，再按实际文件名启动，例如 `redis-server.exe redis.windows.conf`。这是配置文件存在时的替代方式，不是要求凭空创建同名文件。

另一个终端验证：

```powershell
& 'D:\Redis\redis-cli.exe' -h 127.0.0.1 -p 6379 ping
```

应返回 `PONG`。这个前台窗口需要保持开启；关闭它后，Redis 会停止。此路线不负责自动迁移旧队列或安装 Windows 服务。

### 5.2 路线二：Docker Desktop 中运行 Redis

适合新电脑已经支持并愿意使用 Docker 的情况。先按 [Docker 官方 Windows 安装文档](https://docs.docker.com/desktop/setup/install/windows-install/) 安装，启用其要求的虚拟化/WSL2，必要时重启。Docker 要运行 Linux 容器。[Redis 官方 Docker 说明](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/docker/)

PowerShell 检查：

```powershell
docker version
docker info
docker ps -a
```

确认没有名为 `bs-hfn-redis` 的已有容器，再首次执行：

```powershell
docker pull redis:7.4
docker run -d --name bs-hfn-redis --restart unless-stopped -p 127.0.0.1:6379:6379 -v bs-hfn-redis-data:/data redis:7.4 redis-server --appendonly yes
docker exec bs-hfn-redis redis-cli ping
```

应返回 `PONG`。端口只发布到本机，命名卷用于 Redis 持久化。`redis:7.4` 是示例固定系列，不是项目对这一版本的硬编码要求；先拉取镜像并验收，答辩前不要临时升级。

以后启动已有容器只执行：

```powershell
docker start bs-hfn-redis
docker exec bs-hfn-redis redis-cli ping
```

停止使用 `docker stop bs-hfn-redis`。不要重复执行 `docker run`，也不要删除容器、数据卷或执行清空 Redis 的命令来解决同名报错。Docker Desktop 和容器本身必须运行；配置了重启策略不代表 Docker 引擎关闭后仍能提供服务。

### 5.3 路线三：已有 WSL 环境

已有 Ubuntu/WSL 的用户可按 [Redis 官方 Windows/WSL 安装指引](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/) 安装 Redis。Ubuntu 中常用启动与检查命令为：

```bash
sudo service redis-server start
redis-cli ping
```

这些是 Ubuntu 终端命令，不是 PowerShell 命令。Redis 配置只绑定可信本地地址。WSL 网络行为可能受版本与防火墙影响，最终要从 Windows 的后端环境执行第 7.4 节的 Redis 检查，不能仅凭 WSL 内 `PONG` 就认定 Windows 已可连接。

本项目后端和前端仍按 Windows 启动，不需要为了这一条路线搬进 WSL。不要在没有核对网络设置的情况下把 `REDIS_URL` 写成不稳定的 WSL IP 地址。

### 5.4 新 Redis 的数据边界

通常使用新实例、不导入旧消息。MySQL 恢复后，视频已完成状态和路径仍保留，但旧队列不会自动搬来。剩余真实失败或超过 30 分钟未更新的任务，可在确认原文件存在、新 Celery 正常的前提下，由管理员在视频处理中心人工恢复。

Redis 还保存退出令牌的撤销记录。如果不迁移这些记录，又保持原 JWT 密钥，旧的已撤销但未过期令牌存在重新被接受的风险。换电脑本地演示通常应重新生成 `JWT_SECRET_KEY`，并让所有用户重新登录；这不会修改 MySQL 中的用户密码哈希。不要把旧浏览器登录存储整体复制到新电脑。

若需要严格保留会话与撤销状态，应单独规划一致的 Redis 数据迁移，不在本手册中用“复制 dump.rdb”简单代替。

## 6. 新电脑：重建项目依赖

### 6.1 确定项目目录

```powershell
cd D:\BS_HFN
Get-ChildItem -Name
Test-Path .\backend\run.py
Test-Path .\frontend\package-lock.json
Test-Path .\tools\ffmpeg\bin\ffmpeg.exe
```

后三项应均为 `True`。所有后续命令都要在注明的目录执行。数据库迁移命令尤其要求当前目录是 `backend`。

如果从旧电脑带来了 `.venv`，先把它手动改名为 `.venv-old-machine` 保留，再创建新的 `.venv`；不要在原目录上直接运行创建命令来假设旧环境已被彻底重建，也不要递归删除整个项目。

### 6.2 创建新 Python 环境

```powershell
cd D:\BS_HFN
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

等待安装完成且没有错误。依赖要求使用版本范围而非完整冻结文件，新机器解析的 Python 小版本依赖可能与旧机器不同，所以必须验收。若需要精确复现旧环境，可在旧机单独保存 `pip freeze` 的私人安装记录，在确认来源后使用；不要擅自覆盖项目的 `requirements.txt`。

MySQL 默认认证可能需要 RSA 额外依赖。为新机兼容安装项目允许范围内的扩展：

```powershell
.\.venv\Scripts\python.exe -m pip install 'PyMySQL[rsa]>=1.1,<2'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import flask, sqlalchemy, pymysql, redis, celery; print('后端依赖导入成功')"
Test-Path .\.venv\Scripts\celery.exe
```

`pip check` 应报告没有依赖冲突，Celery 入口应存在。RSA 扩展用于 `sha256_password`/`caching_sha2_password` 认证兼容，不要求关闭数据库安全认证。[PyMySQL 官方安装说明](https://pymysql.readthedocs.io/en/latest/user/installation.html)

本文直接调用虚拟环境可执行文件，不需要 `Activate.ps1`，因此通常也不需要处理 PowerShell 脚本执行策略。

### 6.3 安装前端依赖

```powershell
cd D:\BS_HFN\frontend
npm.cmd ci
npm.cmd run build
```

`npm ci` 根据锁文件安装，可能重新建立已有 `node_modules`；它操作的是依赖目录，不是课程数据。不要删除 `package-lock.json`，也不要用 `npm update` 或 `npm audit fix --force` 来完成迁移。

构建应退出成功。`dist` 是构建结果，并不包含 MySQL、后端服务或完整业务媒体，不能复制它就认为项目已部署。

### 6.4 核对 FFmpeg

```powershell
cd D:\BS_HFN
& '.\tools\ffmpeg\bin\ffmpeg.exe' -version
& '.\tools\ffmpeg\bin\ffprobe.exe' -version
```

应输出版本信息而不是报缺文件或 DLL。相对路径已由后端解析，无须把项目 FFmpeg 加入系统 PATH。旧 `.env` 若使用其他绝对路径，要按第 7 节改回项目内路径。

## 7. 新电脑：完整配置 .env

### 7.1 实际使用哪个文件

后端读取 `backend/.env`，不是只读取 `.env.example`。主流程 A 先把旧 `.env` 私下复制过来，再修改机器相关配置。独立流程 B 可以在资源管理器将 `.env.example` 复制一份并改名为 `.env`，之后逐项替换。

务必开启文件扩展名显示，避免产生 `.env.txt`。用编辑器保存为 UTF-8；`start-dev.bat` 保持原 ANSI/CP936 编码，不能为了编辑 `.env` 顺带转换启动脚本编码。

### 7.2 配置模板

以下是说明模板，不含真实凭据。主流程 A 不要机械地用整段覆盖旧配置，先比较、再替换对应项。每项一行；密码含 `#`、空格等字符时用合适的 dotenv 引号表示，含引号本身时需正确转义，随后执行连接检查。

```dotenv
FLASK_ENV=development
SECRET_KEY="替换为私下生成的随机密钥"
JWT_SECRET_KEY="替换为另一个私下生成的随机密钥"

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD="替换为新电脑MySQL密码"
DB_NAME=student_tutoring

REDIS_URL=redis://127.0.0.1:6379/0
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

FFMPEG_BIN=../tools/ffmpeg/bin/ffmpeg.exe
FFPROBE_BIN=../tools/ffmpeg/bin/ffprobe.exe
MEDIA_ROOT=media

MAX_CONTENT_LENGTH=2147483648
MAX_JSON_CONTENT_LENGTH=1048576
AVATAR_MAX_LENGTH=3145728
HOMEWORK_ATTACHMENT_MAX_LENGTH=52428800
EXAM_ATTACHMENT_MAX_LENGTH=52428800
COURSE_COVER_MAX_LENGTH=5242880
VIDEO_PROCESSING_ASYNC=true

ADMIN_USERNAME=admin
ADMIN_INITIAL_PASSWORD="仅全新初始化时使用的私密初始密码"
```

### 7.3 所有参数含义

| 参数 | 本地配置建议 / 含义 | 迁移注意事项 |
| --- | --- | --- |
| `FLASK_ENV` | `development` | 本地媒体路由依赖 DEBUG；不要仅为了听起来正式改为 production |
| `SECRET_KEY` | 独立随机密钥 | 示例字符串不可当真实密钥；本机私下保存 |
| `JWT_SECRET_KEY` | 另一随机密钥 | 新 Redis 不保留撤销记录时建议轮换，所有旧令牌失效但登录密码不变 |
| `DB_HOST` | `127.0.0.1` | 应是新电脑数据库地址，不是旧电脑 IP |
| `DB_PORT` | `3306` | 必须与新 MySQL 实例一致 |
| `DB_USER` | 本地使用自己的数据库账号 | root 便于本地配置，不代表公网部署权限方案 |
| `DB_PASSWORD` | 新电脑该数据库账号的密码 | 不是学生、教师或平台管理员密码 |
| `DB_NAME` | 本文为 `student_tutoring` | 恢复目标名称必须一致，可改名但要同步配置 |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | `/0` 同时用于当前队列/结果及令牌存储；Redis 必须运行 |
| `CORS_ORIGINS` | 精确列出本地前端 origin，逗号分隔 | 不带页面路径，不用 `*`；实际前端端口应与它一致 |
| `FFMPEG_BIN` | `../tools/ffmpeg/bin/ffmpeg.exe` | 相对于 backend，不是相对于浏览器或项目根目录 |
| `FFPROBE_BIN` | `../tools/ffmpeg/bin/ffprobe.exe` | 同上 |
| `MEDIA_ROOT` | `media` 或省略 | 省略时默认 backend/media；相对目录也以 backend 为基准 |
| `MAX_CONTENT_LENGTH` | `2147483648`，2 GiB 请求上限 | 非剩余磁盘空间；转码还需要额外空间 |
| `MAX_JSON_CONTENT_LENGTH` | `1048576`，1 MiB JSON 上限 | 不是普通附件上限 |
| `AVATAR_MAX_LENGTH` | `3145728`，3 MiB | 头像限制 |
| `HOMEWORK_ATTACHMENT_MAX_LENGTH` | `52428800`，50 MiB | 作业附件限制 |
| `EXAM_ATTACHMENT_MAX_LENGTH` | `52428800`，50 MiB | 测验附件限制 |
| `COURSE_COVER_MAX_LENGTH` | `5242880`，5 MiB | 课程封面限制 |
| `VIDEO_PROCESSING_ASYNC` | 完整转码演示用 `true` | `false` 同步处理仍需要 Redis；改变后重启后端与 worker |
| `ADMIN_USERNAME` | 基础管理员初始化用户名 | 恢复完整 SQL 后不会根据这项自动新增或改用户名 |
| `ADMIN_INITIAL_PASSWORD` | `scripts.seed` 首次建管理员时使用 | 修改这项不会重置已导入管理员的密码 |

可在新项目 Python 环境私下生成两项不同的密钥：

```powershell
cd D:\BS_HFN
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))"
```

将两行分别填入 `SECRET_KEY` 与 `JWT_SECRET_KEY`，不要将输出发给其他人。修改配置后一定重启服务；已运行的进程不会自动保证重新读取全部环境参数。

若终端/系统已设置同名环境变量，它可能优先于 `.env`，因为当前 dotenv 加载不强制覆盖外部变量。遇到“文件改了但实际还连接旧地址”，检查启动终端的变量来源；不要把所有环境变量连同密码打印公开。

前端默认使用 `/api`。本地标准启动不需要另外创建前端 `.env`。若旧前端配置了 `VITE_API_BASE_URL` 或终端设置了 `VITE_BACKEND_TARGET`，要核对它们没有指向旧电脑；标准代理目标是 `http://127.0.0.1:5000`。

### 7.4 用实际后端配置检查 Redis

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe -c "from app import create_app; app=create_app(); print('Redis PING:', app.extensions['redis'].ping())"
```

应输出 `Redis PING: True`。这里使用项目 `.env`，比单独在另一个 Redis 实例执行 PING 更有意义。失败先检查 Redis 和 `REDIS_URL`，不要关闭 JWT 安全校验绕过问题。

## 8. 主流程 A：恢复旧电脑的完整数据库

**这是保留你当前项目数据时应该使用的流程。第 9 节不接着执行。**

### 8.1 验证 SQL 传输

```powershell
cd D:\BS_HFN
Get-Item .\backend\backups\move-latest.sql | Select-Object Name,Length,LastWriteTime
Get-FileHash .\backend\backups\move-latest.sql -Algorithm SHA256
```

新旧 SHA256 应完全一致。不同则停止恢复，重新复制有效备份。确认这个文件是第 3 节新导出的文件，而不是历史备份。

### 8.2 建立空目标库

```powershell
mysql -h 127.0.0.1 -P 3306 -u root -p --default-character-set=utf8mb4
```

在 MySQL 提示符中先检查目标是否已存在：

```sql
SHOW DATABASES LIKE 'student_tutoring';
```

如果存在，不要继续导入。先核对其中是否有需要保留的数据。建议使用新的空目标名称，例如 `student_tutoring_moved`，并同步 `DB_NAME`；不要直接执行 DROP DATABASE，也不要把导入当成无损合并。

确认名称没有占用后：

```sql
CREATE DATABASE student_tutoring
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE student_tutoring;
SHOW TABLES;
```

`SHOW TABLES` 此时应为空。本文导出命令没有 `--databases`，恢复到明确选择的目标库。若你使用其他来源的 SQL，必须先核对其中是否自带 CREATE DATABASE/USE 或危险清库语句，不能直接套用空目标的假设。

### 8.3 导入 SQL

仍在 MySQL 客户端中执行：

```sql
SOURCE D:/BS_HFN/backend/backups/move-latest.sql;
```

这是 MySQL 客户端命令，不能直接贴到普通 PowerShell。使用正斜杠与无空格短路径可减少 Windows 路径转义问题。等待所有语句执行结束，留意任何 `ERROR`；SOURCE 后出现一些成功输出不代表整个恢复一定成功。

SQL dump 通常包含对所导出表的删除和重建语句，必须在空目标执行。不要把它导入有旧业务数据的库。恢复语句和客户端使用方法见 [MySQL 官方恢复 SQL 备份说明](https://dev.mysql.com/doc/refman/8.0/en/reloading-sql-format-dumps.html)。

出现错误时暂停，不启动应用，不反复在半恢复库继续导入。保留日志和备份，分析原因，另建新的空目标重试；不要求删除出错库。

### 8.4 核对版本、表与数据

```sql
SELECT DATABASE();
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS total_tables
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';
SHOW CREATE TABLE learning_progress_receipt;
```

当前预期：`f6a7b8c9d0e1`，27 张表，进度凭据表含 `(student_id, request_id)` 唯一约束。重复执行第 3.4 节的行数查询，与旧电脑冻结时的基线一致，再退出 `EXIT;`。

恢复阶段核对时不要先登录并开始演示，避免登录审计、懒执行超时结算等使部分记录发生变化。行数一致仅是必要检查，不代表所有内容都已逐行比较。

### 8.5 从应用环境核对数据库

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe -m flask --app run.py db heads
..\.venv\Scripts\python.exe -m flask --app run.py db current
..\.venv\Scripts\python.exe -c "from app import create_app; from app.extensions import db; from sqlalchemy import text; app=create_app(); ctx=app.app_context(); ctx.push(); print('数据库连接:', db.session.execute(text('SELECT 1')).scalar()); print('迁移版本:', db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()); ctx.pop()"
```

`heads` 读取代码迁移头，`current` 读取实际数据库版本，两者都应为当前 head。命令必须在 backend 执行，否则可能报 `Path doesn't exist: migrations`，这不是让你执行 `db init` 重建迁移目录的理由。

若导入的确是旧版本 `e5f6a7b8c9d0`，先确定 SQL 不是误拿的历史备份。确实需要保留该旧库并升级时，当前安全增量脚本可在 backend 执行：

```powershell
..\.venv\Scripts\python.exe -X utf8 -m scripts.upgrade_local
```

脚本仅接受预期前置版本，先调用 mysqldump 备份，再加进度去重表并核对旧记录。当前 head 时不重复升级；其他未知版本停止，核对迁移链，不使用 `db stamp head` 伪装已升级。

如果恢复后已经是最新版本，无需执行迁移、`scripts.seed` 或 `scripts.seed_demo`。用户密码来自 SQL 中的密码哈希，不是靠 `.env` 自动重置。

## 9. 独立流程 B：确实需要从空库重新建立项目

**仅用于明确不要旧业务数据的新环境。它不是搬迁保留数据的后续步骤。**

### 9.1 初始化空库结构

先完成 Python、前端、Redis、FFmpeg 和 `.env` 配置，再建立专用新空库，例如 `student_tutoring_fresh`，把 `DB_NAME` 指向它。以下命令在 backend 执行：

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe -m flask --app run.py db upgrade
..\.venv\Scripts\python.exe -m flask --app run.py db current
..\.venv\Scripts\python.exe -X utf8 -m scripts.seed
```

当前 head 应为 `f6a7b8c9d0e1`。`scripts.seed` 只补基础分类及不存在的管理员，需要有效 `ADMIN_INITIAL_PASSWORD`；它不生成全部课程，也不重置已有管理员密码。不要运行 `db init` 或 `db migrate` 重新生成项目迁移文件。

### 9.2 可选：建立丰富演示数据

如果已有完整 `backend/media/defense_assets`，可直接执行演示初始化；若没有素材，先安装仅素材生成需要的 Pillow/reportlab，再生成：

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe -m pip install Pillow reportlab
..\.venv\Scripts\python.exe -X utf8 -m scripts.build_demo_assets
..\.venv\Scripts\python.exe -X utf8 -m scripts.seed_demo
```

素材生成需要项目 FFmpeg、中文字体、可写目录与足够空间；仅在没有需保留旧素材的新环境使用，避免覆盖旧素材。默认输出素材在 `media/defense_assets`，PDF副本在项目 `output/pdf`。不要把旧机器的 Codex 运行时绝对路径复制到新电脑执行。

演示导入只允许开发配置，首次写入前需要 mysqldump 正常备份，单事务新增账号和业务记录。已有完成标记时不会重复新增或重置审批/提交状态，但仍可能生成报告文件。它不是“恢复最新数据”工具，也不能代替 SQL 导入。

使用初始虚构账号时自行参阅 `DEMO_GUIDE.md`，不把初始管理员密码和数据库密码混淆。重新生成不会保留旧电脑已做的审批、学习、批改等业务操作。

## 10. 首次启动与日常启动

### 10.1 首次先检查，不直接双击猜测

```powershell
cd D:\BS_HFN
cmd /c start-dev.bat --check
```

当前启动脚本是 ANSI/CP936 编码。它检查：backend/.env、项目 Python、Celery 入口、FFmpeg、ffprobe、系统 npm 和前端 node_modules 是否存在。**它不验证 Python 真能执行、不确认数据库连接、迁移版本、Redis 可用性、媒体完整性或端口空闲。** 因此还要完成前面独立连接检查。

先保证 MySQL 服务运行、Redis PING 成功，再双击 `start-dev.bat`，或者执行：

```powershell
cmd /c start-dev.bat
```

三个终端分别是 Flask API、Celery Worker、Vue Frontend。打开终端不等于全部服务成功，需要分别看报错和成功提示。不要反复双击，避免多进程争用端口。

### 10.2 手工启动：每个任务独立终端

后端终端：

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe run.py
```

应出现本机 5000 的运行提示。开发调试重载可能启动关联子进程，不要凭看到两个 Python 就盲目杀进程。

Celery 终端：

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\celery.exe -A celery_worker.celery_app worker --pool=solo --loglevel=INFO
```

应看到 Redis 连接、视频任务注册及 worker ready。Windows 使用 `solo`，不要照抄 Linux prefork 命令。Celery 没有可以访问的网页，检查它靠终端日志和视频任务闭环。

前端终端：

```powershell
cd D:\BS_HFN\frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

手动命令加 `--strictPort` 防止端口占用时悄悄换到 5174。现有启动脚本的 `npm run dev` 未加此参数，若输出地址不是 5173，先排查旧前端进程，而不是直接忽略 CORS 配置。

### 10.3 打开应用

```text
前端：http://127.0.0.1:5173
API健康入口：http://127.0.0.1:5000/api/health
```

健康检查返回 `code=200`，data 中含 `status=ok`。这只证明 API 服务在响应，不证明 MySQL/Redis 连接或媒体读取正常；必须登录和执行验收。

用固定 `127.0.0.1` 地址，避免在 localhost 与 127.0.0.1 之间切换导致浏览器存储不同、看起来像退出登录或丢草稿。5173 页面应包含正常样式，不是直接双击 dist/index.html 或源码 HTML。

### 10.4 日常启动与关闭

日常：启动 MySQL → 启动 Redis → 启动脚本 → 检查三个终端 → 打开5173。正常情况不需要每天 npm ci、数据库迁移、导入 SQL 或重建演示数据。

关闭：停止业务操作 → 等待补传/转码完成 → 各应用终端 Ctrl+C → 再按所选方式停止 Redis。Celery 停止时等待正常退出，不在写视频时强制结束。MySQL 服务可按自己的日常习惯保留。

修改 `.env` 后重启后端和 worker；修改前端 Vite 环境配置后重启前端；更换前端代码一般由开发热更新加载，但答辩前应完整重启并验收。

### 10.5 可选：预览生产前端构建

仅用于验证已构建前端，不是完整公网部署。MySQL、Redis、Flask和Celery仍需运行，Flask保持本地 development 才有当前开发媒体路由。

当前项目安装的 Vite 6 中，`preview.proxy` 未显式配置时继承 `server.proxy`，因此预览也使用现有 `/api` 和 `/media` 代理。已核对本地 Vite 实现及 [Vite 官方预览代理说明](https://vite.dev/config/preview-options.html#preview-proxy)，不需要为换机另建代理配置。

另开前端终端执行：

```powershell
cd D:\BS_HFN\frontend
npm.cmd run build
npm.cmd run preview -- --host 127.0.0.1 --port 4174 --strictPort
```

访问 `http://127.0.0.1:4174`。显式选择4174避免与端到端测试4173冲突；不要把预览和开发服务的端口混淆。页面仍需要后端与数据库/Redis，预览成功也要验证登录、接口、视频和附件。使用默认 `/api` 同源代理时无需仅为此预览改CORS；如果自行改成跨域直连API，需另外配置对应origin并验收。

普通本地答辩可继续使用经过验收的 `npm run dev`。双击现有脚本启动的是开发前端，不会自动替你切换到生产构建预览。后端仍是本地开发服务，不能把“前端生产构建预览”描述为“整个系统已生产部署”。

`FLASK_ENV=production` 会关闭当前开发媒体路由，并要求至少32位有效密钥；只改这一项会导致视频/封面缺失。生产部署还需要专门的静态服务、鉴权附件处理和反向代理，超出本次本地换机范围。

## 11. 迁移后的完整验收

### 11.1 基础技术验收

```powershell
cd D:\BS_HFN
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
node --version
npm.cmd --version
Test-NetConnection 127.0.0.1 -Port 3306
Test-NetConnection 127.0.0.1 -Port 6379
Test-NetConnection 127.0.0.1 -Port 5000
Test-NetConnection 127.0.0.1 -Port 5173
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

结合第 7.4 节 Redis 真正 PING、第 8.5 节数据库实际连接与版本检查。没有登录验证前，不能只凭四个端口开放就宣布成功。

### 11.2 业务与前端人工验收

先做非破坏性读取，再用专门演练记录测试写入。不要为了验收删除、替换真实答辩视频或重置主账号密码。

| 角色 / 场景 | 检查内容 | 通过标准 |
| --- | --- | --- |
| 未登录 | 首页、课程中心、教师公开主页 | 课程和封面正确，不暴露教师联系方式 |
| 学生 | 登录、我的学习、收藏 | 原课程存在，缩略图完整，卡片尺寸一致 |
| 学生 | 已加入课程的视频 | 视频真实播放、拖动可用，HLS清单和切片都能加载 |
| 学生 | 班级与入班记录 | 已加入/PENDING等与数据库对应，课程详情状态一致 |
| 学生 | 作业与测验读取 | 任务、原成绩、评语、关闭提交状态保留；已批改不可修改 |
| 学生 | 附件 | PDF、图片、文本可按现有权限预览，其他类型按现有规则下载 |
| 学生 | 通知、个人资料、统计 | 分类和资料保留，2张统计图数值与表格一致 |
| 教师 | 班级列表和审批 | 多班级列表内部滚动，审批入口可用，名册和关联课程正确 |
| 教师 | 课程章节与视频统一编辑 | 原视频归属原章节，弹窗尺寸合适、内部滚动 |
| 教师 | 作业、附件测验、批改记录 | 附件试卷可读取、评分锁定与关闭提交规则一致 |
| 教师 | 教学统计 | 2张真实图表，长名称和6课程分页可查看 |
| 管理员 | 后台各管理区 | 用户、课程、班级、公告、分类和审计可读取 |
| 管理员 | 视频处理与图表 | FFmpeg可用；折叠图表展开后2张中性色图正常 |
| 所有角色 | 退出后重新登录 | 安全退出成功，重新登录后不立刻失效 |
| 390px / 桌面宽度 | 页面、表格、弹窗 | 不出现页面横向溢出，密集表格按提示内部横滑 |
| 长名称 / 多数据 / 空数据 | 卡片、列表、图表 | 全文入口可用，分页/内部滚动正常，空状态不造数据 |

转码闭环只用专门测试课程和小文件：上传 → 待处理/处理中 → 可播放 → 实际播放。观察 Celery 日志，确认不是只把数据库状态改为可播放。小文件验证成功并不代表任意超大文件都无需时间或磁盘空间。

断网补传测试：保持后端/Redis/Celery运行，在学生浏览器开发者工具中暂时离线，恢复网络后确认补传。不要关服务模拟浏览器断网；本地缓存按浏览器站点隔离，清站点数据会丢失尚未补传内容。

### 11.3 已有演示数据的脚本检查（可选）

需要旧演示数据标记、报告与初始测试账号仍符合脚本预期。只有你确实迁移了这套数据才运行：

```powershell
cd D:\BS_HFN\backend
..\.venv\Scripts\python.exe -X utf8 -m scripts.seed_demo --check
..\.venv\Scripts\python.exe -X utf8 -m scripts.verify_demo
```

第一条是演示基线检查，不新增演示数据；第二条会真实登录/退出账号，可能产生认证/审计写入，且某些测验查询会按现行业务惰性结算过期记录。它们不主动审批、交卷、重试或删除视频，不能宣传为“绝对零数据库写入”。

审批、删除或修改演示数据后，初始基线可能不再满足。脚本失败时先分辨“场景变化”还是“配置/文件损坏”，不要重新导入 SQL或运行 seed 来强行恢复已改变的业务状态。

浏览器演示检查还需要 Playwright Chromium：

```powershell
cd D:\BS_HFN\frontend
npx.cmd playwright install chromium
node scripts/verify-demo.mjs
```

脚本默认访问已运行的5173，当前核验13个页面和HLS实际播放，截图在 `tmp/demo`。依赖 `backend/demo-data-report.json`、已知初始演示账号与其密码；若已改密码，按脚本支持的私人 `DEFENSE_DEMO_PASSWORD` 环境配置处理，不在文档公开真实新密码。真实场景变动不等于界面一定有缺陷。

### 11.4 隔离自动化测试（可选，建议换机后执行）

后端：

```powershell
cd D:\BS_HFN\backend
$env:RUN_FFMPEG_TEST='1'
..\.venv\Scripts\python.exe -m pytest -q
```

前端：

```powershell
cd D:\BS_HFN\frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

当前前端测试使用独立 API5100、前端4173、测试SQLite和 `backend/.e2e-media`，不是开发 MySQL。不要并发执行多套端到端测试，避免共用端口和测试媒体目录。实际浏览器演示检查与隔离端到端测试不是同一种检查。

本手册编写时旧机器当前 Chromium 全量135/135、生产构建通过，实际开发/生产预览各13页面通过；旧后端85/85属于此前阶段记录。新电脑尚未执行这些测试，不能把旧结果直接写成新机验收通过，未来新增测试后数量也可能变化。

## 12. 常见故障与排查

### 12.1 最有效的排查顺序

先看哪个进程失败：MySQL → Redis → Python导入 → 数据库连接/版本 → Flask → Celery → Vite → 浏览器接口 → 媒体文件。保留第一处真实报错，不要一次改端口、密码、认证插件和依赖版本。

记录错误时只保留必要报错，遮盖密码、密钥、令牌和个人信息。不要把 `.env`、SQL全文或浏览器 Authorization 请求头发到公共渠道。

### 12.2 故障对照表

| 现象 | 常见原因 | 安全处理 |
| --- | --- | --- |
| `py` / `python` 找不到 | Python没安装、PATH没刷新或应用商店别名 | 重开终端，确认3.12实际路径，用完整路径建环境 |
| `No Python at ...` / Celery `Unable to create process` | 沿用旧 `.venv` | 保留旧环境改名，重新创建并安装依赖 |
| `ModuleNotFoundError: flask` 等 | pip安装到其他Python或安装失败 | 使用 `.venv\Scripts\python.exe -m pip`，不要仅用系统pip |
| `npm.ps1 cannot be loaded` | PowerShell执行策略 | 用 `npm.cmd` / `npx.cmd`，不要先放宽全局策略 |
| npm ci 报锁文件不一致 | package.json和锁文件没一起复制 | 从旧项目重新复制对应文件，不删除锁文件盲装 |
| `mysql` / `mysqldump` 找不到 | 客户端bin未入PATH | 添加实际bin，重开终端，或用完整路径 |
| MySQL连接10061 / refused | 服务未运行、端口不对 | 检查实际服务与3306连接，不盲目安装第二实例 |
| MySQL1045 Access denied | 新机DB密码、用户或host权限不符 | 用相同host/port mysql手工验证，核对.env，不改平台密码 |
| `cryptography` is required for caching_sha2_password | 缺RSA额外依赖 | 在项目环境装 `PyMySQL[rsa]>=1.1,<2`，保留安全认证 |
| MySQL1049 Unknown database | 未建库或DB_NAME不匹配 | 核对恢复目标名称；不能用空库假装已恢复 |
| 表不存在 / unknown column | SQL导入中断、版本旧、连错库 | 查看current/head、表数、原错误，不stamp伪装升级 |
| `Path doesn't exist: migrations` | 在根目录而非backend执行迁移 | cd backend再执行，不db init重建项目迁移 |
| 恢复报Table already exists等 | 混用完整导入和迁移、目标非空 | 停止，保留目标和报错，另建空目标；不强行清库 |
| SOURCE找不到文件 | 在PowerShell执行、路径错误或多套层目录 | 在mysql客户端用D:/短路径，核对文件存在 |
| 中文乱码或SQL编码错误 | 错用PowerShell重定向或原文件损坏 | 重导有效UTF8备份，用result-file，核对hash |
| 登录后马上401 / Token失效 | Redis不可用、密钥轮换、旧浏览器令牌 | 验证项目Redis PING，退出重登，不禁用认证校验 |
| 退出失败 | Redis无法写撤销记录 | 恢复Redis并再退出，不把它当成仅转码问题 |
| Celery不断重连Redis | REDIS_URL错误或Redis停了 | 先Redis真PING，再重启worker |
| 视频一直等待 | worker没ready、旧队列没搬或真实任务失败 | 查worker和管理员错误原因，确认原文件后按规则恢复 |
| 任务未注册 | 错worker入口或启动目录 | backend中用celery_worker.celery_app入口重启 |
| FFmpeg找不到 | 没带tools或.env仍是旧绝对路径 | 核对二进制与相对路径，不只安装ffmpeg npm包 |
| 封面/视频404 | 媒体漏复制、MEDIA_ROOT不对、关闭开发媒体路由 | 核对实际根目录、完整HLS目录、FLASK_ENV |
| m3u8能开但视频不能播 | 缺切片、路径不一致或媒体损坏 | 检查清单引用的切片和网络响应，不只复制m3u8 |
| 教学附件/media路径404 | 附件要求鉴权API | 从已登录的作业/测验入口预览，不绕过权限直接访问 |
| 所有/api请求404或代理失败 | 打开了错误端口、旧VITE地址、后端未启动 | 使用5173，核对Vite终端和后端5000 |
| 5173变5174 | 旧前端占端口 | 找到具体占用进程，关闭你确认的旧终端，避免重复双击 |
| 请求CORS报错 | 前端origin不在配置中 | 使用默认地址或精确添加对应origin并重启后端 |
| 头像/附件上传413 | 文件超过对应限制 | 检查大小与.env限制，不能只增加JSON限制 |
| 文件写入Permission denied | 项目只读、磁盘空间不足或安全软件拦截 | 放本地可写目录，检查权限和空间，不全局关闭防护 |
| 系统时间异常、JWT未生效/过期 | 新机时间或时区明显不准 | Windows校准时间，重新登录，勿调整业务截止日期掩盖 |
| 作业/测验显示截止 | 原截止日期已过去 | 日期属于业务数据不是迁移bug；演练专用任务调整需明确操作 |
| seed_demo检查失败 | 数据已操作过、报告缺失或素材缺失 | 区分基线变化和迁移损坏，不重复初始化重置业务 |
| 图表不出现 | 前端依赖没完整安装、零数据或折叠未展开 | npm ci后看浏览器错误；后台需展开，全零允许空状态 |
| Playwright浏览器不存在 | 只装npm没装Chromium | npx.cmd playwright install chromium；普通启动不要求此项 |
| 端到端测试端口占用 | 上一测试未结束或并发跑套件 | 确认自己的测试进程退出，再单套运行 |

### 12.3 如何识别端口占用，不盲目杀进程

```powershell
Get-NetTCPConnection -LocalPort 3306,6379,5000,5173 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

取得 PID 后再查询对应进程，例如将示例1234替换为真实PID：

```powershell
Get-Process -Id 1234 | Select-Object Id,ProcessName,Path
```

优先在对应自己的终端 Ctrl+C。不要执行“杀所有Python/Node/MySQL进程”，可能结束其他项目或破坏真实正在写入的任务。

### 12.4 浏览器侧检查

按F12，查看 Console 和 Network。关注第一个失败的API、500/401/403/404、媒体清单和切片，而不是仅看页面是否有空白。403常是权限不符，不代表数据库一定坏了；课堂附件直接访问拒绝可能是正常权限控制。

密钥轮换后旧token失效是预期现象，重新登录即可。清站点数据会同时清掉本地离线队列和未提交草稿，先处理需要保留内容，不把清缓存当通用首选修复。

## 13. 离线答辩、备份与回退

### 13.1 答辩现场不依赖互联网

提前在新电脑联网完成：基础软件安装、pip/npm依赖安装、Docker镜像拉取（若用）、Playwright浏览器下载（若验收）、完整恢复与计时彩排。然后断开外网测试一次，确认全部本地服务仍运行、实际视频和图表可用。

本地联网地址127.0.0.1不是互联网。不要因为“不联网”停止MySQL/Redis，也不要把浏览器开发者工具保持Offline后误认为整个应用坏了。

现场不要临时执行 npm ci、pip install、docker pull或重新导入SQL，避免下载失败、依赖改变和数据重置。

### 13.2 新电脑完全无法联网时

最好先在这台新电脑联网安装并验收，再带去现场。若只能离线安装，需要另外准备匹配Windows/Python/CPU的安装包、Python wheels、npm可用完整缓存以及所需Docker镜像/浏览器文件，**复制旧node_modules和.venv不等于可靠离线环境**。

Python可在匹配平台的联网Windows环境先下载当前requirements与RSA扩展的wheel包，离线用 `pip install --no-index --find-links=准备的wheel目录` 安装；npm离线安装要求缓存包含锁文件中每个依赖的完整tarball，`npm ci --offline` 缺任何包都会失败。不同平台的二进制包不能随意混用。

这是另一项需要实际验证的离线打包工作，本手册不声称目前项目已经有一键离线安装包或包含完整Docker/WSL/Python运行时。

### 13.3 保留迁移前与彩排后两份配套备份

迁移前备份是旧电脑冻结时的最新SQL和对应媒体；彩排后如果希望保留新操作，再按同样流程暂停写入、导出新SQL并复制对应媒体。文件使用不同名称/日期，不能覆盖唯一旧备份。

只备SQL不备媒体会丢视频/附件；只备媒体不备SQL会丢课程归属和成绩。后台视频替换/删除会清理关联学习记录，不要在主答辩数据里随意尝试。

### 13.4 安全回退

如果新机验收失败，旧机尚未修改就是最直接的回退来源。恢复到旧机演示不需要把失败新库覆盖回去。若要重新恢复到新机，另建空目标，使用确认成功的配套SQL/媒体，先不删除失败库和日志。

本手册不包含DROP DATABASE、TRUNCATE、FLUSHALL、删除数据卷或批量清目录命令。确实需要清理时另行确定精确目标和备份，不作为配置的常规步骤。

### 13.5 不是本手册范围的部署方式

当前后端和前端监听127.0.0.1，适合该电脑浏览器本地答辩，其他电脑和手机不能直接用它们自己的127.0.0.1访问这台机器。局域网演示需要另行修改监听、真实IP、CORS及防火墙并测试，不是“换电脑后直接输入旧链接”。

公网发布、HTTPS、生产WSGI服务、反向代理、独立媒体服务、权限隔离和长期备份是另一条工作线。不要把Vite dev/preview与Flask debug服务直接暴露到互联网，也不要为了现场展示打开数据库或Redis公网端口。

## 14. 最后的勾选清单

### 旧电脑准备

- [ ] 暂停业务写入，浏览器未补传内容已处理，真实转码已结束。
- [ ] 使用实际DB参数导出了新SQL，退出码0、非空，记录SHA256。
- [ ] 记录原库迁移版本、27表与关键表行数。
- [ ] 完整当前代码（包括未提交修改）、实际.env、完整媒体与FFmpeg已复制。
- [ ] 自定义项目外MEDIA_ROOT、演示报告和需要携带的可信Redis程序已另外核对。
- [ ] 没有删除旧机数据库或媒体，私人文件未公开。

### 新电脑配置

- [ ] Python3.12、Node22、MySQL8已安装，工具路径可用。
- [ ] 旧.venv未沿用，新.venv依赖和RSA扩展安装成功，pip check通过。
- [ ] npm ci和生产构建通过，锁文件未随意修改。
- [ ] FFmpeg与ffprobe可执行，新机磁盘可写且有足够空间。
- [ ] Redis只有一个明确实例，项目配置PING为True。
- [ ] .env不是.env.txt，DB密码/路径为新机，密钥私下配置。
- [ ] 使用流程A或B之一，没有混用恢复与初始化。
- [ ] 流程A在空目标导入，SHA256一致，版本/表数/行数核对正确。

### 运行验收

- [ ] MySQL、Redis先运行，再启动API、worker、前端。
- [ ] 三个终端没有启动失败，前端实际端口5173。
- [ ] 学生/教师/管理员原账号可登录并安全退出，数据保留。
- [ ] 真实视频、HLS切片、封面和教学附件可读取。
- [ ] 班级申请、作业/测验成绩与关闭提交/批改锁定正确。
- [ ] 学生/教师/管理员共6张图表按角色正常展示，数值可核对。
- [ ] 手机/桌面布局、弹窗内部滚动、长名称和多数据分页检查通过。
- [ ] 已在专门记录完成小视频转码闭环，不破坏主答辩记录。
- [ ] 已断开外网做一次彩排，未停止本地依赖服务。
- [ ] 已记录新机实际测试结果，不套用旧机结果。

## 15. 核对依据与官方参考

项目核对来源：`start-dev.bat`、`backend/app/config.py`、`backend/app/extensions.py`、`backend/app/services/token_service.py`、`backend/run.py`、`backend/celery_worker.py`、`backend/scripts/seed.py`、`seed_demo.py`、`upgrade_local.py`、`verify_demo.py`、`frontend/vite.config.js`、`frontend/playwright.config.js`、`frontend/scripts/verify-demo.mjs` 及当前迁移链。

补充阅读：

- [MySQL8 Windows安装](https://dev.mysql.com/doc/refman/8.0/en/windows-installation.html)
- [MySQL8 mysqldump备份](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)
- [MySQL8 SQL格式备份恢复](https://dev.mysql.com/doc/refman/8.0/en/reloading-sql-format-dumps.html)
- [Python3.12虚拟环境说明](https://docs.python.org/3.12/library/venv.html)
- [Node.js22官方下载](https://nodejs.org/en/download/archive/v22)
- [PyMySQL RSA认证依赖](https://pymysql.readthedocs.io/en/latest/user/installation.html)
- [Redis Docker运行](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/docker/)
- [Redis Windows/WSL安装](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/)
- [Docker Desktop Windows安装](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Vite预览代理默认值](https://vite.dev/config/preview-options.html#preview-proxy)

外部下载界面、版本及系统要求可能改变，以官方页面为准。本手册没有在另一台新电脑上代替你完成安装、恢复或新机验收；其中会写入文件/数据库的命令是供你明确选择对应流程后执行的步骤，本次编写文档没有导出或恢复真实数据库，也没有更改运行配置或账号。

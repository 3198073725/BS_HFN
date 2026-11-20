# 课程字幕与 AI 总结

> 2026-11-19 更新：现已改为按当前视频独立生成。以下“当前规则”优先于本文末尾保留的早期课程级设计记录。

## 当前规则：按视频独立生成

教师在课程详情中选中一个视频，在“视频笔记 / 我的提问 / AI 总结”标签栏打开 AI 总结。页面显示当前视频名称，“生成当前视频字幕及总结”只提交 video_id，处理这一个视频。切换视频会销毁旧面板并加载新视频记录，不会显示上一个视频的总结或继续轮询上一个视频。

流程：QUEUED → EXTRACTING（FFmpeg 提取当前视频音频）→ SUBTITLING（本地 Whisper 生成当前视频字幕）→ SUMMARIZING（DeepSeek 分段总结、合并当前视频结果）→ DRAFT（教师编辑审核）→ PUBLISHED。FAILED 可重试，CANCELLED 表示已取消。进度按阶段和识别到的时间点估算，不是准确剩余时间。处理单个视频仍需要识别完整视频；长视频和 CPU 模型依然可能耗时较久。

字幕存于 video_subtitle，视频总结存于 video_ai_summary，均以 video_id 唯一关联。已有且源文件指纹相同的字幕直接复用。删视频会级联删除字幕、总结。原 course_ai_summary 表保留历史内容和课程访问策略，不将整门课程的旧总结复制到各视频。旧课程生成接口返回 410，旧 Celery 消息只记录取消，不再识别整门课程。

默认学生加入课程并学完当前视频即可查看该视频已发布的总结，无须学完整门课或完成课程作业测验。“C语言学习”（课程 ID 4）的 open_to_students 已设置为 true，其所有视频发布后的总结向所有正常登录学生开放，无需选课或完成视频。未审核草稿、失效内容、下线课程和不可播放的视频不会向学生开放。

教师或管理员可以点击“取消当前任务”。取消状态写入数据库；提取音频期间定期检查，Whisper 在字幕段返回时检查，DeepSeek 在请求前后检查，耗时推理或网络请求需等下一检查点。旧任务不能覆盖已取消或新任务的结果，取消后允许重试。页面离开不自动取消已提交任务。

当前接口：

- GET /api/videos/{video_id}/ai-summary：读取当前视频状态、进度、解锁情况、总结。
- POST /api/videos/{video_id}/ai-summary/generate：只提交当前视频任务。
- POST /api/videos/{video_id}/ai-summary/cancel：取消当前视频任务。
- PUT /api/videos/{video_id}/ai-summary：提交 content 和 publish 布尔值。
- GET /api/videos/{video_id}/subtitle：读取当前视频 WebVTT。

字幕完成后面板会通知播放器重新获取字幕，无需重开视频。数据库升级仍使用 `flask --app run:app db upgrade`。更新后须重启 Flask、Celery 并刷新浏览器；无需重新下载模型，DeepSeek 和 Whisper 的 .env 配置沿用下文。

## 早期设计记录（课程级生成已停用）

教师在课程详情页“视频笔记 / 我的提问 / AI 总结”这一行打开“AI 总结”，点击“生成字幕及总结”。系统通过 Celery 串行处理课程中已就绪的视频：FFmpeg 提取单声道 16kHz WAV，faster-whisper 识别带时间轴的文本，调用 DeepSeek 分段总结后合并。字幕保存在 video_subtitle，教师审核的课程总结保存在 course_ai_summary。删除视频、课程时由外键和 ORM 级联删除相应数据。音频中间文件使用临时目录，结束时自动清理。

FFmpeg 本身不能识别语音。这里由它提取音频，再由本地 Whisper 模型完成识别；不是把视频上传到 DeepSeek。发送到 DeepSeek 的是字幕文本、课程名称、介绍、章节及非草稿任务的要求，不发送学生姓名、成绩、个人笔记或测验答案。

## 安装和配置

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ai.txt
cd backend
..\.venv\Scripts\python.exe -m flask --app run:app db upgrade
```

在 backend/.env 添加以下配置。不要提交真实密钥到 Git：

```dotenv
DEEPSEEK_API_KEY=在此填写自己的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

首次使用 small 会下载模型，需要网络。离线演示时事先准备 CTranslate2 格式的 faster-whisper 模型，将 WHISPER_MODEL 设置为模型的绝对目录。CPU 识别长视频可能耗时较久，任务页面会显示“正在生成字幕”。Redis、Celery 和 Flask 都应启动；修改 .env 后重启 Flask 和 Celery。字幕识别依赖可选安装，不影响其余课程和转码功能。

当前开发电脑已下载到 tools/whisper-small，实际 .env 已使用 WHISPER_MODEL=../tools/whisper-small（相对于 backend 解析）。迁移电脑时一起复制 tools/whisper-small，不必重新下载。也可运行 `.venv\Scripts\python.exe backend\scripts\prepare_subtitle_model.py` 提前准备模型。

## 审核和解锁规则

任务状态：QUEUED → SUBTITLING → SUMMARIZING → DRAFT → PUBLISHED；失败为 FAILED，可重新生成。生成字幕按视频源文件指纹复用，不会重复识别没有变化的视频。长字幕每段最多 12000 字，分层合并。重复点击生成会被拒绝，以免重复计费。教师可编辑、保存草稿、审核发布；保存草稿会撤回已发布内容。

学生需加入已发布课程、完成所有就绪视频。学生有班级任务访问权限时，还需提交本课程全部已发布/关闭的作业和测验（无须等待教师评分）。没有班级任务权限的学生不会因不可访问的班级任务而永久卡住。学生只能看到已发布且资料指纹未过期的总结。修改课程名称、介绍、视频或任务要求后，旧总结不能重新发布，需重新生成。进入 AI 总结标签或点击刷新时重新校验解锁条件。

字幕生成后重新打开视频，播放器原生字幕轨道可显示或关闭字幕。字幕通过鉴权接口获取，以 Blob URL 加载，不暴露 API Key。语音识别可能有误，尤其是术语、噪声或缺失音轨；教师应校验总结。

## 接口

### 按课程开放给所有学生

course_ai_summary.open_to_students 默认 false，保持原有完成度解锁规则。设置为 true 时，所有正常登录的学生（含未选课、未完成视频的学生）均可查看该已发布课程的已发布总结；待审核草稿和过期总结仍不展示，课程下线后不可访问。该设置不会更改学生学习进度、选课或班级数据，重新生成总结时会保留。当前“C语言学习”（课程 ID 4）启用此设置；其余课程不变。

- GET /api/courses/{id}/ai-summary：教师读取草稿和任务状态，学生读取解锁状态和已发布内容。
- POST /api/courses/{id}/ai-summary/generate：授课教师或管理员发起生成。
- PUT /api/courses/{id}/ai-summary：提交 content 和 publish 布尔值，保存草稿或审核发布。
- GET /api/videos/{id}/subtitle：鉴权后读取 WebVTT 字幕。

DeepSeek 接口依据官方 Chat Completions 协议：https://api-docs.deepseek.com/api/create-chat-completion/ 。语音识别使用 https://github.com/SYSTRAN/faster-whisper 。DEEPSEEK_MODEL 可按账号实际可用模型调整。

## 验收

先选一门仅有短视频的测试课程生成总结；检查字幕时间轴、关闭字幕、教师修改并发布。未完成学习的学生应看到解锁条件，完成视频及可访问任务后可查看正文。修改课程介绍后旧总结不再对学生展示。删除源文件时生成应失败并给出提示，不影响视频转码状态。没有 API Key 或 Redis 时应明确报错，不能假装生成成功。

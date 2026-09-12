# Flask后端技术方案修订

## 1. 后端技术栈最终确定

本项目后端确定采用：

```text
Python
Flask
Flask-SQLAlchemy
Flask-Migrate
Flask-JWT-Extended
Flask-CORS
MySQL
Redis
Celery
FFmpeg
ffprobe
```

各技术职责如下：

| 技术 | 主要作用 |
|---|---|
| Flask | Web后端核心框架 |
| Flask-SQLAlchemy | 数据库ORM操作 |
| Flask-Migrate | 数据库表结构迁移 |
| Flask-JWT-Extended | JWT登录认证 |
| Flask-CORS | 解决Vue与Flask跨域请求 |
| MySQL | 保存系统业务数据 |
| Redis | Celery消息队列 |
| Celery | 执行FFmpeg异步视频任务 |
| FFmpeg | 视频转码、切片、截图、压缩 |
| ffprobe | 获取视频时长、编码、分辨率等信息 |

前端保持：

```text
Vue 3
Vite
Vue Router
Pinia
Axios
Element Plus
ECharts
hls.js
```

因此完整技术架构变为：

```text
Vue 3
   ↓
Axios
   ↓
REST API
   ↓
Flask
   ↓
业务模块
   ├─ 用户
   ├─ 课程
   ├─ 视频
   ├─ 学习
   ├─ 答疑
   ├─ 作业
   └─ 测验
   ↓
Flask-SQLAlchemy
   ↓
MySQL
```

视频处理部分：

```text
Flask
   ↓
Celery
   ↓
Redis
   ↓
FFmpeg / ffprobe
   ↓
视频文件
```

---

# 2. 为什么仍然需要Celery

教师上传一个视频后，FFmpeg转码可能需要几十秒甚至几分钟。

因此不能采用：

```text
Vue上传视频
    ↓
Flask接口
    ↓
FFmpeg开始处理
    ↓
一直等待
    ↓
处理完成后返回
```

这样容易导致：

- HTTP请求超时；
- 用户一直停留在上传页面；
- 多个视频同时上传时阻塞服务器；
- Flask进程被长时间占用。

正确方式：

```text
Vue上传视频
    ↓
Flask保存原文件
    ↓
创建Video数据库记录
    ↓
向Celery提交任务
    ↓
Flask立即返回
    ↓
Celery后台调用FFmpeg
    ↓
处理完成
    ↓
更新Video状态
```

Celery目前官方稳定版仍然可以直接与Flask类Web应用结合使用，并不需要专门的Flask集成包。citeturn985694search0turn985694search3

---

# 3. Flask项目不要写成单文件

虽然Flask可以这样启动：

```text
app.py
```

但本项目后期会包含十几个业务模块，所以绝对不建议把：

```text
登录
课程
视频
作业
FFmpeg
数据库
```

全部写在一个文件里面。

推荐采用：

**Application Factory + Blueprint**

方式组织项目。

Flask官方文档也将Blueprint作为大型应用模块化的重要机制。citeturn985694search1

---

# 4. 推荐后端项目目录

建议最终建立：

```text
backend/
│
├── app/
│   │
│   ├── __init__.py
│   │
│   ├── extensions.py
│   │
│   ├── config.py
│   │
│   ├── constants.py
│   │
│   ├── utils/
│   │
│   ├── models/
│   │
│   ├── services/
│   │
│   ├── tasks/
│   │
│   └── blueprints/
│   │
│   ├── auth/
│   ├── users/
│   ├── courses/
│   ├── videos/
│   ├── learning/
│   ├── questions/
│   ├── homework/
│   ├── exams/
│   ├── statistics/
│   └── admin/
│
├── migrations/
│
├── media/
│
│   ├── avatars/
│   ├── course_covers/
│   ├── videos/
│   │   ├── original/
│   │   ├── processed/
│   │   ├── hls/
│   │   └── covers/
│   │
│   └── homework/
│
├── logs/
│
├── tests/
│
├── run.py
├── celery_worker.py
├── requirements.txt
└── .env
```

这是后面整个项目的基础结构。

---

# 5. app/__init__.py职责

该文件主要负责创建Flask应用。

核心思想：

```text
create_app()
```

在里面完成：

```text
创建Flask对象
↓
读取配置
↓
初始化数据库
↓
初始化JWT
↓
初始化CORS
↓
注册Blueprint
↓
注册异常处理
↓
返回app
```

以后启动项目：

```text
run.py
```

只负责启动应用。

这样能够避免项目越来越大以后代码混乱。

---

# 6. extensions.py

专门管理Flask扩展。

建议统一放：

```text
db

migrate

jwt

cors
```

逻辑结构：

```text
Flask
│
├─ db
├─ migrate
├─ jwt
└─ cors
```

这样其他模块只需要引用：

```text
db
```

而不是在不同地方重复初始化数据库。

---

# 7. Blueprints模块设计

Flask中的Blueprint可以理解为：

**业务模块。**

系统建议建立以下Blueprint。

```text
auth_bp

user_bp

course_bp

video_bp

learning_bp

question_bp

homework_bp

exam_bp

statistics_bp

admin_bp
```

URL规划：

```text
/api/auth

/api/users

/api/courses

/api/videos

/api/learning

/api/questions

/api/homeworks

/api/exams

/api/statistics

/api/admin
```

---

# 8. auth模块

目录：

```text
blueprints/
└── auth/
    ├── __init__.py
    ├── routes.py
    ├── schemas.py
    └── services.py
```

负责：

```text
登录
学生注册
刷新Token
退出
```

例如：

```text
POST /api/auth/login

POST /api/auth/register

POST /api/auth/refresh
```

---

# 9. JWT认证

采用：

```text
Flask-JWT-Extended
```

登录成功后返回：

```json
{
    "code": 200,
    "message": "登录成功",
    "data": {
        "access_token": "xxxxx",
        "refresh_token": "xxxxx",
        "user": {
            "id": 1,
            "username": "zhangsan",
            "role": "STUDENT"
        }
    }
}
```

前端以后访问：

```text
/api/courses
/api/learning/progress
```

统一携带：

```text
Authorization: Bearer TOKEN
```

Flask-JWT-Extended目前仍提供访问Token、Refresh Token及JWT保护接口等机制，非常适合本项目。citeturn985694search22

---

# 10. 权限控制

需要设计两个层级。

第一层：

```text
是否登录
```

第二层：

```text
角色是否允许访问
```

例如：

```text
@student_required

@teacher_required

@admin_required
```

实际效果：

学生请求：

```text
POST /api/teacher/courses
```

直接返回：

```text
403
```

教师不能操作其他教师的课程。

因此还需要进行：

```text
资源所有权校验
```

例如：

```text
当前教师ID == course.teacher_id
```

才能编辑课程。

---

# 11. 数据库ORM

以前文档中的Django Model全部修改成：

```text
Flask-SQLAlchemy Model
```

但数据库设计本身基本不用变。

例如：

```text
User
Course
Chapter
Video
LearningRecord
Question
Answer
Homework
Exam
```

这些表仍然保留。

关系仍然是：

```text
Teacher
   ↓ 1:N

Course
   ↓ 1:N

Chapter
   ↓ 1:N

Video
```

Flask框架改变：

**不会导致数据库业务设计改变。**

---

# 12. 数据库迁移

使用：

```text
Flask-Migrate
```

以后数据库修改通过：

```text
migration
```

维护。

不要在开发过程中每次改字段都：

```text
DROP TABLE
```

重建数据库。

项目发展到中后期以后，这样非常容易丢数据。

---

# 13. Service层

这个项目建议增加：

```text
services/
```

这是非常重要的一层。

不要在：

```text
routes.py
```

里面写几十行甚至几百行业务代码。

正确结构：

```text
Route
   ↓
Service
   ↓
Model
```

例如：

```text
POST /api/courses
```

Route：

```text
读取参数
验证权限
调用CourseService
返回结果
```

CourseService：

```text
创建课程
保存数据库
```

---

# 14. FFmpeg Service

建议：

```text
services/
├── ffmpeg_service.py
├── ffprobe_service.py
└── file_service.py
```

其中：

## ffprobe_service.py

负责：

```text
读取视频时长
读取分辨率
读取编码
读取码率
读取帧率
```

例如逻辑函数：

```text
probe_video()
```

---

## ffmpeg_service.py

负责：

```text
视频转码
HLS切片
生成封面
```

建议对应：

```text
transcode_video()

generate_hls()

generate_cover()
```

这样以后Celery只需要调用这些Service。

---

# 15. Celery任务

建议：

```text
tasks/
└── video_tasks.py
```

主要任务：

```text
process_video(video_id)
```

执行逻辑：

```text
读取Video

↓

更新：
PROCESSING

↓

ffprobe

↓

保存视频信息

↓

FFmpeg转码

↓

生成HLS

↓

生成封面

↓

READY
```

异常：

```text
except Exception
```

更新：

```text
FAILED
```

保存：

```text
error_message
```

---

# 16. Flask和Celery的数据关系

这里是后期非常容易出问题的地方。

Celery任务不能依赖浏览器的：

```text
request
```

上下文。

应该：

```text
Celery收到video_id
↓
进入Flask应用上下文
↓
查询数据库
↓
执行FFmpeg
↓
提交数据库
```

不要把：

```text
request对象
文件对象
SQLAlchemy Model对象
```

直接传给Celery。

只传：

```text
video_id
```

这会稳定很多。

---

# 17. Video上传API

设计：

```text
POST /api/teacher/videos/upload
```

请求：

```text
multipart/form-data
```

包含：

```text
chapter_id
title
description
video_file
```

Flask执行：

```text
验证教师
↓
验证章节
↓
验证视频后缀
↓
验证文件大小
↓
UUID重命名
↓
保存original
↓
创建Video
↓
status=PENDING
↓
提交Celery
↓
返回Video
```

---

# 18. 视频处理状态接口

Vue需要定时查询：

```text
GET /api/videos/{video_id}/status
```

返回：

```json
{
    "code": 200,
    "data": {
        "id": 35,
        "status": "PROCESSING",
        "process_step": "HLS"
    }
}
```

前端显示：

```text
正在生成在线播放资源……
```

最终：

```json
{
    "status": "READY"
}
```

页面显示：

```text
处理完成
```

---

# 19. Flask不要负责直接传输所有视频数据

学生播放HLS时：

不建议：

```text
Vue
↓
Flask
↓
Flask读取TS
↓
返回浏览器
```

开发初期可以这样测试。

最终建议：

```text
Vue
↓
Nginx
↓
media/videos/hls
```

即：

```text
Flask负责业务API

Nginx负责视频静态文件
```

这是比较合理的职责划分。

---

# 20. 开发环境可以简单化

第一阶段暂时不用Nginx。

可以：

```text
Flask直接暴露media
```

用于测试。

等核心系统完成以后再增加：

```text
Nginx
```

不要一开始把时间浪费在正式部署环境。

---

# 21. 后端模块最终划分

因此项目最终后端可以归纳为：

```text
Flask Backend

├── Authentication
│
├── User
│
├── Course
│
├── Chapter
│
├── Video
│
├── FFmpeg
│
├── Learning
│
├── Question
│
├── Homework
│
├── Exam
│
├── Statistics
│
└── Admin
```

---

# 22. 推荐requirements

开发过程中主要依赖控制在：

```text
Flask

Flask-SQLAlchemy

Flask-Migrate

Flask-JWT-Extended

Flask-CORS

PyMySQL

celery

redis

python-dotenv
```

FFmpeg：

**不通过pip安装。**

FFmpeg属于：

```text
系统程序
```

需要单独安装。

Flask通过：

```text
subprocess
```

调用：

```text
ffmpeg.exe
ffprobe.exe
```

Windows开发时尤其要注意FFmpeg路径配置。

---

# 23. Windows开发建议

如果你的主要开发电脑是Windows：

建议：

```text
项目代码
    ↓
Flask

数据库
    ↓
MySQL

FFmpeg
    ↓
Windows FFmpeg

Redis
    ↓
推荐Docker / WSL / 可用Redis环境
```

如果不方便运行Redis：

项目最初阶段可以先：

```text
同步调用FFmpeg
```

把视频处理逻辑跑通。

正确开发顺序：

```text
先跑通FFmpeg
↓
再接Celery
↓
再接Redis
```

不要一开始同时调试：

```text
Flask + Celery + Redis + FFmpeg
```

否则出错以后很难判断是哪一层的问题。

---

# 24. Flask版核心开发顺序

以后严格按照：

```text
① Flask项目初始化

↓

② Flask-SQLAlchemy连接MySQL

↓

③ 用户Model

↓

④ JWT登录

↓

⑤ Blueprint模块

↓

⑥ 权限系统

↓

⑦ Course

↓

⑧ Chapter

↓

⑨ Video上传

↓

⑩ ffprobe

↓

⑪ FFmpeg转码

↓

⑫ HLS

↓

⑬ Vue视频在线播放

↓

⑭ Celery异步化

↓

⑮ 学习记录

↓

⑯ 视频笔记

↓

⑰ 视频时间点提问

↓

⑱ 教师答疑

↓

⑲ 作业

↓

⑳ 测验

↓

统计与后台
```

---

# 25. 第一阶段不要马上使用Celery

非常建议把开发再细分一下。

### 第一步

先在命令行确认：

```text
input.mp4
↓
FFmpeg
↓
index.m3u8
```

能够成功。

### 第二步

写Python：

```text
Python
↓
subprocess
↓
FFmpeg
```

成功。

### 第三步

写Flask接口：

```text
上传MP4
↓
Flask
↓
FFmpeg
↓
生成HLS
```

成功。

### 第四步

Vue：

```text
hls.js
↓
播放m3u8
```

成功。

### 第五步

最后再变成：

```text
Flask
↓
Celery
↓
Redis
↓
FFmpeg
```

这样难度会明显降低。

---

# 26. Flask版最终技术架构

最终建议确定为：

```text
                 Browser
                    │
                  Vue 3
                    │
                  Axios
                    │
                REST API
                    │
                  Flask
           ┌────────┼─────────┐
           │        │         │
          JWT    SQLAlchemy   Celery
                    │         │
                  MySQL      Redis
                              │
                            Worker
                              │
                       FFmpeg / ffprobe
                              │
                         Video Files
                              │
                            Nginx
                              │
                           hls.js
```

这就是后续整个毕业设计统一采用的技术架构。
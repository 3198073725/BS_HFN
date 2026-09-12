# 基于Web技术与FFmpeg的学生课后辅导系统
## 数据库详细设计文档 V1.0

---

# 1. 数据库基本方案

数据库采用：

```text
MySQL 8.x
```

数据库名称建议：

```text
student_tutoring
```

字符集：

```text
utf8mb4
```

排序规则：

```text
utf8mb4_unicode_ci
```

存储引擎：

```text
InnoDB
```

统一配置：

```sql
CREATE DATABASE student_tutoring
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

---

# 2. 数据库设计原则

整个数据库遵循以下原则。

## 2.1 主键统一

所有业务表统一使用：

```text
BIGINT UNSIGNED
```

自增主键。

例如：

```sql
id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT
```

这样后期数据量增加时不容易出现ID不足。

---

# 2.2 时间字段统一

一般业务表统一包含：

```text
created_at
updated_at
```

类型：

```text
DATETIME
```

创建时间：

```sql
DEFAULT CURRENT_TIMESTAMP
```

更新时间：

```sql
DEFAULT CURRENT_TIMESTAMP
ON UPDATE CURRENT_TIMESTAMP
```

---

# 2.3 不使用MySQL ENUM

角色、状态等字段统一使用：

```text
VARCHAR
```

例如：

```text
role = STUDENT
status = READY
```

而不使用：

```sql
ENUM(...)
```

原因是后期扩展状态时更加方便。

状态合法性由Flask业务层控制。

---

# 2.4 文件不保存到数据库

视频、图片、附件不以二进制形式写入MySQL。

数据库只保存：

```text
文件相对路径
```

例如：

```text
/videos/hls/35/index.m3u8
```

实际文件保存在：

```text
media/
```

目录。

---

# 2.5 尽量避免冗余

例如：

学生某门课程的学习进度，不单独在：

```text
course_student
```

保存。

可以通过：

```text
learning_record
```

统计得到。

避免多个位置同时维护学习进度。

---

# 3. 数据表总览

第一版数据库设计18张业务表。

| 编号 | 数据表 | 功能 |
|---:|---|---|
| 1 | sys_user | 用户 |
| 2 | course_category | 课程分类 |
| 3 | course | 课程 |
| 4 | course_student | 学生加入课程 |
| 5 | chapter | 课程章节 |
| 6 | video | 教学视频 |
| 7 | learning_record | 视频学习记录 |
| 8 | video_note | 视频笔记 |
| 9 | question | 学生问题 |
| 10 | answer | 教师回答 |
| 11 | homework | 课后作业 |
| 12 | homework_submission | 作业提交 |
| 13 | exam | 在线测验 |
| 14 | exam_question | 测验题目 |
| 15 | exam_record | 学生测验记录 |
| 16 | exam_answer | 学生答题详情 |
| 17 | notice | 系统公告 |
| 18 | favorite | 课程收藏 |

---

# 4. 数据库核心关系

整体关系如下：

```text
                        sys_user
                     ┌──────┴──────┐
                  Teacher        Student
                     │               │
                     │               │
                     ▼               ▼
                  course ◄──── course_student
                     │
                     │ 1:N
                     ▼
                  chapter
                     │
                     │ 1:N
                     ▼
                   video
             ┌───────┼────────┐
             │       │        │
             ▼       ▼        ▼
        learning   note    question
        record                │
                              ▼
                            answer


course
  │
  ├──── homework
  │         │
  │         ▼
  │   homework_submission
  │
  └──── exam
            │
            ├──── exam_question
            │
            └──── exam_record
                      │
                      ▼
                  exam_answer
```

---

# 5. 用户表 sys_user

## 5.1 功能

保存：

- 管理员；
- 教师；
- 学生。

三种角色统一使用一张用户表。

不建议建立：

```text
student
teacher
admin
```

三个独立账号表。

---

## 5.2 字段设计

| 字段 | 类型 | 空 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | 否 | 主键 |
| username | VARCHAR(50) | 否 | 登录用户名 |
| password_hash | VARCHAR(255) | 否 | 密码Hash |
| real_name | VARCHAR(50) | 否 | 姓名 |
| student_no | VARCHAR(50) | 是 | 学号 |
| teacher_no | VARCHAR(50) | 是 | 教师编号 |
| email | VARCHAR(100) | 是 | 邮箱 |
| phone | VARCHAR(20) | 是 | 手机 |
| avatar | VARCHAR(255) | 是 | 头像 |
| role | VARCHAR(20) | 否 | 用户角色 |
| status | TINYINT | 否 | 用户状态 |
| last_login_at | DATETIME | 是 | 最后登录 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

---

## 5.3 role值

```text
ADMIN
TEACHER
STUDENT
```

---

## 5.4 status

```text
1 = 正常
0 = 禁用
```

用户原则上不进行物理删除。

管理员如果不允许某个账号继续使用：

```text
status = 0
```

即可。

---

# 6. 课程分类表 course_category

用于保存：

```text
计算机
数学
英语
物理
其他
```

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| name | VARCHAR(50) | 分类名称 |
| description | VARCHAR(255) | 分类描述 |
| sort_order | INT | 排序 |
| status | TINYINT | 是否启用 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

分类名称设置唯一。

---

# 7. 课程表 course

## 7.1 功能

保存教师建立的课程。

例如：

```text
Java程序设计
数据库原理
Python程序设计
```

---

## 7.2 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| teacher_id | BIGINT | 任课教师 |
| category_id | BIGINT | 课程分类 |
| name | VARCHAR(100) | 课程名称 |
| cover | VARCHAR(255) | 封面 |
| description | VARCHAR(500) | 简介 |
| detail | TEXT | 详细介绍 |
| status | VARCHAR(20) | 状态 |
| published_at | DATETIME | 发布时间 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

## 7.3 status

```text
DRAFT
PUBLISHED
OFFLINE
```

含义：

```text
DRAFT
草稿

PUBLISHED
正常发布

OFFLINE
下架
```

只有：

```text
PUBLISHED
```

课程允许普通学生查看和加入。

---

# 8. 学生课程关系表 course_student

解决：

```text
一个学生可以加入多门课程
一个课程可以拥有多个学生
```

因此：

```text
Student
N:M
Course
```

需要中间表。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| course_id | BIGINT | 课程 |
| student_id | BIGINT | 学生 |
| join_time | DATETIME | 加入时间 |
| status | TINYINT | 状态 |

必须建立唯一约束：

```text
course_id + student_id
```

避免：

张三重复加入同一门课程。

---

# 9. 章节表 chapter

课程下面建立章节。

例如：

```text
Java程序设计

第一章 Java基础
第二章 面向对象
第三章 集合
```

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| course_id | BIGINT | 所属课程 |
| title | VARCHAR(150) | 章节名称 |
| description | VARCHAR(500) | 描述 |
| sort_order | INT | 排序 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

课程结构固定：

```text
Course
 ↓
Chapter
 ↓
Video
```

第一版不继续增加：

```text
Chapter
 ↓
Section
 ↓
Lesson
```

避免结构过度复杂。

---

# 10. 视频表 video

这是整个项目最重要的数据表之一。

---

## 10.1 基础信息

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 视频ID |
| chapter_id | BIGINT | 所属章节 |
| title | VARCHAR(150) | 标题 |
| description | VARCHAR(500) | 简介 |
| original_name | VARCHAR(255) | 原始文件名 |

---

## 10.2 文件信息

| 字段 | 类型 | 说明 |
|---|---|---|
| original_file | VARCHAR(500) | 原始文件 |
| processed_file | VARCHAR(500) | 标准MP4 |
| hls_path | VARCHAR(500) | m3u8 |
| cover | VARCHAR(500) | 封面 |

例如：

```text
original_file

/videos/original/abc123.mp4
```

```text
processed_file

/videos/processed/35/video.mp4
```

```text
hls_path

/videos/hls/35/index.m3u8
```

```text
cover

/videos/covers/35.jpg
```

---

# 11. 视频元信息

ffprobe读取以下内容。

| 字段 | 类型 | 单位 |
|---|---|---|
| duration | DECIMAL(10,3) | 秒 |
| width | INT | px |
| height | INT | px |
| video_codec | VARCHAR(50) | - |
| audio_codec | VARCHAR(50) | - |
| bitrate | BIGINT | bit/s |
| frame_rate | DECIMAL(8,3) | fps |
| file_size | BIGINT | bytes |

例如：

```text
duration = 1256.335
width = 1920
height = 1080
video_codec = h264
audio_codec = aac
bitrate = 4589612
frame_rate = 30
file_size = 536870912
```

---

# 12. 视频处理字段

| 字段 | 类型 | 说明 |
|---|---|---|
| status | VARCHAR(20) | 视频状态 |
| process_step | VARCHAR(30) | 当前处理步骤 |
| error_message | TEXT | 错误信息 |
| sort_order | INT | 章节内排序 |

status：

```text
UPLOADING
PENDING
PROCESSING
READY
FAILED
```

process_step：

```text
PROBING
TRANSCODING
HLS
COVER
FINISHED
```

---

# 13. 视频状态示例

教师上传后：

```text
status = PENDING
```

Celery开始：

```text
status = PROCESSING
process_step = PROBING
```

ffprobe完成：

```text
process_step = TRANSCODING
```

转码完成：

```text
process_step = HLS
```

生成HLS后：

```text
process_step = COVER
```

全部完成：

```text
status = READY
process_step = FINISHED
```

失败：

```text
status = FAILED
error_message = "FFmpeg exited with code 1..."
```

---

# 14. 学习记录表 learning_record

用于记录：

```text
哪个学生
观看哪个视频
看到什么位置
学了多久
完成多少
```

---

## 14.1 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| student_id | BIGINT | 学生 |
| video_id | BIGINT | 视频 |
| current_time | DECIMAL(10,3) | 当前播放位置 |
| watch_duration | INT UNSIGNED | 实际累计播放秒数 |
| progress | DECIMAL(5,2) | 进度百分比 |
| status | VARCHAR(20) | 状态 |
| last_watch_time | DATETIME | 最近学习 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

---

## 14.2 唯一约束

```text
student_id + video_id
```

一个学生观看一个视频只有：

```text
一条LearningRecord
```

不断更新。

不能每播放20秒插入一条新记录。

---

# 15. 学习状态

```text
NOT_STARTED
LEARNING
COMPLETED
```

当：

```text
progress >= 90
```

设置：

```text
COMPLETED
```

---

# 16. 视频笔记表 video_note

学生可以在视频某个具体位置记录笔记。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| student_id | BIGINT | 学生 |
| video_id | BIGINT | 视频 |
| video_time | DECIMAL(10,3) | 视频秒数 |
| content | TEXT | 笔记 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

例如：

```text
video_time = 755

content =
这里需要重点掌握事务隔离级别
```

前端显示：

```text
12:35
```

---

# 17. 问题表 question

学生针对视频进行提问。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| student_id | BIGINT | 提问学生 |
| video_id | BIGINT | 视频 |
| video_time | DECIMAL(10,3) | 提问位置 |
| title | VARCHAR(200) | 标题 |
| content | TEXT | 问题内容 |
| status | VARCHAR(20) | 状态 |
| created_at | DATETIME | 时间 |
| updated_at | DATETIME | 修改 |

状态：

```text
WAITING
ANSWERED
CLOSED
```

---

# 18. 回答表 answer

教师回答学生的问题。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| question_id | BIGINT | 问题 |
| teacher_id | BIGINT | 教师 |
| content | TEXT | 回答 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

第一版：

```text
一个Question对应一个正式Answer
```

因此：

```text
question_id
```

建立唯一索引。

如果以后想发展成论坛式回复：

再取消这个唯一约束。

现在不要增加复杂度。

---

# 19. 作业表 homework

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| course_id | BIGINT | 所属课程 |
| teacher_id | BIGINT | 发布教师 |
| title | VARCHAR(200) | 标题 |
| description | TEXT | 作业要求 |
| attachment | VARCHAR(500) | 附件 |
| deadline | DATETIME | 截止时间 |
| total_score | DECIMAL(5,2) | 满分 |
| status | VARCHAR(20) | 状态 |
| published_at | DATETIME | 发布时间 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

状态：

```text
DRAFT
PUBLISHED
CLOSED
```

---

# 20. 作业提交表 homework_submission

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| homework_id | BIGINT | 作业 |
| student_id | BIGINT | 学生 |
| content | LONGTEXT | 文字答案 |
| attachment | VARCHAR(500) | 学生附件 |
| status | VARCHAR(20) | 状态 |
| score | DECIMAL(5,2) | 成绩 |
| teacher_comment | TEXT | 教师评语 |
| submit_time | DATETIME | 提交时间 |
| graded_time | DATETIME | 批改时间 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

唯一：

```text
homework_id + student_id
```

即第一版一个学生针对一个作业：

```text
只保留一次最终提交
```

学生再次提交：

更新原记录。

---

# 21. 作业提交状态

```text
NOT_SUBMITTED
SUBMITTED
GRADED
```

实际上：

没有记录即可代表未提交。

因此数据库记录通常只存在：

```text
SUBMITTED
GRADED
```

前端的：

```text
NOT_SUBMITTED
```

可通过是否存在记录判断。

---

# 22. 测验表 exam

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| course_id | BIGINT | 课程 |
| teacher_id | BIGINT | 教师 |
| title | VARCHAR(200) | 名称 |
| description | TEXT | 说明 |
| total_score | DECIMAL(6,2) | 总分 |
| status | VARCHAR(20) | 状态 |
| start_time | DATETIME | 开始 |
| end_time | DATETIME | 结束 |
| time_limit_minutes | INT | 限时 |
| published_at | DATETIME | 发布时间 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

status：

```text
DRAFT
PUBLISHED
CLOSED
```

---

# 23. 试题表 exam_question

第一版支持：

```text
单选题
判断题
```

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| exam_id | BIGINT | 测验 |
| question_type | VARCHAR(20) | 类型 |
| content | TEXT | 题目 |
| option_a | VARCHAR(500) | A |
| option_b | VARCHAR(500) | B |
| option_c | VARCHAR(500) | C |
| option_d | VARCHAR(500) | D |
| correct_answer | VARCHAR(20) | 正确答案 |
| score | DECIMAL(5,2) | 分值 |
| sort_order | INT | 排序 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

类型：

```text
SINGLE
TRUE_FALSE
```

---

# 24. 单选题答案

例如：

```text
correct_answer = A
```

判断题：

```text
correct_answer = TRUE
```

或者：

```text
FALSE
```

统一由业务层判断。

---

# 25. 测验记录 exam_record

记录一次完整测验。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| exam_id | BIGINT | 测验 |
| student_id | BIGINT | 学生 |
| score | DECIMAL(6,2) | 总成绩 |
| correct_count | INT | 正确数量 |
| wrong_count | INT | 错误数量 |
| status | VARCHAR(20) | 状态 |
| started_at | DATETIME | 开始时间 |
| submit_time | DATETIME | 提交时间 |
| duration_seconds | INT | 实际用时 |
| created_at | DATETIME | 创建 |

第一版规定：

```text
一个学生每个测验只能正式提交一次
```

因此唯一：

```text
exam_id + student_id
```

---

# 26. ExamRecord状态

```text
DOING
SUBMITTED
```

学生点击：

开始考试

创建：

```text
DOING
```

提交以后：

```text
SUBMITTED
```

---

# 27. 学生具体答题表 exam_answer

如果只保存：

```text
80分
```

以后无法查看：

学生哪道题答错。

因此建议保留ExamAnswer。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| exam_record_id | BIGINT | 考试记录 |
| question_id | BIGINT | 题目 |
| student_answer | VARCHAR(500) | 学生答案 |
| is_correct | TINYINT | 是否正确 |
| score | DECIMAL(5,2) | 本题得分 |
| created_at | DATETIME | 创建 |

唯一：

```text
exam_record_id + question_id
```

---

# 28. 公告表 notice

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| created_by | BIGINT | 管理员 |
| title | VARCHAR(200) | 标题 |
| content | LONGTEXT | 内容 |
| status | VARCHAR(20) | 状态 |
| publish_time | DATETIME | 发布时间 |
| created_at | DATETIME | 创建 |
| updated_at | DATETIME | 修改 |

状态：

```text
DRAFT
PUBLISHED
OFFLINE
```

---

# 29. 收藏表 favorite

学生收藏课程。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| student_id | BIGINT | 学生 |
| course_id | BIGINT | 课程 |
| created_at | DATETIME | 收藏时间 |

唯一：

```text
student_id + course_id
```

---

# 30. 完整MySQL建表脚本

下面可以直接作为第一版数据库初始化脚本。

```sql
USE student_tutoring;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;


-- =========================================================
-- 1. 用户
-- =========================================================

CREATE TABLE sys_user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(50) NOT NULL,

    student_no VARCHAR(50) NULL,
    teacher_no VARCHAR(50) NULL,

    email VARCHAR(100) NULL,
    phone VARCHAR(20) NULL,
    avatar VARCHAR(255) NULL,

    role VARCHAR(20) NOT NULL,
    status TINYINT NOT NULL DEFAULT 1,

    last_login_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_user_username (username),
    UNIQUE KEY uk_user_student_no (student_no),
    UNIQUE KEY uk_user_teacher_no (teacher_no),
    UNIQUE KEY uk_user_email (email),

    KEY idx_user_role (role),
    KEY idx_user_status (status)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 2. 课程分类
-- =========================================================

CREATE TABLE course_category (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    name VARCHAR(50) NOT NULL,
    description VARCHAR(255) NULL,

    sort_order INT NOT NULL DEFAULT 0,
    status TINYINT NOT NULL DEFAULT 1,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_category_name (name),
    KEY idx_category_status_sort (status, sort_order)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 3. 课程
-- =========================================================

CREATE TABLE course (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    teacher_id BIGINT UNSIGNED NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,

    name VARCHAR(100) NOT NULL,
    cover VARCHAR(255) NULL,

    description VARCHAR(500) NULL,
    detail TEXT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    published_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_course_teacher (teacher_id),
    KEY idx_course_category (category_id),
    KEY idx_course_status (status),
    KEY idx_course_category_status (category_id, status),

    CONSTRAINT fk_course_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_course_category
        FOREIGN KEY (category_id)
        REFERENCES course_category(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 4. 学生加入课程
-- =========================================================

CREATE TABLE course_student (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    course_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,

    join_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TINYINT NOT NULL DEFAULT 1,

    PRIMARY KEY (id),

    UNIQUE KEY uk_course_student (
        course_id,
        student_id
    ),

    KEY idx_course_student_student (student_id),
    KEY idx_course_student_status (course_id, status),

    CONSTRAINT fk_course_student_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_course_student_user
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 5. 课程章节
-- =========================================================

CREATE TABLE chapter (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    course_id BIGINT UNSIGNED NOT NULL,

    title VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,

    sort_order INT NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_chapter_course_sort (
        course_id,
        sort_order
    ),

    CONSTRAINT fk_chapter_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 6. 教学视频
-- =========================================================

CREATE TABLE video (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    chapter_id BIGINT UNSIGNED NOT NULL,

    title VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,

    original_name VARCHAR(255) NULL,

    original_file VARCHAR(500) NULL,
    processed_file VARCHAR(500) NULL,
    hls_path VARCHAR(500) NULL,
    cover VARCHAR(500) NULL,

    duration DECIMAL(10,3) NULL,

    width INT NULL,
    height INT NULL,

    video_codec VARCHAR(50) NULL,
    audio_codec VARCHAR(50) NULL,

    bitrate BIGINT NULL,
    frame_rate DECIMAL(8,3) NULL,
    file_size BIGINT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    process_step VARCHAR(30) NULL,

    error_message TEXT NULL,

    sort_order INT NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_video_chapter_sort (
        chapter_id,
        sort_order
    ),

    KEY idx_video_status (status),

    KEY idx_video_process (
        status,
        process_step
    ),

    CONSTRAINT fk_video_chapter
        FOREIGN KEY (chapter_id)
        REFERENCES chapter(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 7. 视频学习记录
-- =========================================================

CREATE TABLE learning_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    student_id BIGINT UNSIGNED NOT NULL,
    video_id BIGINT UNSIGNED NOT NULL,

    current_time DECIMAL(10,3) NOT NULL DEFAULT 0,

    watch_duration INT UNSIGNED NOT NULL DEFAULT 0,

    progress DECIMAL(5,2) NOT NULL DEFAULT 0,

    status VARCHAR(20) NOT NULL DEFAULT 'LEARNING',

    last_watch_time DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_learning_student_video (
        student_id,
        video_id
    ),

    KEY idx_learning_student_time (
        student_id,
        last_watch_time
    ),

    KEY idx_learning_video (video_id),

    KEY idx_learning_status (
        student_id,
        status
    ),

    CONSTRAINT fk_learning_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_learning_video
        FOREIGN KEY (video_id)
        REFERENCES video(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 8. 视频笔记
-- =========================================================

CREATE TABLE video_note (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    student_id BIGINT UNSIGNED NOT NULL,
    video_id BIGINT UNSIGNED NOT NULL,

    video_time DECIMAL(10,3) NOT NULL DEFAULT 0,

    content TEXT NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_note_student (
        student_id,
        created_at
    ),

    KEY idx_note_video (
        video_id,
        video_time
    ),

    CONSTRAINT fk_note_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_note_video
        FOREIGN KEY (video_id)
        REFERENCES video(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 9. 学生提问
-- =========================================================

CREATE TABLE question (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    student_id BIGINT UNSIGNED NOT NULL,
    video_id BIGINT UNSIGNED NOT NULL,

    video_time DECIMAL(10,3) NOT NULL DEFAULT 0,

    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'WAITING',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_question_student (
        student_id,
        created_at
    ),

    KEY idx_question_video (
        video_id,
        video_time
    ),

    KEY idx_question_status (
        status,
        created_at
    ),

    CONSTRAINT fk_question_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_question_video
        FOREIGN KEY (video_id)
        REFERENCES video(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 10. 教师回答
-- =========================================================

CREATE TABLE answer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    question_id BIGINT UNSIGNED NOT NULL,
    teacher_id BIGINT UNSIGNED NOT NULL,

    content TEXT NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_answer_question (question_id),

    KEY idx_answer_teacher (
        teacher_id,
        created_at
    ),

    CONSTRAINT fk_answer_question
        FOREIGN KEY (question_id)
        REFERENCES question(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_answer_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 11. 作业
-- =========================================================

CREATE TABLE homework (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    course_id BIGINT UNSIGNED NOT NULL,
    teacher_id BIGINT UNSIGNED NOT NULL,

    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,

    attachment VARCHAR(500) NULL,

    deadline DATETIME NULL,

    total_score DECIMAL(5,2)
        NOT NULL DEFAULT 100,

    status VARCHAR(20)
        NOT NULL DEFAULT 'DRAFT',

    published_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_homework_course (
        course_id,
        status
    ),

    KEY idx_homework_teacher (teacher_id),

    KEY idx_homework_deadline (
        status,
        deadline
    ),

    CONSTRAINT fk_homework_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_homework_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 12. 作业提交
-- =========================================================

CREATE TABLE homework_submission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    homework_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,

    content LONGTEXT NULL,

    attachment VARCHAR(500) NULL,

    status VARCHAR(20)
        NOT NULL DEFAULT 'SUBMITTED',

    score DECIMAL(5,2) NULL,

    teacher_comment TEXT NULL,

    submit_time DATETIME NULL,
    graded_time DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_submission_homework_student (
        homework_id,
        student_id
    ),

    KEY idx_submission_student (
        student_id,
        submit_time
    ),

    KEY idx_submission_homework_status (
        homework_id,
        status
    ),

    CONSTRAINT fk_submission_homework
        FOREIGN KEY (homework_id)
        REFERENCES homework(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_submission_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 13. 在线测验
-- =========================================================

CREATE TABLE exam (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    course_id BIGINT UNSIGNED NOT NULL,
    teacher_id BIGINT UNSIGNED NOT NULL,

    title VARCHAR(200) NOT NULL,
    description TEXT NULL,

    total_score DECIMAL(6,2)
        NOT NULL DEFAULT 100,

    status VARCHAR(20)
        NOT NULL DEFAULT 'DRAFT',

    start_time DATETIME NULL,
    end_time DATETIME NULL,

    time_limit_minutes INT NULL,

    published_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_exam_course (
        course_id,
        status
    ),

    KEY idx_exam_teacher (teacher_id),

    KEY idx_exam_time (
        start_time,
        end_time
    ),

    CONSTRAINT fk_exam_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_exam_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 14. 测验题目
-- =========================================================

CREATE TABLE exam_question (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    exam_id BIGINT UNSIGNED NOT NULL,

    question_type VARCHAR(20) NOT NULL,

    content TEXT NOT NULL,

    option_a VARCHAR(500) NULL,
    option_b VARCHAR(500) NULL,
    option_c VARCHAR(500) NULL,
    option_d VARCHAR(500) NULL,

    correct_answer VARCHAR(20) NOT NULL,

    score DECIMAL(5,2)
        NOT NULL DEFAULT 0,

    sort_order INT NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_exam_question_sort (
        exam_id,
        sort_order
    ),

    KEY idx_exam_question_type (
        exam_id,
        question_type
    ),

    CONSTRAINT fk_exam_question_exam
        FOREIGN KEY (exam_id)
        REFERENCES exam(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 15. 学生测验记录
-- =========================================================

CREATE TABLE exam_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    exam_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,

    score DECIMAL(6,2) NOT NULL DEFAULT 0,

    correct_count INT NOT NULL DEFAULT 0,
    wrong_count INT NOT NULL DEFAULT 0,

    status VARCHAR(20)
        NOT NULL DEFAULT 'DOING',

    started_at DATETIME NULL,
    submit_time DATETIME NULL,

    duration_seconds INT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_exam_record (
        exam_id,
        student_id
    ),

    KEY idx_exam_record_student (
        student_id,
        submit_time
    ),

    KEY idx_exam_record_exam_score (
        exam_id,
        score
    ),

    CONSTRAINT fk_exam_record_exam
        FOREIGN KEY (exam_id)
        REFERENCES exam(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_exam_record_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 16. 学生答题详情
-- =========================================================

CREATE TABLE exam_answer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    exam_record_id BIGINT UNSIGNED NOT NULL,
    question_id BIGINT UNSIGNED NOT NULL,

    student_answer VARCHAR(500) NULL,

    is_correct TINYINT NOT NULL DEFAULT 0,

    score DECIMAL(5,2) NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_exam_answer (
        exam_record_id,
        question_id
    ),

    KEY idx_exam_answer_question (
        question_id
    ),

    CONSTRAINT fk_exam_answer_record
        FOREIGN KEY (exam_record_id)
        REFERENCES exam_record(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_exam_answer_question
        FOREIGN KEY (question_id)
        REFERENCES exam_question(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 17. 系统公告
-- =========================================================

CREATE TABLE notice (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    created_by BIGINT UNSIGNED NULL,

    title VARCHAR(200) NOT NULL,

    content LONGTEXT NOT NULL,

    status VARCHAR(20)
        NOT NULL DEFAULT 'DRAFT',

    publish_time DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_notice_status_time (
        status,
        publish_time
    ),

    CONSTRAINT fk_notice_creator
        FOREIGN KEY (created_by)
        REFERENCES sys_user(id)
        ON DELETE SET NULL
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 18. 课程收藏
-- =========================================================

CREATE TABLE favorite (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    student_id BIGINT UNSIGNED NOT NULL,
    course_id BIGINT UNSIGNED NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_favorite_student_course (
        student_id,
        course_id
    ),

    KEY idx_favorite_course (course_id),

    CONSTRAINT fk_favorite_student
        FOREIGN KEY (student_id)
        REFERENCES sys_user(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_favorite_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


SET FOREIGN_KEY_CHECKS = 1;
```

---

# 31. 数据库删除策略

这里必须提前确定，否则后面接口非常容易出现问题。

## 用户

不推荐：

```sql
DELETE FROM sys_user
```

建议：

```text
status = 0
```

进行禁用。

原因：

用户可能关联：

- 课程；
- 学习记录；
- 问题；
- 回答；
- 作业；
- 成绩。

---

# 32. 课程删除

开发阶段允许：

```text
删除DRAFT课程
```

如果课程已经：

```text
PUBLISHED
```

更建议：

```text
OFFLINE
```

而不是物理删除。

这样不会导致大量：

```text
chapter
video
learning_record
question
homework
exam
```

被级联删除。

---

# 33. 视频删除

视频真正删除时必须处理两个层面。

数据库：

```text
DELETE video
```

同时文件系统删除：

```text
original_file

processed_file

hls目录

cover
```

所以应该通过Flask：

```text
VideoService.delete_video()
```

统一处理。

不能直接在数据库后台删Video记录。

---

# 34. 为什么部分外键使用CASCADE

例如：

```text
Course
 ↓
Chapter
 ↓
Video
```

如果真的删除Course：

对应Chapter已经失去意义。

因此：

```text
Course -> Chapter
```

使用：

```text
ON DELETE CASCADE
```

同理：

```text
Chapter -> Video
```

也是CASCADE。

---

# 35. 为什么用户关系使用RESTRICT

例如：

```text
course.teacher_id
```

如果教师账户被删除，而课程还存在：

课程就失去教师。

因此：

```text
ON DELETE RESTRICT
```

强制不允许直接删除用户。

这也进一步说明：

用户应该：

```text
禁用
```

而不是物理删除。

---

# 36. 主要索引设计

数据库索引不是越多越好。

第一版重点优化以下查询。

---

## 课程列表

常见：

```sql
WHERE category_id = ?
AND status = 'PUBLISHED'
```

所以：

```text
idx_course_category_status
```

---

## 教师查询课程

```sql
WHERE teacher_id = ?
```

所以：

```text
idx_course_teacher
```

---

## 章节查询

```sql
WHERE course_id = ?
ORDER BY sort_order
```

所以：

```text
idx_chapter_course_sort
```

---

## 视频

```sql
WHERE chapter_id = ?
ORDER BY sort_order
```

对应：

```text
idx_video_chapter_sort
```

---

# 37. 学习记录索引

学生个人中心经常查询：

```sql
WHERE student_id = ?
ORDER BY last_watch_time DESC
```

因此：

```text
idx_learning_student_time
```

非常重要。

---

# 38. 教师答疑查询

教师经常查询：

```sql
WHERE status = 'WAITING'
ORDER BY created_at DESC
```

所以：

```text
idx_question_status
```

---

# 39. 作业批改

查询：

```sql
WHERE homework_id = ?
AND status = 'SUBMITTED'
```

所以：

```text
idx_submission_homework_status
```

---

# 40. 学习统计不要单独建立统计表

第一版不要建立：

```text
course_statistics
student_statistics
video_statistics
```

这种统计表。

因为容易造成：

```text
原始数据和统计数据不一致
```

直接从：

```text
learning_record
homework_submission
exam_record
```

聚合统计。

例如课程平均进度：

```text
AVG(progress)
```

---

# 41. 课程学生数量

不要在Course存：

```text
student_count
```

第一版直接：

```sql
SELECT COUNT(*)
FROM course_student
WHERE course_id = ?
AND status = 1;
```

即可。

---

# 42. 课程视频数量

不要Course存：

```text
video_count
```

直接：

```text
Course
 ↓
Chapter
 ↓
Video
```

COUNT即可。

---

# 43. 视频时间统一保存秒数

数据库不要存：

```text
12:35
```

字符串。

应该存：

```text
755.000
```

即：

```text
秒
```

前端负责转换：

```text
755
→
12:35
```

这样可以直接：

```javascript
video.currentTime = 755
```

---

# 44. 文件大小统一保存字节

例如：

数据库：

```text
536870912
```

前端显示：

```text
512 MB
```

不要直接数据库保存：

```text
512MB
```

否则不利于排序和计算。

---

# 45. 视频时长统一保存秒

数据库：

```text
1256.335
```

前端：

```text
20:56
```

避免：

```text
00:20:56
```

直接作为数据库核心值。

---

# 46. 状态常量设计

Flask项目中建议建立：

```text
app/constants.py
```

统一保存状态。

用户：

```text
ADMIN
TEACHER
STUDENT
```

课程：

```text
DRAFT
PUBLISHED
OFFLINE
```

视频：

```text
UPLOADING
PENDING
PROCESSING
READY
FAILED
```

学习：

```text
NOT_STARTED
LEARNING
COMPLETED
```

问题：

```text
WAITING
ANSWERED
CLOSED
```

作业：

```text
DRAFT
PUBLISHED
CLOSED
```

测验：

```text
DRAFT
PUBLISHED
CLOSED
```

---

# 47. Flask-SQLAlchemy Model划分

后端建议：

```text
app/models/
```

结构：

```text
models/

├── user.py
├── category.py
├── course.py
├── chapter.py
├── video.py
├── learning.py
├── question.py
├── homework.py
├── exam.py
├── notice.py
└── __init__.py
```

---

# 48. Model对应关系

user.py：

```text
User
```

category.py：

```text
CourseCategory
```

course.py：

```text
Course
CourseStudent
Favorite
```

chapter.py：

```text
Chapter
```

video.py：

```text
Video
```

learning.py：

```text
LearningRecord
VideoNote
```

question.py：

```text
Question
Answer
```

homework.py：

```text
Homework
HomeworkSubmission
```

exam.py：

```text
Exam
ExamQuestion
ExamRecord
ExamAnswer
```

notice.py：

```text
Notice
```

---

# 49. 推荐SQLAlchemy关系

User：

```text
User
 ├─ teaching_courses
 ├─ joined_courses
 ├─ learning_records
 ├─ video_notes
 ├─ questions
 ├─ answers
 ├─ homework_submissions
 └─ exam_records
```

Course：

```text
Course
 ├─ teacher
 ├─ category
 ├─ chapters
 ├─ students
 ├─ homeworks
 └─ exams
```

Chapter：

```text
Chapter
 └─ videos
```

Video：

```text
Video
 ├─ learning_records
 ├─ notes
 └─ questions
```

---

# 50. 第一版数据库禁止随意增加的字段

暂时不要加入：

```text
course.total_student_count

course.avg_progress

video.play_count

video.question_count

student.total_learning_time

student.course_count
```

这些都属于：

```text
可计算字段
```

前期直接统计。

如果未来真的出现性能问题：

再增加缓存字段。

---

# 51. 必须提前考虑的数据一致性

例如教师创建Course：

必须保证：

```text
teacher_id
```

对应用户：

```text
role = TEACHER
```

但数据库外键本身只能确保：

```text
User存在
```

不能确保：

```text
User.role = TEACHER
```

因此必须由：

```text
Flask Service
```

验证。

同理：

```text
student_id
```

必须保证：

```text
role = STUDENT
```

---

# 52. 典型业务事务

学生加入课程：

```text
检查课程存在

↓

检查PUBLISHED

↓

检查学生身份

↓

检查是否已加入

↓

INSERT course_student
```

这些操作应该在一个Service中完成。

---

# 53. 视频处理事务

上传视频：

```text
保存文件
↓
创建Video
↓
COMMIT
↓
Celery.delay(video.id)
```

特别注意：

必须：

```text
数据库COMMIT成功
```

以后再提交Celery。

否则Worker可能提前运行：

```text
Video.query.get(video_id)
```

结果找不到记录。

---

# 54. 测验提交事务

学生提交测验：

```text
查询Exam

↓

检查是否允许提交

↓

查询ExamQuestion

↓

创建/更新ExamAnswer

↓

自动判题

↓

计算总分

↓

更新ExamRecord

↓

COMMIT
```

建议整个过程使用：

```text
数据库事务
```

避免部分答案保存、部分失败。

---

# 55. 默认初始化数据

系统第一次启动建议自动准备：

课程分类：

```text
计算机
数学
英语
物理
其他
```

管理员：

```text
username = admin
role = ADMIN
```

管理员初始密码不要直接写入SQL明文。

通过Python初始化脚本：

```text
seed.py
```

使用Werkzeug：

```text
generate_password_hash()
```

生成。

---

# 56. 数据库最终ER关系总结

```text
SYS_USER
│
├─ Teacher
│    │
│    ├─ COURSE
│    │    │
│    │    ├─ CHAPTER
│    │    │    │
│    │    │    └─ VIDEO
│    │    │         │
│    │    │         ├─ LEARNING_RECORD
│    │    │         ├─ VIDEO_NOTE
│    │    │         └─ QUESTION
│    │    │                 │
│    │    │                 └─ ANSWER
│    │    │
│    │    ├─ HOMEWORK
│    │    │      │
│    │    │      └─ HOMEWORK_SUBMISSION
│    │    │
│    │    └─ EXAM
│    │           │
│    │           ├─ EXAM_QUESTION
│    │           │
│    │           └─ EXAM_RECORD
│    │                   │
│    │                   └─ EXAM_ANSWER
│    │
│    └─ ANSWER
│
└─ Student
     │
     ├─ COURSE_STUDENT
     ├─ FAVORITE
     ├─ LEARNING_RECORD
     ├─ VIDEO_NOTE
     ├─ QUESTION
     ├─ HOMEWORK_SUBMISSION
     └─ EXAM_RECORD
```

---

# 57. 数据库最终确定版本

第一阶段正式开发使用以下18张表：

```text
sys_user

course_category

course

course_student

chapter

video

learning_record

video_note

question

answer

homework

homework_submission

exam

exam_question

exam_record

exam_answer

notice

favorite
```

其中整个系统最核心的数据库链路为：

```text
sys_user

↓

course

↓

chapter

↓

video

↓

learning_record

↓

question

↓

answer
```

而FFmpeg主要围绕：

```text
video
```

表工作。

项目开发前期应该优先实现：

```text
sys_user

course_category

course

chapter

video
```

这5张核心表。

完成视频链路以后再依次增加：

```text
course_student

learning_record

video_note

question

answer
```

最后增加：

```text
homework

exam

notice

favorite
```

通过这种顺序开发，可以最大程度降低数据库结构反复修改带来的返工。
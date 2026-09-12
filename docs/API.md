# API 清单

开发地址：`http://127.0.0.1:5000`

除文件上传外，请求体使用 JSON 对象，默认最大 1 MB；损坏或非对象 JSON 会返回 400。受保护接口通过请求头传递：

```text
Authorization: Bearer <access_token>
```

统一响应格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

响应中的日期时间使用 UTC ISO 8601 格式并带 `Z`，例如 `2026-09-12T08:30:00Z`。请求中的日期时间可以携带时区偏移，后端会统一换算为 UTC。

## 系统与认证

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/health` | 公开 | 健康检查 |
| POST | `/api/auth/register` | 公开 | 注册学生账号 |
| POST | `/api/auth/login` | 公开 | 用户名、邮箱、学号或工号登录 |
| POST | `/api/auth/reset-password` | 公开 | 使用用户名与已登记邮箱、学号、工号或手机号核验后设置新密码 |
| POST | `/api/auth/refresh` | Refresh Token | 轮换 Token 对；旧 Refresh Token 立即失效 |
| POST | `/api/auth/logout` | 任意 JWT | 注销当前及请求体中属于同一用户的 Token |
| GET | `/api/users/me` | 登录用户 | 当前用户资料 |
| GET | `/api/admin/users` | 管理员 | 分页查询用户；支持 `role`、`status`、`keyword`、`page`、`page_size` |
| POST | `/api/admin/users` | 管理员 | 创建教师或学生账号 |
| PUT | `/api/admin/users/{id}/status` | 管理员 | 启用或禁用教师/学生账号 |
| PUT | `/api/admin/users/{id}/password` | 管理员 | 为其他账号设置新密码并记录审计日志；不能重置当前登录账号 |

注册核心字段：`username`、`password`、`real_name`，可选 `email`、`phone`、`student_no`。登录字段为 `account`、`password`。退出时可在 JSON 中附带 `access_token`、`refresh_token`，后端会校验归属后统一注销。

## 班级与课程安排

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/classes` | 教师/学生 | 教师查看自己的班级和完整名册；学生仅查看本人所在班级、教师与已发布班级课程 |
| GET | `/api/classes/course-options` | 教师 | 获取本人课程的轻量选择列表 |
| POST | `/api/classes` | 教师 | 创建班级 |
| PUT | `/api/classes/{id}` | 班级教师 | 编辑班级资料 |
| DELETE | `/api/classes/{id}` | 班级教师 | 删除班级及班级关系 |
| POST | `/api/classes/{id}/students` | 班级教师 | 按用户名、学号或邮箱添加学生 |
| DELETE | `/api/classes/{id}/students/{student_id}` | 班级教师 | 将学生移出班级 |
| POST | `/api/classes/{id}/courses` | 班级教师 | 关联本人的课程并将当前名册整班加入 |
| DELETE | `/api/classes/{id}/courses/{course_id}` | 班级教师 | 解除班级课程关联 |

关联课程请求体为 `{"course_id": 1}`。关联时，已有学生会自动加入课程；之后新增到班级的学生也会同步加入该班级的全部关联课程。已有但已退出的课程关系会重新启用。解除课程关联、移出学生或删除班级只调整班级关系，不删除学生已有的课程关系、学习进度、作业或测验记录。教师可预先关联草稿或已下线课程，学生端只返回其中已发布的课程。

## 课程与章节

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/courses/categories` | 公开 | 分类列表 |
| GET | `/api/courses` | 公开 | 已发布课程；可传 `category_id` |
| GET | `/api/courses/mine` | 教师 | 我的课程 |
| GET | `/api/courses/{id}` | 公开/所有者 | 课程详情 |
| POST | `/api/courses` | 教师 | 创建课程 |
| PUT | `/api/courses/{id}` | 课程教师 | 编辑课程资料 |
| POST | `/api/courses/{id}/cover` | 课程教师 | 上传或替换课程封面 |
| DELETE | `/api/courses/{id}/cover` | 课程教师 | 移除课程封面 |
| DELETE | `/api/courses/{id}` | 课程教师 | 删除草稿课程 |
| POST | `/api/courses/{id}/publish` | 课程教师 | 发布课程 |
| POST | `/api/courses/{id}/offline` | 课程教师 | 下线课程 |
| POST | `/api/courses/{id}/chapters` | 课程教师 | 新增章节 |
| PUT | `/api/courses/{id}/chapters/{chapter_id}` | 课程教师 | 编辑章节 |
| DELETE | `/api/courses/{id}/chapters/{chapter_id}` | 课程教师 | 删除章节 |

课程创建字段：`name`、`category_id`，可选 `description`、`detail`。封面上传使用 `multipart/form-data` 的 `cover` 字段，支持 JPG、PNG、WebP，默认最大 5MB，可通过 `COURSE_COVER_MAX_LENGTH` 调整。课程响应中的 `cover_url` 可直接用于页面展示。章节创建字段：`title`，可选 `description`、`sort_order`。

## 视频

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| POST | `/api/videos/upload` | 课程教师 | 上传并处理章节视频 |
| GET | `/api/videos/{id}` | 公开/所有者 | 视频信息 |
| GET | `/api/videos/{id}/status` | 公开/所有者 | 处理状态 |
| PUT | `/api/videos/{id}` | 课程教师 | 修改标题、描述和排序 |
| POST | `/api/videos/{id}/retry` | 课程教师 | 重新处理失败视频 |
| POST | `/api/videos/{id}/replace` | 课程教师 | 替换源文件并重新处理 |
| DELETE | `/api/videos/{id}` | 课程教师 | 删除视频及关联学习数据 |
| GET | `/media/{path}` | 开发环境 | HLS、封面等媒体文件 |

上传使用 `multipart/form-data`：必填 `video_file`、`chapter_id`、`title`，可选 `description`、`sort_order`。支持 `.mp4`、`.mov`、`.mkv`、`.avi`、`.webm`。

同步模式完成时返回 `201`，处理失败返回 `422`，异步任务成功入队返回 `202`，队列不可用返回 `503` 并将视频标记为失败。状态依次为 `PENDING`、`PROCESSING`、`READY` 或 `FAILED`；处理步骤采用 `PROBING`、`TRANSCODING`、`HLS`、`COVER`、`FINISHED`。

视频标题、描述和排序可在课程任意状态下修改。失败重试仅接受 `FAILED` 状态且要求原始文件仍在受控媒体目录内。替换和删除会清理该视频对应的学习进度、笔记与答疑记录，因此仅允许课程处于草稿或已下线状态，且视频不在等待或处理中；替换成功后返回一个新的视频编号。

## 学习与收藏

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/learning/courses` | 学生 | 已加入课程及聚合学习进度 |
| POST | `/api/learning/courses/{id}/join` | 学生 | 加入已发布课程 |
| DELETE | `/api/learning/courses/{id}/join` | 学生 | 退出课程并保留历史学习数据 |
| GET | `/api/learning/courses/{id}/state` | 学生 | 查询加入与收藏状态 |
| GET | `/api/learning/favorites` | 学生 | 收藏课程列表 |
| POST | `/api/learning/courses/{id}/favorite` | 学生 | 收藏课程 |
| DELETE | `/api/learning/courses/{id}/favorite` | 学生 | 取消收藏 |
| GET | `/api/learning/videos/{id}/progress` | 已加入课程的学生 | 获取断点与学习进度 |
| PUT | `/api/learning/videos/{id}/progress` | 已加入课程的学生 | 更新断点与累计观看时长 |
| GET | `/api/learning/videos/{id}/notes` | 已加入课程的学生 | 当前视频的个人笔记 |
| POST | `/api/learning/videos/{id}/notes` | 已加入课程的学生 | 在视频时间点创建笔记 |
| PUT | `/api/learning/notes/{id}` | 笔记所有者 | 更新笔记 |
| DELETE | `/api/learning/notes/{id}` | 笔记所有者 | 删除笔记 |

学习进度更新字段为 `current_time` 和 `watch_duration_delta`。进度由后端根据视频时长计算，达到 90% 后自动标记为 `COMPLETED`；单次累计观看增量限制为 0–60 秒。

## 视频答疑

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/questions` | 学生/教师 | 学生查看自己的问题，教师查看自己课程的问题 |
| POST | `/api/questions` | 已加入课程的学生 | 在视频时间点提问 |
| GET | `/api/questions/{id}` | 提问学生/课程教师 | 问题详情 |
| POST | `/api/questions/{id}/answer` | 课程教师 | 提交唯一正式回答 |
| PUT | `/api/questions/{id}/answer` | 回答教师 | 更新正式回答 |
| POST | `/api/questions/{id}/close` | 提问学生/课程教师 | 关闭问题 |

问题列表可使用 `status=WAITING|ANSWERED|CLOSED` 和 `video_id` 过滤。教师只能查看和处理自己课程下的问题，学生只能查看自己的问题。

## 作业

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/homeworks` | 学生 | 已加入课程的已发布/已关闭作业及本人提交 |
| GET | `/api/homeworks/manage` | 教师 | 我的作业及提交数量 |
| POST | `/api/homeworks` | 教师 | 创建作业草稿 |
| GET | `/api/homeworks/{id}` | 课程成员/课程教师 | 作业详情 |
| PUT | `/api/homeworks/{id}` | 课程教师 | 编辑草稿作业 |
| DELETE | `/api/homeworks/{id}` | 课程教师 | 删除作业草稿并清理附件目录 |
| POST | `/api/homeworks/{id}/attachment` | 课程教师 | 上传或替换草稿作业附件 |
| GET | `/api/homeworks/{id}/attachment` | 课程成员/课程教师 | 鉴权后在线预览作业附件；`download=1` 强制下载 |
| POST | `/api/homeworks/{id}/publish` | 课程教师 | 发布作业 |
| POST | `/api/homeworks/{id}/close` | 课程教师 | 关闭作业 |
| PUT | `/api/homeworks/{id}/submission` | 课程学生 | 提交或更新文字答案 |
| POST | `/api/homeworks/{id}/submission/attachment` | 课程学生 | 提交或替换本人附件 |
| GET | `/api/homeworks/submissions/{id}/attachment` | 提交学生/课程教师 | 鉴权后预览提交附件；`download=1` 强制下载 |
| GET | `/api/homeworks/{id}/submissions` | 课程教师 | 学生提交列表 |
| PUT | `/api/homeworks/submissions/{id}/grade` | 课程教师 | 保存得分和评语 |

作业状态为 `DRAFT/PUBLISHED/CLOSED`。同一学生同一作业只保留一条最终提交；重新提交会将状态恢复为 `SUBMITTED` 并清除旧成绩。附件使用 `multipart/form-data` 的 `attachment` 字段，支持常用文档、压缩包和图片格式，最大 50 MB。

## 在线测验

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/exams` | 学生 | 已加入课程的测验及本人记录 |
| GET | `/api/exams/manage` | 教师 | 我的测验、题目和提交数量 |
| POST | `/api/exams` | 教师 | 创建测验草稿 |
| GET | `/api/exams/{id}` | 课程成员/课程教师 | 测验详情 |
| PUT | `/api/exams/{id}` | 课程教师 | 编辑草稿测验 |
| DELETE | `/api/exams/{id}` | 课程教师 | 删除测验草稿及其试题 |
| POST | `/api/exams/{id}/questions` | 课程教师 | 添加单选题或判断题 |
| PUT | `/api/exams/questions/{id}` | 课程教师 | 更新草稿试题 |
| DELETE | `/api/exams/questions/{id}` | 课程教师 | 删除草稿试题 |
| POST | `/api/exams/{id}/publish` | 课程教师 | 校验题目总分并发布 |
| POST | `/api/exams/{id}/close` | 课程教师 | 关闭测验 |
| POST | `/api/exams/{id}/start` | 课程学生 | 开始或继续未提交测验，并返回已保存答案 |
| PUT | `/api/exams/{id}/answers` | 课程学生 | 保存未交卷测验的答案草稿 |
| POST | `/api/exams/{id}/submit` | 课程学生 | 正式交卷并自动评分 |
| GET | `/api/exams/{id}/records` | 课程教师 | 查看成绩记录 |
| GET | `/api/exams/records/{id}` | 本人/课程教师 | 测验结果和逐题明细 |

第一版题型为 `SINGLE` 和 `JUDGE`，答案分别使用 `A/B/C/D` 与 `TRUE/FALSE`。保存和交卷体均为 `{"answers": [{"question_id": 1, "answer": "A"}]}`。每名学生每个测验只能正式提交一次；未交卷时响应不会包含 `correct_answer`。页面在选择答案后防抖保存，并在倒计时结束时自动交卷；若浏览器没有及时发出超时请求，后端在下一次查询或继续答题时会使用截止前已保存的答案完成交卷，不接受截止后的新答案。

## 站内消息

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/notifications` | 登录用户 | 分页查询本人通知；支持 `unread_only`、`page`、`page_size` |
| PUT | `/api/notifications/{id}/read` | 通知接收者 | 将单条通知标为已读 |
| PUT | `/api/notifications/read-all` | 登录用户 | 将本人全部未读通知标为已读 |

课程作业或测验发布、作业批改、答疑首次回复及更新回复都会产生站内通知。通知只能由接收者读取或改变已读状态。

## 公告、统计与后台

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/notices` | 公开 | 已发布公告 |
| GET | `/api/notices/manage` | 管理员 | 全部公告 |
| POST | `/api/notices` | 管理员 | 创建公告草稿 |
| PUT | `/api/notices/{id}` | 管理员 | 编辑草稿或已下线公告 |
| PUT | `/api/notices/{id}/status` | 管理员 | 发布或下线公告 |
| DELETE | `/api/notices/{id}` | 管理员 | 删除未发布公告 |
| GET | `/api/statistics` | 学生/教师/管理员 | 当前角色的实时聚合概览 |
| GET | `/api/statistics/courses` | 教师 | 本人课程的学生、进度、作业和测验聚合 |
| GET | `/api/statistics/classes/{id}` | 班级教师 | 按当前班级名册聚合关联课程的视频、作业和测验进展 |

班级统计以当前班级成员数为完成率分母，仅计算该班级已关联课程。视频进度按可播放视频计算；作业和测验总量只包含已发布或已关闭内容；作业平均分仅统计已批改提交，测验平均分仅统计已交卷记录。

### 管理员运维接口

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/admin/videos` | 管理员 | 分页查询转码任务、状态汇总和 FFmpeg/ffprobe 运行状态；支持 `status`、`keyword`、`page`、`page_size` |
| POST | `/api/admin/videos/{id}/retry` | 管理员 | 重新处理失败任务，或恢复超过 30 分钟未更新的等待/处理任务 |
| DELETE | `/api/admin/videos/{id}` | 管理员 | 清理失败任务、原始文件和派生文件 |
| GET | `/api/admin/courses` | 管理员 | 跨教师分页查询课程、章节、视频和学生数量；支持 `status`、`keyword`、`page`、`page_size` |
| PUT | `/api/admin/courses/{id}/status` | 管理员 | 强制下线课程或恢复发布 |
| GET | `/api/admin/classes` | 管理员 | 跨教师查询班级与成员数量；支持 `keyword` |
| DELETE | `/api/admin/classes/{id}` | 管理员 | 删除班级及成员关系，不删除师生账号 |
| GET | `/api/admin/categories` | 管理员 | 查看启用和禁用的全部课程分类 |
| POST | `/api/admin/categories` | 管理员 | 创建课程分类 |
| PUT | `/api/admin/categories/{id}` | 管理员 | 修改课程分类资料和排序 |
| PUT | `/api/admin/categories/{id}/status` | 管理员 | 启用或禁用课程分类 |
| GET | `/api/admin/audit-logs` | 管理员 | 分页查询管理操作审计；支持 `action`、`resource_type`、`keyword`、`page`、`page_size` |

管理员用户、视频、课程和审计查询统一使用 `page` 与 `page_size`，默认分别为 1 和 20，`page_size` 最大为 100。用户、课程和审计接口的 `data` 结构为 `{ "items": [], "pagination": { "page", "page_size", "total", "pages" } }`；视频接口还会同时返回全局状态 `summary` 与媒体工具 `runtime`。非法页码返回 400，超出末页时返回空 `items` 和实际分页元数据。

审计日志记录管理员、动作、资源类型与编号、可读摘要、必要的非敏感详情、来源 IP、User-Agent 和 UTC 时间。当前覆盖账号创建与启停、视频重试与失败文件清理、课程状态、班级删除、分类维护及公告创建、编辑、状态变更和删除；日志只读，不提供修改或删除接口。

视频任务只有在 `FAILED`，或 `PENDING/PROCESSING` 超过 30 分钟未更新时才能重新处理；重新处理前必须确认受控媒体目录内的原始文件仍存在。清理操作仅允许 `FAILED` 状态，接口会拒绝删除正常处理或可播放的视频。

公告状态为 `DRAFT/PUBLISHED/OFFLINE`。统计结果实时读取业务表，不维护独立统计表。

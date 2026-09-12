# API 清单

开发地址：`http://127.0.0.1:5000`

除文件上传外，请求体使用 JSON。受保护接口通过请求头传递：

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

## 系统与认证

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/health` | 公开 | 健康检查 |
| POST | `/api/auth/register` | 公开 | 注册学生账号 |
| POST | `/api/auth/login` | 公开 | 用户名、邮箱或手机号登录 |
| POST | `/api/auth/refresh` | Refresh Token | 轮换 Token 对；旧 Refresh Token 立即失效 |
| POST | `/api/auth/logout` | 任意 JWT | 注销当前及请求体中属于同一用户的 Token |
| GET | `/api/users/me` | 登录用户 | 当前用户资料 |
| POST | `/api/admin/users` | 管理员 | 创建教师或学生账号 |

注册核心字段：`username`、`password`、`real_name`，可选 `email`、`phone`、`student_no`。登录字段为 `account`、`password`。退出时可在 JSON 中附带 `access_token`、`refresh_token`，后端会校验归属后统一注销。

## 课程与章节

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/courses/categories` | 公开 | 分类列表 |
| GET | `/api/courses` | 公开 | 已发布课程；可传 `category_id` |
| GET | `/api/courses/mine` | 教师 | 我的课程 |
| GET | `/api/courses/{id}` | 公开/所有者 | 课程详情 |
| POST | `/api/courses` | 教师 | 创建课程 |
| PUT | `/api/courses/{id}` | 课程教师 | 编辑草稿课程 |
| DELETE | `/api/courses/{id}` | 课程教师 | 删除草稿课程 |
| POST | `/api/courses/{id}/publish` | 课程教师 | 发布课程 |
| POST | `/api/courses/{id}/offline` | 课程教师 | 下线课程 |
| POST | `/api/courses/{id}/chapters` | 课程教师 | 新增章节 |
| PUT | `/api/courses/{id}/chapters/{chapter_id}` | 课程教师 | 编辑章节 |
| DELETE | `/api/courses/{id}/chapters/{chapter_id}` | 课程教师 | 删除章节 |

课程创建字段：`name`、`category_id`，可选 `description`、`detail`。章节创建字段：`title`，可选 `description`、`sort_order`。

## 视频

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| POST | `/api/videos/upload` | 课程教师 | 上传并处理章节视频 |
| GET | `/api/videos/{id}` | 公开/所有者 | 视频信息 |
| GET | `/api/videos/{id}/status` | 公开/所有者 | 处理状态 |
| GET | `/media/{path}` | 开发环境 | HLS、封面等媒体文件 |

上传使用 `multipart/form-data`：必填 `video_file`、`chapter_id`、`title`，可选 `description`、`sort_order`。支持 `.mp4`、`.mov`、`.mkv`、`.avi`、`.webm`。

同步模式完成时返回 `201`，处理失败返回 `422`，异步任务成功入队返回 `202`，队列不可用返回 `503` 并将视频标记为失败。状态依次为 `PENDING`、`PROCESSING`、`READY` 或 `FAILED`；处理步骤采用 `PROBING`、`TRANSCODING`、`HLS`、`COVER`、`FINISHED`。

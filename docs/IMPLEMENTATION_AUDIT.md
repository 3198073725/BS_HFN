# 当前实现审计报告

审计日期：2026-09-12

## 已发现并修复

1. 删除无效且不安全的全局 Git `user.password` 明文配置；保留姓名和邮箱。
2. 固定测试环境为同步视频模式，避免本地 `.env` 污染测试并误连默认 AMQP。
3. Refresh Token 改为单次轮换，退出时可同时注销同一用户的 Access/Refresh Token。
4. 前端增加 Access Token 过期后的单次并发刷新与请求重放。
5. 公开课程和视频接口不再暴露未完成视频及其内部错误信息。
6. Celery 投递失败现在返回 503，并持久化 `FAILED/QUEUE`，不再永久停在 `PENDING`。
7. 视频任务增加两次指数退避重试；重试等待期间回到 `PENDING`，最终失败保留错误信息。
8. FFmpeg 处理步骤统一为数据库文档定义的 `PROBING/TRANSCODING/HLS/COVER/FINISHED`。
9. 转码失败和删除章节/课程时清理派生媒体文件，且限制清理范围只能位于媒体根目录。
10. 支持中文原始视频名，拒绝空文件、超长文件名和负数排序。
11. Windows 下 FFmpeg/ffprobe 输出改为容错解码，消除中文路径导致的读取线程异常。
12. 移除未使用且存在中危 XSS 公告的 ECharts 5；统计模块开发时再引入安全版本。
13. Vite 从 5.4.21 升级到 6.4.3，消除旧版 esbuild 的开发服务器安全公告。
14. 生产环境启动时强制校验至少 32 位的 Flask/JWT 密钥，并收紧默认 CORS 来源。

## 验证结果

- 后端测试：14/14 通过，包含真实 FFmpeg 转码、HLS、封面和上传链路。
- 真实异步链路：MySQL → Redis → Celery → FFmpeg → `READY/FINISHED` 通过，验收数据自动清理。
- 前端：Vite 6.4.3 生产构建通过。
- 依赖：`pip check` 正常；`npm audit` 为 0 个漏洞。
- 数据库：Flask-Migrate 检查无模型漂移。

## 已知非阻塞事项

- Element Plus 与 hls.js 的两个按页加载分块仍超过 500 kB；不影响功能，后续可在页面增多时继续拆分。
- 当前媒体文件由 Flask 仅在开发模式提供；生产部署应交给 Nginx，并配置缓存、Range、MIME 和访问策略。
- Access/Refresh Token 当前保存在浏览器 `localStorage`。毕业设计开发阶段可接受；生产级部署建议将 Refresh Token 改为 HttpOnly、Secure、SameSite Cookie。

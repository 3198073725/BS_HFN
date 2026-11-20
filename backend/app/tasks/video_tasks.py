"""视频异步任务入口，只传递数据库主键，不传请求或 ORM 对象。"""

from celery import shared_task


@shared_task(name='course.generate_summary')
def generate_course_summary(course_id: int, task_id: str):
    # 兼容 Redis 中残留的旧消息，禁止再触发整门课程生成。
    from app.extensions import db
    from app.models import CourseAISummary
    db.session.execute(db.update(CourseAISummary).where(
        CourseAISummary.course_id == course_id, CourseAISummary.task_id == task_id
    ).values(status='CANCELLED', task_id=None, error_message='已改为按视频生成，请刷新页面'))
    db.session.commit()


@shared_task(name='video.generate_summary')
def generate_video_summary(video_id: int, task_id: str):
    from app.services.video_ai_service import run_video_summary
    run_video_summary(video_id, task_id)

from app.services.video_processing_service import (
    VideoProcessingError,
    mark_video_retry_pending,
    process_video_sync,
)


@shared_task(
    bind=True,
    name="video.process",
    max_retries=2,
)
def process_video(self, video_id: int, task_id: str | None = None) -> None:
    try:
        process_video_sync(video_id, raise_on_error=True, expected_task_id=task_id)
    except VideoProcessingError as exc:
        if self.request.retries >= self.max_retries:
            raise
        countdown = min(5 * (2**self.request.retries), 60)
        mark_video_retry_pending(video_id, f"处理失败，将在 {countdown} 秒后重试")
        raise self.retry(exc=exc, countdown=countdown)

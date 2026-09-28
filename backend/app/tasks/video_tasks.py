"""视频异步任务入口，只传递数据库主键，不传请求或 ORM 对象。"""

from celery import shared_task

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

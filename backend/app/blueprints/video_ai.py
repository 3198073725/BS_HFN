import uuid
from flask import Blueprint, Response, current_app
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import User, VideoSubtitle, VideoAISummary
from app.utils import roles_required, success, error, json_body
from app.services.video_ai_service import ACTIVE, material, summary_payload
from app.services.course_ai_service import webvtt
from app.services.video_processing_service import get_visible_video, VideoNotFound

ai_bp = Blueprint('video_ai', __name__)


def context(video_id, manage=False):
    user = db.session.get(User, int(get_jwt_identity()))
    try:
        video = get_visible_video(video_id, user.id, user.role)
    except VideoNotFound:
        return None, user, error('视频不存在或不可见', 404)
    course = video.chapter.course
    owner = user.role == 'ADMIN' or (user.role == 'TEACHER' and user.id == course.teacher_id)
    if manage and not owner:
        return video, user, error('仅授课教师或管理员可管理总结', 403)
    return video, user, None


@ai_bp.get('/courses/<int:course_id>/ai-summary')
@ai_bp.post('/courses/<int:course_id>/ai-summary/generate')
@ai_bp.put('/courses/<int:course_id>/ai-summary')
@roles_required('STUDENT', 'TEACHER', 'ADMIN')
def retired_course_summary(course_id):
    return error('已改为按视频生成总结，请刷新页面并选择具体视频', 410)


@ai_bp.get('/videos/<int:video_id>/ai-summary')
@roles_required('STUDENT', 'TEACHER', 'ADMIN')
def detail(video_id):
    video, user, failure = context(video_id)
    return failure if failure else success(summary_payload(video, user))


@ai_bp.post('/videos/<int:video_id>/ai-summary/generate')
@roles_required('TEACHER', 'ADMIN')
def generate(video_id):
    video, user, failure = context(video_id, True)
    if failure:
        return failure
    if video.status != 'READY':
        return error('仅已就绪的视频可以生成总结', 409)
    if not current_app.config['DEEPSEEK_API_KEY']:
        return error('请先在 backend/.env 配置 DEEPSEEK_API_KEY', 409)
    if not current_app.extensions.get('celery'):
        return error('请先启动 Celery 工作进程', 503)
    row = db.session.scalar(db.select(VideoAISummary).where(VideoAISummary.video_id == video_id))
    task_id = uuid.uuid4().hex
    try:
        if row:
            changed = db.session.execute(db.update(VideoAISummary).where(
                VideoAISummary.id == row.id, VideoAISummary.status.notin_(ACTIVE)
            ).values(status='QUEUED', task_id=task_id, error_message=None,
                     progress=0, progress_message='当前视频任务等待处理'))
            if changed.rowcount != 1:
                db.session.rollback()
                return error('当前视频正在生成中', 409)
        else:
            db.session.add(VideoAISummary(video_id=video_id, status='QUEUED', task_id=task_id,
                                          progress=0, progress_message='当前视频任务等待处理'))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error('当前视频任务已创建，请刷新页面', 409)
    try:
        from app.tasks.video_tasks import generate_video_summary
        generate_video_summary.apply_async(args=[video_id, task_id], task_id=task_id)
    except Exception:
        db.session.execute(db.update(VideoAISummary).where(
            VideoAISummary.video_id == video_id, VideoAISummary.task_id == task_id,
            VideoAISummary.status == 'QUEUED').values(status='FAILED', task_id=None,
                error_message='队列不可用，请启动 Redis 和 Celery 后重试'))
        db.session.commit()
        return error('队列不可用，请启动 Redis 和 Celery 后重试', 503)
    return success(summary_payload(video, user), '已开始生成当前视频字幕及总结', 202)


@ai_bp.post('/videos/<int:video_id>/ai-summary/cancel')
@roles_required('TEACHER', 'ADMIN')
def cancel(video_id):
    video, user, failure = context(video_id, True)
    if failure:
        return failure
    changed = db.session.execute(db.update(VideoAISummary).where(
        VideoAISummary.video_id == video_id, VideoAISummary.status.in_(ACTIVE)
    ).values(status='CANCELLED', task_id=None, progress_message='已取消当前视频任务', error_message=None))
    db.session.commit()
    if not changed.rowcount:
        return error('当前视频没有正在执行的总结任务', 409)
    return success(summary_payload(video, user), '取消指令已记录，处理进程将在检查点退出')


@ai_bp.put('/videos/<int:video_id>/ai-summary')
@roles_required('TEACHER', 'ADMIN')
def edit(video_id):
    video, user, failure = context(video_id, True)
    if failure:
        return failure
    payload = json_body()
    content = str(payload.get('content') or '').strip()
    publish = payload.get('publish', False)
    if not isinstance(publish, bool) or not 1 <= len(content) <= 50000:
        return error('总结需为 1～50000 字，发布参数需为布尔值', 400)
    row = db.session.scalar(db.select(VideoAISummary).where(VideoAISummary.video_id == video_id))
    if not row or row.status in ACTIVE or not row.source_hash:
        return error('请等待当前视频总结生成成功后再编辑发布', 409)
    if publish and (material(video)[1] != row.source_hash or video.status != 'READY'):
        return error('当前视频资料已变更或尚未就绪，请重新生成后发布', 409)
    changed = db.session.execute(db.update(VideoAISummary).where(
        VideoAISummary.id == row.id, VideoAISummary.status.notin_(ACTIVE)
    ).values(content=content, status='PUBLISHED' if publish else 'DRAFT'))
    db.session.commit()
    if not changed.rowcount:
        return error('当前视频正在生成中，请稍后重试', 409)
    return success(summary_payload(video, user), '视频总结已发布' if publish else '草稿已保存')


@ai_bp.get('/videos/<int:video_id>/subtitle')
@roles_required('STUDENT', 'TEACHER', 'ADMIN')
def subtitle(video_id):
    video, user, failure = context(video_id)
    if failure:
        return failure
    row = db.session.scalar(db.select(VideoSubtitle).where(VideoSubtitle.video_id == video_id))
    if not row:
        return error('尚未生成字幕', 404)
    return Response(webvtt(row.segments), mimetype='text/vtt', headers={'Cache-Control': 'private, no-store'})

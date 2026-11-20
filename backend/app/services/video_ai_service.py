"""每次任务仅处理一个视频，进度检查使用独立事务读取取消状态。"""
import hashlib
import json
import time
from flask import current_app
from app.extensions import db
from app.models import Video, VideoAISummary, CourseAISummary, CourseStudent, LearningRecord
from .course_ai_service import deepseek, transcribe

ACTIVE = {'QUEUED', 'EXTRACTING', 'SUBTITLING', 'SUMMARIZING'}


class SummaryCancelled(RuntimeError):
    pass


def material(video):
    payload = {'video': video.title, 'description': video.description,
               'chapter': video.chapter.title, 'chapter_description': video.chapter.description,
               'course': video.chapter.course.name, 'original_file': video.original_file,
               'file_size': video.file_size, 'status': video.status}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return payload, digest


def summary_payload(video, user):
    course = video.chapter.course
    row = db.session.scalar(db.select(VideoAISummary).where(VideoAISummary.video_id == video.id))
    policy = db.session.scalar(db.select(CourseAISummary).where(CourseAISummary.course_id == course.id))
    manager = user.role == 'ADMIN' or (user.role == 'TEACHER' and course.teacher_id == user.id)
    public = bool(policy and policy.open_to_students)
    unlocked, reason = manager, ''
    if not manager:
        joined = db.session.scalar(db.select(CourseStudent.id).where(
            CourseStudent.course_id == course.id, CourseStudent.student_id == user.id,
            CourseStudent.status.is_(True)))
        completed = db.session.scalar(db.select(LearningRecord.id).where(
            LearningRecord.video_id == video.id, LearningRecord.student_id == user.id,
            LearningRecord.status == 'COMPLETED'))
        unlocked = user.role == 'STUDENT' and course.status == 'PUBLISHED' and video.status == 'READY' and bool(public or (joined and completed))
        if not unlocked:
            reason = '加入课程并完成当前视频后解锁'
    stale = bool(row and row.source_hash and row.source_hash != material(video)[1])
    visible = row and unlocked and (manager or (row.status == 'PUBLISHED' and not stale))
    return {'video_id': video.id, 'video_title': video.title,
            'status': (row.status if row else 'NOT_GENERATED') if unlocked else 'LOCKED',
            'manager': manager, 'unlocked': unlocked, 'reason': reason,
            'open_to_students': public, 'stale': stale,
            'content': row.content if visible else None,
            'error_message': row.error_message if row and manager else None,
            'progress': row.progress if row and unlocked else 0,
            'progress_message': row.progress_message if row and unlocked else None,
            'configured': bool(current_app.config['DEEPSEEK_API_KEY']) if manager else None}


def run_video_summary(video_id, task_id):
    claimed = db.session.execute(db.update(VideoAISummary).where(
        VideoAISummary.video_id == video_id, VideoAISummary.task_id == task_id,
        VideoAISummary.status == 'QUEUED').values(status='EXTRACTING', progress=1))
    db.session.commit()
    if claimed.rowcount != 1:
        return
    last_write = [0.0]

    def report(status, progress, message, force=False):
        with db.engine.connect() as connection:
            state = connection.execute(db.select(VideoAISummary.status, VideoAISummary.task_id).where(
                VideoAISummary.video_id == video_id)).one_or_none()
        if not state or state[1] != task_id or state[0] not in ACTIVE:
            raise SummaryCancelled()
        now = time.monotonic()
        if not force and now - last_write[0] < 2:
            return
        result = db.session.execute(db.update(VideoAISummary).where(
            VideoAISummary.video_id == video_id, VideoAISummary.task_id == task_id,
            VideoAISummary.status.in_(ACTIVE)).values(status=status, progress=progress, progress_message=message))
        db.session.commit()
        if not result.rowcount:
            raise SummaryCancelled()
        last_write[0] = now

    try:
        video = db.session.get(Video, video_id)
        if not video or video.status != 'READY':
            raise ValueError('当前视频不可用')
        payload, digest = material(video)
        segments = transcribe(video, report=report)
        report('SUMMARIZING', 76, '正在总结当前视频字幕', True)
        text = '\n'.join(f'[{s["start"]:.0f}秒] {s["text"]}' for s in segments)
        chunks = [text[offset:offset + 12000] for offset in range(0, len(text), 12000)]
        parts = []
        for index, chunk in enumerate(chunks):
            report('SUMMARIZING', 76 + int(18 * index / len(chunks)), f'正在总结第 {index + 1}/{len(chunks)} 段', True)
            parts.append(deepseek('请总结当前视频的这段字幕：\n' + chunk))
        for _ in range(6):
            if sum(map(len, parts)) <= 20000:
                break
            grouped, batch = [], ''
            for part in parts:
                if len(batch) + len(part) > 16000:
                    report('SUMMARIZING', 94, '正在合并当前视频分段总结', True)
                    grouped.append(deepseek('请压缩并合并当前视频小结：\n' + batch))
                    batch = ''
                batch += part + '\n'
            if batch:
                report('SUMMARIZING', 94, '正在合并当前视频分段总结', True)
                grouped.append(deepseek('请压缩并合并当前视频小结：\n' + batch))
            parts = grouped
        if sum(map(len, parts)) > 20000:
            raise ValueError('当前视频总结过长，请稍后重试')
        report('SUMMARIZING', 96, '正在整理当前视频最终总结', True)
        # 源文件存储路径只用于指纹，不发送给模型。
        public_material = {k: v for k, v in payload.items() if k not in {'original_file', 'file_size', 'status'}}
        content = deepseek('仅总结这一个视频。视频资料：' + json.dumps(public_material, ensure_ascii=False)[:6000]
                           + '\n分段小结：\n' + '\n'.join(parts))
        report('SUMMARIZING', 99, '生成完成，正在保存审核草稿', True)
        db.session.execute(db.update(VideoAISummary).where(
            VideoAISummary.video_id == video_id, VideoAISummary.task_id == task_id,
            VideoAISummary.status.in_(ACTIVE)).values(content=content, source_hash=digest,
                status='DRAFT', task_id=None, error_message=None, progress=100, progress_message='当前视频总结已生成，待教师审核'))
        db.session.commit()
    except SummaryCancelled:
        db.session.rollback()
    except Exception as exc:
        db.session.rollback()
        db.session.execute(db.update(VideoAISummary).where(
            VideoAISummary.video_id == video_id, VideoAISummary.task_id == task_id,
            VideoAISummary.status.in_(ACTIVE)).values(status='FAILED', task_id=None,
                error_message=str(exc)[:400] if isinstance(exc, ValueError) else '当前视频总结生成失败，请检查工作进程日志后重试'))
        db.session.commit()
        current_app.logger.warning('视频 %s 总结失败：%s', video_id, type(exc).__name__)

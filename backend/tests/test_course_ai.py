from types import SimpleNamespace
from unittest.mock import patch
from flask_jwt_extended import create_access_token
from app.extensions import db
from app.models import (User, CourseCategory, Course, Chapter, Video, CourseStudent,
                        LearningRecord, CourseAISummary, Homework, HomeworkSubmission,
                        TeachingClass, TeachingClassCourse, TeachingClassJoinRequest)
from app.services.course_ai_service import webvtt
from app.services.video_ai_service import run_video_summary, material, summary_payload
from app.models import VideoAISummary
from app.services.token_service import credential_signature


def seed():
    teacher = User(username='ai_teacher', real_name='教师', password_hash='hash', role='TEACHER', teacher_no='AI01')
    student = User(username='ai_student', real_name='学生', password_hash='hash', role='STUDENT', student_no='AI02')
    category = CourseCategory(name='AI课程分类')
    db.session.add_all([teacher, student, category]); db.session.flush()
    course = Course(teacher_id=teacher.id, category_id=category.id, name='AI测试', status='PUBLISHED')
    db.session.add(course); db.session.flush()
    chapter = Chapter(course_id=course.id, title='第一章')
    db.session.add(chapter); db.session.flush()
    video = Video(chapter_id=chapter.id, title='测试视频', status='READY', original_file='videos/original/source.mp4')
    db.session.add(video)
    db.session.add(CourseStudent(course_id=course.id, student_id=student.id, status=True))
    db.session.commit()
    return teacher, student, course, video


def token(user):
    return {'Authorization': 'Bearer ' + create_access_token(identity=str(user.id), additional_claims={
        'credentials': credential_signature(user.password_hash)})}


def test_worker_processes_only_selected_video(app):
    with app.app_context():
        teacher, student, course, video = seed()
        other = Video(chapter_id=video.chapter_id, title='另一个视频', status='READY')
        db.session.add(other)
        db.session.add(VideoAISummary(video_id=video.id, task_id='one', status='QUEUED'))
        db.session.commit()
        with patch('app.services.video_ai_service.transcribe', return_value=[{'start': 0, 'end': 2, 'text': '变量'}]) as transcribe, patch('app.services.video_ai_service.deepseek', return_value='当前视频总结'):
            run_video_summary(video.id, 'one')
        assert transcribe.call_count == 1
        assert transcribe.call_args.args[0].id == video.id
        row = db.session.scalar(db.select(VideoAISummary).where(VideoAISummary.video_id == video.id))
        assert row.status == 'DRAFT' and row.progress == 100 and row.task_id is None
        assert db.session.scalar(db.select(VideoAISummary).where(VideoAISummary.video_id == other.id)) is None


def test_video_publication_unlocks_only_current_video(app, client):
    with app.app_context():
        teacher, student, course, video = seed()
        other = Video(chapter_id=video.chapter_id, title='其他视频', status='READY')
        db.session.add(other)
        db.session.add(VideoAISummary(video_id=video.id, status='DRAFT', content='草稿', source_hash=material(video)[1]))
        db.session.commit()
        url = f'/api/videos/{video.id}/ai-summary'
        assert client.put(url, headers=token(student), json={'content': '越权', 'publish': True}).status_code == 403
        assert client.put(url, headers=token(teacher), json={'content': '教师校对内容', 'publish': True}).status_code == 200
        assert client.get(url, headers=token(student)).get_json()['data']['content'] is None
        db.session.add(LearningRecord(student_id=student.id, video_id=video.id, status='COMPLETED', progress=100))
        db.session.commit()
        assert client.get(url, headers=token(student)).get_json()['data']['content'] == '教师校对内容'
        assert client.get(f'/api/videos/{other.id}/ai-summary', headers=token(student)).get_json()['data']['content'] is None
        other.title = '只改变其他视频'; db.session.commit()
        assert not summary_payload(video, student)['stale']
        video.description = '当前视频新资料'; db.session.commit()
        assert summary_payload(video, student)['content'] is None
        assert client.put(url, headers=token(teacher), json={'content': '旧总结', 'publish': True}).status_code == 409


def test_queue_uses_video_id_and_legacy_course_endpoint_is_disabled(app, client):
    with app.app_context():
        teacher, student, course, video = seed()
        app.config['DEEPSEEK_API_KEY'] = 'test-key'
        app.extensions['celery'] = SimpleNamespace()
        url = f'/api/videos/{video.id}/ai-summary/generate'
        with patch('app.tasks.video_tasks.generate_video_summary.apply_async') as queue:
            assert client.post(url, headers=token(teacher)).status_code == 202
            assert queue.call_args.kwargs['args'][0] == video.id
            assert client.post(url, headers=token(teacher)).status_code == 409
            assert queue.call_count == 1
            assert client.post(f'/api/courses/{course.id}/ai-summary/generate', headers=token(teacher)).status_code == 410
        row = db.session.scalar(db.select(VideoAISummary))
        with patch('app.services.video_ai_service.transcribe', side_effect=ValueError('源文件不存在')):
            run_video_summary(video.id, row.task_id)
        db.session.expire_all()
        assert row.status == 'FAILED' and row.task_id is None


def test_cancellation_during_transcription_cannot_publish_result(app, client):
    with app.app_context():
        teacher, student, course, video = seed()
        row = VideoAISummary(video_id=video.id, task_id='cancel', status='QUEUED')
        db.session.add(row); db.session.commit()
        def cancel_in_asr(selected, report):
            result = client.post(f'/api/videos/{video.id}/ai-summary/cancel', headers=token(teacher))
            assert result.status_code == 200
            report('SUBTITLING', 40, '检查取消')
            raise AssertionError('取消后不应继续运行')
        with patch('app.services.video_ai_service.transcribe', side_effect=cancel_in_asr), patch('app.services.video_ai_service.deepseek') as ai:
            run_video_summary(video.id, 'cancel')
            ai.assert_not_called()
        db.session.expire_all()
        assert row.status == 'CANCELLED' and row.content is None and row.task_id is None


def test_open_course_policy_applies_to_all_its_video_summaries(app, client):
    with app.app_context():
        teacher, student, course, video = seed()
        newcomer = User(username='new_student', real_name='未选课学生', role='STUDENT', student_no='AI03', password_hash='hash')
        db.session.add(newcomer)
        db.session.add(CourseAISummary(course_id=course.id, status='CANCELLED', open_to_students=True))
        row = VideoAISummary(video_id=video.id, status='DRAFT', content='待审核', source_hash=material(video)[1])
        db.session.add(row); db.session.commit()
        url = f'/api/videos/{video.id}/ai-summary'
        headers = token(newcomer)
        assert client.get(url).status_code == 401
        assert client.get(url, headers=headers).get_json()['data']['unlocked']
        assert client.get(url, headers=headers).get_json()['data']['content'] is None
        row.status = 'PUBLISHED'; db.session.commit()
        assert client.get(url, headers=headers).get_json()['data']['content'] == '待审核'
        course.status = 'OFFLINE'; db.session.commit()
        assert client.get(url, headers=headers).status_code == 404


def test_duplicate_delivery_and_cancelled_task_do_not_run_ai(app):
    with app.app_context():
        teacher, student, course, video = seed()
        row = VideoAISummary(video_id=video.id, task_id='old', status='CANCELLED')
        db.session.add(row); db.session.commit()
        with patch('app.services.video_ai_service.transcribe') as asr, patch('app.services.video_ai_service.deepseek') as ai:
            run_video_summary(video.id, 'old')
            row.status = 'SUMMARIZING'; row.task_id = 'new'; db.session.commit()
            run_video_summary(video.id, 'new')
            run_video_summary(video.id, 'old')
            asr.assert_not_called(); ai.assert_not_called()


def test_legacy_message_cannot_restart_course_generation(app):
    from app.tasks.video_tasks import generate_course_summary
    with app.app_context():
        teacher, student, course, video = seed()
        row = CourseAISummary(course_id=course.id, task_id='legacy', status='SUBTITLING', open_to_students=True)
        db.session.add(row); db.session.commit()
        generate_course_summary.run(course.id, 'legacy')
        db.session.expire_all()
        assert row.status == 'CANCELLED' and row.task_id is None and row.open_to_students


def test_subtitle_and_summary_cascade_delete(app, client):
    from app.models import VideoSubtitle
    with app.app_context():
        teacher, student, course, video = seed()
        video_id = video.id
        db.session.add(VideoSubtitle(video_id=video.id, source_hash='x'*64, segments=[{'start': 0, 'end': 2, 'text': '课程内容'}]))
        db.session.add(VideoAISummary(video_id=video.id, status='DRAFT', content='视频总结'))
        db.session.commit()
        assert client.get(f'/api/videos/{video_id}/subtitle').status_code == 401
        response = client.get(f'/api/videos/{video_id}/subtitle', headers=token(student))
        assert response.status_code == 200 and response.mimetype == 'text/vtt'
        db.session.delete(video); db.session.commit()
        assert db.session.scalar(db.select(VideoSubtitle)) is None
        assert db.session.scalar(db.select(VideoAISummary)) is None


def test_webvtt_escapes_markup_and_keeps_timing():
    output = webvtt([{'start': 1.234, 'end': 62.5, 'text': '<script> --> hello'}])
    assert '00:00:01.234 --> 00:01:02.500' in output
    assert '<script>' not in output

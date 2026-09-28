from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import io
import os
import re
import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import stamp, upgrade
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from werkzeug.datastructures import FileStorage

from app import create_app
from app.config import DevelopmentConfig, TestingConfig
from app.extensions import db
from app.models import (Course, CourseStudent, LearningProgressReceipt, LearningRecord, Notification,
    PasswordResetRequest, TeachingClass, TeachingClassCourse, TeachingClassJoinRequest, TeachingClassStudent, User, Video)
from app.services import class_service, password_reset_service, question_service
from app.services.auth_service import set_user_password
from app.services.learning_service import update_progress, LearningConflict
from app.services.review_guard import claim_pending
from app.services.video_processing_service import replace_video
from test_learning_questions import create_learning_context, login, bearer


def test_progress_receipts_repeat_exact_response_without_increment_and_reject_reuse(app, client):
    context = create_learning_context(app)
    token = login(client, context['student'])
    assert client.post(f"/api/learning/courses/{context['course_id']}/join", headers=bearer(token)).status_code == 201
    endpoint = f"/api/learning/videos/{context['video_id']}/progress"
    payload = {'current_time': 20, 'watch_duration_delta': 15, 'request_id': 'durable-request-1'}
    first = client.put(endpoint, headers=bearer(token), json=payload)
    assert first.status_code == 200
    assert client.put(endpoint, headers=bearer(token), json=payload).get_json()['data'] == first.get_json()['data']
    assert client.put(endpoint, headers=bearer(token), json={**payload, 'current_time': 50}).status_code == 409
    second = client.put(endpoint, headers=bearer(token), json={**payload, 'current_time': 50, 'request_id': 'durable-request-2'})
    assert second.get_json()['data']['watch_duration'] == 30
    # A late retry returns its original acknowledgement without rewinding current data.
    assert client.put(endpoint, headers=bearer(token), json=payload).get_json()['data'] == first.get_json()['data']
    assert client.get(endpoint, headers=bearer(token)).get_json()['data']['current_time'] == 50
    other_token = login(client, context['other_student'])
    assert client.put(endpoint, headers=bearer(other_token), json=payload).status_code == 403
    client.post(f"/api/learning/courses/{context['course_id']}/join", headers=bearer(other_token))
    assert client.put(endpoint, headers=bearer(other_token), json=payload).get_json()['data']['watch_duration'] == 15
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 3
        video = db.session.get(LearningRecord, first.get_json()['data']['id']).video
        db.session.delete(video)
        db.session.commit()
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 0


@pytest.mark.parametrize('request_id', ['', 'x' * 101, 123, 'bad id'])
def test_progress_request_id_validation(app, client, request_id):
    context = create_learning_context(app)
    token = login(client, context['student'])
    response = client.put(f"/api/learning/videos/{context['video_id']}/progress", headers=bearer(token),
        json={'current_time': 1, 'watch_duration_delta': 1, 'request_id': request_id})
    assert response.status_code == 400


@pytest.mark.parametrize('temporary_state', ['OFFLINE', 'PROCESSING', 'FAILED'])
def test_temporarily_unavailable_progress_retained_and_replayable(app, client, temporary_state):
    context = create_learning_context(app)
    token = login(client, context['student'])
    client.post(f"/api/learning/courses/{context['course_id']}/join", headers=bearer(token))
    endpoint = f"/api/learning/videos/{context['video_id']}/progress"
    payload = {'current_time': 20, 'watch_duration_delta': 15, 'request_id': 'waiting-request'}
    with app.app_context():
        if temporary_state == 'OFFLINE':
            db.session.get(Course, context['course_id']).status = 'OFFLINE'
        else:
            db.session.get(Video, context['video_id']).status = temporary_state
        db.session.commit()
    assert client.put(endpoint, headers=bearer(token), json=payload).status_code == 423
    # Existing read endpoints preserve their unavailable/not-found contract.
    assert client.get(endpoint, headers=bearer(token)).status_code == 404
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 0
        db.session.get(Course, context['course_id']).status = 'PUBLISHED'
        db.session.get(Video, context['video_id']).status = 'READY'
        db.session.commit()
    first = client.put(endpoint, headers=bearer(token), json=payload)
    assert first.status_code == 200
    assert first.get_json()['data']['watch_duration'] == 15
    assert client.put(endpoint, headers=bearer(token), json=payload).get_json()['data'] == first.get_json()['data']


def test_replaced_video_old_offline_progress_cannot_credit_new_content(app, client):
    context = create_learning_context(app)
    token = login(client, context['student'])
    client.post(f"/api/learning/courses/{context['course_id']}/join", headers=bearer(token))
    old_endpoint = f"/api/learning/videos/{context['video_id']}/progress"
    payload = {'current_time': 20, 'watch_duration_delta': 15, 'request_id': 'old-media-request'}
    assert client.put(old_endpoint, headers=bearer(token), json=payload).status_code == 200
    with app.app_context():
        course = db.session.get(Course, context['course_id'])
        course.status = 'OFFLINE'
        db.session.commit()
        replacement = replace_video(FileStorage(stream=io.BytesIO(b'new-video'), filename='new.mp4'),
            context['video_id'], course.teacher_id, {'title': '替换后的新内容'})
        new_id = replacement.id
        assert new_id != context['video_id']
        replacement.status = 'READY'
        replacement.duration = 100
        course.status = 'PUBLISHED'
        db.session.commit()
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 0
    assert client.put(old_endpoint, headers=bearer(token), json=payload).status_code == 404
    assert client.put(old_endpoint, headers=bearer(token), json={**payload, 'request_id': 'unsent-old-request'}).status_code == 404
    current = client.get(f'/api/learning/videos/{new_id}/progress', headers=bearer(token))
    assert current.status_code == 200
    assert current.get_json()['data']['watch_duration'] == 0
    assert current.get_json()['data']['progress'] == 0


@pytest.fixture
def file_app(tmp_path, monkeypatch):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{(tmp_path / 'race.db').as_posix()}")
    monkeypatch.setattr(TestingConfig, 'MEDIA_ROOT', tmp_path / 'media')
    application = create_app('testing')
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize('editing', [False, True])
def test_concurrent_question_answer_or_edit_cannot_reopen_closed_question(file_app, monkeypatch, editing):
    from app.models import Question, Answer
    context = create_learning_context(file_app)
    with file_app.app_context():
        student = db.session.scalar(db.select(User).where(User.username == context['student']))
        teacher = db.session.scalar(db.select(User).where(User.username == context['teacher']))
        question = Question(student_id=student.id, video_id=context['video_id'], title='并发关闭', content='内容', status='WAITING')
        db.session.add(question)
        db.session.commit()
        question_id, student_id, teacher_id = question.id, student.id, teacher.id
        if editing:
            question_service.answer_question(question_id, teacher_id, '原回答')
        initial_notifications = db.session.scalar(db.select(db.func.count(Notification.id)))
    barrier = Barrier(2)
    original = question_service._claim_open_question
    def synchronized_claim(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(question_service, '_claim_open_question', synchronized_claim)
    def mutate(action):
        with file_app.app_context():
            try:
                if action == 'close':
                    question_service.close_question(question_id, student_id, 'STUDENT')
                else:
                    method = question_service.update_answer if editing else question_service.answer_question
                    method(question_id, teacher_id, '新回答')
                return 'ok'
            except question_service.QuestionConflict:
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(mutate, ['answer', 'close']))
    assert results[1] == 'ok'
    with file_app.app_context():
        question = db.session.get(Question, question_id)
        assert question.status == 'CLOSED'
        expected = initial_notifications + (1 if results[0] == 'ok' else 0)
        assert db.session.scalar(db.select(db.func.count(Notification.id))) == expected
        if results[0] == 'conflict':
            assert (question.answer.content if question.answer else None) == ('原回答' if editing else None)


def prepare_requests(application):
    context = create_learning_context(application)
    with application.app_context():
        student = db.session.scalar(db.select(User).where(User.username == context['student']))
        teacher = db.session.scalar(db.select(User).where(User.username == context['teacher']))
        classroom = TeachingClass(teacher_id=teacher.id, name='并发审批班')
        db.session.add(classroom)
        db.session.flush()
        db.session.add(TeachingClassCourse(class_id=classroom.id, course_id=context['course_id']))
        join = TeachingClassJoinRequest(class_id=classroom.id, student_id=student.id, status='PENDING')
        db.session.add(join)
        db.session.commit()
        return context, student.id, teacher.id, classroom.id, join.id


@pytest.mark.parametrize('actions', [('APPROVED', 'APPROVED'), ('APPROVED', 'REJECTED'), ('APPROVED', 'CANCELLED')])
def test_concurrent_join_review_or_withdraw_only_one_transition(file_app, monkeypatch, actions):
    _, student_id, teacher_id, class_id, request_id = prepare_requests(file_app)
    barrier = Barrier(2)
    def synchronized_claim(*args, **kwargs):
        barrier.wait(timeout=10)
        return claim_pending(*args, **kwargs)
    monkeypatch.setattr(class_service, 'claim_pending', synchronized_claim)
    def review(action):
        with file_app.app_context():
            try:
                if action == 'CANCELLED':
                    return class_service.cancel_class_join_request(request_id, student_id)['status']
                return class_service.review_class_join_request(request_id, teacher_id, action)['status']
            except class_service.ClassConflict:
                return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review, actions))
    assert results.count('CONFLICT') == 1
    with file_app.app_context():
        final = db.session.get(TeachingClassJoinRequest, request_id)
        assert final.status in actions
        count = db.session.scalar(db.select(db.func.count(TeachingClassStudent.id)).where(TeachingClassStudent.class_id == class_id))
        assert count == (1 if final.status == 'APPROVED' else 0)
        assert db.session.scalar(db.select(db.func.count(Notification.id))) == 1


def test_pending_password_cannot_be_replaced_and_admin_reset_cancels_old_review(file_app):
    _, student_id, teacher_id, class_id, _ = prepare_requests(file_app)
    with file_app.app_context():
        db.session.add(TeachingClassStudent(class_id=class_id, student_id=student_id))
        db.session.commit()
        student = db.session.get(User, student_id)
        request = password_reset_service.submit_student_password_reset(student, 'FirstNew123!')
        request_id, original_hash = request.id, request.requested_password_hash
        with pytest.raises(password_reset_service.PasswordResetRequestConflict):
            password_reset_service.submit_student_password_reset(student, 'Different123!')
        db.session.rollback()
        assert db.session.get(PasswordResetRequest, request_id).requested_password_hash == original_hash
        set_user_password(student_id, 'AdminNew123!', teacher_id)
        with pytest.raises(password_reset_service.PasswordResetRequestConflict):
            password_reset_service.review_student_password_reset(request_id, teacher_id, 'APPROVED')
        db.session.rollback()
        from werkzeug.security import check_password_hash
        assert check_password_hash(db.session.get(User, student_id).password_hash, 'AdminNew123!')


def test_password_approval_cancels_legacy_duplicate_pending_request(file_app):
    _, student_id, teacher_id, class_id, _ = prepare_requests(file_app)
    with file_app.app_context():
        db.session.add(TeachingClassStudent(class_id=class_id, student_id=student_id))
        db.session.commit()
        request = password_reset_service.submit_student_password_reset(db.session.get(User, student_id), 'Approved123!')
        duplicate = PasswordResetRequest(student_id=student_id, requested_password_hash=request.requested_password_hash,
            expires_at=request.expires_at, status='PENDING')
        db.session.add(duplicate)
        db.session.commit()
        request_id, duplicate_id = request.id, duplicate.id
        password_reset_service.review_student_password_reset(request_id, teacher_id, 'APPROVED')
        assert db.session.get(PasswordResetRequest, duplicate_id).status == 'CANCELLED'
        with pytest.raises(password_reset_service.PasswordResetRequestConflict):
            password_reset_service.review_student_password_reset(duplicate_id, teacher_id, 'APPROVED')
        db.session.rollback()


def test_concurrent_password_approval_has_one_password_write_and_result_notification(file_app, monkeypatch):
    _, student_id, teacher_id, class_id, _ = prepare_requests(file_app)
    with file_app.app_context():
        db.session.add(TeachingClassStudent(class_id=class_id, student_id=student_id))
        db.session.commit()
        request_id = password_reset_service.submit_student_password_reset(db.session.get(User, student_id), 'Approved123!').id
    barrier = Barrier(2)
    def synchronized_claim(*args, **kwargs):
        barrier.wait(timeout=10)
        return claim_pending(*args, **kwargs)
    monkeypatch.setattr(password_reset_service, 'claim_pending', synchronized_claim)
    def review(action):
        with file_app.app_context():
            try:
                return password_reset_service.review_student_password_reset(request_id, teacher_id, action)['status']
            except password_reset_service.PasswordResetRequestConflict:
                return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review, ['APPROVED', 'REJECTED']))
    assert results.count('CONFLICT') == 1
    with file_app.app_context():
        assert db.session.scalar(db.select(db.func.count(Notification.id)).where(Notification.recipient_id == student_id)) == 1


def test_receipt_migration_preserves_legacy_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    monkeypatch.setattr(TestingConfig, 'MEDIA_ROOT', tmp_path / 'media')
    application = create_app('testing')
    directory = str(Path(__file__).resolve().parents[1] / 'migrations')
    with application.app_context():
        # Existing early migrations use MySQL BIGINT identity definitions. Build
        # the equivalent previous metadata on SQLite rather than testing those.
        db.create_all()
        LearningProgressReceipt.__table__.drop(db.engine)
        stamp(directory=directory, revision='e5f6a7b8c9d0')
    context = create_learning_context(application)
    with application.app_context():
        student_id = db.session.scalar(db.select(User.id).where(User.username == context['student']))
        db.session.add(CourseStudent(course_id=context['course_id'], student_id=student_id, status=True))
        update_progress(student_id, context['video_id'], 25, 20)
        upgrade(directory=directory)
        record = db.session.scalar(db.select(LearningRecord))
        assert record.watch_duration == 20
        first = update_progress(student_id, context['video_id'], 50, 10, 'migration-retry')
        assert update_progress(student_id, context['video_id'], 50, 10, 'migration-retry') == first
        assert db.session.scalar(db.select(LearningRecord)).watch_duration == 30
        with db.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
        db.session.remove()
        db.engine.dispose()


def test_two_clients_replaying_same_progress_leave_one_committed_increment(file_app):
    context = create_learning_context(file_app)
    with file_app.app_context():
        student_id = db.session.scalar(db.select(User.id).where(User.username == context['student']))
        db.session.add(CourseStudent(course_id=context['course_id'], student_id=student_id, status=True))
        db.session.commit()
    barrier = Barrier(2)
    def replay(_):
        with file_app.app_context():
            barrier.wait(timeout=10)
            try:
                return update_progress(student_id, context['video_id'], 20, 10, 'same-concurrent-request')
            except LearningConflict:
                return 'RETRY'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(replay, range(2)))
    assert any(isinstance(result, dict) for result in results)
    with file_app.app_context():
        assert update_progress(student_id, context['video_id'], 20, 10, 'same-concurrent-request')['watch_duration'] == 10
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 1


@pytest.fixture
def mysql_app(tmp_path, monkeypatch):
    if os.getenv('RUN_MYSQL_TEST') != '1':
        pytest.skip('显式启用后才创建隔离MySQL测试库，不连接真实业务表')
    source = make_url(DevelopmentConfig.SQLALCHEMY_DATABASE_URI)
    name = 'bs_hfn_regression_' + uuid.uuid4().hex
    assert source.get_backend_name() == 'mysql'
    assert re.fullmatch(r'bs_hfn_regression_[a-f0-9]{32}', name) and name != source.database
    admin_engine = create_engine(source.set(database=None))
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    application = None
    try:
        monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', source.set(database=name).render_as_string(hide_password=False))
        monkeypatch.setattr(TestingConfig, 'MEDIA_ROOT', tmp_path / 'mysql-media')
        application = create_app('testing')
        with application.app_context():
            db.create_all()
        yield application
    finally:
        if application:
            with application.app_context():
                db.session.remove()
                db.engine.dispose()
        # Target is an explicitly validated, newly-created disposable schema.
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE `{name}`'))
        admin_engine.dispose()


def test_mysql_concurrent_distinct_and_duplicate_progress_are_serialized(mysql_app):
    context = create_learning_context(mysql_app)
    with mysql_app.app_context():
        student_id = db.session.scalar(db.select(User.id).where(User.username == context['student']))
        db.session.add(CourseStudent(course_id=context['course_id'], student_id=student_id, status=True))
        db.session.commit()
    barrier = Barrier(4)
    def replay(index):
        with mysql_app.app_context():
            barrier.wait(timeout=10)
            # Two identical retries plus two independent deltas, first row absent.
            return update_progress(student_id, context['video_id'], 20, 10, f'mysql-request-{index % 3}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(replay, range(4)))
    assert len(results) == 4
    with mysql_app.app_context():
        assert db.session.scalar(db.select(LearningRecord)).watch_duration == 30
        assert db.session.scalar(db.select(db.func.count(LearningProgressReceipt.id))) == 3


def test_mysql_password_review_racing_admin_reset_keeps_latest_admin_password(mysql_app):
    _, student_id, teacher_id, class_id, _ = prepare_requests(mysql_app)
    with mysql_app.app_context():
        db.session.add(TeachingClassStudent(class_id=class_id, student_id=student_id))
        db.session.commit()
        request_id = password_reset_service.submit_student_password_reset(db.session.get(User, student_id), 'Approved123!').id
    barrier = Barrier(2)
    def race(action):
        with mysql_app.app_context():
            barrier.wait(timeout=10)
            if action == 'ADMIN':
                set_user_password(student_id, 'FinalAdmin123!', teacher_id)
                return 'ADMIN'
            try:
                return password_reset_service.review_student_password_reset(request_id, teacher_id, 'APPROVED')['status']
            except password_reset_service.PasswordResetRequestConflict:
                return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert 'ADMIN' in list(pool.map(race, ['APPROVE', 'ADMIN']))
    with mysql_app.app_context():
        from werkzeug.security import check_password_hash
        assert check_password_hash(db.session.get(User, student_id).password_hash, 'FinalAdmin123!')
        assert db.session.get(PasswordResetRequest, request_id).status in ('CANCELLED', 'APPROVED')

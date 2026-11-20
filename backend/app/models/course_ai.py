from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class VideoSubtitle(IdMixin, TimestampMixin, db.Model):
    __tablename__ = 'video_subtitle'
    video_id = db.Column(BIGINT_UNSIGNED, db.ForeignKey('video.id', ondelete='CASCADE'), unique=True, nullable=False)
    source_hash = db.Column(db.String(64), nullable=False)
    segments = db.Column(db.JSON, nullable=False)
    language = db.Column(db.String(30))
    video = db.relationship('Video', backref=db.backref('subtitle', uselist=False, cascade='all, delete-orphan'))


class CourseAISummary(IdMixin, TimestampMixin, db.Model):
    __tablename__ = 'course_ai_summary'
    course_id = db.Column(BIGINT_UNSIGNED, db.ForeignKey('course.id', ondelete='CASCADE'), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='DRAFT')
    task_id = db.Column(db.String(50))
    content = db.Column(db.Text)
    source_hash = db.Column(db.String(64))
    error_message = db.Column(db.String(500))
    open_to_students = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    course = db.relationship('Course', backref=db.backref('ai_summary', uselist=False, cascade='all, delete-orphan'))


class VideoAISummary(IdMixin, TimestampMixin, db.Model):
    __tablename__ = 'video_ai_summary'
    video_id = db.Column(BIGINT_UNSIGNED, db.ForeignKey('video.id', ondelete='CASCADE'), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='DRAFT')
    task_id = db.Column(db.String(50))
    content = db.Column(db.Text)
    source_hash = db.Column(db.String(64))
    error_message = db.Column(db.String(500))
    progress = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    progress_message = db.Column(db.String(200))
    video = db.relationship('Video', backref=db.backref('ai_summary', uselist=False, cascade='all, delete-orphan'))

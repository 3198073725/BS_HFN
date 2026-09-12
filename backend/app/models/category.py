from app.extensions import db
from .base import IdMixin, TimestampMixin


class CourseCategory(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "course_category"
    __table_args__ = (db.Index("idx_category_status_sort", "status", "sort_order"),)

    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    status = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

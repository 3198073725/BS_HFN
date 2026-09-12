from app.extensions import db
from app.datetime_utils import iso_utc
from .base import IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "sys_user"
    __table_args__ = (
        db.Index("idx_user_role", "role"),
        db.Index("idx_user_status", "status"),
    )

    username = db.Column(db.String(50), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    real_name = db.Column(db.String(50), nullable=False)
    student_no = db.Column(db.String(50), unique=True)
    teacher_no = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20))
    avatar = db.Column(db.String(255))
    bio = db.Column(db.String(500))
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    last_login_at = db.Column(db.DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "real_name": self.real_name,
            "student_no": self.student_no,
            "teacher_no": self.teacher_no,
            "email": self.email,
            "phone": self.phone,
            "avatar": self.avatar,
            "avatar_url": f"/media/{self.avatar}" if self.avatar else None,
            "bio": self.bio,
            "role": self.role,
            "status": bool(self.status),
            "last_login_at": iso_utc(self.last_login_at),
            "created_at": iso_utc(self.created_at),
        }

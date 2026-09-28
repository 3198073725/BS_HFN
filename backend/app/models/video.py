from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Video(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "video"
    __table_args__ = (
        db.Index("idx_video_chapter_sort", "chapter_id", "sort_order"),
        db.Index("idx_video_status", "status"),
        db.Index("idx_video_process", "status", "process_step"),
    )

    chapter_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("chapter.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(500))
    original_name = db.Column(db.String(255))
    original_file = db.Column(db.String(500))
    processed_file = db.Column(db.String(500))
    hls_path = db.Column(db.String(500))
    cover = db.Column(db.String(500))
    duration = db.Column(db.Numeric(10, 3))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    video_codec = db.Column(db.String(50))
    audio_codec = db.Column(db.String(50))
    bitrate = db.Column(db.BigInteger)
    frame_rate = db.Column(db.Numeric(8, 3))
    file_size = db.Column(db.BigInteger)
    status = db.Column(db.String(20), nullable=False, default="PENDING", server_default="PENDING")
    process_step = db.Column(db.String(30))
    task_id = db.Column(db.String(50), index=True)
    error_message = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    chapter = db.relationship("Chapter", backref=db.backref("videos", cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chapter_id": self.chapter_id,
            "title": self.title,
            "description": self.description,
            "original_name": self.original_name,
            "hls_url": f"/media/{self.hls_path}" if self.hls_path else None,
            "cover_url": f"/media/{self.cover}" if self.cover else None,
            "duration": float(self.duration) if self.duration is not None else None,
            "width": self.width,
            "height": self.height,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "bitrate": self.bitrate,
            "frame_rate": float(self.frame_rate) if self.frame_rate is not None else None,
            "file_size": self.file_size,
            "status": self.status,
            "process_step": self.process_step,
            "error_message": self.error_message,
            "sort_order": self.sort_order,
        }

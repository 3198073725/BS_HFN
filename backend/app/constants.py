from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class CourseStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    OFFLINE = "OFFLINE"


class VideoStatus(StrEnum):
    UPLOADING = "UPLOADING"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class LearningStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    LEARNING = "LEARNING"
    COMPLETED = "COMPLETED"


class QuestionStatus(StrEnum):
    WAITING = "WAITING"
    ANSWERED = "ANSWERED"
    CLOSED = "CLOSED"


class PublishStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"

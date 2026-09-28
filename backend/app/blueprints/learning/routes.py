from flask_jwt_extended import get_jwt_identity

from app.constants import UserRole
from app.services.learning_service import (
    LearningConflict,
    LearningNotFound,
    LearningPermissionDenied,
    LearningUnavailable,
    add_favorite,
    create_note,
    delete_note,
    get_progress,
    join_course,
    leave_course,
    list_favorites,
    list_joined_courses,
    list_notes,
    remove_favorite,
    serialize_course_state,
    update_note,
    update_progress,
)
from app.utils import error, json_body, roles_required, success
from . import learning_bp
from .schemas import ValidationError, validate_note, validate_progress


@learning_bp.get("/courses")
@roles_required(UserRole.STUDENT)
def joined_courses():
    return success(list_joined_courses(_student_id()))


@learning_bp.get("/favorites")
@roles_required(UserRole.STUDENT)
def favorites():
    return success(list_favorites(_student_id()))


@learning_bp.get("/courses/<int:course_id>/state")
@roles_required(UserRole.STUDENT)
def course_state(course_id: int):
    return _handle(lambda: success(serialize_course_state(_student_id(), course_id)))


@learning_bp.post("/courses/<int:course_id>/join")
@roles_required(UserRole.STUDENT)
def add_course(course_id: int):
    return _handle(lambda: success(join_course(_student_id(), course_id), "课程加入成功", 201))


@learning_bp.delete("/courses/<int:course_id>/join")
@roles_required(UserRole.STUDENT)
def remove_course(course_id: int):
    def action():
        leave_course(_student_id(), course_id)
        return success(message="已退出课程")

    return _handle(action)


@learning_bp.post("/courses/<int:course_id>/favorite")
@roles_required(UserRole.STUDENT)
def favorite_course(course_id: int):
    return _handle(lambda: success(add_favorite(_student_id(), course_id), "课程收藏成功", 201))


@learning_bp.delete("/courses/<int:course_id>/favorite")
@roles_required(UserRole.STUDENT)
def unfavorite_course(course_id: int):
    def action():
        remove_favorite(_student_id(), course_id)
        return success(message="已取消收藏")

    return _handle(action)


@learning_bp.get("/videos/<int:video_id>/progress")
@roles_required(UserRole.STUDENT)
def video_progress(video_id: int):
    return _handle(lambda: success(get_progress(_student_id(), video_id)))


@learning_bp.put("/videos/<int:video_id>/progress")
@roles_required(UserRole.STUDENT)
def save_video_progress(video_id: int):
    try:
        data = validate_progress(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(
            update_progress(_student_id(), video_id, data["current_time"], data["watch_delta"], data["request_id"]),
            "学习进度已保存",
        )
    )


@learning_bp.get("/videos/<int:video_id>/notes")
@roles_required(UserRole.STUDENT)
def video_notes(video_id: int):
    return _handle(lambda: success(list_notes(_student_id(), video_id)))


@learning_bp.post("/videos/<int:video_id>/notes")
@roles_required(UserRole.STUDENT)
def add_video_note(video_id: int):
    try:
        data = validate_note(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(
            create_note(_student_id(), video_id, data["video_time"], data["content"]),
            "笔记创建成功",
            201,
        )
    )


@learning_bp.put("/notes/<int:note_id>")
@roles_required(UserRole.STUDENT)
def edit_video_note(note_id: int):
    try:
        data = validate_note(json_body(), partial=True)
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(update_note(_student_id(), note_id, data), "笔记更新成功"))


@learning_bp.delete("/notes/<int:note_id>")
@roles_required(UserRole.STUDENT)
def remove_video_note(note_id: int):
    def action():
        delete_note(_student_id(), note_id)
        return success(message="笔记删除成功")

    return _handle(action)


def _student_id() -> int:
    return int(get_jwt_identity())


def _handle(action):
    try:
        return action()
    except LearningUnavailable as exc:
        return error(str(exc), 423)
    except LearningNotFound as exc:
        return error(str(exc), 404)
    except LearningPermissionDenied as exc:
        return error(str(exc), 403)
    except LearningConflict as exc:
        return error(str(exc), 409)
    except ValueError as exc:
        return error(str(exc), 400)

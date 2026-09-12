from flask_jwt_extended import get_jwt_identity

from app.constants import PublishStatus, UserRole
from app.extensions import db
from app.models import User
from app.services.exam_service import (
    ExamConflict,
    ExamNotFound,
    ExamPermissionDenied,
    add_question,
    change_exam_status,
    create_exam,
    delete_draft_exam,
    delete_question,
    get_visible_exam,
    get_visible_record,
    list_exam_records,
    list_student_exams,
    list_teacher_exams,
    save_exam_answers,
    start_exam,
    submit_exam,
    update_exam,
    update_question,
)
from app.utils import error, json_body, roles_required, success
from . import exams_bp
from .schemas import ValidationError, validate_answers, validate_exam, validate_question


@exams_bp.get("")
@roles_required(UserRole.STUDENT)
def student_exams():
    return success(list_student_exams(_user_id()))


@exams_bp.get("/manage")
@roles_required(UserRole.TEACHER)
def teacher_exams():
    return success(list_teacher_exams(_user_id()))


@exams_bp.post("")
@roles_required(UserRole.TEACHER)
def add_exam():
    try:
        data = validate_exam(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(create_exam(_user_id(), data), "测验创建成功", 201))


@exams_bp.get("/<int:exam_id>")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def exam_detail(exam_id: int):
    return _handle(lambda: success(get_visible_exam(exam_id, _user_id(), _current_role())))


@exams_bp.put("/<int:exam_id>")
@roles_required(UserRole.TEACHER)
def edit_exam(exam_id: int):
    try:
        data = validate_exam(json_body(), partial=True)
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(update_exam(exam_id, _user_id(), data), "测验更新成功"))


@exams_bp.delete("/<int:exam_id>")
@roles_required(UserRole.TEACHER)
def remove_exam(exam_id: int):
    return _handle(lambda: _delete_exam_response(exam_id))


@exams_bp.post("/<int:exam_id>/questions")
@roles_required(UserRole.TEACHER)
def add_exam_question(exam_id: int):
    try:
        data = validate_question(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(add_question(exam_id, _user_id(), data), "试题添加成功", 201))


@exams_bp.put("/questions/<int:question_id>")
@roles_required(UserRole.TEACHER)
def edit_exam_question(question_id: int):
    try:
        data = validate_question(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(update_question(question_id, _user_id(), data), "试题更新成功"))


@exams_bp.delete("/questions/<int:question_id>")
@roles_required(UserRole.TEACHER)
def remove_exam_question(question_id: int):
    return _handle(lambda: _delete_question_response(question_id))


@exams_bp.post("/<int:exam_id>/publish")
@roles_required(UserRole.TEACHER)
def publish_exam(exam_id: int):
    return _handle(
        lambda: success(
            change_exam_status(exam_id, _user_id(), PublishStatus.PUBLISHED),
            "测验发布成功",
        )
    )


@exams_bp.post("/<int:exam_id>/close")
@roles_required(UserRole.TEACHER)
def close_exam(exam_id: int):
    return _handle(
        lambda: success(
            change_exam_status(exam_id, _user_id(), PublishStatus.CLOSED),
            "测验已关闭",
        )
    )


@exams_bp.post("/<int:exam_id>/start")
@roles_required(UserRole.STUDENT)
def begin_exam(exam_id: int):
    return _handle(lambda: success(start_exam(exam_id, _user_id()), "测验已开始", 201))


@exams_bp.post("/<int:exam_id>/submit")
@roles_required(UserRole.STUDENT)
def finish_exam(exam_id: int):
    try:
        answers = validate_answers(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(submit_exam(exam_id, _user_id(), answers), "测验提交成功"))


@exams_bp.put("/<int:exam_id>/answers")
@roles_required(UserRole.STUDENT)
def save_answers(exam_id: int):
    try:
        answers = validate_answers(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(save_exam_answers(exam_id, _user_id(), answers), "答案已保存"))


@exams_bp.get("/<int:exam_id>/records")
@roles_required(UserRole.TEACHER)
def exam_records(exam_id: int):
    return _handle(lambda: success(list_exam_records(exam_id, _user_id())))


@exams_bp.get("/records/<int:record_id>")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def exam_record_detail(record_id: int):
    return _handle(
        lambda: success(get_visible_record(record_id, _user_id(), _current_role()))
    )


def _delete_question_response(question_id: int):
    delete_question(question_id, _user_id())
    return success(message="试题删除成功")


def _delete_exam_response(exam_id: int):
    delete_draft_exam(exam_id, _user_id())
    return success(message="测验草稿删除成功")


def _user_id() -> int:
    return int(get_jwt_identity())


def _current_role() -> str:
    return db.session.get(User, _user_id()).role


def _handle(action):
    try:
        return action()
    except ExamNotFound as exc:
        return error(str(exc), 404)
    except ExamPermissionDenied as exc:
        return error(str(exc), 403)
    except ExamConflict as exc:
        return error(str(exc), 409)

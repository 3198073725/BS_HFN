from flask import request, send_file
from flask_jwt_extended import get_jwt_identity

from app.constants import PublishStatus, UserRole
from app.extensions import db
from app.models import User
from app.services.homework_service import (
    HomeworkConflict,
    HomeworkNotFound,
    HomeworkPermissionDenied,
    attach_homework_file,
    attach_submission_file,
    change_homework_status,
    create_homework,
    delete_draft_homework,
    get_visible_homework,
    get_homework_attachment_path,
    get_submission_attachment_path,
    grade_submission,
    list_student_homeworks,
    list_submissions,
    list_teacher_homeworks,
    submit_homework,
    update_homework,
)
from app.utils import error, json_body, roles_required, success
from . import homework_bp
from .schemas import ValidationError, validate_grade, validate_homework, validate_submission


@homework_bp.get("")
@roles_required(UserRole.STUDENT)
def student_homeworks():
    return success(list_student_homeworks(_user_id()))


@homework_bp.get("/manage")
@roles_required(UserRole.TEACHER)
def teacher_homeworks():
    return success(list_teacher_homeworks(_user_id()))


@homework_bp.post("")
@roles_required(UserRole.TEACHER)
def add_homework():
    try:
        data = validate_homework(json_body())
        homework = create_homework(_user_id(), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except HomeworkNotFound as exc:
        return error(str(exc), 404)
    except HomeworkPermissionDenied as exc:
        return error(str(exc), 403)
    except HomeworkConflict as exc:
        return error(str(exc), 409)
    return success(homework, "作业创建成功", 201)


@homework_bp.get("/<int:homework_id>")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def homework_detail(homework_id: int):
    return _handle(
        lambda: success(get_visible_homework(homework_id, _user_id(), _current_role()))
    )


@homework_bp.get("/<int:homework_id>/attachment")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def view_homework_attachment(homework_id: int):
    return _handle(
        lambda: send_file(
            get_homework_attachment_path(homework_id, _user_id(), _current_role()),
            as_attachment=request.args.get("download") == "1",
        )
    )


@homework_bp.get("/submissions/<int:submission_id>/attachment")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def view_submission_attachment(submission_id: int):
    return _handle(
        lambda: send_file(
            get_submission_attachment_path(submission_id, _user_id(), _current_role()),
            as_attachment=request.args.get("download") == "1",
        )
    )


@homework_bp.put("/<int:homework_id>")
@roles_required(UserRole.TEACHER)
def edit_homework(homework_id: int):
    try:
        data = validate_homework(json_body(), partial=True)
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(update_homework(homework_id, _user_id(), data), "作业更新成功")
    )


@homework_bp.delete("/<int:homework_id>")
@roles_required(UserRole.TEACHER)
def remove_homework(homework_id: int):
    return _handle(lambda: _delete_homework_response(homework_id))


@homework_bp.post("/<int:homework_id>/attachment")
@roles_required(UserRole.TEACHER)
def upload_homework_attachment(homework_id: int):
    attachment = request.files.get("attachment")
    if attachment is None:
        return error("请选择附件文件", 400)
    try:
        return _handle(
            lambda: success(
                attach_homework_file(homework_id, _user_id(), attachment),
                "作业附件上传成功",
            )
        )
    except ValueError as exc:
        return error(str(exc), 400)


@homework_bp.post("/<int:homework_id>/publish")
@roles_required(UserRole.TEACHER)
def publish_homework(homework_id: int):
    return _handle(
        lambda: success(
            change_homework_status(homework_id, _user_id(), PublishStatus.PUBLISHED),
            "作业发布成功",
        )
    )


@homework_bp.post("/<int:homework_id>/close")
@roles_required(UserRole.TEACHER)
def close_homework(homework_id: int):
    return _handle(
        lambda: success(
            change_homework_status(homework_id, _user_id(), PublishStatus.CLOSED),
            "作业已关闭",
        )
    )


@homework_bp.put("/<int:homework_id>/submission")
@roles_required(UserRole.STUDENT)
def save_submission(homework_id: int):
    try:
        content = validate_submission(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(submit_homework(homework_id, _user_id(), content), "作业提交成功")
    )


@homework_bp.post("/<int:homework_id>/submission/attachment")
@roles_required(UserRole.STUDENT)
def upload_submission_attachment(homework_id: int):
    attachment = request.files.get("attachment")
    if attachment is None:
        return error("请选择附件文件", 400)
    try:
        return _handle(
            lambda: success(
                attach_submission_file(homework_id, _user_id(), attachment),
                "提交附件上传成功",
            )
        )
    except ValueError as exc:
        return error(str(exc), 400)


@homework_bp.get("/<int:homework_id>/submissions")
@roles_required(UserRole.TEACHER)
def homework_submissions(homework_id: int):
    return _handle(lambda: success(list_submissions(homework_id, _user_id())))


@homework_bp.put("/submissions/<int:submission_id>/grade")
@roles_required(UserRole.TEACHER)
def grade_homework(submission_id: int):
    try:
        score, comment = validate_grade(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(
            grade_submission(submission_id, _user_id(), score, comment),
            "批改完成",
        )
    )


def _user_id() -> int:
    return int(get_jwt_identity())


def _delete_homework_response(homework_id: int):
    delete_draft_homework(homework_id, _user_id())
    return success(message="作业删除成功")


def _current_role() -> str:
    return db.session.get(User, _user_id()).role


def _handle(action):
    try:
        return action()
    except HomeworkNotFound as exc:
        return error(str(exc), 404)
    except HomeworkPermissionDenied as exc:
        return error(str(exc), 403)
    except HomeworkConflict as exc:
        return error(str(exc), 409)

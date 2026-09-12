from flask import request
from flask_jwt_extended import get_jwt_identity

from app.constants import UserRole
from app.extensions import db
from app.models import User
from app.services.learning_service import LearningNotFound, LearningPermissionDenied
from app.services.question_service import (
    QuestionConflict,
    QuestionNotFound,
    QuestionPermissionDenied,
    answer_question,
    close_question,
    create_question,
    get_visible_question,
    list_questions,
    update_answer,
)
from app.utils import error, json_body, roles_required, success
from . import questions_bp
from .schemas import ValidationError, validate_answer, validate_filters, validate_question


@questions_bp.get("")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def question_list():
    try:
        status, video_id = validate_filters(request.args)
        data = list_questions(_user_id(), _current_role(), status, video_id)
    except ValidationError as exc:
        return error(str(exc), 400)
    except QuestionPermissionDenied as exc:
        return error(str(exc), 403)
    return success(data)


@questions_bp.post("")
@roles_required(UserRole.STUDENT)
def add_question():
    try:
        data = validate_question(json_body())
        question = create_question(_user_id(), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except LearningNotFound as exc:
        return error(str(exc), 404)
    except LearningPermissionDenied as exc:
        return error(str(exc), 403)
    except ValueError as exc:
        return error(str(exc), 400)
    return success(question, "问题提交成功", 201)


@questions_bp.get("/<int:question_id>")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def question_detail(question_id: int):
    return _handle(
        lambda: success(get_visible_question(question_id, _user_id(), _current_role()))
    )


@questions_bp.post("/<int:question_id>/answer")
@roles_required(UserRole.TEACHER)
def add_answer(question_id: int):
    try:
        content = validate_answer(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(
        lambda: success(answer_question(question_id, _user_id(), content), "回答提交成功", 201)
    )


@questions_bp.put("/<int:question_id>/answer")
@roles_required(UserRole.TEACHER)
def edit_answer(question_id: int):
    try:
        content = validate_answer(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(update_answer(question_id, _user_id(), content), "回答更新成功"))


@questions_bp.post("/<int:question_id>/close")
@roles_required(UserRole.STUDENT, UserRole.TEACHER)
def close(question_id: int):
    return _handle(
        lambda: success(close_question(question_id, _user_id(), _current_role()), "问题已关闭")
    )


def _user_id() -> int:
    return int(get_jwt_identity())


def _current_role() -> str:
    return db.session.get(User, _user_id()).role


def _handle(action):
    try:
        return action()
    except QuestionNotFound as exc:
        return error(str(exc), 404)
    except QuestionPermissionDenied as exc:
        return error(str(exc), 403)
    except QuestionConflict as exc:
        return error(str(exc), 409)

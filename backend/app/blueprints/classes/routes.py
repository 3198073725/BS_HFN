from flask_jwt_extended import get_jwt, get_jwt_identity

from app.constants import UserRole
from app.services.class_service import (
    ClassConflict,
    ClassNotFound,
    ClassPermissionDenied,
    add_student,
    assign_course,
    cancel_class_join_request,
    create_classroom,
    delete_classroom,
    list_classes,
    list_course_options,
    list_student_class_join_requests,
    list_teacher_class_join_requests,
    remove_student,
    review_class_join_request,
    unassign_course,
    update_classroom,
)
from app.services.password_reset_service import (
    PasswordResetRequestConflict,
    PasswordResetRequestDenied,
    PasswordResetRequestNotFound,
    list_teacher_password_reset_requests,
    review_student_password_reset,
)
from app.utils import error, json_body, roles_required, success
from . import classes_bp
from .schemas import (
    ValidationError,
    validate_classroom,
    validate_course_id,
    validate_student_account,
)


@classes_bp.get("")
@roles_required(UserRole.TEACHER, UserRole.STUDENT)
def classrooms():
    return success(list_classes(int(get_jwt_identity()), get_jwt()["role"]))


@classes_bp.get("/course-options")
@roles_required(UserRole.TEACHER)
def classroom_course_options():
    return success(list_course_options(int(get_jwt_identity())))


@classes_bp.get("/join-requests")
@roles_required(UserRole.TEACHER)
def classroom_join_requests():
    return success(list_teacher_class_join_requests(int(get_jwt_identity())))


@classes_bp.get("/join-requests/mine")
@roles_required(UserRole.STUDENT)
def my_classroom_join_requests():
    return success(list_student_class_join_requests(int(get_jwt_identity())))


@classes_bp.delete("/join-requests/<int:request_id>")
@roles_required(UserRole.STUDENT)
def cancel_my_classroom_join_request(request_id: int):
    try:
        result = cancel_class_join_request(request_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(result, "入班申请已撤回")


@classes_bp.put("/join-requests/<int:request_id>")
@roles_required(UserRole.TEACHER)
def review_classroom_join_request(request_id: int):
    action = str(json_body().get("action") or "").strip().upper()
    if action not in {"APPROVED", "REJECTED"}:
        return error("审批操作只能是 APPROVED 或 REJECTED", 400)
    try:
        result = review_class_join_request(
            request_id,
            int(get_jwt_identity()),
            action,
        )
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    except ClassConflict as exc:
        return error(str(exc), 409)
    message = "已同意入班申请，学生已加入班级" if action == "APPROVED" else "已拒绝入班申请"
    return success(result, message)


@classes_bp.get("/password-reset-requests")
@roles_required(UserRole.TEACHER)
def password_reset_requests():
    return success(list_teacher_password_reset_requests(int(get_jwt_identity())))


@classes_bp.put("/password-reset-requests/<int:request_id>")
@roles_required(UserRole.TEACHER)
def review_password_reset_request(request_id: int):
    action = str(json_body().get("action") or "").strip().upper()
    if action not in {"APPROVED", "REJECTED"}:
        return error("审批操作只能是 APPROVED 或 REJECTED", 400)
    try:
        result = review_student_password_reset(
            request_id,
            int(get_jwt_identity()),
            action,
        )
    except PasswordResetRequestNotFound as exc:
        return error(str(exc), 404)
    except PasswordResetRequestDenied as exc:
        return error(str(exc), 403)
    except PasswordResetRequestConflict as exc:
        return error(str(exc), 409)
    message = "已同意密码重置，新密码现已生效" if action == "APPROVED" else "已拒绝密码重置申请"
    return success(result, message)


@classes_bp.post("")
@roles_required(UserRole.TEACHER)
def add_classroom():
    try:
        classroom = create_classroom(
            int(get_jwt_identity()),
            validate_classroom(json_body()),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(classroom, "班级创建成功", 201)


@classes_bp.put("/<int:class_id>")
@roles_required(UserRole.TEACHER)
def edit_classroom(class_id: int):
    try:
        classroom = update_classroom(
            class_id,
            int(get_jwt_identity()),
            validate_classroom(json_body(), partial=True),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(classroom, "班级更新成功")


@classes_bp.delete("/<int:class_id>")
@roles_required(UserRole.TEACHER)
def remove_classroom(class_id: int):
    try:
        delete_classroom(class_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    return success(message="班级删除成功")


@classes_bp.post("/<int:class_id>/students")
@roles_required(UserRole.TEACHER)
def add_classroom_student(class_id: int):
    try:
        classroom = add_student(
            class_id,
            int(get_jwt_identity()),
            validate_student_account(json_body()),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(classroom, "学生已加入班级", 201)


@classes_bp.delete("/<int:class_id>/students/<int:student_id>")
@roles_required(UserRole.TEACHER)
def remove_classroom_student(class_id: int, student_id: int):
    try:
        classroom = remove_student(class_id, student_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    return success(classroom, "学生已移出班级")


@classes_bp.post("/<int:class_id>/courses")
@roles_required(UserRole.TEACHER)
def add_classroom_course(class_id: int):
    try:
        classroom = assign_course(
            class_id,
            validate_course_id(json_body()),
            int(get_jwt_identity()),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(classroom, "课程已关联，班级学生已同步加入", 201)


@classes_bp.delete("/<int:class_id>/courses/<int:course_id>")
@roles_required(UserRole.TEACHER)
def remove_classroom_course(class_id: int, course_id: int):
    try:
        classroom = unassign_course(class_id, course_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassPermissionDenied as exc:
        return error(str(exc), 403)
    return success(classroom, "班级课程关联已解除")

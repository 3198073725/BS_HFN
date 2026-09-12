from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.constants import CourseStatus, UserRole
from app.services.auth_service import AuthenticationError, get_active_user
from app.services.class_service import (
    ClassConflict,
    ClassNotFound,
    list_course_class_options,
    request_course_class_join,
)
from app.services.course_service import (
    CourseNotFound,
    CoursePermissionDenied,
    CourseStateError,
    change_course_status,
    create_chapter,
    create_course,
    delete_course_cover,
    delete_chapter,
    delete_draft_course,
    get_visible_course,
    list_categories,
    list_published_courses,
    list_teacher_courses,
    update_chapter,
    update_course,
    update_course_cover,
)
from app.utils import error, json_body, roles_required, success
from . import courses_bp
from .schemas import ValidationError, validate_chapter, validate_course


@courses_bp.get("/categories")
def categories():
    return success(list_categories())


@courses_bp.get("")
def published_courses():
    raw_category = request.args.get("category_id")
    try:
        category_id = int(raw_category) if raw_category else None
    except ValueError:
        return error("课程分类参数不正确", 400)
    if category_id is not None and category_id <= 0:
        return error("课程分类参数不正确", 400)
    return success(list_published_courses(category_id))


@courses_bp.get("/mine")
@roles_required(UserRole.TEACHER)
def teacher_courses():
    return success(list_teacher_courses(int(get_jwt_identity())))


@courses_bp.get("/<int:course_id>/classes")
@roles_required(UserRole.STUDENT)
def course_classes(course_id: int):
    try:
        classes = list_course_class_options(course_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    return success(classes)


@courses_bp.post("/<int:course_id>/classes/<int:class_id>/apply")
@roles_required(UserRole.STUDENT)
def apply_to_class_from_course(course_id: int, class_id: int):
    try:
        join_request = request_course_class_join(course_id, class_id, int(get_jwt_identity()))
    except ClassNotFound as exc:
        return error(str(exc), 404)
    except ClassConflict as exc:
        return error(str(exc), 409)
    return success(join_request, "入班申请已提交，请等待教师审批", 202)


@courses_bp.get("/<int:course_id>")
@jwt_required(optional=True)
def course_detail(course_id: int):
    identity = get_jwt_identity()
    viewer_id = None
    viewer_role = None
    try:
        if identity:
            viewer = get_active_user(identity)
            viewer_id = viewer.id
            viewer_role = viewer.role
        course = get_visible_course(course_id, viewer_id, viewer_role)
    except AuthenticationError as exc:
        return error(str(exc), 401)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    return success(course)


@courses_bp.post("")
@roles_required(UserRole.TEACHER)
def add_course():
    try:
        data = validate_course(json_body())
        course = create_course(int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    return success(course, "课程创建成功", 201)


@courses_bp.put("/<int:course_id>")
@roles_required(UserRole.TEACHER)
def edit_course(course_id: int):
    try:
        data = validate_course(json_body(), partial=True)
        course = update_course(course_id, int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(course, "课程更新成功")


@courses_bp.post("/<int:course_id>/cover")
@roles_required(UserRole.TEACHER)
def upload_course_cover(course_id: int):
    cover_file = request.files.get("cover")
    if cover_file is None:
        return error("请选择课程封面", 400)
    try:
        course = update_course_cover(course_id, int(get_jwt_identity()), cover_file)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    except ValueError as exc:
        return error(str(exc), 400)
    return success(course, "课程封面已更新")


@courses_bp.delete("/<int:course_id>/cover")
@roles_required(UserRole.TEACHER)
def remove_course_cover(course_id: int):
    try:
        course = delete_course_cover(course_id, int(get_jwt_identity()))
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(course, "课程封面已移除")


@courses_bp.post("/<int:course_id>/publish")
@roles_required(UserRole.TEACHER)
def publish_course(course_id: int):
    return _change_status(course_id, CourseStatus.PUBLISHED)


@courses_bp.post("/<int:course_id>/offline")
@roles_required(UserRole.TEACHER)
def offline_course(course_id: int):
    return _change_status(course_id, CourseStatus.OFFLINE)


@courses_bp.delete("/<int:course_id>")
@roles_required(UserRole.TEACHER)
def remove_course(course_id: int):
    try:
        delete_draft_course(course_id, int(get_jwt_identity()))
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(message="课程删除成功")


@courses_bp.post("/<int:course_id>/chapters")
@roles_required(UserRole.TEACHER)
def add_chapter(course_id: int):
    try:
        data = validate_chapter(json_body())
        chapter = create_chapter(course_id, int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(chapter, "章节创建成功", 201)


@courses_bp.put("/<int:course_id>/chapters/<int:chapter_id>")
@roles_required(UserRole.TEACHER)
def edit_chapter(course_id: int, chapter_id: int):
    try:
        data = validate_chapter(json_body(), partial=True)
        chapter = update_chapter(course_id, chapter_id, int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(chapter, "章节更新成功")


@courses_bp.delete("/<int:course_id>/chapters/<int:chapter_id>")
@roles_required(UserRole.TEACHER)
def remove_chapter(course_id: int, chapter_id: int):
    try:
        delete_chapter(course_id, chapter_id, int(get_jwt_identity()))
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(message="章节删除成功")


def _change_status(course_id: int, status: CourseStatus):
    try:
        course = change_course_status(course_id, int(get_jwt_identity()), status)
    except CourseNotFound as exc:
        return error(str(exc), 404)
    except CoursePermissionDenied as exc:
        return error(str(exc), 403)
    except CourseStateError as exc:
        return error(str(exc), 409)
    return success(course, "课程状态更新成功")

from flask import current_app, request
from kombu.exceptions import OperationalError

from app.constants import CourseStatus, UserRole, VideoStatus
from app.services.auth_service import ConflictError, create_user
from app.services.admin_service import (
    AdminConflict,
    AdminNotFound,
    change_admin_category_status,
    change_admin_course_status,
    change_user_status,
    create_admin_category,
    delete_admin_class,
    delete_failed_video,
    get_admin_video,
    list_admin_categories,
    list_admin_classes,
    list_admin_courses,
    list_users,
    list_video_operations,
    prepare_video_retry,
    serialize_admin_video,
    update_admin_category,
)
from app.services.video_processing_service import mark_video_failed, process_video_sync
from app.utils import error, json_body, roles_required, success
from app.blueprints.auth.schemas import ValidationError, validate_managed_user
from . import admin_bp
from .schemas import ValidationError as AdminValidationError, validate_category


@admin_bp.get("/users")
@roles_required(UserRole.ADMIN)
def users():
    role = str(request.args.get("role") or "").strip().upper() or None
    if role and role not in {item.value for item in UserRole}:
        return error("用户角色参数不正确", 400)
    raw_status = str(request.args.get("status") or "").strip().lower()
    if raw_status and raw_status not in {"true", "false", "1", "0"}:
        return error("用户状态参数不正确", 400)
    status = raw_status in {"true", "1"} if raw_status else None
    keyword = str(request.args.get("keyword") or "").strip() or None
    if keyword and len(keyword) > 100:
        return error("搜索关键词不能超过100位", 400)
    return success(list_users(role, status, keyword))


@admin_bp.post("/users")
@roles_required(UserRole.ADMIN)
def create_managed_user():
    try:
        data = validate_managed_user(json_body())
        user = create_user(data, data["role"])
    except ValidationError as exc:
        return error(str(exc), 400)
    except ConflictError as exc:
        return error(str(exc), 409)
    return success(user.to_dict(), "用户创建成功", 201)


@admin_bp.put("/users/<int:user_id>/status")
@roles_required(UserRole.ADMIN)
def set_user_status(user_id: int):
    raw_status = json_body().get("status")
    if not isinstance(raw_status, bool):
        return error("用户状态必须是布尔值", 400)
    try:
        user = change_user_status(user_id, raw_status)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(user, "用户状态更新成功")


@admin_bp.get("/videos")
@roles_required(UserRole.ADMIN)
def video_operations():
    status = str(request.args.get("status") or "").strip().upper() or None
    if status and status not in {item.value for item in VideoStatus}:
        return error("视频状态参数不正确", 400)
    keyword = _keyword()
    if isinstance(keyword, tuple):
        return keyword
    return success(list_video_operations(status, keyword))


@admin_bp.post("/videos/<int:video_id>/retry")
@roles_required(UserRole.ADMIN)
def retry_video(video_id: int):
    try:
        video = prepare_video_retry(video_id)
        if current_app.config["VIDEO_PROCESSING_ASYNC"]:
            from app.tasks.video_tasks import process_video

            try:
                process_video.delay(video.id)
            except OperationalError:
                current_app.logger.exception("管理员重新投递视频 %s 失败", video.id)
                failed = mark_video_failed(video.id, "后台任务队列暂不可用", "QUEUE")
                return error(
                    "重新投递失败，后台任务队列暂不可用",
                    503,
                    serialize_admin_video(get_admin_video(failed.id)),
                )
            return success(
                serialize_admin_video(get_admin_video(video.id)),
                "视频已重新加入转码队列",
                202,
            )
        processed = process_video_sync(video.id)
        serialized = serialize_admin_video(get_admin_video(processed.id))
        if processed.status == VideoStatus.READY.value:
            return success(serialized, "视频重新转码完成")
        return error("视频重新转码失败", 422, serialized)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)


@admin_bp.delete("/videos/<int:video_id>")
@roles_required(UserRole.ADMIN)
def remove_failed_video(video_id: int):
    try:
        delete_failed_video(video_id)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(message="失败的视频任务及文件已清理")


@admin_bp.get("/courses")
@roles_required(UserRole.ADMIN)
def managed_courses():
    status = str(request.args.get("status") or "").strip().upper() or None
    if status and status not in {item.value for item in CourseStatus}:
        return error("课程状态参数不正确", 400)
    keyword = _keyword()
    if isinstance(keyword, tuple):
        return keyword
    return success(list_admin_courses(status, keyword))


@admin_bp.put("/courses/<int:course_id>/status")
@roles_required(UserRole.ADMIN)
def set_course_status(course_id: int):
    raw_status = str(json_body().get("status") or "").strip().upper()
    if raw_status not in {CourseStatus.PUBLISHED.value, CourseStatus.OFFLINE.value}:
        return error("管理员只能将课程设为已发布或已下线", 400)
    try:
        course = change_admin_course_status(course_id, CourseStatus(raw_status))
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(course, "课程状态更新成功")


@admin_bp.get("/classes")
@roles_required(UserRole.ADMIN)
def managed_classes():
    keyword = _keyword()
    if isinstance(keyword, tuple):
        return keyword
    return success(list_admin_classes(keyword))


@admin_bp.delete("/classes/<int:class_id>")
@roles_required(UserRole.ADMIN)
def remove_class(class_id: int):
    try:
        delete_admin_class(class_id)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    return success(message="班级及成员关系已删除")


@admin_bp.get("/categories")
@roles_required(UserRole.ADMIN)
def managed_categories():
    return success(list_admin_categories())


@admin_bp.post("/categories")
@roles_required(UserRole.ADMIN)
def add_category():
    try:
        category = create_admin_category(validate_category(json_body()))
    except AdminValidationError as exc:
        return error(str(exc), 400)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(category, "课程分类已创建", 201)


@admin_bp.put("/categories/<int:category_id>")
@roles_required(UserRole.ADMIN)
def edit_category(category_id: int):
    try:
        category = update_admin_category(
            category_id,
            validate_category(json_body(), partial=True),
        )
    except AdminValidationError as exc:
        return error(str(exc), 400)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(category, "课程分类已更新")


@admin_bp.put("/categories/<int:category_id>/status")
@roles_required(UserRole.ADMIN)
def set_category_status(category_id: int):
    raw_status = json_body().get("status")
    if not isinstance(raw_status, bool):
        return error("分类状态必须是布尔值", 400)
    try:
        category = change_admin_category_status(category_id, raw_status)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    return success(category, "课程分类状态更新成功")


def _keyword():
    keyword = str(request.args.get("keyword") or "").strip() or None
    if keyword and len(keyword) > 100:
        return error("搜索关键词不能超过100位", 400)
    return keyword

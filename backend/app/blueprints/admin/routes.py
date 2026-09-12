from flask import current_app, request
from flask_jwt_extended import get_jwt_identity
from kombu.exceptions import OperationalError

from app.constants import CourseStatus, UserRole, VideoStatus
from app.extensions import db
from app.services.auth_service import AuthenticationError, ConflictError, create_user, set_user_password
from app.services.audit_service import list_admin_audit_logs, record_admin_action
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
from app.blueprints.auth.schemas import ValidationError as AuthValidationError, validate_new_password
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
    paging = _pagination()
    if not isinstance(paging, dict):
        return paging
    return success(list_users(**paging, role=role, status=status, keyword=keyword))


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
    _record_audit(
        "USER_CREATE",
        "USER",
        user.id,
        f"创建{data['role']}账号：{user.username}",
        {"role": data["role"], "username": user.username},
    )
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
    _record_audit(
        "USER_STATUS_CHANGE",
        "USER",
        user_id,
        f"将用户 {user['username']} 设为{'启用' if raw_status else '禁用'}",
        {"status": raw_status},
    )
    return success(user, "用户状态更新成功")


@admin_bp.put("/users/<int:user_id>/password")
@roles_required(UserRole.ADMIN)
def reset_managed_user_password(user_id: int):
    if user_id == int(get_jwt_identity()):
        return error("不能通过用户管理重置当前登录账号的密码", 409)
    try:
        password = validate_new_password(json_body())
        user = set_user_password(user_id, password)
    except AuthValidationError as exc:
        return error(str(exc), 400)
    except AuthenticationError as exc:
        return error(str(exc), 404)
    except ConflictError as exc:
        return error(str(exc), 409)
    _record_audit(
        "USER_PASSWORD_RESET",
        "USER",
        user.id,
        f"重置用户密码：{user.username}",
    )
    return success(message="用户密码已重置")


@admin_bp.get("/videos")
@roles_required(UserRole.ADMIN)
def video_operations():
    status = str(request.args.get("status") or "").strip().upper() or None
    if status and status not in {item.value for item in VideoStatus}:
        return error("视频状态参数不正确", 400)
    keyword = _keyword()
    if isinstance(keyword, tuple):
        return keyword
    paging = _pagination()
    if not isinstance(paging, dict):
        return paging
    return success(list_video_operations(**paging, status=status, keyword=keyword))


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
                _record_audit(
                    "VIDEO_RETRY",
                    "VIDEO",
                    video.id,
                    f"重新投递视频失败：{video.title}",
                    {"result": "QUEUE_FAILED"},
                )
                return error(
                    "重新投递失败，后台任务队列暂不可用",
                    503,
                    serialize_admin_video(get_admin_video(failed.id)),
                )
            serialized = serialize_admin_video(get_admin_video(video.id))
            _record_audit(
                "VIDEO_RETRY",
                "VIDEO",
                video.id,
                f"重新投递视频：{video.title}",
                {"result": "QUEUED"},
            )
            return success(
                serialized,
                "视频已重新加入转码队列",
                202,
            )
        processed = process_video_sync(video.id)
        serialized = serialize_admin_video(get_admin_video(processed.id))
        _record_audit(
            "VIDEO_RETRY",
            "VIDEO",
            video.id,
            f"重新处理视频：{video.title}",
            {"result": processed.status},
        )
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
        video = get_admin_video(video_id)
        title = video.title
        delete_failed_video(video_id)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    _record_audit("VIDEO_DELETE", "VIDEO", video_id, f"清理失败视频任务：{title}")
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
    paging = _pagination()
    if not isinstance(paging, dict):
        return paging
    return success(list_admin_courses(**paging, status=status, keyword=keyword))


@admin_bp.get("/audit-logs")
@roles_required(UserRole.ADMIN)
def audit_logs():
    paging = _pagination()
    if not isinstance(paging, dict):
        return paging
    action = str(request.args.get("action") or "").strip().upper() or None
    resource_type = str(request.args.get("resource_type") or "").strip().upper() or None
    if action and len(action) > 50:
        return error("审计动作参数不能超过50位", 400)
    if resource_type and len(resource_type) > 50:
        return error("资源类型参数不能超过50位", 400)
    keyword = _keyword()
    if isinstance(keyword, tuple):
        return keyword
    return success(
        list_admin_audit_logs(
            **paging,
            action=action,
            resource_type=resource_type,
            keyword=keyword,
        )
    )


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
    _record_audit(
        "COURSE_STATUS_CHANGE",
        "COURSE",
        course_id,
        f"将课程 {course['name']} 设为{raw_status}",
        {"status": raw_status},
    )
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
        class_name = delete_admin_class(class_id)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    _record_audit(
        "CLASS_DELETE",
        "CLASS",
        class_id,
        f"删除教学班级：{class_name}",
    )
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
    _record_audit(
        "CATEGORY_CREATE",
        "CATEGORY",
        category["id"],
        f"创建课程分类：{category['name']}",
    )
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
    _record_audit(
        "CATEGORY_UPDATE",
        "CATEGORY",
        category_id,
        f"更新课程分类：{category['name']}",
    )
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
    _record_audit(
        "CATEGORY_STATUS_CHANGE",
        "CATEGORY",
        category_id,
        f"将课程分类 {category['name']} 设为{'启用' if raw_status else '禁用'}",
        {"status": raw_status},
    )
    return success(category, "课程分类状态更新成功")


def _keyword():
    keyword = str(request.args.get("keyword") or "").strip() or None
    if keyword and len(keyword) > 100:
        return error("搜索关键词不能超过100位", 400)
    return keyword


def _pagination():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        return error("分页参数必须是整数", 400)
    if page < 1:
        return error("页码必须大于等于1", 400)
    if page_size < 1 or page_size > 100:
        return error("每页数量必须在1到100之间", 400)
    return {"page": page, "page_size": page_size}


def _record_audit(
    action: str,
    resource_type: str,
    resource_id: int | None,
    summary: str,
    details: dict | None = None,
) -> None:
    try:
        record_admin_action(
            int(get_jwt_identity()),
            action,
            resource_type,
            resource_id,
            summary,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("管理员操作审计写入失败：%s", action)

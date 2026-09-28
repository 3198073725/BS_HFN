from flask import current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from kombu.exceptions import OperationalError

from app.constants import UserRole
from app.services.auth_service import AuthenticationError, get_active_user
from app.services.video_processing_service import (
    VideoNotFound,
    VideoPermissionDenied,
    VideoFileValidationError,
    VideoStateError,
    VideoUploadCancelled,
    cancel_pending_video_upload,
    create_video,
    create_and_process_video,
    delete_teacher_video,
    enqueue_video_processing,
    get_visible_video,
    mark_video_failed,
    prepare_teacher_retry,
    process_video_sync,
    replace_video,
    update_video,
)
from app.utils import error, json_body, roles_required, success
from . import videos_bp
from .schemas import (
    ValidationError,
    validate_replacement,
    validate_update,
    validate_upload,
    validate_upload_token,
)


@videos_bp.post("/upload")
@roles_required(UserRole.TEACHER)
def upload_video():
    video_file = request.files.get("video_file")
    if video_file is None:
        return error("请选择视频文件", 400)
    try:
        data = validate_upload(request.form)
        if current_app.config["VIDEO_PROCESSING_ASYNC"]:
            video = create_video(video_file, int(get_jwt_identity()), data)
            try:
                video = enqueue_video_processing(video.id, data.get("upload_token"))
            except OperationalError:
                current_app.logger.exception("视频 %s 的 Celery 任务投递失败", video.id)
                video = mark_video_failed(video.id, "后台任务队列暂不可用", "QUEUE")
                return error("视频已保存，但后台任务队列暂不可用", 503, video.to_dict())
        else:
            video = create_and_process_video(video_file, int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except VideoNotFound as exc:
        return error(str(exc), 404)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    except VideoFileValidationError as exc:
        return error(str(exc), 400)
    except VideoUploadCancelled as exc:
        return error(str(exc), 409)
    except ValueError as exc:
        return error(str(exc), 409)
    if current_app.config["VIDEO_PROCESSING_ASYNC"]:
        return success(video.to_dict(), "视频已提交后台处理", 202)
    if video.status == "READY":
        return success(video.to_dict(), "视频上传完成", 201)
    return error("视频处理失败", 422, video.to_dict())


@videos_bp.post("/uploads/<upload_token>/cancel")
@roles_required(UserRole.TEACHER)
def cancel_upload(upload_token: str):
    try:
        token = validate_upload_token(upload_token, required=True)
        removed = cancel_pending_video_upload(token, int(get_jwt_identity()))
    except ValidationError as exc:
        return error(str(exc), 400)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    except VideoStateError as exc:
        return error(str(exc), 409)
    message = "上传和后台处理任务已取消，视频已删除" if removed else "取消指令已记录，上传连接正在终止"
    return success({"upload_token": token, "removed": removed}, message)


@videos_bp.get("/<int:video_id>")
@jwt_required(optional=True)
def video_detail(video_id: int):
    return _visible_video_response(video_id)


@videos_bp.get("/<int:video_id>/status")
@jwt_required(optional=True)
def video_status(video_id: int):
    return _visible_video_response(video_id)


@videos_bp.put("/<int:video_id>")
@roles_required(UserRole.TEACHER)
def edit_video(video_id: int):
    try:
        video = update_video(
            video_id,
            int(get_jwt_identity()),
            validate_update(json_body()),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except VideoNotFound as exc:
        return error(str(exc), 404)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    return success(video.to_dict(), "视频资料已更新")


@videos_bp.post("/<int:video_id>/retry")
@roles_required(UserRole.TEACHER)
def retry_video(video_id: int):
    try:
        video = prepare_teacher_retry(video_id, int(get_jwt_identity()))
    except VideoNotFound as exc:
        return error(str(exc), 404)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    except VideoStateError as exc:
        return error(str(exc), 409)
    return _start_video_processing(video, "视频已重新提交后台处理", "视频重新转码完成")


@videos_bp.post("/<int:video_id>/replace")
@roles_required(UserRole.TEACHER)
def replace_teacher_video(video_id: int):
    video_file = request.files.get("video_file")
    if video_file is None:
        return error("请选择视频文件", 400)
    try:
        video = replace_video(
            video_file,
            video_id,
            int(get_jwt_identity()),
            validate_replacement(request.form),
        )
    except ValidationError as exc:
        return error(str(exc), 400)
    except VideoNotFound as exc:
        return error(str(exc), 404)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    except VideoFileValidationError as exc:
        return error(str(exc), 400)
    except VideoUploadCancelled as exc:
        return error(str(exc), 409)
    except VideoStateError as exc:
        return error(str(exc), 409)
    return _start_video_processing(video, "替换视频已提交后台处理", "视频替换完成")


@videos_bp.delete("/<int:video_id>")
@roles_required(UserRole.TEACHER)
def remove_teacher_video(video_id: int):
    try:
        processing_stopped = delete_teacher_video(video_id, int(get_jwt_identity()))
    except VideoNotFound as exc:
        return error(str(exc), 404)
    except VideoPermissionDenied as exc:
        return error(str(exc), 403)
    except VideoStateError as exc:
        return error(str(exc), 409)
    message = "转码任务已终止，视频及相关学习数据已删除" if processing_stopped else "视频及相关学习数据已删除"
    return success(message=message)


def _visible_video_response(video_id: int):
    identity = get_jwt_identity()
    viewer_id = None
    viewer_role = None
    try:
        if identity:
            viewer = get_active_user(identity)
            viewer_id = viewer.id
            viewer_role = viewer.role
        video = get_visible_video(video_id, viewer_id, viewer_role)
    except AuthenticationError as exc:
        return error(str(exc), 401)
    except VideoNotFound as exc:
        return error(str(exc), 404)
    return success(video.to_dict())


def _start_video_processing(video, queued_message: str, ready_message: str):
    if current_app.config["VIDEO_PROCESSING_ASYNC"]:
        try:
            video = enqueue_video_processing(video.id)
        except OperationalError:
            current_app.logger.exception("视频 %s 的 Celery 任务投递失败", video.id)
            failed = mark_video_failed(video.id, "后台任务队列暂不可用", "QUEUE")
            return error("视频已保存，但后台任务队列暂不可用", 503, failed.to_dict())
        return success(video.to_dict(), queued_message, 202)

    processed = process_video_sync(video.id)
    if processed.status == "READY":
        return success(processed.to_dict(), ready_message, 201)
    return error("视频处理失败", 422, processed.to_dict())

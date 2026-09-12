from datetime import timedelta

from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash

from app.constants import PasswordResetStatus
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import PasswordResetRequest, TeachingClass, TeachingClassStudent, User
from app.services.notification_service import queue_notification


RESET_REQUEST_TTL = timedelta(hours=24)


class PasswordResetRequestNotFound(ValueError):
    pass


class PasswordResetRequestDenied(PermissionError):
    pass


class PasswordResetRequestConflict(ValueError):
    pass


def submit_student_password_reset(student: User, new_password: str) -> PasswordResetRequest:
    teacher_classes = db.session.execute(
        db.select(TeachingClass.teacher_id, TeachingClass.id, TeachingClass.name)
        .join(TeachingClassStudent, TeachingClassStudent.class_id == TeachingClass.id)
        .where(TeachingClassStudent.student_id == student.id)
        .order_by(TeachingClass.id)
    ).all()
    if not teacher_classes:
        raise PasswordResetRequestConflict("账号尚未加入班级，请联系管理员重置密码")

    now = utc_now()
    pending = db.session.scalar(
        db.select(PasswordResetRequest)
        .where(
            PasswordResetRequest.student_id == student.id,
            PasswordResetRequest.status == PasswordResetStatus.PENDING.value,
        )
        .order_by(PasswordResetRequest.created_at.desc(), PasswordResetRequest.id.desc())
    )
    if pending is not None and pending.expires_at <= now:
        pending.status = PasswordResetStatus.EXPIRED.value
        pending.reviewed_at = now
        pending = None

    password_hash = generate_password_hash(new_password)
    if pending is None:
        pending = PasswordResetRequest(
            student_id=student.id,
            requested_password_hash=password_hash,
            status=PasswordResetStatus.PENDING.value,
            expires_at=now + RESET_REQUEST_TTL,
        )
        db.session.add(pending)
        db.session.flush()
    else:
        pending.requested_password_hash = password_hash
        pending.expires_at = now + RESET_REQUEST_TTL
        pending.created_at = now
        pending.reviewer_id = None
        pending.reviewed_at = None

    classes_by_teacher: dict[int, list[tuple[int, str]]] = {}
    for teacher_id, class_id, class_name in teacher_classes:
        classes_by_teacher.setdefault(teacher_id, []).append((class_id, class_name))
    for teacher_id, classes in classes_by_teacher.items():
        class_names = "、".join(name for _, name in classes[:3])
        if len(classes) > 3:
            class_names += f"等{len(classes)}个班级"
        queue_notification(
            teacher_id,
            "学生申请重置密码",
            f"{student.real_name}（{student.student_no or student.username}）提交了密码重置申请，所属班级：{class_names}。",
            category="PASSWORD",
            sender_id=student.id,
            link=f"/classes?reset_request_id={pending.id}",
        )
    db.session.commit()
    return pending


def list_teacher_password_reset_requests(teacher_id: int) -> list[dict]:
    student_ids = (
        db.select(TeachingClassStudent.student_id)
        .join(TeachingClass, TeachingClass.id == TeachingClassStudent.class_id)
        .where(TeachingClass.teacher_id == teacher_id)
    )
    now = utc_now()
    requests = db.session.scalars(
        db.select(PasswordResetRequest)
        .options(joinedload(PasswordResetRequest.student))
        .where(
            PasswordResetRequest.student_id.in_(student_ids),
            PasswordResetRequest.status == PasswordResetStatus.PENDING.value,
            PasswordResetRequest.expires_at > now,
        )
        .order_by(PasswordResetRequest.created_at.asc(), PasswordResetRequest.id.asc())
    ).all()
    return [_serialize_for_teacher(item, teacher_id) for item in requests]


def review_student_password_reset(request_id: int, teacher_id: int, action: str) -> dict:
    reset_request = db.session.scalar(
        db.select(PasswordResetRequest)
        .options(joinedload(PasswordResetRequest.student))
        .where(PasswordResetRequest.id == request_id)
    )
    if reset_request is None:
        raise PasswordResetRequestNotFound("密码重置申请不存在")
    if not _teacher_class_rows(reset_request.student_id, teacher_id):
        raise PasswordResetRequestDenied("只能处理自己班级学生的密码重置申请")
    if reset_request.status != PasswordResetStatus.PENDING.value:
        raise PasswordResetRequestConflict("该密码重置申请已处理")

    now = utc_now()
    if reset_request.expires_at <= now:
        reset_request.status = PasswordResetStatus.EXPIRED.value
        reset_request.reviewed_at = now
        db.session.commit()
        raise PasswordResetRequestConflict("该密码重置申请已过期，请让学生重新提交")
    if not reset_request.student.status:
        raise PasswordResetRequestConflict("学生账号已被禁用，不能重置密码")

    approved = action == PasswordResetStatus.APPROVED.value
    if approved:
        reset_request.student.password_hash = reset_request.requested_password_hash
    reset_request.status = (
        PasswordResetStatus.APPROVED.value if approved else PasswordResetStatus.REJECTED.value
    )
    reset_request.reviewer_id = teacher_id
    reset_request.reviewed_at = now
    queue_notification(
        reset_request.student_id,
        "密码重置申请已同意" if approved else "密码重置申请未通过",
        (
            "班级教师已同意你的密码重置申请，现在可以使用申请时填写的新密码登录。"
            if approved
            else "班级教师未同意本次密码重置申请。如仍需重置，请核对信息后重新提交或联系管理员。"
        ),
        category="PASSWORD",
        sender_id=teacher_id,
        link="/notifications",
    )
    db.session.commit()
    return _serialize_for_teacher(reset_request, teacher_id)


def cancel_pending_password_resets(student_id: int, reviewer_id: int | None = None) -> int:
    pending = db.session.scalars(
        db.select(PasswordResetRequest).where(
            PasswordResetRequest.student_id == student_id,
            PasswordResetRequest.status == PasswordResetStatus.PENDING.value,
        )
    ).all()
    now = utc_now()
    for item in pending:
        item.status = PasswordResetStatus.CANCELLED.value
        item.reviewer_id = reviewer_id
        item.reviewed_at = now
    return len(pending)


def _serialize_for_teacher(reset_request: PasswordResetRequest, teacher_id: int) -> dict:
    classes = _teacher_class_rows(reset_request.student_id, teacher_id)
    return {
        "id": reset_request.id,
        "student_id": reset_request.student_id,
        "student_name": reset_request.student.real_name,
        "username": reset_request.student.username,
        "student_no": reset_request.student.student_no,
        "class_ids": [item.id for item in classes],
        "class_names": [item.name for item in classes],
        "status": reset_request.status,
        "requested_at": iso_utc(reset_request.created_at),
        "expires_at": iso_utc(reset_request.expires_at),
    }


def _teacher_class_rows(student_id: int, teacher_id: int) -> list[TeachingClass]:
    return db.session.scalars(
        db.select(TeachingClass)
        .join(TeachingClassStudent, TeachingClassStudent.class_id == TeachingClass.id)
        .where(
            TeachingClass.teacher_id == teacher_id,
            TeachingClassStudent.student_id == student_id,
        )
        .order_by(TeachingClass.id)
    ).all()

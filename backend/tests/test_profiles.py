from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.datetime_utils import utc_now
from app.extensions import db
from app.models import Course, CourseCategory, User


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_user_can_edit_profile_and_manage_avatar(app, client):
    registered = client.post(
        "/api/auth/register",
        json={
            "username": "profile_student",
            "password": "Profile123!",
            "real_name": "资料学生",
            "student_no": "PROFILE001",
            "email": "before@example.com",
        },
    )
    assert registered.status_code == 201
    session = registered.get_json()["data"]
    token = session["access_token"]
    user_id = session["user"]["id"]

    updated = client.put(
        "/api/users/me",
        headers=bearer(token),
        json={
            "real_name": "更新后的姓名",
            "email": "after@example.com",
            "phone": "13000000000",
            "bio": "这是用于个人主页展示的简介。",
        },
    )
    assert updated.status_code == 200
    updated_data = updated.get_json()["data"]
    assert updated_data["real_name"] == "更新后的姓名"
    assert updated_data["bio"] == "这是用于个人主页展示的简介。"

    public_response = client.get(f"/api/users/{user_id}")
    assert public_response.status_code == 200
    public_profile = public_response.get_json()["data"]
    assert public_profile["real_name"] == "更新后的姓名"
    assert public_profile["bio"] == "这是用于个人主页展示的简介。"
    assert "username" not in public_profile
    assert "email" not in public_profile
    assert "phone" not in public_profile

    avatar_response = client.post(
        "/api/users/me/avatar",
        headers=bearer(token),
        data={"avatar": (BytesIO(b"\x89PNG\r\n\x1a\nprofile-avatar"), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert avatar_response.status_code == 200
    avatar_url = avatar_response.get_json()["data"]["avatar_url"]
    assert avatar_url.startswith("/media/avatars/")
    avatar_path = Path(app.config["MEDIA_ROOT"]) / avatar_url.removeprefix("/media/")
    assert avatar_path.is_file()

    delete_response = client.delete("/api/users/me/avatar", headers=bearer(token))
    assert delete_response.status_code == 200
    assert delete_response.get_json()["data"]["avatar_url"] is None
    assert not avatar_path.exists()


def test_public_teacher_profile_only_lists_published_courses(app, client):
    with app.app_context():
        teacher = User(
            username="profile_teacher",
            password_hash=generate_password_hash("Teacher123!"),
            real_name="主页教师",
            teacher_no="PROFILE-T001",
            email="private-teacher@example.com",
            phone="13100000000",
            bio="负责程序设计课程。",
            role=UserRole.TEACHER.value,
            status=True,
        )
        category = CourseCategory(name="主页测试分类", status=True)
        db.session.add_all([teacher, category])
        db.session.flush()
        db.session.add_all(
            [
                Course(
                    teacher_id=teacher.id,
                    category_id=category.id,
                    name="公开课程",
                    status=CourseStatus.PUBLISHED.value,
                    published_at=utc_now(),
                ),
                Course(
                    teacher_id=teacher.id,
                    category_id=category.id,
                    name="未发布课程",
                    status=CourseStatus.DRAFT.value,
                ),
            ]
        )
        db.session.commit()
        teacher_id = teacher.id

    response = client.get(f"/api/users/{teacher_id}")
    assert response.status_code == 200
    profile = response.get_json()["data"]
    assert profile["teacher_no"] == "PROFILE-T001"
    assert [course["name"] for course in profile["courses"]] == ["公开课程"]
    assert "email" not in profile
    assert "phone" not in profile


def test_profile_validation_and_email_conflict(client):
    first = client.post(
        "/api/auth/register",
        json={
            "username": "profile_first",
            "password": "Profile123!",
            "real_name": "第一位学生",
            "student_no": "PROFILE002",
            "email": "first@example.com",
        },
    ).get_json()["data"]
    client.post(
        "/api/auth/register",
        json={
            "username": "profile_second",
            "password": "Profile123!",
            "real_name": "第二位学生",
            "student_no": "PROFILE003",
            "email": "second@example.com",
        },
    )

    invalid = client.put(
        "/api/users/me",
        headers=bearer(first["access_token"]),
        json={"phone": "123"},
    )
    assert invalid.status_code == 400

    conflict = client.put(
        "/api/users/me",
        headers=bearer(first["access_token"]),
        json={"email": "second@example.com"},
    )
    assert conflict.status_code == 409

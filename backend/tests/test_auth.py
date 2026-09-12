from werkzeug.security import generate_password_hash

from app.constants import UserRole
from app.extensions import db
from app.models import User


STUDENT = {
    "username": "student01",
    "password": "Study123!",
    "real_name": "测试学生",
    "student_no": "S20260001",
    "email": "student@example.com",
}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_refresh_me_and_logout(client):
    registered = client.post("/api/auth/register", json=STUDENT)
    assert registered.status_code == 201
    payload = registered.get_json()["data"]
    assert payload["user"]["role"] == "STUDENT"
    assert "password_hash" not in payload["user"]
    assert payload["user"]["created_at"].endswith("Z")

    duplicate = client.post("/api/auth/register", json=STUDENT)
    assert duplicate.status_code == 409

    wrong = client.post("/api/auth/login", json={"account": "student01", "password": "wrong-pass"})
    assert wrong.status_code == 401

    logged_in = client.post(
        "/api/auth/login",
        json={"account": "student01", "password": STUDENT["password"]},
    )
    assert logged_in.status_code == 200
    tokens = logged_in.get_json()["data"]
    assert tokens["user"]["last_login_at"].endswith("Z")

    me = client.get("/api/users/me", headers=bearer(tokens["access_token"]))
    assert me.status_code == 200
    assert me.get_json()["data"]["username"] == "student01"

    refreshed = client.post("/api/auth/refresh", headers=bearer(tokens["refresh_token"]))
    assert refreshed.status_code == 200
    refreshed_tokens = refreshed.get_json()["data"]
    assert refreshed_tokens["access_token"]

    reused_refresh = client.post("/api/auth/refresh", headers=bearer(tokens["refresh_token"]))
    assert reused_refresh.status_code == 401

    logged_out = client.post(
        "/api/auth/logout",
        headers=bearer(refreshed_tokens["refresh_token"]),
        json={"access_token": refreshed_tokens["access_token"]},
    )
    assert logged_out.status_code == 200
    revoked_access = client.get("/api/users/me", headers=bearer(refreshed_tokens["access_token"]))
    revoked_refresh = client.post(
        "/api/auth/refresh",
        headers=bearer(refreshed_tokens["refresh_token"]),
    )
    assert revoked_access.status_code == 401
    assert revoked_refresh.status_code == 401


def test_role_permissions_and_admin_user_creation(app, client):
    with app.app_context():
        admin = User(
            username="admin",
            password_hash=generate_password_hash("Admin123!"),
            real_name="系统管理员",
            role=UserRole.ADMIN.value,
        )
        db.session.add(admin)
        db.session.commit()

    admin_login = client.post(
        "/api/auth/login",
        json={"account": "admin", "password": "Admin123!"},
    ).get_json()["data"]

    teacher = client.post(
        "/api/admin/users",
        headers=bearer(admin_login["access_token"]),
        json={
            "username": "teacher01",
            "password": "Teach123!",
            "real_name": "测试教师",
            "teacher_no": "T20260001",
            "role": "TEACHER",
        },
    )
    assert teacher.status_code == 201
    assert teacher.get_json()["data"]["role"] == "TEACHER"

    student_login = client.post("/api/auth/register", json=STUDENT).get_json()["data"]
    forbidden = client.post(
        "/api/admin/users",
        headers=bearer(student_login["access_token"]),
        json={
            "username": "teacher02",
            "password": "Teach123!",
            "real_name": "无权创建",
            "teacher_no": "T20260002",
            "role": "TEACHER",
        },
    )
    assert forbidden.status_code == 403

from werkzeug.security import generate_password_hash

from app.constants import UserRole
from app.extensions import db
from app.models import TeachingClass, TeachingClassStudent, User


STUDENT = {
    "username": "student01",
    "password": "Study123!",
    "real_name": "测试学生",
    "student_no": "S20260001",
    "email": "student@example.com",
}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_non_object_json_body_returns_bad_request(client):
    for body in ([{"account": "student01"}], "value", 42, True):
        response = client.post("/api/auth/login", json=body)
        assert response.status_code == 400
        assert response.get_json()["message"] == "请求体必须是 JSON 对象"


def test_malformed_json_body_returns_json_bad_request(client):
    response = client.post(
        "/api/auth/login",
        data='{"account":',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["message"] == "请求体不是有效的 JSON"


def test_login_rejects_oversized_credentials_before_password_check(client):
    account = client.post(
        "/api/auth/login",
        json={"account": "a" * 101, "password": "password"},
    )
    password = client.post(
        "/api/auth/login",
        json={"account": "student", "password": "p" * 73},
    )

    assert account.status_code == 400
    assert account.get_json()["message"] == "账号不能超过100位"
    assert password.status_code == 400
    assert password.get_json()["message"] == "密码不能超过72位"


def test_invalid_access_token_is_an_authentication_failure(client):
    response = client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_registration_rejects_identifiers_longer_than_database_columns(client):
    too_long_student_no = {
        **STUDENT,
        "username": "student_long_number",
        "student_no": "S" * 51,
    }
    student_response = client.post("/api/auth/register", json=too_long_student_no)
    assert student_response.status_code == 400
    assert student_response.get_json()["message"] == "学号不能超过50位"

    too_long_email = {
        **STUDENT,
        "username": "student_long_email",
        "student_no": "S20260002",
        "email": f"{'a' * 96}@example.com",
    }
    email_response = client.post("/api/auth/register", json=too_long_email)
    assert email_response.status_code == 400
    assert email_response.get_json()["message"] == "邮箱不能超过100位"


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
        admin_id = admin.id

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

    teacher_with_student_number = client.post(
        "/api/admin/users",
        headers=bearer(admin_login["access_token"]),
        json={
            "username": "teacher_mixed",
            "password": "Teach123!",
            "real_name": "混合编号教师",
            "teacher_no": "T20260003",
            "student_no": "S20260003",
            "role": "TEACHER",
        },
    )
    assert teacher_with_student_number.status_code == 400
    assert teacher_with_student_number.get_json()["message"] == "教师账号不能提供 student_no"

    student_with_teacher_number = client.post(
        "/api/admin/users",
        headers=bearer(admin_login["access_token"]),
        json={
            "username": "student_mixed",
            "password": "Study123!",
            "real_name": "混合编号学生",
            "teacher_no": "T20260004",
            "student_no": "S20260004",
            "role": "STUDENT",
        },
    )
    assert student_with_teacher_number.status_code == 400
    assert student_with_teacher_number.get_json()["message"] == "学生账号不能提供 teacher_no"

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


def test_password_recovery_and_admin_password_reset_are_verified(app, client):
    registered = client.post("/api/auth/register", json=STUDENT)
    assert registered.status_code == 201

    with app.app_context():
        student = db.session.scalar(db.select(User).where(User.username == STUDENT["username"]))
        teacher = User(
            username="password_teacher",
            password_hash=generate_password_hash("Teacher123!"),
            real_name="审批教师",
            teacher_no="PT001",
            role=UserRole.TEACHER.value,
        )
        other_teacher = User(
            username="other_password_teacher",
            password_hash=generate_password_hash("Teacher123!"),
            real_name="其他教师",
            teacher_no="PT002",
            role=UserRole.TEACHER.value,
        )
        db.session.add_all([teacher, other_teacher])
        db.session.flush()
        classroom = TeachingClass(teacher_id=teacher.id, name="密码审批班")
        db.session.add(classroom)
        db.session.flush()
        db.session.add(TeachingClassStudent(class_id=classroom.id, student_id=student.id))
        db.session.commit()
        teacher_username = teacher.username
        other_teacher_username = other_teacher.username

    rejected = client.post(
        "/api/auth/reset-password",
        json={"username": STUDENT["username"], "verification": "wrong", "new_password": "NewStudy123!"},
    )
    assert rejected.status_code == 400
    recovered = client.post(
        "/api/auth/reset-password",
        json={
            "username": STUDENT["username"],
            "verification": STUDENT["student_no"],
            "new_password": "NewStudy123!",
        },
    )
    assert recovered.status_code == 202
    assert recovered.get_json()["data"]["status"] == "PENDING"
    assert client.post(
        "/api/auth/login",
        json={"account": STUDENT["username"], "password": STUDENT["password"]},
    ).status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"account": STUDENT["username"], "password": "NewStudy123!"},
    ).status_code == 401

    teacher_token = client.post(
        "/api/auth/login", json={"account": teacher_username, "password": "Teacher123!"}
    ).get_json()["data"]["access_token"]
    other_teacher_token = client.post(
        "/api/auth/login", json={"account": other_teacher_username, "password": "Teacher123!"}
    ).get_json()["data"]["access_token"]
    requests = client.get(
        "/api/classes/password-reset-requests", headers=bearer(teacher_token)
    )
    assert requests.status_code == 200
    request_item = requests.get_json()["data"][0]
    assert request_item["student_no"] == STUDENT["student_no"]
    assert request_item["class_names"] == ["密码审批班"]
    assert client.get(
        "/api/classes/password-reset-requests", headers=bearer(other_teacher_token)
    ).get_json()["data"] == []
    assert client.put(
        f"/api/classes/password-reset-requests/{request_item['id']}",
        headers=bearer(other_teacher_token),
        json={"action": "APPROVED"},
    ).status_code == 403
    approved = client.put(
        f"/api/classes/password-reset-requests/{request_item['id']}",
        headers=bearer(teacher_token),
        json={"action": "APPROVED"},
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["status"] == "APPROVED"
    assert client.post(
        "/api/auth/login",
        json={"account": STUDENT["username"], "password": "NewStudy123!"},
    ).status_code == 200

    with app.app_context():
        admin = User(
            username="password_admin",
            password_hash=generate_password_hash("Admin123!"),
            real_name="密码管理员",
            email="password-admin@example.com",
            role=UserRole.ADMIN.value,
        )
        db.session.add(admin)
        db.session.commit()
        password_admin_id = admin.id
    admin_token = client.post(
        "/api/auth/login", json={"account": "password_admin", "password": "Admin123!"}
    ).get_json()["data"]["access_token"]
    public_admin_reset = client.post(
        "/api/auth/reset-password",
        json={
            "username": "password_admin",
            "verification": "password-admin@example.com",
            "new_password": "PublicReset123!",
        },
    )
    assert public_admin_reset.status_code == 400
    assert client.put(
        f"/api/admin/users/{password_admin_id}/password",
        headers=bearer(admin_token),
        json={"new_password": "SelfReset123!"},
    ).status_code == 409
    with app.app_context():
        student_id = db.session.scalar(db.select(User.id).where(User.username == STUDENT["username"]))
    reset = client.put(
        f"/api/admin/users/{student_id}/password",
        headers=bearer(admin_token),
        json={"new_password": "AdminReset123!"},
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"account": STUDENT["username"], "password": "AdminReset123!"},
    ).status_code == 200


def test_student_password_reset_requires_a_current_class_teacher(app, client):
    payload = {
        **STUDENT,
        "username": "unassigned_student",
        "student_no": "S20269999",
        "email": "unassigned@example.com",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    response = client.post(
        "/api/auth/reset-password",
        json={
            "username": payload["username"],
            "verification": payload["student_no"],
            "new_password": "NewStudy123!",
        },
    )
    assert response.status_code == 409
    assert response.get_json()["message"] == "账号尚未加入班级，请联系管理员重置密码"

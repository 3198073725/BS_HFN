"""Smoke-read the development data through role-protected API endpoints.

Only demo account logins/logouts are written. No approvals, retries or submissions.
"""
import json
import os
from pathlib import Path

from app import create_app
from scripts.demo_catalog import DEMO_PASSWORD, TEACHERS


def verify():
    app = create_app()
    report = json.loads((Path(__file__).resolve().parents[1] / "demo-data-report.json").read_text(encoding="utf-8"))
    course_id = report["courses"]["c"]
    client = app.test_client()
    checks = 0
    role_paths = {
        "defense_admin": ["/admin/users", "/admin/videos", "/admin/courses", "/admin/classes", "/admin/categories", "/admin/audit-logs", "/notices/manage", "/statistics"],
        "defense_teacher": ["/classes", "/classes/join-requests", "/classes/password-reset-requests", "/courses/mine", "/questions", "/homeworks/manage", "/exams/manage", "/statistics/courses"],
        "defense_student01": ["/learning/courses", "/learning/favorites", "/classes", "/classes/join-requests/mine", f"/courses/{course_id}/classes", "/homeworks", "/exams", "/statistics"],
        "defense_new_student": ["/learning/courses", "/classes", "/classes/join-requests/mine", f"/courses/{course_id}/classes", "/homeworks", "/exams"],
    }
    for username, _name, _bio in TEACHERS[1:]:
        role_paths[username] = ["/classes", "/courses/mine", "/homeworks/manage", "/exams/manage"]
    for username, paths in role_paths.items():
        response = client.post("/api/auth/login", json={"account": username, "password": os.getenv("DEFENSE_DEMO_PASSWORD") or DEMO_PASSWORD})
        assert response.status_code == 200, f"登录失败：{username}"
        session = response.get_json()["data"]
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        for path in ["/users/me", "/notifications", *paths]:
            result = client.get("/api" + path, headers=headers)
            assert result.status_code == 200, f"{username}: {path}: {result.status_code}"
            checks += 1
        if username == "defense_student01":
            for identity, content_type in zip(report["homeworks"]["c"][:4], ["application/pdf", "text/plain", "image/png", "application/zip"]):
                result = client.get(f"/api/homeworks/{identity}/attachment", headers=headers)
                expected_types = {content_type}
                if content_type == "application/zip":
                    expected_types.add("application/x-zip-compressed")
                assert result.status_code == 200 and result.mimetype in expected_types, f"附件{identity}: {result.status_code}, {result.mimetype}"
                checks += 1
            teacher_id = report["accounts"]["defense_teacher"]["id"]
            profile = client.get(f"/api/users/{teacher_id}").get_json()["data"]
            assert "email" not in profile and "phone" not in profile
            assert client.get("/api/admin/users", headers=headers).status_code == 403
            checks += 2
        if username == "defense_new_student":
            assert client.get("/api/learning/courses", headers=headers).get_json()["data"] == []
        result = client.post("/api/auth/logout", headers=headers, json={"refresh_token": session["refresh_token"]})
        assert result.status_code == 200
    for username in ("defense_student29", "defense_student30"):
        assert client.post("/api/auth/login", json={"account": username, "password": os.getenv("DEFENSE_DEMO_PASSWORD") or DEMO_PASSWORD}).status_code == 401
        checks += 1
    print(json.dumps({"api_checks_passed": checks, "accounts_tested": len(role_paths), "disabled_accounts_rejected": 2}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    verify()

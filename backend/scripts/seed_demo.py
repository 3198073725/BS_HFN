"""Add a rich, fictional defense dataset without deleting existing business data.

CLI takes a SQL backup first. One transaction and a marker make reruns no-ops.
No application password, .env setting, or existing user is changed.
"""
import argparse
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path

from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from app import create_app
from app.datetime_utils import utc_now
from app.extensions import db
from app.models import (
    AdminAuditLog, Answer, Chapter, Course, CourseCategory, CourseStudent, Exam,
    ExamAnswer, ExamQuestion, ExamRecord, Favorite, Homework, HomeworkSubmission,
    LearningRecord, Notice, Notification, PasswordResetRequest, Question,
    TeachingClass, TeachingClassCourse, TeachingClassJoinRequest, TeachingClassStudent,
    User, Video, VideoNote,
)
from scripts.demo_catalog import COURSES, DEMO_PASSWORD, RESET_PASSWORD, SEED_MARKER, STUDENT_NAMES, TEACHERS


EXAM_BANKS = {
    "c": [
        ("SINGLE", "C语言中声明整数变量应使用哪种类型？", ["int", "float", "char*", "void"], "A"),
        ("SINGLE", "计算整数a和b的平均值并保留小数，应使用哪种表达式？", ["(a+b)/2", "(a+b)/2.0", "a+b/2", "a-b"], "B"),
        ("JUDGE", "两个整数相除时，结果可能丢失小数部分。", [], "TRUE"),
        ("SINGLE", "for(int i=0;i<10;i++)的循环体执行几次？", ["0", "9", "10", "11"], "C"),
        ("JUDGE", "函数可以用于减少重复代码并划分职责。", [], "TRUE"),
    ],
    "python": [
        ("SINGLE", "Python列表使用哪种括号？", ["[]", "{}", "()", "<>"], "A"),
        ("SINGLE", "字典主要存储哪种结构？", ["仅整数", "键值对", "仅字符串", "文件路径"], "B"),
        ("JUDGE", "列表可以包含不同类型的元素。", [], "TRUE"),
        ("SINGLE", "计算列表长度使用哪个函数？", ["sum", "max", "len", "open"], "C"),
        ("JUDGE", "数据分析前应检查缺失值与异常值。", [], "TRUE"),
    ],
    "database": [
        ("SINGLE", "用于唯一标识一行记录的字段称为？", ["主键", "视图", "索引文件", "游标"], "A"),
        ("SINGLE", "查询数据使用哪个SQL关键字？", ["DELETE", "SELECT", "DROP", "UPDATE"], "B"),
        ("JUDGE", "外键可以维护两张表之间的引用关系。", [], "TRUE"),
        ("SINGLE", "筛选分组后的结果应使用？", ["ORDER BY", "LIMIT", "HAVING", "INSERT"], "C"),
        ("JUDGE", "事务具有原子性，失败时可以回滚。", [], "TRUE"),
    ],
    "web": [
        ("SINGLE", "描述网页内容结构的语言是？", ["HTML", "SQL", "C", "Bash"], "A"),
        ("SINGLE", "设置组件外边距的CSS属性是？", ["padding", "margin", "color", "display"], "B"),
        ("JUDGE", "前端表单校验不能替代后端权限与参数校验。", [], "TRUE"),
        ("SINGLE", "只读取资源通常使用哪个HTTP方法？", ["POST", "DELETE", "GET", "PATCH"], "C"),
        ("JUDGE", "稳定的组件尺寸有助于减少页面布局跳动。", [], "TRUE"),
    ],
    "calculus": [
        ("SINGLE", "函数f(x)=x的导数为？", ["1", "0", "x", "2x"], "A"),
        ("SINGLE", "函数f(x)=x²的导数为？", ["x", "2x", "2", "x³"], "B"),
        ("JUDGE", "函数在一点可导，则在该点连续。", [], "TRUE"),
        ("SINGLE", "常数函数的导数为？", ["1", "常数本身", "0", "不存在"], "C"),
        ("JUDGE", "函数连续就一定处处可导。", [], "FALSE"),
    ],
    "linear": [
        ("SINGLE", "单位矩阵的主对角线元素为？", ["1", "0", "-1", "2"], "A"),
        ("SINGLE", "一个2行3列矩阵转置后为？", ["2行3列", "3行2列", "3行3列", "2行2列"], "B"),
        ("JUDGE", "矩阵乘法一般不满足交换律。", [], "TRUE"),
        ("SINGLE", "行列式为0的方阵称为？", ["单位矩阵", "正交矩阵", "奇异矩阵", "可逆矩阵"], "C"),
        ("JUDGE", "齐次线性方程组总有零解。", [], "TRUE"),
    ],
    "english": [
        ("SINGLE", "Which word means 假设 in academic writing?", ["hypothesis", "holiday", "hardware", "history"], "A"),
        ("SINGLE", "Which connector introduces a contrast?", ["therefore", "however", "also", "finally"], "B"),
        ("JUDGE", "Skimming helps identify the main idea of a passage.", [], "TRUE"),
        ("SINGLE", "Which word is closest to evidence?", ["emotion", "schedule", "proof", "weather"], "C"),
        ("JUDGE", "A conclusion should always introduce an unrelated topic.", [], "FALSE"),
    ],
    "physics": [
        ("SINGLE", "力的国际单位是？", ["牛顿", "焦耳", "瓦特", "米"], "A"),
        ("SINGLE", "匀速直线运动的加速度是？", ["1", "0", "速度值", "无限大"], "B"),
        ("JUDGE", "重复测量有助于评估实验结果的不确定性。", [], "TRUE"),
        ("SINGLE", "动能与速度的哪一项成正比？", ["速度", "速度倒数", "速度平方", "速度三次方"], "C"),
        ("JUDGE", "实验记录只需保留符合预期的结果。", [], "FALSE"),
    ],
}


def existing_marker():
    return db.session.scalar(db.select(AdminAuditLog).where(AdminAuditLog.action == "DEMO_SEED", AdminAuditLog.summary == SEED_MARKER))


def validate_assets(assets):
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    for key, *_rest in COURSES:
        for suffix in ("cover.png", "cover.jpg", "source.mp4", "hls/index.m3u8"):
            if not (assets / key / suffix).is_file():
                raise RuntimeError(f"缺少演示媒体：{key}/{suffix}，请先生成素材")
        if manifest["courses"][key]["duration"] <= 0:
            raise RuntimeError("演示媒体时长无效")
    for name in ("lab-guide.pdf", "lab-report.txt", "result.png", "source-code.zip"):
        if not (assets / "attachments" / name).is_file():
            raise RuntimeError(f"缺少演示作业附件：{name}")
    for index in range(len(TEACHERS)):
        if not (assets / f"teacher-{index}.png").is_file():
            raise RuntimeError("缺少教师头像")
    return manifest


def backup_mysql(app):
    """No password on the command line; refuse to seed if backup fails."""
    executable = shutil.which("mysqldump")
    if not executable:
        raise RuntimeError("找不到mysqldump，停止写入，避免无备份修改数据库")
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if url.get_backend_name() != "mysql":
        raise RuntimeError("演示初始化CLI仅允许当前本地MySQL数据库")
    directory = Path(__file__).resolve().parents[1] / "backups"
    directory.mkdir(exist_ok=True)
    destination = directory / f"pre-defense-{utc_now():%Y%m%d-%H%M%S-%f}.sql"
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = url.password or ""
    command = [executable, "--single-transaction", "--skip-lock-tables", "--no-tablespaces",
               "--set-gtid-purged=OFF", "--hex-blob", "--default-character-set=utf8mb4",
               "--host", url.host or "127.0.0.1", "--port", str(url.port or 3306),
               "--user", url.username or "root", url.database]
    with destination.open("xb") as stream:
        result = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.PIPE, timeout=120)
    if result.returncode or destination.stat().st_size == 0:
        raise RuntimeError("SQL备份失败，已停止写入；请检查MySQL备份权限")
    return destination


def _align_initial_dates(report, now):
    """Backdated fixture events must occur after their parent resources exist.

    Called ONLY during the initial seed transaction, never on normal reruns.
    Explicitly preserve updated_at so stale video samples remain recoverable.
    """
    db.session.flush()
    course_ids = list(report["courses"].values())
    user_ids = [row["id"] for row in report["accounts"].values()]
    def update(model, condition, **fields):
        if hasattr(model, "updated_at"):
            fields["updated_at"] = model.updated_at
        db.session.execute(db.update(model).where(condition).values(**fields))
    update(User, User.id.in_(user_ids), created_at=now-timedelta(days=45))
    update(Chapter, Chapter.course_id.in_(course_ids), created_at=now-timedelta(days=14))
    video_ids = list(db.session.scalars(db.select(Video.id).join(Chapter).where(Chapter.course_id.in_(course_ids))))
    update(Video, Video.id.in_(video_ids), created_at=now-timedelta(days=14))
    update(Video, Video.id.in_(report["video_tasks"].values()), created_at=now-timedelta(days=1))
    update(TeachingClass, TeachingClass.id.in_(report["classes"]), created_at=now-timedelta(days=16))
    update(TeachingClassCourse, TeachingClassCourse.class_id.in_(report["classes"]), assigned_at=now-timedelta(days=13))
    requests = TeachingClassJoinRequest.class_id.in_(report["classes"])
    update(TeachingClassJoinRequest, requests & (TeachingClassJoinRequest.status == "APPROVED"), created_at=now-timedelta(days=13), reviewed_at=now-timedelta(days=12))
    update(TeachingClassJoinRequest, requests & TeachingClassJoinRequest.status.in_(["REJECTED", "CANCELLED"]), created_at=now-timedelta(days=2), reviewed_at=now-timedelta(days=1))
    update(TeachingClassJoinRequest, requests & (TeachingClassJoinRequest.status == "PENDING"), created_at=now-timedelta(hours=2))
    homework_ids = [identity for values in report["homeworks"].values() for identity in values]
    update(Homework, Homework.id.in_(homework_ids), created_at=now-timedelta(days=8))
    update(HomeworkSubmission, HomeworkSubmission.homework_id.in_(homework_ids) & HomeworkSubmission.submit_time.is_not(None), created_at=HomeworkSubmission.submit_time)
    exam_ids = [identity for values in report["exams"].values() for identity in values]
    update(Exam, Exam.id.in_(exam_ids), created_at=now-timedelta(days=15))
    update(ExamRecord, ExamRecord.exam_id.in_(exam_ids), created_at=ExamRecord.started_at)
    records = db.session.scalars(db.select(ExamRecord).where(ExamRecord.exam_id.in_(exam_ids))).all()
    for record in records:
        update(ExamAnswer, ExamAnswer.exam_record_id == record.id, created_at=record.submit_time or record.started_at+timedelta(seconds=30))
    update(LearningRecord, LearningRecord.student_id.in_(user_ids), created_at=now-timedelta(days=12))
    update(VideoNote, VideoNote.student_id.in_(user_ids), created_at=now-timedelta(days=2))
    update(Question, Question.student_id.in_(user_ids), created_at=now-timedelta(days=2))
    question_ids = db.select(Question.id).where(Question.student_id.in_(user_ids))
    update(Answer, Answer.question_id.in_(question_ids), created_at=now-timedelta(days=1))
    update(PasswordResetRequest, PasswordResetRequest.student_id.in_(user_ids) & (PasswordResetRequest.status != "PENDING"),
           created_at=now-timedelta(days=2), reviewed_at=now-timedelta(days=1, hours=2), expires_at=now-timedelta(days=1))
    update(Notice, Notice.created_by == report["accounts"]["defense_admin"]["id"], created_at=now-timedelta(days=10))


def seed_demo_data(app, password=None):
    if not (app.testing or app.debug):
        raise RuntimeError("只允许在开发/测试环境建立演示数据，禁止向生产环境写入")
    with app.app_context():
        marker = existing_marker()
        if marker:
            return {**marker.details, "already_exists": True}
        if db.session.scalar(db.select(User.id).where(User.username.like("defense_%")).limit(1)):
            raise RuntimeError("已有同名前缀账号但缺少数据包标记，停止操作以保护已有数据")
        media = Path(app.config["MEDIA_ROOT"]).resolve()
        assets = media / "defense_assets"
        manifest = validate_assets(assets)
        now = utc_now()
        counts = Counter()
        owned_paths = []
        def add(model, **values):
            row = model(**values)
            db.session.add(row)
            db.session.flush()
            counts[model.__name__] += 1
            return row
        def copy(source, relative):
            target = media / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise RuntimeError(f"目标素材已存在，停止覆盖：{relative}")
            owned_paths.append(target)
            shutil.copy2(source, target)
            return relative
        def write(relative, data):
            target = media / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise RuntimeError(f"目标素材已存在，停止覆盖：{relative}")
            owned_paths.append(target)
            with target.open("xb") as stream:
                stream.write(data)
            return relative
        try:
            password_hash = generate_password_hash(password or DEMO_PASSWORD)
            users = {}
            def user(username, name, role, **fields):
                row = add(User, username=username, real_name=name, role=role, password_hash=password_hash, **fields)
                users[username] = row
                return row
            admin = user("defense_admin", "答辩演示管理员", "ADMIN", bio="负责演示平台运维与教学资源监管。")
            teachers = [user(username, name, "TEACHER", teacher_no=f"DFT2026{index+1:02}", email=f"{username}@example.invalid", bio=bio,
                             avatar=copy(assets / f"teacher-{index}.png", f"avatars/defense-teacher-{index}.png"))
                        for index, (username, name, bio) in enumerate(TEACHERS)]
            students = [user(f"defense_student{index+1:02}", name, "STUDENT", student_no=f"DFS2026{index+1:03}",
                             email=f"defense_student{index+1:02}@example.invalid", status=index < 28,
                             bio="正在学习程序设计与大学通识课程，喜欢记录笔记并通过练习巩固知识。")
                        for index, name in enumerate(STUDENT_NAMES)]
            fresh = user("defense_new_student", "新同学何苗", "STUDENT", student_no="DFS2026031", email="defense_new_student@example.invalid", bio="尚未选课，用于现场展示申请入班、教师审批与课程同步。")
            categories = {}
            for name in dict.fromkeys(spec[2] for spec in COURSES):
                row = db.session.scalar(db.select(CourseCategory).where(CourseCategory.name == name))
                categories[name] = row or add(CourseCategory, name=name, description=f"{name}课后辅导与练习", sort_order=len(categories))
            for name, enabled in [("学习方法（演示）", True), ("归档专题（演示）", False)]:
                if not db.session.scalar(db.select(CourseCategory.id).where(CourseCategory.name == name)):
                    add(CourseCategory, name=name, description="无课程分类，用于展示分类管理与启停。", status=enabled, sort_order=20)
            courses, videos = {}, {}
            for key, name, category, teacher_index, status, subjects in COURSES:
                course = add(Course, teacher_id=teachers[teacher_index].id, category_id=categories[category].id, name=name,
                             description=f"围绕{subjects[0]}与{subjects[1]}开展学习、课堂练习和课后答疑。",
                             detail=f"学习目标：理解{subjects[0]}，掌握{subjects[1]}。\n学习建议：先观看章节短片，再记录笔记、完成作业与阶段测验。\n本课程为答辩演示数据，30秒短片为合成素材，不是完整教学录像。",
                             cover=copy(assets / key / "cover.png", f"course_covers/defense-{key}.png"), status=status,
                             published_at=now-timedelta(days=14) if status != "DRAFT" else None, created_at=now-timedelta(days=20))
                courses[key], videos[key] = course, []
                for chapter_index, subject in enumerate(subjects):
                    chapter = add(Chapter, course_id=course.id, title=f"第{chapter_index+1}章 {subject}", description=f"学习{subject}的基础概念与应用。", sort_order=chapter_index)
                    for video_index, kind in enumerate(["概念讲解", "例题与练习"]):
                        video = add(Video, chapter_id=chapter.id, title=f"{subject} · {kind}", original_name=f"{subject}-{kind}.mp4", description="30秒合成教学演示短片，用于验证播放、笔记及进度保存。", sort_order=video_index,
                                    status="READY", process_step="FINISHED", video_codec="h264", audio_codec="aac", frame_rate=15, **manifest["courses"][key])
                        video.original_file = copy(assets / key / "source.mp4", f"videos/original/defense-{video.id}.mp4")
                        video.processed_file = copy(assets / key / "source.mp4", f"videos/processed/{video.id}/video.mp4")
                        hls_target = media / "videos/hls" / str(video.id)
                        if hls_target.exists():
                            raise RuntimeError("视频切片目标已存在，停止覆盖")
                        owned_paths.append(hls_target)
                        shutil.copytree(assets / key / "hls", hls_target)
                        video.hls_path = f"videos/hls/{video.id}/index.m3u8"
                        video.cover = copy(assets / key / "cover.jpg", f"videos/covers/{video.id}.jpg")
                        videos[key].append(video)
            # Shared source templates are never referenced directly by business rows.
            # Every row owns its files so retry/delete cannot break another video.
            diagnostics = add(Chapter, course_id=courses["algorithm"].id, title="视频处理运维样例（演示）", sort_order=2, description="以下状态为演示夹具，不代表正在运行的真实任务。")
            task_ids = {}
            for key, title, status, step, error in [
                ("retry", "可恢复的转码失败（演示）", "FAILED", "TRANSCODING", "演示夹具：编码任务被中断，原始文件有效，可重新转码。"),
                ("pending", "等待超时任务（演示）", "PENDING", "QUEUED", "演示夹具：等待超过30分钟，可人工恢复；尚未投递真实任务。"),
                ("processing", "处理中断任务（演示）", "PROCESSING", "HLS", "演示夹具：处理阶段超过30分钟未更新，可人工恢复。"),
                ("corrupt", "损坏原始文件（演示）", "FAILED", "PROBING", "演示夹具：源文件不是有效视频，重新转码仍会失败，可清理。"),
                ("missing", "原始文件丢失（演示）", "FAILED", "PROBING", "演示夹具：原始文件不存在，不可恢复，只能清理失败条目。"),
            ]:
                video = add(Video, chapter_id=diagnostics.id, title=title, original_name=f"defense-{key}.mp4", status=status, process_step=step, error_message=error, sort_order=len(task_ids), updated_at=now-timedelta(minutes=45))
                video.original_file = f"videos/original/defense-{video.id}.mp4"
                if key == "corrupt":
                    write(video.original_file, b"Synthetic invalid video fixture, not an MP4 container.\n")
                elif key != "missing":
                    copy(assets / "c/source.mp4", video.original_file)
                video.file_size = (media / video.original_file).stat().st_size if key != "missing" else None
                # File-field updates trigger TimestampMixin.onupdate; apply the
                # stale fixture time after flushing, or recovery stays disabled.
                db.session.flush()
                video.updated_at = now-timedelta(minutes=45)
                task_ids[key] = video.id
            classrooms, memberships = [], set()
            def enroll(student, course):
                identity = (student.id, course.id)
                if identity not in memberships:
                    add(CourseStudent, student_id=student.id, course_id=course.id, join_time=now-timedelta(days=12), status=True)
                    memberships.add(identity)
            def classroom(teacher_index, name, cohort, keys):
                row = add(TeachingClass, teacher_id=teachers[teacher_index].id, name=name, description="2026秋季课后辅导班；演示数据，成员与课程关系可现场管理。")
                for key in keys:
                    add(TeachingClassCourse, class_id=row.id, course_id=courses[key].id)
                for student in cohort:
                    add(TeachingClassStudent, class_id=row.id, student_id=student.id, joined_at=now-timedelta(days=12))
                    for key in keys:
                        enroll(student, courses[key])
                classrooms.append(row)
                return row
            for index in range(9):
                cohort = students[:8] if index == 0 else students[8+(index % 4)*4:12+(index % 4)*4]
                keys = ["c", "python", "database"] if index == 0 else ["c", ["web", "python", "database"][index % 3]]
                classroom(0, f"软件技术26级{index+1:02}班（演示）", cohort, keys)
            classroom(1, "高数基础辅导班（演示）", students[:14], ["calculus", "linear"])
            classroom(1, "数学提高班（演示）", students[14:28], ["calculus", "linear"])
            classroom(2, "英语阅读A班（演示）", students[:14], ["english"])
            classroom(2, "英语阅读B班（演示）", students[14:28], ["english"])
            classroom(3, "力学实验辅导班（演示）", students[8:20], ["physics"])
            for index, student, status in [(0, students[0], "APPROVED"), (1, students[0], "PENDING"), (2, students[0], "REJECTED"), (3, students[0], "CANCELLED"), (2, students[1], "PENDING"), (0, students[8], "PENDING")]:
                add(TeachingClassJoinRequest, class_id=classrooms[index].id, student_id=student.id, source_course_id=courses["c"].id, status=status,
                    reviewer_id=teachers[0].id if status in {"APPROVED", "REJECTED"} else None,
                    reviewed_at=now-timedelta(days=1) if status in {"APPROVED", "REJECTED", "CANCELLED"} else None)
            for key in ("c", "python", "web", "english", "physics"):
                add(Favorite, student_id=students[0].id, course_id=courses[key].id)
            add(Favorite, student_id=fresh.id, course_id=courses["c"].id)
            main_progress = {"c": [0.4, 1, 0, 0.65], "python": [0, 0, 0, 0], "database": [1, 1, 1, 1],
                             "calculus": [0.2, 0, 0.4, 0], "linear": [0.8, 0.6, 0, 1], "english": [1, 0.8, 0.5, 0]}
            for student_index, student in enumerate(students[:28]):
                for key, course in courses.items():
                    if (student.id, course.id) not in memberships:
                        continue
                    for video_index, video in enumerate(videos[key]):
                        ratio = main_progress.get(key, [0.4, 1, 0, 0.65])[video_index] if student_index == 0 else ((student_index+video_index) % 6)/5
                        add(LearningRecord, student_id=student.id, video_id=video.id, current_time=round(float(video.duration)*ratio, 3), progress=round(ratio*100, 2),
                            watch_duration=round(float(video.duration)*ratio), status="COMPLETED" if ratio == 1 else "NOT_STARTED" if ratio == 0 else "LEARNING",
                            last_watch_time=now-timedelta(hours=student_index+video_index))
            for index, content in enumerate(["计算平均值时要使用浮点运算，避免整数除法截断。", "输入校验应先于业务计算，非法成绩要给出提示。", "将重复逻辑拆成函数，有利于测试和维护。"]):
                add(VideoNote, student_id=students[0].id, video_id=videos["c"][0].id, video_time=5+index*7, content=content)
            for index, (title, status) in enumerate([("为什么平均分的小数部分丢失了？", "WAITING"), ("scanf输入失败应该怎么处理？", "ANSWERED"), ("变量命名与函数职责如何划分？", "CLOSED")]):
                question = add(Question, student_id=students[0].id, video_id=videos["c"][0].id, video_time=6+index*7, title=title, content="我在练习时遇到这个问题，希望老师结合例子说明。", status=status)
                if status != "WAITING":
                    add(Answer, question_id=question.id, teacher_id=teachers[0].id, content="先检查输入与变量类型，再把步骤拆开验证；例如平均值用总分除以3.0，并检查输入函数返回值。" if index == 1 else "每个函数只承担一个清晰职责，变量名称表达含义，并使用边界测试验证行为。")
            homework_ids, exam_ids = {}, {}
            for key, course in courses.items():
                if course.status != "PUBLISHED":
                    continue
                enrolled = [student for student in students[:28] if (student.id, course.id) in memberships]
                homework_specs = [("知识巩固练习", "PUBLISHED", 365), ("综合应用练习", "PUBLISHED", 365)]
                if key == "c":
                    homework_specs = [("实验一：变量与输入输出", "PUBLISHED", 365), ("实验二：分支与循环", "PUBLISHED", 365), ("实验三：数组统计", "PUBLISHED", 365), ("实验四：函数拆分", "PUBLISHED", 365), ("指针练习（备课草稿）", "DRAFT", 365), ("阶段复盘（已关闭）", "CLOSED", -5), ("补交提醒（已截止）", "PUBLISHED", -2)]
                homework_ids[key] = []
                for index, (title, status, days) in enumerate(homework_specs):
                    homework = add(Homework, course_id=course.id, teacher_id=course.teacher_id, title=title, description=f"结合《{course.name}》完成本次练习，提交解题过程、结果及至少两组测试。评分：正确性40分，过程20分，规范20分，测试20分。", deadline=now+timedelta(days=days), total_score=100, status=status, published_at=now-timedelta(days=7) if status != "DRAFT" else None)
                    homework_ids[key].append(homework.id)
                    filename = ["lab-guide.pdf", "lab-report.txt", "result.png", "source-code.zip"][index % 4] if key == "c" else "instructions.txt"
                    relative = f"homework/{homework.id}/teacher/{filename}"
                    if key == "c":
                        homework.attachment = copy(assets / "attachments" / filename, relative)
                    else:
                        homework.attachment = write(relative, homework.description.encode("utf-8"))
                    if status == "DRAFT":
                        continue
                    for student_index, student in enumerate(enrolled[:8]):
                        if student_index == 0 and index in {0, 6}:
                            continue
                        submission_status = ["DRAFT", "SUBMITTED", "GRADED"][(student_index+index-1) % 3]
                        submission = add(HomeworkSubmission, homework_id=homework.id, student_id=student.id, content="已完成实验设计与测试，记录了步骤、运行结果和边界情况。", status=submission_status,
                                         score=60+(student_index*7+index*3) % 41 if submission_status == "GRADED" else None,
                                         teacher_comment="步骤清晰，结果正确。建议补充非法输入和边界情况的说明。" if submission_status == "GRADED" else None,
                                         submit_time=now-timedelta(days=6 if days < 0 else 1) if submission_status != "DRAFT" else None,
                                         graded_time=now-timedelta(hours=12) if submission_status == "GRADED" else None)
                        submission.attachment = copy(assets / "attachments/lab-report.txt", f"homework/{homework.id}/{student.id}/lab-report.txt") if key == "c" else None
                exam_specs = [("基础知识测验", "PUBLISHED", "active", 30), ("阶段能力测验", "PUBLISHED", "active", 60)]
                if key == "c":
                    exam_specs += [("下周预习测验（未开始）", "PUBLISHED", "future", 30), ("指针专项测验（草稿）", "DRAFT", "active", 30), ("上周总结测验（已关闭）", "CLOSED", "past", 30), ("历史限时测验（已结束）", "PUBLISHED", "past", 30), ("自动交卷体验（1分钟）", "PUBLISHED", "active", 1)]
                exam_ids[key] = []
                for index, (title, status, window, limit) in enumerate(exam_specs):
                    start = now+timedelta(days=7) if window == "future" else now-timedelta(days=14)
                    end = now+timedelta(days=14 if window == "future" else 365) if window != "past" else now-timedelta(days=3)
                    exam = add(Exam, course_id=course.id, teacher_id=course.teacher_id, title=title, description="包含单选题和判断题，每题20分，共100分。作答期间自动保存，交卷后查看结果与正确答案。", status=status, total_score=100, start_time=start, end_time=end, time_limit_minutes=limit, published_at=now-timedelta(days=14) if status != "DRAFT" else None)
                    exam_ids[key].append(exam.id)
                    bank = []
                    for order, (kind, content, options, correct) in enumerate(EXAM_BANKS[key]):
                        bank.append(add(ExamQuestion, exam_id=exam.id, question_type=kind, content=content, correct_answer=correct, score=20, sort_order=order,
                                        **{f"option_{letter}": value for letter, value in zip("abcd", options)}))
                    if status == "DRAFT" or window == "future" or limit == 1:
                        continue
                    for student_index, student in enumerate(enrolled[:6]):
                        if index == 1 and student_index == 0:
                            continue  # Main student can take this exam live.
                        doing = index == 1 and student_index == 1 and window == "active"
                        correct_count = 4 if student_index == 0 else (student_index+index) % 6
                        record = add(ExamRecord, exam_id=exam.id, student_id=student.id, status="DOING" if doing else "SUBMITTED", score=0 if doing else correct_count*20,
                                     correct_count=0 if doing else correct_count, wrong_count=0 if doing else 5-correct_count,
                                     started_at=now-timedelta(minutes=2) if doing else start+timedelta(days=7), submit_time=None if doing else start+timedelta(days=7, minutes=8), duration_seconds=None if doing else 480)
                        for order, question in enumerate(bank[:2] if doing else bank):
                            correct = order < correct_count
                            incorrect = "FALSE" if question.correct_answer == "TRUE" else "TRUE" if question.question_type == "JUDGE" else "D" if question.correct_answer != "D" else "A"
                            add(ExamAnswer, exam_record_id=record.id, question_id=question.id, student_answer=question.correct_answer if correct or doing else incorrect, is_correct=correct and not doing, score=20 if correct and not doing else 0)
            for student, status, reviewer in [(students[2], "PENDING", None), (students[3], "REJECTED", teachers[0].id), (students[4], "APPROVED", teachers[0].id)]:
                add(PasswordResetRequest, student_id=student.id, requested_password_hash=generate_password_hash(RESET_PASSWORD) if status == "PENDING" else password_hash,
                    status=status, reviewer_id=reviewer, reviewed_at=now-timedelta(days=1) if reviewer else None, expires_at=now+timedelta(hours=24))
            for index, (title, status) in enumerate([("2026秋季学习安排（演示）", "PUBLISHED"), ("作业与测验提交说明（演示）", "PUBLISHED"), ("课程视频观看与断网补传（演示）", "PUBLISHED"), ("入班申请与密码找回说明（演示）", "PUBLISHED"), ("阶段教学计划（公告草稿）", "DRAFT"), ("上学期维护通知（已下线）", "OFFLINE")]):
                add(Notice, created_by=admin.id, title=title, content="请先申请加入课程关联班级，教师审批后同步课程。学习中可记录笔记和提问，作业支持附件预览与下载，测验答案自动保存。密码找回由班级教师审批。此公告是虚构答辩演示资料。", status=status, publish_time=now-timedelta(days=index) if status != "DRAFT" else None)
            notification_specs = [
                ("COURSE", "课程已同步至我的学习", "你的班级已关联C语言、Python与数据库课程。", "/learning"),
                ("CLASS", "入班申请等待审批", "软件技术26级02班的申请等待教师审核。", "/classes"),
                ("HOMEWORK", "实验一待完成", "请查看实验指导PDF，完成变量与输入输出实验。", "/homeworks"),
                ("HOMEWORK", "实验四已评分", "老师已批改实验四，请查看分数和评语。", "/homeworks"),
                ("EXAM", "基础知识测验结果已生成", "你已完成基础测验，可以查看错题和正确答案。", "/exams"),
                ("QUESTION", "老师回复了你的提问", "关于输入失败处理的问题已有回复。", f"/courses/{courses['c'].id}"),
                ("PASSWORD", "密码找回流程说明", "如忘记密码，可提交申请，由所属班级教师审批。", "/notifications"),
                ("SYSTEM", "欢迎使用课后辅导平台", "点击右上角头像可以编辑个人简介与资料。", "/profile"),
            ]
            for index, (category, title, content, link) in enumerate(notification_specs):
                add(Notification, recipient_id=students[0].id, sender_id=teachers[0].id, category=category, title=title, content=content, link=link,
                    created_at=now-timedelta(hours=index), read_at=now-timedelta(minutes=20) if index % 3 == 0 else None)
            for index, student in enumerate(students[1:28]):
                add(Notification, recipient_id=student.id, sender_id=teachers[0].id, category="SYSTEM", title="秋季学习安排", content="请按班级课程安排完成学习，遇到问题可向授课教师提问。", link="/learning", read_at=now if index % 2 else None)
            for category, title, content, link in [("CLASS", "有3条入班申请待处理", "请进入对应班级审核学生申请。", "/classes"), ("PASSWORD", "王子涵申请重置密码", "在班级管理的密码重置申请区域审核，批准后新密码生效。", "/classes"), ("QUESTION", "李晨有新的课程提问", "关于平均值计算的问题需要回复。", "/teacher/questions"), ("HOMEWORK", "有作业等待批改", "学生已提交实验报告，请查看正文与附件。", "/homeworks")]:
                add(Notification, recipient_id=teachers[0].id, sender_id=students[0].id if category != "PASSWORD" else students[2].id, category=category, title=title, content=content, link=link)
            for teacher in teachers[1:]:
                add(Notification, recipient_id=teacher.id, sender_id=admin.id, category="SYSTEM", title="秋季教学资源已准备", content="请查看自己的班级、课程、作业和测验。", link="/teacher/courses")
            add(Notification, recipient_id=admin.id, category="SYSTEM", title="视频处理演示样例已准备", content="视频处理中心包含可恢复、超时、源文件损坏及丢失样例；所有异常状态均为演示夹具。", link="/admin")
            for action, kind, identity, summary in [("USER_CREATE", "USER", teachers[0].id, "建立教师教学账号"), ("USER_STATUS_CHANGE", "USER", students[29].id, "禁用演示学生账号"), ("COURSE_STATUS_CHANGE", "COURSE", courses["linux"].id, "课程下线待修订"), ("NOTICE_CREATE", "NOTICE", None, "准备秋季教学公告"), ("VIDEO_RETRY", "VIDEO", task_ids["retry"], "视频恢复操作样例（非真实执行记录）")]:
                add(AdminAuditLog, admin_id=admin.id, action=action, resource_type=kind, resource_id=identity, summary="演示历史："+summary, details={"demo_fixture": True}, ip_address="127.0.0.1", user_agent="defense-demo-fixture")
            report = {"version": 1, "generated_at": now.isoformat()+"Z", "counts": dict(counts),
                      "accounts": {username: {"id": row.id, "name": row.real_name, "role": row.role} for username, row in users.items()},
                      "courses": {key: row.id for key, row in courses.items()}, "classes": [row.id for row in classrooms], "video_tasks": task_ids,
                      "homeworks": homework_ids, "exams": exam_ids}
            _align_initial_dates(report, now)
            add(AdminAuditLog, admin_id=admin.id, action="DEMO_SEED", resource_type="SYSTEM", summary=SEED_MARKER, details=report, ip_address="127.0.0.1")
            db.session.commit()
            return {**report, "already_exists": False}
        except Exception:
            db.session.rollback()
            # Only paths created by this transaction, never existing user media.
            for path in reversed(owned_paths):
                resolved = path.resolve()
                if resolved == media or not resolved.is_relative_to(media):
                    continue
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                elif resolved.is_file():
                    resolved.unlink()
            raise


def check_demo(app):
    """Read-only checks against real serializers and permission-filtered services."""
    from app.services.class_service import list_course_class_options, list_student_class_join_requests
    from app.services.homework_service import list_student_homeworks
    from app.services.exam_service import list_student_exams
    from app.services.admin_service import serialize_admin_video
    with app.app_context():
        marker = existing_marker()
        if not marker:
            raise RuntimeError("尚未建立演示数据")
        report = marker.details
        student_id = report["accounts"]["defense_student01"]["id"]
        options = list_course_class_options(report["courses"]["c"], student_id)
        assert any(item["joined"] for item in options)
        assert any(item["request_status"] == "PENDING" for item in options)
        assert {item["status"] for item in list_student_class_join_requests(student_id)} >= {"APPROVED", "PENDING", "REJECTED", "CANCELLED"}
        assert len(list_student_homeworks(student_id)) >= 10
        assert len(list_student_exams(student_id)) >= 10
        files = 0
        for course_id in report["courses"].values():
            for video in db.session.scalars(db.select(Video).join(Chapter).where(Chapter.course_id == course_id, Video.status == "READY")):
                for relative in (video.original_file, video.processed_file, video.hls_path, video.cover):
                    assert (Path(app.config["MEDIA_ROOT"]) / relative).is_file(), f"缺少媒体文件：{relative}"
                    files += 1
        retry = serialize_admin_video(db.session.get(Video, report["video_tasks"]["retry"]))
        assert retry["retryable"] and retry["removable"]
        for key in ("pending", "processing"):
            assert serialize_admin_video(db.session.get(Video, report["video_tasks"][key]))["retryable"]
        missing = serialize_admin_video(db.session.get(Video, report["video_tasks"]["missing"]))
        assert not missing["original_exists"] and not missing["retryable"] and missing["removable"]
        return {"checked_media_paths": files, "class_options": len(options), "homeworks": len(list_student_homeworks(student_id)), "exams": len(list_student_exams(student_id))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="安全新增毕业答辩数据；重复运行不重置演示操作")
    parser.add_argument("--check", action="store_true", help="只读验证，不生成数据或备份")
    args = parser.parse_args()
    application = create_app()
    if not application.debug:
        raise RuntimeError("演示初始化CLI仅允许开发环境")
    if args.check:
        print(json.dumps(check_demo(application), ensure_ascii=False, indent=2))
    else:
        with application.app_context():
            already_exists = existing_marker() is not None
            if not already_exists:
                validate_assets(Path(application.config["MEDIA_ROOT"]) / "defense_assets")
                backup = backup_mysql(application)
                print("写入前SQL备份：", backup, flush=True)
        report = seed_demo_data(application, os.getenv("DEFENSE_DEMO_PASSWORD") or DEMO_PASSWORD)
        (Path(__file__).resolve().parents[1] / "demo-data-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("数据包已存在，未重复写入。" if report["already_exists"] else "演示数据已建立，原有账号和数据未修改。")
        print(json.dumps({"counts": report["counts"], "courses": report["courses"], "video_tasks": report["video_tasks"]}, ensure_ascii=False, indent=2))

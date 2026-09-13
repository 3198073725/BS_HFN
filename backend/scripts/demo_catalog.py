"""Fictional, local-only graduation defense scenarios (no real personal data)."""

DEMO_PASSWORD = "Defense123!"
RESET_PASSWORD = "DemoReset123!"
SEED_MARKER = "毕业答辩演示数据 v1"
TEACHERS = [
    ("defense_teacher", "陈明", "计算机课程教师，关注程序设计、数据库与 Web 开发。"),
    ("defense_math_teacher", "周岚", "数学课程教师，擅长用例题解释微积分与线性代数。"),
    ("defense_english_teacher", "林悦", "英语课程教师，关注学术阅读、词汇积累与口语表达。"),
    ("defense_physics_teacher", "王远", "物理课程教师，重视实验观察与物理模型的结合。"),
]
STUDENT_NAMES = [
    "李晨", "张雨桐", "王子涵", "赵一航", "刘欣然", "陈宇", "杨思远", "黄佳宁",
    "周浩", "吴雨晴", "徐嘉诚", "孙若溪", "胡俊杰", "朱可欣", "高博文", "林语",
    "何书豪", "郭晓彤", "马泽宇", "罗诗涵", "梁奕辰", "宋嘉怡", "郑天佑", "谢安然",
    "唐逸凡", "韩沐阳", "曹宁", "许星辰", "邓可", "萧林",
]
# key, name, category, teacher index, status, two chapter subjects
COURSES = [
    ("c", "C语言程序设计 · 从入门到实践", "计算机", 0, "PUBLISHED", ["变量与输入输出", "分支、循环与函数"]),
    ("python", "Python数据分析基础", "计算机", 0, "PUBLISHED", ["列表与字典", "数据清洗与汇总"]),
    ("database", "数据库原理与SQL实践", "计算机", 0, "PUBLISHED", ["关系模型与主外键", "查询与事务"]),
    ("web", "Web前端开发实训", "计算机", 0, "PUBLISHED", ["语义化页面与表单", "组件与接口交互"]),
    ("calculus", "高等数学 · 极限与导数", "数学", 1, "PUBLISHED", ["函数极限", "导数的几何意义"]),
    ("linear", "线性代数 · 矩阵与方程组", "数学", 1, "PUBLISHED", ["矩阵运算", "线性方程组"]),
    ("english", "大学英语阅读与学术词汇", "英语", 2, "PUBLISHED", ["阅读策略", "学术词汇积累"]),
    ("physics", "大学物理 · 力学实验入门", "物理", 3, "PUBLISHED", ["运动与受力", "实验误差分析"]),
    ("algorithm", "数据结构与算法（备课草稿）", "计算机", 0, "DRAFT", ["顺序表与链表", "查找与排序"]),
    ("speaking", "英语口语表达（备课草稿）", "英语", 2, "DRAFT", ["自我介绍", "课堂讨论"]),
    ("linux", "Linux系统基础（已下线待修订）", "计算机", 0, "OFFLINE", ["文件与权限", "进程与服务"]),
    ("probability", "概率论基础（已下线待修订）", "数学", 1, "OFFLINE", ["随机事件", "条件概率"]),
]

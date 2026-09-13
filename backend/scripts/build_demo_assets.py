"""Build original educational demo media, using the optional artifact runtime.

Run with the bundled Python (Pillow/reportlab), not the application's venv.
The seed script itself needs only the project's existing dependencies.
"""
import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from scripts.demo_catalog import COURSES, TEACHERS


def font(size):
    candidates = [Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    raise RuntimeError("缺少绘制演示图片所需的字体，请配置中文字体")


def draw_slide(path, name, category, subjects):
    image = Image.new("RGB", (960, 540), "#f3f0e9")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 24, 540), fill="#315769")
    draw.text((66, 52), "课后辅导教学平台  /  " + category, font=font(22), fill="#627581")
    # Keep long course titles inside the slide.
    title_font = font(38 if len(name) <= 19 else 30)
    draw.text((64, 119), name, font=title_font, fill="#203540")
    draw.line((66, 199, 892, 199), fill="#c3cdc9", width=2)
    for index, subject in enumerate(subjects):
        draw.text((66, 240 + index * 81), f"0{index + 1}", font=font(25), fill="#315769")
        draw.text((125, 237 + index * 81), subject, font=font(30), fill="#334650")
    draw.text((66, 459), "答辩演示短片 · 合成教学素材 · 非完整课程录像", font=font(19), fill="#71818a")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def create_pdf(path):
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    title = ParagraphStyle("title", fontName="STSong-Light", fontSize=22, leading=30, textColor=colors.HexColor("#203540"))
    body = ParagraphStyle("body", fontName="STSong-Light", fontSize=11.5, leading=22, spaceAfter=12, wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=body, fontSize=15, leading=24, textColor=colors.HexColor("#315769"))
    path.parent.mkdir(parents=True, exist_ok=True)
    story = [Paragraph("实验一：变量与输入输出", title), Spacer(1, 12),
             Paragraph("C语言程序设计 | 学生实验指导 | 答辩演示附件", body)]
    sections = [
        ("一、实验目标", "理解整数与浮点数的基本类型；掌握输入、运算和格式化输出；能够解释程序中的关键语句。"),
        ("二、实验任务", "输入三门课程的成绩，计算总分与平均分。平均分保留两位小数；输入范围为0至100。"),
        ("三、示例输入与输出", "输入：85 90 88<br/>输出：总分263，平均分87.67。"),
        ("四、提交要求", "提交程序源文件和实验报告。<br/>报告包含实验步骤、运行结果、至少两组边界测试以及问题总结。"),
        ("五、评分说明", "功能正确40分；输入校验20分；代码规范20分；报告与测试20分。<br/>请独立完成，避免直接复制答案。"),
        ("六、检查清单", "检查整数除法、非法输入和变量名称。报告中的结果是否与程序一致？"),
    ]
    for text, content in sections:
        story += [Paragraph(text, heading), Paragraph(content, body)]
    def footer(canvas, _doc):
        canvas.setFont("STSong-Light", 9)
        canvas.setFillColor(colors.HexColor("#71818a"))
        canvas.drawString(48, 30, "本附件为虚构教学演示资料，无真实个人信息。")
        canvas.drawRightString(A4[0] - 48, 30, str(canvas.getPageNumber()))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=42, bottomMargin=48).build(story, onFirstPage=footer, onLaterPages=footer)


def run(command):
    subprocess.run(command, check=True, capture_output=True, timeout=120)


def build_assets(root, ffmpeg, ffprobe, pdf_output):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"courses": {}}
    for key, name, category, _teacher, _status, subjects in COURSES:
        directory = root / key
        directory.mkdir(exist_ok=True)
        poster, source = directory / "cover.png", directory / "source.mp4"
        if not poster.exists():
            draw_slide(poster, name, category, subjects)
        Image.open(poster).convert("RGB").save(directory / "cover.jpg", quality=90)
        if not source.exists():
            run([ffmpeg, "-y", "-loop", "1", "-framerate", "15", "-i", str(poster),
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                 "-t", "30", "-vf", "drawbox=x=64:y=512:w=832:h=4:color=0x315769:t=fill",
                 "-af", "volume=0.015", "-c:v", "libx264", "-preset", "ultrafast",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(source)])
        hls = directory / "hls"
        hls.mkdir(exist_ok=True)
        if not (hls / "index.m3u8").exists():
            run([ffmpeg, "-y", "-i", str(source), "-c", "copy", "-f", "hls",
                 "-hls_time", "6", "-hls_playlist_type", "vod", "-hls_segment_filename",
                 str(hls / "segment_%05d.ts"), str(hls / "index.m3u8")])
        metadata = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)], timeout=30))
        video_stream = next(item for item in metadata["streams"] if item["codec_type"] == "video")
        manifest["courses"][key] = {"duration": float(metadata["format"]["duration"]),
                                     "width": video_stream["width"], "height": video_stream["height"],
                                     "file_size": source.stat().st_size}
        print("媒体素材完成：", name, flush=True)
    attachments = root / "attachments"
    attachments.mkdir(exist_ok=True)
    create_pdf(pdf_output)
    shutil.copy2(pdf_output, attachments / "lab-guide.pdf")
    (attachments / "lab-report.txt").write_text("实验报告：分支与循环\n学生：答辩演示学生\n实验过程：设计循环，计算1到100的和。\n结果：5050。\n测试：输入0、1和100，检查边界处理。\n思考：循环变量应如何初始化？\n", encoding="utf-8")
    draw_slide(attachments / "result.png", "实验运行结果与测试记录", "计算机", ["输入：85 90 88", "输出：总分263，平均分87.67"])
    with zipfile.ZipFile(attachments / "source-code.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.c", "#include <stdio.h>\nint main(void) { int sum=0; for(int i=1;i<=100;i++) sum+=i; printf(\"%d\\n\", sum); return 0; }\n")
        archive.writestr("README.txt", "Synthetic defense fixture. Compile main.c with a C99 compiler.\n")
    for index, (_username, name, _bio) in enumerate(TEACHERS):
        avatar = Image.new("RGB", (160, 160), ["#315769", "#636955", "#786655", "#586777"][index])
        ImageDraw.Draw(avatar).text((47, 38), name[0], font=font(66), fill="white")
        avatar.save(root / f"teacher-{index}.png")
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成答辩课程封面、短片及作业附件")
    parser.add_argument("--output", type=Path, default=Path("media/defense_assets"))
    parser.add_argument("--ffmpeg", default="../tools/ffmpeg/bin/ffmpeg.exe")
    parser.add_argument("--ffprobe", default="../tools/ffmpeg/bin/ffprobe.exe")
    parser.add_argument("--pdf-output", type=Path, default=Path("../output/pdf/defense-lab-guide.pdf"))
    args = parser.parse_args()
    build_assets(args.output.resolve(), args.ffmpeg, args.ffprobe, args.pdf_output.resolve())

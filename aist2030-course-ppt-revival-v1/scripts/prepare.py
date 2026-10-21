#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prepare.py —— 老旧课程 PPT 复活 · 第 0 步「输入适配」

把各种格式的原始素材统一转成标准 .pptx，再交给 analyze → plan → apply → export 主流程。

支持：
    .pptx   原生，直接复制（可用于统一页面尺寸）
    .pdf    每页渲染为图片（保留原稿设计），可选是否把提取文本写入页面
    .docx   按标题分级切页（需 python-docx）
    .md/.txt 按 # / ## 标题切页
    图片    单图或图片目录，每图一页
    .ppt/.doc 老式二进制：给出明确转换指引（需 WPS / LibreOffice 另存）

用法：
    python prepare.py 发布会.pdf -o 课件.pptx -w work
    python prepare.py 讲义.docx -o 课件.pptx
    python prepare.py ./图片目录 -o 课件.pptx --dpi 120
    python prepare.py 发布会.pdf -o 课件.pptx --with-text   # 把提取文本也写进页面（默认不写）

退出码：
    0 成功 | 2 文件/目录不存在 | 9 缺少可选依赖
"""

import argparse
import json
import os
import shutil
import sys

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
except ImportError:
    sys.stderr.write("[prepare] 缺少 python-pptx，请先 pip install python-pptx\n")
    sys.exit(1)

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_MISSING_DEP = 9

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def fail(code, message, hint=""):
    sys.stderr.write(json.dumps(
        {"ok": False, "code": code, "message": message, "hint": hint},
        ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def new_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def add_text_slide(prs, title, bodies, font_name="微软雅黑"):
    """统一的文本页：标题 + 若干正文段"""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    if title:
        tb = s.shapes.add_textbox(Inches(0.75), Inches(0.6), Inches(11.8), Inches(1.0))
        tf = tb.text_frame
        tf.text = title
        for para in tf.paragraphs:
            for run in para.runs:
                run.font.name = font_name
                run.font.size = Pt(32)
                run.font.bold = True
    y = 1.9
    for b in bodies:
        if not b:
            continue
        box = s.shapes.add_textbox(Inches(0.75), Inches(y), Inches(11.8), Inches(0.8))
        box.text_frame.word_wrap = True
        box.text_frame.text = b
        for para in box.text_frame.paragraphs:
            for run in para.runs:
                run.font.name = font_name
                run.font.size = Pt(18)
        y += 1.1
    return s


# ==================== 各格式转换 ====================

def from_pptx(src, out, prs_size=True):
    if prs_size:
        prs = Presentation(src)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        prs.save(out)
    else:
        shutil.copyfile(src, out)
    return len(Presentation(out).slides.__iter__.__self__._sldIdLst)


def from_pdf(src, out, dpi=100, with_text=False, workdir="work"):
    try:
        import fitz
    except ImportError:
        fail(EXIT_MISSING_DEP, "转换 PDF 需要 PyMuPDF", "请执行 pip install pymupdf")

    os.makedirs(workdir, exist_ok=True)
    prs = new_deck()
    doc = fitz.open(src)
    tmp_imgs = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        img_path = os.path.join(workdir, "_page_%03d.png" % (i + 1))
        pix.save(img_path)
        tmp_imgs.append(img_path)

        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_picture(img_path, 0, 0, prs.slide_width, prs.slide_height)

        if with_text:
            txt = page.get_text().strip().replace("\n", " / ")
            if txt:
                tb = s.shapes.add_textbox(Inches(0.4), Inches(6.35), Inches(12.5), Inches(0.9))
                tb.text_frame.word_wrap = True
                tb.text_frame.text = txt[:180]
                for para in tb.text_frame.paragraphs:
                    for run in para.runs:
                        run.font.name = "微软雅黑"
                        run.font.size = Pt(14)

    prs.save(out)
    # 清理临时渲染图
    for p in tmp_imgs:
        try:
            os.remove(p)
        except Exception:
            pass
    return len(doc)


def from_docx(src, out):
    try:
        import docx
    except ImportError:
        fail(EXIT_MISSING_DEP, "转换 docx 需要 python-docx", "请执行 pip install python-docx")

    d = docx.Document(src)
    prs = new_deck()
    title, bodies, n = "", [], 0
    CHUNK = 5  # 每页最多 5 段正文

    def flush():
        nonlocal title, bodies, n
        if title or bodies:
            add_text_slide(prs, title, bodies)
            n += 1
        title, bodies = "", []

    for p in d.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower()
        if style.startswith("heading") or style.startswith("标题"):
            flush()
            title = text
        else:
            bodies.append(text)
            if len(bodies) >= CHUNK:
                flush()
    flush()
    if n == 0:
        fail(EXIT_BAD_INPUT, "docx 中没有可读正文", "请确认文件内容")
    prs.save(out)
    return n


def from_text(src, out):
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip() for ln in f]
    prs = new_deck()
    title, bodies, n = "", [], 0

    def flush():
        nonlocal title, bodies, n
        if title or bodies:
            add_text_slide(prs, title, bodies)
            n += 1
        title, bodies = "", []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            flush()
            title = s.lstrip("#").strip()
        else:
            bodies.append(s)
            if len(bodies) >= 5:
                flush()
    flush()
    if n == 0:
        fail(EXIT_BAD_INPUT, "文本文件中没有可读内容", "请确认文件内容")
    prs.save(out)
    return n


def from_images(src, out):
    if os.path.isdir(src):
        files = sorted([os.path.join(src, f) for f in os.listdir(src)
                        if os.path.splitext(f)[1].lower() in IMG_EXT])
    else:
        files = [src]
    if not files:
        fail(EXIT_BAD_INPUT, "未找到可用图片", "请确认目录内含 png/jpg 等图片")
    prs = new_deck()
    for f in files:
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_picture(f, 0, 0, prs.slide_width, prs.slide_height)
    prs.save(out)
    return len(files)


def main():
    ap = argparse.ArgumentParser(description="把各种格式的素材统一转成标准 PPTX")
    ap.add_argument("input", help="原始素材：文件（pdf/docx/md/txt/pptx/图片）或图片目录")
    ap.add_argument("-o", "--output", default=None, help="输出 PPTX 路径")
    ap.add_argument("-w", "--workdir", default="work", help="工作目录（PDF 渲染临时图）")
    ap.add_argument("--dpi", type=int, default=100, help="PDF 渲染清晰度（默认 100）")
    ap.add_argument("--with-text", action="store_true",
                    help="PDF 转换时把提取文本也写入页面（默认不写，保持原稿设计）")
    args = ap.parse_args()

    src = args.input
    if not os.path.exists(src):
        fail(EXIT_BAD_INPUT, "文件或目录不存在：%s" % src, "请确认路径")

    out = args.output or os.path.join(args.workdir, "prepared.pptx")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    except Exception as e:
        fail(EXIT_BAD_INPUT, "输出目录无法创建：%s" % e, "请更换输出路径")

    ext = os.path.splitext(src)[1].lower() if os.path.isfile(src) else ""

    if ext == ".pptx":
        n = from_pptx(src, out)
        kind = "pptx（原样沿用，仅统一页面尺寸）"
    elif ext == ".pdf":
        n = from_pdf(src, out, dpi=args.dpi, with_text=args.with_text, workdir=args.workdir)
        kind = "pdf → pptx（每页渲染为图%s）" % ("，含提取文本" if args.with_text else "，不改原稿设计")
    elif ext == ".docx":
        n = from_docx(src, out)
        kind = "docx → pptx（按标题切页）"
    elif ext in (".md", ".markdown", ".txt"):
        n = from_text(src, out)
        kind = "文本 → pptx（按 # 标题切页）"
    elif ext in IMG_EXT:
        n = from_images(src, out)
        kind = "图片 → pptx（每图一页）"
    elif os.path.isdir(src):
        n = from_images(src, out)
        kind = "图片目录 → pptx（每图一页）"
    elif ext in (".ppt", ".doc"):
        fail(EXIT_BAD_INPUT, "老式二进制格式 %s 无法直接解析" % ext,
             "请用 WPS 或 PowerPoint 打开后另存为 .pptx / .docx，再重新运行")
    else:
        fail(EXIT_BAD_INPUT, "暂不支持的格式：%s" % (ext or "目录"),
             "支持：pptx / pdf / docx / md / txt / 图片或图片目录")

    report = {"ok": True, "source": os.path.abspath(src), "output": os.path.abspath(out),
              "kind": kind, "slideCount": n}
    rp = os.path.join(args.workdir, "prepare-report.json")
    try:
        os.makedirs(args.workdir, exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        rp = None

    sys.stderr.write("[prepare] %s\n" % kind)
    sys.stderr.write("[prepare] 已生成 %d 页：%s\n" % (n, out))
    if rp:
        sys.stderr.write("[prepare] 转换报告：%s\n" % rp)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()

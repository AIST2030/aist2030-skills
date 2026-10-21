#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
apply.py —— 老旧课程 PPT 复活 · 第三步「应用」（v1.1 排版引擎版）

按 plan.json 做三件事：
  1. 版式统一（字体 / 字号分档 / 配色）
  2. **版面规整**（页面类型识别 → 版心统一、标题区与正文区分层、行距段距、
     底部说明条统一、文本溢出自动降档）
  3. 写入每页讲解备注，并执行**已声明**的文本替换

铁律：除 plan 中显式声明的 replacements / titleFix 外，不改动任何正文文本。

用法：
    python apply.py 老课件.pptx --plan work/plan.json -o 优化后.pptx -w work/

退出码：
    0 成功 | 2 文件问题 | 3 损坏 | 4 加密/旧格式 | 5 空文档
    7 plan 校验失败 | 8 写出失败
"""

import argparse
import json
import math
import os
import sys

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.enum.text import PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Pt
except ImportError:
    sys.stderr.write("[apply] 缺少 python-pptx，请先 pip install python-pptx\n")
    sys.exit(1)

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_PARSE_FAILED = 3
EXIT_ENCRYPTED = 4
EXIT_EMPTY = 5
EXIT_BAD_PLAN = 7
EXIT_WRITE_FAILED = 8

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# 原字号 >= 该值视为标题级，映射到 style.titleSizePt；否则映射到 bodySizePt
TITLE_SIZE_THRESHOLD = 24

DEFAULT_STYLE = {
    "fontName": "微软雅黑",
    "titleSizePt": 32,
    "bodySizePt": 18,
    "noteSizePt": 14,
    "titleColor": "1F2A44",
    "bodyColor": "333333",
    "accentColor": "C8A45C",
}

DEFAULT_LAYOUT = {
    "mode": "auto",          # auto（按页面类型自动）/ tidy（强制规整）/ keep（不动版式）
    "marginPt": 54,
    "titleHeightPt": 72,
    "titleGapPt": 20,
    "bodyGapPt": 14,
    "lineSpacing": 1.25,
    "spaceAfterPt": 8,
    "bandHeightPt": 48,
    "bandFill": "F5F6F8",
}


# 行业风格预设（页面侧：配色 / 字体 / 字号档位）
# 口播侧（称呼、语气、节奏）见 SKILL.md「行业风格预设」章节，由模型按行业撰写讲稿。
# 字体一律选自 Windows 常见字体，避免缺失导致回退。
INDUSTRY_PRESETS = {
    "通用商务": {"fontName": "微软雅黑", "titleColor": "1F2A44", "bodyColor": "333333",
                "accentColor": "C8A45C", "titleSizePt": 32, "bodySizePt": 18},
    "发布会": {"fontName": "微软雅黑", "titleColor": "12233A", "bodyColor": "2B2B2B",
              "accentColor": "C8A45C", "titleSizePt": 36, "bodySizePt": 18},
    "教育培训": {"fontName": "微软雅黑", "titleColor": "1B5E7E", "bodyColor": "333333",
                "accentColor": "E8A33D", "titleSizePt": 34, "bodySizePt": 20},
    "金融保险": {"fontName": "微软雅黑", "titleColor": "0F2B5B", "bodyColor": "222222",
                "accentColor": "B08D57", "titleSizePt": 32, "bodySizePt": 18},
    "医疗健康": {"fontName": "微软雅黑", "titleColor": "0E7C6B", "bodyColor": "333333",
                "accentColor": "4FB3A0", "titleSizePt": 32, "bodySizePt": 18},
    "政务国企": {"fontName": "黑体", "titleColor": "9E1F19", "bodyColor": "222222",
                "accentColor": "C8A45C", "titleSizePt": 32, "bodySizePt": 18},
    "零售餐饮": {"fontName": "微软雅黑", "titleColor": "B03A2E", "bodyColor": "333333",
                "accentColor": "E67E22", "titleSizePt": 34, "bodySizePt": 20},
    "科技互联网": {"fontName": "微软雅黑", "titleColor": "0B1E3D", "bodyColor": "333333",
                 "accentColor": "2E86DE", "titleSizePt": 32, "bodySizePt": 18},
    "制造业": {"fontName": "微软雅黑", "titleColor": "1C3F5F", "bodyColor": "333333",
              "accentColor": "F39C12", "titleSizePt": 32, "bodySizePt": 18},
    "文化传媒": {"fontName": "微软雅黑", "titleColor": "4A235A", "bodyColor": "333333",
                "accentColor": "D980FA", "titleSizePt": 34, "bodySizePt": 18},
}

DEFAULT_INDUSTRY = "通用商务"

# 行业版式微调（留白 / 标题区高度 / 行距）。未列出的行业沿用 DEFAULT_LAYOUT。
INDUSTRY_LAYOUT = {
    "发布会": {"marginPt": 60, "titleHeightPt": 96, "lineSpacing": 1.3},
    "教育培训": {"marginPt": 52, "titleHeightPt": 80, "bodyGapPt": 16, "lineSpacing": 1.3},
    "政务国企": {"marginPt": 56, "titleHeightPt": 84, "lineSpacing": 1.35},
    "零售餐饮": {"marginPt": 50, "titleHeightPt": 80, "lineSpacing": 1.3},
    "文化传媒": {"marginPt": 48, "titleHeightPt": 88, "lineSpacing": 1.28},
}

# 行业口播基调（供模型撰写讲稿时对齐；脚本侧只做记录，不改文本）
INDUSTRY_TONE = {
    "通用商务": "稳健专业，称呼用「各位 / 大家」，结论先行，数据说话",
    "发布会": "有节奏的铺垫与释放，称呼用「各位朋友」，多用「接下来你会看到」制造期待",
    "教育培训": "亲切耐心，称呼用「同学 / 大家」，多提问、多举例、给可操作步骤",
    "金融保险": "审慎合规，称呼用「各位客户」，强调风险提示，禁用收益承诺与极限词",
    "医疗健康": "严谨温和，称呼用「各位朋友」，强调个体差异、遵医嘱，禁用疗效承诺",
    "政务国企": "庄重规范，称呼用「各位同志」，用语书面化，避免网络化表达",
    "零售餐饮": "热情明快，称呼用「各位老板 / 各位伙伴」，多讲场景与实操",
    "科技互联网": "轻快前沿，称呼用「大家」，可适度用行业术语但要口头解释",
    "制造业": "务实落地，称呼用「各位同事」，强调流程、标准、安全",
    "文化传媒": "有画面感，称呼用「大家」，多用故事与细节描述",
}


def fail(code, message, hint=""):
    sys.stderr.write(json.dumps(
        {"ok": False, "code": code, "message": message, "hint": hint},
        ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


# ==================== 遍历 ====================

def iter_shapes(shapes):
    for sh in shapes:
        try:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                for sub in iter_shapes(sh.shapes):
                    yield sub
                continue
        except Exception:
            pass
        yield sh


def iter_text_units(shapes):
    """递归产出 (shape, paragraph)，覆盖组合形状与表格单元格"""
    for sh in iter_shapes(shapes):
        try:
            if getattr(sh, "has_table", False):
                for row in sh.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            yield sh, para
                continue
        except Exception:
            pass
        try:
            if getattr(sh, "has_text_frame", False):
                for para in sh.text_frame.paragraphs:
                    yield sh, para
        except Exception:
            pass


def text_shapes(shapes):
    """页面上真正有文字的文本框（不含表格）"""
    out = []
    for sh in iter_shapes(shapes):
        try:
            if getattr(sh, "has_table", False):
                continue
            if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
                out.append(sh)
        except Exception:
            pass
    return out


# ==================== 样式 ====================

def set_east_asian_font(run, font_name):
    """python-pptx 的 font.name 只写 latin；中文实际走 a:ea，必须一并设置"""
    run.font.name = font_name
    rPr = run.font._rPr
    # 顺序要求：a:latin → a:ea → a:cs（先插 cs 再插 ea，都用 latin.addnext 才不会反）
    for tag in ("a:cs", "a:ea"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            latin = rPr.find(qn("a:latin"))
            if latin is not None:
                latin.addnext(el)
            else:
                rPr.append(el)
        el.set("typeface", font_name)


def replace_in_paragraph(para, old, new):
    """跨 run 安全替换：合并文本替换后写回首个 run，清空其余 run（保留首个 run 格式）"""
    runs = para.runs
    if not runs:
        return False
    full = "".join(r.text for r in runs)
    if old not in full:
        return False
    runs[0].text = full.replace(old, new)
    for r in runs[1:]:
        r.text = ""
    return True


# ==================== 版面规整 ====================

def classify_slide(slide, prs):
    """页面类型：图片占比高 → design（设计稿型，只规整文字条）；否则 text（文本型，整版规整）"""
    W, H = prs.slide_width, prs.slide_height
    pic_area = 0
    for sh in iter_shapes(slide.shapes):
        try:
            if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                pic_area += (sh.width or 0) * (sh.height or 0)
        except Exception:
            pass
    total = float((W or 1) * (H or 1))
    return "design" if total and pic_area / total >= 0.55 else "text"


def estimate_height_emu(width_emu, text, font_pt, line_spacing):
    """按框宽与字号估算文本所需高度（EMU）"""
    try:
        width_pt = (width_emu or Pt(400)) / 12700.0
    except Exception:
        width_pt = 400.0
    chars_per_line = max(1, int(width_pt / max(1.0, font_pt * 1.05)))
    lines = 0
    for para in (text or "").split("\n"):
        lines += max(1, int(math.ceil(len(para) / float(chars_per_line))))
    return int(lines * font_pt * line_spacing * 12700)


def normalize_paragraph(para, line_spacing, space_after):
    try:
        para.line_spacing = line_spacing
        para.space_after = Pt(space_after)
        para.alignment = PP_ALIGN.LEFT
    except Exception:
        pass


def tidy_design_page(slide, prs, style, layout, page_no, warnings):
    """设计稿型页面：底部说明条统一为通栏，其余文本框收进版心，图片不动"""
    W, H = prs.slide_width, prs.slide_height
    m = Pt(layout["marginPt"])
    band_h = Pt(layout["bandHeightPt"])
    note_size = style["noteSizePt"]

    for sh in text_shapes(slide.shapes):
        try:
            top = sh.top if sh.top is not None else 0
            if top > H * 0.6:
                sh.left, sh.width = m, W - 2 * m
                sh.top, sh.height = H - m - band_h, band_h
                if layout.get("bandFill"):
                    try:
                        sh.fill.solid()
                        sh.fill.fore_color.rgb = RGBColor.from_string(layout["bandFill"])
                    except Exception:
                        pass
                for para in sh.text_frame.paragraphs:
                    normalize_paragraph(para, 1.2, 4)
                    for run in para.runs:
                        if run.text:
                            run.font.size = Pt(note_size)
            else:
                left = sh.left if sh.left is not None else m
                width = sh.width if sh.width is not None else W - 2 * m
                left = max(m, min(left, W - m - Pt(40)))
                width = max(Pt(40), min(width, W - m - left))
                sh.left, sh.width = left, width
                for para in sh.text_frame.paragraphs:
                    normalize_paragraph(para, layout["lineSpacing"], layout["spaceAfterPt"])
        except Exception as e:
            warnings.append("第 %d 页版面规整跳过：%s" % (page_no, e))


def tidy_text_page(slide, prs, style, layout, page_no, warnings):
    """文本型页面：标题区 + 正文区纵向流式排布，统一版心与间距"""
    W, H = prs.slide_width, prs.slide_height
    m = Pt(layout["marginPt"])
    title_h = Pt(layout["titleHeightPt"])
    gap = Pt(layout["titleGapPt"])
    body_gap = Pt(layout["bodyGapPt"])
    line_spacing = layout["lineSpacing"]
    space_after = layout["spaceAfterPt"]

    shapes = sorted(text_shapes(slide.shapes), key=lambda s: ((s.top or 0), (s.left or 0)))
    if not shapes:
        return

    title_sh = shapes[0]
    try:
        title_sh.left, title_sh.top = m, m
        title_sh.width = W - 2 * m
        title_sh.height = title_h
        for para in title_sh.text_frame.paragraphs:
            normalize_paragraph(para, 1.15, 4)
    except Exception as e:
        warnings.append("第 %d 页标题区规整失败：%s" % (page_no, e))

    y = m + title_h + gap
    usable_bottom = H - m

    for sh in shapes[1:]:
        try:
            sh.left, sh.width = m, W - 2 * m
            sh.top = y

            body_size = style["bodySizePt"]
            need = estimate_height_emu(W - 2 * m, sh.text_frame.text, body_size, line_spacing)
            avail = max(Pt(24), usable_bottom - y)
            downgraded = 0
            while need > avail and downgraded < 2:
                body_size = round(body_size * 0.88, 1)
                need = estimate_height_emu(W - 2 * m, sh.text_frame.text, body_size, line_spacing)
                downgraded += 1
            if downgraded:
                warnings.append("第 %d 页文本过长，字号自动降 %d 档至 %.1fpt" % (page_no, downgraded, body_size))
                for para in sh.text_frame.paragraphs:
                    for run in para.runs:
                        if run.text:
                            run.font.size = Pt(body_size)

            sh.height = max(Pt(24), min(need, avail))
            y += sh.height + body_gap

            for para in sh.text_frame.paragraphs:
                normalize_paragraph(para, line_spacing, space_after)
        except Exception as e:
            warnings.append("第 %d 页正文区规整失败：%s" % (page_no, e))


def tidy_layout(slide, prs, style, layout, page_no, warnings):
    mode = layout.get("mode", "auto")
    if mode == "keep":
        return "keep"
    page_type = classify_slide(slide, prs)
    if mode == "tidy":
        page_type = "text"
    if page_type == "design":
        tidy_design_page(slide, prs, style, layout, page_no, warnings)
    else:
        tidy_text_page(slide, prs, style, layout, page_no, warnings)
    return page_type


# ==================== plan ====================

def resolve_style(plan_style, cli_industry, warnings):
    """
    样式优先级：plan.style 显式字段 > 行业预设 > 通用默认。
    plan_style 中的 layout / industry 属控制字段，不参与 style 合并。
    """
    plan_style = plan_style or {}
    industry = (cli_industry or plan_style.get("industry") or DEFAULT_INDUSTRY).strip()

    style = dict(DEFAULT_STYLE)
    layout = dict(DEFAULT_LAYOUT)

    if industry in INDUSTRY_PRESETS:
        style.update(INDUSTRY_PRESETS[industry])
        layout.update(INDUSTRY_LAYOUT.get(industry) or {})
    else:
        warnings.append("未识别的行业「%s」，已回退为「%s」；可选：%s"
                        % (industry, DEFAULT_INDUSTRY, "、".join(INDUSTRY_PRESETS.keys())))
        industry = DEFAULT_INDUSTRY
        style.update(INDUSTRY_PRESETS[DEFAULT_INDUSTRY])

    explicit = {k: v for k, v in plan_style.items() if k not in ("layout", "industry")}
    style.update(explicit)
    layout.update(plan_style.get("layout") or {})
    return style, layout, industry


def load_plan(path, slide_count, cli_industry=None):
    plan_warnings = []
    if not os.path.exists(path):
        fail(EXIT_BAD_PLAN, "plan.json 不存在：%s" % path, "请先由模型产出 plan.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        fail(EXIT_BAD_PLAN, "plan.json 解析失败：%s" % e, "请检查 JSON 格式")

    if not isinstance(plan, dict) or "pages" not in plan:
        fail(EXIT_BAD_PLAN, "plan.json 缺少 pages 字段", "plan 需含 style 与 pages")

    for p in plan["pages"]:
        idx = p.get("index")
        if not isinstance(idx, int) or idx < 1 or idx > slide_count:
            fail(EXIT_BAD_PLAN, "plan 中页码越界：%r（有效范围 1..%d）" % (idx, slide_count),
                 "请修正 plan 的 index")

    style, layout, industry = resolve_style(plan.get("style"), cli_industry, plan_warnings)
    return plan, style, layout, industry, plan_warnings


def main():
    ap = argparse.ArgumentParser(description="按 plan.json 优化并规整 PPTX、写入讲解备注")
    ap.add_argument("input", help="原始课件 .pptx")
    ap.add_argument("--plan", required=True, help="plan.json 路径")
    ap.add_argument("-o", "--output", default=None, help="输出 PPTX 路径")
    ap.add_argument("-w", "--workdir", default="work", help="工作目录")
    ap.add_argument("--keep-existing-notes", action="store_true",
                    help="原备注非空时保留不覆盖")
    ap.add_argument("--industry", default=None,
                    help="行业风格预设，如 发布会 / 教育培训 / 金融保险；覆盖 plan.style.industry")
    args = ap.parse_args()

    src = args.input
    if not os.path.exists(src):
        fail(EXIT_BAD_INPUT, "文件不存在：%s" % src, "请确认路径")
    if os.path.splitext(src)[1].lower() != ".pptx":
        fail(EXIT_BAD_INPUT, "仅支持 .pptx：%s" % src, "请先另存为 .pptx")
    with open(src, "rb") as f:
        if f.read(8) == OLE_MAGIC:
            fail(EXIT_ENCRYPTED, "文件是加密包或旧式二进制格式",
                 "请去除密码后另存为无保护的 .pptx")

    try:
        prs = Presentation(src)
    except Exception as e:
        fail(EXIT_PARSE_FAILED, "文件损坏或无法解析：%s" % e, "请另存为新的 .pptx 后重试")

    slides = list(prs.slides)
    if not slides:
        fail(EXIT_EMPTY, "该文档不含任何幻灯片", "请确认文件")

    plan, style, layout, industry, plan_warnings = load_plan(
        args.plan, len(slides), args.industry)
    page_plan = {p["index"]: p for p in plan["pages"]}

    out = args.output or os.path.join(args.workdir, "optimized.pptx")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    except Exception as e:
        fail(EXIT_WRITE_FAILED, "输出目录无法创建：%s" % e,
             "请更换输出路径，确认盘符与目录存在且有写权限")

    style_changed = 0
    notes_written = 0
    replacements = []
    title_fixes = []
    warnings = list(plan_warnings)
    backup_lines = []
    page_types = {}

    for idx, slide in enumerate(slides, start=1):
        p = page_plan.get(idx, {})
        notes = (p.get("notes") or "").strip()

        # ---------- 1. 版面规整 ----------
        page_types[idx] = tidy_layout(slide, prs, style, layout, idx, warnings)

        # ---------- 2. 版式统一（字体 / 字号分档 / 配色） ----------
        is_design = page_types[idx] == "design"
        for sh, para in iter_text_units(slide.shapes):
            is_title_shape = False
            try:
                is_title_shape = (slide.shapes.title is not None and sh is slide.shapes.title)
            except Exception:
                pass
            in_band = False
            try:
                in_band = is_design and sh.top is not None and sh.top > prs.slide_height * 0.6
            except Exception:
                pass

            for run in para.runs:
                if not run.text:
                    continue
                try:
                    set_east_asian_font(run, style["fontName"])
                    orig_size = run.font.size.pt if run.font.size is not None else None
                    if in_band:
                        run.font.size = Pt(style["noteSizePt"])
                        run.font.color.rgb = RGBColor.from_string(style["bodyColor"])
                    elif is_title_shape or (orig_size is not None and orig_size >= TITLE_SIZE_THRESHOLD):
                        run.font.size = Pt(style["titleSizePt"])
                        run.font.color.rgb = RGBColor.from_string(style["titleColor"])
                    else:
                        run.font.size = Pt(style["bodySizePt"])
                        if run.font.bold and style.get("accentColor"):
                            run.font.color.rgb = RGBColor.from_string(style["accentColor"])
                        else:
                            run.font.color.rgb = RGBColor.from_string(style["bodyColor"])
                    style_changed += 1
                except Exception as e:
                    warnings.append("第 %d 页存在无法调整格式的文本：%s" % (idx, e))

        # ---------- 3. 文本修正（仅执行 plan 显式声明） ----------
        for rep in (p.get("replacements") or []):
            old = rep.get("from", "")
            new = rep.get("to", "")
            if not old:
                warnings.append("第 %d 页替换项缺 from，已跳过" % idx)
                continue
            applied = False
            for sh, para in iter_text_units(slide.shapes):
                if replace_in_paragraph(para, old, new):
                    applied = True
                    break
            replacements.append({
                "page": idx, "from": old, "to": new,
                "reason": rep.get("reason", ""), "applied": applied,
            })
            if not applied:
                warnings.append("第 %d 页未找到待替换原文「%s」，该条替换未生效" % (idx, old))

        # ---------- 4. 标题修正 ----------
        tf = (p.get("titleFix") or "").strip()
        if tf:
            try:
                if slide.shapes.title is not None:
                    old_title = slide.shapes.title.text
                    tparas = slide.shapes.title.text_frame.paragraphs
                    if tparas and tparas[0].runs:
                        tparas[0].runs[0].text = tf
                        for r in tparas[0].runs[1:]:
                            r.text = ""
                        title_fixes.append({"page": idx, "from": old_title, "to": tf})
                    else:
                        warnings.append("第 %d 页标题无可用 run，titleFix 未生效" % idx)
                else:
                    warnings.append("第 %d 页无标题占位符，titleFix 未生效" % idx)
            except Exception as e:
                warnings.append("第 %d 页 titleFix 失败：%s" % (idx, e))

        # ---------- 5. 写入备注 ----------
        if notes:
            try:
                existing = ""
                if slide.has_notes_slide:
                    existing = slide.notes_slide.notes_text_frame.text.strip()
                if existing and args.keep_existing_notes:
                    warnings.append("第 %d 页原有备注非空，已按 --keep-existing-notes 保留" % idx)
                else:
                    if existing:
                        backup_lines.append("## 第 %d 页\n\n%s\n" % (idx, existing))
                    slide.notes_slide.notes_text_frame.text = notes
                    notes_written += 1
            except Exception as e:
                warnings.append("第 %d 页备注写入失败：%s" % (idx, e))
        else:
            warnings.append("第 %d 页 plan 未提供 notes，备注栏保持原样" % idx)

    # ---------- 原备注备份 ----------
    if backup_lines:
        bp = os.path.join(args.workdir, "original-notes-backup.md")
        try:
            os.makedirs(args.workdir, exist_ok=True)
            with open(bp, "w", encoding="utf-8") as f:
                f.write("# 原始备注备份（覆盖前自动留存）\n\n")
                f.write("\n".join(backup_lines))
        except Exception as e:
            warnings.append("原备注备份写出失败：%s" % e)

    # ---------- 保存 ----------
    try:
        prs.save(out)
    except Exception as e:
        fail(EXIT_WRITE_FAILED, "优化后文件写出失败：%s" % e,
             "请更换输出路径，或关闭可能占用该文件的 WPS / PowerPoint")

    n_design = sum(1 for v in page_types.values() if v == "design")
    report = {
        "ok": True,
        "source": os.path.abspath(src),
        "output": os.path.abspath(out),
        "industry": industry,
        "tone": INDUSTRY_TONE.get(industry, ""),
        "style": style,
        "layout": layout,
        "pageTypes": page_types,
        "layoutStats": {"designPages": n_design, "textPages": len(page_types) - n_design},
        "styleChangedRuns": style_changed,
        "notesWritten": notes_written,
        "replacements": replacements,
        "titleFixes": title_fixes,
        "warnings": warnings,
    }

    rp = os.path.join(args.workdir, "apply-report.json")
    try:
        os.makedirs(args.workdir, exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warnings.append("变更清单写出失败：%s" % e)
        rp = None

    sys.stderr.write("[apply] 完成：版式调整 %d 处 / 备注写入 %d 页 / 替换 %d 条\n"
                     % (style_changed, notes_written, len([r for r in replacements if r["applied"]])))
    sys.stderr.write("[apply] 页面类型：设计稿型 %d 页 / 文本型 %d 页\n"
                     % (n_design, len(page_types) - n_design))
    sys.stderr.write("[apply] 行业风格：%s（%s）\n" % (industry, INDUSTRY_TONE.get(industry, "")))
    for w in warnings:
        sys.stderr.write("  ! %s\n" % w)
    sys.stderr.write("[apply] 优化后 PPTX：%s\n" % out)
    if rp:
        sys.stderr.write("[apply] 变更清单：%s\n" % rp)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()

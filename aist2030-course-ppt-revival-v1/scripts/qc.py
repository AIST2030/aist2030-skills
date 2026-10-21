#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qc.py —— 老旧课程 PPT 复活 · 质检闸门（排版 + 讲稿 + 零知识丢失）

对「优化后 PPTX + plan.json」做交付前体检，输出结构化质检报告。
任何 FAIL 项都必须回到 plan / apply 修掉，不允许带病交付。

用法：
    python qc.py 优化后.pptx --plan work/plan.json -w work/
    python qc.py 优化后.pptx --plan work/plan.json --original 原始课件.pptx \
            --industry 教育培训 --strict -o work/qc-report.json

检查项：
  【排版】
    L1 版心一致   文本型页所有文本框左边界与宽度统一
    L2 无越界     所有元素落在版心内
    L3 无重叠     同页文本框纵向不互相压盖
    L4 字号分档   只出现 标题/正文/说明 三档（含自动降档）
    L5 字体统一   全篇东亚字体一致
    L6 无小字     无小于 12pt 的文字
  【讲稿】
    S1 覆盖       每页均有备注
    S2 口语化     无破折号 / 省略号 / 书面括号夹注
    S3 句长       单句不超过 80 字
    S4 极限词     无广告法风险词
    S5 数字中文   阿拉伯数字改中文（年份豁免）
    S6 连贯衔接   相邻页有过渡承接，避免逐页念稿
    S7 开场防重   首讲不复述标题原文
    S8 时长匹配   单页时长落在合理区间
  【安全】
    K1 零知识丢失 除 plan 显式声明的替换外，正文文本与原件完全一致

退出码：0 通过 | 2 文件问题 | 6 质检不达标
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.oxml.ns import qn
    from pptx.util import Pt
except ImportError:
    sys.stderr.write("[qc] 缺少 python-pptx，请先 pip install python-pptx\n")
    sys.exit(1)

from apply import (  # noqa: E402
    INDUSTRY_TONE,
    classify_slide,
    iter_shapes,
    resolve_style,
)

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_QC_FAILED = 6

TOL = Pt(2)  # 位置容差 2pt

# 极限词：FAIL 级（广告法硬风险）与 WARN 级（建议改写）
BANNED_HARD = ["最好", "最佳", "最强", "最省", "最快", "最优", "最低价", "第一品牌",
               "唯一", "独家", "百分百", "绝对", "国家级", "顶级", "万能", "包治"]
BANNED_SOFT = ["领先", "革命性", "颠覆", "史无前例", "前所未有的", "彻底解决", "永久"]

# 衔接信号词（覆盖短视频课程常见的承上启下、递进、举例、收束表达）
TRANSITION_HINTS = [
    # 承接
    "先说", "再说", "接着", "回头", "说完", "讲完", "讲到", "刚才", "前面", "上面",
    "上一页", "回顾", "话说回来", "回过头", "再看",
    # 递进 / 顺序
    "接下来", "然后", "首先", "其次", "最后", "第一", "第二", "第三", "第四",
    # 展开 / 设问
    "为什么", "怎么", "具体", "落地", "实战", "案例", "例子", "故事", "数据",
    "复盘", "收尾", "总结", "其实", "简单说", "说白了",
    # 引入 / 指代
    "我们", "这一", "换个", "记住", "注意", "说到", "聊到", "给你", "我给你",
    "顺着", "于是", "有了", "所以", "那", "那么", "反过来说", "换句话说",
    "到这里", "再往", "讲到这儿", "先来看", "下面", "此时", "这时", "现在",
    "不过", "而且", "同时", "另外", "此外", "引入", "举个例子", "先看",
    "你可能会", "我猜", "这里", "上面那", "顺着这个", "顺着这",
]

TRANSITION_TARGET = 0.70
TRANSITION_FLOOR = 0.50

SPEAK_RATE = 4.8  # 字/秒
MIN_SEC = 6.0
MAX_SEC = 90.0


def fail(code, message, hint=""):
    sys.stderr.write(json.dumps(
        {"ok": False, "code": code, "message": message, "hint": hint},
        ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


# ==================== 抽取 ====================

def run_ea_font(run):
    try:
        rPr = run.font._rPr
        ea = rPr.find(qn("a:ea"))
        if ea is not None and ea.get("typeface"):
            return ea.get("typeface")
    except Exception:
        pass
    try:
        return run.font.name
    except Exception:
        return None


def slide_text_shapes(slide):
    out = []
    for sh in iter_shapes(slide.shapes):
        try:
            if getattr(sh, "has_table", False):
                continue
            if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
                out.append(sh)
        except Exception:
            pass
    return out


def slide_all_shapes(slide):
    out = []
    for sh in iter_shapes(slide.shapes):
        try:
            if getattr(sh, "has_table", False):
                continue
            if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
                out.append(sh)
            elif sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                out.append(sh)
        except Exception:
            pass
    return out


def page_texts(slide):
    """抽出该页全部文本行（含表格），用于零知识丢失比对"""
    lines = []
    for sh in iter_shapes(slide.shapes):
        try:
            if getattr(sh, "has_table", False):
                for row in sh.table.rows:
                    for cell in row.cells:
                        t = (cell.text or "").strip()
                        if t:
                            lines.append(t)
                continue
        except Exception:
            pass
        try:
            if getattr(sh, "has_text_frame", False):
                t = (sh.text_frame.text or "").strip()
                if t:
                    lines.append(t)
        except Exception:
            pass
    return lines


# ==================== 讲稿分析 ====================

def split_sentences(text):
    parts = re.split(r"[。！？；\n]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def has_transition(head, prev_tail):
    h = head.strip()
    if not h:
        return False
    # 1) 头部 30 字内出现任意衔接词（短视频口语常见承上启下表达）
    for w in TRANSITION_HINTS:
        if w in h[:30]:
            return True
    # 2) 与上一页末句有实词回指（>=4 字连续重叠）
    if prev_tail:
        for n in range(6, 3, -1):
            for i in range(0, max(0, len(prev_tail) - n + 1)):
                if prev_tail[i:i + n] in head:
                    return True
    return False


# ==================== 主检查 ====================

def check_layout(prs, style, layout, layout_mode):
    W, H = prs.slide_width, prs.slide_height
    m = Pt(layout["marginPt"])
    allowed = {round(style["titleSizePt"], 1), round(style["bodySizePt"], 1),
               round(style["noteSizePt"], 1)}
    b = style["bodySizePt"]
    for k in (1, 2):
        allowed.add(round(round(b * (0.88 ** k), 1), 1))

    items = {
        "L1": [], "L2": [], "L3": [], "L4": [], "L5": [], "L6": [],
    }

    for idx, slide in enumerate(prs.slides, start=1):
        page_type = classify_slide(slide, prs)
        is_text_page = (page_type != "design")

        shapes = slide_text_shapes(slide)
        for sh in shapes:
            try:
                left, top = sh.left, sh.top
                width, height = sh.width, sh.height
            except Exception:
                continue
            if left is None or top is None or width is None or height is None:
                continue

            # L1 版心一致
            if is_text_page and layout_mode != "keep":
                if abs(left - m) > TOL or abs(width - (W - 2 * m)) > TOL:
                    items["L1"].append("第 %d 页文本框未对齐版心（left=%.0fpt width=%.0fpt，应为 %.0f / %.0f）"
                                       % (idx, left / 12700.0, width / 12700.0,
                                          m / 12700.0, (W - 2 * m) / 12700.0))

            # L2 越界
            over = []
            if left < m - TOL:
                over.append("左")
            if top < m - TOL:
                over.append("上")
            if left + width > W - m + TOL:
                over.append("右")
            if top + height > H - m + TOL:
                over.append("下")
            if over:
                items["L2"].append("第 %d 页元素超出%s边界" % (idx, "、".join(over)))

        # L3 重叠
        boxes = []
        for sh in shapes:
            try:
                if None in (sh.top, sh.height, sh.left, sh.width):
                    continue
                boxes.append((sh.top, sh.left, sh.height, sh.width, sh))
            except Exception:
                continue
        boxes.sort(key=lambda x: (x[0], x[1]))
        for i in range(len(boxes) - 1):
            t1, l1, h1, w1, _ = boxes[i]
            t2, l2, h2, w2, _ = boxes[i + 1]
            v_overlap = (t1 + h1) - t2
            h_overlap = min(l1 + w1, l2 + w2) - max(l1, l2)
            if v_overlap > TOL and h_overlap > TOL:
                items["L3"].append("第 %d 页有文本块重叠（上下压盖 %.0fpt）"
                                   % (idx, v_overlap / 12700.0))

        # L4 / L5 / L6
        for sh, para in _iter_units(slide.shapes):
            for run in para.runs:
                if not run.text:
                    continue
                try:
                    size = run.font.size.pt if run.font.size is not None else None
                except Exception:
                    size = None
                if size is not None:
                    if round(size, 1) not in allowed:
                        items["L4"].append("第 %d 页出现档外字号 %.1fpt「%s」"
                                           % (idx, size, run.text[:12]))
                    if size < 12:
                        items["L6"].append("第 %d 页存在 %.1fpt 小字「%s」"
                                           % (idx, size, run.text[:12]))
                f = run_ea_font(run)
                if f and f != style["fontName"]:
                    items["L5"].append("第 %d 页字体「%s」未统一为 %s"
                                       % (idx, f, style["fontName"]))

    checks = []
    checks.append(_mk("L1", "版心一致（文本型页左边界与宽度统一）", items["L1"], "FAIL", 8))
    checks.append(_mk("L2", "无越界（所有元素落在版心内）", items["L2"], "FAIL", 8))
    checks.append(_mk("L3", "无重叠（同页文本块不互相压盖）", items["L3"], "FAIL", 8))
    checks.append(_mk("L4", "字号分档（仅标题/正文/说明三档）", items["L4"], "WARN", 8))
    checks.append(_mk("L5", "字体统一（全篇东亚字体一致）", items["L5"], "FAIL", 8))
    checks.append(_mk("L6", "无小于 12pt 的小字", items["L6"], "FAIL", 8))
    return checks


def _iter_units(shapes):
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


def _mk(cid, name, items, level, cap=8):
    if not items:
        return {"id": cid, "name": name, "level": "PASS", "count": 0, "items": []}
    return {"id": cid, "name": name, "level": level, "count": len(items),
            "items": items[:cap], "truncated": len(items) > cap}


def check_script(plan, page_meta):
    pages = {p.get("index"): p for p in plan.get("pages", [])}
    notes_map = {}
    s1, s2, s3, s4, s5, s7, s8 = [], [], [], [], [], [], []

    ordered = sorted(pages.keys())
    for i in ordered:
        p = pages[i]
        notes = (p.get("notes") or "").strip()
        if not notes:
            s1.append("第 %d 页 plan 未提供讲解备注" % i)
            continue
        notes_map[i] = notes

        if "——" in notes or "…" in notes or "..." in notes:
            s2.append("第 %d 页含破折号或省略号，口播会卡壳" % i)
        if re.search(r"[（(]\s*(注|即|详见|如图|见表)", notes):
            s2.append("第 %d 页含括号夹注，不适合口播" % i)

        for s in split_sentences(notes):
            if len(s) > 80:
                s3.append("第 %d 页单句 %d 字超限：「%s…」" % (i, len(s), s[:24]))

        for w in BANNED_HARD:
            if w in notes:
                s4.append("第 %d 页含极限词「%s」，违反广告法" % (i, w))
        for w in BANNED_SOFT:
            if w in notes:
                s4.append("第 %d 页含风险表述「%s」，建议改写" % (i, w))

        for d in re.findall(r"\d+", notes):
            if len(d) == 4 and d.startswith(("19", "20")):
                continue  # 年份豁免
            s5.append("第 %d 页阿拉伯数字「%s」，口播建议写中文" % (i, d))

        meta = page_meta.get(i, {})
        title = (meta.get("title") or "").strip()
        if i == ordered[0] and title:
            head = notes[:max(12, min(len(title), 25))]
            same = sum(1 for ch in head if ch in title)
            if len(title) >= 8 and same / float(len(head)) >= 0.8:
                s7.append("首页开场基本复述标题「%s」，建议改成钩子式开场" % title[:20])

        est = len(re.sub(r"\s+", "", notes)) / SPEAK_RATE
        if est < MIN_SEC:
            s8.append("第 %d 页时长 %.0fs 偏短，信息撑不满画面" % (i, est))
        elif est > MAX_SEC:
            s8.append("第 %d 页时长 %.0fs 偏长，建议拆页或精简" % (i, est))

    # S6 连贯衔接
    s6 = []
    hit = 0
    total = 0
    for n in range(1, len(ordered)):
        prev = ordered[n - 1]
        cur = ordered[n]
        if prev not in notes_map or cur not in notes_map:
            continue
        total += 1
        tail_sentences = split_sentences(notes_map[prev])
        prev_tail = tail_sentences[-1] if tail_sentences else ""
        head = notes_map[cur][:40]
        if has_transition(head, prev_tail):
            hit += 1
        else:
            s6.append("第 %d→%d 页缺少衔接，开头建议加承接词" % (prev, cur))
    ratio = (hit / float(total)) if total else 0.0

    checks = []
    checks.append(_mk("S1", "讲稿覆盖（每页均有备注）", s1, "FAIL"))
    checks.append(_mk("S2", "口语化（无破折号/省略号/括号夹注）", s2, "FAIL"))
    checks.append(_mk("S3", "句长控制（单句 ≤80 字）", s3, "FAIL"))
    checks.append(_mk("S4", "合规（无极限词与风险表述）", s4, "FAIL"))
    checks.append(_mk("S5", "数字中文化（年份豁免）", s5, "WARN"))
    if ratio >= TRANSITION_TARGET:
        s6_level = "PASS"
    elif ratio >= TRANSITION_FLOOR:
        s6_level = "WARN"
    else:
        s6_level = "FAIL"
    checks.append({"id": "S6", "name": "连贯衔接（相邻页过渡覆盖率）",
                   "level": s6_level, "count": len(s6),
                   "ratio": round(ratio, 3), "target": TRANSITION_TARGET,
                   "items": s6[:8], "truncated": len(s6) > 8})
    checks.append(_mk("S7", "开场防重（首页不复述标题）", s7, "WARN"))
    checks.append(_mk("S8", "时长匹配（单页 %ss~%ss）" % (int(MIN_SEC), int(MAX_SEC)), s8, "WARN"))
    return checks, ratio


def check_knowledge(prs_opt, prs_src, plan):
    """零知识丢失：除 plan 显式声明的替换外，正文文本应与原件一致"""
    items = []
    pages = {p.get("index"): p for p in plan.get("pages", [])}
    src_slides = list(prs_src.slides)
    for idx, slide in enumerate(prs_opt.slides, start=1):
        if idx > len(src_slides):
            continue
        src_lines = page_texts(src_slides[idx - 1])
        opt_lines = page_texts(slide)
        if src_lines == opt_lines:
            continue
        # 应用已声明替换后再比
        reps = (pages.get(idx) or {}).get("replacements") or []
        tf = ((pages.get(idx) or {}).get("titleFix") or "").strip()
        exp = list(src_lines)
        if tf and exp:
            exp[0] = tf
        for r in reps:
            old, new = r.get("from", ""), r.get("to", "")
            if old:
                exp = [l.replace(old, new) for l in exp]
        if exp == opt_lines:
            continue
        items.append("第 %d 页文本与原件不一致且未声明替换：原件首行「%s」→ 现「%s」"
                     % (idx, (src_lines[0] if src_lines else "")[:20],
                        (opt_lines[0] if opt_lines else "")[:20]))
    return [_mk("K1", "零知识丢失（正文与原件一致或已声明）", items, "FAIL")]


# ==================== main ====================

def main():
    ap = argparse.ArgumentParser(description="优化后 PPTX 交付前质检")
    ap.add_argument("input", help="优化后 .pptx")
    ap.add_argument("--plan", required=True, help="plan.json 路径")
    ap.add_argument("--original", default=None, help="原始课件 .pptx（开启零知识丢失比对）")
    ap.add_argument("--industry", default=None, help="行业风格，需与 apply 时一致")
    ap.add_argument("-o", "--output", default=None, help="质检报告路径")
    ap.add_argument("-w", "--workdir", default="work", help="工作目录")
    ap.add_argument("--strict", action="store_true", help="有 WARN 即判不达标")
    args = ap.parse_args()

    src = args.input
    if not os.path.exists(src):
        fail(EXIT_BAD_INPUT, "文件不存在：%s" % src, "请确认路径")
    try:
        prs = Presentation(src)
    except Exception as e:
        fail(EXIT_BAD_INPUT, "文件无法解析：%s" % e, "请确认是有效的 .pptx")

    try:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        fail(EXIT_BAD_INPUT, "plan.json 读取失败：%s" % e, "请检查路径与 JSON 格式")

    style, layout, industry = resolve_style(plan.get("style"), args.industry, [])
    layout_mode = layout.get("mode", "auto")

    # 页面元信息（标题）供 S7 使用
    page_meta = {}
    for idx, slide in enumerate(prs.slides, start=1):
        t = ""
        try:
            if slide.shapes.title is not None:
                t = slide.shapes.title.text
        except Exception:
            pass
        page_meta[idx] = {"title": t}

    checks = []
    checks += check_layout(prs, style, layout, layout_mode)
    script_checks, ratio = check_script(plan, page_meta)
    checks += script_checks

    if args.original and os.path.exists(args.original):
        try:
            prs_src = Presentation(args.original)
            checks += check_knowledge(prs, prs_src, plan)
        except Exception as e:
            checks.append(_mk("K1", "零知识丢失（正文与原件一致或已声明）",
                              ["原始文件解析失败，无法比对：%s" % e], "WARN"))
    elif args.original:
        checks.append(_mk("K1", "零知识丢失（正文与原件一致或已声明）",
                          ["原始文件不存在：%s" % args.original], "WARN"))

    n_pass = sum(1 for c in checks if c["level"] == "PASS")
    n_warn = sum(1 for c in checks if c["level"] == "WARN")
    n_fail = sum(1 for c in checks if c["level"] == "FAIL")

    failed = n_fail > 0 or (args.strict and n_warn > 0)

    report = {
        "ok": not failed,
        "source": os.path.abspath(src),
        "industry": industry,
        "tone": INDUSTRY_TONE.get(industry, ""),
        "style": style,
        "layout": layout,
        "transitionRatio": round(ratio, 3),
        "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail},
        "checks": checks,
    }

    out = args.output or os.path.join(args.workdir, "qc-report.json")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write("[qc] 报告写出失败：%s\n" % e)
        out = None

    sys.stderr.write("[qc] 行业：%s｜通过 %d / 告警 %d / 不达标 %d\n"
                     % (industry, n_pass, n_warn, n_fail))
    for c in checks:
        mark = {"PASS": "√", "WARN": "!", "FAIL": "×"}[c["level"]]
        extra = ""
        if c["id"] == "S6":
            extra = "（衔接率 %.0f%% / 目标 %.0f%%）" % (ratio * 100, TRANSITION_TARGET * 100)
        sys.stderr.write("  %s %s %s%s\n" % (mark, c["id"], c["name"], extra))
        for it in c.get("items", [])[:5]:
            sys.stderr.write("      - %s\n" % it)
        if c.get("truncated"):
            sys.stderr.write("      …… 共 %d 条，详见报告\n" % c["count"])
    if out:
        sys.stderr.write("[qc] 质检报告：%s\n" % out)

    sys.exit(EXIT_QC_FAILED if failed else EXIT_OK)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S7 · 字幕-语音同步核验 + 抽帧质检 ★交付前的最后闸门（硬失败即 exit 1）

自动检查项（任一硬失败 → 进程退出码 1，阻断交付）：
  1. 成片规格        1080x1920 / fps 24~31 / 有音轨 / 时长 >0.5s
  2. 字幕排版        单行不折行、不超宽（PIL 独立复测）、时间合法、相邻零重叠
  3. 字幕-语音对齐    按 EDL 反算期望成片时间 vs 字幕实际 start（容差 0.15s）
  4. 台词完整        EDL 覆盖内覆盖率 ≥0.7 的 ASR 句必须出现或被显式丢弃
  5. 首尾不吞字
  6. 响度            -16 ±1.5 LUFS
  7. 原字幕清理      canvas_info 断言 + 清理区高频能量（能量只 warn）
  8. 抽帧解码成功
  9. 抽帧无黑场      mean<12 **且** p99<60 双条件（夜景不再被误判为黑场）

★联系表交给人工目视——**模型判不了"字幕压不压脸"，必须人眼看**。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

# 判黑场：均值低 **且** 高光分位也低，才算真黑场（夜景素材均值仅 7 但 p99 很高）
BLACK_MEAN = 12.0
BLACK_P99 = 60.0
# 字幕-语音允许的最大双向偏差
ALIGN_TOLERANCE = 0.15
# 相邻字幕允许的重叠（秒）。规范要求"零重叠"，这里只留 20ms 吸收取整误差
OVERLAP_TOL = 0.02
# 宽度判定的容差（px）。负例"超宽 1px"必须能被抓到，所以留 0.5px 抗浮点误差
MAX_PX_TOL = 0.5
# 报告里每类检查保留的 detail 条数上限
DETAIL_LIMIT = 20
# 台词完整性：EDL 段对 ASR 句的覆盖率阈值
COVERAGE_MIN = 0.70
# 判定"该句已出现在字幕里"的时间轴覆盖率阈值（长句会被拆成多屏）
SUB_HIT_RATIO = 0.60
# 「有话必有字幕」：原字幕窗内新字幕的最低时间覆盖率
SPEECH_COVER_MIN = 0.50
# 检测窗软边容忍：原字幕窗两端有外扩/合并，量覆盖时向内各收这么多秒再比
SPEECH_EDGE_TRIM = 0.18

_FONT_DIRS = ["C:/Windows/Fonts", "C:/Windows/Fonts/Fonts"]
_FONT_ALIAS = {
    "microsoft yahei": ["msyh.ttc", "msyhbd.ttc", "msyhl.ttc"],
    "微软雅黑": ["msyh.ttc", "msyhbd.ttc"],
    "yahei": ["msyh.ttc", "msyhbd.ttc"],
    "simhei": ["simhei.ttf"],
    "黑体": ["simhei.ttf"],
    "simsun": ["simsun.ttc"],
    "宋体": ["simsun.ttc"],
    "noto sans": ["NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf"],
    "source han": ["SourceHanSansSC-Regular.otf"],
}


# ---------------------------------------------------------------- 通用工具

def result(detail, skipped: bool = False) -> dict:
    """统一构造检查结果。count 即异常条数，detail 有界。"""
    return {
        "pass": len(detail) == 0,
        "count": len(detail),
        "detail": list(detail)[:DETAIL_LIMIT],
        "skipped": skipped,
    }


def _load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return fe.json_load(str(p))
    except Exception:
        return None


def _load_edl(work) -> list[dict]:
    """读 edl.csv，只保留能用于时间轴反算的字段。坏行直接丢弃。"""
    import csv as _csv

    p = Path(work) / "edl.csv"
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(_csv.DictReader(f))
    out = []
    for r in rows:
        try:
            out.append({
                "index": str(r.get("index", "")).strip(),
                "ep": (r.get("ep") or "").strip(),
                "final_in": float(r["final_in"]),
                "final_out": float(r["final_out"]),
                "tl_in": float(r["tl_in"]),
                "tl_out": float(r.get("tl_out") or 0.0),
            })
        except Exception:
            continue
    return out


def _norm(s: str) -> str:
    """文本归一化（去空白与标点），用于"这句台词有没有进字幕"的匹配。"""
    return re.sub(r"[\s，。！？、；：,.!?;:…—\-~\"'“”‘’()（）【】《》]", "", s or "")


def resolve_font_file(name: str | None) -> str | None:
    """字体名 → 字体文件路径。用于独立复测字幕宽度（不信上游数值）。"""
    if not name:
        return None
    p = Path(name)
    if p.exists():
        return str(p)
    key = str(name).strip().lower()
    for alias, files in _FONT_ALIAS.items():
        if alias in key:
            for d in _FONT_DIRS:
                for f in files:
                    if (Path(d) / f).exists():
                        return str(Path(d) / f)
    stem = re.sub(r"[^a-z0-9]", "", key)
    if stem:
        try:
            for d in _FONT_DIRS:
                for f in Path(d).glob("*.tt*"):
                    if re.sub(r"[^a-z0-9]", "", f.stem.lower()) == stem:
                        return str(f)
        except Exception:
            pass
    return None


def measure_text_px(text: str, font_file: str, font_size: int) -> float | None:
    """用 PIL 按实际字体量文本宽度（px）。失败返回 None。"""
    try:
        from PIL import ImageFont

        f = ImageFont.truetype(font_file, int(font_size))
        return float(f.getlength(text or ""))
    except Exception:
        return None


def _covered_ratio(iv: tuple[float, float], intervals: list[tuple[float, float]]) -> float:
    """区间 iv 被 intervals 覆盖的比例（0~1）。"""
    a, b = iv
    if b <= a:
        return 0.0
    segs = []
    for s, e in intervals:
        s2, e2 = max(s, a), min(e, b)
        if e2 > s2:
            segs.append((s2, e2))
    if not segs:
        return 0.0
    segs.sort()
    tot, cs, ce = 0.0, segs[0][0], segs[0][1]
    for s, e in segs[1:]:
        if s > ce:
            tot += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    tot += ce - cs
    return tot / (b - a)


# ---------------------------------------------------------------- 1 规格

def check_spec(info: dict, expect_w: int, expect_h: int) -> dict:
    issues = []
    w, h = info.get("width", 0), info.get("height", 0)
    if (w, h) != (expect_w, expect_h):
        issues.append(f"分辨率 {w}x{h} ≠ 预期 {expect_w}x{expect_h}")
    fps = float(info.get("fps") or 0)
    if not (24.0 <= fps <= 31.0):
        issues.append(f"帧率 {fps} 不在 24~31（竖屏短视频应 30）")
    if not info.get("has_audio"):
        issues.append("无音轨")
    dur = float(info.get("duration") or 0)
    if dur <= 0.5:
        issues.append(f"时长 {dur:.2f}s ≤ 0.5s")
    r = result(issues)
    r["spec"] = f"{w}x{h}@{fps}"
    r["duration"] = round(dur, 2)
    return r


# ---------------------------------------------------------------- 2 字幕排版

def check_subtitle_layout(subs: list[dict], meta: dict, duration: float,
                          overlap_tol: float = OVERLAP_TOL) -> dict:
    """
    逐条断言字幕排版与时间轴。任何一条不满足即 FAIL：
      - 文本不含 \\n / \\r / \\N（ASS 软换行）
      - lines == 1（单行不折行）
      - width_px <= max_px —— **并用 PIL 按 meta 字体独立复测**，不信上游数值
      - start < end、落在 [0, duration]、按 start 升序
      - 相邻 cue 零重叠（容差 overlap_tol）
    """
    issues: list[str] = []
    warns: list[str] = []
    notes: list[str] = []
    if not subs:
        r = result([], skipped=True)
        r["notes"] = ["subs_debug.json 缺失或无字幕条目，排版检查跳过"]
        return r

    font_file = resolve_font_file(meta.get("font"))
    font_size = int(meta.get("font_size") or 0) or None
    if meta.get("font") and not font_file:
        notes.append(f"字体 {meta.get('font')!r} 无法解析为字体文件，PIL 复测跳过")
    width_checked = 0
    lines_checked = 0

    prev_start = None
    prev_end = None
    for i, d in enumerate(subs):
        text = d.get("text") or ""
        head = text[:18]

        # --- 换行符 ---
        if ("\n" in text) or ("\r" in text) or ("\\N" in text) or ("\\n" in text):
            issues.append(f"#{i} 含换行符（单行字幕不得折行）: {text[:24]!r}")

        # --- lines == 1 ---
        if d.get("lines") is not None:
            lines_checked += 1
            try:
                if int(d["lines"]) != 1:
                    issues.append(f"#{i} lines={d['lines']}（应=1）: {head}")
            except Exception:
                issues.append(f"#{i} lines 字段非法: {d.get('lines')!r}")

        # --- 宽度：上游数值 ---
        wpx, maxpx = d.get("width_px"), d.get("max_px")
        if wpx is not None and maxpx is not None:
            width_checked += 1
            if float(wpx) > float(maxpx) + MAX_PX_TOL:
                issues.append(f"#{i} 超宽 width_px={wpx} > max_px={maxpx} "
                              f"（溢出 {float(wpx) - float(maxpx):.1f}px）: {head}")
        # --- 宽度：PIL 独立复测 ---
        if font_file and font_size and maxpx is not None:
            measured = measure_text_px(text, font_file, font_size)
            if measured is not None:
                width_checked += 1
                if measured > float(maxpx) + MAX_PX_TOL:
                    issues.append(f"#{i} 实测超宽 {measured:.1f}px > max_px={maxpx} "
                                  f"（上游报 {wpx}；字体 {meta.get('font')} {font_size}px）: {head}")

        # --- 时间轴 ---
        try:
            s = float(d["start"])
            e = float(d["end"])
        except Exception:
            issues.append(f"#{i} start/end 缺失或非法: {d.get('start')!r}/{d.get('end')!r}")
            s = e = None
        if s is not None:
            if e <= s:
                issues.append(f"#{i} start>=end ({s}→{e}): {head}")
            if s < -0.001 or e > duration + 0.5:
                issues.append(f"#{i} 时间越界 [{s}, {e}]，成片 {duration:.2f}s: {head}")
            if prev_start is not None and s < prev_start - 1e-6:
                issues.append(f"#{i} 未按 start 升序（前一条 {prev_start}）: {head}")
            # --- 相邻零重叠 ---
            if prev_end is not None:
                ov = prev_end - s
                if ov > overlap_tol:
                    issues.append(f"#{i} 与上一条重叠 {ov:.3f}s（容差 {overlap_tol}s）: {head}")
                elif ov > 1e-6:
                    warns.append(f"#{i} 与上一条重叠 {ov:.3f}s（未超容差 {overlap_tol}s，"
                                 f"零容忍请用 --overlap-tol 0）: {head}")
            prev_start, prev_end = s, e

    if width_checked == 0:
        notes.append("上游未提供 width_px/max_px 且无可用字体，宽度检查跳过")
    if lines_checked == 0:
        notes.append("上游未提供 lines 字段，lines==1 断言跳过")

    r = result(issues)
    r["warns"] = warns[:DETAIL_LIMIT]
    r["notes"] = notes
    r["cues"] = len(subs)
    return r


# ---------------------------------------------------------------- 3 对齐

def _find_edl_row(rows: list[dict], d: dict) -> dict | None:
    """定位一条字幕对应的 EDL 段：优先 source_id/index，其次 ep + 源时间落在段内。"""
    sid = d.get("source_id", d.get("seg"))
    if sid is not None:
        for r in rows:
            if str(r["index"]) == str(sid):
                return r
    ep = d.get("ep")
    ss = d.get("source_start")
    if ep and ss is not None:
        try:
            ss = float(ss)
        except Exception:
            return None
        for r in rows:
            if r["ep"] == ep and r["final_in"] - 0.5 <= ss <= r["final_out"] + 0.5:
                return r
    return None


def check_align(subs: list[dict], work, tol: float = ALIGN_TOLERANCE) -> dict:
    """
    用 EDL 反算字幕应在的成片时间，与字幕实际 start 比对。
    期望 = tl_in + (source_start - final_in)。
    偏差 > tol 说明 S6 时间码重映射算错了（成片里表现为"字幕看着挺对其实全错位"）。
    """
    rows = _load_edl(work)
    if not rows:
        r = result([], skipped=True)
        r["notes"] = [f"缺少 {Path(work) / 'edl.csv'}，对齐检查跳过"]
        return r
    if not subs:
        r = result([], skipped=True)
        r["notes"] = ["无字幕条目，对齐检查跳过"]
        return r

    issues: list[str] = []
    matched = 0
    for i, d in enumerate(subs):
        if d.get("source_start") is None:
            continue
        row = _find_edl_row(rows, d)
        if row is None:
            issues.append(f"#{i} 找不到对应 EDL 段 "
                          f"(ep={d.get('ep')}, source_id={d.get('source_id') or d.get('seg')}): "
                          f"{(d.get('text') or '')[:18]}")
            continue
        try:
            ss = float(d["source_start"])
            s = float(d["start"])
        except Exception:
            continue
        matched += 1
        expect = row["tl_in"] + (ss - row["final_in"])
        diff = abs(s - expect)
        if diff > tol:
            issues.append(f"#{i} 偏差 {diff:.3f}s：期望 {expect:.2f}s 实际 {s:.2f}s "
                          f"（段#{row['index']} {row['ep']}）: {(d.get('text') or '')[:18]}")
    if matched == 0:
        r = result(issues, skipped=True)
        r["notes"] = ["subs_debug.json 未记录 source_start/source_end，无法做时间轴反算"
                      "（需新版 S6）"]
        r["matched"] = 0
        return r
    r = result(issues)
    r["matched"] = matched
    r["tol"] = tol
    return r


# ---------------------------------------------------------------- 4 完整性

def check_speech_coverage(subs: list[dict], work) -> dict:
    """
    「有话必有字幕」核验：用 S5 检测到的**原字幕时间窗**（= 原片实际出声/出字幕的时刻）
    作为"有话"的证据，逐窗检查新字幕是否覆盖。

    - 读canvas_info.json 的 windows（auto 模式记录）；非 auto 模式无记录则跳过。
    - 每个原字幕窗 [t0,t1] 内，新字幕的时间覆盖比例必须 >= COVER_MIN；
      不足即视为"这段有话但没字幕/字幕太短" → FAIL。
    - 这是对"不能漏字幕"最直接的量化校验。
    """
    ci = _load_json(Path(work) / "canvas_info.json")
    if not ci:
        r = result([], skipped=True)
        r["notes"] = ["缺少 canvas_info.json，无法用原字幕窗核验语音覆盖"]
        return r
    windows = ci.get("windows") or []
    if not windows:
        r = result([], skipped=True)
        r["notes"] = ["canvas_info 非 auto 模式或无字幕窗记录，语音覆盖检查跳过"]
        return r
    if not subs:
        return result([f"检测到 {len(windows)} 个原字幕窗（有话），但新字幕为 0 条："
                       f"完全漏字幕"])

    iv = []
    for s in subs:
        try:
            iv.append((float(s["start"]), float(s["end"])))
        except Exception:
            pass
    iv.sort()

    def cov(a: float, b: float) -> float:
        span = b - a
        if span <= 1e-6:
            return 0.0
        tot, cs, ce = 0.0, None, None
        for x, y in iv:
            s2, e2 = max(x, a), min(y, b)
            if e2 > s2:
                if cs is None:
                    cs, ce = s2, e2
                elif s2 > ce:
                    tot += ce - cs; cs, ce = s2, e2
                else:
                    ce = max(ce, e2)
        if cs is not None:
            tot += ce - cs
        return tot / span

    gaps = []
    worst = 1.0
    for i, wd in enumerate(windows):
        a, b = float(wd["t0"]), float(wd["t1"])
        # 检测窗两端有软边（edge 外扩 + gap 合并），边界会略微超出真实字幕。
        # 向内各收TRIM 秒再量覆盖，避免把"边界检测误差"误判成漏字幕。
        span0 = b - a
        a2, b2 = a + SPEECH_EDGE_TRIM, b - SPEECH_EDGE_TRIM
        if b2 - a2 < span0 * 0.3:      # 窗太短则不裁边
            a2, b2 = a, b
        c = cov(a2, b2)
        worst = min(worst, c)
        if c < SPEECH_COVER_MIN:
            gaps.append(f"原字幕窗#{i} [{a:.2f}-{b:.2f}]（{span0:.1f}s 有话）"
                        f"新字幕仅覆盖 {c*100:.0f}% < {SPEECH_COVER_MIN*100:.0f}%")
    r = result(gaps)
    r["windows"] = len(windows)
    r["worst_coverage"] = round(worst, 3)
    r["notes"] = [f"按 {len(windows)} 个原字幕窗核验语音覆盖，"
                  f"最低覆盖 {worst*100:.0f}%（阈值 {SPEECH_COVER_MIN*100:.0f}%）"]
    return r


def check_completeness(subs: list[dict], work, duration: float) -> dict:
    """
    EDL 覆盖范围内每条 ASR 句，按覆盖率 >=0.7 判定"应出现"：
      - 应出现却既不在 subs_debug 也不在 subs_dropped → FAIL
      - 在 subs_dropped（有 reason）→ WARN
    """
    rows = _load_edl(work)
    asr = _load_json(Path(work) / "asr.json")
    if not rows or not asr:
        r = result([], skipped=True)
        r["notes"] = ["缺少 edl.csv 或 asr.json，完整性检查跳过"]
        return r

    dropped = (_load_json(Path(work) / "subs_dropped.json") or {})
    drop_items = dropped.get("items") or []
    sub_texts = [_norm(s.get("text")) for s in subs]
    sub_iv = []
    for s in subs:
        try:
            sub_iv.append((float(s["start"]), float(s["end"])))
        except Exception:
            pass
    drop_texts = {_norm(x.get("text")) for x in drop_items}

    expected: list[dict] = []
    for row in rows:
        fin, fout, tl_in = row["final_in"], row["final_out"], row["tl_in"]
        for s in (asr.get("episodes", {}).get(row["ep"], {}) or {}).get("sentences", []):
            try:
                a, b = float(s["start"]), float(s["end"])
            except Exception:
                continue
            ov = max(0.0, min(b, fout) - max(a, fin))
            span = max(1e-6, b - a)
            if ov / span < COVERAGE_MIN:
                continue
            expected.append({
                "ep": row["ep"], "seg": row["index"], "text": s.get("text", ""),
                "coverage": round(ov / span, 3),
                "tl_a": tl_in + (max(a, fin) - fin),
                "tl_b": tl_in + (min(b, fout) - fin),
            })

    missing, dropped_hit = [], []
    for e in expected:
        nt = _norm(e["text"])
        hit = _covered_ratio((e["tl_a"], e["tl_b"]), sub_iv) >= SUB_HIT_RATIO
        if not hit:
            for st in sub_texts:
                if nt and st and (nt in st or st in nt):
                    hit = True
                    break
        if hit:
            continue
        if nt in drop_texts:
            reason = ""
            for x in drop_items:
                if _norm(x.get("text")) == nt:
                    reason = x.get("reason") or ""
                    break
            dropped_hit.append(f"{e['ep']} 「{e['text'][:20]}」显式丢弃"
                               f"（reason={reason or '空'}）")
        else:
            missing.append(f"{e['ep']} @{e['tl_a']:.2f}-{e['tl_b']:.2f}s 覆盖率{e['coverage']} "
                           f"「{e['text'][:24]}」未进字幕且未记录丢弃")

    r = result(missing)
    r["expected"] = len(expected)
    r["dropped"] = len(dropped_hit)
    r["warns"] = dropped_hit[:DETAIL_LIMIT]
    return r


# ---------------------------------------------------------------- 5 首尾

def check_head_tail(subs: list[dict], duration: float, audio_start: float = 0.0) -> dict:
    issues = []
    if subs:
        try:
            if float(subs[0]["start"]) < audio_start - 0.10:
                issues.append(f"首条字幕 {float(subs[0]['start']):.2f}s 早于音轨起点 "
                              f"{audio_start:.2f}s（可能吞字头）: {(subs[0].get('text') or '')[:18]}")
            if float(subs[-1]["end"]) > duration + 0.10:
                issues.append(f"末条字幕 {float(subs[-1]['end']):.2f}s 超出成片时长 "
                              f"{duration:.2f}s: {(subs[-1].get('text') or '')[:18]}")
        except Exception:
            issues.append("字幕 start/end 字段非法，无法做首尾检查")
    return result(issues)


# ---------------------------------------------------------------- 7 原字幕清理

def _hf_energy(im_l, box) -> float | None:
    """区域高频能量：相邻像素差绝对值均值（水平+垂直平均）。"""
    from PIL import ImageChops, ImageStat

    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    reg = im_l.crop((x0, y0, x1, y1))
    dx = ImageChops.difference(reg.crop((0, 0, w - 1, h)), reg.crop((1, 0, w, h)))
    dy = ImageChops.difference(reg.crop((0, 0, w, h - 1)), reg.crop((0, 1, w, h)))
    return (ImageStat.Stat(dx).mean[0] + ImageStat.Stat(dy).mean[0]) / 2.0


def check_cleanup(work, video: str, info: dict, qcdir, expect_w: int, expect_h: int) -> dict:
    """
    原片烧录字幕是否清理掉：
      - canvas_info.json 缺失 → FAIL（无法证明清理过）
      - mode=blur/mask：断言 applied==true 且 rect 合法 → 否则 FAIL
      - 抽中间一帧，比较清理区 vs 上方对照区的高频能量 → 只 WARN
        （能量低不能自动证明原字消失，最终必须人眼看）
    """
    ci = _load_json(Path(work) / "canvas_info.json")
    if ci is None:
        return result([f"缺少 {Path(work) / 'canvas_info.json'}，无法证明原片字幕带已清理"
                       f"（需新版 S5 输出该契约）"])

    mode = str(ci.get("mode") or "off").lower()
    if mode == "off":
        r = result([], skipped=True)
        r["notes"] = ["canvas_info.json mode=off（未启用原字幕清理），跳过"]
        r["mode"] = mode
        return r
    if mode == "auto":
        # 自适应模糊：逐窗按实际字幕带处理。核验点：
        #   - applied==true（至少检测到并处理了一个字幕窗）
        #   - 每个窗的 box 都在画面内
        issues = []
        wins = ci.get("windows") or []
        if ci.get("applied") is not True:
            issues.append(f"canvas_info mode=auto 但 applied={ci.get('applied')!r}（应为 true）")
        if not wins:
            issues.append("canvas_info mode=auto 但未记录任何字幕窗（windows 为空）")
        ow = int(ci.get("out_width") or expect_w)
        oh = int(ci.get("out_height") or expect_h)
        for i, wd in enumerate(wins[:DETAIL_LIMIT]):
            try:
                wx0, wy0 = float(wd["x0"]), float(wd["y0"])
                wx1, wy1 = float(wd["x1"]), float(wd["y1"])
            except Exception:
                issues.append(f"auto 字幕窗 #{i} box 字段非法: {wd!r}")
                continue
            if not (0 <= wx0 and wx1 < ow and 0 <= wy0 and wy1 < oh):
                issues.append(f"auto 字幕窗 #{i} box 越出画面: "
                              f"({wx0},{wy0})-({wx1},{wy1}) 画布 {ow}x{oh}")
        r = result(issues)
        r["mode"] = mode
        r["windows"] = len(wins)
        r["sigma"] = ci.get("sigma")
        r["notes"] = [f"自适应字幕模糊：{len(wins)} 个字幕窗，"
                      f"sigma={ci.get('sigma')}，逐窗按实际 box 处理；"
                      f"无字幕帧未做模糊（按需求）"]
        return r
    if mode not in ("blur", "mask"):
        return result([f"canvas_info.json mode={mode!r} 非 off/blur/mask/auto，契约非法"])

    issues = []
    if ci.get("applied") is not True:
        issues.append(f"canvas_info.json mode={mode} 但 applied={ci.get('applied')!r}（应为 true）")

    ow = int(ci.get("out_width") or expect_w)
    oh = int(ci.get("out_height") or expect_h)
    rect = ci.get("rect") or {}
    try:
        rx, ry, rw, rh = (float(rect["x"]), float(rect["y"]),
                          float(rect["w"]), float(rect["h"]))
    except Exception:
        issues.append(f"canvas_info.json rect 缺失或非法: {rect!r}")
        rx = ry = rw = rh = None
    if rw is not None:
        if rw <= 0 or rh <= 0:
            issues.append(f"rect 尺寸非法: w={rw} h={rh}")
        if not (0 <= rx and rx + rw <= ow and 0 <= ry and ry + rh <= oh):
            issues.append(f"rect 越出画面: rect=({rx},{ry},{rw},{rh}) 画布 {ow}x{oh}")

    r = result(issues)
    r["mode"] = mode
    r["rect"] = rect
    r["sigma"] = ci.get("sigma")

    # --- 能量对比（只 warn）---
    warns = []
    notes = []
    if rw and rw > 0 and rh > 0:
        try:
            qcdir = Path(qcdir)
            qcdir.mkdir(parents=True, exist_ok=True)
            dst = str(qcdir / "cleanup_probe.jpg")
            fe.extract_frame(video, max(0.0, float(info.get("duration") or 0) / 2.0),
                             dst, width=None)
            from PIL import Image

            im = Image.open(dst).convert("L")
            box = (rx, ry, rx + rw, ry + rh)
            e_rect = _hf_energy(im, box)
            ref_box = None
            if ry - rh >= 0:
                ref_box = (rx, ry - rh, rx + rw, ry)
            elif ry + 2 * rh <= im.height:
                ref_box = (rx, ry + rh, rx + rw, ry + 2 * rh)
            e_ref = _hf_energy(im, ref_box) if ref_box else None
            r["energy_rect"] = round(e_rect, 3) if e_rect is not None else None
            r["energy_ref"] = round(e_ref, 3) if e_ref is not None else None
            r["probe_frame"] = dst
            if e_rect is not None and e_ref:
                ratio = e_rect / e_ref
                r["energy_ratio"] = round(ratio, 3)
                if ratio > 0.60:
                    warns.append(f"清理区高频能量 {e_rect:.2f} vs 对照区 {e_ref:.2f} "
                                 f"（比值 {ratio:.2f} > 0.60）：原字幕可能没盖住，"
                                 f"必须人眼看 {dst}")
            else:
                notes.append("无法取到对照区，能量对比跳过")
        except Exception as exc:
            notes.append(f"清理区能量检查失败（不影响结论）: {str(exc)[:120]}")
    r["warns"] = warns
    r["notes"] = notes
    return r


# ---------------------------------------------------------------- 8/9 抽帧

def qc_frames(video: str, outdir: str, n: int, subs: list[dict] | None = None):
    """抽帧 + 亮度体检 + 拼联系表。times 与结果一一对应，抽帧失败保留占位。"""
    from PIL import Image, ImageDraw, ImageFont

    info = fe.probe(video)
    dur = float(info.get("duration") or 0)
    n = max(1, int(n))
    times = [dur * (i + 0.5) / n for i in range(n)] if dur > 0 else [0.0] * n

    results = []
    thumbs = []
    for i, t in enumerate(times):
        dst = str(Path(outdir) / f"qc{i:04d}.jpg")
        try:
            fe.extract_frame(video, t, dst, width=360)
        except Exception as exc:
            results.append({"t": round(t, 2), "file": None, "decoded": False,
                            "error": str(exc)[:160], "black": False, "has_sub": None})
            continue
        im = Image.open(dst).convert("L")
        px = list(im.tobytes())          # L 模式：1 字节 = 1 像素，避免 getdata 弃用告警
        mean = sum(px) / len(px)
        srt = sorted(px)
        p99 = srt[int(len(srt) * 0.99)]
        mx = srt[-1]
        is_black = (mean < BLACK_MEAN) and (p99 < BLACK_P99)
        has_sub = any(s["start"] <= t <= s["end"] for s in subs) if subs else None
        results.append({"t": round(t, 2), "file": dst, "decoded": True,
                        "mean": round(mean, 1), "p99": p99, "max": mx,
                        "black": is_black, "has_sub": has_sub})
        thumbs.append((t, dst, mean, has_sub, is_black))

    if not thumbs:
        return results, None, 0

    cols = 4
    cell_w, label_h = 360, 26
    first = Image.open(thumbs[0][1])
    cell_h = int(cell_w * first.height / first.width)
    rows = (len(thumbs) + cols - 1) // cols
    sheet_img = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), (16, 16, 18))
    draw = ImageDraw.Draw(sheet_img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for i, (t, f, mean, has_sub, is_black) in enumerate(thumbs):
        im = Image.open(f).convert("RGB").resize((cell_w, cell_h), Image.LANCZOS)
        x, y = (i % cols) * cell_w, (i // cols) * (cell_h + label_h)
        sheet_img.paste(im, (x, y))
        draw.rectangle([x, y + cell_h, x + cell_w, y + cell_h + label_h], fill=(32, 32, 35))
        flag = "黑!" if is_black else ("字幕" if has_sub else "")
        draw.text((x + 6, y + cell_h + 4),
                  f"t={t:6.2f}s  gray={mean:5.1f} {flag}",
                  fill=(240, 120, 110) if is_black else (235, 200, 110),
                  font=font)

    sheet_path = str(Path(outdir) / "qc_contact_sheet.jpg")
    sheet_img.save(sheet_path, quality=90)
    return results, sheet_path, len(thumbs)


# ---------------------------------------------------------------- main

def print_check(name: str, res: dict) -> None:
    if res.get("skipped"):
        mark = "SKIP"
    else:
        mark = "PASS" if res.get("pass") else "FAIL"
    print(f"  [{mark}] {name}", end="")
    if res.get("count"):
        print(f"  ({res['count']} 处异常)")
    else:
        print()
    for d in (res.get("detail") or [])[:5]:
        print(f"           · {d}")
    for w in (res.get("warns") or [])[:5]:
        print(f"           ~ {w}")
    for n in (res.get("notes") or [])[:5]:
        print(f"           - {n}")


def main():
    ap = argparse.ArgumentParser(description="S7 核验闸门（硬失败 exit 1）")
    ap.add_argument("--work", required=True)
    ap.add_argument("--video", default=None, help="默认 work/final.mp4")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--expect-w", type=int, default=1080)
    ap.add_argument("--expect-h", type=int, default=1920)
    ap.add_argument("--align-tol", type=float, default=ALIGN_TOLERANCE,
                    help="字幕-语音对齐容差（秒，默认 0.15）")
    ap.add_argument("--overlap-tol", type=float, default=OVERLAP_TOL,
                    help="相邻字幕允许重叠（秒，默认 0.02；0 表示零容忍）")
    ap.add_argument("--strict", dest="strict", action="store_true", default=True,
                    help="硬失败即 exit 1（默认）")
    ap.add_argument("--no-strict", dest="strict", action="store_false",
                    help="只报告不阻断（退出码恒为 0）")
    args = ap.parse_args()

    work = Path(args.work)
    video = args.video or str(work / "final.mp4")
    if not Path(video).exists():
        print(f"[S7] 找不到成片 {video}")
        sys.exit(1)

    info = fe.probe(video)
    dur = float(info.get("duration") or 0)

    dbg = _load_json(work / "subs_debug.json") or {}
    meta = dbg.get("meta") or {}
    subs = dbg.get("dialogues") or []

    print("=" * 62)
    print(f"[S7] 核验 {Path(video).name}  (work={work})")
    print(f"     规格 {info['width']}x{info['height']} @{info['fps']} / {dur:.2f}s / "
          f"{info['size_mb']}MB")
    print(f"     字幕 {len(subs)} 条 / 严格模式 {'开' if args.strict else '关'}")
    print("=" * 62)

    qcdir = work / "qc"
    qcdir.mkdir(parents=True, exist_ok=True)

    checks: list[tuple[str, dict]] = []
    checks.append(("成片规格", check_spec(info, args.expect_w, args.expect_h)))
    checks.append(("字幕排版", check_subtitle_layout(subs, meta, dur, args.overlap_tol)))
    checks.append(("字幕-语音对齐", check_align(subs, str(work), args.align_tol)))
    checks.append(("有话必有字幕", check_speech_coverage(subs, str(work))))
    checks.append(("台词完整", check_completeness(subs, str(work), dur)))
    checks.append(("首尾不吞字", check_head_tail(subs, dur)))

    lufs = fe.measure_lufs(video)
    lufs_ok = -17.5 <= lufs <= -14.5
    checks.append(("响度 -16±1.5", result([] if lufs_ok else [f"{lufs:.2f} LUFS 超出 -16±1.5"])))

    checks.append(("原字幕清理", check_cleanup(str(work), video, info, qcdir,
                                               args.expect_w, args.expect_h)))

    fr, sheet, nframes = qc_frames(video, str(qcdir), n=args.frames, subs=subs)
    ndecode_fail = sum(1 for r in fr if not r.get("decoded"))
    checks.append(("抽帧解码", result(
        [f"t={r['t']}s 抽帧失败: {r.get('error')}" for r in fr if not r.get("decoded")]
        or (["全部抽帧失败，无法做画面体检"] if nframes == 0 else []))))
    nblack = sum(1 for r in fr if r.get("black"))
    checks.append(("抽帧无黑场", result(
        [f"t={r['t']}s gray={r['mean']} p99={r.get('p99')}（mean<{BLACK_MEAN} 且 "
         f"p99<{BLACK_P99}）" for r in fr if r.get("black")])))

    print()
    for name, res in checks:
        print_check(name, res)

    fails = [n for n, r in checks if not r.get("skipped") and not r.get("pass", False)]
    skips = [n for n, r in checks if r.get("skipped")]

    report = {
        "video": video,
        "work": str(work),
        "duration": round(dur, 2),
        "lufs": round(lufs, 2),
        "spec": f"{info['width']}x{info['height']}@{info['fps']}",
        "expect": f"{args.expect_w}x{args.expect_h}",
        "subs_count": len(subs),
        "strict": args.strict,
        "frames_n": len(fr),
        "checks": {n: r for n, r in checks},
        "frames": fr,
        "contact_sheet": sheet,
        "hard_fails": fails,
        "skipped": skips,
    }
    fe.json_dump(report, str(work / "qc_report.json"))

    print()
    if sheet:
        print(f"  抽帧联系表 → {sheet}")
        nsub = sum(1 for r in fr if r.get("has_sub"))
        print(f"  {len(fr)} 帧中 {nsub} 帧带字幕 → "
              f"**字幕是否压脸必须人眼看这张图**")
    else:
        print("  [!] 无可用抽帧，联系表未生成")
    print("     ⚠ 人工目视项（字幕压脸 / 清理残留 / 观感）请查看联系表后确认")

    if fails:
        print(f"\n[S7] [!] 硬失败 {len(fails)} 项: {', '.join(fails)}")
        if args.strict:
            sys.exit(1)
        print("     --no-strict：仅报告，不阻断流水线")
    else:
        if skips:
            print(f"\n[S7] [OK] 自动检查全部通过（{len(skips)} 项跳过: {', '.join(skips)}）")
        else:
            print("\n[S7] [OK] 自动检查全部通过")


if __name__ == "__main__":
    main()

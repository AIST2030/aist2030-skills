#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原片硬字幕带检测（S5 自适应模糊用）。

思路：短剧原片的硬字幕是「白色字芯 + 黑色描边」，位于画面下部。
用「亮像素 且 其邻域存在暗像素（描边）」作为文字掩码，逐行统计得到字幕行带；
再在行带内取列范围，得到该帧字幕的实际包围盒。

输出两类信息，供 S5 精确模糊：
  - events：[{t, box}]  该帧有字幕时给出包围盒 (x0,y0,x1,y1)
  - 无字幕的帧不产生 event → S5 对这些帧不做任何模糊

按需求：模糊区域 = 检测到的字幕 box 上下左右各扩 PAD 像素（默认 1px）。
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

# 检测阈值
BRIGHT_T = 185        # 字芯亮度阈值（字幕为纯白，>185）
DARK_T = 75           # 描边/背景暗部阈值
DILATE_K = 5# 描边邻域膨胀核（3x3 一两次 ≈ 5x5），把字芯与描边关联
ROW_MIN_PX = 10       # 一行里至少这么多"文字像素"才算字幕行
BAND_MIN_H = 20# 字幕行带最小高度（像素）
BAND_MAX_H = 160      # 字幕行带最大高度（像素，超出视为误检）
BAND_MERGE_GAP = 8    # 相邻行带间隔 <= 该值则合并（上下两行字幕）
SEARCH_TOP_RATIO = 0.55   # 只在画面下部 55% 以下搜索字幕

_K5 = np.ones((DILATE_K, DILATE_K), bool)


def detect_sub_box(gray: np.ndarray,
                   pad: int = 0, vpad: int = 0,
                   bright_t: int | None = None,
                   dark_t: int | None = None) -> tuple[int, int, int, int] | None:
    """
    在单帧灰度图里检测字幕包围盒。

    返回 (x0, y0, x1, y1)（含 pad / vpad 扩展），无字幕返回 None。
    灰度图 gray: HxW uint8。
    bright_t / dark_t：检测阈值可覆盖（qc_leak 用放宽阈值抓模糊残留）。
    """
    b_t = BRIGHT_T if bright_t is None else bright_t
    d_t = DARK_T if dark_t is None else dark_t
    h, w = gray.shape[:2]
    y_top = int(h * SEARCH_TOP_RATIO)
    reg = gray[y_top:, :]

    bright = reg > b_t
    dark = reg < d_t
    dark_near = binary_dilation(dark, structure=_K5)
    # 文字像素 = 亮字芯 且 附近有暗描边
    textmask = bright & dark_near

    rowsum = textmask.sum(axis=1)
    on = rowsum > ROW_MIN_PX

    # 提取连续行段
    bands: list[list[int]] = []
    i = 0
    n = len(on)
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and on[j + 1]:
                j += 1
            bands.append([i, j])
            i = j + 1
        else:
            i += 1
    if not bands:
        return None

    # 合并邻近行带（同一句字幕的上下两行 / 字与描边分成两段）
    merged: list[list[int]] = []
    for b in bands:
        if merged and b[0] - merged[-1][1] <= BAND_MERGE_GAP:
            merged[-1][1] = b[1]
        else:
            merged.append(b)

    # 取最靠下、且高度合理的那条带作为字幕行（短剧字幕固定在下部）
    cand = [b for b in merged if BAND_MIN_H <= (b[1] - b[0] + 1) <= BAND_MAX_H]
    if not cand:
        return None
    b = max(cand, key=lambda x: x[1])

    ry0, ry1 = b
    band_mask = textmask[ry0:ry1 + 1]
    colsum = band_mask.sum(axis=0)
    cols = np.where(colsum > 0)[0]
    if len(cols) == 0:
        return None

    x0 = int(cols.min())
    x1 = int(cols.max())
    y0 = y_top + ry0
    y1 = y_top + ry1

    # pad 扩展（需求：左右各扩 1px；上下用 vpad 覆盖字形描边）
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - vpad)
    x1 = min(w - 1, x1 + pad)
    y1 = min(h - 1, y1 + vpad)
    return x0, y0, x1, y1


def scan_video(video: str, times: list[float],
               pad: int = 1, vpad: int = 0) -> list[tuple[float, tuple[int, int, int, int]]]:
    """
    在指定时间点抽帧并检测字幕盒。返回 [(t, (x0,y0,x1,y1)), ...]，仅含有字幕的帧。
    """
    import ffmpeg_env as fe

    out: list[tuple[float, tuple[int, int, int, int]]] = []
    for t in times:
        tmp = f"E:/_qc/_band_{t:07.2f}.png"
        try:
            fe.extract_frame(video, t, tmp, width=None)
            gray = np.array(Image.open(tmp).convert("L"))
        except Exception:
            continue
        box = detect_sub_box(gray, pad=pad, vpad=vpad)
        if box:
            out.append((t, box))
    return out


def build_windows(hits: list[tuple[float, tuple[int, int, int, int]]],
                  step: float, max_gap: float = 0.5,
                  edge: float = 0.08) -> list[dict]:
    """
    把逐帧命中合并成「字幕时间窗」。

    - 相邻命中间隔 <= max_gap 视为同一段字幕（桥接采样空隙，避免闪烁）
    - 每窗取内部所有 box 的**并集**作为该窗的模糊区域
    - 时间窗两端各扩 edge 秒，防止字幕首尾帧漏糊
    返回 [{t0, t1, x0, y0, x1, y1, w, h}, ...]
    """
    if not hits:
        return []
    ts = sorted(hits)
    groups: list[list[float]] = [[ts[0][0]]]
    for (t, _box) in ts[1:]:
        if t - groups[-1][-1] <= max_gap:
            groups[-1].append(t)
        else:
            groups.append([t])

    windows: list[dict] = []
    for g in groups:
        boxes = [b for (t, b) in hits if g[0] <= t <= g[-1]]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        windows.append({
            "t0": max(0.0, g[0] - edge),
            "t1": g[-1] + step + edge,
            "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "w": x1 - x0 + 1, "h": y1 - y0 + 1,
        })
    return windows


def detect_windows(video: str, duration: float, pad: int = 2, vpad: int = 5,
                   step: float = 0.2, max_gap: float = 0.5, edge: float = 0.22,
                   workdir: str = "E:/_qc") -> list[dict]:
    """
    对整片做一次扫描，返回字幕时间窗列表（供 S5 精确模糊）。

    pad  = 左右扩展像素（盖住字形两侧反锯齿光晕）
    vpad = 上下扩展像素（覆盖字形描边 + 光晕，防止字形上下缘漏糊）
    edge = 时间窗两端外扩秒数。**必须 ≥ 采样步长 step**：字幕在两次采样之间
           出现/消失时，首末命中点最多偏差一个 step，edge < step 会在窗的头尾
           各漏掉最多 step 秒的模糊 → 原字幕闪现漏出。默认 0.22 > 0.2 保零漏出。
    """
    n = int(duration / step) + 1
    times = [round(x * step, 3) for x in range(n)]
    hits: list[tuple[float, tuple[int, int, int, int]]] = []
    for t in times:
        tmp = f"{workdir}/_bw_{t:07.2f}.png"
        try:
            import ffmpeg_env as fe
            fe.extract_frame(video, t, tmp, width=None)
            gray = np.array(Image.open(tmp).convert("L"))
        except Exception:
            continue
        box = detect_sub_box(gray, pad=pad, vpad=vpad)
        if box:
            hits.append((t, box))
    return build_windows(hits, step=step, max_gap=max_gap, edge=edge)


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else r"E:\duanju_work\work\outputs\serial01\rough.mp4"
    times = [round(x * 0.5, 2) for x in range(0, int(58.53 * 2))]
    ev = scan_video(vid, times)
    print(f"{len(times)} 帧中 {len(ev)} 帧检测到字幕")
    for t, b in ev[:20]:
        print(f"  t={t:6.2f} box={b} w={b[2]-b[0]+1} h={b[3]-b[1]+1}")
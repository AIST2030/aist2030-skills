#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qc_leak · 原字幕「残留漏出」专项质检（S5/S7 之间跑，对象 = canvas.mp4）

三重检测，对象是**模糊后**的画面（canvas.mp4，不带新字幕，避免误伤）：
  1) 锐利字迹检测：用比 S5 检测**更宽**的阈值窗（bright>150 / dark<110）在
     每个字幕窗的时间点抽帧，只看窗 box ± 12px 的范围内——残留未糊的字
     （有黑描边、对比锐利）一定触发；平滑的模糊亮影不会触发（无暗描边相邻）。
  2) 高频能量检测：残留字形 = 高频纹理。抽帧统计 box 区域高频能量，
     与上方同尺寸对照区比较，比值 > 0.5 报异常。
  3) 亮影检测：box 区域均值比对照区亮出 25 以上 → 模糊没糊透（白字能量还在）。

用法：
  python qc_leak.py --work E:/duanju_work/work/outputs/serial01 \
      [--video canvas.mp4] [--strict]
任一残留 → exit 1（--strict），默认只报告。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

BRIGHT_LOOSE = 195   # 接近真字芯阈值：残留字形核心是纯白；皮肤高光多在 170-190
DARK_LOOSE = 60      # 真描边是纯黑；深色背景/阴影多在 60-110 之间
ROW_MIN_PX = 12      # 一行内 ≥12 个文字像素才算残留行
MIN_BAND_H = 15      # 命中行带高度 ≥15px 才像字（30px 字高的残迹）；散点噪声忽略
BOX_MARGIN = 12      # box 外扩检查范围（残留通常发生在 box 边缘）
HF_RATIO_MAX = 0.5   # 残留区/对照区 高频能量比上限（仅提示，场景纹理会误报）
LUMA_DIFF_MAX = 25.0 # 残留区比对照区允许的最大亮度差（模糊白字能量残留）
SAMPLES_PER_WIN = 3  # 每窗抽帧数：窗头 / 窗中 / 窗尾


def sharp_text_rows(im_l, box) -> tuple[int, int] | None:
    """
    在指定区域内找「锐利字迹」行：亮像素(>195) 且 邻域有暗像素(<60)。
    不做下部搜索偏置（与 sub_band 不同，这里的小块就是字幕带本身）。
    命中行带高度 < MIN_BAND_H 视为场景噪声（皮肤高光/衣领边缘）不报。
    返回 (首行, 末行)（相对区域顶部），无则 None。
    """
    import numpy as np
    from scipy.ndimage import binary_dilation
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    arr = np.asarray(im_l.crop((x0, y0, x1 + 1, y1 + 1)))
    bright = arr > BRIGHT_LOOSE
    dark = arr < DARK_LOOSE
    dark_near = binary_dilation(dark, structure=np.ones((5, 5), bool))
    rowsum = (bright & dark_near).sum(axis=1)
    rows = np.where(rowsum > ROW_MIN_PX)[0]
    if len(rows) == 0:
        return None
    if rows[-1] - rows[0] + 1 < MIN_BAND_H:
        return None
    return int(rows[0]), int(rows[-1])


def hf_energy(im_l, box):
    from PIL import ImageChops, ImageStat
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    reg = im_l.crop((x0, y0, x1, y1))
    dx = ImageChops.difference(reg.crop((0, 0, w - 1, h)), reg.crop((1, 0, w, h)))
    dy = ImageChops.difference(reg.crop((0, 0, w, h - 1)), reg.crop((0, 1, w, h)))
    return (ImageStat.Stat(dx).mean[0] + ImageStat.Stat(dy).mean[0]) / 2.0


def region_mean(im_l, box):
    from PIL import ImageStat
    return ImageStat.Stat(im_l.crop([int(v) for v in box])).mean[0]


def main():
    ap = argparse.ArgumentParser(description="原字幕残留漏出质检")
    ap.add_argument("--work", required=True)
    ap.add_argument("--video", default=None, help="默认 work/canvas.mp4")
    ap.add_argument("--strict", action="store_true", help="发现残留 exit 1")
    args = ap.parse_args()

    work = Path(args.work)
    video = args.video or str(work / "canvas.mp4")
    if not Path(video).exists():
        print(f"[qc_leak] 找不到 {video}")
        sys.exit(2)

    ci = json.loads((work / "canvas_info.json").read_text(encoding="utf-8"))
    windows = ci.get("windows") or []
    if not windows:
        print("[qc_leak] canvas_info 无字幕窗，无事可查")
        return

    # 参考原图信息：canvas 可能与检测时同尺寸
    oinfo = fe.probe(video)
    ow, oh = int(oinfo["width"]), int(oinfo["height"])

    issues: list[str] = []      # 硬问题（锐利字迹）
    warns: list[str] = []       # 提示级（高频/亮影，场景纹理会误报，须人看抽帧）
    stats = {"frames": 0, "sharp_hits": 0, "hf_warns": 0, "luma_warns": 0}
    qcdir = work / "qc_leak"
    qcdir.mkdir(parents=True, exist_ok=True)

    for wi, wd in enumerate(windows):
        t0, t1 = float(wd["t0"]), float(wd["t1"])
        bx0 = max(0, int(wd["x0"]) - BOX_MARGIN)
        by0 = max(0, int(wd["y0"]) - BOX_MARGIN)
        bx1 = min(ow - 1, int(wd["x1"]) + BOX_MARGIN)
        by1 = min(oh - 1, int(wd["y1"]) + BOX_MARGIN)
        band_h = by1 - by0
        # 对照区：字幕带上方同高区域
        ref_box = (bx0, max(0, by0 - band_h - 6), bx1, max(1, by0 - 6))

        # 窗内 3 个采样点（收边 0.05s 避开检测软边）
        span = t1 - t0
        ts = [t0 + span * f for f in (0.08, 0.5, 0.92)] if span > 0.4 else [(t0 + t1) / 2]
        for si, t in enumerate(ts):
            t = max(0.0, min(t, float(oinfo["duration"]) - 0.05))
            dst = str(qcdir / f"leak_w{wi:02d}_s{si}.png")
            try:
                fe.extract_frame(video, t, dst, width=None)
                from PIL import Image
                im = Image.open(dst).convert("L")
            except Exception as exc:
                issues.append(f"窗#{wi} t={t:.2f}s 抽帧失败: {str(exc)[:80]}")
                continue
            stats["frames"] += 1

            # 1) 锐利字迹（宽阈值 + 只看 box ± margin）
            hit = sharp_text_rows(im, (bx0, by0, bx1, by1))
            if hit:
                stats["sharp_hits"] += 1
                issues.append(
                    f"窗#{wi} t={t:.2f}s 疑似锐利字迹残留 行{hit[0]}-{hit[1]}"
                    f"/带高{by1-by0}（抽帧 {dst}）")

            # 2) 高频能量对比（提示级）
            e_box = hf_energy(im, (bx0, by0, bx1, by1))
            e_ref = hf_energy(im, ref_box)
            if e_box is not None and e_ref:
                ratio = e_box / e_ref
                if ratio > HF_RATIO_MAX:
                    stats["hf_warns"] += 1
                    warns.append(
                        f"窗#{wi} t={t:.2f}s 高频能量比 {ratio:.2f} > {HF_RATIO_MAX} "
                        f"（box={e_box:.2f} ref={e_ref:.2f}，疑似未糊净，须人看抽帧）")

            # 3) 亮影（提示级：模糊白字能量没摊掉）
            m_box = region_mean(im, (bx0, by0, bx1, by1))
            m_ref = region_mean(im, ref_box)
            if m_box - m_ref > LUMA_DIFF_MAX:
                stats["luma_warns"] += 1
                warns.append(
                    f"窗#{wi} t={t:.2f}s 亮度差 {m_box - m_ref:.1f} > {LUMA_DIFF_MAX} "
                    f"（box={m_box:.1f} ref={m_ref:.1f}，白字能量残留成亮带）")

    print(f"[qc_leak] {Path(video).name}: {len(windows)} 窗 / {stats['frames']} 帧")
    print(f"  锐利字迹命中 {stats['sharp_hits']} / 高频提示 {stats['hf_warns']} / "
          f"亮影提示 {stats['luma_warns']}")
    if warns:
        print("  ~ 提示明细（前 20 条，须人看抽帧确认）：")
        for s in warns[:20]:
            print(f"     ~ {s}")
    if issues:
        print("  [!] 硬问题明细（前 20 条）：")
        for s in issues[:20]:
            print(f"     · {s}")
        if args.strict:
            sys.exit(1)
    else:
        print("  [OK] 无锐利字迹残留；亮影/高频提示见上（0 提示 = 完全干净）")


if __name__ == "__main__":
    main()

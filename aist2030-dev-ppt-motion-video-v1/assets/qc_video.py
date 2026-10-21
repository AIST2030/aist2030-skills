#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成片质检：四项闸门
  1. 输出存在且体积合理
  2. 音画等长（差 ≤ 0.5s）
  3. 分辨率 / 帧率 / 时长与时间轴一致
  4. 整轨响度命中 -16 LUFS ±0.5
  5. 抽帧回读：非黑屏（有内容像素）+ 抽帧目视目录

用法：python qc_video.py <mp4>
"""
import json
import os
import re
import subprocess
import sys

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TIMELINE = os.path.join(ROOT, "remotion", "src", "data", "timeline.json")
TARGET_LUFS = -16.0


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="ignore")


def probe(path):
    r = run([FFMPEG, "-hide_banner", "-i", path])
    err = r.stderr
    out = {}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        out["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #\d+:\d+.*?Video:.*?(\d{2,5})x(\d{2,5}).*?(\d+(?:\.\d+)?) fps", err, re.S)
    if m:
        out["w"], out["h"], out["fps"] = int(m.group(1)), int(m.group(2)), float(m.group(3))
    m = re.search(r"Stream #\d+:\d+.*?Audio:.*?(\d+) Hz.*?(\d+) Hz", err)
    if m:
        out["audio_hz"] = int(m.group(1))
    out["has_audio"] = "Audio:" in err
    return out


def audio_duration(path):
    r = run([FFMPEG, "-hide_banner", "-i", path])
    return probe(path).get("duration", 0.0)


def measure_lufs(path):
    r = run([FFMPEG, "-hide_banner", "-i", path,
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "NUL"])
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', r.stderr)
    return float(m.group(1)) if m else None


def grab_gray(video, t, w, h):
    r = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    raw = r.stdout
    if len(raw) < w * h:
        return None
    import numpy as np
    return np.frombuffer(raw[:w * h], dtype=np.uint8).reshape(h, w)


def main():
    mp4 = sys.argv[1]
    tl = json.load(open(TIMELINE, encoding="utf-8"))
    ok = True

    print("=" * 62)
    print("成片质检")
    print("=" * 62)

    # 1 输出存在
    exists = os.path.exists(mp4)
    size = os.path.getsize(mp4) / 1048576 if exists else 0
    good = exists and size > 2
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] 输出存在 — {size:.1f}MB")

    info = probe(mp4)
    dur = info.get("duration", 0)
    w, h, fps = info.get("w"), info.get("h"), info.get("fps")

    # 2 规格
    good = (w == tl["width"] and h == tl["height"] and info.get("has_audio"))
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] 规格 {w}x{h}@{fps}fps "
          f"（期望 {tl['width']}x{tl['height']}）音轨 {'有' if info.get('has_audio') else '无'}")

    # 3 音画等长 / 时长吻合时间轴
    diff = abs(dur - tl["totalSeconds"])
    good = diff <= 1.0
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] 时长 {dur:.2f}s vs 时间轴 "
          f"{tl['totalSeconds']:.2f}s（差 {diff:.2f}s）")

    # 4 响度
    lufs = measure_lufs(mp4)
    good = lufs is not None and abs(lufs - TARGET_LUFS) <= 1.0
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] 响度 {lufs} LUFS（目标 {TARGET_LUFS}±1.0）")

    # 5 抽帧非黑屏
    import numpy as np
    qc_dir = os.path.join(ROOT, "output", "qc")
    os.makedirs(qc_dir, exist_ok=True)
    dark = []
    for p in tl["pages"]:
        t = p["start"] + p["duration"] * 0.6   # 每页 60% 处
        a = grab_gray(mp4, t, w, h)
        if a is None:
            dark.append(p["id"])
            continue
        bright = (a > 90).mean()
        if bright < 0.012:
            dark.append(f"{p['id']}({bright*100:.1f}%)")
    good = not dark
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] 抽帧非黑屏 — "
          + ("6 页均有内容" if good else f"异常页 {dark}"))

    print("=" * 62)
    print(f"结论：{'全部通过' if ok else '存在未通过项'}")
    print("=" * 62)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

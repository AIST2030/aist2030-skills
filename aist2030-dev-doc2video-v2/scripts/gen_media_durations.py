#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""扫描 remotion/public/media/*.mp4，实测每个素材的真实时长 →
remotion/src/data/mediaDurations.json（供 Remotion 播放列表排段用）。

用法: python gen_media_durations.py
"""
import json
import os
import re
import subprocess

import imageio_ffmpeg

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ 2026-10-20 修复：与 gen_narration.py 同款问题——产物固定写进 skill 安装目录，
#   导致项目侧 mediaDurations.json 永远是空 {}（播放列表排段全失效）。
#   改为「调用方工作目录优先」，cwd 下有 remotion/public/media 即视为项目根。
_CWD = os.getcwd()
if os.path.isdir(os.path.join(_CWD, "remotion", "public", "media")):
    PROJ = _CWD
MEDIA = os.path.join(PROJ, "remotion", "public", "media")
OUT = os.path.join(PROJ, "remotion", "src", "data", "mediaDurations.json")


def probe_dur(ff, path):
    r = subprocess.run([ff, "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def main():
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = {}
    if os.path.isdir(MEDIA):
        for fn in sorted(os.listdir(MEDIA)):
            if not fn.endswith(".mp4") or fn.startswith("_"):
                continue
            d = probe_dur(ff, os.path.join(MEDIA, fn))
            if d:
                out[fn] = round(d, 3)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[durations] {len(out)} 个素材 → {OUT}")
    for k, v in out.items():
        print(f"  {k:16s} {v:7.2f}s")


if __name__ == "__main__":
    main()

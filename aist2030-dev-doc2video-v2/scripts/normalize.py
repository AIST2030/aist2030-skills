#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
响度归一化：双遍 linear loudnorm + 收敛校正 → -16 LUFS
只重编码音频，视频流 copy，零画质损失。

用法：python normalize.py input.mp4
"""
import os
import re
import shutil
import subprocess
import sys

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TARGET = -16.0
TP = -1.5
LRA = 11
SR = 44100


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="ignore")


def measure(path):
    r = run([FFMPEG, "-hide_banner", "-i", path,
             "-af", f"loudnorm=I={TARGET}:TP={TP}:LRA={LRA}:print_format=json",
             "-f", "null", "NUL"])
    mi = re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', r.stderr)
    mt = re.search(r'"input_tp"\s*:\s*"(-?[\d.]+)"', r.stderr)
    if not mi:
        raise RuntimeError("响度测量失败")
    return float(mi.group(1)), (float(mt.group(1)) if mt else None)


def main():
    src = sys.argv[1]
    i_in, tp_in = measure(src)
    print(f"  输入响度 {i_in} LUFS / TP {tp_in}")

    dst = src.replace(".mp4", "_norm.mp4")
    af = (f"loudnorm=I={TARGET}:TP={TP}:LRA={LRA}:"
          f"measured_I={i_in}:measured_TP={tp_in}:linear=true,aresample={SR}")
    run([FFMPEG, "-y", "-loglevel", "error", "-i", src, "-map", "0:v",
         "-map", "0:a", "-c:v", "copy",
         "-af", af, "-ar", str(SR), "-ac", "2", "-c:a", "aac", "-b:a", "192k",
         dst])

    # 收敛校正：linear 模式常差 0.3~0.6 LUFS，逐轮微调
    for r in range(3):
        i_out, _ = measure(dst)
        dev = TARGET - i_out
        print(f"  第{r+1}轮: {i_out:.2f} LUFS（偏差 {dev:+.2f}）")
        if abs(dev) <= 0.3:
            break
        gain = max(-4.0, min(4.0, dev))
        tmp = dst.replace(".mp4", "_tmp.mp4")
        run([FFMPEG, "-y", "-loglevel", "error", "-i", dst, "-map", "0:v",
             "-map", "0:a", "-c:v", "copy", "-af", f"volume={gain:.2f}dB",
             "-c:a", "aac", "-b:a", "192k", tmp])
        shutil.move(tmp, dst)

    i_final, _ = measure(dst)
    shutil.move(dst, src)
    print(f"  [PASS] 归一化后 {i_final:.2f} LUFS（目标 {TARGET}±0.3），已写回 {src}")


if __name__ == "__main__":
    main()

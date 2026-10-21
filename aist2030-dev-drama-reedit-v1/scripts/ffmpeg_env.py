#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ffmpeg 环境解析 + 媒体探针（mini-probe，替代 ffprobe）

本机环境约束（2026-10-17 实测）：
  - 无系统级 ffmpeg / ffprobe
  - ffmpeg 由 imageio_ffmpeg 包提供：ffmpeg-win-x86_64-v7.1.exe
  - **无 ffprobe** → 本模块解析 `ffmpeg -i` 的 stderr 提取元数据

对外 API：
  ffmpeg_exe()                  -> str
  run(args, capture=True)       -> (returncode, stdout, stderr)
  probe(path)                   -> dict {duration, width, height, fps, ...}
  extract_frame(src, t, dst, w=None)
  cut_accurate(src, dst, start, dur, reencode=True)
  loudnorm_two_pass(src, dst, target_lufs=-16.0)
  has_audio(path) -> bool
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

# ---------------------------------------------------------------- ffmpeg 定位

_CANDIDATES = [
    r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe",
]


def ffmpeg_exe() -> str:
    """定位 ffmpeg 可执行文件。优先环境变量，其次 imageio_ffmpeg 随包二进制。"""
    env = os.environ.get("FFMPEG_BIN")
    if env and Path(env).exists():
        return env
    for p in _CANDIDATES:
        if Path(p).exists():
            return p
    try:  # 兜底：若本脚本跑在装了 imageio_ffmpeg 的 venv 里
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "找不到 ffmpeg。请设置环境变量 FFMPEG_BIN 指向 ffmpeg 可执行文件。"
        ) from exc


def run(args: list[str], capture: bool = True, timeout: int = 3600):
    """执行 ffmpeg。返回 (returncode, stdout, stderr)。"""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", *args]
    if capture:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return proc.returncode, proc.stdout.decode("utf-8", "ignore"), proc.stderr.decode("utf-8", "ignore")
    proc = subprocess.run(cmd, timeout=timeout)
    return proc.returncode, "", ""


# ---------------------------------------------------------------- 探针

_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", re.I)
_VID_RE = re.compile(
    r"Stream #\d+:\d+.*?Video:\s*([a-z0-9_]+).*?,\s*(\d+)x(\d+).*?(?:\[SAR\s*(\d+):(\d+)\])?",
    re.I,
)
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps", re.I)
_AUD_RE = re.compile(r"Stream #\d+:\d+.*?Audio:\s*([a-z0-9_]+)", re.I)
_SR_RE = re.compile(r"(\d+)\s*Hz", re.I)
_NF_RE = re.compile(r"Video:.*?(\d+)x(\d+).*?\((\w+)\)", re.I)


def probe(path: str) -> dict:
    """解析媒体元数据。无 ffprobe 环境下的替代方案。"""
    p = str(path)
    if not Path(p).exists():
        raise FileNotFoundError(p)
    # ffmpeg -i 不带输出会报错退出，但 stderr 里有完整信息
    _, _, err = run(["-i", p])
    info: dict = {"path": p, "exists": True}

    m = _DUR_RE.search(err)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        info["duration"] = h * 3600 + mi * 60 + s
    else:
        info["duration"] = 0.0

    mv = _VID_RE.search(err)
    if mv:
        info["vcodec"] = mv.group(1)
        info["width"] = int(mv.group(2))
        info["height"] = int(mv.group(3))
        if mv.group(4):
            info["sar"] = f"{mv.group(4)}:{mv.group(5)}"
    else:
        info.update({"vcodec": None, "width": 0, "height": 0})

    mf = _FPS_RE.search(err)
    if mf:
        fps = float(mf.group(1))
        # 用分数还原更精确的帧率（如 29.97）
        mfr = re.search(r"(\d+)/(\d+)\s*fps", err, re.I)
        if mfr:
            fps = float(Fraction(int(mfr.group(1)), int(mfr.group(2))))
        info["fps"] = round(fps, 5)
    else:
        info["fps"] = 30.0

    ma = _AUD_RE.search(err)
    info["has_audio"] = bool(ma)
    if ma:
        info["acodec"] = ma.group(1)
        ms = _SR_RE.search(err)
        info["sample_rate"] = int(ms.group(1)) if ms else 0

    info["size_mb"] = round(Path(p).stat().st_size / 1024 / 1024, 2)
    return info


def frame_count(duration: float, fps: float) -> int:
    return int(round(duration * fps))


# ---------------------------------------------------------------- 抽帧

def extract_frame(src: str, t: float, dst: str, width: int | None = None) -> str:
    """抽单帧。t 为秒。width 给定则按该宽度缩放（等比）。"""
    vf = f"scale={width}:-2" if width else "null"
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    # -ss 在 -i 之前（输入端 seek，现代 ffmpeg 已帧精确）
    rc, _, err = run(
        ["-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-vf", vf, "-q:v", "2", "-y", dst]
    )
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"抽帧失败 t={t}: {err[-400:]}")
    return dst


def extract_frames(src: str, times: list[float], outdir: str, prefix: str = "f", width: int = 320) -> list[str]:
    out = []
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        dst = str(outdir_path / f"{prefix}{i:04d}.jpg")
        try:
            extract_frame(src, t, dst, width=width)
            out.append(dst)
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- 剪辑

def cut_accurate(src: str, dst: str, start: float, dur: float,
                 width: int | None = None, fps: float | None = None,
                 crf: int = 18, preset: str = "veryfast") -> str:
    """
    帧精确剪切（重编码）。

    `-ss` 放 `-i` 之前：现代 ffmpeg 输入端 seek 会从关键帧解码并丢弃到目标点，
    已是帧精确。「-ss 必须放 -i 之后才准」是 ffmpeg 2.1 之前的过时说法。
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    vf = []
    if width:
        vf.append(f"scale={width}:-2:flags=lanczos")
    if fps:
        vf.append(f"fps={fps}")
    vfilter = ",".join(vf) if vf else "null"
    args = [
        "-ss", f"{start:.6f}", "-i", src, "-t", f"{dur:.6f}",
        "-vf", vfilter,
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
        "-y", dst,
    ]
    rc, _, err = run(args)
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"剪切失败 {src} @{start}+{dur}: {err[-600:]}")
    return dst


def to_intra(src: str, dst: str, crf: int = 16, preset: str = "veryfast",
             width: int | None = None) -> str:
    """
    转 all-intra（每帧都是关键帧的 IDR）。
    好处：之后任意时间点都能 stream copy 剪切，concat 零重编码。
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:-2:flags=lanczos" if width else "null"
    rc, _, err = run([
        "-i", src, "-vf", vf,
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-g", "1",                      # 每帧一个 GOP
        "-bf", "0",                      # 禁用 B 帧，避免 DTS 错位
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-y", dst,
    ])
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"all-intra 转码失败 {src}: {err[-600:]}")
    return dst


def concat_demuxer(clips: list[str], dst: str, workdir: str | None = None) -> str:
    """
    concat 解复用器拼接（零重编码）。

    前置条件：所有片段的编码/分辨率/帧率/SAR/采样率/声道完全一致。
    不一致时 concat filter 会更安全（重编码）。
    """
    clips = [str(Path(c).resolve()).replace("\\", "/") for c in clips]
    workdir = workdir or str(Path(dst).parent)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    lst = Path(workdir) / "concat_list.txt"
    lst.write_text("\n".join(f"file '{c}'" for c in clips), encoding="utf-8")
    rc, _, err = run([
        "-f", "concat", "-safe", "0",
        "-fflags", "+genpts",
        "-i", str(lst),
        "-c", "copy",
        "-movflags", "+faststart",
        "-y", dst,
    ])
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"concat 拼接失败: {err[-600:]}")
    return dst


# ---------------------------------------------------------------- 响度

_LUFS_INPUT_RE = re.compile(r'"input_i"\s*:\s*"?(-?[\d.]+)"?')
_LUFS_SUMMARY_RE = re.compile(r"I:\s*(-?[\d.]+)\s*LUFS")


def measure_lufs(src: str) -> float:
    """
    单遍测量整体响度（EBU R128 integrated loudness）。

    ⚠ ffmpeg 7.x 的 JSON 输出是 `"input_i" : "-16.02"`（冒号两侧有空格），
    早期版本可能是 `"input_i":"-16.02"`。正则必须用 `\\s*` 兼容两种，
    否则会静默返回 0.0 —— 表现为「响度 0.0 LUFS」这种明显荒谬的值。
    """
    rc, _, err = run(["-i", src, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                      "-f", "null", "-"])
    m = _LUFS_INPUT_RE.search(err)
    if m:
        return float(m.group(1))
    # 兜底：老版本只有 summary 行
    m2 = _LUFS_SUMMARY_RE.search(err)
    return float(m2.group(1)) if m2 else 0.0


def loudnorm_two_pass(src: str, dst: str, target_lufs: float = -16.0,
                      tp: float = -1.5, lra: float = 11.0,
                      keep_video_copy: bool = True) -> str:
    """
    双遍 loudnorm 归一化。视频流默认 copy 不重编码（省时省空间）。
    """
    # 第一遍：测量
    rc, _, err = run(["-i", src, "-af",
                      f"loudnorm=I={target_lufs}:TP={tp}:LRA={lra}:print_format=json",
                      "-f", "null", "-"])

    def g(k, default="0"):
        # ⚠ 必须 `\\s*` 兼容 `"k" : "v"` 与 `"k":"v"` 两种格式
        m = re.search(rf'"{re.escape(k)}"\s*:\s*"?(-?[\d.]+)"?', err)
        return m.group(1) if m else default

    measured_i, measured_tp = g("input_i"), g("input_tp")
    measured_lra, measured_thresh = g("input_lra"), g("input_thresh")
    offset = g("target_offset", "0")

    af = (f"loudnorm=I={target_lufs}:TP={tp}:LRA={lra}"
          f":measured_I={measured_i}:measured_TP={measured_tp}"
          f":measured_LRA={measured_lra}:measured_thresh={measured_thresh}"
          f":offset={offset}:linear=true:print_format=summary")

    args = ["-i", src, "-af", af]
    if keep_video_copy:
        args += ["-c:v", "copy"]
    else:
        args += ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", "-y", dst]
    rc2, _, err2 = run(args)
    if rc2 != 0 or not Path(dst).exists():
        raise RuntimeError(f"loudnorm 失败: {err2[-600:]}")
    return dst


# ---------------------------------------------------------------- 静音检测

_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silence(src: str, noise_db: float = -32.0, min_dur: float = 0.30) -> list[tuple[float, float]]:
    """
    静音检测，返回 [(start, end), ...]。

    参数选择（关键）：
      - ffmpeg 默认 noise=-60dB / d=2 对真实素材几乎必然返回 0 条，
        网上因此误传「silencedetect 坏了」。实际要用**比本底噪声高 5-10dB** 的值。
      - 录音室起始约 -45dB，家庭/短剧原片常伴 BGM，需按 -25~-32dB 起调实测。
      - d 取你愿意切的**最短停顿**；<0.25s 会切掉词间自然间隙，成片像勒索信。
    """
    _, _, err = run(["-vn", "-i", src, "-af",
                     f"silencedetect=noise={noise_db}dB:d={min_dur}",
                     "-f", "null", "-"])
    starts = [float(x) for x in _SIL_START.findall(err)]
    ends = [float(x) for x in _SIL_END.findall(err)]
    pairs = []
    for i in range(min(len(starts), len(ends))):
        s, e = starts[i], ends[i]
        if e > s:
            pairs.append((s, e))
    return pairs


# ---------------------------------------------------------------- 工具

def json_dump(obj, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def json_load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ffmpeg_env.py <媒体文件>")
        sys.exit(1)
    print(json.dumps(probe(sys.argv[1]), ensure_ascii=False, indent=2))

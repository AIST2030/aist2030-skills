#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S2b · 语音边界切点图谱（★BGM 素材的正解）

★为什么必须有这个模块（本项目实测踩坑）：
   短剧原片自带持续 BGM，**全片几乎没有绝对静音**。
   ep01 在 -40/-35/-32dB 下静音段均为 **0 个**（-22dB 也只有 1 个），
   纯 silencedetect 方案在这种素材上直接失效 —— 切点白名单是空的，
   "静音吸附"变成"无点可吸"，S3 全部退化为强制硬切，台词必被腰斩。

解法：用 **语音活动检测（VAD）** 而不是绝对静音。
   ffmpeg 的 silencedetect 判的是「整体响度低于阈值」，
   而 VAD 判的是「**这一段有没有人在说话**」——BGM 铺底不影响语音判定。
   台词段之间的间隙（说话人换气/句读停顿）就是天然切点，
   而且这些点**语义上必然安全**：没人说话的地方切不会吞字。

两条通道互补：
  A) ffmpeg silencedetect  → 绝对静音（无 BGM 的口播/录屏素材有效）
  B) FunASR fsmn-vad       → 语音边界（有 BGM 的影视素材有效）★短剧主用
两者合并成统一的 cut_points.json，S3 直接消费。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402
import asr_sensevoice as asr  # noqa: E402

# VAD 段合并参数
MIN_SPEECH_GAP = 0.22# 小于此值的间隙不算切点（会切碎词内停顿）
MAX_MERGE_GAP = 0.45  # 大于此值的间隙视为「说话人间隔」→ 绝对安全切点
SAFE_BAND = (0.10, 6.0)  # 可用切点的间隙时长范围


def vad_segments(audio_wav: str) -> list[tuple[float, float]]:
    """
    调 FunASR 内置 fsmn-vad，返回语音段 [(start,end), ...]。
    """
    ok, msg = asr.asr_available()
    if not ok:
        raise RuntimeError(f"ASR 环境不可用：{msg}")

    child = r'''
import os, sys, json
os.environ.setdefault("MODELSCOPE_CACHE", sys.argv[2])
os.environ.setdefault("HF_HOME", sys.argv[2])
from funasr import AutoModel
m = AutoModel(model="fsmn-vad", device="cpu", disable_update=True)
res = m.generate(input=sys.argv[1])
segs = [[round(s[0]/1000.0,3), round(s[1]/1000.0,3)] for s in res[0].get("value", [])]
print(json.dumps(segs))
'''
    cf = Path(asr.CACHE_ROOT) / "_vad_child.py"
    Path(asr.CACHE_ROOT).mkdir(parents=True, exist_ok=True)
    cf.write_text(child, encoding="utf-8")

    env = dict(os.environ)
    env["MODELSCOPE_CACHE"] = asr.CACHE_ROOT
    env["HF_HOME"] = asr.CACHE_ROOT
    p = subprocess.run([asr.ASR_PY, str(cf), audio_wav, asr.CACHE_ROOT],
                       capture_output=True, timeout=1800, env=env)
    out = p.stdout.decode("utf-8", "ignore").strip()
    if p.returncode != 0 or not out:
        raise RuntimeError(f"VAD 失败: {p.stderr.decode('utf-8','ignore')[-600:]}")
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("["):
            try:
                return [(a, b) for a, b in json.loads(line)]
            except json.JSONDecodeError:
                pass
    raise RuntimeError(f"VAD 输出无法解析: {out[-300:]}")


def build_cut_points(speech: list[tuple[float, float]], duration: float) -> dict:
    """
    从语音段推导切点白名单。

    逻辑：相邻语音段之间的间隙 = 说话人换气/句读停顿 = 天然安全切点。
      - 间隙 ≥ MAX_MERGE_GAP  → 标记 SAFE（极安全，随便切）
      - 间隙 ≥ MIN_SPEECH_GAP → 标记 OK（可切，但吸附时优先往中间偏）
      - 间隙 <  MIN_SPEECH_GAP → 丢弃（词内停顿，切了会断音）
    另外首尾也要给切点（片头之前/片尾之后）。
    """
    merged = []
    for s, e in sorted(speech):
        if merged and s - merged[-1][1] < 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    points = []
    # 片头切点
    if merged:
        if merged[0][0] >= 0.05:
            points.append((0.0, merged[0][0], "HEAD", merged[0][0]))

    for i in range(len(merged) - 1):
        gap_a, gap_b = merged[i][1], merged[i + 1][0]
        gap = gap_b - gap_a
        if gap < MIN_SPEECH_GAP:
            continue
        level = "SAFE" if gap >= MAX_MERGE_GAP else "OK"
        if not (SAFE_BAND[0] <= gap <= SAFE_BAND[1]) and level == "OK":
            continue
        points.append((round(gap_a, 3), round(gap_b, 3), level, round(gap, 3)))

    # 片尾切点
    if merged:
        tail = duration - merged[-1][1]
        if tail >= 0.05:
            points.append((round(merged[-1][1], 3), round(duration, 3), "TAIL", round(tail, 3)))

    n_safe = sum(1 for p in points if p[2] == "SAFE")
    return {
        "speech_segments": [[round(a, 3), round(b, 3)] for a, b in merged],
        "speech_count": len(merged),
        "speech_sec": round(sum(b - a for a, b in merged), 2),
        "cut_points": [{"start": a, "end": b, "level": lv, "gap": g} for a, b, lv, g in points],
        "count": len(points),
        "safe_count": n_safe,
    }


def main():
    ap = argparse.ArgumentParser(description="S2b 语音边界切点图谱（VAD）")
    ap.add_argument("--work", required=True)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    work = Path(args.work)
    catalog = fe.json_load(str(work / "catalog.json"))

    # 已有 silencedetect 结果则合并，没有就只建 VAD
    sil_path = work / "silences.json"
    sil = fe.json_load(str(sil_path)) if sil_path.exists() else {"episodes": {}}

    out = {
        "method": "fsmn-vad (语音活动检测)",
        "note": "BGM 素材下 silencedetect 失效，用 VAD 语音边界替代",
        "min_speech_gap": MIN_SPEECH_GAP,
        "max_merge_gap": MAX_MERGE_GAP,
        "episodes": {},
    }

    for ep in catalog["episodes"]:
        if args.only and ep["ep"] != args.only:
            continue
        print(f"[S2b] {ep['ep']} {ep['name']} VAD 分析中...")

        # 先转 16k 单声道 wav（VAD 要求）
        wav = work / "_tmp" / f"{ep['ep']}_16k.wav"
        wav.parent.mkdir(exist_ok=True)
        rc, _, err = fe.run(["-y", "-i", ep["file"], "-vn", "-ac", "1",
                             "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
        if rc != 0 or not wav.exists():
            print(f"       [!] 抽音轨失败: {err[-300:]}")
            continue

        try:
            speech = vad_segments(str(wav))
            res = build_cut_points(speech, ep["duration"])
        except Exception as exc:
            print(f"       [!] VAD 失败: {exc}")
            continue

        # 合并 silencedetect 的绝对静音点（作为补充通道）
        abs_sil = sil.get("episodes", {}).get(ep["ep"], {}).get("ranges", [])
        res["abs_silence"] = abs_sil
        res["abs_silence_count"] = len(abs_sil)
        res["file"] = ep["file"]
        res["duration"] = ep["duration"]

        out["episodes"][ep["ep"]] = res
        print(f"       语音段 {res['speech_count']} 个 / {res['speech_sec']}s "
              f"({res['speech_sec']/ep['duration']*100:.0f}%)")
        print(f"       切点 {res['count']} 个（其中 {res['safe_count']} 个 SAFE 级）")

    # 汇总
    tot_pts = sum(v["count"] for v in out["episodes"].values())
    tot_safe = sum(v["safe_count"] for v in out["episodes"].values())
    fe.json_dump(out, str(work / "cut_points.json"))
    print(f"\n[S2b] 完成 → {work / 'cut_points.json'}")
    print(f"     全片切点 {tot_pts} 个（SAFE {tot_safe} 个），"
          f"平均每集 {tot_pts/max(1,len(out['episodes'])):.0f} 个")


if __name__ == "__main__":
    main()

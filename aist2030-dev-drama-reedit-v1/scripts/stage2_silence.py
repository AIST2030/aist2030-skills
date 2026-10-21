#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S2 · 静音图谱

产出 silences.json：每集的合法切点区间 [(start, end), ...]

阈值选择是本阶段唯一的技术难点（详见 references/silence-snap.md）：
  - ffmpeg 默认 noise=-60dB / d=2 对真实素材几乎必然返回 0 条
  - 短剧原片自带 BGM/音效，底噪被垫高 → 阈值需按集实测
  - d 取你愿意切的**最短停顿**，<0.25s 会切碎词间自然间隙
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402


def analyze(src: str, noise_db: float, min_dur: float, sweep: list[float] | None = None) -> dict:
    """检测静音。sweep 传入多个阈值时对比覆盖率，辅助选阈值。"""
    pairs = fe.detect_silence(src, noise_db=noise_db, min_dur=min_dur)
    dur = fe.probe(src)["duration"]
    silent_sec = sum(e - s for s, e in pairs)
    return {
        "noise_db": noise_db,
        "min_dur": min_dur,
        "duration": round(dur, 3),
        "count": len(pairs),
        "silent_sec": round(silent_sec, 2),
        "silent_ratio": round(silent_sec / dur, 4) if dur else 0,
        "avg_len": round(silent_sec / len(pairs), 3) if pairs else 0,
        "ranges": [[round(s, 3), round(e, 3)] for s, e in pairs],
    }


def main():
    ap = argparse.ArgumentParser(description="S2 静音图谱")
    ap.add_argument("--work", required=True, help="工作目录（读 catalog.json）")
    ap.add_argument("--noise", type=float, default=-32.0, help="静音阈值 dB（默认 -32）")
    ap.add_argument("--min-dur", type=float, default=0.30, help="最短静音秒数（默认 0.30）")
    ap.add_argument("--sweep", action="store_true", help="多阈值对比，帮用户选参数")
    ap.add_argument("--only", default=None, help="只处理某一集，如 ep01")
    args = ap.parse_args()

    work = Path(args.work)
    catalog = fe.json_load(str(work / "catalog.json"))

    sweep_values = [-40.0, -35.0, -32.0, -28.0, -25.0, -22.0] if args.sweep else None
    out = {"noise_db": args.noise, "min_dur": args.min_dur, "episodes": {}}

    for ep in catalog["episodes"]:
        if args.only and ep["ep"] != args.only:
            continue
        if not ep["has_audio"]:
            print(f"  {ep['ep']}: 无音轨，跳过")
            out["episodes"][ep["ep"]] = {"ranges": [], "note": "无音轨"}
            continue

        print(f"[S2] {ep['ep']} {ep['name']}")
        if sweep_values:
            for nv in sweep_values:
                r = analyze(ep["file"], nv, args.min_dur)
                print(f"    noise={nv:>6.1f}dB  静音段 {r['count']:>3d} 个 / "
                      f"{r['silent_sec']:>6.1f}s ({r['silent_ratio']*100:>4.1f}%) / "
                      f"均长 {r['avg_len']:.2f}s")
            r = analyze(ep["file"], args.noise, args.min_dur)
        else:
            r = analyze(ep["file"], args.noise, args.min_dur)
            print(f"    noise={args.noise}dB → {r['count']} 个静音段 / "
                  f"{r['silent_sec']}s ({r['silent_ratio']*100:.1f}%) / 均长 {r['avg_len']}s")
            if r["count"] == 0:
                print("    [!] 零静音段 → 阈值太低（比底噪还低）。用 --sweep 重跑选阈值。")
            elif r["silent_ratio"] < 0.01:
                print("    [!] 静音极少 → 阈值可能太低；短剧有 BGM 垫底时需上调到 -25~-28。")
            elif r["silent_ratio"] > 0.45:
                print("    [!] 静音过多 → 阈值可能太高，会把台词间隙也当静音。")

        r["file"] = ep["file"]
        r["ep"] = ep["ep"]
        r["fps"] = ep["fps"]
        out["episodes"][ep["ep"]] = r

    fe.json_dump(out, str(work / "silences.json"))
    print(f"\n[S2] 完成 → {work / 'silences.json'}")


if __name__ == "__main__":
    main()

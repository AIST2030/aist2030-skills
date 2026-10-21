#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S3 · 高光定位 + 帧级静音吸附 ★本流水线核心能力

问题：短剧台词密集，按秒硬切会把话拦腰截断（「你凭什么污蔑我|诬陷」→ 观众只听到半句）。

解法（三步）：
  1. 秒 → 帧量化（round(t * fps)），消灭浮点误差
  2. 每个目标切点在 silences.json 里找**最近的静音区间**吸附
  3. 吸附后检查「切点是否落在字头上」：往静音区**中心偏移**，并留 padding

关键设计：
  - 吸附失败（附近无静音）不静默通过 → 标记 `snap: "FORCED"` 并告警
  - 出点吸附漂移超过 --max-drift 秒 → 回退到「入点 + 原定时长」，标记 `FALLBACK`
  - 产出 edl.csv 可人工改，下游全读它 → 人始终掌握最终控制权

两种吸附模式（--snap-mode）：
  center（默认，向后兼容）：切点落在间隙中心，两侧都留余量
  edge：入点贴间隙**结束**处（gap_end - pad），出点贴间隙**开始**处（gap_start + pad）
        → 保留尽可能多的有效内容，适合「一整句台词」类高光
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

# 吸附策略参数
DEFAULT_SEARCH_WINDOW = 3.0    # 在目标点 ±3s 内找静音
DEFAULT_PAD = 0.15             # 静音区两侧留白，防止切掉字头字尾
MIN_SILENCE_LEN = 0.22         # 短于此值的静音不作为切点（会切碎词间间隙）
DEFAULT_MAX_DRIFT = 0.5        # 出点吸附允许的最大漂移，超过则回退
# ★出点死守 0.5s，入点放宽到 1.5s：入点跑一点只是晚进入，出点跑掉会把 5s 的段吸成 14s
DEFAULT_MAX_DRIFT_IN = 1.5     # 入点吸附允许的最大漂移


def quantize(t: float, fps: float) -> int:
    """秒 → 帧号（消除浮点误差）。"""
    return int(round(t * fps))


def frame_to_sec(f: int, fps: float) -> float:
    return f / fps


def timecode(sec: float, fps: float) -> str:
    """秒 → HH:MM:SS:FF 时间码。"""
    total_frames = int(round(sec * fps))
    f = total_frames % int(round(fps))
    s = int(total_frames // int(round(fps)))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}:{f:02d}"


def load_cut_points(work: str, ep: str,
                    cache: dict | None = None
                    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    加载切点白名单。双通道合并：

      A) cut_points.json 的 VAD 语音边界（有 BGM 的影视素材主通道）
      B) silences.json 的绝对静音（无 BGM 的口播/录屏素材补充通道）

    返回 (preferred, fallback)：
      preferred = VAD 切点（更密、更贴近语义边界）
      fallback  = 绝对静音点（VAD 没覆盖到的地方兜底）

    ★cache：同一 ep 的 cut_points 在多条高光里完全一样，按 ep 缓存避免重复 IO
      （单集 20+ 条高光时，JSON 解析开销从 O(n) 降到 O(集数)）。
    """
    if cache is not None and ep in cache:
        return cache[ep]

    work_p = Path(work)
    vad_pts, sil_pts = [], []

    cp = work_p / "cut_points.json"
    if cp.exists():
        d = fe.json_load(str(cp))
        epd = d.get("episodes", {}).get(ep, {})
        for c in epd.get("cut_points", []):
            vad_pts.append((c["start"], c["end"]))

    sp = work_p / "silences.json"
    if sp.exists():
        d = fe.json_load(str(sp))
        for r in d.get("episodes", {}).get(ep, {}).get("ranges", []):
            sil_pts.append((r[0], r[1]))

    # VAD 点优先；补上绝对静音点（去重）
    merged = list(vad_pts)
    for s in sil_pts:
        if not any(abs((s[0] + s[1]) / 2 - (a + b) / 2) < 0.3 for a, b in merged):
            merged.append(s)
    result = (vad_pts, merged or sil_pts)
    if cache is not None:
        cache[ep] = result
    return result


def _progressive_candidates(target: float, usable: list[tuple[float, float]],
                            window: float) -> tuple[list[tuple[float, float]], float]:
    """
    ★渐进搜索：先在 ±window 内找，找不到就逐级扩大（×1.5、×2、×3），
    最后才判定 FORCED。短剧台词密集，±3s 内没间隙很常见，
    直接放弃会让大量切点退化成硬切，等于白做了 VAD。
    """
    for mult in (1.0, 1.5, 2.0, 3.0):
        w = window * mult
        cands = [(s, e) for s, e in usable if not (e < target - w or s > target + w)]
        if cands:
            return cands, w
    return [], window * 3.0


def snap_to_silence(target: float, silences: list[tuple[float, float]],
                    window: float = DEFAULT_SEARCH_WINDOW,
                    pad: float = DEFAULT_PAD,
                    min_len: float = MIN_SILENCE_LEN,
                    mode: str = "center",
                    kind: str = "in",
                    max_drift: float = DEFAULT_MAX_DRIFT) -> dict:
    """
    把目标切点吸附到最近的合法静音区/语音间隙。

    mode=center（默认）：切点 = 间隙中心
    mode=edge：
        kind=in  → 选「区间结束时刻」离目标最近的间隙，切点 = gap_end  - pad
        kind=out → 选「区间开始时刻」离目标最近的间隙，切点 = gap_start + pad
        ★要求 e-s >= max(min_len, 2*pad)，否则两侧留白会溢出间隙、切到字上

    返回 dict:
      snapped      吸附后的秒数
      snap         'SILENCE'（center）/ 'EDGE'（edge）/ 'FORCED'
      reason       说明
      candidates   窗口内所有候选切点（供人工挑选）
    """
    need = max(min_len, 2 * pad)          # edge 模式下两侧都要留 pad
    usable = [(s, e) for s, e in silences if (e - s) >= need]
    cands, w = _progressive_candidates(target, usable, window)

    if not cands:
        return {
            "snapped": round(target, 3),
            "snap": "FORCED",
            "reason": f"±{w:.1f}s 内无 {need:.2f}s 以上的可切间隙，强制切在原点（可能截断台词）",
            "candidates": [],
        }

    if mode == "edge":
        if kind == "out":
            best = min(cands, key=lambda se: abs(se[0] - target))
            snapped = best[0] + pad
            where = "开始处"
        else:
            best = min(cands, key=lambda se: abs(se[1] - target))
            snapped = best[1] - pad
            where = "结束处"
        tag = "EDGE"
        reason = (f"贴边吸附到语音间隙 {best[0]:.2f}-{best[1]:.2f}s 的{where}"
                  f"（长 {best[1]-best[0]:.2f}s，偏移 {snapped - target:+.2f}s）")
    else:
        def dist(sr):
            mid = (sr[0] + sr[1]) / 2
            return abs(mid - target)

        best = min(cands, key=dist)
        # 切点落在间隙中心（不是边缘）：两侧都留余量，切出来最自然
        snapped = (best[0] + best[1]) / 2
        tag = "SILENCE"
        reason = (f"吸附到语音间隙 {best[0]:.2f}-{best[1]:.2f}s（长 {best[1]-best[0]:.2f}s，"
                  f"偏移 {snapped - target:+.2f}s）")

    # 吸附距离过大时给出提示（人可能以为切在了想要的位置）
    drift = abs(snapped - target)
    if drift > window:
        reason += " ⚠偏移大"
    return {
        "snapped": round(snapped, 3),
        "snap": tag,
        "reason": reason,
        "drift": round(drift, 3),
        "candidates": [[round(s, 3), round(e, 3)] for s, e in cands[:5]],
    }


def in_gap(t: float, gaps: list[tuple[float, float]], tol: float) -> bool:
    """切点是否落在某个语音间隙内（允许 tol 容差）。"""
    for s, e in gaps:
        if s - tol <= t <= e + tol:
            return True
    return False


def build_edl(highlights: list[dict], catalog: dict, silences: dict,
              work_dir: str, window: float, pad: float,
              mode: str = "center", max_drift: float = DEFAULT_MAX_DRIFT,
              apply_snap: bool = True, out_csv: str | None = None,
              max_drift_in: float = DEFAULT_MAX_DRIFT_IN,
              output_id: str | None = None) -> dict:
    """
    highlights: [{"ep":"ep01","start":12.0,"dur":6.5,"note":"打脸"}, ...]

    out_csv      非空则直接写盘；为 None 时只返回 rows 不落盘（调用方自己写）
    max_drift    出点漂移限幅（默认 0.5s）
    max_drift_in 入点漂移限幅（默认 1.5s，比出点宽松）
    output_id    多成片场景下的成片 id，仅用于日志/告警定位
    """
    ep_map = {e["ep"]: e for e in catalog["episodes"]}
    rows = []
    warnings = []
    errors = []
    timeline = 0.0     # 在成片时间轴上的累计位置
    cp_cache: dict[str, tuple[list, list]] = {}   # 按 ep 缓存 cut_points

    for i, h in enumerate(highlights, 1):
        ep = h.get("ep")
        # ---- 参数校验（越界/非法直接判错，不静默产出错 EDL）----
        if ep not in ep_map:
            errors.append(f"#{i} 未知集号 {ep!r}（catalog 里只有 {sorted(ep_map)}）")
            continue
        try:
            start = float(h["start"])
            dur = float(h["dur"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"#{i} start/dur 缺失或非数值：{h}")
            continue
        if dur <= 0:
            errors.append(f"#{i} dur={dur} 非法（必须 > 0）")
            continue
        meta = ep_map[ep]
        ep_dur = float(meta.get("duration") or 0)
        if start < 0:
            errors.append(f"#{i} start={start} 非法（必须 >= 0）")
            continue
        if ep_dur > 0 and start >= ep_dur:
            errors.append(f"#{i} start={start} 超出 {ep} 时长 {ep_dur}s")
            continue

        fps = meta["fps"]
        # ★优先用 VAD 语音边界（BGM 素材唯一可行通道），silencedetect 仅作补充
        vad_pts, merged_pts = load_cut_points(work_dir, ep, cp_cache)
        if merged_pts:
            sil = merged_pts
            src_desc = f"VAD×{len(vad_pts)}" if vad_pts else "静音"
        else:
            sil = []
            src_desc = "无"

        # 1) 帧量化
        start_f = quantize(start, fps)
        dur_f = max(1, quantize(dur, fps))
        start_q = frame_to_sec(start_f, fps)
        end_q = frame_to_sec(start_f + dur_f, fps)
        req_dur = end_q - start_q

        if not apply_snap:
            # ★--no-apply-snap：真的只做帧量化，完全不吸附
            final_in, final_out = start_q, end_q
            r_in = {"snapped": round(start_q, 3), "snap": "QUANTIZED",
                    "reason": "--no-apply-snap：仅帧量化", "candidates": []}
            r_out = {"snapped": round(end_q, 3), "snap": "QUANTIZED",
                     "reason": "--no-apply-snap：仅帧量化", "candidates": []}
        else:
            # 2) 入点吸附（限幅比出点宽松，入点跑一点只是晚进入）
            r_in = snap_to_silence(start_q, sil, window, pad,
                                   MIN_SILENCE_LEN, mode, "in", max_drift_in)
            if r_in["snap"] != "FORCED" and abs(r_in["snapped"] - start_q) > max_drift_in:
                final_in_q = frame_to_sec(quantize(start_q, fps), fps)
                r_in["snap"] = "FALLBACK"
                r_in["reason"] = (f"入点漂移 {r_in['snapped'] - start_q:+.2f}s 超过 "
                                  f"{max_drift_in}s，回退到帧量化原点 {final_in_q:.2f}s")
                r_in["snapped"] = round(final_in_q, 3)

            # 3) 出点吸附 —— 必须维持原定片段时长，否则一段被吸成 3.5s
            #    而用户要的是 5s，观感节奏就乱了。
            #    做法：出点目标 = 吸附后入点 + 原定时长，再在该位置附近找间隙。
            target_out = r_in["snapped"] + req_dur
            r_out = snap_to_silence(target_out, sil, window, pad,
                                    MIN_SILENCE_LEN, mode, "out", max_drift)

            final_in, final_out = r_in["snapped"], r_out["snapped"]

            # 3a) 漂移过大 → 回退到「入点 + 原定帧量化时长」，标记 FALLBACK
            if r_out["snap"] != "FORCED" and abs(r_out["snapped"] - target_out) > max_drift:
                final_out = frame_to_sec(quantize(final_in + req_dur, fps), fps)
                r_out["snap"] = "FALLBACK"
                r_out["reason"] = (f"出点漂移 {r_out['snapped'] - target_out:+.2f}s 超过 "
                                   f"{max_drift}s，回退到「入点{final_in:.2f}s+原时长{req_dur:.2f}s」")

            # 3b) 出点被吸到入点之前/重合 → 同样回退
            if final_out <= final_in:
                final_out = frame_to_sec(quantize(final_in + req_dur, fps), fps)
                r_out["snap"] = "FALLBACK"
                r_out["reason"] = f"回退：入点{final_in:.2f}s + 原时长{req_dur:.2f}s"

        # 4) 夹到 [0, 集时长]，防止超出素材末尾产生空帧/报错
        if ep_dur > 0:
            if final_in < 0:
                final_in = 0.0
            if final_in > ep_dur - 1.0 / fps:
                final_in = max(0.0, ep_dur - 1.0 / fps)
            if final_out > ep_dur:
                final_out = ep_dur
            if final_out <= final_in:
                final_out = min(ep_dur, frame_to_sec(quantize(final_in, fps) + 1, fps))

        for tag, r in (("in", r_in), ("out", r_out)):
            if r["snap"] == "FORCED":
                warnings.append(f"#{i} {ep} {tag}点强制切：{r['reason']}")
            elif r["snap"] == "FALLBACK":
                warnings.append(f"#{i} {ep} {tag}点回退：{r['reason']}")

        # 5) 切点合法性检查：是否真的落在某个语音间隙里（容差 = pad）
        if sil and apply_snap:
            for tag, t in (("in", final_in), ("out", final_out)):
                if not in_gap(t, sil, pad + 1e-6):
                    warnings.append(
                        f"#{i} {ep} {tag}点 {t:.3f}s 未落在任何语音间隙内（容差 {pad}s）")

        seg_dur = round(final_out - final_in, 3)
        row = {
            "index": i,
            "ep": ep,
            "file": meta["file"],
            "fps": fps,
            "requested_in": round(start_q, 3),
            "requested_out": round(end_q, 3),
            "final_in": round(final_in, 3),
            "final_out": round(final_out, 3),
            "duration": seg_dur,
            "in_frame": quantize(final_in, fps),
            "out_frame": quantize(final_out, fps),
            "in_tc": timecode(final_in, fps),
            "out_tc": timecode(final_out, fps),
            "tl_in": round(timeline, 3),        # 成片时间轴位置
            "tl_out": round(timeline + seg_dur, 3),
            "in_snap": r_in["snap"],
            "out_snap": r_out["snap"],
            "src": src_desc,
            "in_reason": r_in["reason"],
            "out_reason": r_out["reason"],
            "note": h.get("note", ""),
        }
        rows.append(row)
        timeline += seg_dur

    res = {
        "segments": rows,
        "total_duration": round(timeline, 3),
        "warnings": warnings,
        "errors": errors,
        "search_window": window,
        "pad": pad,
        "snap_mode": mode,
        "max_drift": max_drift,
        "max_drift_in": max_drift_in,
        "apply_snap": apply_snap,
        "output_id": output_id,
        "edl_csv": None,
    }

    # 只有全部条目合法、且至少有一段时才落盘：绝不产出残缺 EDL
    if out_csv and not errors and rows:
        p = Path(out_csv)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        res["edl_csv"] = str(p)
    return res


def main():
    ap = argparse.ArgumentParser(description="S3 高光定位 + 静音吸附")
    ap.add_argument("--work", required=True)
    ap.add_argument("--highlights", default=None,
                    help='JSON 文件或内联 JSON：[{"ep":"ep01","start":12,"dur":6,"note":"打脸"}]')
    ap.add_argument("--highlights-json", dest="highlights_json", default=None,
                    help='内联 JSON 字符串（pipeline 多成片调度用，避免写临时文件）')
    ap.add_argument("--output-id", dest="output_id", default=None,
                    help="成片 id（多成片场景，仅用于日志定位）")
    ap.add_argument("--window", type=float, default=DEFAULT_SEARCH_WINDOW)
    ap.add_argument("--pad", type=float, default=DEFAULT_PAD)
    ap.add_argument("--max-drift", type=float, default=DEFAULT_MAX_DRIFT,
                    help="出点吸附允许的最大漂移（秒），超过则回退并标记 FALLBACK")
    ap.add_argument("--max-drift-in", type=float, dest="max_drift_in",
                    default=DEFAULT_MAX_DRIFT_IN,
                    help="入点吸附允许的最大漂移（秒），默认比出点宽松")
    ap.add_argument("--snap-mode", dest="snap_mode", default="center",
                    choices=["center", "edge"],
                    help="center=切点落在间隙中心（默认）；edge=入点贴间隙尾、出点贴间隙头")
    ap.add_argument("--apply-snap", action="store_true", default=True,
                    help="应用吸附（默认开）；加 --no-apply-snap 只量化不吸附")
    ap.add_argument("--no-apply-snap", dest="apply_snap", action="store_false")
    ap.add_argument("--out-edl", dest="out_edl", default=None,
                    help="输出 EDL 路径（默认 <work>/edl.csv）")
    args = ap.parse_args()

    work = Path(args.work)
    catalog = fe.json_load(str(work / "catalog.json"))
    silences = fe.json_load(str(work / "silences.json"))

    if args.highlights_json:
        highlights = json.loads(args.highlights_json)
    elif args.highlights:
        hl_arg = args.highlights
        if Path(hl_arg).exists():
            highlights = fe.json_load(hl_arg)
        else:
            highlights = json.loads(hl_arg)
    else:
        ap.error("需要 --highlights 或 --highlights-json 之一")
    if isinstance(highlights, dict):
        if isinstance(highlights.get("outputs"), list):
            ap.error("这是多成片清单，请用 pipeline.py 调度（它会按 id 逐个调用本脚本）")
        highlights = highlights.get("highlights", [])

    if not args.apply_snap:
        print("[S3] --no-apply-snap：仅帧量化，不做静音吸附")
    if args.snap_mode == "edge":
        print(f"[S3] 吸附模式 edge（pad={args.pad}s，要求间隙 >= {max(MIN_SILENCE_LEN, 2*args.pad):.2f}s）")

    out_csv = str(Path(args.out_edl)) if args.out_edl else str(work / "edl.csv")
    res = build_edl(highlights, catalog, silences, str(work),
                    args.window, args.pad,
                    mode=args.snap_mode, max_drift=args.max_drift,
                    apply_snap=args.apply_snap, out_csv=out_csv,
                    max_drift_in=args.max_drift_in, output_id=args.output_id)

    # ---- 硬错误优先：未知集/非法参数/空 EDL 一律非零退出，不产出残缺产物 ----
    if res["errors"]:
        print("\n[ERROR] EDL 生成失败，以下条目非法：")
        for e in res["errors"]:
            print(f"    × {e}")
        sys.exit(1)
    if not res["segments"]:
        print("\n[ERROR] EDL 为空（没有一条合法高光），拒绝产出空 EDL")
        sys.exit(1)

    rows = res["segments"]
    head = f"[S3]{'' if not args.output_id else ' ' + args.output_id}"
    print(f"\n{head} EDL → {res['edl_csv']}")
    print(f"     {len(rows)} 段 / 总时长 {res['total_duration']}s\n")
    print(f"{'#':<3}{'集':<7}{'入点':>12}{'出点':>12}{'时长':>7}{'入漂':>8}{'出漂':>8}{'时长差':>8}  "
          f"{'入吸附':<10}{'出吸附':<10}{'来源':<10}备注")
    max_in = max_out = max_grow = 0.0
    for r in rows:
        d_in = float(r["final_in"]) - float(r["requested_in"])
        d_out = float(r["final_out"]) - float(r["requested_out"])
        grow = float(r["duration"]) - (float(r["requested_out"]) - float(r["requested_in"]))
        max_in, max_out, max_grow = max(max_in, abs(d_in)), max(max_out, abs(d_out)), max(max_grow, abs(grow))
        print(f"{r['index']:<3}{r['ep']:<7}{r['in_tc']:>12}{r['out_tc']:>12}{r['duration']:>7.2f}"
              f"{d_in:>+8.2f}{d_out:>+8.2f}{grow:>+8.2f}  "
              f"{r['in_snap']:<10}{r['out_snap']:<10}{r.get('src',''):<10}{r['note']}")
    # 出点限幅守的是「相对目标出点的漂移」= 时长膨胀；入点限幅守的是绝对漂移
    print(f"     最大入点漂移 {max_in:.2f}s（限幅 {args.max_drift_in}s）"
          f" / 最大出点漂移 {max_out:.2f}s"
          f" / 最大时长膨胀 {max_grow:.2f}s（限幅 {args.max_drift}s）")

    if res["warnings"]:
        print("\n[!] 告警（这些切点可能截断台词，建议人工复核）：")
        for w in res["warnings"]:
            print(f"    · {w}")
    else:
        print("\n[OK] 全部切点均落在语音间隙内，无强制切/回退。")


if __name__ == "__main__":
    main()

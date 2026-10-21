#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
流水线编排器 · 支持一次产出 N 个独立连播成片

用法：
  python pipeline.py all --raw <素材目录> --work <工作根目录> --highlights three.json
  python pipeline.py probe|silence|vad|edl|cut|canvas|subs|verify  （单阶段重跑）
  python pipeline.py cut --work <工作根目录> --only serial02         （只跑一个成片）

目录约定（多成片架构）：
  共享（只跑一次，省算力）：
    <work>/catalog.json  silences.json  cut_points.json  asr.json
    <work>/mezz/                      ← 3 个成片共享同一份 mezzanine
  每成片独立：
    <work>/outputs/<id>/{edl.csv, clips/, rough.mp4, canvas.mp4,
                         final.ass, subs_debug.json, qc_report.json}
    <work>/outputs_manifest.json      ← 持久化 job 清单，使后续阶段无需再传 --highlights
  成片：
    <out-dir>/<id>.mp4  +  <out-dir>/manifest.json

设计要点：
  - 每个阶段独立可跑，中间产物全部落盘 → 断点续跑，失败不丢进度
  - 中间产物放在**大空间盘**（默认 E:），不占 C:（本机仅剩 2GB）
  - verify 阶段跑完所有 job 再聚合失败，不会因为第一个 job 挂掉就丢掉其它 job 的报告
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _os_replace(src: Path, dst: Path) -> None:
    os.replace(str(src), str(dst))

HERE = Path(__file__).parent

STAGES = ["probe", "silence", "vad", "edl", "cut", "canvas", "subs", "endcard",
          "verify"]
SHARED_STAGES = ["probe", "silence", "vad"]     # 与成片无关的共享阶段
JOB_STAGES = ["edl", "cut", "canvas", "subs", "endcard", "verify"]

DEFAULT_OUTPUT_ID = "final"                     # 旧格式（顶层数组）的默认成片 id
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def sh(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(HERE / script), *args]
    print(f"\n{'=' * 62}\n$ {Path(script).name} {' '.join(args)}\n{'=' * 62}")
    p = subprocess.run(cmd)
    return p.returncode


# ---------------------------------------------------------------- job 解析

def parse_highlights_source(src: str):
    """--highlights 既可以是 JSON 文件路径，也可以是内联 JSON 字符串。"""
    p = Path(src)
    if p.exists() and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(src)


def load_output_jobs(data) -> list[tuple[str, list[dict]]]:
    """
    兼容两种 highlights 结构，返回 [(id, highlights), ...]：

      新：[{"outputs":[{"id":"serial01","highlights":[{...}]}, ...]}]
      旧：顶层数组 [{"ep":"ep01",...}] → 视为单个输出，id = "final"
    """
    if isinstance(data, dict) and isinstance(data.get("outputs"), list):
        jobs = []
        for o in data["outputs"]:
            oid = str(o.get("id") or "").strip()
            hl = o.get("highlights")
            jobs.append((oid, hl if isinstance(hl, list) else []))
        return jobs
    if isinstance(data, list):
        return [(DEFAULT_OUTPUT_ID, data)]
    if isinstance(data, dict) and isinstance(data.get("highlights"), list):
        return [(DEFAULT_OUTPUT_ID, data["highlights"])]
    raise ValueError(
        "无法识别的 highlights 结构：需要 {outputs:[{id,highlights}]} 或顶层数组")


def load_jobs_from_manifest(work: Path) -> list[tuple[str, list[dict]]] | None:
    """从 <work>/outputs_manifest.json 恢复 job 清单（无需再次传 --highlights）。"""
    mf = work / "outputs_manifest.json"
    if not mf.exists():
        return None
    try:
        d = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[init] outputs_manifest.json 解析失败：{exc}")
        return None
    jobs = [(str(j["id"]), j["highlights"]) for j in d.get("jobs", [])
            if isinstance(j, dict) and j.get("id")]
    return jobs or None


def validate_jobs(jobs: list[tuple[str, list[dict]]], catalog: dict,
                  plan: dict | None) -> list[str]:
    """
    预检。任何一条不通过都直接退出，不浪费几十分钟去切注定失败的片。

      - id 唯一且只含安全字符（会用作目录名/文件名）
      - highlights 非空
      - start>=0 / dur>0 / start<该集时长
      - plan.expected_outputs       给出则校验成片数量
      - plan.expected_source_episodes 给出则校验并集覆盖这些集（不校验每个job各自的集数）
    """
    errs: list[str] = []
    ep_dur = {e["ep"]: float(e.get("duration") or 0) for e in catalog.get("episodes", [])}
    seen: set[str] = set()

    for oid, hl in jobs:
        if not oid:
            errs.append("存在缺少 id 的输出")
            continue
        if not SAFE_ID_RE.match(oid):
            errs.append(f"输出 id '{oid}' 含非法字符（只允许字母/数字/下划线/连字符，且以字母数字开头）")
        if oid in seen:
            errs.append(f"输出 id '{oid}' 重复")
        seen.add(oid)

        if not hl:
            errs.append(f"输出 '{oid}' 的 highlights 为空")
            continue

        for i, h in enumerate(hl, 1):
            if not isinstance(h, dict):
                errs.append(f"{oid} #{i} 不是对象：{h!r}")
                continue
            ep = h.get("ep")
            if ep not in ep_dur:
                errs.append(f"{oid} #{i} 未知集号 {ep!r}（catalog 有 {sorted(ep_dur)}）")
                continue
            try:
                start, dur = float(h["start"]), float(h["dur"])
            except (KeyError, TypeError, ValueError):
                errs.append(f"{oid} #{i} start/dur 缺失或非数值：{h}")
                continue
            if start < 0:
                errs.append(f"{oid} #{i} start={start} < 0")
            if dur <= 0:
                errs.append(f"{oid} #{i} dur={dur} <= 0")
            if ep_dur[ep] > 0 and start >= ep_dur[ep]:
                errs.append(f"{oid} #{i} start={start}s 超出 {ep} 时长 {ep_dur[ep]}s")

    plan = plan or {}
    exp_n = plan.get("expected_outputs")
    if exp_n is not None:
        try:
            if len(jobs) != int(exp_n):
                errs.append(f"plan.expected_outputs={exp_n}，实际 {len(jobs)} 个输出")
        except (TypeError, ValueError):
            errs.append(f"plan.expected_outputs 不是整数：{exp_n!r}")
    exp_eps = plan.get("expected_source_episodes")
    if exp_eps:
        covered = {h.get("ep") for _, hl in jobs for h in hl if isinstance(h, dict)}
        missing = [e for e in exp_eps if e not in covered]
        if missing:
            errs.append(f"plan.expected_source_episodes 未被覆盖：{missing}"
                        f"（三个成片并集只覆盖 {sorted(covered)}）")
    return errs


# ---------------------------------------------------------------- 调度

def run_shared(st: str, work: Path, out_dir: Path, args) -> int:
    if st == "probe":
        extra = ["--no-asr"] if args.no_asr else []
        return sh("stage1_probe.py",
                  ["--raw", args.raw, "--work", str(work),
                   "--shot-every", str(args.shot_every)] + extra)
    if st == "silence":
        return sh("stage2_silence.py",
                  ["--work", str(work), "--noise", str(args.noise),
                   "--min-dur", str(args.min_dur)])
    if st == "vad":
        return sh("stage2b_vad.py", ["--work", str(work)])
    raise ValueError(st)


def run_job(st: str, oid: str, hl: list[dict], work: Path, out_dir: Path, args) -> int:
    job_dir = work / "outputs" / oid
    job_dir.mkdir(parents=True, exist_ok=True)

    if st == "edl":
        cmd = ["--work", str(work),
               "--out-edl", str(job_dir / "edl.csv"),
               "--highlights-json", json.dumps(hl, ensure_ascii=False),
               "--output-id", oid]
        if args.no_apply_snap:
            cmd.append("--no-apply-snap")
        return sh("stage3_edl.py", cmd)

    if st == "cut":
        return sh("stage4_cut.py", ["--work", str(job_dir),
                                    "--mezz-dir", str(work / "mezz"),
                                    "--output-id", oid])

    if st == "canvas":
        extra = ["--level", args.dedup,
                 "--width", str(args.width), "--height", str(args.height)]
        if args.source_sub_mode:
            extra += ["--source-sub-mode", args.source_sub_mode]
        if args.sub_feather is not None:
            extra += ["--sub-feather", str(args.sub_feather)]
        if args.plan:
            extra += ["--plan", args.plan]
        return sh("stage5_canvas.py", ["--work", str(job_dir)] + extra)

    if st == "subs":
        final = str(out_dir / f"{oid}.mp4")
        extra = ["--out", final, "--asr", str(work / "asr.json")]
        if args.no_bgm:
            extra.append("--no-bgm")
        else:
            extra += ["--bgm-style", args.bgm]
        if args.no_subs:
            extra.append("--no-subs")
        if getattr(args, "min_bitrate", None):
            extra += ["--min-bitrate", str(args.min_bitrate)]
        if args.plan:
            extra += ["--plan", args.plan]
        return sh("stage6_subs.py", ["--work", str(job_dir)] + extra)

    if st == "endcard":
        # 片尾引导卡：在 S6 产物末尾追加 --endcard-dur 秒「点底部看全集」卡
        # （萤光计划规则：画面提示引导点击，时长须 < 全片 30%；默认 2.5s 远低于红线）
        final = out_dir / f"{oid}.mp4"
        tmp = out_dir / f"{oid}_ec.mp4"
        extra = ["--text", args.endcard_text, "--dur", str(args.endcard_dur)]
        if args.endcard_dur <= 0:
            print("    (endcard 跳过：--endcard-dur <= 0)")
            return 0
        return sh("endcard.py", ["--video", str(final), "--out", str(tmp)] + extra
                  ) or (_os_replace(tmp, final), 0)[1]

    if st == "verify":
        return sh("stage7_verify.py",
                  ["--work", str(job_dir), "--video", str(out_dir / f"{oid}.mp4"),
                   "--expect-w", str(args.width), "--expect-h", str(args.height)])
    raise ValueError(st)


def job_stats(work: Path, out_dir: Path, oid: str, ok: bool) -> dict:
    """汇总单个成片的信息（写进 <out-dir>/manifest.json）。"""
    job_dir = work / "outputs" / oid
    segs, eps = 0, []
    edl_csv = job_dir / "edl.csv"
    if edl_csv.exists():
        import csv as _csv
        with open(edl_csv, "r", encoding="utf-8-sig") as f:
            rows = list(_csv.DictReader(f))
        segs = len(rows)
        eps = sorted({r["ep"] for r in rows})
    duration = None
    finfo = job_dir / "final_info.json"
    if finfo.exists():
        try:
            duration = json.loads(finfo.read_text(encoding="utf-8")).get("duration")
        except Exception:
            duration = None
    if duration is None:
        rinfo = job_dir / "rough_info.json"
        if rinfo.exists():
            try:
                duration = json.loads(rinfo.read_text(encoding="utf-8")).get("actual")
            except Exception:
                duration = None
    return {
        "id": oid,
        "video": str(out_dir / f"{oid}.mp4"),
        "duration": duration,
        "segments": segs,
        "source_episodes": eps,
        "job_dir": str(job_dir),
        "status": "ok" if ok else "failed",
    }


def main():
    ap = argparse.ArgumentParser(description="短剧二创剪辑流水线（多成片）")
    ap.add_argument("stage", choices=STAGES + ["all"])
    ap.add_argument("--raw", default=r"E:\BaiduNetdiskDownload")
    ap.add_argument("--work", default=r"E:\duanju_work\work", help="工作根目录（共享产物所在层）")
    ap.add_argument("--out-dir", default=r"E:\duanju_work\out")
    ap.add_argument("--highlights", default=None,
                    help="高光清单：JSON 文件路径或内联 JSON，支持 {outputs:[{id,highlights}]}")
    ap.add_argument("--only", default=None, help="只跑指定 id 的成片")
    ap.add_argument("--plan", default=None, help="配置文件 plan.json")
    ap.add_argument("--shot-every", type=float, default=8.0)
    ap.add_argument("--noise", type=float, default=-28.0)
    ap.add_argument("--min-dur", type=float, default=0.30)
    ap.add_argument("--dedup", default="standard",
                    choices=["off", "light", "standard", "strong"])
    ap.add_argument("--width", type=int, default=1080,
                    help="输出宽（默认 1080；快手竖屏标准 720）")
    ap.add_argument("--height", type=int, default=1920,
                    help="输出高（默认 1920；快手竖屏标准 1280）")
    ap.add_argument("--source-sub-mode", dest="source_sub_mode", default=None,
                    choices=["off", "blur", "mask", "auto"],
                    help="传给 S5：原片硬字幕处理方式；auto=自适应逐窗检测模糊（推荐）")
    ap.add_argument("--sub-feather", type=int, default=None,
                    help="原字幕模糊带四边羽化像素（默认 24=maskedmerge 羽化；"
                         "设 0 走快速硬边模糊，软件渲染下羽化慢 30 倍")
    ap.add_argument("--bgm", default="tense",
                    choices=["tense", "epic", "suspense", "none"])
    ap.add_argument("--no-bgm", action="store_true")
    ap.add_argument("--endcard-text", dest="endcard_text", default="点底部看全集",
                    help="片尾引导卡文案（默认『点底部看全集』，不写『合集』二字）")
    ap.add_argument("--endcard-dur", dest="endcard_dur", type=float, default=2.5,
                    help="片尾引导卡时长秒数；<=0 跳过（须 < 全片时长 30%%）")
    ap.add_argument("--min-bitrate", dest="min_bitrate", type=float, default=None,
                    help="成片最低码率 Mbps（平台建议 12-18；传 12 即开启码率模式）")
    ap.add_argument("--no-subs", action="store_true")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--no-apply-snap", action="store_true",
                    help="传给 S3：只做帧量化，不做静音吸附")
    ap.add_argument("--force", action="store_true", help="清空中间产物重跑")
    args = ap.parse_args()

    work = Path(args.work)
    out_dir = Path(args.out_dir)
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.force and work.exists():
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        print(f"[init] 已清空 {work}")

    stages = STAGES if args.stage == "all" else [args.stage]
    needs_jobs = any(s in JOB_STAGES for s in stages)

    # ---------- 解析 job 清单 ----------
    jobs: list[tuple[str, list[dict]]] = []
    if needs_jobs:
        if args.highlights:
            try:
                jobs = load_output_jobs(parse_highlights_source(args.highlights))
            except Exception as exc:
                print(f"[ERROR] --highlights 解析失败：{exc}")
                sys.exit(1)
            src_desc = args.highlights
        else:
            jobs = load_jobs_from_manifest(work) or []
            src_desc = str(work / "outputs_manifest.json")
            if not jobs:
                print("[S3+] 跳过：未提供 --highlights，且没有 outputs_manifest.json")
                print("     先看 work/contact_sheet_ep*.jpg 挑高光，写成 JSON：")
                print('     {"outputs":[{"id":"serial01","highlights":'
                      '[{"ep":"ep01","start":12.0,"dur":6.0,"note":"打脸"}]}]}')
                sys.exit(1)

        if args.only:
            jobs = [j for j in jobs if j[0] == args.only]
            if not jobs:
                print(f"[ERROR] --only {args.only} 不在 job 清单里")
                sys.exit(1)

        # ---------- 预检 ----------
        catalog_path = work / "catalog.json"
        if not catalog_path.exists():
            print(f"[ERROR] 缺少 {catalog_path}，请先跑 probe 阶段")
            sys.exit(1)
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        plan = {}
        if args.plan and Path(args.plan).exists():
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

        errs = validate_jobs(jobs, catalog, plan)
        if errs:
            print(f"[ERROR] 高光清单预检未通过（来源 {src_desc}）：")
            for e in errs:
                print(f"    × {e}")
            sys.exit(1)

        print(f"[init] {len(jobs)} 个成片：{[o for o, _ in jobs]}")
        for oid, hl in jobs:
            eps = sorted({h.get("ep") for h in hl if isinstance(h, dict)})
            print(f"       · {oid}: {len(hl)} 段，覆盖 {eps}")

        # 持久化，使后续阶段不必再次提供 --highlights
        (work / "outputs_manifest.json").write_text(
            json.dumps({"work": str(work), "out_dir": str(out_dir),
                        "jobs": [{"id": o, "highlights": h} for o, h in jobs]},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 阶段调度 ----------
    failed: dict[str, str] = {}      # id -> 失败阶段
    for st in stages:
        if st in SHARED_STAGES:
            rc = run_shared(st, work, out_dir, args)
            if rc != 0:
                print(f"\n[FAIL] 阶段 {st} 退出码 {rc}，已中止后续阶段")
                sys.exit(rc)
            continue

        # 逐 job 跑：某个 job 失败不影响其它 job 跑完本阶段
        stage_failed: list[str] = []
        for oid, hl in jobs:
            if oid in failed:
                continue            # 之前阶段已失败，后续阶段不再重试
            rc = run_job(st, oid, hl, work, out_dir, args)
            if rc != 0:
                stage_failed.append(oid)
                failed[oid] = st

        if stage_failed:
            print(f"\n[FAIL] 阶段 {st}：{len(stage_failed)}/{len(jobs)} 个成片失败 → "
                  f"{', '.join(stage_failed)}")
            # verify 是最后一棒：即便失败也要把其余 job 的报告留下，最后统一非 0 退出
            if st != "verify" and len(stage_failed) == len(jobs):
                sys.exit(1)

    # ---------- 汇总 ----------
    summary = [job_stats(work, out_dir, oid, oid not in failed) for oid, _ in jobs]
    (out_dir / "manifest.json").write_text(
        json.dumps({"out_dir": str(out_dir), "work": str(work),
                    "count": len(summary), "outputs": summary},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[manifest] {out_dir / 'manifest.json'}")
    for s in summary:
        dur = f"{s['duration']:.2f}s" if isinstance(s['duration'], (int, float)) else "-"
        print(f"   · {s['id']}: {s['status']} / {s['segments']} 段 / "
              f"{dur} / 源集 {s['source_episodes']}")

    if failed:
        print(f"\n[FAIL] {len(failed)} 个成片未完成："
              + ", ".join(f"{o}@{s}" for o, s in failed.items()))
        sys.exit(1)

    print(f"\n[OK] 全部阶段完成 → {out_dir}")


if __name__ == "__main__":
    main()

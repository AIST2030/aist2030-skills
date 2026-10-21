#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pipeline.py —— 「文案直出视频」产线的编排入口（一条命令跑全流程）。

它把五段串起来，并固化了几条必须遵守的工序纪律：

  ① 断句配音   gen_narration.py --script <文案>          （词级时间轴）
  ② AI 分镜    由 agent 产出 shotplan.json（本脚本只做校验与补齐）
  ③ 素材       fetch_media.py --assign-only → 并发下载
  ④ 合成渲染   render.py --mode qc（先抽帧）→ --mode full
  ⑤ 质检交付   抽帧人工过目 → loudnorm -16 LUFS

用法：
  # 全流程（素材已就绪时）
  python pipeline.py --project <项目根> --script script.txt --stage all
  # 分步
  python pipeline.py --project <项目根> --script script.txt --stage narration
  python pipeline.py --project <项目根> --stage media --parallel 3
  python pipeline.py --project <项目根> --stage qc
  python pipeline.py --project <项目根> --stage render --loudnorm

设计取舍：
  - **不自动跑 full 渲染**。抽帧质检必须有人过目，脚本不做"静默出片"。
    传 --stage render --yes 才整片渲染（且默认带 --loudnorm）。
  - 素材下载用受管子进程分批并行（本机 8 核/16GB，并发 3 足够）。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
GEN = os.path.join(HERE, "gen_narration.py")
FETCH = os.path.join(HERE, "fetch_media.py")
RENDER = os.path.join(HERE, "render.py")


def run(cmd, cwd=None, tag=""):
    print(f"\n[{tag}] $ {' '.join(str(c) for c in cmd)}")
    p = subprocess.run(cmd, cwd=cwd)
    return p.returncode


def stage_narration(project, script, force=False):
    args = [PY, GEN, "--script", script]
    if force:
        args.append("--force")
    return run(args, cwd=project, tag="① 断句配音")


def check_shotplan(project):
    p = os.path.join(project, "shotplan.json")
    if not os.path.exists(p):
        print(f"[②] ✘ 未找到 {p}")
        print("    shotplan.json 必须由 agent 产出（AI 分镜是本产线的价值核心）。")
        print("    字段：shots[].{id,page,intent,media{type,query},overlay}")
        return False
    with open(p, "r", encoding="utf-8") as f:
        plan = json.load(f)
    shots = plan.get("shots", [])
    bad = [s.get("id") for s in shots
           if not s.get("media", {}).get("query")
           and s.get("media", {}).get("type") != "none"]
    print(f"[②] shotplan 校验：{len(shots)} 镜，缺 query 的 {len(bad)} 个 {bad if bad else ''}")
    return True


def stage_media(project, parallel=3):
    out = os.path.join(project, "remotion", "public", "media")
    os.makedirs(out, exist_ok=True)
    # 1) 预分配（多进程安全的前提）
    rc = run([PY, FETCH, "--plan", os.path.join(project, "shotplan.json"),
              "--out", out, "--assign-only"], cwd=project, tag="③a 素材预分配")
    if rc != 0:
        return rc
    # 2) 按页分批并行下载
    with open(os.path.join(project, "shotplan.json"), "r", encoding="utf-8") as f:
        plan = json.load(f)
    pages = []
    for s in plan.get("shots", []):
        if s.get("page") and s["page"] not in pages:
            pages.append(s["page"])
    groups = [pages[i::parallel] for i in range(parallel)]
    procs = []
    for gi, g in enumerate(groups):
        if not g:
            continue
        log = open(os.path.join(project, f"_fetch_{gi}.log"), "w", encoding="utf-8")
        procs.append((subprocess.Popen(
            [PY, FETCH, "--plan", os.path.join(project, "shotplan.json"),
             "--out", out, "--only", ",".join(g)],
            cwd=project, stdout=log, stderr=subprocess.STDOUT), log, g))
    for p, log, g in procs:
        p.wait()
        log.close()
        print(f"[③b] 分组 {g} 结束 rc={p.returncode}")
    # 3) 汇总
    mp = os.path.join(out, "media_manifest.json")
    if os.path.exists(mp):
        with open(mp, "r", encoding="utf-8") as f:
            items = json.load(f).get("items", [])
        ok = sum(1 for i in items if i.get("ok"))
        print(f"[③c] 素材就绪 {ok}/{len(items)}；未拿到的镜头将回退纯图形层")
    return 0


def stage_qc(project, frames=""):
    args = [PY, RENDER, "--project", project, "--mode", "qc"]
    if frames:
        args += ["--frames", frames]
    return run(args, tag="④a 抽帧质检")


def stage_render(project, loudnorm=True):
    args = [PY, RENDER, "--project", project, "--mode", "full"]
    if loudnorm:
        args.append("--loudnorm")
    return run(args, tag="④b 整片渲染")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--script", default=None, help="源文案 txt（stage=narration 需要）")
    ap.add_argument("--stage", default="all",
                    choices=["all", "narration", "plan", "media", "qc", "render"])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--force-tts", action="store_true")
    ap.add_argument("--frames", default="")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="确认整片渲染（跳过人工抽帧确认）")
    a = ap.parse_args()

    project = os.path.abspath(a.project)
    print("=" * 66)
    print("文案直出视频 · 产线编排")
    print(f"项目: {project} | 阶段: {a.stage}")
    print("=" * 66)

    if a.stage in ("all", "narration"):
        if not a.script:
            print("✘ --stage narration/all 需要 --script <文案.txt>")
            return 2
        if stage_narration(project, a.script, a.force_tts) != 0:
            return 1

    if a.stage in ("all", "plan"):
        if not check_shotplan(project):
            return 2

    if a.stage in ("all", "media"):
        if stage_media(project, a.parallel) != 0:
            return 1

    if a.stage in ("all", "qc"):
        stage_qc(project, a.frames)

    if a.stage == "render":
        if not a.yes:
            print("\n⚠ 整片渲染耗时长（本机约 20+ 分钟）。")
            print("  请先确认抽帧质检通过，再加 --yes 重新执行本命令。")
            return 0
        return stage_render(project, loudnorm=not a.no_loudnorm)

    if a.stage == "all":
        print("\n" + "=" * 66)
        print("① ② ③ 已完成。下一步：")
        print("  1) 人工过目 output/qc/ 下的抽帧，确认画面与字幕无误")
        print("  2) 整片渲染：python pipeline.py --project <项目> --stage render --yes")
        print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())

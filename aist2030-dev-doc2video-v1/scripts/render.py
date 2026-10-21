#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
render.py —— 文案直出视频产线的「④⑤ 合成渲染 + 质检」段。

设计原则（血泪经验，别改）：
  ★ 先抽帧后整片。整片渲染 20+ 分钟，盲渲发现一个错字/黑屏就要重来，
    代价极高。先用 still 抽若干代表帧（每个 10–30 秒），全过再开整片。
  ★ Remotion 需要显式指定本机 Chrome（本机无系统 Chromium/Edge）。
  ★ 并发 ≤ 4（8 核 / 16GB，可用内存常低于 2GB，开高会 OOM）。
  ★ wmic.exe 被安全策略拉黑，命令退出码可能异常 —— 判成功一律以产物为准。

用法：
  # 抽帧质检：按时间轴自动挑代表帧
  python render.py --project <项目根> --mode qc
  # 指定帧抽
  python render.py --project <项目根> --mode qc --frames 100,900,2000
  # 整片渲染
  python render.py --project <项目根> --mode full
  # 整片 + 响度归一到 -16 LUFS
  python render.py --project <项目根> --mode full --loudnorm
"""
import argparse
import json
import os
import subprocess
import sys

CHROME = r"C:\Users\Administrator\AppData\Local\Google\Chrome\Application\chrome.exe"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"
CONCURRENCY = "4"
COMP = "WeiXinXiaoWei"


def detect_comp(project):
    """从 remotion/src/Root.tsx 自动识别 <Composition id="...">。
    写死 comp id 是产线复用的大坑——换项目就渲染失败。"""
    import re
    root = os.path.join(project, "remotion", "src", "Root.tsx")
    if not os.path.exists(root):
        return COMP
    with open(root, "r", encoding="utf-8") as f:
        m = re.search(r'<Composition\s+id="([^"]+)"', f.read())
    return m.group(1) if m else COMP


def ffmpeg_path():
    """优先 imageio_ffmpeg 自带；其次技能文档固化的 venv 路径；最后才裸命令名。
    （曾因用系统 python 跑本脚本 → 无 imageio_ffmpeg → 回退裸 ffmpeg → 本机无
    系统 ffmpeg → FileNotFoundError，整片 loudnorm 阶段失败。2026-10-17 实测。）"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    known = (r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default"
             r"\Lib\site-packages\imageio_ffmpeg\binaries"
             r"\ffmpeg-win-x86_64-v7.1.exe")
    if os.path.exists(known):
        return known
    return "ffmpeg"


def pick_qc_frames(project, n=8):
    """按时间轴自动挑代表帧：每页取其最长镜头的中间时刻。"""
    tl_path = os.path.join(project, "remotion", "src", "data", "timeline.json")
    with open(tl_path, "r", encoding="utf-8") as f:
        tl = json.load(f)
    picks = []
    for p in tl["pages"]:
        best = max(p["shots"], key=lambda s: s["duration"])
        mid = p["startFrame"] + best["startFrame"] + best["durationFrames"] // 2
        picks.append(int(mid))
    # 覆盖首尾
    picks = sorted(set([2] + picks + [tl["totalFrames"] - 3]))
    return picks[: max(n, len(picks))]


def run_remotion(project, args, log_tag):
    remotion_dir = os.path.join(project, "remotion")
    cli = os.path.join(remotion_dir, "node_modules", "@remotion", "cli",
                       "remotion-cli.js")
    cmd = [NODE, cli] + args
    print(f"[{log_tag}] $ {' '.join(args)}")
    p = subprocess.run(cmd, cwd=remotion_dir,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "ignore")
    if p.returncode != 0:
        print(out[-2500:])
    return p.returncode, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="项目根目录（含 remotion/）")
    ap.add_argument("--mode", choices=["qc", "full"], default="qc")
    ap.add_argument("--frames", default="", help="qc 模式：逗号分隔的帧号，缺省自动挑")
    ap.add_argument("--comp", default=None, help="Remotion 合成 id，缺省自动从 Root.tsx 识别")
    ap.add_argument("--out", default=None)
    ap.add_argument("--loudnorm", action="store_true", help="整片后做双遍 loudnorm -16 LUFS")
    ap.add_argument("--concurrency", default=CONCURRENCY)
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    comp = args.comp or detect_comp(project)
    print(f"[render] 项目 {project} | comp={comp}")
    out_dir = os.path.join(project, "output", "qc")
    os.makedirs(out_dir, exist_ok=True)

    browser = ["--browser-executable", CHROME] if os.path.exists(CHROME) else []

    if args.mode == "qc":
        frames = [int(x) for x in args.frames.split(",") if x.strip()] \
            or pick_qc_frames(project)
        print(f"[qc] 待抽 {len(frames)} 帧: {frames}")
        ok = 0
        for fr in frames:
            dst = os.path.join(out_dir, f"f{fr}.png")
            code, _ = run_remotion(
                project,
                ["still", comp, dst, "--frame", str(fr)] + browser,
                f"still {fr}",
            )
            good = os.path.exists(dst) and os.path.getsize(dst) > 10240
            print(f"   frame {fr}: {'OK' if good else 'FAIL'} "
                  f"({os.path.getsize(dst) if os.path.exists(dst) else 0} B)")
            if good:
                ok += 1
        print(f"[qc] 成功 {ok}/{len(frames)} → {out_dir}")
        print("   请人工过目抽帧；确认无误后再跑 --mode full")
        return 0 if ok == len(frames) else 1

    # ---- 整片 ----
    # ★ out 必须转成相对 project 的绝对路径：Remotion 子进程的 cwd 是 remotion/，
    #   传相对路径（如 output/成片.mp4）会被解析到 remotion/output/ 下，
    #   而脚本的存在性检查按 project 根找旧文件 → 误判成功 + loudnorm 改错文件
    #   （2026-10-17 实测踩坑）。
    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(project, args.out)
    else:
        out = os.path.join(project, "output", "成片.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    code, _ = run_remotion(
        project,
        ["render", comp, out,
         "--concurrency", args.concurrency,
         "--codec", "h264"] + browser,
        "render",
    )
    # ⚠ wmic 被拉黑会让退出码异常，以产物为准
    if not (os.path.exists(out) and os.path.getsize(out) > 1024 * 100):
        print(f"[FATAL] 未产出有效成片: {out}")
        return 1
    print(f"[render] 成片已出: {out} "
          f"({os.path.getsize(out)/1024/1024:.1f} MB)")

    if args.loudnorm:
        ff = ffmpeg_path()
        tmp = out.replace(".mp4", "_tmp.mp4")
        os.replace(out, tmp)
        # 双遍 loudnorm，目标 -16 LUFS
        probe = subprocess.run(
            [ff, "-i", tmp, "-af",
             "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        txt = probe.stdout.decode("utf-8", "ignore")
        def grab(k):
            import re
            m = re.search(r'"' + k + r'"\s*:\s*"(-?[\d.]+)"', txt)
            return m.group(1) if m else None
        mi, tp, lra, th = grab("input_i"), grab("input_tp"), grab("input_lra"), grab("input_thresh")
        if not mi:
            print("[warn] loudnorm 测量失败，保留原片")
            os.replace(tmp, out)
            return 0
        r = subprocess.run(
            [ff, "-y", "-i", tmp, "-af",
             f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={mi}:"
             f"measured_TP={tp}:measured_LRA={lra}:measured_thresh={th}:"
             f"linear=true:print_format=summary",
             "-ar", "48000", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(r.stdout.decode("utf-8", "ignore")[-1200:])
        if os.path.exists(out) and os.path.getsize(out) > 1024:
            os.remove(tmp)
            print(f"[loudnorm] -16 LUFS 完成 → {out}")
        else:
            os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

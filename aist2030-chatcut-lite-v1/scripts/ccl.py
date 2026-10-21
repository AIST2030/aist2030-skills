#!/usr/bin/env python
"""ChatCut-Lite 命令行入口：AIST2030 Skill 调用脚本。

用法示例：
  # 环境自检
  python ccl.py doctor

  # 语音清理：转写 + 去口头禅 + 压停顿，产出字幕
  python ccl.py clean input.mp4 --style tiktok -o out/

  # 生成旁白
  python ccl.py tts "欢迎来到我的频道" --voice 晓晓 -o out/

  # 生成 BGM
  python ccl.py music 30 --style lofi -o out/

  # 生成音效
  python ccl.py sfx whoosh -o out/

  # 加 MG 动画（返回可叠加的透明 PNG 序列）
  python ccl.py mg --style bar_chart --text "增长|视频:120,直播:340" -o out/

  # 渲染时间线（读 JSON 工程）
  python ccl.py render project.json -o out/final.mp4

  # 一键成片：素材 + 需求描述
  python ccl.py auto input.mp4 --clean --subtitle --music lofi -o out/final.mp4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 引擎本体位置（ChatCut-Lite 项目根）
ENGINE_CANDIDATES = [
    Path(r"E:\视频创作\AIST2030\ChatCut-Lite"),
    Path(__file__).resolve().parent.parent / "ChatCut-Lite",
    Path(__file__).resolve().parent.parent.parent / "ChatCut-Lite",
]


def find_engine() -> Path:
    for p in ENGINE_CANDIDATES:
        if (p / "engine" / "ffmpeg_engine.py").exists():
            return p
    raise SystemExit(
        "找不到 ChatCut-Lite 引擎本体。\n"
        "请确认路径，默认在 E:\\视频创作\\AIST2030\\ChatCut-Lite"
    )


ENGINE = find_engine()
sys.path.insert(0, str(ENGINE))

# 依赖（numpy/Pillow/edge-tts/faster-whisper）装在项目 venv 里。
# 若当前解释器缺少依赖，自动切到项目 venv 的 python 重跑一次。
def _has_deps() -> bool:
    try:
        import PIL  # noqa
        return True
    except ImportError:
        return False


def _reexec_with_venv() -> None:
    """用项目 venv 的解释器重新执行本脚本。"""
    import os
    import subprocess
    venv_py = ENGINE / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        raise SystemExit(
            f"缺少依赖（Pillow 等），且找不到项目 venv：{venv_py}\n"
            f"请先运行：{ENGINE / '启动.bat'}"
        )
    if os.environ.get("CCL_REEXEC") == "1":
        raise SystemExit("重入后仍缺依赖，请检查 venv 是否完整")
    env = dict(os.environ)
    env["CCL_REEXEC"] = "1"
    env.setdefault("TMP", str(ENGINE / "workspace" / "cache"))
    env.setdefault("TEMP", env["TMP"])
    r = subprocess.run([str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]],
                       env=env)
    sys.exit(r.returncode)


if not _has_deps():
    _reexec_with_venv()

from engine.config import (FFMPEG, has_full_ffmpeg, disable_proxy,  # noqa: E402
                           run_bin)
from engine import ffmpeg_engine as FE  # noqa: E402
from engine import asr as ASR  # noqa: E402
from engine import mg as MG  # noqa: E402
from engine import assets as AST  # noqa: E402
from engine.timeline import Project, Clip, new_project  # noqa: E402


def outdir(p: str | None) -> Path:
    d = Path(p) if p else ENGINE / "workspace" / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- 子命令

def cmd_doctor(args):
    print("=" * 50)
    print("ChatCut-Lite 环境自检")
    print("=" * 50)
    print(f"引擎路径: {ENGINE}")
    print(f"ffmpeg  : {FFMPEG}")
    print(f"完整版  : {'✓ 是（可剪辑）' if has_full_ffmpeg() else '✗ 否（缺 libx264）'}")
    if not has_full_ffmpeg():
        print("\n修复：在 vendor 目录执行 npm i ffmpeg-static ffprobe-static")
    try:
        import faster_whisper  # noqa
        print("faster-whisper : ✓ 已安装")
    except ImportError:
        print("faster-whisper : ✗ 未安装（语音清理不可用）")
    try:
        import edge_tts  # noqa
        print("edge-tts: ✓ 已安装")
    except ImportError:
        print("edge-tts    : ✗ 未安装（TTS 不可用）")
    try:
        from PIL import Image  # noqa
        print("Pillow        : ✓ 已安装")
    except ImportError:
        print("Pillow        : ✗ 未安装（MG 不可用）")
    print(f"\nMG 模板   : {', '.join(MG.STYLES.keys())}")
    print(f"音乐风格  : {', '.join(AST.MUSIC_STYLES.keys())}")
    print(f"音效      : {', '.join(AST.SFX_KINDS)}")
    print(f"中文音色  : {', '.join(n for _, n, _ in AST.list_voices('zh'))}")
    return 0


def cmd_clean(args):
    disable_proxy()
    src = Path(args.input)
    od = outdir(args.out)
    print(f"转写中（模型 {args.model}）…")
    t = ASR.transcribe(src, model_size=args.model,
                       language=None if args.lang == "auto" else args.lang)
    total = len(t.words)
    ASR.clean_fillers(t, aggressive=args.aggressive)
    keeps = ASR.build_keep_ranges(
        t, compress_pause=not args.no_pause,
        pause_threshold=args.pause_threshold)
    cues = ASR.cues_from_transcript(t, max_chars=args.chars)
    ass = ASR.write_ass(cues, od / f"{src.stem}.ass",
                        args.width, args.height, args.style)
    orig = t.words[-1].end - t.words[0].start if t.words else 0
    kept = sum(b - a for a, b in keeps)

    report = {
        "src": str(src),
        "language": t.language,
        "original_dur": round(orig, 2),
        "kept_dur": round(kept, 2),
        "saved_sec": round(orig - kept, 2),
        "total_words": total,
        "removed": [{"text": w.text, "reason": w.reason}
                    for w in t.words if w.removed],
        "keeps": keeps,
        "cues": cues,
        "ass": str(ass),
        "text": t.text,
    }
    (od / f"{src.stem}_clean.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n原始时长 : {orig:.2f}s")
    print(f"保留时长 : {kept:.2f}s  （省 {orig - kept:.2f}s）")
    print(f"删除口头禅: {len(report['removed'])} 处")
    for r in report["removed"][:12]:
        print(f"   - {r['text'].strip()}  ({r['reason']})")
    print(f"字幕     : {len(cues)} 条 → {ass}")
    print(f"报告     : {od / f'{src.stem}_clean.json'}")
    return 0


def cmd_tts(args):
    od = outdir(args.out)
    dst = od / (args.name or f"tts_{abs(hash(args.text)) % 99999}.mp3")
    AST.tts_narration(args.text, dst, args.voice, args.lang, args.rate)
    info = FE.probe(dst)
    print(f"旁白已生成: {dst}  ({info['duration']}s, 音色={args.voice})")
    return 0


def cmd_music(args):
    od = outdir(args.out)
    dst = od / f"bgm_{args.style}_{int(args.duration)}s.wav"
    AST.music_for_video(args.duration, dst, style=args.style, bpm=args.bpm)
    info = FE.probe(dst)
    print(f"BGM 已生成: {dst}  ({info['duration']}s, 风格={args.style})")
    return 0


def cmd_sfx(args):
    od = outdir(args.out)
    dst = od / f"sfx_{args.kind}.wav"
    AST.sfx(args.kind, dst, dur=args.duration)
    print(f"音效已生成: {dst}")
    return 0


def cmd_mg(args):
    od = outdir(args.out)
    c = Clip(src="", start=0, dur=args.duration, kind="mg",
             text=args.text, style=args.style, color=args.color,
             x=args.x, y=args.y)
    d = MG.render_clip(c, args.width, args.height, args.fps, od / "mg")
    n = len(list(Path(d).glob("*.png")))
    print(f"MG 已渲染: {n} 帧 → {d}")
    print(f"模板={args.style}  文字={args.text}  颜色={args.color}")
    return 0


def cmd_render(args):
    pj = Project.load(Path(args.project))
    od = outdir(args.out)
    dst = od / (args.output or f"{pj.name}.mp4")

    ass_path = None
    cues = pj.meta.get("subtitle_cues") or []
    if cues and not args.no_subtitle:
        ass_path = ASR.write_ass(cues, ENGINE / "workspace" / "cache" / "render.ass",
                                 pj.width, pj.height,
                                 pj.meta.get("subtitle_style", "default"))
    renderers = MG.render_project(pj) if not args.no_mg else {}
    trans = {int(k): v for k, v in (pj.meta.get("transitions") or {}).items()}

    print(f"渲染中 → {dst}")
    FE.render(pj, dst, renderers=renderers, ass_path=ass_path, transitions=trans)
    info = FE.probe(dst)
    print(f"完成: {dst.name}  {info['width']}x{info['height']}  "
          f"{info['duration']}s  {dst.stat().st_size / 1024 / 1024:.2f}MB")
    return 0


def cmd_auto(args):
    """一键成片：素材 → 清理 → 字幕 → 配乐 → 成片。

    支持纯视频输入，也支持纯音频输入（自动生成纯色画面底）。
    """
    disable_proxy()
    src = Path(args.input)
    od = outdir(args.out)
    dst = Path(args.output) if args.output else od / f"{src.stem}_final.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)

    sinfo = FE.probe(src)
    has_video = bool(sinfo.get("has_video"))
    if not has_video and not sinfo.get("has_audio"):
        raise SystemExit(f"素材既无视频也无音频：{src}")

    pj = new_project(src.stem, args.width, args.height, args.fps)

    # 纯音频输入 → 生成纯色画面底（先落地，后续视频轨统一引用）
    bg_src = None
    bg_dur = max(2.0, sinfo["duration"])
    if not has_video:
        bg_src = od / f"{src.stem}_bg.mp4"
        run_bin([FFMPEG, "-y", "-f", "lavfi",
                 "-i", f"color=c={args.bg_color}:s={args.width}x{args.height}"
                       f":r={args.fps}:d={bg_dur}",
                 "-c:v", "libx264", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", str(bg_src)])
        print(f"[0/4] 纯音频输入，已生成 {bg_dur:.1f}s 纯色画面底")

    vsrc = str(bg_src) if bg_src else str(src)

    # 1. 语音清理
    cues = []
    if args.clean and sinfo.get("has_audio"):
        print("[1/4] 语音清理…")
        t = ASR.transcribe(src, model_size=args.model, language=args.lang)
        ASR.clean_fillers(t, aggressive=args.aggressive)
        keeps = ASR.build_keep_ranges(t)
        vtrack = pj.tracks[1]
        cursor = 0.0
        for s, e in keeps:
            vtrack.clips.append(Clip(src=vsrc, start=cursor,
                                     dur=e - s, src_in=0, kind="video"))
            cursor += e - s
        # 画面底必须覆盖所有 src_in 取值范围，否则裁剪会读到片尾导致时长错乱
        need = max((c.src_in + c.dur for c in vtrack.clips), default=0)
        if bg_src and need > bg_dur:
            bg_dur = need + 1.0
            run_bin([FFMPEG, "-y", "-f", "lavfi",
                     "-i", f"color=c={args.bg_color}:s={args.width}x{args.height}"
                           f":r={args.fps}:d={bg_dur}",
                     "-c:v", "libx264", "-preset", "veryfast",
                     "-pix_fmt", "yuv420p", str(bg_src)])
            print(f"      画面底补足至 {bg_dur:.1f}s")
        atrack = pj.tracks[2]
        for s, e in keeps:
            atrack.clips.append(Clip(src=str(src), start=cursor - (e - s),
                                     dur=e - s, src_in=s, kind="audio"))
        cues = ASR.cues_from_transcript(t)
        print(f"      {len(t.words)} 词 → 保留 {len(keeps)} 段，"
              f"删 {sum(1 for w in t.words if w.removed)} 个口头禅")
    else:
        dur = sinfo["duration"]
        pj.tracks[1].clips.append(Clip(src=vsrc, start=0, dur=dur, kind="video"))
        if sinfo.get("has_audio"):
            pj.tracks[2].clips.append(Clip(src=str(src), start=0,
                                           dur=dur, kind="audio"))

    dur = pj.duration

    # 2. 字幕
    if args.subtitle and cues:
        print("[2/4] 生成字幕…")
        pj.meta["subtitle_style"] = args.style
        pj.meta["subtitle_cues"] = cues
        print(f"      {len(cues)} 条，样式={args.style}")

    # 3. 配乐
    if args.music:
        print(f"[3/4] 生成 {args.music} 风格 BGM…")
        bgm = od / f"bgm_{args.music}.wav"
        AST.music_for_video(dur, bgm, style=args.music)
        pj.tracks[3].clips.append(Clip(src=str(bgm), start=0, dur=dur,
                                       kind="audio", volume=0.35,
                                       duck=True, fade_out=min(1.5, dur / 3)))
        print(f"      {dur:.1f}s，已开启人声压低")

    # 4. 渲染
    print("[4/4] 渲染成片…")
    ass = None
    if cues and args.subtitle:
        ass = ASR.write_ass(cues, ENGINE / "workspace" / "cache" / "auto.ass",
                            args.width, args.height, args.style)
    FE.render(pj, dst, renderers={}, ass_path=ass)

    info = FE.probe(dst)
    print("\n" + "=" * 50)
    print(f"成片: {dst}")
    print(f"规格: {info['width']}x{info['height']}  {info['duration']}s  "
          f"{dst.stat().st_size / 1024 / 1024:.2f}MB")
    print("=" * 50)
    return 0


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(
        prog="ccl", description="ChatCut-Lite · AIST2030 本地 AI 视频剪辑")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境自检").set_defaults(fn=cmd_doctor)

    c = sub.add_parser("clean", help="语音清理 + 字幕")
    c.add_argument("input")
    c.add_argument("-o", "--out")
    c.add_argument("--model", default="base",
                   choices=["tiny", "base", "small", "medium"])
    c.add_argument("--lang", default="zh")
    c.add_argument("--style", default="default",
                   choices=["default", "bold_white", "tiktok",
                            "bottom_clean", "top"])
    c.add_argument("--chars", type=int, default=18, help="每条字幕最大字数")
    c.add_argument("--aggressive", action="store_true", help="额外删低置信度词")
    c.add_argument("--no-pause", action="store_true", help="不压缩停顿")
    c.add_argument("--pause-threshold", type=float, default=0.45)
    c.add_argument("--width", type=int, default=1920)
    c.add_argument("--height", type=int, default=1080)
    c.set_defaults(fn=cmd_clean)

    c = sub.add_parser("tts", help="生成旁白")
    c.add_argument("text")
    c.add_argument("-o", "--out")
    c.add_argument("--voice", default="云希")
    c.add_argument("--lang", default="zh")
    c.add_argument("--rate", default="+0%")
    c.add_argument("--name")
    c.set_defaults(fn=cmd_tts)

    c = sub.add_parser("music", help="生成 BGM")
    c.add_argument("duration", type=float)
    c.add_argument("-o", "--out")
    c.add_argument("--style", default="lofi",
                   choices=list(AST.MUSIC_STYLES.keys()))
    c.add_argument("--bpm", type=int)
    c.set_defaults(fn=cmd_music)

    c = sub.add_parser("sfx", help="生成音效")
    c.add_argument("kind", choices=AST.SFX_KINDS)
    c.add_argument("-o", "--out")
    c.add_argument("--duration", type=float, default=0.6)
    c.set_defaults(fn=cmd_sfx)

    c = sub.add_parser("mg", help="渲染 MG 动画")
    c.add_argument("-o", "--out")
    c.add_argument("--style", default="title", choices=list(MG.STYLES.keys()))
    c.add_argument("--text", default="AI 一句话生成 MG 动画")
    c.add_argument("--color", default="#ff8a00")
    c.add_argument("--duration", type=float, default=3.0)
    c.add_argument("--width", type=int, default=1920)
    c.add_argument("--height", type=int, default=1080)
    c.add_argument("--fps", type=int, default=30)
    c.add_argument("--x", type=int, default=0)
    c.add_argument("--y", type=int, default=0)
    c.set_defaults(fn=cmd_mg)

    c = sub.add_parser("render", help="按工程文件渲染")
    c.add_argument("project")
    c.add_argument("-o", "--out")
    c.add_argument("--output")
    c.add_argument("--no-subtitle", action="store_true")
    c.add_argument("--no-mg", action="store_true")
    c.set_defaults(fn=cmd_render)

    c = sub.add_parser("auto", help="一键成片")
    c.add_argument("input")
    c.add_argument("-o", "--out")
    c.add_argument("--output")
    c.add_argument("--clean", action="store_true", help="做语音清理")
    c.add_argument("--subtitle", action="store_true", help="生成字幕")
    c.add_argument("--subtitle-style", dest="style", default="default",
                   choices=["default", "bold_white", "tiktok",
                            "bottom_clean", "top"])
    c.add_argument("--music", help="BGM 风格名，留空则不加")
    c.add_argument("--model", default="base")
    c.add_argument("--lang", default="zh")
    c.add_argument("--aggressive", action="store_true")
    c.add_argument("--width", type=int, default=1920)
    c.add_argument("--height", type=int, default=1080)
    c.add_argument("--fps", type=int, default=30)
    c.add_argument("--bg-color", default="#111827",
                   help="纯音频输入时的画面底色")
    c.set_defaults(fn=cmd_auto)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
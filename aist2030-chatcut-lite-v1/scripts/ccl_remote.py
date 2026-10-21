#!/usr/bin/env python
"""ChatCut-Lite 远程调度客户端：让 WorkBuddy（或任何脚本）驱动本机剪辑服务。

用法：
    python ccl_remote.py ping                     # 探活
    python ccl_remote.py auto --input 视频.mp4 --clean --subtitle tiktok --music lofi
    python ccl_remote.py auto --tts "你好世界" --subtitle tiktok   # 纯 TTS 出片
    python ccl_remote.py status <job_id>          # 查询异步渲染进度

auto 常用参数：
    --input PATH   素材绝对路径（可多次，第一个为主素材；纯音频自动配纯色底）
    --tts TEXT     无素材时用 TTS 旁白出片
    --voice NAME   TTS 音色（默认 云希）
    --clean        语音清理（删口头禅+压停顿）
    --subtitle [样式]  烧字幕，样式 default/tiktok/karaoke/minimal/bold_box
    --music STYLE  BGM 风格 lofi/electronic/cinematic/...
    --mg STYLE:TEXT[:颜色]  加 MG 图层，可多次，如 --mg bar_chart:流量构成:#4ade80
    --width/--height/--fps  分辨率帧率（默认 1280x720@30）
    --out NAME     输出文件名
    --async        异步渲染（返回 job id 后立即退出，默认同步等到完成）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8770"
SUBTITLE_STYLES = {"default", "tiktok", "karaoke", "minimal", "bold_box"}


def _post(path: str, body: dict, timeout: int = 320) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get(path: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


def cmd_ping(_args) -> None:
    try:
        print(json.dumps(_get("/api/agent/ping"), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"服务未响应: {e}",
                          "hint": "先启动服务：E:/视频创作/AIST2030/ChatCut-Lite/启动.bat"},
                         ensure_ascii=False))
        sys.exit(1)


def cmd_status(args) -> None:
    print(json.dumps(_get(f"/api/job/{args.job}"), ensure_ascii=False))


def cmd_auto(args) -> None:
    body: dict = {"name": args.name or "", "width": args.width,
                  "height": args.height, "fps": args.fps}
    if args.input:
        body["input"] = args.input
    if args.tts:
        body["tts"] = {"text": args.tts, "voice": args.voice}
    if args.clean:
        body["clean"] = True
    if args.subtitle:
        style = args.subtitle if args.subtitle in SUBTITLE_STYLES else "tiktok"
        body["subtitle"] = True
        body["subtitle_style"] = style
    if args.music:
        body["music"] = args.music
    if args.mg:
        layers = []
        for spec in args.mg:
            parts = spec.split(":", 2)
            style = parts[0]
            text = parts[1] if len(parts) > 1 else "标题"
            layer = {"style": style, "text": text}
            if len(parts) > 2:
                layer["color"] = parts[2]
            layers.append(layer)
        body["mg"] = layers
    if args.out:
        body["out_name"] = args.out
    body["sync"] = not args.async_
    body["sync_timeout"] = args.timeout

    r = _post("/api/agent/auto", body, timeout=args.timeout + 30)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if r.get("job_status") == "done" and r.get("path"):
        print(f"\n✅ 成片：{r['path']}")
    elif r.get("job_status") in ("queued", "running"):
        print(f"\n⏳ 渲染中，用 status {r['job']} 查进度")


def main() -> None:
    ap = argparse.ArgumentParser(description="ChatCut-Lite 远程调度客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping").set_defaults(fn=cmd_ping)

    s = sub.add_parser("status")
    s.add_argument("job")
    s.set_defaults(fn=cmd_status)

    a = sub.add_parser("auto")
    a.add_argument("--input", action="append", help="素材绝对路径，可多次")
    a.add_argument("--tts", help="TTS 旁白文本（无素材时作为主音轨）")
    a.add_argument("--voice", default="云希")
    a.add_argument("--clean", action="store_true", help="语音清理")
    a.add_argument("--subtitle", nargs="?", const="tiktok", default=None,
                   help="烧字幕，可选样式（默认 tiktok）")
    a.add_argument("--music", help="BGM 风格")
    a.add_argument("--mg", action="append", help="MG 图层 style:text[:color]，可多次")
    a.add_argument("--name", help="项目名")
    a.add_argument("--out", help="输出文件名")
    a.add_argument("--width", type=int, default=1280)
    a.add_argument("--height", type=int, default=720)
    a.add_argument("--fps", type=int, default=30)
    a.add_argument("--async", dest="async_", action="store_true",
                   help="异步渲染，立即返回 job id")
    a.add_argument("--timeout", type=int, default=300)
    a.set_defaults(fn=cmd_auto)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

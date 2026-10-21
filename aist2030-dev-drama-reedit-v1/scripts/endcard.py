# -*- coding: utf-8 -*-
"""
片尾引导卡（萤光计划合规引导：规则允许画面提示引导点击，时长须 < 全片 30%、图标不可过大）。

在成片末尾追加约 2.5s 的深色引导卡：
  深蓝黑底 + 细金边框 + 金字「点底部看全集」+ 淡入淡出 + 静音音轨。
文案由 --text 传入（默认「点底部看全集」，注意：不要写"合集"二字——平台本身禁止建合集，
规则原文是"点击【底部合集】"，但我们按用户口径用"点底部看全集"）。

用法：
  python endcard.py --video final.mp4 --out final_ec.mp4 [--text 点底部看全集] [--dur 2.5]

实现：PIL 生成卡片帧 → ffmpeg filter_complex concat（视频+静音 AAC 一起拼）→ 统一重编码，
编码参数跟随源片（fps/分辨率/采样率），不依赖 concat demuxer 的参数对齐，稳。
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

GOLD = (232, 198, 110)
BG = (7, 11, 20)
FONT_BD = r"C:/Windows/Fonts/msyhbd.ttc"
BORDER = (198, 162, 96)
DEFAULT_TEXT = "点底部看全集"


def make_card(w: int, h: int, text: str) -> Image.Image:
    im = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(im)
    m = int(w * 0.05)
    d.rounded_rectangle((m, m, w - m, h - m), 16, outline=BORDER + (210,), width=2)

    f = ImageFont.truetype(FONT_BD, int(h * 0.058))
    # 字间距：逐字绘制
    sp = int(h * 0.014)
    widths = [d.textlength(ch, font=f) for ch in text]
    total = sum(widths) + sp * (len(text) - 1)
    x = (w - total) / 2
    y = h / 2 - h * 0.035

    # 柔投影
    sh = Image.new("L", (w, h), 0)
    ds = ImageDraw.Draw(sh)
    cx = x
    for ch, cw in zip(text, widths):
        ds.text((cx + 3, y + 5), ch, font=f, fill=150)
        cx += cw + sp
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), sh)
    im.alpha_composite(shadow)

    # 金色主字
    d = ImageDraw.Draw(im)
    cx = x
    for ch, cw in zip(text, widths):
        d.text((cx, y), ch, font=f, fill=GOLD)
        cx += cw + sp

    # 底部小三角 + 短线装饰
    ly = y + h * 0.075
    tri = [(w / 2 - 10, ly), (w / 2 - 10, ly + 22), (w / 2 + 10, ly + 11)]
    d.polygon(tri, fill=GOLD)
    d.line([(w / 2 - 150, ly + 11), (w / 2 - 34, ly + 11)], fill=BORDER + (170,), width=2)
    d.line([(w / 2 + 34, ly + 11), (w / 2 + 150, ly + 11)], fill=BORDER + (170,), width=2)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--dur", type=float, default=2.5)
    ap.add_argument("--card-png", default=None, help="卡片帧输出路径（默认与 out 同目录）")
    args = ap.parse_args()

    inp, out = Path(args.video), Path(args.out)
    if not inp.exists():
        print(f"[endcard] 找不到输入视频 {inp}")
        sys.exit(1)

    info = fe.probe(str(inp))
    w, h = info["width"], info["height"]
    fps = info.get("fps") or 30.0
    ar = float(info.get("sample_rate") or 44100)
    ch = int(info.get("channels") or 2)
    print(f"[endcard] 源片 {w}x{h} @{fps:g}fps audio {ar:g}Hz x{ch}，追加 {args.dur}s 引导卡")

    card_png = args.card_png or str(out.parent / "_endcard.png")
    make_card(w, h, args.text).convert("RGB").save(card_png, quality=95)

    # concat 重编码（卡片先淡入淡出，再与源片视频+音频一起拼；静音轨补齐）
    fc = (
        f"[1:v]fade=t=in:st=0:d=0.35,fade=t=out:st={args.dur - 0.35:.2f}:d=0.35[ce];"
        f"[0:v][0:a][ce][2:a]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        "-i", str(inp),
        "-loop", "1", "-framerate", f"{fps:g}", "-t", f"{args.dur:.3f}", "-i", card_png,
        "-f", "lavfi", "-t", f"{args.dur:.3f}",
        "-i", f"anullsrc=r={int(ar)}:cl={'stereo' if ch >= 2 else 'mono'}",
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out), "-y",
    ]
    rc, _, err = fe.run(cmd)
    if rc != 0 or not out.exists():
        print(f"[endcard] 渲染失败:\n{err[-1200:]}")
        sys.exit(1)

    oinfo = fe.probe(str(out))
    print(f"[endcard] 完成 → {out}  {oinfo['duration']:.2f}s（源 {info['duration']:.2f}s + {args.dur}s）")


if __name__ == "__main__":
    main()

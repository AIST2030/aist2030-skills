# -*- coding: utf-8 -*-
"""
平台规则级封面（抖音/快手 2026 规范版）。
规范要点：
  - 1080x1920（9:16）
  - 冲突特写居中（底图人物居中，轻微放大裁切）
  - 顶部 1/3 留白 + 顶部居中粗体白字黑边钩子（宽度 <= 2/3 画面）
  - 底部暗带 + 金色书法剧名（不遮脸）
  - 左上角集数印章
  - 右下角"本作品含AI生成内容"标注
  - 底图右下角 AI 水印模糊去除
用法：
  python rule_cover.py --base <底图> --out <封面.jpg> --ep "第1集" \
      --name "女配闯苗疆" --l1 "穿成必死炮灰" --l2 "一见钟情竟是夺命蛊？"
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
FONT_BD = r"C:/Windows/Fonts/msyhbd.ttc"
FONT_KAI = r"C:/Windows/Fonts/simkai.ttf"
GOLD_HI = (250, 223, 145)
GOLD_LO = (198, 148, 68)
GOLD_DIM = (214, 184, 124)
WHITE = (252, 250, 246)
SEAL_RED = (176, 30, 38)


def bd(size):
    return ImageFont.truetype(FONT_BD, size)


def kai(size):
    return ImageFont.truetype(FONT_KAI, size)


def fit_font(text, max_w, start, floor, mk):
    size = start
    while size > floor:
        f = mk(size)
        if f.getlength(text) <= max_w:
            return f
        size -= 2
    return mk(floor)


def draw_stroke_text(im, xy, text, f):
    """粗体白字黑边（PIL stroke）。"""
    d = ImageDraw.Draw(im)
    d.text(xy, text, font=f, fill=WHITE, stroke_width=9,
           stroke_fill=(8, 8, 10, 255))


def draw_grad_text(im, xy, text, f):
    """金属金渐变字 + 柔投影（掩码直接画在目标位置）。"""
    x, y = int(xy[0]), int(xy[1])
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    bb = mask.getbbox()
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).text((x + 4, y + 8), text, font=f, fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), sh)
    im.alpha_composite(shadow)
    grad = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for gy in range(bb[1], bb[3] + 1):
        t = (gy - bb[1]) / max(1, bb[3] - bb[1])
        c = tuple(int(GOLD_LO[i] + (GOLD_HI[i] - GOLD_LO[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, gy), (im.size[0], gy)], fill=c)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    im.alpha_composite(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ep", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--l1", required=True, help="钩子第一行")
    ap.add_argument("--l2", default="", help="钩子第二行")
    ap.add_argument("--zoom", type=float, default=1.10, help="冲突特写放大倍数")
    ap.add_argument("--ai-label", default="本作品含AI生成内容")
    a = ap.parse_args()

    im = Image.open(a.base).convert("RGB")
    tw, th = im.size

    # ---- 冲突特写裁切：9:16 + zoom，人物居中 ----
    ch = int(th / a.zoom)
    cw = int(ch * W / H)
    if cw > tw:
        cw = tw
        ch = int(cw * H / W)
    cx = (tw - cw) // 2
    cy = max(0, (th - ch) // 3)  # 偏上取景，保住天空留白
    im = im.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)
    # 轻微锐化补偿放大
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))

    # ---- 去右下角 AI 水印 ----
    wm = im.crop((W - 320, H - 180, W, H)).filter(ImageFilter.GaussianBlur(22))
    wm = Image.eval(wm, lambda p: int(p * 0.45))
    im.paste(wm, (W - 320, H - 180))
    im = im.convert("RGBA")

    # ---- 顶部 1/3 暗渐变（钩子文字可读）+ 底部 1/5 暗带 ----
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        v = 0
        if y < 700:
            v = int(150 * (1 - y / 700.0) ** 1.15)
        if y > H - 420:
            v = max(v, int(185 * ((y - (H - 420)) / 420.0) ** 1.1))
        grad.putpixel((0, y), v)
    im = Image.composite(Image.new("RGBA", (W, H), (6, 8, 14, 255)), im,
                         grad.resize((W, H)))

    # ---- 顶部居中钩子（<= 2/3 宽，白字黑边）----
    max_w = int(W * 2 / 3)
    lines = [a.l1] + ([a.l2] if a.l2 else [])
    y = 128
    for line in lines:
        f = fit_font(line, max_w, 92, 56, bd)
        lw = f.getlength(line)
        draw_stroke_text(im, ((W - lw) / 2, y), line, f)
        y += int(f.size * 1.42)

    # ---- 左上角集数印章 ----
    f_ep = bd(46)
    ew = f_ep.getlength(a.ep)
    pw, ph = int(ew) + 56, 84
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((44 + 3, 54 + 6, 44 + pw + 3, 54 + ph + 6),
                                         12, fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((44, 54, 44 + pw, 54 + ph), 12, fill=SEAL_RED + (238,))
    d.text((44 + 28, 54 + 14), a.ep, font=f_ep, fill=WHITE)

    # ---- 底部金色书法剧名 ----
    f_name = fit_font(a.name, W - 320, 128, 84, kai)
    nw = f_name.getlength(a.name)
    ny = H - 400
    draw_grad_text(im, ((W - nw) / 2, ny), a.name, f_name)
    by = ny + int(f_name.size * 1.18)
    d = ImageDraw.Draw(im)
    d.line([(W / 2 - nw / 2 - 36, by), (W / 2 + nw / 2 + 36, by)],
           fill=GOLD_DIM + (210,), width=3)

    # ---- 右下角 AI 标注 ----
    f_ai = bd(30)
    aiw = f_ai.getlength(a.ai_label)
    d.text((W - aiw - 46, H - 118), a.ai_label, font=f_ai,
           fill=(255, 255, 255, 185), stroke_width=2, stroke_fill=(0, 0, 0, 200))

    im.convert("RGB").save(a.out, quality=95)
    print("saved", a.out)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
AI 封面底图 + 文字叠加（免费替代版）。
用法：
  python ai_cover_overlay.py --base <底图.png> --out <封面.jpg> --ep "第壹集" \
      --name "女配闯苗疆" --line1 "..." --line2 "..." [--gold "关键词1,关键词2"] \
      [--name-y 520] [--hook-y 130]
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
FONT_BD = r"C:/Windows/Fonts/msyhbd.ttc"
FONT_KAI = r"C:/Windows/Fonts/simkai.ttf"
GOLD_HI = (250, 223, 145)
GOLD_LO = (200, 150, 70)
GOLD_DIM = (214, 184, 124)
WHITE = (250, 248, 244)
SEAL_RED = (166, 32, 40)


def bd(size): return ImageFont.truetype(FONT_BD, size)
def kai(size): return ImageFont.truetype(FONT_KAI, size)


def draw_text_with_shadow(im, xy, text, f, fill, blur=7, off=(3, 5), shadow_alpha=140):
    x, y = int(xy[0]), int(xy[1])
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    # 投影
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).text((x + off[0], y + off[1]), text, font=f, fill=shadow_alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), sh)
    im.alpha_composite(shadow)
    # 主字
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    lay.paste(fill + (255,), (0, 0), mask)
    im.alpha_composite(lay)


def draw_grad_text(im, xy, text, f):
    x, y = int(xy[0]), int(xy[1])
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    bb = mask.getbbox()
    # 投影
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).text((x + 4, y + 8), text, font=f, fill=160)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), sh)
    im.alpha_composite(shadow)
    # 金属金渐变
    grad = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for gy in range(bb[1], bb[3] + 1):
        t = (gy - bb[1]) / max(1, bb[3] - bb[1])
        c = tuple(int(GOLD_LO[i] + (GOLD_HI[i] - GOLD_LO[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, gy), (im.size[0], gy)], fill=c)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    im.alpha_composite(out)


def segment(line, gold_kw):
    out, rest = [], line
    while rest:
        hit = next((kw for kw in gold_kw if rest.startswith(kw)), None)
        if hit:
            out.append((hit, True)); rest = rest[len(hit):]
        else:
            idx = min((rest.find(kw, 1) for kw in gold_kw if rest.find(kw, 1) > 0), default=len(rest))
            out.append((rest[:idx], False)); rest = rest[idx:]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ep", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--line1", default="")
    ap.add_argument("--line2", default="")
    ap.add_argument("--gold", default="")
    ap.add_argument("--name-y", type=int, default=560, help="剧名纵坐标")
    ap.add_argument("--hook-y", type=int, default=130, help="钩子句起始纵坐标")
    ap.add_argument("--hook-x", type=int, default=-1, help="钩子句起始横坐标；-1 为居中")
    a = ap.parse_args()

    im = Image.open(a.base).convert("RGB")
    # 居中裁成 9:16
    tw, th = im.size
    target = 9 / 16
    if tw / th > target:
        nw = int(th * target); im = im.crop(((tw - nw)//2, 0, (tw - nw)//2 + nw, th))
    else:
        nh = int(tw / target); im = im.crop((0, (th - nh)//2, tw, (th - nh)//2 + nh))
    im = im.resize((W, H), Image.LANCZOS).convert("RGBA")

    # 去水印
    wm = im.crop((W - 150, H - 90, W, H)).filter(ImageFilter.GaussianBlur(16))
    wm = Image.eval(wm, lambda p: int(p * 0.5))
    im.paste(wm, (W - 150, H - 90))

    # 顶部/底部压暗渐变（文字可读；底部给剧名留足够对比度）
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        v = 0
        if y < 360:
            v = int(110 * (1 - y / 360) ** 1.2)
        if y > 920:
            v = max(v, int(170 * ((y - 920) / 360) ** 1.1))
        grad.putpixel((0, y), v)
    im = Image.composite(Image.new("RGBA", (W, H), (5, 7, 13, 255)), im, grad.resize((W, H)))

    # 细金线内框
    d = ImageDraw.Draw(im)
    d.rectangle((24, 24, W-24, H-24), outline=(198, 162, 96, 200), width=2)

    # 左上角集数印章
    f_ep = bd(38); et = a.ep
    bb = f_ep.getbbox(et); ew, eh = bb[2]-bb[0], bb[3]-bb[1]
    pw, ph = ew + 48, eh + 24
    sh = Image.new("RGBA", (W, H), (0,0,0,0))
    ImageDraw.Draw(sh).rounded_rectangle((30+2, 40+5, 30+pw+2, 40+ph+5), 10, fill=(0,0,0,140))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((30, 40, 30+pw, 40+ph), 10, fill=SEAL_RED+(235,))
    d.text((30+24, 40+10), et, font=f_ep, fill=WHITE)

    # 顶部钩子句（放在人物上方天空，不压脸）
    f_hook = bd(56); gold_kw = [k for k in a.gold.split(",") if k]
    y = a.hook_y
    for line in [a.line1, a.line2]:
        if not line: continue
        segs = segment(line, gold_kw)
        total = sum(f_hook.getlength(s) for s, _ in segs)
        x = (W - total) / 2 if a.hook_x < 0 else a.hook_x
        for s, is_gold in segs:
            if is_gold: draw_grad_text(im, (x, y), s, f_hook)
            else: draw_text_with_shadow(im, (x, y), s, f_hook, WHITE)
            x += f_hook.getlength(s)
        y += 78

    # 中下部大号书法剧名
    max_w = W - 100
    size = 150
    while size >= 80:
        f_name = kai(size)
        test = Image.new("L", (W, H), 0)
        ImageDraw.Draw(test).text((0, 0), a.name, font=f_name, fill=255)
        bb = test.getbbox()
        if bb and (bb[2]-bb[0]) <= max_w: break
        size -= 4
    f_name = kai(size)
    test = Image.new("L", (W, H), 0); ImageDraw.Draw(test).text((0,0), a.name, font=f_name, fill=255); bb = test.getbbox()
    nx = (W - (bb[2]-bb[0]))/2 - bb[0]
    ny = a.name_y
    draw_grad_text(im, (nx, ny), a.name, f_name)
    # 剧名下金线
    nbb = Image.new("L", im.size, 0)
    ImageDraw.Draw(nbb).text((nx, ny), a.name, font=f_name, fill=255)
    nbb = nbb.getbbox()
    by = nbb[3] + 18; nw = nbb[2]-nbb[0]
    d = ImageDraw.Draw(im)
    d.line([(W/2 - nw/2 - 30, by), (W/2 + nw/2 + 30, by)], fill=GOLD_DIM+(200,), width=2)

    im.convert("RGB").save(a.out, quality=93)
    print("saved", a.out)


if __name__ == "__main__":
    main()

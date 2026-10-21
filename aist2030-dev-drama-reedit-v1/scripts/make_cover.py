# -*- coding: utf-8 -*-
"""
短剧封面合成器（通用，快手上限 720x1280 竖屏）。

用法：
  python make_cover.py --base 海报.jpg --out out.jpg --ep 第1集 \
      --tag 女配闯苗疆 --line1 "一睁眼穿成炮灰" --line2 "反派竟是梦中人" \
      [--gold 炮灰,梦中人]

设计语言：全出血海报底 + 顶部剧名 tag（金色细字+两侧短线）+ 集数 +
大字标题（白+金属金关键词，柔和投影，无粗描边）+ 细金线内边框。
标题关键词由 --gold 指定（逗号分隔），命中的字用金色渐变。
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
FONT_BD = r"C:/Windows/Fonts/msyhbd.ttc"
FONT_KAI = r"C:/Windows/Fonts/simkai.ttf"   # 楷体（书法体，用于剧名大字）
GOLD_HI = (242, 214, 148)
GOLD_LO = (198, 152, 74)
GOLD_DIM = (208, 178, 122)
WHITE = (250, 248, 244)
SEAL_RED = (166, 32, 40)


def font(size):
    return ImageFont.truetype(FONT_BD, size)


def kai_font(size):
    return ImageFont.truetype(FONT_KAI, size)


def text_mask(size, text, f):
    layer = Image.new("L", size, 0)
    d = ImageDraw.Draw(layer)
    bb = d.textbbox((0, 0), text, font=f)
    d.text((0, 0), text, font=f, fill=255)
    return layer, bb


def draw_grad_text(base, xy, text, f, center_x=True, grad=True):
    """金属金渐变文字 + 柔和投影。center_x 时按 base 宽居中。"""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = probe.textlength(text, font=f)
    x = int((base.size[0] - tw) / 2) if center_x else int(xy[0])
    y = int(xy[1])

    # 掩码直接画在目标位置（避免 bbox 裁剪丢字形侧留白）
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    bb = mask.getbbox()

    # 投影：黑字模糊（L→RGBA 整屏会盖黑底图，必须 paste 进透明层）
    sh = Image.new("L", base.size, 0)
    ImageDraw.Draw(sh).text((x + 4, y + 7), text, font=f, fill=175)
    sh = sh.filter(ImageFilter.GaussianBlur(7))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), sh)
    base.alpha_composite(shadow)

    if grad:
        grad_im = Image.new("RGBA", base.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad_im)
        for gy in range(bb[1], bb[3] + 1):
            t = (gy - bb[1]) / max(1, bb[3] - bb[1])
            c = tuple(int(GOLD_LO[i] + (GOLD_HI[i] - GOLD_LO[i]) * t) for i in range(3)) + (255,)
            gd.line([(0, gy), (base.size[0], gy)], fill=c)
        out = Image.new("RGBA", base.size, (0, 0, 0, 0))
        out.paste(grad_im, (0, 0), mask)
        base.alpha_composite(out)
    else:
        solid = Image.new("RGBA", base.size, (0, 0, 0, 0))
        solid.paste(WHITE + (255,), (0, 0), mask)
        base.alpha_composite(solid)
    return y + (bb[3] - bb[1])


def draw_solid_text(base, xy, text, f, color, center_x=True, blur_shadow=True):
    mask, bb = text_mask(base.size, text, f)
    tw = bb[2] - bb[0]
    x = int((base.size[0] - tw) / 2) if center_x else int(xy[0])
    y = int(xy[1])
    if blur_shadow:
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 160), (x + 2, y + 4), mask)
        sh = sh.filter(ImageFilter.GaussianBlur(5))
        base.alpha_composite(sh)
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    lay.paste(color + (255,), (x, y - bb[1]), mask)
    base.alpha_composite(lay)
    return y + (bb[3] - bb[1])


def letterspace(text, n=1):
    return (" " * n).join(list(text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ep", required=True, help="如：第1集 / 第壹集")
    ap.add_argument("--tag", default="")
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", default="")
    ap.add_argument("--gold", default="", help="逗号分隔的金色关键词")
    a = ap.parse_args()

    im = Image.open(a.base).convert("RGB")
    # 居中裁成 9:16 再放样到 720x1280
    tw, th = im.size
    target = 9 / 16
    if tw / th > target:
        nw = int(th * target)
        im = im.crop(((tw - nw) // 2, 0, (tw - nw) // 2 + nw, th))
    else:
        nh = int(tw / target)
        im = im.crop((0, (th - nh) // 2, tw, (th - nh) // 2 + nh))
    im = im.resize((W, H), Image.LANCZOS)
    im = im.convert("RGBA")

    # 右下角水印压除：局部高斯模糊+压暗
    wm = im.crop((W - 150, H - 90, W, H)).filter(ImageFilter.GaussianBlur(14))
    wm = Image.eval(wm, lambda p: int(p * 0.55))
    im.paste(wm, (W - 150, H - 90))

    d = ImageDraw.Draw(im)
    # 顶部/底部压暗渐变（保证文字可读）
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        v = 0
        if y < 340:
            v = int(120 * (1 - y / 340) ** 1.2)
        if y > 1050:
            v = max(v, int(90 * (y - 1050) / 230))
        grad.putpixel((0, y), v)
    grad = grad.resize((W, H))
    im = Image.composite(Image.new("RGBA", (W, H), (5, 7, 13, 255)), im, grad)
    d = ImageDraw.Draw(im)

    # 细金线内边框
    m = 26
    d.rectangle((m, m, W - m, H - m), outline=(198, 162, 96, 200), width=2)

    # ---------- 顶部：集数（红底白字印章式胶囊）----------
    f_ep = font(42)
    et = a.ep
    bb = f_ep.getbbox(et)
    ew, eh = bb[2] - bb[0], bb[3] - bb[1]
    pw, ph = ew + 64, eh + 30
    px, py = (W - pw) / 2, 60
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((px + 2, py + 5, px + pw + 2, py + ph + 5),
                                         12, fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((px, py, px + pw, py + ph), 12, fill=SEAL_RED + (235,))
    d.text((px + 32, py + 13), et, font=f_ep, fill=WHITE)

    # ---------- 中上部：钩子句（中字，白+金关键词）----------
    f_hook = font(60)
    gold_kw = [k for k in a.gold.split(",") if k]

    def segs_of(line):
        out, rest = [], line
        while rest:
            hit = None
            for kw in gold_kw:
                if kw and rest.startswith(kw):
                    hit = kw
                    break
            if hit:
                out.append((hit, True))
                rest = rest[len(hit):]
            else:
                idx = len(rest)
                for kw in gold_kw:
                    p = rest.find(kw, 1)
                    if p > 0:
                        idx = min(idx, p)
                out.append((rest[:idx], False))
                rest = rest[idx:]
        return out

    y = 250
    for line in [a.line1, a.line2]:
        if not line:
            continue
        segs = segs_of(line)
        total = sum(f_hook.getlength(s) for s, _ in segs)
        x = (W - total) / 2
        for s, is_gold in segs:
            if is_gold:
                draw_grad_text(im, (x, y), s, f_hook, center_x=False)
            else:
                draw_solid_text(im, (x, y), s, f_hook, WHITE, center_x=False)
            x += f_hook.getlength(s)
        y += 86

    # ---------- 中下部：剧名（书法大字，金属金渐变 + 柔投影）----------
    if a.tag:
        max_w = W - 80  # 左右各留 40 安全边
        fsize = 150
        while fsize >= 80:
            f_name = kai_font(fsize)
            test = Image.new("L", (W, H), 0)
            ImageDraw.Draw(test).text((0, 0), a.tag, font=f_name, fill=255)
            bb = test.getbbox()
            if bb and (bb[2] - bb[0]) <= max_w:
                break
            fsize -= 4
        f_name = kai_font(fsize)
        # 用 getbbox 真实宽度居中
        test = Image.new("L", (W, H), 0)
        ImageDraw.Draw(test).text((0, 0), a.tag, font=f_name, fill=255)
        bb = test.getbbox()
        nx = (W - (bb[2] - bb[0])) / 2 - bb[0]
        ny = 830
        # 柔投影
        shm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(shm).text((nx + 4, ny + 8), a.tag, font=f_name, fill=180)
        shm = shm.filter(ImageFilter.GaussianBlur(12))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 255), (0, 0), shm)
        im.alpha_composite(shadow)
        # 金属金渐变（掩码直接画在目标位置）
        nmask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(nmask).text((nx, ny), a.tag, font=f_name, fill=255)
        nbb = nmask.getbbox()
        gi = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gi)
        for gy in range(nbb[1], nbb[3] + 1):
            t = (gy - nbb[1]) / max(1, nbb[3] - nbb[1])
            c = tuple(int(GOLD_LO[i] + (GOLD_HI[i] - GOLD_LO[i]) * t) for i in range(3)) + (255,)
            gd.line([(0, gy), (W, gy)], fill=c)
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.paste(gi, (0, 0), nmask)
        im.alpha_composite(out)
        # 剧名下方细金线
        by = nbb[3] + 26
        nw = nbb[2] - nbb[0]
        d = ImageDraw.Draw(im)
        d.line([(W / 2 - nw / 2 - 30, by), (W / 2 + nw / 2 + 30, by)],
               fill=GOLD_DIM + (200,), width=2)

    im.convert("RGB").save(a.out, quality=93)
    print("saved", a.out)


if __name__ == "__main__":
    main()

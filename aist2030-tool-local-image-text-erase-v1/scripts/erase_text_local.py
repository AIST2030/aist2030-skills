# -*- coding: utf-8 -*-
"""本地文字擦除：抹掉标题文字（含描边/阴影），保住底块渐变与原始高光条。

为什么这么设计（踩过的坑）：
  1) 逐行水平插值 → 水平条纹 + 文字鬼影。背景是水平渐变，行内参考点相距 700px，
     线性近似还原不了非线性渐变。
  2) 逐列垂直插值 → 竖向"窗帘"条纹。列间参考点落在文字描边上，列与列不连续。
  3) 金字塔扩散(push-pull) → 云斑补丁感。
  正解：大范围 mask + cv2.inpaint(TELEA) 打底，再叠一层低频平滑抹掉 inpaint 的分块痕迹，
  最后用羽化 alpha 合成，边界无硬缝。
  mask 里的细长横条（原设计高光条）必须按连通域宽高比挑出来保护，否则会被一起擦掉。

用法：
  python erase_text_local.py <源图> <输出图(不带扩展名)>
"""
import sys

import cv2
import numpy as np

BRIGHT = 105     # 白色文字亮度下限
SATMAX = 115     # 白色文字饱和度上限
GROW = 45        # 擦除区膨胀核（要罩住文字描边/阴影）
INPAINT_R = 20   # inpaint 邻域半径
LOW_SIGMA = 7.0  # 低频平滑强度，抹掉 inpaint 分块感
FEATHER = 4.0    # 合成羽化


def imread_u(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(path, img):
    ext = "." + path.rsplit(".", 1)[-1].lower()
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError("encode failed: " + path)
    buf.tofile(path)


def white_text_mask(img, min_area=30, slim_ar=8.0, slim_h=30):
    """返回 (白色文字 mask, 细长高光条 mask)。高光条是原设计元素，必须保护。"""
    f = img.astype(np.int16)
    mn = f.min(axis=2)
    mx = f.max(axis=2)
    raw = ((mn > BRIGHT) & ((mx - mn) < SATMAX)).astype(np.uint8)

    n, lab, stats, _ = cv2.connectedComponentsWithStats(raw, 8)
    text = np.zeros_like(raw)
    slim = np.zeros_like(raw)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        if w / max(h, 1) > slim_ar and h < slim_h:
            slim[lab == i] = 1
            continue
        text[lab == i] = 1
    return text, slim


def erase(img, grow=GROW, radius=INPAINT_R, low_sigma=LOW_SIGMA, feather=FEATHER,
          protect_slim=True):
    text, slim = white_text_mask(img)
    if text.sum() == 0:
        raise SystemExit("未检测到白色文字，检查阈值")

    hole = cv2.dilate(text, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow)))
    hole[hole > 0] = 1
    protect = np.zeros_like(hole)
    if protect_slim:
        protect = cv2.dilate(slim, np.ones((7, 7), np.uint8))
        hole[protect > 0] = 0

    base = cv2.inpaint(img, hole, radius, cv2.INPAINT_TELEA).astype(np.float32)
    low = cv2.GaussianBlur(base, (0, 0), low_sigma)
    alpha = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), feather)[:, :, None]
    out = img.astype(np.float32) * (1 - alpha) + low * alpha
    return np.clip(out, 0, 255).astype(np.uint8), text, slim, alpha, protect


def main(src, dst_base):
    img = imread_u(src)
    h, w = img.shape[:2]
    out, text, slim, alpha, protect = erase(img)

    print("原图 %dx%d" % (w, h))
    print("  文字 mask = %d px (%.1f%%)" % (text.sum(), 100 * text.sum() / (w * h)))
    print("  保护高光条 = %d px" % slim.sum())
    ys, xs = np.where(text)
    print("  文字区 bbox x %d-%d  y %d-%d" % (xs.min(), xs.max(), ys.min(), ys.max()))

    f = out.astype(np.int16)
    mn = f.min(axis=2)
    mx = f.max(axis=2)
    # 统计擦除带内的白色残留：排除被保护的高光条，且用更严的饱和度阈值，
    # 否则蓝块自身偏亮的云纹(如 #7b8fd7, sat≈92)会被误报成文字残留。
    zone = (alpha[:, :, 0] > 0.5) & (protect == 0)
    left = int((((mn > BRIGHT) & ((mx - mn) < 60)) & zone).sum())
    print("  擦除区内白色残留 = %d  (擦除带 %d px)" % (left, int(zone.sum())))

    imwrite_u(dst_base + ".png", out)
    imwrite_u(dst_base + ".jpg", out)
    print("saved:", dst_base + ".png / .jpg")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

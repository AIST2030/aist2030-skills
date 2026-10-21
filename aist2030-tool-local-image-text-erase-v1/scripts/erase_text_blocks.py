# -*- coding: utf-8 -*-
"""色块文字擦除（保底版 · 进阶）：按色块自适应补底。

适用：设计稿 = 纯色/缓渐变几何色块 + 大号白色标题字（视频封面、字卡、海报截帧）。
不适用：照片/实景底 —— 那种直接走 buddy-image-processing 的 erase。

================== 六个实测结论（决定了本脚本的每一处设计）==================
① inpaint 大范围擦除会留【云斑 + 竖条 + 发灰】：它只能从邻域扩散，
   而设计稿底色是"整块缓变"，邻域扩散还原不出块级渐变。
② 全局多项式拟合会留【文字形状的鬼影】：文字外围的淡色光晕不是纯白，
   抓不进 text mask（阈值 mn>105 且 sat<115），却会留在拟合样本里把曲面拉亮。
   而且低阶曲面跟不动复杂渐变（红块 3 阶拟合残差仍有 19/255），会留浮雕轮廓。
③ 关键：此类封面文字通常带【暗投影】，实测延伸到 40~60px 之外
   （例："为什么？"下方 45px 处 L=71，而文字左侧外/更远处都是 L=85）。
   锚点若落在投影里，填充值被拉暗 → 出现"文字形状的暗轮廓"。
④ 但不同色块可用干净锚点差别极大：蓝块退到 60px 外仍有 21% 干净像素；
   红块文字横贯全宽，连 8px 外都凑不够 → 必须按色块自适应。
⑤ 二值锚点 + 小核逐层扩散 ＞ 一次性大核加权平均。
   软权重/大 sigma 会让【远处像素】直接参与加权，洞内被上下远处颜色平均成
   偏亮值 → 又是"文字形状的浅雾"。逐层推进时每层只由紧邻上一层决定，
   等价于由边界值决定的调和内插，不会跨尺度串色。
⑥ 洞越小内插越准。锚点半径是"避开投影"与"别把洞撑太大"之间的权衡，
   实测 45px 是本图的较优点（投影衰减到 L 只差 3，洞又不至于过大）。

================== 三个编码坑 ==================
· cv2 里 w[:, :, None] 是【单通道】→ GaussianBlur 返回 2 维，
  与三通道的 num 相除会广播失败。必须 np.dstack 铺成三通道。
· cv2.distanceTransform 在 mask【内部】为 0（它算的是"非零像素到最近零像素"），
  所以替换权重 alpha 要用 1 - clip(dist/R)，写成 clip(dist/R) 会把文字原样留下。
· np.mgrid 出的是二维坐标，做多项式项矩阵前必须先 ravel，
  否则 np.stack 会堆到错误的轴上（报 matmul 维度不匹配）。

用法：
  python erase_text_blocks.py <源图> <输出名（不带扩展名）>
依赖 cv2 / numpy。
"""
import sys

import cv2
import numpy as np

BRIGHT = 105          # 白色文字亮度下限
SATMAX = 115          # 白色文字饱和度上限
SIGMA = 10.0          # 每轮扩散核（小核 = 只跟紧邻像素打交道）
ITERS = 260           # 迭代轮数（每轮向内推进约 0.5σ）
DEN_T = 0.45          # 归一化模糊后达到该值才算"已知"
CLASS_DIFF = 20       # 色块判据：某通道比另一通道高这么多
TARGET_RATIO = 0.15   # 干净锚点占比低于此值 → 该色块改用曲面拟合
ANCHOR_HI = 45        # 锚点半径上限（避开文字暗投影）
ANCHOR_LO = 8         # 锚点半径下限
FIT_DEG = 2           # 兜底曲面拟合阶数


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ext = "." + p.rsplit(".", 1)[-1].lower()
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError("encode failed " + p)
    buf.tofile(p)


def text_mask(img):
    """返回 (白色文字 mask, 细长高光条 mask)。"""
    f = img.astype(np.int16)
    mn = f.min(axis=2)
    mx = f.max(axis=2)
    raw = ((mn > BRIGHT) & ((mx - mn) < SATMAX)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(raw, 8)
    text = np.zeros_like(raw)
    slim = np.zeros_like(raw)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 30:
            continue
        if w / max(h, 1) > 8 and h < 30:
            slim[lab == i] = 1        # 原设计自带的高光条，必须保护
        else:
            text[lab == i] = 1
    return text, slim


def block_regions(img, exclude, diff=CLASS_DIFF, close=71, min_area=4000):
    """按色相分出各色块，闭运算补掉文字挖出的洞。"""
    f = img.astype(np.int16)
    b, g, r = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    mx = f.max(axis=2)
    cand = {
        "blue": (b > r + diff) & (b > g + diff) & (mx > 45),
        "red": (r > b + diff) & (mx > 45),
    }
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
    out = {}
    for name, m in cand.items():
        mm = m.astype(np.uint8)
        mm[exclude > 0] = 0
        mm = cv2.morphologyEx(mm, cv2.MORPH_CLOSE, k)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mm, 8)
        keep = np.zeros_like(mm)
        for i in range(1, n):
            if stats[i, 4] >= min_area:
                keep[lab == i] = 1
        out[name] = keep
    return out


def diffusion_fill(img, known, region, iters=ITERS, sigma=SIGMA, den_t=DEN_T):
    """region 内逐层扩散。锚点/增长都不得越出色块边界，否则蓝红块会互相串色。"""
    base = img.astype(np.float32).copy()
    w = (known * (region > 0)).astype(np.float32)
    rounds = 0
    for _ in range(iters):
        w3 = np.dstack([w, w, w])       # 必须三通道，否则广播失败（坑 1）
        num = cv2.GaussianBlur(base * w3, (0, 0), sigma)
        den = cv2.GaussianBlur(w3, (0, 0), sigma)
        est = num / np.maximum(den, 1e-6)
        grow = (den[:, :, 0] >= den_t) & (w < 0.5) & (region > 0)
        if not grow.any():
            break
        base[grow] = est[grow]
        w[grow] = 1.0
        rounds += 1
    return base, w, rounds


def normalize_coords(x, y, w, h):
    return x / w * 2.0 - 1.0, y / h * 2.0 - 1.0


def poly_terms(X, Y, deg):
    out = []
    for i in range(deg + 1):
        for j in range(deg + 1 - i):
            out.append((X ** i) * (Y ** j))
    return np.stack(out, axis=-1)


def eval_surface(coefs, shape, deg):
    h, w = shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    X, Y = normalize_coords(xx.ravel().astype(np.float64), yy.ravel().astype(np.float64), w, h)
    A = poly_terms(X, Y, deg)
    return np.stack([A @ coefs[c] for c in range(3)], axis=1).reshape(h, w, 3).astype(np.float32)


def surface_fill(img, reg, dist, deg=FIT_DEG, excl=8, iters=5, step=3, min_pts=200):
    """锚点不足时的兜底：低阶全局曲面 + IRLS(Cauchy) 自动剔除投影异常值。"""
    ys, xs = np.where((reg > 0) & (dist > excl))
    if len(xs) < min_pts:
        return None
    ys, xs = ys[::step], xs[::step]
    h, w = img.shape[:2]
    X, Y = normalize_coords(xs.astype(np.float64), ys.astype(np.float64), w, h)
    A = poly_terms(X, Y, deg)
    V = img[ys, xs, :].astype(np.float64)
    wt = np.ones(len(xs))
    coefs = None
    for it in range(iters):
        Aw = A * wt[:, None]
        coefs = np.array([np.linalg.lstsq(Aw, V[:, c] * wt, rcond=None)[0] for c in range(3)])
        if it == iters - 1:
            break
        pred = A @ coefs.T
        r = np.sqrt(((V - pred) ** 2).sum(1))
        med = np.median(r)
        mad = np.median(np.abs(r - med)) * 1.4826 + 1e-6
        wt = np.maximum(wt / (1.0 + (r / (3.0 * mad)) ** 2), 1e-3)
    return eval_surface(coefs, (h, w), deg)


def pick_anchor(dist, reg, usable, target=TARGET_RATIO, lo=ANCHOR_LO, hi=ANCHOR_HI):
    """usable 必须是"真正可用的干净锚点"掩码（已含严格色相 + 高光条排除），
    否则会高估算量、误判为锚点充足。"""
    area = max(1, int((reg > 0).sum()))
    for d in range(hi, lo - 1, -2):
        if int((usable & (dist > d) & (reg > 0)).sum()) >= target * area:
            return d, True
    return lo, False


def main(src, dst_base):
    img = imread_u(src)
    h, w = img.shape[:2]
    text, slim = text_mask(img)
    if text.sum() == 0:
        raise SystemExit("未检测到白色文字，检查阈值")

    protect = cv2.dilate(slim, np.ones((13, 13), np.uint8))
    regions = block_regions(img, exclude=(text > 0).astype(np.uint8))
    dist = cv2.distanceTransform((1 - text).astype(np.uint8), cv2.DIST_L2, 5)

    # 锚点用【严格色相】筛：白色字及其抗锯齿边缘（如 (208,219,223)、(101,124,192)）
    # 不满足"某通道显著高于另一通道"，天然被排除，比只靠距离阈值精确得多。
    f = img.astype(np.int16)
    bb, gg, rr = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    mx = f.max(axis=2)
    strict = (((bb > rr + CLASS_DIFF) & (bb > gg + CLASS_DIFF) & (mx > 45))
              | ((rr > bb + CLASS_DIFF) & (mx > 45))) & (text == 0)

    print("原图 %dx%d | 文字 %d px | 保护高光条 %d px" % (w, h, text.sum(), slim.sum()))

    recon = img.astype(np.float32).copy()
    alpha_full = np.zeros((h, w), np.float32)
    covered = np.zeros((h, w), np.uint8)

    for name, reg in regions.items():
        usable = strict & (protect == 0)
        d, enough = pick_anchor(dist, reg, usable)
        m = (reg > 0) & (dist <= d) & (protect == 0)
        if enough:
            kn = (usable & (dist > d) & (reg > 0)).astype(np.float32)
            b_i, w_i, rounds = diffusion_fill(img, kn, region=reg)
            cover = 100.0 * (w_i > 0.5).sum() / max(1, int((reg > 0).sum()))
            print("  [%s] 扩散填充 | 锚点半径 %dpx | 锚点 %d px | 迭代 %d 轮 | 色块覆盖 %.0f%%"
                  % (name, d, int(kn.sum()), rounds, cover))
        else:
            b_i = surface_fill(img, reg, dist)
            if b_i is None:
                print("  [%s] 锚点与拟合样本均不足，跳过（交给 inpaint 兜底）" % name)
                continue
            print("  [%s] 曲面拟合 | 干净锚点不足(<%.0f%%) | 用 dist>%d 样本 + IRLS"
                  % (name, TARGET_RATIO * 100, ANCHOR_LO))
        recon[m] = b_i[m]
        alpha_full[m] = 1.0
        covered[m] = 1

    alpha = cv2.GaussianBlur(alpha_full, (0, 0), 1.5)[:, :, None]
    rest = (alpha_full > 0.5) & (covered == 0)
    if rest.any():
        imp = cv2.inpaint(img, rest.astype(np.uint8), 15, cv2.INPAINT_TELEA).astype(np.float32)
        recon[rest] = imp[rest]
        print("  兜底 inpaint = %d px" % int(rest.sum()))

    out = np.clip(img.astype(np.float32) * (1 - alpha) + recon * alpha, 0, 255).astype(np.uint8)

    f2 = out.astype(np.int16)
    mn = f2.min(axis=2)
    mx2 = f2.max(axis=2)
    zone = alpha[:, :, 0] > 0.5
    print("  填充区内白色残留 = %d (区 %d px)"
          % (int((((mn > BRIGHT) & ((mx2 - mn) < 60)) & zone).sum()), int(zone.sum())))

    imwrite_u(dst_base + ".png", out)
    imwrite_u(dst_base + ".jpg", out)
    print("saved: " + dst_base + ".png / .jpg")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S5 · 9:16 画幅 + 调色去重 + 原片硬字幕处理

三个职责：
  1) 画幅：确保输出 1080×1920 竖屏，且**不留黑边**（横屏源按人物重心裁切，
           竖屏源只做尺寸归一，不拉伸变形）
  2) 去重：平台查重看「画面指纹 + 运动轨迹」，纯改滤镜无效。
           这里做三件有效的事：
             - 分段色温/亮度微调（改变色彩直方图）
             - 关键帧微位移（1.5% 缓慢缩放，打散逐帧像素位置）
             - 随机水平镜像（按镜片段决定，**不镜像含文字/logo 的镜头**）

     去重强度在 assets/plan.example.json 的 dedup.level 里配：off / light / standard / strong。

  3) 原片硬字幕处理（source_subtitle）：原片底部往往已烧录硬字幕，
     S6 若再烧一行新字幕会出现「上下两层字」。本阶段按矩形区域做处理：
       - blur（默认）：局部高斯模糊，只糊字幕带，画面其余部分零改动
       - mask：黑色半透明 drawbox 盖住（旧 --cover-subs 行为）
       - off：不处理
     处理结果写入 <work>/canvas_info.json，供 S6/S7 硬校验。
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

TARGET_W, TARGET_H = 1080, 1920

# 原片烧录字幕的默认处理矩形（基准为输出 1080×1920 坐标，实测校准）
# 常规集缩放 1.5 → y 1230~1327；ep03（源高 1254）缩放 1.531 → y 1256~1355。
BASE_SUB_RECT = (60, 1200, 960, 200)   # 1080×1920 基准
DEFAULT_SUB_MODE = "blur"


def default_sub_rect(w: int = TARGET_W, h: int = TARGET_H) -> str:
    """
    按目标分辨率线性缩放基准字幕矩形。

    1080→720 / 1920→1280 时，原片字幕带在输出里的位置同步缩放，
    故矩形随分辨率等比缩放即可保持覆盖（快手 720×1280 标准规格）。
    """
    sx, sy = w / 1080.0, h / 1920.0
    x, y, ww, hh = BASE_SUB_RECT
    return (f"{int(round(x * sx))}:{int(round(y * sy))}:"
            f"{int(round(ww * sx))}:{int(round(hh * sy))}")
DEFAULT_SUB_SIGMA = 18.0
DEFAULT_AUTO_SIGMA = 32.0   # auto 模式：框很紧（约46px高），需更大 sigma 才能把字彻底糊透
AUTO_BLUR_PASSES = 2        # auto 双程高斯：等效 sigma≈45，把白字能量摊薄到几乎不可见（根治"模糊后仍有亮影"）
AUTO_SAFE = 3               # 检测框外的**硬覆盖**安全边（px）：这段必须全糊，反锯齿光晕在这里被吃掉
AUTO_FEATHER = 3            # 最外圈羽化宽度（px）：用户要求"外扩 2px 左右羽化"，3px≈观感 2px
AUTO_TIME_EDGE = 0.22       # 时间窗两端外扩（≥采样步长 0.2，保证窗头尾不漏帧）
DEFAULT_SUB_FEATHER = 24
MASK_ALPHA = 0.82

# 去重强度档位：eq 参数 = 饱和度:对比度:亮度(加法偏移!):gamma
DEDUP_GRADES = {
    "off":     "eq=saturation=1.00:contrast=1.00:brightness=0.000:gamma=1.00",
    "light":   "eq=saturation=1.06:contrast=1.04:brightness=0.010:gamma=0.99",
    "standard": "eq=saturation=1.12:contrast=1.08:brightness=0.018:gamma=0.97",
    "strong":  "eq=saturation=1.20:contrast=1.14:brightness=0.026:gamma=0.94",
}


def seg_hash(ep: str, idx: int, salt: str) -> float:
    """由集号+序号派生确定性伪随机数（0-1），保证重跑结果一致。"""
    h = hashlib.sha256(f"{salt}|{ep}|{idx}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def fit_vertical(src_w: int, src_h: int) -> tuple[str, str]:
    """
    生成竖屏适配滤镜。

    横屏/方图源 → cover 裁切（不留黑边）：先按高缩放，再按宽裁。
      scale=-2:H, crop=W:H  —— crop 默认居中，调用方可加 x/y 微调重心。
    竖屏源 → 直接拉伸到目标（保持比例，仅在比例略有偏差时）。
    """
    if src_w >= src_h:
        # 横屏：按高度匹配，宽度裁掉
        return f"scale=-2:{TARGET_H},crop={TARGET_W}:{TARGET_H}"
    else:
        # 竖屏：等比缩放到覆盖，再居中裁切（兼容 720x1254 这类非标比例）
        return f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}"


def build_filter(src_w: int, src_h: int, idx: int, ep: str,
                 dedup_level: str = "standard", seed: str = "AIST2030",
                 kenburns: bool = True) -> tuple[str, list[str]]:
    """
    组装视频滤镜链（几何 + 调色去重）。返回 (vf 字符串, 提示信息列表)

    注意：本函数**不**追加 format=yuv420p，由调用方统一在链尾加一次，避免重复。
    """
    notes = []
    chain = [fit_vertical(src_w, src_h)]

    # 调色（同时承担去重职责）
    if dedup_level != "off":
        grade = DEDUP_GRADES.get(dedup_level, DEDUP_GRADES["standard"])
        chain.append(grade)
        notes.append(f"调色去重[{dedup_level}]")
    else:
        notes.append("调色关闭[off]")

    # 关键帧微位移：缓慢缩放 1.5%，打散运动轨迹指纹
    if kenburns and dedup_level != "off":
        r = seg_hash(ep, idx, seed)
        # 起点略缩 + 终点放大，20 秒走完（短于镜头长度则按镜头时长）
        chain.append(
            f"zoompan=z='min(zoom+0.00012,1.015)':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={TARGET_W}x{TARGET_H}:fps=30"
        )
        notes.append(f"关键帧微位移(种子{r:.3f})")

    # 随机镜像：仅对部分片段，破坏左右布局
    if dedup_level in ("standard", "strong"):
        if seg_hash(ep, idx, seed + "_flip") > 0.6:
            chain.append("hflip")
            notes.append("水平镜像")

    return ",".join(chain), notes


# ---------------------------------------------------------------- 字幕处理参数

def parse_rect(s: str) -> tuple[int, int, int, int]:
    """解析 "x:y:w:h"。失败抛 ValueError（调用方负责转 sys.exit(1)）。"""
    parts = [p.strip() for p in str(s).split(":")]
    if len(parts) != 4:
        raise ValueError(f"--sub-rect 需要 4 个整数 x:y:w:h，收到 {s!r}")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f"--sub-rect 需要 4 个整数 x:y:w:h，收到 {s!r}")
    return x, y, w, h


def validate_rect(x: int, y: int, w: int, h: int, sigma: float,
                  cw: int | None = None, ch: int | None = None) -> list[str]:
    """校验矩形与 sigma，返回错误列表（空列表 = 合法）。"""
    cw = TARGET_W if cw is None else cw      # 运行时解析，别用导入期默认绑定
    ch = TARGET_H if ch is None else ch
    errs = []
    if x < 0:
        errs.append(f"x={x} < 0（画布左边界）")
    if y < 0:
        errs.append(f"y={y} < 0（画布上边界）")
    if w <= 0:
        errs.append(f"w={w} 必须 > 0")
    if h <= 0:
        errs.append(f"h={h} 必须 > 0")
    if x + w > cw:
        errs.append(f"x+w={x + w} 超出画布宽 {cw}")
    if y + h > ch:
        errs.append(f"y+h={y + h} 超出画布高 {ch}")
    if sigma <= 0:
        errs.append(f"sigma={sigma} 必须 > 0")
    return errs


def build_blur_complex(base: str, x: int, y: int, w: int, h: int, sigma: float) -> str:
    """
    局部高斯模糊：base 链 → split 两路，一路裁出字幕矩形做 gblur，再 overlay 回原位。

    [0:v]<base>,split[bg][p];
    [p]crop=w:h:x:y,gblur=sigma=S[bl];
    [bg][bl]overlay=x:y[v]
    """
    return (
        f"[0:v]{base},split[bg][p];"
        f"[p]crop={w}:{h}:{x}:{y},gblur=sigma={sigma:g}[bl];"
        f"[bg][bl]overlay={x}:{y}[v]"
    )


def has_filter(name: str) -> bool:
    """本机 ffmpeg 是否编译了指定滤镜。"""
    try:
        _, out, err = fe.run(["-filters"])
    except Exception:
        return False
    return name in (out + err)


def build_adaptive_blur_complex(base: str, windows: list[dict],
                                sigma: float, cw: int, ch: int,
                                safe: int = AUTO_SAFE,
                                feather: int = AUTO_FEATHER,
                                passes: int = AUTO_BLUR_PASSES) -> tuple[str, list[tuple]]:
    """
    自适应字幕模糊 v4：外扩安全边 + 双程高斯 + 外圈羽化。

    对每窗：
      1) 区域 = 检测box 外扩 (safe+feather) px（越界裁剪到画布内）；
      2) crop 出区域，gblur ×passes（双程等效 sigma≈√2·sigma，把白字能量摊薄，
         根治"框内残留亮影/字形淡痕"）；
      3) 用静态羽化 alpha（alphamerge）把最外圈 feather px 做余弦渐变——
         模糊带边缘不再是硬切线；
      4) overlay + enable 时间门控，无字幕时段完全不经过模糊。

    羽化的关键约束：**羽化带只落在"安全边"以外的外扩区**，
    字幕 box + safe px 这一圈内 alpha=255（全糊），保证零漏出；
    从那里到区域外缘的 feather px 内 alpha 从 255 余弦过渡到 0（软边）。

    输入：0=视频，1..n=各窗的静态 alpha PNG（-loop 1）。
    返回 (filter_complex 字符串, [(x,y,w,h), ...] 每窗区域)。
    """
    if not windows:
        return f"[0:v]{base}[v]", []

    n = len(windows)
    regs: list[tuple[int, int, int, int]] = []
    for wd in windows:
        x = max(0, int(wd["x0"]) - safe - feather)
        y = max(0, int(wd["y0"]) - safe - feather)
        x1 = min(cw - 1, int(wd["x1"]) + safe + feather)
        y1 = min(ch - 1, int(wd["y1"]) + safe + feather)
        w = x1 - x + 1
        h = y1 - y + 1
        # ⚠ 宽高必须取偶：gblur 在 yuv420p 奇数尺寸上会掉 1px（实测 95x58 → 94x58），
        #   导致与 alphamerge 的静态 alpha 图尺寸不一致而初始化失败
        w -= w % 2
        h -= h % 2
        regs.append((x, y, w, h))

    labels = "".join(f"[p{i}]" for i in range(n))
    parts = [f"[0:v]{base},split={n + 1}[bg]{labels};"]

    blur = f"gblur=sigma={sigma:g}"
    if passes >= 2:
        blur += f",gblur=sigma={sigma:g}"

    for i, (x, y, w, h) in enumerate(regs):
        parts.append(f"[p{i}]crop={w}:{h}:{x}:{y},{blur}[bl{i}];")
        if feather > 0:
            parts.append(f"[{i + 1}:v]format=gray[am{i}];")
            parts.append(f"[bl{i}][am{i}]alphamerge[ba{i}];")

    prev = "bg"
    for i, wd in enumerate(windows):
        x, y, _w, _h = regs[i]
        tag = f"ba{i}" if feather > 0 else f"bl{i}"
        nxt = "v" if i == n - 1 else f"v{i}"
        parts.append(
            f"[{prev}][{tag}]overlay={x}:{y}:"
            f"enable='between(t,{wd['t0']:.3f},{wd['t1']:.3f})'[{nxt}];"
        )
        prev = nxt

    joined = "".join(parts)
    if joined.endswith(";"):
        joined = joined[:-1]
    return joined, regs


def build_alpha_png(path: str, w: int, h: int, feather: int) -> bool:
    """
    生成静态羽化 alpha 图（灰度 PNG）：内部 255，最外圈 feather px 余弦渐变到 0。
    numpy 向量化，毫秒级。失败返回 False（调用方回退硬边）。
    """
    try:
        import numpy as np
        from PIL import Image
        a = np.full((h, w), 255, np.uint8)
        if feather > 0 and w > 2 * feather and h > 2 * feather:
            ramp = (0.5 - 0.5 * np.cos(np.pi * np.arange(feather) / feather)) * 255.0
            for i in range(feather):
                v = np.uint8(round(float(ramp[i])))
                a[i, :] = np.minimum(a[i, :], v)
                a[h - 1 - i, :] = np.minimum(a[h - 1 - i, :], v)
                a[:, i] = np.minimum(a[:, i], v)
                a[:, w - 1 - i] = np.minimum(a[:, w - 1 - i], v)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(a, "L").save(path)
        return True
    except Exception as exc:
        print(f"[S5] [!] alpha 图生成失败: {exc}")
        return False


def mask_png_name(x: int, y: int, w: int, h: int, feather: int) -> str:
    """遮罩图文件名指纹：由 rect + feather 唯一决定，便于复用。"""
    return f"_sub_mask_x{x}_y{y}_w{w}_h{h}_f{feather}.png"


def build_mask_png(work: Path, x: int, y: int, w: int, h: int, feather: int,
                   cw: int | None = None, ch: int | None = None) -> str | None:
    """
    生成羽化遮罩灰度图（静态 PNG，只做一次，按 rect+feather 复用）。

    白(255)=取模糊层，黑(0)=保留原图；矩形内部 255，四边各 feather 像素做
    余弦过渡（最外圈 0 → 向内渐变到 255），矩形外 0。
    返回 PNG 路径；PIL 不可用或生成失败返回 None（调用方回退硬边）。
    """
    cw = TARGET_W if cw is None else cw      # 运行时解析（见 validate_rect 注释）
    ch = TARGET_H if ch is None else ch
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    dst = Path(work) / mask_png_name(x, y, w, h, feather)
    if dst.exists():
        return str(dst)

    try:
        img = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(img).rectangle([x, y, x + w - 1, y + h - 1], fill=255)
        if feather > 0:
            # 余弦 smoothstep：i=0 → 0（贴原图），i=feather-1 → ≈255（贴模糊层）
            ramp = [int(round(255 * (0.5 - 0.5 * math.cos(math.pi * i / feather))))
                    for i in range(feather)]
            px = img.load()
            x1, y1 = min(x + w, cw), min(y + h, ch)
            # 上下边（整条边先铺），再左右边取 min —— 角落自然取两侧较小值
            for i, v in enumerate(ramp):
                for xx in range(x, x1):
                    px[xx, y + i] = v
                    px[xx, y1 - 1 - i] = v
            for j, v in enumerate(ramp):
                for yy in range(y, y1):
                    if v < px[x + j, yy]:
                        px[x + j, yy] = v
                    if v < px[x1 - 1 - j, yy]:
                        px[x1 - 1 - j, yy] = v
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(dst))
    except Exception as exc:
        print(f"[S5] [!] 遮罩图生成失败: {exc}")
        return None
    return str(dst)


def build_feather_complex(base: str, x: int, y: int, w: int, h: int,
                          sigma: float, cw: int | None = None,
                          ch: int | None = None) -> str:
    """
    羽化版局部模糊：模糊层 pad 回整幅，再用静态遮罩 maskedmerge 融合。

    [0:v]<base>,split[bg][p];
    [p]crop=...,gblur=sigma=S,pad=CW:CH:x:y[bl];     # 模糊层（带外区域被 mask 抹掉，填黑无影响）
    [1:v]scale=CW:CH,format=gray[mk];                # 静态羽化遮罩
    [bl][bg][mk]maskedmerge[v]                       # top=模糊层 bottom=原图 mask=遮罩
    """
    cw = TARGET_W if cw is None else cw      # 运行时解析（见 validate_rect 注释）
    ch = TARGET_H if ch is None else ch
    return (
        f"[0:v]{base},split[bg][p];"
        f"[p]crop={w}:{h}:{x}:{y},gblur=sigma={sigma:g},"
        f"pad={cw}:{ch}:{x}:{y},format=yuv420p[bl];"
        f"[1:v]scale={cw}:{ch},format=gray[mk];"
        f"[bl][bg][mk]maskedmerge[v]"
    )


def main():
    global TARGET_W, TARGET_H   # 必须在任何引用之前声明，供 --width/--height 覆盖
    ap = argparse.ArgumentParser(description="S5 9:16 画幅 + 调色去重 + 原片硬字幕处理")
    ap.add_argument("--work", required=True, help="工作目录（读 edl.csv）")
    ap.add_argument("--in", dest="inp", default=None, help="输入视频（默认 work/rough.mp4）")
    ap.add_argument("--out", default=None, help="输出（默认 work/canvas.mp4）")
    ap.add_argument("--level", default="standard",
                    choices=list(DEDUP_GRADES.keys()), help="去重强度")
    ap.add_argument("--seed", default="AIST2030", help="随机种子（保证可复现）")
    ap.add_argument("--no-kenburns", action="store_true")
    ap.add_argument("--source-sub-mode", dest="source_sub_mode", default=None,
                    choices=["off", "blur", "mask", "auto"],
                    help=f"原片硬字幕处理方式（默认 {DEFAULT_SUB_MODE}）；"
                         "auto=自适应（逐帧检测字幕带，仅在有字幕时按实际box模糊）")
    ap.add_argument("--band-pad", dest="band_pad", type=int, default=2,
                    help="auto 模式：字幕框左右扩展像素（默认 2，盖反锯齿光晕）")
    ap.add_argument("--band-vpad", dest="band_vpad", type=int, default=5,
                    help="auto 模式：字幕框上下扩展像素（默认 5，覆盖描边+光晕）")
    ap.add_argument("--band-step", dest="band_step", type=float, default=0.2,
                    help="auto 模式：字幕检测采样步长（秒，默认 0.2）")
    ap.add_argument("--sub-rect", dest="sub_rect", default=None,
                    help="字幕矩形 x:y:w:h，输出坐标（不填则按 --width/--height 等比缩放基准矩形）")
    ap.add_argument("--sub-sigma", dest="sub_sigma", type=float, default=None,
                    help=f"高斯模糊强度（默认 {DEFAULT_SUB_SIGMA:g}，>0）")
    ap.add_argument("--sub-feather", dest="sub_feather", type=int, default=None,
                    help="模糊带四边羽化过渡宽度（像素，默认 %d）；"
                         "0 = 不羽化（硬边）。仅 blur 模式生效" % DEFAULT_SUB_FEATHER)
    ap.add_argument("--cover-subs", action="store_true",
                    help="[兼容别名] 等价 --source-sub-mode mask（遮盖原片已烧录的字幕带）")
    ap.add_argument("--cover-h", type=int, default=None,
                    help="[兼容] mask 模式下的遮盖**高度**（不是「距底部高度」）："
                         "遮盖框为 (--sub-rect 的 x,y,w) × 本高度，缺省用 --sub-rect 的 h")
    ap.add_argument("--plan", default=None, help="配置文件 plan.json")
    ap.add_argument("--width", type=int, default=TARGET_W,
                    help="输出宽（默认 1080；快手竖屏标准 720）")
    ap.add_argument("--height", type=int, default=TARGET_H,
                    help="输出高（默认 1920；快手竖屏标准 1280）")
    args = ap.parse_args()

    # 分辨率参数化：覆盖模块全局，使 fit_vertical / validate_rect / 遮罩 / 尺寸校验
    # 全部按目标分辨率工作（不改变 skill 默认的 1080×1920 行为）
    TARGET_W, TARGET_H = args.width, args.height

    work = Path(args.work)
    inp = args.inp or str(work / "rough.mp4")
    out = args.out or str(work / "canvas.mp4")
    level = args.level
    seed = args.seed

    plan = {}
    if args.plan and Path(args.plan).exists():
        plan = fe.json_load(args.plan)
        level = plan.get("dedup", {}).get("level", level)
        seed = plan.get("dedup", {}).get("seed", seed)

    # ---- 解析字幕处理配置：CLI 显式参数 > plan.source_subtitle > 内置默认值 ----
    psub = plan.get("source_subtitle") or {}

    sub_mode = args.source_sub_mode
    if sub_mode is None:
        if args.cover_subs:
            sub_mode = "mask"
        else:
            sub_mode = str(psub.get("mode", DEFAULT_SUB_MODE)).lower()
    if sub_mode not in ("off", "blur", "mask", "auto"):
        print(f"[S5] 非法 source-sub-mode: {sub_mode}（应为 off/blur/mask/auto）")
        sys.exit(1)

    rect_s = args.sub_rect
    if rect_s is None:
        pr = psub.get("rect") if isinstance(psub.get("rect"), dict) else psub
        if isinstance(pr, dict) and all(k in pr for k in ("x", "y", "w", "h")):
            rect_s = f"{int(pr['x'])}:{int(pr['y'])}:{int(pr['w'])}:{int(pr['h'])}"
        else:
            rect_s = default_sub_rect(TARGET_W, TARGET_H)
    try:
        x, y, w, h = parse_rect(rect_s)
    except ValueError as exc:
        print(f"[S5] {exc}")
        sys.exit(1)

    sigma = args.sub_sigma
    if sigma is None:
        try:
            sigma = float(psub.get("sigma", DEFAULT_SUB_SIGMA))
        except (TypeError, ValueError):
            sigma = DEFAULT_SUB_SIGMA

    feather = args.sub_feather
    if feather is None:
        try:
            feather = int(psub.get("feather", DEFAULT_SUB_FEATHER))
        except (TypeError, ValueError):
            feather = DEFAULT_SUB_FEATHER
    if feather < 0:
        print(f"[S5] --sub-feather={feather} 不能为负")
        sys.exit(1)
    # 羽化带不能吃掉整个矩形：向内收敛到半宽/半高（会打印提示，不静默）
    max_f = min(w // 2, h // 2)
    if feather > max_f:
        print(f"[S5] [!] 羽化宽度 {feather} 超过矩形半宽/半高，已收敛为 {max_f}")
        feather = max_f

    # mask 模式的兼容高度覆盖（--cover-h）
    if sub_mode == "mask" and args.cover_h is not None:
        h = args.cover_h

    # ---- 边界校验 ----
    errs = validate_rect(x, y, w, h, sigma)
    if errs:
        print(f"[S5] 字幕矩形参数非法（画布 {TARGET_W}x{TARGET_H}）：")
        for e in errs:
            print(f"     - {e}")
        sys.exit(1)

    if not Path(inp).exists():
        print(f"[S5] 找不到输入 {inp}，请先跑 S4")
        sys.exit(1)

    info = fe.probe(inp)
    print(f"[S5] 输入 {Path(inp).name}: {info['width']}x{info['height']} "
          f"{info['duration']:.1f}s @{info['fps']}")
    print(f"     去重强度: {level} / 种子: {seed}")
    if sub_mode == "auto":
        print(f"     原片字幕: auto（自适应，逐帧检测字幕带）")
    else:
        print(f"     原片字幕: {sub_mode} / rect=({x},{y},{w},{h}) / "
              f"sigma={sigma:g} / feather={feather}")

    # 拼接片段清单，用于决定每段的调色参数
    seg_info = []
    if (work / "rough_info.json").exists():
        edl_csv = work / "edl.csv"
        if edl_csv.exists():
            import csv as _csv
            with open(edl_csv, "r", encoding="utf-8-sig") as f:
                seg_info = list(_csv.DictReader(f))

    # 整片一次性处理：滤镜按时间分段切换，用 between(t,...) 表达式选段
    # 这样避免逐段渲染再拼接（二次编码会掉画质）
    chain_parts = []
    all_notes = []
    if seg_info:
        seg_ranges = []
        for r in seg_info:
            seg_ranges.append((float(r["tl_in"]), float(r["tl_out"]), r["ep"], int(r["index"])))
        # 统一几何变换（所有段相同）
        chain_parts.append(fit_vertical(info["width"], info["height"]))
        # 调色：按段切换不同参数（level=off 时完全不调色）
        if level != "off":
            for (t0, t1, _ep, _idx) in seg_ranges:
                chain_parts.append(
                    f"eq=saturation='{1.06}+0.05*sin(t)':contrast=1.06:brightness=0.015"
                    f":enable='between(t,{t0:.3f},{t1:.3f})'"
                )
            # 全片统一色彩基调（保证观感一致，不是逐段乱跳）
            chain_parts.append("eq=saturation=1.06:contrast=1.05:gamma=0.99")
            all_notes.append("统一色调 + 分段色温微扰")
        else:
            all_notes.append("调色关闭[off]")
        if level in ("standard", "strong"):
            chain_parts.append("hflip")   # 整片镜像最稳（分镜逐一镜像易被识别为批处理特征簇）
            all_notes.append("整片水平镜像")
    else:
        vf, all_notes = build_filter(info["width"], info["height"], 0, "ep00", level, seed,
                                     not args.no_kenburns)
        chain_parts.append(vf)

    # ---- 原片硬字幕处理 ----
    if sub_mode == "mask":
        chain_parts.append(
            f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@{MASK_ALPHA}:t=fill"
        )
        all_notes.append(f"遮盖原字幕带（{w}x{h} @({x},{y})，{MASK_ALPHA} 黑）")
    elif sub_mode == "blur":
        all_notes.append(
            f"原片字幕局部高斯模糊（{w}x{h} @({x},{y})，sigma={sigma:g}）")
    elif sub_mode == "auto":
        all_notes.append("原片字幕自适应模糊（auto，逐窗检测后处理）")
    else:
        all_notes.append("原片字幕不处理（off）")

    # ---- 羽化遮罩（仅 blur 模式需要）----
    # 硬边矩形在暗背景上会露出接缝；用静态灰度遮罩做 maskedmerge 融合，
    # 遮罩只按 rect+feather 生成一次，之后同名文件直接复用。
    mask_png = None
    use_feather = False
    if sub_mode == "blur":
        if feather <= 0:
            all_notes.append("边缘羽化: 0（硬边）")
        elif not has_filter("maskedmerge"):
            print("[S5] [!] 羽化不可用：本机 ffmpeg 未提供 maskedmerge 滤镜，已回退硬边")
            all_notes.append("羽化不可用(maskedmerge 缺失)，已回退硬边")
        else:
            mask_png = build_mask_png(work, x, y, w, h, feather)
            if mask_png:
                use_feather = True
                all_notes.append(f"边缘羽化 {feather}px（maskedmerge + 静态遮罩）")
            else:
                print("[S5] [!] 羽化不可用：遮罩图生成失败（PIL 缺失？），已回退硬边")
                all_notes.append("羽化不可用(遮罩生成失败)，已回退硬边")

    # 链尾只保留一个 format=yuv420p
    chain_parts.append("format=yuv420p")
    base_vf = ",".join(chain_parts)

    print(f"     滤镜链: {len(chain_parts)} 段")
    for n in all_notes:
        print(f"       · {n}")

    # ---- 渲染 ----
    enc = ["-c:v", "libx264", "-crf", "19", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:a", "copy",
           "-movflags", "+faststart", "-y", out]

    # ================= auto 模式：自适应字幕带模糊 =================
    if sub_mode == "auto":
        from sub_band import detect_windows

        auto_sigma = DEFAULT_AUTO_SIGMA if args.sub_sigma is None else args.sub_sigma
        auto_feather = AUTO_FEATHER if args.sub_feather is None else max(0, args.sub_feather)
        dur = float(info.get("duration") or 0.0)
        print(f"     [auto] 扫描原字幕带（step={args.band_step}s "
              f"pad={args.band_pad} vpad={args.band_vpad} sigma={auto_sigma:g} "
              f"passes={AUTO_BLUR_PASSES} safe={AUTO_SAFE} feather={auto_feather}）…")
        windows = detect_windows(str(inp), dur,
                                 pad=args.band_pad, vpad=args.band_vpad,
                                 step=args.band_step, max_gap=0.5,
                                 edge=AUTO_TIME_EDGE)
        all_notes.append(
            f"自适应字幕模糊 v4：{len(windows)} 个字幕窗，双程 gblur(sigma={auto_sigma:g})，"
            f"box 外扩{AUTO_SAFE}px 硬覆盖 + 外圈{auto_feather}px 羽化，无字幕帧不处理")
        if not windows:
            print("[S5] [!] auto 模式未检测到任何原字幕，本片不做模糊（不强制加遮罩）")
            all_notes.append("未检测到原字幕，未做模糊")

        # 链尾只保留一个 format=yuv420p
        if "format=yuv420p" not in chain_parts[-1]:
            chain_parts.append("format=yuv420p")
        base_vf_auto = ",".join(chain_parts)

        fc, regs = build_adaptive_blur_complex(
            base_vf_auto, windows, auto_sigma,
            TARGET_W, TARGET_H,
            safe=AUTO_SAFE, feather=auto_feather, passes=AUTO_BLUR_PASSES)

        # 每窗一张静态羽化 alpha 图（region 尺寸）；任何一张失败 → 全部回退硬边
        alpha_paths: list[str] = []
        if windows and auto_feather > 0:
            ok = True
            for i, (x, y, w, h) in enumerate(regs):
                ap = str(work / f"_alpha_win{i:03d}.png")
                if not build_alpha_png(ap, w, h, auto_feather):
                    ok = False
                    break
                alpha_paths.append(ap)
            if not ok:
                print("[S5] [!] alpha 图生成失败，回退硬边模糊")
                alpha_paths = []
        if windows and not alpha_paths:
            fc, regs = build_adaptive_blur_complex(
                base_vf_auto, windows, auto_sigma,
                TARGET_W, TARGET_H, safe=AUTO_SAFE, feather=0,
                passes=AUTO_BLUR_PASSES)
            all_notes.append("羽化回退：本次以硬边模式渲染")

        # 滤镜较长，走 script 文件避免 Windows argv 引号/长度问题
        fc_path = str(work / "_adaptive_filter.txt")
        Path(fc_path).write_text(fc, encoding="utf-8")
        cmd = ["-i", inp]
        for ap in alpha_paths:   # 输入 1..n = 各窗静态 alpha（loop 成视频流供 alphamerge）
            # ⚠ 两个坑（都实测踩过）：
            #   a) -loop 1 无限流 → framesync repeatlast 让渲染永不停机；
            #   b) -t 给 dur+1 之类 → overlay 会把主画面重复到副输入结束，
            #      成片多出 1s 冻结尾巴。
            # 正解：-t 精确 = 片长（静态 alpha 差几帧由 repeatlast 无损补齐）
            cmd += ["-loop", "1", "-framerate", f"{info['fps']:g}",
                    "-t", f"{dur:.3f}", "-i", ap]
        cmd += ["-filter_complex_script", fc_path,
                "-map", "[v]", "-map", "0:a?", *enc]
        rc, _, err = fe.run(cmd)
        if rc != 0 or not Path(out).exists():
            print(f"[!] auto 模式渲染失败:\n{err[-1500:]}")
            sys.exit(1)

        oinfo = fe.probe(out)
        print(f"\n[S5] 完成 → {out}")
        print(f"     {oinfo['width']}x{oinfo['height']} {oinfo['duration']:.2f}s "
              f"{oinfo['size_mb']}MB")

        # ---- 结果落盘 ----
        canvas_info = {
            "input": str(inp),
            "output": str(out),
            "mode": "auto",
            "adaptive": True,
            "engine": "v4",           # v4 = 外扩硬覆盖 + 双程高斯 + 外圈羽化
            "windows": windows,       # 检测到的紧贴 box（S6 落位 / S7 覆盖核验依据）
            "regions": [{"x": x, "y": y, "w": w, "h": h} for (x, y, w, h) in regs],
            "safe_px": AUTO_SAFE,
            "feather": auto_feather if alpha_paths else 0,
            "blur_passes": AUTO_BLUR_PASSES,
            "sigma": auto_sigma,
            "applied": len(windows) > 0,
            "dedup_level": level,
            "out_width": oinfo["width"],
            "out_height": oinfo["height"],
            # 兼容 S6/S7：给一个"代表性"字幕带（首个窗）供落位参考
            "rect": ({"x": windows[0]["x0"], "y": windows[0]["y0"],
                       "w": windows[0]["w"], "h": windows[0]["h"]}
                      if windows else {"x": 0, "y": 0, "w": 0, "h": 0}),
        }
        info_path = work / "canvas_info.json"
        fe.json_dump(canvas_info, str(info_path))
        print(f"     写入 {info_path}（{len(windows)} 个字幕窗，羽化={canvas_info['feather']}px）")
        return

    # ================= blur / mask / off 模式（原固定矩形逻辑）=================
    def blur_cmd(feathered: bool) -> list[str]:
        if feathered:
            fc = build_feather_complex(base_vf, x, y, w, h, sigma)
            return ["-i", inp,
                    # -t 截断静态遮罩输入：framesync repeatlast 会跟随无限 loop 流
                    # 永不结束（实测渲染出 2 小时帧），必须给 mask 一个有限时长
                    "-loop", "1", "-framerate", f"{info['fps']:g}",
                    "-t", f"{float(info.get('duration') or 0) + 1.0:.3f}",
                    "-i", mask_png,
                    "-filter_complex", fc,
                    "-map", "[v]", "-map", "0:a?", *enc]
        # 硬边：split → crop+gblur → overlay
        fc = build_blur_complex(base_vf, x, y, w, h, sigma)
        return ["-i", inp, "-filter_complex", fc,
                "-map", "[v]", "-map", "0:a?", *enc]

    if sub_mode == "blur":
        cmd = blur_cmd(use_feather)
    else:
        cmd = ["-i", inp, "-vf", base_vf, *enc]

    rc, _, err = fe.run(cmd)
    if rc != 0 and use_feather:
        # 羽化链路参数不匹配/不支持 → 明确告知后回退硬边，绝不静默失败
        print(f"[S5] [!] 羽化渲染失败（maskedmerge 链路），已回退硬边。ffmpeg 错误:\n{err[-600:]}")
        use_feather, mask_png = False, None
        all_notes.append("羽化不可用(渲染失败)，已回退硬边")
        rc, _, err = fe.run(blur_cmd(False))
    if rc != 0 or not Path(out).exists():
        print(f"[!] 渲染失败:\n{err[-1500:]}")
        sys.exit(1)

    oinfo = fe.probe(out)
    print(f"\n[S5] 完成 → {out}")
    print(f"     {oinfo['width']}x{oinfo['height']} {oinfo['duration']:.2f}s "
          f"{oinfo['size_mb']}MB")
    if (oinfo["width"], oinfo["height"]) != (TARGET_W, TARGET_H):
        print(f"     [!] 尺寸不符预期（应 {TARGET_W}x{TARGET_H}），"
              f"--sub-rect 是按 {TARGET_W}x{TARGET_H} 坐标算的，请核对")

    # ---- 结果落盘（S6/S7 硬校验依据）----
    canvas_info = {
        "input": str(inp),
        "output": str(out),
        "mode": sub_mode,
        "rect": {"x": x, "y": y, "w": w, "h": h},
        "sigma": sigma,
        "feather": feather if (sub_mode == "blur" and use_feather) else 0,
        "mask_png": mask_png,
        "applied": sub_mode != "off",
        "dedup_level": level,
        "out_width": oinfo["width"],
        "out_height": oinfo["height"],
    }
    info_path = work / "canvas_info.json"
    fe.json_dump(canvas_info, str(info_path))
    print(f"     写入 {info_path}")


if __name__ == "__main__":
    main()

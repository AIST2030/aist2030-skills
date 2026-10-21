#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S1 · 素材探测 → 建索引

产出：
  catalog.json          每集元数据 + 帧数
  contact_sheet_<ep>.jpg 每 N 秒抽帧拼成的联系表（用于人工定位高光）
  asr_<ep>.json         台词 + 句级时间戳（若 ASR 可用）

用法：
  python stage1_probe.py --raw E:/BaiduNetdiskDownload --work E:/duanju_work/work --shot-every 8
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".wmv", ".m4v"}

# 联系表拼图参数
COLS = 5
THUMB_W = 300          # 单格宽
LABEL_H = 22           # 时间码标签条高度


def episode_sort_key(p: Path):
    """第1集 / ep01 / 1 —— 尽量按集数排序，中文数字也认。"""
    import re

    m = re.search(r"(\d+)", p.stem)
    if m:
        return int(m.group(1))
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10}
    for c, v in cn.items():
        if c in p.stem:
            return v
    return 999


def build_contact_sheet(src: str, dur: float, out: str, shot_every: float = 8.0):
    """抽帧拼联系表。每格标时间码，方便报「第 X 秒」。"""
    from PIL import Image, ImageDraw, ImageFont

    n = max(1, int(dur // shot_every) + 1)
    times = [min(i * shot_every, max(0, dur - 0.15)) for i in range(n)]
    frames_dir = Path(out).parent / "_frames_tmp"
    # 按源文件区分前缀，避免多集并发写同一批文件名互相覆盖
    prefix = "cs_" + Path(out).stem.replace("contact_sheet_", "")
    tmp = fe.extract_frames(src, times, str(frames_dir), prefix=prefix, width=THUMB_W)
    if not tmp:
        return None

    first = Image.open(tmp[0])
    ratio = first.height / first.width
    cell_h = int(THUMB_W * ratio)
    rows = (len(tmp) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * THUMB_W, rows * (cell_h + LABEL_H)), (18, 18, 20))
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
    except Exception:
        font = ImageFont.load_default()

    for i, f in enumerate(tmp):
        im = Image.open(f).convert("RGB").resize((THUMB_W, cell_h), Image.LANCZOS)
        x = (i % COLS) * THUMB_W
        y = (i // COLS) * (cell_h + LABEL_H)
        sheet.paste(im, (x, y))
        draw.rectangle([x, y + cell_h, x + THUMB_W, y + cell_h + LABEL_H], fill=(35, 35, 38))
        draw.text((x + 5, y + cell_h + 3), f"{int(times[i]) // 60:02d}:{times[i] % 60:05.2f}",
                  fill=(235, 200, 110), font=font)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    # 不删除临时帧：同名前缀会被下次覆盖，且宿主有 safe-delete 守卫会拦截 os.remove。
    # 只在结束时尝试清空目录（失败无害）。
    return out


def main():
    ap = argparse.ArgumentParser(description="S1 素材探测建索引")
    ap.add_argument("--raw", required=True, help="素材目录")
    ap.add_argument("--work", required=True, help="工作目录（中间产物落这里）")
    ap.add_argument("--shot-every", type=float, default=8.0, help="联系表抽帧间隔秒")
    ap.add_argument("--no-sheet", action="store_true", help="跳过联系表")
    ap.add_argument("--no-asr", action="store_true", help="跳过 ASR")
    args = ap.parse_args()

    raw = Path(args.raw)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    vids = sorted([p for p in raw.iterdir()
                   if p.is_file() and p.suffix.lower() in VIDEO_EXT],
                  key=episode_sort_key)
    if not vids:
        print(f"[!] {raw} 下没找到视频文件")
        sys.exit(1)

    print(f"[S1] 发现 {len(vids)} 个视频文件")
    catalog = {"raw_dir": str(raw), "episodes": []}

    for i, v in enumerate(vids, 1):
        ep = f"ep{i:02d}"
        info = fe.probe(str(v))
        dur = info["duration"]
        frames = fe.frame_count(dur, info["fps"])
        aspect = info["width"] / info["height"] if info["height"] else 0
        rec = {
            "ep": ep,
            "file": str(v),
            "name": v.name,
            "duration": round(dur, 3),
            "fps": info["fps"],
            "frames": frames,
            "width": info["width"],
            "height": info["height"],
            "aspect": round(aspect, 4),
            "is_916": abs(aspect - 9 / 16) < 0.01,
            "vcodec": info.get("vcodec"),
            "acodec": info.get("acodec"),
            "has_audio": info["has_audio"],
            "sample_rate": info.get("sample_rate"),
            "sar": info.get("sar"),
            "size_mb": info["size_mb"],
        }
        # 非 9:16 的特殊比例单独标记（如 720x1254）
        if not rec["is_916"] and rec["width"]:
            rec["note"] = f"非标准 9:16（{info['width']}x{info['height']}, SAR {rec.get('sar')}），S5 需特殊裁切"
        print(f"  {ep} {v.name}: {dur:.1f}s {info['width']}x{info['height']}@{info['fps']} "
              f"audio={info['has_audio']} {info['size_mb']}MB")

        if not args.no_sheet and dur > 0:
            sheet = work / f"contact_sheet_{ep}.jpg"
            try:
                build_contact_sheet(str(v), dur, str(sheet), args.shot_every)
                rec["contact_sheet"] = str(sheet)
                print(f"      联系表 → {sheet.name}")
            except Exception as exc:
                print(f"      [!] 联系表失败: {exc}")

        catalog["episodes"].append(rec)

    total = sum(e["duration"] for e in catalog["episodes"])
    catalog["total_duration"] = round(total, 2)
    catalog["total_frames"] = sum(e["frames"] for e in catalog["episodes"])
    catalog["shot_every"] = args.shot_every
    fe.json_dump(catalog, str(work / "catalog.json"))
    print(f"\n[S1] 完成 → {work / 'catalog.json'}")
    print(f"     合计 {len(catalog['episodes'])} 集 / {total:.1f}s / {catalog['total_frames']} 帧")

    if not args.no_asr:
        try:
            import asr_sensevoice
            asr_sensevoice.run_batch(catalog, str(work), model="sensevoice")
        except Exception as exc:
            print(f"\n[S1] ASR 跳过（不影响后续阶段）: {exc}")
            print("     提示：ASR 用于台词字幕与高光语义定位，跳过后 S6 会无字幕。")


if __name__ == "__main__":
    main()

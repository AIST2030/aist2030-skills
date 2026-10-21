#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S4 · 切条 + concat 精确拼接

策略（省时省空间的关键）：
  - EDL 里多段可能来自**同一集**。对同源素材先转 all-intra mezzanine，
    每帧都是 IDR → 之后任意点都能 stream copy 剪切。
  - 全部片段参数一致（同一份 mezzanine 切的）→ concat 解复用器零重编码拼接。
  - 若 EDL 跨集混合，参数仍一致（我们统一转成同一 mezzanine 规格）。

为什么不直接 -c copy 切原片：
  原片关键帧间隔通常 2-10s，stream copy 切点会**回退到上一个关键帧**，
  表现为开头几秒黑屏/卡住或音画错位 —— 恰好破坏 S3 花力气做的帧级吸附。

★多成片（3 集连播）下的两个关键改动：

  1) mezzanine 缓存**跨输出共享**：3 个成片共用 <root>/mezz，
     同一集只在第一次被用到时转码一次。缓存 key 用
     sha1(绝对路径 + size + mtime_ns)，避免不同目录同名文件串味。

  2) 片段文件名带**指纹**：clip{idx}_{fp8}.mp4。
     旧实现只判断「clip01.mp4 存在就复用」→ 人工改了 edl.csv 的 final_in 之后
     仍然吃旧片段，是典型的静默错误（成片看起来正常，但内容不是你要的）。
     指纹覆盖：源文件(路径+size+mtime_ns) + mezz(路径+size+mtime_ns)
     + final_in + duration + crf + preset + 统一规格。
     同时写同名 .json sidecar 记录这些字段，便于人工排查「为什么没复用」。

  3) 跨集参数真正统一：只统一 width=720 是不够的（ep03 是 720x1254、
     其它集 720x1280、还有 25fps 的源），concat demuxer 会因为分辨率/SAR/帧率
     不一致而失败或产生时间戳错乱。这里统一成 720x1280@30 / SAR 1:1 /
     AAC 48kHz 立体声，源无音轨时用 anullsrc 补静音轨。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

# ---- 统一规格（所有 mezzanine / 片段都强制归一到这个规格）----
MEZZ_WIDTH = 720
MEZZ_HEIGHT = 1280
MEZZ_FPS = 30
MEZZ_CRF = 16
MEZZ_PRESET = "veryfast"
CLIP_CRF = 16
CLIP_PRESET = "veryfast"
# 规格指纹：改了统一步骤就必须改这个串，否则会复用按旧规格切的片段
SPEC_TAG = f"v1:{MEZZ_WIDTH}x{MEZZ_HEIGHT}@{MEZZ_FPS}:sar1:aac192k-48k-2ch:ts30000"

# 统一滤镜链：等比缩放到 720x1280 内 → 居中补边 → SAR=1 → 恒定 30fps
UNIFY_VF = (f"scale={MEZZ_WIDTH}:{MEZZ_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={MEZZ_WIDTH}:{MEZZ_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={MEZZ_FPS}")


# ---------------------------------------------------------------- 工具

def file_sig(path: str) -> dict:
    """文件身份签名：绝对路径 + 大小 + mtime_ns（不受同名文件/秒级 mtime 影响）。"""
    p = Path(path).resolve()
    st = p.stat()
    return {"abs": str(p), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def sha1_8(obj) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def sha1_12(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def read_edl(csv_path: str) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def validate_edl(rows: list[dict]) -> list[str]:
    """
    EDL 硬校验。宁可早早报错，也不要带着错切 20 分钟再发现。

    检查：非空 / index 唯一且为正 / duration>0 / final_in>=0 / final_out<=源时长
    """
    errs: list[str] = []
    if not rows:
        return ["EDL 为空（0 行）"]

    seen: dict[int, int] = {}
    src_dur: dict[str, float] = {}
    for i, r in enumerate(rows, 1):
        try:
            idx = int(r["index"])
        except (KeyError, TypeError, ValueError):
            errs.append(f"第 {i} 行 index 缺失或非整数：{r}")
            continue
        if idx in seen:
            errs.append(f"index {idx} 重复（第 {seen[idx]} 行与第 {i} 行）")
        seen[idx] = i
        if idx <= 0:
            errs.append(f"第 {i} 行 index={idx} 必须为正整数")

        try:
            fi = float(r["final_in"])
            fo = float(r["final_out"])
            dur = float(r["duration"])
        except (KeyError, TypeError, ValueError):
            errs.append(f"第 {i} 行 final_in/final_out/duration 缺失或非数值：{r}")
            continue
        if dur <= 0:
            errs.append(f"#{idx} duration={dur} 非法（必须 > 0）")
        if fi < 0:
            errs.append(f"#{idx} final_in={fi} 非法（必须 >= 0）")
        if fo <= fi:
            errs.append(f"#{idx} final_out({fo}) <= final_in({fi})")

        src = r.get("file", "")
        if not src:
            errs.append(f"#{idx} 缺少 file 字段")
            continue
        if not Path(src).exists():
            errs.append(f"#{idx} 源文件不存在：{src}")
            continue
        if src not in src_dur:
            try:
                src_dur[src] = fe.probe(src)["duration"]
            except Exception as exc:
                errs.append(f"#{idx} 无法探测源时长 {src}: {exc}")
                continue
        # 0.05s 容差：浮点与容器时长标注的误差
        if fo > src_dur[src] + 0.05:
            errs.append(f"#{idx} final_out={fo}s 超出源时长 {src_dur[src]:.2f}s（{Path(src).name}）")
    return errs


# ---------------------------------------------------------------- mezzanine

def ensure_mezz(src: str, cache_dir: str, crf: int = MEZZ_CRF,
                preset: str = MEZZ_PRESET) -> str:
    """
    同源素材只转一次 all-intra，后续复用。

    ★缓存 key = sha1(绝对路径 + size + mtime_ns)。旧实现用 stem + 整数 mtime：
      不同目录下同名素材（第1集.mp4）会命中同一个缓存 → 串片。
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    sig = file_sig(src)
    key = sha1_12(f"{sig['abs']}|{sig['size']}|{sig['mtime_ns']}")
    out = cache_dir / f"mezz_{key}.mp4"
    if out.exists() and out.stat().st_size > 0 and _mezz_ok(str(out)):
        print(f"      复用 mezzanine: {out.name}")
        return str(out)
    if out.exists():
        # 上一次跑到一半被中断留下的残片：换个名字重转，不覆盖（避免又留下半个文件）
        print(f"      [!] {out.name} 是不可用的残片（moov 缺失），重新转码")
        out = cache_dir / f"mezz_{key}_r{int(time.time())}.mp4"

    print(f"      转 all-intra mezzanine: {out.name}")
    info = fe.probe(src)
    common = [
        "-vf", UNIFY_VF,
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-g", "1",              # 每帧一个 GOP
        "-bf", "0",             # 禁用 B 帧，避免 DTS 错位
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "30000",   # 统一时间基准，concat 时间戳不会漂
        "-movflags", "+faststart",
    ]
    if info.get("has_audio"):
        args = ["-i", src, *common, "-y", str(out)]
    else:
        # 源无音轨：补一路静音，否则下游 concat/amix 会因流数不一致失败
        args = ["-i", src, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-map", "0:v", "-map", "1:a", "-shortest",
                *common, "-y", str(out)]

    # ★原子发布：先写 .part 再改名。否则进程被中断（Ctrl-C / 超时 / 磁盘满）时会留下
    #   一个「存在但 moov 缺失」的残片，下次被当成有效缓存复用 → 剪切全崩。
    tmp_out = out.with_suffix(".part.mp4")
    rc, _, err = fe.run([*args[:-2], "-y", str(tmp_out)])
    if rc != 0 or not tmp_out.exists() or not _mezz_ok(str(tmp_out)):
        raise RuntimeError(f"all-intra 转码失败 {src}: {err[-600:]}")
    os.replace(str(tmp_out), str(out))
    return str(out)


def _mezz_ok(path: str) -> bool:
    """缓存有效性检查：能探测到时长才算完整（残片 probe 返回 duration=0）。"""
    try:
        return fe.probe(path)["duration"] > 0
    except Exception:
        return False


# ---------------------------------------------------------------- 片段

def cut_clip(mezz: str, dst: str, start: float, dur: float) -> str:
    """
    帧精确剪切（重编码）。

    `-ss` 放 `-i` 之前：现代 ffmpeg 输入端 seek 会从关键帧解码并丢弃到目标点，
    已是帧精确。「-ss 必须放 -i 之后才准」是 ffmpeg 2.1 之前的过时说法。
    与 ffmpeg_env.cut_accurate 等价，额外固定了 video_track_timescale。
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = fe.run([
        "-ss", f"{start:.6f}", "-i", mezz, "-t", f"{dur:.6f}",
        "-vf", "null",
        "-c:v", "libx264", "-crf", str(CLIP_CRF), "-preset", CLIP_PRESET,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "30000",
        "-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
        "-y", dst,
    ])
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"剪切失败 {mezz} @{start}+{dur}: {err[-600:]}")
    return dst


def clip_fingerprint(r: dict, mezz: str, output_id: str) -> tuple[str, dict]:
    """片段指纹 + sidecar 字段。任一影响像素/声音的输入变化都会改变文件名。"""
    fields = {
        "spec": SPEC_TAG,
        "src": file_sig(r["file"]),
        "mezz": file_sig(mezz),
        "final_in": round(float(r["final_in"]), 6),
        "duration": round(float(r["duration"]), 6),
        "fps": r.get("fps"),
        "crf": CLIP_CRF,
        "preset": CLIP_PRESET,
        "output_id": output_id,
    }
    return sha1_8(fields), fields


def main():
    ap = argparse.ArgumentParser(description="S4 切条 + concat 拼接")
    ap.add_argument("--work", required=True, help="输出工作目录（默认取 <work>/edl.csv）")
    ap.add_argument("--mezz-dir", default=None,
                    help="共享 mezzanine 目录（默认 <work>/mezz；多成片时传 <root>/mezz）")
    ap.add_argument("--out", default=None, help="输出路径（默认 work/rough.mp4）")
    ap.add_argument("--clips-dir", default=None, help="片段目录（默认 work/clips）")
    ap.add_argument("--output-id", default=None, help="成片 id（仅用于日志/sidecar 标记）")
    ap.add_argument("--force-recut", action="store_true", help="强制重切（忽略已存在片段）")
    args = ap.parse_args()

    work = Path(args.work)
    edl_csv = work / "edl.csv"
    if not edl_csv.exists():
        print(f"[S4] 找不到 {edl_csv}，请先跑 S3")
        sys.exit(1)
    edl = read_edl(str(edl_csv))

    errs = validate_edl(edl)
    if errs:
        print("[ERROR] EDL 校验未通过，拒绝剪切：")
        for e in errs:
            print(f"    × {e}")
        sys.exit(1)

    clips_dir = Path(args.clips_dir or (work / "clips"))
    mezz_dir = Path(args.mezz_dir) if args.mezz_dir else (work / "mezz")
    clips_dir.mkdir(parents=True, exist_ok=True)
    oid = args.output_id or work.name

    # 1) 按源文件分组，只转一次 mezzanine
    by_src: dict[str, list[dict]] = {}
    for r in edl:
        by_src.setdefault(r["file"], []).append(r)

    print(f"[S4] {oid}: {len(edl)} 段，来自 {len(by_src)} 个源文件 / mezz 目录 {mezz_dir}")
    src2mezz = {}
    for src in by_src:
        src2mezz[src] = ensure_mezz(src, str(mezz_dir))

    # 2) 逐段剪切（文件名带指纹，改了 EDL 一定不会吃旧片）
    clip_paths = []
    reused = 0
    print("\n     剪切片段：")
    for r in edl:
        idx = int(r["index"])
        mezz = src2mezz[r["file"]]
        fp, fields = clip_fingerprint(r, mezz, oid)
        dst = clips_dir / f"clip{idx:02d}_{fp}.mp4"
        sidecar = dst.with_suffix(".json")

        if (dst.exists() and dst.stat().st_size > 0 and sidecar.exists()
                and not args.force_recut):
            try:
                if fe.json_load(str(sidecar)) == fields:
                    reused += 1
                    print(f"      #{idx:02d} 复用 {dst.name}")
                    clip_paths.append(str(dst))
                    continue
                print(f"      #{idx:02d} 指纹已变（{dst.name} 不匹配），重切")
            except Exception:
                print(f"      #{idx:02d} sidecar 不可读，重切")

        start = float(r["final_in"])
        dur = float(r["duration"])
        try:
            cut_clip(mezz, str(dst), start, dur)
            sz = dst.stat().st_size / 1024
            print(f"      #{idx:02d} {r['ep']} {start:.2f}+{dur:.2f}s → {dst.name} ({sz:.0f}KB)")
            clip_paths.append(str(dst))
            # sidecar 只在剪切成功后写：中途失败不会留下「看起来可复用」的标记
            sidecar.write_text(json.dumps(fields, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        except Exception as exc:
            print(f"      [!] #{idx:02d} 剪切失败: {exc}")
            raise

    print(f"     复用 {reused} / 新切 {len(clip_paths) - reused}")

    # 3) concat 零重编码拼接
    out = args.out or str(work / "rough.mp4")
    print("\n     concat 拼接（零重编码）...")
    fe.concat_demuxer(clip_paths, out, workdir=str(work))

    # 4) 时长校验：与 EDL 预期总时长比对，差 >0.5s 视为不完整
    expected = sum(float(r["duration"]) for r in edl)
    actual = fe.probe(out)["duration"]
    delta = abs(actual - expected)

    print(f"\n[S4] 完成 → {out}")
    print(f"     预期 {expected:.2f}s / 实际 {actual:.2f}s / 偏差 {delta:.3f}s")
    if delta > 0.5:
        print("     [!] 偏差 > 0.5s，拼接可能不完整（检查片段是否齐全）")
        raise SystemExit(1)
    print("     [OK] 时长校验通过")
    fe.json_dump({
        "rough": out, "expected": expected, "actual": actual, "delta": delta,
        "clips": clip_paths, "count": len(clip_paths), "reused": reused,
        "mezz_dir": str(mezz_dir), "output_id": oid, "spec": SPEC_TAG,
    }, str(work / "rough_info.json"))


if __name__ == "__main__":
    main()

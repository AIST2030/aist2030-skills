#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPT 备注 → 分句 → 忠实度断言 → TTS → 词级时间轴（通用版）
==========================================================
产出 timeline.json，供 Remotion 场景按「词」触发动画。

核心能力：
  1. 忠实度硬闸门：分句拼接后必须与 PPT 备注逐字一致，否则终止并定位差异字符
  2. 术语发音优化：中英混排（AI/MoE/MCP...）只在合成文本上替换，不破坏忠实度
  3. 词级时间轴：WordBoundary + 首尾静音裁剪 + 线性校准 + 字符索引对齐
  4. 触发器支持：词带 ci（字符索引）字段，动画可按「念到哪个词」精确入场

用法：
  python gen_narration.py --plan plan.json --out ./remotion
  python gen_narration.py --plan plan.json --out ./remotion --force     # 重做全部配音
  python gen_narration.py --plan plan.json --out ./remotion --only 3,7  # 只重做指定页

plan.json 格式：
{
  "pptx": "E:/path/to/deck.pptx",
  "voice": "zh-CN-XiaoxiaoNeural",     // 可选，默认温暖女声
  "rate": "+25%",                       // 可选，默认 1.25 倍速（口播更紧凑）
  "pitch": "-8Hz",                      // 可选，略降更沉稳
  "fps": 30,
  "width": 1080,
  "height": 1440,
  "sentGap": 0.32,                      // 句间停顿（秒）
  "pageGap": 0.60,                      // 页间停顿（秒）
  "pages": {
    "1": {
      "scene": "Cover",                 // 场景模板名
      "title": "封面",                   // 页标题（调试用）
      "units": ["第一句。", "第二句。"]   // TTS 分句；拼接后必须 == PPT 备注
    }
  }
}
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys

import edge_tts
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ---------------------------------------------------------------- 术语发音优化表
# 只在「送进 TTS 的文本」上替换；clean / 字幕 / 忠实度比对仍用原文。
# 按顺序执行；注意规则之间不要互相破坏。
PRONUNCIATION = [
    # --- AI：核心痛点。夹在中文里会被吞音或读成怪调 ---
    (r"(?<![\u4e00-\u9fffA-Za-z])AI(?=[\u4e00-\u9fff])", "A I"),
    (r"(?<=[\u4e00-\u9fff])AI(?![\u4e00-\u9fffA-Za-z])", "A I"),
    (r"(?<=[\u4e00-\u9fff])AI(?=[\u4e00-\u9fff])", " A I "),
    # --- 字母缩写：逐字母读更清晰 ---
    (r"\bMoE\b", "M O E"),
    (r"\bMCP\b", "M C P"),
    (r"\bPC\b", "P C"),
    (r"\bGEO\b", "G E O"),
    (r"\bPDF\b", "P D F"),
    (r"\bAPI\b", "A P I"),
    # --- 数字/单位 ---
    (r"(\d+)K\b", r"\1 K"),
    (r"(\d)\.(\d)\.(\d+)", r"\1 点 \2 点 \3"),
    # 百分号：56.7% → 百分之56.7（edge-tts 对 % 符号读法不稳定，显式转中文）
    (r"(\d+(?:\.\d+)?)%", r"百分之\1"),
]


# ---------------------------------------------------------------- 多音字规避表
# edge-tts 只吃纯文本（SSML phoneme 不可用），用「等长同音替身」解决多音字误读：
# 原词只出现在字幕/忠实度基准（clean），同音替身只送 TTS。
# 逐字等长 → 字符索引与原句 1:1 映射，词边界对齐（ci）不受破坏。
POLYPHONE = {
    "调用": "掉用",   # diào yòng —— edge-tts 常读成 tiáo，必须规避
    "调度": "掉度",   # diào dù —— 与「调用」同字同险
    "长按": "常按",   # cháng àn —— 防御 zhǎng
}


def apply_polyphone(text: str) -> str:
    """多音字词级同音替换（等长，不影响任何索引）"""
    for k, v in POLYPHONE.items():
        assert len(k) == len(v), f"POLYPHONE 必须等长: {k}->{v}"
        text = text.replace(k, v)
    return text


def norm_clean(s: str) -> str:
    """把原句按 POLYPHONE 归一化，供词边界回查用（等长替换，索引与原句一致）"""
    return apply_polyphone(s)


def apply_pronunciation(text: str) -> str:
    out = text
    for pat, rep in PRONUNCIATION:
        out = re.sub(pat, rep, out)
    return apply_polyphone(out)


PUNCT_RE = re.compile(r"[\s\W]+", re.UNICODE)


def bare(s: str) -> str:
    """去空白与标点，保留中英文与数字"""
    return PUNCT_RE.sub("", s)


# ---------------------------------------------------------------- PPT 备注

def extract_notes(pptx_path: str) -> dict:
    from pptx import Presentation
    prs = Presentation(pptx_path)
    notes = {}
    for i, slide in enumerate(prs.slides, 1):
        txt = ""
        if slide.has_notes_slide:
            # ⚠️ 只取备注区！页面上的 shape 文字里常有提示句，混进来必然导致忠实度失败
            txt = slide.notes_slide.notes_text_frame.text.strip()
        notes[i] = txt
    return notes


def fidelity_check(plan: dict):
    """忠实度硬闸门：分句拼接后必须与 PPT 备注逐字一致"""
    notes = extract_notes(plan["pptx"])
    ok = True
    for page_str, meta in plan["pages"].items():
        page = int(page_str)
        joined = "".join(meta["units"])
        src = notes.get(page, "")
        if joined != src:
            ok = False
            print(f"  [FAIL] P{page} 忠实度不一致")
            _show_diff(joined, src)
    if not ok:
        raise SystemExit("忠实度校验失败，终止。")
    total = sum(len(u) for m in plan["pages"].values() for u in m["units"])
    print(f"  [PASS] {len(plan['pages'])} 页备注逐字比对一致（{total} 字）")


def _show_diff(joined: str, src: str):
    """定位首个差异字符，而不是让人肉眼比对长文本"""
    for i, (a, b) in enumerate(zip(joined, src)):
        if a != b:
            print(f"    首个差异 @{i}: 分句={a!r} 备注={b!r}")
            print(f"    分句上下文: ...{joined[max(0, i-20):i+20]}...")
            print(f"    备注上下文: ...{src[max(0, i-20):i+20]}...")
            return
    print(f"    前缀一致，长度差={len(src) - len(joined)}")
    print(f"    分句尾部: {joined[-40:]!r}")
    print(f"    备注尾部: {src[-40:]!r}")


# ---------------------------------------------------------------- 音频工具

def probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise RuntimeError(f"无法读取时长: {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def decode_pcm(path: str, sr: int = 16000):
    r = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", path,
         "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True)
    import numpy as np
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0, sr


def silence_edges(path: str, thresh_db: float = -45.0, frame_s: float = 0.02):
    """检测 (首静音秒数, 尾静音秒数)。TTS 每句自带可观的首尾静音，不裁会让动画早于语音。"""
    import numpy as np
    a, sr = decode_pcm(path)
    step = int(sr * frame_s)
    n = a.size // step
    if n == 0:
        return 0.0, 0.0
    frames = a[:n * step].reshape(n, step)
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    voiced = np.nonzero(db >= thresh_db)[0]
    if voiced.size == 0:
        dur = probe_duration(path)
        return dur, dur
    return voiced[0] * frame_s, (n - 1 - voiced[-1]) * frame_s


def trim_audio(src: str, dst: str, head: float, tail: float):
    """按检测到的首尾静音裁剪（保留 30ms 预卷 / 50ms 尾卷）"""
    dur = probe_duration(src)
    start = max(0.0, head - 0.03)
    end = max(start + 0.1, dur - max(0.0, tail - 0.05))
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", src,
         "-af", f"atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS",
         "-ar", "24000", "-ac", "1",
         "-c:a", "libmp3lame", "-b:a", "96k", dst],
        check=True)
    return start, end - start


# ---------------------------------------------------------------- TTS

async def tts_one(text: str, out_path: str, voice: str, rate: str, pitch: str, sem):
    async with sem:
        last_err = None
        for attempt in range(3):
            try:
                await edge_tts.Communicate(
                    text, voice, rate=rate, pitch=pitch).save(out_path)
                return
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"TTS 失败(重试3次): {last_err}")


async def words_of(text: str, voice: str, rate: str, pitch: str):
    """词边界（offset/duration 单位 100ns）"""
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                boundary="WordBoundary")
    res = []
    async for ch in comm.stream():
        if ch.get("type") == "WordBoundary":
            res.append({
                "t": round(ch["offset"] / 10_000_000, 3),
                "d": round(ch["duration"] / 10_000_000, 3),
                "w": ch["text"],
            })
    return res


def align_words(words: list, clean: str) -> list:
    """
    把词按顺序对齐回 clean 文本，写入字符索引 ci。
    这是「按词触发动画」的基础：TTS 分词粒度不可控，必须按字符位置定位。
    注意：TTS 文本经过同音替换（POLYPHONE），必须先在归一化基准上回查。
    """
    hay = norm_clean(clean)   # 等长替换，索引与原句 1:1
    cursor = 0
    for w in words:
        wc = bare(w["w"])
        if not wc:
            w["ci"] = -1
            continue
        idx = hay.find(wc, cursor)
        if idx < 0:
            idx = hay.find(wc)   # 兜底
        w["ci"] = idx
        if idx >= 0:
            cursor = idx + len(wc)
    return words


async def build(plan: dict, out_root: str, force: bool, only: list | None):
    voice = plan.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = plan.get("rate", "+25%")   # 1.25 倍语速：口播节奏更紧凑，默认提速
    pitch = plan.get("pitch", "-8Hz")
    fps = plan.get("fps", 30)
    width = plan.get("width", 1080)
    height = plan.get("height", 1440)
    sent_gap = plan.get("sentGap", 0.32)
    page_gap = plan.get("pageGap", 0.60)
    # 字幕三态（v1.2）：band=画面下方外扩窄带 / overlay=叠画面底部 / off=无字幕
    # bandHeight=0 且 subtitles=true → 渲染端按叠底（overlay）处理
    self_captions = bool(plan.get("subtitles", True))
    band = int(plan.get("bandHeight", 0)) if self_captions else 0
    size_map = {"small": 0.8, "medium": 1.0, "large": 1.2}
    caption_ratio = size_map.get(str(plan.get("captionSize", "medium")), 1.0)

    audio_dir = os.path.join(out_root, "public", "audio")
    data_dir = os.path.join(out_root, "src", "data")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    print("=" * 66)
    print("PPT 备注 → 词级时间轴")
    print("=" * 66)
    print(f"音色: {voice} | 语速: {rate} | 音调: {pitch}")
    print(f"画布: {width}x{height} @ {fps}fps")

    print("\n[1/4] 忠实度校验（分句 vs PPT 备注）")
    fidelity_check(plan)

    pages_all = sorted(int(k) for k in plan["pages"].keys())
    pages_sel = only if only else pages_all
    if only:
        print("⚠️ --only 模式只重算选中页，时间轴会被截断为选中页；试听用可以，之后必须全量重跑")

    # ---- 合成 TTS ----
    # ⚠️ 设计要点：TTS 直接写 _raw.mp3（覆写，不删除）。
    # 曾经的坑：TTS 写最终 .mp3、[3/4] 再改名进 _raw —— 重跑时旧 _raw 已存在，
    # 改名被跳过，[3/4] 拿旧 raw 裁剪覆盖新音频，新配音白做、时间轴还是旧语速。
    # 且「删旧 _raw 再合成」会触发批量删除安全拦截（50 个文件阈值）。
    # 正解：合成目标就是 _raw，覆写即更新，从根上杜绝新旧混淆。
    print("\n[2/4] TTS 合成")
    jobs = []
    for page in pages_sel:
        for si, text in enumerate(plan["pages"][str(page)]["units"]):
            outp = os.path.join(audio_dir, f"p{page}_s{si}_raw.mp3")
            if force or not os.path.exists(outp):
                jobs.append((outp, apply_pronunciation(text)))
    if jobs:
        sem = asyncio.Semaphore(4)
        await asyncio.gather(*[tts_one(t, o, voice, rate, pitch, sem) for o, t in jobs])
        print(f"  新合成 {len(jobs)} 句 → _raw.mp3")
    else:
        print("  音频已存在，跳过合成（--force 强制重做）")

    print("\n[3/4] 裁剪静音 + 词边界对齐")
    pages_out = []
    t_global = 0.0
    for page in pages_sel:
        meta = plan["pages"][str(page)]
        shots, t_page = [], 0.0
        for si, text in enumerate(meta["units"]):
            sid = f"p{page}_s{si}"
            raw = os.path.join(audio_dir, f"{sid}_raw.mp3")
            final = os.path.join(audio_dir, f"{sid}.mp3")
            if not os.path.exists(raw):
                # 兼容旧目录结构：只有最终文件没有 _raw 时，先把最终文件扶正为 raw
                if os.path.exists(final):
                    os.replace(final, raw)
                else:
                    raise SystemExit(f"缺少音频: {raw}（请先跑 TTS 合成，勿手动删 _raw）")
            head, tail = silence_edges(raw)
            start_off, dur = trim_audio(raw, final, head, tail)

            words = await words_of(apply_pronunciation(text), voice, rate, pitch)
            # 词时间按裁剪量平移（负值钳到 0）
            for w in words:
                w["t"] = round(max(0.0, w["t"] - start_off), 3)
            # 首末词线性校准，消除累计漂移
            if words:
                last_end = max(w["t"] + w["d"] for w in words)
                k = dur / last_end if last_end > 0.05 else 1.0
                if abs(k - 1) > 0.005:
                    for w in words:
                        w["t"] = round(w["t"] * k, 3)
                        w["d"] = round(w["d"] * k, 3)

            clean = bare(text)
            align_words(words, clean)
            # 多音字替身只服务于发音；字幕/显示层必须映射回原文。
            # 替身逐字等长 → ci 与原句 1:1，按 [ci, ci+len) 从 clean 切片即为原文。
            # （曾经漏了这步：字幕把「长按」显示成「常按」、「调用」显示成「掉用」）
            for w in words:
                if w["ci"] >= 0:
                    n = len(bare(w["w"]))
                    w["w"] = clean[w["ci"]:w["ci"] + n]
            shots.append({
                "id": sid,
                "text": text,
                "clean": clean,
                "audioFile": f"audio/{sid}.mp3",
                "start": round(t_page, 3),
                "startFrame": int(round(t_page * fps)),
                "audioDur": round(dur, 3),
                "duration": round(dur + sent_gap, 3),
                "durationFrames": int(round((dur + sent_gap) * fps)),
                "words": words,
            })
            t_page += dur + sent_gap
            print(f"  {sid}: {dur:5.2f}s / {len(text):2d}字 / {len(words):2d}词")

        page_dur = t_page + page_gap - sent_gap
        pages_out.append({
            "id": f"p{page}",
            "page": page,
            "scene": meta.get("scene", "List"),
            "title": meta.get("title", f"P{page}"),
            "start": round(t_global, 3),
            "startFrame": int(round(t_global * fps)),
            "duration": round(page_dur, 3),
            "durationFrames": int(round(page_dur * fps)),
            "shots": shots,
        })
        print(f"  == P{page} [{meta.get('scene')}] {meta.get('title', '')[:24]}: {page_dur:.1f}s ==")
        t_global += page_dur

    out = {
        "fps": fps, "width": width, "height": height,
        # 字幕三态（v1.2）：bandHeight>0 = 外扩窄带（height 含带高）；bandHeight=0 且
        # subtitles=true = 叠底；subtitles=false = 无字幕（渲染端据此整层不渲染）
        "contentHeight": height - band,
        "bandHeight": band,
        "subtitles": self_captions,
        # 基准字号 = 带高比例换算：窄带场景 band 72px ↔ 字 70px；叠底场景按画布高 6.5%
        "captionFontSize": int(
            round((band if band > 0 else int(height * 0.065)) * caption_ratio)
        ),
        "totalSeconds": round(t_global, 3),
        "totalFrames": int(round(t_global * fps)),
        "pages": pages_out,
    }
    tl_path = os.path.join(data_dir, "timeline.json")
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("\n[4/4] 汇总")
    n_shots = sum(len(p["shots"]) for p in pages_out)
    n_words = sum(len(s["words"]) for p in pages_out for s in p["shots"])
    n_bad = sum(1 for p in pages_out for s in p["shots"]
                for w in s["words"] if w["ci"] < 0)
    print(f"  {len(pages_out)} 页 / {n_shots} 句 / {n_words} 词（未对齐 {n_bad}）")
    print(f"  总时长 {t_global:.1f}s ({int(round(t_global * fps))} 帧)")
    print(f"  → {tl_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="plan.json 路径")
    ap.add_argument("--out", required=True, help="Remotion 项目根目录（含 public/ 与 src/）")
    ap.add_argument("--force", action="store_true", help="强制重新合成全部配音")
    ap.add_argument("--only", type=str, default=None, help="只处理指定页，逗号分隔")
    a = ap.parse_args()

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    only = None
    if a.only:
        only = [int(x) for x in a.only.split(",") if x.strip()]
        only = [p for p in only if str(p) in plan["pages"]]
    asyncio.run(build(plan, a.out, a.force, only))


if __name__ == "__main__":
    main()

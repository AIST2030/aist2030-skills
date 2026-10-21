#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文案直出视频 · ① 断句配音 + 词级时间轴（通用版）
================================================
输入一段口播文案（纯文本），产出配音与可踩点的时间轴：

1. 读源文案 txt，按空行分页、按标点分句（**不依赖 PPT**）
2. edge-tts 逐句合成 mp3（默认 YunxiNeural 沉稳男声）
3. 精确裁剪首尾静音，词边界按裁剪量平移 + 线性校准
4. 词与文本按字符索引对齐（ci 字段），供 Remotion 按语音触发动画
5. 生成 remotion/src/data/timeline.json

★ 为什么改成"不依赖 PPT"（2026-10-17）：
  早期版本从 PPTX 备注取稿，两个坑：
    1) 改文案要同步改 PPT，链路冗余；
    2) PPT 备注里的数据错误会静默进配音
       （实测：把「总参数八百亿 + 激活三十亿」写成了「八十亿激活参数版本」）。
  本产线的定位是「文案直出」，文案就是唯一事实源。

用法：
  python gen_narration.py --script script.txt        # 首次：合成 + 建轴
  python gen_narration.py --script script.txt --force # 强制重合成全部
  python gen_narration.py --script script.txt        # 复用音频，只重建时间轴
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# ★ 2026-10-20 修复：产物落点改为「调用方工作目录优先」。
#   原实现恒定写进 skill 安装目录（~/.workbuddy/skills/...），会把配音 mp3、
#   timeline.json 污染到 skill 源里，且多项目并行时互相覆盖。
#   判定：cwd 下存在 remotion/ 或 script.txt 即视为项目根（pipeline.py 以
#   cwd=project 调用，与此一致）；否则回退旧行为，保证向后兼容。
_CWD = os.getcwd()
if os.path.isdir(os.path.join(_CWD, "remotion")) or os.path.isfile(os.path.join(_CWD, "script.txt")):
    ROOT = _CWD
REMOTION = os.path.join(ROOT, "remotion")
AUDIO_DIR = os.path.join(REMOTION, "public", "audio")
DATA_DIR = os.path.join(REMOTION, "src", "data")

VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
RATE = os.environ.get("TTS_RATE", "+25%")   # 1.25倍语速（对齐 PPT 任务，用户明令）
PITCH = os.environ.get("TTS_PITCH", "-8Hz")

FPS = 30
SENT_GAP = 0.32   # 句间呼吸停顿
PAGE_GAP = 0.60   # 页间停顿

# ---------------------------------------------------------------- 术语发音优化表
# 只在「送进 TTS 的文本」上替换；clean / 字幕 / 忠实度比对仍用原文。
# 源自 aist2030-dev-ppt-motion-video-v1 实战（2026-10-17）：
# edge-tts 只接受纯文本（SSML phoneme 用不了），多音字/缩写只能文本层解决。
PRONUNCIATION = [
    # --- 品牌名：AIST2030 逐段读（须先于 AI 规则，否则被 AI 规则截断）---
    (r"AIST2030", "A I S T 2030"),
    # --- AI：核心痛点。夹在中文里会被吞音或读成怪调 ---
    (r"(?<![\u4e00-\u9fffA-Za-z])AI(?=[\u4e00-\u9fff])", "A I"),
    (r"(?<=[\u4e00-\u9fff])AI(?![\u4e00-\u9fffA-Za-z])", "A I"),
    (r"(?<=[\u4e00-\u9fff])AI(?=[\u4e00-\u9fff])", " A I "),
    # --- 字母缩写：逐字母读更清晰 ---
    (r"\bMoE\b", "M O E"),
    (r"\bMCP\b", "M C P"),
    (r"PC(?=[\u4e00-\u9fff])", "P C"),  # PC版/PC端：\b 在汉字前不触发，须单列
    (r"\bPC\b", "P C"),
    (r"\bGEO\b", "G E O"),
    (r"\bPDF\b", "P D F"),
    (r"\bAPI\b", "A P I"),
    (r"\bApp\b", "A P P"),
    (r"\bWeLM\b", "W E L M"),
    # --- 数字/单位 ---
    (r"(\d+)K\b", r"\1 K"),
    (r"(\d)\.(\d)\.(\d+)", r"\1 点 \2 点 \3"),
]


def apply_pronunciation(text: str) -> str:
    out = text
    for pat, rep in PRONUNCIATION:
        out = re.sub(pat, rep, out)
    return out

# ---------------------------------------------------------------- 文案解析
#
# 分页规则（通用，不写死内容）：
#   1) 若有空行分段 → 每个空行段 = 一页
#   2) 若无空行（整篇一行一段）→ 按单换行分段
#   3) 仍只有一段 → 按句子数贪心分页（每页约 SENT_PER_PAGE 句）
#
# 分句规则：在中文句末标点后断开（保留标点，便于 TTS 自然停顿）。
SENT_PER_PAGE = 4
SPLIT_RE = re.compile(r"(?<=[。！？；!?;])")


def parse_script(path: str) -> dict:
    """读源文案 → {页号: [句1, 句2, ...]}"""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    if len(paras) <= 1:
        paras = [p.strip() for p in raw.split("\n") if p.strip()]
    if len(paras) <= 1:
        # 整篇一段：按句子数贪心分页
        sents = [s for s in SPLIT_RE.split(raw) if s.strip()]
        paras = ["".join(sents[i:i + SENT_PER_PAGE])
                 for i in range(0, len(sents), SENT_PER_PAGE)]

    units = {}
    for i, para in enumerate(paras, 1):
        sents = [s.strip() for s in SPLIT_RE.split(para) if s.strip()]
        units[i] = sents or [para]
    return units


def auto_page_meta(units: dict) -> dict:
    """页标题：默认「第 N 段」，可在项目里按需覆盖。"""
    return {n: {"scene": f"p{n}", "title": f"第{n}页"} for n in units}


# 兜底示例（未提供 --script 时使用；正常产线流程一律走 --script）
SAMPLE_UNITS = {
    1: [
        "各位老板，各位伙伴，大家好。",
        "这一期用一分钟讲清微信原生AI助手小微的最新状态。",
        "截至二零二六年十月，小微还在灰度放量阶段，但它的入口已经铺到了二十八个，覆盖微信里几乎所有你常用的地方。",
    ],
    2: [
        "先看进展。",
        "小微二零二六年六月二十号启动灰度，九月扩大范围，九月十五号正式登陆PC版微信。",
        "主模型是微信自研的WeLM，总参数八百亿，采用混合专家架构，每次任务只激活其中三十亿参数，支持十二万八千的长上下文窗口。",
    ],
    3: [
        "再看全景。",
        "二十八个入口分布在九个场景：消息首页的主入口，聊天场景五个，朋友圈场景五个，公众号场景六个，视频号两个，",
        "听一听两个，图片和扫一扫两个，搜索场景一个，还有电脑端四个专属入口。",
        "小微不是一个独立App，而是嵌在你每天用微信的每个环节里。",
    ],
    4: [
        "不管你有没有灰度资格，有四个入口现在所有人都能用：",
        "第一个，公众号文章的AI摘要；第二个，顶部搜索框长按问小微；",
        "第三个，电脑端聊天里右键问AI；第四个，微信内置浏览器打开网页的问AI入口。",
        "现在就可以打开微信试试看。",
    ],
    5: [
        "很多人担心隐私问题，官方已经明确划了三条红线：",
        "第一，小微不会主动读取你的聊天记录，只有你手动点问小微，它才临时调用当前上下文；",
        "第二，分析完立刻丢弃，不存档不上传做训练；",
        "第三，转账、发红包这些资金操作，AI只能生成跳转链接，最终必须你自己点确认，它碰不到你的账户。",
    ],
    6: [
        "现在你可以打开微信，看看消息列表左上角有没有那个绿色眼睛图标。",
        "有的话，恭喜你已经在第一批灰度里了。没有也不用急，前面说的四个入口你现在就能用。",
        "觉得有用可以关注视频号AIST2030，下一期我们详解二十八个入口分别怎么用。",
    ],
}

# 运行时会被 parse_script 覆盖（当传入 --script 时）
UNITS = SAMPLE_UNITS
PAGE_META = {
    1: {"scene": "p1", "title": "封面"},
    2: {"scene": "p2", "title": "最新进展"},
    3: {"scene": "p3", "title": "入口全景"},
    4: {"scene": "p4", "title": "全量开放"},
    5: {"scene": "p5", "title": "安全边界"},
    6: {"scene": "p6", "title": "行动号召"},
}

PUNCT_RE = re.compile(r"[\s\W]+", re.UNICODE)


def bare(s: str) -> str:
    """去空白与标点（保留中英文与数字）"""
    return PUNCT_RE.sub("", s)


def fidelity_check(script_path=None):
    """
    忠实度闸门：分句单元拼接后必须与源文案逐字一致。

    ★ 产线改造（2026-10-17）：本技能是「文案直出视频」，**不依赖 PPT**。
      早期版本比对 PPTX 备注，导致两个问题：
      1) 文案改动要同步改 PPT，链路冗余；
      2) PPT 备注里的数据错误（如把「总参数八百亿+激活三十亿」写成
         「八十亿激活参数版本」）会静默带进配音。
      现改为：优先比对 --script 指定的纯文本文件；未指定则只做自检并告警，
      绝不因为缺 PPT 就终止。
    """
    # 源文案（去空白换行后拼接），用于逐字比对
    src_all = ""
    if script_path and os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            # ⚠ 必须与 joined_all 用同一套规则（去空白 **和标点**）比对，
            # 否则源文案里的逗号句号会造成"假不一致"误报。
            src_all = re.sub(r"[\s\W]+", "", f.read())
    joined = "".join(u for us in UNITS.values() for u in us)
    if not src_all:
        # 无外部文案时只做自检
        src_all = re.sub(r"[\s\W]+", "", joined)

    joined_all = re.sub(r"[\s\W]+", "", joined)
    total_chars = sum(len(u) for us in UNITS.values() for u in us)
    if src_all and joined_all != src_all:
        print("  [WARN] 分句拼接与源文案不一致（已继续，不终止）")
        # 定位首个差异位置，便于人工核对
        for i, (a, b) in enumerate(zip(joined_all, src_all)):
            if a != b:
                print(f"     首个差异 @{i}: 分句『{joined_all[max(0,i-12):i+12]}』"
                      f" vs 源『{src_all[max(0,i-12):i+12]}』")
                break
        else:
            print(f"     长度不同：分句 {len(joined_all)} / 源 {len(src_all)}")
    else:
        print(f"  [PASS] 逐字比对一致（{total_chars} 字）")


# ---------------------------------------------------------------- 音频工具

def probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise RuntimeError(f"无法读取时长: {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def decode_pcm(path: str, sr: int = 16000):
    """解码为 16k 单声道 float32"""
    r = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", path,
         "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True)
    import numpy as np
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return a, sr


def silence_edges(path: str, thresh_db: float = -45.0, frame_s: float = 0.02):
    """返回 (首静音秒数, 尾静音秒数)"""
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
    head = voiced[0] * frame_s
    tail = (n - 1 - voiced[-1]) * frame_s
    return head, tail


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

async def tts_one(text: str, out_path: str, sem):
    async with sem:
        last_err = None
        for attempt in range(3):
            try:
                # ⚠ 发音替换只作用于送 TTS 的文本；音频/字幕/忠实度都用原文
                await edge_tts.Communicate(
                    apply_pronunciation(text), VOICE, rate=RATE,
                    pitch=PITCH).save(out_path)
                return
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"TTS 失败(重试3次): {last_err}")


async def words_of(text: str):
    """edge-tts 词边界（offset/duration 单位为 100ns）"""
    comm = edge_tts.Communicate(apply_pronunciation(text), VOICE, rate=RATE,
                                pitch=PITCH, boundary="WordBoundary")
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
    """把词按顺序对齐到 clean 文本，写入字符索引 ci"""
    cursor = 0
    for w in words:
        wc = bare(w["w"])
        if not wc:
            w["ci"] = -1
            continue
        idx = clean.find(wc, cursor)
        if idx < 0:
            idx = clean.find(wc)  # 兜底：全文找
        w["ci"] = idx
        if idx >= 0:
            cursor = idx + len(wc)
    return words


async def build(force: bool, script_path: str | None = None):
    # 用源文案解析结果覆盖默认分句（这是"换文案即可重出片"的关键）
    global UNITS, PAGE_META
    if script_path and os.path.exists(script_path):
        UNITS = parse_script(script_path)
        PAGE_META = auto_page_meta(UNITS)

    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    print("=" * 66)
    print("文案直出视频 · ① 断句配音 + 词级时间轴")
    print("=" * 66)
    print(f"音色: {VOICE} | 语速: {RATE} | 音调: {PITCH}")
    print(f"文案: {script_path or '（内置示例）'}")
    print(f"分页: {len(UNITS)} 页 / {sum(len(v) for v in UNITS.values())} 句")

    print("\n[1/4] 忠实度校验（分句拼接 vs 源文案）")
    fidelity_check(script_path)

    # ---- 合成 TTS ----
    print("\n[2/4] TTS 合成（逐句 · 并行）")
    jobs = []
    for page, units in UNITS.items():
        for si, text in enumerate(units):
            outp = os.path.join(AUDIO_DIR, f"p{page}_s{si}.mp3")
            if force or not os.path.exists(outp):
                jobs.append((outp, text))
    if jobs:
        sem = asyncio.Semaphore(4)
        await asyncio.gather(*[tts_one(t, o, sem) for o, t in jobs])
        print(f"  新合成 {len(jobs)} 句")
    else:
        print("  音频已存在，跳过合成（--force 强制重做）")

    # ---- 裁剪 + 词边界 ----
    print("\n[3/4] 裁剪首尾静音 + 词边界对齐")
    pages_out = []
    t_global = 0.0
    for page, units in UNITS.items():
        shots = []
        t_page = 0.0
        for si, text in enumerate(units):
            sid = f"p{page}_s{si}"
            raw = os.path.join(AUDIO_DIR, f"{sid}_raw.mp3")
            fresh = os.path.join(AUDIO_DIR, f"{sid}.mp3")
            # ★ 踩坑（2026-10-17）：--force 重新合成了 fresh，但旧的 _raw 仍在，
            #   裁剪从旧 raw 出 → 成片是旧音色 + 新词轴（错位+没换声）。
            #   规则：force 时一律用本次合成结果刷新 raw；非 force 才复用旧 raw。
            if (force or not os.path.exists(raw)) and os.path.exists(fresh):
                os.replace(fresh, raw)
            head, tail = silence_edges(raw)
            final = os.path.join(AUDIO_DIR, f"{sid}.mp3")
            start_off, dur = trim_audio(raw, final, head, tail)
            words = await words_of(text)
            # 词时间按裁剪量平移（负值钳到 0），再做整体线性校准
            for w in words:
                w["t"] = round(max(0.0, w["t"] - start_off), 3)
            if words:
                last_end = max(w["t"] + w["d"] for w in words)
                k = dur / last_end if last_end > 0.05 else 1.0
                if abs(k - 1) > 0.005:
                    for w in words:
                        w["t"] = round(w["t"] * k, 3)
                        w["d"] = round(w["d"] * k, 3)
            clean = bare(text)
            align_words(words, clean)
            shot = {
                "id": sid,
                "text": text,
                "clean": clean,
                "audioFile": f"audio/{sid}.mp3",
                "start": round(t_page, 3),
                "startFrame": int(round(t_page * FPS)),
                "audioDur": round(dur, 3),
                "duration": round(dur + SENT_GAP, 3),
                "durationFrames": int(round((dur + SENT_GAP) * FPS)),
                "words": words,
            }
            shots.append(shot)
            t_page += dur + SENT_GAP
            print(f"  {sid}: {dur:5.2f}s / {len(text):2d}字 / {len(words):2d}词 "
                  f"(首静音 {head:.2f}s 尾静音 {tail:.2f}s)")
        page_dur = t_page + PAGE_GAP - SENT_GAP  # 末句只补页间停顿
        meta = PAGE_META[page]
        pages_out.append({
            "id": f"p{page}",
            "scene": meta["scene"],
            "title": meta["title"],
            "start": round(t_global, 3),
            "startFrame": int(round(t_global * FPS)),
            "duration": round(page_dur, 3),
            "durationFrames": int(round(page_dur * FPS)),
            "shots": shots,
        })
        print(f"  == P{page} {meta['title']}: {page_dur:.1f}s ==")
        t_global += page_dur

    total = t_global
    out = {
        "fps": FPS,
        "width": 1080,
        "height": 1440,
        "totalSeconds": round(total, 3),
        "totalFrames": int(round(total * FPS)),
        "bgm": "audio/bgm.wav",
        "pages": pages_out,
    }
    tl_path = os.path.join(DATA_DIR, "timeline.json")
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- 汇总 ----
    print("\n[4/4] 时间轴汇总")
    n_shots = sum(len(p["shots"]) for p in pages_out)
    n_words = sum(len(s["words"]) for p in pages_out for s in p["shots"])
    print(f"  {len(pages_out)} 页 / {n_shots} 句 / {n_words} 词")
    print(f"  总时长 {total:.1f}s ({int(round(total * FPS))} 帧 @ {FPS}fps)")
    print(f"  → {tl_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="强制重新合成全部配音")
    ap.add_argument("--script", default=None,
                    help="源文案 txt 路径（纯文本）。指定后与其逐字比对；不指定则自检。")
    a = ap.parse_args()
    asyncio.run(build(a.force, a.script))


if __name__ == "__main__":
    main()

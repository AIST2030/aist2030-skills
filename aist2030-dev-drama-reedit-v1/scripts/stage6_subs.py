#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S6 · ASS 硬字幕（严格单行 / 像素级宽度校验 / 时间守恒）+ BGM + 响度归一化

★最容易出错的环节：时间码重映射。
   多段来自不同集、顺序重排后，**原ASR 时间码全部作废**。
   一句台词的原时间是 [ep02 的 85.2s]，它被放到 EDL 第 3 段，
   而第 3 段在成片里从12.4s 开始、且原片内偏移了 2.1s →
   成片时间 = 12.4 + (85.2 - 该段原片入点)。
   漏掉这一步 → 字幕与声音完全错位，且看起来"字幕挺对"很难一眼发现。

★2026-10-17 重写要点（上一版的五个实测缺陷）：
   1. 严格单行：max_lines 恒为 1，split 出的每一块是**独立时间 cue**，
      禁止把多块 join 回一个 cue（join 必然横向溢出画面）。
   2. 宽度用真实字体测像素（PIL ImageFont.getlength），不再用
      「视觉单位 = 中文1.0/英数0.58」硬编码估算 —— 估算在 62px 下
      会算出 15 字 = 930px > 可用宽，导致溢出。
   3. 时间守恒：首 cue start == 原 start、末 cue end == 原 end、
      单调不重叠；按像素视觉权重分配；总时长不够 n*min_dur 时
      只警告 short_reading，绝不丢字、绝不越界。
   4. 跨 EDL 边界的 ASR 句（无词级时间）→ drop 并记原因，不用整句
      文字去配半段声音。
   5. split 后传播 source_ep/source_start/source_end/warn，S7 才看得到异常。

字幕落位：烧录在 S5 高斯模糊带的垂直中心（默认 1080x1920 下 y=1290，
   若 <work>/canvas_info.json 存在且 mode!=off，则自动取 rect 中心）。

★人工校对稿优先（2026-10-17 追加）：
   若 <work>/cues.json 存在（或 --cues 指定），**完全替代** ASR remap。
   理由：ASR 把「巫离」听成「乌狸/无理/屋理/武狸」、「柴小米」听成
   「柴小妹」、「赤血蚕」听成「赤血餐」，text_fixes 只能修已知错字，
   修不了断句、角色前缀（如「巫离：」）和乱码段删除。
   cues 的每条视为**已断好句的一屏**，仅在实测像素超宽时才再切（标 resplit），
   且不再套 DEFAULT_TEXT_FIXES（避免二次污染，除非显式传 --text-fixes）。
"""
from __future__ import annotations

import argparse
import csv as _csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ffmpeg_env as fe  # noqa: E402

from PIL import ImageFont  # noqa: E402

# ---------------------------------------------------------------- 排版常量
CANVAS_W = 1080
DEFAULT_FONT = "Microsoft YaHei"
DEFAULT_FONT_FILE = "C:/Windows/Fonts/msyh.ttc"
FALLBACK_FONT_FILE = "C:/Windows/Fonts/simhei.ttf"

SUB_MARGIN_H = 70        # 左右安全边距（1080x1920）
OUTLINE_PX = 3           # ASS Outline 单边像素（ScaledBorderAndShadow: yes）
WIDTH_SAFETY = 0.06      # 再留 6% 给 libass 与 PIL 的渲染差异 + 粗体增宽

DEFAULT_SUB_CENTER_Y = 1290   # 模糊带 1180~1400 的中心
FONT_LADDER = (56, 52, 48)    # 字号降级阶梯
MIN_CHARS_PER_LINE = 11       # 一行至少能放下几个汉字，否则降字号

DEFAULT_FONT_SIZE = 56   # 56px：15 个全角字 = 840px < 可用宽 877px（余量 37px）
COVERAGE_MIN = 0.7       # ASR 句/cue 与 EDL 段的最低重叠覆盖率，低于则丢弃

# ASR 同音错字纠错表（仅在无人工校对稿时生效；plan / --text-fixes 可覆盖扩充）
DEFAULT_TEXT_FIXES = {
    "乌狸": "巫离",
    "无理": "巫离",
    "屋理": "巫离",
    "武狸": "巫离",
    "无狸": "巫离",
    "柴小妹": "柴小米",
    "苏竹": "柴小米",
    "赤血餐": "赤血蚕",
    "赤血参": "赤血蚕",
    "江之钰": "江之钰",
    "宋玉瑶": "宋玉瑶",
}

MIN_DUR = 0.75           # 每屏最短（太短看不清）
MAX_DUR = 3.5            # 每屏最长（超时就再切）
MIN_FRAG_CHARS = 2# 长度 <=2 字的碎片优先并回相邻块（杜绝孤字/跳行）

# 断句优先级：VAD 句边界 → 强标点 → 弱标点 → 像素硬切
STRONG_SEPS = "。！？；…!?;"
MEDIUM_SEPS = "，、：,:；;—"

_WS_RE = re.compile(r"[ \t\u3000\xa0]+")


# ---------------------------------------------------------------- 文本清洗
# ★用户要求（2026-10-18）：字幕**不要标点符号**、**不要说话人前缀**。
# 说话人前缀形如「族长：」「巫离：」「小米：」「族人：」，只在句首出现，冒号后接台词。
_SPEAKER_PREFIX_RE = re.compile(
    r"^\s*(?:[一-鿿A-Za-z0-9·]{1,6})\s*[：:]\s*"     # 「某某：」
)
# 需要从字幕里**整体删除**的标点（中英文）。保留「-」以外的连字符不做处理。
_STRIP_PUNCT = "，。！？、；：,.!?;:…—－•·　 \t\r\n\"“”‘’()（）【】《》〈〉「」『』~～-－_"


def strip_speaker_prefix(text: str) -> str:
    """
    去掉句首说话人前缀（如「族长：」「巫离：」），只保留后面的台词。

    规则：句首「1~6 个汉字/字母数字 + 冒号」。
      - 冒号后**有**台词  → 剥掉前缀，只留台词。
      - 冒号后**没有**内容（整条只有「巫离：」）→ 该 cue 没有实质台词，返回空串，
        由上层丢弃，避免产生「巫离」这种只有名字的孤字屏。
    """
    if not text:
        return text
    m = _SPEAKER_PREFIX_RE.match(text)
    if m:
        rest = text[m.end():]
        if rest.strip():
            return rest.lstrip()
        # 整条只有「某某：」——没有任何台词，视为空 cue
        return ""
    return text


def clean_text(s: str) -> str:
    """
    清洗台词文本：
      - 拒绝换行与显式 \\N（ASS 里 \\N 会强制换行，单行约束失效）
      - **去掉句首说话人前缀**（「族长：」等）
      - **去掉所有标点符号**（用户明确要求字幕不带标点）
      - 压缩空白

    注意：标点在**断句之前**被剥掉，所以分层断句（按标点断开）将不再有效——
    断句退化为「像素硬切 + 均衡切分」。这符合"无标点单行字幕"的目标，
    也避免了标点单独占一屏（孤字）的畸形输出。
    """
    if not s:
        return ""
    t = str(s)
    t = t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    for tok in ("\\N", "\\n", "\\r", "\\h", "{\\N}"):
        t = t.replace(tok, " ")
    t = _WS_RE.sub(" ", t)
    t = strip_speaker_prefix(t)
    # 删除标点
    for ch in _STRIP_PUNCT:
        t = t.replace(ch, "")
    return t.strip()


def apply_text_fixes(text: str, fixes: dict | None) -> str:
    """
    按纠错字典做替换（断句前应用，含说话人前缀也一并处理）。

    ★仅用于无人工校对稿的 ASR 回退路径。人工稿已人工纠错，
    再套一次字典会造成二次污染（例如把正确的「宿主」改坏）。
    """
    if not text or not fixes:
        return text
    for k, v in fixes.items():
        if k and v and k != v:
            text = text.replace(k, v)
    return text


# ---------------------------------------------------------------- 像素量尺
class TextMeter:
    """
    用真实字体测文本像素宽度。

    ★这是「绝不横向溢出」的唯一可信依据。硬编码的视觉单位估算
     （中文1.0 / 英数0.58）在 62px 字号下会算出 15 单位 = 930px，
     而 1080 宽扣掉左右 90 边距后只剩 900px → 溢出。
    """

    _font_cache: dict = {}

    def __init__(self, font_size: int, font_file: str = DEFAULT_FONT_FILE,
                 canvas_w: int = CANVAS_W, margin_h: int = SUB_MARGIN_H,
                 outline: int = OUTLINE_PX, safety: float = WIDTH_SAFETY):
        self.font_size = int(font_size)
        self.font_file = font_file
        self.canvas_w = int(canvas_w)
        self.margin_h = int(margin_h)
        self.outline = int(outline)
        self.safety = float(safety)
        raw = (self.canvas_w - 2 * self.margin_h - 2 * self.outline) * (1.0 - self.safety)
        self.usable_px = int(math.floor(raw))
        self._font = self._load()

    def _load(self):
        key = (self.font_size, self.font_file)
        if key not in TextMeter._font_cache:
            try:
                TextMeter._font_cache[key] = ImageFont.truetype(self.font_file, self.font_size)
            except Exception:
                TextMeter._font_cache[key] = ImageFont.truetype(FALLBACK_FONT_FILE, self.font_size)
        return TextMeter._font_cache[key]

    def width(self, text: str) -> float:
        if not text:
            return 0.0
        return float(self._font.getlength(text))

    def fits(self, text: str) -> bool:
        return self.width(text) <= self.usable_px

    def capacity_cjk(self) -> int:
        """一行最多能放下几个全角汉字（用于字号降级判断）。"""
        w = self.width("汉")
        if w <= 0:
            return 99
        return int(self.usable_px // w)


def choose_font_size(requested: int, canvas_w: int, font_file: str,
                     margin_h: int = SUB_MARGIN_H, verbose: bool = True):
    """
    字号自适应：requested 装不下（一行汉字数 < MIN_CHARS_PER_LINE）就降到 58/54。

    返回 (font_size, meter)。降级只在确实装不下时发生，且会打印提示。
    """
    ladder = [requested] + [s for s in FONT_LADDER if s < requested]
    seen, ordered = set(), []
    for s in ladder:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    ordered.sort(reverse=True)

    chosen = ordered[-1]
    meter = TextMeter(chosen, font_file, canvas_w, margin_h)
    for fs in ordered:
        m = TextMeter(fs, font_file, canvas_w, margin_h)
        cap = m.capacity_cjk()
        if cap >= MIN_CHARS_PER_LINE:
            chosen, meter = fs, m
            break
        if verbose and fs == requested:
            print(f"[S6] 字号 {fs} 在可用宽 {m.usable_px}px 下仅能放 {cap} 个汉字"
                  f"（需 ≥{MIN_CHARS_PER_LINE}），尝试降级")
        chosen, meter = fs, m
    if verbose and chosen != requested:
        print(f"[S6] 字号自适应：{requested} → {chosen} "
              f"（可用宽 {meter.usable_px}px，一行最多 {meter.capacity_cjk()} 个汉字）")
    return chosen, meter


# ---------------------------------------------------------------- 断句
def _split_at(text: str, seps: str) -> list[str]:
    """在标点**之后**断开（标点留在前一块末尾）。"""
    parts, cur = [], ""
    for ch in text:
        cur += ch
        if ch in seps:
            parts.append(cur)
            cur = ""
    if cur:
        parts.append(cur)
    return parts


def _hard_cut(text: str, meter: TextMeter) -> list[str]:
    """按像素宽度硬切：逐字累加，超出可用宽就断。保证每块 <= usable_px。"""
    out, cur = [], ""
    for ch in text:
        t = cur + ch
        if cur and meter.width(t) > meter.usable_px:
            out.append(cur)
            cur = ch
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def split_to_lines(text: str, meter: TextMeter, level: int = 0) -> list[str]:
    """
    分层断句：强标点 → 弱标点 → 像素硬切。
    每一层都只在"当前块仍超宽"时才下沉到下一层。
    """
    if meter.fits(text):
        return [text]
    if level >= 2:
        return _hard_cut(text, meter)

    seps = STRONG_SEPS if level == 0 else MEDIUM_SEPS
    parts = _split_at(text, seps)
    if len(parts) <= 1:
        return split_to_lines(text, meter, level + 1)

    out: list[str] = []
    for p in parts:
        if meter.fits(p):
            out.append(p)
        else:
            out.extend(split_to_lines(p, meter, level + 1))
    # ★只过滤真空串，不能用 strip() —— 纯空白块也是"字"，丢了就违反不丢字约束
    return [x for x in out if x]


def balanced_partition(text: str, n: int, meter: TextMeter) -> list[str] | None:
    """
    把 text 切成**恰好 n 段**，且最小化「最宽段」的宽度（DP）。
    放不下（最宽段 > 可用宽）时返回 None，由调用方增大 n 重试。

    ★为什么不用"按 limit 贪心硬切"：
      贪心会把 40 字切成 [13,13,13,1]，末尾出现孤字屏；
      40 字 n=4 的最优解是 [10,10,10,10]。
    """
    L = len(text)
    if L == 0:
        return None
    n = max(1, min(int(n), L))
    if n == 1:
        return [text] if meter.fits(text) else None

    # 前缀宽度表：段宽 w(j,i) = cw[i] - cw[j]
    cw = [0.0] * (L + 1)
    for i in range(1, L + 1):
        cw[i] = meter.width(text[:i])

    INF = float("inf")
    dp = [[INF] * (L + 1) for _ in range(n + 1)]
    par = [[-1] * (L + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for k in range(1, n + 1):
        dpk, dpk1, park = dp[k], dp[k - 1], par[k]
        for i in range(k, L + 1):
            best, bj = INF, -1
            lo = k - 1
            for j in range(lo, i):
                v0 = dpk1[j]
                if v0 == INF:
                    continue
                w = cw[i] - cw[j]
                if w >= best:
                    continue
                v = w if w > v0 else v0
                if v < best:
                    best, bj = v, j
            dpk[i] = best
            park[i] = bj

    if dp[n][L] > meter.usable_px:
        return None

    # 回溯切点
    cuts, i, k = [], L, n
    while k > 0:
        j = par[k][i]
        if j < 0:
            return None
        cuts.append(j)
        i, k = j, k - 1
    cuts.reverse()
    parts, prev = [], 0
    for c in cuts[1:]:
        parts.append(text[prev:c])
        prev = c
    parts.append(text[prev:])
    return [p for p in parts if p] or None


def cut_into_n(text: str, n_min: int, meter: TextMeter) -> list[str]:
    """切成 >= n_min 段，取能放下的最小段数（段宽尽量均衡）。"""
    L = len(text)
    total_w = meter.width(text)
    n = max(1, int(n_min), int(math.ceil(total_w / max(1.0, float(meter.usable_px)))))
    while n <= L:
        parts = balanced_partition(text, n, meter)
        if parts:
            return parts
        n += 1
    return _hard_cut(text, meter)


# ---------------------------------------------------------------- 时间分配
def _allocate(start: float, end: float, chunks: list[str], meter: TextMeter,
              min_dur: float = MIN_DUR) -> list[float]:
    """
    按像素视觉权重把 [start,end] 分给 n 块。

    硬约束（缺一不可）：
      - sum(dur) == end - start        （时间守恒）
      - 首 start == 原 start、末 end == 原 end
      - 单调不重叠（相邻 cue 间隙 = 0，绝不重叠）
    软约束：每块 >= min_dur；总时长不够时放弃软约束并记 short_reading。
    """
    n = len(chunks)
    total = max(0.0, end - start)
    if n <= 0:
        return []
    if n == 1:
        return [total]

    w = [max(1e-6, meter.width(c)) for c in chunks]
    ws = sum(w)
    dur = [total * x / ws for x in w]

    # 水位填充：把低于 min_dur 的抬到 min_dur，差额从富余项里按比例扣
    if min_dur * n <= total + 1e-9:
        for _ in range(64):
            below = [i for i in range(n) if dur[i] < min_dur - 1e-9]
            if not below:
                break
            for i in below:
                dur[i] = min_dur
            excess = sum(dur) - total
            if excess <= 1e-9:
                break
            above = [i for i in range(n) if dur[i] > min_dur + 1e-9]
            pool = sum(dur[i] - min_dur for i in above)
            if pool <= 1e-9:
                break
            take = min(excess, pool)
            for i in above:
                dur[i] -= take * (dur[i] - min_dur) / pool

    # 归一化到总时长（保证守恒与末点对齐）
    s = sum(dur)
    if s > 1e-9 and abs(s - total) > 1e-9:
        dur = [x * total / s for x in dur]
    return dur


def _boundaries(start: float, end: float, durs: list[float]) -> list[float]:
    """由时长序列生成单调不减的时间边界，末点严格等于 end。"""
    b = [float(start)]
    for d in durs[:-1]:
        b.append(b[-1] + max(0.0, d))
    b.append(float(end))
    for i in range(1, len(b)):
        if b[i] < b[i - 1]:
            b[i] = b[i - 1]
    # 厘秒取整后仍保持单调
    r = [round(v, 3) for v in b]
    r[-1] = round(float(end), 3)
    for i in range(len(r) - 2, -1, -1):
        if r[i] > r[i + 1]:
            r[i] = r[i + 1]
    return r


# ---------------------------------------------------------------- 分段主函数
def build_subtitle_segments(d: dict, meter: TextMeter,
                            min_dur: float = MIN_DUR,
                            max_dur: float = MAX_DUR,
                            max_lines: int = 1) -> list[dict]:
    """
    把一条台词拆成若干「严格单行 + 按时间顺序播放」的字幕 cue。

    ★与上一版的本质区别：
       - max_lines 恒为 1，且 split 出的每块是**独立 cue**，不再 "".join 拼回去
       - 宽度用像素实测，逐条硬断言 text_width_px <= usable_px
       - 时间守恒：首 start == 原 start、末 end == 原 end、零重叠
       - 过长再切（>max_dur）、过短与相邻块合并（合并后仍必须单行且宽度达标）
    """
    if max_lines != 1:
        raise ValueError(f"严格单行模式下 max_lines 必须为 1，收到 {max_lines}")

    text = clean_text(d.get("text", ""))
    start = float(d.get("start", 0.0))
    end = float(d.get("end", 0.0))
    if not text or end - start <= 0:
        return []

    base = {
        "ep": d.get("ep"),
        "seg": d.get("seg"),
        "source_ep": d.get("source_ep", d.get("ep")),
        "source_start": d.get("source_start", d.get("start")),
        "source_end": d.get("source_end", d.get("end")),
    }
    if d.get("warn"):
        base["warn"] = d["warn"]

    # 片段在成片时间轴上的位置 → 源时间轴位置是**线性**映射（同一 EDL 段内 tl_in + (t-final_in)）。
    # 记录父cue 的 [source_start, source_end] 与成片 [start, end]，供每个片段按比例插值出
    # 自己的真实源区间——否则片段会继承父cue 整段源时间，S7 反算 expect 时必然误报"错位"。
    p_ss = float(base["source_start"])
    p_se = float(base["source_end"])

    total = end - start
    # 时长决定的最少屏数：>max_dur 就要再切
    n_time = max(1, int(math.ceil(total / max_dur - 1e-9)))

    # 先按「标点优先 + 像素硬切」分层断句
    chunks = split_to_lines(text, meter)
    chunks = [c for c in chunks if c]
    if not chunks:
        return []

    # 标点切出的屏数不够（会有单屏超过 max_dur）→ 改用均衡切分
    if len(chunks) < n_time:
        chunks = cut_into_n(text, n_time, meter)

    # 碎片归并：<= MIN_FRAG_CHARS 字的孤立块并回相邻块（观感），仍须单行且不溢出
    for _ in range(8):
        idx = next((i for i, c in enumerate(chunks)
                    if len(c) <= MIN_FRAG_CHARS and len(chunks) > 1), None)
        if idx is None:
            break
        done = False
        for a, b in ((idx - 1, idx), (idx, idx + 1)):
            if 0 <= a and b < len(chunks) and meter.fits(chunks[a] + chunks[b]):
                chunks = chunks[:a] + [chunks[a] + chunks[b]] + chunks[b + 1:]
                done = True
                break
        if not done:
            break

    # 迭代收敛：过长再切 / 过短与相邻块合并（合并后仍必须单行且宽度达标）
    seen_states = set()
    for _ in range(16):
        state = tuple(chunks)
        if state in seen_states:
            break
        seen_states.add(state)

        durs = _allocate(start, end, chunks, meter, min_dur)
        too_long = [i for i, x in enumerate(durs) if x > max_dur + 1e-9]
        if too_long:
            new_chunks: list[str] = []
            for i, c in enumerate(chunks):
                if i in too_long:
                    k = int(math.ceil(durs[i] / max_dur - 1e-9))
                    new_chunks.extend(cut_into_n(c, k, meter))
                else:
                    new_chunks.append(c)
            if new_chunks and new_chunks != chunks:
                chunks = [x for x in new_chunks if x]
                continue

        too_short = [i for i, x in enumerate(durs) if x < min_dur - 1e-9]
        if too_short and len(chunks) > 1:
            i = min(too_short, key=lambda k: durs[k])
            cand = []
            if i > 0:
                cand.append((durs[i - 1], i - 1, i))
            if i + 1 < len(chunks):
                cand.append((durs[i + 1], i, i + 1))
            cand.sort()
            merged = False
            for _, a, bq in cand:
                comb = chunks[a] + chunks[bq]
                if meter.fits(comb):
                    chunks = chunks[:a] + [comb] + chunks[bq + 1:]
                    merged = True
                    break
            if merged:
                continue
        break

    # ---- 收尾：彻底消除孤字屏（1 字）/ 极短碎片 ----
    # 用户要求"杜绝孤字跳行"。像素硬切 / 均衡切分在极端长度下仍可能留下
    # 1 字尾块（如「…本是为了凉州州那位公|主」）。这里做最后一道收敛：
    # 反复把「<=1 字的块」并入相邻块（优先并入更短的一侧以保持均衡），
    # 只要合并后不超宽就执行，直到没有 1 字块为止。
    def _eliminate_orphans(chunks: list[str]) -> list[str]:
        cs = [c for c in chunks if c]
        changed = True
        while changed and len(cs) > 1:
            changed = False
            for i, c in enumerate(cs):
                if len(c) > 1:
                    continue
                # 优先并入较短的一侧，保持整体均衡
                opts = []
                if i > 0:
                    opts.append((len(cs[i - 1]), i - 1))
                if i + 1 < len(cs):
                    opts.append((len(cs[i + 1]), i + 1))
                opts.sort()
                merged = False
                for _len, j in opts:
                    a, b = min(i, j), max(i, j)
                    comb = cs[a] + cs[b]
                    if meter.fits(comb):
                        cs = cs[:a] + [comb] + cs[b + 1:]
                        changed = merged = True
                        break
                if merged:
                    break
            if changed:
                continue
            # 合并失败（两侧都放不下）→ 整组重新切分。
            # 孤字通常来自「刚好卡在行宽上限」的切分：先把整组用 DP 均衡重切成 n 块，
            # 每块 >=2 字且不超宽；放不下就多切一块（n+1）腾出合并余量。
            joined = "".join(cs)
            for nn in (len(cs), len(cs) + 1, len(cs) + 2):
                if nn > len(joined):
                    break
                alt = balanced_partition(joined, nn, meter)
                if alt and all(len(a) >= 2 for a in alt):
                    cs = alt
                    changed = True
                    break
            # 仍失败（文本太短分不动）：接受当前，至少不是空白屏
            break
        return cs

    chunks = _eliminate_orphans(chunks)

    durs = _allocate(start, end, chunks, meter, min_dur)
    bounds = _boundaries(start, end, durs)

    out: list[dict] = []
    for i, c in enumerate(chunks):
        wpx = meter.width(c)
        # ★硬断言：绝不横向溢出。这里炸掉说明断句/量尺有 bug，必须暴露而不是静默降级
        if wpx > meter.usable_px:
            raise AssertionError(
                f"字幕横向溢出：{wpx:.1f}px > 可用 {meter.usable_px}px "
                f"（字号 {meter.font_size}）文本=「{c}」"
            )
        a, b = bounds[i], bounds[i + 1]
        # 片段的源时间 = 父cue 源区间按成片占比线性插值（成片↔源在同段内是线性映射）。
        # 这样每个片段都带自己真实的 source_start/source_end，S7 反算 expect 才对得上。
        if total > 1e-9 and (p_se - p_ss) > 1e-9:
            frag_ss = p_ss + (a - start) / total * (p_se - p_ss)
            frag_se = p_ss + (b - start) / total * (p_se - p_ss)
        else:
            frag_ss, frag_se = p_ss, p_se
        # ★绝不因"太短"而丢弃 cue —— 丢 cue 就是丢字，只允许记 short_reading 警告
        item = dict(base)
        item.update({
            "start": a,
            "end": b,
            "text": c,
            "source_start": round(frag_ss, 3),
            "source_end": round(frag_se, 3),
            "text_width_px": round(wpx, 2),
            "max_width_px": meter.usable_px,
            "line_count": 1,
            "font_size": meter.font_size,
        })
        if b - a < min_dur - 1e-6:
            item["warn"] = "short_reading"
        out.append(item)
    return out


# ---------------------------------------------------------------- 时间码
def ass_ts(sec: float) -> str:
    """
    秒 → ASS 时间码 H:MM:SS.CC（厘秒）。

    ★上一版把 (sec - int(sec))*100 的 .999 情形先 round 到 100 再硬夹成 99，
    会把 1.999s 错写成 0:00:01.99（实际应进位为 0:00:02.00）。
    正确做法：先算总厘秒再逐级 divmod 进位。
    """
    sec = max(0.0, float(sec))
    # ★用 half-up 而不是 round()：round() 是银行家取整，
    #   12.345 → 1234（.34）而 12.355 → 1236（.36），同一批时间码进位方向不一致。
    total_cs = int(math.floor(sec * 100.0 + 0.5 + 1e-9))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------- 重映射
def _rect_center_y(canvas_info: dict, default: int) -> int:
    r = canvas_info.get("rect")
    if isinstance(r, dict) and all(k in r for k in ("y", "h")):
        return int(round(float(r["y"]) + float(r["h"]) / 2.0))
    if isinstance(r, (list, tuple)) and len(r) == 4:
        return int(round(float(r[1]) + float(r[3]) / 2.0))
    return int(default)


def remap_dialogues(edl_rows: list[dict], asr_data: dict, work: str = "",
                    text_fixes: dict | None = None,
                    coverage_min: float = COVERAGE_MIN):
    """
    ★核心：把各集 ASR 台词映射到成片时间轴。返回 (dialogues, dropped)。

    公式：成片时间 = 该段在成片上的起点 + (台词原时间 - 该段原片入点)

    丢弃规则（都记进 dropped，供 S7 核对）：
      - overlap_too_short：与 EDL 段重叠 < 0.12s
      - cross_boundary   ：覆盖率 coverage = 重叠/(句原时长) < coverage_min。
                           无词级时间时若保留跨边界整句，会出现
                           "整句文字配半段声音"的错位，宁可丢。
                           ★注意：不能只要碰边界就丢 —— 覆盖率 0.95 的
                           句子丢掉等于凭空损失一屏字幕。
    """
    out: list[dict] = []
    dropped: list[dict] = []
    ep_asr = {k: (v or {}).get("sentences", []) for k, v in (asr_data or {}).get("episodes", {}).items()}

    for r in edl_rows:
        ep = r["ep"]
        try:
            fin, fout = float(r["final_in"]), float(r["final_out"])
            tl_in = float(r["tl_in"])
        except (KeyError, TypeError, ValueError):
            continue
        seg_dur = fout - fin
        if seg_dur <= 0:
            continue
        for idx, s in enumerate(ep_asr.get(ep, [])):
            try:
                a, b = float(s["start"]), float(s["end"])
            except (KeyError, TypeError, ValueError):
                continue
            raw = apply_text_fixes(clean_text(s.get("text", "")), text_fixes)
            if not raw or b <= a:
                continue

            ov_a, ov_b = max(a, fin), min(b, fout)
            rec = {
                "ep": ep, "seg": r.get("index"),
                "src_index": idx,
                "src_start": a, "src_end": b,
                "src_text": raw[:80],
                "edl_in": fin, "edl_out": fout, "tl_in": tl_in,
            }
            if ov_b <= ov_a:
                continue          # 与该 EDL 段完全无关（不在成片里），不算"丢弃"
            if ov_b - ov_a < 0.12:
                rec["reason"] = "overlap_too_short"
                rec["overlap"] = round(ov_b - ov_a, 3)
                dropped.append(rec)
                continue
            # 跨边界：覆盖率不足才丢（保留覆盖率高的即使略微跨界，时间会裁剪）
            coverage = (ov_b - ov_a) / (b - a)
            if coverage < coverage_min:
                rec["reason"] = "cross_boundary"
                rec["overlap"] = round(ov_b - ov_a, 3)
                rec["coverage"] = round(coverage, 3)
                dropped.append(rec)
                continue

            new_a = tl_in + (ov_a - fin)
            new_b = tl_in + (ov_b - fin)
            # ★上一版写成 min(new_b, new_b) —— 空操作，等于没夹。
            # 正确：夹到该段在成片上的结束点 tl_in + 段时长。
            new_b = min(new_b, tl_in + seg_dur)
            if new_b <= new_a:
                rec["reason"] = "zero_after_remap"
                dropped.append(rec)
                continue
            out.append({
                "start": round(new_a, 3),
                "end": round(new_b, 3),
                "text": raw,
                "ep": ep,
                "seg": r.get("index"),
                "source_ep": ep,
                "source_start": round(a, 3),
                "source_end": round(b, 3),
            })

    out.sort(key=lambda x: (x["start"], x["end"]))

    # 相邻台词互斥：跨段重排后仍可能出现轻微重叠，夹掉并记 warn（绝不丢字）
    for i in range(1, len(out)):
        if out[i]["start"] < out[i - 1]["end"]:
            ov = out[i - 1]["end"] - out[i]["start"]
            out[i - 1]["end"] = out[i]["start"]
            tag = f"与上一条重叠 {ov:.2f}s（已前移结尾对齐）"
            out[i - 1]["warn"] = tag
            if out[i - 1]["end"] <= out[i - 1]["start"]:
                out[i - 1]["end"] = out[i - 1]["start"]

    # 排序后再按 seg 稳定一次（同一 start 时保持 EDL 顺序）
    out = [x for x in out if x["end"] - x["start"] > 0]
    return out, dropped


# ---------------------------------------------------------------- 人工校对稿
def load_cues(path: str) -> dict:
    """
    读取人工校对稿 cues.json → {ep: [{start, end, text, ...}, ...]}。

    ★文件格式容忍很重要：真实稿为了说明来源，顶层混了
      project / platform / source / note / speakers / review_flags /
      dropped_garbage / pending_calibration 等元数据键，
      直接 for k, v in data.items() 会把 dict/list 当台词列表遍历 → TypeError。
      这里只认「以 ep 开头且值为 list」的键，其余一律忽略。
    """
    data = fe.json_load(path)
    if not isinstance(data, dict):
        raise ValueError(f"cues 文件顶层必须是对象: {path}")

    cues: dict = {}
    skipped_keys: list[str] = []
    for k, v in data.items():
        if not isinstance(k, str) or not k.lower().startswith("ep"):
            skipped_keys.append(str(k))
            continue
        if not isinstance(v, list):
            skipped_keys.append(k)
            continue
        items: list[dict] = []
        for i, c in enumerate(v):
            if not isinstance(c, dict):
                continue
            try:
                a, b = float(c["start"]), float(c["end"])
            except (KeyError, TypeError, ValueError):
                continue
            txt = clean_text(c.get("text", ""))
            if not txt:
                continue
            if b <= a:
                b = a + 0.01
            item = {"start": round(a, 3), "end": round(b, 3), "text": txt,
                    "src_index": i, "t_src": c.get("t_src")}
            items.append(item)
        if items:
            cues[k] = items
    print(f"[S6] 人工校对稿 {Path(path).name}：载入 "
          + ", ".join(f"{k}={len(v)}条" for k, v in cues.items())
          + f"（忽略非台词键 {len(skipped_keys)} 个）")
    return cues


def remap_cues(edl_rows: list[dict], cues: dict,
               coverage_min: float = COVERAGE_MIN):
    """
    ★把人工校对稿映射到成片时间轴（完全替代 ASR remap）。返回 (dialogues, dropped)。

    映射公式： tl_in + (max(start, final_in) - final_in)
    clamp   ： 段的成片结束点 tl_in + seg_dur
    过滤    ： 覆盖率 < coverage_min → 丢弃（reason=partial_by_edl）
    文本    ： ★原样保留，不去说话人前缀（「巫离：」的宽度必须计入），
               不做任何纠错改写 —— 人工稿是权威源。
    """
    out: list[dict] = []
    dropped: list[dict] = []

    for r in edl_rows:
        ep = r.get("ep")
        try:
            fin, fout = float(r["final_in"]), float(r["final_out"])
            tl_in = float(r["tl_in"])
        except (KeyError, TypeError, ValueError):
            continue
        seg_dur = fout - fin
        if seg_dur <= 0:
            continue

        for c in cues.get(ep, []):
            a, b = float(c["start"]), float(c["end"])
            ov_a, ov_b = max(a, fin), min(b, fout)
            overlap = ov_b - ov_a
            if overlap <= 0:          # 与该段无关（台词在别处），不算丢弃
                continue
            coverage = overlap / (b - a) if b > a else 0.0

            rec = {
                "ep": ep, "seg": r.get("index"),
                "src_index": c.get("src_index"),
                "src_start": a, "src_end": b,
                "src_text": c["text"][:80],
                "edl_in": fin, "edl_out": fout, "tl_in": tl_in,
                "overlap": round(overlap, 3),
                "coverage": round(coverage, 3),
            }
            if coverage < coverage_min:
                rec["reason"] = "partial_by_edl"
                dropped.append(rec)
                continue

            new_a = tl_in + (ov_a - fin)
            new_b = tl_in + (ov_b - fin)
            if new_a < tl_in:
                new_a = tl_in
            if new_b > tl_in + seg_dur:
                new_b = tl_in + seg_dur
            if new_b <= new_a:
                rec["reason"] = "zero_after_remap"
                dropped.append(rec)
                continue

            out.append({
                "start": round(new_a, 3),
                "end": round(new_b, 3),
                "text": c["text"],          # ★原文照搬：前缀保留、不纠错
                "ep": ep,
                "seg": r.get("index"),
                "source_ep": ep,
                "source_start": a,
                "source_end": b,
                "coverage": round(coverage, 3),
                "source": "cues",
            })

    out.sort(key=lambda x: (x["start"], x["end"]))
    for i in range(1, len(out)):
        if out[i]["start"] < out[i - 1]["end"]:
            ov = out[i - 1]["end"] - out[i]["start"]
            out[i - 1]["end"] = out[i]["start"]
            out[i - 1]["warn"] = f"与上一条重叠 {ov:.2f}s（已前移结尾对齐）"
            if out[i - 1]["end"] <= out[i - 1]["start"]:
                out[i - 1]["end"] = out[i - 1]["start"]
    return [x for x in out if x["end"] - x["start"] > 0], dropped


# ---------------------------------------------------------------- ASS 写出
def build_ass_header(width: int, height: int, font: str, font_size: int,
                     margin_h: int, margin_v: int,
                     primary: str = "&H00FFFFFF", outline_col: str = "&H00000000",
                     border: int = OUTLINE_PX) -> str:
    """
    MarginV 由「字幕垂直中心 y」反算：\an2 是底部对齐，
    文字盒底边落在 height - MarginV，故
        MarginV = height - center_y - 字高/2
    """
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{font_size},{primary},{primary},{outline_col},{outline_col},-1,0,0,0,100,100,0,0,1,{border},1,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def margin_v_for_center(height: int, center_y: int, font_size: int) -> int:
    """\an2 下让单行文字垂直居中于 center_y 所需的 MarginV。"""
    return int(round(height - center_y - font_size * 0.5))


def write_ass(path: str, dialogues: list[dict], width: int, height: int,
              font: str = DEFAULT_FONT, font_size: int = 62,
              center_y: int = DEFAULT_SUB_CENTER_Y,
              meter: TextMeter | None = None) -> str:
    """
    写出 ASS，并把每条 cue 的 text_width_px / max_width_px / line_count
    回填进 dialogue（供 subs_debug.json 与 S7 硬校验）。
    """
    if meter is None:
        meter = TextMeter(font_size, DEFAULT_FONT_FILE, width)
    margin_v = margin_v_for_center(height, center_y, font_size)
    lines = [build_ass_header(width, height, font, font_size,
                              meter.margin_h, margin_v)]

    for d in dialogues:
        txt = clean_text(d.get("text", ""))
        if not txt:
            continue
        wpx = meter.width(txt)
        if wpx > meter.usable_px:
            raise AssertionError(
                f"write_ass 拦到溢出字幕：{wpx:.1f}px > {meter.usable_px}px 「{txt}」")
        # 单行硬校验：文本里不允许任何换行
        if "\n" in txt or "\r" in txt or "\\N" in txt:
            raise AssertionError(f"write_ass 拦到多行字幕：「{txt}」")
        d["text"] = txt
        d["text_width_px"] = round(wpx, 2)
        d["max_width_px"] = meter.usable_px
        d["line_count"] = 1
        d["font_size"] = meter.font_size
        d["center_y"] = center_y
        esc = txt.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        lines.append(
            f"Dialogue: 0,{ass_ts(d['start'])},{ass_ts(d['end'])},Main,,0,0,0,,"
            f"{{\\an2}}{esc}")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- BGM
def generate_bgm(dst: str, duration: float, style: str = "tense") -> str:
    """
    程序化生成 BGM（零版权风险）。

    用 lavfi 的 `aevalsrc` 合成：低频铺底正弦 + 缓慢起伏。
    短剧「紧张/逆袭」基调：根音 55Hz(A1) + 八度 + 五度，低音量。

    ⚠ 踩坑：表达式里含 `+`/`:` 时，**整个 expr 必须用单引号包起来**，
    否则 aevalsrc 会把 `+` 当成滤镜参数分隔符，报
    `Could not set non-existent option 's'`。
    """
    bases = {
        "tense":    "0.10*sin(55*2*PI*t)+0.05*sin(110*2*PI*t)+0.03*sin(165*2*PI*t)",
        "epic":     "0.11*sin(58*2*PI*t)+0.06*sin(116*2*PI*t)+0.035*sin(174*2*PI*t)+0.02*sin(232*2*PI*t)",
        "suspense": "0.09*sin(49*2*PI*t)+0.05*sin(98*2*PI*t)+0.025*sin(147*2*PI*t)",
    }
    expr = bases.get(style)
    if expr is None:
        rc, _, err = fe.run(["-f", "lavfi", "-i",
                             f"anullsrc=r=44100:cl=stereo:d={duration:.2f}",
                             "-c:a", "aac", "-b:a", "128k", "-y", dst])
        if rc != 0 or not Path(dst).exists():
            raise RuntimeError(f"静音轨生成失败: {err[-400:]}")
        return dst

    src = f"aevalsrc='{expr}':s=44100:d={duration:.2f}"
    fade_out_start = max(0.0, duration - 2.0)
    rc, _, err = fe.run([
        "-f", "lavfi", "-i", src,
        "-af", (f"tremolo=f=0.25:d=0.18,lowpass=f=900,highpass=f=40,"
                f"afade=t=in:d=1.5,afade=t=out:st={fade_out_start:.2f}:d=2.0"),
        "-ac", "2",
        "-c:a", "aac", "-b:a", "128k", "-y", dst,
    ])
    if rc != 0 or not Path(dst).exists():
        raise RuntimeError(f"BGM 生成失败: {err[-400:]}")
    return dst


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="S6 ASS字幕 + BGM + 响度")
    ap.add_argument("--work", required=True)
    ap.add_argument("--in", dest="inp", default=None, help="默认 work/canvas.mp4")
    ap.add_argument("--out", default=None, help="默认 work/final.mp4")
    ap.add_argument("--edl", default=None, help="默认 work/edl.csv")
    ap.add_argument("--asr", default=None, help="默认 work/asr.json")
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--font-file", default=DEFAULT_FONT_FILE)
    ap.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE)
    ap.add_argument("--margin-h", type=int, default=SUB_MARGIN_H)
    ap.add_argument("--cues", default=None,
                    help="人工校对稿 JSON（默认 <work>/cues.json，存在即启用并替代 ASR）")
    ap.add_argument("--no-cues", action="store_true",
                    help="显式忽略 cues.json，退回 ASR + text_fixes 路径")
    ap.add_argument("--coverage-min", type=float, default=COVERAGE_MIN,
                    help=f"ASR句/cue 与 EDL 段的最低重叠覆盖率（默认 {COVERAGE_MIN}）")
    ap.add_argument("--text-fixes", default=None,
                    help='JSON 字符串追加纠错词表，如 \'{"乌狸":"巫离"}\'')
    ap.add_argument("--sub-center-y", type=int, default=None,
                    help=f"字幕垂直中心（默认取 canvas_info.rect 中心，否则 {DEFAULT_SUB_CENTER_Y}）")
    ap.add_argument("--min-dur", type=float, default=MIN_DUR)
    ap.add_argument("--max-dur", type=float, default=MAX_DUR)
    ap.add_argument("--no-bgm", action="store_true", help="不加 BGM")
    ap.add_argument("--bgm-style", default="tense", choices=["tense", "epic", "suspense", "none"])
    ap.add_argument("--bgm-db", type=float, default=-22.0, help="BGM 音量 dB（默认 -22，不盖过人声）")
    ap.add_argument("--target-lufs", type=float, default=-16.0)
    ap.add_argument("--min-bitrate", dest="min_bitrate", type=float, default=None,
                    help="成片最低码率 Mbps（如 12）。设置后字幕烧录段改用 "
                         "b:v/minrate/maxrate 码率模式，对齐平台 12-18Mbps 建议；"
                         "不设则维持 CRF 19 质量模式")
    ap.add_argument("--no-subs", action="store_true")
    ap.add_argument("--plan", default=None)
    args = ap.parse_args()

    work = Path(args.work)
    inp = args.inp or str(work / "canvas.mp4")
    out = args.out or str(work / "final.mp4")
    if not Path(inp).exists():
        print(f"[S6] 找不到 {inp}，请先跑 S5")
        sys.exit(1)

    info = fe.probe(inp)
    W, H = info["width"], info["height"]
    dur = info["duration"]
    print(f"[S6] 输入 {Path(inp).name}: {W}x{H} {dur:.2f}s")

    plan = fe.json_load(args.plan) if (args.plan and Path(args.plan).exists()) else {}
    subs_cfg = plan.get("subtitle", {})
    font = subs_cfg.get("font", args.font)
    font_file = subs_cfg.get("font_file", args.font_file)
    font_size = int(subs_cfg.get("font_size", args.font_size))
    margin_h = int(subs_cfg.get("margin_h", args.margin_h))
    args.min_dur = float(subs_cfg.get("min_dur", args.min_dur))
    args.max_dur = float(subs_cfg.get("max_dur", args.max_dur))

    # 纠错词表：内置默认 ← plan.json ← --text-fixes（后者覆盖前者）
    # ★仅用于 ASR 回退路径；走人工校对稿时不套用（避免二次污染）
    text_fixes = dict(DEFAULT_TEXT_FIXES)
    if isinstance(subs_cfg.get("text_fixes"), dict):
        text_fixes.update(subs_cfg["text_fixes"])
    if args.text_fixes:
        try:
            user_fixes = json.loads(args.text_fixes)
            if isinstance(user_fixes, dict):
                text_fixes.update(user_fixes)
        except json.JSONDecodeError as exc:
            print(f"[!] --text-fixes 不是合法 JSON，已忽略: {exc}")
    audio_cfg = plan.get("audio", {})
    if not args.no_bgm:
        args.bgm_style = audio_cfg.get("bgm_style", args.bgm_style)
        args.bgm_db = audio_cfg.get("bgm_db", args.bgm_db)
    args.target_lufs = audio_cfg.get("target_lufs", args.target_lufs)

    # 字幕垂直中心：优先 canvas_info.rect 中心（S5 的模糊带），否则用默认值
    canvas_info = {}
    ci_path = work / "canvas_info.json"
    if ci_path.exists():
        try:
            canvas_info = fe.json_load(str(ci_path))
        except Exception:
            canvas_info = {}
    if args.sub_center_y is not None:
        center_y = int(args.sub_center_y)
    elif canvas_info:
        center_y = _rect_center_y(canvas_info, DEFAULT_SUB_CENTER_Y)
        print(f"[S6] 字幕中心 y={center_y}（取自 canvas_info.rect）")
    else:
        center_y = DEFAULT_SUB_CENTER_Y
    center_y = int(subs_cfg.get("center_y", center_y))

    tmp = work / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    step = inp

    # ---------- 0) 字号自适应 ----------
    font_size, meter = choose_font_size(font_size, W, font_file,
                                        margin_h=margin_h, verbose=True)
    print(f"[S6] 字号 {font_size} / 可用宽 {meter.usable_px}px "
          f"（一行最多 {meter.capacity_cjk()} 个汉字）/ 中心 y={center_y}")

    # ---------- 1) BGM 混入 ----------
    if not args.no_bgm and args.bgm_style != "none":
        print(f"[S6] 生成程序化 BGM ({args.bgm_style}, {args.bgm_db}dB)...")
        try:
            bgm = generate_bgm(str(tmp / "bgm.m4a"), dur, args.bgm_style)
        except Exception as exc:
            print(f"[!] BGM 生成失败，跳过：{exc}")
            bgm = None
        if bgm:
            mixed = tmp / "with_bgm.mp4"
            rc, _, err = fe.run([
                "-i", inp, "-i", bgm,
                "-filter_complex",
                f"[0:a]volume=1.0[a0];[1:a]volume={args.bgm_db}dB[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", "-y", str(mixed),
            ])
            if rc != 0 or not mixed.exists():
                print(f"[!] BGM 混合失败，跳过 BGM:\n{err[-400:]}")
            else:
                step = str(mixed)
                print("     BGM 已混入")

    # ---------- 2) ASS 字幕 ----------
    ass_path = None
    dials: list[dict] = []
    dropped: list[dict] = []
    src_label = "none"
    if not args.no_subs:
        edl_csv = Path(args.edl) if args.edl else (work / "edl.csv")
        if not edl_csv.exists():
            print(f"[S6] [FAIL] 缺少 {edl_csv}，字幕无法生成"
                  f"（确需无字幕成片请显式加 --no-subs）")
            sys.exit(1)
        with open(edl_csv, "r", encoding="utf-8-sig") as f:
            edl_rows = list(_csv.DictReader(f))

        # ★人工校对稿优先：存在即完全替代 ASR remap
        cues_path = Path(args.cues) if args.cues else (work / "cues.json")
        use_cues = (not args.no_cues) and cues_path.exists()

        if use_cues:
            cues = load_cues(str(cues_path))
            dials, dropped = remap_cues(edl_rows, cues,
                                        coverage_min=args.coverage_min)
            src_label = f"cues:{cues_path.name}"
            print(f"[S6] 字幕来源：人工校对稿 {cues_path.name}（已跳过 ASR/text_fixes）")
        else:
            asr_path = Path(args.asr) if args.asr else (work / "asr.json")
            if not asr_path.exists():
                print(f"[S6] [FAIL] 缺少 {asr_path}，且无 cues.json，字幕无法生成"
                      f"（确需无字幕成片请显式加 --no-subs）")
                sys.exit(1)
            asr_data = fe.json_load(str(asr_path))
            dials, dropped = remap_dialogues(edl_rows, asr_data, str(work),
                                             text_fixes=text_fixes,
                                             coverage_min=args.coverage_min)
            src_label = f"asr:{asr_path.name}"

        if dials:
            expanded: list[dict] = []
            for d in dials:
                segs = build_subtitle_segments(
                    d, meter, min_dur=args.min_dur, max_dur=args.max_dur, max_lines=1)
                # 人工稿每条本应就是一屏；被像素宽度或 max_dur 再切要显式标出来
                if use_cues and len(segs) > 1:
                    for s in segs:
                        s["resplit"] = True
                expanded.extend(segs)
                # 全局互斥兜底（跨段重排后可能出现跨句重叠）：只夹时间，不丢字
                expanded.sort(key=lambda x: (x["start"], x["end"]))
                for i in range(1, len(expanded)):
                    if expanded[i]["start"] < expanded[i - 1]["end"]:
                        expanded[i]["start"] = expanded[i - 1]["end"]
                        if expanded[i]["end"] <= expanded[i]["start"]:
                            expanded[i]["end"] = expanded[i]["start"] + 0.01
                        expanded[i]["warn"] = "时间被前一条挤压（已夹到互斥）"
                ass_path = write_ass(str(work / "final.ass"), expanded, W, H,
                                     font, font_size, center_y=center_y, meter=meter)
                print(f"[S6] ASS 字幕 {len(dials)} 条台词 → {len(expanded)} 屏 "
                      f"→ {work / 'final.ass'}")
                dials = expanded
                warn_short = [d for d in dials if d.get("warn") == "short_reading"]
                if warn_short:
                    print(f"     [!] {len(warn_short)} 屏时长 < {args.min_dur}s（short_reading）")
                other = [d for d in dials if d.get("warn") and d.get("warn") != "short_reading"]
                if other:
                    print(f"     [!] {len(other)} 条字幕时间异常")
                    for d in other[:5]:
                        print(f"         {d['start']:.2f}s 「{d['text'][:24]}」{d['warn']}")
                resplit_n = sum(1 for d in dials if d.get("resplit"))
                if resplit_n:
                    print(f"     [!] {resplit_n} 屏由人工稿再切（resplit，原 cue 超宽或超 "
                          f"{args.max_dur}s）—— 建议人工稿按 {meter.capacity_cjk()} 全角字改写")
            else:
                print("[S6] 无字幕（无台词落入 EDL 区间）")

    # ★无论有没有字幕都要落盘，且无字幕时写空列表（上一版只存 500 条且不清空 → 污染 S7）
    fe.json_dump({
        "count": len(dials),
        "dialogues": dials,          # 全量，不再截断
        "layout": {
            "canvas_w": W, "canvas_h": H,
            "font": font, "font_size": font_size,
            "font_file": font_file,
            "usable_px": meter.usable_px,
            "margin_h": meter.margin_h,
            "center_y": center_y,
            "margin_v": margin_v_for_center(H, center_y, font_size),
            "min_dur": args.min_dur, "max_dur": args.max_dur,
            "coverage_min": args.coverage_min,
            "source": src_label,
            "mode": "single-line",
        },
    }, str(work / "subs_debug.json"))
    fe.json_dump({
        "count": len(dropped),
        "dropped": dropped,
    }, str(work / "subs_dropped.json"))
    if dropped:
        by_reason: dict = {}
        for x in dropped:
            by_reason[x.get("reason", "?")] = by_reason.get(x.get("reason", "?"), 0) + 1
        print(f"[S6] 丢弃 {len(dropped)} 条（{src_label}）{by_reason} → subs_dropped.json")

    # ---------- 3) 烧录字幕（若有） ----------
    if ass_path:
        burned = tmp / "subs.mp4"
        ass_win = str(ass_path).replace("\\", "/").replace(":", "\\:")
        # 码率模式（平台 12-18Mbps 建议）或 CRF 质量模式
        if getattr(args, "min_bitrate", None):
            mbps = float(args.min_bitrate)
            venc = ["-c:v", "libx264", "-preset", "veryfast",
                    "-b:v", f"{mbps:g}M",
                    "-minrate", f"{mbps * 0.8:g}M",
                    "-maxrate", f"{mbps * 1.25:g}M",
                    "-bufsize", f"{mbps * 2:g}M"]
        else:
            venc = ["-c:v", "libx264", "-crf", "19", "-preset", "veryfast"]
        rc, _, err = fe.run([
            "-i", step, "-vf",
            f"ass='{ass_win}':fontsdir='C\\:/Windows/Fonts'",
            *venc,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", "-y", str(burned),
        ])
        if rc != 0 or not burned.exists():
            # ★不再静默降级出「无字幕成片」——那是最难发现的交付事故
            print(f"[S6] [FAIL] 字幕烧录失败（未加 --no-subs，拒绝静默降级）:\n{err[-800:]}")
            sys.exit(1)
        step = str(burned)
        print("     字幕已烧录")

    # ---------- 4) 响度归一化（视频流 copy） ----------
    print(f"[S6] 响度归一化 → {args.target_lufs} LUFS（双遍）")
    fe.loudnorm_two_pass(step, out, target_lufs=args.target_lufs, keep_video_copy=True)

    oinfo = fe.probe(out)
    lufs = fe.measure_lufs(out)
    print(f"\n[S6] 完成 → {out}")
    print(f"     {oinfo['width']}x{oinfo['height']} {oinfo['duration']:.2f}s "
          f"{oinfo['size_mb']}MB / {lufs:.1f} LUFS")
    fe.json_dump({
        "final": out, "duration": oinfo["duration"], "lufs": round(lufs, 2),
        "subs_count": len(dials),
        "dropped_count": len(dropped),
        "center_y": center_y, "font_size": font_size,
        "usable_px": meter.usable_px,
        "subs_source": src_label,
        "bgm": args.bgm_style if not args.no_bgm else "none",
    }, str(work / "final_info.json"))


if __name__ == "__main__":
    main()
